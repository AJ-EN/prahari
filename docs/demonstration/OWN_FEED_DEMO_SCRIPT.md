# PRAHARI — Participant's Own-Feed Demonstration Script
**Gujarat Police Sentinel Hackathon 2026 · Submission Item A3**
*Duration: 2 Minutes 30 Seconds (Within the official 2–3 minute limit)*

> **Official Requirement (Step 5.3):**
> *"Submit a screen-recorded demonstration (maximum 2–3 minutes) showcasing your solution operating on CCTV cameras or video footage of your choice. The demonstration must showcase a fully functional working solution. Mock-ups, animations, simulated interfaces, or concept videos without an operational backend will not be considered."*

---

## 1. Setup & Pre-Recording Verification

### Command to Execute:
```bash
# Terminal 1: Launch PRAHARI in Demo Mode with Practice Camera Grid
source .venv/bin/activate
python run.py demo
```

The system will start 8 synchronized cameras (`Police 1–6`, `Health 7`, `GSRTC 8`) with a simulated vehicle route (`GJ01AB1234` passing cameras 1 → 2 → 3 → 4) and serve the console at **`http://127.0.0.1:8000`**.

---

## 2. Timed Voiceover Script & Click-by-Click Screen Actions

### [0:00 – 0:25] Introduction & Multi-Camera Video Wall
- **Screen Action:** Open browser at `http://127.0.0.1:8000/#/wall`. Show the 8 live camera tiles playing video simultaneously. Point cursor to green bounding boxes detecting vehicle plates in real time. Click on a tile to reveal camera details (codec, resolution, true FPS).
- **Voiceover Script:**
  > *"Welcome to the demonstration of PRAHARI, an integrated video management and analytics platform engineered for the Gujarat Police Sentinel Hackathon. We are running live on our practice feed. On the Video Wall, you can see 8 live camera streams decoding concurrently. Notice the green bounding boxes dynamically localizing license plates as vehicles pass. All stream ingestion enforces RTSP over TCP, extracting presentation timestamps directly from container packets to ensure frame accuracy without depending on network arrival times."*

---

### [0:25 – 0:55] Camera Capability Auto-Profiling (CCAP)
- **Screen Action:** Navigate to `http://127.0.0.1:8000/#/registry`. Scroll to Camera 7 (`Civil Hospital OPD Corridor`) and Camera 8 (`GSRTC Bus Depot`). Click Camera 7 to open the capability profile drawer. Highlight `anpr_viable: false` and the measured reason `plates too small (8.2px < 24px threshold)`.
- **Voiceover Script:**
  > *"Here is our flagship innovation: Camera Capability Auto-Profiling (CCAP). In a heterogeneous statewide deployment across 26 departments, cameras in hospital corridors and depot counters will never show readable plates. Instead of wasting GPU cycles or presenting dead panels, PRAHARI measures each stream for 60 seconds. Camera 7, inside Civil Hospital, is measured at a median plate height of only 8 pixels. The system automatically classifies it as ANPR-unviable, throttles its sampling by 90% to conserve compute, and assigns it to crowd density analytics. PRAHARI discovers what cameras can do without requiring manual surveys."*

---

### [0:55 – 1:30] Watchlist Matching & Automated Real-Time Alerts
- **Screen Action:** Navigate to `http://127.0.0.1:8000/#/alerts`. Show the real-time Alert feed. Point to the red alert banner that just arrived for `GJ01AB1234` (Category: `stolen_vehicle`). Click the alert card to display the high-resolution evidence crop, OCR confidence score, and timestamp. Show the amber `Review` card for close-match ambiguity.
- **Voiceover Script:**
  > *"Next, we demonstrate continuous watchlist correlation. A stolen white Swift with registration number GJ01AB1234 was added to our representative eGujCop watchlist. As it passes Camera 1, the matching engine computes OCR confusion-weighted edit distances. Rather than brittle exact string matching, our Indian Plate Grammar beam search repairs character confusions. Within 50 milliseconds, a high-priority red alert fires with the exact evidence crop, timestamp, and camera location. Acknowledging an alert requires an operator note, permanently recorded in our audit ledger."*

---

### [1:30 – 2:05] Designated Vehicle Route Tracing & Velocity Gating
- **Screen Action:** Navigate to `http://127.0.0.1:8000/#/trace`. In the search bar, type `GJ01AB1234`. Enter mandatory Purpose: `Stolen Vehicle FIR Investigation` and Case ID: `CR-2026-8819`. Click **Trace Vehicle**. Show the interactive map zoom to Gandhinagar, drawing the sequential route from Stop 1 → Stop 2 → Stop 3 → Stop 4 with blue polyline connectors. Point out the dwell times and verified vehicle speeds (e.g. `48 km/h - Plausible`).
- **Voiceover Script:**
  > *"Now, the critical investigative test: Cross-Camera Route Reconstruction. In compliance with the DPDP Act 2023, every query requires a declared Case ID and legal purpose. We type GJ01AB1234. In under one second, PRAHARI reconstructs its complete chronological journey across the cameras on an interactive map. Every hop is physically validated using Haversine distance and elapsed time. Because the vehicle traveled from Camera 1 to Camera 2 at 48 km/h, it is marked physically plausible. If an impossible transit were detected, the system would immediately flag a possible cloned plate."*

---

### [2:05 – 2:30] Reports, Tamper-Evident Audit Ledger & Conclusion
- **Screen Action:** Navigate to `http://127.0.0.1:8000/#/reports`. Click **Download Plates CSV**. Open the downloaded CSV file briefly showing detected plates with GPS coordinates and timestamps. Click **Verify Audit Log** to show the green checkmark: `Chain verified from Genesis (000...000) to Head Hash (a4f8...b129)`.
- **Voiceover Script:**
  > *"Finally, we navigate to Reports. In one click, we export the official compliance CSV containing every detected plate, camera ID, GPS coordinate, and ISO timestamp. In the Audit Vault, our SHA-256 hash-chained ledger guarantees that no log entries have been altered, ensuring full admissibility under Section 65B of the Indian Evidence Act. PRAHARI delivers a complete, secure, and production-ready platform that moves meaning, not megabytes. Thank you."*

---

## 3. Video Recording Technical Checklist
- **Resolution:** 1080p (1920×1080) at 30 fps or 60 fps
- **Audio:** Clear voiceover with zero background noise
- **Visibility:** Upload to YouTube with visibility set to **Unlisted** (as mandated by Step 5.5)
- **Drive Link:** Upload raw `.mp4` file to Google Drive with permission **"Anyone with the link — Viewer"** (test in logged-out incognito browser).
