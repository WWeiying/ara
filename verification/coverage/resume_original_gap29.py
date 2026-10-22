#!/usr/bin/env python3
"""Resume Gap29 after a pre-simulation source-pin stop; preserve the stop record."""

from pathlib import Path

import run_original_gap29 as run


def main():
    output = run.ROOT / "verification/out/vcs-original503-gap29-20260928-01"
    run.batch.SCRIPT = run.gap.extension.SCRIPT = run.SCRIPT
    run.batch.frozen = run.previous.frozen
    run.batch.summarize = run.summarize
    run.batch.schedule = run.memory.original_schedule
    run.batch.base.sources = run.previous.original_sources
    run.previous.BASELINE = run.BASELINE
    run.previous.QUEUE = Path(str(output) + "-queue")
    checkpoint = output / "checkpoint.json"
    state = run.read(checkpoint)
    expected = f"frozen input changed: {run.SCRIPT}"
    if (state["status"] != "STOPPED" or state.get("reason") != expected or
            state["completed"] != 521 or state["passed"] != 503 or
            state.get("simulations_started", False)):
        raise RuntimeError("not the expected pre-simulation stop")
    run.batch.frozen(output, all_cases=True)
    state["resume_record"] = {"prior_status": "STOPPED", "prior_reason": expected,
                              "new_simulations_before_resume": 0}
    state["status"] = "PREPARED"
    run.save(checkpoint, state)
    return run.batch.execute(output, 8)


if __name__ == "__main__":
    raise SystemExit(main())
