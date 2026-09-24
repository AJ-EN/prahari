// Trace — reconstruct one vehicle's route across cameras.
// Misreads are matched by OCR-confusion distance; physically impossible hops are
// flagged in red and KEPT (they may mean a cloned plate); with no confident match
// the ranked near-misses are shown with an explanation, never an empty page.

import { get, session, ApiError, cameras, cachedCamera } from "../api.js";
import {
  h, clear, icon, fmtTime, fmtDateTime, duration, num, plateChip, plateDiff, fmtPlate, normPlate,
  catChip, errorBox, loading, notice, purposeFields, tableWrap, busy,
} from "../ui.js";
import { createMap, refreshSize, hasLeaflet, screenAngle } from "../maputil.js";

let root, ctx, els = {}, purpose;
let map = null, routeLayer = null, stopMarkers = new Map();
let last = null; // last trace result
let runSeq = 0;

// ---------------------------------------------------------------- recent plates
function recent() {
  try { return JSON.parse(session.get("prahari.recentTraces", "[]")) || []; } catch { return []; }
}
function remember(plate) {
  const list = [plate, ...recent().filter((p) => p !== plate)].slice(0, 6);
  session.set("prahari.recentTraces", JSON.stringify(list));
  paintRecent();
}
function paintRecent() {
  const list = recent();
  clear(els.recent, list.length ? [h("span", { class: "muted small" }, "Recent:"),
    list.map((p) => h("button", { type: "button", class: "chip chip-btn mono", onclick: () => { els.plate.value = p; run(); } }, fmtPlate(p)))] : null);
}

// ---------------------------------------------------------------- init
function init(r, c) {
  root = r; ctx = c;
  purpose = purposeFields();
  els.plate = h("input", { id: "tr-plate", class: "plate-input mono", type: "text", required: true, autocomplete: "off",
    autocapitalize: "characters", spellcheck: "false", maxlength: 16, placeholder: "e.g. GJ01AB1234", "aria-describedby": "tr-plate-hint" });
  els.from = h("input", { id: "tr-from", type: "datetime-local", step: 1 });
  els.to = h("input", { id: "tr-to", type: "datetime-local", step: 1 });
  els.speed = h("input", { id: "tr-speed", type: "number", min: 20, max: 1000, step: 10, value: "150" });
  els.go = h("button", { type: "submit", class: "btn primary big" }, icon("trace"), "Trace route");
  els.recent = h("div", { class: "recent-row" });
  els.formErr = h("div", { class: "err-text", role: "alert" });
  els.out = h("div", { class: "trace-out" });

  const form = h("form", { class: "card trace-form", novalidate: true },
    h("div", { class: "trace-search" },
      h("div", { class: "field grow" },
        h("label", { for: "tr-plate", class: "big-label" }, "Vehicle number plate"),
        els.plate,
        h("span", { id: "tr-plate-hint", class: "small muted" }, "Spaces and dashes are ignored. Partial or misread plates are fine — close readings are matched too.")),
      els.go),
    purpose.el,
    h("details", { class: "advanced" }, h("summary", null, "Time window and speed limit (optional)"),
      h("div", { class: "form-grid wide" },
        h("div", { class: "field" }, h("label", { for: "tr-from" }, "From (IST)"), els.from),
        h("div", { class: "field" }, h("label", { for: "tr-to" }, "To (IST)"), els.to),
        h("div", { class: "field" }, h("label", { for: "tr-speed" }, "Flag hops faster than (km/h)"), els.speed))),
    els.formErr, els.recent);
  form.addEventListener("submit", (e) => { e.preventDefault(); run(); });
  els.plate.addEventListener("input", () => { els.plate.value = els.plate.value.toUpperCase(); });

  clear(root,
    h("div", { class: "view-head" },
      h("h1", { id: "h-trace" }, "Trace a vehicle"),
      h("p", { class: "lede" }, "Where has this vehicle been? Every camera sighting, in time order, drawn on the map.")),
    form, els.out);
  paintRecent();
}

