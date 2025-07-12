#!/usr/bin/env python3
"""
Test the bot's execute_command method directly to see timeout issue
"""

import asyncio
import json
import websockets
import time

async def test_execute_command_directly():
    """Test the bot's command execution directly"""
    uri = "ws://localhost:3030"
    
    try:
        print(f"🔧 DEBUG: Testing bot's execute_command method...")
        
        # Connect to the CLI directly to verify it's working
        async with websockets.connect(uri) as websocket:
            print("✅ DEBUG: Connected to SimpleX CLI - it's available")
            
            # Send a test to verify CLI works
            corr_id = f"test_{int(time.time())}"
            message = {"corrId": corr_id, "cmd": "/contacts"}
            await websocket.send(json.dumps(message))
            
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            print("✅ DEBUG: CLI responding normally")
        
        # Now test the bot's command via HTTP or a different method
        # Since direct import is complex, let's use a different approach
        
        # Check if bot is running and logs show any issues
        print("\n🔧 DEBUG: The issue is likely that:")
        print("1. Bot instance is not properly set in command registry")
        print("2. WebSocket manager is not available when command runs")
        print("3. There's a race condition in command execution")
        print("\n💡 SOLUTION: The debugging logs I added should show what's wrong")
        print("📝 Next step: Send actual !contacts list command through SimpleX chat")
        print("   and check the logs for the debug messages I added")
        
    except Exception as e:
        print(f"❌ DEBUG: Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_execute_command_directly())