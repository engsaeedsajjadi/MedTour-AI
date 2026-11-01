"""Section 45: evidence-based release status. This tool does not deploy anything.

A source checkout is certified for real patients only when the committed sign-off file
backend/release/PRODUCTION_APPROVAL.json records every independent review (see
backend/app/release_approval.py). No flag, environment variable or CLI switch can approve it.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.release_approval import APPROVAL_FILE,evaluate  # noqa: E402

def status(path:Path|None=None)->dict:
    result=evaluate(path or APPROVAL_FILE)
    ok=result["authorized"]
    return {
        "release_track":"production" if ok else "pilot-synthetic-data",
        "release_version":result.get("release_version",""),
        "production_authorized":ok,
        "real_patient_data_allowed":ok,
        "live_medical_ai_allowed":False,
        "external_booking_authorized":False,
        "payment_capture_authorized":False,
        "telegram_onboarding_only":True,
        "final_acceptance_verified":ok,
        "missing_prerequisites":result["missing"],
    }

def main()->int:
    result=status()
    print(json.dumps(result,indent=2))
    return 0 if result["production_authorized"] else 1

if __name__=="__main__":
    raise SystemExit(main())
