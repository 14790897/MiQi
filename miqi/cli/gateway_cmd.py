"""Gateway command registration for MiQi CLI."""

from __future__ import annotations

import asyncio

import typer


def register_gateway_command(
    app: typer.Typer,
    *,
    console,
    logo: str,
    make_provider,
) -> None:
    """Register gateway command on the root app."""

    @app.command()
    def gateway(
        port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    ):
        """Start the MiQi gateway."""
        from loguru import logger

        from miqi.agent.loop import AgentLoop
        from miqi.bus.queue import MessageBus
        from miqi.channels.manager import ChannelManager
        from miqi.config.loader import get_data_dir, load_config
        from miqi.cron.service import CronService
        from miqi.cron.types import CronJob
        from miqi.heartbeat.service import HeartbeatService
        from miqi.session.manager import SessionManager

        # Configure loguru for gateway mode
        logger.enable("miqi")
        logger.remove()
        import sys
        if verbose:
            logger.add(
                sys.stderr,
                format="<level>[miqi-gateway] {name}:{function}:{line} | {message}</level>",
                level="DEBUG",
                colorize=True,
            )
        else:
            logger.add(
                sys.stderr,
                format="<level>[miqi-gateway] {name}:{function}:{line} | {message}</level>",
                level="INFO",
                colorize=True,
            )

        console.print(f"{logo} Starting MiQi gateway on port {port}...")

        config = load_config()
        runtime_choice = config.agents.defaults.runtime

        bus = MessageBus()
        provider = make_provider(config)
        session_manager = SessionManager(
            config.workspace_path,
            compact_threshold_messages=config.agents.sessions.compact_threshold_messages,
            compact_threshold_bytes=config.agents.sessions.compact_threshold_bytes,
            compact_keep_messages=config.agents.sessions.compact_keep_messages,
        )

        cron_store_path = get_data_dir() / "cron" / "jobs.json"
        cron = CronService(cron_store_path, job_timeout=config.cron.job_timeout_seconds)

        if runtime_choice == "kun":
            from miqi.agent.tools.registry import ToolRegistry
            from miqi.kun_runtime.migration_adapter import GatewayKunRuntime

            # Build a full ToolRegistry (mirrors AgentLoop._register_default_tools)
            tool_registry = ToolRegistry()
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

            agent = GatewayKunRuntime(
                data_dir=get_data_dir() / "kun_runtime",
                workspace=config.workspace_path,
                provider=provider,
                tool_registry=tool_registry,
                model=config.agents.defaults.model,
                agent_name=config.agents.defaults.name,
                mcp_servers=config.tools.mcp_servers,
            )
            console.print("[green]✓[/green] Runtime: KUN (desktop-workbench engine)")
        else:
            agent = AgentLoop(
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
                session_manager=session_manager,
                mcp_servers=config.tools.mcp_servers,
                channels_config=config.channels,
            )

        async def on_cron_job(job: CronJob) -> str | None:
            response = await agent.process_direct(
                job.payload.message,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
            if job.payload.deliver and job.payload.to:
                from miqi.bus.events import OutboundMessage

                await bus.publish_outbound(
                    OutboundMessage(
                        channel=job.payload.channel or "cli",
                        chat_id=job.payload.to,
                        content=response or "",
                    )
                )
            return response

        cron.on_job = on_cron_job

        channels = ChannelManager(config, bus)

        def _pick_heartbeat_target() -> tuple[str, str]:
            enabled = set(channels.enabled_channels)
            for item in session_manager.list_sessions():
                key = item.get("key") or ""
                if ":" not in key:
                    continue
                channel, chat_id = key.split(":", 1)
                if channel in {"cli", "system"}:
                    continue
                if channel in enabled and chat_id:
                    return channel, chat_id
            return "cli", "direct"

        async def on_heartbeat(prompt: str) -> str:
            channel, chat_id = _pick_heartbeat_target()

            async def _silent(*_args, **_kwargs):
                pass

            return await agent.process_direct(
                prompt,
                session_key="heartbeat",
                channel=channel,
                chat_id=chat_id,
                on_progress=_silent,
            )

        async def on_heartbeat_notify(response: str) -> None:
            from miqi.bus.events import OutboundMessage

            channel, chat_id = _pick_heartbeat_target()
            if channel == "cli":
                return
            await bus.publish_outbound(
                OutboundMessage(channel=channel, chat_id=chat_id, content=response)
            )

        heartbeat_interval_s = max(1, config.heartbeat.interval_seconds)
        heartbeat = HeartbeatService(
            workspace=config.workspace_path,
            on_heartbeat=on_heartbeat,
            on_notify=on_heartbeat_notify,
            interval_s=heartbeat_interval_s,
            enabled=config.heartbeat.enabled,
        )

        if channels.enabled_channels:
            console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
        else:
            console.print("[yellow]Warning: No channels enabled[/yellow]")

        if config.heartbeat.enabled:
            if heartbeat_interval_s % 60 == 0:
                console.print(
                    f"[green]✓[/green] Heartbeat: every {heartbeat_interval_s // 60}m"
                )
            else:
                console.print(f"[green]✓[/green] Heartbeat: every {heartbeat_interval_s}s")
        else:
            console.print("[yellow]Heartbeat disabled[/yellow]")

        async def run():
            try:
                await cron.start()

                cron_status = cron.status()
                if cron_status["jobs"] > 0:
                    console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

                await heartbeat.start()
                await asyncio.gather(
                    agent.run(),
                    channels.start_all(),
                )
            except KeyboardInterrupt:
                console.print("\nShutting down...")
            finally:
                await agent.close_mcp()
                heartbeat.stop()
                cron.stop()
                agent.stop()
                await channels.stop_all()

        asyncio.run(run())
