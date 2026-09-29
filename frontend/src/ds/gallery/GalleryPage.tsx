import { useState, type ReactNode } from "react";
import "../fonts";
import "../tokens.css";
import "../ds.css";
import { FRIES_DIMENSIONS } from "../../api/types";
import { RAMP_ANCHORS, rampVar } from "../ramp";
import { riskT } from "../scoring";
import { Card, Slip } from "../primitives/Card";
import { Dial } from "../primitives/Dial";
import { DimensionMark } from "../primitives/DimensionMark";
import { EvidenceChip, toEvidenceRef } from "../primitives/EvidenceChip";
import { Gauge, readCI } from "../primitives/Gauge";
import { HashBadge } from "../primitives/HashBadge";
import { Pentagon } from "../primitives/Pentagon";
import { ScoreRing } from "../primitives/ScoreRing";
import { Spine } from "../primitives/Spine";
import { CHIP_STATUSES, StatusChip } from "../primitives/StatusChip";
import { Timeline } from "../primitives/Timeline";
import { TracePanel, type TraceChain } from "../primitives/TracePanel";

// Specimen values copied from results/flawed_model_suite/eval_results_v2/variant6_compound.json.
const COMPOUND = { FAIRNESS: 6.6039, ROBUSTNESS: 9.0, INTEGRITY: 2.2894, EXPLAINABILITY: 1.2599, SAFETY: 1.2599 };
const FAIRNESS_OSD = { O: 6, S: 6, D: 8 };
const FAIRNESS_REF = toEvidenceRef({
  uri: "s3://trustlens/evidence/39efa7ad-95a2-4281-85f5-b5dbaa7c4a8c/c8b8f84a-ffce-4df8-b8b9-0a80f5976cf5.json",
  hash: "sha256:86ad1cd39099df1de8ddc73c2af90c53a60de07e9cff1d081dc782922b5ca149",
  created_at: "2026-09-15T00:05:29.311587Z",
  probe_name: "fairness",
  evidence_id: "c8b8f84a-ffce-4df8-b8b9-0a80f5976cf5",
  content_type: "application/json",
});
const DP_CI = readCI({ ci_lower: 0.326535, ci_upper: 0.412892, method: "bootstrap_percentile" });
// Event timestamps are illustrative (the source run stored no events).
const EVENTS = [
  { id: 1, event_type: "evaluation_created", created_at: "2026-09-15T00:04:50Z" },
  { id: 2, event_type: "evaluation_started", created_at: "2026-09-15T00:04:51Z" },
  { id: 3, event_type: "probes_completed", created_at: "2026-09-15T00:06:08Z", detail: { probe_count: 5 } },
  { id: 4, event_type: "agent_completed", created_at: "2026-09-15T00:06:12Z" },
  { id: 5, event_type: "evaluation_finalized", created_at: "2026-09-15T00:06:12Z" },
];
const SWATCHES = [
  "--tl-ink-0", "--tl-ink-1", "--tl-ink-2", "--tl-line-1", "--tl-line-2",
  "--tl-text-1", "--tl-text-2", "--tl-text-3", "--tl-uv", "--tl-fail",
];
const DEMO_VALUES = [COMPOUND.FAIRNESS, COMPOUND.EXPLAINABILITY, COMPOUND.ROBUSTNESS];
const T_FAIR = riskT(FAIRNESS_OSD.O, FAIRNESS_OSD.S, FAIRNESS_OSD.D);
const TRACE: TraceChain = {
  title: `Fairness ${T_FAIR.toFixed(2)}`,
  levels: [
    { layer: "score", heading: "Aspect score (mean of 1 risk)", value: COMPOUND.FAIRNESS.toFixed(4) },
    {
      layer: "assessment",
      heading: "Risk: outcome disparity across identity groups",
      rows: [["O", "6"], ["S", "6"], ["D", "8"], ["T = ∛(O·S·D)", T_FAIR.toFixed(4)]],
    },
    {
      layer: "evidence",
      heading: "Fairness probe · EVALUATED · n = 3000",
      rows: [["demographic_parity_difference", "0.368"], ["equalized_odds_difference", "0.167"], ["subgroup_f1_spread", "0.161"]],
      evidence: [FAIRNESS_REF],
      raw: { demographic_parity_difference: 0.36831, dp_ci: { ci_lower: 0.326535, ci_upper: 0.412892 } },
    },
  ],
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="tl-gallery__section">
      <h2 className="tl-gallery__h2">{title}</h2>
      {children}
    </section>
  );
}

