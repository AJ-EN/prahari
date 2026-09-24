// PRAHARI console — app shell: navigation, theme, server-health banner, live-alert toasts.

import { get, prefs, SERVER_DOWN } from "./api.js";
import { h, clear, icon, ICONS, fmtPlate, catLabel } from "./ui.js";
import { live, sound } from "./live.js";
import { openCamera } from "./camdetail.js";

import overview from "./views/overview.js";
import wall from "./views/wall.js";
import mapView from "./views/map.js";
import alerts from "./views/alerts.js";
import trace from "./views/trace.js";
import registry from "./views/registry.js";
import watchlist from "./views/watchlist.js";
import reports from "./views/reports.js";

const VIEWS = [overview, wall, mapView, alerts, trace, registry, watchlist, reports];
const byId = Object.fromEntries(VIEWS.map((v) => [v.id, v]));

const $ = (sel) => document.querySelector(sel);
const state = { current: null, roots: {}, inited: new Set() };

// ---------------------------------------------------------------- navigation
/** navigate("trace", {plate: "GJ01AB1234"}) */
function navigate(id, params) {
  const qs = params ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString() : "";
  const target = `#/${id}${qs ? `?${qs}` : ""}`;
  if (location.hash === target) route();
  else location.hash = target;
}

const ctx = {
  navigate,
  live,
  openCamera: (c) => openCamera(c, { onMap: (cam) => navigate("map", { focus: cam.id }) }),
};

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [id, qs] = raw.split("?");
  return { id: byId[id] ? id : "overview", params: new URLSearchParams(qs || "") };
}

function buildNav() {
  const nav = $("#nav");
  const list = h("ul", { class: "nav-list" });
  for (const v of VIEWS) {
    const badge = v.id === "alerts" ? h("span", { class: "nav-badge", id: "alert-badge", hidden: true }) : null;
    list.append(h("li", null,
      h("a", { href: `#/${v.id}`, class: "nav-link", dataset: { view: v.id } },
        h("span", { class: "ico-wrap", html: ICONS[v.icon] || "" }), h("span", { class: "nav-label" }, v.title), badge)));
  }
  nav.append(list, h("div", { class: "nav-foot small" }, "Sample data is marked SAMPLE."));
}

function route() {
  const { id, params } = parseHash();
  const view = byId[id];
  if (state.current && state.current !== view) {
    try { state.current.hide?.(); } catch (e) { reportError(e); }
    state.roots[state.current.id].hidden = true;
  }
  let root = state.roots[id];
  if (!root) {
    root = h("section", { class: "view", id: `view-${id}`, "aria-labelledby": `h-${id}` });
    state.roots[id] = root;
    $("#views").append(root);
  }
  root.hidden = false;
  for (const a of document.querySelectorAll(".nav-link")) {
    if (a.dataset.view === id) {
      a.setAttribute("aria-current", "page");
      // On narrow screens the nav is a horizontal strip: keep the current tab in sight.
      const nav = $("#nav");
      if (nav.scrollWidth > nav.clientWidth) nav.scrollLeft = Math.max(0, a.offsetLeft - nav.clientWidth / 2 + a.offsetWidth / 2);
    }
    else a.removeAttribute("aria-current");
  }
  document.title = `${view.title} · PRAHARI Console`;
  if (state.current !== view) window.scrollTo(0, 0);
  const first = !state.inited.has(id);
  state.current = view;
  try {
    if (first) {
      state.inited.add(id);
      view.init(root, ctx);
    }
    view.show?.(params, { first });
  } catch (e) {
    reportError(e);
    clear(root, h("div", { class: "state state-error" }, "This page failed to load. Please refresh the browser."));
  }
}

// ---------------------------------------------------------------- theme
const THEMES = ["auto", "light", "dark"];
function applyTheme(t) {
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  const btn = $("#theme-btn");
  const label = { auto: "Theme: match system", light: "Theme: light", dark: "Theme: dark" }[t];
  btn.innerHTML = ICONS[t === "auto" ? "auto" : t === "light" ? "sun" : "moon"];
  btn.setAttribute("aria-label", `${label} (click to change)`);
  btn.title = label;
  window.dispatchEvent(new Event("prahari:theme"));
}
function initTheme() {
  let t = prefs.get("prahari.theme", "auto");
  if (!THEMES.includes(t)) t = "auto";
  applyTheme(t);
  $("#theme-btn").addEventListener("click", () => {
    t = THEMES[(THEMES.indexOf(t) + 1) % THEMES.length];
    prefs.set("prahari.theme", t);
    applyTheme(t);
  });
}

// ---------------------------------------------------------------- sound toggle
function paintSound() {
  const btn = $("#sound-btn");
  const on = sound.enabled;
  btn.innerHTML = ICONS[on ? "soundOn" : "soundOff"];
  btn.setAttribute("aria-pressed", String(on));
  btn.setAttribute("aria-label", on ? "Alert sound on (click to mute)" : "Alert sound off (click to turn on)");
  btn.title = on ? "Alert sound: on" : "Alert sound: off";
}
function initSound() {
  paintSound();
  $("#sound-btn").addEventListener("click", () => {
    sound.enabled = !sound.enabled;
    paintSound();
    if (sound.enabled) sound.play("review"); // confirms it works
  });
}

