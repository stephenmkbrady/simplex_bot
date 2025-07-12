#!/usr/bin/env python3
"""
Debug the WebSocket connection issue - why does CLI respond to direct connections but not to bot's connection?
"""

import asyncio
import json
import websockets
import time

async def compare_websocket_connections():
    """Compare direct WebSocket vs bot's WebSocket behavior"""
    uri = "ws://localhost:3030"
    
    print("🔍 DEBUGGING: WebSocket connection differences")
    print("=" * 60)
    
    # Test 1: Direct connection (this works)
    print("\n🧪 TEST 1: Direct WebSocket connection (like my tests)...")
    try:
        async with websockets.connect(uri) as ws:
            corr_id = f"direct_test_{int(time.time())}"
            message = {"corrId": corr_id, "cmd": "/contacts"}
            
            start_time = time.time()
            await ws.send(json.dumps(message))
            
            response = await asyncio.wait_for(ws.recv(), timeout=10.0)
            elapsed = time.time() - start_time
            
            resp_data = json.loads(response)
            print(f"✅ Direct connection: Response in {elapsed:.3f}s")
            print(f"   Correlation ID: {resp_data.get('corrId')}")
            print(f"   Response type: {resp_data.get('resp', {}).get('Right', {}).get('type', 'unknown')}")
            
    except Exception as e:
        print(f"❌ Direct connection failed: {e}")
    
    # Test 2: Check if there are multiple connections
    print(f"\n🧪 TEST 2: Multiple connections test...")
    try:
        # Open two connections simultaneously
        async with websockets.connect(uri) as ws1, websockets.connect(uri) as ws2:
            print("✅ Two WebSocket connections opened simultaneously")
            
            # Send command on first connection
            corr_id1 = f"multi_test1_{int(time.time())}"
            message1 = {"corrId": corr_id1, "cmd": "/contacts"}
            await ws1.send(json.dumps(message1))
            
            # Send command on second connection
            corr_id2 = f"multi_test2_{int(time.time())}"
            message2 = {"corrId": corr_id2, "cmd": "/help"}
            await ws2.send(json.dumps(message2))
            
            # Try to receive from both
            try:
                resp1 = await asyncio.wait_for(ws1.recv(), timeout=5.0)
                print("✅ First connection got response")
            except asyncio.TimeoutError:
                print("❌ First connection timed out")
            
            try:
                resp2 = await asyncio.wait_for(ws2.recv(), timeout=5.0)
                print("✅ Second connection got response") 
            except asyncio.TimeoutError:
                print("❌ Second connection timed out")
                
    except Exception as e:
        print(f"❌ Multiple connections test failed: {e}")
    
    # Test 3: Check connection persistence
    print(f"\n🧪 TEST 3: Long-lived connection test...")
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Long-lived connection opened")
            
            # Send multiple commands over time
            for i in range(3):
                corr_id = f"persistent_test_{i}_{int(time.time())}"
                message = {"corrId": corr_id, "cmd": "/help"}
                
                start_time = time.time()
                await ws.send(json.dumps(message))
                
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    elapsed = time.time() - start_time
                    print(f"✅ Command {i+1}: Response in {elapsed:.3f}s")
                except asyncio.TimeoutError:
                    print(f"❌ Command {i+1}: Timed out")
                
                await asyncio.sleep(1)
                
    except Exception as e:
        print(f"❌ Long-lived connection test failed: {e}")
    
    print(f"\n🔍 ANALYSIS:")
    print(f"- Bot's WebSocket ID: 139656541470416 (from logs)")
    print(f"- Bot has been connected for a long time")
    print(f"- CLI might be rejecting commands from long-lived connections")
    print(f"- Or CLI might be in a state where it doesn't respond to certain connections")
    
    print(f"\n💡 POTENTIAL SOLUTIONS:")
    print(f"1. Bot should reconnect its WebSocket periodically")
    print(f"2. CLI might need to be restarted")
    print(f"3. There might be a message queue or correlation ID conflict")

if __name__ == "__main__":
    asyncio.run(compare_websocket_connections())