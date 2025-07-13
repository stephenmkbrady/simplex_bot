# SimpleX Chat Bot Architecture

## Overview

The SimpleX Chat Bot is designed with a clean, modular architecture that separates concerns and provides extensibility through a universal plugin system. This document describes the core components, message flow, and architectural patterns.

## Core Components

### 1. Main Bot Orchestrator (`bot.py`)
- **SimplexChatBot**: Main orchestrator class using dependency injection
- **CommandRegistry**: Legacy command system with plugin integration
- Manages bot lifecycle, signal handling, and component initialization
- Coordinates between plugins, WebSocket manager, and message handlers

### 2. WebSocket Manager (`websocket_manager.py`)
- Handles WebSocket connection to SimpleX CLI
- Manages message correlation, reconnection, and CLI process lifecycle
- Provides message sending/receiving abstraction
- Handles CLI corruption detection and restart logic

### 3. Message Handler (`message_handler.py`)
- Processes incoming messages from SimpleX CLI
- Routes commands to appropriate handlers (plugins or legacy commands)
- Handles file downloads and media processing
- Determines correct chat context (group vs direct) for responses

### 4. Universal Plugin System
- **UniversalPluginManager** (`plugins/universal_plugin_manager.py`): Plugin discovery, loading, and lifecycle management
- **UniversalBotPlugin** (`plugins/universal_plugin_base.py`): Base class for all plugins
- **SimplexBotAdapter** (`plugins/simplex_adapter.py`): Adapter between universal plugins and SimpleX-specific functionality

### 5. Supporting Components
- **ConfigManager** (`config_manager.py`): Configuration management with YAML support
- **AdminManager** (`admin_manager.py`): Role-based access control
- **InviteManager** (`invite_manager.py`): Connection invite management
- **FileDownloadManager** (`file_download_manager.py`): XFTP file handling
- **XFTPClient** (`xftp_client.py`): XFTP protocol client

## Message Flow Architecture

Think of the bot like a restaurant kitchen where orders (messages) flow through different stations before being served back to customers.

### Incoming Message Journey

```
SimpleX CLI → WebSocket → WebSocketManager → MessageHandler → CommandRegistry → PluginManager → Plugin
                                         ↓                                                     ↓
                                     File Handler                                        Status Messages
                                         ↓                                                     ↓
                                   FileDownloadManager                                  SimplexBotAdapter
                                                                                             ↓
                                                                                      WebSocketManager
```

### Step-by-Step Message Processing (Explained Simply)

**Step 1: Message Reception** (The "Front Door")
- Someone sends a message in SimpleX Chat (like "!yt https://youtube.com/watch?v=123")
- SimpleX CLI receives this message and converts it to a JSON format
- The JSON gets sent over a WebSocket connection to our bot
- **WebSocketManager** acts like a receptionist, receiving and organizing these messages

**Step 2: Message Analysis** (The "Order Taker")
- **MessageHandler** is like a waiter who examines each message
- It figures out: Who sent it? Was it in a group or direct message? What did they say?
- Most importantly: Is this a command (does it start with `!`) or just a regular message?
- If it's not a command, the message is ignored (like someone just saying "hello")

**Step 3: Command Routing** (The "Kitchen Manager")
- If it IS a command, MessageHandler calls **CommandRegistry.execute_command()**
- CommandRegistry is like a kitchen manager who decides which chef (plugin) should handle this order
- It creates a **CommandContext** (like an order ticket) with all the important info:
  - What command was requested (`yt`)
  - What arguments were given (`https://youtube.com/watch?v=123`)
  - Who ordered it (`cosmic`)
  - Where to send the result (group `botgroup_11` or direct to `cosmic`)

**Step 4: Finding the Right Chef** (The "Plugin Selection")
- **PluginManager** looks through all available plugins
- Each plugin says "I can handle these commands" (YouTube plugin handles `yt`, `youtube`, `video`)
- When a match is found, the plugin gets the CommandContext

**Step 5: Cooking the Order** (The "Plugin Execution")
- The **Plugin** (like YouTube plugin) starts working on the request
- It might send "status messages" like "🔄 Extracting subtitles..." (like a chef saying "starting your order")
- These status messages go immediately back to the customer via **SimplexBotAdapter**
- The plugin does the actual work (downloading video, processing with AI, etc.)
- Finally, it returns the complete result (like a finished meal)

