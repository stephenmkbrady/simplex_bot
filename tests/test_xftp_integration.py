#!/usr/bin/env python3
"""
Integration tests for XFTP functionality in the SimpleX Bot
"""

import pytest
import asyncio
import tempfile
import os
import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

# Import bot class and related components
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import SimplexChatBot
from xftp_client import XFTPClient, XFTPError


@pytest.fixture
def temp_config_dir():
    """Create temporary directory for test configuration"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def test_config(temp_config_dir):
    """Create test configuration file"""
    config_path = os.path.join(temp_config_dir, 'test_config.yml')
    
    config_content = f"""
servers:
  smp:
    - "smp://test-server.example.com"
  xftp:
    - "xftp://test-xftp.example.com"

bot:
  name: "Test Bot"
  websocket_url: "ws://localhost:3030"
  auto_accept_contacts: true

logging:
  daily_rotation: false
  message_log_separate: false
  retention_days: 30
  log_level: "INFO"

media:
  download_enabled: true
  max_file_size: "100MB"
  allowed_types: 
    - "image"
    - "video"
    - "document"
    - "audio"
  storage_path: "{temp_config_dir}/media"

commands:
  enabled:
    - "help"
    - "echo"
    - "status"
  prefix: "!"

security:
  max_message_length: 4096
  rate_limit_messages: 10
  rate_limit_window: 60

xftp:
  cli_path: "/usr/local/bin/xftp"
  temp_dir: "{temp_config_dir}/temp/xftp"
  timeout: 300
  max_file_size: 1073741824
  retry_attempts: 3
  cleanup_on_failure: true
