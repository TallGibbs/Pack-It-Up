# Failures log

One line per failure found during the build: the input, what went wrong, and what we changed.

| Time | Input | What went wrong | What we changed |
|---|---|---|---|
| 10:56 | Decisions API test call (`client.decisions.create`, choice question) with models/gemini-4-hydrogen, -argon, -neon, -carbon, decisions-1 | 404 "Requested model not found" on v1beta and v1alpha; the endpoint exists but no listed model ID is accepted | Kept `decide()` on the generic `generate_json` fallback until the Decisions model ID is confirmed in AI Studio |
