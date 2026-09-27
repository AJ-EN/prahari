# PRAHARI — Master Submission Checklist & Verification Audit
**Gujarat Police Sentinel Hackathon 2026 · Integrated Video Management & Analytics Platform**
*Submission Deadline: 28 September 2026 · Grand Finale: 12–13 October 2026*

---

## 1. Executive Deliverables Status Summary

| # | Hackathon Deliverable | Status | File Path / Artifact Location |
|---|---|:---:|---|
| **1** | **Solution Presentation (PPT/PDF)** | **READY** | `docs/presentation/PRAHARI-Solution-Presentation.pptx`<br>`docs/presentation/prahari_presentation.html`<br>`docs/presentation/SLIDE_DECK.md` |
| **2** | **Technical Proposal: High-Level Design (HLD)** | **READY** | `docs/hld/PRAHARI_ARCHITECTURE_AND_HLD.md`<br>`docs/hld/HLD.html` (16-Chapter Master Document) |
| **3** | **Workflow & Integration Diagrams** | **READY** | `docs/architecture/WORKFLOW_AND_INTEGRATION_DIAGRAMS.md`<br>(10 Detailed Mermaid Diagrams mapping to code) |
| **4** | **Demonstration on Participant's Own Feed** | **READY** | `docs/demonstration/OWN_FEED_DEMO_SCRIPT.md`<br>(Timed 2:30 script with click-by-click narration) |
| **5** | **Live Demonstration on Government Feed** | **READY** | `docs/demonstration/GOVERNMENT_FEED_DEMO_SCRIPT.md`<br>(~50 cameras live test case + vehicle trace) |
| **6** | **Output Report of Detected Plates & Timestamps** | **READY** | `data/reports/sample_detected_plates_report.csv`<br>(17,956 detected plate records with GPS & timestamps) |
| **7** | **Model 1 Mandatory Registry Deliverables** | **READY** | Registry UI, 3 onboarding paths, OpenAPI at `/docs`,<br>`data/reports/sample_gap_analysis_report.md` |
| **8** | **Infrastructure Sizing Model (~80,000 Cameras)** | **READY** | `bench/sizing_model.py`, `docs/hld/sizing.md`<br>(160 Gbps → 0.45 Gbps peak; ₹130 Cr vs ₹510 Cr TCO) |
| **9** | **Source Code & Unit Test Verification** | **READY** | 159 / 159 automated unit tests passing<br>`pytest tests/ -q` |

---

## 2. Requirement Traceability Matrix (Official Rubric)

### A. Mandatory Submission Requirements (Step 5)
- [x] **Chosen Model Justification:** Hybrid Model (Model 1 Registry + Model 3 Federation + Model 2 Direct Ingest); Model 4 evaluated and refuted with empirical arithmetic (`docs/hld/PRAHARI_ARCHITECTURE_AND_HLD.md` §1 & §3).
- [x] **High-Level System Architecture:** Complete three-tier topology (Edge Nodes, Netram C3 Centers, SCRB State Tier) documented with Mermaid diagrams (`docs/architecture/WORKFLOW_AND_INTEGRATION_DIAGRAMS.md` §1).
- [x] **AI Video Analytics Approach:** YOLOv8 plate detector, aspect ratio two-line splitter, CRNN OCR, Indian Plate Grammar constrained beam search (`prahari/anpr/`).
- [x] **Watchlist Correlation Methodology:** Confusion-space weighted Levenshtein matching (`O/0`, `I/1`, `B/8`) with automated ALERT, REVIEW, and NEAR-MISS tiers (`prahari/registry/watchlist.py`).
- [x] **Designated Vehicle Route Reconstruction:** Timestamped trajectory search with physical velocity plausibility gating (`prahari/registry/trace.py`).
- [x] **Statewide Sizing for ~80,000 Cameras:** Rigorous cost-benefit model proving ₹130 Cr TCO vs ₹510+ Cr for central streaming (`docs/hld/sizing.md`).
- [x] **Departmental Prerequisites:** System uses Camera Capability Auto-Profiling (CCAP) to measure reality, requiring zero bureaucratic surveys from departments (`prahari/anpr/ccap.py`).

---

### B. Mandatory Model 1 Foundation Deliverables
- [x] **Working Registry Portal with GIS Map View:** Accessible via `http://127.0.0.1:8000/#/registry` and `http://127.0.0.1:8000/#/map`.
- [x] **Three Onboarding Paths Demonstrated:**
  1. *Catalogue URL Sync:* `POST /api/cameras/sync`
  2. *Bulk CSV Import:* `POST /api/cameras/import`
  3. *Single Manual Entry:* `POST /api/cameras`
- [x] **OpenAPI Documentation:** Auto-generated interactive Swagger UI served at `http://127.0.0.1:8000/docs`.
- [x] **Coverage Gap Analysis Report:** Synthesizes 1.0 km spatial grids and identifies blind spots (`data/reports/sample_gap_analysis_report.md`).

---

### C. The Six Official Bonus Criteria (6 of 6 Satisfied)
- [x] **Bonus 1: Innovative Hybrid Architecture:** Combines Model 1, 3, and 2, saving ₹380+ Crore over 5 years.
- [x] **Bonus 2: Advanced Cross-Camera Tracking:** Vehicle visual appearance Re-ID bridging across occluded cameras + Haversine velocity gating.
- [x] **Bonus 3: Analytics Beyond ANPR:** CCAP auto-allocates loitering, crowd density, and person detection on non-viable ANPR cameras.
- [x] **Bonus 4: Edge Processing & Bandwidth Optimization:** 5-Tier Bandwidth Ladder with autonomous Tier 0 offline island mode (zero event loss during WAN cuts).
- [x] **Bonus 5: Cybersecurity, Privacy & Legal Admissibility:** Edge SHA-256 evidence hashing + tamper-evident hash-chained audit ledger compliant with Section 65B BSA 2023; DPDP purpose-bound queries.
- [x] **Bonus 6: Operational Dashboards & Health Monitoring:** Real-time 50-camera video wall, live camera health telemetry, and instant alert notifications.

---

## 3. How to Launch & Verify Everything Locally

```bash
# 1. Activate Environment & Run Tests
source .venv/bin/activate
pytest tests/ -q

# 2. Run Pre-Flight Diagnostics
python run.py doctor

# 3. Launch Demo Mode (Practice Grid with 8 Cameras & GJ01AB1234 Test Car)
python run.py demo
# Open browser at http://127.0.0.1:8000

# 4. View Presentation Deck in Browser
open docs/presentation/prahari_presentation.html

# 5. Open Microsoft PowerPoint Presentation
open docs/presentation/PRAHARI-Solution-Presentation.pptx
```
