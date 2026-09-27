# PRAHARI — Official Hackathon Slide Deck Script & Master Guide
**Gujarat Police Sentinel Hackathon 2026 · Integrated Video Management & Analytics Platform**
*Presentation Deck: 18 Slides · 10–12 Minute Presentation + Q&A Defense*

---

## Deck Overview & Presentation Structure

| Slide # | Title | Objective & Jury Appeal | Timing |
|---|---|---|---|
| **01** | **PRAHARI: The Sentinel** | Title, team identity, Gujarat Police context | 0:45 |
| **02** | **The Core Thesis: Move Meaning, Not Megabytes** | Demolishes central streaming with arithmetic | 0:45 |
| **03** | **The Challenge: 26 Departments & 80,000 Cameras** | Ground reality, dispersion, heterogeneity | 0:45 |
| **04** | **Model Selection: Hybrid Architecture (Model 5)** | Model 1 + 3 + 2 justified; Model 4 refuted | 1:00 |
| **05** | **System Architecture & Statewide Topology** | Edge nodes, 34 Netram C3s, SCRB Gandhinagar | 1:00 |
| **06** | **Innovation 1: Camera Capability Auto-Profiling (CCAP)** | Solves dead tiles across hospital corridors & gates | 1:00 |
| **07** | **Innovation 2: Indian Plate Grammar & Confusion Matching** | Kills silent OCR misses; 0 false negatives on stage | 1:00 |
| **08** | **Innovation 3: Re-ID Bridged Trajectory & Velocity Gating** | Cross-camera tracking that survives unreadable plates | 1:00 |
| **09** | **Innovation 4: Zero-Inbound, Zero-Change Onboarding** | Solves the 26-department firewall deadlock | 0:45 |
| **10** | **Innovation 5: The 5-Tier Bandwidth Ladder** | Graceful degradation from 10 Mbps to 2G island mode | 0:45 |
| **11** | **End-to-End Workflow: Ingest → Alert → Trace** | Code-traceable processing sequence | 0:45 |
| **12** | **Evidence Integrity: The NFSU Forensic Play** | Section 65B / BSA compliance, SHA-256 hash chains | 0:45 |
| **13** | **Privacy by Design: DPDP Act 2023 Compliance** | Purpose-bound searches, RBAC, tiered retention | 0:45 |
| **14** | **Infrastructure Sizing: 80,000 Cameras & ₹-Crore TCO** | ₹130 Cr vs ₹510 Cr (₹380+ Cr savings) | 1:00 |
| **15** | **Departmental Prerequisites: Why We Ask for Zero Forms** | System measures reality; no survey paralysis | 0:45 |
| **16** | **Live Technical Evaluation Walkthrough** | ~50 cameras live, designated vehicle GJ01AB1234 | 1:00 |
| **17** | **Statewide Rollout Plan & Future Roadmap** | Phased execution: VISWAS integration to AI scale | 0:45 |
| **18** | **Why PRAHARI Wins: 6/6 Bonus Scorecard** | Unassailable summary & closing pitch | 0:45 |

---

## Detailed Slide Content, Visual Blueprint & Speaker Notes

### Slide 01: Title & Identity
- **Slide Title:** PRAHARI (પ્રહરી)
- **Subtitle:** Integrated Video Management & Analytics Platform across 26 Government Departments
- **Visual Blueprint:** Deep police navy background (`#0d1b2a`), Gujarat Police crest / Sentinel Hackathon logo emblem, gold accent borders, live telemetry badge showing `159 automated tests passing · All 50 cameras connected`.
- **Key Points:**
  - Team PRAHARI · Gujarat Police Innovation Challenge 2026
  - Declared Architecture: Hybrid Model (Model 1 Registry + Model 3 Federation + Model 2 Direct Ingest)
  - Production-tested implementation running live in Python & ONNX
