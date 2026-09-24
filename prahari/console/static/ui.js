// PRAHARI console — DOM helpers, formatting and small shared widgets.
// All API data is inserted with textContent (never innerHTML), so camera names
// or plates from a catalogue can never inject markup.

import { session } from "./api.js";

// ---------------------------------------------------------------- DOM
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "dataset") Object.assign(el.dataset, v);
      else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else if (k === "html") el.innerHTML = v; // ONLY for static, trusted markup (icons)
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (k === "value" || k === "checked" || k === "selected") el[k] = v;
      else el.setAttribute(k, v === true ? "" : String(v));
    }
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === undefined || c === null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function clear(el, ...children) {
  el.replaceChildren();
  return append(el, children);
}

// ---------------------------------------------------------------- icons (static SVG)
const svg = (body, cls = "") =>
  `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${body}</svg>`;

export const ICONS = {
  overview: svg('<path d="M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z"/>'),
  wall: svg('<path d="M3 5h8v6H3zM13 5h8v6h-8zM3 13h8v6H3zM13 13h8v6h-8z"/>'),
  map: svg('<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zm0 2.2 6 2v11.6l-6-2V6.2z"/>'),
  alerts: svg('<path d="M12 3a6 6 0 0 0-6 6v4l-2 3v1h16v-1l-2-3V9a6 6 0 0 0-6-6zm-2 16a2 2 0 0 0 4 0h-4z"/>'),
  trace: svg('<circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="6" r="2.5"/><path d="M7 17c4-1 2-6 6-7s3-3 4-3" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 2"/>'),
  registry: svg('<path d="M4 4h16v4H4zM4 10h16v4H4zM4 16h16v4H4z"/><circle cx="7" cy="6" r="1" fill="var(--surface)"/><circle cx="7" cy="12" r="1" fill="var(--surface)"/><circle cx="7" cy="18" r="1" fill="var(--surface)"/>'),
  watchlist: svg('<path d="M12 5C6 5 2 12 2 12s4 7 10 7 10-7 10-7-4-7-10-7zm0 11a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm0-6a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"/>'),
  reports: svg('<path d="M6 2h9l5 5v15H6zM14 3v5h5M9 13h8M9 17h8M9 9h3" fill="none" stroke="currentColor" stroke-width="1.8"/>'),
  camera: svg('<path d="M4 7h11v10H4zM15 10l5-3v10l-5-3z"/>'),
  sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 1v3M12 20v3M1 12h3M20 12h3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" stroke="currentColor" stroke-width="2"/>'),
  moon: svg('<path d="M20 15A8 8 0 0 1 9 4a8 8 0 1 0 11 11z"/>'),
  auto: svg('<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 3a9 9 0 0 1 0 18z"/>'),
  soundOn: svg('<path d="M4 9h4l5-4v14l-5-4H4zM16 8a5 5 0 0 1 0 8M18.5 5.5a9 9 0 0 1 0 13" fill="currentColor" stroke="currentColor" stroke-width="1.6"/>'),
  soundOff: svg('<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9l6 6M22 9l-6 6" stroke="currentColor" stroke-width="2"/>'),
  copy: svg('<path d="M8 8h11v13H8zM5 3h11v3H7v11H5z"/>'),
  close: svg('<path d="M6 6l12 12M18 6 6 18" stroke="currentColor" stroke-width="2.4"/>'),
  warn: svg('<path d="M12 2 1 21h22L12 2zm-1 7h2v6h-2zm0 8h2v2h-2z"/>'),
  check: svg('<path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/>'),
  question: svg('<circle cx="12" cy="12" r="10"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .8-1 1.5V14M12 17v.5" fill="none" stroke="var(--surface)" stroke-width="2"/>'),
  lock: svg('<path d="M6 10V8a6 6 0 1 1 12 0v2h1v12H5V10zm2 0h8V8a4 4 0 1 0-8 0z"/>'),
  refresh: svg('<path d="M17.6 6.4A8 8 0 1 0 20 12h-2a6 6 0 1 1-1.8-4.2L13 11h7V4z"/>'),
  download: svg('<path d="M11 3h2v10l3.5-3.5 1.4 1.4L12 16.8l-5.9-5.9 1.4-1.4L11 13zM4 19h16v2H4z"/>'),
  upload: svg('<path d="M11 21h2V11l3.5 3.5 1.4-1.4L12 7.2l-5.9 5.9 1.4 1.4L11 11zM4 3h16v2H4z"/>'),
  pin: svg('<path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/>'),
};

