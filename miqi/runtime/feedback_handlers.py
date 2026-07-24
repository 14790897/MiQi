"""Feedback handlers for AppServer dispatch.

Submits user feedback + collected logs to Feishu Bitable and stores
a local backup in memory/FEEDBACK.jsonl.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from miqi.runtime.app_server import AppServerError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_workspace_path() -> Path:
    """Resolve workspace path from bridge state config."""
    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")
    config = state.load_config()
    return config.workspace_path


def _get_feedback_file() -> Path:
    """Return path to local feedback backup JSONL file."""
    return _get_workspace_path() / "memory" / "FEEDBACK.jsonl"


def _ensure_memory_dir() -> None:
    """Ensure the memory directory exists."""
    memory_dir = _get_workspace_path() / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)


def _collect_all_logs(log_dir: Path) -> str:
    """Read every file under workspace/logs/ recursively (relative path
    shown for nested files) and return concatenated text.

    Individual files are capped at 1 MB (tail end).  The combined payload
    is capped at 100,000 UTF-8 bytes to fit within Feishu Bitable
    text-field limits (per official docs).
    """
    if not log_dir.exists():
        return "[日志目录不存在]"

    parts: list[str] = []
    # Recursive walk: catches nested logs and any extension (binary-safe
    # via errors='replace' below).
    for f in sorted(log_dir.rglob("*")):
        if not f.is_file():
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            max_chars = 1_000_000
            if len(content) > max_chars:
                content = f"...(截断 {len(content) - max_chars} 字符)\n{content[-max_chars:]}"
            rel = f.relative_to(log_dir)
            parts.append(f"=== {rel} ===\n{content}")
        except Exception as exc:
            parts.append(f"=== {f.name} === [读取失败: {exc}]")

    if not parts:
        return "[无日志文件]"

    combined = "\n\n".join(parts)
    # Cap by UTF-8 byte size — Feishu Bitable text-field limit is 100k bytes,
    # not 100k chars (Chinese characters can be 3+ bytes each).  Encode once,
    # then slice the tail bytes directly to avoid repeatedly re-encoding.
    encoded = combined.encode("utf-8")
    total_bytes = len(encoded)
    if total_bytes > 100_000:
        # Reserve 100 bytes for the marker text (incl. the digit count).
        keep_bytes = 100_000 - 100
        retained = encoded[-keep_bytes:].decode("utf-8", errors="ignore")
        retained_bytes = len(retained.encode("utf-8"))
        dropped = total_bytes - retained_bytes
        marker = f"...(总日志超出 {dropped} 字节，已截断)\n"
        # If the marker pushed us over (rare; depends on dropped digit count),
        # trim the tail further to fit exactly within the cap.
        candidate = marker + retained
        if len(candidate.encode("utf-8")) > 100_000:
            excess = len(candidate.encode("utf-8")) - 100_000
            retained = retained.encode("utf-8")[:-excess].decode("utf-8", errors="ignore")
            return marker + retained
        return candidate
    return combined


def _collect_system_info() -> dict[str, str]:
    """Collect basic system / environment info."""
    info: dict[str, str] = {
        "os": platform.system(),
        "os_version": platform.release(),
        "machine": platform.machine(),
        "python_version": sys.version.split()[0],
    }
    # Try WSL check
    try:
        import subprocess
        r = subprocess.run(
            ["wsl", "--list", "--verbose"],
            capture_output=True, text=True, timeout=5,  # noqa: S603
        )
        info["wsl_status"] = r.stdout.strip() or "[未安装或无权限]"
    except Exception:
        info["wsl_status"] = "[检测失败]"
    return info


def _get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """Obtain a Feishu tenant_access_token via app_id/app_secret."""
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    code = body.get("code", -1)
    if code != 0:
        msg = body.get("msg", "unknown error")
        raise AppServerError(
            f"获取飞书 tenant_access_token 失败: {msg} (code={code})",
            code="FEISHU_AUTH_ERROR",
        )
    token = body.get("tenant_access_token", "")
    if not token:
        raise AppServerError(
            "飞书返回的 tenant_access_token 为空", code="FEISHU_AUTH_ERROR",
        )
    return token


def _upload_attachment(
    token: str,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    parent_node: str,
) -> str:
    """Upload an attachment to Feishu Drive and return the file_token.

    Used for Bitable attachment fields: the record references the file_token
    rather than embedding the bytes inline.

    `parent_node` MUST be the target Bitable's app_token — empty strings
    cause the upload to fail before the record is created.
    """
    resp = requests.post(
        "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file_name": filename,
            "parent_type": "bitable_file",
            "parent_node": parent_node,
            "size": str(len(data)),
        },
        files={"file": (filename, data, content_type)},
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    code = body.get("code", -1)
    if code != 0:
        msg = body.get("msg", "unknown error")
        raise AppServerError(
            f"上传截图失败: {msg} (code={code})", code="FEISHU_UPLOAD_ERROR",
        )
    file_token = body.get("data", {}).get("file_token", "")
    if not file_token:
        raise AppServerError(
            "上传截图返回的 file_token 为空", code="FEISHU_UPLOAD_ERROR",
        )
    return file_token


def _decode_data_url(data_url: str) -> tuple[str, str, bytes]:
    """Decode a `data:<mime>;base64,<...>` URL to (mime, filename, bytes).

    Validates the encoded b64 section's size BEFORE decoding to bound memory
    usage — a malicious caller could otherwise send a multi-GB data URL.
    """
    if not data_url.startswith("data:"):
        raise AppServerError(
            "Screenshot format error (expected data URL)", code="INVALID_PARAMS",
        )
    try:
        header, b64 = data_url.split(",", 1)
        mime = header.split(";", 1)[0].split(":", 1)[1]
    except Exception as exc:
        raise AppServerError(
            f"Screenshot header parse failed: {exc}", code="INVALID_PARAMS",
        ) from exc

    # Bound the encoded size before decoding.  base64 inflates by ~4/3, so
    # 14 MB encoded gives at most ~10.5 MB decoded — leave a small buffer.
    if len(b64) > 14 * 1024 * 1024:
        raise AppServerError(
            "Screenshot exceeds 10MB limit (encoded)",
            code="FILE_TOO_LARGE",
        )

    import base64
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception as exc:
        raise AppServerError(
            f"Screenshot base64 decode failed: {exc}", code="INVALID_PARAMS",
        ) from exc
    ext_map = {
        "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
        "image/gif": "gif", "image/webp": "webp", "image/bmp": "bmp",
    }
    ext = ext_map.get(mime, "png")
    return mime, f"screenshot.{ext}", raw


def _add_bitable_record(
    token: str,
    app_token: str,
    table_id: str,
    fields: dict[str, Any],
) -> str:
    """Add one record to a Feishu Bitable and return the record_id."""
    resp = requests.post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"fields": fields},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    code = body.get("code", -1)
    if code != 0:
        msg = body.get("msg", "unknown error")
        raise AppServerError(
            f"写入飞书多维表格失败: {msg} (code={code})",
            code="FEISHU_BITABLE_ERROR",
        )
    record = body.get("data", {}).get("record", {})
    record_id = record.get("record_id", "")
    logger.info("Feedback submitted to Feishu Bitable, record_id={}", record_id)
    return record_id


def _save_local_backup(entry: dict[str, Any]) -> None:
    """Append one feedback entry to the local backup JSONL file."""
    _ensure_memory_dir()
    feedback_file = _get_feedback_file()
    try:
        with feedback_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to write local feedback backup: {}", exc)


def _append_feedback(entry: dict[str, Any]) -> None:
    """Backward-compat alias for _save_local_backup."""
    _save_local_backup(entry)


def _read_local_backups() -> list[dict[str, Any]]:
    """Read all local feedback backup entries (newest first)."""
    feedback_file = _get_feedback_file()
    if not feedback_file.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        for line in feedback_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception as exc:
        logger.warning("Failed to read local feedback backups: {}", exc)
        return []

    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return entries


def _read_local_feedbacks() -> list[dict[str, Any]]:
    """Backward-compat alias for _read_local_backups."""
    return _read_local_backups()


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def feedback_submit_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Submit user feedback + collected logs to Feishu Bitable."""
    raw_category = str(params.get("category", "other"))
    allowed_categories = {"bug", "question", "suggestion", "other"}
    category = raw_category if raw_category in allowed_categories else "other"
    title = str(params.get("title", "")).strip()
    content = str(params.get("content", "")).strip()
    contact = str(params.get("contact", "")).strip()
    app_version = str(params.get("app_version", "unknown"))
    prompt_used = str(params.get("prompt_used", "")).strip()
    repro_frequency = str(params.get("repro_frequency", "")).strip()
    screenshots_raw = params.get("screenshots") or []
    if not isinstance(screenshots_raw, list):
        screenshots_raw = []
    screenshots = [str(s) for s in screenshots_raw if s][:5]  # cap at 5

    if not title:
        raise AppServerError("反馈标题不能为空", code="INVALID_PARAMS")
    if not content:
        raise AppServerError("反馈内容不能为空", code="INVALID_PARAMS")

    workspace = _get_workspace_path()
    log_dir = workspace / "logs"

    # 1. Collect all logs
    logger.info("feedback:submit — collecting logs from {}", log_dir)
    log_content = _collect_all_logs(log_dir)

    # 2. Collect system info
    sys_info = _collect_system_info()
    os_str = f"{sys_info['os']} {sys_info['os_version']} ({sys_info['machine']})"

    # 3. Get Feishu config
    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")
    config = state.load_config()
    fb_cfg = config.channels.feedback

    if not fb_cfg.enabled:
        raise AppServerError("反馈功能未启用，请在配置中开启", code="FEEDBACK_DISABLED")

    app_id = fb_cfg.feishu_app_id or config.channels.feishu.app_id
    app_secret = fb_cfg.feishu_app_secret or config.channels.feishu.app_secret
    if not app_id or not app_secret:
        raise AppServerError(
            "飞书 App ID / App Secret 未配置", code="FEISHU_NOT_CONFIGURED",
        )
    if not fb_cfg.bitable_app_token or not fb_cfg.bitable_table_id:
        raise AppServerError(
            "飞书多维表格 app_token / table_id 未配置", code="BITABLE_NOT_CONFIGURED",
        )

    now_iso = datetime.now(timezone.utc).isoformat()

    # 4. Build Bitable fields
    fields: dict[str, Any] = {
        "类别": category,
        "标题": title,
        "详细描述（复现步骤，期望行为，实际行为等）": content,
        "联系方式": contact,
        "应用版本": app_version,
        "操作系统": os_str,
        "Python版本": sys_info["python_version"],
        "日志内容（设置界面日志栏目-复制日志）": log_content,
        "提交时间": now_iso,
        "使用的提示词": prompt_used,
        "复现频率": repro_frequency,
    }

    # 5. Send to Feishu — get token first, then upload screenshots, then add record
    try:
        token = _get_tenant_access_token(app_id, app_secret)

        # 5a. Upload each screenshot to get file_token references
        if screenshots:
            file_tokens: list[dict[str, str]] = []
            for idx, data_url in enumerate(screenshots):
                try:
                    mime, filename, raw = _decode_data_url(data_url)
                except AppServerError:
                    raise
                except Exception as exc:
                    raise AppServerError(
                        f"截图 {idx + 1} 处理失败: {exc}",
                        code="INVALID_PARAMS",
                    ) from exc
                # 10 MB cap per image
                if len(raw) > 10 * 1024 * 1024:
                    raise AppServerError(
                        f"截图 {idx + 1} 超过 10MB 限制",
                        code="FILE_TOO_LARGE",
                    )
                logger.info("Uploading screenshot {} ({} bytes)", idx + 1, len(raw))
                file_token = _upload_attachment(
                    token,
                    filename=filename,
                    content_type=mime,
                    data=raw,
                    parent_node=fb_cfg.bitable_app_token,
                )
                file_tokens.append({"file_token": file_token})
            fields["附件"] = file_tokens

        # 5b. Add the Bitable record (with attachment references)
        record_id = _add_bitable_record(
            token, fb_cfg.bitable_app_token, fb_cfg.bitable_table_id, fields,
        )
    except AppServerError:
        raise
    except Exception as exc:
        logger.exception("feedback:submit — Feishu API error")
        raise AppServerError(
            f"提交到飞书失败: {exc}", code="FEISHU_API_ERROR",
        ) from exc

    # 6. Local backup (strip log content to avoid huge local file)
    local_entry = {
        "id": f"fbk_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "category": category,
        "title": title,
        "content": content,
        "contact": contact,
        "app_version": app_version,
        "os": os_str,
        "python_version": sys_info["python_version"],
        "feishu_record_id": record_id,
        "created_at": now_iso,
    }
    _save_local_backup(local_entry)

    return {"result": {"ok": True, "record_id": record_id}}


async def feedback_list_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """List local feedback backups."""
    # Validate and clamp limit.  Accept int, treat None/0/non-positive as
    # "no limit" (return all).  Clamp to a sane upper bound to bound work.
    raw_limit = params.get("limit")
    if raw_limit is None or raw_limit == 0:
        limit = 0  # 0 = no limit
    else:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            raise AppServerError(
                f"Invalid limit value: {raw_limit!r}", code="INVALID_PARAMS",
            )
    if limit < 0:
        limit = 0
    if limit > 200:
        limit = 200

    entries = _read_local_backups()
    if limit > 0 and len(entries) > limit:
        entries = entries[:limit]
    return {"result": {"entries": entries}}
