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
import base64
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import logging.handlers

# Import our configuration manager
from config_manager import ConfigManager, parse_file_size
from xftp_client import XFTPClient, XFTPError, XFTPDownloadError

# Constants
DEFAULT_MAX_MESSAGE_LENGTH = 4096
DEFAULT_RATE_LIMIT_MESSAGES = 10
DEFAULT_RATE_LIMIT_WINDOW = 60  # seconds
DEFAULT_RETENTION_DAYS = 30
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 30
DEFAULT_RETRY_DELAY = 2
MESSAGE_PREVIEW_LENGTH = 100
SERVER_LIST_PREVIEW_COUNT = 3
BYTES_PER_MB = 1024 * 1024
BYTES_PER_GB = 1024 * 1024 * 1024
BYTES_PER_KB = 1024
HASH_CHUNK_SIZE = 4096
FILE_READ_CHUNK_SIZE = 1024


# Exception hierarchy
class SimplexBotError(Exception):
    """Base exception for SimpleX Bot operations"""
    pass


class ConfigurationError(SimplexBotError):
    """Configuration-related errors"""
    pass


class WebSocketError(SimplexBotError):
    """WebSocket connection and communication errors"""
    pass


class FileDownloadError(SimplexBotError):
    """File download operation errors"""
    pass


class MediaProcessingError(SimplexBotError):
    """Media processing and validation errors"""
    pass


