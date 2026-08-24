import os
import glob
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Initialize Clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

# Configuration
CHUNK_SIZE = 1000  # Characters per chunk
CHUNK_OVERLAP = 200 # Overlap to maintain context

def chunk_text(text, source_file, framework_name):
    """Splits text into overlapping chunks."""
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
            "content": chunk.strip()
        })
        start = end - CHUNK_OVERLAP
    return chunks

def get_embedding(text):
    """Generates vector embedding using OpenAI."""
    response = openai_client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def ingest_file(filepath):
    """Reads a file, chunks it, and uploads to Supabase."""
    filename = os.path.basename(filepath)
    # Extract framework name from filename (e.g., "01_sales_expert_dan_lok.md" -> "Sales Expert Dan Lok")
    framework_name = filename.replace('.md', '').replace('.txt', '').replace('_', ' ').title()
    
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    chunks = chunk_text(text, filename, framework_name)
    print(f"Processing {filename}: {len(chunks)} chunks created.")
    
    for chunk in chunks:
        try:
            embedding = get_embedding(chunk["content"])
            supabase.table("knowledge_chunks").insert({
                "source_file": chunk["source_file"],
                "framework_name": chunk["framework_name"],
                "content": chunk["content"],
                "embedding": embedding
            }).execute()
        except Exception as e:
            print(f"Error inserting chunk: {e}")

def main():
    # Ingest all .md and .txt files in the 'knowledge' folder
    files = glob.glob("knowledge/*.md") + glob.glob("knowledge/*.txt")
    
    if not files:
        print("No files found in 'knowledge' folder. Please add your framework files.")
        return

    print(f"Starting ingestion of {len(files)} files...")
    for file in files:
        ingest_file(file)
    print("Ingestion complete! Your AI Coach now has a vector memory.")

if __name__ == "__main__":
    main()
