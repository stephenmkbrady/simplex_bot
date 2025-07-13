#!/usr/bin/env python3
"""
SimpleX Chat Bot - Refactored with Clean Architecture
Main orchestrator using dependency injection
"""

import asyncio
import argparse
import logging
import signal
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Import configuration manager
from config_manager import ConfigManager

# Import refactored components
from file_download_manager import FileDownloadManager
from message_handler import MessageHandler
from websocket_manager import WebSocketManager
from xftp_client import XFTPClient

# Import universal plugin system
from plugins.universal_plugin_manager import UniversalPluginManager
from plugins.simplex_adapter import SimplexBotAdapter

# Import admin manager
from admin_manager import AdminManager

# Import invite manager
from invite_manager import InviteManager

# Constants
DEFAULT_MAX_MESSAGE_LENGTH = 4096
DEFAULT_RATE_LIMIT_MESSAGES = 10
DEFAULT_RATE_LIMIT_WINDOW = 60  # seconds
DEFAULT_RETENTION_DAYS = 30
BYTES_PER_MB = 1024 * 1024
BYTES_PER_GB = 1024 * 1024 * 1024
BYTES_PER_KB = 1024


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
        import logging.handlers
        
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
        import logging.handlers
        
        # Application log handler
        app_handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.log_dir / "bot.log",
            when='midnight',
            interval=1,
            backupCount=self.config.get('log_retention_days', DEFAULT_RETENTION_DAYS)
        )
        app_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        
        # Message log handler
        msg_handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.log_dir / "messages.log",
            when='midnight',
            interval=1,
            backupCount=self.config.get('log_retention_days', DEFAULT_RETENTION_DAYS)
        )
        msg_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Add handlers
        self.app_logger.addHandler(app_handler)
        self.app_logger.addHandler(console_handler)
        self.message_logger.addHandler(msg_handler)


