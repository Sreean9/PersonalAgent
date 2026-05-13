"""
agent.py – JioJoin Personal AI Agent

Core logic:
  1. Receives a user message and conversation history.
  2. Calls Groq (Llama 3.3-70b) with the full tool registry.
  3. If the model requests tool calls, executes them against the DB.
  4. Feeds tool results back into the model.
  5. Loops until a final text reply is produced.
  6. Returns the reply and the list of tools used.

The agent is stateless per-call; state lives in the ConversationManager and DB.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from groq import AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from tools.tool_registry import TOOLS
from tools.todo_tools import (
    add_todo, list_todos, update_todo, delete_todo, search_todos,
)
from tools.utility_tools import (
    calculate, convert_units,
    set_reminder, list_reminders, cancel_reminder,
)
from tools.discovery_tools import (
    get_whats_new, explore_interest,
    update_user_interests, get_user_interests,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
#  System prompt
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Jio, a friendly and intelligent personal AI assistant built into the JioJoin app.

You help users with four core areas:
1. **To-Do List** – add, view, update, search, and delete tasks
2. **Utility** – perform calculations, convert units, set and manage reminders
3. **What's New** – show the latest JioJoin features, offers, and announcements
4. **Explore Interests** – help users discover content and ideas based on their interests

Guidelines:
- Always use the available tools to act; never make up data.
- Respond in the same language the user writes in (English or Hindi).
- Be concise, warm, and helpful. Avoid long monologues unless the user asks for detail.
- When listing tasks or reminders, present them in a clean, easy-to-read format.
- If you don't know a user's interests yet, ask them before calling explore_interest.
- For reminders, confirm the time back to the user in a human-readable format.
- When a tool returns an error, explain it simply and suggest what the user can do.
- Never expose internal IDs in your response unless the user specifically asks for them.

आप हिंदी में भी उतनी ही कुशलता से जवाब दे सकते हैं। जब उपयोगकर्ता हिंदी में लिखें, तो हिंदी में जवाब दें।
"""

# Maximum number of tool-call rounds to prevent infinite loops
MAX_TOOL_ROUNDS = 5


# ─────────────────────────────────────────────────────────────────────────────
#  Tool dispatcher
# ─────────────────────────────────────────────────────────────────────────────

async def _dispatch_tool(
    name: str,
    args: dict,
    db: AsyncSession,
    user_id: str,
) -> str:
    """
    Route a tool call from the LLM to the correct Python function.
    Returns the tool result as a JSON string.
    """
    try:
        result: dict

        # ── To-Do ──────────────────────────────────────────────────────────
        if name == "add_todo":
            result = await add_todo(db, user_id, **args)
        elif name == "list_todos":
            result = await list_todos(db, user_id, **args)
        elif name == "update_todo":
            result = await update_todo(db, user_id, **args)
        elif name == "delete_todo":
            result = await delete_todo(db, user_id, **args)
        elif name == "search_todos":
            result = await search_todos(db, user_id, **args)

        # ── Utility ────────────────────────────────────────────────────────
        elif name == "calculate":
            result = calculate(**args)
        elif name == "convert_units":
            result = convert_units(**args)
        elif name == "set_reminder":
            result = await set_reminder(db, user_id, **args)
        elif name == "list_reminders":
            result = await list_reminders(db, user_id, **args)
        elif name == "cancel_reminder":
            result = await cancel_reminder(db, user_id, **args)

        # ── Discovery ──────────────────────────────────────────────────────
        elif name == "get_whats_new":
            result = await get_whats_new(db, **args)
        elif name == "explore_interest":
            result = await explore_interest(db, user_id, **args)
        elif name == "update_user_interests":
            result = await update_user_interests(db, user_id, **args)
        elif name == "get_user_interests":
            result = await get_user_interests(db, user_id)

        else:
            result = {"error": f"Unknown tool: {name}"}

    except Exception as exc:
        logger.exception("Tool '%s' raised an exception: %s", name, exc)
        result = {"error": str(exc)}

    return json.dumps(result, default=str)


# ─────────────────────────────────────────────────────────────────────────────
#  Agent
# ─────────────────────────────────────────────────────────────────────────────

class JioJoinAgent:
    """
    Stateless agent that wraps Groq with a tool-calling agentic loop.

    Usage:
        agent = JioJoinAgent()
        reply, tools_used = await agent.run(
            user_message="Add a task: Submit Q2 report by Friday",
            history=[...],       # prior Groq-format messages
            db=db_session,
            user_id="abc-123",
        )
    """

    def __init__(self) -> None:
        self._client = AsyncGroq(api_key=settings.groq_api_key)

    async def run(
        self,
        user_message: str,
        history: list[dict],
        db: AsyncSession,
        user_id: str,
    ) -> tuple[str, list[str]]:
        """
        Run the agent and return (reply_text, list_of_tool_names_used).

        Args:
            user_message: The latest message from the user.
            history: Previous conversation messages (Groq format).
            db: Active async DB session.
            user_id: Authenticated user's ID for scoping tool calls.
        """
        tools_used: list[str] = []

        # Build the initial messages list
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_message},
        ]

        for round_num in range(MAX_TOOL_ROUNDS):
            logger.debug("Agent round %d – sending %d messages", round_num + 1, len(messages))

            response = await self._client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=settings.agent_temperature,
                max_tokens=2048,
            )

            choice = response.choices[0]
            message = choice.message

            # ── No tool calls → final answer ──────────────────────────────
            if not message.tool_calls:
                final_reply = message.content or ""
                logger.debug("Agent finished after %d round(s). Tools used: %s", round_num + 1, tools_used)
                return final_reply, tools_used

            # ── Tool calls requested ──────────────────────────────────────
            # Append the assistant's partial message (with tool_calls)
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            # Execute each tool and collect results
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tools_used.append(tool_name)

                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                logger.debug("Calling tool '%s' with args: %s", tool_name, args)
                tool_result = await _dispatch_tool(tool_name, args, db, user_id)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": tool_result,
                })

        # If we exhausted all rounds, return a safe fallback
        logger.warning("Agent reached max tool rounds (%d) for user %s", MAX_TOOL_ROUNDS, user_id)
        return (
            "I'm having a bit of trouble completing that right now. Please try again or rephrase your request.",
            tools_used,
        )


# Singleton – instantiated once at startup, shared across all requests
agent = JioJoinAgent()
