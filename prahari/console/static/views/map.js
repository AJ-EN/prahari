// Map — every located camera, by status; optional coverage-gap layer.

import { get, cameras } from "../api.js";
import { h, clear, camState, errorBox, loading, empty, num, notice } from "../ui.js";
import { createMap, refreshSize, cameraIcon, cameraPopup, legendControl, hasLeaflet } from "../maputil.js";

let root, ctx, els = {};
let map = null, camLayer = null, gapLayer = null, legend = null;
let markers = new Map();
let gapReport = null, didFit = false, timer = null;
let pendingFocus = null;

function init(r, c) {
  root = r; ctx = c;
  els.gaps = h("input", { id: "map-gaps", type: "checkbox" });
  els.dept = h("select", { id: "map-dept" }, h("option", { value: "" }, "All departments"));
  els.fit = h("button", { type: "button", class: "btn small", onclick: () => fitAll() }, "Fit all cameras");
  els.info = h("div", { class: "small muted", "aria-live": "polite" });
  els.gapInfo = h("div", { class: "gap-info small", hidden: true, "aria-live": "polite" });
  els.msg = h("div");
  els.map = h("div", { class: "map map-full", role: "region", "aria-label": "Map of cameras" });
  els.gaps.addEventListener("change", toggleGaps);
  els.dept.addEventListener("change", () => draw());

  clear(root,
    h("div", { class: "view-head" },
      h("h1", { id: "h-map" }, "Map"),
      h("p", { class: "lede" }, "Where every camera is, and whether it is working. Shapes and colours both show status.")),
    h("div", { class: "toolbar" },
      h("div", { class: "field inline" }, h("label", { for: "map-dept" }, "Department"), els.dept),
      h("label", { class: "check", for: "map-gaps" }, els.gaps, "Show coverage gaps"),
      els.fit, els.info),
    els.gapInfo, els.msg, els.map);

  if (!hasLeaflet()) {
    clear(els.msg, notice("error", "The map library didn't load. Refresh the page; if it persists, the file static/vendor/leaflet/leaflet.js is missing."));
    return;
  }
  map = createMap(els.map);
  camLayer = window.L.layerGroup().addTo(map);
}

function fitAll() {
  if (!map) return;
  const pts = [...markers.values()].map((m) => m.getLatLng());
  if (pts.length === 1) map.setView(pts[0], 14);
  else if (pts.length) map.fitBounds(window.L.latLngBounds(pts).pad(0.15));
}

let camList = [];

async function load(force = false) {
  try {
    camList = await cameras({ force });
    const depts = [...new Set(camList.map((c) => c.department).filter(Boolean))].sort();
    const cur = els.dept.value;
    clear(els.dept, h("option", { value: "" }, "All departments"), depts.map((d) => h("option", { value: d }, d)));
    els.dept.value = depts.includes(cur) ? cur : "";
    clear(els.msg);
    draw();
  } catch (e) {
    clear(els.msg, errorBox(e, () => load(true)));
  }
}

function draw() {
  if (!map) return;
  const L = window.L;
  const dept = els.dept.value;
  const list = camList.filter((c) => !dept || c.department === dept);
  const located = list.filter((c) => c.lat !== null && c.lat !== undefined && c.lon !== null && c.lon !== undefined);
  const counts = {};
  const keep = new Set();
  for (const c of located) {
    const st = camState(c);
    counts[st.key] = (counts[st.key] || 0) + 1;
    keep.add(c.id);
    let m = markers.get(c.id);
    if (!m) {
      m = L.marker([c.lat, c.lon], { keyboard: true, title: c.name || c.id, riseOnHover: true }).addTo(camLayer);
      markers.set(c.id, m);
    } else m.setLatLng([c.lat, c.lon]);
    if (m._stKey !== st.key) { m.setIcon(cameraIcon(st.key)); m._stKey = st.key; }
    m.options.title = c.name || c.id;
    if (!m.isPopupOpen()) m.bindPopup(() => cameraPopup(c, { onDetails: ctx.openCamera }));
    m.bindTooltip(`${c.name || c.id} — ${st.label}`, { direction: "top", offset: [0, -10] });
  }
  for (const [id, m] of markers) if (!keep.has(id)) { camLayer.removeLayer(m); markers.delete(id); }
  if (legend) legend.remove();
  legend = legendControl(counts).addTo(map);
  const missing = list.length - located.length;
  els.info.textContent = `${num(located.length)} camera${located.length === 1 ? "" : "s"} on the map` +
    (missing ? ` · ${num(missing)} without a location (see Registry)` : "");
  if (!list.length && !camList.length) clear(els.msg, empty("No cameras registered yet.", "Add cameras in Registry to see them here."));
  if (!didFit && markers.size) { didFit = true; fitAll(); }
  if (pendingFocus) focusCamera(pendingFocus);
}

