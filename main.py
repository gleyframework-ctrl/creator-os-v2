"""
E5 AI COACH - main.py (PHASE 1: OMNI-FRAMEWORK INJECTION SYSTEM)
Dynamic Framework Router + Gatekeeper + Daily Standup
"""
import json
import os
import re
import time
import logging
import threading
import urllib.request
import urllib.error
import urllib.parse
from typing import List, Optional, Dict, Any
from datetime import datetime

# FastAPI & Pydantic imports
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

# --- ENV VARS ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FISH_API_KEY = os.environ.get("FISH_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WHOP_API_KEY = os.environ.get("WHOP_API_KEY", "")
WHOP_INSIDER_PRODUCT_ID = os.environ.get("WHOP_INSIDER_PRODUCT_ID", "")
WHOP_PARTNER_PRODUCT_ID = os.environ.get("WHOP_PARTNER_PRODUCT_ID", "")

# --- RATE LIMITERS ---
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
            while b and now - b[0] > self.window: b.pop(0)
            if len(b) >= self.max_hits: return False
            b.append(now)
            return True
    def remaining(self, key):
        now = time.time()
        with self.lock:
            b = self.hits.get(key, [])
            while b and now - b[0] > self.window: b.pop(0)
            return max(0, self.max_hits - len(b))

CHAT_LIMIT = RateLimiter(int(os.environ.get("RATE_CHAT_PER_HOUR", "30")), 3600)
TTS_LIMIT = RateLimiter(int(os.environ.get("RATE_TTS_PER_HOUR", "10")), 3600)

# --- MODE TIERS ---
MODE_TIERS = {
    "coach": "free", "xray": "free", "funnel": "free", "quiz": "free",
    "community": "insider", "dm": "insider", "content": "insider",
    "alchemy": "insider", "hack": "insider",
    "offer": "partner", "workshop": "partner", "launch": "partner", "sales": "partner", "email": "insider"
}
TIER_RANK = {"free": 0, "insider": 1, "partner": 2}

