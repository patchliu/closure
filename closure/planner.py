"""AI 决策接口的 planner：固定 JSON 输入输出（设计 7）。

首版提供 ReplayPlanner 读取预录 JSON，从而无需模型服务即可测试控制器。
真实模型适配器后续实现，只需返回 ActionEnvelope。
"""
from __future__ import annotations

from typing import Protocol

from .schemas import ActionEnvelope, DecisionPacket


class Planner(Protocol):
    def decide(self, packet: DecisionPacket) -> ActionEnvelope | None: ...


class ReplayPlanner:
    """按顺序重放预录的 ActionEnvelope；重放身份字段并覆盖为当前值。

    重放的是动作语义（action/payload/proposal_id），packet_hash 与
    expected_state_seq 必须绑定当前 decision packet，避免把旧状态当成新提议。
    """

    def __init__(self, proposals: list[dict]):
        self._queue = list(proposals)

    def __len__(self) -> int:
        return len(self._queue)

    def decide(self, packet: DecisionPacket) -> ActionEnvelope | None:
        if not self._queue:
            return None
        raw = dict(self._queue.pop(0))
        env = ActionEnvelope.model_validate(raw)
        return env.model_copy(
            update={"packet_hash": packet.packet_hash, "expected_state_seq": packet.state_seq}
        )


class NullPlanner:
    """无提案来源时返回 None，控制器据此进入 blocked 并落盘检查点。"""

    def decide(self, packet: DecisionPacket) -> ActionEnvelope | None:  # noqa: ARG002
        return None