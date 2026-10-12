"""执行器：local / ssh / docker 与组合。

首版固定 local/SSH/Docker executor。每个 executor 输出能力探测结果：
supported / unsupported / unknown + 原因。探测失败返回能力缺口，不能让 AI 猜参数绕过。
未配置或不可用的传输不伪造成功。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

from .schemas.enums import Capability

# 能力探测的统一三态 + unkown/unsupported 原因
CAPABILITY_KEYS = (
    "compile",
    "inject",
    "full_dump",
    "simulate",
    "graceful_stop",
    "correctness",
    "benchmark",
)
SUPPORTED = Capability.SUPPORTED.value
UNSUPPORTED = Capability.UNSUPPORTED.value
UNKNOWN = Capability.UNKNOWN.value


@dataclass
class ProbeResult:
    transport: str
    capabilities: dict[str, str] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "transport": self.transport,
            "capabilities": self.capabilities,
            "reasons": self.reasons,
        }


@dataclass
class RunSpec:
    argv: list[str]
    cwd: str
    env: dict[str, str] | None = None
    log_dir: str | None = None
    timeout_seconds: int | None = None
    nonce: str = ""


@dataclass
class RunResult:
    exit_code: int
    stdout_path: str | None = None
    stderr_path: str | None = None
    signal: str | None = None
    timed_out: bool = False
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and self.signal is None


class UnsupportedError(RuntimeError):
    def __init__(self, capability: str, reason: str):
        self.capability = capability
        self.reason = reason
        super().__init__(f"{capability} unsupported: {reason}")


class Executor:
    transport = "base"

    def probe(self) -> ProbeResult:
        raise NotImplementedError

    def run(self, _spec: RunSpec) -> RunResult:
        raise NotImplementedError


class LocalExecutor(Executor):
    transport = "local"

    def probe(self) -> ProbeResult:
        caps = {k: UNSUPPORTED for k in CAPABILITY_KEYS}
        reasons: dict[str, str] = {}
        python = shutil.which("python3") or shutil.which("python")
        if python:
            caps["correctness"] = SUPPORTED
            caps["benchmark"] = SUPPORTED
        for k, v in caps.items():
            if v == UNSUPPORTED:
                reasons[k] = "本机未装配对应 Ascend 工具，需绑定 profile 后重新 doctor"
        # 精确命令存在性由 adapters.ascend 进一步探测，这里只报告本地执行能力。
        return ProbeResult("local", caps, reasons)

    def run(self, spec: RunSpec) -> RunResult:
        stdout_path = stderr_path = None
        if spec.log_dir:
            os.makedirs(spec.log_dir, exist_ok=True)
            stdout_path = os.path.join(spec.log_dir, "stdout.log")
            stderr_path = os.path.join(spec.log_dir, "stderr.log")
        stdout_f = open(stdout_path, "wb") if stdout_path else None
        stderr_f = open(stderr_path, "wb") if stderr_path else None
        try:
            proc = subprocess.run(
                [str(a) for a in spec.argv],
                cwd=spec.cwd,
                env=spec.env,
                stdout=stdout_f or subprocess.PIPE,
                stderr=stderr_f or subprocess.PIPE,
                timeout=spec.timeout_seconds,
            )
            return RunResult(exit_code=proc.returncode, stdout_path=stdout_path, stderr_path=stderr_path)
        except subprocess.TimeoutExpired:
            return RunResult(exit_code=-1, stdout_path=stdout_path, stderr_path=stderr_path, timed_out=True)
        finally:
            if stdout_f:
                stdout_f.close()
            if stderr_f:
                stderr_f.close()


class SshExecutor(Executor):
    transport = "ssh"

    def __init__(self, ssh_alias: str | None = None):
        self.ssh_alias = ssh_alias

    def probe(self) -> ProbeResult:
        if not self.ssh_alias:
            return ProbeResult("ssh", {}, {"all": "未配置 ssh_alias，无法探测远端能力"})
        return ProbeResult(
            "ssh",
            {k: UNKNOWN for k in CAPABILITY_KEYS},
            {"all": f"未连接 {self.ssh_alias}，暂不宣称支持任一能力"},
        )

    def run(self, _spec: RunSpec) -> RunResult:
        raise UnsupportedError("ssh", "未实现远端执行；需先配置可用的 ssh_alias 并 doctor 探测")


class DockerExecutor(Executor):
    transport = "docker"

    def __init__(self, container: str | None = None):
        self.container = container

    def probe(self) -> ProbeResult:
        if not self.container:
            return ProbeResult("docker", {}, {"all": "未配置 container，无法探测容器内能力"})
        return ProbeResult(
            "docker",
            {k: UNKNOWN for k in CAPABILITY_KEYS},
            {"all": f"未启动容器 {self.container}，暂不宣称支持任一能力"},
        )

    def run(self, _spec: RunSpec) -> RunResult:
        raise UnsupportedError("docker", "未实现容器内执行；需先配置可用容器并 doctor 探测")


def build_executor(transport: str, ssh_alias: str | None = None, container: str | None = None) -> Executor:
    if transport == "local":
        return LocalExecutor()
    if transport == "ssh":
        return SshExecutor(ssh_alias)
    if transport == "docker":
        return DockerExecutor(container)
    raise ValueError(f"未知 transport: {transport}")