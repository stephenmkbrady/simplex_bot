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
            # Minimal core bot command for testing basic functionality
            'info': self._info_command,
            # Note: All other commands moved to plugins:
            # - help, ping, status -> Core Plugin
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
    
    async def execute_command(self, text: str, contact_name: str, plugin_manager=None) -> Optional[str]:
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
                from plugins.universal_plugin_base import CommandContext, BotPlatform
                context = CommandContext(
                    command=command_name,
                    args=args,
                    args_raw=' '.join(args),
                    user_id=contact_name,
                    chat_id=contact_name,
                    user_display_name=contact_name,
                    platform=BotPlatform.SIMPLEX,
                    raw_message={}
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
    
    async def _info_command(self, args: list, contact_name: str, send_message_callback):
        """Basic bot info command for testing connectivity - reads from version.yml"""
        import yaml
        from pathlib import Path
        
        # Read version info from version.yml - fail if not found
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
        if hasattr(self.bot_instance, 'plugin_manager'):
            plugin_manager = getattr(self.bot_instance, 'plugin_manager')
            plugin_count = len(plugin_manager.plugins)
        
        info_text = f"""🤖 **{bot_name}**

**Version:** {bot_version}
**Platform:** {platform}
**Status:** ✅ Running

**Description:** {bot_description}

**System Status:**
• Plugin System: {plugin_status}
• Loaded Plugins: {plugin_count}
• Core Commands: 1 (info)

**Getting Started:**
• Use `!help` to see all available commands
• Use `!plugins` to see loaded plugins
• Use `!status` for detailed bot status

This is the only core command. All other functionality is provided through plugins."""

        await send_message_callback(contact_name, info_text)

    async def _help_command(self, args: list, contact_name: str, send_message_callback):
        """Help command handler"""
        # Use contact_name for admin checks
        user_identifier = contact_name
        
        is_admin = self.admin_manager.is_admin(user_identifier)
        all_commands = self.list_commands()
        
        # Filter commands based on permissions
        available_commands = []
        for cmd in all_commands:
            if self.admin_manager.can_run_command(user_identifier, cmd):
                available_commands.append(cmd)
        
        help_text = f"Available commands: {', '.join(available_commands)}"
        
        if is_admin:
            help_text += "\n\nAdmin commands: !admin, !reload_admin, !invite, !contacts, !groups, !debug"
            help_text += "\nUse !admin for admin management, !invite for connection invites."
            help_text += "\nUse !contacts list to see bot contacts, !groups list to see groups."
        
        await send_message_callback(contact_name, help_text)
    
    async def _status_command(self, args: list, contact_name: str, send_message_callback):
        """Status command handler"""
        await send_message_callback(contact_name, "Bot is running and healthy!")
    
    async def _ping_command(self, args: list, contact_name: str, send_message_callback):
        """Ping command handler"""
        await send_message_callback(contact_name, "Pong!")
    
    async def _stats_command(self, args: list, contact_name: str, send_message_callback):
        """Stats command handler"""
        await send_message_callback(contact_name, "Statistics feature coming soon!")
    
    async def _debug_command(self, args: list, contact_name: str, send_message_callback):
        """Debug command handler - tests WebSocket connectivity"""
        user_identifier = contact_name
        
        if not self.admin_manager.is_admin(user_identifier):
            await send_message_callback(contact_name, "Access denied. Only admins can use debug commands.")
            return
        
        if not args:
            help_text = """Debug commands:
!debug websocket - Test WebSocket connection
!debug ping - Send test ping to SimpleX CLI
!debug restart - Force restart SimpleX CLI process"""
            await send_message_callback(contact_name, help_text)
            return
        
        subcommand = args[0].lower()
        
        if subcommand == "websocket":
            # Get WebSocket info
            if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                ws_manager = self.bot_instance.websocket_manager
                ws_id = id(ws_manager.websocket) if ws_manager.websocket else None
                
                response = f"""🔌 WebSocket Debug Info:
ID: {ws_id}
Connected: {ws_manager.websocket is not None}
URL: {ws_manager.websocket_url}
Pending requests: {len(ws_manager.pending_requests)}"""
                
                await send_message_callback(contact_name, response)
            else:
                await send_message_callback(contact_name, "WebSocket manager not available")
        
        elif subcommand == "ping":
            # Send a test command to SimpleX CLI
            if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                ws_manager = self.bot_instance.websocket_manager
                
                await send_message_callback(contact_name, "🏓 Testing SimpleX CLI commands...")
                
                # Test valid SimpleX CLI commands
                test_commands = [
                    "/help",            # Show available commands
                    "/contacts",        # List contacts
                    "/groups",          # List groups
                    "/c",               # Contact shorthand
                    "/g",               # Groups shorthand
                    "/connect",         # Connection command
                ]
                
                working_commands = []
                for cmd in test_commands:
                    try:
                        self.logger.info(f"🔍 Testing CLI command: {cmd}")
                        response = await ws_manager.send_command(cmd, wait_for_response=False)  # Non-blocking
                        if response:
                            working_commands.append(cmd)
                            self.logger.info(f"✅ Command {cmd} works!")
                        else:
                            self.logger.info(f"❌ Command {cmd} timeout")
                    except Exception as e:
                        self.logger.info(f"❌ Command {cmd} failed: {e}")
                
                if working_commands:
                    result = f"🏓 CLI responding! Working commands: {', '.join(working_commands)}"
                else:
                    result = "🏓 CLI not responding to any test commands"
                
                await send_message_callback(contact_name, result)
            else:
                await send_message_callback(contact_name, "WebSocket manager not available")
        
        elif subcommand == "restart":
            # Force restart SimpleX CLI
            if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                ws_manager = self.bot_instance.websocket_manager
                
                await send_message_callback(contact_name, "🔄 Force restarting SimpleX CLI process...")
                
                try:
                    if await ws_manager.restart_cli_process():
                        await send_message_callback(contact_name, "✅ CLI restart successful! User messages should now flow.")
                    else:
                        await send_message_callback(contact_name, "❌ CLI restart failed. Check logs for details.")
                        
                except Exception as e:
                    await send_message_callback(contact_name, f"🔄 Restart failed: {type(e).__name__}: {e}")
            else:
                await send_message_callback(contact_name, "WebSocket manager not available")
        
        else:
            await send_message_callback(contact_name, f"Unknown debug subcommand: {subcommand}")
    
    async def _admin_command(self, args: list, contact_name: str, send_message_callback):
        """Admin management command handler"""
        user_identifier = contact_name
        
        if not self.admin_manager.is_admin(user_identifier):
            await send_message_callback(contact_name, "Access denied. Only admins can use admin commands.")
            return
        
        if not args:
            help_text = """Admin commands:
!admin list - List all admins
!admin add <username> - Add admin with full permissions
!admin remove <username> - Remove admin
!admin permissions <username> - Show user permissions
!admin reload - Reload admin config"""
            await send_message_callback(contact_name, help_text)
            return
        
        subcommand = args[0].lower()
        
        if subcommand == "list":
            admins = self.admin_manager.list_admins()
            if not admins:
                await send_message_callback(contact_name, "No admins configured.")
                return
            
            admin_list = []
            for admin_name, commands in admins.items():
                cmd_str = "all commands" if "*" in commands else ", ".join(commands)
                admin_list.append(f"• {admin_name}: {cmd_str}")
            
            response = "Current admins:\n" + "\n".join(admin_list)
            await send_message_callback(contact_name, response)
        
        elif subcommand == "add":
            if len(args) < 2:
                await send_message_callback(contact_name, "Usage: !admin add <username>")
                return
            
            username = args[1]
            if self.admin_manager.add_admin(username):
                await send_message_callback(contact_name, f"Added {username} as admin with full permissions.")
            else:
                await send_message_callback(contact_name, f"Failed to add {username} as admin.")
        
        elif subcommand == "remove":
            if len(args) < 2:
                await send_message_callback(contact_name, "Usage: !admin remove <username>")
                return
            
            username = args[1]
            if username == contact_name:
                await send_message_callback(contact_name, "You cannot remove yourself as admin.")
                return
            
            if self.admin_manager.remove_admin(username):
                await send_message_callback(contact_name, f"Removed {username} from admins.")
            else:
                await send_message_callback(contact_name, f"Failed to remove {username} or user not found.")
        
        elif subcommand == "permissions":
            if len(args) < 2:
                await send_message_callback(contact_name, "Usage: !admin permissions <username>")
                return
            
            username = args[1]
            perms = self.admin_manager.get_user_permissions(username)
            
            if perms['is_admin']:
                cmd_str = "all commands" if "*" in perms['admin_commands'] else ", ".join(perms['admin_commands'])
                response = f"User {username} is an admin with permissions: {cmd_str}"
            else:
                response = f"User {username} is not an admin. Can only run public commands: {', '.join(perms['public_commands'])}"
            
            await send_message_callback(contact_name, response)
        
        elif subcommand == "reload":
            self.admin_manager.reload_config()
            await send_message_callback(contact_name, "Admin configuration reloaded.")
        
        else:
            await send_message_callback(contact_name, f"Unknown admin subcommand: {subcommand}")
    
    async def _reload_admin_command(self, args: list, contact_name: str, send_message_callback):
        """Reload admin configuration command"""
        user_identifier = contact_name
        
        if not self.admin_manager.is_admin(user_identifier):
            await send_message_callback(contact_name, "Access denied. Only admins can reload admin config.")
            return
        
        self.admin_manager.reload_config()
        await send_message_callback(contact_name, "Admin configuration reloaded successfully.")
    
    async def _invite_command(self, args: list, contact_name: str, send_message_callback):
        """Invite management command handler"""
        user_identifier = contact_name
        
        if not self.admin_manager.is_admin(user_identifier):
            await send_message_callback(contact_name, "Access denied. Only admins can manage invites.")
            return
        
        if not args:
            help_text = """Invite commands:
!invite generate - Generate a one-time connection invite
!invite list - List pending invites
!invite revoke <invite_id> - Revoke a pending invite
!invite stats - Show invite statistics"""
            await send_message_callback(contact_name, help_text)
            return
        
        subcommand = args[0].lower()
        
        if subcommand == "generate":
            # Get the bot's invite manager from command registry
            if self.bot_instance and hasattr(self.bot_instance, 'invite_manager'):
                invite_manager = self.bot_instance.invite_manager
                
                # Use WebSocket restart method - cleanly disconnect, generate invite, reconnect
                await send_message_callback(contact_name, "🔄 Generating invite (temporarily disconnecting)...")
                
                # Generate invite with WebSocket disconnect (main loop handles reconnection)
                invite_link = await invite_manager.generate_invite_with_websocket_disconnect(
                    self.bot_instance.websocket_manager, contact_name, contact_name)
                
                if invite_link:
                    # Store the invite message to be sent after reconnection
                    response = f"""🔗 One-time connection invite generated:

{invite_link}

Share this link with the user and ask them to connect using:
/c {invite_link}

This invite will be auto-accepted when used and expires in 24 hours."""
                    
                    # Store the message to be sent after reconnection
                    self.bot_instance.websocket_manager.pending_invite_message = {
                        'contact_name': contact_name,
                        'message': response
                    }
                    
                    self.logger.info(f"🎫 INVITE MESSAGE QUEUED: Message queued for {contact_name} after reconnection")
                else:
                    # Store failure message to be sent after reconnection
                    self.bot_instance.websocket_manager.pending_invite_message = {
                        'contact_name': contact_name,
                        'message': "Failed to generate invite. Check logs for details."
                    }
            else:
                await send_message_callback(contact_name, "Invite manager not available.")
        
        elif subcommand == "list":
            if self.bot_instance and hasattr(self.bot_instance, 'invite_manager'):
                invite_manager = self.bot_instance.invite_manager
                pending_invites = invite_manager.get_pending_invites()
                
                if not pending_invites:
                    await send_message_callback(contact_name, "No pending invites.")
                    return
                
                response = "📋 Pending invites:\n\n"
                for invite in pending_invites:
                    created = invite['created_at'].strftime("%Y-%m-%d %H:%M")
                    expires = invite['expires_at'].strftime("%Y-%m-%d %H:%M")
                    response += f"• ID: {invite['id']}\n"
                    response += f"  Requested by: {invite['requested_by']}\n"
                    response += f"  Created: {created}\n"
                    response += f"  Expires: {expires}\n\n"
                
                await send_message_callback(contact_name, response)
            else:
                await send_message_callback(contact_name, "Invite manager not available.")
        
        elif subcommand == "revoke":
            if len(args) < 2:
                await send_message_callback(contact_name, "Usage: !invite revoke <invite_id>")
                return
            
            invite_id = args[1]
            
            if self.bot_instance and hasattr(self.bot_instance, 'invite_manager'):
                invite_manager = self.bot_instance.invite_manager
                
                if invite_manager.revoke_invite(invite_id):
                    await send_message_callback(contact_name, f"Invite {invite_id} revoked successfully.")
                else:
                    await send_message_callback(contact_name, f"Invite {invite_id} not found.")
            else:
                await send_message_callback(contact_name, "Invite manager not available.")
        
        elif subcommand == "stats":
            if self.bot_instance and hasattr(self.bot_instance, 'invite_manager'):
                invite_manager = self.bot_instance.invite_manager
                stats = invite_manager.get_stats()
                
                response = f"""📊 Invite Statistics:

Pending invites: {stats['pending_invites']}/{stats['max_pending_invites']}
Invite expiry: {stats['invite_expiry_hours']} hours"""
                
                await send_message_callback(contact_name, response)
            else:
                await send_message_callback(contact_name, "Invite manager not available.")
        
        else:
            await send_message_callback(contact_name, f"Unknown invite subcommand: {subcommand}")
    
    async def _contacts_command(self, args: list, contact_name: str, send_message_callback):
        """List contacts command - admin only"""
        user_identifier = contact_name
        
        if not self.admin_manager.is_admin(user_identifier):
            await send_message_callback(contact_name, "Access denied. Only admins can list contacts.")
            return
        
        if not args:
            help_text = """Contact commands:
!contacts list - List all contacts
!contacts info <name> - Get contact details"""
            await send_message_callback(contact_name, help_text)
            return
        
        subcommand = args[0].lower()
        
        if subcommand == "list":
            if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                ws_manager = self.bot_instance.websocket_manager
                
                # Register callback for contacts response
                async def contacts_callback(response_data):
                    try:
                        self.logger.info(f"🔔 CALLBACK START: Processing contacts callback")
                        contacts_info = self._parse_contacts_response(response_data)
                        self.logger.info(f"🔔 CALLBACK: Parsed {len(contacts_info) if contacts_info else 0} contacts")
                        
                        if contacts_info:
                            contact_list = []
                            for i, contact in enumerate(contacts_info, 1):
                                name = contact.get('localDisplayName', 'Unknown')
                                contact_status = contact.get('contactStatus', 'unknown')
                                conn_status = 'disconnected'
                                if 'activeConn' in contact and contact['activeConn']:
                                    conn_status = contact['activeConn'].get('connStatus', 'unknown')
                                contact_list.append(f"{i}. {name} (Contact: {contact_status}, Connection: {conn_status})")
                            
                            response_text = f"📋 Bot Contacts ({len(contacts_info)} total):\n\n" + "\n".join(contact_list)
                        else:
                            response_text = "No contacts found."
                        
                        self.logger.info(f"🔔 CALLBACK: About to send response: {response_text[:50]}...")
                        self.logger.info(f"🔔 CALLBACK: Sending to contact: {contact_name}")
                        
                        # Call WebSocket manager's send_message directly instead of the wrapper
                        if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                            await self.bot_instance.websocket_manager.send_message(contact_name, response_text)
                            self.logger.info(f"🔔 CALLBACK: Direct send_message completed successfully")
                        else:
                            self.logger.error(f"🔔 CALLBACK: No WebSocket manager available for direct send")
                            # Fallback to the wrapper
                            await send_message_callback(contact_name, response_text)
                            self.logger.info(f"🔔 CALLBACK: Fallback send_message_callback completed")
                    except Exception as e:
                        self.logger.error(f"🔔 CALLBACK ERROR: {type(e).__name__}: {e}")
                        import traceback
                        self.logger.error(f"🔔 CALLBACK TRACEBACK: {traceback.format_exc()}")
                        await send_message_callback(contact_name, f"Error processing contacts: {type(e).__name__}: {e}")
                
                try:
                    # Register the callback and send the command
                    ws_manager.register_command_callback('/contacts', contacts_callback)
                    await ws_manager.send_command("/contacts", wait_for_response=True)
                    # Response will be handled asynchronously by the callback
                        
                except Exception as e:
                    await send_message_callback(contact_name, f"Error sending contacts command: {type(e).__name__}: {e}")
            else:
                await send_message_callback(contact_name, "WebSocket manager not available.")
        
        elif subcommand == "info":
            if len(args) < 2:
                await send_message_callback(contact_name, "Usage: !contacts info <contact_name>")
                return
            
            contact_to_check = " ".join(args[1:])
            
            if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                ws_manager = self.bot_instance.websocket_manager
                
                try:
                    # Send command to get specific contact info
                    response = await ws_manager.send_command(f"/contact {contact_to_check}", wait_for_response=False)  # Non-blocking
                    
                    if response:
                        contact_info = self._parse_contact_info_response(response)
                        if contact_info:
                            info_text = f"📋 Contact Info for {contact_to_check}:\n\n"
                            info_text += f"Display Name: {contact_info.get('localDisplayName', 'Unknown')}\n"
                            info_text += f"Profile Name: {contact_info.get('profile', {}).get('displayName', 'Unknown')}\n"
                            info_text += f"Connection: {contact_info.get('activeConn', 'Unknown')}\n"
                            info_text += f"Created: {contact_info.get('createdAt', 'Unknown')}"
                        else:
                            info_text = f"Contact '{contact_to_check}' not found."
                    else:
                        info_text = f"Failed to get info for contact '{contact_to_check}'."
                        
                except Exception as e:
                    info_text = f"Error getting contact info: {type(e).__name__}: {e}"
                
                await send_message_callback(contact_name, info_text)
            else:
                await send_message_callback(contact_name, "WebSocket manager not available.")
        
        else:
            await send_message_callback(contact_name, f"Unknown contacts subcommand: {subcommand}")
    
    async def _groups_command(self, args: list, contact_name: str, send_message_callback):
        """List groups command - admin only"""
        user_identifier = contact_name
        
        if not self.admin_manager.is_admin(user_identifier):
            await send_message_callback(contact_name, "Access denied. Only admins can list groups.")
            return
        
        if not args:
            help_text = """Group commands:
!groups list - List all groups
!groups info <name> - Get group details
!groups invite <name> - Generate group invite link"""
            await send_message_callback(contact_name, help_text)
            return
        
        subcommand = args[0].lower()
        
        if subcommand == "list":
            if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                ws_manager = self.bot_instance.websocket_manager
                
                # Register callback for groups response
                async def groups_callback(response_data):
                    try:
                        self.logger.info(f"🔔 GROUPS CALLBACK: Processing groups callback")
                        groups_info = self._parse_groups_response(response_data)
                        self.logger.info(f"🔔 GROUPS CALLBACK: Parsed {len(groups_info) if groups_info else 0} groups")
                        
                        if groups_info:
                            group_list = []
                            for i, group in enumerate(groups_info, 1):
                                name = group.get('displayName', 'Unknown')
                                members = group.get('membership', {}).get('memberRole', 'Unknown')
                                group_list.append(f"{i}. {name} (Role: {members})")
                            
                            response_text = f"📋 Bot Groups ({len(groups_info)} total):\n\n" + "\n".join(group_list)
                        else:
                            response_text = "No groups found."
                        
                        self.logger.info(f"🔔 GROUPS CALLBACK: About to send response: {response_text[:50]}...")
                        
                        # Call WebSocket manager's send_message directly
                        if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                            await self.bot_instance.websocket_manager.send_message(contact_name, response_text)
                            self.logger.info(f"🔔 GROUPS CALLBACK: Direct send_message completed successfully")
                        else:
                            self.logger.error(f"🔔 GROUPS CALLBACK: No WebSocket manager available for direct send")
                            await send_message_callback(contact_name, response_text)
                            
                    except Exception as e:
                        self.logger.error(f"🔔 GROUPS CALLBACK ERROR: {type(e).__name__}: {e}")
                        import traceback
                        self.logger.error(f"🔔 GROUPS CALLBACK TRACEBACK: {traceback.format_exc()}")
                        if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                            await self.bot_instance.websocket_manager.send_message(contact_name, f"Error processing groups: {type(e).__name__}: {e}")
                
                try:
                    # Register the callback and send the command
                    ws_manager.register_command_callback('/groups', groups_callback)
                    await ws_manager.send_command("/groups", wait_for_response=True)
                    # Response will be handled asynchronously by the callback
                        
                except Exception as e:
                    if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                        await self.bot_instance.websocket_manager.send_message(contact_name, f"Error sending groups command: {type(e).__name__}: {e}")
            else:
                await send_message_callback(contact_name, "WebSocket manager not available.")
        
        elif subcommand == "info":
            if len(args) < 2:
                await send_message_callback(contact_name, "Usage: !groups info <group_name>")
                return
            
            group_to_check = " ".join(args[1:])
            
            if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                ws_manager = self.bot_instance.websocket_manager
                
                try:
                    # Send command to get specific group info
                    response = await ws_manager.send_command(f"/group {group_to_check}", wait_for_response=False)  # Non-blocking
                    
                    if response:
                        group_info = self._parse_group_info_response(response)
                        if group_info:
                            info_text = f"📋 Group Info for {group_to_check}:\n\n"
                            info_text += f"Display Name: {group_info.get('displayName', 'Unknown')}\n"
                            info_text += f"Description: {group_info.get('description', 'None')}\n"
                            info_text += f"Member Role: {group_info.get('membership', {}).get('memberRole', 'Unknown')}\n"
                            info_text += f"Created: {group_info.get('createdAt', 'Unknown')}"
                        else:
                            info_text = f"Group '{group_to_check}' not found."
                    else:
                        info_text = f"Failed to get info for group '{group_to_check}'."
                        
                except Exception as e:
                    info_text = f"Error getting group info: {type(e).__name__}: {e}"
                
                await send_message_callback(contact_name, info_text)
            else:
                await send_message_callback(contact_name, "WebSocket manager not available.")
        
        elif subcommand == "invite":
            if len(args) < 2:
                await send_message_callback(contact_name, "Usage: !groups invite <group_name>")
                return
            
            group_name = " ".join(args[1:])
            
            if self.bot_instance and hasattr(self.bot_instance, 'websocket_manager'):
                ws_manager = self.bot_instance.websocket_manager
                
                try:
                    await send_message_callback(contact_name, f"🔄 Generating group invite for '{group_name}'...")
                    
                    # Send command to generate group invite (fixed format)
                    response = await ws_manager.send_command(f"/g {group_name} /add", wait_for_response=False)  # Non-blocking
                    
                    if response:
                        invite_link = self._parse_group_invite_response(response)
                        if invite_link:
                            response_text = f"""🔗 Group invite generated for '{group_name}':

{invite_link}

Share this link to invite users to the group.
Note: Group invite permissions depend on your role in the group."""
                        else:
                            response_text = f"Failed to generate invite for group '{group_name}'. Check if you have permission to invite members."
                    else:
                        response_text = f"Failed to generate invite for group '{group_name}'."
                        
                except Exception as e:
                    response_text = f"Error generating group invite: {type(e).__name__}: {e}"
                
                await send_message_callback(contact_name, response_text)
            else:
                await send_message_callback(contact_name, "WebSocket manager not available.")
        
        else:
            await send_message_callback(contact_name, f"Unknown groups subcommand: {subcommand}")
    
    def _parse_contacts_response(self, response):
        """Parse SimpleX CLI /contacts command response"""
        try:
            self.logger.info(f"Parsing contacts response: {type(response)}: {str(response)[:200]}...")
            
            if isinstance(response, dict):
                resp = response.get('resp', {})
                if 'Right' in resp:
                    actual_resp = resp['Right']
                    # Check if this is a contactsList response
                    if isinstance(actual_resp, dict) and actual_resp.get('type') == 'contactsList':
                        contacts = actual_resp.get('contacts', [])
                        self.logger.info(f"Found {len(contacts)} contacts in response")
                        return contacts
                # Handle error responses
                elif 'Left' in resp:
                    error_info = resp['Left']
                    self.logger.error(f"CLI error response: {error_info}")
                    return []
            
            return []
        except Exception as e:
            self.logger.error(f"Error parsing contacts response: {e}")
            return []
    
    def _parse_contacts_text(self, text):
        """Parse text output from /contacts command"""
        try:
            contacts = []
            lines = text.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('--') and not line.startswith('You have'):
                    # Simple parsing - extract contact names
                    # Format might be like: "1. ContactName @active" or just "ContactName"
                    if '. ' in line:
                        parts = line.split('. ', 1)
                        if len(parts) > 1:
                            contact_name = parts[1].split(' ')[0]  # Get first word after number
                            contacts.append({'localDisplayName': contact_name, 'activeConn': 'active'})
                    elif line and not line.startswith('/'):
                        # Just treat the line as a contact name
                        contact_name = line.split(' ')[0]
                        contacts.append({'localDisplayName': contact_name, 'activeConn': 'unknown'})
            
            return contacts
        except Exception as e:
            self.logger.error(f"Error parsing contacts text: {e}")
            return []
    
    def _parse_contact_info_response(self, response):
        """Parse SimpleX CLI contact info response"""
        try:
            if isinstance(response, dict):
                resp = response.get('resp', {})
                if 'Right' in resp:
                    actual_resp = resp['Right']
                    if 'contact' in actual_resp:
                        return actual_resp['contact']
                    elif isinstance(actual_resp, dict) and 'localDisplayName' in actual_resp:
                        return actual_resp
            return None
        except Exception as e:
            self.logger.error(f"Error parsing contact info response: {e}")
            return None
    
    def _parse_groups_response(self, response):
        """Parse SimpleX CLI /groups command response"""
        try:
            self.logger.info(f"Parsing groups response: {type(response)}: {str(response)[:200]}...")
            
            if isinstance(response, dict):
                resp = response.get('resp', {})
                if 'Right' in resp:
                    actual_resp = resp['Right']
                    # Check if this is a groupsList response
                    if isinstance(actual_resp, dict) and actual_resp.get('type') == 'groupsList':
                        groups = actual_resp.get('groups', [])
                        self.logger.info(f"Found {len(groups)} groups in response")
                        return groups
                # Handle error responses
                elif 'Left' in resp:
                    error_info = resp['Left']
                    self.logger.error(f"CLI error response: {error_info}")
                    return []
            
            return []
        except Exception as e:
            self.logger.error(f"Error parsing groups response: {e}")
            return []
    
    def _parse_groups_text(self, text):
        """Parse text output from /groups command"""
        try:
            groups = []
            lines = text.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('--') and not line.startswith('You have'):
                    # Simple parsing - extract group names
                    # Format might be like: "1. GroupName (5 members)" or just "GroupName"
                    if '. ' in line:
                        parts = line.split('. ', 1)
                        if len(parts) > 1:
                            group_name = parts[1].split(' ')[0]  # Get first word after number
                            groups.append({'displayName': group_name, 'membership': {'memberRole': 'member'}})
                    elif line and not line.startswith('/'):
                        # Just treat the line as a group name
                        group_name = line.split(' ')[0]
                        groups.append({'displayName': group_name, 'membership': {'memberRole': 'unknown'}})
            
            return groups
        except Exception as e:
            self.logger.error(f"Error parsing groups text: {e}")
            return []
    
    def _parse_group_info_response(self, response):
        """Parse SimpleX CLI group info response"""
        try:
            if isinstance(response, dict):
                resp = response.get('resp', {})
                if 'Right' in resp:
                    actual_resp = resp['Right']
                    if 'group' in actual_resp:
                        return actual_resp['group']
                    elif isinstance(actual_resp, dict) and 'displayName' in actual_resp:
                        return actual_resp
            return None
        except Exception as e:
            self.logger.error(f"Error parsing group info response: {e}")
            return None
    
    def _parse_group_invite_response(self, response):
        """Parse SimpleX CLI group invite response to extract invite link"""
        try:
            if isinstance(response, dict):
                resp = response.get('resp', {})
                if 'Right' in resp:
                    actual_resp = resp['Right']
                    # Look for invitation link in various possible fields
                    if isinstance(actual_resp, str):
                        if 'https://simplex.chat/invitation' in actual_resp:
                            import re
                            match = re.search(r'https://simplex\.chat/invitation[^\s]*', actual_resp)
                            if match:
                                return match.group(0)
                    elif isinstance(actual_resp, dict):
                        for key, value in actual_resp.items():
                            if isinstance(value, str) and 'https://simplex.chat/invitation' in value:
                                import re
                                match = re.search(r'https://simplex\.chat/invitation[^\s]*', value)
                                if match:
                                    return match.group(0)
            return None
        except Exception as e:
            self.logger.error(f"Error parsing group invite response: {e}")
            return None


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
                self.logger.info("🔧 Starting hot reload monitoring...")
                print("🔧 DEBUG: About to call start_hot_reloading()")
                try:
                    await self.plugin_manager.start_hot_reloading()
                    print("🔧 DEBUG: start_hot_reloading() completed successfully")
                    self.logger.info("✅ Hot reload monitoring started successfully")
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