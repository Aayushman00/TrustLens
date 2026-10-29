"""Live demo driver: audit a Hub model TrustLens has never scored, narrating each stage.

Drives the running stack (``docker compose up``) through the same API the UI uses:
import -> dataset upload -> draft/contract -> assisted evaluation -> per-dimension
evidence -> O/S/D proposals -> human review -> FRIES -> report (JSON+PDF) -> events -> publish.
Pauses between stages (Enter) so the presenter can switch to the matching UI page.

Usage (from backend/)::
    python -m app.scripts.run_demo_unseen_model --csv ../results/demo_unseen_20261028/demo_eval_set.csv
    add --no-pause for a dry run, --engine llm_v1 if provider keys are configured.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.scripts import run_flawed_suite_eval as r

MODEL = "cardiffnlp/twitter-roberta-base-offensive"  # not in any earlier suite/hub run
POSITIVE_INDEX = 1  # id2label {0: non-offensive, 1: offensive}


def stage(title: str, pause: bool) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")
    if pause:
        input("[Enter to run this stage] ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--engine", default="legacy_heuristic", choices=["deterministic", "legacy_heuristic", "llm_v1"])
    ap.add_argument("--out", type=Path, help="new folder to save report.json / report.pdf")
    ap.add_argument("--no-pause", action="store_true")
    args = ap.parse_args()
    pause = not args.no_pause
    out = r.fresh_out_dir(args.out) if args.out else None

    with r._client() as c:
        stage(f"1. IMPORT model metadata only (no weights): {args.model}", pause)
        model = c.post("/models/import-hf", json={"repo_id": args.model})
        model.raise_for_status()
        m = model.json()
        card = (m.get("model_metadata") or {}).get("card_data") or {}
        print(f"model_id={m['id']} pinned revision={m.get('revision')} license={card.get('license')}")
        print("tags:", card.get("tags"))

        stage("2. UPLOAD dataset (hash-named, schema sniffed)", pause)
        with args.csv.open("rb") as f:
            up = c.post("/dataset-uploads", files={"file": (args.csv.name, f, "text/csv")})
        up.raise_for_status()
        ds = up.json()
        print(f"dataset_content_id={ds['id']} rows={ds['row_count']}")

        stage("3. CONTRACT + RUN (Fairness, Robustness, Behavioural Safety + card-based Integrity/Explainability)"
              " in AI_ASSISTED mode", pause)
        ev = r.create_and_run_evaluation(
            c, m["id"], ds["id"], positive_index=POSITIVE_INDEX,
            evaluation_mode="AI_ASSISTED", assessment_engine=args.engine,
        )
        eid = ev["id"]
        print("status:", ev["status"], "| revision:", ev.get("model_revision"), "| device:",
              (ev.get("execution_metadata") or {}).get("execution_device"))

        stage("4. EVIDENCE per FRIES dimension (Layer A: measured, never a score)", pause)
        for p in ev.get("probes") or []:
            print(f"- {p['dimension']:<14} status={p['status']:<22} scoring={p.get('aspect_scoring')}"
                  f" risks={p.get('risks_triggered')} gates={p.get('gates')}")
            if p.get("status_reason"):
                print(f"    reason: {p['status_reason']}")

        stage("5. O/S/D PROPOSALS (Layer B: PROPOSED_REQUIRES_VALIDATION)", pause)
        osd = ev.get("osd_agent") or {}
        print(json.dumps(osd.get("ai_suggestion"), indent=2))
        print("status:", osd.get("methodology_status"), "| rationale:", (osd.get("rationale") or "")[:300])

        stage("6. HUMAN REVIEW: accept agent proposal (edit via UI Review page to show an override)", pause)
        rv = c.post(f"/evaluations/{eid}/human-review",
                    json={"accept_all": True, "review_rationale": "Demo: reviewed evidence dossier, accepted."})
        print("review:", rv.status_code, rv.json() if rv.is_success else rv.text)

        stage("7. FINALIZE -> original FRIES math T=cbrt(O*S*D), weighted overall", pause)
        fin = c.post(f"/evaluations/{eid}/finalize")
        fin.raise_for_status()
        fs = fin.json().get("final_score") or {}
        print("FRIES:", fs.get("fries_score"), "| human_reviewed:", fs.get("human_reviewed"))
        print("dimensions:", json.dumps(fs.get("dimension_scores"), indent=2))
        print("disclaimer:", fs.get("disclaimer"))

        stage("8. REPORT (versioned, hashed) + lifecycle audit trail", pause)
        rep = c.get(f"/reports/{eid}")
        rep.raise_for_status()
        rj = rep.json()
        print(f"report v{rj['version']} json_hash={rj['json_hash']} pdf_hash={rj.get('pdf_hash')}")
        print("sections:", list(rj["report_json"]))
        events = c.get(f"/evaluations/{eid}/events").json()["items"]
        for e in events:
            print(f"  #{e['id']:<3} {e['event_type']}")
        if out:
            (out / "report.json").write_text(json.dumps(rj["report_json"], indent=2), encoding="utf-8")
            (out / "events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
            print("saved report.json + events.json to", out, "(PDF: UI Report page > Download PDF)")

        stage("9. PUBLISH is opt-in, then UNPUBLISH", pause)
        print("published:", c.post(f"/evaluations/{eid}/publish").json()["is_published"])
        print("published:", c.post(f"/evaluations/{eid}/unpublish").json()["is_published"])

    print(f"\nDone. Open http://localhost:5173/evaluations/{eid} and /reports/{eid}")


if __name__ == "__main__":
    main()
