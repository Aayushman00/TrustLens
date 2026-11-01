# 05 — Scope expansion

"Any machine-learning model" is the direction, not the first release. v2 defines a **capability ladder**; each rung ships only when its probes meet the spec 02 acceptance and its TrustBench stratum exists.

## Ladder

| Rung | Model family | Interface | Probes available | Status |
| ---- | ------------ | --------- | ---------------- | ------ |
| R0 | HF text classification (binary + multiclass), English | `LocalHFBackend` (exists) | all spec 02 text probes | v1 baseline, extended |
| R1 | Same, additional tasks and languages: sentiment, topic, NLI, toxicity in ≥ 2 more languages | same | counterfactual lexicons per language | v2 target |
| R2 | Tabular classifiers (scikit-learn/ONNX/XGBoost pickles via safe loaders) | `TabularBackend` | group gap, intersectional, calibration, feature-perturbation robustness, SHAP-based faithfulness, integrity | v2 target |
| R3 | Image classifiers (HF `image-classification`, torchvision) | `ImageBackend` | group gap (when labelled), corruption robustness (noise/blur/JPEG), calibration, occlusion faithfulness, integrity | v2 stretch |
| R4 | Generative LLMs (chat/completion) | `GenerativeBackend` | refusal and toxicity eval sets, counterfactual prompt pairs, jailbreak suite, consistency, integrity | post-v2 |

R0–R2 are committed; R3 is stretch; R4 is explicitly out of the v2 release but the interfaces must not block it.

## Interfaces

```
ModelAdapter     resolve(ref) -> ModelHandle (revision, artefact hashes, card, licence)
InferenceBackend load(handle), predict_proba(batch), device_info()     # exists; generalise batch type
TaskSpec         {task: text_cls|tabular_cls|image_cls|…, labels, positive_class, input_schema}
DatasetAdapter   open(source) -> Rows with declared schema, sha256, licence
Perturbation     (input, rng, budget) -> input'; declares invariance contract (label-preserving?)
Probe            applicable(TaskSpec, ModelHandle, Dataset) -> Applicability; run(ctx) -> [EvidenceItem]
```

A probe declares what it requires (probabilities? gradients? group labels?). The planner computes the **applicability matrix** per evaluation and shows it before running; unsupported probes appear as `not_applicable(reason)`, never silently dropped (v1's `unsupported_modality` soft-skip becomes a first-class state).

## Model sources

- Hugging Face Hub (exists; keep token handling hardened).
- Local folder / file upload with manifest hashing (exists; extend).
- Remote inference endpoint (black-box `predict` only): property probes that need only predictions run; weight-integrity and gradient-based probes are `not_applicable`. Useful for API-served models; MUST record that behavioural, not artefact, identity was audited.

## Dataset handling

- Bundled **probe packs** per task, with licence and provenance: counterfactual identity lexicons, perturbation seeds, severe-harm subsets, small stress sets. Users can add their own.
- User CSV contract (exists) gains: schema validation report, automatic label-mapping suggestion with mandatory confirmation, class-balance and group-size preview with minimum-support warnings before the run.
- Dataset compatibility guard: refuse or warn when label cardinality does not match the model head (v1 left this to the user).

## Languages

R1 adds language as a first-class field on the task spec. A probe whose lexicon or perturbation lacks the language is `not_applicable(language)`; it does not fall back to English.

## Explicit limits (to state in the product)

- Fairness evidence is only as good as the demographic lexicon or labelled column used; the tool does not infer protected attributes.
- Explanations are audited for faithfulness to the model, not for usefulness to a human.
- A pass is not a certificate; the decision is conditional on the profile and evidence budget.

## Acceptance for a new rung

1. TaskSpec + adapters + backend with unit tests.
2. ≥ 3 property probes meeting spec 02 acceptance.
3. TrustBench stratum (≥ 10 models incl. ≥ 4 controlled-defect) and a validity report.
4. Docs: supported-pairing table (model type × dataset × probes) auto-generated from the registry, replacing the hand-written v1 matrix.
