#!/usr/bin/env python3
"""Extend the 600-PASS image with eight system tests and PASS-only coverage."""
from pathlib import Path

import extend_gap_coverage as gap

extension = gap.extension
batch = gap.batch
SCRIPT = Path(__file__).resolve()
original_frozen = batch.frozen


def frozen(output, case=None, all_cases=False):
    plan = original_frozen(output, case, all_cases)
    # The full recollection uses source_entries rather than the older
    # extension's source_selection field. Preserve that provenance explicitly.
    if "source_selection" not in plan:
        plan = dict(plan, source_selection={"full_recollection": str(output),
                                           "source_entries": plan.get("source_entries", [])})
    return plan


batch.frozen = frozen
original_prepare = extension.prepare


def prepare(output, previous, selection):
    original_prepare(output, previous, selection)
    plan = batch.read(output / "plan.json")
    header = batch.ROOT / "apps/riscv-tests/isa/rv64uv/system_gap30_common.h"
    for case in plan["cases"]:
        if case["name"] not in plan["reused"]:
            case["source_files"].update(batch.pins([header]))
    plan["files"].update(batch.pins([Path(gap.__file__), Path(extension.__file__)]))
    batch.save(output / "plan.json", plan)
    batch.save(output / "plan.sha256.json", batch.pins([output / "plan.json"]))
    batch.frozen(output, all_cases=True)


extension.prepare = prepare
extension.SCRIPT = batch.SCRIPT = SCRIPT

if __name__ == "__main__":
    raise SystemExit(extension.main())
