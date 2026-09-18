# Part 4 — The Solution: **PRAHARI**

> **Prahari** (પ્રહરી / प्रहरी) — *"sentinel", "the one who keeps watch."*
> The hackathon is called **Sentinel**. This is its name in Gujarati. Use their word back at them.

**One-line thesis:**
> **Move meaning, not megabytes.** Video stays where it is born. Only *observations* cross the state. The registry is not an inventory — it is the brain.

**Declared model:** **Hybrid / Innovative (Model 5)** = **Model 1 (mandatory registry)** + **Model 3 (federation middleware)** as the spine + **Model 2 (direct connect)** for cameras with no local host + **Model 4's analytics without Model 4's cost.**
**Model 4 is explicitly considered and rejected — with arithmetic.** That rejection is a feature of the submission, not an omission.

---

## 1. Architecture

```
  ┌─ DEPARTMENT PREMISES (x26) ─ video never leaves ────────────────┐
  │                                                                  │
  │   Existing cameras / NVR / DVR / VMS  (UNCHANGED, UNTOUCHED)     │
  │            │ RTSP · ONVIF · vendor SDK · HLS  (LAN only)         │
  │            ▼                                                     │
  │   ╔══════════════════════════════════════════════════╗           │
  │   ║  PRAHARI NODE   (software-only, one container)   ║           │
  │   ║  · protocol adapters      · capability profiler  ║           │
  │   ║  · detect / ANPR / ReID   · disk store-&-forward ║           │
  │   ║  · local 72h evidence ring buffer                ║           │
  │   ╚══════════════════════════════════════════════════╝           │
  └────────────────────│ OUTBOUND ONLY (mTLS 443). No inbound port. ─┘
                       │  events ~200 B  ·  crops ~10 KB  ·  NO video
                       ▼
  ┌─ STATE / SCRB ─────────────────────────────────────────────────┐
  │   GATEWAY → INGEST → SCREEN → EXPLOIT     (UK NAS pipeline)     │
  │      │        │        │         │                              │
  │   authn   normalise  watchlist  trace · search · analytics      │
  │           + dedupe    match                                     │
  │                                                                 │
  │   REGISTRY (Model 1)  ·  MATCH  ·  TRACE  ·  VAULT  ·  SHIELD   │
  │   PostgreSQL + PostGIS + TimescaleDB · NATS/Kafka · object store │
  └──────────────────────────────┬──────────────────────────────────┘
                                 ▼
        CONSOLE — 50-tile adaptive wall · GIS · alerts · trace timeline
        Clip pull-on-demand: state asks node for ONE 30s clip, by case ID
```

**The eight components:**

| Component | Role | Maps to |
|---|---|---|
| **Registry** | Living camera inventory + GIS + health + **measured capability** | **Model 1 (mandatory)** |
| **Node** | Edge agent: adapters, local inference, store-and-forward | Model 2/3 boundary |
| **Bus** | Schema'd event backbone, at-least-once, replayable | Model 3 |
| **Match** | Watchlist correlation, confusion-aware | Model 4 analytics |
| **Trace** | Cross-camera route reconstruction | Bonus: multi-camera correlation |
| **Vault** | Hash-sealed evidence, chain of custody | Bonus: auditability → **NFSU** |
| **Shield** | RBAC, purpose-binding, DPDP audit | Bonus: cybersecurity/privacy |
| **Console** | Operator UI: wall, map, alerts, trace | Criteria 1, 4, 5 |

---

## 2. The five novel claims

These are the defensible, differentiating contributions. Each one is also *visible on screen* — innovation the jury cannot see does not score.

### **A. Camera Capability Auto-Profiling (CCAP)** — *the flagship idea*

**The problem it kills:** the sandbox grid draws from Health, Panchayat, GSRTC, Municipal and Police. Hospital corridors and panchayat gates will never show a number plate. A pure-ANPR system shows **dead panels across half the evaluation grid, on stage.**

**What it does:** on onboarding, the node watches a camera for ~60 seconds and *measures* it — then keeps re-measuring:

