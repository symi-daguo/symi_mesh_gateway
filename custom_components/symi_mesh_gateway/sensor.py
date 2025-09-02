"""Sensor platform for Symi Mesh Gateway."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
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
    """Set up sensor entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    for device in coordinator.devices.values():
        # Check if device should create sensor entities
        if device.platform == "sensor":
            if device.device_type == 11:  # 温湿度传感器
                # Create temperature and humidity sensors
                entities.append(SymiTemperatureSensor(coordinator, device))
                entities.append(SymiHumiditySensor(coordinator, device))
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d sensor entities", len(entities))


class SymiBaseSensor(SymiBaseEntity, SensorEntity):
    """Base class for Symi sensors."""

    def __init__(
        self,
        coordinator: SymiGatewayCoordinator,
        device: SymiDevice,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device)
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{device.unique_id}_{sensor_type}"

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
            
        return attributes


class SymiTemperatureSensor(SymiBaseSensor):
    """Symi temperature sensor."""

    def __init__(
        self,
        coordinator: SymiGatewayCoordinator,
        device: SymiDevice,
    ) -> None:
        """Initialize the temperature sensor."""
        super().__init__(coordinator, device, "temperature")
        
        self._attr_name = f"{device.device_name} 温度"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:thermometer"
        self._state_key = "temperature"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        device_state = self.coordinator.get_device_state(self.device_id)
        temp_raw = device_state.get(self._state_key)
        
        if temp_raw is not None:
            # Temperature is stored as integer * 100, convert to float
            return temp_raw / 100.0
        
        return None


class SymiHumiditySensor(SymiBaseSensor):
    """Symi humidity sensor."""

    def __init__(
        self,
        coordinator: SymiGatewayCoordinator,
        device: SymiDevice,
    ) -> None:
        """Initialize the humidity sensor."""
        super().__init__(coordinator, device, "humidity")
        
        self._attr_name = f"{device.device_name} 湿度"
        self._attr_device_class = SensorDeviceClass.HUMIDITY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:water-percent"
        self._state_key = "humidity"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        device_state = self.coordinator.get_device_state(self.device_id)
        return device_state.get(self._state_key)