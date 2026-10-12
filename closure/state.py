"""状态快照与事件 reducer。

state.json 是可从 events.jsonl 重建的派生快照。所有状态推进都通过 reducer；
AI 输出永远不会直接产生状态（不变量 1）。
"""
from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field

from .events import Event, EventStore, verify_chain
from .hashing import sha256
from .schemas.enums import EventType, StageStatus


class State(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    seq: int = 0
    case_id: str | None = None
    run_status: str = "created"
    stop_reason: str | None = None
    stages: dict[str, str] = Field(default_factory=dict)
    candidates: dict[str, dict] = Field(default_factory=dict)
    incumbent_id: str | None = None
    baseline_variant_id: str | None = None
    budget_limited: dict = Field(default_factory=dict)
    budget_used: dict = Field(default_factory=dict)
    facts: dict[str, dict] = Field(default_factory=dict)
    artifacts: dict[str, dict] = Field(default_factory=dict)
    lessons: dict[str, dict] = Field(default_factory=dict)
    environment: dict = Field(default_factory=dict)
    accepted_plan_hash: str | None = None
    pending_proposal: dict | None = None
    accepted_proposals: dict[str, str] = Field(default_factory=dict)


def _bump(state: State, key: str, n: int = 1) -> None:
    state.budget_used[key] = state.budget_used.get(key, 0) + n


def _on_case_created(state: State, p: dict) -> None:
    state.case_id = p.get("case_id")
    for k, v in (p.get("budget_limits") or {}).items():
        state.budget_limited[k] = v
    for stage in ("preflight", "capture", "compile", "simulate", "validate", "benchmark", "evaluate"):
        state.stages.setdefault(stage, StageStatus.PENDING.value)


def _on_environment_probed(state: State, p: dict) -> None:
    state.environment = p.get("capabilities", {})


def _on_proposal_accepted(state: State, p: dict) -> None:
    state.pending_proposal = p.get("proposal")
    _bump(state, "model_calls")
    proposal = p.get("proposal") or {}
    pid = proposal.get("proposal_id")
    if pid:
        state.accepted_proposals[pid] = sha256(proposal)


def _on_proposal_rejected(state: State, _p: dict) -> None:
    _bump(state, "model_calls")
    state.pending_proposal = None


def _on_stage_planned(state: State, p: dict) -> None:
    stage = p.get("stage", "")
    if stage:
        state.stages[stage] = StageStatus.PENDING.value
    state.accepted_plan_hash = p.get("plan_hash")


def _on_stage_started(state: State, p: dict) -> None:
    stage = p.get("stage", "")
    if stage:
        state.stages[stage] = StageStatus.RUNNING.value


def _on_stage_result(state: State, p: dict) -> None:
    stage = p.get("stage", "")
    status = p.get("status", StageStatus.FAILED.value)
    if stage:
        state.stages[stage] = status
    cid = p.get("candidate_id")
    if cid and cid in state.candidates:
        state.candidates[cid].setdefault("stages", {})[stage] = status
        checks = p.get("checks") or {}
        if stage == "benchmark" and "ratio" in checks:
            state.candidates[cid].setdefault("objective", {})[
                "latency_ratio_to_baseline"
            ] = checks["ratio"]
    if p.get("cost"):
        for k, v in p["cost"].items():
            state.budget_used[k] = state.budget_used.get(k, 0) + v


def _on_candidate_registered(state: State, p: dict) -> None:
    candidate = p.get("candidate", {})
    cid = candidate.get("candidate_id") or p.get("candidate_id")
    if cid:
        state.candidates[cid] = candidate
    if p.get("is_baseline"):
        state.baseline_variant_id = cid
    else:
        _bump(state, "candidates")


def _on_candidate_promoted(state: State, p: dict) -> None:
    cid = p.get("candidate_id")
    if cid:
        state.incumbent_id = cid
        state.candidates[cid]["status"] = "confirmed"


def _on_candidate_rejected(state: State, p: dict) -> None:
    cid = p.get("candidate_id")
    if cid and cid in state.candidates:
        state.candidates[cid]["status"] = "rejected"
        state.candidates[cid]["rejection_reason"] = p.get("reason")


def _on_budget_adjusted(state: State, p: dict) -> None:
    for k, v in (p.get("limits") or {}).items():
        state.budget_limited[k] = v


def _on_run_stopped(state: State, p: dict) -> None:
    state.run_status = "stopped"
    state.stop_reason = p.get("reason")


def _on_artifact_sealed(state: State, p: dict) -> None:
    artifact = p.get("artifact", {})
    aid = artifact.get("id") or p.get("id")
    if aid:
        state.artifacts[aid] = artifact


def _on_sync_verified(state: State, p: dict) -> None:
    state.facts.setdefault("sync", {})["verified"] = p.get("level")


def _on_review_attested(state: State, p: dict) -> None:
    state.facts.setdefault("review", {})[p.get("id", "attestation")] = p


_HANDLERS = {
    EventType.CASE_CREATED: _on_case_created,
    EventType.ENVIRONMENT_PROBED: _on_environment_probed,
    EventType.PROPOSAL_ACCEPTED: _on_proposal_accepted,
    EventType.PROPOSAL_REJECTED: _on_proposal_rejected,
    EventType.STAGE_PLANNED: _on_stage_planned,
    EventType.STAGE_STARTED: _on_stage_started,
    EventType.STAGE_RESULT: _on_stage_result,
    EventType.CANDIDATE_REGISTERED: _on_candidate_registered,
    EventType.CANDIDATE_PROMOTED: _on_candidate_promoted,
    EventType.CANDIDATE_REJECTED: _on_candidate_rejected,
    EventType.BUDGET_ADJUSTED: _on_budget_adjusted,
    EventType.RUN_STOPPED: _on_run_stopped,
    EventType.ARTIFACT_SEALED: _on_artifact_sealed,
    EventType.SYNC_VERIFIED: _on_sync_verified,
    EventType.REVIEW_ATTESTED: _on_review_attested,
}


def reduce(events: list[Event]) -> State:
    state = State()
    for e in events:
        handler = _HANDLERS.get(e.type)
        if handler is not None:
            handler(state, e.payload)
        state.seq = e.seq
    return state


class StateStore:
    """事件日志 + 快照的读写与重建；写入通过其它组件提交事件后调用。"""

    def __init__(self, events_path: str, state_path: str):
        self.events = EventStore(events_path)
        self.state_path = state_path

    def replay(self) -> State:
        events = self.events.load()
        verify_chain(events)
        return reduce(events)

    def write_snapshot(self, state: State) -> None:
        """原子写快照：临时文件 + fsync + rename。"""
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.state_path)
        dfd = os.open(os.path.dirname(self.state_path) or ".", os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)

    def load_snapshot(self) -> State | None:
        if not os.path.exists(self.state_path):
            return None
        return State.model_validate_json(open(self.state_path, encoding="utf-8").read())