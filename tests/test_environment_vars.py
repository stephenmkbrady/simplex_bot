"""
Tests specifically for environment variable handling and edge cases
"""

import pytest
import os
import yaml
from unittest.mock import patch

from config_manager import ConfigManager


class TestEnvironmentVariableEdgeCases:
    """Test edge cases in environment variable substitution"""
    
    def test_missing_env_var_without_default(self, temp_config_dir, minimal_config, clear_env_vars):
        """Test behavior when environment variable is missing and no default provided"""
        config_data = minimal_config.copy()
        config_data.update({
            'test_value': '${MISSING_VAR}',
            'nested': {
                'value': '${ANOTHER_MISSING_VAR}'
            }
        })
        
        config_path = temp_config_dir / "missing_vars.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        # Should leave placeholder unchanged when var is missing
        assert config_manager.get('test_value') == '${MISSING_VAR}'
        assert config_manager.get('nested.value') == '${ANOTHER_MISSING_VAR}'
    
    def test_empty_env_var_with_default(self, temp_config_dir, minimal_config):
        """Test behavior when environment variable is empty but has default"""
        with patch.dict(os.environ, {'EMPTY_VAR': ''}, clear=False):
            config_data = minimal_config.copy()
            config_data.update({
                'with_default': '${EMPTY_VAR:-default_value}',
                'without_default': '${EMPTY_VAR}'
            })
            
            config_path = temp_config_dir / "empty_vars.yml"
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            # Empty var should use default when default is provided
            assert config_manager.get('with_default') == 'default_value'
            # Empty var without default should remain empty
            assert config_manager.get('without_default') == ''
    
    def test_whitespace_in_env_vars(self, temp_config_dir, minimal_config):
        """Test handling of whitespace in environment variables"""
        with patch.dict(os.environ, {
            'WHITESPACE_VAR': '  value with spaces  ',
            'TAB_VAR': '\tvalue\twith\ttabs\t',
            'NEWLINE_VAR': 'value\nwith\nnewlines'
        }, clear=False):
            config_data = minimal_config.copy()
            config_data.update({
                'whitespace': '${WHITESPACE_VAR}',
                'tabs': '${TAB_VAR}',
                'newlines': '${NEWLINE_VAR}'
            })
            
            config_path = temp_config_dir / "whitespace_vars.yml"
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            # Whitespace should be preserved
            assert config_manager.get('whitespace') == '  value with spaces  '
            assert config_manager.get('tabs') == '\tvalue\twith\ttabs\t'
            assert config_manager.get('newlines') == 'value\nwith\nnewlines'
    
    def test_special_characters_in_env_vars(self, temp_config_dir, minimal_config):
        """Test handling of special characters in environment variables"""
        with patch.dict(os.environ, {
            'SPECIAL_CHARS': '!@#$%^&*()_+-=[]{}|;:,.<>?',
            'UNICODE_VAR': 'Hello 世界 🌍 émojis',
            'QUOTES_VAR': '"double quotes" and \'single quotes\'',
            'BACKSLASH_VAR': 'path\\with\\backslashes'
        }, clear=False):
            config_data = minimal_config.copy()
            config_data.update({
                'special': '${SPECIAL_CHARS}',
                'unicode': '${UNICODE_VAR}',
                'quotes': '${QUOTES_VAR}',
                'backslashes': '${BACKSLASH_VAR}'
            })
            
            config_path = temp_config_dir / "special_chars_vars.yml"
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, allow_unicode=True)
            
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            # Special characters should be preserved
            assert config_manager.get('special') == '!@#$%^&*()_+-=[]{}|;:,.<>?'
            assert config_manager.get('unicode') == 'Hello 世界 🌍 émojis'
            assert config_manager.get('quotes') == '"double quotes" and \'single quotes\''
            assert config_manager.get('backslashes') == 'path\\with\\backslashes'
    
    def test_nested_env_var_substitution(self, temp_config_dir, minimal_config):
        """Test that nested environment variable references don't cause infinite loops"""
        with patch.dict(os.environ, {
            'VAR1': '${VAR2}',  # References VAR2
            'VAR2': 'actual_value',
            'SELF_REF': '${SELF_REF}'  # Self-reference
        }, clear=False):
            config_data = minimal_config.copy()
            config_data.update({
                'nested': '${VAR1}',
                'self_ref': '${SELF_REF}'
            })
            
            config_path = temp_config_dir / "nested_vars.yml"
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            # Should substitute only one level (no recursive substitution)
            assert config_manager.get('nested') == '${VAR2}'
            assert config_manager.get('self_ref') == '${SELF_REF}'
    
    def test_malformed_env_var_syntax(self, temp_config_dir, minimal_config):
        """Test handling of malformed environment variable syntax"""
        config_data = minimal_config.copy()
        config_data.update({
            'missing_brace': '${MISSING_BRACE',
            'extra_brace': '${EXTRA_BRACE}}',
            'empty_var': '${}',
            'no_var_name': '${:-default}',
            'invalid_chars': '${INVALID-VAR-NAME}',
            'multiple_colons': '${VAR:-default:-extra}'
        })
        
        config_path = temp_config_dir / "malformed_vars.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        # Malformed syntax should be left unchanged
        assert config_manager.get('missing_brace') == '${MISSING_BRACE'
        assert config_manager.get('extra_brace') == '${EXTRA_BRACE}}'
        assert config_manager.get('empty_var') == '${}'
        assert config_manager.get('no_var_name') == '${:-default}'
        
        # Invalid characters in var names should be handled gracefully
        assert '${INVALID-VAR-NAME}' in config_manager.get('invalid_chars')
        
        # Multiple colons should use first as separator
        assert config_manager.get('multiple_colons') == 'default:-extra'
    
    def test_env_var_case_sensitivity(self, temp_config_dir, minimal_config):
        """Test that environment variable names are case sensitive"""
        with patch.dict(os.environ, {
            'UPPER_VAR': 'upper_value',
            'lower_var': 'lower_value',
            'Mixed_Var': 'mixed_value'
        }, clear=False):
            config_data = minimal_config.copy()
            config_data.update({
                'upper': '${UPPER_VAR}',
                'lower': '${lower_var}',
                'mixed': '${Mixed_Var}',
                'wrong_case1': '${upper_var}',  # Wrong case
                'wrong_case2': '${LOWER_VAR}',  # Wrong case
                'wrong_case3': '${MIXED_VAR}'   # Wrong case
            })
            
            config_path = temp_config_dir / "case_vars.yml"
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            # Correct case should work
            assert config_manager.get('upper') == 'upper_value'
            assert config_manager.get('lower') == 'lower_value'
            assert config_manager.get('mixed') == 'mixed_value'
            
            # Wrong case should not match
            assert config_manager.get('wrong_case1') == '${upper_var}'
            assert config_manager.get('wrong_case2') == '${LOWER_VAR}'
            assert config_manager.get('wrong_case3') == '${MIXED_VAR}'


