# Facts for the Pack It Up judging deck

This file is the input to the Gemini job `slides` (scripts/slides/build.py). It holds facts, numbers and the slide order. It holds no slide copy and no design: Gemini writes both. Every number on a slide must come from this file.

## The product

- Name: Pack It Up. Built at the Gemini 4 NYC hackathon (Cerebral Valley × Google DeepMind), Nov 21, 2026. Problem Statement Two: Element 119.
- Team: Chris and George.
- What it does: you film your rooms on any phone. Pack It Up lists every item with its size and weight, settles what the footage leaves unclear, packs the trucks in 3D, checks every placement against moving rules, and improves the plan with a Gemini 4 model.
- Who it is for: people moving themselves who today guess the truck size from the number of bedrooms.
- All code was written at the event. Brought in: an item size table drafted before the event, Penn Station reference photos, and open-source libraries (listed in the README).

## How it works, in order

1. Film: photos or short clips per room on the phone page (`/app/capture.html`).
2. Gemini 4 Hydrogen (`gemini-4-hydrogen`) reads each photo or clip: items, catalog match, size estimate, material, handling flags (fragile, keep upright, two-person lift). One call per file.
3. The Gemini Decisions API (`gemini-decision-1`) answers the gap questions with a calibrated confidence: is this the same sofa seen twice, which size is closer, is the shelving built in. Confident answers are applied; the rest are asked of the person on the phone.
4. Check the list (`/app/review.html`): quantity, Move / Stays / Sell / Toss, add an item the camera missed.
5. A 3D solver packs the trucks; a checker scores every placement: fit and payload, no overlap, at least 75% support under each piece, upright and on-edge rules, stacking and fragile rules, left/right balance, doorways at the destination.
6. Gemini 4 Neon (`gemini-4-neon`) reads the checker's score and broken rules and changes the solver settings, for up to 3 rounds. The best round with no rule broken is kept.
7. The models page (`/app/models.html`) shows which model did each call.

## The example move used in the screenshots

- Two rooms filmed at the hackathon venue today (one clip and one photo per room): 52 items and 16 boxes, 68 pieces in all.
- 11 gap questions answered (by the Decisions API or by the person).
- The plain solve: 2 × U-Haul 26 ft trucks, score 91.5 out of 100, 0 rules broken.
- After Gemini 4 Neon: 1 × U-Haul 26 ft truck, score 95.2, 0 rules broken.

## What we measured (eval/RESULTS.md as rebuilt at 15:31; use these numbers only, with their caveats)

- Test set: 26 moves filmed today from 16 different sets of footage. Most are rooms at the hackathon venue, not homes.
- Plans with no rule broken, counting one move per set of footage: ours 16 of 16; the stock open-source packer `py3dbp`, scored by the same checker, 3 of 16.
- Rules broken over all 26 moves: stock packer 298, ours 0.
- The checker changed once: at 15:30 we relaxed one rule for small moves (under 30 pieces need 2 stocked destination stores instead of 3). Before that change, 2 of our 24 plans broke it. The plans did not change; the rule did. This caveat must sit next to the 16 of 16.
- Gemini 4 Neon raised the checker's score on 9 of 14 sets (scored before that rule change); on the other 5 the starting plan was already best.
- Inventory against a count made in person in one venue lounge (51 movable things): recall 67% to 75%, precision 84% to 90% over 8 runs. One room only: a first reading, not a measured accuracy.
- Decisions API answers graded in person in that lounge: the 4 answers applied automatically were all correct; 2 of 5 low-confidence suggestions were correct, so the confidence separated what to apply from what to ask.
- Caveats that must appear with the numbers: mostly venue rooms, not homes; item sizes are model estimates or catalog values, not measured; the checker's rules are ours.

## Which model did what

| Job | Model |
|---|---|
| Read photos and clips into an inventory | Gemini 4 Hydrogen |
| Answer gap questions with calibrated confidence | Gemini Decisions API (`gemini-decision-1`) |
| Improve the packing plan from the checker's result | Gemini 4 Neon |
| Moving-supply shopping agent (Shopify `shop.dev` bonus track) | Gemini 4 Neon |
| Narration of the demo video | Gemini text-to-speech |
| 4-second opening clip of the demo video (generated, labelled) | Gemini Omni 1.2 Flash |
| Narration lines and cards of the demo video | Gemini 4 Carbon |
| This slide deck | Gemini 4 Carbon |

## Try it

- On your phone: https://packitup.temperedanalytics.com (works while the demo laptop runs). QR code image: `qr.png`.
- Code: https://github.com/TallGibbs/Pack-It-Up

## Slide order (8 slides)

1. Cover: name, one-line promise, the event, the QR code small in a corner.
2. How it works: the 7 steps above as a simple flow, naming the model at each step.
3. Film: the capture page screenshot.
4. Check the list: the review page screenshots (answers from the Decisions API, and the item list).
5. Neon plans the load: the 3D plan screenshot after Gemini 4 Neon; 2 trucks (91.5) to 1 truck (95.2), 0 rules broken.
6. Which model did what: the models page screenshot and the table above.
7. What we measured: the numbers above with their caveats.
8. Try it yourself: QR code, the address, the GitHub link.

## Never on a slide

- Anything not in this file: no invented numbers, customers, quotes, prices or features.
- Features that are not built: competing agents as a result, a Penn Station arrival render, printed QR box labels, a single-model-call baseline.
- People's names other than the team's first names; no faces.
