import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { vi } from "vitest";
import { TracePanel, type TraceChain } from "./TracePanel";

const CHAIN: TraceChain = {
  title: "Fairness 6.60",
  levels: [
    { layer: "score", heading: "Aspect score", value: "6.6039" },
    { layer: "assessment", heading: "Risk: group disparity", rows: [["O", "6"], ["S", "6"], ["D", "8"], ["T = ∛(O·S·D)", "6.6039"]] },
    { layer: "evidence", heading: "Fairness probe", rows: [["demographic_parity_difference", "0.368"]], raw: { demographic_parity_difference: 0.36831 } },
  ],
};

test("renders nothing when closed", () => {
  const { container } = render(<TracePanel chain={null} onClose={() => {}} />);
  expect(container).toBeEmptyDOMElement();
});

test("focuses its heading on open and lists layers in chain order", () => {
  render(<TracePanel chain={CHAIN} onClose={() => {}} />);
  expect(screen.getByRole("heading", { name: "Fairness 6.60" })).toHaveFocus();
  const layers = screen.getAllByText(/^(FRIES score|Risk assessment|Evidence)$/).map((n) => n.textContent);
  expect(layers).toEqual(["FRIES score", "Risk assessment", "Evidence"]);
});

test("raw JSON is two clicks away (collapsed by default)", () => {
  render(<TracePanel chain={CHAIN} onClose={() => {}} />);
  expect(screen.getByText("Raw JSON").closest("details")).not.toHaveAttribute("open");
});

test("Escape closes", () => {
  const onClose = vi.fn();
  render(<TracePanel chain={CHAIN} onClose={onClose} />);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalled();
});

test("focus returns to the trigger after closing", () => {
  function Harness() {
    const [chain, setChain] = useState<TraceChain | null>(null);
    return (
      <>
        <button onClick={() => setChain(CHAIN)}>6.60</button>
        <TracePanel chain={chain} onClose={() => setChain(null)} />
      </>
    );
  }
  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "6.60" });
  trigger.focus();
  fireEvent.click(trigger);
  expect(screen.getByRole("heading", { name: "Fairness 6.60" })).toHaveFocus();
  fireEvent.click(screen.getByRole("button", { name: "Close trace" }));
  expect(trigger).toHaveFocus();
});

test("a parent re-render with an equal-content chain does not steal focus", () => {
  function Poller() {
    const [tick, setTick] = useState(0);
    // new object identity every render, as a polling page would produce
    const chain: TraceChain = { ...CHAIN, levels: [...CHAIN.levels] };
    return (
      <>
        <button onClick={() => setTick(tick + 1)}>poll</button>
        <TracePanel chain={chain} onClose={() => {}} />
      </>
    );
  }
  render(<Poller />);
  const summary = screen.getByText("Raw JSON");
  summary.setAttribute("tabindex", "0");
  summary.focus();
  fireEvent.click(screen.getByRole("button", { name: "poll" }));
  expect(summary).toHaveFocus();
});
