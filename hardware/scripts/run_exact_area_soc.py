#!/usr/bin/env python3
"""Build matched SoC ablations for exact-backend area specialization."""

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


APPS = ['perf_exact_global_fp16_probe', 'perf_exact_global_reduction_probe', 'perf_exact_global_widening_probe', 'perf_exact_global_widening_stream_probe', 'perf_exact_sparse_window_probe', 'perf_rce_exact_mixed', 'perf_rce_exact_slide', 'perf_rce_exact_load_seed', 'perf_rce_exact_slide_seed', 'perf_reduction_short_stream_probe', 'perf_masked_reduction_stream_probe', 'reduction_audit_alias', 'reduction_audit_empty', 'reduction_audit_context', 'reduction_audit_seed', 'reduction_audit_tail', 'reduction_audit_widen_mask', 'reduction_audit_group_fp', 'reduction_rce_exact_mixed', 'reduction_rce_fp_mixed', 'reduction_audit_ordered_fp16', 'reduction_audit_ordered_rounding']


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--reference", type=Path,
        default=root / "hardware/build/ordered_soc_v4/scalar",
        help="Existing full-profile VCS filelist and source_manifest.json",
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--preserve-reference-flags", action="store_true",
                        help="Keep previous area refinements enabled identically in both builds")
    parser.add_argument("--root-only-cache", action="store_true", help="Keep reduction victims only in Lane zero")
    parser.add_argument("--prune-legacy-fp", action="store_true", help="Remove unreachable legacy FP background state in the fully covered profile")
    parser.add_argument("--compact-segments", action="store_true", help="Use eight 32-bit exponent windows in the candidate")
    parser.add_argument("--direct-bin-read", action="store_true", help="Read exact update operands from registered bins")
    parser.add_argument("--wide-segments", action="store_true", help="Use four 64-bit exponent windows")
    parser.add_argument("--current-integration-rtl", action="store_true", help="Freeze current Lane sequencer, SLDU and address generator on both sides")
    parser.add_argument("--shared-rce-add", action="store_true", help="Share the ordered backend with RCE FP64 completion")
    parser.add_argument("--independent-ordered-mask", action="store_true", help="Remove ready from ordered request mask generation")
    parser.add_argument("--context-issue-cut", action="store_true", help="Select pair/root issue from registered progress without ready feedback")
    parser.add_argument("--arithmetic-only-forward", action="store_true", help="Route non-arithmetic consumers through the existing VRF path")
    parser.add_argument("--static-legacy-state", action="store_true", help="Elaborate disabled VALU/VMFPU legacy state as constants")
    parser.add_argument("--compact-ordered-backend", action="store_true", help="Share scalar ADD output storage across formats")
    parser.add_argument("--static-ordered-arbiter", action="store_true", help="Use fixed-index rotating arbitration")
    parser.add_argument("--app", action="append", default=[], help="Explicit suite instead of the default 22 apps")
    parser.add_argument("--mechanism", choices=["none", "extract", "update", "both"], default="both")
    parser.add_argument("--normalize", action="store_true", help="Also enable shared normalization in the candidate")
    parser.add_argument("--normalize-both", action="store_true", help="Keep validated normalization in both builds")
    parser.add_argument("--forward-capture", action="store_true", help="Freeze requester RTL and enable shared capture in candidate only")
    parser.add_argument("--shared-issue", action="store_true", help="Read issue descriptors from their existing queue slots")
    parser.add_argument("--collision-forward", action="store_true", help="Enable exact-bin collision bypass in candidate only")
    parser.add_argument("--ordered-profile", action="store_true", help="Bind a read-only ordered adder demand observer (FP-enabled configuration)")
    parser.add_argument("--shared-ordered", type=int, choices=[1, 2], help="Number of physical ordered ADD units in candidate")
    parser.add_argument("--prune-legacy-int", action="store_true", help="Specialize away background integer tree contexts when RCE covers them")
    parser.add_argument("--extra-app", action="append", default=[])
    parser.add_argument("--reuse-baseline", type=Path,
                        help="Reuse a matching baseline build/regression; verify inputs before linking")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=3600,
                        help="Wall-clock seconds per simulation; architectural watchdog is unchanged")
    parser.add_argument("--min-performance-apps", type=int, default=5,
                        help="Declared minimum performance programs for the selected suite")
    args = parser.parse_args()
    apps = list(dict.fromkeys([*(args.app or APPS), *args.extra_app]))
    if args.jobs < 1 or args.timeout < 1 or args.min_performance_apps < 0:
        parser.error("jobs and timeout must be positive")
    reference = args.reference.resolve()
    reference_manifest = json.loads((reference / "source_manifest.json").read_text())
    for path,digest in reference_manifest['sources'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:
            raise ValueError('Reference source changed: '+path)
    command = reference_manifest["command"]
    lines = (reference / "filelist").read_text().splitlines()
    if not any("+define+ARA_RED_EXACT_GLOBAL_4LANE" in line for line in lines):
        raise SystemExit("Reference must enable global exact reduction")
    if args.shared_rce_add and not all(any(line.startswith(prefix) for line in lines)
        for prefix in ('+define+ARA_RED_SHARED_ORDERED_ADD', '+define+ARA_RED_RCE_FP64_SUM')):
        raise SystemExit('Shared RCE requires an existing shared ordered backend and FP64 completion')
    if (args.compact_ordered_backend or args.static_ordered_arbiter) and not any(line.startswith('+define+ARA_RED_SHARED_ORDERED_ADD') for line in lines):
        raise SystemExit('Ordered backend refinements require shared ordered ADD')
    if args.context_issue_cut and not any(line.startswith('+define+ARA_RED_CONTEXT_FLOW_4LANE') for line in lines):
        raise SystemExit('Context issue cut requires tagged context flow')
    if args.independent_ordered_mask and not any(line.startswith('+define+ARA_RED_SHARED_ORDERED_ADD') for line in lines):
        raise SystemExit('Independent ordered mask requires the shared ordered backend')
    removed_prefixes = (
        "+define+ARA_RED_SHARED_FINALIZE_EXTRACT", "+define+ARA_RED_SHARED_EXACT_UPDATE", "+define+ARA_RED_SHARED_EXACT_NORMALIZE",
        "+define+ARA_RED_SHARED_FORWARD_CAPTURE", "+define+ARA_RED_SHARED_ISSUE_DESCRIPTOR",
        "+define+ARA_RED_EXACT_COLLISION_FORWARD", "+define+ARA_RED_SHARED_ORDERED_ADD",
        "+define+ARA_RED_SHARED_ORDERED_UNITS", "+define+ARA_RED_PRUNE_LEGACY_INT_STREAM")
    if not args.preserve_reference_flags:
        lines = [line for line in lines if not line.startswith(removed_prefixes)]
    if args.root_only_cache or not args.preserve_reference_flags:
        lines = [line for line in lines if not line.startswith('+define+ARA_RED_ROOT_ONLY_RESULT_CACHE')]
    if args.prune_legacy_fp or not args.preserve_reference_flags:
        lines = [line for line in lines if not line.startswith('+define+ARA_RED_PRUNE_LEGACY_FP_STREAM')]
    if args.compact_segments or not args.preserve_reference_flags:
        lines = [line for line in lines if not line.startswith('+define+ARA_RED_COMPACT_EXACT_SEGMENTS')]
    if args.shared_rce_add or not args.preserve_reference_flags:
        lines = [line for line in lines if not line.startswith('+define+ARA_RED_SHARED_RCE_ADD')]
    if args.independent_ordered_mask or not args.preserve_reference_flags:
        lines = [line for line in lines if not line.startswith('+define+ARA_RED_ORDERED_READY_INDEPENDENT_MASK')]
    if args.context_issue_cut or not args.preserve_reference_flags:
        lines = [line for line in lines if not line.startswith('+define+ARA_RED_CONTEXT_ISSUE_CUT')]
    if args.arithmetic_only_forward or not args.preserve_reference_flags:
        lines = [line for line in lines if not line.startswith('+define+ARA_RED_ARITHMETIC_ONLY_FORWARD')]
    for enabled, macro in ((args.wide_segments, 'ARA_RED_WIDE_EXACT_SEGMENTS'),
                           (args.direct_bin_read, 'ARA_RED_EXACT_DIRECT_BIN_READ'),
                           (args.static_legacy_state, 'ARA_RED_STATIC_LEGACY_STATE'),
                           (args.compact_ordered_backend, 'ARA_RED_COMPACT_ORDERED_BACKEND'),
                           (args.static_ordered_arbiter, 'ARA_RED_STATIC_ORDERED_ARBITER')):
        if enabled or not args.preserve_reference_flags:
            lines = [line for line in lines if not line.startswith('+define+' + macro)]
    if args.normalize_both:
        lines.insert(0, "+define+ARA_RED_SHARED_EXACT_NORMALIZE=1")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    elf_dir = out / 'elfs'
    elf_dir.mkdir()
    for app in apps:
        shutil.copy2(root / 'apps/bin' / app, elf_dir / app)
    (out / "configuration.json").write_text(json.dumps({
        "reference": str(reference), "mechanism": args.mechanism, "normalize": args.normalize,
        "normalize_both": args.normalize_both, "forward_capture": args.forward_capture,
        "shared_issue": args.shared_issue,
        "collision_forward": args.collision_forward,
        "apps": apps, "jobs": args.jobs, "timeout": args.timeout,
        "ordered_profile": args.ordered_profile,
        "shared_ordered": args.shared_ordered,
        "prune_legacy_int": args.prune_legacy_int,
        "reuse_baseline": str(args.reuse_baseline.resolve()) if args.reuse_baseline else None,
        "preserve_reference_flags": args.preserve_reference_flags, "root_only_cache": args.root_only_cache,
        "min_performance_apps": args.min_performance_apps,
        "prune_legacy_fp": args.prune_legacy_fp,
        "compact_segments": args.compact_segments,
        "direct_bin_read": args.direct_bin_read,
        "wide_segments": args.wide_segments,
        "current_integration_rtl": args.current_integration_rtl,
        "shared_rce_add": args.shared_rce_add,
        "independent_ordered_mask": args.independent_ordered_mask,
        "static_legacy_state": args.static_legacy_state,
        "compact_ordered_backend": args.compact_ordered_backend,
        "static_ordered_arbiter": args.static_ordered_arbiter,
        "context_issue_cut": args.context_issue_cut,
        "arithmetic_only_forward": args.arithmetic_only_forward,
        "elf_sha256": {app: hashlib.sha256((elf_dir/app).read_bytes()).hexdigest() for app in apps},
    }, indent=2) + "\n")
    frozen = out / "rtl"
    frozen.mkdir()
    changed_sources = {
        "fp32_exact_reduction_accum.sv": root / "hardware/src/lane/fp32_exact_reduction_accum.sv",
        "fp32_exact_reduction_finalize.sv": root / "hardware/src/lane/fp32_exact_reduction_finalize.sv",
    }
    if args.current_integration_rtl:
        for relative in ('lane/lane_sequencer.sv', 'sldu/sldu.sv', 'vlsu/addrgen.sv'):
            source = root / 'hardware/src' / relative
            changed_sources[source.name] = source
    if args.static_legacy_state:
        for name in ("valu.sv", "vmfpu.sv"):
            changed_sources[name] = root / "hardware/src/lane" / name
    if args.compact_ordered_backend or args.static_ordered_arbiter:
        changed_sources["shared_ordered_adder.sv"] = root / "hardware/src/reduction/shared_ordered_adder.sv"
    if args.forward_capture:
        changed_sources["operand_requester.sv"] = root / "hardware/src/lane/operand_requester.sv"
    if args.arithmetic_only_forward:
        changed_sources["operand_requester.sv"] = root / "hardware/src/lane/operand_requester.sv"
    if args.root_only_cache:
        changed_sources["operand_requester.sv"] = root / "hardware/src/lane/operand_requester.sv"
        changed_sources["lane.sv"] = root / "hardware/src/lane/lane.sv"
    if args.prune_legacy_fp:
        changed_sources["vmfpu.sv"] = root / "hardware/src/lane/vmfpu.sv"
    if args.context_issue_cut:
        changed_sources["vmfpu.sv"] = root / "hardware/src/lane/vmfpu.sv"
    if args.independent_ordered_mask:
        changed_sources["vmfpu.sv"] = root / "hardware/src/lane/vmfpu.sv"
    if args.shared_rce_add:
        changed_sources["ara.sv"] = root / "hardware/src/ara.sv"
        for name in ("shared_ordered_adder.sv", "reduction_completion_engine.sv"):
            changed_sources[name] = root / "hardware/src/reduction" / name
    if args.shared_issue:
        for name in ("valu.sv", "vmfpu.sv"):
            changed_sources[name] = root / "hardware/src/lane" / name
    if args.prune_legacy_int:
        changed_sources["valu.sv"] = root / "hardware/src/lane/valu.sv"
    if args.shared_ordered:
        for name in ("vmfpu.sv", "vector_fus_stage.sv", "lane.sv"):
            changed_sources[name] = root / "hardware/src/lane" / name
        changed_sources["ara.sv"] = root / "hardware/src/ara.sv"
        changed_sources["ara_pkg.sv"] = root / "hardware/include/ara_pkg.sv"
    for name, source in changed_sources.items():
        target = frozen / name
        shutil.copy2(source, target)
        matches = [i for i, line in enumerate(lines) if line.endswith("/" + name)]
        if len(matches) != 1:
            raise SystemExit(f"Expected one {name} in reference filelist")
        lines[matches[0]] = str(target)
    if args.shared_ordered:
        target = frozen / "shared_ordered_adder.sv"
        shutil.copy2(root / "hardware/src/reduction/shared_ordered_adder.sv", target)
        lines.append(str(target))
    if args.ordered_profile:
        target = frozen / "ordered_area_profile.sv"
        shutil.copy2(root / "hardware/tb/ordered_area_profile.sv", target)
        lines.append(str(target))

    # Prepare both builds before running either, so current RTL cannot change
    # between the baseline and candidate snapshots.
    jobs = []
    # The comparator uses the legacy name scalar for its candidate directory.
    for mode in ("baseline", "scalar"):
        directory = out / mode
        if mode == "baseline" and args.reuse_baseline:
            reused = args.reuse_baseline.resolve()
            old_manifest = json.loads((reused / "source_manifest.json").read_text())
            for path, digest in old_manifest["sources"].items():
                if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
                    raise ValueError("Reused source was modified: " + path)
            def signature(filelist):
                return [("source", Path(line).name, hashlib.sha256(Path(line).read_bytes()).hexdigest())
                        if line.startswith("/") else ("option", line) for line in filelist]
            if signature(lines) != signature((reused / "filelist").read_text().splitlines()):
                raise ValueError("Reused baseline filelist differs in sources or options")
            def compile_options(cmd):
                normalized = cmd.copy()
                normalized[normalized.index("-f") + 1] = "<filelist>"
                return normalized
            if compile_options(command) != compile_options(old_manifest["command"]):
                raise ValueError("Reused baseline compiler options differ")
            directory.symlink_to(reused, target_is_directory=True)
            (out / "baseline_reuse_audit.json").write_text(json.dumps({
                "directory": str(reused), "source_files_verified": len(old_manifest["sources"]),
                "filelist_and_compiler_options_match": True,
                "manifest_sha256": hashlib.sha256((reused / "source_manifest.json").read_bytes()).hexdigest(),
                "note": "Input match only; the comparator separately requires complete passing tests and matching ELFs.",
            }, indent=2) + "\n")
            continue
        directory.mkdir()
        selected = lines.copy()
        if mode == "scalar":
            if args.wide_segments:
                selected.insert(0, '+define+ARA_RED_WIDE_EXACT_SEGMENTS=1')
            if args.direct_bin_read:
                selected.insert(0, '+define+ARA_RED_EXACT_DIRECT_BIN_READ=1')
            if args.static_legacy_state:
                selected.insert(0, "+define+ARA_RED_STATIC_LEGACY_STATE=1")
            if args.compact_ordered_backend:
                selected.insert(0, '+define+ARA_RED_COMPACT_ORDERED_BACKEND=1')
            if args.static_ordered_arbiter:
                selected.insert(0, '+define+ARA_RED_STATIC_ORDERED_ARBITER=1')
            if args.context_issue_cut:
                selected.insert(0, '+define+ARA_RED_CONTEXT_ISSUE_CUT=1')
            if args.arithmetic_only_forward:
                selected.insert(0, '+define+ARA_RED_ARITHMETIC_ONLY_FORWARD=1')
            if args.independent_ordered_mask:
                selected.insert(0, '+define+ARA_RED_ORDERED_READY_INDEPENDENT_MASK=1')
            if args.shared_rce_add:
                selected.insert(0, '+define+ARA_RED_SHARED_RCE_ADD=1')
            if args.compact_segments:
                selected.insert(0, '+define+ARA_RED_COMPACT_EXACT_SEGMENTS=1')
            if args.prune_legacy_fp:
                selected.insert(0, '+define+ARA_RED_PRUNE_LEGACY_FP_STREAM=1')
            if args.root_only_cache:
                selected.insert(0, '+define+ARA_RED_ROOT_ONLY_RESULT_CACHE=1')
            if args.mechanism in ("extract", "both"):
                selected.insert(0, "+define+ARA_RED_SHARED_FINALIZE_EXTRACT=1")
            if args.mechanism in ("update", "both"):
                selected.insert(0, "+define+ARA_RED_SHARED_EXACT_UPDATE=1")
            if args.normalize and not args.normalize_both:
                selected.insert(0, "+define+ARA_RED_SHARED_EXACT_NORMALIZE=1")
            if args.forward_capture:
                selected.insert(0, "+define+ARA_RED_SHARED_FORWARD_CAPTURE=1")
            if args.shared_issue:
                selected.insert(0, "+define+ARA_RED_SHARED_ISSUE_DESCRIPTOR=1")
            if args.collision_forward:
                selected.insert(0, "+define+ARA_RED_EXACT_COLLISION_FORWARD=1")
            if args.shared_ordered:
                selected.insert(0, "+define+ARA_RED_SHARED_ORDERED_ADD=1")
                selected.insert(0, f"+define+ARA_RED_SHARED_ORDERED_UNITS={args.shared_ordered}")
            if args.prune_legacy_int:
                selected.insert(0, "+define+ARA_RED_PRUNE_LEGACY_INT_STREAM=1")
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
                 '--elf-dir', str(elf_dir),
                 "--sim", str(directory / "simv"), "--out", str(directory / "regression"),
                 "--jobs", str(args.jobs), "--timeout", str(args.timeout)]
        if args.ordered_profile:
            audit.extend(["--sim-arg", "+AREA_ORDERED_PROFILE"])
        audit.extend(apps)
        jobs.append((directory, build, audit))
    if args.prepare_only:
        print(f"Prepared matched builds in {out}; no compiler or simulator launched")
        return
    def execute(job):
        directory, build, audit = job
        with (directory / "compile.stdout.log").open("w") as log:
            subprocess.run(build, cwd=directory, stdout=log, stderr=subprocess.STDOUT, check=True)
        with (directory / "audit.log").open("w") as log:
            subprocess.run(audit, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
    # Separate working directories and immutable sources make the two builds
    # independent. --jobs applies per mode, i.e. at most 2*jobs simulations.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute, job) for job in jobs]
        for future in futures:
            future.result()
    if args.reuse_baseline:
        deadline = time.monotonic() + args.timeout
        manifest = out / "baseline/regression/manifest.json"
        while True:
            try:
                complete = {t["app"] for t in json.loads(manifest.read_text())["tests"]} == set(apps)
            except (FileNotFoundError, json.JSONDecodeError):
                # The audit driver updates this file as each result completes.
                complete = False
            if complete:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("Reused baseline suite has not finished")
            time.sleep(10)
    subprocess.run([sys.executable, str(root / "hardware/scripts/compare_ordered_add_runs.py"),
                    str(out), '--min-performance-apps', str(args.min_performance_apps)], check=True)


if __name__ == "__main__":
    main()
