#!/usr/bin/env python3
"""
Unified Message Context for SimpleX Bot
Handles all message parsing logic in one place to eliminate duplication
"""

import logging
from typing import Dict, Any, Optional


class MessageContext:
    """Unified message context that handles all SimpleX message parsing"""
    
    def __init__(self, raw_message_data: Dict[str, Any]):
        self.raw_message_data = raw_message_data
        self.logger = logging.getLogger("message_context")
        
        # Parse all data once
        self.chat_info = self._extract_chat_info()
        self.chat_item = self._extract_chat_item()
        self.is_group = self._determine_is_group()
        self.contact_name = self._extract_contact_name()
        self.chat_id = self._determine_chat_id()
        self.message_content = self._extract_message_content()
        
        # Debug logging
        self.logger.debug(f"🔍 CONTEXT: is_group={self.is_group}, contact_name='{self.contact_name}', chat_id='{self.chat_id}'")
    
    def _extract_chat_info(self) -> Dict[str, Any]:
        """Extract chat info handling both regular and XFTP event structures"""
        # Check for regular message structure
        chat_info = self.raw_message_data.get("chatInfo", {})
        
        # Check for XFTP event structure
        if not chat_info and "chatItem" in self.raw_message_data:
            chat_item = self.raw_message_data["chatItem"]
            chat_info = chat_item.get("chatInfo", {})
        
        return chat_info
    
    def _extract_chat_item(self) -> Dict[str, Any]:
        """Extract chat item from message data"""
        return self.raw_message_data.get("chatItem", {})
    
    def _determine_is_group(self) -> bool:
        """Determine if this is a group message"""
        return "groupInfo" in self.chat_info
    
    def _extract_contact_name(self) -> str:
        """Extract the actual sender's contact name (works for both direct and group messages)"""
        try:
            if self.is_group:
                # For group messages, get the actual sender from groupMember
                chat_dir = self.chat_item.get("chatDir", {})
                group_member = chat_dir.get("groupMember", {})
                
                if group_member:
                    contact_name = group_member.get("localDisplayName", "Unknown Member")
                    self.logger.debug(f"🔍 CONTEXT: Group message from '{contact_name}' via groupMember")
                    return contact_name
                else:
                    # Fallback: try to get from chat_info (less reliable for groups)
                    contact_info = self.chat_info.get("contact", {})
                    contact_name = contact_info.get("localDisplayName", "Unknown Member")
                    self.logger.debug(f"🔍 CONTEXT: Group message fallback contact '{contact_name}'")
                    return contact_name
            else:
                # For direct messages, get from contact info
                contact_info = self.chat_info.get("contact", {})
                contact_name = contact_info.get("localDisplayName", "Unknown")
                self.logger.debug(f"🔍 CONTEXT: Direct message from '{contact_name}'")
                return contact_name
                
        except Exception as e:
            self.logger.error(f"🔍 CONTEXT: Error extracting contact name: {e}")
            return "Unknown"
    
    def _determine_chat_id(self) -> str:
        """Determine the correct chat ID for routing messages"""
        try:
            if self.is_group:
                # Group message - route to group
                group_info = self.chat_info.get("groupInfo", {})
                chat_id = group_info.get("localDisplayName", group_info.get("groupName", self.contact_name))
                self.logger.debug(f"🔍 CONTEXT: Group chat_id='{chat_id}'")
                return chat_id
            else:
                # Direct message - route to contact
                self.logger.debug(f"🔍 CONTEXT: Direct chat_id='{self.contact_name}'")
                return self.contact_name
                
        except Exception as e:
            self.logger.error(f"🔍 CONTEXT: Error determining chat ID: {e}")
            # Fallback to contact name
            return self.contact_name
    
    def _extract_message_content(self) -> Dict[str, Any]:
        """Extract message content and metadata"""
        try:
            content = self.chat_item.get("content", {})
            msg_content = content.get("msgContent", {})
            
            return {
                "type": msg_content.get("type", "unknown"),
                "text": msg_content.get("text", ""),
                "full_content": content,
                "msg_content": msg_content
            }
        except Exception as e:
            self.logger.error(f"🔍 CONTEXT: Error extracting message content: {e}")
            return {
                "type": "unknown",
                "text": "",
                "full_content": {},
                "msg_content": {}
            }
    
    def get_chat_context_string(self) -> str:
        """Get a human-readable context string for logging"""
        if self.is_group:
            return f"Group '{self.chat_id}' from {self.contact_name}"
        else:
            return f"DM from {self.contact_name}"
    
    def should_quote_chat_id(self) -> bool:
        """Determine if chat_id needs quoting for SimpleX CLI"""
        return self.is_group and ' ' in self.chat_id
    
    def get_quoted_chat_id(self) -> str:
        """Get properly quoted chat_id for SimpleX CLI commands"""
        if self.should_quote_chat_id():
            return f"'{self.chat_id}'"
        return self.chat_id