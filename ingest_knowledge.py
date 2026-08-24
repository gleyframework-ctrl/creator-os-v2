import os
import glob
import google.generativeai as genai
from supabase import create_client, Client
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

# Initialize API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not GEMINI_API_KEY or not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing API keys in .env file. Check GEMINI_API_KEY, SUPABASE_URL, and SUPABASE_SERVICE_KEY.")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CONFIGURATION ---
CHUNK_SIZE = 1000  # Characters per chunk
CHUNK_OVERLAP = 200 # Overlap to maintain context
EMBEDDING_DIMENSIONS = 1536 

def chunk_text(text, source_file, framework_name, category):
    """Splits text into overlapping chunks and tags with category."""
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        
        # Try to break at a newline to avoid cutting sentences in half
        if end < text_length:
            newline_pos = chunk.rfind('\n')
            if newline_pos > CHUNK_SIZE * 0.5:
                end = start + newline_pos
                chunk = text[start:end]
        
        chunks.append({
            "source_file": source_file,
            "framework_name": framework_name,
            "category": category, # NEW: Tags the data with the subfolder name
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
        print(f"Error generating embedding for chunk: {e}")
        return None

def ingest_file(filepath):
    """Reads a file, chunks it, and uploads to Supabase."""
    path = Path(filepath)
    filename = path.name
    category = path.parent.name # Gets the subfolder name (e.g., 'sales_and_closing')
    
    # Extract framework name from filename
    framework_name = filename.replace('.md', '').replace('.txt', '').replace('_', ' ').title()
    
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    chunks = chunk_text(text, filename, framework_name, category)
    print(f"Processing [{category}] -> {filename}: {len(chunks)} chunks created.")
    
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
    # Recursively find all .md and .txt files in all subfolders inside 'knowledge/'
    files = glob.glob("knowledge/**/*.md", recursive=True) + glob.glob("knowledge/**/*.txt", recursive=True)
    
    if not files:
        print("No .md or .txt files found in 'knowledge/' subfolders. Please add your framework files.")
        return

    print(f"Starting Gemini ingestion of {len(files)} files across subfolders... This may take a few minutes.")
    for file in files:
        ingest_file(file)
    print("✅ Ingestion complete! Your AI Coach now has a categorized vector memory.")

if __name__ == "__main__":
    main()
