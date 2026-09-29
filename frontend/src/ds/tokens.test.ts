import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/ds/tokens.css"), "utf8");

function block(selector: RegExp): Record<string, string> {
  const match = css.match(selector);
  if (!match) throw new Error(`token block not found: ${selector}`);
  const out: Record<string, string> = {};
  for (const [, key, value] of match[1].matchAll(/(--tl-[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    out[key] = value;
  }
  return out;
}

const dark = block(/\.tl\s*\{([^}]*)\}/);
const light = { ...dark, ...block(/\.tl\[data-theme="light"\]\s*\{([^}]*)\}/) };

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT = [
  "--tl-text-1", "--tl-text-2", "--tl-text-3", "--tl-uv", "--tl-fail",
  "--tl-dim-f", "--tl-dim-r", "--tl-dim-i", "--tl-dim-e", "--tl-dim-s",
];
const NON_TEXT = [
  "--tl-line-2", "--tl-ramp-0", "--tl-ramp-3", "--tl-ramp-5",
  "--tl-ramp-7", "--tl-ramp-8_5", "--tl-ramp-10",
];
const RAMP = NON_TEXT.slice(1);

for (const [name, theme] of [["dark", dark], ["light", light]] as const) {
  describe(`${name} theme contrast`, () => {
    for (const bg of ["--tl-ink-0", "--tl-ink-1"]) {
      test.each(TEXT)(`%s on ${bg} >= 4.5:1`, (fg) => {
        expect(ratio(theme[fg], theme[bg])).toBeGreaterThanOrEqual(4.5);
      });
      test.each(NON_TEXT)(`%s on ${bg} >= 3:1`, (fg) => {
        expect(ratio(theme[fg], theme[bg])).toBeGreaterThanOrEqual(3);
      });
    }
  });
}

test("dark ramp luminance strictly increases (trust glows)", () => {
  const l = RAMP.map((k) => luminance(dark[k]));
  l.slice(1).forEach((v, i) => expect(v).toBeGreaterThan(l[i]));
});

test("light ramp luminance strictly decreases (trust = deeper ink)", () => {
  const l = RAMP.map((k) => luminance(light[k]));
  l.slice(1).forEach((v, i) => expect(v).toBeLessThan(l[i]));
});
