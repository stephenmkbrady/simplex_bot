#!/usr/bin/env python3
"""
Test SimpleX CLI commands directly via WebSocket
"""

import asyncio
import json
import websockets
import time

async def test_cli_commands():
    """Test CLI commands directly"""
    uri = "ws://localhost:3030"
    
    # CLI commands to test
    test_commands = [
        "/help",
        "/contacts", 
        "/groups",
        "/c",
        "/g"
    ]
    
    try:
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to SimpleX CLI WebSocket")
            
            for cmd in test_commands:
                print(f"\n📤 Testing CLI command: {cmd}")
                
                # Create proper CLI command message
                corr_id = f"test_{int(time.time())}_{cmd.replace('/', '_')}"
                message = {
                    "corrId": corr_id,
                    "cmd": cmd
                }
                
                # Send command
                await websocket.send(json.dumps(message))
                print(f"📤 Sent: {json.dumps(message)}")
                
                # Wait for response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    print(f"📥 Response: {response[:500]}...")
                    
                    # Parse response
                    try:
                        resp_data = json.loads(response)
                        if 'resp' in resp_data:
                            if 'Right' in resp_data['resp']:
                                print("✅ Command succeeded!")
                            elif 'Left' in resp_data['resp']:
                                error = resp_data['resp']['Left']
                                print(f"❌ Command failed: {error}")
                    except json.JSONDecodeError:
                        print("⚠️ Non-JSON response received")
                        
                except asyncio.TimeoutError:
                    print(f"⏰ Command {cmd} timed out after 10 seconds")
                
                # Wait between commands
                await asyncio.sleep(1)
                
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_cli_commands())