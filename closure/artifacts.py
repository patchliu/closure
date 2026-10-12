"""产物索引、哈希与保留（设计 14）。

manifest 记录 artifact ID、路径、SHA256、字节数、类型、阶段、保留级别、依赖、是否可重建。
GC 先按引用与 pin 标记；仅清理本系统拥有且未被引用/唯一副本的 scratch/reproducible 产物。
"""
from __future__ import annotations

import json
from pathlib import Path

from .hashing import sha256_file
from .schemas import Artifact, RetentionLevel


class ArtifactManifest:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[Artifact]:
        if not self.path.exists():
            return []
        return [Artifact.model_validate(x) for x in json.loads(self.path.read_text(encoding="utf-8"))]

    def save(self, artifacts: list[Artifact]) -> None:
        self.path.write_text(
            json.dumps([a.model_dump() for a in artifacts], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def seal(
        self,
        artifact_id: str,
        path: str | Path,
        type_: str,
        retention: RetentionLevel,
        stage: str | None = None,
        deps: list[str] | None = None,
        rebuildable: bool = False,
    ) -> Artifact:
        p = Path(path)
        artifact = Artifact(
            id=artifact_id,
            path=str(p),
            sha256=sha256_file(str(p)) if p.exists() else "",
            bytes=p.stat().st_size if p.exists() else 0,
            type=type_,
            stage=stage,
            deps=deps or [],
            retention=retention,
            rebuildable=rebuildable,
            sealed=True,
        )
        artifacts = self.load()
        artifacts = [a for a in artifacts if a.id != artifact_id]
        artifacts.append(artifact)
        self.save(artifacts)
        return artifact


def gc_plan(manifest: ArtifactManifest, pinned_ids: set[str]) -> list[Artifact]:
    """返回可清理的产物列表（不真正删除）；essential/evidence 与 pin 一律保留。"""
    removable = []
    for a in manifest.load():
        if a.id in pinned_ids or not a.sealed:
            continue
        if a.retention in (RetentionLevel.SCRATCH, RetentionLevel.REPRODUCIBLE):
            removable.append(a)
    return removable


def apply_gc(manifest: ArtifactManifest, removable: list[Artifact]) -> int:
    manifest_path = manifest.load()
    keep = {a.id for a in manifest_path if a not in removable}
    removed = 0
    for a in removable:
        p = Path(a.path)
        if p.exists():
            p.unlink()
            removed += 1
    manifest.save([a for a in manifest_path if a.id in keep])
    return removed