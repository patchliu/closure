import pytest
from pydantic import ValidationError

from closure.schemas import (
    ActionEnvelope,
    CaseConfig,
    ChangeKind,
    Profile,
    Runtime,
    Transport,
)


def make_case(**over) -> dict:
    data = {
        "case_id": "example-kernel",
        "entry": "input/harness.py",
        "kernel_symbol": "target_kernel",
        "seed": 20261012,
        "roles": {
            "compile": "server-compile",
            "simulate": "mac-sim",
            "validate": "board",
            "benchmark": "board",
        },
        "correctness": {
            "reference": "input/reference.py",
            "input_mode": "initialized",
            "rtol": 0.001,
            "atol": 0.001,
        },
    }
    data.update(over)
    return data


def test_case_config_parses():
    c = CaseConfig.model_validate(make_case())
    assert c.case_id == "example-kernel"
    assert c.budget.max_candidates == 5


def test_case_config_rejects_unknown_field():
    with pytest.raises(ValidationError):
        CaseConfig.model_validate(make_case(bogus=1))


def test_case_config_rejects_bad_enum():
    with pytest.raises(ValidationError):
        CaseConfig.model_validate(make_case(search={"mode": "nope"}))


def test_profile_parses():
    p = Profile.model_validate(
        {
            "name": "mac-sim",
            "transport": "local",
            "runtime": "docker",
            "roles": ["compile", "simulate"],
        }
    )
    assert p.transport == Transport.LOCAL
    assert p.runtime == Runtime.DOCKER


def test_action_envelope_propose_variant():
    a = ActionEnvelope.model_validate(
        {
            "proposal_id": "p003",
            "packet_hash": "ab",
            "expected_state_seq": 1,
            "action": "propose_variant",
            "payload": {
                "baseline": "v000",
                "parent_variant": "v000",
                "change_kind": "ir_patch",
                "hypothesis": "test",
                "change": {"patch_artifact": "proposal:patch-003"},
            },
        }
    )
    assert a.payload.change_kind == ChangeKind.IR_PATCH


def test_action_envelope_rejects_wrong_payload():
    with pytest.raises(ValidationError):
        ActionEnvelope.model_validate(
            {
                "proposal_id": "p1",
                "packet_hash": "ab",
                "expected_state_seq": 1,
                "action": "inspect",
                "payload": {"baseline": "v000", "parent_variant": "v000"},
            }
        )


def test_action_envelope_rejects_unknown_action_field():
    with pytest.raises(ValidationError):
        ActionEnvelope.model_validate(
            {
                "proposal_id": "p1",
                "packet_hash": "ab",
                "expected_state_seq": 1,
                "action": "inspect",
                "payload": {"artifact_id": "a", "purpose": "x", "bogus": 1},
            }
        )


def test_action_envelope_rejects_command_field():
    with pytest.raises(ValidationError):
        ActionEnvelope.model_validate(
            {
                "proposal_id": "p1",
                "packet_hash": "ab",
                "expected_state_seq": 1,
                "action": "inspect",
                "payload": {"artifact_id": "a", "purpose": "x"},
                "command": "rm -rf /",
            }
        )