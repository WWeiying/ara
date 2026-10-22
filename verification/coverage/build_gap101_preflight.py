"""Two illegal segment-store phases: host/Spike only, no RTL build or VCS."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

import build_gap98_preflight as shared
from closure_point_inventory import points

ROOT, OUT = shared.ROOT, shared.OUT
NAME = "vgap101_illegal_segment_store"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
BASE = OUT / "gap100-offline-admitted-715-20261006-01"
BUILD = OUT / "repaired-aligned-build-20260930-01"
SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher"
WORDS = (0xe2050827, 0x22050fa7)
CHECKS = 1075
SYMBOLS = ("tohost", "g75_result", "num_failed", "g75_trap", "trap_fail",
           "g101_ledger", "g101_traps", "g101_dump", "g101_target_dump",
           "g101_recovery_dump", "g101_restore", "g101_bad_a", "g101_bad_b")
require = shared.require


def expected_words():
    result = {}
    for phase in range(2):
        result[("g101_traps", 0)] = 2
        for word in range(512):
            result[("g101_dump", (phase * 512 + word) * 8)] = int.from_bytes(
                bytes([0x40 + word // 16]) * 8, "little")
        for word in range(8):
            data = bytearray([0xa5] * 8)
            result[("g101_target_dump", (phase * 8 + word) * 8)] = int.from_bytes(data, "little")
            if word == 2:
                data[:2] = bytes((0x5e, 0x5f) if phase else (0x50, 0x51))
            result[("g101_recovery_dump", (phase * 8 + word) * 8)] = int.from_bytes(data, "little")
    return result


def validate(commits, symbols, trace):
    events = re.findall(r"exception ([^,\n]+), epc (0x[0-9a-fA-F]+)", trace)
    wanted = [("trap_illegal_instruction", symbols[s]) for s in ("g101_bad_a", "g101_bad_b")]
    require([(name, int(pc, 16)) for name, pc in events] == wanted and
            trace.count("exception ") == 2, "Not exactly two illegal traps at the pinned PCs")
    bad = set(pc for _, pc in wanted)
    require(not any(c.pc in bad or c.pc == symbols["trap_fail"] for c in commits),
            "Rejected word retired or unexpected fatal handler")
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    terminal = [v for c in commits for a, v in c.memory_accesses
                if a == symbols["tohost"] and v is not None]
    require(terminal == [1] and writes.get(symbols["g75_result"]) == CHECKS and
            writes.get(symbols["g75_result"] + 4) == writes.get(symbols["num_failed"]) == 0,
            "Software checks/terminal mismatch")
    for (symbol, offset), expected in expected_words().items():
        require(writes.get(symbols[symbol] + offset) == expected,
                "Independent observed-byte mismatch: %s+%d" % (symbol, offset))
    for phase in range(2):
        expected = [2, symbols[("g101_bad_a", "g101_bad_b")[phase]], WORDS[phase],
                    1, 1 - phase, 0, 0, phase + 1]
        actual = [writes.get(symbols["g101_ledger"] + phase * 80 + i * 8) for i in range(8)]
        require(actual == expected, "Trap/CSR ledger mismatch: " + str(phase))
    restored = [writes.get(symbols["g101_restore"] + i * 8) for i in range(4)]
    require(all(v is not None for v in restored) and restored[0] == restored[1] and
            restored[2] == restored[3], "Trap CSR restoration differs")
    count = Counter()
    for commit in commits:
        for reg, value in commit.vector_writes.items():
            require(reg in range(32) and value == int.from_bytes(bytes([0x40 + reg]) * 128, "little"),
                    "Unexpected VRF write/value outside initialization")
            count[reg] += 1
    require(count == Counter({reg: 2 for reg in range(32)}), "Missing/extra initialization writes")
    return dict(status="GAP101_SPIKE_EXACT_TWO_TRAPS_ORACLE_PASS_NOT_DUT",
                phases=2, checks=CHECKS, illegal_traps=2, rejected_store_writes=0,
                observed_vrf_bytes=8192, target_guard_bytes=128, recovery_guard_bytes=128,
                measured_raw_increment=None, coverage_admitted=False)


def verify_elf(blob, symbols):
    require(blob[:6] == b"\x7fELF\x02\x01" and len(blob) >= 64, "Not ELF64 LE")
    h = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    require(h[:3] == (2, 243, 1) and h[10] == 64 and h[5] + h[11] * 64 <= len(blob), "ELF layout")
    for name, expected in zip(("g101_bad_a", "g101_bad_b"), WORDS):
        pc, actual = symbols[name], []
        require(pc % 4 == 0, "Misaligned rejected word")
        for i in range(h[11]):
            section = struct.unpack_from("<IIQQQQIIQQ", blob, h[5] + i * 64)
            if section[1] == 1 and section[2] & 4 and section[3] <= pc and pc + 4 <= section[3] + section[5]:
                off = section[4] + pc - section[3]
                require(off + 4 <= len(blob), "Truncated word")
                actual.append(struct.unpack_from("<I", blob, off)[0])
        require(actual == [expected], "Wrong/aliased ELF rejected word")


def target_evidence():
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        actual = shared.sha(path)
        require(expected is None or actual == expected, "Pin differs: " + str(path))
        pins.update(shared.merge_pins(pins, {str(path): actual}))
        return path
    state = json.loads(pin(BASE / "status.json").read_bytes())
    bits = json.loads(pin(BASE / "combined-bits.json").read_bytes())
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 715 and
            len(bits["tests"]) == len(set(bits["tests"])) == 715, "Not terminal admitted715")
    require(pin(BASE / "combined-inputs.txt").read_text().splitlines() ==
            [str(BUILD / "sim/simv.vdb"), *bits["tests"]], "Membership/order differs")
    sources = json.loads(pin(BUILD / "build-source-pins.json",
        "6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b").read_bytes())
    original = ROOT / "hardware/src/ara_dispatcher.sv"
    snapshot = OUT / "old-image-source-evidence-20261006-01/ara_dispatcher.sv"
    require(sources[str(original)] == "9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43",
            "Old dispatcher identity differs")
    pin(snapshot, sources[str(original)])
    pin(snapshot.with_name("manifest.json"))
    for path in (ROOT / "hardware/src/segment_sequencer.sv", ROOT / "hardware/include/ara_pkg.sv",
                 ROOT / "hardware/src/ara_soc.sv"):
        pin(path, sources[str(path)])
    design = shared.Design(BUILD / "sim/simv.vdb")
    require(design.source(SCOPE)["resolved_path"] == str(original), "Wrong source owner")
    for relative, expected in bits["design"].items():
        pin(design.db / relative, expected)
    rows = []
    for metric, checksum, wanted in [("branch", "1558979345", {343, 345}),
                                     ("line", "1316526434", {1334, 1337})]:
        record = bits["metrics"][metric][SCOPE]
        definition = design.definition(SCOPE, metric)
        require(record["checksum"] == definition.get("chksum") == checksum, "Shape/checksum differs")
        pin(design.db / ("shape/%s.verilog.shape.xml" % metric))
        selected = [p for p in points(metric, definition, record["width"]) if p["raw_index"] in wanted]
        require({p["raw_index"] for p in selected} == wanted, "Missing target")
        for p in selected:
            require(not int(record["bits"], 16) & (1 << (record["width"] - 1 - p["raw_index"])),
                    "Target already hit in715")
            if metric == "branch":
                require(p["native_id"] == "25" and p["vector"] == {343: "786", 345: "784"}[p["raw_index"]]
                        and p["attributes"]["chksum"] == "3771491581", "Native branch identity differs")
            rows.append(dict(metric=metric, scope=SCOPE, checksum=checksum, width=record["width"], point=p))
    shared.check(pins)
    return dict(status="GAP101_RAW715_TARGETS_ZERO_NOT_ADMISSION", baseline_tests=715,
                targets=rows, pins=pins, source_path=str(original), source_read_path=str(snapshot))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    evidence = target_evidence()
    include = ROOT / "verification/tests"
    host = include / "gap101_host_reference.c"
    paths = [APP, host, include / "gap101_reference.h", include / "gap75_start.S", include / "gap75.ld",
             Path(__file__).resolve(), Path(__file__).with_name("test_build_gap101_preflight.py"),
             shared.LLVM / "clang", shared.LLVM / "llvm-readelf", shared.SPIKE, Path("/usr/bin/cc").resolve()]
    paths += [Path(m.__file__).resolve() for m in tuple(sys.modules.values())
              if getattr(m, "__file__", None) and str(ROOT / "verification") in str(m.__file__)]
    pins = shared.merge_pins(evidence["pins"], {str(p): shared.sha(p) for p in paths})
    shared.check(pins)
    out.mkdir()
    shared.save(out / "input-pins.json", pins)
    shared.save(out / "target-before.json", evidence)
    try:
        host_cmd = ["/usr/bin/cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(host), "-o", str(out / "host-reference")]
        shared.save(out / "host-command.json", host_cmd)
        with (out / "host.log").open("x") as log:
            subprocess.run(host_cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
            subprocess.run([str(out / "host-reference")], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=10)
        elf = out / "input.elf"
        command = [str(shared.LLVM / "clang"), "--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh",
                   "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-O2",
                   "-fno-vectorize", "-fno-slp-vectorize", "-ffreestanding", "-DVLEN=1024", "-DNR_LANES=4",
                   "-I" + str(include), "-fuse-ld=lld", "-nostdlib", "-T" + str(include / "gap75.ld"),
                   str(include / "gap75_start.S"), str(APP), "-o", str(elf)]
        shared.save(out / "compile-command.json", command)
        with (out / "compile.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        symbols = {s: shared._elf_symbol(elf, shared.LLVM / "llvm-readelf", s) for s in SYMBOLS}
        verify_elf(elf.read_bytes(), symbols)
        command = [str(shared.SPIKE), "--isa=rv64gcv_zfh_zvfh_zvl1024b", "--priv=msu", "--pmpregions=0",
                   "-l", "--log-commits", str(elf)]
        shared.save(out / "spike-command.json", command)
        with (out / "spike.stdout").open("x") as stdout, (out / "spike.trace").open("x") as trace:
            subprocess.run(command, stdout=stdout, stderr=trace, check=True, timeout=120)
        validation = validate(shared.parse_spike_commits(out / "spike.trace"), symbols,
                              (out / "spike.trace").read_text())
        shared.save(out / "spike-validation.json", validation)
        shared.check(pins)
        pins = shared.merge_pins(pins, {str(p): shared.sha(p) for p in out.iterdir() if p.is_file()})
        shared.check(pins)
        shared.save(out / "preflight-manifest.json", dict(status="GAP101_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS",
            case=NAME, baseline_tests=715, checks=CHECKS, symbols=symbols, pins=pins,
            input_elf=str(elf), input_spike_trace=str(out / "spike.trace"), validation=validation,
            target_before=str(out / "target-before.json"), target_unhit_count=4,
            coverage_admitted=False, measured_raw_increment=None, rtl_changed=False, exclusions_generated=False))
        print(json.dumps(dict(output=str(out), seal=shared.sha(out / "preflight-manifest.json"), checks=CHECKS)))
    except Exception as error:
        shared.save(out / "failure.json", dict(status="GAP101_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()
