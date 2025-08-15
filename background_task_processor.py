"""
Background Task Processor for Parallel Command Execution

This module implements Option 3 from improve.md - Immediate Response with Background Processing.
Commands are acknowledged immediately while actual processing happens in parallel background tasks.
"""

import asyncio
import time
import uuid
import logging
from typing import Set, Dict, Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from plugins.universal_plugin_base import CommandContext


class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class BackgroundTask:
    """Represents a background command task"""
    task_id: str
    context: CommandContext
    command: str
    plugin_name: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    asyncio_task: Optional[asyncio.Task] = None


class BackgroundTaskProcessor:
    """
    Processes commands in parallel background tasks with immediate user feedback.
    
    Features:
    - Immediate command acknowledgment
    - Parallel execution of all commands
    - Task tracking and status updates
    - Configurable timeouts
    - Resource monitoring
    - Error isolation
    """
    
    def __init__(self, 
                 send_message_callback: Callable[[str, str], None],
                 default_timeout: int = 300,  # 5 minutes default
                 max_concurrent_tasks: int = 50):
        """
        Initialize the background task processor.
        
        Args:
            send_message_callback: Function to send messages back to users
            default_timeout: Default timeout for commands in seconds
            max_concurrent_tasks: Maximum number of concurrent background tasks
        """
        self.send_message_callback = send_message_callback
        self.default_timeout = default_timeout
        self.max_concurrent_tasks = max_concurrent_tasks
        
        # Task tracking
        self.background_tasks: Set[asyncio.Task] = set()
        self.active_tasks: Dict[str, BackgroundTask] = {}
        self.completed_tasks: Dict[str, BackgroundTask] = {}
        
        # Statistics
        self.total_tasks = 0
        self.successful_tasks = 0
        self.failed_tasks = 0
        self.timed_out_tasks = 0
        
        # Configuration
        self.task_timeouts = {
            # Fast commands (should complete quickly)
            "ping": 5,
            "help": 10,
            "status": 15,
            "commands": 10,
            
            # Medium commands  
            "plugins": 30,
            "nist": 30,
            "contacts": 30,
            "groups": 30,
            
            # Slow commands (can take time)
            "loupe": 600,    # 10 minutes for web scraping
            "youtube": 300,   # 5 minutes for video processing
            "ai": 120,       # 2 minutes for AI responses
            "ask": 120,      # 2 minutes for AI with context
            "advice": 60,    # 1 minute for advice
            "song": 90,      # 1.5 minutes for song generation
            "transcribe": 180, # 3 minutes for audio transcription
        }
        
        self.logger = logging.getLogger("background_processor")
        self.logger.info("🔄 Background Task Processor initialized")
    
    async def submit_command(self, 
                           context: CommandContext, 
                           plugin_name: str,
                           command_handler: Callable[[CommandContext], Any]) -> str:
        """
        Submit a command for background processing with immediate acknowledgment.
        
        Args:
            context: Command context with user and message info
            plugin_name: Name of the plugin handling the command
            command_handler: Async function that executes the command
            
        Returns:
            Task ID for tracking
        """
        # Check if we're at capacity
        if len(self.background_tasks) >= self.max_concurrent_tasks:
            return await self._handle_capacity_exceeded(context)
        
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        short_id = task_id[:8]
        
        # Create task record
        task_record = BackgroundTask(
            task_id=task_id,
            context=context,
            command=context.command,
            plugin_name=plugin_name,
            status=TaskStatus.PENDING,
            created_at=datetime.now()
        )
        
        self.active_tasks[task_id] = task_record
        self.total_tasks += 1
        
        # Send immediate acknowledgment to user
        await self._send_immediate_response(context, short_id)
        
        # Start background processing
        asyncio_task = asyncio.create_task(
            self._process_in_background(task_record, command_handler)
        )
        task_record.asyncio_task = asyncio_task
        
        # Track the task for cleanup
        self.background_tasks.add(asyncio_task)
        asyncio_task.add_done_callback(lambda t: self.background_tasks.discard(t))
        
        self.logger.info(f"📤 Submitted task {short_id} for command '{context.command}' from {context.user_display_name}")
        return task_id
    
    async def _send_immediate_response(self, context: CommandContext, short_id: str):
        """Send immediate acknowledgment to user"""
        emoji_map = {
            "loupe": "🔍",
            "youtube": "📺", 
            "ai": "🤖",
            "ask": "🤖",
            "nist": "🎲",
            "advice": "💡",
            "song": "🎵",
            "transcribe": "🎙️",
            "ping": "🏓",
            "help": "❓",
        }
        
        emoji = emoji_map.get(context.command, "⏳")
        
        # Estimate completion time based on command type
        timeout = self.task_timeouts.get(context.command, self.default_timeout)
        if timeout <= 30:
            time_msg = "shortly"
        elif timeout <= 120:
            time_msg = "in 1-2 minutes"
        elif timeout <= 300:
            time_msg = "in 2-5 minutes"
        else:
            time_msg = "in several minutes"
            
        response = f"{emoji} **Processing `{context.command}`**\n" \
                  f"Task ID: `{short_id}`\n" \
                  f"Expected completion: {time_msg}\n" \
                  f"You can continue using other commands while this processes."
        
        await self.send_message_callback(context.chat_id, response)
    
    async def _process_in_background(self, 
                                   task_record: BackgroundTask, 
                                   command_handler: Callable[[CommandContext], Any]):
        """Execute command in background with error handling and timeout"""
        task_record.status = TaskStatus.RUNNING
        task_record.started_at = datetime.now()
        
        short_id = task_record.task_id[:8]
        command = task_record.command
        context = task_record.context
        
        self.logger.info(f"🚀 Starting background execution for task {short_id} ({command})")
        
        try:
            # Get timeout for this specific command
            timeout = self.task_timeouts.get(command, self.default_timeout)
            
            # Execute command with timeout
            result = await asyncio.wait_for(
                command_handler(context),
                timeout=timeout
            )
            
            # Handle successful completion
            task_record.status = TaskStatus.COMPLETED
            task_record.completed_at = datetime.now()
            task_record.result = result
            
            await self._send_completion_response(task_record)
            self.successful_tasks += 1
            
            duration = (task_record.completed_at - task_record.started_at).total_seconds()
            self.logger.info(f"✅ Task {short_id} completed successfully in {duration:.1f}s")
            
        except asyncio.TimeoutError:
            # Handle timeout
            task_record.status = TaskStatus.TIMEOUT
            task_record.completed_at = datetime.now()
            task_record.error = f"Command timed out after {timeout} seconds"
            
            await self._send_timeout_response(task_record)
            self.timed_out_tasks += 1
            
            self.logger.warning(f"⏰ Task {short_id} timed out after {timeout}s")
            
        except Exception as e:
            # Handle other errors
            task_record.status = TaskStatus.FAILED
            task_record.completed_at = datetime.now()
            task_record.error = str(e)
            
            await self._send_error_response(task_record)
            self.failed_tasks += 1
            
            self.logger.error(f"❌ Task {short_id} failed: {e}", exc_info=True)
            
        finally:
            # Move task to completed list and clean up
            self._cleanup_task(task_record)
    
    async def _send_completion_response(self, task_record: BackgroundTask):
        """Send successful completion response"""
        short_id = task_record.task_id[:8]
        duration = (task_record.completed_at - task_record.started_at).total_seconds()
        
        # Add completion header with timing info
        completion_header = f"✅ **Task `{short_id}` completed** ({duration:.1f}s)\n\n"
        
        # Combine header with actual result
        full_response = completion_header + (task_record.result or "Command completed successfully.")
        
        await self.send_message_callback(task_record.context.chat_id, full_response)
    
    async def _send_timeout_response(self, task_record: BackgroundTask):
        """Send timeout response"""
        short_id = task_record.task_id[:8]
        timeout = self.task_timeouts.get(task_record.command, self.default_timeout)
        
        response = f"⏰ **Task `{short_id}` timed out**\n\n" \
                  f"Command `{task_record.command}` exceeded {timeout} second limit.\n" \
                  f"This may indicate the command is taking longer than expected or encountered an issue.\n" \
                  f"You can try running the command again."
        
        await self.send_message_callback(task_record.context.chat_id, response)
    
    async def _send_error_response(self, task_record: BackgroundTask):
        """Send error response"""
        short_id = task_record.task_id[:8]
        
        response = f"❌ **Task `{short_id}` failed**\n\n" \
                  f"Command `{task_record.command}` encountered an error:\n" \
                  f"```\n{task_record.error}\n```\n" \
                  f"Please check your command syntax and try again."
        
        await self.send_message_callback(task_record.context.chat_id, response)
    
    async def _handle_capacity_exceeded(self, context: CommandContext) -> str:
        """Handle when maximum concurrent tasks is exceeded"""
        response = f"🚫 **System at capacity**\n\n" \
                  f"Maximum number of concurrent tasks ({self.max_concurrent_tasks}) reached.\n" \
                  f"Please wait for some tasks to complete and try again.\n" \
                  f"Use `!status` to see current system load."
        
        await self.send_message_callback(context.chat_id, response)
        return "capacity_exceeded"
    
    def _cleanup_task(self, task_record: BackgroundTask):
        """Move completed task to history and clean up active tracking"""
        task_id = task_record.task_id
        
        # Move to completed tasks (keep last 100 for history)
        self.completed_tasks[task_id] = task_record
        if len(self.completed_tasks) > 100:
            # Remove oldest completed task
            oldest_id = min(self.completed_tasks.keys(), 
                          key=lambda k: self.completed_tasks[k].completed_at)
            del self.completed_tasks[oldest_id]
        
        # Remove from active tasks
        if task_id in self.active_tasks:
            del self.active_tasks[task_id]
    
    def get_status(self) -> Dict[str, Any]:
        """Get current processor status and statistics"""
        active_count = len(self.active_tasks)
        pending_count = sum(1 for t in self.active_tasks.values() if t.status == TaskStatus.PENDING)
        running_count = sum(1 for t in self.active_tasks.values() if t.status == TaskStatus.RUNNING)
        
        return {
            "active_tasks": active_count,
            "pending_tasks": pending_count,
            "running_tasks": running_count,
            "background_asyncio_tasks": len(self.background_tasks),
            "capacity_used_percent": (active_count / self.max_concurrent_tasks) * 100,
            "total_processed": self.total_tasks,
            "successful": self.successful_tasks,
            "failed": self.failed_tasks,
            "timed_out": self.timed_out_tasks,
            "success_rate": (self.successful_tasks / max(self.total_tasks, 1)) * 100,
        }
    
    def get_active_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get information about currently active tasks"""
        result = {}
        for task_id, task in self.active_tasks.items():
            short_id = task_id[:8]
            running_time = (datetime.now() - task.created_at).total_seconds()
            
            result[short_id] = {
                "command": task.command,
                "plugin": task.plugin_name,
                "status": task.status.value,
                "user": task.context.user_display_name,
                "chat": task.context.chat_id,
                "running_time": f"{running_time:.1f}s",
                "timeout": self.task_timeouts.get(task.command, self.default_timeout)
            }
        
        return result
    
    async def cancel_task(self, task_id_or_short: str) -> bool:
        """Cancel a running task by ID or short ID"""
        # Find task by full ID or short ID
        task_record = None
        for tid, task in self.active_tasks.items():
            if tid == task_id_or_short or tid.startswith(task_id_or_short):
                task_record = task
                break
        
        if not task_record:
            return False
        
        # Cancel the asyncio task
        if task_record.asyncio_task and not task_record.asyncio_task.done():
            task_record.asyncio_task.cancel()
            
            # Update task record
            task_record.status = TaskStatus.FAILED
            task_record.completed_at = datetime.now()
            task_record.error = "Task cancelled by user"
            
            # Notify user
            short_id = task_record.task_id[:8]
            response = f"🛑 **Task `{short_id}` cancelled**\n\nCommand `{task_record.command}` was cancelled."
            await self.send_message_callback(task_record.context.chat_id, response)
            
            # Clean up
            self._cleanup_task(task_record)
            self.failed_tasks += 1
            
            self.logger.info(f"🛑 Task {short_id} cancelled by user")
            return True
        
        return False