# --- LLM PROVIDERS ---
PROVIDERS = [
    {"name": "gemini", "chat_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "key": GEMINI_API_KEY, "models": ["gemini-2.0-flash", "gemini-1.5-flash"]},
    {"name": "groq", "chat_url": "https://api.groq.com/openai/v1/chat/completions", "key": GROQ_API_KEY, "models": ["llama-3.1-70b-versatile", "llama3-70b-8192"]},
]

# --- FASTAPI APP ---
app = FastAPI(title="E5 AI Coach", version="Phase-1-Omni")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ==============================================================================
# 🧠 PHASE 1: OMNI-FRAMEWORK INJECTION SYSTEM
# ==============================================================================

# 1. THE CORE PHILOSOPHY (Always Active)
CCC_BRAIN = """
You are the E5 AI Coach, an elite, proactive Chief Operating Officer operating at the Googoltradrekachiliaplex level.
YOUR PRIME DIRECTIVES:
1. DIAGNOSE BEFORE PRESCRIBING: Never give generic advice. Anchor every response to the user's specific niche, avatar, and bottleneck.
2. SPICY SPECIFICITY: Use real-world examples, exact numbers, and actionable steps. Never be vague.
3. NO AI FLUFF: Banned words: delve, tapestry, unleash, unlock, game-changing, robust, seamless, synergy. Use short, punchy sentences.
4. STRICT ACCOUNTABILITY: If the user hasn't submitted their Daily Standup, remind them. Review their submitted work before giving new tasks.
"""

# 2. MODE-SPECIFIC LENSES
MODE_PROMPTS = {
    "coach": "LENS: DAILY OPERATOR. Focus on rhythm, Rule of 100, and daily task completion.",
    "quiz": "LENS: ASK METHOD QUIZ ARCHITECT. Force user to define Cure vs Band-Aid. Generate Type/Killer/Score hooks and Buckets.",
    "dm": "LENS: DM DOCTOR. Use S.I.P.E. framework. Classify lead temperature. Guide through 3-Stage Conversation.",
    "offer": "LENS: OFFER ARCHITECT. Stack value using Value Equation. Build Grand Slam Offers.",
    "xray": "LENS: BUSINESS X-RAY. Map user's CVJ stage. Find earliest broken layer. Score RED/YELLOW/GREEN.",
    "content": "LENS: CONTENT ENGINE. Use 4 Hook Components. Apply Performance Drivers.",
    "sales": "LENS: HIGH-TICKET CLOSER. Use 9-Step Script and GEM Theory. Handle objections with Socratic Six.",
    "email": "LENS: EMAIL STORYSELLER. Use S.L.P.C. framework. Map beliefs. Write casual CTAs.",
    "funnel": "LENS: FUNNEL MAP. Apply Ready Now Funnel. Segment Now vs Later people.",
    "launch": "LENS: LAUNCH PLANNER. 21-day map. Pre-promo -> Promo -> Drop -> Push.",
    "alchemy": "LENS: ALCHEMY (VIDEO). Hook 0-5s, Body 5-45s, CTA 45-60s.",
    "hack": "LENS: FUNNEL HACKER. Reverse-engineer competitor funnel.",
    "community": "LENS: COMMUNITY OS. Build culture, rituals, belonging > value.",
    "workshop": "LENS: WORKSHOP ARCHITECT. Design 6-day belief arc."
}

# 3. THE OMNI-FRAMEWORK KNOWLEDGE BASE (Injected Dynamically)
FRAMEWORK_RULES = {
    "quiz": """
    [ASK METHOD FRAMEWORK]
    - Band-Aid vs Cure: The quiz delivers the Band-Aid (free insight). The paid offer is the Cure. Break down the old belief, build the new belief.
    - 3 Frameworks: TYPE (Categorize), KILLER (Identify mistakes/blockers), SCORE (Rate/Benchmark).
    - Buckets: Segment users into 3-5 distinct psychological buckets.
    - Bridge: 5-12 micro-commitment questions. Start with 'Grease the Wheels', end with 'Lead Capture'.
    """,
    "sales": """
    [DAN LOK & CHRIS DO FRAMEWORKS]
    - 9-Step Script: Rapport -> Pre-Frame -> Motivation -> Pains -> Dream -> Bridge Gap -> Money Stage -> Close -> Next Steps.
    - Socratic Six Objections: Raging Bull (Empathy), Hall of Mirrors (Reflect), Double Down (Challenge), The Chief (How?), Yin-Yang (Reframe), Simon Sinek (Why?).
    - GEM Theory: Emerald (Facts), Ruby (Challenges), Sapphire (Fun), Pearl (Authenticity). Adapt to their personality.
    """,
    "email": """
    [JIM HAMILTON STORYSELLING FRAMEWORK]
    - S.L.P.C. Formula: Story (Capture attention) -> Lesson (Extract truth) -> Pivot (Connect to goal) -> CTA (Next step).
    - 4 Core Stories: Origin, Vehicle, Internal Belief, External Belief.
    - Belief Mapping: Identify Internal False Beliefs ("I'm not technical") and External False Beliefs ("Market is saturated"). Uninstall them with Epiphany Bridges.
    - Casual CTAs: Never hard-sell. Use friendly, low-friction invites.
    """,
    "dm": """
    [MIGUEL ALVAREZ & JASON FOX FRAMEWORKS]
    - S.I.P.E. Framework: Short, Incomplete (open loop), Personal, Emotional.
    - 3-Stage Conversation: Cold (Build rapport) -> Warm (Uncover Level 2 Pain) -> Hot (Invite to call).
    - Ladder of Yeses: Reply -> Accept Value -> Agree to Learn -> Agree to Call -> Pay.
    - Market Assumptions: Don't wait for them to reveal pain. Lead with assumptions based on industry struggles.
    """,
    "offer": """
    [ROB LENNON & TODD BROWN FRAMEWORKS]
    - Dream Offer: Dream Outcome + Dream Vehicle + Dream Journey + Dream Price.
    - S.I.N. Protocol: Superior, Irresistible, No-Brainer.
    - Value Equation: (Dream Outcome × Likelihood) / (Time Delay × Effort). Increase numerator, decrease denominator.
    - 3 Levels of Benefits: Functional -> Dimensionalized -> Emotional.
    """,
    "content": """
    [KALLAWAY & MINDVALLEY FRAMEWORKS]
    - 4 Hook Components: Text, Visual, Spoken, Audio. MAX ALIGNMENT is required.
    - On-Target Curiosity Loop: Clarity (what it's about) + Contrast (reality vs expectation).
    - Performance Drivers: Perspective Shift, Tension, Viewer Connection, Promise of Value.
    """,
    "funnel": """
    [RYAN DEISS READY NOW FUNNEL & CVJ]
    - Flip the Funnel: Don't march everyone up slowly. Identify 'Now People' (10X clients) and send them straight to the high-ticket offer.
    - Qualifying Question: Ask one question to segment Now vs Later people (e.g., Budget, Authority, Need, Timing).
    - Customer Value Journey: Aware -> Engage -> Subscribe -> Convert -> Excite -> Ascend -> Advocate -> Promote.
    """,
    "launch": """
    [JESSICA TUTTON & TODD BROWN FRAMEWORKS]
    - 5-Day Warm Launch: Announce -> Educate -> Story/Proof -> Objections -> Open Cart.
    - Bullet Campaign: 3-day Interest Sequence (Clicks) -> 3-day Offer Sequence (Conversions) -> Dynamic Deadline.
    """,
    "alchemy": """
    [PRINCE EA & KALLAWAY FRAMEWORKS]
    - Hero's Journey: Ordinary World -> Call -> Refusal -> Mentor -> Threshold -> Challenge -> Climax -> Transformation.
    - Viral Elements: Social Currency, Relatability, Rallying Cry, 5-Second Rule.
    """,
    "hack": """
    [TTB & DIGITALMARKETER FRAMEWORKS]
    - Funnel Hacking: Reverse-engineer competitor ads, landing pages, and email sequences.
    - 15-Point Landing Page Audit: Market Callout, 5-Second Test, CTA Above Fold, Social Proof, Source Congruency.
    """,
    "community": """
    [DAN HARRISON AVOCADO FRAMEWORK]
    - 5 Horsemen of Retention: Track attendance, Reach out 2x/week, Handwritten cards, Member events, Exit interviews.
    - Community OS: Build culture and rituals. Belonging > Value.
    """,
    "workshop": """
    [RYAN LEVESQUE WORKSHOP FRAMEWORK]
    - 6-Day Belief Arc: Install 4 core beliefs (Opportunity is real, Vehicle is right, They are capable, Now is the time).
    """,
    "coach": "", # Uses base brain only
    "xray": ""  # Uses base brain only
}

# ==============================================================================
# 📊 PYDANTIC MODELS
# ==============================================================================
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str = ""
    prompt: str = ""
    user_message: str = ""
    history: List[ChatMessage] = []
    mode: str = "coach"
    member_context: Optional[str] = None
    member_id: Optional[str] = "default"

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    member_id: Optional[str] = "default"

class UnlockRequest(BaseModel):
    member_id: str = "default"
    license_key: str = ""

class OnboardingRequest(BaseModel):
    member_id: str = "default"
    business_name: str
    niche: str
    target_avatar: str
    core_offer: str
    current_revenue: float
    revenue_goal: float
    biggest_bottleneck: str

class StandupRequest(BaseModel):
    member_id: str = "default"
    tasks_completed: List[str] = []
    asset_links: List[str] = []
    asset_text: str = ""
    metrics: str = ""

# ==============================================================================
# 💾 SUPABASE HELPERS (Simplified for Stability)
# ==============================================================================
MEMORY_STORE = {}

def load_memory(member_id: str) -> tuple[str, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return MEMORY_STORE.get(f"profile_{member_id}", ""), "free"
    try:
        url = (SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory?member_id=eq." + urllib.parse.quote(member_id) + "&select=profile,tier")
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY})
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
            if rows: return rows[0].get("profile") or "", rows[0].get("tier") or "free"
    except Exception as e: log.error("MEMORY LOAD FAIL: %s", e)
    return MEMORY_STORE.get(f"profile_{member_id}", ""), "free"

def save_memory(member_id: str, profile_text: str):
    MEMORY_STORE[f"profile_{member_id}"] = profile_text
    if not SUPABASE_URL or not SUPABASE_KEY or not profile_text: return
    try:
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory"
        body = json.dumps([{"member_id": member_id, "profile": profile_text}]).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e: log.error("MEMORY SAVE FAIL: %s", e)

def get_profile(member_id: str) -> Optional[Dict]:
    mem, _ = load_memory(member_id)
    if mem:
        try: return json.loads(mem)
        except: return None
    return None

def save_profile(member_id: str, data: Dict):
    save_memory(member_id, json.dumps(data))

# ==============================================================================
# 🤖 LLM ENGINE
# ==============================================================================
def try_model(provider, model, messages, temperature, max_tokens):
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode("utf-8")
    req = urllib.request.Request(provider["chat_url"], data=body, method="POST", headers={"Content-Type": "application/json", "Authorization": "Bearer " + provider["key"]})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or ""
    except Exception as e:
        log.error("LLM FAIL %s/%s: %s", provider["name"], model, e)
        return None

def call_llm(messages, temperature=0.5, max_tokens=1500):
    for p in PROVIDERS:
        if not p["key"]: continue
        for model in p["models"]:
            out = try_model(p, model, messages, temperature, max_tokens)
            if out: return out
    raise Exception("All LLM providers failed")

# ==============================================================================
# 🧠 DYNAMIC SYSTEM BUILDER (PHASE 1 CORE)
# ==============================================================================
def build_system(mode: str, member_id: str, member_context: str = "") -> str:
    # 1. Base Brain
    system = CCC_BRAIN
    
    # 2. Mode Lens
    m = mode if mode in MODE_PROMPTS else "coach"
    system += "\n\n" + MODE_PROMPTS[m]
    
    # 3. OMNI-FRAMEWORK INJECTION (Phase 1)
    if mode in FRAMEWORK_RULES and FRAMEWORK_RULES[mode]:
        system += "\n\n" + FRAMEWORK_RULES[mode]
    
    # 4. User Context
    profile = get_profile(member_id)
    if profile:
        system += f"\n\nUSER BUSINESS CONTEXT:\n- Niche: {profile.get('niche', 'N/A')}\n- Avatar: {profile.get('target_avatar', 'N/A')}\n- Offer: {profile.get('core_offer', 'N/A')}\n- Bottleneck: {profile.get('biggest_bottleneck', 'N/A')}\n- Revenue: ${profile.get('current_revenue', 0)} / ${profile.get('revenue_goal', 10000)}"
        
    if member_context:
        system += f"\n\nMEMBER CONTEXT:\n{member_context}"
        
    return system

# ==============================================================================
# 🛣️ ROUTES
# ==============================================================================
@app.get("/")
def root():
    if os.path.exists("chat_test.html"): return FileResponse("chat_test.html")
    return {"status": "ok", "app": "E5 AI Coach Phase 1"}

@app.get("/api/check-onboarding")
def check_onboarding(member_id: str = "default"):
    profile = get_profile(member_id)
    return {"onboarded": profile is not None, "profile": profile}

@app.post("/api/onboarding")
def submit_onboarding(req: OnboardingRequest):
    save_profile(req.member_id, req.dict())
    return {"success": True}

@app.post("/api/standup")
def submit_standup(req: StandupRequest):
    profile = get_profile(req.member_id)
    if not profile: raise HTTPException(403, "Complete onboarding first.")
    
    system = build_system("coach", req.member_id)
    prompt = f"""User submitted Daily Standup:
    Tasks: {req.tasks_completed}
    Links: {req.asset_links}
    Work Text: {req.asset_text}
    Metrics: {req.metrics}
    
    Act as a strict COO. Review their work. Grade it out of 10. Tell them exactly what they did wrong or right based on their niche and bottleneck. Give them ONE specific task to do next."""
    
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    review = call_llm(messages)
    return {"success": True, "review": review}

@app.post("/api/chat")
def chat(req: ChatRequest):
    text = req.message or req.prompt or req.user_message
    if not text: raise HTTPException(400, "empty message")
    
    member_id = (req.member_id or "default").strip()
    if not CHAT_LIMIT.allow(member_id): raise HTTPException(429, "Rate limit reached")
    
    profile = get_profile(member_id)
    if not profile: raise HTTPException(403, "GATEKEEPER: Please complete the onboarding quiz first.")
    
    _, tier = load_memory(member_id)
    need = MODE_TIERS.get(req.mode, "free")
    if TIER_RANK.get(tier or "free", 0) < TIER_RANK.get(need, 0): raise HTTPException(403, f"locked: {need}")
    
    system = build_system(req.mode, member_id, req.member_context)
    
    messages = [{"role": "system", "content": system}]
    for m in req.history[-10:]: messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": text})
    
    try:
        reply = call_llm(messages)
        return {"reply": reply}
    except Exception as e:
        log.error("CHAT 500: %s", e)
        raise HTTPException(500, f"LLM error: {str(e)}")

@app.post("/api/tts")
def tts(req: TTSRequest):
    limit_key = (req.member_id or "anon").strip()
    if not TTS_LIMIT.allow(limit_key): raise HTTPException(429, "Voice limit reached")
    if not FISH_API_KEY: raise HTTPException(503, "FISH_API_KEY missing")
    # TTS logic would go here (omitted for brevity to focus on Phase 1 Brain)
    return {"status": "TTS placeholder"}

@app.get("/test")
def test_page():
    if os.path.exists("chat_test.html"): return FileResponse("chat_test.html")
    return HTMLResponse("<h3>chat_test.html not found</h3>")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
