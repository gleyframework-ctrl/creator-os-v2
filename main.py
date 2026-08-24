"""
E5 AI COACH - main.py (FINAL PRODUCTION BUILD)
Fused Quindecillion Brain + Gatekeeper + Daily Standup
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
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# --- RATE LIMITER ---
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

CHAT_LIMIT = RateLimiter(30, 3600)

# --- APP SETUP ---
app = FastAPI(title="E5 AI Coach OS", version="Final")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ==============================================================================
# 🧠 THE QUINDECILLION MASTER BRAIN (Fused Frameworks)
# ==============================================================================
MASTER_BRAIN = """
You are the E5 AI Coach, a proactive Chief Operating Officer operating at the Quindecillion level.
Your knowledge is a perfectly fused matrix of:
1. Alex Hormozi: Value Equation, $100M Offers/Leads/Money Models, Core 4, Rule of 100.
2. Ryan Levesque (ASK Method): Band-Aid vs Cure, Type/Killer/Score Quizzes, Deep Dive Surveys, Buckets.
3. Ryan Deiss (DigitalMarketer): Customer Value Journey (8 stages), Ready Now Funnel, Growth Flywheel, Triple Double.
4. Dan Lok & Chris Do: High-Ticket Closing, Socratic Six, GEM Theory, Objection Handling.
5. Miguel Alvarez & Jason Fox: S.I.P.E. DM Framework, 3-Stage Conversation, Ladder of Yeses.
6. Todd Brown & Paul Mascetta: A-Z Copywriting, Big Idea, Neurochemical Persuasion (WOMP).
7. Jessica DeRose & Jim Hamilton: Magnetic Messaging, S.L.P.C. Email Storyselling.
8. Laura Meyer & Roland Frasier: Fractional Consulting, 63-Step Profit Optimizer, E2P.

YOUR PRIME DIRECTIVES:
1. GATEKEEPER: Never give generic advice. Anchor every response to the user's specific niche, avatar, and bottleneck stored in their profile.
2. ACCOUNTABILITY: If the user hasn't submitted their Daily Standup, remind them. Review their submitted work before giving new tasks.
3. DIAGNOSE BEFORE PRESCRIBING: Use the Customer Value Journey to find the exact broken stage.
4. SPICY SPECIFICITY: Use real-world examples. No AI fluff.
5. DYNAMIC ROUTING: Automatically select the exact framework needed (e.g., if they lack leads, prescribe ASK Method Quiz; if they can't close, prescribe Socratic Six).

YOUR TONE:
- Calm, deeply insightful, slightly detached, authoritative.
- Short punchy sentences for actions.
- Banned words: delve, tapestry, unleash, unlock, game-changing, robust, seamless, synergy.
"""

MODE_PROMPTS = {
    "coach": "LENS: DAILY OPERATOR. Focus on rhythm, Rule of 100, and daily task completion.",
    "quiz": "LENS: ASK METHOD ARCHITECT. Force user to define Cure vs Band-Aid. Generate Type/Killer/Score hooks and Buckets.",
    "dm": "LENS: DM DOCTOR. Use S.I.P.E. framework. Classify lead temperature. Guide through 3-Stage Conversation.",
    "offer": "LENS: OFFER ARCHITECT. Stack value using Value Equation. Build Grand Slam Offers.",
    "xray": "LENS: BUSINESS X-RAY. Map user's CVJ stage. Find earliest broken layer. Score RED/YELLOW/GREEN.",
    "content": "LENS: CONTENT ENGINE. Use S.L.P.C. framework for emails. Use 4 Hook Components for short-form video.",
    "sales": "LENS: HIGH-TICKET CLOSER. Use 9-Step Script and GEM Theory. Handle objections with Socratic Six."
}

# ==============================================================================
# 📊 PYDANTIC MODELS
# ==============================================================================
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
# In production, replace these with actual Supabase calls. 
# For this build, we use a local JSON file or memory for demonstration if Supabase is missing.
MEMORY_STORE = {}

def get_profile(member_id: str) -> Optional[Dict]:
    return MEMORY_STORE.get(f"profile_{member_id}")

def save_profile(member_id: str, data: Dict):
    MEMORY_STORE[f"profile_{member_id}"] = data

def get_standup(member_id: str) -> Optional[Dict]:
    return MEMORY_STORE.get(f"standup_{member_id}")

def save_standup(member_id: str, data: Dict):
    MEMORY_STORE[f"standup_{member_id}"] = data

# ==============================================================================
# 🤖 LLM ENGINE
# ==============================================================================
def call_llm(messages: List[Dict], temperature: float = 0.5) -> str:
    # Simple failover logic
    providers = [
        {"name": "gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "key": GEMINI_API_KEY, "model": "gemini-2.0-flash"},
        {"name": "groq", "url": "https://api.groq.com/openai/v1/chat/completions", "key": GROQ_API_KEY, "model": "llama-3.1-70b-versatile"}
    ]
    
    for p in providers:
        if not p["key"]: continue
        try:
            body = json.dumps({"model": p["model"], "messages": messages, "temperature": temperature}).encode("utf-8")
            req = urllib.request.Request(p["url"], data=body, method="POST", headers={
                "Content-Type": "application/json", "Authorization": f"Bearer {p['key']}"
            })
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            log.error(f"LLM Error ({p['name']}): {e}")
            continue
    return "Error: All LLM providers failed. Please check API keys."

# ==============================================================================
# 🛣️ ROUTES
# ==============================================================================
@app.get("/")
def root():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return {"status": "ok", "app": "E5 AI Coach OS"}

@app.get("/api/check-onboarding")
def check_onboarding(member_id: str = "default"):
    profile = get_profile(member_id)
    return {"onboarded": profile is not None, "profile": profile}

@app.post("/api/onboarding")
def submit_onboarding(req: OnboardingRequest):
    save_profile(req.member_id, req.dict())
    return {"success": True, "message": "Onboarding complete. AI Coach activated."}

@app.post("/api/standup")
def submit_standup(req: StandupRequest):
    profile = get_profile(req.member_id)
    if not profile:
        raise HTTPException(403, "Complete onboarding first.")
    
    save_standup(req.member_id, req.dict())
    
    # AI Review of Standup
    system = f"{MASTER_BRAIN}\n\nUSER PROFILE: {json.dumps(profile)}"
    prompt = f"""
    The user just submitted their Daily Standup:
    Tasks: {req.tasks_completed}
    Links: {req.asset_links}
    Work Text: {req.asset_text}
    Metrics: {req.metrics}
    
    Act as a strict COO. Review their work. Grade it out of 10. 
    Tell them exactly what they did wrong or right based on the frameworks.
    Give them ONE specific task to do next.
    """
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    review = call_llm(messages)
    return {"success": True, "review": review}

@app.post("/api/chat")
def chat(req: ChatRequest):
    if not CHAT_LIMIT.allow(req.member_id or "default"):
        raise HTTPException(429, "Rate limit reached.")
        
    profile = get_profile(req.member_id or "default")
    if not profile:
        raise HTTPException(403, "GATEKEEPER: Please complete the onboarding quiz first.")
        
    standup = get_standup(req.member_id or "default")
    
    # Build Context
    context = f"USER PROFILE: {json.dumps(profile)}\n"
    if standup:
        context += f"LATEST STANDUP: {json.dumps(standup)}\n"
        
    system = f"{MASTER_BRAIN}\n\n{context}\n\nCURRENT MODE: {MODE_PROMPTS.get(req.mode, '')}"
    
    messages = [{"role": "system", "content": system}]
    for m in req.history[-10:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})
    
    reply = call_llm(messages)
    return {"reply": reply}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
