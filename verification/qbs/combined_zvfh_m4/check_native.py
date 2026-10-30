"""Strict combined production-selector evidence. No build or guest execution.

Input is the merged, ordered stdout/stderr stream from two separate processes,
enclosed by the parent's MODE_BEGIN/MODE_END and GUEST_EXIT records.
"""
import argparse
import json
from pathlib import Path
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


SEEDS = (0, 1, 2, 4, 8, 16, 31, 0)
EXACT = ("packedbytes=exact scales=exact bsums=exact input=exact canaries=exact")
FAILURE = re.compile(
    r"Q8K_COMBINED_FAIL|Q8K_M4_FAIL|Kernel panic|Illegal instruction|"
    r"Assertion .*failed|Segmentation fault|qemu: fatal|AddressSanitizer|"
    r"runtime error:|terminate called", re.I)


def check_output(text):
    """Reject missing/extra/reordered calls, unattributed traces and OFF/ON drift."""
    if FAILURE.search(text):
        raise ValueError("Guest failure")
    records = [line.strip() for line in text.splitlines()
               if "Q8K_COMBINED" in line or
               ("GGML_RISCV_QBS" in line and "M4_PREPARE" in line)]
    cursor = 0

    def take(pattern):
        nonlocal cursor
        if cursor == len(records):
            raise ValueError("Truncated evidence")
        line = records[cursor]
        cursor += 1
        match = re.fullmatch(pattern, line)
        if match is None:
            raise ValueError(f"Unexpected record {cursor}: {line}")
        return match.groups()

    def exact(line):
        take(re.escape(line))

    paired = []
    summaries = []
    vlens = []
    for mode in (0, 1):
        exact(f"Q8K_COMBINED_MODE_BEGIN mode={mode}")
        vlen, = take(rf"Q8K_COMBINED_BEGIN mode={mode} vlen=(128|1024) cases=50")
        vlens.append(int(vlen))
        evidence = []
        vector = 0
        for index, (name, k, eligible) in enumerate(CASES):
            input_digests = set()
            for frm in range(5):
                for env, seed in enumerate(SEEDS):
                    exact(f"Q8K_COMBINED_CALL id={index} name={name} k={k} "
                          f"eligible={int(eligible)} frm={frm} env={env} seed={seed}")
                    used = bool(mode and eligible and k and frm == 0)
                    path = "rvv" if used else "generic"
                    exact(f"GGML_RISCV_QBS_Q8K_M4_PREPARE enabled={mode} path={path} k={k}")
                    vector += used
                    signedmax = int(frm == 0 and name.startswith("first_max_"))
                    fma = int(frm == 0 and name == "fma_rounding")
                    underflow = int(frm == 0 and name == "fused_underflow")
                    prefix = re.escape(f"Q8K_COMBINED_CALL_PASS id={index} frm={frm} env={env} ")
                    suffix = re.escape(f" {EXACT} signedmax={signedmax} fma={fma} underflow={underflow} ")
                    ef, af, ev, av, input_hash, output_hash = take(
                        prefix + r"ef=(\d+) af=(\d+) ev=(\d+) av=(\d+)" + suffix +
                        r"input_digest=([0-9a-f]{16}) digest=([0-9a-f]{16})")
                    ef, af, ev, av = map(int, (ef, af, ev, av))
                    if ef != af or af >> 5 != frm or af & seed != seed:
                        raise ValueError(f"FCSR mismatch: {name}/{frm}/{env}")
                    if ev != env or av != env:
                        raise ValueError(f"VCSR mismatch: {name}/{frm}/{env}")
                    if underflow and af & 2 != seed & 2:
                        raise ValueError("Fused underflow witness raised UF")
                    input_digests.add(input_hash)
                    evidence.append((input_hash, output_hash, ef, ev))
            if len(input_digests) != 1:
                raise ValueError(f"Input changed between calls: {name}")
        exact(f"Q8K_COMBINED_PASS mode={mode} cases=50 checks=2000")
        exact(f"Q8K_COMBINED_MODE_END mode={mode} exit=0")
        expected_vector = 312 if mode else 0
        if vector != expected_vector:
            raise ValueError("Internal case inventory drift")
        summaries.append(dict(mode=mode, cases=50, checks=2000, vector=vector,
                              fallback=2000-vector))
        paired.append(evidence)
    exact("Q8K_COMBINED_GUEST_EXIT=0")
    if cursor != len(records):
        raise ValueError("Extra protocol or trace")
    if vlens[0] != vlens[1]:
        raise ValueError("OFF/ON VLEN mismatch")
    if paired[0] != paired[1]:
        raise ValueError("OFF/ON input/output digest or CSR mismatch")
    return dict(state="PASS", vlen=vlens[0], cases=50, real_cases=6,
                checks=4000, modes=summaries, paired_digests="exact")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    try:
        result = check_output(args.log.read_text())
    except (OSError, ValueError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
