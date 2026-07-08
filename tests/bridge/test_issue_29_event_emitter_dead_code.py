"""Regression coverage for issue #29 dead bridge EventEmitter code."""

from pathlib import Path


def test_bridge_event_emitter_adapter_is_removed():
    """Runtime events should be routed by runtime.services, not bridge dead code."""
    miqi_dir = Path(__file__).parent.parent.parent / "miqi"

    assert not (miqi_dir / "bridge" / "event_emitter.py").exists()


def test_bridge_state_does_not_expose_dead_event_emitter_pointer():
    from miqi.bridge.server import _state

    assert not hasattr(_state, "_event_emitter")
