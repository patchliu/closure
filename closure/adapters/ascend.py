"""Ascend 适配器：编译捕获、IR dump/inject、msprof、板上 runner。

首版在不具备真机工具时返回明确的 unsupported/blocked，不伪造能力。
argv 构造逻辑可单测；实际执行依赖 executor 与已探测能力。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Any

from ..hashing import sha256_bytes
from ..schemas.enums import Capability, CheckResult

DUMP_PRINT_FLAGS = [
    "--mlir-print-ir-before-all",
    "--mlir-print-ir-after-all",
    "--mlir-disable-threading",
]


@dataclass
class CapabilityMatrix:
    compile: str = Capability.UNSUPPORTED.value
    inject: str = Capability.UNSUPPORTED.value
    full_dump: str = Capability.UNSUPPORTED.value
    simulate: str = Capability.UNSUPPORTED.value
    graceful_stop: str = Capability.UNSUPPORTED.value
    correctness: str = Capability.UNSUPPORTED.value
    benchmark: str = Capability.UNSUPPORTED.value
    reasons: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "compile": self.compile,
            "inject": self.inject,
            "full_dump": self.full_dump,
            "simulate": self.simulate,
            "graceful_stop": self.graceful_stop,
            "correctness": self.correctness,
            "benchmark": self.benchmark,
            "reasons": dict(self.reasons),
        }


class AscendAdapter:
    """当前机器 Ascend 工具链的探测与命令构造。

    探测关键词（不安装、不改全局环境）：
    bishengir-compile / bishengir-opt / msprof / npu-smi / python。
    """

    _KNOWN_COMPILERS = ("bishengir-compile", "bishengir-opt", "hivmc")
    _KNOWN_TOOLS = ("msprof", "npu-smi")

    def probe(self) -> CapabilityMatrix:
        m = CapabilityMatrix(reasons={})
        found_compiler = any(shutil.which(c) for c in self._KNOWN_COMPILERS)
        if found_compiler:
            m.compile = Capability.UNKNOWN.value
            m.reasons["compile"] = "发现编译器可执行名，但未验证注入/导出能力"
        else:
            m.reasons["compile"] = "未在 PATH 找到 bishengir-compile/bishengir-opt"
        if shutil.which("msprof"):
            m.simulate = Capability.UNKNOWN.value
            m.reasons["simulate"] = "发现 msprof，但未做目标版本烟测"
        else:
            m.reasons["simulate"] = "未在 PATH 找到 msprof"
        for k in ("inject", "full_dump", "graceful_stop", "correctness", "benchmark"):
            m.reasons[k] = "需绑定具体 profile 与工具版本后探测"
        return m

    def capture_compile_argv(
        self,
        entry: str,
        kernel_symbol: str,
        soc: str | None = None,
        dtype: str | None = None,
        shape: list[int] | None = None,
        grid: list[int] | None = None,
        extra: list[str] | None = None,
    ) -> list[str]:
        """构造/捕获编译器 argv（真实 argv 需现场重放，这里给出确定性骨架）。"""
        argv = ["bishengir-compile", entry]
        if kernel_symbol:
            argv += ["--kernel", kernel_symbol]
        if soc:
            argv += ["--soc", soc]
        if dtype:
            argv += ["--dtype", dtype]
        if shape:
            argv += ["--shape", ",".join(str(s) for s in shape)]
        if grid:
            argv += ["--grid", ",".join(str(g) for g in grid)]
        if extra:
            argv += extra
        return argv

    def build_dump_argv(self, base_argv: list[str]) -> list[str]:
        """重放性全量 Pass dump：保留语义参数，替换输出，追加 before/after-all。"""
        argv = list(base_argv)
        # 移去与全量打印冲突的过滤选项
        argv = [a for a in argv if not a.startswith("--mlir-print-ir-after=")]
        return argv + DUMP_PRINT_FLAGS

    def inject_cache_key(self, ir_content: bytes) -> str:
        """IR 内容 SHA256 进入缓存键，避免缓存键未含 IR 内容而不生效。"""
        return sha256_bytes(ir_content)

    def build_inject_argv(self, base_argv: list[str], inject_path: str, cache_root: str, ir_content: bytes) -> list[str]:
        key = self.inject_cache_key(ir_content)
        return list(base_argv) + [
            "--inject-ir-from-file",
            inject_path,
            "--inject-cache-root",
            f"{cache_root}/{key}",
        ]

    def validate_injection(self, requested: bool, argv_has_path: bool, post_pass_match: bool) -> dict[str, str]:
        """注入生效校验：实际 argv 含路径 + 注入后结构匹配。二者缺一不可。"""
        ok = requested and argv_has_path and post_pass_match
        return {
            "requested": _bool(requested),
            "argv_has_path": _bool(argv_has_path),
            "post_pass_match": _bool(post_pass_match),
            "result": CheckResult.PASS.value if ok else CheckResult.FAIL.value,
        }


def _bool(v: bool) -> str:
    return "yes" if v else "no"