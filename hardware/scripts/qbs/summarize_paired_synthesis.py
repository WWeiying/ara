#!/usr/bin/env python3
"""Summarize a same-revision QBS-off/on Design Compiler pair."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path


AREA_FIELDS = {
    "number_of_cells": r"^Number of cells:\s+([0-9]+)",
    "number_of_combinational_cells":
        r"^Number of combinational cells:\s+([0-9]+)",
    "number_of_sequential_cells": r"^Number of sequential cells:\s+([0-9]+)",
    "number_of_macros": r"^Number of macros/black boxes:\s+([0-9]+)",
    "combinational_area": r"^Combinational area:\s+([0-9.]+)",
    "noncombinational_area": r"^Noncombinational area:\s+([0-9.]+)",
    "macro_area": r"^Macro/Black Box area:\s+([0-9.]+)",
    "total_cell_area": r"^Total cell area:\s+([0-9.]+)",
}

QOR_FIELDS = {
    "logic_levels": r"^\s*Levels of Logic:\s+(-?[0-9.]+)",
    "critical_path_length_ns": r"^\s*Critical Path Length:\s+(-?[0-9.]+)",
    "clk_wns_ns": r"^\s*Critical Path Slack:\s+(-?[0-9.]+)",
    "clock_period_ns": r"^\s*Critical Path Clk Period:\s+(-?[0-9.]+)",
    "clk_tns_ns": r"^\s*Total Negative Slack:\s+(-?[0-9.]+)",
    "clk_violating_paths": r"^\s*No\. of Violating Paths:\s+(-?[0-9.]+)",
}

POWER_TOP = (
    r"^ara_soc\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+"
    r"([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+100\.0\s*$"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256_manifest(path: Path) -> int:
    entries = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        digest, filename = line.split(maxsplit=1)
        filename = filename.lstrip("* ")
        artifact = Path(filename)
        require(artifact.is_file(), f"manifest artifact is missing: {artifact}")
        require(sha256(artifact) == digest,
                f"manifest hash no longer matches: {artifact}")
        entries += 1
    require(entries > 0, f"empty SHA-256 manifest: {path}")
    return entries


def extract(text: str, pattern: str, field: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    require(match is not None, f"missing report field: {field}")
    return match.group(1)


def parse_run(
    root: Path,
    tag: str,
    qbs_enabled: bool,
    source_root: Path,
    expected_git_head: str,
) -> dict[str, object]:
    run = root / tag
    require((run / "status").read_text().strip() == "PASS", f"{tag} did not pass")
    require((run / "driver_exit_code").read_text().strip() == "0",
            f"{tag} driver returned nonzero")
    reports = run / "reports"
    area_path = reports / "area.rpt"
    qor_path = reports / "qor.rpt"
    timing_path = reports / "clk_i_max.tim"
    power_path = reports / "power.rpt"
    for path in (area_path, qor_path, timing_path, power_path, run / "dc.log"):
        require(path.is_file() and path.stat().st_size > 0, f"missing artifact: {path}")
    flist_path = run / "ara_soc_dc.f"
    require(flist_path.is_file(), f"missing synthesized file list: {flist_path}")
    flist_text = flist_path.read_text(errors="replace")
    qbs_define_present = "ARA_QBS_ENABLE=1" in flist_text
    require(qbs_define_present == qbs_enabled,
            f"{tag} QBS define does not match its configuration")
    require("Thank you" in (run / "dc.log").read_text(errors="replace"),
            f"{tag} dc_shell did not terminate normally")
    actual_git_head = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    require(actual_git_head == expected_git_head,
            f"{tag} source worktree revision changed: {actual_git_head}")
    output_manifest = run / "outputs.sha256"
    require(output_manifest.is_file(), f"missing output manifest: {tag}")
    output_manifest_entries = verify_sha256_manifest(output_manifest)

    dc_root = source_root / "backend" / "syn" / "ara_soc" / "v1-dc"
    source_files = {
        "sdc_sha256": dc_root / "local_scripts" / "ara_soc.sdc",
        "dc_tcl_sha256": dc_root / "global_scripts" / "dc.tcl",
        "dont_use_tcl_sha256": dc_root / "global_scripts" / "dc_dont_use.tcl",
    }
    for path in source_files.values():
        require(path.is_file(), f"missing synthesis input: {path}")

    area_text = area_path.read_text(errors="replace")
    qor_text = qor_path.read_text(errors="replace")
    power_text = power_path.read_text(errors="replace")
    clk_start = qor_text.find("Timing Path Group 'clk_i'")
    require(clk_start >= 0, f"{tag} has no clk_i path group")
    clk_end = qor_text.find("Timing Path Group '", clk_start + 1)
    clk_text = qor_text[clk_start:clk_end if clk_end >= 0 else None]

    row: dict[str, object] = {
        "configuration": tag,
        "qbs_enabled": int(qbs_enabled),
        "source_git_head": actual_git_head,
        "output_manifest_entries": output_manifest_entries,
    }
    for field, pattern in AREA_FIELDS.items():
        value = extract(area_text, pattern, field)
        row[field] = int(value) if field.startswith("number_") else float(value)
    for field, pattern in QOR_FIELDS.items():
        value = float(extract(clk_text, pattern, field))
        row[field] = int(value) if field == "clk_violating_paths" else value
    power_match = re.search(POWER_TOP, power_text, flags=re.MULTILINE)
    require(power_match is not None, f"{tag} has no top-level power row")
    switch_mw, internal_mw, leakage_nw, total_mw = (
        float(value) for value in power_match.groups()
    )
    leakage_mw = leakage_nw / 1_000_000.0
    require(
        abs((switch_mw + internal_mw + leakage_mw) - total_mw) < 0.02,
        f"{tag} power units or total are inconsistent",
    )
    row.update({
        "vectorless_switching_power_mw": switch_mw,
        "vectorless_internal_power_mw": internal_mw,
        "leakage_power_mw": leakage_mw,
        "vectorless_total_power_mw": total_mw,
        "power_primary_inputs_unannotated": int("PWR-414" in power_text),
        "power_sequential_outputs_unannotated": int("PWR-415" in power_text),
        "power_black_box_outputs_unannotated": int("PWR-428" in power_text),
    })
    row.update({
        "area_report_sha256": sha256(area_path),
        "qor_report_sha256": sha256(qor_path),
        "timing_report_sha256": sha256(timing_path),
        "power_report_sha256": sha256(power_path),
        "dc_log_sha256": sha256(run / "dc.log"),
        "file_list_sha256": sha256(flist_path),
        "git_status_after_sha256": sha256(run / "git_status_after"),
        **{field: sha256(path) for field, path in source_files.items()},
    })
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--expected-git-head")
    args = parser.parse_args()

    root = args.run_root.resolve()
    require((root / "DONE").is_file(), f"paired synthesis is incomplete: {root}")
    script_text = (root / "run_paired_dc.sh").read_text()
    revision_match = re.search(r"^revision=([0-9a-f]{40})$", script_text, re.MULTILINE)
    require(revision_match is not None, "paired runner has no source revision")
    git_head = revision_match.group(1)
    if args.expected_git_head:
        require(git_head == args.expected_git_head,
                f"source revision mismatch: {git_head}")

    def runner_path(variable: str) -> Path:
        match = re.search(rf"^{variable}=(.+)$", script_text, re.MULTILINE)
        require(match is not None, f"paired runner has no {variable} worktree")
        path = Path(match.group(1)).resolve()
        require(path.is_dir(), f"paired runner worktree is missing: {path}")
        return path

    off_root = runner_path("off")
    on_root = runner_path("on")
    require((root / "deps_snapshot_status").read_text().strip() == "ready",
            "dependency snapshot was not frozen")
    dependency_entries = verify_sha256_manifest(root / "deps_files.sha256")
    verify_sha256_manifest(root / "deps_tree_manifest.sha256")

    rows = [
        parse_run(root, "qbs_off", False, off_root, git_head),
        parse_run(root, "qbs_on", True, on_root, git_head),
    ]
    off, on = rows
    for field in ("sdc_sha256", "dc_tcl_sha256", "dont_use_tcl_sha256"):
        require(off[field] == on[field], f"paired synthesis differs in {field}")
    off_area = float(off["total_cell_area"])
    on_area = float(on["total_cell_area"])
    delta_area = on_area - off_area
    delta_percent = 100.0 * delta_area / off_area
    off_standard_cell_area = (
        float(off["combinational_area"]) + float(off["noncombinational_area"])
    )
    on_standard_cell_area = (
        float(on["combinational_area"]) + float(on["noncombinational_area"])
    )
    standard_cell_delta = on_standard_cell_area - off_standard_cell_area
    standard_cell_delta_percent = (
        100.0 * standard_cell_delta / off_standard_cell_area
    )
    macro_delta = float(on["macro_area"]) - float(off["macro_area"])

    fieldnames = list(rows[0])
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "run_root": str(root),
        "git_head": git_head,
        "runner_sha256": sha256(root / "run_paired_dc.sh"),
        "dependency_manifest_sha256": sha256(root / "deps_files.sha256"),
        "dependency_manifest_entries": dependency_entries,
        "qbs_area_delta": delta_area,
        "qbs_area_delta_percent": delta_percent,
        "qbs_off_standard_cell_area": off_standard_cell_area,
        "qbs_on_standard_cell_area": on_standard_cell_area,
        "qbs_standard_cell_area_delta": standard_cell_delta,
        "qbs_standard_cell_area_delta_percent": standard_cell_delta_percent,
        "qbs_macro_area_delta": macro_delta,
        "qbs_off_clk_wns_ns": off["clk_wns_ns"],
        "qbs_on_clk_wns_ns": on["clk_wns_ns"],
        "qbs_clk_wns_delta_ns": (
            float(on["clk_wns_ns"]) - float(off["clk_wns_ns"])
        ),
        "qbs_off_clk_tns_ns": off["clk_tns_ns"],
        "qbs_on_clk_tns_ns": on["clk_tns_ns"],
        "qbs_off_clk_violating_paths": off["clk_violating_paths"],
        "qbs_on_clk_violating_paths": on["clk_violating_paths"],
        "qbs_off_clock_period_ns": off["clock_period_ns"],
        "qbs_on_clock_period_ns": on["clock_period_ns"],
        "qbs_off_leakage_power_mw": off["leakage_power_mw"],
        "qbs_on_leakage_power_mw": on["leakage_power_mw"],
        "qbs_leakage_power_delta_percent": (
            100.0
            * (float(on["leakage_power_mw"]) - float(off["leakage_power_mw"]))
            / float(off["leakage_power_mw"])
        ),
        "qbs_off_vectorless_total_power_mw": off["vectorless_total_power_mw"],
        "qbs_on_vectorless_total_power_mw": on["vectorless_total_power_mw"],
        "qbs_vectorless_total_power_delta_percent": (
            100.0
            * (
                float(on["vectorless_total_power_mw"])
                - float(off["vectorless_total_power_mw"])
            )
            / float(off["vectorless_total_power_mw"])
        ),
        "power_claim_available": False,
        "vectorless_power_comparison_available": True,
        "power_note": (
            "DC vectorless estimates are recorded under identical assumptions, but "
            "primary inputs, sequential outputs, and SRAM black-box outputs are not "
            "activity-annotated. They are not workload-power measurements."
        ),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {args.output_csv} and {args.output_json}")


if __name__ == "__main__":
    main()