export const icon = (name, label) =>
  h("span", { class: "ico-wrap", html: ICONS[name] || "", ...(label ? { role: "img", "aria-label": label } : {}) });

// ---------------------------------------------------------------- time (always IST)
const TZ = "Asia/Kolkata";
const fmtT = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const fmtDT = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const fmtD = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });

/** Accepts unix seconds, ISO string or Date. */
export function toDate(v) {
  if (v === null || v === undefined || v === "") return null;
  if (v instanceof Date) return v;
  const d = typeof v === "number" ? new Date(v * 1000) : new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}
export const fmtTime = (v) => { const d = toDate(v); return d ? fmtT.format(d) : "—"; };
export const fmtDateTime = (v) => { const d = toDate(v); return d ? fmtDT.format(d) : "—"; };
/** YYYY-MM-DD of today in IST. */
export const todayIST = () => fmtD.format(new Date());

export function ago(v) {
  const d = toDate(v);
  if (!d) return "never";
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < -5) return "in the future (clock skew?)";
  if (s < 5) return "just now";
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function duration(sec) {
  if (sec === null || sec === undefined || Number.isNaN(sec)) return "—";
  const s = Math.round(Math.abs(sec));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${s % 60 ? `${s % 60} s` : ""}`.trim();
  return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}

export const num = (n, digits = 0) =>
  n === null || n === undefined || Number.isNaN(Number(n))
    ? "—"
    : Number(n).toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const pct = (x) => (x === null || x === undefined ? "—" : `${Math.round(Number(x) * 100)}%`);

// ---------------------------------------------------------------- plates
export const normPlate = (p) => String(p || "").toUpperCase().replace(/[^A-Z0-9]/g, "");

/** "GJ01AB1234" -> "GJ 01 AB 1234" (only when it looks like a standard plate). */
export function fmtPlate(p) {
  const s = normPlate(p);
  const m = s.match(/^([A-Z]{2})(\d{1,2})([A-Z]{0,3})(\d{1,4})$/);
  return m ? [m[1], m[2], m[3], m[4]].filter(Boolean).join(" ") : s || "—";
}

/** An HSRP-style plate chip. */
export function plateChip(p, { size = "", title } = {}) {
  return h("span", { class: `plate ${size}`, title: title || undefined },
    h("span", { class: "plate-ind", "aria-hidden": "true" }, "IND"),
    h("span", { class: "plate-txt" }, fmtPlate(p)));
}

/**
 * Show `observed` with characters that differ from `reference` highlighted.
 * Returns {el, edits:["pos7 Z→2", ...]} (positional compare; lengths may differ).
 */
export function plateDiff(observed, reference) {
  const o = normPlate(observed), r = normPlate(reference);
  const el = h("span", { class: "mono plate-diff" });
  const edits = [];
  for (let i = 0; i < o.length; i++) {
    const differs = r && (i >= r.length || o[i] !== r[i]);
    if (differs) {
      el.append(h("mark", { class: "diff", title: r[i] ? `read "${o[i]}", expected "${r[i]}"` : "extra character" }, o[i]));
      edits.push(r[i] ? `${o[i]}→${r[i]} at char ${i + 1}` : `extra ${o[i]} at char ${i + 1}`);
    } else el.append(o[i]);
  }
  if (r && r.length > o.length) edits.push(`${r.length - o.length} character(s) missing`);
  return { el, edits };
}

export const CATEGORY_LABEL = {
  stolen_vehicle: "Stolen vehicle",
  wanted_person: "Wanted person",
  missing_person: "Missing person",
  blacklisted: "Blacklisted",
  suspect: "Suspect",
};
export const catLabel = (c) => CATEGORY_LABEL[c] || String(c || "—").replace(/_/g, " ");
export const catChip = (c) => h("span", { class: `chip cat cat-${c || "other"}` }, catLabel(c));

// ---------------------------------------------------------------- camera state
export const STALE_S = 600;

/**
 * One consistent reading of a camera's health for every view.
 * key: live | degraded | stale | offline | unknown | absent
 */
export function camState(c) {
  const age = c.last_seen ? Date.now() / 1000 - c.last_seen : null;
  if (c.status === "absent") return { key: "absent", label: "Not in catalogue", short: "Absent" };
  if (c.status === "offline") return { key: "offline", label: "Offline", short: "Offline" };
  if (age === null) return { key: "unknown", label: "Never reported", short: "No signal yet" };
  if (age > STALE_S) return { key: "stale", label: `No signal for ${duration(age)}`, short: "Stale" };
  if (c.status === "degraded") return { key: "degraded", label: "Degraded", short: "Degraded" };
  return { key: "live", label: "Live", short: "Live" };
}

export const STATE_ORDER = ["live", "degraded", "stale", "unknown", "offline", "absent"];
export const STATE_NAMES = {
  live: "Live", degraded: "Degraded", stale: "Stale (no recent signal)", unknown: "Never reported",
  offline: "Offline", absent: "Not in catalogue",
};

/** Shape + colour + text: status is never conveyed by colour alone. */
export function stateShape(key) {
  const shapes = {
    live: '<circle cx="8" cy="8" r="6"/>',
    degraded: '<path d="M8 1.5 15 14.5H1z"/>',
    stale: '<path d="M8 1.5 15 14.5H1z"/>',
    offline: '<rect x="2" y="2" width="12" height="12" rx="1"/>',
    unknown: '<circle cx="8" cy="8" r="5.5" fill="none" stroke-width="2.4"/>',
    absent: '<rect x="1.5" y="6" width="13" height="4" rx="1"/>',
  };
  return `<svg class="shape st-${key}" viewBox="0 0 16 16" aria-hidden="true" focusable="false">${shapes[key] || shapes.unknown}</svg>`;
}

export function statePill(c, { withAge = false } = {}) {
  const st = camState(c);
  return h("span", { class: `pill st-${st.key}` },
    h("span", { class: "shape-wrap", html: stateShape(st.key) }),
    st.key === "stale" ? `Stale · ${ago(c.last_seen)}` : st.label,
    withAge && st.key !== "stale" && c.last_seen ? h("span", { class: "muted" }, ` · ${ago(c.last_seen)}`) : null);
}

// ---------------------------------------------------------------- states
export function loading(msg = "Loading…") {
  return h("div", { class: "state state-loading", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), msg);
}

export function empty(msg, hint) {
  return h("div", { class: "state state-empty" }, h("strong", null, msg), hint ? h("p", null, hint) : null);
}

export function errorBox(err, retry) {
  const msg = err && err.message ? err.message : String(err || "Something went wrong.");
  return h("div", { class: "state state-error", role: "alert" },
    icon("warn"),
    h("div", null, h("strong", null, msg),
      retry ? h("div", null, h("button", { class: "btn small", type: "button", onclick: retry }, "Try again")) : null));
}

export function notice(kind, ...children) {
  const kids = children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false);
  const lead = kids.length && kids[0] instanceof Element && kids[0].classList.contains("ico-wrap") ? [kids.shift()] : [];
  return h("div", { class: `notice notice-${kind}`, role: kind === "error" ? "alert" : "status" }, lead, h("div", { class: "notice-body" }, kids));
}

/** Wrap a table so it scrolls horizontally instead of breaking the page. */
export const tableWrap = (table) => h("div", { class: "table-wrap" }, table);

// ---------------------------------------------------------------- clipboard
export async function copyText(text, btn) {
  let ok = false;
  try {
    await navigator.clipboard.writeText(text);
    ok = true;
  } catch {
    const ta = h("textarea", { style: { position: "fixed", opacity: "0" } }, text);
    document.body.append(ta);
    ta.select();
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove();
  }
  if (btn) {
    const old = btn.textContent;
    btn.textContent = ok ? "Copied" : "Select and copy";
    setTimeout(() => { btn.textContent = old; }, 1500);
  }
  return ok;
}

export function copyField(label, value) {
  const id = `f-${Math.random().toString(36).slice(2)}`;
  if (!value) {
    return h("div", { class: "copy-field" }, h("span", { class: "label" }, label), h("span", { class: "muted" }, "Not provided"));
  }
  const input = h("input", { id, class: "mono", type: "text", readonly: true, value });
  const btn = h("button", { type: "button", class: "btn small", onclick: () => copyText(value, btn) }, "Copy");
  return h("div", { class: "copy-field" }, h("label", { for: id, class: "label" }, label), h("div", { class: "copy-row" }, input, btn));
}

// ---------------------------------------------------------------- purpose binding
const PURPOSES = [
  "Stolen vehicle recovery",
  "Wanted person tracking",
  "Missing person search",
  "Accident / hit-and-run investigation",
  "Crime investigation",
  "Demonstration / training",
];

/**
 * The purpose + case id fields every audited search needs.
 * Returns {el, read()} — read() returns {purpose, case_id} or null after focusing the gap.
 */
export function purposeFields({ compact = false } = {}) {
  const uid = Math.random().toString(36).slice(2);
  const listId = `purposes-${uid}`;
  const purpose = h("input", { id: `p-${uid}`, type: "text", list: listId, required: true, autocomplete: "off",
    placeholder: "e.g. Stolen vehicle recovery", value: session.get("prahari.purpose") });
  const caseId = h("input", { id: `c-${uid}`, type: "text", required: true, autocomplete: "off",
    placeholder: "e.g. FIR-123/2026", value: session.get("prahari.case_id") });
  const actor = h("input", { id: `a-${uid}`, type: "text", autocomplete: "name",
    placeholder: "Name / badge no.", value: session.get("prahari.actor") });
  const save = () => {
    session.set("prahari.purpose", purpose.value.trim());
    session.set("prahari.case_id", caseId.value.trim());
    session.set("prahari.actor", actor.value.trim());
  };
  // Keep every purpose form on the page in sync with the remembered values.
  const refresh = () => {
    if (document.activeElement !== purpose) purpose.value = session.get("prahari.purpose");
    if (document.activeElement !== caseId) caseId.value = session.get("prahari.case_id");
    if (document.activeElement !== actor) actor.value = session.get("prahari.actor");
  };
  for (const i of [purpose, caseId, actor]) i.addEventListener("change", save);
  const el = h("fieldset", { class: `purpose ${compact ? "compact" : ""}` },
    h("legend", null, icon("lock"), "Why are you searching?"),
    h("p", { class: "purpose-why" }, "Every search is logged for accountability — state the purpose and case reference."),
    h("div", { class: "purpose-grid" },
      h("div", { class: "field" }, h("label", { for: purpose.id }, "Purpose ", h("span", { class: "req" }, "(required)")), purpose,
        h("datalist", { id: listId }, PURPOSES.map((p) => h("option", { value: p })))),
      h("div", { class: "field" }, h("label", { for: caseId.id }, "Case / FIR no. ", h("span", { class: "req" }, "(required)")), caseId),
      h("div", { class: "field" }, h("label", { for: actor.id }, "Officer ", h("span", { class: "muted" }, "(optional)")), actor)));
  return {
    el,
    refresh,
    read() {
      save();
      const p = purpose.value.trim(), c = caseId.value.trim();
      purpose.setAttribute("aria-invalid", p ? "false" : "true");
      caseId.setAttribute("aria-invalid", c ? "false" : "true");
      if (!p) { purpose.focus(); return null; }
      if (!c) { caseId.focus(); return null; }
      return { purpose: p, case_id: c };
    },
  };
}

// ---------------------------------------------------------------- CSV input (file or paste)
/**
 * A file picker + paste box. The file is read in the browser and sent as raw text.
 * Returns {el, text(), setText(), reset()}.
 */
export function csvInput({ template, templateName = "template.csv", label = "CSV" }) {
  const uid = Math.random().toString(36).slice(2);
  const area = h("textarea", { id: `csv-${uid}`, class: "mono", rows: 6, spellcheck: "false",
    placeholder: `Paste ${label} here, or choose a file above. For example:\n\n${template}` });
  const fileInfo = h("span", { class: "muted small", "aria-live": "polite" });
  const file = h("input", { id: `file-${uid}`, type: "file", accept: ".csv,text/csv,text/plain", class: "file-input" });
  file.addEventListener("change", async () => {
    const f = file.files && file.files[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) { fileInfo.textContent = "That file is over 5 MB — please split it."; return; }
    try {
      area.value = (await f.text()).replace(/^﻿/, "");
      const rows = area.value.split(/\r?\n/).filter((l) => l.trim()).length;
      fileInfo.textContent = `Loaded ${f.name} — ${Math.max(rows - 1, 0)} data row(s). Check below, then import.`;
    } catch {
      fileInfo.textContent = "Couldn't read that file. Try pasting its contents instead.";
    }
  });
  const dl = h("button", { type: "button", class: "btn small ghost", onclick: () => downloadText(template, templateName, "text/csv") },
    icon("download"), "Download template");
  const show = h("details", { class: "template" }, h("summary", null, "Show the template"), h("pre", { class: "mono" }, template));
  const el = h("div", { class: "csv-input" },
    h("div", { class: "csv-file-row" },
      h("label", { for: file.id, class: "btn small" }, icon("upload"), "Choose CSV file…"), file, dl, fileInfo),
    h("label", { for: area.id, class: "label" }, `…or paste ${label}`), area, show);
  return {
    el,
    text: () => area.value,
    setText: (t) => { area.value = t; },
    reset: () => { area.value = ""; file.value = ""; fileInfo.textContent = ""; },
  };
}

export function downloadText(text, name, type = "text/plain") {
  downloadBlob(new Blob([text], { type }), name);
}

export function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = h("a", { href: url, download: name, style: { display: "none" } });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// ---------------------------------------------------------------- busy buttons
/** Disable a button and show a busy label while `fn` runs. */
export async function busy(btn, label, fn) {
  const old = btn.innerHTML;
  btn.disabled = true;
  btn.setAttribute("aria-busy", "true");
  btn.textContent = label;
  try {
    return await fn();
  } finally {
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
    btn.innerHTML = old;
  }
}

/** Key/value definition list; skips empty values. */
export function kv(pairs) {
  const dl = h("dl", { class: "kv" });
  for (const [k, v] of pairs) {
    if (v === undefined || v === null || v === "") continue;
    dl.append(h("dt", null, k), h("dd", null, v));
  }
  return dl;
}

function skippedWhere(s) {
  if (s.id) return s.id;
  if (s.line !== undefined && s.line !== null) return `line ${s.line}`;
  if (s.index !== undefined && s.index !== null) return `record #${Number(s.index) + 1}`;
  return "record";
}

