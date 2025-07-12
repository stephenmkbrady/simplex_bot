#!/usr/bin/env python3
"""
WebSocket Manager for SimpleX Bot
Handles all WebSocket communication with SimpleX Chat CLI
"""

import asyncio
import json
import logging
import time
import websockets
from typing import Dict, Any, Optional, Callable

# Constants
DEFAULT_MAX_RETRIES = 30
DEFAULT_RETRY_DELAY = 2


class WebSocketError(Exception):
    """WebSocket connection and communication errors"""
    pass


class WebSocketManager:
    """Manages WebSocket connections and communication with SimpleX Chat CLI"""
    
    def __init__(self, websocket_url: str, logger: logging.Logger):
        self.websocket_url = websocket_url
        self.logger = logger
        
        # Connection state
        self.websocket = None
        self.running = False
        self.correlation_counter = 0
        self.pending_requests: Dict[str, Any] = {}
        
        # Callbacks for message handling
        self.message_handlers: Dict[str, Callable] = {}
        
        # User message flow monitoring
        self.last_user_message_time = time.time()
        self.user_message_count = 0
        self.system_message_count = 0
        self.cli_corruption_detected = False
        self.cli_restart_needed = False
        
        # Pending invite message storage
        self.pending_invite_message = None
        
        # Command response callbacks
        self.command_callbacks = {}
    
    def register_message_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for specific message types"""
        self.message_handlers[message_type] = handler
        self.logger.debug(f"Registered handler for message type: {message_type}")
    
    def register_command_callback(self, command: str, callback: Callable) -> None:
        """Register a callback for command responses"""
        self.command_callbacks[command] = callback
        self.logger.debug(f"Registered callback for command: {command}")
    
    async def _handle_contacts_response(self, response_data: Dict) -> None:
        """Handle contactsList response and trigger callback"""
        try:
            self.logger.info(f"🔔 CONTACTS HANDLER: Starting contacts response handler")
            if '/contacts' in self.command_callbacks:
                callback = self.command_callbacks['/contacts']
                self.logger.info(f"🔔 CONTACTS HANDLER: Found callback, executing...")
                await callback(response_data)
                self.logger.info(f"🔔 CONTACTS HANDLER: Callback completed successfully")
            else:
                self.logger.warning("🔔 CONTACTS HANDLER: No callback registered for /contacts command")
        except Exception as e:
            self.logger.error(f"🔔 CONTACTS HANDLER ERROR: {type(e).__name__}: {e}")
            import traceback
            self.logger.error(f"🔔 CONTACTS HANDLER TRACEBACK: {traceback.format_exc()}")
    
    async def _handle_groups_response(self, response_data: Dict) -> None:
        """Handle groupsList response and trigger callback"""
        try:
            self.logger.info(f"🔔 GROUPS HANDLER: Starting groups response handler")
            if '/groups' in self.command_callbacks:
                callback = self.command_callbacks['/groups']
                self.logger.info(f"🔔 GROUPS HANDLER: Found callback, executing...")
                await callback(response_data)
                self.logger.info(f"🔔 GROUPS HANDLER: Callback completed successfully")
            else:
                self.logger.warning("🔔 GROUPS HANDLER: No callback registered for /groups command")
        except Exception as e:
            self.logger.error(f"🔔 GROUPS HANDLER ERROR: {type(e).__name__}: {e}")
            import traceback
            self.logger.error(f"🔔 GROUPS HANDLER TRACEBACK: {traceback.format_exc()}")
    
    def generate_correlation_id(self) -> str:
        """Generate a unique correlation ID for requests"""
        self.correlation_counter += 1
        return f"bot_req_{int(time.time())}_{self.correlation_counter}"
    
    async def connect(self, max_retries: int = DEFAULT_MAX_RETRIES, retry_delay: int = DEFAULT_RETRY_DELAY) -> bool:
        """Connect to the SimpleX Chat CLI WebSocket server with retries"""
        old_websocket_id = id(self.websocket) if self.websocket else None
        self.logger.info(f"🔌 CONNECT START: Current WebSocket ID: {old_websocket_id}")
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"🔌 ATTEMPT {attempt + 1}/{max_retries}: Connecting to {self.websocket_url}")
                
                # Close old connection if exists
                if self.websocket:
                    self.logger.info(f"🔌 CLEANUP: Closing old WebSocket {id(self.websocket)}")
                    try:
                        await self.websocket.close()
                    except Exception as cleanup_error:
                        self.logger.warning(f"🔌 CLEANUP ERROR: {cleanup_error}")
                
                # Create new connection
                self.websocket = await websockets.connect(self.websocket_url)
                new_websocket_id = id(self.websocket)
                self.logger.info(f"🔌 SUCCESS: Created WebSocket {new_websocket_id} (was {old_websocket_id})")
                # Note: websockets ClientConnection doesn't have .closed attribute 
                self.logger.info(f"🔌 STATE: WebSocket connected={self.websocket is not None}, type={type(self.websocket).__name__}")
                
                # Log successful reconnection
                if hasattr(self, '_restart_listener') and self._restart_listener:
                    self.logger.info(f"🔌 INVITE RECOVERY: WebSocket {new_websocket_id} reconnected after invite generation")
                    self._restart_listener = False
                
                # Check for pending invite message to send after reconnection
                if self.pending_invite_message:
                    self.logger.info("🎫 PENDING MESSAGE: Found pending invite message, scheduling delivery...")
                    # Schedule the message to be sent after connection is fully established
                    asyncio.create_task(self._send_pending_invite_message())
                    
                return True
                
            except Exception as e:
                self.logger.error(f"🔌 EXCEPTION in connect attempt {attempt + 1}: {type(e).__name__}: {e}")
                import traceback
                self.logger.error(f"🔌 TRACEBACK: {traceback.format_exc()}")
                
                if attempt < max_retries - 1:
                    self.logger.warning(f"🔌 RETRY: Attempt {attempt + 1} failed, retrying in {retry_delay}s")
                    await asyncio.sleep(retry_delay)
                else:
                    self.logger.error(f"🔌 FAILED: All {max_retries} connection attempts failed")
                    return False
        
        self.logger.error(f"🔌 FAILED: Connection failed after all attempts")
        return False
    
    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server"""
        websocket_id = id(self.websocket) if self.websocket else None
        self.logger.info(f"🔌 DISCONNECT START: WebSocket ID: {websocket_id}")
        
        if self.websocket:
            try:
                # Mark that we need to restart the listener when reconnecting
                self._restart_listener = True
                self.logger.info(f"🔌 CLOSING: WebSocket {websocket_id}")
                await self.websocket.close()
                self.logger.info(f"🔌 CLOSED: WebSocket {websocket_id} successfully closed")
                
                self.websocket = None
                self.logger.info(f"🔌 DISCONNECT COMPLETE: WebSocket reference cleared")
                
            except Exception as e:
                self.logger.error(f"🔌 DISCONNECT EXCEPTION: {type(e).__name__}: {e}")
                import traceback
                self.logger.error(f"🔌 DISCONNECT TRACEBACK: {traceback.format_exc()}")
                self.websocket = None  # Clear reference even on error
        else:
            self.logger.info("🔌 DISCONNECT: No WebSocket to disconnect")
    
    async def send_command(self, command: str, wait_for_response: bool = False) -> Optional[Dict]:
        """
        Send a command to SimpleX Chat CLI
        
        Args:
            command: The command to send
            wait_for_response: Whether to wait for and return the response
            
        Returns:
            Response dict if wait_for_response is True, None otherwise
        """
        websocket_id = id(self.websocket) if self.websocket else None
        self.logger.info(f"📤 COMMAND: Sending '{command}' via WebSocket {websocket_id}")
        
        if not self.websocket:
            self.logger.error("📤 ERROR: Not connected to SimpleX Chat CLI")
            return None
        
        corr_id = self.generate_correlation_id()
        
        message = {
            "corrId": corr_id,
            "cmd": command
        }
        
        try:
            # Debug: Log WebSocket state before sending
            self.logger.info(f"🔍 WS DEBUG: About to send command on WebSocket {id(self.websocket)}")
            self.logger.info(f"🔍 WS DEBUG: WebSocket state - connected: {self.websocket is not None}")
            
            # Log the exact message being sent
            self.logger.info(f"🔍 RAW SEND: {json.dumps(message)}")
            
            await self.websocket.send(json.dumps(message))
            self.logger.info(f"📤 SENT: Command '{command}' sent successfully (corr_id: {corr_id})")
            self.logger.info(f"🔍 WS DEBUG: Send completed without exceptions")
            
            if wait_for_response:
                # Store the request for correlation - response will be handled by _handle_response
                self.pending_requests[corr_id] = {"command": command, "timestamp": time.time()}
                self.logger.info(f"📤 NO-BLOCK SETUP: Stored pending request '{corr_id}' for async response")
                self.logger.info(f"📤 NO-BLOCK SETUP: Response will be handled by message listener")
                # Don't wait or block - let the message listener handle the response via _handle_response
                return None
                
        except (websockets.ConnectionClosed, TypeError) as e:
            self.logger.error(f"📤 WEBSOCKET ERROR: {type(e).__name__}: {e}")
            raise WebSocketError(f"WebSocket communication error: {e}")
        except Exception as e:
            self.logger.error(f"📤 SEND ERROR: Failed to send command '{command}': {type(e).__name__}: {e}")
            import traceback
            self.logger.error(f"📤 SEND TRACEBACK: {traceback.format_exc()}")
            return None
    
    async def send_message(self, contact_name: str, message: str) -> None:
        """Send a message to a specific contact, splitting long messages"""
        websocket_id = id(self.websocket) if self.websocket else None
        self.logger.info(f"📤 SEND START: Sending to {contact_name} via WebSocket {websocket_id}")
        self.logger.info(f"📤 SEND MESSAGE CONTENT: {message[:100]}...")
        
        # Security configuration - these could be passed in constructor
        MAX_MESSAGE_LENGTH = 4096
        
        if len(message) > MAX_MESSAGE_LENGTH:
            self.logger.info(f"Message too long ({len(message)} chars), splitting into multiple messages")
            
            # Split message intelligently
            chunks = self._split_message_smartly(message, MAX_MESSAGE_LENGTH)
            
            for i, chunk in enumerate(chunks):
                if len(chunks) > 1:
                    # Add part indicator for multi-part messages
                    if i == 0:
                        chunk_message = f"{chunk}\n\n--- (Part {i+1}/{len(chunks)}) ---"
                    elif i == len(chunks) - 1:
                        chunk_message = f"--- (Part {i+1}/{len(chunks)}) ---\n\n{chunk}"
                    else:
                        chunk_message = f"--- (Part {i+1}/{len(chunks)}) ---\n\n{chunk}\n\n--- (continues...) ---"
                else:
                    chunk_message = chunk
                
                command = f"@{contact_name} {chunk_message}"
                await self.send_command(command)
                self.logger.info(f"Sent message part {i+1}/{len(chunks)} to {contact_name}: {chunk_message[:100]}...")
                
                # Small delay between messages to avoid flooding
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.5)
        else:
            command = f"@{contact_name} {message}"
            await self.send_command(command)
            self.logger.info(f"Sent message to {contact_name}: {message[:100]}...")
    
    def _split_message_smartly(self, message: str, max_length: int) -> list[str]:
        """Split message intelligently at natural break points"""
        if len(message) <= max_length:
            return [message]
        
        chunks = []
        current_chunk = ""
        
        # Split by paragraphs first (double newlines)
        paragraphs = message.split('\n\n')
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed limit, start new chunk
            if len(current_chunk) + len(paragraph) + 2 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # If single paragraph is too long, split it by sentences
                if len(paragraph) > max_length:
                    sentences = self._split_by_sentences(paragraph, max_length)
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) + 1 > max_length:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                current_chunk = ""
                        current_chunk += sentence + " "
                else:
                    current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _split_by_sentences(self, text: str, max_length: int) -> list[str]:
        """Split text by sentences when paragraphs are too long"""
        sentences = []
        current = ""
        
        # Split by common sentence endings
        import re
        sentence_endings = re.split(r'([.!?]+\s+)', text)
        
        for i in range(0, len(sentence_endings), 2):
            sentence = sentence_endings[i]
            if i + 1 < len(sentence_endings):
                sentence += sentence_endings[i + 1]
            
            if len(current) + len(sentence) > max_length:
                if current:
                    sentences.append(current.strip())
                    current = ""
                
                # If single sentence is still too long, split by words
                if len(sentence) > max_length:
                    words = sentence.split()
                    if len(words) == 1 and len(words[0]) > max_length:
                        # Fallback: Force truncation for unsplittable content
                        truncated = words[0][:max_length-3] + "..."
                        if current:
                            sentences.append(current.strip())
                            current = ""
                        sentences.append(truncated)
                    else:
                        for word in words:
                            if len(current) + len(word) + 1 > max_length:
                                if current:
                                    sentences.append(current.strip())
                                    current = ""
                            current += word + " "
                else:
                    current = sentence
            else:
                current += sentence
        
        if current:
            sentences.append(current.strip())
        
        return sentences
    
    async def accept_contact_request(self, request_number: int) -> None:
        """Accept an incoming contact request"""
        command = f"/ac {request_number}"
        await self.send_command(command)
        self.logger.info(f"Accepted contact request #{request_number}")
    
    async def connect_to_address(self, address: str) -> Optional[Dict]:
        """Connect to a SimpleX address or invitation link"""
        command = f"/c {address}"
        response = await self.send_command(command, wait_for_response=True)
        if response:
            self.logger.info(f"Connected to address: {address}")
        return response
    
    async def listen_for_messages(self) -> None:
        """Listen for incoming messages from SimpleX Chat CLI"""
        websocket_id = id(self.websocket) if self.websocket else None
        self.logger.info(f"🔊 LISTEN START: Starting message listener on WebSocket {websocket_id}")
        
        if not self.websocket:
            self.logger.error("🔊 LISTEN ERROR: No WebSocket connection available")
            return
        
        # Start heartbeat task to detect if listener is alive
        heartbeat_task = asyncio.create_task(self._heartbeat_monitor(websocket_id))
        
        try:
            self.logger.info(f"🔊 LISTEN LOOP: Entering message loop for WebSocket {websocket_id}")
            
            message_count = 0
            async for message in self.websocket:
                message_count += 1
                self.logger.debug(f"🔊 HEARTBEAT: Received message #{message_count} on WebSocket {websocket_id}")
                
                try:
                    data = json.loads(message)
                    
                    # Debug: Log raw message for correlation debugging
                    corr_id = data.get('corrId', 'None')
                    msg_type = data.get('resp', {}).get('Right', {}).get('type', 'unknown')
                    self.logger.info(f"🔍 RAW RECV: corrId={corr_id}, type={msg_type}")
                    
                    # DEBUG: If this is a contactsList response, log the actual contact data
                    if msg_type == 'contactsList':
                        contacts = data.get('resp', {}).get('Right', {}).get('contacts', [])
                        self.logger.info(f"🔍 CONTACTS DATA: Found {len(contacts)} contacts in response")
                        for i, contact in enumerate(contacts[:5], 1):  # Log first 5 contacts
                            name = contact.get('localDisplayName', 'Unknown')
                            status = contact.get('contactStatus', 'unknown')
                            self.logger.info(f"🔍 CONTACT {i}: {name} ({status})")
                        if len(contacts) > 5:
                            self.logger.info(f"🔍 CONTACTS: ... and {len(contacts) - 5} more")
                    
                    # Smart logging that filters out base64 image data
                    self._log_websocket_message_safely(message, data)
                    
                    await self._handle_response(data)
                    
                    self.logger.info(f"🔊 PROCESSED: Successfully processed message #{message_count}")
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"🔊 JSON ERROR: Failed to parse message #{message_count}: {e}")
                except Exception as e:
                    self.logger.error(f"🔊 MESSAGE EXCEPTION: Error processing message #{message_count}: {type(e).__name__}: {e}")
                    import traceback
                    self.logger.error(f"🔊 MESSAGE TRACEBACK: {traceback.format_exc()}")
                    
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.info(f"🔊 CONNECTION CLOSED: WebSocket {websocket_id} connection closed: {e}")
        except Exception as e:
            self.logger.error(f"🔊 LISTEN EXCEPTION: Error in message listener: {type(e).__name__}: {e}")
            import traceback
            self.logger.error(f"🔊 LISTEN TRACEBACK: {traceback.format_exc()}")
        finally:
            # Cancel heartbeat task
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            self.logger.info(f"🔊 LISTEN END: Message listener ended for WebSocket {websocket_id}")
    
    async def _heartbeat_monitor(self, websocket_id):
        """Monitor if the message listener is still alive and detect CLI corruption"""
        try:
            heartbeat_count = 0
            corruption_check_interval = 4  # Check every 4 heartbeats (60 seconds)
            
            while True:
                await asyncio.sleep(15)  # Every 15 seconds
                heartbeat_count += 1
                
                # Basic heartbeat log
                self.logger.debug(f"💓 HEARTBEAT #{heartbeat_count}: Message listener alive on WebSocket {websocket_id}")
                self.logger.debug(f"📊 STATS: User messages: {self.user_message_count}, System messages: {self.system_message_count}")
                
                # Check for CLI corruption every minute
                if heartbeat_count % corruption_check_interval == 0:
                    await self._check_cli_corruption()
                
                # Check if WebSocket is still valid
                if not self.websocket or id(self.websocket) != websocket_id:
                    self.logger.warning(f"💓 HEARTBEAT: WebSocket changed! Was {websocket_id}, now {id(self.websocket) if self.websocket else 'None'}")
                    break
                    
        except asyncio.CancelledError:
            self.logger.debug(f"💓 HEARTBEAT: Monitor cancelled for WebSocket {websocket_id}")
        except Exception as e:
            self.logger.error(f"💓 HEARTBEAT ERROR: {type(e).__name__}: {e}")
    
    async def _check_cli_corruption(self):
        """Check if SimpleX CLI is in a corrupted state"""
        try:
            current_time = time.time()
            time_since_last_user_message = current_time - self.last_user_message_time
            
            # If we have system messages but no user messages for 2 minutes, suspect corruption
            if (self.system_message_count > 5 and 
                time_since_last_user_message > 120 and  # 2 minutes
                not self.cli_corruption_detected):
                
                self.logger.warning(f"🚨 CLI CORRUPTION DETECTED: No user messages for {time_since_last_user_message:.1f}s but {self.system_message_count} system messages")
                self.cli_corruption_detected = True
                
                # Signal that CLI restart is needed
                await self._handle_cli_corruption()
                
        except Exception as e:
            self.logger.error(f"Error checking CLI corruption: {e}")
    
    async def _handle_cli_corruption(self):
        """Handle detected CLI corruption"""
        self.logger.error("🚨 CRITICAL: SimpleX CLI corruption detected - user messages not flowing")
        self.logger.info("🔄 SOLUTION: CLI restart required to restore user message flow")
        
        # Set a flag that the main loop can check
        self.cli_restart_needed = True
    
    async def restart_cli_process(self):
        """Restart the SimpleX CLI process to fix corruption"""
        try:
            self.logger.info("🔄 CLI RESTART: Attempting to restart SimpleX CLI process...")
            
            # First disconnect WebSocket cleanly
            await self.disconnect()
            
            # Kill the SimpleX CLI process (it will be restarted by the container)
            import subprocess
            
            # Find and kill the simplex-chat process
            self.logger.info("🔄 CLI RESTART: Killing SimpleX CLI process...")
            result = await asyncio.create_subprocess_exec(
                "pkill", "-f", "simplex-chat",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            
            # Wait for the container's startup script to restart CLI
            self.logger.info("🔄 CLI RESTART: Waiting for CLI to restart...")
            await asyncio.sleep(5)
            
            # Reset corruption flags
            self.cli_corruption_detected = False
            self.cli_restart_needed = False
            self.user_message_count = 0
            self.system_message_count = 0
            self.last_user_message_time = time.time()
            
            # Try to reconnect
            self.logger.info("🔄 CLI RESTART: Attempting to reconnect...")
            if await self.connect():
                self.logger.info("✅ CLI RESTART: Successfully restarted CLI and reconnected")
                return True
            else:
                self.logger.error("❌ CLI RESTART: Failed to reconnect after CLI restart")
                return False
                
        except Exception as e:
            self.logger.error(f"🔄 CLI RESTART ERROR: {type(e).__name__}: {e}")
            import traceback
            self.logger.error(f"🔄 CLI RESTART TRACEBACK: {traceback.format_exc()}")
            return False
    
    def _is_user_message(self, response_data: Dict) -> bool:
        """Detect if this is a user chat message vs system message"""
        try:
            resp = response_data.get("resp", {})
            
            # Handle SimpleX Chat CLI's Either-type responses
            if "Right" in resp:
                actual_resp = resp["Right"]
            else:
                actual_resp = resp
            
            resp_type = actual_resp.get("type", "")
            
            # Check for user chat messages
            if resp_type in ["newChatItem", "newChatItems"]:
                # Extract chat item to check if it's from a user
                if resp_type == "newChatItem":
                    chat_item = actual_resp.get("chatItem", {})
                    chat_info = actual_resp.get("chatInfo", {})
                elif resp_type == "newChatItems":
                    chat_items = actual_resp.get("chatItems", [])
                    if chat_items:
                        chat_item = chat_items[0].get("chatItem", {})
                        chat_info = chat_items[0].get("chatInfo", {})
                    else:
                        return False
                else:
                    return False
                
                # Check if this is from a user contact (not system)
                if chat_info.get("chatType") == "direct":
                    content = chat_item.get("content", {})
                    msg_content = content.get("msgContent", {})
                    
                    # User text messages
                    if msg_content.get("type") == "text":
                        return True
                
            return False
            
        except Exception as e:
            self.logger.debug(f"Error checking if user message: {e}")
            return False
    
    async def _handle_response(self, response_data: Dict) -> None:
        """Handle responses from SimpleX Chat CLI"""
        try:
            # Track user vs system messages
            if self._is_user_message(response_data):
                self.user_message_count += 1
                self.last_user_message_time = time.time()
                self.logger.info(f"👤 USER MESSAGE #{self.user_message_count}: Received user message")
            else:
                self.system_message_count += 1
                self.logger.debug(f"🔧 SYSTEM MESSAGE #{self.system_message_count}: System message")
            
            corr_id = response_data.get("corrId")
            resp = response_data.get("resp", {})
            
            # CORRELATION DEBUG: Log every response with correlation details
            self.logger.info(f"🔍 CORRELATION DEBUG: Processing response with corrId='{corr_id}'")
            self.logger.info(f"🔍 CORRELATION DEBUG: Current pending_requests keys: {list(self.pending_requests.keys())}")
            
            # Handle SimpleX Chat CLI's Either-type responses (Right wrapper for success)
            if "Right" in resp:
                actual_resp = resp["Right"]
                resp_type = actual_resp.get("type", "")
                self.logger.info(f"🔍 CORRELATION DEBUG: Right-wrapped response type: {resp_type}")
            elif "Left" in resp:
                # Handle error responses (Left wrapper)
                error_resp = resp["Left"]
                self.logger.error(f"Received error response: {error_resp}")
                return
            else:
                # Fallback for direct responses (shouldn't happen with current SimpleX CLI)
                actual_resp = resp
                resp_type = resp.get("type", "")
                self.logger.info(f"🔍 CORRELATION DEBUG: Direct response type: {resp_type}")
            
            # Handle correlation ID responses first
            if corr_id:
                self.logger.info(f"🔍 CORRELATION DEBUG: Found corrId '{corr_id}', checking if in pending_requests...")
                if corr_id in self.pending_requests:
                    self.logger.info(f"✅ CORRELATION SUCCESS: Found pending request for '{corr_id}' - storing response")
                    
                    # Get the original request info
                    request_info = self.pending_requests[corr_id]
                    command = request_info.get('command', '')
                    
                    # Store the response
                    response_key = f"{corr_id}_response"
                    self.pending_requests[response_key] = response_data
                    self.logger.info(f"✅ CORRELATION SUCCESS: Stored response with key '{response_key}'")
                    
                    # Remove the pending request
                    del self.pending_requests[corr_id]
                    self.logger.info(f"✅ CORRELATION SUCCESS: Removed pending request '{corr_id}'")
                    
                    # Trigger callback for specific commands
                    if command == '/contacts' and resp_type == 'contactsList':
                        self.logger.info(f"🔔 CONTACTS CALLBACK: Triggering contacts list callback")
                        asyncio.create_task(self._handle_contacts_response(response_data))
                    elif command == '/groups' and resp_type == 'groupsList':
                        self.logger.info(f"🔔 GROUPS CALLBACK: Triggering groups list callback")
                        asyncio.create_task(self._handle_groups_response(response_data))
                    
                    self.logger.info(f"✅ CORRELATION SUCCESS: Updated pending_requests keys: {list(self.pending_requests.keys())}")
                else:
                    self.logger.warning(f"❌ CORRELATION MISS: corrId '{corr_id}' not found in pending_requests")
                    self.logger.warning(f"❌ CORRELATION MISS: Available keys were: {list(self.pending_requests.keys())}")
            else:
                self.logger.info(f"🔍 CORRELATION DEBUG: No corrId in response - not a command response")
            
            # Route to appropriate message handler
            if resp_type in self.message_handlers:
                await self.message_handlers[resp_type](actual_resp)
            else:
                self.logger.debug(f"No handler registered for response type: {resp_type}")
                
        except Exception as e:
            self.logger.error(f"Error handling response: {e}")
    
    def _log_websocket_message_safely(self, message: str, data: Dict) -> None:
        """Log WebSocket messages while filtering out base64 data to prevent log spam"""
        try:
            # Check if this is a file message with base64 data
            if self._contains_base64_file_data(data):
                # Log a summary instead of the full message
                msg_type = "unknown"
                file_name = "unknown"
                file_size = 0
                
                # Extract basic info for logging
                if "resp" in data and "Right" in data["resp"]:
                    resp_data = data["resp"]["Right"]
                    msg_type = resp_data.get("type", "unknown")
                    
                    if msg_type in ["newChatItem", "newChatItems"]:
                        # Try to extract file info
                        chat_item = resp_data.get("chatItem", {}) if msg_type == "newChatItem" else {}
                        if not chat_item and msg_type == "newChatItems":
                            chat_items = resp_data.get("chatItems", [])
                            if chat_items:
                                chat_item = chat_items[0].get("chatItem", {})
                        
                        content = chat_item.get("content", {})
                        msg_content = content.get("msgContent", {})
                        content_type = msg_content.get("type", "")
                        
                        if content_type == "file":
                            file_name = msg_content.get("fileName", "unknown")
                            file_size = msg_content.get("fileSize", 0)
                        elif content_type == "image":
                            file_name = "image"
                            image_data = msg_content.get("image", "")
                            if image_data.startswith("data:image/"):
                                # Calculate approximate size from data URL
                                if "," in image_data:
                                    base64_data = image_data.split(",", 1)[1]
                                    file_size = (len(base64_data.rstrip("=")) * 3) // 4
                                else:
                                    file_size = 0
                            else:
                                file_size = 0
                
                self.logger.debug(f"Received message type: {msg_type} (file: {file_name}, {file_size} bytes) - base64 data filtered")
            else:
                # Log normally for non-file messages
                self.logger.debug(f"Received WebSocket message: {message[:200]}...")
                
        except Exception as e:
            self.logger.debug(f"Error in safe logging: {e}")
    
    def _contains_base64_file_data(self, data: Dict) -> bool:
        """Check if the message contains base64 file data"""
        try:
            if "resp" in data and "Right" in data["resp"]:
                resp_data = data["resp"]["Right"]
                msg_type = resp_data.get("type", "")
                
                if msg_type == "newChatItem":
                    return self._check_chat_item_for_file_data(resp_data.get("chatItem", {}))
                elif msg_type == "newChatItems":
                    chat_items = resp_data.get("chatItems", [])
                    return any(self._check_chat_item_for_file_data(item.get("chatItem", {})) for item in chat_items)
            
            return False
        except Exception:
            return False
    
    def _check_chat_item_for_file_data(self, chat_item: Dict) -> bool:
        """Check if a chat item contains file data"""
        try:
            content = chat_item.get("content", {})
            msg_content = content.get("msgContent", {})
            msg_type = msg_content.get("type", "")
            
            # Check for traditional file format with embedded data
            if msg_type == "file" and "fileData" in msg_content:
                return True
            
            # Check for SimpleX image format with data URL
            if msg_type == "image" and "image" in msg_content:
                image_data = msg_content.get("image", "")
                return image_data.startswith("data:image/")
            
            return False
        except Exception:
            return False
    
    async def _send_pending_invite_message(self):
        """Send pending invite message after reconnection"""
        try:
            if not self.pending_invite_message:
                return
                
            # Wait a moment for connection to stabilize
            await asyncio.sleep(2)
            
            contact_name = self.pending_invite_message['contact_name']
            message = self.pending_invite_message['message']
            
            self.logger.info(f"🎫 SENDING PENDING: Sending queued invite message to {contact_name}")
            
            # Send the invite message
            await self.send_message(contact_name, message)
            
            # Clear the pending message
            self.pending_invite_message = None
            
            self.logger.info(f"🎫 SENT PENDING: Successfully sent queued invite message to {contact_name}")
            
        except Exception as e:
            self.logger.error(f"🎫 PENDING MESSAGE ERROR: {type(e).__name__}: {e}")
            import traceback
            self.logger.error(f"🎫 PENDING MESSAGE TRACEBACK: {traceback.format_exc()}")
            # Clear the pending message even on error to avoid infinite retry
            self.pending_invite_message = None