class TestEnvironmentFileHandling:
    """Test .env file loading and processing"""
    
    def test_env_file_loading(self, temp_config_dir, minimal_config):
        """Test loading environment variables from .env file"""
        env_content = """
# This is a comment
TEST_VAR1=value1
TEST_VAR2=value2
TEST_VAR3=value with spaces
TEST_VAR4="quoted value"
TEST_VAR5='single quoted'

# Another comment
EMPTY_VAR=
"""
        
        env_path = temp_config_dir / ".env"
        with open(env_path, 'w') as f:
            f.write(env_content)
        
        config_data = minimal_config.copy()
        config_data.update({
            'var1': '${TEST_VAR1}',
            'var2': '${TEST_VAR2}',
            'var3': '${TEST_VAR3}',
            'var4': '${TEST_VAR4}',
            'var5': '${TEST_VAR5}',
            'empty': '${EMPTY_VAR:-default}'
        })
        
        config_path = temp_config_dir / "env_file_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)
        
        try:
            config_manager = ConfigManager(str(config_path), str(env_path))
            
            assert config_manager.get('var1') == 'value1'
            assert config_manager.get('var2') == 'value2'
            assert config_manager.get('var3') == 'value with spaces'
            assert config_manager.get('var4') == '"quoted value"'
            assert config_manager.get('var5') == "'single quoted'"
            assert config_manager.get('empty') == 'default'  # Empty var should use default
        finally:
            os.chdir(original_cwd)
    
    def test_env_file_missing(self, temp_config_dir, minimal_config, caplog):
        """Test behavior when .env file is missing"""
        config_data = minimal_config.copy()
        config_data.update({'test': '${TEST_VAR:-default}'})
        
        config_path = temp_config_dir / "no_env_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        nonexistent_env = temp_config_dir / "nonexistent.env"
        
        config_manager = ConfigManager(str(config_path), str(nonexistent_env))
        
        # Should log warning about missing .env file
        assert "Environment file" in caplog.text
        assert "not found" in caplog.text
        
        # Should still work with defaults
        assert config_manager.get('test') == 'default'
    
    def test_env_file_vs_system_env_precedence(self, temp_config_dir, minimal_config):
        """Test precedence between .env file and system environment variables"""
        # Create .env file
        env_content = "TEST_PRECEDENCE=env_file_value\n"
        env_path = temp_config_dir / ".env"
        with open(env_path, 'w') as f:
            f.write(env_content)
        
        # Set system environment variable with different value
        with patch.dict(os.environ, {'TEST_PRECEDENCE': 'system_env_value'}, clear=False):
            config_data = minimal_config.copy()
            config_data.update({'test': '${TEST_PRECEDENCE}'})
            
            config_path = temp_config_dir / "precedence_test.yml"
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            original_cwd = os.getcwd()
            os.chdir(temp_config_dir)
            
            try:
                config_manager = ConfigManager(str(config_path), str(env_path))
                
                # System environment should take precedence over .env file
                # (this depends on python-dotenv behavior - it doesn't override existing env vars by default)
                assert config_manager.get('test') == 'system_env_value'
            finally:
                os.chdir(original_cwd)


