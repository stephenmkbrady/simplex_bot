#!/usr/bin/env python3
"""
Get detailed structure of contacts and groups responses
"""

import asyncio
import json
import websockets
import time

async def get_detailed_responses():
    """Get full responses to understand data structure"""
    uri = "ws://localhost:3030"
    
    try:
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to SimpleX CLI WebSocket")
            
            # Test /contacts command
            print(f"\n📤 Testing /contacts command...")
            corr_id = f"test_contacts_{int(time.time())}"
            message = {"corrId": corr_id, "cmd": "/contacts"}
            
            await websocket.send(json.dumps(message))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                resp_data = json.loads(response)
                
                print("Full /contacts response:")
                print(json.dumps(resp_data, indent=2))
                
                # Extract contacts data structure
                if 'resp' in resp_data and 'Right' in resp_data['resp']:
                    contacts_list = resp_data['resp']['Right']
                    if 'contacts' in contacts_list:
                        contacts = contacts_list['contacts']
                        print(f"\nFound {len(contacts)} contacts:")
                        for i, contact in enumerate(contacts):
                            print(f"Contact {i+1}: {json.dumps(contact, indent=2)}")
                            break  # Just show first contact structure
                    
            except Exception as e:
                print(f"Error with /contacts: {e}")
                
            await asyncio.sleep(1)
            
            # Test /groups command  
            print(f"\n📤 Testing /groups command...")
            corr_id = f"test_groups_{int(time.time())}"
            message = {"corrId": corr_id, "cmd": "/groups"}
            
            await websocket.send(json.dumps(message))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                resp_data = json.loads(response)
                
                print("Full /groups response:")
                print(json.dumps(resp_data, indent=2))
                
            except Exception as e:
                print(f"Error with /groups: {e}")
                
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(get_detailed_responses())