// PRAHARI console — camera snapshot loader.
//
// GET /api/cameras/{id}/snapshot.jpg returns the node's latest decoded frame. The endpoint
// may not exist yet (it is added by the integration step) and a camera may simply have no
// frame yet. We fetch with fetch() (not <img src>) so we can see the status code:
//   * route missing (FastAPI's default 404 "Not Found" for every camera) -> "endpoint absent":
//     stop hammering it and probe ONE camera every 15 s; images appear by themselves once
//     the endpoint is deployed.
//   * per-camera failure -> back off that tile (2 s, 4 s, ... 30 s).

import { snapshotUrl } from "./api.js";

const PROBE_MS = 15000;
let endpoint = "unknown"; // unknown | present | absent
let lastProbe = 0;
let probeCursor = 0;
let routeMissingStreak = 0;

export const snapshotEndpoint = () => endpoint;

/**
 * Should this camera be fetched now? (Callers still track per-tile backoff.)
 * While the endpoint looks absent, only one camera per PROBE_MS is allowed through.
 */
export function mayFetch(index, total) {
  if (endpoint !== "absent") return true;
  const now = Date.now();
  if (now - lastProbe < PROBE_MS) return false;
  if (total > 0 && index !== probeCursor % total) return false;
  lastProbe = now;
  probeCursor++;
  return true;
}

/**
 * Fetch one snapshot. Resolves {ok:true, url} (an object URL — caller must revoke) or
 * {ok:false, reason: "none"|"error"|"network"}. Never throws.
 */
export async function fetchSnapshot(id, { signal } = {}) {
  let res;
  try {
    res = await fetch(`${snapshotUrl(id)}?t=${Date.now()}`, { cache: "no-store", signal });
  } catch {
    return { ok: false, reason: "network" };
  }
  if (res.ok && (res.headers.get("content-type") || "").startsWith("image/")) {
    try {
      const blob = await res.blob();
      endpoint = "present";
      routeMissingStreak = 0;
      return { ok: true, url: URL.createObjectURL(blob) };
    } catch {
      return { ok: false, reason: "error" };
    }
  }
  if (res.status === 404 || res.status === 405) {
    let detail = null;
    try { detail = (await res.json()).detail; } catch { /* not JSON */ }
    // Starlette's answer for a route that doesn't exist at all.
    if (detail === "Not Found" || detail === "Method Not Allowed") {
      routeMissingStreak++;
      if (endpoint !== "present" && routeMissingStreak >= 2) endpoint = "absent";
    }
    return { ok: false, reason: "none" };
  }
  return { ok: false, reason: res.status === 503 || res.status === 204 ? "none" : "error" };
}
