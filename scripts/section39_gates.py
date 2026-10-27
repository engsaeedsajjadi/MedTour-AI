"""Section 39: evaluate independent phase acceptance evidence, fail closed.

Do not attach confidential reports, patient data, credentials, or personal names.
An evidence reference must point to separately reviewed records; it is NOT certification.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

PHASE_KEYS={"id","title","depends_on","sections","requirements"}

def evaluate(plan:dict[str,Any])->dict[str,Any]:
    phases=plan.get("phases")
    if plan.get("schema_version")!=1 or not isinstance(phases,list) or len(phases)!=5:
        raise ValueError("Invalid phase plan")
    ids=[p.get("id") for p in phases if isinstance(p,dict)]
    if ids!=["G1","G2","G3","G4","G5"]:
        raise ValueError("Wrong phase order or duplicate gates")
    evidence=plan.get("evidence")
    if not isinstance(evidence,dict):raise ValueError("Evidence must be an object")
    unknown=set(evidence)-set(ids)
    if unknown:raise ValueError("Unknown evidence phase")
    statuses={}
    for phase in phases:
        if not PHASE_KEYS.issubset(phase):raise ValueError("Incomplete gate definition")
        if not isinstance(phase["sections"],list) or not phase["sections"] or not all(
            type(x) is int and 1<=x<=45 for x in phase["sections"]
        ):raise ValueError("Invalid section mapping")
        req=phase["requirements"]
        if not isinstance(req,list) or not req or len(set(req))!=len(req) or not all(
            isinstance(x,str) and x for x in req
        ):raise ValueError("Invalid acceptance requirements")
        if any(dep not in statuses for dep in phase["depends_on"]):
            raise ValueError("Dependency must precede phase")
        submitted=evidence.get(phase["id"],{})
        if not isinstance(submitted,dict) or set(submitted)-set(req):
            raise ValueError("Unknown evidence requirement")
        # Only an explicit, separately approved record counts. Repository commits and
        # authored docs do not mean a live security/clinical/operational signoff.
        complete=[]
        for name in req:
            item=submitted.get(name)
            if not isinstance(item,dict):continue
            if item.get("approved") is not True:continue
            if item.get("review_type")!="independent":continue
            reference=item.get("evidence_ref")
            if not isinstance(reference,str) or len(reference)<8 or len(reference)>200:continue
            if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./:" for c in reference):continue
            complete.append(name)
        dependencies_met=all(statuses[d]["accepted"] for d in phase["depends_on"])
        accepted=dependencies_met and len(complete)==len(req)
        statuses[phase["id"]]={"accepted":accepted,
            "dependencies_met":dependencies_met,
            "approved_evidence_count":len(complete),
            "required_evidence_count":len(req),
            "missing":[name for name in req if name not in complete]}
    return {"phases":statuses,"all_gates_accepted":all(x["accepted"] for x in statuses.values()),
            "production_authorized":False}

def main()->int:
    path=Path(__file__).resolve().parents[1]/"docs/section39_acceptance_gates.json"
    report=evaluate(json.loads(path.read_text(encoding="utf-8")))
    print(json.dumps(report,indent=2))
    return 0 if report["all_gates_accepted"] else 1

if __name__=="__main__":
    raise SystemExit(main())