/** Summarise an onboarding/import result as readable lines. */
export function resultSummary(res, noun = "camera") {
  const list = (arr) => (arr && arr.length ? arr.slice(0, 12).join(", ") + (arr.length > 12 ? ` … +${arr.length - 12} more` : "") : "");
  const n = (arr) => (arr ? arr.length : 0);
  const rows = [];
  if (res.parsed !== undefined) rows.push(["Read", `${res.parsed} ${noun}(s)`]);
  rows.push(["Added", n(res.added) ? `${n(res.added)} — ${list(res.added)}` : "0"]);
  if (res.updated) rows.push(["Updated", n(res.updated) ? `${n(res.updated)} — ${list(res.updated)}` : "0"]);
  if (res.unchanged) rows.push(["Unchanged", String(n(res.unchanged))]);
  if (n(res.absent)) rows.push(["No longer in catalogue", `${n(res.absent)} — ${list(res.absent)} (marked absent, not deleted)`]);
  if (n(res.without_location)) rows.push(["Missing location", `${n(res.without_location)} — ${list(res.without_location)} (won't appear on the map)`]);
  const skipped = res.skipped || [];
  const out = h("div", null, kv(rows));
  if (skipped.length) {
    out.append(h("p", { class: "warn-text" }, `${skipped.length} record(s) could not be read:`),
      h("ul", { class: "small" }, skipped.slice(0, 20).map((s) =>
        h("li", null, typeof s === "string" ? s : `${skippedWhere(s)}: ${s.reason || s.error || "unreadable"}`))));
  }
  return out;
}
