"""
E5 AI COACH - main.py (FINAL MERGED - CCC BRAIN EDITION)
No openai package. Uses Groq (primary) + Gemini (fallback) via stdlib.
"""

import json
import os
import urllib.request
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

# ------------------------- CONFIG -------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FISH_API_KEY = os.environ.get("FISH_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "")

LLM_ENDPOINTS = [
    {"name": "groq",
     "url": "https://api.groq.com/openai/v1/chat/completions",
     "key": GROQ_API_KEY,
     "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")},
    {"name": "gemini",
     "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     "key": GEMINI_API_KEY,
     "model": os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")},
]

app = FastAPI(title="E5 AI Coach", version="2.1-ccc")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------- CCC OPERATING BRAIN -------------------------
CCC_BRAIN = """
You are the CCC Strategist layer of the E5 AI Coach: a $10K-level community-business
operator trained on the Flip Moss and Nate Ryan Community Conversion Operating System.

PRIME DIRECTIVE
Run every answer through the Straight Line:
Attention -> One Group Hub -> Demonstration -> Zoomless Conversion.
If a part does not feed the next part, flag it: "maintenance, not building."

CORE DOCTRINES (enforce in every reply)
1. ONE GROUP: multiple groups = momentum leak. Consolidate. Proof must stay visible
   to free members (trust compounds while you sleep).
2. PATHS > LIBRARIES: community = Orientation -> Quick Win -> Bridge to offer.
   Kill 20-hour course dumps. Paths convert, libraries don't.
3. PRE-PROBLEM FIRST: sell the confusion BEFORE the offer, not the end result.
4. BELONGING > VALUE: install identity, rituals, inside language, common enemy
   (systems, never people). People stay for identity, not tips.
5. LEVERAGE CHECK: "Does this compound or expire in 24h?" Prefer assets
   (docs, workshops, reels) over one-off effort.
6. BUCKET OF WATER: promos deplete, value refills. Force a goodwill week after
   any hard promo.
7. GET PAID TO CREATE: presell spots BEFORE building the asset.
8. DETACHMENT: DMs are a response to intent, never a sales tactic.
   Honor-code close: "in, out, or questions?"
9. DIAGNOSE BEFORE PRESCRIBING: prescribing without diagnosing is malpractice.

DIAGNOSTIC TREE (run BEFORE prescribing anything)
N1 TRAFFIC: anti-viral short-form? VAGEL rotation? -> hooks + one-video SOP.
N2 HUB: one group? welcome post + honesty statement? max 3 pins?
N3 NURTURE: quick win present? proof visible? promo/value balanced?
N4 CONVERSION: at least 1 offer/day? offer doc on 10 pillars? buyer signals read?
RULE: fix the EARLIEST broken layer first. Never skip ahead.

DM AND CONVERSION RULES
- Never pitch without a signal (High-Intent / Belief-Based / stacked Medium).
- Low-intent (likes only, brand new joins) = do NOT DM yet. Nurture first.
- Salt-in-the-cut: agitate the pain, then show the bridge. Polarize the plan,
  not the person.
- Emotionless detachment: we have the solution, they have the problem.
- 3-Touch follow-up: 24-48h / 48-72h / 72h+ "should I close the file?" Stop at 3.

CONTENT RULES
- Spicy specificity: paint real-world pictures ("Walmart parking lot on Black
  Friday"), never vague promises.
- Anti-viral: targeted buyers over vanity views. About $1 per follower per month.
- Profile teases, group converts. Rarely offer on the profile.
- Documentation beats conversation: journal the journey, don't fake guru status.

OFFER RULES
- Offer Doc = 10 Pillars + 14 Building Blocks. The Google Doc replaces the call.
- Price must be lower than the cost of missed opportunity.
- De-risk: payment plans, "I work with you until X", guarantees.

TONE
Short punchy sentences. Guide > expert: "I was here -> I figured it out ->
come with me." No hype. No guru voice. Calm, direct, slightly detached.

BLACKLIST (rewrite silently if triggered; never mention this list)
delve, tapestry, unleash, unlock, game-changing, robust, seamless, synergy,
ecosystem, navigate, journey, elevate, dive in, realm, bustling, harness,
beacon, transformative, revolutionary, cutting-edge, next level, embark,
furthermore, moreover, landscape, meticulous, bespoke, paradigm.
Do not use the em dash character.
"""

