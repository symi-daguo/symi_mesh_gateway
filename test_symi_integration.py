"""Test script for Symi Mesh Gateway integration."""
import asyncio
import logging
import sys
from typing import Any

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Add custom_components to path
sys.path.insert(0, '.')

from custom_components.symi_mesh_gateway.tcp_comm import SymiTCPConnection, discover_gateways
from custom_components.symi_mesh_gateway.device_manager import SymiDeviceManager
from custom_components.symi_mesh_gateway.protocol import SymiProtocol


async def test_discovery():
    """Test gateway discovery."""
    logger.info("Testing gateway discovery...")
    
    try:
        gateways = await discover_gateways(timeout=10)
        logger.info(f"Found {len(gateways)} gateways: {gateways}")
        return gateways
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        return []


async def test_connection(host: str, port: int = 4196):
    """Test connection to gateway."""
    logger.info(f"Testing connection to {host}:{port}...")
    
    connection = SymiTCPConnection(host, port, timeout=10)
    
    try:
        # Test connection
        if await connection.connect():
            logger.info("Connection successful!")
            
            # Test device discovery
            device_manager = SymiDeviceManager(connection)
            devices = await device_manager.discover_devices()
            
            logger.info(f"Discovered {len(devices)} devices:")
            for device in devices:
                logger.info(f"  - {device.mac_address}: {device.device_name} "
                          f"(Type: {device.device_type}, Channels: {device.channels}, "
                          f"Platform: {device.platform})")
            
            # Test device control if we have devices
            if devices:
                test_device = devices[0]
                logger.info(f"Testing control with device: {test_device.mac_address}")
                
                if test_device.platform == "switch":
                    # Test switch control
                    logger.info("Testing switch ON...")
                    await device_manager.control_switch(test_device.unique_id, 1, True)
                    await asyncio.sleep(2)
                    
                    logger.info("Testing switch OFF...")
                    await device_manager.control_switch(test_device.unique_id, 1, False)
                    
                elif test_device.platform == "light":
                    # Test light control
                    if test_device.supports_brightness:
                        logger.info("Testing light brightness...")
                        await device_manager.control_light_brightness(test_device.unique_id, 50)
                        await asyncio.sleep(2)
                        
                        await device_manager.control_light_brightness(test_device.unique_id, 0)
            
            # Close connection
            await connection.disconnect()
            logger.info("Connection closed successfully")
            return True
            
        else:
            logger.error("Failed to connect")
            return False
            
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        await connection.disconnect()
        return False


async def test_protocol():
    """Test protocol parsing."""
    logger.info("Testing protocol parsing...")
    
    # Test device list command
    cmd = SymiProtocol.create_device_list_command()
    logger.info(f"Device list command: {' '.join(f'{b:02X}' for b in cmd)}")
    
    # Test control command
    ctrl_cmd = SymiProtocol.create_control_command(0x0001, 0x02, 0x02)
    logger.info(f"Control command: {' '.join(f'{b:02X}' for b in ctrl_cmd)}")
    
    # Test switch value encoding/decoding
    for channels in [1, 2, 4, 6]:
        for channel in range(1, channels + 1):
            for state in [True, False]:
                encoded = SymiProtocol.encode_switch_value(channels, channel, state)
                decoded = SymiProtocol.decode_switch_value(encoded, channels)
                logger.info(f"Channels={channels}, Ch={channel}, State={state}: "
                          f"Encoded=0x{encoded:02X}, Decoded={decoded}")


async def main():
    """Main test function."""
    logger.info("Starting Symi Mesh Gateway integration tests...")
    
    # Test protocol
    await test_protocol()
    
    # Test discovery
    gateways = await test_discovery()
    
    # Test connection if we found gateways
    if gateways:
        logger.info(f"Testing connection to first gateway: {gateways[0]}")
        await test_connection(gateways[0])
    else:
        logger.info("No gateways found, testing with manual IP (if available)")
        # You can manually test with a known IP here
        # await test_connection("192.168.1.100")
    
    logger.info("Tests completed!")


if __name__ == "__main__":
    asyncio.run(main())