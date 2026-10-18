#!/usr/bin/env python3
"""Build and compare the original and scalar ordered paths with matched inputs."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


APPS = [
    "perf_ordered_nonduplicate_probe",
    "perf_ordered_reduction_interleave_probe",
    "perf_widening_ordered_stream_probe",
    "perf_masked_ordered_alias_probe",
    "perf_reduction_e64_stream_probe",
    "reduction_audit_ordered_fp16",
    "reduction_audit_ordered_rounding",
    "reduction_audit_widen_mask",
    "reduction_audit_empty",
    "reduction_audit_alias",
    "reduction_rce_ordered_boundary",
    "reduction_rce_fp_mixed",
    "perf_rce_fp64_mixed",
    "reduction_rce_exact_mixed",
]


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--reference", type=Path,
        default=root / "hardware/build/rce/paper_iscas_v2/full",
        help="Existing full-profile VCS filelist and source_manifest.json",
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--output-register", action="store_true",
                        help="Also move the scalar ADD register to the output")
    args = parser.parse_args()
    reference = args.reference.resolve()
    command = json.loads((reference / "source_manifest.json").read_text())["command"]
    lines = (reference / "filelist").read_text().splitlines()
    if not any("+define+ARA_RED_ORDERED_FAST_4LANE" in line for line in lines):
        raise SystemExit("Reference must enable the original ordered fast path")
    lines = [line for line in lines if not line.startswith((
        "+define+ARA_RED_ORDERED_SCALAR_ADD", "+define+ARA_RED_ORDERED_ADD_ONLY",
        "+define+ARA_RED_ORDERED_OUTPUT_REG"))]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "configuration.json").write_text(json.dumps({
        "reference": str(reference), "output_register": args.output_register,
        "apps": APPS,
    }, indent=2) + "\n")
    frozen = out / "rtl"
    frozen.mkdir()
    for name, source in {
        "vmfpu.sv": root / "hardware/src/lane/vmfpu.sv",
        "ara_dispatcher.sv": root / "hardware/src/ara_dispatcher.sv",
    }.items():
        target = frozen / name
        shutil.copy2(source, target)
        matches = [i for i, line in enumerate(lines) if line.endswith("/" + name)]
        if len(matches) != 1:
            raise SystemExit(f"Expected one {name} in reference filelist")
        lines[matches[0]] = str(target)

    # Prepare both builds before running either, so current RTL cannot change
    # between the baseline and candidate snapshots.
    jobs = []
    for mode in ("baseline", "scalar"):
        directory = out / mode
        directory.mkdir()
        selected = lines.copy()
        if mode == "scalar":
            selected.insert(0, "+define+ARA_RED_ORDERED_SCALAR_ADD=1")
            if args.output_register:
                selected.insert(0, "+define+ARA_RED_ORDERED_OUTPUT_REG=1")
        filelist = directory / "filelist"
        filelist.write_text("\n".join(selected) + "\n")
        build = command.copy()
        build[build.index("-f") + 1] = str(filelist)
        sources = [Path(line) for line in selected if line.startswith("/")]
        manifest = {
            "command": build,
            "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sources if p.is_file()},
        }
        (directory / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        audit = [sys.executable, str(root / "hardware/scripts/run_reduction_audit.py"),
                 "--sim", str(directory / "simv"), "--out", str(directory / "regression"),
                 "--jobs", "2", "--timeout", "300", *APPS]
        jobs.append((directory, build, audit))
    if args.prepare_only:
        print(f"Prepared matched builds in {out}; no compiler or simulator launched")
        return
    for directory, build, audit in jobs:
        with (directory / "compile.stdout.log").open("w") as log:
            subprocess.run(build, cwd=directory, stdout=log, stderr=subprocess.STDOUT, check=True)
        with (directory / "audit.log").open("w") as log:
            subprocess.run(audit, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run([sys.executable, str(root / "hardware/scripts/compare_ordered_add_runs.py"),
                    str(out)], check=True)


if __name__ == "__main__":
    main()
