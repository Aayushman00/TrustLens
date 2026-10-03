"""Runs ONE evaluation of the 2-label toxic-bert conversion through the live TrustLens API
(same dataset, mapping, mode and engine as run_flawed_suite_eval). Output: eval_results_v3/.
Usage (from backend/, stack up)::  python -m app.scripts.run_reference_2label_eval <new-out-dir>
"""
import json


from app.scripts import run_flawed_suite_eval as r

NAME = "reference_toxicbert_2label"


def main() -> None:
    import sys

    # Historical output lives in eval_results_v3; new runs need a fresh directory.
    out = r.fresh_out_dir(r.SUITE_DIR / (sys.argv[1] if len(sys.argv) > 1 else "eval_results_v3"))
    with r._client() as c:
        ds = r.upload_eval_dataset(c)
        card = (r.SUITE_DIR / "models" / NAME / "README.md").read_text(encoding="utf-8")
        body = {"hf_repo_id": f"{r.WORKER_MODEL_ROOT}/{NAME}",
                "model_metadata": {"card_text": card, "card_data": {"license": "apache-2.0"}},
                "revision": "local"}
        resp = c.post("/models", json=body)
        if resp.status_code == 409:
            mid = r._find_existing_model(c, body["hf_repo_id"])["id"]
        else:
            resp.raise_for_status()
            mid = resp.json()["id"]
        ev = r.create_and_run_evaluation(c, mid, ds)
    (out / f"{NAME}.json").write_text(json.dumps(ev, indent=2), encoding="utf-8")
    print(ev["status"], (ev.get("final_score") or {}))


if __name__ == "__main__":
    main()
