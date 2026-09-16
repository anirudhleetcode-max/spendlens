const TOKEN_KEY = "spendlens.token";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export const tokenStore = {
  get: () => {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set: (t: string | null) => {
    try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
  },
};

function authHeaders(init?: HeadersInit) {
  const headers = new Headers(init);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function toError(res: Response): Promise<ApiError> {
  const data = await res.json().catch(() => ({}));
  const detail = (data as { detail?: unknown }).detail;
  const msg = typeof detail === "string" ? detail
    : Array.isArray(detail) ? detail.map((d: { msg?: string; loc?: string[] }) =>
        `${d.loc?.slice(-1)[0] ?? ""}: ${d.msg ?? ""}`.replace(/^: /, "")).join(", ")
    : `Request failed (${res.status})`;
  if (res.status === 401) tokenStore.set(null);
  return new ApiError(res.status, msg);
}

export async function api<T = unknown>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = authHeaders(opts.headers);
  let body = opts.body;
  if (opts.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.json);
  }
  let res: Response;
  try {
    res = await fetch(path, { ...opts, headers, body });
  } catch {
    throw new ApiError(0, "Can't reach the server. Is the backend running?");
  }
  if (res.status === 204) return undefined as T;
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

/** Authenticated binary fetch (receipt images, CSV). */
export async function apiBlob(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const res = await fetch(path, { headers: authHeaders() });
  if (!res.ok) throw await toError(res);
  const cd = res.headers.get("Content-Disposition");
  const filename = cd?.match(/filename="?([^";]+)"?/)?.[1] ?? null;
  return { blob: await res.blob(), filename };
}

export async function downloadFile(path: string, fallbackName: string) {
  const { blob, filename } = await apiBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename ?? fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
