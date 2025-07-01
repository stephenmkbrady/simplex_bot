#!/bin/bash

# Script to connect to SimpleX Chat invitation non-interactively
# Usage: ./connect_invitation.sh <invitation_url>

INVITATION_URL="$1"
PROFILE_DIR="/app/profile"
DEVICE_NAME="Bot"

if [ -z "$INVITATION_URL" ]; then
    echo "Usage: $0 <invitation_url>"
    exit 1
fi

echo "Connecting to SimpleX Chat invitation..."
echo "Invitation URL: $INVITATION_URL"
echo "Profile directory: $PROFILE_DIR"
echo "Device name: $DEVICE_NAME"

# Try using echo to pipe the command directly
echo "Attempting connection using echo pipe method..."
echo "/connect $INVITATION_URL" | timeout 30 simplex-chat -d "$PROFILE_DIR" --device-name "$DEVICE_NAME" -e '/q' -t 1 2>&1

echo "Connection attempt completed."