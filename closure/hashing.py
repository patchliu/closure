"""固定 JSON canonicalization 与哈希。

事件链、计划、提案、产物等持久标识都必须用同一个哈希函数。
规则（对应设计 25.3）：
- UTF-8 编码；
- 键排序；
- 无多余空白（compact separators）；
- 禁用 NaN/Infinity；
- 调用方负责排除事件自身 hash 字段。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS_HASH = "0" * 64


def canonical_json(data: Any) -> bytes:
    """把任意 JSON 兼容对象序列化为确定性的 UTF-8 字节串。"""
    return json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(data: Any) -> str:
    """对任意 JSON 兼容对象做规范化 JSON 后求 SHA-256。"""
    return hashlib.sha256(canonical_json(data)).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()