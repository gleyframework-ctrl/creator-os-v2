"""
E5 AI COACH - GOOGOLTRADREKACHILIA-PLEX EDITION
The Ultimate $500M Business Operating System
Fusing: $100M Offers, Leads, Money Models, Retention, Branding + 5 Scaling Frameworks
"""

import json, os, re, time, logging, threading, urllib.request, urllib.error, urllib.parse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# ==================== CONFIG & VAULT ====================
try:
    from vault import SCRIPT_VAULT
except:
    SCRIPT_VAULT = ""

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("e5-coach")

UA = "Mozilla/5.0"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FISH_API_KEY = os.environ.get("FISH_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WHOP_API_KEY = os.environ.get("WHOP_API_KEY", "")

# ==================== RATE LIMITERS ====================
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
    def remaining(self, key):
        now = time.time()
        with self.lock:
            b = self.hits.get(key, [])
            while b and now - b[0] > self.window:
                b.pop(0)
            return max(0, self.max_hits - len(b))

CHAT_LIMIT = RateLimiter(30, 3600)
TTS_LIMIT = RateLimiter(10, 3600)

# ==================== MODE TIERS ====================
MODE_TIERS = {
    "coach": "free", "xray": "free", "funnel": "free",
    "community": "insider", "dm": "insider", "content": "insider",
    "alchemy": "insider", "hack": "insider",
    "offer": "partner", "workshop": "partner", "launch": "partner",
}
TIER_RANK = {"free": 0, "insider": 1, "partner": 2}

# ==================== PROVIDERS ====================
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

app = FastAPI(title="E5 AI Coach", version="Googoltradrekachiliaplex")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ==================== PYDANTIC MODELS ====================
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

class TaskCompleteRequest(BaseModel):
    member_id: str = "default"
    task_id: str

class GoalsUpdateRequest(BaseModel):
    member_id: str = "default"
    revenue_goal: Optional[float] = None
    lead_goal: Optional[int] = None
    conversion_goal: Optional[float] = None

class KPIUpdateRequest(BaseModel):
    member_id: str = "default"
    revenue: Optional[float] = None
    leads: Optional[int] = None
    calls: Optional[int] = None
    conversion_rate: Optional[float] = None

class FrameworkChecklistRequest(BaseModel):
    member_id: str = "default"
    framework_id: str

# ==================== SUPABASE HELPERS ====================
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

def load_docs(member_id: str) -> str:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ""
    try:
        url = (SUPABASE_URL.rstrip("/") + "/rest/v1/member_docs" +
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

# ==================== USER STATE ====================
class UserBusinessState(BaseModel):
    member_id: str = "default"
    business_name: str = ""
    avatar: dict = {"niche": "coach", "target": "B2B", "stage": "Lead Gen"}
    current_stage: str = "Lead Gen"
    monthly_revenue: float = 0.0
    monthly_revenue_goal: float = 10000.0
    lead_goal: int = 100
    conversion_goal: float = 20.0
    primary_bottleneck: str = "No leads"
    daily_kpis: Dict[str, int] = {"dm_outreach": 0, "content_posts": 0, "calls_booked": 0, "revenue": 0}
    tasks_completed: List[str] = []
    tasks_pending: List[str] = []
    framework_progress: Dict[str, str] = {}
    framework_checklist: Dict[str, List[Dict]] = {}
    weekly_plan: Dict[str, List[str]] = {}
    goals: Dict[str, float] = {"revenue": 10000, "leads": 100, "conversion": 20}
    streak_days: int = 0
    last_active: Optional[str] = None
    rule_100_count: int = 0
    health_score: int = 0

def get_user_state(member_id: str) -> UserBusinessState:
    memory, _ = load_memory(member_id)
    if memory:
        try:
            data = json.loads(memory)
            return UserBusinessState(**data)
        except:
            pass
    return UserBusinessState(member_id=member_id)

def save_user_state(state: UserBusinessState):
    save_memory(state.member_id, json.dumps(state.dict()))

# ==================== LLM ENGINE ====================
def try_model(provider, model, messages, temperature=0.5, max_tokens=1500):
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(provider["chat_url"], data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + provider["key"], "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or ""
    except Exception as e:
        log.error("LLM fail %s/%s: %s", provider["name"], model, e)
        return None

def call_llm(messages, temperature=0.5, max_tokens=1500):
    for provider in PROVIDERS:
        if not provider["key"]: continue
        for model in provider["models"]:
            result = try_model(provider, model, messages, temperature, max_tokens)
            if result: return result
    raise Exception("All LLM providers failed")

# ==================== SYSTEM PROMPTS ====================
CCC_BRAIN = """You are the E5 AI Coach — a proactive, predictive, prescriptive business COO operating at Googoltradrekachiliaplex level.
You fuse ALL frameworks: TTB, AVOCADO, $100M Offers/Leads/Money Models/Retention/Branding, Closing Playbook, 5 Scaling Frameworks.
You NEVER just answer questions. You DIAGNOSE → PRESCRIBE → DRIVE ACTION.
Ban all fluff. Use Spicy Specificity. End with a direct command or question.
Always leverage: Value Equation, Core 4, ECAFI, SOULFUL, 5 Horsemen, Rule of 100, Money Models.
"""

MODE_PROMPTS = {
    "coach": "LENS: DAILY OPERATOR – focus on rhythm, Rule of 100, 5 Horsemen of Retention.",
    "xray": "LENS: BUSINESS X-RAY – Find earliest broken layer in Straight Line. Score RED/YELLOW/GREEN.",
    "funnel": "LENS: FUNNEL MAP – Visualize customer journey. Apply Value Equation to reduce friction.",
    "community": "LENS: COMMUNITY OS – Build culture, rituals, belonging > value. Design welcome experience.",
    "dm": "LENS: DM DOCTOR – Classify signal. Use ECAFI & SOULFUL scripts. Diagnose, don't pitch.",
    "offer": "LENS: OFFER ARCHITECT – Stack value, de-risk, anchor price. Build Grand Slam Offers.",
    "workshop": "LENS: WORKSHOP ARCHITECT – Design 6-day belief arc. Install 4 core beliefs.",
    "content": "LENS: CONTENT ENGINE – Spicy specificity, polarize, document journey. 7 Content Types.",
    "launch": "LENS: LAUNCH PLANNER – 21-day map: Pre-promo → Promo → Drop → Push → 72h countdown.",
    "alchemy": "LENS: ALCHEMY (VIDEO) – Hook 0-5s, Body 5-45s, CTA 45-60s. Retain through curiosity.",
    "hack": "LENS: FUNNEL HACKER – Reverse-engineer competitor funnel stage-by-stage. Rebuild for niche.",
}

def build_system(mode, member_context, memory="", docs=""):
    m = mode if mode in MODE_PROMPTS else "coach"
    system = CCC_BRAIN + "\n" + MODE_PROMPTS[m]
    if SCRIPT_VAULT: system += "\n" + SCRIPT_VAULT
    if docs: system += "\nMEMBER DOCS:\n" + docs
    if memory: system += "\nMEMBER MEMORY:\n" + memory
    if member_context: system += "\nCONTEXT:\n" + member_context
    return system

# ==================== FRAMEWORK CHECKLISTS ====================
FRAMEWORK_CHECKLISTS = {
    "avocado": [
        {"step": "Define Dream Client Avatar (AVOCADO)", "done": False},
        {"step": "Create R.I.P.E. Lead Magnet", "done": False},
        {"step": "Write ECAFI DM Script", "done": False},
        {"step": "Design 3-Tier Offer Stack", "done": False},
        {"step": "Build Community OS Structure", "done": False},
    ],
    "money_models": [
        {"step": "Identify Attraction Offer", "done": False},
        {"step": "Define Upsell Path (Classic/Menu/Anchor/Rollover)", "done": False},
        {"step": "Set Up Downsells (Payment Plan/Trial/Feature)", "done": False},
        {"step": "Create Continuity Offers (Bonus/Discount/Waived Fee)", "done": False},
    ],
    "leads": [
        {"step": "Map Core 4 Channels (Warm/Cold/Content/Ads)", "done": False},
        {"step": "Set Rule of 100 Daily Actions", "done": False},
        {"step": "Create Lead Magnet (Win Money Back/Giveaway/Decoy)", "done": False},
        {"step": "Write Hook Scripts (Call Out + Value + CTA)", "done": False},
    ],
    "community_os": [
        {"step": "Define Green → Ripe Customer Sequence", "done": False},
        {"step": "Implement 5 Horsemen of Retention", "done": False},
        {"step": "Create Exit Interview Process", "done": False},
        {"step": "Build Member Events Calendar", "done": False},
    ],
    "ttb": [
        {"step": "Clarify Brand & Ikigai", "done": False},
        {"step": "Apply TRUST Formula (Time/Results/Uniqueness/Social Proof/Trust)", "done": False},
        {"step": "Plan Sustainable Content Strategy", "done": False},
    ],
    "soulful": [
        {"step": "Learn SOULFUL Framework (Situation/Outcome/Understanding/Leverage/Frame/Uncover/Lead)", "done": False},
        {"step": "Practice Validation Cheatsheet", "done": False},
    ],
    "delivery": [
        {"step": "Create Onboarding Checklist", "done": False},
        {"step": "Define Activation Point", "done": False},
        {"step": "Build Milestone Tracking System", "done": False},
    ],
    "value_eq": [
        {"step": "Define Dream Outcome", "done": False},
        {"step": "Assess Perceived Likelihood of Achievement", "done": False},
        {"step": "Reduce Time Delay", "done": False},
        {"step": "Lower Effort & Sacrifice", "done": False},
    ],
}

# ==================== NEW OS ENDPOINTS ====================

# 1. DAILY BRIEFING
@app.post("/api/daily-briefing")
def daily_briefing(req: ChatRequest):
    member_id = req.member_id or "default"
    state = get_user_state(member_id)
    system = build_system("coach", req.member_context, docs=load_docs(member_id))
    prompt = f"""User state:
- Stage: {state.current_stage}
- Revenue: ${state.monthly_revenue} / ${state.monthly_revenue_goal}
- Bottleneck: {state.primary_bottleneck}
- Today's KPIs: {state.daily_kpis}
- Tasks done: {state.tasks_completed}
- Tasks pending: {state.tasks_pending}

Generate a Daily Battle Plan with:
- 3-5 specific tasks (with exact frameworks to use)
- A motivational check-in
- Clear KPIs to hit today.
Be direct, commanding, and leverage appropriate framework(s)."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    plan = call_llm(messages)
    tasks = parse_tasks(plan)
    return {"plan": plan, "tasks": tasks, "state": state.dict()}

def parse_tasks(plan):
    lines = plan.split("\n")
    tasks = [l for l in lines if l.strip().startswith(("1.", "2.", "3.", "4.", "5.", "-", "•"))]
    return tasks

# 2. TASK COMPLETION
@app.post("/api/task/complete")
def complete_task(req: TaskCompleteRequest):
    member_id = req.member_id or "default"
    task_id = req.task_id
    state = get_user_state(member_id)
    if task_id not in state.tasks_pending:
        return {"error": "Task not pending"}
    state.tasks_pending.remove(task_id)
    state.tasks_completed.append(task_id)
    today = datetime.now().date().isoformat()
    if state.last_active and state.last_active == today:
        state.streak_days += 1
    else:
        state.streak_days = 1
    state.last_active = today
    save_user_state(state)
    system = build_system("coach", "")
    prompt = f"User just completed task '{task_id}'. Current state: {state.dict()}. What's the next logical task? Provide brief motivating message and next task."
    msg = call_llm([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
    new_task = extract_next_task(msg)
    if new_task:
        state.tasks_pending.append(new_task)
        save_user_state(state)
    return {"feedback": msg, "new_task": new_task, "state": state.dict()}

def extract_next_task(msg):
    lines = msg.split("\n")
    for l in lines:
        if l.strip().startswith(("1.", "2.", "3.", "-", "•", "Next")):
            return l.strip()
    return None

# 3. PREDICTIVE INSIGHTS
@app.get("/api/predictive-insight")
def predictive_insight(member_id: str = "default"):
    state = get_user_state(member_id)
    insights = []
    if state.daily_kpis.get("dm_outreach", 0) < 20:
        insights.append({
            "severity": "high",
            "message": "Low DM outreach. Rule of 100 requires >20/day. Use ECAFI scripts.",
            "action": "Review DM Doctor mode for scripts."
        })
    if state.daily_kpis.get("calls_booked", 0) == 0 and state.daily_kpis.get("dm_outreach", 0) > 10:
        insights.append({
            "severity": "medium",
            "message": "Sending DMs but booking zero calls. Check your 'Frame' stage.",
            "action": "Role-play with AI in DM Doctor mode."
        })
    if state.monthly_revenue < state.monthly_revenue_goal * 0.5:
        insights.append({
            "severity": "high",
            "message": f"Revenue at {state.monthly_revenue/state.monthly_revenue_goal*100:.0f}% of goal. Need urgent offer optimization.",
            "action": "Use Offer Architect mode to rebuild Grand Slam Offer."
        })
    return {"insights": insights, "health_score": compute_health(state)}

def compute_health(state):
    score = 0
    if state.daily_kpis.get("dm_outreach", 0) >= 30: score += 25
    if state.daily_kpis.get("content_posts", 0) >= 1: score += 25
    if state.daily_kpis.get("calls_booked", 0) >= 1: score += 25
    if state.tasks_completed: score += 25
    return min(score, 100)

# 4. SOCIAL MEDIA DRAFT
@app.post("/api/social/draft")
def social_draft(req: ChatRequest):
    member_id = req.member_id or "default"
    state = get_user_state(member_id)
    topic = getattr(req, 'topic', 'business growth')
    platform = getattr(req, 'platform', 'linkedin')
    system = build_system("content", "")
    prompt = f"Create a {platform} post about '{topic}' for a {state.avatar.get('niche','coach')} business. Use 7 Content Types (Authority, Validation, Opener, etc.). Make it Spicy Specific. Include hook, body, and CTA."
    draft = call_llm([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
    return {"draft": draft, "platform": platform, "topic": topic}

# 5. GOALS
@app.post("/api/goals")
def set_goals(req: GoalsUpdateRequest):
    state = get_user_state(req.member_id)
    if req.revenue_goal is not None:
        state.goals["revenue"] = req.revenue_goal
    if req.lead_goal is not None:
        state.goals["leads"] = req.lead_goal
    if req.conversion_goal is not None:
        state.goals["conversion"] = req.conversion_goal
    save_user_state(state)
    return state.goals

@app.get("/api/goals")
def get_goals(member_id: str = "default"):
    state = get_user_state(member_id)
    return state.goals

# 6. KPI UPDATE
@app.post("/api/kpis")
def update_kpis(req: KPIUpdateRequest):
    state = get_user_state(req.member_id)
    if req.revenue is not None:
        state.monthly_revenue = req.revenue
    if req.leads is not None:
        state.daily_kpis["dm_outreach"] = req.leads
    if req.calls is not None:
        state.daily_kpis["calls_booked"] = req.calls
    if req.conversion_rate is not None:
        state.conversion_goal = req.conversion_rate
    save_user_state(state)
    return {"success": True}

# 7. WEEKLY PLAN
@app.get("/api/weekly-plan")
def get_weekly_plan(member_id: str = "default"):
    state = get_user_state(member_id)
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    cache_key = f"weekly_{week_start.isoformat()}"
    if hasattr(get_weekly_plan, "cache") and cache_key in get_weekly_plan.cache:
        return get_weekly_plan.cache[cache_key]
    system = build_system("coach", "")
    prompt = f"""Generate 7-day weekly plan for business owner:
- Stage: {state.current_stage}
- Revenue goal: ${state.goals['revenue']}, Current: ${state.monthly_revenue}
- Lead goal: {state.goals['leads']} leads/month
- Bottleneck: {state.primary_bottleneck}
- KPIs: {state.daily_kpis}

Return JSON with days (Monday-Sunday) as keys and list of 2-3 specific tasks per day, each including framework reference.
Output only valid JSON."""
    try:
        response = call_llm([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        plan = json.loads(response)
    except:
        plan = {
            "Monday": ["Send 30 DMs (ECAFI)", "Post 1 Authority content"],
            "Tuesday": ["Follow up with 5 leads", "Review Value Equation"],
            "Wednesday": ["Content post (Validation)", "Log Rule of 100"],
            "Thursday": ["Prepare workshop", "Review framework checklist"],
            "Friday": ["Live workshop", "Send 30 DMs"],
            "Saturday": ["Review weekly metrics", "Plan next week"],
            "Sunday": ["Rest & reflect"]
        }
    if not hasattr(get_weekly_plan, "cache"):
        get_weekly_plan.cache = {}
    get_weekly_plan.cache[cache_key] = plan
    return plan

# 8. FRAMEWORK CHECKLIST
@app.post("/api/framework-checklist")
def get_framework_checklist(req: FrameworkChecklistRequest):
    state = get_user_state(req.member_id)
    framework_id = req.framework_id
    checklist = FRAMEWORK_CHECKLISTS.get(framework_id, [])
    if framework_id in state.framework_checklist:
        user_steps = state.framework_checklist[framework_id]
        for step in checklist:
            for us in user_steps:
                if us["step"] == step["step"]:
                    step["done"] = us["done"]
                    break
    return checklist

@app.post("/api/framework-checklist/update")
def update_framework_step(req: dict):
    member_id = req.get("member_id", "default")
    framework_id = req.get("framework_id")
    step_index = req.get("step_index")
    done = req.get("done", False)
    if framework_id is None or step_index is None:
        raise HTTPException(400, "Missing parameters")
    state = get_user_state(member_id)
    if framework_id not in state.framework_checklist:
        state.framework_checklist[framework_id] = FRAMEWORK_CHECKLISTS.get(framework_id, []).copy()
    if step_index < len(state.framework_checklist[framework_id]):
        state.framework_checklist[framework_id][step_index]["done"] = done
        save_user_state(state)
        return {"success": True}
    return {"error": "Step not found"}

# 9. COACH CHECK-IN
@app.post("/api/coach-checkin")
def coach_checkin(req: ChatRequest):
    member_id = req.member_id or "default"
    state = get_user_state(member_id)
    system = build_system("coach", req.member_context, load_memory(member_id)[0])
    prompt = f"""You are proactive coach. Initiate check-in based on user state:
{state.dict()}
Ask about progress, challenges, what they need help with. Suggest single most important framework to focus on today. Be empathetic but direct. End with clear question."""
    response = call_llm([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
    return {"coach_message": response}

# ==================== EXISTING CHAT ENDPOINT ====================
@app.post("/api/chat")
def chat(req: ChatRequest):
    text = req.message or req.prompt or req.user_message
    if not text: raise HTTPException(400, "empty")
    member_id = req.member_id or "default"
    if not CHAT_LIMIT.allow(member_id):
        raise HTTPException(429, f"Rate limit. Remaining: {CHAT_LIMIT.remaining(member_id)}")
    memory, tier = load_memory(member_id)
    need = MODE_TIERS.get(req.mode, "free")
    if TIER_RANK.get(tier or "free", 0) < TIER_RANK.get(need, 0):
        raise HTTPException(403, f"locked: {need}")
    docs = load_docs(member_id)
    state = get_user_state(member_id)
    system = build_system(req.mode, req.member_context, memory, docs)
    system += f"\nCURRENT USER STATE: {state.dict()}\nUse this to personalize your response."
    messages = [{"role": "system", "content": system}]
    for m in req.history[-16:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": text})
    try:
        reply = call_llm(messages)
        reply, mem_update = extract_memory(reply)
        if mem_update:
            save_memory(member_id, mem_update)
        return {"reply": reply, "response": reply, "remaining": CHAT_LIMIT.remaining(member_id)}
    except Exception as e:
        log.error("CHAT ERR: %s", e)
        raise HTTPException(500, str(e))

def extract_memory(text):
    return text, ""

# ==================== OTHER ROUTES ====================
@app.get("/api/health")
def health():
    return {"ok": True, "brain": "Googoltradrekachiliaplex", "frameworks_loaded": len(FRAMEWORK_CHECKLISTS)}

@app.get("/api/tier")
def tier_endpoint(member_id: str = "default"):
    _, tier = load_memory(member_id)
    return {"tier": tier or "free"}

@app.post("/api/unlock")
def unlock(req: UnlockRequest):
    tier = whop_tier_for_license(req.license_key) if WHOP_API_KEY else "insider"
    if tier:
        set_tier(req.member_id, tier)
        return {"tier": tier}
    raise HTTPException(403, "Invalid license")

def whop_tier_for_license(key: str):
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
            return "insider"
    except:
        return None

@app.get("/test")
def test_page():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return HTMLResponse("<h3>chat_test.html not found</h3>")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
