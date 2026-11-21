# 3-Minute Live Pitch & 5:00 PM Prep Cue Cards (Phone-Sized)

Open on phone during rehearsal or judging: `/app/pitch.html` (or read below).
**Format:** 3:00 live demo + 2:00 Q&A. **Rule:** Live unrehearsed input only — lead with the 3D truck & Penn Station load plan, never slides or a dashboard.

---

## 👤 CHRIS — Glanceable Phone Card

### 1. Opening Hook (`0:00 – 0:12`)
- **My move story:** Rented a truck **too big** → open floor space → **things slid & broke**.
- Bedroom calculators guess blind; nobody checks how cargo actually braces.
- *(Pass to George for his WNY → UES tight-truck half of the hook.)*

### 2. Live Phone Capture (`0:25 – 0:55`)
- Film / pick **live judging-room clip** on `packitup.temperedanalytics.com`.
- **Talk while filming:** *"these chairs stack"*, *"the plants stay"*.
- Point out **Gemini 4 Hydrogen** extracting items + sizes + **spoken quotes** in parallel.
- Answer **1 live Decisions API card** (`gemini-decision-1` auto-settled the high-confidence ones in ~200 ms, 0 output tokens).
- Tap **"Plan the truck load →"** *(hand to George)*.

### 3. Proof & Honest Failure (`2:25 – 2:45`)
- **Baseline vs Ours:** Single-call LLM plan overlaps/floats items; our solver + verifier = **0 rule violations**.
- **Unprepared eval:** Hand-counted Malin lounge + logged real fixes in `FAILURES.md` (closed cabinets assumed empty & asked; open-frame weight fix).

---

## 👤 GEORGE — Glanceable Phone Card

### 1. Opening Hook (`0:12 – 0:25`)
- **My move story:** Super short drive (**West New York, NJ → Upper East Side**) — a **smaller, right-sized truck** makes tight NYC streets & turns way easier to maneuver.
- **Too big** = broken stuff + stuck in NYC traffic; **too small** = items left on the curb.
- **Live test:** Moving **this hackathon room** into **6 storefronts at NY Penn Station**.

### 2. 3D Fleet, Physics & Penn Station (`0:55 – 1:55`)
- **Right-sized U-Haul fleet** (`10 / 15 / 20 / 26 ft` downsizing): snug load so nothing slides, compact enough for NYC streets.
- **Physics Verifier (`verify.py`):** `0 violations` — `>=75%` base support, 0 overlaps, upright/on-edge rules, fragile top-protection, `40–60%` left-right CoG balance.
- **Neon + Managed Agents:** Compete on packing strategies to repair violations.
- **Penn Station 6-Store LIFO Unload:** Stop 1 (*Merch Kiosk*) loaded last by rear door → Stop 6 (*Concourse*) loaded first by cab, all clearing store doorways.
- **Outputs:** Scan **offline QR box label** (holds full manifest, no wifi needed) + **Nano Banana 2.1** arrival visual *(badged illustrative)*.

### 3. Judge "What-If" + Model Close (`1:55 – 2:25` & `2:45 – 3:00`)
- **At `1:55`:** Ask judge to **add a piano** or **force a 10-ft truck** → 1-tap re-solve → **Move Plan Judge (`gemini-decision-1`)** gates safety/rubrics & escalates to **Neon**.
- **At `2:45` (Closing line):**
  - **Hydrogen** sees & hears the room.
  - **Neon + Managed Agents** plan & optimize the pack.
  - **Nano Banana 2.1** previews arrival.
  - **Decision 1** routes gap questions & judges the final load.

---

## ⚡ 2-Minute Q&A Quick Hits

- **What was built today vs brought in?** All code written after 10:30 AM (see public git commits); `item_catalog.csv` & Penn Station reference photos disclosed under *Brought in* in `README.md`.
- **Why not one model call?** Hydrogen is fast/parallel on video+audio; `gemini-decision-1` gives calibrated probabilities in ~200 ms with 0 output tokens; Neon reasons over 3D verifier violations. Single-call LLM baseline fails physics checks.
- **Is the arrival image the plan?** No — the 3D coordinates & verifier math are the plan; Nano Banana is clearly badged illustrative.
- **Non-box items (lamps, bikes, tables)?** Modeled as oriented bounding cuboids with `must_stay_upright`, `load_on_edge`, `disassemble`, and `light_only` stacking rules.

---

## 🕔 Pre-5:00 PM Submission Checklist

- [ ] **4:15 PM:** Record **1-minute demo video** (screen + voiceover, showing only features built today).
- [ ] **4:35 PM:** Open video link in an **incognito window** to confirm public access.
- [ ] **4:40 PM:** Confirm GitHub repo is **public**, `.env` & raw photos/videos are **not committed**, and **both Chris & George** are listed on the submission form.
- [ ] **4:45 PM:** Run **two full 3:00 timed rehearsals** on a fresh room clip using `/app/pitch.html`.
- [ ] **4:55 PM:** Submit before **5:00 PM** sharp.
