"""
Integration tests for bot configuration loading and application with refactored architecture
"""

import pytest
import asyncio
import tempfile
import yaml
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

# Import bot class
from bot import SimplexChatBot, DailyRotatingLogger


class TestBotConfigurationIntegration:
    """Test bot integration with configuration system"""
    
    def test_bot_initialization_with_config(self, temp_config_dir, minimal_config):
        """Test bot initializes correctly with configuration file"""
        config_path = temp_config_dir / "bot_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Check bot configuration is applied correctly
            assert bot.config.get('name') == minimal_config['bot']['name']
            assert bot.config.get('websocket_url') == minimal_config['bot']['websocket_url']
            assert bot.config.get('auto_accept_contacts') == minimal_config['bot']['auto_accept_contacts']
            
            # Check components are initialized
            assert bot.websocket_manager is not None
            assert bot.file_download_manager is not None
            assert bot.message_handler is not None
            assert bot.command_registry is not None
            
            # Check media configuration through file download manager
            assert bot.file_download_manager.media_enabled == minimal_config['media']['download_enabled']
            assert str(bot.file_download_manager.media_path) == minimal_config['media']['storage_path']
            
        finally:
            os.chdir(original_cwd)
    
    def test_bot_with_environment_variables(self, temp_config_dir, sample_config_dict, mock_env_vars):
        """Test bot configuration with environment variable substitution"""
        config_path = temp_config_dir / "env_bot_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(sample_config_dict, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Check environment variables are substituted
            assert bot.config.get('name') == 'Test Bot'  # From mock_env_vars
            assert bot.config.get('websocket_url') == 'ws://test:3030'  # From mock_env_vars
            
        finally:
            os.chdir(original_cwd)
    
    def test_bot_commands_configuration(self, temp_config_dir):
        """Test bot command configuration"""
        config_data = {
            'servers': {'smp': ['smp://localhost:5223']},
            'bot': {
                'name': 'Test Bot',
                'websocket_url': 'ws://localhost:3030',
                'auto_accept_contacts': True
            },
            'logging': {'daily_rotation': True, 'retention_days': 30, 'log_level': 'INFO'},
            'media': {'download_enabled': True, 'allowed_types': ['image'], 'storage_path': './media', 'max_file_size': '100MB'},
            'commands': {
                'enabled': ['help', 'status'],  # Only help and status enabled
                'prefix': '!'
            },
            'security': {'max_message_length': 4096, 'rate_limit_messages': 10, 'rate_limit_window': 60},
            'xftp': {'cli_path': '/usr/local/bin/xftp', 'temp_dir': './temp/xftp', 'timeout': 300}
        }
        
        config_path = temp_config_dir / "commands_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Check available commands in command registry
            available_commands = bot.command_registry.list_commands()
            assert 'help' in available_commands
            assert 'status' in available_commands
            assert 'ping' in available_commands  # Default commands are always available
            assert 'stats' in available_commands  # Default commands are always available
            
        finally:
            os.chdir(original_cwd)
    
    def test_bot_media_directory_creation(self, temp_config_dir, minimal_config):
        """Test bot creates media directories on initialization"""
        # Use a custom media path for testing
        test_media_path = temp_config_dir / "test_media"
        minimal_config['media']['storage_path'] = str(test_media_path)
        
        config_path = temp_config_dir / "media_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Check media directories are created through file download manager
            assert test_media_path.exists()
            assert (test_media_path / "images").exists()
            assert (test_media_path / "videos").exists()
            assert (test_media_path / "documents").exists()
            assert (test_media_path / "audio").exists()
            
        finally:
            os.chdir(original_cwd)
    
    def test_bot_with_invalid_config_fails(self, temp_config_dir, invalid_config):
        """Test bot initialization fails with invalid configuration"""
        config_path = temp_config_dir / "invalid_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(invalid_config, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            with pytest.raises((ValueError, KeyError, TypeError)):
                SimplexChatBot(str(config_path))
        finally:
            os.chdir(original_cwd)


class TestBotLoggingIntegration:
    """Test bot logging configuration integration"""
    
    def test_daily_rotating_logger_initialization(self, temp_config_dir):
        """Test DailyRotatingLogger initialization"""
        logging_config = {
            'daily_rotation': True,
            'message_log_separate': True,
            'retention_days': 7,
            'log_level': 'DEBUG'
        }
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            logger_setup = DailyRotatingLogger('test.app', 'test.messages', logging_config)
            
            # Check loggers are created
            assert logger_setup.app_logger is not None
            assert logger_setup.message_logger is not None
            
            # Check log directory is created
            log_dir = temp_config_dir / "logs"
            assert log_dir.exists()
        finally:
            os.chdir(original_cwd)
    
    def test_bot_logging_setup(self, temp_config_dir, minimal_config):
        """Test bot logging is set up correctly"""
        # Configure logging settings
        minimal_config['logging'] = {
            'daily_rotation': True,
            'message_log_separate': True,
            'retention_days': 14,
            'log_level': 'INFO'
        }
        
        config_path = temp_config_dir / "logging_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Check loggers are available
            assert hasattr(bot, 'logger')
            assert hasattr(bot, 'message_logger')
            assert bot.logger is not None
            assert bot.message_logger is not None
        finally:
            os.chdir(original_cwd)


