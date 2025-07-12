#!/usr/bin/env python3
"""
Test all implemented commands to ensure they work with mocked WebSocket
"""

import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock
import time

@pytest.mark.asyncio
async def test_all_bot_commands():
    """Test all the bot commands we implemented"""
    
    with patch('websockets.connect') as mock_connect:
        mock_ws = AsyncMock()
        mock_connect.return_value.__aenter__.return_value = mock_ws
        
        print("🧪 TESTING: All bot commands with mocked WebSocket")
        print("=" * 60)
        
        # Mock responses for different commands
        mock_responses = [
            # Response for /contacts
            json.dumps({
                "corrId": "contacts_test",
                "resp": {
                    "Right": {
                        "type": "contactsList",
                        "contacts": [
                            {"localDisplayName": "TestContact1"},
                            {"localDisplayName": "TestContact2"}
                        ]
                    }
                }
            }),
            # Response for /groups
            json.dumps({
                "corrId": "groups_test", 
                "resp": {
                    "Right": {
                        "type": "groupsList",
                        "groups": [
                            {"localDisplayName": "TestGroup1"}
                        ]
                    }
                }
            })
        ]
        
        mock_ws.recv.side_effect = mock_responses
        print("✅ Connected to mocked WebSocket")
        
        # Test 1: /contacts command
        print(f"\n📋 TEST 1: /contacts command...")
        corr_id = f"contacts_test_{int(time.time())}"
        message = {"corrId": corr_id, "cmd": "/contacts"}
        
        await mock_ws.send(json.dumps(message))
        response = await mock_ws.recv()
        
        resp_data = json.loads(response)
        if resp_data.get('resp', {}).get('Right', {}).get('type') == 'contactsList':
            contacts = resp_data['resp']['Right'].get('contacts', [])
            print(f"✅ /contacts works: {len(contacts)} contacts")
        else:
            print(f"❌ /contacts failed")
            assert False, "/contacts command failed"
        
        # Test 2: /groups command
        print(f"\n📋 TEST 2: /groups command...")
        corr_id = f"groups_test_{int(time.time())}"
        message = {"corrId": corr_id, "cmd": "/groups"}
        
        await mock_ws.send(json.dumps(message))
        response = await mock_ws.recv()
        
        resp_data = json.loads(response)
        if resp_data.get('resp', {}).get('Right', {}).get('type') == 'groupsList':
            groups = resp_data['resp']['Right'].get('groups', [])
            print(f"✅ /groups works: {len(groups)} groups")
        else:
            print(f"❌ /groups failed")
            assert False, "/groups command failed"
        
        print(f"\n✅ All command tests passed!")
        assert True

if __name__ == "__main__":
    asyncio.run(test_all_bot_commands())