// PRAHARI console — Leaflet helpers (Leaflet 1.9.4 is vendored and loaded as global `L`).
// The map must stay useful offline: if OpenStreetMap tiles can't load, markers and
// routes still draw on a plain background, with a small note saying why.

import { h, camState, stateShape, fmtDateTime, ago, STATE_NAMES } from "./ui.js";

export const hasLeaflet = () => typeof window.L !== "undefined";

// Gujarat, for an empty map.
const DEFAULT_VIEW = { center: [22.7, 71.8], zoom: 7 };

export function createMap(el, { zoomControl = true } = {}) {
  if (!hasLeaflet()) return null;
  const L = window.L;
  const map = L.map(el, { zoomControl, preferCanvas: false, worldCopyJump: false, attributionControl: true })
    .setView(DEFAULT_VIEW.center, DEFAULT_VIEW.zoom);
  const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
    crossOrigin: true,
  }).addTo(map);

  const note = h("div", { class: "map-offline-note", role: "status", hidden: true },
    "Map background unavailable (no internet?) — cameras and routes are still shown.");
  el.append(note);
  let loaded = 0, failed = 0;
  tiles.on("tileload", () => {
    loaded++;
    note.hidden = true;
    el.classList.remove("no-tiles");
  });
  tiles.on("tileerror", () => {
    failed++;
    if (loaded === 0 && failed >= 3) {
      note.hidden = false;
      el.classList.add("no-tiles");
    }
  });
  // If nothing at all arrives within a few seconds, say so rather than show a blank grey box.
  setTimeout(() => {
    if (loaded === 0) { note.hidden = false; el.classList.add("no-tiles"); }
  }, 6000);
  return map;
}

/** Leaflet sizes itself on creation; call when a hidden map becomes visible. */
export function refreshSize(map) {
  if (!map) return;
  requestAnimationFrame(() => map.invalidateSize({ pan: false }));
}

export function cameraIcon(key, { size = 22 } = {}) {
  const L = window.L;
  return L.divIcon({
    className: `cam-marker st-${key}`,
    html: `<span class="cam-marker-inner">${stateShape(key)}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

/** Popup DOM for a camera (text only; safe for catalogue-provided names). */
export function cameraPopup(c, { onDetails } = {}) {
  const st = camState(c);
  const box = h("div", { class: "popup" },
    h("strong", { class: "popup-title" }, c.name || c.id),
    h("div", { class: "muted mono small" }, c.id),
    h("div", null, h("span", { class: `pill st-${st.key}` }, h("span", { class: "shape-wrap", html: stateShape(st.key) }), st.label)),
    h("div", { class: "small" }, `${c.department || "No department"} · last seen ${c.last_seen ? ago(c.last_seen) : "never"}`),
    c.last_seen ? h("div", { class: "small muted" }, fmtDateTime(c.last_seen)) : null,
    c.codec || c.width ? h("div", { class: "small muted" }, [c.codec && c.codec.toUpperCase(), c.width && c.height ? `${c.width}×${c.height}` : null].filter(Boolean).join(" · ")) : null);
  if (onDetails) box.append(h("button", { type: "button", class: "btn small", onclick: () => onDetails(c) }, "Details & stream links"));
  return box;
}

/** Legend control listing each state that occurs, with its shape and count. */
export function legendControl(counts) {
  const L = window.L;
  const ctl = L.control({ position: "bottomleft" });
  ctl.onAdd = () => {
    const box = h("div", { class: "map-legend" }, h("strong", null, "Cameras"));
    for (const key of Object.keys(STATE_NAMES)) {
      if (!counts[key]) continue;
      box.append(h("div", { class: "legend-row" },
        h("span", { class: `cam-marker st-${key} legend-shape`, html: `<span class="cam-marker-inner">${stateShape(key)}</span>` }),
        `${STATE_NAMES[key]} (${counts[key]})`));
    }
    L.DomEvent.disableClickPropagation(box);
    return box;
  };
  return ctl;
}

/** Bearing in screen space between two lat/lngs (degrees, 0 = east, clockwise). */
export function screenAngle(map, a, b) {
  const pa = map.project(a, 10), pb = map.project(b, 10);
  return (Math.atan2(pb.y - pa.y, pb.x - pa.x) * 180) / Math.PI;
}
