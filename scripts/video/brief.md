# Brief for the video's narration and cards

Input to the Gemini job `video_script` (`python -m scripts.video.build --write-script`). The facts are in `scripts/slides/brief.md`, which the build sends along with this file; use no number that is not there. This file says what is on screen in each shot and what the narration should cover. It holds no finished sentences: Gemini writes the lines and the cards.

## The video

- 60 seconds, 8 shots, one narrator (a calm, warm text-to-speech voice). Real screen recordings of the app, captions of the narration at the bottom of every shot.
- Viewers: hackathon judges. They want to see what was built today and which Gemini models do what.
- Tone: a person explaining their project to friends. Short, concrete, plain words. No hype ("revolutionary", "seamless", "unlock", "effortless", "game-changing").
- The voice speaks about 2.4 words a second. Each line has a hard word limit; shorter is fine.
- Write numbers in the spoken lines as words ("sixteen", "three"), so the voice and the captions agree. Cards may use digits.

## Shots

| Shot | Seconds | On screen | The line covers | Max words |
|---|---|---|---|---|
| S1 | 6 | A 4 s generated clip of boxes being loaded into a truck, then the title card | The problem: people moving themselves guess the truck size; this project counts instead | 10 |
| S2 | 8 | Phone, capture page: two rooms with a clip and a photo each, the footer "52 items + 16 boxes in 2 rooms" | You film each room; Gemini 4 Hydrogen lists every item with size, weight and handling | 17 |
| S3 | 9 | Phone, review page: the answered questions, one "Answered by the Decisions API" | The Gemini Decisions API settles what the footage leaves unclear and asks the person only when it is unsure | 18 |
| S4 | 6 | Phone, review page item list ending on an upright piano "added by you", Move / Stays / Sell / Toss | The person checks the list: counts, what stays, what was missed | 11 |
| S5 | 8 | Laptop, 3D plan: header "2 × U-Haul 26 ft · 16 boxes · 0 rule violations", the load playing piece by piece | A 3D solver packs the trucks and a checker tests every piece against moving rules (name a few) | 15 |
| S6 | 9 | Laptop, "Plan with Neon" pressed, Neon's rounds appear, header changes to one 26 ft truck, score 95.2, 0 violations | Gemini 4 Neon reads the checker's result and changes the plan: two trucks become one, no rule broken | 20 |
| S7 | 9 | 3 s of the models page, then the results card | The measured result for our plans against the stock packer, saying "mostly venue rooms" | 19 |
| S8 | 5 | The end card | Built today with Gemini; invite the viewer to try it on their phone | 9 |

Also write `S6_alt`: the S6 line to use if the page does not end on one truck (say that Neon changes the solver settings to raise the score, nothing about the truck count). Max 16 words.

## Cards

Three cards, each a complete HTML page designed at 1920×1080 CSS pixels: `title`, `results`, `end`. Rules for all three:

- The bottom 150 px stay empty: the build draws the caption band there.
- Self-contained: no external scripts or images. The only image allowed is `qr.png` (the QR code for the demo address), on the end card only. Google Fonts allowed, with a system-font fallback.
- Large and readable on a phone screen: body text at least 40 px, headlines much larger.
- One consistent look across the three, a clean modern Google style; your own design.
- `title`: the name, a one-line promise, "Gemini 4 NYC hackathon · Nov 21, 2026".
- `results`: plans with no rule broken, one per set of footage, ours against the stock `py3dbp` packer, with the caveats in small text: mostly venue rooms not homes, same checker for both, the one rule relaxed for small moves at 15:30 (before it, 2 of our 24 plans broke it), source `eval/RESULTS.md`.
- `end`: the QR code, `packitup.temperedanalytics.com`, `github.com/TallGibbs/Pack-It-Up`, and a small line: narration by Gemini text-to-speech, opening clip generated with Gemini Omni 1.2 Flash, script and cards written by Gemini 4 Carbon.
