// Registry — the camera table, the three onboarding paths, and the coverage-gap report.

import { get, post, request, cameras, invalidateCameras, buildUrl } from "../api.js";
import {
  h, clear, icon, ago, camState, statePill, errorBox, loading, empty, num, notice, tableWrap, busy,
  csvInput, resultSummary, STATE_NAMES,
} from "../ui.js";

let root, ctx, els = {};
let camList = [];
const filt = { q: "", dept: "", state: "" };

const CAMERA_TEMPLATE =
  "camera_id,name,department,latitude,longitude,codec,resolution,fps,rtsp,hls\n" +
  "PS-01,Sector 7 gate,Police,23.2156,72.6369,H.264,1280x720,25,rtsp://10.1.1.5:554/live,\n" +
  "AMC-014,Navrangpura crossroads,Municipal,23.0395,72.5660,H.265,1920x1080,25,rtsp://10.0.4.14:554/stream1,\n";

function init(r, c) {
  root = r; ctx = c;
  els.q = h("input", { id: "rg-q", type: "search", placeholder: "Name or id", autocomplete: "off" });
  els.dept = h("select", { id: "rg-dept" }, h("option", { value: "" }, "All departments"));
  els.state = h("select", { id: "rg-state" }, h("option", { value: "" }, "Any status"),
    Object.entries(STATE_NAMES).map(([k, v]) => h("option", { value: k }, v)));
  els.count = h("span", { class: "muted", "aria-live": "polite" });
  els.table = h("div");
  els.q.addEventListener("input", () => { filt.q = els.q.value.trim().toLowerCase(); paintTable(); });
  els.dept.addEventListener("change", () => { filt.dept = els.dept.value; paintTable(); });
  els.state.addEventListener("change", () => { filt.state = els.state.value; paintTable(); });
  els.deptList = h("datalist", { id: "rg-depts" });
  els.gaps = h("div");

  clear(root,
    h("div", { class: "view-head" },
      h("h1", { id: "h-registry" }, "Camera registry"),
      h("p", { class: "lede" }, "Every camera from every department, in one list. Add cameras three ways below.")),
    h("section", { class: "card", "aria-labelledby": "h-cams" },
      h("div", { class: "card-head" }, h("h2", { id: "h-cams" }, "Cameras"), els.count),
      h("div", { class: "toolbar" },
        h("div", { class: "field inline" }, h("label", { for: "rg-q" }, "Search"), els.q),
        h("div", { class: "field inline" }, h("label", { for: "rg-dept" }, "Department"), els.dept),
        h("div", { class: "field inline" }, h("label", { for: "rg-state" }, "Status"), els.state)),
      els.table),
    h("h2", { class: "section-title", id: "h-onboard" }, "Add cameras"),
    h("div", { class: "onboard-grid" }, syncCard(), csvCard(), manualCard()),
    els.deptList,
    h("section", { class: "card", id: "gaps", "aria-labelledby": "h-gaps" },
      h("div", { class: "card-head" }, h("h2", { id: "h-gaps" }, "Coverage gaps"),
        h("div", { class: "row gap" },
          h("a", { class: "btn small", href: "#/map?gaps=1" }, icon("map"), "Show on map"),
          h("a", { class: "btn small ghost", href: buildUrl("/api/reports/gap", { format: "md" }), download: "prahari_gap_report.md" }, icon("download"), "Download report"))),
      els.gaps));
}

