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
                    # Create a complete message structure that includes the original chatItem data
                    # This is crucial for group messages to preserve the groupMember information
                    fake_message_data = {
                        'chatInfo': message_data.get('chatInfo', {}),
                        'chatItem': {
                            # Preserve the original chatDir (contains groupMember for groups)
                            'chatDir': message_data.get('chatItem', {}).get('chatDir', {}),
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
        enabled_plugin_count = 0
        all_commands = {}
        total_commands = 0
        
        if hasattr(self.bot_instance, 'plugin_manager'):
            plugin_manager = getattr(self.bot_instance, 'plugin_manager')
            plugin_count = len(plugin_manager.plugins)
            
            # Get commands from all plugins
            for plugin_name, plugin in plugin_manager.plugins.items():
                if plugin.enabled:
                    enabled_plugin_count += 1
                    commands = plugin.get_commands()
                    if commands:
                        all_commands[plugin_name] = {
                            'commands': commands,
                            'description': plugin.description,
                            'version': plugin.version
                        }
                        total_commands += len(commands)
        
        # Add legacy commands from command registry
        legacy_commands = self.list_commands()
        if legacy_commands:
            total_commands += len(legacy_commands)
        
        # Start building help text with bot info
        help_text = f"""🤖 **{bot_name} Help & Information**

**Bot Details:**
• Version: {bot_version}
• Platform: {platform} 
• Status: ✅ Running
• Description: {bot_description}

**System Status:**
• Plugin System: {plugin_status}
• Total Plugins: {plugin_count}
• Enabled Plugins: {enabled_plugin_count}
• Total Commands: {total_commands}"""
        
        # Add core commands (both legacy and core plugin commands)
        core_commands = set(legacy_commands) if legacy_commands else set()
        
        # Add core plugin commands if available
        if 'core' in all_commands:
            core_commands.update(all_commands['core']['commands'])
        
        if core_commands:
            help_text += f"""

**Core Commands:**"""
            # Sort commands for consistent display
            for cmd in sorted(core_commands):
                if cmd == 'help':
                    help_text += f"\n• `!{cmd}` - Show this help and bot information"
                elif cmd == 'plugins':
                    help_text += f"\n• `!{cmd}` - List all plugins and their status"
                elif cmd == 'commands':
                    help_text += f"\n• `!{cmd}` - List all available commands"
                elif cmd == 'ping':
                    help_text += f"\n• `!{cmd}` - Test bot responsiveness"
                elif cmd == 'uptime':
                    help_text += f"\n• `!{cmd}` - Show bot uptime"
                elif cmd == 'enable':
                    help_text += f"\n• `!{cmd} <plugin>` - Enable a plugin"
                elif cmd == 'disable':
                    help_text += f"\n• `!{cmd} <plugin>` - Disable a plugin"
                elif cmd == 'start':
                    help_text += f"\n• `!{cmd} <plugin>` - Start a plugin"
                elif cmd == 'stop':
                    help_text += f"\n• `!{cmd} <plugin>` - Stop a plugin"
                elif cmd == 'reload':
                    help_text += f"\n• `!{cmd} <plugin>` - Reload a plugin"
                elif cmd == 'status':
                    help_text += f"\n• `!{cmd} <plugin>` - Show plugin status"
                elif cmd == 'platform':
                    help_text += f"\n• `!{cmd}` - Show platform information"
                elif cmd == 'container':
                    help_text += f"\n• `!{cmd} <action> <plugin>` - Manage plugin containers"
                elif cmd == 'containers':
                    help_text += f"\n• `!{cmd}` - List all containerized plugins"
                else:
                    help_text += f"\n• `!{cmd}` - {cmd.title()} command"
        
        # Add plugin commands (excluding core plugin which is shown separately)
        plugin_commands = {k: v for k, v in all_commands.items() if k != 'core'}
        if plugin_commands:
            help_text += f"""

**Available Plugin Commands:**"""
        
        # Add plugin commands
        for plugin_name, plugin_info in plugin_commands.items():
            commands_str = ', '.join([f"`!{cmd}`" for cmd in plugin_info['commands']])
            help_text += f"\n\n**{plugin_name.title()} Plugin** (v{plugin_info['version']}):\n"
            help_text += f"*{plugin_info['description']}*\n"
            help_text += f"Commands: {commands_str}"
        
        # Add dynamic tips based on available commands
        tips = [
            "All commands start with `!`",
            "Commands are case-sensitive"
        ]
        
        # Add tips for available commands dynamically
        if 'plugins' in core_commands:
            tips.append("Use `!plugins` for detailed plugin status")
        if 'commands' in core_commands:
            tips.append("Use `!commands` for complete command list with examples")
        if plugin_commands:
            tips.append("Plugin commands are automatically discovered and loaded")
        
        # Check for specific plugin features
        if 'simplex' in all_commands:
            simplex_commands = all_commands['simplex']['commands']
            if 'stats' in simplex_commands:
                tips.append("Use `!stats` for bot statistics (admin only)")
            if 'admin' in simplex_commands:
                tips.append("Use `!admin` for admin management (admin only)")
        
        help_text += f"""

**Tips:**"""
        for tip in tips:
            help_text += f"\n• {tip}"
        
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
        self.logger.info(f"📁 INIT DEBUG: Media config from bot.yml: {media_config}")
        
        self.file_download_manager = FileDownloadManager(
            media_config=media_config,
            xftp_client=self.xftp_client,
            logger=self.logger
        )
        
        self.logger.info(f"📁 INIT DEBUG: FileDownloadManager initialized")
        self.logger.info(f"📁 INIT DEBUG: Media enabled: {self.file_download_manager.media_enabled}")
        self.logger.info(f"📁 INIT DEBUG: Media path: {self.file_download_manager.media_path}")
        self.logger.info(f"📁 INIT DEBUG: Media config used: {self.file_download_manager.media_config}")
        
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
        self.websocket_manager.register_message_handler('rcvFileDescrReady', self._handle_file_descriptor_ready)
    
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
            # Quote group name if it contains spaces to handle parsing correctly
            # SimpleX CLI uses single quotes for names with spaces: @'John Doe' 
            has_spaces = ' ' in group_name
            quoted_group_name = f"'{group_name}'" if has_spaces else group_name
            
            self.logger.info(f"🔧 GROUP JOIN DEBUG: group_name='{group_name}', has_spaces={has_spaces}")
            self.logger.info(f"🔧 GROUP JOIN DEBUG: quoted_group_name='{quoted_group_name}'")
            
            commands_to_try = [
                f"/join {quoted_group_name}",     # Join with group name (quoted if needed)
                f"/join {group_id}",              # Join with group ID (fallback)
            ]
            
            self.logger.info(f"🔧 GROUP JOIN DEBUG: commands_to_try={commands_to_try}")
            
            # Try each command until one works
            for i, command in enumerate(commands_to_try):
                try:
                    self.logger.info(f"🔧 GROUP JOIN DEBUG: Attempt {i+1}: Trying command: {command}")
                    
                    # Send the command through WebSocket
                    response = await self.websocket_manager.send_command(command, wait_for_response=True)
                    
                    self.logger.info(f"🔧 GROUP JOIN DEBUG: Command response: {response}")
                    self.logger.info(f"🔧 GROUP JOIN DEBUG: Response type: {type(response)}")
                    
                    # If we get here without error, the command might have worked
                    if response and 'error' not in str(response).lower():
                        self.logger.info(f"✅ Successfully sent command: {command}")
                        break
                    else:
                        self.logger.warning(f"🔧 GROUP JOIN DEBUG: Command {command} returned error or empty response")
                        self.logger.info(f"🔧 GROUP JOIN DEBUG: Will continue to next command (if available)")
                        
                except Exception as e:
                    self.logger.warning(f"🔧 GROUP JOIN DEBUG: Command '{command}' failed with exception: {e}")
                    if i == len(commands_to_try) - 1:  # Last attempt
                        self.logger.error(f"🔧 GROUP JOIN DEBUG: All command attempts failed for group '{group_name}'")
                        raise e
                    # Continue to next command
            
            self.logger.info(f"🔧 GROUP JOIN DEBUG: Group invitation acceptance process completed for '{group_name}'")
            self.logger.info(f"🔧 GROUP JOIN DEBUG: Commands sent, waiting for async responses...")
            self.logger.info(f"🔧 GROUP JOIN DEBUG: Success will be indicated by 'memberJoinedGroup' event or group messages")
            
        except Exception as e:
            self.logger.error(f"Error accepting group invitation: {e}")
    
    async def _handle_member_joined_group(self, response_data: Dict[str, Any]):
        """Handle when a member (including the bot) joins a group"""
        try:
            self.logger.info(f"🔧 MEMBER JOIN DEBUG: Processing memberJoinedGroup event")
            
            group_info = response_data.get('groupInfo', {})
            member_info = response_data.get('memberInfo', {})
            
            group_name = group_info.get('groupName', 'Unknown Group')
            member_name = member_info.get('localDisplayName', 'Unknown Member')
            
            self.logger.info(f"🔧 MEMBER JOIN DEBUG: group_name='{group_name}', member_name='{member_name}'")
            
            # Check if this is the bot joining
            # Assuming the bot's member info will have a specific identifier or we can detect it
            self.logger.info(f"Member '{member_name}' joined group '{group_name}'")
            self.message_logger.info(f"Group join: {member_name} -> {group_name}")
            
            # If this is the bot itself joining (you may need to adjust this logic based on actual response structure)
            if member_name == self.config.get('bot_name', 'SimpleX Bot') or 'bot' in member_name.lower():
                self.logger.info(f"🎉 Bot successfully joined group '{group_name}'!")
                self.logger.info(f"🔧 MEMBER JOIN DEBUG: Bot join confirmed for group '{group_name}'")
            else:
                self.logger.info(f"🔧 MEMBER JOIN DEBUG: Other member '{member_name}' joined, not the bot")
                
        except Exception as e:
            self.logger.error(f"Error handling member joined group: {e}")
            self.logger.error(f"🔧 MEMBER JOIN DEBUG: Full response_data: {response_data}")

    async def _handle_file_descriptor_ready(self, response_data: Dict[str, Any]):
        """Handle rcvFileDescrReady event - delegate to message handler"""
        try:
            self.logger.info("🎯 BOT: Received rcvFileDescrReady event, delegating to message handler")
            await self.message_handler.handle_file_descriptor_ready(response_data)
        except Exception as e:
            self.logger.error(f"Error handling file descriptor ready event: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")


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