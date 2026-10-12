"""AI 决策接口的严格动作 envelope（设计 7.1）。

统一 envelope：schema_version、proposal_id、packet_hash、expected_state_seq、
action、payload。payload 是动作内容，拒绝未知字段、隐式类型转换和未注册 artifact。

AI 只能提交提案、分析和补丁，不能直接写状态、事实或执行命令。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import ActionType, ChangeKind


class _Action(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InspectPayload(_Action):
    artifact_id: str
    purpose: str
    start: int | None = None
    limit: int | None = None


class ProposeVariantPayload(_Action):
    baseline: str
    parent_variant: str
    change_kind: ChangeKind
    hypothesis: str
    evidence: list[str] = Field(default_factory=list)
    change: dict[str, Any] = Field(default_factory=dict)
    expected_observation: str = ""
    falsification: str = ""
    required_checks: list[str] = Field(default_factory=list)
    cost_estimate: dict[str, int] = Field(default_factory=dict)
    stop_if: list[str] = Field(default_factory=list)

    @field_validator("change")
    @classmethod
    def _validate_change(cls, v: dict[str, Any], info):
        kind = info.data.get("change_kind")
        if kind == ChangeKind.IR_PATCH and "patch_artifact" not in v:
            raise ValueError("ir_patch 的 change 必须包含 patch_artifact")
        if kind == ChangeKind.COMPILER_OPTION and not isinstance(
            v.get("options"), dict
        ):
            raise ValueError("compiler_option 的 change 必须包含 options 字典")
        return v


class RequestMeasurementPayload(_Action):
    question: str
    evidence_gap: str
    cheapest_decisive_stage: str = ""
    expected_cost: dict[str, int] = Field(default_factory=dict)
    stop_condition: str = ""
    target_candidate: str | None = None


class Claim(_Action):
    text: str
    verification: Literal["observed", "inferred", "unverified"] = "inferred"
    evidence: list[str] = Field(default_factory=list)


class SubmitAnalysisPayload(_Action):
    claims: list[Claim] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"


class ProposeCompilerPatchPayload(_Action):
    source_sha: str
    patch_artifact: str | None = None
    dossier_artifact: str | None = None
    legality_conditions: list[str] = Field(default_factory=list)
    test_suggestions: list[str] = Field(default_factory=list)


class RequestFinishPayload(_Action):
    conclusion: str
    goal_coverage: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


_PAYLOAD_MODELS: dict[ActionType, type[_Action]] = {
    ActionType.INSPECT: InspectPayload,
    ActionType.PROPOSE_VARIANT: ProposeVariantPayload,
    ActionType.REQUEST_MEASUREMENT: RequestMeasurementPayload,
    ActionType.SUBMIT_ANALYSIS: SubmitAnalysisPayload,
    ActionType.PROPOSE_COMPILER_PATCH: ProposeCompilerPatchPayload,
    ActionType.REQUEST_FINISH: RequestFinishPayload,
}


class ActionEnvelope(_Action):
    schema_version: int = 1
    proposal_id: str
    packet_hash: str
    expected_state_seq: int
    action: ActionType
    payload: Any = None

    @model_validator(mode="after")
    def _coerce_payload(self) -> "ActionEnvelope":
        model = _PAYLOAD_MODELS[self.action]
        object.__setattr__(self, "payload", model.model_validate(self.payload))
        return self