# Corrected Generic Checker: Static Follow-Up

Decision: **no remaining concrete blocker found in the reviewed correction**.
This supplements, rather than overwrites, CODE_REVIEW01's two initial refusals.
It is static preparation review, not nine-reference acceptance or DUT approval.
No Host/Spike/DUT/compile was run by this reviewer; preflight results below are
existing executor evidence read and checked against their test implementation.

## Exact Revision

| File in original_remaining9_prepare01 | SHA-256 |
| --- | --- |
| check_reference.py | 3379658485e42e616eaea432df67d43d1ed21729edaed63cfd6c2abacfa9bd8e |
| reference.py | ea5ce182b5acac380c055b26b58e4c22cf372875949cd11322d75a7ad50cb923 |
| test_host.py | 952adbc27695ebe05a6efc2c97e0a2892ee88b18d39c6dbb50859f3a20aa5229 |
| checker_host_preflight03.json | 20c4e375d3909de4f0275cca9303c7ae9683f714eadb15ff5f8eed2acecf920e |
| README.md | 77f94c45778da442ddc3d8427e4a39c62ec954e3094bc9cd2be31138bfa7daed |
| static_admission.json | c23f6b29d700ab48adc134eb4d8561445716e86e93233e221b69149c2fe1ebdc |

Source/ELF geometry and cost findings remain those of CODE_REVIEW01 and the
525-pin prepared_inspection01.json. Static-admission identity is unchanged.

## Closed Findings

1. Boot handling now requires exactly five known PCs/encodings and exact integer
   register/memory effects, with no CSR/vector write effects, before firmware.
   The known mhartid read is admitted only at its boot position. Subsequent
   return to boot is rejected. Firmware's extra-CSR rejection remains unchanged.
   This closes the prior unconditional false rejection at PC0x1008.
2. Extraction now retains actual capacity CSR/register effects. Validation
   requires capacity vtype, VL and vstart to match the requested shape, then
   starts helper vtype tracking from that observed vtype. Unchanged helper
   vsets legitimately omit a CSR write; missing/wrong capacity state is rejected.
   This closes e16/m1's false rejection without substituting an expected value.

The positive synthetic ledger in test_host.py removes each redundant vtype
write relative to actual predecessor type, including the first helper vset for
e16/m1. Negative witnesses explicitly remove or corrupt capacity vtype. The
raw-PC negative tests now prepend a valid boot, so their expected failure must
reach the intended firmware-PC gate rather than the original unrelated boot bug.

Preflight03 has exact nine-shape membership and, per shape, one positive plus
19 ledger negatives,62 forbidden/interior helper-PC negatives and3 boot
negatives (wrong CSR, wrong hart, repeated boot). Count totals are180 ledger
checks,558 PC negatives,27 boot negatives. The existing9*13 native Host results
remain additional evidence, not actual vector executions. Host mode `bank0`
continues to mean a missing-NV mutation, as now disclosed; actual wrong-bank
coverage is the raw address mutation even when numerical fixtures coincide.

## Execution Boundary

The reviewed worker reads preflight03, admits only after static cost, snapshots
source/helper/ELF evidence, checks pins before execution, and writes an exclusive
per-case attempt sentinel. It uses actual Zfh+Zvfh profile,3M/256MiB/120s, no
retry, sequential dispatch and stop-on-first-error. It validates complete raw,
the static bound, post-run pins and host witness rejection before READY.

Tesla clarified the parent's batch2 wording as at most two concurrent references,
not a first-two-only authorization. Under that reading, jobs1 satisfies the
limit. The worker still dispatches all nine sequentially: it does NOT provide
a two-case review pause, and this supplement must not be read as asserting one.

No new reference result was queried or accepted in this review. Final reference
acceptance still requires each sealed READY, full raw, actual firmware count,
full setup/helper/oracle/CSR/exit and stable pins. Static cost plausibility does
not guarantee the independent wall/file limits or waive any checker failure.
