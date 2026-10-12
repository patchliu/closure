"""控制器与状态机（设计 6、7）。

只有控制器能提交权威状态；worker 写自己的日志/结果包；AI 只提交提案。
控制器按固定顺序：关联活 worker → 收集结果 → 执行已接受计划 → 申请新提案。

状态贯穿：_emit 返回提交后的最新 State，各步进方法只 replay 一次并传递，
避免每个事件全链重放。
"""
from __future__ import annotations

import json
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .evaluator import Evaluator
from .executors import LocalExecutor, RunSpec
from .hashing import sha256, sha256_file
from .planner import NullPlanner, Planner
from .schemas import (
    ActionEnvelope,
    Candidate,
    CaseConfig,
    DecisionPacket,
    EventType,
    StageStatus,
)
from .selection import PromotionContext, promotion_ok, route_evidence_level
from .state import State, StateStore

_VARIANT_PIPELINE = ["validate", "benchmark", "evaluate"]


@dataclass
class StepOutcome:
    status: str  # continue / blocked / stopped / done
    state: State
    detail: str = ""


class ExperimentPaths:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.case_toml = self.root / "case.toml"
        self.profiles_dir = self.root / "profiles"
        self.events = self.root / "events.jsonl"
        self.state = self.root / "state.json"
        self.input_dir = self.root / "input"
        self.runs_dir = self.root / "runs"
        self.analysis_dir = self.root / "analysis"
        self.report = self.root / "report.md"
        self.artifact_manifest = self.root / "artifact-manifest.json"


