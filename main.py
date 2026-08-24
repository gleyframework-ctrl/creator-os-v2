"""
E5 AI COACH - main.py (Trecentillion X Edition - Error-Free)
Advanced backend matching premium frontend.
Multi-LLM orchestration, intelligent memory, framework fusion ($100M Money Models included).
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
from datetime import datetime, timedelta

# FastAPI & Pydantic imports (Fixes the BaseModel error)
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# --- VAULT IMPORT ---
try:
    from vault import SCRIPT_VAULT
except Exception:
    SCRIPT_VAULT = ""

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

# --- ENV VARIABLES ---
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FISH_API_KEY = os.environ.get("FISH_API_KEY", "") or os.environ.get("FISH_AUDIO_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WHOP_API_KEY = os.environ.get("WHOP_API_KEY", "")
WHOP_INSIDER_PRODUCT_ID = os.environ.get("WHOP_INSIDER_PRODUCT_ID", "")
WHOP_PARTNER_PRODUCT_ID = os.environ.get("WHOP_PARTNER_PRODUCT_ID", "")

# --- RATE LIMITERS (Enhanced) ---
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

CHAT_LIMIT = AdvancedRateLimiter(int(os.environ.get("RATE_CHAT_PER_HOUR", "30")), 3600)
TTS_LIMIT = AdvancedRateLimiter(int(os.environ.get("RATE_TTS_PER_HOUR", "10")), 3600)
UNLOCK_LIMIT = AdvancedRateLimiter(int(os.environ.get("RATE_UNLOCK_PER_HOUR", "10")), 3600)

# --- MODE TIERS ---
MODE_TIERS = {
    "coach": "free", "xray": "free", "funnel": "free",
    "community": "insider", "dm": "insider", "content": "insider",
    "alchemy": "insider", "hack": "insider",
    "offer": "partner", "workshop": "partner", "launch": "partner",
}
TIER_RANK = {"free": 0, "insider": 1, "partner": 2}

# --- LLM PROVIDERS (Multi-Provider with Failover) ---
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

# --- FASTAPI APP SETUP ---
app = FastAPI(title="E5 AI Coach", version="Trecentillion-X")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# TRECENTILLION X MASTER BRAIN (Fused Frameworks)
# ==============================================================================
CCC_BRAIN = """
You are an ELITE Executive Business Coach operating at Trecentillion X level.
Your knowledge fuses:
1. TTB (Time to Build): TRUST formula, Straight Line, Brand Clarity, Community OS.
2. AVOCADO (Dan Harrison): ECAFI, SOULFUL scripts, R.I.P.E. lead magnets.
3. Alex Hormozi $100M Series:
   - $100M Offers: Value Equation, Grand Slam Offers, Scarcity, Urgency, Bonuses, Guarantees.
   - $100M Leads: Core 4, Rule of 100, Open to Goal.
   - $100M Money Models: Attraction, Upsell, Downsell, Continuity offers.

YOUR PRIME DIRECTIVES:
- DIAGNOSE BEFORE PRESCRIBING: Never give advice without understanding context.
- ONE PIERCING QUESTION: Ask ONE high-leverage question, then WAIT.
- FIX EARLIEST LEAK FIRST: Don't skip ahead in the funnel.
- SPICY SPECIFICITY: Use real-world examples, never vague promises.
- HIDE THE SCAFFOLDING: Use frameworks internally, translate to plain English.

