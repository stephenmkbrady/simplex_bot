#!/usr/bin/env python3
"""
Message Handler for SimpleX Bot
Handles message processing, routing, and command execution
"""

import logging
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime

from file_download_manager import FileDownloadManager


class MessageHandler:
    """Handles incoming message processing and routing"""
    
    def __init__(self, 
                 command_registry: 'CommandRegistry',
                 file_download_manager: FileDownloadManager,
                 send_message_callback: Callable,
                 logger: logging.Logger,
                 message_logger: logging.Logger):
        self.command_registry = command_registry
        self.file_download_manager = file_download_manager
        self.send_message_callback = send_message_callback
        self.logger = logger
        self.message_logger = message_logger
        
        # Constants
        self.MESSAGE_PREVIEW_LENGTH = 100
    
    async def process_message(self, message_data: Dict[str, Any]) -> None:
        """Process an incoming message and handle commands"""
        try:
            # Extract message information
            chat_item = message_data.get("chatItem", {})
            chat_info = message_data.get("chatInfo", {})
            
            # Get contact name - it's nested in the contact object
            contact_info = chat_info.get("contact", {})
            contact_name = contact_info.get("localDisplayName", "Unknown")
            
            # Debug logging to see the structure
            self.logger.debug(f"Chat info keys: {list(chat_info.keys())}")
            self.logger.debug(f"Contact info keys: {list(contact_info.keys())}")
            self.logger.debug(f"Extracted contact name: {contact_name}")
            
            # Get message content
            content = chat_item.get("content", {})
            msg_content = content.get("msgContent", {})
            msg_type = msg_content.get("type", "unknown")
            
            # Log message type for debugging
            self.logger.debug(f"Processing message type: {msg_type}")
            
            if msg_type == "text":
                await self._handle_text_message(contact_name, content)
            elif msg_type in ["file", "image", "video", "audio", "media", "attachment"]:
                await self._handle_file_message(contact_name, content, msg_type)
            else:
                # Log unhandled message types
                if msg_type not in ["text"]:
                    self.logger.warning(f"Unhandled message type: {msg_type}")
                        
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            # Log the full message structure on error for debugging
            self.logger.debug(f"Message data structure: {message_data}")
    
    async def _handle_text_message(self, contact_name: str, content: Dict[str, Any]) -> None:
        """Handle text messages and command processing"""
        text = content.get("msgContent", {}).get("text", "")
        
        # Log the message
        self.message_logger.info(f"FROM {contact_name}: {text}")
        self.logger.info(f"Received message from {contact_name}: {text[:self.MESSAGE_PREVIEW_LENGTH]}...")
        
        # Check if it's a command
        if self.command_registry.is_command(text):
            await self._process_command(contact_name, text)
    
    async def _process_command(self, contact_name: str, text: str) -> None:
        """Process a command message"""
        try:
            # Try to get plugin manager from the bot instance
            plugin_manager = None
            if hasattr(self, '_bot_instance'):
                plugin_manager = getattr(self._bot_instance, 'plugin_manager', None)
            
            result = await self.command_registry.execute_command(text, contact_name, plugin_manager)
            if result:
                await self.send_message_callback(contact_name, result)
                self.message_logger.info(f"TO {contact_name}: {result[:self.MESSAGE_PREVIEW_LENGTH]}...")
        except Exception as e:
            self.logger.error(f"Error executing command: {e}")
            error_msg = f"Error processing command"
            await self.send_message_callback(contact_name, error_msg)
    
    async def _handle_file_message(self, contact_name: str, content: Dict[str, Any], msg_type: str) -> None:
        """Handle file/media messages"""
        self.logger.info(f"File message detected: {msg_type}")
        
        # Clean base64 data from content structure for logging
        content_for_log = self.file_download_manager.clean_content_for_logging(content)
        self.logger.debug(f"Content structure: {content_for_log}")
        
        if not self.file_download_manager.media_enabled:
            self.logger.info("Media downloads disabled, skipping file")
            return
        
        try:
            file_info = content.get("msgContent", {})
            inner_msg_type = file_info.get("type", "")
            self.logger.debug(f"File info keys: {list(file_info.keys())}")
            self.logger.debug(f"Inner message type: {inner_msg_type}")
            
            # Extract file information
            file_name, file_size, file_type = self.file_download_manager.extract_file_info_from_content(
                file_info, inner_msg_type, contact_name
            )
            
            # Validate file for download
            if not self.file_download_manager.validate_file_for_download(file_name, file_size, file_type):
                from config_manager import parse_file_size
                max_size = parse_file_size(self.file_download_manager.media_config.get('max_file_size', '100MB'))
                if file_size > max_size:
                    await self.send_message_callback(contact_name, f"File {file_name} is too large to download")
                return
            
            # Log the file message
            self.message_logger.info(f"FILE FROM {contact_name}: {file_name} ({file_size} bytes)")
            self.logger.info(f"Received file from {contact_name}: {file_name}")
            
            # For now, acknowledge that we would download the file
            # TODO: Implement actual download logic with XFTP integration
            await self.send_message_callback(contact_name, f"📁 File received: {file_name}")
            
        except Exception as e:
            self.logger.error(f"Error handling file message: {e}")
            await self.send_message_callback(contact_name, f"Error processing file: {str(e)}")


