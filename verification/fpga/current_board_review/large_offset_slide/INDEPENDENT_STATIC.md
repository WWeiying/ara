# Independent Large-Offset Slide Static Review

2026-10-10. Read-only source/evidence review; this report is the only new file
for this task. No RTL, prepared program, frozen image, capture script or existing
report was changed. No simulation, build, converter or duplicate capture was run.
The parent owns `capture_current.py` and the 103200..104000ns capture.

## Measured Scope and Identity

Read `/home/wangwy/fpga_runs/current_board_integration_final03/large-offset/summary.json`
and `tests/e8_m8_single/console.log`. The batch has two PASS, one FAIL and three
CANCELLED, not six completed measurements:

- e8/m4 single and four-mask sequence: PASS, VL512/offset511.
- e8/m8 single: FAIL, op12/seed0/VL1024/offset1023/mask-mode0; element1023
  expected185 (0xb9), actual91 (0x5b). It reaches the oracle and tohost3, not timeout.
- e8/m8 sequence and both e16/m8 programs: CANCELLED; no correctness conclusion.

The prepared SoC ELF, failed run's input ELF and `capture01/input.elf` independently
hash to `a6e3f2faf535389b59b2520daab8af86f1caa842aeb8171d2451bab10d760364`.
`capture01/command.json` identifies final03's existing simv and image-ledger SHA256
`75f0823f427c232bb01d46fcebbb3c6d95abd2d199d8dbfe29ef93084e750c55`.

`prepared01/reference02/results.json` records six Spike reference passes with
`rv64gcv_zvfh_zvl1024b`. Those commands use **Spike-build ELFs**, not the identical
SoC ELF: source-oracle agreement is established by that record, binary identity
between reference and SoC execution is not claimed here.

The saved original is
`prepared01/prepared/e8_m8_single/original/`, from handoff03's small-slide source.
Its `case.json` identifies the exact original trial and historical identical
wrong value; it does not establish that historical and current internal causes
are the same. Saved source hashes in that record:

| Source | SHA256 from case record |
|---|---|
| scenario.c | fcf8c797f385aa5823bbd0343eb2fd488797b18b83ecdc0cbc88b813b48f20c6 |
| operations.S | 95e7e30ad58da051784588418eac35aa950d98b030c4f38dfe878a7fe31140a2 |
| operations.h | 42344524d126e6e679db6e2f92aa70b8434c0e7599f6861b36deebfb2c46ff85 |

Read `scenario.c:30`, `:42`, `:53`, `:62` and `:65`: mask mode0 selects every
element; input is the original xorshift stream; old output is 0x5b; the sole
eligible destination is element1023, taking input[0]. The oracle still checks
all other elements and both guards. `operations.S` op12 loads v8, v16, v24 and
v0, executes `vslideup.vx v24,v8,t3,v0.t`, reads vstart, then performs an unmasked
full-length `vse8.v v24,(a2)`. The output pointer is `output+1`.

Original failing run's scalar trace identifies PC0x800006c6/opcode0x388e4c57.
Its CSV field is **cycle**, not ns: target retire cycle103383, vstart read at
PC0x800006ca cycle103686 returning0, final store PC0x800006d2 cycle109846.
The README's ns labels include a time-origin conversion; do not reinterpret
these CSV counts as backend acceptance or physical writeback timestamps.

## Frozen RTL Basis

These current files were independently hashed against
`/home/wangwy/fpga_runs/current_board_integration_final03/frozen/sources/` and
are byte-identical. Line references below apply to both copies.

| File under hardware/src | SHA256 |
|---|---|
| sldu/sldu.sv | 1908da4368316c0979e388e934cf04dacf2d266297b36d35b1a803222d2a311e |
| lane/lane_sequencer.sv | 60137df7264ccd09b2a9a1548d2e522c4785bd43c26a06a27024a0c8eb114da0 |
| lane/operand_requester.sv | 327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2 |
| masku/masku.sv | 1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d |

Use final03 for measured behavior. A concurrently edited current dispatcher
extension fix is not present in this sealed image and is unrelated to the
static slide arithmetic below. Configuration recorded by prepared provenance
is VLEN1024/NrLanes4: 32 data bytes or 256 packed predicate bits per aggregate.

## Exact Expected Geometry

The following are source-derived expectations, **not decoded waveform values**.

| Field | e8/m4 PASS control | e8/m8 failing case |
|---|---|---|
| Architectural VL / stride | 512 / 511 | 1024 / 1023 |
| Source request SlideAddrGenA.vstart / vl per lane | 0 / 1 | 0 / 1 |
| MaskM.vstart / vl / EEW | 1 / 1 / EW64 | 3 / 1 / EW64 |
| Mask aggregate's first architectural bit | 256 | 768 |
| MASKU trimmed_stride | 255 | 255 |
| MASKU initial mask_pnt / read_cnt | 224 / 32 | 224 / 32 |
| Emitted predicate slice first element | 480 | 992 |
| SLDU byte stride / residual | 511 / 31 | 1023 / 31 |
| SLDU initial output_limit / issue_cnt / commit_cnt | 512 / 1 / 1 | 1024 / 1 / 1 |
| SLDU vrf_pnt / out_pnt / in_pnt | 15 / 31 / 0 | 31 / 31 / 0 |
| Destination per-lane word address, v24 base96 | 111 | 127 |
| Sole enabled physical destination byte | lane3 byte7 | lane3 byte7 |

Derivation and contracts:

- `lane_sequencer.sv:852` requests `(VL-stride+NrLanes-1)/NrLanes` source
  elements per lane. Every lane supplies one raw word even though only source
  element0 is ultimately written. Do not treat three lanes as absent operands.
