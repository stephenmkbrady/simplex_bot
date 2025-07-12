# SimpleX Chat Bot

A Python bot for SimpleX Chat with Docker support that can automatically process invites, log messages to daily files, download media, and respond to commands using custom SMP/XFTP servers.

## Features

- **Hot Reload Development**: Real-time plugin updates without restarting the bot
- **Daily Message Logging**: Separate log files for each day with timestamps
- **Media Downloads**: Automatic download and storage of images, videos, and documents
- **Custom Server Support**: Uses your own SMP/XFTP servers (no official servers)
- **Command Line Interface**: Accept connections via CLI arguments
- **Configuration Management**: YAML-based configuration with environment variables
- **Docker Support**: Complete containerized setup with persistent storage
- **Extensible Commands**: !help, !echo, !status, and custom command framework

## Prerequisites

1. **Docker & Docker Compose**: For containerized deployment
2. **Custom SimpleX Servers**: Your own SMP and XFTP server addresses
3. **Configuration Files**: config.yml and .env files (templates provided)

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd SIMPLEX_BOT

# Create required directories
mkdir -p bot_profile logs media

# Copy configuration templates  
cp config.yml.example config.yml
cp .env.example .env
```

### 2. Configure Your Setup

Edit `config.yml` with your custom servers:
```yaml
servers:
  smp:
    - "smp://your-server.com"
  xftp:
    - "xftp://your-files-server.com"
```

Edit `.env` with your environment variables:
```bash
SMP_SERVER_1=smp://your-server.com
XFTP_SERVER_1=xftp://your-files-server.com
WEBSOCKET_URL=ws://simplex-chat:3030
```

### 3. Start the Bot

```bash
# Build and start the entire stack
docker-compose up --build -d

# View logs
docker-compose logs -f simplex-bot

# Connect to a SimpleX address
docker-compose exec simplex-bot python bot.py --connect "simplex://invitation-link"
```

## Configuration

### config.yml Structure

```yaml
# Server Configuration  
servers:
  smp:
    - "${SMP_SERVER_1}"
    - "${SMP_SERVER_2}"
  xftp:
    - "${XFTP_SERVER_1}" 
    - "${XFTP_SERVER_2}"

# Bot Settings
bot:
  name: "SimpleX Bot"
  websocket_url: "${WEBSOCKET_URL}"
  auto_accept_contacts: true
  
# Logging Configuration
logging:
  daily_rotation: true
  message_log_separate: true
  retention_days: 30
  
# Media Settings  
media:
  download_enabled: true
  max_file_size: "100MB"
  allowed_types: ["image", "video", "document"]
  storage_path: "./media"
```

### Environment Variables (.env)

```bash
# Server Configuration
SMP_SERVER_1=smp://your-primary-server.com
SMP_SERVER_2=smp://your-backup-server.com  
XFTP_SERVER_1=xftp://your-files-server.com
XFTP_SERVER_2=xftp://your-backup-files-server.com

# Bot Configuration
WEBSOCKET_URL=ws://simplex-chat:3030
BOT_NAME=SimpleX Bot

# Security
AUTO_ACCEPT_CONTACTS=true
MAX_FILE_SIZE=104857600
```

## Usage

### Available Commands

- **!help** - Show available commands and bot information
- **!echo <text>** - Echo back the provided text  
- **!status** - Display bot status, server information, and connection details

### Command Line Options

```bash
# Connect to a specific SimpleX address
python bot.py --connect "simplex://address"

# Accept a one-time invitation link
python bot.py --connect "https://simplex.chat/invitation#..."

# Join a group via invite link
python bot.py --group "https://simplex.chat/contact#..."

# Display help
python bot.py --help
```

### Daily Operations

**View Logs:**
```bash
# Application logs
tail -f logs/bot-$(date +%Y-%m-%d).log

# Message logs  
tail -f logs/messages-$(date +%Y-%m-%d).log

