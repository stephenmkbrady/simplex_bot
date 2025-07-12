#!/usr/bin/env python3
"""
Test if there's an issue with the bot's specific WebSocket connection
"""

import asyncio
import json
import websockets
import time

async def test_bot_websocket_issue():
    """Test various scenarios that might affect the bot's WebSocket"""
    uri = "ws://localhost:3030"
    
    print("🔍 DEBUGGING: Bot's WebSocket connection issue")
    print("=" * 50)
    
    # Test 1: Check for correlation ID conflicts
    print("\n🧪 TEST 1: Correlation ID conflict test...")
    try:
        async with websockets.connect(uri) as ws:
            # Use a correlation ID format similar to what the bot uses
            bot_style_corr_id = f"bot_req_{int(time.time())}_999"
            message = {"corrId": bot_style_corr_id, "cmd": "/contacts"}
            
            start_time = time.time()
            await ws.send(json.dumps(message))
            
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                elapsed = time.time() - start_time
                print(f"✅ Bot-style correlation ID works: {elapsed:.3f}s")
            except asyncio.TimeoutError:
                print(f"❌ Bot-style correlation ID timed out")
                
    except Exception as e:
        print(f"❌ Correlation ID test failed: {e}")
    
    # Test 2: Send rapid commands like the bot might
    print(f"\n🧪 TEST 2: Rapid command sequence test...")
    try:
        async with websockets.connect(uri) as ws:
            # Send multiple commands rapidly without waiting for responses
            corr_ids = []
            for i in range(5):
                corr_id = f"rapid_bot_test_{int(time.time())}_{i}"
                corr_ids.append(corr_id)
                message = {"corrId": corr_id, "cmd": "/help"}
                await ws.send(json.dumps(message))
                await asyncio.sleep(0.1)  # Small delay like the bot might have
            
            # Now try to receive all responses
            responses_received = 0
            for i in range(5):
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    responses_received += 1
                except asyncio.TimeoutError:
                    break
            
            print(f"✅ Rapid commands: {responses_received}/5 responses received")
            
            # Now try the contacts command after rapid commands
            print(f"   Testing /contacts after rapid commands...")
            corr_id = f"post_rapid_contacts_{int(time.time())}"
            message = {"corrId": corr_id, "cmd": "/contacts"}
            await ws.send(json.dumps(message))
            
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                print(f"✅ /contacts works after rapid commands")
            except asyncio.TimeoutError:
                print(f"❌ /contacts timed out after rapid commands")
                
    except Exception as e:
        print(f"❌ Rapid command test failed: {e}")
    
    # Test 3: Check current bot connection state
    print(f"\n🧪 TEST 3: Bot connection health check...")
    
    # Since I can't directly access the bot's connection, let's try something else
    # Let's see if we can "heal" the bot's connection by restarting it
    print("💡 RECOMMENDATION: The bot's WebSocket connection might be in a bad state")
    print("🔧 SOLUTION: Try restarting the bot to get a fresh WebSocket connection")
    
    print(f"\n📊 CURRENT SITUATION:")
    print(f"- Bot's WebSocket (ID: 139656541470416) not responding to /contacts")
    print(f"- Fresh WebSocket connections work perfectly")
    print(f"- Bot can send commands but doesn't get responses")
    print(f"- This suggests a connection-specific issue")
    
    print(f"\n🎯 ROOT CAUSE HYPOTHESIS:")
    print(f"1. Bot's WebSocket connection is in a corrupted state")
    print(f"2. CLI might have stopped responding to this specific connection")
    print(f"3. There might be unprocessed messages in the connection queue")
    print(f"4. The correlation ID tracking might be out of sync")

if __name__ == "__main__":
    asyncio.run(test_bot_websocket_issue())