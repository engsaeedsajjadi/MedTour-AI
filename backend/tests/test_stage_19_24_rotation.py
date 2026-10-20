"""Stage 19.24 rotation handoff fail-closed unit checks (no live DB)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.staged_rotation_contract import prepare_rotation
from app.staged_tenant_epoch_control import EpochState
from test_stage_19_22_tenant_registry import config, TID_A, TID_B


class FakeReader:
    def __init__(self, state):
        self.state = state
        self.calls = 0

    def read(self, tenant_id):
        self.calls += 1
        assert tenant_id == TID_A
        if isinstance(self.state, Exception):
            raise self.state
        return self.state


def configs():
    old = config()
    return old, replace(old, database_password="replacement-" + "z"*48)


def test_preflight_only_accepts_exact_disabled_epoch():
    old, new = configs()
    reader = FakeReader(EpochState(2, False))
    handoff = prepare_rotation(
        reader=reader, old=old, replacement=new, disabled_generation=2,
    )
    assert handoff.tenant_id == TID_A
    assert handoff.database_role == old.database_role
    assert handoff.from_generation == 1
    assert handoff.to_generation == 3
    assert reader.calls == 1
    assert new.database_password not in repr(handoff)


@pytest.mark.parametrize("state", [
    EpochState(1, True), EpochState(1, False),
    EpochState(2, True), EpochState(3, False), None
])
def test_preflight_fails_when_tenant_not_disabled_at_expected_epoch(state):
    old, new = configs()
    with pytest.raises(LookupError):
        prepare_rotation(
            reader=FakeReader(state), old=old,
            replacement=new, disabled_generation=2,
        )


def test_preflight_refuses_disconnected_control_plane():
    old, new = configs()
    with pytest.raises(LookupError, match="unavailable"):
        prepare_rotation(
            reader=FakeReader(ConnectionError("Synthetic epoch unavailable")),
            old=old, replacement=new, disabled_generation=2,
        )


@pytest.mark.parametrize("change", [
    {"tenant_id": TID_B},
    {"database_role": "mt_clone_b"},
    {"slug": "other-tenant"},
    {"whatsapp_phone_id": "wa-other"},
    {"database_host": "foreign.example.invalid"},
    {"database_port": 5555},
    {"database_name": "another_clone"},
])
def test_preflight_blocks_identity_or_database_endpoint_switch(change):
    old, new = configs()
    with pytest.raises(ValueError):
        prepare_rotation(
            reader=FakeReader(EpochState(2, False)),
            old=old, replacement=replace(new, **change),
            disabled_generation=2,
        )


def test_preflight_refuses_reuse_of_old_password():
    old, _ = configs()
    with pytest.raises(ValueError, match="differ"):
        prepare_rotation(
            reader=FakeReader(EpochState(2, False)),
            old=old, replacement=old, disabled_generation=2,
        )


@pytest.mark.parametrize("generation", [0, 1, -1, True, "2"])
def test_preflight_rejects_invalid_generation(generation):
    old, new = configs()
    with pytest.raises(ValueError):
        prepare_rotation(
            reader=FakeReader(EpochState(2, False)),
            old=old, replacement=new, disabled_generation=generation,
        )
