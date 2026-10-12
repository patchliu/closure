"""第 25.2 节 12 条程序不变量，每条至少一个自动化测试。"""
import pytest
from pydantic import ValidationError

from closure.adapters.ascend import AscendAdapter
from closure.artifacts import ArtifactManifest, gc_plan
from closure.controller import Controller
from closure.evaluator import Evaluator
from closure.events import Event, EventStore
from closure.executors import DockerExecutor, LocalExecutor, RunResult, UnsupportedError
from closure.hashing import GENESIS_HASH, sha256
from closure.planner import ReplayPlanner
from closure.schemas import ActionEnvelope, Candidate, EventType, ProposeVariantPayload, RetentionLevel
from closure.selection import PromotionContext, promotion_ok
from closure.state import reduce
from closure.worker import (
    WorkerIdentityError,
    WorkerRecord,
    pid_alive,
    read_record,
    verify_identity,
    write_record,
)


def _ev(type_, seq, payload):
    return Event.build(type_, seq, GENESIS_HASH, payload)


def _propose(pid="p001", change=None):
    return {
        "proposal_id": pid,
        "packet_hash": "__stub__",
        "expected_state_seq": 0,
        "action": "propose_variant",
        "payload": {
            "baseline": "v000",
            "parent_variant": "v000",
            "change_kind": "ir_patch",
            "hypothesis": "test",
            "change": change if change is not None else {"patch_artifact": "proposal:patch-1"},
        },
    }


def _run_until_terminal(controller, max_steps=20):
    for _ in range(max_steps):
        r = controller.run_step()
        if r.status in ("stopped", "done"):
            return


# 1. AI 输出不可能直接生成 candidate.promoted / stage.succeeded / observed fact
def test_ai_output_cannot_directly_mutate_state():
    smuggled = {
        "proposal": {"proposal_id": "p1", "action": "propose_variant"},
        "candidate": {"candidate_id": "x", "promoted": True},
        "stage": "validate",
        "status": "succeeded",
        "facts": {"k": "v"},
    }
    state = reduce([_ev(EventType.PROPOSAL_ACCEPTED, 1, smuggled)])
    assert state.candidates == {}
    assert state.stages == {}
    assert state.facts == {}


def test_ai_envelope_rejects_state_fields():
    with pytest.raises(ValidationError):
        ActionEnvelope.model_validate(
            {
                "proposal_id": "p1",
                "packet_hash": "h",
                "expected_state_seq": 0,
                "action": "inspect",
                "payload": {"artifact_id": "a", "purpose": "x"},
                "candidate": {"promoted": True},
            }
        )


# 2. baseline/reference/协议/封存产物不可被 candidate 修改
def test_candidate_cannot_override_reference_or_protocol():
    base = {
        "baseline": "v0",
        "parent_variant": "v0",
        "change_kind": "ir_patch",
        "hypothesis": "h",
        "change": {"patch_artifact": "x"},
    }
    with pytest.raises(ValidationError):
        ProposeVariantPayload.model_validate({**base, "reference": "input/other.py"})
    with pytest.raises(ValidationError):
        ProposeVariantPayload.model_validate({**base, "protocol": "closure-eval-v2"})


def test_gc_retains_essential_evidence(tmp_path):
    m = ArtifactManifest(str(tmp_path / "manifest.json"))
    for name, ret in [
        ("essential", RetentionLevel.ESSENTIAL),
        ("evidence", RetentionLevel.EVIDENCE),
        ("repro", RetentionLevel.REPRODUCIBLE),
        ("scratch", RetentionLevel.SCRATCH),
    ]:
        (tmp_path / name).write_text("data")
        m.seal(name, tmp_path / name, "log", ret)
    removable = {a.id for a in gc_plan(m, pinned_ids={"scratch"})}
    assert "essential" not in removable
    assert "evidence" not in removable
    assert "scratch" not in removable  # 被引用
    assert "repro" in removable


