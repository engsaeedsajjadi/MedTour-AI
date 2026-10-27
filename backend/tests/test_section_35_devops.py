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
