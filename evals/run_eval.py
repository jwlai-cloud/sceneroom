# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Does the verification path actually get the right answer?

Runs claims with known verdicts through the real `_check_factual` — the same
Parallel call and the same Verifier agent the product uses — and scores the
result. Written because "pro feels better than base" was an impression formed
from a handful of runs, and an impression is not a number.

    uv run python evals/run_eval.py                 # the configured processor
    uv run python evals/run_eval.py --compare       # base vs pro, same claims

Two errors are counted separately, because they are not equally bad:

- **Wrong call** — said verified when the truth is contradicted, or vice versa.
  This is the failure that ships an error, and it is the one that matters.
- **Missed** — answered `unverifiable` when there was a real answer. Costs the
  writer a decision they should not have had to make, but ships nothing wrong.

A system that misses is tolerable. A system that makes wrong calls is not, and
the scoring says so rather than averaging them into one accuracy number.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

HERE = pathlib.Path(__file__).parent
DATASET = HERE / "claims.jsonl"


def load() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


async def score_one(case: dict) -> dict:
    # Imported inside so the processor env var is read at call time, which is
    # what makes --compare able to switch it between runs.
    from app.models import Claim, ClaimKind, Scene
    from app.orchestrator import _check_factual

    claim = Claim(id=case["id"], kind=ClaimKind.HISTORICAL, text=case["claim"])
    scene = Scene(id="eval", intent="eval", setting=case["setting"])

    started = time.perf_counter()
    await _check_factual(claim, scene)
    took = time.perf_counter() - started

    got = claim.verdict.value if claim.verdict else "none"
    want = case["expected"]

    if got == want:
        outcome = "hit"
    elif got == "unverifiable":
        outcome = "missed"
    elif want == "unverifiable":
        outcome = "overclaimed"   # asserted an answer where none exists
    else:
        outcome = "wrong"

    return {
        "id": case["id"],
        "want": want,
        "got": got,
        "outcome": outcome,
        "seconds": round(took, 1),
        "sources": len(claim.sources),
    }


async def run(label: str) -> list[dict]:
    cases = load()
    # Serially, not concurrently: this measures quality, and a rate limit that
    # empties a source list would look like a verification failure.
    results = []
    for case in cases:
        r = await score_one(case)
        results.append(r)
        mark = {"hit": "✓", "missed": "~", "wrong": "✗", "overclaimed": "!"}[r["outcome"]]
        print(f"  {mark} {r['id']:<18} want {r['want']:<13} got {r['got']:<13} "
              f"{r['sources']} sources  {r['seconds']}s")
    return results


def summarise(label: str, results: list[dict]) -> dict:
    n = len(results)
    counts = {k: sum(1 for r in results if r["outcome"] == k) for k in
              ("hit", "missed", "wrong", "overclaimed")}
    print(f"\n{label}: {counts['hit']}/{n} correct · "
          f"{counts['missed']} missed · {counts['wrong']} WRONG · "
          f"{counts['overclaimed']} overclaimed")
    if counts["wrong"]:
        print("  wrong calls (these ship errors):")
        for r in results:
            if r["outcome"] == "wrong":
                print(f"    {r['id']}: wanted {r['want']}, said {r['got']}")
    return counts


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true", help="run base and pro")
    args = ap.parse_args()

    if not os.getenv("PARALLEL_API_KEY"):
        print("PARALLEL_API_KEY is not set — this would score the offline fixtures.")
        return 2

    if not args.compare:
        label = os.getenv("PARALLEL_PROCESSOR", "base")
        print(f"processor: {label}\n")
        summarise(label, await run(label))
        return 0

    for processor in ("base", "pro"):
        os.environ["PARALLEL_PROCESSOR"] = processor
        # The client reads the processor at import; reload so the switch takes.
        import importlib

        from app.services import parallel_client

        importlib.reload(parallel_client)
        print(f"\n=== processor: {processor} ===")
        summarise(processor, await run(processor))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
