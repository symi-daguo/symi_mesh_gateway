"""Independent protocol test script for Symi Mesh Gateway."""
import asyncio
import logging
import socket
import struct
from typing import Any

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Protocol constants
PROTOCOL_HEAD = 0x53
OP_READ_DEVICE_LIST = 0x12
OP_DEVICE_LIST_RESPONSE = 0x92
OP_DEVICE_CONTROL = 0x30
OP_DEVICE_CONTROL_RESPONSE = 0xB0
OP_DEVICE_STATUS_EVENT = 0x80

DEFAULT_PORT = 4196
DEVICE_DATA_SIZE = 16

# Device type mapping
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


def calculate_checksum(data: list[int]) -> int:
    """Calculate XOR checksum."""
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum


def create_device_list_command() -> bytes:
    """Create device list query command."""
    command = [PROTOCOL_HEAD, OP_READ_DEVICE_LIST, 0x00, 0x41]
    checksum = calculate_checksum(command)
    return bytes(command + [checksum])


def create_control_command(network_address: int, msg_type: int, value: int) -> bytes:
    """Create device control command."""
    addr_low = network_address & 0xFF
    addr_high = (network_address >> 8) & 0xFF
    
    command = [
        PROTOCOL_HEAD,
        OP_DEVICE_CONTROL,
        0x04,  # data length
        addr_low,
        addr_high,
        msg_type,
        value
    ]
    
    checksum = calculate_checksum(command)
    return bytes(command + [checksum])


def parse_device_data(data: bytes) -> dict[str, Any]:
    """Parse single device from 16-byte data."""
    if len(data) != DEVICE_DATA_SIZE:
        return {}
        
    # Extract MAC address (6 bytes)
    mac_bytes = data[0:6]
    mac_address = ":".join(f"{b:02x}" for b in mac_bytes)
    
    # Extract network address (2 bytes, little endian)
    network_address = struct.unpack("<H", data[6:8])[0]
    
    # Extract device type and subtype
    device_type = data[8]
    device_subtype = data[9]
    
    # Extract RSSI (signed)
    rssi = struct.unpack("b", data[10:11])[0]
    
    # Extract vendor ID
    vendor_id = data[11]
    
    return {
        "mac_address": mac_address,
        "network_address": network_address,
        "device_type": device_type,
        "device_subtype": device_subtype,
        "rssi": rssi,
        "vendor_id": vendor_id,
        "device_name": DEVICE_TYPE_MAPPING.get(device_type, f"未知设备({device_type})")
    }


async def discover_gateways_simple(timeout: int = 5) -> list[str]:
    """Simple gateway discovery."""
    gateways = []
    
    try:
        # Get local IP to determine network range
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        # Extract network part (assuming /24)
        network_parts = local_ip.split('.')
        network_base = '.'.join(network_parts[:3])
        
        logger.info(f"Scanning network {network_base}.0/24 for Symi gateways")
        
        # Scan common IPs (not all 254 to save time)
        test_ips = [1, 2, 100, 101, 102, 103, 200, 201, 254]
        tasks = []
        
        for i in test_ips:
            ip = f"{network_base}.{i}"
            tasks.append(check_gateway_simple(ip, DEFAULT_PORT, timeout))
            
        # Wait for all scans to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect successful discoveries
        for i, result in enumerate(results):
            if isinstance(result, bool) and result:
                ip = f"{network_base}.{test_ips[i]}"
                gateways.append(ip)
                logger.info(f"Found Symi gateway at {ip}")
                
    except Exception as err:
        logger.error(f"Error during gateway discovery: {err}")
        
    return gateways


