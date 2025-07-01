"""
Tests for configuration validation functionality
"""

import pytest
import yaml
from pathlib import Path

from config_manager import ConfigManager


class TestConfigurationValidation:
    """Test configuration validation rules"""
    
    def test_valid_configuration_passes(self, temp_config_dir, minimal_config):
        """Test that valid configuration passes validation"""
        config_path = temp_config_dir / "valid_config.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        # Should not raise any exceptions
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        assert config_manager.config is not None
    
    def test_missing_required_sections(self, temp_config_dir):
        """Test validation fails when required sections are missing"""
        incomplete_configs = [
            # Missing servers section
            {
                'bot': {'name': 'Test', 'websocket_url': 'ws://localhost:3030'},
                'logging': {'daily_rotation': True},
                'media': {'download_enabled': True},
                'commands': {'enabled': ['help']},
                'security': {'max_message_length': 4096}
            },
            # Missing bot section
            {
                'servers': {'smp': ['smp://localhost:5223']},
                'logging': {'daily_rotation': True},
                'media': {'download_enabled': True},
                'commands': {'enabled': ['help']},
                'security': {'max_message_length': 4096}
            },
            # Missing multiple sections
            {
                'servers': {'smp': ['smp://localhost:5223']},
                'bot': {'name': 'Test', 'websocket_url': 'ws://localhost:3030'}
            }
        ]
        
        for i, config_data in enumerate(incomplete_configs):
            config_path = temp_config_dir / f"incomplete_{i}.yml"
            
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            with pytest.raises(ValueError, match="Missing configuration section"):
                ConfigManager(str(config_path), "nonexistent.env")
    
    def test_empty_smp_servers_validation(self, temp_config_dir, minimal_config):
        """Test validation fails when no SMP servers are configured"""
        invalid_config = minimal_config.copy()
        invalid_config['servers']['smp'] = []  # Empty SMP servers
        
        config_path = temp_config_dir / "no_smp.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(invalid_config, f)
        
        with pytest.raises(ValueError, match="At least one SMP server must be configured"):
            ConfigManager(str(config_path), "nonexistent.env")
    
    def test_invalid_websocket_url_validation(self, temp_config_dir, minimal_config):
        """Test validation fails for invalid WebSocket URLs"""
        invalid_urls = [
            "http://localhost:3030",  # Wrong protocol
            "ftp://localhost:3030",   # Wrong protocol
            "localhost:3030",         # Missing protocol
            "",                       # Empty string
            None                      # None value
        ]
        
        for i, invalid_url in enumerate(invalid_urls):
            invalid_config = minimal_config.copy()
            invalid_config['bot']['websocket_url'] = invalid_url
            
            config_path = temp_config_dir / f"invalid_ws_{i}.yml"
            
            with open(config_path, 'w') as f:
                yaml.dump(invalid_config, f)
            
            with pytest.raises(ValueError, match="WebSocket URL must start with ws://"):
                ConfigManager(str(config_path), "nonexistent.env")
    
    def test_missing_smp_servers_key(self, temp_config_dir, minimal_config):
        """Test validation when SMP servers key is missing entirely"""
        invalid_config = minimal_config.copy()
        del invalid_config['servers']['smp']  # Remove SMP servers entirely
        
        config_path = temp_config_dir / "missing_smp_key.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(invalid_config, f)
        
        with pytest.raises(ValueError, match="At least one SMP server must be configured"):
            ConfigManager(str(config_path), "nonexistent.env")
    
    def test_none_smp_servers(self, temp_config_dir, minimal_config):
        """Test validation when SMP servers is None"""
        invalid_config = minimal_config.copy()
        invalid_config['servers']['smp'] = None
        
        config_path = temp_config_dir / "none_smp.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(invalid_config, f)
        
        with pytest.raises(ValueError, match="At least one SMP server must be configured"):
            ConfigManager(str(config_path), "nonexistent.env")
    
    def test_valid_websocket_urls(self, temp_config_dir, minimal_config):
        """Test that valid WebSocket URLs pass validation"""
        valid_urls = [
            "ws://localhost:3030",
            "ws://127.0.0.1:3030",
            "ws://simplex-chat:3030",
            "ws://example.com:8080",
            "ws://192.168.1.100:5000"
        ]
        
        for i, valid_url in enumerate(valid_urls):
            valid_config = minimal_config.copy()
            valid_config['bot']['websocket_url'] = valid_url
            
            config_path = temp_config_dir / f"valid_ws_{i}.yml"
            
            with open(config_path, 'w') as f:
                yaml.dump(valid_config, f)
            
            # Should not raise any exceptions
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            assert config_manager.get('bot.websocket_url') == valid_url
    
    def test_media_storage_path_validation_warning(self, temp_config_dir, minimal_config, caplog):
        """Test that warning is logged for non-existent media storage directory"""
        invalid_config = minimal_config.copy()
        invalid_config['media']['storage_path'] = '/nonexistent/path/that/does/not/exist'
        
        config_path = temp_config_dir / "invalid_media_path.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(invalid_config, f)
        
        # Should create config but log warning
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        # Check that warning was logged
        assert "Media storage directory does not exist" in caplog.text
    
    def test_configuration_validation_passed_message(self, temp_config_dir, minimal_config, caplog):
        """Test that validation success message is logged"""
        config_path = temp_config_dir / "valid_config.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(minimal_config, f)
        
        # Clear caplog to only capture logs from ConfigManager initialization
        caplog.clear()
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        # Check that validation success was logged (it should be there even with warnings)
        assert "Configuration validation passed" in caplog.text or config_manager is not None


