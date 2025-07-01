"""
Tests for ConfigManager class - YAML parsing and configuration management
"""

import pytest
import os
import yaml
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

from config_manager import ConfigManager, parse_file_size


class TestConfigManagerBasics:
    """Test basic ConfigManager functionality"""
    
    def test_config_manager_initialization(self, temp_config_dir, config_file, env_file, mock_env_vars):
        """Test ConfigManager initializes correctly with valid files"""
        # Change to temp directory to test relative paths
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            config_manager = ConfigManager(str(config_file), str(env_file))
            
            assert config_manager.config_path == str(config_file)
            assert config_manager.env_file == str(env_file)
            assert isinstance(config_manager.config, dict)
            assert 'servers' in config_manager.config
            assert 'bot' in config_manager.config
        finally:
            os.chdir(original_cwd)
    
    def test_config_manager_missing_files(self, temp_config_dir):
        """Test ConfigManager behavior with missing configuration files"""
        nonexistent_config = temp_config_dir / "nonexistent.yml"
        nonexistent_env = temp_config_dir / "nonexistent.env"
        
        # Should create default config when config file is missing
        config_manager = ConfigManager(str(nonexistent_config), str(nonexistent_env))
        
        # Should have default configuration
        assert config_manager.config is not None
        assert 'servers' in config_manager.config
        assert 'bot' in config_manager.config
    
    def test_get_method_dot_notation(self, temp_config_dir, config_file, env_file, mock_env_vars):
        """Test ConfigManager.get() method with dot notation"""
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            config_manager = ConfigManager(str(config_file), str(env_file))
            
            # Test getting nested values
            assert config_manager.get('bot.name') == 'Test Bot'
            assert config_manager.get('servers.smp') == ['smp://test-server1.com', 'smp://test-server2.com']
            
            # Test getting non-existent key with default
            assert config_manager.get('nonexistent.key', 'default') == 'default'
            
            # Test getting non-existent key without default
            assert config_manager.get('nonexistent.key') is None
        finally:
            os.chdir(original_cwd)


class TestYAMLParsing:
    """Test YAML parsing functionality"""
    
    def test_valid_yaml_parsing(self, temp_config_dir, sample_config_dict):
        """Test parsing of valid YAML configuration"""
        config_path = temp_config_dir / "test_config.yml"
        
        with open(config_path, 'w') as f:
            yaml.dump(sample_config_dict, f)
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        # Check that all sections are parsed correctly
        assert 'servers' in config_manager.config
        assert 'bot' in config_manager.config
        assert 'logging' in config_manager.config
        assert 'media' in config_manager.config
        assert 'commands' in config_manager.config
        assert 'security' in config_manager.config
    
    def test_invalid_yaml_parsing(self, temp_config_dir):
        """Test handling of invalid YAML"""
        config_path = temp_config_dir / "invalid.yml"
        
        # Create invalid YAML
        with open(config_path, 'w') as f:
            f.write("invalid: yaml: content: [\n")
        
        with pytest.raises(yaml.YAMLError):
            ConfigManager(str(config_path), "nonexistent.env")
    
    def test_yaml_with_different_data_types(self, temp_config_dir, minimal_config):
        """Test YAML parsing with different data types"""
        config_data = minimal_config.copy()
        config_data.update({
            'string_value': 'test',
            'int_value': 42,
            'float_value': 3.14,
            'bool_value': True,
            'list_value': ['item1', 'item2'],
            'dict_value': {'nested': 'value'},
            'null_value': None
        })
        
        config_path = temp_config_dir / "types_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        assert config_manager.get('string_value') == 'test'
        assert config_manager.get('int_value') == 42
        assert config_manager.get('float_value') == 3.14
        assert config_manager.get('bool_value') is True
        assert config_manager.get('list_value') == ['item1', 'item2']
        assert config_manager.get('dict_value.nested') == 'value'
        assert config_manager.get('null_value') is None


