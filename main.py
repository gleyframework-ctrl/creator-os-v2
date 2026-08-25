"""
E5 AI COACH OS - main.py (STRICT EXECUTION EDITION)
RAG-Powered, Journey-Aware, Accountability-First Backend
"""
import os
import time
import logging
import threading
import urllib.request
import urllib.error
import json
from typing import List, Optional, Dict, Any
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

CHAT_LIMIT = RateLimiter(50, 3600)

app = FastAPI(title="E5 AI Coach OS | Strict Execution", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ==============================================================================
# 🗺️ THE 90-DAY JOURNEY MAP (Strict Execution Timeline)
# ==============================================================================
JOURNEY_MAP = {
    "Phase 1": {
        "name": "Foundation",
        "days": "1-30",
        "focus": "Offer, Avatar, and First Content",
        "tasks": [
            {"id": "p1_t1", "name": "Define Core Offer & Value Stack", "deadline_day": 3},
            {"id": "p1_t2", "name": "Identify Target Avatar & Pain Points", "deadline_day": 7},
            {"id": "p1_t3", "name": "Create First Content Piece (Video/Post)", "deadline_day": 14},
            {"id": "p1_t4", "name": "Write & Test DM Outreach Template", "deadline_day": 21}
        ]
    },
    "Phase 2": {
        "name": "Traffic",
        "days": "31-60",
        "focus": "Inbound/Outbound Systems and Volume",
        "tasks": [
            {"id": "p2_t1", "name": "Double Content Volume & Pick Primary Platform", "deadline_day": 37},
            {"id": "p2_t2", "name": "Build Inbound System (Comments to DMs)", "deadline_day": 45},
            {"id": "p2_t3", "name": "Launch Outbound Cold DM/Email System", "deadline_day": 52},
            {"id": "p2_t4", "name": "Fill Weekly Traffic Tracker with Real Data", "deadline_day": 60}
        ]
    },
    "Phase 3": {
        "name": "Conversion",
        "days": "61-90",
        "focus": "Optimization, Funnel Hacking, and Scaling",
        "tasks": [
            {"id": "p3_t1", "name": "Funnel Hack 3 Competitors & Submit Report", "deadline_day": 67},
            {"id": "p3_t2", "name": "Rebuild Offer Doc with Real Conversion Data", "deadline_day": 75},
            {"id": "p3_t3", "name": "Optimize Landing Page Conversion Rate", "deadline_day": 82},
            {"id": "p3_t4", "name": "Execute Full Launch Plan", "deadline_day": 90}
        ]
    }
}

# ==============================================================================
# 🧠 GOOGOL-PLEX RAG RETRIEVAL ENGINE
# ==============================================================================
def get_gemini_embedding(text: str) -> Optional[List[float]]:
    if not GEMINI_API_KEY: return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={GEMINI_API_KEY}"
        payload = json.dumps({"model": "models/text-embedding-004", "content": {"parts": [{"text": text}]}}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))["embedding"]["values"]
    except Exception as e:
        log.error(f"Embedding Error: {e}")
        return None