// ---------------------------------------------------------------- run
async function run() {
  els.formErr.textContent = "";
  const plate = normPlate(els.plate.value);
  if (plate.length < 4) {
    els.formErr.textContent = "Enter at least 4 characters of the plate.";
    els.plate.setAttribute("aria-invalid", "true");
    els.plate.focus();
    return;
  }
  els.plate.setAttribute("aria-invalid", "false");
  const p = purpose.read();
  if (!p) { els.formErr.textContent = "Fill in the purpose and case number — every search is logged."; return; }
  const my = ++runSeq;
  history.replaceState(null, "", `#/trace?plate=${encodeURIComponent(plate)}`);
  remember(plate);
  const query = { ...p, from: els.from.value || undefined, to: els.to.value || undefined, max_speed_kmh: els.speed.value || undefined };
  await busy(els.go, "Tracing…", async () => {
    clear(els.out, loading(`Searching every camera for ${fmtPlate(plate)}…`));
    let res, watch = null;
    try {
      [res, watch] = await Promise.all([
        get(`/api/trace/${encodeURIComponent(plate)}`, query, { timeout: 60000 }),
        get(`/api/watchlist/${encodeURIComponent(plate)}`).catch((e) => (e instanceof ApiError && e.status === 404 ? { none: true } : null)),
        cameras().catch(() => []),
      ]);
    } catch (e) {
      if (my === runSeq) clear(els.out, errorBox(e, run));
      return;
    }
    if (my !== runSeq) return;
    last = res;
    render(res, watch);
  });
}

// ---------------------------------------------------------------- render
function watchBadge(watch) {
  if (!watch) return null;
  if (watch.none) return h("div", { class: "wl-status wl-none" }, icon("check"), "Not on the watchlist");
  const d = watch.details || {};
  return h("div", { class: `wl-status ${watch.active === false ? "wl-none" : "wl-hit"}` },
    icon("warn"), h("span", null, watch.active === false ? "Was on the watchlist (deactivated): " : "On the watchlist: "), catChip(watch.category),
    h("div", { class: "small" }, [d.vehicle, d.fir_no && `FIR ${d.fir_no}`, d.police_station].filter(Boolean).join(" · ")));
}

function grammarLine(g) {
  if (!g) return null;
  if (g.valid) {
    const where = [g.state, g.district && `${g.district} RTO`].filter(Boolean).join(" · ");
    return h("div", { class: "grammar ok" }, icon("check"), where ? `Valid plate — ${where}` : "Valid plate format");
  }
  return h("div", { class: "grammar bad" }, icon("warn"), `Not a valid Indian plate format${g.reasons && g.reasons.length ? ` (${g.reasons.join("; ")})` : ""}`);
}

function didYouMean(g) {
  const list = (g && g.did_you_mean) || [];
  if (!list.length) return null;
  return h("div", { class: "dym" }, h("span", null, "Valid plates it could be:"),
    list.slice(0, 5).map((c) => h("button", { type: "button", class: "chip chip-btn mono", title: (c.edits || []).join(", "),
      onclick: () => { els.plate.value = c.plate; run(); } }, fmtPlate(c.plate))));
}

function camName(id, fallback) {
  const c = cachedCamera(id);
  return (c && c.name) || fallback || id;
}

