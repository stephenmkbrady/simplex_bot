"""
Tests for WebSocketManager component
"""

import pytest
import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from websocket_manager import WebSocketManager, WebSocketError


class TestWebSocketManager:
    """Test WebSocketManager functionality"""
    
    def setup_method(self):
        """Setup test dependencies"""
        self.logger = logging.getLogger('test')
        self.websocket_url = 'ws://localhost:3030'
        
        # Create WebSocket manager
        self.ws_manager = WebSocketManager(
            websocket_url=self.websocket_url,
            logger=self.logger
        )
    
    def test_websocket_manager_initialization(self):
        """Test WebSocketManager initialization"""
        assert self.ws_manager.websocket_url == self.websocket_url
        assert self.ws_manager.logger == self.logger
        assert self.ws_manager.websocket is None
        assert self.ws_manager.running == False
        assert self.ws_manager.correlation_counter == 0
        assert len(self.ws_manager.pending_requests) == 0
        assert len(self.ws_manager.message_handlers) == 0
    
    def test_register_message_handler(self):
        """Test message handler registration"""
        async def test_handler(data):
            pass
        
        self.ws_manager.register_message_handler('test_type', test_handler)
        
        assert 'test_type' in self.ws_manager.message_handlers
        assert self.ws_manager.message_handlers['test_type'] == test_handler
    
    def test_generate_correlation_id(self):
        """Test correlation ID generation"""
        corr_id1 = self.ws_manager.generate_correlation_id()
        corr_id2 = self.ws_manager.generate_correlation_id()
        
        assert corr_id1 != corr_id2
        assert corr_id1.startswith('bot_req_')
        assert corr_id2.startswith('bot_req_')
        assert self.ws_manager.correlation_counter == 2
    
    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful WebSocket connection"""
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_websocket = AsyncMock()
            mock_connect.return_value = mock_websocket
            
            result = await self.ws_manager.connect(max_retries=1, retry_delay=0.1)
            
            assert result == True
            assert self.ws_manager.websocket == mock_websocket
            mock_connect.assert_called_once_with(self.websocket_url)
    
    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Test WebSocket connection failure"""
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            
            result = await self.ws_manager.connect(max_retries=2, retry_delay=0.1)
            
            assert result == False
            assert self.ws_manager.websocket is None
            assert mock_connect.call_count == 2
    
    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test WebSocket disconnection"""
        mock_websocket = AsyncMock()
        self.ws_manager.websocket = mock_websocket
        
        await self.ws_manager.disconnect()
        
        mock_websocket.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_command_basic(self):
        """Test basic command sending"""
        mock_websocket = AsyncMock()
        self.ws_manager.websocket = mock_websocket
        
        await self.ws_manager.send_command("test command")
        
        # Verify send was called
        mock_websocket.send.assert_called_once()
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        
        assert sent_data['cmd'] == "test command"
        assert 'corrId' in sent_data
    
    @pytest.mark.asyncio
    async def test_send_command_no_connection(self):
        """Test command sending without connection"""
        self.ws_manager.websocket = None
        
        result = await self.ws_manager.send_command("test command")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test message sending"""
        mock_websocket = AsyncMock()
        self.ws_manager.websocket = mock_websocket
        
        await self.ws_manager.send_message("TestUser", "Hello world")
        
        # Verify send was called with correct format
        mock_websocket.send.assert_called_once()
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        
        assert sent_data['cmd'] == "@TestUser Hello world"
    
    @pytest.mark.asyncio
    async def test_send_message_truncation(self):
        """Test message truncation for long messages"""
        mock_websocket = AsyncMock()
        self.ws_manager.websocket = mock_websocket
        
        long_message = "A" * 5000  # Longer than MAX_MESSAGE_LENGTH
        await self.ws_manager.send_message("TestUser", long_message)
        
        # Verify message was truncated
        mock_websocket.send.assert_called_once()
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        
        assert len(sent_data['cmd']) < len(f"@TestUser {long_message}")
        assert sent_data['cmd'].endswith("...")
    
    @pytest.mark.asyncio
    async def test_accept_contact_request(self):
        """Test accepting contact requests"""
        mock_websocket = AsyncMock()
        self.ws_manager.websocket = mock_websocket
        
        await self.ws_manager.accept_contact_request(123)
        
        # Verify correct command was sent
        mock_websocket.send.assert_called_once()
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        
        assert sent_data['cmd'] == "/ac 123"
    
    @pytest.mark.asyncio
    async def test_connect_to_address(self):
        """Test connecting to SimpleX address"""
        mock_websocket = AsyncMock()
        self.ws_manager.websocket = mock_websocket
        
        address = "simplex://invitation-link"
        result = await self.ws_manager.connect_to_address(address)
        
        # Verify correct command was sent
        mock_websocket.send.assert_called_once()
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        
        assert sent_data['cmd'] == f"/c {address}"
    
    def test_contains_base64_file_data(self):
        """Test base64 file data detection"""
        # Test with image data
        data_with_image = {
            'resp': {
                'Right': {
                    'type': 'newChatItem',
                    'chatItem': {
                        'content': {
                            'msgContent': {
                                'type': 'image',
                                'image': 'data:image/png;base64,iVBORw0KGgo...'
                            }
                        }
                    }
                }
            }
        }
        
        assert self.ws_manager._contains_base64_file_data(data_with_image) == True
        
        # Test with regular text
        data_with_text = {
            'resp': {
                'Right': {
                    'type': 'newChatItem',
                    'chatItem': {
                        'content': {
                            'msgContent': {
                                'type': 'text',
                                'text': 'Hello world'
                            }
                        }
                    }
                }
            }
        }
        
        assert self.ws_manager._contains_base64_file_data(data_with_text) == False
        
        # Test with file data
        data_with_file = {
            'resp': {
                'Right': {
                    'type': 'newChatItem',
                    'chatItem': {
                        'content': {
                            'msgContent': {
                                'type': 'file',
                                'fileData': 'base64encodeddata...'
                            }
                        }
                    }
                }
            }
        }
        
        assert self.ws_manager._contains_base64_file_data(data_with_file) == True
    
    def test_log_websocket_message_safely(self):
        """Test safe WebSocket message logging"""
        # Test with large file data (should be filtered)
        large_file_message = json.dumps({
            'resp': {
                'Right': {
                    'type': 'newChatItem',
                    'chatItem': {
                        'content': {
                            'msgContent': {
                                'type': 'image',
                                'image': 'data:image/png;base64,' + 'A' * 1000
                            }
                        }
                    }
                }
            }
        })
        
        # Should not raise exception
        data = json.loads(large_file_message)
        self.ws_manager._log_websocket_message_safely(large_file_message, data)
        
        # Test with regular message
        regular_message = json.dumps({
            'resp': {
                'Right': {
                    'type': 'newChatItem',
                    'chatItem': {
                        'content': {
                            'msgContent': {
                                'type': 'text',
                                'text': 'Hello world'
                            }
                        }
                    }
                }
            }
        })
        
        # Should not raise exception
        data = json.loads(regular_message)
        self.ws_manager._log_websocket_message_safely(regular_message, data)
    
    @pytest.mark.asyncio
    async def test_handle_response_success(self):
        """Test handling successful responses"""
        # Mock handler
        test_handler = AsyncMock()
        self.ws_manager.register_message_handler('testType', test_handler)
        
        response_data = {
            'corrId': 'test_corr_id',
            'resp': {
                'Right': {
                    'type': 'testType',
                    'data': 'test_data'
                }
            }
        }
        
        await self.ws_manager._handle_response(response_data)
        
        # Verify handler was called
        test_handler.assert_called_once_with({'type': 'testType', 'data': 'test_data'})
    
    @pytest.mark.asyncio
    async def test_handle_response_error(self):
        """Test handling error responses"""
        response_data = {
            'corrId': 'test_corr_id',
            'resp': {
                'Left': {
                    'error': 'Something went wrong'
                }
            }
        }
        
        # Should not raise exception
        await self.ws_manager._handle_response(response_data)
    
    @pytest.mark.asyncio
    async def test_handle_response_correlation(self):
        """Test handling responses with correlation IDs"""
        corr_id = 'test_corr_id'
        self.ws_manager.pending_requests[corr_id] = {'command': 'test', 'timestamp': 123456}
        
        response_data = {
            'corrId': corr_id,
            'resp': {
                'Right': {
                    'type': 'response',
                    'data': 'test_response'
                }
            }
        }
        
        await self.ws_manager._handle_response(response_data)
        
        # Verify correlation ID was handled
        assert corr_id not in self.ws_manager.pending_requests
        assert f"{corr_id}_response" in self.ws_manager.pending_requests


class TestWebSocketManagerErrors:
    """Test WebSocketManager error handling"""
    
    @pytest.mark.asyncio
    async def test_send_command_websocket_error(self):
        """Test command sending with WebSocket errors"""
        logger = logging.getLogger('test')
        ws_manager = WebSocketManager('ws://localhost:3030', logger)
        
        mock_websocket = AsyncMock()
        mock_websocket.send.side_effect = Exception("WebSocket error")
        ws_manager.websocket = mock_websocket
        
        result = await ws_manager.send_command("test command")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_handle_response_exception(self):
        """Test response handling with exceptions"""
        logger = logging.getLogger('test')
        ws_manager = WebSocketManager('ws://localhost:3030', logger)
        
        # Invalid response data should not crash
        invalid_response = {'invalid': 'structure'}
        
        # Should not raise exception
        await ws_manager._handle_response(invalid_response)