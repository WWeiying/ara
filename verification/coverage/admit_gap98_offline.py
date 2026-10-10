"""Strict GAP98 offline replay and historical706+1 admission; never launches EDA."""
import argparse
import json
from pathlib import Path
import struct

import admit_gap97_offline as common
import build_gap98_preflight as software
import run_gap98_simulation as runner

ROOT, OUT, DESIGN = common.ROOT, common.OUT, common.DESIGN
BASE = software.BASE
RUN = OUT / "gap98-div16-pack-old-image-20261006-01"
PRE_SEAL = "3400071e979c91f07424be4dd320a764f905dc9225181aea6e9eff5202f0fa63"
RUN_SEAL = "7017615fb9b789ae25430d74676dc5d6afc33554c986066b42e5b27ec71a5d3f"
BASE_SEALS = dict(zip(("combined-bits.json", "status.json", "combined-inputs.txt", "evidence-pins.json"),
    ("9aef93246352ac70f4df1446e17580497832c26f51d3099608bcd2470f9fa626",
     "4f7a1bd4896c6ce7a15e9503e6b447ccc77aa3e3ea17759905c138d70657b01f",
     "c43a8ba33c8d1596325b8e474c0c50685bdf259be233c2d4a557fa0eac98de66",
     "af861e93e20eb4ffdcabdbc62d76b37c7c10180cb852991efc5e5e5a816e0a61")))
require, save = software.require, software.save


def elf_metadata(blob, expected):
    require(len(blob) >= 64 and blob[:6] == b"\x7fELF\x02\x01", "Invalid ELF64 LE")
    h = struct.unpack_from("<HHIQQQIHHHHHH", blob, 16)
    require(h[:3] == (2, 243, 1) and h[3] == 0x80000000 and h[10] == 64 and
            0 < h[11] < 65535 and h[5] + h[11] * 64 <= len(blob), "Bad ELF header")
    sections = [struct.unpack_from("<IIQQQQIIQQ", blob, h[5] + i * 64) for i in range(h[11])]
    found = {}
    lengths = dict(tohost=8, g75_result=8, g75_trap=24, num_failed=4, trap_fail=4)
    require(set(expected) == set(lengths), "Unexpected ELF evidence symbols")
    for section in sections:
        require(section[1] == 8 or section[4] + section[5] <= len(blob), "Truncated ELF")
        if section[1] not in (2, 11):
            continue
        require(section[9] == 24 and section[5] % 24 == 0 and section[6] < len(sections), "Bad symbol table")
        strings = sections[section[6]]
        require(strings[1] == 3 and strings[4] + strings[5] <= len(blob), "Bad strings")
        text = blob[strings[4]:strings[4] + strings[5]]
        for offset in range(section[4], section[4] + section[5], 24):
            name, info, other, index, value, size = struct.unpack_from("<IBBHQQ", blob, offset)
            require(name < len(text) and b"\0" in text[name:], "Bad symbol name")
            label = text[name:text.index(b"\0", name)].decode()
            if label not in expected:
                continue
            require(label not in found and 0 < index < len(sections), "Ambiguous evidence symbol")
            owner = sections[index]
            require(owner[2] & (4 if label == "trap_fail" else 2) and owner[3] <= value and
                    value + max(size, lengths[label]) <= owner[3] + owner[5], "Evidence outside section")
            found[label] = value
    require(found == expected, "Derived ELF symbols differ")
    return dict(entry=h[3], symbols=found)


def commit_rows(path):
    fields = {"pc", "insn", "rd_wdata", "mem_addr", "mem_rmask", "mem_wmask", "mem_wdata"}
    rows = [{k: v if k == "event" else int(v, 16 if k in fields else 10) for k, v in row.items()}
            for row in common.read_csv(path, common.COMMIT_FIELDS)]
    require(all(r["event"] in ("retire", "arch_start", "cvx_req", "cvx_resp") and r["trap"] == 0
                for r in rows), "Unexpected/trapped commit event")
    require(all(a["cycle"] <= b["cycle"] for a, b in zip(rows, rows[1:])), "Cycle regression")
    return rows


