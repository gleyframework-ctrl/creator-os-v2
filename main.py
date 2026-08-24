"""
E5 AI COACH - main.py (GATEKEEPER & DEEP CONTEXT EDITION)
Advanced backend with mandatory onboarding and state-aware AI.
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
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

try:
    from vault import SCRIPT_VAULT
except Exception:
    SCRIPT_VAULT = ""

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FISH_API_KEY = os.environ.get("FISH_API_KEY", "") or os.environ.get("FISH_AUDIO_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WHOP_API_KEY = os.environ.get("WHOP_API_KEY", "")
WHOP_INSIDER_PRODUCT_ID = os.environ.get("WHOP_INSIDER_PRODUCT_ID", "")
WHOP_PARTNER_PRODUCT_ID = os.environ.get("WHOP_PARTNER_PRODUCT_ID", "")
MANUAL_INSIDER_CODES = [c.strip() for c in os.environ.get("MANUAL_INSIDER_CODES", "").split(",") if c.strip()]
MANUAL_PARTNER_CODES = [c.strip() for c in os.environ.get("MANUAL_PARTNER_CODES", "").split(",") if c.strip()]

_DEFAULT_ORIGINS = "https://e5-ai-coach-production.up.railway.app,http://localhost:8000,http://127.0.0.1:8000"
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]

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

CHAT_LIMIT = RateLimiter(int(os.environ.get("RATE_CHAT_PER_HOUR", "30")), 3600)
TTS_LIMIT = RateLimiter(int(os.environ.get("RATE_TTS_PER_HOUR", "10")), 3600)
UNLOCK_LIMIT = RateLimiter(int(os.environ.get("RATE_UNLOCK_PER_HOUR", "10")), 3600)

MODE_TIERS = {
    "coach": "free", "xray": "free", "funnel": "free",
    "community": "insider", "dm": "insider", "content": "insider", "alchemy": "insider", "hack": "insider",
    "offer": "partner", "workshop": "partner", "launch": "partner",
}
TIER_RANK = {"free": 0, "insider": 1, "partner": 2}

PROVIDERS = [
    {"name": "gemini", "chat_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "key": GEMINI_API_KEY, "models": ["gemini-2.0-flash", "gemini-1.5-flash"]},
    {"name": "groq", "chat_url": "https://api.groq.com/openai/v1/chat/completions", "key": GROQ_API_KEY, "models": ["llama-3.1-70b-versatile", "llama3-70b-8192"]},
]

app = FastAPI(title="E5 AI Coach", version="Gatekeeper-X")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])

# ==============================================================================
# 🧠 THE MASTER BRAIN (Context-Aware)
# ==============================================================================
CCC_BRAIN = """
You are the E5 AI Coach, an elite, proactive Chief Operating Officer. You fuse TTB, AVOCADO, and Alex Hormozi's $100M frameworks.
PRIME DIRECTIVES:
1. NEVER give generic advice. Anchor every response to the user's specific niche, avatar, offer, and bottleneck.
2. DIAGNOSE BEFORE PRESCRIBING. 
3. FIX THE EARLIEST LEAK FIRST.
4. SPICY SPECIFICITY. No fluff.
TONE: Calm, deeply insightful, slightly detached. Short punchy sentences for actions.
BLACKLIST: delve, tapestry, unleash, unlock, game-changing, robust, seamless, synergy, ecosystem, navigate, journey, elevate.
Do NOT use em dashes.
"""

MODE_PROMPTS = {
    "coach": "LENS: DAILY OPERATOR. Focus on rhythm, energy, inbox priority, Rule of 100.",
    "xray": "LENS: BUSINESS X-RAY. Find earliest broken layer in Straight Line.",
    "funnel": "LENS: FUNNEL MAP. Visualize the customer journey.",
    "community": "LENS: COMMUNITY OS. Build culture, linear paths.",
    "dm": "LENS: DM DOCTOR. Classify signal. Use ECAFI & SOULFUL scripts.",
    "offer": "LENS: OFFER ARCHITECT. Stack value, de-risk, anchor price.",
    "workshop": "LENS: WORKSHOP ARCHITECT. Design 6-day belief arc.",
    "content": "LENS: CONTENT ENGINE. Spicy specificity, polarize.",
    "launch": "LENS: LAUNCH PLANNER. 21-day map.",
    "alchemy": "LENS: ALCHEMY (VIDEO). Hook 0-5s, Body 5-45s, CTA 45-60s.",
    "hack": "LENS: FUNNEL HACKER. Reverse-engineer competitor funnel.",
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
    current_monthly_revenue: float
    revenue_goal: float
    biggest_bottleneck: str
    business_stage: str

# ==============================================================================
# 💾 SUPABASE HELPERS (Memory, Tier, Onboarding)
# ==============================================================================
MEMORY_RE = re.compile(r"[{1,2}\sMEMORY\s]{1,2}(.*?)(?:[{1,2}\s/\sMEMORY\s]{1,2}|$)", re.S)

def load_memory(member_id):
    if not SUPABASE_URL or not SUPABASE_KEY: return "", "free"
    try:
        url = (SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory?member_id=eq." + urllib.parse.quote(member_id) + "&select=profile,tier")
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY})
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
            if rows: return (rows[0].get("profile") or "", rows[0].get("tier") or "free")
    except Exception as e: log.error("MEMORY LOAD FAIL: %s", e)
    return "", "free"

def save_memory(member_id, profile_text):
    if not SUPABASE_URL or not SUPABASE_KEY or not profile_text: return
    try:
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory"
        body = json.dumps([{"member_id": member_id, "profile": profile_text}]).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e: log.error("MEMORY SAVE FAIL: %s", e)

def set_tier(member_id, tier):
    if not SUPABASE_URL or not SUPABASE_KEY: return
    try:
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory"
        body = json.dumps([{"member_id": member_id, "tier": tier}]).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e: log.error("TIER SAVE FAIL: %s", e)

def extract_memory(reply):
    m = MEMORY_RE.search(reply)
    if m: return MEMORY_RE.sub("", reply).strip(), m.group(1).strip()
    return reply, ""

# --- ONBOARDING GATEKEEPER LOGIC ---
def get_business_profile(member_id: str) -> Optional[Dict]:
    if not SUPABASE_URL or not SUPABASE_KEY: return None
    try:
        url = (SUPABASE_URL.rstrip("/") + "/rest/v1/business_profiles?member_id=eq." + urllib.parse.quote(member_id) + "&select=*")
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY})
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
            return rows[0] if rows else None
    except Exception as e:
        log.error("PROFILE LOAD FAIL: %s", e)
        return None

def save_business_profile(req: OnboardingRequest):
    if not SUPABASE_URL or not SUPABASE_KEY: return
    try:
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/business_profiles"
        body = json.dumps([req.dict()]).encode("utf-8")
        req_obj = urllib.request.Request(url, data=body, method="POST", headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req_obj, timeout=10).read()
    except Exception as e: log.error("PROFILE SAVE FAIL: %s", e)

def whop_tier_for_license(key):
    if key in MANUAL_PARTNER_CODES: return "partner"
    if key in MANUAL_INSIDER_CODES: return "insider"
    if not WHOP_API_KEY: return None
    try:
        url = "https://api.whop.com/api/v2/licenses/" + urllib.parse.quote(key)
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + WHOP_API_KEY, "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            status = str(data.get("status") or data.get("state") or "active").lower()
            if status in ("revoked", "cancelled", "canceled", "expired", "inactive"): return None
            pid = (data.get("product_id") or data.get("experience_id") or (data.get("product") or {}).get("id") or (data.get("experience") or {}).get("id") or "")
            if pid and WHOP_PARTNER_PRODUCT_ID and pid == WHOP_PARTNER_PRODUCT_ID: return "partner"
            if pid and WHOP_INSIDER_PRODUCT_ID and pid == WHOP_INSIDER_PRODUCT_ID: return "insider"
            if not WHOP_INSIDER_PRODUCT_ID and not WHOP_PARTNER_PRODUCT_ID: return "insider"
    except Exception as e: log.error("WHOP CHECK FAIL: %s", e)
    return None

# ==============================================================================
# 🤖 LLM ENGINE
# ==============================================================================
def try_model(p, model, messages, temperature, max_tokens):
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode("utf-8")
    req = urllib.request.Request(p["chat_url"], data=body, method="POST", headers={"Content-Type": "application/json", "Authorization": "Bearer " + p["key"], "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or ""
    except Exception as e:
        log.error("LLM FAIL %s/%s: %s", p["name"], model, e)
        return None

def call_llm(messages, temperature=0.5, max_tokens=1500):
    for p in PROVIDERS:
        if not p["key"]: continue
        for model in p["models"]:
            if not model: continue
            out = try_model(p, model, messages, temperature, max_tokens)
            if out: return out
    raise Exception("All LLM providers failed")

def build_system(mode, member_id, member_context, memory=""):
    m = mode if mode in MODE_PROMPTS else "coach"
    system = CCC_BRAIN + "\n" + MODE_PROMPTS[m]
    if SCRIPT_VAULT: system += "\n" + SCRIPT_VAULT
    
    # INJECT DEEP BUSINESS CONTEXT
    profile = get_business_profile(member_id)
    if profile:
        system += f"""
