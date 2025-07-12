#!/usr/bin/env python3
"""
Test to find the difference between working and failing WebSocket connections
"""

import asyncio
import json
import websockets
import time

async def test_fresh_connection():
    """Test fresh connection like my working tests"""
    print("🧪 TEST 1: Fresh connection (like my working tests)")
    print("=" * 50)
    
    async with websockets.connect('ws://localhost:3030') as ws:
        print('✅ Connected to WebSocket')
        
        # Check for initial messages
        initial_messages = []
        print('🔍 Checking for initial messages...')
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                data = json.loads(msg)
                msg_type = data.get('resp', {}).get('Right', {}).get('type', 'unknown')
                initial_messages.append(msg_type)
                print(f'   📥 Initial message: {msg_type}')
        except asyncio.TimeoutError:
            print(f'📊 Received {len(initial_messages)} initial messages')
        
        # Send contacts command
        print('\n📤 Sending /contacts command...')
        corr_id = f'fresh_test_{int(time.time())}'
        await ws.send(json.dumps({'corrId': corr_id, 'cmd': '/contacts'}))
        
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=10.0)
            resp_data = json.loads(resp)
            resp_type = resp_data.get('resp', {}).get('Right', {}).get('type', 'unknown')
            resp_corr_id = resp_data.get('corrId', '')
            
            if resp_type == 'contactsList':
                contacts = resp_data.get('resp', {}).get('Right', {}).get('contacts', [])
                print(f'✅ SUCCESS: Got {len(contacts)} contacts:')
                for i, contact in enumerate(contacts, 1):
                    name = contact.get('localDisplayName', 'Unknown')
                    status = contact.get('contactStatus', 'unknown')
                    print(f'   {i}. {name} ({status})')
            else:
                print(f'✅ SUCCESS: Got response type={resp_type}, corrId={resp_corr_id}')
            return True
        except asyncio.TimeoutError:
            print('❌ TIMEOUT: No response')
            return False

async def test_bot_like_connection():
    """Test connection that mimics the bot's behavior"""
    print("\n🤖 TEST 2: Bot-like connection (persistent with message listening)")
    print("=" * 60)
    
    async with websockets.connect('ws://localhost:3030') as ws:
        print('✅ Connected to WebSocket')
        
        # Simulate bot's message listening behavior
        print('🔊 Starting message listener (like the bot)...')
        
        async def message_listener():
            messages = []
            try:
                async for message in ws:
                    data = json.loads(message)
                    msg_type = data.get('resp', {}).get('Right', {}).get('type', 'unknown')
                    corr_id = data.get('corrId', 'None')
                    messages.append((msg_type, corr_id))
                    print(f'   👂 Listener received: type={msg_type}, corrId={corr_id}')
                    
                    # Stop after we get some messages or a command response
                    if len(messages) >= 10 or corr_id.startswith('bot_like_test'):
                        break
            except Exception as e:
                print(f'   👂 Listener error: {e}')
            return messages
        
        # Start listener task
        listener_task = asyncio.create_task(message_listener())
        
        # Wait a moment like the bot does
        await asyncio.sleep(1.0)
        
        # Send contacts command while listener is running
        print('\n📤 Sending /contacts command while listener is active...')
        corr_id = f'bot_like_test_{int(time.time())}'
        await ws.send(json.dumps({'corrId': corr_id, 'cmd': '/contacts'}))
        
        # Wait for listener to finish or timeout
        try:
            messages = await asyncio.wait_for(listener_task, timeout=15.0)
            
            # Check if we got our response
            found_response = False
            for msg_type, msg_corr_id in messages:
                if msg_corr_id == corr_id:
                    print(f'✅ SUCCESS: Found response type={msg_type}, corrId={msg_corr_id}')
                    found_response = True
                    break
            
            if not found_response:
                print(f'❌ FAILURE: No response found for corrId={corr_id}')
                print(f'📊 Received {len(messages)} total messages:')
                for i, (msg_type, msg_corr_id) in enumerate(messages, 1):
                    print(f'   {i}. type={msg_type}, corrId={msg_corr_id}')
                return False
            
            return True
            
        except asyncio.TimeoutError:
            print('❌ TIMEOUT: Listener timed out')
            listener_task.cancel()
            return False

