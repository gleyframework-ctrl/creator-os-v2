import os
import time
import logging
import threading
import urllib.request
import json
import re
from typing import List, Optional, Dict
from datetime import datetime, date
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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

app = FastAPI(title="E5 AI Coach OS", version="5.4")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ============================================================
# JOURNEY MAP (12 tasks) — SAME AS BEFORE
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
# DATABASE HELPERS (SAME)
# ============================================================
# ... (all the db_* functions remain exactly the same)
# I'm omitting them here for brevity — keep your existing code.
# Just copy your db_get_profile, db_upsert_profile, etc. from your current main.py

# ============================================================
# NVIDIA LLM (SAME)
# ============================================================
def call_llm(messages, temperature=0.3):
    # ... keep your existing call_llm
    pass

# ============================================================
# PYDANTIC MODELS (SAME)
# ============================================================
# ... keep your existing models

# ============================================================
# HELPERS (SAME)
# ============================================================
# ... keep get_current_task, advance_journey, calculate_trajectory

# ============================================================
# ROUTES — UPDATED FOR LANDING PAGE
# ============================================================

# --- LANDING PAGE AT ROOT ---
@app.get("/")
async def landing_page():
    """Serve the landing page at the root."""
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    # Fallback: if index.html doesn't exist, serve the app (for backward compatibility)
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return {"status": "ok", "message": "Welcome to E5 AI Coach OS"}

# --- APP AT /chat ---
@app.get("/chat")
@app.get("/chat.html")
@app.get("/app")
async def serve_app():
    """Serve the main app at /chat."""
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return {"status": "ok", "message": "App not found"}

# --- LEGACY ONBOARDING (for backward compatibility) ---
@app.get("/onboarding.html")
async def onboarding_page():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return {"status": "ok"}

# --- API ROUTES (ALL YOUR EXISTING ENDPOINTS) ---
# Keep all your /api/* endpoints exactly as they are.
# Example:
# @app.get("/api/health")
# @app.get("/api/check-onboarding")
# @app.post("/api/onboarding")
# @app.post("/api/generate-strategy")
# @app.post("/api/complete-onboarding")
# @app.get("/api/journey")
# @app.post("/api/standup")
# @app.post("/api/win")
# @app.post("/api/chat")
# @app.post("/api/check-inactive")
# @app.post("/api/trigger-re-engagement")

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
