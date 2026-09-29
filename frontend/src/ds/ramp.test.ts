import { expect, test } from "vitest";
import { rampColor, rampVar, RAMP_ANCHORS } from "./ramp";

test("anchors map to their css variable", () => {
  expect(RAMP_ANCHORS).toEqual([0, 3, 5, 7, 8.5, 10]);
  expect(rampVar(8.5)).toBe("var(--tl-ramp-8_5)");
  expect(rampColor(0)).toBe("var(--tl-ramp-0)");
  expect(rampColor(10)).toBe("var(--tl-ramp-10)");
});

test("between anchors mixes in oklch", () => {
  expect(rampColor(4)).toBe("color-mix(in oklch, var(--tl-ramp-5) 50.0%, var(--tl-ramp-3))");
});

test("out of range clamps", () => {
  expect(rampColor(-1)).toBe("var(--tl-ramp-0)");
  expect(rampColor(10.4)).toBe("var(--tl-ramp-10)");
});

test("non-finite throws (callers must treat as unscored)", () => {
  expect(() => rampColor(Number.NaN)).toThrow(RangeError);
});
