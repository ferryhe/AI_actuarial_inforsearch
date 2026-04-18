"""
API service layer.

Services are organized by domain:
- task_service:   Task-related queries and operations
- chat_service:   Chat/conversation operations
- collection_service: Collection and data operations
"""

from __future__ import annotations

from ai_actuarial.api.services.task_service import (
    ensure_conversation_schema,
    get_catalog_stats,
    get_chunk_generation_stats,
    get_file_catalog_stats,
    get_markdown_conversion_stats,
    get_or_create_conversation,
    get_schedule_status,
    get_scheduled_tasks,
    get_task_log,
    list_active_tasks,
    list_conversations,
    list_task_history,
    parse_task_history_limit,
    parse_task_log_tail,
)
from ai_actuarial.api.services.chat_service import (
    add_message,
    delete_conversation,
    ensure_conversation_schema,
    get_conversation_messages,
    get_or_create_conversation,
    list_conversations,
    update_conversation_title,
)
from ai_actuarial.api.services.collection_service import (
    browse_folder,
    start_collection,
)

__all__ = [
    # task_service
    "get_catalog_stats",
    "get_chunk_generation_stats",
    "get_file_catalog_stats",
    "get_markdown_conversion_stats",
    "get_schedule_status",
    "get_scheduled_tasks",
    "get_task_log",
    "list_active_tasks",
    "list_task_history",
    "parse_task_history_limit",
    "parse_task_log_tail",
    # chat_service
    "add_message",
    "delete_conversation",
    "ensure_conversation_schema",
    "get_conversation_messages",
    "get_or_create_conversation",
    "list_conversations",
    "update_conversation_title",
    # collection_service
    "browse_folder",
    "start_collection",
]
