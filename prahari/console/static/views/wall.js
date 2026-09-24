// Wall — every camera as a tile with its latest picture (refreshed ~2 s, only while visible).

import { cameras, prefs } from "../api.js";
import { h, clear, icon, ago, camState, stateShape, errorBox, loading, empty, num, STATE_NAMES } from "../ui.js";
import { fetchSnapshot, mayFetch, snapshotEndpoint } from "../snapshots.js";

const REFRESH_MS = 2000;
const MAX_INFLIGHT = 4; // browsers allow ~6 connections per host; leave room for the API + live feed

let root, ctx, els = {};
let tiles = new Map(); // id -> tile state
let visible = new Set(); // ids currently in the viewport
let io = null, ticker = null, listTimer = null, ageTimer = null;
let inflight = 0;
let ioLive = false; // IntersectionObserver has delivered at least once (it doesn't in never-rendered tabs)
let cams = [];
const filt = { q: "", dept: "", state: "" };

function init(r, c) {
  root = r; ctx = c;
  const uid = "wall";
  els.q = h("input", { id: `${uid}-q`, type: "search", placeholder: "Name or id", autocomplete: "off" });
  els.dept = h("select", { id: `${uid}-dept` }, h("option", { value: "" }, "All departments"));
  els.state = h("select", { id: `${uid}-state` }, h("option", { value: "" }, "Any status"),
    h("option", { value: "live" }, "Live"), h("option", { value: "problem" }, "Not reporting (offline / stale / never)"),
    Object.entries(STATE_NAMES).map(([k, v]) => h("option", { value: k }, v)));
  els.count = h("span", { class: "muted", "aria-live": "polite" });
  els.snapNote = h("div", { class: "notice notice-info small", hidden: true, role: "status" },
    "Camera pictures appear here automatically once the capture service starts sending frames. Status and last-seen times are live now.");
  els.grid = h("div", { class: "wall-grid" });
  els.status = h("div");

  const size = prefs.get("prahari.wallSize", "m");
  const sizeSeg = h("div", { class: "seg", role: "group", "aria-label": "Tile size" },
    [["s", "Small"], ["m", "Medium"], ["l", "Large"]].map(([v, label]) => {
      const b = h("button", { type: "button", class: "seg-btn", "aria-pressed": String(size === v), onclick: () => {
        prefs.set("prahari.wallSize", v);
        els.grid.dataset.size = v;
        for (const x of b.parentNode.children) x.setAttribute("aria-pressed", String(x === b));
      } }, label);
      return b;
    }));
  els.grid.dataset.size = size;

  els.q.addEventListener("input", () => { filt.q = els.q.value.trim().toLowerCase(); paint(); });
  els.dept.addEventListener("change", () => { filt.dept = els.dept.value; paint(); });
  els.state.addEventListener("change", () => { filt.state = els.state.value; paint(); });

  clear(root,
    h("div", { class: "view-head" },
      h("h1", { id: "h-wall" }, "Camera wall"),
      h("p", { class: "lede" }, "Latest picture from every camera. Click a tile for details and stream links.")),
    h("div", { class: "toolbar" },
      h("div", { class: "field inline" }, h("label", { for: els.q.id }, "Search"), els.q),
      h("div", { class: "field inline" }, h("label", { for: els.dept.id }, "Department"), els.dept),
      h("div", { class: "field inline" }, h("label", { for: els.state.id }, "Status"), els.state),
      sizeSeg, els.count),
    els.snapNote, els.status, els.grid);

  io = new IntersectionObserver((entries) => {
    ioLive = true;
    for (const e of entries) {
      const id = e.target.dataset.id;
      if (e.isIntersecting) visible.add(id);
      else visible.delete(id);
    }
  }, { rootMargin: "150px" });
}

function makeTile(c) {
  const img = h("img", { alt: "", hidden: true, decoding: "async" });
  const phText = h("span", { class: "ph-text" }, "No picture yet");
  const ph = h("div", { class: "snap-ph" }, icon("camera"), phText);
  const badge = h("span", { class: "snap-badge" });
  const name = h("span", { class: "tile-name" });
  const meta = h("span", { class: "tile-meta" });
  const pill = h("span", { class: "pill" });
  const age = h("span", { class: "tile-age" });
  const el = h("button", { type: "button", class: "tile", dataset: { id: c.id }, onclick: () => ctx.openCamera(t.cam) },
    h("span", { class: "snap" }, img, ph, badge),
    h("span", { class: "tile-cap" }, name, meta, h("span", { class: "tile-status" }, pill, age)));
  const t = { id: c.id, cam: c, el, img, ph, phText, badge, name, meta, pill, age, url: null, nextAt: 0, fails: 0, busy: false };
  io.observe(el);
  return t;
}

function paintTile(t) {
  const c = t.cam;
  const st = camState(c);
  t.el.className = `tile st-${st.key}`;
  t.el.setAttribute("aria-label", `${c.name || c.id}, ${c.department || "no department"}, ${st.label}, last seen ${ago(c.last_seen)}. Open details.`);
  t.name.textContent = c.name || c.id;
  t.meta.textContent = `${c.department || "—"} · ${c.id}`;
  t.pill.className = `pill st-${st.key}`;
  t.pill.replaceChildren(h("span", { class: "shape-wrap", html: stateShape(st.key) }), st.short);
  t.age.textContent = c.last_seen ? `seen ${ago(c.last_seen)}` : "never seen";
  if (!t.url) t.phText.textContent = st.key === "offline" ? "Camera offline" : st.key === "absent" ? "Removed from catalogue" : "No picture yet";
}