class CommandRegistry:
    """Registry for bot commands with extensible architecture"""
    
    def __init__(self, logger: logging.Logger, admin_manager: AdminManager, bot_instance=None):
        self.logger = logger
        self.admin_manager = admin_manager
        self.bot_instance = bot_instance
        self.commands = {}
        self._register_default_commands()
    
    def _register_default_commands(self):
        """Register default bot commands"""
        self.commands = {
            # Core help command that integrates info functionality
            'help': self._help_command,
            # Note: Other commands moved to plugins:
            # - ping, status, uptime, plugins, etc. -> Core Plugin
            # - invite, debug, contacts, groups, admin, reload_admin, stats -> SimpleX Plugin
        }
    
    def register_command(self, name: str, handler):
        """Register a new command"""
        self.commands[name] = handler
        self.logger.info(f"Registered command: {name}")
    
    def get_command(self, name: str):
        """Get a command handler"""
        return self.commands.get(name)
    
    def list_commands(self) -> list:
        """List all available commands"""
        return list(self.commands.keys())
    
    def is_command(self, text: str) -> bool:
        """Check if text is a command"""
        if not text.strip():
            return False
        
        # Check if starts with command prefix (default: !)
        text = text.strip()
        if text.startswith('!'):
            command_part = text[1:].split()[0] if text[1:].split() else ""
            # Check both legacy commands and assume plugin commands exist
            # Plugin commands will be handled in execute_command
            return command_part in self.commands or len(command_part) > 0
        
        return False
    
    async def execute_command(self, text: str, contact_name: str, plugin_manager=None, message_data: Dict[str, Any] = None) -> Optional[str]:
        """Execute a command and return the response"""
        if not self.is_command(text):
            return None
        
        # Parse command and arguments
        command_text = text[1:]  # Remove ! prefix
        parts = command_text.split()
        command_name = parts[0] if parts else ""
        args = parts[1:] if len(parts) > 1 else []
        
        # Use contact_name for admin checks (simple and reliable)
        user_identifier = contact_name
        
        # Check admin permissions before executing any command
        if not self.admin_manager.can_run_command(user_identifier, command_name):
            denial_message = self.admin_manager.get_denied_message(user_identifier, command_name)
            self.logger.warning(f"Access denied for user {contact_name} to command {command_name}")
            return denial_message
        
        # First try plugin manager if available
        if plugin_manager:
            try:
                # Use the adapter's normalize_context method to create proper context
                if hasattr(plugin_manager, 'adapter') and plugin_manager.adapter:
                    # Create a fake message structure that normalize_context expects
                    fake_message_data = {
                        'chatInfo': message_data.get('chatInfo', {}),
                        'chatItem': {
                            'content': {
                                'msgContent': {
                                    'text': f"!{command_name} {' '.join(args)}"
                                }
                            }
                        }
                    }
                    context = plugin_manager.adapter.normalize_context(fake_message_data)
                else:
                    # Fallback to original method if adapter not available
                    from plugins.universal_plugin_base import CommandContext, BotPlatform
                    chat_id = contact_name  # Fallback to contact name
                    if message_data:
                        raw_message = message_data
                    else:
                        raw_message = {}
                    
                    context = CommandContext(
                        command=command_name,
                        args=args,
                        args_raw=' '.join(args),
                        user_id=contact_name,
                        chat_id=chat_id,
                        user_display_name=contact_name,
                        platform=BotPlatform.SIMPLEX,
                        raw_message=raw_message
                    )
                
                plugin_result = await plugin_manager.handle_command(context)
                if plugin_result is not None:
                    return plugin_result
            except Exception as e:
                self.logger.error(f"Error in plugin manager: {e}")
                # Fall through to legacy commands
        
        # Fall back to legacy command registry
        handler = self.get_command(command_name)
        if not handler:
            return f"Unknown command: {command_name}"
        
        try:
            # For backward compatibility, we'll capture the send_message_callback
            # and return the response instead of calling it directly
            response_capture = {"response": None}
            
            async def capture_callback(contact: str, message: str):
                response_capture["response"] = message
            
            # Call handler with standard arguments
            await handler(args, contact_name, capture_callback)
            return response_capture.get("response", "Command executed")
            
        except Exception as e:
            self.logger.error(f"Error executing command {command_name}: {e}")
            return f"Error executing command: {command_name}"
    
    async def _help_command(self, args: list, contact_name: str, send_message_callback):
        """Comprehensive help command that includes bot info and all available commands"""
        import yaml
        from pathlib import Path
        from datetime import datetime
        
        # Read version info from version.yml
        version_file = Path("version.yml")
        with open(version_file, 'r') as f:
            version_data = yaml.safe_load(f)
        
        bot_info = version_data['bot']
        bot_name = bot_info['name']
        bot_version = bot_info['version']
        bot_description = bot_info['description']
        platform = bot_info['platform']
        
        # Check plugin system status
        plugin_status = '✅ Active' if hasattr(self.bot_instance, 'plugin_manager') else '❌ Not Available'
        plugin_count = 0
        all_commands = {}
        
        if hasattr(self.bot_instance, 'plugin_manager'):
            plugin_manager = getattr(self.bot_instance, 'plugin_manager')
            plugin_count = len(plugin_manager.plugins)
            
            # Get commands from all plugins
            for plugin_name, plugin in plugin_manager.plugins.items():
                if plugin.enabled:
                    commands = plugin.get_commands()
                    if commands:
                        all_commands[plugin_name] = {
                            'commands': commands,
                            'description': plugin.description,
                            'version': plugin.version
                        }
        
        # Start building help text with bot info
        help_text = f"""🤖 **{bot_name} Help & Information**

**Bot Details:**
• Version: {bot_version}
• Platform: {platform} 
• Status: ✅ Running
• Description: {bot_description}

**System Status:**
• Plugin System: {plugin_status}
• Loaded Plugins: {plugin_count}
• Total Commands: {sum(len(info['commands']) for info in all_commands.values()) + 1}

**Core Commands:**
• `!help` - Show this help and bot information

**Available Plugin Commands:**"""
        
        # Add plugin commands
        for plugin_name, plugin_info in all_commands.items():
            commands_str = ', '.join([f"`!{cmd}`" for cmd in plugin_info['commands']])
            help_text += f"\n\n**{plugin_name.title()} Plugin** (v{plugin_info['version']}):\n"
            help_text += f"*{plugin_info['description']}*\n"
            help_text += f"Commands: {commands_str}"
        
        help_text += f"""

**Tips:**
• All commands start with `!`
• Commands are case-sensitive
• Use `!plugins` for detailed plugin status
• Use `!status` for comprehensive bot information"""
        
        await send_message_callback(contact_name, help_text)