function render(res, watch) {
  const s = res.summary || {};
  const q = res.query;
  const head = h("div", { class: "trace-head card" },
    h("div", { class: "th-plate" }, plateChip(q, { size: "xl" }), grammarLine(res.grammar), watchBadge(watch)));

  if (res.status !== "matched" || !(res.sightings || []).length) {
    head.append(h("div", { class: "th-main" },
      h("h2", { class: "th-headline" }, `No confident sighting of ${fmtPlate(q)}`),
      h("p", null, `No camera read a plate close enough to ${fmtPlate(q)} to be sure it is the same vehicle` +
        `${res.params && res.params.max_distance !== undefined ? ` (confusion distance up to ${res.params.max_distance})` : ""}. ` +
        ((res.near_misses || []).length ? "The closest readings are ranked below — check them before concluding the vehicle was not seen." : "")),
      didYouMean(res.grammar)));
    clear(els.out, head, nearMissPanel(res, { open: true }), auditNote());
    return;
  }

  const span = s.first_seen && s.last_seen ? (new Date(s.last_seen) - new Date(s.first_seen)) / 1000 : null;
  const readings = [...(s.distinct_readings || [])].sort((a, b) => (normPlate(b) === normPlate(q)) - (normPlate(a) === normPlate(q))).map((r) => {
    const exact = normPlate(r) === normPlate(q);
    return h("span", { class: `chip mono ${exact ? "" : "chip-warn"}`, title: exact ? "exact read" : "misread, matched by OCR confusion" },
      exact ? fmtPlate(r) : plateDiff(r, q).el);
  });
  head.append(h("div", { class: "th-main" },
    h("h2", { class: "th-headline" }, `Seen at ${num(s.cameras)} camera${s.cameras === 1 ? "" : "s"}, ${fmtTime(s.first_seen)} → ${fmtTime(s.last_seen)} IST`),
    h("div", { class: "th-stats" },
      stat("Sightings", num(s.sightings)), stat("Cameras", num(s.cameras)), stat("Route length", `${num(s.path_km, 1)} km`),
      stat("Time span", duration(span)), stat("Plate reads matched", num(s.events_matched))),
    h("div", { class: "th-readings" }, h("span", { class: "muted small" }, "Read as: "), readings,
      readings.length > 1 ? h("span", { class: "muted small" }, " — highlighted characters were misread by the camera and corrected by confusion matching.") : null)));

  const flags = (res.sightings || []).filter((x) => x.hop && x.hop.plausible === false);
  const flagBox = flags.length ? notice("error", icon("warn"), h("div", null,
    h("strong", null, `${flags.length} physically impossible jump${flags.length === 1 ? "" : "s"} — flagged, not hidden`),
    h("ul", null, flags.map((x) => h("li", null,
      `Stop ${x.seq - 1} → ${x.seq}: ${num(x.hop.distance_km, 1)} km in ${duration(x.hop.gap_s)} = ${num(x.hop.speed_kmh)} km/h. `,
      h("span", { class: "muted" }, "Possible misread, camera clock error, or a cloned plate (two vehicles with the same number)."))))))
    : notice("ok", icon("check"), "Every hop between cameras is physically plausible.");

  els.mapBox = h("div", { class: "map map-trace", role: "region", "aria-label": `Route map for ${q}` });
  const mapCard = h("section", { class: "card trace-map-card", "aria-labelledby": "h-route" },
    h("div", { class: "card-head" }, h("h2", { id: "h-route" }, "Route"),
      h("div", { class: "row gap" },
        h("button", { type: "button", class: "btn small", onclick: () => fitRoute("all") }, "Whole route"),
        flags.length ? h("button", { type: "button", class: "btn small", onclick: () => fitRoute("main") }, "Zoom to main route") : null,
        h("button", { type: "button", class: "btn small ghost", onclick: () => window.print() }, "Print / save PDF"))),
    h("div", { class: "route-legend small" },
      h("span", null, h("span", { class: "lg-line ok", "aria-hidden": "true" }), "plausible hop (arrow = direction)"),
      h("span", null, h("span", { class: "lg-line bad", "aria-hidden": "true" }), "impossible hop (dashed red)"),
      h("span", null, h("span", { class: "stop-dot", "aria-hidden": "true" }, "1"), "stop number, in time order")),
    els.mapBox);

  clear(els.out, head, flagBox, mapCard, timelineCard(res), nearMissPanel(res, { open: false }), auditNote());
  drawRoute(res);
}

const stat = (label, value) => h("div", { class: "th-stat" }, h("span", { class: "th-stat-v" }, value), h("span", { class: "th-stat-l" }, label));

function auditNote() {
  return h("p", { class: "small muted audit-note" }, icon("lock"),
    `This search was recorded in the audit log (purpose: “${session.get("prahari.purpose")}”, case: ${session.get("prahari.case_id")}).`);
}

