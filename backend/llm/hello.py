"""Hello test: python -m backend.llm.hello [job ...]

Calls generate_text("hello") on each job twice; the second call must be a cache hit.
"""
import json
import sys

from . import GLOBAL_LOG, for_job

jobs = sys.argv[1:] or ["hello"]
for name in jobs:
    job = for_job(name)
    for i in range(2):
        out = job.generate_text("Say hello in five words or fewer.", prompt_version="hello_v1")
        last = json.loads(GLOBAL_LOG.read_text(encoding="utf-8").splitlines()[-1])
        print(f"{job!r} call {i + 1}: cache={last['cache']} latency={last['latency_s']}s -> {out.strip()!r}")
