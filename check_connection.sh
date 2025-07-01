#!/bin/bash

# Script to check SimpleX Chat connection status and attempt connection
PROFILE_DIR="/app/profile"
DEVICE_NAME="Bot"
INVITATION_URL="$1"

echo "=== SimpleX Chat Connection Status Check ==="
echo "Profile directory: $PROFILE_DIR"
echo "Device name: $DEVICE_NAME"

# Check if profile exists
if [ -d "$PROFILE_DIR" ]; then
    echo "✓ Profile directory exists"
    ls -la "$PROFILE_DIR"
else
    echo "✗ Profile directory does not exist"
    exit 1
fi

# Check current user and contacts
echo ""
echo "=== Checking current user and contacts ==="
echo "/me" | timeout 10 simplex-chat -d "$PROFILE_DIR" --device-name "$DEVICE_NAME" -e "/q" -t 1 2>&1

echo ""
echo "=== Listing contacts ==="
echo "/contacts" | timeout 10 simplex-chat -d "$PROFILE_DIR" --device-name "$DEVICE_NAME" -e "/q" -t 1 2>&1

# If invitation URL provided, attempt connection
if [ -n "$INVITATION_URL" ]; then
    echo ""
    echo "=== Attempting to connect to invitation ==="
    echo "Invitation URL: $INVITATION_URL"
    
    # Create connection command
    echo "/connect $INVITATION_URL" | timeout 30 simplex-chat -d "$PROFILE_DIR" --device-name "$DEVICE_NAME" -e "/q" -t 1 2>&1
    
    echo ""
    echo "=== Checking contacts after connection attempt ==="
    echo "/contacts" | timeout 10 simplex-chat -d "$PROFILE_DIR" --device-name "$DEVICE_NAME" -e "/q" -t 1 2>&1
fi

echo ""
echo "=== Connection check completed ==="