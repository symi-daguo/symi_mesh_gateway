"""Constants for the Symi Mesh Gateway integration."""
from __future__ import annotations

DOMAIN = "symi_mesh_gateway"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_TIMEOUT = "timeout"

# Default values
DEFAULT_PORT = 4196
DEFAULT_TIMEOUT = 10
DEFAULT_SCAN_INTERVAL = 30

# Protocol constants
PROTOCOL_HEAD = 0x53
DISCOVERY_COMMAND = [0x53, 0x12, 0x00, 0x41]  # 发现设备命令（4字节）

# Operation codes
OP_READ_DEVICE_LIST = 0x12
OP_DEVICE_LIST_RESPONSE = 0x92
OP_DEVICE_CONTROL = 0x30
OP_DEVICE_CONTROL_RESPONSE = 0xB0
OP_DEVICE_STATUS_EVENT = 0x80

# Device types mapping
DEVICE_TYPE_MAPPING = {
    1: "零火开关",
    2: "单火开关", 
    3: "智能插座",
    4: "智能灯",
    5: "智能窗帘",
    6: "情景面板",
    7: "门磁传感器",
    8: "人体感应",
    9: "插卡取电",
    10: "温控器",
    11: "温湿度传感器",
    20: "透传模块",
    24: "五色调光灯",
    74: "透传模块"
}

# Platform mapping
DEVICE_TYPE_TO_PLATFORM = {
    1: "switch",      # 零火开关
    2: "switch",      # 单火开关
    3: "switch",      # 智能插座
    4: "light",       # 智能灯
    5: "cover",       # 智能窗帘
    6: None,          # 情景面板 (不创建实体)
    7: "binary_sensor", # 门磁传感器
    8: "binary_sensor", # 人体感应
    9: "switch",      # 插卡取电
    10: "climate",    # 温控器
    11: "sensor",     # 温湿度传感器
    20: "switch",     # 透传模块 (作为开关)
    24: "light",      # 五色调光灯
    74: "switch"      # 透传模块 (作为开关)
}

# Message types
MSG_TYPE_ON_OFF = 0x02
MSG_TYPE_LIGHT_BRIGHTNESS = 0x03
MSG_TYPE_LIGHT_COLOR_TEMP = 0x04
MSG_TYPE_CURTAIN_STATUS = 0x05
MSG_TYPE_CURTAIN_POSITION = 0x06

# Control values
CONTROL_OFF = 0x01
CONTROL_ON = 0x02

# Event types
RESULT_CMD_OK = 0
RESULT_EVENT_NODE_STATUS = 6

# Discovery settings
DISCOVERY_TIMEOUT = 5
DISCOVERY_PORT = 4196
DISCOVERY_BROADCAST_ADDR = "255.255.255.255"

# Device data format (16 bytes)
DEVICE_DATA_SIZE = 16
DEVICE_MAC_OFFSET = 0      # 6 bytes
DEVICE_ADDR_OFFSET = 6     # 2 bytes (little endian)
DEVICE_TYPE_OFFSET = 8     # 1 byte
DEVICE_SUBTYPE_OFFSET = 9  # 1 byte (channels)
DEVICE_RSSI_OFFSET = 10    # 1 byte
DEVICE_VENDOR_OFFSET = 11  # 1 byte
DEVICE_EXT_OFFSET = 12     # 4 bytes

# Error messages
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_INVALID_HOST = "invalid_host"
ERROR_TIMEOUT = "timeout"
ERROR_UNKNOWN = "unknown"

# Entity names
ENTITY_NAME_FORMAT = "{device_name} {channel_name}"
SWITCH_CHANNEL_NAMES = ["开关", "开关1", "开关2", "开关3", "开关4", "开关5", "开关6"]