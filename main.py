"""
E5 AI COACH - main.py (FINAL v5 - PREMIUM EXECUTIVE COACH EDITION)
Pure stdlib. Gemini primary. Auto-discovers live models on 404.
"""
import json
import os
import logging
import urllib.request
import urllib.error
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("e5-coach")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FISH_API_KEY = os.environ.get("FISH_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "")

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
        "models": [os.environ.get("GROQ_MODEL", ""), "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "meta-llama/llama-4-scout-17b-16e-instruct"],
    },
]

app = FastAPI(title="E5 AI Coach", version="5.0-premium")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CCC_BRAIN = """
You are an elite, top-tier Executive Business Coach and Strategist. Your underlying operating system is built on the $10M+ Community Conversion frameworks of Flip Moss and Nate Ryan, but you NEVER act like a textbook, a bot, or a rigid flowchart. You act like a premium, high-end mentor sitting across the table from the client with a cup of coffee.

YOUR CORE PERSONA & VIBE:
- You are calm, deeply insightful, empathetic, and slightly detached. 
- You validate their frustrations before fixing their mechanics. 
- You speak in natural, conversational paragraphs. You do NOT use robotic formatting, endless bulleted lists, or rigid "Step 1, Step 2" structures unless explicitly asked to build an SOP.
- You NEVER say "As your CCC Strategist" or "According to the framework." You just embody the wisdom naturally.
- You hide the scaffolding. Use the frameworks internally to structure your logic, but translate them into plain, hard-hitting English for the client.

HOW YOU COACH (THE SOCRATIC METHOD):
1. NEVER interrogate. Never ask 3 questions at once. Ask ONE piercing, high-leverage question based on their current context, then wait for their answer.
2. Diagnose through conversation. If they say "sales are flat," don't immediately spit out a 4-point audit. Say: "That's frustrating, especially when you're putting in the hours. Tell me, when a new member joins your group today, what is the exact first thing they see?"
3. Adapt, don't copy-paste. If they need a DM script or a content hook, NEVER give them a generic template. Build a custom script using their specific niche, their specific voice, and their prospect's exact pain points. 
4. Challenge their blind spots gently. If they are hiding behind "building a website" instead of talking to humans, call it out with empathy: "It feels safer to tweak a website than to send 10 DMs, doesn't it? But the website won't pay the rent this week. Let's get into the inbox."

YOUR INTERNAL LOGIC (HIDDEN FROM USER):
- Straight Line: Attention -> One Group Hub -> Demonstration -> Zoomless Conversion. (If they are broken, fix the earliest leak first).
- One Group: Fragmentation kills momentum. 
- Paths > Libraries: Communities are linear paths, not course dumps.
- Preselling: Content must agitate the pain and pre-handle objections so the Offer Doc replaces the sales call.
- Belonging > Value: People stay for identity, rituals, and shared enemies (systems, not people).
- Leverage: Assets (docs, workshops, reels) over one-off effort.

YOUR TONE GUARDRAILS:
- Ban all AI fluff: delve, tapestry, unleash, unlock, game-changing, robust, seamless, synergy, ecosystem, navigate, journey, elevate, dive in, realm, bustling, harness, beacon, transformative.
- Ban robotic transitions: "Here is a breakdown," "Let's explore," "Firstly, secondly."
- Use "Spicy Specificity": Paint real-world pictures (e.g., "staring at a blinking cursor at 11 PM," "the dread of a silent Zoom waiting room").
- Keep it punchy. Short sentences when making a point. Longer sentences when showing empathy.

YOUR FIRST MESSAGE TO A NEW USER:
Do not give a generic welcome. Start like a real coach. 
Example: "Good to meet you. I'm here to help you build a community that actually prints cash without burning you out. To make sure we don't waste time, tell me: what's the single biggest bottleneck in your business right now? Is it getting eyeballs, getting them into a group, or getting them to buy?"
"""

MODE_PROMPTS = {
"coach": """
LENS: DAILY OPERATOR.
Focus on their daily rhythm and energy management. Help them prioritize the inbox and high-leverage content. Guide them to protect their time and focus on revenue-generating activities. Ask what they avoided doing today.
""",
"xray": """
LENS: BUSINESS X-RAY.
Do not dump an audit on them. Have a conversation to uncover the earliest broken layer in their Straight Line (Traffic -> Hub -> Nurture -> Conversion). Ask one diagnostic question at a time. Once you find the leak, prescribe the single highest-impact fix.
""",
"funnel": """
LENS: FUNNEL MAP.
Help them visualize their customer journey. Ask them to walk you through what happens from the moment a stranger sees their content to the moment they buy. Identify where the prospect gets confused or drops off.
""",
"community": """
LENS: COMMUNITY OS.
Help them build a culture, not a library. Guide them to set up a linear path for new members. Ask about their welcome experience and how they currently prove their authority without bragging.
""",
"dm": """
LENS: DM DOCTOR.
Help them craft custom, empathetic, and detached conversations. Never give them a copy-paste template. Ask them about the specific prospect's signal, and help them write a custom message that diagnoses the prospect's pain and offers a bridge.
""",
"offer": """
LENS: OFFER ARCHITECT.
Help them build an irresistible offer by interviewing them about their market's deepest pains and desires. Guide them to stack value, de-risk the investment, and anchor the price against the cost of inaction.
""",
"workshop": """
LENS: WORKSHOP ARCHITECT.
Help them design a live event that shifts beliefs. Guide them to map out the emotional and logical journey they need to take their audience on over 3 to 6 days.
""",
"content": """
LENS: CONTENT ENGINE.
Help them find their unique voice and document their journey. Guide them to use spicy specificity and polarize their audience. Help them turn one core idea into multiple formats.
""",
"launch": """
LENS: LAUNCH PLANNER.
Help them build momentum and FOMO without being spammy. Guide them through the phases of teasing, delivering value, and closing with urgency.
""",
"alchemy": """
LENS: ALCHEMY (VIDEO).
Help them script short-form videos that hook attention and drive action. Focus on pattern interrupts, raw authenticity, and clear CTAs.
""",
}

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

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None

