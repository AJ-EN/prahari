"""
Seed a representative SAMPLE watchlist (and, with --demo, sample cameras and
synthetic sightings so the trace and alert views have something to show).

    python -m prahari.registry.seed            # watchlist only (idempotent)
    python -m prahari.registry.seed --demo     # + 13 sample cameras + ~120 events

EVERYTHING HERE IS SAMPLE DATA. FIR numbers, police stations and subjects are
fabricated and marked as such; no entry refers to a real case or person.
"""
from __future__ import annotations

import argparse
import random
import time
import uuid

from prahari.common import plate_grammar as g
from prahari.registry import cameras as cam_mod
from prahari.registry import events as ev_mod
from prahari.registry import watchlist as wl_mod
from prahari.registry.db import Store

SAMPLE = "SAMPLE DATA - fabricated for demonstration, not a real record"

# (plate, category, vehicle, police station, note)
WATCHLIST: list[tuple[str, str, str, str, str]] = [
    # stolen vehicles
    ("GJ01AB1234", "stolen_vehicle", "Maruti Suzuki Swift, white", "Navrangpura", "stolen from society parking"),
    ("GJ01KP7781", "stolen_vehicle", "Hyundai Creta, grey", "Satellite", "stolen overnight"),
    ("GJ05JT3309", "stolen_vehicle", "Honda Activa 6G, blue", "Adajan (Surat)", "two-wheeler theft"),
    ("GJ06FH2290", "stolen_vehicle", "Mahindra Bolero, white", "Sayajigunj (Vadodara)", "stolen from highway dhaba"),
    ("GJ18BD6612", "stolen_vehicle", "Toyota Innova Crysta, silver", "Sector-7 (Gandhinagar)", "taxi, stolen"),
    ("GJ27TA0457", "stolen_vehicle", "Bajaj Pulsar 150, black", "Odhav", "two-wheeler theft"),
    ("GJ03HR5521", "stolen_vehicle", "Tata Nexon, red", "Pradyuman Nagar (Rajkot)", "stolen from showroom yard"),
    ("GJ23CM8816", "stolen_vehicle", "Maruti Suzuki Ertiga, white", "Anand Town", "stolen"),
    ("GJ15AK2244", "stolen_vehicle", "Hero Splendor Plus, black", "Valsad City", "two-wheeler theft"),
    ("GJ32E9067", "stolen_vehicle", "Tata Ace, white", "Sanand", "goods carrier stolen"),
    ("MH04GZ3812", "stolen_vehicle", "Kia Seltos, black", "Thane (MH) via inter-state alert", "inter-state"),
    ("RJ14CV6260", "stolen_vehicle", "Mahindra Scorpio, black", "Jaipur (RJ) via inter-state alert", "inter-state"),
    # wanted persons (vehicle associated with the subject)
    ("GJ18BK4521", "wanted_person", "Mahindra Thar, black", "Infocity (Gandhinagar)", "subject W-01 (sample)"),
    ("GJ01RX9090", "wanted_person", "Toyota Fortuner, white", "Vastrapur", "subject W-02 (sample)"),
    ("GJ05CQ1407", "wanted_person", "Hyundai i20, blue", "Umra (Surat)", "subject W-03 (sample)"),
    ("GJ10DN7736", "wanted_person", "Royal Enfield Classic 350, green", "Jamnagar City-A", "subject W-04 (sample)"),
    ("GJ12BY4403", "wanted_person", "Isuzu D-Max, white", "Bhuj A-Division", "subject W-05 (sample)"),
    ("GJ16AX8862", "wanted_person", "Maruti Suzuki Dzire, silver", "Bharuch City", "subject W-06 (sample)"),
    ("MP09WK5150", "wanted_person", "Tata Safari, grey", "Indore (MP) via inter-state alert", "subject W-07 (sample)"),
    ("22BH4471C", "wanted_person", "Skoda Slavia, white", "Crime Branch Ahmedabad", "BH-series; subject W-08 (sample)"),
    # missing persons (last seen travelling in)
    ("GJ01WE3350", "missing_person", "Maruti Suzuki Alto, red", "Maninagar", "missing person M-01 (sample)"),
    ("GJ04EL6188", "missing_person", "TVS Jupiter, white", "Bhavnagar Nilambaug", "missing person M-02 (sample)"),
    ("GJ07CF2927", "missing_person", "Honda City, grey", "Nadiad Town", "missing person M-03 (sample)"),
    ("GJ21AQ5073", "missing_person", "Maruti Suzuki Eeco, white", "Navsari Town", "missing person M-04 (sample)"),
    ("GJ13MN8704", "missing_person", "Bajaj CT100, black", "Surendranagar City", "missing person M-05 (sample)"),
    ("GJ38T4412", "missing_person", "Tata Tiago, blue", "Dwarka", "missing person M-06 (sample)"),
    ("GJ02DP1906", "missing_person", "Hyundai Venue, white", "Mehsana A-Division", "missing person M-07 (sample)"),
    # blacklisted (e.g. repeated e-challan evasion, permit violations)
    ("GJ01DV7003", "blacklisted", "Ashok Leyland Dost, white", "Traffic Branch Ahmedabad", "unpaid e-challans"),
    ("GJ05UU2468", "blacklisted", "Force Traveller, white", "Traffic Branch Surat", "permit violation"),
    ("GJ06PM6604", "blacklisted", "Eicher Pro 2049, yellow", "Traffic Branch Vadodara", "overloading, repeat"),
    ("GJ03BW3071", "blacklisted", "Mahindra Pik-Up, silver", "Traffic Branch Rajkot", "unpaid e-challans"),
    ("GJ24X5519", "blacklisted", "Tata 407, blue", "Patan City", "fake permit"),
    ("GJ09ZH0772", "blacklisted", "Maruti Suzuki Ertiga, white", "Himmatnagar", "illegal taxi operation"),
    # suspect (BOLO)
    ("GJ01HT6129", "suspect", "Maruti Suzuki Brezza, grey", "Crime Branch Ahmedabad", "chain-snatching series (sample)"),
    ("GJ27CE9354", "suspect", "Honda Shine, red", "Ramol", "chain-snatching series (sample)"),
    ("GJ05MR3717", "suspect", "Toyota Glanza, blue", "Varachha (Surat)", "liquor transport tip-off (sample)"),
    ("GJ11BN0588", "suspect", "Mahindra XUV700, black", "Junagadh B-Division", "seen near ATM thefts (sample)"),
    ("GJ20Q7736", "suspect", "Tata Yodha, white", "Dahod Town", "border smuggling tip-off (sample)"),
    ("GJ37KL2210", "suspect", "Kia Sonet, white", "Morbi City", "cheating case (sample)"),
    ("DL3CBJ5087", "suspect", "Hyundai Verna, silver", "Delhi Police via inter-state alert", "inter-state (sample)"),
]


