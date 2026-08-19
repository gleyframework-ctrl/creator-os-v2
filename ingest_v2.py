import os
from supabase import create_client
from langchain_community.embeddings import FastEmbedEmbeddings
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL").strip(), os.getenv("SUPABASE_SERVICE_KEY").strip()
)
embeddings = FastEmbedEmbeddings()

def parse_chunk_file(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    meta = {}
    body_lines = []
    header_done = False
    for line in text.splitlines():
        if not header_done:
            if line.startswith("CHUNK:"):
                meta["title"] = line.split(":", 1)[1].strip()
                continue
            if line.startswith("CATEGORY:"):
                meta["category"] = line.split(":", 1)[1].strip()
                continue
            if line.startswith("SOURCE:"):
                meta["source"] = line.split(":", 1)[1].strip()
                continue
            if line.strip() == "---":
                header_done = True
                continue
        body_lines.append(line)
    return meta, "\n".join(body_lines).strip()

def main():
    folder = "knowledge"
    count = 0
    for fname in sorted(os.listdir(folder)):
        if not fname.startswith("ttb_"):
            continue
        meta, body = parse_chunk_file(os.path.join(folder, fname))
        if not body:
            continue
        existing = (supabase.table("builder_embeddings")
                    .select("id")
                    .filter("metadata->>title", "eq", meta.get("title", ""))
                    .execute())
        if existing.data:
            print(f"⏭️  ALREADY IN VAULT: {fname}")
            continue
        vec = embeddings.embed_query(body)
        supabase.table("builder_embeddings").insert({
            "content": body,
            "metadata": {
                "title": meta.get("title", ""),
                "source": meta.get("source", ""),
                "category": meta.get("category", "builder"),
            },
            "embedding": vec,
        }).execute()
        count += 1
        print(f"✅ INGESTED: {fname} -> builder_embeddings")
    print(f"🎉 DONE. {count} new builder chunk(s) ingested.")

if __name__ == "__main__":
    main()
