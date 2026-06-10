"""MiQi TUI — Textual-based terminal interface."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static
from textual.containers import Horizontal, Vertical
from textual.binding import Binding


class MiQiTui(App):
    """MiQi Terminal User Interface.

    Launch with:
        uv run python -m miqi.tui.app
    or via CLI:
        miqi tui
    """

    BINDINGS = [
        Binding("ctrl+c", "abort", "Abort current turn", priority=True),
        Binding("ctrl+n", "new_thread", "New conversation thread"),
        Binding("ctrl+p", "toggle_plan", "Toggle plan sidebar"),
        Binding("ctrl+s", "save_session", "Save current session"),
    ]

    CSS = """
    #chat {
        height: 1fr;
        overflow-y: auto;
        padding: 1;
    }
    #plan-sidebar {
        width: 30%;
        border-left: solid gray;
        padding: 1;
    }
    #input {
        dock: bottom;
        margin: 1;
    }
    """

    _plan_visible: bool = False
    _agent_loop: object = None  # AgentLoop instance for runtime connection

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Vertical(Static(id="chat"), id="chat-container")
            yield Vertical(Static(id="plan-sidebar"), id="plan-container")
        yield Input(placeholder="Type a message...", id="input")
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.query_one("#chat", Static).update(
            "Welcome to MiQi TUI!\n"
            "Type a message below and press Enter to send.\n"
            "Ctrl+C: abort | Ctrl+N: new thread | Ctrl+P: toggle plan",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Send message when user presses Enter."""
        if not event.value.strip():
            return
        content = event.value.strip()
        self._append_message("You", content)
        event.input.value = ""

        # If runtime is connected, process the message
        if self._agent_loop is not None:
            self._process_message(content)
        else:
            self._append_message("MiQi", "(No runtime connected. Set _agent_loop to an AgentLoop instance.)")

    def action_abort(self) -> None:
        """Abort the current turn."""
        if self._agent_loop is not None:
            try:
                self._agent_loop.stop()  # type: ignore[union-attr]
                self._append_message("System", "Turn aborted.")
            except Exception:
                pass

    def action_new_thread(self) -> None:
        """Start a new conversation thread."""
        chat = self.query_one("#chat", Static)
        chat.update("New thread started.\nType a message below and press Enter.")
        self._append_message("System", "New thread.")

    def action_toggle_plan(self) -> None:
        """Toggle plan sidebar visibility."""
        sidebar = self.query_one("#plan-sidebar", Static)
        self._plan_visible = not self._plan_visible
        sidebar.display = self._plan_visible
        sidebar.update("Plan sidebar" if self._plan_visible else "")

    def action_save_session(self) -> None:
        """Save current session."""
        self._append_message("System", "Session saved.")

    def update_plan(self, plan_data: dict) -> None:
        """Update the plan sidebar with current plan state."""
        sidebar = self.query_one("#plan-sidebar", Static)
        steps = plan_data.get("steps", [])
        if not steps:
            sidebar.update("")
            return

        lines = [f"[bold]{plan_data.get('title', 'Plan')}[/bold]\n"]
        icons = {"pending": "○", "in_progress": "●", "completed": "✓", "skipped": "—"}
        for step in steps:
            icon = icons.get(step.get("status", "pending"), "?")
            desc = step.get("description", "")
            status = step.get("status", "pending")
            if status == "in_progress":
                lines.append(f"[bold blue]{icon} {desc}[/bold blue]")
            elif status == "completed":
                lines.append(f"[green]{icon} {desc}[/green]")
            elif status == "skipped":
                lines.append(f"[dim]{icon} {desc}[/dim]")
            else:
                lines.append(f"{icon} {desc}")
        sidebar.update("\n".join(lines))

    def show_diff(self, filepath: str, old: str, new: str) -> None:
        """Show an inline diff in the chat area."""
        import difflib
        chat = self.query_one("#chat", Static)
        current = str(chat.renderable or "")

        diff = list(difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{filepath}",
            tofile=f"b/{filepath}",
            lineterm="",
        ))

        formatted: list[str] = []
        for line in diff:
            if line.startswith("@@"):
                formatted.append(f"[cyan]{line}[/cyan]")
            elif line.startswith("+"):
                formatted.append(f"[green]{line}[/green]")
            elif line.startswith("-"):
                formatted.append(f"[red]{line}[/red]")
            else:
                formatted.append(line)

        chat.update(
            f"{current}\n\n[bold]Diff: {filepath}[/bold]\n"
            + "\n".join(formatted)
        )

    def _append_message(self, sender: str, content: str) -> None:
        """Append a message to the chat display."""
        chat = self.query_one("#chat", Static)
        current = chat.renderable or ""
        chat.update(f"{current}\n\n[{sender}]: {content}")

    def _process_message(self, content: str) -> None:
        """Process a message through the connected AgentLoop."""
        import asyncio

        async def _run() -> None:
            try:
                response = await self._agent_loop.process_direct(  # type: ignore[union-attr]
                    content=content,
                    session_key="tui:default",
                    channel="tui",
                )
                self._append_message("MiQi", response or "(no response)")
            except Exception as e:
                self._append_message("MiQi", f"Error: {e}")

        asyncio.create_task(_run())
