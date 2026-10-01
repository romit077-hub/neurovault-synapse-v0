from dataclasses import dataclass

from app.ingestion.files import ExtractedSection


@dataclass(frozen=True)
class Chunk:
    text: str
    source_ref: str
    start_char: int


def chunk_sections(sections: list[ExtractedSection], size: int = 850, overlap: int = 150) -> list[Chunk]:
    if size < 10 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk size must exceed overlap")
    result: list[Chunk] = []
    for section in sections:
        text = " ".join(section.text.split())
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + size // 2, end)
                if boundary > start:
                    end = boundary
            part = text[start:end].strip()
            if part:
                result.append(Chunk(part, section.source_ref, start))
            if end == len(text):
                break
            next_start = max(start + 1, end - overlap)
            # Resume at a word boundary, while guaranteeing progress.
            space = text.find(" ", next_start, min(end + 1, len(text)))
            start = space + 1 if space != -1 else next_start
    return result
