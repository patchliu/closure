"""独立 evaluator（设计 12.1）。

reference、容差、输入生成器、计时器与验收策略由 evaluator 持管并哈希；
候选只能提交目标代码/IR，不能修改这些内容。评测协议与容差缺失时返回
EVALUATION_CONFIG_MISSING，不从示例偷拿默认值（设计 7.3）。
"""
from __future__ import annotations

from statistics import median
from typing import Any

from .hashing import sha256


def allclose(a: Any, b: Any, rtol: float, atol: float) -> bool:
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(allclose(x, y, rtol, atol) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    try:
        return abs(float(a) - float(b)) <= atol + rtol * max(abs(float(a)), abs(float(b)))
    except (TypeError, ValueError):
        return a == b


class Evaluator:
    """协议绑定：reference 哈希 + 容差 + 计时协议。"""

    def __init__(
        self,
        protocol: str,
        reference_hash: str | None,
        rtol: float,
        atol: float,
    ):
        self.protocol = protocol
        self.reference_hash = reference_hash
        self.rtol = rtol
        self.atol = atol

    def protocol_hash(self) -> str:
        return sha256(
            {
                "protocol": self.protocol,
                "reference_hash": self.reference_hash,
                "rtol": self.rtol,
                "atol": self.atol,
            }
        )

    def check_correctness(self, reference: Any, candidate: Any) -> bool:
        return allclose(candidate, reference, self.rtol, self.atol)

    @staticmethod
    def latency_ratio(candidate_median: float, baseline_median: float) -> float:
        """(baseline - candidate) / baseline，正值表示改善。"""
        if baseline_median <= 0:
            raise ValueError("baseline_median 必须为正")
        return (baseline_median - candidate_median) / baseline_median

    @staticmethod
    def median(samples: list[float]) -> float:
        return median(samples)