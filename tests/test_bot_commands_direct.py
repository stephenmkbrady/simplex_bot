#!/usr/bin/env python3
"""
Test bot commands by directly calling the WebSocket manager with timeouts
"""

import asyncio
import json
import websockets
import time

async def test_contacts_command_timeout():
    """Test the specific !contacts list command that's timing out"""
    uri = "ws://localhost:3030"
    
    try:
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to SimpleX CLI WebSocket")
            
            # Test the exact command the bot would send
            print(f"\n📤 Testing exact bot command: /contacts")
            corr_id = f"bot_test_{int(time.time())}"
            message = {"corrId": corr_id, "cmd": "/contacts"}
            
            start_time = time.time()
            await websocket.send(json.dumps(message))
            print(f"📤 Sent at: {start_time}")
            
            try:
                # Test with different timeout values
                print("⏰ Waiting for response (30 second timeout)...")
                response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                end_time = time.time()
                
                print(f"✅ Response received after {end_time - start_time:.2f} seconds")
                
                # Parse response
                resp_data = json.loads(response)
                print(f"📥 Response correlation ID: {resp_data.get('corrId')}")
                
                if 'resp' in resp_data:
                    if 'Right' in resp_data['resp']:
                        actual_resp = resp_data['resp']['Right']
                        resp_type = actual_resp.get('type', 'unknown')
                        print(f"✅ Success response type: {resp_type}")
                        
                        if resp_type == 'contactsList':
                            contacts = actual_resp.get('contacts', [])
                            print(f"✅ Found {len(contacts)} contacts")
                        
                    elif 'Left' in resp_data['resp']:
                        error = resp_data['resp']['Left']
                        print(f"❌ Error response: {error}")
                        
            except asyncio.TimeoutError:
                end_time = time.time()
                print(f"❌ Command timed out after {end_time - start_time:.2f} seconds")
                
                # Try to see if there are any pending messages
                try:
                    print("🔍 Checking for delayed responses...")
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    print(f"📥 Delayed response received: {response[:100]}...")
                except asyncio.TimeoutError:
                    print("🔍 No delayed responses")
            
            # Test multiple rapid commands to see if there's a queue issue
            print(f"\n📤 Testing rapid commands...")
            for i in range(3):
                corr_id = f"rapid_test_{i}_{int(time.time())}"
                message = {"corrId": corr_id, "cmd": "/help"}
                await websocket.send(json.dumps(message))
                print(f"📤 Sent rapid command {i+1}")
                
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    resp_data = json.loads(response)
                    print(f"✅ Rapid command {i+1} responded: {resp_data.get('corrId')}")
                except asyncio.TimeoutError:
                    print(f"❌ Rapid command {i+1} timed out")
                
                await asyncio.sleep(0.5)
                
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_contacts_command_timeout())