import pytest

from closure.templates import CASE_TOML, HARNESS_PY, REFERENCE_PY


@pytest.fixture
def case_dir(tmp_path):
    (tmp_path / "input").mkdir(parents=True)
    (tmp_path / "profiles").mkdir(parents=True)
    (tmp_path / "case.toml").write_text(CASE_TOML.format(case_id="example-kernel"), encoding="utf-8")
    (tmp_path / "input" / "reference.py").write_text(REFERENCE_PY, encoding="utf-8")
    (tmp_path / "input" / "harness.py").write_text(HARNESS_PY, encoding="utf-8")
    return tmp_path


def propose_variant(pid="p001", parent="v000", baseline="v000", change=None):
    return {
        "proposal_id": pid,
        "packet_hash": "__stub__",
        "expected_state_seq": 0,
        "action": "propose_variant",
        "payload": {
            "baseline": baseline,
            "parent_variant": parent,
            "change_kind": "ir_patch",
            "hypothesis": "test hypothesis",
            "change": change if change is not None else {"patch_artifact": "proposal:patch-1"},
        },
    }