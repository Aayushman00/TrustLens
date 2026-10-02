# ADR 0013 — Artifact-set integrity (round 3, L7)

- **Status:** accepted, 2026-10-03.
- **Methodology:** `tl-integrity-v1.1` → `tl-integrity-v1.2`; global
  `v6-eod-fairness-risk-2026` → `v7-artifact-set-integrity-2026`.
- **Supersedes:** ADR 0012's "never reads weight bytes" rule, for the Integrity hash check
  only. Hub import itself still downloads no weights.

## Context

Up to v1.1, Integrity hashed one file: `model.safetensors` or `pytorch_model.bin`.
- **Hub models:** the hash was compared with that file's LFS sha256.
- **Local folders:** it was compared with `train_manifest.json`'s
  `model_safetensors_sha256`.

That leaves three gaps:
- A sharded checkpoint (`model-0000k-of-0000n.safetensors` plus an index) was not
  verified at all.
- An edited `config.json` or tokenizer changes what the model computes, and was not
  detected.
- An extra weight file next to the attested one was not noticed.

## Decision

`integrity_artifact.verify_local_artifacts` (local folders) and `hub_weight_hashes` (Hub)
record a structured `artifact_verification`. It is stored in the probe metrics **and** in
the persisted evidence artifact.

### What goes in the set

The set is enumerated deterministically, from top-level files only:

| Part | Files |
|---|---|
| Weights | `model.safetensors.index.json` / `pytorch_model.bin.index.json` and every shard its `weight_map` names; otherwise the single `model.safetensors` / `pytorch_model.bin` |
| Loader files | `config.json`, `generation_config.json`, the tokenizer files (`tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `added_tokens.json`, `vocab.txt`, `vocab.json`, `merges.txt`, sentencepiece models) |
| Other weight-like files | `.safetensors`, `.bin`, `.pt`, `.pth`, `.ckpt`, `.h5`, `.msgpack`, `.gguf`, `.onnx`. These are hashed so that an unexpected one can be detected |

READMEs, `train_manifest.json`, `artifact_manifest.json` and subdirectories are outside
the set.

### The authoritative manifest

The first one found is used:
1. **Operator manifest:** `probe_config.extra.integrity.artifact_manifest`, as
   `{"files": {name: sha256}}`.
2. **Folder manifest:** `artifact_manifest.json` in the folder
   (`trustlens-artifact-manifest-v1`, written by `build_artifact_manifest`).
3. **Legacy:** `train_manifest.json`'s `model_safetensors_sha256`. It covers a single
   `model.safetensors` only.

The manifest identity is the sha256 of the canonical, sorted `{name: sha256}` map.

### Statuses

| Status | When | Integrity outcome |
|---|---|---|
| VERIFIED | Every manifest file is present and matches | `hash_comparison = match`; no risk |
| MISMATCH | A file differs from the manifest, or a weight file the manifest does not list is present | `hash_comparison = diverge` → `I-INT-BYTES-DIVERGE` (risk) |
| INCOMPLETE | A file the manifest or the weight index expects is absent | Not a risk. Failed gate `G-INT-ARTIFACT-INCOMPLETE`; the hash is not compared |
| UNPINNED | Hashes are recorded but there is no manifest | Not a risk and not a gap. The folder is content-addressed, as in L3 |
| UNSUPPORTED / UNVERIFIABLE | No single or sharded safetensors / `.bin` checkpoint (for example GGUF only), or the lookup failed | `performed: false`; the hash is not compared |

`artifact_verification` carries:
- the filenames, observed and expected sha256 and per-file state (`match`, `changed`,
  `missing`, `unexpected`, `unattested`, `recorded`);
- the manifest source, coverage and identity;
- the mismatch details;
- the set digest.

**A non-weight file the manifest does not list** is reported as `unattested`, not as a
mismatch. A weights-only manifest is therefore still usable.

**Single-file folders keep the L3 identity** when there is no set manifest: the weight
file's sha256, checked against `train_manifest.json`. Stored L3 identities stay
comparable.

**Hub models:** every weight shard is checked against its LFS sha256. Non-LFS files have
no sha256 reference on the Hub and are not compared.

## What it verifies

Artifact integrity verifies one thing: **the bytes evaluated are the bytes a stated
manifest attests**, for the files the loader reads.

## What it does not verify

- **The model is not shown to be safe.** A match does not show the absence of
  backdoors, trojans, data poisoning, malicious training or behavioural manipulation.
  Those would be in the attested bytes themselves.
- **Who produced the manifest is not verified.** This is not a PKI and does not check
  signatures. A folder `artifact_manifest.json` can be rewritten by anyone who can
  rewrite the folder. It catches accidental, partial or uncoordinated change, not a
  capable attacker. An operator-supplied manifest held elsewhere is stronger.
- **Tampering is not proven.** A mismatch shows the bytes differ. It does not show
  tampering or intent.
- **License, card claims and provenance are not covered.** Those remain disclosure
  checks.

## L3 distinction preserved

Missing disclosure or metadata never becomes an integrity risk:
- a missing manifest is UNPINNED;
- a missing license or revision is a `disclosure_gap`;
- an absent artifact is INCOMPLETE, an unverified gate.

Only positive evidence of divergence — changed bytes, an unexpected weight file, or
listing drift — goes into `risks_triggered`.