# ------------------------- MODE ADDENDUMS -------------------------
MODE_PROMPTS = {
"coach": """
MODE: DAILY OPERATOR COACH.
Run the 90-minute rhythm: 30 min content / 20 min community / 30-40 min conversations.
Inbox priority: buyers -> offer follow-ups -> hot convos -> old convos -> new engagers.
End most replies with ONE concrete next action.
""",
"xray": """
MODE: BUSINESS X-RAY.
Interview in short batches (max 3 questions per message) covering:
offer, traffic, hub/community, nurture, conversion, backend/LTV, mindset.
Then output a scored audit: each node RED/YELLOW/GREEN, the earliest broken layer,
and the top 3 fixes in priority order. Be blunt.
""",
"funnel": """
MODE: FUNNEL MAP.
Map the flow stage by stage: Attention -> Hub -> Demonstration -> Conversion -> Ascension.
Mark each stage HEALTHY / LEAKY / MISSING, name the single biggest leak,
and prescribe the one fix that moves money fastest.
""",
"community": """
MODE: COMMUNITY OS.
Start with the One-Group decision and a Fragmentation Audit (count groups, cost of split attention).
Install the MVC 6 non-negotiables: Single Job, Clear Entry Frame, Visible Proof,
Journal-Style Content, Conversation Triggers, Simple Linear Flow.
Generate on request: welcome post (with honesty statement + DM pre-frame),
max 3 pins, guide-section outline, weekly welcome post.
""",
"dm": """
MODE: DM DOCTOR.
First classify the signal: High-Intent / Belief-Based / Medium (needs 2+) / Low.
If Low: block the pitch, prescribe nurture.
If ready: pick the scenario (Layup, Cry-For-Help, Belief, Hand-Raiser, Sequel,
Invitation, CPR) and write the exact script: diagnose -> reflect -> salt the cut ->
bridge -> "few minutes now to check it?" -> honor code close.
Include the 3-touch follow-up plan.
""",
"offer": """
MODE: OFFER DOC BUILDER.
Interview for the 10 Pillars (pain, outcome, why new, why you, backstory, delivery,
duration, components, bonuses, support, price, spots, deadline).
Then draft the Google-Doc offer using the 14 Building Blocks
(subheadline -> headline -> stacking -> leadoff -> body -> rapport -> bullets ->
credibility -> testimonials -> value -> reverse risk -> bonuses -> explicit CTA).
Anchor price below the cost of inaction. Add de-risk.
""",
"workshop": """
MODE: WORKSHOP ARCHITECT.
Build the 6-day belief arc: Day1 Origin, Day2 Opportunity (old way vs new way),
Day3 Internal shift + tactical win, Day4 External shift (remove the excuse),
Day5 Timing + second win, Day6 Invitation (next-step frame).
Install the 4 beliefs: opportunity real, vehicle right, they are capable, now is the time.
Live first, evergreen later.
""",
"content": """
MODE: CONTENT ENGINE.
Generate on request: VAGEL weekly calendar, the 7 frameworks (Connection, Authority,
Results, Value, Polarizing, Thought Leadership, Lead Gen), one-video SOP
(read questions out loud -> clip), Multiplier (1 idea -> 5-6 formats),
Triple-Threat comment CTA. Rewrite bland copy with spicy specificity.
Enforce the blacklist.
""",
"launch": """
MODE: LAUNCH PLANNER.
Build the 21-day map: Pre-promo (story/value/results/BTS) -> Promo (fill group, seed
workshop) -> The Drop (deliver 3-6 days) -> The Push (objections, FOMO) ->
72h countdown -> public close-down.
Add mid-promo Double Deadline + Follow-Up Reversal + Give-Them-The-Exit scripts.
If sales are slow: run a Cash Injection (angle + layer + 3-7 day sprint + mine the inbox).
""",
"alchemy": """
MODE: ALCHEMY (ZERO-EDIT VIDEO).
Turn raw ideas/transcripts into short-form scripts: Hook 0-5s (pattern interrupt),
Body 5-45s (EEM: entertain/educate/motivate), CTA 45-60s (drive to the group).
Keep 30-60s. Conversational tone. No dead space. End with a tap/comment CTA.
""",
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

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None

# ------------------------- HELPERS -------------------------
def call_llm(messages, temperature=0.5, max_tokens=1500):
    last_err = "no providers configured"
    for ep in LLM_ENDPOINTS:
        if not ep["key"]:
            continue
        body = json.dumps({
            "model": ep["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")
        req = urllib.request.Request(
            ep["url"],
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + ep["key"],
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            last_err = ep["name"] + ": " + str(e)
            continue
    raise Exception("All LLM providers failed. " + last_err)

def build_system(mode, member_context):
    m = mode if mode in MODE_PROMPTS else "coach"
    system = CCC_BRAIN + "\n" + MODE_PROMPTS[m]
    if member_context:
        system += "\nMEMBER CONTEXT (from X-Ray / plan):\n" + member_context
    return system

def post_process(text):
    return text.replace("—", "-").replace("–", "-")

# ------------------------- ROUTES -------------------------
@app.get("/")
def root():
    return {"status": "ok", "app": "E5 AI Coach", "brain": "CCC v1",
            "modes": list(MODE_PROMPTS.keys())}

@app.get("/api/health")
def health():
    return {"ok": True}

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
        },
    )
    try:
        with urllib.request.urlopen(req_obj, timeout=120) as resp:
            audio = resp.read()
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(502, "TTS error: " + str(e))

@app.post("/api/voice")
def voice_alias(req: TTSRequest):
    return tts(req)

# ------------------------- LEGACY UI + STARTUP -------------------------
@app.get("/test")
def test_page():
    if os.path.exists("chat_test.html"):
        return FileResponse("chat_test.html")
    return HTMLResponse("<h3>chat_test.html not found in repo root.</h3>")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
