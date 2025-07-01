#!/usr/bin/env python3
"""
SimpleX Chat utility functions for the bot
"""

import asyncio
import websockets
import json
import logging
import sys
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SimplexConnector:
    """Utility class for connecting to SimpleX Chat via WebSocket"""
    
    def __init__(self, websocket_url: str = "ws://localhost:3030"):
        self.websocket_url = websocket_url
        self.corr_id_counter = 1
    
    def get_next_corr_id(self) -> str:
        """Get next correlation ID for commands"""
        corr_id = str(self.corr_id_counter)
        self.corr_id_counter += 1
        return corr_id
    
    async def send_command(self, command: str, timeout: int = 30) -> Optional[Dict[Any, Any]]:
        """Send a command to SimpleX Chat and return the response"""
        try:
            async with websockets.connect(self.websocket_url) as websocket:
                corr_id = self.get_next_corr_id()
                message = {
                    "corrId": corr_id,
                    "cmd": command
                }
                
                logger.info(f"Sending command: {command}")
                await websocket.send(json.dumps(message))
                
                response = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                response_data = json.loads(response)
                
                logger.info(f"Received response: {response_data}")
                return response_data
                
        except websockets.exceptions.ConnectionRefused:
            logger.error("Failed to connect to SimpleX Chat WebSocket - connection refused")
            return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for response from SimpleX Chat (timeout: {timeout}s)")
            return None
        except Exception as e:
            logger.error(f"Error communicating with SimpleX Chat: {e}")
            return None
    
    async def connect_to_invitation(self, invitation_url: str) -> bool:
        """Connect to a SimpleX Chat invitation"""
        logger.info(f"Attempting to connect to invitation: {invitation_url}")
        
        response = await self.send_command(f"/connect {invitation_url}")
        
        if response and "resp" in response and "Right" in response["resp"]:
            resp_type = response["resp"]["Right"].get("type")
            if resp_type == "sentConfirmation":
                logger.info("✓ Connection invitation sent successfully")
                return True
            else:
                logger.warning(f"Unexpected response type: {resp_type}")
        else:
            logger.error("Failed to connect to invitation")
        
        return False
    
    async def get_contacts(self) -> Optional[list]:
        """Get list of contacts"""
        response = await self.send_command("/contacts")
        
        if response and "resp" in response and "Right" in response["resp"]:
            contacts_data = response["resp"]["Right"]
            if contacts_data.get("type") == "contactsList":
                return contacts_data.get("contacts", [])
        
        return None
    
    async def get_user_info(self) -> Optional[Dict[Any, Any]]:
        """Get current user information"""
        response = await self.send_command("/me")
        
        if response and "resp" in response and "Right" in response["resp"]:
            return response["resp"]["Right"]
        
        return None

async def connect_invitation_main(invitation_url: str) -> bool:
    """Main function for connecting to an invitation"""
    connector = SimplexConnector()
    
    # Try to connect
    success = await connector.connect_to_invitation(invitation_url)
    
    if success:
        print("✓ Connection invitation sent successfully")
        
        # Check contacts after connection
        contacts = await connector.get_contacts()
        if contacts is not None:
            print(f"Current contacts: {len(contacts)}")
            for contact in contacts:
                print(f"  - {contact.get('localDisplayName', 'Unknown')}")
        
        return True
    else:
        print("✗ Failed to connect to invitation")
        return False

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) != 2:
        print("Usage: python3 simplex_utils.py <invitation_url>")
        sys.exit(1)
    
    invitation_url = sys.argv[1]
    success = asyncio.run(connect_invitation_main(invitation_url))
    
    sys.exit(0 if success else 1)