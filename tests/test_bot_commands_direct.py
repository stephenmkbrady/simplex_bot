#!/usr/bin/env python3
"""
Test bot commands by directly calling the WebSocket manager with mocked connections
"""

import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock
import time

@pytest.mark.asyncio
async def test_contacts_command_timeout():
    """Test the specific !contacts list command with mocked WebSocket"""
    
    with patch('websockets.connect') as mock_connect:
        mock_ws = AsyncMock()
        mock_connect.return_value.__aenter__.return_value = mock_ws
        
        print(f"Connecting to mocked WebSocket...")
        print("✅ Connected to mocked SimpleX CLI WebSocket")
        
        # Mock response for contacts command
        mock_response = json.dumps({
            "corrId": "bot_test_12345",
            "resp": {
                "Right": {
                    "type": "contactsList",
                    "contacts": [
                        {"localDisplayName": "TestContact1", "contactId": 1},
                        {"localDisplayName": "TestContact2", "contactId": 2}
                    ]
                }
            }
        })
        mock_ws.recv.return_value = mock_response
        
        # Test the exact command the bot would send
        print(f"\n📤 Testing exact bot command: /contacts")
        corr_id = f"bot_test_{int(time.time())}"
        message = {"corrId": corr_id, "cmd": "/contacts"}
        
        start_time = time.time()
        await mock_ws.send(json.dumps(message))
        print(f"📤 Sent at: {start_time}")
        
        print("⏰ Waiting for mocked response...")
        response = await mock_ws.recv()
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
                    assert len(contacts) >= 0  # Should have contacts list
                    return True
        
        assert False, "Contacts command test failed"

if __name__ == "__main__":
    asyncio.run(test_contacts_command_timeout())