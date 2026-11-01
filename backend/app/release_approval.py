"""Evidence-based production release authorization.

Production is authorized only by a committed, reviewable sign-off file — never by an environment
variable or CLI flag. The file is built into the image from ``backend/release/`` and records the
references of the independent reviews a human release board has completed. Code cannot produce
these reviews; it only refuses to run in production until they are recorded.

Expected file (``backend/release/PRODUCTION_APPROVAL.json``)::

    {
      "release_version": "1.0.0",
      "security_penetration_test_reference": "...",
      "clinical_safety_review_reference": "...",
      "privacy_impact_assessment_reference": "...",
      "backup_restore_drill_reference": "...",
      "provider_contracts_reference": "...",
      "approved_by": ["name / role", "name / role"],
      "approved_at": "2027-01-15"
    }
"""
from __future__ import annotations
import json
import os
import re
from datetime import date
from pathlib import Path

APPROVAL_FILE = Path(__file__).resolve().parents[1] / "release" / "PRODUCTION_APPROVAL.json"

REFERENCE_FIELDS = (
    "security_penetration_test_reference",
    "clinical_safety_review_reference",
    "privacy_impact_assessment_reference",
    "backup_restore_drill_reference",
    "provider_contracts_reference",
)
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/#-]{5,119}$")


def _approval_path() -> Path:
    # Tests may point at a temporary file; production images always use the built-in path.
    override = os.getenv("MEDTOUR_RELEASE_APPROVAL_FILE_FOR_TESTS", "")
    if override and os.getenv("APP_ENV") == "test":
        return Path(override)
    return APPROVAL_FILE


def evaluate(path: Path | None = None) -> dict:
    """Return which sign-offs are present; never raises on malformed input."""
    target = path or _approval_path()
    missing: list[str] = []
    data: dict = {}
    if not target.is_file():
        return {"authorized": False, "missing": ["approval_file", *REFERENCE_FIELDS, "approved_by", "approved_at"]}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
    except (ValueError, OSError):
        return {"authorized": False, "missing": ["valid_json"]}
    for field in REFERENCE_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not _REF.fullmatch(value.strip()):
            missing.append(field)
    approvers = data.get("approved_by")
    if not (isinstance(approvers, list) and len([a for a in approvers if isinstance(a, str) and a.strip()]) >= 2):
        missing.append("approved_by")  # at least two independent approvers
    try:
        approved = date.fromisoformat(str(data.get("approved_at", "")))
        if approved > date.today():
            missing.append("approved_at")
    except ValueError:
        missing.append("approved_at")
    return {"authorized": not missing, "missing": missing,
            "release_version": str(data.get("release_version", "")) if not missing else ""}
