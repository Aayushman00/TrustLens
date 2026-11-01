# TRUSTLENS — MASTER DEMO + VIVA SCRIPT

> Written in first person, for the person presenting TrustLens as their own project.
> Grounded directly in the current implementation (backend `FastAPI` app, `worker` Celery
> service, `frontend` React/Vite app, Postgres/Redis/MinIO via Docker Compose). Nothing
> in this script describes a feature, endpoint, UI screen, or metric that isn't actually
> in the codebase as of this write-up. Where something is planned but not built, it is
> explicitly labeled POST-MVP.

---

## PART 1 — PROJECT AT A GLANCE

TrustLens is a local-first system I built that takes a Hugging Face model, runs a fixed
set of measurements against it across five dimensions — Fairness, Robustness, Integrity,
Explainability, Safety — and produces a report that separates **what was actually
measured** from **what a human decided about it**. It never invents a "the model is
safe" verdict. If the evidence isn't there, it says so instead of guessing.

**What actually exists today:**
- A React/TypeScript frontend (Vite build) talking to a FastAPI backend over a versioned
  REST API (`/v1/...`).
- A Celery worker (Redis broker) that does the actual model loading and inference,
  separate from the API process.
- PostgreSQL for all evaluation state, lifecycle, and audit history.
- MinIO (S3-compatible) for evidence artifacts and generated reports/PDFs.
- Everything runs from one `docker-compose.yml` — Postgres, Redis, MinIO, the API, the
  worker, and the frontend are all services in the same compose file.
- 536 backend tests (pytest, real Postgres) and 30 frontend tests (Vitest + Node's
  built-in test runner) passing as of the last full run I did.

**What it is not:** it is not a cloud SaaS product, it does not do behavioral safety
red-teaming, it does not do SHAP/LIME explainability, and it does not let an LLM invent
a trust score. All of that is either out of scope by design or explicitly deferred —
covered in Part 16.

---

## PART 2 — 10-MINUTE HAPPY-PATH DEMO SCRIPT

This is the condensed version — see Part 3 for the full step-by-step with talking
points. Use this as your run-sheet during the actual demo.

1. Open the app at `http://localhost:5173`, log in. Land on **Overview**.
2. Go to **Models → Import HF model**. Import an already-cached model (e.g.
   `textattack/bert-base-uncased-SST-2`) so it doesn't wait on a cold download.
3. **New evaluation** → pick the model → pick **Robustness** → pick the one approved
   contract shown → **Review** → **Run evaluation**.
4. Watch the evaluation detail page poll from `PENDING` → `RUNNING` → dimension chips
   turning "done" one at a time → `FINALIZED`.
5. Point at the **Robustness** dimension card: clean accuracy, robust accuracy, accuracy
   drop, the named risk.
6. Open **Evidence Dossier** for Robustness, point at the `EvidenceChainTag` labels
   (Observed evidence / Derived metric / Gate/rule / Risk decision / Human judgment /
   Limitation).
7. Point at the **Overall FRIES assessment** card — explain it's withheld here because
   no human has entered O/S/D yet (autonomous mode, deterministic engine never invents
   O/S/D).
8. Open **Evaluation timeline** — point at the ordered lifecycle events.
9. Click **View report** → show the Report page: Executive Assessment, Evidence
   Traceability panel with the same tags, Documentation Sources, Reproducibility
   section.
10. Click **Download JSON** and mention PDF generation is the same document rendered
    through WeasyPrint — same source, no separate calculation.

---

## PART 3 — DETAILED STEP-BY-STEP DEMO

### STEP 0 — Starting the local application

**WHAT I DO**
I open a terminal in the project root and run `docker compose up -d`, then I open
`http://localhost:5173` in the browser. I log in with a seeded account.

**WHAT I SHOULD SEE**
Compose brings up six containers: `postgres`, `redis`, `minio` (plus a one-shot
`minio-init` that creates the bucket), `api`, `worker`, `frontend`. The login page
loads, and after login I land on the **Overview** page.

**WHAT I SAY**
"Everything you're about to see is running on this laptop. There's no cloud service
behind this — Postgres, Redis, MinIO, the API, and the worker are all containers on
this machine, started from one `docker-compose.yml`."

**WHAT IT MEANS**
The whole stack — API, background worker, database, object storage — is defined as
one Compose file with explicit service dependencies, so the system starts in a known
order and every piece is independently inspectable (`docker logs`, `docker exec`).

**WHY THIS DESIGN**
I wanted a system a professor — or anyone — could clone and run without me owning any
infrastructure, and where every evaluation happens on hardware I control, not a
third-party API.

**IMPORTANT POINT TO EMPHASIZE**
"Nothing about this evaluation touches a cloud model API — the actual inference
happens in the worker container, on this machine's GPU or CPU."

**LIKELY PROFESSOR QUESTION**
1. "Why not just deploy this to the cloud?"
2. "What if I don't have Docker?"

**ANSWER**
1. "Local-first was a deliberate choice — I cover the reasons in detail later, but
   short version: privacy of the model/dataset, full control of the execution
   environment, and reproducibility of exactly what ran."
2. "Docker Compose is the only hard dependency for running the full stack; the backend
   and worker can also run natively against a local Postgres/Redis/MinIO if someone
   doesn't want containers, which is what I actually used while developing this."

---

### STEP 1 — Landing page / Overview

**WHAT I DO**
I land on `/` — the **Overview** page.

**WHAT I SHOULD SEE**
The header text "TrustLens Local Engine — evaluations run and store evidence on this
machine," an **Import HF model** button, and — once there's history — counts of
running/finalized evaluations plus a list of recent evaluations with their status
badges.

**WHAT I SAY**
"This is the landing page. It's intentionally simple — a summary of recent activity and
one button to bring in a new model."

**WHAT IT MEANS**
This page just calls `GET /v1/models` and `GET /v1/evaluations` and renders what comes
back — there's no separate dashboard-computation service.

**WHY THIS DESIGN**
I didn't want a landing page that pretends to know more than the API actually returns —
what you see here is exactly the persisted state.

**IMPORTANT POINT TO EMPHASIZE**
"There's no separate analytics layer here — this page is a direct read of the same data
every other page reads."

**LIKELY PROFESSOR QUESTION**
"Is this real-time?"

**ANSWER**
"It loads once on page open. The evaluation detail page is the one that polls, because
that's the page where state is actually changing while you watch it."

---

### STEP 2 — Importing a model

**WHAT I DO**
I go to **Models → Import HF model**, type a Hugging Face repo id (for example
`textattack/bert-base-uncased-SST-2`), and submit.

**WHAT I SHOULD SEE**
A new model row appears with the repo id, a real pinned revision (a git commit SHA from
the Hub), a license, and the raw model card tags. If I re-import the same repo id later,
it refreshes the metadata/revision rather than creating a duplicate.

**WHAT I SAY**
"I'm importing a model by its Hugging Face repo id. This call goes to the Hub's metadata
API — it does not download model weights at this step, only the card, file list, and
the current revision."

**WHAT IT MEANS**
Behind this button is `POST /v1/models/import-hf`, which resolves the repo through a
model-adapter layer restricted to `huggingface.co`/`www.huggingface.co`, pins the exact
revision, and stores the card text and metadata in Postgres.

**WHY THIS DESIGN**
I separated "register this model" from "run inference on it" so that importing is fast,
safe, and doesn't need a GPU — Integrity, Explainability, and Safety only need the card
metadata, not the weights.

**IMPORTANT POINT TO EMPHASIZE**
"The revision gets pinned right here, at import time — that's the exact commit every
later evaluation freezes against, not whatever 'main' happens to point to tomorrow."

**LIKELY PROFESSOR QUESTION**
1. "What if the repo doesn't exist, or is private?"
2. "Can I import from an arbitrary URL?"

**ANSWER**
1. "It returns a structured 404 if the repo/revision isn't found, and a 403 if it's
   gated and I haven't configured a Hugging Face token."
2. "Only `huggingface.co` — the import path validates the repo id against a strict
   pattern and only ever talks to the Hub's own host allowlist, so there's no arbitrary
   URL fetching here."

---

### STEP 4 — Creating an evaluation: choosing the model and category

