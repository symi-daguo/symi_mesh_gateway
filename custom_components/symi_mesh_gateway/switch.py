"""Switch platform for Symi Mesh Gateway."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
    """Set up switch entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    for device in coordinator.devices.values():
        # Check if device should create switch entities
        if device.platform == "switch":
            # For multi-channel switches, create one entity per channel
            if device.channels > 1:
                for channel in range(1, device.channels + 1):
                    entities.append(SymiSwitchEntity(coordinator, device, channel))
            else:
                entities.append(SymiSwitchEntity(coordinator, device))
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d switch entities", len(entities))


class SymiSwitchEntity(SymiBaseEntity, SwitchEntity):
    """Symi switch entity."""

    def __init__(
        self,
        coordinator: SymiGatewayCoordinator,
        device: SymiDevice,
        channel: int | None = None,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, device, channel)
        
        # Set switch-specific attributes
        if channel:
            self._attr_name = f"{device.device_name} 开关{channel}"
            self._state_key = f"switch_{channel}"
        else:
            self._attr_name = f"{device.device_name}"
            self._state_key = "switch_1"
            
        self._attr_icon = "mdi:light-switch"

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        device_state = self.coordinator.get_device_state(self.device_id)
        return device_state.get(self._state_key, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        channel = self._channel or 1
        success = await self.coordinator.async_control_switch(
            self.device_id, channel, True
        )
        
        if success:
            # Update state immediately for better responsiveness
            self.coordinator._device_states.setdefault(self.device_id, {})[self._state_key] = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on switch %s channel %d", self.device_id, channel)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        channel = self._channel or 1
        success = await self.coordinator.async_control_switch(
            self.device_id, channel, False
        )
        
        if success:
            # Update state immediately for better responsiveness
            self.coordinator._device_states.setdefault(self.device_id, {})[self._state_key] = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off switch %s channel %d", self.device_id, channel)

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
        
        if self._channel:
            attributes["channel"] = self._channel
            
        return attributes