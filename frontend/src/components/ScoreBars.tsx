import { FRIES_DIMENSIONS } from "../api/types";

/** Labeled 0-10 bars for final_score.dimension_scores (stable F/R/I/E/S order). */
export default function ScoreBars({ scores }: { scores: Record<string, number> }) {
  const ordered = [
    ...FRIES_DIMENSIONS.filter((d) => d in scores),
    ...Object.keys(scores).filter((k) => !(FRIES_DIMENSIONS as string[]).includes(k)),
  ];
  return (
    <div className="score-bars">
      {ordered.map((dimension) => {
        const value = scores[dimension];
        return (
          <div className="score-bar-row" key={dimension}>
            <span className="score-bar-label">{dimension.toLowerCase()}</span>
            <span className="score-bar-track">
              <span
                className="score-bar-fill"
                style={{ width: `${Math.max(0, Math.min(10, value)) * 10}%` }}
              />
            </span>
            <span className="score-bar-value">{value.toFixed(2)}</span>
          </div>
        );
      })}
    </div>
  );
}
