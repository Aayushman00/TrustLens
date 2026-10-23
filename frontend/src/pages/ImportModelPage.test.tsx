import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { ApiError, apiFetch } from "../api/client";
import ImportModelPage from "./ImportModelPage";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, apiFetch: vi.fn() };
});

const model = (revision: string | null) => ({
  id: 7, hf_repo_id: "org/m", model_metadata: {}, checksum: null, revision,
  created_at: "2026-01-01T00:00:00Z", updated_at: null,
});
const renderPage = () => render(<MemoryRouter><ImportModelPage /></MemoryRouter>);

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
});

test("submit stays disabled until a reference is entered; labels exclude the hint text", async () => {
  renderPage();
  expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
  const ref = screen.getByLabelText(/^Repo ID or URL/);
  expect(ref).toHaveAccessibleDescription(/Example: distilbert/);
  await userEvent.type(ref, "org/m");
  expect(screen.getByRole("button", { name: "Import" })).toBeEnabled();
});

test("a bare repo id posts repo_id; an https URL posts url; revision is only sent when given", async () => {
  vi.mocked(apiFetch).mockResolvedValue(model("abc"));
  renderPage();
  await userEvent.type(screen.getByLabelText(/^Repo ID or URL/), " org/m ");
  await userEvent.click(screen.getByRole("button", { name: "Import" }));
  await screen.findByRole("heading", { name: "Imported org/m" });
  expect(vi.mocked(apiFetch).mock.calls[0]).toEqual([
    "/v1/models/import-hf", { method: "POST", body: { repo_id: "org/m" } },
  ]);

  await userEvent.clear(screen.getByLabelText(/^Repo ID or URL/));
  await userEvent.type(screen.getByLabelText(/^Repo ID or URL/), "https://huggingface.co/org/m");
  await userEvent.type(screen.getByLabelText(/^Revision/), "v1");
  await userEvent.click(screen.getByRole("button", { name: "Import" }));
  await screen.findByRole("heading", { name: "Imported org/m" });
  expect(vi.mocked(apiFetch).mock.calls[1][1]).toEqual({
    method: "POST", body: { url: "https://huggingface.co/org/m", revision: "v1" },
  });
});

test("success moves focus to the result and links to the model", async () => {
  vi.mocked(apiFetch).mockResolvedValue(model("abcdef123456"));
  renderPage();
  await userEvent.type(screen.getByLabelText(/^Repo ID or URL/), "org/m");
  await userEvent.click(screen.getByRole("button", { name: "Import" }));
  const heading = await screen.findByRole("heading", { name: "Imported org/m" });
  expect(heading).toHaveFocus();
  expect(screen.getByRole("link", { name: /start an evaluation/ })).toHaveAttribute("href", "/models/7");
  expect(screen.queryByText(/No revision was pinned/)).not.toBeInTheDocument();
});

test("an unpinned result warns and does not promise an evaluation", async () => {
  vi.mocked(apiFetch).mockResolvedValue(model(null));
  renderPage();
  await userEvent.type(screen.getByLabelText(/^Repo ID or URL/), "org/m");
  await userEvent.click(screen.getByRole("button", { name: "Import" }));
  expect(await screen.findByText(/No revision was pinned/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open model" })).toHaveAttribute("href", "/models/7");
  expect(screen.queryByRole("link", { name: /start an evaluation/ })).not.toBeInTheDocument();
});

test("an API error is shown inside an alert region and keeps the form usable", async () => {
  vi.mocked(apiFetch).mockRejectedValue(new ApiError(422, { code: "INVALID_MODEL_REF", message: "Bad ref", details: {} }));
  renderPage();
  await userEvent.type(screen.getByLabelText(/^Repo ID or URL/), "nope");
  await userEvent.click(screen.getByRole("button", { name: "Import" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("INVALID_MODEL_REF: Bad ref");
  expect(screen.getByRole("button", { name: "Import" })).toBeEnabled();
  expect(screen.queryByRole("heading", { name: /Imported/ })).not.toBeInTheDocument();
});
