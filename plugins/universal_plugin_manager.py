"""
Universal Plugin Manager

Enhanced plugin manager that works with universal plugins and bot adapters.
Supports hot reloading and works across different bot platforms.
"""

import os
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import asyncio
import threading
import time
import logging

from .universal_plugin_base import UniversalBotPlugin, BotAdapter, CommandContext


class UniversalPluginFileHandler(FileSystemEventHandler):
    """File system event handler for plugin hot reloading"""
    
    def __init__(self, plugin_manager):
        super().__init__()
        self.plugin_manager = plugin_manager
        self.last_modified = {}
        self.debounce_time = 1.0  # 1 second debounce to avoid multiple rapid reloads
        self.logger = logging.getLogger("plugin_file_handler")
        
    def on_modified(self, event):
        if event.is_directory:
            return
        
        # Handle plugin file changes
        if event.src_path.endswith('plugin.py'):
            # Debounce rapid file changes
            current_time = time.time()
            if event.src_path in self.last_modified:
                if current_time - self.last_modified[event.src_path] < self.debounce_time:
                    return
            
            self.last_modified[event.src_path] = current_time
            
            # Schedule reload in the main thread
            plugin_file = Path(event.src_path)
            self._schedule_reload(plugin_file)
            return
    
    def on_deleted(self, event):
        if event.is_directory:
            return
        
        if not event.src_path.endswith('plugin.py'):
            return
            
        plugin_file = Path(event.src_path)
        self._schedule_unload(plugin_file)
    
    def _schedule_reload(self, plugin_file: Path):
        """Schedule plugin reload in the main thread"""
        if self.plugin_manager.loop:
            asyncio.run_coroutine_threadsafe(
                self.plugin_manager._handle_file_change(plugin_file),
                self.plugin_manager.loop
            )
    
    def _schedule_unload(self, plugin_file: Path):
        """Schedule plugin unload in the main thread"""
        if self.plugin_manager.loop:
            asyncio.run_coroutine_threadsafe(
                self.plugin_manager._handle_file_deletion(plugin_file),
                self.plugin_manager.loop
            )


