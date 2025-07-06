"""
Universal Plugin Base Classes for Multi-Bot Support

This module provides universal plugin interfaces that can work across different bot platforms
(Matrix, SimpleX, Discord, etc.) using bot-specific adapters.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class BotPlatform(Enum):
    """Supported bot platforms"""
    MATRIX = "matrix"
    SIMPLEX = "simplex"
    DISCORD = "discord"
    TELEGRAM = "telegram"


@dataclass
class CommandContext:
    """Universal command context that works across different bot platforms"""
    command: str                    # The command name (without prefix)
    args: List[str]                # Command arguments as list
    args_raw: str                  # Raw arguments string
    user_id: str                   # Platform-specific user identifier
    chat_id: str                   # Platform-specific chat/room identifier
    user_display_name: str         # Human-readable user name
    platform: BotPlatform          # Which bot platform this is from
    raw_message: Dict[str, Any]     # Platform-specific raw message data
    
    # Helper properties
    @property
    def has_args(self) -> bool:
        """Check if command has arguments"""
        return bool(self.args_raw.strip())
    
    @property
    def arg_count(self) -> int:
        """Get number of arguments"""
        return len(self.args)
    
    def get_arg(self, index: int, default: str = "") -> str:
        """Get argument by index with default"""
        return self.args[index] if index < len(self.args) else default


class BotAdapter(ABC):
    """Abstract adapter interface for different bot platforms"""
    
    def __init__(self, bot_instance, platform: BotPlatform):
        self.bot = bot_instance
        self.platform = platform
    
    @abstractmethod
    async def send_message(self, message: str, context: CommandContext) -> bool:
        """Send a message back to the user/chat"""
        pass
    
    @abstractmethod
    async def send_file(self, file_path: str, context: CommandContext, caption: str = "") -> bool:
        """Send a file to the user/chat"""
        pass
    
    @abstractmethod
    def normalize_context(self, platform_data: Dict[str, Any]) -> CommandContext:
        """Convert platform-specific data to universal CommandContext"""
        pass
    
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user information (optional, platform-dependent)"""
        return {}
    
    async def download_file(self, file_info: Dict[str, Any]) -> Optional[str]:
        """Download a file (optional, platform-dependent)"""
        return None


class UniversalBotPlugin(ABC):
    """Universal plugin base class that works across different bot platforms"""
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self.version = "1.0.0"
        self.description = "A universal bot plugin"
        self.adapter: Optional[BotAdapter] = None
        self.supported_platforms = [BotPlatform.MATRIX, BotPlatform.SIMPLEX]  # Override in subclasses
    
    @abstractmethod
    def get_commands(self) -> List[str]:
        """Return list of commands this plugin handles"""
        pass
    
    @abstractmethod
    async def handle_command(self, context: CommandContext) -> Optional[str]:
        """Handle a command and return response or None"""
        pass
    
    async def initialize(self, adapter: BotAdapter) -> bool:
        """Initialize plugin with bot adapter. Return True if successful."""
        self.adapter = adapter
        
        # Check if this plugin supports the current platform
        if adapter.platform not in self.supported_platforms:
            return False
        
        return True
    
    async def cleanup(self):
        """Cleanup when plugin is disabled/unloaded"""
        pass
    
    def can_handle(self, command: str) -> bool:
        """Check if this plugin can handle the command"""
        return command in self.get_commands()
    
    def supports_platform(self, platform: BotPlatform) -> bool:
        """Check if plugin supports a specific platform"""
        return platform in self.supported_platforms
    
    def get_info(self) -> Dict[str, Any]:
        """Return plugin information"""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "enabled": self.enabled,
            "commands": self.get_commands(),
            "supported_platforms": [p.value for p in self.supported_platforms],
            "current_platform": self.adapter.platform.value if self.adapter else None
        }
    
    # Convenience methods for plugin developers
    async def send_message(self, message: str, context: CommandContext) -> bool:
        """Send a message using the bot adapter"""
        if self.adapter:
            return await self.adapter.send_message(message, context)
        return False
    
    async def send_file(self, file_path: str, context: CommandContext, caption: str = "") -> bool:
        """Send a file using the bot adapter"""
        if self.adapter:
            return await self.adapter.send_file(file_path, context, caption)
        return False
    
    async def download_file(self, file_info: Dict[str, Any]) -> Optional[str]:
        """Download a file using the bot adapter"""
        if self.adapter:
            return await self.adapter.download_file(file_info)
        return None


# Backward compatibility - alias to the old name
BotPlugin = UniversalBotPlugin