**WHAT I DO**
I click **New evaluation** (or **New evaluation** from a model's detail page), pick the
imported model, then choose a category: **Fairness**, **Robustness**, or
**Documentation & Governance**.

**WHAT I SHOULD SEE**
A stepper at the top (Model → Category → Source/Contract → Review). For Robustness, the
button is disabled with "No approved contract for this exact model + revision" if
nothing matches. For Documentation & Governance, it says "Integrity, Explainability and
Safety — always available, no local inference."

**WHAT I SAY**
"TrustLens never free-text evaluates a model. Every run has to match an approved
contract, or it uses the documentation-only path — there's no 'just run everything and
see what happens' button."

**WHAT IT MEANS**
Each button here reflects `GET /v1/models/{id}/evaluation-options`, which checks the
imported model+revision against two YAML registries — `supported_pairings_v1.yaml` for
Fairness model-faithful pairings, and `supported_robustness_compat_v1.yaml` for
Robustness — and only enables what's actually approved for this exact revision.

**WHY THIS DESIGN**
If I let people evaluate any dataset against any model, the numbers would be
uncomparable and the "gates" (minimum sample size, label compatibility) would be
meaningless. Pinning the pairing to an exact model+dataset+revision combination is what
makes the resulting metric actually mean something.

**IMPORTANT POINT TO EMPHASIZE**
"This button being disabled is itself a feature — it's the system refusing to let me
run an unapproved comparison."

**LIKELY PROFESSOR QUESTION**
1. "What if I want to test a completely different model?"
2. "Who approves a new pairing?"

**ANSWER**
1. "I can always evaluate Integrity/Explainability/Safety — those are documentation
   checks, always available. For Fairness there's also the 'my local dataset' path,
   which doesn't need a pre-approved pairing at all."
2. "Right now it's a YAML file I maintain — adding a new pairing means adding an entry
   with the exact model revision, dataset revision, and task type, which is deliberately
   a manual, reviewed step, not automatic."

---

### STEP 5 — Choosing the source / evaluation contract

**WHAT I DO**
For Fairness, I additionally choose between **Approved benchmark** and **My local
dataset**. I then pick the actual contract card from the catalog (or, for a local
dataset, upload a CSV and pick target/text/group columns).

**WHAT I SHOULD SEE**
The **Review before running** screen: model + revision, the contract's label, "Local
inference" as the execution mode, and a per-dimension outcome list (e.g. Fairness: "Not
applicable", Robustness: "Model-faithful", Integrity/Explainability/Safety: "Will run").

**WHAT I SAY**
"This is the frozen evaluation contract. Model reference, model revision, dataset
identity, dataset revision — everything gets locked in right here, before anything
runs."

**WHAT IT MEANS**
On submit, the backend calls `build_evaluation_contract(...)`, which never trusts a
client-supplied revision — it re-reads the model row's own stored revision and freezes
it, along with the dataset key/revision from the registry, into a JSON object
(`EvaluationContractV1`) that's saved on the evaluation row and sent to the worker.

**WHY THIS DESIGN**
If the model on the Hub gets updated between when I click "New evaluation" and when the
worker actually picks up the job, I don't want the evaluation silently running against a
different model. Freezing the contract at creation time is what makes the whole
evaluation reproducible after the fact.

**IMPORTANT POINT TO EMPHASIZE**
"Once this contract is frozen, nothing later in the pipeline is allowed to substitute a
different model or dataset revision — even if the live Hub repo changes underneath it."

**LIKELY PROFESSOR QUESTION**
1. "What's actually inside this contract object?"
2. "Why not just always use the 'current' model?"

**ANSWER**
1. "Schema version, contract kind — registry pairing, proxy, user dataset, or
   documentation-only — model ref and revision, dataset key and revision, and for the
   user-dataset path, the dataset's own content hash and the column names."
2. "Because 'current' isn't a fixed point — if I ran the same evaluation again next
   week and the model changed, I'd get a different number under the same label, and I'd
   have no way to explain why."

---

### STEP 6/7/8 — Starting the evaluation: PENDING → RUNNING

**WHAT I DO**
I click **Run evaluation**.

**WHAT I SHOULD SEE**
I'm redirected to the evaluation detail page. The status badge shows `PENDING`
immediately, then flips to `RUNNING` within a second or two, with a progress bar and a
row of dimension chips ("Fairness · pending", "Robustness · pending", etc.) that flip to
"done" one at a time.

**WHAT I SAY**
"The moment I clicked Run, the API created the row as PENDING and handed the actual work
off to a background worker — the browser isn't blocked waiting for inference to
finish."

**WHAT IT MEANS**
`POST /v1/evaluations` inserts the row, then calls `enqueue_evaluate_model(...)`, which
sends a Celery task (`trustlens.evaluate_model`) over Redis. The worker picks it up,
and its very first action is an atomic, conditional database update — only if the row
is still `PENDING` does it flip to `RUNNING`; otherwise it's a safe no-op.

**WHY THIS DESIGN**
Model inference can take anywhere from a couple of seconds to a couple of minutes. If
the API tried to do that inline, the HTTP request would time out or block the whole
process. Splitting "accept the request" from "do the work" is the standard fix for
long-running jobs — and it also means if a message ever gets delivered twice, the
CAS check makes sure the pipeline only actually runs once.

**IMPORTANT POINT TO EMPHASIZE**
"That PENDING → RUNNING flip is a conditional database update, not a plain write — it
only succeeds if the row is still exactly PENDING, which is what stops the same
evaluation from ever being run twice."

**LIKELY PROFESSOR QUESTION**
1. "What if the message queue fails to deliver the task?"
2. "What if two workers pick up the same task?"

**ANSWER**
1. "That's a confirmed enqueue failure — I have an admin-only endpoint,
   `reconcile-enqueue`, that only acts when the evaluation's own event history
   confirms the enqueue actually failed, and it just re-sends the same frozen payload."
2. "The conditional update I just mentioned handles that — only one of them can
   successfully flip PENDING to RUNNING; the other sees the row already changed and
   exits cleanly, logging that it skipped a no-longer-pending evaluation."

---

### STEP 9 — Worker execution / model loading

**WHAT I DO**
Nothing — I just watch, or optionally show the worker container logs
(`docker logs -f trustlens-worker` or the compose service name).

**WHAT I SHOULD SEE**
In the logs: the Hub metadata calls for the model, "Loading weights" progress, then a
line like `inference_loaded model_ref=... revision=... device=...`, followed by one
`probe_complete` line per dimension.

**WHAT I SAY**
"This is the worker actually loading the model with Transformers and placing it on
whichever device it detected — GPU if one's available, CPU if not — and then running
each probe in turn."

**WHAT IT MEANS**
The worker's device-selection code calls `torch.cuda.is_available()` for real; it never
fabricates a device name. Whatever it detects gets written once into the evaluation's
`execution_metadata` and is the same value surfaced later in the UI, the API response,
and the report.

**WHY THIS DESIGN**
I wanted the "was this actually on a GPU" question to have one honest answer, recorded
at the moment inference happened — not a claim added afterward.

**IMPORTANT POINT TO EMPHASIZE**
"If there's no GPU, this doesn't silently pretend there is one — it records `cpu` and
the real reason it fell back."

**LIKELY PROFESSOR QUESTION**
"Did you actually verify GPU execution, or just configure it?"

**ANSWER**
"Both, and I keep them separate. GPU passthrough is *configured* by default in
`docker-compose.yml`. I *verified* it live — rebuilt the worker with that same default
config, ran a real evaluation, and confirmed `execution_device: cuda`,
`cuda_available: true`, and the real GPU name showed up identically in the database, the
API response, and the generated report."

---

### STEP 10 — Fairness

**WHAT I DO**
I open the Fairness dimension card / Evidence Dossier once the evaluation finishes (see
Part 4 for the concrete real numbers I use here).

**WHAT I SHOULD SEE**
Either "Not applicable" (if the contract didn't select Fairness), or, if it did: a
disparity metric (demographic parity difference, or worst-group accuracy gap), the
fairness mode (model-faithful / proxy / user-defined local), per-group evidence, and a
risk interpretation line.

**WHAT I SAY**
"Fairness measures how the model's predictions differ across groups in the selected
dataset — it doesn't decide whether that difference is acceptable, it reports the
number and lets the gate/risk logic name it."

**WHAT IT MEANS**
The probe computes disparity statistics (demographic parity difference, equalized odds
difference, or worst-group accuracy gap depending on the task), checks a minimum
group-size gate (`min_group_n`, default 30), and — only if that gate passes — may name a
risk.

**WHY THIS DESIGN**
A disparity computed from six examples per group isn't reliable. The gate exists so a
tiny, noisy subgroup difference can't get dressed up as a named risk.

**IMPORTANT POINT TO EMPHASIZE**
"If a group has too few rows, Fairness reports insufficient evidence instead of a
number it can't stand behind."

**LIKELY PROFESSOR QUESTION**
"Does TrustLens decide what counts as a 'sensitive attribute'?"

**ANSWER**
"No — for the user-dataset path, I pick the group column myself when I set up the
evaluation. TrustLens never infers which column is a protected attribute; that's a
human decision at setup time, not something the system guesses."

---

### STEP 11 — Robustness

**WHAT I DO**
Open the Robustness dimension card / Evidence Dossier.

**WHAT I SHOULD SEE**
Attack type (`char_swap`), clean accuracy, robust accuracy, accuracy drop, and — if the
drop clears the threshold with its confidence interval — the named risk `R-ROB-PERT`.

**WHAT I SAY**
"This runs the model on the clean benchmark, then on a character-perturbed version of
the same inputs, and compares accuracy."

**WHAT IT MEANS**
Concretely, the probe applies a seeded character-swap perturbation, requires 100%
perturbation coverage of the evaluated sample, needs at least 200 requested rows / 100
actually evaluated, checks label compatibility (at least 95% of labels must map onto the
model's label space), and only names the risk `R-ROB-PERT` if the accuracy drop exceeds
0.05 **and** the bootstrap confidence interval's lower bound also exceeds 0.05.

**WHY THIS DESIGN**
A single perturbed run could get lucky or unlucky. Requiring both the point estimate
*and* the confidence interval to clear the threshold means a single noisy sample can't
trigger a named risk on its own.

**IMPORTANT POINT TO EMPHASIZE**
"This is one specific, well-defined attack — character-swap perturbation — not a claim
about robustness to every kind of adversarial input."

**LIKELY PROFESSOR QUESTION**
1. "Why character-swap specifically?"
2. "What's the bootstrap for?"

**ANSWER**
1. "It's a simple, reproducible, seeded perturbation that's easy to audit — a
   deliberately narrow, well-understood starting point rather than an open-ended
   adversarial search."
2. "It gives me a confidence interval around the accuracy drop — 1,000 resamples,
   percentile method — so I'm not naming a risk off one point estimate that could just
   be sampling noise."

---

### STEP 12 — Integrity

**WHAT I DO**
Open the Integrity dimension card / Evidence Dossier.

**WHAT I SHOULD SEE**
Checks like "revision pinned", "manifest present", "license disclosed", displayed as a
checklist, with named risks such as `I-INT-REV-UNPINNED`, `I-INT-MANIFEST-MISSING`,
`I-INT-LICENSE-UNDISCLOSED`, `I-INT-BYTES-DIVERGE` only where they actually apply.

**WHAT I SAY**
"Integrity checks whether the model's identity and provenance are properly disclosed —
is the revision pinned, is there a file manifest, is the license stated."

**WHAT IT MEANS**
This is entirely metadata-driven — no inference, no weights loaded — comparing what the
Hub reports against what TrustLens expects for a well-documented model.

**WHY THIS DESIGN**
Provenance problems (an unpinned revision, an undisclosed license) are objectively
checkable from metadata; I didn't want to blend that with anything requiring a
judgment call.

**IMPORTANT POINT TO EMPHASIZE**
"A named Integrity risk here is not proof of tampering or malicious intent — it's a
disclosure gap, and the code says so explicitly in its own claim text."

**LIKELY PROFESSOR QUESTION**
"Can Integrity detect if someone swapped the model weights?"

**ANSWER**
"Only if I supply a trusted reference hash to compare against — and even then, a match
or mismatch is a hash comparison, not a cryptographic identity proof from a PKI. That
limitation is written directly into the probe's own claim text."

---

### STEP 13 — Explainability

**WHAT I DO**
Open the Explainability dimension card / Evidence Dossier.

**WHAT I SHOULD SEE**
A **Documentation coverage** value (a ratio, not a score out of 10), a checklist of
which model-card sections are present, and — if the card is missing — "Documentation
coverage is not equivalent to explanation quality" plus an explicit
`CLAIM_NOT_ESTABLISHED`-style disclaimer.

**WHAT I SAY**
"Explainability here means: does the model card actually explain how this model works
and what it's for. It's a documentation check, not a SHAP or LIME analysis of the
model's internals."

**WHAT IT MEANS**
The probe reads the pinned model card text, checks for expected sections (intended use,
limitations, training data, evaluation, etc.), and reports coverage. Nothing here
touches the model's weights or runs an explanation algorithm.

**WHY THIS DESIGN**
I don't have a validated, general-purpose behavioral explainability method to run
against arbitrary Hub models, so I refused to fake one. Documentation completeness is
something I can measure honestly today.

**IMPORTANT POINT TO EMPHASIZE**
"You will never see the words 'Explainability score' anywhere in this system — only
'Documentation coverage,' on purpose."

**LIKELY PROFESSOR QUESTION**
"So this doesn't tell me if the model is actually explainable?"

**ANSWER**
"Correct, and I say that explicitly in the UI. Real behavioral explainability — SHAP,
attention analysis, counterfactuals — is future work, listed under Track 2 in my
roadmap, not something this measures today."

---

### STEP 14 — Safety

**WHAT I DO**
Open the Safety dimension card / Evidence Dossier.

**WHAT I SHOULD SEE**
A governance/disclosure checklist (e.g. is there a stated intended use, misuse
guidance, ethical considerations section) plus lexical flags for certain high-impact
phrases in the card text, and the same "Documentation coverage" wording — never
"Safety score."

**WHAT I SAY**
"Safety here checks whether the model's own documentation discloses governance
information — intended use, misuse warnings — not whether the model actually behaves
safely under adversarial prompts."

**WHAT IT MEANS**
Same shape as Explainability: metadata and card-text analysis only. No prompts are sent
to the model to test for harmful outputs.

**WHY THIS DESIGN**
Real red-teaming/behavioral safety testing is a substantial, separate research problem;
building it into the MVP without validating the methodology would have meant
fabricating confidence I don't have.

**IMPORTANT POINT TO EMPHASIZE**
"There is no red-teaming, no jailbreak testing, and no refusal-rate measurement
anywhere in this codebase — Safety today is a documentation/governance check, full
stop."

**LIKELY PROFESSOR QUESTION**
"Can you tell me if this model will refuse harmful requests?"

**ANSWER**
"No — that's outside what Track 1 Safety measures. It's explicitly future work; I list
it as such rather than let the dimension name imply more than it does."

---

### STEP 15 — Evidence collection

**WHAT I DO**
No separate action — this is what just happened behind steps 10–14.

**WHAT I SAY**
"Every probe that just ran wrote its own evidence artifact to object storage and its own
summary row to Postgres — nothing here is recomputed later."

**WHAT IT MEANS**
Each probe result is persisted as a `ProbeResult` row (dimension, status, metric
values, confidence, evidence references) plus a JSON evidence artifact in MinIO,
content-hashed at write time.

**WHY THIS DESIGN**
Append-only, hash-verifiable evidence means the report and the UI can both point back
to the exact same artifact instead of two different recomputations that could quietly
drift apart.

**IMPORTANT POINT TO EMPHASIZE**
"The Evidence Dossier, the dimension card, and the report all read from this same
persisted row — there's exactly one source of truth."

**LIKELY PROFESSOR QUESTION**
"What if two probes disagree?"

**ANSWER**
"They can't, structurally — each dimension has exactly one probe and one persisted
result per evaluation; there's no second computation path to disagree with."

---

### STEP 16/17 — Human review and O/S/D entry

*(Covered in full detail in Part 5 — this is the summary version for the happy path.)*

**WHAT I DO**
For an `AI_ASSISTED` evaluation once it reaches `AWAITING_REVIEW`, I click **Review
O/S/D**, then enter Occurrence, Severity, and Detection values for each aspect and
submit.

**WHAT I SHOULD SEE**
A table with one row per FRIES dimension, three independent number inputs (O, S, D) per
row, each optional and separately editable, plus a "Machine-measured evidence" column
that's read-only.

**WHAT I SAY**
"O, S, and D are always entered by a human here — the deterministic engine never
proposes them. I can fill in some, all, or none of the three for each aspect."

**WHAT IT MEANS**
Submitting posts to `POST /v1/evaluations/{id}/human-review`, which stores the values
exactly as entered — no rounding, no inference, no defaulting a blank field to zero.

**WHY THIS DESIGN**
FRIES needs O/S/D, and TrustLens has no validated way to compute those from probe
metrics automatically — so rather than invent one, I require a person to supply them.

**IMPORTANT POINT TO EMPHASIZE**
"A blank field stays blank. It is never silently treated as a zero."

**LIKELY PROFESSOR QUESTION**
"Why not let the system estimate O/S/D from the metrics automatically?"

**ANSWER**
"Because metric-to-O/S/D mapping is unresolved research — I say that directly in the
scoring code's own docstring. Automating it would mean fabricating a judgment I can't
justify."

---

### STEP 18 — FRIES finalization

**WHAT I DO**
I click **Submit review + finalize** (assisted mode) or the evaluation autonomously
reaches `FINALIZED` (autonomous mode, no human step).

**WHAT I SHOULD SEE**
If all five aspects have complete O, S, and D: an **Overall FRIES assessment** card with
a number between 0 and 10, per-dimension score bars, and a disclaimer describing exactly
how it was computed. If not: the withheld state (Part 4).

**WHAT I SAY**
"FRIES only gets computed once every required aspect has a complete O, S, D triple —
otherwise the system explicitly withholds it rather than filling gaps."

**WHAT IT MEANS**
`score_from_finalized_osd(...)` computes `Pi = cbrt(O × S × D)` per risk (with a veto to
zero if any of O, S, D is zero), averages per aspect, then takes a weighted average
across the five dimensions (equal 0.2 weights by default) for the final score.

**WHY THIS DESIGN**
The cube-root-of-product formula and the zero-veto rule come from the FRIES paper — a
single catastrophic component (any 0) should be able to drag the whole risk to zero, not
get averaged away.

**IMPORTANT POINT TO EMPHASIZE**
"This is pure arithmetic on human-supplied integers — there is no model, no LLM, and no
heuristic anywhere inside this calculation."

**LIKELY PROFESSOR QUESTION**
"What do O, S, D actually stand for?"

**ANSWER**
"Occurrence, Severity, Detection — each 0 to 10, higher is better/safer in this
convention. They're finalized per FRIES-aspect risk and combined with a cube-root
formula, `Pi = cbrt(O·S·D)`."

---

### STEP 19 — Evaluation timeline

**WHAT I DO**
Scroll to **Evaluation timeline** on the detail page.

**WHAT I SHOULD SEE**
An ordered list: `Evaluation created`, `Evaluation started`, `Probes completed`,
`O/S/D representation proposed`, and then either `Awaiting human review` →
`Human review submitted` → `Evaluation finalized`, or straight to `Evaluation
finalized` for autonomous mode. Each with a timestamp.

**WHAT I SAY**
"This is an append-only audit log of exactly what happened and in what order — it's not
a second source of truth, just a record of when the real state changes above already
happened."

**WHAT IT MEANS**
Events are ordered by database id, not by timestamp — because a whole pipeline run
happens inside one transaction, and Postgres can give several events in that
transaction the identical wall-clock timestamp. Id ordering never has that ambiguity.

**WHY THIS DESIGN**
I wanted a place to answer "when did this actually happen" without ever letting that
answer become the thing that decides current status — status lives in one column,
this table only narrates it.

**IMPORTANT POINT TO EMPHASIZE**
"Nothing reads this table to decide what state the evaluation is in — it's audit
evidence, not authoritative state."

**LIKELY PROFESSOR QUESTION**
"What happens if the same event gets recorded twice?"

**ANSWER**
"It can't, by construction — an event is only ever written immediately after the
lifecycle's own atomic status transition succeeds. If that transition is a no-op
because the evaluation already moved on, no event gets written either."

---

### STEP 20/21 — Evidence traceability and the final report

**WHAT I DO**
Click **View report**.

**WHAT I SHOULD SEE**
The Report page: Executive Assessment, Evaluation Contract, Model Identity, Dataset
Identity, Local Execution Environment, per-dimension Dimension Evidence cards, an
Evidence Traceability section with the same `EvidenceChainTag` labels, Human O/S/D
Assessment, FRIES Assessment, Reproducibility Information, Limitations, Documentation
Sources, and Artifacts (JSON/PDF links and hashes).

**WHAT I SAY**
"This report is generated once and stored — I'm not looking at a live recomputation,
I'm looking at the exact JSON document that got persisted, with its own hash."

**WHAT IT MEANS**
`GET /v1/reports/{id}` auto-generates version 1 on first read if none exists;
`POST /v1/reports/{id}/generate` force-creates the next version. Every version writes
new, versioned MinIO keys — nothing is ever overwritten.

**WHY THIS DESIGN**
Reports are the artifact someone might cite later — I wanted them to be genuinely
immutable once created, with an explicit version number, not something that silently
changes if I regenerate it.

**IMPORTANT POINT TO EMPHASIZE**
"Every report version is append-only — regenerating never overwrites a previous
version, and the database enforces that with a uniqueness constraint on (evaluation,
version), not just application code."

**LIKELY PROFESSOR QUESTION**
"What if two people regenerate the report at the same time?"

**ANSWER**
"I specifically hardened this — report generation takes a row lock on the evaluation for
the duration of version assignment, so two concurrent requests can't compute the same
next version number, and there's a database unique constraint as the final backstop
even if that locking were ever bypassed."

---

### STEP 22 — PDF report

**WHAT I DO**
On the report page, I note the **PDF** artifact link (if WeasyPrint is available in this
environment) or point out `pdf_uri: not generated` if it isn't.

**WHAT I SHOULD SEE**
Either an `s3://` PDF URI with a matching SHA-256 hash, or an honest "not generated (PDF
disabled on host)" message — never a broken link, never a fabricated one.

**WHAT I SAY**
"The PDF is rendered from the exact same JSON document as the web report — there's no
second calculation path for the PDF."

**WHAT IT MEANS**
`render_pdf(render_html(report_json))` — the HTML template and the PDF both consume the
identical `report_json` object built once by `build_report_json(...)`.

**WHY THIS DESIGN**
If the PDF and the web report could disagree, I'd have two different "final answers"
for the same evaluation. Deriving both from one document by construction rules that
out.

**IMPORTANT POINT TO EMPHASIZE**
"If PDF rendering isn't available on a given host, the report still returns
successfully as JSON-only — a missing PDF library never blocks the actual evidence."

**LIKELY PROFESSOR QUESTION**
"Why would PDF generation ever be unavailable?"

**ANSWER**
"WeasyPrint needs OS-level libraries — Pango, HarfBuzz — that aren't present on every
host. The Docker image ships them; a bare CI runner or a laptop without them just
degrades to JSON+HTML, by design, not by accident."

---

### STEP 23 — What the final result actually means

**WHAT I SAY**
"What you've just seen is: five independent, fixed measurements; each one gated by its
own validity rules before it's allowed to name a risk; a human converting that evidence
into Occurrence/Severity/Detection; and only then, a single arithmetic formula turning
those into one number. At every step before the human, the system either measured
something or said it couldn't — it never guessed."

---

## PART 4 — HONESTY / INSUFFICIENT-EVIDENCE DEMO

This is the demonstration I treat as the most important part of the whole defense.

### The strongest real positive result I have

I actually ran this: `textattack/bert-base-uncased-SST-2` against the approved
`sst2_robustness` contract, on a real GPU (RTX 4060 Laptop GPU), inside the default
Docker Compose configuration.

**Observed metric:** clean accuracy 0.975, robust accuracy (after character-swap
perturbation) 0.695 — accuracy drop 0.28.

**Confidence interval:** bootstrap (B = 1,000, percentile method) gives a lower bound of
0.22 on the accuracy drop; clean/robust accuracy each also have their own Wilson-score
interval.

**Validity gates:** perturbation coverage 100% (every evaluated row was perturbed), 200
evaluated rows (clears the minimum of 100), label compatibility above the 95% floor.

**Risk:** because the point estimate (0.28) *and* the CI lower bound (0.22) both clear
the 0.05 threshold, the probe names risk `R-ROB-PERT`.

**Human assessment:** in my demo I entered O/S/D for this exact evaluation — for example
Robustness O=7, S=8, D=7 — as a human judgment about how often this failure mode occurs
in practice, how severe it is, and how detectable it is; not a re-measurement of the
0.28 number.

**Final FRIES:** with all five aspects complete, this evaluation genuinely scored —
5.3845 in my run, with per-dimension scores (Robustness came out at 7.3186 in that same
run).

**Final report status:** `FINALIZED`, `fries_status: scored`, `scoring_withheld: false`.

"Notice the layers here: 0.28 is the *observed metric*. 0.22 is the *confidence
interval's* honest floor. R-ROB-PERT is the *named risk* — a rule firing because both
of those cleared a threshold. 7/8/7 is *my own human judgment* entered separately. And
5.38 is the *final FRIES number*, produced by one fixed formula on that human input.
Five completely distinct things, never blurred into one."

### Why did the system not simply give a score? (the honesty path)

I take the exact same model and contract, but this time I stop **before** any human
review — right after the evaluation reaches `FINALIZED` in autonomous mode with an
incomplete/absent O/S/D (which is the default: the deterministic engine abstains on
every aspect by design).

**WHAT I DO** — open that evaluation's detail page.

**WHAT I SHOULD SEE** — the **Overall FRIES assessment** card shows three rows:
"Measured evidence: Available", "O/S/D synthesis: Unavailable", "Final FRIES:
Withheld" — with the text "This is not a low trust score — it means no synthesized
score exists yet." The report's `score.fries_score` is `null`, never `0`.

**WHAT I SAY**
"The probes ran, the evidence exists — you can see the 0.28 accuracy drop right there in
the Robustness card. What's missing is a human decision about Occurrence, Severity, and
Detection. So FRIES is withheld. Not zero. Withheld."

**WHY DID THE SYSTEM NOT SIMPLY GIVE A SCORE?**
"Because a score without a human judgment behind O/S/D would just be the system
guessing. I'd rather show nothing than show a number I can't justify."

**WHY IS INSUFFICIENT EVIDENCE DIFFERENT FROM FAILURE?**
"Insufficient evidence means the measurement itself is fine, but a required input for
the *next* step is missing — like Explainability saying 'no model card text — cannot
evaluate' when the card genuinely has nothing in it. Failure means something broke.
Those get different status codes and different UI states on purpose."

**WHY IS ABSTENTION IMPORTANT?**
"Because the alternative — quietly defaulting a missing value to zero, or to some
average — would let a gap in the evidence disappear into the final number, and nobody
looking at a 5.4 out of 10 would know that one of the five dimensions never actually
ran, or that a human never actually weighed in."

---

## PART 5 — HUMAN REVIEW + O/S/D + FRIES

### Case A — no human review

An `AI_ASSISTED` evaluation sitting at `AWAITING_REVIEW`. `mode_disclosure.human_reviewed
= false`, disclaimer: *"Awaiting human review before finalize. This is a human-review
workflow, not LLM interpretation of evidence."*

### Case B — human review exists, O/S/D incomplete

A reviewer submits, say, only Fairness's O and S (leaving D blank, and every other
aspect untouched). On finalize: status is `FINALIZED`, `final_score` is still `null`
(withheld), but — this is the part I fixed and specifically verified — `mode_disclosure`
now correctly reports `human_reviewed: true`, `fries_status: "withheld"`, and the
disclaimer *"Human review recorded, but at least one required aspect is missing a
complete human O/S/D triple... FRIES is withheld until every required aspect has all
three."*

### Case C — human review exists, O/S/D complete

A reviewer supplies O, S, and D for all five aspects. `final_score` is populated,
`human_reviewed: true`, `fries_status: "scored"`, disclaimer *"Human review recorded and
complete for every required aspect... FRIES has been scored from this human-supplied
O/S/D."*

**Exact words for "why can a human review exist while FRIES is still withheld?"**

"Those are two different questions. `human_reviewed` answers 'did a person actually look
at this and submit something' — that's read straight from the human_reviews record.
`scoring_withheld` answers 'is every required O/S/D triple complete' — that's a separate
completeness check. A reviewer can genuinely submit a review that only fills in two of
five aspects; that's a real review, so `human_reviewed` is true, but FRIES still can't be
computed from an incomplete set, so it stays withheld. They're independent facts, and I
made sure the system reports them as two separate facts instead of collapsing them into
one."

*(Small honest aside if asked directly: earlier in development, `human_reviewed` was
incorrectly derived only from the scored-results table, so it read as `false` even after
a genuine review — I found that live while validating the system and fixed it to read
from the actual human-review record instead. I mention this only if it comes up, as
evidence I test my own claims rather than to dwell on it.)*

---

## PART 6 — NON-HAPPY PATH DEMOS

Each of these is real and either directly testable in the live app or safely
demonstrable by describing what would happen — I never suggest actually corrupting
data to show one.

### 1. Invalid/unsupported evaluation contract

**WHAT I DO** — try to request a Robustness contract for a model+revision that isn't in
the approved list (e.g. by editing the request directly, since the UI already disables
this).
**WHAT HAPPENS** — a structured 422/404 validation error; no evaluation row is created.
**WHAT I SAY** — "The contract builder refuses before anything is persisted."
**WHY IT HAPPENS** — `build_evaluation_contract` checks the model+revision against the
compat registry and raises before any DB write.
**HOW TRUSTLENS PROTECTS STATE** — no partial evaluation ever exists for a rejected
contract.
**WHAT THE PROFESSOR SHOULD LEARN** — validation happens before persistence, not after.

### 2. Invalid user dataset

**WHAT I DO** — upload a CSV missing the selected target/group column, or exceeding the
50,000-row / 10 MB limit.
**WHAT HAPPENS** — a clear validation error naming the missing column or the limit
exceeded; the file is never used to create an evaluation.
**WHY IT HAPPENS** — `DatasetService.upload` sniffs columns and row count before
accepting the file.
**HOW TRUSTLENS PROTECTS STATE** — the evaluation contract can't even be built without a
dataset whose columns match what was requested.
**WHAT THE PROFESSOR SHOULD LEARN** — the same "gate before proceeding" pattern used
throughout the probes is also used at upload time.

### 3. Missing/insufficient documentation

Already covered in Part 4/Step 13 — Explainability/Safety returning
`INSUFFICIENT_EVIDENCE` with an honest reason ("no model card text").

### 4. Failed inference / pipeline logic error

**WHAT I DO** — describe what happens if the model reference on the worker's payload
doesn't match the model actually stored (a stale/drifted reference).
**WHAT HAPPENS** — the pipeline detects the mismatch, transitions the evaluation
straight to `FAILED` with `reason_code: model_ref_mismatch`, and returns without
raising — Celery never retries it.
**WHY IT HAPPENS** — the pipeline explicitly distinguishes "a real logic error" (never
retryable) from "a transient connection problem" (retryable).
**HOW TRUSTLENS PROTECTS STATE** — the FAILED transition is the same conditional CAS
used everywhere; the event recorded (`evaluation_failed` with that reason code) only
gets written if the transition actually applied.
**WHAT THE PROFESSOR SHOULD LEARN** — logic errors and transient errors are handled by
two completely different code paths, on purpose.

### 5. Worker retry, then retry exhaustion

**WHAT I DO** — describe (not force, in a live demo) what happens if the worker hits a
transient `ConnectionError` or `TimeoutError` — for example, Redis or Postgres blips
mid-run.
**WHAT HAPPENS** — Celery automatically retries the task up to 3 times with exponential
backoff. If all three retries also fail, the task ends in permanent failure, and a
callback (`on_failure`) transitions the evaluation from `RUNNING` straight to `FAILED`,
through the exact same atomic CAS, recording one event with
`reason_code: worker_retries_exhausted`.
**WHY IT HAPPENS** — `autoretry_for=(ConnectionError, TimeoutError)`, `max_retries=3` on
the Celery task; the `on_failure` callback is Celery's own hook, guaranteed to fire
exactly once, only after retries are truly exhausted.
**HOW TRUSTLENS PROTECTS STATE** — the CAS only applies if the row is still `RUNNING` —
if the pipeline had already reached a terminal state before the exception surfaced, this
is a safe no-op, never overwriting FINALIZED or an already-recorded FAILED.
**WHAT THE PROFESSOR SHOULD LEARN** — "this used to be a real gap I found in my own
audit — an evaluation could stay `RUNNING` forever if retries exhausted. I traced
Celery's exact retry/failure lifecycle and closed it with the smallest possible fix:
one more caller of the same CAS function, not a new mechanism."

### 6. Confirmed enqueue failure and reconciliation

**WHAT I DO** — describe what happens if the initial Celery enqueue itself fails (Redis
unreachable at creation time).
**WHAT HAPPENS** — the evaluation is created as `PENDING`, and the very same
`evaluation_created` event honestly records `enqueued: false`. An admin can call
`POST /v1/evaluations/{id}/reconcile-enqueue`, which only proceeds if the evaluation is
still `PENDING` **and** its own event history confirms the last enqueue attempt actually
failed — never based on how long it's been sitting there.
**WHY IT HAPPENS** — I deliberately avoided an age-based timeout, because a legitimately
slow (but successfully enqueued) evaluation must never be mistaken for a stuck one.
**HOW TRUSTLENS PROTECTS STATE** — re-enqueuing never changes status itself; only the
worker's own CAS does that when it actually picks up the task, so even a duplicate
reconciliation attempt can't create two running copies.
**WHAT THE PROFESSOR SHOULD LEARN** — the fix uses the *confirmed* signal already in the
event log, not a guess based on elapsed time.

### 7. Stale CAS transition / duplicate action protection

**WHAT I DO** — describe what happens if a redelivered Celery message tries to run the
same evaluation a second time after it already finished.
**WHAT HAPPENS** — the second delivery's attempt to flip `PENDING → RUNNING` fails
(the row is no longer `PENDING`), logs a "skip, not pending" message, and returns —
zero side effects, no duplicate probe rows, no duplicate events.
**WHY IT HAPPENS** — every lifecycle transition anywhere in the codebase goes through
one function, `transition_status`, which is an atomic, conditional SQL `UPDATE ... WHERE
status IN (...)` — never a plain unconditional write.
**HOW TRUSTLENS PROTECTS STATE** — I specifically removed a legacy method that *could*
write status unconditionally, once I confirmed nothing legitimate depended on it —
there is now exactly one status-mutation code path in the whole system.
**WHAT THE PROFESSOR SHOULD LEARN** — "compare-and-swap" isn't just a database
buzzword here — it's the literal mechanism that makes duplicate delivery harmless.

### 8. Report version race

**WHAT I DO** — describe (or, if you want to actually show it, this is real and
tested) two concurrent requests to regenerate the same evaluation's report at the same
moment.
**WHAT HAPPENS** — I tested this with two genuinely concurrent database transactions:
both succeed, and they land on versions 1 and 2 — never both on the same version
number. This is enforced two ways: a row lock on the evaluation for the duration of
version assignment, and a database-level unique constraint on
`(evaluation_id, version)` as the backstop.
**WHY IT HAPPENS / HOW IT'S PROTECTED** — even if the application-level lock were ever
bypassed by a future change, the database itself would refuse the duplicate insert.
**WHAT THE PROFESSOR SHOULD LEARN** — "I don't just trust my own application code to
get concurrency right — I also put the real invariant in the database schema."

### 9. Unsupported robustness pairing

Same as non-happy path #1, specific to robustness — the "no approved contract for this
exact model + revision" disabled button on the Category step, backed by the same
compat-registry check server-side.

### 10. Ownership restrictions

**WHAT I DO** — describe logging in as a different user and trying to read another
user's uploaded dataset directly by id.
**WHAT HAPPENS** — a `403 Forbidden`.
**WHY IT HAPPENS** — dataset access is ownership-gated at the service layer
(`get_owned`), admin excepted.
**WHAT THE PROFESSOR SHOULD LEARN** — ownership is enforced server-side on every read,
not just hidden in the UI.

---

## PART 7 — WHAT HAPPENS BEHIND EACH BUTTON

### "Run evaluation"

**A. SIMPLE EXPLANATION** — "The API saves the evaluation as PENDING, then hands the
actual work to a background worker. The worker loads the model, runs each of the five
checks, and updates the evaluation as it goes."

**B. TECHNICAL EXPLANATION** — `POST /v1/evaluations` → `EvaluationService.
create_evaluation` resolves and freezes the `EvaluationContractV1`, inserts the
`Evaluation` row as `PENDING`, calls `enqueue_evaluate_model` (Celery `send_task` over
Redis), and records an `evaluation_created` event with the real enqueue outcome. The
Celery task `trustlens.evaluate_model` (in the `worker` service) calls
`run_evaluation_pipeline`, which does the atomic `PENDING → RUNNING` CAS, runs
`run_all_probes` (Fairness → Robustness → Integrity → Explainability → Safety, fixed
order), persists each `ProbeResult` + MinIO evidence artifact, runs the O/S/D
mapper, and drives the evaluation through `PROBES_COMPLETED → AGENT_COMPLETED →
AWAITING_REVIEW | FINALIZED`, recording one `EvaluationEvent` per real transition.

### "Submit review + finalize"

**A. SIMPLE EXPLANATION** — "This saves exactly what I typed as the human O/S/D values,
then checks if every dimension now has a complete set. If so, it computes FRIES; if
not, FRIES stays withheld."

**B. TECHNICAL EXPLANATION** — `POST /v1/evaluations/{id}/human-review` persists a
`HumanReview` row (append-only — "latest wins" for finalize) and an
`EVENT_HUMAN_REVIEW_SUBMITTED` event. `POST /v1/evaluations/{id}/finalize` then either
computes `score_from_finalized_osd` and upserts `FinalScore` (if every aspect is
complete), or leaves no `FinalScore` row and marks `scoring_withheld: true` — either
way, the evaluation reaches `FINALIZED`.

### "Generate report" / "View report"

**A. SIMPLE EXPLANATION** — "This builds one JSON document from everything already
saved, stores it, and shows it to me. Asking for it again just gives me back the same
stored document, unless I explicitly ask to regenerate."

**B. TECHNICAL EXPLANATION** — `GET /v1/reports/{id}` calls `ReportService.get_report`,
which auto-generates version 1 via `build_report_json` if none exists, else reads back
the stored artifact from MinIO. `POST /v1/reports/{id}/generate` always creates
`latest_version + 1`, under a row lock on the evaluation to prevent a concurrent
duplicate version, writes new MinIO keys for JSON (and PDF, if WeasyPrint is available),
and records a `report_generated` event.

---

## PART 8 — TRUSTLENS ARCHITECTURE EXPLANATION

```
Browser
  ↓
React / Vite / TypeScript frontend  (client-side routing, polling for active evaluations)
  ↓  (REST, JSON, Bearer JWT)
FastAPI backend  (validation, auth, contract freezing, DB writes, enqueue)
  ↓                                  ↓
PostgreSQL                          Redis (Celery broker)
(evaluations, events,                 ↓
 probe results, reviews,           Celery worker
 final scores, reports)            (model loading via Transformers,
  ↓                                 local inference, five probes,
MinIO                               O/S/D mapping)
(evidence artifacts,                  ↓
 report JSON/PDF)                  writes back to PostgreSQL + MinIO
```

I present the architecture pointing at each layer as I say this, and I keep it to one
breath per layer.

---

## PART 9 — TECH STACK: WHY EACH TECHNOLOGY

**React** — WHAT IT IS: a component-based UI library. WHY I USED IT: the frontend is
mostly "render this evaluation's current state," which maps cleanly onto components
re-rendering from fetched data. ADVANTAGES: huge ecosystem, easy to reason about state
per page. DISADVANTAGES: I hand-roll polling instead of using a data-fetching library,
so there's some repeated `useEffect` boilerplate. WHY NOT SIMPLER: plain server-rendered
HTML would fight the polling/live-status requirement on the evaluation detail page.

**Vite** — WHAT IT IS: the frontend build tool and dev server. WHY: fast dev-server
startup and a simple, standard production build (`tsc -b && vite build`).
ADVANTAGES: near-instant hot reload while developing. DISADVANTAGES: another tool in
the chain, though a very thin one. WHY NOT SIMPLER: Create React App is effectively
unmaintained; Vite is the current standard.

**TypeScript** — WHAT IT IS: typed JavaScript. WHY: the API response shapes are
hand-mirrored as TypeScript types (`api/types.ts`), so a backend field rename shows up
as a compile error in the frontend instead of a silent `undefined` in production.
ADVANTAGES: caught real mistakes during development. DISADVANTAGES: the types are
hand-written, not generated from the OpenAPI schema, so they can drift if I'm not
careful. WHY NOT SIMPLER: plain JS would have hidden exactly the kind of shape mismatch
I actually caught with this.

**FastAPI** — WHAT IT IS: a Python web framework with request/response validation
built on Pydantic. WHY: I get typed request/response models "for free," and it
integrates cleanly with the same Python ML stack (Transformers, PyTorch) the worker
uses. ADVANTAGES: automatic OpenAPI docs, fast to write, good performance. TRADE-OFF:
I still had to build the whole worker/queue layer separately for anything
long-running — FastAPI alone won't run a five-minute model evaluation inline. WHY NOT
SIMPLER: Flask would have needed the same background-worker split anyway, without the
built-in validation.

**Python** — the shared language across API, worker, and probes — chosen because the
entire ML ecosystem I depend on (Transformers, PyTorch, scikit-learn, Fairlearn) is
Python-native.

**PostgreSQL** — WHAT IT IS: a relational database. WHY: evaluation lifecycle needs
real transactions and atomic conditional updates — the CAS pattern I rely on
everywhere is a single SQL `UPDATE ... WHERE status IN (...)`, which is exactly what a
relational database gives you for free. ADVANTAGES: real foreign keys, unique
constraints (I lean on one for report versioning), row-level locking. TRADE-OFF: schema
migrations (Alembic) are one more thing to maintain versus a schemaless store.
WHY NOT JSON FILES / SQLITE: JSON files can't give me an atomic conditional write across
concurrent processes; SQLite doesn't give the same concurrent-connection story Postgres
does, and I specifically needed two real, independent transactions to prove the report
version race couldn't happen.

**SQLAlchemy** — WHAT IT IS: the Python ORM/SQL toolkit. WHY: repository classes wrap
each table's operations, so the "only mutate status through `transition_status`" rule
is enforced in one place rather than scattered raw SQL. TRADE-OFF: an ORM adds an
abstraction layer between me and the actual SQL, which occasionally makes performance
tuning less direct.

**Alembic** — WHAT IT IS: SQLAlchemy's migration tool. WHY: every schema change (adding
`evaluation_events`, adding the report unique constraint) is a versioned, reversible
migration I can test with upgrade/downgrade/re-upgrade against a real database.

