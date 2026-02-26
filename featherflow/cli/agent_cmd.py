"""Agent command registration for FeatherFlow CLI."""

from __future__ import annotations

import asyncio
import os
import signal
from contextlib import nullcontext

import typer


def register_agent_command(
    app: typer.Typer,
    *,
    console,
    logo: str,
    make_provider,
    print_agent_response,
    init_prompt_session,
    flush_pending_tty_input,
    read_interactive_input_async,
    is_exit_command,
    restore_terminal,
) -> None:
    """Register agent command on the root app."""

    @app.command()
    def agent(
        message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
        session_id: str = typer.Option("cli:default", "--session", "-s", help="Session ID"),
        markdown: bool = typer.Option(
            True, "--markdown/--no-markdown", help="Render assistant output as Markdown"
        ),
        logs: bool = typer.Option(
            False, "--logs/--no-logs", help="Show runtime logs during chat"
        ),
    ):
        """Interact with the agent directly."""
        from loguru import logger

        from featherflow.agent.loop import AgentLoop
        from featherflow.bus.queue import MessageBus
        from featherflow.config.loader import get_data_dir, load_config
        from featherflow.cron.service import CronService

        config = load_config()

        bus = MessageBus()
        provider = make_provider(config)

        cron_store_path = get_data_dir() / "cron" / "jobs.json"
        cron = CronService(cron_store_path)

        if logs:
            logger.enable("featherflow")
        else:
            logger.disable("featherflow")

        agent_loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=config.workspace_path,
            agent_name=config.agents.defaults.name,
            model=config.agents.defaults.model,
            temperature=config.agents.defaults.temperature,
            max_tokens=config.agents.defaults.max_tokens,
            max_iterations=config.agents.defaults.max_tool_iterations,
            reflect_after_tool_calls=config.agents.defaults.reflect_after_tool_calls,
            web_config=config.tools.web,
            paper_config=config.tools.papers,
            memory_window=config.agents.defaults.memory_window,
            exec_config=config.tools.exec,
            memory_config=config.agents.memory,
            self_improvement_config=config.agents.self_improvement,
            session_config=config.agents.sessions,
            cron_service=cron,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            mcp_servers=config.tools.mcp_servers,
            channels_config=config.channels,
        )

        def _thinking_ctx():
            if logs:
                return nullcontext()
            return console.status("[dim]featherflow is thinking...[/dim]", spinner="dots")

        async def _cli_progress(content: str, *, tool_hint: bool = False) -> None:
            ch = agent_loop.channels_config
            if ch and tool_hint and not ch.send_tool_hints:
                return
            if ch and not tool_hint and not ch.send_progress:
                return
            console.print(f"  [dim]↳ {content}[/dim]")

        if message:
            async def run_once():
                with _thinking_ctx():
                    response = await agent_loop.process_direct(message, session_id, on_progress=_cli_progress)
                print_agent_response(response, render_markdown=markdown)
                await agent_loop.close_mcp()

            asyncio.run(run_once())
        else:
            from featherflow.bus.events import InboundMessage

            init_prompt_session()
            console.print(
                f"{logo} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n"
            )

            if ":" in session_id:
                cli_channel, cli_chat_id = session_id.split(":", 1)
            else:
                cli_channel, cli_chat_id = "cli", session_id

            def _exit_on_sigint(signum, frame):
                agent_loop.stop()
                restore_terminal()
                console.print("\nGoodbye!")
                os._exit(0)

            signal.signal(signal.SIGINT, _exit_on_sigint)

            async def run_interactive():
                bus_task = asyncio.create_task(agent_loop.run())
                turn_done = asyncio.Event()
                turn_done.set()
                turn_response: list[str] = []

                async def _consume_outbound():
                    while True:
                        try:
                            msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                            if msg.metadata.get("_progress"):
                                is_tool_hint = msg.metadata.get("_tool_hint", False)
                                ch = agent_loop.channels_config
                                if ch and is_tool_hint and not ch.send_tool_hints:
                                    pass
                                elif ch and not is_tool_hint and not ch.send_progress:
                                    pass
                                else:
                                    console.print(f"  [dim]↳ {msg.content}[/dim]")
                            elif not turn_done.is_set():
                                if msg.content:
                                    turn_response.append(msg.content)
                                turn_done.set()
                            elif msg.content:
                                console.print()
                                print_agent_response(msg.content, render_markdown=markdown)
                        except asyncio.TimeoutError:
                            continue
                        except asyncio.CancelledError:
                            break

                outbound_task = asyncio.create_task(_consume_outbound())

                try:
                    while True:
                        try:
                            flush_pending_tty_input()
                            user_input = await read_interactive_input_async()
                            command = user_input.strip()
                            if not command:
                                continue

                            if is_exit_command(command):
                                restore_terminal()
                                console.print("\nGoodbye!")
                                break

                            turn_done.clear()
                            turn_response.clear()

                            await bus.publish_inbound(InboundMessage(
                                channel=cli_channel,
                                sender_id="user",
                                chat_id=cli_chat_id,
                                content=user_input,
                            ))

                            with _thinking_ctx():
                                await turn_done.wait()

                            if turn_response:
                                print_agent_response(turn_response[0], render_markdown=markdown)
                        except KeyboardInterrupt:
                            restore_terminal()
                            console.print("\nGoodbye!")
                            break
                        except EOFError:
                            restore_terminal()
                            console.print("\nGoodbye!")
                            break
                finally:
                    agent_loop.stop()
                    outbound_task.cancel()
                    await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
                    await agent_loop.close_mcp()

            asyncio.run(run_interactive())
