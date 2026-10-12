"""结果、事实、产物、候选、经验、协议等结构化记录 schema。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    CandidateStatus,
    CheckResult,
    EvidenceLevel,
    HandoffStatus,
    LessonLevel,
    RecipeStatus,
    RetentionLevel,
    Stage,
    StageStatus,
    Verification,
)


class _Rec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fact(_Rec):
    """一条可定位来源的事实；value 与 verification 分开（设计 7.4）。"""

    key: str
    value: Any = None
    verification: Verification = Verification.UNVERIFIED
    source_artifact: str | None = None
    parser_version: str | None = None
    offset: int | None = None


class Check(_Rec):
    name: str
    result: CheckResult = CheckResult.NOT_RUN
    code: str | None = None
    source_artifact: str | None = None
    parser_version: str | None = None


class ProcessInfo(_Rec):
    exit_code: int | None = None
    signal: str | None = None
    reason: str | None = None


class Result(_Rec):
    """一次 attempt 的 stage 结果（对应设计 6.3）。"""

    case_id: str
    variant_id: str
    attempt_id: str
    stage: Stage
    status: StageStatus
    process: ProcessInfo = ProcessInfo()
    target_kernel: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
    checks: dict[str, Any] = Field(default_factory=dict)
    eligible_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class Artifact(_Rec):
    id: str
    path: str
    sha256: str
    bytes: int
    type: str
    stage: Stage | None = None
    deps: list[str] = Field(default_factory=list)
    retention: RetentionLevel = RetentionLevel.EVIDENCE
    rebuildable: bool = False
    copies: list[str] = Field(default_factory=list)
    checked_at: str | None = None
    sealed: bool = False


class Measurement(_Rec):
    id: str
    candidate_id: str
    metric: str
    value: float
    unit: str | None = None
    sample_index: int | None = None
    raw: list[float] = Field(default_factory=list)


class Candidate(_Rec):
    """候选谱系（设计 23.2）。"""

    candidate_id: str
    parent_variant: str | None = None
    baseline_variant: str
    hypothesis: str | None = None
    proposal_hash: str | None = None
    source_or_ir_hash: str | None = None
    target_fingerprint: str | None = None
    evaluation_protocol_hash: str | None = None
    scope: str | None = None
    status: CandidateStatus = CandidateStatus.PROPOSED
    evidence_level: EvidenceLevel = EvidenceLevel.E0
    stages: dict[str, str] = Field(default_factory=dict)
    objective: dict[str, Any] = Field(default_factory=dict)
    measurements: list[Measurement] = Field(default_factory=list)
    rejection_reason: str | None = None


class Lesson(_Rec):
    """经验（设计 17）。至少含问题签名、前提、禁止条件、检测器、动作、验证器。"""

    id: str
    signature: str
    preconditions: list[str] = Field(default_factory=list)
    prohibitions: list[str] = Field(default_factory=list)
    detector: str = ""
    suggested_action: str = ""
    validator: str = ""
    success_cases: list[str] = Field(default_factory=list)
    failure_cases: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)
    toolchain_scope: str = ""
    level: LessonLevel = LessonLevel.OBSERVATION
    last_verified: str | None = None


class Recipe(_Rec):
    """优化 recipe（设计 23.4）。"""

    recipe_id: str
    status: RecipeStatus = RecipeStatus.PROPOSED
    pattern: str = ""
    preconditions: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    transformation: str = ""
    expected_effect: str = ""
    reject_if: list[str] = Field(default_factory=list)
    compiler_location: dict[str, str] = Field(default_factory=dict)
    positive_cases: list[str] = Field(default_factory=list)
    negative_cases: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class DecisionPacket(_Rec):
    """短 episode 的恢复包（设计 23.3）。"""

    case_id: str
    packet_hash: str = ""
    state_seq: int = 0
    schema_version: int = 1
    protocol_hash: str | None = None
    platform_pack_hash: str | None = None
    incumbent_id: str | None = None
    current_candidate_id: str | None = None
    fact_summary: list[dict[str, Any]] = Field(default_factory=list)
    evidence_index: list[str] = Field(default_factory=list)
    negated_hypotheses: list[str] = Field(default_factory=list)
    remaining_budget: dict[str, Any] = Field(default_factory=dict)
    allowed_actions: list[str] = Field(default_factory=list)
    unsatisfied_checks: list[str] = Field(default_factory=list)


class Handoff(_Rec):
    """episode 交接（设计 23.3）。只能声明意图，最终状态由控制器重新验收。"""

    status: HandoffStatus
    artifact_id: str | None = None
    note: str = ""