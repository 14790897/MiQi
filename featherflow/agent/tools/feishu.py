"""Feishu business tools: cloud docs, calendar events, and tasks."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
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
    from lark_oapi.api.im.v1 import GetChatMembersRequest
    from lark_oapi.api.task.v2 import CreateTaskRequest, Due, InputTask, Member

    FEISHU_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
    lark = None


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
            },
            "required": ["title"],
        }

    async def execute(
        self,
        title: str,
        folder_token: str | None = None,
        content: str | None = None,
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
        return "Create a Feishu calendar event and add attendees from group members."

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
                    "description": "Optional attendee list (open_id or @name)",
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
        return "Create a Feishu task and assign it to people in the current group."

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
                    "description": "Optional assignee list (open_id or @name)",
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