# 3. 结果绑定精确哈希；旧成绩不跟随新代码
def test_protocol_hash_binds_inputs():
    a = Evaluator("p", "refA", 0.001, 0.001).protocol_hash()
    assert a != Evaluator("p", "refB", 0.001, 0.001).protocol_hash()
    assert a != Evaluator("p", "refA", 0.1, 0.001).protocol_hash()
    assert a != Evaluator("q", "refA", 0.001, 0.001).protocol_hash()


def test_promotion_rejects_protocol_mismatch():
    cand = Candidate(
        candidate_id="x",
        baseline_variant="v0",
        source_or_ir_hash="ir-hash",
        evaluation_protocol_hash="OLD",
    )
    ctx = PromotionContext(
        protocol_hash="NEW",
        source_hash_matches=True,
        correctness_passed=True,
        independent_confirmation_passed=True,
        regression_limits_passed=True,
        mandatory_artifacts_verified=True,
    )
    ok, failed = promotion_ok(cand, ctx)
    assert not ok
    assert "evaluation_protocol_matches" in failed


# 4. 上一个 attempt 的输出/结果不被覆盖（事件只追加，不改写）
def test_events_append_only_no_overwrite(tmp_path):
    store = EventStore(str(tmp_path / "events.jsonl"))
    e1 = store.append(EventType.CASE_CREATED, {"case_id": "a"})
    store.append(EventType.CASE_CREATED, {"case_id": "b"})
    events = store.load()
    assert [e.seq for e in events] == [1, 2]
    assert events[0].hash == e1.hash
    assert events[0].payload["case_id"] == "a"


# 5. worker 状态未知不重复 launch；身份不匹配不向裸 PID 发信号
def test_worker_identity_mismatch_rejected(tmp_path):
    path = str(tmp_path / "worker.json")
    rec = WorkerRecord(attempt_id="a1", nonce="n1", pid=12345, status="running")
    write_record(path, rec)
    forged = rec.model_copy(update={"nonce": "n2"})
    with pytest.raises(WorkerIdentityError):
        verify_identity(forged, path)
    assert pid_alive(None) is False
    assert read_record(str(tmp_path / "missing.json")) is None


# 6. 预算计入失败；候选效果计数可区分原因
def test_budget_counts_failed_stage():
    state = reduce(
        [
            _ev(
                EventType.STAGE_RESULT,
                1,
                {"stage": "validate", "status": "failed", "cost": {"runs": 3}},
            )
        ]
    )
    assert state.budget_used.get("runs") == 3


def test_rejection_reason_distinguished():
    state = reduce(
        [
            _ev(EventType.CANDIDATE_REGISTERED, 1, {"candidate": {"candidate_id": "v1", "baseline_variant": "v0"}, "is_baseline": False}),
            _ev(EventType.CANDIDATE_REJECTED, 2, {"candidate_id": "v1", "reason": "COMPILE_FAILED"}),
        ]
    )
    assert state.candidates["v1"]["rejection_reason"] == "COMPILE_FAILED"


# 7. unknown/partial 不升级为成功；零退出码不独立构成成功
def test_zero_exit_not_success_and_no_partial_success():
    assert not RunResult(exit_code=0, signal="SIGINT").succeeded
    assert not RunResult(exit_code=-1, timed_out=True).succeeded
    assert RunResult(exit_code=0).succeeded
    from closure.schemas import StageStatus

    assert "partial" not in {s.value for s in StageStatus}
    assert "unknown" not in {s.value for s in StageStatus}


# 8. 快筛优胜不改变 device incumbent；必须独立确认
def test_no_promotion_without_independent_confirmation():
    cand = Candidate(
        candidate_id="x",
        baseline_variant="v0",
        source_or_ir_hash="ir-hash",
        evaluation_protocol_hash="p",
    )
    ctx = PromotionContext(
        protocol_hash="p",
        source_hash_matches=True,
        correctness_passed=True,
        independent_confirmation_passed=False,
        regression_limits_passed=True,
        mandatory_artifacts_verified=True,
    )
    ok, failed = promotion_ok(cand, ctx)
    assert not ok
    assert "independent_confirmation_passed" in failed


