"""case / profile / resolved 三层配置的严格 schema。

三层原则（设计 5.1）：
- case.toml：算子语义、输入、预算与正确性标准，不含主机绝对路径；
- profiles/*.toml：执行位置、容器、解释器、激活脚本、SoC 与工具定位；
- resolved.json：解析后的实际路径、版本、哈希、argv，创建 attempt 后不可改。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import Runtime, SearchMode, Transport

SCHEMA_VERSION = 1


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = SCHEMA_VERSION


class Roles(_Schema):
    compile: str
    simulate: str
    validate_role: str = Field(validation_alias="validate")
    benchmark: str


class Correctness(_Schema):
    reference: str
    input_mode: str
    rtol: float
    atol: float


class Simulation(_Schema):
    input_mode: str = "initialized"
    launch_count: int = 1
    capture_after_target_seconds: int = 600
    startup_timeout_seconds: int = 600
    hard_timeout_seconds: int = 1800
    allow_partial: bool = True


class Budget(_Schema):
    max_candidates: int = 5
    max_simulator_runs: int = 6
    max_wall_seconds: int = 7200
    max_artifact_bytes: int = 21474836480
    max_model_calls: int = 20


class Search(_Schema):
    mode: SearchMode = SearchMode.DIAGNOSE
    max_stalled_candidates: int = 3
    candidate_pool_size: int = 3


class Evaluation(_Schema):
    protocol: str = "closure-eval-v1"
    protected_reference: bool = True
    promotion_requires: str = "device_confirmed"
    confirmation_order: str = "ABBA"


class CaseConfig(_Schema):
    case_id: str
    entry: str
    kernel_symbol: str
    dtype: str = "float16"
    shape: list[int] = Field(default_factory=lambda: [1, 8192, 96, 128])
    grid: list[int] = Field(default_factory=lambda: [64])
    seed: int
    roles: Roles
    correctness: Correctness
    simulation: Simulation = Simulation()
    budget: Budget = Budget()
    search: Search = Search()
    evaluation: Evaluation = Evaluation()


class Profile(_Schema):
    """机器 profile；name 通常取文件名去后缀。"""

    name: str
    transport: Transport
    runtime: Runtime = Runtime.NATIVE
    container: str | None = None
    user: str | None = None
    python: str | None = None
    bootstrap: str | None = None
    work_root: str | None = None
    roles: list[str]
    soc: str | None = None
    device: str | None = None
    ssh_alias: str | None = None


class ResolvedConfig(_Schema):
    """解析后的实际配置，创建 attempt 后不可改。"""

    case_id: str
    profile_name: str | None = None
    kernel_symbol: str
    entry_abs: str | None = None
    python: str | None = None
    soc: str | None = None
    argv: list[str] = Field(default_factory=list)
    input_sha256: str | None = None
    toolchain_fingerprint: str | None = None
    semantic_params: dict[str, Any] = Field(default_factory=dict)