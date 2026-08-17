import os
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

APP_VERSION = "2026-08-12-aicoach-slice2-memory-v4"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health():
    return {"status": "ok", "version": APP_VERSION}

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

# FIX APPLIED HERE: Changed to llama3-70b-8192
llm = ChatGroq(
    model_name="llama3-70b-8192",
    temperature=0.2,
    api_key=os.getenv("GROQ_API_KEY").strip(),
)

retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

prompt = ChatPromptTemplate.from_template("""You are the Master AI Coach for the E5 C.A.M.P. Masterclass.
Your goal is NOT to just give a quick answer, but to COACH the member using the E5 frameworks.

RULES:
1. Identify which E5 tool applies (e.g., W.E.B., Awareness Pyramid, 4 Sales, Big Idea, MVF, CPCmos).
2. Give a powerful insight using the exact E5 terminology (in the language of the question).
3. CRITICAL: End your response by asking the member 1 or 2 specific diagnostic questions.
4. Never invent facts. Use ONLY the course context provided.
5. If MEMBER MEMORY exists below, personalize your answer using their niche, stage, and past struggles. Reference their past sessions when relevant.

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
    existing = (
        supabase.table("members")
        .select("member_id")
        .eq("member_id", member_id)
        .execute()
    )
    if not existing.data:
        supabase.table("members").insert({"member_id": member_id}).execute()

def build_memory_block(member_id: str) -> str:
    try:
        prof = (
            supabase.table("members").select("*").eq("member_id", member_id).execute()
        )
        hist = (
            supabase.table("chat_history")
            .select("question, answer, created_at")
            .eq("member_id", member_id)
            .order("created_at", desc=True)
            .limit(3)
            .execute()
        )
    except Exception as e:
        print(f"⚠️ MEMORY READ FAILED: {e}")
        return "MEMBER MEMORY: (unavailable)"

    if not prof.data:
        return "MEMBER MEMORY: (new member, no profile yet)"

    p = prof.data[0]
    lines = ["MEMBER MEMORY (use this to personalize):"]
    if p.get("name"):
        lines.append(f"- Name: {p['name']}")
    if p.get("niche"):
        lines.append(f"- Niche/Business: {p['niche']}")
    if p.get("current_stage"):
        lines.append(f"- Current funnel stage: {p['current_stage']}")
    if p.get("struggles"):
        lines.append(f"- Known struggles: {p['struggles']}")
    if hist.data:
        lines.append("- Recent coaching sessions:")
        for h in reversed(hist.data):
            lines.append(
                f'  * Member asked: "{(h["question"] or "")[:150]}" -> You advised: "{(h["answer"] or "")[:150]}"'
            )
    return "\n".join(lines)

def save_memory(member_id: str, question: str, answer: str):
    try:
        supabase.table("chat_history").insert(
            {
                "member_id": member_id,
                "question": question,
                "answer": answer,
            }
        ).execute()
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
            "member_id": profile.member_id,
            "name": profile.name,
            "niche": profile.niche,
            "current_stage": profile.current_stage,
            "struggles": profile.struggles,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        supabase.table("members").upsert(row, on_conflict="member_id").execute()
        return {"status": "success", "member_id": profile.member_id}
    except Exception as e:
        print(f"❌ REGISTER FAILURE: {e}")
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
        answer = (prompt | llm | StrOutputParser()).invoke(
            {
                "memory": memory_block,
                "context": context,
                "question": req.question,
            }
        )

        if req.member_id:
            save_memory(req.member_id, req.question, answer)

        return {"status": "success", "answer": answer, "member_id": req.member_id}
    except Exception as e:
        print(f"❌ RAG FAILURE: {e}")
        raise HTTPException(status_code=500, detail=f"RAG failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))