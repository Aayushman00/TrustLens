"""Copy each evaluation's TrustLens report (JSON + PDF) and raw evidence
artifacts out of the api container into the results folder, for the report.

For every saved evaluation JSON under <results-subdir> (``raw/*.json`` or
``*.json``), GET /v1/reports/{id} (generates v1 if needed), then copies
/data/artifacts/trustlens/{reports,evidence}/{id} into
<results-subdir>/artifacts/<file-stem>/.

Usage (from backend/, stack up)::  python -m app.scripts.export_artifacts final_20261002_repeat5
"""
from __future__ import annotations

import json
import subprocess
import sys

import httpx

from app.scripts.run_flawed_suite_eval import API_BASE, SUITE_DIR

_CONTAINER = "majorproject-api-1"
_ROOT = "/data/artifacts/trustlens"


def main() -> None:
    base = SUITE_DIR / sys.argv[1]
    files = sorted((base / "raw").glob("*.json")) or sorted(p for p in base.glob("*.json") if not p.name.startswith(("_", "analysis")))
    index = []
    with httpx.Client(base_url=API_BASE, timeout=180) as c:
        for p in files:
            ev = json.loads(p.read_text(encoding="utf-8"))
            eid, row = ev.get("id"), {"file": p.name, "evaluation_id": ev.get("id"), "status": ev.get("status")}
            if not eid or ev.get("status") != "FINALIZED":
                index.append({**row, "exported": False, "reason": "not finalized"})
                continue
            dest = base / "artifacts" / p.stem
            dest.mkdir(parents=True, exist_ok=True)
            rep = c.get(f"/reports/{eid}")
            row["report_status"] = rep.status_code
            if rep.status_code == 200:
                meta = rep.json()
                row.update({k: meta.get(k) for k in ("version", "json_hash", "pdf_hash", "fries_score", "methodology_version")})
            for kind in ("reports", "evidence"):
                r = subprocess.run(
                    ["docker", "cp", f"{_CONTAINER}:{_ROOT}/{kind}/{eid}", str(dest / kind)],
                    capture_output=True, text=True,
                )
                row[f"{kind}_copied"] = r.returncode == 0
            index.append({**row, "exported": True})
    (base / "artifacts" / "_index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"{sum(r['exported'] for r in index)}/{len(index)} exported -> {base / 'artifacts'}")


if __name__ == "__main__":
    main()
