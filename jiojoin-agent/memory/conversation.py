"""
memory/conversation.py – Conversation history management.

Architecture:
  • In-memory dict keyed by session_id for fast access during active requests.
  • Messages are also persisted to the DB (ConversationMessage table) so history
    survives server restarts and can be fetched for existing sessions.
  • On first access of a session, history is loaded from DB into memory.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import ConversationMessage

settings = get_settings()

# In-memory store: session_id → list of Groq-format message dicts
_memory: Dict[str, List[dict]] = defaultdict(list)
_loaded_sessions: set[str] = set()
_lock = asyncio.Lock()


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

async def get_history(
    db: AsyncSession,
    user_id: str,
    session_id: str,
) -> List[dict]:
    """
    Return the conversation history for a session as a list of Groq message dicts.
    Loads from DB on first access.
    """
    async with _lock:
        if session_id not in _loaded_sessions:
            await _load_from_db(db, user_id, session_id)
            _loaded_sessions.add(session_id)

    return list(_memory[session_id])


async def add_message(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    role: str,
    content: str,
    tool_name: Optional[str] = None,
) -> None:
    """
    Append a message to both in-memory history and the DB.

    Args:
        role: 'user', 'assistant', or 'tool'.
        content: Message text content.
        tool_name: For tool messages, the name of the tool that produced this result.
    """
    msg: dict = {"role": role, "content": content}

    async with _lock:
        _memory[session_id].append(msg)

        # Trim to max window to control context size
        max_msgs = settings.max_conversation_history
        if len(_memory[session_id]) > max_msgs:
            _memory[session_id] = _memory[session_id][-max_msgs:]

    # Persist asynchronously
    db_msg = ConversationMessage(
        user_id=user_id,
        session_id=session_id,
        role=role,
        content=content,
        tool_name=tool_name,
    )
    db.add(db_msg)
    await db.commit()


async def add_messages_bulk(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    messages: List[dict],
) -> None:
    """Bulk-add a list of message dicts (used after a tool-calling exchange)."""
    for msg in messages:
        await add_message(
            db=db,
            user_id=user_id,
            session_id=session_id,
            role=msg["role"],
            content=msg.get("content") or "",
            tool_name=msg.get("name"),
        )


async def clear_session(session_id: str) -> None:
    """Remove a session from the in-memory cache (does not delete DB records)."""
    async with _lock:
        _memory.pop(session_id, None)
        _loaded_sessions.discard(session_id)


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _load_from_db(
    db: AsyncSession,
    user_id: str,
    session_id: str,
) -> None:
    """Load the last N messages from DB into the in-memory dict."""
    max_msgs = settings.max_conversation_history
    stmt = (
        select(ConversationMessage)
        .where(
            ConversationMessage.user_id == user_id,
            ConversationMessage.session_id == session_id,
        )
        .order_by(ConversationMessage.created_at.asc())
        .limit(max_msgs)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    _memory[session_id] = [
        {"role": row.role, "content": row.content}
        for row in rows
    ]
