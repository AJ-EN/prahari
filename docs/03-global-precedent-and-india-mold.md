# Part 3 — Has This Been Solved Elsewhere? Yes. Four Times. Here Is The India Mold.

You asked for solved precedent, re-cast for India. Here it is, with what to take and what to refuse.

---

## Precedent A — **Fūsus / Axon (USA)** — *the closest analogue that exists*

**What they solved:** exactly this problem. Unify a city's fragmented public + private cameras into one real-time operational picture **without replacing any hardware**.

**The mechanism:** a small edge appliance (*FususCORE*) plugs into whatever DVR/NVR a site already has, normalises its streams, and dials out through a secure tunnel to a cloud "Real-Time Crime Center." No new cameras, no new switches, no rip-and-replace. Plus a **community camera registry** where businesses and residents opt in.

**✅ Take:** the edge-normalisation pattern; the outbound-only tunnel; the opt-in private camera registry; "integrate, don't replace."

**❌ Refuse:** the hardware mandate and the cloud dependency. Fūsus assumes good US broadband, municipal budgets, and *one* agency. Gujarat has 26 departments, 1,000 km of dispersion, patchy links in Dahod and the border districts, and a hard cost ceiling.

**🇮🇳 The India mold:** make the node **software-only** so a department can run it on a spare desktop, a ₹30k Jetson, or a VM in the state data centre — no procurement required. Add **disk-backed store-and-forward** so a node in a low-connectivity block keeps working through an outage and syncs later. Keep department **data sovereignty**: video never leaves their premises.