class CommandRegistry:
    """Registry for bot commands with extensible command system"""
    
    def __init__(self, command_prefix: str = "!", logger: logging.Logger = None):
        self.command_prefix = command_prefix
        self.logger = logger or logging.getLogger(__name__)
        self.commands: Dict[str, Callable] = {}
        
        # Register default commands
        self._register_default_commands()
    
    def _register_default_commands(self) -> None:
        """Register the default bot commands"""
        self.register_command("help", self._handle_help)
        self.register_command("echo", self._handle_echo)
        self.register_command("status", self._handle_status)
    
    def register_command(self, name: str, handler: Callable) -> None:
        """Register a new command handler"""
        command_name = f"{self.command_prefix}{name}"
        self.commands[command_name] = handler
        self.logger.debug(f"Registered command: {command_name}")
    
    def is_command(self, text: str) -> bool:
        """Check if text is a command"""
        return any(text.startswith(cmd) for cmd in self.commands.keys())
    
    async def execute_command(self, text: str, contact_name: str) -> Optional[str]:
        """Execute a command and return the response"""
        parts = text.split()
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        if command in self.commands:
            try:
                return await self.commands[command](contact_name, args)
            except Exception as e:
                self.logger.error(f"Error handling command {command}: {e}")
                return f"Error processing command: {command}"
        else:
            available_commands = ", ".join(self.commands.keys())
            return f"Unknown command: {command}. Available: {available_commands}"
    
    def get_commands_list(self) -> List[str]:
        """Get list of available commands"""
        return list(self.commands.keys())
    
    # Default command handlers
    async def _handle_help(self, contact_name: str, args: List[str] = None) -> str:
        """Handle the !help command"""
        commands_list = ", ".join(self.commands.keys())
        
        help_text = f"""
🤖 SimpleX Bot Commands:

{commands_list}

📡 Bot is online and ready
🕒 Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Use !status for detailed information.
        """.strip()
        
        return help_text
    
    async def _handle_echo(self, contact_name: str, args: List[str] = None) -> str:
        """Handle the !echo command"""
        if not args:
            return "Usage: !echo <text_to_echo>"
        
        echo_text = " ".join(args)
        return f"Echo: {echo_text}"
    
    async def _handle_status(self, contact_name: str, args: List[str] = None) -> str:
        """Handle the !status command - placeholder for now"""
        # This will be populated by the main bot class with actual status info
        return f"""
📊 SimpleX Bot Status

🔗 Connection: Active
🕒 Runtime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

For detailed status information, the bot owner needs to implement status reporting.
        """.strip()