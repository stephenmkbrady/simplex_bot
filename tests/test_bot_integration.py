"""
Integration tests for bot configuration loading and application
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
            
            # Check bot configuration is applied
            assert bot.bot_name == minimal_config['bot']['name']
            assert bot.websocket_url == minimal_config['bot']['websocket_url']
            assert bot.auto_accept_contacts == minimal_config['bot']['auto_accept_contacts']
            
            # Check media configuration
            assert bot.media_enabled == minimal_config['media']['download_enabled']
            assert str(bot.media_path) == minimal_config['media']['storage_path']
            
            # Check security configuration
            assert bot.max_message_length == minimal_config['security']['max_message_length']
            
            # Check server information
            assert bot.server_info == minimal_config['servers']
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
            assert bot.bot_name == 'Test Bot'  # From mock_env_vars
            assert bot.websocket_url == 'ws://test:3030'  # From mock_env_vars
            
            # Check server configuration from env vars
            expected_smp = ['smp://test-server1.com', 'smp://test-server2.com']
            assert bot.server_info['smp'] == expected_smp
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
            'logging': {'daily_rotation': True, 'retention_days': 30},
            'media': {'download_enabled': True, 'allowed_types': ['image']},
            'commands': {
                'enabled': ['help', 'status'],  # Only help and status enabled
                'prefix': '!'
            },
            'security': {'max_message_length': 4096}
        }
        
        config_path = temp_config_dir / "commands_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Check only enabled commands are available
            assert '!help' in bot.commands
            assert '!status' in bot.commands
            assert '!echo' not in bot.commands  # Should not be enabled
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
            
            # Check media directories are created
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
            with pytest.raises(ValueError):
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
            assert hasattr(bot, 'app_logger')
            assert hasattr(bot, 'message_logger')
            assert bot.app_logger is not None
            assert bot.message_logger is not None
        finally:
            os.chdir(original_cwd)


class TestBotMethodIntegration:
    """Test bot methods work with configuration"""
    
    @pytest.mark.asyncio
    async def test_handle_status_command_with_config(self, temp_config_dir, sample_config_dict, mock_env_vars):
        """Test !status command returns correct configuration information"""
        config_path = temp_config_dir / "status_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(sample_config_dict, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Call status command
            status_response = await bot.handle_status("test_contact")
            
            # Check status contains configuration information
            assert 'Test Bot' in status_response  # Bot name from env vars
            assert 'ws://test:3030' in status_response  # WebSocket URL from env vars
            assert 'smp://test-server1.com' in status_response  # SMP server from env vars
            assert 'xftp://test-files1.com' in status_response  # XFTP server from env vars
            assert './test_media' in status_response  # Media path from env vars
        finally:
            os.chdir(original_cwd)
    
    @pytest.mark.asyncio
    async def test_handle_help_command_with_config(self, temp_config_dir):
        """Test !help command reflects configured commands"""
        config_data = {
            'servers': {'smp': ['smp://localhost:5223']},
            'bot': {'name': 'Help Test Bot', 'websocket_url': 'ws://localhost:3030'},
            'logging': {'daily_rotation': True, 'retention_days': 30},
            'media': {'download_enabled': False, 'allowed_types': ['image']},
            'commands': {
                'enabled': ['help', 'echo'],  # Only help and echo
                'prefix': '!'
            },
            'security': {'max_message_length': 4096}
        }
        
        config_path = temp_config_dir / "help_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Call help command
            help_response = await bot.handle_help("test_contact")
            
            # Check help contains correct information
            assert 'Help Test Bot' in help_response
            assert '!help' in help_response
            assert '!echo' in help_response
            assert '!status' not in help_response  # Should not be enabled
            assert 'Media downloads: disabled' in help_response
        finally:
            os.chdir(original_cwd)
    
    def test_get_file_type_method(self, temp_config_dir, minimal_config):
        """Test file type detection method"""
        config_path = temp_config_dir / "file_type_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Test different file types
            assert bot._get_file_type("image.jpg") == "image"
            assert bot._get_file_type("video.mp4") == "video"
            assert bot._get_file_type("audio.mp3") == "audio"
            assert bot._get_file_type("document.pdf") == "document"
            assert bot._get_file_type("unknown.xyz") == "document"  # Default
        finally:
            os.chdir(original_cwd)
    
    @pytest.mark.asyncio
    async def test_send_message_respects_max_length(self, temp_config_dir):
        """Test send_message respects max_message_length configuration"""
        config_data = {
            'servers': {'smp': ['smp://localhost:5223']},
            'bot': {'name': 'Test Bot', 'websocket_url': 'ws://localhost:3030'},
            'logging': {'daily_rotation': True, 'retention_days': 30},
            'media': {'download_enabled': True, 'allowed_types': ['image']},
            'commands': {'enabled': ['help'], 'prefix': '!'},
            'security': {'max_message_length': 10}  # Very short limit for testing
        }
        
        config_path = temp_config_dir / "max_length_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            bot = SimplexChatBot(str(config_path))
            
            # Mock the send_command method to avoid actual WebSocket connection
            bot.send_command = AsyncMock()
            
            # Test with long message
            long_message = "This is a very long message that exceeds the limit"
            await bot.send_message("test_contact", long_message)
            
            # Check that send_command was called with truncated message
            bot.send_command.assert_called_once()
            call_args = bot.send_command.call_args[0][0]  # Get the command argument
            
            # The command should contain truncated message with "..."
            assert len(call_args) <= len("@test_contact ") + 10 + len("...")
            assert "..." in call_args
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
            'logging': {'daily_rotation': True},
            'media': {'download_enabled': True},
            'commands': {'enabled': ['help']},
            'security': {'max_message_length': 4096}
        }
        
        config_path = temp_config_dir / "minimal_required.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_required, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            # Should initialize successfully with defaults for missing keys
            bot = SimplexChatBot(str(config_path))
            
            # Check defaults are applied
            assert bot.auto_accept_contacts is True  # Should default to True
        finally:
            os.chdir(original_cwd)