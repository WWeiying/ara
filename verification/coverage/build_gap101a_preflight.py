"""Independent NF*EMUL-only host/Spike preflight; original two-phase FAIL preserved."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import subprocess

import build_gap101_preflight as original
import run_gap101_simulation as frozen

s = original.shared
ROOT, OUT = original.ROOT, original.OUT
NAME = "vgap101a_nf_emul_only"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
FAILURE = OUT / "gap101-register-overflow-failure-sealed-20261006-01.json"
FAILURE_SEAL = "05874511cd477205d71871e62bb9f809f803fc86c6a103b1a26fcdc8380ee6ea"
CHECKS = 539
SYMBOLS = tuple(x.replace("g101_", "g101a_") for x in original.SYMBOLS if x != "g101_bad_b")
require = original.require


def expected_words():
    return {(name.replace("g101_", "g101a_"), offset): (1 if name == "g101_traps" else value)
            for (name, offset), value in original.expected_words().items()
            if offset < (4096 if name == "g101_dump" else 64)}


def validate(commits, symbols, trace):
    events = re.findall(r"exception ([^,\n]+), epc (0x[0-9a-fA-F]+)", trace)
    require([(n, int(pc, 16)) for n, pc in events] == [("trap_illegal_instruction", symbols["g101a_bad_a"])]
            and trace.count("exception ") == 1, "Not exactly one NF*EMUL trap")
    require(not any(c.pc in (symbols["g101a_bad_a"], symbols["trap_fail"]) for c in commits), "Bad retirement")
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    terminal = [v for c in commits for a, v in c.memory_accesses if a == symbols["tohost"] and v is not None]
    require(terminal == [1] and writes.get(symbols["g75_result"]) == CHECKS and
            writes.get(symbols["g75_result"] + 4) == writes.get(symbols["num_failed"]) == 0, "Software result differs")
    for (name, offset), value in expected_words().items():
        require(writes.get(symbols[name] + offset) == value, "Observed bytes differ: %s+%d" % (name, offset))
    ledger = [writes.get(symbols["g101a_ledger"] + i * 8) for i in range(8)]
    require(ledger == [2, symbols["g101a_bad_a"], 0xe2050827, 1, 1, 0, 0, 1], "Trap CSR ledger differs")
    restored = [writes.get(symbols["g101a_restore"] + i * 8) for i in range(4)]
    require(all(v is not None for v in restored) and restored[0] == restored[1] and restored[2] == restored[3],
            "Restoration differs")
    count = Counter()
    for c in commits:
        for reg, value in c.vector_writes.items():
            require(reg in range(32) and value == int.from_bytes(bytes([0x40+reg])*128, "little"), "VRF write differs")
            count[reg] += 1
    require(count == Counter({r: 1 for r in range(32)}), "VRF initialization population differs")
    return dict(status="GAP101A_NF_EMUL_SPIKE_PREFLIGHT_PASS_NOT_DUT", checks=CHECKS, phases=1,
                illegal_traps=1, unchanged_vrf_bytes=4096, unchanged_target_guard_bytes=64,
                recovery_guard_bytes=64, coverage_admitted=False, original_phase1_failure_preserved=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    out = p.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    require(s.sha(FAILURE) == FAILURE_SEAL, "Original failure seal differs")
    old = frozen.life.read_bound(frozen.PRE / "preflight-manifest.json", frozen.PRE_SEAL)
    s.check(old["pins"])
    evidence = original.target_evidence()
    evidence["targets"] = [r for r in evidence["targets"] if (r["metric"], r["point"]["raw_index"])
                            in {("branch", 345), ("line", 1334)}]
    require(len(evidence["targets"]) == 2, "NF-only target count differs")
    include = ROOT / "verification/tests"
    paths = [APP, Path(__file__).resolve(), Path(__file__).with_name("test_build_gap101a_preflight.py"),
             Path(original.__file__).resolve(), Path(frozen.__file__).resolve(), FAILURE,
             frozen.PRE / "preflight-manifest.json"]
    pins = s.merge_pins(old["pins"], evidence["pins"])
    pins = s.merge_pins(pins, {str(f): s.sha(f) for f in paths})
    s.check(pins)
    out.mkdir()
    s.save(out / "input-pins.json", pins)
    s.save(out / "target-before.json", evidence)
    try:
        host_cmd = ["/usr/bin/cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(include / "gap101_host_reference.c"), "-o", str(out / "host-reference")]
        s.save(out / "host-command.json", host_cmd)
        with (out / "host.log").open("x") as log:
            subprocess.run(host_cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
            subprocess.run([str(out / "host-reference")], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=10)
        elf = out / "input.elf"
        command = json.loads((frozen.PRE / "compile-command.json").read_bytes())
        command = [str(APP) if x == str(original.APP) else str(elf) if x == str(frozen.PRE / "input.elf") else x
                   for x in command]
        require(str(APP) in command and str(elf) in command and str(original.APP) not in command, "Compile substitution")
        s.save(out / "compile-command.json", command)
        with (out / "compile.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        symbols = {key: s._elf_symbol(elf, s.LLVM / "llvm-readelf", key) for key in SYMBOLS}
        blob = elf.read_bytes()
        h = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
        owners = []
        for i in range(h[11]):
            sec = struct.unpack_from("<IIQQQQIIQQ", blob, h[5] + i*64)
            pc = symbols["g101a_bad_a"]
            if sec[1] == 1 and sec[2] & 4 and sec[3] <= pc and pc+4 <= sec[3]+sec[5]:
                owners.append(struct.unpack_from("<I", blob, sec[4]+pc-sec[3])[0])
        require(owners == [0xe2050827], "NF-only ELF word differs")
        command = [str(s.SPIKE), "--isa=rv64gcv_zfh_zvfh_zvl1024b", "--priv=msu", "--pmpregions=0",
                   "-l", "--log-commits", str(elf)]
        s.save(out / "spike-command.json", command)
        with (out / "spike.stdout").open("x") as stdout, (out / "spike.trace").open("x") as trace:
            subprocess.run(command, stdout=stdout, stderr=trace, check=True, timeout=120)
        result = validate(s.parse_spike_commits(out / "spike.trace"), symbols, (out / "spike.trace").read_text())
        s.save(out / "spike-validation.json", result)
        s.check(pins)
        pins = s.merge_pins(pins, {str(f): s.sha(f) for f in out.iterdir() if f.is_file()})
        s.save(out / "preflight-manifest.json", dict(status="GAP101A_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS",
            case=NAME, baseline_tests=715, checks=CHECKS, symbols=symbols, pins=pins,
            validation=result, target_unhit_count=2, input_elf=str(elf), input_spike_trace=str(out / "spike.trace"),
            target_before=str(out / "target-before.json"), original_failure=str(FAILURE),
            original_failure_seal=FAILURE_SEAL, coverage_admitted=False, rtl_changed=False,
            vcs_started=False, measured_raw_increment=None))
        print(json.dumps(dict(output=str(out), seal=s.sha(out / "preflight-manifest.json"), checks=CHECKS)))
    except Exception as error:
        s.save(out / "failure.json", dict(status="GAP101A_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__": main()
