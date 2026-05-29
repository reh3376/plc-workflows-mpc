"""Detect step changes in an input signal.

Slices a continuous operating-data trace into step-test windows that the
identifier can fit against. Lightweight (no sklearn): uses a robust threshold
on |Δu| and collapses adjacent edges into a single event.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class StepEvent:
    """A detected step change in the input signal.

    Attributes:
        start_index: index just before the edge (last pre-step sample).
        settled_index: index used as the end of the step-test window.
        initial_value: mean input value just before the edge.
        final_value: mean input value just after the edge has settled.
    """

    start_index: int
    settled_index: int
    initial_value: float
    final_value: float

    @property
    def magnitude(self) -> float:
        return self.final_value - self.initial_value


def detect_steps(
    u: np.ndarray,
    *,
    threshold: float | None = None,
    min_separation: int = 1,
    settle_samples: int = 0,
) -> list[StepEvent]:
    """Find step changes in ``u``.

    A step is detected where ``|Δu|`` exceeds ``threshold``. If ``threshold``
    is ``None``, a robust noise-floor estimate (99th percentile of |Δu|) is
    used so quiescent noise is ignored. ``min_separation`` collapses edges
    within N samples into one event; ``settle_samples`` extends the window
    after the edge before reporting the settled index.
    """
    arr = np.asarray(u, dtype=float).ravel()
    if arr.size < 2:
        return []

    du = np.diff(arr)
    abs_du = np.abs(du)
    if threshold is None:
        threshold = max(float(np.quantile(abs_du, 0.99)), 1e-9)

    edges = np.nonzero(abs_du > threshold)[0]
    if edges.size == 0:
        return []

    events: list[StepEvent] = []
    cluster_start = int(edges[0])
    cluster_end = int(edges[0])
    for idx in edges[1:]:
        i = int(idx)
        if i - cluster_end <= min_separation:
            cluster_end = i
        else:
            events.append(_make_event(arr, cluster_start, cluster_end, settle_samples))
            cluster_start = i
            cluster_end = i
    events.append(_make_event(arr, cluster_start, cluster_end, settle_samples))
    return events


def _make_event(u: np.ndarray, start: int, end: int, settle: int) -> StepEvent:
    pre_lo = max(0, start - 5)
    initial = float(np.mean(u[pre_lo : start + 1])) if start > pre_lo else float(u[start])
    settled_index = min(u.size - 1, end + 1 + settle)
    post_lo = max(end + 1, settled_index - 4)
    final = float(np.mean(u[post_lo : settled_index + 1]))
    return StepEvent(
        start_index=int(start),
        settled_index=int(settled_index),
        initial_value=initial,
        final_value=final,
    )


__all__ = ["StepEvent", "detect_steps"]
