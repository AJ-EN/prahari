// Watchlist — plates to alert on: list, add, CSV import, deactivate, and a purpose-bound check.

import { get, post, request } from "../api.js";
import {
  h, clear, icon, fmtDateTime, plateChip, plateDiff, fmtPlate, normPlate, catChip, catLabel, CATEGORY_LABEL,
  errorBox, loading, empty, num, notice, tableWrap, busy, csvInput, purposeFields,
} from "../ui.js";

let root, ctx, els = {};
let entries = [], inactive = [];
const filt = { cat: "", q: "", showInactive: false };

const TEMPLATE =
  "plate,category,fir_no,police_station,vehicle,note\n" +
  "GJ01AB1234,stolen_vehicle,FIR-123/2026,Navrangpura,\"Maruti Swift, white\",stolen from parking\n" +
  "GJ18BK4521,wanted_person,FIR-77/2026,Sector-7,\"Hyundai i20, red\",\n";

function init(r, c) {
  root = r; ctx = c;
  els.chips = h("div", { class: "chips", role: "group", "aria-label": "Filter by category" });
  els.q = h("input", { id: "wl-q", type: "search", placeholder: "Plate, vehicle, FIR…", autocomplete: "off" });
  els.inactive = h("input", { id: "wl-inactive", type: "checkbox" });
  els.count = h("span", { class: "muted", "aria-live": "polite" });
  els.sample = h("div");
  els.table = h("div");
  els.q.addEventListener("input", () => { filt.q = els.q.value.trim().toUpperCase(); paint(); });
  els.inactive.addEventListener("change", () => { filt.showInactive = els.inactive.checked; load(); });

  clear(root,
    h("div", { class: "view-head" },
      h("h1", { id: "h-watchlist" }, "Watchlist"),
      h("p", { class: "lede" }, "Plates every camera checks against, all the time. A close read (e.g. 8 for B) still matches.")),
    els.sample,
    h("section", { class: "card", "aria-labelledby": "h-wl" },
      h("div", { class: "card-head" }, h("h2", { id: "h-wl" }, "Entries"), els.count),
      els.chips,
      h("div", { class: "toolbar" },
        h("div", { class: "field inline" }, h("label", { for: "wl-q" }, "Find in list"), els.q),
        h("label", { class: "check", for: "wl-inactive" }, els.inactive, "Include deactivated")),
      els.table),
    h("div", { class: "onboard-grid two" }, addCard(), importCard()),
    checkCard());
}

// ---------------------------------------------------------------- list
function paintChips() {
  const counts = {};
  for (const e of entries) counts[e.category] = (counts[e.category] || 0) + 1;
  const cats = [...new Set([...Object.keys(CATEGORY_LABEL), ...Object.keys(counts)])];
  const chip = (value, label, n) => h("button", { type: "button", class: `chip chip-btn ${value ? `cat cat-${value}` : ""}`, "aria-pressed": String(filt.cat === value),
    onclick: () => { filt.cat = filt.cat === value ? "" : value; paintChips(); paint(); } }, `${label} (${num(n)})`);
  clear(els.chips, chip("", "All", entries.length), cats.filter((c) => counts[c]).map((c) => chip(c, catLabel(c), counts[c])));
}

function paint() {
  const all = filt.showInactive ? [...entries, ...inactive] : entries;
  const list = all.filter((e) => {
    if (filt.cat && e.category !== filt.cat) return false;
    if (filt.q) {
      const d = e.details || {};
      const hay = `${e.plate} ${d.vehicle || ""} ${d.fir_no || ""} ${d.police_station || ""} ${d.note || ""}`.toUpperCase();
      if (!hay.includes(filt.q) && !e.plate.includes(normPlate(filt.q))) return false;
    }
    return true;
  });
  els.count.textContent = `${num(list.length)} of ${num(all.length)} shown`;
  clear(els.sample, all.some((e) => e.details && e.details.sample)
    ? notice("warn", icon("warn"), "These entries are SAMPLE data, fabricated for demonstration — they do not refer to real cases or people.") : null);
  if (!all.length) { clear(els.table, empty("The watchlist is empty.", "Add a plate below, or import a CSV.")); return; }
  if (!list.length) { clear(els.table, empty("No entries match.")); return; }
  const table = h("table", { class: "table" },
    h("caption", { class: "sr-only" }, "Watchlist entries"),
    h("thead", null, h("tr", null, ["Plate", "Category", "Vehicle", "FIR / police station", "Note", "Added", ""].map((t) => h("th", { scope: "col" }, t)))),
    h("tbody", null, list.map((e) => {
      const d = e.details || {};
      const g = e.grammar || {};
      return h("tr", { class: e.active === false ? "row-muted" : "" },
        h("td", null, plateChip(e.plate), g.valid === false ? h("div", { class: "small warn-text" }, "non-standard format") : null,
          g.state ? h("div", { class: "small muted" }, [g.state, g.district].filter(Boolean).join(" · ")) : null),
        h("td", null, catChip(e.category)),
        h("td", null, d.vehicle || "—"),
        h("td", { class: "small" }, d.fir_no || "—", d.police_station ? h("div", { class: "muted" }, d.police_station) : null),
        h("td", { class: "small" }, d.note || ""),
        h("td", { class: "small" }, fmtDateTime(e.added_at), h("div", { class: "muted" }, e.source || "")),
        h("td", null, e.active === false
          ? h("span", { class: "chip" }, "Deactivated")
          : h("button", { type: "button", class: "btn small ghost danger", onclick: (ev) => deactivate(e, ev.currentTarget), "aria-label": `Deactivate ${e.plate}` }, "Deactivate")));
    })));
  const wrap = tableWrap(table);
  wrap.classList.add("scroll-limit");
  clear(els.table, wrap);
}

