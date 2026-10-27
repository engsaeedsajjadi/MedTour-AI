"""Fail-closed acceptance report, not a production authorization service.

Evidence references are metadata only. This script never fetches documents,
handles PHI, or grants permission to deploy.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/"docs/section44_final_acceptance.json"

def assess(document:dict)->dict:
    checks=document.get("checks")
    evidence=document.get("evidence")
    if (document.get("schema_version")!=1 or document.get("production_authorized") is not False
        or not isinstance(checks,list) or len(checks)!=15
        or len(set(checks))!=15 or not all(isinstance(x,str) and x for x in checks)
        or not isinstance(evidence,dict) or set(evidence)-set(checks)):
        raise ValueError("Invalid final-acceptance evidence document")
    accepted=[]
    for check in checks:
        record=evidence.get(check)
        if not isinstance(record,dict):
            continue
        ref=record.get("evidence_ref")
        if (record.get("approved") is True and record.get("review_type")=="independent"
            and isinstance(ref,str) and 8<=len(ref)<=180
            and all(c.isascii() and (c.isalnum() or c in "/:._-#") for c in ref)):
            accepted.append(check)
    return {
        "evidence_coverage_complete":len(accepted)==len(checks),
        "accepted_evidence_count":len(accepted),
        "required_evidence_count":len(checks),
        "missing":[x for x in checks if x not in accepted],
        "final_acceptance_confirmed":False,
        "production_authorized":False,
        "note":"Document references require separate genuine verification and named authority signoff",
    }

def main()->int:
    report=assess(json.loads(FILE.read_text(encoding="utf-8")))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 1  # acceptance authority is external; script cannot approve production

if __name__=="__main__":
    raise SystemExit(main())
