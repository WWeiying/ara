#!/usr/bin/env python3
"""Offline re-audit and source-freeze receipt; never executes an EDA tool."""
import argparse
import json
from pathlib import Path
from upstream_20261009_run import (ROOT, TARGETS, ORIGINAL_SHA, audit, baseline_gate,
                                  cases, save, sha, validate_output)


def close(output):
    output = validate_output(output)
    results = {}
    source_hashes = {name: sha((ROOT / path).read_bytes()) for name, path in TARGETS.items()}
    for suite in TARGETS:
        rows = cases(suite)
        manifests = {}
        for variant in ("baseline", "candidate"):
            directory = ROOT / f"verification/out/upstream_20261009-{suite}-{variant}01"
            manifest = json.loads((directory / "manifest.json").read_text())
            prior = json.loads((directory / "audit.json").read_text())
            if manifest["suite"] != suite or manifest["variant"] != variant:
                raise ValueError("wrong experiment identity")
            if json.loads((directory / "cases.json").read_text()) != list(map(list, rows)):
                raise ValueError("changed cases")
            if sha((directory / "cases.txt").read_bytes()) != manifest["cases_sha256"]:
                raise ValueError("changed executable cases")
            for record in manifest["sources"]:
                if sha(Path(record["frozen"]).read_bytes()) != record["sha256"]:
                    raise ValueError("changed archived input")
            manifests[variant] = {r["relative"]: r["sha256"] for r in manifest["sources"]}
            wanted_sha = ORIGINAL_SHA[suite] if variant == "baseline" else source_hashes[suite]
            if manifests[variant][TARGETS[suite]] != wanted_sha:
                raise ValueError("wrong original/current DUT")
            for stage in ("build", "sim"):
                stage_result = json.loads((directory / stage / "result.json").read_text())
                if stage_result["returncode"] or stage_result.get("timeout"):
                    raise ValueError("incomplete execution")
                if sha((directory / stage / "console.log").read_bytes()) != stage_result["log_sha256"]:
                    raise ValueError("changed execution log")
            if sha((directory / "build/simv").read_bytes()) != prior["image_sha256"]:
                raise ValueError("changed image")
            if sha((directory / "sim/observed.txt").read_bytes()) != prior["trace_sha256"]:
                raise ValueError("changed observations")
            result = audit((directory / "sim/observed.txt").read_text(),
                           (directory / "sim/console.log").read_text(), suite, rows)
            if variant == "baseline":
                baseline_gate(result, suite, rows)
            elif result["status"] != "PASS":
                raise ValueError("candidate not fully passing")
            results[f"{suite}_{variant}"] = dict(
                cases=result["cases"], checks=result["checks"], passing_cases=result["passing_cases"],
                failed_checks=len(result["failures"]), directory=str(directory),
                verdict="EXPECTED_OLD_FAILURE" if variant == "baseline" else "PASS",
                manifest_sha256=sha((directory / "manifest.json").read_bytes()),
                image_sha256=prior["image_sha256"], dut_sha256=wanted_sha,
                compile_seconds=prior["compile"]["elapsed_s"], sim_seconds=prior["simulation"]["elapsed_s"])
        differing = {p for p in manifests["baseline"] if manifests["baseline"][p] != manifests["candidate"][p]}
        if differing != {TARGETS[suite]}:
            raise ValueError(f"old/new pair differs beyond the owned DUT: {differing}")
    output.mkdir(parents=True)
    result = dict(status="PASS", sources_frozen=source_hashes, results=results,
                  checker_sha256=sha((Path(__file__).parent / "upstream_20261009_run.py").read_bytes()),
                  closure_sha256=sha(Path(__file__).read_bytes()),
                  scope="actual module RV64 Sv39 RVH=0 PMP=0; no full-SoC/cache signoff")
    save(output / "audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = close(args.output)
    print(json.dumps(result, indent=2))
