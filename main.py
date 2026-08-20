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

APP_VERSION = "2026-08-20-aicoach-v10.3-vision-fix"

GROQ_KEY = os.getenv("GROQ_API_KEY").strip()
ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()

PREFERRED_MODELS = [
    "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3-32b",
    "llama-3.1-8b-instant", "mixtral-8x7b-32768",
]

ASSET_TYPES = ["offer", "avatar", "customer_voice", "traffic", "capture",
               "nurture", "convert", "retain", "numbers", "story",
               "sales_page", "squeeze_page", "quiz_page", "thank_you_page",
               "email_copy", "social_channel", "customer_avatar", "business_details", "other"]

ASSET_KEYWORDS = [
    (["convert", "sales_page"], ["sales page", "salespage", "صفحة البيع"]),
    (["capture", "squeeze_page", "quiz_page"], ["squeeze", "quiz", "lead magnet", "التقاط", "اختبار"]),
    (["retain", "thank_you_page"], ["thank you", "thankyou", "شكر"]),
    (["nurture", "email_copy"], ["email", "e-mail", "رسائل", "رسالة"]),
    (["traffic", "social_channel"], ["youtube", "instagram", "tiktok", "social", "traffic", "ads", "يوتيوب", "قناة", "إعلان"]),
    (["avatar", "customer_avatar"], ["avatar", "عميل"]),
    (["offer"], ["offer", "عرض"]),
]

def pick_live_model() -> str:
    try:
        r = httpx.get("https://api.groq.com/openai/v1/models",
                      headers={"Authorization": f"Bearer {GROQ_KEY}"}, timeout=10)
        available = {m["id"] for m in r.json().get("data", [])}
        for model in PREFERRED_MODELS:
            if model in available: return model
        if available: return sorted(available)[0]
        return PREFERRED_MODELS[0]
    except Exception:
        return PREFERRED_MODELS[0]

def pick_vision_model() -> str:
    try:
        r = httpx.get("https://api.groq.com/openai/v1/models",
                      headers={"Authorization": f"Bearer {GROQ_KEY}"}, timeout=10)
        available = [m["id"] for m in r.json().get("data", [])]
        for pattern in ["llama-4-scout", "llama-4-maverick", "vision"]:
            for mid in available:
                if pattern in mid: return mid
        return ""
    except Exception:
        return ""

CHOSEN_MODEL = pick_live_model()
VISION_CHOSEN = pick_vision_model()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def health():
    return {"status": "ok", "version": APP_VERSION, "model": CHOSEN_MODEL,
            "vision": VISION_CHOSEN or ("gemini-free" if GEMINI_KEY else "none"),
            "tts": "elevenlabs" if ELEVEN_KEY else "edge-free", "stt": "groq-whisper-free"}

@app.get("/test")
def test_page(): return FileResponse("chat_test.html")

supabase = create_client(os.getenv("SUPABASE_URL").strip(), os.getenv("SUPABASE_SERVICE_KEY").strip())
embeddings = FastEmbedEmbeddings()

vectorstore = SupabaseVectorStore(client=supabase, embedding=embeddings,
                                  table_name="course_embeddings", query_name="match_documents")
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
builder_store = SupabaseVectorStore(client=supabase, embedding=embeddings,
                                    table_name="builder_embeddings", query_name="match_builder_documents")
builder_retriever = builder_store.as_retriever(search_kwargs={"k": 3})
llm = ChatGroq(model_name=CHOSEN_MODEL, temperature=0.4, api_key=GROQ_KEY)

COACHING_RULES = """
ABSOLUTE RULES (breaking any of them = failure):
1. DIAGNOSE BEFORE PRESCRIBING. If work isn't shown, ask to paste or screenshot it.
2. PERSONALIZE WITH MEMORY. Use niche in every example.
3. ONE INSIGHT PER RESPONSE. 2-4 sentences, applied to THEIR case.
4. APPLY, DON'T RECITE. Use frameworks invisibly.
5. 60% QUESTIONS, 40% INSIGHT.
6. REWRITE TOGETHER. BEFORE/AFTER.
7. SHORT AND HUMAN. 150-250 words.
8. NEVER INVENT.
9. USE THE ASSET INVENTORY.
10. FUNNEL X-RAY. Compare metrics to benchmarks.
11. CUSTOMER VOICE. Use their exact words.
12. READ BEFORE ASKING.
13. HYPOTHESIS FIRST.
14. BOTTLENECK ONLY.
15. SECOND-ORDER QUESTIONS.
16. MINE THE VOICE.
17. ACCOUNTABILITY LOOP.
18. STAGE LADDER (OFFER/AVATAR/TRAFFIC/CAPTURE/NURTURE/CONVERT/RETAIN).
19. VISION ANALYSIS. Screenshot = source of truth, even if it shows a different offer/audience than the member's file. Quote the exact headline you see.
"""

