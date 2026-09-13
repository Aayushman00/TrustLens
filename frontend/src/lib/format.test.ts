import assert from "node:assert/strict";
import { test } from "node:test";

import { fmtTimeSeconds, parseOsdInput } from "./format.ts";

test("empty string is null", () => {
  assert.equal(parseOsdInput(""), null);
  assert.equal(parseOsdInput("   "), null);
});

test("non-numeric is null", () => {
  assert.equal(parseOsdInput("abc"), null);
});

test("non-integer is null", () => {
  assert.equal(parseOsdInput("1.5"), null);
});

test("integer zero is valid", () => {
  assert.equal(parseOsdInput("0"), 0);
});

test("out of domain is null", () => {
  assert.equal(parseOsdInput("11"), null);
  assert.equal(parseOsdInput("-1"), null);
});

test("fmtTimeSeconds returns an em dash for null/undefined", () => {
  assert.equal(fmtTimeSeconds(null), "—");
  assert.equal(fmtTimeSeconds(undefined), "—");
});

test("fmtTimeSeconds returns the raw string for an unparseable date", () => {
  assert.equal(fmtTimeSeconds("not-a-date"), "not-a-date");
});

test("fmtTimeSeconds includes seconds in the rendered output", () => {
  const result = fmtTimeSeconds("2026-03-15T10:30:45Z");
  // Locale-independent: assert the seconds component is present as two
  // digits somewhere in the string, without pinning an exact locale format.
  assert.match(result, /\d{2}:\d{2}:\d{2}/);
});
