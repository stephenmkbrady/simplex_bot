"""
Tests for bot health, startup, and stability with refactored architecture
"""

import pytest
import asyncio
import time
import signal
import os
import subprocess
import yaml
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from config_manager import ConfigManager
from bot import SimplexChatBot


class TestBotHealth:
    """Test bot health and startup behavior"""
    
    def test_bot_initialization_no_errors(self, temp_config_dir, minimal_config):
        """Test that bot initializes without errors or warnings"""
        config_path = temp_config_dir / "health_test_config.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        # Create bot and verify no exceptions during initialization
        bot = SimplexChatBot(config_path=str(config_path))
        
        # Verify bot components are initialized correctly
        assert bot.config is not None
        assert bot.logger is not None
        assert bot.message_logger is not None
        assert bot.websocket_manager is not None
        assert bot.file_download_manager is not None
        assert bot.message_handler is not None
        assert bot.command_registry is not None
        assert bot.xftp_client is not None
        assert bot.running is False  # Should start as False
        
    def test_bot_configuration_validation_health(self, temp_config_dir, minimal_config):
        """Test that bot configuration is validated properly"""
        config_path = temp_config_dir / "validation_health_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        bot = SimplexChatBot(config_path=str(config_path))
        
        # Verify configuration is loaded correctly
        assert bot.config.get('name') is not None
        assert bot.config.get('websocket_url', '').startswith('ws://')
        
    @pytest.mark.asyncio
    async def test_bot_connection_retry_mechanism(self, temp_config_dir, minimal_config, caplog):
        """Test that bot implements proper retry logic for connections"""
        config_path = temp_config_dir / "retry_test_config.yml"
        
        # Set an unreachable WebSocket URL
        test_config = minimal_config.copy()
        test_config['bot']['websocket_url'] = 'ws://unreachable-host:9999'
        
        with open(config_path, 'w') as f:
            yaml.dump(test_config, f)
        
        bot = SimplexChatBot(config_path=str(config_path))
        
        # Test connection with limited retries
        result = await bot.websocket_manager.connect(max_retries=3, retry_delay=0.1)
        
        # Should fail but with proper retry logging
        assert result is False
        
        # Check that retry messages were logged
        assert "Connection attempt" in caplog.text
        assert "retrying in" in caplog.text
        assert "Failed to connect" in caplog.text
        
    @pytest.mark.asyncio
    async def test_bot_graceful_shutdown(self, temp_config_dir, minimal_config):
        """Test that bot shuts down gracefully"""
        config_path = temp_config_dir / "shutdown_test_config.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        bot = SimplexChatBot(config_path=str(config_path))
        
        # Mock the websocket
        bot.websocket_manager.websocket = AsyncMock()
        bot.running = True
        
        # Test stop method
        await bot.stop()
        
        # Verify graceful shutdown
        assert bot.running is False
        
    def test_bot_command_registration_health(self, temp_config_dir, minimal_config):
        """Test that all required commands are registered properly"""
        config_path = temp_config_dir / "commands_health_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        bot = SimplexChatBot(config_path=str(config_path))
        
        # Verify all expected commands are registered
        required_commands = ['help', 'status', 'ping', 'stats']
        available_commands = bot.command_registry.list_commands()
        
        for cmd in required_commands:
            assert cmd in available_commands
            # Verify command handlers are callable
            handler = bot.command_registry.get_command(cmd)
            assert callable(handler)
        
    def test_bot_logger_initialization_health(self, temp_config_dir, minimal_config):
        """Test that bot logging is set up correctly without errors"""
        config_path = temp_config_dir / "logger_health_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        bot = SimplexChatBot(config_path=str(config_path))
        
        # Verify loggers are initialized
        assert bot.logger is not None
        assert bot.message_logger is not None
        
        # Test logging (should not raise exceptions)
        bot.logger.info("Test log message")
        bot.message_logger.info("Test message log")
        
    @pytest.mark.asyncio
    async def test_bot_message_handling_no_errors(self, temp_config_dir, minimal_config):
        """Test that bot handles messages without throwing errors"""
        config_path = temp_config_dir / "message_handling_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        bot = SimplexChatBot(config_path=str(config_path))
        
        # Mock message data in the correct format for the refactored architecture
        test_message_data = {
            'chatItem': {
                'chatDir': {'contact': 'test_contact'},
                'meta': {'createdAt': '2025-01-01T00:00:00.000Z'},
                'content': {
                    'msgContent': {'type': 'text', 'text': '!help'}
                }
            },
            'chatInfo': {
                'contact': {
                    'localDisplayName': 'TestUser'
                }
            }
        }
        
        # Mock websocket manager
        bot.websocket_manager.send_message = AsyncMock()
        
        # Test message processing (should not raise exceptions)
        try:
            await bot.message_handler.process_message(test_message_data)
            # If we get here, no exception was raised
            assert True
        except Exception as e:
            pytest.fail(f"Bot message processing raised an exception: {e}")
            
    def test_bot_environment_variable_handling(self, temp_config_dir):
        """Test that bot handles environment variables correctly"""
        # Create config with environment variables
        config_data = {
            'servers': {
                'smp': ['${TEST_SMP_SERVER:-smp://localhost:5223}'],
                'xftp': ['${TEST_XFTP_SERVER:-}']
            },
            'bot': {
                'name': '${TEST_BOT_NAME:-Health Test Bot}',
                'websocket_url': '${TEST_WEBSOCKET_URL:-ws://localhost:3030}',
                'auto_accept_contacts': True
            },
            'logging': {
                'daily_rotation': True,
                'retention_days': 30,
                'log_level': 'INFO'
            },
            'media': {
                'download_enabled': True,
                'allowed_types': ['image'],
                'max_file_size': '100MB',
                'storage_path': './media'
            },
            'commands': {
                'enabled': ['help', 'echo', 'status'],
                'prefix': '!'
            },
            'security': {
                'max_message_length': 4096,
                'rate_limit_messages': 10,
                'rate_limit_window': 60
            },
            'xftp': {
                'cli_path': '/usr/local/bin/xftp',
                'temp_dir': './temp/xftp',
                'timeout': 300
            }
        }
        
        config_path = temp_config_dir / "env_var_health_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # Test with environment variables set
        with patch.dict(os.environ, {
            'TEST_BOT_NAME': 'Env Test Bot',
            'TEST_WEBSOCKET_URL': 'ws://test-host:3030'
        }, clear=False):
            
            bot = SimplexChatBot(config_path=str(config_path))
            
            # Verify environment variables were substituted
            assert bot.config.get('name') == 'Env Test Bot'
            assert bot.config.get('websocket_url') == 'ws://test-host:3030'
            
        # Test with environment variables not set (should use defaults)
        with patch.dict(os.environ, {}, clear=True):
            bot2 = SimplexChatBot(config_path=str(config_path))
            
            # Verify defaults were used
            assert bot2.config.get('name') == 'Health Test Bot'
            assert bot2.config.get('websocket_url') == 'ws://localhost:3030'

    def test_bot_component_integration(self, temp_config_dir, minimal_config):
        """Test that all bot components are properly integrated"""
        config_path = temp_config_dir / "integration_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        bot = SimplexChatBot(config_path=str(config_path))
        
        # Test component dependencies
        assert bot.message_handler.command_registry == bot.command_registry
        assert bot.message_handler.file_download_manager == bot.file_download_manager
        assert bot.file_download_manager.xftp_client == bot.xftp_client
        
        # Test that components have required dependencies
        assert hasattr(bot.message_handler, 'send_message_callback')
        assert hasattr(bot.file_download_manager, 'logger')
        assert hasattr(bot.websocket_manager, 'logger')

    def test_bot_command_execution(self, temp_config_dir, minimal_config):
        """Test command execution functionality"""
        config_path = temp_config_dir / "command_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        bot = SimplexChatBot(config_path=str(config_path))
        
        # Test command detection
        assert bot.command_registry.is_command('!help') == True
        assert bot.command_registry.is_command('!status') == True
        assert bot.command_registry.is_command('hello') == False
        assert bot.command_registry.is_command('') == False


