// Reports — plates CSV export, plate-read search, and the tamper-evident audit log.

import { get, request, cameras, cachedCamera, session } from "../api.js";
import {
  h, clear, icon, fmtTime, fmtDateTime, num, plateDiff, errorBox, loading, empty, notice, tableWrap, busy,
  purposeFields, downloadBlob, todayIST, normPlate,
} from "../ui.js";

let root, ctx, els = {};

const ACTIONS = [
  ["", "All actions"], ["trace", "Vehicle trace"], ["events.search", "Plate-read search"], ["watchlist.search", "Watchlist check"],
  ["report.plates_csv", "Plates CSV export"], ["alert.ack", "Alert acknowledged"], ["watchlist.add", "Watchlist add"],
  ["watchlist.import", "Watchlist import"], ["watchlist.deactivate", "Watchlist deactivate"], ["camera.manual_add", "Camera added by hand"],
  ["camera.bulk_import", "Camera CSV import"], ["camera.catalogue_sync", "Catalogue sync"], ["camera.delete", "Camera removed"],
];
const actionName = Object.fromEntries(ACTIONS);

function limitWrap(table) {
  const w = tableWrap(table);
  w.classList.add("scroll-limit");
  return w;
}

function camSelect(id) {
  return h("select", { id }, h("option", { value: "" }, "All cameras"));
}

async function fillCams(...selects) {
  try {
    const list = await cameras();
    for (const s of selects) {
      const cur = s.value;
      clear(s, h("option", { value: "" }, "All cameras"), list.map((c) => h("option", { value: c.id }, `${c.name || c.id} (${c.id})`)));
      s.value = cur;
    }
  } catch { /* the selects keep "All cameras"; errors show elsewhere */ }
}

function init(r, c) {
  root = r; ctx = c;
  clear(root,
    h("div", { class: "view-head" },
      h("h1", { id: "h-reports" }, "Reports & audit"),
      h("p", { class: "lede" }, "Export every plate read, look up reads, and prove that nobody has altered the search log.")),
    h("div", { class: "grid-2" }, csvCard(), searchCard()),
    auditCard());
}

// ---------------------------------------------------------------- plates CSV
function csvCard() {
  const from = h("input", { id: "rp-from", type: "datetime-local", step: 1, value: `${todayIST()}T00:00` });
  const to = h("input", { id: "rp-to", type: "datetime-local", step: 1 });
  els.csvCam = camSelect("rp-cam");
  const out = h("div", { "aria-live": "polite" });
  const btn = h("button", { type: "submit", class: "btn primary" }, icon("download"), "Download plates CSV");
  const form = h("form", { novalidate: true },
    h("div", { class: "form-grid wide" },
      h("div", { class: "field" }, h("label", { for: "rp-from" }, "From (IST)"), from),
      h("div", { class: "field" }, h("label", { for: "rp-to" }, "To (IST, blank = now)"), to),
      h("div", { class: "field" }, h("label", { for: "rp-cam" }, "Camera"), els.csvCam)),
    h("p", { class: "small muted" }, "Every detected plate with camera, location, time, OCR confidence and any watchlist match. The export is recorded in the audit log."),
    btn, out);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    busy(btn, "Preparing…", async () => {
      clear(out);
      try {
        const res = await request("/api/reports/plates.csv", {
          raw: true, timeout: 120000,
          query: { from: from.value, to: to.value, camera: els.csvCam.value, purpose: session.get("prahari.purpose") || "report export", case_id: session.get("prahari.case_id") },
        });
        const blob = await res.blob();
        const rows = Math.max(0, (await blob.text()).split("\n").filter((l) => l.trim()).length - 1);
        downloadBlob(blob, `prahari_plates_${(from.value || "all").slice(0, 10)}.csv`);
        clear(out, notice(rows ? "ok" : "warn", icon("check"), rows ? `Downloaded ${num(rows)} plate read(s).` : "Downloaded — but there were no plate reads in that window."));
      } catch (ex) { clear(out, errorBox(ex)); }
    });
  });
  return h("section", { class: "card", "aria-labelledby": "h-csv" }, h("h2", { id: "h-csv" }, "Plates CSV"), form);
}

