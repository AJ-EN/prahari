# PRAHARI: infrastructure sizing and cost-benefit for about 80,000 cameras

This document is generated from **`bench/sizing_model.py`**. Every table below comes from that script. To test a
different assumption, edit the field in the `Assumptions` class and re-run:

```bash
.venv/bin/python bench/sizing_model.py        # prints every table and writes docs/hld/sizing.json
```

**Labels.** Every number has one of four labels. **MEASURED** means a file or benchmark in this repository, cited by
path. **GIVEN** means it comes from the organisers or the public record. **PRICE** means a market price, cited in
§10. **ASSUMED** means our estimate, with its basis and a confidence rating. Anything else is **DERIVED**, and the
formula is shown. All money is in ₹, **excluding 18% GST**. 1 lakh (L) = 10⁵ and 1 crore (Cr) = 10⁷. The figures
are accurate to about ±30% and are rounded to match. We do not claim more precision than that.

---

## 0. Corrections to our own earlier documents (read first)

| Earlier claim | Status | Corrected figure |
|---|---|---|
| Doc 01 §3.3: **"160 Gbps → 0.39 Gbps, ~400×"** | **The arithmetic is correct for its inputs.** Recomputed: 24,000 cams × 0.2 veh/s = 415 M events/day. At 200 B + 10 KB each, that is 392 Mbps, or 410×. **But the inputs are off, and in both directions.** The doc assumed 3.4× too many plate events: 0.2 veh/s around the clock on *every* traffic-facing camera, including departmental gates. It also assumed 1.5× too small a crop. It left out telemetry, clip pulls and protocol overhead. And it compared *average* flows, while a link has to be provisioned for the peak. | **Average ≈ 0.21 Gbps; peak hour ≈ 0.45 Gbps.** The ratio is **~750× on averages and ~360× at peak.** For a link you have to buy, peak is the honest basis. Across every sensitivity case the ratio stays between **110× and 5,500×**. **Recommended headline: "160 Gbps → under 0.5 Gbps at peak (~350×)".** The conclusion stands. The number changes. |
| Doc 01 §3.1 / doc 04 §3: **"~2,000 central GPUs vs ~0"** | **Overstated.** 2,000 GPUs buys continuous analytics at full video rate. A central system that ran the *same* 1-fps ANPR + 0.2-fps light analytics as PRAHARI would need about **224 L4s**. In the central case, decode is the limit, not inference. PRAHARI also has GPUs: **166 L4s at the Netram centres**, plus about 3,450 small edge nodes. | The case against Model 4 does **not** rest on GPUs. It rests on **WAN bandwidth (≈ ₹60 Cr/yr)** and **52 PB of video storage.** Those two costs remain even in the most favourable version of Model 4 (§7). |
| README: **"roughly 40 cameras at one frame per second"** per machine | That is the naive figure: 1000 / 21 ms = 47. It is correct for synthetic frames on the M1. | Planning figure: **~14 ANPR streams per M1-class worker at 1 fps**, after a ×2 safety factor for real footage and 60% target utilisation (§4). |
| Brief/README: 48-camera stability figures (43% / 369 MB keyframes; 181% / 581 MB full decode) | These figures are quoted, but **their raw JSON is not in `data/`**. Only the 12-camera runs were kept. | This model uses the 12-camera files. They agree per camera: full decode 3.7% vs 3.8% of a core per camera. |

---

## 1. Headline numbers (80,000 cameras, base case)

| | PRAHARI (federated) | Model 4 (central VMS + AI) |
|---|---|---|
| Sustained backbone | **0.21 Gbps avg / 0.45 Gbps peak** | **160 Gbps** at 2 Mbps; 320 Gbps at 4 Mbps |
| Ratio | **~360× at peak** (750× on averages) | |
| Plate events | 124 M/day. 1,400/s average, **3,100/s peak** | same |
| Edge / GPU compute | **83 GPU servers (166 L4) at 34 Netram + 3,455 edge mini-PCs** | 2,000 GPUs as usually specified (224 L4s for the same analytics) + 445 recording servers |
| Central storage | **~210 TB logical / ~630 TB raw** (all copies, erasure coding and DR included) | **52 PB** for 30 days of video, one copy |
| Capex | **₹49 Cr** | ₹101 Cr (steelman) to ₹175 Cr (as specified, infrastructure only). **₹312 Cr** with commercial licences |
| Opex per year | **₹18 Cr** | ₹84–95 Cr (infrastructure only). ₹119 Cr with licence support |
| **5-year TCO** | **≈ ₹130 Cr** | **≈ ₹510–640 Cr** (infrastructure only). ≈ ₹870 Cr with licences |
| Per camera | ₹6,100 capex; ₹3,300 per year all-in over 5 years | ₹12,700–21,800 capex; ₹12,800–16,000 per year |

**The fairest single comparison** sets PRAHARI against the Model 4 steelman: the same analytics, no licences, and
only the GPUs it actually needs. That comparison is **₹130 Cr vs ₹510 Cr over 5 years, about 4×.** The difference is
mostly the WAN bill, which recurs every year.