def seed_watchlist(store: Store) -> int:
    for i, (plate, cat, vehicle, ps, note) in enumerate(WATCHLIST, start=1):
        wl_mod.add(store, plate, cat, source="seed:sample", details={
            "fir_no": f"SAMPLE-FIR-{1119100 + i:07d}/2026",
            "police_station": f"{ps} PS (SAMPLE)",
            "vehicle": vehicle,
            "note": note,
            "sample": True,
            "disclaimer": SAMPLE,
        })
    return len(WATCHLIST)


# Around Gandhinagar / Ahmedabad (same geography as sandbox/grid.py), plus one
# far camera in Surat so the demo trace contains a physically impossible hop.
DEMO_CAMERAS = [
    ("DEMO-01", "Police", "Gandhinagar Ch-0 circle", 23.2156, 72.6369),
    ("DEMO-02", "Municipal", "Gandhinagar Sector-11", 23.2237, 72.6500),
    ("DEMO-03", "GSRTC", "Gandhinagar bus depot", 23.1991, 72.6305),
    ("DEMO-04", "Police", "Infocity junction", 23.1650, 72.6100),
    ("DEMO-05", "Panchayat", "Adalaj crossroads", 23.1300, 72.6000),
    ("DEMO-06", "Health", "Civil hospital Sola", 23.0900, 72.5950),
    ("DEMO-07", "Police", "Sola overbridge", 23.0600, 72.5800),
    ("DEMO-08", "Municipal", "Navrangpura", 23.0395, 72.5660),
    ("DEMO-09", "Police", "Ashram Road", 23.0225, 72.5714),
    ("DEMO-10", "GSRTC", "Geeta Mandir bus stand", 23.0120, 72.5870),
    ("DEMO-11", "Police", "Gandhinagar Sector-30", 23.2310, 72.6200),
    ("DEMO-12", "Municipal", "GIFT City gate", 23.2450, 72.6700),
    ("DEMO-13", "Police", "Surat Udhna darwaja", 21.1702, 72.8311),
]


