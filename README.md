# Pack It Up

Film your home on any phone and get labelled boxes, a truck size, and a load order that has been checked to fit.

Built at the Cerebral Valley × Google DeepMind **Gemini 4 NYC hackathon** (Nov 21, 2026), Problem Statement Two: Element 119.

## Demo video and slides

- **1-minute demo video:** https://youtu.be/u_4H0JKHQrY
- **Judging slides:** [frontend/slides/index.html](frontend/slides/index.html), 8 slides. Open them through the running app at `/app/slides/` (for example https://packitup.temperedanalytics.com/app/slides/ while the demo laptop runs); arrow keys move between slides. The app screenshots they show are captured at build time and not committed.
- **Try it on your phone:** https://packitup.temperedanalytics.com (works while the demo laptop runs the API and the tunnel).

Both were made by Gemini, not hand-written: the slides' copy and design by Gemini 4 Carbon (`python -m scripts.slides.build`, from the facts in [scripts/slides/brief.md](scripts/slides/brief.md)); the video's narration lines and cards by Gemini 4 Carbon, its voice by Gemini text-to-speech (`gemini-3.8-flash-tts`), and its 4-second opening by Gemini Omni 1.2 Flash, labelled as generated on screen (`python -m scripts.video.build`, plan in [plan/VIDEO_SCRIPT.md](plan/VIDEO_SCRIPT.md)). Every app shot in both is a screen capture of Pack It Up running on Nov 21, 2026. The rule is in [AGENTS.md](AGENTS.md), "Demo and presentation outputs are made by Gemini".

## Status

In progress. Track A (ingestion: photos and clips to a resolved inventory with sizes, weights and questions) runs end to end; see [backend/ingest/README.md](backend/ingest/README.md). Track B (solver, checker, 3D view, the Gemini 4 Neon planner loop) was joined into `main` at 13:55 and runs from the same inventory. What we measured is in [eval/RESULTS.md](eval/RESULTS.md).

## What was built at the event

- **Before the event:** research and planning only. The first commit, made before kickoff, contains this README, `.gitignore`, `.env.example`, `FAILURES.md` and empty folder READMEs. It has no code.
- **At the event:** all code.
- **Brought in:**
  - Penn Station reference photos and clips (`data/NYPenn/`), taken by the team before kickoff. Used as the move destination; not committed.
  - `data/item_catalog.csv`: starting item sizes and handling flags, drafted in the planning repo before kickoff and brought in at the event.
  - Python libraries (see `requirements.txt`): `google-genai` (Apache-2.0), `fastapi` (MIT), `uvicorn` (BSD-3-Clause), `python-multipart` (Apache-2.0), `jsonschema` (MIT), `Pillow` (MIT-CMU), `pillow-heif` (BSD-3-Clause), `imageio-ffmpeg` (BSD-2-Clause; ships an ffmpeg binary under its own licence), `python-dotenv` (BSD-3-Clause), `databricks-sql-connector` (Apache-2.0; only for the optional Databricks copy of the model-use history, which stores data and runs no model), `py3dbp` (MIT; bin and item modelling and the baseline packer in `backend/solver.py`). The 3D page loads `three.js` 0.160 (MIT) from the jsDelivr CDN.
  - U-Haul's truck guidance (the home size each truck is for, and its cargo volume), read from uhaul.com/Truck-Rentals on Nov 21. Used only as the rule-of-thumb baseline in `eval/results_table.py`.
  - Gemini API list prices (`backend/analysis/prices.toml`): dollars per million tokens for the models we call, copied by hand from Google's pricing page (ai.google.dev/gemini-api/docs/pricing) on Nov 21. Used only for the cost estimate on the usage page (`/app/models.html`).

## Layout

| Folder | Purpose |
|---|---|
| `backend/` | API server: Gemini 4 calls, packing solver, verifier |
| `frontend/` | Web page: upload, inventory review, 3D van view |
| `data/` | Reference tables (item sizes, truck dimensions), plus demo photo and video folders that stay out of git. See [data/README.md](data/README.md) |
| `eval/` | Baselines, test set results, scoring scripts |

[FAILURES.md](FAILURES.md) logs what broke during the build and what we changed.

## Models

Every model call goes through `backend/llm/` and is set per job in [backend/llm/models.toml](backend/llm/models.toml); `runs/<run_id>/calls.jsonl` logs which model did each call.

| Job | Model | What it does |
|---|---|---|
| `perceive` | Gemini 4 Hydrogen (`gemini-4-hydrogen`) | One call per photo or clip: items, catalog match, size estimate, material, handling flags, fixtures and personal belongings |
| `decide` | Gemini Decisions API (`gemini-decision-1`, api_version `v1alpha`) | Calibrated answers to gap questions: same item seen twice, catalog vs measured size, counts, built-in vs free-standing, and Shopify moving-supply spec verification |
| `decide_fallback` | Gemini 4 Hydrogen | Enum-constrained JSON answer if a Decisions API call fails |
| `plan` | Gemini 4 Neon (`gemini-4-neon`) | Reads verifier violations and revises 3D packing strategy |
| `shop` | Gemini 4 Neon (`gemini-4-neon`) | **Bonus Track (Shopify `shop.dev`):** Move Supply Kit & conversational Shopping Agent over live `https://mcp.shop.com` (`search_catalog`, `ask_business`, `create_cart`, `create_checkout`) |

## Setup

1. Copy `.env.example` to `.env` and add your Gemini API key. Never commit `.env`.
2. `python -m venv .venv`, then `.venv\Scripts\pip install -r requirements.txt` (Windows) or `.venv/bin/pip install -r requirements.txt`.
3. Check the models answer: `python -m backend.llm.hello`.
4. Inventory a folder of photos and clips: `python -m backend.ingest data/Inputs/Malin --room "Malin lounge"`.
5. API: `uvicorn backend.app:app --port 8000`, then `curl -F room="Lounge" -F files=@photo.jpg localhost:8000/upload` and `curl localhost:8000/inventory/<run_id>`.
6. Which model did which job: open `/app/models.html?run_id=<run_id>`, or `?run_id=all` for totals and run-by-run trends; or run `python -m backend.analysis [run_id | --trends]`. It copies each run's `calls.jsonl` and `questions.json` into `.history/analysis.db` (git-ignored), which keeps a run, marked archived, after its folder is deleted. If `.env` has the `DATABRICKS_*` settings (see `.env.example`), the API also copies new or changed runs every minute to Delta tables in your own Databricks workspace (`pack_it_up.model_use`: runs, calls, decisions, perception); `python -m backend.analysis --push` copies now, and `GET /analysis/databricks` shows when it last ran. The models page reads that copy back (`GET /analysis/databricks/summary`, kept for a minute) and shows it under "History in Databricks": totals per model across every run, queried from the Delta tables.
7. Score against a hand count: `python eval/score_inventory.py runs/<run_id> eval/hand_counts/malin.json`.

## Open the pages (phone upload and review)

Plain HTML in `frontend/`, no build step. `capture.html` films or picks photos and clips per room, shows each file's progress, and asks the top question right there; `review.html` has every question plus quantity and Move / Stays / Sell / Toss edits. Both hand off to the 3D view (`index.html?run_id=…`).

- **Without a server (mock data):** `python -m http.server 8080 --directory frontend`, then open `http://localhost:8080/capture.html?mock=1` or `http://localhost:8080/review.html?mock=1`.
- **Against the API:** the API serves the pages at `/app`. Run it on all interfaces: `uvicorn backend.app:app --host 0.0.0.0 --port 8000`, then open `http://<laptop IP>:8000/app/capture.html` on the phone. `review.html?run_id=<run_id>` opens a finished run. Pages served elsewhere take `?api=http://<host>:8000`.
- **Check the phone can reach the laptop first.** Get the laptop's IP with `ipconfig` (IPv4 Address), then open `http://<laptop IP>:8000/health` on the phone, on the same wifi. Venue wifi often blocks device-to-device traffic, and Windows blocks inbound ports on networks marked Public.
- **Demo address: https://packitup.temperedanalytics.com/** opens the capture page from any network. It is a named Cloudflare tunnel (`pack-it-up`) to the API on the demo laptop, so it works only while that laptop runs both the API and the tunnel. Start both with `powershell -ExecutionPolicy Bypass -File run_demo.ps1`. It starts a hidden keeper process that checks every 10 seconds and starts the API or the tunnel again if either has stopped; the keeper does not belong to the terminal or agent session that started it, but it does not survive a reboot. `run_demo.ps1 -Status` shows what is running, `-RestartApi` restarts the API with the code on disk (after a Python change), and `-Stop` stops everything. Logs are in `.cache/demo/`. The tunnel's credentials stay in `~/.cloudflared/` and are never committed. At the Hackathon venue the wifi blocks phone-to-laptop traffic, so this is how phones and judges reach it.
- **To run it full time without the laptop,** see [DEPLOY.md](DEPLOY.md): one Linux server runs the API and the same tunnel under systemd.
- **Without the named tunnel, use a quick tunnel:** `cloudflared tunnel --url http://localhost:8000` prints an `https://….trycloudflare.com` address; open `<that address>/app/capture.html` on the phone. It works on any network, but each upload is capped at 100 MB, so keep clips short. On the laptop, `capture.html` shows a QR code of its own address when opened through the LAN IP or the tunnel.
- A plain file input opens the phone's camera over HTTP; nothing here needs HTTPS.
