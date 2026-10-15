# Conditional Packed Scalar Design

DESIGN ONLY. Not implemented, compiled, Host-tested, referenced or admitted.
Use only if the completed sole-O2 cost assessment is HOLD. Do not alter the
original C/ELFs, current reference, helpers or sealed audit. This is a future
equivalent software conversion, NOT original C or ELF byte identity.

The companion static design is
`../continuous_o2_static_review01/PACKING_PROPOSAL.md`, SHA256
`56f22f569164be74c0b783a638bc7014c52f2f67e482000399ad0babac3e2813`.

## Exact Scope

Retain seed/op/mode/start nesting, 1134 calls and 366 exclusions, all 20 helper
machine-code windows, original arguments and vtype/VRF predecessor history.
Every call initializes all 1024 input and 1088 output bytes, checks returned
vstart/status, and judges all 1088 output bytes, including guards and inactive
bytes. No RVV initialization/checking, sampled oracle, signatures, reset
partitions, shortened history or new Linux ABI claim.

## One Scalar Conversion

The aligned byte arrays remain byte arrays. Represent the original input
formula with a 3-seed by 256-byte immutable table (768 bytes), independently
proved against `(i*37+seed*71+3)&255` for every original input position. On
EVERY call, copy its four periods with 128 scalar eight-byte stores, then write
136 sentinel words. No cached initialization or omitted unchanged stores.

Use fixed-size `__builtin_memcpy` between byte-array storage and local uint64_t
objects; it is legal byte copying, not a uint64_t-pointer alias cast. With the
existing `-fno-builtin`, inspect actual generated code rather than assuming
ordinary memcpy inlines. Reject library/byte-loop expansion or extra RVV before
reference. Explicit aligned scalar ld/sd with memory clobbers is an alternative
only if this one selected lowering requires it, not a blind flag search.

Check all 136 output words in ascending byte order. Each expected word combines
current input bytes and sentinel bytes using the original active interval
`[32 + start*bytes, 32 + n*vlenb)`. Guard words never form out-of-bounds input
pointers. Partial boundary masks select whole bytes; full/empty masks are
handled separately to avoid shifts by 64. Little-endian byte mapping is explicit.

Equality of eight bytes is proved by equality of their 64-bit packed word.
On a mismatch, run the original byte check for those eight positions in order,
using the original status-inclusive error count and `errors<12` diagnostic
condition. Continue all subsequent words/calls. This preserves exact count,
ordered byte diagnostics, per-mode error deltas and final exit without counting
one error per word. Expected bytes still derive from CURRENT post-helper input,
as in the original C, not merely from a precomputed expected-output table.

## Required Finite Proof Before Any New Reference

Host compares original and transformed initial arrays, all expected bytes and
full ordered scope for all 1134 calls. Test each output-byte corruption,
cross-word multi-errors, first/last guards, partial boundaries, empty active
interval, status errors and the 11/12/13 diagnostic threshold. Compare exact
errors and ordered diagnostics, not only a PASS boolean. Run appropriate UB
instrumentation; verify actual helper bytes and no new vector instructions.

The future observer must require per-call FRESH store coverage of all
1024+1088 initialization bytes and full output read coverage. The current
reference's scalar-memory shadow validates setup values but does not separately
prove that every equal-valued initialization store was newly retired each call.
Do not mislabel that existing evidence; add fresh coverage to a future observer
and reject deletion of an entire repeated initialization interval.

## Cost Boundary

Original byte-level setup/check work is 3,628,800 positions across 1134 calls.
Packing offers 299,376 setup word stores plus 154,224 output word checks
(453,600 word-level operations), but adds table/input loads, masks, loop/control
and retains every vector helper. This is NOT an eightfold runtime claim.

Historical whole-partition rates were about 644.45 to 784.10 retired/s; they are
proxies, not a current continuous-image measurement. At the slower proxy,
`firmware / 644.4508024094405 * 1.20 + 300 <= 10800` allows at most about
5,638,944 firmware instructions. The 300 seconds is an explicit planning
allowance, not a measured validation duration. Actual scalar lowering and one
separately authorized complete reference must establish cost before DUT
admission. No timeout extension or partition parallelism may manufacture a
continuous under-three-hour result.
