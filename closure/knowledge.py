"""经验库与目标平台知识包（设计 17）。

首版用 Git 中 JSON 规则 + Markdown 案例：按错误指纹/Pass/SoC/版本区间检索。
经验分层：observation → validated_case → rule_candidate → active_rule。
AI 只能新增候选经验，不能把候选直接升为强制规则。
"""
from __future__ import annotations

import json
from pathlib import Path

from .schemas import Lesson, Recipe


class KnowledgeStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.lessons_dir = self.root / "lessons"
        self.recipes_dir = self.root / "recipes"
        self.packs_dir = self.root / "target-packs"
        for d in (self.lessons_dir, self.recipes_dir, self.packs_dir):
            d.mkdir(parents=True, exist_ok=True)

    def _write(self, directory: Path, id_: str, data: dict) -> Path:
        path = directory / f"{id_}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def add_lesson(self, lesson: Lesson) -> Path:
        return self._write(self.lessons_dir, lesson.id, lesson.model_dump())

    def load_lessons(self) -> list[Lesson]:
        return [
            Lesson.model_validate(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(self.lessons_dir.glob("*.json"))
        ]

    def match_lessons(self, signature: str) -> list[Lesson]:
        return [l for l in self.load_lessons() if l.signature == signature]

    def add_recipe(self, recipe: Recipe) -> Path:
        return self._write(self.recipes_dir, recipe.recipe_id, recipe.model_dump())

    def load_recipes(self) -> list[Recipe]:
        return [
            Recipe.model_validate(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(self.recipes_dir.glob("*.json"))
        ]

    def register_pack(self, pack_id: str, pack: dict) -> Path:
        return self._write(self.packs_dir, pack_id, pack)

    def load_packs(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for p in sorted(self.packs_dir.glob("*.json")):
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        return out


def build_dossier(
    case_id: str,
    candidate_id: str,
    proposal_hash: str | None,
    baseline_variant: str | None,
    before_ir_hash: str | None,
    after_ir_hash: str | None,
    device_validated: bool,
) -> Recipe:
    """从一次本地实验生成可审查的 compiler landing dossier（设计 13）。

    首版只输出 dossier 的结构与证据；是否关闭 inject 由 compiler 自动复现（T6）另行验证。
    """
    return Recipe(
        recipe_id=f"{candidate_id}-optimization",
        status="proposed",
        pattern="IR 注入候选（dossier 输入）",
        parameters={"case_id": case_id, "baseline_variant": baseline_variant},
        compiler_location={},
        positive_cases=[candidate_id],
        evidence=[
            *(f"proposal_hash:{proposal_hash}" if proposal_hash else []),
            *(f"before_ir:{before_ir_hash}" if before_ir_hash else []),
            *(f"after_ir:{after_ir_hash}" if after_ir_hash else []),
        ],
        expected_effect="需在关闭 inject 的编译器中复现（T6）" if not device_validated else "device_confirmed",
        reject_if=["无稳定模式", "收益不泛化", "IR 阶段信息不足"],
    )