---

## 2. Assumptions

Only the assumptions that matter are listed here. The full list, with comments, is at the top of `bench/sizing_model.py`.

| # | Assumption | Value | Label and basis | Confidence |
|---|---|---|---|---|
| A1 | Cameras statewide | 80,000 | GIVEN: organisers | high |
| A2 | VISWAS cameras (police) | 17,500 | GIVEN: ph-I ~7,000 at ~1,200 junctions/entry points in 41 places + ph-II ~10,500 (Surat, Vadodara, 52 municipalities, 80 border points) | high |
| A3 | VISWAS video already terminates at the 34 Netram centres | yes | ASSUMED: Netram is the district command-and-control centre that views VISWAS feeds | medium-high |
| A4 | Traffic-facing (ANPR-viable) share, VISWAS / departmental | 60% / 20% → **29% overall** | ASSUMED. VISWAS is sited at junctions and entry points. Departmental cameras are mostly corridors, counters and yards (doc 01 §3.6). **CCAP measures this per camera (plate legibility, plate px height), so the registry *discovers* the true share in the first weeks of Phase 1. It is not a planning guess we are stuck with.** | medium / low |
| A5 | Vehicles per ANPR camera per day, VISWAS / departmental | 12,000 / 2,000 | ASSUMED: one approach of an urban junction averages ~500/h over the day. Gates and frontage roads carry far less | medium / low |
| A6 | Read yield (deduplicated plate events per vehicle pass) | 0.8 | ASSUMED: two-wheeler plates are rear-only; occlusion; night | medium |
| A7 | Peak-hour share of daily traffic (K-factor) | 9% → peak/avg = 2.16 | ASSUMED: standard traffic-engineering range 8–10% | high |
| A8 | ANPR analysis rate | 1 fps at junctions; **4 fps at the 10% of cameras on highways and entry points** → mean 1.3 fps | DERIVED: at 60 km/h a vehicle crosses a ~15 m view in 0.9 s, so 1 fps can miss it | medium |
| A9 | Light analytics (person / crowd / intrusion) | 0.2 fps, 50 events/cam/day, 10% with an image | design / ASSUMED | low |
| A10 | Event size on the wire | 550 B (+15% TLS/HTTP framing) | **MEASURED**: mean JSON of stored plate events incl. 5 ranked candidates, `data/demo.db`, 281 rows = 547 B | high |
| A11 | Evidence crop (plate + vehicle context) | 15 KB | ASSUMED. **MEASURED** synthetic plate crops average 5.2 KB (360×141, 2,196 files in `data/evidence/`). Real footage is noisier, and a vehicle crop is added | medium |
| A12 | Clip pulls | 2,000/day × 30 s × 4 Mbps | ASSUMED: ~60 per district per day | low |
| A13 | ANPR cost per frame (M1) | 21 ms p90 at 960 px with a plate; 3.8 ms without; 40.8 ms at 1280 px | **MEASURED**: `prahari.anpr.bench`, saved in `docs/hld/bench-anpr-m1.json` (CoreML detector, CPU OCR) | high (for M1, synthetic) |
| A14 | Software decode cost (M1) | 0.39% of one core per Mpix/s → **20% of a core per 1080p25 stream** | **MEASURED**: 12 cams, 111.7 Mpix/s, 43.8% CPU, `data/stability-20260924-225251-full5-22642.json` | high (for M1) |
| A15 | Keyframe-only decode (M1) | 0.52% of a core per camera | **MEASURED**: `data/stability-20260924-224549.json` (12 cams, 6.2%) | high |
| A16 | Production safety factor on per-frame cost | ×2 | ASSUMED: real 1080p footage, more plates per frame, night, bigger production models | medium |
| A17 | Target utilisation | 60% | design: headroom for bursts, reconnect storms, rebuilds | high |
| A18 | ANPR cameras whose GOP ≤ 1 s (keyframe decode is enough) | 30% | ASSUMED. The rest need full decode. CCAP reads the GOP from the stream | low |
| A19 | Departmental NVR sites | 50% × 6 cams, 35% × 20, 15% × 60 → mean 19 → **~3,300 sites** | ASSUMED. The registry replaces this with real data | low |
| A20 | Relative performance vs one M1 worker | EDGE-S ×1.5, EDGE-M ×2, EDGE-L (2× L4) ×20 | ASSUMED: **not measured on the target hardware** | low-medium |
| A21 | Hardware decode capacity (1080p25 streams) | EDGE-S 24, EDGE-M 18, EDGE-L 256 | Orin NX: **18× 1080p30 H.265** (NVIDIA datasheet). L4: **4 NVDEC** (datasheet) × ~32 streams each (ASSUMED). QuickSync 24 (ASSUMED) | medium |
| A22 | Event row on disk (hot) | 1,050 B incl. indexes | **MEASURED** upper bound: `data/demo.db` 294,912 B / 281 rows | medium |
| A23 | Retention | events hot 90 d, warm to 1 y; crops 90 d; clips 30 d; case-linked events, crops and clips cold for 7 y | policy (doc 04 §5). **We deliberately do not keep all plate reads for 7 years** (DPDP proportionality). The UK NAS keeps them 1 year | policy |
| A24 | Model 4 video | 2 Mbps/cam, 30 d retention, 40 streams/GPU, 600 Mbps per recorder, 4,000 WAN sites | ASSUMED (doc 01) | medium |
| A25 | WAN price, Model 4 | ₹250 per Mbps-month on 1.25× sustained | PRICE: ILL ₹25–38k/month for 100 Mbps (₹250–380/Mbps); ₹1.5 L for 1 Gbps (₹150/Mbps) | **low: the biggest swing factor (§8)** |
| A26 | DC facility | ₹15,000 per kW IT per month, all-in | PRICE: Indian colocation ₹8k–25k/kW-month. Cross-check: ₹9/kWh × 730 h × PUE 1.6 = ₹10.5k for power alone | medium |
| A27 | Power | ₹9/kWh | PRICE: Gujarat HT effective ₹7.5–8.5/kWh; LT commercial is higher | medium |
| A28 | AMC | 8% of hardware per year, from year 2 | ASSUMED: typical Indian government AMC after warranty | medium |
| A29 | Staff (loaded, per year) | 12 NOC/SOC @ ₹15 L; 33 field engineers @ ₹8 L; PRAHARI platform team 15 @ ₹25 L; Model 4 +12 DC ops | ASSUMED | medium |
| A30 | Commercial licences (Model 4 only) | VMS ₹5k/channel, ANPR ₹30k/channel, basic analytics ₹5k/channel, +20%/yr support | ASSUMED: **low**. Shown separately so no conclusion depends on it | low |

