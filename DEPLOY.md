# Deploy Pack It Up on a server

At the event the app ran on a laptop: `run_demo.ps1` kept the API and a named Cloudflare tunnel running, and https://packitup.temperedanalytics.com/ worked only while that laptop was on. This guide moves both to an always-on Linux server, so the same address keeps working with the laptop off.

The files are in [`deploy/`](deploy/):

| File | What it does |
|---|---|
| `setup.sh` | First-time setup as root: packages, a `packitup` service user, the checkout in `/opt/pack-it-up`, the venv, `.env`, the systemd units, a health check. `--cloudflared` also installs cloudflared |
| `update.sh` | `git pull`, `pip install`, restart. Waits until no move has changed for 90 s first (`--force` skips the wait) |
| `cleanup.sh` | Deletes moves untouched for 30 days and cache files older than 14 days. `DRY_RUN=1` lists only |
| `packitup.service` | The API: `uvicorn` on `127.0.0.1:8000`, one worker, restarts if it stops, starts at boot |
| `packitup-cleanup.service`, `.timer` | Runs `cleanup.sh` daily at about 04:17 |
| `cloudflared-config.yml.example` | Tunnel config for the server |

## 1. Get a Gemini key that outlasts the event

The event key belongs to the event's account, which is temporary (decisions.md, 12:00 and 13:10). When that key stops working, every model call fails, wherever the app runs.

1. Create a key in Google AI Studio on a project with billing turned on.
2. On the laptop, put it in `.env` as `GEMINI_API_KEY_PERSONAL` and run `GEMINI_KEY_PROFILE=PERSONAL python -m backend.llm.hello`. Check it reaches every model in `backend/llm/models.toml`: the four Gemini 4 models, `gemini-decision-1` on `v1alpha`, and the TTS, image, video, robotics and managed-agent models. The event key reached them all; a personal key may not.
3. For any model it cannot reach, change that job's line in `models.toml` (or set `MODEL_<JOB>=provider:model` in the server's `.env`) and log it in `FAILURES.md`.
4. Set a budget alert on that billing account (step 6 explains why).

On the server, put this key in plain `GEMINI_API_KEY`; no profile is needed.

## 2. Pick a server

Use **one always-on Linux VM with its own disk** (Ubuntu 24.04 or Debian 12; Python 3.11 or later). 2 vCPU and 2 to 4 GB of RAM is enough for demo traffic; any provider works.

Serverless hosting (Cloud Run, Lambda, Vercel) does not fit this code:
- Everything is kept on local disk: `runs/` (uploads, inventories), `.cache/` (model-call cache, renders) and `.history/analysis.db` (SQLite).
- `/upload` replies at once and the pipeline keeps going in a background thread; rendering, the agent race and the Databricks copy do too.
- The upload locks live in memory, so the API must be **one process**. Don't add workers or a second copy behind a load balancer.

The server needs no open inbound ports: the tunnel connects outward. Allow SSH only.

## 3. Run the setup

```bash
sudo apt-get install -y git
sudo git clone https://github.com/TallGibbs/Pack-It-Up.git /opt/pack-it-up
sudo bash /opt/pack-it-up/deploy/setup.sh --cloudflared
```

Then add the key and restart:

```bash
sudo -u packitup nano /opt/pack-it-up/.env      # GEMINI_API_KEY=..., Databricks settings if wanted
sudo systemctl restart packitup
curl http://127.0.0.1:8000/health               # {"ok":true}
```

`setup.sh` can be run again; it never overwrites `.env`. Other paths or users: `APP_DIR=/srv/pack-it-up APP_USER=pack sudo -E bash deploy/setup.sh`.

## 4. Copy what git doesn't have

From the laptop, if you want them on the server:
- `data/NYPenn/` (Penn Station photos and clips used by the arrival render and destination views).
- Past moves: `runs/` and `.history/analysis.db`. Without them the server starts empty, and the Usage page has no history except what Databricks holds.

```bash
scp -r data/NYPenn runs .history  user@server:/tmp/packitup-copy/
# on the server:
sudo cp -r /tmp/packitup-copy/* /opt/pack-it-up/ && sudo chown -R packitup:packitup /opt/pack-it-up
sudo systemctl restart packitup
```

## 5. Move the Cloudflare tunnel