def seed_demo(store: Store, *, now: float | None = None) -> dict:
    rng = random.Random(7)
    now = now or time.time()
    cams = [{"id": cid, "name": f"{name} (SAMPLE)", "department": dept, "lat": lat, "lon": lon,
             "codec": "h264", "width": 1280, "height": 720, "fps": 25.0, "live": True,
             "raw": {"sample": True}} for cid, dept, name, lat, lon in DEMO_CAMERAS]
    cam_mod.upsert(store, cams, source="manual")

    def ev(camera: str, ts: float, raw: str, plate: str | None, conf: float = 0.9) -> dict:
        return {"event_id": uuid.uuid4().hex, "camera_id": camera, "ts": ts, "pts_s": 0.0,
                "raw_text": raw, "plate": plate, "ocr_conf": conf, "det_conf": 0.95,
                "bbox": [100, 200, 180, 50], "valid": g.is_valid(raw), "candidates": []}

    t0 = now - 50 * 60
    events = []
    # Route of the stolen Swift: Gandhinagar -> Ahmedabad, ~35 min, one misread,
    # and one read in Surat 12 minutes later (a cloned plate: impossible hop).
    route = [("DEMO-01", 0, "GJ01AB1234"), ("DEMO-03", 240, "GJ01AB1234"),
             ("DEMO-04", 600, "GJ01AB1Z34"), ("DEMO-05", 900, "GJ01AB1234"),
             ("DEMO-07", 1500, "6J01AB1234"), ("DEMO-08", 1800, "GJ01AB1234"),
             ("DEMO-13", 2520, "GJ01AB1234"), ("DEMO-09", 2100, "GJ01AB1234")]
    for cam, dt, raw in route:
        plate = raw if g.is_valid(raw) else None
        events.append(ev(cam, t0 + dt, raw, plate, 0.72 if plate is None else 0.93))
        events.append(ev(cam, t0 + dt + 1.2, raw, plate, 0.88))       # 2nd frame, same pass
    # Wanted-person vehicle, three sightings in Gandhinagar.
    for cam, dt in (("DEMO-11", 300), ("DEMO-02", 720), ("DEMO-12", 1320)):
        events.append(ev(cam, t0 + dt, "GJ18BK4521", "GJ18BK4521", 0.91))
    # Background traffic: plausible Gujarat plates, not on the watchlist.
    series = "ABCDEFHJKLMNPRSTUVWXYZ"
    for _ in range(90):
        d = rng.choice([1, 1, 1, 18, 18, 27, 2, 6, 5, 23])
        p = (f"GJ{d:02d}{rng.choice(series)}{rng.choice(series)}{rng.randint(1, 9999):04d}")
        cam = rng.choice([c for c in DEMO_CAMERAS if c[0] != "DEMO-06"])[0]
        events.append(ev(cam, t0 + rng.uniform(0, 3000), p, p, round(rng.uniform(0.6, 0.99), 2)))
    events.sort(key=lambda e: e["ts"])
    n_alerts = n_reviews = 0
    for e in events:
        r = ev_mod.ingest(store, e)
        n_alerts += sum(1 for a in r["alerts"] if a["kind"] == "alert")
        n_reviews += sum(1 for a in r["alerts"] if a["kind"] == "review")
    # Health after the events, so the demo shows one offline and one stale camera.
    for cid, *_ in DEMO_CAMERAS:
        cam_mod.update_health(store, cid, status="online", last_seen=now - 30)
    cam_mod.update_health(store, "DEMO-06", status="offline", last_seen=now - 3600)
    cam_mod.update_health(store, "DEMO-10", status="online", last_seen=now - 1800)
    cam_mod.update_health(store, "DEMO-12", capability={
        "anpr_viable": False, "anpr_reason": "plate < 60 px wide at 640x360 (sample)"})
    return {"cameras": len(cams), "events": len(events), "alerts": n_alerts,
            "reviews": n_reviews}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", help="database path (default: $PRAHARI_DB or data/prahari.db)")
    ap.add_argument("--demo", action="store_true",
                    help="also add sample cameras and synthetic sightings")
    args = ap.parse_args()
    store = Store(args.db)
    n = seed_watchlist(store)
    print(f"watchlist: {n} SAMPLE entries upserted into {store.path}")
    if args.demo:
        print("demo:", seed_demo(store))
    print("counts:", store.counts())
    with store.read() as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print(f"database size: {store.size_bytes() / 1024:.1f} KB")


if __name__ == "__main__":
    main()
