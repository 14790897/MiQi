"""KUN runtime — desktop workbench execution engine for MiQi.

Replaces the native ``miqi.agent.loop.AgentLoop`` message-bus loop with a
Thread → Turn → TurnItem → RuntimeEvent pipeline designed for GUI rendering,
live streaming, and long-task robustness.

The module is built in phases:
  Phase 1 — contracts (this file imports them)
  Phase 2 — event_bus, sse, event_recorder
  Phase 3 — stores, usage
  Phase 4 — thread_service, turn_service, cancellation, migration_adapter
  Phase 5 — model_client
  Phase 6 — tool_host
  Phase 7 — approval_gate, user_input_gate
  Phase 8 — loop, compactor, history_repair, token_economy, tool_storm_breaker
  Phase 9 — router, runtime (HTTP + SSE)
  Phase 10 — CLI/gateway integration
  Phase 11 — legacy loop retirement
"""
