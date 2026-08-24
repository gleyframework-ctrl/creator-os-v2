"""
E5 AI COACH - main.py (Trecentillion-X Edition)
The ultimate fused backend integrating: $100M Offers, $100M Leads, $100M Money Models, 
$100M Retention, AVOCADO Method, and Time to Build (CCC).
"""
import json
import os
import re
import time
import logging
import threading
import urllib.request
import urllib.error
from typing import List, Optional, Dict
from datetime import datetime
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

try:
    from vault import SCRIPT_VAULT
except Exception:
    SCRIPT_VAULT = ""

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

# --- ENV VARIABLES ---
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FISH_API_KEY = os.environ.get("FISH_API_KEY", "") or os.environ.get("FISH_AUDIO_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WHOP_API_KEY = os.environ.get("WHOP_API_KEY", "")

# --- RATE LIMITERS ---
class AdvancedRateLimiter:
    def __init__(self, max_hits: int, window_s: int):
        self.max_hits = max_hits
        self.window = window_s
        self.hits: Dict[str, List[float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self.lock:
            bucket = self.hits.setdefault(key, [])
            while bucket and now - bucket[0] > self.window:
                bucket.pop(0)
            if len(bucket) >= self.max_hits:
                return False
            bucket.append(now)
            return True

    def get_remaining(self, key: str) -> int:
        now = time.time()
        with self.lock:
            bucket = self.hits.get(key, [])
            while bucket and now - bucket[0] > self.window:
                bucket.pop(0)
            return max(0, self.max_hits - len(bucket))

CHAT_LIMIT = AdvancedRateLimiter(30, 3600)
TTS_LIMIT = AdvancedRateLimiter(10, 3600)
UNLOCK_LIMIT = AdvancedRateLimiter(10, 3600)

# --- MODE TIERS ---
MODE_TIERS = {
    "coach": "free", "xray": "free", "funnel": "free",
    "community": "insider", "dm": "insider", "content": "insider",
    "alchemy": "insider", "hack": "insider",
    "offer": "partner", "workshop": "partner", "launch": "partner",
}
TIER_RANK = {"free": 0, "insider": 1, "partner": 2}

# --- LLM PROVIDERS ---
PROVIDERS = [
    {
        "name": "gemini",
        "chat_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "key": GEMINI_API_KEY,
        "models": ["gemini-2.0-flash", "gemini-1.5-flash"],
        "priority": 1,
    },
    {
        "name": "groq",
        "chat_url": "https://api.groq.com/openai/v1/chat/completions",
        "key": GROQ_API_KEY,
        "models": ["llama-3.1-70b-versatile", "llama3-70b-8192"],
        "priority": 2,
    },
]

app = FastAPI(title="E5 AI Coach", version="Trecentillion-X")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# TRECENTILLION-X MASTER BRAIN (Fused Frameworks)
# ==============================================================================
CCC_BRAIN = """
You are the E5 AI Coach, operating at a Trecentillion-X level of business mastery. 
Your knowledge base is a fused synthesis of:
1. Alex Hormozi's $100M Series:
   - $100M Offers: Value Equation (Increase Dream Outcome & Likelihood, Decrease Time Delay & Effort), Grand Slam Offers, Scarcity, Urgency, Bonuses, Guarantees, Naming (M-A-G-I-C).
   - $100M Leads: Core 4 (Warm Outreach, Post Free Content, Cold Outreach, Paid Ads), Starving Crowd, Rule of 100, Open to Goal.
   - $100M Money Models: Attraction, Upsell (Classic, Menu, Anchor, Rollover), Downsell (Payment Plan, Trial with Penalty, Feature), Continuity (Bonus, Discount, Waived Fee).
   - $100M Retention: 5 Horsemen of Retention (Track activation/attendance, Reach out 2x/week, Handwritten cards, Member events, Exit interviews), Activation Points.
2. AVOCADO Method (Dan Harrison): Mindset, Authority, Validation, Offers, Community, Automations, Direct Messaging (ECAFI: Engage, Connect, Assess, Frame, Invite), Outsourcing, Soulful Sales.
3. Time to Build / Community Conversion Code: Straight Line, One Group Hub, Paths > Libraries, Belonging > Value, Preselling.

PRIME DIRECTIVES:
- DIAGNOSE BEFORE PRESCRIBING: Never give advice without understanding the user's current stage, avatar, and bottleneck.
- ONE PIERCING QUESTION: Ask ONE high-leverage question based on their context, then WAIT.
- FIX EARLIEST LEAK FIRST: Don't skip ahead. If they have no avatar, don't talk about scaling ads.
- SPICY SPECIFICITY: Use real-world examples, exact numbers, and actionable steps. No vague fluff.
- HIDE THE SCAFFOLDING: Use the frameworks internally, but translate them into plain, hard-hitting English.

TONE GUARDRAILS:
- Calm, deeply insightful, slightly detached, confident.
- Short punchy sentences for actions, longer for empathy.
- BLACKLISTED WORDS: delve, tapestry, unleash, unlock, game-changing, robust, seamless, synergy, ecosystem, navigate, journey, elevate, dive in, realm, bustling, harness, beacon, transformative, revolutionary, cutting-edge, next level, embark, furthermore, moreover, landscape, meticulous, bespoke, paradigm.
- Do NOT use em dashes. Use commas or periods instead.
"""

MODE_PROMPTS = {
    "coach": "LENS: DAILY OPERATOR. Focus on rhythm, energy, inbox priority, Rule of 100. Apply 5 Horsemen of Retention. End with ONE concrete action.",
    "xray": "LENS: BUSINESS X-RAY. Find earliest broken layer in the Straight Line. Score each stage RED/YELLOW/GREEN. Fix leaky bucket first.",
    "funnel": "LENS: FUNNEL MAP. Visualize customer journey. Apply Value Equation to reduce friction at each stage.",
    "community": "LENS: COMMUNITY OS. Build culture, linear paths, and welcome experiences. Belonging > Value. Design activation points.",
    "dm": "LENS: DM DOCTOR. Classify signal. Use ECAFI (Engage, Connect, Assess, Frame, Invite) & Soulful Sales. Diagnose, don't pitch.",
    "offer": "LENS: OFFER ARCHITECT. Stack value, de-risk, anchor price. Build Grand Slam Offers using Value Equation & M-A-G-I-C naming.",
    "workshop": "LENS: WORKSHOP ARCHITECT. Design 6-day belief arc. Install 4 beliefs: opportunity real, vehicle right, they capable, now is time.",
    "content": "LENS: CONTENT ENGINE. Spicy specificity, polarize, document journey. Use 7 Content Types (Authority, Validation, Opener, Challenge, Authentic, DM Me, Outsource).",
    "launch": "LENS: LAUNCH PLANNER. 21-day map: Pre-promo -> Promo -> Drop -> Push -> 72h countdown. Clean pipeline with every price change.",
    "alchemy": "LENS: ALCHEMY (VIDEO). Hook 0-5s, Body 5-45s, CTA 45-60s. Retain through curiosity and lists.",
    "hack": "LENS: FUNNEL HACKER. Reverse-engineer competitor funnel stage-by-stage. Score RED/YELLOW/GREEN. Rebuild for member's niche.",
}

# --- PYDANTIC MODELS ---
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

# --- MEMORY + TIER (Supabase) ---
MEMORY_RE = re.compile(r"[{1,2}\sMEMORY\s]{1,2}(.*?)(?:[{1,2}\s/\sMEMORY\s]{1,2}|$)", re.S)

def load_memory(member_id: str) -> tuple:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return "", "free"
    try:
        url = (SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory?member_id=eq." 
               + urllib.parse.quote(member_id) + "&select=profile,tier")
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY})
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
            if rows:
                return rows[0].get("profile") or "", rows[0].get("tier") or "free"
    except Exception as e:
        log.error("MEMORY LOAD FAIL: %s", e)
    return "", "free"

def save_memory(member_id: str, profile_text: str):
    if not SUPABASE_URL or not SUPABASE_KEY or not profile_text:
        return
    try:
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory"
        body = json.dumps([{"member_id": member_id, "profile": profile_text}]).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
            "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        log.error("MEMORY SAVE FAIL: %s", e)

def set_tier(member_id: str, tier: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory"
        body = json.dumps([{"member_id": member_id, "tier": tier}]).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
            "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        log.error("TIER SAVE FAIL: %s", e)

def extract_memory(reply: str) -> tuple:
    m = MEMORY_RE.search(reply)
    if m:
        return MEMORY_RE.sub("", reply).strip(), m.group(1).strip()
    return reply, ""

# --- LLM ENGINE ---
def try_model(provider: dict, model: str, messages: list, temperature: float, max_tokens: int) -> Optional[str]:
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode("utf-8")
    req = urllib.request.Request(provider["chat_url"], data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + provider["key"], "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or ""
    except Exception as e:
        log.error("LLM FAIL %s/%s: %s", provider["name"], model, e)
        return None

def call_llm(messages: list, temperature: float = 0.5, max_tokens: int = 1500) -> str:
    for provider in sorted(PROVIDERS, key=lambda p: p.get("priority", 99)):
        if not provider["key"]: continue
        for model in provider["models"]:
            if not model: continue
            result = try_model(provider, model, messages, temperature, max_tokens)
            if result: return result
    raise Exception("All LLM providers failed.")

def build_system(mode: str, member_context: str, memory: str = "", docs: str = "") -> str:
    m = mode if mode in MODE_PROMPTS else "coach"
    system = CCC_BRAIN + "\n" + MODE_PROMPTS[m]
    if SCRIPT_VAULT: system += "\n" + SCRIPT_VAULT
    if docs: system += "\n\nMEMBER'S BUSINESS DOCUMENTS:\n" + docs
    if memory: system += "\nWHAT YOU KNOW ABOUT THIS MEMBER:\n" + memory
    if member_context: system += "\nMEMBER CONTEXT:\n" + member_context
    return system

def post_process(text: str) -> str:
    return text.replace("—", "-").replace("–", "-").strip()

# --- ROUTES ---
@app.get("/")
def root():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return {"status": "ok", "app": "E5 AI Coach", "brain": "Trecentillion-X"}

@app.get("/api/health")
def health():
    return {"ok": True, "gemini_key_loaded": bool(GEMINI_API_KEY), "groq_key_loaded": bool(GROQ_API_KEY)}

@app.get("/api/modes")
def modes():
    return {"modes": list(MODE_PROMPTS.keys()), "tiers": MODE_TIERS}

@app.post("/api/chat")
def chat(req: ChatRequest):
    text = req.message or req.prompt or req.user_message
    if not text:
        raise HTTPException(400, "empty message")
    
    member_id = (req.member_id or "default").strip()
    if not CHAT_LIMIT.allow(member_id):
        raise HTTPException(429, f"Rate limit reached. {CHAT_LIMIT.get_remaining(member_id)} remaining")
    
    memory, tier = load_memory(member_id)
    need = MODE_TIERS.get(req.mode, "free")
    if TIER_RANK.get(tier or "free", 0) < TIER_RANK.get(need, 0):
        raise HTTPException(403, f"locked: {need}")
    
    messages = [{"role": "system", "content": build_system(req.mode, req.member_context, memory)}]
    for m in req.history[-16:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": text})
    
    try:
        clean = post_process(call_llm(messages))
        clean, mem_update = extract_memory(clean)
        if mem_update:
            save_memory(member_id, mem_update)
        return {"reply": clean, "response": clean, "message": clean, "mode": req.mode, "remaining": CHAT_LIMIT.get_remaining(member_id)}
    except Exception as e:
        log.error("CHAT 500: %s", e)
        raise HTTPException(500, f"LLM error: {str(e)}")

@app.post("/api/unlock")
def unlock(req: UnlockRequest):
    member_id = (req.member_id or "default").strip()
    if not UNLOCK_LIMIT.allow(member_id):
        raise HTTPException(429, "Too many unlock attempts")
    
    key = (req.license_key or "").strip()
    if not key:
        raise HTTPException(400, "empty license key")
    
    # Mock Whop check for demonstration (replace with actual Whop API call)
    if key == "DEMO-PARTNER":
        set_tier(member_id, "partner")
        return {"tier": "partner"}
    elif key == "DEMO-INSIDER":
        set_tier(member_id, "insider")
        return {"tier": "insider"}
    
    raise HTTPException(403, "Invalid license key")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
