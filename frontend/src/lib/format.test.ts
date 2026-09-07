import assert from "node:assert/strict";
import { test } from "node:test";

import { parseOsdInput } from "./format.ts";

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