class TestBotMethodIntegration:
    """Test bot methods work with configuration"""
    
    @pytest.mark.asyncio
    async def test_command_execution_with_config(self, temp_config_dir, minimal_config):
        """Test command execution works correctly"""
        config_path = temp_config_dir / "command_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Test command detection
            assert bot.command_registry.is_command('!help') == True
            assert bot.command_registry.is_command('!status') == True
            assert bot.command_registry.is_command('hello') == False
            
            # Test command execution
            result = await bot.command_registry.execute_command('!help', 'test_user')
            assert result is not None
            assert 'commands' in result.lower()
            
        finally:
            os.chdir(original_cwd)
    
    def test_file_type_detection_method(self, temp_config_dir, minimal_config):
        """Test file type detection method in file download manager"""
        config_path = temp_config_dir / "file_type_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Test different file types through file download manager
            assert bot.file_download_manager._get_file_type("image.jpg") == "image"
            assert bot.file_download_manager._get_file_type("video.mp4") == "video"
            assert bot.file_download_manager._get_file_type("audio.mp3") == "audio"
            assert bot.file_download_manager._get_file_type("document.pdf") == "document"
            assert bot.file_download_manager._get_file_type("unknown.xyz") == "document"  # Default
            
        finally:
            os.chdir(original_cwd)
    
    @pytest.mark.asyncio
    async def test_websocket_message_sending(self, temp_config_dir, minimal_config):
        """Test WebSocket message sending respects configuration"""
        config_path = temp_config_dir / "websocket_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Mock the websocket send_command method
            bot.websocket_manager.send_command = AsyncMock()
            
            # Test message sending
            await bot.websocket_manager.send_message("test_contact", "test message")
            
            # Check that send_command was called
            bot.websocket_manager.send_command.assert_called_once()
            
        finally:
            os.chdir(original_cwd)

    def test_component_dependency_injection(self, temp_config_dir, minimal_config):
        """Test that components are properly dependency injected"""
        config_path = temp_config_dir / "dependency_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Test dependency injection relationships
            assert bot.message_handler.command_registry == bot.command_registry
            assert bot.message_handler.file_download_manager == bot.file_download_manager
            assert bot.file_download_manager.xftp_client == bot.xftp_client
            
            # Test that send_message_callback is properly injected
            assert bot.message_handler.send_message_callback == bot.websocket_manager.send_message
            
        finally:
            os.chdir(original_cwd)


class TestConfigurationErrors:
    """Test error handling in configuration loading"""
    
    def test_config_manager_initialization_error_propagates(self, temp_config_dir):
        """Test that ConfigManager errors propagate to bot initialization"""
        # Create a file that's not valid YAML
        config_path = temp_config_dir / "invalid_yaml.yml"
        with open(config_path, 'w') as f:
            f.write("invalid: yaml: content: [\n")
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            with pytest.raises(yaml.YAMLError):
                SimplexChatBot(str(config_path))
        finally:
            os.chdir(original_cwd)
    
    def test_bot_handles_missing_optional_config_sections(self, temp_config_dir):
        """Test bot handles missing optional configuration gracefully"""
        # Minimal config with only required sections
        minimal_required = {
            'servers': {'smp': ['smp://localhost:5223']},
            'bot': {'name': 'Test', 'websocket_url': 'ws://localhost:3030'},
            'logging': {'daily_rotation': True, 'log_level': 'INFO'},
            'media': {'download_enabled': True, 'storage_path': './media', 'max_file_size': '100MB', 'allowed_types': ['image']},
            'commands': {'enabled': ['help']},
            'security': {'max_message_length': 4096},
            'xftp': {'cli_path': '/usr/local/bin/xftp', 'temp_dir': './temp/xftp', 'timeout': 300}
        }
        
        config_path = temp_config_dir / "minimal_required.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_required, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            # Should initialize successfully with defaults for missing keys
            bot = SimplexChatBot(str(config_path))
            
            # Check defaults are applied - auto_accept_contacts should default if not specified
            # The exact default depends on the configuration loading logic
            assert bot.config.get('auto_accept_contacts') is not None
            
        finally:
            os.chdir(original_cwd)

    def test_component_initialization_with_minimal_config(self, temp_config_dir):
        """Test all components initialize correctly with minimal configuration"""
        minimal_config = {
            'servers': {'smp': ['smp://localhost:5223'], 'xftp': ['xftp://localhost:443']},
            'bot': {'name': 'Test Bot', 'websocket_url': 'ws://localhost:3030', 'auto_accept_contacts': True},
            'logging': {'daily_rotation': True, 'log_level': 'INFO', 'retention_days': 30},
            'media': {
                'download_enabled': True, 
                'storage_path': './media', 
                'max_file_size': '100MB', 
                'allowed_types': ['image', 'video', 'document', 'audio']
            },
            'commands': {'enabled': ['help', 'status'], 'prefix': '!'},
            'security': {'max_message_length': 4096, 'rate_limit_messages': 10, 'rate_limit_window': 60},
            'xftp': {'cli_path': '/usr/local/bin/xftp', 'temp_dir': './temp/xftp', 'timeout': 300, 'max_file_size': 1073741824, 'retry_attempts': 3, 'cleanup_on_failure': True}
        }
        
        config_path = temp_config_dir / "component_init_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Verify all components are properly initialized
            assert bot.websocket_manager is not None
            assert bot.file_download_manager is not None
            assert bot.message_handler is not None
            assert bot.command_registry is not None
            assert bot.xftp_client is not None
            
            # Verify component types
            assert hasattr(bot.websocket_manager, 'websocket_url')
            assert hasattr(bot.file_download_manager, 'media_enabled')
            assert hasattr(bot.message_handler, 'command_registry')
            assert hasattr(bot.command_registry, 'commands')
            assert hasattr(bot.xftp_client, 'cli_path')
            
        finally:
            os.chdir(original_cwd)