"""Simple keyword search over the files in the knowledge_base folder."""
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from config.settings import BASE_DIR

KB_DIR = BASE_DIR / "knowledge_base"
MAX_CHARS = 1200
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "be", "by", "with",
    "as", "at", "it", "that", "this", "from", "which", "when", "if", "not", "no", "their", "its",
}


@dataclass(frozen=True)
class Chunk:
    source: str
    location: str
    text: str


def _stem(token: str) -> str:
    if token.endswith("sses") and len(token) > 5:
        return token[:-2]
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def _tokenize(text: str) -> list:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [_stem(w) for w in words if w not in STOPWORDS and len(w) > 1]


def _split_long(body: str) -> list:
    parts, current = [], ""
    for paragraph in re.split(r"\n\s*\n", body):
        if current and len(current) + len(paragraph) > MAX_CHARS:
            parts.append(current.strip())
            current = ""
        current += paragraph + "\n\n"
    if current.strip():
        parts.append(current.strip())
    return parts


def _chunks_from_text(name: str, text: str) -> list:
    sections, title, buffer = [], "Introduction", []
    for line in text.splitlines():
        if line.startswith("#"):
            if buffer:
                sections.append((title, "\n".join(buffer).strip()))
            title, buffer = line.lstrip("#").strip(), []
        else:
            buffer.append(line)
    if buffer:
        sections.append((title, "\n".join(buffer).strip()))
    chunks = []
    for title, body in sections:
        for part in _split_long(body) if body else []:
            chunks.append(Chunk(name, title, f"{title}. {part}"))
    return chunks


def _chunks_from_pdf(path) -> list:
    import fitz  # PyMuPDF

    chunks = []
    with fitz.open(path) as doc:
        for number, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            for part in _split_long(text) if text else []:
                chunks.append(Chunk(path.name, f"page {number}", part))
    return chunks


def _signature() -> tuple:
    if not KB_DIR.exists():
        return ()
    files = [p for p in sorted(KB_DIR.iterdir())
             if p.suffix.lower() in (".md", ".txt", ".pdf") and p.name.lower() != "readme.md"]
    return tuple((p.name, p.stat().st_mtime) for p in files)


@lru_cache(maxsize=1)
def _index(signature: tuple):
    chunks = []
    for name, _ in signature:
        path = KB_DIR / name
        try:
            if path.suffix.lower() == ".pdf":
                chunks += _chunks_from_pdf(path)
            else:
                chunks += _chunks_from_text(name, path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue  # one bad file should not stop the others
    counters = [Counter(_tokenize(c.text)) for c in chunks]
    doc_freq = Counter()
    for counter in counters:
        doc_freq.update(counter.keys())
    n = len(chunks)
    idf = {term: math.log((n + 1) / (df + 1)) + 1 for term, df in doc_freq.items()}
    return chunks, counters, idf


def list_sources() -> list:
    return [name for name, _ in _signature()]


def search_knowledge(query: str, k: int = 3) -> list:
    chunks, counters, idf = _index(_signature())
    terms = set(_tokenize(query))
    scored = []
    for chunk, counter in zip(chunks, counters):
        score = sum((1 + math.log(counter[t])) * idf.get(t, 0.0) for t in terms if counter.get(t))
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:k]]
