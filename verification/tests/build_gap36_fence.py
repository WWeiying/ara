#!/usr/bin/env python3
"""Build only; audit real FENCE.T ELF. Never invoke a simulator or patch a NOP ELF."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/fence_t_gap36_smoke"
AUDIT = ROOT / "verification/tests/gap36_fence_source_audit.json"
BITS = ROOT / "verification/out/gap35-analysis-20261004-01/baseline-bits.json"
BASE = ROOT / "verification/out/gap34-current-20261001-01"
NAME = "fence_t_gap36_smoke"


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_insn(reg, base, offset, fp=False):
    return (offset << 20) | (base << 15) | (3 << 12) | (reg << 7) | (7 if fp else 3)


def store_insn(reg, base, offset, fp=False):
    return ((offset >> 5) << 25) | (reg << 20) | (base << 15) | (3 << 12) | \
           ((offset & 31) << 7) | (0x27 if fp else 0x23)


def validate_log(log):
    require("FAIL:" not in log and "unexpected_trap" not in log, "failure/trap in UART")
    rows = re.findall(r"^fence_t_gap36_smoke rounds=(\d+) checks=(\d+) failures=(\d+)$",
                      log, re.MULTILINE)
    require(rows == [("2", "458", "0")], "wrong or duplicated selfcheck summary")
    require(log.splitlines().count("PASSED: " + NAME) == 1, "missing/duplicate PASS marker")
    return {"rounds": 2, "checks": 458, "failures": 0,
            "scope": "UART selfcheck only; hardware EOC, commit order and FSM evidence still required"}


def audit_elf(metadata, blob):
    require(metadata["FileSummary"]["Format"] == "elf64-littleriscv", "not RV64 LE ELF")
    sections = [entry["Section"] for entry in metadata["Sections"]]
    symbols = {entry["Symbol"]["Name"]["Name"]: entry["Symbol"]
               for entry in metadata["Symbols"]}

    def symbol(name):
        return symbols[name]["Value"]

    def offset(pc):
        for sec in sections:
            if sec["Flags"]["Value"] & 4 and sec["Address"] <= pc < sec["Address"] + sec["Size"]:
                return pc - sec["Address"] + sec["Offset"]
        raise ValueError("PC not in executable section")

    def words(pc, count):
        pos = offset(pc)
        return [int.from_bytes(blob[p:p+4], "little") for p in range(pos, pos + 4 * count, 4)]

    fence_sites = []
    instruction_count = 0
    for sec in sections:
        if not sec["Flags"]["Value"] & 4:
            continue
        data = blob[sec["Offset"]:sec["Offset"] + sec["Size"]]
        pos = 0
        while pos < len(data):
            half = int.from_bytes(data[pos:pos+2], "little")
            length = 4 if half & 3 == 3 else 2
            require(pos + length <= len(data), "truncated instruction")
            instruction_count += 1
            if length == 4:
                require(half & 31 != 31, "unsupported long instruction")
                word = int.from_bytes(data[pos:pos+4], "little")
                op, funct3 = word & 127, (word >> 12) & 7
                require(op not in (0x57, 0x5b, 0x2b, 0x7b), "accelerator/custom instruction")
                require(op not in (7, 0x27) or funct3 in (2, 3), "vector memory instruction")
                if op == 0x0b:
                    require(word == 0x0b, "noncanonical custom0")
                    fence_sites.append(sec["Address"] + pos)
            pos += length
    require(fence_sites == [symbol("gap36_fence0"), symbol("gap36_fence1")], "need exactly two real FENCE.T sites")
    rows = []
    saved = [1, *range(3, 32)]
    for n in range(2):
        begin = symbol(f"gap36_probe{n}")
        fence = symbol(f"gap36_fence{n}")
        resume = symbol(f"gap36_resume{n}")
        pc = symbol(f"gap36_pc{n}")
        require(resume == fence + 4 and pc == fence + 8, "wrong exact resume/PC layout")
        require(words(fence, 1) == [0x0b], "FENCE.T replaced")
        prefix = [0xe0010113] + [store_insn(r, 2, 8*r) for r in saved]
        prefix += [store_insn(r, 2, 256+8*r, True) for r in range(32)]
        require(words(begin, len(prefix)) == prefix, "ABI save differs")
        seed = [load_insn(r, 11, 8*r, True) for r in range(32)] + [0x00050f93]
        seed += [load_insn(r, 31, 8*r) for r in range(1, 32)] + [0x0330000f]
        require(words(fence - 4*len(seed), len(seed)) == seed, "GPR/FPR seed or pre-fence barrier differs")
        capture = [store_insn(30, 31, 240), 0x00000f17, store_insn(30, 31, 512)]
        capture += [store_insn(r, 31, 8*r) for r in [*range(30), 31]]
        capture += [store_insn(r, 31, 256+8*r, True) for r in range(32)]
        capture += [0x0330000f]
        require(words(resume, len(capture)) == capture, "GPR/FPR/PC capture differs")
        suffix = [load_insn(r, 2, 256+8*r, True) for r in range(32)]
        suffix += [load_insn(r, 2, 8*r) for r in saved] + [0x20010113, 0x00008067]
        end = begin + symbols[f"gap36_probe{n}"]["Size"]
        require(words(end - 4*len(suffix), len(suffix)) == suffix, "ABI restore differs")
        rows.append({"round": n, "fence_pc": hex(fence), "word": "0x0000000b",
                     "resume_pc": hex(resume), "auipc_pc": hex(pc),
                     "fence_file_offset": offset(fence), "resume_file_offset": offset(resume)})
    warm = words(symbol("gap36_warm"), symbols["gap36_warm"]["Size"] // 4)
    require(sum(w & 127 == 0x63 for w in warm) == 2, "warm branch loop absent")
    for entry in metadata["ProgramHeaders"]:
        seg = entry["ProgramHeader"]
        if seg["Type"]["Name"] == "PT_LOAD":
            require(0x80000000 <= seg["PhysicalAddress"] and
                    seg["PhysicalAddress"] + seg["MemSize"] <= 0x80100000, "ELF outside link RAM")
    return {"sites": rows, "static_instruction_count": instruction_count,
            "all_gpr_fpr_seed_capture_abi_sequences": "PASS",
            "accelerator_instructions": 0, "canonical_custom0_sites": 2,
            "scalar_warm_branches": 2, "load_segments_fit_link_ram": True}


def negative_audits(metadata, blob, proof):
    results = []
    for label, relative, value in (("NOP-instead-of-FENCE", 0, 0x13),
                                   ("skipped-first-capture", 4, 0x13),
                                   ("wrong-AUIPC-register", 8, 0x00000e97),
                                   ("missing-GPR-seed", -8, 0x13),
                                   ("missing-FPR-capture", 4 + 34*4, 0x13),
                                   ("QBS-custom2", 0, 0x5b)):
        mutated = bytearray(blob)
        pos = proof["sites"][0]["fence_file_offset"] + relative
        mutated[pos:pos+4] = value.to_bytes(4, "little")
        try:
            audit_elf(metadata, mutated)
        except ValueError:
            results.append({"mutation": label, "result": "REJECTED"})
        else:
            raise ValueError("audit accepted " + label)
    altered = copy.deepcopy(metadata)
    for entry in altered["Symbols"]:
        if entry["Symbol"]["Name"]["Name"] == "gap36_resume0":
            entry["Symbol"]["Value"] += 4
    try:
        audit_elf(altered, blob)
    except ValueError:
        results.append({"mutation": "wrong-resume-symbol", "result": "REJECTED"})
    else:
        raise ValueError("audit accepted shifted resume")
    good = f"{NAME} rounds=2 checks=458 failures=0\nPASSED: {NAME}\n"
    validate_log(good)
    for label, bad in (("one-round", good.replace("rounds=2", "rounds=1")),
                       ("missing-check", good.replace("458", "457")),
                       ("duplicate-boot", good + good),
                       ("trap", good + "FAIL: unexpected_trap\n")):
        try:
            validate_log(bad)
        except ValueError:
            results.append({"mutation": label, "result": "REJECTED"})
        else:
            raise ValueError("log audit accepted " + label)
    return {"scope": "In-memory audit mutation tests only, never executed on a RISC-V model or DUT; no mutant ELF written.",
            "rejected": len(results), "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-log", type=Path)
    args = parser.parse_args()
    if args.check_log:
        print(json.dumps(validate_log(args.check_log.read_text()), indent=2))
        return
    if not args.output:
        parser.error("--output required for build")
    out = args.output.resolve()
    if out.parent != ROOT / "verification/out" or not out.name.startswith("gap36-fence-") or out.exists():
        parser.error("use a NEW verification/out/gap36-fence-* directory")
    audit = json.loads(AUDIT.read_text())
    manifest = ROOT / audit["compile_manifest"]
    pinned = {row["path"]: row["sha256"] for row in json.loads(manifest.read_text())["files"]}
    rtl_matches = {}
    for relative in audit["pinned_rtl"]:
        source = ROOT / relative
        require(pinned.get(str(source)) == digest(source), "compiled RTL differs: " + relative)
        rtl_matches[str(source)] = pinned[str(source)]
    bits = json.loads(BITS.read_text())
    for target in audit["targets"]:
        require(any(target in metric for metric in bits["metrics"].values()), "unknown target " + target)
    llvm = ROOT / "install/riscv-llvm"
    cc = llvm / "bin/clang"
    common = ROOT / "apps/common"
    runtime = [common / n for n in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c")]
    sources = [APP / "main.c", APP / "probe.S", Path(__file__).resolve(), AUDIT, common / "link.ld", *runtime]
    source_hashes = {str(p): digest(p) for p in sources}
    out.mkdir(parents=True)
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
        require(result.returncode == 0, "command failed: " + str(log))
        return result.stdout

    objects = []
    for source in [*runtime, APP / "probe.S", APP / "main.c"]:
        obj = out / (source.name + ".o")
        warning = ["-Wall", "-Wextra", "-Werror"] if source.parent == APP else []
        command([cc, *flags, *includes, *warning, "-c", source, "-o", obj],
                out / (source.name + ".build.log"))
        objects.append(obj)
    elf = out / (NAME + ".elf")
    command([cc, *flags, "-fuse-ld=lld", "-static", "-nostartfiles", f"-T{common / 'link.ld'}",
             *objects, "-lm", f"-L{llvm.resolve() / 'lib/generic'}", "-lclang_rt.builtins-riscv64", "-o", elf],
            out / "link.log")
    command([llvm / "bin/llvm-objdump", "-d", elf], out / (NAME + ".dis"))
    command([llvm / "bin/llvm-readelf", "-lWs", elf], out / (NAME + ".readelf"))
    metadata = json.loads(command([llvm / "bin/llvm-readobj", "--elf-output-style=JSON",
        "--sections", "--symbols", "--program-headers", elf], out / "elf_metadata.json"))[0]
    blob = elf.read_bytes()
    proof = audit_elf(metadata, blob)
    mutations = negative_audits(metadata, blob, proof)
    require(all(digest(Path(p)) == sha for p, sha in source_hashes.items()), "source drift during build")
    save(out / "source_hashes.json", source_hashes)
    save(out / "rtl_source_match.json", {"compile_manifest": str(manifest), "sha256": digest(manifest),
         "matches": rtl_matches, "scope": "Read-only navigation/source-identity check, not a functional oracle"})
    save(out / "negative_audits.json", mutations)
    evidence = {"status": "STATIC_ELF_AUDIT_PASS", "test": "app:" + NAME,
        "precheck_type": "compile + static ELF audit + negative validator tests",
        "spike_run": False, "dut_run": False, "hardware_golden_pass": False,
        "fence_emulation_or_nop_substitution": False, "elf": str(elf), "elf_sha256": digest(elf),
        "required_runtime_checks": 458, "required_rounds": 2, "timeout_s": 300, "elf_audit": proof,
        "negative_audit_count": mutations["rejected"], "post_dut_admission": audit["post_dut_admission"]}
    save(out / "precheck.json", evidence)
    shapes = {metric: {t: values[t] for t in audit["targets"] if t in values}
              for metric, values in bits["metrics"].items()}
    save(out / "baseline_shapes.json", {"cache": str(BITS), "tests": len(bits["tests"]),
        "metrics": shapes, "note": "620-case reference raw shapes only; no new coverage measured or DVE percentage."})
    selection = {"status": "DRAFT_NOT_RUN_SEPARATE_FUTURE_ADMISSION", "baseline": str(BASE),
        "baseline_bits": str(BITS),
        "note": "Update baseline and bitmap membership at actual admission; do not append to the current 10-case batch. Static/ELF precheck only; enforce post_dut_admission from source audit.",
        "cases": [{"name": "app:" + NAME, "binary": str(elf), "sources": list(source_hashes),
            "evidence": [str(out / n) for n in ("precheck.json", "negative_audits.json", "source_hashes.json",
                "build_commands.json", "rtl_source_match.json", "baseline_shapes.json", NAME + ".dis")],
            "source_audit": audit["source_audit"], "targets": audit["targets"],
            "rationale": audit["rationale"], "timeout_s": 300}]}
    save(out / "selection-draft.json", selection)
    print("STATIC_ELF_AUDIT_PASS", elf)
    print("Negative audit cases:", mutations["rejected"])
    print("No Spike/VCS execution; no hardware PASS claim.")
    print("Selection draft:", out / "selection-draft.json")


if __name__ == "__main__":
    main()
