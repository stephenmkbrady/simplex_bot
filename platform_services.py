#!/usr/bin/env python3
"""
Platform Service Architecture for Universal Bot Plugin System

This module provides the core infrastructure for platform-agnostic services
that plugins can use without being tied to specific platforms like SimpleX.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import logging


class PlatformService(ABC):
    """Base class for platform-specific services"""
    
    def __init__(self, name: str, logger: Optional[logging.Logger] = None):
        self.name = name
        self.logger = logger or logging.getLogger(__name__)
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if service is available on current platform"""
        pass
    
    @abstractmethod
    def get_service_info(self) -> Dict[str, Any]:
        """Get service capabilities and metadata"""
        pass


class MessageHistoryService(PlatformService):
    """Service for accessing message history"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__("message_history", logger)
    
    @abstractmethod
    async def get_recent_messages(self, chat_id: str, count: int = 10) -> List[Dict]:
        """Get recent messages from chat"""
        pass
    
    @abstractmethod
    async def get_messages_by_criteria(self, chat_id: str, **kwargs) -> List[Dict]:
        """Get messages by various criteria (sender, time range, etc.)"""
        pass


class ContactManagementService(PlatformService):
    """Service for managing contacts/users"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__("contact_management", logger)
    
    @abstractmethod
    async def get_contacts(self) -> List[Dict]:
        """Get all contacts"""
        pass
    
    @abstractmethod
    async def get_contact_info(self, contact_id: str) -> Dict:
        """Get specific contact information"""
        pass


class GroupManagementService(PlatformService):
    """Service for managing groups/channels"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__("group_management", logger)
    
    @abstractmethod
    async def get_groups(self) -> List[Dict]:
        """Get all groups"""
        pass
    
    @abstractmethod
    async def get_group_info(self, group_id: str) -> Dict:
        """Get specific group information"""
        pass
    
    @abstractmethod
    async def get_group_members(self, group_id: str) -> List[Dict]:
        """Get group members"""
        pass


class FileService(PlatformService):
    """Service for file operations"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__("file_operations", logger)
    
    @abstractmethod
    async def download_file(self, file_info: Dict) -> str:
        """Download file and return local path"""
        pass
    
    @abstractmethod
    async def send_file(self, chat_id: str, file_path: str, caption: str = "") -> bool:
        """Send file to chat"""
        pass


class InviteManagementService(PlatformService):
    """Service for managing invitations and connections"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__("invite_management", logger)
    
    @abstractmethod
    async def generate_invite(self, requested_by: str) -> Optional[str]:
        """Generate connection invite"""
        pass
    
    @abstractmethod
    async def list_pending_invites(self) -> List[Dict]:
        """List pending invitations"""
        pass


class NotificationService(PlatformService):
    """Service for sending notifications to multiple targets"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__("notification", logger)
    
    @abstractmethod
    async def notify_groups(self, groups: List[str], message: str) -> Dict[str, bool]:
        """Send notification to multiple groups
        Returns: Dict mapping group names to success status"""
        pass
    
    @abstractmethod  
    async def notify_users(self, users: List[str], message: str) -> Dict[str, bool]:
        """Send notification to multiple users
        Returns: Dict mapping user names to success status"""
        pass
    
    @abstractmethod
    async def bulk_notify(self, targets: Dict[str, List[str]], message: str) -> Dict[str, Dict[str, bool]]:
        """Send notifications to mixed targets
        Args: targets = {'groups': ['group1'], 'users': ['user1']}
        Returns: Dict with 'groups' and 'users' keys mapping to success status"""
        pass


class AudioProcessingService(PlatformService):
    """Service for audio processing and speech-to-text functionality"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__("audio_processing", logger)
    
    @abstractmethod
    async def process_audio_file(self, file_path: str, context: Dict[str, Any]) -> Optional[str]:
        """Process audio file and return transcribed text
        Args:
            file_path: Path to the audio file
            context: Additional context for processing (chat_id, user, etc.)
        Returns:
            Transcribed text or None if processing failed
        """
        pass
    
    @abstractmethod
    async def get_supported_formats(self) -> List[str]:
        """Get list of supported audio formats"""
        pass
    
    @abstractmethod
    async def estimate_processing_time(self, file_size: int) -> float:
        """Estimate processing time in seconds based on file size"""
        pass


class PlatformStatusService(PlatformService):
    """Service for getting platform status and diagnostics"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__("platform_status", logger)
    
    @abstractmethod
    async def get_connection_info(self) -> Dict[str, Any]:
        """Get connection status information"""
        pass
    
    @abstractmethod
    async def get_platform_health(self) -> Dict[str, Any]:
        """Get platform health metrics"""
        pass
    
    @abstractmethod
    async def get_diagnostic_info(self) -> Dict[str, Any]:
        """Get detailed diagnostic information"""
        pass


class PlatformServiceRegistry:
    """Central registry for platform-specific services"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.services: Dict[str, PlatformService] = {}
        self.logger = logger or logging.getLogger(__name__)
        self.logger.info("🔧 SERVICE REGISTRY: Initialized platform service registry")
    
    def register_service(self, service_name: str, service_provider: PlatformService):
        """Register a platform service (e.g., message_history, contact_management)"""
        self.services[service_name] = service_provider
        self.logger.info(f"🔧 SERVICE REGISTRY: Registered service '{service_name}'")
    
    def get_service(self, service_name: str) -> Optional[PlatformService]:
        """Get a platform service if available"""
        service = self.services.get(service_name)
        if service:
            self.logger.debug(f"🔧 SERVICE REGISTRY: Retrieved service '{service_name}'")
        else:
            self.logger.debug(f"🔧 SERVICE REGISTRY: Service '{service_name}' not available")
        return service
    
    def list_available_services(self) -> List[str]:
        """List all available services for current platform"""
        return list(self.services.keys())
    
    async def check_service_availability(self, service_name: str) -> bool:
        """Check if a service is both registered and available"""
        service = self.get_service(service_name)
        if not service:
            return False
        
        try:
            return await service.is_available()
        except Exception as e:
            self.logger.error(f"🔧 SERVICE REGISTRY: Error checking availability of '{service_name}': {e}")
            return False
    
    def get_service_info(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific service"""
        service = self.get_service(service_name)
        return service.get_service_info() if service else None
    
    def get_all_services_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all registered services"""
        info = {}
        for name, service in self.services.items():
            try:
                info[name] = service.get_service_info()
            except Exception as e:
                self.logger.error(f"🔧 SERVICE REGISTRY: Error getting info for '{name}': {e}")
                info[name] = {"error": str(e)}
        return info