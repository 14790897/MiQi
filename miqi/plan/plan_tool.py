"""Agent tools for plan creation and management."""

from __future__ import annotations

from typing import Any

from miqi.agent.tools.base import Tool
from miqi.plan.plan_tracker import PlanTracker


class PlanCreateTool(Tool):
    """Create a plan for a multi-step task."""

    name = "plan_create"
    description = (
        "Create a step-by-step plan for a complex task. "
        "Use this when a task requires multiple steps to complete."
    )

    def __init__(self, tracker: PlanTracker):
        self._tracker = tracker

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Plan title"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "description": {"type": "string"},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": [],
                            },
                        },
                        "required": ["id", "description"],
                    },
                },
            },
            "required": ["title", "steps"],
        }

    async def execute(self, **kwargs: Any) -> str:
        title = kwargs["title"]
        steps = kwargs["steps"]
        plan = self._tracker.create(title, steps)
        step_list = "\n".join(
            f"  {s['id']}: [{s.get('status', 'pending')}] {s['description']}"
            for s in steps
        )
        return f"Plan created: {plan.plan_id}\n{step_list}"


class PlanUpdateTool(Tool):
    """Update a plan step's status."""

    name = "plan_update"
    description = "Update the status of a step in the current plan"

    def __init__(self, tracker: PlanTracker):
        self._tracker = tracker

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "step_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "skipped"],
                },
            },
            "required": ["plan_id", "step_id", "status"],
        }

    async def execute(self, **kwargs: Any) -> str:
        plan_id = kwargs["plan_id"]
        step_id = kwargs["step_id"]
        status = kwargs["status"]
        step = self._tracker.update_step(plan_id, step_id, status)
        if step is None:
            return f"Error: plan {plan_id} or step {step_id} not found"
        return f"Step '{step.description}' → {status}"
