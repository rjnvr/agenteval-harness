import re

TOKEN_RE = re.compile(r"[a-z0-9$,.%-]+")


def tokenize(text: str) -> set[str]:
    return {token.strip(".,").lower() for token in TOKEN_RE.findall(text.lower()) if len(token) > 2}


def chunk_text(text: str, max_words: int = 85) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        if len(current) + len(words) > max_words and current:
            chunks.append(" ".join(current))
            current = []
        current.extend(words)
    if current:
        chunks.append(" ".join(current))
    return chunks or [text]


def retrieve_chunks(document_text: str, question: str, top_k: int = 3) -> list[str]:
    query_terms = tokenize(question)
    scored = []
    for chunk in chunk_text(document_text):
        chunk_terms = tokenize(chunk)
        overlap = len(query_terms & chunk_terms)
        scored.append((overlap, len(chunk_terms), chunk))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [chunk for _, _, chunk in scored[:top_k]]

