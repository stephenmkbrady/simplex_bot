#!/usr/bin/env python3
"""
Admin Manager for SimpleX Chat Bot
Handles admin permissions and command authorization
"""

import os
import yaml
import logging
from typing import Dict, Any, List, Optional, Set
from pathlib import Path


class AdminManager:
    """Manages admin permissions and command authorization"""
    
    def __init__(self, config_path: str = "admin_config.yml", logger: Optional[logging.Logger] = None):
        """
        Initialize admin manager
        
        Args:
            config_path: Path to admin configuration file
            logger: Logger instance
        """
        self.config_path = config_path
        self.logger = logger or logging.getLogger(__name__)
        self.config: Dict[str, Any] = {}
        self.admins: Set[str] = set()
        self.admin_commands: Dict[str, List[str]] = {}
        self.public_commands: List[str] = []
        
        # Load configuration
        self._load_config()
    
    def _load_config(self):
        """Load admin configuration from YAML file"""
        if not os.path.exists(self.config_path):
            self.logger.info(f"Admin config file {self.config_path} not found, creating default")
            self._create_default_config()
            return
        
        try:
            with open(self.config_path, 'r') as file:
                self.config = yaml.safe_load(file) or {}
            
            # Parse configuration
            self._parse_config()
            
            self.logger.info(f"Loaded admin configuration from {self.config_path}")
            self.logger.info(f"Admins: {list(self.admins)}")
            self.logger.info(f"Public commands: {self.public_commands}")
            
        except Exception as e:
            self.logger.error(f"Error loading admin config: {e}")
            self._create_default_config()
    
    def _parse_config(self):
        """Parse loaded configuration into internal structures"""
        # Get admins list
        admins_config = self.config.get('admins', [])
        
        # Handle both simple list and dict format
        if isinstance(admins_config, list):
            # Simple list format: ['admin1', 'admin2']
            self.admins = set(admins_config)
            # All admins can run all commands by default
            for admin in self.admins:
                self.admin_commands[admin] = ['*']
        else:
            # Dict format with specific permissions
            for admin_name, permissions in admins_config.items():
                self.admins.add(admin_name)
                if isinstance(permissions, list):
                    self.admin_commands[admin_name] = permissions
                elif isinstance(permissions, dict):
                    self.admin_commands[admin_name] = permissions.get('commands', ['*'])
                else:
                    self.admin_commands[admin_name] = ['*']
        
        # Get public commands that everyone can run
        self.public_commands = self.config.get('public_commands', [
            'help', 'status', 'ping', 'stats'
        ])
    
    def _create_default_config(self):
        """Create default admin configuration file"""
        default_config = {
            'admins': {
                'admin': {
                    'commands': ['*'],  # '*' means all commands
                    'description': 'Main administrator with full access'
                }
            },
            'public_commands': [
                'help',
                'status', 
                'ping',
                'stats'
            ],
            'settings': {
                'require_admin_for_plugins': True,
                'default_deny_message': 'Access denied. You need admin permissions to use this command.',
                'admin_only_mode': False
            }
        }
        
        try:
            with open(self.config_path, 'w') as file:
                yaml.dump(default_config, file, default_flow_style=False, indent=2)
            
            self.config = default_config
            self._parse_config()
            
            self.logger.info(f"Created default admin config at {self.config_path}")
            
        except Exception as e:
            self.logger.error(f"Error creating default admin config: {e}")
            # Fallback to in-memory defaults
            self.config = default_config
            self._parse_config()
    
    def reload_config(self):
        """Reload configuration from file"""
        self._load_config()
    
    def is_admin(self, user_identifier: str) -> bool:
        """Check if user is an admin by Contact ID"""
        return user_identifier in self.admins
    
    def can_run_command(self, user_identifier: str, command: str) -> bool:
        """Check if user can run a specific command by Contact ID"""
        # Check if admin-only mode is enabled
        if self.config.get('settings', {}).get('admin_only_mode', False):
            return self.is_admin(user_identifier)
        
        # Check public commands first
        if command in self.public_commands:
            return True
        
        # Check admin permissions
        if not self.is_admin(user_identifier):
            # Non-admin trying to run non-public command
            return False
        
        # Admin user - check their specific permissions
        user_commands = self.admin_commands.get(user_identifier, [])
        
        # '*' means all commands
        if '*' in user_commands:
            return True
        
        # Check specific command permission
        return command in user_commands
    
    def get_denied_message(self, user_identifier: str, command: str) -> str:
        """Get appropriate denial message"""
        settings = self.config.get('settings', {})
        
        if settings.get('admin_only_mode', False):
            return "Bot is in admin-only mode. Only administrators can use commands."
        
        default_message = settings.get('default_deny_message', 
                                     'Access denied. You need admin permissions to use this command.')
        
        return default_message
    
    def add_admin(self, user_name: str, commands: List[str] = None) -> bool:
        """Add a new admin user"""
        if commands is None:
            commands = ['*']
        
        try:
            self.admins.add(user_name)
            self.admin_commands[user_name] = commands
            
            # Update config file
            if 'admins' not in self.config:
                self.config['admins'] = {}
            
            self.config['admins'][user_name] = {
                'commands': commands,
                'description': f'Admin added at runtime'
            }
            
            # Save to file
            with open(self.config_path, 'w') as file:
                yaml.dump(self.config, file, default_flow_style=False, indent=2)
            
            self.logger.info(f"Added admin: {user_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding admin {user_name}: {e}")
            return False
    
    def remove_admin(self, user_name: str) -> bool:
        """Remove an admin user"""
        if user_name not in self.admins:
            return False
        
        try:
            self.admins.remove(user_name)
            self.admin_commands.pop(user_name, None)
            
            # Update config file
            if 'admins' in self.config and user_name in self.config['admins']:
                del self.config['admins'][user_name]
            
            # Save to file
            with open(self.config_path, 'w') as file:
                yaml.dump(self.config, file, default_flow_style=False, indent=2)
            
            self.logger.info(f"Removed admin: {user_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error removing admin {user_name}: {e}")
            return False
    
    def list_admins(self) -> Dict[str, List[str]]:
        """List all admins and their permissions"""
        return self.admin_commands.copy()
    
    def get_user_permissions(self, user_identifier: str) -> Dict[str, Any]:
        """Get detailed permissions for a user"""
        return {
            'is_admin': self.is_admin(user_identifier),
            'admin_commands': self.admin_commands.get(user_identifier, []),
            'public_commands': self.public_commands,
            'can_run_public': True
        }
    
    def get_admin_info(self, user_identifier: str) -> Dict[str, Any]:
        """Get admin information including localDisplayName for reference"""
        if not self.is_admin(user_identifier):
            return None
            
        admin_config = self.config.get('admins', {}).get(user_identifier, {})
        return {
            'contact_id': user_identifier,
            'commands': admin_config.get('commands', []),
            'description': admin_config.get('description', ''),
            'localDisplayName': admin_config.get('localDisplayName', 'Unknown')
        }