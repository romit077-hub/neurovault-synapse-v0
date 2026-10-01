from dataclasses import dataclass
from io import BytesIO
from pathlib import PureWindowsPath
import re
import unicodedata
from zipfile import BadZipFile, ZipFile

import pymupdf
from docx import Document


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 500_000
MAX_PDF_PAGES = 100
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
ALLOWED_MIME = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
}


class InvalidUpload(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedSection:
    text: str
    source_ref: str


def safe_filename(name: str) -> str:
    base = PureWindowsPath(name.replace("/", "\\")).name
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    if not base or base.startswith("."):
        raise InvalidUpload("Choose a regular PDF, DOCX, or TXT filename")
    if len(base) > 100 and "." in base:
        stem, extension = base.rsplit(".", 1)
        base = stem[:99 - len(extension)] + "." + extension
    return base[:100]


def validate_upload(name: str, mime: str | None, data: bytes) -> tuple[str, str]:
    filename = safe_filename(name)
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise InvalidUpload("Only PDF, DOCX, and TXT files are supported")
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise InvalidUpload("File must be nonempty and at most 10 MiB")
    if mime and mime.lower().split(";", 1)[0].strip() not in ALLOWED_MIME[extension]:
        raise InvalidUpload("The file's declared content type does not match its extension")
    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise InvalidUpload("File content is not a PDF")
    if extension == ".docx":
        if not data.startswith(b"PK\x03\x04"):
            raise InvalidUpload("File content is not a DOCX")
        try:
            with ZipFile(BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 1500 or sum(item.file_size for item in entries) > 30 * 1024 * 1024:
                    raise InvalidUpload("DOCX archive is too large after decompression")
                names = {item.filename.lower() for item in entries}
                if "word/document.xml" not in names or "[content_types].xml" not in names:
                    raise InvalidUpload("DOCX archive is missing required document parts")
                if any("vbaproject.bin" in name for name in names):
                    raise InvalidUpload("Macro-enabled documents are not supported")
                if any(item.flag_bits & 1 for item in entries):
                    raise InvalidUpload("Encrypted DOCX files are not supported")
        except BadZipFile as exc:
            raise InvalidUpload("DOCX archive is corrupt") from exc
    if extension == ".txt":
        if b"\x00" in data:
            raise InvalidUpload("TXT must contain readable UTF-8 text")
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InvalidUpload("TXT must be UTF-8 encoded") from exc
    return filename, extension


def extract_sections(extension: str, data: bytes) -> list[ExtractedSection]:
    try:
        if extension == ".txt":
            sections = [ExtractedSection(data.decode("utf-8-sig"), "text")]
        elif extension == ".docx":
            document = Document(BytesIO(data))
            paragraphs = [p.text for p in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    paragraphs.append(" | ".join(cell.text for cell in row.cells))
            sections = [ExtractedSection("\n".join(paragraphs), "document")]
        elif extension == ".pdf":
            with pymupdf.open(stream=data, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise InvalidUpload("Password-protected PDFs are not supported")
                if len(pdf) > MAX_PDF_PAGES:
                    raise InvalidUpload("PDF exceeds the 100-page limit")
                sections = []
                for number, page in enumerate(pdf, start=1):
                    sections.append(ExtractedSection(page.get_text("text"), f"page {number}"))
        else:
            raise InvalidUpload("Unsupported document type")
    except InvalidUpload:
        raise
    except Exception as exc:
        raise InvalidUpload("Could not extract readable text from this document") from exc
    cleaned = [ExtractedSection(" ".join(s.text.split()) if s.source_ref.startswith("page ") else s.text.strip(), s.source_ref) for s in sections]
    if sum(len(s.text) for s in cleaned) > MAX_TEXT_CHARS:
        raise InvalidUpload("Extracted text exceeds 500,000 characters")
    if not any(s.text.strip() for s in cleaned):
        raise InvalidUpload("No readable text found. Scanned images need OCR, which is not in V0")
    return [s for s in cleaned if s.text.strip()]
