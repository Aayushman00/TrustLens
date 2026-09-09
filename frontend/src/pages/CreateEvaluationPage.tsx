import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { apiFetch, apiUpload } from "../api/client";
import type {
  EvaluationCreate,
  EvaluationOptionsRead,
  EvaluationRead,
  GroupDiscoveryRead,
  ModelList,
  ModelRead,
  UserDatasetList,
  UserDatasetRead,
} from "../api/types";
import ContractCatalog, { type ContractSelection } from "../components/ContractCatalog";
import ErrorNotice from "../components/ErrorNotice";
import Spinner from "../components/Spinner";
import { shortRevision } from "../lib/contract";

type Family = "fairness" | "robustness" | "documentation";
type Step = "model" | "family" | "source" | "contract" | "dataset-setup" | "review";
type FairnessSource = "approved" | "local";

const MISSING_GROUP_VALUE = "(missing)";

/** Expected per-dimension outcome, derived from the selected contract's
 * shape and the current (unchanged) probe dispatch logic — never a claim
 * about statistical results, only about which dimension will attempt to run. */
function expectedDimensionOutcomes(choice: ContractSelection | null) {
  const always = { INTEGRITY: "Will run", EXPLAINABILITY: "Will run", SAFETY: "Will run" };
  if (!choice) return { FAIRNESS: "Not applicable", ROBUSTNESS: "Not applicable", ...always };
  if (choice.family === "fairness" && choice.pairing_id) {
    return { FAIRNESS: "Model-faithful", ROBUSTNESS: "Not applicable", ...always };
  }
  if (choice.family === "fairness" && choice.contract_kind === "proxy_lr") {
    return { FAIRNESS: "Proxy", ROBUSTNESS: "Not applicable", ...always };
  }
  if (choice.family === "fairness" && choice.user_dataset_id) {
    return { FAIRNESS: "User-defined local evaluation", ROBUSTNESS: "Not applicable", ...always };
  }
  if (choice.family === "robustness") {
    return { FAIRNESS: "Not applicable", ROBUSTNESS: "Model-faithful", ...always };
  }
  return { FAIRNESS: "Not applicable", ROBUSTNESS: "Not applicable", ...always };
}

