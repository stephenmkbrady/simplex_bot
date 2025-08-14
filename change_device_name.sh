#!/bin/bash
# Script to change device name of existing SimpleX profile

DEVICE_NAME=${1:-${DEVICE_NAME:-"rename_bot"}}

echo "🔄 Changing device name to: $DEVICE_NAME"

# Use the CLI to change the profile name
echo "Updating profile display name..."
./compose.sh exec simplex-bot-v2 bash -c "echo '/set profile displayName \"$DEVICE_NAME\"' | simplex-chat -d /app/profile/simplex --device-name '$DEVICE_NAME' -e '/q' -t 1"

echo "✅ Device name changed to: $DEVICE_NAME"
echo "🔄 Restarting bot to apply changes..."

./compose.sh restart

echo "✅ Bot restarted with new device name"