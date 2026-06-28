"""
Lightweight timing utilities for latency measurement.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator


@dataclass
class Timer:
    """Accumulate named durations across multiple steps."""

    _data: dict[str, float] = field(default_factory=dict, init=False)

    def record(self, name: str, elapsed_ms: float) -> None:
        self._data[name] = round(elapsed_ms, 2)

    def get(self, name: str) -> float:
        return self._data.get(name, 0.0)

    def total_ms(self) -> float:
        return round(sum(self._data.values()), 2)

    def to_dict(self) -> dict[str, float]:
        return dict(self._data)


@contextmanager
def timed(timer: Timer, name: str) -> Generator[None, None, None]:
    """Context manager that records elapsed time into a Timer instance.

    Example::

        t = Timer()
        with timed(t, "embed"):
            vectors = embedder.embed(texts)
        print(t.get("embed"))  # ms elapsed
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        timer.record(name, elapsed)


def now_ms() -> float:
    """Current time in milliseconds (monotonic)."""
    return time.perf_counter() * 1000
