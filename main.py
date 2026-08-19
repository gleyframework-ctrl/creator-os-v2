import os
import httpx
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
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

APP_VERSION = "2026-08-19-aicoach-v8-realcoach"

# ---------- SELF-HEALING MODEL DISCOVERY ----------
GROQ_KEY = os.getenv("GROQ_API_KEY").strip()

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
                print(f"🔥 DISCOVERED LIVE MODEL: {model}")
                return model
        if available:
            fallback = sorted(available)[0]
            print(f"🔥 NO PREFERRED MODEL LIVE. USING FIRST AVAILABLE: {fallback}")
            return fallback
        print("⚠️ MODEL LIST EMPTY. USING DEFAULT.")
        return PREFERRED_MODELS[0]
    except Exception as e:
        print(f"⚠️ MODEL DISCOVERY FAILED: {e}")
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
    return {"status": "ok", "version": APP_VERSION, "model": CHOSEN_MODEL}

@app.get("/test")
def test_page():
    return FileResponse("chat_test.html")

# ---------- CLIENTS ----------
supabase = create_client(
    os.getenv("SUPABASE_URL").strip(), os.getenv("SUPABASE_SERVICE_KEY").strip()
)
embeddings = FastEmbedEmbeddings()
vectorstore = SupabaseVectorStore(
    client=supabase,
    embedding=embeddings,
    table_name="course_embeddings",
    query_name="match_documents",
)

llm = ChatGroq(
    model_name=CHOSEN_MODEL,
    temperature=0.4,
    api_key=GROQ_KEY,
)

retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

prompt = ChatPromptTemplate.from_template("""You are the Master AI Coach for the E5 C.A.M.P. Masterclass — a world-class business coach trained in the Socratic method and ICF-level coaching. You are NOT a professor and NOT a textbook. You COACH.

ABSOLUTE RULES (breaking any of them = failure):

1. DIAGNOSE BEFORE PRESCRIBING. If the member mentions a piece of work (headline, funnel, offer, ad) but has NOT shown it, your FIRST job is to ask them to paste it. Never give generic advice about unseen work.

2. PERSONALIZE WITH MEMORY. If you know the member's niche, EVERY example must use THEIR niche (a fitness-for-dads coach gets fitness-for-dads examples — never SaaS or generic business). Reference their past sessions when relevant.

3. ONE INSIGHT PER RESPONSE. Pick the SINGLE most powerful lever for their situation. Explain it in 2-4 sentences, then apply it directly to THEIR case. Depth over breadth. Never dump an entire framework.

4. APPLY, DON'T RECITE. Use E5 tools invisibly. Say "your headline is missing the Promise — the concrete result" — do NOT recite full acronym lectures like "CPCmos stands for Copy-Promise-Credibility...".

5. 60% QUESTIONS, 40% INSIGHT. End EVERY response with 1-2 sharp, specific diagnostic questions about THEIR real business. Never generic questions.

6. REWRITE TOGETHER. When they share their work, show a concrete BEFORE/AFTER rewrite live, then ask: "Which version feels more like you?" Coaching is a dialogue, not a monologue.

7. SHORT AND HUMAN. 150-250 words max. Short paragraphs. No giant tables or essays unless explicitly asked. Talk like a wise friend over coffee.

8. NEVER INVENT. Use ONLY the course context provided. If the context doesn't cover the topic, say so honestly and coach from first principles.

9. LANGUAGE. Respond in the language the member writes in (English or Arabic).

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

class MemberProfile(BaseModel):
    member_id: str
    name: Optional[str] = None
    niche: Optional[str] = None
    current_stage: Optional[str] = None
    struggles: Optional[str] = None

# ---------- MEMORY HELPERS ----------
def ensure_member(member_id: str):
    existing = supabase.table("members").select("member_id").eq("member_id", member_id).execute()
    if not existing.data:
        supabase.table("members").insert({"member_id": member_id}).execute()

def build_memory_block(member_id: str) -> str:
    try:
        prof = supabase.table("members").select("*").eq("member_id", member_id).execute()
        hist = (supabase.table("chat_history").select("question, answer, created_at")
                .eq("member_id", member_id).order("created_at", desc=True).limit(3).execute())
    except Exception as e:
        return "MEMBER MEMORY: (unavailable)"

    if not prof.data:
        return "MEMBER MEMORY: (new member, no profile yet)"

    p = prof.data[0]
    lines = ["MEMBER MEMORY (use this to personalize):"]
    if p.get("name"): lines.append(f"- Name: {p['name']}")
    if p.get("niche"): lines.append(f"- Niche/Business: {p['niche']}")
    if p.get("current_stage"): lines.append(f"- Current funnel stage: {p['current_stage']}")
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
        memory_block = "MEMBER MEMORY: (no member attached - generic coaching)"
        if req.member_id:
            ensure_member(req.member_id)
            memory_block = build_memory_block(req.member_id)

        docs = retriever.invoke(req.question)
        context = format_docs(docs)
        answer = (prompt | llm | StrOutputParser()).invoke({
            "memory": memory_block, "context": context, "question": req.question,
        })

        if req.member_id:
            save_memory(req.member_id, req.question, answer)

        return {"status": "success", "answer": answer, "member_id": req.member_id}
    except Exception as e:
        print(f"❌ RAG FAILURE: {e}")
        raise HTTPException(status_code=500, detail=f"RAG failed: {e}")

if __name__ == "__main__":
    print(f"🔥 SERVER STARTING WITH MODEL: {CHOSEN_MODEL}")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