---

## 3. Bandwidth

### 3.1 Statewide and per district

| quantity | value | how |
|---|---|---|
| camera mix | 23,000 ANPR + 57,000 light (29% ANPR) | A2 × A4 |
| events/day | 124 M plate + 2.8 M light | ANPR cams × A5 × A6 |
| events/s | **1,400 avg / 3,100 peak hour** | ÷ 86,400; × 2.16 |
| GB/day | events 68 · crops 1,820 · telemetry 86 · clips 30 → **~2.3 TB/day** | × A10, A11, 100 bps/cam, A12 |
| events only (text, no images) | **7 Mbps** statewide average | |
| everything | **210 Mbps avg / 450 Mbps peak** | |
| mean district (1/33) | 6.4 Mbps avg / 13 Mbps peak | |
| largest district (15% of cameras) | ~67 Mbps peak | |
| largest Netram (Surat or Vadodara, ~30% of VISWAS) | ~110 Mbps peak | |
| **Model 4 video** | **160 Gbps** at 2 Mbps; 320 Gbps at 4 Mbps; 1.73 PB/day | 80,000 × bitrate |
| **ratio** | **~750× average; ~360× peak** | |

Crops are 80% of PRAHARI's traffic. The bandwidth ladder therefore controls cost mainly through crops. At tier 2
(crops only for watchlist hits), statewide peak falls to **~30 Mbps**.

### 3.2 A departmental site, by bandwidth-ladder tier

| site | share of sites | tier 3/4 avg | tier 3/4 peak | tier 1 (events only, zstd) | tier 0: offline days a 100 GB queue holds | a 30 s clip at 512 kbps |
|---|---|---|---|---|---|---|
| 6 cams | 50% | 4 kbps | 25 kbps | 0.2 kbps | > 1 year | 4 min |
| 20 cams | 35% | 13 kbps | 83 kbps | 0.6 kbps | > 1 year | 4 min |
| 60 cams | 15% | 38 kbps | 250 kbps | 1.7 kbps | 240 days | 4 min |

**What this means for the low-bandwidth strategy.** A departmental site needs **tens of kbps, not Mbps**. A 4G
dongle or an existing GSWAN or broadband drop is enough. For a departmental site, "offline" is a latency problem.
It is not a data-loss problem. The queue does not fill. Only the Netram nodes carry real volume. The largest Netram
averages ~50 Mbps, or ~550 GB/day (DERIVED: 110 Mbps ÷ 2.16 × 86,400 s ÷ 8). **EDGE-L therefore gets a 2 TB NVMe
queue (~3.5 days of outage).** Clip pulls are the only transfer that needs bandwidth. On a thin link the clip
arrives in minutes rather than seconds, and the console shows its progress.

| Tier | Uplink | Sent | Statewide peak at this tier |
|---|---|---|---|
| 4 | > 10 Mbps | events + crops + thumbnails + live relay on request | ~450 Mbps + relays |
| 3 | 2–10 Mbps | events + crops | ~450 Mbps |
| 2 | 0.2–2 Mbps | events; crops only for watchlist hits | ~30 Mbps |
| 1 | < 200 kbps | events only, zstd-batched | ~6 Mbps |
| 0 | offline | disk queue; replays in order on reconnect | 0 |

---

## 4. Edge compute

