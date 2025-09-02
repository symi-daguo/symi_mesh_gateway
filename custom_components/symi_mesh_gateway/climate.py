"""Climate platform for Symi Mesh Gateway."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SymiGatewayCoordinator
from .entity import SymiBaseEntity
from .protocol import SymiDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    for device in coordinator.devices.values():
        # Check if device should create climate entities
        if device.platform == "climate":
            entities.append(SymiClimateEntity(coordinator, device))
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d climate entities", len(entities))


class SymiClimateEntity(SymiBaseEntity, ClimateEntity):
    """Symi climate entity."""

    def __init__(
        self,
        coordinator: SymiGatewayCoordinator,
        device: SymiDevice,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, device)
        
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
        )
        
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.FAN_ONLY]
        self._attr_fan_modes = ["自动", "高速", "中速", "低速"]
        
        self._attr_min_temp = 5
        self._attr_max_temp = 35
        self._attr_target_temperature_step = 1
        
        self._attr_icon = "mdi:thermostat"

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        device_state = self.coordinator.get_device_state(self.device_id)
        temp_raw = device_state.get("current_temperature")
        
        if temp_raw is not None:
            return temp_raw / 100.0  # Convert from raw to celsius
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        device_state = self.coordinator.get_device_state(self.device_id)
        return device_state.get("target_temperature")

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current operation mode."""
        device_state = self.coordinator.get_device_state(self.device_id)
        mode = device_state.get("mode", 0)
        
        mode_map = {
            0: HVACMode.OFF,
            1: HVACMode.COOL,
            2: HVACMode.HEAT,
            3: HVACMode.FAN_ONLY,
        }
        
        return mode_map.get(mode, HVACMode.OFF)

    @property
    def fan_mode(self) -> str | None:
        """Return current fan mode."""
        device_state = self.coordinator.get_device_state(self.device_id)
        fan_speed = device_state.get("fan_speed", 0)
        
        fan_map = {
            0: "自动",
            1: "高速",
            2: "中速", 
            3: "低速",
            4: "自动",
        }
        
        return fan_map.get(fan_speed, "自动")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
            
        # Clamp temperature to valid range
        temperature = max(self._attr_min_temp, min(self._attr_max_temp, int(temperature)))
        
        # Send temperature control command
        from .protocol import SymiProtocol
        command = SymiProtocol.create_control_command(
            self._device.network_address,
            0x1B,  # TMPC_TEMP
            temperature
        )
        
        response_data = await self.coordinator.connection.send_command(command)
        if response_data:
            response = SymiProtocol.parse_response(response_data)
            if response and response["status"] == 0:  # RESULT_CMD_OK
                # Update state immediately
                self.coordinator._device_states.setdefault(self.device_id, {})["target_temperature"] = temperature
                self.async_write_ha_state()
                _LOGGER.debug("Temperature set successfully: %s to %d°C", self.device_id, temperature)
            else:
                _LOGGER.error("Failed to set temperature %s", self.device_id)
        else:
            _LOGGER.error("No response for temperature command: %s", self.device_id)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        mode_map = {
            HVACMode.OFF: 0,
            HVACMode.COOL: 1,
            HVACMode.HEAT: 2,
            HVACMode.FAN_ONLY: 3,
        }
        
        mode_value = mode_map.get(hvac_mode, 0)
        
        # Send mode control command
        from .protocol import SymiProtocol
        command = SymiProtocol.create_control_command(
            self._device.network_address,
            0x1D,  # TMPC_MODE
            mode_value
        )
        
        response_data = await self.coordinator.connection.send_command(command)
        if response_data:
            response = SymiProtocol.parse_response(response_data)
            if response and response["status"] == 0:  # RESULT_CMD_OK
                # Update state immediately
                self.coordinator._device_states.setdefault(self.device_id, {})["mode"] = mode_value
                self.async_write_ha_state()
                _LOGGER.debug("HVAC mode set successfully: %s to %s", self.device_id, hvac_mode)
            else:
                _LOGGER.error("Failed to set HVAC mode %s", self.device_id)
        else:
            _LOGGER.error("No response for HVAC mode command: %s", self.device_id)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        fan_map = {
            "自动": 4,
            "高速": 1,
            "中速": 2,
            "低速": 3,
        }
        
        fan_value = fan_map.get(fan_mode, 4)
        
        # Send fan speed control command
        from .protocol import SymiProtocol
        command = SymiProtocol.create_control_command(
            self._device.network_address,
            0x1C,  # TMPC_WIND_SPEED
            fan_value
        )
        
        response_data = await self.coordinator.connection.send_command(command)
        if response_data:
            response = SymiProtocol.parse_response(response_data)
            if response and response["status"] == 0:  # RESULT_CMD_OK
                # Update state immediately
                self.coordinator._device_states.setdefault(self.device_id, {})["fan_speed"] = fan_value
                self.async_write_ha_state()
                _LOGGER.debug("Fan mode set successfully: %s to %s", self.device_id, fan_mode)
            else:
                _LOGGER.error("Failed to set fan mode %s", self.device_id)
        else:
            _LOGGER.error("No response for fan mode command: %s", self.device_id)

    def _handle_status_update(self, updated_states: dict[str, Any]) -> None:
        """Handle status update from coordinator."""
        if any(key in updated_states for key in ["current_temperature", "target_temperature", "mode", "fan_speed"]):
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = {
            "device_type": self._device.device_type,
            "network_address": f"0x{self._device.network_address:04X}",
            "rssi": self._device.rssi,
            "vendor_id": self._device.vendor_id,
        }
        
        device_state = self.coordinator.get_device_state(self.device_id)
        
        # Add keyboard lock status if available
        if "keyboard_lock" in device_state:
            attributes["keyboard_lock"] = device_state["keyboard_lock"]
            
        # Add valve status if available
        if "valve_status" in device_state:
            attributes["valve_status"] = device_state["valve_status"]
            
        return attributes