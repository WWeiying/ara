#!/usr/bin/env python3
"""Freeze and compare the request/Lane/AKV/QBS timing candidate on VCS."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from run_operand_ext import ROOT, save, sha, verify
from run_shared_alu_soc import execute

sys.path.insert(0, str(ROOT / "verification"))
from ara_verify.vcs_source_manifest import collect


RTL = (
    "hardware/src/lane/simd_mul_shared.sv",
    "hardware/src/lane/simd_mul_shared_product.sv",
    "hardware/src/lane/simd_fma_shared.sv",
    "hardware/src/vlsu/akv/akv_engine.sv",
    "hardware/src/vlsu/qbs/qbs_block_adapter.sv",
)
CASES = {
    "vsaxpy_asm": None,
    "rv64uv-ara-vfmacc": None,
    "rv64uv-ara-vsetvli": None,
    "qbs_control_smoke": "QBS control smoke (enabled): PASS",
    "akv_context_smoke": "AKV context smoke: PASS",
    "qbs_akv_handoff_smoke": "QBS/AKV handoff smoke: PASS",
    "llama_qwen25_shape_decode_n32_qbs": "QBS_REAL_BENCH case=shape_decode_n32_qbs result=PASS",
}
REQUEST_DEFINE = "+define+ARA_REGISTER_ACCELERATOR_REQUEST=1"
TIMERS = (
    ("task_cycles", r"(?m)^\[PERF\]\s+total_cycles\s*:\s*(\d+)"),
    ("projection_cycles", r"\btimed_cycles=(\d+)"),
    ("hw_cycles", r"\[hw-cycles\]:\s*(\d+)"),
    ("finish_ticks", r"\$finish at simulation time\s+(\d+)"),
)


def freeze(out, base, dpi, elf_dir, register_request):
    flags = subprocess.check_output(
        ["make", "-s", "config-check", "optimization_profile=candidate_all",
         "nr_lanes=4", "vlen=1024", "acc_req_register=1"], cwd=ROOT / "hardware",
        text=True,
    ).split("bender_defs=", 1)[1].strip()
    targets = "rtl cv64a6_imafdcv_sv39 tech_cells_generic_include_tc_sram " \
        "tech_cells_generic_include_tc_clk exclude_first_pass_decoder ara_test " \
        "cva6_test notsynthesis"
    bender = [str(ROOT / "hardware/bender"), "script", "verilator", "--no-default-target"]
    for target in targets.split():
        bender += ["-t", target]
    bender += shlex.split(flags) + ["--define", "FOR_VERIFY",
                                   "--define", "COMMON_CELLS_ASSERTS_OFF"]
    flist = out / "bender.f"
    flist.write_bytes(subprocess.check_output(bender, cwd=ROOT / "hardware",
                       env=dict(os.environ, BENDER_LOCAL="true")))
    source = out / "source"
    for row in collect(flist, ROOT, [dpi]):
        original = Path(row["path"])
        if original == flist:
            continue
        if not original.is_relative_to(ROOT):
            raise ValueError(f"build uses non-local source: {original}")
        target = source / original.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        if sha(target) != row["sha256"]:
            raise ValueError(f"source drift during copy: {original}")
    frozen_flist = flist.read_text().replace(str(ROOT) + "/", str(source) + "/")
    if REQUEST_DEFINE not in frozen_flist.splitlines():
        raise ValueError("registered request not selected")
    for line in frozen_flist.splitlines():
        if line.startswith("/") and (not Path(line).is_relative_to(source) or not Path(line).is_file()):
            raise ValueError(f"unsealed filelist input: {line}")
    reference = out / "base_rtl"
    reference.mkdir()
    old_flist = "\n".join(line for line in frozen_flist.splitlines() if line != REQUEST_DEFINE) + "\n"
    for relative in RTL:
        original = source / relative
        if not original.is_file() or str(original) not in old_flist:
            raise ValueError(f"expected timing source absent: {relative}")
        copy = reference / Path(relative).name
        copy.write_bytes(subprocess.check_output(["git", "show", f"{base}:{relative}"], cwd=ROOT))
        old_flist = old_flist.replace(str(original), str(copy))
    (out / "baseline.f").write_text(old_flist)
    if not register_request:
        frozen_flist = "\n".join(line for line in frozen_flist.splitlines()
                                 if line != REQUEST_DEFINE) + "\n"
    (out / "candidate.f").write_text(frozen_flist)
    inputs = out / "elf"
    inputs.mkdir()
    for name in CASES:
        src = elf_dir / name
        shutil.copy2(src if src.is_file() else ROOT / "apps/bin" / name, inputs / name)
        if (inputs / name).read_bytes()[:4] != b"\x7fELF":
            raise ValueError(f"invalid ELF: {name}")
    save(out / "plan.json", dict(baseline=base, cases=list(CASES), bender=bender,
                                register_request=register_request,
                                scope="identical ELF, full SoC, four-lane candidate_all"))
    inputs = [f for f in out.rglob("*") if f.is_file()]
    inputs.extend((Path(__file__).resolve(), Path(__file__).with_name("run_operand_ext.py"),
                   Path(__file__).with_name("run_shared_alu_soc.py"),
                   ROOT / "config/optimizations.mk"))
    save(out / "source-pins.json", {str(f): sha(f) for f in inputs})


def worker(out, dpi):
    verify(out)
    variants = ("baseline", "candidate")
    vcs = shutil.which("vcs")
    if not vcs:
        raise ValueError("VCS not found")

    def build(variant):
        d = out / variant
        d.mkdir()
        command = [
            vcs, "-full64", "-sverilog", "+v2k", "-j8", "-lca", "+nospecify",
            "+notimingchecks", "+vpi", "-top", "ara_tb", "-timescale=1ns/100fs",
            "+define+SIMULATION", "+define+no_warning", "+define+TSMC_NO_WARNING",
            "+define+ARA_NO_FSDB", "+define+ARA_FAIL_FAST_ASSERTS",
            "-f", str(out / f"{variant}.f"), str(out / "source" / dpi.relative_to(ROOT)),
            "-o", "simv", "-l", "compile.log",
        ]
        save(d / "command.json", command)
        if execute(command, d, d / "build.log", 1800) or not (d / "simv").is_file():
            raise ValueError(f"{variant} build failed; see {d}/build.log")
        return sha(d / "simv")

    save(out / "status.json", {"state": "BUILDING"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        images = dict(zip(variants, pool.map(build, variants)))
    save(out / "status.json", {"state": "RUNNING", "simv_sha256": images})
    verify(out)

    def run(job):
        variant, name = job
        d = out / variant / name
        d.mkdir()
        command = [str(out / variant / "simv"), "-no_save",
                   f"+PRELOAD={out}/elf/{name}", f"+TESTCASE={name}",
                   "+NO_FSDB", "+NO_INSTR_TRACE", "+ntb_random_seed=1"]
        save(d / "command.json", command)
        if execute(command, d, d / "run.log", 600):
            raise ValueError(f"VCS did not complete: {variant}/{name}")
        log = (d / "run.log").read_text(errors="replace")
        if ("*** SUCCESS ***" not in log or
                re.search(r"Fatal:|Error:|\*\*\* FAILED \*\*\*", log) or
                (CASES[name] and CASES[name] not in log)):
            raise ValueError(f"missing program success or assertion failed: {variant}/{name}")
        timers = {key: [int(value) for value in re.findall(pattern, log)] for key, pattern in TIMERS}
        if not any(timers.values()):
            raise ValueError(f"no timing evidence: {variant}/{name}")
        save(d / "metrics.json", timers)
        return variant, name, timers

    results = {variant: {} for variant in variants}
    cases = list(CASES)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for start in range(0, len(cases), 2):
            jobs = [(v, n) for n in cases[start:start + 2] for v in variants]
            for variant, name, timers in pool.map(run, jobs):
                results[variant][name] = timers
            save(out / "status.json", {"state": "RUNNING", "measured": results,
                                       "simv_sha256": images})
    verify(out)
    save(out / "status.json", {"state": "PASS", "measured": results, "simv_sha256": images,
                               "scope": "functional smoke; inspect paired cycles before accepting"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--baseline", default="HEAD")
    parser.add_argument("--dpi", type=Path, default=ROOT / "hardware/build/work-dpi/elfloader.o")
    parser.add_argument("--elf-dir", type=Path, default=ROOT / "apps/bin")
    parser.add_argument("--keep-request-fast-path", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    dpi = args.dpi.resolve()
    if args.prepare:
        out.mkdir(parents=True, exist_ok=False)
        base = subprocess.check_output(["git", "rev-parse", args.baseline], cwd=ROOT,
                                       text=True).strip()
        freeze(out, base, dpi, args.elf_dir.resolve(), not args.keep_request_fast_path)
        save(out / "status.json", {"state": "PREPARED"})
    else:
        if json.loads((out / "status.json").read_text())["state"] != "PREPARED":
            raise ValueError("worker requires a new prepared snapshot")
        try:
            worker(out, dpi)
        except Exception as error:
            save(out / "status.json", {"state": "FAIL", "reason": str(error)})
            raise


if __name__ == "__main__":
    main()
