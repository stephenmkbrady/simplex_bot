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
        
        # Removed contact ID resolver - using simple contact_name approach
        
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
            
            # Simple approach - just use contact_name for admin checks
            self.logger.debug(f"Processing message from contact: {contact_name}")
            
            # Get message content
            content = chat_item.get("content", {})
            msg_content = content.get("msgContent", {})
            msg_type = msg_content.get("type", "unknown")
            
            # Log message type for debugging
            self.logger.debug(f"Processing message type: {msg_type}")
            
            if msg_type == "text":
                await self._handle_text_message(contact_name, content)
            elif msg_type == "link":
                # Handle link messages (treat similar to text for commands)
                await self._handle_text_message(contact_name, content)
            elif msg_type in ["file", "image", "video", "audio", "media", "attachment"]:
                await self._handle_file_message(contact_name, content, msg_type)
            else:
                # Log unhandled message types
                if msg_type not in ["text", "link"]:
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


