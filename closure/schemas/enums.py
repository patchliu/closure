"""Closure 使用的所有枚举与固定错误码。

枚举值即判定依据；状态推进必须依赖这些枚举，而不是报告措辞。
"""
from __future__ import annotations

from enum import Enum


class Stage(str, Enum):
    PREFLIGHT = "preflight"
    CAPTURE = "capture"
    DUMP = "dump"
    COMPILE = "compile"
    SIMULATE = "simulate"
    VALIDATE = "validate"
    BENCHMARK = "benchmark"
    ANALYZE = "analyze"
    PROPOSE = "propose"
    CHECK_PROPOSAL = "check_proposal"
    EVALUATE = "evaluate"
    COMPILER_PLAN = "compiler_plan"
    PATCH = "patch"
    TEST = "test"
    FINISHED = "finished"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"


class CheckResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    NOT_RUN = "not_run"


class Capability(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class Verification(str, Enum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"


class Completeness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    INVALID = "invalid"


class CandidateStatus(str, Enum):
    PROPOSED = "proposed"
    COMPILED = "compiled"
    PROVISIONAL = "provisional"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class EvidenceLevel(str, Enum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"


class LessonLevel(str, Enum):
    OBSERVATION = "observation"
    VALIDATED_CASE = "validated_case"
    RULE_CANDIDATE = "rule_candidate"
    ACTIVE_RULE = "active_rule"


class RecipeStatus(str, Enum):
    PROPOSED = "proposed"
    TESTED = "tested"
    COMPILER_INTEGRATED = "compiler_integrated"


class HandoffStatus(str, Enum):
    CANDIDATE_READY = "candidate_ready"
    NEED_EVIDENCE = "need_evidence"
    PIVOT = "pivot"
    BLOCKED = "blocked"


class SearchMode(str, Enum):
    DIAGNOSE = "diagnose"
    OPTIMIZE = "optimize"
    COMPILER_LANDING = "compiler_landing"


class Transport(str, Enum):
    LOCAL = "local"
    SSH = "ssh"


class Runtime(str, Enum):
    NATIVE = "native"
    DOCKER = "docker"


class ActionType(str, Enum):
    INSPECT = "inspect"
    PROPOSE_VARIANT = "propose_variant"
    REQUEST_MEASUREMENT = "request_measurement"
    SUBMIT_ANALYSIS = "submit_analysis"
    PROPOSE_COMPILER_PATCH = "propose_compiler_patch"
    REQUEST_FINISH = "request_finish"


class RetentionLevel(str, Enum):
    ESSENTIAL = "essential"
    EVIDENCE = "evidence"
    REPRODUCIBLE = "reproducible"
    SCRATCH = "scratch"


class ChangeKind(str, Enum):
    IR_PATCH = "ir_patch"
    COMPILER_OPTION = "compiler_option"


class ErrorCode(str, Enum):
    CONFIG_INVALID = "CONFIG_INVALID"
    EVALUATION_CONFIG_MISSING = "EVALUATION_CONFIG_MISSING"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    STALE_PROPOSAL = "STALE_PROPOSAL"
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    HASH_MISMATCH = "HASH_MISMATCH"
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
    COMPILE_FAILED = "COMPILE_FAILED"
    INJECTION_UNVERIFIED = "INJECTION_UNVERIFIED"
    TARGET_NOT_MATCHED = "TARGET_NOT_MATCHED"
    TRACE_PARTIAL = "TRACE_PARTIAL"
    CORRECTNESS_FAILED = "CORRECTNESS_FAILED"
    PERFORMANCE_INCONCLUSIVE = "PERFORMANCE_INCONCLUSIVE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    PLANNER_INVALID = "PLANNER_INVALID"


class EventType(str, Enum):
    CASE_CREATED = "case.created"
    ENVIRONMENT_PROBED = "environment.probed"
    PROPOSAL_ACCEPTED = "proposal.accepted"
    PROPOSAL_REJECTED = "proposal.rejected"
    STAGE_PLANNED = "stage.planned"
    STAGE_STARTED = "stage.started"
    STAGE_RESULT = "stage.result_committed"
    CANDIDATE_REGISTERED = "candidate.registered"
    CANDIDATE_PROMOTED = "candidate.promoted"
    CANDIDATE_REJECTED = "candidate.rejected"
    BUDGET_ADJUSTED = "budget.adjusted"
    RUN_STOPPED = "run.stopped"
    ARTIFACT_SEALED = "artifact.sealed"
    SYNC_VERIFIED = "sync.verified"
    REVIEW_ATTESTED = "review.attested"