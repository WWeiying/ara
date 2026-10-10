#!/usr/bin/env python3
"""Collection-only resume: validate copied outcomes, never schedule simulation."""
import fcntl
from pathlib import Path
import traceback

import queue_other_gap_exploration as q

b = q.batch
OUT = q.ROOT / "verification/out/vcs-original473-gap28-20260928-01"
EVIDENCE = OUT / "dve-resume-01"


def main():
    q.QUEUE = OUT.with_name(OUT.name + "-queue")
    with (q.ROOT / "verification/out/.batch-vcs.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = b.read(OUT / "checkpoint.json")
        q.require(state["status"] == "STOPPED" and state["phase"] == "DVE",
                  "requires stopped collection, not simulation")
        q.require(state["completed"] == state["total"] == 521 and
                  state["counts"] == {"PASS": 503, "TIMEOUT": 18}, "unexpected outcomes")
        EVIDENCE.mkdir(exist_ok=False)
        b.save(EVIDENCE / "checkpoint.before.json", state)
        try:
            plan = q.frozen(OUT, all_cases=True)
            previous = Path(plan["source_selection"]["previous"])
            q.require(previous == q.BASELINE, "wrong predecessor")
            copied = {}
            for name in plan["reused"]:
                original = previous / "outcomes" / (name + ".json")
                path = OUT / "outcomes" / (name + ".json")
                # Validate the historical hash first, then the exact permitted
                # prepare-time transformation. Do not bless arbitrary copies.
                b.check({str(original): plan["files"][str(original)]})
                expected = dict(b.read(original), reused=True)
                q.require(b.read(path) == expected, f"copied outcome differs: {name}")
                copied.update(b.pins([path]))
            q.require(len(copied) == 485, "wrong inherited outcome count")
            outcome_pins = b.pins(OUT / "outcomes" / (c["name"] + ".json")
                                  for c in plan["cases"])
            collection_plan = dict(plan, files=dict(plan["files"], **copied))
            b.save(EVIDENCE / "collection-plan.json", collection_plan)
            manifest = {
                "mode": "DVE_ONLY_NO_RESIM", "original_plan_unchanged": True,
                "rootcause": "prepare pinned predecessor outcomes but not copied outcome paths; summarize KeyError",
                "copied_outcomes_validated": len(copied), "outcomes": outcome_pins,
                "files": b.pins([OUT / "plan.json", OUT / "plan.sha256.json",
                                 EVIDENCE / "collection-plan.json", Path(__file__).resolve()]),
                "image_policy": "original473 archived-source validation; no live RTL claim",
            }
            b.save(EVIDENCE / "manifest.json", manifest)
            b.save(EVIDENCE / "status.json", {"status": "RUNNING", "phase": "DVE_ONLY"})
            print("Validated original archive/image and 485 inherited copies; collecting 503 PASS VDBs", flush=True)
            outcomes = q.summarize(OUT, collection_plan)
            b.check(outcome_pins)
            b.check(manifest["files"])
            q.frozen(OUT, all_cases=True)
            q.require(sum(x["passed_only"] for x in outcomes) == 503, "PASS count drift")
            state.pop("reason", None)
            state.update(status="COMPLETE_WITH_FAILURES", phase="complete", passed_only=503,
                         collection_resume=str(EVIDENCE / "manifest.json"))
            b.save(OUT / "checkpoint.json", state)
            b.save(EVIDENCE / "status.json", {"status": "COMPLETE", "passed": 503,
                   "excluded_timeouts": 18, "resimulated": 0,
                   "collection": str(OUT / "collection.json")})
            print("COMPLETE: DVE 503 PASS; 18 TIMEOUT excluded; zero resimulation", flush=True)
        except Exception as error:
            b.save(EVIDENCE / "status.json", {"status": "STOPPED", "reason": str(error),
                   "traceback": traceback.format_exc(), "resimulated": 0})
            raise


if __name__ == "__main__":
    main()
