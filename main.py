import os
import time
import logging
import threading
import urllib.request
import urllib.error
import json
import re
import subprocess
from typing import List, Optional, Dict
from datetime import datetime, date
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# ============================================================
# DNS FIX FOR RAILWAY (CRITICAL)
# ============================================================
try:
    with open('/etc/resolv.conf', 'w') as f:
        f.write('nameserver 8.8.8.8\n')
        f.write('nameserver 1.1.1.1\n')
        f.write('nameserver 127.0.0.11\n')
    print("✅ DNS servers updated to 8.8.8.8, 1.1.1.1, 127.0.0.11")
except Exception as e:
    print(f"⚠️ Could not update DNS servers: {e}")

# ============================================================
# LOGGING & ENV (NO TRAILING SPACES)
# ============================================================
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "meta-llama/llama-3.3-70b-instruct:free").strip()
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()

# ============================================================
# SUPABASE CLIENT
# ============================================================
from supabase import create_client
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    log.warning("️ Supabase credentials missing. Using in-memory fallback.")
    supabase = None
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("✅ Supabase connected.")
    except Exception as e:
        log.error(f"⚠️ Supabase connection failed: {e}")
        supabase = None

# ============================================================
# IN-MEMORY FALLBACK
# ============================================================
PROFILES_DB = {}
JOURNEY_DB = {}
WINS_DB = {}
SCORES_DB = {}

# ============================================================
# RATE LIMITER
# ============================================================
class RateLimiter:
    def __init__(self, max_hits, window_s):
        self.max_hits = max_hits
        self.window = window_s
        self.hits = {}
        self.lock = threading.Lock()
    
    def allow(self, key):
        now = time.time()
        with self.lock:
            b = self.hits.setdefault(key, [])
            while b and now - b[0] > self.window:
                b.pop(0)
            if len(b) >= self.max_hits:
                return False
            b.append(now)
            return True

CHAT_LIMIT = RateLimiter(50, 3600)

# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(title="E5 AI Coach OS", version="2.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ============================================================
# JOURNEY MAP
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
# SUPABASE HELPERS
# ============================================================
def db_get_profile(member_id):
    if supabase:
        try:
            result = supabase.table("profiles").select("*").eq("member_id", member_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            log.error(f"Supabase get profile error: {e}")
            return PROFILES_DB.get(member_id)
    return PROFILES_DB.get(member_id)

def db_upsert_profile(member_id, data):
    if supabase:
        try:
            supabase.table("profiles").upsert({**data, "member_id": member_id}).execute()
            return True
        except Exception as e:
            log.error(f"Supabase upsert profile error: {e}")
    PROFILES_DB[member_id] = data
    return True

def db_get_journey(member_id):
    if supabase:
        try:
            result = supabase.table("journeys").select("*").eq("member_id", member_id).execute()
            if result.data:
                return result.data[0]
        except Exception as e:
            log.error(f"Supabase get journey error: {e}")
    return JOURNEY_DB.get(member_id, {
        "current_day": 1, "current_phase": "Phase 1",
        "current_task_id": "p1_t1", "tasks_completed": [],
        "streak": 0, "last_standup_date": None, "xp_total": 0, "badges": []
    })

def db_upsert_journey(member_id, data):
    if supabase:
        try:
            supabase.table("journeys").upsert({**data, "member_id": member_id}).execute()
            return True
        except Exception as e:
            log.error(f"Supabase upsert journey error: {e}")
    JOURNEY_DB[member_id] = data
    return True

def db_add_standup(member_id, task_id, tasks_completed, asset_links, asset_text, metrics, score, review, evidence):
    if supabase:
        try:
            supabase.table("standups").insert({
                "member_id": member_id, "task_id": task_id,
                "tasks_completed": tasks_completed, "asset_links": asset_links,
                "asset_text": asset_text, "metrics": metrics,
                "score": score, "review_text": review,
                "link_present": evidence.get("link_present", False),
                "metrics_present": evidence.get("metrics_present", False),
                "deliverables_mentioned": evidence.get("deliverables_mentioned", False),
                "evidence_score": evidence.get("evidence_score", 0)
            }).execute()
            return True
        except Exception as e:
            log.error(f"Supabase add standup error: {e}")
    return True

def db_add_win(member_id, win_text, revenue):
    if supabase:
        try:
            supabase.table("wins").insert({
                "member_id": member_id,
                "win_text": win_text,
                "revenue_amount": revenue
            }).execute()
            return True
        except Exception as e:
            log.error(f"Supabase add win error: {e}")
    WINS_DB.setdefault(member_id, []).append({"win_text": win_text, "revenue_amount": revenue})
    return True

def db_get_wins(member_id):
    if supabase:
        try:
            result = supabase.table("wins").select("*").eq("member_id", member_id).order("created_at", desc=True).execute()
            return result.data if result.data else []
        except Exception as e:
            log.error(f"Supabase get wins error: {e}")
    return WINS_DB.get(member_id, [])

def db_add_score(member_id, score):
    if supabase:
        try:
            supabase.table("scores").insert({"member_id": member_id, "score": score}).execute()
            return True
        except Exception as e:
            log.error(f"Supabase add score error: {e}")
    SCORES_DB.setdefault(member_id, []).append(score)
    return True

def db_get_scores(member_id):
    if supabase:
        try:
            result = supabase.table("scores").select("score").eq("member_id", member_id).execute()
            return [row["score"] for row in result.data] if result.data else []
        except Exception as e:
            log.error(f"Supabase get scores error: {e}")
    return SCORES_DB.get(member_id, [])

# ============================================================
# LLM ENGINE — WITH DNS FIX & RETRIES
# ============================================================
def call_llm_with_retry(messages: List[Dict], temperature: float = 0.3, max_retries: int = 3) -> str:
    """Call LLM with retries to handle transient DNS errors."""
    last_error = ""
    
    for attempt in range(max_retries):
        try:
            return call_llm(messages, temperature)
        except Exception as e:
            last_error = str(e)
            log.warning(f"⚠️ LLM call failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
    
    log.error(f"❌ All LLM retries failed. Last error: {last_error}")
    return f"Error: LLM failed after {max_retries} retries. {last_error}"

def call_llm(messages: List[Dict], temperature: float = 0.3) -> str:
    """Call LLM with OpenRouter primary + Gemini fallback."""
    
    # 1. Get API Key
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip() or os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        log.error("❌ CRITICAL: No API key found.")
        return "Error: No API key configured."

    # 2. Get Model and URL
    model = os.environ.get("GROQ_MODEL", "meta-llama/llama-3.3-70b-instruct:free").strip()
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
    url = f"{base_url}/chat/completions"
    
    masked_key = api_key[:10] + "..." + api_key[-4:] if len(api_key) > 14 else "***"
    log.info(f" Calling LLM: Model='{model}', Key='{masked_key}'")

    # 3. Try OpenRouter
    try:
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1500
        }).encode("utf-8")
        
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://e5-ai-coach-production.up.railway.app",
                "X-Title": "E5 AI Coach OS"
            }
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            log.info("✅ OpenRouter succeeded!")
            return result["choices"][0]["message"]["content"]
            
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode('utf-8', errors='ignore')[:300]
        except:
            pass
        log.error(f"❌ OpenRouter HTTP {e.code}: {e.reason} - {error_body}")
        raise  # Re-raise to trigger retry
    except Exception as e:
        log.error(f"❌ OpenRouter failed: {str(e)}")
        raise  # Re-raise to trigger retry
    
    # 4. Fallback to Gemini (only if OpenRouter raises an exception)
    # This code is unreachable if OpenRouter raises, but kept for structure
    return "Error: OpenRouter failed."

