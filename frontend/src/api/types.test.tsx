import { describe, expect, it } from "vitest";
import { ACTIVE_STATUSES } from "./types";

describe("ACTIVE_STATUSES", () => {
  it("stops polling once an evaluation is terminal or waiting on a human", () => {
    // FAILED must never be treated as still pending — the detail page polls
    // only while the status is in this list.
    for (const s of ["FAILED", "FINALIZED", "AWAITING_REVIEW"] as const) {
      expect(ACTIVE_STATUSES).not.toContain(s);
    }
    expect(ACTIVE_STATUSES).toEqual(["PENDING", "RUNNING", "PROBES_COMPLETED", "AGENT_COMPLETED"]);
  });
});