// ---------------------------------------------------------------- table
function paintTable() {
  const list = camList.filter((c) => {
    if (filt.dept && c.department !== filt.dept) return false;
    if (filt.state && camState(c).key !== filt.state) return false;
    if (filt.q && !`${c.name} ${c.id}`.toLowerCase().includes(filt.q)) return false;
    return true;
  });
  els.count.textContent = `${num(list.length)} of ${num(camList.length)} shown`;
  if (!camList.length) { clear(els.table, empty("No cameras registered yet.", "Use one of the three forms below to add them.")); return; }
  if (!list.length) { clear(els.table, empty("No cameras match these filters.")); return; }
  const srcName = { catalogue: "Catalogue", bulk: "CSV import", manual: "By hand", api: "API" };
  const table = h("table", { class: "table registry-table" },
    h("caption", { class: "sr-only" }, "Registered cameras"),
    h("thead", null, h("tr", null, ["Status", "Camera", "Department", "Added via", "Video", "Location", "Last seen", "Streams", ""].map((t) => h("th", { scope: "col" }, t)))),
    h("tbody", null, list.slice(0, 1000).map((c) => {
      const streams = [c.rtsp_url && "RTSP", c.hls_url && "HLS", c.whep_url && "WebRTC"].filter(Boolean);
      const cap = c.capability || {};
      return h("tr", null,
        h("td", null, statePill(c)),
        h("td", null, h("strong", null, c.name || "—"), h("div", { class: "small muted mono" }, c.id)),
        h("td", null, c.department || "—"),
        h("td", null, srcName[c.source] || c.source || "—"),
        h("td", { class: "small" }, [c.codec && c.codec.toUpperCase(), c.width && c.height ? `${c.width}×${c.height}` : null, c.fps ? `${c.fps} fps` : null].filter(Boolean).join(" · ") || "—",
          cap.anpr_viable === false ? h("div", { class: "warn-text" }, "Can't read plates") : null),
        h("td", { class: "small mono" }, c.lat !== null && c.lat !== undefined ? `${Number(c.lat).toFixed(4)}, ${Number(c.lon).toFixed(4)}` : h("span", { class: "warn-text" }, "missing")),
        h("td", { class: "small" }, c.last_seen ? ago(c.last_seen) : "never"),
        h("td", { class: "small" }, streams.length ? streams.join(", ") : h("span", { class: "muted" }, "none")),
        h("td", null, h("button", { type: "button", class: "btn small ghost", onclick: () => ctx.openCamera(c), "aria-label": `Details for ${c.name || c.id}` }, "Details")));
    })));
  const wrap = tableWrap(table);
  wrap.classList.add("scroll-limit");
  clear(els.table, wrap, list.length > 1000 ? h("p", { class: "small muted" }, "Showing the first 1,000 — narrow the search.") : null);
}

async function loadCams(force = true) {
  if (!camList.length) clear(els.table, loading("Loading cameras…"));
  try {
    camList = await cameras({ force });
    const depts = [...new Set(camList.map((c) => c.department).filter(Boolean))].sort();
    const cur = els.dept.value;
    clear(els.dept, h("option", { value: "" }, "All departments"), depts.map((d) => h("option", { value: d }, d)));
    els.dept.value = depts.includes(cur) ? cur : "";
    filt.dept = els.dept.value;
    clear(els.deptList, depts.map((d) => h("option", { value: d })));
    paintTable();
  } catch (e) {
    clear(els.table, errorBox(e, () => loadCams(true)));
  }
}

async function afterChange() {
  invalidateCameras();
  await loadCams(true);
  loadGaps();
}

// ---------------------------------------------------------------- onboarding cards
function onboardCard(n, title, lede, ...body) {
  return h("section", { class: "card onboard", "aria-labelledby": `h-ob-${n}` },
    h("div", { class: "onboard-num", "aria-hidden": "true" }, String(n)),
    h("h3", { id: `h-ob-${n}` }, title), h("p", { class: "small muted" }, lede), ...body);
}

