# Part 5 — The Scorecard: Every Single Thing They Want

Every requirement extracted from the official site, made traceable. **Nothing here is optional except where marked BONUS.**
Status: ☐ not started · ◐ in progress · ☑ done

---

## A. MANDATORY SUBMISSION ARTIFACTS (deadline **28 Sep 2026**)

### A1 — Solution Presentation (PPT/PDF)
| ☐ | Item |
|---|---|
| ☐ | Model chosen (1–5 / Hybrid / Custom) **with justification** |
| ☐ | Solution overview, objectives, key innovations |
| ☐ | High-level system architecture + end-to-end workflow |
| ☐ | AI video analytics approach: detection, recognition, event analytics |
| ☐ | **Methodology for correlating live feeds with watchlist DBs + automated real-time alerts** |
| ☐ | Key technologies, frameworks, tools |
| ☐ | Scalability, interoperability, security, deployment considerations |
| ☐ | Expected operational benefits + impact on policing and public safety |

### A2 — Technical Proposal / High-Level Design (HLD)
| ☐ | Item |
|---|---|
| ☐ | Overall architecture + diagrams + component interactions |
| ☐ | Approach for integrating heterogeneous cameras, NVRs, VMS into one platform |
| ☐ | Architecture for ingesting/processing/managing streams from **geographically dispersed** sites |
| ☐ | Watchlist integration approach (stolen vehicles, wanted/missing persons, blacklisted vehicles, suspects) + continuous correlation → real-time alerts |
| ☐ | AI analytics: **ANPR, FRS, object detection, person & vehicle tracking** + any additional |
| ☐ | Alert generation & notification workflow: **prioritisation, visualisation, user interaction** |
| ☐ | Scalability / interoperability / security / performance for statewide **~80,000 cameras** |
| ☐ | **Technical prerequisites, assumptions, and information required from departments** ← *answer: CCAP measures it* |

### A3 — Demonstration on Participant's Own Feed (2–3 min screen recording)
| ☐ | Item |
|---|---|
| ☐ | Onboarding + processing of live/recorded feeds |
| ☐ | AI detection & analytics (ANPR / FRS / other) |
| ☐ | Correlation of detected entities against a representative watchlist |
| ☐ | Automatic real-time alert generation + visualisation on match |
| ☐ | ⚠️ **Fully functional working solution — mock-ups, animations and concept videos are explicitly rejected** |

### A4 — Live Demonstration on Government-Provided Feed
| ☐ | Item |
|---|---|
| ☐ | Onboard the government feed(s) onto the platform |
| ☐ | Demonstrate successful onboarding + live/recorded viewing |
| ☐ | Demonstrate video-analytics output on the provided feed |
| ☐ | Screen-recorded video **+ output report showing detected vehicles/plates with timestamps** |

### A5 — Submission Mechanics *(criterion #7 = free marks; do not lose them)*
| ☐ | Item |
|---|---|
| ☐ | YouTube link — visibility set to **Unlisted** |
| ☐ | Drive/OneDrive link — **"Anyone with the link — Viewer"** (test in incognito!) |
| ☐ | *(optional, do it)* Hosted platform URL **+ test login credentials** for the screening committee |
| ☐ | *(optional, do it)* GitHub/GitLab repo link with source |
| ☐ | Every link verified from a logged-out browser |

---

## B. SCALABILITY PLAN — ~80,000 CAMERAS (Step 6, explicitly enumerated)
| ☐ | Item |
|---|---|
| ☐ | Central, regional and **edge** compute requirements |
| ☐ | GPU / accelerator requirements for analytics |
| ☐ | Expected network bandwidth **+ low-bandwidth strategies** |
| ☐ | Hot / warm / cold storage assumptions based on retention periods |
| ☐ | Load balancing, horizontal scaling, monitoring, logging, health checks |
| ☐ | High availability, backup, **disaster recovery**, cybersecurity controls |
| ☐ | **Estimated implementation and operational costs** ← the ₹-crore table |

---

## C. SOLUTION DESIGN DIMENSIONS (Step 3 — all ten must appear)
`☐ Overall Architecture` `☐ Integration Strategy` `☐ AI & Video Analytics` `☐ Cybersecurity Architecture` `☐ Deployment Architecture` `☐ Infrastructure Sizing` `☐ Cost-Benefit Analysis` `☐ Department-wise Information Requirements` `☐ Scalability Strategy` `☐ Future Roadmap`

---

## D. LIVE TECHNICAL EVALUATION (Step 4 — this is where it is won)
| ☐ | Item |
|---|---|
| ☐ | Onboard **~50** geographically distributed heterogeneous cameras — *all of them, not six* |
| ☐ | Centralised monitoring across all onboarded cameras |
| ☐ | AI-powered video analytics running on the grid |
| ☐ | **Given a plate on the day: identify, trace and present that vehicle's movement across the network** |
| ☐ | Complete route + **timestamped, location-wise movement history** |
| ☐ | Working watchlist DB + continuous cross-referencing + automated real-time alerts |
| ☐ | Evidence of integration, analytics, interoperability, scalability, end-to-end performance |
| ☐ | GIS visualisation of route, movement history, searchable events |

---

## E. MODEL 1 — MANDATORY REGISTRY (required in every submission)
| ☐ | Item |
|---|---|
| ☐ | **Working registry portal with GIS map view** |
| ☐ | **Bulk import + manual entry + API-based** camera onboarding (demonstrate all three) |
| ☐ | Sample onboarded camera-metadata dataset |
| ☐ | **Registry API documentation** |
| ☐ | **Sample gap-analysis report** |
| ☐ | Interactive GIS map: department / camera type / status / coverage layers |
| ☐ | Camera health and maintenance-status monitoring |
| ☐ | Gap analysis: uncovered zones + ageing infrastructure |
| ☐ | Role-based search, filtering, export, **metadata audit trails** |

## E2 — Model 3 deliverables (our federation spine)
| ☐ | Item |
|---|---|
| ☐ | Working middleware federating **≥2 different systems** |
| ☐ | Unified **event-correlation** dashboard |
| ☐ | **Adapter/plugin architecture documentation** |
| ☐ | Sample **federated analytics report** |

## E3 — Model 2 elements we adopt
| ☐ | Item |
|---|---|
| ☐ | Feed aggregation via RTSP / ONVIF / vendor APIs |
| ☐ | ANPR-based metadata generation |
| ☐ | Event tagging + camera-wise indexing |
| ☐ | Searchable vehicle-movement records |
| ☐ | **Configurable video walls / multi-camera grid** |
| ☐ | Alerts for tagged events and vehicles of interest |
| ☐ | Architecture note: **existing departmental systems remain unaffected** |

---

## F. GOVERNMENT DATABASE INTEGRATION (adapters + mocks now, real later)
| ☐ | DB | Contains |
|---|---|---|
| ☐ | **VAHAN** | vehicle registration, owner, make/model/colour |
| ☐ | **SARTHI** | driving licences |
| ☐ | **eGujCop** (CCTNS) | FIRs, arrested persons, wanted criminals |
| ☐ | **AFIS / NAFIS** | fingerprints |
| ☐ | Watchlist entities: stolen vehicles, wanted persons, missing persons, unidentified bodies, blacklisted vehicles, suspects |

> Build a **documented adapter interface** with realistic mock implementations + record/replay fixtures. Say plainly: *"production credentials are a departmental provisioning step; the interface is complete and tested."* That is the honest, credible position — and far stronger than pretending to have live access.

---

## G. OFFICIAL PRE-SUBMISSION CHECKLIST (verbatim from the Resources page — treat as scored)
| ☐ | Item |
|---|---|
| ☐ | Every client **forces RTSP over TCP** |
| ☐ | **No timing logic** depends on `CAP_PROP_FPS` or frame arrival time |
| ☐ | Inter-frame gaps do not crash or stall the pipeline |
| ☐ | **Reconnect with backoff implemented AND tested by restarting a feed** |
| ☐ | Decoder warnings on join are **logged, not fatal** |
| ☐ | Camera list + per-camera properties read from **`/api/ingest`** |
| ☐ | Handles mixed **H.264/H.265** and mixed resolutions |
| ☐ | Behaviour sane across a **scene discontinuity** (loop point) |

---

## H. BONUS CONSIDERATION (all six, deliberately)
| ☐ | Criterion | Component |
|---|---|---|
| ☐ | Innovative hybrid/customised architecture with operational value | Model 1+3+2; Model 4 rejected with arithmetic |
| ☐ | Advanced cross-camera vehicle tracking / multi-camera correlation | §C Re-ID-bridged trajectory |
| ☐ | Additional reliable analytics beyond mandatory ANPR | §A CCAP-driven pipelines |
| ☐ | Strong edge processing / bandwidth optimisation / low connectivity | §E Bandwidth ladder, tier-0 offline |
| ☐ | Enhanced cybersecurity, privacy, auditability, RBAC | §Vault + §Shield |
| ☐ | Operational dashboards, alerts, health monitoring, integration-ready APIs | Console + Registry + OpenAPI |

---

## I. ADMIN & ELIGIBILITY — *do these first, they gate everything*
| ☐ | Item |
|---|---|
| ☐ | 🔴 **Register on the portal** — required for access to the ~50 live feeds |
| ☐ | 🔴 Confirm **Category 1 vs Category 2** (see `02-game-theory-and-win-strategy.md` §1.2) |
| ☐ | 🔴 **Email organisers to resolve the top-3-per-category vs top-6-pooled contradiction** |
| ☐ | DPIIT Startup Recognition Certificate, if registering as a startup |
| ☐ | Pull `/api/ingest` and archive the full camera catalogue |
| ☐ | Verify RTSP reachability from your network; **test HLS fallback if port 8554 is blocked** |

---

## J. CALENDAR
| Date | Event |
|---|---|
| **18 Sep 2026** | today |
| **28 Sep 2026** | 🔴 **Registration AND submission close** · shortlisting |
| **12–13 Oct 2026** | Grand Finale — live production round |
| **13 Oct 2026** | Results |

**10 days to submission. 24 days to the finale.**