E5_PROMPT = ChatPromptTemplate.from_template("""You are the Master AI Coach for the E5 C.A.M.P. Masterclass.
""" + COACHING_RULES + """
{memory}
COURSE CONTEXT:
{context}
MEMBER'S QUESTION:
{question}
COACH'S RESPONSE:""")

BUILDER_PROMPT = ChatPromptTemplate.from_template("""You are "THE BUILDER" — master AI coach of the Time to Build system (Tom Noske & Mamba). Philosophy: OFFER FIRST, AUDIENCE SECOND.
""" + COACHING_RULES + """
{memory}
COURSE CONTEXT:
{context}
MEMBER'S QUESTION:
{question}
COACH'S RESPONSE:""")

def format_docs(docs): return "\n\n".join(d.page_content for d in docs)

class ChatRequest(BaseModel):
    question: str
    member_id: Optional[str] = None
    coach_id: Optional[str] = "e5"
    language: Optional[str] = "en"
    vision_analysis: Optional[str] = None

class MemberProfile(BaseModel):
    member_id: str
    name: Optional[str] = None
    niche: Optional[str] = None
    current_stage: Optional[str] = None
    struggles: Optional[str] = None
    business_context: Optional[str] = None

class AssetSave(BaseModel):
    member_id: str
    asset_type: str
    title: Optional[str] = None
    content: Optional[str] = None
    url: Optional[str] = None
    metrics: Optional[str] = None

class VisionRequest(BaseModel):
    image_b64: str
    context: Optional[str] = None

def ensure_member(member_id: str):
    existing = supabase.table("members").select("member_id").eq("member_id", member_id).execute()
    if not existing.data:
        supabase.table("members").insert({"member_id": member_id}).execute()

def build_memory_block(member_id: str) -> str:
    try:
        prof = supabase.table("members").select("*").eq("member_id", member_id).execute()
        hist = (supabase.table("chat_history").select("question, answer, created_at")
                .eq("member_id", member_id).order("created_at", desc=True).limit(3).execute())
        assets = supabase.table("member_assets").select("asset_type,title,metrics").eq("member_id", member_id).execute()
    except Exception: return "MEMBER MEMORY: (unavailable)"
    if not prof.data: return "MEMBER MEMORY: (new member)"
    p = prof.data[0]
    lines = ["MEMBER MEMORY:"]
    if p.get("name"): lines.append(f"- Name: {p['name']}")
    if p.get("niche"): lines.append(f"- Niche: {p['niche']}")
    if p.get("current_stage"): lines.append(f"- Stage: {p['current_stage']}")
    if p.get("struggles"): lines.append(f"- Struggles: {p['struggles']}")
    if p.get("business_context"):
        lines.append("- BUSINESS CONTEXT:")
        lines.append(p["business_context"][:2000])
    if assets.data:
        parts = [a["asset_type"] + (f" [{a['metrics']}]" if a.get("metrics") else "") for a in assets.data]
        lines.append("- X-RAY ON FILE: " + " | ".join(parts))
    if hist.data:
        lines.append("- Recent sessions:")
        for h in reversed(hist.data):
            lines.append(f'  * Q: "{(h["question"] or "")[:150]}" -> A: "{(h["answer"] or "")[:150]}"')
    return "\n".join(lines)

def find_asset_review(member_id: str, question: str) -> str:
    try:
        q = question.lower()
        for types, kws in ASSET_KEYWORDS:
            if any(k in q for k in kws):
                for atype in types:
                    row = (supabase.table("member_assets").select("content,title,asset_type,metrics")
                           .eq("member_id", member_id).eq("asset_type", atype).execute())
                    if row.data and (row.data[0].get("content") or "").strip():
                        a = row.data[0]
                        head = f"\n- ASSET UNDER REVIEW ({a['asset_type']}"
                        if a.get("title"): head += f": {a['title']}"
                        if a.get("metrics"): head += f" | metric: {a['metrics']}"
                        head += "):\n"
                        return head + (a["content"] or "")[:6000]
                break
    except Exception: pass
    return ""

