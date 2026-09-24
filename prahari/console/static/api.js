// PRAHARI console — API client. Every call goes through request(), which turns
// network failures, timeouts and FastAPI error bodies into one plain-language ApiError.

export const SERVER_DOWN =
  "Can't reach the PRAHARI server. Is `python run.py` still running on this machine?";

export class ApiError extends Error {
  constructor(message, { status = 0, kind = "http", detail = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind; // http | network | timeout | abort
    this.detail = detail;
  }
}

// ---------------------------------------------------------------- session storage
// Purpose / case id / operator name are remembered for this browser tab only.
export const session = {
  get(key, fallback = "") {
    try { return sessionStorage.getItem(key) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { sessionStorage.setItem(key, value ?? ""); } catch { /* storage blocked: ignore */ }
  },
};

export const prefs = {
  get(key, fallback = null) {
    try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, value); } catch { /* storage blocked: ignore */ }
  },
};

export function getActor() {
  return session.get("prahari.actor", "").trim();
}

// HTTP header values must be Latin-1; encode anything else so fetch never throws.
function headerSafe(v) {
  return /^[\x20-\x7e]*$/.test(v) ? v : encodeURIComponent(v);
}

export function buildUrl(path, query) {
  const url = new URL(path, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      url.searchParams.set(k, String(v));
    }
  }
  return url.pathname + url.search;
}

function describe(status, body) {
  const d = body && typeof body === "object" ? body.detail : null;
  if (typeof d === "string" && d) return d;
  if (d && typeof d === "object" && !Array.isArray(d) && d.message) return d.message;
  if (Array.isArray(d) && d.length) {
    return d
      .map((e) => {
        const where = Array.isArray(e.loc) ? e.loc.filter((p) => p !== "body" && p !== "query").join(".") : "";
        return where ? `${where}: ${e.msg}` : e.msg;
      })
      .join("; ");
  }
  if (status === 404) return "Not found.";
  if (status === 507) return "The server's disk is nearly full, so nothing new can be stored.";
  if (status >= 500) return `The server hit an error (HTTP ${status}). Check the server window for details.`;
  return `The request was refused (HTTP ${status}).`;
}

const TIMEOUT_MS = 20000;

/**
 * request(path, {method, query, json, body, contentType, timeout, raw, signal})
 * Returns parsed JSON (or text); with raw:true returns the Response.
 */
export async function request(path, opts = {}) {
  const { method = "GET", query, json, body, contentType, timeout = TIMEOUT_MS, raw = false, signal } = opts;
  const headers = {};
  const actor = getActor();
  if (actor) headers["X-Actor"] = headerSafe(actor);
  let payload;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(json);
  } else if (body !== undefined) {
    headers["Content-Type"] = contentType || "text/plain";
    payload = body;
  }
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; ctrl.abort(); }, timeout);
  const onAbort = () => ctrl.abort();
  if (signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  try {
    let res;
    try {
      res = await fetch(buildUrl(path, query), { method, headers, body: payload, signal: ctrl.signal, cache: "no-store" });
    } catch {
      if (timedOut) throw new ApiError("The server took too long to answer. Please try again.", { kind: "timeout" });
      if (signal?.aborted) throw new ApiError("Cancelled.", { kind: "abort" });
      throw new ApiError(SERVER_DOWN, { kind: "network" });
    }
    if (!res.ok) {
      let detail = null;
      try { detail = await res.json(); } catch { /* not JSON */ }
      throw new ApiError(describe(res.status, detail), { status: res.status, kind: "http", detail });
    }
    if (raw) return res;
    const ct = res.headers.get("content-type") || "";
    try {
      return ct.includes("json") ? await res.json() : await res.text();
    } catch {
      if (timedOut) throw new ApiError("The server took too long to answer. Please try again.", { kind: "timeout" });
      throw new ApiError("The server sent an unreadable answer. Please try again.", { kind: "http", status: res.status });
    }
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
}

export const get = (path, query, opts = {}) => request(path, { ...opts, query });
export const post = (path, json, opts = {}) => request(path, { ...opts, method: "POST", json });

// ---------------------------------------------------------------- shared caches
let camCache = { at: 0, data: null, pending: null };
const CAM_TTL = 10000;

/** All registered cameras (cached ~10 s; force:true to refetch). */
export async function cameras({ force = false } = {}) {
  const fresh = camCache.data && Date.now() - camCache.at < CAM_TTL;
  if (fresh && !force) return camCache.data;
  if (camCache.pending) return camCache.pending;
  camCache.pending = get("/api/cameras")
    .then((r) => {
      camCache = { at: Date.now(), data: r.cameras || [], pending: null };
      return camCache.data;
    })
    .catch((e) => {
      camCache.pending = null;
      throw e;
    });
  return camCache.pending;
}

export function invalidateCameras() {
  camCache = { at: 0, data: camCache.data, pending: null };
}

/** Camera lookup by id from the last loaded list (no fetch). */
export function cachedCamera(id) {
  return (camCache.data || []).find((c) => c.id === id) || null;
}

export const snapshotUrl = (id) => `/api/cameras/${encodeURIComponent(id)}/snapshot.jpg`;
