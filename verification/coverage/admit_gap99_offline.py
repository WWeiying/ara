"""Strict scalar-only GAP99 replay and historical707+1 union; no simulation."""
import argparse
import json
from pathlib import Path
import struct

import admit_gap97_offline as common
import admit_gap98_offline as shape
import build_gap99_preflight as oracle
import run_gap99_simulation as runner
from ara_verify import contract

ROOT, OUT, DESIGN = common.ROOT, common.OUT, common.DESIGN
BASE = OUT / "gap98-offline-admitted-707-20261006-02"
RUN = OUT / "gap99-csr-satp-mprv-old-image-20261006-01"
RUN_SEAL = "193d75d30e4fe98929bd2c969f95732bd23bedfc2e62d051fbaffe286f5373f2"
BASE_SEALS = dict(zip(("combined-bits.json", "status.json", "combined-inputs.txt", "evidence-pins.json"),
    ("49e7ae83ee9df72b09bd2efdccbb73b990defe9a33beca35b3505db019a1ba75",
     "c99bb541e8ee8cd85d81ae896ab12554c047cd9b8ae22548362e60d2adbc5f31",
     "a15ee53aa80358067df1457a670c5761e476aa68663bdeb18167eb3148543991",
     "438bca9d4bfb215bd4d806863a38f756ab210f68d05b2dcfa4920e04c129c163")))
require, save = oracle.require, oracle.save


def elf_metadata(blob, expected):
    base = shape.elf_metadata(blob, {k: v for k, v in expected.items() if k != "g99_observed"})
    header = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    sections = [struct.unpack_from("<IIQQQQIIQQ", blob, header[5] + i * 64) for i in range(header[11])]
    found = []
    for sec in sections:
        if sec[1] not in (2, 11):
            continue
        textsec = sections[sec[6]]
        strings = blob[textsec[4]:textsec[4] + textsec[5]]
        for offset in range(sec[4], sec[4] + sec[5], 24):
            name, info, other, index, value, size = struct.unpack_from("<IBBHQQ", blob, offset)
            label = strings[name:strings.index(b"\0", name)].decode()
            if label != "g99_observed":
                continue
            require(0 < index < len(sections), "Unbound observation symbol")
            owner = sections[index]
            require(owner[2] & 2 and owner[3] <= value and size == 96 and
                    value + size <= owner[3] + owner[5], "Observation outside allocated section")
            found.append(value)
    require(found == [expected["g99_observed"]], "Ambiguous/wrong observation ELF symbol")
    base["symbols"]["g99_observed"] = found[0]
    return base


def commit_rows(path):
    rows = shape.commit_rows(path)
    require(all(r["event"] == "retire" for r in rows), "Unexpected CVX/backend activity in scalar-only case")
    require(not any(shape.is_accelerator(r["insn"]) for r in rows), "Unexpected architectural accelerator instruction")
    return rows


