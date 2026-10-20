"""Stage 19.14 — isolated SQLAlchemy/psycopg tenant-principal pool probe.

This file is deliberately NOT part of the live application wiring.
It runs only inside an ephemeral container against the disposable restored clone.
Do not use real patient information or production credentials.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.models import Patient


HOST = os.environ["PROBE_DB_HOST"]
DB = "medtour_principal_clone"
TENANT_A = os.environ["PROBE_TENANT_A"]
TENANT_B = os.environ["PROBE_TENANT_B"]
PATIENT_A = os.environ["PROBE_PATIENT_A"]
PATIENT_B = os.environ["PROBE_PATIENT_B"]

config = {
    "mt_clone_a": (os.environ["PROBE_PASSWORD_A"], TENANT_A, PATIENT_A, TENANT_B, PATIENT_B),
    "mt_clone_b": (os.environ["PROBE_PASSWORD_B"], TENANT_B, PATIENT_B, TENANT_A, PATIENT_A),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def role_session_factory(role: str):
    password, _, _, _, _ = config[role]
    # Each authenticated database role gets its own SQLAlchemy Engine and pool.
    # Do NOT implement 'SET ROLE' or re-use another tenant's credentials.
    url = URL.create(
        "postgresql+psycopg", username=role, password=password,
        host=HOST, port=5432, database=DB
    )
    engine = create_engine(
        url, pool_size=2, max_overflow=0, pool_timeout=10,
        pool_pre_ping=True, pool_reset_on_return="rollback",
        connect_args={"connect_timeout": 5},
    )
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


engines_and_sessions = {role: role_session_factory(role) for role in config}


def verify_owned_rows(role: str) -> None:
    _, own_tenant, own_patient, other_tenant, other_patient = config[role]
    _, Session = engines_and_sessions[role]
    with Session() as session:
        identity = session.execute(text("SELECT current_user, session_user")).one()
        require(identity == (role, role), f"Unexpected authenticated principal for {role}: {identity}")
        ids = set(session.scalars(select(Patient.id)).all())
        require(own_patient in ids, f"Cannot see own synthetic patient as {role}")
        require(other_patient not in ids, f"Foreign synthetic patient leaked to {role}")
        require(
            all(x == own_tenant for x in session.scalars(select(Patient.tenant_id)).all()),
            f"Foreign tenant row leaked under {role}"
        )
        session.rollback()


def verify_guc_spoof_does_not_switch_role(role: str) -> None:
    _, own_tenant, own_patient, other_tenant, other_patient = config[role]
    _, Session = engines_and_sessions[role]
    with Session() as session:
        session.execute(
            text("SELECT set_config('medtour.tenant_id', :foreign_tenant, false)"),
            {"foreign_tenant": other_tenant},
        )
        session.commit()  # deliberately preserve the malicious session-level setting
    verify_owned_rows(role)
    print(f"PASS: {role} GUC forgery cannot switch authenticated tenant", flush=True)


def verify_cannot_set_role(role: str) -> None:
    other = "mt_clone_b" if role == "mt_clone_a" else "mt_clone_a"
    _, Session = engines_and_sessions[role]
    with Session() as session:
        try:
            session.execute(text(f"SET ROLE {other}"))
        except DBAPIError as exc:
            session.rollback()
            require(getattr(exc.orig, "sqlstate", None) == "42501", "Unexpected SET ROLE error")
        else:
            session.rollback()
            raise AssertionError(f"{role} escalated to {other}")
    verify_owned_rows(role)
    print(f"PASS: {role} cannot SET ROLE to a different tenant", flush=True)


def verify_foreign_insert_rejected(role: str) -> None:
    _, Session = engines_and_sessions[role]
    _, own_tenant, own_patient, other_tenant, other_patient = config[role]
    with Session() as session:
        try:
            # Even an ORM-generated INSERT must be enforced by PostgreSQL.
            session.add(Patient(
                id=str(uuid4()), tenant_id=other_tenant, full_name="BLOCKED Synthetic",
                country="", language="en", contact=""
            ))
            session.flush()
        except DBAPIError as exc:
            session.rollback()
            require(getattr(exc.orig, "sqlstate", None) == "42501", "Unexpected RLS INSERT error")
        else:
            session.rollback()
            raise AssertionError(f"{role} inserted a foreign-tenant patient")
    print(f"PASS: {role} ORM foreign-tenant INSERT is rejected by RLS", flush=True)


def verify_permissions(role: str) -> None:
    _, Session = engines_and_sessions[role]
    with Session() as session:
        # Runtime role may read its own patients but must not read admin catalog.
        try:
            session.execute(text("SELECT count(*) FROM public.tenants"))
        except DBAPIError as exc:
            session.rollback()
            require(getattr(exc.orig, "sqlstate", None) == "42501", "Unexpected catalog-deny error")
        else:
            session.rollback()
            raise AssertionError(f"{role} could SELECT the tenant registry")
    print(f"PASS: {role} is denied direct tenant-registry SELECT", flush=True)


def verify_repeated_sessions(role: str, repeats: int = 12) -> None:
    # Alternating commits and rollbacks exercises connection reuse.
    _, own_tenant, own_patient, other_tenant, other_patient = config[role]
    _, Session = engines_and_sessions[role]
    for i in range(repeats):
        with Session() as session:
            identity = session.execute(text("SELECT session_user")).scalar_one()
            require(identity == role, f"Pool leaked session principal: expected {role}, got {identity}")
            ids = set(session.scalars(select(Patient.id)).all())
            require(own_patient in ids and other_patient not in ids, f"Pool data isolation violation: {role}")
            if i % 2:
                session.commit()
            else:
                session.rollback()


def main() -> None:
    try:
        for role in config:
            verify_owned_rows(role)
            verify_guc_spoof_does_not_switch_role(role)
            verify_cannot_set_role(role)
            verify_foreign_insert_rejected(role)
            verify_permissions(role)
            verify_repeated_sessions(role)
            print(f"PASS: {role} ORM identity and pooled session isolation", flush=True)

        # Threads share each engine pool but no SQLAlchemy Session instance.
        with ThreadPoolExecutor(max_workers=6) as threads:
            tasks = [threads.submit(verify_repeated_sessions, role, 8)
                     for role in ("mt_clone_a", "mt_clone_b") for _ in range(3)]
            for task in tasks:
                task.result()

        print("PASS: SQLALCHEMY 19.14 ISOLATED TENANT-PRINCIPAL POOL PROOF COMPLETED", flush=True)
        print("LIMITATION: live FastAPI get_db, pre-auth, refresh, portal, webhook and migration credentials are NOT integrated", flush=True)
    finally:
        for engine, _ in engines_and_sessions.values():
            engine.dispose()


if __name__ == "__main__":
    main()
