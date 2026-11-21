# Submission and round-one judging plan

Draft written at 14:05 on Nov 21 for Chris and George to agree. Nothing here is decided until it is in [memory/decisions.md](../memory/decisions.md). It replaces the "One-minute video" and "Three-minute demo script" sections of [EVENT_DAY_PLAN.md](EVENT_DAY_PLAN.md) where they differ, because those assumed agents, a render and a baseline table that are not built.

## What we can show today

| Built and live on `main` | Not built |
|---|---|
| Phone capture page: photos and clips per room, progress per file | Competing agents (B7) |
| Inventory from Gemini 4 Hydrogen, with sizes, weights and box estimates | Penn Station arrival render (B9) |
| Gap questions answered by the Decisions API, and by the person on the phone | QR box labels print page (B10) |
| Review page: quantity, Move / Stays / Sell / Toss, add an item | A single-model-call packing baseline |
| 3D truck view from the Python solver, with the verifier's violation count and a what-if re-solve | |
| Model-use page: which model did which call | |
| "Plan with Neon" (since 14:14): Gemini 4 Neon reads the checker's result and changes the solver settings | |
| `FAILURES.md` with 60 rows; one hand count (Malin, recall 67-75%) | |

The video and the live demo show only the left column.

## The submission form

| Field | What we enter |
|---|---|
| Team name | Pack It Up |
| Team members | Chris and George. Only Chris is on the form now; George has to be added with the + button |
| Project description | Draft below |
| Public GitHub repository | https://github.com/TallGibbs/Pack-It-Up (checked public at 14:00) |
| 1-minute demo video | YouTube link, unlisted. Open it in a private window before submitting |
| Problem statement | Two: Element 119. In Chris's screenshot of the form this option looks dimmed; check it can be selected |

**Description draft (about 90 words):**

> Pack It Up turns a phone walk-through of your home into a move plan. Film each room; Gemini 4 Hydrogen reads the footage and lists every item with its size, weight and handling needs. The Gemini Decisions API settles what the footage leaves unclear (is this the same sofa, is that cabinet full) and asks you only what it can't answer. A 3D packing solver then loads the trucks, a checker scores every placement, and Gemini 4 Neon reads that score and improves the plan, so you get the truck count, box count and load order. Judges can try it on their own phone: packitup.temperedanalytics.com

Cut the last sentence if the laptop will be off when the form is read.

## One-minute video

Screen recording of the phone and the laptop, with one voice. Everything on screen was built today.

| Time | On screen | Said |
|---|---|---|
| 0:00-0:08 | Phone filming a corner of the venue | Self-movers guess their truck size. We count instead |
| 0:08-0:22 | Capture page: files uploading, items appearing | Hydrogen reads each photo and clip into an inventory |
| 0:22-0:32 | A gap question answered on the phone | The Decisions API answers what it can and asks about the rest |
| 0:32-0:48 | Review edit, "Plan the truck load", "Plan with Neon", trucks loading in 3D, 0 violations | A solver packs it, a checker scores it, and Neon improves the plan |
| 0:48-0:55 | Model-use page, then the results table | Which model did which job, and how accurate it was |
| 0:55-1:00 | End card: repo address and the QR code | |

Record at 4:00, upload by 4:30. Use a move filmed today at the venue, not a prepared clip.

## Round one: three minutes live, two minutes of questions

| Time | What happens |
|---|---|
| 0:00-0:20 | Opening slide with the QR code. One line on the problem. "Scan this and film your corner of the room while we talk." Start our own upload |
| 0:20-1:00 | Inventory appears on the laptop. Answer one Decisions API question live |
| 1:00-1:50 | Review page: toss one item, add a piano. Plan the truck load: trucks, pieces, 0 violations |
| 1:50-2:20 | A judge picks a what-if change; re-solve |
| 2:20-2:50 | Results table and one failure from `FAILURES.md` with its fix |
| 2:50-3:00 | Closing slide: which model did which job, and the QR code again |