class UniversalPluginManager:
    """Universal plugin manager that works with bot adapters"""
    
    def __init__(self, plugins_dir: str = "plugins/external"):
        self.plugins: Dict[str, UniversalBotPlugin] = {}
        self.plugins_dir = Path(plugins_dir)
        self.failed_plugins: Dict[str, str] = {}
        self.adapter: Optional[BotAdapter] = None
        self.loop = None
        self.file_observer = None
        self.file_handler = None
        self.module_cache: Dict[str, any] = {}
        self.logger = logging.getLogger("universal_plugin_manager")
        
        # Ensure plugins directory exists
        self.plugins_dir.mkdir(exist_ok=True)
        
        self.logger.info(f"🔌 Universal plugin manager initialized for directory: {self.plugins_dir}")
        
    async def start_hot_reloading(self):
        """Start file system monitoring for hot reloading"""
        try:
            self.loop = asyncio.get_event_loop()
            self.file_handler = UniversalPluginFileHandler(self)
            self.file_observer = Observer()
            
            # Watch plugins directory for plugin changes
            self.file_observer.schedule(
                self.file_handler, 
                str(self.plugins_dir), 
                recursive=True
            )
            
            self.file_observer.start()
            self.logger.info("🔥 Hot reloading enabled for plugins...")
            
        except Exception as e:
            self.logger.error(f"⚠️ Could not start hot reloading: {e}")
    
    async def stop_hot_reloading(self):
        """Stop file system monitoring"""
        if self.file_observer:
            self.file_observer.stop()
            self.file_observer.join()
            self.logger.info("🔥 Hot reloading stopped")
    
    async def _handle_file_change(self, plugin_file: Path):
        """Handle plugin file modification"""
        plugin_name = plugin_file.parent.name
        self.logger.info(f"🔥 Plugin file changed: {plugin_name}")
        
        if plugin_name in self.plugins:
            # Reload existing plugin
            await self.reload_plugin(plugin_name)
        else:
            # Load new plugin
            await self.load_plugin_from_file(plugin_file, plugin_name)
    
    async def _handle_file_deletion(self, plugin_file: Path):
        """Handle plugin file deletion"""
        plugin_name = plugin_file.parent.name
        self.logger.info(f"🗑️ Plugin file deleted: {plugin_name}")
        
        if plugin_name in self.plugins:
            await self.unload_plugin(plugin_name)
    
    async def discover_and_load_plugins(self, adapter: BotAdapter) -> Dict[str, bool]:
        """Automatically discover and load all plugins from plugins directory"""
        self.adapter = adapter
        results = {}
        
        # Look for plugin.py files in plugin subfolders
        for plugin_dir in self.plugins_dir.iterdir():
            if plugin_dir.is_dir() and not plugin_dir.name.startswith('__'):
                plugin_file = plugin_dir / "plugin.py"
                if plugin_file.exists():
                    plugin_name = plugin_dir.name
                    success = await self.load_plugin_from_file(plugin_file, plugin_name)
                    results[plugin_name] = success
            
        self.logger.info(f"✅ Plugin discovery complete: {len(self.plugins)} loaded, {len(self.failed_plugins)} failed")
        
        # Start hot reloading after initial load
        await self.start_hot_reloading()
        
        return results
    
    async def load_plugin_from_file(self, plugin_file: Path, plugin_name: str = None) -> bool:
        """Load a specific plugin from file"""
        if plugin_name is None:
            plugin_name = plugin_file.stem
        
        try:
            # Remove from cache if exists (for hot reloading)
            # Build module name relative to plugins_dir
            relative_plugin_dir = str(self.plugins_dir).replace('/', '.')
            module_name = f"{relative_plugin_dir}.{plugin_name}.plugin"
            if module_name in sys.modules:
                del sys.modules[module_name]
            
            # Also remove the parent module if exists
            parent_module_name = f"{relative_plugin_dir}.{plugin_name}"
            if parent_module_name in sys.modules:
                del sys.modules[parent_module_name]
            
            # Dynamically import the plugin module
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if not spec or not spec.loader:
                raise ImportError(f"Could not load spec for {plugin_file}")
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find plugin class - look for classes that inherit from UniversalBotPlugin
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, UniversalBotPlugin) and 
                    attr != UniversalBotPlugin):
                    plugin_class = attr
                    break
            
            if not plugin_class:
                raise ImportError(f"No UniversalBotPlugin subclass found in {plugin_file}")
            
            # Create plugin instance
            plugin = plugin_class()
            
            # Check platform compatibility
            if not plugin.supports_platform(self.adapter.platform):
                self.logger.warning(f"Plugin {plugin.name} does not support platform {self.adapter.platform.value}")
                return False
            
            # Initialize plugin with adapter
            if await plugin.initialize(self.adapter):
                # Cleanup old plugin if reloading
                if plugin.name in self.plugins:
                    old_plugin = self.plugins[plugin.name]
                    await old_plugin.cleanup()
                
                self.plugins[plugin.name] = plugin
                self.failed_plugins.pop(plugin_name, None)  # Clear any previous failures
                self.logger.info(f"✅ Loaded plugin: {plugin.name} v{plugin.version} for {self.adapter.platform.value}")
                return True
            else:
                raise Exception("Plugin initialization failed")
                
        except Exception as e:
            error_msg = f"Failed to load plugin {plugin_name}: {e}"
            self.logger.error(error_msg)
            self.failed_plugins[plugin_name] = str(e)
            return False
    
    async def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a specific plugin"""
        self.logger.info(f"🔄 Reloading plugin: {plugin_name}")
        
        # Find the plugin file in subfolder
        plugin_file = self.plugins_dir / plugin_name / "plugin.py"
        if not plugin_file.exists():
            self.logger.error(f"❌ Plugin file not found: {plugin_file}")
            return False
        
        # Unload current plugin
        if plugin_name in self.plugins:
            await self.unload_plugin(plugin_name, announce=False)
        
        # Load new version
        success = await self.load_plugin_from_file(plugin_file, plugin_name)
        
        if success:
            self.logger.info(f"✅ Plugin {plugin_name} reloaded successfully")
        else:
            self.logger.error(f"❌ Failed to reload plugin {plugin_name}")
        
        return success
    
    async def unload_plugin(self, plugin_name: str, announce: bool = True) -> bool:
        """Unload a specific plugin"""
        if plugin_name not in self.plugins:
            return False
        
        try:
            # Cleanup plugin
            plugin = self.plugins[plugin_name]
            await plugin.cleanup()
            
            # Remove from active plugins
            del self.plugins[plugin_name]
            
            if announce:
                self.logger.info(f"🗑️ Unloaded plugin: {plugin_name}")
            
            return True
        except Exception as e:
            self.logger.error(f"❌ Error unloading plugin {plugin_name}: {e}")
            return False
    
    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a specific plugin"""
        if plugin_name in self.plugins:
            self.plugins[plugin_name].enabled = True
            self.logger.info(f"✅ Enabled plugin: {plugin_name}")
            return True
        return False
    
    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a specific plugin"""
        if plugin_name in self.plugins:
            self.plugins[plugin_name].enabled = False
            self.logger.info(f"⏸️ Disabled plugin: {plugin_name}")
            return True
        return False

    async def handle_command(self, context: CommandContext) -> Optional[str]:
        """Try to handle command with available plugins"""
        for plugin in self.plugins.values():
            if plugin.enabled and plugin.can_handle(context.command):
                try:
                    result = await plugin.handle_command(context)
                    if result is not None:
                        return result
                except Exception as e:
                    self.logger.error(f"❌ Plugin {plugin.name} error handling {context.command}: {e}")
                    # Continue to next plugin instead of crashing
                    continue
        return None
    
    def get_all_commands(self) -> Dict[str, str]:
        """Get all available commands mapped to plugin names"""
        commands = {}
        for plugin in self.plugins.values():
            if plugin.enabled:
                for cmd in plugin.get_commands():
                    commands[cmd] = plugin.name
        return commands
    
    def get_plugin_status(self) -> Dict[str, any]:
        """Get status of all plugins"""
        return {
            "loaded": {name: plugin.get_info() for name, plugin in self.plugins.items()},
            "failed": self.failed_plugins,
            "total_loaded": len(self.plugins),
            "total_failed": len(self.failed_plugins),
            "hot_reloading": self.file_observer is not None and self.file_observer.is_alive(),
            "platform": self.adapter.platform.value if self.adapter else None
        }
    
    async def cleanup(self):
        """Cleanup plugin manager"""
        await self.stop_hot_reloading()
        
        # Cleanup all plugins
        for plugin in list(self.plugins.values()):
            await plugin.cleanup()
        
        self.plugins.clear()
        self.logger.info("🔌 Universal plugin manager cleanup complete")