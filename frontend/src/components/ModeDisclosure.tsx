import type { ModeDisclosure } from "../api/types";

export function modeLabel(mode: "AI_ASSISTED" | "AI_AUTONOMOUS"): string {
  return mode === "AI_ASSISTED" ? "AI-Assisted" : "AI-Autonomous";
}

/** Mandatory mode/provenance disclosure — reused on detail, review and report pages. */
export default function ModeDisclosureBanner({
  disclosure,
}: {
  disclosure: ModeDisclosure;
}) {
  const tone = disclosure.human_reviewed ? "notice-reviewed" : "notice-unreviewed";
  return (
    <div className={`notice ${tone}`}>
      <div className="notice-chips">
        <span className="badge badge-mode">{modeLabel(disclosure.evaluation_mode)}</span>
        <span className={`badge ${disclosure.human_reviewed ? "badge-yes" : "badge-no"}`}>
          {disclosure.human_reviewed ? "Human-reviewed" : "Not human-reviewed"}
        </span>
      </div>
      <p className="notice-disclaimer">{disclosure.disclaimer}</p>
      <p className="notice-fineprint">Methodology: {disclosure.methodology_status}</p>
    </div>
  );
}
