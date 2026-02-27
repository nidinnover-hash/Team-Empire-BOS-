"""
Seed memory data via the HTTP API.
Run from project root: .venv/Scripts/python scripts/seed_memory.py
Requires server running on port 8001.
"""
import urllib.request
import urllib.parse
import json

BASE = "http://localhost:8001"


def post(path, payload, token=None):
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def get(path, token):
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def login():
    data = urllib.parse.urlencode({"username": "demo@ai.com", "password": "demo"}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/auth/login",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


PROFILE_ENTRIES = [
    ("owner_name", "Demo Admin", "fact"),
    ("owner_role", "CEO", "fact"),
    ("company_name", "Nidin Nover AI", "fact"),
    ("company_focus", "AI-powered personal productivity and delegation", "goal"),
    ("primary_goal", "Automate routine decisions and email responses using AI", "goal"),
    ("communication_style", "Direct, concise, no fluff. Use bullet points for summaries.", "preference"),
    ("working_hours", "9am-6pm weekdays", "preference"),
    ("ai_rule_1", "Never send emails without explicit approval", "rule"),
    ("ai_rule_2", "Flag anything involving money, hiring, or firing for human review", "rule"),
    ("ai_rule_3", "Summarize emails in 3 bullets max", "rule"),
]

TEAM_MEMBERS = [
    {"name": "Alice Chen", "role_title": "Head of Engineering", "team": "tech",
     "skills": "Python,FastAPI,PostgreSQL,System Design", "ai_level": 4,
     "notes": "Reliable, handles backend architecture"},
    {"name": "Bob Martinez", "role_title": "Sales Manager", "team": "sales",
     "skills": "CRM,B2B Sales,Negotiation,HubSpot", "ai_level": 2,
     "notes": "Manages enterprise accounts"},
    {"name": "Carol Smith", "role_title": "Operations Lead", "team": "ops",
     "skills": "Process Design,Scheduling,Vendor Management", "ai_level": 2,
     "notes": "Keeps day-to-day running smoothly"},
    {"name": "David Park", "role_title": "Product Designer", "team": "tech",
     "skills": "Figma,UX Research,Prototyping", "ai_level": 1,
     "notes": "Leads all UI/UX decisions"},
]

DAILY_CONTEXTS = [
    {"date": "2026-02-22", "context_type": "priority",
     "content": "Review Q1 roadmap and finalize sprint goals with Alice", "related_to": "engineering"},
    {"date": "2026-02-22", "context_type": "priority",
     "content": "Follow up with Bob on enterprise pipeline - 3 deals closing this week", "related_to": "sales"},
    {"date": "2026-02-22", "context_type": "meeting",
     "content": "Standup at 10am with ops team - discuss vendor contract renewal", "related_to": "ops"},
    {"date": "2026-02-22", "context_type": "blocker",
     "content": "Waiting on legal sign-off for new contractor agreement", "related_to": "admin"},
    {"date": "2026-02-22", "context_type": "decision",
     "content": "Decided to switch email provider to Postmark for transactional emails", "related_to": "tech"},
]


def main():
    print("Logging in...")
    token = login()
    print("  OK\n")

    print("Seeding profile memory...")
    for key, value, category in PROFILE_ENTRIES:
        r = post("/api/v1/memory/profile", {"key": key, "value": value, "category": category}, token)
        if "id" in r:
            print(f"  [{category}] {key}")
        else:
            print(f"  FAIL {key}: {r}")

    print("\nSeeding team members...")
    existing = get("/api/v1/memory/team", token)
    existing_names = {m["name"] for m in existing}
    for m in TEAM_MEMBERS:
        if m["name"] in existing_names:
            print(f"  SKIP {m['name']} (already exists)")
            continue
        r = post("/api/v1/memory/team", m, token)
        if "id" in r:
            print(f"  {r['name']} - {r['role_title']} ({r['team']})")
        else:
            print(f"  FAIL {m['name']}: {r}")

    print("\nSeeding daily context...")
    existing_ctx = get("/api/v1/memory/context?for_date=2026-02-22", token)
    existing_content = {c["content"] for c in existing_ctx}
    for c in DAILY_CONTEXTS:
        if c["content"] in existing_content:
            print(f"  SKIP [{c['context_type']}] already exists")
            continue
        r = post("/api/v1/memory/context", c, token)
        if "id" in r:
            print(f"  [{r['context_type']}] {r['content'][:60]}")
        else:
            print(f"  FAIL: {r}")

    print("\nVerification:")
    profile = get("/api/v1/memory/profile", token)
    team = get("/api/v1/memory/team", token)
    context = get("/api/v1/memory/context", token)
    print(f"  Profile entries : {len(profile)}")
    print(f"  Team members    : {len(team)}")
    print(f"  Context items   : {len(context)}")


if __name__ == "__main__":
    main()
