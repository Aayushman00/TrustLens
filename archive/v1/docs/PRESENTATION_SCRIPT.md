# TrustLens: 10-minute presentation script + Q&A drill

Spoken script. **[brackets]** = what to click or show. Times add up to 10:00.
Pre-run evaluation = the finished `cardiffnlp/twitter-roberta-base-offensive` run. Open it in a tab before you start.

---

## 1. Problem and pitch (0:00–1:00)  [slide 1]

"Downloading a classifier from Hugging Face takes one line of code. Deciding whether it deserves to be used is much harder.
Today people look at one accuracy number and a model card, and that hides the questions that matter: is it fair across groups, does it break under noisy input, are the weights what they claim to be?

TrustLens is my answer. It **measures** a model on five dimensions, **maps** each measurement to a named risk, lets a **human rate** that risk, and **withholds** a score instead of guessing when the evidence isn't there.

The five dimensions are FRIES: Fairness, Robustness, Integrity, Explainability, Safety.
One thing up front: this is a traceable risk profile. It is not a proof that a model is safe."

## 2. Architecture (1:00–2:00)  [slide 2]

"Everything runs locally. The React frontend talks to a FastAPI backend over a versioned REST API.
The API never runs inference. It writes state to **Postgres** and artifacts to **MinIO**, then hands the job to a **Celery worker** through Redis.
The worker loads the model, runs the probes on CPU or GPU, and writes evidence under SHA-256 hashes.
I did it this way so the UI stays responsive during slow inference, and so the model and data never leave the machine."

## 3. Five dimension cards + Evidence Dossier (2:00–4:00)  [browser: finished evaluation]

[Open the evaluation. Point at the header Contract line.]
"This is a real audit of a model that appears nowhere in my thesis experiments, scored on fresh data. The contract line shows the three configured probes: Fairness, Robustness and Safety."

[Point at the five cards in turn, one sentence each.]
- "**Fairness**: equal-opportunity gap between groups, with a bootstrap confidence interval."
- "**Robustness**: clean accuracy against accuracy after character-swap noise."
- "**Integrity**: weight-file hashes checked against the Hub's published sha256."
- "**Explainability**: how complete the model card is. It's documentation coverage, not SHAP or LIME."
- "**Safety**: severe-miss rate on rows labelled severe, plus a governance checklist."

[Open **Evidence Dossier** → Fairness.]
"This is the part I care most about. Every number has a chain: observed evidence, then derived metric, then gate, then risk decision, then human judgment, then limitation. A reader can follow any claim back to raw data and hashes."

## 4. Honesty angle (4:00–5:00)  [point at a gate chip]

[Point at an `INSUFFICIENT_EVIDENCE` / `NOT_APPLICABLE` chip, or `G-FAIR-CI-WIDE` / `I-INT-LICENSE-UNDISCLOSED`.]
"Look at this chip. The tool is saying 'I can't measure this reliably', because a gate failed. For example the confidence interval was too wide, or the model card has no license.
A tool that always returns a number looks more impressive, but a made-up number is worse than no number. And a withheld FRIES is not a zero. It means no score exists yet."

## 5. Human review + finalize (5:00–7:00)  [Review page, status AWAITING_REVIEW]

"The engine only proposes Occurrence, Severity and Detection ratings. They're marked `PROPOSED_REQUIRES_VALIDATION`. Measured evidence is read-only here, and the human enters the judgment."

[Override one value, e.g. Detection 7 → 5. Type a rationale: "Probe set is English-only, so detection confidence is lower."]
"I'm changing this one and recording why. The rationale is stored with the rating."

[Click **Finalize**.]
"Per risk the score is the cube root of O times S times D, and a zero in any term vetoes it. Those combine into an aspect score, then a weighted FRIES. The page states clearly that this is an audit artifact."

## 6. Report + timeline (7:00–8:00)  [Timeline → Report → download JSON and PDF]

"The timeline is append-only, so mistakes get a new event rather than an edit. The report is versioned JSON, and the PDF is a projection of the same source, not a separate calculation. Revisions, dataset hashes and seeds are all in the Reproducibility section."

## 7. Limitations + close (8:00–10:00)  [slide 3]

"What it does not do:
- Robustness covers text classifiers and character swaps only.
- Explainability is model-card based, not runtime explanation.
- Safety needs user-supplied labelled data, and it is not red-teaming.
- The O/S/D bands are heuristics pending validation.
- The evaluation set is English, and it's a single-user local tool.

What I'd build next: stronger worker health monitoring, richer perturbations, and validated O/S/D bands.

To close: TrustLens doesn't tell you whether to trust a model. It shows exactly what was measured, what that implies, who judged it, and what it couldn't know. Thank you. Happy to take questions."

---

## Q&A drill

