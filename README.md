# Pack It Up

Film your home on any phone and get labelled boxes, a truck size, and a load order that has been checked to fit.

Built at the Cerebral Valley × Google DeepMind **Gemini 4 NYC hackathon** (Nov 21, 2026), Problem Statement Two: Element 119.

## Status

Not started. Hacking begins at 10:30 AM EST on Nov 21, 2026.

## What was built at the event

- **Before the event:** research and planning only. The first commit, made before kickoff, contains this README, `.gitignore`, `.env.example`, `FAILURES.md` and empty folder READMEs. It has no code.
- **At the event:** all code.
- **Brought in:** _to be listed (open-source libraries and their licences, any reference tables)._

## Layout

| Folder | Purpose |
|---|---|
| `backend/` | API server: Gemini 4 calls, packing solver, verifier |
| `frontend/` | Web page: upload, inventory review, 3D van view |
| `data/` | Reference tables (item sizes, truck dimensions) |
| `eval/` | Baselines, test set results, scoring scripts |

[FAILURES.md](FAILURES.md) logs what broke during the build and what we changed.

## Models

_To be filled in: which Gemini 4 model or API does which job._

## Setup

_To be filled in._

1. Copy `.env.example` to `.env` and add your Gemini API key. Never commit `.env`.