async function load() {
  if (!entries.length) clear(els.table, loading("Loading watchlist…"));
  try {
    const [a, b] = await Promise.all([
      get("/api/watchlist", { active: true }),
      filt.showInactive ? get("/api/watchlist", { active: false }) : Promise.resolve({ entries: [] }),
    ]);
    entries = a.entries || [];
    inactive = b.entries || [];
    paintChips();
    paint();
  } catch (e) {
    clear(els.table, errorBox(e, load));
  }
}

async function deactivate(e, btn) {
  if (!window.confirm(`Stop alerting on ${fmtPlate(e.plate)}?\n\nThe entry and its past alerts are kept for the audit trail.`)) return;
  await busy(btn, "…", async () => {
    try {
      await request(`/api/watchlist/${encodeURIComponent(e.plate)}`, { method: "DELETE" });
      await load();
    } catch (ex) {
      window.alert(`Couldn't deactivate: ${ex.message}`);
    }
  });
}

// ---------------------------------------------------------------- add / import
function addCard() {
  const f = (id, label, input) => h("div", { class: "field" }, h("label", { for: id }, label), input);
  const i = {
    plate: h("input", { id: "wa-plate", class: "mono", type: "text", required: true, autocomplete: "off", autocapitalize: "characters", placeholder: "GJ01AB1234" }),
    category: h("select", { id: "wa-cat", required: true }, Object.entries(CATEGORY_LABEL).map(([v, t]) => h("option", { value: v }, t))),
    vehicle: h("input", { id: "wa-veh", type: "text", autocomplete: "off", placeholder: "Make, model, colour" }),
    fir: h("input", { id: "wa-fir", type: "text", autocomplete: "off", placeholder: "FIR-123/2026" }),
    ps: h("input", { id: "wa-ps", type: "text", autocomplete: "off", placeholder: "Police station" }),
    note: h("input", { id: "wa-note", type: "text", autocomplete: "off" }),
  };
  i.plate.addEventListener("input", () => { i.plate.value = i.plate.value.toUpperCase(); });
  const out = h("div", { "aria-live": "polite" });
  const btn = h("button", { type: "submit", class: "btn primary" }, "Add to watchlist");
  const form = h("form", { novalidate: true },
    h("div", { class: "form-grid" }, f("wa-plate", "Plate (required)", i.plate), f("wa-cat", "Category (required)", i.category),
      f("wa-veh", "Vehicle", i.vehicle), f("wa-fir", "FIR no.", i.fir), f("wa-ps", "Police station", i.ps), f("wa-note", "Note", i.note)),
    btn, out);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!normPlate(i.plate.value)) { clear(out, notice("error", "Enter the plate.")); i.plate.focus(); return; }
    const details = {};
    if (i.vehicle.value.trim()) details.vehicle = i.vehicle.value.trim();
    if (i.fir.value.trim()) details.fir_no = i.fir.value.trim();
    if (i.ps.value.trim()) details.police_station = i.ps.value.trim();
    if (i.note.value.trim()) details.note = i.note.value.trim();
    busy(btn, "Saving…", async () => {
      try {
        const res = await post("/api/watchlist", { plate: i.plate.value, category: i.category.value, details });
        const g = res.grammar || {};
        clear(out, notice(g.valid === false ? "warn" : "ok", icon("check"), `${fmtPlate(res.plate)} is on the watchlist as ${catLabel(res.category)}.`,
          g.valid === false ? h("div", { class: "small" }, `Note: it doesn't fit the Indian plate format (${(g.reasons || []).join("; ")}). It will still be matched.`) : null));
        form.reset();
        load();
      } catch (ex) { clear(out, errorBox(ex)); }
    });
  });
  return h("section", { class: "card", "aria-labelledby": "h-wadd" }, h("h2", { id: "h-wadd" }, "Add a plate"), form);
}

