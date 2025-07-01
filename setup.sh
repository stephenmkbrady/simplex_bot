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
echo "4. Start the bot:"
echo "   docker-compose up -d"
echo ""
echo "5. View logs:"
echo "   docker-compose logs -f simplex-bot"
echo ""
echo "6. Connect to a SimpleX address:"
echo "   docker-compose exec simplex-bot python bot.py --connect 'simplex://...'"
echo ""
echo "📚 For more information, see README.md"

# Warn about configuration
echo ""
echo "⚠️  IMPORTANT SECURITY NOTES:"
echo "   - Never commit .env or config.yml to version control"
echo "   - Use only your own SMP and XFTP servers"
echo "   - Keep your bot profile and logs secure"
echo ""

echo "✅ Setup script completed successfully!"