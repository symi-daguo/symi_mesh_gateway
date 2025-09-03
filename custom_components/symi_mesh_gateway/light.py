"""Light platform for Symi Mesh Gateway."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
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
    """Set up light entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    for device in coordinator.devices.values():
        # Check if device should create light entities
        if device.platform == "light":
            entities.append(SymiLightEntity(coordinator, device))
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d light entities", len(entities))


class SymiLightEntity(SymiBaseEntity, LightEntity):
    """Symi light entity."""

    def __init__(
        self,
        coordinator: SymiGatewayCoordinator,
        device: SymiDevice,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator, device)
        
        self._attr_icon = "mdi:lightbulb"
        
        # Set supported color modes based on device capabilities
        supported_color_modes = {ColorMode.ONOFF}
        
        if device.supports_brightness:
            supported_color_modes.add(ColorMode.BRIGHTNESS)
            
        if device.supports_color_temp:
            supported_color_modes.add(ColorMode.COLOR_TEMP)
            # Set color temperature range (mireds)
            self._attr_min_mireds = 153  # ~6500K
            self._attr_max_mireds = 500  # ~2000K
            
        self._attr_supported_color_modes = supported_color_modes
        
        # Set initial color mode
        if ColorMode.COLOR_TEMP in supported_color_modes:
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif ColorMode.BRIGHTNESS in supported_color_modes:
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        device_state = self.coordinator.get_device_state(self.device_id)
        
        # Check if brightness > 0 or switch is on
        brightness = device_state.get("brightness", 0)
        switch_state = device_state.get("switch_1", False)
        
        return brightness > 0 or switch_state

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light (0..255)."""
        if not self._device.supports_brightness:
            return None
            
        device_state = self.coordinator.get_device_state(self.device_id)
        brightness_percent = device_state.get("brightness", 0)
        
        # Convert from percentage (0-100) to HA brightness (0-255)
        return int(brightness_percent * 255 / 100)

    @property
    def color_temp(self) -> int | None:
        """Return the color temperature in mireds."""
        if not self._device.supports_color_temp:
            return None
            
        device_state = self.coordinator.get_device_state(self.device_id)
        color_temp_percent = device_state.get("color_temp", 50)
        
        # Convert from percentage (0-100) to mireds
        # 0% = warm (500 mireds), 100% = cool (153 mireds)
        return int(self._attr_max_mireds - (color_temp_percent * (self._attr_max_mireds - self._attr_min_mireds) / 100))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        success = True
        
        # Handle brightness
        if ATTR_BRIGHTNESS in kwargs and self._device.supports_brightness:
            brightness_255 = kwargs[ATTR_BRIGHTNESS]
            brightness_percent = int(brightness_255 * 100 / 255)
            brightness_percent = max(1, min(100, brightness_percent))  # Clamp to 1-100
            
            success = await self.coordinator.async_control_light_brightness(
                self.device_id, brightness_percent
            )
            
            if success:
                # Update state immediately
                self.coordinator._device_states.setdefault(self.device_id, {})["brightness"] = brightness_percent
        
        # Handle color temperature
        if ATTR_COLOR_TEMP_KELVIN in kwargs and self._device.supports_color_temp:
            color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            # Convert from Kelvin to mireds, then to percentage
            color_temp_mireds = 1000000 / color_temp_kelvin
            color_temp_percent = int(100 - ((color_temp_mireds - self._attr_min_mireds) * 100 / (self._attr_max_mireds - self._attr_min_mireds)))
            color_temp_percent = max(0, min(100, color_temp_percent))
            
            success = await self.coordinator.async_control_light_color_temp(
                self.device_id, color_temp_percent
            ) and success
            
            if success:
                # Update state immediately
                self.coordinator._device_states.setdefault(self.device_id, {})["color_temp"] = color_temp_percent
        
        # If no brightness specified, turn on with default brightness
        if ATTR_BRIGHTNESS not in kwargs and self._device.supports_brightness:
            # Get current brightness or use 100%
            current_brightness = self.brightness
            if not current_brightness or current_brightness == 0:
                success = await self.coordinator.async_control_light_brightness(
                    self.device_id, 100
                )
                if success:
                    self.coordinator._device_states.setdefault(self.device_id, {})["brightness"] = 100
        
        # For basic on/off lights, send switch command
        if not self._device.supports_brightness:
            success = await self.coordinator.async_control_switch(
                self.device_id, 1, True
            )
            if success:
                self.coordinator._device_states.setdefault(self.device_id, {})["switch_1"] = True
        
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on light %s", self.device_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        success = True
        
        if self._device.supports_brightness:
            # Turn off by setting brightness to 0
            success = await self.coordinator.async_control_light_brightness(
                self.device_id, 0
            )
            if success:
                self.coordinator._device_states.setdefault(self.device_id, {})["brightness"] = 0
        else:
            # For basic on/off lights, send switch command
            success = await self.coordinator.async_control_switch(
                self.device_id, 1, False
            )
            if success:
                self.coordinator._device_states.setdefault(self.device_id, {})["switch_1"] = False
        
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off light %s", self.device_id)

    def _handle_status_update(self, updated_states: dict[str, Any]) -> None:
        """Handle status update from coordinator."""
        if any(key in updated_states for key in ["brightness", "color_temp", "switch_1"]):
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = {
            "device_type": self._device.device_type,
            "network_address": f"0x{self._device.network_address:04X}",
            "rssi": self._device.rssi,
            "vendor_id": self._device.vendor_id,
            "supports_brightness": self._device.supports_brightness,
            "supports_color_temp": self._device.supports_color_temp,
        }
        
        device_state = self.coordinator.get_device_state(self.device_id)
        if "brightness" in device_state:
            attributes["brightness_percent"] = device_state["brightness"]
        if "color_temp" in device_state:
            attributes["color_temp_percent"] = device_state["color_temp"]
            
        return attributes