import { describe, expect, it } from "vitest";
import { engineLabel } from "./ModeDisclosure";

describe("engineLabel", () => {
  it("names the LLM-assisted engine instead of calling it deterministic", () => {
    expect(engineLabel("llm_v1")).toBe("LLM-assisted");
  });
  it("keeps the other labels", () => {
    expect(engineLabel("legacy_heuristic")).toBe("legacy heuristic");
    expect(engineLabel("deterministic")).toBe("deterministic");
    expect(engineLabel(null)).toBe("deterministic");
  });
});
