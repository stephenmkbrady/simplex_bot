#!/usr/bin/env python3
"""
Hot Reload Test Script

This script tests the hot reload functionality by:
1. Modifying the example plugin version
2. Checking bot logs for hot reload activity
3. Reverting the change
4. Checking for hot reload again

Usage: python test_hot_reload.py
"""

import subprocess
import time
import re
from datetime import datetime

class HotReloadTester:
    def __init__(self):
        self.plugin_file = "/home/user/Documents/DEV/SIMPLEX_BOT/plugins/external/example/plugin.py"
        self.original_version = '        self.version = "2.0.0"  # Updated for universal support'
        self.test_version = '        self.version = "2.0.1"  # HOT RELOAD TEST VERSION'
        
    def get_recent_logs(self, since_seconds=10):
        """Get recent bot logs"""
        try:
            cmd = f"docker compose -f /home/user/Documents/DEV/SIMPLEX_BOT/docker-compose.yml logs simplex-bot --since={since_seconds}s"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.stdout
        except Exception as e:
            print(f"Error getting logs: {e}")
            return ""
    
    def check_for_hot_reload_logs(self, logs):
        """Check if logs contain hot reload activity"""
        patterns = [
            r"🔥 Plugin file changed: example",
            r"🔄 Reloading plugin: example",
            r"Plugin.*example.*reload"
        ]
        
        found_patterns = []
        for pattern in patterns:
            if re.search(pattern, logs, re.IGNORECASE):
                found_patterns.append(pattern)
        
        return found_patterns
    
    def modify_plugin_file(self, new_content_line):
        """Modify the plugin file with new version"""
        try:
            with open(self.plugin_file, 'r') as f:
                content = f.read()
            
            # Replace the version line
            if self.original_version in content:
                new_content = content.replace(self.original_version, new_content_line)
            elif self.test_version in content:
                new_content = content.replace(self.test_version, new_content_line)
            else:
                print("ERROR: Could not find version line to replace!")
                return False
            
            with open(self.plugin_file, 'w') as f:
                f.write(new_content)
            
            print(f"✅ Modified plugin file: {new_content_line.strip()}")
            return True
            
        except Exception as e:
            print(f"❌ Error modifying plugin file: {e}")
            return False
    
    def run_test(self):
        """Run the complete hot reload test"""
        print("🧪 Starting Hot Reload Test")
        print("=" * 50)
        
        # Step 1: Modify plugin to test version
        print("\n📝 Step 1: Modifying example plugin to test version...")
        if not self.modify_plugin_file(self.test_version):
            return False
        
        # Wait for hot reload to trigger
        print("⏳ Waiting 5 seconds for hot reload to trigger...")
        time.sleep(5)
        
        # Check logs for hot reload activity
        print("📋 Checking logs for hot reload activity...")
        logs = self.get_recent_logs(10)
        patterns_found = self.check_for_hot_reload_logs(logs)
        
        if patterns_found:
            print("✅ Hot reload detected! Found patterns:")
            for pattern in patterns_found:
                print(f"   - {pattern}")
        else:
            print("❌ No hot reload activity detected in logs")
            print("Recent logs:")
            print(logs[-500:])  # Last 500 chars
        
        test1_success = len(patterns_found) > 0
        
        # Step 2: Revert plugin to original version
        print("\n📝 Step 2: Reverting example plugin to original version...")
        if not self.modify_plugin_file(self.original_version):
            return False
        
        # Wait for second hot reload
        print("⏳ Waiting 5 seconds for second hot reload...")
        time.sleep(5)
        
        # Check logs again
        print("📋 Checking logs for second hot reload...")
        logs = self.get_recent_logs(10)
        patterns_found_2 = self.check_for_hot_reload_logs(logs)
        
        if patterns_found_2:
            print("✅ Second hot reload detected! Found patterns:")
            for pattern in patterns_found_2:
                print(f"   - {pattern}")
        else:
            print("❌ No second hot reload activity detected")
            print("Recent logs:")
            print(logs[-500:])
        
        test2_success = len(patterns_found_2) > 0
        
        # Final results
        print("\n" + "=" * 50)
        print("🏁 Test Results:")
        print(f"   First hot reload (modify):  {'✅ PASS' if test1_success else '❌ FAIL'}")
        print(f"   Second hot reload (revert): {'✅ PASS' if test2_success else '❌ FAIL'}")
        
        if test1_success and test2_success:
            print("🎉 Hot reload is working correctly!")
            return True
        else:
            print("⚠️  Hot reload needs debugging")
            print("\nDebugging info:")
            print("- Check if watchdog is installed: pip list | grep watchdog")
            print("- Check if hot reload started: docker logs should show '🔥 Hot reloading enabled'")
            print("- Check file permissions in container")
            return False

def main():
    """Run the hot reload test"""
    tester = HotReloadTester()
    success = tester.run_test()
    exit(0 if success else 1)

if __name__ == "__main__":
    main()