### 4.1 Streams per node, derived from our measured per-frame time

Formula (`node_streams`): **streams = 1000 ms × util × perf ÷ (ms per frame × safety × fps)**. The number of
full-decode ANPR streams is also capped at hw_decode × util ÷ (1 − keyframe share).

| class | hardware | price (PRICE/ASSUMED) | power | ANPR @1 fps | ANPR @ mixed 1.3 fps | light-only @0.2 fps |
|---|---|---|---|---|---|---|
| M1 (measured) | 1 worker | – | – | 47 naive → **14 planned** | – | – |
| **EDGE-S** | Mini-PC, Intel Core Ultra (iGPU + NPU + QuickSync), 16 GB, 512 GB SSD | ₹75k (₹55k–1 L) | 35 W | 20 | 16 (inference-bound) | ~590 |
| **EDGE-M** | Jetson Orin NX 16 GB, fanless, 512 GB NVMe (rugged, no-AC sites) | ₹1.1 L (module ₹49k) | 25 W | 15 | 15 (decode-bound) | ~790 |
| **EDGE-L** | 2U server, 2× NVIDIA L4, 256 GB, 2 TB NVMe queue (at Netram) | ₹11.5 L | 650 W | 219 | 219 (decode-bound) | ~7,900 |

**Decode, not inference, is the edge bottleneck.** In software on the M1, one 1080p25 stream costs 20% of a core
(MEASURED, A14). Eight cores therefore full-decode only ~23 streams at 60% utilisation. Keyframe-only decode costs
~40× less, but it gives 1 fps only when the camera's GOP is ≤ 1 s. So every production node class has a hardware
decoder, and CCAP records each camera's GOP. Where a department allows it, a one-time camera setting change to
GOP = fps would double EDGE-L capacity. That is sensitivity case "All ANPR cams keyframe-decodable". Light analytics
is almost free: a single node can carry hundreds of those cameras.

### 4.2 Fleet for 80,000 cameras

| item | count | how |
|---|---|---|
| EDGE-L at Netram (VISWAS) | **49 working + 34 N+1 spares = 83 servers (166 L4)** | max(inference, decode) on 10,500 ANPR + 7,000 light, + 1 per Netram |
| Departmental NVR sites | ~3,300 (mean 19 cams) | A19 |
| EDGE-S | **3,290 + 5% spares = 3,455** | **one per site. The count is set by the number of sites, not by load.** Even a 60-camera site (12 ANPR) fits on one node |
| Edge power | ~170 kW, spread across 3,300 premises | |

The departmental edge costs ~₹26 Cr in hardware. We have assumed that every site buys a new node. Where a
department already has a PC beside its NVR (i5-class or newer), PRAHARI runs on that PC. At 40% reuse, capex falls
by ₹12 Cr (§8).

---

## 5. Regional (Netram) and central (SCRB / State Data Centre) tiers

### 5.1 Workload

| | value | how |
|---|---|---|
| Ingest | 1,400 events/s avg, **3,100/s peak** | §3 |
| Rows per year | **~45 billion** (124 M/day × 365) | |
| Hot rows (90 d) | ~11 billion, **~12 TB** per copy | × 1,050 B (A22) |
| Warm rows (to 1 y, compressed ×5) | ~7 TB per copy | |
| Watchlist screening | 3,100 events/s × 0.5 ms confusion-aware match ≈ 1.6 cores (3 pods, for HA) | ASSUMED 0.5 ms/event |
| Search / trace | 10,000 queries/day, ~0.5/s peak. Each fuzzy query expands to ≤ ~64 candidate plates and probes a (plate, ts) index in daily partitions | ASSUMED |
| Monitoring | ~1.5 M time series (3,538 nodes × 200 + 80,000 cams × 10) | ASSUMED per-node/per-cam series |

At this ingest rate a single PostgreSQL + TimescaleDB primary is enough. It needs daily chunks, a (plate, ts) btree,
and a trigram index for partial plates. The write rate is under 10% of what one tuned node handles with batched
inserts. Sharding (Citus, keyed by plate hash) becomes necessary only at roughly 10× today's event rate. A columnar
store such as ClickHouse is a reasonable alternative for the warm tier. The model does not depend on that choice.

### 5.2 Hardware

| tier | contents | count |
|---|---|---|
| **Central DC (primary)** | Kubernetes: ingest gateway ×3, event bus (NATS JetStream / Kafka) ×3, screen/match ×3, API + console + search ×3, registry/GIS/auth/audit ×3, monitoring ×4, control plane ×3 = **220 vCPU** | **4 app hosts** (2-socket, 512 GB, N+1) |
| | PostgreSQL + PostGIS + TimescaleDB: primary + synchronous standby (the standby serves search/trace reads) | **2 DB hosts**, ~19 TB NVMe each |
| | Object store (MinIO / Ceph, erasure coding 4+2) for crops, clips and case evidence | **6 storage hosts** (12 × 20 TB) |
| **DR site (warm standby)** | 50% of app compute, 1 async DB replica, full object store | **9 hosts** |
| **Regional: 34 Netram** | 2 servers per Netram (active/standby): district relay, **local watchlist cache and alerting**, district console, 7-day event cache, clip relay. Plus the EDGE-L servers from §4 | **68 servers** + 83 EDGE-L |
| Central IT power (DC + DR) | | ~12 kW |

