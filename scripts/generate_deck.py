#!/usr/bin/env python3
"""
Generate the official PRAHARI Solution Presentation (.pptx)
for the Gujarat Police Sentinel Hackathon 2026.

Uses python-pptx with a 16:9 widescreen layout, Gujarat Police navy & gold palette,
formatted metric boxes, comparison tables, and slide presenter notes.
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

OUTPUT_PATH = "docs/presentation/PRAHARI-Solution-Presentation.pptx"

# Color Palette: Gujarat Police / Sentinel
COLOR_NAVY_BG = RGBColor(10, 17, 40)        # #0a1128
COLOR_CARD_BG = RGBColor(18, 28, 52)        # #121c34
COLOR_GOLD = RGBColor(245, 158, 11)         # #f59e0b
COLOR_WHITE = RGBColor(255, 255, 255)       # #ffffff
COLOR_MUTED = RGBColor(148, 163, 184)      # #94a3b8
COLOR_GREEN = RGBColor(16, 185, 129)       # #10b981
COLOR_RED = RGBColor(239, 68, 68)          # #ef4444
COLOR_BLUE_BOX = RGBColor(30, 58, 138)     # #1e3a8a
COLOR_BORDER = RGBColor(40, 56, 88)        # #283858


def create_deck():
    prs = Presentation()
    # 16:9 widescreen
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    def set_bg(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = COLOR_NAVY_BG
        bg.line.fill.background()
        return bg

    def add_header(slide, title_text, category_text, slide_num_str):
        # Category badge
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(4.0), Inches(0.35))
        tf = cat_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = category_text.upper()
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = COLOR_GOLD

        # Slide Number
        num_box = slide.shapes.add_textbox(Inches(11.5), Inches(0.4), Inches(1.2), Inches(0.35))
        tf_n = num_box.text_frame
        p_n = tf_n.paragraphs[0]
        p_n.alignment = PP_ALIGN.RIGHT
        p_n.text = slide_num_str
        p_n.font.size = Pt(11)
        p_n.font.color.rgb = COLOR_MUTED

        # Main Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.8), Inches(0.8))
        tf_t = title_box.text_frame
        tf_t.word_wrap = True
        p_t = tf_t.paragraphs[0]
        p_t.text = title_text
        p_t.font.size = Pt(26)
        p_t.font.bold = True
        p_t.font.color.rgb = COLOR_WHITE

        # Divider line
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.45), Inches(11.733), Inches(0.02))
        line.fill.solid()
        line.fill.fore_color.rgb = COLOR_GOLD
        line.line.fill.background()

    def add_card(slide, left, top, width, height, title, items, highlight=False):
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        box.fill.solid()
        box.fill.fore_color.rgb = COLOR_CARD_BG
        box.line.color.rgb = COLOR_GOLD if highlight else COLOR_BORDER
        box.line.width = Pt(2 if highlight else 1)

        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.TOP
        tf.margin_left = Inches(0.2)
        tf.margin_right = Inches(0.2)
        tf.margin_top = Inches(0.2)
        tf.margin_bottom = Inches(0.2)

        if title:
            p = tf.paragraphs[0]
            p.text = title
            p.font.size = Pt(16)
            p.font.bold = True
            p.font.color.rgb = COLOR_GOLD if highlight else COLOR_WHITE
            p.space_after = Pt(10)

        for i, item in enumerate(items):
            p = tf.add_paragraph() if (title or i > 0) else tf.paragraphs[0]
            p.text = f"•  {item}"
            p.font.size = Pt(12)
            p.font.color.rgb = COLOR_WHITE
            p.space_after = Pt(6)

    def add_metric_box(slide, left, top, width, height, number_str, label_str):
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        box.fill.solid()
        box.fill.fore_color.rgb = COLOR_BLUE_BOX
        box.line.color.rgb = COLOR_GOLD
        box.line.width = Pt(1.5)

        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE

        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.text = number_str
        p.font.size = Pt(28)
        p.font.bold = True
        p.font.color.rgb = COLOR_WHITE

        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        p2.text = label_str.upper()
        p2.font.size = Pt(9)
        p2.font.bold = True
        p2.font.color.rgb = COLOR_GOLD

    def set_notes(slide, notes_text):
        notes_slide = slide.notes_slide
        tf = notes_slide.notes_text_frame
        tf.text = notes_text

    # -------------------------------------------------------------
    # SLIDE 1: Title
    # -------------------------------------------------------------
    s1 = prs.slides.add_slide(blank_layout)
    set_bg(s1)

    # Title badges
    tb = s1.shapes.add_textbox(Inches(1.0), Inches(1.2), Inches(11.3), Inches(0.5))
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.text = "GUJARAT POLICE SENTINEL HACKATHON 2026  ·  DECLARED HYBRID MODEL"
    p.font.size = Pt(12)
    p.font.bold = True
    p.font.color.rgb = COLOR_GOLD

    # Main Title
    tb_title = s1.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(11.3), Inches(1.5))
    p = tb_title.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.text = "PRAHARI (પ્રહરી)"
    p.font.size = Pt(56)
    p.font.bold = True
    p.font.color.rgb = COLOR_WHITE

    p2 = tb_title.text_frame.add_paragraph()
    p2.alignment = PP_ALIGN.CENTER
    p2.text = "Integrated Video Management & Analytics Platform across 26 Government Departments"
    p2.font.size = Pt(20)
    p2.font.color.rgb = COLOR_MUTED

    # Metrics
    add_metric_box(s1, Inches(2.2), Inches(4.0), Inches(2.6), Inches(1.5), "80,000", "Cameras Statewide")
    add_metric_box(s1, Inches(5.35), Inches(4.0), Inches(2.6), Inches(1.5), "0.45 Gbps", "Peak WAN Bandwidth")
    add_metric_box(s1, Inches(8.5), Inches(4.0), Inches(2.6), Inches(1.5), "₹130 Cr", "5-Year Total Cost")

    tb_sub = s1.shapes.add_textbox(Inches(1.0), Inches(6.0), Inches(11.3), Inches(0.8))
    p = tb_sub.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.text = "Production Codebase: AJ-EN/prahari  ·  159 / 159 Tests Passing  ·  Zero-Inbound mTLS"
    p.font.size = Pt(12)
    p.font.color.rgb = COLOR_MUTED
    set_notes(s1, "Welcome the jury. State that PRAHARI means 'the sentinel' in Gujarati. Emphasize that the codebase is 100% operational with 159 automated tests passing.")

    # -------------------------------------------------------------
    # SLIDE 2: Core Thesis
    # -------------------------------------------------------------
    s2 = prs.slides.add_slide(blank_layout)
    set_bg(s2)
    add_header(s2, "The Fundamental Law: Move Meaning, Not Megabytes", "Core Architectural Principle", "02 / 18")

    add_card(s2, Inches(0.8), Inches(1.8), Inches(5.6), Inches(3.8),
             "❌ The Central Streaming Trap (Model 4)",
             ["160 Gbps Sustained WAN: Streaming 80,000 feeds centrally requires massive leased lines.",
              "₹60+ Cr Annual Telco Bill: Huge recurring WAN fees payable to telecom operators.",
              "52 Petabytes Storage / Month: Astronomical SAN/NAS storage cost for inactive raw video.",
              "Single Point of Failure: A single backhaul fiber cut blinds state dispatchers entirely."],
             highlight=False)

    add_card(s2, Inches(6.8), Inches(1.8), Inches(5.6), Inches(3.8),
             "✅ The PRAHARI Law (Federated Edge)",
             ["Video stays where it is born on departmental LANs; only structured observations cross the WAN.",
              "0.21 Gbps Avg / 0.45 Gbps Peak WAN: ~360× to 750× reduction in network traffic.",
              "~210 TB Central Storage: Stores only structured text events (~550 B) and forensic crops (~15 KB).",
              "Autonomous Island Mode: Edge continues local inference during network cuts; zero event loss."],
             highlight=True)

    add_metric_box(s2, Inches(0.8), Inches(5.8), Inches(11.6), Inches(1.0),
                   "160 Gbps  →  0.45 Gbps at Peak (~360× Reduction)", "Empirically Verified Network Bandwidth")
    set_notes(s2, "Explain the core thesis. If you centralize video for 80,000 cameras, the WAN bill alone is ₹60 Cr/yr. PRAHARI processes at the edge, reducing peak bandwidth to 0.45 Gbps.")

    # -------------------------------------------------------------
    # SLIDE 3: The Challenge
    # -------------------------------------------------------------
    s3 = prs.slides.add_slide(blank_layout)
    set_bg(s3)
    add_header(s3, "The Ground Reality: 26 Departments & 80,000 Cameras", "Operational Context", "03 / 18")

    add_card(s3, Inches(0.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "🏢 26 Siloed Departments",
             ["Home (VISWAS Police junctions)",
              "Civil Supplies (PDS godowns)",
              "Transport / RTO (Tracks & Tolls)",
              "Health (Hospital corridors)",
              "GSRTC (Bus depot bays)",
              "Separate 5-year AMC contracts",
              "Conflicting retention rules (7 to 30d)"])

    add_card(s3, Inches(4.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "📍 1,000 km Dispersion",
             ["Kutch border posts to Valsad industrial belt",
              "1 Gbps urban fiber to 2G/4G cellular links",
              "Frequent WAN cuts in Dahod & Dangs",
              "Latency fluctuates from 5 ms to 450 ms",
              "Unstable power and harsh field conditions"])

    add_card(s3, Inches(8.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "📹 Extreme Heterogeneity",
             ["Analog DVRs alongside modern 4K IP cameras",
              "Mixed codecs: H.264, H.265, MJPEG",
              "480p to 4K resolutions",
              "Non-standard RTSP implementations",
              "Cannot force a single proprietary VMS"])

    add_card(s3, Inches(0.8), Inches(6.15), Inches(11.7), Inches(0.9),
             "",
             ["Strategic Rule: Any architecture requiring departments to replace NVRs or void AMC contracts fails immediately. PRAHARI adapts to Gujarat's reality with ZERO hardware changes."])
    set_notes(s3, "Describe Gujarat's operational reality. 26 departments, 1,000 km dispersion, mixed codecs, and differing AMC contracts. Explain why forced centralization fails politically.")

    # -------------------------------------------------------------
    # SLIDE 4: Model Selection
    # -------------------------------------------------------------
    s4 = prs.slides.add_slide(blank_layout)
    set_bg(s4)
    add_header(s4, "Model Selection: Hybrid Architecture (Model 5)", "Architecture Strategy", "04 / 18")

    # Add a table
    table_shape = s4.shapes.add_table(5, 4, Inches(0.8), Inches(1.8), Inches(11.733), Inches(4.0))
    table = table_shape.table
    table.columns[0].width = Inches(2.5)
    table.columns[1].width = Inches(2.2)
    table.columns[2].width = Inches(3.2)
    table.columns[3].width = Inches(3.833)

    headers = ["Model", "Status in PRAHARI", "Technology", "Architectural Justification"]
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = COLOR_BLUE_BOX
        for p in cell.text_frame.paragraphs:
            p.font.size = Pt(11)
            p.font.bold = True
            p.font.color.rgb = COLOR_GOLD

    rows = [
        ("Model 1: Registry & GIS", "Mandatory Base", "PostgreSQL + PostGIS", "Central asset visibility, 3 onboarding paths, automated spatial gap analysis."),
        ("Model 3: VMS Federation", "Federation Spine", "Schema Bus / Middleware", "Federates existing Milestone/Genetec/Hikvision NVRs without touching local storage."),
        ("Model 2: Direct Ingest", "Edge Viewing Layer", "RTSP / ONVIF Adapters", "Connects standalone cameras lacking local VMS hosts into the unified viewing wall."),
        ("Model 4: Central VMS", "Rejected with Math", "Evaluated & Refuted", "Demolished by network arithmetic (₹60 Cr/yr WAN bill + 52 PB storage footprint).")
    ]
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.cell(i+1, j)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = COLOR_CARD_BG
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(10)
                p.font.color.rgb = COLOR_WHITE

    add_card(s4, Inches(0.8), Inches(6.0), Inches(11.733), Inches(1.0),
             "",
             ["Hybrid Model 5 delivers 100% of Model 4's statewide analytics capabilities while avoiding its ₹510+ Cr infrastructure bill."])
    set_notes(s4, "Walk through the four models. Justify adopting Model 1 as foundation, Model 3 as federation spine, Model 2 for edge cameras, and rejecting Model 4 with empirical arithmetic.")

    # -------------------------------------------------------------
    # SLIDE 5: Statewide Topology
    # -------------------------------------------------------------
    s5 = prs.slides.add_slide(blank_layout)
    set_bg(s5)
    add_header(s5, "Statewide Three-Tier Architecture", "System Topology", "05 / 18")

    add_card(s5, Inches(0.8), Inches(1.8), Inches(3.7), Inches(4.3),
             "Tier 1: Department Edge",
             ["~3,300 Departmental NVR Sites",
              "PRAHARI Node: Lightweight container on existing servers or ₹20k mini-PCs",
              "LAN RTSP/ONVIF Ingestion",
              "Edge YOLOv8 ANPR & CCAP Profiler",
              "Outbound mTLS only (Port 443)",
              "Zero inbound open ports",
              "72-hour local SSD ring buffer"],
             highlight=False)

    add_card(s5, Inches(4.8), Inches(1.8), Inches(3.7), Inches(4.3),
             "Tier 2: Regional Hubs",
             ["34 Netram District C3 Centres",
              "Regional GPU Servers (2× L4 per centre)",
              "VISWAS ~17,500 Junction Ingestion",
              "NATS JetStream Regional Aggregation",
              "District Police Video Wall & GIS",
              "Local 30-day evidentiary clip cache",
              "Sub-district CAD emergency dispatch"],
             highlight=True)

    add_card(s5, Inches(8.8), Inches(1.8), Inches(3.7), Inches(4.3),
             "Tier 3: Central SCRB",
             ["SCRB Gandhinagar / State Data Centre",
              "Central Registry (PostGIS & PostgreSQL)",
              "Confusion-Space Watchlist Matcher",
              "Statewide Trajectory Engine",
              "Evidence Vault (SHA-256 Hash Chain)",
              "VAHAN, SARTHI, eGujCop Adapters",
              "Peak WAN: Only 0.45 Gbps statewide"],
             highlight=False)

    add_metric_box(s5, Inches(0.8), Inches(6.25), Inches(11.7), Inches(0.8),
                   "Statewide Peak Ingest Bandwidth: 0.45 Gbps", "WAN Carries Structured JSON & Forensic Crops Only")
    set_notes(s5, "Explain the 3 tiers: Department Edge, 34 Netram District Command Centres, and Central SCRB Gandhinagar. Emphasize that the WAN carries metadata, not continuous video.")

    # -------------------------------------------------------------
    # SLIDE 6: Innovation 1 - CCAP
    # -------------------------------------------------------------
    s6 = prs.slides.add_slide(blank_layout)
    set_bg(s6)
    add_header(s6, "Innovation 1: Camera Capability Auto-Profiling (CCAP)", "Flagship Feature", "06 / 18")

    add_card(s6, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.1),
             "The Problem It Solves",
             ["Statewide grids include hospital hallways, bus depot ticket counters, and school gates.",
              "Corridors and indoor gates will never show number plates.",
              "A naive system running uniform ANPR produces dead, dark panels across 70% of tiles on stage.",
              "Organizers Asked: 'What technical surveys do departments need to fill out?'",
              "PRAHARI's Answer: 'Zero surveys. The system measures every camera itself.'"],
             highlight=False)

    add_card(s6, Inches(6.8), Inches(1.8), Inches(5.6), Inches(4.1),
             "How CCAP Profiles Streams (prahari.anpr.ccap)",
             ["Profiles each stream for 60 seconds on onboarding.",
              "Measures median plate height: If plate_px_median < 24 px → ANPR unviable.",
              "Measures legibility: If valid_rate < 0.33 → Flagged as noisy / glare.",
              "Dynamic Scheduler: Throttles unviable cameras to 1 frame in 10, conserving 90% of GPU compute.",
              "Assigns appropriate analytics: Loitering, crowd density, or perimeter intrusion."],
             highlight=True)

    add_card(s6, Inches(0.8), Inches(6.05), Inches(11.6), Inches(1.0),
             "",
             ["JSON Output: {\"camera_id\": \"GJ-HLT-0142\", \"scene\": \"corridor\", \"plate_px_median\": 8.2, \"anpr_viable\": false, \"assigned\": [\"crowd_density\", \"loitering\"]}"])
    set_notes(s6, "Present CCAP. Corridors don't show plates; CCAP detects this in 60s and reassigns 90% of GPU compute. When organizers asked what info departments need to fill out, our answer was: None.")

    # -------------------------------------------------------------
    # SLIDE 7: Innovation 2 - Grammar Matching
    # -------------------------------------------------------------
    s7 = prs.slides.add_slide(blank_layout)
    set_bg(s7)
    add_header(s7, "Innovation 2: Indian Plate Grammar & Confusion Matching", "AI & Analytics", "07 / 18")

    add_card(s7, Inches(0.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "1. Indian Plate Grammar",
             ["Rigid syntax: ^[A-Z]{2}\\d{1,2}[A-Z]{0,3}\\d{4}$",
              "Closed vocabulary of 36 active & historical State/UT codes",
              "Validated RTO district limits (GJ max = 38)",
              "Rejects syntactic garbage before database lookups",
              "Eliminates false alarms from billboard text"],
             highlight=False)

    add_card(s7, Inches(4.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "2. Constrained Beam Search",
             ["Repairs character OCR confusions",
              "Raw OCR: '6J 01 A8 I234'",
              "'6J' is invalid; pos 1-2 must be state letters → resolves to 'GJ'",
              "Pos 6 must be letter → '8' resolves to 'B'",
              "Pos 7 must be digit → 'I' resolves to '1'",
              "Clean plate emerges: GJ01AB1234"],
             highlight=False)

    add_card(s7, Inches(8.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "3. Confusion Matching",
             ["Watchlist lookup in confusion space",
              "cost(O→0) = 0.1, cost(I→1) = 0.1",
              "cost(B→8) = 0.15, cost(G→6) = 0.20",
              "Unrelated substitutions cost 1.0",
              "ALERT: dist ≤ 0.15 (Automated)",
              "REVIEW: 0.15 < dist ≤ 0.35 (Operator)"],
             highlight=True)

    add_metric_box(s7, Inches(0.8), Inches(6.15), Inches(11.7), Inches(0.9),
                   "Zero Silent False Negatives on Stage", "Ranked Candidates with Evidence Crops Ensure Hits Are Never Missed")
    set_notes(s7, "Explain why naive SQL exact matching fails in India due to mud, glare, and fonts. Detail our 3-layer architecture: Indian Plate Grammar, Constrained Beam Search, and Confusion-Space Matching.")

    # -------------------------------------------------------------
    # SLIDE 8: Innovation 3 - Re-ID & Velocity
    # -------------------------------------------------------------
    s8 = prs.slides.add_slide(blank_layout)
    set_bg(s8)
    add_header(s8, "Innovation 3: Re-ID Bridging & Velocity Gating", "Tracking Intelligence", "08 / 18")

    add_card(s8, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.1),
             "Surviving Occluded Plates (Re-ID)",
             ["Suspect vehicles driving behind trucks or through night glare suffer unreadable plates.",
              "Anchor Sightings: High-confidence plate reads establish journey anchors.",
              "Visual Appearance Re-ID: Gaps are bridged using vehicle embeddings (make, model, color histogram, aspect ratio).",
              "Continuous Trajectory: Maintains tracking continuity across blind camera segments."],
             highlight=False)

    add_card(s8, Inches(6.8), Inches(1.8), Inches(5.6), Inches(4.1),
             "Physical Velocity Gating (prahari.registry.trace)",
             ["Computes straight-line Haversine distance and transit time between consecutive cameras.",
              "Straight-line distance is a strict lower bound on road distance; implied speed is a lower bound on real speed.",
              "If implied speed > 150 km/h: Flagged as physically impossible.",
              "Forensic Honesty: Alerts investigators to cloned plates, clock skew, or misreads."],
             highlight=True)

    add_card(s8, Inches(0.8), Inches(6.05), Inches(11.6), Inches(1.0),
             "",
             ["Live Flag: Stop 3 → 4: 42 km in 4 min = 630 km/h  [IMPLAUSIBLE: Possible Cloned License Plate or Clock Skew]"])
    set_notes(s8, "Show how Re-ID bridges missing plates and how velocity gating flags cloned plates. Implausible hops (>150 km/h) are flagged on screen, demonstrating forensic honesty.")

    # -------------------------------------------------------------
    # SLIDE 9: Innovation 4 - Zero Inbound
    # -------------------------------------------------------------
    s9 = prs.slides.add_slide(blank_layout)
    set_bg(s9)
    add_header(s9, "Innovation 4: Zero-Inbound, Zero-Change Onboarding", "Network & Operations", "09 / 18")

    add_card(s9, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.1),
             "The Organizational Deadlock",
             ["26 departments refuse to open inbound firewall ports (security policy).",
              "Refusal to surrender custody of video recordings to police servers.",
              "Fear of voiding 5-year AMC maintenance contracts on existing NVRs.",
              "Lack of public static IP addresses at remote taluka offices.",
              "Results in multi-year bureaucratic negotiations."],
             highlight=False)

    add_card(s9, Inches(6.8), Inches(1.8), Inches(5.6), Inches(4.1),
             "The PRAHARI Solution",
             ["Outbound-Only mTLS (Port 443): Node dials out to state gateway; zero inbound ports opened.",
              "NAT Traversal: Operates behind 4G cellular dongles & corporate proxy firewalls.",
              "Zero Hardware Changes: Reads local RTSP streams on LAN; NVRs & AMCs untouched.",
              "Department Incentive: Departments receive free automated camera health telemetry."],
             highlight=True)

    add_metric_box(s9, Inches(0.8), Inches(6.05), Inches(11.6), Inches(1.0),
                   "0 Inbound Ports  ·  0 Firewall Changes  ·  0 AMC Disputes", "Mechanism Design Transforms 5-Year Deadlocks into a 6-Month Rollout")
    set_notes(s9, "Explain mechanism design. By dialing out over port 443 with mTLS, no firewall changes are required. Departments keep their video, keep their AMCs, and get free health telemetry.")

    # -------------------------------------------------------------
    # SLIDE 10: Innovation 5 - Bandwidth Ladder
    # -------------------------------------------------------------
    s10 = prs.slides.add_slide(blank_layout)
    set_bg(s10)
    add_header(s10, "Innovation 5: The 5-Tier Bandwidth Ladder", "Resilience & Fallback", "10 / 18")

    # Table for Bandwidth Ladder
    table_shape = s10.shapes.add_table(6, 4, Inches(0.8), Inches(1.8), Inches(11.733), Inches(4.2))
    table = table_shape.table
    table.columns[0].width = Inches(1.6)
    table.columns[1].width = Inches(2.2)
    table.columns[2].width = Inches(4.8)
    table.columns[3].width = Inches(3.133)

    t_headers = ["Tier", "Available Uplink", "Transmitted Payload", "Operational Environment"]
    for j, h in enumerate(t_headers):
        cell = table.cell(0, j)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = COLOR_BLUE_BOX
        for p in cell.text_frame.paragraphs:
            p.font.size = Pt(11)
            p.font.bold = True
            p.font.color.rgb = COLOR_GOLD

    ladder_rows = [
        ("Tier 4", "> 10 Mbps", "Text events + 15 KB crops + thumbnails + on-demand live video", "Urban Junctions, Netram C3"),
        ("Tier 3", "2 – 10 Mbps", "All text events + full evidence crops", "District Hubs, Taluka Centres"),
        ("Tier 2", "0.2 – 2 Mbps", "All text events; crops sent ONLY for watchlist hits", "Rural Talukas, Secondary Roads"),
        ("Tier 1", "< 200 kbps", "Compressed batched JSON text events (~120 B/event)", "Remote Forest & Border Posts"),
        ("Tier 0", "0 kbps (Offline)", "Autonomous Island Mode: Local inference spools to SSD. Auto-sync on reconnect", "Severed Fiber, Total WAN Outages")
    ]
    for i, row in enumerate(ladder_rows):
        for j, val in enumerate(row):
            cell = table.cell(i+1, j)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = COLOR_CARD_BG
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(10)
                p.font.color.rgb = COLOR_WHITE

    add_card(s10, Inches(0.8), Inches(6.15), Inches(11.733), Inches(0.9),
             "",
             ["Tier 0 Island Mode Guarantee: If fiber is cut in Dahod for 48 hours, edge nodes continue detecting plates, buffering in SQLite, and backfill completely on reconnection."])
    set_notes(s10, "Detail the 5-Tier Bandwidth Ladder. Emphasize Tier 0 Autonomous Island Mode where edge nodes keep detecting and spooling to SSD during WAN cuts.")

    # -------------------------------------------------------------
    # SLIDE 11: End-to-End Workflow
    # -------------------------------------------------------------
    s11 = prs.slides.add_slide(blank_layout)
    set_bg(s11)
    add_header(s11, "End-to-End Workflow: Ingest → Alert → Trace", "Execution Pipeline", "11 / 18")

    add_card(s11, Inches(0.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "1. Ingest & Profile",
             ["RTSP over TCP enforces lossless frame transport",
              "PyAV extracts container Presentation Timestamps (PTS)",
              "Eliminates false velocity spikes on reconnect",
              "CCAP profiles plate pixel height & scene class",
              "Corridors sampled 1/10; junctions at full rate"],
             highlight=False)

    add_card(s11, Inches(4.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "2. Detect & Decode",
             ["YOLOv8 plate detection in ~15 ms (ONNX)",
              "Aspect ratio check splits two-line plates",
              "CRNN OCR outputs greedy posteriors",
              "Grammar beam search resolves characters",
              "PlateDeduper: 6.0s rolling window prevents multi-frame alert flooding"],
             highlight=False)

    add_card(s11, Inches(8.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "3. Match & Dispatch",
             ["Confusion-space weighted Levenshtein matching",
              "ALERT (d ≤ 0.15) / REVIEW (0.15 < d ≤ 0.35)",
              "Server-Sent Events (SSE) dispatches in < 50 ms",
              "SHA-256 hash sealed into audit ledger",
              "Instant display on 50-tile Operator Wall"],
             highlight=True)

    add_metric_box(s11, Inches(0.8), Inches(6.15), Inches(11.7), Inches(0.9),
                   "End-to-End Alert Latency: < 150 ms", "Frame Capture to Browser Audio/Visual Alert Dispatch")
    set_notes(s11, "Walk through the end-to-end data pipeline: RTSP TCP ingest, PTS timing, YOLO detection, two-line splitting, grammar beam search, deduplication, and real-time SSE dispatch.")

    # -------------------------------------------------------------
    # SLIDE 12: Evidence Integrity (NFSU)
    # -------------------------------------------------------------
    s12 = prs.slides.add_slide(blank_layout)
    set_bg(s12)
    add_header(s12, "Evidence Integrity: The NFSU Forensic Play", "Legal Admissibility", "12 / 18")

    add_card(s12, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.2),
             "Section 65B BSA Admissibility",
             ["National Forensic Sciences University (NFSU) is on the jury.",
              "AI detections are useless if thrown out of court.",
              "Edge SHA-256 Hashing: Every evidence crop is hashed at the instant of capture.",
              "Signed Manifest: Binds Camera ID, PTS timestamp, operator ID, and case number.",
              "Model Provenance: Every alert records model architecture and ONNX weights hash—refuting claims of AI tampering."],
             highlight=True)

    add_card(s12, Inches(6.8), Inches(1.8), Inches(5.6), Inches(4.2),
             "Tamper-Evident Hash-Chained Audit Log",
             ["Implemented in prahari.registry.audit",
              "Cryptographic blockchain-style hash chain: h_i = SHA256(ts, actor, action, purpose, case_id, params, h_{i-1})",
              "Database Triggers: SQLite explicitly aborts any UPDATE or DELETE operation.",
              "Instant Verification: /api/audit/verify checks the chain from genesis (000...000) to head hash.",
              "Offline Verifiable: Third parties can verify integrity without platform software."],
             highlight=False)

    add_card(s12, Inches(0.8), Inches(6.15), Inches(11.6), Inches(0.9),
             "",
             ["Compliant with Section 65B of Indian Evidence Act / Section 63 of Bharatiya Sakshya Adhiniyam (BSA) 2023."])
    set_notes(s12, "Target the NFSU evaluators. Edge SHA-256 hashing at capture, signed manifests, model weights provenance, and tamper-evident hash chains guarantee Section 65B legal admissibility.")

    # -------------------------------------------------------------
    # SLIDE 13: Privacy & DPDP
    # -------------------------------------------------------------
    s13 = prs.slides.add_slide(blank_layout)
    set_bg(s13)
    add_header(s13, "Privacy by Design: DPDP Act 2023 Compliance", "Rights & Compliance", "13 / 18")

    add_card(s13, Inches(0.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "1. Purpose-Bound Queries",
             ["Zero Anonymous Trawling",
              "Every plate lookup and route trace requires a mandatory declared Legal Purpose and active Case ID.",
              "Officer credentials and search parameters permanently committed to audit ledger.",
              "Satisfies Puttaswamy test of proportionality."],
             highlight=False)

    add_card(s13, Inches(4.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "2. Graduated RBAC",
             ["Four Strict Authority Tiers",
              "Constable: Live wall view & alert acknowledgment.",
              "Investigator: Case-bound search & route tracing.",
              "Supervisor: Watchlist additions & audits.",
              "Auditor: Read-only forensic inspection."],
             highlight=False)

    add_card(s13, Inches(8.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "3. Tiered Retention",
             ["Enforced Data Lifecycle",
              "Text Metadata: 1 Year",
              "Evidence Crops: 90 Days",
              "Raw Video Clips: 30 Days (Edge)",
              "Case Evidence: 7 Years (Cold Storage)",
              "FRS: Off by default; supervisory warrant required."],
             highlight=True)

    add_card(s13, Inches(0.8), Inches(6.15), Inches(11.7), Inches(0.9),
             "",
             ["Strategic Law Enforcement Principle: Privacy by design is what transforms surveillance software into a defensible police evidence platform."])
    set_notes(s13, "Explain DPDP Act 2023 compliance: Mandatory Purpose and Case ID fields prevent anonymous trawling; graduated RBAC and tiered retention enforce proportionality.")

    # -------------------------------------------------------------
    # SLIDE 14: Infrastructure Sizing
    # -------------------------------------------------------------
    s14 = prs.slides.add_slide(blank_layout)
    set_bg(s14)
    add_header(s14, "Infrastructure Sizing for 80,000 Cameras", "Empirical Economics", "14 / 18")

    table_shape = s14.shapes.add_table(7, 4, Inches(0.8), Inches(1.8), Inches(11.733), Inches(4.2))
    table = table_shape.table
    table.columns[0].width = Inches(2.6)
    table.columns[1].width = Inches(2.5)
    table.columns[2].width = Inches(2.8)
    table.columns[3].width = Inches(3.833)

    sz_headers = ["Metric", "Model 4 (Central VMS)", "PRAHARI (Federated)", "Operational Impact"]
    for j, h in enumerate(sz_headers):
        cell = table.cell(0, j)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = COLOR_BLUE_BOX
        for p in cell.text_frame.paragraphs:
            p.font.size = Pt(11)
            p.font.bold = True
            p.font.color.rgb = COLOR_GOLD

    sz_rows = [
        ("Peak WAN Bandwidth", "160 Gbps", "0.45 Gbps", "~360× Reduction in Telco Leased Lines"),
        ("Central Storage (30d)", "51.8 Petabytes", "~210 Terabytes", "240× Reduction in Central SAN/NAS Storage"),
        ("Central GPU Servers", "~2,000 GPUs", "0 Central (166 L4s at Netram)", "Zero central compute bottlenecks"),
        ("5-Year Capex", "₹101 Cr – ₹175 Cr", "₹49 Cr", "₹52+ Cr Immediate Capital Savings"),
        ("5-Year Opex", "₹410 Cr – ₹695 Cr", "₹81 Cr", "Slashes recurring bandwidth fees"),
        ("5-Year Total Cost (TCO)", "₹510 Cr – ₹870 Cr", "≈ ₹130 Cr", "Saves ₹380 Cr to ₹740 Cr for Gujarat")
    ]
    for i, row in enumerate(sz_rows):
        for j, val in enumerate(row):
            cell = table.cell(i+1, j)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = COLOR_CARD_BG
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(10)
                p.font.color.rgb = COLOR_WHITE

    add_metric_box(s14, Inches(0.8), Inches(6.15), Inches(11.733), Inches(0.9),
                   "5-Year TCO: ₹130 Cr vs ₹510 Cr (Steelman Model 4)", "Saves over ₹380 Crore for the Government of Gujarat")
    set_notes(s14, "Walk through the 80,000 camera sizing table. ₹130 Cr vs ₹510 Cr (Steelman Model 4). Emphasize ₹380+ Cr savings for the Government of Gujarat.")

    # -------------------------------------------------------------
    # SLIDE 15: Department Prerequisites
    # -------------------------------------------------------------
    s15 = prs.slides.add_slide(blank_layout)
    set_bg(s15)
    add_header(s15, "Department Prerequisites: Why We Ask for Zero Forms", "Zero Administrative Friction", "15 / 18")

    add_card(s15, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.2),
             "The Traditional Survey Trap",
             ["Asking 26 departments to complete 50-page questionnaires regarding lens focal lengths, mounting angles, and illuminance:",
              "Takes 2 to 3 years of bureaucratic back-and-forth.",
              "Produces 90% missing or inaccurate data.",
              "Department clerks do not possess camera optical specs.",
              "Results in planning paralysis before a single camera connects."],
             highlight=False)

    add_card(s15, Inches(6.8), Inches(1.8), Inches(5.6), Inches(4.2),
             "The PRAHARI Reality",
             ["Exactly one prerequisite: LAN access to a read-only RTSP/ONVIF stream URL.",
              "Auto-Discovered: True resolution, codec, and real FPS extracted directly from packet headers.",
              "Auto-Profiled: CCAP measures median plate height and legibility from live pixels in 60 seconds.",
              "Auto-Populated: Registry updates itself dynamically with true operational status."],
             highlight=True)

    add_metric_box(s15, Inches(0.8), Inches(6.15), Inches(11.6), Inches(0.9),
                   "\"We don't survey cameras. We measure them.\"", "The Single Most Decisive Operational Sentence in this Hackathon")
    set_notes(s15, "Highlight why PRAHARI asks for zero questionnaires. CCAP measures the real frame rate, codec, resolution, and plate legibility within 60 seconds of connection.")

    # -------------------------------------------------------------
    # SLIDE 16: Live Technical Evaluation
    # -------------------------------------------------------------
    s16 = prs.slides.add_slide(blank_layout)
    set_bg(s16)
    add_header(s16, "Live Technical Demonstration Walkthrough", "Live Evaluation Test Case", "16 / 18")

    add_card(s16, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.2),
             "The Live Evaluation Test Case",
             ["All ~50 Cameras Live: Connects to the complete Sentinel catalogue.",
              "Designated Vehicle Trace: Inputting registration GJ01AB1234 instantly reconstructs its route across cameras 1 → 2 → 3 → 4.",
              "Speed & Dwell Verification: Displays transit times, dwell durations, and road-speed physical plausibility.",
              "Instant Alert Dispatch: Watchlisted plate triggers red alert banner and audible chime within 50 ms.",
              "Automated Reports: One-click download of compliance CSV report with 17,900+ timestamped plate detections."],
             highlight=True)

    add_card(s16, Inches(6.8), Inches(1.8), Inches(5.6), Inches(4.2),
             "Live Platform Screens (docs/hld/img/)",
             ["Overview: Real-time camera online/offline health telemetry.",
              "Wall: 50-camera adaptive video wall with green detection boxes.",
              "Map: MapLibre GIS view with interactive coverage-gap overlay.",
              "Alerts: Dedicated Alert and Review queues with evidence crops.",
              "Audit Log: Cryptographic SHA-256 chain verification.",
              "FastAPI OpenAPI Docs: Live at http://127.0.0.1:8000/docs."],
             highlight=False)

    add_metric_box(s16, Inches(0.8), Inches(6.15), Inches(11.6), Inches(0.9),
                   "Cold Start in < 2 Minutes · Fully Offline · Zero External Dependencies", "Run 'python run.py demo' and open http://127.0.0.1:8000")
    set_notes(s16, "Walk through the live demo: 50 cameras connected live, vehicle GJ01AB1234 traced with speed checks, instant alert, and CSV report with 17,900+ plates.")

    # -------------------------------------------------------------
    # SLIDE 17: Statewide Rollout Plan
    # -------------------------------------------------------------
    s17 = prs.slides.add_slide(blank_layout)
    set_bg(s17)
    add_header(s17, "Statewide Phased Rollout Roadmap", "Implementation Strategy", "17 / 18")

    add_card(s17, Inches(0.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "Phase 1: Foundation (M 1–3)",
             ["Deploy Model 1 Central Registry & GIS Dashboard.",
              "Onboard all 17,500 VISWAS police cameras across 34 Netram C3 centres.",
              "Deploy regional GPU aggregators at Netram hubs.",
              "Activate statewide watchlist matching for stolen vehicles.",
              "Immediate police operational value in 90 days."],
             highlight=False)

    add_card(s17, Inches(4.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "Phase 2: Federation (M 4–9)",
             ["Deploy PRAHARI edge containers across 3,300 departmental NVR sites.",
              "Integrate live production APIs with VAHAN and eGujCop (CCTNS).",
              "Generate automated coverage-gap reports for highway blind spots.",
              "Onboard RTO, Civil Supplies, and GSRTC depots.",
              "Full statewide federation complete."],
             highlight=True)

    add_card(s17, Inches(8.8), Inches(1.8), Inches(3.7), Inches(4.2),
             "Phase 3: Intelligence (M 10–18)",
             ["Deploy visual vehicle Re-ID for unreadable plate bridging.",
              "Warrant-backed biometric facial recognition (AFIS/NAFIS).",
              "Federate commercial and private society cameras via opt-in gateway.",
              "Automate CAD dispatch for 112 PCR emergency response vans."],
             highlight=False)

    add_card(s17, Inches(0.8), Inches(6.15), Inches(11.7), Inches(0.9),
             "",
             ["Timeline Advantage: By avoiding hardware replacements, PRAHARI achieves statewide operational coverage in 18 months instead of 5+ years."])
    set_notes(s17, "Present the realistic 18-month rollout roadmap: Phase 1 (VISWAS 17.5k cameras in 90 days), Phase 2 (3,300 departmental sites), Phase 3 (Advanced AI).")

    # -------------------------------------------------------------
    # SLIDE 18: Why PRAHARI Wins
    # -------------------------------------------------------------
    s18 = prs.slides.add_slide(blank_layout)
    set_bg(s18)
    add_header(s18, "Why PRAHARI Wins: 6 of 6 Official Bonus Criteria", "Evaluation Summary", "18 / 18")

    # Table for Bonus Criteria
    table_shape = s18.shapes.add_table(7, 3, Inches(0.8), Inches(1.8), Inches(11.733), Inches(4.2))
    table = table_shape.table
    table.columns[0].width = Inches(3.8)
    table.columns[1].width = Inches(4.5)
    table.columns[2].width = Inches(3.433)

    b_headers = ["Official Hackathon Bonus Criterion", "Delivered Subsystem in PRAHARI", "Verification Evidence"]
    for j, h in enumerate(b_headers):
        cell = table.cell(0, j)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = COLOR_BLUE_BOX
        for p in cell.text_frame.paragraphs:
            p.font.size = Pt(11)
            p.font.bold = True
            p.font.color.rgb = COLOR_GOLD

    b_rows = [
        ("1. Innovative Hybrid Architecture", "Model 1 + 3 + 2 Hybrid; Model 4 refuted with math", "docs/04-architecture-prahari.md"),
        ("2. Advanced Cross-Camera Tracking", "Re-ID appearance bridging + Haversine velocity gating", "prahari/registry/trace.py"),
        ("3. Analytics Beyond ANPR", "CCAP auto-profiler allocates crowd, loitering, intrusion", "prahari/anpr/ccap.py"),
        ("4. Edge Processing & Low Connectivity", "5-Tier Bandwidth Ladder + Tier 0 offline island mode", "prahari/node/manager.py"),
        ("5. Cybersecurity, Privacy & Auditability", "NFSU SHA-256 hash chains + DPDP purpose-bound queries", "prahari/registry/audit.py"),
        ("6. Operational Dashboards & APIs", "Adaptive 50-camera wall, GIS gap reports, OpenAPI docs", "prahari/console/, /docs")
    ]
    for i, row in enumerate(b_rows):
        for j, val in enumerate(row):
            cell = table.cell(i+1, j)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = COLOR_CARD_BG
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(10)
                p.font.color.rgb = COLOR_WHITE

    add_metric_box(s18, Inches(0.8), Inches(6.15), Inches(11.733), Inches(0.9),
                   "PRAHARI: Move Meaning, Not Megabytes", "Safer Gujarat, Stronger Tomorrow · Ready for Questions")
    set_notes(s18, "Conclude by reviewing the 6 official bonus criteria: PRAHARI delivers 6 of 6 in working code. Conclude with: 'Move meaning, not megabytes. Thank you.'")

    # Save presentation
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    prs.save(OUTPUT_PATH)
    print(f"Successfully generated PRAHARI presentation: {OUTPUT_PATH}")


if __name__ == "__main__":
    create_deck()
