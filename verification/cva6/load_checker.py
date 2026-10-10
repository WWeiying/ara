"""Replay load/cache attempt lifetimes independently of the SV test ledger.

This is a boundary contract, not a CPU commit or real-MMU correctness checker.
"""

from collections import Counter
import json
import re

from cva6.checker import ERROR_PATTERN

CASES = (
    "back_to_back_hit", "wait_grant_misaligned", "wait_grant_access_fault",
    "wait_grant_page_fault", "page_conflict_fault", "wait_grant_return_collision",
    "page_conflict_pulse_collision", "tlb_miss_fault", "tlb_miss_retry",
    "nonidempotent_retry", "accepted_tag_fault", "flush_old_miss_and_queued_head",
    "flush_same_accept", "flush_same_fault", "fault_then_same_id",
)
MEMORY_WORD = 0x1122334455667788
PRE_FIELDS = frozenset("""
cycle epoch in_valid in_seq in_id in_addr in_expected_cause head_valid head_seq head_id head_addr
bypass_count bypass_next bypass_ready state next_state pop translation_req fault_enable fault cause tval
dtlb_hit conflict stall_ni stores_empty wb_clear commit_id flush req gnt req_id tag kill rvalid rid rdata
return_seq valid result_id result_seq result ex_valid ex_cause ex_tval ldbuf_valid ldbuf_next
ldbuf_flushed ldbuf_flushed_next ldbuf_w ldbuf_r last_id slot0_id slot1_id cache_state cache_next
cache_busy cache_stall rd_req rd_allow cache_hit miss_req miss_ack miss_return mem_pending
paddr miss_addr
""".split())
POST_FIELDS = frozenset("cycle epoch state bypass_count ldbuf_valid ldbuf_flushed cache_state fault".split())
BOOL_FIELDS = frozenset("""
in_valid head_valid bypass_ready pop translation_req fault_enable fault dtlb_hit conflict stall_ni
stores_empty wb_clear flush req gnt tag kill rvalid valid ex_valid ldbuf_w ldbuf_r cache_busy
cache_stall rd_req rd_allow cache_hit miss_req miss_ack miss_return
""".split())


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
    require(text and text.endswith("\n"), "missing/truncated trace")
    rows = [json.loads(line, object_pairs_hook=unique_object) for line in text.splitlines()]
    require(len(rows) % 2 == 0, "missing pre/post pair")
    for index, row in enumerate(rows):
        phase = "pre" if index % 2 == 0 else "post"
        fields = PRE_FIELDS if phase == "pre" else POST_FIELDS
        require(isinstance(row, dict) and set(row) == fields | {"phase", "case"}, "trace schema mismatch")
        require(row["phase"] == phase and row["cycle"] == index // 2 + 1, "trace order/gap")
        require(isinstance(row["case"], str), "invalid case label")
        for name in fields:
            require(type(row[name]) is int and 0 <= row[name] < 2**64, f"unknown/invalid {name}")
            if name in BOOL_FIELDS:
                require(row[name] in (0, 1), f"nonbinary {name}")
    return rows


def replay(rows, require_coverage=True):
    queue, active, transactions, slots = [], {}, {}, {}
    events, coverage = Counter(), Counter()
    epoch = 0
    pending_memory = 0
    cache_owner = 0
    seen_ids, seen_slots, labels = set(), set(), []
    last_post = None
    for pre, post in zip(rows[::2], rows[1::2]):
        p = pre
        prefix = f"cycle {p['cycle']} {p['case']}: "

        def check(ok, what):
            require(ok, prefix + what)

        check(p["epoch"] == epoch, "wrong epoch")
        check(post["case"] == p["case"], "case changes across edge")
        if p["case"] != "reset" and (not labels or labels[-1] != p["case"]):
            labels.append(p["case"])
        if last_post is not None:
            for name in ("state", "cache_state", "ldbuf_valid", "ldbuf_flushed", "bypass_count", "fault"):
                check(p[name] == last_post[name], f"unrecorded state change: {name}")
        check(p["bypass_count"] == len(queue), "bypass occupancy mismatch")
        check(p["bypass_ready"] == (not queue), "bypass readiness mismatch")
        check(p["ldbuf_valid"] == sum(1 << s for s in slots), "load buffer occupancy mismatch")
        for slot, owner in slots.items():
            check(p[f"slot{slot}_id"] == transactions[owner]["id"], "slot ID ownership mismatch")
        if p["in_valid"]:
            ident, seq = p["in_id"], p["in_seq"]
            check(p["bypass_ready"] and ident < 8, "illegal upstream stimulus")
            check(seq == len(transactions) + 1 and ident not in active, "reused live ID/sequence")
            transactions[seq] = dict(id=ident, address=p["in_addr"], cause=p["in_expected_cause"],
                                     epoch=epoch, pops=0, done=0, canceled=False, attempts=0, returns=0)
            active[ident] = seq
            queue.append(seq)
            events["issued"] += 1
            coverage["id_reuse"] += ident in seen_ids
            seen_ids.add(ident)
        head = queue[0] if queue else 0
        check(p["head_valid"] == bool(head), "wrong head validity")
        if head:
            tx = transactions[head]
            check((p["head_seq"], p["head_id"], p["head_addr"]) == (head, tx["id"], tx["address"]),
                  "head identity changed")
        if p["head_valid"] and p["stall_ni"] and not p["fault"]:
            check(not p["pop"], "NI request popped before ordering conditions were satisfied")
        if p["pop"]:
            check(bool(queue), "orphan pop")
            seq = queue.pop(0)
            transactions[seq]["pops"] += 1
            check(transactions[seq]["pops"] == 1, "duplicate pop")
            events["pops"] += 1
        returned = slots.get(p["rid"], 0) if p["rvalid"] else 0
        check(p["return_seq"] == returned, "TB return ledger disagrees with independent ownership")
        completed = active.get(p["result_id"], 0) if p["valid"] else 0
        check(p["result_seq"] == completed, "TB result ledger disagrees with independent ownership")
        if p["valid"] and not p["flush"]:
            check(completed != 0, "orphan/duplicate completion")
            tx = transactions[completed]
            check(not tx["canceled"] and tx["pops"] == 1, "unaccepted/canceled instruction completed")
            check(p["ex_valid"] == bool(tx["cause"]), "wrong exception status")
            if p["ex_valid"]:
                check((p["ex_cause"], p["ex_tval"]) == (tx["cause"], tx["address"]), "wrong exception payload")
                check(not returned or returned == completed, "exception attributed to old cache return")
                events["exceptions"] += 1
            else:
                check(returned == completed and p["result"] == MEMORY_WORD, "wrong normal result/owner")
                events["normal"] += 1
            tx["done"] += 1
            check(tx["done"] == 1, "duplicate completion")
            del active[p["result_id"]]
            events["completed"] += 1
        check(p["ldbuf_w"] == bool(p["req"] and p["gnt"]) and p["ldbuf_r"] == p["rvalid"],
              "buffer movement differs from accepted/returned attempts")
        if p["tag"] and not p["kill"]:
            check(cache_owner > 0 and p["paddr"] == transactions[cache_owner]["address"],
                  "tag phase physical address belongs to wrong request")
        if p["rvalid"]:
            check(returned > 0, "cache response without an accepted attempt")
            transactions[returned]["returns"] += 1
            del slots[p["rid"]]
            events["returns"] += 1
        if p["gnt"]:
            check(p["req"] and head and p["req_id"] < 2, "illegal cache grant")
            check(p["req_id"] not in slots, "live buffer overwritten")
            slots[p["req_id"]] = head
            cache_owner = head
            transactions[head]["attempts"] += 1
            events["accepted_attempts"] += 1
            coverage["slot_reuse"] += p["req_id"] in seen_slots
            seen_slots.add(p["req_id"])
        check(p["mem_pending"] == pending_memory, "memory ledger drift")
        if p["miss_return"]:
            check(pending_memory == 1, "unmatched memory return")
            pending_memory -= 1
            events["memory_returns"] += 1
        if p["miss_ack"]:
            check(p["miss_req"] and pending_memory == 0, "illegal miss acceptance")
            check(cache_owner > 0 and p["miss_addr"] == transactions[cache_owner]["address"],
                  "miss physical address belongs to wrong request")
            pending_memory += 1
            events["memory_requests"] += 1
        if p["flush"]:
            for seq in active.values():
                transactions[seq]["canceled"] = True
                events["canceled"] += 1
            active.clear()
            queue.clear()
            epoch += 1
        check(post["epoch"] == epoch, "post epoch mismatch")
        check(p["bypass_next"] == post["bypass_count"] == len(queue), "bypass edge mismatch")
        check(p["ldbuf_next"] == post["ldbuf_valid"] == sum(1 << s for s in slots), "buffer edge mismatch")
        check(p["ldbuf_flushed_next"] == post["ldbuf_flushed"], "flush bookkeeping edge mismatch")
        check(p["next_state"] == post["state"] and p["cache_next"] == post["cache_state"], "FSM edge mismatch")
        coverage["back_to_back_accept_return"] += bool(p["gnt"] and p["rvalid"])
        coverage["wait_grant_fault"] += bool(p["state"] == 1 and p["fault"] and p["pop"])
        coverage["wait_page_fault"] += bool(p["state"] == 3 and p["fault"] and p["pop"])
        coverage["grant_return_collision"] += bool(p["state"] == 1 and p["fault"] and p["rvalid"] and not p["pop"])
        coverage["page_return_collision"] += bool(p["state"] == 3 and p["fault"] and p["rvalid"] and not p["pop"])
        coverage["expired_fault_wait"] += bool(p["case"] == "page_conflict_pulse_collision" and
                                               p["state"] == 3 and not p["fault"] and p["head_valid"])
        coverage["tlb_kill"] += bool(p["state"] == 4 and p["kill"] and p["rvalid"] and not p["valid"])
        coverage["ni_kill"] += bool(p["state"] == 5 and p["kill"] and p["rvalid"] and not p["valid"])
        coverage["flush_grant"] += bool(p["flush"] and p["gnt"])
        coverage["flush_fault_result"] += bool(p["flush"] and p["valid"] and p["ex_valid"])
        last_post = post
    require(not queue and not active and not slots and pending_memory == 0, "undrained lifecycle")
    for seq, tx in transactions.items():
        require(tx["attempts"] == tx["returns"], f"leaked cache attempt {seq}")
        require((tx["done"] == 0 and tx["pops"] <= 1) if tx["canceled"] else
                (tx["done"] == 1 and tx["pops"] == 1), f"incomplete logical instruction {seq}")
    if require_coverage:
        require(labels == list(CASES), "missing/reordered cases")
        require(all(coverage.values()) and len(coverage) == 12, "missing lifecycle coverage")
        require(events["issued"] == 22 and events["completed"] == 18 and events["canceled"] == 4,
                "logical workload coverage changed")
        require(events["accepted_attempts"] == events["returns"] == 15, "cache workload coverage changed")
    return dict(counts=dict(events), coverage=dict(coverage), cases=labels,
                cycles=len(rows) // 2, transactions=transactions)


def analyze(console, trace, config, returncode=0):
    try:
        require(returncode == 0, "simulator did not exit successfully")
        require(not ERROR_PATTERN.search(console) and "LOAD_CHECK_FAIL" not in console and
                "LOAD_ENV_FAIL" not in console, "simulator/harness failure")
        cfg = json.loads(config, object_pairs_hook=unique_object) if isinstance(config, str) else config
        require(cfg == dict(schema=1, scope="load_bypass_wt_control_boundary_contract", mmu=1, ni=1,
                            load_entries=2, xlen=64, real_mmu=False, real_scoreboard=False,
                            real_cache_array=False), "unsupported scope/configuration")
        result = replay(parse_trace(trace))
        markers = re.findall(r"^LOAD_CONTRACT_END cases=(\d+) transactions=(\d+) cycles=(\d+) checks=(\d+) errors=(\d+)$",
                             console, re.M)
        require(len(markers) == 1, "missing/duplicate final marker")
        cases, txns, cycles, checks, errors = map(int, markers[0])
        require((cases, txns, cycles, errors) == (len(CASES), 22, result["cycles"], 0) and checks > 0,
                "final marker disagrees with trace")
        case_ends = re.findall(r"^LOAD_CASE_END name=(\w+) cycle=\d+ errors=0$", console, re.M)
        require(case_ends == list(CASES), "missing/failed case completion")
        return dict(status="PASS", errors=[], checks=checks, **result)
    except (ValueError, TypeError, KeyError, IndexError) as error:
        return dict(status="FAIL", errors=[str(error)], counts={})