function focusCamera(id) {
  const m = markers.get(id);
  if (!m) return;
  pendingFocus = null;
  map.setView(m.getLatLng(), Math.max(map.getZoom(), 15));
  m.openPopup();
}

async function toggleGaps() {
  if (!map) return;
  const L = window.L;
  if (!els.gaps.checked) {
    if (gapLayer) map.removeLayer(gapLayer);
    els.gapInfo.hidden = true;
    return;
  }
  els.gapInfo.hidden = false;
  clear(els.gapInfo, loading("Working out coverage gaps…"));
  try {
    gapReport = await get("/api/reports/gap", { format: "json" }, { timeout: 60000 });
  } catch (e) {
    clear(els.gapInfo, errorBox(e, toggleGaps));
    return;
  }
  if (!els.gaps.checked) return;
  const cov = gapReport.coverage || {};
  const cells = cov.uncovered_cells || [];
  if (gapLayer) map.removeLayer(gapLayer);
  const renderer = L.canvas({ padding: 0.3 });
  gapLayer = L.layerGroup(cells.map((cell) => {
    const poly = L.polygon((cell.polygon || []).map(([lon, lat]) => [lat, lon]), {
      renderer, color: "#c2410c", weight: 0.6, fillColor: "#ea580c", fillOpacity: 0.28, interactive: true,
    });
    poly.bindTooltip(`No camera within ${cov.radius_km ?? 1} km · nearest: ${cell.nearest_camera || "—"} (${num(cell.nearest_camera_km, 1)} km away)`, { sticky: true });
    return poly;
  })).addTo(map);
  camLayer.eachLayer((m) => m.setZIndexOffset(1000));
  clear(els.gapInfo,
    h("span", { class: "gap-swatch", "aria-hidden": "true" }),
    h("strong", null, `Coverage ${num(cov.coverage_pct, 1)}%`),
    ` of ${num(cov.cells)} cells (${cov.cell_km ?? 1} km grid) have a camera within ${cov.radius_km ?? 1} km; ` +
    `${num(cov.effective_coverage_pct, 1)}% counting only healthy cameras. ` +
    `Shaded: ${cells.length < (cov.uncovered || 0) ? `the ${num(cells.length)} worst of ${num(cov.uncovered)}` : num(cells.length)} uncovered cells. `,
    h("a", { href: "#/registry?panel=gaps" }, "Full gap report →"));
}

function show(params) {
  refreshSize(map);
  const focus = params && params.get("focus");
  if (focus) { pendingFocus = focus; didFit = true; }
  if (params && params.get("gaps") === "1" && !els.gaps.checked) { els.gaps.checked = true; toggleGaps(); }
  if (!camList.length && !els.msg.childElementCount) clear(els.msg, loading("Loading cameras…"));
  load();
  clearInterval(timer);
  timer = setInterval(() => { if (!document.hidden) load(true); }, 15000);
}

function hide() { clearInterval(timer); timer = null; }

export default { id: "map", title: "Map", icon: "map", init, show, hide, refresh: () => load(true) };
