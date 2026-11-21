# Instructions for agents

Pack It Up is being built at the Gemini 4 NYC hackathon on Nov 21, 2026. Several people and agent sessions work in this repo at the same time. **This repo is public:** never write anything here you wouldn't publish.

## Before you start

1. `git pull --rebase`.
2. If you have the team's private planning repo (on Chris's laptop it is the sibling folder `../pack_perfect_hackathon`), read its `memory/README.md` and follow it. In short: read the decisions log, add your row to the sessions table, and keep out of files another active session claims. Plans and specs are in its `plan/` folder; for Track A, `plan/INGESTION_SPEC.md` is the spec.
3. If you don't have that repo, ask the user what is decided before changing anything outside your track.

## Who owns what

| Area | Owner | Paths |
|---|---|---|
| Track A: ingestion and analysis | Chris | `backend/llm/`, `backend/ingest/`, `backend/prompts/`, `eval/hand_counts/`, `eval/score_inventory.py`, the review screen in `frontend/` |
| Track B: packing plan and output | George | `backend/catalog.py`, `data/*.csv`, `backend/expand.py`, `solver.py`, `verify.py`, `planner.py`, `agents.py`, `render.py`, `labels.py`, the 3D view in `frontend/` |
| Shared | Both | `backend/app.py`, `README.md`, `FAILURES.md`, `eval/RESULTS.md`, `requirements.txt` |

Change files outside your track only when the user asks, and say so in the commit message.

## Build rules

- **All code is written at the event.** Commit small and often; the history is our evidence. Anything brought in (libraries, reference tables, Penn Station media) is listed under "Brought in" in `README.md`.
- **Model calls go through `backend/llm/` only.** No other file imports a model SDK. Code calls `for_job("<job>")`; `backend/llm/models.toml` maps jobs to `provider:model`. The demo runs on Gemini 4 models only.
- **The inventory contract** is the resolved `inventory.json` from `backend/ingest/` (each item has a `size` block). Track B reads sizes and weights from it rather than from the catalog.
- **Log failures.** One line in `FAILURES.md` for each thing that breaks: input, what went wrong, what we changed.

## Gemini API skills

Before writing or changing any Gemini API code (in practice, anything in `backend/llm/`), load Google's public skills from [google-gemini/gemini-skills](https://github.com/google-gemini/gemini-skills) (Apache-2.0):

| Skill | Use it for |
|---|---|
| `gemini-api-dev` | The `google-genai` SDK: Interactions API, structured output, function calling, the Decisions API (`gemini-decision-1`), TTS, managed agents, Deep Research, current model IDs |
| `gemini-live-api-dev` | Live API streaming over WebSocket (only if we add live capture) |
| `gemini-api-cli` | Calling the API from the shell for quick checks |
| `gemini-omni-flash-api` | Video generation (not in our plan) |

How to get them:
- **Claude Code:** `/plugin marketplace add google-gemini/gemini-skills`, then `/plugin install gemini-skills@gemini-skills`.
- **Antigravity:** bundled. Settings → Customizations → Build with Google Plugins, or `agy plugin install https://github.com/google-gemini/gemini-skills`.
- **Other agents:** `npx skills add google-gemini/gemini-skills --skill gemini-api-dev`. Install into your own agent setup; don't commit the skill files here.
- **No install possible:** read [skills/gemini-api-dev/SKILL.md](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/SKILL.md) before writing model code.

Rules from the skill that apply here: use `google-genai` (Python) or `@google/genai` (JS), never the deprecated `google-generativeai` or `@google/generative-ai`; never use `gemini-2.5-*`, `gemini-2.0-*` or `gemini-1.5-*` models.

**Where the skill and this repo disagree, this repo wins.** The skill describes the API in general; `backend/llm/models.toml` and `FAILURES.md` record what we measured with our event keys. Example: the skill puts the Decisions API on `v1beta`, but our keys list `gemini-decision-1` only under `v1alpha` (v1beta returns 404), so `models.toml` sets `api_version = "v1alpha"`. Keep the rule that only `backend/llm/` imports a model SDK, even when a skill example imports it somewhere else.

## Never commit

- API keys or account details. Keys live in `.env`, which is git-ignored.
- Photos or clips. `data/Inputs/` and `data/NYPenn/` keep only `.gitkeep`; their `.gitignore` files ignore the media.
- `runs/` and `.cache/` (pipeline outputs, transcripts, model-call cache).
- Personal details about anyone.