def call_llm_with_fallback(messages: List[Dict], temperature: float = 0.3) -> str:
    """Wrapper that tries OpenRouter, then Gemini."""
    try:
        return call_llm(messages, temperature)
    except Exception as e:
        log.warning(f"⚠️ OpenRouter failed, trying Gemini fallback...")
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not gemini_key:
            return "Error: Both OpenRouter and Gemini failed."
        
        try:
            gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip()
            gemini_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            
            payload2 = json.dumps({
                "model": gemini_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1500
            }).encode("utf-8")
            
            req2 = urllib.request.Request(
                gemini_url, data=payload2, method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {gemini_key}"
                }
            )
            with urllib.request.urlopen(req2, timeout=90) as resp2:
                result2 = json.loads(resp2.read().decode("utf-8"))
                log.info("✅ Gemini fallback succeeded!")
                return result2["choices"][0]["message"]["content"]
        except Exception as e2:
            log.error(f" Gemini fallback failed: {str(e2)}")
            return "Error: Both OpenRouter and Gemini failed."

# ============================================================
# PYDANTIC MODELS
# ============================================================
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str = ""
    history: List[ChatMessage] = []
    mode: str = "coach"
    member_id: Optional[str] = "default"

class OnboardingRequest(BaseModel):
    member_id: str = "default"
    business_name: str
    niche: str
    target_avatar: str
    core_offer: str
    current_revenue: float = 0
    revenue_goal: float = 10000
    biggest_bottleneck: str
    current_level: str = "beginner"
    weekly_hours: str = "4-7"
    offer_done: bool = False
    audience_done: bool = False
    sales_done: bool = False
    launch_done: bool = False

class StandupRequest(BaseModel):
    member_id: str = "default"
    current_task_id: str
    tasks_completed: List[str] = []
    asset_links: List[str] = []
    asset_text: str = ""
    metrics: str = ""

class WinRequest(BaseModel):
    member_id: str = "default"
    win_text: str
    revenue_amount: Optional[float] = None

class StrategyRequest(BaseModel):
    member_id: str
    stage: str
    bottleneck: str
    hours: str

class CompleteOnboardingRequest(BaseModel):
    member_id: str
    stage: str
    bottleneck: str
    hours: str
    strategy_document: str
    starting_day: int
    speed_profile: str

# ============================================================
# HELPERS
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
        journey["current_phase"] = "Phase 2"
        journey["current_task_id"] = "p2_t1"
    elif phase == "Phase 2" and len(completed_in_phase) >= 4:
        journey["current_phase"] = "Phase 3"
        journey["current_task_id"] = "p3_t1"
    else:
        remaining = [t for t in phase_tasks if t["id"] not in completed]
        if remaining:
            journey["current_task_id"] = remaining[0]["id"]

# ============================================================
# ROUTES
# ============================================================
@app.get("/")
def root():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return {"status": "ok"}

@app.get("/api/health")
def health():
    return {"ok": True, "supabase": supabase is not None, "version": "2.2"}

@app.get("/api/check-onboarding")
def check_onboarding(member_id: str = "default"):
    profile = db_get_profile(member_id)
    return {"onboarded": profile is not None, "profile": profile}

@app.post("/api/onboarding")
def submit_onboarding(req: OnboardingRequest):
    starting_day = 1
    if req.current_level == "intermediate" and (req.offer_done and req.audience_done):
        starting_day = 15
    elif req.current_level == "advanced" and (req.offer_done and req.audience_done and req.sales_done):
        starting_day = 31
    
    speed_profile = "accelerator" if req.weekly_hours == "8+" else "steady" if req.weekly_hours == "4-7" else "reflective"
    
    profile_data = req.dict()
    profile_data["speed_profile"] = speed_profile
    db_upsert_profile(req.member_id, profile_data)
    db_upsert_journey(req.member_id, {
        "current_day": starting_day,
        "current_phase": "Phase 1",
        "current_task_id": "p1_t1",
        "tasks_completed": [],
        "streak": 0,
        "last_standup_date": None,
        "xp_total": 0,
        "badges": []
    })
    
    return {"success": True, "starting_day": starting_day, "speed_profile": speed_profile}