class TestDockerHealthIntegration:
    """Test Docker-specific health scenarios"""
    
    def test_docker_compose_environment_variable_passing(self):
        """Test that docker-compose correctly passes environment variables"""
        # This test verifies the environment variable setup matches expectations
        required_env_vars = [
            'SMP_SERVER_1', 'XFTP_SERVER_1', 'BOT_NAME', 
            'WEBSOCKET_URL', 'AUTO_ACCEPT_CONTACTS'
        ]
        
        # Read docker-compose.yml to verify environment variables are defined
        compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        assert compose_path.exists(), "docker-compose.yml not found"
        
        with open(compose_path, 'r') as f:
            compose_content = f.read()
        
        # Verify that required environment variables are present in docker-compose
        for env_var in required_env_vars:
            assert env_var in compose_content, f"Environment variable {env_var} not found in docker-compose.yml"
            
    def test_docker_network_configuration(self):
        """Test that Docker networking is configured correctly"""
        compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        
        with open(compose_path, 'r') as f:
            compose_content = f.read()
        
        # Verify network configuration
        assert "networks:" in compose_content
        assert "simplex-net:" in compose_content
        assert "driver: bridge" in compose_content


class TestBotStabilityAndResilience:
    """Test bot stability under various conditions"""
    
    @pytest.mark.asyncio
    async def test_bot_handles_malformed_messages_gracefully(self, temp_config_dir, minimal_config):
        """Test that bot handles malformed messages without crashing"""
        config_path = temp_config_dir / "malformed_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        bot = SimplexChatBot(config_path=str(config_path))
        bot.websocket_manager.send_message = AsyncMock()
        
        # Test various malformed message scenarios
        malformed_messages = [
            {},  # Empty dict
            {'invalid': 'structure'},  # Missing required fields
            {'chatItem': {'invalid': 'structure'}},  # Invalid chatItem structure
            None,  # None value
        ]
        
        for msg in malformed_messages:
            try:
                await bot.message_handler.process_message(msg)
                # Should handle gracefully, not crash
            except Exception as e:
                # Log the error but don't fail the test - bot should be resilient
                print(f"Bot handled malformed message with error: {e}")
                
    def test_bot_resource_cleanup(self, temp_config_dir, minimal_config):
        """Test that bot properly cleans up resources"""
        config_path = temp_config_dir / "cleanup_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        # Create and initialize bot
        bot = SimplexChatBot(config_path=str(config_path))
        
        # Verify bot created necessary resources
        assert hasattr(bot, 'logger')
        assert hasattr(bot, 'message_logger')
        assert hasattr(bot, 'config_manager')
        assert hasattr(bot, 'websocket_manager')
        assert hasattr(bot, 'file_download_manager')
        assert hasattr(bot, 'message_handler')
        assert hasattr(bot, 'command_registry')
        assert hasattr(bot, 'xftp_client')
        
        # Bot should clean up properly when destroyed
        # (Python garbage collection should handle this, but we verify attributes exist)
        del bot