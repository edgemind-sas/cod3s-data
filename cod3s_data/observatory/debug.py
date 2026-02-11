"""Debug Controller for Observatory - state machine and breakpoint evaluation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cod3s_data.observatory.expression_parser import evaluate_expression, validate_expression


class DebugState(Enum):
    """Debug mode states."""

    INACTIVE = "inactive"
    RUNNING = "running"
    PAUSED = "paused"
    STEPPING = "stepping"


class DebugGranularity(Enum):
    """Step granularity levels."""

    MESSAGE = "message"
    STAGE = "stage"
    BREAKPOINT = "breakpoint"


@dataclass
class Breakpoint:
    """A debug breakpoint."""

    id: str
    channel_pattern: str
    condition: str | None = None
    component_id: str | None = None
    enabled: bool = True
    hit_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel_pattern": self.channel_pattern,
            "condition": self.condition,
            "component_id": self.component_id,
            "enabled": self.enabled,
            "hit_count": self.hit_count,
        }


class BreakpointEvaluator:
    """Evaluates breakpoints against messages using safe expression parsing."""

    def __init__(self) -> None:
        self._breakpoints: dict[str, Breakpoint] = {}

    @property
    def has_breakpoints(self) -> bool:
        return any(bp.enabled for bp in self._breakpoints.values())

    def add(
        self,
        breakpoint_id: str,
        channel_pattern: str,
        condition: str | None = None,
        component_id: str | None = None,
    ) -> None:
        """Add a breakpoint. Validates condition at creation time."""
        if condition is not None:
            validate_expression(condition)

        self._breakpoints[breakpoint_id] = Breakpoint(
            id=breakpoint_id,
            channel_pattern=channel_pattern,
            condition=condition,
            component_id=component_id,
        )

    def remove(self, breakpoint_id: str) -> None:
        if breakpoint_id not in self._breakpoints:
            raise KeyError(f"Breakpoint '{breakpoint_id}' not found")
        del self._breakpoints[breakpoint_id]

    def toggle(self, breakpoint_id: str, enabled: bool) -> None:
        if breakpoint_id not in self._breakpoints:
            raise KeyError(f"Breakpoint '{breakpoint_id}' not found")
        self._breakpoints[breakpoint_id].enabled = enabled

    def list_all(self) -> list[dict[str, Any]]:
        return [bp.to_dict() for bp in self._breakpoints.values()]

    def evaluate(
        self,
        channel: str,
        message: Any,
        component_id: str | None = None,
    ) -> Breakpoint | None:
        """Evaluate all breakpoints against a message.

        Returns the first matching Breakpoint, or None.
        """
        for bp in self._breakpoints.values():
            if not bp.enabled:
                continue

            # Check channel pattern (simple glob: * matches any segment)
            if not self._match_channel(bp.channel_pattern, channel):
                continue

            # Check component (if specified)
            if bp.component_id is not None and bp.component_id != component_id:
                continue

            # Check condition (if specified)
            if bp.condition is not None:
                context = self._build_context(channel, message)
                try:
                    if not evaluate_expression(bp.condition, context):
                        continue
                except Exception:
                    continue  # Invalid condition doesn't match

            # Match found
            bp.hit_count += 1
            return bp

        return None

    @staticmethod
    def _match_channel(pattern: str, channel: str) -> bool:
        """Simple channel pattern matching supporting * wildcards."""
        if pattern == "*":
            return True
        if "*" not in pattern:
            return pattern == channel

        # Convert glob-style pattern to simple matching
        parts = pattern.split("*")
        if len(parts) == 2:
            prefix, suffix = parts
            return channel.startswith(prefix) and channel.endswith(suffix)

        # Fallback: exact match
        return pattern == channel

    @staticmethod
    def _build_context(channel: str, message: Any) -> dict[str, Any]:
        """Build evaluation context from a message."""
        context: dict[str, Any] = {
            "channel": channel,
            "value": getattr(message, "value", None),
            "key": getattr(message, "key", None),
        }
        tags = getattr(message, "tags", None)
        if tags and isinstance(tags, dict):
            for k, v in tags.items():
                context[f"tags.{k}"] = v
        return context


class DebugController:
    """Manages debug state machine and synchronization.

    Uses asyncio.Event for pause/step coordination.
    """

    def __init__(self, enabled: bool = False) -> None:
        self._state: DebugState = DebugState.RUNNING if enabled else DebugState.INACTIVE
        self._granularity: DebugGranularity = DebugGranularity.MESSAGE
        self._breakpoint_evaluator = BreakpointEvaluator()
        self._step_count: int = 0
        self._enabled = enabled

        # Synchronization
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._step_completed = asyncio.Event()

        # Slow-motion
        self._slow_motion: bool = False
        self._slow_motion_delay_ms: int = 500

        # Last step result
        self._last_step_result: dict[str, Any] = {}

    @property
    def is_active(self) -> bool:
        return self._state != DebugState.INACTIVE

    @property
    def state(self) -> DebugState:
        return self._state

    @property
    def granularity(self) -> DebugGranularity:
        return self._granularity

    @property
    def breakpoint_evaluator(self) -> BreakpointEvaluator:
        return self._breakpoint_evaluator

    async def pause(self) -> None:
        """Transition to PAUSED state."""
        if self._state == DebugState.INACTIVE:
            self._state = DebugState.RUNNING
        self._state = DebugState.PAUSED
        self._pause_event.clear()

    async def resume(self) -> None:
        """Transition to RUNNING state."""
        self._state = DebugState.RUNNING
        self._pause_event.set()

    async def step(self, granularity: str | None = None) -> dict[str, Any]:
        """Execute one step at the specified granularity."""
        if granularity:
            self._granularity = DebugGranularity(granularity)
        self._state = DebugState.STEPPING
        self._step_completed.clear()

        # Temporarily allow execution
        self._pause_event.set()

        # Wait for step to complete
        await self._step_completed.wait()

        # Re-pause
        self._state = DebugState.PAUSED
        self._pause_event.clear()
        self._step_count += 1

        return self._last_step_result

    async def check_message(self, channel: str, message: Any) -> None:
        """Called on every message published. Handles breakpoints, stepping, pausing."""
        # Evaluate breakpoints (always, even during free running)
        if self._breakpoint_evaluator.has_breakpoints:
            hit = self._breakpoint_evaluator.evaluate(channel, message)
            if hit is not None:
                self._last_step_result = {
                    "type": "breakpoint_hit",
                    "breakpoint": hit.to_dict(),
                    "channel": channel,
                }
                self._state = DebugState.PAUSED
                self._pause_event.clear()
                self._step_completed.set()
                return

        # Handle stepping
        if self._state == DebugState.STEPPING:
            if self._granularity == DebugGranularity.MESSAGE:
                self._last_step_result = {
                    "type": "step_completed",
                    "channel": channel,
                }
                self._step_completed.set()
                return

        # Handle slow-motion
        if self._slow_motion and self._state == DebugState.RUNNING:
            await asyncio.sleep(self._slow_motion_delay_ms / 1000.0)

        # Handle pause
        await self._pause_event.wait()

    def set_granularity(self, granularity: str) -> None:
        self._granularity = DebugGranularity(granularity)

    def set_slow_motion(self, enabled: bool, delay_ms: int = 500) -> None:
        self._slow_motion = enabled
        self._slow_motion_delay_ms = max(100, min(5000, delay_ms))

    def get_state_dict(self) -> dict[str, Any]:
        """Return debug state as a dictionary."""
        return {
            "state": self._state.value,
            "granularity": self._granularity.value,
            "breakpoints": self._breakpoint_evaluator.list_all(),
            "slow_motion": self._slow_motion,
            "slow_motion_delay_ms": self._slow_motion_delay_ms,
            "step_count": self._step_count,
        }
