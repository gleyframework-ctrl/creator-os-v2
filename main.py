import os
import time
import logging
import threading
import urllib.request
import json
import re
import base64
import shutil
from typing import List, Optional, Dict, Literal
from datetime import datetime, date
from uuid import uuid4
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "CDN-Cache-Control": "no-store",
    "Cloudflare-CDN-Cache-Control": "no-store",
}
import httpx
try:
    from framework_search import search_frameworks
    FRAMEWORK_SEARCH_AVAILABLE = True
except ImportError:
    FRAMEWORK_SEARCH_AVAILABLE = False

# ============================================================
# LOGGING & ENV
# ============================================================
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

# ===== NVIDIA — USING THE WORKING MODEL =====
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct").strip()
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


SELF_CRITIQUE_BLOCK = """

SELF-CRITIQUE (run this checklist on your draft BEFORE you output it. Do not output the checklist itself):
1. [F3_PLAIN_RULE]
2. User context referenced (their day, task, bottleneck, or recent win)? If no, add one.
3. Banned phrases absent? Never use: 'it depends', 'you should consider', 'in today's world', 'at the end of the day', 'it's important to', 'remember that'.
4. At least 2 markdown sections with ## headers? If no, restructure.
5. Ends with a single, clear question? If no, add one.
Only output the FINAL improved version."""
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
WHOP_API_KEY = os.environ.get("WHOP_API_KEY", "").strip()
TIKHUB_API_KEY = os.environ.get("TIKHUB_API_KEY", "").strip()

log.info(f"🔍 NVIDIA Model: {NVIDIA_MODEL}")
log.info(f"🔍 Telegram Bot: {'Set' if TELEGRAM_BOT_TOKEN else 'MISSING'}")

# ============================================================
# POSTGRESQL
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
        log.info(f"🔍 Connecting to PostgreSQL: host={PGHOST}, db={PGDATABASE}, user={PGUSER}")
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
        log.warning("⚠️ Using in‑memory fallback (data will be lost on restart)")
        log.warning("⚠️ To fix, add PGHOST, PGDATABASE, PGUSER, PGPASSWORD to Railway variables")
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

# Upload directory
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(title="E5 AI Coach OS", version="6.0")
# Same-origin deployment; cross-origin wildcard removed.
from integration_support import (
 security_gate, require_member, set_session, csrf, pack, unpack, llm_result,
 check_upload, COOKIE, install_strict_database, checked_connection, persist_review, save_strategy
)

# ============================================================
# OAUTH STATE STORAGE (in-memory, single-worker safe)
# ============================================================
OAUTH_STATES = {}


def _prune_oauth_states():
    now = time.time()
    for k, v in list(OAUTH_STATES.items()):
        if v.get("exp", 0) + 300 < now:
            OAUTH_STATES.pop(k, None)