# Docker logs
docker-compose logs -f simplex-bot
```

**Check Media Downloads:**
```bash
ls -la media/
```

**Bot Status:**
```bash
docker-compose exec simplex-bot python -c "
import bot; 
bot.get_status()
"
```

## File Structure

```
SIMPLEX_BOT/
├── bot.py                 # Main bot implementation
├── requirements.txt       # Python dependencies  
├── docker-compose.yml     # Docker orchestration
├── Dockerfile            # Bot container definition
├── config.yml.example   # Configuration template
├── config.yml           # Bot configuration
├── .env.example         # Environment template
├── .env                 # Environment variables
├── README.md            # This documentation
├── dev_log.md          # Development notes
├── bot_profile/        # SimpleX profile data (persistent)
├── logs/              # Daily log files
│   ├── bot-2025-01-01.log      # Application logs
│   ├── messages-2025-01-01.log # Message logs  
│   └── ...
├── media/             # Downloaded files
│   ├── images/
│   ├── videos/
│   └── documents/
└── scripts/           # Utility scripts
    ├── setup.sh       # Initial setup
    └── cleanup.sh     # Maintenance
```

## Development

### Current Implementation Status

**Working Features:**
- WebSocket connection to SimpleX Chat CLI with automatic reconnection
- Full command processing system with admin permissions
- YAML configuration loading with environment variable substitution
- Daily log rotation and separate message logging
- Media download via XFTP protocol with type validation
- Custom server configuration (SMP/XFTP)
- CLI argument processing for connections and invites
- Comprehensive admin commands (!contacts, !groups, !debug, !plugins, !commands)
- Plugin system with hot reload capability
- Contact and group management
- Invite generation and processing
- Async correlation system for CLI responses

**Test Coverage:**
- **Main Code**: 4,372 lines across 11 core Python files
- **Test Suite**: 6,601 lines across 35 test files
- **Test Types**: Unit tests, integration tests, WebSocket tests, CLI tests, comprehensive functional tests
- **Core Functionality**: ✅ VERIFIED (WebSocket, contacts, CLI commands)

### Adding Custom Commands

Once the bot is updated, you can add commands by extending the framework:

```python  
# In the updated bot implementation
self.commands = {
    "!help": self.handle_help,
    "!echo": self.handle_echo, 
    "!status": self.handle_status,
    "!custom": self.handle_custom,  # Your command
}

async def handle_custom(self, contact_name: str, args: list = None) -> str:
    """Handle custom command logic"""
    return "Custom response"
```

## Troubleshooting

### Common Issues

1. **Configuration Problems**
   - Check `config.yml` syntax and environment variable substitution
   - Verify `.env` file contains all required variables
   - Ensure custom server addresses are correct

2. **Docker Issues**  
   - Run `docker-compose logs` to check service startup
   - Verify volume mounts with `docker-compose config`
   - Check network connectivity between containers

3. **Connection Problems**
   - Verify SimpleX Chat CLI starts with custom server configuration
   - Check WebSocket connectivity on port 3030
   - Review bot connection logs for specific errors

4. **Media Download Issues**
   - Check XFTP server configuration
   - Verify media directory permissions
   - Review file size limits in configuration

### Debug Commands

```bash
# Check container status  
docker-compose ps

# View detailed logs
docker-compose logs --tail=100 simplex-bot
docker-compose logs --tail=100 simplex-chat

# Test configuration
docker-compose config

# Access bot container  
docker-compose exec simplex-bot bash

# Test WebSocket connection
docker-compose exec simplex-bot python -c "
import asyncio, websockets, json
async def test():
    async with websockets.connect('ws://simplex-chat:3030') as ws:
        await ws.send(json.dumps({'corrId': 'test', 'cmd': '/contacts'}))
        print(await ws.recv())
asyncio.run(test())
"
```

## Security Considerations

1. **Custom Servers Only**: Never use official SimpleX servers to maintain privacy
2. **Environment Variables**: Keep sensitive configuration in `.env` files (not committed to git)
3. **File Validation**: Validate downloaded media files for safety
4. **Access Control**: Implement contact filtering and command permissions
5. **Log Security**: Ensure logs don't contain sensitive data

## Important Links

- [SimpleX Chat CLI Documentation](https://simplex.chat/docs/cli.html)
- [SimpleX Chat GitHub](https://github.com/simplex-chat/simplex-chat)
- [Bot Examples](https://github.com/simplex-chat/simplex-chat/tree/stable/apps/simplex-bot)
- [Advanced Bot Examples](https://github.com/simplex-chat/simplex-chat/tree/stable/apps/simplex-bot-advanced)

## Support

For development questions and support:
1. Review `dev_log.md` for detailed technical analysis
2. Check the SimpleX Chat documentation
3. Examine the official bot examples
4. Join SimpleX development groups for community support