class Controller:
    def __init__(self, case_dir: str | Path, planner: Planner | None = None):
        self.paths = ExperimentPaths(case_dir)
        self.store = StateStore(str(self.paths.events), str(self.paths.state))
        self.planner: Planner = planner or NullPlanner()
        self._started_at = time.monotonic()

    def case_config(self) -> CaseConfig:
        data = tomllib.loads(self.paths.case_toml.read_text(encoding="utf-8"))
        return CaseConfig.model_validate(data)

    def evaluator(self) -> Evaluator:
        cfg = self.case_config()
        return Evaluator(
            protocol=cfg.evaluation.protocol,
            reference_hash=sha256_file(str(self.paths.root / cfg.correctness.reference))
            if (self.paths.root / cfg.correctness.reference).exists()
            else None,
            rtol=cfg.correctness.rtol,
            atol=cfg.correctness.atol,
        )

    # ---- 事件提交（唯一权威入口） ----
    def _emit(self, type_: EventType, payload: dict) -> State:
        self.store.events.append(type_, payload)
        state = self.store.replay()
        self.store.write_snapshot(state)
        return state

    # ---- 初始化 / 基线 ----
    def ensure_initialized(self, state: State) -> State:
        if state.case_id is None:
            cfg = self.case_config()
            state = self._emit(
                EventType.CASE_CREATED,
                {"case_id": cfg.case_id, "budget_limits": cfg.budget.model_dump(exclude={"schema_version"})},
            )
        if state.baseline_variant_id is None:
            state = self._emit(
                EventType.CANDIDATE_REGISTERED,
                {
                    "candidate": {
                        "candidate_id": "v000",
                        "baseline_variant": "v000",
                        "status": "proposed",
                        "stages": {s: "succeeded" for s in _VARIANT_PIPELINE},
                        "objective": {},
                    },
                    "is_baseline": True,
                },
            )
            state = self._emit(EventType.CANDIDATE_PROMOTED, {"candidate_id": "v000"})
        return state

    # ---- 预算 ----
    def _budget_exhausted(self, state: State) -> str | None:
        limits = state.budget_limited or {}
        used = state.budget_used or {}
        checks = {
            "max_model_calls": ("model_calls", limits.get("max_model_calls")),
            "max_candidates": ("candidates", limits.get("max_candidates")),
            "max_simulator_runs": ("simulator_runs", limits.get("max_simulator_runs")),
        }
        for reason, (key, limit) in checks.items():
            if limit is not None and used.get(key, 0) >= int(limit):
                return reason
        max_wall = limits.get("max_wall_seconds")
        if max_wall is not None:
            wall = state.budget_used.get("wall_seconds", 0) + (time.monotonic() - self._started_at)
            if wall >= int(max_wall):
                return "max_wall_seconds"
        return None

    # ---- 预算记录 ----
    def adjust_budget(self, limits: dict) -> State:
        """调整预算上限（设计 7.3：记录事件，不追溯更改已有成本）。"""
        return self._emit(EventType.BUDGET_ADJUSTED, {"limits": limits})

    def record_wall_usage(self) -> State:
        """把本进程已消耗的墙钟时间落盘，resume 后墙钟预算不重置。

        总预算必须包含失败与基础设施故障的实际消耗（设计 25.2 条 6）；
        墙钟是跨进程唯一需要累积记录的预算项。
        """
        elapsed = round(time.monotonic() - self._started_at, 6)
        self._started_at = time.monotonic()
        return self._emit(EventType.BUDGET_ADJUSTED, {"used": {"wall_seconds": elapsed}})

    # ---- decision packet ----
    def build_packet(self, state: State) -> DecisionPacket:
        packet = DecisionPacket(
            case_id=state.case_id,
            state_seq=state.seq,
            protocol_hash=self.evaluator().protocol_hash(),
            incumbent_id=state.incumbent_id,
            negated_hypotheses=[
                c["hypothesis"]
                for c in state.candidates.values()
                if c.get("status") == "rejected" and c.get("hypothesis")
            ],
            remaining_budget=_remaining_budget(state),
            allowed_actions=["propose_variant", "submit_analysis", "request_finish", "inspect"],
        )
        packet.packet_hash = sha256(packet.model_dump(exclude={"packet_hash"}))
        return packet

    # ---- 主步进 ----
    def run_step(self) -> StepOutcome:
        state = self.store.replay()
        if state.run_status == "stopped":
            return StepOutcome("done", state, state.stop_reason or "")
        if state.case_id is None or state.baseline_variant_id is None:
            state = self.ensure_initialized(state)

        reason = self._budget_exhausted(state)
        if reason:
            state = self._emit(EventType.RUN_STOPPED, {"reason": reason})
            return StepOutcome("stopped", state, reason)

        cand = self._pending_candidate(state)
        if cand is not None:
            state = self._advance_candidate(cand["candidate_id"], state)
            return StepOutcome("continue", state)

        packet = self.build_packet(state)
        proposal = self.planner.decide(packet)
        if proposal is None:
            state = self._emit(EventType.RUN_STOPPED, {"reason": "waiting_for_external_input"})
            return StepOutcome("blocked", state, "waiting_for_external_input")

        return self._resolve_proposal(proposal, state)

    def _pending_candidate(self, state: State) -> dict | None:
        for cid, c in state.candidates.items():
            if c.get("status") == "proposed" and cid != state.baseline_variant_id:
                return c
        return None

    # ---- proposal 处理 ----
    def _resolve_proposal(self, proposal: ActionEnvelope, state: State) -> StepOutcome:
        if proposal.expected_state_seq != state.seq:
            state = self._emit(
                EventType.PROPOSAL_REJECTED,
                {"proposal_id": proposal.proposal_id, "reason": "STALE_PROPOSAL"},
            )
            return StepOutcome("continue", state, "STALE_PROPOSAL")

        content_hash = sha256(proposal.model_dump())
        if proposal.proposal_id in state.accepted_proposals:
            if state.accepted_proposals[proposal.proposal_id] == content_hash:
                return StepOutcome("continue", state, "already_accepted")
            state = self._emit(
                EventType.PROPOSAL_REJECTED,
                {"proposal_id": proposal.proposal_id, "reason": "duplicate_id_conflict"},
            )
            return StepOutcome("continue", state, "duplicate_id_conflict")

        state = self._emit(
            EventType.PROPOSAL_ACCEPTED,
            {"proposal": proposal.model_dump(), "plan_hash": self._plan_hash(proposal)},
        )

        action = proposal.action
        if action.value == "propose_variant":
            state = self._register_variant(proposal, state)
        elif action.value == "request_finish":
            if self._goal_met(state):
                state = self._emit(EventType.RUN_STOPPED, {"reason": "finished"})
                return StepOutcome("stopped", state, "finished")
            return StepOutcome("continue", state, "goal_not_met")
        elif action.value == "submit_analysis":
            self._save_analysis(proposal)
        # inspect / request_measurement / propose_compiler_patch：首版记录，不改状态
        return StepOutcome("continue", state)

    def _plan_hash(self, proposal: ActionEnvelope) -> str:
        cfg = self.case_config()
        return sha256(
            {
                "proposal": proposal.model_dump(),
                "case_id": cfg.case_id,
                "dtype": cfg.dtype,
                "shape": cfg.shape,
                "grid": cfg.grid,
            }
        )

    def _goal_met(self, state: State) -> bool:
        for cid, c in state.candidates.items():
            if cid != state.baseline_variant_id and c.get("status") == "confirmed":
                return True
        return False

    def _register_variant(self, proposal: ActionEnvelope, state: State) -> State:
        payload = proposal.payload
        vid = f"v{len(state.candidates):03d}"
        cfg = self.case_config()
        evaluator = self.evaluator()
        candidate = {
            "candidate_id": vid,
            "parent_variant": payload.parent_variant,
            "baseline_variant": payload.baseline,
            "hypothesis": payload.hypothesis,
            "proposal_hash": sha256(proposal.model_dump()),
            "source_or_ir_hash": sha256({"variant": vid, "change": payload.change}),
            "evaluation_protocol_hash": evaluator.protocol_hash(),
            "scope": "local-fixture",
            "status": "proposed",
            "evidence_level": route_evidence_level(cfg.search.mode, self._device_available(state)).value,
            "stages": {
                "compile": "skipped",
                "simulate": "blocked",
                "validate": "pending",
                "benchmark": "pending",
                "evaluate": "pending",
            },
            "objective": {"latency_ratio_to_baseline": None},
        }
        return self._emit(EventType.CANDIDATE_REGISTERED, {"candidate": candidate, "is_baseline": False})

    def _device_available(self, state: State) -> bool:
        """环境能力矩阵中 benchmark 是否已探测为 supported（doctor 发射 environment.probed）。"""
        return (state.environment or {}).get("benchmark") == "supported"

    # ---- 候选推进 ----
    def _advance_candidate(self, cid: str, state: State) -> State:
        cand = state.candidates[cid]
        stages = cand.get("stages", {})
        for stage in _VARIANT_PIPELINE:
            if stages.get(stage) != "succeeded":
                return self._run_stage(cid, stage, state)
        return state

    def _run_stage(self, cid: str, stage: str, state: State) -> State:
        state = self._emit(EventType.STAGE_STARTED, {"stage": stage, "candidate_id": cid})
        if stage == "validate":
            ok, checks = self._validate_correctness()
            state = self._emit(
                EventType.STAGE_RESULT,
                {
                    "stage": stage,
                    "status": StageStatus.SUCCEEDED.value if ok else StageStatus.FAILED.value,
                    "candidate_id": cid,
                    "checks": checks,
                    "cost": {"runs": 2},  # reference + candidate 各一次子进程
                },
            )
            if not ok:
                state = self._emit(EventType.CANDIDATE_REJECTED, {"candidate_id": cid, "reason": "CORRECTNESS_FAILED"})
        elif stage == "benchmark":
            baseline_median, candidate_median = self._benchmark()
            ratio = Evaluator.latency_ratio(candidate_median, baseline_median) if baseline_median > 0 else 0.0
            state = self._emit(
                EventType.STAGE_RESULT,
                {
                    "stage": stage,
                    "status": StageStatus.SUCCEEDED.value,
                    "candidate_id": cid,
                    "checks": {"baseline_median": baseline_median, "candidate_median": candidate_median, "ratio": ratio},
                    "cost": {"runs": 6},  # baseline/candidate 各 3 次采样子进程
                },
            )
        elif stage == "evaluate":
            state = self._evaluate(cid, state)
        return state

    def _evaluate(self, cid: str, state: State) -> State:
        cand = state.candidates[cid]
        evaluator = self.evaluator()
        # 独立确认：benchmark 中 candidate < baseline（比率 > 0）
        obj = cand.get("objective", {})
        ratio = obj.get("latency_ratio_to_baseline")
        ctx = PromotionContext(
            protocol_hash=evaluator.protocol_hash(),
            source_hash_matches=cand.get("source_or_ir_hash") is not None,
            correctness_passed=cand.get("stages", {}).get("validate") == "succeeded",
            independent_confirmation_passed=ratio is not None and ratio > 0,
            regression_limits_passed=ratio is not None and ratio > 0,
            mandatory_artifacts_verified=True,
        )
        ok, failed = promotion_ok(Candidate(**cand), ctx)
        state = self._emit(
            EventType.STAGE_RESULT,
            {"stage": "evaluate", "status": StageStatus.SUCCEEDED.value if ok else StageStatus.FAILED.value, "candidate_id": cid, "checks": {"failed": failed}},
        )
        if ok:
            return self._emit(EventType.CANDIDATE_PROMOTED, {"candidate_id": cid})
        return self._emit(EventType.CANDIDATE_REJECTED, {"candidate_id": cid, "reason": "promotion_failed: " + ",".join(failed)})

    # ---- 本地数值 fixture 运行 ----
    def _validate_correctness(self) -> tuple[bool, dict]:
        cfg = self.case_config()
        evaluator = self.evaluator()
        ref = self._run_python(cfg.correctness.reference, [])
        cand = self._run_python(cfg.entry, ["--mode", "candidate"])
        if ref is None or cand is None:
            return False, {"reference": "missing", "candidate": "missing"}
        ok = evaluator.check_correctness(ref.get("values"), cand.get("values"))
        return ok, {"correctness": "pass" if ok else "fail"}

    def _benchmark(self) -> tuple[float, float]:
        cfg = self.case_config()
        n = 3
        baseline = [self._run_python(cfg.entry, ["--mode", "baseline"])["latency_ms"] for _ in range(n)]
        candidate = [self._run_python(cfg.entry, ["--mode", "candidate"])["latency_ms"] for _ in range(n)]
        return Evaluator.median(baseline), Evaluator.median(candidate)

    def _run_python(self, script_rel: str, extra: list[str]) -> dict | None:
        out = self.paths.runs_dir / ".tmp" / f"{sha256(script_rel + json.dumps(extra))[:12]}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        argv = [sys.executable, str(self.paths.root / script_rel), *extra, "--out", str(out)]
        result = LocalExecutor().run(RunSpec(argv=argv, cwd=str(self.paths.root), log_dir=str(out.parent)))
        if result.exit_code != 0 or not out.exists():
            return None
        return json.loads(out.read_text(encoding="utf-8"))

    def _save_analysis(self, proposal: ActionEnvelope) -> None:
        self.paths.analysis_dir.mkdir(parents=True, exist_ok=True)
        path = self.paths.analysis_dir / f"{proposal.proposal_id}.json"
        path.write_text(json.dumps(proposal.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


def _remaining_budget(state: State) -> dict:
    limits = state.budget_limited or {}
    used = state.budget_used or {}
    out = {}
    for k in ("max_model_calls", "max_candidates", "max_simulator_runs", "max_wall_seconds"):
        if k in limits:
            key = k.replace("max_", "")
            out[k] = limits[k] - used.get(key, 0)
    return out
