"""Hello test: python -m backend.llm.hello [--list] [job ...]

Calls generate_text("hello") on each job twice; the second call must be a cache hit.
--list prints the models this key can see (default and v1alpha API versions).
Set GEMINI_KEY_PROFILE=PERSONAL to use GEMINI_API_KEY_PERSONAL from .env instead of GEMINI_API_KEY.
"""
import json
import sys

from . import GLOBAL_LOG, _load_env, for_job

args = sys.argv[1:]
_load_env()

if "--list" in args:
    args.remove("--list")
    from google import genai  # SDK import stays inside backend/llm/

    from .gemini import key_var
    import os

    var = key_var()
    if not os.environ.get(var):
        sys.exit(f"{var} is not set in .env")
    print(f"key: {var} (value not shown)")
    for av in (None, "v1alpha"):
        client = genai.Client(api_key=os.environ[var], **({"http_options": {"api_version": av}} if av else {}))
        try:
            names = sorted(m.name.removeprefix("models/") for m in client.models.list())
        except Exception as e:
            print(f"  {av or 'default'}: ERROR {type(e).__name__}: {str(e)[:200]}")
            continue
        wanted = [n for n in names if n.startswith(("gemini-4", "gemini-decision"))]
        print(f"  {av or 'default'}: {len(names)} models; Gemini 4 and Decisions: {wanted or 'none'}")

for name in args or ["hello"]:
    job = for_job(name)
    for i in range(2):
        out = job.generate_text("Say hello in five words or fewer.", prompt_version="hello_v1")
        last = json.loads(GLOBAL_LOG.read_text(encoding="utf-8").splitlines()[-1])
        print(f"{job!r} call {i + 1}: cache={last['cache']} latency={last['latency_s']}s -> {out.strip()!r}")
