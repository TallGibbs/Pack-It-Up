"""Build and query `.history/analysis.db` from the run folders. See __init__.py."""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import threading
from pathlib import Path

from backend.ingest.common import ROOT, RUNS_DIR

from . import pricing

# Outside .cache/ (which people wipe to force fresh model calls) and runs/ (which gets cleaned up), so the
# history survives both. Git-ignored: it holds item labels and question text from real footage.
DB_PATH = Path(os.environ.get("PACK_ANALYSIS_DB", ROOT / ".history" / "analysis.db"))
SOURCES = ("calls.jsonl", "questions.json", "status.json", "manifest.json", "inventory.json", "answers.json")

# What each job is for, in words a judge can repeat back. Jobs not listed show their own name.
ROLES = {
    "perceive": ("Sees", "Lists the items, sizes, materials and handling flags in each photo and clip"),
    "perceive_fallback": ("Sees (backup)", "Second look if the first model's answer is weak"),
    "transcribe": ("Hears", "Transcribes a clip's narration when the perceive model can't hear"),
    "decide": ("Answers", "Calibrated answers to gap questions: same item?, how many?, built in?, how full?"),
    "decide_fallback": ("Answers (backup)", "Enum-constrained answer when a Decisions API call fails"),
    "plan": ("Plans", "Reads the checker's violations and changes the packing strategy"),
    "managed_agent": ("Competes", "Strategy agents each try a packing plan in their own Google managed-agent sandbox (Antigravity)"),
    "route": ("Guides", "Writes the truck route brief from live road, toll, bridge clearance, parking and weather data"),
    "shop": ("Shops", "Plans the box and supply kit and answers shopping questions in plain words"),
    "judge": ("Judges", "Final check on the packed plan: yes/no safety gates, scores and a go-ahead choice"),
    "judge_escalate": ("Judges (second look)", "Diagnoses a plan the judge flagged or was unsure about, and proposes a fix"),
    "baseline": ("Baseline", "One-call packing plan, scored by our checker for comparison"),
    "image": ("Draws", "Illustrative arrival image (not the plan)"),
    "hello": ("Check", "Connection check"),
}
ORDER = list(ROLES)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, created TEXT, rooms TEXT, n_files INTEGER, stage TEXT,
  items INTEGER, volume_cuft REAL, weight_lb REAL, sig TEXT, archived INTEGER DEFAULT 0, archived_at TEXT);
CREATE TABLE IF NOT EXISTS calls (
  run_id TEXT, seq INTEGER, ts TEXT, job TEXT, provider TEXT, model TEXT, kind TEXT, prompt_version TEXT,
  file TEXT, cache TEXT, valid INTEGER, latency_s REAL, tokens_in INTEGER, tokens_out INTEGER,
  thoughts INTEGER, attempt INTEGER, media_mode TEXT, error TEXT, PRIMARY KEY (run_id, seq));
CREATE TABLE IF NOT EXISTS decisions (
  run_id TEXT, question_id TEXT, kind TEXT, refers_to TEXT, item_label TEXT, text TEXT, ask TEXT,
  model_answer TEXT, model_answer_label TEXT, model_confidence REAL, via TEXT, final_answer TEXT,
  final_answer_label TEXT, answered_by TEXT, status TEXT, low_confidence INTEGER, user_changed INTEGER,
  PRIMARY KEY (run_id, question_id));
CREATE TABLE IF NOT EXISTS perception (
  run_id TEXT, file TEXT, room_id TEXT, kind TEXT, model TEXT, prompt_version TEXT, items INTEGER,
  units INTEGER, containers INTEGER, spoken_facts INTEGER, seconds REAL, PRIMARY KEY (run_id, file));
