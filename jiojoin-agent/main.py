"""
main.py – JioJoin Personal AI Agent API

FastAPI application exposing:
  POST /auth/register    – create account
  POST /auth/login       – get JWT token

  POST /chat             – main agent chat endpoint (auth required)

  GET  /todos            – list to-dos
  POST /todos            – create a to-do
  PUT  /todos/{id}       – update a to-do
  DELETE /todos/{id}     – delete a to-do

  GET  /reminders        – list reminders
  POST /reminders        – create a reminder
  DELETE /reminders/{id} – cancel a reminder

  GET  /interests        – get user interests
  PUT  /interests        – update user interests

  GET  /whats-new        – latest announcements

  GET  /health           – service health check
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db, init_db
from auth import (
    hash_password, verify_password,
    create_access_token, get_current_user,
)
from models import (
    User, Todo, Reminder, UserInterest,
    UserRegister, UserLogin, TokenResponse, UserOut,
    TodoCreate, TodoUpdate, TodoOut,
    ReminderCreate, ReminderOut,
    InterestUpdate, InterestOut,
    AnnouncementOut,
    ChatRequest, ChatResponse,
    TodoStatus, TodoPriority, ReminderStatus,
)
from agent import agent
from memory import conversation as conv_memory
from tools.todo_tools import (
    add_todo as tool_add_todo,
    list_todos as tool_list_todos,
    update_todo as tool_update_todo,
    delete_todo as tool_delete_todo,
)
from tools.utility_tools import (
    set_reminder as tool_set_reminder,
    list_reminders as tool_list_reminders,
    cancel_reminder as tool_cancel_reminder,
)
from tools.discovery_tools import (
    get_whats_new as tool_get_whats_new,
    get_user_interests as tool_get_interests,
    update_user_interests as tool_update_interests,
)

# ─────────────────────────────────────────────────────────────────────────────
#  App setup
# ─────────────────────────────────────────────────────────────────────────────

settings = get_settings()
logging.basicConfig(
    level=logging.DEBUG if not settings.is_production else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting JioJoin Agent API…")
    await init_db()
    logger.info("Database initialised.")
    yield
    logger.info("Shutting down JioJoin Agent API.")


app = FastAPI(
    title="JioJoin Personal AI Agent",
    description="Production-grade personal AI assistant for the JioJoin platform.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Tighten to your mobile app origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "JioJoin Agent API", "version": "1.0.0"}


# ─────────────────────────────────────────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=TokenResponse, status_code=201, tags=["Auth"])
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new JioJoin user."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered.")

    user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        preferred_language=payload.preferred_language,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.name)
    return TokenResponse(access_token=token, user_id=user.id, name=user.name)


@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate and receive a JWT token."""
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(user.id, user.name)
    return TokenResponse(access_token=token, user_id=user.id, name=user.name)


@app.get("/auth/me", response_model=UserOut, tags=["Auth"])
async def me(current_user: User = Depends(get_current_user)):
    return current_user


# ─────────────────────────────────────────────────────────────────────────────
#  Chat – the main agent endpoint
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a message to the JioJoin AI agent and receive a response.

    - If `session_id` is omitted, a new session is created.
    - The agent has access to all tools: to-do, utility, discovery.
    - Responses are in English or Hindi depending on the user's message language.
    """
    session_id = payload.session_id or str(uuid.uuid4())

    # Load conversation history
    history = await conv_memory.get_history(db, current_user.id, session_id)

    # Run the agent
    try:
        reply, tools_used = await agent.run(
            user_message=payload.message,
            history=history,
            db=db,
            user_id=current_user.id,
        )
    except Exception as exc:
        logger.exception("Agent error for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=500, detail="The agent encountered an error. Please try again.")

    # Persist the exchange
    await conv_memory.add_message(db, current_user.id, session_id, "user", payload.message)
    await conv_memory.add_message(db, current_user.id, session_id, "assistant", reply)

    return ChatResponse(reply=reply, session_id=session_id, tools_used=tools_used)


# ─────────────────────────────────────────────────────────────────────────────
#  To-Do REST endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/todos", response_model=List[TodoOut], tags=["To-Do"])
async def get_todos(
    status: Optional[TodoStatus] = Query(None),
    priority: Optional[TodoPriority] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await tool_list_todos(
        db, current_user.id,
        status=status.value if status else None,
        priority=priority.value if priority else None,
        limit=limit,
    )
    return result["todos"]


@app.post("/todos", response_model=TodoOut, status_code=201, tags=["To-Do"])
async def create_todo(
    payload: TodoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await tool_add_todo(
        db, current_user.id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority.value,
        due_date=payload.due_date.isoformat() if payload.due_date else None,
        tags=payload.tags,
    )
    return result["todo"]


@app.put("/todos/{todo_id}", response_model=TodoOut, tags=["To-Do"])
async def update_todo_endpoint(
    todo_id: str,
    payload: TodoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await tool_update_todo(
        db, current_user.id, todo_id,
        title=payload.title,
        description=payload.description,
        status=payload.status.value if payload.status else None,
        priority=payload.priority.value if payload.priority else None,
        due_date=payload.due_date.isoformat() if payload.due_date else None,
        tags=payload.tags,
    )
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found."))
    return result["todo"]


@app.delete("/todos/{todo_id}", status_code=204, tags=["To-Do"])
async def delete_todo_endpoint(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await tool_delete_todo(db, current_user.id, todo_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found."))


# ─────────────────────────────────────────────────────────────────────────────
#  Reminders REST endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/reminders", response_model=List[ReminderOut], tags=["Reminders"])
async def get_reminders(
    status: Optional[ReminderStatus] = Query(ReminderStatus.ACTIVE),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await tool_list_reminders(db, current_user.id, status=status.value if status else "active")
    return result["reminders"]


@app.post("/reminders", response_model=ReminderOut, status_code=201, tags=["Reminders"])
async def create_reminder(
    payload: ReminderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await tool_set_reminder(
        db, current_user.id,
        title=payload.title,
        remind_at=payload.remind_at.isoformat(),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Could not create reminder."))
    return result["reminder"]


@app.delete("/reminders/{reminder_id}", status_code=204, tags=["Reminders"])
async def cancel_reminder_endpoint(
    reminder_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await tool_cancel_reminder(db, current_user.id, reminder_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found."))


# ─────────────────────────────────────────────────────────────────────────────
#  Interests REST endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/interests", response_model=List[InterestOut], tags=["Interests"])
async def get_interests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await tool_get_interests(db, current_user.id)
    return result["interests"]


@app.put("/interests", response_model=List[InterestOut], tags=["Interests"])
async def update_interests(
    payload: InterestUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await tool_update_interests(db, current_user.id, payload.topics)
    result = await tool_get_interests(db, current_user.id)
    return result["interests"]


# ─────────────────────────────────────────────────────────────────────────────
#  What's New REST endpoint
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/whats-new", response_model=List[AnnouncementOut], tags=["Discovery"])
async def whats_new(
    category: Optional[str] = Query(None, regex="^(feature|offer|general)$"),
    limit: int = Query(5, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await tool_get_whats_new(db, category=category, limit=limit)
    return result["announcements"]


# ─────────────────────────────────────────────────────────────────────────────
#  Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=not settings.is_production,
        log_level="debug" if not settings.is_production else "info",
    )