def architecture(rows, meta):
    retires = [r for r in rows if r["event"] == "retire"]
    require(retires and [r["order"] for r in retires] == list(range(len(retires))), "Incomplete scalar retirement")
    symbols = meta["symbols"]
    memory, terminal, vl, flags, restarts, divisions = {}, [], [], [], [], []
    for r in retires:
        require(0 <= r["rd"] < 32 and r["pc"] != symbols["trap_fail"], "Invalid rd/trap handler")
        insn = r["insn"]
        if insn == 0x82821857:
            divisions.append(r["order"])
        if insn & 127 == 0x57 and (insn >> 12) & 7 == 7:
            require(insn >> 20 == 9 and (insn >> 15) & 31 != 0 and
                    r["rd"] == (insn >> 7) & 31 != 0 and r["rd_wdata"] == 128,
                    "Wrong e16/m2/tu/mu VSET return")
            vl.append(r["order"])
        if insn & 127 == 0x73 and insn >> 20 in (1, 8) and (insn >> 12) & 7 == 2 and (insn >> 15) & 31 == 0:
            require(r["rd"] == (insn >> 7) & 31 != 0, "Wrong CSR readback destination")
            (flags if insn >> 20 == 1 else restarts).append((r["order"], r["rd_wdata"]))
        mask, address, data = r["mem_wmask"], r["mem_addr"], r["mem_wdata"]
        if mask:
            size = bin(mask).count("1")
            require(size in (1, 2, 4, 8) and address % size == 0 and
                    mask == ((1 << size) - 1) << (address & 7), "Bad unshifted store mask")
            for byte in range(size):
                memory[address + byte] = (data >> (8 * byte)) & 255
            if address == symbols["tohost"]:
                require(size == 8, "Partial tohost")
                terminal.append((r["order"], data))
    require(terminal == [(len(retires) - 1, 1)], "Nonterminal/failed/duplicate tohost")
    require(len(vl) == len(flags) == len(restarts) == len(divisions) == 8 and
            [v for _, v in flags] == [0, 3, 3, 3] * 2 and all(v == 0 for _, v in restarts),
            "Wrong division/config/fflags/vstart population")
    for i in range(8):
        end = vl[i + 1] if i < 7 else len(retires)
        require(vl[i] < divisions[i] < flags[i][0] < restarts[i][0] < end, "Reordered/missing batch probes")
    required = {}
    for address, value, size in ((symbols["g75_result"], 3112, 4), (symbols["g75_result"] + 4, 0, 4),
                                 (symbols["num_failed"], 0, 4),
                                 *((symbols["g75_trap"] + offset, 0, 8) for offset in (0, 8, 16))):
        required.update({address + i: (value >> (8 * i)) & 255 for i in range(size)})
    require(all(memory.get(a) == v for a, v in required.items()), "Incomplete/wrong DUT signature")
    return dict(status="GAP98_ARCHITECTURE_EXACT", scalar_retirements=len(retires), checks=3112,
                divisions=8, vset_returns=8, flags=[v for _, v in flags], vstart=[v for _, v in restarts],
                expected_final_memory={hex(a): v for a, v in required.items()})


def is_accelerator(insn):
    return common.is_accelerator(insn) or (insn & 127 in (0x07, 0x27) and (insn >> 12) & 7 in (0, 5, 6, 7))


def handshakes(rows):
    pending, starts, complete = {}, [], []
    for row in rows:
        event, tid = row["event"], row["trans_id"]
        if event == "retire":
            continue
        require(0 <= tid < 8, "Invalid transaction")
        if event == "arch_start":
            require(tid not in pending and row["order"] == len(starts) and is_accelerator(row["insn"]),
                    "Unbound accelerator start")
            token = dict(start=row, request=None, response=None)
            pending[tid] = token
            starts.append(token)
        elif event == "cvx_req":
            require(tid in pending and pending[tid]["request"] is None and
                    pending[tid]["start"]["insn"] == row["insn"], "Duplicate/orphan request")
            pending[tid]["request"] = row
        else:
            require(tid in pending and pending[tid]["request"] is not None and row["insn"] == 0,
                    "Orphan response")
            token = pending.pop(tid)
            token["response"] = row
            complete.append(token)
    retired = [r for r in rows if r["event"] == "retire" and is_accelerator(r["insn"])]
    require(not pending and len(starts) == len(complete) == len(retired) > 0, "Incomplete CVX lifecycle")
    for token, retire in zip(starts, retired):
        s, q, p = token["start"], token["request"], token["response"]
        require(s["insn"] == retire["insn"] and s["cycle"] <= q["cycle"] <= p["cycle"] <= retire["cycle"] and
                (retire["rd"] == 0 or p["rd_wdata"] == retire["rd_wdata"]), "CVX binding/timing/result mismatch")
    return dict(status="CVX_FULL_LIFECYCLE_BOUND", requests=len(starts), responses=len(complete))


