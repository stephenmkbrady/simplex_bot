#!/usr/bin/env python3
"""
XFTP Client for SimpleX Bot
Handles file downloads using the XFTP (SimpleX File Transfer Protocol)
"""

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import shutil


logger = logging.getLogger(__name__)

# Constants
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB
DEFAULT_RETRY_ATTEMPTS = 3
HASH_CHUNK_SIZE = 4096


@dataclass
class CLIResult:
    """Result from XFTP CLI execution"""
    success: bool
    output: str
    error: str
    return_code: int
    execution_time: float


class XFTPError(Exception):
    """Base exception for XFTP operations"""
    pass


class XFTPDownloadError(XFTPError):
    """Download operation failed"""
    pass


class XFTPIntegrityError(XFTPError):
    """File integrity verification failed"""
    pass


class XFTPTimeoutError(XFTPError):
    """Download timeout exceeded"""
    pass


class XFTPCLIInterface:
    """Manages XFTP CLI subprocess operations"""
    
    def __init__(self, cli_path: str, timeout: int = DEFAULT_TIMEOUT_SECONDS):
        self.cli_path = cli_path
        self.timeout = timeout
        
    async def execute_recv(self, xftp_file: str, output_dir: str) -> CLIResult:
        """Execute xftp recv command"""
        start_time = time.time()
        
        # Use absolute paths to avoid path resolution issues
        abs_xftp_file = os.path.abspath(xftp_file)
        abs_output_dir = os.path.abspath(output_dir)
        
        cmd = [self.cli_path, "recv", abs_xftp_file, abs_output_dir, "-y"]  # Add -y flag to auto-answer yes
        
        try:
            # Change to output directory to ensure file is saved there
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=abs_output_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=self.timeout
            )
            
            execution_time = time.time() - start_time
            
            return CLIResult(
                success=(process.returncode == 0),
                output=stdout.decode('utf-8', errors='ignore'),
                error=stderr.decode('utf-8', errors='ignore'),
                return_code=process.returncode,
                execution_time=execution_time
            )
            
        except asyncio.TimeoutError:
            logger.error(f"XFTP command timed out after {self.timeout} seconds")
            raise XFTPTimeoutError(f"Download timeout exceeded ({self.timeout}s)")
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Error executing XFTP command: {e}")
            return CLIResult(
                success=False,
                output="",
                error=str(e),
                return_code=-1,
                execution_time=execution_time
            )
    
    def parse_cli_output(self, output: str) -> Dict:
        """Parse CLI output for status and progress information"""
        lines = output.strip().split('\n')
        result = {
            'status': 'unknown',
            'progress': 0,
            'error': None,
            'file_path': None
        }
        
        for line in lines:
            line = line.strip()
            if 'received file' in line.lower() or 'file downloaded:' in line.lower():
                result['status'] = 'completed'
                # Try to extract file path
                if ':' in line:
                    result['file_path'] = line.split(':', 1)[1].strip()
            elif 'receiving' in line.lower():
                result['status'] = 'downloading'
            elif 'error' in line.lower() or 'failed' in line.lower():
                result['status'] = 'error'
                result['error'] = line
            elif '%' in line:
                # Try to extract progress percentage
                try:
                    import re
                    match = re.search(r'(\d+)%', line)
                    if match:
                        result['progress'] = int(match.group(1))
                except:
                    pass
        
        return result


class SecurityValidator:
    """Security validation for XFTP operations"""
    
    @staticmethod
    def validate_file_path(path: str, allowed_dirs: List[str]) -> bool:
        """Prevent directory traversal attacks"""
        try:
            resolved_path = Path(path).resolve()
            for allowed_dir in allowed_dirs:
                if resolved_path.is_relative_to(Path(allowed_dir).resolve()):
                    return True
            return False
        except Exception:
            return False
    
    @staticmethod
    def validate_file_size(size: int, max_size: int = DEFAULT_MAX_FILE_SIZE) -> bool:
        """Enforce file size limits (default 1GB)"""
        return 0 < size <= max_size
    
    @staticmethod
    def secure_cleanup(file_path: str):
        """Securely delete temporary files"""
        try:
            if os.path.exists(file_path):
                # Overwrite with random data before deletion for security
                with open(file_path, 'rb+') as f:
                    length = f.seek(0, 2)  # Get file size
                    f.seek(0)
                    f.write(os.urandom(length))
                    f.flush()
                    os.fsync(f.fileno())
                os.remove(file_path)
        except Exception as e:
            logger.warning(f"Failed to securely delete {file_path}: {e}")
    
    @staticmethod
    def validate_file_description(description: str) -> bool:
        """Validate file description format"""
        if not description or len(description.strip()) == 0:
            return False
        
        # Basic validation - should contain some key XFTP markers
        # This would need to be more sophisticated based on actual XFTP format
        return len(description) > 10 and not any(
            dangerous in description.lower() 
            for dangerous in ['../', '~/', '/etc/', '/proc/', '/sys/']
        )