// ---------------------------------------------------------------- plate-read search
function searchCard() {
  const purpose = purposeFields({ compact: true });
  els.purpose = purpose;
  const plate = h("input", { id: "rs-plate", class: "mono", type: "text", autocomplete: "off", autocapitalize: "characters", placeholder: "Leave blank for the latest reads" });
  plate.addEventListener("input", () => { plate.value = plate.value.toUpperCase(); });
  els.searchCam = camSelect("rs-cam");
  const out = h("div", { "aria-live": "polite" });
  const btn = h("button", { type: "submit", class: "btn primary" }, "Search reads");
  const form = h("form", { novalidate: true },
    h("div", { class: "form-grid" },
      h("div", { class: "field" }, h("label", { for: "rs-plate" }, "Plate (optional)"), plate),
      h("div", { class: "field" }, h("label", { for: "rs-cam" }, "Camera"), els.searchCam)),
    purpose.el, btn, out);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const p = normPlate(plate.value);
    const q = { camera: els.searchCam.value, limit: 200 };
    if (p) {
      const pb = purpose.read();
      if (!pb) { clear(out, notice("error", "Searching for a plate needs a purpose and case number — every search is logged.")); return; }
      Object.assign(q, pb, { plate: p });
    }
    busy(btn, "Searching…", async () => {
      clear(out, loading("Searching…"));
      try {
        const r = await get("/api/events", q, { timeout: 60000 });
        const evs = r.events || [];
        if (!evs.length) {
          const nm = r.near_misses || [];
          clear(out, empty(p ? `No reads close to ${p}.` : "No plate reads yet."),
            nm.length ? h("p", { class: "small" }, "Closest readings: ", nm.slice(0, 6).map((m) => h("span", { class: "chip mono", title: `distance ${m.distance}` }, m.reading))) : null);
          return;
        }
        clear(out, h("p", { class: "small muted" }, `${num(r.count)} read(s)${p ? ` within confusion distance ${r.max_distance} of ${p}` : ", newest first"}.`),
          limitWrap(h("table", { class: "table compact" },
            h("thead", null, h("tr", null, ["Time (IST)", "Camera", "Read", p ? "Distance" : "Format", "OCR"].map((t) => h("th", { scope: "col" }, t)))),
            h("tbody", null, evs.map((ev) => h("tr", null,
              h("td", { class: "mono small" }, fmtDateTime(ev.ts)),
              h("td", { class: "small" }, (ev.camera && ev.camera.name) || cachedCamera(ev.camera_id)?.name || ev.camera_id),
              h("td", null, p ? plateDiff(ev.raw_text || ev.plate, p).el : h("span", { class: "mono" }, ev.plate || ev.raw_text)),
              h("td", { class: "small" }, p ? Number(ev.match?.distance ?? 0).toFixed(2) : ev.valid ? "valid" : "non-standard"),
              h("td", { class: "num small" }, ev.ocr_conf !== undefined ? `${Math.round(ev.ocr_conf * 100)}%` : "—")))))));
      } catch (ex) { clear(out, errorBox(ex)); }
    });
  });
  return h("section", { class: "card", "aria-labelledby": "h-rs" }, h("h2", { id: "h-rs" }, "Search plate reads"),
    h("p", { class: "small muted" }, "Look-alike characters are matched (e.g. a camera reading 8 for B)."), form);
}