async def test_exact_bot_scenario():
    """Test the exact scenario that fails in the bot"""
    print("\n🔍 TEST 3: Exact bot failure scenario")
    print("=" * 40)
    
    # Connect and wait for initial system messages like the bot
    async with websockets.connect('ws://localhost:3030') as ws:
        print('✅ Connected to WebSocket')
        
        # Receive initial system messages (like bot startup)
        print('📥 Waiting for initial system messages...')
        system_messages = []
        start_time = time.time()
        
        while time.time() - start_time < 3.0:  # Wait up to 3 seconds
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                data = json.loads(msg)
                msg_type = data.get('resp', {}).get('Right', {}).get('type', 'unknown')
                system_messages.append(msg_type)
                print(f'   📨 System message: {msg_type}')
            except asyncio.TimeoutError:
                break
        
        print(f'📊 Received {len(system_messages)} system messages')
        
        # Now send contacts command exactly like the bot
        print('\n📤 Sending /contacts command exactly like the bot...')
        corr_id = f'bot_req_{int(time.time())}_1'
        message = {"corrId": corr_id, "cmd": "/contacts"}
        
        await ws.send(json.dumps(message))
        print(f'📤 Sent command with corrId: {corr_id}')
        
        # Wait for response with timeout
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=35.0)  # Longer than bot's 30s
            resp_data = json.loads(resp)
            resp_type = resp_data.get('resp', {}).get('Right', {}).get('type', 'unknown')
            resp_corr_id = resp_data.get('corrId', '')
            
            if resp_corr_id == corr_id:
                if resp_type == 'contactsList':
                    contacts = resp_data.get('resp', {}).get('Right', {}).get('contacts', [])
                    print(f'✅ SUCCESS: Got {len(contacts)} contacts:')
                    for i, contact in enumerate(contacts, 1):
                        name = contact.get('localDisplayName', 'Unknown')
                        status = contact.get('contactStatus', 'unknown')
                        print(f'   {i}. {name} ({status})')
                else:
                    print(f'✅ SUCCESS: Got response type={resp_type}, corrId={resp_corr_id}')
                return True
            else:
                print(f'❌ WRONG RESPONSE: Expected corrId={corr_id}, got={resp_corr_id}')
                return False
                
        except asyncio.TimeoutError:
            print('❌ TIMEOUT: No response after 35 seconds (bot times out at 30s)')
            return False

async def main():
    """Run all tests to find the difference"""
    print("🔬 WEBSOCKET DIFFERENCE INVESTIGATION")
    print("=" * 50)
    print("Finding why /contacts works in isolated tests but fails in the bot")
    print()
    
    results = {}
    
    # Test 1: Fresh connection
    results['fresh'] = await test_fresh_connection()
    
    # Test 2: Bot-like connection
    results['bot_like'] = await test_bot_like_connection()
    
    # Test 3: Exact bot scenario
    results['exact_bot'] = await test_exact_bot_scenario()
    
    # Summary
    print("\n" + "=" * 60)
    print("🏁 FINAL RESULTS:")
    print("=" * 60)
    
    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name.replace('_', ' ').title()}")
    
    print("\n🔍 ANALYSIS:")
    if results['fresh'] and not results['exact_bot']:
        print("❗ Fresh connections work but bot scenario fails")
        print("❗ This confirms there's a difference in connection behavior")
    elif all(results.values()):
        print("✅ All tests pass - the issue might be elsewhere")
    else:
        print("❌ Multiple test failures - need deeper investigation")

if __name__ == "__main__":
    asyncio.run(main())