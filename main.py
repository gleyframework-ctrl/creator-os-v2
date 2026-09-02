import os
import time
import logging
import threading
import urllib.request
import json
import re
import base64
import shutil
from typing import List, Optional, Dict
from datetime import datetime, date
from uuid import uuid4
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

# ============================================================
# LOGGING & ENV
# ============================================================
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

# NVIDIA — keep your working model
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct").strip()
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Optional API keys (add only when needed)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
WHOP_API_KEY = os.environ.get("WHOP_API_KEY", "").strip()
TIKHUB_API_KEY = os.environ.get("TIKHUB_API_KEY", "").strip()

log.info(f"🔍 NVIDIA Model: {NVIDIA_MODEL}")

# ============================================================
# POSTGRESQL — UNCHANGED
# ============================================================
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
        # NEW: funnels table
        cur.execute("CREATE TABLE IF NOT EXISTS funnels (member_id TEXT PRIMARY KEY, data JSONB, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
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
FUNNEL_DB = {}

# Upload directory for proof files
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(title="E5 AI Coach OS", version="6.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ============================================================
# JOURNEY MAP — UNCHANGED
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
# DATABASE HELPERS — UNCHANGED (plus new funnel helpers)
# ============================================================
# ... [all existing db_* functions remain exactly as before]
# I'm including them implicitly; in the final code you keep yours.
# For brevity I'll show only the new funnel helpers:

def db_get_funnel(member_id):
    try:
        conn = get_db_connection()
        if not conn: return FUNNEL_DB.get(member_id, {"stages": []})
        cur = conn.cursor()
        cur.execute("SELECT data FROM funnels WHERE member_id = %s", (member_id,))
        result = cur.fetchone()
        cur.close(); conn.close()
        return result['data'] if result else {"stages": []}
    except: return FUNNEL_DB.get(member_id, {"stages": []})

def db_save_funnel(member_id, data):
    try:
        conn = get_db_connection()
        if not conn: FUNNEL_DB[member_id] = data; return True
        cur = conn.cursor()
        cur.execute("INSERT INTO funnels (member_id, data) VALUES (%s, %s) ON CONFLICT (member_id) DO UPDATE SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP", (member_id, json.dumps(data)))
        conn.commit(); cur.close(); conn.close()
        return True
    except: FUNNEL_DB[member_id] = data; return True

def db_add_proof(member_id, filename, filepath):
    try:
        conn = get_db_connection()
        if not conn: PROOF_DB.setdefault(member_id, []).append({"filename": filename, "filepath": filepath}); return True
        cur = conn.cursor()
        cur.execute("INSERT INTO proof_files (member_id, data) VALUES (%s, %s)", (member_id, json.dumps({"filename": filename, "filepath": filepath})))
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

# ============================================================
# EXISTING ROUTES — KEEP ALL YOUR CURRENT API ENDPOINTS
# ============================================================
# [All existing routes: /, /chat, /api/health, /api/check-onboarding,
#  /api/onboarding, /api/generate-strategy, /api/complete-onboarding,
#  /api/journey, /api/standup, /api/win, /api/chat, /api/check-inactive,
#  /api/trigger-re-engagement, /api/tts, /api/analyze-funnel,
#  /api/proactive-suggest — all unchanged. Keep your code as is.]

# ============================================================
# NEW ROUTES — Additive Features
# ============================================================

# ---- FILE UPLOADS ----
@app.post("/api/upload-proof")
async def upload_proof(
    member_id: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        ext = file.filename.split('.')[-1] if '.' in file.filename else ''
        unique_name = f"{uuid4()}.{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_name)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        db_add_proof(member_id, file.filename, file_path)
        return {
            "success": True,
            "filename": file.filename,
            "path": file_path,
            "url": f"/api/proof/{unique_name}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/proof/{filename}")
async def get_proof(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "File not found"}, 404

# ---- VISUAL FUNNEL MAP ----
@app.get("/api/funnel")
async def get_funnel(member_id: str = "default"):
    funnel = db_get_funnel(member_id)
    return {"success": True, "funnel": funnel}

@app.post("/api/funnel")
async def save_funnel(request: Request):
    data = await request.json()
    member_id = data.get("member_id", "default")
    funnel_data = data.get("funnel", {"stages": []})
    db_save_funnel(member_id, funnel_data)
    return {"success": True}

# ---- WHOP INTEGRATION ----
@app.get("/api/whop/verify")
async def verify_whop_membership(member_id: str = "default"):
    if not WHOP_API_KEY:
        return {"error": "Whop API key not configured"}
    profile = db_get_profile(member_id) or {}
    whop_user_id = profile.get("whop_user_id")
    if not whop_user_id:
        return {"error": "Whop user ID not found"}
    headers = {"Authorization": f"Bearer {WHOP_API_KEY}"}
    url = "https://api.whop.com/api/v1/memberships"
    try:
        import requests
        response = requests.get(url, headers=headers, params={"user_id": whop_user_id})
        if response.status_code == 200:
            memberships = response.json()
            active = any(m.get("status") == "active" for m in memberships)
            return {"active": active, "memberships": memberships}
        return {"error": "Failed to fetch membership"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/webhook/whop")
async def whop_webhook(request: Request):
    payload = await request.json()
    event_type = payload.get("type")
    # Handle membership events (update local DB, send emails, etc.)
    # For MVP, just log
    log.info(f"Whop webhook received: {event_type}")
    return {"status": "ok"}

# ---- SOCIAL MEDIA CONNECT ----
@app.post("/api/social/connect")
async def connect_social(request: Request):
    data = await request.json()
    member_id = data.get("member_id", "default")
    platform = data.get("platform")
    username = data.get("username")
    if not platform or not username:
        return {"error": "Platform and username required"}
    profile = db_get_profile(member_id) or {}
    social = profile.get("social_accounts", {})
    social[platform] = {"username": username, "connected_at": datetime.now().isoformat()}
    profile["social_accounts"] = social
    db_upsert_profile(member_id, profile)
    return {"success": True, "platform": platform, "username": username}

@app.get("/api/social/analytics")
async def get_social_analytics(member_id: str = "default", platform: str = ""):
    if not platform:
        return {"error": "Platform required"}
    profile = db_get_profile(member_id) or {}
    social = profile.get("social_accounts", {}).get(platform)
    if not social:
        return {"error": "Account not connected"}
    username = social.get("username")
    # Stub: in production, call an external API like TikHub
    # For now, return a mock response
    return {
        "platform": platform,
        "username": username,
        "followers": 0,
        "engagement_rate": 0,
        "avg_views": 0,
        "message": "Social analytics requires API key. Add TIKHUB_API_KEY to enable."
    }

# ============================================================
# NVIDIA LLM (unchanged)
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
# MAIN
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
