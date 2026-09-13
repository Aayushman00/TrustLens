export type AssessmentEngine = "deterministic" | "legacy_heuristic" | "llm_v1";

const OPTIONS: { value: AssessmentEngine; label: string; hint: string }[] = [
  {
    value: "deterministic",
    label: "Deterministic (default)",
    hint: "Conservative — abstains on every O/S/D; you fill in all values during review.",
  },
  {
    value: "legacy_heuristic",
    label: "Legacy heuristic scoring",
    hint: "Proposes O/S/D bands from probe metrics (coverage ratios, pass rates) for you to review.",
  },
  {
    value: "llm_v1",
    label: "LLM-assisted scoring",
    hint: "Like legacy heuristic, but Integrity/Explainability/Safety are judged by an LLM reading the model card instead of a coverage ratio. Falls back to the heuristic band if the LLM call fails.",
  },
];

export default function AssessmentEngineSelector({
  value,
  onChange,
}: {
  value: AssessmentEngine;
  onChange: (value: AssessmentEngine) => void;
}) {
  return (
    <div className="advanced-setting">
      <div className="advanced-setting-eyebrow">Advanced</div>
      {OPTIONS.map((option) => (
        <label className="radio-row" key={option.value} htmlFor={`assessment-engine-${option.value}`}>
          <input
            id={`assessment-engine-${option.value}`}
            type="radio"
            name="assessment-engine"
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            aria-label={option.label}
          />
          <span>
            {option.label}
            <span className="field-hint" style={{ display: "block" }}>
              {option.hint}
            </span>
          </span>
        </label>
      ))}
    </div>
  );
}