**Celery** — WHAT IT IS: a distributed task queue for Python. WHY: model inference is
slow and shouldn't block an HTTP request. ADVANTAGES: built-in retry/backoff for
transient errors, and a clean `on_failure` hook I used for the retry-exhaustion fix.
TRADE-OFF: it's another moving part with its own failure modes (see Part 12).
BROKER: Redis — chosen because it's simple to run in Compose and is also reused for
Celery's result backend; there's no separate message broker technology in this stack.

**MinIO** — WHAT IT IS: an S3-compatible object store, self-hosted. WHY: evidence
artifacts and report JSON/PDF are blobs, not relational rows — I wanted them versioned
and content-addressable, separate from Postgres. ADVANTAGES: same API shape as AWS S3,
so the exact same `boto3` client code would work against real S3 if I ever deployed
there. TRADE-OFF: it's one more container to run locally.

**Docker / Docker Compose** — WHAT IT IS: containerization + multi-service
orchestration. WHY: one file (`docker-compose.yml`) brings up all six services with
correct startup dependencies; there's also a GPU-passthrough default and a CPU-only
override file for machines without an NVIDIA GPU. TRADE-OFF: anyone running this needs
Docker installed; I don't get a zero-dependency single binary.

**Hugging Face / Transformers, PyTorch** — WHAT IT IS: the model hub client and the
inference library. WHY: this is the entire point — TrustLens evaluates real Hugging
Face models by actually loading and running them, not by calling out to a hosted
inference API.