function syncCard() {
  const url = h("input", { id: "ob-url", type: "url", placeholder: "http://…/api/ingest", autocomplete: "url" });
  const paste = h("textarea", { id: "ob-json", class: "mono", rows: 4, spellcheck: "false", placeholder: '[{"id":"CAM-1","name":"…","lat":23.0,"lon":72.5,"rtsp":"rtsp://…"}]' });
  const out = h("div", { "aria-live": "polite" });
  const btn = h("button", { type: "submit", class: "btn primary" }, "Sync now");
  const form = h("form", { novalidate: true },
    h("div", { class: "field" }, h("label", { for: "ob-url" }, "Catalogue URL"), url),
    h("details", null, h("summary", { class: "small" }, "No network? Paste the catalogue JSON instead"),
      h("div", { class: "field" }, h("label", { for: "ob-json" }, "Catalogue JSON"), paste)),
    btn, out);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const body = {};
    if (paste.value.trim()) {
      try { body.payload = JSON.parse(paste.value); } catch (ex) { clear(out, notice("error", `That JSON doesn't parse: ${ex.message}`)); return; }
    } else if (url.value.trim()) body.url = url.value.trim();
    else { clear(out, notice("error", "Enter the catalogue URL (or paste the JSON).")); url.focus(); return; }
    busy(btn, "Syncing…", async () => {
      clear(out, loading("Fetching the catalogue…"));
      try {
        const res = await post("/api/cameras/sync", body, { timeout: 90000 });
        clear(out, notice("ok", icon("check"), h("strong", null, "Catalogue synced.")), resultSummary(res));
        afterChange();
      } catch (ex) {
        if (ex.status === 502) {
          clear(out, notice("error", icon("warn"), h("div", null,
            h("strong", null, "Couldn't fetch the catalogue from that URL."),
            h("div", { class: "small" }, "Check the address, and that the catalogue service is reachable from the machine running PRAHARI."),
            h("div", { class: "small muted" }, `Details: ${ex.message}`))));
        } else clear(out, errorBox(ex));
      }
    });
  });
  return onboardCard(1, "Sync from catalogue URL", "Pulls the department's camera list. Safe to repeat: existing cameras are updated, vanished ones are marked absent (never deleted).", form);
}

function csvCard() {
  const csv = csvInput({ template: CAMERA_TEMPLATE, templateName: "prahari_cameras_template.csv", label: "camera rows" });
  const out = h("div", { "aria-live": "polite" });
  const btn = h("button", { type: "submit", class: "btn primary" }, "Import cameras");
  const form = h("form", { novalidate: true }, csv.el, btn, out);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = csv.text().trim();
    if (!text) { clear(out, notice("error", "Choose a CSV file or paste rows first.")); return; }
    busy(btn, "Importing…", async () => {
      clear(out, loading("Importing…"));
      try {
        const res = await request("/api/cameras/import", { method: "POST", body: text + "\n", contentType: "text/csv", timeout: 90000 });
        clear(out, notice(res.skipped && res.skipped.length ? "warn" : "ok", icon("check"), h("strong", null, `Imported ${res.parsed} row(s).`)), resultSummary(res));
        afterChange();
      } catch (ex) { clear(out, errorBox(ex)); }
    });
  });
  return onboardCard(2, "Import CSV", "One row per camera. Column names are flexible (id / camera_id, lat / latitude, rtsp / rtsp_url…).", form);
}