// ---------------------------------------------------------------- audit
function auditCard() {
  els.aAction = h("select", { id: "au-action" }, ACTIONS.map(([v, t]) => h("option", { value: v }, t)));
  els.aCase = h("input", { id: "au-case", type: "search", autocomplete: "off", placeholder: "Exact case / FIR no." });
  els.aLimit = h("select", { id: "au-limit" }, [50, 200, 1000].map((n) => h("option", { value: n }, `Last ${n}`)));
  els.aTable = h("div");
  els.verifyOut = h("div", { "aria-live": "polite" });
  const verifyBtn = h("button", { type: "button", class: "btn primary" }, icon("lock"), "Verify audit chain");
  verifyBtn.addEventListener("click", () => busy(verifyBtn, "Verifying…", verify));
  for (const el of [els.aAction, els.aLimit]) el.addEventListener("change", loadAudit);
  let t = null;
  els.aCase.addEventListener("input", () => { clearTimeout(t); t = setTimeout(loadAudit, 400); });
  return h("section", { class: "card", "aria-labelledby": "h-audit" },
    h("div", { class: "card-head" }, h("h2", { id: "h-audit" }, "Audit log"), verifyBtn),
    h("p", { class: "small muted" }, "Every search, export and change is chained with SHA-256: each entry includes the previous entry's hash, " +
      "so editing or deleting any past entry breaks the chain. “Verify” recomputes it from the first entry."),
    els.verifyOut,
    h("div", { class: "toolbar" },
      h("div", { class: "field inline" }, h("label", { for: "au-action" }, "Action"), els.aAction),
      h("div", { class: "field inline" }, h("label", { for: "au-case" }, "Case"), els.aCase),
      h("div", { class: "field inline" }, h("label", { for: "au-limit" }, "Show"), els.aLimit),
      h("button", { type: "button", class: "btn small ghost", onclick: loadAudit }, icon("refresh"), "Refresh")),
    els.aTable);
}

async function verify() {
  clear(els.verifyOut, loading("Recomputing every hash…"));
  try {
    const r = await get("/api/audit/verify", null, { timeout: 120000 });
    if (r.intact) {
      clear(els.verifyOut, h("div", { class: "verify verify-ok", role: "status" }, icon("check"),
        h("div", null, h("strong", null, "INTACT — the audit log has not been altered."),
          h("div", { class: "small" }, `${num(r.entries)} entries verified at ${fmtTime(Date.now() / 1000)} IST.`),
          r.head_hash ? h("div", { class: "small" }, "Latest hash: ", h("code", { class: "mono hash" }, r.head_hash)) : null,
          h("div", { class: "small muted" }, "Record this hash outside the system (e.g. in a signed report) to also detect deletion of the newest entries."))));
    } else {
      clear(els.verifyOut, h("div", { class: "verify verify-bad", role: "alert" }, icon("warn"),
        h("div", null, h("strong", null, "TAMPERED — the audit chain is broken."),
          h("div", null, `First bad entry: #${r.first_broken_id ?? "?"}. ${r.reason || ""}`),
          h("div", { class: "small" }, `${num(r.entries)} entries checked. Preserve this database file and report it.`))));
    }
  } catch (e) { clear(els.verifyOut, errorBox(e, verify)); }
}

function paramsText(p) {
  if (!p || typeof p !== "object") return "";
  return Object.entries(p).filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ");
}

async function loadAudit() {
  if (!els.aTable.childElementCount) clear(els.aTable, loading("Loading audit log…"));
  try {
    const r = await get("/api/audit", { limit: els.aLimit.value, action: els.aAction.value, case_id: els.aCase.value.trim() });
    const list = r.entries || [];
    if (!list.length) { clear(els.aTable, empty("No audit entries match.", "Searches, exports and registry changes appear here as they happen.")); return; }
    clear(els.aTable, limitWrap(h("table", { class: "table compact audit-table" },
      h("caption", { class: "sr-only" }, "Audit log entries, newest first"),
      h("thead", null, h("tr", null, ["#", "Time (IST)", "Who", "Action", "Purpose", "Case", "Details", "Hash"].map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", null, list.map((e) => h("tr", null,
        h("td", { class: "num mono small" }, String(e.id)),
        h("td", { class: "mono small" }, fmtDateTime(e.ts)),
        h("td", { class: "small" }, e.actor || "—"),
        h("td", { class: "small" }, actionName[e.action] || e.action),
        h("td", { class: "small" }, e.purpose || h("span", { class: "muted" }, "—")),
        h("td", { class: "small mono" }, e.case_id || h("span", { class: "muted" }, "—")),
        h("td", { class: "small params" }, paramsText(e.params)),
        h("td", null, h("code", { class: "mono hash small", title: e.hash }, (e.hash || "").slice(0, 10)))))))));
  } catch (e) { clear(els.aTable, errorBox(e, loadAudit)); }
}

function show() {
  els.purpose.refresh();
  fillCams(els.csvCam, els.searchCam);
  loadAudit();
}

export default { id: "reports", title: "Reports", icon: "reports", init, show, refresh: loadAudit };