**pytest** — the backend test runner: 536 tests passing against a real, isolated
Postgres database as of my last full run.

**Vitest + Testing Library, plus Node's built-in test runner** — the frontend test
setup: Vitest with `@testing-library/react`/`jest-dom` for component/DOM tests (25
tests), and Node's native `node:test` for pure-logic unit tests (5 tests) — 30 total.

---

## PART 10 — ARCHITECTURE DECISIONS + TRADE-OFFS

**Local-first.** ADVANTAGE: full control of what model runs, on what hardware, with
what data — nothing leaves the machine. DISADVANTAGE: no built-in horizontal scaling
story; it's one worker container by default. WHY ACCEPTABLE HERE: this is a research/
academic evaluation tool, not a hosted product — control and reproducibility matter
more than elastic scale.

**Asynchronous evaluation (Celery, not inline).** ADVANTAGE: the API stays responsive
regardless of how long inference takes. DISADVANTAGE: a whole extra failure surface
(broker down, worker crashed, message redelivered) that I had to explicitly design
around — which is exactly what items 4 and the retry-exhaustion fix were about.
ACCEPTABLE: the alternative (blocking HTTP requests for model inference) simply doesn't
work past a few seconds.

**Deterministic probes, not LLM judgment.** ADVANTAGE: every number is reproducible and
auditable — same inputs, same code, same output. DISADVANTAGE: it's narrower — an LLM
judge could in principle answer more open-ended questions. ACCEPTABLE: I'd rather
answer five specific questions honestly than one open-ended question I can't validate.

