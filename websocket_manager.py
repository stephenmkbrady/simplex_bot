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
DEFAULT_TIMEOUT_SECONDS = 30


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
    
    def register_message_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for specific message types"""
        self.message_handlers[message_type] = handler
        self.logger.debug(f"Registered handler for message type: {message_type}")
    
    def generate_correlation_id(self) -> str:
        """Generate a unique correlation ID for requests"""
        self.correlation_counter += 1
        return f"bot_req_{int(time.time())}_{self.correlation_counter}"
    
    async def connect(self, max_retries: int = DEFAULT_MAX_RETRIES, retry_delay: int = DEFAULT_RETRY_DELAY) -> bool:
        """Connect to the SimpleX Chat CLI WebSocket server with retries"""
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Connecting to SimpleX Chat CLI at {self.websocket_url} (attempt {attempt + 1}/{max_retries})")
                self.websocket = await websockets.connect(self.websocket_url)
                self.logger.info("Successfully connected to SimpleX Chat CLI")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay}s: {e}")
                    await asyncio.sleep(retry_delay)
                else:
                    self.logger.error(f"Failed to connect to SimpleX Chat CLI after {max_retries} attempts: {e}")
                    return False
        return False
    
    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server"""
        if self.websocket:
            await self.websocket.close()
            self.logger.info("Disconnected from SimpleX Chat CLI")
    
    async def send_command(self, command: str, wait_for_response: bool = False) -> Optional[Dict]:
        """
        Send a command to SimpleX Chat CLI
        
        Args:
            command: The command to send
            wait_for_response: Whether to wait for and return the response
            
        Returns:
            Response dict if wait_for_response is True, None otherwise
        """
        if not self.websocket:
            self.logger.error("Not connected to SimpleX Chat CLI")
            return None
        
        corr_id = self.generate_correlation_id()
        
        message = {
            "corrId": corr_id,
            "cmd": command
        }
        
        try:
            await self.websocket.send(json.dumps(message))
            self.logger.debug(f"Sent command: {command} (corr_id: {corr_id})")
            
            if wait_for_response:
                # Store the request for correlation
                self.pending_requests[corr_id] = {"command": command, "timestamp": time.time()}
                
                # Wait for response (with timeout)
                timeout = DEFAULT_TIMEOUT_SECONDS
                start_time = time.time()
                
                while corr_id in self.pending_requests:
                    if time.time() - start_time > timeout:
                        self.logger.warning(f"Timeout waiting for response to command: {command}")
                        del self.pending_requests[corr_id]
                        return None
                    
                    await asyncio.sleep(0.1)
                
                # Response should be stored with "_response" suffix
                return self.pending_requests.get(f"{corr_id}_response")
                
        except (websockets.exceptions.ConnectionClosed, json.JSONEncodeError) as e:
            raise WebSocketError(f"WebSocket communication error: {e}")
        except Exception as e:
            self.logger.error(f"Failed to send command: {e}")
            return None
    
    async def send_message(self, contact_name: str, message: str) -> None:
        """Send a message to a specific contact, splitting long messages"""
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
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    
                    # Smart logging that filters out base64 image data
                    self._log_websocket_message_safely(message, data)
                    
                    await self._handle_response(data)
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse JSON message: {e}")
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.info("WebSocket connection closed")
        except Exception as e:
            self.logger.error(f"Error in message listener: {e}")
    
    async def _handle_response(self, response_data: Dict) -> None:
        """Handle responses from SimpleX Chat CLI"""
        try:
            corr_id = response_data.get("corrId")
            resp = response_data.get("resp", {})
            
            # Handle SimpleX Chat CLI's Either-type responses (Right wrapper for success)
            if "Right" in resp:
                actual_resp = resp["Right"]
                resp_type = actual_resp.get("type", "")
                self.logger.debug(f"Processing Right-wrapped response type: {resp_type}")
            elif "Left" in resp:
                # Handle error responses (Left wrapper)
                error_resp = resp["Left"]
                self.logger.error(f"Received error response: {error_resp}")
                return
            else:
                # Fallback for direct responses (shouldn't happen with current SimpleX CLI)
                actual_resp = resp
                resp_type = resp.get("type", "")
                self.logger.debug(f"Processing direct response type: {resp_type}")
            
            # Handle correlation ID responses first
            if corr_id and corr_id in self.pending_requests:
                # Store the response
                self.pending_requests[f"{corr_id}_response"] = response_data
                # Remove the pending request
                del self.pending_requests[corr_id]
            
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