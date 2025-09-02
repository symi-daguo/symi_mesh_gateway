"""Device manager for Symi Mesh Gateway."""
from __future__ import annotations

import logging
from typing import Any, Callable

from .const import (
    MSG_TYPE_LIGHT_BRIGHTNESS,
    MSG_TYPE_LIGHT_COLOR_TEMP,
    MSG_TYPE_ON_OFF,
    OP_DEVICE_LIST_RESPONSE,
    OP_DEVICE_STATUS_EVENT,
    RESULT_CMD_OK,
    RESULT_EVENT_NODE_STATUS,
)
from .protocol import DeviceStatus, SymiDevice, SymiProtocol
from .tcp_comm import SymiTCPConnection

_LOGGER = logging.getLogger(__name__)


class SymiDeviceManager:
    """Manage Symi devices and communication."""
    
    def __init__(self, connection: SymiTCPConnection):
        """Initialize device manager."""
        self.connection = connection
        self.devices: dict[str, SymiDevice] = {}
        self.device_states: dict[str, dict[str, Any]] = {}
        self._status_callbacks: list[Callable[[str, dict[str, Any]], None]] = []
        
        # Register message handler
        connection.add_message_handler(self._handle_message)
    
    async def discover_devices(self) -> list[SymiDevice]:
        """Discover all devices connected to the gateway."""
        if not self.connection.connected:
            _LOGGER.error("Cannot discover devices: not connected to gateway")
            return []
            
        try:
            # Send device list query command
            command = SymiProtocol.create_device_list_command()
            response_data = await self.connection.send_command(command)
            
            if not response_data:
                _LOGGER.error("No response received for device list query")
                return []
                
            # Parse response
            response = SymiProtocol.parse_response(response_data)
            if not response:
                _LOGGER.error("Failed to parse device list response")
                return []
                
            if response["opcode"] != OP_DEVICE_LIST_RESPONSE:
                _LOGGER.error("Unexpected response opcode: %02X", response["opcode"])
                return []
                
            if response["status"] != RESULT_CMD_OK:
                _LOGGER.error("Device list query failed with status: %02X", response["status"])
                return []
                
            # Parse device list
            devices = SymiProtocol.parse_device_list(response["data"])
            
            # Update device registry
            for device in devices:
                self.devices[device.unique_id] = device
                # Initialize device state
                if device.unique_id not in self.device_states:
                    self.device_states[device.unique_id] = {}
                    
            _LOGGER.info("Discovered %d devices", len(devices))
            return devices
            
        except Exception as err:
            _LOGGER.error("Error discovering devices: %s", err)
            return []
    
    async def control_switch(
        self, 
        device_id: str, 
        channel: int, 
        state: bool
    ) -> bool:
        """Control switch device."""
        device = self.devices.get(device_id)
        if not device:
            _LOGGER.error("Device not found: %s", device_id)
            return False
            
        try:
            # Encode switch value
            value = SymiProtocol.encode_switch_value(device.channels, channel, state)
            
            # Send control command
            command = SymiProtocol.create_control_command(
                device.network_address,
                MSG_TYPE_ON_OFF,
                value
            )
            
            response_data = await self.connection.send_command(command)
            if response_data:
                response = SymiProtocol.parse_response(response_data)
                if response and response["status"] == RESULT_CMD_OK:
                    # Update local state
                    self._update_device_state(device_id, f"switch_{channel}", state)
                    _LOGGER.debug("Switch control successful: %s channel %d = %s", 
                                device_id, channel, state)
                    return True
                    
            _LOGGER.error("Switch control failed for device %s", device_id)
            return False
            
        except Exception as err:
            _LOGGER.error("Error controlling switch %s: %s", device_id, err)
            return False
    
    async def control_light_brightness(
        self, 
        device_id: str, 
        brightness: int
    ) -> bool:
        """Control light brightness (0-100)."""
        device = self.devices.get(device_id)
        if not device:
            _LOGGER.error("Device not found: %s", device_id)
            return False
            
        if not device.supports_brightness:
            _LOGGER.error("Device does not support brightness control: %s", device_id)
            return False
            
        try:
            # Send brightness control command
            command = SymiProtocol.create_control_command(
                device.network_address,
                MSG_TYPE_LIGHT_BRIGHTNESS,
                brightness
            )
            
            response_data = await self.connection.send_command(command)
            if response_data:
                response = SymiProtocol.parse_response(response_data)
                if response and response["status"] == RESULT_CMD_OK:
                    # Update local state
                    self._update_device_state(device_id, "brightness", brightness)
                    _LOGGER.debug("Brightness control successful: %s = %d", device_id, brightness)
                    return True
                    
            _LOGGER.error("Brightness control failed for device %s", device_id)
            return False
            
        except Exception as err:
            _LOGGER.error("Error controlling brightness %s: %s", device_id, err)
            return False
    
    async def control_light_color_temp(
        self, 
        device_id: str, 
        color_temp: int
    ) -> bool:
        """Control light color temperature (0-100)."""
        device = self.devices.get(device_id)
        if not device:
            _LOGGER.error("Device not found: %s", device_id)
            return False
            
        if not device.supports_color_temp:
            _LOGGER.error("Device does not support color temperature control: %s", device_id)
            return False
            
        try:
            # Send color temperature control command
            command = SymiProtocol.create_control_command(
                device.network_address,
                MSG_TYPE_LIGHT_COLOR_TEMP,
                color_temp
            )
            
            response_data = await self.connection.send_command(command)
            if response_data:
                response = SymiProtocol.parse_response(response_data)
                if response and response["status"] == RESULT_CMD_OK:
                    # Update local state
                    self._update_device_state(device_id, "color_temp", color_temp)
                    _LOGGER.debug("Color temperature control successful: %s = %d", device_id, color_temp)
                    return True
                    
            _LOGGER.error("Color temperature control failed for device %s", device_id)
            return False
            
        except Exception as err:
            _LOGGER.error("Error controlling color temperature %s: %s", device_id, err)
            return False
    
    def get_device_state(self, device_id: str) -> dict[str, Any]:
        """Get current device state."""
        return self.device_states.get(device_id, {})
    
    def get_device(self, device_id: str) -> SymiDevice | None:
        """Get device by ID."""
        return self.devices.get(device_id)
    
    def get_all_devices(self) -> list[SymiDevice]:
        """Get all registered devices."""
        return list(self.devices.values())
    
    def add_status_callback(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Add status update callback."""
        self._status_callbacks.append(callback)
    
    def remove_status_callback(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Remove status update callback."""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
    
    def _handle_message(self, data: bytes) -> None:
        """Handle incoming messages from gateway."""
        try:
            response = SymiProtocol.parse_response(data)
            if not response:
                return
                
            # Handle status events
            if (response["opcode"] == OP_DEVICE_STATUS_EVENT and 
                response["status"] == RESULT_EVENT_NODE_STATUS):
                self._handle_status_event(response["data"])
                
        except Exception as err:
            _LOGGER.error("Error handling message: %s", err)
    
    def _handle_status_event(self, data: bytes) -> None:
        """Handle device status event."""
        statuses = SymiProtocol.parse_status_event(data)
        if not statuses:
            return
            
        # Find device by network address
        device = None
        for dev in self.devices.values():
            if dev.network_address == statuses[0].network_address:
                device = dev
                break
                
        if not device:
            _LOGGER.warning("Received status for unknown device: %04X", 
                          statuses[0].network_address)
            return
            
        # Update device states
        device_id = device.unique_id
        updated_states = {}
        
        for status in statuses:
            if status.msg_type == MSG_TYPE_ON_OFF:
                # Decode switch states
                switch_states = SymiProtocol.decode_switch_value(status.value, device.channels)
                for channel, state in switch_states.items():
                    key = f"switch_{channel}"
                    self._update_device_state(device_id, key, state)
                    updated_states[key] = state
                    
            elif status.msg_type == MSG_TYPE_LIGHT_BRIGHTNESS:
                self._update_device_state(device_id, "brightness", status.value)
                updated_states["brightness"] = status.value
                
            elif status.msg_type == MSG_TYPE_LIGHT_COLOR_TEMP:
                self._update_device_state(device_id, "color_temp", status.value)
                updated_states["color_temp"] = status.value
        
        # Notify callbacks
        if updated_states:
            for callback in self._status_callbacks:
                try:
                    callback(device_id, updated_states)
                except Exception as err:
                    _LOGGER.error("Error in status callback: %s", err)
    
    def _update_device_state(self, device_id: str, key: str, value: Any) -> None:
        """Update device state."""
        if device_id not in self.device_states:
            self.device_states[device_id] = {}
        self.device_states[device_id][key] = value