"""
    
    with open(config_path, 'w') as f:
        f.write(config_content)
    
    return config_path


@pytest.fixture
def mock_bot(test_config):
    """Create a mock bot instance for testing"""
    with patch('bot.websockets.connect'), \
         patch('bot.SimplexChatBot.connect', return_value=True):
        
        bot = SimplexChatBot(config_path=test_config)
        
        # Mock the loggers if they don't exist
        if not hasattr(bot, 'app_logger'):
            bot.app_logger = Mock()
        if not hasattr(bot, 'message_logger'):
            bot.message_logger = Mock()
            
        return bot


class TestXFTPBotIntegration:
    """Test XFTP integration with the SimpleX Bot"""
    
    def test_bot_xftp_initialization(self, mock_bot):
        """Test that bot initializes XFTP client correctly"""
        # Check XFTP client was created
        assert hasattr(mock_bot, 'xftp_client')
        assert hasattr(mock_bot, 'xftp_available')
        
        # Check configuration was loaded
        assert 'xftp' in mock_bot.config
        assert mock_bot.config['xftp']['timeout'] == 300
    
    def test_bot_xftp_missing_cli(self, test_config):
        """Test bot behavior when XFTP CLI is missing"""
        with patch('bot.websockets.connect'), \
             patch('bot.SimplexChatBot.connect', return_value=True), \
             patch('xftp_client.XFTPClient.is_available', return_value=False):
            
            bot = SimplexChatBot(config_path=test_config)
            
            # Mock the loggers if they don't exist
            if not hasattr(bot, 'app_logger'):
                bot.app_logger = Mock()
            if not hasattr(bot, 'message_logger'):
                bot.message_logger = Mock()
                
            assert bot.xftp_available is False
    
    @pytest.mark.asyncio
    async def test_download_via_xftp_success(self, mock_bot, temp_config_dir):
        """Test successful XFTP download through bot"""
        # Create test file info
        file_info = {
            'fileId': 'test_file_123',
            'fileHash': 'abc123def456',
            'fileSize': 1024,
            'fileName': 'test_file.txt'
        }
        
        # Create output path
        output_path = Path(temp_config_dir) / 'downloads' / 'test_file.txt'
        output_path.parent.mkdir(exist_ok=True)
        
        # Mock XFTP client success
        with patch.object(mock_bot.xftp_client, 'download_file', return_value=True):
            mock_bot.xftp_available = True
            
            result = await mock_bot._download_via_xftp(
                file_info=file_info,
                file_path=output_path,
                original_name='test_file.txt'
            )
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_download_via_xftp_missing_file_id(self, mock_bot, temp_config_dir):
        """Test XFTP download with missing file ID"""
        file_info = {
            'fileHash': 'abc123def456',
            'fileSize': 1024,
            'fileName': 'test_file.txt'
        }
        
        output_path = Path(temp_config_dir) / 'downloads' / 'test_file.txt'
        
        mock_bot.xftp_available = True
        
        result = await mock_bot._download_via_xftp(
            file_info=file_info,
            file_path=output_path,
            original_name='test_file.txt'
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_download_via_xftp_client_unavailable(self, mock_bot, temp_config_dir):
        """Test XFTP download when client is unavailable"""
        file_info = {
            'fileId': 'test_file_123',
            'fileHash': 'abc123def456',
            'fileSize': 1024,
            'fileName': 'test_file.txt'
        }
        
        output_path = Path(temp_config_dir) / 'downloads' / 'test_file.txt'
        
        # Set XFTP as unavailable
        mock_bot.xftp_available = False
        
        result = await mock_bot._download_via_xftp(
            file_info=file_info,
            file_path=output_path,
            original_name='test_file.txt'
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_download_via_xftp_error_handling(self, mock_bot, temp_config_dir):
        """Test XFTP download error handling"""
        file_info = {
            'fileId': 'test_file_123',
            'fileHash': 'abc123def456',
            'fileSize': 1024,
            'fileName': 'test_file.txt'
        }
        
        output_path = Path(temp_config_dir) / 'downloads' / 'test_file.txt'
        
        # Mock XFTP client to raise exception
        with patch.object(mock_bot.xftp_client, 'download_file', side_effect=XFTPError("Test error")):
            mock_bot.xftp_available = True
            
            result = await mock_bot._download_via_xftp(
                file_info=file_info,
                file_path=output_path,
                original_name='test_file.txt'
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_smp_fallback_download(self, mock_bot, temp_config_dir):
        """Test SMP fallback download functionality"""
        file_info = {
            'fileId': 'test_file_123',
            'fileHash': 'abc123def456',
            'fileSize': 1024,
            'fileName': 'test_file.txt'
        }
        
        output_path = Path(temp_config_dir) / 'downloads' / 'test_file.txt'
        
        # Mock send_command to simulate successful SMP response
        with patch.object(mock_bot, 'send_command', return_value="file received successfully"):
            result = await mock_bot._download_via_smp_fallback(
                file_info=file_info,
                file_path=output_path,
                original_name='test_file.txt'
            )
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_smp_fallback_timeout(self, mock_bot, temp_config_dir):
        """Test SMP fallback with timeout"""
        file_info = {
            'fileId': 'test_file_123',
            'fileHash': 'abc123def456',
            'fileSize': 1024,
            'fileName': 'test_file.txt'
        }
        
        output_path = Path(temp_config_dir) / 'downloads' / 'test_file.txt'
        
        # Mock send_command to simulate timeout
        with patch.object(mock_bot, 'send_command', side_effect=asyncio.TimeoutError):
            result = await mock_bot._download_via_smp_fallback(
                file_info=file_info,
                file_path=output_path,
                original_name='test_file.txt'
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_complete_download_workflow_with_fallback(self, mock_bot, temp_config_dir):
        """Test complete download workflow with XFTP failure and SMP fallback"""
        # Mock message with file information
        file_info = {
            'fileId': 'test_file_123',
            'fileHash': 'abc123def456',
            'fileSize': 1024,
            'fileName': 'test_file.txt'
        }
        
        # Mock XFTP failure and SMP success
        with patch.object(mock_bot.xftp_client, 'download_file', return_value=False), \
             patch.object(mock_bot, 'send_command', return_value="file received successfully"), \
             patch.object(mock_bot, '_generate_safe_filename', return_value='test_file.txt'):
            
            mock_bot.xftp_available = True
            
            result = await mock_bot._download_file(
                contact_name='test_contact',
                file_info=file_info,
                file_type='document'
            )
            
            # Should succeed via SMP fallback
            assert result is True
    
    def test_xftp_configuration_loading(self, mock_bot):
        """Test that XFTP configuration is properly loaded"""
        xftp_config = mock_bot.config.get('xftp', {})
        
        assert xftp_config['cli_path'] == '/usr/local/bin/xftp'
        assert xftp_config['timeout'] == 300
        assert xftp_config['max_file_size'] == 1073741824
        assert xftp_config['retry_attempts'] == 3
        assert xftp_config['cleanup_on_failure'] is True
    
    def test_xftp_client_configuration_inheritance(self, mock_bot):
        """Test that XFTP client inherits configuration correctly"""
        if mock_bot.xftp_client:
            assert mock_bot.xftp_client.max_file_size == 1073741824
            assert mock_bot.xftp_client.retry_attempts == 3
            assert mock_bot.xftp_client.cleanup_on_failure is True


class TestXFTPErrorScenarios:
    """Test various error scenarios in XFTP integration"""
    
    @pytest.mark.asyncio
    async def test_file_too_large(self, mock_bot, temp_config_dir):
        """Test handling of files that are too large"""
        file_info = {
            'fileId': 'large_file_123',
            'fileHash': 'abc123def456',
            'fileSize': 2 * 1024 * 1024 * 1024,  # 2GB
            'fileName': 'large_file.txt'
        }
        
        output_path = Path(temp_config_dir) / 'downloads' / 'large_file.txt'
        
        mock_bot.xftp_available = True
        
        result = await mock_bot._download_via_xftp(
            file_info=file_info,
            file_path=output_path,
            original_name='large_file.txt'
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_missing_file_hash(self, mock_bot, temp_config_dir):
        """Test handling of files with missing hash"""
        file_info = {
            'fileId': 'test_file_123',
            'fileSize': 1024,
            'fileName': 'test_file.txt'
        }
        
        output_path = Path(temp_config_dir) / 'downloads' / 'test_file.txt'
        
        mock_bot.xftp_available = True
        
        result = await mock_bot._download_via_xftp(
            file_info=file_info,
            file_path=output_path,
            original_name='test_file.txt'
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_xftp_client_exception(self, mock_bot, temp_config_dir):
        """Test handling of unexpected XFTP client exceptions"""
        file_info = {
            'fileId': 'test_file_123',
            'fileHash': 'abc123def456',
            'fileSize': 1024,
            'fileName': 'test_file.txt'
        }
        
        output_path = Path(temp_config_dir) / 'downloads' / 'test_file.txt'
        
        # Mock XFTP client to raise unexpected exception
        with patch.object(mock_bot.xftp_client, 'download_file', side_effect=Exception("Unexpected error")):
            mock_bot.xftp_available = True
            
            result = await mock_bot._download_via_xftp(
                file_info=file_info,
                file_path=output_path,
                original_name='test_file.txt'
            )
            
            assert result is False


if __name__ == "__main__":
    pytest.main([__file__])