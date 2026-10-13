"""
Framework Search — BM25 keyword retrieval for 403 framework files.
Zero dependencies. Pure Python.
"""
import os
import re
import math
from collections import Counter

FRAMEWORK_DIR = os.environ.get("FRAMEWORK_DIR", "/app/knowledge/foundation")


class BM25:
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.corpus = []
        self.doc_len = []
        self.avgdl = 0
        self.idf = {}
        self.N = 0
        self.docs_meta = []

    def tokenize(self, text):
        text = text.lower()
        tokens = re.findall(r'[a-z0-9\u0600-\u06FF]+', text)
        return tokens

    def fit(self, documents, metas=None):
        self.corpus = [self.tokenize(doc) for doc in documents]
        self.N = len(self.corpus)
        self.doc_len = [len(doc) for doc in self.corpus]
        self.avgdl = sum(self.doc_len) / self.N if self.N > 0 else 0
        self.docs_meta = metas or [{} for _ in range(self.N)]

        df = Counter()
        for doc in self.corpus:
            for token in set(doc):
                df[token] += 1

        self.idf = {}
        for token, freq in df.items():
            self.idf[token] = math.log((self.N - freq + 0.5) / (freq + 0.5) + 1)

    def search(self, query, top_k=5):
        if self.N == 0:
            return []
        query_tokens = self.tokenize(query)
        scores = []
        for i, doc in enumerate(self.corpus):
            score = 0.0
            doc_counter = Counter(doc)
            for token in query_tokens:
                if token not in self.idf:
                    continue
                tf = doc_counter[token]
                idf = self.idf[token]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                score += idf * numerator / denominator
            if score > 0:
                scores.append((score, i))
        scores.sort(reverse=True)
        return scores[:top_k]


_index = None
_documents = []
_metas = []


def _chunk_text(text, chunk_size=800, overlap=100):
    words = text.split()
    if len(words) <= chunk_size:
        return [text]
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def build_index(framework_dir=None):
    global _index, _documents, _metas
    fdir = framework_dir or FRAMEWORK_DIR
    if not os.path.isdir(fdir):
        print(f"FRAMEWORK DIR NOT FOUND: {fdir}")
        _index = BM25()
        _index.fit([])
        return

    files_found = 0
    for root, dirs, files in os.walk(fdir):
        for fname in files:
            if not fname.endswith(('.md', '.txt', '.markdown')):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue

            rel = os.path.relpath(fpath, fdir)
            category = rel.split(os.sep)[0] if os.sep in rel else 'root'

            for chunk in _chunk_text(content):
                _documents.append(chunk)
                _metas.append({'file': rel, 'category': category})
            files_found += 1

    _index = BM25()
    _index.fit(_documents, _metas)
    print(f"FRAMEWORK INDEX BUILT: {len(_documents)} chunks from {files_found} files")


def search_frameworks(query, top_k=4, max_chars=3000):
    global _index
    if _index is None:
        try:
            build_index()
        except Exception as e:
            print(f"Auto-build index failed: {e}")
            return ""
    results = _index.search(query, top_k=top_k)
    if not results:
        return ""
    out = []
    total = 0
    for score, idx in results:
        meta = _metas[idx]
        chunk = _documents[idx]
        excerpt = chunk[:1200]
        block = f"[Source: {meta.get('file', 'unknown')} | {meta.get('category', '')}]\n{excerpt}"
        if total + len(block) > max_chars:
            break
        out.append(block)
        total += len(block)
    return "\n\n---\n\n".join(out)
