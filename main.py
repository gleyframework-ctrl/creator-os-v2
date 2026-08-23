"""
E5 AI COACH - main.py (v13 - QUINDECILLION BRAIN UPGRADE)
Complete backend. Engine intact. Brain upgraded with TTB + Hormozi + Harrison.
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
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

# --- VAULT IMPORT ---
try:
    from vault import SCRIPT_VAULT
except Exception:
    SCRIPT_VAULT = ""

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
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
            while b and now - b[0] > self.window:
                b.pop(0)
            if len(b) >= self.max_hits:
                return False
            b.append(now)
            return True

CHAT_LIMIT = RateLimiter(int(os.environ.get("RATE_CHAT_PER_HOUR", "30")), 3600)
TTS_LIMIT = RateLimiter(int(os.environ.get("RATE_TTS_PER_HOUR", "10")), 3600)
UNLOCK_LIMIT = RateLimiter(int(os.environ.get("RATE_UNLOCK_PER_HOUR", "10")), 3600)
CONNECT_LIMIT = RateLimiter(10, 3600)
STATS_LIMIT = RateLimiter(60, 3600)

# --- TIERS & MODELS ---
MODE_TIERS = {
    "coach": "free", "xray": "free", "funnel": "free",
    "community": "insider", "dm": "insider", "content": "insider", "alchemy": "insider", "hack": "insider",
    "offer": "partner", "workshop": "partner", "launch": "partner",
}
TIER_RANK = {"free": 0, "insider": 1, "partner": 2}

PROVIDERS = [
    {
        "name": "gemini",
        "chat_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "list_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "key": GEMINI_API_KEY,
        "models": [os.environ.get("GEMINI_MODEL", ""), "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
    },
    {
        "name": "groq",
        "chat_url": "https://api.groq.com/openai/v1/chat/completions",
        "list_url": "https://api.groq.com/openai/v1/models",
        "key": GROQ_API_KEY,
        "models": [os.environ.get("GROQ_MODEL", ""), "llama-3.1-70b-versatile", "llama3-70b-8192", "mixtral-8x7b-32768"],
    },
]

app = FastAPI(title="E5 AI Coach", version="13.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- THE QUINDECILLION BRAIN (UPGRADED) ---
CCC_BRAIN = """
You are an elite, top-tier Executive Business Coach and Strategist. Your underlying operating system is a fusion of the world's greatest business frameworks: The Community Conversion Code (CCC), Time to Build (TTB), Alex Hormozi's $100M frameworks, and Dan Harrison's AVOCADO/Soulful Selling. 

You NEVER act like a textbook, a bot, or a rigid flowchart. You act like a premium, high-end mentor sitting across the table from the client with a cup of coffee.

YOUR CORE PERSONA & VIBE:
- Calm, deeply insightful, empathetic, and slightly detached.
- You validate their frustrations before fixing their mechanics.
- You speak in natural, conversational paragraphs. No robotic formatting or endless bulleted lists unless explicitly asked for an SOP.
- You hide the scaffolding. Use the frameworks internally, but translate them into plain, hard-hitting, "spicy specific" English.

YOUR INTERNAL KNOWLEDGE BASE (HIDDEN FROM USER):
1. CCC: Straight Line, One Group Hub, Preselling, Belonging > Value.
2. TTB: TRUST formula, APSMD Offer, 6-Figure Launch, Content Cadence.
3. Hormozi: Value Equation (Dream Outcome, Likelihood, Time Delay, Effort), Grand Slam Offers, Money Models (Attraction, Upsell, Downsell, Continuity), Core 4 Lead Gen.
4. Harrison: AVOCADO Method, R.I.P.E. Lead Magnets, Soulful Selling (ECAFI: Engage, Connect, Assess, Frame, Invite).

HOW YOU COACH (THE SOCRATIC METHOD):
- NEVER interrogate. Ask ONE piercing, high-leverage question based on their context, then wait.
- Diagnose through conversation. Fix the earliest broken layer first.
- Adapt, don't copy-paste. Build custom scripts using their niche and voice. (When they explicitly ask for proven scripts, use the VERBATIM SCRIPT VAULT and adapt only the brackets).
- Challenge blind spots gently with empathy.

