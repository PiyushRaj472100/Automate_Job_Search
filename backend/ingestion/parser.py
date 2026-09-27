"""Resume file parser supporting PDF and DOCX extraction, cleaning, and hashing."""

import hashlib
import io
import re
from typing import NamedTuple

from docx import Document
from pypdf import PdfReader


class ResumeParseResult(NamedTuple):
    """Result of parsing and cleaning a resume document."""

    file_name: str
    file_hash: str
    file_extension: str
    raw_text: str
    cleaned_text: str
    file_size_bytes: int


class ResumeParserError(Exception):
    """Base exception for resume parsing failures."""

    pass


class UnsupportedFileFormatError(ResumeParserError):
    """Raised when the uploaded file extension or mime type is unsupported."""

    pass


class EmptyResumeError(ResumeParserError):
    """Raised when an uploaded resume file contains no readable text."""

    pass


class CorruptFileError(ResumeParserError):
    """Raised when an uploaded resume file cannot be decoded or is malformed."""

    pass


def clean_extracted_text(text: str) -> str:
    """Normalize extracted text by cleaning whitespace and strange characters."""
    if not text:
        return ""

    # Replace carriage returns and vertical tabs
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")

    # Normalize unicode bullets and hyphens
    cleaned = re.sub(r"[\u2022\u2023\u25E6\u2043\u2219\uf0b7]", "•", cleaned)
    cleaned = re.sub(r"[\u2013\u2014]", "-", cleaned)

    # Remove non-printable control characters except newline and tab
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)

    # Collapse multiple consecutive blank lines into max 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # Strip excessive horizontal whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)

    return cleaned.strip()


def extract_text_from_pdf(content: bytes) -> str:
    """Extract plain text from PDF bytes using pypdf."""
    try:
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) == 0:
            raise EmptyResumeError("PDF document contains 0 pages.")

        extracted_pages: list[str] = []
        for _idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""

            if page_text.strip():
                extracted_pages.append(page_text)

        full_text = "\n\n".join(extracted_pages)
        return full_text
    except EmptyResumeError:
        raise
    except Exception as e:
        raise CorruptFileError(f"Failed to read PDF document: {e}") from e


def extract_text_from_docx(content: bytes) -> str:
    """Extract plain text from DOCX bytes using python-docx."""
    try:
        doc = Document(io.BytesIO(content))
        paragraphs: list[str] = []

        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                paragraphs.append(text)

        # Also extract table contents if present
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    paragraphs.append(row_text)

        full_text = "\n".join(paragraphs)
        return full_text
    except Exception as e:
        raise CorruptFileError(f"Failed to read DOCX document: {e}") from e


def parse_resume_bytes(file_name: str, content: bytes) -> ResumeParseResult:
    """Parse, validate, hash, and clean resume bytes.

    Args:
        file_name: Original uploaded filename
        content: Raw binary content of the resume

    Returns:
        ResumeParseResult containing hashes and cleaned text

    Raises:
        UnsupportedFileFormatError: If file is not PDF or DOCX
        EmptyResumeError: If file is 0 bytes or contains no extractable text
        CorruptFileError: If file structure cannot be read
    """
    if not content or len(content) == 0:
        raise EmptyResumeError("Uploaded file is empty (0 bytes).")

    # Normalize extension
    lower_name = file_name.lower().strip()
    if lower_name.endswith(".pdf"):
        extension = "pdf"
        raw_text = extract_text_from_pdf(content)
    elif lower_name.endswith(".docx"):
        extension = "docx"
        raw_text = extract_text_from_docx(content)
    else:
        raise UnsupportedFileFormatError(
            f"Unsupported file format for '{file_name}'. Only PDF and DOCX are supported."
        )

    cleaned_text = clean_extracted_text(raw_text)
    if not cleaned_text:
        raise EmptyResumeError(f"No extractable text found in '{file_name}'.")

    # Compute deterministic SHA-256
    file_hash = hashlib.sha256(content).hexdigest()

    return ResumeParseResult(
        file_name=file_name,
        file_hash=file_hash,
        file_extension=extension,
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        file_size_bytes=len(content),
    )