export default function GalleryPage() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [reduce, setReduce] = useState(false);
  const [trace, setTrace] = useState<TraceChain | null>(null);
  const [demo, setDemo] = useState(0);

  return (
    <div className="tl tl-gallery" data-theme={theme} data-motion={reduce ? "reduce" : undefined}>
      <header className="tl-gallery__head">
        <div>
          <h1 className="tl-display tl-gallery__h1">TrustLens design system</h1>
          <p className="tl-gallery__note">Specimen data — not an audit. Values from variant6_compound; event times illustrative.</p>
        </div>
        <div className="tl-gallery__toggles">
          <button type="button" aria-pressed={theme === "light"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>Light theme</button>
          <button type="button" aria-pressed={reduce} onClick={() => setReduce(!reduce)}>Reduce motion</button>
        </div>
      </header>

      <Section title="Colour">
        <div className="tl-gallery__swatches">
          {SWATCHES.map((v) => (
            <figure key={v} className="tl-gallery__swatch"><span style={{ background: `var(${v})` }} /><figcaption><code>{v}</code></figcaption></figure>
          ))}
        </div>
        <p className="tl-gallery__caption">Trust ramp (score layer only) — anchors 0 → 10</p>
        <div className="tl-gallery__ramp">
          {RAMP_ANCHORS.map((a) => <span key={a} style={{ background: rampVar(a) }}><code>{a}</code></span>)}
        </div>
      </Section>

      <Section title="Type">
        <p className="tl-display tl-gallery__spec-display">4.08</p>
        <p>IBM Plex Sans — Demographic parity difference across identity groups</p>
        <p><code>ev_c8b8f84a  application/json  sha256:86ad1cd3…a149</code></p>
      </Section>

      <Section title="Motion">
        <p className="tl-gallery__caption">Moves only on a real change (here: your click). Reduced motion shows the end state instantly.</p>
        <ScoreRing value={DEMO_VALUES[demo]} label="Demo aspect" size="lg" />
        <button type="button" onClick={() => setDemo((demo + 1) % DEMO_VALUES.length)}>Change value</button>
      </Section>

      <Section title="Materials">
        <div className="tl-gallery__row">
          <Card title="Card (chrome)">Structural surface.</Card>
          <Slip label="Slip (evidence)">demographic_parity_difference = 0.36831</Slip>
        </div>
      </Section>

      <Section title="Status">
        <div className="tl-gallery__row">{Object.keys(CHIP_STATUSES).map((s) => <StatusChip key={s} status={s} />)}</div>
      </Section>

      <Section title="Dimensions">
        <div className="tl-gallery__row">{FRIES_DIMENSIONS.map((d) => <DimensionMark key={d} dimension={d} />)}</div>
      </Section>

      <Section title="Evidence">
        <div className="tl-gallery__col">
          <HashBadge hash={FAIRNESS_REF.hash} label="evidence hash" />
          <HashBadge hash={null} label="TrustLens version" />
          <EvidenceChip evidence={FAIRNESS_REF} onTrace={() => setTrace(TRACE)} />
        </div>
      </Section>

      <Section title="Gauge">
        <Gauge label="Demographic parity difference" metricKey="demographic_parity_difference" value={0.36831} ci={DP_CI} />
        <Gauge label="Equalized odds difference" metricKey="equalized_odds_difference" value={null} />
      </Section>

      <Section title="Dial">
        <div className="tl-gallery__row">
          <Dial letter="O" value={FAIRNESS_OSD.O} source="agent" />
          <Dial letter="S" value={FAIRNESS_OSD.S} source="agent" />
          <Dial letter="D" value={FAIRNESS_OSD.D} source="agent" />
          <Dial letter="D" value={null} />
        </div>
        <p className="tl-gallery__caption">T = ∛(O × S × D) = ∛(6 × 6 × 8) = {T_FAIR.toFixed(2)} · higher = safer (inverted FMEA)</p>
      </Section>

      <Section title="Score ring">
        <div className="tl-gallery__row">
          <button type="button" className="tl-gallery__trace" aria-label={`Trace Fairness ${T_FAIR.toFixed(2)}`} onClick={() => setTrace(TRACE)}>
            <ScoreRing value={COMPOUND.FAIRNESS} label="Fairness" />
          </button>
          <ScoreRing value={5.04} proposed label="Proposed" />
          <ScoreRing value={0} veto label="Vetoed" />
          <ScoreRing value={null} label="Unscored" />
        </div>
      </Section>

      <Section title="Pentagon">
        <div className="tl-gallery__row">
          <Pentagon scores={COMPOUND} title="Complete (compound flaw)" />
          <Pentagon scores={{ ...COMPOUND, SAFETY: null }} title="Safety missing" />
        </div>
        <p className="tl-gallery__caption">Traceable aggregation of risk assessments — not an absolute safety measure.</p>
      </Section>

      <Section title="Spine">
        <Spine stages={[
          { key: "draft", label: "Draft", state: "done", at: "2026-09-15T00:04:50Z" },
          { key: "dataset", label: "Dataset validated", state: "done", at: "2026-09-15T00:04:50Z" },
          { key: "probes", label: "Probes", state: "current" },
          { key: "osd", label: "O/S/D proposal", state: "pending" },
          { key: "review", label: "Human review", state: "not_required", note: "AI_AUTONOMOUS mode" },
          { key: "final", label: "Final score", state: "pending" },
          { key: "report", label: "Report", state: "pending" },
        ]} />
      </Section>

      <Section title="Timeline">
        <Timeline events={EVENTS} />
      </Section>

      <Section title="Trace panel">
        <button type="button" onClick={() => setTrace(TRACE)}>Open example trace</button>
      </Section>

      <TracePanel chain={trace} onClose={() => setTrace(null)} />
    </div>
  );
}
