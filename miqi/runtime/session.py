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

    def __init__(self, *, services: RuntimeServices, event_queue: asyncio.Queue | None = None):
        self.services = services
        self.session_id = services.session_id
        self._submissions: asyncio.Queue[Any] = asyncio.Queue()
        self._events: asyncio.Queue[Any] = event_queue or asyncio.Queue()
        self._runner = TaskRunner(services=services, event_queue=self._events)
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()
        # Phase 14 follow-up: track active turn for abort
        self._active_turn_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

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

        All typed events emitted by the orchestrator, AgentControl, spawn-tool,
        and other services flow into the session's event queue and become
        available through next_event(). This includes tool-call-begin/end,
        sub-agent-spawned/completed, turn-start/complete, and error events.
        """
        # Shared event queue — services push into it, consumers read from it
        events: asyncio.Queue[Any] = asyncio.Queue()

        services = RuntimeServices.from_config(
            config=config,
            provider=provider,
            session_id=session_id,
            workspace=workspace,
            event_sink=events.put,  # asyncio.Queue.put is a coroutine sink
        )
        runtime = cls(services=services, event_queue=events)
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
        """Main dispatch loop: dequeue submissions → TaskRunner.handle().

        Phase 14 follow-up: non-blocking dispatch that can dequeue AbortTurn
        while a UserMessage turn is still running. Uses asyncio.wait() to
        race the active turn task against new submissions.
        """
        from miqi.protocol.commands import AbortTurn

        while not self._stopped.is_set():
            # If no turn is running, wait for the next submission
            async with self._lock:
                if self._active_turn_task is None:
                    try:
                        submission = await asyncio.wait_for(
                            self._submissions.get(), timeout=0.5,
                        )
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

                    if isinstance(submission, AbortTurn):
                        await self._runner.handle(submission)
                        continue

                    # Spawn new turn
                    self._active_turn_task = asyncio.create_task(
                        self._runner.handle(submission)
                    )
                    continue  # Back to top of loop to enter the wait

            # A turn is running — wait for EITHER it to finish OR a new submission
            assert self._active_turn_task is not None
            done, pending = await asyncio.wait(
                [self._active_turn_task, asyncio.create_task(self._submissions.get())],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel the get() waiter if the turn finished first
            for p in pending:
                p.cancel()

            for d in done:
                if d is self._active_turn_task:
                    # Turn finished
                    async with self._lock:
                        self._active_turn_task = None
                    try:
                        await d  # Let any exception surface
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass
                else:
                    # New submission arrived while turn was running
                    submission = d.result()
                    if isinstance(submission, AbortTurn):
                        async with self._lock:
                            if self._active_turn_task is not None:
                                self._active_turn_task.cancel()
                                self._active_turn_task = None
                        await self._runner.handle(submission)
                    # Non-AbortTurn submissions while a turn is running
                    # are dropped silently (avoid stacking turns)