```json
{
  "camera_id": "GJ-HLT-0142",
  "scene_class": "corridor",         // road_junction | corridor | gate | counter | platform | yard
  "plate_legibility": 0.06,          // measured, not assumed
  "est_plate_px_height": 4.1,        // px -> is ANPR even physically possible?
  "motion_density": 0.31,
  "night_capable": true, "codec": "h265", "true_fps": 12.4,
  "recommended_pipelines": ["person_detect", "loitering", "crowd_density"],
  "anpr_viable": false,
  "confidence": 0.91
}
```

Every camera gets the analytic it can actually support. **Result: 50 live tiles, 50 working analytics — not 20 working and 30 dark.**

**Why it wins beyond the demo:** the organisers explicitly asked for *"technical prerequisites and information required from participating departments to assess camera integration feasibility."* They are asking teams to design a survey form — because **they do not know what their own 80,000 cameras can do.**

> Your answer: **"We require nothing from the departments. The system measures it itself, and the registry populates itself."**

That is the single most powerful sentence available in this competition. It converts the mandatory-and-boring Model 1 into the crown jewel, and it scales: 80,000 cameras cannot be surveyed by hand, but they can profile themselves.

---

### **B. Grammar-Constrained Plate Decoding + Confusion-Space Matching** — *wins the live test*

**The problem it kills:** every competing team ships `SELECT * FROM watchlist WHERE plate = ?`. One wrong OCR character → zero alerts → the money moment dies on stage.

**Three layers:**

**1. Decode under the Indian plate grammar.** A valid Indian plate is not an arbitrary string:
```
^[A-Z]{2} \d{1,2} [A-Z]{0,3} \d{4}$     + BH-series, old-format, vanity variants
  │        │        │          └─ always 4 digits
  │        │        └─ letters only
  │        └─ RTO district code — must be VALID FOR THAT STATE
  └─ state code — must be a REAL state code (GJ, MH, RJ, ...)
```
Feed this as a constraint into decoding (constrained beam search over the OCR posterior) instead of accepting free-form text. A raw read of `6J 01 A8 I234` is impossible under the grammar; the constrained decode resolves it to `GJ 01 AB 1234` — because `6J` is not a state code and `GJ` is, and position 6 must be a letter. **Structure is free accuracy.**

**2. Match in confusion space, not string space.** Weighted edit distance where the substitution cost comes from the *actual* OCR confusion matrix:
```
cost(O→0)=0.1   cost(I→1)=0.1   cost(B→8)=0.15   cost(S→5)=0.15
cost(G→6)=0.2   cost(Z→2)=0.2   cost(D→0)=0.25   cost(A→4)=0.3
cost(G→X)=1.0   ... (unrelated substitutions stay expensive)
```
Return **ranked candidates with posteriors**, never a bare hit/miss.

**3. Never return empty.** If nothing clears the alert threshold, the console shows a **"near miss" panel** — ranked candidates with evidence crops for one-click operator confirmation. On stage, "no result" reads as failure; "here are 4 ranked candidates, here are the crops, here is #1 at 0.87" reads as a *working investigative tool.*

**Expected effect on the live evaluation:** competitors find the designated vehicle at ~3 cameras. You find it at 8–12. Same footage, same models — **better matching primitive.**

---

### **C. Re-ID-Bridged Trajectory** — *cross-camera tracking that survives unreadable plates*

When the plate is unreadable at camera N (angle, night, glare, obscured), the route breaks. Bridge it:

1. **Anchor** on high-confidence plate reads
2. **Bridge** gaps with vehicle appearance embedding + type + colour
3. **Gate** every candidate by **travel-time feasibility** on the road graph — if camera A → camera B is 4.2 km, a 40-second transit implies 378 km/h and is rejected as physically impossible
4. **Emit confidence per hop**, with an auditable reason

```
14:02:11  CAM-0417 Rajkot Ring Rd    PLATE  0.94  ██████████
14:09:38  CAM-0422 Gondal Chowkdi    ReID   0.71  ███████░░░  (plate occluded; 7.3km/7m27s = 58 km/h ✓)
14:21:05  CAM-0491 NH-27 Toll        PLATE  0.89  █████████░
```

Honest, explainable, forensically defensible. **Directly targets the named bonus criterion "advanced cross-camera vehicle movement tracking or multi-camera correlation"** — and the physical-plausibility gate is what separates this from a similarity search.

---

### **D. Zero-Inbound, Zero-Change Onboarding** — *the mechanism-design piece*

The node **dials out** over mTLS/443. The state never connects *in*.

