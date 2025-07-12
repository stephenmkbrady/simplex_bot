#!/usr/bin/env python3
"""
Debug the exact bot timeout issue by simulating the bot's command flow
"""

import asyncio
import json
import websockets
import time

class MockWebSocketManager:
    def __init__(self):
        self.websocket = None
        self.correlation_counter = 0
        self.pending_requests = {}
        
    def generate_correlation_id(self) -> str:
        """Generate a unique correlation ID for requests"""
        self.correlation_counter += 1
        return f"bot_req_{int(time.time())}_{self.correlation_counter}"

    async def send_command_with_debug(self, websocket, command: str) -> dict:
        """Send command exactly like the bot does with detailed logging"""
        print(f"🔧 DEBUG: Starting send_command for '{command}'")
        
        if not websocket:
            print("❌ No websocket connection")
            return None
        
        corr_id = self.generate_correlation_id()
        print(f"🔧 DEBUG: Generated correlation ID: {corr_id}")
        
        message = {
            "corrId": corr_id,
            "cmd": command
        }
        
        try:
            # Send the command
            await websocket.send(json.dumps(message))
            print(f"🔧 DEBUG: Command sent successfully")
            
            # Store the request for correlation (like the bot does)
            self.pending_requests[corr_id] = {"command": command, "timestamp": time.time()}
            print(f"🔧 DEBUG: Stored pending request for {corr_id}")
            
            # Wait for response with timeout (like the bot does)
            timeout = 30
            start_time = time.time()
            
            print(f"🔧 DEBUG: Starting wait loop for response...")
            
            response_received = False
            while corr_id in self.pending_requests:
                if time.time() - start_time > timeout:
                    print(f"⏰ DEBUG: Timeout reached after {timeout} seconds")
                    del self.pending_requests[corr_id]
                    return None
                
                # Check if response arrived by manually checking for it
                try:
                    raw_response = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                    print(f"🔧 DEBUG: Received raw response: {raw_response[:100]}...")
                    
                    # Parse the response
                    response_data = json.loads(raw_response)
                    response_corr_id = response_data.get("corrId")
                    
                    print(f"🔧 DEBUG: Response correlation ID: {response_corr_id}")
                    
                    if response_corr_id == corr_id:
                        print(f"✅ DEBUG: Correlation ID matches!")
                        # Store the response (like the bot does)
                        self.pending_requests[f"{corr_id}_response"] = response_data
                        # Remove the pending request
                        del self.pending_requests[corr_id]
                        response_received = True
                        break
                    else:
                        print(f"⚠️ DEBUG: Correlation ID mismatch - ignoring")
                        
                except asyncio.TimeoutError:
                    # No message received in 0.1 seconds, continue waiting
                    pass
                except Exception as e:
                    print(f"❌ DEBUG: Error receiving response: {e}")
                
                await asyncio.sleep(0.1)
            
            if response_received:
                # Get the stored response (like the bot does)
                response = self.pending_requests.get(f"{corr_id}_response")
                print(f"🔧 DEBUG: Retrieved stored response")
                return response
            else:
                print(f"❌ DEBUG: No response received")
                return None
                
        except Exception as e:
            print(f"❌ DEBUG: Exception in send_command: {type(e).__name__}: {e}")
            return None

async def debug_contacts_timeout():
    """Debug the exact timeout issue with !contacts list"""
    uri = "ws://localhost:3030"
    
    try:
        print(f"🔧 DEBUG: Connecting to {uri}...")
        
        mock_manager = MockWebSocketManager()
        
        async with websockets.connect(uri) as websocket:
            print("✅ DEBUG: Connected to SimpleX CLI WebSocket")
            
            # Test the exact flow the bot uses for !contacts list
            print(f"\n🔧 DEBUG: Testing bot's exact command flow for !contacts list")
            
            # This is what the bot does when it processes !contacts list
            response = await mock_manager.send_command_with_debug(websocket, "/contacts")
            
            if response:
                print(f"✅ DEBUG: Command succeeded!")
                print(f"🔧 DEBUG: Response type: {type(response)}")
                
                # Test the parsing like the bot does
                if isinstance(response, dict):
                    resp = response.get('resp', {})
                    if 'Right' in resp:
                        actual_resp = resp['Right']
                        if actual_resp.get('type') == 'contactsList':
                            contacts = actual_resp.get('contacts', [])
                            print(f"✅ DEBUG: Bot would parse {len(contacts)} contacts")
                        else:
                            print(f"⚠️ DEBUG: Unexpected response type: {actual_resp.get('type')}")
                    elif 'Left' in resp:
                        error = resp['Left']
                        print(f"❌ DEBUG: Bot would see error: {error}")
                    else:
                        print(f"⚠️ DEBUG: Unexpected response format")
            else:
                print(f"❌ DEBUG: Command failed/timed out!")
                
    except Exception as e:
        print(f"❌ DEBUG: Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_contacts_timeout())