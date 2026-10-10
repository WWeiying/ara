"""GAP98 successor: explicitly prove legal backend micro-op lifecycle."""
from collections import Counter
from pathlib import Path

import admit_gap98_offline as old

ORIGINAL_SEAL = "3b53224a383e1dadbc152c4b11a1e8486a86bc9a856e218138f1ac52812b1560"
require = old.require
original_handshakes, original_runtime, original_prepare = old.handshakes, old.runtime, old.prepare_chain


def commit_rows(path):
    hex_fields = {"pc", "insn", "rd_wdata", "mem_addr", "mem_rmask", "mem_wmask", "mem_wdata"}
    rows = [{k: v if k == "event" else int(v, 16 if k in hex_fields else 10) for k, v in r.items()}
            for r in old.common.read_csv(path, old.common.COMMIT_FIELDS)]
    allowed = {"retire", "arch_start", "cvx_req", "cvx_resp", "uop_alloc", "uop_done"}
    require(all(r["event"] in allowed and r["trap"] == 0 for r in rows), "Unknown event/actual trap")
    require(all(a["cycle"] <= b["cycle"] for a, b in zip(rows, rows[1:])), "Cycle regression")
    return rows


def backend_instruction(insn):
    return insn == 0x82821857 or (insn & 127 in (7, 0x27) and (insn >> 12) & 7 == 5)


def uop_audit(rows, vector_path):
    starts = [r for r in rows if r["event"] == "arch_start"]
    require(len(starts) == 48 and [r["order"] for r in starts] == list(range(48)), "Wrong48 architecture requests")
    expected = {r["order"]: r for r in starts if backend_instruction(r["insn"])}
    require(len(expected) == 32 and sum(r["insn"] == 0x82821857 for r in expected.values()) == 8 and
            sum(r["insn"] & 127 == 7 for r in expected.values()) == 16 and
            sum(r["insn"] & 127 == 0x27 for r in expected.values()) == 8, "Wrong32 backend commands")
    codes = Counter(r["insn"] & ~(31 << 15) if r["insn"] & 127 in (7, 0x27) else r["insn"]
                    for r in expected.values())
    require(codes == {0x02005407: 8, 0x02005207: 8, 0x02005827: 8, 0x82821857: 8},
            "Wrong load-v8/load-v4/store-v16/div-v16 opcode distribution")
    seen_starts, active, allocated, completed, pairs = {}, {}, {}, {}, []
    zero_fields = ("pc", "rd", "rd_wdata", "mem_addr", "mem_rmask", "mem_wmask", "mem_wdata", "trap")
    for row in rows:
        if row["event"] == "arch_start":
            seen_starts[row["order"]] = row
        if row["event"] not in ("uop_alloc", "uop_done"):
            continue
        seq, vid = row["order"], row["port"]
        require(seq in expected and seq in seen_starts and 0 <= vid < 8 and
                all(row[k] == 0 for k in zero_fields), "Unbound uop metadata")
        start = expected[seq]
        require(row["insn"] == start["insn"] and row["trans_id"] == start["trans_id"] and
                start["cycle"] <= row["cycle"], "Uop command/transaction/timing differs")
        if row["event"] == "uop_alloc":
            require(vid not in active and seq not in allocated, "VID reuse/duplicate allocation")
            active[vid] = row
            allocated[seq] = row
        else:
            require(vid in active and seq not in completed, "Orphan/duplicate completion")
            alloc = active.pop(vid)
            require(alloc["order"] == seq and alloc["insn"] == row["insn"] and
                    alloc["trans_id"] == row["trans_id"] and alloc["cycle"] <= row["cycle"], "Wrong completion binding")
            completed[seq] = row
            pairs.append(dict(arch=start, allocation=alloc, completion=row))
    require(not active and set(allocated) == set(completed) == set(expected), "Missing/incomplete32 micro-ops")
    vector_rows = old.common.read_csv(vector_path, old.common.VECTOR_FIELDS)
    observed = {}
    for row in vector_rows:
        if row["event"] not in ("alloc", "done"):
            continue
        event = "uop_alloc" if row["event"] == "alloc" else "uop_done"
        key = (event, int(row["arch_seq"]))
        require(key not in observed, "Duplicate vector lifecycle")
        observed[key] = (int(row["cycle"]), int(row["vid"]), int(row["insn"], 16))
    reference = {(r["event"], r["order"]): (r["cycle"], r["port"], r["insn"])
                 for r in rows if r["event"] in ("uop_alloc", "uop_done")}
    require(observed == reference and len(observed) == 64, "Commit/vector lifecycle disagreement")
    return dict(status="GAP98_EXACT32_UOPS_BOUND", allocations=32, completions=32, architectural_requests=48,
                vector_lifecycle_crosscheck=True, pairs=pairs, opcode_counts={hex(k): v for k, v in codes.items()},
                timing_note="alloc may precede CVX acceptance; backend completion need not precede scalar retire")


def handshakes(rows):
    # These rows are not ignored: runtime separately binds every micro-op.
    return original_handshakes([r for r in rows if r["event"] not in ("uop_alloc", "uop_done")])


def runtime(run, meta, spike):
    uops = uop_audit(commit_rows(run / "commit_trace.csv"), run / "vector_trace.csv")
    result = original_runtime(run, meta, spike)
    result["backend-uops"] = uops
    return result


def prepare_chain():
    require(old.software.sha(Path(old.__file__).resolve()) == ORIGINAL_SEAL, "Frozen original checker changed")
    book, *rest = original_prepare()
    book.merge({str(Path(old.__file__).resolve()): ORIGINAL_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_admit_gap98_offline_v2.py")):
        book.read(path)
    monitor = old.ROOT / "hardware/tb/ara_commit_monitor.sv"
    sources = book.json(old.OUT / "repaired-aligned-build-20260930-01/build-source-pins.json")
    book.merge({str(monitor): sources[str(monitor)]})
    book.read(monitor)
    book.check()
    return (book, *rest)


# Only this process uses the successor functions; sealed files are never edited.
old.commit_rows = commit_rows
old.handshakes = handshakes
old.runtime = runtime
old.prepare_chain = prepare_chain


if __name__ == "__main__":
    old.main()
