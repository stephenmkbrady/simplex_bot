#!/usr/bin/env python3
"""
Configuration Manager for SimpleX Chat Bot
Handles YAML configuration loading with environment variable substitution
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import re

logger = logging.getLogger(__name__)

# Constants
DEFAULT_RETENTION_DAYS = 30
BYTES_PER_KB = 1024


class ConfigManager:
    """Manages bot configuration from YAML files with environment variable substitution"""
    
    def __init__(self, config_path: str = "config.yml", env_file: str = ".env"):
        """
        Initialize configuration manager
        
        Args:
            config_path: Path to YAML configuration file
            env_file: Path to environment file
        """
        self.config_path = config_path
        self.env_file = env_file
        self.config: Dict[str, Any] = {}
        
        # Load environment variables first
        self._load_env_file()
        
        # Load and parse configuration
        self._load_config()
    
    def _load_env_file(self):
        """Load environment variables from .env file"""
        if os.path.exists(self.env_file):
            load_dotenv(self.env_file)
            logger.info(f"Loaded environment variables from {self.env_file}")
        else:
            logger.warning(f"Environment file {self.env_file} not found")
    
    def _substitute_env_vars(self, value: Any) -> Any:
        """
        Recursively substitute environment variables in configuration values
        Supports ${VAR_NAME} and ${VAR_NAME:-default_value} syntax
        """
        if isinstance(value, str):
            # Pattern to match ${VAR_NAME} or ${VAR_NAME:-default}
            pattern = r'\$\{([^}]+)\}'
            
            def replace_var(match):
                var_expr = match.group(1)
                
                # Check if there's a default value
                if ':-' in var_expr:
                    var_name, default_value = var_expr.split(':-', 1)
                    return os.getenv(var_name.strip(), default_value)
                else:
                    var_name = var_expr.strip()
                    env_value = os.getenv(var_name)
                    if env_value is None:
                        logger.warning(f"Environment variable {var_name} not found")
                        return match.group(0)  # Return original if not found
                    return env_value
            
            return re.sub(pattern, replace_var, value)
        
        elif isinstance(value, dict):
            return {k: self._substitute_env_vars(v) for k, v in value.items()}
        
        elif isinstance(value, list):
            return [self._substitute_env_vars(item) for item in value]
        
        else:
            return value
    
    def _load_config(self):
        """Load and parse YAML configuration file"""
        if not os.path.exists(self.config_path):
            logger.error(f"Configuration file {self.config_path} not found")
            # Create default configuration
            self._create_default_config()
            return
        
        try:
            with open(self.config_path, 'r') as file:
                raw_config = yaml.safe_load(file)
            
            # Substitute environment variables
            self.config = self._substitute_env_vars(raw_config)
            
            # Validate configuration
            self._validate_config()
            
            logger.info(f"Successfully loaded configuration from {self.config_path}")
            
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML configuration: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise
    
    def _create_default_config(self):
        """Create a default configuration if none exists"""
        self.config = {
            'servers': {
                'smp': ['smp://localhost:5223'],
                'xftp': ['xftp://localhost:5443']
            },
            'bot': {
                'name': 'SimpleX Bot',
                'websocket_url': 'ws://localhost:3030',
                'auto_accept_contacts': True
            },
            'logging': {
                'daily_rotation': True,
                'message_log_separate': True,
                'retention_days': DEFAULT_RETENTION_DAYS,
                'log_level': 'INFO'
            },
            'media': {
                'download_enabled': True,
                'max_file_size': '100MB',
                'allowed_types': ['image', 'video', 'document', 'audio'],
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
        logger.warning("Using default configuration")
    
    def _validate_config(self):
        """Validate configuration structure and values"""
        required_sections = ['servers', 'bot', 'logging', 'media', 'commands', 'security']
        
        for section in required_sections:
            if section not in self.config:
                logger.error(f"Missing required configuration section: {section}")
                raise ValueError(f"Missing configuration section: {section}")
        
        # Validate servers
        if not self.config['servers'].get('smp'):
            logger.error("No SMP servers configured")
            raise ValueError("At least one SMP server must be configured")
        
        # Validate websocket URL
        websocket_url = self.config['bot'].get('websocket_url')
        if not websocket_url or not websocket_url.startswith('ws://'):
            logger.error("Invalid WebSocket URL configuration")
            raise ValueError("WebSocket URL must start with ws://")
        
        # Validate media settings
        media_path = self.config['media'].get('storage_path')
        if media_path and not os.path.exists(os.path.dirname(media_path)):
            logger.warning(f"Media storage directory does not exist: {media_path}")
        
        logger.info("Configuration validation passed")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation
        
        Args:
            key_path: Dot-separated path to configuration value (e.g., 'bot.name')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            logger.debug(f"Configuration key not found: {key_path}")
            return default
    
    def get_servers(self) -> Dict[str, list]:
        """Get server configuration"""
        return self.config.get('servers', {})
    
    def get_bot_config(self) -> Dict[str, Any]:
        """Get bot configuration"""
        return self.config.get('bot', {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration"""
        return self.config.get('logging', {})
    
    def get_media_config(self) -> Dict[str, Any]:
        """Get media configuration"""
        return self.config.get('media', {})
    
    def get_commands_config(self) -> Dict[str, Any]:
        """Get commands configuration"""
        return self.config.get('commands', {})
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration"""
        return self.config.get('security', {})
    
    def reload(self):
        """Reload configuration from file"""
        logger.info("Reloading configuration")
        self._load_env_file()
        self._load_config()
    
    def to_dict(self) -> Dict[str, Any]:
        """Return full configuration as dictionary"""
        return self.config.copy()


def parse_file_size(size_str: str) -> int:
    """
    Parse file size string (e.g., '100MB', '1GB') to bytes
    
    Args:
        size_str: Size string with unit
        
    Returns:
        Size in bytes
    """
    size_str = size_str.upper().strip()
    
    if size_str.endswith('B'):
        size_str = size_str[:-1]
    
    multipliers = {
        'K': BYTES_PER_KB,
        'M': BYTES_PER_KB ** 2,
        'G': BYTES_PER_KB ** 3,
        'T': BYTES_PER_KB ** 4
    }
    
    if size_str[-1] in multipliers:
        return int(float(size_str[:-1]) * multipliers[size_str[-1]])
    
    return int(size_str)


if __name__ == "__main__":
    # Test the configuration manager
    logging.basicConfig(level=logging.INFO)
    
    try:
        config = ConfigManager()
        print("Configuration loaded successfully:")
        print(f"Bot name: {config.get('bot.name')}")
        print(f"SMP servers: {config.get('servers.smp')}")
        print(f"Media enabled: {config.get('media.download_enabled')}")
        
    except Exception as e:
        print(f"Configuration error: {e}")