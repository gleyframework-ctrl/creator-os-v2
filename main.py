import os
import io
import httpx
import edge_tts
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Response, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

APP_VERSION = "2026-08-20-aicoach-v9.4-push2talk"

GROQ_KEY = os.getenv("GROQ_API_KEY").strip()
ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()

PREFERRED_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
]

def pick_live_model() -> str:
    try:
        r = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            timeout=10,
        )
        available = {m["id"] for m in r.json().get("data", [])}
        for model in PREFERRED_MODELS:
            if model in available:
                return model
        if available:
            return sorted(available)[0]
        return PREFERRED_MODELS[0]
    except Exception:
        return PREFERRED_MODELS[0]

CHOSEN_MODEL = pick_live_model()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/")
def health():
    return {"status": "ok", "version": APP_VERSION, "model": CHOSEN_MODEL, "tts": "elevenlabs" if ELEVEN_KEY else "edge-free", "stt": "groq-whisper-free"}

@app.get("/test")
def test_page():
    return FileResponse("chat_test.html")

# ---------- CLIENTS ----------
supabase = create_client(
    os.getenv("SUPABASE_URL").strip(), os.getenv("SUPABASE_SERVICE_KEY").strip()
)
embeddings = FastEmbedEmbeddings()

vectorstore = SupabaseVectorStore(
    client=supabase, embedding=embeddings,
    table_name="course_embeddings", query_name="match_documents",
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

builder_store = SupabaseVectorStore(
    client=supabase, embedding=embeddings,
    table_name="builder_embeddings", query_name="match_builder_documents",
)
builder_retriever = builder_store.as_retriever(search_kwargs={"k": 3})

llm = ChatGroq(model_name=CHOSEN_MODEL, temperature=0.4, api_key=GROQ_KEY)

# ---------- COACHING RULES ----------
COACHING_RULES = """
ABSOLUTE RULES (breaking any of them = failure):

1. DIAGNOSE BEFORE PRESCRIBING. If the member mentions a piece of work but has NOT shown it, FIRST ask them to paste it.

2. PERSONALIZE WITH MEMORY. Use the member's niche in EVERY example. Reference past sessions when relevant.

3. ONE INSIGHT PER RESPONSE. The single most powerful lever, 2-4 sentences, applied to THEIR case.

4. APPLY, DON'T RECITE. Use frameworks invisibly. No acronym lectures.

5. 60% QUESTIONS, 40% INSIGHT. End with 1-2 sharp diagnostic questions.

6. REWRITE TOGETHER. Show concrete BEFORE/AFTER, ask which feels right.

7. SHORT AND HUMAN. 150-250 words. No essays/tables unless asked.

8. NEVER INVENT. Only course context. Admit gaps honestly.
"""

E5_PROMPT = ChatPromptTemplate.from_template("""You are the Master AI Coach for the E5 C.A.M.P. Masterclass — a world-class business coach trained in the Socratic method. You COACH, you don't lecture.
""" + COACHING_RULES + """
{memory}

COURSE CONTEXT:
{context}

MEMBER'S QUESTION:
{question}

COACH'S RESPONSE:""")

BUILDER_PROMPT = ChatPromptTemplate.from_template("""You are "THE BUILDER" — master AI coach of the Time to Build system (Tom Noske & Mamba). Philosophy: OFFER FIRST, AUDIENCE SECOND. Direct, practical: "Stop overthinking. Do the work."

You know deeply: the 5 Pillars (Offer 1-30, Audience 30-60, Profit 60-90, TRUST, Repeat & Scale); the Two Traps (Content-First, Business-First); Dream Follower & Avatar (Ben & Grace, attract & repel); TRUST framework (Targeted Authority, Relatable Humanity, Unshakable Story, Status-driven Admiration, Timeless Service); Ikigai; BrandWidth (Past/Present/Future); Trust Equation (time x frequency x quality; 420 minutes; 7-11-4); Pub Chat (speak to ONE person); Origin Story (iceberg); Do-the-Work law (finish Core first, 14 days); KPIs & TRUST Audit.

EXTRA RULE: NEVER promise income results. Stories are examples, not guarantees.
""" + COACHING_RULES + """
{memory}

COURSE CONTEXT:
{context}

MEMBER'S QUESTION:
{question}

COACH'S RESPONSE:""")

def format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)

# ---------- MODELS ----------
class ChatRequest(BaseModel):
    question: str
    member_id: Optional[str] = None
    coach_id: Optional[str] = "e5"
    language: Optional[str] = "en"

class MemberProfile(BaseModel):
    member_id: str
    name: Optional[str] = None
    niche: Optional[str] = None
    current_stage: Optional[str] = None
    struggles: Optional[str] = None

# ---------- MEMORY ----------
def ensure_member(member_id: str):
    existing = supabase.table("members").select("member_id").eq("member_id", member_id).execute()
    if not existing.data:
        supabase.table("members").insert({"member_id": member_id}).execute()

