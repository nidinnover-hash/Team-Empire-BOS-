# Spec: Brain + Memory + Email
**For Codex implementation. Read this fully before writing any code.**

---

## Overview

Three builds in priority order:
1. **Brain** — Wire OpenAI + Claude to the agent orchestrator (real AI thinking)
2. **Memory** — Profile, team, and decision memory (what makes it a clone)
3. **Email** — Gmail integration (read, summarize, draft replies)

Do NOT skip steps. Do NOT merge them into one big change.
Each step must work independently before moving to the next.

---

## STEP 1 — BRAIN (Wire Real AI to the Orchestrator)

### What Exists Now (Do Not Delete)
- `app/agents/orchestrator.py` — keyword routing + hardcoded plan (keep the structure, replace the logic)
- `app/services/command.py` — OpenAI already wired here for `/commands` endpoint (use this as reference)
- `app/core/config.py` — OPENAI_API_KEY already loaded from .env

### What to Build

#### 1A. Add Anthropic (Claude) support to config
File: `app/core/config.py`

Add these fields to the `Settings` class:
```
ANTHROPIC_API_KEY: str | None = None
DEFAULT_AI_PROVIDER: str = "openai"   # "openai" or "anthropic"
AGENT_MODEL_OPENAI: str = "gpt-4o-mini"
AGENT_MODEL_ANTHROPIC: str = "claude-haiku-4-5-20251001"
```

File: `.env.example`
Add:
```
ANTHROPIC_API_KEY=your-anthropic-key-here
DEFAULT_AI_PROVIDER=openai
AGENT_MODEL_OPENAI=gpt-4o-mini
AGENT_MODEL_ANTHROPIC=claude-haiku-4-5-20251001
```

#### 1B. Add anthropic to requirements
File: `requirements.txt`
Add: `anthropic>=0.40.0`

#### 1C. Create AI router service
New file: `app/services/ai_router.py`

Purpose: single function that calls either OpenAI or Claude based on config.
No other file should call OpenAI or Anthropic directly — everything goes through this.

```python
async def call_ai(
    system_prompt: str,
    user_message: str,
    memory_context: str = "",
    provider: str | None = None,   # None = use DEFAULT_AI_PROVIDER from config
    max_tokens: int = 800,
) -> str:
    """
    Route to OpenAI or Anthropic based on config.
    Returns the response text.
    Returns a fallback message on error (never raises).
    """
```

Implementation rules:
- If provider is "openai": use AsyncOpenAI, model from AGENT_MODEL_OPENAI
- If provider is "anthropic": use anthropic.AsyncAnthropic, model from AGENT_MODEL_ANTHROPIC
- If key is missing or placeholder: return "AI not configured. Set API key in .env."
- Always wrap in try/except. Never let an AI call crash the API.
- If memory_context is provided, prepend it to the system prompt like:
  ```
  [MEMORY CONTEXT]
  {memory_context}
  [END MEMORY]

  {system_prompt}
  ```

#### 1D. Rewrite the orchestrator to use real AI
File: `app/agents/orchestrator.py`

Keep: `AgentChatRequest`, `AgentChatResponse`, `route_role()` function (keyword routing is fine for now)

Replace: `build_plan()` with a real async function:

```python
async def run_agent(request: AgentChatRequest, memory_context: str = "") -> AgentChatResponse:
```

Each role has a specific system prompt. Use these exact prompts:

**CEO Clone:**
```
You are Nidin's CEO Clone. You think strategically.
Your job: help Nidin make high-level decisions, prioritize, and delegate.
Always respond with: what the decision is, who should act on it, and what approval is needed.
Be direct. No fluff. Max 3 bullet points unless asked for more.
```

**Ops Manager Clone:**
```
You are Nidin's Ops Manager Clone. You manage daily operations.
Your job: assign tasks, track blockers, manage the team's daily plan.
Always respond with: task list, who is assigned, what is blocked.
Be specific. Use names and numbers.
```

**Sales Lead Clone:**
```
You are Nidin's Sales Lead Clone. You manage leads and conversions.
Your job: summarize lead status, identify who needs follow-up, draft outreach.
Always respond with: lead count, conversion rate context, next action per lead segment.
```

**Tech PM Clone:**
```
You are Nidin's Tech PM Clone. You manage the tech team.
Your job: convert goals into dev tasks, track progress, flag technical risks.
Always respond with: current sprint status, next tasks, any blockers.
```

The function should:
1. Call `route_role()` to get the role
2. Get the system prompt for that role
3. Call `call_ai(system_prompt, message, memory_context)`
4. Parse the response
5. Return AgentChatResponse with:
   - role: the routed role
   - plan: split AI response into lines (as list)
   - draft_action: the full AI response text
   - requires_approval: True if message contains "send", "assign", "change", "spend"

#### 1E. Update the agents endpoint
File: `app/api/v1/endpoints/agents.py`

The `/api/v1/agents/chat` POST endpoint should:
- Accept `AgentChatRequest`
- Call `await run_agent(request, memory_context="")` (memory_context empty for now, filled in Step 2)
- Return `AgentChatResponse`
- Log the command as an event (use existing `record_action`)

