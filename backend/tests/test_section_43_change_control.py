"""Section 43 synthetic change-control tests."""
import json,sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.section43_change_gate import assess,REQUIRED

def policy():
    return json.loads((ROOT/"docs/section43_change_control.json").read_text(encoding="utf-8"))

def test_empty_evidence_blocks_change():
    report=assess(policy(),{})
    assert not report["change_review_ready"]
    assert report["outstanding"]==list(REQUIRED)
    assert report["production_authorized"] is False

def test_unverified_or_malformed_evidence_not_accepted():
    partial={x:{"status":"passed","ref":"x"} for x in REQUIRED}
    assert not assess(policy(),partial)["change_review_ready"]
    partial={x:{"status":"passed","ref":"ci/checks/12345"} for x in REQUIRED}
    report=assess(policy(),partial)
    assert report["change_review_ready"]
    assert not report["production_authorized"]

def test_policy_tamper_fails_closed():
    p=policy()
    p["production_authorized"]=True
    with pytest.raises(ValueError):assess(p,{})
    p=policy()
    p["required_checks"]=[]
    with pytest.raises(ValueError):assess(p,{})
    with pytest.raises(ValueError):assess(policy(),{"bypass":True})
