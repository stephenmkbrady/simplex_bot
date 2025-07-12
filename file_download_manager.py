#!/usr/bin/env python3
"""
File Download Manager for SimpleX Bot
Handles all file and media download operations
"""

import asyncio
import copy
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from config_manager import parse_file_size
from xftp_client import XFTPClient


class FileDownloadManager:
    """Manages file downloads and media operations for SimpleX Bot"""
    
    def __init__(self, media_config: Dict[str, Any], xftp_client: XFTPClient, logger: logging.Logger):
        self.media_config = media_config
        self.xftp_client = xftp_client
        self.logger = logger
        
        # Setup media storage
        self.media_enabled = media_config.get('download_enabled', True)
        self.media_path = Path(media_config.get('storage_path', './media'))
        self.media_path.mkdir(exist_ok=True)
        
        # Create media subdirectories
        for media_type in ['images', 'videos', 'documents', 'audio']:
            (self.media_path / media_type).mkdir(exist_ok=True)
    
    def clean_content_for_logging(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Clean base64 data from content structure for safe logging"""
        content_for_log = copy.deepcopy(content)
        if 'msgContent' in content_for_log and 'image' in content_for_log['msgContent']:
            image_data = content_for_log['msgContent']['image']
            if isinstance(image_data, str) and image_data.startswith('data:image/'):
                # Truncate base64 data
                header_part = image_data.split(',')[0] if ',' in image_data else image_data
                content_for_log['msgContent']['image'] = f"{header_part},<base64_truncated>"
        return content_for_log
    
    def extract_file_info_from_content(self, file_info: Dict[str, Any], inner_msg_type: str, contact_name: str) -> Tuple[str, int, str]:
        """Extract file information from message content"""
        # Handle SimpleX image format vs traditional file format
        if inner_msg_type == "image" and "image" in file_info:
            # SimpleX image format: type: 'image', image: 'data:image/jpg;base64,[data]'
            image_data_url = file_info.get("image", "")
            file_name = self._generate_image_filename(contact_name, image_data_url)
            file_size = self._calculate_data_url_size(image_data_url)
            file_type = "image"
            
            self.logger.info(f"SimpleX image detected: {file_name} ({file_size} bytes)")
            return file_name, file_size, file_type
            
        elif inner_msg_type == "video" and "image" in file_info:
            return self._handle_video_file_info(file_info)
        else:
            # Traditional file format: fileName, fileSize, fileData
            file_name = file_info.get("fileName", "unknown_file")
            file_size = file_info.get("fileSize", 0)
            file_type = self._get_file_type(file_name)
            
            self.logger.info(f"Traditional file format: {file_name} ({file_size} bytes)")
            return file_name, file_size, file_type
    
    def _handle_video_file_info(self, file_info: Dict[str, Any]) -> Tuple[str, int, str]:
        """Handle video file information extraction"""
        # Check if this is actually an image file misclassified as video
        potential_filename = file_info.get("fileName", "")
        if potential_filename:
            actual_file_type = self._get_file_type(potential_filename)
            if actual_file_type == "image":
                # This is actually an image file, treat it as such
                self.logger.info(f"🖼️ Large image detected (misclassified as video): {potential_filename}")
                # Process as image file instead of video
                file_name = potential_filename
                file_size = file_info.get("fileSize", 0)
                file_type = "image"
                return file_name, file_size, file_type
            else:
                # This is a real video file
                return self._extract_video_info(file_info)
        else:
            # No filename available, assume it's a video
            return self._extract_video_info(file_info)
    
    def _extract_video_info(self, file_info: Dict[str, Any]) -> Tuple[str, int, str]:
        """Extract video file information"""
        thumbnail_data_url = file_info.get("image", "")
        duration = file_info.get("duration", 0)
        
        file_name = file_info.get("fileName", f"video_{int(time.time())}.mp4")
        file_size = file_info.get("fileSize", 0)
        file_type = "video"
        
        self.logger.info(f"🎬 XFTP_DEBUG: SimpleX video detected - name: {file_name}, size: {file_size}, duration: {duration}s")
        self.logger.info(f"🎬 XFTP_DEBUG: Video has thumbnail: {len(thumbnail_data_url) > 0}")
        self.logger.info(f"🎬 XFTP_DEBUG: Looking for XFTP fields - fileId: {'fileId' in file_info}, fileHash: {'fileHash' in file_info}")
        
        return file_name, file_size, file_type
    
    def validate_file_for_download(self, file_name: str, file_size: int, file_type: str) -> bool:
        """Validate if file meets download criteria"""
        # Define MediaProcessingError locally to avoid circular dependency
        class MediaProcessingError(Exception):
            pass
        
        # Input validation
        if not file_name or not isinstance(file_name, str):
            self.logger.error("Invalid file name provided")
            raise MediaProcessingError("Invalid file name")
        
        if not isinstance(file_size, int) or file_size < 0:
            self.logger.error(f"Invalid file size: {file_size}")
            raise MediaProcessingError("Invalid file size")
        
        if not file_type or not isinstance(file_type, str):
            self.logger.error("Invalid file type provided")
            raise MediaProcessingError("Invalid file type")
        
        # Sanitize filename
        safe_filename = self._sanitize_filename(file_name)
        if not safe_filename:
            self.logger.error(f"Filename sanitization failed: {file_name}")
            raise MediaProcessingError("Invalid filename")
        
        # Check file size limit
        max_size = parse_file_size(self.media_config.get('max_file_size', '100MB'))
        if file_size > max_size:
            self.logger.warning(f"File too large: {file_name} ({file_size} bytes)")
            return False
        
        # Check if file type is allowed
        if file_type not in self.media_config.get('allowed_types', ['image', 'video', 'document', 'audio']):
            self.logger.warning(f"File type not allowed: {file_name}")
            return False
        
        return True
    
    def get_media_statistics(self) -> Dict[str, Any]:
        """Get statistics about downloaded media files"""
        stats = {
            'total_files': 0,
            'total_size_mb': 0.0,
            'images': 0,
            'videos': 0,
            'documents': 0,
            'audio': 0
        }
        
        try:
            for media_type in ['images', 'videos', 'documents', 'audio']:
                media_dir = self.media_path / media_type
                if media_dir.exists():
                    files = list(media_dir.glob('*'))
                    stats[media_type] = len(files)
                    stats['total_files'] += len(files)
                    
                    # Calculate total size
                    for file_path in files:
                        if file_path.is_file():
                            stats['total_size_mb'] += file_path.stat().st_size / (1024 * 1024)
        
        except Exception as e:
            self.logger.error(f"Error calculating media statistics: {e}")
        
        return stats
    
    def _get_file_type(self, filename: str) -> str:
        """Determine file type from filename extension"""
        ext = Path(filename).suffix.lower()
        
        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        video_exts = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm'}
        audio_exts = {'.mp3', '.wav', '.ogg', '.m4a', '.flac'}
        
        if ext in image_exts:
            return 'image'
        elif ext in video_exts:
            return 'video'
        elif ext in audio_exts:
            return 'audio'
        else:
            return 'document'
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent security issues"""
        # Remove null bytes and control characters
        filename = ''.join(char for char in filename if ord(char) >= 32)
        
        # Remove path separators and dangerous characters
        forbidden_chars = ['/', '\\', '..', '~', '|', '&', ';', '`', '$', '<', '>', '"', "'", ':', '?', '*']
        for char in forbidden_chars:
            filename = filename.replace(char, '_')
        
        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = name[:250] + ('.' + ext if ext else '')
        
        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')
        
        # Ensure it's not empty
        if not filename:
            return "unknown_file"
        
        return filename
    
    def generate_safe_filename(self, original_name: str, contact_name: str, file_type: str) -> str:
        """Generate a safe, unique filename to avoid conflicts"""
        # Input validation
        if not isinstance(original_name, str):
            original_name = "unknown_file"
        if not isinstance(contact_name, str):
            contact_name = "unknown_contact"
        if not isinstance(file_type, str):
            file_type = "unknown"
        
        # Sanitize the original filename
        safe_name = self._sanitize_filename(original_name)
        if not safe_name:
            safe_name = "unknown_file"
        
        # Add timestamp and contact info for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_contact = self._sanitize_filename(contact_name)[:20]
        
        # Split filename and extension
        name_part = Path(safe_name).stem
        ext_part = Path(safe_name).suffix
        
        # Create unique filename
        unique_name = f"{timestamp}_{safe_contact}_{name_part}{ext_part}"
        
        # Ensure it's not too long
        if len(unique_name) > 200:
            unique_name = f"{timestamp}_{safe_contact}_{name_part[:50]}{ext_part}"
        
        return unique_name
    
    def _generate_image_filename(self, contact_name: str, image_data_url: str) -> str:
        """Generate a filename for SimpleX images that don't have explicit names"""
        try:
            # Extract file extension from data URL (e.g., data:image/jpg;base64,...)
            if image_data_url.startswith("data:image/"):
                mime_part = image_data_url.split(";")[0]  # data:image/jpg
                image_format = mime_part.split("/")[1]    # jpg
                
                # Map common formats
                format_map = {
                    "jpeg": "jpg",
                    "png": "png",
                    "gif": "gif",
                    "webp": "webp",
                    "bmp": "bmp"
                }
                ext = format_map.get(image_format, image_format)
            else:
                ext = "jpg"  # Default fallback
            
            # Generate timestamp-based filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_contact = self._sanitize_filename(contact_name)[:20]
            
            filename = f"{timestamp}_{safe_contact}_image.{ext}"
            
            self.logger.debug(f"Generated image filename: {filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"Error generating image filename: {e}")
            return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_image.jpg"
    
    def _calculate_data_url_size(self, data_url: str) -> int:
        """Calculate the size of data from a data URL"""
        try:
            if not data_url.startswith("data:"):
                return 0
            
            # Extract base64 part after the comma
            if "," in data_url:
                base64_data = data_url.split(",", 1)[1]
                # Calculate approximate size (base64 is ~4/3 the size of original data)
                # Remove any padding characters for accurate calculation
                base64_clean = base64_data.rstrip("=")
                original_size = (len(base64_clean) * 3) // 4
                
                self.logger.debug(f"Calculated data URL size: {original_size} bytes")
                return original_size
            
            return 0
            
        except Exception as e:
            self.logger.error(f"Error calculating data URL size: {e}")
            return 0