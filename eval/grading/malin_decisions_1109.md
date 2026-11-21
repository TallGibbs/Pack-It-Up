# Decisions API grading: Malin, run 20261121-110958

Questions raised by the pipeline for the Malin lounge (5 files: IMG_6703.MP4, IMG_6704.MP4, IMG_6705.JPEG, IMG_6707.JPEG, IMG_6708.JPEG), answered by the Gemini Decisions API (`gemini-decision-1`), and graded by Chris against the room in person on Nov 21, 2026. Answers at confidence 0.7 or above are applied automatically; lower ones are shown to the user as suggestions.

## Applied automatically (confidence >= 0.7): 4 of 4 correct

| Question | Decisions answer | Confidence | Truth (in person) | Correct |
|---|---|---|---|---|
| Is the double-wide metal shelving unit on a credenza base built in or free-standing? | free_standing | 0.90 | free-standing | yes |
| Size of the dark-wood open shelving: catalog 32 x 12 x 72 in, or footage 96 x 16 x 84 in? | footage | 0.94 | about 96 in tall, slightly wider than tall | yes |
| How many communal work tables? | 2 | 0.72 | 2 | yes |
| Is the white sculptural armchair (IMG_6704) one of the armchairs already counted (orange, burgundy, grey)? | different | 0.88 | different | yes |

## Suggested only (confidence < 0.7): 2 of 5 correct as graded by Chris; 2 of 6 including one derived row

| Question | Decisions suggestion | Confidence | Truth (in person) | Correct |
|---|---|---|---|---|
| How many armchairs? (options 1, 3, 4, 5, 6, 7) | 4 | 0.27 | 4 single-seat chairs | yes |
| Is the dark-wood open shelving built in or free-standing? | free_standing | 0.51 | free-standing | yes |
| How many bar stools? (options 4, 5, 6, 7) | 5 | 0.51 | 6 | no (6 was offered at low probability) |
| How many upholstered work chairs? (options 5, 9, 10, 11, 12) | 12 | 0.31 | 16 | no (16 was not an option) |
| Is the cream bouclé armchair (IMG_6708) one of the armchairs already counted (orange, burgundy, grey)? | same | 0.54 | different (it is the white sculptural chair from IMG_6704, which was not in that list) | no |
| *Derived:* Is the dark brown armchair (IMG_6705) one of the armchairs already counted? | different | 0.62 | same (it is the burgundy chair) | no |

The derived row was not in Chris's list; it follows from his note that the model's "dark brown" armchair is the burgundy one.

## Not gradeable

| Question | Decisions suggestion | Confidence | Why |
|---|---|---|---|
| How full is the closed credenza sideboard? | empty | 0.36 | Doors closed; contents unknown in person too. Footage can't answer this, so from this run on, closed containers go straight to the user (see FAILURES.md, 11:30) |

## Summary

- Applied answers: 4 of 4 correct. Every answer the pipeline acted on without asking was right.
- Suggestions below 0.7: 2 of 5 correct (Chris's grading), 2 of 6 with the derived row. The threshold kept all of the wrong answers from being applied.
- Two failures came from the question, not the model: the work-chair count offered no option as high as 16, and the cream bouclé comparison didn't include the one chair it matched. Both are fixed in the pipeline (FAILURES.md, 11:30).
