"""报告生成（设计 6：report.md 不是恢复依据，只展示结构化事实）。"""
from __future__ import annotations

from pathlib import Path

from .state import State


def render_report(state: State) -> str:
    lines = ["# Closure 实验报告", ""]
    lines.append(f"- case_id: `{state.case_id}`")
    lines.append(f"- run_status: `{state.run_status}`" + (f"（原因：{state.stop_reason}）" if state.stop_reason else ""))
    lines.append(f"- baseline: `{state.baseline_variant_id}`")
    lines.append(f"- incumbent: `{state.incumbent_id}`")
    lines.append("")

    lines.append("## 阶段状态")
    lines.append("")
    lines.append("| stage | status |")
    lines.append("|---|---|")
    for stage, status in sorted(state.stages.items()):
        lines.append(f"| {stage} | {status} |")
    lines.append("")

    lines.append("## 候选")
    lines.append("")
    lines.append("| candidate | 状态 | 基线 | 目标/基线比率 |")
    lines.append("|---|---|---|---|")
    for cid, c in sorted(state.candidates.items()):
        ratio = (c.get("objective") or {}).get("latency_ratio_to_baseline")
        ratio_s = f"{ratio:.3f}" if isinstance(ratio, (int, float)) else "-"
        lines.append(f"| {cid} | {c.get('status')} | {c.get('baseline_variant')} | {ratio_s} |")
    lines.append("")

    lines.append("## 预算")
    lines.append("")
    lines.append("| 项 | 已用 | 上限 |")
    lines.append("|---|---|---|")
    for k, limit in sorted((state.budget_limited or {}).items()):
        key = k.replace("max_", "")
        lines.append(f"| {k} | {state.budget_used.get(key, 0)} | {limit} |")
    lines.append("")

    if state.environment:
        lines.append("## 环境能力")
        lines.append("")
        lines.append("```json")
        lines.append(_json(state.environment))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def _json(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)


def write_report(state: State, path: str | Path) -> None:
    Path(path).write_text(render_report(state), encoding="utf-8")