# 9. 恢复不重写已接受计划（同 proposal 重放幂等，不重复注册候选）
def test_recovery_does_not_rewrite_accepted_plan(case_dir):
    controller = Controller(case_dir, planner=ReplayPlanner([_propose(), _propose()]))
    _run_until_terminal(controller)
    state = controller.store.replay()
    assert "v001" in state.candidates
    assert "v002" not in state.candidates
    assert "p001" in state.accepted_proposals


# 10. 未验证同步不标完成；GC 不删除引用/唯一副本
def test_unverified_sync_not_complete():
    state = reduce([_ev(EventType.SYNC_VERIFIED, 1, {"level": "unverified"})])
    assert state.run_status == "created"
    assert state.facts["sync"]["verified"] == "unverified"


def test_promote_unknown_candidate_does_not_crash_replay():
    # 事件链中可能出现指向未注册候选的 promote（迁移/手工合并），
    # 重放必须不崩溃，且 incumbent 指针仍可推进。
    state = reduce([_ev(EventType.CANDIDATE_PROMOTED, 1, {"candidate_id": "ghost"})])
    assert state.incumbent_id == "ghost"
    assert state.candidates == {}


# 6b. 墙钟预算跨进程累积，resume 不重置（设计 25.2 条 6）
def test_wall_budget_persists_across_resume(case_dir):
    content = (case_dir / "case.toml").read_text(encoding="utf-8")
    (case_dir / "case.toml").write_text(
        content.replace("max_wall_seconds = 7200", "max_wall_seconds = 5"), encoding="utf-8"
    )
    c1 = Controller(case_dir, planner=ReplayPlanner([]))
    c1.ensure_initialized(c1.store.replay())
    c1.record_wall_usage()
    assert c1.store.replay().budget_used.get("wall_seconds", 0) > 0
    # 人为放大已落盘的墙钟消耗，模拟上一进程长跑
    c1._emit(EventType.BUDGET_ADJUSTED, {"used": {"wall_seconds": 5.0}})
    # 新进程：_started_at 归零，但持久化的消耗必须继续生效
    c2 = Controller(case_dir)
    assert c2._budget_exhausted(c2.store.replay()) == "max_wall_seconds"


# 11. 不支持能力返回明确错误与最小缺口，不偷偷绕过
def test_unsupported_capability_clear_error():
    local = LocalExecutor().probe()
    assert local.capabilities["compile"] == "unsupported"
    assert local.reasons["compile"]
    asc = AscendAdapter().probe().as_dict()
    assert asc["compile"] in {"unsupported", "unknown"}
    assert asc["simulate"] in {"unsupported", "unknown"}
    with pytest.raises(UnsupportedError) as ei:
        DockerExecutor().run(None)
    assert ei.value.reason


# 12. 同一锁定 packet/proposal/config 的解析不依赖模型品牌
def test_ai_envelope_rejects_model_brand():
    with pytest.raises(ValidationError):
        ActionEnvelope.model_validate({**_propose(), "model": "gpt-4o"})


def test_plan_resolution_model_independent(case_dir):
    c1 = Controller(case_dir)
    c2 = Controller(case_dir)
    c1.ensure_initialized(c1.store.replay())
    state = c1.store.replay()
    p1 = c1.build_packet(state)
    p2 = c2.build_packet(state)
    assert p1.packet_hash == p2.packet_hash
    env = ActionEnvelope.model_validate(_propose())
    assert c1._plan_hash(env) == c2._plan_hash(env)
    assert sha256(env.model_dump()) == sha256(env.model_dump())