"""候选晋级与分级路由（设计 23）。

晋级谓词固定在 selection 中；快筛胜者不能直接晋级为 device incumbent。
只有通过全部谓词的候选，控制器才追加 candidate.promoted 事件。
"""
from __future__ import annotations

from dataclasses import dataclass

from .schemas import Candidate, EvidenceLevel, SearchMode


@dataclass
class PromotionContext:
    protocol_hash: str
    source_hash_matches: bool
    correctness_passed: bool
    independent_confirmation_passed: bool
    regression_limits_passed: bool
    mandatory_artifacts_verified: bool


def promotion_ok(candidate: Candidate, ctx: PromotionContext) -> tuple[bool, list[str]]:
    checks = {
        "source_hash_matches": candidate.source_or_ir_hash is not None and ctx.source_hash_matches,
        "evaluation_protocol_matches": candidate.evaluation_protocol_hash == ctx.protocol_hash,
        "requested_scope_correctness_passed": ctx.correctness_passed,
        "independent_confirmation_passed": ctx.independent_confirmation_passed,
        "configured_regression_limits_passed": ctx.regression_limits_passed,
        "mandatory_artifacts_verified": ctx.mandatory_artifacts_verified,
    }
    failed = [k for k, v in checks.items() if not v]
    return (not failed, failed)


def route_evidence_level(mode: SearchMode, device_available: bool) -> EvidenceLevel:
    """首次需要运行的证据等级：diagnose 从 E0 起步；optimize 可先短测。"""
    if mode == SearchMode.COMPILER_LANDING:
        return EvidenceLevel.E2
    if mode == SearchMode.OPTIMIZE and device_available:
        return EvidenceLevel.E1
    return EvidenceLevel.E0