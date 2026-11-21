# Event day plan (rules posted Nov 21)

The official builder guide changes several parts of `BUILD_PLAN.md` (pre-event; kept in the private planning repo). This file is the current plan for the day. Where the two disagree, this one wins. The pipeline design, mover rules and verifier checks in BUILD_PLAN.md still stand.

The step-by-step build list, with done-checks for each track, is in [BUILD_STEPS.md](BUILD_STEPS.md).

## Rules that bind us

| Rule | What it means for us |
|---|---|
| Build in one of two problem statements | We are in **Problem Statement Two: Element 119** (video, images and generated media as the core) |
| Use at least two Gemini 4 models, each with a clear job | See "Model jobs" below |
| Element 119 says to use the Decisions API | It is also named in 20% of the score |
| Must go beyond a text box | Phone video in, 3D van and generated image out |
| Not allowed: demos that only run on scripted inputs | The live demo runs on footage filmed in the room, not our prepared clip |
| Not allowed: evaluations made only of examples written to pass | Test set comes from rooms we did not prepare |
| Repositories must be public | Build in a fresh public repo, not this one |
| Demo may only highlight what was built during the hackathon; new work only | Disqualification risk. See "Compliance" |
| Anti-projects include "Image Analyzers" and "any project where a dashboard is the main feature" | Lead with the packing plan and the van loading, never the item list or stat tiles |
| Submission due 5:00 PM with a 1-minute demo video | Record by 4:30 |
| Round one: 3-minute live demo plus 2 minutes Q&A | Script below |

Hacking runs 10:30 AM to 5:00 PM: 6.5 hours.

## Our answers to Element 119's three questions

- **Hardest input we can throw at it:** a cluttered room filmed handheld, with closed closets and partly hidden furniture, plus several rooms in one request.
- **What raw video gives that a text description loses:** the count and size class of every item, how full the shelves and closets are, and which items are fragile or awkward. Nobody writes that list accurately by hand, which is why bedroom-count calculators are wrong.
- **How far we pushed before it broke:** keep a running failures log during the build (see "Evaluation") and show the before and after.

## Demo scenario: move this hackathon to Penn Station

The product is for people moving home. The demo shows it on input nobody prepared: we photograph the hackathon venue during the event and plan the move of everything in it to NY Penn Station.

- **Source:** photos and clips of the venue taken today: tables, stacked chairs, monitors, AV and whiteboards. The judges see their own room inventoried.
- **Destination:** Penn Station's LIRR concourse. Reference photos and clips are in `data/NYPenn/` in this repo. They were taken before kickoff, so we list them in the build repo's README as reference media brought in.
- **The line to land:** "This hackathon fits in N 26-foot trucks, M boxes, 0 rule violations."

What this changes in the build:

| Change | Where | Notes |
|---|---|---|
| Venue items in the catalog | Track B, 10:30 | Folding and banquet tables, stacking chairs, monitors, projector, podium, whiteboards. Treat a stack of chairs as one item so the packer stays fast |
| Fleet sizing | Track B solver | Answer "how many trucks of which size", not only "the smallest truck that fits". Fill one truck, then start the next |
| Unload plan | Track B | Unload order is the load order reversed, per truck. No new solver work |
| Arrival render | Nano Banana 2.1 | One illustrative image of the venue's contents set up in the concourse, using the Penn Station photos as references. Labelled illustrative. Gemini Omni Flash clip only if far ahead |

Out of scope: computing where each item goes inside Penn Station. A floor-plan placement step is a second product; the render covers the destination.

The home case still opens the pitch in one line. The wifi fallback is unchanged: a cached run, announced as such (see the demo script).

## Model jobs

Each model needs a job a judge can repeat back. Confirm model IDs, access and limits in AI Studio at kickoff; the notes on Neon, Hydrogen and the Decisions API come from third-party write-ups, not Google's docs.

