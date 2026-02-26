"""Gateway command registration for FeatherFlow CLI."""

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
        """Start the FeatherFlow gateway."""
        from featherflow.agent.loop import AgentLoop
        from featherflow.bus.queue import MessageBus
        from featherflow.channels.manager import ChannelManager
        from featherflow.config.loader import get_data_dir, load_config
        from featherflow.cron.service import CronService
        from featherflow.cron.types import CronJob
        from featherflow.heartbeat.service import HeartbeatService
        from featherflow.session.manager import SessionManager

        if verbose:
            import logging

            logging.basicConfig(level=logging.DEBUG)

        console.print(f"{logo} Starting FeatherFlow gateway on port {port}...")

        config = load_config()
        bus = MessageBus()
        provider = make_provider(config)
        session_manager = SessionManager(
            config.workspace_path,
            compact_threshold_messages=config.agents.sessions.compact_threshold_messages,
            compact_threshold_bytes=config.agents.sessions.compact_threshold_bytes,
            compact_keep_messages=config.agents.sessions.compact_keep_messages,
        )

        cron_store_path = get_data_dir() / "cron" / "jobs.json"
        cron = CronService(cron_store_path)

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
                from featherflow.bus.events import OutboundMessage

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
            from featherflow.bus.events import OutboundMessage

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

        cron_status = cron.status()
        if cron_status["jobs"] > 0:
            console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

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
