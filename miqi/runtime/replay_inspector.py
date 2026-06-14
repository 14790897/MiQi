"""Live-independent replay/debug inspector over the runtime DB."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from miqi.runtime.replay_document import (
    canonical_replay_payload,
    ledger_item_to_dict,
    timeline_to_dict,
    with_document_hash,
)
from miqi.runtime.replay_protocol import ReplayIntegrityCheck, ReplayIntegrityReport
from miqi.runtime.replay_runtime import ReplayRuntime
from miqi.runtime.stored_runtime import StoredRuntimeReader, StoredThreadBundle
from miqi.runtime.thread_runtime import RuntimeThread


class ReplayInspector:
    """Build deterministic replay/debug views for stored runtime threads."""

    def __init__(self, db_path: Path, *, client_id: str):
        self.db_path = Path(db_path)
        self.client_id = client_id
        self.reader = StoredRuntimeReader(self.db_path, client_id=client_id)

    async def load_bundle(self, thread_id: str, *, session_id: str | None = None) -> StoredThreadBundle:
        return await self.reader.load_bundle(thread_id, session_id=session_id)

    async def list_turn_ids(self, thread_id: str, *, session_id: str | None = None) -> list[str]:
        bundle = await self.load_bundle(thread_id, session_id=session_id)
        return ReplayRuntime.list_turn_ids_from_items(bundle.ledger_items)

    async def turn_timeline(
        self,
        thread_id: str,
        turn_id: str,
        *,
        session_id: str | None = None,
    ) -> Any | None:
        bundle = await self.load_bundle(thread_id, session_id=session_id)
        items = [item for item in bundle.ledger_items if item.turn_id == turn_id]
        if not items:
            return None
        return ReplayRuntime.build_timeline_from_items(thread_id, turn_id, items)

    # ── actual history (no fallback) ──────────────────────────────────────

    async def _actual_history_messages(self, thread: RuntimeThread) -> list[dict[str, Any]]:
        """Return provider message dicts from runtime_history_items rows only.

        Does NOT fall back to ledger reconstruction.  An empty history table
        returns [] so integrity checks can detect the mismatch.
        """
        items = await self.reader.load_history_items(thread)
        messages: list[dict[str, Any]] = []
        for item in items:
            msg: dict[str, Any] = {"role": item.role, "content": item.content}
            msg.update(item.payload.get("message_fields", {}))
            messages.append(msg)
        return messages

    # ── reports ───────────────────────────────────────────────────────────

    async def provider_messages_report(
        self,
        thread_id: str,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        bundle = await self.load_bundle(thread_id, session_id=session_id)
        history_messages = await self._actual_history_messages(bundle.thread)
        ledger_messages = []
        for item in bundle.ledger_items:
            if item.item_type == "message" and item.role is not None:
                msg = {"role": item.role, "content": item.content}
                msg.update(item.payload.get("message_fields", {}))
                ledger_messages.append(msg)
        return {
            "threadId": bundle.thread.thread_id,
            "sessionId": bundle.thread.session_id,
            "historyMessages": history_messages,
            "ledgerMessages": ledger_messages,
            "matches": history_messages == ledger_messages,
            "historyCount": len(history_messages),
            "ledgerCount": len(ledger_messages),
        }

    async def integrity_report(
        self,
        thread_id: str,
        *,
        session_id: str | None = None,
    ) -> ReplayIntegrityReport:
        bundle = await self.load_bundle(thread_id, session_id=session_id)
        checks: list[ReplayIntegrityCheck] = []

        message_report = await self.provider_messages_report(
            thread_id, session_id=bundle.thread.session_id,
        )
        checks.append(ReplayIntegrityCheck(
            name="providerHistoryMatchesLedger",
            ok=bool(message_report["matches"]),
            severity="error" if not message_report["matches"] else "info",
            message=(
                "Provider history matches ledger reconstruction"
                if message_report["matches"]
                else "Provider history differs from ledger reconstruction"
            ),
            details={
                "historyCount": message_report["historyCount"],
                "ledgerCount": message_report["ledgerCount"],
            },
        ))

        seqs = [item.seq for item in bundle.ledger_items]
        monotonic = seqs == sorted(seqs) and len(seqs) == len(set(seqs))
        checks.append(ReplayIntegrityCheck(
            name="ledgerSeqMonotonic",
            ok=monotonic,
            severity="error" if not monotonic else "info",
            message="Ledger sequence numbers are monotonic and unique" if monotonic else "Ledger sequence numbers are not monotonic or unique",
            details={"seqs": seqs},
        ))

        turn_ids = ReplayRuntime.list_turn_ids_from_items(bundle.ledger_items)
        timelines = [
            ReplayRuntime.build_timeline_from_items(
                thread_id,
                turn_id,
                [item for item in bundle.ledger_items if item.turn_id == turn_id],
            )
            for turn_id in turn_ids
        ]
        incomplete = [timeline.turn_id for timeline in timelines if timeline.status == "incomplete"]
        checks.append(ReplayIntegrityCheck(
            name="turnsHaveTerminalStatus",
            ok=not incomplete,
            severity="warning" if incomplete else "info",
            message="All turns have terminal status" if not incomplete else "Some turns have no terminal status",
            details={"incompleteTurnIds": incomplete},
        ))

        pending_tools = [
            {"turnId": timeline.turn_id, "toolCallId": tool.tool_call_id}
            for timeline in timelines
            for tool in timeline.tool_calls
            if tool.status == "pending"
        ]
        pending_execs = [
            {"turnId": timeline.turn_id, "toolCallId": command.tool_call_id}
            for timeline in timelines
            for command in timeline.exec_commands
            if command.status == "pending"
        ]
        pending_approvals = [
            {"turnId": timeline.turn_id, "approvalId": approval.approval_id}
            for timeline in timelines
            for approval in timeline.approval_events
            if approval.decision == "pending"
        ]
        pending_count = len(pending_tools) + len(pending_execs) + len(pending_approvals)
        checks.append(ReplayIntegrityCheck(
            name="noDanglingOperations",
            ok=pending_count == 0,
            severity="warning" if pending_count else "info",
            message="No dangling tool/exec/approval operations" if pending_count == 0 else "Some tool/exec/approval operations are still pending",
            details={
                "pendingTools": pending_tools,
                "pendingExecs": pending_execs,
                "pendingApprovals": pending_approvals,
            },
        ))

        return ReplayIntegrityReport(
            thread_id=bundle.thread.thread_id,
            session_id=bundle.thread.session_id,
            ok=all(check.ok for check in checks if check.severity == "error"),
            checks=checks,
        )

    # ── turn response (used by debug/replay/turn handler) ────────────────

    async def build_turn_response(
        self,
        thread_id: str,
        turn_id: str,
        *,
        session_id: str | None = None,
        include_raw_ledger: bool = False,
    ) -> dict[str, Any]:
        bundle = await self.load_bundle(thread_id, session_id=session_id)
        timeline = await self.turn_timeline(thread_id, turn_id, session_id=session_id)
        raw_items: list[dict[str, Any]] = []
        if include_raw_ledger:
            raw_items = [
                ledger_item_to_dict(item)
                for item in bundle.ledger_items
                if item.turn_id == turn_id
            ]
        return {
            "threadId": bundle.thread.thread_id,
            "turnId": turn_id,
            "sessionId": bundle.thread.session_id,
            "source": "stored",
            "timeline": asdict(timeline) if timeline is not None else None,
            "rawLedgerItems": raw_items,
        }

    # ── full document ─────────────────────────────────────────────────────

    async def build_thread_document(
        self,
        thread_id: str,
        *,
        session_id: str | None = None,
        include_raw_ledger: bool = False,
    ) -> dict[str, Any]:
        bundle = await self.load_bundle(thread_id, session_id=session_id)
        turn_ids = ReplayRuntime.list_turn_ids_from_items(bundle.ledger_items)
        turns = [
            timeline_to_dict(ReplayRuntime.build_timeline_from_items(
                bundle.thread.thread_id,
                turn_id,
                [item for item in bundle.ledger_items if item.turn_id == turn_id],
            ))
            for turn_id in turn_ids
        ]
        provider_messages = await self._actual_history_messages(bundle.thread)
        integrity = (await self.integrity_report(
            bundle.thread.thread_id, session_id=bundle.thread.session_id,
        )).to_dict()
        payload = canonical_replay_payload(
            thread_id=bundle.thread.thread_id,
            session_id=bundle.thread.session_id,
            source="stored",
            turns=turns,
            provider_messages=provider_messages,
            integrity=integrity,
            raw_ledger_items=(
                [ledger_item_to_dict(item) for item in bundle.ledger_items]
                if include_raw_ledger
                else []
            ),
        )
        return with_document_hash(payload)