def architecture(rows, meta):
    require(rows and [r["order"] for r in rows] == list(range(len(rows))) and
            all(r["event"] == "retire" and r["trap"] == 0 for r in rows), "Incomplete/trapped scalar retirement")
    s = meta["symbols"]
    memory, registers, satp_reads, satp_writes, status_reads, status_writes, terminal = {}, {0: 0}, [], [], [], [], []
    for row in rows:
        require(row["pc"] != s["trap_fail"] and 0 <= row["rd"] < 32, "Trap handler/invalid destination")
        insn = row["insn"]
        if insn & 127 == 0x73:
            csr, funct, rs1, rd = insn >> 20, (insn >> 12) & 7, (insn >> 15) & 31, (insn >> 7) & 31
            if csr in (0x180, 0x300) and funct == 2 and rs1 == 0:
                require(rd != 0 and row["rd"] == rd, "Wrong CSR read destination")
                (satp_reads if csr == 0x180 else status_reads).append(row["rd_wdata"])
            if csr in (0x180, 0x300) and funct == 1:
                require(rs1 != 0 and rs1 in registers, "Unproven CSR operand")
                if csr == 0x180:
                    require(rd != 0 and row["rd"] == rd and row["rd_wdata"] == 0, "Wrong SATP old return")
                    satp_writes.append(registers[rs1])
                else:
                    require(rd == row["rd"] == 0, "Unexpected MSTATUS destination")
                    status_writes.append(registers[rs1])
        mask, address, data = row["mem_wmask"], row["mem_addr"], row["mem_wdata"]
        if mask:
            size = bin(mask).count("1")
            require(size in (1, 2, 4, 8) and address % size == 0 and
                    mask == ((1 << size) - 1) << (address & 7), "Bad unshifted scalar store")
            for i in range(size):
                memory[address + i] = (data >> (8 * i)) & 255
            if address == s["tohost"]:
                require(size == 8, "Partial tohost")
                terminal.append((row["order"], data))
        if row["rd"]:
            registers[row["rd"]] = row["rd_wdata"]
    require(satp_reads == [0] * 4 and satp_writes == [(1 << 60) | 0x12345, (1 << 60) | 0x12346],
            "Wrong SATP write/readback population or ordering")
    require(len(status_reads) == 5 and len(status_writes) == 4 and status_reads[0] & 0x21800 == 0,
            "Wrong MSTATUS phases/startup contract")
    initial = status_reads[0]
    for phase, priv in enumerate((0, 0x800)):
        setting = (initial & ~0x21888) | 0x20000 | priv
        require(status_writes[phase * 2:phase * 2 + 2] == [setting, initial] and
                status_reads[1 + phase * 2] & 0x21800 == 0x20000 | priv and
                status_reads[2 + phase * 2] == initial, "Wrong MPRV/MPP configuration or restore")
    require(terminal == [(len(rows) - 1, 1)], "Incomplete/duplicate/failed terminal")
    expected = {}
    def word(address, value, size=8):
        expected.update({address + i: (value >> (8 * i)) & 255 for i in range(size)})
    for i, value in enumerate(oracle.expected_observations(0)):
        word(s["g99_observed"] + 8 * i, value)
    word(s["g75_result"], 14, 4)
    word(s["g75_result"] + 4, 0, 4)
    word(s["num_failed"], 0, 4)
    for off in (0, 8, 16):
        word(s["g75_trap"] + off, 0)
    require(all(memory.get(a) == v for a, v in expected.items()), "Wrong/incomplete96-byte oracle/signature")
    return dict(status="GAP99_ARCHITECTURE_EXACT", scalar_retirements=len(rows), checks=14,
                exact_observed_bytes=96, satp_writes=satp_writes, status_writes=status_writes,
                satp_reads=satp_reads, status_reads=status_reads,
                expected_final_memory={hex(a): v for a, v in expected.items()})


def vector_zero(path):
    rows = common.read_csv(path, common.VECTOR_FIELDS)
    hex_fields = {"insn", "be", "wdata"}
    require(len(rows) == 1 and rows[0]["event"] == "config" and
            all(int(value, 16 if key in hex_fields else 10) == {"nr_lanes": 4, "vlen_bits": 1024}.get(key, 0)
                for key, value in rows[0].items() if key != "event"), "Unexpected vector data/reset/config")


def zero_contract(path):
    text = Path(path).read_text()
    records = [(i, contract.parse_contract_summary(line)) for i, line in enumerate(text.splitlines(), 1)
               if "[ARA_CONTRACT]" in line]
    require(len(records) == 1 and records[0][1] is not None and
            all(v == 0 for v in records[0][1].values()), "Not exact zero-CVX contract")
    # The shared checker intentionally requires activity. Only its two activity
    # requirements are inapplicable after proving every counter and trace zero.
    line = records[0][0]
    allowed = {"line %d: requests must be nonzero" % line, "line %d: responses must be nonzero" % line}
    issues = contract.check_contract_log(path)
    require(set(issues) == allowed and len(issues) == 2 and text.count("Core Test *** SUCCESS ***") == 1,
            "Contract/simulator diagnostic outside proven zero-activity exception")
    return dict(status="EXACT_ZERO_CVX_CONTRACT", counts=records[0][1],
                shared_checker_activity_requirements_only_inapplicable=True,
                shared_checker_issues_preserved=issues)


