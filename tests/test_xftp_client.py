#!/usr/bin/env python3
"""
Test suite for XFTP Client functionality
"""

import pytest
import asyncio
import tempfile
import os
import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from xftp_client import (
    XFTPClient, XFTPError, XFTPDownloadError, XFTPIntegrityError, 
    XFTPTimeoutError, SecurityValidator, XFTPCLIInterface, CLIResult
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_logger():
    """Create a mock logger for tests"""
    return Mock(spec=logging.Logger)


@pytest.fixture
def xftp_config():
    """Default XFTP configuration for tests"""
    return {
        'cli_path': '/usr/local/bin/xftp',
        'temp_dir': './temp/xftp',
        'timeout': 300,
        'max_file_size': 1024 * 1024 * 1024,  # 1GB
        'retry_attempts': 3,
        'cleanup_on_failure': True
    }


@pytest.fixture
def xftp_client(temp_dir, mock_logger, xftp_config):
    """Create an XFTP client for tests"""
    xftp_config['temp_dir'] = temp_dir
    return XFTPClient(
        cli_path='/usr/local/bin/xftp',
        temp_dir=temp_dir,
        config=xftp_config,
        logger=mock_logger
    )


class TestSecurityValidator:
    """Test security validation functions"""
    
    def test_validate_file_path_valid(self, temp_dir):
        """Test file path validation with valid paths"""
        allowed_dirs = [temp_dir]
        test_path = os.path.join(temp_dir, 'test_file.txt')
        
        assert SecurityValidator.validate_file_path(test_path, allowed_dirs) is True
    
    def test_validate_file_path_traversal_attack(self, temp_dir):
        """Test file path validation blocks directory traversal"""
        allowed_dirs = [temp_dir]
        malicious_path = os.path.join(temp_dir, '../../../etc/passwd')
        
        assert SecurityValidator.validate_file_path(malicious_path, allowed_dirs) is False
    
    def test_validate_file_size_valid(self):
        """Test file size validation with valid sizes"""
        assert SecurityValidator.validate_file_size(1024) is True
        assert SecurityValidator.validate_file_size(1024 * 1024) is True
        assert SecurityValidator.validate_file_size(1024 * 1024 * 1024) is True
    
    def test_validate_file_size_invalid(self):
        """Test file size validation with invalid sizes"""
        assert SecurityValidator.validate_file_size(0) is False
        assert SecurityValidator.validate_file_size(-1) is False
        assert SecurityValidator.validate_file_size(2 * 1024 * 1024 * 1024) is False  # 2GB
    
    def test_validate_file_description_valid(self):
        """Test file description validation with valid descriptions"""
        valid_desc = '{"version": "1.0", "fileId": "test123", "fileHash": "abc123"}'
        assert SecurityValidator.validate_file_description(valid_desc) is True
    
    def test_validate_file_description_invalid(self):
        """Test file description validation with invalid descriptions"""
        assert SecurityValidator.validate_file_description("") is False
        assert SecurityValidator.validate_file_description("   ") is False
        assert SecurityValidator.validate_file_description("short") is False
        
        # Test malicious paths
        malicious_desc = 'some content with ../../../etc/passwd'
        assert SecurityValidator.validate_file_description(malicious_desc) is False
    
    def test_secure_cleanup(self, temp_dir):
        """Test secure file cleanup"""
        test_file = os.path.join(temp_dir, 'test_cleanup.txt')
        
        # Create test file
        with open(test_file, 'w') as f:
            f.write('sensitive data')
        
        assert os.path.exists(test_file)
        
        # Test cleanup
        SecurityValidator.secure_cleanup(test_file)
        assert not os.path.exists(test_file)


class TestXFTPCLIInterface:
    """Test XFTP CLI interface"""
    
    def test_parse_cli_output_success(self):
        """Test parsing successful CLI output"""
        cli = XFTPCLIInterface('/usr/local/bin/xftp')
        
        output = "receiving file test.txt\nreceived file: /tmp/test.txt"
        result = cli.parse_cli_output(output)
        
        assert result['status'] == 'completed'
        assert result['file_path'] == '/tmp/test.txt'
    
    def test_parse_cli_output_progress(self):
        """Test parsing CLI output with progress"""
        cli = XFTPCLIInterface('/usr/local/bin/xftp')
        
        output = "receiving file test.txt\nProgress: 45%\ndownloading chunks..."
        result = cli.parse_cli_output(output)
        
        assert result['status'] == 'downloading'
        assert result['progress'] == 45
    
    def test_parse_cli_output_error(self):
        """Test parsing CLI output with errors"""
        cli = XFTPCLIInterface('/usr/local/bin/xftp')
        
        output = "receiving file test.txt\nError: Failed to connect to relay"
        result = cli.parse_cli_output(output)
        
        assert result['status'] == 'error'
        assert 'Failed to connect' in result['error']
    
    @pytest.mark.asyncio
    async def test_execute_recv_timeout(self, temp_dir):
        """Test CLI execution with timeout"""
        cli = XFTPCLIInterface('/nonexistent/xftp', timeout=1)
        
        xftp_file = os.path.join(temp_dir, 'test.xftp')
        with open(xftp_file, 'w') as f:
            f.write('{"test": "data"}')
        
        # The CLI doesn't exist, so it should return a failed result, not timeout
        result = await cli.execute_recv(xftp_file, temp_dir)
        assert result.success is False
        assert result.return_code == -1


class TestXFTPClient:
    """Test XFTP client functionality"""
    
    def test_initialization(self, xftp_client, temp_dir):
        """Test XFTP client initialization"""
        assert xftp_client.temp_dir == Path(temp_dir)
        assert xftp_client.max_file_size == 1024 * 1024 * 1024
        assert xftp_client.retry_attempts == 3
    
    def test_create_xftp_description(self, xftp_client):
        """Test file description creation"""
        file_id = "test_file_123"
        file_hash = "abc123def456"
        file_size = 1024
        
        description = xftp_client._create_xftp_description(file_id, file_hash, file_size)
        
        # Should be valid JSON
        parsed = json.loads(description)
        assert parsed['fileId'] == file_id
        assert parsed['fileHash'] == file_hash
        assert parsed['fileSize'] == file_size
    
    def test_verify_file_integrity_success(self, xftp_client, temp_dir):
        """Test successful file integrity verification"""
        test_file = os.path.join(temp_dir, 'test_file.txt')
        test_content = b'Hello, World!'
        
        # Create test file
        with open(test_file, 'wb') as f:
            f.write(test_content)
        
        # Calculate expected hash
        import hashlib
        expected_hash = hashlib.sha512(test_content).hexdigest()
        
        # Test verification
        assert xftp_client.verify_file_integrity(test_file, expected_hash) is True
    
    def test_verify_file_integrity_failure(self, xftp_client, temp_dir):
        """Test failed file integrity verification"""
        test_file = os.path.join(temp_dir, 'test_file.txt')
        
        # Create test file
        with open(test_file, 'wb') as f:
            f.write(b'Hello, World!')
        
        # Use wrong hash
        wrong_hash = 'wrong_hash_value'
        
        # Test verification failure
        assert xftp_client.verify_file_integrity(test_file, wrong_hash) is False
    
    def test_verify_file_integrity_missing_file(self, xftp_client):
        """Test file integrity verification with missing file"""
        nonexistent_file = '/nonexistent/file.txt'
        some_hash = 'abc123'
        
        assert xftp_client.verify_file_integrity(nonexistent_file, some_hash) is False
    
    def test_find_downloaded_file(self, xftp_client, temp_dir):
        """Test finding downloaded file in directory"""
        temp_path = Path(temp_dir)
        
        # Create some files
        (temp_path / 'test.xftp').write_text('xftp description')
        (temp_path / 'downloaded_file.txt').write_text('actual file content')
        
        found_file = xftp_client._find_downloaded_file(temp_path, 'downloaded_file.txt')
        
        assert found_file is not None
        assert found_file.name == 'downloaded_file.txt'
    
    def test_find_downloaded_file_only_xftp(self, xftp_client, temp_dir):
        """Test finding downloaded file when only .xftp files exist"""
        temp_path = Path(temp_dir)
        
        # Create only .xftp file
        (temp_path / 'test.xftp').write_text('xftp description')
        
        found_file = xftp_client._find_downloaded_file(temp_path, 'test_file.txt')
        
        assert found_file is None
    
    def test_is_available_missing_cli(self, xftp_client):
        """Test availability check with missing CLI"""
        xftp_client.cli_path = '/nonexistent/xftp'
        assert xftp_client.is_available() is False
    
    @pytest.mark.asyncio
    async def test_cleanup_temp_files(self, xftp_client, temp_dir):
        """Test temporary file cleanup"""
        # Create session directory with files
        session_id = 'test_session_123'
        session_dir = Path(temp_dir) / session_id
        session_dir.mkdir()
        
        test_file = session_dir / 'test_file.txt'
        test_file.write_text('test content')
        
        assert session_dir.exists()
        assert test_file.exists()
        
        # Test cleanup
        await xftp_client.cleanup_temp_files(session_id)
        
        assert not session_dir.exists()
    
    @pytest.mark.asyncio
    async def test_download_file_invalid_size(self, xftp_client):
        """Test download with invalid file size"""
        result = await xftp_client.download_file(
            file_id='test123',
            file_hash='abc123',
            file_size=2 * 1024 * 1024 * 1024,  # 2GB - too large
            file_name='large_file.txt',
            output_path='/tmp/output.txt'
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_download_file_missing_xftp_cli(self, xftp_client):
        """Test download when XFTP CLI is not available"""
        xftp_client.cli_path = '/nonexistent/xftp'
        
        result = await xftp_client.download_file(
            file_id='test123',
            file_hash='abc123',
            file_size=1024,
            file_name='test_file.txt',
            output_path='/tmp/output.txt'
        )
        
        assert result is False


class TestXFTPIntegration:
    """Integration tests for XFTP functionality"""
    
    @pytest.mark.asyncio
    async def test_download_workflow_mock_success(self, xftp_client, temp_dir):
        """Test complete download workflow with mocked CLI success"""
        output_path = os.path.join(temp_dir, 'downloaded_file.txt')
        
        # Mock the CLI interface to simulate successful download
        with patch.object(xftp_client.cli, 'execute_recv') as mock_exec:
            # Mock successful CLI execution
            mock_exec.return_value = CLIResult(
                success=True,
                output='received file: downloaded_file.txt',
                error='',
                return_code=0,
                execution_time=5.0
            )
            
            # Mock finding the downloaded file
            with patch.object(xftp_client, '_find_downloaded_file') as mock_find:
                # Create a mock file path
                mock_file_path = Path(temp_dir) / 'downloaded_file.txt'
                mock_file_path.write_text('mock file content')
                mock_find.return_value = mock_file_path
                
                # Mock file integrity verification
                with patch.object(xftp_client, 'verify_file_integrity', return_value=True):
                    result = await xftp_client.download_file(
                        file_id='test123',
                        file_hash='abc123def456',
                        file_size=1024,
                        file_name='downloaded_file.txt',
                        output_path=output_path
                    )
                    
                    assert result is True
    
    @pytest.mark.asyncio
    async def test_download_workflow_cli_failure(self, xftp_client, temp_dir):
        """Test download workflow with CLI failure"""
        output_path = os.path.join(temp_dir, 'failed_file.txt')
        
        # Mock the CLI interface to simulate failure
        with patch.object(xftp_client.cli, 'execute_recv') as mock_exec:
            mock_exec.return_value = CLIResult(
                success=False,
                output='',
                error='Failed to connect to relay',
                return_code=1,
                execution_time=1.0
            )
            
            result = await xftp_client.download_file(
                file_id='test123',
                file_hash='abc123def456',
                file_size=1024,
                file_name='failed_file.txt',
                output_path=output_path
            )
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_download_workflow_integrity_failure(self, xftp_client, temp_dir):
        """Test download workflow with integrity verification failure"""
        output_path = os.path.join(temp_dir, 'corrupt_file.txt')
        
        # Mock successful CLI but failed integrity check
        with patch.object(xftp_client.cli, 'execute_recv') as mock_exec:
            mock_exec.return_value = CLIResult(
                success=True,
                output='received file: corrupt_file.txt',
                error='',
                return_code=0,
                execution_time=3.0
            )
            
            # Mock file creation
            def create_corrupt_file(*args, **kwargs):
                session_files = list(Path(xftp_client.temp_dir).glob('*/corrupt_file.txt'))
                if session_files:
                    session_files[0].write_text('corrupted content')
                return mock_exec.return_value
            
            mock_exec.side_effect = create_corrupt_file
            
            # Mock integrity verification failure
            with patch.object(xftp_client, 'verify_file_integrity', return_value=False):
                result = await xftp_client.download_file(
                    file_id='test123',
                    file_hash='abc123def456',
                    file_size=1024,
                    file_name='corrupt_file.txt',
                    output_path=output_path
                )
                
                assert result is False


if __name__ == "__main__":
    pytest.main([__file__])