class TestEnvironmentVariableSubstitution:
    """Test environment variable substitution functionality"""
    
    def test_simple_env_var_substitution(self, temp_config_dir, minimal_config, mock_env_vars):
        """Test basic environment variable substitution"""
        config_data = minimal_config.copy()
        config_data.update({
            'test_value': '${SMP_SERVER_1}',
            'nested': {
                'value': '${BOT_NAME}'
            }
        })
        
        config_path = temp_config_dir / "env_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        assert config_manager.get('test_value') == 'smp://test-server1.com'
        assert config_manager.get('nested.value') == 'Test Bot'
    
    def test_env_var_with_default_values(self, temp_config_dir, minimal_config, clear_env_vars):
        """Test environment variable substitution with default values"""
        config_data = minimal_config.copy()
        config_data.update({
            'with_default': '${NONEXISTENT_VAR:-default_value}',
            'without_default': '${ANOTHER_NONEXISTENT_VAR}',
            'empty_default': '${EMPTY_VAR:-}',
            'complex_default': '${MISSING:-http://localhost:3030}'
        })
        
        config_path = temp_config_dir / "defaults_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        assert config_manager.get('with_default') == 'default_value'
        assert config_manager.get('without_default') == '${ANOTHER_NONEXISTENT_VAR}'  # Should remain unchanged
        assert config_manager.get('empty_default') == ''
        assert config_manager.get('complex_default') == 'http://localhost:3030'
    
    def test_env_var_in_lists(self, temp_config_dir, minimal_config, mock_env_vars):
        """Test environment variable substitution in lists"""
        config_data = minimal_config.copy()
        config_data.update({
            'test_servers': ['${SMP_SERVER_1}', '${SMP_SERVER_2}', 'static://server.com']
        })
        
        config_path = temp_config_dir / "list_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        expected = ['smp://test-server1.com', 'smp://test-server2.com', 'static://server.com']
        assert config_manager.get('test_servers') == expected
    
    def test_boolean_env_var_substitution(self, temp_config_dir, minimal_config):
        """Test boolean environment variable substitution"""
        with patch.dict(os.environ, {
            'TRUE_VAR': 'true',
            'FALSE_VAR': 'false',
            'YES_VAR': 'yes',
            'NO_VAR': 'no',
            'ONE_VAR': '1',
            'ZERO_VAR': '0'
        }, clear=False):
            config_data = minimal_config.copy()
            config_data.update({
                'bool_true': '${TRUE_VAR:-false}',
                'bool_false': '${FALSE_VAR:-true}',
                'bool_yes': '${YES_VAR:-no}',
                'bool_no': '${NO_VAR:-yes}',
                'bool_one': '${ONE_VAR:-0}',
                'bool_zero': '${ZERO_VAR:-1}'
            })
            
            config_path = temp_config_dir / "bool_test.yml"
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            # All should be strings after substitution
            assert config_manager.get('bool_true') == 'true'
            assert config_manager.get('bool_false') == 'false'
            assert config_manager.get('bool_yes') == 'yes'
            assert config_manager.get('bool_no') == 'no'
            assert config_manager.get('bool_one') == '1'
            assert config_manager.get('bool_zero') == '0'
    
    def test_multiple_env_vars_in_single_value(self, temp_config_dir, minimal_config):
        """Test multiple environment variables in a single configuration value"""
        with patch.dict(os.environ, {
            'HOST': 'example.com',
            'PORT': '8080',
            'PROTOCOL': 'https'
        }, clear=False):
            config_data = minimal_config.copy()
            config_data.update({
                'url': '${PROTOCOL:-http}://${HOST:-localhost}:${PORT:-80}/api'
            })
            
            config_path = temp_config_dir / "multi_env_test.yml"
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            assert config_manager.get('url') == 'https://example.com:8080/api'


