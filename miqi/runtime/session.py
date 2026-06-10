"""Runtime session — the Codex-like entry point for all frontends.

Owns submissions queue, event queue, TaskRunner, and service lifecycle.
Frontends should use RuntimeSession.create() + start/stop/submit/next_event.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from miqi.protocol.commands import Submission
from miqi.runtime.services import RuntimeServices
from miqi.runtime.task_runner import TaskRunner


class RuntimeSession:
    """A single runtime session with submission queue and event stream.

    Usage:
        runtime = RuntimeSession.create(config=..., provider=..., ...)
        await runtime.start()
        await runtime.submit(UserMessage(content="hello"))
        while True:
            event = await runtime.next_event(timeout=120)
            if isinstance(event, AgentMessageEvent):
                print(event.content)
                break
        await runtime.stop()
    """

    def __init__(self, *, services: RuntimeServices):
        self.services = services
        self.session_id = services.session_id
        self._submissions: asyncio.Queue[Any] = asyncio.Queue()
        self._events: asyncio.Queue[Any] = asyncio.Queue()
        self._runner = TaskRunner(services=services, event_queue=self._events)
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    @classmethod
    def create(
        cls,
        *,
        config: Any,
        provider: Any,
        session_id: str,
        workspace: Path,
    ) -> "RuntimeSession":
        """Create a RuntimeSession from config and provider.

        The event_sink is wired automatically to the session's internal
        event queue so that services (AgentControl, orchestrator) emit
        typed events that consumers read via next_event().
        """
        services = RuntimeServices.from_config(
            config=config,
            provider=provider,
            session_id=session_id,
            workspace=workspace,
            event_sink=None,  # Services emit via event_emitter, not this sink
        )
        runtime = cls(services=services)
        return runtime

    async def start(self) -> None:
        """Start the background dispatch loop."""
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the dispatch loop and tear down agent resources."""
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self.services.agent_loop.stop()
        await self.services.agent_loop.close_mcp()

    async def submit(self, submission: Any) -> None:
        """Submit a command to the runtime (UserMessage, AbortTurn, etc.)."""
        await self._submissions.put(submission)

    async def next_event(self, timeout: float | None = None) -> Any | None:
        """Wait for the next typed event from the runtime.

        Returns None on timeout, otherwise a protocol event dataclass.
        """
        try:
            if timeout is None:
                return await self._events.get()
            return await asyncio.wait_for(self._events.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def _run(self) -> None:
        """Main dispatch loop: dequeue submissions → TaskRunner.handle()."""
        while not self._stopped.is_set():
            try:
                submission = await self._submissions.get()
                await self._runner.handle(submission)
            except asyncio.CancelledError:
                break
            except Exception:
                # Don't let a single submission crash the loop
                pass
