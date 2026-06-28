"""Abstract base class for all orchestrator agents."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """All agents share a common interface: execute() takes a context dict
    and returns an updated context dict with the agent's output merged in."""

    name: str = "base"

    @abstractmethod
    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Run the agent and return the updated context."""
        ...
