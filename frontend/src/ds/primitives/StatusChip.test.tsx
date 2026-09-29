import { render, screen } from "@testing-library/react";
import { CHIP_STATUSES, StatusChip } from "./StatusChip";

test.each(Object.entries(CHIP_STATUSES))("%s shows its word, not just colour", (status, meta) => {
  render(<StatusChip status={status} />);
  expect(screen.getByText(meta.word)).toBeInTheDocument();
});

test("unknown backend status renders verbatim", () => {
  render(<StatusChip status="QUARANTINED" />);
  expect(screen.getByText("QUARANTINED")).toBeInTheDocument();
});
