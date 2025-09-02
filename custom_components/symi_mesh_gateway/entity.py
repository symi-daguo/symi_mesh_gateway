"""Base entity for Symi Mesh Gateway."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SymiGatewayCoordinator
from .protocol import SymiDevice

_LOGGER = logging.getLogger(__name__)


class SymiBaseEntity(CoordinatorEntity[SymiGatewayCoordinator]):
    """Base class for Symi entities."""

    def __init__(
        self,
        coordinator: SymiGatewayCoordinator,
        device: SymiDevice,
        channel: int | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        
        self._device = device
        self._channel = channel
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.unique_id)},
            name=device.device_name,
            manufacturer="Symi",
            model=device.device_name,
            sw_version=f"Type {device.device_type}",
            via_device=(DOMAIN, coordinator.entry.entry_id),
        )
        
        # Generate unique_id
        if channel:
            self._attr_unique_id = f"{device.unique_id}_ch{channel}"
            self._attr_name = f"{device.device_name} 通道{channel}"
        else:
            self._attr_unique_id = device.unique_id
            self._attr_name = device.device_name
            
        # Add device status callback
        coordinator.add_status_callback(device.unique_id, self._handle_status_update)

    @property
    def device_id(self) -> str:
        """Return device ID."""
        return self._device.unique_id

    @property
    def channel(self) -> int | None:
        """Return channel number."""
        return self._channel

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data.get("connected", False)

    def _handle_status_update(self, updated_states: dict[str, Any]) -> None:
        """Handle status update from coordinator."""
        # This will be implemented by subclasses if needed
        pass

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("Added entity: %s", self.entity_id)

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        # Remove status callback
        self.coordinator.remove_status_callback(self.device_id, self._handle_status_update)
        await super().async_will_remove_from_hass()
        _LOGGER.debug("Removed entity: %s", self.entity_id)