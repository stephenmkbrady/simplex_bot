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
            
            # Debug: Log the message structure to understand the issue
            self.logger.info(f"🔍 MESSAGE DEBUG: chat_info keys: {list(chat_info.keys())}")
            self.logger.info(f"🔍 MESSAGE DEBUG: chat_item keys: {list(chat_item.keys())}")
            
            # Determine chat type (direct contact or group)
            # Check for groupInfo to determine if this is a group message
            if "groupInfo" in chat_info:
                chat_type = "group"
            elif "contact" in chat_info:
                chat_type = "direct"
            else:
                # Fallback - check the 'type' field
                chat_type = chat_info.get("type", "direct")
            
            self.logger.info(f"🔍 MESSAGE DEBUG: detected chat_type: '{chat_type}'")
            
            if chat_type == "direct":
                # Get contact name - it's nested in the contact object
                contact_info = chat_info.get("contact", {})
                contact_name = contact_info.get("localDisplayName", "Unknown")
                chat_context = f"DM from {contact_name}"
            elif chat_type == "group":
                # Get group and member information
                group_info = chat_info.get("groupInfo", {})
                chat_dir = chat_item.get("chatDir", {})
                group_member = chat_dir.get("groupMember", {})
                
                # Debug: Log group parsing details
                self.logger.info(f"🔍 GROUP DEBUG: group_info keys: {list(group_info.keys())}")
                self.logger.info(f"🔍 GROUP DEBUG: chatDir keys: {list(chat_dir.keys())}")
                self.logger.info(f"🔍 GROUP DEBUG: groupMember keys: {list(group_member.keys()) if group_member else 'None'}")
                
                # Extract group name and contact name from correct locations
                group_name = group_info.get("localDisplayName", group_info.get("groupName", "Unknown Group"))
                contact_name = group_member.get("localDisplayName", "Unknown Member")
                chat_context = f"Group '{group_name}' from {contact_name}"
                
                self.logger.info(f"🔍 GROUP DEBUG: parsed group_name='{group_name}', contact_name='{contact_name}'")
            else:
                self.logger.warning(f"Unknown chat type: {chat_type}")
                return
            
            self.logger.debug(f"Processing message in {chat_context}")
            
            # Get message content
            content = chat_item.get("content", {})
            msg_content = content.get("msgContent", {})
            msg_type = msg_content.get("type", "unknown")
            
            # Log message type for debugging
            self.logger.debug(f"Processing message type: {msg_type}")
            
            if msg_type == "text":
                await self._handle_text_message(contact_name, content, chat_context, message_data)
            elif msg_type == "link":
                # Handle link messages (treat similar to text for commands)
                await self._handle_text_message(contact_name, content, chat_context, message_data)
            elif msg_type in ["file", "image", "video", "audio", "media", "attachment"]:
                await self._handle_file_message(contact_name, content, msg_type, chat_context)
            else:
                # Log unhandled message types
                if msg_type not in ["text", "link"]:
                    self.logger.warning(f"Unhandled message type: {msg_type}")
                        
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            # Log the full message structure on error for debugging
            self.logger.debug(f"Message data structure: {message_data}")
    
    async def _handle_text_message(self, contact_name: str, content: Dict[str, Any], chat_context: str, message_data: Dict[str, Any]) -> None:
        """Handle text messages and command processing"""
        text = content.get("msgContent", {}).get("text", "")
        
        # Log the message with context
        self.message_logger.info(f"{chat_context}: {text}")
        self.logger.info(f"Received message in {chat_context}: {text[:self.MESSAGE_PREVIEW_LENGTH]}...")
        
        # Check if it's a command
        if self.command_registry.is_command(text):
            await self._process_command(contact_name, text, message_data)
    
    async def _process_command(self, contact_name: str, text: str, message_data: Dict[str, Any]) -> None:
        """Process a command message"""
        try:
            # Try to get plugin manager from the bot instance
            plugin_manager = None
            if hasattr(self, '_bot_instance'):
                plugin_manager = getattr(self._bot_instance, 'plugin_manager', None)
            
            result = await self.command_registry.execute_command(text, contact_name, plugin_manager, message_data)
            if result:
                # For groups, we need to send to the group, not the individual contact
                chat_info = message_data.get("chatInfo", {})
                
                # Use same logic as above to detect group vs direct
                if "groupInfo" in chat_info:
                    # Send to group - we need the group name for this
                    group_info = chat_info.get("groupInfo", {})
                    group_name = group_info.get("localDisplayName", group_info.get("groupName", "Unknown Group"))
                    await self.send_message_callback(group_name, result)
                    self.message_logger.info(f"TO Group '{group_name}': {result[:self.MESSAGE_PREVIEW_LENGTH]}...")
                else:
                    # Send to direct contact
                    await self.send_message_callback(contact_name, result)
        except Exception as e:
            self.logger.error(f"Error executing command: {e}")
            error_msg = f"Error processing command"
            await self.send_message_callback(contact_name, error_msg)
    
    async def _handle_file_message(self, contact_name: str, content: Dict[str, Any], msg_type: str, chat_context: str) -> None:
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


