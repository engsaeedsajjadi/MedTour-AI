"""Section 35: inspect resolved Docker Compose configuration, never deploy.

Usage: docker compose config --format json | python scripts/verify_compose.py
Do not print Compose JSON: it can contain resolved secrets.
"""
from __future__ import annotations
import json
import sys

def inspect(config: dict) -> list[str]:
    failures=[]
    services=config.get("services",{})
    for required in ("db","redis","migrate","api","web"):
        if required not in services:
            failures.append(f"missing_service:{required}")
    for name in ("db","api","web","telegram-gateway"):
        service=services.get(name,{})
        for port in service.get("ports",[]):
            if isinstance(port,str):
                failures.append(f"unstructured_port:{name}")
            elif port.get("published") and port.get("host_ip") not in ("127.0.0.1","::1"):
                failures.append(f"public_host_port:{name}")
    worker=services.get("outbound-worker",{})
    if worker and "messaging" not in worker.get("profiles",[]):
        failures.append("worker_missing_opt_in_profile")
    telegram=services.get("telegram-gateway")
    if telegram is not None:
        if "telegram" not in telegram.get("profiles",[]):
            failures.append("telegram_gateway_not_opt_in")
        cmd=str(telegram.get("command",[]))
        if "app.telegram_entrypoint:app" not in cmd or "app.main:app" in cmd:
            failures.append("telegram_gateway_not_isolated")
        if not telegram.get("read_only",False):
            failures.append("telegram_gateway_writable_fs")
        env=telegram.get("environment",{})
        keys=set(env) if isinstance(env,(dict,list)) else set()
        if {"DATABASE_URL","POSTGRES_PASSWORD","JWT_SECRET"} & keys:
            failures.append("telegram_gateway_receives_backend_credentials")
    api=services.get("api",{})
    migration=services.get("migrate",{})
    if not migration or "alembic" not in str(migration.get("command",[])):
        failures.append("missing_one_shot_migration")
    if api.get("depends_on",{}).get("migrate",{}).get("condition")!="service_completed_successfully":
        failures.append("api_not_gated_on_migration")
    if "python -m alembic upgrade head" in " ".join(api.get("command",[]) if isinstance(api.get("command"),list) else [str(api.get("command",""))]):
        failures.append("migrations_run_in_api_startup_manual_release_gate")
    db=services.get("db",{})
    if not db.get("healthcheck"):
        failures.append("database_healthcheck_missing")
    redis=services.get("redis",{})
    if not redis.get("healthcheck"):
        failures.append("redis_healthcheck_missing")
    return failures

def main() -> int:
    try:
        data=json.load(sys.stdin)
        failures=inspect(data)
    except (ValueError,TypeError,KeyError):
        print("Invalid resolved Compose JSON",file=sys.stderr)
        return 2
    if failures:
        for fault in failures:print("FAIL "+fault)
        return 1
    print("PASS: Compose development boundary checks; production readiness NOT certified")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
