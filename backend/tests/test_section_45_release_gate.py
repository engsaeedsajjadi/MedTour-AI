"""Section 45 release status must not be forgeable by environment variables."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.section45_release_gate import status,main
from app.safety_rules import assert_safe_runtime
import pytest

def test_release_gate_always_denies_real_patient_operations(monkeypatch):
    for mode in ("test","development","production"):
        monkeypatch.setenv("APP_ENV",mode)
        monkeypatch.setenv("MEDTOUR_PRODUCTION_APPROVED","true")
        result=status()
        assert result["production_authorized"] is False
        assert result["real_patient_data_allowed"] is False
        assert result["payment_capture_authorized"] is False
        assert result["final_acceptance_verified"] is False
        assert main()==1

def test_existing_production_runtime_guard_rejects_alpha():
    with pytest.raises(RuntimeError,match="NOT authorized"):
        assert_safe_runtime("production")


def _approval(tmp_path, **override):
    import json
    data = {"release_version": "1.0.0",
            "security_penetration_test_reference": "PENTEST-2027-001",
            "clinical_safety_review_reference": "CLINICAL-REVIEW-2027-01",
            "privacy_impact_assessment_reference": "DPIA-2027-01",
            "backup_restore_drill_reference": "DR-DRILL-2027-01",
            "provider_contracts_reference": "CONTRACTS-2027-01",
            "approved_by": ["Security lead", "Clinical governance lead"],
            "approved_at": "2026-10-01"}
    data.update(override)
    path = tmp_path / "PRODUCTION_APPROVAL.json"
    path.write_text(json.dumps(data))
    return path

def test_environment_flags_never_authorize_without_signoff(monkeypatch):
    for flag in ("MEDTOUR_PRODUCTION_APPROVED","PRODUCTION_READY","MEDTOUR_PRODUCTION_AUTHORIZED"):
        monkeypatch.setenv(flag,"true")
    assert status()["production_authorized"] is False
    with pytest.raises(RuntimeError,match="NOT authorized"):
        assert_safe_runtime("production")

def test_complete_signoff_authorizes_and_incomplete_does_not(tmp_path, monkeypatch):
    good = _approval(tmp_path)
    assert status(good)["production_authorized"] is True
    monkeypatch.setenv("MEDTOUR_RELEASE_APPROVAL_FILE_FOR_TESTS", str(good))
    assert_safe_runtime("production")  # signed off: allowed to start (compliance checks still apply)
    for bad in ({"security_penetration_test_reference": ""}, {"approved_by": ["only one"]},
                {"approved_at": "2999-01-01"}, {"backup_restore_drill_reference": "x"}):
        path = _approval(tmp_path, **bad)
        assert status(path)["production_authorized"] is False
        monkeypatch.setenv("MEDTOUR_RELEASE_APPROVAL_FILE_FOR_TESTS", str(path))
        with pytest.raises(RuntimeError, match="NOT authorized"):
            assert_safe_runtime("production")

def test_test_override_is_ignored_outside_tests(tmp_path, monkeypatch):
    from app.release_approval import _approval_path, APPROVAL_FILE
    monkeypatch.setenv("MEDTOUR_RELEASE_APPROVAL_FILE_FOR_TESTS", str(_approval(tmp_path)))
    monkeypatch.setenv("APP_ENV", "production")
    assert _approval_path() == APPROVAL_FILE
