# Failures log

One line per failure found during the build: the input, what went wrong, and what we changed.

| Time | Input | What went wrong | What we changed |
|---|---|---|---|
| 10:56 | Decisions API test call (`client.decisions.create`, choice question) with models/gemini-4-hydrogen, -argon, -neon, -carbon, decisions-1 | 404 "Requested model not found" on v1beta and v1alpha; the endpoint exists but no listed model ID is accepted | Kept `decide()` on the generic `generate_json` fallback until the Decisions model ID is confirmed in AI Studio |
| 11:00 | Malin IMG_6708.JPEG, perceive_v1 on gemini-4-hydrogen | The model leaked its reasoning into an item label ("communal work table (foreground ... let's use 108x44x30)") | `perceive.clean_label()` trims labels over 60 chars at the first parenthesis or dash |
| 11:00 | Malin merge | Canonical-noun matcher found "chair" in "...and chairs around it" and split one communal table into two groups | Match only the head phrase (before parentheses, commas, "with"), and pick the noun that ends last |
| 11:05 | Malin resolve, "room divider bookshelf" (catalog `bookshelf_tall`) | Longest side 96 vs 72 in passed the ±35% rule, so the 32-in-wide catalog size was used for a 96-in-wide unit (model volume 4.7x the catalog's) | Added a second trigger: bounding-box volume must also be within 0.5x-2x of the catalog's, else use the model's size and raise `size_check` |
| 11:06 | Malin resolve, weights | Density table on bounding boxes gave an open shelf 747 lb and a floor lamp 50 lb | Open-frame factor 0.35 for shelving, lamps, chairs, stools, tables and plants |
