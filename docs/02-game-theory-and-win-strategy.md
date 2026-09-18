# Part 2 — Game Theory: How This Is Won

## 1. The game as defined by the rules

**Players:** Category 1 (student teams + small/medium startups incl. DPIIT-recognised) and Category 2 (large startups, companies, system integrators).

**Structure — a two-stage elimination game:**

```
PHASE 1 — Sandbox Round (Rs 18,00,000)          submission deadline 28 Sep 2026
  Category 1: 1st Rs 4L | 2nd Rs 2L | 3rd Rs 1L
  Category 2: 1st Rs 5L | 2nd Rs 3L | 3rd Rs 2L
  + 4 consolation awards Rs 25,000 each (across both categories)
  -> Top 3 from EACH category advance = 6 finalists

PHASE 2 — Production Round / Grand Finale (Rs 31,00,000)   12-13 Oct 2026
  Category-blind. Live feeds, production scale.
  1st Rs 16L | 2nd Rs 8L | 3rd Rs 7L
  + Rs 50,000 consolation x 3 non-podium finalists
  + Rs 50,000 Special Jury Award (discretionary, "outstanding aspect of any solution")
```

### 1.1 The most important line in the entire rulebook

> "**The Top 3 teams from each category** will receive Phase 1 prizes and advance to the Grand Finale as the six finalist teams." — /phases

**Each category has its own three guaranteed seats.** In Phase 1 you never compete against Category 2. You compete against student teams and small startups.

> ⚠️ **Contradiction to resolve before you register.** FAQ #48 says instead: *"The six highest-ranked participants **across both categories** qualify for Phase 2."* That is a pooled ranking and a completely different game. The `/phases` page is the structured, authoritative one, but **email sentinel.hackathon@gujarat.gov.in and get this in writing.** If it is pooled, Category 1's protection evaporates and strategy shifts materially.

### 1.2 Category choice is the single highest-leverage decision you will make

Assuming `/phases` is correct:

| | Category 1 | Category 2 |
|---|---|---|
| Field | Student teams, small/medium startups | TCS, L&T, Honeywell, Vehant, Staqu, Videonetics, Allied Digital, regional SIs |
| Typical resources | 2–6 people, weeks | Dedicated teams, existing shipped VMS/ANPR products, reference deployments |
| Finale seats | **3** | **3** |
| P(top 3) for a strong small team | **High** | Low |
| 1st prize | ₹4L | ₹5L |

You pay ₹1,00,000 of Phase-1 prize money for a **dramatically** higher probability of reaching the ₹31,00,000 category-blind finale. That is not a close call.

> **Dominant strategy: if you are eligible for Category 1, enter Category 1.**
> DPIIT recognition takes days–weeks and is free — if you have a registered entity and no DPIIT certificate, start that application today; it is the cheapest strategic asset available to you.

---

## 2. Model the opponents

A hackathon converges on a modal strategy. Predict it, then refuse to compete there.

**What ~85% of teams will submit:**
1. Model 4 (sounds most impressive) or Model 2 (easiest)
2. YOLOv8 + EasyOCR/PaddleOCR → ANPR
3. React dashboard: a map, a 2×3 video grid, an alerts table
4. Demo on **4–9 cameras** of the ~50
5. `WHERE plate = ?` exact-match watchlist
6. A slide claiming 80,000-camera scale with a Kubernetes diagram and **zero measurements**
7. Nothing on security, privacy, audit, evidence integrity, or cost
8. Half the video panels showing corridors with no vehicles and no analytics running

**Where they will visibly fail, on stage:**
- Only a handful of cameras onboarded → looks like a prototype
- Designated-vehicle trace returns 2–3 hits → looks unconvincing
- One OCR character wrong → zero watchlist alerts → the money moment fails
- Scale claims unsupported → the technical jury discounts everything
- Dead panels on non-traffic feeds → looks broken

---

## 3. Find the uncontested dimensions

Score is a weighted sum over seven published criteria. Compete where marginal effort buys the most marginal score — i.e. where competitors are weakest and the criterion is explicit.

| # | Criterion | Field strength | Your leverage | Priority |
|---|---|---|---|---|
| 1 | Successful Test Case (gov feed) | Medium | **Onboard all ~50, not 6** | 🔴 **HIGHEST** |
| 2 | Solution Presentation | Medium-high | Framing + the 400:1 number | 🟠 High |
| 3 | Solution Architecture / HLD | **Weak** | Genuine federated design w/ reasoning | 🔴 **HIGHEST** |
| 4 | Working Platform maturity | Medium | Runs unattended, degrades gracefully | 🟠 High |
| 5 | Video Analytics Output | Medium | Trace recall + per-camera right analytic | 🔴 **HIGHEST** |
| 6 | Scalability & PoC readiness | **Very weak** | **Measured** load test → cost table | 🔴 **HIGHEST** |
| 7 | Submission completeness | Medium | Pure discipline. Free marks. | 🟢 Free |
| B | Bonus | **Very weak** | Hit 6 of 6 named bonus items deliberately | 🟠 High |

### The five asymmetric bets

**Bet 1 — Onboard all ~50 cameras.** *Cheapest large gain in the entire competition.*
The test literally says "~50 cameras." Most teams show 6. A wall of 50 live tiles with per-camera health scores simultaneously maxes criteria 1, 4 and 6 and is instantly legible to a non-technical police audience. **Pure execution, near-zero technical risk, maximum perceptual payoff.**

**Bet 2 — Win the designated-vehicle trace on recall.**
The jury hands you one plate, on stage. Whoever renders the longest credible route owns the room. Confusion-aware matching + Re-ID bridging turns 3 hits into 8–12. *This is the single moment the finale is decided in.*

