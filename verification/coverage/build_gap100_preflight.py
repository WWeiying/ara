"""Single CSR HPM/vectored software preflight, historical708, no RTL execution."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import subprocess

import build_gap98_preflight as shared
import inventory_csr_707 as inventory

ROOT, OUT, sha, save, require = shared.ROOT, shared.OUT, shared.sha, shared.save, shared.require
NAME = "vgap100_csr_hpm_vectored"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
BASE = OUT / "gap99-offline-admitted-708-20261006-01"
TARGETS = {"cond": {232, 443, 445, 447, 449, 451, 452, 453, 506, 515, 521, 524},
           "line": {890}, "branch": {587}}
SYMBOLS = ("tohost", "g75_result", "num_failed", "g75_trap", "trap_fail", "g100_observed",
           "g100_snapshots", "g100_state", "g100_m_table", "g100_s_table", "g100_hpm",
           "g100_break", "g100_uecall", "g100_irq_begin", "g100_irq_end", "g100_after_irq")
SPIKE_ISA = "rv64gcv_zfh_zvfh_zvl1024b_zicntr_zihpm"


def trap_distribution(text):
    events = re.findall(r"exception ([^,\n]+), epc (0x[0-9a-fA-F]+)", text)
    counts = Counter(name for name, _ in events)
    expected = dict(trap_illegal_instruction=6, trap_breakpoint=1, **{"interrupt #1": 1},
                    trap_user_ecall=5, trap_supervisor_ecall=5, trap_machine_ecall=5)
    require(dict(counts) == expected and text.count("exception ") == len(events),
            "Unexpected/unparsed Spike trap: " + str(dict(counts)))
    return dict(counts)


def phase(row):
    require(0 <= row < 15, "Invalid phase")
    priv = (3, 1, 0)[row // 4] if row < 12 else (3, 1, 0)[row - 12]
    m, s = (row % 4) // 2, row % 2
    allowed = priv == 3 or (priv == 1 and m == 1) or (priv == 0 and m == s == 1)
    cause = (0 if allowed else 2) if row < 12 else (3, (1 << 63) | 1, 8)[row - 12]
    return priv, m, s, cause


def oracle(row):
    priv, m, s, cause = phase(row)
    return [m * 8, s * 8, int(cause != 0), 1, cause, 1, 1, int(row == 13),
            0 if cause == 0 else 1 if row >= 13 else 3,
            0x5a5 if row < 12 and cause else 0, 0, 0,
            0 if cause == 0 or row == 14 else priv, 0, 2 if row == 13 else 0]


def validate_window(commits, symbols):
    begin, end = symbols["g100_irq_begin"], symbols["g100_irq_end"]
    require(end - begin == 256 * 4 and begin % 4 == 0, "Wrong NOP window layout")
    window = [c for c in commits if begin <= c.pc < end]
    require(len(window) <= 256 and [c.pc for c in window] == list(range(begin, begin + 4 * len(window), 4)),
            "Window is not one contiguous prefix")
    require(all(c.instruction == 0x13 and not (c.gpr_writes or c.fpr_writes or c.vector_writes or
                c.csr_writes or c.memory_accesses) for c in window), "Non-inert interrupt window instruction")
    require(not any(c.pc == end for c in commits), "SSIP window timed out")
    return len(window)


def validate_elf_window(blob, symbols):
    require(len(blob) >= 64 and blob[:6] == b"\x7fELF\x02\x01", "Not ELF64 LE")
    header = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    require(header[:3] == (2, 243, 1) and header[10] == 64 and header[11] > 0 and
            header[5] + 64 * header[11] <= len(blob), "Bad ELF section headers")
    begin, end = symbols["g100_irq_begin"], symbols["g100_irq_end"]
    require(begin % 4 == 0 and end - begin == 1024, "Bad ELF NOP window")
    owners = []
    for index in range(header[11]):
        section = struct.unpack_from("<IIQQQQIIQQ", blob, header[5] + index * 64)
        if section[1] == 1 and section[2] & 4 and section[3] <= begin and end <= section[3] + section[5]:
            require(section[4] + section[5] <= len(blob), "Truncated executable section")
            offset = section[4] + begin - section[3]
            owners.append(blob[offset:offset + 1024])
    require(owners == [b"\x13\0\0\0" * 256], "Ambiguous/non-inert ELF window")


def validate(commits, symbols):
    require(not any(c.vector_writes or c.pc == symbols["trap_fail"] for c in commits), "Unexpected vector/fatal trap")
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    terminal = [v for c in commits for a, v in c.memory_accesses if a == symbols["tohost"] and v is not None]
    require(terminal == [1] and writes.get(symbols["g75_result"]) == 225 and
            writes.get(symbols["g75_result"] + 4) == writes.get(symbols["num_failed"]) == 0 and
            all(writes.get(symbols["g75_trap"] + off) == 0 for off in (0, 8, 16)), "Wrong exact software result")
    for row in range(15):
        got = [writes.get(symbols["g100_observed"] + (row * 15 + col) * 8) for col in range(15)]
        require(got == oracle(row), "Independent phase oracle mismatch: " + str(row))
        raw = [writes.get(symbols["g100_snapshots"] + (row * 15 + col) * 8) for col in range(15)]
        priv, m, s, cause = phase(row)
        require(all(v is not None for v in raw), "Incomplete raw snapshot")
        require(raw[0] == raw[4] == cause and raw[1] == (2 if row == 14 else priv + 8) and
                raw[2] == int(cause != 0) and raw[3] == 1 and raw[12] == 0, "Wrong raw trap population")
        entry = symbols["g100_hpm"] if row < 12 else symbols["g100_break"] if row == 12 else symbols["g100_uecall"]
        epc = raw[5]
        if row == 13:
            require(symbols["g100_irq_begin"] <= epc < symbols["g100_irq_end"] and epc % 4 == 0,
                    "SSIP EPC outside exact inert window")
        else:
            require(epc == (entry if cause else 0), "Wrong synchronous EPC")
        require(raw[6] in ((0, entry) if row == 12 else (0xc0302f73,) if cause == 2 else (0,)), "Wrong raw TVAL")
        require(raw[9] == int(row == 13) and raw[14] == (0 if not cause else 1 if row >= 13 else 3),
                "Wrong native vector slot/target privilege")
        require(raw[10] == (0x5a5 if row < 12 and cause else 0), "Wrong HPM value/denied destination")
        require((raw[7] & (2 if row >= 13 else 8)) == 0 and
                (raw[8] & 2) == (2 if row == 13 else 0), "Wrong trap enable/pending state")
        require(((raw[7] >> (8 if row >= 13 else 11)) & (1 if row >= 13 else 3)) ==
                (0 if not cause or row == 14 else priv), "Wrong trap previous privilege")
    nops = validate_window(commits, symbols)
    epc = writes[symbols["g100_snapshots"] + (13 * 15 + 5) * 8]
    require(epc == symbols["g100_irq_begin"] + 4 * nops, "SSIP EPC does not follow retired NOP prefix")
    hpm = [c for c in commits if c.pc == symbols["g100_hpm"]]
    require(len(hpm) == 7 and all(c.instruction == 0xc0302f73 and c.gpr_writes == {30: 0} for c in hpm),
            "Wrong legal HPM read population/value")
    return dict(status="SPIKE_CSR_HPM_VECTORED_PREFLIGHT_PASS_NOT_DUT", phases=15, checks=225,
                exact_observed_bytes=1800, raw_snapshot_bytes=1800, legal_hpm_reads=7, denied_hpm_reads=5,
                expected_traps=23, irq_nop_prefix=nops, scalar_comparison_qualified=False,
                vector_destination_instructions=0, measured_raw_increment=None, coverage_admitted=False)


def target_evidence():
    pins = {}
    def pin(path, expected=None):
        nonlocal pins
        path = Path(path).absolute()
        actual = sha(path)
        require(expected is None or expected == actual, "Pinned input drift: " + str(path))
        pins = shared.merge_pins(pins, {str(path): actual})
        return path
    state = json.loads(pin(BASE / "status.json").read_bytes())
    bits = json.loads(pin(BASE / "combined-bits.json",
        "15e2bb8b04190b883429039301a0109d9d1bb202e5d1ef47cd0668d948d4949d").read_bytes())
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and
            state["aggregate_passed"] == len(bits["tests"]) == len(set(bits["tests"])) == 708, "Not admitted708")
    require(pin(BASE / "combined-inputs.txt").read_text().splitlines() ==
            [str(inventory.BUILD / "sim/simv.vdb"), *bits["tests"]], "Exact708 membership/order differs")
    sources = json.loads(pin(inventory.BUILD / "build-source-pins.json").read_bytes())
    for relative in ("hardware/deps/cva6/core/csr_regfile.sv", "hardware/deps/cva6/core/perf_counters.sv",
                     "hardware/src/ara_soc.sv", "hardware/src/ara_system.sv",
                     "hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv"):
        path = ROOT / relative
        pin(path, sources[str(path)])
    config = (ROOT / "hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv").read_text()
    require("RVZicntr: bit'(1)" in config and "RVZihpm: bit'(1)" in config, "Counter ISA differs")
    design = inventory.Design(inventory.BUILD / "sim/simv.vdb")
    require(design.source(inventory.SCOPE)["resolved_path"] == str(inventory.SOURCE), "Wrong CSR source owner")
    for relative, expected in bits["design"].items():
        pin(design.db / relative, expected)
    rows = []
    for metric, wanted in TARGETS.items():
        record = bits["metrics"][metric][inventory.SCOPE]
        pin(design.db / ("shape/" + metric + ".verilog.shape.xml"))
        if metric == "cond":
            nodes = [n for n in inventory.read_xml(design.db / "shape/cond.verilog.shape.xml")
                     if n.get("id") == design.hierarchy[inventory.SCOPE].get("id") and
                     n.get("chksum") == record["checksum"]]
            require(len(nodes) == 1, "Ambiguous CSR condition shape")
            definition = nodes[0]
        else:
            definition = design.definition(inventory.SCOPE, metric)
        require(definition.get("chksum") == record["checksum"], "Definition checksum differs")
        mapped, _ = inventory.mapped_points(metric, definition, record)
        selected = [p for p in mapped if p["raw_index"] in wanted]
        require({p["raw_index"] for p in selected} == wanted, "Missing target coordinates")
        for p in selected:
            require(not (int(record["bits"], 16) & (1 << (record["width"] - 1 - p["raw_index"]))), "Target already hit")
            rows.append(dict(metric=metric, scope=inventory.SCOPE, point=p, checksum=record["checksum"],
                             width=record["width"], hit_before=False))
    shared.check(pins)
    return dict(baseline_tests=708, targets=rows, pins=pins, exclusions_generated=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    evidence = target_evidence()
    paths = [APP, Path(__file__).resolve(), Path(__file__).with_name("test_build_gap100_preflight.py"),
             ROOT / "verification/tests/gap75_start.S", ROOT / "verification/tests/gap75.ld",
             shared.LLVM / "clang", shared.LLVM / "llvm-readelf", shared.SPIKE,
             Path(shared.__file__).resolve(), Path(inventory.__file__).resolve(),
             ROOT / "verification/coverage/GAP100_SCALAR_COMPARISON_SCOPE.md"]
    paths += [p for p in (ROOT / "apps/riscv-tests/isa/macros").rglob("*") if p.is_file()]
    paths += list((ROOT / "verification/ara_verify").glob("*.py"))
    pins = shared.merge_pins(evidence["pins"], {str(p): sha(p) for p in paths})
    shared.check(pins)
    out.mkdir()
    save(out / "target-before.json", evidence)
    elf = out / "input.elf"
    command = [str(shared.LLVM / "clang"), "--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh",
               "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-O2",
               "-fno-vectorize", "-fno-slp-vectorize", "-ffreestanding", "-DG75_NO_PRINT", "-D__SPIKE__",
               "-DVLEN=1024", "-DNR_LANES=4", "-I" + str(ROOT / "apps/riscv-tests/isa/macros/vector"),
               "-I" + str(ROOT / "apps/riscv-tests/env"), "-I" + str(ROOT / "apps/common"),
               "-fuse-ld=lld", "-nostdlib", "-T" + str(ROOT / "verification/tests/gap75.ld"),
               str(ROOT / "verification/tests/gap75_start.S"), str(APP), "-o", str(elf)]
    save(out / "compile-command.json", command)
    try:
        with (out / "compile.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        symbols = {key: shared._elf_symbol(elf, shared.LLVM / "llvm-readelf", key) for key in SYMBOLS}
        require(symbols["g100_m_table"] % 256 == symbols["g100_s_table"] % 256 == 0, "Unaligned vector tables")
        validate_elf_window(elf.read_bytes(), symbols)
        command = [str(shared.SPIKE), "--isa=" + SPIKE_ISA, "--priv=msu", "--pmpregions=0",
                   "-l", "--log-commits", str(elf)]
        save(out / "spike-command.json", command)
        with (out / "spike.stdout").open("x") as stdout, (out / "spike.trace").open("x") as trace:
            subprocess.run(command, stdout=stdout, stderr=trace, check=True, timeout=120)
        validation = validate(shared.parse_spike_commits(out / "spike.trace"), symbols)
        validation["trap_distribution"] = trap_distribution((out / "spike.trace").read_text())
        save(out / "spike-validation.json", validation)
        shared.check(pins)
        pins = shared.merge_pins(pins, {str(p): sha(p) for p in out.iterdir() if p.is_file()})
        shared.check(pins)
        save(out / "preflight-manifest.json", dict(status="GAP100_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME,
             baseline_tests=708, checks=225, symbols=symbols, spike_validation=validation, pins=pins,
             input_elf=str(elf), input_spike_trace=str(out / "spike.trace"),
             target_before=str(out / "target-before.json"), target_unhit_count=14,
             scalar_comparison_qualified=False, measured_raw_increment=None, coverage_admitted=False,
             rtl_changed=False, new_RTL_signoff=False, exclusions_generated=False))
        print(json.dumps(dict(output=str(out), seal=sha(out / "preflight-manifest.json"), checks=225, targets=14)))
    except Exception as error:
        save(out / "failure.json", dict(status="GAP100_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()
