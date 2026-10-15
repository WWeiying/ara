# E8 M1 Full4095 Source Gate

**NO_BLOCKER_SOURCE_FOR_HOST_COMPILE_ONLY.** No actual compiled-artifact,
reference-entry or DUT acceptance is given by this source review. Aquinas
owns `full_e8_m1_packed_prepare01`; this reviewer changed no producer file,
ran no test/compiler/reference/DUT and did not query the running mf2 task.

## Bound Source

| Source | SHA256 |
| --- | --- |
| Archived rvv_matrix_e8_m1 ELF and recovery22 rebuilt ELF, independently rehashed equal | 199a69e4394959e73f0b7458359c06f0e39a09f4c621028eb356723684dd1f9a |
| Original rvv_matrix_e8_m1.S | 7d2c0d69f8390a795d884d95eb43b85dc8c405b5dc9b227925da22a218ae7cce |
| Original e8/operations.h | 7686eb17f96d500c82711d09bbaa74c965352b4257b0b7db3510d3fbbd9bf48c |
| recovery22/reconstructed_oracle.c | 7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91 |
| PLAN.md | 7e2326a77280cd0387cf7cec48cd072e540ae7230ef3f1d3ed008887fa609bd4 |
| model.py | fcc70864b06894b733ea27ddea2356574882cfcf3ae38abea485944d2acbb3b4 |
| packed.h | 02a179ec40cb5df9df844ebc333c1de142f4fb3cf969f141bc85b43de88116dc |
| host.c | d1f7c14475b00d69d03b80aee9dba16ccd6c9cab132b8d4b0519358f3f217f49 |
| prepare.py | 0eefab76361d5ad44a5e2ca30524484b51b138a68e3e5e0422b1ebc171107e90 |

Original C bytes remain lost; the reconstruction is binary-equivalent, not
recovered verbatim C. Original assembly retains capacity plus25 helpers,
13 instructions per call, including full-capacity input/old-vd loads and
store, original mask load, target VL, vstart write/read and target instruction.

## Static Findings

- VLEN1024/e8m1 gives CAP128: one full128B physical register, unlike mf2's
  observed lower64B. Original source histories remain3 seeds,7 VL values
  (0,1,2,3,64,127,128),3 masks,20 ordinary operations with3 starts and5
  special operations with1 start. Duplicate starts are retained. Expected
  totals4095 calls,524160 results,8190 guards,4095 vstart reads,53235 helper
  instructions and69615 packed comparison reads.
- The model recomputes128 RNG steps per seed with original recurrence and
  special byte values. Host compares every actual C input against generated
  input and checks unused original backing. Seed state is not copied from
  mf2. Source arrays remain a/b1024, out1026, mask128.
- Original gather bounds are CAP128, not target VL. Index255 is out of range;
  indices below128 can read original source elements beyond target VL.
  Slidedown uses the same original capacity bound. Reduction seed and
  compress order/sentinel suffix match original C.
- The130B output comprises frontguard,128 data bytes,rearguard. Sixteen8B
  accesses plus2B at offset128 cover it exactly. Tail2 is result127 and rear
  guard, never an oracle exemption. Memcpy avoids alignment/aliasing UB;
  the padded17th ROM word does not justify reading output bytes130..135.
- Software initializes all128 mask bytes;16 meaningful bytes and112 zeros.
  Actual vlm loads16 bytes, not all128 software bytes. Per-seed source and
  per-group mask initialization remain in their original loop positions;
  every call initializes output anew. Original per-byte failure fallback
  stays verbatim inside the packed mismatch branch.
- Flat ROM4095*17*8=556920B plus384B masks is plausible within1MiB.
  Static arithmetic is not actual layout proof. Actual section placement,
  bss_end/stack_top gap >=64KiB, actual stack frames and compiler-generated
  memcpy loads/stores must be inspected after compilation. In particular
  do not presume SH/SD ordering or reuse mf2 inline PC/base-register sites.
- Planned Host checks original and packed all4095/counters/errors, eight
  fault categories plus deliberate UBSan shift64, all130 byte mutations,
  unaligned access and protected-page exact boundary. Host positives are
  software-model evidence, not actual helper execution.
- Compile gate compares all original helper machine bytes and rejects extra
  RVV with both vectorizers disabled. Original capacity vtype is m1, not
  inherited mf2 vtype7. Actual helper encoding/ABI remain artifact gates.

## Subsequent Gates

Actual Host numeric receipts, SoC/Spike ELF identities, complete pins, layout,
ROM bytes, no-extra-RVV and real scalar instruction sites are still required.
Before this source gate was handed off, prepare.py's reference metadata was
clarified from hard_instructions=3M to distinct hard_steps_including_boot=4M
and firmware_to_HTIF_accept_limit=3M; this is the bounded contract below,
not a limit expansion or permission to run the separate reference drafts.
Then separately review the one reference entry: finite rs4000000+quit,
120s,768MiB, firmware-to-success <=3000000, exact full4095 oracle and real
boot/HTIF/side-effect-free park through EOF. No reference retry or budget
growth is approved. This document itself does not release reference or DUT.

For a future DUT observer, derive the no-op exception from actual encoded
VSLIDEUP.VI immediate2 and VL<=2; preserve full oracle and generic lifecycle.
Do not waive VL3 slideup, slidedown, masked-off nonempty ordinary targets,
nonempty op24, or any of the five setup/store memory helpers. Predicted18
source no-op targets are not an actual DUT observation. Do not modify the
running mf2 checker to apply this fact.
