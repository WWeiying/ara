"""Strict independent GAP97 admission: scalar/CSR/config, zero vector data."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification"))
import build_gap97_preflight as preflight
import run_gap97_simulation as runner
import coverage_bitmap_delta as bitmap
from ara_verify.spike_trace import compare_commit_prefix
from ara_verify.vector_commit import compare_vector_commits
from ara_verify.contract import check_contract_log, parse_contract_summary

OUT = ROOT / "verification/out"
BASE = OUT / "gap96-offline-admitted-705-20261006-01"
RUN = OUT / "gap97-csr-large-avl-old-image-20261006-01"
DESIGN = OUT / "repaired-aligned-build-20260930-01/sim/simv.vdb"
PREPARED_SEAL = "ad68ebb21763f0204be06c9734792b59a7abfdf9f81963522625e8382f855a41"
BASE_SEALS = {"combined-bits.json": "30139b06d8d16a70c39eb1938f3b191ca9e7b8057da85241a8bd0d8ead90b7e0",
              "status.json": "da0dafbe2e32e4b2d30a5bd5b51de504e0d0baa0874da8a7477c141c76897ea0",
              "combined-inputs.txt": "0cbbe9c7b1e77630185f1f7ca8b26d1193be4712a98fc28ac274814946d9071f",
              "evidence-pins.json": "64893c34c83ee16d1fed329a4a6386cf9eeeeb8e641bcc7ba78e48a9eba9d163"}
COMMIT_FIELDS = ("cycle", "event", "order", "port", "trans_id", "pc", "insn", "rd",
                 "rd_wdata", "mem_addr", "mem_rmask", "mem_wmask", "mem_wdata", "trap")
VECTOR_FIELDS = ("cycle", "event", "arch_seq", "vid", "lane", "source", "insn", "use_vd",
                 "vd", "eew", "vl", "vstart", "addr", "be", "wdata", "nr_lanes", "vlen_bits")
SELF = Path(__file__).resolve()
SELF_SHA = preflight.sha(SELF)
require = preflight.require


class PinBook:
    """Expected hashes are immutable: snapshotting cannot replace prior evidence."""
    def __init__(self):
        self.pins = {}

    def merge(self, additions):
        require(isinstance(additions, dict) and additions, "Missing expected pins")
        for path, expected in additions.items():
            require(isinstance(path, str) and Path(path).is_absolute() and
                    isinstance(expected, str) and len(expected) == 64 and
                    all(c in "0123456789abcdef" for c in expected), "Malformed expected pin")
            require(path not in self.pins or self.pins[path] == expected, "Expected-pin conflict: " + path)
        self.pins.update(additions)

    def read(self, path):
        path = Path(path).absolute()
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        require(str(path) not in self.pins or self.pins[str(path)] == actual,
                "Pinned evidence drift: " + str(path))
        self.merge({str(path): actual})
        return raw

    def json(self, path):
        return json.loads(self.read(path))

    def check(self):
        for path, expected in self.pins.items():
            require(preflight.sha(path) == expected, "Pinned evidence drift: " + path)


def elf_metadata(blob):
    require(len(blob) >= 64 and blob[:6] == b"\x7fELF\x02\x01", "Invalid ELF64 LE")
    header = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    require(header[:3] == (2, 243, 1) and header[10] == 64 and
            0 < header[11] < 65535, "Unsupported ELF")
    entry, shoff, count = header[3], header[5], header[11]
    require(entry == 0x80000000 and shoff + count * 64 <= len(blob), "Bad ELF sections/entry")
    sections = [struct.unpack_from("<IIQQQQIIQQ", blob, shoff + i * 64) for i in range(count)]
    symbols = {}
    for sec in sections:
        require(sec[1] == 8 or sec[4] + sec[5] <= len(blob), "Truncated ELF section")
        if sec[1] not in (2, 11):
            continue
        require(sec[9] == 24 and sec[5] % 24 == 0 and sec[6] < count, "Bad symbol table")
        strings = sections[sec[6]]
        require(strings[1] == 3 and strings[4] + strings[5] <= len(blob), "Bad symbol strings")
        text = blob[strings[4]:strings[4] + strings[5]]
        for offset in range(sec[4], sec[4] + sec[5], 24):
            name, info, other, index, value, size = struct.unpack_from("<IBBHQQ", blob, offset)
            require(name < len(text) and b"\0" in text[name:], "Bad symbol name")
            label = text[name:text.index(b"\0", name)].decode("utf-8")
            if label not in runner.SYMBOLS:
                continue
            require(label not in symbols and 0 < index < count, "Ambiguous/nonconcrete evidence symbol")
            owner = sections[index]
            length = {"tohost": 8, "g75_result": 8, "g75_trap": 24, "num_failed": 4,
                      "g97_observed": 560, "g97_avl": 40}.get(label, 4)
            require(owner[2] & 2 and owner[3] <= value and
                    value + max(length, size) <= owner[3] + owner[5], "Evidence symbol outside section")
            symbols[label] = value
    require(symbols == runner.SYMBOLS, "Derived ELF symbols differ from sealed preflight")

    def instruction(address):
        matches = [s for s in sections if s[1] != 8 and s[2] & 4 and
                   s[3] <= address and address + 4 <= s[3] + s[5]]
        require(len(matches) == 1, "Unbound executable address")
        sec = matches[0]
        offset = sec[4] + address - sec[3]
        return int.from_bytes(blob[offset:offset + 4], "little")
    codes = {key: instruction(value) for key, value in symbols.items()
             if key.startswith("gap97_probe") or key == "gap97_large_avl"}
    return dict(entry=entry, symbols=symbols, instructions=codes)


def read_csv(path, fields):
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == list(fields), "Unexpected CSV header: " + str(path))
        rows = list(reader)
    require(rows and all(set(row) == set(fields) and all(v is not None and v != "" for v in row.values())
                         for row in rows), "Incomplete/extra CSV fields")
    return rows


def commit_rows(path):
    parsed = []
    hex_fields = {"pc", "insn", "rd_wdata", "mem_addr", "mem_rmask", "mem_wmask", "mem_wdata"}
    for row in read_csv(path, COMMIT_FIELDS):
        require(row["event"] in ("retire", "arch_start", "cvx_req", "cvx_resp"),
                "Unexpected commit event/vector data activity")
        parsed.append({key: value if key == "event" else int(value, 16 if key in hex_fields else 10)
                       for key, value in row.items()})
    require(all(r["trap"] == 0 for r in parsed), "Trapped/unknown commit")
    require(all(a["cycle"] <= b["cycle"] for a, b in zip(parsed, parsed[1:])), "Cycle order regression")
    return parsed


def is_accelerator(insn):
    return (insn & 127 == 0x57 or
            (insn & 127 == 0x73 and (insn >> 12) & 7 in (1, 2, 3, 5, 6, 7) and
             insn >> 20 in (8, 9, 10, 15, 0xc20, 0xc21, 0xc22)))


def architecture_audit(rows, meta):
    symbols, code = meta["symbols"], meta["instructions"]
    retires = [r for r in rows if r["event"] == "retire"]
    require(retires and [r["order"] for r in retires] == list(range(len(retires))), "Incomplete retirement order")
    registers, memory, probes, terminal = {0: 0}, {}, [], []
    for row in retires:
        require(0 <= row["rd"] < 32, "Invalid destination register")
        require(row["pc"] != symbols["trap_fail"], "Trap handler retired")
        for phase in range(10):
            label = "gap97_probe%d" % phase
            if row["pc"] == symbols[label]:
                require(row["insn"] == code[label], "CSR differs from ELF instruction")
                rd = preflight.validate_probe(row["insn"], phase, registers)
                require(row["rd"] == rd and row["rd_wdata"] == preflight.phase_oracle(phase)[3],
                        "CSR old value/destination mismatch")
                probes.append(phase)
        if row["pc"] == symbols["gap97_large_avl"]:
            insn = row["insn"]
            require(insn == code["gap97_large_avl"] and insn & 127 == 0x57 and
                    (insn >> 12) & 7 == 7 and insn >> 20 == 0, "Wrong vset instruction")
            rd, rs1 = (insn >> 7) & 31, (insn >> 15) & 31
            require(rd != 0 and rs1 != 0 and registers.get(rs1) == 1 << 20 and
                    row["rd"] == rd and row["rd_wdata"] == 128, "Large AVL/returned VL mismatch")
            probes.append("avl")
        mask = row["mem_wmask"]
        if mask:
            address, data = row["mem_addr"], row["mem_wdata"]
            size = bin(mask).count("1")
            require(0 < size <= 8 and mask == ((1 << size) - 1) << (address & 7) and
                    address % size == 0, "Invalid unshifted store mask/alignment")
            for byte in range(size):
                memory[address + byte] = (data >> (8 * byte)) & 255
            if address == symbols["tohost"]:
                require(size == 8, "Partial tohost write")
                terminal.append((row["order"], data))
        if row["rd"]:
            registers[row["rd"]] = row["rd_wdata"]
    require(probes == list(range(10)) + ["avl"], "Missing/duplicate/reordered CSR/vset probes")
    after_vset = [r for r in retires if r["pc"] != symbols["gap97_large_avl"] and
                  r["order"] > next(r["order"] for r in retires if r["pc"] == symbols["gap97_large_avl"]) and
                  is_accelerator(r["insn"])]
    require(len(after_vset) == 4, "Missing/extra post-vset CSR reads")
    for row, (csr, value) in zip(after_vset, ((0xc20, 128), (0xc21, 0), (0xc22, 128), (8, 0))):
        insn = row["insn"]
        require(insn & 127 == 0x73 and insn >> 20 == csr and (insn >> 12) & 7 == 2 and
                (insn >> 15) & 31 == 0 and row["rd"] == (insn >> 7) & 31 != 0 and
                row["rd_wdata"] == value, "Post-vset CSR return mismatch")
    require(terminal == [(len(retires) - 1, 1)], "Incomplete/failed/overwritten terminal tohost")
    expected = {}

    def word(address, value, size=8):
        for i in range(size):
            expected[address + i] = (value >> (8 * i)) & 255
    for phase in range(10):
        for column, value in enumerate(preflight.phase_oracle(phase)):
            word(symbols["g97_observed"] + phase * 56 + column * 8, value)
    for column, value in enumerate((128, 128, 0, 128, 0)):
        word(symbols["g97_avl"] + column * 8, value)
    word(symbols["g75_result"], 75, 4)
    word(symbols["g75_result"] + 4, 0, 4)
    word(symbols["num_failed"], 0, 4)
    for offset in (0, 8, 16):
        word(symbols["g75_trap"] + offset, 0)
    require(all(memory.get(a) == v for a, v in expected.items()), "Missing/wrong exact DUT signature")
    return dict(status="ARCHITECTURE_CONTRACT_EXACT", scalar_retirements=len(retires),
                csr_phases=10, checks=75, exact_observed_bytes=600, probes=probes,
                post_vset_csr_reads=after_vset,
                vset_retire=next(r for r in retires if r["pc"] == symbols["gap97_large_avl"]),
                expected_final_memory={hex(a): v for a, v in expected.items()})


def handshake_audit(rows, architecture):
    pending, starts, completed = {}, [], []
    for row in rows:
        event, tid = row["event"], row["trans_id"]
        if event == "retire":
            continue
        require(0 <= tid < 8, "Invalid accelerator transaction ID")
        if event == "arch_start":
            require(tid not in pending and row["order"] == len(starts) and is_accelerator(row["insn"]),
                    "Duplicate/unexpected architectural start")
            token = dict(start=row, request=None, response=None)
            starts.append(token)
            pending[tid] = token
        elif event == "cvx_req":
            require(tid in pending and pending[tid]["request"] is None and
                    pending[tid]["start"]["insn"] == row["insn"], "Unbound/duplicate accepted request")
            pending[tid]["request"] = row
        elif event == "cvx_resp":
            require(tid in pending and pending[tid]["request"] is not None and row["insn"] == 0,
                    "Orphan/premature accelerator response")
            token = pending.pop(tid)
            token["response"] = row
            completed.append(token)
    require(not pending and len(completed) == len(starts), "Incomplete accelerator handshake")
    retired = [r for r in rows if r["event"] == "retire" and is_accelerator(r["insn"])]
    require(len(starts) == len(retired), "Accelerator start/retirement population differs")
    require(len(starts) == 85, "Not exact ten CSR phases plus vset/four readbacks")
    for token, retire in zip(starts, retired):
        start, request, response = token["start"], token["request"], token["response"]
        require(start["insn"] == retire["insn"] and
                start["cycle"] <= request["cycle"] <= response["cycle"] <= retire["cycle"] and
                (retire["rd"] == 0 or response["rd_wdata"] == retire["rd_wdata"]),
                "Handshake/retirement encoding, timing, or result mismatch")
    vset = [t for t in starts if t["start"]["insn"] & 127 == 0x57]
    require(len(vset) == 1 and vset[0]["request"]["insn"] == architecture["vset_retire"]["insn"] and
            vset[0]["response"]["rd_wdata"] == 128, "Vset interface result/lifecycle mismatch")
    return dict(status="CVX_HANDSHAKES_BOUND", requests=len(starts), responses=len(completed),
                vset_requests=1, vset_responses=1, vset=vset[0],
                evidence="commit_trace.csv arch_start/cvx_req/cvx_resp; NOT vector_trace.csv",
                request_operand_fields_observable=False,
                operand_proof="scalar GPR reconstruction at labelled vset retirement")


def validate_scalar(result, retirements):
    require(result["status"] == "TERMINAL_TOHOST_MATCH" and result["ara_trap_events"] == 0 and
            result["matched_instructions"] == result["ara_committed_instructions"] ==
            result["ara_retired_instructions"] == retirements and
            result["skipped_unobservable_register_values"] == 0 and
            result["stopped_at_unobservable"] is None and result["mismatch"] is None,
            "Incomplete/nonexact scalar comparison")


def validate_vector(result):
    zero = ("vector_destination_requests", "prefix_vector_destination_requests", "compared_instructions",
            "compared_bytes", "skipped_unknown_bytes", "non_bit_exact_instructions", "unobservable_instructions")
    empty = ("incomplete_requests", "unretired_requests", "trapped_requests", "instructions")
    require(result["status"] == "UNOBSERVABLE" and result["nr_lanes"] == 4 and
            result["vlen_bits"] == 1024 and all(result[k] == 0 for k in zero) and
            all(result[k] == [] for k in empty) and result["first_mismatch"] is None and
            result["stopped_at_spike_index"] is None, "Not exact zero-vector-data UNOBSERVABLE")


def runtime(run, meta, spike):
    rows = commit_rows(run / "commit_trace.csv")
    architecture = architecture_audit(rows, meta)
    handshakes = handshake_audit(rows, architecture)
    vector_rows = read_csv(run / "vector_trace.csv", VECTOR_FIELDS)
    hex_fields = {"insn", "be", "wdata"}
    require(len(vector_rows) == 1 and vector_rows[0]["event"] == "config" and
            all(int(value, 16 if key in hex_fields else 10) ==
                {"nr_lanes": 4, "vlen_bits": 1024}.get(key, 0)
                for key, value in vector_rows[0].items() if key != "event"),
            "Vector data events/config differ")
    scalar = compare_commit_prefix(spike, run / "commit_trace.csv", meta["entry"],
        terminal_tohost_address=meta["symbols"]["tohost"], rvfi_store_data_layout="unshifted")
    validate_scalar(scalar, architecture["scalar_retirements"])
    vector = compare_vector_commits(spike, run / "commit_trace.csv", run / "vector_trace.csv", meta["entry"])
    validate_vector(vector)
    require(not check_contract_log(run / "run.vcs.log"), "Contract/simulator failure")
    log = (run / "run.vcs.log").read_text()
    summaries = [parse_contract_summary(line) for line in log.splitlines() if "[ARA_CONTRACT]" in line]
    require(len(summaries) == 1 and summaries[0] is not None and
            summaries[0]["requests"] == summaries[0]["responses"] == handshakes["requests"] and
            summaries[0]["exceptions"] == summaries[0]["mmu_request_cycles"] == 0,
            "Contract counters do not bind handshake population")
    require(log.count("Core Test *** SUCCESS ***") == 1, "Missing/duplicate software success")
    scope = dict(status="ZERO_VECTOR_DATA_REQUESTS_ARCH_CONFIG_CHECKED", data_requests=0,
                 data_bytes=0, vector_comparator_status="UNOBSERVABLE", vector_comparison_pass=False,
                 vset_architecture_checked=True, cvx_handshakes_checked=True,
                 vector_trace_evidence="one config row, no request/alloc/done/write rows")
    return dict(scalar=scalar, vector=vector, architecture=architecture, handshakes=handshakes,
                vector_data_scope=scope, contract=summaries[0], elf_metadata=meta)


def prepare_chain():
    book = PinBook()
    book.merge({str(SELF): SELF_SHA,
                str(Path(runner.__file__).resolve()): "7a46b9e2443625040b597ee59499b11e87d21c036aaff027f0e39cc00abcf063",
                str(Path(preflight.__file__).resolve()): "f24897358b1c13ed3bc062505f202e43a424ed9446307d187f5ba225df2817ee",
                str(runner.PRE / "preflight-manifest.json"): runner.PRE_SEAL,
                str(RUN / "manifest.json"): PREPARED_SEAL,
                str(RUN.with_name(RUN.name + ".prepared.json")): PREPARED_SEAL,
                **{str(BASE / name): seal for name, seal in BASE_SEALS.items()}})
    pre = book.json(runner.PRE / "preflight-manifest.json")
    runner.validate_preflight(pre)
    book.merge(pre["pins"])
    manifest = book.json(RUN / "manifest.json")
    require(book.json(RUN.with_name(RUN.name + ".prepared.json")) == manifest, "Run/prepared mismatch")
    book.merge(manifest["pins"])
    require(all(manifest["pins"].get(p) == h for p, h in pre["pins"].items()), "Run omitted preflight pins")
    expected_spec = {k: pre[k] for k in ("case", "checks", "symbols", "baseline_tests", "target_unhit_count",
                     "expected_vector_data_requests", "expected_vector_data_bytes", "expected_vsetvli")}
    require(manifest["command"] == runner.command(RUN) and manifest["preflight"] == expected_spec and
            manifest["timeout_s"] == 600 and manifest["coverage_admitted"] is False and
            manifest["rtl_changed"] is False and manifest["admission_performed"] is False,
            "Foreign run command/contract")
    status = book.json(RUN / "simulation-status.json")
    require(status == dict(status="SIMULATION_EXITED_NOT_ADMITTED", returncode=0, case=runner.NAME,
                           coverage_admitted=False, admission_performed=False), "Run not successful terminal")
    old = book.json(BASE / "combined-bits.json")
    state = book.json(BASE / "status.json")
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 705 and
            len(old["tests"]) == len(set(old["tests"])) == 705, "Wrong historical705 baseline")
    require(book.read(BASE / "combined-inputs.txt").decode().splitlines() == [str(DESIGN), *old["tests"]],
            "Historical membership/order differs")
    book.merge(book.json(BASE / "evidence-pins.json"))
    # All inherited expectations must match before any new artifact is snapshotted.
    book.check()
    for relative, expected in old["design"].items():
        book.merge({str(DESIGN / "snps/coverage/db" / relative): expected})
    for path in [Path(__file__).with_name("test_admit_gap97_offline.py"), Path(bitmap.__file__).resolve(),
                 *sorted((ROOT / "verification/ara_verify").glob("*.py")),
                 ROOT / "hardware/tb/ara_commit_monitor.sv", ROOT / "verification/uvm/ara_acc_contract_monitor.sv"]:
        book.read(path)
    source_pins = book.json(OUT / "repaired-aligned-build-20260930-01/build-source-pins.json")
    for path in (ROOT / "hardware/tb/ara_commit_monitor.sv", ROOT / "verification/uvm/ara_acc_contract_monitor.sv"):
        book.merge({str(path): source_pins[str(path)]})
    meta = elf_metadata(book.read(runner.PRE / "input.elf"))
    targets = book.json(runner.PRE / "target-before.json")
    require(targets["baseline_sha256"] == BASE_SEALS["combined-bits.json"] and
            targets["design"] == old["design"] and len(targets["targets"]) == 6, "Wrong six-point baseline")
    require({p["point"]["raw_index"] for p in targets["targets"]} == set(preflight.TARGETS), "Target set differs")
    new_vdb = str(RUN / "code.vdb")
    require(new_vdb not in old["tests"], "Duplicate new VDB")
    names = sorted((RUN / "code.vdb/snps/coverage/db/testdata").iterdir())
    require(len(names) == 1 and names[0].is_dir() and names[0].name == runner.NAME, "Foreign VDB test identity")
    for path in (RUN / "console.log", RUN / "run.vcs.log", RUN / "commit_trace.csv", RUN / "vector_trace.csv"):
        book.read(path)
    for path in sorted((RUN / "code.vdb").rglob("*")):
        if path.is_file():
            book.read(path)
    book.check()
    return book, old, meta, targets


def target_hits(before, sample, targets):
    rows = []
    for target in targets["targets"]:
        scope, raw = target["scope"], target["point"]["raw_index"]
        old, new = before["metrics"]["cond"][scope], sample["metrics"]["cond"][scope]
        require(old["checksum"] == new["checksum"] == target["metric_checksum"] and
                old["width"] == new["width"] == target["width"], "Target shape changed")
        mask = 1 << (old["width"] - raw - 1)
        require(not int(old["bits"], 16) & mask, "Target not zero in705")
        rows.append(dict(target=target, hit_before=False, hit_in_new=bool(int(new["bits"], 16) & mask)))
    return dict(targets=rows, intended_targets=6, hit_targets=sum(r["hit_in_new"] for r in rows),
                all_targets_hit=all(r["hit_in_new"] for r in rows), coverage_gain_is_not_a_PASS_requirement=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check-inputs", "admit"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "admit" and args.output is None:
        parser.error("admit requires --output")
    if args.mode == "check-inputs" and args.output is not None:
        parser.error("check-inputs writes no output")
    out = args.output.absolute() if args.output is not None else None
    if out is not None:
        require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh independent output required")
    book, old, meta, targets = prepare_chain()
    if args.mode == "check-inputs":
        print(json.dumps(dict(status="GAP97_INPUT_CHAIN_CHECKED_NOT_ADMITTED", pins=len(book.pins), baseline=705)))
        return
    result = runtime(RUN, meta, runner.PRE / "spike.trace")
    book.check()
    out.mkdir()
    inputs = out / "new-inputs.txt"
    with inputs.open("x") as stream:
        stream.write(str(DESIGN) + "\n" + str(RUN / "code.vdb") + "\n")
    book.read(inputs)
    try:
        sample = bitmap.collect(inputs)
        require(sample["tests"] == [str(RUN / "code.vdb")], "Wrong new VDB population")
        book.merge(sample["input_hashes"])
        combined = bitmap.combine(old, sample)
        require(combined["tests"] == [*old["tests"], str(RUN / "code.vdb")] and
                len(set(combined["tests"])) == 706, "Wrong exact705+1 union")
        delta = bitmap.delta(old, combined)
        hits = target_hits(old, sample, targets)
        book.check()
        for name, data in (("scalar-comparison.json", result["scalar"]),
                           ("vector-comparison.json", result["vector"]),
                           ("architecture-audit.json", result["architecture"]),
                           ("cvx-handshake-audit.json", result["handshakes"]),
                           ("vector-data-scope.json", result["vector_data_scope"]),
                           ("contract-audit.json", result["contract"]), ("elf-metadata.json", result["elf_metadata"]),
                           ("target-hit-audit.json", hits), ("combined-bits.json", combined),
                           ("raw-bitmap-delta.json", delta)):
            preflight.save(out / name, data)
            book.read(out / name)
        with (out / "combined-inputs.txt").open("x") as stream:
            stream.write("\n".join([str(DESIGN), *combined["tests"]]) + "\n")
        book.read(out / "combined-inputs.txt")
        book.check()
        preflight.save(out / "evidence-pins.json", book.pins)
        book.check()
        preflight.save(out / "status.json", dict(status="PASS_RAW_UNION_HISTORICAL_ONLY", aggregate_passed=706,
             new_passed=1, official_DVE_report=False, rtl_changed=False, new_RTL_signoff=False,
             simulations_started=False, vector_comparator_status="UNOBSERVABLE", vector_comparison_pass=False,
             vector_data_requests=0, vset_architecture_checked=True))
        print(json.dumps(dict(aggregate_passed=706, target_hits=hits["hit_targets"], raw_delta=delta["metrics"])))
    except Exception as error:
        preflight.save(out / "failure.json", dict(status="GAP97_NOT_ADMITTED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()
