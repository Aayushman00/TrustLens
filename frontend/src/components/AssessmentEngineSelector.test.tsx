/** frontend/src/components/AssessmentEngineSelector.test.tsx */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AssessmentEngineSelector from "./AssessmentEngineSelector";

describe("AssessmentEngineSelector", () => {
  it("renders three options with deterministic checked by default", () => {
    render(<AssessmentEngineSelector value="deterministic" onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: /deterministic/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /legacy heuristic/i })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /llm-assisted/i })).not.toBeChecked();
  });

  it("calls onChange with legacy_heuristic when that option is picked", () => {
    const onChange = vi.fn();
    render(<AssessmentEngineSelector value="deterministic" onChange={onChange} />);
    fireEvent.click(screen.getByRole("radio", { name: /legacy heuristic/i }));
    expect(onChange).toHaveBeenCalledWith("legacy_heuristic");
  });

  it("calls onChange with llm_v1 when that option is picked", () => {
    const onChange = vi.fn();
    render(<AssessmentEngineSelector value="deterministic" onChange={onChange} />);
    fireEvent.click(screen.getByRole("radio", { name: /llm-assisted/i }));
    expect(onChange).toHaveBeenCalledWith("llm_v1");
  });

  it("reflects legacy_heuristic as the checked value when passed", () => {
    render(<AssessmentEngineSelector value="legacy_heuristic" onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: /legacy heuristic/i })).toBeChecked();
  });
});
