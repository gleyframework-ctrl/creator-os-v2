import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

APP_VERSION = "2026-08-11-aicoach-slice1-v3"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/")
def health():
    return {"status": "ok", "version": APP_VERSION}

@app.get("/test")
def test_page():
    return FileResponse("chat_test.html")

supabase = create_client(os.getenv("SUPABASE_URL").strip(), os.getenv("SUPABASE_SERVICE_KEY").strip())
embeddings = FastEmbedEmbeddings()
vectorstore = SupabaseVectorStore(
    client=supabase, embedding=embeddings,
    table_name="course_embeddings", query_name="match_documents",
)
llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.2,
               api_key=os.getenv("GROQ_API_KEY").strip())

retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
prompt = ChatPromptTemplate.from_template("""You are an expert AI business coach. Answer using ONLY the context. Be concise. Answer in the same language as the question.
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
        print(f"❌ RAG FAILURE: {e}")
        raise HTTPException(status_code=500, detail=f"RAG failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))