| Model or API | Job | Why this one |
|---|---|---|
| `gemini-4-hydrogen` | Watches each room video and returns the structured inventory | Fast tier; one call per room, run in parallel |
| `gemini-4-neon` (or `gemini-4-carbon` if access is solid) | Plans the pack: item-to-box assignment, strategy choice, reading verifier violations and revising | The reasoning-heavy step |
| Decisions API (Gemini Decision 1) | Structured yes/no and multiple-choice calls on the footage: is this closet full, is this item fragile, is this the same sofa seen earlier, does the plan look loaded as specified | Built for structured questions about an input, and accepts video and images |
| Managed Agents | Parallel sandboxes each run a packing strategy with the solver; best verified plan wins | The $5,000 side prize |
| Nano Banana 2.1 | One illustrative image of the packed van | Labelled illustrative; the 3D view is the plan |

If time is short, the minimum that satisfies the rule is Hydrogen for inventory, Neon for planning, and the Decisions API for the gap questions.

## Compliance

- **Fresh public repo.** [TallGibbs/Pack-It-Up](https://github.com/TallGibbs/Pack-It-Up) was created at 9:20 AM with a scaffold commit of docs and empty folders, no code, and its README says so. All code goes in after 10:30 so the commit history is the evidence of what was built today. Commit often.
- **Do not copy in the practice 3D demo.** Rebuild the van view today. It is a small amount of three.js and Gemini can write it.
- **Reference data.** `plan/data/item_catalog.csv` and `plan/data/trucks.csv` were prepared before the event. Either regenerate them today, or bring them in and say so in the new repo's README. Ask in Discord #questions which the organizers prefer, and do the stricter thing if there is no answer.
- **README disclosure in the new repo.** State plainly: research and planning were done beforehand, all code was written at the event, and list anything brought in (open-source libraries, any reference tables).
- **No home footage in the repo.** Add `demo_videos/` and `*.mp4` to `.gitignore` in the first commit.
- **No photos of people in the repo.** The Penn Station shots show identifiable strangers, and venue shots will show other hackers. Keep raw photos and clips in a git-ignored `media/` folder (also ignore `*.jpg`, `*.jpeg`, `*.heic`). Show them in the demo, don't commit them.
- **Penn Station reference media** was captured before kickoff. List it in the README's "Brought in" section.
- **Rights.** Use only our own footage, open-source libraries with their licences, and published truck dimensions.
- **Keys.** `.env` only, git-ignored, from the first commit. The temporary DeepMind keys never go in chat, commits or screenshots.
- **Swappable models.** All model calls go through `backend/llm/` so jobs can move to other providers after the event. See [BUILD_STEPS.md](BUILD_STEPS.md#model-provider-layer). The demo runs on Gemini 4 only.
- **Add every team member** on the submission page and check the video link opens in a private window.

## How we score on each criterion

| Criterion (round one weight) | What we show |
|---|---|
| Live demo (35%) | Film a corner of the judging room on a phone, upload it, and get a packed van within the 3 minutes. Let a judge add or remove an item and re-solve |
| Proof it works (25%) | The verifier (the plan the agent checks its own output against), the baseline comparison, and the failures log |
| Creativity (20%) | Packing a real home into a real truck from handheld video, with a checked load order. Name the prior art and what it lacks |
| Gemini 4 and Decisions API use (20%) | Three clear jobs on screen: Hydrogen sees, Neon plans, Decisions answers. Managed Agents compete |

Round two uses the same criteria with equal weights, so proof and model use matter more on stage.

## Evaluation

This is 25% of round one and is cheap to build if we start early.

- **Baseline A, a single model call:** ask one model to output a full packing plan with coordinates for the same inventory. Run it through our verifier and count overlaps, out-of-bounds items and unsupported items.
- **Baseline B, how people do it today:** the bedroom-count truck size from the rental sites.
- **Our system:** the same inventories through agents plus solver, scored by the same verifier.
- **Test set we did not prepare:** footage filmed at the venue today (lobby, kitchen area, a meeting room), and rooms filmed by people outside the team if we can get them. Keep our own prepared clip out of the reported numbers.
- **Inventory accuracy:** for two or three venue clips, hand-count the items and report found, missed and double-counted.
- **Failures log:** a `FAILURES.md` in the new repo. One line per failure: input, what went wrong, what we changed. Judges ask for this directly.

One results table on screen is enough: rule violations per plan and percent of valid plans, baseline against ours, with the number of test rooms stated.

## Three-minute demo script

| Time | What happens |
|---|---|
| 0:00-0:20 | The problem in one line: self-movers guess their truck and their packing. "To prove it on input we didn't prepare, we're moving this hackathon to Penn Station." Start the upload of venue photos taken a minute ago |
| 0:20-0:50 | Inventory of the room appears. A Decisions API gap question pops up ("is that cabinet full?"); answer it live |
| 0:50-1:40 | Agents compete on packing strategies. The verifier score climbs. The winning plan loads into the 3D trucks item by item: "N 26-foot trucks, M boxes, 0 violations" |
| 1:40-2:00 | Arrival: the unload order at Penn Station and the illustrative render of the venue set up in the concourse. Scan one printed box label with a phone: its contents and destination appear. (If A6 is built, show a photo of a marked box identified with no QR instead) |
| 2:00-2:20 | A judge changes something (add a piano, switch to smaller trucks). Re-solve; show the check that fails or passes |
| 2:20-2:50 | Results table against the baselines, and one honest failure with its fix |
| 2:50-3:00 | Which model did which job, in one sentence |

Have the prepared clip's cached run ready only as a fallback if venue wifi fails, and say so if we use it.

## One-minute video

Screen recording with voice: clip going in, inventory, agents and score, van loading, results table. Show only things built today. Record at 4:15, upload by 4:40.

## Timeline

| Time | Track A: ingestion and analysis (Chris) | Track B: packing plan and output (George) |
|---|---|---|
| 10:30-11:00 | Keys from the DeepMind accounts, schema agreed, model provider layer. Photograph the venue for the demo scenario | Hand-written sample venue inventory; venue items added to the catalog |
| 11:00-12:30 | Hydrogen: room video to inventory JSON | Solver and verifier on the sample inventory, with fleet sizing |
| 12:30-1:00 | Film three venue clips for the test set | Three.js truck view from solver output |
| 1:00-1:30 | Lunch; join the two tracks end to end | |
| 1:30-2:45 | Decisions API gap questions; review UI | Neon planning loop; Managed Agents runs |
| 2:45-3:45 | Run baselines and the test set; write FAILURES.md | Score display; load animation; re-solve on edit; QR box labels and print page (B10) |
| 3:45-4:15 | Results table on screen; README with disclosure. Box recognition without QR (A6) only if the core is done | Penn Station arrival render; unload order view; print the demo labels; polish |
| 4:15-4:45 | Record and upload the 1-minute video | Rehearse the live demo twice on a fresh clip |
| 4:45-5:00 | Submit: public repo, video, all team members | |

Cut order if we run late: box recognition without QR (A6), then the Penn Station arrival render (keep the unload order, which is free), then the QR labels (B10), then the judge-edit re-solve, then Managed Agents parallelism (fall back to one agent run). Never cut the second model, the Decisions API call, the verifier, or the baseline table.

## Questions judges are likely to ask

- What was built today, and what did you bring? (Point to the README disclosure and commit history.)
- Why two models rather than one? (Speed and cost on perception, reasoning on planning; show the single-call baseline.)
- How accurate is the inventory? (Give the hand-count numbers and say where it misses.)
- What happens with items that are not boxes, such as a bike or a lamp? (Treated as cuboids with upright and no-stack flags; say this is a simplification.)
- Is the generated image the plan? (No. The 3D view is computed; the image is illustrative.)

## Open questions for the organizers

- Is reference data prepared beforehand acceptable if disclosed?
- Does the Managed Agents prize require a specific agent or model?
- ~~Are credits or pre-provisioned keys being handed out?~~ Answered: DeepMind emails temporary AI Studio accounts with API keys already created, usable in Antigravity too.
- Can the live demo use footage filmed in the judging room?

## Optional: Shopify bonus track

A "buy these boxes" list through shop.dev, generated from the box counts. Only if we are ahead at 3:00 PM.