> [Axon Fūsus](https://www.axon.com/products/axon-fusus/unified-interface) · [RTCC in the cloud](https://www.axon.com/resources/real-time-crime-center-in-the-cloud-the-next-generation-of-police-technology)

---

## Precedent B — **UK National ANPR Service (NAS), Leonardo + Home Office** — *the scale template*

**What they solved:** national plate intelligence at a scale larger than Gujarat's target.

**The numbers** (these are your credibility anchors — cite them in the deck):
- **~90 million reads/day**, all UK forces connected, live since Feb 2019
- Four-stage pipeline: **Gateway → Ingest → Screen → Exploit**
- Ingest sustains **12,000 events/sec**
- Screen matches against a **45M+ record** vehicle-of-interest list
- Exploit delivers **sub-millisecond alerts** over **36B+ reads / 70B+ images**
- 12-month retention; enriched with make/model/colour from DVLA (the UK's VAHAN)
- Published **Data Protection Impact Assessment** — a public privacy artifact

**✅ Take:** the four-stage pipeline shape (it maps 1:1 onto our design); the *separation of the real-time hot path from the analytical cold path*; the DPIA as a deliverable. Cite the 90M/day figure to prove metadata-federation is a proven pattern at national scale — this is how you make your architecture look *conservative* rather than speculative.

**❌ Refuse:** the assumption of uniform, machine-readable plates. NAS works partly because UK plates are one standardised font.

**🇮🇳 The India mold:** India's plates are **not** one thing — two-line and stacked two-wheeler plates, hand-painted fonts, HSRP glare, BH-series, vanity, damage and deliberate obscuring. So the UK's "read the plate, then exact-match the hotlist" primitive **must be replaced** by *grammar-constrained decoding + confusion-space matching*. This is the core Indian adaptation and the sharpest technical differentiator available. (See `04-architecture.md` §B.)

> [Leonardo on NAS](https://uk.leonardo.com/en/news-and-stories-detail/-/detail/driven-by-innovation-the-uk-national-anpr-service) · [NAS DPIA (GOV.UK)](https://www.gov.uk/government/publications/national-anpr-service-data-protection-impact-assessment/national-anpr-service-data-protection-impact-assessment-accessible) · [NPCC ANPR Strategy](https://npcc.police.uk/ANPR%20Strategy%202020%20Final.pdf)

---

## Precedent C — **South Korea integrated CCTV control centres (통합관제센터)** — *the governance template*

**What they solved:** the *organisational* problem — cameras "previously operated separately by departments and by purpose" consolidated into district-level integrated control centres, raising operational efficiency and **cutting maintenance cost**. Seoul now runs AI-enabled coverage across all 25 boroughs.

**The mechanism:** statutory. Consolidation sits inside the **Personal Information Protection Act Art. 25** and its Enforcement Decree, with formal construction guidelines. Privacy protection and consolidation arrived *together*, as one package.

**✅ Take:** the pairing. Consolidation **must** ship with its privacy frame or it stalls politically. Also take the "reduces maintenance cost" argument — it is the line that converts a reluctant department head.

**❌ Refuse:** the reliance on a statutory mandate. You cannot legislate in a hackathon.

**🇮🇳 The India mold:** substitute **incentive for mandate**. If a department must be *compelled* to join, adoption takes years. If joining gives them, free and immediately: camera health monitoring they don't have, a gap-analysis map, their own analytics, and reduced AMC disputes — they join voluntarily. **Design the integration so participating is individually rational for each of the 26 departments.** Pair it with **DPDP Act 2023**-aligned controls as the Indian equivalent of PIPA Art. 25.

> [Seoul CCTV Integrated Control Center](https://seoulsolution.kr/en/content/keeping-citizens-safe-seoul-cctv-integrated-control-center) · [Seoul smart public safety](https://english.seoul.go.kr/seoul-policy-archive/smart-public-safety/)

---

## Precedent D — **China: Skynet / Sharp Eyes** — *the anti-pattern, and you should say so*

Full centralisation of video and identity at national scale.

**❌ Refuse entirely — and name the refusal explicitly in your deck.** It is (a) economically impossible at Gujarat's budget, (b) incompatible with the DPDP Act 2023 and Indian constitutional privacy jurisprudence (*K.S. Puttaswamy*, 2017 — proportionality and necessity), and (c) exactly what Model 4 quietly becomes at 80,000 cameras.

**Why say it out loud:** explicitly considering and rejecting the maximalist option, on cost *and* rights grounds, is a maturity signal. It tells a government jury you understand the political and legal envelope they operate in — not just the technology. Very few teams will do this. It costs one slide.

---

## Precedent E — **Detroit Project Green Light / US community camera registries** — *for the private-camera clause*

The problem statement says the system should support viewing of private cameras from *"societies, malls, commercial establishments... wherever feasible and permitted."* That last clause is the organisers admitting they have no consent framework.

**✅ Take:** the tiered opt-in registry — the owner chooses *registered* (police know it exists, request footage manually), *shared-on-request*, or *live-integrated*.

**🇮🇳 The India mold:** DPDP-aligned consent artifact per camera, with scope, retention, revocation, and a full audit trail of every access. Default tier = "registered," **not** live ingest — the proportionate default. This turns a vague clause into a designed, defensible subsystem that nobody else will build.

---

## Precedent F — **What Gujarat already has** (do not propose what exists)

Critical context most teams will miss entirely:

- **VISWAS** (Video Integration & State-wide Advanced Security): **Phase I — 7,000+ cameras** live since May 2022 at ~1,200 junctions across 34 district HQs, 6 pilgrimage centres and the Statue of Unity. **Phase II — 10,500+ cameras** into Surat, Vadodara and 52 municipalities + inter-state entry/exit points, extending to 51 tier-3 cities.
- **34 "Netram"** district-level command & control centres — one per district.
- **ITMS** (Intelligent Traffic Management), **10,000 body-worn cameras**, **19 drone camera systems** already integrated.

**Strategic consequence — this reframes your entire pitch.** The 80,000 figure is not greenfield. It is **VISWAS + the 26 departments' existing estates + private cameras**. Gujarat does not need another command centre; it has 34. It needs the **connective tissue** between Netram centres, departmental VMS estates, and the state databases.

> **Position your solution as the layer that makes VISWAS statewide and multi-department — not as a replacement for it.** Saying "your Netram centres become nodes in this fabric, and VISWAS Phase I/II are onboarded as-is on day one" tells the jury you did your homework on *their* programme. Almost no competing team will know these names. Use them.

> [VISWAS Phase I](https://deshgujarat.com/2022/07/02/7000-cctv-cameras-installed-in-gujarat-under-phase-i-of-viswas-10000-to-be-installed-in-phase-ii/) · [Phase II](https://deshgujarat.com/2023/12/15/10500-cctv-cameras-being-installed-across-gujarat-under-viswas-project/) · [MyGov success story](https://blog.mygov.in/citizens-success-story-of-video-integration-and-state-wide-advance-security-viswas/) · [VISWAS tender (GIL)](https://gil.gujarat.gov.in/tendercms/TenderDocs/2022113103811611.pdf)

---

## The synthesis

| Source | Take | Refuse | India mold |
|---|---|---|---|
| Fūsus/Axon | Edge normalisation, outbound-only tunnel, private registry | Hardware mandate, cloud dependency | Software-only node; store-and-forward; department data sovereignty |
| UK NAS | 4-stage pipeline, hot/cold split, DPIA, 90M/day proof | Uniform-plate assumption | Grammar-constrained decode + confusion-space matching |
| South Korea | Consolidation + privacy as one package; cost-saving argument | Statutory mandate | Incentive-compatible voluntary onboarding + DPDP alignment |
| China | — | Everything | Name it and reject it on cost + *Puttaswamy*/DPDP grounds |
| Detroit/US | Tiered private-camera opt-in | Ad-hoc consent | DPDP consent artifact, default tier = "registered" |
| **Gujarat VISWAS** | **It already exists** | Proposing a replacement | **Be the connective tissue, not the replacement** |