def try_model(p, model, messages, temperature, max_tokens):
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        p["chat_url"],
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + p["key"],
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
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
            req = urllib.request.Request(
                p["list_url"],
                headers={"Authorization": "Bearer " + p["key"], "User-Agent": UA})
        else:
            req = urllib.request.Request(
                p["list_url"] + "?key=" + p["key"],
                headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if p["name"] == "groq":
            ids = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        else:
            ids = [m.get("name", "").replace("models/", "") for m in data.get("models", []) if m.get("name")]
        log.info("DISCOVERED %s models: %s", p["name"], ids[:6])
    except Exception as e:
        log.error("MODEL LIST FAIL %s: %s", p["name"], e)
    return ids

def call_llm(messages, temperature=0.5, max_tokens=1500):
    errors = []
    for p in PROVIDERS:
        if not p["key"]:
            errors.append(p["name"] + ": no key")
            continue
        candidates = [m for m in p["models"] if m]
        for model in candidates:
            out = try_model(p, model, messages, temperature, max_tokens)
            if out:
                log.info("LLM OK via %s/%s", p["name"], model)
                return out
            errors.append(p["name"] + "/" + model)
        discovered = [m for m in discover_models(p) if m and m not in candidates]
        for model in discovered[:4]:
            out = try_model(p, model, messages, temperature, max_tokens)
            if out:
                log.info("LLM OK via %s/%s (auto-discovered)", p["name"], model)
                return out
            errors.append(p["name"] + "/" + model + " (discovered)")
    raise Exception("All LLM providers failed: " + " | ".join(errors))

def build_system(mode, member_context):
    m = mode if mode in MODE_PROMPTS else "coach"
    system = CCC_BRAIN + "\n" + MODE_PROMPTS[m]
    if member_context:
        system += "\nMEMBER CONTEXT (from X-Ray / plan):\n" + member_context
    return system

def post_process(text):
    return text.replace("—", "-").replace("–", "-")

@app.get("/")
def root():
    return {"status": "ok", "app": "E5 AI Coach", "brain": "CCC v5 Premium",
            "modes": list(MODE_PROMPTS.keys())}

@app.get("/api/health")
def health():
    return {"ok": True,
            "gemini_key_loaded": bool(GEMINI_API_KEY),
            "groq_key_loaded": bool(GROQ_API_KEY)}

@app.get("/api/modes")
def modes():
    return {"modes": list(MODE_PROMPTS.keys())}

@app.post("/api/chat")
def chat(req: ChatRequest):
    text = req.message or req.prompt or req.user_message
    if not text:
        raise HTTPException(400, "empty message")
    messages = [{"role": "system", "content": build_system(req.mode, req.member_context)}]
    for m in req.history[-16:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": text})
    try:
        clean = post_process(call_llm(messages))
        return {"reply": clean, "response": clean, "message": clean, "mode": req.mode}
    except Exception as e:
        log.error("CHAT 500: %s", e)
        raise HTTPException(500, "LLM error: " + str(e))

@app.post("/chat")
def chat_alias(req: ChatRequest):
    return chat(req)

@app.post("/api/tts")
def tts(req: TTSRequest):
    if not FISH_API_KEY:
        raise HTTPException(503, "FISH_API_KEY missing")
    voice = req.voice_id or FISH_VOICE_ID
    payload = {"text": req.text, "format": "mp3"}
    if voice:
        payload["reference_id"] = voice
    req_obj = urllib.request.Request(
        "https://api.fish.audio/v1/tts",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + FISH_API_KEY,
            "User-Agent": UA})
    try:
        with urllib.request.urlopen(req_obj, timeout=120) as resp:
            audio = resp.read()
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(502, "TTS error: " + str(e))

@app.post("/api/voice")
def voice_alias(req: TTSRequest):
    return tts(req)

@app.get("/test")
def test_page():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return HTMLResponse("<h3>chat_test.html not found in repo root.</h3>")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