The `pack-it-up` tunnel keeps its name and hostname; only the machine running it changes.

1. On the laptop, find the tunnel ID and its credentials file: `cloudflared tunnel list`, then `%USERPROFILE%\.cloudflared\<TUNNEL-ID>.json`.
2. Copy that file to the server as `/etc/cloudflared/<TUNNEL-ID>.json` (`sudo chmod 600`). Never commit it.
3. Copy `deploy/cloudflared-config.yml.example` to `/etc/cloudflared/config.yml` and fill in the tunnel ID.
4. **Stop the laptop first:** `powershell -ExecutionPolicy Bypass -File run_demo.ps1 -Stop`. If both machines connect to the same tunnel, Cloudflare sends some visitors to each, and moves end up split across two disks.
5. On the server: `sudo cloudflared service install`, then `sudo systemctl status cloudflared`.
6. From a phone on mobile data, open https://packitup.temperedanalytics.com/health and then the capture page.

If you'd rather manage the tunnel from the Cloudflare dashboard: Zero Trust > Networks > Tunnels > create a tunnel, then run the `cloudflared service install <token>` line it shows, and add a public hostname pointing to `http://localhost:8000`. Then move the DNS record from the old tunnel to the new one.

The laptop is free after this. `run_demo.ps1` still works for local testing, as long as it doesn't start the tunnel while the server is running it.

## 6. Protect it before you leave it public

- **There is no real login.** The sign-in page asks only for a name, and CORS allows any site. Anyone with the address can upload files and spend money on the Gemini key. The simplest fix needs no code: put **Cloudflare Access** in front of the hostname (Zero Trust > Access > Applications > Self-hosted, hostname `packitup.temperedanalytics.com`, a policy allowing your team's emails). Phones then sign in once with a one-time email code.
- **Cap spending** on the Gemini key's billing account (step 1). Move 133201 cost an estimated $1.20 at list prices (Usage page; sessions.md, 15:16).
- **Uploads are photos and videos of people's homes.** `cleanup.sh` deletes a move 30 days after its last change; change `RUNS_KEEP_DAYS` in `deploy/packitup-cleanup.service` to suit, then run `update.sh` so the unit is reinstalled. `DELETE /runs/{run_id}/files/{name}` removes a single file.
- **Uploads are capped at 100 MB per request** by Cloudflare, as before. Keep clips short.

## 7. Day to day

| Task | Command |
|---|---|
| Deploy new code from `main` | `sudo bash /opt/pack-it-up/deploy/update.sh` |
| Status | `systemctl status packitup cloudflared` |
| Logs | `journalctl -u packitup -f` (the API), `journalctl -u cloudflared -f` (the tunnel) |
| Restart | `sudo systemctl restart packitup` |
| See what cleanup would delete | `sudo -u packitup DRY_RUN=1 /opt/pack-it-up/deploy/cleanup.sh` |
| Change a setting in `.env` | edit, then `sudo systemctl restart packitup` |

- **Backups:** `runs/` and `.history/` exist only on this disk. Either turn on your provider's disk snapshots, or copy them off nightly, e.g. `rsync -a /opt/pack-it-up/runs /opt/pack-it-up/.history backup-host:pack-it-up/`. The Databricks copy keeps the usage history, but not the media or the inventories.
- **Uptime:** add a free uptime check on `https://packitup.temperedanalytics.com/health`.
- **Free public services:** the route features call Nominatim, OSRM's demo server, Overpass and Open-Meteo; the shop calls `mcp.shop.com`. Their terms allow light use. That's fine at demo traffic; real users would need paid or self-hosted versions.
- `.cache/calls.jsonl` (the log of every model call) keeps growing; it is small, but trim it once a year or so.

## What has been checked

On a Linux container, not a real VM: `pip install -r requirements.txt` succeeded; the `ExecStart` command from `packitup.service` started the API, `/health` answered `{"ok":true}`, `/app/capture.html` answered 200 and `/` redirected to it; `cleanup.sh` deleted a 40-day-old move and a 20-day-old cache file and kept the new ones, and `DRY_RUN=1` listed the same without deleting. All three scripts pass `bash -n`.

Not checked: `setup.sh` and `update.sh` end to end under systemd, the cloudflared install and tunnel move, Cloudflare Access, and a personal Gemini key against every model.