async def check_gateway_simple(host: str, port: int, timeout: int) -> bool:
    """Check if a gateway exists at the given host:port."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout / 10  # Quick timeout for each host
        )
        
        # Send discovery command
        discovery_cmd = create_device_list_command()
        
        writer.write(discovery_cmd)
        await writer.drain()
        
        # Try to read response
        try:
            response = await asyncio.wait_for(reader.read(1024), timeout=1.0)
            writer.close()
            await writer.wait_closed()
            
            # Check if response looks like a valid Symi response
            return len(response) > 4 and response[0] == PROTOCOL_HEAD
            
        except asyncio.TimeoutError:
            writer.close()
            await writer.wait_closed()
            return False
            
    except Exception:
        return False


async def test_gateway_connection(host: str, port: int = DEFAULT_PORT):
    """Test connection and device discovery."""
    logger.info(f"Testing connection to {host}:{port}")
    
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=10
        )
        
        logger.info("Connection established!")
        
        # Send device list command
        command = create_device_list_command()
        logger.info(f"Sending command: {' '.join(f'{b:02X}' for b in command)}")
        
        writer.write(command)
        await writer.drain()
        
        # Read response
        response = await asyncio.wait_for(reader.read(1024), timeout=10)
        logger.info(f"Received response: {' '.join(f'{b:02X}' for b in response)}")
        
        if len(response) >= 4:
            head, opcode, status, length = response[:4]
            logger.info(f"Response: head=0x{head:02X}, opcode=0x{opcode:02X}, status=0x{status:02X}, length={length}")
            
            if head == PROTOCOL_HEAD and opcode == OP_DEVICE_LIST_RESPONSE and status == 0:
                data = response[4:4+length]
                device_count = len(data) // DEVICE_DATA_SIZE
                logger.info(f"Found {device_count} devices")
                
                for i in range(device_count):
                    offset = i * DEVICE_DATA_SIZE
                    device_data = data[offset:offset + DEVICE_DATA_SIZE]
                    device = parse_device_data(device_data)
                    
                    if device:
                        logger.info(f"Device {i+1}: {device['mac_address']} - {device['device_name']} "
                                  f"(Type: {device['device_type']}, Addr: 0x{device['network_address']:04X})")
                        
                        # Test control command for first device
                        if i == 0 and device['device_type'] in [1, 2, 3]:  # Switch types
                            logger.info("Testing switch control...")
                            
                            # Turn on
                            control_cmd = create_control_command(device['network_address'], 0x02, 0x02)
                            logger.info(f"Sending ON command: {' '.join(f'{b:02X}' for b in control_cmd)}")
                            writer.write(control_cmd)
                            await writer.drain()
                            
                            ctrl_response = await asyncio.wait_for(reader.read(1024), timeout=5)
                            logger.info(f"Control response: {' '.join(f'{b:02X}' for b in ctrl_response)}")
                            
                            await asyncio.sleep(2)
                            
                            # Turn off
                            control_cmd = create_control_command(device['network_address'], 0x02, 0x01)
                            logger.info(f"Sending OFF command: {' '.join(f'{b:02X}' for b in control_cmd)}")
                            writer.write(control_cmd)
                            await writer.drain()
                            
                            ctrl_response = await asyncio.wait_for(reader.read(1024), timeout=5)
                            logger.info(f"Control response: {' '.join(f'{b:02X}' for b in ctrl_response)}")
            
        # Close connection
        writer.close()
        await writer.wait_closed()
        logger.info("Connection closed")
        
        return True
        
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False


async def test_protocol():
    """Test protocol functions."""
    logger.info("Testing protocol functions...")
    
    # Test device list command
    cmd = create_device_list_command()
    logger.info(f"Device list command: {' '.join(f'{b:02X}' for b in cmd)}")
    
    # Test control commands
    test_commands = [
        (0x0001, 0x02, 0x02),  # Turn on switch
        (0x0001, 0x02, 0x01),  # Turn off switch
        (0x0002, 0x03, 50),    # Set brightness to 50%
        (0x0003, 0x04, 75),    # Set color temp to 75%
    ]
    
    for addr, msg_type, value in test_commands:
        cmd = create_control_command(addr, msg_type, value)
        logger.info(f"Control command (addr=0x{addr:04X}, type=0x{msg_type:02X}, val={value}): "
                   f"{' '.join(f'{b:02X}' for b in cmd)}")


async def main():
    """Main test function."""
    logger.info("Starting Symi protocol tests...")
    
    # Test protocol functions
    await test_protocol()
    
    # Test gateway discovery
    logger.info("Discovering gateways...")
    gateways = await discover_gateways_simple(timeout=5)
    
    if gateways:
        logger.info(f"Found gateways: {gateways}")
        # Test connection to first gateway
        await test_gateway_connection(gateways[0])
    else:
        logger.info("No gateways found. You can manually test with a known IP:")
        logger.info("Example: await test_gateway_connection('192.168.1.100')")
    
    logger.info("Tests completed!")


if __name__ == "__main__":
    asyncio.run(main())