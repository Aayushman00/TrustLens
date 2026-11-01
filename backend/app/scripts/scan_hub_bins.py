"""Scan pickle-format files (*.bin, *.pt, *.pkl) of Hub repos with the opcode scanner. Each file is downloaded at the
repo's pinned commit sha, scanned, and deleted immediately. Nothing is ever unpickled.

python -m app.scripts.scan_hub_bins --repos results/m0_pickle_scan_repos.txt --out results/m0_pickle_scan.json
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

from app.integrity.opcode_scan import scan_file

EXTS = (".bin", ".pt", ".pkl")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--max-mb", type=int, default=1024, help="skip files larger than this")
    a = ap.parse_args()
    api = HfApi()
    done = json.loads(a.out.read_text()) if a.out.exists() else []  # resumable
    seen = {(r["repo"], r["file"]) for r in done}
    for repo in [x.strip() for x in a.repos.read_text().splitlines() if x.strip() and not x.startswith("#")]:
        try:
            info = api.model_info(repo, files_metadata=True)
        except Exception as e:
            print(repo, "model_info failed", type(e).__name__)
            continue
        for s in info.siblings or []:
            if not s.rfilename.endswith(EXTS) or (repo, s.rfilename) in seen:
                continue
            row = {"repo": repo, "file": s.rfilename, "revision": info.sha, "size_bytes": s.size}
            if (s.size or 0) > a.max_mb * 2**20:
                row.update(skipped="too_large")
            else:
                with tempfile.TemporaryDirectory() as d:
                    try:
                        p = hf_hub_download(repo, s.rfilename, revision=info.sha, local_dir=d)
                        row.update(scan_file(Path(p)).__dict__)
                    except Exception as e:
                        row.update(skipped=f"download_failed:{type(e).__name__}")
            done.append(row)
            print(repo, s.rfilename, row.get("tier", row.get("skipped")), flush=True)
            a.out.write_text(json.dumps(done, indent=1))
    scanned = [r for r in done if "tier" in r]
    print({"scanned": len(scanned), "tiers": {str(t): sum(r["tier"] == t for r in scanned) for t in ("A", "B", None)}})


if __name__ == "__main__":
    main()
