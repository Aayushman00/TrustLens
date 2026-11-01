# Supported pairings v1 (model-faithful evaluation)

TrustLens executes **allowlisted** model+dataset combinations through a generic pairing pipeline. FairnessProbe does not embed dataset-specific preprocessing; it resolves a pairing, loads rows via the pairing’s adapter, and runs `InferenceBackend` on the pinned model revision.

## Contract files

| File | Purpose |
|------|---------|
| `configs/supported_pairings_v1.yaml` | Execution allowlist: model SHA, dataset SHA, adapter, label space |
| `configs/datasets_v1.yaml` | Dataset pins (`logical_key`, Hub path, revision, fairness metadata) |
| `backend/app/inference/pairing.py` | `resolve_pairing()`, compatibility checks |
| `backend/app/inference/adapters/` | `ModelInputAdapter` implementations + factory |

## First pairing: HateXplain (multiclass)

| Field | Value |
|-------|-------|
| Pairing id | `hatexplain_bert_v1` |
| Model | `Hate-speech-CNERG/bert-base-uncased-hatexplain` |
| Model revision | `e487c81b768c7532bf474bd5e486dedea4cf3848` |
| Dataset logical key | `hatexplain_fairness` |
| Adapter | `hatexplain_post_tokens_v1` |
| Task | `multiclass_classification` (hate speech / normal / offensive) |
| Sensitive attribute | Annotated target community (majority vote) |

**Content warning:** HateXplain contains hate and offensive speech. Use only in controlled evaluation environments.

### Dataset loading note

The Hub dataset script is not loadable under `datasets` 5.x. Rows are fetched from the canonical GitHub JSON URLs referenced by the original Hub loading script (documented in `datasets_v1.yaml` under `fairness.raw_data_urls`).

### Metrics policy (multiclass / F-FAIR-PERF)

- Multiclass pairing: binary DP/EO are marked `NOT_APPLICABLE` (no binary collapse).
- **F-FAIR-PERF** scores `subgroup_worst_group_acc_gap` (max − min per-group accuracy on groups with `n ≥ min_group_n`).
- **Gates** (from `datasets_v1.yaml` fairness block): `G-FAIR-N-TOTAL` (`n ≥ 200`), `G-FAIR-N-GROUP` (≥2 groups with `n ≥ 50`), `G-FAIR-CI-WIDE` (bootstrap gap CI width `> 0.15` → `mapping_blocked`, no trigger).
- **Trigger:** gap `> 0.02` **and** bootstrap 95% CI lower bound `> 0.02` → `scored_risk_id: F-FAIR-PERF`.
- Bootstrap: row resample with replacement, `B=1000`, seed = probe seed.
- Evidence artifact: methodology v1.0 JSON (`methodology_version: tl-methodology-v1.0`) with `metrics`, `uncertainty`, `reliability`, `osd_proposals: []`.
- O/S/D mapping and `osd_proposals` population are **out of scope** for this slice.

### Sensitive attribute

Resolved in order: `probe_config.extra.sensitive_attribute` → `slice_definitions.sensitive_attribute` → dataset `fairness.default_sensitive_attribute`. Must appear in `fairness.sensitive_attributes`; never inferred from the model. HateXplain default: `target_community` (adapter maps annotator target majority vote into row field `sensitive`).

## Probe behavior

| Condition | Path | Status |
|-----------|------|--------|
| Pairing resolved (multiclass) | Adapter → `LocalHFBackend` → F-FAIR-PERF evaluator | `EVALUATED` or `INSUFFICIENT_EVIDENCE` |
| Adult tabular (no pairing) | sklearn logistic regression proxy | `PROXY` |
| NLP dataset without pairing | Skip | `NOT_APPLICABLE` |
| Pairing path failure | No LR fallback | `FAILED` |

`PROXY` and `NOT_APPLICABLE` fairness results do not produce O/S/D bands in the OSD agent.

## Adding a second pairing

1. Pin the dataset in `configs/datasets_v1.yaml` (include `fairness` block when needed).
2. Add an entry to `configs/supported_pairings_v1.yaml` with full SHAs.
3. If Hub rows are already `{text, label, sensitive}`, use `input_adapter: plain_text_v1`.
4. Otherwise implement `your_adapter_v1` and register it in `backend/app/inference/adapters/registry.py`.

No FairnessProbe changes are required for new pairings that fit the contract.

## Smoke test

From the repo root with `backend[dev,fairness,robustness]` installed and network access:

```powershell
python backend/scripts/smoke_model_faithful.py --n 56 --seed 42
```

## Tests

- CI (network-free): `pytest -m "not integration"` from `backend/`
- Live Hub integration (opt-in): `TRUSTLENS_LIVE_TESTS=1 pytest -m integration backend/tests/test_pairing_integration.py`
