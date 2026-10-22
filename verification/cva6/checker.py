"""Fail-closed, pre-NBA transaction replay for the real acc_dispatcher trace."""

from collections import Counter
import json
import re

from .stimulus import MAX_CYCLES

NUMERIC_FIELDS = """
cycle epoch hs accept seq id pc kind view issue_fu issue_op cons stall
ex_valid ex_seq ex_id ex_kind usage empty head_seq head_id head_kind head_insn head_rs2
c0_acc c0_valid c0_id ack0 c1_acc c1_valid c1_id commit commit_id
pending pending_next authorized authorized_next flush in_valid in_ready pop ld_pop st_pop
a_full b_full out_valid out_ready out_fire out_seq out_id out_insn out_rs2 out_frm
spec_ld disp_ld spec_st disp_st no_ld no_st ld_done st_done
resp_valid resp_seq resp_id resp_flags resp_flags_valid result_valid result_seq result_id
result_flags result_flags_valid exception resp_ready
""".split()
BIT_FIELDS = """
hs accept cons stall ex_valid empty c0_acc c0_valid ack0 c1_acc c1_valid commit flush
in_valid in_ready pop ld_pop st_pop a_full b_full out_valid out_ready out_fire no_ld no_st
ld_done st_done resp_valid resp_flags_valid result_valid result_flags_valid resp_ready
""".split()
REQUIRED = {
    "commit_id_mismatch", "port1_blocked", "port1_released", "queue_capacity",
    "flush_ready_cancel", "flush_pending_cancel", "flush_spill_preserved",
    "reuse_canceled_wait", "reuse_responded_wait", "load_pop_ex_store",
    "load_pop_downstream_blocked", "store_pop_downstream_blocked",
    "load_pop_complete_overlap", "store_pop_complete_overlap", "response_without_memory_done",
}
ERROR_PATTERN = re.compile(r"CONTRACT_FAIL|(?:fatal|error)(?:\s*[-:]|\s+\[)|"
                           r"assert(?:ion)?\s+(?:failed|failure)|ASSERT FAILED|"
                           r"segmentation fault|timed?\s*out", re.I)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_trace(text):
    require(text.endswith("\n"), "truncated trace (missing final newline)")
    rows = [json.loads(line, object_pairs_hook=unique_object) for line in text.splitlines()]
    require(0 < len(rows) <= MAX_CYCLES, "empty or over-bound trace")
    for cycle, row in enumerate(rows, 1):
        require(isinstance(row, dict) and set(row) == set(NUMERIC_FIELDS) | {"phase", "label"},
                f"cycle {cycle}: trace schema mismatch")
        require(all(type(row[k]) is int and row[k] >= 0 for k in NUMERIC_FIELDS),
                f"cycle {cycle}: unknown, negative or non-integer signal")
        require(all(row[k] in (0, 1) for k in BIT_FIELDS), f"cycle {cycle}: non-binary signal")
        require(row["phase"] == "pre" and row["epoch"] == 1 and row["cycle"] == cycle,
                f"cycle {cycle}: wrong sampling phase, epoch or sequence")
        require(isinstance(row["label"], str), "invalid trace label")
    return rows


def check_log(log, count, returncode=0):
    require(returncode == 0, f"simulator returned {returncode}")
    require(not ERROR_PATTERN.search(log), "simulator/harness/assertion failure")
    markers = re.findall(r"^CVA6_CONTRACT_COMPLETE.*$", log, flags=re.M)
    require(markers == [f"CVA6_CONTRACT_COMPLETE cycles={count}"],
            "missing, duplicate or incorrect completion marker")


def insn(seq, kind):
    return (0x02000057, 0x02006007, 0x02006027)[kind] | (seq << 7)


def mask(ids):
    return sum(1 << ident for ident in ids)


