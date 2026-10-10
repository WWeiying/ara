#!/usr/bin/env python3
"""Build isolated gap35 CSR ELFs, Spike-precheck, and emit a runner selection."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "apps/riscv-tests/isa/rv64uv"
AUDIT = ROOT / "verification/tests/gap35_csr_source_audit.json"
BASE = ROOT / "verification/out/gap34-current-20261001-01"
BITS = ROOT / "verification/out/gap35-analysis-20261004-01/baseline-bits.json"
INSTANCE = "ara_tb.dut.i_ara_soc.i_system.i_ariane."
CASES = {
    "csr_gap35_permissions": (132, 126),
    "csr_gap35_counteren": (36, 16),
    "csr_gap35_fp_rw": (75, 27),
}
SENTINEL = 0x1122334455667788


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_log(name, log):
    phases, illegal = CASES[name]
    summary = re.findall(
        re.escape(name) + r" phases=(\d+) checks=(\d+) illegal=(\d+) legal=(\d+) failures=(\d+)", log)
    if len(summary) != 1:
        raise ValueError("missing or duplicate summary")
    p, checks, bad, good, errors = map(int, summary[0])
    if (p, bad, good, errors) != (phases, illegal, phases - illegal, 0) or checks < 8 * p:
        raise ValueError("incomplete or failing selfcheck")
    if log.splitlines().count("PASSED: " + name) != 1 or "FAIL:" in log:
        raise ValueError("missing unique PASS or explicit failure")
    rows = re.findall(r"^PROBE phase=(\d+) priv=(\d+) insn=([0-9a-f]+) legal=(\d+) "
                      r"cause=([0-9a-f]+) epc=([0-9a-f]+) tval=([0-9a-f]+) rd=([0-9a-f]+)$",
                      log, re.MULTILINE)
    if len(rows) != p:
        raise ValueError("missing per-access evidence")
    entries, base, observed_illegal = [], None, 0
    for index, row in enumerate(rows):
        phase, priv, insn, legal, cause, epc, tval, rd = (
            int(value, 10 if i in (0, 1, 3) else 16) for i, value in enumerate(row))
        if phase != index or priv not in (0, 1, 3) or legal not in (0, 1):
            raise ValueError("invalid phase or privilege")
        if (insn & 0x7f) != 0x73 or ((insn >> 12) & 7) not in (1, 2, 3, 5, 6, 7):
            raise ValueError("not a CSR instruction")
        if cause != (2 if not legal else {0: 8, 1: 9, 3: 11}[priv]):
            raise ValueError("wrong exception cause")
        if tval != (0 if legal else insn):
            raise ValueError("wrong exact TVAL")
        address = epc - (4 if legal else 0)
        if base is None:
            base = address
        if address != base or address % 64:
            raise ValueError("wrong exact EPC")
        if (not legal or (insn >> 7) & 31 == 0) and rd != SENTINEL:
            raise ValueError("destination clobbered")
        observed_illegal += not legal
        entries.append({"phase": phase, "privilege": priv, "instruction": hex(insn),
                        "csr": hex(insn >> 20), "legal": bool(legal), "cause": cause,
                        "epc": hex(epc), "tval": hex(tval), "rd": hex(rd)})
    if observed_illegal != illegal:
        raise ValueError("trap count differs from summary")
    return {"phases": p, "checks": checks, "illegal": bad, "legal": good,
            "failures": errors, "probes": entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=BASE)
    parser.add_argument("--baseline-bits", type=Path, default=BITS)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != ROOT / "verification/out" or not out.name.startswith("gap35-csr-"):
        parser.error("use a new verification/out/gap35-csr-* directory")
    if out.exists():
        parser.error("new output directory required")
    baseline_bits = json.loads(args.baseline_bits.read_text())
    targets = [INSTANCE + "csr_regfile_i", INSTANCE + "commit_stage_i"]
    for target in targets:
        if not any(target in metric for metric in baseline_bits["metrics"].values()):
            parser.error("target absent from baseline: " + target)
    out.mkdir(parents=True)
    audit = json.loads(AUDIT.read_text())
    llvm = ROOT / "install/riscv-llvm"
    cc = llvm / "bin/clang"
    common = ROOT / "apps/common"
    runtime = ROOT / "apps/riscv-tests/benchmarks/common"
    flags = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "--target=riscv64-unknown-elf",
             "-mcmodel=medany", "-mno-relax", "-O2", "-std=gnu99", "-fno-vectorize",
             "-fno-slp-vectorize", "-mno-implicit-float", "-fno-common", "-fno-builtin-printf",
             "-DNR_LANES=4", "-DVLEN=1024"]
    includes = ["-I" + str(ROOT / p) for p in ("apps/include", "apps/common",
        "apps/riscv-tests/isa/macros/scalar", "apps/riscv-tests/isa/macros/vector",
        "apps/riscv-tests/env", "apps/riscv-tests/benchmarks/common")]
    commands = []

    def command(argv, log):
        argv = list(map(str, argv))
        commands.append(argv)
        save(out / "build_commands.json", commands)
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=60)
        log.write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("build failed; inspect " + str(log))
        return result.stdout

    objects, spike_objects = [], []
    for filename in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c"):
        obj = out / (filename + ".o")
        command([cc, *flags, *includes, "-c", common / filename, "-o", obj],
                out / (filename + ".build.log"))
        objects.append(obj)
    spike_flags = [*flags, "-D__SPIKE__=1", "-DPREALLOCATE=1", "-DG35_TRACE=1"]
    for filename in ("crt.S", "syscalls.c"):
        obj = out / ("spike_" + filename + ".o")
        command([cc, *spike_flags, *includes, "-c", runtime / filename, "-o", obj],
                out / ("spike_" + filename + ".build.log"))
        spike_objects.append(obj)
    results, selection = [], []
    source_hashes = {str(p): digest(p) for p in [Path(__file__), AUDIT, DEST / "csr_gap35_body.h",
                                               *[DEST / (n + ".c") for n in CASES]]}
    for name in CASES:
        source = DEST / (name + ".c")
        elf, spike_elf = out / (name + ".elf"), out / (name + ".spike")
        command([cc, *flags, *includes, "-Wall", "-Wextra", "-Werror", "-fuse-ld=lld",
                 "-static", "-nostartfiles", f"-T{common / 'link.ld'}", source, *objects,
                 "-lm", f"-L{llvm.resolve() / 'lib/generic'}", "-lclang_rt.builtins-riscv64", "-o", elf],
                out / (name + ".build.log"))
        command([cc, *spike_flags, *includes, "-Wall", "-Wextra", "-Werror", "-fuse-ld=lld",
                 "-static", "-nostdlib", f"-T{runtime / 'test.ld'}", source, *spike_objects,
                 "-o", spike_elf], out / (name + ".spike.build.log"))
        for binary in (elf, spike_elf):
            command([llvm / "bin/llvm-objdump", "-d", binary], Path(str(binary) + ".dis"))
            command([llvm / "bin/llvm-readelf", "-lWs", binary], Path(str(binary) + ".readelf"))
        argv = [str(ROOT / "install/riscv-isa-sim/bin/spike"), "--isa=rv64gcv_zfh",
                "--pmpregions=0", "--varch=vlen:1024,elen:64", str(spike_elf)]
        started = time.monotonic()
        log = out / (name + ".spike.log")
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired as exc:
            log.write_bytes((exc.stdout or b"") + (exc.stderr or b""))
            save(out / "failure.json", {"name": name, "command": argv, "status": "TIMEOUT"})
            raise
        log.write_bytes(result.stdout + result.stderr)
        row = {"test": "rvv:" + name, "command": argv, "returncode": result.returncode,
               "seconds": round(time.monotonic() - started, 3), "elf": str(elf),
               "elf_sha256": digest(elf), "spike_elf_sha256": digest(spike_elf)}
        results.append(row)
        save(out / "spike_results.json", results)
        if result.returncode:
            raise RuntimeError("Spike failed; inspect " + str(log))
        evidence = validate_log(name, log.read_text())
        evidence.update(row, status="PASS", oracle="ISA selfcheck; Spike-only, no RTL coverage claim")
        row.update({key: evidence[key] for key in ("phases", "checks", "illegal", "legal", "status")})
        save(out / (name + ".evidence.json"), evidence)
        save(out / "spike_results.json", results)
        selection.append({"name": "rvv:" + name, "binary": str(elf),
            "sources": [str(source), str(DEST / "csr_gap35_body.h"), str(Path(__file__)), str(AUDIT)],
            "evidence": [str(log), str(out / (name + ".evidence.json")),
                         str(out / "build_commands.json"), str(out / "source_hashes.json"), str(AUDIT)],
            "source_audit": audit["cases"][name]["source_audit"], "targets": targets,
            "rationale": audit["cases"][name]["rationale"], "timeout_s": 180})
        print("Spike PASS", name, "phases", evidence["phases"], "checks", evidence["checks"], flush=True)
    if any(digest(Path(path)) != value for path, value in source_hashes.items()):
        raise RuntimeError("source changed during build; discard this output")
    save(out / "source_hashes.json", source_hashes)
    save(out / "selection.json", {"baseline": str(args.baseline.resolve()),
        "baseline_bits": str(args.baseline_bits.resolve()), "cases": selection})
    shapes = {metric: {target: {key: row[key] for key in ("width", "checksum")}
                       for target, row in instances.items() if target in targets}
              for metric, instances in baseline_bits["metrics"].items()}
    save(out / "baseline_shapes.json", {"cache": str(args.baseline_bits.resolve()),
        "tests": len(baseline_bits["tests"]), "metrics": shapes,
        "note": "Raw bitmap shapes only, not DVE denominators or measured new coverage."})
    print("Selection:", out / "selection.json")


if __name__ == "__main__":
    main()
