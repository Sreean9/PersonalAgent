"""
tools/tool_registry.py – Groq-compatible tool definitions (JSON Schema).

This is the single source of truth for what tools the LLM can call.
Each entry maps directly to a function in the tools package.
"""

TOOLS: list[dict] = [
    # ── To-Do ─────────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "add_todo",
            "description": (
                "Create a new to-do item / task for the user. "
                "Use this when the user wants to add, save, or remember a task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short title of the task (required).",
                    },
                    "description": {
                        "type": "string",
                        "description": "Longer description or notes about the task.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Task priority. Defaults to 'medium'.",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date/time in ISO-8601 format (e.g. '2025-06-15' or '2025-06-15T09:00:00').",
                    },
                    "tags": {
                        "type": "string",
                        "description": "Comma-separated tags (e.g. 'work,urgent').",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": (
                "Retrieve the user's to-do items. "
                "Use this when the user asks to see, show, or list their tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "Filter by task status.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Filter by priority.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tasks to return (default 20).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": (
                "Update an existing to-do item (change status, title, due date, etc.). "
                "Use this when the user marks a task as done, edits a task, or reschedules it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "string",
                        "description": "The ID of the to-do item to update.",
                    },
                    "title": {"type": "string", "description": "New title."},
                    "description": {"type": "string", "description": "New description."},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "due_date": {
                        "type": "string",
                        "description": "New due date in ISO-8601 format.",
                    },
                    "tags": {"type": "string"},
                },
                "required": ["todo_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_todo",
            "description": "Permanently delete a to-do item by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "string",
                        "description": "The ID of the to-do item to delete.",
                    },
                },
                "required": ["todo_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_todos",
            "description": "Search the user's to-do items by keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword to match against task titles and descriptions.",
                    },
                },
                "required": ["query"],
            },
        },
    },

    # ── Utility ───────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate a mathematical expression. "
                "Use for arithmetic, percentages (e.g. '15% of 2400'), square roots, trigonometry, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate (e.g. '(45 * 12) / 7', 'sqrt(144)', '15% of 2400').",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_units",
            "description": (
                "Convert a value between units. "
                "Supports length (km, miles, feet), weight (kg, lbs), volume (litres, gallons), "
                "temperature (Celsius, Fahrenheit, Kelvin), speed (kph, mph), and data size (MB, GB)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "number",
                        "description": "The numeric value to convert.",
                    },
                    "from_unit": {
                        "type": "string",
                        "description": "Source unit (e.g. 'km', 'kg', 'celsius', 'gb').",
                    },
                    "to_unit": {
                        "type": "string",
                        "description": "Target unit (e.g. 'miles', 'lbs', 'fahrenheit', 'mb').",
                    },
                },
                "required": ["value", "from_unit", "to_unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": (
                "Set a reminder for the user at a specific time. "
                "Use when the user wants to be reminded about something later."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "What to remind the user about.",
                    },
                    "remind_at": {
                        "type": "string",
                        "description": "When to remind – ISO-8601 or natural language like 'tomorrow at 9am', 'in 2 hours'.",
                    },
                },
                "required": ["title", "remind_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "Show the user's upcoming or past reminders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "triggered", "cancelled"],
                        "description": "Filter by reminder status. Defaults to 'active'.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reminder",
            "description": "Cancel an active reminder by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "string",
                        "description": "The ID of the reminder to cancel.",
                    },
                },
                "required": ["reminder_id"],
            },
        },
    },

    # ── Discovery ─────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_whats_new",
            "description": (
                "Fetch the latest announcements, feature updates, or offers in JioJoin. "
                "Use when the user asks 'what's new', 'any updates', 'show announcements', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["feature", "offer", "general"],
                        "description": "Filter announcements by category.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of announcements to return (default 5).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explore_interest",
            "description": (
                "Help the user explore a topic they're interested in. "
                "Use when the user asks to 'discover something new', 'tell me about X', "
                "or wants personalised content recommendations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The specific topic to explore (e.g. 'cricket', 'cooking', 'investing'). Leave blank to use saved interests.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_interests",
            "description": (
                "Save or update the user's interest topics so the agent can personalise responses. "
                "Use when the user tells you their hobbies, interests, or preferences."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of interest topics (e.g. ['cricket', 'cooking', 'finance']).",
                    },
                },
                "required": ["topics"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_interests",
            "description": "Retrieve the user's saved interest topics.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
