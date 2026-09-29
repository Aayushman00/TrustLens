import type { CSSProperties } from "react";
import type { FriesDimension } from "../../api/types";
import { DIMENSIONS } from "../dimensions";

const SHAPES = {
  circle: <circle cx="8" cy="8" r="6" />,
  square: <rect x="2.5" y="2.5" width="11" height="11" />,
  hexagon: <polygon points="8,1.5 13.6,4.75 13.6,11.25 8,14.5 2.4,11.25 2.4,4.75" />,
  diamond: <polygon points="8,1.5 14.5,8 8,14.5 1.5,8" />,
  triangle: <polygon points="8,2 14.5,13.5 1.5,13.5" />,
};

export function DimensionGlyph({ dimension, size = 16 }: { dimension: FriesDimension; size?: number }) {
  return (
    <svg className="tl-dim__glyph" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
      {SHAPES[DIMENSIONS[dimension].shape]}
    </svg>
  );
}

export function DimensionMark({ dimension, showLabel = true }: { dimension: FriesDimension; showLabel?: boolean }) {
  const meta = DIMENSIONS[dimension];
  const style = { "--tl-dim-c": `var(${meta.cssVar})` } as CSSProperties;
  return (
    <span
      className="tl-dim"
      style={style}
      {...(showLabel ? {} : { role: "img", "aria-label": meta.label })}
    >
      <DimensionGlyph dimension={dimension} />
      <span className="tl-dim__mono" aria-hidden={showLabel ? undefined : true}>{meta.monogram}</span>
      {showLabel && <span className="tl-dim__label">{meta.label}</span>}
    </span>
  );
}