@app.post("/api/generate-strategy")
def generate_strategy(req: StrategyRequest):
    starting_day = 15 if req.stage == "product" else 31 if req.stage == "selling" else 1
    speed_profile = "accelerator" if req.hours == "8+" else "steady" if req.hours == "4-7" else "reflective"
    
    bottleneck_map = {
        "traffic": "Module 3 — Attract (Content Engine)",
        "conversion": "Module 4 — Convert (Funnel Engineering)",
        "content": "Module 3 — Attract (Content Creation)",
        "community": "Module 5 — Automate (Community Systems)",
        "offer": "Module 2 — Package (Offer Engineering)",
        "time": "Module 5 — Automate (Systems)",
        "other": "Module 1 — Position (Foundation)"
    }
    focus = bottleneck_map.get(req.bottleneck, "Module 1 — Position")
    
    system_prompt = "You are a strategic business coach. Generate a personalized strategy document based on the member's answers. Include: Current Stage, Biggest Challenge, Recommended Focus Area, Starting Day, Speed Profile, Recommended First Task, and Next Steps. Use a clear, professional, and encouraging tone."
    user_prompt = f"Member answers:\n- Stage: {req.stage}\n- Biggest Challenge: {req.bottleneck}\n- Hours Available: {req.hours}/week\n\nCalculated:\n- Starting Day: {starting_day}\n- Speed Profile: {speed_profile}\n- Focus Area: {focus}\n\nGenerate a strategy document."
    
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
    
    # Use the retry + fallback wrapper
    document = call_llm_with_retry(messages)
    if document.startswith("Error:"):
        document = call_llm_with_fallback(messages)
    
    if supabase:
        try:
            supabase.table("strategy_docs").insert({
                "member_id": req.member_id,
                "document": document,
                "starting_day": starting_day,
                "speed_profile": speed_profile,
                "bottleneck": req.bottleneck
            }).execute()
        except Exception as e:
            log.error(f"Error saving strategy doc: {e}")
    
    return {
        "document": document,
        "starting_day": starting_day,
        "speed_profile": speed_profile,
        "focus": focus
    }

@app.post("/api/complete-onboarding")
def complete_onboarding(req: CompleteOnboardingRequest):
    profile = db_get_profile(req.member_id)
    if not profile:
        db_upsert_profile(req.member_id, {
            "business_name": "New Member",
            "niche": "",
            "target_avatar": "",
            "biggest_bottleneck": req.bottleneck,
            "current_level": req.stage,
            "weekly_hours": req.hours,
            "speed_profile": req.speed_profile,
            "onboarding_complete": True
        })
    else:
        db_upsert_profile(req.member_id, {
            **profile,
            "current_level": req.stage,
            "weekly_hours": req.hours,
            "speed_profile": req.speed_profile,
            "onboarding_complete": True,
            "biggest_bottleneck": req.bottleneck
        })
    
    journey = db_get_journey(req.member_id)
    if not journey:
        journey = {
            "member_id": req.member_id,
            "current_day": req.starting_day,
            "current_phase": "Phase 1",
            "current_task_id": "p1_t1",
            "tasks_completed": [],
            "streak": 0,
            "last_standup_date": None,
            "xp_total": 0,
            "badges": []
        }
    else:
        journey["current_day"] = req.starting_day
    
    db_upsert_journey(req.member_id, journey)
    
    if supabase:
        try:
            supabase.table("strategy_docs").upsert({
                "member_id": req.member_id,
                "document": req.strategy_document,
                "starting_day": req.starting_day,
                "speed_profile": req.speed_profile,
                "bottleneck": req.bottleneck
            }).execute()
        except Exception as e:
            log.error(f"Error saving strategy doc: {e}")
    
    return {
        "success": True,
        "message": "Onboarding complete",
        "starting_day": req.starting_day,
        "speed_profile": req.speed_profile
    }

