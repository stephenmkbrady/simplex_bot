#!/usr/bin/env python3
"""
Test the complete message flow that triggers !contacts list command
"""

import asyncio
import json
import websockets
import time

async def test_complete_message_flow():
    """Send a properly formatted user message to trigger the bot's command processing"""
    uri = "ws://localhost:3030"
    
    try:
        print(f"🧪 TEST: Connecting to {uri} to test complete message flow...")
        
        async with websockets.connect(uri) as websocket:
            print("✅ TEST: Connected to SimpleX CLI WebSocket")
            
            # Create a properly formatted user message that simulates receiving "!contacts list"
            # This should match the exact format the bot expects to receive from SimpleX CLI
            test_message = {
                "corrId": f"test_user_message_{int(time.time())}",
                "resp": {
                    "Right": {
                        "type": "newChatItem",
                        "user": {
                            "userId": 1,
                            "localDisplayName": "Bot"
                        },
                        "chatItem": {
                            "chatItemId": int(time.time()),
                            "itemTs": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
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
            
            print(f"📤 TEST: Sending user message: !contacts list")
            await websocket.send(json.dumps(test_message))
            
            print(f"⏰ TEST: Waiting for bot to process command and respond...")
            
            # Wait for responses and capture them
            responses_received = 0
            start_time = time.time()
            timeout = 35  # Slightly longer than bot's 30-second timeout
            
            while time.time() - start_time < timeout:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    responses_received += 1
                    
                    try:
                        resp_data = json.loads(response)
                        
                        # Check if this is a bot response (outgoing message)
                        if 'resp' in resp_data and 'Right' in resp_data['resp']:
                            resp_content = resp_data['resp']['Right']
                            
                            if resp_content.get('type') == 'newChatItem':
                                chat_item = resp_content.get('chatItem', {})
                                content = chat_item.get('itemContent', {})
                                
                                if content.get('type') == 'sndMsgContent':
                                    msg_content = content.get('msgContent', {})
                                    if msg_content.get('type') == 'text':
                                        bot_reply = msg_content.get('text', '')
                                        elapsed = time.time() - start_time
                                        print(f"🤖 TEST: Bot responded after {elapsed:.2f}s: {bot_reply[:100]}...")
                                        
                                        if "contacts" in bot_reply.lower():
                                            print(f"✅ TEST: SUCCESS! Contacts command responded")
                                            return True
                                        elif "websocket manager not available" in bot_reply.lower():
                                            print(f"❌ TEST: Bot reports WebSocket manager not available")
                                            return False
                                        elif "error" in bot_reply.lower():
                                            print(f"❌ TEST: Bot reported error: {bot_reply}")
                                            return False
                        
                        # Also check for error responses
                        elif 'resp' in resp_data and 'Left' in resp_data['resp']:
                            error = resp_data['resp']['Left']
                            print(f"❌ TEST: CLI error response: {error}")
                    
                    except json.JSONDecodeError:
                        print(f"⚠️ TEST: Non-JSON response received")
                    
                except asyncio.TimeoutError:
                    # No response in 2 seconds, continue waiting
                    elapsed = time.time() - start_time
                    if elapsed > 10:  # Log progress every 10 seconds
                        print(f"⏰ TEST: Still waiting... {elapsed:.1f}s elapsed, {responses_received} responses received")
            
            elapsed = time.time() - start_time
            print(f"❌ TEST: TIMEOUT! Command did not respond within {timeout} seconds")
            print(f"📊 TEST: Total time elapsed: {elapsed:.2f}s")
            print(f"📊 TEST: Responses received: {responses_received}")
            return False
                
    except Exception as e:
        print(f"❌ TEST: Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

async def run_comprehensive_tests():
    """Run comprehensive tests including the message flow"""
    print("🧪 STARTING COMPREHENSIVE TESTS")
    print("=" * 50)
    
    # Test 1: Verify CLI is working
    print("\n🧪 TEST 1: Verify CLI connectivity...")
    try:
        async with websockets.connect("ws://localhost:3030") as ws:
            await ws.send(json.dumps({"corrId": "test", "cmd": "/help"}))
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print("✅ TEST 1: CLI is responding")
    except Exception as e:
        print(f"❌ TEST 1: CLI connectivity failed: {e}")
        return
    
    # Test 2: Test the complete message flow
    print("\n🧪 TEST 2: Testing complete !contacts list message flow...")
    success = await test_complete_message_flow()
    
    if success:
        print("\n✅ ALL TESTS PASSED: !contacts list command is working")
    else:
        print("\n❌ TEST FAILED: !contacts list command timed out")
        print("\n🔍 NEXT STEPS:")
        print("1. Check bot logs for debug messages I added")
        print("2. Look for 'CONTACTS DEBUG' messages in the logs")
        print("3. Check if bot_instance and websocket_manager are available")

if __name__ == "__main__":
    asyncio.run(run_comprehensive_tests())