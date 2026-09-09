/** fetch wrapper: base URL, error envelope.
 *
 * TrustLens is single-user and local-only — the backend resolves every
 * request to the local instance identity, so no auth token handling here.
 */

import type { ApiErrorBody } from "./types";

export const API_BASE: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = {
    code: "UNKNOWN",
    message: `Request failed with status ${response.status}`,
    details: {},
  };
  try {
    const parsed = (await response.json()) as Partial<ApiErrorBody>;
    if (parsed && typeof parsed.message === "string") {
      body = {
        code: parsed.code ?? "UNKNOWN",
        message: parsed.message,
        details: parsed.details ?? {},
      };
    }
  } catch {
    // non-JSON error body — keep the fallback
  }
  return new ApiError(response.status, body);
}

export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Multipart upload (local dataset files) — apiFetch is JSON-only, this is the
 * one exception. No manual Content-Type: the browser sets the multipart
 * boundary. Files stay on this TrustLens instance's local stack — this is
 * not a call to a hosted/cloud service. */
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}