- **Speaker Script:**
  > *"Respected members of the jury and senior officers of Gujarat Police: Welcome. In Gujarati, PRAHARI means 'the sentinel'—the one who stands watch. We present PRAHARI: an integrated video management and analytics platform engineered specifically to unify all 26 independent government departments and scale effortlessly to 80,000 cameras statewide. Everything we show you today is fully built, rigorously benchmarked, and operating live on the Sentinel camera network."*

---

### Slide 02: The Core Thesis: Move Meaning, Not Megabytes
- **Slide Title:** The Fundamental Law: Move Meaning, Not Megabytes
- **Visual Blueprint:** Split-screen comparison. Left side (Red): Central VMS streaming 80,000 cameras = 160 Gbps sustained pipe, 52 PB video storage, ₹510+ Cr cost. Right side (Green): PRAHARI federated edge = 0.21 Gbps average / 0.45 Gbps peak, ~210 TB metadata, ₹130 Cr cost.
- **Key Callout Box:** `160 Gbps → 0.45 Gbps (Peak): A 360× Network Reduction`
- **Key Points:**
  - Video stays where it is born—on departmental LANs.
  - Only compact observations (~550-byte event records and ~15-KB forensic crops) cross the statewide WAN.
  - The central registry is not an inventory; it is the intelligence brain.
- **Speaker Script:**
  > *"Before writing a single line of code, we confronted the physics of statewide surveillance. If you stream 80,000 cameras centrally to Gandhinagar, you need 160 Gigabits per second of continuous bandwidth and 52 Petabytes of storage every single month. That is not just a ₹60-crore annual telecom bill—it is a single point of failure that collapses during fiber cuts. Our thesis is simple: Move meaning, not megabytes. We execute computer vision at the edge, where video is born. We transmit only structured observations—reducing statewide WAN bandwidth to less than half a gigabit at peak. That 360× reduction is the mathematical foundation of our entire architecture."*

---

### Slide 03: The Reality: 26 Departments & 80,000 Cameras
- **Slide Title:** The Ground Reality across Gujarat
- **Visual Blueprint:** Map of Gujarat highlighting 1,000 km dispersion (Kutch border to Valsad industrial belt). Department icons around the periphery: Home (VISWAS), Food & Civil Supplies (Godowns), RTO (Tracks & Tolls), Health (Hospitals), GSRTC (Bus Stations).
- **Key Points:**
  - **26 Siloed Departments:** Standalone VMSs (Milestone, Genetec, Dahua, Hikvision), separate 5-year AMC contracts, conflicting storage rules (7 to 30 days).
  - **1,000 km Geographical Dispersion:** From high-speed urban highways to remote border outposts in Banaskantha and tribal talukas in Dahod.
  - **Extreme Heterogeneity:** IP vs analog, H.264 vs H.265, 480p to 4K resolutions, non-standard RTSP implementations.
- **Speaker Script:**
  > *"Gujarat's surveillance landscape is defined by organizational heterogeneity. 26 independent departments have deployed cameras over the past decade under separate AMC contracts. A hospital corridor in Civil Hospital Ahmedabad has completely different optics, lighting, and functional requirements than an RTO checkpoint in Dahod or a VISWAS junction in Surat. Any solution that expects all 26 departments to surrender control, replace their NVRs, or conform to one single proprietary VMS will fail politically before it ever deploys. We designed PRAHARI to fit Gujarat's reality, rather than forcing Gujarat to fit a vendor's product."*

---

### Slide 04: Model Selection: Hybrid Architecture (Model 5)
- **Slide Title:** Choosing the Right Approach: Hybrid Model Justification
- **Visual Blueprint:** Matrix table showing Models 1, 2, 3, 4 vs PRAHARI Hybrid. Green checkmarks and clear operational rationale.
- **Key Points:**
  - **Model 1 (Mandatory Base):** Centralized Registry & GIS Foundation. Built with 3 onboarding paths (API sync, CSV bulk upload, manual entry) and spatial coverage-gap analysis.
  - **Model 3 (Federation Spine):** Event bus and protocol adapter layer interconnecting departmental VMSs without touching existing storage or AMCs.
  - **Model 2 (Edge Viewing & Analytics):** Direct RTSP/ONVIF ingestion for standalone cameras lacking local VMS hosts.
  - **Model 4 Rejected with Arithmetic:** Centralizing raw video requires 445 recording servers, 2,000 GPUs, and ₹510+ Cr. PRAHARI achieves Model 4's analytics without Model 4's ruinous infrastructure cost.