"""

_lock = threading.Lock()


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default  # missing, or caught mid-write: the next sync picks it up


def _sig(rd: Path) -> str:
    parts = []
    for name in SOURCES:
        p = rd / name
        try:
            st = p.stat()
            parts.append(f"{name}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            pass
    perc = rd / "perception"
    if perc.is_dir():
        parts.append(f"perception:{sum(1 for _ in perc.glob('*.json'))}:{perc.stat().st_mtime_ns}")
    return "|".join(parts)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    cols = {r["name"] for r in con.execute("PRAGMA table_info(runs)")}
    for col, decl in (("archived", "INTEGER DEFAULT 0"), ("archived_at", "TEXT")):  # databases made before 12:40
        if col not in cols:
            con.execute(f"ALTER TABLE runs ADD COLUMN {col} {decl}")
    return con


def _opt_label(q: dict, key) -> str | None:
    if key is None:
        return None
    opts = q.get("options") or {}
    if isinstance(opts, dict):
        return str(opts.get(str(key), key))
    return str(key)


def _load_run(con: sqlite3.Connection, run_id: str, rd: Path, sig: str) -> None:
    for t in ("calls", "decisions", "perception", "runs"):
        con.execute(f"DELETE FROM {t} WHERE run_id = ?", (run_id,))

    manifest = _read(rd / "manifest.json", {}) or {}
    status = _read(rd / "status.json", {}) or {}
    inv = _read(rd / "inventory.json", {}) or {}
    totals = inv.get("totals") or {}
    labels = {it.get("id"): it.get("label") for room in inv.get("rooms", []) for it in room.get("items", [])}
    labels.update({c.get("id"): c.get("label") for room in inv.get("rooms", []) for c in room.get("containers", [])})
    rooms = ", ".join(r.get("name", r.get("id", "")) for r in manifest.get("rooms", []))
    if manifest.get("who"):  # the sign-in name leads, so the models page and the Databricks copy show whose move it is
        rooms = f"{manifest['who']}: {rooms}"
    con.execute("INSERT INTO runs (run_id, created, rooms, n_files, stage, items, volume_cuft, weight_lb, sig, archived) "
                "VALUES (?,?,?,?,?,?,?,?,?,0)",
                (run_id, manifest.get("created"), rooms, len(manifest.get("files", [])), status.get("stage"),
                 totals.get("item_count"), totals.get("volume_cuft"), totals.get("weight_lb"), sig))

    calls_path = rd / "calls.jsonl"
    if calls_path.exists():
        rows = []
        for seq, line in enumerate(calls_path.read_text(encoding="utf-8").splitlines()):
            try:
                r = json.loads(line)
            except ValueError:
                continue  # a half-written last line
            # A managed-agent call logs the agent's name as `model` and the model it ran on as `agent_model`.
            # This table answers "which model did which job", so it keeps the model; `kind` still says managed_agent.
            rows.append((run_id, seq, r.get("ts"), r.get("job"), r.get("provider"), r.get("agent_model") or r.get("model"), r.get("kind"),
                         r.get("prompt_version"), r.get("file"), r.get("cache"), int(bool(r.get("valid"))),
                         r.get("latency_s"), r.get("tokens_in"), r.get("tokens_out"), r.get("thoughts"),
                         r.get("attempt"), r.get("media_mode"), r.get("error")))
        con.executemany("INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    qs = (_read(rd / "questions.json", {}) or {}).get("questions", [])
    for q in qs:
        ma = q.get("model_answer") or {}
        model_ans = ma.get("answer", q.get("suggested"))
        final = q.get("answer")
        by = q.get("answered_by")
        changed = int(by == "user" and model_ans is not None and final is not None and str(final) != str(model_ans))
        con.execute("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, q.get("id"), q.get("kind"), q.get("refers_to"), labels.get(q.get("refers_to")),
                     q.get("text"), q.get("ask"), None if model_ans is None else str(model_ans),
                     _opt_label(q, model_ans), ma.get("confidence"), ma.get("via"),
                     None if final is None else str(final), _opt_label(q, final), by, q.get("status"),
                     int(bool(q.get("low_confidence"))), changed))

    files = status.get("files", {})
    perc = rd / "perception"
    if perc.is_dir():
        for p in perc.glob("*.json"):
            d = _read(p, {}) or {}
            name = d.get("file") or p.stem
            items = d.get("items") or []
            units = sum(int(it.get("quantity") or it.get("count") or 1) for it in items if isinstance(it, dict))
            con.execute("INSERT OR REPLACE INTO perception VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (run_id, name, d.get("room_id"), d.get("kind"), d.get("model"), d.get("prompt_version"),
                         len(items), units, len(d.get("containers") or []), len(d.get("spoken_facts") or []),
                         (files.get(name) or {}).get("seconds")))


def sync(run_id: str | None = None) -> None:
    """Copy new or changed runs into the database. Cheap when nothing changed (one stat per file)."""
    if not RUNS_DIR.is_dir():
        return
    dirs = [RUNS_DIR / run_id] if run_id else [p for p in RUNS_DIR.iterdir() if p.is_dir()]
    with _lock:
        con = connect()
        try:
            known = {r["run_id"]: r["sig"] for r in con.execute("SELECT run_id, sig FROM runs")}
            for rd in dirs:
                if not rd.is_dir():
                    continue
                sig = _sig(rd)
                if known.get(rd.name) != sig:
                    _load_run(con, rd.name, rd, sig)
            if not run_id:
                # A run whose folder is gone stays, marked archived: the database is the history, and the
                # folders can be cleaned up. If the folder comes back, the next sync reloads it.
                gone = set(known) - {p.name for p in dirs}
                now = dt.datetime.now().isoformat(timespec="seconds")
                con.executemany("UPDATE runs SET archived = 1, archived_at = ? WHERE run_id = ? AND archived = 0",
                                [(now, rid) for rid in gone])
            con.commit()
        finally:
            con.close()


# ---------- queries ----------

def _configured() -> dict[str, dict]:
    """Every job in models.toml, so the page can show jobs that were set up but not called."""
    try:
        from backend.llm import load_config  # reads models.toml only; no SDK import
        jobs = load_config().get("jobs", {})
    except Exception:
        return {}
    out = {}
    for job, cfg in jobs.items():
        role, does = ROLES.get(job, (job, ""))
        out[job] = {"model": str(cfg.get("model", "")).partition(":")[2], "role": role, "does": does}
    return out


def _jobs(con: sqlite3.Connection, where: str, args: tuple) -> list[dict]:
    rows = con.execute(f"""
        SELECT job, model, provider, COUNT(*) AS calls,
               SUM(cache = 'miss') AS live_calls, SUM(cache = 'hit') AS cached,
               SUM(valid = 0) AS failed_attempts,
               ROUND(AVG(CASE WHEN cache = 'miss' AND valid = 1 THEN latency_s END), 2) AS avg_latency_s,
               ROUND(MAX(CASE WHEN cache = 'miss' THEN latency_s END), 2) AS max_latency_s,
               ROUND(SUM(CASE WHEN cache = 'miss' THEN latency_s ELSE 0 END), 1) AS total_latency_s,
               SUM(COALESCE(tokens_in, 0)) AS tokens_in, SUM(COALESCE(tokens_out, 0)) AS tokens_out,
               SUM(COALESCE(thoughts, 0)) AS thoughts,
               COUNT(DISTINCT run_id) AS runs
        FROM calls WHERE {where} GROUP BY job, model, provider""", args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["role"], d["does"] = ROLES.get(d["job"], (d["job"], ""))
        c = pricing.cost_usd(d["model"], d["tokens_in"], d["tokens_out"], d["thoughts"])
        d["cost_usd"] = None if c is None else round(c, 4)  # estimate at list prices; see pricing.py
        out.append(d)
    out.sort(key=lambda d: (ORDER.index(d["job"]) if d["job"] in ORDER else 99, d["job"]))
    return out


def _decision_stats(con: sqlite3.Connection, where: str, args: tuple) -> dict:
    r = con.execute(f"""
        SELECT COUNT(*) AS questions,
               SUM(via = 'decisions_api') AS by_decisions_api,
               SUM(via = 'generate_json_fallback') AS by_fallback,
               SUM(answered_by IN ('decisions_api', 'generate_json_fallback')) AS applied_automatically,
               SUM(answered_by = 'user') AS answered_by_user,
               SUM(answered_by = 'user' AND model_answer IS NOT NULL) AS user_checked,
               SUM(user_changed) AS user_changed,
               SUM(status != 'answered' OR status IS NULL) AS open,
               ROUND(AVG(model_confidence), 3) AS mean_confidence,
               SUM(model_confidence >= 0.9) AS conf_90, SUM(model_confidence >= 0.7 AND model_confidence < 0.9) AS conf_70,
               SUM(model_confidence < 0.7) AS conf_low
        FROM decisions WHERE {where}""", args).fetchone()
    d = {k: (v or 0) for k, v in dict(r).items()}
    d["agreement"] = round(1 - d["user_changed"] / d["user_checked"], 3) if d["user_checked"] else None
    kinds = con.execute(f"""SELECT kind, COUNT(*) AS n, ROUND(AVG(model_confidence), 3) AS mean_confidence
                            FROM decisions WHERE {where} GROUP BY kind ORDER BY n DESC""", args).fetchall()
    d["by_kind"] = [dict(k) for k in kinds]
    return d


def list_runs() -> list[dict]:
    sync()
    con = connect()
    try:
        rows = con.execute("""
            SELECT r.*, (SELECT COUNT(*) FROM calls c WHERE c.run_id = r.run_id) AS calls,
                        (SELECT COUNT(*) FROM decisions d WHERE d.run_id = r.run_id) AS questions
            FROM runs r ORDER BY r.run_id DESC""").fetchall()
        return [{k: r[k] for k in r.keys() if k != "sig"} for r in rows]
    finally:
        con.close()


def run_summary(run_id: str) -> dict | None:
    sync(run_id)
    con = connect()
    try:
        run = con.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None:
            return None
        calls = [dict(r) for r in con.execute("SELECT * FROM calls WHERE run_id = ? ORDER BY seq", (run_id,))]
        timeline = _timeline(calls)
        decisions = [dict(r) for r in con.execute(
            "SELECT * FROM decisions WHERE run_id = ? ORDER BY model_confidence IS NULL, model_confidence", (run_id,))]
        perception = [dict(r) for r in con.execute("SELECT * FROM perception WHERE run_id = ? ORDER BY file", (run_id,))]
        jobs = _jobs(con, "run_id = ?", (run_id,))
        return {"run": {k: run[k] for k in run.keys() if k != "sig"},
                "configured": _configured(),
                "jobs": jobs, "cost": pricing.summarize(jobs),
                "decision_stats": _decision_stats(con, "run_id = ?", (run_id,)),
                "decisions": decisions, "perception": perception, "timeline": timeline}
    finally:
        con.close()


def overall() -> dict:
    sync()
    con = connect()
    try:
        n = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        jobs = _jobs(con, "1 = 1", ())
        return {"runs": n, "configured": _configured(), "jobs": jobs, "cost": pricing.summarize(jobs),
                "decision_stats": _decision_stats(con, "1 = 1", ())}
    finally:
        con.close()


def trends() -> list[dict]:
    """One row per run, oldest first: how fast and how sure the models were, and how often the user kept
    the Decisions API's answer. Cached calls are left out of the times (they replay an earlier answer)."""
    sync()
    con = connect()
    try:
        rows = con.execute("""
            SELECT r.run_id, r.created, r.rooms, r.n_files, r.items, r.archived,
              (SELECT ROUND(AVG(latency_s), 1) FROM calls c WHERE c.run_id = r.run_id AND c.job = 'perceive'
                 AND c.cache = 'miss' AND c.valid = 1) AS perceive_s,
              (SELECT COUNT(*) FROM calls c WHERE c.run_id = r.run_id AND c.job = 'perceive' AND c.cache = 'miss') AS perceive_live,
              (SELECT COUNT(*) FROM calls c WHERE c.run_id = r.run_id AND c.job = 'perceive' AND c.cache = 'hit') AS perceive_cached,
              (SELECT ROUND(AVG(latency_s), 2) FROM calls c WHERE c.run_id = r.run_id AND c.job = 'decide'
                 AND c.cache = 'miss' AND c.valid = 1) AS decide_s,
              (SELECT COUNT(*) FROM calls c WHERE c.run_id = r.run_id AND c.job = 'decide') AS decide_calls,
              (SELECT ROUND(AVG(model_confidence), 3) FROM decisions d WHERE d.run_id = r.run_id
                 AND d.via = 'decisions_api') AS confidence,
              (SELECT COUNT(*) FROM decisions d WHERE d.run_id = r.run_id AND d.via = 'decisions_api') AS answers,
              (SELECT COUNT(*) FROM decisions d WHERE d.run_id = r.run_id AND d.answered_by = 'user'
                 AND d.model_answer IS NOT NULL) AS user_checked,
              (SELECT COALESCE(SUM(user_changed), 0) FROM decisions d WHERE d.run_id = r.run_id) AS user_changed,
              (SELECT prompt_version FROM perception p WHERE p.run_id = r.run_id AND prompt_version IS NOT NULL
                 GROUP BY prompt_version ORDER BY COUNT(*) DESC LIMIT 1) AS prompt_version
            FROM runs r ORDER BY COALESCE(r.created, r.run_id), r.run_id""").fetchall()
        cost: dict[str, float] = {}  # estimated dollars per run, at list prices
        for c in con.execute("""SELECT run_id, model, SUM(COALESCE(tokens_in, 0)) AS tin, SUM(COALESCE(tokens_out, 0)) AS tout,
                                       SUM(COALESCE(thoughts, 0)) AS th FROM calls GROUP BY run_id, model"""):
            cost[c["run_id"]] = cost.get(c["run_id"], 0.0) + (pricing.cost_usd(c["model"], c["tin"], c["tout"], c["th"]) or 0.0)
        out = []
        for r in rows:
            d = dict(r)
            d["kept"] = round(1 - d["user_changed"] / d["user_checked"], 3) if d["user_checked"] else None
            d["cost_usd"] = round(cost.get(d["run_id"], 0.0), 4)
            out.append(d)
        return out
    finally:
        con.close()


def _timeline(calls: list[dict]) -> dict:
    """Calls as bars on one clock. The log stamps each call when it ends (to the second), so start = end - latency."""
    bars = []
    for c in calls:
        try:
            end = dt.datetime.fromisoformat(c["ts"]).timestamp()
        except (TypeError, ValueError):
            continue
        lat = float(c.get("latency_s") or 0)
        bars.append({"job": c["job"], "model": c["model"], "file": c["file"], "cache": c["cache"],
                     "valid": bool(c["valid"]), "start": end - lat, "end": end, "latency_s": lat})
    if not bars:
        return {"span_s": 0, "bars": []}
    t0 = min(b["start"] for b in bars)
    for b in bars:
        b["start"] = round(b["start"] - t0, 2)
        b["end"] = round(b["end"] - t0, 2)
    return {"span_s": round(max(b["end"] for b in bars), 2), "bars": bars}
