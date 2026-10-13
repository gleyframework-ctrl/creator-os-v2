# knowledge_loader.py — reads .md frameworks from knowledge/foundation/
import os, re
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge" / "foundation"
_cache = {}

def _load_all():
    if _cache:
        return _cache
    files = {}
    if not KNOWLEDGE_DIR.exists():
        print(f"[KNOWLEDGE] Folder not found: {KNOWLEDGE_DIR}")
        return files
    for md_path in KNOWLEDGE_DIR.rglob("*.md"):
        try:
            text = md_path.read_text(encoding="utf-8", errors="ignore")
            rel = md_path.relative_to(KNOWLEDGE_DIR)
            category = rel.parts[0] if len(rel.parts) > 1 else "misc"
            name = md_path.stem
            files[str(rel)] = {
                "category": category,
                "name": name,
                "text": text,
                "preview": text[:4000],
            }
        except Exception as e:
            print(f"[KNOWLEDGE] Skip {md_path}: {e}")
    _cache.update(files)
    print(f"[KNOWLEDGE] Loaded {len(files)} framework files")
    return _cache


SYNONYMS = {
    "dm": ["dm", "dms", "message", "messages", "reply", "replies", "outreach", "inbox", "messenger"],
    "dm_copy": ["dm", "micro-copy", "microcopy", "message", "hook"],
    "offer": ["offer", "pricing", "package", "price", "value"],
    "content": ["content", "post", "posts", "video", "reel", "hook", "short-form"],
    "community": ["community", "group", "engagement", "members", "audit"],
    "launch": ["launch", "webinar", "challenge", "waitlist", "promo"],
    "funnel": ["funnel", "conversion", "bottleneck", "ltv", "cvj"],
    "psychology": ["psychology", "persuasion", "system 1", "system 2", "cognitive", "bias"],
    "sales": ["sales", "closing", "call", "objection", "script"],
    "copy": ["copy", "copywriting", "story", "storytelling", "email"],
    "brand": ["brand", "positioning", "message", "voice"],
}

def _expand(words):
    expanded = set(words)
    for w in list(words):
        for key, syns in SYNONYMS.items():
            if w == key or w in syns:
                expanded.update(syns)
    return expanded

def search(query, top_k=3):
    files = _load_all()
    q_words = set(re.findall(r"\w+", query.lower()))
    q_words = _expand(q_words)
    if not q_words:
        return []
    scored = []
    for key, f in files.items():
        name_lower = f["name"].lower()
        cat_lower = f["category"].lower()
        body = f["text"][:6000].lower()
        # Boost filename matches heavily
        name_words = set(re.findall(r"\w+", name_lower))
        cat_words = set(re.findall(r"\w+", cat_lower))
        body_words = set(re.findall(r"\w+", body))
        score = (
            len(q_words & name_words) * 10 +
            len(q_words & cat_words) * 5 +
            len(q_words & body_words) * 1
        )
        if score > 0:
            scored.append((score, f))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [f for _, f in scored[:top_k]]

def get_context(query, top_k=3, max_chars_per_file=3000):
    results = search(query, top_k)
    if not results:
        return ""
    parts = []
    for f in results:
        parts.append("### Source: " + f["name"] + " (" + f["category"] + ")\n" + f["preview"][:max_chars_per_file])
    return "\n\n---\n\n".join(parts)

def list_all():
    files = _load_all()
    return [{"name": f["name"], "category": f["category"]} for f in files.values()]