- `lane_sequencer.sv:906` makes MaskM EEW64/is_slide1; `:924` requests the
  packed-word origin `stride/256` and ceil((VL-floor(stride/256)*256)/256)
  beats. `operand_requester.sv:420` converts this vstart into a lane-word address;
  eew=EW64 means no further shift. It is **not** a data-element offset of1023.
  With scale_vl=0, request vl1 means one EW64 word, not an endpoint minus vstart3.
- `masku.sv:1772` trims stride modulo256; `:1824` rounds the remaining position
  to 32 destination elements. `:1160` maps packed bits224..255 from that aggregate
  into a 32-byte predicate slice. For all-one input this must be 0xffffffff.
  `:1206` records first-element VL-read_cnt=992; read_cnt is32, not1.
- `sldu.sv:630` initializes residual/output position; `:737` enables only local
  sequential byte31 since current_output_end=32. `:744` shuffles BE, `:748`
  ANDs it with mask_q. EW8 byte31 maps to physical byte31, lane3 byte7, through
  `ara_pkg.sv:456`'s shuffle table. Correct final BE is lane3=0x80, others0.
- `ara_pkg.sv:1013` gives vaddr(v24)=24*4=96. The final target is therefore
  lane3/address127/wdata[63:56]=0xb9. Non-enabled wdata bytes are don't-care;
  neither req=1 alone nor a matching data byte without BE proves a write.

## Candidate Assessment

**Full-VLMAX byte truncation: retain as a probe, not the leading proven cause.**
`sldu.sv:20` uses 11-bit vlen_t for VLEN1024, so1024 is representable.
`output_limit` at `:525` is wider still. EW8 shifts by0; stride conversion at
`:57` saturates only at the ELEN-width bound, not1023. Thus static initialization
does not wrap VL1024 to0 or clamp the last byte out. The enabled-byte comparison
at `:737` is local byte31<output_limit1024, with current_output_end32.
Inspect actual issue_cnt/output_limit at the original slide context, not a nearby
load/maintenance context. Any mismatch from the table moves the investigation
upstream; these source expressions alone do not demonstrate that mismatch.

**MaskM origin or packed-mask delivery: discriminating address boundary.**
The m8 case reads v0's last lane word (index3), while m4 reads index1. Verify
the actual request reaches that address and returns 256 one bits. A request
outside v0, an incomplete final mask load, or a stale queue word can explain a
zero bit. A different in-range word of a fully loaded all-one v0 cannot explain
this single case by itself. Do not change origin3 to0 merely because that makes
this uniform predicate pass.

**Pure mask shuffle is weak for this all-one discriminator.**
Both e8 cases have the same local mask pointer224, residual31 and mapping. A
permutation of 256 ones remains ones; a wrong eew_vmask permutation alone cannot
turn the needed bit off if the returned aggregate really is all ones. First
separate bad/missing packed data from MASKU extraction, queue ownership and SLDU
mask delivery. `sldu.sv:245`..`:306` retains mask data and lane validity together;
context flush/handoff must not discard this word before consumption.

**NP2 data path and VRF endpoint: check before blaming the predicate.**
Offsets511 and1023 both use residual31 and the same five non-power-of-two
permutation steps. `sldu.sv:388` deliberately removes complete-word displacement;
`:1033`..`:1063` uses atomic np2_data feedback. Identical residual logic makes a
generic residual31 bug less discriminating, but state/operand ownership remains
possible. If mask is all ones and out_en_seq[31]=1, inspect sld_op_dst[3][63:56],
queued BE/data/address, and request/grant progression to address127. Do not infer
correct data solely from issue completion.

**The final store is a separate observable boundary.**
Actual0x5b is also the original memory fill. It can mean the slide left old vd,
or that correct vd was never stored to memory. `sldu.sv:1097` distinguishes normal
grant from final VRF grant; `:1126` counts logical bytes, even with zero BE.
Thus retirement with vstart0 does not prove that byte was enabled. If capture
shows a correct slide result accepted, check final physical write and subsequent
store rather than relabeling this as a mask failure. `vstu.sv:315`, `:404`, `:432`
and `:446` handle byte count, final byte and AXI strobes; its vlen_t at `:31` also
represents1024. No specific store defect is established by this review.

The parent's current profile includes SLDU output request/normal grant but not
its final grant or every lane's physical VRF write; its bounded window also does
not extend to final store completion. These are evidence limits, not requests
for a new run. If existing capture cannot distinguish those last boundaries,
record them as unknown instead of asserting successful physical writeback.

## Consume the Existing Capture Once

Follow the first failing boundary: original accepted VL/stride -> lane MaskM
origin/count -> packed aggregate -> MASKU emitted predicate -> SLDU mask_q and
valid -> pre-mask out_en_seq/flat -> post-mask out_en -> data/address/BE and
handshake. The current explicit signal profile covers most of this chain.

For the expected single result, logical issue/commit progress is one byte even
if BE=0 (`sldu.sv:874`). A zero-mask result can therefore finish normally with
the exact observed old value. This makes the hypothesis testable, not proven.
Use instruction id/op/vd and acceptance to associate fields; scalar retirement
alone is not the execution cycle. Do not decode a partially written conversion
output or combine fields from unrelated contexts.

No unique current RTL root cause was established statically. The useful narrowed
comparison is origin1->3, destination word111->127 and byte total512->1024, while
local mask geometry and residual permutation remain identical. Leave the three
cancelled cases unproven and do not expand the test matrix before the existing
capture identifies the first divergence.