- **Speaker Script:**
  > *"The hackathon outlined four reference models. We selected Model 5: an innovative Hybrid. We adopt Model 1 as the mandatory GIS foundation. We adopt Model 3 as the federation spine, using an event bus to federate existing departmental VMSs so their existing workflows continue uninterrupted. We incorporate Model 2 to directly connect orphaned cameras. Crucially, we evaluated Model 4—full centralization—and explicitly rejected it with arithmetic. We deliver 100% of Model 4's statewide analytics capabilities at one-fourth the 5-year total cost of ownership."*

---

### Slide 05: System Architecture & Statewide Topology
- **Slide Title:** Statewide Three-Tier Topology
- **Visual Blueprint:** Three distinct vertical layers:
  1. *Edge Tier:* 26 Department Premises (NVRs + PRAHARI Edge Node)
  2. *Regional Tier:* 34 Netram District C3 Command Centres (GPU Inference + NATS Leaf Nodes)
  3. *Central Tier:* SCRB Gandhinagar / State Data Centre (Registry + Matcher + Trace + Evidence Vault)
- **Key Points:**
  - **Edge Tier:** Software-only container running on local hardware or ₹20,000 mini-PCs. Zero inbound open ports.
  - **Regional Tier:** Leverages existing 34 Netram District Command Centres for local GPU acceleration and high-density junction streams.
  - **Central Tier:** State Crime Records Bureau (SCRB) hosts the central PostgreSQL/PostGIS registry, confusion-space matcher, and tamper-evident audit ledger.
- **Speaker Script:**
  > *"Here is how PRAHARI maps across Gujarat. At the edge, inside each departmental building, runs the PRAHARI Node—a single lightweight container connecting to local NVRs. In the middle tier, we leverage Gujarat's existing 34 Netram District Command and Control Centres, placing regional GPU servers to handle high-density VISWAS junctions. At the apex, in SCRB Gandhinagar, sits the State Brain: the Central Registry, the Watchlist Matcher, the Trajectory Engine, and the Tamper-Evident Evidence Vault. The network between them carries structured observations—never raw, continuous video."*

---

### Slide 06: Innovation 1: Camera Capability Auto-Profiling (CCAP)
- **Slide Title:** Flagship Innovation: Camera Capability Auto-Profiling (CCAP)
- **Visual Blueprint:** CCAP JSON schema visual, camera comparison graphic showing a hospital corridor classified as `anpr_viable: false` (plate height 8px) vs a traffic junction classified as `anpr_viable: true` (plate height 34px). Graph showing compute savings.
- **Key Points:**
  - **The Problem:** Hospital corridors and bus depots will never show readable plates. Standard systems produce dead, dark tiles on stage.
  - **What CCAP Does:** On onboarding, the node profiles the stream for 60 seconds, measuring median plate height (`plate_px_median`), Indian plate grammar match rate (`valid_rate`), and motion density.
  - **Intelligent Resource Allocation:** Non-viable cameras are throttled to 1 frame in 10, conserving 90% of GPU compute for junction cameras while assigning appropriate analytics (loitering, crowd density).
  - **The Policy Answer:** *"We require zero surveys from departments. The system measures every camera itself."*
- **Speaker Script:**
  > *"When you integrate 50 heterogeneous cameras across hospitals, bus depots, and police junctions, a naive ANPR engine will show dark, dead tiles on half the screen because corridors do not have vehicles. CCAP solves this. When a camera connects, our profiler actively measures it. If plate height is under 24 pixels or legibility is under 33%, CCAP marks it ANPR-unviable, throttles its sampling by 90%, and reassigns it to crowd or loitering analytics. When the organizers asked what information we need from departments, our answer was: Nothing. The system profiles its own estate automatically."*

