"""
E5 AI COACH - main.py (BUSINESS OS EDITION)
Proactive Business Operating System. Tracks progress, predicts bottlenecks, and drives daily execution.
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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# --- VAULT IMPORT ---
try:
    from vault import SCRIPT_VAULT
except Exception:
    SCRIPT_VAULT = ""

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
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

_DEFAULT_ORIGINS = "https://e5-ai-coach-production.up.railway.app,http://localhost:8000,http://127.0.0.1:8000"
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]

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

CHAT_LIMIT = AdvancedRateLimiter(50, 3600)

# --- FASTAPI APP SETUP ---
app = FastAPI(title="E5 Business OS", version="5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# THE QUINDECILLION OS BRAIN (PROACTIVE COO)
# ==============================================================================
CCC_BRAIN = """
You are the E5 Business OS, an elite Chief Operating Officer and Executive Strategist. You are NOT a passive chatbot. You are a proactive, predictive, and prescriptive operating system for the user's business.

YOUR CORE DIRECTIVES:
1. PROACTIVE MANAGEMENT: Do not just answer questions. Drive the user's day. Ask what they accomplished, predict bottlenecks, and assign the next critical task.
2. CONTEXT AWARENESS: You must know their exact business stage (e.g., Stage 1: Monetize, Stage 2: Advertise). Tailor all advice to their current stage.
3. FRAMEWORK INTEGRATION: Automatically apply the correct framework (Hormozi Value Equation, TTB Straight Line, AVOCADO ECAFI, E5 Core) based on the task.
4. PREDICTIVE ANALYSIS: Look at their inputs (leads, conversions, tasks) and predict where they will fail next week. Warn them now.
5. DAILY EXECUTION: Give them exactly 3 critical tasks for the day. No more, no less. Tell them exactly what to focus on.

YOUR TONE:
Calm, deeply insightful, authoritative, and slightly detached. Short punchy sentences for actions. No AI fluff. 

