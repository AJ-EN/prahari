# Part 6 — The 10-Day Build Plan

**Today: 18 Sep 2026 · Submit: 28 Sep 2026 · Finale: 12–13 Oct 2026**

**Sequencing principle:** build in the order that *de-risks the demo*, not the order that is architecturally tidy.
Anything that can fail on stage gets built and hardened first. Polish is last and is expendable.

---

### 🔴 DAY 0 — TODAY, BLOCKING (do before any code)
- [ ] **Register on the portal.** Nothing else matters; feed access is gated behind it.
- [ ] **Decide Category 1 vs 2** → `02-game-theory-and-win-strategy.md` §1.2
- [ ] **Email organisers**: resolve top-3-per-category vs top-6-pooled (materially changes strategy)
- [ ] `curl -s http://<host>/api/ingest` → **archive the full catalogue**; count cameras, codecs, resolutions
- [ ] Verify RTSP/TCP reachability; confirm the HLS fallback works if 8554 is blocked
- [ ] Record 10 minutes from 3 different cameras locally for offline development

### DAY 1–2 — Ingest spine (highest technical risk → do first)
- [ ] `/api/ingest` catalogue poller → Registry (**zero hardcoded URLs, ever**)
- [ ] Node: RTSP-over-TCP capture, **PTS-driven** timing, mixed H.264/H.265
- [ ] Reconnect with exponential backoff (2 s → 30 s); decoder warnings logged not fatal
- [ ] Scene-discontinuity (loop point) recovery: reset trackers, Re-ID gallery, background model
- [ ] **Prove all ~50 streams stay up unattended for 60 minutes.** This single test de-risks the demo.
- [ ] Postgres + PostGIS + TimescaleDB schema; NATS JetStream bus; event schema v1

### DAY 3–4 — Registry + CCAP + Console skeleton *(the mandatory model, made the crown jewel)*
- [ ] Registry CRUD + **bulk import / manual entry / API onboarding** (all three are graded)
- [ ] **CCAP**: 60 s scene profiling → scene class, plate legibility, est. plate px height, recommended pipelines
- [ ] GIS map: department / type / status / coverage layers
- [ ] Health monitoring + **gap-analysis report generator**
- [ ] Console: **50-tile adaptive video wall** (decode only what is visible), alert queue, map

### DAY 5–6 — The money path: ANPR → watchlist → alert → trace
- [ ] Vehicle + plate detection; plate OCR
- [ ] **§B grammar-constrained decoding** (state codes, RTO codes, position constraints)
- [ ] **§B confusion-weighted matching** + ranked candidates + **"near miss" panel** (never return empty)
- [ ] Watchlist schema + seed data + continuous correlation + real-time alert generation
- [ ] **§C Trace**: plate-anchored route + Re-ID bridging + travel-time feasibility gating
- [ ] GIS route rendering + timestamped movement history + exportable report

### DAY 7 — The uncontested ground
- [ ] **§Vault**: SHA-256 at capture, signed manifest, hash-chained audit log, offline-verifiable export
- [ ] **§Shield**: RBAC, purpose-bound queries + case ID, retention tiers, immutable access audit
- [ ] **§E bandwidth ladder** + tier-0 disk-backed store-and-forward (kill the WAN and prove it)
- [ ] Government DB adapters (VAHAN / SARTHI / eGujCop / AFIS / NAFIS) — documented interface + mocks
- [ ] Non-traffic analytics from CCAP: person, loitering, crowd density, intrusion

### DAY 8 — Measure. This is the criterion nobody else will satisfy.
- [ ] **Load test**: streams per node, p95 latency, CPU/GPU/RAM, event throughput
- [ ] **ANPR benchmark** on real feeds: precision/recall, with an honest failure analysis
- [ ] Extrapolate → node count → **₹-crore cost table vs central VMS**
- [ ] Bandwidth measurement → validate the 160 Gbps vs 0.39 Gbps claim **with real data**
- [ ] DR/HA design; statewide phased rollout plan

### DAY 9 — Documents (allow a full day; this is 3 of 7 criteria)
- [ ] Solution Presentation (PPT/PDF) — `05-scorecard.md` §A1
- [ ] HLD — `05-scorecard.md` §A2, all 8 items
- [ ] Own-feed demo video (2–3 min, working software only)
- [ ] Government-feed demo video **+ output report with plates and timestamps**
- [ ] Registry API docs (OpenAPI), adapter architecture doc, federated analytics report, gap-analysis report

### DAY 10 (27 Sep) — Submit at T-48h, then keep building
- [ ] Walk **every** line of `05-scorecard.md`
- [ ] Verify every link from a logged-out incognito browser
- [ ] Hosted URL + test credentials; repo link
- [ ] **Submit.** Do not touch the deadline.

### 28 Sep → 12 Oct — Finale hardening (14 days, ignored by most teams)
- [ ] Cold-start rehearsal: **no internet, laptop only, under 2 minutes, ten times in a row**
- [ ] Chaos drills: kill feeds, kill the network, kill a node mid-demo
- [ ] Feature flags for everything — any component disableable in 5 seconds on stage
- [ ] Pre-recorded fallback video, queued and ready
- [ ] Rehearse the 60-second trace narrative for a non-technical audience
- [ ] Prepare for **unfamiliar live feeds on the day** — generic onboarding, zero assumptions

---

## Standing rules
1. **Nothing hardcoded.** `/api/ingest` is the contract; the URL pattern is not.
2. **Runs fully offline.** No cloud in the demo path, ever.
3. **Every feature behind a flag.** Stage-disableable in 5 seconds.
4. **Degrade, never crash.** One dead camera must never stall the wall.
5. **Never return empty.** Ranked candidates with evidence beat "no results" every time.
6. **Measure, don't claim.** Every number in the deck traceable to a real run.
7. **Reliability outranks ambition.** A crashed demo scores zero.