class SimplexChatBot:
    """Main bot orchestrator using dependency injection"""
    
    def __init__(self, config_path: str = "config.yml", cli_args: Optional[argparse.Namespace] = None):
        # Load configuration
        self.cli_args = cli_args
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.get_bot_config()
        
        # Setup logging
        self.logger_manager = DailyRotatingLogger(
            "SimplexChatBot", 
            "SimplexChatMessages", 
            self.config.get('logging', {})
        )
        self.logger = self.logger_manager.app_logger
        self.message_logger = self.logger_manager.message_logger
        
        # Initialize admin manager
        self.admin_manager = AdminManager(logger=self.logger)
        
        # Initialize invite manager
        self.invite_manager = InviteManager(logger=self.logger)
        
        # Initialize components with dependency injection
        self._initialize_components()
        
        # Initialize plugin system
        self._initialize_plugin_system()
        
        # Bot state
        self.running = False
        self.contacts = {}
        self.contact_requests = {}
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger.info("SimplexChatBot initialized with clean architecture")
    
    def _initialize_components(self):
        """Initialize all components with proper dependency injection"""
        # Initialize XFTP client
        xftp_config = self.config.get('xftp', {})
        self.xftp_client = XFTPClient(
            cli_path=xftp_config.get('executable_path', '/usr/local/bin/xftp'),
            temp_dir=xftp_config.get('temp_dir', './temp/xftp'),
            config=xftp_config,
            logger=self.logger
        )
        
        # Initialize file download manager
        media_config = self.config.get('media', {})
        self.file_download_manager = FileDownloadManager(
            media_config=media_config,
            xftp_client=self.xftp_client,
            logger=self.logger
        )
        
        # Initialize WebSocket manager
        websocket_url = self.config.get('websocket_url', 'ws://localhost:3030')
        self.websocket_manager = WebSocketManager(
            websocket_url=websocket_url,
            logger=self.logger
        )
        
        # Initialize command registry (will set bot_instance after creation)
        self.command_registry = CommandRegistry(self.logger, self.admin_manager)
        
        # Initialize message handler
        self.message_handler = MessageHandler(
            command_registry=self.command_registry,
            file_download_manager=self.file_download_manager,
            send_message_callback=self.websocket_manager.send_message,
            logger=self.logger,
            message_logger=self.message_logger
        )
        
        # Pass bot instance to message handler and command registry for plugin access
        self.message_handler._bot_instance = self
        self.command_registry.bot_instance = self
        
        # Register WebSocket message handlers
        self.websocket_manager.register_message_handler('newChatItem', self._handle_new_chat_item)
        self.websocket_manager.register_message_handler('newChatItems', self._handle_new_chat_items)
        self.websocket_manager.register_message_handler('contactRequest', self._handle_contact_request)
        self.websocket_manager.register_message_handler('contactConnected', self._handle_contact_connected)
        self.websocket_manager.register_message_handler('receivedGroupInvitation', self._handle_group_invitation)
        self.websocket_manager.register_message_handler('memberJoinedGroup', self._handle_member_joined_group)
    
    def _initialize_plugin_system(self):
        """Initialize the universal plugin system"""
        try:
            # Create plugin manager with main bot logger
            self.plugin_manager = UniversalPluginManager("plugins/external", logger=self.logger)
            
            # Create SimpleX adapter
            self.plugin_adapter = SimplexBotAdapter(self)
            
            self.logger.info("Plugin system initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize plugin system: {e}")
            self.plugin_manager = None
            self.plugin_adapter = None
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    async def start(self):
        """Start the bot"""
        self.logger.info("Starting SimplexChatBot...")
        
        # Connect to WebSocket
        if not await self.websocket_manager.connect():
            self.logger.error("Failed to connect to SimpleX Chat CLI")
            return False
        
        self.running = True
        
        # Load plugins after successful connection
        if self.plugin_manager and self.plugin_adapter:
            try:
                await self.plugin_manager.discover_and_load_plugins(self.plugin_adapter)
                self.logger.info("Plugins loaded successfully")
                
                # Start hot reload monitoring
                self.logger.debug("🔧 Starting hot reload monitoring...")
                print("🔧 DEBUG: About to call start_hot_reloading()")
                try:
                    await self.plugin_manager.start_hot_reloading()
                    print("🔧 DEBUG: start_hot_reloading() completed successfully")
                    self.logger.debug("✅ Hot reload monitoring started successfully")
                except Exception as e:
                    print(f"🔧 DEBUG: start_hot_reloading() failed: {e}")
                    import traceback
                    print(f"🔧 DEBUG: Traceback: {traceback.format_exc()}")
                    raise
                
            except Exception as e:
                self.logger.error(f"Failed to load plugins: {e}")
        
        self.logger.info("SimplexChatBot started successfully")
        
        # Start listening for messages with reconnection handling
        self.logger.info("🔄 MAIN LOOP: Starting main message listening loop")
        while self.running:
            try:
                # Check if CLI restart is needed due to corruption
                if getattr(self.websocket_manager, 'cli_restart_needed', False):
                    self.logger.warning("🔄 MAIN LOOP: CLI restart needed, attempting recovery...")
                    if await self.websocket_manager.restart_cli_process():
                        self.logger.info("🔄 MAIN LOOP: CLI restart successful, resuming")
                    else:
                        self.logger.error("🔄 MAIN LOOP: CLI restart failed, continuing with reconnection")
                
                self.logger.info("🔄 MAIN LOOP: Calling listen_for_messages()")
                await self.websocket_manager.listen_for_messages()
                
                # If we reach here, the connection was closed gracefully
                if self.running:
                    # Check if this was due to CLI corruption
                    if getattr(self.websocket_manager, 'cli_restart_needed', False):
                        self.logger.info("🔄 MAIN LOOP: Connection lost due to CLI corruption, restarting CLI...")
                        if await self.websocket_manager.restart_cli_process():
                            self.logger.info("🔄 MAIN LOOP: CLI restart successful, resuming message listening")
                            continue
                        else:
                            self.logger.error("🔄 MAIN LOOP: CLI restart failed, trying normal reconnection")
                    
                    self.logger.info("🔄 MAIN LOOP: WebSocket connection lost, attempting to reconnect...")
                    if await self.websocket_manager.connect():
                        self.logger.info("🔄 MAIN LOOP: Successfully reconnected, resuming message listening")
                        continue
                    else:
                        self.logger.error("🔄 MAIN LOOP: Failed to reconnect, stopping bot")
                        break
                else:
                    # Bot is shutting down
                    self.logger.info("🔄 MAIN LOOP: Bot shutting down, exiting message loop")
                    break
                    
            except Exception as e:
                self.logger.error(f"🔄 MAIN LOOP: Exception in message listening loop: {type(e).__name__}: {e}")
                import traceback
                self.logger.error(f"🔄 MAIN LOOP: Traceback: {traceback.format_exc()}")
                if self.running:
                    self.logger.info("🔄 MAIN LOOP: Waiting 5 seconds before retry...")
                    await asyncio.sleep(5)  # Wait before retry
                else:
                    break
        
        return True
    
    async def stop(self):
        """Stop the bot"""
        self.logger.info("Stopping SimplexChatBot...")
        self.running = False
        
        # Cleanup plugin system
        if hasattr(self, 'plugin_manager') and self.plugin_manager:
            try:
                await self.plugin_manager.cleanup()
                self.logger.info("Plugin system cleaned up")
            except Exception as e:
                self.logger.error(f"Error cleaning up plugin system: {e}")
        
        # Disconnect WebSocket
        await self.websocket_manager.disconnect()
        
        self.logger.info("SimplexChatBot stopped")
    
    async def _handle_new_chat_item(self, response_data: Dict[str, Any]):
        """Handle new chat item messages"""
        try:
            await self.message_handler.process_message(response_data)
        except Exception as e:
            self.logger.error(f"Error handling new chat item: {e}")
    
    async def _handle_new_chat_items(self, response_data: Dict[str, Any]):
        """Handle multiple new chat items"""
        try:
            chat_items = response_data.get('chatItems', [])
            for item in chat_items:
                await self.message_handler.process_message(item)
        except Exception as e:
            self.logger.error(f"Error handling new chat items: {e}")
    
    async def _handle_contact_request(self, response_data: Dict[str, Any]):
        """Handle incoming contact requests"""
        try:
            contact_request = response_data.get('contactRequest', {})
            contact_name = contact_request.get('localDisplayName', 'Unknown')
            
            self.logger.info(f"New contact request from: {contact_name}")
            self.message_logger.info(f"Contact request: {contact_name}")
            
            # Check if this request should be auto-accepted based on pending invites
            should_auto_accept = False
            
            # First check invite manager for pending invites
            if hasattr(self, 'invite_manager') and self.invite_manager.should_auto_accept(contact_request):
                should_auto_accept = True
                self.logger.info(f"Auto-accepting contact request from {contact_name} due to pending invite")
                # Mark an invite as used
                self.invite_manager.mark_invite_used()
            
            # Fallback to config setting
            elif self.config.get('auto_accept_contacts', False):
                should_auto_accept = True
                self.logger.info(f"Auto-accepting contact request from {contact_name} due to config setting")
            
            if should_auto_accept:
                # Auto-accept the contact request
                await self._accept_contact_request(contact_request)
                
        except Exception as e:
            self.logger.error(f"Error handling contact request: {e}")
    
    async def _accept_contact_request(self, contact_request: Dict[str, Any]):
        """Accept a contact request"""
        try:
            # Extract the contact request ID or number for acceptance
            # This is a simplified implementation - you'd need the actual request ID
            contact_name = contact_request.get('localDisplayName', 'Unknown')
            
            # Send acceptance command via WebSocket
            # The exact command format depends on SimpleX CLI WebSocket API
            accept_command = f"/_accept {contact_name}"
            
            # Log the acceptance
            self.logger.info(f"Accepting contact request from: {contact_name}")
            
            # Send the accept command
            await self.websocket_manager.send_command(accept_command)
            
        except Exception as e:
            self.logger.error(f"Error accepting contact request: {e}")
    
    async def _handle_contact_connected(self, response_data: Dict[str, Any]):
        """Handle contact connection notifications"""
        try:
            contact = response_data.get('contact', {})
            contact_name = contact.get('localDisplayName', 'Unknown')
            
            self.logger.info(f"Contact connected: {contact_name}")
            self.message_logger.info(f"Contact connected: {contact_name}")
            
            # Store contact information
            self.contacts[contact_name] = contact
            
        except Exception as e:
            self.logger.error(f"Error handling contact connected: {e}")
    
    async def _handle_group_invitation(self, response_data: Dict[str, Any]):
        """Handle incoming group invitations"""
        try:
            self.logger.info(f"🎯 GROUP INVITATION DEBUG: Processing group invitation")
            
            # Extract data directly from response_data structure
            from_contact = response_data.get('contact', {})
            group_info = response_data.get('groupInfo', {})
            
            from_contact_name = from_contact.get('localDisplayName', 'Unknown')
            group_name = group_info.get('localDisplayName', group_info.get('groupProfile', {}).get('displayName', 'Unknown Group'))
            group_id = group_info.get('groupId')
            
            self.logger.info(f"Group invitation to '{group_name}' (ID: {group_id}) from: {from_contact_name}")
            self.message_logger.info(f"Group invitation: {group_name} from {from_contact_name}")
            
            # Check if the inviter is an admin
            is_admin_inviter = self.admin_manager.is_admin(from_contact_name)
            
            if is_admin_inviter:
                self.logger.info(f"Auto-accepting group invitation to '{group_name}' from admin {from_contact_name}")
                
                # Check if we're already a member (invitation might be auto-accepted)
                membership = group_info.get('membership', {})
                member_status = membership.get('memberStatus', 'unknown')
                
                self.logger.info(f"Current membership status: {member_status}")
                
                if member_status == 'invited':
                    self.logger.info(f"Status is 'invited', attempting to accept invitation")
                    await self._accept_group_invitation(response_data)
                elif member_status == 'member':
                    self.logger.info(f"🎉 Already a member of group '{group_name}'! No action needed.")
                else:
                    self.logger.info(f"Unknown status '{member_status}', trying to accept anyway")
                    await self._accept_group_invitation(response_data)
            else:
                self.logger.info(f"Ignoring group invitation to '{group_name}' from non-admin {from_contact_name}")
                
        except Exception as e:
            self.logger.error(f"Error handling group invitation: {e}")
            self.logger.error(f"Full response_data for debugging: {response_data}")
    
    async def _accept_group_invitation(self, response_data: Dict[str, Any]):
        """Accept a group invitation"""
        try:
            group_info = response_data.get('groupInfo', {})
            group_id = group_info.get('groupId')
            group_name = group_info.get('localDisplayName', group_info.get('groupProfile', {}).get('displayName', 'Unknown Group'))
            
            # Also check membership info for additional details
            membership = group_info.get('membership', {})
            member_id = membership.get('memberId')
            group_member_id = membership.get('groupMemberId')
            
            self.logger.info(f"Debug: group_id={group_id}, member_id={member_id}, group_member_id={group_member_id}")
            self.logger.info(f"Attempting to accept group invitation using /join commands")
            
            if not group_id:
                self.logger.error(f"Cannot accept group invitation: missing group ID for '{group_name}'")
                return
            
            # Try different approaches to accept group invitation
            # Based on testing, use /join commands for group invitations
            commands_to_try = [
                f"/join {group_name}",            # Join with group name (primary)
                f"/join {group_id}",              # Join with group ID (fallback)
            ]
            
            # Try each command until one works
            for i, command in enumerate(commands_to_try):
                try:
                    self.logger.info(f"Attempt {i+1}: Trying command: {command}")
                    
                    # Send the command through WebSocket
                    response = await self.websocket_manager.send_command(command, wait_for_response=True)
                    
                    self.logger.info(f"Command response: {response}")
                    
                    # If we get here without error, the command might have worked
                    if response and 'error' not in str(response).lower():
                        self.logger.info(f"✅ Successfully sent command: {command}")
                        break
                    else:
                        self.logger.warning(f"Command {command} returned error or empty response")
                        
                except Exception as e:
                    self.logger.warning(f"Command '{command}' failed: {e}")
                    if i == len(commands_to_try) - 1:  # Last attempt
                        self.logger.error(f"All command attempts failed for group '{group_name}'")
                        raise e
                    # Continue to next command
            
            self.logger.info(f"Group invitation acceptance process completed for '{group_name}'")
            
        except Exception as e:
            self.logger.error(f"Error accepting group invitation: {e}")
    
    async def _handle_member_joined_group(self, response_data: Dict[str, Any]):
        """Handle when a member (including the bot) joins a group"""
        try:
            group_info = response_data.get('groupInfo', {})
            member_info = response_data.get('memberInfo', {})
            
            group_name = group_info.get('groupName', 'Unknown Group')
            member_name = member_info.get('localDisplayName', 'Unknown Member')
            
            # Check if this is the bot joining
            # Assuming the bot's member info will have a specific identifier or we can detect it
            self.logger.info(f"Member '{member_name}' joined group '{group_name}'")
            self.message_logger.info(f"Group join: {member_name} -> {group_name}")
            
            # If this is the bot itself joining (you may need to adjust this logic based on actual response structure)
            if member_name == self.config.get('bot_name', 'SimpleX Bot') or 'bot' in member_name.lower():
                self.logger.info(f"🎉 Bot successfully joined group '{group_name}'!")
                
        except Exception as e:
            self.logger.error(f"Error handling member joined group: {e}")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="SimpleX Chat Bot")
    parser.add_argument(
        "-c", "--config", 
        default="config.yml", 
        help="Path to configuration file"
    )
    parser.add_argument(
        "--websocket-url", 
        help="WebSocket URL for SimpleX Chat CLI"
    )
    parser.add_argument(
        "--log-level", 
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help="Set logging level"
    )
    parser.add_argument(
        "--profile-path", 
        help="Path to SimpleX Chat profile directory"
    )
    parser.add_argument(
        "--media-path", 
        help="Path to media storage directory"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Run in dry-run mode (no actual downloads)"
    )
    
    return parser.parse_args()


async def main():
    """Main entry point"""
    args = parse_arguments()
    
    # Create and start bot
    bot = SimplexChatBot(config_path=args.config, cli_args=args)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down...")
    except Exception as e:
        bot.logger.error(f"Unexpected error: {e}")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())