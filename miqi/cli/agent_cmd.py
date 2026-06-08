"""Agent command registration for MiQi CLI."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
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
            True, "--logs/--no-logs", help="Show runtime logs during chat"
        ),
    ):
        """Interact with the agent directly."""
        from loguru import logger

        from miqi.agent.loop import AgentLoop
        from miqi.bus.queue import MessageBus
        from miqi.config.loader import get_data_dir, load_config
        from miqi.cron.service import CronService

        # Configure loguru: enable miqi namespace and set level
        logger.enable("miqi")
        if not logs:
            # When --no-logs, suppress loguru output but don't fully disable
            # (errors and warnings should still be visible)
            logger.remove()
            logger.add(
                sys.stderr,
                format="<level>[miqi] {name}:{function}:{line} | {message}</level>",
                level="WARNING",
                colorize=True,
            )

        config = load_config()
        runtime_choice = config.agents.defaults.runtime

        bus = MessageBus()
        provider = make_provider(config)

        cron_store_path = get_data_dir() / "cron" / "jobs.json"
        cron = CronService(cron_store_path, job_timeout=config.cron.job_timeout_seconds)

        if logs:
            logger.enable("miqi")
        else:
            logger.disable("miqi")

        if runtime_choice == "kun":
            from miqi.agent.tools.registry import ToolRegistry
            from miqi.kun_runtime.migration_adapter import GatewayKunRuntime

            _workspace_path = config.workspace_path
            _allowed_dir = _workspace_path if config.tools.restrict_to_workspace else None
            from miqi.agent.tools.cron import CronTool
            from miqi.agent.tools.filesystem import (
                EditFileTool,
                ListDirTool,
                ReadFileTool,
                WriteFileTool,
            )
            from miqi.agent.tools.message import MessageTool
            from miqi.agent.tools.papers import PaperDownloadTool, PaperGetTool, PaperSearchTool
            from miqi.agent.tools.shell import ExecTool
            from miqi.agent.tools.web import WebFetchTool, WebSearchTool

            tool_registry = ToolRegistry()
            for cls in (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool):
                tool_registry.register(cls(workspace=_workspace_path, allowed_dir=_allowed_dir))
            tool_registry.register(ExecTool(
                working_dir=str(_workspace_path),
                timeout=config.tools.exec.timeout,
                restrict_to_workspace=config.tools.restrict_to_workspace,
                env_passthrough=list(config.tools.exec.env_passthrough),
            ))
            tool_registry.register(WebSearchTool(
                provider=config.tools.web.search.provider,
                api_key=config.tools.web.search.api_key or None,
                max_results=config.tools.web.search.max_results,
                ollama_api_key=config.tools.web.search.ollama_api_key or None,
                ollama_api_base=config.tools.web.search.ollama_api_base,
            ))
            tool_registry.register(WebFetchTool(
                provider=config.tools.web.fetch.provider,
                ollama_api_key=config.tools.web.fetch.ollama_api_key or None,
                ollama_api_base=config.tools.web.fetch.ollama_api_base,
            ))
            tool_registry.register(PaperSearchTool(
                provider=config.tools.papers.provider,
                semantic_scholar_api_key=config.tools.papers.semantic_scholar_api_key or None,
                timeout_seconds=config.tools.papers.timeout_seconds,
                default_limit=config.tools.papers.default_limit,
                max_limit=config.tools.papers.max_limit,
            ))
            tool_registry.register(PaperGetTool(
                provider=config.tools.papers.provider,
                semantic_scholar_api_key=config.tools.papers.semantic_scholar_api_key or None,
                timeout_seconds=config.tools.papers.timeout_seconds,
            ))
            tool_registry.register(PaperDownloadTool(
                workspace=_workspace_path,
                provider=config.tools.papers.provider,
                semantic_scholar_api_key=config.tools.papers.semantic_scholar_api_key or None,
                timeout_seconds=config.tools.papers.timeout_seconds,
            ))
            tool_registry.register(MessageTool(send_callback=bus.publish_outbound))
            tool_registry.register(CronTool(cron))

            agent_loop = GatewayKunRuntime(
                data_dir=get_data_dir() / "kun_runtime",
                workspace=config.workspace_path,
                provider=provider,
                tool_registry=tool_registry,
                model=config.agents.defaults.model,
                agent_name=config.agents.defaults.name,
                mcp_servers=config.tools.mcp_servers,
            )
        else:
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
                max_tool_result_chars=config.agents.defaults.max_tool_result_chars,
                context_limit_chars=config.agents.defaults.context_limit_chars,
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
            return console.status("[dim]miqi is thinking...[/dim]", spinner="dots")

        async def _cli_progress(content: str, *, tool_hint: bool = False) -> None:
            ch = agent_loop.channels_config
            if ch and tool_hint and not ch.send_tool_hints:
                return
            if ch and not tool_hint and not ch.send_progress:
                return
            console.print(f"  [dim]↳ {content}[/dim]")

        async def on_cron_job(job) -> str | None:
            from miqi.bus.events import OutboundMessage
            response = await agent_loop.process_direct(
                job.payload.message,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
            if job.payload.deliver and job.payload.to:
                await bus.publish_outbound(
                    OutboundMessage(
                        channel=job.payload.channel or "cli",
                        chat_id=job.payload.to,
                        content=response or "",
                    )
                )
            return response

        cron.on_job = on_cron_job

        if message:
            async def run_once():
                with _thinking_ctx():
                    response = await agent_loop.process_direct(message, session_id, on_progress=_cli_progress)
                print_agent_response(response, render_markdown=markdown)
                await agent_loop.close_mcp()

            asyncio.run(run_once())
        else:
            from miqi.bus.events import InboundMessage

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
                await cron.start()
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