def runtime(run, meta, spike):
    rows = commit_rows(run / "commit_trace.csv")
    arch = architecture(rows, meta)
    vector_zero(run / "vector_trace.csv")
    scalar = common.compare_commit_prefix(spike, run / "commit_trace.csv", meta["entry"],
        terminal_tohost_address=meta["symbols"]["tohost"], rvfi_store_data_layout="unshifted")
    common.validate_scalar(scalar, len(rows))
    vector = common.compare_vector_commits(spike, run / "commit_trace.csv", run / "vector_trace.csv", meta["entry"])
    common.validate_vector(vector)
    independent = oracle.validate(oracle.shared.parse_spike_commits(spike), meta["symbols"])
    return dict(scalar=scalar, vector=vector, architecture=arch, contract=zero_contract(run / "run.vcs.log"),
                independent_spike_oracle=independent, elf_metadata=meta,
                activity_scope=dict(status="SCALAR_ONLY_ZERO_VECTOR_ZERO_CVX_PROVEN", vector_destinations=0,
                    vector_bytes=0, cvx_arch_starts=0, cvx_requests=0, cvx_responses=0, backend_allocations=0,
                    backend_completions=0, vector_comparator_status="UNOBSERVABLE", vector_comparison_pass=False,
                    interface_visibility="commit trace and vector config present; no interface events, not missing handshake proof"))


