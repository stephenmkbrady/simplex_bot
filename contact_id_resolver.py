#!/usr/bin/env python3
"""
Contact ID Resolver for SimpleX Chat Bot
Resolves localDisplayName to Contact ID using SimpleX CLI
"""

import asyncio
import logging
import re
from typing import Dict, Optional


class ContactIdResolver:
    """Resolves contact names to Contact IDs using SimpleX CLI"""
    
    def __init__(self, simplex_profile_path: str = "/app/profile/simplex", logger: Optional[logging.Logger] = None):
        """
        Initialize contact ID resolver
        
        Args:
            simplex_profile_path: Path to SimpleX profile database
            logger: Logger instance
        """
        self.simplex_profile_path = simplex_profile_path
        self.logger = logger or logging.getLogger(__name__)
        
        # Cache for contact name to ID mapping
        self.contact_id_cache: Dict[str, str] = {}
        self.cache_timestamp = 0
        self.cache_ttl = 300  # 5 minutes
        
        self.logger.info("Contact ID resolver initialized")
    
    async def get_contact_id(self, contact_name: str) -> Optional[str]:
        """
        Get Contact ID for a given contact name
        
        Args:
            contact_name: Local display name of the contact
            
        Returns:
            Contact ID as string or None if not found
        """
        try:
            # Check cache first
            if self._is_cache_valid() and contact_name in self.contact_id_cache:
                return self.contact_id_cache[contact_name]
            
            # Query SimpleX CLI for contact info
            contact_id = await self._query_contact_id(contact_name)
            
            if contact_id:
                # Update cache
                self.contact_id_cache[contact_name] = contact_id
                self.cache_timestamp = asyncio.get_event_loop().time()
                
                self.logger.debug(f"Resolved {contact_name} to Contact ID {contact_id}")
                return contact_id
            
            self.logger.warning(f"Could not resolve Contact ID for {contact_name}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error resolving contact ID for {contact_name}: {e}")
            return None
    
    async def _query_contact_id(self, contact_name: str) -> Optional[str]:
        """Query SimpleX CLI for contact ID"""
        try:
            cmd = [
                "simplex-chat",
                "-d", self.simplex_profile_path,
                "-e", f"/info {contact_name}",
                "-t", "2"
            ]
            
            # Run the command
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                self.logger.error(f"Failed to query contact info for {contact_name}: {stderr.decode()}")
                return None
            
            # Parse the output to extract contact ID
            output = stdout.decode().strip()
            contact_id = self._extract_contact_id(output)
            
            if contact_id:
                self.logger.debug(f"Extracted Contact ID {contact_id} for {contact_name}")
                return contact_id
            
            self.logger.warning(f"Could not extract Contact ID from output: {output}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error querying contact ID for {contact_name}: {e}")
            return None
    
    def _extract_contact_id(self, output: str) -> Optional[str]:
        """Extract contact ID from CLI output"""
        # Look for "contact ID: X" pattern
        match = re.search(r'contact ID:\s*(\d+)', output)
        if match:
            return match.group(1)
        return None
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid"""
        if not self.cache_timestamp:
            return False
        
        current_time = asyncio.get_event_loop().time()
        return (current_time - self.cache_timestamp) < self.cache_ttl
    
    async def refresh_cache(self):
        """Refresh the contact ID cache for all contacts"""
        try:
            # Get all contacts first
            cmd = [
                "simplex-chat",
                "-d", self.simplex_profile_path,
                "-e", "/contacts",
                "-t", "2"
            ]
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                self.logger.error(f"Failed to get contacts list: {stderr.decode()}")
                return
            
            # Parse contact names from output
            output = stdout.decode().strip()
            contact_names = self._extract_contact_names(output)
            
            # Get ID for each contact
            for contact_name in contact_names:
                contact_id = await self._query_contact_id(contact_name)
                if contact_id:
                    self.contact_id_cache[contact_name] = contact_id
            
            self.cache_timestamp = asyncio.get_event_loop().time()
            self.logger.info(f"Refreshed contact ID cache for {len(self.contact_id_cache)} contacts")
            
        except Exception as e:
            self.logger.error(f"Error refreshing contact ID cache: {e}")
    
    def _extract_contact_names(self, output: str) -> list:
        """Extract contact names from /contacts output"""
        lines = output.split('\n')
        contact_names = []
        
        for line in lines:
            line = line.strip()
            # Skip empty lines and system messages
            if line and not line.startswith('Current user:') and not line.startswith('Using SimpleX'):
                contact_names.append(line)
        
        return contact_names
    
    def get_cached_contacts(self) -> Dict[str, str]:
        """Get all cached contact name to ID mappings"""
        return self.contact_id_cache.copy()
    
    def clear_cache(self):
        """Clear the contact ID cache"""
        self.contact_id_cache.clear()
        self.cache_timestamp = 0
        self.logger.info("Contact ID cache cleared")