def check_trace(rows, config, *, require_coverage=True, expected_stimulus=None):
    require((config["xlen"], config["ids"], config["ports"], config["fpga"])
            == (64, 8, 2, 0), "unexpected real configuration")
    require(len(config["fences"]) == 5 and len(set(config["fences"])) == 5,
            "invalid fence enum metadata")
    if expected_stimulus is not None:
        require(len(rows) == len(expected_stimulus), "stimulus/trace length mismatch")
    transactions = {}
    queue, spill, inflight = [], [], {}
    memory = {1: [], 2: []}
    pending, authorized = set(), set()
    pipe = None
    coverage = Counter()
    fences, scalars = set(), set()
    events = []
    max_queue = max_spill = 0

    for r in rows:
        c = r["cycle"]

        def eq(name, value):
            require(r[name] == value, f"cycle {c} {name}: got {r[name]}, expected {value}")

        def event(name, seq):
            events.append({"cycle": c, "event": name, "seq": seq,
                           "id": transactions[seq]["id"], "pc": transactions[seq]["pc"]})

        if expected_stimulus is not None:
            stimulus = expected_stimulus[c - 1]
            require(r["label"] == stimulus["label"], f"cycle {c}: stimulus label mismatch")
            for name in ("seq", "id", "kind", "view", "cons", "c0_acc", "c0_valid", "c0_id",
                         "c1_acc", "c1_valid", "c1_id", "ack0", "flush", "resp_seq", "resp_id",
                         "ld_done", "st_done"):
                eq(name, stimulus[name])
            eq("out_ready", stimulus["ready"])
        require(r["id"] < 8 and r["c0_id"] < 8 and r["c1_id"] < 8,
                f"cycle {c}: ID out of range")
        require(r["kind"] in (0, 1, 2) and r["view"] in range(9), f"cycle {c}: invalid kind/view")
        eq("hs", int(r["seq"] != 0))
        accept = bool(r["hs"] and not r["flush"])
        if r["hs"]:
            require(r["view"] == 1, f"cycle {c}: non-ACCEL handshake in stimulus")
        eq("accept", accept)
        eq("pc", 0x80000000 + 4 * r["seq"] if r["seq"] else 0)
        eq("ex_valid", pipe is not None)
        if pipe is not None:
            t = transactions[pipe]
            eq("ex_seq", pipe); eq("ex_id", t["id"]); eq("ex_kind", t["kind"])

        eq("usage", len(queue))
        eq("pending", mask(pending)); eq("authorized", mask(authorized))
        candidates = queue + ([pipe] if pipe is not None else [])
        head = candidates[0] if candidates else None
        eq("empty", not candidates)
        if head is not None:
            t = transactions[head]
            eq("head_seq", head); eq("head_id", t["id"]); eq("head_kind", t["kind"])
            eq("head_insn", insn(head, t["kind"])); eq("head_rs2", 0xcafe0000 + head)
        for kind, suffix in ((1, "ld"), (2, "st")):
            spec = sum(t["kind"] == kind and t["state"] in ("accepted", "queued")
                       for t in transactions.values())
            eq("spec_" + suffix, spec)
            eq("disp_" + suffix, len(memory[kind]))
            eq("no_" + suffix, not (spec or memory[kind]))

        view = r["view"]
        any_memory = not (r["no_ld"] and r["no_st"])
        stall = (view == 1 and len(queue) >= 2 or
                 view == 2 and r["cons"] and not r["no_st"] or
                 view == 3 and r["cons"] and any_memory or view >= 4 and any_memory)
        eq("stall", bool(stall))
        require(not (accept and stall), f"cycle {c}: upstream accepted while stalled")
        if view in (1, 2, 3):
            eq("issue_fu", config[{1: "accel", 2: "load", 3: "store"}[view]])
        if view >= 4:
            eq("issue_fu", config["ctrl"]); eq("issue_op", config["fences"][view - 4])
        counts = tuple(r[k] for k in ("spec_ld", "disp_ld", "spec_st", "disp_st"))
        state = {(1, 0, 0, 0): "load_spec", (0, 1, 0, 0): "load_disp",
                 (0, 0, 1, 0): "store_spec", (0, 0, 0, 1): "store_disp",
                 (0, 0, 0, 0): "empty"}.get(counts)
        if state and view >= 4:
            fences.add((state, view, r["cons"]))
        if state and view in (2, 3):
            scalars.add((state, view, r["cons"]))
        if view == 1 and stall and not r["hs"]:
            coverage["queue_capacity"] += 1

        commit = bool(r["c0_acc"] and not r["c0_valid"] or
                      r["ack0"] and r["c0_valid"] and r["c1_acc"] and not r["c1_valid"])
        commit_id = r["c1_id"] if r["c0_valid"] else r["c0_id"]
        eq("commit", commit); eq("commit_id", commit_id)
        head_id = transactions[head]["id"] if head else None
        eligible = head is not None and (head_id in authorized or
                    commit and commit_id in pending and head_id == commit_id)
        valid = bool(eligible and not r["flush"])
        eq("in_valid", valid); eq("in_ready", len(spill) < 2)
        require(r["a_full"] + r["b_full"] == len(spill), f"cycle {c}: spill occupancy")
        eq("pop", valid and len(spill) < 2)
        pop = bool(r["pop"])
        pop_kind = transactions[head]["kind"] if pop else 0
        eq("ld_pop", pop_kind == 1); eq("st_pop", pop_kind == 2)
        if head and commit and commit_id in pending and commit_id != head_id:
            coverage["commit_id_mismatch"] += 1
        port1 = (head and r["c0_valid"] and r["c1_acc"] and not r["c1_valid"]
                 and r["c1_id"] == head_id)
        if port1 and not r["ack0"]:
            require(not pop, f"cycle {c}: younger port escaped")
            coverage["port1_blocked"] += 1
        if port1 and r["ack0"] and pop:
            coverage["port1_released"] += 1
        if head and not eligible and transactions[head].get("reused"):
            coverage[f"reuse_{transactions[head]['reused']}_wait"] += 1
        if pop and pop_kind == 1 and r["ex_kind"] == 2:
            coverage["load_pop_ex_store"] += 1
        if pop_kind:
            prefix = {1: "load", 2: "store"}[pop_kind]
            if not r["out_ready"]:
                coverage[prefix + "_pop_downstream_blocked"] += 1
            if r[{1: "ld_done", 2: "st_done"}[pop_kind]]:
                coverage[prefix + "_pop_complete_overlap"] += 1

        eq("out_valid", bool(spill)); eq("out_fire", bool(spill and r["out_ready"]))
        if spill:
            seq = spill[0]
            t = transactions[seq]
            eq("out_seq", seq); eq("out_id", t["id"])
            eq("out_insn", insn(seq, t["kind"])); eq("out_rs2", 0xcafe0000 + seq)
            eq("out_frm", 2)
            if not r["out_ready"]:
                coverage["held_output_cycles"] += 1
        if r["out_fire"]:
            seq = spill.pop(0)
            ident = transactions[seq]["id"]
            require(ident not in inflight, f"cycle {c}: duplicate inflight ID")
            inflight[ident] = seq
            transactions[seq]["state"] = "delivered"
            event("deliver", seq)

        for name, source in (("result_valid", "resp_valid"), ("result_id", "resp_id"),
                             ("result_seq", "resp_seq"), ("result_flags", "resp_flags"),
                             ("result_flags_valid", "resp_flags_valid")):
            eq(name, r[source])
        eq("resp_ready", 1); eq("exception", 0)
        if r["resp_valid"]:
            seq = inflight.pop(r["resp_id"], None)
            require(seq is not None and seq == r["resp_seq"], f"cycle {c}: orphan/duplicate response")
            transactions[seq]["state"] = "responded"
            event("response", seq)
            kind = transactions[seq]["kind"]
            if kind and not r[{1: "ld_done", 2: "st_done"}[kind]] and seq in memory[kind]:
                coverage["response_without_memory_done"] += 1
        for kind, signal in ((1, "ld_done"), (2, "st_done")):
            if r[signal]:
                require(bool(memory[kind]), f"cycle {c}: {signal} underflow")
                seq = memory[kind].pop(0)
                require(transactions[seq]["state"] in ("delivered", "responded"),
                        f"cycle {c}: completion before external acceptance")
                event(signal, seq)

        next_pending, next_authorized = set(pending), set(authorized)
        if pipe is not None:
            next_pending.add(transactions[pipe]["id"])
            transactions[pipe]["state"] = "queued"
            event("enqueue", pipe)
        if commit and commit_id in pending:
            next_pending.discard(commit_id)
            next_authorized.add(commit_id)
        queue = candidates
        if pop:
            seq = queue.pop(0)
            next_authorized.discard(transactions[seq]["id"])
            spill.append(seq)
            transactions[seq]["state"] = "spilled"
            if pop_kind:
                memory[pop_kind].append(seq)
            event("pop", seq)
        if r["flush"]:
            if spill:
                coverage["flush_spill_preserved"] += len(spill)
            for seq in queue:
                ident = transactions[seq]["id"]
                if ident in authorized:
                    coverage["flush_ready_cancel"] += 1
                if ident in pending:
                    coverage["flush_pending_cancel"] += 1
                transactions[seq]["state"] = "canceled"
                event("cancel", seq)
            queue = []
            next_pending.clear(); next_authorized.clear()
        eq("pending_next", mask(next_pending)); eq("authorized_next", mask(next_authorized))
        pending, authorized = next_pending, next_authorized
        pipe = None
        if accept:
            seq, ident = r["seq"], r["id"]
            require(seq not in transactions, f"cycle {c}: duplicate issue identity")
            old = [t for t in transactions.values() if t["id"] == ident]
            require(all(t["state"] in ("canceled", "responded") for t in old),
                    f"cycle {c}: premature ID reuse")
            transactions[seq] = {"id": ident, "kind": r["kind"], "pc": r["pc"],
                                 "state": "accepted", "reused": old[-1]["state"] if old else None}
            pipe = seq
            event("accept", seq)
        max_queue, max_spill = max(max_queue, len(queue)), max(max_spill, len(spill))

    require(not (queue or spill or inflight or pipe or pending or authorized or any(memory.values())),
            "end of trace has outstanding lifecycle state")
    require(all(t["state"] in ("responded", "canceled") for t in transactions.values()),
            "end of trace has unfinished transactions")
    if require_coverage:
        require(REQUIRED <= coverage.keys(), f"missing coverage: {sorted(REQUIRED - coverage.keys())}")
        require(coverage["port1_blocked"] >= 3, "insufficient older-ack backpressure")
        require(len(fences) == 50, f"fence coverage {len(fences)}/50")
        require(len(scalars) == 20, f"scalar stall coverage {len(scalars)}/20")
        require(max_spill == 2 and max_queue >= 2, "spill/queue not stressed")
    counts = Counter(e["event"] for e in events)
    return {"status": "PASS", "cycles": len(rows), "events": dict(counts),
            "coverage": dict(coverage), "fence_combinations": len(fences),
            "scalar_combinations": len(scalars), "max_queue": max_queue, "max_spill": max_spill,
            "transactions": transactions, "timeline": events}


def check_evidence(log, trace, config, *, returncode=0, expected_stimulus=None):
    rows = parse_trace(trace)
    check_log(log, len(rows), returncode)
    return check_trace(rows, config, expected_stimulus=expected_stimulus)
