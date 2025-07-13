#!/usr/bin/env python3
"""
Message Handler for SimpleX Bot
Handles message processing, routing, and command execution
"""

import logging
import time
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
            
            # Basic content logging for debugging
            self.logger.debug(f"Message content type: {content.get('type', 'unknown')}")
            self.logger.debug(f"Message content keys: {list(msg_content.keys()) if msg_content else 'None'}")
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
            elif msg_type == "voice":
                await self._handle_voice_message(contact_name, content, chat_context, message_data)
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
    
    async def _handle_voice_message(self, contact_name: str, content: Dict[str, Any], chat_context: str, message_data: Dict[str, Any]) -> None:
        """Handle voice messages with STT integration"""
        self.logger.info(f"🎤 VOICE DEBUG: Voice message detected from {contact_name}")
        
        try:
            # Extract voice message info from message structure
            chat_item = message_data.get("chatItem", {})
            file_info = chat_item.get("file", {})
            msg_content = content.get("msgContent", {})
            
            self.logger.info(f"🎤 VOICE DEBUG: Chat item keys: {list(chat_item.keys())}")
            self.logger.info(f"🎤 VOICE DEBUG: File info keys: {list(file_info.keys()) if file_info else 'None'}")
            self.logger.info(f"🎤 VOICE DEBUG: Full file info: {file_info}")
            
            if not file_info:
                self.logger.warning("🎤 VOICE DEBUG: Voice message has no file information")
                return
            
            # Extract file details
            file_name = file_info.get("fileName", "unknown_voice.m4a")
            file_size = file_info.get("fileSize", 0)
            file_status = file_info.get("fileStatus", {})
            file_protocol = file_info.get("fileProtocol", "unknown")
            duration = msg_content.get("duration", 0)
            
            self.logger.info(f"🎤 VOICE DEBUG: File name: {file_name}")
            self.logger.info(f"🎤 VOICE DEBUG: File size: {file_size} bytes")
            self.logger.info(f"🎤 VOICE DEBUG: File status: {file_status}")
            self.logger.info(f"🎤 VOICE DEBUG: File protocol: {file_protocol}")
            self.logger.info(f"🎤 VOICE DEBUG: Duration: {duration}s")
            
            self.logger.info(f"Voice message: {file_name} ({file_size} bytes, {duration}s duration)")
            self.message_logger.info(f"VOICE FROM {contact_name}: {file_name} ({duration}s)")
            
            # Check media download status
            self.logger.info(f"🎤 VOICE DEBUG: Media downloads enabled: {self.file_download_manager.media_enabled}")
            if not self.file_download_manager.media_enabled:
                self.logger.warning("🎤 VOICE DEBUG: Media downloads disabled - voice files cannot be downloaded for STT")
            
            # Check if we have a plugin manager with STT plugin
            if hasattr(self, '_bot_instance'):
                bot_instance = self._bot_instance
                if hasattr(bot_instance, 'plugin_manager'):
                    plugin_manager = bot_instance.plugin_manager
                    
                    # Look for STT plugin
                    stt_plugin = None
                    for plugin in plugin_manager.plugins.values():
                        if hasattr(plugin, 'handle_audio_message') and plugin.name == 'stt_wyoming':
                            stt_plugin = plugin
                            break
                    
                    if stt_plugin:
                        self.logger.info("Found STT plugin, processing voice message...")
                        
                        # Create context for the STT plugin
                        # Use same logic as _process_command to determine chat target
                        chat_info = message_data.get("chatInfo", {})
                        if "groupInfo" in chat_info:
                            # Group message - need group context
                            group_info = chat_info.get("groupInfo", {})
                            group_name = group_info.get("localDisplayName", group_info.get("groupName", "Unknown Group"))
                            chat_id = group_name
                        else:
                            # Direct message
                            chat_id = contact_name
                        
                        # Create command context for STT plugin
                        from plugins.universal_plugin_base import CommandContext, BotPlatform
                        context = CommandContext(
                            command="auto_transcribe",
                            args=[],
                            args_raw="",
                            user_id=contact_name,
                            user_display_name=contact_name,
                            chat_id=chat_id,
                            platform=BotPlatform.SIMPLEX,
                            raw_message=message_data
                        )
                        
                        # Process the voice message with STT plugin
                        await stt_plugin.handle_audio_message(file_info, context)
                    else:
                        self.logger.info("No STT plugin found, acknowledging voice message")
                        await self.send_message_callback(contact_name, f"🎤 Voice message received: {file_name} ({duration}s)")
                else:
                    self.logger.info("No plugin manager available")
                    await self.send_message_callback(contact_name, f"🎤 Voice message received: {file_name} ({duration}s)")
            else:
                self.logger.info("No bot instance available for plugin integration")
                await self.send_message_callback(contact_name, f"🎤 Voice message received: {file_name} ({duration}s)")
                
        except Exception as e:
            self.logger.error(f"Error handling voice message: {e}")
            import traceback
            self.logger.error(f"Voice message error traceback: {traceback.format_exc()}")
            await self.send_message_callback(contact_name, "Error processing voice message")

    async def _handle_file_message(self, contact_name: str, content: Dict[str, Any], msg_type: str, chat_context: str) -> None:
        """Handle file/media messages"""
        self.logger.info(f"📁 DOWNLOAD DEBUG: File message detected: {msg_type}")
        
        # Clean base64 data from content structure for logging
        content_for_log = self.file_download_manager.clean_content_for_logging(content)
        self.logger.info(f"📁 DOWNLOAD DEBUG: Content structure: {content_for_log}")
        
        self.logger.info(f"📁 DOWNLOAD DEBUG: Media enabled: {self.file_download_manager.media_enabled}")
        if not self.file_download_manager.media_enabled:
            self.logger.warning("📁 DOWNLOAD DEBUG: Media downloads disabled, skipping file")
            return
        
        try:
            file_info = content.get("msgContent", {})
            inner_msg_type = file_info.get("type", "")
            self.logger.info(f"📁 DOWNLOAD DEBUG: File info keys: {list(file_info.keys())}")
            self.logger.info(f"📁 DOWNLOAD DEBUG: Inner message type: {inner_msg_type}")
            
            # Extract file information
            self.logger.info("📁 DOWNLOAD DEBUG: Extracting file information...")
            file_name, file_size, file_type = self.file_download_manager.extract_file_info_from_content(
                file_info, inner_msg_type, contact_name
            )
            self.logger.info(f"📁 DOWNLOAD DEBUG: Extracted - name: {file_name}, size: {file_size}, type: {file_type}")
            
            # Validate file for download
            self.logger.info("📁 DOWNLOAD DEBUG: Validating file for download...")
            is_valid = self.file_download_manager.validate_file_for_download(file_name, file_size, file_type)
            self.logger.info(f"📁 DOWNLOAD DEBUG: File validation result: {is_valid}")
            
            if not is_valid:
                from config_manager import parse_file_size
                max_size = parse_file_size(self.file_download_manager.media_config.get('max_file_size', '100MB'))
                self.logger.warning(f"📁 DOWNLOAD DEBUG: File validation failed - size: {file_size}, max: {max_size}")
                if file_size > max_size:
                    await self.send_message_callback(contact_name, f"File {file_name} is too large to download")
                return
            
            # Log the file message
            self.message_logger.info(f"FILE FROM {contact_name}: {file_name} ({file_size} bytes)")
            self.logger.info(f"📁 DOWNLOAD DEBUG: File approved for download: {file_name}")
            
            # Attempt to download the file using the restored download logic
            self.logger.info("📁 DOWNLOAD DEBUG: Starting file download process...")
            download_success = await self._download_file(contact_name, file_info, file_type, inner_msg_type)
            
            if download_success == "acknowledged":
                self.logger.info(f"📁 DOWNLOAD DEBUG: Video/audio message acknowledged - waiting for XFTP file description: {file_name}")
                await self.send_message_callback(contact_name, f"📹 Video received - downloading via XFTP...")
            elif download_success == "thumbnail_skipped":
                self.logger.info(f"📁 DOWNLOAD DEBUG: Thumbnail skipped for {file_name} - waiting for XFTP")
                # No message sent - wait for XFTP download
            elif download_success:
                self.logger.info(f"📁 DOWNLOAD DEBUG: Successfully downloaded file: {file_name}")
                await self.send_message_callback(contact_name, f"✓ Downloaded: {file_name}")
            else:
                self.logger.error(f"📁 DOWNLOAD DEBUG: Failed to download file: {file_name}")
                await self.send_message_callback(contact_name, f"✗ Failed to download: {file_name}")
            
        except Exception as e:
            self.logger.error(f"📁 DOWNLOAD DEBUG: Error handling file message: {e}")
            import traceback
            self.logger.error(f"📁 DOWNLOAD DEBUG: Traceback: {traceback.format_exc()}")
            await self.send_message_callback(contact_name, f"Error processing file: {str(e)}")

    async def _download_file(self, contact_name: str, file_info: Dict, file_type: str, inner_msg_type: str = "file") -> bool:
        """Download file using available methods (direct data or XFTP)"""
        try:
            self.logger.info(f"🔍 DOWNLOAD: Starting file download - contact: {contact_name}, type: {file_type}, inner_msg_type: {inner_msg_type}")
            self.logger.info(f"🔍 DOWNLOAD: File info keys: {list(file_info.keys())}")
            
            # Clean base64 data for logging
            file_info_for_log = dict(file_info)
            if 'image' in file_info_for_log and isinstance(file_info_for_log['image'], str):
                if file_info_for_log['image'].startswith('data:image/'):
                    header_part = file_info_for_log['image'].split(',')[0] if ',' in file_info_for_log['image'] else file_info_for_log['image']
                    file_info_for_log['image'] = f"{header_part},<base64_truncated>"
            
            self.logger.info(f"🔍 DOWNLOAD: Full file_info: {file_info_for_log}")
            
            # Handle SimpleX image format - Skip thumbnails, wait for XFTP
            if inner_msg_type == "image" and "image" in file_info:
                image_data_url = file_info.get("image", "")
                file_name = self.file_download_manager._generate_image_filename(contact_name, image_data_url)
                file_size = self.file_download_manager._calculate_data_url_size(image_data_url)
                
                self.logger.info(f"🔍 DOWNLOAD: Processing SimpleX image - name: {file_name}, size: {file_size}")
                self.logger.info(f"🔍 DOWNLOAD: This is an embedded image (thumbnail), skipping - waiting for XFTP")
                
                # Skip thumbnail download, return acknowledgment
                return "thumbnail_skipped"
            
            # For other file types, check for various download methods
            # Generate filename and path
            file_name = file_info.get("fileName", f"unknown_file_{int(time.time())}")
            file_size = file_info.get("fileSize", 0)
            
            # Generate safe filename and determine storage path
            safe_filename = self.file_download_manager.generate_safe_filename(file_name, contact_name, file_type)
            
            # Determine storage directory based on file type
            if file_type == 'audio':
                storage_dir = self.file_download_manager.media_path / 'audio'
            else:
                storage_dir = self.file_download_manager.media_path / f"{file_type}s"
            storage_dir.mkdir(exist_ok=True)
            
            file_path = storage_dir / safe_filename
            
            self.logger.info(f"🔍 DOWNLOAD: Target path: {file_path}")
            
            # Method 1: Skip thumbnails - only use XFTP
            if "fileData" in file_info:
                self.logger.info(f"🔍 DOWNLOAD: Direct file data (thumbnail) detected - skipping, waiting for XFTP")
                return "thumbnail_skipped"
            
            # Method 2: Try XFTP download using file ID/hash
            elif "fileId" in file_info or "fileHash" in file_info:
                self.logger.info(f"🔍 DOWNLOAD: Using Method 2 - XFTP download (large file)")
                
                if hasattr(self, '_bot_instance') and hasattr(self._bot_instance, 'xftp_client'):
                    xftp_client = self._bot_instance.xftp_client
                    self.logger.info(f"🔍 DOWNLOAD: XFTP client available: {xftp_client is not None}")
                    
                    if xftp_client:
                        xftp_success = await self._download_via_xftp(file_info, file_path, file_name, xftp_client)
                        if xftp_success:
                            self.logger.info(f"🔍 DOWNLOAD: XFTP download successful")
                            return True
                
                self.logger.warning(f"🔍 DOWNLOAD: XFTP download failed for {file_name}")
                return False
            
            # Method 3: Handle video/audio messages without XFTP indicators
            else:
                # For video/audio messages, the initial message only contains thumbnail
                # The actual file will arrive later via rcvFileDescrReady event
                if inner_msg_type in ["video", "audio", "voice"]:
                    self.logger.info(f"📹 Video/audio message received - waiting for XFTP file description")
                    # Don't attempt download - just acknowledge receipt
                    # The rcvFileDescrReady event will handle the actual download
                    return "acknowledged"  # Special return value to indicate waiting for XFTP
                else:
                    # For other file types without XFTP indicators, assume it's a thumbnail - skip
                    self.logger.info(f"🔍 DOWNLOAD: File without XFTP indicators detected - likely thumbnail, skipping: {file_name} (type: {inner_msg_type})")
                    return "thumbnail_skipped"
                
        except Exception as e:
            self.logger.error(f"🔍 DOWNLOAD: Error in file download: {e}")
            # If it's likely a thumbnail parsing error, skip instead of failing
            if "fileData" in file_info or ("image" in file_info and inner_msg_type == "image"):
                self.logger.info(f"🔍 DOWNLOAD: Error likely from thumbnail processing - skipping")
                return "thumbnail_skipped"
            return False

    async def _download_via_xftp(self, file_info: Dict, file_path, original_name: str, xftp_client) -> bool:
        """Download file via XFTP using file ID or hash"""
        try:
            self.logger.info(f"🔥 XFTP: _download_via_xftp called for {original_name}")
            
            # Check if XFTP client is available
            if not xftp_client:
                self.logger.warning(f"🔥 XFTP: XFTP client not initialized for {original_name}")
                return False
            
            # Check for new XFTP format (file description text)
            file_descr_text = file_info.get("fileDescrText")
            if file_descr_text:
                self.logger.info(f"🔥 XFTP: Using XFTP file description format")
                file_size = file_info.get("fileSize", 0)
                
                self.logger.info(f"🔥 XFTP: File description length: {len(file_descr_text)} chars, Size: {file_size}")
                self.logger.info(f"🔥 XFTP: Starting XFTP download for {original_name} (Size: {file_size})")
                
                # Use XFTPClient with file description text
                self.logger.info(f"🔥 XFTP: Calling xftp_client.download_file_with_description")
                success = await xftp_client.download_file_with_description(
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
                
                self.logger.info(f"🔥 XFTP: File parameters - ID: {file_id}, Hash: {file_hash}, Size: {file_size}")
                
                if not file_id:
                    self.logger.warning(f"🔥 XFTP: No file ID available for XFTP download: {original_name}")
                    return False
                
                self.logger.info(f"🔥 XFTP: Starting XFTP download for {original_name} (ID: {file_id}, Size: {file_size})")
                
                # Use XFTPClient to download the file
                self.logger.info(f"🔥 XFTP: Calling xftp_client.download_file with output_path: {file_path}")
                success = await xftp_client.download_file(
                    file_id=file_id,
                    file_hash=file_hash,
                    file_size=file_size,
                    file_name=original_name,
                    output_path=str(file_path)
                )
            
            if success:
                self.logger.info(f"🔥 XFTP: XFTP download completed successfully: {original_name}")
                return True
            else:
                self.logger.warning(f"🔥 XFTP: XFTP download failed: {original_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"🔥 XFTP: Unexpected error in XFTP download for {original_name}: {e}")
            return False

    async def handle_file_descriptor_ready(self, data: Dict):
        """Handle rcvFileDescrReady event with XFTP file metadata"""
        try:
            self.logger.info(f"🎯 XFTP: Processing file descriptor ready event")
            self.logger.info(f"🎯 XFTP: Event data keys: {list(data.keys())}")
            
            # Extract file information from the event
            file_info = data.get("rcvFileInfo", {})
            if not file_info:
                # Try alternative key names
                file_info = data.get("rcvFileDescr", {})
                if not file_info:
                    file_info = data.get("rcvFileTransfer", {})
                    if not file_info:
                        self.logger.warning(f"🎯 XFTP: No file info found in event data")
                        self.logger.warning(f"🎯 XFTP: Available keys: {list(data.keys())}")
                        return
                    else:
                        self.logger.info(f"🎯 XFTP: Found file info in rcvFileTransfer")
                else:
                    self.logger.info(f"🎯 XFTP: Found file info in rcvFileDescr")
            
            # Extract the XFTP file description text
            file_descr_text = file_info.get("fileDescrText", "")
            if not file_descr_text:
                # Try alternative key names
                file_descr_text = file_info.get("description", "")
                if not file_descr_text:
                    file_descr_text = file_info.get("fileDescription", "")
            
            if not file_descr_text:
                self.logger.warning(f"🎯 XFTP: No file description text found")
                self.logger.warning(f"🎯 XFTP: File info content: {file_info}")
                return
            
            # Extract contact information if available
            contact_name = "unknown_contact"
            
            # Log the full data structure to debug contact extraction
            self.logger.info(f"🎯 XFTP DEBUG: Full event data structure:")
            for key, value in data.items():
                if key not in ['rcvFileDescr', 'rcvFileTransfer']:  # Skip large XFTP data
                    self.logger.info(f"🎯 XFTP DEBUG:   {key}: {value}")
            
            # Try multiple sources for contact info
            if "chatItem" in data:
                chat_item = data["chatItem"]
                self.logger.info(f"🎯 XFTP DEBUG: chatItem keys: {list(chat_item.keys())}")
                chat_info = chat_item.get("chatInfo", {})
                self.logger.info(f"🎯 XFTP DEBUG: chatInfo: {chat_info}")
                
                # Check if it's a direct contact
                if "contact" in chat_info:
                    contact_name = chat_info["contact"].get("localDisplayName", "unknown_contact")
                    self.logger.info(f"🎯 XFTP: Found contact name from chatItem.chatInfo.contact: {contact_name}")
                
                # Check if it's a group message
                elif "groupInfo" in chat_info:
                    # For group messages, get the actual sender from chatItem.chatItem.chatDir.groupMember
                    chat_item_inner = chat_item.get("chatItem", {})
                    chat_dir = chat_item_inner.get("chatDir", {})
                    group_member = chat_dir.get("groupMember", {})
                    if group_member:
                        contact_name = group_member.get("localDisplayName", "unknown_contact")
                        self.logger.info(f"🎯 XFTP: Found contact name from chatItem.chatItem.chatDir.groupMember: {contact_name}")
                    else:
                        self.logger.warning(f"🎯 XFTP: Group message but no groupMember found in chatDir: {chat_dir}")
            
            # Fallback: try user field
            if contact_name == "unknown_contact" and "user" in data:
                user_info = data["user"]
                self.logger.info(f"🎯 XFTP DEBUG: user field: {user_info}")
                contact_name = user_info.get("localDisplayName", user_info.get("displayName", "unknown_contact"))
                self.logger.info(f"🎯 XFTP: Found contact name from user field: {contact_name}")
            
            self.logger.info(f"🎯 XFTP: Final contact name: {contact_name}")
            
            # Parse file information from description text
            file_size = self._parse_xftp_file_size(file_descr_text)
            
            # Use a temporary filename for initial download - actual filename will be determined after download
            temp_file_name = f"xftp_download_{int(time.time())}"
            
            self.logger.info(f"🎯 XFTP: Ready to download - temp name: {temp_file_name}, size: {file_size}")
            self.logger.info(f"🎯 XFTP: XFTP description available: {len(file_descr_text)} chars")
            
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
                self.logger.info(f"🎯 XFTP: File download successful: {actual_filename} at {actual_path}")
                await self.send_message_callback(contact_name, f"✓ Downloaded via XFTP: {actual_filename}")
            else:
                self.logger.error(f"🎯 XFTP: File download failed: {temp_file_name}")
                await self.send_message_callback(contact_name, f"✗ XFTP download failed")
                
        except Exception as e:
            self.logger.error(f"🎯 XFTP: Error handling file descriptor ready: {e}")
            import traceback
            self.logger.error(f"🎯 XFTP: Traceback: {traceback.format_exc()}")

    async def _download_via_xftp_with_filename_detection(self, file_info: Dict, contact_name: str):
        """Download file via XFTP and return actual filename and path"""
        try:
            file_size = file_info.get('fileSize', 0)
            file_descr_text = file_info.get('fileDescrText', '')
            
            if not file_descr_text:
                self.logger.error("🎯 XFTP: No XFTP file description provided")
                return None
            
            self.logger.info(f"🔥 XFTP: Starting XFTP download with filename detection")
            
            # Get XFTP client from bot instance
            if not (hasattr(self, '_bot_instance') and hasattr(self._bot_instance, 'xftp_client')):
                self.logger.error("🎯 XFTP: XFTP client not available")
                return None
            
            xftp_client = self._bot_instance.xftp_client
            if not xftp_client:
                self.logger.error("🎯 XFTP: XFTP client not initialized")
                return None
            
            # Use the new XFTP client method that preserves filenames
            import tempfile
            with tempfile.TemporaryDirectory(prefix="xftp_download_") as temp_dir:
                
                # Download using XFTP client with filename detection
                success, actual_filename, file_path = await xftp_client.download_file_with_description_get_filename(
                    file_description=file_descr_text,
                    file_size=file_size,
                    temp_dir=temp_dir
                )
                
                if not success or not actual_filename:
                    self.logger.error("🎯 XFTP: XFTP download failed or no filename detected")
                    return None
                
                self.logger.info(f"🔥 XFTP: Successfully detected actual filename: {actual_filename}")
                
                # Determine file type and storage directory
                file_type = self.file_download_manager._get_file_type(actual_filename)
                safe_filename = self.file_download_manager.generate_safe_filename(actual_filename, contact_name, file_type)
                
                # Determine storage directory
                if file_type == 'audio':
                    storage_dir = self.file_download_manager.media_path / 'audio'
                else:
                    storage_dir = self.file_download_manager.media_path / f"{file_type}s"
                storage_dir.mkdir(exist_ok=True)
                
                final_path = storage_dir / safe_filename
                
                # Move file to final location
                import shutil
                shutil.move(file_path, str(final_path))
                
                self.logger.info(f"🔥 XFTP: File moved to final location: {final_path}")
                
                return (actual_filename, str(final_path))
                
        except Exception as e:
            self.logger.error(f"🎯 XFTP: Error in XFTP download with filename detection: {e}")
            import traceback
            self.logger.error(f"🎯 XFTP: Traceback: {traceback.format_exc()}")
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
            
            # Fallback - look for just numbers
            size_match = re.search(r'(\d+)', file_descr_text)
            if size_match:
                return int(size_match.group(1))
            
            return 0
            
        except Exception as e:
            self.logger.error(f"Error parsing XFTP file size: {e}")
            return 0