def prepare_chain():
    book = common.PinBook()
    book.merge({str(runner.PRE / "preflight-manifest.json"): runner.PRE_SEAL,
                str(RUN / "manifest.json"): RUN_SEAL, str(RUN.with_name(RUN.name + ".prepared.json")): RUN_SEAL,
                **{str(BASE / name): seal for name, seal in BASE_SEALS.items()}})
    pre = book.json(runner.PRE / "preflight-manifest.json")
    runner.validate(pre)
    book.merge(pre["pins"])
    manifest = book.json(RUN / "manifest.json")
    book.merge(manifest["pins"])
    require(book.json(RUN.with_name(RUN.name + ".prepared.json")) == manifest and manifest["preflight"] == pre and
            manifest["command"] == runner.command(RUN) and manifest["timeout_s"] == 600 and
            manifest["old_image_files_checked"] == 66 and manifest["baseline_tests"] == 707 and
            all(manifest[k] == 0 for k in ("expected_cvx_requests", "expected_vector_destination_requests", "expected_vector_bytes")) and
            all(manifest[k] is False for k in ("coverage_admitted", "rtl_changed", "new_RTL_signoff", "admission_performed")) and
            all(manifest["pins"].get(p) == h for p, h in pre["pins"].items()), "Run contract differs")
    require(book.json(RUN / "simulation-status.json") == dict(status="SIMULATION_EXITED_NOT_ADMITTED", returncode=0,
            case=runner.NAME, coverage_admitted=False, admission_performed=False), "Failed/nonterminal run")
    old, state = book.json(BASE / "combined-bits.json"), book.json(BASE / "status.json")
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 707 and
            len(old["tests"]) == len(set(old["tests"])) == 707 and
            book.read(BASE / "combined-inputs.txt").decode().splitlines() == [str(DESIGN), *old["tests"]],
            "Wrong historical707 membership")
    book.merge(book.json(BASE / "evidence-pins.json"))
    book.check()
    for relative, expected in old["design"].items():
        book.merge({str(DESIGN / "snps/coverage/db" / relative): expected})
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_admit_gap99_offline.py"),
                 Path(common.__file__).resolve(), Path(shape.__file__).resolve(), Path(common.bitmap.__file__).resolve(),
                 *sorted((ROOT / "verification/ara_verify").glob("*.py"))):
        book.read(path)
    sources = book.json(OUT / "repaired-aligned-build-20260930-01/build-source-pins.json")
    for path in (ROOT / "hardware/tb/ara_commit_monitor.sv", ROOT / "verification/uvm/ara_acc_contract_monitor.sv"):
        book.merge({str(path): sources[str(path)]})
        book.read(path)
    meta = elf_metadata(book.read(pre["input_elf"]), pre["symbols"])
    targets = book.json(pre["target_before"])
    require(targets["baseline_tests"] == 707 and len(targets["targets"]) == 2 and
            {r["point"]["raw_index"] for r in targets["targets"]} == {155, 334} and
            all(r["metric"] == "cond" and not r["hit"] for r in targets["targets"]), "Wrong zero targets")
    require(str(RUN / "code.vdb") not in old["tests"], "Duplicate VDB")
    tests = list((RUN / "code.vdb/snps/coverage/db/testdata").iterdir())
    require(len(tests) == 1 and tests[0].is_dir() and tests[0].name == runner.NAME, "Foreign VDB test")
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
        a, b = before["metrics"]["cond"][scope], sample["metrics"]["cond"][scope]
        require(a["checksum"] == b["checksum"] == target["checksum"] and
                a["width"] == b["width"] == target["width"], "Condition shape drift")
        mask = 1 << (a["width"] - raw - 1)
        require(not int(a["bits"], 16) & mask, "Nonzero target in707")
        rows.append(dict(target=target, hit_before=False, hit_in_new=bool(int(b["bits"], 16) & mask)))
    require(len(rows) == 2 and {r["target"]["point"]["raw_index"] for r in rows} == {155, 334}, "Wrong target population")
    return dict(targets=rows, intended_targets=2, hit_targets=sum(r["hit_in_new"] for r in rows),
                coverage_gain_is_not_a_PASS_requirement=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check-inputs", "admit"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if (args.mode == "admit") != (args.output is not None):
        parser.error("Only admit requires --output")
    out = args.output.absolute() if args.output else None
    if out:
        require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh independent output required")
        out.mkdir()
    try:
        book, old, meta, targets = prepare_chain()
        if args.mode == "check-inputs":
            print(json.dumps(dict(status="GAP99_INPUT_CHAIN_CHECKED_NOT_ADMITTED", pins=len(book.pins))))
            return
        result = runtime(RUN, meta, runner.PRE / "spike.trace")
        book.check()
        for key, value in result.items():
            save(out / (key + "-audit.json"), value)
            book.read(out / (key + "-audit.json"))
        inputs = out / "new-inputs.txt"
        with inputs.open("x") as stream:
            stream.write(str(DESIGN) + "\n" + str(RUN / "code.vdb") + "\n")
        book.read(inputs)
        sample = common.bitmap.collect(inputs)
        require(sample["tests"] == [str(RUN / "code.vdb")], "Wrong new VDB population")
        book.merge(sample["input_hashes"])
        combined = common.bitmap.combine(old, sample)
        require(combined["tests"] == [*old["tests"], str(RUN / "code.vdb")] and
                len(set(combined["tests"])) == 708, "Wrong exact707+1 union")
        hits, delta = target_hits(old, sample, targets), common.bitmap.delta(old, combined)
        book.check()
        for name, value in (("target-hit-audit.json", hits), ("raw-bitmap-delta.json", delta), ("combined-bits.json", combined)):
            save(out / name, value)
            book.read(out / name)
        with (out / "combined-inputs.txt").open("x") as stream:
            stream.write("\n".join([str(DESIGN), *combined["tests"]]) + "\n")
        book.read(out / "combined-inputs.txt")
        book.check()
        save(out / "evidence-pins.json", book.pins)
        book.check()
        save(out / "status.json", dict(status="PASS_RAW_UNION_HISTORICAL_ONLY", aggregate_passed=708,
             new_passed=1, official_DVE_report=False, rtl_changed=False, new_RTL_signoff=False,
             simulations_started=False, vector_comparator_status="UNOBSERVABLE", vector_comparison_pass=False,
             vector_destination_requests=0, vector_bytes=0, cvx_requests=0, checks=14))
        print(json.dumps(dict(aggregate_passed=708, target_hits=hits["hit_targets"], raw_delta=delta["metrics"])))
    except Exception as error:
        if out:
            save(out / "failure.json", dict(status="GAP99_NOT_ADMITTED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()