// ---------------------------------------------------------------- timeline
function timelineCard(res) {
  const q = res.query;
  const rows = [];
  for (const x of res.sightings) {
    const hop = x.hop;
    const bad = hop && hop.plausible === false;
    const { el: readEl, edits } = plateDiff(x.observed, q);
    const exact = x.match_distance === 0 || !edits.length;
    const cam = x.camera || {};
    const tr = h("tr", { class: `${bad ? "row-bad" : ""}`, id: `stop-${x.seq}`, tabindex: "-1", dataset: { seq: x.seq } },
      h("td", null, h("button", { type: "button", class: `stop-num ${bad ? "bad" : ""}`, "aria-label": `Show stop ${x.seq} on the map`, onclick: () => focusStop(x.seq) }, String(x.seq))),
      h("td", { title: fmtDateTime(x.ts) }, h("strong", { class: "mono" }, fmtTime(x.ts)),
        x.reads > 1 ? h("div", { class: "small muted nowrap" }, `${x.reads} reads`) : null),
      h("td", null, h("strong", null, cam.name || cam.id), h("div", { class: "small muted" }, [cam.id, cam.department].filter(Boolean).join(" · ")),
        cam.lat === null || cam.lat === undefined ? h("div", { class: "small warn-text" }, "no location — not on map") : null),
      h("td", { title: x.matched_on && x.matched_on !== "plate" ? `matched on ${x.matched_on === "raw_text" ? "the raw OCR text" : x.matched_on}` : undefined },
        h("span", { class: "read-as" }, readEl),
        exact ? null : h("div", { class: "small corr" }, h("span", { class: "chip chip-warn small" }, "misread"), ` ${edits.join(", ")}`)),
      h("td", { class: "num" }, h("strong", { class: "mono" }, Number(x.match_distance ?? 0).toFixed(2)),
        h("div", { class: "small muted" }, exact ? "exact" : "OCR confusion")),
      h("td", null, confBar("OCR", x.confidence && x.confidence.ocr), confBar("Detect", x.confidence && x.confidence.det)),
      h("td", { class: "num" }, hop ? shortDur(hop.gap_s) : h("span", { class: "muted" }, "start")),
      h("td", { class: "num" }, hop ? `${num(hop.distance_km, 1)} km` : "—"),
      h("td", { class: `num ${bad ? "speed-bad" : ""}` }, hop ? [bad ? icon("warn") : null, `${num(hop.speed_kmh)} km/h`] : "—"),
      h("td", null, !hop ? h("span", { class: "chip" }, "Start")
        : bad ? h("span", { class: "chip chip-bad" }, icon("warn"), "IMPOSSIBLE")
          : h("span", { class: "chip chip-ok" }, icon("check"), "OK")));
    rows.push(tr);
    if (bad) {
      rows.push(h("tr", { class: "row-bad-reason" }, h("td", { colspan: 10 }, icon("warn"),
        h("strong", null, ` Implausible hop from ${camName(hop.from_camera)}: `), hop.reason || "faster than any vehicle could travel.")));
    }
  }
  const table = h("table", { class: "table timeline" },
    h("caption", { class: "sr-only" }, `Sightings of ${q} in time order`),
    h("thead", null, h("tr", null, ["#", "Time (IST)", "Camera", "Read as", "Match", "Confidence", "Gap", "Distance", "Speed", "Check"]
      .map((t) => h("th", { scope: "col" }, t)))),
    h("tbody", null, rows));
  return h("section", { class: "card", "aria-labelledby": "h-timeline" },
    h("div", { class: "card-head" }, h("h2", { id: "h-timeline" }, "Timeline"),
      h("span", { class: "small muted" }, "Match distance 0 = exact read; small values = the camera confused similar-looking characters.")),
    tableWrap(table));
}

function shortDur(sec) {
  const t = Math.round(Math.abs(sec || 0));
  if (t < 60) return `${t}s`;
  if (t < 3600) return `${Math.floor(t / 60)}m ${String(t % 60).padStart(2, "0")}s`;
  return `${Math.floor(t / 3600)}h ${String(Math.floor((t % 3600) / 60)).padStart(2, "0")}m`;
}

function confBar(label, v) {
  if (v === null || v === undefined) return null;
  const p = Math.round(v * 100);
  return h("div", { class: "conf" }, h("span", { class: "conf-l small" }, label),
    h("span", { class: "bar", role: "img", "aria-label": `${label} confidence ${p}%` }, h("span", { class: `bar-fill ${p < 60 ? "low" : ""}`, style: { width: `${p}%` } })),
    h("span", { class: "conf-v small mono" }, `${p}%`));
}

