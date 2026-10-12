"""编译日志事实提取（设计 16）。

优先从 worker 结构化事件获得进程与退出信息；文本日志只识别工具内部事实。
关键字段无法识别时是 unknown，不把"没有找到错误"当成功。
"""
from __future__ import annotations

import re

from ..schemas.records import Fact

_LINE_RE = re.compile(r"^\[([A-Z_]+)\]\s*(.*)$")


def parse_compile_facts(text: str, source_artifact: str | None = None, parser_version: str = "compile-log-v1") -> list[Fact]:
    facts: list[Fact] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _LINE_RE.match(line.strip())
        if not m:
            continue
        tag, body = m.group(1), m.group(2)
        pairs = _parse_kv(body)
        facts.append(
            Fact(
                key=f"log:{tag.lower()}",
                value=pairs,
                verification="observed",
                source_artifact=source_artifact,
                parser_version=parser_version,
                offset=lineno,
            )
        )
    return facts


def _parse_kv(body: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for part in body.split():
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
        else:
            out.setdefault("token", part)
    return out