# e8/mf2 Full Original4095: Software-Only Preparation

Status: source review in progress; no Host/compile/reference/DUT yet.

Owned path: `arithmetic_restart_original/full_e8_mf2_packed_prepare01/`.
Independent reviewer: Averroes. Predecessors remain unchanged.

## Source Contract

Original `rvv_extended04/rvv_matrix_e8_mf2.S`, `e8/operations.h`, and
archived Linux ELF bind the source-derived port. Reconstructed C is not
verbatim recovered C: recovery22 proves byte-equivalent Linux rebuilding.
Original helpers, including capacity, must match archived machine bytes.
VLENB128/e8/mf2 implies CAP64; fractional groups still occupy one physical
register. Do not join half a register or require multiple register outputs.

The original loops give 3 seeds * 7 VLs * 3 masks * (20 ordinary ops *
3 starts + 5 special ops * 1 start) =4095 calls, including duplicate starts.
VLs are 0,1,2,3,32,63,64. Results:4095*64=262080 typed uint8 values;
guards:4095*2=8190; returned vstart checks:4095. All original 25 helpers
execute in original order, each with13 instructions. Physical mask128 is
initialized completely:8 meaningful bytes and120 zero bytes. The original
vlm at capacity64 reads8 bytes, not128; upper120 bytes remain software-buffer
coverage, not a claim that the full physical v0 was loaded.

## Minimal Scalar Adaptation

Reuse accepted packed-scalar memcpy idiom, without dictionary indirection.
Per-call ROM row holds8 uint64 words and the final2 bytes in a padded ninth
ROM word. ROM padding is representation only. Actual output initialization
and inspection cover exactly66 bytes:8 SD/LD plus SH/LHU. Tail2 comprises
result element63 and the rear guard; the front guard is in the first LD.
Destination is
still `out+1`; output backing array remains1026 bytes, a/b remain1024 bytes.
Original RNG code runs anew for each seed and exactly64 elements. Do not
reuse CAP32/CAP1024 generated input. Preserve full128-byte mask values.
Only initialization, mask scalar copy, and successful output comparison
are adapted; original C per-byte failure fallback is retained verbatim.
No algorithm, loop sequence, helper assembly, or target instruction change.

Flat expected ROM4095*9*8=294840 bytes, masks384 bytes; no index table.
Original buffers total3202 bytes plus counters/runtime. Reserve64KiB stack
inside1MiB image; actual link map and compiler stack frames must confirm.
Memcpy avoids alias/alignment UB; only shifts0..56 in word construction.
No automatic vectorization; every vector instruction must be within original
capacity/op helper windows. Only actual compiled code can establish cost.

## Gates

1. Source/helper/CAP/fractional/tail/physical-mask review before Host/compile.
2. Host original vs packed all4095 in exact order and byte-for-byte errors;
   active/prestart/inactive/tail/both guards/returned-vstart negatives;
   unaligned memcpy and protected-page exact66-byte boundary checks.
3. Actual SoC/Spike compilation, original helper bytes, no additional RVV,
   image/stack bounds and scalar instruction cost inspection.
4. Independent final review before one bounded full Spike reference.
   No reference is run by preparation; no DUT authorization exists.

No current accepted full e8/mf2 result was found in arithmetic scope and
terminal inventory searches. Prefix or another shape is not this scope.