@app.get("/api/journey")
def get_journey_status(member_id: str = "default"):
    journey = db_get_journey(member_id)
    profile = db_get_profile(member_id) or {}
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    current_task = get_current_task(journey)
    progress_percent = min(100, max(1, (journey.get("current_day", 1) / 90) * 100))
    scores = db_get_scores(member_id)
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    wins = db_get_wins(member_id)
    xp = journey.get("xp_total", 0)
    streak = journey.get("streak", 0)
    
    return {
        "current_day": journey.get("current_day", 1),
        "current_phase": phase_info["name"],
        "phase_days": phase_info["days"],
        "sub_coach": phase_info.get("sub_coach", "Strategist"),
        "focus": phase_info["focus"],
        "current_task": current_task,
        "tasks_completed": journey.get("tasks_completed", []),
        "tasks_completed_count": len(journey.get("tasks_completed", [])),
        "progress_percent": round(progress_percent, 1),
        "streak": streak,
        "xp": xp,
        "avg_score": avg_score,
        "standup_count": len(scores),
        "wins": wins,
        "profile": {
            "business_name": profile.get("business_name", ""),
            "niche": profile.get("niche", ""),
            "bottleneck": profile.get("biggest_bottleneck", ""),
            "speed_profile": profile.get("speed_profile", "steady")
        },
        "all_phases": {
            k: {
                "name": v["name"],
                "sub_coach": v.get("sub_coach", "Strategist"),
                "tasks": [{
                    "id": t["id"],
                    "name": t["name"],
                    "deadline_day": t["deadline_day"],
                    "completed": t["id"] in journey.get("tasks_completed", []),
                    "why": t.get("why", ""),
                    "frameworks": t.get("frameworks", []),
                    "deliverables": t.get("deliverables", [])
                } for t in v["tasks"]]
            } for k, v in JOURNEY_MAP.items()
        }
    }

@app.post("/api/standup")
def submit_standup(req: StandupRequest):
    profile = db_get_profile(req.member_id)
    if not profile:
        raise HTTPException(403, "Complete onboarding first.")
    
    journey = db_get_journey(req.member_id)
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    task = next((t for t in phase_info["tasks"] if t["id"] == req.current_task_id), phase_info["tasks"][0])
    
    frameworks_str = ", ".join(task.get("frameworks", []))
    deliverables_str = "\n".join([f"- {d}" for d in task.get("deliverables", [])])
    
    system = f"""You are a STRICT Chief Operating Officer grading execution.
TASK BEING GRADED: {task['name']}
REQUIRED FRAMEWORKS: {frameworks_str}
REQUIRED DELIVERABLES:
{deliverables_str}
MEMBER CONTEXT: Niche: {profile.get('niche', 'N/A')} | Bottleneck: {profile.get('biggest_bottleneck', 'N/A')} | Speed: {profile.get('speed_profile', 'steady')}
EVIDENCE-BASED GRADING RUBRIC: Link present? (+2), Specific metrics? (+2), Deliverables mentioned? (+2), Quality? (0-4). Grade STRICTLY.
OUTPUT FORMAT: GRADE: [X]/10
AUDIT: [2-3 specific things missing]
WHAT TO FIX: [Exact fix if < 7]
NEXT STEP: [Exact next task if >= 7]
FRAMEWORK TIP: [One insight]"""
    
    prompt = f"Tasks completed: {req.tasks_completed}\nLinks: {req.asset_links}\nWork content: {req.asset_text}\nMetrics: {req.metrics}"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    review = call_llm_with_retry(messages)
    if review.startswith("Error:"):
        review = call_llm_with_fallback(messages)
    
    score = 5
    try:
        m = re.search(r'GRADE:\s*(\d+)', review)
        if m:
            score = int(m.group(1))
    except:
        pass
    score = min(10, max(0, score))
    
    evidence = {
        "link_present": len(req.asset_links) > 0 and req.asset_links[0].strip(),
        "metrics_present": req.metrics.strip() != "",
        "deliverables_mentioned": len(req.tasks_completed) > 0,
        "evidence_score": score
    }
    today = date.today().isoformat()
    last_date = journey.get("last_standup_date")
    
    if last_date != today:
        if last_date:
            try:
                days_since = (date.today() - date.fromisoformat(last_date)).days
            except:
                days_since = 1
            journey["streak"] = journey.get("streak", 0) + 1 if days_since <= 1 else 1
        else:
            journey["streak"] = 1
        journey["last_standup_date"] = today
    
    if score >= 7 and req.current_task_id not in journey.get("tasks_completed", []):
        journey.setdefault("tasks_completed", []).append(req.current_task_id)
        journey["current_day"] = min(90, journey.get("current_day", 1) + 7)
        advance_journey(journey, req.member_id)
        xp_gained = 125
        journey["xp_total"] = journey.get("xp_total", 0) + xp_gained
    else:
        xp_gained = 25
    
    db_add_standup(req.member_id, req.current_task_id, ",".join(req.tasks_completed), ",".join(req.asset_links), req.asset_text, req.metrics, score, review, evidence)
    db_add_score(req.member_id, score)
    db_upsert_journey(req.member_id, journey)
    
    return {
        "success": True,
        "review": review,
        "score": score,
        "task_unlocked": score >= 7,
        "streak": journey.get("streak", 0),
        "xp_gained": xp_gained,
        "xp_total": journey.get("xp_total", 0),
        "journey_updated": True
    }