What a department must do to join: **nothing.** No firewall change (the #1 real-world blocker), no port forwarding, no public IP, no VMS change, no AMC renegotiation, no video leaving their premises, no loss of control.

What they get on day one, free: camera health monitoring they don't currently have, a GIS gap-analysis map of their own estate, their own analytics, evidence they can cite in AMC disputes, and a revocation switch they control.

> This is the **South Korea lesson without the statute**: make joining *individually rational* for each of the 26 departments rather than mandated. It converts a 5-year political negotiation into a 6-month rollout — and it is the answer to the organisers' *actual* problem, which is organisational, not technical.

---

### **E. The Bandwidth Ladder** — *works in Dahod and on the border*

The node measures its uplink continuously and **degrades along a ladder** rather than failing:

| Tier | Uplink | What is sent |
|---|---|---|
| 4 | > 10 Mbps | events + crops + periodic thumbnails + live relay on request |
| 3 | 2–10 Mbps | events + crops |
| 2 | 0.2–2 Mbps | events + crops **only for watchlist hits** |
| 1 | < 200 kbps | events only, compressed, batched |
| 0 | offline | **disk-backed queue** — keeps running, syncs on reconnect |

Tier 0 is the one that matters: a node in a border block keeps detecting through a two-day outage and backfills on reconnect. **Nothing is lost.** Directly targets the bonus criterion *"strong edge-processing, bandwidth-optimisation, or low-connectivity operation."*

---

## 3. Why this is the right answer, in numbers

The cost-benefit table the organisers explicitly asked for and nobody else will build properly. **Every figure gets replaced by a measured one after the load test — measurements are the whole point.**

| | Model 4 (central VMS) | **PRAHARI (federated)** |
|---|---|---|
| Sustained backbone | **~160 Gbps** | **~0.39 Gbps** (~400× less) |
| Central storage, 30 d | **~51.8 PB** | ~metadata + evidence crops only |
| Central GPUs | **~2,000** | ~0 (inference at the edge) |
| Dept. firewall changes | 26 negotiations | **0** |
| Dept. loses video control | Yes | **No** |
| Works during a WAN outage | No | **Yes** (tier 0) |
| Onboarding a new department | Re-architect | Deploy one container |
| Realistic time-to-statewide | Years | Months |

> **The slide that wins the architecture criterion: `160 Gbps → 0.39 Gbps`.**
> One number, derived from first principles, that justifies the entire design and quietly demolishes every Model 4 submission in the room.

---

## 4. Evidence integrity — the NFSU play (§Vault)

NFSU is the **National Forensic Sciences University**. Admissibility is their entire discipline. Nobody else will build for them.

- Every exported clip/crop: **SHA-256 hashed at the edge, at the moment of capture**
- **Signed manifest**: camera ID, PTS + wall-clock, operator, case ID, purpose, model + version that generated the detection
- **Append-only, hash-chained audit log** — tamper-evident
- Model **provenance** recorded per detection (which weights produced this alert?) — essential when a detection is challenged in court
- Export bundle verifiable **offline**, by a third party, without the platform

This is one focused subsystem, buildable in ~a day, aimed squarely at a known evaluator on the panel.

## 5. Privacy by design — the DPDP play (§Shield)

India's **DPDP Act 2023** is live, and *K.S. Puttaswamy* (2017) requires proportionality for state surveillance. A surveillance platform with no rights architecture is not deployable — and the organisers know it.

- **Purpose-bound queries**: every watchlist lookup requires a stated purpose + case ID. No anonymous trawling.
- **RBAC** with graduated authority: constable / investigator / supervisor / auditor
- **Tiered retention**: events 1 yr · crops 90 d · clips 30 d — configurable per department, enforced by the system
- **Face recognition off by default**, behind explicit supervisory authorisation (proportionality)
- Full **immutable access audit** — who looked at what, when, why
- **Private cameras**: consent artifact per camera, owner-revocable, default tier "registered" not "live ingest"

> Note the framing for the deck: this is not a compliance burden. It is **what makes a system a police *evidence* platform rather than a surveillance liability** — and it is the reason the state can actually deploy it.

---

## 6. Deliberate mapping to the official bonus list

The organisers published exactly six bonus items. Hit all six, on purpose:

| Official bonus criterion | Our component |
|---|---|
| Innovative hybrid/customised architecture with operational value | Model 1+3+2 hybrid; Model 4 rejected with arithmetic |
| Advanced cross-camera tracking / multi-camera correlation | **§C** Re-ID-bridged trajectory with physical-plausibility gating |
| Additional reliable analytics beyond mandatory ANPR | **§A** CCAP-driven per-camera pipelines (person, loitering, crowd, intrusion) |
| Strong edge processing / bandwidth optimisation / low connectivity | **§E** Bandwidth ladder + tier-0 offline operation |
| Enhanced cybersecurity, privacy, auditability, RBAC | **§Vault** + **§Shield** (NFSU + DPDP) |
| Operational dashboards, alerts, health monitoring, integration-ready APIs | Console + Registry health + documented OpenAPI |

**6 of 6. Not by accident.**

---

## 7. Technology choices (optimised for 10 days, honest about it)

| Layer | Choice | Why |
|---|---|---|
| Node runtime | Python + FFmpeg/GStreamer, packaged in Docker | Fastest path; matches their suggested stack |
| Detection | YOLO-family, ONNX Runtime / TensorRT | CPU-viable fallback is essential for demo safety |
| Plate OCR | Fine-tuned recogniser + **grammar-constrained decode** | §B — the differentiator |
| Vehicle Re-ID | Lightweight appearance embedding + colour/type | §C |
| Bus | **NATS JetStream** (Kafka-compatible story for the HLD) | Runs in one binary — demo-safe; Kafka named as the production path |
| Store | PostgreSQL + **PostGIS** + **TimescaleDB** | Exactly their suggested stack; time-series is the right shape for events |
| Evidence | MinIO (S3-compatible) | Their suggested stack; matches production object storage |
| Console | React + MapLibre/Leaflet + HLS.js / WebRTC | Their suggested stack |
| Deploy | Docker Compose (demo) → Kubernetes (HLD) | **Everything runs offline on one laptop. Non-negotiable.** |

> **Hard demo rule:** a full cold start on a laptop with **no internet**, in under 2 minutes, every time. Cloud is a Phase-2 story in the HLD, never a demo dependency. A crashed demo scores zero regardless of how good the architecture was.

---

## 8. Sandbox contract — read this or die in Phase 2

From the official Resources page, these are non-negotiable engineering constraints:

- **`GET /api/ingest` is the contract. The URL pattern is NOT.** Camera IDs and the camera set can change. **Hardcode nothing** — a team that hardcodes 50 URLs dies on stage when the finale feeds differ.
- **Force RTSP over TCP** everywhere (`rtsp_transport=tcp`). UDP silently corrupts frames across NAT and reads as model failure.
- **Drive all timing from PTS**, never from frame arrival time. On connect the gateway replays a buffered GOP — frames arrive faster than real time, and an arrival-timestamped tracker computes impossible velocities on **every single reconnect**. Kalman filters must be fed PTS deltas.
- **Never trust `CAP_PROP_FPS`.** Measure the real rate. Any speed/dwell metric derived from the declared FPS is wrong.
- **Assume non-uniform frame intervals.** Gaps are not disconnects.
- **Reconnect with exponential backoff** (~2 s → cap ~30 s). Feeds are supervised and restart.
- **Decoder warnings at join are normal** (`Error constructing the frame RPS`, `Could not find ref with POC`) — self-correct at the first IDR. A pipeline that aborts on the first decoder error will bounce forever on the H.265 streams.
- **Mixed H.264/H.265, mixed resolution, mixed fps.** A fixed-shape inference batch will not work. Read per-camera properties from `/api/ingest`.
- **Each feed loops** → hard scene discontinuity, like a camera reboot. Background models, Re-ID galleries and track IDs must **recover from a hard cut**, not assume continuity.
- **No footage downloads.** `/stream/<id>` answers range requests, so `curl` yields a partial file that *looks* complete — a trap. Build against live capture from day one.
- **Consume only.** Never publish to the gateway, never call its control API.
- **Pace your load** — each client gets its own copy of the stream. Open only what you process.

> These constraints are not incidental. They are a **deliberate filter** the organisers built to separate production-ready teams from prototypes. Their own pre-submission checklist is reproduced in `05-scorecard.md`. Treat every line as a scored item.
