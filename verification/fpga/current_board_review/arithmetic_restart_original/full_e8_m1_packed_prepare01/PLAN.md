# e8/m1 Full4095 Software Preparation

Owned successor only; no DUT authorization. Source review precedes Host/compile,
and exact artifact/reference-entry review precedes the single reference.

## Original Source

Archived rvv_extended04/rvv_matrix_e8_m1.S:
7d2c0d69f8390a795d884d95eb43b85dc8c405b5dc9b227925da22a218ae7cce.
Archived/recovery22 Linux ELF:
199a69e4394959e73f0b7458359c06f0e39a09f4c621028eb356723684dd1f9a.
recovery22/reconstructed_oracle.c:
7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91.
Reconstruction is binary-equivalent, not original C bytes or a Linux replay.
No accepted full e8/m1 execution found in family directories/full22 inventory.

Original capacity helper e8,m1 at VLENB128 gives CAP128 and one full physical
register. Preserve original25 operations and26 helper routines. Three seeds,
seven lengths 0/1/2/3/64/127/128, three masks and original kinds/starts yield
4095 calls,524160 uint8 results,8190 guards,4095 returned-vstart checks and
53235 helper instructions. Recompute all128 RNG elements per seed using the
original recurrence/special values; do not reuse CAP64 inputs. Gather indices
are uint8:255 is out-of-range at CAP128, indices below128 are in range.
Original mask128 is fully initialized; first16 bytes encode128 predicates and
upper112 bytes are zero. Original vlm reads16 bytes, not128.

## Narrow Packed Adaptation

Full original a/b[1024], out[1026], mask[128] remain. Successful comparison and
initialization cover130 bytes only:16 memcpy uint64 accesses plus one memcpy
uint16 tail. Front guard is in first word; tail2 contains result127/rear guard.
No rounded-up output access. Original per-byte failure fallback, original
call history/order, seed updates, helper assembly and returned CSR stay intact.
Flat expected_words[4095][17] is556920 bytes; masks384, no dictionary.
Padding of final ROM word is representation only. Physical image1MiB reserves
64KiB stack; actual ELF section bounds and stack frame must prove capacity.

Reuse full_e8_mf2_packed_prepare01 source harness idiom, with independently
CAP128-generated rows and exact Host comparison against reconstructed original C.
Host20 receipts: original/packed full4095 positives, active/prestart/inactive/
tail/frontguard/rearguard/vstart/final-result mutations, plus UBSan shift64
negative; protected-page and unaligned memcpy boundary probes. Original C
uint8 promotions are bounded; original uint64 shifts/products and guarded
division retained. memcpy avoids alias/alignment UB, word shifts remain0..56.
Compile same RISC-V GCC with both vectorizers disabled, confirm all original
helper bytes and no extra vector instructions. No blind flag variants.

## Reference And Future Owner Contract

Reference only after independent final entry: one finite rs4000000+quit,
120 seconds,768MiB raw ceiling, complete fullscope firmware <=3000000 gate.
Continue through real post-HTIF park to EOF; no early-success raw truncation.
No automatic retry/limit expansion, no DUT. Actual cost is unknown before run.
Static conservative projection below2M is a preparation hypothesis, not a result.

Future backend owner eligibility must decode exact VSLIDEUP.VI offset2:
VL1/2 legitimately has no Ara target request. All output/guard/vstart/CSR
checks remain mandatory, no blanket slide waiver. VL3 op19, op20 slide-down,
all five full-capacity memory helpers and nonempty op24 remain required.
This preparation does not edit any active worker/checker or parse active CSV.
