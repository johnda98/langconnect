import logging
import re
import uuid
from io import BytesIO
from typing import Any

from fastapi import HTTPException, UploadFile, status
from langchain_community.document_loaders.parsers import BS4HTMLParser, PDFMinerParser
from langchain_community.document_loaders.parsers.generic import MimeTypeBasedParser
from langchain_community.document_loaders.parsers.msword import MsWordParser
from langchain_community.document_loaders.parsers.txt import TextParser
from langchain_core.documents.base import Blob, Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pdfminer.high_level import extract_text  # type: ignore
try:  # Optional dependency for better PDF fallback
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None

LOGGER = logging.getLogger(__name__)

# Document Parser Configuration
HANDLERS = {
    "application/pdf": PDFMinerParser(),
    "text/plain": TextParser(),
    "text/html": BS4HTMLParser(),
    "application/msword": MsWordParser(),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        MsWordParser()
    ),
}

SUPPORTED_MIMETYPES = sorted(HANDLERS.keys())

MIMETYPE_BASED_PARSER = MimeTypeBasedParser(
    handlers=HANDLERS,
    fallback_parser=None,
)

# Text Splitter
TEXT_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
MIN_TEXT_CHARS = 500  # below this, treat as low-extract and trigger fallback/OCR guidance

_NULL_CHAR = "\x00"
_ZERO_WIDTH = "[\u200b\u200c\u200d\ufeff\u2060]"
_NBSP = "\xa0"
_MULTISPACE = re.compile(r"[ \t]{2,}")
_MULTINEWLINE = re.compile(r"\n{3,}")


def _normalize_text(value: str | None) -> str:
    """Normalize text so keyword search sees literals."""
    if not value:
        return ""
    cleaned = value.replace(_NBSP, " ")
    cleaned = re.sub(_ZERO_WIDTH, "", cleaned)
    cleaned = _MULTISPACE.sub(" ", cleaned)
    cleaned = _MULTINEWLINE.sub("\n\n", cleaned)
    return cleaned.strip()


def _sanitize_text(value: str | None) -> str:
    """Remove characters that PostgreSQL text columns cannot store."""
    if not value:
        return ""
    return value.replace(_NULL_CHAR, "")


def _sanitize_value(value: Any) -> Any:
    """Recursively sanitize strings in metadata structures."""
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def _sanitize_metadata(metadata: dict | None) -> dict:
    if not metadata:
        return {}
    return {key: _sanitize_value(val) for key, val in metadata.items()}


async def process_document(
    file: UploadFile, metadata: dict | None = None
) -> list[Document]:
    """Process an uploaded file into LangChain documents."""
    # Generate a unique ID for this file processing instance
    file_id = uuid.uuid4()

    contents = await file.read()
    blob = Blob(data=contents, mimetype=file.content_type or "text/plain")

    docs = MIMETYPE_BASED_PARSER.parse(blob)

    for doc in docs:
        doc.page_content = _sanitize_text(_normalize_text(doc.page_content))
        if hasattr(doc, "metadata") and isinstance(doc.metadata, dict):
            doc.metadata = _sanitize_metadata(doc.metadata)

    # Add provided metadata to each document
    if metadata:
        sanitized_metadata = _sanitize_metadata(metadata)
        for doc in docs:
            # Ensure metadata attribute exists and is a dict
            if not hasattr(doc, "metadata") or not isinstance(doc.metadata, dict):
                doc.metadata = {}
            # Update with provided metadata, preserving existing keys if not overridden
            doc.metadata.update(sanitized_metadata)

    # If nothing was extracted, fail fast so the caller can warn the user
    total_len = sum(len((d.page_content or "").strip()) for d in docs)

    # Fallback for PDFs that yielded little or no text: try alternative extractors
    if total_len < MIN_TEXT_CHARS and (file.content_type or "").lower() == "application/pdf":
        LOGGER.info("Primary PDF parse yielded low text; attempting fallback text extract.")
        try:
            fallback_text = extract_text(BytesIO(contents))  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover
            LOGGER.warning(f"PDF fallback extract_text failed: {exc}")
            fallback_text = ""
        # If still low and PyMuPDF is available, try it
        if (not fallback_text or len(fallback_text.strip()) < MIN_TEXT_CHARS) and fitz:
            try:
                with fitz.open(stream=contents, filetype="pdf") as doc:
                    texts = [page.get_text("text") for page in doc]
                fallback_text = "\n".join(texts)
            except Exception as exc:  # pragma: no cover
                LOGGER.warning(f"PyMuPDF fallback failed: {exc}")

        if fallback_text and len(fallback_text.strip()) >= MIN_TEXT_CHARS:
            docs = [
                Document(
                    page_content=_sanitize_text(_normalize_text(fallback_text)),
                    metadata=_sanitize_metadata(metadata) if metadata else {},
                )
            ]
            total_len = len(docs[0].page_content)

    # Enforce minimum text only for PDFs; for other types require non-empty
    if (file.content_type or "").lower() == "application/pdf":
        if total_len < MIN_TEXT_CHARS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Too little extractable text found. Please upload a text-searchable copy or OCR the PDF (export to TXT) before retrying.",
            )
    else:
        if total_len == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No extractable text found. Please upload a text-searchable copy.",
            )

    # Split documents
    split_docs = TEXT_SPLITTER.split_documents(docs)

    # Add the generated file_id to all split documents' metadata
    for split_doc in split_docs:
        split_doc.page_content = _sanitize_text(_normalize_text(split_doc.page_content))
        if not hasattr(split_doc, "metadata") or not isinstance(
            split_doc.metadata, dict
        ):
            split_doc.metadata = {}  # Initialize if it doesn't exist
        else:
            split_doc.metadata = _sanitize_metadata(split_doc.metadata)
        split_doc.metadata["file_id"] = str(
            file_id
        )  # Store as string for compatibility

    return split_docs
