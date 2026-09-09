export default function DocumentationPage() {
  return (
    <>
      <div className="page-header">
        <div>
          <h1>Documentation</h1>
          <p className="muted">What TrustLens measures today, and what it does not.</p>
        </div>
      </div>

      <div className="card">
        <h2>Fairness</h2>
        <p>
          Model-faithful evaluation runs your imported model locally against an approved
          pairing (currently HateXplain). Group-disparity metrics — demographic parity
          difference, equalized-odds difference, worst-group accuracy gap with a 95%
          bootstrap confidence interval — are computed from real predictions. A
          <strong> proxy evaluation</strong> (Adult income dataset, admin-only) uses a
          separate tabular model and is never presented as model-faithful.
        </p>
      </div>

      <div className="card">
        <h2>Robustness</h2>
        <p>
          Model-faithful evaluation perturbs input text with a discrete character-swap
          attack and compares clean vs. robust accuracy, only for models with an approved
          compatibility pin (currently AG News and SST-2 BERT checkpoints). No other
          dataset is substituted automatically — an unmatched model shows{" "}
          <strong>Not applicable</strong>, never a score of zero.
        </p>
      </div>

      <div className="card">
        <h2>Integrity, Explainability, Safety</h2>
        <p>
          These three dimensions are documentation- and provenance-oriented, not behavioral
          testing. Integrity checks revision identity, hash verification where available,
          and license disclosure. Explainability checks documentation completeness against
          recognized model-card sections —{" "}
          <strong>documentation coverage is not equivalent to explanation quality</strong>.
          Safety checks safety-governance disclosures in the model card. None of the three
          run red-teaming, refusal benchmarks, SHAP/LIME attribution, or produce a
          safe/unsafe classification.
        </p>
      </div>

      <div className="card">
        <h2>FRIES and O/S/D</h2>
        <p>
          FRIES is a synthesis of Occurrence/Severity/Detection (O/S/D) across all five
          dimensions. In the default deterministic engine, O and D are not currently
          approved for automatic generation, so FRIES is <strong>withheld</strong> rather
          than fabricated. Withheld is not a failing score — it means no synthesized number
          exists yet for this run.
        </p>
      </div>

      <div className="card">
        <h2>Local-first execution</h2>
        <p>
          TrustLens runs entirely on this machine: model weights are downloaded once and
          stored locally, inference happens locally, and evidence is stored on the local
          evidence store. Nothing is uploaded to a shared or hosted TrustLens service as
          part of running an evaluation.
        </p>
      </div>
    </>
  );
}
