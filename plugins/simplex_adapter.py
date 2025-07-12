"""
SimpleX Bot Adapter for Universal Plugin System

This adapter allows universal plugins to work with the SimpleX bot by translating
between the universal plugin interface and SimpleX-specific functionality.
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

from .universal_plugin_base import BotAdapter, CommandContext, BotPlatform


class SimplexBotAdapter(BotAdapter):
    """Adapter for SimpleX bot integration with universal plugins"""
    
    def __init__(self, simplex_bot):
        super().__init__(simplex_bot, BotPlatform.SIMPLEX)
        self.logger = logging.getLogger("simplex_adapter")
        # Store reference to bot instance for SimpleX-specific plugins
        self.bot_instance = simplex_bot
    
    async def send_message(self, message: str, context: CommandContext) -> bool:
        """Send a message back to the SimpleX contact"""
        try:
            await self.bot.websocket_manager.send_message(context.user_display_name, message)
            self.logger.debug(f"Sent message to {context.user_display_name}: {message[:100]}...")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message to {context.user_display_name}: {e}")
            return False
    
    async def send_file(self, file_path: str, context: CommandContext, caption: str = "") -> bool:
        """Send a file to the SimpleX contact"""
        try:
            # For SimpleX, we would need to implement file sending through XFTP
            # This is a placeholder for future implementation
            file_path = Path(file_path)
            if not file_path.exists():
                await self.send_message(f"❌ File not found: {file_path.name}", context)
                return False
            
            # For now, just send a message about the file
            file_info = f"📁 File ready: {file_path.name} ({file_path.stat().st_size} bytes)"
            if caption:
                file_info += f"\n💬 {caption}"
            
            # TODO: Implement actual XFTP file sending
            await self.send_message(file_info, context)
            self.logger.info(f"File send requested: {file_path.name} to {context.user_display_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send file to {context.user_display_name}: {e}")
            return False
    
    def normalize_context(self, platform_data: Dict[str, Any]) -> CommandContext:
        """Convert SimpleX message data to universal CommandContext"""
        # Extract SimpleX-specific message data
        chat_item = platform_data.get('chatItem', {})
        chat_info = platform_data.get('chatInfo', {})
        
        # Get contact information
        contact_info = chat_info.get('contact', {})
        contact_name = contact_info.get('localDisplayName', 'Unknown')
        
        # Get message content
        content = chat_item.get('content', {})
        msg_content = content.get('msgContent', {})
        
        # Parse command from text
        text = msg_content.get('text', '').strip()
        if not text.startswith('!'):
            # Not a command
            return CommandContext(
                command="",
                args=[],
                args_raw="",
                user_id=contact_name,
                chat_id=contact_name,  # SimpleX uses contact names as chat IDs
                user_display_name=contact_name,
                platform=BotPlatform.SIMPLEX,
                raw_message=platform_data
            )
        
        # Parse command and arguments
        command_text = text[1:]  # Remove ! prefix
        parts = command_text.split()
        command_name = parts[0] if parts else ""
        args = parts[1:] if len(parts) > 1 else []
        args_raw = ' '.join(args)
        
        return CommandContext(
            command=command_name,
            args=args,
            args_raw=args_raw,
            user_id=contact_name,
            chat_id=contact_name,
            user_display_name=contact_name,
            platform=BotPlatform.SIMPLEX,
            raw_message=platform_data
        )
    
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get SimpleX contact information"""
        try:
            # In SimpleX, user_id is the contact display name
            # We can get basic info from the bot's contact registry
            contacts = getattr(self.bot, 'contacts', {})
            contact_info = contacts.get(user_id, {})
            
            return {
                "display_name": user_id,
                "platform": "simplex",
                "contact_info": contact_info
            }
        except Exception as e:
            self.logger.error(f"Failed to get user info for {user_id}: {e}")
            return {}
    
    async def download_file(self, file_info: Dict[str, Any]) -> Optional[str]:
        """Download a file using SimpleX XFTP"""
        try:
            # Use the bot's file download manager
            if hasattr(self.bot, 'file_download_manager'):
                # Extract file information
                file_name = file_info.get('fileName', 'unknown_file')
                file_size = file_info.get('fileSize', 0)
                
                # Validate file for download
                file_type = self.bot.file_download_manager._get_file_type(file_name)
                
                if self.bot.file_download_manager.validate_file_for_download(
                    file_name, file_size, file_type
                ):
                    # Generate safe filename
                    safe_filename = self.bot.file_download_manager.generate_safe_filename(
                        file_name, "plugin_download", file_type
                    )
                    
                    # Download using XFTP client
                    media_dir = self.bot.file_download_manager.media_path / file_type + 's'
                    download_path = media_dir / safe_filename
                    
                    # TODO: Implement actual XFTP download
                    # For now, return the expected path
                    self.logger.info(f"File download requested: {file_name} -> {download_path}")
                    return str(download_path)
                
                else:
                    self.logger.warning(f"File validation failed: {file_name}")
                    return None
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to download file: {e}")
            return None
    
    def get_bot_info(self) -> Dict[str, Any]:
        """Get information about the SimpleX bot"""
        return {
            "platform": "simplex",
            "bot_name": getattr(self.bot, 'config', {}).get('name', 'SimpleX Bot'),
            "websocket_url": getattr(self.bot, 'websocket_manager', {}).websocket_url if hasattr(self.bot, 'websocket_manager') else None,
            "media_enabled": getattr(self.bot, 'file_download_manager', {}).media_enabled if hasattr(self.bot, 'file_download_manager') else False,
            "xftp_available": hasattr(self.bot, 'xftp_client'),
            "commands_available": len(getattr(self.bot, 'command_registry', {}).list_commands() if hasattr(self.bot, 'command_registry') else [])
        }