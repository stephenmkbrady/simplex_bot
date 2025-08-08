"""
Universal Plugin Base Classes for Multi-Bot Support

This module provides universal plugin interfaces that can work across different bot platforms
(Matrix, SimpleX, Discord, etc.) using bot-specific adapters.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import os
import subprocess
import asyncio
import aiohttp
import logging
from pathlib import Path


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
    
    def __init__(self, name: str, logger = None):
        self.name = name
        self.enabled = True
        self.version = "1.0.0"
        self.description = "A universal bot plugin"
        self.adapter: Optional[BotAdapter] = None
        self.logger = logger
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
        info = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "enabled": self.enabled,
            "commands": self.get_commands(),
            "supported_platforms": [p.value for p in self.supported_platforms],
            "current_platform": self.adapter.platform.value if self.adapter else None,
            "containerized": self.requires_container() if hasattr(self, 'requires_container') else False
        }
        return info
    
    def requires_container(self) -> bool:
        """Check if this plugin requires Docker containers"""
        return False
    
    def get_help(self) -> str:
        """Return help text for this plugin"""
        return f"{self.description} - Commands: {', '.join(self.get_commands())}"
    
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


class ContainerizedBotPlugin(UniversalBotPlugin):
    """Base class for plugins that require Docker containers"""
    
    def __init__(self, name: str, logger=None, service_host="localhost", service_port=8001):
        super().__init__(name, logger)
        self.service_host = service_host
        self.service_port = service_port
        self.http_client: Optional[aiohttp.ClientSession] = None
        self.plugin_dir = Path(__file__).parent if hasattr(self, '__file__') else Path.cwd()
        
        # Setup logger if not provided
        if not self.logger:
            self.logger = logging.getLogger(f"plugin.{self.name}")
    
    def requires_container(self) -> bool:
        """This plugin requires Docker containers"""
        return True
    
    @abstractmethod
    def get_commands(self) -> List[str]:
        """Return list of commands this plugin handles"""
        pass
    
    @abstractmethod
    async def handle_command(self, context: CommandContext) -> Optional[str]:
        """Handle a command and return response or None"""
        pass
    
    def get_docker_compose_path(self) -> Path:
        """Get path to plugin's docker-compose.yml"""
        return self.plugin_dir / "docker-compose.yml"
    
    async def send_http_request(self, endpoint: str, data: Optional[Dict] = None, method: str = "GET") -> Dict[str, Any]:
        """Send HTTP request to plugin service"""
        if not self.http_client:
            self.http_client = aiohttp.ClientSession()
        
        url = f"http://{self.service_host}:{self.service_port}{endpoint}"
        try:
            if method.upper() == "POST" and data:
                async with self.http_client.post(url, json=data) as response:
                    return await response.json()
            else:
                async with self.http_client.get(url) as response:
                    return await response.json()
        except Exception as e:
            self.logger.error(f"HTTP request to {url} failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def health_check(self) -> bool:
        """Check if plugin service is healthy"""
        try:
            result = await self.send_http_request("/health")
            return result.get("status") == "healthy"
        except:
            return False
    
    async def start_services(self) -> bool:
        """Start required Docker services"""
        compose_file = self.get_docker_compose_path()
        if not compose_file.exists():
            self.logger.error(f"docker-compose.yml not found at {compose_file}")
            return False
        
        try:
            env = os.environ.copy()
            env['PLUGIN_INSTANCE_ID'] = self.name
            env['PLUGIN_NAME'] = self.name
            
            self.logger.info(f"Starting Docker services for {self.name} plugin...")
            result = subprocess.run([
                "docker", "compose", "-f", str(compose_file),
                "-p", f"plugin-{self.name}",  # Isolated project namespace
                "up", "-d"
            ], cwd=compose_file.parent, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"Successfully started containers for {self.name} plugin")
                
                # Wait for service to be ready
                for attempt in range(30):  # 30 second timeout
                    if await self.health_check():
                        self.logger.info(f"Service health check passed for {self.name} plugin")
                        return True
                    await asyncio.sleep(1)
                
                self.logger.warning(f"Service health check failed for {self.name} plugin")
                return True  # Container started but health check failed
            else:
                self.logger.error(f"Failed to start containers for {self.name} plugin: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting services for {self.name} plugin: {e}")
            return False
    
    async def stop_services(self) -> bool:
        """Stop Docker services"""
        compose_file = self.get_docker_compose_path()
        if not compose_file.exists():
            return True  # Nothing to stop
        
        try:
            self.logger.info(f"Stopping Docker services for {self.name} plugin...")
            result = subprocess.run([
                "docker", "compose", "-f", str(compose_file),
                "-p", f"plugin-{self.name}",
                "down"
            ], cwd=compose_file.parent, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"Successfully stopped containers for {self.name} plugin")
                return True
            else:
                self.logger.error(f"Failed to stop containers for {self.name} plugin: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error stopping services for {self.name} plugin: {e}")
            return False
    
    async def restart_services(self) -> bool:
        """Restart Docker services"""
        await self.stop_services()
        return await self.start_services()
    
    async def cleanup_services(self) -> bool:
        """Complete cleanup including volumes and orphaned containers"""
        compose_file = self.get_docker_compose_path()
        if not compose_file.exists():
            return True
        
        try:
            self.logger.info(f"Cleaning up Docker services for {self.name} plugin...")
            result = subprocess.run([
                "docker", "compose", "-f", str(compose_file),
                "-p", f"plugin-{self.name}",
                "down", "--volumes", "--remove-orphans"
            ], cwd=compose_file.parent, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"Successfully cleaned up containers for {self.name} plugin")
                return True
            else:
                self.logger.error(f"Failed to cleanup containers for {self.name} plugin: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error cleaning up services for {self.name} plugin: {e}")
            return False
    
    async def get_container_status(self) -> Dict[str, Any]:
        """Get detailed container status"""
        try:
            result = subprocess.run([
                "docker", "compose", "-p", f"plugin-{self.name}", "ps", "--format", "json"
            ], capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                import json
                containers = []
                for line in result.stdout.strip().split('\n'):
                    try:
                        containers.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                
                return {
                    "plugin": self.name,
                    "containers": containers,
                    "healthy": await self.health_check(),
                    "last_check": asyncio.get_event_loop().time()
                }
            else:
                return {
                    "plugin": self.name,
                    "containers": [],
                    "healthy": False,
                    "last_check": asyncio.get_event_loop().time()
                }
                
        except Exception as e:
            self.logger.error(f"Error getting container status for {self.name}: {e}")
            return {
                "plugin": self.name,
                "containers": [],
                "healthy": False,
                "error": str(e),
                "last_check": asyncio.get_event_loop().time()
            }
    
    async def initialize(self, adapter: BotAdapter) -> bool:
        """Initialize plugin with automatic container startup"""
        # Call parent initialization
        if not await super().initialize(adapter):
            return False
        
        # Start containers if they exist
        if self.get_docker_compose_path().exists():
            container_started = await self.start_services()
            if not container_started:
                self.logger.warning(f"Failed to start containers for {self.name}, but plugin will continue")
        
        return True
    
    async def cleanup(self):
        """Cleanup plugin and stop containers"""
        # Stop containers
        if self.get_docker_compose_path().exists():
            await self.stop_services()
        
        # Close HTTP client
        if self.http_client:
            await self.http_client.close()
        
        # Call parent cleanup
        await super().cleanup()


# Backward compatibility - alias to the old name
BotPlugin = UniversalBotPlugin