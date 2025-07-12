#!/usr/bin/env python3
"""
Test WebSocket API connectivity with SimpleX CLI
"""

import asyncio
import json
import websockets
import time

async def test_websocket_commands():
    """Test various WebSocket commands to debug API issues"""
    uri = "ws://localhost:3030"
    
    # Commands to test (based on the bot's implementation)
    test_commands = [
        "/help",
        "/_get chats", 
        "/users",
        "/_info",
        "/connect"
    ]
    
    try:
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to SimpleX CLI WebSocket")
            
            for cmd in test_commands:
                print(f"\n📤 Testing command: {cmd}")
                
                # Create message with correlation ID
                corr_id = f"test_{int(time.time())}_{cmd.replace('/', '_')}"
                message = {
                    "corrId": corr_id,
                    "cmd": cmd
                }
                
                # Send command
                await websocket.send(json.dumps(message))
                print(f"📤 Sent: {json.dumps(message)}")
                
                # Wait for response with timeout
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    print(f"📥 Response: {response[:500]}...")
                    
                    # Parse and check for correlation ID match
                    try:
                        resp_data = json.loads(response)
                        resp_corr_id = resp_data.get("corrId")
                        if resp_corr_id == corr_id:
                            print(f"✅ Correlation ID matches: {resp_corr_id}")
                        else:
                            print(f"⚠️ Correlation ID mismatch: sent {corr_id}, got {resp_corr_id}")
                    except json.JSONDecodeError:
                        print("⚠️ Response is not valid JSON")
                        
                except asyncio.TimeoutError:
                    print(f"⏰ Command {cmd} timed out after 10 seconds")
                
                # Small delay between commands
                await asyncio.sleep(1)
                
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket_commands())