---

## STEP 2 — MEMORY

### What Exists Now
- `app/memory/` folder — completely empty
- `app/models/` — has User, Event, Approval, Task, Project etc.
- `app/db/base.py` — DeclarativeBase ready for new models

### What to Build

#### 2A. New migration
File: `alembic/versions/20260221_0005_add_memory_tables.py`

Create 3 new tables:

**profile_memory** — Who Nidin is and how he operates
```sql
id          SERIAL PRIMARY KEY
key         VARCHAR(100) NOT NULL  -- e.g. "business_rule", "personal_goal", "tone"
value       TEXT NOT NULL          -- the actual memory content
category    VARCHAR(50)            -- "identity", "rules", "goals", "preferences"
created_at  TIMESTAMP DEFAULT now()
updated_at  TIMESTAMP DEFAULT now()
UNIQUE(key)
```

**team_members** — Your actual team (not the generic users table)
```sql
id              SERIAL PRIMARY KEY
user_id         INT REFERENCES users(id)   -- links to auth user if they have one
name            VARCHAR(100) NOT NULL
role_title      VARCHAR(100)               -- "Developer", "Tech Head", "Manager", "Counsellor"
team            VARCHAR(50)                -- "tech", "sales", "ops", "admin"
reports_to_id   INT REFERENCES team_members(id)
skills          TEXT                       -- comma-separated or JSON text
ai_level        INT DEFAULT 1              -- 1=none, 2=basic, 3=intermediate, 4=advanced, 5=expert
current_project VARCHAR(200)
notes           TEXT
is_active       BOOL DEFAULT true
created_at      TIMESTAMP DEFAULT now()
```

**daily_context** — Today's active priorities (short-term memory)
```sql
id              SERIAL PRIMARY KEY
date            DATE NOT NULL
context_type    VARCHAR(50)   -- "priority", "meeting", "blocker", "decision"
content         TEXT NOT NULL
related_to      VARCHAR(100)  -- name or entity it relates to
created_at      TIMESTAMP DEFAULT now()
```

#### 2B. New ORM models
- `app/models/memory.py` — ProfileMemory, TeamMember, DailyContext models
- Follow exact same pattern as `app/models/user.py`

#### 2C. New schemas
- `app/schemas/memory.py` — Pydantic schemas for all 3 models
- Include Create, Update, and Read schemas

#### 2D. New services
- `app/services/memory.py`

Required functions:
```python
async def get_profile_memory(db) -> list[ProfileMemory]
async def upsert_profile_memory(db, key, value, category) -> ProfileMemory
async def get_team_members(db, team=None) -> list[TeamMember]
async def create_team_member(db, data) -> TeamMember
async def update_team_member(db, member_id, data) -> TeamMember
async def get_daily_context(db, date=None) -> list[DailyContext]
async def add_daily_context(db, data) -> DailyContext
async def build_memory_context(db) -> str
```

**`build_memory_context()`** is the most important function.
It builds a single text string that gets injected into every AI call.
Format:
```
PROFILE:
- [key]: [value]
- [key]: [value]

TEAM (tech):
- [name] | [role_title] | AI Level: [ai_level] | Project: [current_project]

TODAY'S PRIORITIES:
- [content] (related to: [related_to])
```

#### 2E. New endpoints
File: `app/api/v1/endpoints/memory.py`

```
GET  /api/v1/memory/profile              → list all profile memory (CEO only)
POST /api/v1/memory/profile              → add/update a memory key (CEO only)
GET  /api/v1/memory/team                 → list team members (MANAGER+)
POST /api/v1/memory/team                 → add team member (ADMIN+)
PATCH /api/v1/memory/team/{id}           → update team member (ADMIN+)
GET  /api/v1/memory/context              → get today's daily context (MANAGER+)
POST /api/v1/memory/context              → add context item (MANAGER+)
```

All writes must log an event via `record_action()`.

#### 2F. Wire memory into the agent
File: `app/api/v1/endpoints/agents.py`

Update the `/api/v1/agents/chat` endpoint:
1. Call `await build_memory_context(db)` before calling run_agent
2. Pass the result as `memory_context` to `run_agent()`

Now the AI knows who Nidin is, who his team is, and what today's priorities are.

#### 2G. Register the new router
File: `app/api/v1/router.py`

Add: `from app.api.v1.endpoints import memory` and include its router.

---

## STEP 3 — EMAIL (Gmail Integration)

### What Exists Now
- `.env.example` has GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI already
- `app/core/config.py` has GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI already
- Integration framework exists (`app/models/integration.py`, service, endpoint)

### What to Build

#### 3A. Add dependencies
File: `requirements.txt`
Add:
```
google-auth>=2.27.0
google-auth-oauthlib>=1.2.0
google-api-python-client>=2.118.0
```

#### 3B. New migration
File: `alembic/versions/20260221_0006_add_emails_table.py`