// ---------------------------------------------------------------- clock
function tickClock() {
  $("#clock").textContent = `${new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour12: false })} IST`;
}

// ---------------------------------------------------------------- connection + banner
function paintConn() {
  const el = $("#conn");
  const s = live.state;
  el.dataset.state = s;
  el.querySelector(".conn-text").textContent =
    { live: "Live alerts on", connecting: "Connecting…", reconnecting: "Reconnecting…", offline: "Offline" }[s] || s;
  el.title = s === "live" ? "Receiving alerts in real time" : "Live alert feed interrupted — retrying automatically";
}

let serverDown = false;
async function pollHealth() {
  try {
    await get("/api/health", null, { timeout: 8000 });
    if (serverDown) {
      serverDown = false;
      $("#server-banner").hidden = true;
      live.reconnectNow();
      live.resync();
      try { state.current?.refresh?.(); } catch (e) { reportError(e); }
    }
  } catch (e) {
    if (e.kind === "http") return; // server answered: it's up
    serverDown = true;
    const b = $("#server-banner");
    clear(b, icon("warn"), h("div", null, h("strong", null, SERVER_DOWN), h("div", { class: "small" }, "Retrying automatically every few seconds — this page will recover by itself.")));
    b.hidden = false;
  }
}

// ---------------------------------------------------------------- alert badge + toasts
function paintBadge() {
  const b = $("#alert-badge");
  if (!b) return;
  const n = live.openCount();
  const nAlert = live.openCount("alert");
  b.hidden = n === 0;
  b.textContent = n > 99 ? "99+" : String(n);
  b.classList.toggle("has-alert", nAlert > 0);
  b.setAttribute("aria-label", `${n} open (${nAlert} alerts, ${n - nAlert} to review)`);
}

export function toast({ kind = "info", title, body, actionLabel, onAction, timeout = 10000 }) {
  const box = $("#toasts");
  const t = h("div", { class: `toast toast-${kind}` }); // #toasts is the live region
  const close = () => { t.classList.add("leaving"); setTimeout(() => t.remove(), 250); };
  append3(t,
    h("div", { class: "toast-kind" }, kind === "alert" ? icon("warn") : kind === "review" ? icon("question") : icon("check"),
      kind === "alert" ? "ALERT" : kind === "review" ? "NEEDS REVIEW" : ""),
    h("div", { class: "toast-body" }, h("strong", null, title), body ? h("div", null, body) : null),
    h("div", { class: "toast-actions" },
      onAction ? h("button", { type: "button", class: "btn small", onclick: () => { onAction(); close(); } }, actionLabel || "Open") : null,
      h("button", { type: "button", class: "btn small ghost", "aria-label": "Dismiss", onclick: close }, "Dismiss")));
  box.prepend(t);
  while (box.children.length > 4) box.lastElementChild.remove();
  if (timeout) setTimeout(close, timeout);
}
function append3(el, ...kids) { for (const k of kids) el.append(k); }

function onNewAlert(a) {
  const isAlert = a.kind === "alert";
  const cam = (a.camera && (a.camera.name || a.camera.id)) || a.camera_id;
  toast({
    kind: isAlert ? "alert" : "review",
    title: isAlert
      ? `${catLabel(a.category)}: ${fmtPlate(a.watchlist_plate)}`
      : `Possible match for ${fmtPlate(a.watchlist_plate)} — needs a human to confirm`,
    body: `Read "${a.observed}" at ${cam}`,
    actionLabel: "Open alerts",
    onAction: () => navigate("alerts"),
    timeout: isAlert ? 20000 : 12000,
  });
  sound.play(isAlert ? "alert" : "review");
}

// ---------------------------------------------------------------- errors
let lastErrToast = 0;
function reportError(e) {
  // Keep the console clean for operators; still leave a trace for developers.
  console.warn("[prahari]", e);
  if (Date.now() - lastErrToast > 5000) {
    lastErrToast = Date.now();
    toast({ kind: "info", title: "Something on this page didn't work", body: (e && e.message) || String(e), timeout: 6000 });
  }
}
window.addEventListener("unhandledrejection", (ev) => { ev.preventDefault(); reportError(ev.reason); });
window.addEventListener("error", (ev) => { if (ev.error) { ev.preventDefault(); reportError(ev.error); } });

// ---------------------------------------------------------------- boot
function boot() {
  buildNav();
  initTheme();
  initSound();
  tickClock();
  setInterval(tickClock, 1000);
  live.addEventListener("status", paintConn);
  live.addEventListener("change", paintBadge);
  live.addEventListener("new", (e) => onNewAlert(e.detail.alert));
  paintConn();
  live.start();
  pollHealth();
  setInterval(pollHealth, 5000);
  window.addEventListener("hashchange", route);
  route();
}

boot();