def build_memory_block(member_id: str) -> str:
    try:
        prof = supabase.table("members").select("*").eq("member_id", member_id).execute()
        hist = (supabase.table("chat_history").select("question, answer, created_at")
                .eq("member_id", member_id).order("created_at", desc=True).limit(3).execute())
    except Exception:
        return "MEMBER MEMORY: (unavailable)"
    if not prof.data:
        return "MEMBER MEMORY: (new member, no profile yet)"
    p = prof.data[0]
    lines = ["MEMBER MEMORY (use this to personalize):"]
    if p.get("name"): lines.append(f"- Name: {p['name']}")
    if p.get("niche"): lines.append(f"- Niche/Business: {p['niche']}")
    if p.get("current_stage"): lines.append(f"- Current stage: {p['current_stage']}")
    if p.get("struggles"): lines.append(f"- Known struggles: {p['struggles']}")
    if hist.data:
        lines.append("- Recent coaching sessions:")
        for h in reversed(hist.data):
            lines.append(f'  * Member asked: "{(h["question"] or "")[:150]}" -> You advised: "{(h["answer"] or "")[:150]}"')
    return "\n".join(lines)

def save_memory(member_id: str, question: str, answer: str):
    try:
        supabase.table("chat_history").insert({
            "member_id": member_id, "question": question, "answer": answer,
        }).execute()
        supabase.table("members").update(
            {"updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("member_id", member_id).execute()
    except Exception as e:
        print(f"⚠️ MEMORY WRITE FAILED: {e}")

# ---------- ENDPOINTS ----------
@app.post("/api/member/register")
async def register_member(profile: MemberProfile):
    try:
        row = {
            "member_id": profile.member_id, "name": profile.name,
            "niche": profile.niche, "current_stage": profile.current_stage,
            "struggles": profile.struggles, "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        supabase.table("members").upsert(row, on_conflict="member_id").execute()
        return {"status": "success", "member_id": profile.member_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Register failed: {e}")

@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    try:
        coach = (req.coach_id or "e5").strip().lower()
        lang = (req.language or "en").strip().lower()
        lang_note = ("\n\n[SYSTEM LANGUAGE DIRECTIVE: The member chose ARABIC. Respond ENTIRELY in Arabic — warm, clear coaching tone. Keep framework names like TRUST and Dream Avatar in English where natural.]"
                     if lang.startswith("ar") else
                     "\n\n[SYSTEM LANGUAGE DIRECTIVE: Respond in English.]")
        use_retriever = builder_retriever if coach == "builder" else retriever
        use_prompt = BUILDER_PROMPT if coach == "builder" else E5_PROMPT

        memory_block = "MEMBER MEMORY: (no member attached - generic coaching)"
        if req.member_id:
            ensure_member(req.member_id)
            memory_block = build_memory_block(req.member_id)

        docs = use_retriever.invoke(req.question)
        context = format_docs(docs)
        answer = (use_prompt | llm | StrOutputParser()).invoke({
            "memory": memory_block, "context": context, "question": req.question + lang_note,
        })
        if req.member_id:
            save_memory(req.member_id, req.question, answer)
        return {"status": "success", "answer": answer, "member_id": req.member_id, "coach": coach}
    except Exception as e:
        print(f"❌ RAG FAILURE: {e}")
        raise HTTPException(status_code=500, detail=f"RAG failed: {e}")

# ---------- VOICE OUT (TTS): FREE EDGE + ELEVENLABS UPGRADE SWITCH ----------
@app.post("/api/tts")
async def text_to_speech(req: dict):
    text = (req.get("text") or "").strip()
    lang = (req.get("language") or "en").strip().lower()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    if ELEVEN_KEY:
        voice_id = "pNInz6obpgDQGcFmaJgB"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"}
        payload = {"text": text, "model_id": "eleven_multilingual_v2",
                   "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                print(f"ElevenLabs error: {r.text}")
                raise HTTPException(status_code=500, detail="Voice generation failed")
            return Response(content=r.content, media_type="audio/mpeg")

    voice = "ar-EG-ShakirNeural" if lang.startswith("ar") else "en-US-ChristopherNeural"
    try:
        buf = io.BytesIO()
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return Response(content=buf.getvalue(), media_type="audio/mpeg")
    except Exception as e:
        print(f"❌ TTS FAILURE: {e}")
        raise HTTPException(status_code=500, detail="Voice generation failed")

# ---------- VOICE IN (STT): FREE GROQ WHISPER ----------
@app.post("/api/stt")
async def speech_to_text(file: UploadFile = File(...), language: str = Form("en")):
    audio_bytes = await file.read()
    files = {"file": (file.filename or "voice.webm", audio_bytes, file.content_type or "audio/webm")}
    data = {"model": "whisper-large-v3"}
    if (language or "en").lower().startswith("ar"):
        data["language"] = "ar"
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers, files=files, data=data,
            )
            if r.status_code != 200:
                print(f"Whisper error: {r.text}")
                raise HTTPException(status_code=500, detail="Transcription failed")
            return {"text": r.json().get("text", "")}
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ STT FAILURE: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")

if __name__ == "__main__":
    print(f"🔥 SERVER STARTING WITH MODEL: {CHOSEN_MODEL}")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