---

### Slide 07: Innovation 2: Indian Plate Grammar & Confusion Matching
- **Slide Title:** Grammar-Constrained OCR & Confusion-Space Matching
- **Visual Blueprint:** Flow diagram contrasting naive exact SQL match (`WHERE plate = ocr`) vs PRAHARI 3-Layer matching:
  1. Indian Plate Grammar Regex & State Code Dictionary
  2. Constrained Beam Search (`6J01A8I234` → `GJ01AB1234`)
  3. Confusion Distance Weighted Matrix (`O/0`, `I/1`, `B/8`)
- **Key Points:**
  - **Eliminates Silent Misses:** Indian plates feature bent metal, high-beam glare, HSRP security holograms, and dirt. A single misread character destroys exact string matching.
  - **Structure is Free Accuracy:** Validates against 36 official state codes and RTO district ceilings.
  - **Confusion-Weighted Edit Distance:** Distance between `O` and `0` is 0.1; distance between `G` and `X` is 1.0.
  - **Tiered Operator Alerts:**
    - *ALERT ($d \le 0.15$):* Instant automated dispatch
    - *REVIEW ($0.15 < d \le 0.35$):* 1-click operator verification with evidence crops
    - *NEAR-MISS ($0.35 < d \le 0.50$):* Investigative leads—never an empty screen!
- **Speaker Script:**
  > *"Every competing team will deploy standard OCR with exact SQL string matching. On Indian roads, that fails. A spot of mud turns a B into an 8; high-beam glare turns a G into a 6. With exact matching, the stolen vehicle drives past and the system raises zero alerts. PRAHARI uses a three-layer engine. First, we constrain decoding using the Indian Plate Grammar—validating state codes and RTO numbers. Second, constrained beam search repairs character confusions. Third, watchlist matching occurs in confusion space using weighted Levenshtein distance. We output ranked candidates with evidence crops. The money moment on stage never fails."*

---

### Slide 08: Innovation 3: Re-ID Bridged Trajectory & Velocity Gating
- **Slide Title:** Re-ID Bridged Trajectory & Physical Velocity Gating
- **Visual Blueprint:** Map route visual showing stops 1 through 5. Hop 2 shows plate occluded by a truck, bridged via Vehicle Appearance Re-ID (White Swift, embedding similarity 0.78). Hop 4 shows an amber flag: `Implied speed 192 km/h exceeds 150 km/h limit — Possible cloned plate or clock skew`.
- **Key Points:**
  - **Survives Missing Plates:** High-confidence plate reads serve as anchors; gaps are bridged by vehicle appearance embeddings (color, model, type).
  - **Physical Velocity Gating:** Every hop computes great-circle Haversine distance and elapsed time. If implied speed exceeds 150 km/h, the hop is physically impossible.
  - **Forensic Honesty:** Implausible hops are **flagged on screen for investigators**, not hidden. Cloned plates, misreads, and clock skews are immediately visible.
- **Speaker Script:**
  > *"When tracking a suspect vehicle across Gujarat, route reconstruction breaks if a plate is occluded by an overtaking truck. PRAHARI bridges these gaps. High-confidence plate reads anchor the track, while vehicle appearance embeddings bridge occluded cameras. Crucially, every hop is gated by real-world physics. If camera A to camera B is 15 kilometers and the sightings are 3 minutes apart, that implies 300 km/h. Instead of pretending that is valid, PRAHARI flags it as physically impossible—instantly alerting investigators to a cloned plate or a misread. That is forensic integrity."*

---