def validate_vector(result):
    require(result["status"] == "PASS" and result["nr_lanes"] == 4 and result["vlen_bits"] == 1024 and
            all(result[k] == 24 for k in ("vector_destination_requests", "prefix_vector_destination_requests",
                                         "compared_instructions")) and result["compared_bytes"] == 6144 and
            all(result[k] == 0 for k in ("skipped_unknown_bytes", "non_bit_exact_instructions",
                                         "unobservable_instructions")) and
            all(result[k] == [] for k in ("incomplete_requests", "unretired_requests", "trapped_requests")) and
            result["first_mismatch"] is None and result["stopped_at_spike_index"] is None,
            "Incomplete/nonexact vector comparison")
    require(len(result["instructions"]) == 24 and all(r["status"] == "PASS" and
            r["compared_bytes"] == 256 and r["skipped_unknown_bytes"] == r["unknown_write_bytes"] ==
            r["mismatch_count"] == 0 and r["first_mismatch"] is None for r in result["instructions"]),
            "Nonexact individual vector destination")


def runtime(run, meta, spike):
    rows = commit_rows(run / "commit_trace.csv")
    arch, cvx = architecture(rows, meta), handshakes(rows)
    scalar = common.compare_commit_prefix(spike, run / "commit_trace.csv", meta["entry"],
        terminal_tohost_address=meta["symbols"]["tohost"], rvfi_store_data_layout="unshifted")
    common.validate_scalar(scalar, arch["scalar_retirements"])
    common.read_csv(run / "vector_trace.csv", common.VECTOR_FIELDS)
    vector = common.compare_vector_commits(spike, run / "commit_trace.csv", run / "vector_trace.csv", meta["entry"])
    validate_vector(vector)
    require(not common.check_contract_log(run / "run.vcs.log"), "Contract/simulator/software failure")
    log = (run / "run.vcs.log").read_text()
    summaries = [common.parse_contract_summary(s) for s in log.splitlines() if "[ARA_CONTRACT]" in s]
    require(len(summaries) == 1 and summaries[0] is not None and
            summaries[0]["requests"] == summaries[0]["responses"] == cvx["requests"] and
            summaries[0]["exceptions"] == summaries[0]["mmu_request_cycles"] == 0 and
            log.count("Core Test *** SUCCESS ***") == 1, "Contract counters/success differ")
    oracle = software.validate_spike(software.parse_spike_commits(spike), meta["symbols"])
    return dict(scalar=scalar, vector=vector, architecture=arch, handshakes=cvx, contract=summaries[0],
                independent_spike_oracle=oracle, elf_metadata=meta)


def prepare_chain():
    book = common.PinBook()
    book.merge({str(runner.PRE / "preflight-manifest.json"): PRE_SEAL,
                str(RUN.with_name(RUN.name + ".prepared.json")): RUN_SEAL,
                str(RUN / "manifest.json"): RUN_SEAL,
                **{str(BASE / name): seal for name, seal in BASE_SEALS.items()}})
    pre = book.json(runner.PRE / "preflight-manifest.json")
    main = runner.validate(pre)
    book.merge(pre["pins"])
    manifest = book.json(RUN / "manifest.json")
    book.merge(manifest["pins"])
    require(book.json(RUN.with_name(RUN.name + ".prepared.json")) == manifest and
            manifest["preflight"] == pre and manifest["command"] == runner.command(main, RUN) and
            manifest["timeout_s"] == 600 and manifest["old_image_files_checked"] == 66 and
            all(manifest[k] is False for k in ("coverage_admitted", "rtl_changed", "new_RTL_signoff", "admission_performed")) and
            all(manifest["pins"].get(p) == h for p, h in pre["pins"].items()), "Run contract differs")
    require(book.json(RUN / "simulation-status.json") == dict(status="SIMULATION_EXITED_NOT_ADMITTED",
            returncode=0, case=runner.NAME, coverage_admitted=False, admission_performed=False), "Run failed/nonterminal")
    old, state = book.json(BASE / "combined-bits.json"), book.json(BASE / "status.json")
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 706 and
            len(old["tests"]) == len(set(old["tests"])) == 706 and
            book.read(BASE / "combined-inputs.txt").decode().splitlines() == [str(DESIGN), *old["tests"]],
            "Wrong exact historical706 population")
    book.merge(book.json(BASE / "evidence-pins.json"))
    book.check()
    for relative, expected in old["design"].items():
        book.merge({str(DESIGN / "snps/coverage/db" / relative): expected})
    for path in [Path(__file__).resolve(), Path(__file__).with_name("test_admit_gap98_offline.py"),
                 Path(common.__file__).resolve(), Path(common.bitmap.__file__).resolve(),
                 *sorted((ROOT / "verification/ara_verify").glob("*.py"))]:
        book.read(path)
    meta = elf_metadata(book.read(main["input_elf"]), main["symbols"])
    targets = book.json(pre["target_before"])
    require(targets["baseline_sha256"] == BASE_SEALS["combined-bits.json"] and targets["design"] == old["design"] and
            runner.rebind.select_scopes([r["scope"] for r in targets["rows"]]) == [r["scope"] for r in targets["rows"]] and
            sum(len(r["missing_points"]) for r in targets["rows"]) == targets["target_unhit_count"] == 125,
            "Eight-scope125 target binding differs")
    require(str(RUN / "code.vdb") not in old["tests"], "Duplicate VDB")
    tests = list((RUN / "code.vdb/snps/coverage/db/testdata").iterdir())
    require(len(tests) == 1 and tests[0].is_dir() and tests[0].name == runner.NAME, "Foreign VDB test")
    for path in [RUN / name for name in ("console.log", "run.vcs.log", "commit_trace.csv", "vector_trace.csv")]:
        book.read(path)
    for path in sorted((RUN / "code.vdb").rglob("*")):
        if path.is_file():
            book.read(path)
    book.check()
    return book, old, meta, targets, main