INTERNAL KNOWLEDGE BASE (USE DYNAMICALLY):
- HORMOZI: Value Equation, Money Models (Attraction, Upsell, Downsell, Continuity), Core 4, Rule of 100.
- TTB: Straight Line, TRUST formula, Brand Clarity, Community OS.
- AVOCADO: ECAFI (Engage, Connect, Assess, Frame, Invite), SOULFUL scripts, R.I.P.E. Lead Magnets.
- E5: Core frameworks, daily execution, predictive scaling.
"""

MODE_PROMPTS = {
    "coach": "LENS: DAILY OPERATOR. Focus on today's 3 critical tasks, progress tracking, and removing today's bottleneck.",
    "xray": "LENS: BUSINESS X-RAY. Find the earliest broken layer. Score stages RED/YELLOW/GREEN. Fix the leaky bucket.",
    "funnel": "LENS: FUNNEL MAP. Visualize the customer journey. Apply Value Equation to reduce friction.",
    "community": "LENS: COMMUNITY OS. Build culture, linear paths, and welcome experiences. Belonging > Value.",
    "dm": "LENS: DM DOCTOR. Classify signal. Use ECAFI & SOULFUL scripts. Diagnose, don't pitch.",
    "offer": "LENS: OFFER ARCHITECT. Stack value, de-risk, anchor price. Build Grand Slam Offers using Value Equation.",
    "workshop": "LENS: WORKSHOP ARCHITECT. Design 6-day belief arc. Install 4 beliefs.",
    "content": "LENS: CONTENT ENGINE. Spicy specificity, polarize, document journey. Use 7 Content Types.",
    "launch": "LENS: LAUNCH PLANNER. 21-day map: Pre-promo -> Promo -> Drop -> Push -> 72h countdown.",
    "alchemy": "LENS: ALCHEMY (VIDEO). Hook 0-5s, Body 5-45s, CTA 45-60s.",
    "hack": "LENS: FUNNEL HACKER. Reverse-engineer competitor funnel. Score RED/YELLOW/GREEN.",
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
    member_id: Optional[str] = "default"

class TaskLogRequest(BaseModel):
    member_id: str = "default"
    task: str
    completed: bool = True

class DashboardRequest(BaseModel):
    member_id: str = "default"

# --- SUPABASE MEMORY & STATE ---
MEMORY_RE = re.compile(r"[{1,2}\sMEMORY\s]{1,2}(.*?)(?:[{1,2}\s/\sMEMORY\s]{1,2}|$)", re.S)

def load_memory(member_id: str) -> tuple[str, str]:
    if not SUPABASE_URL or not SUPABASE_KEY: return "", "free"
    try:
        url = (SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory?member_id=eq." 
               + urllib.parse.quote(member_id) + "&select=profile,tier")
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY})
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
            if rows: return (rows[0].get("profile") or "", rows[0].get("tier") or "free")
    except Exception as e: log.error("MEMORY LOAD FAIL: %s", e)
    return "", "free"

def save_memory(member_id: str, profile_text: str):
    if not SUPABASE_URL or not SUPABASE_KEY or not profile_text: return
    try:
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/member_memory"
        body = json.dumps([{"member_id": member_id, "profile": profile_text}]).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
            "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e: log.error("MEMORY SAVE FAIL: %s", e)

def extract_memory(reply: str) -> tuple[str, str]:
    m = MEMORY_RE.search(reply)
    if m: return MEMORY_RE.sub("", reply).strip(), m.group(1).strip()
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
    providers = [
        {"name": "gemini", "chat_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "key": GEMINI_API_KEY, "models": ["gemini-2.0-flash", "gemini-1.5-flash"]},
        {"name": "groq", "chat_url": "https://api.groq.com/openai/v1/chat/completions", "key": GROQ_API_KEY, "models": ["llama-3.1-70b-versatile", "llama3-70b-8192"]},
    ]
    for provider in providers:
        if not provider["key"]: continue
        for model in provider["models"]:
            if not model: continue
            result = try_model(provider, model, messages, temperature, max_tokens)
            if result: return result
    raise Exception("All LLM providers failed")

def build_system(mode: str, member_context: str, memory: str = "", docs: str = "") -> str:
    m = mode if mode in MODE_PROMPTS else "coach"
    system = CCC_BRAIN + "\n" + MODE_PROMPTS[m]
    if SCRIPT_VAULT: system += "\n" + SCRIPT_VAULT
    if docs: system += "\n\nMEMBER'S DOCS:\n" + docs
    if memory: system += "\n\nCURRENT BUSINESS STATE & PROGRESS:\n" + memory
    if member_context: system += "\n\nMEMBER CONTEXT:\n" + member_context
    return system

# --- ROUTES ---
@app.get("/")
def root():
    if os.path.exists("chat_test.html"): return FileResponse("chat_test.html")
    return {"status": "ok", "app": "E5 Business OS"}

@app.post("/api/chat")
def chat(req: ChatRequest):
    text = req.message or req.prompt or req.user_message
    if not text: raise HTTPException(400, "empty message")
    
    member_id = (req.member_id or "default").strip()
    if not CHAT_LIMIT.allow(member_id): raise HTTPException(429, "Rate limit reached")
    
    memory, tier = load_memory(member_id)
    messages = [{"role": "system", "content": build_system(req.mode, "", memory)}]
    for m in req.history[-10:]: messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": text})
    
    try:
        clean = call_llm(messages)
        clean, mem_update = extract_memory(clean)
        if mem_update: save_memory(member_id, mem_update)
        return {"reply": clean, "mode": req.mode}
    except Exception as e:
        log.error("CHAT 500: %s", e)
        raise HTTPException(500, f"LLM error: {str(e)}")

@app.post("/api/log-task")
def log_task(req: TaskLogRequest):
    """Logs a task and asks the AI to update the daily plan."""
    member_id = (req.member_id or "default").strip()
    memory, _ = load_memory(member_id)
    
    prompt = f"User just completed this task: '{req.task}'. Update their progress. What is the NEXT critical task they must do today based on their current business stage? Give them exactly ONE next task. Keep it under 50 words."
    
    messages = [{"role": "system", "content": build_system("coach", "", memory)}, {"role": "user", "content": prompt}]
    
    try:
        response = call_llm(messages)
        # Append to memory
        new_memory = f"{memory}\n[LOGGED TASK]: {req.task} (Completed: {req.completed})"
        save_memory(member_id, new_memory)
        return {"reply": response}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/test")
def test_page():
    if os.path.exists("chat_test.html"): return FileResponse("chat_test.html")
    return HTMLResponse("<h3>chat_test.html not found</h3>")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
