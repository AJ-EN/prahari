# PRAHARI

**Gujarat Police Sentinel Hackathon 2026 — Integrated Video Management & Analytics Platform.**

PRAHARI connects to every camera in the Sentinel catalogue, reads number plates, checks them against a
watchlist, raises live alerts, and traces any vehicle's route across the cameras on a map.
You run **one command** and use it in a **web browser**.

> **Declared model:** Hybrid — Model 1 (registry + GIS, mandatory) as the foundation, Model 3 (federation)
> as the spine, Model 2 (direct connect) for the cameras. Why: [`docs/04-architecture-prahari.md`](docs/04-architecture-prahari.md).
> Strategy and analysis: [`docs/README.md`](docs/README.md).

---

## Quick start (about 10 minutes)

### 1. Install Python 3.12
From [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **"Add python.exe to PATH"**.

### 2. Open a terminal in this folder and install

**Mac / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

This installs about 300 MB of packages. The first run also downloads ~11 MB of plate-reading models.

### 3. Try practice mode first
```bash
python run.py demo
```
Open **http://127.0.0.1:8000**. Eight built-in cameras start playing. A stolen white Swift, **GJ01AB1234**,
drives past cameras 1 → 2 → 3 → 4. Within a minute you should see:
- plates being read on the **Wall**,
- red **alerts** for GJ01AB1234 and GJ18BD6612 (both on the sample watchlist),
- on **Trace**, type `GJ01AB1234` → its route on the map, camera by camera, with times.

The practice videos loop every 40 seconds, so the same car passes again each loop: a trace shows stops like
"1, 5, 9" at the same camera. Practice mode uses its own database (`data/demo.db`), so it never mixes with real
data. Stop with **Ctrl+C**.

### 4. Paste in the real camera link
Copy the settings file, then edit the first line:

```bash
cp prahari.env.example prahari.env
```
(Windows: `copy prahari.env.example prahari.env`)

```ini
INGEST_URL=http://<host>/api/ingest
```
`<host>` is on the Sentinel portal's **Resources** page after logging in (the `curl -s http://<host>/api/ingest` line).
If the portal gives you a token, put it on `INGEST_TOKEN=`. Nothing else needs changing.

### 5. Check everything
```bash
python run.py doctor
```
It checks Python, packages, models, disk, database, the catalogue link, and opens two real camera streams.
Every problem comes with a `→` line telling you how to fix it.

### 6. Run it
```bash
python run.py
```
Open the address it prints. All cameras in the catalogue connect automatically.

---

## What you'll see in the browser

| Page | What it's for |
|---|---|
| **Overview** | Cameras live/offline, plate reads, open alerts, system health |
| **Wall** | Every camera's latest picture, with green boxes on plates being read |
| **Map** | Every camera on a map, coloured by health; toggle coverage gaps |
| **Alerts** | Live alerts when a watchlisted vehicle is seen. *Alert* = confident; *Review* = a close match a person should confirm |
| **Trace** | Type a plate → its route on the map, stop by stop, with times and speeds. Impossible jumps are flagged, not hidden |
| **Registry** | All cameras. Add cameras three ways: sync from the catalogue link, import a CSV, or add one by hand. Coverage-gap report |
| **Watchlist** | Add or import vehicles of interest. Ships with a **SAMPLE** list — replace it with your own |
| **Reports** | Download the plates report (CSV); check the audit log is untampered |

Trace and search ask for a **purpose** and **case ID**. Every search is written to a tamper-evident audit log.
This is deliberate (accountability, and the DPDP Act 2023), not a bug.

**API documentation** (a required submission item) is served automatically at **http://127.0.0.1:8000/docs**.

---

## Producing the submission artefacts

| Required item | How |
|---|---|
| Demo on the **government feed** | `python run.py` with the real link; screen-record the Wall, Alerts and a Trace |
| **Output report** of detected plates with timestamps | Reports page → *Download plates CSV* (or `http://127.0.0.1:8000/api/reports/plates.csv`) |
| Demo on **your own feed** | Add your own camera (see below) and run |
| **Registry**: GIS view, onboarding demo, API docs, gap report | Registry + Map pages; `/docs`; Registry → Coverage gaps |
| Designated-vehicle trace on the day | Trace page → type the plate they give you |

### Your own cameras
Any RTSP camera, or a phone running an RTSP camera app, works. Registry → *Add one camera* with its `rtsp://` URL
and a location, or import a CSV.

---

## How many cameras can one laptop handle?

Measured on an Apple M1 laptop with 8 GB of RAM:
- Keeping 48 cameras connected: about half of one CPU core and ~370 MB of RAM (keyframes mode).
- Reading plates: ~15–25 ms per frame, so roughly **40 cameras at one frame per second** on one machine.

If a laptop struggles, set in `prahari.env`: `MAX_CAMERAS=20`, or `TARGET_FPS=1`, or `CAPTURE_MODE=keyframes`.
With an NVIDIA GPU: `pip install onnxruntime-gpu` (instead of `onnxruntime`); it is used automatically.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No camera link yet` | Set `INGEST_URL=` in `prahari.env` (step 4) |
| Doctor: *can't read the catalogue* | Open the URL in a browser **on the same computer**. If that fails too, it's the network or VPN, not PRAHARI |
| Doctor: *could not open the stream* | Port 8554 may be blocked on your network (office and college Wi-Fi often block it). Try another network, e.g. a phone hotspot |
| `Missing Python package` | Activate the venv (step 2), then `pip install -r requirements.txt` |
| `Port 8000 is already in use` | Set `PORT=8001` in `prahari.env` |
| Wall pictures stay blank | That camera isn't delivering video. Check its status dot, then run `python run.py doctor` |
| No plates read on one camera | It may be a corridor or gate, or its plates are too small; the system measures this and shows it in the camera's details |
| macOS prints `objc ... AVFFrameReceiver is implemented in both` | Harmless. Two video libraries both ship a macOS webcam helper we don't use |
| Want a clean start | Stop it, delete the `data/` folder, start again |

Detailed logs: `PRAHARI_LOG=INFO python run.py` (Windows PowerShell: `$env:PRAHARI_LOG="INFO"; python run.py`).

---

## Honest limitations

- Plate reading was tested on **synthetic plates**. Real CCTV (night, glare, dirt, motion blur, hand-painted
  plates) will be harder. Two-line **two-wheeler** plates are often missed today.
- Plates smaller than ~24 pixels tall can't be read reliably. The system detects such cameras and reports them.
- Matching a vehicle across cameras by its appearance, when its plate is unreadable, is designed but not built yet.
- Operator identity is not authenticated yet: this is for a controlled demo, not open deployment.

---

## For developers

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
python bench/bench_plate_matching.py
python -m prahari.node.stability --catalogue URL --seconds 120
```

| Folder | Contents |
|---|---|
| `prahari/node/` | Camera connections: catalogue parsing, RTSP over TCP, PTS timing, reconnect with backoff |
| `prahari/anpr/` | Plate detector and reader (ONNX), two-line handling, de-duplication, camera capability profiling |
| `prahari/common/plate_grammar.py` | Indian plate grammar and confusion-aware watchlist matching |
| `prahari/registry/` | SQLite registry: cameras, events, watchlist, alerts, trace, reports, hash-chained audit log |
| `prahari/api/` | FastAPI app (`/api/...`, docs at `/docs`) |
| `prahari/console/` | The browser console |
| `prahari/runtime.py` | Wires cameras → plate reader → registry → live alerts |
| `sandbox/` | Practice camera grid (`demo_grid.py`, `rtsp_server.py`) |
| `docs/` | Strategy, architecture, requirement scorecard, benchmarks |
| `run.py` | The one command |

Disk use is bounded on purpose: raw video is never stored, evidence crops are capped at 300 MB, and writing stops
below 3 GB free. `scripts/clean.sh` removes everything that can be regenerated.
