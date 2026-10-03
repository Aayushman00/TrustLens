"""Upload each suite model folder to a private Hub repo (needs HF_TOKEN).

Removes the local-directory vs Hub confound: variants evaluated through
import-hf get the same revision pinning and manifest checks as real models.

Usage (from backend/)::  python -m app.scripts.publish_suite_to_hub --prefix <hf-username>
"""
from __future__ import annotations

import argparse
import os

from app.scripts.run_flawed_suite_eval import LOCAL_VARIANTS, SUITE_DIR

REFERENCE_2LABEL = "reference_toxicbert_2label"


def hub_repo_id(prefix: str, name: str) -> str:
    return f"{prefix}/trustlens-suite-{name.replace('_', '-')}"


def main() -> None:
    from huggingface_hub import HfApi

    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True)
    args = ap.parse_args()
    api = HfApi(token=os.environ["HF_TOKEN"])
    for name in [*LOCAL_VARIANTS, REFERENCE_2LABEL]:
        rid = hub_repo_id(args.prefix, name)
        api.create_repo(rid, private=True, exist_ok=True)
        info = api.upload_folder(
            repo_id=rid,
            folder_path=str(SUITE_DIR / "models" / name),
            commit_message=f"suite model {name}",
        )
        print("uploaded", rid, "revision", info.oid)


if __name__ == "__main__":
    main()