class TestBooleanConversion:
    """Test boolean-like environment variable handling"""
    
    def test_boolean_string_values(self, temp_config_dir, minimal_config):
        """Test various boolean string representations"""
        with patch.dict(os.environ, {
            'BOOL_TRUE': 'true',
            'BOOL_FALSE': 'false',
            'BOOL_YES': 'yes',
            'BOOL_NO': 'no',
            'BOOL_ON': 'on',
            'BOOL_OFF': 'off',
            'BOOL_1': '1',
            'BOOL_0': '0',
            'BOOL_UPPER': 'TRUE',
            'BOOL_MIXED': 'False'
        }, clear=False):
            config_data = minimal_config.copy()
            config_data.update({
                'true_val': '${BOOL_TRUE}',
                'false_val': '${BOOL_FALSE}',
                'yes_val': '${BOOL_YES}',
                'no_val': '${BOOL_NO}',
                'on_val': '${BOOL_ON}',
                'off_val': '${BOOL_OFF}',
                'one_val': '${BOOL_1}',
                'zero_val': '${BOOL_0}',
                'upper_val': '${BOOL_UPPER}',
                'mixed_val': '${BOOL_MIXED}'
            })
            
            config_path = temp_config_dir / "boolean_test.yml"
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f)
            
            config_manager = ConfigManager(str(config_path), "nonexistent.env")
            
            # All should be returned as strings (ConfigManager doesn't do boolean conversion)
            assert config_manager.get('true_val') == 'true'
            assert config_manager.get('false_val') == 'false'
            assert config_manager.get('yes_val') == 'yes'
            assert config_manager.get('no_val') == 'no'
            assert config_manager.get('on_val') == 'on'
            assert config_manager.get('off_val') == 'off'
            assert config_manager.get('one_val') == '1'
            assert config_manager.get('zero_val') == '0'
            assert config_manager.get('upper_val') == 'TRUE'
            assert config_manager.get('mixed_val') == 'False'
    
    def test_boolean_default_values(self, temp_config_dir, minimal_config, clear_env_vars):
        """Test boolean default values"""
        config_data = minimal_config.copy()
        config_data.update({
            'bool_with_true_default': '${MISSING_BOOL:-true}',
            'bool_with_false_default': '${MISSING_BOOL:-false}',
            'bool_with_yes_default': '${MISSING_BOOL:-yes}',
            'bool_with_no_default': '${MISSING_BOOL:-no}',
            'bool_with_1_default': '${MISSING_BOOL:-1}',
            'bool_with_0_default': '${MISSING_BOOL:-0}'
        })
        
        config_path = temp_config_dir / "bool_defaults_test.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        config_manager = ConfigManager(str(config_path), "nonexistent.env")
        
        # Default values should be used
        assert config_manager.get('bool_with_true_default') == 'true'
        assert config_manager.get('bool_with_false_default') == 'false'
        assert config_manager.get('bool_with_yes_default') == 'yes'
        assert config_manager.get('bool_with_no_default') == 'no'
        assert config_manager.get('bool_with_1_default') == '1'
        assert config_manager.get('bool_with_0_default') == '0'