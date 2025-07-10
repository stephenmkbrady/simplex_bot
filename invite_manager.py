#!/usr/bin/env python3
"""
Invite Manager for SimpleX Chat Bot
Handles one-time connection invite generation and auto-acceptance
"""

import asyncio
import json
import logging
import subprocess
import time
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta


class InviteManager:
    """Manages connection invites and auto-acceptance"""
    
    def __init__(self, simplex_profile_path: str = "/app/profile/simplex", logger: Optional[logging.Logger] = None):
        """
        Initialize invite manager
        
        Args:
            simplex_profile_path: Path to SimpleX profile database
            logger: Logger instance
        """
        self.simplex_profile_path = simplex_profile_path
        self.logger = logger or logging.getLogger(__name__)
        
        # Track generated invites for auto-acceptance
        self.pending_invites: Set[str] = set()
        self.invite_metadata: Dict[str, Dict] = {}
        
        # Configuration
        self.max_pending_invites = 10
        self.invite_expiry_hours = 24
        
        self.logger.info("Invite manager initialized")
    
    async def generate_invite_with_websocket_disconnect(self, websocket_manager, requested_by: str, contact_id: str = None) -> Optional[str]:
        """
        Generate invite by disconnecting WebSocket and letting main loop handle reconnection
        
        Args:
            websocket_manager: WebSocket manager to disconnect 
            requested_by: Name of the admin who requested the invite
            contact_id: Contact ID of the admin (for verification)
            
        Returns:
            Invitation link or None if failed
        """
        try:
            # Clean up expired invites first
            self._cleanup_expired_invites()
            
            # Check if we have too many pending invites
            if len(self.pending_invites) >= self.max_pending_invites:
                self.logger.warning(f"Too many pending invites ({len(self.pending_invites)}), cleanup needed")
                return None
            
            self.logger.info(f"🎫 INVITE START: Generating invite for {requested_by}")
            
            # Step 1: Disconnect WebSocket to release database lock
            self.logger.info("🎫 DISCONNECT: Disconnecting WebSocket for invite generation...")
            await websocket_manager.disconnect()
            
            # Wait to ensure clean disconnect and database release
            self.logger.info("🎫 WAIT: Waiting for database lock release...")
            await asyncio.sleep(2)
            
            # Step 2: Generate invite using CLI (safe now)
            self.logger.info("🎫 GENERATE: Calling CLI to generate invite...")
            invite_link = await self.generate_invite(requested_by, contact_id)
            
            # Wait to ensure CLI is completely done
            self.logger.info("🎫 CLI COMPLETE: Waiting for CLI completion...")
            await asyncio.sleep(1)
            
            # Step 3: Schedule CLI restart to prevent corruption
            self.logger.info("🎫 PROACTIVE RESTART: Scheduling CLI restart to prevent corruption...")
            asyncio.create_task(self._schedule_cli_restart())
            
            # Step 4: DO NOT RECONNECT - let main loop handle it
            self.logger.info("🎫 INVITE COMPLETE: Invite generation finished, main loop will handle reconnection")
                
            return invite_link
            
        except Exception as e:
            self.logger.error(f"🎫 INVITE ERROR: Error generating invite: {type(e).__name__}: {e}")
            import traceback
            self.logger.error(f"🎫 INVITE TRACEBACK: {traceback.format_exc()}")
            return None
    
    async def generate_invite(self, requested_by: str, contact_id: str = None) -> Optional[str]:
        """
        Generate invite using CLI - causes temporary database lock but works
        """
        try:
            # Clean up expired invites first
            self._cleanup_expired_invites()
            
            if len(self.pending_invites) >= self.max_pending_invites:
                self.logger.warning(f"Too many pending invites ({len(self.pending_invites)})")
                return None
            
            cmd = ["simplex-chat", "-d", self.simplex_profile_path, "-e", "/connect", "-t", "2"]
            self.logger.info(f"Generating invite requested by {requested_by}")
            
            result = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                self.logger.error(f"Failed to generate invite: {stderr.decode()}")
                return None
            
            output = stdout.decode().strip()
            invite_link = self._extract_invite_link(output)
            
            if not invite_link:
                self.logger.error("Failed to extract invite link")
                return None
            
            # Store invite metadata
            invite_id = self._generate_invite_id(invite_link)
            self.pending_invites.add(invite_id)
            self.invite_metadata[invite_id] = {
                'link': invite_link, 'requested_by': requested_by, 'contact_id': contact_id,
                'created_at': datetime.now(), 'expires_at': datetime.now() + timedelta(hours=self.invite_expiry_hours)
            }
            
            self.logger.info(f"Generated invite {invite_id} for {requested_by}")
            return invite_link
            
        except Exception as e:
            self.logger.error(f"Error generating invite: {e}")
            return None
    
    def _extract_invite_link(self, output: str) -> Optional[str]:
        """Extract the invitation link from CLI output"""
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('https://simplex.chat/invitation'):
                return line
        return None
    
    def _extract_invite_from_websocket_response(self, response: Dict) -> Optional[str]:
        """Extract invitation link from WebSocket response"""
        try:
            # WebSocket response structure may vary - check common fields
            if isinstance(response, dict):
                # Look for invite link in response text/message
                response_text = response.get('response', '') or response.get('message', '') or str(response)
                
                # Search for invitation URL in the response text
                if 'https://simplex.chat/invitation' in response_text:
                    # Extract the URL
                    import re
                    match = re.search(r'https://simplex\.chat/invitation[^\s]*', response_text)
                    if match:
                        return match.group(0)
                
                # Also check if the entire response is just the URL
                if response_text.startswith('https://simplex.chat/invitation'):
                    return response_text.strip()
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error parsing WebSocket response: {e}")
            return None
    
    def _generate_invite_id(self, invite_link: str) -> str:
        """Generate a unique ID for the invite based on the link"""
        # Extract key parts from the invite link for a unique ID
        import hashlib
        return hashlib.md5(invite_link.encode()).hexdigest()[:8]
    
    def _cleanup_expired_invites(self):
        """Remove expired invites from tracking"""
        now = datetime.now()
        expired_invites = []
        
        for invite_id, metadata in self.invite_metadata.items():
            if metadata['expires_at'] < now:
                expired_invites.append(invite_id)
        
        for invite_id in expired_invites:
            self.pending_invites.discard(invite_id)
            del self.invite_metadata[invite_id]
            self.logger.info(f"Removed expired invite {invite_id}")
    
    def should_auto_accept(self, contact_request_data: Dict) -> bool:
        """
        Check if an incoming contact request should be auto-accepted
        
        This is a simplified check - in a real implementation you'd want
        to match the contact request to the generated invite somehow
        """
        # For now, auto-accept all requests if we have pending invites
        # In a more sophisticated system, you'd match the request to the specific invite
        return len(self.pending_invites) > 0
    
    def mark_invite_used(self, invite_id: str = None):
        """
        Mark an invite as used (remove from pending)
        
        Args:
            invite_id: Specific invite ID, or None to remove oldest
        """
        if invite_id and invite_id in self.pending_invites:
            self.pending_invites.remove(invite_id)
            del self.invite_metadata[invite_id]
            self.logger.info(f"Marked invite {invite_id} as used")
        elif self.pending_invites:
            # Remove oldest invite if no specific ID provided
            oldest_invite = min(self.invite_metadata.keys(), 
                              key=lambda k: self.invite_metadata[k]['created_at'])
            self.pending_invites.remove(oldest_invite)
            del self.invite_metadata[oldest_invite]
            self.logger.info(f"Marked oldest invite {oldest_invite} as used")
    
    def get_pending_invites(self) -> List[Dict]:
        """Get list of pending invites with metadata"""
        self._cleanup_expired_invites()
        
        invites = []
        for invite_id, metadata in self.invite_metadata.items():
            invites.append({
                'id': invite_id,
                'requested_by': metadata['requested_by'],
                'contact_id': metadata.get('contact_id'),
                'created_at': metadata['created_at'],
                'expires_at': metadata['expires_at'],
                'link': metadata['link']
            })
        
        # Sort by creation time
        invites.sort(key=lambda x: x['created_at'])
        return invites
    
    def revoke_invite(self, invite_id: str) -> bool:
        """
        Revoke a pending invite
        
        Args:
            invite_id: ID of the invite to revoke
            
        Returns:
            True if successfully revoked, False if not found
        """
        if invite_id in self.pending_invites:
            self.pending_invites.remove(invite_id)
            del self.invite_metadata[invite_id]
            self.logger.info(f"Revoked invite {invite_id}")
            return True
        return False
    
    def get_stats(self) -> Dict:
        """Get invite statistics"""
        self._cleanup_expired_invites()
        
        return {
            'pending_invites': len(self.pending_invites),
            'max_pending_invites': self.max_pending_invites,
            'invite_expiry_hours': self.invite_expiry_hours
        }
    
    async def _schedule_cli_restart(self):
        """Schedule CLI restart after a short delay to prevent corruption"""
        try:
            # Wait a few seconds to ensure invite message is sent
            await asyncio.sleep(3)
            
            self.logger.info("🔄 PROACTIVE CLI RESTART: Killing SimpleX CLI process to prevent corruption...")
            
            # Kill the SimpleX CLI process (container will restart it)
            result = await asyncio.create_subprocess_exec(
                "pkill", "-f", "simplex-chat",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                self.logger.info("✅ PROACTIVE CLI RESTART: SimpleX CLI process killed successfully")
                self.logger.info("🔄 PROACTIVE CLI RESTART: Container will restart CLI automatically")
            else:
                self.logger.warning(f"⚠️ PROACTIVE CLI RESTART: pkill returned {result.returncode}")
                if stderr:
                    self.logger.warning(f"⚠️ PROACTIVE CLI RESTART: pkill stderr: {stderr.decode()}")
                    
        except Exception as e:
            self.logger.error(f"🔄 PROACTIVE CLI RESTART ERROR: {type(e).__name__}: {e}")
            import traceback
            self.logger.error(f"🔄 PROACTIVE CLI RESTART TRACEBACK: {traceback.format_exc()}")