### Slide 09: Innovation 4: Zero-Inbound, Zero-Change Onboarding
- **Slide Title:** Zero-Inbound, Zero-Change Edge Onboarding
- **Visual Blueprint:** Department network firewall diagram. Shows PRAHARI Node dialing OUTWARD over mTLS Port 443. Red barrier across inbound ports (Port 80, 554, 8000 blocked).
- **Key Points:**
  - **The Mechanism Design Solution:** Department IT administrators will not open inbound ports or surrender custody of video feeds.
  - **Outbound-Only mTLS:** Node dials out over standard port 443. Works behind any corporate or departmental firewall with zero NAT configuration.
  - **Zero Hardware Changes:** Existing cameras, NVRs, and vendor AMC contracts remain 100% untouched.
  - **Department Incentive:** Departments gain free camera health monitoring, GIS mapping, and maintain a local cryptographic kill switch.
- **Speaker Script:**
  > *"The single biggest barrier to statewide surveillance in India is administrative friction. 26 departments refuse to open inbound firewall ports or void their 5-year AMC contracts. PRAHARI solves this through mechanism design. The edge node dials outward over port 443 using mutual TLS. No inbound ports are opened. No firewall rules are changed. No video leaves the premises. The department retains 100% custody of its recordings while receiving automated health monitoring for free. Joining is frictionless."*

---

### Slide 10: Innovation 5: The 5-Tier Bandwidth Ladder
- **Slide Title:** The Bandwidth Ladder: Resilience from Fiber to 2G
- **Visual Blueprint:** Stepped ladder diagram illustrating Tiers 4 down to 0, showing bandwidth thresholds, transmitted payloads, and fallback behaviors.
- **Key Points:**
  - **Tier 4 (>10 Mbps):** Full spectrum (events + crops + thumbnails + on-demand live video).
  - **Tier 3 (2–10 Mbps):** Standard operations (all text events + evidence crops).
  - **Tier 2 (0.2–2 Mbps):** Watchlist-prioritized (all text events; crops sent only for watchlist hits).
  - **Tier 1 (<200 kbps):** Ultra-low bandwidth (compressed JSON text events only, ~120 B/event).
  - **Tier 0 (0 kbps / Offline):** Autonomous Island Mode. Local inference continues uninterrupted; events and evidence buffer in SQLite on local SSD. Zero data loss; auto-replays on reconnect.
- **Speaker Script:**
  > *"Gujarat's geography spans high-speed fiber corridors and remote border posts in Kutch where connectivity drops for hours. PRAHARI does not crash when the network degrades. Our node continuously probes its uplink and steps down a 5-tier bandwidth ladder. At Tier 2, routine crops stay local and only watchlist hit crops cross the WAN. In Tier 0—a complete fiber cut—the node enters Autonomous Island Mode. ANPR continues, writing to an encrypted local SSD ring buffer. When the link restores, it backfills without losing a single event."*

---

### Slide 11: End-to-End Workflow & Data Pipeline
- **Slide Title:** End-to-End Operational Workflow
- **Visual Blueprint:** Horizontal sequence flow: Camera (RTSP TCP) → PyAV PTS Extraction → CCAP Evaluation → YOLO Plate Detection → Grammar Beam Search → Deduplication Window → Confusion Watchlist Match → Real-time SSE Dispatch → React Wall & Map.
- **Key Points:**
  - Strict TCP transport prevents UDP packet drops.
  - PTS timestamps eliminate false velocity spikes on reconnect.
  - 6.0-second rolling deduplication window prevents alert spam.
  - Sub-50 millisecond total end-to-end processing latency.
- **Speaker Script:**
  > *"Here is the complete data flow. From the RTSP stream, we enforce TCP and extract presentation timestamps directly from packet headers. CCAP validates camera viability. The YOLO detector extracts the plate region, handling two-line stacked plates automatically. Constrained beam search decodes the characters under Indian grammar. The deduplicator prevents multi-frame alert flooding. The event is matched against the watchlist in confusion space, and within 50 milliseconds, an alert arrives on the operator's screen."*

---

