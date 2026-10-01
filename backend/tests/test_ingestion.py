from io import BytesIO

import pymupdf
from docx import Document
import pytest

from app.ingestion.chunking import chunk_sections
from app.ingestion.files import ExtractedSection, InvalidUpload, extract_sections, validate_upload


def test_txt_extracts_utf8(sample_text):
    filename, extension = validate_upload("course.txt", "text/plain", sample_text)
    assert filename == "course.txt"
    assert extract_sections(extension, sample_text)[0].text.startswith("Machine Learning")


def test_pdf_and_docx_extraction():
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((40, 40), "Deadline is 14 October 2026")
    data = pdf.tobytes()
    validate_upload("course.pdf", "application/pdf", data)
    assert "Deadline" in extract_sections(".pdf", data)[0].text
    document = Document()
    document.add_paragraph("Machine Learning assignment deadline is 14 October 2026.")
    stream = BytesIO()
    document.save(stream)
    validate_upload("course.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", stream.getvalue())
    assert "Machine Learning" in extract_sections(".docx", stream.getvalue())[0].text


def test_chunking_preserves_order_and_overlap():
    sections = [ExtractedSection(" ".join(f"word{i}" for i in range(120)), "page 2")]
    chunks = chunk_sections(sections, size=100, overlap=25)
    assert len(chunks) > 3
    assert all(chunk.source_ref == "page 2" for chunk in chunks)
    assert chunks[0].start_char == 0
    assert chunks[1].start_char < chunks[0].start_char + len(chunks[0].text)


@pytest.mark.parametrize(
    "name,mime,data",
    [
        ("evil.exe", "application/octet-stream", b"hello"),
        ("fake.pdf", "application/pdf", b"not a pdf"),
        ("note.txt", "application/pdf", b"hello"),
        ("note.txt", "text/plain", b"\x00bad"),
        ("note.txt", "text/plain", b""),
        ("note.txt", "text/plain", b"A" * (10 * 1024 * 1024 + 1)),
    ],
    ids=[
        "unsupported-extension",
        "fake-pdf",
        "mime-mismatch",
        "nul-byte-text",
        "empty-text",
        "oversized-text",
    ],
)
def test_upload_validation_rejects_bad_inputs(name, mime, data):
    with pytest.raises(InvalidUpload):
        validate_upload(name, mime, data)


def test_filename_never_preserves_path():
    name, _ = validate_upload(r"C:\Users\private\assignment.txt", "text/plain", b"safe")
    assert name == "assignment.txt"
