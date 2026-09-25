// PRAHARI console — the camera detail dialog (shared by Wall, Map, Registry and Alerts).

import { h, clear, icon, kv, copyField, statePill, fmtDateTime, ago, camState } from "./ui.js";
import { fetchSnapshot, snapshotEndpoint } from "./snapshots.js";

let dlg = null;
let timer = null;
let currentUrl = null;
let ctrl = null;

function ensureDialog() {
  if (dlg) return dlg;
  dlg = h("dialog", { class: "cam-dialog", "aria-labelledby": "cam-dialog-title" });
  dlg.addEventListener("close", stop);
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); }); // click on backdrop
  document.body.append(dlg);
  return dlg;
}

function stop() {
  clearTimeout(timer);
  timer = null;
  if (ctrl) ctrl.abort();
  ctrl = null;
  if (currentUrl) URL.revokeObjectURL(currentUrl);
  currentUrl = null;
}

/** The plate-reading profile measured by the node, in plain words. */
function anprSummary(p) {
  if (!p || typeof p !== "object") return null;
  const n = (x) => Number(x || 0).toLocaleString("en-IN");
  if (p.reason === "insufficient data") return `Still measuring (${n(p.frames)} frames so far)`;
  const pct = (x) => `${Math.round(Number(x || 0) * 100)}%`;
  const detail = `${n(p.plates)} plates in ${n(p.frames)} frames · typical plate ${Math.round(p.plate_px_median || 0)} px tall · ${pct(p.valid_rate)} read as valid plates`;
  return p.anpr_viable ? `Yes — ${detail}` : `No — ${p.reason}. ${detail}`;
}

function capabilityRows(cap) {
  if (!cap || typeof cap !== "object") return [];
  const nice = {
    measured_fps: "Measured frame rate", anpr_viable: "Plate reading possible", anpr_reason: "Why not",
    plate_px: "Plate width (px)", bitrate_kbps: "Bitrate (kbps)", decode_warnings: "Decoder warnings",
  };
  const rows = [];
  for (const [k, v] of Object.entries(cap)) {
    if (k === "state") continue;                       // already shown as Status
    if (k === "last_error" && !v) continue;            // nothing to report
    if (v === null || v === undefined) continue;
    if (k === "anpr") { const s = anprSummary(v); if (s) rows.push(["Plate reading", s]); continue; }
    if (k === "size" && Array.isArray(v) && v.length === 2) { rows.push(["Measured resolution", `${v[0]} × ${v[1]}`]); continue; }
    rows.push([
      nice[k] || k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
      typeof v === "boolean" ? (v ? "Yes" : "No") : typeof v === "object" ? JSON.stringify(v) : String(v),
    ]);
  }
  return rows;
}

/** Open the dialog for camera `c` (a camera object from /api/cameras). */
export function openCamera(c, { onMap } = {}) {
  const d = ensureDialog();
  stop();
  const st = camState(c);
  const img = h("img", { alt: `Latest picture from ${c.name || c.id}`, hidden: true });
  const ph = h("div", { class: "snap-ph" }, icon("camera"), h("span", { class: "ph-text" }, "Loading picture…"));
  const stamp = h("span", { class: "snap-stamp", hidden: true });
  const frame = h("div", { class: `snap big st-${st.key}` }, img, ph, stamp);

  const res = c.width && c.height ? `${c.width} × ${c.height}` : null;
  const details = kv([
    ["Camera id", h("span", { class: "mono" }, c.id)],
    ["Department", c.department || "—"],
    ["Status", statePill(c)],
    ["Last seen", c.last_seen ? `${ago(c.last_seen)} (${fmtDateTime(c.last_seen)})` : "Never"],
    ["Location", c.lat !== null && c.lat !== undefined ? `${Number(c.lat).toFixed(5)}, ${Number(c.lon).toFixed(5)}` : "Not recorded — won't appear on the map"],
    ["Video", [c.codec ? c.codec.toUpperCase() : null, res, c.fps ? `${c.fps} fps declared` : null].filter(Boolean).join(" · ") || "—"],
    ["Onboarded via", { catalogue: "Catalogue sync", bulk: "CSV import", manual: "Added by hand", api: "API" }[c.source] || c.source],
    ...capabilityRows(c.capability),
  ]);

  const actions = h("div", { class: "row gap" });
  if (onMap && c.lat !== null && c.lat !== undefined) {
    actions.append(h("button", { type: "button", class: "btn", onclick: () => { d.close(); onMap(c); } }, icon("pin"), "Show on map"));
  }

  clear(d,
    h("div", { class: "dialog-head" },
      h("h2", { id: "cam-dialog-title" }, c.name || c.id),
      h("button", { type: "button", class: "btn icon-only ghost", "aria-label": "Close", onclick: () => d.close() }, icon("close"))),
    h("div", { class: "dialog-body cam-detail" },
      h("div", null, frame, actions),
      h("div", null, details,
        h("h3", null, "Stream links"),
        h("p", { class: "muted small" }, "Copy into VLC or ffplay to watch the camera directly."),
        copyField("RTSP", c.rtsp_url),
        copyField("HLS", c.hls_url),
        copyField("WebRTC (WHEP)", c.whep_url))));

  const tick = async () => {
    if (!d.open) return;
    ctrl = new AbortController();
    const r = await fetchSnapshot(c.id, { signal: ctrl.signal });
    if (!d.open) { if (r.ok) URL.revokeObjectURL(r.url); return; }
    if (r.ok) {
      if (currentUrl) URL.revokeObjectURL(currentUrl);
      currentUrl = r.url;
      img.src = r.url;
      img.hidden = false;
      ph.hidden = true;
      stamp.hidden = false;
      stamp.textContent = `Updated ${new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata" })} IST`;
    } else if (!currentUrl) {
      ph.querySelector(".ph-text").textContent =
        st.key === "offline" ? "Camera offline — no picture" : r.reason === "network" ? "Can't reach the server" : "No picture yet";
    }
    timer = setTimeout(tick, snapshotEndpoint() === "absent" ? 15000 : 2000);
  };
  if (!d.open) d.showModal();
  tick();
}