If the tunnel or wifi fails, open a move from earlier today on the laptop and say that is what it is.

## The QR code for judges

- **Where it points:** `https://packitup.temperedanalytics.com/`. It opens the name page, then capture. Each person who scans gets their own move (decision 12:19).
- **The image:** [demo_qr.png](demo_qr.png), made at 14:20 with the `qrcode` library. A second library read it back as the address above. Not yet scanned by a phone from a projected slide. If we later want a landing page with two choices, change what the address serves; the image stays the same.
- **Where it appears:** the opening and closing slides, the video's end card, and a printed sheet on the table. Put it in the slides as a saved image, so it still shows if the wifi drops.
- **What to tell judges:** three photos or a clip under 20 seconds; each file takes about 30 seconds to read; clips over 95 MB are refused.
- **A second link for judges who don't want to film:** a finished move opened straight in the review page and the 3D view. Pick one whose photos show no people, because the review page shows thumbnails.

### What has to hold for judges to use it

| Risk | What we do |
|---|---|
| The tunnel stops without anyone noticing. At 13:59 the address returned 530 because `cloudflared` had exited; the API was still up | Make `run_demo.ps1` restart the tunnel when it exits, and check `/health` before each demo |
| The laptop sleeps or closes while we present on it | Keep-awake on, lid open, on power. The address works only while this laptop runs |
| Several judges upload at once on the event API key | Not measured. Two phones at once worked at 13:47 with cached photos only |
| `GET /analysis/runs` lists every move's id to anyone | Leave it, or hide it behind a setting before the QR goes out |
| A move started by a judge shows other hackers in its photos | Photos stay in `runs/` on the laptop, which is git-ignored |

## Before we submit, in order of points at stake

1. **Results table (proof, 25%).** Done at 14:50: [eval/RESULTS.md](../eval/RESULTS.md), built by `python eval/results_table.py` from the 24 moves on the demo laptop (14 different sets of footage). One per set: the stock `py3dbp` packer's plan broke no rule on 3 of 14, ours on 13 of 14; U-Haul's bedroom rule picked too small a truck on 7 of 14; Neon raised the score on 9 of 14. Venue lounge against the in-person count: recall 67% to 75%. Not built: a single-model-call baseline. Run the script again before submitting if new moves should count.
2. **A model in Track B (model use, 20%).** Done at 14:14: "Plan with Neon" is live (decisions.md 14:14). On move 133201 it goes from two 26 ft trucks (91.5) to one (95.2).
3. **README.** Status still says Track B is being built. Add what the app does now, the results table, and whether `data/trucks.csv`, `penn_zones.csv` and `sample_venue.json` were brought in.
4. **Tunnel restart** in `run_demo.ps1`.
5. **Slides and QR image.** Eight slides since 14:55: cover with the code, how it works, four "in action" slides with screenshots of move 133201 (film, check the list, Neon plans the load, which model did what), what we measured, try it yourself. The code is bottom right on every slide between the cover and the close. The screenshots are in the deck only, not in git. Chris has them as a private Claude deck that downloads as PowerPoint or PDF. The baseline line on the "what we measured" slide is a placeholder until the results table exists.

## Timeline

| Time | Chris | George |
|---|---|---|
| 2:10-3:30 | Results table; tunnel restart; README | B6; push everything to `main` |
| 3:30 | Stop adding anything the video shows | |
| 3:30-4:00 | Slides with the QR code; film a fresh venue move for the video | Rehearse the 3D part |
| 4:00-4:30 | Record and upload the video; check the link in a private window | Create a Cerebral Valley account if needed, so he can be added to the form |
| 4:30-4:40 | Submit the form | |
| 4:40-5:00 | Rehearse the live demo twice | |

## To decide

- Does the QR code open a new move (as now), or a page that offers both "film your own" and "look at a finished move"?
- Slides as a page in the app (`frontend/`), or Google Slides?
- Who records and voices the video?
- Ask an organizer: can the live demo use footage filmed in the judging room, and can the form be edited after it is submitted?