def target_hits(before, sample, targets):
    rows = []
    for target in targets["rows"]:
        scope = target["scope"]
        a, b = before["metrics"]["branch"][scope], sample["metrics"]["branch"][scope]
        require(a["width"] == b["width"] == target["width"] and
                a["checksum"] == b["checksum"] == target["checksum"], "Target shape drift")
        for point in target["missing_points"]:
            raw = point["raw_index"]
            require(56 <= raw <= 82, "Outside-band target")
            mask = 1 << (a["width"] - raw - 1)
            require(not int(a["bits"], 16) & mask, "Nonzero baseline target")
            rows.append(dict(scope=scope, point=point, hit_before=False, hit_in_new=bool(int(b["bits"], 16) & mask)))
    require(len(rows) == len({(r["scope"], r["point"]["raw_index"]) for r in rows}) == 125, "Target population differs")
    return dict(targets=rows, intended_targets=125, physical_scopes=8,
                hit_targets=sum(r["hit_in_new"] for r in rows), coverage_gain_is_not_a_PASS_requirement=True)


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
        book, old, meta, targets, software_case = prepare_chain()
        if args.mode == "check-inputs":
            print(json.dumps(dict(status="GAP98_INPUT_CHAIN_CHECKED_NOT_ADMITTED", pins=len(book.pins))))
            return
        result = runtime(RUN, meta, Path(software_case["input_spike_trace"]))
        book.check()
        for key, data in result.items():
            save(out / (key + "-audit.json"), data)
            book.read(out / (key + "-audit.json"))
        inputs = out / "new-inputs.txt"
        with inputs.open("x") as stream:
            stream.write(str(DESIGN) + "\n" + str(RUN / "code.vdb") + "\n")
        book.read(inputs)
        sample = common.bitmap.collect(inputs)
        require(sample["tests"] == [str(RUN / "code.vdb")], "Wrong new sample population")
        book.merge(sample["input_hashes"])
        combined = common.bitmap.combine(old, sample)
        require(combined["tests"] == [*old["tests"], str(RUN / "code.vdb")] and
                len(set(combined["tests"])) == 707, "Wrong exact706+1 union")
        hits, delta = target_hits(old, sample, targets), common.bitmap.delta(old, combined)
        book.check()
        for name, data in (("target-hit-audit.json", hits), ("raw-bitmap-delta.json", delta),
                           ("combined-bits.json", combined)):
            save(out / name, data)
            book.read(out / name)
        with (out / "combined-inputs.txt").open("x") as stream:
            stream.write("\n".join([str(DESIGN), *combined["tests"]]) + "\n")
        book.read(out / "combined-inputs.txt")
        book.check()
        save(out / "evidence-pins.json", book.pins)
        book.check()
        save(out / "status.json", dict(status="PASS_RAW_UNION_HISTORICAL_ONLY", aggregate_passed=707,
             new_passed=1, official_DVE_report=False, rtl_changed=False, new_RTL_signoff=False,
             simulations_started=False, vector_comparator_status="PASS", vector_bytes=6144,
             vector_destination_instructions=24, checks=3112))
        print(json.dumps(dict(aggregate_passed=707, target_hits=hits["hit_targets"], raw_delta=delta["metrics"])))
    except Exception as error:
        if out:
            save(out / "failure.json", dict(status="GAP98_NOT_ADMITTED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()
