# JioJoin Personal AI Agent

A production-grade personal AI assistant backend for the **JioJoin** mobile app, powered by **Groq (Llama 3.3-70b)** and built with **FastAPI**.

---

## Features

| Capability | What it does |
|---|---|
| **To-Do Tracking** | Add, list, update, delete, and search tasks with priorities, due dates, and tags |
| **Utility Tools** | Math calculator, unit converter (length, weight, temperature, data, speed), reminder management |
| **What's New** | Admin-managed announcements surface new features and offers |
| **Interest Explorer** | Personalised content recommendations based on user-saved interests |
| **Bilingual** | Responds in English or Hindi depending on the user's message |
| **Multi-turn memory** | Conversation history persisted per session in SQLite |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Mobile App (iOS / Android)               │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS / REST + JWT
┌───────────────────────────▼─────────────────────────────────────┐
│                      FastAPI  (main.py)                         │
│  /auth  /chat  /todos  /reminders  /interests  /whats-new       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                     JioJoinAgent  (agent.py)                    │
│                                                                 │
│  System Prompt → Groq API (Llama 3.3-70b) ←─┐                  │
│                       │                      │                  │
│              Tool Call Loop                  │ Tool Results     │
│                       │                      │                  │
│         ┌─────────────▼──────────────┐       │                  │
│         │      Tool Dispatcher       │───────┘                  │
│         │  todo / utility / discovery│                          │
│         └─────────────┬──────────────┘                          │
└───────────────────────┼─────────────────────────────────────────┘
                        │ async SQLAlchemy
┌───────────────────────▼─────────────────────────────────────────┐
│                   SQLite / PostgreSQL                           │
│   users · todos · reminders · user_interests                   │
│   announcements · conversation_messages                        │
└─────────────────────────────────────────────────────────────────┘
```

**Agent loop** (in `agent.py`):
1. Build messages: `[system_prompt, …history, user_message]`
2. Call Groq with tool definitions
3. If model requests tool calls → execute them → append results → go to 2
4. When model returns plain text → return to caller (max 5 rounds)

---

## Project Structure

```
jiojoin-agent/
├── main.py                  # FastAPI app & all REST endpoints
├── agent.py                 # Core agent + Groq tool-calling loop
├── auth.py                  # JWT auth (bcrypt + python-jose)
├── config.py                # Pydantic settings (reads .env)
├── database.py              # Async SQLAlchemy engine + DB init
├── models.py                # ORM models + Pydantic schemas
├── requirements.txt
├── .env.example
├── tools/
│   ├── todo_tools.py        # To-Do CRUD functions
│   ├── utility_tools.py     # Calculator, unit converter, reminders
│   ├── discovery_tools.py   # What's new, interest explorer
│   └── tool_registry.py     # Groq-compatible tool JSON schemas
└── memory/
    └── conversation.py      # In-memory + DB conversation history
```

---

## Quick Start

### 1. Clone & install

```bash
git clone <your-repo>
cd jiojoin-agent
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set your GROQ_API_KEY
# Get a free key at https://console.groq.com
```

### 3. Run the server

```bash
python main.py
# OR with hot-reload
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

---

## API Reference

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Create a new account |
| `POST` | `/auth/login` | Login and receive JWT token |
| `GET`  | `/auth/me` | Get current user profile |

All other endpoints require `Authorization: Bearer <token>` header.

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | Send a message to the AI agent |

**Request body:**
```json
{
  "message": "Add a task: Submit Q2 report by Friday, high priority",
  "session_id": "optional-uuid-for-continued-conversation"
}
```

**Response:**
```json
{
  "reply": "Done! I've added 'Submit Q2 report' as a high-priority task due this Friday. ✅",
  "session_id": "abc-123",
  "tools_used": ["add_todo"]
}
```

### To-Do

| Method | Path | Description |
|--------|------|-------------|
| `GET`    | `/todos` | List tasks (filter by status/priority) |
| `POST`   | `/todos` | Create a task |
| `PUT`    | `/todos/{id}` | Update a task |
| `DELETE` | `/todos/{id}` | Delete a task |

### Reminders

| Method | Path | Description |
|--------|------|-------------|
| `GET`    | `/reminders` | List reminders |
| `POST`   | `/reminders` | Create a reminder |
| `DELETE` | `/reminders/{id}` | Cancel a reminder |

### Interests & Discovery

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/interests` | Get user interests |
| `PUT` | `/interests` | Update user interests |
| `GET` | `/whats-new` | Latest announcements |

---

## Example Conversations

**To-Do tracking:**
```
User: Add a high-priority task to submit my project report by June 20th
Jio:  Got it! I've added "Submit project report" with high priority, due June 20th. 📋

User: Mark it as in progress
Jio:  Done! "Submit project report" is now marked as In Progress. Keep going! 💪
```

**Utility:**
```
User: What is 15% of 4500?
Jio:  15% of 4,500 = ₹675

User: Remind me to call the doctor tomorrow at 10am
Jio:  Reminder set! I'll remind you to "Call the doctor" on Wednesday at 10:00 AM. 🔔
```

**Hindi:**
```
User: मेरे सभी काम दिखाओ
Jio:  आपके to-do items यहाँ हैं:
      1. ✅ Q2 report submit करना (high priority, 20 June तक)
```

**Interest discovery:**
```
User: I'm interested in cricket and cooking
Jio:  Great! I've saved Cricket and Cooking as your interests.

User: Tell me something interesting about cricket
Jio:  Here are some fascinating cricket facts: ...
```

---

## Production Deployment

### Switch to PostgreSQL

Update `.env`:
```
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/jiojoin
```
Add `asyncpg` to `requirements.txt`.

### Deployment checklist

- [ ] Set `APP_ENV=production` in `.env`
- [ ] Use a strong random `JWT_SECRET_KEY`
- [ ] Use PostgreSQL (not SQLite) for multi-instance deployments
- [ ] Set `CORS` origins to your app's domain
- [ ] Run behind a reverse proxy (nginx / Caddy) with HTTPS
- [ ] Use gunicorn + uvicorn workers: `gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker`
- [ ] Add push notification service for reminder delivery (FCM for Android, APNs for iOS)

### Push Notifications for Reminders

The current implementation stores reminders in the DB. To actually deliver them:
1. Add a background worker (e.g. Celery + Redis, or APScheduler) that polls `reminders` where `status='active'` and `remind_at <= now()`
2. Integrate Firebase Cloud Messaging (FCM) to push to the mobile app

---

## Language Expansion

To add a new regional language (e.g. Tamil):
1. Update the `preferred_language` validator in `models.py` (add `"ta"` to the pattern)
2. Add a Tamil instruction line to `SYSTEM_PROMPT` in `agent.py`
3. The Llama model handles Tamil natively — no other changes needed

---

## License

© Reliance Jio Infocomm Ltd. Internal use only.