function manualCard() {
  const f = (id, label, input, hint) => h("div", { class: "field" }, h("label", { for: id }, label), input, hint ? h("span", { class: "small muted" }, hint) : null);
  const i = {
    id: h("input", { id: "mc-id", type: "text", required: true, autocomplete: "off", placeholder: "e.g. AMC-NAV-014" }),
    name: h("input", { id: "mc-name", type: "text", autocomplete: "off", placeholder: "e.g. Navrangpura crossroads (north)" }),
    department: h("input", { id: "mc-dept", type: "text", list: "rg-depts", autocomplete: "off", placeholder: "e.g. Police" }),
    lat: h("input", { id: "mc-lat", type: "number", step: "any", min: -90, max: 90, placeholder: "23.0395" }),
    lon: h("input", { id: "mc-lon", type: "number", step: "any", min: -180, max: 180, placeholder: "72.5660" }),
    codec: h("select", { id: "mc-codec" }, [["", "Unknown"], ["h264", "H.264"], ["h265", "H.265 / HEVC"], ["mjpeg", "MJPEG"]].map(([v, t]) => h("option", { value: v }, t))),
    width: h("input", { id: "mc-w", type: "number", min: 1, step: 1, placeholder: "1920" }),
    height: h("input", { id: "mc-h", type: "number", min: 1, step: 1, placeholder: "1080" }),
    fps: h("input", { id: "mc-fps", type: "number", min: 0, step: "any", placeholder: "25" }),
    rtsp_url: h("input", { id: "mc-rtsp", type: "text", autocomplete: "off", placeholder: "rtsp://10.0.4.14:554/stream1" }),
    hls_url: h("input", { id: "mc-hls", type: "text", autocomplete: "off", placeholder: "http://…/index.m3u8" }),
    live: h("input", { id: "mc-live", type: "checkbox", checked: true }),
  };
  const out = h("div", { "aria-live": "polite" });
  const btn = h("button", { type: "submit", class: "btn primary" }, "Add camera");
  const form = h("form", { novalidate: true },
    h("div", { class: "form-grid" },
      f("mc-id", "Camera id (required)", i.id), f("mc-name", "Name", i.name), f("mc-dept", "Department", i.department),
      f("mc-lat", "Latitude", i.lat), f("mc-lon", "Longitude", i.lon), f("mc-codec", "Codec", i.codec),
      f("mc-w", "Width (px)", i.width), f("mc-h", "Height (px)", i.height), f("mc-fps", "Frame rate", i.fps)),
    f("mc-rtsp", "RTSP URL", i.rtsp_url), f("mc-hls", "HLS URL", i.hls_url),
    h("label", { class: "check", for: "mc-live" }, i.live, "Live stream (not a recording)"),
    btn, out);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const id = i.id.value.trim();
    if (!id) { clear(out, notice("error", "A camera id is required.")); i.id.focus(); return; }
    const numOrNull = (el) => (el.value.trim() === "" ? null : Number(el.value));
    const lat = numOrNull(i.lat), lon = numOrNull(i.lon);
    if ((lat === null) !== (lon === null)) { clear(out, notice("error", "Give both latitude and longitude, or neither.")); return; }
    if (lat !== null && (Number.isNaN(lat) || lat < -90 || lat > 90)) { clear(out, notice("error", "Latitude must be between -90 and 90.")); i.lat.focus(); return; }
    if (lon !== null && (Number.isNaN(lon) || lon < -180 || lon > 180)) { clear(out, notice("error", "Longitude must be between -180 and 180.")); i.lon.focus(); return; }
    const body = {
      id, name: i.name.value.trim(), department: i.department.value.trim(), lat, lon, codec: i.codec.value,
      width: numOrNull(i.width), height: numOrNull(i.height), fps: numOrNull(i.fps), live: i.live.checked,
      rtsp_url: i.rtsp_url.value.trim(), hls_url: i.hls_url.value.trim(),
    };
    busy(btn, "Saving…", async () => {
      try {
        const res = await post("/api/cameras", body);
        const was = res.updated && res.updated.includes(id) ? "updated" : "added";
        clear(out, notice("ok", icon("check"), `Camera ${id} ${was}.`,
          lat === null ? h("div", { class: "small" }, "It has no location, so it won't appear on the map yet.") : null));
        form.reset();
        i.live.checked = true;
        afterChange();
      } catch (ex) { clear(out, errorBox(ex)); }
    });
  });
  return onboardCard(3, "Add one camera", "For a single new camera. Adding an existing id updates it.", form);
}

