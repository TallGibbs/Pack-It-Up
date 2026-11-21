# Upload and review UI spec (Track A)

The phone pages for Track A: film or photograph a room, watch it being processed, check the inventory, and hand it to Track B's packing plan. Builds on the HTTP routes in [INGESTION_SPEC.md](INGESTION_SPEC.md#interfaces) and BUILD_STEPS step A5. Where this spec and INGESTION_SPEC differ on routes or data, INGESTION_SPEC wins.

The upload is the start of the live demo (0:00 to 0:50 in the [demo script](EVENT_DAY_PLAN.md#three-minute-demo-script)), so it must be quick and must not fail in front of the judges. The review screen is a checkpoint on the way to the packing plan, not the product: the anti-project rules warn against dashboards and image analyzers. Someone should get through it in under 30 seconds.

## Pages and files

Plain HTML and JS, no build step, no framework. New files only; `frontend/index.html` is George's.

| File | What it is |
|---|---|
| `frontend/capture.html` | Capture and progress screens |
| `frontend/review.html` | Review and handoff screens |
| `frontend/ui/capture.js`, `frontend/ui/review.js` | Each page's script (moved out of the HTML at 12:40) |
| `frontend/ui/api.js` | API client: real server or mock, chosen by the URL; also the helpers both pages share |
| `frontend/ui/style.css` | Shared styles, phone first |
| `frontend/mock/mock-api.js` | In-browser mock of the Track A routes |
| `frontend/mock/inventory.json` | Fixture in the `inventory_v2` shape, with `set_by_speech` and questions |

Query parameters, on either page:

- `?mock=1` runs against the mock. No server, no key, no media needed.
- `?api=http://host:port` points at an API on another origin. Default: the page's own origin.
- `?run_id=…` picks the run: the one `review.html` shows, and the one `capture.html` carries on with. The capture page adds it to its own address after the first upload, so a reload continues the same move (decision 12:19; details in [frontend/README.md](../frontend/README.md#what-a-move-is)).

## Screen 1: Capture

- **Room card.** A room name field (placeholder "Living room"; default "Room 1") and two buttons:
  - **Film or photograph**: `<input type="file" accept="image/*,video/*" capture="environment">`. Opens the camera straight away. One shot per tap.
  - **Choose from library**: `<input type="file" accept="image/*,video/*" multiple>`. Several photos and clips at once. On iOS this also offers the camera.
  
  Two inputs are needed because `capture` and `multiple` don't work together on most phones.
- **Upload on pick.** Files start uploading as soon as they are picked, so the first room uploads while the second is being filmed. One `POST /upload` per pick, with `room` and, after the first, the `run_id` it returned. Uploads go through `XMLHttpRequest` so a progress bar can show bytes sent (`fetch` has no upload progress).
- **Several rooms per move.** "Add another room" adds a card. Every room in a move shares one `run_id`.
- **Narration hint**, under the buttons: "Talk while you film: 'these chairs stack', 'the cabinet's full of books', 'the sofa stays'. We'll hear it." Spoken facts show up on the review screen as "you said: …".
- **Filming hints**, one line: slow pan, 10 to 30 seconds per clip, include a door or a person for scale.
- **Size guard.** Warn (don't block) when a clip is over 200 MB. Cloudflare's free tunnel rejects requests over 100 MB, so warn at 90 MB when the page is on a `trycloudflare.com` address.
- **Open on phone.** On a wide screen (the laptop), show a QR code of the page's address so a phone opens it without typing an IP. If the page was opened on `localhost`, say that the QR needs the LAN or tunnel address instead.

## Screen 2: Progress

Shown on the capture page under each room card as soon as an upload starts. The screen is never blank.

- One row per file: kind icon (photo or clip), name, then its current step:
  `uploading 43%` → `received` → `looking…` → `done · 23 items · 18 s` (or `failed`, with the error).
- Data: client-side upload progress until the POST returns, then `GET /runs/{run_id}` every second. `status.files[name]` gives `intake`, `perceive`, `items`, `seconds`; `status.stage` gives the run stage; `status.errors` lists failures.
- A running count from the partial inventory: "31 items found so far".
- **Live question** (decision 11:38). The top open question appears as a card under the progress list as soon as the server raises it, and is answered there with one tap (`POST /answer`). After an answer the next one shows; the rest stay on the review page. `always_show` questions (closed cupboards) come first. The page scrolls to the first card once.
- **Footer buttons.** "Check list" (to `review.html`) and **"Plan the truck load →"** (straight to `index.html?run_id=…`, skipping review). Both appear as soon as `GET /runs` returns an `inventory`. "Plan the truck load" becomes the main button when `status.stage` is `done`, or after 60 seconds (the speed budget: show what finished, mark the rest pending). Leaving never cancels files still processing.
- Polling stops when the stage is `done` or `failed`, or the page is hidden, and restarts when it's shown again.

## Screen 3: Review

`review.html?run_id=…`. Loads `GET /runs/{run_id}`, and keeps polling while `partial` is true.

**Top bar:** the move totals that matter to the truck: items, cubic feet, pounds, and "+ N boxes" from containers. They update after every edit.

**Question cards first**, at most 5 plus any `always_show` ones, in the order the server gives (it ranks by cubic feet at stake). `same_item` and `fixture_check` questions are never open cards (decision 11:38): their text is written for the model, so they show collapsed with the Decisions API's best guess and a "Change" link. Each card:

- The crop of the item or container, the question text, and one button per option. One tap answers it: `POST /answer/{run_id}` with `{question_id, answer}`. The reply is the updated inventory; re-render from it.
- Questions the Decisions API already answered, or the narrator already answered, show collapsed as "Answered by the Decisions API: …" or "You said: '…'", with a "Change" link that reopens the options.

**Item list**, grouped by room, largest volume first. Each row:

- **Thumbnail** from `GET /media/{run_id}/{sha256[:16]}/crop?box={box_2d}&t={timestamp_s}&size=160`, lazy-loaded.
- **Label**, and a badge when the item was only heard (`heard_only`) or is partly visible.
- **Size and weight with sources**, in one line: `36 × 36 × 36 in · catalog` and `85 lb · estimate`. Source words: `catalog`, `estimate` (vision), `you said` (speech), `default`; weight `density` shows as `by material`.
- **"You said" quotes** from `set_by_speech`: `“these chairs stack” — 0:07 in IMG_6703`.
- **Handling badges** that matter for loading: fragile, two-person, keep upright.
- **Quantity stepper** (− n +). Sends `PATCH /inventory/{run_id}/items/{id}` with `{quantity}` 400 ms after the last tap. Setting 0 marks the item trash (the server does this).
- **Disposition** (decision 11:38): Move (`keep`), Stays (`stays`), Sell (`sell`), Toss (`trash`) as a segmented control, sent with `PATCH {disposition}`. `undecided` counts as moving and shows Move outlined. Stays, Sell and Toss rows dim and drop out of the totals. Any other value (an older `donate`) shows as a badge until a segment is tapped.

**Add an item** (added 12:40): a "+ Add an item" button under each room's list, for something the camera didn't see ("add a piano"). It opens a sheet with a searchable catalog list grouped by category (`GET /catalog`), a quantity stepper, and "Not in the list" for a typed name plus length, width and height in inches. It sends `POST /inventory/{run_id}/items` with `{room, catalog_id, quantity}` or `{room, label, dims_in, quantity}`; the reply is the updated inventory. Added rows show an "added by you" badge, count in the totals, and are removed with Toss or quantity 0.

**Below the items:** containers (bookshelf, cabinet: contents, fullness, about N boxes), then one footnote line for what's left out: "Left out: 14 fixtures, 13 personal belongings (5 laptops, 5 jackets, 3 backpacks)".

Edits apply optimistically and are replaced by the server's reply. If a request fails, the row reverts and shows "Didn't save, tap to retry".

## Screen 4: Handoff

**"Plan the truck load →"** in the sticky bar of both pages, with the totals beside it on the review page. Open questions don't block it; it says "2 questions open".

It opens Track B's page with the run: `index.html?run_id={run_id}` (plus `&api=` or `&mock=1` if set). Edits only change the inventory; Track B solves when its page opens, so re-solve after an edit is tapping the button again (decision 11:38). The proposed contract for George (which fields to read) is in [memory/open-questions.md](../memory/open-questions.md).

## Data the pages read

Checked against real runs from the ingestion session at 11:40. The pages render without any optional field; they just show less.

- **Items:** the `inventory_v2` item shape from resolve, including `set_by_speech: [{field, value, quote, source, timestamp_s}]` and `heard_only`. One sentence can set two fields, so quotes are shown once each. Disposition `stays` (from speech: "this sofa stays") selects Stays, and the row drops out of the totals. `contents_unknown` shows "contents unknown, assumed empty".
- **Containers:** `set_by_speech` quotes are shown inline. Container evidence has no `sha256`, so the crop borrows the hash of an item seen in the same file.
- **Questions,** as `backend/ingest/gaps.py` writes them in `inventory.questions`:
  - `options` is `{key: label}`. The button shows the label and `POST /answer` sends the key. `options: null` with `free_text: true` shows a text box. `free_text: "number"` next to options adds a number box, and the `more` option is dropped (the API rejects it as an answer).
  - `always_show: true` (closed cupboards) is shown on top of the 5 ranked questions, never capped.
  - `refers_to` is an item id, a container label or a room id; the card's crop comes from that target.
  - `shown: true` marks the open questions the server wants the user to see (at most 5); the rest are counted in "N smaller questions not shown".
  - `suggested` and `model_answer.confidence` mark the Decisions API's best guess on its button ("best guess · 36%").
  - `status: answered` with `answered_by` of `decisions_api`, `generate_json_fallback`, `speech` or `user` shows collapsed, with a "Change" link.
  - The question `text` is written for the model, so some are long ("The last image is a new sighting…"). Cards clamp to 4 lines; a short `user_text` field would read better.
- **File names:** iPhone camera captures all arrive as `image.jpg`, and the server keys status by file name, so the capture page renames repeats to `image_2.jpg` before upload.

## How the phone reaches the laptop

The server runs on the laptop (`uvicorn backend.app:app --host 0.0.0.0 --port 8000`). The phone has to load the page and post files to it.

| Route | How | Works when | Breaks when | Upload speed |
|---|---|---|---|---|
| **LAN IP** | Phone and laptop on the venue wifi; open `http://<laptop IP>:8000/…` | The wifi lets devices talk to each other | Guest and event wifi often isolate clients. Windows also marks new wifi as Public and its firewall blocks inbound 8000 unless Python is allowed on Public networks | Fastest: local only |
| **Phone hotspot** | Laptop joins the phone's hotspot; phone opens the laptop's hotspot address | Hotspots usually allow it | Not tested on iPhone. The laptop's Gemini calls then go over cellular | Fast to the laptop; Gemini upload over cellular |
| **Tunnel** (Cloudflare quick tunnel: `cloudflared tunnel --url http://localhost:8000`) | Phone opens the `https://…trycloudflare.com` address | Any network with internet, including isolated wifi | Needs `cloudflared` installed before the demo. Free tunnel limit is 100 MB per request. Quick tunnels have no uptime guarantee | Phone → internet → laptop: venue upstream bandwidth twice |
| **No phone** | Copy the files to the laptop (AirDrop or cable) and use the capture page on the laptop | Always | Slower on stage | n/a |

**Decided (11:38): test LAN now, tunnel as backup.** Test the LAN route once: open `http://<laptop IP>:8000/health` on the phone. If it answers, use LAN and keep a tunnel running as backup. If it doesn't, use the tunnel. Rehearse the "No phone" route once; it's the fallback in the demo script.

**HTTP is enough.** A file input with `capture` opens the camera over plain HTTP; it isn't a secure-context feature. `getUserMedia` (a live camera preview in the page) needs HTTPS or `localhost`, so it only works through the tunnel. These pages don't use it: the phone's own camera app records better video, with audio, and needs no permission prompt.

**One port.** A tunnel exposes one port, so `backend/app.py` serves `frontend/` at `/app` (decision 11:38): the phone opens `/app/capture.html` on the same address as the API. For page work without the API, `python -m http.server 8080` in `frontend/` still works, with `?api=` or `?mock=1`.

## Done when

On a phone-sized viewport (390 × 844) against `?mock=1`: pick files, see per-file progress, open the review, edit a quantity, change a disposition, answer a question, and reach the handoff button. Then the same against the real server with the Malin photos.

## Not in scope

- `getUserMedia` capture, in-page video recording or trimming.
- Login, saved moves, editing dimensions by hand (`PATCH` doesn't accept them).
- The 3D view, solve and re-solve (Track B).
