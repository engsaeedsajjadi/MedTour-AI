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
