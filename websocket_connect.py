#!/usr/bin/env python3

import asyncio
import websockets
import json
import sys

async def connect_to_simplex(invitation_url):
    """Connect to SimpleX Chat via WebSocket and send connection command"""
    
    uri = "ws://localhost:3030"
    
    try:
        print(f"Connecting to SimpleX Chat WebSocket at {uri}...")
        
        async with websockets.connect(uri) as websocket:
            print("✓ Connected to SimpleX Chat WebSocket")
            
            # Send connect command
            connect_command = {
                "corrId": "1",
                "cmd": f"/connect {invitation_url}"
            }
            
            print(f"Sending connect command: {connect_command}")
            await websocket.send(json.dumps(connect_command))
            
            # Wait for response
            print("Waiting for response...")
            response = await asyncio.wait_for(websocket.recv(), timeout=30)
            print(f"Response: {response}")
            
            # Send contacts command to check if connection worked
            contacts_command = {
                "corrId": "2", 
                "cmd": "/contacts"
            }
            
            print(f"Sending contacts command: {contacts_command}")
            await websocket.send(json.dumps(contacts_command))
            
            # Wait for contacts response
            contacts_response = await asyncio.wait_for(websocket.recv(), timeout=10)
            print(f"Contacts response: {contacts_response}")
            
    except websockets.exceptions.ConnectionRefused:
        print("✗ Failed to connect to SimpleX Chat WebSocket - connection refused")
        return False
    except asyncio.TimeoutError:
        print("✗ Timeout waiting for response from SimpleX Chat")
        return False
    except Exception as e:
        print(f"✗ Error connecting to SimpleX Chat: {e}")
        return False
    
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 websocket_connect.py <invitation_url>")
        sys.exit(1)
    
    invitation_url = sys.argv[1]
    print(f"Attempting to connect to invitation: {invitation_url}")
    
    success = asyncio.run(connect_to_simplex(invitation_url))
    
    if success:
        print("✓ Connection attempt completed successfully")
    else:
        print("✗ Connection attempt failed")
        sys.exit(1)