function importCard() {
  const csv = csvInput({ template: TEMPLATE, templateName: "prahari_watchlist_template.csv", label: "watchlist rows" });
  const out = h("div", { "aria-live": "polite" });
  const btn = h("button", { type: "submit", class: "btn primary" }, "Import watchlist");
  const form = h("form", { novalidate: true }, csv.el, btn, out);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = csv.text().trim();
    if (!text) { clear(out, notice("error", "Choose a CSV file or paste rows first.")); return; }
    busy(btn, "Importing…", async () => {
      try {
        const res = await request("/api/watchlist/import", { method: "POST", body: text + "\n", contentType: "text/csv", timeout: 90000 });
        const errs = res.errors || [];
        clear(out, notice(errs.length ? "warn" : "ok", icon("check"), `Imported ${num(res.imported)} plate(s).`),
          errs.length ? h("ul", { class: "small" }, errs.slice(0, 20).map((x) => h("li", null, `Line ${x.line}: ${x.error}`))) : null);
        load();
      } catch (ex) { clear(out, errorBox(ex)); }
    });
  });
  return h("section", { class: "card", "aria-labelledby": "h-wimp" }, h("h2", { id: "h-wimp" }, "Import CSV"),
    h("p", { class: "small muted" }, "Columns plate and category are required; any other column is kept with the entry."), form);
}

// ---------------------------------------------------------------- purpose-bound check
function checkCard() {
  const purpose = purposeFields({ compact: true });
  els.purpose = purpose;
  const plate = h("input", { id: "wc-plate", class: "mono", type: "text", autocomplete: "off", autocapitalize: "characters", placeholder: "Plate as read, e.g. GJ01AB1Z34" });
  plate.addEventListener("input", () => { plate.value = plate.value.toUpperCase(); });
  const out = h("div", { "aria-live": "polite" });
  const btn = h("button", { type: "submit", class: "btn primary" }, "Check");
  const form = h("form", { novalidate: true },
    h("div", { class: "row gap wrap end" }, h("div", { class: "field grow" }, h("label", { for: "wc-plate" }, "Plate to check"), plate), btn),
    purpose.el, out);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const p = normPlate(plate.value);
    if (!p) { clear(out, notice("error", "Enter a plate to check.")); plate.focus(); return; }
    const pb = purpose.read();
    if (!pb) { clear(out, notice("error", "Fill in the purpose and case number — every search is logged.")); return; }
    busy(btn, "Checking…", async () => {
      try {
        const r = await get("/api/watchlist/search", { plate: p, top_k: 10, ...pb });
        const hits = r.hits || [];
        const corr = (r.corrections || []).slice(0, 5);
        clear(out,
          hits.length
            ? tableWrap(h("table", { class: "table compact" },
              h("caption", null, `Watchlist entries close to ${p} (${num(r.watchlist_size)} checked)`),
              h("thead", null, h("tr", null, ["Watchlist plate", "Read vs entry", "Distance", "Decision", "Category", "Why"].map((t) => h("th", { scope: "col" }, t)))),
              h("tbody", null, hits.map((x) => h("tr", null,
                h("td", null, plateChip(x.watchlist_plate)),
                h("td", null, plateDiff(p, x.watchlist_plate).el),
                h("td", { class: "num mono" }, Number(x.distance).toFixed(2)),
                h("td", null, x.decision === "alert" ? h("span", { class: "kind-badge k-alert mini" }, icon("warn"), "ALERT")
                  : h("span", { class: "kind-badge k-review mini" }, icon("question"), "REVIEW")),
                h("td", null, catChip(x.category)),
                h("td", { class: "small" }, x.explain || ""))))))
            : notice("ok", icon("check"), `${fmtPlate(p)} is not close to any of the ${num(r.watchlist_size)} watchlist entries.`),
          r.grammar && r.grammar.valid === false && corr.length
            ? h("p", { class: "small" }, "Not a valid plate format. Likely intended: ", corr.map((c) => [h("span", { class: "chip mono" }, fmtPlate(c.plate)), " "]))
            : null);
      } catch (ex) { clear(out, errorBox(ex)); }
    });
  });
  return h("section", { class: "card", "aria-labelledby": "h-wchk" },
    h("h2", { id: "h-wchk" }, "Check a plate against the watchlist"),
    h("p", { class: "small muted" }, "Type a plate as a camera or witness read it — near-misses caused by look-alike characters are found too."), form);
}

function show() { els.purpose.refresh(); load(); }

export default { id: "watchlist", title: "Watchlist", icon: "watchlist", init, show, refresh: load };
