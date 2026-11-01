# ADR 0014 — Hard-fail evidence is non-overridable

Status: **proposed** (v2). Supersedes nothing; extends ADR 0013.

## Context

v1 lets a human type any O/S/D, including a veto (0). Integrity findings (a hash mismatch, a dangerous pickle opcode) are facts about the artefact, not judgements. If a reviewer can override them, the audit's strongest signal becomes the easiest to wave away, and a report saying "ADOPT" on a tampered file is worse than no report. Against that, hash checks have false-positive paths: a repository re-uploaded under the same revision label, a locally re-converted file, a mirror.

## Decision

Split integrity findings into two tiers.

| Tier | Finding | Machine action | Overridable? |
| ---- | ------- | -------------- | ------------ |
| A — verified fault | Artefact sha256 differs from an *authoritative* reference (Hub LFS hash at the pinned revision, or a user-supplied signed manifest); pickle scan finds a callable on the versioned denylist (`integrity/denylist-v1`); `trust_remote_code` payload present and the run policy forbids it | `REJECT` (hard fail) | **No.** No override control exists in API or UI |
| B — unverifiable | No reference hash available, revision not pinned, licence undeclared, scan not possible, pickle references a callable that is neither allowlisted nor denylisted (spike S7: `training_args.bin` references `__main__` classes) | Not a hard fail. Becomes `insufficient_evidence` / lowers `ADOPT` eligibility through the loss profile; may trigger `COLLECT_MORE_EVIDENCE` | Reviewer may record a justified note; the note is stored beside, never inside, machine output |

A Tier A finding is resolved by **changing the facts, not the verdict**: re-download at the pinned revision, pin a different revision, or declare a different artefact. Each resolution is a new evaluation with its own evidence hashes. The old REJECT stays in history.

A reviewer MAY attach an `acknowledged_risk` annotation to a Tier A report (e.g. "research use in an air-gapped sandbox"). The annotation is displayed prominently, the action stays `REJECT`, and exported reports carry the annotation next to the verdict.

## Consequences

- Removes K5 (a veto can only come from a human): vetoes now come from evidence.
- The decision engine treats Tier A as `loss(ADOPT) = loss(ADOPT_WITH_CONTROLS) = ∞` (spec 03).
- Costs convenience in the false-positive cases, mitigated by explicit re-verification flow and a clear "how to resolve" message with the differing file and both hashes.
- The Tier A list is closed and versioned; adding to it requires an ADR so that "hard fail" cannot quietly expand into general strictness.

## Alternatives considered

- *Fully overridable with justification.* Rejected: the exact scenario the audit exists to catch.
- *Everything integrity-related is hard fail.* Rejected: unverifiable is not the same as faulty, and punishing missing metadata would turn disclosure gaps into rejections (the distinction v1 was built around).