export default function CreateEvaluationPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const [modelId, setModelId] = useState<number | null>(
    params.get("modelId") ? Number(params.get("modelId")) : null,
  );
  const [models, setModels] = useState<ModelRead[] | null>(null);
  const [model, setModel] = useState<ModelRead | null>(null);
  const [options, setOptions] = useState<EvaluationOptionsRead | null>(null);
  const [family, setFamily] = useState<Family | null>(null);
  const [choice, setChoice] = useState<ContractSelection | null>(null);
  const [step, setStep] = useState<Step>(modelId ? "family" : "model");
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

  // User-defined local Fairness dataset wizard state.
  const [fairnessSource, setFairnessSource] = useState<FairnessSource | null>(null);
  const [datasets, setDatasets] = useState<UserDatasetRead[] | null>(null);
  const [selectedDataset, setSelectedDataset] = useState<UserDatasetRead | null>(null);
  const [uploading, setUploading] = useState(false);
  const [datasetError, setDatasetError] = useState<unknown>(null);
  const [targetColumn, setTargetColumn] = useState<string>("");
  const [groupColumn, setGroupColumn] = useState<string>("");
  const [textColumn, setTextColumn] = useState<string>("");
  const [groupDiscovery, setGroupDiscovery] = useState<GroupDiscoveryRead | null>(null);
  const [discoveringGroups, setDiscoveringGroups] = useState(false);
  const [includedGroups, setIncludedGroups] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (step !== "dataset-setup") return;
    let cancelled = false;
    apiFetch<UserDatasetList>("/v1/datasets")
      .then((page) => {
        if (!cancelled) setDatasets(page.items);
      })
      .catch((err) => {
        if (!cancelled) setDatasetError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [step]);

  useEffect(() => {
    if (!selectedDataset || !groupColumn) {
      setGroupDiscovery(null);
      return;
    }
    let cancelled = false;
    setDiscoveringGroups(true);
    apiFetch<GroupDiscoveryRead>(
      `/v1/datasets/${selectedDataset.id}/groups?column=${encodeURIComponent(groupColumn)}`,
    )
      .then((discovery) => {
        if (cancelled) return;
        setGroupDiscovery(discovery);
        setIncludedGroups(
          new Set(
            discovery.observed_groups
              .filter((g) => g.value !== MISSING_GROUP_VALUE)
              .map((g) => g.value),
          ),
        );
      })
      .catch((err) => {
        if (!cancelled) setDatasetError(err);
      })
      .finally(() => {
        if (!cancelled) setDiscoveringGroups(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDataset, groupColumn]);

  async function handleUpload(file: File) {
    setUploading(true);
    setDatasetError(null);
    try {
      const uploaded = await apiUpload<UserDatasetRead>("/v1/datasets", file);
      setDatasets((prev) => [uploaded, ...(prev ?? [])]);
      setSelectedDataset(uploaded);
      setTargetColumn("");
      setGroupColumn("");
      setTextColumn("");
      setGroupDiscovery(null);
      setIncludedGroups(new Set());
    } catch (err) {
      setDatasetError(err);
    } finally {
      setUploading(false);
    }
  }

  function toggleIncludedGroup(value: string) {
    setIncludedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  useEffect(() => {
    if (modelId != null) return;
    let cancelled = false;
    apiFetch<ModelList>("/v1/models?limit=100")
      .then((page) => {
        if (!cancelled) setModels(page.items);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [modelId]);

  useEffect(() => {
    if (modelId == null) return;
    let cancelled = false;
    async function load() {
      try {
        const [row, opts] = await Promise.all([
          apiFetch<ModelRead>(`/v1/models/${modelId}`),
          apiFetch<EvaluationOptionsRead>(`/v1/models/${modelId}/evaluation-options`),
        ]);
        if (!cancelled) {
          setModel(row);
          setOptions(opts);
        }
      } catch (err) {
        if (!cancelled) setError(err);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [modelId]);

  const outcomes = useMemo(() => expectedDimensionOutcomes(choice), [choice]);

  async function handleSubmit() {
    if (!model || !choice) return;
    setSubmitting(true);
    setError(null);
    const body: EvaluationCreate = { model_id: model.id, evaluation_mode: "AI_AUTONOMOUS" };
    if (choice.pairing_id) body.pairing_id = choice.pairing_id;
    if (choice.dataset_key) body.dataset_key = choice.dataset_key;
    if (choice.contract_kind) body.contract_kind = choice.contract_kind;
    if (choice.user_dataset_id) {
      body.user_dataset_id = choice.user_dataset_id;
      body.target_column = choice.target_column;
      body.group_column = choice.group_column;
      body.text_column = choice.text_column;
      body.included_group_values = choice.included_group_values;
    }
    try {
      const created = await apiFetch<EvaluationRead>("/v1/evaluations", {
        method: "POST",
        body,
      });
      navigate(`/evaluations/${created.id}`);
    } catch (err) {
      setError(err);
      setSubmitting(false);
    }
  }

  const usingLocalDataset = family === "fairness" && fairnessSource === "local";
  const steps: { key: Step; label: string }[] =
    family === "fairness"
      ? [
          { key: "model", label: "Model" },
          { key: "family", label: "Category" },
          { key: "source", label: "Source" },
          usingLocalDataset
            ? { key: "dataset-setup", label: "Dataset" }
            : { key: "contract", label: "Contract" },
          { key: "review", label: "Review" },
        ]
      : [
          { key: "model", label: "Model" },
          { key: "family", label: "Category" },
          { key: "contract", label: "Contract" },
          { key: "review", label: "Review" },
        ];
  const stepIndex = Math.max(
    0,
    steps.findIndex((s) => s.key === step),
  );

  return (
    <>
      <div className="page-header">
        <div>
          <h1>New evaluation</h1>
          <p className="muted">Choose an approved contract — TrustLens never free-text evaluates.</p>
        </div>
      </div>

      <div className="stepper">
        {steps.map((s, i) => (
          <Fragment key={s.key}>
            <span
              className={`step ${i < stepIndex ? "done" : i === stepIndex ? "current" : ""}`}
            >
              <span className="step-num">{i < stepIndex ? "✓" : i + 1}</span>
              {s.label}
            </span>
            {i < steps.length - 1 ? <span className="step-sep" /> : null}
          </Fragment>
        ))}
      </div>

      <ErrorNotice error={error} />

      {step === "model" ? (
        <div className="card">
          <h2>Choose a model</h2>
          {models == null ? <Spinner label="Loading models…" /> : null}
          {models != null && models.length === 0 ? (
            <p className="empty">
              No models yet — <Link to="/models/import">import one first</Link>.
            </p>
          ) : null}
          {models != null && models.length > 0 ? (
            <div className="contract-card-grid">
              {models.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className="contract-card"
                  onClick={() => {
                    setModelId(m.id);
                    setStep("family");
                  }}
                >
                  <span className="contract-card-title">{m.hf_repo_id}</span>
                  <span className="contract-card-sub mono">
                    Revision: {shortRevision(m.revision)}
                  </span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {step === "family" && model ? (
        <div className="card">
          <h2>What do you want to evaluate?</h2>
          <p className="muted">
            {model.hf_repo_id} · revision <span className="mono">{shortRevision(model.revision)}</span>
          </p>
          {options == null ? (
            <Spinner label="Loading approved contracts…" />
          ) : (
            <div className="choice-grid">
              <button
                type="button"
                className="choice-card"
                onClick={() => {
                  setFamily("fairness");
                  setFairnessSource(null);
                  setStep("source");
                }}
              >
                <span className="choice-card-icon" aria-hidden="true">
                  ⚖
                </span>
                <span className="choice-card-title">Fairness</span>
                <span className="choice-card-desc">
                  {options.fairness.length > 0
                    ? "Model-faithful pairing available, or evaluate your own local dataset."
                    : "No approved pairing for this exact model + revision — you can still evaluate your own local dataset."}
                </span>
              </button>
              <button
                type="button"
                className="choice-card"
                disabled={options.robustness.length === 0}
                onClick={() => {
                  setFamily("robustness");
                  setStep("contract");
                }}
              >
                <span className="choice-card-icon" aria-hidden="true">
                  ◈
                </span>
                <span className="choice-card-title">Robustness</span>
                <span className="choice-card-desc">
                  {options.robustness.length > 0
                    ? "Char-swap contract available for this model."
                    : "No approved contract for this exact model + revision."}
                </span>
              </button>
              <button
                type="button"
                className="choice-card"
                onClick={() => {
                  setFamily("documentation");
                  setChoice({
                    family: "documentation",
                    label: "Documentation & governance",
                    sublabel: "Always available",
                  });
                  setStep("review");
                }}
              >
                <span className="choice-card-icon" aria-hidden="true">
                  ▤
                </span>
                <span className="choice-card-title">Documentation &amp; Governance</span>
                <span className="choice-card-desc">
                  Integrity, Explainability and Safety — always available, no local inference.
                </span>
              </button>
            </div>
          )}
          <div className="btn-row" style={{ marginTop: "1rem" }}>
            <button type="button" className="btn btn-secondary" onClick={() => setStep("model")}>
              Back
            </button>
          </div>
        </div>
      ) : null}

      {step === "source" && family === "fairness" ? (
        <div className="card">
          <h2>Evaluation source</h2>
          <p className="muted">
            Compare the model's performance against an approved benchmark, or against data
            stored on this machine.
          </p>
          <div className="choice-grid">
            <button
              type="button"
              className="choice-card"
              disabled={!options || (options.fairness.length === 0 && !options.proxy_lr_available)}
              onClick={() => {
                setFairnessSource("approved");
                setStep("contract");
              }}
            >
              <span className="choice-card-icon" aria-hidden="true">
                ✓
              </span>
              <span className="choice-card-title">Approved benchmark</span>
              <span className="choice-card-desc">Use a validated TrustLens benchmark.</span>
            </button>
            <button
              type="button"
              className="choice-card"
              onClick={() => {
                setFairnessSource("local");
                setChoice(null);
                setStep("dataset-setup");
              }}
            >
              <span className="choice-card-icon" aria-hidden="true">
                ⌂
              </span>
              <span className="choice-card-title">My local dataset</span>
              <span className="choice-card-desc">
                Evaluate this model against a CSV file stored in your local TrustLens instance —
                not an approved/certified benchmark.
              </span>
            </button>
          </div>
          <div className="btn-row" style={{ marginTop: "1rem" }}>
            <button type="button" className="btn btn-secondary" onClick={() => setStep("family")}>
              Back
            </button>
          </div>
        </div>
      ) : null}

      {step === "dataset-setup" && model ? (
        <div className="card">
          <h2>Local dataset</h2>
          <p className="muted">
            The file stays on this TrustLens instance — nothing is uploaded to a hosted or cloud
            service.
          </p>
          <ErrorNotice error={datasetError} />

          <div className="review-block-label" style={{ marginTop: "0.6rem" }}>
            Upload or choose a dataset
          </div>
          <div className="btn-row">
            <label className="btn btn-secondary" style={{ cursor: "pointer" }}>
              {uploading ? "Uploading…" : "Upload CSV"}
              <input
                type="file"
                accept=".csv"
                hidden
                disabled={uploading}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (file) void handleUpload(file);
                }}
              />
            </label>
          </div>
          {datasets == null ? (
            <Spinner label="Loading your datasets…" />
          ) : datasets.length > 0 ? (
            <div className="contract-card-grid" style={{ marginTop: "0.6rem" }}>
              {datasets.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  className={`contract-card${selectedDataset?.id === d.id ? " selected" : ""}`}
                  onClick={() => {
                    setSelectedDataset(d);
                    setTargetColumn("");
                    setGroupColumn("");
                    setTextColumn("");
                    setGroupDiscovery(null);
                    setIncludedGroups(new Set());
                  }}
                >
                  <span className="contract-card-title">{d.filename}</span>
                  <span className="contract-card-sub mono">
                    {d.row_count.toLocaleString()} rows · {d.format.toUpperCase()}
                  </span>
                  <span className="contract-card-sub mono">
                    Fingerprint: {d.content_hash.replace("sha256:", "").slice(0, 8)}…
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="empty">No local datasets uploaded yet.</p>
          )}

          {selectedDataset ? (
            <>
              <div className="review-block-label" style={{ marginTop: "1rem" }}>
                Columns
              </div>
              <div className="kv">
                <label htmlFor="target-column">Target / ground-truth column</label>
                <select
                  id="target-column"
                  value={targetColumn}
                  onChange={(e) => setTargetColumn(e.target.value)}
                >
                  <option value="">Select a column…</option>
                  {selectedDataset.columns.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <label htmlFor="text-column">Text / model input column</label>
                <select
                  id="text-column"
                  value={textColumn}
                  onChange={(e) => setTextColumn(e.target.value)}
                >
                  <option value="">Select a column…</option>
                  {selectedDataset.columns.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <label htmlFor="group-column">Group attribute</label>
                <select
                  id="group-column"
                  value={groupColumn}
                  onChange={(e) => setGroupColumn(e.target.value)}
                >
                  <option value="">Select a column…</option>
                  {selectedDataset.columns.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <p className="field-hint">
                Select the column you want TrustLens to use for comparing model performance
                across groups.
              </p>

              {groupColumn ? (
                <>
                  <div className="review-block-label" style={{ marginTop: "1rem" }}>
                    Detected groups
                  </div>
                  {discoveringGroups ? <Spinner label="Reading observed values…" /> : null}
                  {groupDiscovery ? (
                    <div className="contract-card-grid">
                      {groupDiscovery.observed_groups
                        .filter((g) => g.value !== MISSING_GROUP_VALUE)
                        .map((g) => (
                          <label
                            key={g.value}
                            className={`contract-card${includedGroups.has(g.value) ? " selected" : ""}`}
                            style={{ cursor: "pointer" }}
                          >
                            <input
                              type="checkbox"
                              checked={includedGroups.has(g.value)}
                              onChange={() => toggleIncludedGroup(g.value)}
                              style={{ marginRight: "0.4rem" }}
                            />
                            <span className="contract-card-title">{g.value}</span>
                            <span className="contract-card-sub mono">
                              {g.count.toLocaleString()} rows
                            </span>
                          </label>
                        ))}
                      {groupDiscovery.missing_count > 0 ? (
                        <div className="contract-card static">
                          <span className="contract-card-title">Missing</span>
                          <span className="contract-card-sub mono">
                            {groupDiscovery.missing_count.toLocaleString()} rows
                          </span>
                          <span className="contract-card-sub">
                            Excluded — missing/null values are never compared as a group.
                          </span>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {includedGroups.size < 2 ? (
                    <p className="field-hint">Select at least 2 groups to compare.</p>
                  ) : null}
                </>
              ) : null}
            </>
          ) : null}

          <div className="btn-row" style={{ marginTop: "1.1rem" }}>
            <button
              type="button"
              className="btn"
              disabled={
                !selectedDataset || !targetColumn || !groupColumn || !textColumn ||
                includedGroups.size < 2
              }
              onClick={() => {
                if (!selectedDataset) return;
                setChoice({
                  family: "fairness",
                  user_dataset_id: selectedDataset.id,
                  target_column: targetColumn,
                  group_column: groupColumn,
                  text_column: textColumn,
                  included_group_values: Array.from(includedGroups),
                  label: selectedDataset.filename,
                  sublabel: "User-defined local evaluation",
                });
                setStep("review");
              }}
            >
              Continue
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setStep("source")}>
              Back
            </button>
          </div>
        </div>
      ) : null}

      {step === "contract" && options && family && family !== "documentation" ? (
        <div className="card">
          <h2>Choose an approved contract</h2>
          <ContractCatalog
            options={{
              ...options,
              fairness: family === "fairness" ? options.fairness : [],
              robustness: family === "robustness" ? options.robustness : [],
            }}
            selectable
            selected={choice}
            onSelect={(c) => {
              setChoice(c);
              setStep("review");
            }}
          />
          {family === "fairness" && options.proxy_lr_available ? (
            <div className="contract-group">
              <div className="contract-group-title">Admin-only</div>
              <button
                type="button"
                className={`contract-card${choice?.contract_kind === "proxy_lr" ? " selected" : ""}`}
                onClick={() => {
                  setChoice({
                    family: "fairness",
                    contract_kind: "proxy_lr",
                    label: "Adult (proxy)",
                    sublabel: "Proxy evaluation",
                  });
                  setStep("review");
                }}
              >
                <span className="contract-card-title">Adult income (tabular proxy)</span>
                <span className="contract-card-sub">
                  Predictions come from a separate model on tabular features — not the imported
                  model.
                </span>
                <span className="contract-card-chips">
                  <span className="chip">Proxy evaluation</span>
                </span>
              </button>
            </div>
          ) : null}
          <div className="btn-row" style={{ marginTop: "1rem" }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setStep(family === "fairness" ? "source" : "family")}
            >
              Back
            </button>
          </div>
        </div>
      ) : null}

      {step === "review" && model && choice ? (
        <div className="card">
          <h2>Review before running</h2>
          <div className="review-summary">
            <div>
              <div className="review-block-label">Model</div>
              <div className="review-block-value">{model.hf_repo_id}</div>
              <div className="muted mono">Revision: {shortRevision(model.revision)}</div>
            </div>
            <div>
              <div className="review-block-label">Evaluation</div>
              <div className="review-block-value">
                {family === "documentation" ? "Documentation & governance" : choice.label}
              </div>
              <div className="muted">{choice.sublabel}</div>
            </div>
            <div>
              <div className="review-block-label">Execution</div>
              <div className="review-block-value">Local inference</div>
              <div className="muted">Runs on the TrustLens Local Engine — no upload.</div>
            </div>
          </div>

          {choice.user_dataset_id ? (
            <div className="review-summary" style={{ marginTop: "0.6rem" }}>
              <div>
                <div className="review-block-label">Target column</div>
                <div className="review-block-value mono">{choice.target_column}</div>
              </div>
              <div>
                <div className="review-block-label">Group attribute</div>
                <div className="review-block-value mono">{choice.group_column}</div>
              </div>
              <div>
                <div className="review-block-label">Groups</div>
                <div className="review-block-value">
                  {(choice.included_group_values ?? []).join(" · ")}
                </div>
              </div>
            </div>
          ) : null}

          <div className="review-block-label">Dimensions</div>
          <div className="dimension-outcome-list">
            {(Object.entries(outcomes) as [string, string][]).map(([dim, outcome]) => (
              <div key={dim} className="dimension-outcome-row">
                <span>{dim.charAt(0) + dim.slice(1).toLowerCase()}</span>
                <span className="muted">{outcome}</span>
              </div>
            ))}
          </div>

          <p className="field-hint" style={{ marginTop: "0.8rem" }}>
            Result is finalized automatically (no human review step) unless you choose
            otherwise later. FRIES is withheld by default until O/S/D synthesis is available.
          </p>

          <ErrorNotice error={error} />
          <div className="btn-row" style={{ marginTop: "1.1rem" }}>
            <button type="button" className="btn" disabled={submitting} onClick={() => void handleSubmit()}>
              {submitting ? "Starting…" : "Run evaluation"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() =>
                setStep(
                  family === "documentation"
                    ? "family"
                    : usingLocalDataset
                      ? "dataset-setup"
                      : "contract",
                )
              }
            >
              Back
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
