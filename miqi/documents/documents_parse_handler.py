"""Document parse handler for AppServer dispatch.

Provides documents.parse — a handler that extracts text content from uploaded
documents (PDF, Word, Excel, PowerPoint) for preview and RAG usage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from miqi.documents.document_parser import (
    parse_document,
    is_supported_document,
    MAX_PREVIEW_CHARS,
)
from miqi.runtime.app_server import AppServerError
from miqi.runtime.file_handlers import (
    _get_workspace_path,
    _validate_file_path,
    _verify_session_ownership,
    _resolve_session_files_path,
)


async def documents_parse_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Parse a document and return extracted text.

    Params:
        path (required): Document file path (workspace-relative or absolute).
        session_key (optional): Session scope for path resolution.
        force_ocr (optional): Force OCR even for text-based PDFs.
        preview (optional): If True, limit to MAX_PREVIEW_CHARS.
    """
    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")
    force_ocr = params.get("force_ocr", False)
    is_preview = params.get("preview", False)

    logger.info(
        "[docs:parse] req={} path={} session_key={} preview={}",
        request_id, file_path, session_key, is_preview,
    )

    if not file_path:
        raise AppServerError("path is required", code="INVALID_PARAMS")

    # Resolve and validate the path
    try:
        resolved = _validate_file_path(file_path, client_id, session_key)
    except AppServerError:
        raise
    except ValueError as exc:
        logger.warning("[docs:parse] invalid path {}: {}", file_path, exc)
        raise AppServerError("Invalid file path", code="INVALID_PARAMS") from exc

    if not resolved.exists():
        logger.warning("[docs:parse] file not found: {}", resolved)
        raise AppServerError(
            f"File not found: {file_path}"
            + (f" (session: {session_key})" if session_key else ""),
            code="NOT_FOUND",
        )

    if not is_supported_document(resolved):
        suffix = resolved.suffix.lower()
        raise AppServerError(
            f"Unsupported document format: {suffix or resolved.name}",
            code="INVALID_PARAMS",
        )

    try:
        max_chars = MAX_PREVIEW_CHARS if is_preview else 50_000
        result = parse_document(resolved, max_chars=max_chars, force_ocr=force_ocr)
    except Exception as exc:
        logger.error("[docs:parse] parsing failed for {}: {} type={}", file_path, exc, type(exc).__name__)
        raise AppServerError(
            f"Document parsing failed: {exc}", code="INTERNAL",
        ) from exc

    logger.info(
        "[docs:parse] ok path={} text_len={} ocr={} ms={}",
        file_path, len(result["text"]), result.get("ocr_used"), result.get("parse_ms"),
    )

    return {
        "result": {
            "path": file_path,
            "text": result["text"],
            "page_count": result["page_count"],
            "size_bytes": result["size_bytes"],
            "mime_type": result["mime_type"],
            "ocr_used": result["ocr_used"],
            "parse_ms": result["parse_ms"],
        },
    }
