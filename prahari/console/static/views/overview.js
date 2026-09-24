// Overview — the headline numbers, system health and the latest alerts.

import { get, cameras } from "../api.js";
import { h, clear, num, ago, fmtTime, todayIST, camState, stateShape, errorBox, loading, empty, notice, icon } from "../ui.js";
import { alertCard } from "./alerts.js";

let root, ctx, timer = null, els = {};

function stat(label, { href, hint } = {}) {
  const value = h("div", { class: "stat-value" }, "…");
  const sub = h("div", { class: "stat-sub" }, hint || "");
  const inner = [h("div", { class: "stat-label" }, label), value, sub];
  const card = href ? h("a", { class: "stat card", href }, inner) : h("div", { class: "stat card" }, inner);
  return { card, value, sub };
}

function init(r, c) {
  root = r; ctx = c;
  els.cams = stat("Cameras", { href: "#/registry" });
  els.live = stat("Live now", { href: "#/wall" });
  els.down = stat("Not reporting", { href: "#/registry" });
  els.reads = stat("Plate reads today", { href: "#/reports" });
  els.alerts = stat("Open alerts", { href: "#/alerts" });
  els.watch = stat("Watchlist", { href: "#/watchlist" });
  els.health = h("div", { class: "health-strip card", role: "group", "aria-label": "System health" }, loading("Checking system health…"));
  els.recent = h("div", { class: "recent-alerts" });
  els.attention = h("div");
  els.err = h("div");
  clear(root,
    h("div", { class: "view-head" },
      h("h1", { id: "h-overview" }, "Overview"),
      h("p", { class: "lede" }, "The state of every camera, alert and search, at a glance.")),
    els.err,
    h("div", { class: "stats" }, [els.cams, els.live, els.down, els.reads, els.alerts, els.watch].map((s) => s.card)),
    els.health,
    h("div", { class: "grid-2 wide-left" },
      h("section", { class: "card", "aria-labelledby": "h-recent" },
        h("div", { class: "card-head" }, h("h2", { id: "h-recent" }, "Latest alerts"), h("a", { href: "#/alerts" }, "All alerts →")),
        els.recent),
      h("section", { class: "card", "aria-labelledby": "h-attn" },
        h("div", { class: "card-head" }, h("h2", { id: "h-attn" }, "Cameras needing attention"), h("a", { href: "#/registry" }, "Registry →")),
        els.attention)));
  ctx.live.addEventListener("change", paintRecent);
}

function paintRecent() {
  if (!root || root.hidden) return;
  if (!ctx.live.loaded && ctx.live.loadError) {
    set(els.alerts, "—", "Unavailable");
    clear(els.recent, errorBox(ctx.live.loadError, () => ctx.live.resync()));
    return;
  }
  if (!ctx.live.loaded) { clear(els.recent, loading("Loading alerts…")); return; }
  const openAlerts = ctx.live.openCount("alert"), openReview = ctx.live.openCount("review");
  set(els.alerts, num(openAlerts + openReview), `${num(openAlerts)} alert${openAlerts === 1 ? "" : "s"} · ${num(openReview)} to review`);
  els.alerts.card.classList.toggle("stat-hot", openAlerts > 0);
  const list = ctx.live.sorted().slice(0, 5);
  if (!list.length) { clear(els.recent, empty("No alerts yet.", "Alerts appear here the moment a camera reads a watchlisted plate.")); return; }
  clear(els.recent, list.map((a) => alertCard(a, ctx, { compact: true })));
}

function set(s, value, sub) {
  s.value.textContent = value;
  if (sub !== undefined) s.sub.textContent = sub;
}

// "Plate reads today" pulls up to 5,000 events, so it refreshes once a minute, not every 15 s.
let readsAt = 0, readsCache = null;
function readsToday() {
  if (readsCache && Date.now() - readsAt < 60000) return readsCache;
  readsAt = Date.now();
  readsCache = get("/api/events", { from: `${todayIST()}T00:00:00+05:30`, limit: 5000 }, { timeout: 30000 })
    .catch((e) => { readsAt = 0; throw e; });
  return readsCache;
}

