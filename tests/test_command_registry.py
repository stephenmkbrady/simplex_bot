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
        self.command_registry = CommandRegistry(self.logger)
    
    def test_command_registry_initialization(self):
        """Test CommandRegistry initialization"""
        assert self.command_registry.logger == self.logger
        assert len(self.command_registry.commands) > 0
        
        # Check default commands are registered
        default_commands = ['help', 'status', 'ping', 'stats']
        for cmd in default_commands:
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
        help_command = self.command_registry.get_command('help')
        assert callable(help_command)
        
        # Get non-existent command
        assert self.command_registry.get_command('nonexistent') is None
    
    def test_list_commands(self):
        """Test command listing"""
        commands = self.command_registry.list_commands()
        
        assert isinstance(commands, list)
        assert len(commands) > 0
        assert 'help' in commands
        assert 'status' in commands
        assert 'ping' in commands
        assert 'stats' in commands
    
    def test_is_command(self):
        """Test command detection"""
        # Valid commands
        assert self.command_registry.is_command('!help') == True
        assert self.command_registry.is_command('!status') == True
        assert self.command_registry.is_command('!ping') == True
        assert self.command_registry.is_command('!stats') == True
        
        # Invalid commands
        assert self.command_registry.is_command('!nonexistent') == False
        assert self.command_registry.is_command('help') == False  # Missing !
        assert self.command_registry.is_command('hello world') == False
        assert self.command_registry.is_command('') == False
        assert self.command_registry.is_command('!') == False
        
        # Edge cases
        assert self.command_registry.is_command('!help extra args') == True  # Should still detect help
        assert self.command_registry.is_command('  !help  ') == True  # Should handle whitespace
    
    @pytest.mark.asyncio
    async def test_execute_command_help(self):
        """Test help command execution"""
        result = await self.command_registry.execute_command('!help', 'TestUser')
        
        assert result is not None
        assert isinstance(result, str)
        assert 'commands' in result.lower()
        assert 'help' in result
        assert 'status' in result
        assert 'ping' in result
        assert 'stats' in result
    
    @pytest.mark.asyncio
    async def test_execute_command_status(self):
        """Test status command execution"""
        result = await self.command_registry.execute_command('!status', 'TestUser')
        
        assert result is not None
        assert isinstance(result, str)
        assert 'running' in result.lower() or 'healthy' in result.lower()
    
    @pytest.mark.asyncio
    async def test_execute_command_ping(self):
        """Test ping command execution"""
        result = await self.command_registry.execute_command('!ping', 'TestUser')
        
        assert result is not None
        assert isinstance(result, str)
        assert 'pong' in result.lower()
    
    @pytest.mark.asyncio
    async def test_execute_command_stats(self):
        """Test stats command execution"""
        result = await self.command_registry.execute_command('!stats', 'TestUser')
        
        assert result is not None
        assert isinstance(result, str)
        # Stats command returns "coming soon" message
        assert 'soon' in result.lower() or 'statistics' in result.lower()
    
    @pytest.mark.asyncio
    async def test_execute_command_with_args(self):
        """Test command execution with arguments"""
        result = await self.command_registry.execute_command('!help extra args', 'TestUser')
        
        assert result is not None
        assert isinstance(result, str)
        # Should still execute help command even with extra args
        assert 'commands' in result.lower()
    
    @pytest.mark.asyncio
    async def test_execute_command_nonexistent(self):
        """Test execution of non-existent command"""
        result = await self.command_registry.execute_command('!nonexistent', 'TestUser')
        
        assert result is not None
        assert isinstance(result, str)
        assert 'unknown command' in result.lower()
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
        assert result is not None
        assert 'unknown command' in result.lower()
    
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
        assert 'error' in result.lower()
        assert 'error' in result  # Should mention the command name


class TestCommandRegistryIntegration:
    """Test CommandRegistry integration scenarios"""
    
    @pytest.mark.asyncio
    async def test_command_registry_with_real_callbacks(self):
        """Test CommandRegistry with actual callback functions"""
        logger = logging.getLogger('test')
        command_registry = CommandRegistry(logger)
        
        # Track callback calls
        callback_calls = []
        
        async def mock_send_callback(contact, message):
            callback_calls.append((contact, message))
        
        # Execute help command with real callback
        help_handler = command_registry.get_command('help')
        await help_handler([], 'TestUser', mock_send_callback)
        
        # Verify callback was called
        assert len(callback_calls) == 1
        assert callback_calls[0][0] == 'TestUser'
        assert 'commands' in callback_calls[0][1].lower()
    
    def test_command_parsing_edge_cases(self):
        """Test command parsing edge cases"""
        logger = logging.getLogger('test')
        command_registry = CommandRegistry(logger)
        
        # Test various command formats
        test_cases = [
            ('!help', True),
            ('!HELP', False),  # Case sensitive
            ('!!help', False),  # Double exclamation
            ('!help!', True),   # Should still detect help
            ('!help_test', False),  # Different command
            ('!help-test', False),  # Different command
            ('!help123', False),    # Different command
            ('!help ', True),       # Trailing space
            (' !help', True),       # Leading space
            ('!help\n', True),      # Newline
            ('!help\t', True),      # Tab
        ]
        
        for command_text, expected in test_cases:
            result = command_registry.is_command(command_text)
            assert result == expected, f"Failed for '{command_text}': expected {expected}, got {result}"