**Bet 3 — Replace scale claims with measurements.**
Actually run the load test. Publish: *"1 node sustained N streams at M ms p95 on this hardware; therefore 80,000 cameras = X nodes = ₹Y crore capex vs ₹Z crore for central ingest; here is the bandwidth arithmetic."* They **asked** for a cost-benefit analysis. Nobody will do it properly. A jury evaluating a real programme will weight this enormously.

**Bet 4 — Own the criteria nobody touches: security, privacy, evidence integrity.**
- **NFSU is a knowledge partner — a forensic sciences university.** Hash-sealed evidence, signed manifests, chain of custody, tamper-evident audit logs are *their entire discipline*. This is a targeted play at a known evaluator.
- **DPDP Act 2023** is live. A rights-respecting surveillance design — purpose-bound queries, case-ID-tied watchlist lookups, retention policy, immutable audit — is something the state legally needs and no student team will build.

**Bet 5 — Make the mandatory Model 1 registry the crown jewel, not the chore.**
Everyone treats the registry as CRUD and sprints to AI. It is the one component the organisers made **mandatory**, and §4 of `01-decode-and-first-principles.md` shows it is what they actually lack. A registry that *measures its own cameras* answers their literal question — *"what information do we need from departments?"* — with **"nothing, we measure it ourselves."**

---

## 4. Model the judges

Score is not one function. It is four people with different utilities. **Ship one artifact aimed at each.**

| Evaluator | Actually cares about | Your targeted artifact |
|---|---|---|
| **Gujarat Police leadership** | Will it catch criminals? Will it embarrass me? Is it simple to operate? | The 60-second trace demo: plate in → route on a map → alert fires. No jargon. |
| **NFSU** (forensics) | Evidence admissibility, chain of custody, tamper-evidence | Hash-sealed evidence vault + signed export manifest + audit log |
| **DA-IICT** (academic) | Architectural soundness, algorithmic novelty, honest evaluation | The 400:1 derivation, grammar-constrained decoding, measured benchmarks with failure analysis |
| **i-Hub** (startup/scale) | Deployability, cost, rollout realism | Cost model in ₹ crore, phased rollout plan, ops runbook |

**Corollary — legibility is a scoring function.** A judge who does not understand your innovation cannot score it. Every clever thing must have a 10-second plain-language version. Innovation that is not *visible on screen* does not exist.

---

## 5. Sequential game: Phase 1 → Phase 2

Phase 1 prize is *explicitly* a development grant. So Phase 1 is a **signalling game**: you are not proving you built a demo, you are proving you can be trusted to build the real thing.

Consequences:
- Do **not** build a throwaway demo. Build the real system's skeleton and show it running.
- Ship things a demo doesn't need but a deployment does: health monitoring, reconnect logic, API docs, a runbook, an ops dashboard. These are *signals*, and they are cheap.
- Phase 2 is category-blind and against companies with shipped products. Your edge there is **architecture and adaptability**, not polish. Your system must onboard unfamiliar live feeds *on the day, on stage.* Design for that now: **generic onboarding, zero hardcoding.**

> **Hard rule: nothing about the sandbox may be hardcoded.** Read the camera list from `/api/ingest`. Anyone who hardcodes 50 camera URLs dies in Phase 2 when the feeds change.

---

## 6. Minimax: the losing branches, and how to close them

Expected value means nothing if the tail kills you. Rank risks by `P(occurrence) × damage`:

| Risk | Damage | Mitigation |
|---|---|---|
| **Demo fails live (network/feed/GPU)** | Catastrophic → 0 | Runs 100% offline/local. No cloud in the demo path. Pre-recorded fallback video queued and ready. Rehearse a cold start. |
| Feeds down/changed on the day | Severe | Everything driven by `/api/ingest`. Auto-reconnect with backoff. Graceful per-camera degradation — one dead camera must never stall the wall. |
| ANPR misses the designated vehicle | Severe — the money moment | Confusion-aware fuzzy match + Re-ID bridging + operator-assisted "near miss" panel showing ranked candidates. Never return an empty result. |
| Judges don't grasp the innovation | Moderate, silent | One-sentence version of every clever thing. Show, don't assert. |
| Incomplete submission | Fatal, self-inflicted | Criterion #7 is free marks. Checklist in `04-scorecard.md`. |
| Miss the 28 Sep deadline | Fatal | 10 days from today. Submit at T-48h, then keep improving for the finale. |

**The asymmetry:** a flawless architecture with a crashed demo scores near zero. A decent architecture with a flawless demo podiums. **Reliability outranks ambition.** Every feature ships behind a flag that can be turned off in 5 seconds on stage.

---

## 7. The strategic position, in one paragraph

> Enter **Category 1**. Submit a **Hybrid architecture (Model 1 + 3 + selective 2)** and *justify the rejection of Model 4 with arithmetic* — the 400:1 bandwidth ratio. Onboard **all ~50 cameras**, not six. Win the **vehicle-trace moment on recall** using grammar-constrained plate decoding and Re-ID bridging, because exact-string matching is the field's universal failure mode. Replace every scale claim with a **measured number and a ₹-crore cost table**, because the jury is evaluating a real programme and nobody else will. Own **evidence integrity and DPDP-aligned privacy** because NFSU is on the panel and it is uncontested ground. Make the **mandatory registry the crown jewel** — a registry that measures its own cameras answers the question they actually asked. And make the whole thing **boringly reliable**, because on 13 October the only thing that matters is that it works in front of the DGP.
