#!/bin/bash
# Docker Compose wrapper with plugin container management

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

show_help() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Enhanced docker compose wrapper that properly manages plugin containers"
    echo ""
    echo "Commands:"
    echo "  up [options]     Start the bot (same as docker compose up)"
    echo "  down [options]   Stop the bot and all plugin containers"
    echo "  stop [options]   Stop the bot and all plugin containers"
    echo "  restart          Restart the bot and all plugin containers"
    echo "  logs [options]   Show logs (same as docker compose logs)"
    echo "  ps [options]     Show container status including plugins"
    echo "  *                Pass through to docker compose"
    echo ""
    echo "Examples:"
    echo "  $0 up -d         Start bot in background"
    echo "  $0 down          Stop bot and all plugins"
    echo "  $0 logs -f       Follow bot logs"
    echo "  $0 ps            Show all containers"
}

cleanup_plugins() {
    echo "🔍 Cleaning up plugin containers..."
    if [ -x "./stop_all_plugins.sh" ]; then
        ./stop_all_plugins.sh
    else
        echo "⚠️ stop_all_plugins.sh not found or not executable"
    fi
}

show_status() {
    echo "📊 Container Status:"
    echo ""
    echo "🤖 Main Bot:"
    docker ps --filter "name=simplex-bot-v2" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "   No bot containers running"
    echo ""
    echo "🔌 Plugin Containers:"
    docker ps --filter "label=simplex.plugin" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "   No plugin containers running"
}

case "$1" in
    "help"|"-h"|"--help")
        show_help
        ;;
    "up")
        echo "🚀 Starting SimplexBot..."
        shift
        docker compose up "$@"
        ;;
    "down")
        echo "🛑 Stopping SimplexBot and plugins..."
        shift
        docker compose down "$@"
        cleanup_plugins
        echo "✅ All containers stopped"
        ;;
    "stop")
        echo "🛑 Stopping SimplexBot and plugins..."
        shift
        docker compose stop "$@"
        cleanup_plugins
        echo "✅ All containers stopped"
        ;;
    "restart")
        echo "🔄 Restarting SimplexBot and plugins..."
        docker compose down
        cleanup_plugins
        echo "⏳ Waiting 2 seconds..."
        sleep 2
        docker compose up -d
        echo "✅ SimplexBot restarted"
        ;;
    "ps"|"status")
        shift
        show_status
        if [ "$1" != "--no-compose" ]; then
            echo ""
            echo "📋 Compose Services:"
            docker compose ps "$@"
        fi
        ;;
    "logs")
        shift
        docker compose logs "$@"
        ;;
    *)
        # Pass through to docker compose
        docker compose "$@"
        ;;
esac