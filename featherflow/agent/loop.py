"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Awaitable, Callable

from loguru import logger

from featherflow.agent.context import ContextBuilder
from featherflow.agent.memory import MemoryStore
from featherflow.agent.subagent import SubagentManager
from featherflow.agent.tools.cron import CronTool
from featherflow.agent.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)
from featherflow.agent.tools.message import MessageTool
from featherflow.agent.tools.papers import PaperDownloadTool, PaperGetTool, PaperSearchTool
from featherflow.agent.tools.registry import ToolRegistry
from featherflow.agent.tools.shell import ExecTool
from featherflow.agent.tools.spawn import SpawnTool
from featherflow.agent.tools.web import WebFetchTool, WebSearchTool
from featherflow.bus.events import InboundMessage, OutboundMessage
from featherflow.bus.queue import MessageBus
from featherflow.config.schema import (
    AgentMemoryConfig,
    AgentSelfImprovementConfig,
    AgentSessionConfig,
    ChannelsConfig,
    ExecToolConfig,
    PapersToolConfig,
    WebToolsConfig,
)
from featherflow.cron.service import CronService
from featherflow.providers.base import LLMProvider
from featherflow.session.manager import Session, SessionManager


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        agent_name: str = "featherflow",
        model: str | None = None,
        max_iterations: int = 40,
        reflect_after_tool_calls: bool = True,
        web_config: WebToolsConfig | None = None,
        paper_config: PapersToolConfig | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        memory_window: int = 100,
        max_tool_result_chars: int = 16000,
        context_limit_chars: int = 600000,
        brave_api_key: str | None = None,
        exec_config: ExecToolConfig | None = None,
        memory_config: AgentMemoryConfig | None = None,
        self_improvement_config: AgentSelfImprovementConfig | None = None,
        session_config: AgentSessionConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
    ):
        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.agent_name = agent_name.strip() or "featherflow"
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.reflect_after_tool_calls = reflect_after_tool_calls
        self.web_config = web_config or WebToolsConfig()
        self.paper_config = paper_config or PapersToolConfig()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.max_tool_result_chars = max_tool_result_chars
        self.context_limit_chars = context_limit_chars
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.memory_config = memory_config or AgentMemoryConfig()
        self.self_improvement_config = self_improvement_config or AgentSelfImprovementConfig()
        self.session_config = session_config or AgentSessionConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace

        self.memory = MemoryStore(
            workspace=workspace,
            flush_every_updates=self.memory_config.flush_every_updates,
            flush_interval_seconds=self.memory_config.flush_interval_seconds,
            short_term_turns=self.memory_config.short_term_turns,
            pending_limit=self.memory_config.pending_limit,
            self_improvement_enabled=self.self_improvement_config.enabled,
            max_lessons_in_prompt=self.self_improvement_config.max_lessons_in_prompt,
            min_lesson_confidence=self.self_improvement_config.min_lesson_confidence,
            max_lessons=self.self_improvement_config.max_lessons,
            lesson_confidence_decay_hours=self.self_improvement_config.lesson_confidence_decay_hours,
            feedback_max_message_chars=self.self_improvement_config.feedback_max_message_chars,
            feedback_require_prefix=self.self_improvement_config.feedback_require_prefix,
            promotion_enabled=self.self_improvement_config.promotion_enabled,
            promotion_min_users=self.self_improvement_config.promotion_min_users,
            promotion_triggers=self.self_improvement_config.promotion_triggers,
        )
        self.context = ContextBuilder(
            workspace,
            memory_store=self.memory,
            agent_name=self.agent_name,
        )
        self.sessions = session_manager or SessionManager(
            workspace,
            compact_threshold_messages=self.session_config.compact_threshold_messages,
            compact_threshold_bytes=self.session_config.compact_threshold_bytes,
            compact_keep_messages=self.session_config.compact_keep_messages,
        )
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            web_config=self.web_config,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._consolidation_tasks: set[asyncio.Task] = set()  # Strong refs to in-flight tasks
        self._consolidation_locks: dict[str, asyncio.Lock] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        for cls in (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
        ))
        self.tools.register(
            WebSearchTool(
                provider=self.web_config.search.provider,
                api_key=self.web_config.search.api_key or None,
                max_results=self.web_config.search.max_results,
                ollama_api_key=self.web_config.search.ollama_api_key or None,
                ollama_api_base=self.web_config.search.ollama_api_base,
            )
        )
        self.tools.register(
            WebFetchTool(
                provider=self.web_config.fetch.provider,
                ollama_api_key=self.web_config.fetch.ollama_api_key or None,
                ollama_api_base=self.web_config.fetch.ollama_api_base,
            )
        )
        self.tools.register(
            PaperSearchTool(
                provider=self.paper_config.provider,
                semantic_scholar_api_key=self.paper_config.semantic_scholar_api_key or None,
                timeout_seconds=self.paper_config.timeout_seconds,
                default_limit=self.paper_config.default_limit,
                max_limit=self.paper_config.max_limit,
            )
        )
        self.tools.register(
            PaperGetTool(
                provider=self.paper_config.provider,
                semantic_scholar_api_key=self.paper_config.semantic_scholar_api_key or None,
                timeout_seconds=self.paper_config.timeout_seconds,
            )
        )
        self.tools.register(
            PaperDownloadTool(
                workspace=self.workspace,
                provider=self.paper_config.provider,
                semantic_scholar_api_key=self.paper_config.semantic_scholar_api_key or None,
                timeout_seconds=self.paper_config.timeout_seconds,
            )
        )
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from featherflow.agent.tools.mcp import connect_mcp_servers
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except (Exception, asyncio.CancelledError) as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except (Exception, asyncio.CancelledError):
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None = None,
        sender_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Update context for all tools that need routing info."""
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.set_context(channel, chat_id, message_id)

        if spawn_tool := self.tools.get("spawn"):
            if isinstance(spawn_tool, SpawnTool):
                spawn_tool.set_context(channel, chat_id)

        if cron_tool := self.tools.get("cron"):
            if isinstance(cron_tool, CronTool):
                cron_tool.set_context(channel, chat_id)

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _estimate_chars(messages: list[dict]) -> int:
        """Rough character count of all message content (no tokenisation needed)."""
        total = 0
        for m in messages:
            c = m.get("content")
            if isinstance(c, str):
                total += len(c)
            elif isinstance(c, list):  # multimodal: list of blocks
                for block in c:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        total += len(block["text"])
        return total

    @staticmethod
    def _trim_context(
        messages: list[dict],
        limit_chars: int,
        current_chars: int,
    ) -> list[dict]:
        """Drop oldest assistant↔tool pairs until total chars fit under limit.

        Always keeps the system prompt (index 0) and the final user message.
        Returns the trimmed list (original is NOT mutated).
        """
        if limit_chars <= 0 or current_chars <= limit_chars:
            return messages

        # Identify trimmable range: after the system prompt, before the last user msg.
        # We look for (assistant, tool…) pairs to remove from the front.
        work = list(messages)
        while current_chars > limit_chars and len(work) > 2:
            # Find the first assistant message (after the system prompt)
            cut_start = None
            for i in range(1, len(work) - 1):
                if work[i].get("role") == "assistant":
                    cut_start = i
                    break
            if cut_start is None:
                break  # nothing left to trim

            # Collect consecutive assistant + tool result messages to drop together
            cut_end = cut_start + 1
            while cut_end < len(work) - 1 and work[cut_end].get("role") == "tool":
                cut_end += 1

            removed = work[cut_start:cut_end]
            removed_chars = sum(
                len(m.get("content", "")) if isinstance(m.get("content"), str) else 0
                for m in removed
            )
            work = work[:cut_start] + work[cut_end:]
            current_chars -= removed_chars
            logger.debug(
                "Context trim: dropped {} msgs ({} chars); remaining ~{} chars",
                len(removed), removed_chars, current_chars,
            )

        return work

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            val = next(iter(tc.arguments.values()), None) if tc.arguments else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop. Returns (final_content, tools_used, messages)."""
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []

        while iteration < self.max_iterations:
            iteration += 1

            # Trim oversized context before each LLM call
            if self.context_limit_chars > 0:
                est = self._estimate_chars(messages)
                if est > self.context_limit_chars:
                    logger.warning(
                        "Context too large (~{} chars, limit {}); trimming oldest turns",
                        est, self.context_limit_chars,
                    )
                    messages = self._trim_context(messages, self.context_limit_chars, est)

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if response.has_tool_calls:
                if on_progress:
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    # For MCP tools, create a progress forwarder that sends
                    # page-level progress to the user's chat channel
                    _mcp_on_progress = None
                    if tool_call.name.startswith("mcp_") and on_progress:
                        async def _mcp_on_progress(progress, total, _on_progress=on_progress):
                            if total:
                                pct = int(progress / total * 100)
                                await _on_progress(
                                    f"\u23f3 {progress}/{total} ({pct}%)",
                                    tool_hint=True,
                                )

                    result = await self.tools.execute(
                        tool_call.name,
                        tool_call.arguments,
                        _on_progress=_mcp_on_progress,
                    )
                    # Truncate large tool results to prevent context explosion.
                    # This applies to the live prompt; saved-session truncation is
                    # separate (see _save_turn / _TOOL_RESULT_MAX_CHARS).
                    if (
                        self.max_tool_result_chars > 0
                        and isinstance(result, str)
                        and len(result) > self.max_tool_result_chars
                    ):
                        truncated_note = (
                            f"\n... [truncated: original {len(result)} chars, "
                            f"showing first {self.max_tool_result_chars}]"
                        )
                        result = result[: self.max_tool_result_chars] + truncated_note
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
                    if tool_call.name == "message" and isinstance(result, str) and result.startswith("Message sent"):
                        final_content = None
                        return final_content, tools_used, messages
                if self.reflect_after_tool_calls:
                    messages.append(
                        {
                            "role": "user",
                            "content": "Reason silently about whether more tools are needed. Do not expose this reflection process unless explicitly asked.",
                        }
                    )
            else:
                final_content = self._strip_think(response.content)
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages

    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                try:
                    response = await self._process_message(msg)
                    if response is not None:
                        await self.bus.publish_outbound(response)
                    elif msg.channel == "cli":
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel, chat_id=msg.chat_id, content="", metadata=msg.metadata or {},
                        ))
                except Exception as e:
                    logger.error("Error processing message: {}", e)
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
            except asyncio.TimeoutError:
                continue

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        """Stop the agent loop."""
        self.memory.flush(force=True)
        self._running = False
        logger.info("Agent loop stopping")

    def _get_consolidation_lock(self, session_key: str) -> asyncio.Lock:
        lock = self._consolidation_locks.get(session_key)
        if lock is None:
            lock = asyncio.Lock()
            self._consolidation_locks[session_key] = lock
        return lock

    def _prune_consolidation_lock(self, session_key: str, lock: asyncio.Lock) -> None:
        """Drop lock entry if no longer in use."""
        if not lock.locked():
            self._consolidation_locks.pop(session_key, None)

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            self._set_tool_context(
                channel,
                chat_id,
                msg.metadata.get("message_id"),
                sender_id=msg.sender_id,
                metadata=msg.metadata,
            )
            history = session.get_history(max_messages=self.memory_window)
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content, channel=channel, chat_id=chat_id,
            )
            final_content, _, all_msgs = await self._run_agent_loop(messages)
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)
        previous_assistant = self._get_last_assistant_message(session)

        # Slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            lock = self._get_consolidation_lock(session.key)
            self._consolidating.add(session.key)
            try:
                async with lock:
                    snapshot = session.messages[session.last_consolidated:]
                    if snapshot:
                        temp = Session(key=session.key)
                        temp.messages = list(snapshot)
                        if not await self._consolidate_memory(temp, archive_all=True):
                            return OutboundMessage(
                                channel=msg.channel, chat_id=msg.chat_id,
                                content="Memory archival failed, session not cleared. Please try again.",
                            )
            except Exception:
                logger.exception("/new archival failed for {}", session.key)
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )
            finally:
                self._consolidating.discard(session.key)
                self._prune_consolidation_lock(session.key, lock)

            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="New session started.")
        if cmd == "/help":
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="Assistant commands:\n/new - Start a new conversation\n/help - Show available commands")

        unconsolidated = len(session.messages) - session.last_consolidated
        if (unconsolidated >= self.memory_window and session.key not in self._consolidating):
            self._consolidating.add(session.key)
            lock = self._get_consolidation_lock(session.key)

            async def _consolidate_and_unlock():
                try:
                    async with lock:
                        await self._consolidate_memory(session)
                finally:
                    self._consolidating.discard(session.key)
                    self._prune_consolidation_lock(session.key, lock)
                    _task = asyncio.current_task()
                    if _task is not None:
                        self._consolidation_tasks.discard(_task)

            _task = asyncio.create_task(_consolidate_and_unlock())
            self._consolidation_tasks.add(_task)

        self._set_tool_context(
            msg.channel,
            msg.chat_id,
            msg.metadata.get("message_id"),
            sender_id=msg.sender_id,
            metadata=msg.metadata,
        )
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        history = session.get_history(max_messages=self.memory_window)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel, chat_id=msg.chat_id,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages, on_progress=on_progress or _bus_progress,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)

        self.memory.record_turn(
            session_key=session.key,
            user_message=msg.content,
            assistant_message=final_content,
        )
        self.memory.record_user_feedback(
            session_key=session.key,
            user_message=msg.content,
            previous_assistant=previous_assistant,
            actor_key=msg.sender_id,
        )
        self.memory.flush_if_needed()

        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)

        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
                return None

        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=final_content,
            metadata=msg.metadata or {},
        )

    _TOOL_RESULT_MAX_CHARS = 500

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime
        for m in messages[skip:]:
            entry = {k: v for k, v in m.items() if k != "reasoning_content"}
            if entry.get("role") == "tool" and isinstance(entry.get("content"), str):
                content = entry["content"]
                if len(content) > self._TOOL_RESULT_MAX_CHARS:
                    entry["content"] = content[:self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def _consolidate_memory(self, session: Session, archive_all: bool = False) -> bool:
        """Archive consolidated turns into memory store and advance cursor."""
        try:
            if archive_all:
                keep_count = 0
                old_messages = session.messages
            else:
                keep_count = self.memory_window // 2
                if len(session.messages) <= keep_count:
                    return True
                if len(session.messages) - session.last_consolidated <= 0:
                    return True
                old_messages = session.messages[session.last_consolidated:-keep_count]
                if not old_messages:
                    return True

            pending_user: str | None = None
            for item in old_messages:
                role = item.get("role")
                content = str(item.get("content", "")).strip()
                if not content:
                    continue
                if role == "user":
                    pending_user = content
                elif role == "assistant" and pending_user is not None:
                    self.memory.record_turn(
                        session_key=session.key,
                        user_message=pending_user,
                        assistant_message=content,
                    )
                    pending_user = None
                elif role == "assistant":
                    self.memory.remember(content, immediate=False)

            self.memory.flush(force=True)
            session.last_consolidated = 0 if archive_all else len(session.messages) - keep_count
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return False

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        response = await self._process_message(msg, session_key=session_key, on_progress=on_progress)
        return response.content if response else ""

    @staticmethod
    def _get_last_assistant_message(session) -> str:
        """Get the last assistant message from a session, if available."""
        for item in reversed(session.messages):
            if item.get("role") == "assistant":
                return str(item.get("content", ""))
        return ""
