"""Seal the original two-phase FAIL, never admit or alter its artifacts."""
import argparse
import csv
import json
from pathlib import Path
import re

import build_gap101_preflight as software
import run_gap101_simulation as runner
from check_gap100_runtime import scalar_memory

ROOT, OUT, require = software.ROOT, software.OUT, software.require
RUN = OUT / "gap101-illegal-segment-store-old-image-20261006-01"


def scalar_store(row):
    address = int(row["mem_addr"], 16)
    mask = int(row["mem_wmask"], 16)
    if not mask:
        return None
    access = scalar_memory(int(row["insn"], 16))
    require(access is not None and access[0] == "write", "Unknown RVFI store")
    size = access[1]
    require(address % size == 0 and mask == ((1 << size) - 1) << (address & 7), "Store mask/address differs")
    # This monitor reports lane-positioned masks but right-justified store data.
    value = int(row["mem_wdata"], 16) & ((1 << (size * 8)) - 1)
    return address, value.to_bytes(size, "little")


def audit():
    pins = {}
    def read(path, expected=None):
        path = Path(path).absolute()
        raw = path.read_bytes()
        actual = software.shared.sha(path)
        require(expected is None or expected == actual, "Input drift: " + str(path))
        pins.update(software.shared.merge_pins(pins, {str(path): actual}))
        return raw
    pre = json.loads(read(runner.PRE / "preflight-manifest.json", runner.PRE_SEAL))
    software.shared.check(pre["pins"])
    pins.update(software.shared.merge_pins(pins, pre["pins"]))
    runtime = json.loads(read(RUN / "manifest.json"))
    require(runtime["input_elf"] == pre["input_elf"] and runtime["preflight"] == pre,
            "Run/preflight identity differs")
    software.shared.check(runtime["pins"])
    pins.update(software.shared.merge_pins(pins, runtime["pins"]))
    status = json.loads(read(RUN / "simulation-status.json"))
    require(status["coverage_admitted"] is False, "Unexpected admission")
    rows = list(csv.DictReader(read(RUN / "commit_trace.csv").decode().splitlines()))
    retired = [r for r in rows if r["event"] == "retire"]
    require([int(r["order"]) for r in retired] == list(range(len(retired))), "Incomplete retirement order")
    memory = {}
    for row in retired:
        store = scalar_store(row)
        if store:
            address, data = store
            memory.update({address + i: byte for i, byte in enumerate(data)})
    symbols = pre["symbols"]
    def value(symbol, offset=0, size=8):
        address = symbols[symbol] + offset
        require(all(address + i in memory for i in range(size)), "Unobserved bytes: " + symbol)
        return int.from_bytes(bytes(memory[address + i] for i in range(size)), "little")
    require(value("g75_result", size=4) == 1075 and value("g75_result", 4, 4) ==
            value("num_failed", size=4) == 7 and value("tohost") == 3 and value("g101_traps") == 1,
            "Not the original seven-check FAIL")
    diffs = []
    counts = {}
    for (symbol, offset), expected in software.expected_words().items():
        actual = value(symbol, offset)
        counts[symbol] = counts.get(symbol, 0) + 1
        if actual != expected:
            diffs.append(dict(symbol=symbol, offset=offset, actual=hex(actual), expected=hex(expected)))
    ledgers = []
    for phase in range(2):
        expected = [2, symbols[("g101_bad_a", "g101_bad_b")[phase]], software.WORDS[phase],
                    1, 1-phase, 0, 0, phase+1]
        actual = [value("g101_ledger", phase * 80 + i * 8) for i in range(8)]
        ledgers.append(dict(phase=phase, actual=actual, expected=expected))
        for i, (got, want) in enumerate(zip(actual, expected)):
            if got != want:
                diffs.append(dict(symbol="g101_ledger", offset=phase*80+i*8,
                                  actual=hex(got), expected=hex(want)))
    restored = [value("g101_restore", i * 8) for i in range(4)]
    require(restored[0] == restored[1] and restored[2] == restored[3], "Trap CSR restore changed")
    require(len(diffs) == 7 and not any(d["symbol"] in ("g101_dump", "g101_recovery_dump") for d in diffs),
            "Unexpected independent failure population")
    require(value("g101_target_dump", 80) == 0xa5a5a5a5a5a5405f, "Wrong exact corrupted target word")
    console = read(RUN / "console.log").decode()
    require("requests=148 responses=148 exceptions=1" in console and "protocol_errors=0" in console and
            "failure value 0000000000000003" in console, "Runtime contract differs")
    trace = read(RUN / "trace_hart_0.log").decode()
    events = re.findall(r"Exception @\s*(\d+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)", trace)
    require(len(events) == 1 and int(events[0][1], 16) == symbols["g101_bad_a"] and
            events[0][2] == "Illegal Instruction", "Exception ledger differs")
    read(RUN / "vector_trace.csv")
    original_source = ROOT / "hardware/src/ara_dispatcher.sv"
    old_source = OUT / "old-image-source-evidence-20261006-01/ara_dispatcher.sv"
    read(old_source, "9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43")
    read(ROOT / "hardware/src/segment_sequencer.sv", "672ddcdfafc3fb40206e9b28c9c4e5d67d40dc9fae18e577cff9c5dc586d4452")
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_seal_gap101_failure.py")):
        read(path)
    software.shared.check(pins)
    return dict(status="GAP101_OLD_IMAGE_REGISTER_OVERFLOW_FAIL_SEALED_NOT_ADMITTED", checks=1075,
                failed_checks=7, root_causes=1, phase0_pass=True, phase1_pass=False,
                ledgers=ledgers, differences=diffs, checked_words=counts,
                vrf_snapshot_bytes_equal=8192, legal_recovery_guard_bytes_equal=128,
                mtvec_mscratch_restored=True, target_actual="0xa5a5a5a5a5a5405f",
                target_expected="0xa5a5a5a5a5a5a5a5", phase1_events=[r for r in rows if r["insn"] == "22050fa7"],
                source=dict(historical_path=str(original_source), read_path=str(old_source),
                    dispatcher_default="1202-1227: vd defaults to zero",
                    store_decode="4389: vs1=insn.vmem_type.rd, use_vs1=1; unit store does not assign vd/vs2",
                    incorrect_guard="4543: unsigned'(ara_req.vd)+segment_register_count>32",
                    sequencing="segment_sequencer.sv:234: vs1+5-bit segment offset wraps v31 to v0"),
                classification="Measured old-image architectural failure, not a software-policy relaxation",
                original_simulator_exit_status=status, pins=pins, coverage_admitted=False, rtl_changed=False,
                retry_performed=False, qualifications=[])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == OUT and output.resolve() == output and not output.exists(), "Fresh output required")
    result = audit()
    software.shared.save(output, result)
    print(json.dumps(dict(output=str(output), seal=software.shared.sha(output), status=result["status"])))


if __name__ == "__main__": main()