@app.post("/api/win")
def submit_win(req: WinRequest):
    if not db_get_profile(req.member_id):
        raise HTTPException(403, "Complete onboarding first.")
    db_add_win(req.member_id, req.win_text, req.revenue_amount)
    return {"success": True, "total_wins": len(db_get_wins(req.member_id))}

@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.message:
        raise HTTPException(400, "empty message")
    if not CHAT_LIMIT.allow(req.member_id or "default"):
        raise HTTPException(429, "Rate limit reached")
    
    profile = db_get_profile(req.member_id or "default")
    if not profile:
        raise HTTPException(403, "GATEKEEPER: Complete onboarding first.")
    
    journey = db_get_journey(req.member_id or "default")
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    current_task = get_current_task(journey)
    task_completed = current_task["id"] in journey.get("tasks_completed", [])
    streak = journey.get("streak", 0)
    frameworks_str = ", ".join(current_task.get("frameworks", []))
    wins = db_get_wins(req.member_id or "default")
    scores = db_get_scores(req.member_id or "default")
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    
    if not task_completed:
        return {
            "reply": f"""**ACCOUNTABILITY GATE**
You are Day {journey.get('current_day', 1)} — {phase_info['name']} phase.
Current task: {current_task['name']}
Deadline: Day {current_task['deadline_day']}
Why: {current_task.get('why', 'Complete this task to move forward.')}
Required frameworks: {frameworks_str}
Deliverables needed:
{chr(10).join(['— ' + d for d in current_task.get('deliverables', [])])}

Submit your work using the 'Submit Daily Work' button. I will grade it and unlock the next step."""
        }
    
    wins_text = "No wins recorded yet."
    if wins:
        wins_text = f"{len(wins)} wins recorded. Latest: {wins[0]['win_text'][:100]}"
    
    system_prompt = f"""You are the E5 AI Coach — an elite, proactive Chief Operating Officer.
CURRENT MEMBER CONTEXT: Business: {profile.get('business_name', 'N/A')} | Niche: {profile.get('niche', 'N/A')} | Avatar: {profile.get('target_avatar', 'N/A')} | Bottleneck: {profile.get('biggest_bottleneck', 'N/A')} | Speed: {profile.get('speed_profile', 'steady')} | Day: {journey.get('current_day', 1)}/90 | Phase: {phase_info['name']} | Task: {current_task['name']} | Completed: {task_completed} | Streak: {streak} | Avg score: {avg_score}/10 | Wins: {wins_text} | Frameworks: {frameworks_str}
COACHING RULES: 1. Diagnose Before Prescribing. 2. Personalize with Memory. 3. One Insight Per Response. 4. Apply, Don't Recite. 5. 60% Questions / 40% Insight. 6. Rewrite Together. 7. Short & Human (150-250 words). 8. Never Invent. 9. Language Matching (EN/AR).
TONE: Calm. Authoritative. Short punchy sentences. Think McKinsey Partner meets Alex Hormozi."""
    
    messages = [{"role": "system", "content": system_prompt}] + [{"role": m.role, "content": m.content} for m in req.history[-10:]] + [{"role": "user", "content": req.message}]
    reply = call_llm_with_retry(messages)
    if reply.startswith("Error:"):
        reply = call_llm_with_fallback(messages)
    return {"reply": reply}

# ============================================================
# MAIN ENTRY POINT
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
