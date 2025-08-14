#!/bin/bash
# Script to reinitialize SimpleX profile with correct device name

DEVICE_NAME=${1:-${DEVICE_NAME:-"rename_bot"}}

echo "🔄 Reinitializing SimpleX profile with device name: $DEVICE_NAME"

# Stop the bot
./compose.sh down

# Clear the profile
echo "🗑️ Clearing existing profile..."
rm -rf bot_profile/*

# Start with the correct device name
echo "🚀 Starting bot with device name: $DEVICE_NAME"
DEVICE_NAME="$DEVICE_NAME" ./compose.sh up -d

echo "✅ Profile reinitialized with device name: $DEVICE_NAME"