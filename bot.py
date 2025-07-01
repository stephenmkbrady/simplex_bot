#!/usr/bin/env python3
"""
SimpleX Chat Bot - Enhanced Python bot with configuration management,
daily logging, media downloads, and CLI interface
"""

import asyncio
import websockets
import json
import logging
import signal
import sys
import time
import argparse
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import logging.handlers

# Import our configuration manager
from config_manager import ConfigManager, parse_file_size


class DailyRotatingLogger:
    """Custom logger with daily rotation and separate message logging"""
    
    def __init__(self, app_logger_name: str, message_logger_name: str, config: Dict[str, Any]):
        self.config = config
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # Configure application logger
        self.app_logger = logging.getLogger(app_logger_name)
        self.app_logger.setLevel(getattr(logging, config.get('log_level', 'INFO')))
        
        # Configure message logger  
        self.message_logger = logging.getLogger(message_logger_name)
        self.message_logger.setLevel(logging.INFO)
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup daily rotating file handlers"""
        
        # Application log handler
        app_handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.log_dir / "bot.log",
            when='midnight',
            interval=1,
            backupCount=self.config.get('retention_days', 30),
            encoding='utf-8'
        )
        app_handler.suffix = "%Y-%m-%d"
        app_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        app_handler.setFormatter(app_formatter)
        self.app_logger.addHandler(app_handler)
        
        # Console handler for application logs
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(app_formatter)
        self.app_logger.addHandler(console_handler)
        
        # Message log handler (separate file)
        if self.config.get('message_log_separate', True):
            msg_handler = logging.handlers.TimedRotatingFileHandler(
                filename=self.log_dir / "messages.log",
                when='midnight',
                interval=1,
                backupCount=self.config.get('retention_days', 30),
                encoding='utf-8'
            )
            msg_handler.suffix = "%Y-%m-%d"
            msg_formatter = logging.Formatter(
                '%(asctime)s - %(message)s'
            )
            msg_handler.setFormatter(msg_formatter)
            self.message_logger.addHandler(msg_handler)


class SimplexChatBot:
    """Enhanced SimpleX Chat Bot with configuration management and extended features"""
    
    def __init__(self, config_path: str = "config.yml", cli_args: Optional[argparse.Namespace] = None):
        """
        Initialize the SimpleX Chat Bot
        
        Args:
            config_path: Path to configuration file
            cli_args: Command line arguments
        """
        # Load configuration
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.to_dict()
        self.cli_args = cli_args
        
        # Setup logging
        self._setup_logging()
        
        # Bot configuration from config file
        bot_config = self.config_manager.get_bot_config()
        self.websocket_url = bot_config.get('websocket_url', 'ws://localhost:3030')
        self.bot_name = bot_config.get('name', 'SimpleX Bot')
        self.auto_accept_contacts = bot_config.get('auto_accept_contacts', True)
        
        # Connection state
        self.websocket = None
        self.running = False
        self.correlation_counter = 0
        self.pending_requests: Dict[str, Any] = {}
        
        # Media configuration
        self.media_config = self.config_manager.get_media_config()
        self.media_enabled = self.media_config.get('download_enabled', True)
        self.media_path = Path(self.media_config.get('storage_path', './media'))
        self.media_path.mkdir(exist_ok=True)
        
        # Create media subdirectories
        for media_type in ['images', 'videos', 'documents', 'audio']:
            (self.media_path / media_type).mkdir(exist_ok=True)
        
        # Security configuration
        security_config = self.config_manager.get_security_config()
        self.max_message_length = int(security_config.get('max_message_length', 4096))
        self.rate_limit_messages = int(security_config.get('rate_limit_messages', 10))
        self.rate_limit_window = int(security_config.get('rate_limit_window', 60))
        
        # Command configuration
        self.commands = self._setup_commands()
        
        # Server information for status command
        self.server_info = self.config_manager.get_servers()
        
        self.app_logger.info(f"Initialized {self.bot_name}")
        self.app_logger.info(f"SMP Servers: {self.server_info.get('smp', [])}")
        self.app_logger.info(f"XFTP Servers: {self.server_info.get('xftp', [])}")
    
    def _setup_logging(self):
        """Setup daily rotating logging"""
        logging_config = self.config_manager.get_logging_config()
        
        if logging_config.get('daily_rotation', True):
            logger_setup = DailyRotatingLogger('bot.app', 'bot.messages', logging_config)
            self.app_logger = logger_setup.app_logger
            self.message_logger = logger_setup.message_logger
        else:
            # Fallback to basic logging
            logging.basicConfig(
                level=getattr(logging, logging_config.get('log_level', 'INFO')),
                format='%(asctime)s - %(levelname)s - %(message)s'
            )
            self.app_logger = logging.getLogger('bot.app')
            self.message_logger = logging.getLogger('bot.messages')
    
    def _setup_commands(self) -> Dict[str, callable]:
        """Setup available commands based on configuration"""
        commands_config = self.config_manager.get_commands_config()
        enabled_commands = commands_config.get('enabled', ['help', 'echo', 'status'])
        prefix = commands_config.get('prefix', '!')
        
        available_commands = {
            f"{prefix}help": self.handle_help,
            f"{prefix}echo": self.handle_echo,
            f"{prefix}status": self.handle_status,
        }
        
        # Filter to only enabled commands
        enabled_commands_dict = {}
        for cmd_name in enabled_commands:
            full_cmd = f"{prefix}{cmd_name}"
            if full_cmd in available_commands:
                enabled_commands_dict[full_cmd] = available_commands[full_cmd]
        
        return enabled_commands_dict
    
    def generate_correlation_id(self) -> str:
        """Generate a unique correlation ID for requests"""
        self.correlation_counter += 1
        return f"bot_req_{int(time.time())}_{self.correlation_counter}"
    
    async def connect(self, max_retries: int = 30, retry_delay: int = 2) -> bool:
        """Connect to the SimpleX Chat CLI WebSocket server with retries"""
        for attempt in range(max_retries):
            try:
                self.app_logger.info(f"Connecting to SimpleX Chat CLI at {self.websocket_url} (attempt {attempt + 1}/{max_retries})")
                self.websocket = await websockets.connect(self.websocket_url)
                self.app_logger.info("Successfully connected to SimpleX Chat CLI")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    self.app_logger.warning(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay}s: {e}")
                    await asyncio.sleep(retry_delay)
                else:
                    self.app_logger.error(f"Failed to connect to SimpleX Chat CLI after {max_retries} attempts: {e}")
                    return False
        return False
    
    async def disconnect(self):
        """Disconnect from the WebSocket server"""
        if self.websocket:
            await self.websocket.close()
            self.app_logger.info("Disconnected from SimpleX Chat CLI")
    
    async def send_command(self, command: str, wait_for_response: bool = False) -> Optional[Dict]:
        """
        Send a command to SimpleX Chat CLI
        
        Args:
            command: The command to send
            wait_for_response: Whether to wait for and return the response
            
        Returns:
            Response dict if wait_for_response is True, None otherwise
        """
        if not self.websocket:
            self.app_logger.error("Not connected to SimpleX Chat CLI")
            return None
        
        corr_id = self.generate_correlation_id()
        
        message = {
            "corrId": corr_id,
            "cmd": command
        }
        
        try:
            await self.websocket.send(json.dumps(message))
            self.app_logger.debug(f"Sent command: {command} (corr_id: {corr_id})")
            
            if wait_for_response:
                # Store the request for correlation
                self.pending_requests[corr_id] = {"command": command, "timestamp": time.time()}
                
                # Wait for response (with timeout)
                timeout = 30  # 30 seconds timeout
                start_time = time.time()
                
                while corr_id in self.pending_requests:
                    if time.time() - start_time > timeout:
                        self.app_logger.warning(f"Timeout waiting for response to command: {command}")
                        del self.pending_requests[corr_id]
                        return None
                    
                    await asyncio.sleep(0.1)
                
                # Response should be stored with "_response" suffix
                return self.pending_requests.get(f"{corr_id}_response")
            
        except Exception as e:
            self.app_logger.error(f"Failed to send command: {e}")
            return None
    
    async def send_message(self, contact_name: str, message: str):
        """Send a message to a specific contact"""
        if len(message) > self.max_message_length:
            self.app_logger.warning(f"Message too long ({len(message)} chars), truncating")
            message = message[:self.max_message_length] + "..."
        
        command = f"@{contact_name} {message}"
        await self.send_command(command)
        self.app_logger.info(f"Sent message to {contact_name}: {message[:100]}...")
    
    async def accept_contact_request(self, request_number: int):
        """Accept an incoming contact request"""
        command = f"/ac {request_number}"
        await self.send_command(command)
        self.app_logger.info(f"Accepted contact request #{request_number}")
    
    async def connect_to_address(self, address: str):
        """Connect to a SimpleX address or invitation link"""
        command = f"/c {address}"
        response = await self.send_command(command, wait_for_response=True)
        if response:
            self.app_logger.info(f"Connected to address: {address}")
        return response
    
    async def handle_help(self, contact_name: str, args: list = None) -> str:
        """Handle the !help command"""
        commands_list = ", ".join(self.commands.keys())
        server_count = len(self.server_info.get('smp', []))
        
        help_text = f"""
