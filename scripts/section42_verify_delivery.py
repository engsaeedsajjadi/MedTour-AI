"""Section 42: reproducible inventory validation without secrets or patient data."""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"docs/section42_delivery_manifest.json"

def assess(root:Path,manifest:dict)->dict:
    if manifest.get("schema_version")!=1 or manifest.get("project")!="MedTour-AI":
        raise ValueError("Invalid delivery manifest")
    rows=manifest.get("artifacts")
    if not isinstance(rows,list) or not rows:raise ValueError("Missing artifact inventory")
    results=[]
    for row in rows:
        if not isinstance(row,dict) or type(row.get("required")) is not bool:
            raise ValueError("Malformed inventory row")
        raw=row.get("path")
        if not isinstance(raw,str) or not raw or "\\" in raw:
            raise ValueError("Invalid inventory path")
        rel=Path(raw)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Path escapes repository")
        target=root/rel
        exists=target.exists() and (target.is_file() or target.is_dir()) and not target.is_symlink()
        results.append({"id":row["id"],"path":raw,"present":exists,"required":row["required"]})
    complete=all(x["present"] for x in results if x["required"])
    return {"inventory_complete":complete,"production_accepted":False,
        "artifact_count":len(results),"missing_required":[x["path"] for x in results if x["required"] and not x["present"]],
        "external_acceptance_outstanding":manifest.get("external_acceptance",[]),"artifacts":results}

def main():
    report=assess(ROOT,json.loads(MANIFEST.read_text(encoding="utf-8")))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report["inventory_complete"] else 1

if __name__=="__main__":
    raise SystemExit(main())