**Evidence-first architecture (measure → gate → risk, in that order).** ADVANTAGE: a
risk can never be named without evidence and a passed gate behind it. DISADVANTAGE:
more code, more states to test (EVALUATED, INSUFFICIENT_EVIDENCE, NOT_APPLICABLE,
FAILED, PROXY per dimension). ACCEPTABLE: the whole value proposition of TrustLens is
that a reader can trust the "why," not just the number.

**EvaluationContractV1 (frozen contract).** Already covered in Step 5 — the short
version: reproducibility requires a fixed point, and "current Hub state" isn't one.

**PostgreSQL for lifecycle/state, MinIO for artifacts.** ADVANTAGE: relational
guarantees (transactions, constraints, locks) where I actually need them (status,
uniqueness); cheap, versioned blob storage where I don't need to query the contents.
DISADVANTAGE: two storage systems to keep consistent, which is why the frozen
`json_hash`/`pdf_hash` fields exist — to make cross-checking possible.

**Celery for background execution; Docker Compose to run everything.** Both already
covered above.

**Frozen model + dataset revisions.** Covered in Step 5.

**Explicit evaluation modes (`AI_AUTONOMOUS` vs `AI_ASSISTED`).** ADVANTAGE: the system
is upfront about whether a human ever reviewed this result — it's a field on every
evaluation, not an inference. DISADVANTAGE: it's one more branch in the pipeline logic
to test (and I do test both). ACCEPTABLE: hiding this distinction would be exactly the
kind of overclaiming TrustLens exists to avoid.

**CAS state transitions.** Covered extensively above — this is the single mechanism
that makes concurrent/duplicate execution safe.

**Append-only EvaluationEvent.** ADVANTAGE: a genuine audit trail that can't be edited
after the fact. DISADVANTAGE: no "undo" — if I ever need to correct a mistaken event, I
add a new one, I don't edit the old one. ACCEPTABLE: audit trails that can be silently
edited aren't audit trails.

**Canonical report JSON (PDF is a projection of it).** Covered in Step 22.

**Deterministic O/S/D handling; human review required.** Covered in Step 16–18 and Part
5.

**Abstention / insufficient evidence.** The whole of Part 4.

---

## PART 11 — WHY LOCAL-FIRST?

**20-second answer:** "Because the model and the data stay on the machine that's
running the evaluation. I don't send anything to a third-party inference API, I control
exactly what hardware ran it, and I can reproduce the same run later because nothing
about the environment is hidden behind someone else's service."

**60-second answer:** "TrustLens is meant to answer 'what does the evidence actually
show for this model,' and I wanted that answer to be independently checkable. If
inference happened on a cloud API I don't control, I couldn't honestly claim to know
what device it ran on, what version of the library computed it, or whether the model
weights I evaluated are the exact ones pinned in the contract. Running locally — with
Docker Compose bringing up Postgres, Redis, MinIO, the API, and the worker on one
machine — means every one of those facts is something I can actually verify and record,
which is exactly what the `execution_metadata` field does: real device, real GPU name,
never fabricated."