**Step 6: Serving the Result** (The "Final Delivery")
- The final result goes back through: Plugin → CommandRegistry → MessageHandler
- **MessageHandler** makes sure it gets delivered to the right place (group or direct message)
- The result appears in SimpleX Chat where the original command was sent

### Two Types of Responses (Why This Matters)

**Status Messages** (The "Your order is being prepared" updates):
- Sent immediately during processing
- Go through: Plugin → SimplexBotAdapter → WebSocketManager → SimpleX CLI
- Examples: "🔄 Extracting subtitles...", "🤖 Generating summary..."

**Final Results** (The "Here's your finished order"):
- Sent when the plugin is completely done
- Go through: Plugin → CommandRegistry → MessageHandler → WebSocketManager → SimpleX CLI  
- Examples: The complete YouTube video summary

Both types MUST go to the same place (if you ordered in a group, both status updates and final result should appear in that group).

## Plugin Architecture

### Universal Plugin System

The bot uses a universal plugin architecture that allows plugins to work with different chat platforms (SimpleX, Matrix, Discord, etc.) without being rewritten:

```
Plugin
  ↓
UniversalBotPlugin (base class)
  ↓
Platform-Specific Adapter (SimplexBotAdapter)
  ↓
Bot Platform (SimpleX, Matrix, etc.)
```

**How This Works:**
- **Plugin**: Specialized functionality module (YouTube processor, Home Assistant controller, etc.)
- **UniversalBotPlugin**: Base class that defines the interface all plugins must implement
- **Platform Adapter**: Translates between the plugin's universal interface and platform-specific messaging
- **Bot Platform**: The actual chat platform (SimpleX, Matrix) with its own message formats and protocols

### Plugin Lifecycle

**1. Discovery**:
- PluginManager scans the `plugins/external/` directory
- Finds all Python files that contain plugin classes
- Identifies which plugins are available to load

**2. Loading**:
- Imports plugin modules and creates instances of plugin classes
- Each plugin declares what commands it can handle
- Plugin announces which platforms it supports

**3. Initialization**:
- Calls `plugin.initialize(adapter)` with platform adapter
- Plugin learns how to communicate with the bot via the adapter
- Plugin validates it can work with the current platform

**4. Registration**:
- Plugin registers supported commands and platform compatibility
- Bot indexes which plugin handles which commands
- Plugin is marked as ready for use

**5. Execution**:
- Plugin handles commands via `handle_command(context)`
- Plugin receives CommandContext with all necessary information
- Plugin processes request and returns result or sends status messages

**6. Cleanup**:
- Plugin cleanup on shutdown or reload
- Plugin releases any resources (file handles, network connections, etc.)
- Plugin state is properly saved if needed

### Plugin Types

#### Core Plugin (`plugins/external/core/`)
- Basic bot functionality (ping, status, uptime)
- Plugin management commands (reload, enable, disable)
- System information and health checks

#### SimpleX Plugin (`plugins/external/simplex/`)
- SimpleX-specific functionality
- Contact and group management
- Invite generation and management
- Debug and admin commands

#### YouTube Plugin (`plugins/external/youtube/`)
- YouTube video processing
- Subtitle extraction and AI summarization
- Q&A functionality with video content
- Configurable AI models and processing options

#### Home Assistant Plugin (`plugins/external/homeassistant/`)
- Smart home integration
- Entity state monitoring and control
- Wake-on-LAN functionality
- REST API integration with caching

#### Additional Plugins
- **AI Plugin**: General AI assistance and utilities
- **Auth Plugin**: Authentication and authorization
- **Database Plugin**: Database operations and queries
- **Example Plugin**: Plugin development template

## Context and Routing

### CommandContext Structure

```python
@dataclass
class CommandContext:
    command: str           # Command name (e.g., "yt", "ping")
    args: List[str]       # Parsed command arguments
    args_raw: str         # Raw argument string
    user_id: str          # User identifier
    chat_id: str          # Chat identifier (contact name or group name)
    user_display_name: str # Display name of user
    platform: BotPlatform # Platform enum (SIMPLEX, MATRIX)
    raw_message: Dict     # Original message data
```

### Chat Context Routing

The bot handles two types of chat contexts:

1. **Direct Messages**
   - `chat_id = contact_name`
   - Messages sent directly to the contact
   - Used for private interactions

