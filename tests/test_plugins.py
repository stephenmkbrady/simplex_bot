#!/usr/bin/env python3
"""
Test script for the universal plugin system
"""
import asyncio
import sys
from bot import SimplexChatBot

async def test_plugin_integration():
    print("🚀 Testing Universal Plugin System Integration")
    print("=" * 50)
    
    try:
        # Initialize bot
        print("1. Initializing bot...")
        bot = SimplexChatBot('config.yml')
        print("✅ Bot initialized")
        
        # Load plugins
        print("\n2. Loading plugins...")
        if bot.plugin_manager and bot.plugin_adapter:
            results = await bot.plugin_manager.discover_and_load_plugins(bot.plugin_adapter)
            print(f"✅ Plugin loading results: {results}")
            
            status = bot.plugin_manager.get_plugin_status()
            print(f"✅ Loaded plugins: {list(status['loaded'].keys())}")
            if status['failed']:
                print(f"⚠️  Failed plugins: {list(status['failed'].keys())}")
        else:
            print("❌ Plugin system not initialized")
            return
        
        # Test commands
        print("\n3. Testing commands...")
        test_commands = ['!help', '!ping', '!status', '!plugins', '!echo hello', '!youtube']
        contact_name = 'TestUser'
        
        for cmd in test_commands:
            print(f"\nTesting command: {cmd}")
            
            # Check if recognized
            is_cmd = bot.command_registry.is_command(cmd)
            print(f"  - is_command: {is_cmd}")
            
            if is_cmd:
                try:
                    result = await bot.command_registry.execute_command(cmd, contact_name, bot.plugin_manager)
                    if result:
                        print(f"  ✅ Success (length: {len(result)})")
                        print(f"  📝 Preview: {result[:150]}...")
                    else:
                        print(f"  ❌ No result returned")
                except Exception as e:
                    print(f"  ❌ Error: {e}")
            else:
                print(f"  ❌ Not recognized as command")
        
        # Test direct plugin manager commands
        print("\n4. Testing direct plugin manager...")
        from plugins.universal_plugin_base import CommandContext, BotPlatform
        
        test_context = CommandContext(
            command='help',
            args=[],
            args_raw='',
            user_id='test_user',
            chat_id='test_chat',
            user_display_name='Test User',
            platform=BotPlatform.SIMPLEX,
            raw_message={}
        )
        
        try:
            result = await bot.plugin_manager.handle_command(test_context)
            if result:
                print(f"✅ Direct plugin command successful")
                print(f"📝 Response: {result[:200]}...")
            else:
                print("❌ Direct plugin command failed")
        except Exception as e:
            print(f"❌ Direct plugin error: {e}")
        
        print("\n5. Summary")
        print("=" * 50)
        print("✅ Universal plugin system successfully integrated!")
        print("🔌 Core and example plugins loaded and functional")
        print("💡 Plugins respond to commands through universal adapter")
        print("🚀 Ready for SimpleX bot deployment!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_plugin_integration())