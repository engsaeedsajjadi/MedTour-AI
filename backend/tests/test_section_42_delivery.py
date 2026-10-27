"""Section 42 release inventory safeguards."""
import json,sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.section42_verify_delivery import assess

def manifest():
    return json.loads((ROOT/"docs/section42_delivery_manifest.json").read_text(encoding="utf-8"))

def test_delivery_inventory_has_declared_artifacts_and_no_production_claim():
    result=assess(ROOT,manifest())
    assert result["artifact_count"]>=15
    assert result["production_accepted"] is False
    assert "independent_privacy_review" in result["external_acceptance_outstanding"]

def test_missing_file_fails_inventory(tmp_path):
    content=manifest()
    report=assess(tmp_path,content)
    assert report["inventory_complete"] is False
    assert report["missing_required"]

@pytest.mark.parametrize("path",["../private.env","/etc/passwd","x\\y"])
def test_unsafe_paths_are_rejected(path):
    content=manifest()
    content["artifacts"][0]["path"]=path
    with pytest.raises(ValueError):
        assess(ROOT,content)