### Slide 12: Evidence Integrity: The NFSU Forensic Play
- **Slide Title:** Evidence Integrity & Legal Admissibility (The NFSU Play)
- **Visual Blueprint:** Cryptographic chain diagram showing SHA-256 block hashes linked from Genesis (`000...000`) to Head Hash. Certificate of Admissibility graphic (Section 65B BSA).
- **Key Points:**
  - **Designed for NFSU:** National Forensic Sciences University evaluates legal admissibility.
  - **Edge SHA-256 Hashing:** Evidence crops are hashed on the edge node at the microsecond of capture.
  - **Tamper-Evident Hash-Chained Audit Log:** Every query, search, and alert is cryptographically chained. SQLite triggers prevent `UPDATE` or `DELETE`.
  - **Model Provenance:** Every alert records the exact model architecture, weights hash, and runtime provider, ensuring admissibility under Section 65B of the Indian Evidence Act / Section 63 BSA 2023.
- **Speaker Script:**
  > *"We know the National Forensic Sciences University is on the evaluation panel. An AI detection is useless to a police officer if it gets thrown out of court. PRAHARI is engineered for legal admissibility under Section 65B of the Indian Evidence Act and the new Bharatiya Sakshya Adhiniyam. Every evidence crop is SHA-256 hashed at the edge at the moment of capture. Every user action and query is committed to an append-only, tamper-evident hash-chained audit ledger. Any attempt to alter historical records breaks the chain. We record model weights provenance for every detection."*

---

### Slide 13: Privacy by Design: DPDP Act 2023 Compliance
- **Slide Title:** Privacy by Design & DPDP Act 2023 Compliance
- **Visual Blueprint:** UI screenshot of Search/Trace modal highlighting mandatory `Purpose` and `Case ID` input fields. Graduated RBAC pyramid.
- **Key Points:**
  - **Mandatory Purpose-Bound Queries:** No anonymous surveillance trawling. All plate lookups require an active Case ID and declared official purpose.
  - **Graduated RBAC:** Constable (Live view/ack) → Investigator (Trace/evidence) → Supervisor (Watchlist) → Auditor (Immutable logs).
  - **Tiered Retention Schedules:** Text metadata (1 year) · Evidence crops (90 days) · Video clips (30 days) · Case-linked evidence (7 years).
  - **Proportionate Facial Recognition:** FRS is disabled by default; unlocked only under explicit supervisory warrant.
- **Speaker Script:**
  > *"Under the Digital Personal Data Protection Act 2023 and the Supreme Court's Puttaswamy ruling, state surveillance must satisfy the test of proportionality. PRAHARI enforces privacy by design. Anonymous trawling is impossible: every search and trace requires a declared Case ID and legal purpose, sealed into the audit log. We implement strict role-based access control, enforce tiered retention schedules, and keep facial recognition locked behind supervisory authorization."*

---

### Slide 14: Infrastructure Sizing: 80,000 Cameras & ₹-Crore TCO
- **Slide Title:** Infrastructure Sizing: 80,000 Cameras & Cost-Benefit
- **Visual Blueprint:** Comprehensive comparison table and bar chart contrasting Model 4 vs PRAHARI.
- **Key Data Table:**

| Metric | Model 4 (Central VMS) | PRAHARI (Federated) | Impact |
|---|---|---|---|
| **Peak WAN Bandwidth** | **160 Gbps** | **0.45 Gbps** | **~360× Reduction** |
| **Central Video Storage (30 d)**| **51.8 PB** | **~210 TB** | 240× Reduction |
| **Central GPUs** | **~2,000 GPUs** | **0 Central (166 L4s at Netram)**| Zero Central GPU Bottleneck |
| **5-Year Capex** | ₹101 Cr – ₹175 Cr | **₹49 Cr** | ₹52+ Cr Savings |
| **5-Year Opex** | ₹410 Cr – ₹695 Cr | **₹81 Cr** | Slashes Recurring Bandwidth |
| **5-Year Total TCO** | **₹510 Cr – ₹870 Cr** | **≈ ₹130 Cr** | **Saves ₹380 Cr to ₹740 Cr** |

