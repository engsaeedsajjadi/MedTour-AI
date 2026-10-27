"""Section 36: static CI quality-gate and contract checks without real patient data."""
from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def test_ci_runs_backend_suite_and_real_pg_migration():
    workflow=(ROOT/".github/workflows/backend-ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q" in workflow
    assert "python -m alembic upgrade head" in workflow
    assert "tests/section_26_pg_probe.py" in workflow

def test_frontend_ci_checks_types_build_and_dependency_audit():
    workflow=(ROOT/".github/workflows/frontend-ci.yml").read_text(encoding="utf-8")
    assert "npm ci" in workflow
    assert "npm audit --audit-level=high" in workflow
    assert "npm run typecheck" in workflow
    assert "npm run build" in workflow

def test_production_gate_exists_in_backend():
    safety=(ROOT/"backend/app/safety_rules.py").read_text(encoding="utf-8")
    main=(ROOT/"backend/app/main.py").read_text(encoding="utf-8")
    assert "assert_safe_runtime" in safety
    assert "assert_safe_runtime()" in main
