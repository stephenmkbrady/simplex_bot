"""
Tests for FileDownloadManager component
"""

import pytest
import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from file_download_manager import FileDownloadManager
from xftp_client import XFTPClient


class TestFileDownloadManager:
    """Test FileDownloadManager functionality"""
    
    def setup_method(self):
        """Setup test dependencies"""
        self.logger = logging.getLogger('test')
        self.temp_dir = Path(tempfile.mkdtemp())
        
        # Mock XFTP client
        self.xftp_client = MagicMock(spec=XFTPClient)
        
        # Media configuration
        self.media_config = {
            'download_enabled': True,
            'storage_path': str(self.temp_dir / 'media'),
            'max_file_size': '100MB',
            'allowed_types': ['image', 'video', 'document', 'audio']
        }
        
        # Create file download manager
        self.file_manager = FileDownloadManager(
            media_config=self.media_config,
            xftp_client=self.xftp_client,
            logger=self.logger
        )
    
    def test_file_manager_initialization(self):
        """Test FileDownloadManager initialization"""
        assert self.file_manager.media_config == self.media_config
        assert self.file_manager.xftp_client == self.xftp_client
        assert self.file_manager.logger == self.logger
        assert self.file_manager.media_enabled == True
        assert self.file_manager.media_path.exists()
        
        # Check media subdirectories are created
        for media_type in ['images', 'videos', 'documents', 'audio']:
            assert (self.file_manager.media_path / media_type).exists()
    
    def test_get_file_type(self):
        """Test file type detection"""
        assert self.file_manager._get_file_type('image.jpg') == 'image'
        assert self.file_manager._get_file_type('image.PNG') == 'image'
        assert self.file_manager._get_file_type('video.mp4') == 'video'
        assert self.file_manager._get_file_type('audio.mp3') == 'audio'
        assert self.file_manager._get_file_type('document.pdf') == 'document'
        assert self.file_manager._get_file_type('unknown.xyz') == 'document'
    
    def test_sanitize_filename(self):
        """Test filename sanitization"""
        # Test normal filename
        assert self.file_manager._sanitize_filename('normal_file.txt') == 'normal_file.txt'
        
        # Test dangerous characters
        assert self.file_manager._sanitize_filename('../../../etc/passwd') == '______etc_passwd'
        assert self.file_manager._sanitize_filename('file<>:|?"*.txt') == 'file_______.txt'
        
        # Test empty filename
        assert self.file_manager._sanitize_filename('') == 'unknown_file'
        assert self.file_manager._sanitize_filename('   ') == 'unknown_file'
        
        # Test very long filename
        long_name = 'a' * 300 + '.txt'
        result = self.file_manager._sanitize_filename(long_name)
        assert len(result) <= 255
        assert result.endswith('.txt')
    
    def test_generate_safe_filename(self):
        """Test safe filename generation"""
        filename = self.file_manager.generate_safe_filename(
            'test.pdf', 'TestUser', 'document'
        )
        
        assert 'test.pdf' in filename
        assert 'TestUser' in filename
        assert filename.endswith('.pdf')
        assert len(filename) <= 200
    
    def test_validate_file_for_download(self):
        """Test file validation for download"""
        # Valid file
        assert self.file_manager.validate_file_for_download(
            'test.jpg', 1024, 'image'
        ) == True
        
        # File too large (assuming max is 100MB)
        large_size = 200 * 1024 * 1024  # 200MB
        assert self.file_manager.validate_file_for_download(
            'large.jpg', large_size, 'image'
        ) == False
        
        # Invalid file type
        assert self.file_manager.validate_file_for_download(
            'test.exe', 1024, 'executable'
        ) == False
        
        # Invalid inputs should raise exception
        with pytest.raises(Exception):
            self.file_manager.validate_file_for_download('', 1024, 'image')
        
        with pytest.raises(Exception):
            self.file_manager.validate_file_for_download('test.jpg', -1, 'image')
        
        with pytest.raises(Exception):
            self.file_manager.validate_file_for_download('test.jpg', 1024, '')
    
    def test_extract_file_info_from_content(self):
        """Test file information extraction"""
        # Test SimpleX image format
        image_content = {
            'image': 'data:image/jpg;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=='
        }
        filename, size, file_type = self.file_manager.extract_file_info_from_content(
            image_content, 'image', 'TestUser'
        )
        assert file_type == 'image'
        assert filename.endswith('.jpg')
        assert size > 0
        
        # Test traditional file format
        file_content = {
            'fileName': 'document.pdf',
            'fileSize': 2048
        }
        filename, size, file_type = self.file_manager.extract_file_info_from_content(
            file_content, 'file', 'TestUser'
        )
        assert filename == 'document.pdf'
        assert size == 2048
        assert file_type == 'document'
    
    def test_calculate_data_url_size(self):
        """Test data URL size calculation"""
        # Test valid data URL
        data_url = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=='
        size = self.file_manager._calculate_data_url_size(data_url)
        assert size > 0
        
        # Test invalid data URL
        assert self.file_manager._calculate_data_url_size('not a data url') == 0
        assert self.file_manager._calculate_data_url_size('') == 0
    
    def test_generate_image_filename(self):
        """Test image filename generation"""
        # Test with valid data URL
        data_url = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=='
        filename = self.file_manager._generate_image_filename('TestUser', data_url)
        
        assert filename.endswith('.png')
        assert 'TestUser' in filename
        assert 'image' in filename
        
        # Test with invalid data URL
        filename = self.file_manager._generate_image_filename('TestUser', 'invalid')
        assert filename.endswith('.jpg')  # Default extension
    
    def test_clean_content_for_logging(self):
        """Test content cleaning for logging"""
        # Test with base64 image data
        content = {
            'msgContent': {
                'image': 'data:image/png;base64,' + 'A' * 1000  # Long base64 data
            }
        }
        
        cleaned = self.file_manager.clean_content_for_logging(content)
        
        # Should truncate base64 data
        assert len(cleaned['msgContent']['image']) < len(content['msgContent']['image'])
        assert 'base64_truncated' in cleaned['msgContent']['image']
        
        # Test with non-image content
        content = {'msgContent': {'text': 'Hello world'}}
        cleaned = self.file_manager.clean_content_for_logging(content)
        assert cleaned == content  # Should be unchanged
    
    def test_get_media_statistics(self):
        """Test media statistics calculation"""
        # Create some test files
        images_dir = self.file_manager.media_path / 'images'
        test_file1 = images_dir / 'test1.jpg'
        test_file2 = images_dir / 'test2.png'
        
        test_file1.write_text('fake image data 1')
        test_file2.write_text('fake image data 2')
        
        stats = self.file_manager.get_media_statistics()
        
        assert stats['total_files'] >= 2
        assert stats['images'] >= 2
        assert stats['total_size_mb'] > 0
        assert 'videos' in stats
        assert 'documents' in stats
        assert 'audio' in stats


class TestFileDownloadManagerDisabled:
    """Test FileDownloadManager with downloads disabled"""
    
    def test_disabled_file_manager(self):
        """Test FileDownloadManager when downloads are disabled"""
        logger = logging.getLogger('test')
        temp_dir = Path(tempfile.mkdtemp())
        xftp_client = MagicMock(spec=XFTPClient)
        
        media_config = {
            'download_enabled': False,
            'storage_path': str(temp_dir / 'media'),
            'max_file_size': '100MB',
            'allowed_types': ['image']
        }
        
        file_manager = FileDownloadManager(
            media_config=media_config,
            xftp_client=xftp_client,
            logger=logger
        )
        
        assert file_manager.media_enabled == False
        # Media directories should still be created
        assert file_manager.media_path.exists()