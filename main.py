"""
E5 AI COACH - main.py (FINAL MASTER EDITION - v8)
Pure stdlib. No external LLM packages. 
Includes: Premium Brain, Verbatim Vault, Supabase Memory, Whop Gating, Fish TTS.
"""
import json
import os
import re
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

# ------------------------- LOGGING & CONFIG -------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

# Browser User-Agent to bypass Cloudflare 403 blocks
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FISH_API_KEY = os.environ.get("FISH_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WHOP_API_KEY = os.environ.get("WHOP_API_KEY", "")
WHOP_INSIDER_PRODUCT_ID = os.environ.get("WHOP_INSIDER_PRODUCT_ID", "")
WHOP_PARTNER_PRODUCT_ID = os.environ.get("WHOP_PARTNER_PRODUCT_ID", "")

# BULLETPROOF MANUAL CODES (Hardcoded so Railway env sync issues don't break testing)
env_insider = [c.strip() for c in os.environ.get("MANUAL_INSIDER_CODES", "").split(",") if c.strip()]
env_partner = [c.strip() for c in os.environ.get("MANUAL_PARTNER_CODES", "").split(",") if c.strip()]
MANUAL_INSIDER_CODES = list(set(["test123", "insider_beta"] + env_insider))
MANUAL_PARTNER_CODES = list(set(["partner123", "partner_beta"] + env_partner))

MODE_TIERS = {
    "coach": "free", "xray": "free", "funnel": "free",
    "community": "insider", "dm": "insider", "content": "insider", "alchemy": "insider",
    "offer": "partner", "workshop": "partner", "launch": "partner",
}
TIER_RANK = {"free": 0, "insider": 1, "partner": 2}

PROVIDERS = [
    {
        "name": "gemini",
        "chat_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "list_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "key": GEMINI_API_KEY,
        "models": [os.environ.get("GEMINI_MODEL", ""), "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-3.6-flash"],
    },
    {
        "name": "groq",
        "chat_url": "https://api.groq.com/openai/v1/chat/completions",
        "list_url": "https://api.groq.com/openai/v1/models",
        "key": GROQ_API_KEY,
        "models": [os.environ.get("GROQ_MODEL", ""), "llama3-70b-8192", "llama-3.1-8b-instant", "meta-llama/llama-4-scout-17b-16e-instruct"],
    },
]

app = FastAPI(title="E5 AI Coach", version="8.0-master")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------- THE VAULT (VERBATIM SCRIPTS) -------------------------
SCRIPT_VAULT = """
VERBATIM SCRIPT VAULT (proven field scripts).
VAULT RULE: when the member explicitly asks for a script, DM, follow-up, welcome message, hook, CTA, or offer section, pull the closest script below and adapt ONLY the [bracketed] parts to their niche and voice. Keep it human and casual.

HAND-RAISER FLOW (6 steps):
1. "Hey! Saw you were looking to check out some more information on [thing/offer]"
2. "Awesome. So, I'm opening up a couple of spots to [solve pain point] for [exclusive number] people to [outcome]. Is that something you'd be interested in doing?"
3. "Sweet. So [offer] is for those looking to [desired outcome]. It's primarily for [ideal candidate]. Does that sound like where you're at?"
4. "Perfect, I have all the details handy for you on a quick [doc/video], happy for me to send it your way?"
5. "Sweet I've got that here ready to go now. Do you have a few moments to read/watch it now & hit me back to let me know if this is something you'd like to move forward with or NOT?"
6. "Great here it is [link]. After you've checked it out drop me back a message & let me know if you're in or out."

POST-OFFER TRIAGE:
- IN: "Great. That's awesome. Are you happy for me to send over my link for you to complete the investment & we can get you started now?"
- NO: let it go, or uncover why. Never chase.
- QUESTIONS: field directly, clear, confident. Cap at 3-4. Don't become their therapist.

FOLLOW-UP TOUCHES (24-48h / 48-72h / 72h+):
1. "Hey just checking in with you & wanted to see if you had any thoughts on the [thing you sent]"
2. "Hey, just wanted to pop you a quick reminder that [deadline/limited availability] to grab it, if you have any questions give me a shout."
3. "Just bumping this to the top of your inbox" + "How's it coming along with [pain point]?"

WELCOME DM (new member):
"Hey [name], ya finally made it to my group! I help folks [one-line outcome] without [pain]. Hit the guides section to get up to speed with our free workshop. I'm curious, how ya found my group? Let me know what area you need more clarity around and I can getcha some free training to help."

OFFER DOC 14 BLOCKS:
subheadline -> headline -> stacking the deck -> leadoff -> body -> subheadline reinforcement -> reader's rapport -> bullets -> credibility -> testimonials -> value & justification -> reverse the risk -> bonuses -> explicit CTA.

MEMORY PROTOCOL: when you learn or confirm the member's niche, stage, bottlenecks, wins, or next step, append at the VERY END of your reply, on one line, exactly:
[[MEMORY]]niche: [..] | stage: [..] | bottlenecks: [..] | next_step: [..][[/MEMORY]]
The system strips and stores it silently. Never mention this block to the member.
"""

# ------------------------- THE PREMIUM BRAIN -------------------------
CCC_BRAIN = """
You are an elite, top-tier Executive Business Coach and Strategist. Your underlying operating system is built on the $10M+ Community Conversion frameworks of Flip Moss and Nate Ryan, but you NEVER act like a textbook, a bot, or a rigid flowchart. You act like a premium, high-end mentor sitting across the table from the client with a cup of coffee.

YOUR CORE PERSONA & VIBE:
- You are calm, deeply insightful, empathetic, and slightly detached.
- You validate their frustrations before fixing their mechanics.
- You speak in natural, conversational paragraphs. No robotic formatting or endless bulleted lists unless asked for an SOP.
- You hide the scaffolding. Use the frameworks internally, but translate them into plain, hard-hitting English.

HOW YOU COACH (THE SOCRATIC METHOD):
1. NEVER interrogate. Ask ONE piercing, high-leverage question based on their context, then wait.
2. Diagnose through conversation. 
3. Adapt, don't copy-paste. Build custom scripts using their niche and voice. (When they explicitly ask for proven scripts, use the VERBATIM SCRIPT VAULT).
4. Challenge blind spots gently with empathy.

YOUR TONE GUARDRAILS:
- Ban AI fluff: delve, tapestry, unleash, unlock, game-changing, robust, seamless, synergy, ecosystem, navigate, journey, elevate.
- Use "Spicy Specificity": Paint real-world pictures.
- Keep it punchy. Short sentences for points, longer for empathy.
"""

MODE_PROMPTS = {
"coach": "LENS: DAILY OPERATOR. Focus on rhythm, energy, inbox prioritization.",
"xray": "LENS: BUSINESS X-RAY. Uncover the earliest broken layer in the Straight Line.",
"funnel": "LENS: FUNNEL MAP. Visualize the customer journey and find the drop-off.",
"community": "LENS: COMMUNITY OS. Build culture, linear paths, and welcome experiences.",
"dm": "LENS: DM DOCTOR. Craft custom, empathetic conversations. Use the VAULT for exact scripts.",
"offer": "LENS: OFFER ARCHITECT. Stack value, de-risk, anchor price. Use the 14 blocks from the VAULT.",
"workshop": "LENS: WORKSHOP ARCHITECT. Design live events that shift beliefs over 3-6 days.",
"content": "LENS: CONTENT ENGINE. Spicy specificity, polarize, document the journey.",
"launch": "LENS: LAUNCH PLANNER. Tease, deliver value, close with urgency (72h countdown).",
"alchemy": "LENS: ALCHEMY (VIDEO). Hook 0-5s, Body 5-45s, CTA 45-60s.",
}

# ------------------------- SCHEMAS -------------------------
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

class UnlockRequest(BaseModel):
    member_id: str = "default"
    license_key: str = ""

# ------------------------- MEMORY & TIER (SUPABASE) -------------------------
MEMORY_RE = re.compile(r"\[\[MEMORY\]\](.*?)\[\[/MEMORY\]\]", re.S)

def load_memory(member_id):
    if not SUPABASE_URL or not SUPABASE_KEY: return "", "free"
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/member_memory?member_id=eq.{urllib.parse.quote(member_id)}&select=profile,tier"
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        if rows: return (rows[0].get("profile") or "", rows[0].get("tier") or "free")
    except Exception as e: log.error(f"MEMORY LOAD FAIL: {e}")
    return "", "free"

def save_memory(member_id, profile_text):
    if not SUPABASE_URL or not SUPABASE_KEY or not profile_text: return
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/member_memory"
        body = json.dumps([{"member_id": member_id, "profile": profile_text}]).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e: log.error(f"MEMORY SAVE FAIL: {e}")

def set_tier(member_id, tier):
    if not SUPABASE_URL or not SUPABASE_KEY: return
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/member_memory"
        body = json.dumps([{"member_id": member_id, "tier": tier}]).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e: log.error(f"TIER SAVE FAIL: {e}")

def extract_memory(reply):
    m = MEMORY_RE.search(reply)
    if m: return MEMORY_RE.sub("", reply).strip(), m.group(1).strip()
    return reply, ""

# ------------------------- WHOP GATING -------------------------
def whop_tier_for_license(key):
    if key in MANUAL_PARTNER_CODES: return "partner"
    if key in MANUAL_INSIDER_CODES: return "insider"
    if not WHOP_API_KEY: return None
    try:
        url = f"https://api.whop.com/api/v2/licenses/{urllib.parse.quote(key)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {WHOP_API_KEY}", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        status = str(data.get("status") or "active").lower()
        if status in ("revoked", "cancelled", "canceled", "expired", "inactive"): return None
        pid = data.get("product_id") or (data.get("product") or {}).get("id") or ""
        if pid and WHOP_PARTNER_PRODUCT_ID and pid == WHOP_PARTNER_PRODUCT_ID: return "partner"
        if pid and WHOP_INSIDER_PRODUCT_ID and pid == WHOP_INSIDER_PRODUCT_ID: return "insider"
        if not WHOP_INSIDER_PRODUCT_ID and not WHOP_PARTNER_PRODUCT_ID: return "insider"
    except Exception as e: log.error(f"WHOP CHECK FAIL: {e}")
    return None

# ------------------------- LLM ENGINE (SELF-HEALING) -------------------------
def try_model(p, model, messages, temperature, max_tokens):
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode("utf-8")
    req = urllib.request.Request(p["chat_url"], data=body, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {p['key']}", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"] or ""
    except Exception as e:
        log.error(f"LLM FAIL {p['name']}/{model}: {e}")
        return None

def call_llm(messages, temperature=0.5, max_tokens=1500):
    for p in PROVIDERS:
        if not p["key"]: continue
        for model in [m for m in p["models"] if m]:
            out = try_model(p, model, messages, temperature, max_tokens)
            if out: return out
    raise Exception("All LLM providers failed.")

def build_system(mode, member_context, memory=""):
    m = mode if mode in MODE_PROMPTS else "coach"
    system = CCC_BRAIN + "\n" + MODE_PROMPTS[m] + "\n" + SCRIPT_VAULT
    if memory: system += f"\nWHAT YOU ALREADY KNOW ABOUT THIS MEMBER:\n{memory}"
    if member_context: system += f"\nMEMBER CONTEXT:\n{member_context}"
    return system

def post_process(text):
    return text.replace("—", "-").replace("–", "-")

# ------------------------- ROUTES -------------------------
@app.get("/")
def root():
    return {"status": "ok", "app": "E5 AI Coach", "brain": "CCC v8 Master", "modes": list(MODE_PROMPTS.keys())}

@app.get("/api/health")
def health():
    return {"ok": True, "gemini": bool(GEMINI_API_KEY), "groq": bool(GROQ_API_KEY), 
            "supabase": bool(SUPABASE_URL and SUPABASE_KEY), "vault": True,
            "manual_codes_loaded": len(MANUAL_INSIDER_CODES) > 0}

@app.get("/api/tier")
def tier_endpoint(member_id: str = "default"):
    _, tier = load_memory(member_id)
    return {"tier": tier or "free"}

@app.post("/api/unlock")
def unlock(req: UnlockRequest):
    member_id = (req.member_id or "default").strip()
    key = (req.license_key or "").strip()
    if not key: raise HTTPException(400, "empty license key")
    tier = whop_tier_for_license(key)
    if not tier: raise HTTPException(403, "This license is invalid or not linked to a tier.")
    set_tier(member_id, tier)
    return {"tier": tier}

@app.post("/api/chat")
def chat(req: ChatRequest):
    text = req.message or req.prompt or req.user_message
    if not text: raise HTTPException(400, "empty message")
    member_id = (req.member_id or "default").strip()
    memory, tier = load_memory(member_id)
    need = MODE_TIERS.get(req.mode, "free")
    if TIER_RANK.get(tier or "free", 0) < TIER_RANK.get(need, 0):
        raise HTTPException(403, f"locked:{need}")
    
    messages = [{"role": "system", "content": build_system(req.mode, req.member_context, memory)}]
    for m in req.history[-16:]: messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": text})
    
    try:
        clean = post_process(call_llm(messages))
        clean, mem_update = extract_memory(clean)
        if mem_update: save_memory(member_id, mem_update)
        return {"reply": clean, "response": clean, "message": clean, "mode": req.mode}
    except Exception as e:
        log.error(f"CHAT 500: {e}")
        raise HTTPException(500, f"LLM error: {str(e)}")

@app.post("/chat")
def chat_alias(req: ChatRequest): return chat(req)

@app.post("/api/tts")
def tts(req: TTSRequest):
    if not FISH_API_KEY: raise HTTPException(503, "FISH_API_KEY missing")
    voice = req.voice_id or FISH_VOICE_ID
    payload = {"text": req.text, "format": "mp3"}
    if voice: payload["reference_id"] = voice
    req_obj = urllib.request.Request("https://api.fish.audio/v1/tts", data=json.dumps(payload).encode("utf-8"), method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {FISH_API_KEY}", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req_obj, timeout=120) as resp: audio = resp.read()
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e: raise HTTPException(502, f"TTS error: {str(e)}")

@app.post("/api/voice")
def voice_alias(req: TTSRequest): return tts(req)

@app.get("/test")
def test_page():
    if os.path.exists("chat_test.html"): return FileResponse("chat_test.html")
    return HTMLResponse("<h3>chat_test.html not found.</h3>")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