Say the **short** answer first. Go deeper only if they push.

| Question | Short answer | Trap: don't say |
|---|---|---|
| What problem does it solve? | Honest, evidence-backed audit across five dimensions, instead of one opaque score. | "It proves the model is trustworthy." |
| What's novel? | The architecture: no risk without a passed gate, and it abstains instead of fabricating. | That it's a new ML algorithm or metric. |
| Why five dimensions? | Five different, independently measurable questions. One number would hide which one is broken. | That all five run at equal depth. |
| Why a human in the loop? | Metric → O/S/D mapping is unresolved research. I won't fake it. | "AI can't do it." Say it's not validated. |
| Why not just use an LLM? | Reproducibility and validated methodology. `llm_v1` exists as opt-in, labelled as a proposal. | "LLMs can't be trusted." |
| What's a gate? | A validity check (min sample, CI width, label compatibility) that must pass before a risk is named. | |
| What's evidence vs risk? | A metric is a fact. A risk is the judgment that the fact crossed a threshold. | |
| Why bootstrap CI? | Resampling makes no distribution assumption. Wilson intervals for proportions behave better near 0 or 1. | |
| What is an evaluation contract? | Frozen JSON of model revision, dataset hash and probe config, set once and never re-derived. | |
| Reproducibility? | Pinned HF revision, SHA-256 on dataset and artifacts, methodology version, seeds in the report. | "Bit-for-bit identical." Float differences are possible. |
| Can you prove it's safe / fair? | No. It measures specific things on specific data. Evidence toward the question, not certification. | |
| Can TrustLens be wrong? | Evidence and gates are deterministic and testable. O/S/D and FRIES reflect human judgment, which it never claims to validate. | |
| Why Celery / Postgres / MinIO? | Celery: inference is too slow for an HTTP request and needs retries. Postgres: transactions and atomic conditional updates. MinIO: S3-style artifact storage that stays local. | |
| Why local-first? | Model and data stay on the machine, and nothing depends on a cloud API. | |
| What is CAS? | Compare-and-swap: "set status to X only if it is currently Y". Every lifecycle transition uses it. | |
| What if the worker dies? | `task_acks_late` redelivers the task, and the CAS-gated first step makes a redelivery safe. Transient errors retry 3 times, then go to FAILED. | That a hang-timeout exists. |
| Biggest weakness? | A task that hangs without raising has no automatic timeout or heartbeat yet. Next thing I'd build. | |
| Why no sensitive-attribute inference? | Choosing a protected attribute is a value judgment, so a human picks the column. | |
| Why is the demo score low? | The model is out-of-distribution (tweets vs news comments). Low evidence is a finding, not a failure. I don't retune thresholds live. | |
| Scale it? | More Celery workers on the same Redis broker. GPU scheduling is future work. | |

**Check before you speak:** `docs/TRUSTLENS_DEMO_VIVA_SCRIPT.md` Parts 22 and 23 still say "Safety is documentation only" and "deterministic abstention only". The README and `DEMO_UNSEEN_MODEL.md` say Safety now includes a severe-miss probe and that `legacy_heuristic` and `llm_v1` engines exist. This script follows the README. Check the code or the thesis if asked for exact detail.

---

## Failure recovery (stay calm, say it out loud)

| If this happens | Do this | Say this |
|---|---|---|
| Page won't load | `docker ps`, then `docker compose up -d` | "Local dev server, not hosted. Confirming the containers are up." |
| Stuck at `RUNNING 0/5` | Show `docker compose logs worker` | "The worker is downloading real weights and running real inference, not simulating." |
| Run is slow | Switch to the pre-run evaluation tab | "Inference on 2,000 rows is the slow part, so here's the finished run of the same configuration." |
| Evaluation `FAILED` | Show the error and the `FAILED` timeline event | "Failures are recorded, not hidden. Here's the exact error." |
| API error | Read the structured error code | "It returns structured codes on purpose, so I can say exactly what happened." |
| Hub unreachable | Use the `results/external_hub_validation_20261003_v9r/` evaluations | "No network, so I'm showing a stored run. Same screens." |
| Report or PDF fails | Download the JSON | "JSON is the canonical document. The PDF is a projection and needs OS libraries." |
| Numbers differ from rehearsal | Don't apologise | "Expected. Reproducible configuration, not bit-identical floating point." |
| A question you can't answer | Pause two seconds | "Let me get the wording exactly right." Then explain what the code does. |
| Asked about an unbuilt feature | Be direct | "Not implemented. It's in my limitations, and here's how I'd build it." |

**Never claim:** that it proves safety or fairness, that it does red-teaming, that it gives SHAP/LIME explanations, that Explainability is a score (it's "documentation coverage"), or that a hang-timeout exists.
