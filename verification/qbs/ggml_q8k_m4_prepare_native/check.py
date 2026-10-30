"""Exact per-case coverage; no guest PASS-only or performance acceptance."""
import re

CASES = [(name, blocks*256, eligible) for name, blocks, eligible in [
    ("zero",1,True), ("negative_zero",1,True), ("mixed_zero",1,True),
    ("first_max_pos",1,True), ("first_max_neg",1,True), ("first_max_boundary",1,True),
    ("ties_even",1,True), ("fma_rounding",1,True), ("fused_underflow",1,True),
    ("bsums_boundary",2,True), ("bsums_extrema",1,True),
    *[(f"blocks_{b}",b,True) for b in (2,4,5,6,17,28,32,33,35,65)],
    ("low_below",1,False), ("low_equal",1,True), ("low_above",1,True),
    ("high_below",1,True), ("high_equal",1,True), ("high_above",1,False),
    ("tiny_normal",1,False), ("max_finite",1,False),
    *[(f"late_exception_{i}",2,False) for i in range(6)], ("empty",0,False),
    *[(f"finite_{i}",1+i%3,True) for i in range(8)],
    ("real_attn_first",6,True), ("real_attn_last",6,True),
    ("real_gate_first",6,True), ("real_gate_last",6,True),
    ("real_down_first",35,True), ("real_down_last",35,True)]]


def check_output(text, vlen):
    if vlen not in (128, 1024) or re.search(
            r"Q8K_M4_FAIL|Kernel panic|Illegal instruction|Assertion .*failed|Segmentation fault|qemu: fatal", text, re.I):
        raise ValueError("Guest failure")
    records = [line.strip() for line in text.splitlines() if "Q8K_M4_" in line]
    if len(records) != len(CASES) + 3 or records[0] != f"Q8K_M4_BEGIN vlen={vlen} cases=50":
        raise ValueError("Missing/extra protocol or wrong VLEN")
    digests = []
    for index, (name, k, eligible) in enumerate(CASES):
        vector = 24 if eligible and k else 0
        prefix = (f"Q8K_M4_CASE_PASS id={index} name={name} k={k} eligible={int(eligible)} "
                  f"checks=120 vector={vector} fallback={120-vector} digest=")
        if not re.fullmatch(re.escape(prefix) + r"[0-9a-f]{16}", records[index+1]):
            raise ValueError(f"Wrong/missing case evidence: {name}")
        digests.append(records[index+1].split("digest=")[1])
    if records[-2:] != ["Q8K_M4_PASS cases=50 checks=6000 vector=936 fallback=5064 bytes=exact "
                         "bsums=exact fcsr=exact vcsr=exact guards=exact", "Q8K_M4_GUEST_EXIT=0"]:
        raise ValueError("Incomplete suite/guest exit")
    return dict(state="PASS", cases=50, checks=6000, vector=936, fallback=5064,
                real_cases=6, vlen=vlen, digests=digests)
