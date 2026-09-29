import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { HashBadge, shortHash } from "./HashBadge";

const FULL = "sha256:86ad1cd39099df1de8ddc73c2af90c53a60de07e9cff1d081dc782922b5ca149";

function mockClipboard(writeText: (t: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

test("shortHash keeps first 8 and last 4 of the digest", () => {
  expect(shortHash(FULL)).toBe("86ad1cd3…a149");
  expect(shortHash("local")).toBe("local");
});

test("null hash says not recorded and offers no copy", () => {
  render(<HashBadge hash={null} />);
  expect(screen.getByText("— not recorded")).toBeInTheDocument();
  expect(screen.queryByRole("button")).toBeNull();
});

test("full hash is exposed to assistive tech", () => {
  render(<HashBadge hash={FULL} label="evidence hash" />);
  // aria-label on <code> is ignored by screen readers; the full hash must be real (sr-only) text
  expect(screen.getByText(`evidence hash ${FULL}`)).toHaveClass("tl-sr-only");
});

test("copy writes the full hash and confirms", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  mockClipboard(writeText);
  render(<HashBadge hash={FULL} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy hash" }));
  expect(await screen.findByText("Copied")).toBeInTheDocument();
  expect(writeText).toHaveBeenCalledWith(FULL);
});

test("clipboard failure is visible, not silent", async () => {
  mockClipboard(vi.fn().mockRejectedValue(new Error("denied")));
  render(<HashBadge hash={FULL} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy hash" }));
  expect(await screen.findByText("Copy failed")).toBeInTheDocument();
});

test("missing clipboard API is visible, not silent", async () => {
  Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
  render(<HashBadge hash={FULL} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy hash" }));
  expect(await screen.findByText("Copy failed")).toBeInTheDocument();
});
