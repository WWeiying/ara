# Full6720 Reference Core Review

**NO_BLOCKER_REFERENCE_ENTRY** for exact sibling full6720_e16_mf4_reference01.
Parent has already authorized the sole reference after this core check; Tesla
may execute that entry without another approval layer. This is not reference
PASS or DUT permission. No execution was started by this reviewer.

- ENTRY SHA: `0c7febdeffdb16f3d71cbd633105a7598a41b211046fe1518248439e3ccf17f7`.
- Pins SHA: `efdab8d004f3ca7bae8d2eecbb484fa874497ddf092414361a39197bf676dac6`.
- Checker SHA: `d03da9efd7395d44ff3056de19440c316630568417f085a2337b09559d98042c`.
- Exact Spike ELF: `0326cc068509dd6a42a8840426de99fd251dcefe04e552bda5135c36040c7d1e`.

## Core Findings

Read original parent.c/input formulas, current checker and short tests, actual
linked instruction excerpts and executor. No numerical Host, compile, CFG,
reference or raw replay was repeated. The177-pin manifest is bound; current
entry/checker/transport/audit/test receipts and four imported modules match.
This limited review did not independently rehash all177 inputs; executor
requires all of them unchanged before reference and again after reference/audit.

Original enumeration is preserved:8 scenarios,7 lengths,4 masks,5 rounding
modes,3 operations,2 sticky values,6720 contiguous calls. original_call uses
row=n//2, bank1 fixture index3360+row, exactly matching original C at VLEN1024.
Input/seed formulas match the original header. Freshness is scenario-only16 SH
input/16 SD seed, row-only8 SD mask, call-only18 SD output, not invented per-call
input refresh. Original1024B input backing,128B seed,64B mask and144B output
are checked before helpers. All output18 LD comparisons retain128B destination
and both8B guards. VL0 keeps all144B old; other calls replace only bytes8..9
with original wanted.bits. Flags/sticky and returned vstart remain exact.

Actual fixture LD at0x8000033e and LW at0x80000340 must read correct bank1
address, field order, width and value; both source and initialized ELF memory
are checked. Row1545 bank1 is0x7e00/NV16, not bank0's0x7c00/0. No generated
replacement floating-point oracle is used. All6720 fixture-field reads are
required, reused across the two original sticky calls.

Helpers at0x8000066c/06bc/070c retain21 instructions each, plus capacity3 at
0x80000664. Exact PC/code and contiguous step/op checks prevent skipped or
uninvoked helper interiors. Source uses e16/mf4 CAP16/vtype14, while seed/
destination load/store deliberately use e16/m1 VL64/vtype8. Full128B actual
vector result and store are checked, including tail and VL0. All6720 flags/
vstarts and flags_seen21 are mandatory; frm/fflags save, requested rounding/
sticky, packed status and restoration are checked. No scalar FPR is admitted.

Actual prologues justify opaque initial s-register spills only: source
0x800000e4..fa lies within the declared32B prefix; wrapper s0 at0x80000768 is
also within its prefix. Other unknown store sources fail. Runtime effective
addresses/initialized scalar loads and actual branch/jalr/return flow are
checked. The only jr is the actual input switch at0x800001f2; helper dispatch
uses jalr t2 at0x80000416, compatible with inherited control-flow decoding.

## Receipts and Execution Boundary

Stored19 short tests actual wait0,2.0716013368219137s,no timeout; log reports
19 PASS/1.851s and its hash matches. Tests include bank, NV, wrongNaN, vstart,
helper deletion/op mutation, upper seed/input backing, freshness, short128B
store, final oracle tail, restoration, missing EOF and wrong encoding. These
are local checker witnesses, not full reference execution or hardware evidence.

Exact bound remains rs2000000;quit,120s reference,512MiB raw,600s one closed
audit. Numeric wait receipts precede outcome checks. Outputs are exclusive,
failure records retained, no retry/recompile/VCS command. HTIF requires actual
0x8000007a SD value1 after complete6720 oracle and exact console; all later
rows through EOF must be original0x8000007e/a001 pure park without side effects.
Full totals require141120 operation-helper instructions plus capacity3,
967680 byte comparisons and all source event counts. Budget/partial EOF is not
PASS. Independent full-source/DUT acceptance remains a later terminal stage.
