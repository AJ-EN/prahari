// Alerts — live watchlist hits. "alert" = confident match; "review" = a weaker match
// that needs a human to confirm before anyone acts on it.

import { cameras, cachedCamera } from "../api.js";
import { h, clear, icon, fmtTime, ago, plateChip, plateDiff, catChip, errorBox, loading, empty, busy, num } from "../ui.js";

let root, ctx, els = {};
const filters = { kind: "all", status: "open" };
const fresh = new Set(); // ids that arrived while this page was open (highlight)
const cardCache = new Map(); // id -> {sig, el}

/** One alert as a card. Also used by Overview (compact). */
export function alertCard(a, ctx, { compact = false } = {}) {
  const isAlert = a.kind === "alert";
  const acked = a.status === "ack";
  const cam = a.camera || {};
  const camName = cam.name || cam.id || a.camera_id;
  const details = (a.watchlist && a.watchlist.details) || {};
  const { el: observed, edits } = plateDiff(a.observed, a.watchlist_plate);
  const exact = !edits.length;

  const kindBadge = h("div", { class: `kind-badge ${isAlert ? "k-alert" : "k-review"}` },
    icon(isAlert ? "warn" : "question"),
    h("span", null, isAlert ? "ALERT" : "REVIEW"),
    !compact ? h("span", { class: "kind-sub" }, isAlert ? "Confident watchlist match" : "Needs a human to confirm") : null);

  const card = h("article", {
    class: `alert-card ${isAlert ? "is-alert" : "is-review"} ${acked ? "is-acked" : ""} ${compact ? "compact" : ""} ${fresh.has(a.id) ? "is-fresh" : ""}`,
    "aria-label": `${isAlert ? "Alert" : "Review item"}: ${a.watchlist_plate} at ${camName}`,
  });

  const plates = h("div", { class: "alert-plates" },
    h("div", { class: "ap" }, h("span", { class: "ap-label" }, "Camera read"), h("span", { class: "ap-obs" }, observed)),
    h("span", { class: "ap-arrow", "aria-hidden": "true" }, exact ? "=" : "≈"),
    h("div", { class: "ap" }, h("span", { class: "ap-label" }, "Watchlist plate"), plateChip(a.watchlist_plate)));

  const facts = h("div", { class: "alert-facts" },
    catChip(a.category),
    h("span", { class: "fact" }, h("span", { class: "muted" }, "Match distance "), h("strong", { class: "mono" }, Number(a.distance ?? 0).toFixed(2)),
      h("span", { class: "muted" }, exact ? " (exact)" : ` (${edits.join(", ")})`)),
    a.score !== undefined && a.score !== null ? h("span", { class: "fact" }, h("span", { class: "muted" }, "Score "), h("strong", null, `${Math.round(a.score * 100)}%`)) : null,
    a.hits > 1 ? h("span", { class: "fact" }, `Seen ${a.hits}× here`) : null);

  const where = h("div", { class: "alert-where" },
    h("span", null, icon("camera"), " ", h("strong", null, camName), cam.department ? h("span", { class: "muted" }, ` · ${cam.department}`) : null),
    h("span", null, h("strong", null, fmtTime(a.ts)), h("span", { class: "muted" }, ` IST · ${ago(a.ts)}`)));

  card.append(kindBadge, h("div", { class: "alert-main" }, plates, facts, where));

  if (!compact) {
    const info = [details.vehicle, details.fir_no && `FIR ${details.fir_no}`, details.police_station, details.note].filter(Boolean);
    if (info.length) card.querySelector(".alert-main").append(h("div", { class: "alert-info small" }, info.join(" · ")));
    if (a.explain) card.querySelector(".alert-main").append(h("div", { class: "small muted" }, `Why: ${a.explain}`));
    if (!isAlert) card.querySelector(".alert-main").append(h("div", { class: "review-hint small" },
      "This is a weaker match. Look at the camera picture and confirm the plate before acting."));
  }

  const actions = h("div", { class: "alert-actions" });
  if (acked) {
    actions.append(h("div", { class: "acked small" }, icon("check"),
      h("span", null, `Acknowledged${a.acked_by ? ` by ${a.acked_by}` : ""}${a.acked_at ? ` at ${fmtTime(a.acked_at)}` : ""}`),
      a.note ? h("div", { class: "muted" }, `“${a.note}”`) : null));
  } else {
    actions.append(ackControl(a, ctx));
  }
  if (!compact) {
    actions.append(
      h("button", { type: "button", class: "btn small ghost", onclick: () => ctx.navigate("trace", { plate: a.watchlist_plate }) }, "Trace this plate"),
      h("button", { type: "button", class: "btn small ghost", onclick: async () => {
        const c = cachedCamera(a.camera_id) || (await cameras().catch(() => [])).find((x) => x.id === a.camera_id);
        if (c) ctx.openCamera(c);
      } }, "Camera"));
  }
  card.append(actions);
  return card;
}

