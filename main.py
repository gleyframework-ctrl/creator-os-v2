import os
import time
import logging
import threading
import urllib.request
import json
import re
import base64
from typing import List, Optional, Dict
from datetime import datetime, date
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

# ============================================================
# LOGGING & ENV
# ============================================================
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

# NVIDIA — using the proven working model
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct").strip()
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

log.info(f"🔍 NVIDIA Model: {NVIDIA_MODEL}")

# PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor

PGHOST = os.environ.get("PGHOST", "").strip()
PGDATABASE = os.environ.get("PGDATABASE", "").strip()
PGUSER = os.environ.get("PGUSER", "").strip()
PGPASSWORD = os.environ.get("PGPASSWORD", "").strip()
PGPORT = os.environ.get("PGPORT", "5432").strip()

DATABASE_CONNECTED = False

def get_db_connection():
    try:
        if not all([PGHOST, PGDATABASE, PGUSER, PGPASSWORD]):
            return None
        return psycopg2.connect(
            host=PGHOST, database=PGDATABASE, user=PGUSER,
            password=PGPASSWORD, port=PGPORT, cursor_factory=RealDictCursor
        )
    except Exception as e:
        log.error(f"DB Error: {e}")
        return None

def init_db():
    global DATABASE_CONNECTED
    conn = get_db_connection()
    if not conn:
        log.warning("⚠️ Using in‑memory fallback")
        return
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS profiles (member_id TEXT PRIMARY KEY, data JSONB, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS journeys (member_id TEXT PRIMARY KEY, data JSONB, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS standups (id SERIAL PRIMARY KEY, member_id TEXT, data JSONB, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS wins (id SERIAL PRIMARY KEY, member_id TEXT, data JSONB, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS scores (id SERIAL PRIMARY KEY, member_id TEXT, score INT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS strategy_docs (member_id TEXT PRIMARY KEY, data JSONB, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS proof_files (id SERIAL PRIMARY KEY, member_id TEXT, data JSONB, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS member_notifications (id SERIAL PRIMARY KEY, member_id TEXT, notification_type TEXT, message TEXT, sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, read_at TIMESTAMP, action_taken BOOLEAN DEFAULT FALSE)")
        conn.commit()
        cur.close(); conn.close()
        DATABASE_CONNECTED = True
        log.info("✅ PostgreSQL tables ready")
    except Exception as e:
        log.error(f"Init DB error: {e}")

init_db()

# In‑memory fallback
PROFILES_DB = {}
JOURNEY_DB = {}
WINS_DB = {}
SCORES_DB = {}
PROOF_DB = {}

app = FastAPI(title="E5 AI Coach OS", version="5.5")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ============================================================
# JOURNEY MAP (12 tasks) — UNCHANGED
# ============================================================
JOURNEY_MAP = {
    "Phase 1": {
        "name": "Foundation", "days": "1-30", "focus": "Offer, Avatar, and First Content", "sub_coach": "Foundation Strategist",
        "tasks": [
            {"id": "p1_t1", "name": "Define Core Offer & Value Stack", "deadline_day": 3, "why": "Without a clear offer, all traffic is wasted.", "frameworks": ["AVOCADO Opening Offers", "Value Equation (Hormozi)"], "deliverables": ["Written offer in one sentence", "3 core outcomes you deliver", "Price and guarantee defined"]},
            {"id": "p1_t2", "name": "Identify Target Avatar & Pain Points", "deadline_day": 7, "why": "Speaking to everyone means converting no one.", "frameworks": ["Dream Customer/Follower (TTB)", "Pain Stack Analysis"], "deliverables": ["Avatar name, age, situation", "3 biggest fears", "3 biggest desires", "Where they hang out online"]},
            {"id": "p1_t3", "name": "Create & Publish First Content Piece", "deadline_day": 14, "why": "The first piece proves you can execute.", "frameworks": ["Hook Mastery (Kallaway)", "Anti-viral content strategy"], "deliverables": ["Published TikTok or YouTube Short", "Link to the video", "View count after 48 hours"]},
            {"id": "p1_t4", "name": "Write & Test DM Outreach Template", "deadline_day": 21, "why": "DMs are your fastest path to revenue.", "frameworks": ["SIPE DM Framework", "Ladder of Tiny Yeses"], "deliverables": ["3-message DM sequence written", "Sent to 10 people", "Reply rate reported"]}
        ]
    },
    "Phase 2": {
        "name": "Traffic", "days": "31-60", "focus": "Content volume, Inbound system, Outbound system", "sub_coach": "Traffic & Growth Specialist",
        "tasks": [
            {"id": "p2_t1", "name": "Double Content Volume & Consistency", "deadline_day": 37, "why": "Traffic is the fuel.", "frameworks": ["Content Engine (E5)", "VAGEL weekly rotation"], "deliverables": ["7 pieces published this week", "Links to all 7", "Best performing piece identified"]},
            {"id": "p2_t2", "name": "Build Inbound System (Comment to DM)", "deadline_day": 45, "why": "Inbound leads are warm leads.", "frameworks": ["Community OS", "Comment-to-DM trigger flow"], "deliverables": ["CTA in every video", "Keyword trigger set up", "First inbound DM documented"]},
            {"id": "p2_t3", "name": "Launch Outbound DM System", "deadline_day": 52, "why": "Outbound is your tap.", "frameworks": ["DM Doctor", "Rohan 7-step follow-up"], "deliverables": ["50 DMs sent this week", "Positive reply rate", "3 calls booked"]},
            {"id": "p2_t4", "name": "Fill Weekly Traffic Tracker", "deadline_day": 60, "why": "What you do not measure you cannot improve.", "frameworks": ["Traffic tracking matrix"], "deliverables": ["Weekly tracker with: views, clicks, DMs sent, replies, calls, closes"]}
        ]
    },
    "Phase 3": {
        "name": "Conversion", "days": "61-90", "focus": "Funnel hacking, Offer rebuild, Landing page, Full launch", "sub_coach": "Revenue & Conversion Specialist",
        "tasks": [
            {"id": "p3_t1", "name": "Funnel Hack 3 Competitors", "deadline_day": 67, "why": "Your competitors have already spent money testing what works.", "frameworks": ["Funnel Hacker mode", "Competitor analysis matrix"], "deliverables": ["3 competitor funnels documented", "Best hook from each", "One element to steal and improve"]},
            {"id": "p3_t2", "name": "Rebuild Offer Doc with Real Data", "deadline_day": 75, "why": "Your offer should be built on what the market proved it wants.", "frameworks": ["Offer Architect (10 pillars)", "F.I.B.S. (Belcher)"], "deliverables": ["New offer doc with real testimonials", "Price anchoring updated", "Risk reversal added"]},
            {"id": "p3_t3", "name": "Optimize Landing Page Conversion", "deadline_day": 82, "why": "A 1% improvement in conversion rate doubles revenue.", "frameworks": ["STORM copywriting (Cattoni)", "19-section sales page (Tutton)"], "deliverables": ["Heatmap or session recording reviewed", "Headline A/B tested", "Conversion rate before and after"]},
            {"id": "p3_t4", "name": "Execute Full Launch Plan", "deadline_day": 90, "why": "A launch is a concentrated burst of revenue.", "frameworks": ["Launch Planner", "21-day launch map"], "deliverables": ["Launch executed", "Revenue generated", "Full case study written"]}
        ]
    }
}

# ============================================================
# DATABASE HELPERS — UNCHANGED
# ============================================================
def db_get_profile(member_id):
    try:
        conn = get_db_connection()
        if not conn: return PROFILES_DB.get(member_id)
        cur = conn.cursor()
        cur.execute("SELECT data FROM profiles WHERE member_id = %s", (member_id,))
        result = cur.fetchone()
        cur.close(); conn.close()
        return result['data'] if result else PROFILES_DB.get(member_id)
    except: return PROFILES_DB.get(member_id)

def db_upsert_profile(member_id, data):
    try:
        conn = get_db_connection()
        if not conn: PROFILES_DB[member_id] = data; return True
        cur = conn.cursor()
        cur.execute("INSERT INTO profiles (member_id, data) VALUES (%s, %s) ON CONFLICT (member_id) DO UPDATE SET data = EXCLUDED.data", (member_id, json.dumps(data)))
        conn.commit(); cur.close(); conn.close()
        return True
    except: PROFILES_DB[member_id] = data; return True

def db_get_journey(member_id):
    default = {"current_day": 1, "current_phase": "Phase 1", "current_task_id": "p1_t1", "tasks_completed": [], "streak": 0, "last_standup_date": None, "xp_total": 0, "badges": []}
    try:
        conn = get_db_connection()
        if not conn: return JOURNEY_DB.get(member_id, default)
        cur = conn.cursor()
        cur.execute("SELECT data FROM journeys WHERE member_id = %s", (member_id,))
        result = cur.fetchone()
        cur.close(); conn.close()
        return result['data'] if result else JOURNEY_DB.get(member_id, default)
    except: return JOURNEY_DB.get(member_id, default)

def db_upsert_journey(member_id, data):
    try:
        conn = get_db_connection()
        if not conn: JOURNEY_DB[member_id] = data; return True
        cur = conn.cursor()
        cur.execute("INSERT INTO journeys (member_id, data) VALUES (%s, %s) ON CONFLICT (member_id) DO UPDATE SET data = EXCLUDED.data", (member_id, json.dumps(data)))
        conn.commit(); cur.close(); conn.close()
        return True
    except: JOURNEY_DB[member_id] = data; return True

def db_add_standup(member_id, task_id, tasks_completed, asset_links, asset_text, metrics, score, review, evidence, proof_files=None):
    try:
        conn = get_db_connection()
        if not conn: return True
        cur = conn.cursor()
        data = {
            "task_id": task_id, "tasks_completed": tasks_completed,
            "asset_links": asset_links, "asset_text": asset_text,
            "metrics": metrics, "score": score, "review": review,
            "evidence": evidence, "proof_files": proof_files or []
        }
        cur.execute("INSERT INTO standups (member_id, data) VALUES (%s, %s)", (member_id, json.dumps(data)))
        conn.commit(); cur.close(); conn.close()
    except: pass
    return True

def db_add_proof(member_id, filename, file_data):
    try:
        conn = get_db_connection()
        if not conn:
            PROOF_DB.setdefault(member_id, []).append({"filename": filename, "data": file_data})
            return True
        cur = conn.cursor()
        cur.execute("INSERT INTO proof_files (member_id, data) VALUES (%s, %s)", (member_id, json.dumps({"filename": filename, "data": file_data})))
        conn.commit(); cur.close(); conn.close()
    except: pass
    return True

def db_get_proofs(member_id):
    try:
        conn = get_db_connection()
        if not conn: return PROOF_DB.get(member_id, [])
        cur = conn.cursor()
        cur.execute("SELECT data FROM proof_files WHERE member_id = %s ORDER BY created_at DESC", (member_id,))
        results = cur.fetchall()
        cur.close(); conn.close()
        return [r['data'] for r in results] if results else PROOF_DB.get(member_id, [])
    except: return PROOF_DB.get(member_id, [])

def db_add_win(member_id, win_text, revenue):
    try:
        conn = get_db_connection()
        if not conn: WINS_DB.setdefault(member_id, []).append({"win_text": win_text, "revenue_amount": revenue}); return True
        cur = conn.cursor()
        cur.execute("INSERT INTO wins (member_id, data) VALUES (%s, %s)", (member_id, json.dumps({"win_text": win_text, "revenue_amount": revenue})))
        conn.commit(); cur.close(); conn.close()
    except: pass
    return True

def db_get_wins(member_id):
    try:
        conn = get_db_connection()
        if not conn: return WINS_DB.get(member_id, [])
        cur = conn.cursor()
        cur.execute("SELECT data FROM wins WHERE member_id = %s ORDER BY created_at DESC", (member_id,))
        results = cur.fetchall()
        cur.close(); conn.close()
        return [r['data'] for r in results] if results else WINS_DB.get(member_id, [])
    except: return WINS_DB.get(member_id, [])

def db_add_score(member_id, score):
    try:
        conn = get_db_connection()
        if not conn: SCORES_DB.setdefault(member_id, []).append(score); return True
        cur = conn.cursor()
        cur.execute("INSERT INTO scores (member_id, score) VALUES (%s, %s)", (member_id, score))
        conn.commit(); cur.close(); conn.close()
    except: pass
    return True

def db_get_scores(member_id):
    try:
        conn = get_db_connection()
        if not conn: return SCORES_DB.get(member_id, [])
        cur = conn.cursor()
        cur.execute("SELECT score FROM scores WHERE member_id = %s", (member_id,))
        results = cur.fetchall()
        cur.close(); conn.close()
        return [r['score'] for r in results] if results else SCORES_DB.get(member_id, [])
    except: return SCORES_DB.get(member_id, [])

def db_get_inactive_members():
    try:
        conn = get_db_connection()
        if not conn: return []
        cur = conn.cursor()
        cur.execute("""
            SELECT j.member_id, p.data->>'business_name' as business_name,
                   j.data->>'streak' as streak, j.data->>'last_standup_date' as last_standup_date,
                   j.data->>'current_day' as current_day, j.data->>'xp_total' as xp,
                   j.data->>'current_task_id' as current_task
            FROM journeys j JOIN profiles p ON j.member_id = p.member_id
            WHERE (j.data->>'last_standup_date' IS NULL OR j.data->>'last_standup_date' < NOW() - INTERVAL '3 days')
            AND p.data->>'onboarding_complete' = 'true'
            ORDER BY j.data->>'last_standup_date' ASC NULLS FIRST
        """)
        results = cur.fetchall(); cur.close(); conn.close()
        inactive = []
        for row in results:
            last_date = row.get('last_standup_date')
            days = 14 if not last_date else (date.today() - date.fromisoformat(last_date)).days
            task_name = "Unknown"
            for phase in JOURNEY_MAP.values():
                for t in phase.get("tasks", []):
                    if t["id"] == row.get('current_task', 'p1_t1'):
                        task_name = t["name"]; break
            inactive.append({
                "member_id": row['member_id'],
                "business_name": row.get('business_name', 'Member'),
                "streak": int(row.get('streak', 0)),
                "days_inactive": days,
                "current_day": int(row.get('current_day', 1)),
                "xp": int(row.get('xp', 0)),
                "current_task": task_name
            })
        return inactive
    except: return []

def db_add_notification(member_id, notification_type, message):
    try:
        conn = get_db_connection()
        if not conn: return True
        cur = conn.cursor()
        cur.execute("INSERT INTO member_notifications (member_id, notification_type, message) VALUES (%s, %s, %s)", (member_id, notification_type, message))
        conn.commit(); cur.close(); conn.close()
    except: pass
    return True

def send_telegram_message(chat_id, message):
    if not TELEGRAM_BOT_TOKEN or not chat_id: return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()).get("ok", False)
    except: return False

def send_re_engagement_notification(member):
    days = member.get("days_inactive", 0)
    if days < 3: return False
    msg = f"⚠️ You haven't submitted a standup in {days} days. Your streak is at risk!"
    contact = db_get_profile(member['member_id']) or {}
    if contact.get('telegram_id'):
        success = send_telegram_message(contact['telegram_id'], msg)
        if success:
            db_add_notification(member['member_id'], "streak_warning", msg)
            return True
    return False

# ============================================================
# NVIDIA LLM — UNCHANGED
# ============================================================
def call_llm(messages, temperature=0.3):
    if not NVIDIA_API_KEY: return "Error: No NVIDIA API key"
    for attempt in range(3):
        try:
            payload = json.dumps({"model": NVIDIA_MODEL, "messages": messages, "temperature": temperature, "max_tokens": 1024}).encode()
            req = urllib.request.Request(NVIDIA_URL, data=payload, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {NVIDIA_API_KEY}"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in [503,429,502,504]: time.sleep(2); continue
            return f"Error: {e.code}"
        except: time.sleep(2); continue
    return "Error: Service unavailable"

# ============================================================
# PYDANTIC MODELS — UNCHANGED
# ============================================================
class ChatMessage(BaseModel): role: str; content: str
class ChatRequest(BaseModel): message: str = ""; history: List[ChatMessage] = []; mode: str = "coach"; member_id: Optional[str] = "default"
class OnboardingRequest(BaseModel):
    member_id: str = "default"
    business_name: str; niche: str; target_avatar: str
    core_offer: str; current_revenue: float = 0; revenue_goal: float = 10000
    biggest_bottleneck: str; current_level: str = "beginner"; weekly_hours: str = "4-7"
    primary_traffic_source: str = "content"
    offer_done: bool = False; audience_done: bool = False
    sales_done: bool = False; launch_done: bool = False
class StandupRequest(BaseModel):
    member_id: str = "default"; current_task_id: str
    tasks_completed: List[str] = []
    asset_links: List[str] = []
    asset_text: str = ""
    metrics: str = ""
    proof_files: List[dict] = []
class WinRequest(BaseModel): member_id: str = "default"; win_text: str; revenue_amount: Optional[float] = None
class StrategyRequest(BaseModel): member_id: str; stage: str; bottleneck: str; hours: str; primary_traffic_source: str = "content"
class CompleteOnboardingRequest(BaseModel): member_id: str; stage: str; bottleneck: str; hours: str; strategy_document: str; starting_day: int; speed_profile: str; primary_traffic_source: str = "content"

# ============================================================
# HELPERS — UNCHANGED
# ============================================================
def get_current_task(journey):
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    return next((t for t in phase_info["tasks"] if t["id"] == journey["current_task_id"]), phase_info["tasks"][0])

def advance_journey(journey, member_id):
    phase = journey["current_phase"]
    phase_tasks = JOURNEY_MAP[phase]["tasks"]
    completed = journey.get("tasks_completed", [])
    completed_in_phase = [t for t in phase_tasks if t["id"] in completed]
    if phase == "Phase 1" and len(completed_in_phase) >= 4:
        journey["current_phase"] = "Phase 2"; journey["current_task_id"] = "p2_t1"
    elif phase == "Phase 2" and len(completed_in_phase) >= 4:
        journey["current_phase"] = "Phase 3"; journey["current_task_id"] = "p3_t1"
    else:
        remaining = [t for t in phase_tasks if t["id"] not in completed]
        if remaining: journey["current_task_id"] = remaining[0]["id"]

def calculate_trajectory(journey):
    current_day = journey.get("current_day", 1)
    tasks_completed = len(journey.get("tasks_completed", []))
    expected = max(1, current_day // 7)
    if tasks_completed > expected: return {"status": "ahead", "message": "🚀 You're ahead!", "color": "green"}
    elif tasks_completed < expected: return {"status": "behind", "message": "⚠️ You're behind.", "color": "yellow"}
    else: return {"status": "on_track", "message": "✅ You're on track.", "color": "blue"}

# ============================================================
# EXISTING ROUTES — UNCHANGED
# ============================================================

# --- LANDING PAGE AND APP ---
@app.get("/")
async def landing_page():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return {"status": "ok", "message": "Welcome to E5 AI Coach OS"}

@app.get("/chat")
@app.get("/chat.html")
@app.get("/app")
async def serve_app():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return {"status": "ok", "message": "App not found"}

@app.get("/onboarding.html")
async def onboarding_page():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return {"status": "ok"}

# --- API HEALTH ---
@app.get("/api/health")
def health():
    return {"ok": True, "database": DATABASE_CONNECTED, "version": "5.5"}

# --- ONBOARDING ---
@app.get("/api/check-onboarding")
def check_onboarding(member_id: str = "default"):
    profile = db_get_profile(member_id)
    return {"onboarded": profile is not None, "profile": profile}

@app.post("/api/onboarding")
def submit_onboarding(req: OnboardingRequest):
    starting_day = 1
    if req.current_level == "intermediate" and (req.offer_done and req.audience_done): starting_day = 15
    elif req.current_level == "advanced" and (req.offer_done and req.audience_done and req.sales_done): starting_day = 31
    speed_profile = "accelerator" if req.weekly_hours == "8+" else "steady" if req.weekly_hours == "4-7" else "reflective"
    profile_data = req.dict()
    profile_data["speed_profile"] = speed_profile
    db_upsert_profile(req.member_id, profile_data)
    db_upsert_journey(req.member_id, {"current_day": starting_day, "current_phase": "Phase 1", "current_task_id": "p1_t1", "tasks_completed": [], "streak": 0, "last_standup_date": None, "xp_total": 0, "badges": []})
    return {"success": True, "starting_day": starting_day, "speed_profile": speed_profile}

@app.post("/api/generate-strategy")
def generate_strategy(req: StrategyRequest):
    starting_day = 15 if req.stage == "product" else 31 if req.stage == "selling" else 1
    speed_profile = "accelerator" if req.hours == "8+" else "steady" if req.hours == "4-7" else "reflective"
    focus = {
        "traffic": "Module 3 — Attract", "conversion": "Module 4 — Convert",
        "content": "Module 3 — Attract", "community": "Module 5 — Automate",
        "offer": "Module 2 — Package", "time": "Module 5 — Automate", "other": "Module 1 — Position"
    }.get(req.bottleneck, "Module 1 — Position")
    traffic_source = req.primary_traffic_source or "content"
    system = f"""You are a strategic coach. Generate a personalized strategy document.
The member's primary traffic source is: {traffic_source}.
Customize advice accordingly (e.g., if content, focus on viral hooks; if DMs, focus on sequences; if paid, focus on ads).
Include: Current Stage, Biggest Challenge, Recommended Focus, Starting Day, Speed Profile, Recommended First Task, and Next Steps."""
    user = f"Stage: {req.stage}, Challenge: {req.bottleneck}, Hours: {req.hours}, Traffic: {traffic_source}. Starting Day: {starting_day}, Speed: {speed_profile}, Focus: {focus}"
    document = call_llm([{"role": "system", "content": system}, {"role": "user", "content": user}])
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO strategy_docs (member_id, data) VALUES (%s, %s) ON CONFLICT (member_id) DO UPDATE SET data = EXCLUDED.data", (req.member_id, json.dumps({"document": document, "starting_day": starting_day, "speed_profile": speed_profile, "bottleneck": req.bottleneck, "primary_traffic_source": traffic_source})))
            conn.commit(); cur.close(); conn.close()
    except: pass
    return {"document": document, "starting_day": starting_day, "speed_profile": speed_profile, "focus": focus}

@app.post("/api/complete-onboarding")
def complete_onboarding(req: CompleteOnboardingRequest):
    profile = db_get_profile(req.member_id)
    if not profile:
        db_upsert_profile(req.member_id, {"business_name": "New Member", "niche": "", "target_avatar": "", "biggest_bottleneck": req.bottleneck, "current_level": req.stage, "weekly_hours": req.hours, "speed_profile": req.speed_profile, "primary_traffic_source": req.primary_traffic_source, "onboarding_complete": True})
    else:
        db_upsert_profile(req.member_id, {**profile, "current_level": req.stage, "weekly_hours": req.hours, "speed_profile": req.speed_profile, "primary_traffic_source": req.primary_traffic_source, "onboarding_complete": True, "biggest_bottleneck": req.bottleneck})
    journey = db_get_journey(req.member_id) or {"member_id": req.member_id, "current_day": req.starting_day, "current_phase": "Phase 1", "current_task_id": "p1_t1", "tasks_completed": [], "streak": 0, "last_standup_date": None, "xp_total": 0, "badges": []}
    journey["current_day"] = req.starting_day
    db_upsert_journey(req.member_id, journey)
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO strategy_docs (member_id, data) VALUES (%s, %s) ON CONFLICT (member_id) DO UPDATE SET data = EXCLUDED.data", (req.member_id, json.dumps({"document": req.strategy_document, "starting_day": req.starting_day, "speed_profile": req.speed_profile, "bottleneck": req.bottleneck, "primary_traffic_source": req.primary_traffic_source})))
            conn.commit(); cur.close(); conn.close()
    except: pass
    return {"success": True, "message": "Onboarding complete", "starting_day": req.starting_day, "speed_profile": req.speed_profile}

# --- JOURNEY ---
@app.get("/api/journey")
def get_journey_status(member_id: str = "default"):
    journey = db_get_journey(member_id)
    profile = db_get_profile(member_id) or {}
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    current_task = get_current_task(journey)
    progress = min(100, max(1, (journey.get("current_day",1)/90)*100))
    scores = db_get_scores(member_id)
    avg_score = round(sum(scores)/len(scores),1) if scores else 0
    wins = db_get_wins(member_id)
    proofs = db_get_proofs(member_id)
    return {
        "current_day": journey.get("current_day",1),
        "current_phase": phase_info["name"],
        "phase_days": phase_info["days"],
        "sub_coach": phase_info.get("sub_coach","Strategist"),
        "focus": phase_info["focus"],
        "current_task": current_task,
        "tasks_completed": journey.get("tasks_completed",[]),
        "tasks_completed_count": len(journey.get("tasks_completed",[])),
        "progress_percent": round(progress,1),
        "streak": journey.get("streak",0),
        "xp": journey.get("xp_total",0),
        "avg_score": avg_score,
        "standup_count": len(scores),
        "wins": wins,
        "proofs": proofs,
        "trajectory": calculate_trajectory(journey),
        "profile": {
            "business_name": profile.get("business_name",""),
            "niche": profile.get("niche",""),
            "bottleneck": profile.get("biggest_bottleneck",""),
            "speed_profile": profile.get("speed_profile","steady"),
            "primary_traffic_source": profile.get("primary_traffic_source","content")
        },
        "all_phases": {k: {"name": v["name"], "sub_coach": v.get("sub_coach","Strategist"), "tasks": [{"id": t["id"], "name": t["name"], "deadline_day": t["deadline_day"], "completed": t["id"] in journey.get("tasks_completed",[]), "why": t.get("why",""), "frameworks": t.get("frameworks",[]), "deliverables": t.get("deliverables",[])} for t in v["tasks"]]} for k,v in JOURNEY_MAP.items()}
    }

# --- STANDUP ---
@app.post("/api/standup")
def submit_standup(req: StandupRequest):
    profile = db_get_profile(req.member_id)
    if not profile: raise HTTPException(403, "Complete onboarding first.")
    journey = db_get_journey(req.member_id)
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    task = next((t for t in phase_info["tasks"] if t["id"] == req.current_task_id), phase_info["tasks"][0])
    frameworks_str = ", ".join(task.get("frameworks", []))
    deliverables_str = "\n".join([f"- {d}" for d in task.get("deliverables", [])])
    system = f"""You are a STRICT COO grading execution.
TASK: {task['name']}
FRAMEWORKS: {frameworks_str}
DELIVERABLES:\n{deliverables_str}
MEMBER: Niche={profile.get('niche','N/A')} | Speed={profile.get('speed_profile','steady')} | Traffic Source={profile.get('primary_traffic_source','content')}
RUBRIC: Link(+2), Metrics(+2), Deliverables(+2), Quality(0-4).
OUTPUT: GRADE: [X]/10
AUDIT: [2-3 issues]
WHAT TO FIX: [if <7]
NEXT STEP: [if >=7]
FRAMEWORK TIP: [insight]"""
    prompt = f"Tasks: {req.tasks_completed}\nLinks: {req.asset_links}\nContent: {req.asset_text}\nMetrics: {req.metrics}"
    review = call_llm([{"role":"system","content":system},{"role":"user","content":prompt}])
    score = 5
    try: m = re.search(r'GRADE:\s*(\d+)', review); score = int(m.group(1)) if m else 5
    except: pass
    score = min(10, max(0, score))
    evidence = {"link_present": len(req.asset_links)>0 and req.asset_links[0].strip(), "metrics_present": req.metrics.strip()!="", "deliverables_mentioned": len(req.tasks_completed)>0, "evidence_score": score}
    today = date.today().isoformat()
    last_date = journey.get("last_standup_date")
    if last_date != today:
        if last_date:
            try: days_since = (date.today() - date.fromisoformat(last_date)).days
            except: days_since = 1
            journey["streak"] = journey.get("streak",0) + 1 if days_since <= 1 else 1
        else: journey["streak"] = 1
        journey["last_standup_date"] = today
    if score >= 7 and req.current_task_id not in journey.get("tasks_completed",[]):
        journey.setdefault("tasks_completed",[]).append(req.current_task_id)
        journey["current_day"] = min(90, journey.get("current_day",1) + 7)
        advance_journey(journey, req.member_id)
        xp_gained = 125
        journey["xp_total"] = journey.get("xp_total",0) + xp_gained
    else:
        xp_gained = 25
    for pf in req.proof_files or []:
        db_add_proof(req.member_id, pf.get("filename", "unknown"), pf.get("data", ""))
    db_add_standup(req.member_id, req.current_task_id, ",".join(req.tasks_completed), ",".join(req.asset_links), req.asset_text, req.metrics, score, review, evidence, req.proof_files)
    db_add_score(req.member_id, score)
    db_upsert_journey(req.member_id, journey)
    return {"success": True, "review": review, "score": score, "task_unlocked": score >= 7, "streak": journey.get("streak",0), "xp_gained": xp_gained, "xp_total": journey.get("xp_total",0), "journey_updated": True}

# --- WIN ---
@app.post("/api/win")
def submit_win(req: WinRequest):
    if not db_get_profile(req.member_id): raise HTTPException(403, "Complete onboarding first.")
    db_add_win(req.member_id, req.win_text, req.revenue_amount)
    return {"success": True, "total_wins": len(db_get_wins(req.member_id))}

# --- CHAT ---
@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.message: raise HTTPException(400, "empty message")
    profile = db_get_profile(req.member_id or "default")
    if not profile: raise HTTPException(403, "GATEKEEPER: Complete onboarding first.")
    journey = db_get_journey(req.member_id or "default")
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    current_task = get_current_task(journey)
    task_completed = current_task["id"] in journey.get("tasks_completed", [])
    if not task_completed:
        return {"reply": f"""**ACCOUNTABILITY GATE**
You are Day {journey.get('current_day',1)} — {phase_info['name']} phase.
Current task: {current_task['name']}
Deadline: Day {current_task['deadline_day']}
Why: {current_task.get('why', 'Complete this task.')}
Frameworks: {', '.join(current_task.get('frameworks', []))}
Deliverables:
{chr(10).join(['— ' + d for d in current_task.get('deliverables', [])])}
Submit your work using the 'Submit Daily Work' button."""}
    wins_text = "No wins yet."
    wins = db_get_wins(req.member_id or "default")
    if wins: wins_text = f"{len(wins)} wins. Latest: {wins[0]['win_text'][:100]}"
    scores = db_get_scores(req.member_id or "default")
    avg_score = round(sum(scores)/len(scores),1) if scores else 0
    traffic_source = profile.get('primary_traffic_source', 'content')
    system_prompt = f"""You are the E5 AI Coach.
MEMBER: {profile.get('business_name','N/A')} | Niche: {profile.get('niche','N/A')} | Bottleneck: {profile.get('biggest_bottleneck','N/A')} | Speed: {profile.get('speed_profile','steady')} | Traffic Source: {traffic_source}
Day: {journey.get('current_day',1)}/90 | Phase: {phase_info['name']} | Task: {current_task['name']} | Streak: {journey.get('streak',0)} | Avg score: {avg_score}/10 | Wins: {wins_text}
RULES: Diagnose first, personalize, one insight, apply frameworks, 60% questions/40% insight, short (150-250 words), never invent.
Tailor your advice to their primary traffic source ({traffic_source})."""
    messages = [{"role": "system", "content": system_prompt}] + [{"role": m.role, "content": m.content} for m in req.history[-10:]] + [{"role": "user", "content": req.message}]
    reply = call_llm(messages)
    return {"reply": reply}

# --- RE-ENGAGEMENT ---
@app.post("/api/check-inactive")
def check_inactive():
    inactive = db_get_inactive_members()
    sent = 0
    for m in inactive:
        if send_re_engagement_notification(m): sent += 1
    return {"success": True, "inactive_count": len(inactive), "sent_count": sent}

@app.post("/api/trigger-re-engagement")
def trigger_re_engagement(member_id: str):
    return {"success": True, "member_id": member_id, "message": "Test notification triggered."}

# ============================================================
# NEW: VOICE AI COACH (TTS)
# ============================================================
import edge_tts
import base64
from fastapi.responses import JSONResponse

@app.post("/api/tts")
async def text_to_speech(request: Request):
    """Convert text to speech using edge_tts (free)."""
    try:
        data = await request.json()
        text = data.get("text", "")
        if not text:
            return JSONResponse({"error": "No text provided"}, status_code=400)
        
        voice = data.get("voice", "en-US-AriaNeural")
        communicate = edge_tts.Communicate(text, voice)
        
        # Generate audio
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        # Encode as base64 for frontend
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        return JSONResponse({"audio": audio_base64})
    except Exception as e:
        log.error(f"TTS Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ============================================================
# NEW: FUNNEL ANALYZER
# ============================================================
@app.post("/api/analyze-funnel")
async def analyze_funnel(request: Request):
    """Analyze a competitor's funnel using AI."""
    try:
        data = await request.json()
        url = data.get("url", "")
        member_id = data.get("member_id", "default")
        
        if not url:
            return JSONResponse({"error": "No URL provided"}, status_code=400)
        
        # Get member profile for context
        profile = db_get_profile(member_id) or {}
        niche = profile.get("niche", "digital products")
        business_name = profile.get("business_name", "your business")
        
        # Enhanced AI prompt for funnel analysis
        prompt = f"""
        You are a funnel hacking expert. Analyze this competitor's funnel:
        
        URL: {url}
        Member's Niche: {niche}
        Member's Business: {business_name}
        
        Provide a detailed analysis with these sections:
        
        1. 🎯 HEADLINE ANALYSIS
        - What's the headline?
        - What emotion does it trigger?
        - What could be improved?
        
        2. 📢 CALL-TO-ACTION (CTA)
        - What's the CTA?
        - Is it clear and compelling?
        - Suggestions for improvement
        
        3. 💰 PRICING STRATEGY
        - What's the pricing model?
        - How is it positioned?
        - What could you learn from this?
        
        4. 📊 SOCIAL PROOF
        - What testimonials or numbers are shown?
        - How credible are they?
        - How can you use similar social proof?
        
        5. 🔥 3 ACTIONABLE IMPROVEMENTS
        - Specific things you can steal and implement in YOUR funnel
        - Why each works
        
        Format with clear headings and bullet points.
        Make it practical and actionable.
        """
        
        analysis = call_llm([{"role": "system", "content": "You are a world-class funnel hacker and conversion expert."}, {"role": "user", "content": prompt}])
        return {"analysis": analysis}
        
    except Exception as e:
        log.error(f"Funnel Analysis Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ============================================================
# NEW: PROACTIVE SUGGESTIONS
# ============================================================
@app.post("/api/proactive-suggest")
async def proactive_suggest(request: Request):
    """Generate proactive suggestions based on member's progress."""
    try:
        data = await request.json()
        member_id = data.get("member_id", "default")
        
        # Get member's journey and profile
        journey = db_get_journey(member_id)
        profile = db_get_profile(member_id) or {}
        
        if not journey:
            return JSONResponse({"error": "Member not found"}, status_code=404)
        
        # Calculate days since last standup
        last_date = journey.get("last_standup_date")
        days_since = 0
        if last_date:
            try:
                days_since = (date.today() - date.fromisoformat(last_date)).days
            except:
                days_since = 0
        
        # Get current task
        current_task = get_current_task(journey)
        task_name = current_task.get("name", "your current task")
        
        # Get streak
        streak = journey.get("streak", 0)
        
        # Build context for AI
        tasks_completed = len(journey.get("tasks_completed", []))
        total_tasks = 12
        phase = journey.get("current_phase", "Phase 1")
        
        context = f"""
        Member Progress:
        - Phase: {phase}
        - Day: {journey.get('current_day', 1)}/90
        - Tasks completed: {tasks_completed}/{total_tasks}
        - Current task: {task_name}
        - Streak: {streak} days
        - Days since last standup: {days_since}
        - Niche: {profile.get('niche', 'Unknown')}
        - Bottleneck: {profile.get('biggest_bottleneck', 'Unknown')}
        - Traffic source: {profile.get('primary_traffic_source', 'Unknown')}
        """
        
        # Determine urgency based on days since last standup
        urgency = "normal"
        if days_since >= 14:
            urgency = "critical"
        elif days_since >= 7:
            urgency = "warning"
        elif days_since >= 3:
            urgency = "gentle"
        
        prompt = f"""
        You are a proactive business coach. Based on this member's progress, provide ONE specific, actionable suggestion.
        
        {context}
        
        Urgency level: {urgency}
        
        Guidelines:
        - If streak is low or days_since is high: Focus on re-engagement
        - If tasks_completed is low: Focus on getting started
        - If days_since is normal: Provide a "quick win" tip for their current task
        - Be encouraging but direct
        - Keep it under 150 words
        - Include a specific call to action
        
        Format: Just the suggestion text, no extra commentary.
        """
        
        suggestion = call_llm([{"role": "system", "content": "You are a proactive, encouraging business coach who gives specific, actionable advice."}, {"role": "user", "content": prompt}])
        
        return {
            "suggestion": suggestion,
            "urgency": urgency,
            "days_since": days_since,
            "streak": streak
        }
        
    except Exception as e:
        log.error(f"Proactive Suggestion Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
