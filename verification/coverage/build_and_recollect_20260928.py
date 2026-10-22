#!/usr/bin/env python3
"""Build reviewed repair, then run the gated fresh-image coverage campaign.

Run as the systemd main process. This driver never patches RTL, changes an
oracle, retries a failed test, or admits a historical VDB.
"""
import argparse
import os
from pathlib import Path
import re
import sys

import build_memory_vl0_repair as builder
import run_full_recollection_20260928 as campaign

base = builder.base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unit-output", type=Path, required=True)
    parser.add_argument("--unit-pass-marker", required=True)
    args = parser.parse_args()
    build = base.checked_output(args.build_output)
    output = base.checked_output(args.output)
    unit = args.unit_output.resolve(strict=True)
    base.check_service()
    expected_service = "ara-full-recollection-" + output.name + ".service"
    if os.environ["ARA_CHECKPOINT_UNIT"] != expected_service:
        raise RuntimeError("service must match the subsequent full campaign")
    if build.exists() or output.exists() or build == output:
        raise RuntimeError("new, separate build and campaign directories required")
    unit_log = unit / "run.log"
    if (unit / "run.exitcode").read_text().strip() != "0":
        raise RuntimeError("repair unit did not exit successfully")
    text = unit_log.read_text()
    if args.unit_pass_marker not in text.splitlines() or re.search(
            r"^FAIL(?:\s|:)|Fatal:|Error:|FIRST_FAILURE", text, re.M):
        raise RuntimeError("repair unit did not pass cleanly")
    # Validate the actual source hashes used for the small discriminating test.
    unit_sources = {}
    for line in (unit / "sources.sha256").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        name = name.lstrip("*")
        source = Path(name)
        if not source.is_absolute():
            source = unit / source
        unit_sources[str(source.resolve(strict=True))] = digest
    base.check(unit_sources)
    repaired_sources = [
        (base.ROOT / "hardware/deps/fpnew/src" / name).resolve(strict=True)
        for name in ("fpnew_opgroup_multifmt_slice.sv", "fpnew_cast_multi.sv", "fpnew_pkg.sv")
    ]
    if any(str(p) not in unit_sources for p in repaired_sources):
        raise RuntimeError("unit evidence does not cover the conversion RTL being repaired")
    evidence = [unit_log, unit / "run.exitcode", unit / "sources.sha256"]
    before = base.pins([Path(__file__), Path(campaign.__file__),
                        campaign.DEFAULT_PLAN, *evidence])
    before.update(unit_sources)
    dispatcher = base.sha256(builder.DISPATCHER)
    build.mkdir()
    state = {"status": "BUILDING", "campaign": str(output),
             "unit_evidence": str(unit), "old_vdb_reuse": False}
    status_path = build / "pipeline-status.json"
    base.save(status_path, state)
    try:
        # Keep the same PID: the builder verifies systemd ownership itself.
        sys.argv = [builder.__file__, "--output", str(build),
                    "--approved-dispatcher-sha256", dispatcher]
        builder.main()
        base.check(before)
        result = base.read(build / "build-status.json")
        if result["status"] != "PASS":
            raise RuntimeError("coverage build did not pass its source/config audit")
        manifest = base.sources(build / "sim/vcs_source_manifest.json")
        compiled = {str(Path(r["path"]).resolve()): r["sha256"] for r in manifest["files"]}
        if any(compiled.get(str(p)) != unit_sources[str(p)] for p in repaired_sources):
            raise RuntimeError("unit-tested conversion RTL differs from full-image compile inputs")
        evidence.append(build / "build-status.json")
        freeze = build / "recollection-freeze.json"
        files = dict(before, **base.pins(evidence))
        base.save(freeze, {"status": "READY_FOR_FULL_RECOLLECTION",
            "simv": str(build / "sim/simv"), "image": result["image"],
            "files": files, "repair_evidence": [str(p) for p in evidence]})
        campaign.prepare(output, campaign.DEFAULT_PLAN, freeze)
        state.update(status="GATED_RECOLLECTION_STARTED", freeze=str(freeze))
        base.save(status_path, state)
        os.execv(sys.executable, [sys.executable, campaign.__file__,
                                 "--output", str(output), "--execute"])
    except Exception as error:
        state.update(status="STOPPED", reason=f"{type(error).__name__}: {error}")
        base.save(status_path, state)
        raise


if __name__ == "__main__":
    main()
