import os
import google.generativeai as genai
from supabase import create_client, Client
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables (works locally and in GitHub Actions)
load_dotenv()

# Initialize API Keys
GEMINI_API_KEY = os.getenv("AQ.Ab8RN6LWU9S8X5qOEqtMcNHblYU4SfmpHn7Su7XzwgJQAV7mMA")
SUPABASE_URL = os.getenv("https://abcdefgh.supabase.co")
SUPABASE_KEY = os.getenv("sb_secret_oyrzdG6BI_KPfB4Za-D_UQ_V6e_TR8f")

if not GEMINI_API_KEY or not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing API keys. Check your environment variables or GitHub Secrets.")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CONFIGURATION ---
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
EMBEDDING_DIMENSIONS = 1536 

def chunk_text(text, source_file, framework_name, category):
    """Splits text into overlapping chunks and tags with category."""
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        
        if end < text_length:
            newline_pos = chunk.rfind('\n')
            if newline_pos > CHUNK_SIZE * 0.5:
                end = start + newline_pos
                chunk = text[start:end]
        
        chunks.append({
            "source_file": source_file,
            "framework_name": framework_name,
            "category": category,
            "content": chunk.strip()
        })
        start = end - CHUNK_OVERLAP
    return chunks

def get_gemini_embedding(text):
    """Generates vector embedding using Gemini's text-embedding-004 model."""
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            output_dimensionality=EMBEDDING_DIMENSIONS
        )
        return result['embedding']
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def ingest_file(filepath):
    """Reads a file, clears old chunks, and uploads new ones to Supabase."""
    path = Path(filepath)
    filename = path.name
    category = path.parent.name 
    
    framework_name = filename.replace('.md', '').replace('.txt', '').replace('_', ' ').title()
    
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # CI/CD UPGRADE: Delete existing chunks for this file to prevent duplicates on update
    print(f"Clearing old chunks for {filename}...")
    supabase.table("knowledge_chunks").delete().eq("source_file", filename).execute()
    
    chunks = chunk_text(text, filename, framework_name, category)
    print(f"Processing [{category}] -> {filename}: {len(chunks)} new chunks created.")
    
    for chunk in chunks:
        embedding = get_gemini_embedding(chunk["content"])
        
        if embedding:
            try:
                supabase.table("knowledge_chunks").insert({
                    "source_file": chunk["source_file"],
                    "framework_name": chunk["framework_name"],
                    "category": chunk["category"],
                    "content": chunk["content"],
                    "embedding": embedding
                }).execute()
            except Exception as e:
                print(f"Error inserting chunk into Supabase: {e}")

def main():
    base_path = Path("knowledge")
    files = list(base_path.rglob("*.md")) + list(base_path.rglob("*.txt"))
    
    if not files:
        print("No .md or .txt files found in 'knowledge/' subfolders.")
        return

    print(f"Starting cloud ingestion of {len(files)} files...")
    for file in files:
        ingest_file(str(file))
    print("✅ Cloud ingestion complete! AI Brain updated successfully.")

if __name__ == "__main__":
    main()