function ackControl(a, ctx) {
  const wrap = h("div", { class: "ack" });
  const btn = h("button", { type: "button", class: "btn small primary" }, "Acknowledge");
  btn.addEventListener("click", () => {
    const id = `note-${a.id}-${Math.random().toString(36).slice(2, 6)}`;
    const note = h("input", { id, type: "text", placeholder: "e.g. PCR dispatched / false read", maxlength: 300 });
    const err = h("div", { class: "small err-text", role: "alert" });
    const confirm = h("button", { type: "submit", class: "btn small primary" }, "Confirm");
    const cancel = h("button", { type: "button", class: "btn small ghost", onclick: () => clear(wrap, btn) }, "Cancel");
    const form = h("form", { class: "ack-form" },
      h("label", { for: id, class: "small" }, "Note (optional)"), note, h("div", { class: "row gap" }, confirm, cancel), err);
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      busy(confirm, "Saving…", async () => {
        try { await ctx.live.ack(a.id, note.value.trim()); }
        catch (ex) { err.textContent = ex.message; }
      });
    });
    clear(wrap, form);
    note.focus();
  });
  wrap.append(btn);
  return wrap;
}

function init(r, c) {
  root = r; ctx = c;
  const seg = (name, options) => h("div", { class: "seg", role: "group", "aria-label": name === "kind" ? "Show type" : "Show status" },
    options.map(([value, label]) => {
      const b = h("button", { type: "button", class: "seg-btn", "aria-pressed": String(filters[name] === value), onclick: () => {
        filters[name] = value;
        for (const x of b.parentNode.children) x.setAttribute("aria-pressed", String(x === b));
        paint();
      } }, label);
      return b;
    }));
  els.count = h("span", { class: "muted", "aria-live": "polite" });
  els.list = h("div", { class: "alert-list" });
  els.legend = h("div", { class: "alert-legend small" },
    h("span", { class: "kind-badge k-alert mini" }, icon("warn"), "ALERT"), " confident match — act on it. ",
    h("span", { class: "kind-badge k-review mini" }, icon("question"), "REVIEW"), " weaker match — a human must confirm first.");
  clear(root,
    h("div", { class: "view-head" },
      h("h1", { id: "h-alerts" }, "Alerts"),
      h("p", { class: "lede" }, "Watchlist hits from every camera, arriving live. Newest first.")),
    els.legend,
    h("div", { class: "toolbar" },
      seg("kind", [["all", "All"], ["alert", "Alerts"], ["review", "Needs review"]]),
      seg("status", [["open", "Open"], ["ack", "Acknowledged"], ["all", "All"]]),
      els.count),
    els.list);
  ctx.live.addEventListener("change", () => { if (!root.hidden) paint(); });
  ctx.live.addEventListener("new", (e) => {
    fresh.add(e.detail.alert.id);
    setTimeout(() => fresh.delete(e.detail.alert.id), 30000);
  });
}

function paint() {
  const L = ctx.live;
  if (!L.loaded && L.loadError) { clear(els.list, errorBox(L.loadError, () => L.resync())); els.count.textContent = ""; return; }
  if (!L.loaded) { clear(els.list, loading("Loading alerts…")); return; }
  const all = L.sorted();
  const list = all.filter((a) => (filters.kind === "all" || a.kind === filters.kind) && (filters.status === "all" || a.status === filters.status));
  els.count.textContent = `Showing ${num(list.length)} of ${num(all.length)}`;
  if (!list.length) {
    const msg = filters.status === "open" ? "Nothing waiting — no open alerts." : "No alerts match these filters.";
    clear(els.list, empty(msg, L.state === "live" ? "This page is connected: new alerts will appear here instantly." : "Reconnecting to the live feed…"));
    return;
  }
  // Reuse unchanged cards so an Acknowledge form someone is typing in survives a new arrival.
  const next = list.slice(0, 200).map((a) => {
    const sig = `${a.status}|${a.hits}|${a.note}|${a.acked_by}|${fresh.has(a.id)}|${Math.floor(Date.now() / 30000)}`;
    const hit = cardCache.get(a.id);
    if (hit && hit.sig === sig) return hit.el;
    const el = alertCard(a, ctx);
    cardCache.set(a.id, { sig, el });
    return el;
  });
  if (list.length > 200) next.push(h("p", { class: "muted small" }, `Showing the newest 200 of ${list.length}.`));
  const same = next.length === els.list.children.length && next.every((el, i) => els.list.children[i] === el);
  if (!same) {
    const focused = document.activeElement;
    els.list.replaceChildren(...next);
    if (focused && els.list.contains(focused)) focused.focus();
  }
  if (cardCache.size > 600) for (const id of [...cardCache.keys()].slice(0, 200)) cardCache.delete(id);
}

let ageTimer = null;
function show() {
  paint();
  clearInterval(ageTimer);
  ageTimer = setInterval(() => { if (!document.hidden && !els.list.querySelector(".ack-form")) paint(); }, 30000);
}
function hide() { clearInterval(ageTimer); }

export default { id: "alerts", title: "Alerts", icon: "alerts", init, show, hide, refresh: () => ctx.live.resync() };
