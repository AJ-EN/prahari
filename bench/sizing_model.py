"""
PRAHARI infrastructure sizing and cost-benefit model (statewide, ~80,000 cameras).

    .venv/bin/python bench/sizing_model.py            # print tables, write docs/hld/sizing.json
    .venv/bin/python bench/sizing_model.py --quiet    # only write the JSON

Every input lives in the `Assumptions` dataclass below, with a label:

    MEASURED  - taken from a file or benchmark in this repo (path given)
    GIVEN     - stated by the organisers or public record (source given)
    PRICE     - a market price anchor (source listed in docs/hld/sizing.md)
    ASSUMED   - our estimate; basis and confidence stated

Everything else is DERIVED by the functions below, and each function says what formula it uses.
Change an assumption, re-run, and every table and the JSON update. Sensitivity cases are just
`dataclasses.replace(BASE, field=value)`; see SENSITIVITY at the bottom.

Money is in Indian rupees, excluding GST (add 18%). 1 lakh = 1e5, 1 crore = 1e7.
Results are rounded for display; no figure here is precise to better than about +/-30%.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "docs" / "hld" / "sizing.json"

LAKH, CRORE = 1e5, 1e7
DAY_S = 86_400


# ─────────────────────────────────────────────────────────────────────────────────────────────
# ASSUMPTIONS. One place. Each has a label and a basis.
# ─────────────────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Assumptions:
    # ── Estate ──────────────────────────────────────────────────────────────────────────────
    total_cameras: int = 80_000             # GIVEN: organisers' statewide target
    viswas_cameras: int = 17_500            # GIVEN: VISWAS ph-I ~7,000 + ph-II ~10,500 (public record)
    netram_centres: int = 34                # GIVEN: one Netram district command centre per district HQ
    districts: int = 33                     # GIVEN
    private_optin_cameras: int = 10_000     # ASSUMED (low): phase 3, registry + on-demand clip only, no
                                            #   continuous analytics (consent envelope, see doc 04 §5)
    largest_district_share: float = 0.15    # ASSUMED (medium): Ahmedabad or Surat carries ~15% of cameras
    largest_netram_viswas_share: float = 0.30   # GIVEN-derived: ~10,500 VISWAS ph-II cams went to Surat and
                                            #   Vadodara, so the biggest Netram carries ~30% of VISWAS

    # ── Camera mix. CCAP measures this per camera, so these shares are discovered, not guessed ──
    viswas_anpr_share: float = 0.60         # ASSUMED (medium): VISWAS is sited at ~1,200 junctions and
                                            #   inter-state entry/exit points; some cams are overview/PTZ
    dept_anpr_share: float = 0.20           # ASSUMED (low): depot/hospital/office gates and frontage roads;
                                            #   most departmental cams face corridors, counters, yards
    anpr_fps: float = 1.0                   # design choice: 1 analysed frame/s at junctions (vehicles slow)
    high_speed_share: float = 0.10          # ASSUMED (medium): share of ANPR cams on highways/entry points
    high_speed_fps: float = 4.0             # DERIVED need: 60 km/h crosses a ~15 m view in ~0.9 s, so 1 fps
                                            #   can miss it; 4 fps gives >=3 chances
    light_fps: float = 0.2                  # design choice: person/crowd/intrusion, 1 frame per 5 s
    anpr_keyframe_share: float = 0.30       # ASSUMED (low): ANPR cams whose GOP <= 1 s, so keyframe-only
                                            #   decode gives 1 fps; the rest need full decode (CCAP reads GOP)

    # ── Traffic ─────────────────────────────────────────────────────────────────────────────
    viswas_vehicles_per_cam_day: float = 12_000   # ASSUMED (medium): one approach of an urban junction;
                                                   #   ~500/h daytime avg, lower at night
    dept_vehicles_per_cam_day: float = 2_000      # ASSUMED (low): gates and frontage roads
    read_yield: float = 0.80                # ASSUMED (medium): deduplicated plate events per vehicle pass
                                            #   (rear-only two-wheeler plates, occlusion, night)
    peak_hour_fraction: float = 0.09        # ASSUMED (high): traffic-engineering K-factor, 8-10% of daily
                                            #   traffic in the peak hour -> statewide peak/avg = 0.09*24
    site_burst_factor: float = 3.0          # ASSUMED (medium): a single site's link sees bigger bursts than
                                            #   the statewide aggregate
    light_events_per_cam_day: float = 50    # ASSUMED (low): intrusion/crowd alerts + periodic counts
    light_crop_share: float = 0.10          # ASSUMED: share of light events that carry an image

    # ── Payloads ────────────────────────────────────────────────────────────────────────────
    event_bytes: float = 550                # MEASURED: mean JSON size of a stored plate event incl. 5 ranked
                                            #   candidates, data/demo.db (281 rows) = 547 B
    crop_bytes: float = 15_000              # ASSUMED (medium): plate crop + vehicle context. MEASURED synthetic
                                            #   plate crops average 5.2 KB (data/evidence, 2,196 files,
                                            #   360x141); real footage is noisier and we add a vehicle crop
    crop_share_of_anpr_events: float = 1.0  # bandwidth-ladder tier 3/4: every plate event ships its crop
    protocol_overhead: float = 1.15         # ASSUMED (medium): TLS + HTTP/2 framing on batched posts
    telemetry_bps_per_cam: float = 100      # ASSUMED (medium): health heartbeat + metrics, per camera
    clips_per_day: float = 2_000            # ASSUMED (low): on-demand clip pulls statewide (~60/district/day)
    clip_seconds: float = 30                # design: one clip = 30 s, pulled by case ID
    clip_mbps: float = 4.0                  # ASSUMED: main-stream bitrate of the pulled clip

    # ── Centralised video (Model 4) ─────────────────────────────────────────────────────────
    video_mbps: float = 2.0                 # ASSUMED (medium): 1080p H.264, conservative (doc 01 §3.1)
    video_mbps_high: float = 4.0            # ASSUMED: realistic 1080p25 quality
    model4_retention_days: float = 30       # ASSUMED: the retention a central VMS is usually specified with
    model4_streams_per_gpu: float = 40      # ASSUMED (doc 01): continuous detect+track at video rate
    model4_link_headroom: float = 1.25      # ASSUMED: provisioned capacity / sustained video
    model4_recorder_mbps: float = 600       # ASSUMED (medium): sustained write per VMS recording server
    model4_sites: int = 4_000               # ASSUMED (low): distinct sites needing a video-grade WAN link

    # ── Measured on the dev machine (Apple M1, 8 GB). Synthetic streams, synthetic plates. ──
    anpr_ms_plate_p90: float = 21.0         # MEASURED: prahari.anpr.bench, 960-wide frame, 1 plate, p90
                                            #   (docs/hld/bench-anpr-m1.json). 1280-wide: 40.8 ms
    det_ms_empty_p90: float = 3.8           # MEASURED: same bench, 960-wide, no plate (detector only)
    sw_decode_core_pct_per_mpix_s: float = 0.39  # MEASURED: full decode, 12 cams, 111.7 Mpix/s -> 43.8%
                                            #   of one core (data/stability-20260924-225251-full5-22642.json)
    keyframe_core_pct_per_cam: float = 0.52 # MEASURED: keyframes-only, 12 cams -> 6.2% of one core
                                            #   (data/stability-20260924-224549.json)
    safety_factor: float = 2.0              # ASSUMED: real footage (more plates/frame, 1080p, night),
                                            #   production models bigger than the demo ones
    target_util: float = 0.60               # ASSUMED: plan nodes at 60% so a node survives bursts/rebuilds

    # ── Departmental sites (where the NVRs are). Node count is site-bound, not throughput-bound ──
    dept_site_mix: tuple = ((0.50, 6), (0.35, 20), (0.15, 60))   # ASSUMED (low): (share of sites,
                                            #   cameras per site): offices/panchayats, depots/PHCs,
                                            #   hospitals/campuses. Registry replaces this with real data
    reuse_existing_pc_share: float = 0.0    # ASSUMED: 0 = buy every node (conservative)
    spare_node_share: float = 0.05          # ASSUMED: cold spares held per district
    sites_without_uplink_share: float = 0.30  # ASSUMED (low): sites that need a new 4G/broadband link

    # ── Storage and retention ───────────────────────────────────────────────────────────────
    event_row_bytes_hot: float = 1_050      # MEASURED upper bound: data/demo.db 294,912 B / 281 rows incl.
                                            #   4 indexes and page overhead
    warm_compression: float = 5.0           # ASSUMED (medium): columnar/time-series compression of old rows
    event_hot_days: int = 90                # policy: searchable at full speed
    event_total_days: int = 365             # policy: all plate reads kept 1 year (UK NAS keeps 1 yr)
    case_event_share: float = 0.001         # ASSUMED: events tied to a case, kept cold for 7 years
    cold_years: int = 7                     # policy: case evidence
    crop_days: int = 90                     # policy (doc 04 §5): crops 90 days unless case-linked
    clip_days: int = 30                     # policy (doc 04 §5)
    clip_case_share: float = 0.30           # ASSUMED: clips that become case evidence (cold 7 y)
    db_copies: int = 3                      # design: primary + sync standby (DC) + async replica (DR);
                                            #   the standby also serves search/trace reads
    object_overhead: float = 1.5            # design: erasure coding 4+2
    object_sites: int = 2                   # design: DC + DR both hold crops/clips
    edge_queue_gb: float = 100              # design: disk store-and-forward queue per node

    # ── Central software sizing ─────────────────────────────────────────────────────────────
    gateway_events_per_s_per_pod: float = 5_000   # ASSUMED (medium): mTLS + schema validation, 8 vCPU pod
    screen_ms_per_event: float = 0.5        # ASSUMED (medium): confusion-aware watchlist screen, CPU
    searches_per_day: float = 10_000        # ASSUMED: investigator trace/search queries statewide
    vcpu_per_host: int = 128                # 2-socket host
    metric_series_per_node: int = 200       # ASSUMED
    metric_series_per_cam: int = 10         # ASSUMED

    # ── Prices (ex-GST). Sources in docs/hld/sizing.md §Sources ─────────────────────────────
    price_l4_gpu: float = 2.5 * LAKH        # PRICE: Indian listings Rs 1-3 L; AceCloud cites Rs 2.4 L
    price_server_base: float = 6.5 * LAKH   # PRICE: Dell R760, 1x Xeon Gold, 64 GB, Rs 6.51 L (IndiaMART)
    price_central_host: float = 9 * LAKH    # ASSUMED from R760 anchor: 2-socket, 512 GB RAM
    price_regional_server: float = 5 * LAKH # ASSUMED: 1U, 32 cores, 128 GB, 4x NVMe
    price_nvme_per_tb: float = 12_000       # ASSUMED (medium): enterprise NVMe, 2026 prices
    price_hdd_per_raw_tb: float = 4_500     # PRICE: Seagate Exos 20 TB ~Rs 90k retail in India
    price_object_host: float = 5 * LAKH     # ASSUMED: 12-bay storage server without drives (240 TB raw)
    price_dense_chassis_per_raw_tb: float = 1_250   # ASSUMED: 60-bay JBOD + head server ~Rs 15 L per
                                            #   1.2 PB raw, used for Model 4 video storage
    model4_storage_overhead: float = 1.25   # ASSUMED: RAID-6/EC overhead on video storage, one copy
    price_site_install: float = 15_000      # ASSUMED: engineer visit, mounting, onboarding, per node
    price_central_network: float = 1.5 * CRORE  # ASSUMED: firewalls, 25G switching, per DC site
    price_model4_core_network: float = 8 * CRORE    # ASSUMED: 100G spine for 160-320 Gbps ingest
    price_model4_site_link_install: float = 30_000  # ASSUMED: CPE + fibre drop per site
    price_vms_license_per_ch: float = 5_000     # ASSUMED (low): enterprise VMS device licence, Rs 2-10k
    price_anpr_license_per_ch: float = 30_000   # ASSUMED (low): commercial ANPR channel licence, Rs 15-60k
    price_light_ai_license_per_ch: float = 5_000  # ASSUMED (low): basic analytics channel licence
    license_support_rate: float = 0.20      # ASSUMED: annual software support on licences
    power_per_kwh: float = 9.0              # PRICE: Gujarat HT effective Rs 7.5-8.5/kWh; LT commercial higher
    dc_per_kw_month: float = 15_000         # PRICE: Indian colocation Rs 8k-25k per kW-month all-in;
                                            #   cross-check: Rs 9/kWh x 730 h x PUE 1.6 = Rs 10.5k power only
    bw_per_mbps_month: float = 250          # PRICE: ILL 100 Mbps Rs 25-38k/mo; 1 Gbps Rs 1.5 L/mo
    ill_1g_month: float = 1.5 * LAKH        # PRICE: 1 Gbps ILL per month
    ill_100m_month: float = 30_000          # PRICE: 100 Mbps ILL per month
    site_link_month: float = 1_500          # ASSUMED: 4G/5G or broadband for a site with no usable uplink
    amc_rate: float = 0.08                  # ASSUMED (medium): hardware AMC per year after 1-yr warranty
    years: int = 5
    # Staff (loaded cost per year)
    platform_team_fte: int = 15             # ASSUMED: PRAHARI engineering + L3 support
    platform_fte_cost: float = 25 * LAKH
    ops_fte: int = 12                       # ASSUMED: 24x7 NOC/SOC, both models
    ops_fte_cost: float = 15 * LAKH
    field_fte_per_district: int = 1         # ASSUMED: field engineer per district
    field_fte_cost: float = 8 * LAKH
    model4_dc_ops_extra_fte: int = 12       # ASSUMED: storage/GPU/VMS admins a central VMS adds


# Edge node classes. perf = ANPR throughput relative to ONE worker on the measured M1.
# hw_decode = concurrent 1080p25 full-decode streams the hardware decoder sustains.
NODE_CLASSES = {
    "EDGE-S": dict(desc="Mini-PC, Intel Core Ultra (iGPU+NPU, QuickSync), 16 GB, 512 GB SSD",
                   perf=1.5, hw_decode=24, price=75_000, watts=35,
                   basis="ASSUMED (low-medium): 2 workers on iGPU+NPU ~ 1.5x one M1 worker; "
                         "QuickSync ~24x 1080p25; price Rs 55k-1 L"),
    "EDGE-M": dict(desc="Jetson Orin NX 16 GB, fanless industrial box, 512 GB NVMe",
                   perf=2.0, hw_decode=18, price=110_000, watts=25,
                   basis="ASSUMED perf (TensorRT INT8); NVDEC 18x 1080p30 H.265 (NVIDIA spec); "
                         "module Rs 49k (IndiaMART) + carrier/enclosure ~Rs 60k"),
    "EDGE-L": dict(desc="2U server, 2x NVIDIA L4, 256 GB, at a Netram centre",
                   perf=20.0, hw_decode=256, price=6.5 * LAKH + 2 * 2.5 * LAKH, watts=650,
                   basis="ASSUMED perf ~10x M1 per L4 with batched TensorRT and OCR on GPU; "
                         "4 NVDEC per L4 ~ 128x 1080p25 each; price = R760 + 2x L4"),
}
PROD_MPIX_S = 1920 * 1080 * 25 / 1e6        # a 1080p25 production camera, Mpix/s


# ─────────────────────────────────────────────────────────────────────────────────────────────
# DERIVED quantities
# ─────────────────────────────────────────────────────────────────────────────────────────────
def camera_mix(a: Assumptions, total: int, viswas: int) -> dict:
    """Split an estate into VISWAS/departmental x ANPR/light cameras."""
    dept = total - viswas
    v_anpr = viswas * a.viswas_anpr_share
    d_anpr = dept * a.dept_anpr_share
    return dict(total=total, viswas=viswas, dept=dept,
                viswas_anpr=v_anpr, viswas_light=viswas - v_anpr,
                dept_anpr=d_anpr, dept_light=dept - d_anpr,
                anpr=v_anpr + d_anpr, light=total - v_anpr - d_anpr,
                anpr_share=(v_anpr + d_anpr) / total if total else 0.0)


def effective_anpr_fps(a: Assumptions) -> float:
    """Mean analysed fps over ANPR cameras: junctions at anpr_fps, highway points at high_speed_fps."""
    return (1 - a.high_speed_share) * a.anpr_fps + a.high_speed_share * a.high_speed_fps


def bandwidth(a: Assumptions, mix: dict) -> dict:
    """Upstream bytes/day from all nodes; statewide and per-district averages and peaks.

    events/day   = cams x vehicles/day x read_yield           (ANPR)  + cams x light events (light)
    bytes/day    = events x event_bytes + crop events x crop_bytes, x protocol overhead
    peak (state) = avg x peak_hour_fraction x 24
    """
    ev_v = mix["viswas_anpr"] * a.viswas_vehicles_per_cam_day * a.read_yield
    ev_d = mix["dept_anpr"] * a.dept_vehicles_per_cam_day * a.read_yield
    ev_anpr = ev_v + ev_d
    ev_light = mix["light"] * a.light_events_per_cam_day
    ev_total = ev_anpr + ev_light
    b_events = ev_total * a.event_bytes
    b_crops = (ev_anpr * a.crop_share_of_anpr_events + ev_light * a.light_crop_share) * a.crop_bytes
    b_telemetry = mix["total"] * a.telemetry_bps_per_cam / 8 * DAY_S
    b_clips = a.clips_per_day * a.clip_seconds * a.clip_mbps * 1e6 / 8
    b_total = (b_events + b_crops + b_telemetry) * a.protocol_overhead + b_clips
    avg_mbps = b_total * 8 / DAY_S / 1e6
    peak_factor = a.peak_hour_fraction * 24
    # Only the traffic-driven part peaks; telemetry and clips are roughly flat.
    traffic_mbps = (b_events + b_crops) * a.protocol_overhead * 8 / DAY_S / 1e6
    peak_mbps = avg_mbps + traffic_mbps * (peak_factor - 1)
    return dict(
        events_per_day=ev_total, anpr_events_per_day=ev_anpr, light_events_per_day=ev_light,
        events_per_s_avg=ev_total / DAY_S, events_per_s_peak=ev_total / DAY_S * peak_factor,
        gb_per_day=dict(events=b_events / 1e9, crops=b_crops / 1e9, telemetry=b_telemetry / 1e9,
                        clips=b_clips / 1e9, total=b_total / 1e9),
        mbps_events_only=b_events * a.protocol_overhead * 8 / DAY_S / 1e6,
        mbps_avg=avg_mbps, mbps_peak=peak_mbps, peak_factor=peak_factor,
        district_avg_mbps=avg_mbps / a.districts,
        district_avg_peak_mbps=peak_mbps / a.districts,
        largest_district_peak_mbps=peak_mbps * a.largest_district_share,
    )


def site_uplink(a: Assumptions) -> list[dict]:
    """Per departmental site: the uplink it needs at each tier of the bandwidth ladder."""
    rows = []
    for share, cams in a.dept_site_mix:
        n_anpr = cams * a.dept_anpr_share
        ev_anpr = n_anpr * a.dept_vehicles_per_cam_day * a.read_yield
        ev_light = (cams - n_anpr) * a.light_events_per_cam_day
        b_ev = (ev_anpr + ev_light) * a.event_bytes * a.protocol_overhead
        b_crop = (ev_anpr + ev_light * a.light_crop_share) * a.crop_bytes * a.protocol_overhead
        b_tel = cams * a.telemetry_bps_per_cam / 8 * DAY_S
        peak = a.peak_hour_fraction * 24 * a.site_burst_factor

        def kbps(b):
            return b * 8 / DAY_S / 1e3
        tier3 = kbps(b_ev + b_crop + b_tel)
        tier1 = kbps(b_ev * 0.4 + b_tel * 0.2)   # zstd-batched events, sparse telemetry
        rows.append(dict(cams=cams, share_of_sites=share,
                         tier3_avg_kbps=tier3, tier3_peak_kbps=tier3 * peak,
                         tier1_avg_kbps=tier1,
                         offline_days_in_queue=a.edge_queue_gb * 1e9 / (b_ev + b_crop + b_tel),
                         clip_pull_minutes_at_512k=a.clip_seconds * a.clip_mbps / 0.512 / 60))
    return rows


def netram_peak_mbps(a: Assumptions, mix: dict) -> float:
    """Peak upstream of the busiest Netram (VISWAS events + crops only)."""
    ev = mix["viswas_anpr"] * a.viswas_vehicles_per_cam_day * a.read_yield * a.largest_netram_viswas_share
    b = ev * (a.event_bytes + a.crop_bytes * a.crop_share_of_anpr_events) * a.protocol_overhead
    return b * 8 / DAY_S / 1e6 * a.peak_hour_fraction * 24


def model4_bandwidth(a: Assumptions, total: int) -> dict:
    """Centralising pixels: every camera streams continuously to the state DC."""
    gbps = total * a.video_mbps / 1e3
    gbps_hi = total * a.video_mbps_high / 1e3
    tb_day = total * a.video_mbps * 1e6 / 8 * DAY_S / 1e12
    return dict(gbps=gbps, gbps_high=gbps_hi, tb_per_day=tb_day,
                pb_retained=tb_day * a.model4_retention_days / 1e3)


def node_streams(a: Assumptions, cls: dict) -> dict:
    """Streams one node sustains, from our MEASURED per-frame time.

    inference: streams = 1000 ms x util x perf / (ms_per_frame x safety x fps)
    decode:    ANPR streams needing full decode <= hw_decode x util
    """
    budget = 1000 * a.target_util * cls["perf"]
    anpr_inf = budget / (a.anpr_ms_plate_p90 * a.safety_factor * a.anpr_fps)
    anpr_inf_mix = budget / (a.anpr_ms_plate_p90 * a.safety_factor * effective_anpr_fps(a))
    anpr_dec = cls["hw_decode"] * a.target_util / max(1e-9, 1 - a.anpr_keyframe_share)
    light_inf = budget / (a.det_ms_empty_p90 * a.safety_factor * a.light_fps)
    return dict(anpr_1fps=math.floor(min(anpr_inf, anpr_dec)),
                anpr_mixed_fps=math.floor(min(anpr_inf_mix, anpr_dec)),
                anpr_bound="decode" if anpr_dec < anpr_inf_mix else "inference",
                light_only=math.floor(light_inf))


def m1_reference(a: Assumptions) -> dict:
    """What the measured M1 itself would carry under production safety margins."""
    anpr = 1000 * a.target_util / (a.anpr_ms_plate_p90 * a.safety_factor * a.anpr_fps)
    naive = 1000 / a.anpr_ms_plate_p90
    sw_dec_per_1080p = a.sw_decode_core_pct_per_mpix_s * PROD_MPIX_S
    return dict(naive_streams_1fps=math.floor(naive), planned_streams_1fps=math.floor(anpr),
                sw_decode_pct_core_per_1080p25=sw_dec_per_1080p,
                sw_decode_streams_8_cores_at_util=math.floor(800 * a.target_util / sw_dec_per_1080p),
                keyframe_streams_per_core_at_util=math.floor(100 * a.target_util / a.keyframe_core_pct_per_cam))


def site_load_nodes(a: Assumptions, cams: float, anpr_share: float, cls: dict) -> int:
    """Nodes needed at one site (>= 1): max of inference load and hardware-decode load."""
    n_anpr = cams * anpr_share
    n_light = cams - n_anpr
    inf_ms = (n_anpr * effective_anpr_fps(a) * a.anpr_ms_plate_p90
              + n_light * a.light_fps * a.det_ms_empty_p90) * a.safety_factor / cls["perf"]
    full_dec = n_anpr * (1 - a.anpr_keyframe_share)
    return max(1, math.ceil(max(inf_ms / (1000 * a.target_util),
                                full_dec / (cls["hw_decode"] * a.target_util))))


def edge(a: Assumptions, mix: dict) -> dict:
    """Edge fleet: EDGE-L at Netram for VISWAS (video already terminates there); EDGE-S per
    departmental NVR site. Departmental node count is bound by the number of sites."""
    L, S = NODE_CLASSES["EDGE-L"], NODE_CLASSES["EDGE-S"]
    # VISWAS at Netram: aggregate load, then one N+1 spare per Netram that has any cameras.
    inf_ms = (mix["viswas_anpr"] * effective_anpr_fps(a) * a.anpr_ms_plate_p90
              + mix["viswas_light"] * a.light_fps * a.det_ms_empty_p90) * a.safety_factor / L["perf"]
    full_dec = mix["viswas_anpr"] * (1 - a.anpr_keyframe_share)
    l_work = math.ceil(max(inf_ms / (1000 * a.target_util), full_dec / (L["hw_decode"] * a.target_util)))
    l_spare = a.netram_centres if mix["viswas"] else 0
    l_nodes = l_work + l_spare

    mean_cams = sum(s * c for s, c in a.dept_site_mix)
    sites = mix["dept"] / mean_cams if mix["dept"] else 0
    s_nodes_exact = sum(sites * s * site_load_nodes(a, c, a.dept_anpr_share, S) for s, c in a.dept_site_mix)
    s_bought = math.ceil(s_nodes_exact * (1 - a.reuse_existing_pc_share))
    s_spares = math.ceil(s_nodes_exact * a.spare_node_share)
    s_total = s_bought + s_spares
    return dict(edge_l_working=l_work, edge_l_spares=l_spare, edge_l_total=l_nodes,
                dept_sites=round(sites), dept_mean_cams_per_site=mean_cams,
                edge_s_nodes=round(s_nodes_exact), edge_s_bought=s_bought, edge_s_spares=s_spares,
                edge_s_total=s_total,
                capex=l_nodes * L["price"] + s_total * S["price"]
                      + (s_bought + l_work) * a.price_site_install,
                kw=(l_nodes * L["watts"] + (s_bought + math.ceil(s_nodes_exact * a.reuse_existing_pc_share))
                    * S["watts"]) / 1e3)


def storage(a: Assumptions, bw: dict) -> dict:
    """Central storage by tier (TB, one logical copy, then with copies)."""
    ev_day = bw["events_per_day"]
    ev_hot = ev_day * a.event_hot_days * a.event_row_bytes_hot / 1e12
    ev_warm = ev_day * (a.event_total_days - a.event_hot_days) * a.event_row_bytes_hot / a.warm_compression / 1e12
    ev_cold = ev_day * a.case_event_share * 365 * a.cold_years * a.event_row_bytes_hot / a.warm_compression / 1e12
    crop_day = bw["gb_per_day"]["crops"] / 1e3
    crops_hot = crop_day * a.crop_days
    crops_cold = crop_day * a.case_event_share * 365 * a.cold_years
    clip_day = bw["gb_per_day"]["clips"] / 1e3
    clips_hot = clip_day * a.clip_days
    clips_cold = clip_day * a.clip_case_share * 365 * a.cold_years
    bus = bw["gb_per_day"]["events"] * 7 / 1e3 * 3          # 7-day replay, 3 replicas
    db_tb = (ev_hot + ev_warm) * a.db_copies
    obj_usable = crops_hot + crops_cold + clips_hot + clips_cold + ev_cold
    obj_raw = obj_usable * a.object_overhead * a.object_sites
    return dict(events_hot_tb=ev_hot, events_warm_tb=ev_warm, events_cold_tb=ev_cold,
                crops_hot_tb=crops_hot, crops_cold_tb=crops_cold,
                clips_hot_tb=clips_hot, clips_cold_tb=clips_cold, bus_tb=bus,
                db_nvme_tb_all_copies=db_tb, object_usable_tb=obj_usable, object_raw_tb=obj_raw,
                total_logical_tb=ev_hot + ev_warm + ev_cold + obj_usable,
                total_raw_tb=db_tb + obj_raw + bus)


def central(a: Assumptions, bw: dict, st: dict, mix: dict, n_nodes: int) -> dict:
    """Central (SCRB/state DC) + DR + 34 regional (Netram) tiers: pods -> vCPU -> hosts -> Rs."""
    peak = bw["events_per_s_peak"]
    pods = {
        "ingest-gateway (8 vCPU)": (max(3, math.ceil(peak / a.gateway_events_per_s_per_pod * 2)), 8),
        "event bus brokers (8 vCPU)": (3, 8),
        "screen/match workers (8 vCPU)": (max(3, math.ceil(peak * a.screen_ms_per_event / 1000
                                                           / a.target_util / 8) + 1), 8),
        "API + console + search (16 vCPU)": (3, 16),
        "registry/GIS/auth/audit (8 vCPU)": (3, 8),
        "monitoring: metrics+logs (16 vCPU)": (max(3, math.ceil((n_nodes * a.metric_series_per_node
                                                                 + mix["total"] * a.metric_series_per_cam)
                                                                / 1_000_000) + 2), 16),
        "k8s control plane (4 vCPU)": (3, 4),
    }
    vcpu = sum(n * c for n, c in pods.values())
    app_hosts = max(3, math.ceil(vcpu / (a.vcpu_per_host * a.target_util)) + 1)   # +1 for N+1
    db_hosts = 2                         # primary + sync standby (standby serves search/trace reads)
    obj_hosts_per_site = max(6, math.ceil(st["object_raw_tb"] / a.object_sites / 240))  # 12x20 TB
    dc_hosts = app_hosts + db_hosts + obj_hosts_per_site
    dr_hosts = math.ceil(app_hosts * 0.5) + 1 + obj_hosts_per_site   # warm standby: half compute
    obj_site = obj_hosts_per_site * a.price_object_host \
        + st["object_raw_tb"] / a.object_sites * a.price_hdd_per_raw_tb
    db_nvme_per_copy = st["db_nvme_tb_all_copies"] / a.db_copies * a.price_nvme_per_tb
    capex_dc = (app_hosts + db_hosts) * a.price_central_host + 2 * db_nvme_per_copy \
        + obj_site + a.price_central_network
    capex_dr = (math.ceil(app_hosts * 0.5) + 1) * a.price_central_host + db_nvme_per_copy \
        + obj_site + a.price_central_network
    regional_servers = 2 * a.netram_centres
    capex_regional = regional_servers * a.price_regional_server
    kw = (dc_hosts + dr_hosts) * 0.55     # ASSUMED ~550 W per loaded host
    return dict(pods={k: v[0] for k, v in pods.items()}, vcpu=vcpu, app_hosts=app_hosts,
                db_hosts=db_hosts, object_hosts_per_site=obj_hosts_per_site,
                dc_hosts=dc_hosts, dr_hosts=dr_hosts, regional_servers=regional_servers,
                search_qps_peak=a.searches_per_day / DAY_S * a.peak_hour_fraction * 24 * 2,
                capex_dc=capex_dc, capex_dr=capex_dr, capex_regional=capex_regional, kw_it=kw)


def staff_cost(a: Assumptions, model4: bool) -> float:
    c = a.ops_fte * a.ops_fte_cost + a.field_fte_per_district * a.districts * a.field_fte_cost
    c += a.platform_team_fte * a.platform_fte_cost if not model4 else 0
    c += a.model4_dc_ops_extra_fte * a.ops_fte_cost if model4 else 0
    return c


def prahari_costs(a: Assumptions, total: int, viswas: int) -> dict:
    mix = camera_mix(a, total, viswas)
    bw = bandwidth(a, mix)
    ed = edge(a, mix)
    st = storage(a, bw)
    ce = central(a, bw, st, mix, ed["edge_l_total"] + ed["edge_s_total"])
    hw_capex = ed["capex"] + ce["capex_dc"] + ce["capex_dr"] + ce["capex_regional"]
    sites = ed["dept_sites"]
    opex = {
        "edge power": ed["kw"] * 8_760 * a.power_per_kwh,
        "regional power": ce["regional_servers"] * 0.5 * 8_760 * a.power_per_kwh,
        "DC + DR facility (per kW IT)": ce["kw_it"] * a.dc_per_kw_month * 12,
        "central uplinks (2x1G at DC and DR)": 4 * a.ill_1g_month * 12 if total else 0,
        "Netram backup links (100M)": a.netram_centres * a.ill_100m_month * 12,
        "site links where none exists": sites * a.sites_without_uplink_share * a.site_link_month * 12,
        "hardware AMC": hw_capex * a.amc_rate,
        "staff (platform, NOC/SOC, field)": staff_cost(a, model4=False),
    }
    opex_y = sum(opex.values())
    # AMC starts year 2 (1-year warranty): 5-year opex = 5 x opex - 1 x AMC
    opex_5y = a.years * opex_y - opex["hardware AMC"]
    return dict(mix=mix, bandwidth=bw, edge=ed, storage=st, central=ce,
                capex=dict(edge=ed["capex"], central_dc=ce["capex_dc"], dr=ce["capex_dr"],
                           regional=ce["capex_regional"], total=hw_capex),
                opex_per_year=opex, opex_per_year_total=opex_y,
                tco_5y=hw_capex + opex_5y)


def model4_costs(a: Assumptions, total: int, viswas: int, streams_per_gpu: float | None = None,
                 licences: bool = True) -> dict:
    """Central VMS + AI (Model 4): all video to the state DC, recorded, analysed there.
    Given the same DC facility, power, AMC and staff prices as PRAHARI.
    licences=True : commercial VMS + analytics licences (+ annual support), no in-house platform team.
    licences=False: infrastructure only; the same in-house platform team as PRAHARI instead."""
    mix = camera_mix(a, total, viswas)
    m4 = model4_bandwidth(a, total)
    spg = streams_per_gpu or a.model4_streams_per_gpu
    gpus = math.ceil(total / spg)
    gpu_servers = math.ceil(gpus / 4)
    recorders = math.ceil(total * a.video_mbps / (a.model4_recorder_mbps * a.target_util))
    storage_tb = m4["pb_retained"] * 1e3
    raw_tb = storage_tb * a.model4_storage_overhead
    drives = raw_tb / 20                              # 20 TB drives
    kw_it = gpu_servers * 0.75 + recorders * 0.45 + drives * 0.012 + 20   # + core network, mgmt
    hw = {
        "GPU servers (4x L4)": gpu_servers * (a.price_server_base + 4 * a.price_l4_gpu),
        "recording servers": recorders * a.price_server_base,
        "video storage": raw_tb * (a.price_hdd_per_raw_tb + a.price_dense_chassis_per_raw_tb),
        "core network": a.price_model4_core_network,
        "site WAN installs": a.model4_sites * a.price_model4_site_link_install,
        "metadata/DR/management (~as PRAHARI central)": 6 * CRORE,
    }
    lic = {
        "VMS licences": total * a.price_vms_license_per_ch,
        "ANPR licences": mix["anpr"] * a.price_anpr_license_per_ch,
        "basic analytics licences": mix["light"] * a.price_light_ai_license_per_ch,
    } if licences else {}
    hw_capex, lic_capex = sum(hw.values()), sum(lic.values())
    opex = {
        "WAN bandwidth (video)": m4["gbps"] * 1e3 * a.model4_link_headroom * a.bw_per_mbps_month * 12,
        "DC facility (per kW IT)": kw_it * a.dc_per_kw_month * 12,
        "hardware AMC": hw_capex * a.amc_rate,
        "licence support": lic_capex * a.license_support_rate,
        "staff (NOC/SOC, DC ops, field)": staff_cost(a, model4=True),
        "in-house platform team": 0 if licences else a.platform_team_fte * a.platform_fte_cost,
    }
    opex_y = sum(opex.values())
    opex_5y = a.years * opex_y - opex["hardware AMC"] - opex["licence support"]
    return dict(licences=licences, gbps=m4["gbps"], storage_pb=m4["pb_retained"], gpus=gpus, gpu_servers=gpu_servers,
                recorders=recorders, drives=math.ceil(drives), kw_it=kw_it,
                capex_hw=hw, capex_licences=lic,
                capex=dict(hardware=hw_capex, licences=lic_capex, total=hw_capex + lic_capex),
                opex_per_year=opex, opex_per_year_total=opex_y,
                tco_5y=hw_capex + lic_capex + opex_5y)


def model4_steelman_gpus(a: Assumptions, total: int, viswas: int) -> int:
    """Model 4 running the SAME 1-fps analytics as PRAHARI on L4s (decode-bound, like EDGE-L)."""
    mix = camera_mix(a, total, viswas)
    L = NODE_CLASSES["EDGE-L"]
    inf_ms = (mix["anpr"] * effective_anpr_fps(a) * a.anpr_ms_plate_p90
              + mix["light"] * a.light_fps * a.det_ms_empty_p90) * a.safety_factor / L["perf"]
    full_dec = mix["anpr"] * (1 - a.anpr_keyframe_share)
    servers = math.ceil(max(inf_ms / (1000 * a.target_util), full_dec / (L["hw_decode"] * a.target_util)))
    return servers * 2


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Phases, sensitivity, output
# ─────────────────────────────────────────────────────────────────────────────────────────────
PHASES = [  # (name, months, total govt cameras, of which VISWAS, private registry-only)
    ("Phase 1: VISWAS + 34 Netram", "0-6", 17_500, 17_500, 0),
    ("Phase 2: + departments", "6-18", 50_000, 17_500, 0),
    ("Phase 3: 80k + private opt-in", "18-36", 80_000, 17_500, 10_000),
]


def phases(a: Assumptions) -> list[dict]:
    rows, prev_capex = [], 0.0
    for name, months, total, viswas, private in PHASES:
        p = prahari_costs(a, total, viswas)
        rows.append(dict(phase=name, months=months, cameras=total, private_registry_only=private,
                         edge_l=p["edge"]["edge_l_total"], edge_s=p["edge"]["edge_s_total"],
                         events_per_day=p["bandwidth"]["events_per_day"],
                         mbps_peak=p["bandwidth"]["mbps_peak"],
                         capex_cumulative=p["capex"]["total"],
                         capex_increment=p["capex"]["total"] - prev_capex,
                         opex_per_year=p["opex_per_year_total"]))
        prev_capex = p["capex"]["total"]
    return rows


def model4_variants(a: Assumptions) -> dict:
    """Three honest versions of Model 4, from the most to the least favourable to PRAHARI."""
    t, v = a.total_cameras, a.viswas_cameras
    g = model4_steelman_gpus(a, t, v)
    return {
        "as_specified_with_licences": model4_costs(a, t, v, licences=True),
        "infrastructure_only": model4_costs(a, t, v, licences=False),
        "steelman_same_analytics_infra_only": model4_costs(a, t, v, streams_per_gpu=t / g, licences=False),
    }


def headline(a: Assumptions) -> dict:
    p = prahari_costs(a, a.total_cameras, a.viswas_cameras)
    mv = model4_variants(a)
    m, mi, ms = (mv["as_specified_with_licences"], mv["infrastructure_only"],
                 mv["steelman_same_analytics_infra_only"])
    bw = p["bandwidth"]
    return dict(
        anpr_share=p["mix"]["anpr_share"],
        events_per_day=bw["events_per_day"],
        prahari_mbps_avg=bw["mbps_avg"], prahari_mbps_peak=bw["mbps_peak"],
        model4_gbps=m["gbps"],
        ratio_avg=m["gbps"] * 1e3 / bw["mbps_avg"], ratio_peak=m["gbps"] * 1e3 / bw["mbps_peak"],
        edge_nodes=p["edge"]["edge_l_total"] + p["edge"]["edge_s_total"],
        central_raw_tb=p["storage"]["total_raw_tb"], model4_pb=m["storage_pb"],
        prahari_capex_cr=p["capex"]["total"] / CRORE, prahari_opex_cr=p["opex_per_year_total"] / CRORE,
        prahari_tco_cr=p["tco_5y"] / CRORE,
        model4_capex_cr=m["capex"]["total"] / CRORE, model4_opex_cr=m["opex_per_year_total"] / CRORE,
        model4_tco_cr=m["tco_5y"] / CRORE,
        model4_infra_capex_cr=mi["capex"]["total"] / CRORE, model4_infra_opex_cr=mi["opex_per_year_total"] / CRORE,
        model4_infra_tco_cr=mi["tco_5y"] / CRORE,
        model4_steelman_gpus=ms["gpus"], model4_steelman_capex_cr=ms["capex"]["total"] / CRORE,
        model4_steelman_opex_cr=ms["opex_per_year_total"] / CRORE, model4_steelman_tco_cr=ms["tco_5y"] / CRORE,
    )


SENSITIVITY = [  # (label, overrides)
    ("Base case", {}),
    ("ANPR-capable share 50% (dept 43%)", dict(dept_anpr_share=0.43, viswas_anpr_share=0.8)),
    ("ANPR at 2 fps everywhere", dict(anpr_fps=2.0, high_speed_fps=4.0)),
    ("Crop 10 KB", dict(crop_bytes=10_000)),
    ("Crop 30 KB", dict(crop_bytes=30_000)),
    ("Traffic x2 (24k VISWAS / 4k dept veh/day)", dict(viswas_vehicles_per_cam_day=24_000,
                                                      dept_vehicles_per_cam_day=4_000)),
    ("Doc-01 traffic (0.2 veh/s on every ANPR cam)", dict(viswas_vehicles_per_cam_day=17_280 / 0.8,
                                                         dept_vehicles_per_cam_day=17_280 / 0.8)),
    ("Safety factor 3 (real footage worse)", dict(safety_factor=3.0)),
    ("All ANPR cams keyframe-decodable (GOP<=1s)", dict(anpr_keyframe_share=1.0)),
    ("Reuse existing dept PCs at 40% of sites", dict(reuse_existing_pc_share=0.4)),
    ("Crops only for watchlist hits (tier 2)", dict(crop_share_of_anpr_events=0.001)),
    ("Cold 7 y for ALL events (not recommended)", dict(case_event_share=1.0)),
    ("Bandwidth Rs 100/Mbps-month (state fibre)", dict(bw_per_mbps_month=100)),
    ("Bandwidth Rs 500/Mbps-month (small links)", dict(bw_per_mbps_month=500)),
    ("Model 4 at 4 Mbps", dict(video_mbps=4.0)),
    ("Model 4 at 7-day retention", dict(model4_retention_days=7)),
]


def sensitivity(base: Assumptions) -> list[dict]:
    out = []
    for label, ov in SENSITIVITY:
        h = headline(replace(base, **ov))
        out.append(dict(case=label, **{k: h[k] for k in (
            "events_per_day", "prahari_mbps_peak", "ratio_peak", "edge_nodes", "central_raw_tb",
            "prahari_capex_cr", "prahari_tco_cr", "model4_steelman_tco_cr", "model4_infra_tco_cr",
            "model4_tco_cr")}))
    return out


def doc01_check() -> dict:
    """Recompute doc 01 §3.2 exactly as written (24,000 cams x 0.2 veh/s, 200 B + 10 KB)."""
    ev = 80_000 * 0.30 * 0.2 * DAY_S
    ev_mbps = ev * 200 * 8 / DAY_S / 1e6
    crop_mbps = ev * 10_000 * 8 / DAY_S / 1e6
    return dict(events_per_day=ev, events_mbps=ev_mbps, with_crops_mbps=ev_mbps + crop_mbps,
                ratio=160_000 / (ev_mbps + crop_mbps))


# ── printing ─────────────────────────────────────────────────────────────────────────────────
def cr(x: float) -> str:
    return f"{x / CRORE:,.1f}" if x >= CRORE else f"{x / CRORE:,.2f}"


def sig(x: float, n: int = 2) -> str:
    """Round to n significant figures for display."""
    if x == 0:
        return "0"
    d = n - int(math.floor(math.log10(abs(x)))) - 1
    v = round(x, d)
    return f"{v:,.{max(0, d)}f}" if d > 0 else f"{int(v):,}"


def table(title: str, header: list[str], rows: list[list]) -> None:
    print(f"\n### {title}\n")
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join("---" for _ in header) + "|")
    for r in rows:
        print("| " + " | ".join(str(c) for c in r) + " |")


def report(a: Assumptions) -> dict:
    p = prahari_costs(a, a.total_cameras, a.viswas_cameras)
    mv = model4_variants(a)
    m, mi, ms = (mv["as_specified_with_licences"], mv["infrastructure_only"],
                 mv["steelman_same_analytics_infra_only"])
    mix, bw, ed, st, ce = p["mix"], p["bandwidth"], p["edge"], p["storage"], p["central"]
    h = headline(a)
    d1 = doc01_check()
    m4b = model4_bandwidth(a, a.total_cameras)

    table("Camera mix (80,000)", ["segment", "ANPR", "light analytics", "total"], [
        ["VISWAS (at Netram)", f"{mix['viswas_anpr']:,.0f}", f"{mix['viswas_light']:,.0f}", f"{mix['viswas']:,}"],
        ["Departmental", f"{mix['dept_anpr']:,.0f}", f"{mix['dept_light']:,.0f}", f"{mix['dept']:,}"],
        ["All", f"{mix['anpr']:,.0f}", f"{mix['light']:,.0f}", f"{mix['total']:,} ({mix['anpr_share']:.0%} ANPR)"],
    ])
    table("Bandwidth: PRAHARI upstream vs centralised video", ["quantity", "value"], [
        ["events/day: plate + light", f"{sig(bw['anpr_events_per_day'])} + {sig(bw['light_events_per_day'])}"],
        ["events/s avg / peak hour", f"{sig(bw['events_per_s_avg'])} / {sig(bw['events_per_s_peak'])}"],
        ["GB/day events / crops / telemetry / clips",
         " / ".join(sig(bw['gb_per_day'][k]) for k in ("events", "crops", "telemetry", "clips"))],
        ["statewide events only, avg", f"{sig(bw['mbps_events_only'])} Mbps"],
        ["statewide all traffic, avg / peak", f"{sig(bw['mbps_avg'])} / {sig(bw['mbps_peak'])} Mbps"],
        ["per district avg / peak (mean district)", f"{sig(bw['district_avg_mbps'])} / {sig(bw['district_avg_peak_mbps'])} Mbps"],
        ["largest district peak", f"{sig(bw['largest_district_peak_mbps'])} Mbps"],
        ["largest Netram (VISWAS) peak", f"{sig(netram_peak_mbps(a, mix))} Mbps"],
        ["Model 4 video @2 / @4 Mbps", f"{sig(m4b['gbps'])} / {sig(m4b['gbps_high'])} Gbps"],
        ["ratio vs PRAHARI avg / peak (@2 Mbps)", f"{sig(h['ratio_avg'])}x / {sig(h['ratio_peak'])}x"],
        ["doc 01 as written (recomputed)", f"{sig(d1['with_crops_mbps'])} Mbps, ratio {sig(d1['ratio'])}x"],
    ])
    table("Departmental site uplink by bandwidth-ladder tier",
          ["site cams", "share of sites", "tier 3 avg", "tier 3 peak", "tier 1 avg", "offline days in 100 GB queue",
           "30 s clip over 512 kbps"],
          [[r["cams"], f"{r['share_of_sites']:.0%}", f"{sig(r['tier3_avg_kbps'])} kbps",
            f"{sig(r['tier3_peak_kbps'])} kbps", f"{sig(r['tier1_avg_kbps'])} kbps",
            ">1 year" if r["offline_days_in_queue"] > 365 else sig(r["offline_days_in_queue"]),
            f"{r['clip_pull_minutes_at_512k']:.0f} min"]
           for r in site_uplink(a)])
    ref = m1_reference(a)
    rows = [["M1 laptop (measured)", "1 worker", f"{ref['naive_streams_1fps']} naive / {ref['planned_streams_1fps']} planned",
             "-", "-", "-", "-"]]
    for k, c in NODE_CLASSES.items():
        s = node_streams(a, c)
        rows.append([k, c["desc"], s["anpr_1fps"], f"{s['anpr_mixed_fps']} ({s['anpr_bound']}-bound)",
                     s["light_only"], f"{c['price'] / LAKH:.1f} L", f"{c['watts']} W"])
    table("Edge node classes (streams per node, safety x%.1f, util %.0f%%)" % (a.safety_factor, a.target_util * 100),
          ["class", "hardware", "ANPR @1 fps", "ANPR @ mixed fps", "light-only @0.2 fps", "price", "power"], rows)
    print(f"\nSoftware decode on M1: {sig(ref['sw_decode_pct_core_per_1080p25'])}% of a core per 1080p25 stream "
          f"-> ~{ref['sw_decode_streams_8_cores_at_util']} full-decode streams per 8 cores at target util; "
          f"keyframe-only ~{ref['keyframe_streams_per_core_at_util']} streams per core. Decode, not inference, "
          f"is the edge bottleneck without hardware decode.")
    table("Edge fleet for 80,000 cameras", ["item", "count"], [
        ["EDGE-L at Netram (working + one N+1 spare per Netram)", f"{ed['edge_l_working']} + {ed['edge_l_spares']} = {ed['edge_l_total']}"],
        ["Departmental NVR sites (mean cams/site)", f"{sig(ed['dept_sites'])} ({ed['dept_mean_cams_per_site']:.0f})"],
        ["EDGE-S nodes (bought + spares)", f"{ed['edge_s_bought']:,} + {ed['edge_s_spares']:,} = {ed['edge_s_total']:,}"],
        ["Edge power", f"{sig(ed['kw'])} kW"],
    ])
    table("Central (SCRB DC), DR and regional tiers", ["item", "value"], [
        ["ingest peak", f"{sig(bw['events_per_s_peak'])} events/s"],
        ["search/trace peak", f"{ce['search_qps_peak']:.1f} queries/s"],
        ["pods", ", ".join(f"{k}: {v}" for k, v in ce["pods"].items())],
        ["app vCPU", ce["vcpu"]],
        ["DC hosts (app + DB + object)", f"{ce['app_hosts']} + {ce['db_hosts']} + {ce['object_hosts_per_site']} = {ce['dc_hosts']}"],
        ["DR hosts (warm standby)", ce["dr_hosts"]],
        ["Regional servers (2 per Netram)", ce["regional_servers"]],
        ["central IT power (DC + DR)", f"{sig(ce['kw_it'])} kW"],
    ])
    table("Storage tiers (TB, one logical copy)", ["tier", "TB"], [
        ["events hot (90 d, row store)", sig(st["events_hot_tb"])],
        ["events warm (to 1 y, compressed)", sig(st["events_warm_tb"])],
        ["events cold (case-linked, 7 y)", sig(st["events_cold_tb"])],
        ["crops hot (90 d)", sig(st["crops_hot_tb"])],
        ["crops cold (case-linked, 7 y)", sig(st["crops_cold_tb"])],
        ["clips hot (30 d)", sig(st["clips_hot_tb"])],
        ["clips cold (case-linked, 7 y)", sig(st["clips_cold_tb"])],
        ["event bus (7 d replay, x3)", sig(st["bus_tb"])],
        ["TOTAL logical / raw incl. copies, EC, DR", f"{sig(st['total_logical_tb'])} / {sig(st['total_raw_tb'])}"],
        ["Model 4 video, 30 d (one copy)", f"{sig(m['storage_pb'] * 1e3)} TB = {sig(m['storage_pb'])} PB"],
    ])
    table("Capex, Rs crore (ex-GST), 80,000 cameras", ["line", "PRAHARI", "line", "Model 4 (infra only)"], [
        ["edge nodes + install", cr(p["capex"]["edge"]), "GPU servers (4x L4)", cr(mi["capex_hw"]["GPU servers (4x L4)"])],
        ["central DC", cr(p["capex"]["central_dc"]), "recording servers", cr(mi["capex_hw"]["recording servers"])],
        ["DR site", cr(p["capex"]["dr"]), "video storage", cr(mi["capex_hw"]["video storage"])],
        ["regional (Netram) servers", cr(p["capex"]["regional"]), "core network", cr(mi["capex_hw"]["core network"])],
        ["", "", "site WAN installs", cr(mi["capex_hw"]["site WAN installs"])],
        ["", "", "metadata/DR/management", cr(mi["capex_hw"]["metadata/DR/management (~as PRAHARI central)"])],
        ["CAPEX", cr(p["capex"]["total"]), "CAPEX", cr(mi["capex"]["total"])],
        ["", "", "+ commercial licences (if bought)", cr(m["capex"]["licences"])],
    ])
    table("Opex per year, Rs crore", ["line", "PRAHARI", "line", "Model 4 (infra only)"],
          [[k1, cr(v1) if k1 else "", k2, cr(v2) if k2 else ""] for (k1, v1), (k2, v2) in zip(
              list(p["opex_per_year"].items()) + [("", 0)] * 3,
              [(k, v) for k, v in mi["opex_per_year"].items() if k != "licence support"] + [("", 0)] * 5)
           if k1 or k2] + [["OPEX / YEAR", cr(p["opex_per_year_total"]), "OPEX / YEAR", cr(mi["opex_per_year_total"])]])
    table("5-year TCO, Rs crore (capex + 5 yr opex, AMC from year 2)", ["design", "capex", "opex/yr", "5-yr TCO"], [
        ["PRAHARI (federated)", cr(p["capex"]["total"]), cr(p["opex_per_year_total"]), cr(p["tco_5y"])],
        [f"Model 4 steelman: same 1-fps analytics, {ms['gpus']} L4s, infra only",
         cr(ms["capex"]["total"]), cr(ms["opex_per_year_total"]), cr(ms["tco_5y"])],
        [f"Model 4 as usually specified: {mi['gpus']:,} GPUs, infra only",
         cr(mi["capex"]["total"]), cr(mi["opex_per_year_total"]), cr(mi["tco_5y"])],
        ["Model 4 as usually specified + commercial licences",
         cr(m["capex"]["total"]), cr(m["opex_per_year_total"]), cr(m["tco_5y"])],
    ])
    print(f"\nModel 4 as specified: {mi['gpus']:,} GPUs in {mi['gpu_servers']} servers, {mi['recorders']} recorders, "
          f"~{mi['drives']:,} x 20 TB drives, ~{sig(mi['kw_it'])} kW IT. Steelman: {ms['gpus']} GPUs, ~{sig(ms['kw_it'])} kW IT.")
    ph = phases(a)
    table("Phased rollout", ["phase", "months", "cameras", "EDGE-L", "EDGE-S", "events/day", "peak Mbps",
                             "capex this phase (Cr)", "opex/yr at end (Cr)"],
          [[r["phase"], r["months"], f"{r['cameras']:,}" + (f" + {r['private_registry_only']:,} pvt" if r["private_registry_only"] else ""),
            r["edge_l"], f"{r['edge_s']:,}", sig(r["events_per_day"]), sig(r["mbps_peak"]),
            cr(r["capex_increment"]), cr(r["opex_per_year"])] for r in ph])
    sens = sensitivity(a)
    table("Sensitivity (80,000 cameras; TCO = 5 years, Rs crore)",
          ["case", "events/day", "PRAHARI peak Mbps", "ratio @peak", "edge nodes", "central raw TB",
           "PRAHARI capex", "PRAHARI TCO", "M4 steelman TCO", "M4 infra TCO", "M4 +licences TCO"],
          [[s["case"], sig(s["events_per_day"]), sig(s["prahari_mbps_peak"]), f"{sig(s['ratio_peak'])}x",
            f"{s['edge_nodes']:,}", sig(s["central_raw_tb"]), f"{s['prahari_capex_cr']:.0f}",
            f"{s['prahari_tco_cr']:.0f}", f"{s['model4_steelman_tco_cr']:.0f}", f"{s['model4_infra_tco_cr']:.0f}",
            f"{s['model4_tco_cr']:.0f}"] for s in sens])
    return dict(assumptions=asdict(a), node_classes=NODE_CLASSES, headline=h, doc01_recomputed=d1,
                m1_reference=ref, node_streams={k: node_streams(a, c) for k, c in NODE_CLASSES.items()},
                site_uplink=site_uplink(a), netram_largest_peak_mbps=netram_peak_mbps(a, mix),
                prahari=p, model4=mv,
                model4_steelman_gpus=model4_steelman_gpus(a, a.total_cameras, a.viswas_cameras),
                phases=ph, sensitivity=sens)


def _round(o):
    if isinstance(o, float):
        return float(sig(o, 3).replace(",", "")) if o else 0.0
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_round(v) for v in o]
    return o


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = report(Assumptions())
    if not args.quiet:
        print(buf.getvalue())
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(_round(res), indent=1))
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
