"""Section 44: synthetic checks for fail-closed final-acceptance policy."""
import json
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.section44_acceptance import assess

def manifest():
    return json.loads((ROOT/"docs/section44_final_acceptance.json").read_text(encoding="utf-8"))

def test_empty_evidence_never_authorizes_production():
    r=assess(manifest())
    assert r["required_evidence_count"]==15
    assert r["accepted_evidence_count"]==0
    assert r["final_acceptance_confirmed"] is False
    assert r["production_authorized"] is False

def test_self_asserted_evidence_rejected():
    doc=manifest()
    doc["evidence"]={x:{"approved":True,"review_type":"self",
                        "evidence_ref":"internal/check-123456"}
                     for x in doc["checks"]}
    r=assess(doc)
    assert r["accepted_evidence_count"]==0
    assert len(r["missing"])==15

def test_even_full_independent_refs_are_not_authorization():
    doc=manifest()
    doc["evidence"]={x:{"approved":True,"review_type":"independent",
                        "evidence_ref":"audit/reference-123456"}
                     for x in doc["checks"]}
    r=assess(doc)
    assert r["evidence_coverage_complete"] is True
    assert r["final_acceptance_confirmed"] is False
    assert r["production_authorized"] is False

def test_mutated_claim_and_unknown_check_rejected():
    doc=manifest()
    doc["production_authorized"]=True
    with pytest.raises(ValueError):assess(doc)
    doc=manifest()
    doc["evidence"]["unreviewed_check"]={"approved":True}
    with pytest.raises(ValueError):assess(doc)