# ============================================================
# JOURNEY MAP
# ============================================================
JOURNEY_MAP_V1 = {  # BRICK G: old 3-phase map, kept for reference, not used
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

# ===== BRICK G: 5-phase journey (Foundation, Product, Community, Traffic, Retention). 18 tasks, one every 5 days. =====
# Scale (Phase 6) comes in a later brick. No framework names: frameworks is [] on every task (key kept).
# Each task sets standup_link / standup_metrics, which _e3_rubric already reads. The grader is not changed.
JOURNEY_MAP = {
    "Phase 1": {
        "name": "Foundation", "days": "1-15", "focus": "Who you help and what you sell", "sub_coach": "Foundation Coach",
        "tasks": [
            {"id": "p1_t1", "name": "Define your offer", "deadline_day": 1, "why": "A clear offer makes every next step easier.",
             "frameworks": [], "deliverables": ["Your offer in one sentence", "3 results your customer gets", "Your price and your guarantee"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p1_t2", "name": "Know your customer", "deadline_day": 6, "why": "When you know one person well, your words reach them.",
             "frameworks": [], "deliverables": ["Who they are and their situation", "Their 3 biggest worries", "Their 3 biggest wishes", "Where they spend time online"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p1_position", "name": "Write your positioning statement", "deadline_day": 11, "why": "One clear sentence tells people why you are the right choice.",
             "frameworks": [], "deliverables": ["One sentence: I help [who] get [result] without [pain]", "Why they should pick you over other options"],
             "standup_link": False, "standup_metrics": False},
        ]
    },
    "Phase 2": {
        "name": "Product", "days": "16-30", "focus": "Prove people want it before you build it", "sub_coach": "Product Coach",
        "tasks": [
            {"id": "p2_presell", "name": "Build a one-page pre-sell", "deadline_day": 16, "why": "A simple page lets people say yes before you build the full product.",
             "frameworks": [], "deliverables": ["A headline with the main result", "Who it is for", "Your 3 results", "Your price and how to say yes"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p2_walkthrough", "name": "Record a 5-minute offer walkthrough", "deadline_day": 21, "why": "A short video explains your offer better than a long text.",
             "frameworks": [], "deliverables": ["A video of 5 minutes or less about your offer", "Link to the video"],
             "standup_link": True, "standup_metrics": False},
            {"id": "p2_signals", "name": "Get 3 people to say \"I'd buy this\"", "deadline_day": 26, "why": "Real people saying yes proves your offer before you build it.",
             "frameworks": [], "deliverables": ["How many people you talked to", "3 people who said they would buy", "What they said, in their words"],
             "standup_link": False, "standup_metrics": True},
        ]
    },
    "Phase 3": {
        "name": "Community", "days": "31-50", "focus": "A home for your paying members", "sub_coach": "Community Coach",
        "tasks": [
            {"id": "p3_create", "name": "Create your community on Whop or Skool", "deadline_day": 31, "why": "Your community is your shop, your classroom and your checkout in one place.",
             "frameworks": [], "deliverables": ["Community created", "Link to your community"],
             "standup_link": True, "standup_metrics": False},
            {"id": "p3_welcome", "name": "Write your welcome post", "deadline_day": 36, "why": "A good welcome helps new members feel at home and take a first step.",
             "frameworks": [], "deliverables": ["Who the community is for", "What members get", "The first step to take"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p3_channels", "name": "Set up your channels", "deadline_day": 41, "why": "Clear channels help members find what they need.",
             "frameworks": [], "deliverables": ["3 to 5 channels with clear names", "One line on what goes in each"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p3_pricing", "name": "Set your pricing tiers", "deadline_day": 46, "why": "Clear prices make it easy to say yes.",
             "frameworks": [], "deliverables": ["1 to 3 price levels", "What each level includes", "The price of each level"],
             "standup_link": False, "standup_metrics": True},
        ]
    },
    "Phase 4": {
        "name": "Traffic", "days": "51-70", "focus": "Bring the right people to your community", "sub_coach": "Traffic Coach",
        "tasks": [
            {"id": "p4_diagnostic", "name": "Answer the 12-question traffic check", "deadline_day": 51, "why": "Your answers show which way of finding people fits you best.",
             "frameworks": [], "deliverables": ["Your audience, past clients and warm contacts", "Your time and budget", "What you are comfortable doing: camera, writing, messages, live calls", "Your offer status and price"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p4_method", "name": "Pick one traffic method", "deadline_day": 56, "why": "One method done well beats five done halfway. No audience yet? Sending 100 messages a day works.",
             "frameworks": [], "deliverables": ["The 3 methods the coach suggested", "The one you picked and why", "Your plan for the first week"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p4_launch", "name": "Launch your method and log your first link", "deadline_day": 61, "why": "Starting is the hardest part. Your first link proves you started.",
             "frameworks": [], "deliverables": ["What you launched", "Link to your first post, message or page"],
             "standup_link": True, "standup_metrics": False},
            {"id": "p4_first_sale", "name": "Record your first sale", "deadline_day": 66, "why": "Your first sale proves people will pay for what you offer.",
             "frameworks": [], "deliverables": ["Who bought", "What they paid", "How they found you"],
             "standup_link": False, "standup_metrics": True},
        ]
    },
    "Phase 5": {
        "name": "Retention", "days": "71-90", "focus": "Keep members happy and growing", "sub_coach": "Retention Coach",
        "tasks": [
            {"id": "p5_engagement", "name": "Plan your weekly member activity", "deadline_day": 71, "why": "A steady weekly rhythm keeps members coming back.",
             "frameworks": [], "deliverables": ["One thing you post or host every week", "The day and time"],
             "standup_link": False, "standup_metrics": False},
            {"id": "p5_audit", "name": "Check why members stay or leave", "deadline_day": 76, "why": "Knowing why people stay or leave shows you what to fix.",
             "frameworks": [], "deliverables": ["How many members joined", "How many members left", "2 reasons people stay or leave"],
             "standup_link": False, "standup_metrics": True},
            {"id": "p5_upsell", "name": "Write your next offer for members", "deadline_day": 81, "why": "Happy members often want more help from you.",
             "frameworks": [], "deliverables": ["The next offer for current members", "Its price", "How you will tell members"],
             "standup_link": False, "standup_metrics": True},
            {"id": "p5_workshop", "name": "Run a 6-day workshop", "deadline_day": 86, "why": "A short live workshop brings members together and brings new people in.",
             "frameworks": [], "deliverables": ["The 6 topics", "How many people joined", "What you learned"],
             "standup_link": False, "standup_metrics": True},
        ]
    },
}
# ===== end BRICK G map =====

# ============================================================
# DATABASE HELPERS
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
        data = {"task_id": task_id, "tasks_completed": tasks_completed, "asset_links": asset_links, "asset_text": asset_text, "metrics": metrics, "score": score, "review": review, "evidence": evidence, "proof_files": proof_files or []}
        cur.execute("INSERT INTO standups (member_id, data) VALUES (%s, %s)", (member_id, json.dumps(data)))
        conn.commit(); cur.close(); conn.close()
    except: pass
    return True

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

def db_get_standups(member_id, limit=3):
    conn = checked_connection(globals())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT data, created_at FROM standups WHERE member_id = %s ORDER BY created_at DESC LIMIT %s", (member_id, limit))
            return [{**row["data"], "review_text": row["data"].get("review", ""), "created_at": str(row["created_at"])} for row in cur.fetchall()]
    except Exception:
        raise HTTPException(503, "Recent standups could not be read.")
    finally:
        conn.close()

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

def db_get_inactive_members():
    try:
        conn = get_db_connection()
        if not conn: return []
        cur = conn.cursor()
        cur.execute("""
            SELECT j.member_id, p.data->>'business_name' as business_name,
                   j.streak as streak, j.data->>'last_standup_date' as last_standup_date,
                   j.current_day as current_day, j.xp_total as xp,
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
# NVIDIA LLM
# ============================================================
def call_llm(messages, temperature=0.3, max_tokens=1024):
    if not NVIDIA_API_KEY:
        log.error("❌ NVIDIA_API_KEY is not set!")
        return "Error: No NVIDIA API key configured"
    for attempt in range(3):
        try:
            log.info(f"🚀 Calling NVIDIA NIM (attempt {attempt+1}/3)...")
            payload = json.dumps({"model": NVIDIA_MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode()
            req = urllib.request.Request(NVIDIA_URL, data=payload, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {NVIDIA_API_KEY}"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in [503,429,502,504]: time.sleep(2); continue
            log.error(f"NVIDIA HTTP {e.code}: {e.reason}")
            if e.code == 404:
                return f"Error: Model '{NVIDIA_MODEL}' not found. Update NVIDIA_MODEL in Railway."
            return f"Error: {e.code}"
        except Exception as e:
            log.warning(f"⚠️ NVIDIA attempt {attempt+1} failed: {e}")
            if attempt < 2: time.sleep(2); continue
    return "Error: Service temporarily unavailable"


async def stream_llm(messages, temperature=0.3):
    """Async generator yielding tokens from NVIDIA NIM stream."""
    if not NVIDIA_API_KEY:
        yield "Error: No NVIDIA API key configured"
        return
    payload = {
        "model": NVIDIA_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1024,
        "stream": True,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + NVIDIA_API_KEY,
        "Accept": "text/event-stream",
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", NVIDIA_URL, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    yield "Error: NVIDIA " + str(resp.status_code)
                    return
                line_count = 0
                async for line in resp.aiter_lines():
                    line_count += 1
                    if line_count <= 3:
                        log.info("NVIDIA RAW LINE: " + repr(line)[:300])
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
                    except Exception:
                        continue
    except Exception as e:
        yield "ERROR: " + str(e)

# ============================================================
# PYDANTIC MODELS
# ============================================================
class ChatMessage(BaseModel): role: Literal['user', 'assistant']; content: str = Field(max_length=20000)
class ChatRequest(BaseModel): message: str = Field(default="", max_length=20000); history: List[ChatMessage] = Field(default_factory=list, max_length=20); mode: str = "coach"; member_id: Optional[str] = "default"; beginner: bool = False
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
# HELPERS
# ============================================================
def get_current_task(journey):
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    return next((t for t in phase_info["tasks"] if t["id"] == journey["current_task_id"]), phase_info["tasks"][0])

def advance_journey(journey, member_id):
    # BRICK G: generic. Move to the next phase only when every task in the current phase is done.
    # No phase names or task ids are hardcoded. After the last phase, nothing changes (same as before).
    keys = list(JOURNEY_MAP.keys())
    phase = journey.get("current_phase")
    if phase not in JOURNEY_MAP:
        phase = keys[0]
        journey["current_phase"] = phase
    completed = journey.get("tasks_completed", []) or []
    remaining = [t for t in JOURNEY_MAP[phase]["tasks"] if t["id"] not in completed]
    if remaining:
        journey["current_task_id"] = remaining[0]["id"]
        return
    i = keys.index(phase)
    if i + 1 != len(keys):
        nxt = keys[i + 1]
        journey["current_phase"] = nxt
        nxt_remaining = [t for t in JOURNEY_MAP[nxt]["tasks"] if t["id"] not in completed]
        journey["current_task_id"] = (nxt_remaining or JOURNEY_MAP[nxt]["tasks"])[0]["id"]

def calculate_trajectory(journey):
    # Brick 3.1: pace from the current task's own deadline_day. Never behind before deadline + 3 days.
    import operator
    neutral = {"status": "on_track", "message": "", "color": "blue"}
    try:
        current_day = int(journey.get("current_day", 1) or 1)
        task = get_current_task(journey) or {}
        deadline = int(task.get("deadline_day") or 0)
        completed = set(journey.get("tasks_completed", []) or [])
    except Exception:
        return neutral
    if not deadline or task.get("id") in completed:
        return neutral
    over = current_day - deadline
    late_msg = "This task was planned for Day %d. Pick it up today. Nothing is lost." % deadline
    if operator.ge(over, 3):
        return {"status": "behind", "message": late_msg, "color": "neutral"}
    if operator.gt(over, 0):
        return {"status": "on_track", "message": late_msg, "color": "neutral"}
    ahead = False
    try:
        for phase in JOURNEY_MAP.values():
            for t in phase.get("tasks", []):
                if t.get("id") in completed and operator.gt(int(t.get("deadline_day") or 0), current_day):
                    ahead = True
    except Exception:
        ahead = False
    left = deadline - current_day
    if left == 0:
        msg = "Your current task is planned for Day %d. That's today." % deadline
    else:
        msg = "Your current task is planned for Day %d. You have %d day%s." % (deadline, left, "" if left == 1 else "s")
    if ahead:
        return {"status": "ahead", "message": msg, "color": "green"}
    return {"status": "on_track", "message": msg, "color": "blue"}

# ============================================================
# ROUTES — ALL DEFINED HERE
# ============================================================

# --- LANDING PAGE (ROOT) ---
@app.get("/")
async def landing_page():
    """Serve the landing page at the root URL."""
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    # If index.html doesn't exist, serve the app
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html", headers=NO_CACHE_HEADERS)
    return {"status": "ok", "message": "E5 AI Coach OS is running. Add index.html for landing page."}

# --- APP ---
@app.get("/chat")
@app.get("/chat.html")
@app.get("/app")
async def serve_app():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html", headers=NO_CACHE_HEADERS)
    return {"status": "ok", "message": "App not found"}

@app.get("/onboarding.html")
async def onboarding_page():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html", headers=NO_CACHE_HEADERS)
    return {"status": "ok"}

# --- HEALTH ---
@app.get("/api/health")
def health():
    return {"ok": True, "database": DATABASE_CONNECTED, "version": "6.0", "model": NVIDIA_MODEL}

# --- ONBOARDING ---
@app.get("/api/check-onboarding")
def check_onboarding(request: Request, member_id: str = "default"):
    member_id = require_member(request, member_id)
    profile = db_get_profile(member_id)
    journey = db_get_journey(member_id)
    return {"onboarded": bool(profile and (profile.get("onboarding_complete") or (profile.get("business_name") and profile.get("niche") and profile.get("core_offer")))), "profile": profile, "journey": journey}

@app.post("/api/onboarding")
def submit_onboarding(request: Request, req: OnboardingRequest):
    req.member_id = require_member(request, req.member_id)
    starting_day = 1
    if req.current_level == "intermediate" and (req.offer_done and req.audience_done): starting_day = 15
    elif req.current_level == "advanced" and (req.offer_done and req.audience_done and req.sales_done): starting_day = 31
    speed_profile = "accelerator" if req.weekly_hours == "8+" else "steady" if req.weekly_hours == "4-7" else "reflective"
    profile_data = req.dict()
    profile_data["speed_profile"] = speed_profile
    existing = db_get_profile(req.member_id) or {}
    db_upsert_profile(req.member_id, {**existing, **profile_data})
    current = db_get_journey(req.member_id)
    if not current.get("tasks_completed") and current.get("xp_total", 0) == 0:
        db_upsert_journey(req.member_id, {"current_day": starting_day, "current_phase": "Phase 1", "current_task_id": "p1_t1", "tasks_completed": [], "streak": 0, "last_standup_date": None, "xp_total": 0, "badges": []})
    return {"success": True, "starting_day": starting_day, "speed_profile": speed_profile}

@app.post("/api/generate-strategy")
def generate_strategy(request: Request, req: StrategyRequest):
    req.member_id = require_member(request, req.member_id)
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
Customize advice accordingly.
Include: Current Stage, Biggest Challenge, Recommended Focus, Starting Day, Speed Profile, Recommended First Task, and Next Steps."""
    user = f"Stage: {req.stage}, Challenge: {req.bottleneck}, Hours: {req.hours}, Traffic: {traffic_source}. Starting Day: {starting_day}, Speed: {speed_profile}, Focus: {focus}"
    document = llm_result(call_llm([{"role": "system", "content": system}, {"role": "user", "content": user}]))
    save_strategy(globals(), req.member_id, {"document": document, "starting_day": starting_day, "speed_profile": speed_profile, "bottleneck": req.bottleneck, "primary_traffic_source": traffic_source})
    return {"document": document, "starting_day": starting_day, "speed_profile": speed_profile, "focus": focus}

@app.post("/api/complete-onboarding")
def complete_onboarding(request: Request, req: CompleteOnboardingRequest):
    req.member_id = require_member(request, req.member_id)
    profile = db_get_profile(req.member_id)
    if not profile:
        db_upsert_profile(req.member_id, {"business_name": "New Member", "niche": "", "target_avatar": "", "biggest_bottleneck": req.bottleneck, "current_level": req.stage, "weekly_hours": req.hours, "speed_profile": req.speed_profile, "primary_traffic_source": req.primary_traffic_source, "onboarding_complete": True})
    else:
        db_upsert_profile(req.member_id, {**profile, "current_level": req.stage, "weekly_hours": req.hours, "speed_profile": req.speed_profile, "primary_traffic_source": req.primary_traffic_source, "onboarding_complete": True, "biggest_bottleneck": req.bottleneck})
    journey = db_get_journey(req.member_id) or {"member_id": req.member_id, "current_day": req.starting_day, "current_phase": "Phase 1", "current_task_id": "p1_t1", "tasks_completed": [], "streak": 0, "last_standup_date": None, "xp_total": 0, "badges": []}
    journey["current_day"] = max(journey.get("current_day", 1), req.starting_day)
    db_upsert_journey(req.member_id, journey)
    save_strategy(globals(), req.member_id, {"document": req.strategy_document, "starting_day": req.starting_day, "speed_profile": req.speed_profile, "bottleneck": req.bottleneck, "primary_traffic_source": req.primary_traffic_source})
    return {"success": True, "message": "Onboarding complete", "starting_day": req.starting_day, "speed_profile": req.speed_profile}


@app.get("/api/session")
def current_session(request: Request):
    return {"ok": True, "member_id": require_member(request),
            "csrf_token": csrf(request.state.session)}

@app.post("/api/logout")
def logout(request: Request):
    require_member(request)
    response = JSONResponse({"ok": True})
    for name in ["e5_session", "member_id", "whop_user_id", "whop_valid", "admin_secret", "pkce_verifier", "e5_oauth"]:
        response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")
    return response

@app.post("/api/business-profile")
def save_business_profile(request: Request, req: OnboardingRequest):
    req.member_id = require_member(request, req.member_id)
    existing = db_get_profile(req.member_id) or {}
    db_upsert_profile(req.member_id, {**existing, **req.dict()})
    return {"success": True, "journey_preserved": True}

# --- JOURNEY ---
@app.get("/api/journey")
def get_journey_status(request: Request, member_id: str = "default"):
    member_id = require_member(request, member_id)
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
        "standup_rubric": _e3_rubric(current_task) if isinstance(current_task, dict) else None,  # BRICK E3
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

# ===== BRICK E3: fair standup. Grading matches the task. Plain-language grader. =====
# Link (+2) and Numbers (+2) are scored by the server, and only when the task asks for them.
# The AI scores the rest (parts covered + quality). Total is always out of 10. Pass stays at 7.
# (needs_link, needs_numbers) per task. Unknown task ids fall back to the deliverables text.
# A task dict can override with "standup_link", "standup_metrics", "standup_checks".
_E3_NEEDS = {
    "p1_t1": (False, False), "p1_t2": (False, False), "p1_t3": (True, True), "p1_t4": (False, True),
    "p2_t1": (True, True), "p2_t2": (False, False), "p2_t3": (False, True), "p2_t4": (False, True),
    "p3_t1": (True, False), "p3_t2": (False, False), "p3_t3": (False, True), "p3_t4": (False, True),
}
# Keep in sync with chat_test.html BF_JARGON_CAPS / BF_JARGON_NAMES (BRICK F)
_E3_JARGON_CAPS = ["STORM", "CVJ", "AVOCADO", "SIPE", "VAGEL", "TTB", "FIBS", "F.I.B.S", "ECAFI"]
_E3_JARGON_NAMES = ["Hormozi", "Kallaway", "Cattoni", "Tutton", "Belcher", "Rohan", "Value Equation",
                    "Pain Stack", "Tiny Yeses", "DM Doctor", "Offer Architect", "Community OS",
                    "Content Engine", "Dream Customer", "Dream Follower", "Hook Mastery", "Anti-viral",
                    "Launch Planner", "21-day launch map", "Customer Value Journey",
                    # BRICK F.3: 25 more names from the framework corpus (Big Idea and Editorial Calendar left out on purpose)
                    "Jim Hamilton", "Todd Brown", "Kevin Rogers", "Chris Rocheleau",
                    "Bart Schutz", "DigitalMarketer", "Alex Cattoni", "Bullet Campaign",
                    "Message Mapping", "Copywriting Crossroads", "Email Storyselling", "Write and Ignite",
                    "Predictable Sales System", "Predictable Sales Canvas", "Ready Now Funnel", "Flood Your Funnel",
                    "Self Liquidating Offer", "Trial Upgrade Offer", "Value Journey", "Before After Grid",
                    "Gain Logic Fear", "Indoctrination Series", "Social Media Scorecards", "Lead Magnet Builder",
                    "Qualified Email",
                    # BRICK F.3c: 23 Content drawer selector names (agentic_core.py FRAMEWORK_GRAPH)
                    "S.O.U.L.F.U.L", "S.I.P.E", "R.I.P.E", "Content Cannon",
                    "Objection Akido", "Value Ladder Canvas", "Perfect Offer Builder", "Million Dollar Message",
                    "Core Message Canvas", "Green to Ripe Sequence", "MVC Build Sheets", "One Group Audit Checklist",
                    "Ascension Map", "Growth Scorecard", "Big 3 Planning Canvas", "Insight Call Script",
                    "Buyer Signal Cheat Sheet", "7-Scenario DM Playbook", "ICP Builder", "10 Pillars of Offer Doc",
                    "CVJ Audit", "Step LTV Benchmark", "Bottleneck Hunter"]

# ===== BRICK F.3: one plain-words rule for every coach prompt (same lists as the grader) =====
def _f3_banned_words():
    return ", ".join(_E3_JARGON_CAPS + _E3_JARGON_NAMES)


def _f3_plain_rule():
    return ("Plain everyday words only. Never name a framework, method, book or author. "
            "Never write any of these words: " + _f3_banned_words() + ".")


SELF_CRITIQUE_BLOCK = SELF_CRITIQUE_BLOCK.replace("[F3_PLAIN_RULE]", _f3_plain_rule())
# ===== end BRICK F.3 =====


def _e3_rubric(task):
    task = task if isinstance(task, dict) else {}
    tid = str(task.get("id", ""))
    if tid in _E3_NEEDS:
        link, numbers = _E3_NEEDS[tid]
    else:
        text = " ".join(str(d) for d in task.get("deliverables", [])).lower()
        link = any(w in text for w in ("link", "url"))
        numbers = any(w in text for w in ("count", "rate", "revenue", "views", "reported", "before and after", "tracker", "%"))
    link = bool(task.get("standup_link", link))
    numbers = bool(task.get("standup_metrics", numbers))
    checks = bool(task.get("standup_checks", False))
    ai_max = 10 - (2 if link else 0) - (2 if numbers else 0)
    parts = 2 + (0 if link else 1) + (0 if numbers else 1)
    return {"task_id": tid, "link": link, "metrics": numbers, "checks": checks,
            "parts_max": parts, "quality_max": ai_max - parts, "ai_max": ai_max}


def _e3_has_link(links):
    for x in links or []:
        s = str(x or "").strip().lower()
        if s.startswith("http://") or s.startswith("https://") or s.startswith("/api/proof/"):
            return True
    return False


def _e3_has_numbers(metrics):
    return bool(re.search(r"\d", str(metrics or "")))


def _e3_has_jargon(s):
    s = str(s or "")
    caps = r"\b(" + "|".join(re.escape(w) for w in _E3_JARGON_CAPS) + r")\b"
    names = r"(?i)\b(" + "|".join(re.escape(w) for w in _E3_JARGON_NAMES) + r")\b"
    return bool(re.search(caps, s) or re.search(names, s))


def _e3_grader_prompt(task, profile, rubric, link_ok, numbers_ok):
    N = chr(10)
    parts = N.join(str(i + 1) + ". " + str(d) for i, d in enumerate(task.get("deliverables", []))) or "- (no list given)"  # BRICK E3.1
    lines = [
        "You check a beginner's work on one task in a business coaching app. Be fair, kind and honest.",
        "",
        "TASK: " + str(task.get("name", "")),
        "WHY IT MATTERS: " + str(task.get("why", "")),
        "THE PARTS OF THIS TASK:", parts,
        "MEMBER: niche = " + str(profile.get("niche", "N/A")) + ", customer = " + str(profile.get("target_avatar", "N/A")),
        "",
        "Score only two things:",
        "1. PARTS (0-" + str(rubric["parts_max"]) + "): how much of the list above is clearly in the work. Short, simple answers count. If a part is a link or a number, skip it: the app checks those itself.",
        "2. QUALITY (0-" + str(rubric["quality_max"]) + "): is it specific to their business and their customer, and could they really use it?",
        "Add the two. Never take points off for missing links or numbers, and never for spelling, grammar or language.",
    ]
    if rubric["link"]:
        lines.append("Note: this task needs a link. Link given: " + ("yes" if link_ok else "no") + ".")
    if rubric["metrics"]:
        lines.append("Note: this task needs numbers. Numbers given: " + ("yes" if numbers_ok else "no") + ".")
    lines += [
        "",
        "Rules: plain everyday words, like a kind friend. No jargon, no acronyms, no framework names, no author or book names. Do not invent anything about their work. Write REASON, HINT and NEXT in the same language as the member's work.",
        "",
        "OUTPUT exactly these 5 lines and nothing else:",
        "GRADE: X/" + str(rubric["ai_max"]),
        "REASON: one short sentence, the main reason for this score",
        "HINT: one short sentence, the single most useful thing to add or fix",
        "NEXT: one short sentence, what to do once this task is done",
        "MISSING: the numbers of the parts above that are missing or too thin, separated by commas, or none",  # BRICK E3.1
    ]
    return N.join(lines)


def _e3_parse_grade(raw, ai_max):
    m = re.search(r"GRADE:\s*(\d+)(?:\s*/\s*(\d+))?", str(raw or ""))
    if not m:
        return 0
    x = int(m.group(1))
    if m.group(2):
        den = int(m.group(2))
    else:
        den = ai_max if x <= ai_max else 10
    if den > 0 and den != ai_max:
        x = int(round(x * ai_max / float(den)))
    return min(ai_max, max(0, x))


def _e3_line(raw, key):
    m = re.search(r"(?im)^[\s*#_-]*" + key + r"[\s*_]*:[\s*_]*(.+)$", str(raw or ""))
    if not m:
        return ""
    s = re.sub(r"(?i)<br\s*/?>", " ", m.group(1))
    s = re.sub(r"[*_`#]+", "", s).strip()
    return s[:300]


def _e3_feedback(raw, score, rubric, link_ok, numbers_ok):
    passed = score >= 7
    reason, hint, nxt = _e3_line(raw, "REASON"), _e3_line(raw, "HINT"), _e3_line(raw, "NEXT")
    if not reason or _e3_has_jargon(reason):
        reason = "Your work covers what this task asks for." if passed else "Some parts of this task are still missing or too general."
    if not passed and rubric["link"] and not link_ok:
        hint = "Add the link to your work. It must start with http:// or https://"
    elif not passed and rubric["metrics"] and not numbers_ok:
        hint = "Add your real numbers, for example views, replies or sales."
    elif not hint or _e3_has_jargon(hint):
        hint = "Pick the part of the list you skipped and add it in a few clear lines."
    if not nxt or _e3_has_jargon(nxt):
        nxt = "Open your next task and start with the first part."
    return reason, hint, nxt


def _e3_review_text(score, reason, hint, nxt):
    N = chr(10)
    out = "GRADE: " + str(score) + "/10" + N + N + "REASON: " + reason + N + N
    return out + ("NEXT: " + nxt if score >= 7 else "HINT: " + hint)


# ===== BRICK E3.1: relaxed standup minimum + missing_items in the /api/standup response =====
# missing_items lists what is still missing, in plain words. It never changes the score.
# Server checks: work too short, link (only if the task needs one), numbers (only if needed).
# AI check: the grader's MISSING line gives the numbers of the task parts not yet covered.
import operator as _op31

_E31_MIN_CHARS = 15
_E31_MIN_WORDS = 3


def _e31_work_ok(text):
    s = str(text or "").strip()
    return _op31.ge(len(s), _E31_MIN_CHARS) or _op31.ge(len(s.split()), _E31_MIN_WORDS)


def _e31_missing_parts(raw, deliverables):
    line = _e3_line(raw, "MISSING")
    if not line or re.match(r"(?i)\s*(none|nothing|no|n/a|-)(\W|$)", line):
        return []
    out = []
    for m in re.findall(r"\d+", line):
        i = int(m)
        if i in range(1, len(deliverables) + 1) and i not in out:
            out.append(i)
    return out[:10]


def _e31_missing_items(raw, task, rubric, link_ok, numbers_ok, asset_text):
    try:
        items = []
        if not _e31_work_ok(asset_text):
            items.append({"key": "work", "label": "A few clear lines about what you did"})
        if rubric.get("link") and not link_ok:
            items.append({"key": "link", "label": "A link to your work (starting with http:// or https://)"})
        if rubric.get("metrics") and not numbers_ok:
            items.append({"key": "numbers", "label": "Your real numbers, for example views, replies or sales"})
        deliverables = [str(d) for d in (task.get("deliverables") or [])]
        for i in _e31_missing_parts(raw, deliverables):
            label = deliverables[i - 1].strip()[:200]
            if label and not _e3_has_jargon(label):
                items.append({"key": "part", "index": i, "label": label})
            elif label:
                items.append({"key": "part", "index": i, "label": "Part " + str(i) + " of this task"})
        return items
    except Exception:
        return []
# ===== end BRICK E3.1 helpers =====


# --- STANDUP ---
@app.post("/api/standup")
def submit_standup(request: Request, req: StandupRequest):
    req.member_id = require_member(request, req.member_id)
    profile = db_get_profile(req.member_id)
    if not profile: raise HTTPException(403, "Complete onboarding first.")
    journey = db_get_journey(req.member_id)
    import copy
    old_journey = copy.deepcopy(journey)
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    if req.current_task_id != journey.get("current_task_id"):
        raise HTTPException(409, "Journey task changed. Refresh before submitting.")
    if req.current_task_id in journey.get("tasks_completed", []):
        raise HTTPException(409, "This task is already complete.")
    task = next((t for t in phase_info["tasks"] if t["id"] == req.current_task_id), None)
    if not task: raise HTTPException(422, "Unknown journey task.")
    # Files were uploaded separately; validate that supplied receipts belong to this member.
    from pathlib import Path
    owned_files = {Path(str(p.get("filepath", ""))).name for p in db_get_proofs(req.member_id)}
    for pf in req.proof_files or []:
        name = str(pf.get("url", "")).rsplit("/", 1)[-1]
        if name not in owned_files: raise HTTPException(422, "Upload proof before attaching its receipt.")

    # BRICK E3: grading matches the task. The server scores link and numbers, the AI scores the rest.
    rubric = _e3_rubric(task)
    link_ok = _e3_has_link(req.asset_links)
    numbers_ok = _e3_has_numbers(req.metrics)
    system = _e3_grader_prompt(task, profile, rubric, link_ok, numbers_ok)
    prompt = "Completed actions: " + "; ".join(str(x) for x in req.tasks_completed) + "\nLinks: " + ", ".join(str(x) for x in req.asset_links) + "\nWork: " + str(req.asset_text) + "\nNumbers: " + str(req.metrics)
    raw_review = llm_result(call_llm([{"role":"system","content":system},{"role":"user","content":prompt}]))
    if not re.search(r'GRADE:\s*\d+', str(raw_review)): raise HTTPException(502, "AI review did not include a valid grade.")
    ai_score = _e3_parse_grade(raw_review, rubric["ai_max"])
    link_pts = 2 if (rubric["link"] and link_ok) else 0
    number_pts = 2 if (rubric["metrics"] and numbers_ok) else 0
    score = min(10, max(0, ai_score + link_pts + number_pts))
    e3_reason, e3_hint, e3_next = _e3_feedback(raw_review, score, rubric, link_ok, numbers_ok)
    review = _e3_review_text(score, e3_reason, e3_hint, e3_next)
    e3_missing = _e31_missing_items(raw_review, task, rubric, link_ok, numbers_ok, req.asset_text)  # BRICK E3.1
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
        journey["current_day"] = min(90, journey.get("current_day",1) + 5)  # BRICK G: 18 tasks x 5 days
        advance_journey(journey, req.member_id)
        xp_gained = 125
        journey["xp_total"] = journey.get("xp_total",0) + xp_gained
    else:
        xp_gained = 25
        journey["xp_total"] = journey.get("xp_total", 0) + xp_gained
    persist_review(globals(), req.member_id, old_journey, journey, {"task_id": req.current_task_id, "tasks_completed": ",".join(req.tasks_completed), "asset_links": ",".join(req.asset_links), "asset_text": req.asset_text, "metrics": req.metrics, "score": score, "review": review, "evidence": evidence, "proof_files": req.proof_files}, score)
    return {"success": True, "review": review, "score": score, "task_unlocked": score >= 7, "streak": journey.get("streak",0), "xp_gained": xp_gained, "xp_total": journey.get("xp_total",0), "journey_updated": True, "reason": e3_reason, "hint": e3_hint, "next_step": e3_next, "missing_items": e3_missing, "rubric": rubric, "points": {"ai": ai_score, "link": link_pts, "numbers": number_pts}}  # BRICK E3

# --- WIN ---
@app.post("/api/win")
def submit_win(request: Request, req: WinRequest):
    req.member_id = require_member(request, req.member_id)
    if not db_get_profile(req.member_id): raise HTTPException(403, "Complete onboarding first.")
    db_add_win(req.member_id, req.win_text, req.revenue_amount)
    return {"success": True, "total_wins": len(db_get_wins(req.member_id))}

# --- CHAT ---
@app.post("/api/chat")
def chat(request: Request, req: ChatRequest):
    req.member_id = require_member(request, req.member_id)
    if not req.message: raise HTTPException(400, "empty message")
    profile = db_get_profile(req.member_id or "default")
    if not profile: raise HTTPException(403, "GATEKEEPER: Complete onboarding first.")
    journey = db_get_journey(req.member_id or "default")
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    current_task = get_current_task(journey)
    task_completed = current_task["id"] in journey.get("tasks_completed", [])
    task_status_line = "✅ Task completed" if task_completed else "⏳ Task NOT yet completed — nudge them to finish it, but still answer their question first."
    wins_text = "No wins yet."
    wins = db_get_wins(req.member_id or "default")
    if wins: wins_text = f"{len(wins)} wins. Latest: {wins[0]['win_text'][:100]}"
    scores = db_get_scores(req.member_id or "default")
    avg_score = round(sum(scores)/len(scores),1) if scores else 0
    traffic_source = profile.get('primary_traffic_source', 'content')
    # Fetch recent context for personalization
    member_id_for_ctx = req.member_id or "default"
    recent_standups = db_get_standups(member_id_for_ctx, 3)
    standups_text = "None yet."
    if recent_standups:
        lines = []
        for s in recent_standups:
            sc = s.get('score', '?')
            notes = (s.get('review_text') or s.get('asset_text') or '')[:200]
            lines.append(f"- Score: {sc}/10 | Notes: {notes}")
        standups_text = "\n".join(lines)
    recent_wins_list = db_get_wins(member_id_for_ctx)[:3]
    wins_full_text = "None yet."
    if recent_wins_list:
        wins_full_text = "\n".join([f"- {w.get('win_text','')[:200]}" for w in recent_wins_list])
    recent_scores_list = scores[-3:] if scores else []
    scores_text = ", ".join([str(s) for s in recent_scores_list]) if recent_scores_list else "None yet"

    framework_context = ""
    if FRAMEWORK_SEARCH_AVAILABLE:
        try:
            framework_context = search_frameworks(req.message, top_k=3, max_chars=2500)
        except Exception as e:
            log.error(f"Framework search error: {e}")

    system_prompt = f"""You are the E5 AI Coach.

LANGUAGE RULE: Always respond in the same language the user writes in. If they write Arabic, respond fully in Arabic (Modern Standard Arabic). If they write English, respond in English. If they mix, match the dominant language. Never mix languages in one response.
MEMBER: {profile.get('business_name','N/A')} | Niche: {profile.get('niche','N/A')} | Bottleneck: {profile.get('biggest_bottleneck','N/A')} | Speed: {profile.get('speed_profile','steady')} | Traffic Source: {traffic_source}
Day: {journey.get('current_day',1)}/90 | Phase: {phase_info['name']} | Current Task: {current_task['name']} | Task Status: {task_status_line} | Streak: {journey.get('streak',0)}

RECENT STANDUPS (last 3):
{standups_text}

RECENT WINS (last 3):
{wins_full_text}

RECENT SCORES (last 3): {scores_text}

COACH NOTES (use the ideas, never the names; use ONLY if directly relevant to the user's question, otherwise ignore):
{framework_context if framework_context else "No notes matched."}

RULES: Diagnose first. Personalize using the RECENT STANDUPS and WINS above — reference the user's actual work. Use plain everyday words, never framework names. ALWAYS answer the user's question, even if their current task is not completed — then nudge them back to the task. 60% questions / 40% insight. Short (150-250 words). Never invent.  Never repeat a recommendation you already gave. OUTPUT: Markdown only. Use ## headers for sections, numbered lists for steps, bullets for details, blank lines between sections. Bold only key terms. Max 250 words. No walls of text.

SELF-CRITIQUE (run this checklist on your draft BEFORE you output it. Do not output the checklist itself):
1. {_f3_plain_rule()}
2. User context referenced (their day, task, bottleneck, or recent win)? If no, add one.
3. Banned phrases absent? Never use: 'it depends', 'you should consider', 'in today's world', 'at the end of the day', 'it's important to', 'remember that'.
4. At least 2 markdown sections with ## headers? If no, restructure.
5. Ends with a single, clear question? If no, add one.
Only output the FINAL improved version."""
    system_prompt = _b5_system_prompt(req, profile, journey, phase_info, current_task, framework_context, standups_text, wins_full_text, system_prompt)
    system_prompt = _bf_system_prompt(req, current_task, system_prompt)  # BRICK F
    messages = [{"role": "system", "content": system_prompt}] + [{"role": m.role, "content": m.content} for m in req.history[-10:]] + [{"role": "user", "content": req.message}]
    reply = llm_result(call_llm(messages))
    return {"reply": reply}


# ===== BRICK F: EMBEDDED COACH IN TRY AGAIN. Plain prompt for chat mode "standup_fix". =====
# Used only when the request says mode == "standup_fix" (sent by the Try again coach panel).
# Any other mode, or any error, returns the prompt unchanged. Grader and scoring are not touched.
BF_MODE = "standup_fix"


def _bf_system_prompt(req, current_task, default_prompt):
    try:
        if str(getattr(req, "mode", "") or "") != BF_MODE:
            return default_prompt
        task = current_task if isinstance(current_task, dict) else {}
        N = chr(10)
        rubric = _e3_rubric(task)
        parts = N.join("- " + str(d) for d in task.get("deliverables", [])) or "- (no list given)"
        needs = []
        if rubric.get("link"):
            needs.append("a link to their work")
        if rubric.get("metrics"):
            needs.append("their real numbers")
        lines = [
            "You help someone fix their daily standup before they submit it again. Their last try did not pass yet.",
            "",
            "TASK: " + str(task.get("name", "")),
            "THE PARTS OF THIS TASK:", parts,
            "THIS TASK ALSO NEEDS: " + (", ".join(needs) if needs else "nothing else"),
            "",
            "The user message has their current text, their score, the reason, a hint and what is still missing.",
            "",
            "Rules:",
            "- Plain everyday words, like a kind friend. No jargon, no acronyms, no framework names, no author or book names.",
            "- Never lecture. No lists of tips, no headings, no markdown.",
            "- 2 to 4 short sentences in total.",
            "- First reply: give ONE concrete suggestion for the biggest missing item: one or two sentences they could add to their own text, in their voice, inside double quotes. Use only facts from their text. Where a fact is missing, leave a blank like [your number].",
            "- Follow-up: answer their question directly in 1 to 3 sentences, then stop.",
            "- Never rewrite their whole text. Never invent results, numbers or links.",
            # BRICK F.1: language fix
            "- Write in English by default. Only write in another language if the user's own text is clearly and mostly in that language.",
        ]
        return N.join(lines)
    except Exception:
        return default_prompt
# ===== end BRICK F helper =====


@app.post("/api/chat/stream")
async def chat_stream(request: Request, req: ChatRequest):
    req.member_id = require_member(request, req.member_id)
    if not req.message: raise HTTPException(400, "empty message")
    profile = db_get_profile(req.member_id or "default")
    if not profile: raise HTTPException(403, "GATEKEEPER: Complete onboarding first.")
    journey = db_get_journey(req.member_id or "default")
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    current_task = get_current_task(journey)
    task_completed = current_task["id"] in journey.get("tasks_completed", [])
    task_status_line = "Task completed" if task_completed else "Task NOT yet completed"
    wins = db_get_wins(req.member_id or "default")
    scores = db_get_scores(req.member_id or "default")
    avg_score = round(sum(scores)/len(scores),1) if scores else 0
    traffic_source = profile.get('primary_traffic_source', 'content')
    member_id_for_ctx = req.member_id or "default"
    recent_standups = db_get_standups(member_id_for_ctx, 3)
    standups_text = "None yet."
    if recent_standups:
        lines = []
        for s in recent_standups:
            sc = s.get('score', '?')
            notes = (s.get('review_text') or s.get('asset_text') or '')[:200]
            lines.append("- Score: " + str(sc) + "/10 | Notes: " + notes)
        standups_text = chr(10).join(lines)
    recent_wins_list = wins[:3]
    wins_full_text = "None yet."
    if recent_wins_list:
        wins_full_text = chr(10).join(["- " + (w.get('win_text','') or '')[:200] for w in recent_wins_list])
    recent_scores_list = scores[-3:] if scores else []
    scores_text = ", ".join([str(s) for s in recent_scores_list]) if recent_scores_list else "None yet"
    framework_context = ""
    if FRAMEWORK_SEARCH_AVAILABLE:
        try:
            framework_context = search_frameworks(req.message, top_k=3, max_chars=2500)
        except Exception as e:
            log.error("Framework search error: " + str(e))
    N = chr(10)
    system_prompt = (
        "You are the E5 AI Coach." + N + N +
        "LANGUAGE RULE: Always respond in the same language the user writes in. If Arabic, respond in Arabic. If English, respond in English." + N +
        "MEMBER: " + str(profile.get('business_name','N/A')) + " | Niche: " + str(profile.get('niche','N/A')) + " | Bottleneck: " + str(profile.get('biggest_bottleneck','N/A')) + " | Speed: " + str(profile.get('speed_profile','steady')) + " | Traffic: " + str(traffic_source) + N +
        "Day: " + str(journey.get('current_day',1)) + "/90 | Phase: " + str(phase_info['name']) + " | Task: " + str(current_task['name']) + " | Status: " + task_status_line + " | Streak: " + str(journey.get('streak',0)) + N + N +
        "RECENT STANDUPS:" + N + standups_text + N + N +
        "RECENT WINS:" + N + wins_full_text + N + N +
        "RECENT SCORES: " + scores_text + N + N +
        "COACH NOTES (use the ideas, never the names):" + N + (framework_context if framework_context else "None matched.") + N + N +
        "RULES: Diagnose first. Personalize. Use plain everyday words, never framework names. ALWAYS answer the user's question, then nudge them back to the task. 60% questions / 40% insight. Short (150-250 words). Never invent. OUTPUT: Markdown only. Use ## headers, numbered lists, bullets, blank lines. Bold only key terms. Max 250 words." + SELF_CRITIQUE_BLOCK
    )
    system_prompt = _b5_system_prompt(req, profile, journey, phase_info, current_task, framework_context, standups_text, wins_full_text, system_prompt)
    system_prompt = _bf_system_prompt(req, current_task, system_prompt)  # BRICK F
    messages = [{"role": "system", "content": system_prompt}] + [{"role": m.role, "content": m.content} for m in req.history[-10:]] + [{"role": "user", "content": req.message}]

    async def event_stream():
        try:
            async for token in stream_llm(messages):
                if token.lstrip().lower().startswith("error:"):
                    yield "data: " + json.dumps({"error": "AI provider unavailable. Retry later."}) + N + N
                    yield "data: [DONE]" + N + N
                    return
                yield "data: " + json.dumps({"token": token}) + N + N
            yield "data: [DONE]" + N + N
        except Exception as e:
            yield "data: " + json.dumps({"error": str(e)}) + N + N
            yield "data: [DONE]" + N + N

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# --- RE-ENGAGEMENT ---
@app.post("/api/check-inactive")
def check_inactive():
    inactive = db_get_inactive_members()
    sent = 0
    for m in inactive:
        if send_re_engagement_notification(m): sent += 1
    return {"success": True, "inactive_count": len(inactive), "sent_count": sent}

@app.post("/api/trigger-re-engagement")
def trigger_re_engagement(request: Request, member_id: str):
    member_id = require_member(request, member_id)
    return {"success": True, "member_id": member_id, "delivered": False, "message": "Acknowledged only; no notification was sent."}

# ============================================================
# NEW: VOICE AI COACH (TTS)
# ============================================================
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    log.warning("⚠️ edge-tts not installed. Voice TTS will not work. Run: pip install edge-tts")

@app.post("/api/tts")
async def text_to_speech(request: Request):
    if not EDGE_TTS_AVAILABLE:
        return JSONResponse({"error": "TTS not available. Install edge-tts."}, status_code=500)
    try:
        data = await request.json()
        text = data.get("text", "")
        if not text:
            return JSONResponse({"error": "No text provided"}, status_code=400)
        voice = data.get("voice", "en-US-AriaNeural")
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        return JSONResponse({"audio": audio_base64})
    except Exception as e:
        log.error(f"TTS Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ============================================================
# NEW: FUNNEL ANALYZER
# ============================================================
# ===== BRICK E1A: server freeze fix. Sync AI calls inside async routes run in the threadpool. =====
from starlette.concurrency import run_in_threadpool as _e1_pool

@app.post("/api/analyze-funnel")
async def analyze_funnel(request: Request):
    try:
        data = await request.json()
        url = data.get("url", "")
        member_id = require_member(request, data.get("member_id"))
        if not url:
            return JSONResponse({"error": "No URL provided"}, status_code=400)
        profile = db_get_profile(member_id) or {}
        niche = profile.get("niche", "digital products")
        business_name = profile.get("business_name", "your business")
        prompt = f"""
        You are a funnel hacking expert. Analyze this competitor's funnel:
        URL: {url}
        Member's Niche: {niche}
        Member's Business: {business_name}

        Provide analysis with:
        1. 🎯 HEADLINE ANALYSIS
        2. 📢 CALL-TO-ACTION (CTA)
        3. 💰 PRICING STRATEGY
        4. 📊 SOCIAL PROOF
        5. 🔥 3 ACTIONABLE IMPROVEMENTS
        Format with clear headings and bullet points.
        """
        analysis = await _e1_pool(call_llm, [{"role": "system", "content": "You are a world-class funnel hacker. Use plain everyday words, never framework names. Score each section /100. Give specific fixes with time estimates. No generic advice."}, {"role": "user", "content": prompt}], temperature=0.4, max_tokens=3000)  # BRICK E1A
        return {"analysis": llm_result(analysis), "page_fetched": False, "analysis_type": "url_only_hypothesis"}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Funnel Analysis Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ============================================================
# NEW: PROACTIVE SUGGESTIONS
# ============================================================
@app.post("/api/proactive-suggest")
async def proactive_suggest(request: Request):
    try:
        data = await request.json()
        member_id = require_member(request, data.get("member_id"))
        journey = db_get_journey(member_id)
        profile = db_get_profile(member_id) or {}
        if not journey:
            return JSONResponse({"error": "Member not found"}, status_code=404)
        last_date = journey.get("last_standup_date")
        days_since = 0
        if last_date:
            try: days_since = (date.today() - date.fromisoformat(last_date)).days
            except: days_since = 0
        current_task = get_current_task(journey)
        task_name = current_task.get("name", "your current task")
        streak = journey.get("streak", 0)
        tasks_completed = len(journey.get("tasks_completed", []))
        total_tasks = sum(len(v["tasks"]) for v in JOURNEY_MAP.values())  # BRICK G
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
        """
        urgency = "critical" if days_since >= 14 else "warning" if days_since >= 7 else "gentle" if days_since >= 3 else "normal"
        prompt = f"""
        Based on this member's progress, provide ONE specific, actionable suggestion.
        {context}
        Urgency: {urgency}
        Keep under 150 words. Include a call to action.
        """
        suggestion = call_llm([{"role": "system", "content": "You are a proactive, encouraging business coach."}, {"role": "user", "content": prompt}])
        return {"suggestion": llm_result(suggestion), "urgency": urgency, "days_since": days_since, "streak": streak}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Proactive Suggestion Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ============================================================
# NEW: FUNNEL MAP
# ============================================================
@app.get("/api/funnel")
async def get_funnel(request: Request, member_id: str = "default"):
    member_id = require_member(request, member_id)
    funnel = db_get_funnel(member_id)
    return {"success": True, "funnel": funnel}

@app.post("/api/funnel")
async def save_funnel(request: Request):
    data = await request.json()
    member_id = require_member(request, data.get("member_id"))
    funnel_data = data.get("funnel", {"stages": []})
    db_save_funnel(member_id, funnel_data)
    return {"success": True}

# ============================================================
# NEW: FILE UPLOADS
# ============================================================
@app.post("/api/upload-proof")
async def upload_proof(request: Request, member_id: str = Form(...), file: UploadFile = File(...)):
    member_id = require_member(request, member_id)
    from pathlib import Path
    blob = await file.read(5 * 1024 * 1024 + 1)
    ext = check_upload(file.filename, blob)
    name = str(uuid4()) + ext
    path = Path(UPLOAD_DIR) / name
    path.write_bytes(blob)
    try:
        db_add_proof(member_id, Path(file.filename or "proof").name, str(path))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return {"success": True, "filename": Path(file.filename or "proof").name, "path": str(path), "url": "/api/proof/" + name}

@app.get("/api/proof/{filename}")
async def get_proof(request: Request, filename: str):
    from pathlib import Path
    member_id = require_member(request)
    if Path(filename).name != filename:
        raise HTTPException(404, "File not found.")
    owned = any(Path(str(p.get("filepath", ""))).name == filename for p in db_get_proofs(member_id))
    path = Path(UPLOAD_DIR) / filename
    if not owned or not path.is_file(): raise HTTPException(404, "File not found.")
    # Force download; no active HTML/script rendering on the application origin.
    return FileResponse(str(path), media_type="application/octet-stream", filename=filename,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

# ============================================================
# NEW: WHOP INTEGRATION
# ============================================================
@app.get("/api/whop/verify")
async def verify_whop_membership(request: Request, member_id: str = "default"):
    member_id = require_member(request, member_id)
    if not WHOP_API_KEY:
        return {"error": "Whop API key not configured. Add WHOP_API_KEY to Railway."}
    profile = db_get_profile(member_id) or {}
    whop_user_id = profile.get("whop_user_id")
    if not whop_user_id:
        return {"error": "Whop user ID not found. Connect your account first."}
    try:
        import requests
        headers = {"Authorization": f"Bearer {WHOP_API_KEY}"}
        url = "https://api.whop.com/api/v1/memberships"
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
    log.info(f"Whop webhook received: {event_type}")
    return {"status": "ok"}

# ============================================================
# NEW: SOCIAL MEDIA CONNECT
# ============================================================
@app.post("/api/social/connect")
async def connect_social(request: Request):
    data = await request.json()
    member_id = require_member(request, data.get("member_id"))
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
async def get_social_analytics(request: Request, member_id: str = "default", platform: str = ""):
    member_id = require_member(request, member_id)
    if not platform:
        return {"error": "Platform required"}
    profile = db_get_profile(member_id) or {}
    social = profile.get("social_accounts", {}).get(platform)
    if not social:
        return {"error": "Account not connected"}
    username = social.get("username")
    if not TIKHUB_API_KEY:
        return {
            "platform": platform,
            "username": username,
            "message": "Social analytics requires TIKHUB_API_KEY. Add to Railway to enable."
        }
    try:
        import requests
        url = f"https://api.tikhub.io/v1/{platform}/user/{username}/stats"
        headers = {"Authorization": f"Bearer {TIKHUB_API_KEY}"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                "platform": platform,
                "username": username,
                "followers": data.get("followers_count", 0),
                "engagement_rate": data.get("engagement_rate", 0),
                "avg_views": data.get("avg_views", 0)
            }
        return {"error": "Failed to fetch analytics"}
    except Exception as e:
        return {"error": str(e)}

# ============================================================
# MAIN
# ============================================================
# ============================================================
# ROUTES
# ============================================================
@app.get("/premium_dashboard.js")
def premium_dashboard_js():
    return FileResponse("premium_dashboard.js")

@app.get("/test")
def test_page():
    return RedirectResponse("/app", status_code=302)
# ============================================================

# ============================================================
# NEW FEATURES (Add new routes here, always at the left edge)
# ============================================================
@app.get("/funnel")
def funnel_page():
    return FileResponse("funnel.html", headers=NO_CACHE_HEADERS)

@app.get("/staging")
async def staging():
    return FileResponse("app_staging.html", headers=NO_CACHE_HEADERS)


# ============================================================
# BRICK 1A — ACTIVITY EVENTS (behavior/UX tracking only)
# Silent by design: DB problems are logged (throttled), never raised.
# Not scorekeeping: North Star metrics come from standups/scores tables.
# Written without angle-bracket characters on purpose (copy-safe):
#   _op.lt(a, b) means a is less than b
#   _op.le(a, b) means a is less than or equal to b
#   _op.gt(a, b) means a is greater than b
#   _op.ge(a, b) means a is greater than or equal to b
# ============================================================
import operator as _op
from psycopg2.extras import execute_values
from starlette.concurrency import run_in_threadpool

ACTIVITY_EVENT_TYPES = {
    "onboarding_answered", "first_creation_saved", "today_viewed",
    "task_started", "task_submitted", "task_passed", "task_failed",
    "coach_message_sent", "tool_opened", "win_logged",
}
ACTIVITY_ONCE_TYPES = {"first_creation_saved"}
ACTIVITY_MAX_BATCH = 50
ACTIVITY_MAX_META_BYTES = 2048
ACTIVITY_MAX_BODY_BYTES = 128 * 1024
ACTIVITY_RATE_PER_MIN = 100
_ACTIVITY_WINDOWS = {}
_ACTIVITY_LOCK = threading.Lock()
_ACTIVITY_LAST_ERROR_LOG = [0.0]


def _activity_log_error(msg):
    """Log at most one activity error line per minute."""
    now = time.time()
    if _op.ge(now - _ACTIVITY_LAST_ERROR_LOG[0], 60):
        _ACTIVITY_LAST_ERROR_LOG[0] = now
        log.error("Activity: " + str(msg))


def get_db_connection_quiet():
    """Copy of get_db_connection() without the per-call INFO log."""
    try:
        if not all([PGHOST, PGDATABASE, PGUSER, PGPASSWORD]):
            return None
        return psycopg2.connect(
            host=PGHOST, database=PGDATABASE, user=PGUSER,
            password=PGPASSWORD, port=PGPORT, cursor_factory=RealDictCursor
        )
    except Exception as e:
        _activity_log_error("DB Error: " + str(e))
        return None


def _activity_take_quota(member_id, wanted):
    """Fixed 60s window per member. Returns how many events may be stored now."""
    if _op.le(wanted, 0):
        return 0
    now = time.time()
    with _ACTIVITY_LOCK:
        if _op.gt(len(_ACTIVITY_WINDOWS), 10000):
            for k, v in list(_ACTIVITY_WINDOWS.items()):
                if _op.ge(now - v[0], 60):
                    _ACTIVITY_WINDOWS.pop(k, None)
        win = _ACTIVITY_WINDOWS.get(member_id)
        if not win or _op.ge(now - win[0], 60):
            win = [now, 0]
            _ACTIVITY_WINDOWS[member_id] = win
        allowed = max(0, min(wanted, ACTIVITY_RATE_PER_MIN - win[1]))
        win[1] += allowed
        return allowed


def _activity_clean(item):
    """Return (event_type, meta_json) or None if rejected."""
    if not isinstance(item, dict):
        return None
    event_type = item.get("event_type")
    if not isinstance(event_type, str):
        return None
    event_type = event_type.strip()
    if event_type not in ACTIVITY_EVENT_TYPES:
        return None
    meta = item.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    try:
        meta_json = json.dumps(meta, default=str, allow_nan=False)
    except Exception:
        meta_json = "{}"
    if _op.gt(len(meta_json.encode("utf-8")), ACTIVITY_MAX_META_BYTES):
        ts = meta.get("ts")
        meta_json = json.dumps({"meta_dropped": "too_large",
                                "ts": ts if isinstance(ts, (int, float)) else None})
    return (event_type, meta_json)


def _activity_store(member_id, rows):
    """Insert cleaned rows in one transaction. Returns (stored, skipped) or None."""
    if not rows:
        return (0, 0)
    conn = get_db_connection_quiet()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        skipped = 0
        once_in_batch = {et for et, _ in rows if et in ACTIVITY_ONCE_TYPES}
        if once_in_batch:
            cur.execute(
                "SELECT DISTINCT event_type FROM events WHERE member_id = %s AND event_type = ANY(%s)",
                (member_id, list(once_in_batch)))
            already = {r["event_type"] for r in cur.fetchall()}
            seen, kept = set(), []
            for et, mj in rows:
                if et in ACTIVITY_ONCE_TYPES:
                    if et in already or et in seen:
                        skipped += 1
                        continue
                    seen.add(et)
                kept.append((et, mj))
            rows = kept
        stored = 0
        if rows:
            execute_values(
                cur,
                "INSERT INTO events (member_id, event_type, meta) VALUES %s ON CONFLICT DO NOTHING",
                [(member_id, et, mj) for et, mj in rows],
                template="(%s, %s, %s::jsonb)", page_size=ACTIVITY_MAX_BATCH)
            stored = max(0, cur.rowcount)
            skipped += len(rows) - stored
        conn.commit()
        cur.close()
        return (stored, skipped)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        _activity_log_error("insert failed: " + str(e))
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def _activity_read_body(request):
    """Read and parse the JSON body. Returns a dict or None (never raises)."""
    try:
        raw = await request.body()
        if not raw or _op.gt(len(raw), ACTIVITY_MAX_BODY_BYTES):
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


@app.post("/api/activity")
async def activity_single(request: Request):
    member_id = require_member(request)
    try:
        body = await _activity_read_body(request)
        row = _activity_clean(body) if body else None
        if not row:
            return {"ok": False, "reason": "rejected"}
        if _op.lt(_activity_take_quota(member_id, 1), 1):
            return {"ok": False, "reason": "rate_limited"}
        result = await run_in_threadpool(_activity_store, member_id, [row])
        if result is None:
            return {"ok": False, "reason": "db_unavailable"}
        return {"ok": True, "stored": result[0], "skipped": result[1]}
    except Exception as e:
        _activity_log_error("/api/activity: " + str(e))
        return {"ok": False, "reason": "error"}


@app.post("/api/activity/batch")
async def activity_batch(request: Request):
    member_id = require_member(request)
    try:
        body = await _activity_read_body(request)
        items = body.get("events") if body else None
        if not isinstance(items, list) or not items:
            return {"ok": False, "reason": "rejected"}
        over_cap = max(0, len(items) - ACTIVITY_MAX_BATCH)
        items = items[:ACTIVITY_MAX_BATCH]
        rows = [r for r in (_activity_clean(i) for i in items) if r]
        rejected = (len(items) - len(rows)) + over_cap
        allowed = _activity_take_quota(member_id, len(rows))
        rate_limited = len(rows) - allowed
        rows = rows[:allowed]
        if not rows:
            return {"ok": False, "reason": "rate_limited" if rate_limited else "rejected",
                    "rejected": rejected, "rate_limited": rate_limited}
        result = await run_in_threadpool(_activity_store, member_id, rows)
        if result is None:
            return {"ok": False, "reason": "db_unavailable"}
        return {"ok": True, "stored": result[0], "skipped": result[1],
                "rejected": rejected, "rate_limited": rate_limited}
    except Exception as e:
        _activity_log_error("/api/activity/batch: " + str(e))
        return {"ok": False, "reason": "error"}


@app.get("/api/activity/recent")
def activity_recent(request: Request, limit: str = "50"):
    member_id = require_member(request)
    try:
        n = max(1, min(200, int(limit)))
    except Exception:
        n = 50
    conn = get_db_connection_quiet()
    if not conn:
        return {"ok": False, "events": []}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, event_type, meta, created_at FROM events "
            "WHERE member_id = %s ORDER BY created_at DESC, id DESC LIMIT %s",
            (member_id, n))
        rows = cur.fetchall()
        cur.close()
        return {"ok": True, "count": len(rows), "events": [
            {"id": r["id"], "event_type": r["event_type"], "meta": r["meta"] or {},
             "created_at": r["created_at"].isoformat() if r["created_at"] else None}
            for r in rows]}
    except Exception as e:
        _activity_log_error("/api/activity/recent: " + str(e))
        return {"ok": False, "events": []}
    finally:
        try:
            conn.close()
        except Exception:
            pass




# ============================================================
# BRICK 1B: WORKSPACE SYNC (localStorage snapshots, version-checked)
# Silent by design: DB problems are logged (throttled), never raised.
# Comparisons use the operator module (copy-safe, no angle brackets).
# ============================================================
import operator as _sop
from starlette.concurrency import run_in_threadpool as _sync_threadpool

SYNC_TOOL_KEYS = ("funnel", "launch", "reality", "content", "community",
                  "leads", "actions", "library", "dna")
SYNC_MAX_TOOL_BYTES = 1024 * 1024        # 1 MB per tool
SYNC_MAX_BODY_BYTES = 2 * 1024 * 1024    # 2 MB per request
SYNC_RATE_PER_MIN = 60                   # requests per member per minute
_SYNC_WINDOWS = {}
_SYNC_LOCK = threading.Lock()
_SYNC_LAST_ERROR_LOG = [0.0]


def _sync_log_error(msg):
    """Log at most one sync error line per minute."""
    now = time.time()
    if _sop.ge(now - _SYNC_LAST_ERROR_LOG[0], 60):
        _SYNC_LAST_ERROR_LOG[0] = now
        log.error("Sync: " + str(msg))


def _sync_conn():
    """Quiet DB connection for the sync endpoints (no per-call INFO log)."""
    try:
        if not all([PGHOST, PGDATABASE, PGUSER, PGPASSWORD]):
            return None
        return psycopg2.connect(host=PGHOST, database=PGDATABASE, user=PGUSER,
                                password=PGPASSWORD, port=PGPORT, cursor_factory=RealDictCursor)
    except Exception as e:
        _sync_log_error(f"DB Error: {e}")
        return None


def _sync_close(conn):
    try:
        conn.close()
    except Exception:
        pass


def _sync_allow(member_id):
    """Fixed 60s window per member. True if this request may proceed."""
    now = time.time()
    with _SYNC_LOCK:
        if _sop.gt(len(_SYNC_WINDOWS), 10000):
            for k, v in list(_SYNC_WINDOWS.items()):
                if _sop.ge(now - v[0], 60):
                    _SYNC_WINDOWS.pop(k, None)
        win = _SYNC_WINDOWS.get(member_id)
        if not win or _sop.ge(now - win[0], 60):
            win = [now, 0]
            _SYNC_WINDOWS[member_id] = win
        if _sop.ge(win[1], SYNC_RATE_PER_MIN):
            return False
        win[1] += 1
        return True


def _sync_iso(value):
    return value.isoformat() if value else None


def _sync_prepare(tool_key, item):
    """Validate one tool snapshot. Returns a dict with data_json/base/client_ts, or {"error": reason}."""
    if tool_key not in SYNC_TOOL_KEYS:
        return {"error": "unknown_tool"}
    if not isinstance(item, dict):
        return {"error": "bad_item"}
    data = item.get("data")
    if not isinstance(data, (dict, list)):
        return {"error": "bad_data"}
    try:
        data_json = json.dumps(data, allow_nan=False, separators=(",", ":"))
    except Exception:
        return {"error": "bad_data"}
    if _sop.gt(len(data_json.encode("utf-8")), SYNC_MAX_TOOL_BYTES):
        return {"error": "too_large"}
    base = item.get("base_updated_at")
    if isinstance(base, str) and base.strip():
        try:
            datetime.fromisoformat(base.strip())
            base = base.strip()
        except Exception:
            base = None
    else:
        base = None
    try:
        client_ts = int(item.get("client_ts"))
        if _sop.lt(client_ts, 0):
            client_ts = None
    except Exception:
        client_ts = None
    return {"data_json": data_json, "base": base, "client_ts": client_ts}


def _sync_write(member_id, prepared):
    """Version-checked upserts in one transaction. Returns {tool_key: result} or None on DB failure.
    A write only lands if the server copy is still the version the browser last saw (base_updated_at),
    or if no server copy exists yet. Otherwise the result is a conflict carrying the server copy."""
    conn = _sync_conn()
    if not conn:
        return None
    results = {}
    try:
        cur = conn.cursor()
        for tool_key, p in prepared.items():
            row = None
            if p["base"]:
                cur.execute(
                    "UPDATE local_state SET data = %s::jsonb, client_ts = %s, updated_at = NOW() "
                    "WHERE member_id = %s AND tool_key = %s AND updated_at = %s::timestamptz "
                    "RETURNING updated_at",
                    (p["data_json"], p["client_ts"], member_id, tool_key, p["base"]))
                row = cur.fetchone()
            if not row:
                cur.execute(
                    "INSERT INTO local_state (member_id, tool_key, data, client_ts, updated_at) "
                    "VALUES (%s, %s, %s::jsonb, %s, NOW()) "
                    "ON CONFLICT (member_id, tool_key) DO NOTHING RETURNING updated_at",
                    (member_id, tool_key, p["data_json"], p["client_ts"]))
                row = cur.fetchone()
            if row:
                results[tool_key] = {"status": "saved", "updated_at": _sync_iso(row["updated_at"])}
                continue
            cur.execute(
                "SELECT data, updated_at, client_ts FROM local_state WHERE member_id = %s AND tool_key = %s",
                (member_id, tool_key))
            srv = cur.fetchone()
            results[tool_key] = {
                "status": "conflict",
                "data": srv["data"] if srv else None,
                "updated_at": _sync_iso(srv["updated_at"]) if srv else None,
                "client_ts": srv["client_ts"] if srv else None,
            }
        conn.commit()
        cur.close()
        return results
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        _sync_log_error(f"write failed: {e}")
        return None
    finally:
        _sync_close(conn)


def _sync_read(member_id):
    """Returns (tools, meta) or None on DB failure."""
    conn = _sync_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT tool_key, data, updated_at, client_ts FROM local_state WHERE member_id = %s",
            (member_id,))
        rows = cur.fetchall()
        cur.close()
        tools, meta = {}, {}
        for r in rows:
            if r["tool_key"] in SYNC_TOOL_KEYS:
                tools[r["tool_key"]] = r["data"]
                meta[r["tool_key"]] = {"updated_at": _sync_iso(r["updated_at"]), "client_ts": r["client_ts"]}
        return (tools, meta)
    except Exception as e:
        _sync_log_error(f"read failed: {e}")
        return None
    finally:
        _sync_close(conn)


def _sync_remove(member_id, tool_key):
    """Delete one snapshot (tool_key) or all of them (tool_key None). Returns count or None."""
    conn = _sync_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        if tool_key:
            cur.execute("DELETE FROM local_state WHERE member_id = %s AND tool_key = %s", (member_id, tool_key))
        else:
            cur.execute("DELETE FROM local_state WHERE member_id = %s", (member_id,))
        n = max(0, cur.rowcount)
        conn.commit()
        cur.close()
        return n
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        _sync_log_error(f"delete failed: {e}")
        return None
    finally:
        _sync_close(conn)


@app.get("/api/sync")
def sync_get(request: Request):
    member_id = require_member(request)  # outside try: 401 behaves like every other route
    try:
        result = _sync_read(member_id)
    except Exception as e:
        _sync_log_error(f"GET /api/sync: {e}")
        result = None
    if result is None:
        return JSONResponse({"ok": False, "reason": "db_unavailable"}, headers=NO_CACHE_HEADERS)
    return JSONResponse({"ok": True, "tools": result[0], "meta": result[1]}, headers=NO_CACHE_HEADERS)


@app.post("/api/sync")
async def sync_post(request: Request):
    member_id = require_member(request)  # outside try: 401 behaves like every other route
    try:
        if not _sync_allow(member_id):
            return {"ok": False, "reason": "rate_limited"}
        raw = await request.body()
        if not raw:
            return {"ok": False, "reason": "rejected"}
        if _sop.gt(len(raw), SYNC_MAX_BODY_BYTES):
            return {"ok": False, "reason": "too_large"}
        try:
            body = json.loads(raw)
        except Exception:
            body = None
        if not isinstance(body, dict):
            return {"ok": False, "reason": "rejected"}
        single = isinstance(body.get("tool_key"), str)
        items = {body["tool_key"]: body} if single else body.get("tools")
        if not isinstance(items, dict) or not items:
            return {"ok": False, "reason": "rejected"}
        results, prepared = {}, {}
        for k, item in list(items.items())[:len(SYNC_TOOL_KEYS)]:
            p = _sync_prepare(str(k), item)
            if "error" in p:
                results[str(k)] = {"status": "rejected", "reason": p["error"]}
            else:
                prepared[str(k)] = p
        if prepared:
            written = await _sync_threadpool(_sync_write, member_id, prepared)
            if written is None:
                return {"ok": False, "reason": "db_unavailable", "results": results}
            results.update(written)
        out = {"ok": True, "results": results}
        if single:
            one = results.get(body["tool_key"], {})
            out["status"] = one.get("status")
            out["updated_at"] = one.get("updated_at")
        return out
    except Exception as e:
        _sync_log_error(f"POST /api/sync: {e}")
        return {"ok": False, "reason": "error"}


@app.delete("/api/sync")
def sync_delete(request: Request):
    member_id = require_member(request)  # outside try: 401 behaves like every other route
    try:
        qp = request.query_params
        tool_key = (qp.get("tool_key") or "").strip()
        wipe_all = (qp.get("all") or "").strip() in ("1", "true")
        if tool_key and tool_key not in SYNC_TOOL_KEYS:
            return {"ok": False, "reason": "unknown_tool"}
        if not tool_key and not wipe_all:
            return {"ok": False, "reason": "rejected"}
        n = _sync_remove(member_id, tool_key or None)
        if n is None:
            return {"ok": False, "reason": "db_unavailable"}
        return {"ok": True, "deleted": n}
    except Exception as e:
        _sync_log_error(f"DELETE /api/sync: {e}")
        return {"ok": False, "reason": "error"}
# ===== end BRICK 1B backend =====


# ============================================================
# BRICK 4: FIRST WIN (10-minute first task: offer, 3 outcomes, price, guarantee)
# POST /api/first-win/draft  AI drafts all four parts (counts against the AI quota)
# POST /api/first-win        saves them and completes task p1_t1 in one locked transaction
# Silent by design: after require_member, every failure is {"ok": False, "reason": ...} with HTTP 200.
# Does not add 7 days, does not touch the streak, writes no standup or score row.
# ============================================================
from integration_support import check_rate_limit as _fw_rate_check

FW_TASK_ID = "p1_t1"
FW_XP = 125
FW_MAX_BODY_BYTES = 32 * 1024
FW_WHERE = {"youtube": "content", "dms": "outbound", "community": "community", "email": "email"}
FW_HOURS = ("1-3", "4-7", "8+")
FW_SPEED = {"1-3": "reflective", "4-7": "steady", "8+": "accelerator"}


def _fw_text(value, max_len):
    """Single-line, trimmed, length-capped text. Non-strings become empty."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:max_len]


async def _fw_read(request):
    try:
        raw = await request.body()
        if not raw or len(raw) > FW_MAX_BODY_BYTES:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _fw_answers(raw):
    a = raw if isinstance(raw, dict) else {}
    out = {}
    sell = _fw_text(a.get("sell"), 300)
    who = _fw_text(a.get("who"), 300)
    where = str(a.get("where") or "").strip().lower()
    hours = str(a.get("hours") or "").strip()
    if sell:
        out["sell"] = sell
    if who:
        out["who"] = who
    if where in FW_WHERE:
        out["where"] = where
    if hours in FW_HOURS:
        out["hours"] = hours
    return out


def _fw_outcomes(value):
    items = value if isinstance(value, list) else []
    return [x for x in (_fw_text(i, 200) for i in items) if x][:3]


def _fw_clean_win(body):
    """Returns (win, None) or (None, message). All four parts of p1_t1 are required."""
    offer = _fw_text(body.get("offer"), 280)
    outcomes = _fw_outcomes(body.get("outcomes"))
    price = _fw_text(body.get("price"), 60)
    guarantee = _fw_text(body.get("guarantee"), 280)
    if len(offer) < 15:
        return None, "Write your offer in at least 15 characters."
    if len(outcomes) != 3:
        return None, "Fill in all 3 results your customer gets."
    if not price:
        return None, "Add a price. A guess is fine; you can change it later."
    if not guarantee:
        return None, "Add a guarantee, even a simple one."
    return {"offer": offer, "outcomes": outcomes, "price": price, "guarantee": guarantee}, None


def _fw_draft_messages(a):
    where_label = {"youtube": "YouTube or short videos", "dms": "direct messages",
                   "community": "an online community", "email": "an email list"}.get(a.get("where", ""), "not given")
    system = (
        "You help a beginner coach or creator write their first offer. "
        "Write in the same language as their answers. Use plain, everyday words. "
        "No framework names, no jargon, no hype, no income claims. "
        "Return ONLY one JSON object, no markdown, no code fences, with exactly these keys: "
        '{"offer": "one sentence: who it helps, the result, and how", '
        '"outcomes": ["result 1", "result 2", "result 3"], '
        '"price": "a realistic starting price with currency, e.g. $97", '
        '"guarantee": "one simple, honest guarantee they can keep"}. '
        "The JSON keys stay in English."
    )
    user = (
        "What I sell: " + a.get("sell", "") + "\n"
        "Who it is for: " + a.get("who", "") + "\n"
        "Where my audience is: " + where_label + "\n"
        "Hours per week I have: " + a.get("hours", "not given")
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _fw_parse_draft(raw):
    s = str(raw or "")
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1 or j <= i:
        return None
    try:
        d = json.loads(s[i:j + 1])
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    draft = {"offer": _fw_text(d.get("offer"), 280), "outcomes": _fw_outcomes(d.get("outcomes")),
             "price": _fw_text(str(d.get("price") or ""), 60), "guarantee": _fw_text(d.get("guarantee"), 280)}
    if not draft["offer"] or len(draft["outcomes"]) != 3 or not draft["price"] or not draft["guarantee"]:
        return None
    return draft


def _fw_commit(member_id, win, answers):
    """Complete p1_t1 and merge the profile in one transaction (journey row locked)."""
    conn = _sync_conn()
    if not conn:
        return {"ok": False, "reason": "db_unavailable"}
    try:
        with conn:
            with conn.cursor() as cur:
                default = {"current_day": 1, "current_phase": "Phase 1", "current_task_id": FW_TASK_ID,
                           "tasks_completed": [], "streak": 0, "last_standup_date": None, "xp_total": 0, "badges": []}
                cur.execute("INSERT INTO journeys (member_id, data) VALUES (%s, %s) ON CONFLICT (member_id) DO NOTHING",
                            (member_id, json.dumps(default)))
                cur.execute("SELECT data FROM journeys WHERE member_id = %s FOR UPDATE", (member_id,))
                row = cur.fetchone()
                journey = dict(row["data"]) if row and isinstance(row.get("data"), dict) else dict(default)
                completed = list(journey.get("tasks_completed") or [])
                if FW_TASK_ID in completed:
                    return {"ok": False, "reason": "already_done"}
                if journey.get("current_phase", "Phase 1") != "Phase 1" or journey.get("current_task_id", FW_TASK_ID) != FW_TASK_ID:
                    return {"ok": False, "reason": "wrong_task"}
                now = datetime.now().isoformat()
                completed.append(FW_TASK_ID)
                journey["tasks_completed"] = completed
                journey.setdefault("current_phase", "Phase 1")
                journey.setdefault("current_day", 1)
                advance_journey(journey, member_id)
                journey["xp_total"] = int(journey.get("xp_total") or 0) + FW_XP
                journey["first_win_at"] = now
                cur.execute("UPDATE journeys SET data = %s WHERE member_id = %s", (json.dumps(journey), member_id))
                cur.execute("SELECT data FROM profiles WHERE member_id = %s FOR UPDATE", (member_id,))
                prow = cur.fetchone()
                profile = dict(prow["data"]) if prow and isinstance(prow.get("data"), dict) else {}
                profile.update({"core_offer": win["offer"], "offer_outcomes": win["outcomes"],
                                "offer_price": win["price"], "offer_guarantee": win["guarantee"],
                                "onboarding_complete": True, "first_win_at": now})
                if answers.get("sell"):
                    profile["offer_sells"] = answers["sell"]
                    if not str(profile.get("niche") or "").strip():
                        profile["niche"] = answers["sell"]
                if answers.get("who"):
                    profile["target_avatar"] = answers["who"]
                if answers.get("where"):
                    profile["primary_traffic_source"] = FW_WHERE[answers["where"]]
                    profile["audience_channel"] = answers["where"]
                if answers.get("hours"):
                    profile["weekly_hours"] = answers["hours"]
                    profile["speed_profile"] = FW_SPEED[answers["hours"]]
                if not str(profile.get("business_name") or "").strip():
                    profile["business_name"] = str(profile.get("name") or "").strip() or "New Member"
                profile.setdefault("current_level", "beginner")
                cur.execute("INSERT INTO profiles (member_id, data) VALUES (%s, %s) "
                            "ON CONFLICT (member_id) DO UPDATE SET data = EXCLUDED.data",
                            (member_id, json.dumps(profile)))
        return {"ok": True, "task_unlocked": True, "task_id": FW_TASK_ID, "xp_gained": FW_XP,
                "xp_total": journey["xp_total"], "streak": journey.get("streak", 0),
                "next_task_id": journey.get("current_task_id")}
    except Exception as e:
        log.error("FirstWin: save failed: " + str(e))
        return {"ok": False, "reason": "db_unavailable"}
    finally:
        _sync_close(conn)


@app.post("/api/first-win/draft")
async def first_win_draft(request: Request):
    member_id = require_member(request)  # outside try: 401 behaves like every other route
    try:
        body = await _fw_read(request)
        if body is None:
            return {"ok": False, "reason": "invalid"}
        a = _fw_answers(body.get("answers"))
        if not a.get("sell") or not a.get("who"):
            return {"ok": False, "reason": "invalid", "detail": "Tell us what you sell and who it is for."}
        session = getattr(request.state, "session", None) or {}
        if not session.get("admin"):
            # Counted against the existing AI quota (20/min, 500/day) via an AI path it already covers.
            if _fw_rate_check(member_id, "/api/ai/generate") is not None:
                return {"ok": False, "reason": "rate_limited"}
        raw = await run_in_threadpool(call_llm, _fw_draft_messages(a), 0.4, 900)
        if not isinstance(raw, str) or not raw.strip() or raw.lstrip().lower().startswith("error:"):
            return {"ok": False, "reason": "ai_unavailable"}
        draft = _fw_parse_draft(raw)
        if not draft:
            return {"ok": False, "reason": "ai_bad_output"}
        return {"ok": True, "draft": draft}
    except Exception as e:
        log.error("FirstWin: draft failed: " + str(e))
        return {"ok": False, "reason": "ai_unavailable"}


@app.post("/api/first-win")
async def first_win_save(request: Request):
    member_id = require_member(request)  # outside try: 401 behaves like every other route
    try:
        body = await _fw_read(request)
        if body is None:
            return {"ok": False, "reason": "invalid"}
        if str(body.get("current_task_id") or "") != FW_TASK_ID:
            return {"ok": False, "reason": "wrong_task"}
        win, err = _fw_clean_win(body)
        if not win:
            return {"ok": False, "reason": "invalid", "detail": err}
        return await run_in_threadpool(_fw_commit, member_id, win, _fw_answers(body.get("answers")))
    except Exception as e:
        log.error("FirstWin: save failed: " + str(e))
        return {"ok": False, "reason": "error"}
# ===== end BRICK 4 backend =====

# ============================================================
# BRICK 5: BEGINNER COACH PROMPT (guided-mode users only)
# Used only when the request says beginner=true AND the server's journey has
# fewer than 2 completed tasks (the same rule as guided mode). Otherwise the
# original prompt is used, unchanged. Any error falls back to the original.
# ============================================================
import operator as _op5

B5_GUIDED_TASK_LIMIT = 2  # BRICK F.4: no longer used (no task cutoff), kept for reference


def _b5_beginner_on(req, journey):
    try:
        if getattr(req, "beginner", False) is not True:
            return False
        # BRICK F.4: no task cutoff. The browser decides (beginner = guidedOn(), off only via Show all tools).
        return True
    except Exception:
        return False


def _b5_system_prompt(req, profile, journey, phase_info, current_task, framework_context,
                      standups_text, wins_text, default_prompt):
    if not _b5_beginner_on(req, journey):
        return default_prompt
    try:
        N = chr(10)
        p = profile if isinstance(profile, dict) else {}
        t = current_task if isinstance(current_task, dict) else {}
        done = t.get("id") in (journey.get("tasks_completed") or [])
        dels = N.join("- " + str(d) for d in (t.get("deliverables") or []))
        return (
            "You are a warm, practical business coach talking to a beginner." + N + N +
            "LANGUAGE RULE: Always reply in the same language the user writes in. If Arabic, reply fully in Arabic. If English, reply in English." + N + N +
            "MEMBER: Sells: " + str(p.get("core_offer") or p.get("niche") or "not set yet") +
            " | Helps: " + str(p.get("target_avatar") or "not set yet") +
            " | Audience channel: " + str(p.get("primary_traffic_source", "content")) +
            " | Hours per week: " + str(p.get("weekly_hours", "not set")) + N +
            "Day: " + str(journey.get("current_day", 1)) + "/90 | Phase: " + str(phase_info.get("name", "")) +
            " | Current task: " + str(t.get("name", "")) +
            " | Status: " + ("completed" if done else "not completed yet") + N +
            "WHAT THE CURRENT TASK ASKS FOR:" + N + (dels or "- (nothing listed)") + N + N +
            "RECENT STANDUPS:" + N + str(standups_text) + N + N +
            "RECENT WINS:" + N + str(wins_text) + N + N +
            "BACKGROUND IDEAS (use the ideas if they help; never mention their names, authors, books or sources):" + N +
            (framework_context if framework_context else "None.") + N + N +
            "RULES:" + N +
            "1. Use plain, everyday words. No jargon, no acronyms, no framework names, no author or book names." + N +
            "2. Work on one part of the current task at a time." + N +
            "3. Give at most 3 numbered steps the user can do today." + N +
            "4. End with at most one short question." + N +
            "5. Keep it under about 150 words: a short paragraph, then the numbered steps. No headings." + N +
            "6. Always answer the user's question first. If it is off-task, answer briefly, then bring them back to the current task." + N +
            "7. Never invent facts about the user. Never promise income or results."
        )
    except Exception:
        return default_prompt
# ===== end BRICK 5 backend =====



# ============================================================
# MAIN (This MUST be at the very bottom)
# ============================================================


# ===== DIRECT AI ENDPOINT =====
class AIRequest(BaseModel):
    prompt: str
    member_id: str = "default"

@app.post("/api/ai/generate")
async def ai_generate(request: Request, req: AIRequest):
    req.member_id = require_member(request, req.member_id)
    try:
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            from langchain_groq import ChatGroq
            llm = ChatGroq(model="openai/gpt-oss-120b", groq_api_key=groq_key, temperature=0.7)
            result = llm.invoke(req.prompt)
            return {"ok": True, "text": result.content, "model": "groq"}

        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"))
            result = model.generate_content(req.prompt)
            return {"ok": True, "text": result.text, "model": "gemini"}

        nvidia_key = os.environ.get("NVIDIA_API_KEY")
        if nvidia_key:
            from openai import OpenAI
            client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nvidia_key)
            completion = client.chat.completions.create(
                model=os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"),
                messages=[{"role": "user", "content": req.prompt}],
                temperature=0.7,
                max_tokens=4000,
            )
            return {"ok": True, "text": completion.choices[0].message.content, "model": "nvidia"}

        return {"ok": False, "error": "No AI API key configured"}
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)}



from agentic_core import agentic_pipeline

class AgenticRequest(BaseModel):
    prompt: str
    member_id: str = "default"
    dna: str = "not set"

@app.post("/api/ai/agentic")
async def ai_agentic(request: Request, req: AgenticRequest):
    req.member_id = require_member(request, req.member_id)
    try:
        return await _e1_pool(agentic_pipeline, req.prompt, req.dna)  # BRICK E1A
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# WHOP OAUTH GATE
# ============================================================
WHOP_CLIENT_ID = os.environ.get("WHOP_AICOACH_CLIENT_ID", "").strip()
WHOP_CLIENT_SECRET = os.environ.get("WHOP_AICOACH_CLIENT_SECRET", "").strip()
WHOP_PRODUCT_ID = os.environ.get("WHOP_AICOACH_PRODUCT_ID", "").strip()
WHOP_COMMUNITY_PRODUCT_ID = os.environ.get("WHOP_COMMUNITY_PRODUCT_ID", "").strip()
WHOP_REDIRECT_URI = os.environ.get("WHOP_AICOACH_REDIRECT_URI", "").strip()
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "").strip()

import hashlib
import secrets
import base64

@app.get("/auth/whop")
def whop_login(request: Request):
    from urllib.parse import urlencode, quote
    client_id = (WHOP_CLIENT_ID or "").strip()
    redirect_uri = (WHOP_REDIRECT_URI or "").strip()
    if not client_id:
        raise HTTPException(status_code=500, detail="Whop Client ID not set")
    _prune_oauth_states()
    nonce = secrets.token_urlsafe(16)
    state = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    OAUTH_STATES[state] = {
        "verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "exp": int(time.time()) + 600,
    }
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
"scope": "openid profile email",
            "nonce": nonce,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        },
        quote_via=quote,
    )
    response = RedirectResponse(f"https://api.whop.com/oauth/authorize?{query}")
    return response

@app.get("/auth/whop/callback")
async def whop_callback(code: str, request: Request, state: str = ""):
    import logging
    from fastapi.responses import JSONResponse
    log = logging.getLogger("uvicorn.error")

    client_id = (WHOP_CLIENT_ID or "").strip()
    client_secret = (WHOP_CLIENT_SECRET or "").strip()
    if not client_id or not client_secret or not WHOP_PRODUCT_ID:
        raise HTTPException(status_code=500, detail="Whop credentials not configured")

    flow = OAUTH_STATES.pop(state, None) if state else None
    if not flow or flow.get("exp", 0) < time.time():
        log.warning("Whop OAuth: unknown/expired state (server restarted, page refreshed, or old link)")
        raise HTTPException(400, "OAuth state is invalid or expired. Please sign in again.")
    code_verifier = flow["verifier"]
    redirect_uri = flow.get("redirect_uri") or (WHOP_REDIRECT_URI or "").strip()
    token_url = "https://api.whop.com/oauth/token"

    def whop_error(step, resp):
        body = (resp.text or "")[:2000]
        log.error("Whop OAuth %s failed: HTTP %s body=%s", step, resp.status_code, body)
        try:
            detail = resp.json()
        except Exception:
            detail = body
        return JSONResponse(
            status_code=400,
            content={"error": f"Whop {step} failed", "whop_status": resp.status_code, "whop_response": detail},
        )

    async with httpx.AsyncClient(timeout=30) as client:
        # Attempt 1: confidential client, client_secret in JSON body
        token_resp = await client.post(
            token_url,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        if token_resp.status_code == 401:
            log.warning("Whop token exchange (JSON + secret) got 401: %s -- retrying with HTTP Basic auth", (token_resp.text or "")[:2000])
            token_resp = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "code_verifier": code_verifier,
                },
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
            )
        if not (200 <= token_resp.status_code < 300):
            return whop_error("token exchange", token_resp)
        try:
            token_data = token_resp.json()
        except Exception:
            return whop_error("token exchange (non-JSON response)", token_resp)
        access_token = token_data.get("access_token")
        if not access_token:
            log.error("Whop OAuth: token response had no access_token: %s", (token_resp.text or "")[:2000])
            raise HTTPException(status_code=400, detail="Failed to get access token")

        user_resp = await client.get(
            "https://api.whop.com/api/v1/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status_code == 200:
            user_data = user_resp.json()
            user_id = user_data.get("id")
        else:
            log.warning("Whop /api/v1/users/me returned HTTP %s: %s -- falling back to /oauth/userinfo", user_resp.status_code, (user_resp.text or "")[:2000])
            user_resp = await client.get(
                "https://api.whop.com/oauth/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_resp.status_code != 200:
                return whop_error("user lookup", user_resp)
            user_data = user_resp.json()
            user_id = user_data.get("sub") or user_data.get("id")
            user_data.setdefault("username", user_data.get("preferred_username", ""))
        if not user_id:
            log.error("Whop OAuth: no user id in user response: %s", (user_resp.text or "")[:2000])
            raise HTTPException(400, "Whop returned no user identity.")

        has_access = False
        if WHOP_PRODUCT_ID:
            access_resp = await client.get(
                f"https://api.whop.com/api/v1/users/{user_id}/access/{WHOP_PRODUCT_ID}",
                headers={"Authorization": f"Bearer {WHOP_API_KEY}"},
            )
            if access_resp.status_code != 200:
                log.warning("Whop access check (product) HTTP %s: %s", access_resp.status_code, (access_resp.text or "")[:2000])
            access_data = access_resp.json()
            if access_data.get("has_access"):
                has_access = True
        if not has_access and WHOP_COMMUNITY_PRODUCT_ID:
            access_resp = await client.get(
                f"https://api.whop.com/api/v1/users/{user_id}/access/{WHOP_COMMUNITY_PRODUCT_ID}",
                headers={"Authorization": f"Bearer {WHOP_API_KEY}"},
            )
            if access_resp.status_code != 200:
                log.warning("Whop access check (community) HTTP %s: %s", access_resp.status_code, (access_resp.text or "")[:2000])
            access_data = access_resp.json()
            if access_data.get("has_access"):
                has_access = True
    if has_access:
        email = user_data.get("email", "")
        name = user_data.get("name", "") or user_data.get("username", "")
        current = db_get_profile(user_id) or {}
        db_upsert_profile(user_id, {**current, "name": name, "email": email, "whop_user_id": user_id})
        response = RedirectResponse("/app", status_code=302)
        set_session(response, user_id)
        return response
    else:
        return RedirectResponse("https://whop.com/income-engine-growth-lab/ai-coach-7f/", status_code=302)

@app.get("/admin_login")
def admin_login(key: str = ""):
    raise HTTPException(410, "URL-key admin login is disabled. Use POST /auth/admin.")

@app.post("/auth/admin")
async def admin_session(request: Request):
    # Optional operator login; JSON body prevents putting keys into URLs/logs.
    origin = request.headers.get("Origin")
    expected = os.environ.get("APP_ORIGIN", "").rstrip("/")
    if origin and origin.rstrip("/") != (expected or str(request.base_url).rstrip("/")):
        raise HTTPException(403, "Origin not permitted.")
    body = await request.json()
    offered = str(body.get("key", ""))
    allowed = [x for x in (os.environ.get("ADMIN_SECRET", ""), os.environ.get("ADMIN_SECRET_2", "")) if x]
    if not any(secrets.compare_digest(offered, value) for value in allowed):
        raise HTTPException(403, "Forbidden.")
    # Stable opaque identity without disclosing the administrator key.
    uid = "admin_" + hashlib.sha256(offered.encode()).hexdigest()[:20]
    response = JSONResponse({"ok": True})
    return set_session(response, uid, admin=True)

@app.middleware("http")
async def whop_gate_middleware(request: Request, call_next):
    return await security_gate(request, call_next)


# ============================================================
# PROFILE API
# ============================================================
@app.get("/api/profile")
async def get_profile(request: Request):
    member_id = require_member(request)
    data = db_get_profile(member_id)
    if data is None:
        return {"ok": True, "profile": {"member_id": member_id, "name": "", "email": "", "data": {}}}
    return {"ok": True, "profile": {"member_id": member_id, "name": data.get("name", ""), "email": data.get("email", ""), "data": data}}

@app.post("/api/profile")
async def update_profile(request: Request):
    member_id = require_member(request)
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("data", {}), dict):
        raise HTTPException(422, "Profile must contain an object in data.")
    profile = db_get_profile(member_id) or {}
    # Only allow editable personal fields. Do not overwrite business/Whop context.
    extra = body.get("data", {})
    for field in ("avatar", "phone", "bio"):
        if field in extra: profile[field] = str(extra[field])[:3000]
    for field in ("name", "email"):
        if field in body: profile[field] = str(body[field])[:320]
    db_upsert_profile(member_id, profile)
    return {"ok": True}

# ============================================================
# DYNAMIC TASK GENERATOR
# ============================================================
class GenerateTasksRequest(BaseModel):
    member_id: str = "default"


# ===== BRICK F.2: no framework names in AI-generated tasks =====
# Only these fields are kept. frameworks is always [] so the frontend never falls back to [t.framework].
# A task whose text holds a jargon word is dropped (never scrubbed). Same lists as the grader.
_F2_ALLOWED = ("name", "why", "deliverable", "deliverables", "deadline_days")


def _f2_has_jargon(text):
    text = str(text or "")
    for w in _E3_JARGON_CAPS:
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", text):
            return True
    for w in _E3_JARGON_NAMES:
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", text, re.I):
            return True
    return False


def _f2_clean_tasks(tasks):
    cleaned, dropped_for_jargon = [], 0
    for t in (tasks if isinstance(tasks, list) else []):
        if not isinstance(t, dict):
            continue
        c = {}
        for k in _F2_ALLOWED:
            if k not in t:
                continue
            v = t[k]
            if k == "deliverables":
                if isinstance(v, list):
                    c[k] = [str(x) for x in v if isinstance(x, (str, int, float))]
            elif k == "deadline_days":
                if isinstance(v, (int, float, str)):
                    c[k] = v
            elif isinstance(v, (str, int, float)):
                c[k] = str(v)
        if not str(c.get("name", "")).strip():
            continue
        texts = [c.get("name", ""), c.get("why", ""), c.get("deliverable", "")] + c.get("deliverables", [])
        if any(_f2_has_jargon(x) for x in texts):
            dropped_for_jargon += 1
            continue
        c["frameworks"] = []
        cleaned.append(c)
    return cleaned, dropped_for_jargon
# ===== end BRICK F.2 =====


@app.post("/api/generate-tasks")
async def generate_tasks(request: Request, req: GenerateTasksRequest):
    req.member_id = require_member(request, req.member_id)
    try:
        return await _do_generate_tasks(req)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()[-800:]
        log.error("GENERATE-TASKS ERROR: " + str(e) + "\n" + tb)
        return JSONResponse({"ok": False, "error": "Task generation failed."}, status_code=502)


async def _do_generate_tasks(req: GenerateTasksRequest):
    profile = db_get_profile(req.member_id)
    if not profile:
        raise HTTPException(403, "Complete onboarding first.")
    journey = db_get_journey(req.member_id)
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    scores = db_get_scores(req.member_id)
    avg_score = round(sum(scores)/len(scores), 1) if scores else 0
    wins = db_get_wins(req.member_id)
    standups = db_get_standups(req.member_id, 3)

    wins_text = "None yet."
    if wins:
        wins_text = chr(10).join(["- " + (w.get('win_text','') or '')[:150] for w in wins[:3]])

    standups_text = "None yet."
    if standups:
        standups_text = chr(10).join(["- Score: " + str(s.get('score','?')) + " | " + (s.get('review_text','') or '')[:150] for s in standups[:3]])

    bottleneck = str(profile.get('biggest_bottleneck', 'traffic'))
    niche = str(profile.get('niche', ''))
    phase_name = str(phase_info['name'])
    rag_query = bottleneck + ' ' + niche + ' ' + phase_name + ' offer value stack content marketing funnel traffic conversion'
    framework_context = ""
    if FRAMEWORK_SEARCH_AVAILABLE:
        try:
            framework_context = search_frameworks(rag_query, top_k=3, max_chars=2000)
        except Exception as e:
            log.error("Task gen framework search error: " + str(e))

    N = chr(10)
    prompt = (
        "You are the E5 AI Coach. Generate the next 3 tasks for this user. Return JSON ONLY."
        + N + N + "USER CONTEXT:" + N
        + "Niche: " + str(profile.get('niche','N/A')) + N
        + "Avatar: " + str(profile.get('target_avatar','N/A')) + N
        + "Bottleneck: " + str(profile.get('biggest_bottleneck','N/A')) + N
        + "Day: " + str(journey.get('current_day',1)) + "/90" + N
        + "Phase: " + str(phase_info['name']) + N
        + "Avg score: " + str(avg_score) + "/10" + N
        + "Recent wins:" + N + wins_text + N
        + "Recent standups:" + N + standups_text + N + N
        + "COACH NOTES (use the ideas, never the names):" + N + (framework_context if framework_context else "None.") + N + N
        + "OUTPUT (JSON ONLY, no markdown, no code fences):" + N
        + '{"tasks": [{"name": "task name", "why": "one sentence why this task matters for THIS user", "deliverable": "specific thing they produce", "deadline_days": 7}]}'
        + N + N + "RULES: 3 tasks. Every task MUST directly address the user's bottleneck (" + bottleneck + "). Use plain everyday words. Never name a framework, method, book or author. Never write any of these words: " + ", ".join(_E3_JARGON_CAPS + _E3_JARGON_NAMES) + ". Use the ideas in COACH NOTES, never their names. If the notes do not relate to the bottleneck, ignore them. Deadline 3-14 days. Never generic."
    )

    raw = llm_result(call_llm([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=3000))

    clean = raw.strip()
    if clean.startswith("```"):
        parts = clean.split("```")
        if len(parts) > 1:
            clean = parts[1]
            if clean.startswith("json"):
                clean = clean[4:]
    clean = clean.strip()

    try:
        parsed = json.loads(clean)
        tasks = parsed.get("tasks", [])
        if not tasks:
            log.warning("BRICK F.2: generate-tasks returned no tasks. raw=" + raw[:500])
            return {"ok": False, "error": "No tasks in response"}
        tasks, dropped = _f2_clean_tasks(tasks)
        if not tasks:
            log.warning("BRICK F.2: all generated tasks dropped (jargon=" + str(dropped) + ")")
            return {"ok": False, "error": "Those tasks used coach jargon. Please try again." if dropped else "No tasks in response"}
        return {"ok": True, "tasks": tasks, "generated_for_day": journey.get('current_day',1), "phase": phase_info['name']}
    except Exception as e:
        log.warning("BRICK F.2: generate-tasks parse failed: " + str(e) + " raw=" + raw[:500])
        return {"ok": False, "error": "Parse failed: " + str(e)}


install_strict_database(globals())

# ===== BRICK G: one-time reset of test journeys that still use the old 3-phase task ids =====
# Runs only for a journey whose current task or completed list holds one of these 10 retired ids.
# The list is hardcoded on purpose (never pattern-based), so a journey is reset at most once,
# and future map changes can never trigger it. The reset is WRITTEN first and then returned,
# so the standup snapshot always matches the saved row (no 409). A failed write raises 503.
_G_RETIRED_IDS = ("p1_t3", "p1_t4", "p2_t1", "p2_t2", "p2_t3", "p2_t4", "p3_t1", "p3_t2", "p3_t3", "p3_t4")
_g_db_get_journey_strict = db_get_journey


def _g_needs_reset(journey):
    if not isinstance(journey, dict):
        return False
    if str(journey.get("current_task_id") or "") in _G_RETIRED_IDS:
        return True
    return any(str(t) in _G_RETIRED_IDS for t in (journey.get("tasks_completed") or []))


def _g_reset(journey):
    j = dict(journey)
    legacy = list(j.get("tasks_completed_legacy") or [])
    for t in (journey.get("tasks_completed") or []):
        if t not in legacy:
            legacy.append(t)
    j.update({"current_phase": "Phase 1", "current_task_id": "p1_t1", "tasks_completed": [],
              "current_day": 1, "tasks_completed_legacy": legacy,
              "brick_g_reset_at": datetime.now().isoformat()})
    return j


def db_get_journey(member_id):
    journey = _g_db_get_journey_strict(member_id)
    if _g_needs_reset(journey):
        journey = _g_reset(journey)
        db_upsert_journey(member_id, journey)
        log.info("BRICK G: journey reset to the new Phase 1 for member " + str(member_id))
    return journey
# ===== end BRICK G reset =====


# === Groq primary override (inserted) ===
_orig_call_llm = call_llm
_orig_stream_llm = stream_llm

def call_llm(messages, temperature=0.3, max_tokens=2048):
    _gk = os.environ.get("GROQ_API_KEY","").strip()
    if _gk:
        _gm = os.environ.get("GROQ_MODEL","openai/gpt-oss-120b")
        for _a in range(2):
            try:
                log.info("Calling Groq " + _gm + " attempt " + str(_a+1))
                _pl = json.dumps({"model": _gm, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode()
                _rq = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=_pl, method="POST",
                    headers={"Content-Type":"application/json","Authorization":"Bearer "+_gk,"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(_rq, timeout=90) as _rs:
                    _j = json.loads(_rs.read().decode())
                    _m = _j["choices"][0]["message"]
                    _txt = _m.get("content","") or ""
                    if not _txt.strip() and _m.get("reasoning"):
                        _txt = _m["reasoning"]
                    return _txt
            except urllib.error.HTTPError as _e:
                if _e.code in [429,502,503,504]:
                    time.sleep(2); continue
                log.error("Groq HTTP " + str(_e.code))
                break
            except Exception as _e:
                log.warning("Groq attempt " + str(_a+1) + " failed: " + str(_e))
                if _a < 1: time.sleep(2)
    return _orig_call_llm(messages, temperature, max_tokens)

async def stream_llm(messages, temperature=0.3):
    _gk = os.environ.get("GROQ_API_KEY","").strip()
    if _gk:
        _gm = os.environ.get("GROQ_MODEL","openai/gpt-oss-120b")
        try:
            _body = {"model": _gm, "messages": messages, "temperature": temperature, "max_tokens": 2048, "stream": True}
            _hd = {"Content-Type": "application/json", "Authorization": "Bearer " + _gk, "Accept": "text/event-stream", "User-Agent": "Mozilla/5.0"}
            async with httpx.AsyncClient(timeout=180.0) as _c:
                async with _c.stream("POST", "https://api.groq.com/openai/v1/chat/completions", json=_body, headers=_hd) as _r:
                    if _r.status_code != 200:
                        log.error("Groq stream HTTP " + str(_r.status_code))
                    else:
                        _reasoning_buf = []
                        _content_started = False
                        async for _line in _r.aiter_lines():
                            if not _line or not _line.startswith("data: "):
                                continue
                            _d = _line[6:].strip()
                            if _d == "[DONE]":
                                return
                            try:
                                _ck = json.loads(_d)
                                _delta = _ck.get("choices",[{}])[0].get("delta",{})
                                _t = _delta.get("content","") or ""
                                _r_tok = _delta.get("reasoning","") or ""
                                if _t:
                                    _content_started = True
                                    yield _t
                                elif _r_tok and not _content_started:
                                    _reasoning_buf.append(_r_tok)
                            except Exception:
                                continue
                        if not _content_started and _reasoning_buf:
                            yield "".join(_reasoning_buf)
                        return
        except Exception as _e:
            log.warning("Groq stream failed: " + str(_e))
    async for _tok in _orig_stream_llm(messages, temperature):
        yield _tok
# === end Groq override ===


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
