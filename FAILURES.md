# Failures log

One line per failure found during the build: the input, what went wrong, and what we changed.

| Time | Input | What went wrong | What we changed |
|---|---|---|---|
| 10:56 | Decisions API test call (`client.decisions.create`, choice question) with models/gemini-4-hydrogen, -argon, -neon, -carbon, decisions-1 | 404 "Requested model not found" on v1beta and v1alpha; the endpoint exists but no listed model ID is accepted | Kept `decide()` on the generic `generate_json` fallback until the Decisions model ID is confirmed in AI Studio |
| 11:00 | Malin IMG_6708.JPEG, perceive_v1 on gemini-4-hydrogen | The model leaked its reasoning into an item label ("communal work table (foreground ... let's use 108x44x30)") | `perceive.clean_label()` trims labels over 60 chars at the first parenthesis or dash |
| 11:00 | Malin merge | Canonical-noun matcher found "chair" in "...and chairs around it" and split one communal table into two groups | Match only the head phrase (before parentheses, commas, "with"), and pick the noun that ends last |
