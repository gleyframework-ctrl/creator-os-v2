"""
E5 AI COACH OS - main.py (FINAL WHOP EDITION)
RAG-Powered Dynamic Framework Router + Strict Accountability + Whop Identity
"""
import os
import time
import logging
import threading
import urllib.request
import urllib.error
import json
from typing import List, Optional, Dict, Any

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

app = FastAPI(title="E5 AI Coach OS | Whop Edition", version="Final")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
    tasks_completed: List[str] = []
    asset_links: List[str] = []
    asset_text: str = ""
    metrics: str = ""

MEMORY_STORE = {}
def get_profile(mid: str) -> Optional[Dict]: return MEMORY_STORE.get(f"profile_{mid}")
def save_profile(mid: str, data: Dict): MEMORY_STORE[f"profile_{mid}"] = data
def get_standup(mid: str) -> Optional[Dict]: return MEMORY_STORE.get(f"standup_{mid}")
def save_standup(mid: str, data: Dict): MEMORY_STORE[f"standup_{mid}"] = data

# ==============================================================================
# 🤖 LLM ENGINE
# ==============================================================================
def call_llm(messages: List[Dict], temperature: float = 0.4) -> str:
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
    return {"success": True}

@app.post("/api/standup")
def submit_standup(req: StandupRequest):
    profile = get_profile(req.member_id)
    if not profile: raise HTTPException(403, "Complete onboarding first.")
    save_standup(req.member_id, req.dict())
    
    rag_context = retrieve_relevant_context(f"Grade this standup: {req.asset_text} {req.metrics}")
    
    system = f"""You are a STRICT Chief Operating Officer for a Whop Digital Product Creator.
    Grade the user's daily work against the expert frameworks retrieved below.
    Be specific, critical, and actionable. No generic praise.
    
    USER CONTEXT: {json.dumps(profile)}
    EXPERT FRAMEWORKS FOR GRADING: {rag_context}
    
    OUTPUT FORMAT:
    1. 📊 GRADE (Out of 10)
    2. 🔍 AUDIT (What is missing/wrong based on frameworks)
    3. ✅ NEXT STEP (One specific task for tomorrow)"""
    
    prompt = f"Tasks: {req.tasks_completed}\nLinks: {req.asset_links}\nWork Text: {req.asset_text}\nMetrics: {req.metrics}"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    return {"success": True, "review": call_llm(messages)}

@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.message: raise HTTPException(400, "empty message")
    if not CHAT_LIMIT.allow(req.member_id or "default"): raise HTTPException(429, "Rate limit reached")
    
    profile = get_profile(req.member_id or "default")
    if not profile: raise HTTPException(403, "GATEKEEPER: Please complete onboarding first.")
    
    standup = get_standup(req.member_id or "default")
    if not standup and "standup" not in req.message.lower():
        return {"reply": "🛑 **ACCOUNTABILITY GATE TRIGGERED**\n\nYou have not submitted your Daily Standup. As your COO, I cannot give you new strategic advice until you prove execution.\n\nPlease click the 'Submit Daily Work' button, log what you did today, and I will grade it before we proceed."}

    rag_context = retrieve_relevant_context(req.message, top_k=4)
    
    system_prompt = f"""
    You are the E5 AI Coach, an elite, proactive Chief Operating Officer designed EXCLUSIVELY to help creators, coaches, and business owners launch, sell, and scale digital products, courses, and communities on Whop.
    
    STRICT RULE: You do NOT discuss CPA marketing, affiliate marketing, email infrastructure, domain burns, or SMTP. Your entire focus is on digital products, course creation, Whop community building, content marketing, and high-ticket coaching.
    
    TRANSLATION RULE: The knowledge base contains raw expert frameworks. You MUST translate the core mechanics of these frameworks to apply strictly to Whop digital products. If a retrieved framework mentions irrelevant examples, ignore them and apply the underlying psychological or structural principle to Whop product launches, course sales, or community growth.
    
    YOUR TONE: Calm, deeply insightful, slightly detached, authoritative. Short punchy sentences. ZERO AI FLUFF. Banned words: delve, tapestry, unleash, unlock, game-changing, robust, seamless, synergy.
    
    USER CONTEXT:
    - Niche: {profile.get('niche', 'N/A')}
    - Avatar: {profile.get('target_avatar', 'N/A')}
    - Bottleneck: {profile.get('biggest_bottleneck', 'N/A')}
    
    EXPERT KNOWLEDGE RETRIEVED:
    {rag_context}
    
    INSTRUCTIONS:
    You MUST base your advice strictly on the [EXPERT KNOWLEDGE RETRIEVED] above. 
    If the retrieved context contains the exact framework (e.g., S.L.P.C., Socratic Six, ASK Method, Value Equation), use it explicitly. 
    Do not hallucinate generic advice.
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