The central tier is small because PRAHARI moves no video to it. That is deliberate. The whole central footprint for
statewide PRAHARI (DC + DR, 21 hosts) is smaller than **one row** of the Model 4 design, which needs 500 GPU servers
and 445 recorders.

---

## 6. Storage tiers

| tier | TB (one logical copy) | medium | copies |
|---|---|---|---|
| events hot, 90 d | 12 | NVMe, row store | 3 (primary, standby, DR) |
| events warm, 90 d – 1 y | 7 | NVMe/SSD, compressed chunks | 3 |
| events cold, case-linked, 7 y | 0.07 | object store (HDD) | EC 4+2 × 2 sites |
| crops hot, 90 d | **163** | object store | EC 4+2 × 2 sites |
| crops cold, case-linked, 7 y | 5 | object store | EC 4+2 × 2 sites |
| clips hot, 30 d | 1 | object store | EC 4+2 × 2 sites |
| clips cold, case-linked, 7 y | 23 | object store | EC 4+2 × 2 sites |
| event bus, 7-day replay | 1.4 (incl. ×3) | NVMe | ×3 |
| **total** | **~210 TB logical / ~630 TB raw** | | |
| *departmental video* | **not stored centrally.** It stays on departmental NVRs at their own 7–15-day retention (GIVEN, FAQ). Clips are pulled by case ID | | |
| *Model 4 video, 30 d* | **51,800 TB = 52 PB** (one copy; ~3,240 × 20 TB drives before overhead) | | |

Crops account for 77% of PRAHARI's central storage. Keeping every plate read for 7 years instead of 1 would add
~15 PB raw. It would also be disproportionate under the DPDP Act. So only case-linked records go to the cold tier.

---

## 7. Costs

### 7.1 Capex, ₹ crore, 80,000 cameras (ex-GST)

| PRAHARI | ₹ Cr | Model 4 (as specified, infrastructure only) | ₹ Cr |
|---|---|---|---|
| edge nodes + installation (83 EDGE-L, 3,455 EDGE-S, ₹15k install per node) | 40.5 | 500 GPU servers (2,000 L4) | 82.5 |
| central DC (hosts, NVMe, object store, network) | 2.5 | 445 recording servers | 28.9 |
| DR site | 2.2 | 52 PB video storage | 37.3 |
| regional (68 Netram servers) | 3.4 | core network (100G spine) | 8.0 |
| | | site WAN installs (4,000 × ₹30k) | 12.0 |
| | | metadata / DR / management | 6.0 |
| **PRAHARI capex** | **48.6** | **Model 4 capex** | **174.7** |
| | | + commercial VMS/ANPR/analytics licences, if bought | +137.5 |

### 7.2 Opex per year, ₹ crore

| PRAHARI | ₹ Cr/yr | Model 4 (infrastructure only) | ₹ Cr/yr |
|---|---|---|---|
| edge power (170 kW across sites) | 1.3 | **WAN bandwidth for video** (160 Gbps × 1.25 × ₹250) | **60.0** |
| regional power | 0.3 | DC facility (~630 kW IT) | 11.4 |
| DC + DR facility (~12 kW IT) | 0.2 | hardware AMC | 14.0 |
| central uplinks (2 × 1 Gbps at DC and at DR) | 0.7 | staff (NOC/SOC, DC ops, field) | 6.2 |
| Netram backup links (34 × 100 Mbps) | 1.2 | in-house platform team | 3.8 |
| new links for the 30% of sites without one | 1.8 | | |
| hardware AMC | 3.9 | | |
| staff (platform 15, NOC/SOC 12, field 33) | 8.2 | | |
| **total** | **17.6** | **total** | **95.4** (+ licence support 27.5 if licensed) |

**Staff is PRAHARI's largest opex line, at 47%.** Its infrastructure costs are small. Model 4's largest line is the
WAN, at 63%. **A field fleet of 3,455 edge nodes is PRAHARI's real operational burden.** At a 3–5% annual failure
rate that means ~100–170 site visits per year. We budget one field engineer per district plus 5% cold spares, and
the NVR keeps recording while a node is down.

### 7.3 Five-year TCO (capex + 5 years opex; AMC from year 2), ₹ crore

| design | capex | opex/yr | **5-yr TCO** |
|---|---|---|---|
| **PRAHARI (federated)** | 48.6 | 17.6 | **~133** |
| Model 4 **steelman**: same 1-fps analytics, 224 L4s, infrastructure only | 101 | 83.5 | **~511** |
| Model 4 as usually specified: 2,000 GPUs, infrastructure only | 175 | 95.4 | **~638** |
| Model 4 as usually specified + commercial licences | 312 | 119 | **~866** |