Create table: **emails**
```sql
id              SERIAL PRIMARY KEY
organization_id INT REFERENCES organizations(id)
gmail_id        VARCHAR(200) UNIQUE     -- Gmail message ID
thread_id       VARCHAR(200)
from_address    VARCHAR(300)
to_address      VARCHAR(300)
subject         VARCHAR(500)
body_text       TEXT
received_at     TIMESTAMP
is_read         BOOL DEFAULT false
category        VARCHAR(50)             -- "team", "lead", "vendor", "other"
ai_summary      TEXT                    -- AI-generated summary
draft_reply     TEXT                    -- AI-drafted reply (pending approval)
reply_approved  BOOL DEFAULT false
reply_sent      BOOL DEFAULT false
created_at      TIMESTAMP DEFAULT now()
```

#### 3C. Gmail OAuth tool
New file: `app/tools/gmail.py`

Required functions:
```python
def get_gmail_auth_url() -> str
    # Returns Google OAuth URL for Gmail scope
    # Scope: https://www.googleapis.com/auth/gmail.modify

async def exchange_code_for_tokens(code: str) -> dict
    # Exchanges auth code for access_token + refresh_token
    # Returns: {"access_token": ..., "refresh_token": ..., "expires_at": ...}

async def fetch_recent_emails(access_token: str, max_results: int = 20) -> list[dict]
    # Fetches recent emails from Gmail API
    # Returns list of: {gmail_id, thread_id, from, to, subject, body, received_at}

async def send_email(access_token: str, to: str, subject: str, body: str) -> bool
    # Sends email via Gmail API
    # Returns True on success
    # THIS FUNCTION REQUIRES AN APPROVED ACTION — never call directly
```

#### 3D. Email service
New file: `app/services/email_service.py`

Required functions:
```python
async def sync_emails(db, access_token: str, org_id: int) -> int
    # Fetches recent emails, stores new ones in DB
    # Returns count of new emails synced
    # Logs a sync event via record_action()

async def summarize_email(db, email_id: int) -> str
    # Calls call_ai() with the email body
    # System prompt: "Summarize this email in 2-3 bullet points. Be concise."
    # Saves ai_summary to the email record
    # Returns the summary

async def draft_reply(db, email_id: int, instruction: str = "") -> str
    # Calls call_ai() with the email body + instruction
    # System prompt: "You are Nidin's assistant. Draft a professional reply to this email."
    # Saves draft_reply to the email record
    # Sets reply_approved = False
    # Creates an approval request (approval_type = "send_message")
    # Returns the draft text

async def send_approved_reply(db, email_id: int, actor_user_id: int) -> bool
    # ONLY called after approval is granted
    # Sends via gmail.send_email()
    # Sets reply_sent = True
    # Logs event
    # Returns True on success
```

#### 3E. Email endpoints
New file: `app/api/v1/endpoints/email.py`

```
GET  /api/v1/email/auth-url                     → returns Gmail OAuth URL (ADMIN+)
POST /api/v1/email/callback?code={code}         → exchanges code, saves tokens to Integration table (ADMIN+)
POST /api/v1/email/sync                         → syncs recent emails from Gmail (ADMIN+)
GET  /api/v1/email/inbox                        → list emails with summaries (MANAGER+)
POST /api/v1/email/{id}/summarize               → AI summarizes the email (MANAGER+)
POST /api/v1/email/{id}/draft-reply             → AI drafts a reply, creates approval (MANAGER+)
POST /api/v1/email/{id}/send                    → sends ONLY if approval exists + approved (CEO/ADMIN)
```

**Critical rule:** `/email/{id}/send` must check that:
1. An approval record exists for this email
2. Its status is "approved"
3. Actor has CEO or ADMIN role
If any check fails: return 403 with reason.

#### 3F. Store Gmail tokens securely
After OAuth callback:
- Store access_token + refresh_token in the existing `integrations` table
- `type = "gmail"`
- `config_json = {"access_token": ..., "refresh_token": ..., "expires_at": ...}`
- Never log tokens in events table
- Never return tokens in API responses

#### 3G. Register the new router
File: `app/api/v1/router.py`
Add email router.

---

## Implementation Order for Codex

```
Step 1A → 1B → 1C → 1D → 1E   (Brain)   Test: POST /api/v1/agents/chat returns real AI text
Step 2A → 2B → 2C → 2D → 2E → 2F → 2G  (Memory)  Test: AI response includes team context
Step 3A → 3B → 3C → 3D → 3E → 3F → 3G  (Email)   Test: sync + summarize + draft flow works
```

---

## What Codex Must NOT Do
- Do NOT delete any existing endpoints or models
- Do NOT change the RBAC system
- Do NOT change the approval workflow logic
- Do NOT auto-send emails — always create approval first
- Do NOT store API keys or tokens in the events table
- Do NOT skip migrations — every new table needs an Alembic migration

---

## Definition of Done

**Brain is done when:**
- POST /api/v1/agents/chat returns a real AI-generated response
- Switching DEFAULT_AI_PROVIDER between "openai" and "anthropic" works

**Memory is done when:**
- Profile memory can be set via API
- Team members can be added via API
- Agent chat responses include memory context

**Email is done when:**
- Gmail OAuth flow completes
- Emails sync to DB
- AI summary generated on demand
- Draft reply creates an approval request
- Send only works after approval is granted
