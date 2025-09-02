"""Cover platform for Symi Mesh Gateway."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
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
    """Set up cover entities."""
    coordinator: SymiGatewayCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    for device in coordinator.devices.values():
        # Check if device should create cover entities
        if device.platform == "cover":
            entities.append(SymiCoverEntity(coordinator, device))
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d cover entities", len(entities))


class SymiCoverEntity(SymiBaseEntity, CoverEntity):
    """Symi cover entity."""

    def __init__(
        self,
        coordinator: SymiGatewayCoordinator,
        device: SymiDevice,
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator, device)
        
        self._attr_device_class = CoverDeviceClass.CURTAIN
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )
        self._attr_icon = "mdi:curtains"

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover (0-100)."""
        device_state = self.coordinator.get_device_state(self.device_id)
        return device_state.get("position", 0)

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        device_state = self.coordinator.get_device_state(self.device_id)
        return device_state.get("status") == 1  # 1 = opening

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        device_state = self.coordinator.get_device_state(self.device_id)
        return device_state.get("status") == 2  # 2 = closing

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        position = self.current_cover_position
        return position == 0 if position is not None else None

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # Send curtain control command (status = 1 for open)
        from .protocol import SymiProtocol
        command = SymiProtocol.create_control_command(
            self._device.network_address,
            0x05,  # CURT_RUN_STATUS
            1      # Open
        )
        
        response_data = await self.coordinator.connection.send_command(command)
        if response_data:
            response = SymiProtocol.parse_response(response_data)
            if response and response["status"] == 0:  # RESULT_CMD_OK
                # Update state immediately
                self.coordinator._device_states.setdefault(self.device_id, {})["status"] = 1
                self.async_write_ha_state()
                _LOGGER.debug("Cover open command sent successfully: %s", self.device_id)
            else:
                _LOGGER.error("Failed to open cover %s", self.device_id)
        else:
            _LOGGER.error("No response for cover open command: %s", self.device_id)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        # Send curtain control command (status = 2 for close)
        from .protocol import SymiProtocol
        command = SymiProtocol.create_control_command(
            self._device.network_address,
            0x05,  # CURT_RUN_STATUS
            2      # Close
        )
        
        response_data = await self.coordinator.connection.send_command(command)
        if response_data:
            response = SymiProtocol.parse_response(response_data)
            if response and response["status"] == 0:  # RESULT_CMD_OK
                # Update state immediately
                self.coordinator._device_states.setdefault(self.device_id, {})["status"] = 2
                self.async_write_ha_state()
                _LOGGER.debug("Cover close command sent successfully: %s", self.device_id)
            else:
                _LOGGER.error("Failed to close cover %s", self.device_id)
        else:
            _LOGGER.error("No response for cover close command: %s", self.device_id)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        # Send curtain control command (status = 3 for stop)
        from .protocol import SymiProtocol
        command = SymiProtocol.create_control_command(
            self._device.network_address,
            0x05,  # CURT_RUN_STATUS
            3      # Stop
        )
        
        response_data = await self.coordinator.connection.send_command(command)
        if response_data:
            response = SymiProtocol.parse_response(response_data)
            if response and response["status"] == 0:  # RESULT_CMD_OK
                # Update state immediately
                self.coordinator._device_states.setdefault(self.device_id, {})["status"] = 3
                self.async_write_ha_state()
                _LOGGER.debug("Cover stop command sent successfully: %s", self.device_id)
            else:
                _LOGGER.error("Failed to stop cover %s", self.device_id)
        else:
            _LOGGER.error("No response for cover stop command: %s", self.device_id)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = kwargs.get(ATTR_POSITION, 0)
        
        # Send curtain position command
        from .protocol import SymiProtocol
        command = SymiProtocol.create_control_command(
            self._device.network_address,
            0x06,  # CURT_RUN_PER_POS
            position
        )
        
        response_data = await self.coordinator.connection.send_command(command)
        if response_data:
            response = SymiProtocol.parse_response(response_data)
            if response and response["status"] == 0:  # RESULT_CMD_OK
                # Update state immediately
                self.coordinator._device_states.setdefault(self.device_id, {})["position"] = position
                self.async_write_ha_state()
                _LOGGER.debug("Cover position set successfully: %s to %d", self.device_id, position)
            else:
                _LOGGER.error("Failed to set cover position %s", self.device_id)
        else:
            _LOGGER.error("No response for cover position command: %s", self.device_id)

    def _handle_status_update(self, updated_states: dict[str, Any]) -> None:
        """Handle status update from coordinator."""
        if any(key in updated_states for key in ["status", "position"]):
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
        if "status" in device_state:
            status_map = {0: "unknown", 1: "opening", 2: "closing", 3: "stopped"}
            attributes["run_status"] = status_map.get(device_state["status"], "unknown")
            
        return attributes