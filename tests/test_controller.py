import pytest

from closure.controller import Controller
from closure.planner import ReplayPlanner
from closure.state import StateStore
from closure.templates import CASE_TOML, HARNESS_PY, REFERENCE_PY


@pytest.fixture
def case_dir(tmp_path):
    (tmp_path / "input").mkdir(parents=True)
    (tmp_path / "profiles").mkdir(parents=True)
    (tmp_path / "case.toml").write_text(CASE_TOML.format(case_id="example-kernel"), encoding="utf-8")
    (tmp_path / "input" / "reference.py").write_text(REFERENCE_PY, encoding="utf-8")
    (tmp_path / "input" / "harness.py").write_text(HARNESS_PY, encoding="utf-8")
    return tmp_path


def propose_variant(pid="p001", parent="v000", baseline="v000"):
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
            "change": {"patch_artifact": "proposal:patch-1"},
        },
    }


def run_until_terminal(controller: Controller, max_steps=20):
    results = []
    for _ in range(max_steps):
        r = controller.run_step()
        results.append(r)
        if r.status in ("stopped", "done"):
            return results
    return results


def test_baseline_registered_and_promoted(case_dir):
    controller = Controller(case_dir, planner=ReplayPlanner([]))
    run_until_terminal(controller)
    state = controller.store.replay()
    assert state.baseline_variant_id == "v000"
    assert state.incumbent_id == "v000"
    # planner 耗尽 -> 停止，理由为等待外部输入
    assert state.run_status == "stopped"
    assert state.stop_reason == "waiting_for_external_input"


def test_proposal_promotes_improved_candidate(case_dir):
    controller = Controller(case_dir, planner=ReplayPlanner([propose_variant()]))
    run_until_terminal(controller)
    state = controller.store.replay()
    assert "v001" in state.candidates
    assert state.incumbent_id == "v001"
    assert state.candidates["v001"]["status"] == "confirmed"
    obj = state.candidates["v001"]["objective"]
    assert obj["latency_ratio_to_baseline"] > 0


def test_failed_candidate_does_not_replace_incumbent(case_dir):
    # 无 proposal 场景下 baseline 即 incumbent；这里验证 CSP 不变式：
    # 错误 candidate 状态绝不改变 incumbent。
    controller = Controller(case_dir, planner=ReplayPlanner([]))
    run_until_terminal(controller)
    state = controller.store.replay()
    assert state.incumbent_id == "v000"
    # 直接注入一个被拒绝候选（正确性失败）不应影响 incumbent。
    from closure.schemas.enums import EventType

    controller.store.events.append(
        EventType.CANDIDATE_REGISTERED,
        {"candidate": {"candidate_id": "v999", "status": "proposed", "baseline_variant": "v000"}, "is_baseline": False},
    )
    controller.store.events.append(EventType.CANDIDATE_REJECTED, {"candidate_id": "v999", "reason": "CORRECTNESS_FAILED"})
    state2 = controller.store.replay()
    assert state2.incumbent_id == "v000"


def test_state_snapshot_deleted_rebuilt_after_run(case_dir):
    controller = Controller(case_dir, planner=ReplayPlanner([propose_variant()]))
    run_until_terminal(controller)
    store = StateStore(str(case_dir / "events.jsonl"), str(case_dir / "state.json"))
    (case_dir / "state.json").unlink()
    state = store.replay()
    assert state.incumbent_id == "v001"
    assert state.candidates["v001"]["status"] == "confirmed"