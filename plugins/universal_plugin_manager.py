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

from .universal_plugin_base import UniversalBotPlugin, ContainerizedBotPlugin, BotAdapter, CommandContext

# Import platform services
try:
    import sys
    import os
    # Add parent directory to path for imports
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from platform_services import PlatformServiceRegistry
    from plugins.external.simplex.services import SimpleXPlatformServices
except ImportError:
    PlatformServiceRegistry = None
    SimpleXPlatformServices = None


class UniversalPluginFileHandler(FileSystemEventHandler):
    """File system event handler for plugin hot reloading"""
    
    def __init__(self, plugin_manager):
        super().__init__()
        self.plugin_manager = plugin_manager
        self.last_modified = {}
        self.debounce_time = 1.0  # 1 second debounce to avoid multiple rapid reloads
        self.logger = plugin_manager.logger
        
    def on_modified(self, event):
        self.logger.debug(f"🔔 File event received: {event.src_path}")
        self.logger.debug(f"🔔 Event is_directory: {event.is_directory}")
        
        if event.is_directory:
            self.logger.debug("🔔 Ignoring directory event")
            return
        
        self.logger.debug(f"🔔 Checking if file ends with 'plugin.py': {event.src_path.endswith('plugin.py')}")
        
        # Handle plugin file changes
        if event.src_path.endswith('plugin.py'):
            self.logger.debug(f"🔔 Plugin file modified: {event.src_path}")
            
            # Debounce rapid file changes
            current_time = time.time()
            if event.src_path in self.last_modified:
                time_diff = current_time - self.last_modified[event.src_path]
                self.logger.debug(f"🔔 Time since last modification: {time_diff:.2f}s (debounce: {self.debounce_time}s)")
                if time_diff < self.debounce_time:
                    self.logger.debug("🔔 Ignoring due to debounce")
                    return
            
            self.last_modified[event.src_path] = current_time
            self.logger.debug(f"🔔 Scheduling reload for: {event.src_path}")
            
            # Schedule reload in the main thread
            plugin_file = Path(event.src_path)
            self._schedule_reload(plugin_file)
            return
        else:
            self.logger.debug(f"🔔 Ignoring non-plugin file: {event.src_path}")
    
    def on_deleted(self, event):
        if event.is_directory:
            return
        
        if not event.src_path.endswith('plugin.py'):
            return
            
        plugin_file = Path(event.src_path)
        self._schedule_unload(plugin_file)
    
    def _schedule_reload(self, plugin_file: Path):
        """Schedule plugin reload in the main thread"""
        self.logger.debug(f"🗓️ Scheduling reload for: {plugin_file}")
        self.logger.debug(f"🗓️ Plugin manager loop: {self.plugin_manager.loop}")
        
        if self.plugin_manager.loop:
            self.logger.debug("🗓️ Submitting coroutine to event loop...")
            future = asyncio.run_coroutine_threadsafe(
                self.plugin_manager._handle_file_change(plugin_file),
                self.plugin_manager.loop
            )
            self.logger.debug(f"🗓️ Coroutine submitted: {future}")
        else:
            self.logger.debug("🗓️ No event loop available for scheduling reload!")
    
    def _schedule_unload(self, plugin_file: Path):
        """Schedule plugin unload in the main thread"""
        if self.plugin_manager.loop:
            asyncio.run_coroutine_threadsafe(
                self.plugin_manager._handle_file_deletion(plugin_file),
                self.plugin_manager.loop
            )


