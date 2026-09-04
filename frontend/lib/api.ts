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

/** Saca un mensaje legible de lo que sea que haya respondido el servidor.
 *
 *  Los errores nuestros vienen como `{error, code, details}`, pero no todos lo
 *  son: FastAPI contesta `{"detail": …}` cuando falla la validación, y Caddy
 *  devuelve HTML si la API está reiniciando. Antes se leía `body.error` a
 *  secas, así que en esos dos casos el aviso salía VACÍO — un recuadro rojo
 *  sin una palabra, que es lo peor que puede pasar cuando algo falla.
 */
function cuerpoDeError(res: Response, data: unknown, texto: string): ApiErrorBody {
  const d = (data ?? {}) as Record<string, unknown>;
  if (typeof d.error === "string" && d.error.trim()) {
    return d as unknown as ApiErrorBody;
  }
  // `detail` de FastAPI: string en los errores a mano, lista en los de
  // validación (ahí se resume el primero, que es el que dice qué campo falla).
  let msg = "";
  if (typeof d.detail === "string") {
    msg = d.detail;
  } else if (Array.isArray(d.detail) && d.detail.length) {
    const primero = d.detail[0] as Record<string, unknown>;
    const campo = Array.isArray(primero?.loc) ? primero.loc.join(".") : "";
    msg = [campo, primero?.msg].filter(Boolean).join(": ");
  }
  if (!msg && texto && !texto.trimStart().startsWith("<")) {
    msg = texto.slice(0, 200);
  }
  if (!msg) {
    msg =
      res.status >= 500
        ? `El servidor no respondió bien (${res.status}). Si acaba de actualizarse la app, espera unos segundos y repite.`
        : `La petición falló (${res.status} ${res.statusText}).`;
  }
  return { error: msg, code: `http_${res.status}`, details: {} };
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

/** Contra qué servidor habla la app.
 *
 *  En producción manda SIEMPRE el host desde el que se abrió: Caddy sirve la
 *  web y la API juntas (`/api/*` y `/ws/*` van al mismo sitio), así que una
 *  ruta relativa acierta desde el dominio, desde la IP y desde la APK.
 *
 *  Lo configurado (`NEXT_PUBLIC_API_URL`) solo se respeta en local, que es
 *  donde de verdad hacen falta dos puertos distintos (web :3000, API :8000).
 *  Esa variable se INLINEA en el bundle al compilar: cuando se quedó con el
 *  nombre viejo de Tailscale, el día que ese host dejó de publicarse la app
 *  cargaba pero ninguna llamada llegaba — "Failed to fetch" en el login, con
 *  el servidor perfecto. Un dominio quemado no puede volver a tirar esto.
 */
function esLocal(host: string): boolean {
  return host === "localhost" || host === "127.0.0.1";
}

const CONFIG_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

function resolverBase(): string {
  // En el servidor (SSR/build) no hay `window` ni origen: se usa lo que haya
  // configurado, y si no, la API local.
  if (typeof window === "undefined") return CONFIG_URL || "http://localhost:8000";
  if (esLocal(window.location.hostname)) return CONFIG_URL || "http://localhost:8000";
  return "";
}

const BASE_URL = resolverBase();
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
  // El cuerpo no siempre es nuestro JSON: un 502 mientras la API reinicia
  // llega como HTML y `JSON.parse` reventaba con un SyntaxError que subía en
  // vez del error de verdad.
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!res.ok) {
    throw new ApiError(res.status, cuerpoDeError(res, data, text));
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>("GET", path, undefined, init),
  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>("POST", path, body, init),
  put: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>("PUT", path, body, init),
  patch: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>("PATCH", path, body, init),
  del: <T>(path: string, init?: RequestInit) => request<T>("DELETE", path, undefined, init),
  baseUrl: BASE_URL,
  wsUrl: resolverWs(),
};

/** Igual que la base REST, pero para el WebSocket de la cola.
 *
 *  Se deriva del origen en vez de dejarlo relativo: `new WebSocket("/ws/queue")`
 *  depende del navegador, y aquí se entra también desde la APK.
 */
function resolverWs(): string {
  const cfg = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "") ?? "";
  if (typeof window === "undefined") {
    return (cfg || BASE_URL.replace(/^http/, "ws")).replace(/\/$/, "");
  }
  if (esLocal(window.location.hostname)) {
    return (cfg || BASE_URL.replace(/^http/, "ws")).replace(/\/$/, "");
  }
  const esquema = window.location.protocol === "https:" ? "wss" : "ws";
  return `${esquema}://${window.location.host}`;
}