class XFTPIntegrationError(SimplexBotError):
    """XFTP client integration errors"""
    pass


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
        try:
            self.config_manager = ConfigManager(config_path)
            self.config = self.config_manager.to_dict()
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration from {config_path}: {e}")
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
        
        # Log media configuration
        self.app_logger.info(f"Media downloads enabled: {self.media_enabled}")
        self.app_logger.debug(f"Media storage path: {self.media_path}")
        
        # Create media subdirectories
        for media_type in ['images', 'videos', 'documents', 'audio']:
            (self.media_path / media_type).mkdir(exist_ok=True)
        
        # Security configuration
        security_config = self.config_manager.get_security_config()
        self.max_message_length = int(security_config.get('max_message_length', DEFAULT_MAX_MESSAGE_LENGTH))
        self.rate_limit_messages = int(security_config.get('rate_limit_messages', DEFAULT_RATE_LIMIT_MESSAGES))
        self.rate_limit_window = int(security_config.get('rate_limit_window', DEFAULT_RATE_LIMIT_WINDOW))
        
        # Command configuration
        self.commands = self._setup_commands()
        
        # Server information for status command
        self.server_info = self.config_manager.get_servers()
        
        # Initialize XFTP client
        self._setup_xftp_client()
        
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
    
    def _setup_xftp_client(self):
        """Setup XFTP client for file downloads"""
        try:
            # Get XFTP configuration (will be added to config.yml)
            xftp_config = self.config.get('xftp', {})
            
            # Default XFTP settings
            cli_path = xftp_config.get('cli_path', '/usr/local/bin/xftp')
            temp_dir = xftp_config.get('temp_dir', './temp/xftp')
            
            # Create XFTP client
            self.xftp_client = XFTPClient(
                cli_path=cli_path,
                temp_dir=temp_dir,
                config=xftp_config,
                logger=self.app_logger
            )
            
            # Check if XFTP is available
            self.xftp_available = self.xftp_client.is_available()
            
            if self.xftp_available:
                self.app_logger.info(f"XFTP client initialized successfully (CLI: {cli_path})")
            else:
                self.app_logger.warning(f"XFTP CLI not available at {cli_path} - large file downloads will be limited")
                self.app_logger.warning(f"Note: XFTP downloads will continue with CLI unavailable for testing purposes")
                
        except Exception as e:
            self.app_logger.error(f"Failed to initialize XFTP client: {e}")
            self.xftp_client = None
            self.xftp_available = False
    
    def generate_correlation_id(self) -> str:
        """Generate a unique correlation ID for requests"""
        self.correlation_counter += 1
        return f"bot_req_{int(time.time())}_{self.correlation_counter}"
    
    async def connect(self, max_retries: int = DEFAULT_MAX_RETRIES, retry_delay: int = DEFAULT_RETRY_DELAY) -> bool:
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
                timeout = DEFAULT_TIMEOUT_SECONDS
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
        self.app_logger.info(f"Sent message to {contact_name}: {message[:MESSAGE_PREVIEW_LENGTH]}...")
    
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
        
        # Get media statistics
        media_stats = self._get_media_statistics()
        
        status_text = f"""
📊 {self.bot_name} Status Report

🔗 Connection:
  • WebSocket: {self.websocket_url}
  • Status: {"Connected" if self.websocket else "Disconnected"}

📡 Servers:
  • SMP: {len(smp_servers)} configured
    {chr(10).join([f"    - {server}" for server in smp_servers[:SERVER_LIST_PREVIEW_COUNT]])}
  • XFTP: {len(xftp_servers)} configured
    {chr(10).join([f"    - {server}" for server in xftp_servers[:SERVER_LIST_PREVIEW_COUNT]])}

📁 Media:
  • Downloads: {"Enabled" if self.media_enabled else "Disabled"}
  • Storage: {self.media_path}
  • Max size: {self.media_config.get('max_file_size', 'N/A')}
  • Files stored: {media_stats['total_files']} ({media_stats['total_size_mb']:.1f} MB)
    - Images: {media_stats['images']}
    - Videos: {media_stats['videos']}
    - Documents: {media_stats['documents']}
    - Audio: {media_stats['audio']}

⚙️ Configuration:
  • Auto-accept contacts: {"Yes" if self.auto_accept_contacts else "No"}
  • Commands enabled: {len(self.commands)}
  • Log retention: {self.config_manager.get('logging.retention_days', 30)} days

🕒 Runtime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return status_text
    
    def _get_media_statistics(self) -> Dict[str, Any]:
        """Get statistics about downloaded media files"""
        stats = {
            'total_files': 0,
            'total_size_mb': 0.0,
            'images': 0,
            'videos': 0,
            'documents': 0,
            'audio': 0
        }
        
        try:
            for media_type in ['images', 'videos', 'documents', 'audio']:
                media_dir = self.media_path / media_type
                if media_dir.exists():
                    files = list(media_dir.glob('*'))
                    stats[media_type] = len(files)
                    stats['total_files'] += len(files)
                    
                    # Calculate total size
                    for file_path in files:
                        if file_path.is_file():
                            stats['total_size_mb'] += file_path.stat().st_size / BYTES_PER_MB
        
        except Exception as e:
            self.app_logger.error(f"Error calculating media statistics: {e}")
        
        return stats
    
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
            msg_content = content.get("msgContent", {})
            msg_type = msg_content.get("type", "unknown")
            
            # Log message type for debugging
            self.app_logger.debug(f"Processing message type: {msg_type}")
            
            if msg_type == "text":
                text = content.get("msgContent", {}).get("text", "")
                
                # Log the message
                self.message_logger.info(f"FROM {contact_name}: {text}")
                self.app_logger.info(f"Received message from {contact_name}: {text[:MESSAGE_PREVIEW_LENGTH]}...")
                
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
                                self.message_logger.info(f"TO {contact_name}: {response[:MESSAGE_PREVIEW_LENGTH]}...")
                        except Exception as e:
                            self.app_logger.error(f"Error handling command {command}: {e}")
                            error_msg = f"Error processing command: {command}"
                            await self.send_message(contact_name, error_msg)
                    else:
                        available_commands = ", ".join(self.commands.keys())
                        response = f"Unknown command: {command}. Available: {available_commands}"
                        await self.send_message(contact_name, response)
            
            # Handle file/media messages
            elif msg_type in ["file", "image", "video", "audio", "media", "attachment"]:
                self.app_logger.info(f"File message detected: {msg_type}")
                await self.handle_file_message(contact_name, content, msg_type)
            else:
                # Log unhandled message types
                if msg_type not in ["text"]:
                    self.app_logger.warning(f"Unhandled message type: {msg_type}")
                        
        except Exception as e:
            self.app_logger.error(f"Error processing message: {e}")
            # Log the full message structure on error for debugging
            self.app_logger.debug(f"Message data structure: {message_data}")
    
    def _clean_content_for_logging(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Clean base64 data from content structure for safe logging"""
        content_for_log = dict(content)
        if 'msgContent' in content_for_log and 'image' in content_for_log['msgContent']:
            image_data = content_for_log['msgContent']['image']
            if isinstance(image_data, str) and image_data.startswith('data:image/'):
                # Truncate base64 data
                header_part = image_data.split(',')[0] if ',' in image_data else image_data
                content_for_log['msgContent']['image'] = f"{header_part},<base64_truncated>"
        return content_for_log
    
    def _extract_file_info_from_content(self, file_info: Dict[str, Any], inner_msg_type: str, contact_name: str) -> tuple[str, int, str]:
        """Extract file information from message content"""
        # Handle SimpleX image format vs traditional file format
        if inner_msg_type == "image" and "image" in file_info:
            # SimpleX image format: type: 'image', image: 'data:image/jpg;base64,[data]'
            image_data_url = file_info.get("image", "")
            file_name = self._generate_image_filename(contact_name, image_data_url)
            file_size = self._calculate_data_url_size(image_data_url)
            file_type = "image"
            
            self.app_logger.info(f"SimpleX image detected: {file_name} ({file_size} bytes)")
            return file_name, file_size, file_type
            
        elif inner_msg_type == "video" and "image" in file_info:
            return self._handle_video_file_info(file_info)
        else:
            # Traditional file format: fileName, fileSize, fileData
            file_name = file_info.get("fileName", "unknown_file")
            file_size = file_info.get("fileSize", 0)
            file_type = self._get_file_type(file_name)
            
            self.app_logger.info(f"Traditional file format: {file_name} ({file_size} bytes)")
            return file_name, file_size, file_type
    
    def _handle_video_file_info(self, file_info: Dict[str, Any]) -> tuple[str, int, str]:
        """Handle video file information extraction"""
        # Check if this is actually an image file misclassified as video
        potential_filename = file_info.get("fileName", "")
        if potential_filename:
            actual_file_type = self._get_file_type(potential_filename)
            if actual_file_type == "image":
                # This is actually an image file, treat it as such
                self.app_logger.info(f"🖼️ Large image detected (misclassified as video): {potential_filename}")
                # Process as image file instead of video
                file_name = potential_filename
                file_size = file_info.get("fileSize", 0)
                file_type = "image"
                return file_name, file_size, file_type
            else:
                # This is a real video file
                return self._extract_video_info(file_info)
        else:
            # No filename available, assume it's a video
            return self._extract_video_info(file_info)
    
    def _extract_video_info(self, file_info: Dict[str, Any]) -> tuple[str, int, str]:
        """Extract video file information"""
        thumbnail_data_url = file_info.get("image", "")
        duration = file_info.get("duration", 0)
        
        file_name = file_info.get("fileName", f"video_{int(time.time())}.mp4")
        file_size = file_info.get("fileSize", 0)
        file_type = "video"
        
        self.app_logger.info(f"🎬 XFTP_DEBUG: SimpleX video detected - name: {file_name}, size: {file_size}, duration: {duration}s")
        self.app_logger.info(f"🎬 XFTP_DEBUG: Video has thumbnail: {len(thumbnail_data_url) > 0}")
        self.app_logger.info(f"🎬 XFTP_DEBUG: Looking for XFTP fields - fileId: {'fileId' in file_info}, fileHash: {'fileHash' in file_info}")
        
        return file_name, file_size, file_type
    
    def _validate_file_for_download(self, file_name: str, file_size: int, file_type: str) -> bool:
        """Validate if file meets download criteria"""
        # Input validation
        if not file_name or not isinstance(file_name, str):
            self.app_logger.error("Invalid file name provided")
            raise MediaProcessingError("Invalid file name")
        
        if not isinstance(file_size, int) or file_size < 0:
            self.app_logger.error(f"Invalid file size: {file_size}")
            raise MediaProcessingError("Invalid file size")
        
        if not file_type or not isinstance(file_type, str):
            self.app_logger.error("Invalid file type provided")
            raise MediaProcessingError("Invalid file type")
        
        # Sanitize filename
        safe_filename = self._sanitize_filename(file_name)
        if not safe_filename:
            self.app_logger.error(f"Filename sanitization failed: {file_name}")
            raise MediaProcessingError("Invalid filename")
        
        # Check file size limit
        max_size = parse_file_size(self.media_config.get('max_file_size', '100MB'))
        if file_size > max_size:
            self.app_logger.warning(f"File too large: {file_name} ({file_size} bytes)")
            return False
        
        # Check if file type is allowed
        if file_type not in self.media_config.get('allowed_types', ['image', 'video', 'document', 'audio']):
            self.app_logger.warning(f"File type not allowed: {file_name}")
            return False
        
        return True
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent security issues"""
        import re
        
        # Remove null bytes and control characters
        filename = ''.join(char for char in filename if ord(char) >= 32)
        
        # Remove path separators and dangerous characters
        forbidden_chars = ['/', '\\', '..', '~', '|', '&', ';', '`', '$', '<', '>', '"', "'"]
        for char in forbidden_chars:
            filename = filename.replace(char, '_')
        
        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = name[:250] + ('.' + ext if ext else '')
        
        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')
        
        # Ensure it's not empty
        if not filename:
            return "unknown_file"
        
        return filename
    
    async def _handle_download_result(self, download_success: str, file_name: str, contact_name: str) -> None:
        """Handle the result of a file download attempt"""
        if download_success == "acknowledged":
            self.app_logger.info(f"Video/audio message acknowledged - waiting for XFTP file description: {file_name}")
            await self.send_message(contact_name, f"📹 Video received - downloading via XFTP...")
        elif download_success == "thumbnail_skipped":
            self.app_logger.info(f"Thumbnail skipped for {file_name} - waiting for XFTP")
            # No message sent - wait for XFTP download
        elif download_success:
            self.app_logger.info(f"Successfully downloaded file: {file_name}")
            await self.send_message(contact_name, f"✓ Downloaded: {file_name}")
        else:
            self.app_logger.error(f"Failed to download file: {file_name}")
            await self.send_message(contact_name, f"✗ Failed to download: {file_name}")

    async def handle_file_message(self, contact_name: str, content: Dict[str, Any], msg_type: str = "file") -> None:
        """Handle incoming file/media messages with actual download functionality"""
        self.app_logger.debug(f"handle_file_message called for {contact_name}, type: {msg_type}")
        
        # Clean base64 data from content structure for logging
        content_for_log = self._clean_content_for_logging(content)
        self.app_logger.debug(f"Content structure: {content_for_log}")
        
        if not self.media_enabled:
            self.app_logger.info("Media downloads disabled, skipping file")
            return
        
        try:
            file_info = content.get("msgContent", {})
            inner_msg_type = file_info.get("type", "")
            self.app_logger.debug(f"File info keys: {list(file_info.keys())}")
            self.app_logger.debug(f"Inner message type: {inner_msg_type}")
            
            # Log basic file info for debugging
            self.app_logger.debug(f"Processing {inner_msg_type} message with fields: {list(file_info.keys())}")
            
            # Extract file information
            file_name, file_size, file_type = self._extract_file_info_from_content(file_info, inner_msg_type, contact_name)
            
            # Validate file for download
            if not self._validate_file_for_download(file_name, file_size, file_type):
                if file_size > parse_file_size(self.media_config.get('max_file_size', '100MB')):
                    await self.send_message(contact_name, f"File {file_name} is too large to download")
                return
            
            # Log the file message
            self.message_logger.info(f"FILE FROM {contact_name}: {file_name} ({file_size} bytes)")
            self.app_logger.info(f"Received file from {contact_name}: {file_name}")
            
            # Attempt to download the file
            download_success = await self._download_file(contact_name, file_info, file_type, inner_msg_type)
            
            # Handle download result
            await self._handle_download_result(download_success, file_name, contact_name)
            
        except (FileDownloadError, MediaProcessingError) as e:
            self.app_logger.error(f"File processing error: {e}")
            await self.send_message(contact_name, f"Error processing file: {str(e)}")
        except Exception as e:
            self.app_logger.error(f"Unexpected error handling file message: {e}")
            await self.send_message(contact_name, f"Error processing file: {str(e)}")
    
    async def handle_file_descriptor_ready(self, data: Dict):
        """Handle rcvFileDescrReady event with XFTP file metadata"""
        try:
            self.app_logger.info(f"🎯 XFTP_DEBUG: Processing file descriptor ready event")
            self.app_logger.info(f"🎯 XFTP_DEBUG: Event data keys: {list(data.keys())}")
            
            # Extract file information from the event
            file_info = data.get("rcvFileInfo", {})
            if not file_info:
                # Try alternative key names
                file_info = data.get("rcvFileDescr", {})
                if not file_info:
                    file_info = data.get("rcvFileTransfer", {})
                    if not file_info:
                        self.app_logger.warning(f"🎯 XFTP_DEBUG: No file info found in event data")
                        self.app_logger.warning(f"🎯 XFTP_DEBUG: Available keys: {list(data.keys())}")
                        return
                    else:
                        self.app_logger.info(f"🎯 XFTP_DEBUG: Found file info in rcvFileTransfer")
                else:
                    self.app_logger.info(f"🎯 XFTP_DEBUG: Found file info in rcvFileDescr")
            
            self.app_logger.info(f"🎯 XFTP_DEBUG: File info keys: {list(file_info.keys())}")
            self.app_logger.info(f"🎯 XFTP_DEBUG: Full file info: {file_info}")
            
            # Extract contact information from chat item (the sender)
            chat_item = data.get("chatItem", {})
            chat_info = chat_item.get("chatInfo", {})
            if "contact" in chat_info:
                contact_name = chat_info["contact"].get("localDisplayName", "Unknown")
            else:
                # Fallback to user info if no contact found
                user_info = data.get("user", {})
                contact_name = user_info.get("localDisplayName", "Unknown")
            
            # Extract XFTP file description text
            file_descr_text = file_info.get("fileDescrText", "")
            file_descr_complete = file_info.get("fileDescrComplete", False)
            
            self.app_logger.info(f"🎯 XFTP_DEBUG: File description complete: {file_descr_complete}")
            self.app_logger.info(f"🎯 XFTP_DEBUG: File description text (first 200 chars): {file_descr_text[:200]}...")
            
            if not file_descr_text or not file_descr_complete:
                self.app_logger.warning(f"🎯 XFTP_DEBUG: Incomplete file description - cannot download")
                return
            
            # Parse file information from description text
            file_size = self._parse_xftp_file_size(file_descr_text)
            
            # Use a temporary filename for initial download - actual filename will be determined after download
            temp_file_name = f"xftp_download_{int(time.time())}"
            
            # Extract chat item for more details if available
            chat_item = data.get("chatItem", {})
            if chat_item:
                content = chat_item.get("content", {})
                msg_content = content.get("msgContent", {})
                # For now, we'll let the XFTP client determine the actual filename from the download
            
            self.app_logger.info(f"🎯 XFTP_DEBUG: Ready to download - temp name: {temp_file_name}, size: {file_size}")
            self.app_logger.info(f"🎯 XFTP_DEBUG: XFTP description available: {len(file_descr_text)} chars")
            
            # Create a file info dict compatible with our XFTP client
            xftp_file_info = {
                'fileName': temp_file_name,
                'fileSize': file_size,
                'fileDescrText': file_descr_text  # Use the actual XFTP description
            }
            
            # Attempt XFTP download - this will return the actual filename and path
            download_result = await self._download_via_xftp_with_filename_detection(xftp_file_info, contact_name)
            
            if download_result:
                actual_filename, actual_path = download_result
                self.app_logger.info(f"🎯 XFTP_DEBUG: File download successful: {actual_filename} at {actual_path}")
                await self.send_message(contact_name, f"✓ Downloaded via XFTP: {actual_filename}")
            else:
                self.app_logger.error(f"🎯 XFTP_DEBUG: File download failed: {temp_file_name}")
                await self.send_message(contact_name, f"✗ XFTP download failed")
                
        except Exception as e:
            self.app_logger.error(f"🎯 XFTP_DEBUG: Error handling file descriptor ready: {e}")
    
    async def _download_via_xftp_with_filename_detection(self, file_info: Dict, contact_name: str) -> Optional[tuple]:
        """Download file via XFTP and return actual filename and path"""
        try:
            file_size = file_info.get('fileSize', 0)
            file_descr_text = file_info.get('fileDescrText', '')
            
            if not file_descr_text:
                self.app_logger.error("No XFTP file description provided")
                return None
            
            self.app_logger.info(f"🔥 XFTP_DEBUG: Starting XFTP download with filename detection")
            
            # Use XFTP client to download to a temporary directory first
            if not self.xftp_available:
                self.app_logger.error("XFTP client not available")
                return None
            
            # Use the new XFTP client method that preserves filenames
            import tempfile
            with tempfile.TemporaryDirectory(prefix="xftp_download_") as temp_dir:
                
                # Download using XFTP client with filename detection
                success, actual_filename, file_path = await self.xftp_client.download_file_with_description_get_filename(
                    file_description=file_descr_text,
                    file_size=file_size,
                    temp_dir=temp_dir
                )
                
                if not success or not actual_filename:
                    self.app_logger.error("XFTP download failed or no filename detected")
                    return None
                
                self.app_logger.info(f"🔥 XFTP_DEBUG: Successfully detected actual filename: {actual_filename}")
                
                # Determine file type and storage directory
                file_type = self._get_file_type(actual_filename)
                safe_filename = self._generate_safe_filename(actual_filename, contact_name, file_type)
                
                # Determine storage directory
                if file_type == 'audio':
                    storage_dir = self.media_path / 'audio'
                else:
                    storage_dir = self.media_path / f"{file_type}s"
                storage_dir.mkdir(exist_ok=True)
                
                final_path = storage_dir / safe_filename
                
                # Move file to final location
                import shutil
                shutil.move(file_path, str(final_path))
                
                self.app_logger.info(f"🔥 XFTP_DEBUG: File moved to final location: {final_path}")
                
                return (actual_filename, str(final_path))
                
        except Exception as e:
            self.app_logger.error(f"Error in XFTP download with filename detection: {e}")
            return None
    
    def _parse_xftp_file_size(self, file_descr_text: str) -> int:
        """Parse file size from XFTP file description text"""
        try:
            import re
            # Look for "size: XXmb" pattern
            size_match = re.search(r'size:\s*(\d+)([kmg]?b)', file_descr_text, re.IGNORECASE)
            if size_match:
                size_num = int(size_match.group(1))
                size_unit = size_match.group(2).lower()
                
                if size_unit == 'gb':
                    return size_num * 1024 * 1024 * 1024
                elif size_unit == 'mb':
                    return size_num * 1024 * 1024
                elif size_unit == 'kb':
                    return size_num * 1024
                else:  # bytes
                    return size_num
            
            return 0
        except Exception as e:
            self.app_logger.error(f"Error parsing XFTP file size: {e}")
            return 0
    
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
    
    def _generate_safe_filename(self, original_name: str, contact_name: str, file_type: str) -> str:
        """Generate a safe, unique filename to avoid conflicts"""
        # Input validation
        if not isinstance(original_name, str):
            original_name = "unknown_file"
        if not isinstance(contact_name, str):
            contact_name = "unknown_contact"
        if not isinstance(file_type, str):
            file_type = "unknown"
        
        # Sanitize the original filename
        safe_name = self._sanitize_filename(original_name)
        if not safe_name:
            safe_name = "unknown_file"
        
        # Add timestamp and contact info for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_contact = self._sanitize_filename(contact_name)[:20]
        
        # Split filename and extension
        name_part = Path(safe_name).stem
        ext_part = Path(safe_name).suffix
        
        # Create unique filename
        unique_name = f"{timestamp}_{safe_contact}_{name_part}{ext_part}"
        
        # Ensure it's not too long
        if len(unique_name) > 200:
            unique_name = f"{timestamp}_{safe_contact}_{name_part[:50]}{ext_part}"
        
        return unique_name
    
    def _generate_image_filename(self, contact_name: str, image_data_url: str) -> str:
        """Generate a filename for SimpleX images that don't have explicit names"""
        try:
            # Extract file extension from data URL (e.g., data:image/jpg;base64,...)
            if image_data_url.startswith("data:image/"):
                mime_part = image_data_url.split(";")[0]  # data:image/jpg
                image_format = mime_part.split("/")[1]    # jpg
                
                # Map common formats
                format_map = {
                    "jpeg": "jpg",
                    "png": "png",
                    "gif": "gif",
                    "webp": "webp",
                    "bmp": "bmp"
                }
                ext = format_map.get(image_format, image_format)
            else:
                ext = "jpg"  # Default fallback
            
            # Generate timestamp-based filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_contact = "".join(c for c in contact_name if c.isalnum() or c in "_-")[:20]
            
            filename = f"{timestamp}_{safe_contact}_image.{ext}"
            
            self.app_logger.debug(f"Generated image filename: {filename}")
            return filename
            
        except Exception as e:
            self.app_logger.error(f"Error generating image filename: {e}")
            return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_image.jpg"
    
    def _calculate_data_url_size(self, data_url: str) -> int:
        """Calculate the size of data from a data URL"""
        try:
            if not data_url.startswith("data:"):
                return 0
            
            # Extract base64 part after the comma
            if "," in data_url:
                base64_data = data_url.split(",", 1)[1]
                # Calculate approximate size (base64 is ~4/3 the size of original data)
                # Remove any padding characters for accurate calculation
                base64_clean = base64_data.rstrip("=")
                original_size = (len(base64_clean) * 3) // 4
                
                self.app_logger.debug(f"Calculated data URL size: {original_size} bytes")
                return original_size
            
            return 0
            
        except Exception as e:
            self.app_logger.error(f"Error calculating data URL size: {e}")
            return 0
    
    def _parse_data_url(self, data_url: str) -> tuple[str, str]:
        """Parse a data URL and return (mime_type, base64_data)"""
        try:
            if not data_url.startswith("data:"):
                raise ValueError("Invalid data URL format")
            
            # Split into header and data parts
            header, data = data_url.split(",", 1)
            
            # Extract MIME type from header (e.g., "data:image/jpg;base64")
            mime_type = header.split(";")[0].replace("data:", "")
            
            return mime_type, data
            
        except Exception as e:
            self.app_logger.error(f"Error parsing data URL: {e}")
            return "application/octet-stream", ""
    
    async def _download_file(self, contact_name: str, file_info: Dict, file_type: str, inner_msg_type: str = "file") -> bool:
        """Download file using available methods (direct data or XFTP)"""
        try:
            self.app_logger.info(f"🔍 XFTP_DEBUG: Starting file download - contact: {contact_name}, type: {file_type}, inner_msg_type: {inner_msg_type}")
            self.app_logger.info(f"🔍 XFTP_DEBUG: File info keys: {list(file_info.keys())}")
            # Clean base64 data for logging
            file_info_for_log = dict(file_info)
            if 'image' in file_info_for_log and isinstance(file_info_for_log['image'], str):
                if file_info_for_log['image'].startswith('data:image/'):
                    header_part = file_info_for_log['image'].split(',')[0] if ',' in file_info_for_log['image'] else file_info_for_log['image']
                    file_info_for_log['image'] = f"{header_part},<base64_truncated>"
            
            self.app_logger.info(f"🔍 XFTP_DEBUG: Full file_info: {file_info_for_log}")
            
            # Handle SimpleX image format - Skip thumbnails, wait for XFTP
            if inner_msg_type == "image" and "image" in file_info:
                image_data_url = file_info.get("image", "")
                file_name = self._generate_image_filename(contact_name, image_data_url)
                file_size = self._calculate_data_url_size(image_data_url)
                
                self.app_logger.info(f"🔍 XFTP_DEBUG: Processing SimpleX image - name: {file_name}, size: {file_size}")
                self.app_logger.info(f"🔍 XFTP_DEBUG: This is an embedded image (thumbnail), skipping - waiting for XFTP")
                
                # Skip thumbnail download, return acknowledgment
                return "thumbnail_skipped"
            
            # Handle traditional file format
            else:
                file_name = file_info.get("fileName", "unknown_file")
                file_size = file_info.get("fileSize", 0)
                
                self.app_logger.info(f"🔍 XFTP_DEBUG: Processing traditional file - name: {file_name}, size: {file_size}")
                
                # Check for XFTP indicators
                has_file_id = "fileId" in file_info
                has_file_hash = "fileHash" in file_info
                has_file_data = "fileData" in file_info
                
                self.app_logger.info(f"🔍 XFTP_DEBUG: File indicators - fileId: {has_file_id}, fileHash: {has_file_hash}, fileData: {has_file_data}")
                if has_file_id:
                    self.app_logger.info(f"🔍 XFTP_DEBUG: fileId value: {file_info.get('fileId')}")
                if has_file_hash:
                    self.app_logger.info(f"🔍 XFTP_DEBUG: fileHash value: {file_info.get('fileHash')}")
                
                # Generate safe filename
                safe_filename = self._generate_safe_filename(file_name, contact_name, file_type)
                
                # Determine storage directory
                if file_type == 'audio':
                    storage_dir = self.media_path / 'audio'
                else:
                    storage_dir = self.media_path / f"{file_type}s"  # images, videos, documents
                storage_dir.mkdir(exist_ok=True)
                
                file_path = storage_dir / safe_filename
                
                # Method 1: Skip thumbnails - only use XFTP
                if "fileData" in file_info:
                    self.app_logger.info(f"🔍 XFTP_DEBUG: Direct file data (thumbnail) detected - skipping, waiting for XFTP")
                    return "thumbnail_skipped"
                
                # Method 2: Try XFTP download using file ID/hash
                elif "fileId" in file_info or "fileHash" in file_info:
                    self.app_logger.info(f"🔍 XFTP_DEBUG: Using Method 2 - XFTP download (large file)")
                    self.app_logger.info(f"🔍 XFTP_DEBUG: XFTP available: {self.xftp_available}")
                    
                    xftp_success = await self._download_via_xftp(file_info, file_path, file_name)
                    if xftp_success:
                        self.app_logger.info(f"🔍 XFTP_DEBUG: XFTP download successful")
                        return True
                    
                    # Fallback to SMP if XFTP fails
                    self.app_logger.warning(f"🔍 XFTP_DEBUG: XFTP download failed for {file_name}, attempting SMP fallback")
                    return await self._download_via_smp_fallback(file_info, file_path, file_name)
                
                # Method 3: Handle video/audio messages without XFTP indicators
                else:
                    # For video/audio messages, the initial message only contains thumbnail
                    # The actual file will arrive later via rcvFileDescrReady event
                    if inner_msg_type in ["video", "audio"]:
                        self.app_logger.info(f"📹 Video/audio message received - waiting for XFTP file description")
                        # Don't attempt download - just acknowledge receipt
                        # The rcvFileDescrReady event will handle the actual download
                        return "acknowledged"  # Special return value to indicate waiting for XFTP
                    else:
                        # For other file types without XFTP indicators, assume it's a thumbnail - skip
                        self.app_logger.info(f"🔍 XFTP_DEBUG: File without XFTP indicators detected - likely thumbnail, skipping: {file_name} (type: {inner_msg_type})")
                        return "thumbnail_skipped"
                
        except Exception as e:
            self.app_logger.error(f"Error in file download: {e}")
            # If it's likely a thumbnail parsing error, skip instead of failing
            if "fileData" in file_info or ("image" in file_info and inner_msg_type == "image"):
                self.app_logger.info(f"🔍 XFTP_DEBUG: Error likely from thumbnail processing - skipping")
                return "thumbnail_skipped"
            return False
    
    async def _save_simplex_image_data(self, image_data_url: str, file_path: Path, original_name: str) -> bool:
        """Save SimpleX image data from data URL format"""
        try:
            self.app_logger.debug(f"Saving SimpleX image data to {file_path}")
            
            # Parse the data URL to extract base64 content
            mime_type, base64_data = self._parse_data_url(image_data_url)
            
            # Debug: Log actual base64 data length
            self.app_logger.info(f"📊 Base64 DEBUG: Original data URL length: {len(image_data_url)}")
            self.app_logger.info(f"📊 Base64 DEBUG: Extracted base64 data length: {len(base64_data)}")
            self.app_logger.info(f"📊 Base64 DEBUG: First 50 chars of base64: {base64_data[:50]}")
            
            if not base64_data:
                self.app_logger.error(f"No base64 data found in image URL for {original_name}")
                return False
            
            # Decode base64 image data with proper padding
            try:
                # Fix base64 padding if needed
                missing_padding = len(base64_data) % 4
                if missing_padding:
                    base64_data += '=' * (4 - missing_padding)
                
                file_bytes = base64.b64decode(base64_data)
            except Exception as e:
                self.app_logger.error(f"Failed to decode base64 data for {original_name}: {e}")
                return False
            
            # Write to file
            with open(file_path, 'wb') as f:
                f.write(file_bytes)
            
            # Validate the downloaded file
            if self._validate_downloaded_file(file_path, len(file_bytes)):
                self.app_logger.info(f"Saved SimpleX image: {file_path} ({len(file_bytes)} bytes)")
                
                # Calculate and log file hash for integrity
                file_hash = self._get_file_hash(file_path)
                if file_hash:
                    self.app_logger.debug(f"Image hash (SHA-256): {file_hash}")
                
                return True
            else:
                self.app_logger.error(f"File validation failed for {original_name}")
                self._cleanup_failed_download(file_path)
                return False
            
        except Exception as e:
            self.app_logger.error(f"Error saving SimpleX image data for {original_name}: {e}")
            self._cleanup_failed_download(file_path)
            return False
    
    async def _save_direct_file_data(self, file_data: str, file_path: Path, original_name: str) -> bool:
        """Save file data that's directly embedded in the message"""
        try:
            # Decode base64 file data with proper padding
            # Fix base64 padding if needed
            missing_padding = len(file_data) % 4
            if missing_padding:
                file_data += '=' * (4 - missing_padding)
            
            file_bytes = base64.b64decode(file_data)
            
            # Write to file
            with open(file_path, 'wb') as f:
                f.write(file_bytes)
            
            # Validate the downloaded file
            if self._validate_downloaded_file(file_path, len(file_bytes)):
                self.app_logger.info(f"Saved file directly: {file_path} ({len(file_bytes)} bytes)")
                
                # Calculate and log file hash for integrity
                file_hash = self._get_file_hash(file_path)
                if file_hash:
                    self.app_logger.debug(f"File hash (SHA-256): {file_hash}")
                
                return True
            else:
                self.app_logger.error(f"File validation failed for {original_name}")
                self._cleanup_failed_download(file_path)
                return False
            
        except Exception as e:
            self.app_logger.error(f"Error saving direct file data for {original_name}: {e}")
            self._cleanup_failed_download(file_path)
            return False
    
    async def _download_via_xftp(self, file_info: Dict, file_path: Path, original_name: str) -> bool:
        """Download file via XFTP using file ID or hash"""
        try:
            self.app_logger.info(f"🔥 XFTP_DEBUG: _download_via_xftp called for {original_name}")
            
            # Check if XFTP client is available
            if not self.xftp_client:
                self.app_logger.warning(f"🔥 XFTP_DEBUG: XFTP client not initialized for {original_name}")
                return False
            
            if not self.xftp_available:
                self.app_logger.warning(f"🔥 XFTP_DEBUG: XFTP CLI not available, but proceeding for testing - {original_name}")
                # Continue anyway for testing purposes
            
            # Check for new XFTP format (file description text)
            file_descr_text = file_info.get("fileDescrText")
            if file_descr_text:
                self.app_logger.info(f"🔥 XFTP_DEBUG: Using XFTP file description format")
                file_size = file_info.get("fileSize", 0)
                
                self.app_logger.info(f"🔥 XFTP_DEBUG: File description length: {len(file_descr_text)} chars, Size: {file_size}")
                self.app_logger.info(f"🔥 XFTP_DEBUG: Starting XFTP download for {original_name} (Size: {file_size})")
                
                # Use XFTPClient with file description text
                self.app_logger.info(f"🔥 XFTP_DEBUG: Calling xftp_client.download_file_with_description")
                success = await self.xftp_client.download_file_with_description(
                    file_description=file_descr_text,
                    file_size=file_size,
                    file_name=original_name,
                    output_path=str(file_path)
                )
            else:
                # Fallback to old format
                file_id = file_info.get("fileId")
                file_hash = file_info.get("fileHash")
                file_size = file_info.get("fileSize", 0)
                
                self.app_logger.info(f"🔥 XFTP_DEBUG: File parameters - ID: {file_id}, Hash: {file_hash}, Size: {file_size}")
                
                if not file_id:
                    self.app_logger.warning(f"🔥 XFTP_DEBUG: No file ID available for XFTP download: {original_name}")
                    return False
                
                if not file_hash:
                    self.app_logger.warning(f"🔥 XFTP_DEBUG: No file hash available for integrity verification: {original_name}")
                    return False
                
                self.app_logger.info(f"🔥 XFTP_DEBUG: Starting XFTP download for {original_name} (ID: {file_id}, Size: {file_size})")
                
                # Use XFTPClient to download the file
                self.app_logger.info(f"🔥 XFTP_DEBUG: Calling xftp_client.download_file with output_path: {file_path}")
                success = await self.xftp_client.download_file(
                    file_id=file_id,
                    file_hash=file_hash,
                    file_size=file_size,
                    file_name=original_name,
                    output_path=str(file_path)
                )
            
            if success:
                self.app_logger.info(f"🔥 XFTP_DEBUG: XFTP download completed successfully: {original_name}")
                return True
            else:
                self.app_logger.warning(f"🔥 XFTP_DEBUG: XFTP download failed: {original_name}")
                return False
                
        except XFTPError as e:
            self.app_logger.error(f"🔥 XFTP_DEBUG: XFTP error downloading {original_name}: {e}")
            return False
        except Exception as e:
            self.app_logger.error(f"🔥 XFTP_DEBUG: Unexpected error in XFTP download for {original_name}: {e}")
            return False
    
    async def _download_via_smp_fallback(self, file_info: Dict, file_path: Path, original_name: str) -> bool:
        """Fallback to SMP download when XFTP fails"""
        try:
            # Try to request the file through SMP protocol
            # This would typically involve sending a download request through SimpleX CLI
            file_id = file_info.get("fileId")
            file_hash = file_info.get("fileHash")
            
            if not file_id and not file_hash:
                self.app_logger.warning(f"No file ID or hash available for SMP fallback: {original_name}")
                return False
            
            self.app_logger.info(f"Attempting SMP fallback download for {original_name}")
            
            # Send download request command (this is a simplified approach)
            download_cmd = f"/receive_file {file_id or file_hash}"
            
            try:
                response = await self.send_command(download_cmd, wait_for_response=True, timeout=30)
                
                if response and "file received" in response.lower():
                    self.app_logger.info(f"SMP fallback download initiated for {original_name}")
                    # Note: The actual file transfer would happen through the CLI
                    # This is a placeholder for SMP integration
                    return True
                else:
                    self.app_logger.warning(f"SMP fallback download failed for {original_name}")
                    return False
                    
            except asyncio.TimeoutError:
                self.app_logger.warning(f"SMP fallback download timed out for {original_name}")
                return False
                
        except Exception as e:
            self.app_logger.error(f"Error in SMP fallback download for {original_name}: {e}")
            return False
    
    def _is_download_successful(self, response: Dict) -> bool:
        """Check if a download response indicates success"""
        try:
            if "resp" in response and "Right" in response["resp"]:
                resp_data = response["resp"]["Right"]
                resp_type = resp_data.get("type", "")
                return resp_type in ["fileDownloaded", "downloadComplete", "success"]
            return False
        except Exception:
            return False
    
    def _validate_downloaded_file(self, file_path: Path, expected_size: int = None) -> bool:
        """Validate that a downloaded file is complete and not corrupted"""
        try:
            if not file_path.exists():
                return False
            
            # Check if file is empty
            if file_path.stat().st_size == 0:
                self.app_logger.warning(f"Downloaded file is empty: {file_path}")
                return False
            
            # Check expected size if provided
            if expected_size and file_path.stat().st_size != expected_size:
                self.app_logger.warning(f"File size mismatch: expected {expected_size}, got {file_path.stat().st_size}")
                return False
            
            # Basic file integrity check - try to read the file
            try:
                with open(file_path, 'rb') as f:
                    f.read(FILE_READ_CHUNK_SIZE)  # Read first chunk to check accessibility
            except Exception as e:
                self.app_logger.error(f"Cannot read downloaded file {file_path}: {e}")
                return False
            
            return True
            
        except Exception as e:
            self.app_logger.error(f"Error validating file {file_path}: {e}")
            return False
    
    def _cleanup_failed_download(self, file_path: Path):
        """Clean up partially downloaded or corrupted files"""
        try:
            if file_path.exists():
                file_path.unlink()
                self.app_logger.info(f"Cleaned up failed download: {file_path}")
        except Exception as e:
            self.app_logger.error(f"Error cleaning up file {file_path}: {e}")
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file for integrity checking"""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            self.app_logger.error(f"Error calculating hash for {file_path}: {e}")
            return ""
    
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
            elif resp_type == "rcvFileDescrReady":
                self.app_logger.info(f"🎯 XFTP_DEBUG: rcvFileDescrReady event received!")
                await self.handle_file_descriptor_ready(actual_resp)
            else:
                self.app_logger.debug(f"Received response type: {resp_type}")
                
        except Exception as e:
            self.app_logger.error(f"Error handling response: {e}")
    
    def _log_websocket_message_safely(self, message: str, data: Dict):
        """Log WebSocket messages while filtering out base64 data to prevent log spam"""
        try:
            # Check if this is a file message with base64 data
            if self._contains_base64_file_data(data):
                # Log a summary instead of the full message
                msg_type = "unknown"
                file_name = "unknown"
                file_size = 0
                
                # Extract basic info for logging
                if "resp" in data and "Right" in data["resp"]:
                    resp_data = data["resp"]["Right"]
                    msg_type = resp_data.get("type", "unknown")
                    
                    if msg_type in ["newChatItem", "newChatItems"]:
                        # Try to extract file info
                        chat_item = resp_data.get("chatItem", {}) if msg_type == "newChatItem" else {}
                        if not chat_item and msg_type == "newChatItems":
                            chat_items = resp_data.get("chatItems", [])
                            if chat_items:
                                chat_item = chat_items[0].get("chatItem", {})
                        
                        content = chat_item.get("content", {})
                        msg_content = content.get("msgContent", {})
                        content_type = msg_content.get("type", "")
                        
                        if content_type == "file":
                            file_name = msg_content.get("fileName", "unknown")
                            file_size = msg_content.get("fileSize", 0)
                        elif content_type == "image":
                            file_name = "image"
                            image_data = msg_content.get("image", "")
                            if image_data.startswith("data:image/"):
                                # Calculate approximate size from data URL
                                if "," in image_data:
                                    base64_data = image_data.split(",", 1)[1]
                                    file_size = (len(base64_data.rstrip("=")) * 3) // 4
                                else:
                                    file_size = 0
                            else:
                                file_size = 0
                
                self.app_logger.debug(f"Received message type: {msg_type} (file: {file_name}, {file_size} bytes) - base64 data filtered")
            else:
                # Log normally for non-file messages
                self.app_logger.debug(f"Received WebSocket message: {message[:200]}...")
                
        except Exception as e:
            self.app_logger.debug(f"Error in safe logging: {e}")
    
    def _contains_base64_file_data(self, data: Dict) -> bool:
        """Check if the message contains base64 file data"""
        try:
            if "resp" in data and "Right" in data["resp"]:
                resp_data = data["resp"]["Right"]
                msg_type = resp_data.get("type", "")
                
                if msg_type == "newChatItem":
                    return self._check_chat_item_for_file_data(resp_data.get("chatItem", {}))
                elif msg_type == "newChatItems":
                    chat_items = resp_data.get("chatItems", [])
                    return any(self._check_chat_item_for_file_data(item.get("chatItem", {})) for item in chat_items)
            
            return False
        except Exception:
            return False
    
    def _check_chat_item_for_file_data(self, chat_item: Dict) -> bool:
        """Check if a chat item contains file data"""
        try:
            content = chat_item.get("content", {})
            msg_content = content.get("msgContent", {})
            msg_type = msg_content.get("type", "")
            
            # Check for traditional file format with embedded data
            if msg_type == "file" and "fileData" in msg_content:
                return True
            
            # Check for SimpleX image format with data URL
            if msg_type == "image" and "image" in msg_content:
                image_data = msg_content.get("image", "")
                return image_data.startswith("data:image/")
            
            return False
        except Exception:
            return False

    async def listen_for_messages(self):
        """Listen for incoming messages from SimpleX Chat CLI"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    
                    # Smart logging that filters out base64 image data
                    self._log_websocket_message_safely(message, data)
                    
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