// PRAHARI console — the live alert store. One EventSource for the whole page;
// views subscribe to its events instead of opening their own connections.
//
// events: "status" {state: connecting|live|reconnecting|offline}
//         "new"    {alert}   an alert this page had not seen before
//         "change"            the alert list changed (ack, resync, new)

import { get, post, prefs } from "./api.js";

const STREAM = "/api/alerts/stream";
const KEEP = 500;

class LiveAlerts extends EventTarget {
  constructor() {
    super();
    this.alerts = new Map(); // id -> alert
    this.state = "connecting";
    this.loaded = false;
    this.loadError = null;
    this.es = null;
    this.retryMs = 2000;
    this.retryTimer = null;
    this.started = false;
  }

  start() {
    if (this.started) return;
    this.started = true;
    this.resync();
    this.connect();
    // Reconnect promptly when the laptop wakes up / tab returns.
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && (!this.es || this.es.readyState === EventSource.CLOSED)) this.reconnectNow();
    });
    window.addEventListener("online", () => this.reconnectNow());
  }

  setState(state) {
    if (this.state === state) return;
    this.state = state;
    this.dispatchEvent(new CustomEvent("status", { detail: { state } }));
  }

  /** Reload the latest alerts from the API (after connect / reconnect). */
  async resync() {
    try {
      const r = await get("/api/alerts", { limit: 300 });
      const fresh = new Map();
      for (const a of r.alerts || []) fresh.set(a.id, { ...(this.alerts.get(a.id) || {}), ...a });
      // Keep anything the stream delivered that the list didn't include.
      for (const [id, a] of this.alerts) if (!fresh.has(id)) fresh.set(id, a);
      this.alerts = fresh;
      this.loaded = true;
      this.loadError = null;
    } catch (e) {
      this.loadError = e;
    }
    this.trim();
    this.dispatchEvent(new Event("change"));
  }

  connect() {
    clearTimeout(this.retryTimer);
    if (this.es) { try { this.es.close(); } catch { /* ignore */ } }
    this.setState(this.state === "live" ? "reconnecting" : this.state);
    let es;
    try {
      es = new EventSource(STREAM);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.es = es;
    let wasDown = this.state !== "connecting";
    es.onopen = () => {
      this.retryMs = 2000;
      this.setState("live");
      if (wasDown) this.resync(); // fill anything missed while disconnected
      wasDown = true;
    };
    es.onmessage = (ev) => {
      let a;
      try { a = JSON.parse(ev.data); } catch { return; }
      if (!a || a.id === undefined) return;
      const isNew = !this.alerts.has(a.id);
      this.alerts.set(a.id, { ...(this.alerts.get(a.id) || {}), ...a });
      this.trim();
      if (isNew) this.dispatchEvent(new CustomEvent("new", { detail: { alert: a } }));
      this.dispatchEvent(new Event("change"));
    };
    es.onerror = () => {
      // The browser retries by itself while readyState is CONNECTING; if it gave up
      // (CLOSED, e.g. the server answered with an error) we retry with backoff.
      this.setState("reconnecting");
      if (es.readyState === EventSource.CLOSED) this.scheduleReconnect();
    };
  }

  scheduleReconnect() {
    clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(() => this.connect(), this.retryMs);
    this.retryMs = Math.min(this.retryMs * 2, 30000);
  }

  reconnectNow() {
    this.retryMs = 2000;
    this.connect();
  }

  trim() {
    if (this.alerts.size <= KEEP) return;
    const keep = this.sorted().slice(0, KEEP);
    this.alerts = new Map(keep.map((a) => [a.id, a]));
  }

  /** Newest sighting first. */
  sorted() {
    return [...this.alerts.values()].sort((a, b) => (b.ts || 0) - (a.ts || 0) || b.id - a.id);
  }

  openCount(kind) {
    let n = 0;
    for (const a of this.alerts.values()) if (a.status === "open" && (!kind || a.kind === kind)) n++;
    return n;
  }

  async ack(id, note) {
    const a = await post(`/api/alerts/${encodeURIComponent(id)}/ack`, note ? { note } : {});
    this.alerts.set(a.id, { ...(this.alerts.get(a.id) || {}), ...a });
    this.dispatchEvent(new Event("change"));
    return a;
  }
}

export const live = new LiveAlerts();

// ---------------------------------------------------------------- sound
let audioCtx = null;

export const sound = {
  get enabled() { return prefs.get("prahari.sound", "off") === "on"; },
  set enabled(v) {
    prefs.set("prahari.sound", v ? "on" : "off");
    if (v) this.unlock();
  },
  unlock() {
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === "suspended") audioCtx.resume();
    } catch { audioCtx = null; }
  },
  /** Two rising tones for an alert, one soft tone for a review item. */
  play(kind) {
    if (!this.enabled) return;
    this.unlock();
    if (!audioCtx) return;
    const tones = kind === "alert" ? [[880, 0], [1175, 0.18], [880, 0.36], [1175, 0.54]] : [[660, 0]];
    const t0 = audioCtx.currentTime + 0.02;
    for (const [f, dt] of tones) {
      const o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.type = "sine";
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t0 + dt);
      g.gain.exponentialRampToValueAtTime(kind === "alert" ? 0.25 : 0.12, t0 + dt + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.16);
      o.connect(g).connect(audioCtx.destination);
      o.start(t0 + dt);
      o.stop(t0 + dt + 0.18);
    }
  },
};