### 7.4 Phased rollout

| phase | months | cameras | EDGE-L | EDGE-S | plate events/day | peak Mbps | **capex this phase** | opex/yr at end of phase |
|---|---|---|---|---|---|---|---|---|
| **1: VISWAS + 34 Netram** | 0–6 | 17,500 | 83 | 0 | ~100 M | ~370 | **₹17.7 Cr** | ₹12.5 Cr |
| **2: + departments** | 6–18 | 50,000 | 83 | ~1,800 | ~110 M | ~410 | **₹16.1 Cr** | ₹15.1 Cr |
| **3: 80k + private opt-in** | 18–36 | 80,000 + 10,000 private (registry + clip pull only) | 83 | ~3,450 | ~124 M | ~450 | **₹14.8 Cr** | ₹17.6 Cr |

Phase 1 carries the whole central core, DR and all 34 Netram deployments. Staff costs are full-size from day 1.
**VISWAS produces ~80% of all plate events.** The departments add many cameras but few plates. So traffic and
central sizing are essentially settled in Phase 1, and Phases 2–3 are mostly a field-deployment exercise.

---

## 8. Sensitivity (80,000 cameras; TCO = 5 years, ₹ crore)

| case | plate events/day | PRAHARI peak Mbps | ratio @ peak | edge nodes | central raw TB | PRAHARI capex | PRAHARI TCO | M4 steelman TCO | M4 infra TCO | M4 + licences TCO |
|---|---|---|---|---|---|---|---|---|---|---|
| **Base case** | 124 M | 450 | 360× | 3,538 | 630 | 49 | 133 | 511 | 638 | 866 |
| ANPR-capable share 50% (not 29%) | 180 M | 650 | 250× | 4,072 | 900 | 55 | 143 | 522 | 638 | 947 |
| ANPR at 2 fps everywhere | 124 M | 450 | 360× | 4,089 | 630 | 57 | 145 | 521 | 638 | 866 |
| Crop 10 KB | 124 M | 310 | 520× | 3,538 | 470 | 49 | 133 | 511 | 638 | 866 |
| Crop 30 KB | 124 M | 860 | 190× | 3,538 | 1,100 | 49 | 133 | 511 | 638 | 866 |
| Traffic ×2 | 240 M | 880 | 180× | 3,538 | 1,200 | 49 | 133 | 511 | 638 | 866 |
| Doc-01 traffic (0.2 veh/s on every ANPR cam) | 400 M | 1,400 | 110× | 3,538 | 1,900 | 49 | 134 | 511 | 638 | 866 |
| Safety factor 3 (real footage worse) | 124 M | 450 | 360× | 4,080 | 630 | 56 | 144 | 519 | 638 | 866 |
| All ANPR cams keyframe-decodable (GOP ≤ 1 s) | 124 M | 450 | 360× | 3,538 | 630 | 49 | 133 | 511 | 638 | 866 |
| Reuse existing departmental PCs at 40% of sites | 124 M | 450 | 360× | 2,222 | 630 | 37 | 117 | 511 | 638 | 866 |
| Crops only for watchlist hits (tier 2) | 124 M | 29 | 5,500× | 3,538 | 130 | 48 | 132 | 511 | 638 | 866 |
| Cold 7 y for **all** events (not recommended) | 124 M | 450 | 360× | 3,538 | 15,000 | 57 | 147 | 511 | 638 | 866 |
| WAN ₹100/Mbps-month (state-owned fibre) | 124 M | 450 | 360× | 3,538 | 630 | 49 | 133 | **331** | 458 | 686 |
| WAN ₹500/Mbps-month (small site links) | 124 M | 450 | 360× | 3,538 | 630 | 49 | 133 | 811 | 938 | 1,166 |
| Model 4 at 4 Mbps | 124 M | 450 | 720× | 3,538 | 630 | 49 | 133 | 920 | 1,046 | 1,275 |
| Model 4 at 7-day retention | 124 M | 450 | 360× | 3,538 | 630 | 49 | 133 | 471 | 597 | 826 |

**How to read this table:**

- **PRAHARI's TCO barely moves (₹117–147 Cr) across every case.** Its cost comes from the number of sites and
  from staff, not from traffic. Traffic, crop size and ANPR share move *bandwidth* and *storage*, which are cheap
  at this scale.
- **Model 4's TCO is dominated by the price per Mbps.** If the state can deliver 160 Gbps over its own fibre
  (GSWAN / BharatNet) at ~₹100/Mbps-month, the steelman falls to ~₹330 Cr, **still ~2.5× PRAHARI**. That is the
  most favourable case for Model 4 in this model. Even then it needs 52 PB, and it needs every department to send
  its video out, which is the consent problem in doc 01 §3.4.
- The bandwidth *ratio* ranges from 110× (doc-01 traffic) to 5,500× (tier 2). It never approaches parity.

