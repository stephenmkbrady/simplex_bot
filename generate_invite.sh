#!/bin/bash
# Generate SimpleX Bot invitation link

echo "🎫 Generating bot invitation..."

# Check if the bot container is running
if ! docker ps --filter "name=simplex-bot-v2" --format "{{.Names}}" | grep -q "simplex-bot-v2"; then
    echo "❌ Bot container is not running. Starting bot first..."
    ./compose.sh up -d
    echo "⏳ Waiting for bot to initialize..."
    sleep 20
else
    echo "✅ Bot container is running"
fi

echo ""
./compose.sh exec simplex-bot-v2 simplex-chat -d /app/profile/simplex --device-name $DEVICE_NAME -e '/connect' -t 1

echo ""
echo "✅ Use the invitation link above to connect to the bot!"
echo "Waiting for a minute"
echo ""
sleep 60 
echo "restarting the bot as part of the generate"
./compose.sh down
./compose.sh up