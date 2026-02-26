"""Onboarding command registration for FeatherFlow CLI."""

from __future__ import annotations

import sys
from typing import Callable

import typer


def register_onboard_command(
    app: typer.Typer,
    *,
    console,
    logo: str,
    normalize_agent_name: Callable[[str], str],
    interactive_onboard_setup: Callable,
    create_workspace_templates: Callable,
) -> None:
    """Register onboard command on the root app."""

    @app.command()
    def onboard():
        """Initialize FeatherFlow configuration and workspace."""
        from featherflow.config.loader import get_config_path, load_config, save_config
        from featherflow.config.schema import Config
        from featherflow.utils.helpers import get_workspace_path

        config_path = get_config_path()
        interactive_onboard = bool(sys.stdin.isatty() and sys.stdout.isatty())

        agent_name = "featherflow"
        soul_preset = "balanced"

        if config_path.exists():
            console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
            console.print("  [bold]y[/bold] = overwrite with defaults (existing values will be lost)")
            console.print("  [bold]N[/bold] = refresh config, keeping existing values and adding new fields")
            if typer.confirm("Overwrite?"):
                config = Config()
                if interactive_onboard:
                    agent_name, soul_preset = interactive_onboard_setup(config)
                else:
                    agent_name = normalize_agent_name(config.agents.defaults.name)
                save_config(config)
                console.print(f"[green]✓[/green] Config reset to defaults at {config_path}")
            else:
                config = load_config()
                save_config(config)
                agent_name = normalize_agent_name(getattr(config.agents.defaults, "name", "featherflow"))
                console.print(f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)")
        else:
            config = Config()
            if interactive_onboard:
                agent_name, soul_preset = interactive_onboard_setup(config)
            else:
                agent_name = normalize_agent_name(config.agents.defaults.name)
            save_config(config)
            console.print(f"[green]✓[/green] Created config at {config_path}")

        workspace = get_workspace_path()
        created_workspace = not workspace.exists()
        workspace.mkdir(parents=True, exist_ok=True)

        if created_workspace:
            console.print(f"[green]✓[/green] Created workspace at {workspace}")

        create_workspace_templates(
            workspace,
            agent_name=agent_name,
            soul_preset=soul_preset,
        )

        console.print(f"\n{logo} featherflow is ready!")
        provider_name = config.get_provider_name(config.agents.defaults.model)
        console.print(f"  Name: [cyan]{config.agents.defaults.name}[/cyan]")
        if provider_name:
            console.print(f"  Provider: [cyan]{provider_name}[/cyan]")
        console.print(f"  Model: [cyan]{config.agents.defaults.model}[/cyan]")
        if config.tools.web.search.api_key:
            console.print("  Web search: [green]Brave enabled[/green]")
        else:
            console.print(
                "  Web search: [yellow]Brave disabled[/yellow] (model-native search may still work)"
            )

        console.print("\nNext steps:")
        console.print('  1. Chat: [cyan]featherflow agent -m "Hello!"[/cyan]')
        console.print("  2. Start gateway: [cyan]featherflow gateway[/cyan]")
        console.print(
            "\n[dim]Want chat app setup? See repository docs: Chat Apps section[/dim]"
        )