**The five assumptions that move the result most:**
1. **WAN price per Mbps (A25).** It swings Model 4's 5-year cost by ±₹300 Cr.
2. **Number of departmental NVR sites (A19).** It sets PRAHARI's node count, edge capex and field workload. The registry replaces this assumption with real data.
3. **Real-footage performance vs the M1 (A16, A20).** None of our production node classes has been measured. A safety factor of 3 adds ~550 nodes and ~₹11 Cr to the 5-year TCO.
4. **VISWAS vehicles per camera and ANPR share (A4, A5).** Together they drive ~80% of events, bandwidth and crop storage.
5. **Crop size and crop policy (A11, ladder tier).** Crops are 80% of the bytes. Sending them only for hits cuts peak traffic 15× and central storage 5×.

---

## 9. Scaling mechanics, HA and DR

**Horizontal scaling unit.**
- *Edge:* one EDGE-S per departmental NVR site (≤ ~16 ANPR at mixed fps plus hundreds of light cameras). One EDGE-L per ~220 ANPR streams at a Netram, plus N+1. A new department is added as *N more nodes*. No central change is needed.
- *Central:* stateless pods scale horizontally on consumer lag, with about one gateway pod per 2,500 events/s. The bus is partitioned by `camera_id`, which keeps per-camera ordering and PTS monotonicity. The DB is partitioned by day, with a plate-hash shard at ~10× today's rate. The object store grows by one storage host per ~160 TB usable.

