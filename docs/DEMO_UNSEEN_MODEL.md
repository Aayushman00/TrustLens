# Demo: auditing a real model TrustLens has never seen

Goal: show every capability of TrustLens on one real Hugging Face model that appears in **none** of
the thesis experiments (controlled suite, 15-model Hub run, 7-model external audit), on a **fresh
dataset sample** the tool has never scored. Nothing is pre-cached or rehearsed against, so the
numbers are whatever the tool honestly produces. Do not promise a verdict in advance.

Total time: about 20 min live (inference on 2 000 rows is the long pole; start step 0 early).

## Assets and links

| What | Link | Pin |
|---|---|---|
| **Model under audit** `cardiffnlp/twitter-roberta-base-offensive` (RoBERTa-base, tweet offensive-language classifier; labels `non-offensive`/`offensive`; no license in card metadata, which exercises the disclosure-gap path) | https://huggingface.co/cardiffnlp/twitter-roberta-base-offensive | revision `c77b3b9d3b2284d628d03b2d74ccd6dd1bc60698` |
| **Evaluation dataset** Civil Comments, `validation` split (suite used `test`/`train`), new seed, suite texts removed, honest labels (no injected flaws) | https://huggingface.co/datasets/google/civil_comments | revision `f2970eb3a55777454c94069077cc8d9b5866312d` |
| Model's own training data (for the "domain shift" talking point: tweets vs. news comments) | https://huggingface.co/datasets/cardiffnlp/tweet_eval (config `offensive`) | n/a |
| Paper behind the model (documentation-source demo) | https://arxiv.org/abs/2010.12421 (TweetEval) | n/a |

Why this pair: the model was **not** trained on Civil Comments, so this is a real out-of-distribution
audit. Expect imperfect accuracy; that is the point (Robustness and Fairness evidence should show it).
Check beforehand that the model is absent from earlier runs:
`grep -r "twitter-roberta-base-offensive" results/ | head` should print nothing.

## Step 0: setup (before the audience arrives)

```bash
docker compose up -d                 # postgres, redis, api, worker, frontend
cd backend
uv pip install datasets --python .venv/Scripts/python.exe   # once; the backend venv has no pip and no `datasets`
python -m app.scripts.prepare_demo_data --out ../results/demo_unseen_20261028
#  -> demo_eval_set.csv (2 000 rows) + demo_eval_set_manifest.json (sha256, counts)
```

Open http://localhost:5173. Say: everything runs locally; inference happens in the worker on this
machine (RTX 4060 or CPU), not through a cloud API.

## Part A: UI walk-through (each feature, in order)

| # | Do in UI | Show / say | Feature proven |
|---|---|---|---|
| 1 | **Overview** | Counts and recent evaluations are a direct read of persisted state | Local-first dashboard |
| 2 | **Models → Import HF model** → `cardiffnlp/twitter-roberta-base-offensive` | Metadata only, no weights; revision pinned to the commit SHA above; license missing | Hub adapter, revision pinning |
| 3 | **Model detail** | Card text, tags, files, `id2label` snapshot | Card parsing, label-space capture |
| 4 | On the **New evaluation** page (step 2, Datasets & documentation), paste the TweetEval paper URL under *Documentation URL* → **Add documentation source** | Recorded as a declared pointer for a human reviewer; TrustLens does not fetch or hash it, so it shows `not_applicable` (expected). The pinned model card is added automatically and shows `ok` | Documentation sources |
| 5 | **Model detail → Evaluate model → Start evaluation** | Stepper: Model → Datasets & documentation → Review. Model detail URL is `/models/<id>` (the id differs per import) | Draft workflow |
| 6 | **Fairness**: tick *Configure Fairness*, upload `demo_eval_set.csv` | Schema sniff, row count (2000), column types | Dataset intake (URL fetch is SSRF-guarded; upload used here) |
| 7 | **Column mapping**: text=`text`, target=`label`, sensitive=`identity_ref`; min group size 30; *Favorable outcome* = `offensive`. The two label-mapping dropdowns only appear after the columns are chosen: `0→non-offensive`, `1→offensive`. Click **Save & validate**, then **Confirm Fairness** (button reads *Fairness confirmed* when done) | The tool will not guess labels; mapping is explicit and stored in the contract. Save with an unset mapping fails with `references unknown model_label_index=-1` | Evaluation contract v2, label mapping, group gates |
| 8 | **Robustness**: tick *Configure Robustness*, upload the same CSV again (each probe has its own upload), text=`text`, target=`label`, same `0/1` mapping, no sensitive column. **Save & validate → Confirm Robustness** | Character-swap perturbations, budget 0.03 | Robustness probe |
| 9 | **Behavioural safety**: tick *Configure Behavioural safety*, upload the same CSV again, text=`text`, target=`label`, severe-harm column=`severe`, harmful class=`offensive`, same `0/1` mapping. **Save & validate → Confirm Behavioural safety**. The page layout shifts after Save, so re-locate the Confirm button before clicking | Severe-miss rate on rows marked severe and toxic | Safety behaviour probe |
| 10 | **Review step** (bottom of the same page): under *Advanced*, pick **Legacy heuristic scoring** (the default is *Deterministic*, which abstains on every O/S/D; *LLM-assisted* needs keys), then **Continue to review**. The button stays disabled until every ticked probe is confirmed | Read the mode disclosure aloud: what a human must do vs. what is automatic | Dual workflow modes, engine selector |
| 11 | **Run evaluation**; watch the detail page | `PENDING → RUNNING`, dimension chips completing one by one | Async Celery pipeline, live progress |
| 12 | **Dimension cards**. First check the header *Contract* line lists all three probes (`Fairness + Robustness + Safety`); if a probe is missing, its Confirm click did not register and the Safety card will only show the model-card disclosure checks, not the severe-miss rate. | Fairness: DPD/EOD and worst-group gap with bootstrap CI. Robustness: clean vs perturbed accuracy and drop. Safety: severe-miss rate. Integrity: artifact/metadata checks (revision pinned, manifest, license). Explainability: card completeness | All five FRIES probes |
| 13 | **Evidence Dossier** (open Fairness, then Integrity) | Chain tags: Observed evidence → Derived metric → Gate/rule → Risk decision → Human judgment → Limitation | Traceability |
| 14 | Point at any `INSUFFICIENT_EVIDENCE`/`NOT_APPLICABLE`/gate chip, e.g. `G-FAIR-CI-WIDE`, `I-INT-LICENSE-UNDISCLOSED` | The tool withholds instead of inventing a number | Honest abstention, gates, disclosure gaps |
| 15 | **Execution metadata** | Device, GPU name, backend, fallback reason | Hardware evidence |
| 16 | **Review page** (status `AWAITING_REVIEW`) | Proposed O/S/D per aspect, marked `PROPOSED_REQUIRES_VALIDATION`; override one value (e.g. Detection 7→5) and write a rationale | Human-in-the-loop override |
| 17 | **Finalize** | Formula `T_risk = ∛(O·S·D)`; veto if any term is 0; aspect mean; weighted overall; the disclaimer that this is an audit artifact, not a safety proof | FRIES scoring |
| 18 | **Evaluation timeline** | Ordered, append-only lifecycle events | Audit trail |
| 19 | **View report** | Executive assessment, Evidence Traceability panel, Documentation Sources, Reproducibility (revisions, hashes, versions) | Versioned report |
| 20 | **Download JSON and PDF**; show the two hashes | Same source rendered twice, no separate calculation | JSON/PDF reports, hashing |
| 21 | **Publish → Unpublish** | Private by default, opt-in only | Publish flag |
| 22 | **Evaluations history** | Filter, reopen this run | History |
| 23 | **Settings / Documentation pages** | Methodology and configuration in-app | Settings, docs |