def save_memory(member_id: str, question: str, answer: str):
    try:
        supabase.table("chat_history").insert({"member_id": member_id, "question": question, "answer": answer}).execute()
        supabase.table("members").update({"updated_at": datetime.now(timezone.utc).isoformat()}).eq("member_id", member_id).execute()
    except Exception as e:
        print(f"⚠️ MEMORY WRITE FAILED: {e}")

@app.post("/api/member/register")
async def register_member(profile: MemberProfile):
    try:
        row = {"member_id": profile.member_id, "name": profile.name, "niche": profile.niche,
               "current_stage": profile.current_stage, "struggles": profile.struggles,
               "business_context": profile.business_context,
               "updated_at": datetime.now(timezone.utc).isoformat()}
        supabase.table("members").upsert(row, on_conflict="member_id").execute()
        return {"status": "success", "member_id": profile.member_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Register failed: {e}")

@app.post("/api/assets")
async def save_asset(a: AssetSave):
    if a.asset_type not in ASSET_TYPES:
        raise HTTPException(status_code=400, detail="Unknown asset type")
    try:
        existing = (supabase.table("member_assets").select("id")
                    .eq("member_id", a.member_id).eq("asset_type", a.asset_type).execute())
        row = {"member_id": a.member_id, "asset_type": a.asset_type, "title": a.title,
               "content": a.content, "url": a.url, "metrics": a.metrics,
               "updated_at": datetime.now(timezone.utc).isoformat()}
        if existing.data:
            supabase.table("member_assets").update(row).eq("id", existing.data[0]["id"]).execute()
        else:
            supabase.table("member_assets").insert(row).execute()
        return {"status": "success", "asset_type": a.asset_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Asset save failed: {e}")

@app.get("/api/assets")
async def list_assets(member_id: str):
    try:
        rows = (supabase.table("member_assets")
                .select("asset_type,title,url,content,metrics,updated_at")
                .eq("member_id", member_id).execute())
        return {"assets": rows.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Asset list failed: {e}")

# ---------- VISION ----------
VISION_PROMPT = ("You are a top-tier direct-response funnel analyst. "
                 "This screenshot may be in Arabic — quote it as-is. Analyze: "
                 "1) page type; 2) exact headline; 3) promise/offer; 4) CTA; "
                 "5) trust elements; 6) top 3 weaknesses. Max 250 words.")

async def gemini_vision(b64: str, prompt: str) -> str:
    """Try multiple Gemini model IDs with real error capture."""
    last_err = "no vision model succeeded"
    # broad alias list — at least one will exist on the free tier
    for model in ["gemini-2.0-flash", "gemini-2.0-flash-exp",
                  "gemini-1.5-flash", "gemini-1.5-flash-latest",
                  "gemini-2.5-flash", "gemini-2.5-flash-lite",
                  "gemini-pro-vision", "gemini-1.0-pro-vision-latest"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/png", "data": b64}},
            ]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 600},
        }
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code == 200:
                    try:
                        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    except Exception:
                        return r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                last_err = f"{model}: HTTP {r.status_code} — {r.text[:200]}"
                print(f"Gemini {model}: {last_err}")
        except Exception as e:
            last_err = f"{model}: {str(e)[:200]}"
            print(f"Gemini {model} failure: {e}")
    raise HTTPException(status_code=500, detail=f"Gemini vision failed: {last_err}")

@app.post("/api/vision")
async def vision_analyze(req: VisionRequest):
    prompt = VISION_PROMPT + (f"\nMember context: {req.context}" if req.context else "")
    vision_model = VISION_CHOSEN or pick_vision_model()
    if vision_model:
        payload = {
            "model": vision_model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{req.image_b64}"}},
            ]}],
            "temperature": 0.3,
        }
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post("https://api.groq.com/openai/v1/chat/completions",
                                      json=payload, headers=headers)
                if r.status_code == 200:
                    return {"analysis": r.json()["choices"][0]["message"]["content"]}
                last_err = f"Groq: {r.text[:200]}"
                print(f"Groq vision error: {r.text}")
        except Exception as e:
            last_err = f"Groq exception: {str(e)[:200]}"
            print(f"Groq vision failure: {e}")
    if GEMINI_KEY:
        try:
            analysis = await gemini_vision(req.image_b64, prompt)
            return {"analysis": analysis}
        except HTTPException as e:
            last_err = e.detail
    raise HTTPException(status_code=500, detail=last_err if 'last_err' in locals() else "No vision engine available")

