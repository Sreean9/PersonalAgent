"""
tools/todo_tools.py – To-Do list CRUD operations used as agent tools.

Each function receives a DB session and user_id so it can safely scope
queries to the authenticated user only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models import Todo, TodoStatus, TodoPriority


# ── Helpers ───────────────────────────────────────────────────────────────────

def _todo_to_dict(todo: Todo) -> dict:
    return {
        "id": todo.id,
        "title": todo.title,
        "description": todo.description,
        "status": todo.status.value,
        "priority": todo.priority.value,
        "due_date": todo.due_date.isoformat() if todo.due_date else None,
        "tags": todo.tags,
        "created_at": todo.created_at.isoformat(),
        "updated_at": todo.updated_at.isoformat(),
    }


def _parse_priority(priority_str: Optional[str]) -> TodoPriority:
    if not priority_str:
        return TodoPriority.MEDIUM
    try:
        return TodoPriority(priority_str.lower())
    except ValueError:
        return TodoPriority.MEDIUM


def _parse_status(status_str: Optional[str]) -> Optional[TodoStatus]:
    if not status_str:
        return None
    try:
        return TodoStatus(status_str.lower())
    except ValueError:
        return None


# ── Tool functions ────────────────────────────────────────────────────────────

async def add_todo(
    db: AsyncSession,
    user_id: str,
    title: str,
    description: Optional[str] = None,
    priority: Optional[str] = "medium",
    due_date: Optional[str] = None,
    tags: Optional[str] = None,
) -> dict:
    """
    Create a new to-do item for the user.

    Args:
        title: Short title of the task.
        description: Optional longer description.
        priority: 'low', 'medium', or 'high'. Defaults to 'medium'.
        due_date: ISO-8601 date/datetime string (e.g. '2025-06-15').
        tags: Comma-separated tags (e.g. 'work,urgent').

    Returns:
        The created to-do item as a dict.
    """
    parsed_due: Optional[datetime] = None
    if due_date:
        try:
            parsed_due = datetime.fromisoformat(due_date)
            if parsed_due.tzinfo is None:
                parsed_due = parsed_due.replace(tzinfo=timezone.utc)
        except ValueError:
            pass  # ignore malformed date – item is still created

    todo = Todo(
        user_id=user_id,
        title=title.strip(),
        description=description,
        priority=_parse_priority(priority),
        due_date=parsed_due,
        tags=tags,
    )
    db.add(todo)
    await db.commit()
    await db.refresh(todo)
    return {"success": True, "todo": _todo_to_dict(todo)}


async def list_todos(
    db: AsyncSession,
    user_id: str,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """
    Retrieve the user's to-do items, optionally filtered by status or priority.

    Args:
        status: Filter by 'pending', 'in_progress', 'completed', or 'cancelled'.
        priority: Filter by 'low', 'medium', or 'high'.
        limit: Maximum number of results (default 20).

    Returns:
        A list of to-do items.
    """
    stmt = select(Todo).where(Todo.user_id == user_id)

    parsed_status = _parse_status(status)
    if parsed_status:
        stmt = stmt.where(Todo.status == parsed_status)

    parsed_priority = _parse_priority(priority) if priority else None
    if parsed_priority and priority:
        stmt = stmt.where(Todo.priority == parsed_priority)

    stmt = stmt.order_by(Todo.created_at.desc()).limit(min(limit, 50))

    result = await db.execute(stmt)
    todos = result.scalars().all()
    return {"todos": [_todo_to_dict(t) for t in todos], "count": len(todos)}


async def update_todo(
    db: AsyncSession,
    user_id: str,
    todo_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_date: Optional[str] = None,
    tags: Optional[str] = None,
) -> dict:
    """
    Update one or more fields on an existing to-do item.

    Args:
        todo_id: The ID of the to-do to update.
        title: New title (optional).
        description: New description (optional).
        status: New status – 'pending', 'in_progress', 'completed', 'cancelled'.
        priority: New priority – 'low', 'medium', 'high'.
        due_date: New due date as ISO-8601 string.
        tags: New comma-separated tags.

    Returns:
        The updated to-do item, or an error message if not found.
    """
    result = await db.execute(
        select(Todo).where(Todo.id == todo_id, Todo.user_id == user_id)
    )
    todo = result.scalar_one_or_none()
    if not todo:
        return {"success": False, "error": f"To-do with id '{todo_id}' not found."}

    if title is not None:
        todo.title = title.strip()
    if description is not None:
        todo.description = description
    if status is not None:
        parsed = _parse_status(status)
        if parsed:
            todo.status = parsed
    if priority is not None:
        todo.priority = _parse_priority(priority)
    if due_date is not None:
        try:
            parsed_due = datetime.fromisoformat(due_date)
            todo.due_date = parsed_due.replace(tzinfo=timezone.utc) if parsed_due.tzinfo is None else parsed_due
        except ValueError:
            pass
    if tags is not None:
        todo.tags = tags

    todo.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(todo)
    return {"success": True, "todo": _todo_to_dict(todo)}


async def delete_todo(
    db: AsyncSession,
    user_id: str,
    todo_id: str,
) -> dict:
    """
    Permanently delete a to-do item.

    Args:
        todo_id: The ID of the to-do to delete.

    Returns:
        Success flag.
    """
    result = await db.execute(
        select(Todo).where(Todo.id == todo_id, Todo.user_id == user_id)
    )
    todo = result.scalar_one_or_none()
    if not todo:
        return {"success": False, "error": f"To-do with id '{todo_id}' not found."}

    await db.delete(todo)
    await db.commit()
    return {"success": True, "message": f"To-do '{todo.title}' deleted."}


async def search_todos(
    db: AsyncSession,
    user_id: str,
    query: str,
) -> dict:
    """
    Search to-do items by keyword in the title or description.

    Args:
        query: The search term.

    Returns:
        Matching to-do items.
    """
    from sqlalchemy import or_
    stmt = (
        select(Todo)
        .where(
            Todo.user_id == user_id,
            or_(
                Todo.title.ilike(f"%{query}%"),
                Todo.description.ilike(f"%{query}%"),
            ),
        )
        .order_by(Todo.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    todos = result.scalars().all()
    return {"todos": [_todo_to_dict(t) for t in todos], "count": len(todos)}
