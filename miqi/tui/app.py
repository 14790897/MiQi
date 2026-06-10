"""MiQi TUI — Textual-based terminal interface."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static
from textual.containers import Horizontal, Vertical


class MiQiTui(App):
    """MiQi Terminal User Interface."""

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

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Vertical(Static(id="chat"), id="chat-container")
            yield Vertical(Static(id="plan-sidebar"), id="plan-container")
        yield Input(placeholder="Type a message...", id="input")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Send message to MiQi runtime when user presses Enter."""
        chat = self.query_one("#chat", Static)
        current = chat.renderable or ""
        chat.update(f"{current}\n\nYou: {event.value}")
        event.input.value = ""

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.query_one("#chat", Static).update(
            "Welcome to MiQi TUI!\n"
            "Type a message below and press Enter.\n"
            "Ctrl+C to abort, Ctrl+N for new thread."
        )