\n\nCRITICAL USER BUSINESS CONTEXT (Use this to personalize EVERY response):
- Business Name: {profile.get('business_name', 'N/A')}
- Niche: {profile.get('niche', 'N/A')}
- Target Avatar: {profile.get('target_avatar', 'N/A')}
- Core Offer: {profile.get('core_offer', 'N/A')}
- Current Revenue: ${profile.get('current_monthly_revenue', 0)}/mo
- Revenue Goal: ${profile.get('revenue_goal', 10000)}/mo
- Biggest Bottleneck: {profile.get('biggest_bottleneck', 'N/A')}
- Business Stage: {profile.get('business_stage', 'N/A')}
"""
    if memory: system += "\nWHAT YOU KNOW ABOUT THIS MEMBER:\n" + memory
    if member_context: system += "\nMEMBER CONTEXT:\n" + member_context
    return system

def post_process(text): return text.replace("—", "-").replace("–", "-").strip()

# ==============================================================================
# 🛣️ ROUTES
# ==============================================================================
@app.get("/")
def root():
    if os.path.exists("chat_test.html"): return FileResponse("chat_test.html")
    return {"status": "ok", "app": "E5 AI Coach"}

@app.get("/api/health")
def health():
    return {"ok": True, "gemini": bool(GEMINI_API_KEY), "groq": bool(GROQ_API_KEY), "supabase": bool(SUPABASE_URL)}

@app.get("/api/modes")
def modes(): return {"modes": list(MODE_PROMPTS.keys()), "tiers": MODE_TIERS}

@app.get("/api/tier")
def tier_endpoint(member_id: str = "default"):
    _, tier = load_memory(member_id)
    return {"tier": tier or "free"}

@app.get("/api/check-onboarding")
def check_onboarding(member_id: str = "default"):
    profile = get_business_profile(member_id)
    return {"onboarded": profile is not None, "profile": profile}

@app.post("/api/onboarding")
def submit_onboarding(req: OnboardingRequest):
    save_business_profile(req)
    # Initialize memory with their context
    save_memory(req.member_id, f"User completed onboarding. Business: {req.business_name}, Niche: {req.niche}, Bottleneck: {req.biggest_bottleneck}")
    return {"success": True}

@app.post("/api/unlock")
def unlock(req: UnlockRequest):
    member_id = (req.member_id or "default").strip()
    if not UNLOCK_LIMIT.allow(member_id): raise HTTPException(429, "Too many unlock attempts")
    key = (req.license_key or "").strip()
    if not key: raise HTTPException(400, "empty license key")
    try: tier = whop_tier_for_license(key)
    except Exception as e: raise HTTPException(502, f"Whop check failed: {e}")
    if not tier: raise HTTPException(403, "Invalid license")
    set_tier(member_id, tier)
    return {"tier": tier}

@app.post("/api/chat")
def chat(req: ChatRequest):
    text = req.message or req.prompt or req.user_message
    if not text: raise HTTPException(400, "empty message")
    
    member_id = (req.member_id or "default").strip()
    
    # GATEKEEPER: Force onboarding before chatting
    profile = get_business_profile(member_id)
    if not profile:
        raise HTTPException(403, "GATEKEEPER: Please complete the onboarding quiz to unlock the AI Coach.")
        
    if not CHAT_LIMIT.allow(member_id): raise HTTPException(429, "Rate limit reached")
    
    memory, tier = load_memory(member_id)
    need = MODE_TIERS.get(req.mode, "free")
    if TIER_RANK.get(tier or "free", 0) < TIER_RANK.get(need, 0): raise HTTPException(403, f"locked: {need}")
    
    messages = [{"role": "system", "content": build_system(req.mode, member_id, "", memory)}]
    for m in req.history[-16:]: messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": text})
    
    try:
        clean = post_process(call_llm(messages))
        clean, mem_update = extract_memory(clean)
        if mem_update: save_memory(member_id, mem_update)
        return {"reply": clean, "response": clean, "message": clean, "mode": req.mode}
    except Exception as e:
        log.error("CHAT 500: %s", e)
        raise HTTPException(500, f"LLM error: {str(e)}")

@app.post("/chat")
def chat_alias(req: ChatRequest): return chat(req)

@app.post("/api/tts")
def tts(req: TTSRequest):
    limit_key = (req.member_id or "anon").strip()
    if not TTS_LIMIT.allow(limit_key): raise HTTPException(429, "Voice limit reached")
    if not FISH_API_KEY: raise HTTPException(503, "FISH_API_KEY missing")
    voice = req.voice_id or FISH_VOICE_ID
    def call(payload):
        req_obj = urllib.request.Request("https://api.fish.audio/v1/tts", data=json.dumps(payload).encode("utf-8"), method="POST", headers={"Content-Type": "application/json", "Authorization": "Bearer " + FISH_API_KEY, "User-Agent": UA})
        with urllib.request.urlopen(req_obj, timeout=60) as resp: return resp.read()
    payload = {"text": req.text, "format": "mp3"}
    if voice: payload["reference_id"] = voice
    try: return Response(content=call(payload), media_type="audio/mpeg")
    except Exception as e:
        log.error("TTS FAIL: %s", e)
        raise HTTPException(502, f"TTS error: {str(e)}")

@app.post("/api/voice")
def voice_alias(req: TTSRequest): return tts(req)

@app.get("/test")
def test_page():
    if os.path.exists("chat_test.html"): return FileResponse("chat_test.html")
    return HTMLResponse("<h3>chat_test.html not found</h3>")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