function matches(c) {
  const st = camState(c).key;
  if (filt.dept && (c.department || "") !== filt.dept) return false;
  if (filt.state === "problem") { if (!["offline", "stale", "unknown", "absent"].includes(st)) return false; }
  else if (filt.state === "live") { if (!(st === "live" || st === "degraded")) return false; }
  else if (filt.state && st !== filt.state) return false;
  if (filt.q && !`${c.name} ${c.id}`.toLowerCase().includes(filt.q)) return false;
  return true;
}

function paint() {
  const shown = cams.filter(matches);
  els.count.textContent = `Showing ${num(shown.length)} of ${num(cams.length)}`;
  const seen = new Set();
  const order = [];
  for (const c of shown) {
    let t = tiles.get(c.id);
    if (!t) { t = makeTile(c); tiles.set(c.id, t); }
    t.cam = c;
    paintTile(t);
    seen.add(c.id);
    order.push(t.el);
  }
  // Drop tiles for cameras that are gone or filtered out.
  for (const [id, t] of tiles) {
    if (!seen.has(id)) {
      io.unobserve(t.el);
      visible.delete(id);
      if (t.url) URL.revokeObjectURL(t.url);
      tiles.delete(id);
    }
  }
  const same = order.length === els.grid.children.length && order.every((el, i) => els.grid.children[i] === el);
  if (!same) els.grid.replaceChildren(...order);
  if (!cams.length) clear(els.status, empty("No cameras registered yet.", "Add cameras in Registry — sync a catalogue URL, import a CSV, or add one by hand."));
  else if (!shown.length) clear(els.status, empty("No cameras match these filters."));
  else clear(els.status);
}

async function loadList(force = false) {
  try {
    cams = await cameras({ force });
    const depts = [...new Set(cams.map((c) => c.department).filter(Boolean))].sort();
    const cur = filt.dept;
    clear(els.dept, h("option", { value: "" }, "All departments"), depts.map((d) => h("option", { value: d }, d)));
    els.dept.value = depts.includes(cur) ? cur : "";
    filt.dept = els.dept.value;
    paint();
  } catch (e) {
    if (!cams.length) { els.grid.replaceChildren(); clear(els.status, errorBox(e, () => loadList(true))); }
    else clear(els.status, errorBox(e));
  }
}

async function refreshTile(t, index, total) {
  if (!mayFetch(index, total)) return;
  t.busy = true;
  inflight++;
  const r = await fetchSnapshot(t.id);
  inflight--;
  t.busy = false;
  if (!tiles.has(t.id)) { if (r.ok) URL.revokeObjectURL(r.url); return; }
  const now = Date.now();
  if (r.ok) {
    if (t.url) URL.revokeObjectURL(t.url);
    t.url = r.url;
    t.img.src = r.url;
    t.img.hidden = false;
    t.ph.hidden = true;
    t.fails = 0;
    t.nextAt = now + REFRESH_MS;
    t.badge.textContent = "";
  } else {
    t.fails++;
    t.nextAt = now + Math.min(REFRESH_MS * 2 ** Math.min(t.fails, 4), 30000);
    if (t.url) t.badge.textContent = "picture not updating";
    else t.phText.textContent = r.reason === "network" ? "Can't reach server" : camState(t.cam).key === "offline" ? "Camera offline" : "No picture yet";
  }
}

/** Fallback for the rare case the observer hasn't reported yet. */
function inViewport() {
  const hgt = window.innerHeight || document.documentElement.clientHeight;
  return [...tiles.values()].filter((t) => {
    const r = t.el.getBoundingClientRect();
    return r.bottom > -150 && r.top < hgt + 150 && r.width > 0;
  }).map((t) => t.id);
}

function tick() {
  // Only the wall's own visibility matters; hidden browser tabs are throttled by the browser anyway.
  if (root.hidden) return;
  els.snapNote.hidden = snapshotEndpoint() !== "absent";
  const now = Date.now();
  const ids = ioLive ? [...visible].filter((id) => tiles.has(id)) : inViewport();
  ids.forEach((id, i) => {
    const t = tiles.get(id);
    if (t.busy || now < t.nextAt || inflight >= MAX_INFLIGHT) return;
    refreshTile(t, i, ids.length);
  });
}

function show(params, { first } = {}) {
  if (params && params.get("dept")) { filt.dept = params.get("dept"); }
  if (first) clear(els.status, loading("Loading cameras…"));
  loadList(!first);
  clearInterval(ticker); clearInterval(listTimer); clearInterval(ageTimer);
  ticker = setInterval(tick, 500);
  listTimer = setInterval(() => { if (!document.hidden) loadList(true); }, 10000);
  ageTimer = setInterval(() => { for (const t of tiles.values()) paintTile(t); }, 5000);
}

function hide() {
  clearInterval(ticker); clearInterval(listTimer); clearInterval(ageTimer);
  ticker = listTimer = ageTimer = null;
}

export default { id: "wall", title: "Wall", icon: "wall", init, show, hide, refresh: () => loadList(true) };
