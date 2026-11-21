"""Copy the analysis database to Databricks, so the model-use history outlives this laptop.

One-way and in the background: the local SQLite (`store.py`) stays the source the page reads; this copies
each new or changed run into Delta tables in `<catalog>.<schema>` (default `pack_it_up.model_use`):
runs, calls, decisions, perception, the same columns as the local tables plus `pushed_at`. A run is
replaced whole (delete, then insert), keyed on run_id, so re-sending one is safe.

Off unless `.env` has DATABRICKS_HOST, DATABRICKS_HTTP_PATH and DATABRICKS_TOKEN. Network or Databricks
trouble never reaches the page: the loop records the error and tries again later. Databricks is storage
only here; no model runs on it.

    python -m backend.analysis --push      # copy now and print what was sent
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import re
import threading
import time

from . import store

log = logging.getLogger("pack.analysis.databricks")
logging.getLogger("databricks.sql").setLevel(logging.ERROR)  # hides a pyarrow notice we don't need (no Arrow fetches)

TABLES = {
    "runs": ["run_id STRING", "created STRING", "rooms STRING", "n_files BIGINT", "stage STRING", "items BIGINT",
             "volume_cuft DOUBLE", "weight_lb DOUBLE", "archived BIGINT", "archived_at STRING"],
    "calls": ["run_id STRING", "seq BIGINT", "ts STRING", "job STRING", "provider STRING", "model STRING",
              "kind STRING", "prompt_version STRING", "file STRING", "cache STRING", "valid BIGINT",
              "latency_s DOUBLE", "tokens_in BIGINT", "tokens_out BIGINT", "thoughts BIGINT", "attempt BIGINT",
              "media_mode STRING", "error STRING"],
    "decisions": ["run_id STRING", "question_id STRING", "kind STRING", "refers_to STRING", "item_label STRING",
                  "text STRING", "ask STRING", "model_answer STRING", "model_answer_label STRING",
                  "model_confidence DOUBLE", "via STRING", "final_answer STRING", "final_answer_label STRING",
                  "answered_by STRING", "status STRING", "low_confidence BIGINT", "user_changed BIGINT"],
    "perception": ["run_id STRING", "file STRING", "room_id STRING", "kind STRING", "model STRING",
                   "prompt_version STRING", "items BIGINT", "units BIGINT", "containers BIGINT",
                   "spoken_facts BIGINT", "seconds DOUBLE"],
}
BATCH = 100          # rows per INSERT statement
INTERVAL_S = 60      # background loop period
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

state = {"enabled": False, "last_push": None, "last_error": None, "last_error_at": None,
         "runs_pushed": 0, "pending": None, "target": None}
_push_lock = threading.Lock()
_started = False


def _cfg() -> dict | None:
    store_env = {k: os.environ.get(k, "").strip() for k in ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")}
    if not all(store_env.values()):
        return None
    catalog = os.environ.get("DATABRICKS_CATALOG", "pack_it_up").strip()
    schema = os.environ.get("DATABRICKS_SCHEMA", "model_use").strip()
    if not (_NAME.match(catalog) and _NAME.match(schema)):
        raise ValueError("DATABRICKS_CATALOG and DATABRICKS_SCHEMA must be plain names (letters, digits, _)")
    host = re.sub(r"^https?://", "", store_env["DATABRICKS_HOST"]).rstrip("/")
    return {"host": host, "http_path": store_env["DATABRICKS_HTTP_PATH"], "token": store_env["DATABRICKS_TOKEN"],
            "catalog": catalog, "schema": schema}


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(store.ROOT / ".env")
    except ImportError:
        pass


def enabled() -> bool:
    _load_env()
    try:
        return _cfg() is not None
    except ValueError:
        return False


def _connect(cfg: dict):
    from databricks import sql  # only imported when configured
    return sql.connect(server_hostname=cfg["host"], http_path=cfg["http_path"], access_token=cfg["token"],
                       _socket_timeout=120)


def _ensure(cur, cfg: dict) -> str:
    """Create the schema and tables if missing. The catalog itself is made once in the workspace."""
    ns = f"`{cfg['catalog']}`.`{cfg['schema']}`"
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {ns}")
    for t, cols in TABLES.items():
        cur.execute(f"CREATE TABLE IF NOT EXISTS {ns}.`{t}` ({', '.join(cols)}, pushed_at TIMESTAMP)")
    return ns


def _local_rows(con, table: str, run_id: str) -> list[dict]:
    names = [c.split()[0] for c in TABLES[table]]
    return [{n: r[n] for n in names} for r in con.execute(f"SELECT * FROM {table} WHERE run_id = ?", (run_id,))]


def _insert(cur, ns: str, table: str, rows: list[dict], now: dt.datetime) -> None:
    names = [c.split()[0] for c in TABLES[table]]
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        params, values = {}, []
        for j, row in enumerate(chunk):
            marks = []
            for n in names:
                key = f"p{j}_{n}"
                params[key] = row[n]
                marks.append(f":{key}")
            params[f"p{j}_pushed_at"] = now
            marks.append(f":p{j}_pushed_at")
            values.append("(" + ", ".join(marks) + ")")
        cur.execute(f"INSERT INTO {ns}.`{table}` ({', '.join(names)}, pushed_at) VALUES {', '.join(values)}", params)


def _pending(con) -> list[tuple[str, str]]:
    """Runs whose content (sig) or archived flag changed since the last successful push."""
    rows = con.execute("""SELECT r.run_id, r.sig || '|' || COALESCE(r.archived, 0) AS s FROM runs r
                          LEFT JOIN pushed p ON p.run_id = r.run_id
                          WHERE p.sig IS NULL OR p.sig != r.sig || '|' || COALESCE(r.archived, 0)
                          ORDER BY r.run_id""").fetchall()
    return [(r["run_id"], r["s"]) for r in rows]


def push(force: bool = False) -> dict:
    """Copy new or changed runs (all runs with force=True). Returns {"pushed": [...], "target": ...}."""
    _load_env()
    cfg = _cfg()
    if cfg is None:
        raise RuntimeError("Databricks is not set up: add DATABRICKS_HOST, DATABRICKS_HTTP_PATH and DATABRICKS_TOKEN to .env")
    with _push_lock:
        store.sync()
        con = store.connect()
        try:
            con.execute("CREATE TABLE IF NOT EXISTS pushed (run_id TEXT PRIMARY KEY, sig TEXT, pushed_at TEXT)")
            if force:
                con.execute("DELETE FROM pushed")
            todo = _pending(con)
            state["pending"] = len(todo)
            target = f"{cfg['catalog']}.{cfg['schema']}"
            state["target"] = target
            if not todo:
                return {"pushed": [], "target": target}
            done = []
            with _connect(cfg) as dbx, dbx.cursor() as cur:
                ns = _ensure(cur, cfg)
                for run_id, sig in todo:
                    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
                    for table in TABLES:
                        cur.execute(f"DELETE FROM {ns}.`{table}` WHERE run_id = :run_id", {"run_id": run_id})
                        rows = _local_rows(con, table, run_id)
                        if rows:
                            _insert(cur, ns, table, rows, now)
                    con.execute("INSERT OR REPLACE INTO pushed VALUES (?, ?, ?)",
                                (run_id, sig, dt.datetime.now().isoformat(timespec="seconds")))
                    con.commit()
                    done.append(run_id)
                    state["pending"] = len(todo) - len(done)
            state["runs_pushed"] += len(done)
            state["last_push"] = dt.datetime.now().isoformat(timespec="seconds")
            return {"pushed": done, "target": target}
        finally:
            con.close()


def _loop() -> None:
    wait = INTERVAL_S
    while True:
        time.sleep(wait)
        try:
            push()
            state["last_error"] = None
            wait = INTERVAL_S
        except Exception as e:  # network, auth, a sleeping warehouse: record it and back off
            state["last_error"] = f"{type(e).__name__}: {e}"[:300]
            state["last_error_at"] = dt.datetime.now().isoformat(timespec="seconds")
            log.warning("Databricks copy failed: %s", state["last_error"])
            wait = min(wait * 2, 15 * 60)


def start_background() -> None:
    """Start the copy loop once per process, only when Databricks is configured."""
    global _started
    state["enabled"] = enabled()
    if _started or not state["enabled"]:
        return
    _started = True
    threading.Thread(target=_loop, name="databricks-copy", daemon=True).start()


def status() -> dict:
    out = {k: v for k, v in state.items()}
    out["enabled"] = enabled()
    return out
