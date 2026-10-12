"""Closure 命令行入口（设计 19）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters.ascend import AscendAdapter
from .artifacts import ArtifactManifest, gc_plan
from .controller import Controller
from .executors import build_executor
from .knowledge import KnowledgeStore, build_dossier
from .migrate import export_bundle, import_bundle
from .planner import ReplayPlanner
from .report import write_report
from .schemas.enums import EventType
from .templates import CASE_TOML, HARNESS_PY, PROFILE_TOML, REFERENCE_PY


def _load_proposals(path: str | None) -> list[dict]:
    if not path:
        return []
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_init(args) -> int:
    root = Path(args.case)
    root.mkdir(parents=True, exist_ok=True)
    (root / "profiles").mkdir(parents=True, exist_ok=True)
    (root / "input").mkdir(parents=True, exist_ok=True)
    (root / "case.toml").write_text(CASE_TOML.format(case_id=args.case_id), encoding="utf-8")
    (root / "profiles" / "mac-sim.toml").write_text(PROFILE_TOML.format(name="mac-sim"), encoding="utf-8")
    (root / "input" / "reference.py").write_text(REFERENCE_PY, encoding="utf-8")
    (root / "input" / "harness.py").write_text(HARNESS_PY, encoding="utf-8")
    print(f"已初始化 case：{root}")
    print("  - case.toml / profiles/mac-sim.toml")
    print("  - input/reference.py、input/harness.py（本地数值 fixture，非 Ascend）")
    return 0


def cmd_doctor(args) -> int:
    root = Path(args.case)
    if not (root / "case.toml").exists():
        print("未找到 case.toml，先运行 `closure init --case ...`", file=sys.stderr)
        return 1
    asc = AscendAdapter()
    local = build_executor("local")
    print("== Ascend 工具链 ==\n")
    print(json.dumps(asc.probe().as_dict(), ensure_ascii=False, indent=2))
    print("\n== 本地执行能力 ==\n")
    print(json.dumps(local.probe().as_dict(), ensure_ascii=False, indent=2))
    return 0


def _run_loop(case_dir: str, proposals: list[dict], max_candidates: int | None, max_steps: int) -> int:
    controller = Controller(case_dir, planner=ReplayPlanner(proposals))
    state = controller.store.replay()
    controller.ensure_initialized(state)
    if max_candidates is not None:
        controller.store.events.append(EventType.BUDGET_ADJUSTED, {"limits": {"max_candidates": max_candidates}})
        controller.store.write_snapshot(controller.store.replay())

    for _ in range(max_steps):
        r = controller.run_step()
        if r.status in ("stopped", "done"):
            break
    state = controller.store.replay()
    write_report(state, Path(case_dir) / "report.md")
    print(f"run 结束：run_status={state.run_status}" + (f"，原因={state.stop_reason}" if state.stop_reason else ""))
    print(f"incumbent={state.incumbent_id}")
    return 0


def cmd_run(args) -> int:
    return _run_loop(args.case, _load_proposals(args.proposals), args.max_candidates, args.max_steps)


def cmd_resume(args) -> int:
    return _run_loop(args.case, _load_proposals(args.proposals), None, args.max_steps)


def cmd_status(args) -> int:
    controller = Controller(args.case)
    state = controller.store.replay()
    out = []
    out.append(f"case_id: {state.case_id}")
    out.append(f"run_status: {state.run_status}" + (f"（{state.stop_reason}）" if state.stop_reason else ""))
    out.append(f"baseline: {state.baseline_variant_id}")
    out.append(f"incumbent: {state.incumbent_id}")
    out.append("stages: " + ", ".join(f"{k}={v}" for k, v in sorted(state.stages.items())))
    print("\n".join(out))
    return 0


def cmd_report(args) -> int:
    controller = Controller(args.case)
    state = controller.store.replay()
    write_report(state, Path(args.case) / "report.md")
    print(f"已生成 {args.case}/report.md")
    return 0


def cmd_freeze(args) -> int:
    # 首版：仅落盘当前快照，不再推进；不迁移活进程内存。
    controller = Controller(args.case)
    state = controller.store.replay()
    controller.store.write_snapshot(state)
    print("已冻结：state.json 已封存当前快照")
    return 0


def cmd_export(args) -> int:
    manifest = export_bundle(args.case, args.output, args.level)
    print(f"已导出到 {args.output}（{len(manifest)} 项）")
    return 0


def cmd_import(args) -> int:
    problems = import_bundle(args.bundle, args.case)
    print(f"已导入到 {args.case}")
    for p in problems:
        print(f"  [warn] {p}", file=sys.stderr)
    return 0


def cmd_gc(args) -> int:
    manifest = ArtifactManifest(Path(args.case) / "artifact-manifest.json")
    removable = gc_plan(manifest, set())
    print(f"可清理产物：{len(removable)} 项（dry-run）")
    for a in removable:
        print(f"  - {a.id} ({a.retention.value}) {a.path}")
    return 0


def cmd_compiler_plan(args) -> int:
    controller = Controller(args.case)
    state = controller.store.replay()
    cand = state.candidates.get(args.variant)
    if cand is None:
        print(f"未找到 variant: {args.variant}", file=sys.stderr)
        return 1
    kg = KnowledgeStore(Path(args.case) / "knowledge")
    recipe = build_dossier(
        case_id=state.case_id,
        candidate_id=args.variant,
        proposal_hash=cand.get("proposal_hash"),
        baseline_variant=cand.get("baseline_variant"),
        before_ir_hash=None,
        after_ir_hash=cand.get("source_or_ir_hash"),
        device_validated=cand.get("status") == "confirmed",
    )
    path = kg.add_recipe(recipe)
    print(f"已生成 dossier/recipe: {path}")
    print(f"状态：{recipe.status.value}（首版不自动改编译器，见设计 T6）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="closure", description="Closure：性能分析到编译器优化的闭环")
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="初始化 case")
    init.add_argument("--case", required=True)
    init.add_argument("--case-id", default="example-kernel")

    doctor = sub.add_parser("doctor", help="探测环境与能力矩阵")
    doctor.add_argument("--case", required=True)

    run = sub.add_parser("run", help="运行控制循环")
    run.add_argument("--case", required=True)
    run.add_argument("--proposals", help="replay planner 的预录 JSON 列表")
    run.add_argument("--max-candidates", type=int, default=None)
    run.add_argument("--max-steps", type=int, default=40)

    resume = sub.add_parser("resume", help="从事件恢复并继续")
    resume.add_argument("--case", required=True)
    resume.add_argument("--proposals", help="补充的预录提案")
    resume.add_argument("--max-steps", type=int, default=40)

    status = sub.add_parser("status", help="查看状态")
    status.add_argument("--case", required=True)

    report = sub.add_parser("report", help="生成 report.md")
    report.add_argument("--case", required=True)

    freeze = sub.add_parser("freeze", help="冻结快照")
    freeze.add_argument("--case", required=True)

    export = sub.add_parser("export", help="导出状态 bundle")
    export.add_argument("--case", required=True)
    export.add_argument("--level", choices=["essentials", "full"], default="essentials")
    export.add_argument("--output", required=True)

    imp = sub.add_parser("import", help="导入状态 bundle")
    imp.add_argument("--bundle", required=True)
    imp.add_argument("--case", required=True)

    gc = sub.add_parser("gc", help="产物 GC（dry-run）")
    gc.add_argument("--case", required=True)

    cp = sub.add_parser("compiler-plan", help="生成 compiler dossier")
    cp.add_argument("--case", required=True)
    cp.add_argument("--variant", required=True)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "init": cmd_init,
        "doctor": cmd_doctor,
        "run": cmd_run,
        "resume": cmd_resume,
        "status": cmd_status,
        "report": cmd_report,
        "freeze": cmd_freeze,
        "export": cmd_export,
        "import": cmd_import,
        "gc": cmd_gc,
        "compiler-plan": cmd_compiler_plan,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())