🤖 {self.bot_name} Commands:

{commands_list}

📡 Connected to {server_count} SMP server(s)
📁 Media downloads: {"enabled" if self.media_enabled else "disabled"}
🕒 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Use !status for detailed information.
        """.strip()
        
        return help_text
    
    async def handle_echo(self, contact_name: str, args: list = None) -> str:
        """Handle the !echo command"""
        if not args:
            return "Usage: !echo <text_to_echo>"
        
        echo_text = " ".join(args)
        return f"Echo: {echo_text}"
    
    async def handle_status(self, contact_name: str, args: list = None) -> str:
        """Handle the !status command"""
        smp_servers = self.server_info.get('smp', [])
        xftp_servers = self.server_info.get('xftp', [])
        
        status_text = f"""
📊 {self.bot_name} Status Report

🔗 Connection:
  • WebSocket: {self.websocket_url}
  • Status: {"Connected" if self.websocket else "Disconnected"}

📡 Servers:
  • SMP: {len(smp_servers)} configured
    {chr(10).join([f"    - {server}" for server in smp_servers[:3]])}
  • XFTP: {len(xftp_servers)} configured  
    {chr(10).join([f"    - {server}" for server in xftp_servers[:3]])}

📁 Media:
  • Downloads: {"Enabled" if self.media_enabled else "Disabled"}
  • Storage: {self.media_path}
  • Max size: {self.media_config.get('max_file_size', 'N/A')}

