import os
import time
import logging
import threading
import urllib.request
import json
from typing import List, Optional, Dict
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

# --- ENV VARS ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# --- IN-MEMORY DATABASE (Replaces Supabase for now) ---
PROFILES_DB = {}
JOURNEY_DB = {}

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
CHAT_LIMIT = RateLimiter(50, 3600)

app = FastAPI(title="E5 AI Coach OS", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- JOURNEY MAP ---
JOURNEY_MAP = {
    "Phase 1": {
        "name": "Foundation", "days": "1-30", "focus": "Offer, Avatar, and First Content",
        "tasks": [
            {"id": "p1_t1", "name": "Define Core Offer & Value Stack", "deadline_day": 3},
            {"id": "p1_t2", "name": "Identify Target Avatar & Pain Points", "deadline_day": 7},
            {"id": "p1_t3", "name": "Create First Content Piece", "deadline_day": 14},
            {"id": "p1_t4", "name": "Write & Test DM Outreach Template", "deadline_day": 21}
        ]
    },
    "Phase 2": {
        "name": "Traffic", "days": "31-60", "focus": "Inbound/Outbound Systems",
        "tasks": [
            {"id": "p2_t1", "name": "Double Content Volume", "deadline_day": 37},
            {"id": "p2_t2", "name": "Build Inbound System", "deadline_day": 45},
            {"id": "p2_t3", "name": "Launch Outbound DM System", "deadline_day": 52},
            {"id": "p2_t4", "name": "Fill Weekly Traffic Tracker", "deadline_day": 60}
        ]
    },
    "Phase 3": {
        "name": "Conversion", "days": "61-90", "focus": "Optimization and Scaling",
        "tasks": [
            {"id": "p3_t1", "name": "Funnel Hack 3 Competitors", "deadline_day": 67},
            {"id": "p3_t2", "name": "Rebuild Offer Doc", "deadline_day": 75},
            {"id": "p3_t3", "name": "Optimize Landing Page", "deadline_day": 82},
            {"id": "p3_t4", "name": "Execute Full Launch Plan", "deadline_day": 90}
        ]
    }
}

# --- LLM ENGINE ---
def call_llm(messages: List[Dict], temperature: float = 0.3) -> str:
    api_key = GROQ_API_KEY if GROQ_API_KEY else GEMINI_API_KEY
    if not api_key:
        return "Error: No API keys configured in Railway."
    
    url = "https://api.groq.com/openai/v1/chat/completions" if GROQ_API_KEY else "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    model = "llama-3.1-70b-versatile" if GROQ_API_KEY else "gemini-2.0-flash"
    
    try:
        payload = json.dumps({"model": model, "messages": messages, "temperature": temperature}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]
    except Exception as e:
        log.error(f"LLM Error: {e}")
        return f"Error: LLM failed. {str(e)}"

# --- PYDANTIC MODELS ---
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
    current_task_id: str
    tasks_completed: List[str] = []
    asset_links: List[str] = []
    asset_text: str = ""
    metrics: str = ""

# --- ROUTES ---
@app.get("/")
def root():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return {"status": "ok"}

@app.get("/api/check-onboarding")
def check_onboarding(member_id: str = "default"):
    profile = PROFILES_DB.get(member_id)
    return {"onboarded": profile is not None, "profile": profile}

@app.post("/api/onboarding")
def submit_onboarding(req: OnboardingRequest):
    PROFILES_DB[req.member_id] = req.model_dump()
    JOURNEY_DB[req.member_id] = {
        "current_day": 1, "current_phase": "Phase 1", "current_task_id": "p1_t1", 
        "tasks_completed": [], "standup_history": []
    }
    return {"success": True}

@app.get("/api/journey")
def get_journey_status(member_id: str = "default"):
    journey = JOURNEY_DB.get(member_id, {
        "current_day": 1, "current_phase": "Phase 1", "current_task_id": "p1_t1", 
        "tasks_completed": [], "standup_history": []
    })
    profile = PROFILES_DB.get(member_id, {})
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    current_task = next((t for t in phase_info["tasks"] if t["id"] == journey["current_task_id"]), phase_info["tasks"][0])
    progress_percent = min(100, max(1, (journey["current_day"] / 90) * 100))
    
    return {
        "current_day": journey["current_day"],
        "current_phase": phase_info["name"],
        "phase_days": phase_info["days"],
        "focus": phase_info["focus"],
        "current_task": current_task,
        "tasks_completed_count": len(journey["tasks_completed"]),
        "progress_percent": round(progress_percent, 1),
        "all_phases": {k: {"name": v["name"], "tasks": [t["name"] for t in v["tasks"]]} for k, v in JOURNEY_MAP.items()}
    }

@app.post("/api/standup")
def submit_standup(req: StandupRequest):
    profile = PROFILES_DB.get(req.member_id)
    if not profile:
        raise HTTPException(403, "Complete onboarding first.")
    
    journey = JOURNEY_DB.get(req.member_id, {
        "current_day": 1, "current_phase": "Phase 1", "current_task_id": "p1_t1", 
        "tasks_completed": [], "standup_history": []
    })
    
    system = f"""You are a STRICT Chief Operating Officer. 
    The user is submitting work for: {req.current_task_id}
    Grade their submission out of 10. Be specific.
    USER CONTEXT: {json.dumps(profile)}
    OUTPUT FORMAT:
    1. GRADE: [Score]/10
    2. AUDIT: What is missing.
    3. NEXT STEP: If score >= 7, tell them the NEXT task. If < 7, tell them what to fix."""
    
    prompt = f"Tasks: {req.tasks_completed}\nLinks: {req.asset_links}\nWork Text: {req.asset_text}\nMetrics: {req.metrics}"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    review = call_llm(messages)
    
    if req.current_task_id not in journey["tasks_completed"]:
        journey["tasks_completed"].append(req.current_task_id)
        journey["current_day"] = min(90, journey["current_day"] + 7)
        if journey["current_phase"] == "Phase 1" and len(journey["tasks_completed"]) >= 4:
            journey["current_phase"] = "Phase 2"
            journey["current_task_id"] = "p2_t1"
        elif journey["current_phase"] == "Phase 2" and len(journey["tasks_completed"]) >= 8:
            journey["current_phase"] = "Phase 3"
            journey["current_task_id"] = "p3_t1"
            
    journey["standup_history"].append({"date": datetime.now().isoformat(), "task": req.current_task_id, "review": review})
    JOURNEY_DB[req.member_id] = journey
    
    return {"success": True, "review": review, "journey_updated": True}

@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.message:
        raise HTTPException(400, "empty message")
    if not CHAT_LIMIT.allow(req.member_id or "default"):
        raise HTTPException(429, "Rate limit reached")
    
    profile = PROFILES_DB.get(req.member_id or "default")
    if not profile:
        raise HTTPException(403, "GATEKEEPER: Please complete onboarding first.")
    
    journey = JOURNEY_DB.get(req.member_id or "default", {
        "current_day": 1, "current_phase": "Phase 1", "current_task_id": "p1_t1", 
        "tasks_completed": [], "standup_history": []
    })
    
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    current_task = next((t for t in phase_info["tasks"] if t["id"] == journey["current_task_id"]), phase_info["tasks"][0])
    
    task_is_completed = journey["current_task_id"] in journey["tasks_completed"]
    last_standup = journey["standup_history"][-1] if journey["standup_history"] else None
    
    if not task_is_completed and not last_standup:
        return {
            "reply": f"""🛑 **STRICT ACCOUNTABILITY GATE TRIGGERED**
You are on Day {journey['current_day']} of {phase_info['name']}.
Your ONLY focus right now is:
🎯 {current_task['name']} (Deadline: Day {current_task['deadline_day']})
I cannot give you new strategic advice until you prove execution on this exact task.
 Action Required: Click the 'Submit Daily Work' button, paste what you have done for this task, and let me grade it."""
        }
    
    system_prompt = f"""
You are the E5 AI Coach, an elite, proactive Chief Operating Officer.
The user is currently on **Day {journey['current_day']}** of **{phase_info['name']}**.
Their current mandatory focus is: **{current_task['name']}**.
STRICT RULE: Focus on digital products, Whop, content marketing.
USER CONTEXT:
- Niche: {profile.get('niche', 'N/A')}
- Avatar: {profile.get('target_avatar', 'N/A')}
- Bottleneck: {profile.get('biggest_bottleneck', 'N/A')}
INSTRUCTIONS: Be calm, deeply insightful, authoritative. Short punchy sentences. ZERO AI FLUFF.
"""
    messages = [{"role": "system", "content": system_prompt}]
    for m in req.history[-10:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})
    
    reply = call_llm(messages)
    return {"reply": reply}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
