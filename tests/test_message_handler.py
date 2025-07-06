"""
Tests for MessageHandler component
"""

import pytest
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from message_handler import MessageHandler
from file_download_manager import FileDownloadManager
from bot import CommandRegistry


class TestMessageHandler:
    """Test MessageHandler functionality"""
    
    def setup_method(self):
        """Setup test dependencies"""
        self.logger = logging.getLogger('test')
        self.message_logger = logging.getLogger('test_messages')
        
        # Mock dependencies
        self.command_registry = CommandRegistry(self.logger)
        self.file_download_manager = MagicMock(spec=FileDownloadManager)
        self.send_message_callback = AsyncMock()
        
        # Create message handler
        self.message_handler = MessageHandler(
            command_registry=self.command_registry,
            file_download_manager=self.file_download_manager,
            send_message_callback=self.send_message_callback,
            logger=self.logger,
            message_logger=self.message_logger
        )
    
    @pytest.mark.asyncio
    async def test_process_text_message(self):
        """Test processing text messages"""
        message_data = {
            'chatItem': {
                'chatDir': {'contact': 'test_contact'},
                'meta': {'createdAt': '2025-01-01T00:00:00.000Z'},
                'content': {
                    'msgContent': {'type': 'text', 'text': 'Hello world'}
                }
            },
            'chatInfo': {
                'contact': {
                    'localDisplayName': 'TestUser'
                }
            }
        }
        
        await self.message_handler.process_message(message_data)
        
        # Should not call send_message for regular text
        self.send_message_callback.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_process_command_message(self):
        """Test processing command messages"""
        message_data = {
            'chatItem': {
                'chatDir': {'contact': 'test_contact'},
                'meta': {'createdAt': '2025-01-01T00:00:00.000Z'},
                'content': {
                    'msgContent': {'type': 'text', 'text': '!help'}
                }
            },
            'chatInfo': {
                'contact': {
                    'localDisplayName': 'TestUser'
                }
            }
        }
        
        await self.message_handler.process_message(message_data)
        
        # Should call send_message for help command
        self.send_message_callback.assert_called_once()
        call_args = self.send_message_callback.call_args
        assert call_args[0][0] == 'TestUser'  # Contact name
        assert 'commands' in call_args[0][1].lower()  # Response contains 'commands'
    
    @pytest.mark.asyncio
    async def test_process_file_message(self):
        """Test processing file messages"""
        message_data = {
            'chatItem': {
                'chatDir': {'contact': 'test_contact'},
                'meta': {'createdAt': '2025-01-01T00:00:00.000Z'},
                'content': {
                    'msgContent': {
                        'type': 'file',
                        'fileName': 'test.pdf',
                        'fileSize': 1024
                    }
                }
            },
            'chatInfo': {
                'contact': {
                    'localDisplayName': 'TestUser'
                }
            }
        }
        
        await self.message_handler.process_message(message_data)
        
        # Should not call send_message for file messages
        self.send_message_callback.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_process_malformed_message(self):
        """Test processing malformed messages"""
        malformed_messages = [
            {},  # Empty
            {'chatItem': {}},  # Missing content
            {'chatItem': {'content': {}}},  # Missing msgContent
            {'invalid': 'structure'},  # Wrong structure
        ]
        
        for message_data in malformed_messages:
            # Should not raise exceptions
            await self.message_handler.process_message(message_data)
            
        # Should not call send_message for malformed messages
        self.send_message_callback.assert_not_called()
    
    def test_message_handler_initialization(self):
        """Test MessageHandler initialization"""
        assert self.message_handler.command_registry == self.command_registry
        assert self.message_handler.file_download_manager == self.file_download_manager
        assert self.message_handler.send_message_callback == self.send_message_callback
        assert self.message_handler.logger == self.logger
        assert self.message_handler.message_logger == self.message_logger
        assert self.message_handler.MESSAGE_PREVIEW_LENGTH == 100


class TestMessageHandlerIntegration:
    """Test MessageHandler integration with other components"""
    
    @pytest.mark.asyncio
    async def test_command_execution_integration(self):
        """Test command execution through MessageHandler"""
        logger = logging.getLogger('test')
        message_logger = logging.getLogger('test_messages')
        
        # Create real command registry
        command_registry = CommandRegistry(logger)
        
        # Mock other dependencies
        file_download_manager = MagicMock(spec=FileDownloadManager)
        send_message_callback = AsyncMock()
        
        # Create message handler
        message_handler = MessageHandler(
            command_registry=command_registry,
            file_download_manager=file_download_manager,
            send_message_callback=send_message_callback,
            logger=logger,
            message_logger=message_logger
        )
        
        # Test each default command
        commands_to_test = ['!help', '!status', '!ping', '!stats']
        
        for command in commands_to_test:
            send_message_callback.reset_mock()
            
            message_data = {
                'chatItem': {
                    'chatDir': {'contact': 'test_contact'},
                    'meta': {'createdAt': '2025-01-01T00:00:00.000Z'},
                    'content': {
                        'msgContent': {'type': 'text', 'text': command}
                    }
                },
                'chatInfo': {
                    'contact': {
                        'localDisplayName': 'TestUser'
                    }
                }
            }
            
            await message_handler.process_message(message_data)
            
            # Should call send_message for each command
            send_message_callback.assert_called_once()
            call_args = send_message_callback.call_args
            assert call_args[0][0] == 'TestUser'  # Contact name
            assert isinstance(call_args[0][1], str)  # Response is string
            assert len(call_args[0][1]) > 0  # Response is not empty