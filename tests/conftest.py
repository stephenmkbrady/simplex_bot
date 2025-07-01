"""
Pytest configuration and fixtures for SimpleX Bot tests
"""

import pytest
import tempfile
import os
import yaml
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for test configuration files"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_config_dict():
    """Sample configuration dictionary for testing"""
    return {
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


@pytest.fixture
def sample_env_vars():
    """Sample environment variables for testing"""
    return {
        'SMP_SERVER_1': 'smp://test-server1.com',
        'SMP_SERVER_2': 'smp://test-server2.com',
        'XFTP_SERVER_1': 'xftp://test-files1.com',
        'XFTP_SERVER_2': 'xftp://test-files2.com',
        'BOT_NAME': 'Test Bot',
        'WEBSOCKET_URL': 'ws://test:3030',
        'AUTO_ACCEPT_CONTACTS': 'false',
        'LOG_RETENTION_DAYS': '7',
        'LOG_LEVEL': 'DEBUG',
        'MEDIA_DOWNLOAD_ENABLED': 'true',
        'MAX_FILE_SIZE': '50MB',
        'MEDIA_STORAGE_PATH': './test_media',
        'MAX_MESSAGE_LENGTH': '2048',
        'RATE_LIMIT_MESSAGES': '5',
        'RATE_LIMIT_WINDOW': '30'
    }


@pytest.fixture
def config_file(temp_config_dir, sample_config_dict):
    """Create a temporary config.yml file"""
    config_path = temp_config_dir / "config.yml"
    with open(config_path, 'w') as f:
        yaml.dump(sample_config_dict, f)
    return config_path


@pytest.fixture
def env_file(temp_config_dir, sample_env_vars):
    """Create a temporary .env file"""
    env_path = temp_config_dir / ".env"
    with open(env_path, 'w') as f:
        for key, value in sample_env_vars.items():
            f.write(f"{key}={value}\n")
    return env_path


@pytest.fixture
def minimal_config():
    """Minimal valid configuration for testing"""
    return {
        'servers': {
            'smp': ['smp://localhost:5223'],
            'xftp': ['xftp://localhost:5443']
        },
        'bot': {
            'name': 'Test Bot',
            'websocket_url': 'ws://localhost:3030',
            'auto_accept_contacts': True
        },
        'logging': {
            'daily_rotation': True,
            'message_log_separate': True,
            'retention_days': 30,
            'log_level': 'INFO'
        },
        'media': {
            'download_enabled': True,
            'max_file_size': '100MB',
            'allowed_types': ['image', 'video', 'document'],
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


@pytest.fixture
def invalid_config():
    """Invalid configuration for testing validation"""
    return {
        'servers': {
            'smp': [],  # Empty SMP servers - should fail validation
            'xftp': ['xftp://localhost:5443']
        },
        'bot': {
            'name': 'Test Bot',
            'websocket_url': 'invalid://url',  # Invalid WebSocket URL
            'auto_accept_contacts': True
        }
        # Missing required sections
    }


@pytest.fixture
def mock_env_vars(sample_env_vars):
    """Mock environment variables for testing"""
    with patch.dict(os.environ, sample_env_vars, clear=False):
        yield sample_env_vars


@pytest.fixture
def clear_env_vars():
    """Clear all test environment variables"""
    test_vars = [
        'SMP_SERVER_1', 'SMP_SERVER_2', 'XFTP_SERVER_1', 'XFTP_SERVER_2',
        'BOT_NAME', 'WEBSOCKET_URL', 'AUTO_ACCEPT_CONTACTS',
        'LOG_RETENTION_DAYS', 'LOG_LEVEL', 'MEDIA_DOWNLOAD_ENABLED',
        'MAX_FILE_SIZE', 'MEDIA_STORAGE_PATH', 'MAX_MESSAGE_LENGTH',
        'RATE_LIMIT_MESSAGES', 'RATE_LIMIT_WINDOW'
    ]
    
    # Store original values
    original_values = {}
    for var in test_vars:
        if var in os.environ:
            original_values[var] = os.environ[var]
            del os.environ[var]
    
    yield
    
    # Restore original values
    for var, value in original_values.items():
        os.environ[var] = value