// ---------------------------------------------------------------- gap report
async function loadGaps() {
  clear(els.gaps, loading("Analysing coverage…"));
  let r;
  try { r = await get("/api/reports/gap", { format: "json" }, { timeout: 60000 }); }
  catch (e) { clear(els.gaps, errorBox(e, loadGaps)); return; }
  const t = r.totals || {}, cov = r.coverage || {};
  const tile = (label, value, bad) => h("div", { class: `mini-stat ${bad ? "bad" : ""}` }, h("span", { class: "mini-v" }, value), h("span", { class: "mini-l" }, label));
  const tiles = h("div", { class: "mini-stats" },
    tile("Area covered", `${num(cov.coverage_pct, 1)}%`),
    tile("Covered by healthy cameras", `${num(cov.effective_coverage_pct, 1)}%`),
    tile("Healthy", num(t.healthy)),
    tile("Offline", num(t.offline), t.offline > 0),
    tile("Stale (no recent signal)", num(t.stale), t.stale > 0),
    tile("Never reported", num(t.never_seen), t.never_seen > 0),
    tile("Not in catalogue", num(t.absent), t.absent > 0),
    tile("Can't read plates", num(t.anpr_unviable), t.anpr_unviable > 0),
    tile("No location", num(t.without_location), t.without_location > 0),
    tile("No stream link", num(t.without_stream_url), t.without_stream_url > 0));
  const explain = h("p", { class: "small muted" },
    `The area around the cameras is split into ${num(cov.cells)} ${cov.cells === 1 ? "cell" : "cells"} of ${cov.cell_km ?? 1} km. A cell is covered if a camera is within ${cov.radius_km ?? 1} km. ` +
    `${num(cov.uncovered)} cells have no camera nearby. Generated ${r.generated_at ? r.generated_at.replace("T", " ").slice(0, 19) : "now"} IST.`);

  const depts = Object.entries(r.by_department || {});
  const deptTable = depts.length ? tableWrap(h("table", { class: "table compact" },
    h("caption", null, "By department"),
    h("thead", null, h("tr", null, ["Department", "Cameras", "Located", "Healthy", "Offline / stale", "Can't read plates"].map((x) => h("th", { scope: "col" }, x)))),
    h("tbody", null, depts.map(([d, v]) => h("tr", null, h("td", null, d), h("td", { class: "num" }, num(v.total)), h("td", { class: "num" }, num(v.located)),
      h("td", { class: "num" }, num(v.healthy)), h("td", { class: `num ${v.offline_or_stale ? "warn-text" : ""}` }, num(v.offline_or_stale)),
      h("td", { class: `num ${v.anpr_unviable ? "warn-text" : ""}` }, num(v.anpr_unviable))))))) : null;

  const listBlock = (title, arr, extra) => {
    if (!arr || !arr.length) return null;
    return h("details", { class: "gap-list" }, h("summary", null, `${title} (${arr.length})`),
      h("ul", null, arr.slice(0, 100).map((c) => h("li", null,
        h("button", { type: "button", class: "linkish", onclick: () => { const cam = camList.find((x) => x.id === c.id); if (cam) ctx.openCamera(cam); } }, c.name || c.id),
        h("span", { class: "muted small" }, ` · ${c.id} · ${c.department || "—"}${extra ? ` · ${extra(c)}` : ""}`)))));
  };
  clear(els.gaps, tiles, explain, deptTable,
    listBlock("Offline", r.offline, (c) => `last seen ${c.last_seen ? c.last_seen.replace("T", " ").slice(0, 16) : "never"}`),
    listBlock("Stale — no signal recently", r.stale, (c) => `silent ${Math.round((c.age_s || 0) / 60)} min`),
    listBlock("Never reported", r.never_seen),
    listBlock("No longer in the catalogue", r.absent),
    listBlock("Camera can't read plates", r.anpr_unviable, (c) => c.reason || "capability check"),
    listBlock("No location (not on the map)", r.without_location),
    listBlock("No stream link", r.without_stream_url));
}

function show(params) {
  loadCams(true);
  loadGaps();
  if (params && params.get("panel") === "gaps") setTimeout(() => document.getElementById("gaps")?.scrollIntoView({ behavior: "smooth" }), 100);
}

export default { id: "registry", title: "Registry", icon: "registry", init, show, refresh: () => { loadCams(true); loadGaps(); } };
