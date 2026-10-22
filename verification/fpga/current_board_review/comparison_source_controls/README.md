# FP Comparison Source-Origin Controls

Terminal A/B: candidate03 restart vv/vf each report10 errors; zero-start PASS.
Candidate04 **3/3 PASS with the exact same ELFs and checker**, flags1/start_after0
unchanged. Zero-start complete commit CSV is byte-identical (including cycles).
See [AB_REPORT.md](AB_REPORT.md). No FSDB or image build was performed here.

Three **new directed controls**, not archived originals. No production changes.
Prepared C/S and ELFs are frozen after host/Spike validation. Candidate04 must
reuse `soc01/programs.json` and the same three ELFs; do not rebuild or relabel
candidate03 failures as passes.

| Name | Target | VL / vstart | Purpose |
| --- | --- | --- | --- |
| vv_restart16 | vmfeq.vv v24,v8,v16,v0.t | 32 / 16 | Both source requests incorrectly start at lane word1 |
| vv_start0 | vmfeq.vv v24,v8,v16,v0.t | 32 / 0 | Normal origin0 control |
| vf_restart16 | vmfeq.vf v24,v8,ft0,v0.t | 32 / 16 | Vector source plus boxed scalar 1.0 control |

All use e16/m1, four lanes, VLEN1024, tu/mu, disjoint source/destination
registers, and no software hints. Sixty-four finite source elements are loaded;
values are only FP16 ONE=0x3c00/TWO=0x4000. Full source readback is checked.
Literal golden truth is `0x9e35c692396d58b3` (bit i describes element i).
Bits16..31=0x396d and bits32..47=0xc692 are complementary: every active-region
index i has different truth from i+16. This is not the old alternating or
constant-input matrix pattern. The prefix and final16-element blocks differ
from these blocks. Predicate bits16..31=0xd6ad, retaining active and masked-off
positions. Scalar control uses boxed `0xffffffffffff3c00`.

## Independent Oracle

- The result oracle uses the literal truth table, not observed operands/results.
  A separate scalar equality check validates generated finite input pairs.
- All1024 destination mask bits are read back. Prestart and masked-off body bits
  must equal initialized old vd. Active body bits must equal golden truth.
- Mask tails permit only old/one, additionally the computed comparison result
  within e16/m1 VLMAX64, not an unrestricted tail don't-care. Every predicate
  byte, source element, and surrounding memory guard is checked.
- Immediately before/after the target, VL=32, vtype=8, frm=1 and vcsr=5 are
  checked. Vstart must change from the requested start to0. Fflags must retain
  NX=1 exactly, without introducing NV or any other flag.
- Shared comparison `capture.S`, builder, and integration startup/runtime are
  reused read-only and hashed. The builder's directory named `original/` holds
  generated assembly here and makes **no historical provenance claim**.

## Reference Checkpoints

- `host01/result.json`: 156 positive/negative checks PASS, including three
  shifted16 wrong-result models rejected, every body-bit corruption, CSR,
  source, predicate, guard, and prohibited-tail corruption checks.
- `reference01/reference.json`: all3 Spike PASS with explicit ISA
  `rv64gcv_zvfh_zvl1024b` and the existing nonzero-vstart model probe.
- `prepared01/provenance.json`: generated source and imported dependency pins.
- `soc01/programs.json`: reusable VCS manifest with exact pass markers and ELF
  hashes. `preflight01.json` adds target PC/opcode and candidate03 identity pins.

Preparation attempt01 was rejected by the host compiler for misleading
indentation before any tests executed. `prepared_compile_attempt01/` and
`host_compile_attempt01/` retain that history. Only statement formatting was
corrected; no oracle expectation or input changed.

## Authorized Baseline Replay

`replay.py` uses the existing integration runner against immutable candidate03,
jobs1,180 seconds/case, independent service outer900 seconds. It performs one
admission inventory under cap24, reserves any unoccupied NF7 slots up to2,
and requires32GiB MemAvailable. It never builds an image, retries admission,
or modifies external tasks. Each case has a separate runner invocation, so an
expected baseline failure cannot cancel the zero-start control or third case.

Pass acceptance requires complete runner status, process success, exact marker
counts, firmware success, input/image identities, and a raw failure-marker veto.
The final `COMPLETE_3_BASELINE_OBSERVATIONS` label means collection finished,
not that the DUT passed. Read each result and `all_pass`.
