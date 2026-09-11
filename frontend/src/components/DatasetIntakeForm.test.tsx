import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { apiFetch, ApiError } from "../api/client";
import DatasetIntakeForm from "./DatasetIntakeForm";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, apiFetch: vi.fn() };
});

describe("DatasetIntakeForm", () => {
  it("fetches dataset and reports content to parent", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      id: "content-1",
      content_hash: "abc",
      byte_size: 100,
      format: "csv",
      row_count: 3,
      columns: [{ name: "text", inferred_type: "string" }],
      created_at: "2026-01-01T00:00:00Z",
    });
    const onReady = vi.fn();
    render(<DatasetIntakeForm onContentReady={onReady} />);

    fireEvent.change(screen.getByLabelText(/dataset url/i), { target: { value: "https://example.com/d.csv" } });
    fireEvent.click(screen.getByRole("button", { name: /fetch/i }));

    await waitFor(() => expect(onReady).toHaveBeenCalledWith(expect.objectContaining({ id: "content-1" })));
    expect(screen.getByText(/3 rows/i)).toBeInTheDocument();
    expect(screen.getByText(/text/)).toBeInTheDocument();
    expect(screen.getByText(/string/)).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledWith("/v1/dataset-fetches", {
      method: "POST",
      body: { source_url: "https://example.com/d.csv" },
    });
  });

  it("disables the fetch button while a URL has not been entered", () => {
    render(<DatasetIntakeForm onContentReady={vi.fn()} />);
    expect(screen.getByRole("button", { name: /fetch/i })).toBeDisabled();
  });

  it("shows a loading state while the fetch is in flight", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    vi.mocked(apiFetch).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );
    render(<DatasetIntakeForm onContentReady={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/dataset url/i), { target: { value: "https://example.com/d.csv" } });
    fireEvent.click(screen.getByRole("button", { name: /fetch/i }));

    expect(await screen.findByRole("button", { name: /fetching/i })).toBeDisabled();

    resolveFetch({
      id: "content-1",
      content_hash: "abc",
      byte_size: 10,
      format: "csv",
      row_count: 1,
      columns: [],
      created_at: "2026-01-01T00:00:00Z",
    });

    await waitFor(() => expect(screen.getByRole("button", { name: /fetch dataset/i })).not.toBeDisabled());
  });

  it("surfaces the backend's SSRF-rejection message rather than a generic failure", async () => {
    vi.mocked(apiFetch).mockRejectedValueOnce(
      new ApiError(422, {
        code: "VALIDATION_ERROR",
        message: "could not fetch dataset URL: resolved address is private/loopback/link-local/reserved: 127.0.0.1",
        details: {},
      }),
    );
    render(<DatasetIntakeForm onContentReady={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/dataset url/i), { target: { value: "http://169.254.169.254/secret" } });
    fireEvent.click(screen.getByRole("button", { name: /fetch/i }));

    expect(await screen.findByText(/private\/loopback/i)).toBeInTheDocument();
    // Not stuck in the loading state after failure.
    expect(screen.getByRole("button", { name: /fetch dataset/i })).not.toBeDisabled();
  });

  it("clears a previously-shown dataset preview when a replacement fetch fails", async () => {
    // First attempt succeeds and shows a preview...
    vi.mocked(apiFetch).mockResolvedValueOnce({
      id: "content-1",
      content_hash: "abc",
      byte_size: 100,
      format: "csv",
      row_count: 3,
      columns: [{ name: "good_column", inferred_type: "string" }],
      created_at: "2026-01-01T00:00:00Z",
    });
    const onReady = vi.fn();
    const onFetchStart = vi.fn();
    render(<DatasetIntakeForm onContentReady={onReady} onFetchStart={onFetchStart} />);

    fireEvent.change(screen.getByLabelText(/dataset url/i), { target: { value: "https://example.com/good.csv" } });
    fireEvent.click(screen.getByRole("button", { name: /fetch/i }));
    await waitFor(() => expect(screen.getByText(/good_column/)).toBeInTheDocument());

    // ...then a replacement URL that fails (e.g. resolves to HTML) must not
    // leave the previous dataset's preview/columns visibly attached.
    vi.mocked(apiFetch).mockRejectedValueOnce(
      new ApiError(422, {
        code: "VALIDATION_ERROR",
        message:
          "downloaded file is not a valid CSV: this URL points to a webpage (HTML), not a raw CSV dataset",
        details: {},
      }),
    );
    fireEvent.change(screen.getByLabelText(/dataset url/i), { target: { value: "https://example.com/page.html" } });
    fireEvent.click(screen.getByRole("button", { name: /fetch/i }));

    expect(await screen.findByText(/not a raw CSV dataset/i)).toBeInTheDocument();
    expect(screen.queryByText(/good_column/)).not.toBeInTheDocument();
    // The parent must be told to drop its own stale dataset/label-mapping
    // state the instant the replacement attempt begins, not only on success.
    expect(onFetchStart).toHaveBeenCalledTimes(2);
  });
});