class XFTPClient:
    """Main interface for XFTP file operations"""
    
    def __init__(self, cli_path: str, temp_dir: str, config: Dict, logger: logging.Logger):
        self.cli_path = cli_path
        self.temp_dir = Path(temp_dir)
        self.config = config
        self.logger = logger
        
        # Create temp directory if it doesn't exist
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize CLI interface
        timeout_raw = config.get('timeout', 300)
        timeout = int(timeout_raw) if isinstance(timeout_raw, str) else timeout_raw
        self.cli = XFTPCLIInterface(
            cli_path=cli_path,
            timeout=timeout
        )
        
        # Configuration
        max_file_size_raw = config.get('max_file_size', DEFAULT_MAX_FILE_SIZE)
        self.max_file_size = int(max_file_size_raw) if isinstance(max_file_size_raw, str) else max_file_size_raw
        
        retry_attempts_raw = config.get('retry_attempts', DEFAULT_RETRY_ATTEMPTS)
        self.retry_attempts = int(retry_attempts_raw) if isinstance(retry_attempts_raw, str) else retry_attempts_raw
        
        cleanup_raw = config.get('cleanup_on_failure', True)
        self.cleanup_on_failure = cleanup_raw if isinstance(cleanup_raw, bool) else str(cleanup_raw).lower() == 'true'
        
    async def download_file(self, file_id: str, file_hash: str, file_size: int, 
                          file_name: str, output_path: str) -> bool:
        """
        Download file using XFTP protocol
        
        Args:
            file_id: XFTP file identifier
            file_hash: Expected file hash for verification
            file_size: Expected file size
            file_name: Original filename (for logging)
            output_path: Where to save the downloaded file
            
        Returns:
            True if successful, False if failed
        """
        session_id = f"xftp_{int(time.time())}_{hash(file_id)}"
        temp_xftp_file = None
        temp_output_dir = None
        
        self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: download_file called - file_name: {file_name}, file_id: {file_id}, file_size: {file_size}")
        self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI path: {self.cli_path}, available: {os.path.exists(self.cli_path)}")
        
        try:
            # Validate inputs
            if not SecurityValidator.validate_file_size(file_size, self.max_file_size):
                self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: File size validation failed: {file_size} > {self.max_file_size}")
                raise XFTPDownloadError(f"File size {file_size} exceeds limit {self.max_file_size}")
            
            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: File size validation passed")
            
            # Create temporary directory for this download
            temp_output_dir = self.temp_dir / session_id
            temp_output_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Created temp directory: {temp_output_dir}")
            
            # Create .xftp file description
            file_description = self._create_xftp_description(file_id, file_hash, file_size)
            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Created file description: {file_description}")
            
            if not SecurityValidator.validate_file_description(file_description):
                self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: File description validation failed")
                raise XFTPDownloadError("Invalid file description format")
            
            # Write file description to temporary .xftp file
            temp_xftp_file = temp_output_dir / f"{session_id}.xftp"
            with open(temp_xftp_file, 'w') as f:
                f.write(file_description)
            
            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Written .xftp file to: {temp_xftp_file}")
            self.logger.info(f"Starting XFTP download for {file_name} (ID: {file_id})")
            
            # Attempt download with retries
            last_error = None
            for attempt in range(self.retry_attempts):
                try:
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Attempt {attempt + 1}/{self.retry_attempts}")
                    result = await self.cli.execute_recv(str(temp_xftp_file), str(temp_output_dir))
                    
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI result - success: {result.success}, return_code: {result.return_code}")
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI output: {result.output}")
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI error: {result.error}")
                    
                    if result.success:
                        # Find the downloaded file
                        downloaded_file = self._find_downloaded_file(temp_output_dir, file_name)
                        self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Found downloaded file: {downloaded_file}")
                        
                        if downloaded_file and downloaded_file.exists():
                            # Verify integrity
                            if self.verify_file_integrity(str(downloaded_file), file_hash):
                                # Move to final location
                                shutil.move(str(downloaded_file), output_path)
                                self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: XFTP download successful: {file_name}")
                                return True
                            else:
                                self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: File integrity verification failed")
                                raise XFTPIntegrityError("File integrity verification failed")
                        else:
                            self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: Downloaded file not found in {temp_output_dir}")
                            raise XFTPDownloadError("Downloaded file not found")
                    else:
                        error_msg = f"XFTP CLI failed: {result.error}"
                        self.logger.warning(f"🚀 XFTP_CLIENT_DEBUG: Attempt {attempt + 1}/{self.retry_attempts} failed: {error_msg}")
                        last_error = error_msg
                        
                        if attempt < self.retry_attempts - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            
                except Exception as e:
                    error_msg = f"Download attempt failed: {e}"
                    self.logger.warning(f"🚀 XFTP_CLIENT_DEBUG: Attempt {attempt + 1}/{self.retry_attempts} failed: {error_msg}")
                    last_error = error_msg
                    
                    if attempt < self.retry_attempts - 1:
                        await asyncio.sleep(2 ** attempt)
            
            self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: All attempts failed")
            raise XFTPDownloadError(f"All {self.retry_attempts} attempts failed. Last error: {last_error}")
            
        except Exception as e:
            self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: XFTP download error for {file_name}: {e}")
            return False
            
        finally:
            # Cleanup temporary files
            if self.cleanup_on_failure or True:  # Always cleanup for security
                await self.cleanup_temp_files(session_id, temp_output_dir)
    
    async def download_file_with_description(self, file_description: str, file_size: int, 
                                           file_name: str, output_path: str) -> bool:
        """
        Download file using XFTP protocol with provided file description
        
        Args:
            file_description: XFTP file description text (content of .xftp file)
            file_size: Expected file size
            file_name: Original filename (for logging)
            output_path: Where to save the downloaded file
            
        Returns:
            True if successful, False if failed
        """
        session_id = f"xftp_{int(time.time())}_{hash(file_description)}"
        temp_xftp_file = None
        temp_output_dir = None
        
        self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: download_file_with_description called - file_name: {file_name}, file_size: {file_size}")
        self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI path: {self.cli_path}, available: {os.path.exists(self.cli_path)}")
        self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: File description: {file_description}")
        
        try:
            # Validate inputs
            if not SecurityValidator.validate_file_size(file_size, self.max_file_size):
                self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: File size validation failed: {file_size} > {self.max_file_size}")
                raise XFTPDownloadError(f"File size {file_size} exceeds limit {self.max_file_size}")
            
            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: File size validation passed")
            
            # Create temporary directory for this download
            temp_output_dir = self.temp_dir / session_id
            temp_output_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Created temp directory: {temp_output_dir}")
            
            # Validate file description
            if not SecurityValidator.validate_file_description(file_description):
                self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: File description validation failed")
                raise XFTPDownloadError("Invalid file description format")
            
            # Write file description to temporary .xftp file
            temp_xftp_file = temp_output_dir / f"{session_id}.xftp"
            with open(temp_xftp_file, 'w') as f:
                f.write(file_description)
            
            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Written .xftp file to: {temp_xftp_file}")
            self.logger.info(f"Starting XFTP download for {file_name}")
            
            # Attempt download with retries
            last_error = None
            for attempt in range(self.retry_attempts):
                try:
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Attempt {attempt + 1}/{self.retry_attempts}")
                    result = await self.cli.execute_recv(str(temp_xftp_file), str(temp_output_dir))
                    
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI result - success: {result.success}, return_code: {result.return_code}")
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI output: {result.output}")
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI error: {result.error}")
                    
                    # Check if download was successful by looking for "File downloaded:" in output
                    if result.success or "File downloaded:" in result.output:
                        # Find the downloaded file
                        downloaded_file = self._find_downloaded_file(temp_output_dir, file_name)
                        self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Found downloaded file: {downloaded_file}")
                        
                        if downloaded_file and downloaded_file.exists():
                            # For now, skip integrity verification since we don't have expected hash
                            # Move to final location
                            shutil.move(str(downloaded_file), output_path)
                            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: XFTP download successful: {file_name}")
                            return True
                        else:
                            self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: Downloaded file not found in {temp_output_dir}")
                            raise XFTPDownloadError("Downloaded file not found")
                    else:
                        error_msg = f"XFTP CLI failed: {result.error}"
                        self.logger.warning(f"🚀 XFTP_CLIENT_DEBUG: Attempt {attempt + 1}/{self.retry_attempts} failed: {error_msg}")
                        last_error = error_msg
                        
                        if attempt < self.retry_attempts - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            
                except Exception as e:
                    error_msg = f"Download attempt failed: {e}"
                    self.logger.warning(f"🚀 XFTP_CLIENT_DEBUG: Attempt {attempt + 1}/{self.retry_attempts} failed: {error_msg}")
                    last_error = error_msg
                    
                    if attempt < self.retry_attempts - 1:
                        await asyncio.sleep(2 ** attempt)
            
            self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: All attempts failed")
            raise XFTPDownloadError(f"All {self.retry_attempts} attempts failed. Last error: {last_error}")
            
        except Exception as e:
            self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: XFTP download error for {file_name}: {e}")
            return False
            
        finally:
            # Cleanup temporary files
            if self.cleanup_on_failure or True:  # Always cleanup for security
                await self.cleanup_temp_files(session_id, temp_output_dir)
    
    async def download_file_with_description_get_filename(self, file_description: str, file_size: int, 
                                                        temp_dir: str) -> tuple:
        """
        Download file using XFTP protocol with provided file description and return actual filename
        
        Args:
            file_description: XFTP file description text (content of .xftp file)
            file_size: Expected file size
            temp_dir: Temporary directory to download to
            
        Returns:
            Tuple of (success: bool, actual_filename: str or None, file_path: str or None)
        """
        session_id = f"xftp_{int(time.time())}_{hash(file_description)}"
        temp_xftp_file = None
        temp_output_dir = None
        
        self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: download_file_with_description_get_filename called - file_size: {file_size}")
        self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI path: {self.cli_path}, available: {os.path.exists(self.cli_path)}")
        
        try:
            # Validate inputs
            if not SecurityValidator.validate_file_size(file_size, self.max_file_size):
                self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: File size validation failed: {file_size} > {self.max_file_size}")
                return (False, None, None)
            
            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: File size validation passed")
            
            # Create temporary directory for this download
            temp_output_dir = Path(temp_dir) / session_id
            temp_output_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Created temp directory: {temp_output_dir}")
            
            # Validate file description
            if not SecurityValidator.validate_file_description(file_description):
                self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: File description validation failed")
                return (False, None, None)
            
            # Write file description to temporary .xftp file
            temp_xftp_file = temp_output_dir / f"{session_id}.xftp"
            with open(temp_xftp_file, 'w') as f:
                f.write(file_description)
            
            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Written .xftp file to: {temp_xftp_file}")
            self.logger.info(f"Starting XFTP download for filename detection")
            
            # Attempt download with retries
            last_error = None
            for attempt in range(self.retry_attempts):
                try:
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Attempt {attempt + 1}/{self.retry_attempts}")
                    result = await self.cli.execute_recv(str(temp_xftp_file), str(temp_output_dir))
                    
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI result - success: {result.success}, return_code: {result.return_code}")
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI output: {result.output}")
                    self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: CLI error: {result.error}")
                    
                    # Check if download was successful by looking for "File downloaded:" in output
                    if result.success or "File downloaded:" in result.output:
                        # Find the downloaded file (but don't move it)
                        downloaded_files = list(temp_output_dir.glob("*"))
                        downloaded_files = [f for f in downloaded_files if f.is_file() and not f.name.endswith('.xftp')]
                        
                        if downloaded_files:
                            actual_file = downloaded_files[0]  # Should be only one file
                            actual_filename = actual_file.name
                            self.logger.info(f"🚀 XFTP_CLIENT_DEBUG: Found downloaded file: {actual_filename}")
                            return (True, actual_filename, str(actual_file))
                        else:
                            self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: Downloaded file not found in {temp_output_dir}")
                            return (False, None, None)
                    else:
                        error_msg = f"XFTP CLI failed: {result.error}"
                        self.logger.warning(f"🚀 XFTP_CLIENT_DEBUG: Attempt {attempt + 1}/{self.retry_attempts} failed: {error_msg}")
                        last_error = error_msg
                        
                        if attempt < self.retry_attempts - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            
                except Exception as e:
                    error_msg = f"Download attempt failed: {e}"
                    self.logger.warning(f"🚀 XFTP_CLIENT_DEBUG: Attempt {attempt + 1}/{self.retry_attempts} failed: {error_msg}")
                    last_error = error_msg
                    
                    if attempt < self.retry_attempts - 1:
                        await asyncio.sleep(2 ** attempt)
            
            self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: All attempts failed")
            return (False, None, None)
            
        except Exception as e:
            self.logger.error(f"🚀 XFTP_CLIENT_DEBUG: XFTP download error: {e}")
            return (False, None, None)
            
        finally:
            # Don't cleanup here - let the caller handle cleanup after moving the file
            pass
    
    def _create_xftp_description(self, file_id: str, file_hash: str, file_size: int) -> str:
        """
        Create XFTP file description from SimpleX metadata
        
        Note: This is a placeholder implementation. The actual format would need
        to be determined based on how SimpleX Chat provides file metadata.
        """
        # This is a simplified placeholder - the actual implementation would need
        # to properly format the .xftp file based on the SimpleX protocol
        description = {
            "version": "1.0",
            "fileId": file_id,
            "fileHash": file_hash,
            "fileSize": file_size,
            "timestamp": int(time.time())
        }
        
        # In reality, this would need to be the proper XFTP format
        # For now, return a JSON representation as a placeholder
        return json.dumps(description, indent=2)
    
    def _find_downloaded_file(self, temp_dir: Path, expected_name: str) -> Optional[Path]:
        """Find the downloaded file in the temporary directory"""
        try:
            # Look for files that aren't .xftp files
            for file_path in temp_dir.iterdir():
                if file_path.is_file() and not file_path.name.endswith('.xftp'):
                    return file_path
            return None
        except Exception as e:
            self.logger.error(f"Error finding downloaded file: {e}")
            return None
    
    def verify_file_integrity(self, file_path: str, expected_hash: str) -> bool:
        """Verify downloaded file integrity using SHA-512"""
        try:
            if not os.path.exists(file_path):
                return False
            
            # Calculate SHA-512 hash
            sha512_hash = hashlib.sha512()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b''):
                    sha512_hash.update(chunk)
            
            calculated_hash = sha512_hash.hexdigest()
            
            # Compare hashes (case-insensitive)
            return calculated_hash.lower() == expected_hash.lower()
            
        except Exception as e:
            self.logger.error(f"Error verifying file integrity: {e}")
            return False
    
    async def cleanup_temp_files(self, session_id: str, temp_dir: Optional[Path] = None):
        """Clean up temporary files for a session"""
        try:
            if temp_dir is None:
                temp_dir = self.temp_dir / session_id
            
            if temp_dir and temp_dir.exists():
                # Securely delete all files in the temp directory
                for file_path in temp_dir.rglob('*'):
                    if file_path.is_file():
                        SecurityValidator.secure_cleanup(str(file_path))
                
                # Remove the directory
                shutil.rmtree(temp_dir, ignore_errors=True)
                
            self.logger.debug(f"Cleaned up temporary files for session {session_id}")
            
        except Exception as e:
            self.logger.warning(f"Failed to cleanup temp files for session {session_id}: {e}")
    
    def is_available(self) -> bool:
        """Check if XFTP CLI is available and functional"""
        try:
            if not os.path.exists(self.cli_path):
                return False
            
            if not os.access(self.cli_path, os.X_OK):
                return False
            
            # TODO: Add a simple test command to verify XFTP CLI works
            return True
            
        except Exception:
            return False