class UniversalPluginManager:
    """Universal plugin manager that works with bot adapters"""
    
    def __init__(self, plugins_dir: str = "plugins/external", logger: Optional[logging.Logger] = None):
        self.plugins: Dict[str, UniversalBotPlugin] = {}
        self.plugins_dir = Path(plugins_dir)
        self.failed_plugins: Dict[str, str] = {}
        self.adapter: Optional[BotAdapter] = None
        self.loop = None
        self.file_observer = None
        self.file_handler = None
        self.module_cache: Dict[str, any] = {}
        self.logger = logger if logger else logging.getLogger("universal_plugin_manager")
        
        # Platform service registry
        self.service_registry: Optional['PlatformServiceRegistry'] = None
        if PlatformServiceRegistry:
            self.service_registry = PlatformServiceRegistry(logger=self.logger)
        
        # Ensure plugins directory exists
        self.plugins_dir.mkdir(exist_ok=True)
        
        self.logger.debug(f"🔌 Universal plugin manager initialized for directory: {self.plugins_dir}")
    
    async def initialize_platform_services(self, adapter: BotAdapter):
        """Initialize platform-specific services based on the adapter"""
        if not self.service_registry:
            self.logger.warning("🔧 SERVICE REGISTRY: Platform service registry not available")
            return
        
        # Import and initialize platform services based on adapter type
        try:
            if hasattr(adapter, 'platform'):
                platform = adapter.platform
                self.logger.info(f"🔧 SERVICE REGISTRY: Initializing services for platform: {platform}")
                
                # Initialize SimpleX services if this is a SimpleX platform
                if (platform.value == "simplex" and SimpleXPlatformServices and 
                    hasattr(adapter, 'bot') and adapter.bot):
                    
                    self.logger.info("🔧 SERVICE REGISTRY: Registering SimpleX platform services")
                    simplex_services = SimpleXPlatformServices(adapter.bot, self.logger)
                    simplex_services.register_all_services(self.service_registry)
                    
                    # Store reference for message history integration
                    self.simplex_services = simplex_services
                    
                elif platform.value == "matrix":
                    self.logger.info("🔧 SERVICE REGISTRY: Matrix services not implemented yet")
                    
                elif platform.value == "discord":
                    self.logger.info("🔧 SERVICE REGISTRY: Discord services not implemented yet")
                    
                else:
                    self.logger.warning(f"🔧 SERVICE REGISTRY: Unknown platform: {platform}")
                
            else:
                self.logger.warning("🔧 SERVICE REGISTRY: Adapter does not specify platform")
                
        except Exception as e:
            self.logger.error(f"🔧 SERVICE REGISTRY: Error initializing platform services: {e}")
        
    def load_plugin_config(self) -> Dict[str, Dict[str, any]]:
        """Load plugin configuration from plugin.yml"""
        import yaml
        
        config_file = self.plugins_dir.parent / "plugin.yml"
        if not config_file.exists():
            self.logger.info("No plugin.yml found, all plugins enabled by default")
            return {}
        
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            plugins_config = config.get('plugins', {})
            self.logger.info(f"📋 Loaded plugin configuration: {len(plugins_config)} plugins configured")
            return plugins_config
        except Exception as e:
            self.logger.error(f"❌ Failed to load plugin configuration: {e}")
            return {}
    
    def is_plugin_enabled(self, plugin_name: str, config: Dict[str, Dict[str, any]]) -> bool:
        """Check if a plugin is enabled in configuration"""
        if not config:
            return True  # Default to enabled if no config
        
        plugin_config = config.get(plugin_name, {})
        enabled = plugin_config.get('enabled', True)  # Default to enabled
        
        if not enabled:
            self.logger.info(f"🚫 Plugin '{plugin_name}' disabled by configuration")
        
        return enabled
        
    async def start_hot_reloading(self):
        """Start file system monitoring for hot reloading"""
        # Use print for debugging since async logging might have issues
        print(f"🔧 DEBUG: start_hot_reloading() called")
        
        try:
            import os
            import sys
            
            print(f"🔧 DEBUG: In start_hot_reloading try block")
            
            self.logger.debug(f"📁 Setting up hot reload for directory: {self.plugins_dir}")
            print(f"📁 DEBUG: Setting up hot reload for directory: {self.plugins_dir}")
            
            self.logger.debug(f"📁 Absolute path: {self.plugins_dir.absolute()}")
            print(f"📁 DEBUG: Absolute path: {self.plugins_dir.absolute()}")
            
            self.logger.debug(f"📁 Directory exists: {self.plugins_dir.exists()}")
            print(f"📁 DEBUG: Directory exists: {self.plugins_dir.exists()}")
            
            if self.plugins_dir.exists():
                files = list(self.plugins_dir.rglob("*.py"))
                self.logger.debug(f"📁 Found {len(files)} Python files to watch")
                print(f"📁 DEBUG: Found {len(files)} Python files to watch")
                for i, f in enumerate(files[:5]):  # Show first 5 files
                    self.logger.debug(f"   📄 {f}")
                    print(f"   📄 DEBUG: File {i+1}: {f}")
            
            self.loop = asyncio.get_event_loop()
            self.logger.debug("⏰ Event loop obtained")
            print("⏰ DEBUG: Event loop obtained")
            
            self.file_handler = UniversalPluginFileHandler(self)
            self.logger.debug("📋 File handler created")
            print("📋 DEBUG: File handler created")
            
            self.file_observer = Observer()
            self.logger.debug(f"👁️ Observer created: {type(self.file_observer)}")
            print(f"👁️ DEBUG: Observer created: {type(self.file_observer)}")
            
            observer_state = getattr(self.file_observer, '_state', 'unknown')
            self.logger.debug(f"👁️ Observer state: {observer_state}")
            print(f"👁️ DEBUG: Observer state: {observer_state}")
            
            # Watch plugins directory for plugin changes
            watch_path = str(self.plugins_dir.absolute())
            self.logger.debug(f"📂 About to schedule watching of: {watch_path}")
            print(f"📂 DEBUG: About to schedule watching of: {watch_path}")
            
            watch = self.file_observer.schedule(
                self.file_handler, 
                watch_path, 
                recursive=True
            )
            self.logger.debug(f"📂 Scheduled watch object: {watch}")
            print(f"📂 DEBUG: Scheduled watch object: {watch}")
            
            self.logger.debug(f"📂 Watch path: {watch.path}")
            print(f"📂 DEBUG: Watch path: {watch.path}")
            
            self.logger.debug(f"📂 Watch recursive: {watch.is_recursive}")
            print(f"📂 DEBUG: Watch recursive: {watch.is_recursive}")
            
            self.logger.debug("🚀 Starting observer...")
            print("🚀 DEBUG: Starting observer...")
            
            self.file_observer.start()
            
            final_state = getattr(self.file_observer, '_state', 'unknown')
            is_alive = self.file_observer.is_alive()
            
            self.logger.debug(f"🚀 Observer started! State: {final_state}")
            print(f"🚀 DEBUG: Observer started! State: {final_state}")
            
            self.logger.debug(f"🚀 Observer is_alive: {is_alive}")
            print(f"🚀 DEBUG: Observer is_alive: {is_alive}")
            
            # Give it a moment to start
            import time
            time.sleep(0.1)
            
            final_final_state = getattr(self.file_observer, '_state', 'unknown')
            self.logger.debug(f"🚀 Observer final state: {final_final_state}")
            print(f"🚀 DEBUG: Observer final state: {final_final_state}")
            
            self.logger.debug("🔥 Hot reloading enabled for plugins...")
            print("🔥 DEBUG: Hot reloading enabled for plugins...")
            
        except Exception as e:
            error_msg = f"⚠️ Could not start hot reloading: {e}"
            self.logger.error(error_msg)
            print(f"DEBUG ERROR: {error_msg}")
            
            import traceback
            tb = traceback.format_exc()
            self.logger.error(f"Traceback: {tb}")
            print(f"DEBUG TRACEBACK: {tb}")
            
            # Re-raise to ensure the error is noticed
            raise
    
    async def stop_hot_reloading(self):
        """Stop file system monitoring"""
        if self.file_observer:
            self.file_observer.stop()
            self.file_observer.join()
            self.logger.debug("🔥 Hot reloading stopped")
    
    async def _handle_file_change(self, plugin_file: Path):
        """Handle plugin file modification"""
        plugin_name = plugin_file.parent.name
        self.logger.debug(f"🔥 Plugin file changed: {plugin_name}")
        
        if plugin_name in self.plugins:
            # Reload existing plugin
            await self.reload_plugin(plugin_name)
        else:
            # Load new plugin
            await self.load_plugin_from_file(plugin_file, plugin_name)
    
    async def _handle_file_deletion(self, plugin_file: Path):
        """Handle plugin file deletion"""
        plugin_name = plugin_file.parent.name
        self.logger.debug(f"🗑️ Plugin file deleted: {plugin_name}")
        
        if plugin_name in self.plugins:
            await self.unload_plugin(plugin_name)
    
    async def discover_and_load_plugins(self, adapter: BotAdapter) -> Dict[str, bool]:
        """Automatically discover and load all plugins from plugins directory"""
        self.adapter = adapter
        
        # Initialize platform services first
        await self.initialize_platform_services(adapter)
        
        results = {}
        
        # Load plugin configuration
        plugin_config = self.load_plugin_config()
        
        # Look for plugin.py files in plugin subfolders
        for plugin_dir in self.plugins_dir.iterdir():
            if plugin_dir.is_dir() and not plugin_dir.name.startswith('__'):
                plugin_file = plugin_dir / "plugin.py"
                if plugin_file.exists():
                    plugin_name = plugin_dir.name
                    
                    # Check if plugin is enabled in configuration
                    if not self.is_plugin_enabled(plugin_name, plugin_config):
                        self.logger.info(f"⏸️  Skipping disabled plugin: {plugin_name}")
                        results[plugin_name] = False
                        continue
                    
                    success = await self.load_plugin_from_file(plugin_file, plugin_name)
                    results[plugin_name] = success
            
        enabled_count = len(self.plugins)
        disabled_count = sum(1 for result in results.values() if not result and plugin_config.get(plugin_name, {}).get('enabled', True) == False)
        failed_count = len(self.failed_plugins)
        
        self.logger.info(f"✅ Plugin discovery complete: {enabled_count} loaded, {disabled_count} disabled, {failed_count} failed")
        
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
                self.logger.debug(f"🔍 Checking class {attr_name}: {attr}")
                if isinstance(attr, type):
                    is_subclass = issubclass(attr, UniversalBotPlugin)
                    not_universal = (attr != UniversalBotPlugin)
                    not_containerized = (attr != ContainerizedBotPlugin)
                    self.logger.debug(f"  issubclass(UniversalBotPlugin): {is_subclass}")
                    self.logger.debug(f"  not UniversalBotPlugin: {not_universal}")
                    self.logger.debug(f"  not ContainerizedBotPlugin: {not_containerized}")
                    
                    if (isinstance(attr, type) and 
                        issubclass(attr, UniversalBotPlugin) and 
                        attr != UniversalBotPlugin and 
                        attr != ContainerizedBotPlugin):
                        self.logger.debug(f"  *** SELECTED: {attr} ***")
                        plugin_class = attr
                        break
                    else:
                        self.logger.debug(f"  SKIPPED")
            
            self.logger.debug(f"🔍 Final plugin_class: {plugin_class}")
            
            if not plugin_class:
                raise ImportError(f"No UniversalBotPlugin subclass found in {plugin_file}")
            
            # Create plugin instance with logger
            plugin = plugin_class(logger=self.logger)
            
            # Check platform compatibility
            if not plugin.supports_platform(self.adapter.platform):
                self.logger.warning(f"Plugin {plugin.name} does not support platform {self.adapter.platform.value}")
                return False
            
            # Initialize plugin with adapter and platform services
            if await plugin.initialize(self.adapter, self.service_registry):
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
        self.logger.debug(f"🔄 Reloading plugin: {plugin_name}")
        
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
            self.logger.debug(f"✅ Plugin {plugin_name} reloaded successfully")
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
            self.logger.debug(f"✅ Enabled plugin: {plugin_name}")
            return True
        return False
    
    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a specific plugin"""
        if plugin_name in self.plugins:
            self.plugins[plugin_name].enabled = False
            self.logger.debug(f"⏸️ Disabled plugin: {plugin_name}")
            return True
        return False

    async def handle_message(self, context: CommandContext) -> Optional[str]:
        """Handle both commands and regular messages, broadcasting to all plugins"""
        self.logger.info(f"📢 PLUGIN MANAGER: handle_message called with: '{context.args_raw}' from {context.user_display_name}")
        if not self.plugins:
            self.logger.warning(f"📢 PLUGIN MANAGER: No plugins loaded!")
            return None
        
        # Store message in history service if available (for non-command messages)
        if not context.args_raw.startswith('!') and hasattr(self, 'simplex_services'):
            try:
                message_service = self.simplex_services.get_message_history_service()
                message_data = {
                    'sender': context.user_display_name,
                    'content': context.args_raw,
                    'type': 'text',
                    'user_id': context.user_id,
                    'raw_message': context.raw_message
                }
                message_service.store_message(context.chat_id, message_data)
            except Exception as e:
                self.logger.error(f"Error storing message in history: {e}")
        
        # Let all plugins process the message for context/history (non-command messages)
        if not context.args_raw.startswith('!'):
            self.logger.info(f"📢 PLUGIN MANAGER: Broadcasting non-command message to {len(self.plugins)} plugins")
            for plugin_name, plugin in self.plugins.items():
                if plugin.enabled:
                    self.logger.info(f"📢 PLUGIN MANAGER: Calling handle_message on {plugin_name}")
                    try:
                        await plugin.handle_message(context)
                        self.logger.info(f"📢 PLUGIN MANAGER: {plugin_name} handle_message completed")
                    except Exception as e:
                        self.logger.error(f"Plugin {plugin_name} message handling error: {e}")
                else:
                    self.logger.info(f"📢 PLUGIN MANAGER: Skipping disabled plugin {plugin_name}")
        else:
            self.logger.info(f"📢 PLUGIN MANAGER: Skipping command message broadcast (starts with !)")
        
        # Then handle commands if this is a command message
        if context.args_raw.startswith('!'):
            return await self.handle_command(context)
        
        return None

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
    
    async def get_plugin_status(self) -> Dict[str, any]:
        """Get status of all plugins including container status"""
        loaded_plugins = {}
        for name, plugin in self.plugins.items():
            plugin_info = plugin.get_info()
            
            # Add container status for containerized plugins
            if hasattr(plugin, 'requires_container') and plugin.requires_container():
                try:
                    container_status = await plugin.get_container_status()
                    plugin_info['container_status'] = container_status
                except Exception as e:
                    plugin_info['container_status'] = {"error": str(e)}
            
            loaded_plugins[name] = plugin_info
        
        return {
            "loaded": loaded_plugins,
            "failed": self.failed_plugins,
            "total_loaded": len(self.plugins),
            "total_failed": len(self.failed_plugins),
            "hot_reloading": self.file_observer is not None and self.file_observer.is_alive(),
            "platform": self.adapter.platform.value if self.adapter else None
        }
    
    async def start_plugin_containers(self, plugin_name: str) -> bool:
        """Start containers for a specific plugin"""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False
        
        plugin = self.plugins[plugin_name]
        if hasattr(plugin, 'requires_container') and plugin.requires_container():
            return await plugin.start_services()
        else:
            self.logger.warning(f"Plugin {plugin_name} does not require containers")
            return False
    
    async def stop_plugin_containers(self, plugin_name: str) -> bool:
        """Stop containers for a specific plugin"""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False
        
        plugin = self.plugins[plugin_name]
        if hasattr(plugin, 'requires_container') and plugin.requires_container():
            return await plugin.stop_services()
        else:
            self.logger.warning(f"Plugin {plugin_name} does not require containers")
            return False
    
    async def restart_plugin_containers(self, plugin_name: str) -> bool:
        """Restart containers for a specific plugin"""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False
        
        plugin = self.plugins[plugin_name]
        if hasattr(plugin, 'requires_container') and plugin.requires_container():
            return await plugin.restart_services()
        else:
            self.logger.warning(f"Plugin {plugin_name} does not require containers")
            return False
    
    async def cleanup_plugin_containers(self, plugin_name: str) -> bool:
        """Cleanup containers for a specific plugin"""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False
        
        plugin = self.plugins[plugin_name]
        if hasattr(plugin, 'requires_container') and plugin.requires_container():
            return await plugin.cleanup_services()
        else:
            self.logger.warning(f"Plugin {plugin_name} does not require containers")
            return False
    
    async def get_container_status(self, plugin_name: str) -> Dict[str, any]:
        """Get container status for a specific plugin"""
        if plugin_name not in self.plugins:
            return {"error": f"Plugin {plugin_name} not found"}
        
        plugin = self.plugins[plugin_name]
        if hasattr(plugin, 'requires_container') and plugin.requires_container():
            return await plugin.get_container_status()
        else:
            return {"message": f"Plugin {plugin_name} does not require containers"}
    
    async def cleanup(self):
        """Cleanup plugin manager"""
        await self.stop_hot_reloading()
        
        # Stop all containerized plugins first
        containerized_plugins = []
        regular_plugins = []
        
        for plugin in list(self.plugins.values()):
            if hasattr(plugin, 'requires_container') and plugin.requires_container():
                containerized_plugins.append(plugin)
            else:
                regular_plugins.append(plugin)
        
        # Stop containerized plugins first (they might take longer)
        if containerized_plugins:
            self.logger.info(f"🐳 Stopping {len(containerized_plugins)} containerized plugins...")
            for plugin in containerized_plugins:
                try:
                    self.logger.info(f"🐳 Stopping containers for {plugin.name}...")
                    await plugin.cleanup()
                    self.logger.info(f"✅ Stopped containers for {plugin.name}")
                except Exception as e:
                    self.logger.error(f"❌ Error stopping containers for {plugin.name}: {e}")
        
        # Cleanup regular plugins
        if regular_plugins:
            self.logger.info(f"🔌 Cleaning up {len(regular_plugins)} regular plugins...")
            for plugin in regular_plugins:
                try:
                    await plugin.cleanup()
                except Exception as e:
                    self.logger.error(f"❌ Error cleaning up {plugin.name}: {e}")
        
        self.plugins.clear()
        self.logger.info("🔌 Universal plugin manager cleanup complete")