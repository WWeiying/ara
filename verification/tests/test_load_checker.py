import copy
import json

import pytest

from cva6 import load_checker as checker


def normal_fixture():
    pairs = []
    for cycle in (1, 2):
        pre = dict.fromkeys(checker.PRE_FIELDS, 0)
        pre.update(phase="pre", case="unit", cycle=cycle, bypass_ready=1,
                   rd_allow=1, cache_hit=1, dtlb_hit=1, stores_empty=1, wb_clear=1,
                   rdata=checker.MEMORY_WORD)
        post = dict.fromkeys(checker.POST_FIELDS, 0)
        post.update(phase="post", case="unit", cycle=cycle)
        pairs.append((pre, post))
    p, q = pairs[0]
    p.update(in_valid=1, in_seq=1, in_id=0, in_addr=0x80000100,
             head_valid=1, head_seq=1, head_addr=0x80000100,
             pop=1, req=1, gnt=1, ldbuf_w=1, ldbuf_next=1,
             next_state=2, cache_next=1, translation_req=1)
    q.update(state=2, cache_state=1, ldbuf_valid=1)
    p, q = pairs[1]
    p.update(state=2, cache_state=1, cache_busy=1, tag=1, rvalid=1,
             return_seq=1, ldbuf_valid=1, ldbuf_r=1, valid=1,
             result_seq=1, result=checker.MEMORY_WORD, paddr=0x80000100)
    return [row for pair in pairs for row in pair]


def encode(rows):
    return "".join(json.dumps(row) + "\n" for row in rows)


def replay(rows):
    return checker.replay(checker.parse_trace(encode(rows)), require_coverage=False)


def test_independent_normal_lifecycle():
    result = replay(normal_fixture())
    assert result["counts"] == dict(issued=1, pops=1, accepted_attempts=1,
                                    normal=1, completed=1, returns=1)


@pytest.mark.parametrize("index,field,value", [
    (0, "in_id", 8), (0, "head_addr", 0x80000200), (0, "pop", 0),
    (0, "ldbuf_w", 0), (1, "ldbuf_valid", 0), (2, "result", 0),
    (2, "result_id", 1), (2, "return_seq", 3), (2, "result_seq", 3),
    (2, "rvalid", 0), (2, "ex_valid", 1), (2, "slot0_id", 1),
    (2, "miss_return", 1), (3, "cache_state", 1), (3, "epoch", 1),
    (2, "paddr", 0),
])
def test_corrupted_lifecycle_rejected(index, field, value):
    rows = normal_fixture()
    rows[index][field] = value
    with pytest.raises(ValueError):
        replay(rows)


def test_missing_last_response_is_not_a_pass():
    with pytest.raises(ValueError, match="undrained"):
        replay(normal_fixture()[:2])


def test_ni_constraint_checks_pop_not_wait_state_name():
    rows = normal_fixture()
    rows[0].update(stall_ni=1, stores_empty=0)
    with pytest.raises(ValueError, match="NI request popped"):
        replay(rows)


def test_parser_rejects_unknown_truncated_or_duplicate_fields():
    good = encode(normal_fixture())
    variants = [good.rstrip(), good + "{}\n", good.replace('"cycle": 1', '"cycle": "x"', 1),
                good.replace('"cycle": 1', '"cycle": 1, "cycle": 1', 1),
                good.replace('"phase": "pre"', '"phase": "post"', 1)]
    for bad in variants:
        with pytest.raises(ValueError):
            checker.parse_trace(bad)


def test_complete_marker_alone_cannot_pass():
    config = dict(schema=1, scope="load_bypass_wt_control_boundary_contract", mmu=1, ni=1,
                  load_entries=2, xlen=64, real_mmu=False, real_scoreboard=False, real_cache_array=False)
    result = checker.analyze("LOAD_CONTRACT_END cases=15 transactions=22 cycles=2 checks=99 errors=0\n",
                             encode(normal_fixture()), config)
    assert result["status"] == "FAIL"
    assert "cases" in result["errors"][0]


def test_flush_same_grant_reclaims_without_completing():
    rows = normal_fixture()
    rows[0].update(flush=1, next_state=7)
    rows[1].update(state=7, epoch=1)
    rows[2].update(state=7, epoch=1, kill=1, valid=0, result_seq=0)
    rows[3].update(epoch=1)
    result = replay(rows)
    assert result["counts"]["canceled"] == 1
    assert result["counts"].get("completed", 0) == 0
    rows[2].update(valid=1, result_seq=0)
    with pytest.raises(ValueError, match="orphan/duplicate"):
        replay(rows)


def test_exception_payload_independent_of_testbench_ledger():
    rows = normal_fixture()
    rows[0]["in_expected_cause"] = 5
    rows[2].update(ex_valid=1, ex_cause=5, ex_tval=0x80000100)
    assert replay(rows)["counts"]["exceptions"] == 1
    bad = copy.deepcopy(rows)
    bad[2]["ex_tval"] += 8
    with pytest.raises(ValueError, match="payload"):
        replay(bad)
