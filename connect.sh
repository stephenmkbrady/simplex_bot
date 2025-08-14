#!/bin/bash

# Simple wrapper script to connect to SimpleX Chat invitations
# Usage: ./connect.sh <invitation_url>

INVITATION_URL="$1"

if [ -z "$INVITATION_URL" ]; then
    echo "Usage: $0 <invitation_url>"
    echo "Example: $0 'https://simplex.chat/invitation#/?v=2-7&smp=...'"
    exit 1
fi

echo "=== SimpleX Chat Invitation Connection ==="
echo "Invitation URL: $INVITATION_URL"
echo ""

# Try the Python WebSocket approach first (most reliable)
echo "Attempting connection via WebSocket API..."
./compose.sh exec simplex-bot-v2 python3 /app/simplex_utils.py "$INVITATION_URL"

if [ $? -eq 0 ]; then
    echo "✓ Connection successful!"
else
    echo "✗ WebSocket connection failed, trying CLI method..."
    
    # Fallback to CLI method
    echo "Attempting connection via CLI method..."
    DEVICE_NAME=${DEVICE_NAME:-"rename_bot"}
    echo "/connect $INVITATION_URL" | ./compose.sh exec simplex-bot-v2 timeout 30 simplex-chat -d /app/profile/simplex --device-name "$DEVICE_NAME" -e '/q' -t 1
fi

echo ""
echo "=== Connection attempt completed ==="