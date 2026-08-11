import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_groq import ChatGroq
from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# LAW 0 & 3: MASTER CONFIG + LIVENESS PROBE
APP_VERSION = "2026-08-11-aicoach-slice1-v2"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/")
def health():
    return {"status": "ok", "version": APP_VERSION}

# DATABASE + RAG
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
embeddings = FastEmbedEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")
vectorstore = SupabaseVectorStore(
    client=supabase, embedding=embeddings,
    table_name="course_embeddings", query_name="match_documents",
)
llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.2,
               api_key=os.getenv("GROQ_API_KEY"))

# LAW 1: THE ARTIFACT
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
prompt = ChatPromptTemplate.from_template("""You are an expert AI business coach for the E5 Method community.
Answer using ONLY the context below. If the context is not enough, say so honestly.
Be concise, encouraging, actionable. Answer in the same language as the question.

Context:
{context}

Question:
{question}

Answer:""")

def format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)

rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt | llm | StrOutputParser()
)

class ChatRequest(BaseModel):
    question: str

@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    try:
        return {"status": "success", "answer": rag_chain.invoke(req.question)}
    except Exception as e:
        print(f"❌ RAG PIPELINE FAILURE: {e}")
        raise HTTPException(status_code=500, detail=f"RAG failed: {e}")

# REPLIT-AWARE RUNNER
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))