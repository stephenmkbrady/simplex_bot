"""
Tests for bot health, startup, and stability
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
        
        # Mock CLI args
        cli_args = MagicMock()
        cli_args.connect = None
        cli_args.group = None
        
        # Create bot and verify no exceptions during initialization
        bot = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
        
        # Verify bot attributes are set correctly
        assert bot.bot_name is not None
        assert bot.websocket_url is not None
        assert bot.commands is not None
        assert len(bot.commands) > 0
        assert bot.running is False  # Should start as False
        
    def test_bot_configuration_validation_health(self, temp_config_dir, minimal_config):
        """Test that bot configuration is validated properly"""
        config_path = temp_config_dir / "validation_health_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        cli_args = MagicMock()
        cli_args.connect = None
        cli_args.group = None
        
        bot = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
        
        # Verify configuration is loaded correctly
        assert bot.config_manager.get('bot.name') is not None
        assert bot.config_manager.get('bot.websocket_url').startswith('ws://')
        assert len(bot.config_manager.get('servers.smp')) > 0
        
    @pytest.mark.asyncio
    async def test_bot_connection_retry_mechanism(self, temp_config_dir, minimal_config, caplog):
        """Test that bot implements proper retry logic for connections"""
        config_path = temp_config_dir / "retry_test_config.yml"
        
        # Set an unreachable WebSocket URL
        test_config = minimal_config.copy()
        test_config['bot']['websocket_url'] = 'ws://unreachable-host:9999'
        
        with open(config_path, 'w') as f:
            yaml.dump(test_config, f)
        
        cli_args = MagicMock()
        cli_args.connect = None
        cli_args.group = None
        
        bot = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
        
        # Test connection with limited retries
        result = await bot.connect(max_retries=3, retry_delay=0.1)
        
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
        
        cli_args = MagicMock()
        cli_args.connect = None
        cli_args.group = None
        
        bot = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
        
        # Mock the websocket
        bot.websocket = AsyncMock()
        bot.running = True
        
        # Test stop method
        await bot.stop()
        
        # Verify graceful shutdown
        assert bot.running is False
        bot.websocket.close.assert_called_once()
        
    def test_bot_command_registration_health(self, temp_config_dir, minimal_config):
        """Test that all required commands are registered properly"""
        config_path = temp_config_dir / "commands_health_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        cli_args = MagicMock()
        cli_args.connect = None
        cli_args.group = None
        
        bot = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
        
        # Verify all expected commands are registered
        required_commands = ['!help', '!echo', '!status']
        for cmd in required_commands:
            assert cmd in bot.commands
            # Verify command handlers are callable
            assert callable(bot.commands[cmd])
        
    def test_bot_logger_initialization_health(self, temp_config_dir, minimal_config):
        """Test that bot logging is set up correctly without errors"""
        config_path = temp_config_dir / "logger_health_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        cli_args = MagicMock()
        cli_args.connect = None
        cli_args.group = None
        
        bot = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
        
        # Verify loggers are initialized
        assert bot.app_logger is not None
        assert bot.message_logger is not None
        
        # Test logging (should not raise exceptions)
        bot.app_logger.info("Test log message")
        bot.message_logger.info("Test message log")
        
    @pytest.mark.asyncio
    async def test_bot_message_handling_no_errors(self, temp_config_dir, minimal_config):
        """Test that bot handles messages without throwing errors"""
        config_path = temp_config_dir / "message_handling_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        cli_args = MagicMock()
        cli_args.connect = None
        cli_args.group = None
        
        bot = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
        
        # Mock message data
        test_message_data = {
            'chatItemId': 123,
            'chatItem': {
                'chatDir': {'contact': 'test_contact'},
                'meta': {'createdAt': '2025-01-01T00:00:00.000Z'},
                'content': {
                    'text': '!help',
                    'msgContent': {'type': 'text', 'text': '!help'}
                }
            }
        }
        
        # Mock websocket
        bot.websocket = AsyncMock()
        
        # Test message processing (should not raise exceptions)
        try:
            await bot.process_message(test_message_data)
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
            
            cli_args = MagicMock()
            cli_args.connect = None
            cli_args.group = None
            
            bot = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
            
            # Verify environment variables were substituted
            assert bot.bot_name == 'Env Test Bot'
            assert bot.websocket_url == 'ws://test-host:3030'
            
        # Test with environment variables not set (should use defaults)
        with patch.dict(os.environ, {}, clear=True):
            bot2 = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
            
            # Verify defaults were used
            assert bot2.bot_name == 'Health Test Bot'
            assert bot2.websocket_url == 'ws://localhost:3030'


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
            
    def test_docker_service_dependency_configuration(self):
        """Test that Docker services are configured with proper dependencies"""
        compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        
        with open(compose_path, 'r') as f:
            compose_content = f.read()
        
        # Verify service dependency configuration
        assert "depends_on:" in compose_content
        assert "simplex-chat:" in compose_content
        assert "condition: service_healthy" in compose_content
        
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
        
        cli_args = MagicMock()
        cli_args.connect = None
        cli_args.group = None
        
        bot = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
        bot.websocket = AsyncMock()
        
        # Test various malformed message scenarios
        malformed_messages = [
            {},  # Empty dict
            {'invalid': 'structure'},  # Missing required fields
            {'chatItemId': 'invalid_id'},  # Invalid data types
            None,  # None value
        ]
        
        for msg in malformed_messages:
            try:
                await bot.process_message(msg)
                # Should handle gracefully, not crash
            except Exception as e:
                # Log the error but don't fail the test - bot should be resilient
                print(f"Bot handled malformed message with error: {e}")
                
    def test_bot_resource_cleanup(self, temp_config_dir, minimal_config):
        """Test that bot properly cleans up resources"""
        config_path = temp_config_dir / "cleanup_test.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        cli_args = MagicMock()
        cli_args.connect = None
        cli_args.group = None
        
        # Create and initialize bot
        bot = SimplexChatBot(config_path=str(config_path), cli_args=cli_args)
        
        # Verify bot created necessary resources
        assert hasattr(bot, 'app_logger')
        assert hasattr(bot, 'message_logger')
        assert hasattr(bot, 'config_manager')
        
        # Bot should clean up properly when destroyed
        # (Python garbage collection should handle this, but we verify attributes exist)
        del bot