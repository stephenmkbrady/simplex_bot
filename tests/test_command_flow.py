#!/usr/bin/env python3
"""
Test the complete command flow that happens when !contacts list is executed
"""

import asyncio
import json
import sys
import os
import pytest

# Add the current directory to Python path so we can import bot modules
sys.path.insert(0, '/app')

@pytest.mark.asyncio
async def test_contacts_command_flow():
    """Test the complete flow from command to response"""
    try:
        # Import bot components
        from bot import SimplexChatBot
        from config_manager import ConfigManager
        
        print("🔧 DEBUG: Importing bot components...")
        
        # Initialize config manager
        config_manager = ConfigManager(config_path="/app/config.yml")
        config = config_manager.get_bot_config()
        
        print("🔧 DEBUG: Creating bot instance...")
        
        # Create bot instance (without starting it)
        bot = SimplexChatBot(config)
        
        print("🔧 DEBUG: Testing command registry directly...")
        
        # Test the command registry directly
        command_registry = bot.command_registry
        
        # Set up the bot instance reference for the command
        if hasattr(command_registry, '_contacts_command'):
            # Get the contacts command handler
            contacts_handler = command_registry._contacts_command
            
            print("🔧 DEBUG: Found contacts command handler")
            
            # Test admin check
            admin_manager = bot.admin_manager
            can_run = admin_manager.can_run_command("NonpareilMagnitude", "contacts")
            print(f"🔧 DEBUG: Admin check for NonpareilMagnitude: {can_run}")
            
            if can_run:
                print("🔧 DEBUG: Testing contacts command execution...")
                
                # Simulate the exact call that execute_command makes
                args = ["list"]
                contact_name = "NonpareilMagnitude"
                
                response_capture = {"response": None}
                
                async def capture_callback(contact: str, message: str):
                    print(f"🔧 DEBUG: Captured response: {message[:100]}...")
                    response_capture["response"] = message
                
                # Set the bot instance reference that the command needs
                command_registry.bot_instance = bot
                
                print("🔧 DEBUG: Calling contacts handler...")
                start_time = asyncio.get_event_loop().time()
                
                try:
                    # This is the exact call that execute_command makes
                    await contacts_handler(args, contact_name, capture_callback)
                    
                    end_time = asyncio.get_event_loop().time()
                    elapsed = end_time - start_time
                    
                    print(f"🔧 DEBUG: Handler completed in {elapsed:.2f} seconds")
                    
                    response = response_capture.get("response")
                    if response:
                        print(f"✅ DEBUG: Got response: {response[:200]}...")
                    else:
                        print(f"❌ DEBUG: No response captured")
                        
                except Exception as e:
                    end_time = asyncio.get_event_loop().time()
                    elapsed = end_time - start_time
                    print(f"❌ DEBUG: Handler failed after {elapsed:.2f} seconds: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    
            else:
                print("❌ DEBUG: Admin check failed")
                
        else:
            print("❌ DEBUG: Contacts command handler not found")
            
    except Exception as e:
        print(f"❌ DEBUG: Error in test: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_contacts_command_flow())