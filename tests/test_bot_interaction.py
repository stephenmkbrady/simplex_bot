#!/usr/bin/env python3
"""
Test bot interaction by simulating actual user messages sent to the bot
"""

import asyncio
import json
import websockets
import time

async def test_bot_with_user_messages():
    """Send simulated user messages that the bot would actually receive"""
    uri = "ws://localhost:3030"
    
    test_commands = [
        "!debug ping",
        "!contacts list",
        "!groups list"
    ]
    
    try:
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to SimpleX CLI WebSocket")
            
            for cmd in test_commands:
                print(f"\n📤 Testing bot command: {cmd}")
                
                # Simulate the message format that SimpleX CLI would send when a user sends a message
                # This mimics what happens when NonpareilMagnitude sends a message to the bot
                corr_id = f"sim_{int(time.time())}"
                
                user_message = {
                    "corrId": corr_id,
                    "resp": {
                        "Right": {
                            "type": "newChatItem",
                            "user": {
                                "userId": 1,
                                "localDisplayName": "Bot"
                            },
                            "chatItem": {
                                "chatItemId": int(time.time()),
                                "itemTs": f"{time.time()}",
                                "itemContent": {
                                    "type": "rcvMsgContent",
                                    "msgContent": {
                                        "type": "text",
                                        "text": cmd
                                    }
                                },
                                "itemDeleted": False,
                                "itemEdited": False,
                                "itemTimed": None,
                                "itemLive": None
                            },
                            "chatInfo": {
                                "chatType": "direct",
                                "contactId": 4,
                                "localDisplayName": "NonpareilMagnitude",
                                "contact": {
                                    "contactId": 4,
                                    "localDisplayName": "NonpareilMagnitude",
                                    "profile": {
                                        "displayName": "NonpareilMagnitude",
                                        "fullName": ""
                                    },
                                    "activeConn": {
                                        "connStatus": "ready"
                                    },
                                    "contactUsed": True,
                                    "contactStatus": "active"
                                }
                            }
                        }
                    }
                }
                
                # Send the message
                await websocket.send(json.dumps(user_message))
                print(f"📤 Sent simulated user message: {cmd}")
                
                # Wait a bit for the bot to process and respond
                await asyncio.sleep(3)
                
                # Try to receive any responses (bot's replies)
                try:
                    while True:
                        response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                        resp_data = json.loads(response)
                        
                        # Check if this is a bot response (message from bot to user)
                        if 'resp' in resp_data and 'Right' in resp_data['resp']:
                            resp_content = resp_data['resp']['Right']
                            if resp_content.get('type') == 'newChatItem':
                                chat_item = resp_content.get('chatItem', {})
                                content = chat_item.get('itemContent', {})
                                if content.get('type') == 'sndMsgContent':
                                    msg_content = content.get('msgContent', {})
                                    if msg_content.get('type') == 'text':
                                        bot_reply = msg_content.get('text', '')
                                        print(f"🤖 Bot replied: {bot_reply[:100]}...")
                        
                except asyncio.TimeoutError:
                    print("⏰ No more responses received")
                
                print("---")
                
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_bot_with_user_messages())