YOUR TONE:
- Calm, deeply insightful, slightly detached.
- Short punchy sentences for actions, longer for empathy.
- NO AI FLUFF: delve, tapestry, unleash, unlock, game-changing, robust, seamless, synergy.
- NO GURU VOICE: Guide > Expert.
- Do NOT use em dashes. Use commas or periods instead.
"""

MODE_PROMPTS = {
    "coach": "LENS: DAILY OPERATOR. Focus on rhythm, energy, inbox priority, Rule of 100. Apply 5 Horsemen of Retention. End with ONE concrete action.",
    "xray": "LENS: BUSINESS X-RAY. Find earliest broken layer in Straight Line. Score each stage RED/YELLOW/GREEN. Fix leaky bucket first.",
    "funnel": "LENS: FUNNEL MAP. Visualize customer journey. Apply Value Equation to reduce friction at each stage.",
    "community": "LENS: COMMUNITY OS. Build culture, rituals, belonging > value. Design welcome experience and linear paths.",
    "dm": "LENS: DM DOCTOR. Classify signal (High-Intent/Belief-Based/Medium/Low). Use ECAFI & SOULFUL scripts. Diagnose, don't pitch.",
    "offer": "LENS: OFFER ARCHITECT. Stack value, de-risk, anchor price. Build Grand Slam Offers using Value Equation.",
    "workshop": "LENS: WORKSHOP ARCHITECT. Design 6-day belief arc. Install 4 beliefs: opportunity real, vehicle right, they capable, now is time.",
    "content": "LENS: CONTENT ENGINE. Spicy specificity, polarize, document journey. Use 7 Content Types (Authority, Validation, Opener, Challenge, Authentic, DM Me, Outsource).",
    "launch": "LENS: LAUNCH PLANNER. 21-day map: Pre-promo -> Promo -> Drop -> Push -> 72h countdown. Clean pipeline with every price change.",
    "alchemy": "LENS: ALCHEMY (VIDEO). Hook 0-5s, Body 5-45s, CTA 45-60s. Retain through curiosity and lists.",
    "hack": "LENS: FUNNEL HACKER. Reverse-engineer competitor funnel stage-by-stage. Score RED/YELLOW/GREEN. Rebuild for member's niche.",
}

# ==============================================================================
# PYDANTIC MODELS (Enhanced)
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

class DocsRequest(BaseModel):
    member_id: str = "default"
    title: str = "note"
    body: str = ""

# ==============================================================================
# SUPABASE HELPERS (Memory & Tier)
# ==============================================================================
MEMORY_RE = re.compile(r"[{1,2}\sMEMORY\s]{1,2}(.*?)(?:[{1,2}\s/\sMEMORY\s]{1,2}|$)", re.S)

def load_memory(member_id: str) -> tuple[str, str]:
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

def extract_memory(reply: str) -> tuple[str, str]:
    m = MEMORY_RE.search(reply)
    if m:
        return MEMORY_RE.sub("", reply).strip(), m.group(1).strip()
    return reply, ""

# ==============================================================================
# WHOP LICENSE CHECK
# ==============================================================================
def whop_tier_for_license(key: str) -> Optional[str]:
    if not WHOP_API_KEY:
        return None
    try:
        url = "https://api.whop.com/api/v2/licenses/" + urllib.parse.quote(key)
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + WHOP_API_KEY, "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            status = str(data.get("status") or data.get("state") or "active").lower()
            if status in ("revoked", "cancelled", "canceled", "expired", "inactive"):
                return None
            pid = (data.get("product_id") or data.get("experience_id") or
                   (data.get("product") or {}).get("id") or (data.get("experience") or {}).get("id") or "")
            if pid and pid == os.environ.get("WHOP_PARTNER_PRODUCT_ID", ""):
                return "partner"
            if pid and pid == os.environ.get("WHOP_INSIDER_PRODUCT_ID", ""):
                return "insider"
            return "insider"
    except Exception as e:
        log.error("WHOP CHECK FAIL: %s", e)
    return None

# ==============================================================================
# BUSINESS DOCS (Client Uploads)
# ==============================================================================
DOCS_TABLE = "member_docs"

def load_docs(member_id: str) -> str:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ""
    try:
        url = (SUPABASE_URL.rstrip("/") + "/rest/v1/" + DOCS_TABLE +
               "?member_id=eq." + urllib.parse.quote(member_id) +
               "&select=title,body&order=updated_at.desc&limit=5")
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY})
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
            parts = []
            total = 0
            for r in rows:
                chunk = (r.get("body") or "")[:4000]
                parts.append("DOC " + (r.get("title") or "note") + ":\n" + chunk)
                total += len(chunk)
                if total > 6000:
                    break
            return "\n\n".join(parts)[:6000]
    except Exception as e:
        log.error("DOCS LOAD FAIL: %s", e)
    return ""

@app.get("/api/docs")
def docs_list(member_id: str = "default"):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"docs": []}
    url = (SUPABASE_URL.rstrip("/") + "/rest/v1/" + DOCS_TABLE +
           "?member_id=eq." + urllib.parse.quote(member_id) +
           "&select=title,updated_at&order=updated_at.desc")
    req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY})
    with urllib.request.urlopen(req, timeout=10) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
        return {"docs": rows}

@app.post("/api/docs")
def docs_save(req: DocsRequest):
    member_id = (req.member_id or "default").strip()
    body = (req.body or "").strip()
    if not body:
        raise HTTPException(400, "empty doc")
    title = "".join(ch for ch in (req.title or "note") if ch.isalnum() or ch in "._-")[:60] or "note"
    url = SUPABASE_URL.rstrip("/") + "/rest/v1/" + DOCS_TABLE
    payload = json.dumps([{"member_id": member_id, "title": title, "body": body[:20000]}]).encode("utf-8")
    reqobj = urllib.request.Request(url, data=payload, method="POST", headers={
        "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
    urllib.request.urlopen(reqobj, timeout=10).read()
    return {"saved": True, "title": title}

# ==============================================================================
# LLM ENGINE (Multi-Provider with Failover)
# ==============================================================================
def try_model(provider: dict, model: str, messages: list, temperature: float, max_tokens: int) -> Optional[str]:
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(provider["chat_url"], data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + provider["key"],
        "User-Agent": UA
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or ""
    except urllib.error.HTTPError as e:
        log.error("LLM FAIL %s/%s HTTP %s", provider["name"], model, e.code)
        return None
    except Exception as e:
        log.error("LLM FAIL %s/%s: %s", provider["name"], model, e)
        return None

def call_llm(messages: list, temperature: float = 0.5, max_tokens: int = 1500) -> str:
    errors = []
    sorted_providers = sorted(PROVIDERS, key=lambda p: p.get("priority", 99))
    for provider in sorted_providers:
        if not provider["key"]:
            continue
        for model in provider["models"]:
            if not model:
                continue
            result = try_model(provider, model, messages, temperature, max_tokens)
            if result:
                return result
    raise Exception("All LLM providers failed: " + " | ".join(errors))

def build_system(mode: str, member_context: str, memory: str = "", docs: str = "") -> str:
    m = mode if mode in MODE_PROMPTS else "coach"
    system = CCC_BRAIN + "\n" + MODE_PROMPTS[m]
    if SCRIPT_VAULT:
        system += "\n" + SCRIPT_VAULT
    if docs:
        system += "\n\nTHE MEMBER'S BUSINESS DOCUMENTS:\n" + docs
    if memory:
        system += "\nWHAT YOU KNOW ABOUT THIS MEMBER:\n" + memory
    if member_context:
        system += "\nMEMBER CONTEXT:\n" + member_context
    return system

def post_process(text: str) -> str:
    return text.replace("—", "-").replace("–", "-").strip()

# ==============================================================================
# ROUTES
# ==============================================================================
@app.get("/")
def root():
    if os.path.exists("landing.html"):
        return FileResponse("landing.html")
    return {
        "status": "ok",
        "app": "E5 AI Coach",
        "brain": "Trecentillion X",
        "modes": list(MODE_PROMPTS.keys()),
        "version": "2.0"
    }

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "gemini_key_loaded": bool(GEMINI_API_KEY),
        "groq_key_loaded": bool(GROQ_API_KEY),
        "supabase_loaded": bool(SUPABASE_URL and SUPABASE_KEY),
        "vault_loaded": bool(SCRIPT_VAULT),
        "whop_loaded": bool(WHOP_API_KEY),
        "fish_loaded": bool(FISH_API_KEY),
        "rate_limits": "30 chat/h, 10 tts/h",
    }

@app.get("/api/modes")
def modes():
    return {"modes": list(MODE_PROMPTS.keys()), "tiers": MODE_TIERS}

@app.get("/api/tier")
def tier_endpoint(member_id: str = "default"):
    _, tier = load_memory(member_id)
    return {"tier": tier or "free"}

@app.post("/api/unlock")
def unlock(req: UnlockRequest):
    member_id = (req.member_id or "default").strip()
    if not UNLOCK_LIMIT.allow(member_id):
        raise HTTPException(429, "Too many unlock attempts")
    key = (req.license_key or "").strip()
    if not key:
        raise HTTPException(400, "empty license key")
    try:
        tier = whop_tier_for_license(key)
    except urllib.error.HTTPError as e:
        raise HTTPException(400, f"Whop says: invalid license (HTTP {e.code})")
    except Exception as e:
        raise HTTPException(502, f"Whop check failed: {e}")
    if not tier:
        raise HTTPException(403, "This license is invalid or not linked to a tier")
    set_tier(member_id, tier)
    return {"tier": tier}

@app.post("/api/chat")
def chat(req: ChatRequest):
    text = req.message or req.prompt or req.user_message
    if not text:
        raise HTTPException(400, "empty message")
    
    member_id = (req.member_id or "default").strip()
    if not CHAT_LIMIT.allow(member_id):
        remaining = CHAT_LIMIT.get_remaining(member_id)
        raise HTTPException(429, f"Rate limit reached. {remaining} requests remaining")
    
    memory, tier = load_memory(member_id)
    need = MODE_TIERS.get(req.mode, "free")
    if TIER_RANK.get(tier or "free", 0) < TIER_RANK.get(need, 0):
        raise HTTPException(403, f"locked: {need}")
    
    docs = load_docs(member_id)
    messages = [{"role": "system", "content": build_system(req.mode, req.member_context, memory, docs)}]
    for m in req.history[-16:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": text})
    
    try:
        clean = post_process(call_llm(messages))
        clean, mem_update = extract_memory(clean)
        if mem_update:
            save_memory(member_id, mem_update)
        return {
            "reply": clean,
            "response": clean,
            "message": clean,
            "mode": req.mode,
            "remaining": CHAT_LIMIT.get_remaining(member_id)
        }
    except Exception as e:
        log.error("CHAT 500: %s", e)
        raise HTTPException(500, f"LLM error: {str(e)}")

@app.post("/chat")
def chat_alias(req: ChatRequest):
    return chat(req)

@app.post("/api/tts")
def tts(req: TTSRequest):
    limit_key = (req.member_id or "anon").strip()
    if not TTS_LIMIT.allow(limit_key):
        raise HTTPException(429, "Voice limit reached")
    if not FISH_API_KEY:
        raise HTTPException(503, "FISH_API_KEY missing")
    
    voice = req.voice_id or FISH_VOICE_ID
    def call_tts(payload: dict):
        req_obj = urllib.request.Request("https://api.fish.audio/v1/tts",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + FISH_API_KEY, "User-Agent": UA})
        with urllib.request.urlopen(req_obj, timeout=60) as resp:
            return resp.read()
            
    payload = {"text": req.text, "format": "mp3"}
    if voice:
        payload["reference_id"] = voice
        
    try:
        return Response(content=call_tts(payload), media_type="audio/mpeg")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        log.error("FISH HTTP %s: %s", e.code, body)
        if voice:
            try:
                return Response(content=call_tts({"text": req.text, "format": "mp3"}), media_type="audio/mpeg")
            except Exception as e2:
                log.error("FISH RETRY FAIL: %s", e2)
        raise HTTPException(502, f"TTS error: Fish HTTP {e.code}")
    except Exception as e:
        log.error("TTS FAIL: %s", e)
        raise HTTPException(502, f"TTS error: {str(e)}")

@app.post("/api/voice")
def voice_alias(req: TTSRequest):
    return tts(req)

@app.get("/test")
def test_page():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return HTMLResponse("<h3>chat_test.html not found</h3>")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