2. **Group Messages**
   - `chat_id = group_name`
   - Messages sent to the group
   - Maintains group conversation context

### Context Creation and Chat Routing

The bot uses a unified approach for determining where messages should be sent (group vs direct chat):

**Primary Context Creation** (`plugins/simplex_adapter.py:70-76`):
- **SimplexBotAdapter.normalize_context()** is the master method for creating CommandContext objects
- Analyzes the incoming message data to determine chat type (`"direct"` or `"group"`)
- Sets `chat_id` appropriately:
  - For **direct messages**: `chat_id = contact_name` (e.g., "cosmic")
  - For **group messages**: `chat_id = group_name` (e.g., "botgroup_11")

**CommandRegistry Usage** (`bot.py:198-211`):
- When processing plugin commands, CommandRegistry calls the adapter's `normalize_context()` method
- Creates a standardized message structure to pass to the adapter
- This ensures plugin status messages use the same routing logic as other messages

**MessageHandler Final Delivery** (`message_handler.py:136-144`):
- Handles delivery of final command results
- Uses its own logic to determine group vs direct context
- Routes final responses to the correct chat destination

## Configuration Management

### Configuration Hierarchy

1. **Bot Configuration** (`config.yml`)
   - WebSocket URL, media settings, admin config
   - Global bot behavior and security settings

2. **Plugin Configuration**
   - Each plugin can have its own `config.yaml`
   - Plugin-specific settings and API keys
   - Hot-reloadable configuration

3. **Admin Configuration** (`admin_config.yml`)
   - User permissions and role assignments
   - Command access control
   - Public vs admin command separation

## Security Model

### Access Control

- **Admin Users**: Full access to all commands
- **Public Users**: Limited to public commands only
- **Command-Level Permissions**: Granular control per command
- **Platform Integration**: SimpleX's built-in privacy and security

### Input Validation

- Command parsing with proper quote handling
- File type validation for downloads
- Size limits and security checks
- Escaped command character handling

## Extension Points

### Adding New Plugins

1. Create plugin directory in `plugins/external/`
2. Implement `UniversalBotPlugin` base class
3. Define supported commands and platforms
4. Add plugin configuration if needed
5. Plugin manager auto-discovers and loads

### Adding New Platforms

1. Create platform-specific adapter (like `SimplexBotAdapter`)
2. Implement `BotAdapter` interface
3. Add platform enum to `BotPlatform`
4. Update plugin compatibility as needed

### Adding New Features

- **File Processing**: Extend `FileDownloadManager`
- **AI Integration**: Add to existing AI plugin or create new one
- **External APIs**: Create dedicated plugin with proper error handling
- **Database Operations**: Extend database plugin functionality

## Performance Considerations

### Hot Reloading

- File system monitoring for plugin changes
- Graceful plugin reload without bot restart
- Configuration reload without service interruption

### Resource Management

- Connection pooling for external APIs
- Caching strategies for expensive operations
- Memory management for large file processing
- WebSocket reconnection and error recovery

### Scalability

- Modular plugin architecture allows selective loading
- Stateless plugin design for horizontal scaling
- Configuration-driven feature enablement
- Efficient message correlation and routing

## Development Guidelines

### Code Organization

- Clear separation of concerns between components
- Dependency injection for testability
- Interface-based design for extensibility
- Comprehensive error handling and logging

### Testing Strategy

- Unit tests for individual components
- Integration tests for message flow
- Plugin isolation for reliable testing
- Mock external dependencies

### Logging and Monitoring

- Structured logging with correlation IDs
- Debug logging for troubleshooting
- Performance monitoring and metrics
- Error tracking and alerting

## Future Architecture Improvements

### Known Issues

1. **Context Creation Inconsistency**: Multiple code paths create CommandContext with different logic
2. **Plugin Communication**: No inter-plugin communication mechanism
3. **State Management**: Limited persistent state capabilities
4. **Error Recovery**: Incomplete error recovery for some failure modes

### Planned Enhancements

1. **Unified Context Creation**: Single source of truth for CommandContext
2. **Plugin Registry**: Centralized plugin discovery and management
3. **Event System**: Plugin-to-plugin communication via events
4. **Persistent Storage**: Database integration for stateful plugins
5. **Metrics Collection**: Comprehensive monitoring and analytics
6. **Multi-Platform Support**: Full Matrix and other platform implementations