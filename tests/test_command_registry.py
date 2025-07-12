"""
Tests for CommandRegistry component
"""

import pytest
import asyncio
import logging
from unittest.mock import AsyncMock

from bot import CommandRegistry


class TestCommandRegistry:
    """Test CommandRegistry functionality"""
    
    def setup_method(self):
        """Setup test dependencies"""
        self.logger = logging.getLogger('test')
        from admin_manager import AdminManager
        self.admin_manager = AdminManager(logger=self.logger)
        self.command_registry = CommandRegistry(self.logger, self.admin_manager)
    
    def test_command_registry_initialization(self):
        """Test CommandRegistry initialization"""
        assert self.command_registry.logger == self.logger
        assert len(self.command_registry.commands) > 0
        
        # Check that only core command is registered (others moved to plugins)
        core_commands = ['info']
        for cmd in core_commands:
            assert cmd in self.command_registry.commands
            assert callable(self.command_registry.commands[cmd])
    
    def test_register_command(self):
        """Test command registration"""
        async def test_command(args, contact_name, send_callback):
            await send_callback(contact_name, "Test response")
        
        self.command_registry.register_command('test', test_command)
        
        assert 'test' in self.command_registry.commands
        assert self.command_registry.commands['test'] == test_command
    
    def test_get_command(self):
        """Test command retrieval"""
        # Get existing command
        info_command = self.command_registry.get_command('info')
        assert callable(info_command)
        
        # Get non-existent command
        assert self.command_registry.get_command('nonexistent') is None
    
    def test_list_commands(self):
        """Test command listing"""
        commands = self.command_registry.list_commands()
        
        assert isinstance(commands, list)
        assert len(commands) > 0
        assert 'info' in commands
    
    def test_is_command(self):
        """Test command detection"""
        # Valid commands - is_command now accepts any ! command and checks plugins later
        assert self.command_registry.is_command('!info') == True
        assert self.command_registry.is_command('!help') == True  # Plugin commands also accepted
        assert self.command_registry.is_command('!status') == True
        assert self.command_registry.is_command('!ping') == True
        assert self.command_registry.is_command('!stats') == True
        
        # Invalid commands
        assert self.command_registry.is_command('!nonexistent') == True  # Still valid format
        assert self.command_registry.is_command('info') == False  # Missing !
        assert self.command_registry.is_command('hello world') == False
        assert self.command_registry.is_command('') == False
        assert self.command_registry.is_command('!') == False  # Empty command
        
        # Edge cases
        assert self.command_registry.is_command('!info extra args') == True  # Should still detect info
        assert self.command_registry.is_command('  !info  ') == True  # Should handle whitespace
    
    @pytest.mark.asyncio
    async def test_execute_command_info(self):
        """Test info command execution"""
        result = await self.command_registry.execute_command('!info', 'TestUser')
        
        assert result is not None
        assert isinstance(result, str)
        assert 'info' in result.lower() or 'bot' in result.lower()
    
    @pytest.mark.asyncio
    async def test_execute_command_moved_to_plugin(self):
        """Test that commands moved to plugins return unknown command when no plugin manager"""
        # These commands were moved to plugins and should return unknown when no plugin manager
        for cmd in ['!help', '!status', '!ping', '!stats']:
            result = await self.command_registry.execute_command(cmd, 'TestUser')
            assert result is not None
            assert isinstance(result, str)
            assert 'Unknown command' in result  # Capital U in actual implementation
    
    
    
    @pytest.mark.asyncio
    async def test_execute_command_with_args(self):
        """Test command execution with arguments"""
        result = await self.command_registry.execute_command('!info extra args', 'TestUser')
        
        assert result is not None
        assert isinstance(result, str)
        # Should still execute info command even with extra args
        assert 'info' in result.lower() or 'bot' in result.lower()
    
    @pytest.mark.asyncio
    async def test_execute_command_nonexistent(self):
        """Test execution of non-existent command"""
        result = await self.command_registry.execute_command('!nonexistent', 'TestUser')
        
        assert result is not None
        assert isinstance(result, str)
        assert 'Unknown command' in result  # Capital U in actual implementation
        assert 'nonexistent' in result
    
    @pytest.mark.asyncio
    async def test_execute_command_invalid_format(self):
        """Test execution of invalid command format"""
        # Not a command (missing !)
        result = await self.command_registry.execute_command('help', 'TestUser')
        assert result is None
        
        # Empty command
        result = await self.command_registry.execute_command('', 'TestUser')
        assert result is None
        
        # Just exclamation mark
        result = await self.command_registry.execute_command('!', 'TestUser')
        assert result is None  # is_command returns False for just '!'
    
    @pytest.mark.asyncio
    async def test_custom_command_registration_and_execution(self):
        """Test registering and executing custom commands"""
        # Register a custom command
        async def custom_command(args, contact_name, send_callback):
            response = f"Hello {contact_name}! Args: {', '.join(args) if args else 'none'}"
            await send_callback(contact_name, response)
        
        self.command_registry.register_command('custom', custom_command)
        
        # Test execution
        result = await self.command_registry.execute_command('!custom arg1 arg2', 'TestUser')
        
        assert result is not None
        assert 'Hello TestUser!' in result
        assert 'arg1, arg2' in result
    
    @pytest.mark.asyncio
    async def test_command_error_handling(self):
        """Test command error handling"""
        # Register a command that raises an exception
        async def error_command(args, contact_name, send_callback):
            raise Exception("Command error")
        
        self.command_registry.register_command('error', error_command)
        
        # Test execution - should handle error gracefully
        result = await self.command_registry.execute_command('!error', 'TestUser')
        
        assert result is not None
        assert 'Error executing command' in result
        assert 'error' in result  # Should mention the command name