async function load() {
  const [health, cams, watch, reads] = await Promise.allSettled([
    get("/api/health"),
    cameras({ force: true }),
    get("/api/watchlist", { active: true }),
    readsToday(),
  ]);
  const firstErr = [health, cams, watch, reads].find((r) => r.status === "rejected");
  clear(els.err, firstErr ? errorBox(firstErr.reason, load) : null);

  if (cams.status === "fulfilled") {
    const list = cams.value;
    const counts = {};
    for (const c of list) { const k = camState(c).key; counts[k] = (counts[k] || 0) + 1; }
    const live = (counts.live || 0) + (counts.degraded || 0);
    const down = (counts.offline || 0) + (counts.stale || 0) + (counts.unknown || 0);
    const depts = new Set(list.map((c) => c.department).filter(Boolean)).size;
    set(els.cams, num(list.length), `${depts} department${depts === 1 ? "" : "s"}`);
    set(els.live, num(live), list.length ? `${Math.round((live / list.length) * 100)}% of cameras` : "No cameras yet");
    set(els.down, num(down), [counts.offline && `${counts.offline} offline`, counts.stale && `${counts.stale} stale`, counts.unknown && `${counts.unknown} never reported`].filter(Boolean).join(" · ") || "All reporting");
    els.down.card.classList.toggle("stat-warn", down > 0);
    const bad = list.filter((c) => ["offline", "stale", "unknown", "absent"].includes(camState(c).key));
    if (!list.length) clear(els.attention, empty("No cameras registered yet.", "Add them in Registry: sync a catalogue URL, import a CSV, or add one by hand."));
    else if (!bad.length) clear(els.attention, notice("ok", icon("check"), "Every camera is reporting."));
    else {
      clear(els.attention, h("ul", { class: "attn-list" }, bad.slice(0, 8).map((c) => {
        const st = camState(c);
        return h("li", null, h("button", { type: "button", class: "linkish", onclick: () => ctx.openCamera(c) },
          h("span", { class: `pill st-${st.key}` }, h("span", { class: "shape-wrap", html: stateShape(st.key) }), st.short), " ", c.name || c.id,
          h("span", { class: "muted small" }, ` · ${c.department || "—"} · last seen ${ago(c.last_seen)}`)));
      })), bad.length > 8 ? h("p", { class: "small muted" }, `…and ${bad.length - 8} more in the Registry.`) : null);
    }
  } else {
    for (const s of [els.cams, els.live, els.down]) set(s, "—", "Unavailable");
    clear(els.attention, errorBox(cams.reason, load));
  }

  if (watch.status === "fulfilled") set(els.watch, num(watch.value.count), "active entries");
  else set(els.watch, "—", "Unavailable");

  if (reads.status === "fulfilled") {
    const n = reads.value.count || 0;
    const last = (reads.value.events || [])[0];
    set(els.reads, n >= 5000 ? "5,000+" : num(n), last ? `latest ${fmtTime(last.ts)} IST` : "none since midnight IST");
  } else set(els.reads, "—", "Unavailable");

  if (health.status === "fulfilled") {
    const d = health.value;
    const item = (label, value, ok = true) =>
      h("div", { class: `hs-item ${ok ? "" : "hs-bad"}` }, h("span", { class: "hs-label" }, label),
        h("span", { class: "hs-value" }, ok ? null : icon("warn"), value));
    clear(els.health,
      h("strong", { class: "hs-title" }, "System health"),
      item("Server", d.status === "ok" ? "Running" : d.status, d.status === "ok"),
      item("Version", d.version),
      item("Database", `${num((d.db_bytes || 0) / 1048576, 1)} MB`),
      item("Disk free", `${num((d.disk_free_mb || 0) / 1024, 1)} GB`, d.disk_ok !== false),
      item("Plate reads stored", num(d.counts?.plate_events)),
      item("Audit entries", num(d.counts?.audit_log)),
      item("Consoles watching live", num(d.live_subscribers)));
  } else clear(els.health, errorBox(health.reason, load));
  paintRecent();
}

function show() {
  load();
  paintRecent();
  clearInterval(timer);
  timer = setInterval(() => { if (!document.hidden) load(); }, 15000);
}

function hide() {
  clearInterval(timer);
  timer = null;
}

export default { id: "overview", title: "Overview", icon: "overview", init, show, hide, refresh: load };
