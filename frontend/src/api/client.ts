/** fetch wrapper: base URL, Bearer header, error envelope, single-flight refresh.
 *
 * Tokens live in localStorage (MVP choice — see README for the XSS tradeoff).
 * On a 401 the client tries POST /v1/auth/refresh once (rotated pair, shared
 * across concurrent callers), retries the request, and otherwise signals
 * auth failure so the AuthContext can log out.
 */

import type { ApiErrorBody, TokenResponse } from "./types";

export const API_BASE: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const ACCESS_KEY = "trustlens.access_token";
const REFRESH_KEY = "trustlens.refresh_token";

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

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function storeTokens(tokens: TokenResponse): void {
  localStorage.setItem(ACCESS_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

let onAuthFailure: (() => void) | null = null;

/** AuthContext registers its logout handler here (called when refresh fails). */
export function setAuthFailureHandler(handler: (() => void) | null): void {
  onAuthFailure = handler;
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  /** Skip the Authorization header (login/refresh). */
  anonymous?: boolean;
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

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refreshToken = localStorage.getItem(REFRESH_KEY);
      if (!refreshToken) return false;
      try {
        const response = await fetch(`${API_BASE}/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!response.ok) return false;
        storeTokens((await response.json()) as TokenResponse);
        return true;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, anonymous = false } = options;

  const doFetch = () => {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (!anonymous) {
      const token = getAccessToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    return fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  };

  let response = await doFetch();

  if (response.status === 401 && !anonymous) {
    if (await tryRefresh()) {
      response = await doFetch();
    }
    if (response.status === 401) {
      clearTokens();
      onAuthFailure?.();
    }
  }

  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}
