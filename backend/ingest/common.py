"""Run folders and small JSON helpers shared by the ingest stages."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = Path(os.environ.get("PACK_RUNS_DIR", ROOT / "runs"))

_status_lock = threading.Lock()


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "room_1"


def new_run_id(hint: str = "") -> str:
    """Timestamp, room hint, and a random suffix: two phones starting "Room 1" in the same second
    must not share a run, and with no login the id is all that keeps a run private."""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    token = secrets.token_hex(3)
    return f"{stamp}-{slug(hint)[:24]}-{token}" if hint else f"{stamp}-{token}"


def run_dir(run_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", run_id):
        raise ValueError(f"bad run id {run_id!r}")
    return RUNS_DIR / run_id


def _retry_locked(fn, tries: int = 40, wait_s: float = 0.025):
    """Windows refuses to replace a file while another thread has it open (and the reverse), so a
    page polling GET /runs can collide with the pipeline writing the same file. Wait and try again."""
    for attempt in range(tries):
        try:
            return fn()
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(wait_s)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(_retry_locked(lambda: path.read_text(encoding="utf-8")))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _retry_locked(lambda: os.replace(tmp, path))


def scrub(text) -> str:
    """Error text safe to show: this laptop's folders (and the user name in them) taken out.
    GET /runs returns status.json to anyone with the address."""
    text = str(text)
    for path, short in ((RUNS_DIR, "runs"), (ROOT, "."), (Path.home(), "~")):
        plain = str(path)
        for form in (plain, plain.replace("\\", "\\\\"), path.as_posix()):  # as is, repr()-doubled, forward slashes
            text = text.replace(form, short)
    return text


def update_status(rd: Path, **changes) -> dict:
    """Merge into runs/<id>/status.json. `files={name: {...}}` merges per file."""
    with _status_lock:
        st = read_json(rd / "status.json", {"stage": "created", "files": {}, "errors": []})
        files = changes.pop("files", None)
        if files:
            for k, v in files.items():
                if "error" in v:
                    v = {**v, "error": scrub(v["error"])}
                st["files"].setdefault(k, {}).update(v)
        err = changes.pop("error", None)
        if err:
            st["errors"].append(scrub(err))
        st.update(changes)
        st["updated"] = dt.datetime.now().isoformat(timespec="seconds")
        write_json(rd / "status.json", st)
        return st
