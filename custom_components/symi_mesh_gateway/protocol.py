"""Protocol parsing module for Symi Mesh Gateway."""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from typing import Any

from .const import (
    DEVICE_ADDR_OFFSET,
    DEVICE_DATA_SIZE,
    DEVICE_EXT_OFFSET,
    DEVICE_MAC_OFFSET,
    DEVICE_RSSI_OFFSET,
    DEVICE_SUBTYPE_OFFSET,
    DEVICE_TYPE_MAPPING,
    DEVICE_TYPE_OFFSET,
    DEVICE_TYPE_TO_PLATFORM,
    DEVICE_VENDOR_OFFSET,
    MSG_TYPE_LIGHT_BRIGHTNESS,
    MSG_TYPE_LIGHT_COLOR_TEMP,
    MSG_TYPE_ON_OFF,
    OP_DEVICE_CONTROL,
    OP_DEVICE_LIST_RESPONSE,
    OP_DEVICE_STATUS_EVENT,
    OP_READ_DEVICE_LIST,
    PROTOCOL_HEAD,
    RESULT_CMD_OK,
    RESULT_EVENT_NODE_STATUS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SymiDevice:
    """Symi device data structure."""
    mac_address: str
    network_address: int
    device_type: int
    device_subtype: int  # channels/routes
    rssi: int
    vendor_id: int
    extended_data: bytes
    
    @property
    def unique_id(self) -> str:
        """Generate unique device ID."""
        return self.mac_address.replace(":", "").lower()
    
    @property
    def device_name(self) -> str:
        """Get device type name."""
        return DEVICE_TYPE_MAPPING.get(self.device_type, f"未知设备({self.device_type})")
    
    @property
    def platform(self) -> str | None:
        """Get Home Assistant platform for this device."""
        return DEVICE_TYPE_TO_PLATFORM.get(self.device_type)
    
    @property
    def channels(self) -> int:
        """Get number of channels/routes."""
        # For switches, subtype indicates number of channels
        if self.device_type in [1, 2]:  # 零火开关, 单火开关
            return max(1, self.device_subtype) if self.device_subtype <= 6 else 1
        return 1
    
    @property
    def supports_brightness(self) -> bool:
        """Check if device supports brightness control."""
        return self.device_type in [4, 24]  # 智能灯, 五色调光灯
    
    @property
    def supports_color_temp(self) -> bool:
        """Check if device supports color temperature control."""
        return self.device_type in [4, 24]  # 智能灯, 五色调光灯


@dataclass
class DeviceStatus:
    """Device status data structure."""
    network_address: int
    msg_type: int
    value: Any
    

class SymiProtocol:
    """Symi protocol parser."""
    
    @staticmethod
    def create_device_list_command() -> list[int]:
        """Create device list query command."""
        return [PROTOCOL_HEAD, OP_READ_DEVICE_LIST, 0x00, 0x41]
    
    @staticmethod
    def create_control_command(
        network_address: int, 
        msg_type: int, 
        value: int
    ) -> list[int]:
        """Create device control command."""
        # Convert network address to little endian bytes
        addr_low = network_address & 0xFF
        addr_high = (network_address >> 8) & 0xFF
        
        return [
            PROTOCOL_HEAD,
            OP_DEVICE_CONTROL,
            0x04,  # data length
            addr_low,
            addr_high,
            msg_type,
            value
        ]
    
    @staticmethod
    def parse_response(data: bytes) -> dict[str, Any] | None:
        """Parse gateway response."""
        if len(data) < 4:
            _LOGGER.warning("Response too short: %s bytes", len(data))
            return None
            
        head, opcode, status, length = data[:4]
        
        if head != PROTOCOL_HEAD:
            _LOGGER.warning("Invalid protocol header: %02X", head)
            return None
            
        response = {
            "opcode": opcode,
            "status": status,
            "length": length,
            "data": data[4:4+length] if length > 0 else b""
        }
        
        _LOGGER.debug("Parsed response: opcode=%02X, status=%02X, length=%d", 
                     opcode, status, length)
        
        return response
    
    @staticmethod
    def parse_device_list(data: bytes) -> list[SymiDevice]:
        """Parse device list from response data."""
        devices = []
        
        if len(data) % DEVICE_DATA_SIZE != 0:
            _LOGGER.warning("Invalid device list data length: %d", len(data))
            return devices
            
        device_count = len(data) // DEVICE_DATA_SIZE
        _LOGGER.debug("Parsing %d devices from %d bytes", device_count, len(data))
        
        for i in range(device_count):
            offset = i * DEVICE_DATA_SIZE
            device_data = data[offset:offset + DEVICE_DATA_SIZE]
            
            try:
                device = SymiProtocol._parse_single_device(device_data)
                if device:
                    devices.append(device)
                    _LOGGER.debug("Parsed device: %s (%s)", device.mac_address, device.device_name)
            except Exception as err:
                _LOGGER.error("Error parsing device %d: %s", i, err)
                
        return devices
    
    @staticmethod
    def _parse_single_device(data: bytes) -> SymiDevice | None:
        """Parse single device from 16-byte data."""
        if len(data) != DEVICE_DATA_SIZE:
            return None
            
        # Extract MAC address (6 bytes)
        mac_bytes = data[DEVICE_MAC_OFFSET:DEVICE_MAC_OFFSET + 6]
        mac_address = ":".join(f"{b:02x}" for b in mac_bytes)
        
        # Extract network address (2 bytes, little endian)
        network_address = struct.unpack("<H", data[DEVICE_ADDR_OFFSET:DEVICE_ADDR_OFFSET + 2])[0]
        
        # Extract device type and subtype
        device_type = data[DEVICE_TYPE_OFFSET]
        device_subtype = data[DEVICE_SUBTYPE_OFFSET]
        
        # Extract RSSI (signed)
        rssi = struct.unpack("b", data[DEVICE_RSSI_OFFSET:DEVICE_RSSI_OFFSET + 1])[0]
        
        # Extract vendor ID
        vendor_id = data[DEVICE_VENDOR_OFFSET]
        
        # Extract extended data
        extended_data = data[DEVICE_EXT_OFFSET:DEVICE_EXT_OFFSET + 4]
        
        return SymiDevice(
            mac_address=mac_address,
            network_address=network_address,
            device_type=device_type,
            device_subtype=device_subtype,
            rssi=rssi,
            vendor_id=vendor_id,
            extended_data=extended_data
        )
    
    @staticmethod
    def parse_status_event(data: bytes) -> list[DeviceStatus] | None:
        """Parse device status event."""
        if len(data) < 6:
            _LOGGER.warning("Status event data too short: %s bytes", len(data))
            return None
            
        # Skip first byte (unknown)
        # Extract network address (2 bytes, little endian)
        network_address = struct.unpack("<H", data[1:3])[0]
        
        # Parse message type/value pairs
        statuses = []
        offset = 3
        
        while offset < len(data) - 1:  # -1 for checksum
            if offset + 1 >= len(data):
                break
                
            msg_type = data[offset]
            value = data[offset + 1]
            
            statuses.append(DeviceStatus(
                network_address=network_address,
                msg_type=msg_type,
                value=value
            ))
            
            offset += 2
            
        _LOGGER.debug("Parsed %d status updates for device %04X", 
                     len(statuses), network_address)
        
        return statuses
    
    @staticmethod
    def encode_switch_value(channels: int, channel: int, state: bool) -> int:
        """Encode switch control value for multi-channel switches."""
        if channels == 1:
            return 0x02 if state else 0x01
            
        # For multi-channel switches, use 2 bits per channel
        # bit0-1: channel 1, bit2-3: channel 2, etc.
        value = 0
        channel_bits = 0x02 if state else 0x01  # 10=on, 01=off
        bit_position = (channel - 1) * 2
        value |= (channel_bits << bit_position)
        
        return value
    
    @staticmethod
    def decode_switch_value(value: int, channels: int) -> dict[int, bool]:
        """Decode switch state value for multi-channel switches."""
        states = {}
        
        if channels == 1:
            states[1] = value == 0x02
        else:
            # Decode 2 bits per channel
            for channel in range(1, channels + 1):
                bit_position = (channel - 1) * 2
                channel_bits = (value >> bit_position) & 0x03
                states[channel] = channel_bits == 0x02
                
        return states


def calculate_checksum(data: list[int]) -> int:
    """Calculate XOR checksum for command."""
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum