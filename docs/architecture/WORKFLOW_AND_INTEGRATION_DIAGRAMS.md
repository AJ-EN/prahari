# PRAHARI — Complete Workflow & Integration Diagrams
**Gujarat Police Sentinel Hackathon 2026 · Integrated Video Management & Analytics Platform**

> **Core System Thesis:** *Move meaning, not megabytes.* Video stays where it is born. Only structured observations cross the state. The registry is the brain.
>
> This document details the technical workflows, data pipelines, and architectural integration boundaries of **PRAHARI**, directly derived from the production codebase (`prahari/`).

---

## 1. System-Wide Tiered Topology & Multi-Department Integration

PRAHARI implements **Hybrid Model 5** (Model 1 Registry + Model 3 Federation Middleware + Model 2 Direct Ingest for unmanaged streams). 
Video never leaves departmental premises unless an explicit, signed clip-pull request with an active Case ID is issued.

```mermaid
flowchart TB
    subgraph DEPT["Department Premises (26 Independent Departments)"]
        direction TB
        CAMS["Heterogeneous Cameras<br/>(Analog, IP, H.264, H.265, 480p-4K)"] --> NVR["Existing NVR / DVR / VMS<br/>(Hikvision, Dahua, Milestone, Genetec)"]
        NVR -->|"RTSP / ONVIF / HLS (LAN only)"| NODE["PRAHARI Edge Node<br/>(One Container / Lightweight Mini-PC)"]
        
        subgraph NODE_BOX["Inside PRAHARI Node (prahari.node & prahari.anpr)"]
            CAP["Capture Manager<br/>(TCP Enforced, PTS Driven)"] --> CCAP["CCAP Profiler<br/>(Capability Measurement)"]
            CCAP --> ANPR["ANPR & Analytics Engine<br/>(ONNX Runtime / TensorRT)"]
            ANPR --> DISK["Local Ring Buffer & Queue<br/>(72h Evidence & Offline Spool)"]
        end
    end

    NODE -->|"Outbound mTLS (TCP 443)<br/>Events ~550 B · Crops ~15 KB<br/>NO CONTINUOUS VIDEO"| REGIONAL["Regional Tier (34 Netram District C3 Centres)"]

    subgraph REGIONAL["Regional Tier: 34 Netram Command Centres"]
        NETRAM_INGEST["Regional Event Aggregator<br/>(NATS JetStream Leaf Node)"]
        NETRAM_GPU["GPU Acceleration Pool<br/>(2x NVIDIA L4 per Netram Server)"]
        NETRAM_C3["District Police Wall & GIS View"]
    end

    REGIONAL -->|"Backbone WAN (~450 Mbps Statewide Peak)"| STATE["Central Tier: State Crime Records Bureau (SCRB Gandhinagar)"]

    subgraph STATE["Central Tier (SCRB / State Data Centre)"]
        direction TB
        GATEWAY["mTLS Reverse Proxy & API Gateway<br/>(Kong / NGINX)"]
        EVENT_BUS["High-Throughput Event Bus<br/>(NATS JetStream / Apache Kafka)"]
        
        subgraph CORE["State Brain & Engines"]
            REGISTRY["Central Registry (Model 1)<br/>(PostgreSQL + PostGIS)"]
            MATCHER["Watchlist Correlation Engine<br/>(Confusion-Space Matcher)"]
            TRACER["Trajectory Reconstruction<br/>(Velocity-Gated Cross-Camera Trace)"]
            VAULT["Evidence Vault & Hash Chain<br/>(SHA-256 Tamper-Evident Log)"]
        end
        
        GATEWAY --> EVENT_BUS
        EVENT_BUS --> MATCHER
        EVENT_BUS --> REGISTRY
        EVENT_BUS --> VAULT
        MATCHER --> TRACER
    end

    subgraph ADAPTERS["External Government Database Adapters"]
        VAHAN[("VAHAN API<br/>Vehicle Registration")]
        SARTHI[("SARTHI API<br/>Driving Licenses")]
        EGUJCOP[("eGujCop / CCTNS<br/>FIRs & Stolen Vehicles")]
        NAFIS[("AFIS / NAFIS<br/>Biometrics & Fingerprints")]
    end

    MATCHER <--> ADAPTERS

    subgraph CLIENTS["Command & Control Visualisation"]
        CONSOLE["Operator Console (React / MapLibre)<br/>- 50-Tile Adaptive Video Wall<br/>- GIS Map & Coverage Gap Layers<br/>- Real-time Alert & Review Queue<br/>- Trace Timeline & Speed Verification"]
    end

    STATE -->|"Real-time SSE / WebSocket"| CONSOLE
```

---

## 2. Camera Feed Ingestion & Capture Worker Loop (`prahari.node.capture`)

The ingestion pipeline handles non-uniform frame arrivals, GOP replays on reconnect, and prevents memory leaks using single-frame drop buffers.

```mermaid
sequenceDiagram
    autonumber
    participant Cam as CCTV / RTSP Gateway (cctv.corp8.cloud)
    participant Worker as CameraWorker (prahari.node.capture)
    participant FFmpeg as PyAV / FFmpeg Context (TCP Transport)
    participant Buffer as Single-Frame Slot (Atomic Lock)
    participant Mgr as NodeManager (prahari.node.manager)
    participant Runtime as ANPR Scheduler (prahari.runtime)

    Mgr->>Worker: start()
    Worker->>FFmpeg: av.open(rtsp_url, options={'rtsp_transport': 'tcp', 'stimeout': 5000000})
    Note over Worker,FFmpeg: Strict TCP prevents UDP NAT packet drops
    
    loop Stream Decoding
        FFmpeg->>Worker: Packet received (PTS, DTS, keyframe flag)
        alt Decoder Parameter Change / RPS Warning
            Worker->>Worker: Log warning, wait for next IDR (no crash)
        else Valid Video Packet
            Worker->>Worker: Extract Packet PTS (Presentation Timestamp)
            Note over Worker: Never trust CAP_PROP_FPS or arrival time
            Worker->>Buffer: Store latest FrameSample(bgr, pts, epoch_s) (overwrite older)
        end
    end

    alt Stream Disconnect / Network Failure
        FFmpeg-->>Worker: Connection Drop / EOF
        Worker->>Mgr: Notify backoff state
        Worker->>Worker: Exponential backoff delay (2s -> 4s -> 8s -> max 30s)
        Worker->>FFmpeg: Reconnect
        Worker->>Runtime: _on_discontinuity(camera_id) (Flush Kalman & ReID galleries)
    end

    Runtime->>Buffer: latest(camera_id)
    Buffer-->>Runtime: Returns freshest FrameSample for inference
```

---

## 3. Camera Capability Auto-Profiling (CCAP) Lifecycle (`prahari.anpr.ccap`)

CCAP solves the core real-world challenge: heterogeneous cameras across 26 departments (e.g. hospital corridors vs toll gates). 
It actively profiles cameras and automatically allocates compute only where plates can physically be read.

```mermaid
stateDiagram-v2
    [*] --> Accumulating: Camera Onboarded
    
    state Accumulating {
        [*] --> SamplingFrames: Capture Frames
        SamplingFrames --> ExtractingMetrics: Run YOLO & OCR
        ExtractingMetrics --> UpdatingStats: Update frames, plates, bbox heights, valid rates
    }

    Accumulating --> Evaluating: frames >= 30 AND plates >= 5
    Accumulating --> InsufficientData: frames < 30 OR plates < 5

    state Evaluating {
        [*] --> CheckPixelHeight: Calculate Median Plate Pixel Height (plate_px_median)
        
        CheckPixelHeight --> UnviableHeight: plate_px_median < 24 px
        note right of UnviableHeight: Heuristic: Single-line exact-read rate drops below 40% under 24px
        
        CheckPixelHeight --> CheckLegibility: plate_px_median >= 24 px
        
        CheckLegibility --> UnviableLegibility: valid_rate < 0.33
        note right of UnviableLegibility: More than 67% reads fail Indian Plate Grammar (Glare, Angle, Dirt)
        
        CheckLegibility --> ViableOK: valid_rate >= 0.33
    }

    UnviableHeight --> MarkUnviable: Set anpr_viable = False
    UnviableLegibility --> MarkUnviable: Set anpr_viable = False
    ViableOK --> MarkViable: Set anpr_viable = True

    MarkViable --> DynamicScheduler: Sample every 1 frame (Full Rate)
    MarkUnviable --> DynamicScheduler: Sample 1 frame in 10 (Conserve 90% GPU budget)
    InsufficientData --> DynamicScheduler: Sample every 1 frame (Collecting Evidence)
```

---

## 4. ANPR Detection, Two-Line Handling & Grammar-Constrained OCR Pipeline

This diagram shows how raw pixels are transformed into grammatically validated license plates using `prahari.anpr.pipeline` and `prahari.common.plate_grammar`.

```mermaid
flowchart TD
    FRAME["Incoming FrameSample (BGR, PTS, camera_id)"] --> DET_PREP["Letterbox Preprocessing (640x640 / 960x960)"]
    DET_PREP --> YOLO_DET["Plate Detection Model (YOLO-v8 / ONNX CoreML/CUDA)"]
    YOLO_DET --> NMS["Non-Maximum Suppression (Conf >= 0.3, IoU >= 0.45)"]
    
    NMS --> BBOX{"Bounding Box Detected?"}
    BBOX -->|No| DROP["Discard Frame / Return Empty"]
    BBOX -->|Yes| CROP["Crop License Plate Region"]
    
    CROP --> ASPECT{"Aspect Ratio Check (w/h)"}
    ASPECT -->|"w/h < 2.2 (Two-Line Square Plate)"| SPLIT["Split Vertically into Line 1 & Line 2 (Two-Wheeler / Taxi)"]
    ASPECT -->|"w/h >= 2.2 (Standard Long Plate)"| SINGLE["Single Line Normalisation"]
    
    SPLIT --> OCR_IN["OCR Normalisation (Grayscale / Contrast / 48px height)"]
    SINGLE --> OCR_IN
    
    OCR_IN --> OCR_NET["OCR Recurrent Model (CRNN / SVTR / ONNX)"]
    OCR_NET --> CTC_RAW["Raw OCR Posterior & Greedy String (e.g. '6J01A8I234')"]
    
    CTC_RAW --> GRAMMAR{"Validate against Indian Plate Grammar<br/>(State Code + RTO + Series + 4 Digits)"}
    
    GRAMMAR -->|Valid Direct| CLEAN_PLATE["Validated Plate: 'GJ01AB1234'<br/>grammar_valid = True"]
    GRAMMAR -->|Invalid Syntax| BEAM["Constrained Beam Search over OCR Posteriors<br/>Cost Matrix: 6->G (0.2), 8->B (0.15), I->1 (0.1)"]
    
    BEAM --> RESOLVED{"Grammar Resolution"}
    RESOLVED -->|Success| REPAIRED["Corrected Plate: 'GJ01AB1234'<br/>grammar_valid = False, plate = 'GJ01AB1234'"]
    RESOLVED -->|Ambiguous / Bad| FALLBACK["Keep Raw Text: '6J01A8I234'<br/>grammar_valid = False, plate = ''"]
    
    CLEAN_PLATE --> DEDUP["PlateDeduper (6.0s Rolling Time Window)"]
    REPAIRED --> DEDUP
    FALLBACK --> DEDUP
    
    DEDUP --> EMIT["Emit PlateEvent (event_id, ts, plate, raw_text, bbox, crop)"]
```

---

## 5. Confusion-Space Watchlist Matching Engine (`prahari.registry.watchlist`)

Unlike naive systems that use brittle `SELECT * WHERE plate = ocr` queries, PRAHARI computes OCR-confusion-weighted edit distances and delivers graded alert tiers.

```mermaid
flowchart LR
    subgraph INGEST["Event Ingest"]
        EV["Incoming PlateEvent<br/>- plate: GJ01AB1234<br/>- raw_text: 6J01A8I234<br/>- candidates: [GJ01AB1234]"]
    end

    subgraph MATCH_ENGINE["Matching Engine (prahari.registry.watchlist)"]
        WL_CACHE["Watchlist InMemory / DB Cache<br/>(Indexed Plates, Categories, Priority)"]
        
        DIST_CALC["Confusion Distance Calculator<br/>d(q, s) = Weighted Levenshtein<br/>- Identical char: 0.0<br/>- OCR confusion (O/0, I/1, B/8): 0.1-0.2<br/>- Other replacement: 1.0"]
        
        RANKER["Candidate Ranker<br/>Score = 1.0 - (distance / max(len(q), len(s)))"]
    end

    subgraph THRESHOLDS["Classification Thresholds"]
        DECISION{"Distance Threshold"}
        ALERT["ALERT (High Confidence)<br/>d <= 0.15 (Score >= 0.85)<br/>Automated Real-time Dispatch"]
        REVIEW["REVIEW (Close Ambiguity)<br/>0.15 < d <= 0.35 (Score 0.65-0.85)<br/>Queued for Human Operator"]
        NEAR_MISS["NEAR-MISS (Investigative)<br/>0.35 < d <= 0.50<br/>Available in 'Did You Mean' Query"]
        IGNORE["Discard / Background Log<br/>d > 0.50"]
    end

    EV --> DIST_CALC
    WL_CACHE --> DIST_CALC
    DIST_CALC --> RANKER
    RANKER --> DECISION
    
    DECISION -->|d <= 0.15| ALERT
    DECISION -->|0.15 < d <= 0.35| REVIEW
    DECISION -->|0.35 < d <= 0.50| NEAR_MISS
    DECISION -->|d > 0.50| IGNORE
    
    ALERT --> BUS["SSE / WebSocket Alert Bus -> UI & SMS/Telegram Dispatch"]
    REVIEW --> BUS
```

---

## 6. Cross-Camera Re-ID & Velocity-Gated Trajectory Reconstruction (`prahari.registry.trace`)

When tracing a suspect vehicle across Gujarat's highway grid, PRAHARI connects sightings, bridges unreadable plates with vehicle appearance, and physically validates each hop against road physics.

```mermaid
sequenceDiagram
    autonumber
    actor Investigator as Investigating Officer
    participant API as /api/trace Endpoint (prahari.registry.trace)
    participant Audit as Hash-Chained Audit Log (prahari.registry.audit)
    participant Store as SQLite / TimescaleDB Store
    participant Geo as Geodesy Engine (prahari.registry.geo)
    participant Console as GIS Trace UI (MapLibre Leaflet)

    Investigator->>API: GET /api/trace?plate=GJ01AB1234&purpose=Stolen_Vehicle_FIR_129&case_id=CR-2026-9912
    
    Note over API,Audit: DPDP Act 2023 Compliance: Purpose & Case ID Mandatory
    API->>Audit: append(actor='inspr_patel', action='trace', purpose='...', case_id='...')
    Audit-->>API: Entry SHA-256 Hashed & Chained

    API->>Store: scan(query='GJ01AB1234', t_from, t_to)
    Store-->>API: Raw sightings matching query within confusion distance <= 0.5

    API->>API: 1. Group & collapse consecutive reads at same camera (collapse_s = 60s)
    
    loop For each consecutive camera hop (A -> B)
        API->>Geo: haversine_km(latA, lonA, latB, lonB)
        Geo-->>API: straight_line_distance_km
        API->>API: time_delta_hours = (tsB - tsA) / 3600
        API->>API: implied_speed_kmh = straight_line_distance_km / time_delta_hours
        
        alt implied_speed_kmh <= 150 km/h
            API->>API: Mark Hop: plausible = True
        else implied_speed_kmh > 150 km/h
            API->>API: Mark Hop: plausible = False, reason = 'Speed exceeds 150 km/h (Possible cloned plate or misread)'
        end
    end

    API-->>Console: Structured Route JSON (Stops, Coordinates, Dwell Times, Speed, Plausibility)
    Console->>Console: Render interactive polyline on map, color-code implausible hops in amber/red
```

---

## 7. Zero-Inbound Outbound mTLS & Bandwidth Ladder (`prahari.node.manager`)

How PRAHARI functions reliably even in remote tribal blocks (Dahod, Dangs) and border outposts with unstable 2G/4G connectivity.

```mermaid
flowchart TD
    UPLINK["Uplink Monitor: Continuous RTT & Throughput Probe"] --> EVAL{"Measured WAN Bandwidth"}
    
    EVAL -->|"> 10 Mbps (Optical Fibre / 5G)"| T4["Tier 4: Full Spectrum<br/>- All Plate & Analytic Events<br/>- High-Res Evidence Crops (15 KB)<br/>- Periodic Camera Thumbnails (5s)<br/>- On-Demand HD Live Video Relay"]
    
    EVAL -->|"2 to 10 Mbps (Standard Broadband / 4G)"| T3["Tier 3: Standard Operations<br/>- All Plate & Analytic Events<br/>- Full Evidence Crops for all events<br/>- Thumbnails throttled to 30s"]
    
    EVAL -->|"0.2 to 2 Mbps (Constrained Cellular / 3G)"| T2["Tier 2: Watchlist-Prioritised<br/>- All Text Metadata Events<br/>- Crops transmitted ONLY for Watchlist Matches<br/>- Routine crops held in local disk ring-buffer"]
    
    EVAL -->|"< 200 kbps (Degraded / 2G / Satellite)"| T1["Tier 1: Ultra-Low Bandwidth<br/>- Compressed JSON Text Events Only (~120 B/ev)<br/>- Batched gzip transmission every 60s<br/>- Zero image/video transmission"]
    
    EVAL -->|"0 kbps (Total WAN Blackout / Fiber Cut)"| T0["Tier 0: Autonomous Island Mode<br/>- Continuous Local Inference & ANPR<br/>- SQLite Local Disk Spool (data/spool.db)<br/>- 72-Hour FIFO Video & Crop Ring Buffer<br/>- Zero Data Loss: Auto-Replay & Backfill on Reconnect"]

    T4 --> OUTBOUND["Outbound Only mTLS Gateway (Port 443)<br/>NO Inbound Ports Open · Firewall Traversal Complete"]
    T3 --> OUTBOUND
    T2 --> OUTBOUND
    T1 --> OUTBOUND
    T0 --> SINK[("Local SSD Ring Buffer")]
```

---

## 8. Cryptographic Chain-of-Custody & Tamper-Evident Audit Log (`prahari.registry.audit`)

Designed specifically for the National Forensic Sciences University (NFSU) evaluators and Section 65B Bharatiya Sakshya Adhiniyam compliance.

```mermaid
sequenceDiagram
    autonumber
    participant Cam as CCTV Camera
    participant Edge as Edge Node (prahari.node)
    participant Central as State Evidence Vault (prahari.registry.audit)
    participant Court as Forensic Auditor / NFSU Examiner

    Cam->>Edge: Video Frame with License Plate
    Edge->>Edge: Capture Frame & Crop Plate
    Edge->>Edge: Compute SHA-256 Hash of JPEG Crop (evidence_sha256)
    Edge->>Central: Transmit Event + evidence_sha256 + Model Version + PTS
    
    Central->>Central: Fetch previous block hash (prev_hash)
    Central->>Central: Construct JSON Canonical Payload:<br/>[ts, actor, action, purpose, case_id, params, prev_hash]
    Central->>Central: block_hash = SHA256(canonical_payload)
    Central->>Central: INSERT INTO audit_log VALUES (..., prev_hash, block_hash)
    Note over Central: SQLite Triggers PREVENT ANY UPDATE or DELETE on audit_log
    
    Court->>Central: Run audit verification (/api/audit/verify)
    loop Every Entry from Genesis ("0"*64) to Head
        Central->>Central: Recompute SHA-256 over linked blocks
        alt Hash Mismatch or Broken Link
            Central-->>Court: FAIL: Tampering detected at Entry #ID!
        end
    end
    Central-->>Court: PASS: Untampered Chain (Head Hash: a4f8...b129)
    Court->>Court: Certificate of Admissibility Generated
```

---

## 9. Model 1 Central Registry Onboarding & Geospatial Coverage Gap Analysis (`prahari.registry.reports`)

Demonstrating compliance with Mandatory Model 1 requirements: 3 onboarding paths, interactive GIS layers, and spatial gap reports.

```mermaid
flowchart TB
    subgraph ONBOARDING["Three Onboarding Paths (Model 1 Requirement)"]
        direction LR
        P1["Path 1: Dynamic Catalogue Sync<br/>POST /api/cameras/sync<br/>Fetches JSON from URL"]
        P2["Path 2: Bulk CSV Import<br/>POST /api/cameras/import<br/>Uploads departmental CSV"]
        P3["Path 3: Manual Entry / Single API<br/>POST /api/cameras<br/>Single camera registration"]
    end

    ONBOARDING --> UPSERT["Database Upsert Engine (prahari.registry.cameras)<br/>- Normalises Coordinates (Rejects Null Island [0,0])<br/>- Standardises Department Names<br/>- Preserves Stream Credentials"]

    UPSERT --> DB[("PostgreSQL / SQLite Registry Store<br/>Table: cameras")]

    subgraph ANALYTICS["Coverage Gap & Spatial Intelligence (prahari.registry.reports)"]
        DB --> LOC_FILTER["Filter Located Cameras (lat, lon != null)"]
        LOC_FILTER --> BBOX["Compute Bounding Box (minLon, minLat, maxLon, maxLat)"]
        BBOX --> GRID["Synthesise 1.0 km Geodesic Grid (cell_km = 1.0)"]
        
        GRID --> DIST_CHECK["Haversine Distance Matrix: Cell Center -> All Cameras"]
        DIST_CHECK --> CLASSIFY{"Nearest Camera <= radius_km (1.0 km)?"}
        
        CLASSIFY -->|Yes| COVERED["Mark Cell: Covered"]
        CLASSIFY -->|No| GAP["Mark Cell: UNCOVERED GAP"]
        
        GAP --> RANK_GAPS["Rank Worst Gaps by Distance to Nearest Camera"]
        COVERED --> HEALTH_FILTER["Filter by Camera Health (exclude offline/stale)"]
        HEALTH_FILTER --> EFF_COV["Calculate Effective Operational Coverage %"]
    end

    RANK_GAPS --> REPORT_GEN["Generate Gap Analysis Report<br/>- Markdown Table (/api/reports/gap?format=md)<br/>- GeoJSON Map Layer (/api/reports/gap?format=json)"]
    EFF_COV --> REPORT_GEN
    REPORT_GEN --> UI["Interactive GIS Map & Downloadable Report"]
```

---

## 10. Multi-Agency Government Database Federation Interface

How PRAHARI bridges live edge surveillance with national and state databases (VAHAN, SARTHI, eGujCop, AFIS/NAFIS).

```mermaid
flowchart LR
    subgraph PRAHARI_CORE["PRAHARI Event Engine"]
        PLATE_EV["Validated Plate Event<br/>GJ01AB1234"]
        REID_EV["Vehicle Appearance Vector<br/>[White, Hatchback, Swift]"]
    end

    subgraph FED_LAYER["Federation Adapter Middleware (Model 3 Spine)"]
        ROUTER["Government Adapter Dispatcher"]
        
        A_VAHAN["VAHAN Adapter<br/>- REST / SOAP Client<br/>- Vehicle Make, Model, Fuel, Owner"]
        A_EGUJ["eGujCop (CCTNS) Adapter<br/>- Stolen Vehicle FIR Database<br/>- Wanted Suspect Watchlists"]
        A_SARTHI["SARTHI Adapter<br/>- Driver License Verification"]
        A_NAFIS["AFIS / NAFIS Adapter<br/>- Biometric Reference Link"]
    end

    subgraph EXTERNAL["Official State & National Infrastructure"]
        DB_V[("National VAHAN 4.0")]
        DB_E[("Gujarat Police eGujCop")]
        DB_S[("MoRTH SARTHI 4.0")]
        DB_N[("NCRB NAFIS")]
    end

    PLATE_EV --> ROUTER
    REID_EV --> ROUTER
    
    ROUTER --> A_VAHAN <--> DB_V
    ROUTER --> A_EGUJ <--> DB_E
    ROUTER --> A_SARTHI <--> DB_S
    ROUTER --> A_NAFIS <--> DB_N

    A_VAHAN --> ENRICH["Enriched Intel Record<br/>- Owner Name & Address<br/>- Registered Colour & Model<br/>- Active FIR Status (eGujCop)"]
    A_EGUJ --> ENRICH
    
    ENRICH --> DISPATCH["Automated Police Control Room Dispatch<br/>(112 Dial, PCR Van CAD, Push Notification)"]
```
