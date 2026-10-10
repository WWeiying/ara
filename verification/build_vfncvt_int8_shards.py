#!/usr/bin/env python3
"""Build/freeze directed test inputs and validate their ordinal union in Spike.

Uses only the existing LLVM, Ara runtime, and restart-enabled golden Spike.
Does not invoke make (which regenerates shared link.ld), RTL tools, or VCS.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def catalog():
    """Independent VLEN=1024 case/observation geometry, no numeric oracle."""
    result = []

    def add(op, rm, span, active, **description):
        result.append(dict(ordinal=len(result), op=op, rm=rm,
                           byte_checks=span, active_checks=active,
                           csr_checks=3, **description))

    boundaries = [0xb800, 0xb801, 0x57f8, 0x57ff,
                  0xd804, 0xd807, 0x5bfc, 0x5bff]
    for op in range(4):
        for rm in range(5):
            for kind, n in enumerate([73, 16, 16, 16]):
                add(op, rm, n, n, category="batch", kind=kind)
            for half in boundaries:
                add(op, rm, 1, 1, category="boundary", half=f"{half:04x}")
    for lmul in [5, 6, 7, 0, 1, 2]:
        n = 128 >> (8 - lmul) if lmul > 3 else 128 << lmul
        for op in range(4):
            for policy in range(6):
                vl, start = n, 0
                if policy in (1, 2):
                    vl, start = n - 3, 5
                elif policy == 4:
                    vl, start = n - 1, n
                elif policy == 5:
                    vl = 0
                active = sum(policy != 3 and (policy != 1 or
                             ((0x69 if (i // 8) & 1 else 0xa6) >> (i % 8)) & 1)
                             for i in range(start, vl))
                add(op, 3, max(n, 128), active, category="geometry",
                    lmul=lmul, vl=vl, vstart=start, policy=policy)
    for op in range(4):
        for rm in range(5):
            for half in [0xd800, 0xd801, 0xd802, 0xdbfc]:
                add(op, rm, 1, 1, category="extra", half=f"{half:04x}")
    assert len(result) == 464
    return result


def totals(entries):
    return dict(case_count=len(entries), **{
        key: sum(entry[key] for entry in entries)
        for key in ("byte_checks", "active_checks", "csr_checks")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spike", type=Path, default=Path(
        "/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike"))
    args = parser.parse_args()
    root, out, spike = args.root.resolve(), args.output.resolve(), args.spike.resolve()
    inputs = out / "inputs"
    source = inputs / "source"
    if source.exists() or (out / "manifest.json").exists():
        parser.error("output already has a snapshot/manifest; use a new output directory")
    source.mkdir(parents=True)
    build, logs = out / "build", out / "logs"
    build.mkdir()
    logs.mkdir()
    compiler = (root / "install/riscv-llvm/bin/clang").resolve()

    def snapshot(relative):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
        return target

    test_rel = Path("apps/riscv-tests/isa/rv64uv/vfncvt_int8.c")
    test = snapshot(test_rel)
    snapshot(Path("verification/build_vfncvt_int8_shards.py"))
    for directory in ["apps/common", "apps/riscv-tests/benchmarks/common"]:
        for path in (root / directory).iterdir():
            if path.is_file() and path.suffix in (".c", ".h", ".S", ".ld"):
                snapshot(path.relative_to(root))
    snapshot(Path("apps/riscv-tests/env/encoding.h"))
    for subdir in ["scalar", "vector"]:
        relative = Path("apps/riscv-tests/isa/macros") / subdir
        shutil.copytree(root / relative, source / relative)
    legacy = inputs / "legacy"
    legacy.mkdir(exist_ok=True)
    old_elf = root / "apps/riscv-tests/isa/rv64uv-p-vfncvt_int8"
    if not (legacy / old_elf.name).exists():
        shutil.copy2(old_elf, legacy / old_elf.name)

    commands = []

    def execute(command, name, timeout=120, trace=False):
        command = list(map(str, command))
        stdout = logs / f"{name}.stdout"
        stderr = logs / f"{name}.{'trace' if trace else 'stderr'}"
        record = dict(argv=command, cwd=str(out), stdout=str(stdout.relative_to(out)),
                      stderr=str(stderr.relative_to(out)))
        commands.append(record)
        before = time.monotonic()
        try:
            with stdout.open("w") as so, stderr.open("w") as se:
                process = subprocess.run(command, cwd=out, stdout=so, stderr=se,
                                         timeout=timeout, check=False)
            record.update(returncode=process.returncode,
                          seconds=round(time.monotonic() - before, 3))
            if process.returncode:
                raise RuntimeError(f"{name} failed: {stderr.read_text()[-5000:]}")
        finally:
            (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        return stdout, stderr

    common = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-mno-relax",
              "-mcmodel=medany", "-O3", "-ffast-math", "-fno-common",
              "-fno-builtin-printf", "-fno-vectorize", "-mllvm",
              "-scalable-vectorization=off", "-mllvm", "-riscv-v-vector-bits-min=0",
              "-mno-implicit-float", "-ffunction-sections", "-fdata-sections",
              "-std=gnu99", "-DVLEN=1024", "-DNR_LANES=4",
              "-Wall", "-Wextra", "-Wno-unused-command-line-argument"]
    # Legacy Spike test.ld only collects .text/.bss/.tbss without .* suffixes.
    spike_flags = [flag for flag in common
                   if flag not in ("-ffunction-sections", "-fdata-sections")]
    macros = source / "apps/riscv-tests/isa/macros"
    includes = [f"-I{macros / 'scalar'}", f"-I{macros / 'vector'}"]
    ara = source / "apps/common"
    bench = source / "apps/riscv-tests/benchmarks/common"
    env = source / "apps/riscv-tests/env"
    runtime = []
    for name in ["crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c"]:
        obj = build / f"{name}.o"
        execute([compiler, *common, f"-I{ara}", "-c", ara / name, "-o", obj],
                f"runtime-{name}")
        runtime.append(obj)
    cases = catalog()
    variants = [("default", {}, cases[:384], False),
                ("full", {"VFNCVT_INT8_EXTRA_BOUNDARIES": 1}, cases, False)]
    for shard in range(8):
        variants.append((f"shard_{shard}", dict(VFNCVT_INT8_EXTRA_BOUNDARIES=1,
                         VFNCVT_INT8_SHARD_COUNT=8, VFNCVT_INT8_SHARD_ID=shard),
                         [case for case in cases if case["ordinal"] % 8 == shard], True))
    smoke_cases = [case for case in cases if
                   (case["category"] == "batch" and case["kind"] == 0) or
                   (case["category"] == "geometry" and case["lmul"] == 7 and case["policy"] == 0) or
                   (case["category"] == "extra" and case["rm"] == 1)]
    assert len(smoke_cases) == 40
    variants.append(("smoke", dict(VFNCVT_INT8_EXTRA_BOUNDARIES=1, VFNCVT_INT8_SMOKE=1),
                     smoke_cases, True))
    records = {}
    instruction = re.compile(r"^core +0: 0x[0-9a-f]+ \(0x[0-9a-f]+\)")
    opcodes = ["vfncvt.x.f.w", "vfncvt.xu.f.w", "vfncvt.rtz.x.f.w", "vfncvt.rtz.xu.f.w"]

    for name, defines, entries, build_ara in variants:
        flags = [f"-D{key}={value}" for key, value in defines.items()]
        record = dict(name=name, source_flags=defines, ordinals=[c["ordinal"] for c in entries],
                      **totals(entries))
        if build_ara:
            elf = inputs / f"{name}.elf"
            execute([compiler, "-fuse-ld=lld", *common, *includes, f"-I{ara}", *flags,
                     "-static", "-nostartfiles", "-Wl,--gc-sections", "-T", ara / "link_sim_2m.ld",
                     "-o", elf, test, *runtime, "-lm",
                     f"-L{root / 'install/riscv-llvm/lib/generic'}", "-lclang_rt.builtins-riscv64"],
                    f"compile-{name}-ara")
            record.update(elf=str(elf.relative_to(out)), sha256=sha256(elf))
        golden = inputs / f"{name}.spike.elf"
        execute([compiler, "-fuse-ld=lld", *spike_flags, *includes, f"-I{env}", f"-I{bench}",
                 *flags, "-DPREALLOCATE=1", "-D__FLOAT_SUPPORT__", "-D__SPIKE__=1",
                 "-static", "-nostdlib", "-nostartfiles", "-T", bench / "test.ld",
                 "-o", golden, test, bench / "crt.S", bench / "syscalls.c"], f"compile-{name}-spike")
        stdout, trace = execute([spike, "-l", "--isa=rv64gcv_zfh_zvfh_zvl1024b", golden],
                                f"spike-{name}", trace=True)
        output = stdout.read_text()
        if "PASSED:" not in output or "FAIL" in output:
            raise RuntimeError(f"{name}: missing numerical PASS: {output}")
        summary = re.search(r"vfncvt_int8: (\d+) cases, VLEN=(\d+)", output)
        checks = re.search(r"vfncvt_int8_checks: ordinals=(\d+) bytes=(\d+) active=(\d+) csr=(\d+)", output)
        bitmap = re.search(r"vfncvt_int8_ids:([ 0-9a-f]+)\n", output)
        assert summary and checks and bitmap, output
        observed = [i * 64 + bit for i, word in enumerate(bitmap[1].split())
                    for bit in range(64) if int(word, 16) & (1 << bit)]
        assert observed == record["ordinals"], (name, observed, record["ordinals"])
        assert tuple(map(int, summary.groups())) == (len(entries), 1024)
        assert tuple(map(int, checks.groups())) == (
            384 if name == "default" else 464, record["byte_checks"],
            record["active_checks"], record["csr_checks"])
        insns, conversion_counts = 0, [0] * 4
        with trace.open() as stream:
            for line in stream:
                if instruction.match(line):
                    insns += 1
                    for op, opcode in enumerate(opcodes):
                        if opcode in line:
                            conversion_counts[op] += 1
                elif not re.match(r"^core +0: >>>>", line):
                    raise RuntimeError(f"unexpected golden trace record: {line}")
        assert conversion_counts == [sum(c["op"] == op for c in entries) for op in range(4)]
        with trace.open("rb") as src, gzip.open(str(trace) + ".gz", "wb") as dst:
            shutil.copyfileobj(src, dst)
        trace.unlink()
        record.update(spike_elf=str(golden.relative_to(out)), spike_sha256=sha256(golden),
                      spike_status="PASS", spike_instruction_count=insns,
                      opcode_counts=conversion_counts, observed_ordinals=observed,
                      console=str(stdout.relative_to(out)), trace=str(trace.relative_to(out)) + ".gz")
        records[name] = record
        print(f"{name}: PASS {len(entries)} cases, {insns} instructions", flush=True)

    shards = [records[f"shard_{i}"] for i in range(8)]
    union = [ordinal for shard in shards for ordinal in shard["observed_ordinals"]]
    assert sorted(union) == list(range(464)) and len(set(union)) == 464
    sums = {key: sum(shard[key] for shard in shards)
            for key in ("case_count", "byte_checks", "active_checks", "csr_checks")}
    assert sums == totals(cases)
    manifest = dict(status="PASS", vlen=1024, nr_lanes=4, shard_count=8,
                    shard_rule="zero-based testcase ordinal modulo 8; guard before prepare/reference",
                    source=str(test.relative_to(out)), source_sha256=sha256(test),
                    compiler=dict(path=str(compiler), sha256=sha256(compiler),
                                  ara_flags=common, spike_flags=spike_flags),
                    spike=dict(path=str(spike), sha256=sha256(spike)),
                    default=records["default"], full=records["full"], shards=shards,
                    smoke=records["smoke"], partition=dict(status="PASS", **sums),
                    catalog=cases, vcs_run=False,
                    input_sha256={str(p.relative_to(out)): sha256(p)
                                  for p in sorted(inputs.rglob("*")) if p.is_file()})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "SHA256SUMS").write_text("".join(f"{digest}  {path}\n" for path, digest in
                                            manifest["input_sha256"].items()))
    for path in inputs.rglob("*"):
        if path.is_file():
            path.chmod(path.stat().st_mode & ~0o222)
    print(f"Frozen inputs; disjoint union PASS: {sums}", flush=True)


if __name__ == "__main__":
    main()
