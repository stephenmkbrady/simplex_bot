#!/usr/bin/env python3
"""
Test the bot's command functionality by simulating WebSocket messages
"""

import asyncio
import json
import websockets
import time

async def test_bot_commands():
    """Test the bot commands by sending simulated user messages"""
    uri = "ws://localhost:3030"
    admin_user = "NonpareilMagnitude"
    
    # Commands to test
    test_messages = [
        "!debug ping",
        "!contacts list", 
        "!groups list",
        "!help"
    ]
    
    try:
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to SimpleX CLI WebSocket")
            
            for msg in test_messages:
                print(f"\n📤 Testing command: {msg}")
                
                # Create a simulated user message that the bot would receive
                # This simulates what SimpleX CLI sends when a user sends a message
                corr_id = f"test_{int(time.time())}_{msg.replace(' ', '_')}"
                
                # Simulate the message format that SimpleX CLI uses for incoming messages
                simulated_message = {
                    "corrId": corr_id,
                    "resp": {
                        "Right": {
                            "type": "newChatItem",
                            "chatItem": {
                                "content": {
                                    "msgContent": {
                                        "type": "text",
                                        "text": msg
                                    }
                                }
                            },
                            "chatInfo": {
                                "chatType": "direct",
                                "localDisplayName": admin_user
                            }
                        }
                    }
                }
                
                # Send the simulated message
                await websocket.send(json.dumps(simulated_message))
                print(f"📤 Sent simulated message: {msg}")
                
                # Wait for any responses
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    print(f"📥 Response received: {response[:200]}...")
                except asyncio.TimeoutError:
                    print("⏰ No immediate response received")
                
                # Wait between commands
                await asyncio.sleep(2)
                
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_bot_commands())