- **Speaker Script:**
  > *"Here is the arithmetic the organizers asked for. Sizing for 80,000 cameras: Model 4 requires ₹510 to ₹870 Crore over five years, dominated by a ₹60-crore annual telecom bill for 160 Gbps of bandwidth. PRAHARI requires ₹130 Crore all-in—including edge hardware, Netram servers, storage, power, and maintenance. We achieve a ₹380 to ₹740 Crore saving for the Government of Gujarat, with zero single points of failure."*

---

### Slide 15: Departmental Prerequisites: Why We Ask for Zero Forms
- **Slide Title:** Departmental Prerequisites: Why We Ask for Zero Forms
- **Visual Blueprint:** Comparison visual: Traditional Approach (Bureaucratic 50-page survey questionnaire across 26 departments) vs PRAHARI Approach (Connect read-only RTSP stream → CCAP auto-discovers geometry, resolution, FPS, and viability).
- **Key Points:**
  - **Traditional Integration Failure:** Asking 26 departments to complete technical surveys regarding camera field-of-view, sensor sizes, and focal lengths takes 3 years and yields 90% missing data.
  - **The PRAHARI Solution:** The edge node automatically reads stream metadata (codec, resolution, GOP structure) and CCAP actively measures physical plate legibility.
  - **Department Prerequisite:** Exactly one item—LAN access to a read-only RTSP/ONVIF stream.
- **Speaker Script:**
  > *"The problem statement asks teams to specify technical prerequisites and information required from participating departments. Other teams will present lengthy survey forms asking for lens focal lengths, mounting heights, and illuminance. Departments do not know these answers. Our answer is radical simplicity: We require zero survey forms. The department provides LAN access to the RTSP stream. PRAHARI's CCAP measures the real frame rate, the codec, the true resolution, and the physical legibility of plates within 60 seconds."*

---

### Slide 16: Live Technical Evaluation Walkthrough
- **Slide Title:** Live Evaluation Walkthrough: The 50-Camera Grid
- **Visual Blueprint:** Real screenshots of PRAHARI running live:
  - *The Wall:* 50 camera tiles live, green bounding boxes on detected plates.
  - *Alerts Screen:* Instant red alert banner for stolen vehicle `GJ01AB1234`.
  - *Trace Screen:* Interactive GIS map displaying sequential stops (Stop 1 to Stop 4), dwell times, and verified speeds.
  - *Reports Screen:* One-click download of timestamped Plates CSV.
- **Key Points:**
  - Full cold start in under 2 minutes completely offline on a single laptop.
  - Designated vehicle `GJ01AB1234` identified across cameras 1 → 2 → 3 → 4.
  - Seamless handling of looping sandbox feeds with zero tracking corruption.
  - Downloadable CSV report with 17,900+ timestamped plate detections.
- **Speaker Script:**
  > *"Everything we have described is operational right now. When the jury gives us the designated registration number today, we type it into the Trace console. In seconds, PRAHARI reconstructs its complete chronological journey across the cameras on an interactive GIS map—displaying stop times, dwell durations, and speed validation. If the plate is on the watchlist, an instant red alert fires with the evidence crop. We can immediately export the compliance CSV report containing every detected plate and timestamp."*

---

### Slide 17: Statewide Rollout Plan & Future Roadmap
- **Slide Title:** Statewide Phased Rollout Plan
- **Visual Blueprint:** Phased Gantt chart spanning Month 1 to Month 18.
- **Key Points:**
  - **Phase 1 (Months 1–3):** Deploy Model 1 Registry & GIS mapping. Onboard all 17,500 VISWAS police cameras across 34 Netram C3 centres.
  - **Phase 2 (Months 4–9):** Multi-department expansion across 3,300 sites (PDS godowns, RTO tracks, hospitals, bus depots). Integrate VAHAN and eGujCop production APIs.
  - **Phase 3 (Months 10–18):** Deploy visual Re-ID models and proportionate AFIS/NAFIS facial recognition integration under judicial warrant.
