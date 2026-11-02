"""Section 39: no phase can pass on missing or self-declared evidence."""
import json
import sys
from copy import deepcopy
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.section39_gates import evaluate

def plan():
    return json.loads((ROOT/"docs/section39_acceptance_gates.json").read_text(encoding="utf-8"))

def test_unverified_phases_are_blocked():
    r=evaluate(plan())
    assert r["all_gates_accepted"] is False
    assert r["production_authorized"] is False
    assert all(not phase["accepted"] for phase in r["phases"].values())

def test_unreviewed_or_unlinked_evidence_is_not_accepted():
    p=plan()
    p["evidence"]["G1"]={
        key:{"approved":True,"review_type":"self","evidence_ref":"review/12345678"}
        for key in p["phases"][0]["requirements"]}
    assert evaluate(p)["phases"]["G1"]["accepted"] is False
    p["evidence"]["G1"]={
        key:{"approved":True,"review_type":"independent","evidence_ref":"review/12345678"}
        for key in p["phases"][0]["requirements"]}
    r=evaluate(p)
    assert r["phases"]["G1"]["accepted"] is True
    assert r["phases"]["G2"]["accepted"] is False
    assert r["all_gates_accepted"] is False

def test_bad_schema_unknown_evidence_and_dependency_fail_closed():
    p=plan()
    p["schema_version"]=99
    with pytest.raises(ValueError):evaluate(p)
    p=plan()
    p["evidence"]["G1"]={"bypass":True}
    with pytest.raises(ValueError):evaluate(p)
    p=plan()
    p["phases"][1]["depends_on"]=["G5"]
    with pytest.raises(ValueError):evaluate(p)

def test_no_real_patient_data_stored_in_release_plan():
    raw=(ROOT/"docs/section39_acceptance_gates.json").read_text(encoding="utf-8")
    assert '"evidence": {}' in raw
    assert '"production_authorized": false' in raw
