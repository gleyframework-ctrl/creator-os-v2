import os, glob
from dotenv import load_dotenv
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from supabase import create_client

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
embeddings = FastEmbedEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

files = glob.glob("knowledge/*.txt")
if not files:
    raise SystemExit("❌ FAIL LOUDLY: knowledge/ folder is empty. Add a .txt and re-run.")

for path in files:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    docs = splitter.create_documents([text], metadatas=[{"source": os.path.basename(path)}])
    print(f"Ingesting {os.path.basename(path)} -> {len(docs)} chunks")
    SupabaseVectorStore.from_documents(docs, embeddings, client=supabase,
        table_name="course_embeddings", query_name="match_documents")

print("✅ Ingestion complete. The coach has a brain.")