**Deep technical answer:** "The trade-off is real, and I'll name it directly: this
doesn't scale horizontally out of the box — it's one worker container by default, so a
queue of evaluations runs sequentially unless someone adds more worker replicas, and
there's no managed infrastructure, load balancing, or multi-tenant story here. For an
academic tool evaluating one model at a time, that's an acceptable trade for the
reproducibility and control I get in return. If I were scaling this to production, I'd
add worker replicas behind the same Redis broker — Celery already supports that — and
I'd need a real GPU scheduling story instead of the current one-worker-one-GPU
assumption, but the core architecture (frozen contract, CAS lifecycle, evidence-first
probes) doesn't need to change to get there."

---

## PART 12 — WHY CELERY?

**"Why can't FastAPI just run the evaluation?"**

"Because model inference can take anywhere from seconds to a couple of minutes, and an
HTTP request holding a connection open that long is a bad idea — browsers, proxies, and
load balancers all have their own timeouts, and the whole API process would be blocked
serving that one request instead of handling anything else. Splitting 'accept the
request' from 'do the work' means the API responds instantly with `PENDING`, and the
actual work happens in a separate worker process."

**Blocking inference / request timeouts:** exactly the concern above — solved by
enqueue-then-poll instead of a blocking call.

**Background execution:** the worker (`worker/app/tasks/evaluate.py`) is a completely
separate Celery consumer process from the API.

**Retries:** `autoretry_for=(ConnectionError, TimeoutError)`, `max_retries=3`,
exponential backoff — transient network blips get retried automatically; real logic
errors (bad contract, mismatched model) are explicitly never retried.

**Worker isolation:** if the worker process crashes mid-evaluation, the API process is
completely unaffected — it just keeps serving other requests.

**Scaling:** Celery supports multiple worker processes/replicas consuming from the same
queue; I run one by default, but the architecture doesn't assume exactly one.

**Current retry-exhaustion behavior, accurately:** "If all three retries also fail, the
task ends in permanent failure, and I added an `on_failure` callback that transitions
the evaluation from RUNNING to FAILED through the same CAS mechanism, recording an
event with reason code `worker_retries_exhausted`. Before I added that, this was a real
gap — an evaluation could be left RUNNING forever. I do **not** have a
heartbeat/lease/timeout system watching long-running tasks in general — that's the
next thing I'd build, not something already in place."

---

## PART 13 — WHY POSTGRESQL?

"Every piece of state that actually matters here — the evaluation's status, its
lifecycle events, the human review, the final score, the report versions, who owns
what — needs to be written and read with real transactional guarantees. The one
mechanism the entire lifecycle depends on, the atomic PENDING-to-RUNNING style
transition, is a single conditional SQL `UPDATE` — that's not something you get for
free from a JSON file on disk, where two processes could both read the same file, both
decide to proceed, and both write, corrupting each other. Postgres also gave me a real
unique constraint to enforce 'no two report versions with the same number' at the
schema level, not just in application code — which matters because I specifically
tested that a bypassed application-level lock still can't produce a duplicate, because
the database itself refuses it."

---

## PART 14 — WHY MINIO?

"Evidence artifacts and report JSON/PDF are blobs — I don't need to run SQL queries
against their contents, I just need to store them, retrieve them by key, and know
they haven't changed (I hash them at write time). Object storage is the right shape for
that, and MinIO gives me an S3-compatible API I can run entirely locally in Docker,
with the exact same client code (`boto3`) that would talk to real AWS S3. The
trade-off is it's one more container and one more thing that can be unavailable — if
MinIO is down, report/evidence reads and writes fail with a clear `503
STORAGE_UNAVAILABLE`, not a silent fallback."

---

## PART 15 — WHY DETERMINISTIC EVALUATION?

"I could have built this by asking an LLM, 'is this model fair, is it robust, is it
safe,' and having it write a paragraph back. I didn't, because that answer wouldn't be
reproducible — ask again tomorrow, maybe get a different answer, with no way to know
why. Instead, every one of the five dimensions runs a fixed piece of code: a specific
metric, computed the same way every time, checked against an explicit numeric
threshold, with a confidence interval where that's implemented, and it only names a
risk if the gate actually passes. Nothing is hidden inside a model's reasoning — the
whole chain, from raw evidence to gate to named risk, is code I can show you and you
can re-run.

That said, I'm not against AI-assisted interpretation in general — I just don't claim it
does something today that it doesn't. Right now, the O/S/D mapper is explicitly a
deterministic engine that abstains on every aspect, by design, because I don't have a
validated way to map metrics onto Occurrence/Severity/Detection automatically. An
AI-assisted mode that *proposes* O/S/D for a human to review — clearly labeled as a
proposal, never as ground truth — is future work I've thought about, but it isn't
implemented, and I won't claim it is."

---

## PART 16 — EXPLAIN THE FIVE DIMENSIONS

