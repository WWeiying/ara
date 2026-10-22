#!/usr/bin/env python3
"""Build new gap37 ELFs and strictly precheck on Spike only. Never invokes VCS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "apps/riscv-tests/isa/rv64uv"
OUT = ROOT / "verification/out/gap37-csr-analysis-20261004-01"
BASE = ROOT / "verification/out/gap35-vector-checked-preflight-20261004-03"
CASES = {"gap37_csr_alias_tvm": (52, 7, 626), "gap37_csr_counters": (22, 0, 245)}
SENTINEL = 0x1122334455667788
OPS = ((1, 11, 0x8000000100000240), (2, 11, 0x0001000200000022),
       (3, 11, 0x8000000000000200), (5, 2, 2), (6, 2, 2), (7, 2, 2))


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_probes(name):
    rows = []

    def add(csr, op, rs, priv, legal, old):
        rows.append((priv, (csr << 20) | (rs << 15) | (op << 12) | (13 << 7) | 0x73,
                     int(legal), old if legal else SENTINEL))

    def update(old, op, value):
        return value if op in (1, 5) else old | value if op in (2, 6) else old & ~value

    if name == "gap37_csr_alias_tvm":
        for mask in (0, 0x222):
            for priv in (3, 1):
                enabled = 0x208
                for op, rs, value in OPS:
                    old = enabled & mask
                    add(0x104, op, rs, priv, True, old)
                    enabled = (enabled & ~mask) | (update(old, op, value) & mask)
        for tvm in (0, 1):
            for priv in (3, 1):
                for op in (1, 2, 3, 5, 6, 7, 2):
                    # The last access is the explicit CSRRS x0 read.
                    rs = 0 if op >= 5 else 11
                    add(0x180, op, rs, priv, not tvm or priv == 3, 0)
                p, insn, legal, old = rows[-1]
                rows[-1] = (p, insn & ~(31 << 15), legal, old)
    elif name == "gap37_csr_counters":
        inhibit = 5
        for op, value in zip((1, 2, 3, 5, 6, 7), (0, 5, 1, 1, 4, 1)):
            add(0x320, op, value if op >= 5 else 11, 3, True, inhibit)
            inhibit = update(inhibit, op, value)
        for csr in (0xb00, 0xb02):
            count = 0x1234567811223344
            for op, rs, value in OPS:
                add(csr, op, rs, 3, True, count)
                count = update(count, op, value)
            add(csr, 2, 0, 3, True, count)
            add(csr, 7, 0, 3, True, count)
    else:
        raise ValueError("Unknown case")
    assert len(rows) == CASES[name][0]
    return rows


def validate_log(name, log, stub):
    phases, illegal, checks = CASES[name]
    summary = re.findall(re.escape(name) +
        r" phases=(\d+) checks=(\d+) illegal=(\d+) legal=(\d+) failures=(\d+)", log)
    if len(summary) != 1 or tuple(map(int, summary[0])) != (phases, checks, illegal, phases - illegal, 0):
        raise ValueError("Missing, duplicate, incomplete or failing summary")
    if log.splitlines().count("PASSED: " + name) != 1 or "FAIL:" in log:
        raise ValueError("Missing unique PASS or explicit failure")
    rows = re.findall(r"^PROBE phase=(\d+) priv=(\d+) insn=([0-9a-f]+) legal=(\d+) "
                      r"cause=([0-9a-f]+) epc=([0-9a-f]+) tval=([0-9a-f]+) rd=([0-9a-f]+)$",
                      log, re.MULTILINE)
    if len(rows) != phases or stub % 64:
        raise ValueError("Missing access evidence or invalid ELF stub symbol")
    evidence = []
    for i, (row, expected) in enumerate(zip(rows, expected_probes(name))):
        observed = tuple(int(v, 10 if j in (0, 1, 3) else 16) for j, v in enumerate(row))
        priv, insn, legal, old = expected
        want = (i, priv, insn, legal, {1: 9, 3: 11}[priv] if legal else 2,
                stub + (4 if legal else 0), 0 if legal else insn, old)
        if observed != want:
            raise ValueError(f"Probe {i}: {observed!r} != independent expected {want!r}")
        evidence.append(dict(zip(("phase", "priv", "insn", "legal", "cause", "epc", "tval", "rd"), observed)))
    return dict(phases=phases, illegal=illegal, legal=phases-illegal, checks=checks,
                failures=0, probes=evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", default="preflight-01")
    args = parser.parse_args()
    if not re.fullmatch(r"preflight-\d{2}", args.attempt):
        parser.error("attempt must be preflight-NN")
    audit = json.loads((OUT / "source-audit.json").read_text())
    out = OUT / args.attempt
    out.mkdir(exist_ok=False)
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
    runtime_sources = [common / n for n in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c")]
    spike_sources = [runtime / n for n in ("crt.S", "syscalls.c")]
    sources = [Path(__file__), DEST / "csr_gap35_body.h", DEST / "gap37_csr_ops.h",
               *[DEST / (name + ".c") for name in CASES], *runtime_sources, *spike_sources,
               common / "link.ld", runtime / "test.ld", OUT / "source-audit.json",
               OUT / "native-points.json", ROOT / "verification/tests/build_gap35_csr.py",
               ROOT / "verification/coverage/reviewed_20261004/audit_readonly.py"]
    hashes = {str(p): digest(p) for p in sources}
    save(out / "source-hashes.json", hashes)
    save(out / "tool-hashes.json", {str(p): digest(p) for p in
        (cc, llvm / "bin/ld.lld", ROOT / "install/riscv-isa-sim/bin/spike")})
    commands = []

    def command(argv, log, timeout=60):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(ROOT), timeout_s=timeout, log=str(log)))
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout)
        with log.open("xb") as stream:
            stream.write(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}): {log}")
        return (result.stdout + result.stderr).decode()

    results, selection = [], []
    try:
        objects, spike_objects = [], []
        spike_flags = [*flags, "-D__SPIKE__=1", "-DPREALLOCATE=1", "-DG35_TRACE=1"]
        for srcs, opts, objs, prefix in ((runtime_sources, flags, objects, ""),
                                       (spike_sources, spike_flags, spike_objects, "spike_")):
            for source in srcs:
                obj = out / (prefix + source.name + ".o")
                command([cc, *opts, *includes, "-c", source, "-o", obj], out / (obj.name + ".build.log"))
                objs.append(obj)
        for name in CASES:
            started = time.monotonic()
            source = DEST / (name + ".c")
            elf, spike_elf = out / (name + ".elf"), out / (name + ".spike")
            for binary, opts, objs, link, libs in (
                (elf, flags, objects, common / "link.ld", ["-lm", f"-L{llvm.resolve() / 'lib/generic'}", "-lclang_rt.builtins-riscv64"]),
                (spike_elf, spike_flags, spike_objects, runtime / "test.ld", [])):
                command([cc, *opts, *includes, "-Wall", "-Wextra", "-Werror", "-fuse-ld=lld",
                    "-static", "-nostdlib", f"-T{link}", source, *objs, *libs, "-o", binary],
                    Path(str(binary) + ".build.log"))
                command([llvm / "bin/llvm-objdump", "-d", binary], Path(str(binary) + ".dis"))
                command([llvm / "bin/llvm-readelf", "-lWs", binary], Path(str(binary) + ".readelf"))
            symbols = command([llvm / "bin/llvm-nm", spike_elf], out / (name + ".nm"))
            stub_rows = re.findall(r"^([0-9a-f]+) [bB] csr_gap35_stub$", symbols, re.MULTILINE)
            if len(stub_rows) != 1:
                raise ValueError("Missing unique ELF probe stub")
            log = out / (name + ".spike.log")
            output = command([ROOT / "install/riscv-isa-sim/bin/spike", "--isa=rv64gcv_zfh",
                "--pmpregions=0", "--varch=vlen:1024,elen:64", spike_elf], log)
            evidence = validate_log(name, output, int(stub_rows[0], 16))
            seconds = round(time.monotonic() - started, 3)
            assert seconds <= 600
            evidence.update(status="SPIKE_PASS_ONLY", elapsed_build_and_precheck_s=seconds,
                elf_sha256=digest(elf), spike_elf_sha256=digest(spike_elf), log_sha256=digest(log),
                oracle="Exact independent instruction/rd/cause/EPC/TVAL model; C checks exact state and restoration. No DUT coverage claim.")
            save(out / (name + ".evidence.json"), evidence)
            results.append(dict(name=name, **{k: evidence[k] for k in ("status", "phases", "checks", "illegal", "elapsed_build_and_precheck_s")}))
            selection.append(dict(name="rvv:" + name, binary=str(elf), timeout_s=600,
                sources=[str(source), str(DEST / "gap37_csr_ops.h"), str(DEST / "csr_gap35_body.h"), str(Path(__file__))],
                evidence=[str(log), str(out / (name + ".evidence.json")), str(out / "source-hashes.json"), str(OUT / "source-audit.json")],
                targets=["ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i"],
                source_audit=str(OUT / "source-audit.json"), rationale=audit["cases"][name]["rationale"],
                predicted_missing_native_branches=[p["native"] for p in audit["cases"][name]["branches"]]))
            print(name, "Spike PASS", evidence["phases"], "phases", evidence["checks"], "checks", seconds, "s", flush=True)
        assert all(digest(Path(p)) == h for p, h in hashes.items()), "Read-only inputs changed"
        save(out / "selection-draft.json", dict(baseline=str(BASE), baseline_bits=str(BASE / "combined-bits.json"),
             status="DRAFT_SPIKE_ONLY_NOT_SUBMITTED", cases=selection,
             admission="Parent must independently admit against frozen image and assess strict terminal/trace evidence; no gain until passing same-image VCS delta."))
    except Exception as exc:
        save(out / "failure.json", dict(type=type(exc).__name__, error=str(exc)))
        raise
    finally:
        save(out / "commands.json", commands)
        save(out / "spike-results.json", results)


if __name__ == "__main__":
    main()