class TestConfigurationGetters:
    """Test configuration getter methods"""
    
    def test_get_servers(self, temp_config_dir, config_file, env_file, mock_env_vars):
        """Test get_servers() method"""
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            config_manager = ConfigManager(str(config_file), str(env_file))
            servers = config_manager.get_servers()
            
            assert 'smp' in servers
            assert 'xftp' in servers
            assert servers['smp'] == ['smp://test-server1.com', 'smp://test-server2.com']
            assert servers['xftp'] == ['xftp://test-files1.com', 'xftp://test-files2.com']
        finally:
            os.chdir(original_cwd)
    
    def test_get_bot_config(self, temp_config_dir, config_file, env_file, mock_env_vars):
        """Test get_bot_config() method"""
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            config_manager = ConfigManager(str(config_file), str(env_file))
            bot_config = config_manager.get_bot_config()
            
            assert bot_config['name'] == 'Test Bot'
            assert bot_config['websocket_url'] == 'ws://test:3030'
            assert bot_config['auto_accept_contacts'] == 'false'  # String after substitution
        finally:
            os.chdir(original_cwd)
    
    def test_get_logging_config(self, temp_config_dir, config_file, env_file, mock_env_vars):
        """Test get_logging_config() method"""
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            config_manager = ConfigManager(str(config_file), str(env_file))
            logging_config = config_manager.get_logging_config()
            
            assert logging_config['daily_rotation'] is True
            assert logging_config['message_log_separate'] is True
            assert logging_config['retention_days'] == '7'  # String after substitution
            assert logging_config['log_level'] == 'DEBUG'
        finally:
            os.chdir(original_cwd)
    
    def test_get_media_config(self, temp_config_dir, config_file, env_file, mock_env_vars):
        """Test get_media_config() method"""
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            config_manager = ConfigManager(str(config_file), str(env_file))
            media_config = config_manager.get_media_config()
            
            assert media_config['download_enabled'] == 'true'  # String after substitution
            assert media_config['max_file_size'] == '50MB'
            assert media_config['storage_path'] == './test_media'
            assert 'image' in media_config['allowed_types']
        finally:
            os.chdir(original_cwd)


class TestFileSizeParsing:
    """Test file size parsing utility function"""
    
    def test_parse_file_size_bytes(self):
        """Test parsing file sizes in bytes"""
        assert parse_file_size("1024") == 1024
        assert parse_file_size("1024B") == 1024
        assert parse_file_size("2048b") == 2048
    
    def test_parse_file_size_kilobytes(self):
        """Test parsing file sizes in kilobytes"""
        assert parse_file_size("1K") == 1024
        assert parse_file_size("2k") == 2048
        assert parse_file_size("1.5K") == int(1.5 * 1024)
    
    def test_parse_file_size_megabytes(self):
        """Test parsing file sizes in megabytes"""
        assert parse_file_size("1M") == 1024 * 1024
        assert parse_file_size("100MB") == 100 * 1024 * 1024
        assert parse_file_size("2.5m") == int(2.5 * 1024 * 1024)
    
    def test_parse_file_size_gigabytes(self):
        """Test parsing file sizes in gigabytes"""
        assert parse_file_size("1G") == 1024 * 1024 * 1024
        assert parse_file_size("2GB") == 2 * 1024 * 1024 * 1024
    
    def test_parse_file_size_terabytes(self):
        """Test parsing file sizes in terabytes"""
        assert parse_file_size("1T") == 1024 * 1024 * 1024 * 1024
        assert parse_file_size("1TB") == 1024 * 1024 * 1024 * 1024
    
    def test_parse_file_size_edge_cases(self):
        """Test edge cases in file size parsing"""
        assert parse_file_size("0") == 0
        assert parse_file_size("0B") == 0
        assert parse_file_size("  100MB  ") == 100 * 1024 * 1024  # Whitespace handling


class TestConfigurationReload:
    """Test configuration reloading functionality"""
    
    def test_config_reload(self, temp_config_dir, sample_config_dict, mock_env_vars):
        """Test configuration reloading"""
        config_path = temp_config_dir / "reload_test.yml"
        
        # Create initial configuration
        with open(config_path, 'w') as f:
            yaml.dump(sample_config_dict, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            original_name = config_manager.get('bot.name')
            
            # Modify the configuration file
            modified_config = sample_config_dict.copy()
            modified_config['bot']['name'] = 'Modified Bot Name'
            
            with open(config_path, 'w') as f:
                yaml.dump(modified_config, f)
            
            # Reload configuration
            config_manager.reload()
            
            # Check that configuration was reloaded
            assert config_manager.get('bot.name') == 'Modified Bot Name'
            assert config_manager.get('bot.name') != original_name
        finally:
            os.chdir(original_cwd)