// ---------------------------------------------------------------- near misses
function nearMissPanel(res, { open }) {
  const list = res.near_misses || [];
  const q = res.query;
  if (!list.length) {
    return open ? notice("info", "No plate reads at all in this time window — nothing to compare against. Check the time window, or whether the cameras are reporting.") : h("span");
  }
  const table = h("table", { class: "table" },
    h("caption", { class: "sr-only" }, "Closest plate readings, ranked"),
    h("thead", null, h("tr", null, ["Rank", "Reading", "Distance", "Similarity", "Reads", "Cameras", "First / last seen", "Verdict", ""].map((t) => h("th", { scope: "col" }, t)))),
    h("tbody", null, list.map((m, i) => h("tr", null,
      h("td", { class: "num" }, String(i + 1)),
      h("td", null, h("span", { class: "read-as" }, plateDiff(m.reading, q).el), m.grammar_valid === false ? h("div", { class: "small muted" }, "not a valid plate format") : null),
      h("td", { class: "num mono" }, Number(m.distance).toFixed(2)),
      h("td", null, h("span", { class: "bar", role: "img", "aria-label": `similarity ${Math.round(m.similarity * 100)}%` },
        h("span", { class: "bar-fill", style: { width: `${Math.round(m.similarity * 100)}%` } })), h("span", { class: "small mono" }, ` ${Math.round(m.similarity * 100)}%`)),
      h("td", { class: "num" }, num(m.events)),
      h("td", { class: "small" }, (m.cameras || []).map((id) => camName(id)).join(", ")),
      h("td", { class: "small" }, fmtTime(m.first_ts), m.last_ts !== m.first_ts ? ` – ${fmtTime(m.last_ts)}` : ""),
      h("td", null, m.weak ? h("span", { class: "chip" }, "Weak — likely a different vehicle") : h("span", { class: "chip chip-warn" }, "Worth checking")),
      h("td", null, h("button", { type: "button", class: "btn small", onclick: () => { els.plate.value = m.reading; run(); } }, "Trace this"))))));
  const body = [
    h("p", { class: "small" }, "These are the closest readings the cameras made. None was close enough to count as this vehicle automatically — " +
      "a person should look at them before concluding the vehicle was not seen. Lower distance = closer."),
    tableWrap(table)];
  if (open) {
    return h("section", { class: "card", "aria-labelledby": "h-nm" }, h("div", { class: "card-head" }, h("h2", { id: "h-nm" }, "Closest readings (ranked)")), ...body);
  }
  return h("details", { class: "card near-miss" }, h("summary", null, h("strong", null, `Other close readings not on this route (${list.length})`)), ...body);
}

// ---------------------------------------------------------------- map drawing
function drawRoute(res) {
  if (!hasLeaflet()) {
    clear(els.mapBox, notice("error", "The map library didn't load — the timeline below has the full route."));
    return;
  }
  const L = window.L;
  if (map) { map.remove(); map = null; }
  map = createMap(els.mapBox);
  routeLayer = L.layerGroup().addTo(map);
  stopMarkers = new Map();
  const pts = res.sightings.filter((x) => x.camera && x.camera.lat !== null && x.camera.lat !== undefined && x.camera.lon !== null);

  // Hops (drawn first, under the markers).
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    const hop = b.hop || {};
    const bad = hop.plausible === false;
    const A = [a.camera.lat, a.camera.lon], B = [b.camera.lat, b.camera.lon];
    const line = L.polyline([A, B], bad
      ? { color: "#dc2626", weight: 5, dashArray: "10 9", opacity: 0.95 }
      : { color: "#2563eb", weight: 5, opacity: 0.9 }).addTo(routeLayer);
    line.bindTooltip(bad
      ? `Stop ${a.seq} → ${b.seq}: IMPOSSIBLE — ${num(hop.speed_kmh)} km/h`
      : `Stop ${a.seq} → ${b.seq}: ${num(hop.distance_km, 1)} km in ${duration(hop.gap_s)} (${num(hop.speed_kmh)} km/h)`,
    { sticky: true, className: bad ? "tt-bad" : "" });
    if (A[0] === B[0] && A[1] === B[1]) continue;
    const mid = [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2];
    const ang = screenAngle(map, A, B);
    L.marker(mid, {
      interactive: false, keyboard: false,
      icon: L.divIcon({ className: `route-arrow ${bad ? "bad" : ""}`, iconSize: [22, 22], iconAnchor: [11, 11],
        html: `<svg viewBox="0 0 22 22" style="transform:rotate(${ang}deg)" aria-hidden="true"><path d="M4 4 L19 11 L4 18 L8 11 Z"/></svg>` }),
    }).addTo(routeLayer);
    if (bad) {
      L.marker(mid, {
        interactive: false, keyboard: false,
        icon: L.divIcon({ className: "hop-flag", iconSize: null, iconAnchor: [-14, 12],
          html: `<span>IMPOSSIBLE · ${num(hop.speed_kmh)} km/h</span>` }),
      }).addTo(routeLayer);
    }
  }

  // Stops: one marker per camera location, labelled with every stop number there.
  const byLoc = new Map();
  for (const x of pts) {
    const key = `${x.camera.lat},${x.camera.lon}`;
    if (!byLoc.has(key)) byLoc.set(key, []);
    byLoc.get(key).push(x);
  }
  const firstSeq = pts.length ? pts[0].seq : null, lastSeq = pts.length ? pts[pts.length - 1].seq : null;
  for (const group of byLoc.values()) {
    const x0 = group[0];
    const seqs = group.map((g) => g.seq);
    const bad = group.some((g) => g.hop && g.hop.plausible === false);
    const cls = ["stop-marker", bad ? "bad" : "", seqs.includes(firstSeq) ? "first" : "", seqs.includes(lastSeq) ? "last" : ""].join(" ");
    const label = seqs.join(",");
    const w = Math.max(30, 14 + label.length * 9);
    const m = L.marker([x0.camera.lat, x0.camera.lon], {
      keyboard: true, title: `Stop ${label}: ${x0.camera.name || x0.camera.id}`, zIndexOffset: 1000,
      icon: L.divIcon({ className: cls, iconSize: [w, 30], iconAnchor: [w / 2, 15], html: `<span>${label}</span>` }),
    }).addTo(routeLayer);
    const tip = h("div", { class: "stop-tip" },
      h("strong", null, x0.camera.name || x0.camera.id),
      group.map((g) => h("div", { class: "small" }, `#${g.seq} · ${fmtTime(g.ts)} IST · read ${g.observed}`)),
      seqs.includes(firstSeq) ? h("div", { class: "small" }, "First sighting") : null,
      seqs.includes(lastSeq) ? h("div", { class: "small" }, "Last sighting") : null);
    m.bindTooltip(tip, { direction: "top", offset: [0, -14] });
    m.on("click", () => highlightRow(seqs[0]));
    for (const s of seqs) stopMarkers.set(s, m);
  }
  refreshSize(map);
  setTimeout(() => fitRoute("all"), 60);
}

