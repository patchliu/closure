"""worker：脱离会话执行一次 attempt，写结构化日志、心跳和结果包。

worker 拥有自己的执行日志、worker.json（身份 + 状态）与 result.json；
身份用 nonce + pid + 启动时间标识，防止 PID 复用后向错误进程发信号（不变量 5）。
"""
from __future__ import annotations

import json
import os
import time
import uuid

from pydantic import BaseModel, ConfigDict, Field

from .executors import Executor, RunSpec


class WorkerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    pid: int | None = None
    start_time: float = Field(default_factory=time.time)
    nonce: str = Field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "pending"
    exit_code: int | None = None
    signal: str | None = None


class WorkerIdentityError(RuntimeError):
    pass


def write_record(path: str, record: WorkerRecord) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def read_record(path: str) -> WorkerRecord | None:
    if not os.path.exists(path):
        return None
    return WorkerRecord.model_validate_json(open(path, encoding="utf-8").read())


def pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        # ESRCH（进程不存在）与 EPERM（存在但属他人）之外均视为不可用。
        return False


def verify_identity(record: WorkerRecord, record_path: str) -> WorkerRecord:
    """以磁盘上的 worker.json 为权威；nonce 或 pid 不一致即拒绝。"""
    disk = read_record(record_path)
    if disk is None:
        raise WorkerIdentityError(f"worker 身份文件缺失: {record_path}")
    if disk.nonce != record.nonce:
        raise WorkerIdentityError("worker nonce 不匹配，拒绝操作（可能为 PID 复用）")
    return disk


def launch_worker(executor: Executor, spec: RunSpec, attempt_id: str, work_dir: str) -> WorkerRecord:
    """执行一次 attempt：写身份 → 运行 → 写结果 → 更新身份状态。"""
    os.makedirs(work_dir, exist_ok=True)
    record_path = os.path.join(work_dir, "worker.json")
    spec.nonce = spec.nonce or uuid.uuid4().hex
    record = WorkerRecord(attempt_id=attempt_id, nonce=spec.nonce, pid=os.getpid(), status="running")
    write_record(record_path, record)

    result = executor.run(spec)

    record.status = "done" if result.succeeded else "failed"
    record.exit_code = result.exit_code
    record.signal = result.signal
    write_record(record_path, record)

    result_path = os.path.join(work_dir, "result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "attempt_id": attempt_id,
                    "exit_code": result.exit_code,
                    "signal": result.signal,
                    "timed_out": result.timed_out,
                    "duration_seconds": result.duration_seconds,
                }
            )
            + "\n"
        )
    return record