"""Section 35: deployment configuration policy unit checks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.verify_compose import inspect

def sample():
    return {"services":{
      "db":{"healthcheck":{"test":["CMD","true"]},"ports":[{"published":"5544","host_ip":"127.0.0.1"}]},
      "redis":{"healthcheck":{"test":["CMD","true"]}},
      "migrate":{"command":["python","-m","alembic","upgrade","head"]},
      "api":{"command":["uvicorn","app.main:app"],"ports":[{"published":"8000","host_ip":"127.0.0.1"}],
             "depends_on":{"migrate":{"condition":"service_completed_successfully"}}},
      "web":{"ports":[{"published":"3000","host_ip":"127.0.0.1"}]},
      "outbound-worker":{"profiles":["messaging"]}}}

def test_valid_local_development_compose():
    assert inspect(sample())==[]

def test_public_ports_are_blocked():
    data=sample()
    data["services"]["api"]["ports"][0]["host_ip"]="0.0.0.0"
    assert "public_host_port:api" in inspect(data)

def test_migration_gates_are_required():
    data=sample()
    data["services"]["api"]["command"]=["sh","-c","python -m alembic upgrade head && uvicorn app.main:app"]
    data["services"]["api"]["depends_on"]={}
    findings=inspect(data)
    assert "migrations_run_in_api_startup_manual_release_gate" in findings
    assert "api_not_gated_on_migration" in findings

def test_worker_requires_opt_in():
    data=sample()
    data["services"]["outbound-worker"]["profiles"]=[]
    assert "worker_missing_opt_in_profile" in inspect(data)


def test_optional_telegram_gateway_must_be_isolated_and_opt_in():
    data=sample()
    data["services"]["telegram-gateway"]={
        "profiles":["telegram"],
        "command":["uvicorn","app.telegram_entrypoint:app","--host","0.0.0.0"],
        "read_only":True,
        "environment":{"TELEGRAM_BOT_ENABLED":"false","REDIS_URL":"redis://redis:6379/0"},
        "ports":[{"published":"8001","host_ip":"127.0.0.1"}],
    }
    assert inspect(data)==[]
    data["services"]["telegram-gateway"]["ports"][0]["host_ip"]="0.0.0.0"
    assert "public_host_port:telegram-gateway" in inspect(data)
    data["services"]["telegram-gateway"]["ports"][0]["host_ip"]="127.0.0.1"
    data["services"]["telegram-gateway"]["environment"]["DATABASE_URL"]="postgresql://unsafe"
    assert "telegram_gateway_receives_backend_credentials" in inspect(data)
    del data["services"]["telegram-gateway"]["environment"]["DATABASE_URL"]
    data["services"]["telegram-gateway"]["command"]=["uvicorn","app.main:app"]
    assert "telegram_gateway_not_isolated" in inspect(data)
    data["services"]["telegram-gateway"]["profiles"]=[]
    assert "telegram_gateway_not_opt_in" in inspect(data)


def test_optional_local_poller_is_opt_in_and_isolated():
    data=sample()
    data["services"]["telegram-poller"]={
        "profiles":["telegram-polling"],
        "command":["python","-m","app.telegram_poller"],
        "read_only":True,
        "environment":{"TELEGRAM_POLLING_ENABLED":"false","REDIS_URL":"redis://redis:6379/0"},
    }
    assert inspect(data)==[]
    service=data["services"]["telegram-poller"]
    service["profiles"]=[]
    assert "telegram_poller_not_opt_in" in inspect(data)
    service["profiles"]=["telegram-polling"]
    service["environment"]["JWT_SECRET"]="unsafe"
    assert "telegram_poller_receives_backend_credentials" in inspect(data)
    del service["environment"]["JWT_SECRET"]
    service["ports"]=[{"published":"8005","host_ip":"127.0.0.1"}]
    assert "telegram_poller_exposes_port" in inspect(data)
    del service["ports"]
    service["read_only"]=False
    assert "telegram_poller_writable_fs" in inspect(data)
    service["read_only"]=True
    service["command"]=["uvicorn","app.main:app"]
    assert "telegram_poller_wrong_entrypoint" in inspect(data)