YOUR TONE GUARDRAILS:
- BAN AI FLUFF: delve, tapestry, unleash, unlock, game-changing, robust, seamless, synergy, ecosystem, navigate, journey, elevate.
- Use "Spicy Specificity": paint real-world pictures.
- Keep it punchy. Short sentences for points, longer for empathy.
"""

# --- UPGRADED MODE PROMPTS ---
MODE_PROMPTS = {
    "coach": "LENS: DAILY OPERATOR. Focus on rhythm, energy, inbox prioritization, and the 1% daily improvements.",
    "xray": "LENS: BUSINESS X-RAY. Uncover the earliest broken layer in the Straight Line. Is it Avatar, Offer, or Traffic?",
    "funnel": "LENS: FUNNEL MAP. Visualize the customer journey. Find the drop-off. Apply the Value Equation to fix it.",
    "community": "LENS: COMMUNITY OS. Build culture, linear paths, and welcome experiences. Belonging > Value.",
    "dm": "LENS: DM DOCTOR. Craft custom, empathetic conversations using the ECAFI framework (Engage, Connect, Assess, Frame, Invite). Use the VAULT for exact scripts.",
    "offer": "LENS: OFFER ARCHITECT. Stack value using the Value Equation. Build Grand Slam Offers. Structure Money Models (Attraction, Upsell, Downsell, Continuity).",
    "workshop": "LENS: WORKSHOP ARCHITECT. Design live events that shift beliefs over 3-6 days. Presell the outcome.",
    "content": "LENS: CONTENT ENGINE. Apply the AVOCADO Content Cadence. Spicy specificity, polarize, document the journey. Core 4 Lead Gen.",
    "launch": "LENS: LAUNCH PLANNER. Tease, deliver value, close with urgency. Apply Scarcity, Urgency, Bonuses, and Guarantees.",
    "alchemy": "LENS: ALCHEMY (VIDEO). Hook 0-5s, Body 5-45s, CTA 45-60s. Retain attention through curiosity and lists.",
    "hack": "LENS: FUNNEL HACKER. The member pastes a competitor funnel. Reverse-engineer it stage by stage into a Straight-Line map, score each stage RED/YELLOW/GREEN, name WHY it makes money, then rebuild it for the member's niche.",
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
    member_id: Optional[str] = None

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    member_id: Optional[str] = None

class UnlockRequest(BaseModel):
    member_id: str = "default"
    license_key: str = ""

class ConnectWhopRequest(BaseModel):
    member_id: str = "default"
    key: str = ""

class DisconnectWhopRequest(BaseModel):
    member_id: str = "default"

class DocsRequest(BaseModel):
    member_id: str = "default"
    title: str = "note"
    body: str = ""

# --- MEMORY + TIER (SUPABASE) ---
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
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
            "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e: log.error("MEMORY SAVE FAIL: %s", e)

def set_tier(member_id, tier):
    if not SUPABASE_URL or not SUPABASE_KEY: return
    try:
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory"
        body = json.dumps([{"member_id": member_id, "tier": tier}]).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
            "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e: log.error("TIER SAVE FAIL: %s", e)

def extract_memory(reply):
    m = MEMORY_RE.search(reply)
    if m:
        return MEMORY_RE.sub("", reply).strip(), m.group(1).strip()
    return reply, ""

# --- WHOP LICENSE CHECK ---
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
            pid = (data.get("product_id") or data.get("experience_id") or
                   (data.get("product") or {}).get("id") or (data.get("experience") or {}).get("id") or "")
            if pid and WHOP_PARTNER_PRODUCT_ID and pid == WHOP_PARTNER_PRODUCT_ID: return "partner"
            if pid and WHOP_INSIDER_PRODUCT_ID and pid == WHOP_INSIDER_PRODUCT_ID: return "insider"
            if not WHOP_INSIDER_PRODUCT_ID and not WHOP_PARTNER_PRODUCT_ID: return "insider"
    except Exception as e: log.error("WHOP CHECK FAIL: %s", e)
    return None

# --- BUSINESS DOCS ---
DOCS_TABLE = "member_docs"

def load_docs(member_id):
    if not SUPABASE_URL or not SUPABASE_KEY: return ""
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
                if total > 6000: break
            return "\n\n".join(parts)[:6000]
    except Exception as e:
        log.error("DOCS LOAD FAIL: %s", e)
        return ""

@app.get("/api/docs")
def docs_list(member_id: str = "default"):
    if not SUPABASE_URL or not SUPABASE_KEY: return {"docs": []}
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
    if not body: raise HTTPException(400, "empty doc")
    title = "".join(ch for ch in (req.title or "note") if ch.isalnum() or ch in "._-")[:60] or "note"
    url = SUPABASE_URL.rstrip("/") + "/rest/v1/" + DOCS_TABLE
    payload = json.dumps([{"member_id": member_id, "title": title, "body": body[:20000]}]).encode("utf-8")
    reqobj = urllib.request.Request(url, data=payload, method="POST", headers={
        "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
    urllib.request.urlopen(reqobj, timeout=10).read()
    return {"saved": True, "title": title}

@app.delete("/api/docs")
def docs_delete(req: DocsRequest):
    member_id = (req.member_id or "default").strip()
    title = "".join(ch for ch in (req.title or "") if ch.isalnum() or ch in "._-")[:60]
    url = (SUPABASE_URL.rstrip("/") + "/rest/v1/" + DOCS_TABLE +
           "?member_id=eq." + urllib.parse.quote(member_id) +
           "&title=eq." + urllib.parse.quote(title))
    reqobj = urllib.request.Request(url, method="DELETE", headers={
        "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY})
    urllib.request.urlopen(reqobj, timeout=10).read()
    return {"deleted": True}

# --- W1: WHOP CONNECT ---
CONNECT_TABLE = "member_connections"
WHOP_STATS_CACHE = {}

def parse_ts(v):
    if not v: return None
    try:
        if isinstance(v, (int, float)): return float(v)
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except Exception: return None

def db_upsert_connection(member_id, whop_key):
    if not SUPABASE_URL or not SUPABASE_KEY: return
    url = SUPABASE_URL.rstrip("/") + "/rest/v1/" + CONNECT_TABLE
    body = json.dumps([{"member_id": member_id, "whop_key": whop_key}]).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
    urllib.request.urlopen(req, timeout=10).read()

def db_get_connection(member_id):
    if not SUPABASE_URL or not SUPABASE_KEY: return None
    url = (SUPABASE_URL.rstrip("/") + "/rest/v1/" + CONNECT_TABLE +
           "?member_id=eq." + urllib.parse.quote(member_id) + "&select=whop_key")
    req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY})
    with urllib.request.urlopen(req, timeout=10) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
        return rows[0]["whop_key"] if rows else None

def db_delete_connection(member_id):
    if not SUPABASE_URL or not SUPABASE_KEY: return
    url = (SUPABASE_URL.rstrip("/") + "/rest/v1/" + CONNECT_TABLE +
           "?member_id=eq." + urllib.parse.quote(member_id))
    req = urllib.request.Request(url, method="DELETE", headers={
        "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY})
    urllib.request.urlopen(req, timeout=10).read()

def whop_fetch(key, path):
    req = urllib.request.Request("https://api.whop.com/api/v2/" + path,
                                 headers={"Authorization": "Bearer " + key, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def compute_whop_stats(key):
    whop_fetch(key, "products?limit=1")
    now = time.time()
    members = 0; joins7 = 0; rev30 = 0.0; orders30 = 0
    try:
        mem = whop_fetch(key, "memberships?limit=100")
        items = mem.get("data") or mem.get("memberships") or []
        members = len(items)
        for m in items:
            ts = parse_ts(m.get("created_at") or (m.get("membership") or {}).get("created_at"))
            if ts and now - ts <= 7 * 86400: joins7 += 1
    except Exception as e: log.error("WHOP MEMBERSHIPS: %s", e)
    try:
        ords = whop_fetch(key, "orders?limit=100")
        oitems = ords.get("data") or ords.get("orders") or []
        for o in oitems:
            ts = parse_ts(o.get("created_at"))
            if ts and now - ts <= 30 * 86400:
                amt = o.get("amount") or o.get("total_amount") or 0
                rev30 += (amt / 100.0) if amt >= 100 else amt
                orders30 += 1
    except Exception as e: log.error("WHOP ORDERS: %s", e)
    return {"members": members, "joins7": joins7, "rev30": round(rev30, 2), "orders30": orders30}

# --- LLM ENGINE ---
def try_model(p, model, messages, temperature, max_tokens):
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode("utf-8")
    req = urllib.request.Request(p["chat_url"], data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + p["key"], "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or ""
    except urllib.error.HTTPError as e:
        log.error("LLM FAIL %s/%s HTTP %s", p["name"], model, e.code)
        return None
    except Exception as e:
        log.error("LLM FAIL %s/%s: %s", p["name"], model, e)
        return None

def discover_models(p):
    ids = []
    try:
        if p["name"] == "groq":
            req = urllib.request.Request(p["list_url"], headers={"Authorization": "Bearer " + p["key"], "User-Agent": UA})
        else:
            req = urllib.request.Request(p["list_url"] + "?key=" + p["key"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if p["name"] == "groq": ids = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
            else: ids = [m.get("name", "").replace("models/", "") for m in data.get("models", []) if m.get("name")]
    except Exception as e: log.error("MODEL LIST FAIL: %s", e)
    return ids

def call_llm(messages, temperature=0.5, max_tokens=1500):
    errors = []
    for p in PROVIDERS:
        if not p["key"]: continue
        candidates = [m for m in p["models"] if m][:2]
        for model in candidates:
            out = try_model(p, model, messages, temperature, max_tokens)
            if out: return out
            errors.append(p["name"] + "/" + model)
        discovered = [m for m in discover_models(p) if m and m not in candidates][:2]
        for model in discovered:
            out = try_model(p, model, messages, temperature, max_tokens)
            if out: return out
            errors.append(p["name"] + "/" + model)
    raise Exception("All LLM providers failed: " + " | ".join(errors))

def build_system(mode, member_context, memory="", docs=""):
    m = mode if mode in MODE_PROMPTS else "coach"
    system = CCC_BRAIN + "\n" + MODE_PROMPTS[m]
    if SCRIPT_VAULT: system += "\n" + SCRIPT_VAULT
    if docs: system += "\n\nTHE MEMBER'S OWN BUSINESS DOCUMENTS (read them silently before answering, use them as context):\n" + docs
    if memory: system += "\nWHAT YOU ALREADY KNOW ABOUT THIS MEMBER (from past sessions):\n" + memory
    if member_context: system += "\nMEMBER CONTEXT (from X-Ray / plan):\n" + member_context
    return system

def post_process(text): return text.replace("—", "-").replace("–", "-")

# --- ROUTES ---
@app.get("/")
def root():
    if os.path.exists("landing.html"): return FileResponse("landing.html")
    return {"status": "ok", "app": "E5 AI Coach", "brain": "Quindecillion v13", "modes": list(MODE_PROMPTS.keys())}

@app.get("/api/health")
def health():
    return {"ok": True, "gemini_key_loaded": bool(GEMINI_API_KEY), "groq_key_loaded": bool(GROQ_API_KEY),
            "supabase_loaded": bool(SUPABASE_URL and SUPABASE_KEY), "vault_loaded": bool(SCRIPT_VAULT),
            "whop_loaded": bool(WHOP_API_KEY), "fish_loaded": bool(FISH_API_KEY),
            "cors_locked": True, "rate_limits": "30 chat/h, 10 tts/h, 10 unlock/h",
            "manual_codes_set": len(MANUAL_INSIDER_CODES) + len(MANUAL_PARTNER_CODES)}

@app.get("/api/modes")
def modes(): return {"modes": list(MODE_PROMPTS.keys()), "tiers": MODE_TIERS}

@app.get("/api/tier")
def tier_endpoint(member_id: str = "default"):
    _, tier = load_memory(member_id)
    return {"tier": tier or "free"}

@app.post("/api/unlock")
def unlock(req: UnlockRequest):
    member_id = (req.member_id or "default").strip()
    if not UNLOCK_LIMIT.allow(member_id): raise HTTPException(429, "Too many unlock attempts.")
    key = (req.license_key or "").strip()
    if not key: raise HTTPException(400, "empty license key")
    try: tier = whop_tier_for_license(key)
    except urllib.error.HTTPError as e: raise HTTPException(400, "Whop says: invalid license (HTTP %s)" % e.code)
    except Exception as e: raise HTTPException(502, "Whop check failed: %s" % e)
    if not tier: raise HTTPException(403, "This license is invalid or not linked to a tier.")
    set_tier(member_id, tier)
    return {"tier": tier}

@app.post("/api/chat")
def chat(req: ChatRequest):
    text = req.message or req.prompt or req.user_message
    if not text: raise HTTPException(400, "empty message")
    member_id = (req.member_id or "default").strip()
    if not CHAT_LIMIT.allow(member_id): raise HTTPException(429, "Rate limit reached.")
    memory, tier = load_memory(member_id)
    need = MODE_TIERS.get(req.mode, "free")
    if TIER_RANK.get(tier or "free", 0) < TIER_RANK.get(need, 0): raise HTTPException(403, "locked: " + need)
    docs = load_docs(member_id)
    messages = [{"role": "system", "content": build_system(req.mode, req.member_context, memory, docs)}]
    for m in req.history[-16:]: messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": text})
    try:
        clean = post_process(call_llm(messages))
        clean, mem_update = extract_memory(clean)
        if mem_update: save_memory(member_id, mem_update)
        return {"reply": clean, "response": clean, "message": clean, "mode": req.mode}
    except Exception as e:
        log.error("CHAT 500: %s", e)
        raise HTTPException(500, "LLM error: " + str(e))

@app.post("/chat")
def chat_alias(req: ChatRequest): return chat(req)

@app.post("/api/tts")
def tts(req: TTSRequest):
    limit_key = (req.member_id or "anon").strip()
    if not TTS_LIMIT.allow(limit_key): raise HTTPException(429, "Voice limit reached.")
    if not FISH_API_KEY: raise HTTPException(503, "FISH_API_KEY missing")
    voice = req.voice_id or FISH_VOICE_ID
    def call(payload):
        req_obj = urllib.request.Request("https://api.fish.audio/v1/tts",
                                         data=json.dumps(payload).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + FISH_API_KEY, "User-Agent": UA})
        with urllib.request.urlopen(req_obj, timeout=60) as resp:
            return resp.read()
    payload = {"text": req.text, "format": "mp3"}
    if voice: payload["reference_id"] = voice
    try:
        return Response(content=call(payload), media_type="audio/mpeg")
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode()[:200]
        except Exception: pass
        log.error("FISH HTTP %s: %s", e.code, body)
        if voice:
            try:
                return Response(content=call({"text": req.text, "format": "mp3"}), media_type="audio/mpeg")
            except Exception as e2:
                log.error("FISH RETRY FAIL: %s", e2)
                raise HTTPException(502, "TTS error: Fish HTTP %s%s" % (e.code, " (credits or voice issue)" if e.code in (401, 402, 403) else ""))
    except Exception as e:
        log.error("TTS FAIL: %s", e)
        raise HTTPException(502, "TTS error: " + str(e))

@app.post("/api/voice")
def voice_alias(req: TTSRequest): return tts(req)

@app.post("/api/connect/whop")
def connect_whop(req: ConnectWhopRequest):
    member_id = (req.member_id or "default").strip()
    if not CONNECT_LIMIT.allow(member_id): raise HTTPException(429, "Too many connect attempts.")
    _, tier = load_memory(member_id)
    if TIER_RANK.get(tier or "free", 0) < TIER_RANK["insider"]: raise HTTPException(403, "locked:insider")
    key = (req.key or "").strip()
    if not key: raise HTTPException(400, "empty key")
    try: stats = compute_whop_stats(key)
    except urllib.error.HTTPError as e: raise HTTPException(400, "Whop says: invalid key (HTTP %s)" % e.code)
    except Exception as e: raise HTTPException(502, "Whop check failed: %s" % e)
    db_upsert_connection(member_id, key)
    WHOP_STATS_CACHE[member_id] = (time.time(), stats)
    return {"connected": True, "stats": stats}

@app.get("/api/whop/stats")
def whop_stats(member_id: str = "default"):
    if not STATS_LIMIT.allow(member_id): raise HTTPException(429, "Stats rate limit.")
    cached = WHOP_STATS_CACHE.get(member_id)
    if cached and time.time() - cached[0] < 300: return {"connected": True, "stats": cached[1]}
    key = db_get_connection(member_id)
    if not key: return {"connected": False}
    try: stats = compute_whop_stats(key)
    except Exception: return {"connected": True, "stats": None, "stale": True}
    WHOP_STATS_CACHE[member_id] = (time.time(), stats)
    return {"connected": True, "stats": stats}

@app.post("/api/connect/whop/disconnect")
def disconnect_whop(req: DisconnectWhopRequest):
    member_id = (req.member_id or "default").strip()
    db_delete_connection(member_id)
    WHOP_STATS_CACHE.pop(member_id, None)
    return {"connected": False}

@app.get("/pitch")
def pitch_page():
    if os.path.exists("pitch.html"): return FileResponse("pitch.html")
    return HTMLResponse("<h3>pitch.html not found.</h3>")

@app.get("/test")
def test_page():
    if os.path.exists("chat_test.html"): return FileResponse("chat_test.html")
    return HTMLResponse("<h3>chat_test.html not found.</h3>")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