/** "all": every stop. "main": the longest run of stops joined only by plausible hops. */
function fitRoute(mode = "all") {
  if (!map || !last) return;
  const L = window.L;
  let list = (last.sightings || []).filter((x) => x.camera && x.camera.lat !== null && x.camera.lat !== undefined);
  if (mode === "main") {
    let best = [], cur = [];
    for (const x of list) {
      if (x.hop && x.hop.plausible === false) cur = [];
      cur.push(x);
      if (cur.length > best.length) best = cur.slice();
    }
    list = best;
  }
  const pts = list.map((x) => [x.camera.lat, x.camera.lon]);
  map.invalidateSize();
  if (pts.length === 1) map.setView(pts[0], 14);
  else if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.12));
}

function focusStop(seq) {
  const m = stopMarkers.get(seq);
  if (!m || !map) return;
  map.setView(m.getLatLng(), Math.max(map.getZoom(), 13));
  m.openTooltip();
  els.mapBox.scrollIntoView({ behavior: "smooth", block: "center" });
}

function highlightRow(seq) {
  const row = document.getElementById(`stop-${seq}`);
  if (!row) return;
  for (const r of row.parentNode.querySelectorAll(".row-hl")) r.classList.remove("row-hl");
  row.classList.add("row-hl");
  row.scrollIntoView({ behavior: "smooth", block: "center" });
  row.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- lifecycle
function show(params) {
  purpose.refresh();
  refreshSize(map);
  const plate = params && params.get("plate");
  if (plate && normPlate(plate) !== (last && normPlate(last.query))) {
    els.plate.value = normPlate(plate);
    if (session.get("prahari.purpose") && session.get("prahari.case_id")) run();
    else {
      clear(els.out, notice("info", `Ready to trace ${fmtPlate(plate)} — fill in the purpose and case number above, then press “Trace route”.`));
      purpose.read();
    }
  } else if (!last && !els.out.childElementCount) {
    clear(els.out, h("div", { class: "empty-hero" },
      icon("trace"),
      h("p", null, "Enter a plate above to see every camera that read it, the route between them, and any sighting that doesn't add up.")));
    els.plate.focus({ preventScroll: true });
  }
}

export default { id: "trace", title: "Trace", icon: "trace", init, show };