def retrieve_relevant_context(user_query: str, top_k: int = 4) -> str:
    if not SUPABASE_URL or not SUPABASE_KEY: return ""
    embedding = get_gemini_embedding(user_query)
    if not embedding: return ""

    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/rpc/match_chunks"
        payload = json.dumps({"query_embedding": embedding, "match_count": top_k}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers={
            "Content-Type": "application/json", "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.loads(resp.read().decode("utf-8"))
            
        context = "\n\n--- RETRIEVED EXPERT FRAMEWORKS ---\n"
        for row in results:
            context += f"\n[Source: {row.get('framework_name', 'Unknown')}]\n{row.get('content', '')}\n"
        return context + "--- END RETRIEVED CONTEXT ---\n"
    except Exception as e:
        log.error(f"RAG Retrieval Error: {e}")
        return ""

# ==============================================================================
# 📊 PYDANTIC MODELS & MEMORY
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
    current_task_id: str  # The specific task they are submitting work for
    tasks_completed: List[str] = []
    asset_links: List[str] = []
    asset_text: str = ""
    metrics: str = ""

MEMORY_STORE = {}

def get_profile(mid: str) -> Optional[Dict]: 
    return MEMORY_STORE.get(f"profile_{mid}")

def save_profile(mid: str, data: Dict): 
    MEMORY_STORE[f"profile_{mid}"] = data

def get_journey(mid: str) -> Dict:
    """Returns the user's current journey status."""
    default_journey = {
        "current_day": 1,
        "current_phase": "Phase 1",
        "current_task_id": "p1_t1",
        "tasks_completed": [],
        "standup_history": []
    }
    return MEMORY_STORE.get(f"journey_{mid}", default_journey)

def save_journey(mid: str, data: Dict):
    MEMORY_STORE[f"journey_{mid}"] = data

# ==============================================================================
# 🤖 LLM ENGINE
# ==============================================================================
def call_llm(messages: List[Dict], temperature: float = 0.3) -> str:
    providers = [
        {"name": "gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "key": GEMINI_API_KEY, "model": "gemini-2.0-flash"},
        {"name": "groq", "url": "https://api.groq.com/openai/v1/chat/completions", "key": GROQ_API_KEY, "model": "llama-3.1-70b-versatile"}
    ]
    for p in providers:
        if not p["key"]: continue
        try:
            body = json.dumps({"model": p["model"], "messages": messages, "temperature": temperature}).encode("utf-8")
            req = urllib.request.Request(p["url"], data=body, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {p['key']}"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]
        except Exception as e:
            log.error(f"LLM Error ({p['name']}): {e}")
            continue
    return "Error: All LLM providers failed."

# ==============================================================================
# 🛣️ ROUTES
# ==============================================================================
@app.get("/")
def root():
    if os.path.exists("chat_test.html"): return FileResponse("chat_test.html")
    return {"status": "ok"}

@app.get("/api/check-onboarding")
def check_onboarding(member_id: str = "default"):
    profile = get_profile(member_id)
    return {"onboarded": profile is not None, "profile": profile}

@app.post("/api/onboarding")
def submit_onboarding(req: OnboardingRequest):
    save_profile(req.member_id, req.dict())
    # Initialize Journey at Day 1, Phase 1, Task 1
    save_journey(req.member_id, {
        "current_day": 1,
        "current_phase": "Phase 1",
        "current_task_id": "p1_t1",
        "tasks_completed": [],
        "standup_history": []
    })
    return {"success": True}

@app.get("/api/journey")
def get_journey_status(member_id: str = "default"):
    """Provides structured data for the frontend visual timeline."""
    journey = get_journey(member_id)
    profile = get_profile(member_id) or {}
    
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    current_task = next((t for t in phase_info["tasks"] if t["id"] == journey["current_task_id"]), phase_info["tasks"][0])
    
    # Calculate visual progress (1 to 90 days)
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
    profile = get_profile(req.member_id)
    if not profile: raise HTTPException(403, "Complete onboarding first.")
    
    journey = get_journey(req.member_id)
    
    # 1. Grade the work against the specific framework
    rag_context = retrieve_relevant_context(f"Grade this work for task: {req.current_task_id}. Content: {req.asset_text}")
    
    system = f"""You are a STRICT Chief Operating Officer. 
    The user is submitting work for: {req.current_task_id}
    Grade their submission out of 10 based on the expert frameworks retrieved below.
    Be specific, critical, and actionable. 
    
    USER CONTEXT: {json.dumps(profile)}
    EXPERT FRAMEWORKS FOR GRADING: {rag_context}
    
    OUTPUT FORMAT:
    1. 📊 GRADE: [Score]/10
    2. 🔍 AUDIT: What is missing or wrong based on the frameworks.
    3. ✅ NEXT STEP: If score >= 7, congratulate them and tell them the NEXT task to focus on. If score < 7, tell them exactly what to fix before resubmitting.
    """
    
    prompt = f"Tasks: {req.tasks_completed}\nLinks: {req.asset_links}\nWork Text: {req.asset_text}\nMetrics: {req.metrics}"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    review = call_llm(messages)
    
    # 2. Update Journey if they passed (Score >= 7 assumed if no explicit fail, simplified for this demo)
    # In a real app, you'd parse the score from the LLM response. Here we assume submission = progress for the prototype.
    if req.current_task_id not in journey["tasks_completed"]:
        journey["tasks_completed"].append(req.current_task_id)
        journey["current_day"] = min(90, journey["current_day"] + 7) # Advance ~1 week per completed task
        
        # Simple phase advancement logic
        if journey["current_phase"] == "Phase 1" and len(journey["tasks_completed"]) >= 4:
            journey["current_phase"] = "Phase 2"
            journey["current_task_id"] = "p2_t1"
        elif journey["current_phase"] == "Phase 2" and len(journey["tasks_completed"]) >= 8:
            journey["current_phase"] = "Phase 3"
            journey["current_task_id"] = "p3_t1"
            
    journey["standup_history"].append({"date": datetime.now().isoformat(), "task": req.current_task_id, "review": review})
    save_journey(req.member_id, journey)
    
    return {"success": True, "review": review, "journey_updated": True}

@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.message: raise HTTPException(400, "empty message")
    if not CHAT_LIMIT.allow(req.member_id or "default"): raise HTTPException(429, "Rate limit reached")
    
    profile = get_profile(req.member_id or "default")
    if not profile: raise HTTPException(403, "GATEKEEPER: Please complete onboarding first.")
    
    journey = get_journey(req.member_id or "default")
    phase_info = JOURNEY_MAP[journey["current_phase"]]
    current_task = next((t for t in phase_info["tasks"] if t["id"] == journey["current_task_id"]), phase_info["tasks"][0])
    
    # 🛑 STRICT EXECUTION GATE: Check if they are trying to skip ahead
    last_standup = journey["standup_history"][-1] if journey["standup_history"] else None
    task_is_completed = journey["current_task_id"] in journey["tasks_completed"]
    
    if not task_is_completed and not last_standup:
        return {
            "reply": f"""🛑 **STRICT ACCOUNTABILITY GATE TRIGGERED**

You are on **Day {journey["current_day"]}** of **{phase_info["name"]}**. 

Your **ONLY** focus right now is: 
🎯 **{current_task["name"]}** (Deadline: Day {current_task["deadline_day"]})

I cannot give you new strategic advice, answer questions about scaling, or discuss future phases until you prove execution on this exact task. 

👉 **Action Required:** Click the 'Submit Daily Work' button, paste what you have done for this task, and let me grade it. Do nothing else until this is locked in."""
        }

    # If they passed the gate, retrieve context and answer
    rag_context = retrieve_relevant_context(req.message, top_k=4)
    
    system_prompt = f"""
    You are the E5 AI Coach, an elite, proactive Chief Operating Officer.
    The user is currently on **Day {journey["current_day"]}** of **{phase_info["name"]}**.
    Their current mandatory focus is: **{current_task["name"]}**.
    
    STRICT RULE: You do NOT discuss CPA, affiliate marketing, or generic business fluff. Your entire focus is on digital products, Whop, content marketing, and high-ticket coaching.
    
    If the user asks about advanced topics (e.g., scaling ads, advanced funnels) while their current task is incomplete, gently but firmly redirect them: "We do not discuss that until {current_task["name"]} is completed and approved. Let's focus on the current step."
    
    USER CONTEXT:
    - Niche: {profile.get('niche', 'N/A')}
    - Avatar: {profile.get('target_avatar', 'N/A')}
    - Bottleneck: {profile.get('biggest_bottleneck', 'N/A')}
    
    EXPERT KNOWLEDGE RETRIEVED:
    {rag_context}
    
    INSTRUCTIONS:
    Base your advice strictly on the [EXPERT KNOWLEDGE RETRIEVED]. Be calm, deeply insightful, slightly detached, and authoritative. Short punchy sentences. ZERO AI FLUFF.
    """
    
    messages = [{"role": "system", "content": system_prompt}]
    for m in req.history[-10:]: messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})
    
    try:
        return {"reply": call_llm(messages)}
    except Exception as e:
        raise HTTPException(500, f"LLM error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
