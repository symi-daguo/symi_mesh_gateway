"""DataUpdateCoordinator for Symi Mesh Gateway."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .device_manager import SymiDeviceManager
from .protocol import SymiDevice
from .tcp_comm import SymiTCPConnection

_LOGGER = logging.getLogger(__name__)


class SymiGatewayCoordinator(DataUpdateCoordinator):
    """Coordinator for Symi Mesh Gateway."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.port = entry.data[CONF_PORT]
        self.timeout = entry.data[CONF_TIMEOUT]
        
        # Initialize connection and device manager
        self.connection = SymiTCPConnection(self.host, self.port, self.timeout)
        self.device_manager = SymiDeviceManager(self.connection)
        
        # Track devices and their states
        self.devices: dict[str, SymiDevice] = {}
        self._device_states: dict[str, dict[str, Any]] = {}
        self._status_callbacks: dict[str, list[Callable]] = {}
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        
        # Register for device status updates
        self.device_manager.add_status_callback(self._handle_status_update)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            if not self.connection.connected:
                _LOGGER.info("Connecting to gateway at %s:%s", self.host, self.port)
                if not await self.connection.connect():
                    raise UpdateFailed("Failed to connect to gateway")
                
                # Discover devices after connection
                await self._discover_devices()
            
            # Return current device states
            return {
                "devices": self.devices,
                "states": self._device_states,
                "connected": self.connection.connected
            }
            
        except Exception as err:
            _LOGGER.error("Error updating data: %s", err)
            raise UpdateFailed(f"Error communicating with gateway: {err}") from err

    async def _discover_devices(self) -> None:
        """Discover devices and update registry."""
        try:
            _LOGGER.info("Discovering devices...")
            
            # Send device discovery command and let the message handler process responses
            await self.device_manager.discover_devices()
            
            # Give some time for responses to arrive
            await asyncio.sleep(2)
            
            # Update coordinator devices from device manager
            self.devices = dict(self.device_manager.devices)
            self._device_states = dict(self.device_manager.device_states)
                    
            _LOGGER.info("Device discovery complete. Total devices: %d", len(self.devices))
            
        except Exception as err:
            _LOGGER.error("Error discovering devices: %s", err)
            raise

    async def async_control_switch(self, device_id: str, channel: int, state: bool) -> bool:
        """Control switch device."""
        return await self.device_manager.control_switch(device_id, channel, state)

    async def async_control_light_brightness(self, device_id: str, brightness: int) -> bool:
        """Control light brightness."""
        return await self.device_manager.control_light_brightness(device_id, brightness)

    async def async_control_light_color_temp(self, device_id: str, color_temp: int) -> bool:
        """Control light color temperature."""
        return await self.device_manager.control_light_color_temp(device_id, color_temp)

    def get_device(self, device_id: str) -> SymiDevice | None:
        """Get device by ID."""
        return self.devices.get(device_id)

    def get_device_state(self, device_id: str) -> dict[str, Any]:
        """Get device state."""
        return self._device_states.get(device_id, {})

    def add_status_callback(self, device_id: str, callback: Callable) -> None:
        """Add status update callback for specific device."""
        if device_id not in self._status_callbacks:
            self._status_callbacks[device_id] = []
        self._status_callbacks[device_id].append(callback)

    def remove_status_callback(self, device_id: str, callback: Callable) -> None:
        """Remove status update callback."""
        if device_id in self._status_callbacks and callback in self._status_callbacks[device_id]:
            self._status_callbacks[device_id].remove(callback)

    def _handle_status_update(self, device_id: str, updated_states: dict[str, Any]) -> None:
        """Handle device status update."""
        # Update internal state
        if device_id not in self._device_states:
            self._device_states[device_id] = {}
        self._device_states[device_id].update(updated_states)
        
        # Call device-specific callbacks
        if device_id in self._status_callbacks:
            for callback in self._status_callbacks[device_id]:
                try:
                    callback(updated_states)
                except Exception as err:
                    _LOGGER.error("Error in status callback for %s: %s", device_id, err)
        
        # Trigger coordinator update to notify all entities
        self.async_set_updated_data(self.data or {})

    async def async_shutdown(self) -> None:
        """Shutdown coordinator."""
        _LOGGER.info("Shutting down Symi Gateway coordinator")
        
        # Remove status callback
        self.device_manager.remove_status_callback(self._handle_status_update)
        
        # Disconnect from gateway
        if self.connection.connected:
            await self.connection.disconnect()


async def async_get_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> SymiGatewayCoordinator:
    """Get coordinator for the given config entry."""
    coordinator = SymiGatewayCoordinator(hass, entry)
    
    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()
    
    return coordinator