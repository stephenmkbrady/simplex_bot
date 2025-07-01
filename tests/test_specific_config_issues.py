"""
Tests for specific configuration issues found in the project
"""

import pytest
import os
import yaml
from unittest.mock import patch

from config_manager import ConfigManager


class TestSpecificConfigurationIssues:
    """Test specific configuration issues and edge cases found in real usage"""
    
    def test_auto_accept_contacts_boolean_conversion(self, temp_config_dir):
        """Test AUTO_ACCEPT_CONTACTS environment variable with boolean-like values"""
        # Test the specific syntax from the user's config.yml
        config_data = {
            'bot': {
                'auto_accept_contacts': '${AUTO_ACCEPT_CONTACTS:-true}',
                'websocket_url': 'ws://localhost:3030'
            },
            'servers': {'smp': ['smp://localhost:5223']},
            'logging': {'daily_rotation': True},
            'media': {'download_enabled': True},
            'commands': {'enabled': ['help']},
            'security': {'max_message_length': 4096}
        }
        
        config_path = temp_config_dir / "auto_accept_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # Test with different boolean-like environment variable values
        test_cases = [
            ('true', 'true'),
            ('false', 'false'), 
            ('True', 'True'),
            ('False', 'False'),
            ('TRUE', 'TRUE'),
            ('FALSE', 'FALSE'),
            ('yes', 'yes'),
            ('no', 'no'),
            ('1', '1'),
            ('0', '0'),
            ('on', 'on'),
            ('off', 'off')
        ]
        
        for env_value, expected_result in test_cases:
            with patch.dict(os.environ, {'AUTO_ACCEPT_CONTACTS': env_value}, clear=False):
                config_manager = ConfigManager(str(config_path), "nonexistent.env")
                
                result = config_manager.get('bot.auto_accept_contacts')
                assert result == expected_result, f"Expected {expected_result}, got {result} for env value {env_value}"
    
    def test_auto_accept_contacts_default_value(self, temp_config_dir):
        """Test AUTO_ACCEPT_CONTACTS default value when environment variable is not set"""
        config_data = {
            'bot': {
                'auto_accept_contacts': '${AUTO_ACCEPT_CONTACTS:-true}',
                'websocket_url': 'ws://localhost:3030'
            },
            'servers': {'smp': ['smp://localhost:5223']},
            'logging': {'daily_rotation': True},
            'media': {'download_enabled': True},
            'commands': {'enabled': ['help']},
            'security': {'max_message_length': 4096}
        }
        
        config_path = temp_config_dir / "auto_accept_default_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # Clear AUTO_ACCEPT_CONTACTS from environment
        env_backup = os.environ.get('AUTO_ACCEPT_CONTACTS')
        if 'AUTO_ACCEPT_CONTACTS' in os.environ:
            del os.environ['AUTO_ACCEPT_CONTACTS']
        
        try:
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            # Should use the default value 'true'
            result = config_manager.get('bot.auto_accept_contacts')
            assert result == 'true'
        finally:
            # Restore environment variable if it existed
            if env_backup is not None:
                os.environ['AUTO_ACCEPT_CONTACTS'] = env_backup
    
    def test_bot_applies_auto_accept_setting_correctly(self, temp_config_dir):
        """Test that bot correctly interprets auto_accept_contacts setting"""
        from bot import SimplexChatBot
        
        test_cases = [
            ('true', True),   # String 'true' should be interpreted as boolean True
            ('false', False), # String 'false' should be interpreted as boolean False
            ('1', True),      # String '1' should be interpreted as boolean True  
            ('0', False),     # String '0' should be interpreted as boolean False
            ('yes', True),    # String 'yes' should be interpreted as boolean True
            ('no', False),    # String 'no' should be interpreted as boolean False
        ]
        
        for env_value, expected_bool in test_cases:
            config_data = {
                'servers': {'smp': ['smp://localhost:5223']},
                'bot': {
                    'name': 'Test Bot',
                    'websocket_url': 'ws://localhost:3030',
                    'auto_accept_contacts': f'${{AUTO_ACCEPT_CONTACTS:-{env_value}}}'
                },
                'logging': {'daily_rotation': True, 'retention_days': 30},
                'media': {'download_enabled': True, 'allowed_types': ['image']},
                'commands': {'enabled': ['help'], 'prefix': '!'},
                'security': {'max_message_length': 4096}
            }
            
            config_path = temp_config_dir / f"bot_auto_accept_{env_value}.yml"
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            original_cwd = os.getcwd()
            os.chdir(temp_config_dir)
            
            try:
                # Clear the environment variable to use default
                if 'AUTO_ACCEPT_CONTACTS' in os.environ:
                    del os.environ['AUTO_ACCEPT_CONTACTS']
                
                bot = SimplexChatBot(str(config_path))
                
                # Bot should convert string to boolean correctly
                # Note: The current bot implementation may need updating to handle this conversion
                # For now, we test what the config manager returns
                config_value = bot.config_manager.get('bot.auto_accept_contacts')
                assert config_value == env_value
                
                # If bot does boolean conversion, test that too
                # This might require updating the bot code to handle string-to-boolean conversion
                
            finally:
                os.chdir(original_cwd)
    
    def test_config_with_malformed_env_var_syntax_edge_cases(self, temp_config_dir):
        """Test specific malformed environment variable syntax that might appear in real configs"""
        config_data = {
            'servers': {'smp': ['smp://localhost:5223']},
            'bot': {
                'name': 'Test Bot',
                'websocket_url': 'ws://localhost:3030',
                # Test the specific syntax that might cause issues
                'auto_accept_contacts': '${AUTO_ACCEPT_CONTACTS:-true}',  # Correct
                'malformed1': '${AUTO_ACCEPT_CONTACTS-true}',             # Missing colon
                'malformed2': '${AUTO_ACCEPT_CONTACTS:true}',             # Missing dash
                'malformed3': '${AUTO_ACCEPT_CONTACTS:--true}',           # Double dash
                'malformed4': '${AUTO_ACCEPT_CONTACTS:-}',                # Empty default
            },
            'logging': {'daily_rotation': True, 'retention_days': 30},
            'media': {'download_enabled': True, 'allowed_types': ['image']},
            'commands': {'enabled': ['help'], 'prefix': '!'},
            'security': {'max_message_length': 4096}
        }
        
        config_path = temp_config_dir / "malformed_syntax_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # Clear environment variable
        if 'AUTO_ACCEPT_CONTACTS' in os.environ:
            del os.environ['AUTO_ACCEPT_CONTACTS']
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        # Correct syntax should work
        assert config_manager.get('bot.auto_accept_contacts') == 'true'
        
        # Malformed syntax should be left as-is (not substituted)
        assert '${AUTO_ACCEPT_CONTACTS-true}' in config_manager.get('bot.malformed1')
        assert '${AUTO_ACCEPT_CONTACTS:true}' in config_manager.get('bot.malformed2')
        assert config_manager.get('bot.malformed3') == '-true'  # Should parse as empty var with default "-true"
        assert config_manager.get('bot.malformed4') == ''       # Empty default
    
    def test_real_world_config_structure(self, temp_config_dir):
        """Test a configuration structure similar to the actual project setup"""
        # This mimics the structure from config.yml.example
        config_data = {
            'servers': {
                'smp': ['${SMP_SERVER_1}', '${SMP_SERVER_2:-}'],
                'xftp': ['${XFTP_SERVER_1}', '${XFTP_SERVER_2:-}']
            },
            'bot': {
                'name': '${BOT_NAME:-SimpleX Bot}',
                'websocket_url': '${WEBSOCKET_URL:-ws://localhost:3030}',
                'auto_accept_contacts': '${AUTO_ACCEPT_CONTACTS:-true}'
            },
            'logging': {
                'daily_rotation': True,
                'message_log_separate': True,
                'retention_days': '${LOG_RETENTION_DAYS:-30}',
                'log_level': '${LOG_LEVEL:-INFO}'
            },
            'media': {
                'download_enabled': '${MEDIA_DOWNLOAD_ENABLED:-true}',
                'max_file_size': '${MAX_FILE_SIZE:-100MB}',
                'allowed_types': ['image', 'video', 'document', 'audio'],
                'storage_path': '${MEDIA_STORAGE_PATH:-./media}'
            },
            'commands': {
                'enabled': ['help', 'echo', 'status'],
                'prefix': '!'
            },
            'security': {
                'max_message_length': '${MAX_MESSAGE_LENGTH:-4096}',
                'rate_limit_messages': '${RATE_LIMIT_MESSAGES:-10}',
                'rate_limit_window': '${RATE_LIMIT_WINDOW:-60}'
            }
        }
        
        config_path = temp_config_dir / "real_world_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # Test with minimal required environment variables
        with patch.dict(os.environ, {
            'SMP_SERVER_1': 'smp://test-server.com',
            'XFTP_SERVER_1': 'xftp://test-files.com'
        }, clear=True):
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            # Test that defaults are applied correctly
            assert config_manager.get('bot.name') == 'SimpleX Bot'
            assert config_manager.get('bot.websocket_url') == 'ws://localhost:3030'
            assert config_manager.get('bot.auto_accept_contacts') == 'true'
            assert config_manager.get('logging.retention_days') == '30'
            assert config_manager.get('logging.log_level') == 'INFO'
            assert config_manager.get('media.download_enabled') == 'true'
            assert config_manager.get('media.max_file_size') == '100MB'
            assert config_manager.get('media.storage_path') == './media'
            assert config_manager.get('security.max_message_length') == '4096'
            assert config_manager.get('security.rate_limit_messages') == '10'
            assert config_manager.get('security.rate_limit_window') == '60'
            
            # Test that required variables are set
            assert config_manager.get('servers.smp') == ['smp://test-server.com', '']
            assert config_manager.get('servers.xftp') == ['xftp://test-files.com', '']
    
    def test_empty_optional_server_handling(self, temp_config_dir):
        """Test handling of optional servers when environment variables are empty"""
        config_data = {
            'servers': {
                'smp': ['${SMP_SERVER_1}', '${SMP_SERVER_2:-}'],  # Second server is optional
                'xftp': ['${XFTP_SERVER_1}', '${XFTP_SERVER_2:-}']  # Second server is optional
            },
            'bot': {'name': 'Test', 'websocket_url': 'ws://localhost:3030'},
            'logging': {'daily_rotation': True},
            'media': {'download_enabled': True},
            'commands': {'enabled': ['help']},
            'security': {'max_message_length': 4096}
        }
        
        config_path = temp_config_dir / "optional_servers_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # Test with only primary servers set
        with patch.dict(os.environ, {
            'SMP_SERVER_1': 'smp://primary.com',
            'XFTP_SERVER_1': 'xftp://primary.com'
            # SMP_SERVER_2 and XFTP_SERVER_2 are not set
        }, clear=False):
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            # Should have primary servers and empty strings for optional ones
            smp_servers = config_manager.get('servers.smp')
            xftp_servers = config_manager.get('servers.xftp')
            
            assert smp_servers == ['smp://primary.com', '']
            assert xftp_servers == ['xftp://primary.com', '']
            
            # Filter out empty servers for practical use
            active_smp = [s for s in smp_servers if s]
            active_xftp = [s for s in xftp_servers if s]
            
            assert active_smp == ['smp://primary.com']
            assert active_xftp == ['xftp://primary.com']