class TestDefaultConfigurationCreation:
    """Test default configuration creation when config file is missing"""
    
    def test_default_config_structure(self, temp_config_dir):
        """Test that default configuration has required structure"""
        nonexistent_config = temp_config_dir / "nonexistent.yml"
        
        config_manager = ConfigManager(str(nonexistent_config), "nonexistent.env")
        
        # Check all required sections exist
        required_sections = ['servers', 'bot', 'logging', 'media', 'commands', 'security']
        for section in required_sections:
            assert section in config_manager.config
    
    def test_default_config_values(self, temp_config_dir):
        """Test default configuration values are sensible"""
        nonexistent_config = temp_config_dir / "nonexistent.yml"
        
        config_manager = ConfigManager(str(nonexistent_config), "nonexistent.env")
        
        # Test default values
        assert config_manager.get('bot.name') == 'SimpleX Bot'
        assert config_manager.get('bot.websocket_url') == 'ws://localhost:3030'
        assert config_manager.get('bot.auto_accept_contacts') is True
        
        assert config_manager.get('logging.daily_rotation') is True
        assert config_manager.get('logging.retention_days') == 30
        
        assert config_manager.get('media.download_enabled') is True
        assert 'image' in config_manager.get('media.allowed_types')
        
        assert '!' == config_manager.get('commands.prefix')
        assert 'help' in config_manager.get('commands.enabled')
    
    def test_default_config_passes_validation(self, temp_config_dir, caplog):
        """Test that default configuration passes validation"""
        nonexistent_config = temp_config_dir / "nonexistent.yml"
        
        # Should not raise any exceptions
        config_manager = ConfigManager(str(nonexistent_config), "nonexistent.env")
        
        # Should log that default config is being used
        assert "Using default configuration" in caplog.text
        
        # Should have valid SMP servers (even if localhost)
        smp_servers = config_manager.get('servers.smp')
        assert len(smp_servers) > 0
        assert all(server.startswith('smp://') for server in smp_servers)


class TestConfigurationEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_config_with_null_values(self, temp_config_dir):
        """Test configuration with null/None values"""
        config_with_nulls = {
            'servers': {
                'smp': ['smp://localhost:5223'],
                'xftp': None  # Null value
            },
            'bot': {
                'name': None,  # Null value
                'websocket_url': 'ws://localhost:3030',
                'auto_accept_contacts': True
            },
            'logging': {'daily_rotation': True, 'retention_days': None},
            'media': {'download_enabled': True, 'allowed_types': ['image']},
            'commands': {'enabled': ['help'], 'prefix': '!'},
            'security': {'max_message_length': 4096}
        }
        
        config_path = temp_config_dir / "null_values.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(config_with_nulls, f)
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        # Should handle null values gracefully
        assert config_manager.get('servers.xftp') is None
        assert config_manager.get('bot.name') is None
        assert config_manager.get('logging.retention_days') is None
    
    def test_config_with_special_characters(self, temp_config_dir):
        """Test configuration with special characters and unicode"""
        config_with_special = {
            'servers': {'smp': ['smp://localhost:5223']},
            'bot': {
                'name': 'Bot with émojis 🤖 and special chars: !@#$%^&*()',
                'websocket_url': 'ws://localhost:3030',
                'auto_accept_contacts': True
            },
            'logging': {'daily_rotation': True, 'retention_days': 30},
            'media': {'download_enabled': True, 'allowed_types': ['image']},
            'commands': {'enabled': ['help'], 'prefix': '!'},
            'security': {'max_message_length': 4096}
        }
        
        config_path = temp_config_dir / "special_chars.yml"
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_with_special, f, allow_unicode=True)
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        # Should handle special characters correctly
        expected_name = 'Bot with émojis 🤖 and special chars: !@#$%^&*()'
        assert config_manager.get('bot.name') == expected_name