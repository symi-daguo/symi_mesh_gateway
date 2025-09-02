"""Config flow for Symi Mesh Gateway integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DOMAIN,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_HOST,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN,
)
from .tcp_comm import SymiTCPConnection, discover_gateways

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    host = data[CONF_HOST]
    port = data[CONF_PORT]
    timeout = data[CONF_TIMEOUT]
    
    # Test connection
    connection = SymiTCPConnection(host, port, timeout)
    
    try:
        if not await connection.connect():
            raise CannotConnect("Failed to connect to gateway")
            
        # Try to discover devices to verify the gateway is working
        from .device_manager import SymiDeviceManager
        device_manager = SymiDeviceManager(connection)
        devices = await device_manager.discover_devices()
        
        # Close connection
        await connection.disconnect()
        
        # Return info that you want to store in the config entry
        return {
            "title": f"Symi Gateway ({host})",
            "device_count": len(devices)
        }
        
    except asyncio.TimeoutError as err:
        await connection.disconnect()
        raise CannotConnect("Connection timeout") from err
    except Exception as err:
        await connection.disconnect()
        raise CannotConnect(f"Connection failed: {err}") from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Symi Mesh Gateway."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        super().__init__()
        self._discovered_gateways: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            # Try to discover gateways automatically
            try:
                _LOGGER.info("Searching for Symi gateways on the network...")
                self._discovered_gateways = await discover_gateways(timeout=5)
                _LOGGER.info("Found %d gateways", len(self._discovered_gateways))
                
                if self._discovered_gateways:
                    return await self.async_step_discovery()
                    
            except Exception as err:
                _LOGGER.warning("Auto-discovery failed: %s", err)
            
            # No gateways found, show manual configuration
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={
                    "discovery_status": "未发现网关，请手动配置"
                }
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = ERROR_CANNOT_CONNECT
        except InvalidHost:
            errors[CONF_HOST] = ERROR_INVALID_HOST
        except TimeoutError:
            errors["base"] = ERROR_TIMEOUT
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = ERROR_UNKNOWN
        else:
            # Check if already configured
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors
        )

    async def async_step_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle discovery step."""
        if user_input is None:
            # Show discovered gateways
            gateway_options = {}
            for gateway_ip in self._discovered_gateways:
                gateway_options[gateway_ip] = f"Symi Gateway ({gateway_ip})"
            
            # Add manual option
            gateway_options["manual"] = "手动配置"
            
            return self.async_show_form(
                step_id="discovery",
                data_schema=vol.Schema({
                    vol.Required("gateway"): vol.In(gateway_options)
                }),
                description_placeholders={
                    "gateway_count": str(len(self._discovered_gateways))
                }
            )

        selected_gateway = user_input["gateway"]
        
        if selected_gateway == "manual":
            # User chose manual configuration
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA
            )
        
        # User selected a discovered gateway
        gateway_data = {
            CONF_HOST: selected_gateway,
            CONF_PORT: DEFAULT_PORT,
            CONF_TIMEOUT: DEFAULT_TIMEOUT
        }
        
        errors = {}
        
        try:
            info = await validate_input(self.hass, gateway_data)
        except CannotConnect:
            errors["base"] = ERROR_CANNOT_CONNECT
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = ERROR_UNKNOWN
        else:
            # Check if already configured
            await self.async_set_unique_id(selected_gateway)
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title=info["title"], 
                data=gateway_data,
                description_placeholders={
                    "device_count": str(info["device_count"])
                }
            )

        if errors:
            # Show error and let user choose again
            return self.async_show_form(
                step_id="discovery",
                data_schema=vol.Schema({
                    vol.Required("gateway"): vol.In({
                        gateway: f"Symi Gateway ({gateway})" 
                        for gateway in self._discovered_gateways
                    })
                }),
                errors=errors
            )

    async def async_step_zeroconf(
        self, discovery_info: dict[str, Any]
    ) -> FlowResult:
        """Handle zeroconf discovery."""
        host = discovery_info.get("host")
        if not host:
            return self.async_abort(reason="no_host")
            
        # Set unique_id to prevent duplicate entries
        await self.async_set_unique_id(host)
        self._abort_if_unique_id_configured()
        
        # Try to connect and validate
        gateway_data = {
            CONF_HOST: host,
            CONF_PORT: DEFAULT_PORT,
            CONF_TIMEOUT: DEFAULT_TIMEOUT
        }
        
        try:
            info = await validate_input(self.hass, gateway_data)
            return self.async_create_entry(title=info["title"], data=gateway_data)
        except Exception:
            # If validation fails, continue with user flow
            return await self.async_step_user()


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(HomeAssistantError):
    """Error to indicate invalid host."""