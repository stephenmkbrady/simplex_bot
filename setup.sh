#!/bin/bash

# SimpleX Bot Setup Script
# This script helps set up the SimpleX Bot environment

set -e

echo "🤖 SimpleX Bot Setup Script"
echo "=================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "   Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    echo "   Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✅ Docker and Docker Compose found"

# Create required directories
echo "📁 Creating required directories..."
mkdir -p bot_profile logs media/{images,videos,documents,audio} scripts

# Set proper ownership for Docker container user (1000:1001)
echo "🔧 Setting directory ownership for Docker container..."
sudo chown -R 1000:1001 bot_profile logs media 2>/dev/null || {
    echo "⚠️  Could not set ownership automatically. You may need to run:"
    echo "   sudo chown -R 1000:1001 bot_profile logs media"
    echo "   if the bot fails to start due to permission issues."
}

# Check if configuration files exist
if [ ! -f "config.yml" ]; then
    if [ -f "config.yml.example" ]; then
        echo "📋 Creating config.yml from template..."
        cp config.yml.example config.yml
        echo "⚠️  Please edit config.yml with your server configuration"
    else
        echo "❌ config.yml.example not found"
        exit 1
    fi
else
    echo "✅ config.yml already exists"
fi

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "📋 Creating .env from template..."
        cp .env.example .env
        echo "⚠️  Please edit .env with your environment variables"
    else
        echo "❌ .env.example not found"
        exit 1
    fi
else
    echo "✅ .env already exists"
fi

# Set proper permissions
echo "🔧 Setting permissions..."
chmod +x setup.sh
chmod 644 config.yml .env

# Create gitignore to protect sensitive files
if [ ! -f ".gitignore" ]; then
    echo "📝 Creating .gitignore..."
    cat > .gitignore << EOF
# Environment and configuration
.env
config.yml

# Bot data
bot_profile/
logs/
media/

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
.coverage
.pytest_cache/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
EOF
fi

# Display configuration instructions
echo ""
echo "🎉 Setup complete! Next steps:"
echo ""
echo "1. Edit your server configuration:"
echo "   nano config.yml"
echo ""
echo "2. Set your environment variables:"
echo "   nano .env"
echo ""
echo "3. Important: Configure your custom servers in both files"
echo "   - Never use official SimpleX servers"
echo "   - Replace placeholder URLs with your actual servers"
echo ""
echo "4. Start the bot (use the enhanced wrapper):"
echo "   ./compose.sh up -d"
echo ""
echo "5. View logs:"
echo "   ./compose.sh logs -f"
echo ""
echo "6. Generate bot invitation link:"
echo "   ./generate_invite.sh"
echo ""
echo "7. Connect to someone else's invitation:"
echo "   ./connect.sh 'simplex://...'"
echo ""
echo "8. Check bot and plugin status:"
echo "   ./compose.sh ps"
echo ""
echo "📚 For more information, see README.md"
echo ""
echo "📋 HELPFUL SCRIPTS:"
echo ""
echo "• ./compose.sh - Enhanced Docker Compose wrapper"
echo "  - Properly manages plugin containers"
echo "  - Use instead of 'docker-compose' commands"
echo "  - Examples: ./compose.sh up -d, ./compose.sh down, ./compose.sh logs -f"
echo ""
echo "• ./generate_invite.sh - Generate bot invitation links"
echo "  - Creates a connection invite for others to connect to your bot"
echo "  - Automatically restarts the bot to ensure clean state"
echo "  - Share the generated link via another secure channel"
echo ""
echo "• ./connect.sh - Connect to invitation links"
echo "  - Usage: ./connect.sh 'simplex://invitation_link_here'"
echo "  - Connects your bot to someone else's SimpleX invitation"
echo "  - Uses both WebSocket API and CLI fallback methods"
echo ""
echo "• ./run_tests.sh - Run bot tests"
echo "  - Examples: ./run_tests.sh config, ./run_tests.sh integration"

# Warn about configuration
echo ""
echo "⚠️  IMPORTANT SECURITY NOTES:"
echo "   - Never commit .env or config.yml to version control"
echo "   - Use only your own SMP and XFTP servers"
echo "   - Keep your bot profile and logs secure"
echo ""

echo "✅ Setup script completed successfully!"