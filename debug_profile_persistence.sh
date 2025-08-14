#!/bin/bash

echo "=== SIMPLEX CHAT PROFILE PERSISTENCE DIAGNOSTIC ==="
echo "Timestamp: $(date)"
echo

# Function to check directory contents with detailed info
check_directory() {
    local dir="$1"
    local description="$2"
    
    echo "=== $description ==="
    if [ -d "$dir" ]; then
        echo "Directory exists: $dir"
        echo "Permissions: $(ls -ld "$dir")"
        echo "Owner: $(stat -c '%U:%G' "$dir" 2>/dev/null || echo "unknown")"
        echo "Contents:"
        if [ "$(ls -A "$dir" 2>/dev/null)" ]; then
            ls -la "$dir"
            echo
            echo "File details:"
            find "$dir" -type f -exec echo "File: {}" \; -exec ls -la {} \; -exec echo "Size: $(stat -c %s {} 2>/dev/null || echo unknown) bytes" \; -exec echo "---" \;
        else
            echo "Directory is empty"
        fi
    else
        echo "Directory does not exist: $dir"
    fi
    echo
}

# Function to check SimpleX Chat CLI behavior
test_simplex_cli() {
    echo "=== SIMPLEX CHAT CLI DIAGNOSTIC ==="
    
    # Check if CLI is installed
    if command -v simplex-chat >/dev/null 2>&1; then
        echo "SimpleX Chat CLI found: $(which simplex-chat)"
        echo "Version info:"
        simplex-chat --version 2>/dev/null || echo "Could not get version"
    else
        echo "SimpleX Chat CLI not found in PATH"
    fi
    echo
    
    # Test profile initialization
    echo "Testing profile initialization..."
    DEVICE_NAME=${DEVICE_NAME:-"rename_bot"}
    echo "Command: simplex-chat -d /app/profile --device-name $DEVICE_NAME -e '/q' -t 1"
    
    # Create a test to see what happens
    mkdir -p /tmp/test_profile
    echo "Test profile creation in /tmp/test_profile:"
    echo 'Test' | timeout 10 simplex-chat -d /tmp/test_profile --device-name TestBot -e '/q' -t 1 2>&1 || echo "Command failed or timed out"
    
    echo "Test profile contents:"
    ls -la /tmp/test_profile/ 2>/dev/null || echo "No test profile created"
    echo
}

# Function to check container environment
check_container_env() {
    echo "=== CONTAINER ENVIRONMENT ==="
    echo "Current user: $(whoami)"
    echo "User ID: $(id -u)"
    echo "Group ID: $(id -g)"
    echo "Groups: $(groups)"
    echo "Working directory: $(pwd)"
    echo "Environment variables related to profile:"
    env | grep -i profile || echo "No profile-related env vars"
    echo
}

# Function to check volume mount
check_volume_mount() {
    echo "=== VOLUME MOUNT ANALYSIS ==="
    echo "Mount points:"
    mount | grep -E "(app|profile)" || echo "No app/profile mounts found"
    echo
    echo "Filesystem info for /app:"
    df -h /app 2>/dev/null || echo "Cannot get filesystem info for /app"
    echo
    echo "Filesystem info for /app/profile:"
    df -h /app/profile 2>/dev/null || echo "Cannot get filesystem info for /app/profile"
    echo
}

# Function to simulate profile creation and check persistence
test_profile_persistence() {
    echo "=== PROFILE PERSISTENCE TEST ==="
    
    # Create a test file in the profile directory
    echo "Creating test file in profile directory..."
    echo "Test data created at $(date)" > /app/profile/test_persistence.txt
    
    if [ -f /app/profile/test_persistence.txt ]; then
        echo "✓ Test file created successfully"
        echo "Content: $(cat /app/profile/test_persistence.txt)"
        echo "File permissions: $(ls -la /app/profile/test_persistence.txt)"
    else
        echo "✗ Failed to create test file"
    fi
    echo
}

# Function to check for existing SimpleX database files
check_simplex_database() {
    echo "=== SIMPLEX DATABASE FILES ==="
    echo "Looking for SimpleX database files in /app/profile:"
    
    # Common SimpleX database file patterns
    find /app/profile -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" -o -name "*chat*" -o -name "*simplex*" 2>/dev/null | while read file; do
        echo "Found: $file"
        echo "  Size: $(stat -c %s "$file" 2>/dev/null || echo unknown) bytes"
        echo "  Modified: $(stat -c %y "$file" 2>/dev/null || echo unknown)"
        echo "  Permissions: $(ls -la "$file")"
        echo
    done
    
    # Check for any files at all
    echo "All files in profile directory:"
    find /app/profile -type f 2>/dev/null | head -20 || echo "No files found"
    echo
}

# Main execution
echo "Starting diagnostic..."
echo

check_container_env
check_volume_mount
check_directory "/app/profile" "PROFILE DIRECTORY (/app/profile)"
check_directory "./bot_profile" "HOST PROFILE DIRECTORY (./bot_profile)"
check_simplex_database
test_profile_persistence
test_simplex_cli

echo "=== DIAGNOSTIC COMPLETE ==="
echo "Key findings to investigate:"
echo "1. Is the profile directory properly mounted?"
echo "2. Are there permission issues preventing file creation?"
echo "3. Is SimpleX Chat CLI creating files in the expected location?"
echo "4. Are database files being created but in wrong location?"
echo
echo "Next steps:"
echo "- Check if files exist on host system in ./bot_profile"
echo "- Verify docker volume mount is working"
echo "- Test SimpleX CLI profile creation manually"