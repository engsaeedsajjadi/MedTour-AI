"""Section 43: fail-closed change/release evidence manifest validator.

This is a *process gate*, not an assertion that security, clinical or
production signoff exists. Never store secrets or patient data in evidence.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/"docs/section43_change_control.json"
REQUIRED=("scope_review","backend_tests","frontend_build","migration_review",
          "tenant_security_review","privacy_review","rollback_plan")

def assess(policy:dict, evidence:dict)->dict:
    if policy.get("version")!=1 or policy.get("production_authorized") is not False:
        raise ValueError("Invalid execution policy")
    if policy.get("required_checks")!=list(REQUIRED):
        raise ValueError("Change policy mismatch")
    if not isinstance(evidence,dict) or set(evidence)-set(REQUIRED):
        raise ValueError("Unrecognized evidence")
    outstanding=[]
    for check in REQUIRED:
        record=evidence.get(check)
        if not isinstance(record,dict) or record.get("status")!="passed":
            outstanding.append(check)
            continue
        ref=record.get("ref")
        if not isinstance(ref,str) or len(ref)<8 or len(ref)>180 or not all(
            c.isalnum() or c in "-_/.:#" for c in ref
        ):
            outstanding.append(check)
    return {"change_review_ready":not outstanding,"outstanding":outstanding,
            "production_authorized":False,"independent_approvals_required":True}

def main()->int:
    policy=json.loads(POLICY.read_text(encoding="utf-8"))
    evidence_path=ROOT/"docs/section43_evidence.json"
    evidence=json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {}
    report=assess(policy,evidence)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report["change_review_ready"] else 1

if __name__=="__main__":
    raise SystemExit(main())
