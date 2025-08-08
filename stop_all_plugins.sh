#!/bin/bash
# Stop all plugin containers when the main bot stops

echo "🛑 Stopping all plugin containers..."

# Find all containers with simplex.plugin label
PLUGIN_CONTAINERS=$(docker ps --filter "label=simplex.plugin" --format "{{.Names}}" 2>/dev/null)

if [ -z "$PLUGIN_CONTAINERS" ]; then
    echo "📋 No plugin containers found"
    exit 0
fi

echo "🔍 Found plugin containers:"
echo "$PLUGIN_CONTAINERS" | while read container; do
    echo "   - $container"
done

# Stop plugin containers
echo "🛑 Stopping plugin containers..."
for container in $PLUGIN_CONTAINERS; do
    echo "   Stopping $container..."
    docker stop "$container" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "   ✅ Stopped $container"
    else
        echo "   ❌ Failed to stop $container"
    fi
done

# Remove stopped containers
echo "🗑️ Removing plugin containers..."
for container in $PLUGIN_CONTAINERS; do
    echo "   Removing $container..."
    docker rm "$container" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "   ✅ Removed $container"
    else
        echo "   ⚠️ Could not remove $container (may already be removed)"
    fi
done

echo "✅ Plugin container cleanup complete"