#!/usr/bin/env python3
"""
Test the bot's ACTUAL command processing, not just CLI connectivity
"""

import asyncio
import json
import websockets
import time

async def test_actual_bot_message_processing():
    """Test if the bot can actually process user messages and execute commands"""
    uri = "ws://localhost:3030"
    
    print("🔍 TESTING: Actual bot message processing (not just CLI)")
    print("=" * 60)
    
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Connected to SimpleX CLI WebSocket")
            
            # Try to find the exact message format that triggers bot processing
            # Based on the conversation history, let me try the format that actually works
            
            print(f"\n📤 Attempting to send a properly formatted user message...")
            
            # This should be the format that SimpleX CLI sends when a user sends a message
            user_message = {
                "corrId": "",  # No correlation ID for incoming messages
                "resp": {
                    "Right": {
                        "type": "newChatItem",
                        "user": {
                            "userId": 1,
                            "localDisplayName": "Bot"
                        },
                        "chatItem": {
                            "chatItemId": int(time.time()),
                            "itemTs": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
                            "itemContent": {
                                "type": "rcvMsgContent",
                                "msgContent": {
                                    "type": "text", 
                                    "text": "!contacts list"
                                }
                            },
                            "itemDeleted": False,
                            "itemEdited": False
                        },
                        "chatInfo": {
                            "chatType": "direct",
                            "contactId": 4,
                            "localDisplayName": "NonpareilMagnitude",
                            "contact": {
                                "contactId": 4,
                                "localDisplayName": "NonpareilMagnitude",
                                "profile": {
                                    "displayName": "NonpareilMagnitude"
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
            
            print(f"📤 Sending: {json.dumps(user_message)[:100]}...")
            await ws.send(json.dumps(user_message))
            
            print(f"⏰ Waiting to see if bot processes this as a user message...")
            
            # Wait and watch for any activity
            responses = []
            timeout = 30
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    responses.append(response)
                    
                    try:
                        resp_data = json.loads(response)
                        resp_type = resp_data.get('resp', {}).get('Right', {}).get('type', 'unknown')
                        print(f"📥 Received response type: {resp_type}")
                        
                        # Check if this looks like a bot reply
                        if resp_type == 'newChatItem':
                            chat_item = resp_data.get('resp', {}).get('Right', {}).get('chatItem', {})
                            content = chat_item.get('itemContent', {})
                            if content.get('type') == 'sndMsgContent':
                                msg_content = content.get('msgContent', {})
                                if msg_content.get('type') == 'text':
                                    bot_reply = msg_content.get('text', '')
                                    print(f"🤖 BOT REPLIED: {bot_reply}")
                                    if 'contacts' in bot_reply.lower() or 'bot contacts' in bot_reply.lower():
                                        print(f"✅ SUCCESS: Bot processed !contacts list command!")
                                        return True
                    
                    except json.JSONDecodeError:
                        print(f"📥 Non-JSON response")
                
                except asyncio.TimeoutError:
                    # Check if we should continue waiting
                    continue
            
            print(f"❌ Bot did not process the message as expected")
            print(f"📊 Received {len(responses)} responses total")
            
            # Let's also check if we can see ANY evidence of bot activity
            print(f"\n🔍 Testing: Can we see any bot command activity at all?")
            
            # Try sending a simple message that might trigger something
            simple_test = {
                "corrId": "",
                "resp": {
                    "Right": {
                        "type": "newChatItem", 
                        "chatItem": {
                            "itemContent": {
                                "type": "rcvMsgContent",
                                "msgContent": {
                                    "type": "text",
                                    "text": "!help"
                                }
                            }
                        },
                        "chatInfo": {
                            "chatType": "direct",
                            "localDisplayName": "NonpareilMagnitude"
                        }
                    }
                }
            }
            
            await ws.send(json.dumps(simple_test))
            
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                print(f"📥 Got response to !help test")
                return False  # At least something responded
            except asyncio.TimeoutError:
                print(f"❌ No response to !help either")
                return False
            
    except Exception as e:
        print(f"❌ Test failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 REALITY CHECK: Testing actual bot command processing")
    print("(Not just CLI connectivity)")
    print()
    
    success = asyncio.run(test_actual_bot_message_processing())
    
    if success:
        print(f"\n✅ Bot command processing IS working!")
    else:
        print(f"\n❌ Bot command processing is NOT working!")
        print(f"💡 The CLI works fine, but the bot isn't processing user messages")
        print(f"🔧 Need to debug the bot's message handling pipeline")