class TestCommandRegistryIntegration:
    """Test CommandRegistry integration scenarios"""
    
    @pytest.mark.asyncio
    async def test_command_registry_with_real_callbacks(self):
        """Test CommandRegistry with actual callback functions"""
        logger = logging.getLogger('test')
        from admin_manager import AdminManager
        admin_manager = AdminManager(logger=logger)
        command_registry = CommandRegistry(logger, admin_manager)
        
        # Track callback calls
        callback_calls = []
        
        async def mock_send_callback(contact, message):
            callback_calls.append((contact, message))
        
        # Execute info command with real callback
        info_handler = command_registry.get_command('info')
        await info_handler([], 'TestUser', mock_send_callback)
        
        # Verify callback was called
        assert len(callback_calls) == 1
        assert callback_calls[0][0] == 'TestUser'
        assert len(callback_calls[0][1]) > 0  # Should return some info
    
    def test_command_parsing_edge_cases(self):
        """Test command parsing edge cases"""
        logger = logging.getLogger('test')
        from admin_manager import AdminManager
        admin_manager = AdminManager(logger=logger)
        command_registry = CommandRegistry(logger, admin_manager)
        
        # Test various command formats
        test_cases = [
            ('!info', True),
            ('!INFO', True),        # Valid command format
            ('!!info', True),       # Double exclamation - treated as valid (!info after first !)
            ('!info!', True),       # Should still detect info
            ('!info_test', True),   # Valid command format
            ('!info-test', True),   # Valid command format  
            ('!info123', True),     # Valid command format
            ('!info ', True),       # Trailing space
            (' !info', True),       # Leading space
            ('!info\n', True),      # Newline
            ('!info\t', True),      # Tab
            ('!help', True),        # Valid command format (plugin will handle)
            ('!status', True),      # Valid command format (plugin will handle)
            ('!ping', True),        # Valid command format (plugin will handle)
            ('!stats', True),       # Valid command format (plugin will handle)
        ]
        
        for command_text, expected in test_cases:
            result = command_registry.is_command(command_text)
            assert result == expected, f"Failed for '{command_text}': expected {expected}, got {result}"