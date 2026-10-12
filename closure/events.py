"""追加式事件日志与哈希链。

events.jsonl 是权威记录；state.json 是可重建快照（见 state.py）。
- 事件含递增 seq、schema 版本、前序事件哈希、计划/产物哈希（落在 payload 内）。
- 单写者锁保护提交；
- 写产物/结果先落临时文件，再追加事件并 fsync，最后原子更新快照（见 controller）。
"""
from __future__ import annotations

import fcntl
import os
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .hashing import GENESIS_HASH, sha256
from .schemas.enums import EventType

_EVENT_FIELDS = ("schema_version", "seq", "event_id", "type", "created_at", "previous_hash", "payload")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    seq: int
    event_id: str
    type: EventType
    created_at: str = Field(default_factory=_now)
    previous_hash: str
    payload: dict = Field(default_factory=dict)
    hash: str = ""

    def hash_digest(self) -> str:
        """规范化哈希，明确排除事件自身 hash 字段（设计 25.3）。"""
        raw = {k: getattr(self, k) for k in _EVENT_FIELDS}
        return sha256(raw)

    @classmethod
    def build(cls, type_: EventType, seq: int, previous_hash: str, payload: dict) -> "Event":
        e = cls(
            seq=seq,
            event_id=uuid.uuid4().hex,
            type=type_,
            previous_hash=previous_hash,
            payload=payload,
        )
        e.hash = e.hash_digest()
        return e


class EventStore:
    """追加式 JSONL 事件日志，带单写者文件锁与哈希链校验。"""

    def __init__(self, path: str):
        self.path = path
        self.lock_path = path + ".lock"

    def _lock(self):
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _unlock(self, fd: int):
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    def load(self) -> list[Event]:
        """读取所有完整事件行；忽略末尾不完整行（写入中断的残迹）。"""
        if not os.path.exists(self.path):
            return []
        events: list[Event] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(Event.model_validate_json(line))
                except ValidationError:
                    # 末尾截断行：停止读取，其余交由校验判断。
                    break
        return events

    def last(self) -> Event | None:
        events = self.load()
        return events[-1] if events else None

    def append(self, type_: EventType, payload: dict) -> Event:
        fd = self._lock()
        try:
            events = self.load()
            verify_chain(events)
            previous_hash = events[-1].hash if events else GENESIS_HASH
            seq = events[-1].seq + 1 if events else 1
            event = Event.build(type_, seq, previous_hash, payload)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(event.model_dump_json() + "\n")
                f.flush()
                os.fsync(f.fileno())
            return event
        finally:
            self._unlock(fd)

    def verify(self) -> list[Event]:
        events = self.load()
        verify_chain(events)
        return events


def verify_chain(events: list[Event]) -> None:
    """校验已提交事件链的序号与哈希链。"""
    prev = GENESIS_HASH
    for i, e in enumerate(events):
        if e.seq != i + 1:
            raise ValueError(f"事件序号断裂：期望 {i + 1}，实际 {e.seq}")
        if e.previous_hash != prev:
            raise ValueError(f"事件 {e.seq} 的前序哈希不匹配")
        if e.hash != e.hash_digest():
            raise ValueError(f"事件 {e.seq} 的内容哈希不匹配")
        prev = e.hash