**FAIRNESS** — Measures today: disparity in model performance across groups in a
selected dataset (demographic parity difference / equalized odds difference / worst-
group accuracy gap, depending on task), for an approved model-faithful pairing, an
admin-gated tabular proxy path, or a user's own local CSV. Does NOT claim: which
attribute is "sensitive" (that's chosen by a human), or fairness beyond the specific
metric computed. Gate: minimum group size (30 by default). Evidence: per-group
prediction statistics, persisted with the exact dataset content hash. Insufficient
evidence: a group too small to trust. Risks named: only when the gate passes and the
disparity clears a threshold. Limitation: it's one metric family, not a general
fairness certification.

**ROBUSTNESS** — Measures: accuracy drop under a specific, seeded character-swap
perturbation, against an approved dataset/model pairing. Does NOT claim: robustness to
any other kind of adversarial input — semantic attacks, different perturbation types,
adaptive attackers. Gates: perturbation coverage 100%, minimum evaluated rows (100 of
200 requested), label compatibility ≥95%. Evidence: clean/robust accuracy, bootstrap
confidence interval. Insufficient evidence: gate failure (e.g. too few rows evaluated).
Risk named: `R-ROB-PERT`, only if drop and CI lower bound both exceed 0.05. Limitation:
this is a narrow, specific attack — the code says so in its own docstring.

**INTEGRITY** — Measures: disclosure/provenance of the model's identity — is the
revision pinned, is there a manifest, is the license disclosed, do local artifact bytes
match a trusted reference hash if one was supplied. Does NOT claim: tampering,
malicious intent, or Hub compromise. Evidence: metadata comparisons, no inference run.
Named risks: `I-INT-REV-UNPINNED`, `I-INT-MANIFEST-MISSING`, `I-INT-LICENSE-
UNDISCLOSED`, `I-INT-BYTES-DIVERGE`. Limitation: a hash match/mismatch is not a PKI-
grade identity proof.

**EXPLAINABILITY** — Measures: model-card documentation coverage — are the expected
sections (intended use, limitations, training data, evaluation) present. Does NOT
claim: SHAP, LIME, attention analysis, or any runtime explanation of the model's
actual behavior. Metric: "Documentation coverage," a ratio — never called a score.
Insufficient evidence: no card text at all. Limitation: explicitly disclosed in the
persisted evidence itself — "documentation coverage is not equivalent to explanation
quality."

**SAFETY** — Measures: governance/disclosure checklist items in the model card
(intended use, misuse guidance, ethical considerations) plus lexical flags for certain
phrases. Does NOT claim: refusal-rate testing, jailbreak resistance, or any behavioral
red-teaming — no prompts are ever sent to the model for this. Metric: same
"Documentation coverage" wording, never "Safety score." Limitation: this is Track 1
(documentation) only; there is no red-teaming code anywhere in this codebase.

---

## PART 17 — EXPLAIN FRIES

"FRIES is the single final number TrustLens can produce, and it only exists once a
human has supplied Occurrence, Severity, and Detection for every required aspect.

It exists because I wanted a single, comparable number at the end, but I refused to
compute it from a black box — so the formula itself is simple and fixed: for each named
risk, `Pi = cbrt(O × S × D)`, with a hard veto to zero if any one of O, S, D is zero.
Those get averaged per aspect, then combined across the five FRIES dimensions with
weights that default to equal (0.2 each, always summing to 1).

The inputs it needs are exactly O, S, D per aspect — nothing else. The role of human
review is to supply those three numbers; TrustLens's own deterministic engine never
proposes them, because how to map a measured metric onto Occurrence, Severity, and
Detection is genuinely unresolved — I say that directly in the scoring code's own
comments, and I wasn't willing to fake an answer to it.

FRIES is withheld — `fries_score: null`, never a fabricated zero — whenever any required
aspect is missing a complete O/S/D triple. And the distinction I keep coming back to:
the probe evidence (the 0.28 accuracy drop, say) is one thing; the final FRIES
interpretation is a completely separate thing, produced only after a human has looked
at that evidence and made a judgment call."

---

## PART 18 — EVIDENCE-FIRST PHILOSOPHY

Exact lines to memorize:

- "We don't claim something just because the model exists — every claim in this system
  traces back to a specific measurement or an explicit human judgment."
- "We separate evidence from risk — a metric being computed is not the same thing as a
  risk being named; a risk only gets named once a gate passes."
- "We don't treat missing evidence as proof of safety — 'insufficient evidence' and
  'no risk found' are two different states in this system, on purpose."
- "We abstain when the evidence is insufficient — the system says so explicitly instead
  of filling the gap with a guess."
- "We don't let the AI invent the measurements — every number in Fairness, Robustness,
  Integrity, Explainability, and Safety comes from fixed, deterministic code, not from
  a model's own judgment."

---

## PART 19 — SECURITY / DATA-PRIVACY EXPLANATION

**Local-first processing** — WHAT IT PROTECTS: the model and dataset never leave the
machine running TrustLens. WHY IT MATTERS: no third party ever sees the data being
evaluated. LIMITATION: it's still a single machine's trust boundary — if that machine
is compromised, so is everything on it.

**Dataset ownership controls** — WHAT IT PROTECTS: one user's uploaded CSV can't be read
by another user (403, admin excepted). WHY IT MATTERS: multi-user local instances don't
leak each other's data. LIMITATION: evaluations and reports themselves use a documented
shared-read model — any authenticated user can view any evaluation by id; this is an
intentional MVP choice, not an oversight, but worth knowing about.

**Model repository restrictions / host allowlist** — WHAT IT PROTECTS: model imports
only ever talk to `huggingface.co`/`www.huggingface.co`. WHY IT MATTERS: no
server-side-request-forgery surface for fetching an attacker-controlled URL.
LIMITATION: it's an allowlist, not a full network sandbox.

**Documentation URL handling** — WHAT IT PROTECTS: user-supplied documentation URLs
(papers, external cards) are stored as a pointer only — never fetched server-side.
WHY IT MATTERS: there's genuinely no SSRF surface here, by design, not by a filter that
could be bypassed. LIMITATION: a human still has to manually follow the link to verify
its content.

**Filename sanitization** — WHAT IT PROTECTS: an uploaded CSV's filename is normalized
before it's used to build an object-storage key — no path traversal, no control
characters, no escaping the intended per-user/per-dataset prefix. WHY IT MATTERS: I
found and fixed this in my own audit; a crafted filename could otherwise reach outside
its intended storage location. LIMITATION: it's deterministic normalization, not a
full path-validation library.

**Model revision pinning / dataset hash verification** — WHAT IT PROTECTS: the exact
model and dataset evaluated is frozen and content-hashed at creation time. WHY IT
MATTERS: it's what makes the whole contract reproducible and non-substitutable later.

**Authenticated API access** — every `/v1` route requires a bearer JWT; mutating
routes are additionally role-gated (reviewer/admin) where appropriate.

**Generic error responses** — unhandled exceptions return a structured
`INTERNAL_ERROR` body with no stack trace or internal path; full details only go to
server-side logs.

**Secrets never in lifecycle events** — `EvaluationEvent.detail` is deliberately a
small, closed-shape JSON payload — reason codes and counts, never raw exception text,
stack traces, or file paths.

---

## PART 20 — REPRODUCIBILITY

"Reproducible here means: same model reference, same pinned revision, same dataset
identity/revision (or, for a user dataset, the same content hash), same evaluation
contract, same fixed thresholds and bootstrap settings, re-run through the same local
inference path, should give you the same evidence and the same gate/risk outcomes.
Every one of those identity facts — model revision, dataset revision, documentation
revision and hash, the contract itself — is frozen and persisted, and the report's own
Reproducibility section states this explicitly.

What I do **not** claim is bit-for-bit identical output across every machine — different
hardware, different CUDA/driver versions, different library builds can all introduce
tiny floating-point differences in real inference. The report text says exactly that:
'this is reproducible configuration, not a claim of bitwise-identical output.' I'd
rather state that limitation plainly than let 'reproducible' imply more than it does."

---

## PART 21 — TESTING + VALIDATION

**Backend:** 536 tests passing (pytest), against a real, isolated Postgres database
(`TEST_DATABASE_URL`, never the development database — I specifically hardened this
after finding the test suite could otherwise touch dev data). This includes migration
upgrade/downgrade/re-upgrade tests, and a genuine multi-threaded concurrency test that
opens two real database transactions to prove the report-version race actually can't
happen.

**Frontend:** 30 tests passing — 25 via Vitest + Testing Library (component/DOM
behavior: FRIES withheld never rendering as zero, O/S/D fields being independently
editable, the evidence timeline handling empty/unknown states honestly), 5 via Node's
built-in test runner (pure formatting/parsing logic).

**Real Docker/GPU validation, done live, not just configured:** rebuilt the worker
image with the default (GPU-enabled) Compose configuration, confirmed `nvidia-smi`
inside the container, confirmed `torch.cuda.is_available()` is `True`, then ran a real
evaluation and confirmed `execution_device: cuda`, `gpu_name` matching the real card,
identically in the database, the API, and the generated report.

**Real evaluation validation:** a real Robustness run (SST-2, real GPU inference,
described in Part 4), a real user-dataset Fairness run (real uploaded CSV, real SHA-256,
real group discovery, real per-group inference), a real complete O/S/D → scored FRIES
run, and a real withheld-FRIES run — all cross-checked across the database, the API
response, and the generated report JSON.

**PDF validation:** confirmed a real, valid PDF file (`%PDF-1.7` header, correct size,
correct recorded SHA-256) was generated from the canonical report JSON in the Docker
environment.

**What was mocked in the test suite:** Redis/Celery enqueue is monkeypatched in most
backend tests (the pipeline itself is called directly); MinIO/report storage uses an
in-memory fake store that specifically enforces "never overwrite an existing key" so
tests catch any accidental violation of append-only semantics; live Hugging Face Hub
calls are gated behind an explicit opt-in flag and skipped by default.

**What's honestly not covered live:** the CPU-only Compose override wasn't
independently re-run in my last validation pass (the code path and its "never fabricate
a GPU" behavior are unit-tested, just not re-run live that session); a genuinely
undocumented/no-card Hugging Face model wasn't independently re-fetched live in that
same pass (covered by the automated documentation tests instead); PDF text-content
extraction (versus structural validity) wasn't checked, since I didn't have a PDF-
reading tool in that environment; and the actual browser/visual walkthrough was
UNVERIFIED in that pass because the browser automation tool wasn't connected — I did
not fabricate a screenshot to cover for that.

**"How do you know your project works?"** — "Because I have 536 backend tests and 30
frontend tests passing against real infrastructure — not mocks pretending to be a
database — plus I personally ran real evaluations against real cached Hugging Face
models on real GPU hardware and cross-checked the numbers by hand across the database,
the API, and the report."

**"What remains untested?"** — answered honestly above; I don't pretend everything is
covered.

---

## PART 22 — LIMITATIONS + POST-MVP

**"WHAT I WILL SAY WHEN PROFESSOR ASKS WHAT IS NOT IMPLEMENTED"**

- Advanced behavioral safety evaluation (red-teaming, jailbreak/refusal-rate testing) —
  **POST-MVP**. Safety today is documentation/governance only.
- Runtime explanation methods (SHAP, LIME, attention visualization) — **POST-MVP**.
  Explainability today is documentation coverage only.
- Stronger semantic/adversarial robustness (beyond character-swap perturbation) —
  **POST-MVP**.
- Track 2 documentation-to-behavior verification (checking that what a card *claims*
  matches what the model actually *does*) — **POST-MVP**, explicitly out of scope for
  the current methodology.
- Future AI-assisted O/S/D interpretation (a proposal a human reviews, clearly labeled
  as not ground truth) — **POST-MVP**; today's engine is purely deterministic
  abstention.
- Stronger worker health monitoring — a heartbeat/lease/timeout system that detects a
  task silently stuck for hours, beyond what retry-exhaustion already covers —
  **POST-MVP**. What exists today is retry-exhaustion handling (three transient-error
  retries, then a clean RUNNING→FAILED transition) — not a general timeout/lease
  mechanism for an arbitrarily long-hung task.
- Horizontal scaling / multi-worker GPU scheduling — **POST-MVP**; the current default
  is one worker.
- Cloud/multi-tenant deployment — **POST-MVP**; this is a local-first tool today.

---

## PART 23 — RAPID-FIRE PROFESSOR QUESTIONS

*(Format: 15–30s answer, deeper technical answer, and a "don't say this" trap where one
exists.)*

**What problem does TrustLens solve?**
"It gives you an honest, evidence-backed answer about a Hugging Face model across five
trust dimensions, instead of a single opaque score." Deeper: it's specifically about
separating measurement from judgment — evidence, gates, risks, and human O/S/D are all
kept as distinct, traceable layers. Don't say: "it proves the model is trustworthy" —
it never proves that; it measures specific things and abstains otherwise.

**What is the novelty?**
"The evidence-first architecture — a risk can never be named without a passed gate
behind it, and the system explicitly abstains (FRIES withheld) rather than fabricate a
score when evidence or human judgment is missing." Don't say this is a novel ML
algorithm — the novelty is the architecture/methodology discipline, not a new metric.

**Why five dimensions?**
"Fairness, Robustness, Integrity, Explainability, Safety map onto five genuinely
different, independently measurable questions about a model — mixing them into one
number would hide which one actually has a problem." Don't say all five are measured
with equal depth — Fairness/Robustness run real inference; Integrity/Explainability/
Safety are documentation-based.

**Why local-first?** — see Part 11.

**Why FastAPI?** — see Part 9. Don't say FastAPI runs the inference — the worker does.

**Why React?** — see Part 9.

**Why PostgreSQL?** — see Part 13.

**Why Celery?** — see Part 12. Don't claim a full heartbeat/timeout system exists.

**Why MinIO?** — see Part 14.

**Why Docker?** — reproducible, one-command local environment across machines.

**Why not just use an LLM?** — see Part 15. Don't say "LLMs can't be trusted" as a
blanket claim — the actual reason is reproducibility and validated methodology, stated
precisely.

**Why not just use one trust score?** — because collapsing five independent
measurements into one number, without keeping the evidence traceable, is exactly the
overclaiming TrustLens is designed to avoid.

**What is an evaluation contract?** — a frozen JSON object (`EvaluationContractV1`)
recording exactly which model+revision, dataset+revision (or user dataset+hash), and
contract kind this evaluation is locked to, resolved once at creation and never
re-derived later.

**What is CAS?** — compare-and-swap: an atomic conditional database update — "set status
to X only if it's currently Y" — the single mechanism every lifecycle transition in
TrustLens uses.

**Why are events append-only?** — so the audit trail can't be edited after the fact;
mistakes get a new event, not an edited old one.

**Why are evidence and risk separate?** — a metric is a fact; a risk is a judgment that
fact crossed a threshold. Conflating them would let a borderline or noisy number get
reported with false confidence.

**Why can the system say insufficient evidence?** — because a gate (minimum sample
size, label compatibility, presence of documentation) failed — the honest answer is "I
can't measure this reliably," not a fabricated result.

**What is FRIES?** — see Part 17.

**What are O/S/D?** — Occurrence, Severity, Detection — human-entered integers 0–10 per
FRIES aspect, combined by `Pi = cbrt(O·S·D)`.

**Why is human review required?** — because metric-to-O/S/D mapping is unresolved;
TrustLens won't invent that judgment.

**What happens if the worker fails?** — a transient error retries up to 3 times with
backoff; a logic error transitions straight to FAILED without retrying; exhausted
retries also transition to FAILED via the same CAS.

**What happens if retries are exhausted?** — `on_failure` fires exactly once, CAS'es
RUNNING→FAILED, records one event with `reason_code: worker_retries_exhausted`.

**What happens if two workers update the same evaluation?** — the CAS admits only one;
the other's conditional update matches zero rows and is a safe no-op.

**How is reproducibility achieved?** — see Part 20.

**How is the dataset verified?** — SHA-256 content hash computed at upload, frozen into
the contract, and the dataset re-verified against that hash before use.

**How is model identity verified?** — the exact revision (a git SHA from the Hub) is
pinned at import and frozen into the contract; the pipeline explicitly never re-reads a
possibly-drifted live model row.

**How do you handle missing documentation?** — `retrieval_status: not_found` (or "no
card text"), and Explainability/Safety report `INSUFFICIENT_EVIDENCE` rather than
fabricating coverage.

**What does fairness/robustness/integrity/explainability/safety actually measure?** —
see Part 16, verbatim.

**Can you prove the model is safe?** — "No — Safety here is a documentation/governance
check, not a behavioral safety test. I say that explicitly rather than imply more."

**Can you prove the model is fair?** — "No — Fairness measures one specific disparity
metric on one specific dataset; it's evidence toward the question, not a certification."

**Can TrustLens be wrong?** — "The evidence and gates are deterministic and testable,
so 'wrong' there would be a bug I could find and fix — I actually did find and fix two
in my own audit. The human-entered O/S/D and the resulting FRIES number can absolutely
be wrong in the sense that they reflect a person's judgment, which the system never
pretends to validate."

**What are the limitations? / biggest weakness of your architecture?** — "Probably the
worker layer — Celery gives me retries and a clean failure callback, but I don't yet
have a general timeout/heartbeat system for a task that hangs without raising an
exception at all. That's the next thing I'd build."

**What would you change with more time?** — the AI-assisted O/S/D proposal mode
(clearly labeled, human-reviewed), Track 2 documentation-to-behavior checks, and a real
worker health-monitoring system.

**How would you scale it?** — more Celery worker replicas behind the same Redis broker
(already Celery's native model), plus a GPU-scheduling story if running several workers
on shared hardware.

**What happens if PostgreSQL goes down?** — every DB-backed request fails cleanly
(`503 DATABASE_UNCONFIGURED` or a connection error) rather than silently proceeding;
no in-flight write is left half-committed because everything is one transaction per
request.

**What happens if MinIO goes down?** — evidence/report reads and writes fail with
`503 STORAGE_UNAVAILABLE`; the DB-side lifecycle itself isn't corrupted, since the
report DB row is only inserted after the storage write succeeds.

**What happens if the worker dies mid-task?** — with `task_acks_late=True`, the message
is redelivered; the pipeline's own CAS-gated first step means a redelivered task that
already got as far as `RUNNING` (or further) safely no-ops instead of re-running.

**What happens if a task runs for hours?** — honestly: today, nothing automatically
intervenes unless it eventually raises a `ConnectionError`/`TimeoutError` that exhausts
retries. A general stuck-task timeout is POST-MVP — don't claim otherwise.

**Why not Kafka instead of Celery?** — Kafka is a distributed log/streaming platform;
I needed a task queue with built-in retry semantics for a handful of background jobs,
not a high-throughput event stream — Celery+Redis is the right-sized tool.

**Why not MongoDB?** — I need real transactions and atomic conditional updates for the
CAS lifecycle; a relational database gives me that directly.

**Why not SQLite?** — SQLite doesn't give the same concurrent-writer story Postgres
does, and I specifically needed two truly independent concurrent transactions to prove
the report-version race is actually prevented.

**Why not run everything synchronously?** — see Part 12; inference is too slow for a
blocking HTTP request.

**Why Docker Compose?** — one file, one command, every service (Postgres/Redis/MinIO/
API/worker/frontend) with correct dependencies.

**What is asynchronous processing? / What is an API? / What is FastAPI? / What is
Uvicorn? / What is Alembic? / What is SQLAlchemy? / What is an ORM? / What is a
migration? / What is a worker? / What is a queue?** — Give the plain, one-sentence
definition for whichever of these come up (these are "explain the basics" questions,
not gotchas): asynchronous processing means work happens in the background instead of
blocking the caller; an API is a defined way for programs to talk to each other; FastAPI
is the Python web framework this API is built with; Uvicorn is the ASGI server that
actually runs FastAPI; Alembic is SQLAlchemy's schema-migration tool; SQLAlchemy is the
Python ORM/SQL toolkit used here; an ORM maps database rows to Python objects; a
migration is a versioned, reversible schema change; a worker is a separate process that
consumes and executes background jobs; a queue is the ordered list of pending jobs a
worker consumes from (Redis, here).

**What is a model revision?** — a specific, immutable commit/version of a Hugging Face
model repo, identified by a git SHA.

**What is a confidence interval? Why bootstrap? Why Wilson interval?** — a confidence
interval expresses the uncertainty around a point estimate from a finite sample.
Bootstrap (resampling with replacement, 1,000 times, percentile method) is used for the
accuracy-drop interval because it doesn't assume a particular distribution shape.
Wilson-score intervals are used for the clean/robust accuracy proportions themselves,
which is a standard, better-behaved interval for a proportion than the naive normal
approximation, especially near 0 or 1.

**What are gates?** — explicit validity checks (minimum sample size, perturbation
coverage, label compatibility) that must pass before a probe is allowed to name a risk.

**Why should confidence affect risk interpretation?** — because a point estimate alone
can't tell you if an observed drop is real or just sampling noise; requiring the
confidence interval's own lower bound to also clear the threshold is a stricter,
more honest bar.

**Why don't you automatically infer sensitive attributes?** — because deciding what
counts as a protected/sensitive attribute is a value judgment, not a statistical fact —
a human picks the group column explicitly.

**Why don't you automatically infer O/S/D?** — see Part 17/15 — the mapping is
unresolved research; I refuse to fake it.

**Why doesn't documentation automatically prove safety/explainability?** — because a
well-written card doesn't guarantee the model actually behaves as described — that's
exactly why Explainability/Safety are labeled "Documentation coverage," never a claim
about actual behavior.

---

## PART 24 — LIVE DEMO FAILURE RECOVERY

- **Page doesn't load:** "Give me one second — this is a local dev server, not a hosted
  service, so let me just confirm the containers are up." (Check `docker ps` calmly.)
- **Evaluation takes longer than expected:** "This is expected — the worker is actually
  loading real model weights and running real inference, not simulating anything. It
  stays responsive because the API isn't blocked waiting on it."
- **Worker is slow:** "I can show you the worker's own logs while we wait, so you can
  see exactly which probe is running right now."
- **API returns an error:** "Let's look at the actual error code — TrustLens returns
  structured error codes on purpose, so I can tell you exactly what just happened
  instead of guessing."
- **Model download takes time:** "This model isn't cached locally yet, so it's pulling
  weights from the Hub right now — in a real run I'd pre-cache the model I'm
  demonstrating, exactly like I did for today."
- **Report generation fails:** "Report generation needs the object storage service to
  be reachable — let me confirm MinIO is up; if it's down, the API will tell us with a
  clear storage-unavailable error rather than hang."
- **PDF is slow / unavailable:** "PDF rendering depends on OS-level libraries that
  aren't guaranteed on every host — if it's not available here, the report still
  returns successfully as JSON, which is the canonical document anyway."
- **Professor asks something outside the current demo:** "That's a fair question — it's
  not something I can show live right now, but let me explain exactly what the code
  does for that case." (Then answer from this script's relevant part.)
- **I forget a technical term:** "Let me get the wording exactly right rather than
  guess" — pause, then give the accurate version; it's fine to take two seconds.
- **A live result differs slightly from a previous run:** "That's expected, actually —
  I've been explicit that this is reproducible configuration, not bit-for-bit identical
  output; small floating-point differences across hardware or library versions are
  normal and I call that out directly in the report itself."
- **A feature is unavailable in this environment:** "That's genuinely not verified in
  this environment, and I'd rather tell you that than fake it — here's what the code
  does and how I verified it elsewhere."

---

## PART 25 — PRESENTATION ORDER

0. Prepare environment — `docker compose up -d`, pre-import/pre-cache the demo model.
1. Introduce the problem (Part 1).
2. Introduce TrustLens (Part 1 / Part 18).
3. Architecture (Part 8).
4. Create an evaluation (Steps 4–6).
5. Happy-path execution (Steps 7–15).
6. Explain evidence (Step 15 / Evidence Dossier).
7. Show a named risk (Part 4, real Robustness numbers).
8. Human review (Part 5).
9. FRIES (Step 18 / Part 17).
10. Timeline (Step 19).
11. Report (Step 20/21).
12. PDF (Step 22).
13. Deliberate insufficient-evidence / withheld example (Part 4).
14. Failure/retry example (Part 6, described, not forced).
15. Architecture/tech-stack defense (Parts 9–10, only if time/asked).
16. Limitations (Part 22).
17. Closing statement (below).

---

## PART 26 — 5 / 10 / 20-MINUTE VERSIONS

### A. 5-MINUTE COMPRESSED DEMO
- Skip: model import (pre-done), the full contract wizard (jump straight to Review),
  worker logs, tech-stack defense.
- Click: New evaluation (pre-selected model) → pick the approved Robustness contract →
  Run → wait (or resume a pre-run evaluation) → point at the Robustness card and the
  Overall FRIES card (withheld) → View report.
- Say: "Fixed measurement, named risk only if a gate passes, and the score is withheld
  until a human enters Occurrence/Severity/Detection — never a guessed number."

### B. 10-MINUTE NORMAL DEMO
- Follow Part 2 exactly.

### C. 20-MINUTE DETAILED DEMO
- Everything in Part 2, plus: the full contract-creation wizard from scratch (Steps
  4–5), a real human-review walkthrough (Part 5, Case B then Case C on two prepared
  evaluations), the insufficient-evidence path (Part 4) shown side-by-side with the
  scored path, one non-happy-path description (Part 6, #5 retry exhaustion), and the
  tech-stack/architecture defense (Parts 9–10) if the professor engages with it.

---

## PART 27 — FINAL ONE-PAGE CHEAT SHEET

**PROJECT IN ONE SENTENCE:** TrustLens runs fixed, evidence-first measurements across
five trust dimensions of a Hugging Face model and only produces a final score once a
human has supplied the judgment (O/S/D) that measurement alone can't give.

**ARCHITECTURE IN ONE SENTENCE:** React/Vite frontend → FastAPI → Postgres (state) +
MinIO (artifacts), with a Celery worker (Redis broker) doing the actual model
inference in the background.

**FIVE DIMENSIONS:** Fairness, Robustness, Integrity, Explainability, Safety.

**CORE PHILOSOPHY:** Evidence first, gates before risk, abstain rather than fabricate.

**HAPPY PATH:** Import model → freeze contract → PENDING → RUNNING → five probes →
evidence persisted → (review if assisted) → O/S/D → FRIES → timeline → report → PDF.

**FAILURE PATH:** Logic error → immediate FAILED (no retry); transient error → retry ×3
→ exhausted → FAILED via CAS; enqueue failure → confirmed, reconcilable, never
guessed.

**MOST IMPORTANT METRICS (real, from my own run):** Robustness clean=0.975,
robust=0.695, drop=0.28, CI lower=0.22, risk R-ROB-PERT; FRIES=5.3845 once scored.

**MOST IMPORTANT DESIGN DECISIONS:** frozen EvaluationContractV1; CAS as the only
status-mutation path; append-only events; canonical report JSON (PDF is a projection);
deterministic O/S/D abstention; withheld FRIES is never a fabricated zero.

**TOP 15 QUESTIONS + ONE-LINE ANSWERS:** see Part 23 for full answers; the one-liners
are the bold-faced questions themselves, in order, from "What problem does TrustLens
solve" through "Why not run everything synchronously."

**TOP 10 THINGS I MUST NOT CLAIM:** see Part 22 / below.

**TOP 10 SENTENCES TO MEMORIZE:**
1. "TrustLens never free-text evaluates a model."
2. "This is not a low trust score — it means no synthesized score exists yet."
3. "A blank field stays blank. It is never silently treated as a zero."
4. "There is no red-teaming, no jailbreak testing, and no refusal-rate measurement
   anywhere in this codebase."
5. "You will never see the words 'Explainability score' anywhere — only 'Documentation
   coverage.'"
6. "The whole lifecycle runs through one atomic, conditional database update — never a
   plain write."
7. "The PDF is rendered from the exact same JSON document as the web report."
8. "Reproducible means same configuration, same evidence path — not bit-for-bit
   identical output."
9. "I'd rather show nothing than show a number I can't justify."
10. "Insufficient evidence and no-risk-found are two different states, on purpose."

---

## PART 22 (CLAIMS) — TOP 10 CLAIMS I MUST NEVER MAKE

1. "TrustLens proves the model is safe." — it does not; Safety is documentation-only.
2. "TrustLens proves the model is fair." — it measures one disparity metric on one
   dataset, not a fairness certification.
3. "Explainability uses SHAP/LIME." — not implemented; documentation coverage only.
4. "Robustness covers adversarial attacks in general." — only character-swap
   perturbation is implemented.
5. "O/S/D are inferred automatically." — always human-entered, never inferred.
6. "This runs in the cloud." — it's local-first; Docker Compose on one machine.
7. "Reports are bit-for-bit reproducible across machines." — configuration-reproducible
   only, explicitly not bitwise.
8. "There's a worker heartbeat/timeout/lease system." — not implemented; only
   retry-exhaustion → FAILED exists.
9. "There's a single overall trust score." — FRIES is per-evaluation and can be
   withheld entirely; there is no cross-dimension "trust score" fabricated when
   evidence is missing.
10. "A named risk means the model is bad." — a named risk means a specific gated
    threshold was crossed on a specific metric; it's evidence toward a judgment, not
    the judgment itself.

---

## FINAL CLOSING STATEMENT

"That's TrustLens — a local-first system that measures five specific things about a
model, using fixed, auditable code, and that refuses to turn silence into a score. Every
number you saw today traced back to a real measurement or a real human decision, and
where the evidence wasn't there, the system said so instead of guessing. That
discipline — evidence first, judgment second, and abstain rather than fabricate — is
the actual contribution of this project, more than any single metric inside it. Thank
you."
