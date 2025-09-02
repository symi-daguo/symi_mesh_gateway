"""TCP communication module for Symi Mesh Gateway."""
from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any, Callable

from .const import DEFAULT_PORT, DEFAULT_TIMEOUT, PROTOCOL_HEAD

_LOGGER = logging.getLogger(__name__)


class SymiTCPConnection:
    """TCP connection handler for Symi Mesh Gateway."""

    def __init__(self, host: str, port: int = DEFAULT_PORT, timeout: int = DEFAULT_TIMEOUT):
        """Initialize TCP connection."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._message_handlers: list[Callable[[bytes], None]] = []
        self._listen_task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        """Return connection status."""
        return self._connected and self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> bool:
        """Establish TCP connection."""
        try:
            _LOGGER.debug("Connecting to %s:%s", self.host, self.port)
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout
            )
            self._connected = True
            _LOGGER.info("Connected to Symi Gateway at %s:%s", self.host, self.port)
            
            # Start listening for incoming messages
            self._listen_task = asyncio.create_task(self._listen_for_messages())
            return True
            
        except (OSError, asyncio.TimeoutError) as err:
            _LOGGER.error("Failed to connect to %s:%s: %s", self.host, self.port, err)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close TCP connection."""
        self._connected = False
        
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
            
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception as err:
                _LOGGER.debug("Error closing writer: %s", err)
            self._writer = None
            
        self._reader = None
        _LOGGER.info("Disconnected from Symi Gateway")

    async def send_command(self, command: list[int]) -> bytes | None:
        """Send command and wait for response."""
        if not self.connected:
            _LOGGER.error("Not connected to gateway")
            return None

        if not self._writer:
            _LOGGER.error("No writer available")
            return None

        try:
            # Calculate checksum (XOR of all bytes)
            checksum = 0
            for byte in command:
                checksum ^= byte
            
            # Add checksum to command
            full_command = command + [checksum]
            command_bytes = bytes(full_command)
            
            _LOGGER.debug("Sending command: %s", " ".join(f"{b:02X}" for b in command_bytes))
            
            self._writer.write(command_bytes)
            await self._writer.drain()
            
            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(
                    self._read_response(),
                    timeout=self.timeout
                )
                return response
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for response")
                return None
                
        except Exception as err:
            _LOGGER.error("Error sending command: %s", err)
            return None

    async def _read_response(self) -> bytes:
        """Read response from gateway."""
        if not self._reader:
            raise RuntimeError("No reader available")
            
        # Read header (head + opcode + status + length)
        header = await self._reader.read(4)
        if len(header) < 4:
            raise RuntimeError("Incomplete header received")
            
        head, opcode, status, length = header
        
        if head != PROTOCOL_HEAD:
            raise RuntimeError(f"Invalid protocol header: {head:02X}")
            
        # Read data and checksum
        remaining_bytes = length + 1  # data + checksum
        if remaining_bytes > 0:
            data_and_checksum = await self._reader.read(remaining_bytes)
            if len(data_and_checksum) < remaining_bytes:
                raise RuntimeError("Incomplete data received")
        else:
            data_and_checksum = b""
            
        full_response = header + data_and_checksum
        _LOGGER.debug("Received response: %s", " ".join(f"{b:02X}" for b in full_response))
        
        return full_response

    async def _listen_for_messages(self) -> None:
        """Listen for incoming messages."""
        while self._connected and self._reader:
            try:
                # Try to read incoming data
                data = await asyncio.wait_for(self._reader.read(1024), timeout=1.0)
                if not data:
                    break
                    
                # Process received data
                await self._process_incoming_data(data)
                
            except asyncio.TimeoutError:
                # Timeout is normal, continue listening
                continue
            except Exception as err:
                _LOGGER.error("Error listening for messages: %s", err)
                break

    async def _process_incoming_data(self, data: bytes) -> None:
        """Process incoming data and call handlers."""
        if len(data) < 4:
            return
            
        # Check if this is a valid protocol message
        if data[0] != PROTOCOL_HEAD:
            return
            
        # Call all registered message handlers
        for handler in self._message_handlers:
            try:
                handler(data)
            except Exception as err:
                _LOGGER.error("Error in message handler: %s", err)

    def add_message_handler(self, handler: Callable[[bytes], None]) -> None:
        """Add a message handler."""
        self._message_handlers.append(handler)

    def remove_message_handler(self, handler: Callable[[bytes], None]) -> None:
        """Remove a message handler."""
        if handler in self._message_handlers:
            self._message_handlers.remove(handler)


async def discover_gateways(timeout: int = 5) -> list[str]:
    """Discover Symi gateways on the network by scanning port 4196."""
    gateways = []
    
    # Get local network range
    try:
        # Get local IP to determine network range
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        # Extract network part (assuming /24)
        network_parts = local_ip.split('.')
        network_base = '.'.join(network_parts[:3])
        
        _LOGGER.info("Scanning network %s.0/24 for Symi gateways", network_base)
        
        # Scan all IPs in the network
        tasks = []
        for i in range(1, 255):
            ip = f"{network_base}.{i}"
            tasks.append(_check_gateway(ip, DEFAULT_PORT, timeout))
            
        # Wait for all scans to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect successful discoveries
        for i, result in enumerate(results):
            if isinstance(result, bool) and result:
                ip = f"{network_base}.{i + 1}"
                gateways.append(ip)
                _LOGGER.info("Found Symi gateway at %s", ip)
                
    except Exception as err:
        _LOGGER.error("Error during gateway discovery: %s", err)
        
    return gateways


async def _check_gateway(host: str, port: int, timeout: int) -> bool:
    """Check if a gateway exists at the given host:port."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout / 50  # Quick timeout for each host
        )
        
        # Send discovery command
        discovery_cmd = [0x53, 0x12, 0x00, 0x41]
        checksum = 0
        for byte in discovery_cmd:
            checksum ^= byte
        full_cmd = discovery_cmd + [checksum]
        
        writer.write(bytes(full_cmd))
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