#!/bin/bash

# Function to cleanup processes on exit
cleanup() {
    echo "Received termination signal, cleaning up..."
    if [ -n "$SIMPLEX_PID" ]; then
        echo "Stopping SimpleX Chat CLI (PID: $SIMPLEX_PID)"
        kill -TERM $SIMPLEX_PID 2>/dev/null || true
        wait $SIMPLEX_PID 2>/dev/null || true
    fi
    if [ -n "$BOT_PID" ]; then
        echo "Stopping bot (PID: $BOT_PID)"
        kill -TERM $BOT_PID 2>/dev/null || true
        wait $BOT_PID 2>/dev/null || true
    fi
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Check if SimpleX Chat CLI is already installed
if [ ! -f "/usr/local/bin/simplex-chat" ]; then
    echo "Installing SimpleX Chat CLI..."
    curl -L https://github.com/simplex-chat/simplex-chat/releases/latest/download/simplex-chat-ubuntu-22_04-x86-64 -o /usr/local/bin/simplex-chat
    chmod +x /usr/local/bin/simplex-chat
else
    echo "SimpleX Chat CLI already installed"
fi

echo "Setting up SimpleX Chat CLI arguments..."
if [ -n "$SMP_SERVER_1" ]; then
    SMP_ARGS="-s $SMP_SERVER_1"
    if [ -n "$SMP_SERVER_2" ]; then
        SMP_ARGS="$SMP_ARGS -s $SMP_SERVER_2"
    fi
fi

if [ -n "$XFTP_SERVER_1" ]; then
    XFTP_ARGS="--xftp-server $XFTP_SERVER_1"
    if [ -n "$XFTP_SERVER_2" ]; then
        XFTP_ARGS="$XFTP_ARGS --xftp-server $XFTP_SERVER_2"
    fi
fi

echo "Initializing SimpleX Chat profile..."
(printf 'y\ny\ny\nBot\n'; yes) | simplex-chat -d /app/profile/simplex --device-name Bot $SMP_ARGS $XFTP_ARGS -e '/q' -t 1 2>/dev/null || true

# Function to start and monitor SimpleX Chat CLI
start_simplex_cli() {
    echo "Starting SimpleX Chat CLI..."
    echo "SMP Args: $SMP_ARGS"
    echo "XFTP Args: $XFTP_ARGS"
    
    # Kill any existing SimpleX Chat processes (use ps instead of pgrep for compatibility)
    # Find and kill existing simplex-chat processes
    ps aux | grep '[s]implex-chat' | awk '{print $2}' | xargs kill -TERM 2>/dev/null || true
    sleep 2
    
    simplex-chat -d /app/profile/simplex --device-name Bot -p 3030 $SMP_ARGS $XFTP_ARGS > /app/logs/simplex-chat.log 2>&1 &
    SIMPLEX_PID=$!
    echo "SimpleX Chat CLI started with PID: $SIMPLEX_PID"
    return $SIMPLEX_PID
}

# Function to check if SimpleX Chat CLI is responding
check_simplex_health() {
    # Try to connect to the WebSocket port
    timeout 5 bash -c "echo > /dev/tcp/localhost/3030" 2>/dev/null
    return $?
}

# Function to start bot
start_bot() {
    echo "Starting bot..."
    python3 bot.py --config /app/config.yml &
    BOT_PID=$!
    echo "Bot started with PID: $BOT_PID"
}

# Start SimpleX Chat CLI
start_simplex_cli

# Wait for SimpleX Chat CLI to be ready
echo "Waiting for SimpleX Chat CLI to start..."
for i in {1..30}; do
    if check_simplex_health; then
        echo "SimpleX Chat CLI is responding on port 3030"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "SimpleX Chat CLI failed to start after 30 attempts"
        exit 1
    fi
    echo "Waiting for SimpleX Chat CLI... ($i/30)"
    sleep 2
done

# Start the bot
start_bot

# Monitor both processes
echo "Monitoring processes..."
while true; do
    # Check if SimpleX Chat CLI is still running
    if ! kill -0 $SIMPLEX_PID 2>/dev/null; then
        echo "SimpleX Chat CLI died (PID: $SIMPLEX_PID), restarting..."
        start_simplex_cli
        
        # Wait for it to be ready again
        echo "Waiting for SimpleX Chat CLI to restart..."
        for i in {1..30}; do
            if check_simplex_health; then
                echo "SimpleX Chat CLI restarted successfully"
                break
            fi
            if [ $i -eq 30 ]; then
                echo "SimpleX Chat CLI failed to restart after 30 attempts, exiting..."
                exit 1
            fi
            echo "Waiting for restart... ($i/30)"
            sleep 2
        done
    fi
    
    # Check if bot is still running
    if ! kill -0 $BOT_PID 2>/dev/null; then
        echo "Bot died (PID: $BOT_PID), restarting..."
        start_bot
    fi
    
    # Check if port 3030 is still accessible
    if ! check_simplex_health; then
        echo "SimpleX Chat CLI not responding on port 3030, restarting..."
        echo "Current PID: $SIMPLEX_PID"
        
        # Kill the process if it exists but isn't responding
        echo "Killing unresponsive SimpleX Chat CLI process: $SIMPLEX_PID"
        kill -TERM $SIMPLEX_PID 2>/dev/null || true
        sleep 5
        kill -KILL $SIMPLEX_PID 2>/dev/null || true
        
        start_simplex_cli
        
        # Wait for it to be ready
        for i in {1..30}; do
            if check_simplex_health; then
                echo "SimpleX Chat CLI restarted successfully after health check failure"
                break
            fi
            if [ $i -eq 30 ]; then
                echo "SimpleX Chat CLI failed to restart after health check failure, exiting..."
                exit 1
            fi
            echo "Waiting for restart after health check failure... ($i/30)"
            sleep 2
        done
    fi
    
    sleep 10
done