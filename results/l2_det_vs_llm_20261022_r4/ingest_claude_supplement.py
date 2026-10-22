"""Append the Claude supplemental answers for L2 runs that no API provider answered.
Usage: python ingest_claude_supplement.py <answers_dir> <llm_responses.jsonl>
Each answer file is Pxx_rN.json (raw JSON text of one blinded Claude subagent). Only runs that are
fallbacks in llm_runs.json get a record; existing provider answers are never touched."""
import json, sys, hashlib
from datetime import UTC, datetime
from pathlib import Path

ans_dir, store = Path(sys.argv[1]), Path(sys.argv[2])
runs = json.loads((store.parent / "llm_runs.json").read_text(encoding="utf-8"))
idx = json.loads((store.parent / "packet_index.json").read_text(encoding="utf-8"))
MODEL = "claude-sonnet-5-5"
n = 0
with store.open("a", encoding="utf-8") as f:
    for pid, rs in runs.items():
        for r in rs:
            if not r["fallback"]:
                continue
            p = ans_dir / f"{pid}_r{r['run_index']}.json"
            raw = p.read_text(encoding="utf-8")
            rec = {"packet_id": pid, "packet_sha256": idx[pid], "run_index": r["run_index"],
                   "prompt_version": "osd-llm-v3-decision-first-2026-10-03",
                   "provenance": {"llm_provider": "claude", "llm_model": MODEL, "llm_temperature": None,
                                  "llm_prompt_sha256": r["prompt_sha256"], "llm_attempts": 1,
                                  "llm_prompt_version": "osd-llm-v3-decision-first-2026-10-03",
                                  "llm_prompt_truncated": r["prompt_truncated"], "supplemental": True},
                   "attempts": [{"provider": "claude", "raw": raw, "elapsed_s": 0.0}],
                   "elapsed_s": 0.0, "at": datetime.now(UTC).isoformat()}
            f.write(json.dumps(rec) + "\n"); n += 1
print("appended", n)
