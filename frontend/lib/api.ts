/**
 * Cliente HTTP minimalista para la API FastAPI.
 *
 * Lee `NEXT_PUBLIC_API_URL` y `NEXT_PUBLIC_API_KEY` de env vars al construir.
 * Devuelve siempre `Promise<T>` con el body parseado, o lanza ApiError con
 * shape consistente (`{error, code, details, status}`).
 */

export interface ApiErrorBody {
  error: string;
  code: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error);
    this.status = status;
    this.code = body.code;
    this.details = body.details ?? {};
  }
}

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

function authHeaders(): Record<string, string> {
  return API_KEY ? { "X-API-Key": API_KEY } : {};
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  init: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...authHeaders(),
    ...((init.headers as Record<string, string>) ?? {}),
  };

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: payload,
    // Mandar cookies en cross-origin (auth login + me). El backend tiene
    // CORS con `allow_credentials=True`.
    credentials: "include",
    ...init,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    throw new ApiError(res.status, data ?? { error: res.statusText, code: "http_error" });
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>("GET", path, undefined, init),
  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>("POST", path, body, init),
  put: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>("PUT", path, body, init),
  del: <T>(path: string, init?: RequestInit) => request<T>("DELETE", path, undefined, init),
  baseUrl: BASE_URL,
  wsUrl: (process.env.NEXT_PUBLIC_WS_URL ?? BASE_URL.replace(/^http/, "ws")).replace(/\/$/, ""),
};
