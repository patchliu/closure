"""状态导出/导入（设计 15）。

Git 管小状态；SSH+rsync 管大文件。这里实现离线 bundle 导出/导入 + 哈希校验。
首版不迁移活进程内存；导出的是已封存/权威事件与小文件。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .hashing import sha256_file

ESSENTIAL_FILES = ["case.toml", "events.jsonl", "state.json", "report.md"]
ESSENTIAL_DIRS = ["profiles", "input", "analysis", "knowledge"]


def export_bundle(case_dir: str | Path, out_dir: str | Path, level: str = "essentials") -> dict:
    root = Path(case_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    files: list[Path] = [root / f for f in ESSENTIAL_FILES if (root / f).exists()]
    for d in ESSENTIAL_DIRS:
        if (root / d).exists():
            files += [p for p in (root / d).rglob("*") if p.is_file()]
    if level == "full" and (root / "runs").exists():
        files += [p for p in (root / "runs").rglob("*") if p.is_file()]

    manifest = {}
    for p in files:
        rel = p.relative_to(root)
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        manifest[str(rel)] = sha256_file(str(dest))

    manifest_path = out / "bundle-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["bundle-manifest.json"] = sha256_file(str(manifest_path))
    return manifest


def import_bundle(bundle_dir: str | Path, target_dir: str | Path, overwrite: bool = False) -> list[str]:
    src = Path(bundle_dir)
    dst = Path(target_dir)
    manifest_path = src / "bundle-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("缺少 bundle-manifest.json")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for rel, expected in manifest.items():
        if rel == "bundle-manifest.json":
            if sha256_file(str(manifest_path)) != expected:
                problems.append(f"manifest 自身哈希不匹配: {rel}")
            continue
        sp = src / rel
        dp = dst / rel
        if sp.exists() and sha256_file(str(sp)) != expected:
            problems.append(f"哈希不匹配: {rel}")
            continue
        if dp.exists() and not overwrite:
            continue
        dp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sp, dp)
    return problems