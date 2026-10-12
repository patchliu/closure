import os

import pytest

from closure.events import EventStore
from closure.schemas.enums import EventType, StageStatus
from closure.state import StateStore, reduce


def test_append_and_verify_chain(tmp_path):
    store = EventStore(str(tmp_path / "events.jsonl"))
    e1 = store.append(EventType.CASE_CREATED, {"case_id": "c1", "budget_limits": {"max_candidates": 5}})
    e2 = store.append(EventType.STAGE_STARTED, {"stage": "capture"})
    events = store.verify()
    assert [e.seq for e in events] == [1, 2]
    assert e2.previous_hash == e1.hash
    assert e1.hash == e1.hash_digest()


def test_reducer_and_snapshot_rebuild(tmp_path):
    store = EventStore(str(tmp_path / "events.jsonl"))
    store.append(EventType.CASE_CREATED, {"case_id": "c1", "budget_limits": {"max_candidates": 5}})
    store.append(EventType.CANDIDATE_REGISTERED, {"candidate": {"candidate_id": "v000", "status": "proposed"}, "is_baseline": True})
    store.append(EventType.CANDIDATE_PROMOTED, {"candidate_id": "v000"})
    store.append(EventType.STAGE_RESULT, {"stage": "capture", "status": "succeeded"})

    state = reduce(store.load())
    assert state.case_id == "c1"
    assert state.baseline_variant_id == "v000"
    assert state.incumbent_id == "v000"
    assert state.stages["capture"] == StageStatus.SUCCEEDED.value
    assert state.seq == 4


def test_snapshot_deleted_then_rebuilt(tmp_path):
    store = StateStore(str(tmp_path / "events.jsonl"), str(tmp_path / "state.json"))
    store.events.append(EventType.CASE_CREATED, {"case_id": "c1", "budget_limits": {}})
    store.events.append(EventType.STAGE_STARTED, {"stage": "compile"})
    state = store.replay()
    store.write_snapshot(state)
    assert os.path.exists(store.state_path)
    os.remove(store.state_path)
    rebuilt = store.replay()
    assert rebuilt.case_id == "c1"
    assert rebuilt.stages["compile"] == StageStatus.RUNNING.value


def test_truncated_tail_line_ignored(tmp_path):
    path = tmp_path / "events.jsonl"
    store = EventStore(str(path))
    store.append(EventType.CASE_CREATED, {"case_id": "c1", "budget_limits": {}})
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"schema_version":1,"seq":2,"event_id":"x","type')  # 不完整行
    events = store.load()
    assert len(events) == 1


def test_chain_tamper_detected(tmp_path):
    path = tmp_path / "events.jsonl"
    store = EventStore(str(path))
    store.append(EventType.CASE_CREATED, {"case_id": "c1", "budget_limits": {}})
    # 篡改 payload
    lines = path.read_text().strip().split("\n")
    import json

    obj = json.loads(lines[0])
    obj["payload"] = {"case_id": "hacked"}
    path.write_text(json.dumps(obj) + "\n")
    with pytest.raises(ValueError):
        store.verify()