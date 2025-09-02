"""Binary sensor platform for Symi Mesh Gateway."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up binary sensor entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    for device in coordinator.devices.values():
        # Check if device should create binary sensor entities
        if device.platform == "binary_sensor":
            entities.append(SymiBinarySensorEntity(coordinator, device))
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d binary sensor entities", len(entities))


class SymiBinarySensorEntity(SymiBaseEntity, BinarySensorEntity):
    """Symi binary sensor entity."""

    def __init__(
        self,
        coordinator: SymiGatewayCoordinator,
        device: SymiDevice,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, device)
        
        # Set device class and attributes based on device type
        if device.device_type == 7:  # 门磁传感器
            self._attr_device_class = BinarySensorDeviceClass.DOOR
            self._attr_icon = "mdi:door"
            self._state_key = "door_status"
        elif device.device_type == 8:  # 人体感应
            self._attr_device_class = BinarySensorDeviceClass.MOTION
            self._attr_icon = "mdi:motion-sensor"
            self._state_key = "motion_status"
        else:
            self._attr_device_class = BinarySensorDeviceClass.GENERIC
            self._attr_icon = "mdi:radiobox-blank"
            self._state_key = "sensor_status"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        device_state = self.coordinator.get_device_state(self.device_id)
        return device_state.get(self._state_key, False)

    def _handle_status_update(self, updated_states: dict[str, Any]) -> None:
        """Handle status update from coordinator."""
        if self._state_key in updated_states:
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
        
        # Add battery level if available
        if "battery_level" in device_state:
            attributes["battery_level"] = device_state["battery_level"]
            
        # Add tamper status if available
        if "tamper_alarm" in device_state:
            attributes["tamper_alarm"] = device_state["tamper_alarm"]
            
        return attributes