**Load balancing.** Nodes only **dial out**, over mTLS on 443. Each node holds an ordered endpoint list: DC gateway
VIP, then Netram relay, then DR gateway VIP. A pair of L4 load balancers (keepalived/HAProxy, or the SDC's F5) sits
in front of the gateway pods. Nodes reconnect with jittered exponential backoff (2 s → 30 s), so a gateway restart
does not cause a thundering herd. Camera-to-node assignment is stored in the registry. When a node at a large site
fails, its cameras move to a sibling node. At a single-node site they are marked "analytics degraded", and the NVR
keeps recording.

**Monitoring and health checks.** Nodes send a heartbeat every 30 s. Per camera we collect measured fps, last-frame
age, reconnects, decode errors and PTS discontinuities; the node code already produces these (`data/stability-*.json`).
Metrics go by remote-write to VictoriaMetrics/Mimir (~1.5 M series), logs to Loki, and results appear on Grafana
dashboards and the registry map. Alert rules:
- camera offline > 5 min
- node silent > 2 min
- queue depth > 1 h
- ingest lag > 60 s
- **clock skew > 2 s**, because timestamps are evidence

The camera health map is itself a deliverable: departments get it for free on day one (doc 04 §2D).

**High availability.**
- *Gateway, bus and screen:* ×3 across hosts, with quorum.
- *PostgreSQL:* synchronous standby with Patroni failover (< 60 s).
- *Object store:* EC 4+2 across 6 hosts, so it survives 2 host failures.
- *Netram:* active/standby server pair, plus N+1 EDGE-L.
- *District alerting:* works through a central outage, because each Netram holds a watchlist cache and screens its own district's events locally.

**Disaster recovery.** The DR site is warm standby: 100% of storage, 50% of compute. It is in a different seismic
zone from the primary. Kutch is zone V, so neither site should be there. Options are a second Gujarat DC or the
national government cloud (MeghRaj/NIC).

| data / service | RPO | RTO | why achievable |
|---|---|---|---|
| plate events | **effectively 0** | 1 h (DR promotion) | nodes keep events in their disk queue until the central store acks them; the DR site receives the replay |
| watchlist alerts within a district | 0 | **~0** | Netram screens locally; no central dependency |
| cross-district alerts, search, trace | < 1 min (async DB replication) | **4 h** | warm standby, DNS/VIP switch |
| evidence crops | < 15 min (bucket replication) | 4 h | edge ring buffer keeps 72 h as a second source |
| case clips and evidence bundles | 0 once sealed | 4 h | hash-sealed at the edge; replicated on seal; departmental NVR is the original |
| audit log | 0 | 4 h | hash chain; daily anchor exported offline (NFSU-verifiable) |

**Backup.** Continuous WAL archiving to the object store with 14-day point-in-time recovery. Nightly logical dumps
of the registry and watchlist. Monthly DR failover drill. Object-lock (WORM) on the case-evidence buckets.

---

## 10. What we measured vs what we assumed

**Measured** on an Apple M1, 8 GB, with **synthetic streams and synthetic plates**:
- ANPR cost per frame: 3.8 ms detector-only and 21 ms with one plate (p90, 960 px); 40.8 ms at 1280 px. Source: `docs/hld/bench-anpr-m1.json`.
- Software decode: 20% of a core per 1080p25 stream (scaled from 12 cameras at 111.7 Mpix/s = 43.8% CPU). Keyframe-only: 0.52% of a core per camera. Zero decode errors over 100–200 s runs. Source: `data/stability-*.json`.
- Event size: 547 B serialised. Evidence crop: 5.2 KB (plate only, synthetic). Stored row: ≤ 1.05 KB including indexes. Source: `data/demo.db`, `data/evidence/`.
- Practice mode: 8 cameras, 788 frames at ~14 ms average (reported in the brief; the raw log is not retained).

**Not measured, and assumed with an explicit margin:**
- Performance on EDGE-S, EDGE-M and EDGE-L hardware. None of it has been benchmarked.
- Real CCTV footage (night, glare, two-line plates).
- Real camera GOP settings, the number of cameras per departmental site, and actual traffic per camera.
- Every price. These are Indian retail and list anchors; government volume procurement is usually 15–30% lower, and we have **not** applied that discount.

The ×2 safety factor and 60% utilisation are there because the first set is unmeasured. The model is set up so
that each of the second set can be replaced by a registry measurement during Phase 1.

**What would change our minds:**
- Suppose a Phase-1 pilot measures production nodes at half our assumed inference *and* decode performance. EDGE-L grows from 83 to 132, EDGE-S from 3,455 to 3,973, and edge capex from ₹40 Cr to ₹51 Cr. The 5-year TCO rises from ₹133 Cr to ₹148 Cr (checked in the model). The departmental fleet grows very little, because its size is set by the number of sites, not by load.
- If the state already owns ≥ 160 Gbps of spare fibre capacity to a single DC, the WAN argument weakens to ~2.5×. The storage and departmental-consent arguments would remain.

---

## 11. Sources (price and fact anchors, accessed 25 Sep 2026)

- NVIDIA L4 price in India: [IndiaMART listing ₹1 L](https://www.indiamart.com/proddetail/nvidia-l4-tensor-core-gpu-card-24gb-2855181097191.html); [IndiaMART listing ₹3 L](https://www.indiamart.com/proddetail/nvidia-l4-tensor-core-gpu-24gb-gddr6-2856474096573.html); [AceCloud, L4 price in India (₹2.4 L buy, ₹36.7k/month rent)](https://acecloud.ai/blog/nvidia-l4-price/)
- NVIDIA L4 has 4 NVDEC and 2 NVENC decoders/encoders and a 72 W TDP: [Cisco-hosted NVIDIA L4 datasheet](https://www.cisco.com/c/dam/en/us/products/collateral/servers-unified-computing/ucs-c-series-rack-servers/nvidia-l4-gpu.pdf)
- Jetson Orin NX 16 GB module ₹49k: [IndiaMART](https://www.indiamart.com/proddetail/nvidia-jetson-orin-nx-module-2851947013888.html). Decode 18× 1080p30 H.265: [NVIDIA Jetson Orin NX series datasheet](https://developer.nvidia.com/downloads/jetson-orin-nx-series-data-sheet)
- Server: Dell PowerEdge R760 (Xeon Gold 4409Y, 2×32 GB) ₹6.51 L: [IndiaMART](https://www.indiamart.com/proddetail/dell-poweredge-r760-rack-server-2855827528297.html)
- HDD: Seagate Exos X20 20 TB ₹89.9k–92k: [Computech Store](https://computechstore.in/product/seagate-exos-x20-20tb/), [IndiaMART](https://www.indiamart.com/proddetail/seagate-exos-20tb-hdd-sata-enterprise-hdd-nas-hdd-2853000238733.html)
- Leased-line pricing in India (100 Mbps ₹25–38k/month; 1 Gbps ₹1.5 L+/month; ex-GST): [itforsme.in ILL pricing guide](https://www.itforsme.in/pricing/internet-leased-line-india)
- Colocation in India (full rack ₹25k–60k/month; power ₹8k–25k per kW-month): [Cyfuture colocation pricing](https://cyfuture.cloud/kb/colocation/full-rack-colocation-pricing-from-top-indian-data-centers)
- Gujarat tariffs held at previous-year levels for FY 2026-27: [Mercom India](https://www.mercomindia.com/gujarat-retains-fy-2027-power-tariffs-at-previous-years-levels). HT energy charge ~₹4.3/kWh, effective ₹7.5–8.5/kWh with FPPPA, duty and demand charges: [Bridgeway Power, GERC HT tariff 2026-27](https://bridgewaypower.in/blog/gujarat-gerc-ht-tariff-2026-27)
- VISWAS phase I (~7,000 cameras, ~1,200 locations, 34 Netram): [DeshGujarat, Jul 2022](https://deshgujarat.com/2022/07/02/7000-cctv-cameras-installed-in-gujarat-under-phase-i-of-viswas-10000-to-be-installed-in-phase-ii/). Phase II (~10,500 cameras, Surat/Vadodara, 52 municipalities, 80 entry/exit points): [DeshGujarat, Dec 2023](https://deshgujarat.com/2023/12/15/10500-cctv-cameras-being-installed-across-gujarat-under-viswas-project/)
- Departmental retention of 7–15 days and mixed cloud/local storage: organisers' FAQ (`research/00-official-faqs.txt`)
- **No source found; clearly labelled ASSUMED ranges:** Intel Core Ultra mini-PC price (₹55k–1 L), per-channel VMS/ANPR licence prices, AMC rate, staff costs, and per-NVDEC stream throughput on the L4.