## Part B: same run from the terminal (proves the UI is only a client of the API)

```bash
cd backend
python -m app.scripts.run_demo_unseen_model \
    --csv ../results/demo_unseen_20261028/demo_eval_set.csv \
    --out ../results/demo_unseen_20261028/run1
```

It pauses at 9 stages (press Enter; switch to the matching UI page each time): import, upload,
contract+run, per-dimension evidence, O/S/D proposals, human review, finalize, report+events,
publish/unpublish. Add `--no-pause` for a dry run the day before, `--engine llm_v1` if LLM keys exist.
A dry run uses the same model and creates a second evaluation; that is fine, evaluations are append-only.

## Part C: extra proofs (optional, 2 min each)

1. **Integrity tamper detection**: `python -m app.scripts.tamper_demo variant1_fairness` flips one
   weight byte in a copy, re-hashes, and triggers `I-INT-BYTES-DIVERGE` (limit stated in the script:
   a forger who also replaces the reference hash is not caught).
2. **Reproducibility**: re-run the same model + CSV; the revision, dataset hash and seeds in the report
   are identical, so differences are visible rather than hidden. Point at `results/README.md`
   (result folders are never edited, reruns get new folders).
3. **Tests**: `cd backend && pytest -m "not integration" -q` and `cd frontend && npm test`.

## Talking points (read before presenting)

* No score is read from a single metric. Evidence (Layer A) → O/S/D (Layer B, proposed) → FRIES (Layer C).
* Out-of-distribution input is the honest expectation here; low Robustness/Fairness evidence is a
  finding, not a demo failure. Do not retune thresholds live.
* Known limits to say before being asked: text classifiers only for Robustness (character swaps);
  Explainability is card-based, not SHAP/LIME; Safety needs user-supplied labelled data;
  no resource checker; O/S/D bands are heuristics pending validation; the evaluation set is English.
* If the audience asks "is it trustworthy?": TrustLens produces a traceable risk profile, not a verdict.

## Fallbacks

| Problem | Action |
|---|---|
| Cold download of weights is slow | Do step 0 and one `--no-pause` dry run first; the worker caches weights |
| Hub unreachable | Use `results/external_hub_validation_20261003_v9r/` evaluations to show the same screens, and say so |
| First run sits at `RUNNING 0/5` for a minute or two | Normal: the worker is resolving the pinned revision and downloading weights from the Hub (visible in `docker compose logs worker`); no action needed |
| `ModuleNotFoundError: No module named 'datasets'` in step 0 | `uv pip install datasets --python .venv/Scripts/python.exe` from `backend/` (plain `pip` is not in the venv) |
| Worker on CPU only | Lower the size: `prepare_demo_data --size 500` (group gates `n≥30` still hold) |
| Evaluation `FAILED` | Show the error, the `FAILED` event in the timeline, and that failures are recorded rather than hidden |
