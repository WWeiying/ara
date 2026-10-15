# Exact Bounded Reference Entry Review

Decision: **NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT**.
The decision binds entry02.json SHA
`a19f81642a1932e1a7475bec6462c111f97255878ca337b947dde9337b673917` in
full_e8_mf2_packed_prepare01. Aquinas owns execution under the parent's existing
authorization. This reviewer did not launch Host/compile/Spike/DUT. All original
and successor inputs remain unchanged. No large historical trace was reread.

## Actual Evidence

- ACTUAL_ARTIFACTS.md and artifact_result.json establish the accepted Host/
  compilation scope.129 preparation pins,20 stored Host receipts, both compiled
  ELFs, every original helper byte, actual scalar tail2 width and whole4095 ROM
  ordering were independently verified, not merely copied from proof.json.
- A second read-only identity command actually exited0 (session2129,
  completion09787b): all150 entry02 pins match; original lifecycle12 and new
  boundary7 receipts each record strict integer returncode0, timeoutfalse,
  attempts1. These tests were not rerun. reference01 did not exist at this gate.
- Retained draft entry.json and reference_check.py had an HTIF early-return gap.
  They remain unchanged and unapproved for reference execution. Only successor
  reference02.py/reference_check02.py/raw_boundary02.py is cleared here.

## Checker Contract

The full parser derives the original4095 tuples using CAP64, not current VL
as a source-selection limit. Gather/slidedown agree with original C and helper
source setup: valid source elements beyond VL but below64 remain readable;
source indices>=64 return0. This is not an expansion to physical128-byte data.

Each actual helper instruction must match code and its ordered position in the
expected operation, with exact a0..a6 parameters. Capacity is exactly once;
all13 positions appear4095 times. All compiled RVV sites are in those original
helper/capacity windows, which the parser owns. No detached extra helper or
interior instruction can be absorbed as scalar activity.

fractional_group takes the low64 bytes of exactly one1024-bit physical v8/v16/
v24, not eight registers or a whole128-byte expected result. Actual full-capacity
setup inputs and old-vd, target predicate low64 bits, target VL/vtype7/vstart,
target result, returned vstart0 and final64-element vector store are checked.
Original upper-half physical-register contents are not invented or constrained.

Lifecycle binds exact compiled Spike PC/code and ordering for BSS,552 RNG/input
stores,1575 complete128-byte software mask setups, and9 fresh output stores
per call. It rejects missing stores even if old bytes would match. Output reads
are owned by exact PC/address/width/order: eight LD plus one LHU,36855 total.
The two-byte tail is result63 plus rear guard; front guard remains in first LD.
Missing/deleted calls, stale seed/mask ownership, over-wide tails and output
backing overruns are not accepted by aggregate counts alone.

Success requires software return0, actual HTIF store1 at8000007a/00a2b023,
the exact original console marker, complete full oracle and all lifecycle
counts. After success the parser continues to EOF and accepts only
8000007e/a001 with an empty side-effect field. Other PCs, changed park encoding,
GPR/memory/vector/CSR side effects, boot reentry and missing completion fail.
The actual reset-ROM contract is five instructions1000..1010, not six;
firmware must begin at80000000. Parser end-of-file is necessary for acceptance.
This closes the identified early-return gap without changing the data oracle.

## Driver And Boundaries

reference02.py requires this exact independent review hash and exact entry02
hash/status before creating fresh reference01. Directory creation is exclusive;
there is no auto-retry. All pinned inputs are checked before execution and after
execution/parsing. Original pins and old pending entry are retained.

The sole command file is finite `rs 4000000` followed by `quit`. Total execution
ceiling4000000 includes boot and any parking; accepted firmware-to-HTIF cost
must separately be<=3000000. Limits are120s execution,768MiB file size,600s
offline audit. A fully correct but >3M firmware result becomes HOLD, not READY.
No larger timeout, reduced oracle or retry follows from this review.

Actual Spike child wait is persisted before parsing; the separate parser child
gets its own numeric wait receipt. Traps, bad completion, mismatches, timeout,
nonzero exit or pin drift preserve failure and prevent READY. The offline parser
performs one semantic traversal; surrounding hashes are integrity checks, not a
second semantic replay. No firmware instruction cost has yet been measured.
The compiler-based1.2M envelope is an estimate, not a reference/DUT observation.

| Bound module | SHA256 |
| --- | --- |
| reference02.py | 1267665ec498b6a64d5821e76f7bae021def007950c92add5cb5ed423513224d |
| reference_check02.py | 5b335a937cb0ab4cda37fb9fe487e1a1507ad89b61b93ba7f679d54fd241436f |
| raw_boundary02.py | 3453a6a13589df7accc7679d81e9be11c09575c95ecd114c40e54614ef4a7260 |
| lifecycle.py | 7299b116b148dcc167cc699838fcb7d82c7e6f14122349688cef6057a2df07fd |
| lifecycle12 receipt | 33828230dca3bc0a2a6620f4f0c40ca8339ccb797d6d55c2a47952aec39d9824 |
| boundary7 receipt | c83a914dc1cfc30483fe8ca2fb34031c521d10f2853cb8c90b5a8a2482bf10e3 |

The machine-consumable verdict is reference_entry02.json. It authorizes no new
DUT run and claims neither a completed reference nor arithmetic22/Linux closure.