@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    try:
        coach = (req.coach_id or "e5").strip().lower()
        lang = (req.language or "en").strip().lower()
        lang_note = ("\n\n[SYSTEM: Respond ENTIRELY in Arabic. Keep framework names like TRUST in English.]"
                     if lang.startswith("ar") else "\n\n[SYSTEM: Respond in English.]")
        use_retriever = builder_retriever if coach == "builder" else retriever
        use_prompt = BUILDER_PROMPT if coach == "builder" else E5_PROMPT
        memory_block = "MEMBER MEMORY: (no member)"
        if req.member_id:
            ensure_member(req.member_id)
            memory_block = build_memory_block(req.member_id)
            memory_block += find_asset_review(req.member_id, req.question)
            if req.vision_analysis:
                memory_block += f"\n- SCREENSHOT UNDER REVIEW (vision analysis):\n{req.vision_analysis[:6000]}"
                atype = "other"
                ql = req.question.lower()
                for types, kws in ASSET_KEYWORDS:
                    if any(k in ql for k in kws):
                        atype = types[0]; break
                try:
                    existing = (supabase.table("member_assets").select("id")
                                .eq("member_id", req.member_id).eq("asset_type", atype).execute())
                    row = {"member_id": req.member_id, "asset_type": atype,
                           "title": "Screenshot analysis", "content": req.vision_analysis[:6000],
                           "updated_at": datetime.now(timezone.utc).isoformat()}
                    if existing.data:
                        supabase.table("member_assets").update(row).eq("id", existing.data[0]["id"]).execute()
                    else:
                        supabase.table("member_assets").insert(row).execute()
                except Exception: pass
        docs = use_retriever.invoke(req.question)
        context = format_docs(docs)
        answer = (use_prompt | llm | StrOutputParser()).invoke({
            "memory": memory_block, "context": context, "question": req.question + lang_note,
        })
        if req.member_id: save_memory(req.member_id, req.question, answer)
        return {"status": "success", "answer": answer, "member_id": req.member_id, "coach": coach}
    except Exception as e:
        print(f"❌ RAG FAILURE: {e}")
        raise HTTPException(status_code=500, detail=f"RAG failed: {e}")

@app.post("/api/tts")
async def text_to_speech(req: dict):
    text = (req.get("text") or "").strip()
    lang = (req.get("language") or "en").strip().lower()
    if not text: raise HTTPException(status_code=400, detail="Empty text")
    if ELEVEN_KEY:
        voice_id = "pNInz6obpgDQGcFmaJgB"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"}
        payload = {"text": text, "model_id": "eleven_multilingual_v2",
                   "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200: raise HTTPException(status_code=500, detail="Voice failed")
            return Response(content=r.content, media_type="audio/mpeg")
    voice = "ar-SA-HamedNeural" if lang.startswith("ar") else "en-US-ChristopherNeural"
    try:
        buf = io.BytesIO()
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": buf.write(chunk["data"])
        return Response(content=buf.getvalue(), media_type="audio/mpeg")
    except Exception as e:
        print(f"❌ TTS FAILURE: {e}")
        raise HTTPException(status_code=500, detail="Voice failed")

@app.post("/api/stt")
async def speech_to_text(file: UploadFile = File(...), language: str = Form("en")):
    audio_bytes = await file.read()
    files = {"file": (file.filename or "voice.webm", audio_bytes, file.content_type or "audio/webm")}
    data = {"model": "whisper-large-v3"}
    if (language or "en").lower().startswith("ar"): data["language"] = "ar"
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post("https://api.groq.com/openai/v1/audio/transcriptions",
                                  headers=headers, files=files, data=data)
            if r.status_code != 200: raise HTTPException(status_code=500, detail="Transcription failed")
            return {"text": r.json().get("text", "")}
    except HTTPException: raise
    except Exception as e:
        print(f"❌ STT FAILURE: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")

if __name__ == "__main__":
    print(f"🔥 MODEL: {CHOSEN_MODEL} | VISION: {VISION_CHOSEN or ('gemini' if GEMINI_KEY else 'none')}")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
