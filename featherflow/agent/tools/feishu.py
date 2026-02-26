"""Feishu business tools: cloud docs, calendar events, and tasks."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from featherflow.agent.tools.base import Tool

try:
    import lark_oapi as lark
    from lark_oapi.api.calendar.v4 import (
        CalendarEvent,
        CalendarEventAttendee,
        CreateCalendarEventAttendeeRequest,
        CreateCalendarEventAttendeeRequestBody,
        CreateCalendarEventRequest,
        PrimaryCalendarRequest,
        TimeInfo,
    )
    from lark_oapi.api.docx.v1 import (
        Block,
        CreateDocumentBlockChildrenRequest,
        CreateDocumentBlockChildrenRequestBody,
        CreateDocumentRequest,
        CreateDocumentRequestBody,
        Text,
        TextElement,
        TextRun,
    )
    from lark_oapi.api.drive.v1 import (
        CreateFolderFileRequest,
        CreateFolderFileRequestBody,
        CreatePermissionMemberRequest,
        FileUploadInfo,
        ListFileRequest,
        Member as PermissionMember,
        UploadAllFileRequest,
        UploadAllFileRequestBody,
        UploadFinishFileRequest,
        UploadFinishFileRequestBody,
        UploadPartFileRequest,
        UploadPartFileRequestBody,
        UploadPrepareFileRequest,
    )
    from lark_oapi.api.im.v1 import GetChatMembersRequest
    from lark_oapi.api.task.v2 import CreateTaskRequest, Due, InputTask, Member

    FEISHU_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
    lark = None

# Files larger than this threshold must use multipart (分片) upload.
# upload_all API hard-limits: ≤ 20 MB per Feishu official docs (2024-10-23).
_FEISHU_UPLOAD_ALL_MAX_BYTES: int = 20 * 1024 * 1024  # 20 MB


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).lower()


def _clean_target(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = re.sub(r"</?at[^>]*>", "", text).strip()
    if text.startswith("@"):
        text = text[1:].strip()
    return text.strip(" ,.;:()[]{}")


def _looks_like_open_id(value: str) -> bool:
    return bool(re.match(r"^(ou|on)_[A-Za-z0-9]+$", (value or "").strip()))


def _safe_drive_name(value: str, fallback: str = "artifact") -> str:
    name = (value or "").strip()
    if not name:
        name = fallback
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:255] if len(name) > 255 else name


def _split_folder_path(path: str) -> list[str]:
    parts = [seg.strip() for seg in (path or "").split("/") if seg.strip()]
    return [_safe_drive_name(seg, "folder") for seg in parts]


@dataclass
class ResolvedUser:
    """Resolved Feishu user identity."""

    input_value: str
    open_id: str
    name: str = ""
    source: str = "unknown"

    def as_dict(self) -> dict[str, str]:
        payload = {
            "input": self.input_value,
            "open_id": self.open_id,
            "source": self.source,
        }
        if self.name:
            payload["name"] = self.name
        return payload


class FeishuToolBase(Tool):
    """Shared utilities for Feishu business tools."""

    def __init__(self, app_id: str, app_secret: str):
        self._channel = ""
        self._chat_id = ""
        self._message_id: str | None = None
        self._sender_id = ""
        self._metadata: dict[str, Any] = {}
        self._member_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
        self._member_cache_ttl_seconds = 60

        self._client: Any = None
        if FEISHU_AVAILABLE and lark is not None and app_id and app_secret:
            lark_sdk = lark
            self._client = (
                lark_sdk.Client.builder()
                .app_id(app_id)
                .app_secret(app_secret)
                .build()
            )

    def set_context(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None = None,
        sender_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._channel = channel
        self._chat_id = chat_id
        self._message_id = message_id
        self._sender_id = sender_id or ""
        self._metadata = metadata or {}

    @staticmethod
    def _ok_payload(**kwargs: Any) -> str:
        data = {"ok": True}
        data.update(kwargs)
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _error_payload(message: str, **kwargs: Any) -> str:
        data = {"ok": False, "error": message}
        data.update(kwargs)
        return json.dumps(data, ensure_ascii=False)

    async def _run_sync(self, func: Callable[..., Any], *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args))

    def _check_ready(self) -> str | None:
        if not FEISHU_AVAILABLE:
            return "Feishu SDK not installed. Run: pip install lark-oapi"
        if self._client is None:
            return "Feishu app_id/app_secret not configured"
        return None

    def _check_feishu_channel(self) -> str | None:
        if self._channel and self._channel != "feishu":
            return f"Current channel is '{self._channel}', not feishu"
        return None

    async def _grant_permission(
        self,
        token: str,
        token_type: str,
        *,
        member_type: str = "openchat",
        member_id: str = "",
        perm: str = "view",
    ) -> str | None:
        """Grant permission for a cloud doc/file to a user or group.

        Args:
            token: The doc/file token.
            token_type: Resource type, e.g. "docx", "file", "sheet".
            member_type: "openchat" for group, "openid" for user.
            member_id: The group chat_id or user open_id.
            perm: Permission level: "view", "edit", or "full_access".

        Returns:
            Error message string on failure, None on success.

        Note (2025-07-03 official docs):
            - To grant group access with tenant_access_token, the app must be
              a bot member of the group first.
            - Direct folder-level app grants are not supported; use group-based
              access instead.
        """
        if not FEISHU_AVAILABLE or self._client is None:
            return "Feishu client not available"
        if not token or not member_id:
            return "token and member_id are required for permission grant"
        try:
            member = (
                PermissionMember.builder()
                .member_type(member_type)
                .member_id(member_id)
                .perm(perm)
                .build()
            )
            request = (
                CreatePermissionMemberRequest.builder()
                .token(token)
                .type(token_type)
                .need_notification(False)
                .request_body(member)
                .build()
            )
            response = await self._run_sync(
                self._client.drive.v1.permission_member.create, request
            )
            if not response.success():
                return (
                    f"Failed to grant permission: code={response.code}, "
                    f"msg={response.msg}"
                )
            return None
        except Exception as e:
            return f"Failed to grant permission: {e}"

    def _sender_open_id(self) -> str:
        sender = str((self._metadata or {}).get("sender_open_id") or self._sender_id or "").strip()
        return sender if _looks_like_open_id(sender) else ""

    def _mentions(self) -> list[dict[str, str]]:
        raw = (self._metadata or {}).get("mentions")
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        items: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            open_id = str(item.get("open_id") or "").strip()
            name = str(item.get("name") or "").strip()
            if not open_id or open_id in seen:
                continue
            seen.add(open_id)
            payload = {"open_id": open_id}
            if name:
                payload["name"] = name
            items.append(payload)
        return items

    async def _list_group_members(self) -> tuple[list[dict[str, str]], str | None]:
        if not self._chat_id.startswith("oc_"):
            return [], "Current chat is not a group chat"

        now = time.time()
        cached = self._member_cache.get(self._chat_id)
        if cached and now - cached[0] < self._member_cache_ttl_seconds:
            return cached[1], None

        members: list[dict[str, str]] = []
        page_token = ""
        try:
            while True:
                builder = (
                    GetChatMembersRequest.builder()
                    .chat_id(self._chat_id)
                    .member_id_type("open_id")
                    .page_size(50)
                )
                if page_token:
                    builder.page_token(page_token)
                request = builder.build()
                response = await self._run_sync(self._client.im.v1.chat_members.get, request)
                if not response.success():
                    return [], f"Failed to list group members: code={response.code}, msg={response.msg}"

                data = response.data
                for item in (data.items or []):
                    open_id = str(getattr(item, "member_id", "") or "").strip()
                    name = str(getattr(item, "name", "") or "").strip()
                    if open_id:
                        members.append({"open_id": open_id, "name": name})
                if not getattr(data, "has_more", False):
                    break
                page_token = str(getattr(data, "page_token", "") or "").strip()
                if not page_token:
                    break
        except Exception as e:
            return [], f"Failed to list group members: {e}"

        self._member_cache[self._chat_id] = (now, members)
        return members, None

    async def _resolve_users(
        self,
        targets: list[str] | None,
        *,
        allow_sender_fallback: bool,
    ) -> tuple[list[ResolvedUser], list[str], list[dict[str, Any]], str | None]:
        cleaned_targets = [_clean_target(v) for v in (targets or [])]
        cleaned_targets = [v for v in cleaned_targets if v]

        mentions = self._mentions()
        mentions_by_name: dict[str, list[dict[str, str]]] = {}
        mentions_by_open: dict[str, dict[str, str]] = {}
        for item in mentions:
            open_id = item["open_id"]
            mentions_by_open[open_id] = item
            normalized = _normalize_name(item.get("name", ""))
            if normalized:
                mentions_by_name.setdefault(normalized, []).append(item)

        resolved: list[ResolvedUser] = []
        unresolved: list[str] = []
        ambiguous: list[dict[str, Any]] = []
        seen_open_ids: set[str] = set()

        def _append(open_id: str, input_value: str, source: str, name: str = "") -> None:
            if not open_id or open_id in seen_open_ids:
                return
            seen_open_ids.add(open_id)
            resolved.append(
                ResolvedUser(
                    input_value=input_value,
                    open_id=open_id,
                    name=name,
                    source=source,
                )
            )

        for target in cleaned_targets:
            if _looks_like_open_id(target):
                mention = mentions_by_open.get(target, {})
                _append(target, target, "direct", mention.get("name", ""))
                continue

            normalized = _normalize_name(target)
            mention_hits = mentions_by_name.get(normalized, [])
            if len(mention_hits) == 1:
                hit = mention_hits[0]
                _append(hit["open_id"], target, "mention", hit.get("name", ""))
                continue
            if len(mention_hits) > 1:
                ambiguous.append(
                    {
                        "input": target,
                        "candidates": [
                            {"open_id": v["open_id"], "name": v.get("name", "")}
                            for v in mention_hits[:10]
                        ],
                    }
                )
                continue
            unresolved.append(target)

        if unresolved:
            members, error = await self._list_group_members()
            if error:
                return resolved, unresolved, ambiguous, error

            exact_map: dict[str, list[dict[str, str]]] = {}
            for item in members:
                normalized = _normalize_name(item.get("name", ""))
                if normalized:
                    exact_map.setdefault(normalized, []).append(item)

            remaining_unresolved: list[str] = []
            for target in unresolved:
                normalized = _normalize_name(target)
                hits = exact_map.get(normalized, [])
                if len(hits) == 1:
                    hit = hits[0]
                    _append(hit["open_id"], target, "group_member", hit.get("name", ""))
                    continue
                if len(hits) > 1:
                    ambiguous.append(
                        {
                            "input": target,
                            "candidates": [
                                {"open_id": v["open_id"], "name": v.get("name", "")}
                                for v in hits[:10]
                            ],
                        }
                    )
                    continue

                fuzzy_hits = [
                    item
                    for item in members
                    if normalized
                    and normalized in _normalize_name(item.get("name", ""))
                ]
                unique_fuzzy: dict[str, dict[str, str]] = {v["open_id"]: v for v in fuzzy_hits}
                fuzzy_values = list(unique_fuzzy.values())
                if len(fuzzy_values) == 1:
                    hit = fuzzy_values[0]
                    _append(hit["open_id"], target, "group_member_fuzzy", hit.get("name", ""))
                    continue
                if len(fuzzy_values) > 1:
                    ambiguous.append(
                        {
                            "input": target,
                            "candidates": [
                                {"open_id": v["open_id"], "name": v.get("name", "")}
                                for v in fuzzy_values[:10]
                            ],
                        }
                    )
                    continue
                remaining_unresolved.append(target)

            unresolved = remaining_unresolved

        if not cleaned_targets and allow_sender_fallback:
            sender_open_id = self._sender_open_id()
            if sender_open_id:
                _append(sender_open_id, "sender", "sender")

        return resolved, unresolved, ambiguous, None

    @staticmethod
    def _to_unix_seconds(value: str | int | float, timezone: str) -> int:
        if isinstance(value, (int, float)):
            raw = int(value)
            return raw // 1000 if raw > 10**11 else raw

        text = str(value).strip()
        if text.isdigit():
            raw = int(text)
            return raw // 1000 if raw > 10**11 else raw

        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(timezone))
        return int(dt.timestamp())


class FeishuDocTool(FeishuToolBase):
    """Create Feishu cloud docs and optionally append plain text."""

    @property
    def name(self) -> str:
        return "feishu_doc"

    @property
    def description(self) -> str:
        return "Create a Feishu cloud doc. Optionally write plain-text content into the doc."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title"},
                "folder_token": {
                    "type": "string",
                    "description": "Optional folder token where the doc should be created",
                },
                "content": {
                    "type": "string",
                    "description": "Optional plain text content to append into the doc",
                },
                "grant_chat_access": {
                    "type": "boolean",
                    "description": (
                        "If true, grant the current group chat view access to the "
                        "created doc via drive permission-member/create (2025-07-03). "
                        "Requires the app to be a bot member of the group."
                    ),
                    "default": False,
                },
            },
            "required": ["title"],
        }

    async def execute(
        self,
        title: str,
        folder_token: str | None = None,
        content: str | None = None,
        grant_chat_access: bool = False,
        **kwargs: Any,
    ) -> str:
        if error := self._check_ready():
            return self._error_payload(error)
        if error := self._check_feishu_channel():
            return self._error_payload(error)

        doc_body = CreateDocumentRequestBody.builder().title(title.strip())
        if folder_token:
            doc_body.folder_token(folder_token.strip())
        request = CreateDocumentRequest.builder().request_body(doc_body.build()).build()

        try:
            response = await self._run_sync(self._client.docx.v1.document.create, request)
        except Exception as e:
            return self._error_payload(f"Failed to create doc: {e}")

        if not response.success():
            return self._error_payload(
                "Failed to create doc",
                code=response.code,
                msg=response.msg,
            )

        document = response.data.document if response.data else None
        document_id = str(getattr(document, "document_id", "") or "").strip()
        if not document_id:
            return self._error_payload("Doc created but document_id missing in response")

        payload: dict[str, Any] = {
            "document_id": document_id,
            "title": str(getattr(document, "title", "") or title),
            "url_candidates": [
                f"https://www.feishu.cn/docx/{document_id}",
                f"https://www.larksuite.com/docx/{document_id}",
            ],
        }

        if content and content.strip():
            write_ok, write_error = await self._append_plain_text(document_id, content)
            payload["content_written"] = write_ok
            if write_error:
                payload["content_write_warning"] = write_error

        # Optional: grant current group chat view access to the newly created doc.
        # Official docs (2025-07-03): POST /open-apis/drive/v1/permissions/:token/members
        if grant_chat_access and self._chat_id:
            perm_error = await self._grant_permission(
                document_id,
                "docx",
                member_type="openchat",
                member_id=self._chat_id,
                perm="view",
            )
            if perm_error:
                payload["grant_chat_access_warning"] = perm_error
            else:
                payload["grant_chat_access"] = {"ok": True, "chat_id": self._chat_id}

        return self._ok_payload(**payload)

    async def _append_plain_text(self, document_id: str, content: str) -> tuple[bool, str | None]:
        # Feishu doc text API works on block children. Root block id equals document_id.
        lines = [line.rstrip() for line in content.splitlines()]
        lines = [line if line else " " for line in lines]
        if not lines:
            return True, None

        chunk_size = 20
        for idx in range(0, len(lines), chunk_size):
            chunk = lines[idx : idx + chunk_size]
            blocks = []
            for line in chunk:
                text = (
                    Text.builder()
                    .elements(
                        [
                            TextElement.builder()
                            .text_run(TextRun.builder().content(line).build())
                            .build()
                        ]
                    )
                    .build()
                )
                blocks.append(Block.builder().block_type(2).text(text).build())

            body = CreateDocumentBlockChildrenRequestBody.builder().children(blocks).build()
            request = (
                CreateDocumentBlockChildrenRequest.builder()
                .document_id(document_id)
                .block_id(document_id)
                .client_token(str(uuid.uuid4()))
                .request_body(body)
                .build()
            )
            try:
                response = await self._run_sync(
                    self._client.docx.v1.document_block_children.create,
                    request,
                )
            except Exception as e:
                return False, str(e)

            if not response.success():
                return False, f"code={response.code}, msg={response.msg}"

        return True, None


class FeishuCalendarTool(FeishuToolBase):
    """Create calendar events and optionally add attendees."""

    @property
    def name(self) -> str:
        return "feishu_calendar"

    @property
    def description(self) -> str:
        return (
            "Create a Feishu calendar event and add attendees. "
            "Pass attendee display names (e.g. '张三') or open_ids in 'attendees'; "
            "the tool automatically resolves them from group members — "
            "NO need to call feishu_group first unless you want to verify names."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title"},
                "start_time": {
                    "type": "string",
                    "description": "Start time (ISO8601 or unix seconds/ms)",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time (ISO8601 or unix seconds/ms)",
                },
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone, e.g. Asia/Shanghai",
                    "default": "Asia/Shanghai",
                },
                "description": {"type": "string", "description": "Optional event description"},
                "calendar_id": {
                    "type": "string",
                    "description": "Optional calendar_id. If omitted, use primary calendar.",
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Attendee list. Each entry can be a display name (e.g. '张三') "
                        "or an open_id (e.g. 'ou_xxx'). "
                        "Names are automatically resolved from the current group member list. "
                        "If a name cannot be resolved, the whole call fails — use feishu_group "
                        "action=list_members to check exact names first."
                    ),
                },
                "need_notification": {
                    "type": "boolean",
                    "description": "Whether to notify attendees",
                    "default": True,
                },
            },
            "required": ["title", "start_time", "end_time"],
        }

    async def execute(
        self,
        title: str,
        start_time: str,
        end_time: str,
        timezone: str = "Asia/Shanghai",
        description: str | None = None,
        calendar_id: str | None = None,
        attendees: list[str] | None = None,
        need_notification: bool = True,
        **kwargs: Any,
    ) -> str:
        if error := self._check_ready():
            return self._error_payload(error)
        if error := self._check_feishu_channel():
            return self._error_payload(error)

        try:
            start_unix = self._to_unix_seconds(start_time, timezone)
            end_unix = self._to_unix_seconds(end_time, timezone)
        except Exception as e:
            return self._error_payload(f"Invalid event time: {e}")

        if end_unix <= start_unix:
            return self._error_payload("end_time must be later than start_time")

        resolved_attendees: list[ResolvedUser] = []
        if attendees:
            resolved_attendees, unresolved, ambiguous, resolve_error = await self._resolve_users(
                attendees,
                allow_sender_fallback=False,
            )
            if resolve_error:
                return self._error_payload(resolve_error)
            if unresolved or ambiguous:
                return self._error_payload(
                    "Failed to resolve attendees",
                    unresolved=unresolved,
                    ambiguous=ambiguous,
                    resolved=[v.as_dict() for v in resolved_attendees],
                )

        final_calendar_id = (calendar_id or "").strip()
        if not final_calendar_id:
            final_calendar_id, calendar_error = await self._primary_calendar_id()
            if calendar_error:
                return self._error_payload(calendar_error)

        event = (
            CalendarEvent.builder()
            .summary(title.strip())
            .description((description or "").strip())
            .start_time(
                TimeInfo.builder()
                .timestamp(str(start_unix))
                .timezone(timezone)
                .build()
            )
            .end_time(
                TimeInfo.builder()
                .timestamp(str(end_unix))
                .timezone(timezone)
                .build()
            )
            .build()
        )
        request = (
            CreateCalendarEventRequest.builder()
            .calendar_id(final_calendar_id)
            .user_id_type("open_id")
            .idempotency_key(str(uuid.uuid4()))
            .request_body(event)
            .build()
        )

        try:
            response = await self._run_sync(self._client.calendar.v4.calendar_event.create, request)
        except Exception as e:
            return self._error_payload(f"Failed to create calendar event: {e}")

        if not response.success():
            return self._error_payload(
                "Failed to create calendar event",
                code=response.code,
                msg=response.msg,
            )

        event_data = response.data.event if response.data else None
        event_id = str(getattr(event_data, "event_id", "") or "").strip()
        app_link = str(getattr(event_data, "app_link", "") or "").strip()

        attendee_add_warning = None
        if event_id and resolved_attendees:
            attendee_add_warning = await self._add_event_attendees(
                calendar_id=final_calendar_id,
                event_id=event_id,
                attendees=resolved_attendees,
                need_notification=need_notification,
            )

        payload: dict[str, Any] = {
            "calendar_id": final_calendar_id,
            "event_id": event_id,
            "title": title.strip(),
            "start_time_unix": start_unix,
            "end_time_unix": end_unix,
            "app_link": app_link,
            "attendees": [v.as_dict() for v in resolved_attendees],
        }
        if attendee_add_warning:
            payload["attendee_add_warning"] = attendee_add_warning
        return self._ok_payload(**payload)

    async def _primary_calendar_id(self) -> tuple[str, str | None]:
        request = PrimaryCalendarRequest.builder().user_id_type("open_id").build()
        try:
            response = await self._run_sync(self._client.calendar.v4.calendar.primary, request)
        except Exception as e:
            return "", f"Failed to get primary calendar: {e}"

        if not response.success():
            return "", (
                "Failed to get primary calendar. Provide calendar_id explicitly. "
                f"code={response.code}, msg={response.msg}"
            )

        calendars = response.data.calendars if response.data else []
        for item in (calendars or []):
            calendar = getattr(item, "calendar", None)
            calendar_id = str(getattr(calendar, "calendar_id", "") or "").strip()
            if calendar_id:
                return calendar_id, None
        return "", "No primary calendar found. Provide calendar_id explicitly."

    async def _add_event_attendees(
        self,
        *,
        calendar_id: str,
        event_id: str,
        attendees: list[ResolvedUser],
        need_notification: bool,
    ) -> str | None:
        attendee_models = [
            CalendarEventAttendee.builder()
            .type("user")
            .attendee_id(item.open_id)
            .build()
            for item in attendees
        ]
        body = (
            CreateCalendarEventAttendeeRequestBody.builder()
            .attendees(attendee_models)
            .need_notification(need_notification)
            .build()
        )
        request = (
            CreateCalendarEventAttendeeRequest.builder()
            .calendar_id(calendar_id)
            .event_id(event_id)
            .user_id_type("open_id")
            .request_body(body)
            .build()
        )
        try:
            response = await self._run_sync(
                self._client.calendar.v4.calendar_event_attendee.create,
                request,
            )
        except Exception as e:
            return f"Failed to add attendees: {e}"

        if not response.success():
            return f"Failed to add attendees: code={response.code}, msg={response.msg}"
        return None


class FeishuTaskTool(FeishuToolBase):
    """Create Feishu tasks and assign members from group context."""

    @property
    def name(self) -> str:
        return "feishu_task"

    @property
    def description(self) -> str:
        return (
            "Create a Feishu task and assign it to people in the current group. "
            "Pass assignee display names (e.g. '张三') or open_ids; "
            "the tool automatically resolves them from group members — "
            "NO need to call feishu_group first unless you want to verify names."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Task title/summary"},
                "description": {"type": "string", "description": "Optional task description"},
                "assignees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Assignee list. Each entry can be a display name (e.g. '张三') "
                        "or an open_id (e.g. 'ou_xxx'). "
                        "Names are automatically resolved from the current group member list. "
                        "Use feishu_group action=list_members to check exact names if resolution fails."
                    ),
                },
                "due_at": {
                    "type": "string",
                    "description": "Optional due time (ISO8601 or unix seconds/ms)",
                },
                "is_all_day": {
                    "type": "boolean",
                    "description": "Whether due_at should be treated as all-day",
                    "default": False,
                },
            },
            "required": ["summary"],
        }

    async def execute(
        self,
        summary: str,
        description: str | None = None,
        assignees: list[str] | None = None,
        due_at: str | None = None,
        is_all_day: bool = False,
        **kwargs: Any,
    ) -> str:
        if error := self._check_ready():
            return self._error_payload(error)
        if error := self._check_feishu_channel():
            return self._error_payload(error)

        resolved, unresolved, ambiguous, resolve_error = await self._resolve_users(
            assignees,
            allow_sender_fallback=not assignees,
        )
        if resolve_error:
            return self._error_payload(resolve_error)
        if unresolved or ambiguous:
            return self._error_payload(
                "Failed to resolve assignees",
                unresolved=unresolved,
                ambiguous=ambiguous,
                resolved=[v.as_dict() for v in resolved],
            )

        task_builder = (
            InputTask.builder()
            .summary(summary.strip())
            .description((description or "").strip())
            .client_token(str(uuid.uuid4()))
        )

        if resolved:
            members = [
                Member.builder()
                .id(item.open_id)
                .type("user")
                .role("assignee")
                .name(item.name)
                .build()
                for item in resolved
            ]
            task_builder.members(members)

        if due_at:
            try:
                due_seconds = self._to_unix_seconds(due_at, "Asia/Shanghai")
                task_builder.due(
                    Due.builder()
                    .timestamp(due_seconds)
                    .is_all_day(bool(is_all_day))
                    .build()
                )
            except Exception as e:
                return self._error_payload(f"Invalid due_at: {e}")

        request = (
            CreateTaskRequest.builder()
            .user_id_type("open_id")
            .request_body(task_builder.build())
            .build()
        )

        try:
            response = await self._run_sync(self._client.task.v2.task.create, request)
        except Exception as e:
            return self._error_payload(f"Failed to create task: {e}")

        if not response.success():
            return self._error_payload(
                "Failed to create task",
                code=response.code,
                msg=response.msg,
            )

        task = response.data.task if response.data else None
        return self._ok_payload(
            task_id=str(getattr(task, "task_id", "") or ""),
            guid=str(getattr(task, "guid", "") or ""),
            summary=str(getattr(task, "summary", "") or summary),
            status=str(getattr(task, "status", "") or ""),
            url=str(getattr(task, "url", "") or ""),
            assignees=[item.as_dict() for item in resolved],
        )


class FeishuDriveTool(FeishuToolBase):
    """Manage Feishu Drive folders and upload local artifacts."""

    def __init__(self, app_id: str, app_secret: str, workspace: Path):
        super().__init__(app_id, app_secret)
        self._workspace = workspace.resolve()
        self._default_parent_token = "root"
        self._default_max_file_size_mb = 200

    @property
    def name(self) -> str:
        return "feishu_drive"

    @property
    def description(self) -> str:
        return "Create Feishu Drive folders and upload local files from workspace."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "create_folder",
                        "ensure_folder_path",
                        "upload_file",
                        "upload_files",
                        "grant_permission",
                    ],
                    "description": (
                        "Drive action to execute. "
                        "grant_permission: call POST /drive/v1/permissions/:token/members "
                        "to authorize a user or group for a doc/file."
                    ),
                },
                "parent_folder_token": {
                    "type": "string",
                    "description": "Parent folder token. Defaults to 'root'.",
                },
                "folder_token": {
                    "type": "string",
                    "description": "Target folder token for upload.",
                },
                "folder_name": {
                    "type": "string",
                    "description": "Folder name for create_folder.",
                },
                "folder_path": {
                    "type": "string",
                    "description": "Folder path like 'reports/2026Q1'. Will auto-create segments.",
                },
                "local_path": {
                    "type": "string",
                    "description": "Local file path for upload_file.",
                },
                "local_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Local file paths for upload_files.",
                },
                "file_name": {
                    "type": "string",
                    "description": "Optional override filename on Drive for upload_file.",
                },
                "max_size_mb": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1024,
                    "description": (
                        "Reject upload if local file exceeds this limit (MB). "
                        "Files >20 MB automatically use multipart upload "
                        "(upload_prepare/upload_part/upload_finish)."
                    ),
                },
                "file_token": {
                    "type": "string",
                    "description": "File/doc token for grant_permission action.",
                },
                "token_type": {
                    "type": "string",
                    "enum": ["file", "docx", "sheet", "bitable", "wiki"],
                    "description": "Resource type for grant_permission. Default 'file'.",
                },
                "member_type": {
                    "type": "string",
                    "enum": ["openchat", "openid", "unionid"],
                    "description": (
                        "Member type for grant_permission. "
                        "'openchat'=group chat, 'openid'=user open_id."
                    ),
                },
                "member_id": {
                    "type": "string",
                    "description": (
                        "Member ID for grant_permission. "
                        "Chat ID (oc_...) for openchat, open_id (ou_...) for openid. "
                        "Defaults to current group chat_id when member_type=openchat."
                    ),
                },
                "perm": {
                    "type": "string",
                    "enum": ["view", "edit", "full_access"],
                    "description": "Permission level for grant_permission. Default 'view'.",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        parent_folder_token: str | None = None,
        folder_token: str | None = None,
        folder_name: str | None = None,
        folder_path: str | None = None,
        local_path: str | None = None,
        local_paths: list[str] | None = None,
        file_name: str | None = None,
        max_size_mb: int | None = None,
        # grant_permission action parameters
        file_token: str | None = None,
        token_type: str = "file",
        member_type: str = "openchat",
        member_id: str | None = None,
        perm: str = "view",
        **kwargs: Any,
    ) -> str:
        if error := self._check_ready():
            return self._error_payload(error)

        # Drive operations only require app credentials, not a Feishu channel context.
        # Intentionally skipping _check_feishu_channel() here so Drive can be used
        # from any channel (CLI, Telegram, cron, heartbeat, etc.).
        parent_token = (parent_folder_token or self._default_parent_token).strip()
        max_size_bytes = max(1, max_size_mb or self._default_max_file_size_mb) * 1024 * 1024

        if action == "create_folder":
            if not folder_name:
                return self._error_payload("folder_name is required for create_folder")
            folder, create_error = await self._create_folder(parent_token, folder_name)
            if create_error:
                return self._error_payload(create_error)
            return self._ok_payload(**folder)

        if action == "ensure_folder_path":
            if not folder_path:
                return self._error_payload("folder_path is required for ensure_folder_path")
            ensured, ensure_error = await self._ensure_folder_path(parent_token, folder_path)
            if ensure_error:
                return self._error_payload(ensure_error)
            return self._ok_payload(**ensured)

        if action == "upload_file":
            if not local_path:
                return self._error_payload("local_path is required for upload_file")
            target_folder, created_info, folder_error = await self._resolve_target_folder(
                parent_token=parent_token,
                folder_token=folder_token,
                folder_path=folder_path,
            )
            if folder_error:
                return self._error_payload(folder_error)
            upload, upload_error = await self._upload_file(
                local_path=local_path,
                folder_token=target_folder,
                file_name=file_name,
                max_size_bytes=max_size_bytes,
            )
            if upload_error:
                return self._error_payload(upload_error, target_folder_token=target_folder)
            payload = {"target_folder_token": target_folder, **upload}
            if created_info:
                payload["folder_prepare"] = created_info
            return self._ok_payload(**payload)

        if action == "upload_files":
            if not local_paths:
                return self._error_payload("local_paths is required for upload_files")
            target_folder, created_info, folder_error = await self._resolve_target_folder(
                parent_token=parent_token,
                folder_token=folder_token,
                folder_path=folder_path,
            )
            if folder_error:
                return self._error_payload(folder_error)

            uploaded: list[dict[str, Any]] = []
            failed: list[dict[str, str]] = []
            for path in local_paths:
                item, item_error = await self._upload_file(
                    local_path=path,
                    folder_token=target_folder,
                    file_name=None,
                    max_size_bytes=max_size_bytes,
                )
                if item_error:
                    failed.append({"local_path": str(path), "error": item_error})
                else:
                    uploaded.append(item)

            if failed:
                return self._error_payload(
                    "Some files failed to upload",
                    target_folder_token=target_folder,
                    uploaded=uploaded,
                    failed=failed,
                    folder_prepare=created_info,
                )
            return self._ok_payload(
                target_folder_token=target_folder,
                uploaded=uploaded,
                count=len(uploaded),
                folder_prepare=created_info,
            )

        if action == "grant_permission":
            tok = (file_token or "").strip()
            tok_type = (token_type or "file").strip()
            mem_type = (member_type or "openchat").strip()
            mem_id = (member_id or self._chat_id or "").strip()
            perm_level = (perm or "view").strip()
            if not tok:
                return self._error_payload(
                    "file_token is required for grant_permission action"
                )
            if not mem_id:
                return self._error_payload(
                    "member_id is required (or invoke from a group chat context "
                    "so chat_id can be used as default)"
                )
            perm_error = await self._grant_permission(
                tok, tok_type,
                member_type=mem_type,
                member_id=mem_id,
                perm=perm_level,
            )
            if perm_error:
                return self._error_payload(perm_error)
            return self._ok_payload(
                file_token=tok,
                token_type=tok_type,
                member_type=mem_type,
                member_id=mem_id,
                perm=perm_level,
            )

        return self._error_payload(f"Unknown action: {action}")

    async def _resolve_target_folder(
        self,
        *,
        parent_token: str,
        folder_token: str | None,
        folder_path: str | None,
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        if folder_token and folder_token.strip():
            return folder_token.strip(), None, None
        if folder_path and folder_path.strip():
            ensured, ensure_error = await self._ensure_folder_path(parent_token, folder_path)
            if ensure_error:
                return "", None, ensure_error
            return str(ensured.get("folder_token") or ""), ensured, None
        return parent_token, None, None

    async def _ensure_folder_path(
        self,
        parent_token: str,
        folder_path: str,
    ) -> tuple[dict[str, Any], str | None]:
        parts = _split_folder_path(folder_path)
        if not parts:
            return {}, "folder_path is empty"

        current = parent_token
        created: list[dict[str, str]] = []
        reused: list[dict[str, str]] = []

        for segment in parts:
            existing, find_error = await self._find_child_folder(current, segment)
            if find_error:
                return {}, find_error
            if existing:
                current = existing["folder_token"]
                reused.append(existing)
                continue

            created_folder, create_error = await self._create_folder(current, segment)
            if create_error:
                return {}, create_error
            current = created_folder["folder_token"]
            created.append(created_folder)

        return {
            "folder_path": "/".join(parts),
            "folder_token": current,
            "created": created,
            "reused": reused,
        }, None

    async def _find_child_folder(
        self,
        parent_token: str,
        folder_name: str,
    ) -> tuple[dict[str, str] | None, str | None]:
        next_page = ""
        target_name = folder_name.strip()
        try:
            while True:
                builder = (
                    ListFileRequest.builder()
                    .folder_token(parent_token)
                    .page_size(200)
                )
                if next_page:
                    builder.page_token(next_page)
                request = builder.build()
                response = await self._run_sync(self._client.drive.v1.file.list, request)
                if not response.success():
                    return None, (
                        "Failed to list drive folder contents: "
                        f"code={response.code}, msg={response.msg}"
                    )

                for item in (response.data.files or []):
                    name = str(getattr(item, "name", "") or "").strip()
                    ftype = str(getattr(item, "type", "") or "").strip().lower()
                    token = str(getattr(item, "token", "") or "").strip()
                    url = str(getattr(item, "url", "") or "").strip()
                    if name == target_name and token and ftype == "folder":
                        return {
                            "folder_name": name,
                            "folder_token": token,
                            "folder_url": url,
                        }, None

                if not getattr(response.data, "has_more", False):
                    break
                next_page = str(getattr(response.data, "next_page_token", "") or "").strip()
                if not next_page:
                    break
        except Exception as e:
            return None, f"Failed to list drive folders: {e}"
        return None, None

    async def _create_folder(
        self,
        parent_token: str,
        folder_name: str,
    ) -> tuple[dict[str, str], str | None]:
        body = (
            CreateFolderFileRequestBody.builder()
            .name(_safe_drive_name(folder_name, "folder"))
            .folder_token(parent_token)
            .build()
        )
        request = CreateFolderFileRequest.builder().request_body(body).build()
        try:
            response = await self._run_sync(self._client.drive.v1.file.create_folder, request)
        except Exception as e:
            return {}, f"Failed to create folder: {e}"

        if not response.success():
            return {}, f"Failed to create folder: code={response.code}, msg={response.msg}"

        token = str(getattr(response.data, "token", "") or "").strip()
        url = str(getattr(response.data, "url", "") or "").strip()
        return {
            "folder_name": _safe_drive_name(folder_name, "folder"),
            "folder_token": token,
            "folder_url": url,
            "parent_folder_token": parent_token,
        }, None

    async def _upload_file(
        self,
        *,
        local_path: str,
        folder_token: str,
        file_name: str | None,
        max_size_bytes: int,
    ) -> tuple[dict[str, Any], str | None]:
        """Upload a local file to Feishu Drive.

        Routing logic (per official docs):
          - size <= 20 MB  → upload_all  (POST /drive/v1/files/upload_all)
          - size >  20 MB  → multipart   (upload_prepare/upload_part/upload_finish)
        Files exceeding max_size_bytes are rejected regardless of upload method.
        """
        try:
            file_path = self._resolve_local_file(local_path)
        except Exception as e:
            return {}, str(e)

        size = file_path.stat().st_size
        if size <= 0:
            return {}, f"Local file is empty: {file_path}"
        if size > max_size_bytes:
            return {}, (
                f"Local file exceeds configured size limit "
                f"({size / 1024 / 1024:.1f} MB > {max_size_bytes / 1024 / 1024:.0f} MB): "
                f"{file_path}"
            )

        upload_name = _safe_drive_name(file_name or file_path.name, "file")

        if size > _FEISHU_UPLOAD_ALL_MAX_BYTES:
            # Use multipart upload for files > 20 MB
            return await self._upload_file_multipart(
                file_path=file_path,
                folder_token=folder_token,
                upload_name=upload_name,
                size=size,
            )

        # Small file (≤ 20 MB): use upload_all with Adler-32 checksum
        checksum = self._adler32_file(file_path)
        try:
            with open(file_path, "rb") as f:
                body = (
                    UploadAllFileRequestBody.builder()
                    .file_name(upload_name)
                    .parent_type("explorer")
                    .parent_node(folder_token)
                    .size(size)
                    .checksum(checksum)
                    .file(f)
                    .build()
                )
                request = UploadAllFileRequest.builder().request_body(body).build()
                response = await self._run_sync(
                    self._client.drive.v1.file.upload_all, request
                )
        except Exception as e:
            return {}, f"Failed to upload file {file_path}: {e}"

        if not response.success():
            return {}, (
                f"Failed to upload file {file_path.name}: "
                f"code={response.code}, msg={response.msg}"
            )

        file_token = str(getattr(response.data, "file_token", "") or "").strip()
        return {
            "local_path": str(file_path),
            "file_name": upload_name,
            "file_token": file_token,
            "size_bytes": size,
            "checksum_adler32": checksum,
            "upload_method": "upload_all",
            "url_candidates": [
                f"https://www.feishu.cn/file/{file_token}",
                f"https://www.larksuite.com/file/{file_token}",
            ],
        }, None

    async def _upload_file_multipart(
        self,
        *,
        file_path: Path,
        folder_token: str,
        upload_name: str,
        size: int,
    ) -> tuple[dict[str, Any], str | None]:
        """Multipart upload for files > 20 MB.

        Steps:
          1. upload_prepare  → upload_id, block_size, block_num
          2. upload_part (×block_num)
          3. upload_finish   → file_token

        See official docs (2024-09-05):
          POST /open-apis/drive/v1/files/upload_prepare
          POST /open-apis/drive/v1/files/upload_part
          POST /open-apis/drive/v1/files/upload_finish
        """
        # Step 1: prepare
        try:
            prepare_body = (
                FileUploadInfo.builder()
                .file_name(upload_name)
                .parent_type("explorer")
                .parent_node(folder_token)
                .size(size)
                .build()
            )
            prepare_request = (
                UploadPrepareFileRequest.builder()
                .request_body(prepare_body)
                .build()
            )
            prepare_resp = await self._run_sync(
                self._client.drive.v1.file.upload_prepare, prepare_request
            )
        except Exception as e:
            return {}, f"Multipart upload_prepare failed for {file_path.name}: {e}"

        if not prepare_resp.success():
            return {}, (
                f"Multipart upload_prepare failed for {file_path.name}: "
                f"code={prepare_resp.code}, msg={prepare_resp.msg}"
            )

        upload_id = str(getattr(prepare_resp.data, "upload_id", "") or "").strip()
        block_size = int(getattr(prepare_resp.data, "block_size", 4 * 1024 * 1024) or 4 * 1024 * 1024)
        block_num = int(getattr(prepare_resp.data, "block_num", 0) or 0)
        if not upload_id or block_num <= 0:
            return {}, f"Multipart upload_prepare returned invalid data for {file_path.name}"

        # Step 2: upload parts
        try:
            with open(file_path, "rb") as f:
                for seq in range(block_num):
                    chunk = f.read(block_size)
                    if not chunk:
                        break
                    part_body = (
                        UploadPartFileRequestBody.builder()
                        .upload_id(upload_id)
                        .seq(seq)
                        .size(len(chunk))
                        .file(chunk)
                        .build()
                    )
                    part_request = (
                        UploadPartFileRequest.builder()
                        .request_body(part_body)
                        .build()
                    )
                    part_resp = await self._run_sync(
                        self._client.drive.v1.file.upload_part, part_request
                    )
                    if not part_resp.success():
                        return {}, (
                            f"Multipart upload_part seq={seq} failed for {file_path.name}: "
                            f"code={part_resp.code}, msg={part_resp.msg}"
                        )
        except Exception as e:
            return {}, f"Multipart upload_part failed for {file_path.name}: {e}"

        # Step 3: finish
        try:
            finish_body = (
                UploadFinishFileRequestBody.builder()
                .upload_id(upload_id)
                .block_num(block_num)
                .build()
            )
            finish_request = (
                UploadFinishFileRequest.builder()
                .request_body(finish_body)
                .build()
            )
            finish_resp = await self._run_sync(
                self._client.drive.v1.file.upload_finish, finish_request
            )
        except Exception as e:
            return {}, f"Multipart upload_finish failed for {file_path.name}: {e}"

        if not finish_resp.success():
            return {}, (
                f"Multipart upload_finish failed for {file_path.name}: "
                f"code={finish_resp.code}, msg={finish_resp.msg}"
            )

        file_token = str(getattr(finish_resp.data, "file_token", "") or "").strip()
        return {
            "local_path": str(file_path),
            "file_name": upload_name,
            "file_token": file_token,
            "size_bytes": size,
            "upload_method": "multipart",
            "block_num": block_num,
            "url_candidates": [
                f"https://www.feishu.cn/file/{file_token}",
                f"https://www.larksuite.com/file/{file_token}",
            ],
        }, None

    def _resolve_local_file(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = self._workspace / path
        resolved = path.resolve()
        try:
            resolved.relative_to(self._workspace)
        except ValueError:
            raise PermissionError(f"Path outside workspace is not allowed: {resolved}")
        if not resolved.exists():
            raise FileNotFoundError(f"Local file not found: {resolved}")
        if not resolved.is_file():
            raise IsADirectoryError(f"Not a file: {resolved}")
        return resolved

    @staticmethod
    def _adler32_file(path: Path) -> str:
        """Compute Adler-32 checksum as required by Feishu upload_all API.

        The official API parameter 'checksum' expects an Adler-32 value
        (not MD5/SHA). Returns the checksum as a decimal string.
        """
        value = 1  # Adler-32 initial value
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                value = zlib.adler32(chunk, value)
        return str(value & 0xFFFFFFFF)  # Ensure unsigned 32-bit


class FeishuGroupTool(FeishuToolBase):
    """Query Feishu group information: list members of the current group chat."""

    @property
    def name(self) -> str:
        return "feishu_group"

    @property
    def description(self) -> str:
        return (
            "Query Feishu group information. Use action='list_members' to get the "
            "display name and open_id of every member in the current group chat. "
            "Call this when you need to know who is in the group, or when "
            "feishu_calendar / feishu_task attendee/assignee resolution fails."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_members"],
                    "description": "'list_members': return all members of the current group chat.",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str = "list_members", **kwargs: Any) -> str:
        if error := self._check_ready():
            return self._error_payload(error)
        if error := self._check_feishu_channel():
            return self._error_payload(error)

        if action == "list_members":
            if not self._chat_id:
                return self._error_payload(
                    "No chat context — this tool only works when invoked from a Feishu channel."
                )
            members, error = await self._list_group_members()
            if error:
                return self._error_payload(
                    error,
                    hint=(
                        "Ensure the app has 'im:chat.group_info:readonly' permission in "
                        "Feishu Open Platform > Permissions & Scopes, and that the bot "
                        "is a member of the target group."
                    ),
                )
            return self._ok_payload(
                chat_id=self._chat_id,
                count=len(members),
                members=members,
            )

        return self._error_payload(f"Unknown action: {action}")


class FeishuHandoffTool(FeishuToolBase):
    """Generic collaboration handoff orchestrator for Feishu."""

    def __init__(self, app_id: str, app_secret: str, workspace: Path):
        super().__init__(app_id, app_secret)
        self._workspace = workspace.resolve()
        self._drive = FeishuDriveTool(app_id, app_secret, workspace)
        self._doc = FeishuDocTool(app_id, app_secret)
        self._task = FeishuTaskTool(app_id, app_secret)
        self._calendar = FeishuCalendarTool(app_id, app_secret)

    @property
    def name(self) -> str:
        return "feishu_handoff"

    @property
    def description(self) -> str:
        return (
            "Generic Feishu handoff orchestration: archive artifacts to Drive, "
            "optionally create summary doc/task/calendar, and return unified delivery receipts."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "artifacts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Local workspace file paths to upload.",
                },
                "folder_path": {
                    "type": "string",
                    "description": "Optional Drive folder path like 'deliveries/2026-02-26'.",
                },
                "folder_token": {
                    "type": "string",
                    "description": "Optional existing Drive folder token (higher priority than folder_path).",
                },
                "parent_folder_token": {
                    "type": "string",
                    "description": "Parent folder for folder_path creation. Defaults to root.",
                },
                "summary_title": {"type": "string", "description": "Optional summary doc title."},
                "summary_content": {"type": "string", "description": "Optional summary doc content."},
                "task_summary": {"type": "string", "description": "Optional task summary to create."},
                "task_description": {"type": "string", "description": "Optional task description."},
                "task_assignees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional task assignees (open_id or @name).",
                },
                "task_due_at": {"type": "string", "description": "Optional task due datetime."},
                "task_is_all_day": {"type": "boolean", "default": False},
                "calendar_title": {"type": "string", "description": "Optional calendar event title."},
                "calendar_start_time": {
                    "type": "string",
                    "description": "Calendar start time when calendar_title is provided.",
                },
                "calendar_end_time": {
                    "type": "string",
                    "description": "Calendar end time when calendar_title is provided.",
                },
                "calendar_timezone": {"type": "string", "default": "Asia/Shanghai"},
                "calendar_description": {"type": "string"},
                "calendar_attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional calendar attendees (open_id or @name).",
                },
                "continue_on_error": {
                    "type": "boolean",
                    "default": True,
                    "description": "If false, stop at first failed sub-step.",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "Only return orchestration plan, do not execute API calls.",
                },
            },
        }

    async def execute(
        self,
        artifacts: list[str] | None = None,
        folder_path: str | None = None,
        folder_token: str | None = None,
        parent_folder_token: str | None = None,
        summary_title: str | None = None,
        summary_content: str | None = None,
        task_summary: str | None = None,
        task_description: str | None = None,
        task_assignees: list[str] | None = None,
        task_due_at: str | None = None,
        task_is_all_day: bool = False,
        calendar_title: str | None = None,
        calendar_start_time: str | None = None,
        calendar_end_time: str | None = None,
        calendar_timezone: str = "Asia/Shanghai",
        calendar_description: str | None = None,
        calendar_attendees: list[str] | None = None,
        continue_on_error: bool = True,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> str:
        if error := self._check_ready():
            return self._error_payload(error)
        # Note: intentionally not calling _check_feishu_channel() here.
        # Handoff orchestrates Drive uploads which work from any channel.
        # Individual sub-tools (doc/task/calendar) that need Feishu group context
        # will return their own errors if invoked without a Feishu channel.

        artifacts = artifacts or []
        steps: list[dict[str, Any]] = []
        outputs: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []

        if dry_run:
            plan = {
                "folder": {
                    "folder_token": folder_token,
                    "folder_path": folder_path,
                    "parent_folder_token": parent_folder_token or "root",
                },
                "artifacts_count": len(artifacts),
                "create_summary_doc": bool(summary_title or summary_content),
                "create_task": bool(task_summary),
                "create_calendar": bool(calendar_title),
            }
            return self._ok_payload(plan=plan, dry_run=True)

        self._set_children_context()

        target_folder_token = (folder_token or "").strip()
        if folder_path and not target_folder_token:
            res = await self._drive.execute(
                action="ensure_folder_path",
                folder_path=folder_path,
                parent_folder_token=parent_folder_token or "root",
            )
            payload = self._parse_payload(res)
            step = {"step": "ensure_folder_path", "ok": bool(payload.get("ok", False)), "result": payload}
            steps.append(step)
            if payload.get("ok"):
                target_folder_token = str(payload.get("folder_token") or "")
                outputs["folder"] = payload
            else:
                errors.append({"step": "ensure_folder_path", "error": payload.get("error", "unknown error")})
                if not continue_on_error:
                    return self._error_payload(
                        "handoff failed",
                        steps=steps,
                        errors=errors,
                        outputs=outputs,
                    )
        elif target_folder_token:
            outputs["folder"] = {"folder_token": target_folder_token}

        if artifacts:
            upload_kwargs: dict[str, Any] = {
                "action": "upload_files",
                "local_paths": artifacts,
            }
            if target_folder_token:
                upload_kwargs["folder_token"] = target_folder_token
            elif parent_folder_token:
                upload_kwargs["parent_folder_token"] = parent_folder_token

            res = await self._drive.execute(**upload_kwargs)
            payload = self._parse_payload(res)
            step = {"step": "upload_files", "ok": bool(payload.get("ok", False)), "result": payload}
            steps.append(step)
            if payload.get("ok"):
                outputs["uploads"] = payload
                if not target_folder_token:
                    target_folder_token = str(payload.get("target_folder_token") or "")
            else:
                errors.append({"step": "upload_files", "error": payload.get("error", "unknown error")})
                outputs["uploads"] = payload
                if not continue_on_error:
                    return self._error_payload(
                        "handoff failed",
                        steps=steps,
                        errors=errors,
                        outputs=outputs,
                    )

        if summary_title or summary_content:
            res = await self._doc.execute(
                title=(summary_title or "交接摘要").strip(),
                content=(summary_content or "").strip(),
                folder_token=target_folder_token or None,
            )
            payload = self._parse_payload(res)
            step = {"step": "create_summary_doc", "ok": bool(payload.get("ok", False)), "result": payload}
            steps.append(step)
            if payload.get("ok"):
                outputs["summary_doc"] = payload
            else:
                errors.append({"step": "create_summary_doc", "error": payload.get("error", "unknown error")})
                if not continue_on_error:
                    return self._error_payload(
                        "handoff failed",
                        steps=steps,
                        errors=errors,
                        outputs=outputs,
                    )

        if task_summary:
            res = await self._task.execute(
                summary=task_summary,
                description=task_description or "",
                assignees=task_assignees,
                due_at=task_due_at,
                is_all_day=task_is_all_day,
            )
            payload = self._parse_payload(res)
            step = {"step": "create_task", "ok": bool(payload.get("ok", False)), "result": payload}
            steps.append(step)
            if payload.get("ok"):
                outputs["task"] = payload
            else:
                errors.append({"step": "create_task", "error": payload.get("error", "unknown error")})
                if not continue_on_error:
                    return self._error_payload(
                        "handoff failed",
                        steps=steps,
                        errors=errors,
                        outputs=outputs,
                    )

        if calendar_title:
            if not calendar_start_time or not calendar_end_time:
                errors.append(
                    {
                        "step": "create_calendar",
                        "error": "calendar_start_time and calendar_end_time are required when calendar_title is set",
                    }
                )
                steps.append(
                    {
                        "step": "create_calendar",
                        "ok": False,
                        "result": {"ok": False, "error": errors[-1]["error"]},
                    }
                )
                if not continue_on_error:
                    return self._error_payload(
                        "handoff failed",
                        steps=steps,
                        errors=errors,
                        outputs=outputs,
                    )
            else:
                res = await self._calendar.execute(
                    title=calendar_title,
                    start_time=calendar_start_time,
                    end_time=calendar_end_time,
                    timezone=calendar_timezone,
                    description=calendar_description or "",
                    attendees=calendar_attendees,
                )
                payload = self._parse_payload(res)
                step = {"step": "create_calendar", "ok": bool(payload.get("ok", False)), "result": payload}
                steps.append(step)
                if payload.get("ok"):
                    outputs["calendar"] = payload
                else:
                    errors.append({"step": "create_calendar", "error": payload.get("error", "unknown error")})
                    if not continue_on_error:
                        return self._error_payload(
                            "handoff failed",
                            steps=steps,
                            errors=errors,
                            outputs=outputs,
                        )

        if errors:
            return self._error_payload(
                "handoff completed with partial failures",
                steps=steps,
                errors=errors,
                outputs=outputs,
            )
        return self._ok_payload(steps=steps, outputs=outputs)

    def _set_children_context(self) -> None:
        for tool in (self._drive, self._doc, self._task, self._calendar):
            tool.set_context(
                channel=self._channel,
                chat_id=self._chat_id,
                message_id=self._message_id,
                sender_id=self._sender_id,
                metadata=self._metadata,
            )

    @staticmethod
    def _parse_payload(raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
            return {"ok": False, "error": "Non-dict tool payload", "raw": raw}
        except Exception:
            return {"ok": False, "error": "Invalid JSON payload", "raw": raw}