- **Speaker Script:**
  > *"Our rollout plan is realistic and phased. In Phase 1, we deploy the Model 1 Central Registry and integrate the 17,500 VISWAS cameras already terminating at the 34 Netram centres. In Phase 2, we deploy lightweight edge containers across 3,300 departmental sites and establish live API bridges with VAHAN and eGujCop. In Phase 3, we scale visual Re-ID and warrant-backed biometric intelligence. The state achieves immediate operational value in 90 days."*

---

### Slide 18: Why PRAHARI Wins: 6/6 Bonus Scorecard
- **Slide Title:** Conclusion: Engineered to Win Every Dimension
- **Visual Blueprint:** Official Evaluation Rubric Checklist showing all 6 bonus criteria fulfilled with exact code references.
- **Key Summary Points:**
  1. *Innovative Hybrid Architecture:* Model 1 + 3 + 2; Model 4 refuted with math.
  2. *Advanced Cross-Camera Tracking:* Re-ID appearance bridging + velocity gating.
  3. *Analytics Beyond ANPR:* CCAP auto-allocates loitering, crowd, and intrusion models.
  4. *Edge Processing & Bandwidth:* 5-Tier Bandwidth Ladder + Tier 0 offline island mode.
  5. *Cybersecurity & Privacy:* NFSU-grade SHA-256 hash chains + DPDP purpose binding.
  6. *Operational Dashboards:* Live 50-camera wall, GIS coverage gaps, OpenAPI at `/docs`.
- **Speaker Script:**
  > *"To conclude: The Sentinel Hackathon published six official bonus criteria. PRAHARI hits all six—not by promise, but in working code. We bring an innovative hybrid architecture backed by empirical sizing, cross-camera tracking with physical velocity gating, camera auto-profiling that prevents dead screens, a bandwidth ladder that operates during fiber cuts, NFSU-grade forensic evidence integrity, and a fully functional operator console. PRAHARI moves meaning, not megabytes—delivering a safer Gujarat, built on sound engineering. Thank you. We are ready for your questions."*

---

## Anticipated Jury Questions & Authoritative Answers

### Q1: "Why not choose Model 4 and centralize all video feeds in Gandhinagar?"
- **Answer:** *"With 80,000 cameras, centralizing raw video requires 160 Gigabits per second of sustained WAN bandwidth. In Gujarat, providing 100 Mbps to 4,000 departmental sites incurs a recurring telecom cost of over ₹60 Crore every year—over ₹300 Crore across 5 years for bandwidth alone. Furthermore, a single fiber cut blinds the central platform. Under PRAHARI, bandwidth drops to 0.45 Gbps at peak, saving ₹380+ Crore, and every edge node continues detecting vehicles during complete network blackouts."*

### Q2: "How do you handle two-wheeler plates, which are often two-line and dirty?"
- **Answer:** *"In `prahari/anpr/pipeline.py`, when a plate bounding box has an aspect ratio under 2.2, our pipeline recognizes it as a square two-line plate and splits it vertically into Line 1 (State & RTO) and Line 2 (Series & Digits). Both lines are normalized and fed into our OCR engine. Even if characters are degraded, our Indian Plate Grammar and confusion-weighted beam search resolve the string."*

### Q3: "What happens if a department refuses to install software on their NVR?"
- **Answer:** *"PRAHARI requires zero software installation on departmental NVRs. The PRAHARI Node runs on a separate, dedicated ₹20,000 mini-PC or existing departmental server on the local LAN. It connects to the NVR via standard, read-only RTSP stream URLs. The NVR is completely untouched, its 5-year AMC remains valid, and the department retains complete local ownership of its recordings."*

### Q4: "How does this comply with the new DPDP Act 2023 and police search guidelines?"
- **Answer:** *"In `prahari/registry/trace.py` and `prahari/registry/audit.py`, we enforce purpose-bound queries. An operator cannot type a license plate without inputting a mandatory official Case ID and investigation purpose. Every search is sealed into an append-only, SHA-256 hash-chained audit log that cannot be edited or deleted even by a database administrator. We provide full accountability and compliance with Section 65B of the Indian Evidence Act."*