⚙️ Configuration:
  • Auto-accept contacts: {"Yes" if self.auto_accept_contacts else "No"}
  • Commands enabled: {len(self.commands)}
  • Log retention: {self.config_manager.get('logging.retention_days', 30)} days

🕒 Runtime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return status_text
    
    async def process_message(self, message_data: Dict):
        """Process an incoming message and handle commands"""
        try:
            # Extract message information
            chat_item = message_data.get("chatItem", {})
            chat_info = message_data.get("chatInfo", {})
            
            # Get contact name - it's nested in the contact object
            contact_info = chat_info.get("contact", {})
            contact_name = contact_info.get("localDisplayName", "Unknown")
            
            # Debug logging to see the structure
            self.app_logger.debug(f"Chat info keys: {list(chat_info.keys())}")
            self.app_logger.debug(f"Contact info keys: {list(contact_info.keys())}")
            self.app_logger.debug(f"Extracted contact name: {contact_name}")
            
            # Get message content
            content = chat_item.get("content", {})
            if content.get("msgContent", {}).get("type") == "text":
                text = content.get("msgContent", {}).get("text", "")
                
                # Log the message
                self.message_logger.info(f"FROM {contact_name}: {text}")
                self.app_logger.info(f"Received message from {contact_name}: {text[:100]}...")
                
                # Check if it's a command
                if any(text.startswith(cmd) for cmd in self.commands.keys()):
                    parts = text.split()
                    command = parts[0].lower()
                    args = parts[1:] if len(parts) > 1 else []
                    
                    if command in self.commands:
                        try:
                            response = await self.commands[command](contact_name, args)
                            if response:
                                await self.send_message(contact_name, response)
                                self.message_logger.info(f"TO {contact_name}: {response[:100]}...")
                        except Exception as e:
                            self.app_logger.error(f"Error handling command {command}: {e}")
                            error_msg = f"Error processing command: {command}"
                            await self.send_message(contact_name, error_msg)
                    else:
                        available_commands = ", ".join(self.commands.keys())
                        response = f"Unknown command: {command}. Available: {available_commands}"
                        await self.send_message(contact_name, response)
            
            # Handle file/media messages
            elif content.get("msgContent", {}).get("type") == "file":
                await self.handle_file_message(contact_name, content)
                        
        except Exception as e:
            self.app_logger.error(f"Error processing message: {e}")
    
    async def handle_file_message(self, contact_name: str, content: Dict):
        """Handle incoming file/media messages"""
        if not self.media_enabled:
            self.app_logger.debug("Media downloads disabled, skipping file")
            return
        
        try:
            file_info = content.get("msgContent", {})
            file_name = file_info.get("fileName", "unknown_file")
            file_size = file_info.get("fileSize", 0)
            
            # Check file size limit
            max_size = parse_file_size(self.media_config.get('max_file_size', '100MB'))
            if file_size > max_size:
                self.app_logger.warning(f"File too large: {file_name} ({file_size} bytes)")
                await self.send_message(contact_name, f"File {file_name} is too large to download")
                return
            
            # Determine file type and storage location
            file_type = self._get_file_type(file_name)
            if file_type not in self.media_config.get('allowed_types', ['image', 'video', 'document', 'audio']):
                self.app_logger.warning(f"File type not allowed: {file_name}")
                return
            
            # Log the file message
            self.message_logger.info(f"FILE FROM {contact_name}: {file_name} ({file_size} bytes)")
            self.app_logger.info(f"Received file from {contact_name}: {file_name}")
            
            # Here we would implement actual file download logic
            # This would require XFTP integration which is complex
            # For now, we just log that we received a file
            
        except Exception as e:
            self.app_logger.error(f"Error handling file message: {e}")
    
    def _get_file_type(self, filename: str) -> str:
        """Determine file type from filename extension"""
        ext = Path(filename).suffix.lower()
        
        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        video_exts = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm'}
        audio_exts = {'.mp3', '.wav', '.ogg', '.m4a', '.flac'}
        
        if ext in image_exts:
            return 'image'
        elif ext in video_exts:
            return 'video'
        elif ext in audio_exts:
            return 'audio'
        else:
            return 'document'
    
    async def handle_contact_request(self, request_data: Dict):
        """Handle incoming contact requests"""
        try:
            contact_request = request_data.get("contactRequest", {})
            local_display_name = contact_request.get("localDisplayName", "Unknown")
            
            self.app_logger.info(f"Received contact request from: {local_display_name}")
            self.message_logger.info(f"CONTACT_REQUEST FROM: {local_display_name}")
            
            if self.auto_accept_contacts:
                # Auto-accept contact requests
                request_id = contact_request.get("contactRequestId")
                if request_id:
                    await self.accept_contact_request(request_id)
                    self.app_logger.info(f"Auto-accepted contact request from {local_display_name}")
            else:
                self.app_logger.info(f"Contact request from {local_display_name} - manual acceptance required")
            
        except Exception as e:
            self.app_logger.error(f"Error handling contact request: {e}")
    
    async def handle_response(self, response_data: Dict):
        """Handle responses from SimpleX Chat CLI"""
        try:
            corr_id = response_data.get("corrId")
            resp = response_data.get("resp", {})
            
            # Handle SimpleX Chat CLI's Either-type responses (Right wrapper for success)
            if "Right" in resp:
                actual_resp = resp["Right"]
                resp_type = actual_resp.get("type", "")
                self.app_logger.debug(f"Processing Right-wrapped response type: {resp_type}")
            elif "Left" in resp:
                # Handle error responses (Left wrapper)
                error_resp = resp["Left"]
                self.app_logger.error(f"Received error response: {error_resp}")
                return
            else:
                # Fallback for direct responses (shouldn't happen with current SimpleX CLI)
                actual_resp = resp
                resp_type = resp.get("type", "")
                self.app_logger.debug(f"Processing direct response type: {resp_type}")
            
            if corr_id and corr_id in self.pending_requests:
                # Store the response
                self.pending_requests[f"{corr_id}_response"] = response_data
                # Remove the pending request
                del self.pending_requests[corr_id]
            
            # Handle different response types
            if resp_type == "chatCmdError":
                error_info = actual_resp.get("chatError", {})
                self.app_logger.error(f"Chat command error: {error_info}")
            elif resp_type == "contactConnected":
                contact_info = actual_resp.get("contact", {})
                contact_name = contact_info.get("displayName", "Unknown")
                self.app_logger.info(f"Contact connected: {contact_name}")
                self.message_logger.info(f"CONTACT_CONNECTED: {contact_name}")
            elif resp_type == "newChatItem":
                self.app_logger.debug(f"Processing single newChatItem")
                await self.process_message(actual_resp)
            elif resp_type == "newChatItems":
                self.app_logger.debug(f"Processing newChatItems (multiple items)")
                # Handle newChatItems which contains an array of chat items
                chat_items = actual_resp.get("chatItems", [])
                for chat_item_data in chat_items:
                    # Each item in chatItems has the same structure as newChatItem
                    await self.process_message(chat_item_data)
            elif resp_type == "contactRequest":
                await self.handle_contact_request(actual_resp)
            else:
                self.app_logger.debug(f"Received response type: {resp_type}")
                
        except Exception as e:
            self.app_logger.error(f"Error handling response: {e}")
    
    async def listen_for_messages(self):
        """Listen for incoming messages from SimpleX Chat CLI"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    self.app_logger.info(f"RAW WebSocket message received: {message}")
                    self.app_logger.info(f"Parsed WebSocket data: {json.dumps(data, indent=2)}")
                    
                    await self.handle_response(data)
                    
                except json.JSONDecodeError as e:
                    self.app_logger.error(f"Failed to parse JSON message: {e}")
                except Exception as e:
                    self.app_logger.error(f"Error processing message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            self.app_logger.info("WebSocket connection closed")
        except Exception as e:
            self.app_logger.error(f"Error in message listener: {e}")
    
    async def process_cli_connections(self):
        """Process any connections specified via CLI arguments"""
        if not self.cli_args:
            return
        
        if hasattr(self.cli_args, 'connect') and self.cli_args.connect:
            self.app_logger.info(f"Connecting to address from CLI: {self.cli_args.connect}")
            await self.connect_to_address(self.cli_args.connect)
        
        if hasattr(self.cli_args, 'group') and self.cli_args.group:
            self.app_logger.info(f"Joining group from CLI: {self.cli_args.group}")
            await self.connect_to_address(self.cli_args.group)
    
    async def start(self):
        """Start the bot with automatic reconnection"""
        self.running = True
        self.app_logger.info(f"Starting {self.bot_name}")
        
        while self.running:
            try:
                # Connect to SimpleX Chat CLI
                if not await self.connect():
                    self.app_logger.error("Failed to connect, waiting 30s before retry...")
                    await asyncio.sleep(30)
                    continue
                
                # Process CLI connections if any (only on first connection)
                if hasattr(self, '_first_connection'):
                    await self.process_cli_connections()
                    delattr(self, '_first_connection')
                else:
                    self._first_connection = True
                    await self.process_cli_connections()
                
                # Start listening for messages
                await self.listen_for_messages()
                
            except KeyboardInterrupt:
                self.app_logger.info("Bot stopped by user")
                break
            except websockets.exceptions.ConnectionClosed:
                self.app_logger.warning("WebSocket connection lost. Attempting to reconnect in 10s...")
                await asyncio.sleep(10)
                continue
            except Exception as e:
                self.app_logger.error(f"Bot error: {e}. Reconnecting in 10s...")
                await asyncio.sleep(10)
                continue
            finally:
                await self.disconnect()
        
        self.running = False
        return True
    
    async def stop(self):
        """Stop the bot"""
        self.app_logger.info("Stopping bot...")
        self.running = False
        if self.websocket:
            await self.disconnect()


def setup_argument_parser() -> argparse.ArgumentParser:
    """Setup command line argument parser"""
    parser = argparse.ArgumentParser(
        description="SimpleX Chat Bot with configuration management"
    )
    
    parser.add_argument(
        '--config', '-c',
        default='config.yml',
        help='Path to configuration file (default: config.yml)'
    )
    
    parser.add_argument(
        '--connect',
        help='SimpleX address or invitation link to connect to'
    )
    
    parser.add_argument(
        '--group', '-g',
        help='Group invitation link to join'
    )
    
    parser.add_argument(
        '--version', '-v',
        action='version',
        version='SimpleX Bot 2.0'
    )
    
    return parser


def signal_handler(bot):
    """Create signal handler for graceful shutdown"""
    def handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        asyncio.create_task(bot.stop())
    return handler


async def main():
    """Main function to run the bot"""
    # Parse command line arguments
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # Create bot instance
    try:
        bot = SimplexChatBot(config_path=args.config, cli_args=args)
    except Exception as e:
        print(f"Error initializing bot: {e}")
        sys.exit(1)
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler(bot))
    signal.signal(signal.SIGTERM, signal_handler(bot))
    
    print(f"""
    ╔══════════════════════════════════════╗
    ║          SimpleX Chat Bot v2.0       ║
    ║                                      ║
    ║  Configuration: {args.config:<19} ║
    ║  SMP Servers: {len(bot.server_info.get('smp', [])):<2}                 ║
    ║  Media Downloads: {str(bot.media_enabled):<14} ║
    ║                                      ║
    ║  Available commands:                 ║
    ║  {', '.join(bot.commands.keys()):<35} ║
    ║                                      ║
    ║  Press Ctrl+C to stop                ║
    ╚══════════════════════════════════════╝
    """)
    
    # Start the bot
    await bot.start()


if __name__ == "__main__":
    # Check if required dependencies are available
    try:
        import websockets
        import yaml
        from dotenv import load_dotenv
    except ImportError as e:
        print(f"Error: Missing required dependency: {e}")
        print("Install dependencies with: pip install -r requirements.txt")
        sys.exit(1)
    
    # Run the bot
    asyncio.run(main())