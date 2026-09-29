import type { FriesDimension } from "../api/types";

export interface DimensionMeta {
  key: FriesDimension;
  label: string;
  monogram: string;
  shape: "circle" | "square" | "hexagon" | "diamond" | "triangle";
  cssVar: string;
}

/** Identity only — a hue says WHICH dimension, never how good. */
export const DIMENSIONS: Record<FriesDimension, DimensionMeta> = {
  FAIRNESS: { key: "FAIRNESS", label: "Fairness", monogram: "F", shape: "circle", cssVar: "--tl-dim-f" },
  ROBUSTNESS: { key: "ROBUSTNESS", label: "Robustness", monogram: "R", shape: "square", cssVar: "--tl-dim-r" },
  INTEGRITY: { key: "INTEGRITY", label: "Integrity", monogram: "I", shape: "hexagon", cssVar: "--tl-dim-i" },
  EXPLAINABILITY: { key: "EXPLAINABILITY", label: "Explainability", monogram: "E", shape: "diamond", cssVar: "--tl-dim-e" },
  SAFETY: { key: "SAFETY", label: "Safety", monogram: "S", shape: "triangle", cssVar: "--tl-dim-s" },
};
