"""trace 统计：忙碌/占用率/重叠率的确定性计算（设计 11.1）。

- busy(c,p) = length(union(事件区间 ∩ W))，避免重叠事件重复计时。
- util(c,p) = busy / length(W)。
- overlap(p,q) = length(union(p) ∩ union(q) ∩ W) / length(W)。

不能把 partial 采样宣称为完整成功；时间单位显式保留，不默认微秒。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class IntervalEvent:
    core: str
    pipeline: str
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"事件区间非法：end({self.end}) < start({self.start})")


def _union_length(intervals: Iterable[tuple[float, float]]) -> float:
    """求一组区间并集的长度（按单位，不做跨核时钟校准）。"""
    merged: list[tuple[float, float]] = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return sum(e - s for s, e in merged)


def _clip(ev: IntervalEvent, ws: float, we: float) -> tuple[float, float] | None:
    s = max(ev.start, ws)
    e = min(ev.end, we)
    if e <= s:
        return None
    return (s, e)


@dataclass
class PipelineMetrics:
    core: str
    pipeline: str
    busy: float
    window_length: float
    util: float


@dataclass
class OverlapMetrics:
    core: str
    pipeline_a: str
    pipeline_b: str
    overlap: float
    window_length: float
    ratio: float


@dataclass
class TraceMetrics:
    window_start: float
    window_end: float
    unit: str
    per_pipeline: list[PipelineMetrics] = field(default_factory=list)
    overlaps: list[OverlapMetrics] = field(default_factory=list)
    completeness: str = "unknown"

    @property
    def window_length(self) -> float:
        return max(0.0, self.window_end - self.window_start)


def compute_trace_metrics(
    events: Iterable[IntervalEvent],
    window_start: float,
    window_end: float,
    unit: str,
    completeness: str = "unknown",
) -> TraceMetrics:
    events = list(events)
    wl = max(0.0, window_end - window_start)
    metrics = TraceMetrics(window_start, window_end, unit, completeness=completeness)

    by_pipeline: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for ev in events:
        clipped = _clip(ev, window_start, window_end)
        if clipped:
            by_pipeline.setdefault((ev.core, ev.pipeline), []).append(clipped)

    for (core, pipe), intervals in sorted(by_pipeline.items()):
        busy = _union_length(intervals)
        metrics.per_pipeline.append(
            PipelineMetrics(core, pipe, busy, wl, busy / wl if wl else 0.0)
        )

    pipelines = sorted({(e.core, e.pipeline) for e in events})
    for i in range(len(pipelines)):
        for j in range(i + 1, len(pipelines)):
            a, b = pipelines[i], pipelines[j]
            if a[0] != b[0]:
                continue  # 跨核时钟未校准时不算全局交集
            ia = by_pipeline.get(a, [])
            ib = by_pipeline.get(b, [])
            inter = _union_length(ia) + _union_length(ib) - _union_length(ia + ib)
            metrics.overlaps.append(
                OverlapMetrics(a[0], a[1], b[1], inter, wl, inter / wl if wl else 0.0)
            )
    return metrics