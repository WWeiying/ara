# Current board review: lane mask requests

Scope: `hardware/src/lane/lane_sequencer.sv` only. No dispatcher, VMFPU,
MASKU, SLDU, shared builder, or FPGA source mirror is modified by this work.
No commit is made. This is reduced current-RTL contract verification, not
execution or closure of the original board programs.

## Provenance and hypothesis

`provenance.json` pins 23 archived files, original ELF/report hashes, and
selected records from `ALL_FAILURE_REVIEW.md` and `STALL_TRIAGE.md`. Original
ELFs, sources, reports, and the deployed lane source are copied into
`verification/out/board-current-lane-provenance-20261010/`.

The archived scalar comparison e64/m1 single has seed=0, op=VMSEQ.vx,
VL8/vstart4, predicate all-on, scalar=-3, old destination byte=0x5b. Its
prestart bit 2 changed from zero to one. The associated original ELF hash
is `8de4083a10c2a8f88be76700b9ce1f6a4ecd263d41eeef0655645641725dac4f`.
The current lane already requests packed old vd from word zero (line near
1096), and already excludes mask-logical vs1 from the global mask override.
Neither existing repair was changed.

The recorded scalar comparison stall `rvv_masks_scalar_restart_e8_m4` has
VL512/vstart256, PC=67084, opcode=608e4c57 (vmseq.vx v24,v8,t3,v0.t), original
ELF hash `5f56543aaff7c6c904d2e1c1727ba64d209b009434d7e23ddd5af1f54da03fb4`.
The board print is a trial boundary, not an internal acceptance probe.

Falsifiable prediction before changing RTL: the current lane supplies only
one EW64 mask aggregate, starting at word 1, while MASKU's ALU/MFPU/MASKU
consumers still traverse VL512 from zero. After that raw word is exhausted,
the consumer retains 256 elements and cannot complete. The zero-vstart
control must receive two raw words and complete. Memory must retain its
different restart-relative request contract.

A second inspected lane contract predicts slidedown MaskM origin=64 at
vstart256 because it inherits ordinary per-lane vstart. Its full destination
mask traversal instead requires origin=0. Slideup already replaces the
origin with its stride-based word coordinate.

## Harness and Limits

`run.py` compiles host VCS, never Verilator or ZCC. It snapshots every listed
production source and included header. Interface typedefs are copied verbatim
from the snapshotted current `lane.sv`; the production packages are used.
Four lane sequencers, four real integer VALUs, and the real MASKU/operand
shuffler execute in a 220-cycle bounded fixture. The three focused FSDBs dump
only the top, MASKU, lane-0 sequencer, and lane-0 VALU, ending at 2260 ns.
Compile timeout is 180 seconds; each simulator timeout is 30 seconds. At most
four case-local simulators run concurrently, and a failing batch stops further
dispatch. No files consumed by an active build are edited.

Integer comparison data uses the original seed-0 xorshift/boundary generator,
scalar=-3, and predicate patterns 0xff, 0x00, and 0x24. Every bit below VL is
checked, including prestart and masked-off bits. Raw old-vd/mask streams are
finite and honor each actual lane request's EW64 word origin/count. Old vd
word zero is the archived 0x5b pattern; later words intentionally differ so
an incorrect word origin is observable.

Important abstraction: ordinary data operands are modeled as a zero-origin
post-queue stream. There is no operand_requester, VRF bank arbitration,
dispatcher, source-layout conversion, alias lifetime, or software execution.
This proves the packed-mask request and merge contract, not full architectural
execution of the original single. MFPU/ALU arithmetic and memory cases test
mask supply with an ideal ready consumer, not those functional units' results.
Mask-logical and FP-compare checks are lane request checks only; slides are
also request checks, not joint SLDU correctness tests. FP flags are excluded.

Probe semantics:

- `mask_origin/length`: registered lane-0 MaskM command, in EW64 words.
- `old_origin`: registered lane-0 MaskB word origin, not data-element vstart.
- `raw_m/raw_b`: lane-0 raw words handshaken into MASKU operand spill registers.
- Comparison `issue/commit`: remaining processing elements / packed-result
  elements awaiting commit. `read` is not the completion counter for this path.
- ALU/MFPU mask-supply `read/commit`: remaining mask expansion / delivery
  elements. `issue` remains VL and does not diagnose a stall for this path.
- `finish`: testbench cycle at MASKU's actual `vinsn_done[3]`, measured from
  reset release, not software cycles or total instruction latency.
- `beats`: observed output valid/ready samples, diagnostic only. It is not the
  raw-word count or a performance oracle; completion and raw counts are checked
  independently. It is not qualified with MASKU's internal queue-pop event and
  must not be substituted for committed beat count.

## Baseline

Canonical baseline: `verification/out/board-current-lane-baseline-20261010/`.
Lane SHA256: `65d0e9dc482e4c340de8adcd4f9873138c824e5af8139c6424aed256b96352ce`.
Ten assertions finish: four expected RTL contract failures, six passing
controls. An `expected_failure` record means the bug was reproduced, not that
the RTL passed correctness.

| Case | Baseline result |
|---|---|
| e64 VL8/vstart4 integer compare | old origin 0, correct data/prefix, done cycle 10 |
| e8 VL512/vstart0 compare control | mask 0/2, correct data, done cycle 24 |
| e8 VL512/vstart256 compare | mask 1/1, raw_m=1, issue=256, commit=256, no done |
| e16 VL512/vstart256 MFPU mask supply | mask 1/1, read=256, commit=256, no done |
| e8 VL512/vstart256 ALU mask supply | mask 1/1, read=256, commit=256, no done |
| e8 load/store mask supply | mask 1/1, done cycle 14 each |
| unmasked mask-logical vs1 request | vs1=v16, mask 0/2; no completion claim |
| slideup stride1 request | mask 0/2 |
| slidedown stride0 request | wrong mask origin 64, length 2 |

## Repair and Reproduction

Only the lane is changed: zero-origin/full-length predicate requests for
ALU/MFPU/MASKU; zero slidedown mask origin. Memory trimming, the mask-logical
source exemption, packed old-vd origin, and slideup stride handling remain.
Candidate lane SHA256:
`2f1899d5bcf14df84a7622678276619ce6bfbcfecdc6239072412d0fe7a86c99`.

Run from the verification worktree with VCS and Verdi on the host environment:

```sh
python3 verification/fpga/current_board_review/lane/run.py \
  --baseline --frozen verification/out/board-current-lane-baseline-20261010/snapshot \
  --lane verification/out/board-current-lane-baseline-20261010/snapshot/hardware/src/lane/lane_sequencer.sv \
  --out verification/out/NEW-lane-baseline
python3 verification/fpga/current_board_review/lane/run.py \
  --frozen verification/out/board-current-lane-baseline-20261010/snapshot \
  --out verification/out/NEW-lane-fixed
python3 verification/fpga/current_board_review/lane/audit_results.py \
  --baseline verification/out/NEW-lane-baseline --fixed verification/out/NEW-lane-fixed
```

The fixed suite has 41 cases: 33 integer compare data checks and eight mask
supply/request checks. Regression includes e8/e16/e32/e64, legal LMUL ranges,
all-on/all-off/sparse masks, unaligned starts, aggregate boundaries and tails.
The audit requires identical baseline/fixed testbench and production inputs
except for `lane_sequencer.sv`, and explicitly rejects full-board closure.

## Fixed Results

All 41 cases passed. Canonical results and source-differential audit:
`verification/out/board-current-lane-fixed-20261010/status.json` and
`verification/out/board-current-lane-fixed-20261010/audit.json`.
Audit status: `PASS_REDUCED_LANE_CONTRACTS`; only the lane production source
differs, and its candidate hash matches the current worktree. No simulator is
left running. The candidate is ready for the parent's frozen integrated build.

| Case | Fixed result |
|---|---|
| e64 VL8/vstart4 integer compare | old origin 0, data/prefix pass, cycle 10 unchanged |
| e8 VL512/vstart0 compare control | mask 0/2, data pass, cycle 24 unchanged |
| e8 VL512/vstart256 compare | mask 0/2, raw_m=2, issue/commit=0, data pass, cycle 24 |
| e16 VL512/vstart256 MFPU mask supply | mask 0/2, raw_m=2, read/commit=0, cycle 39 |
| e8 VL512/vstart256 ALU mask supply | mask 0/2, raw_m=2, read/commit=0, cycle 23 |
| e8 load/store mask supply | mask 1/1, cycle 14 each, unchanged |
| mask-logical vs1 / FP-compare requests | origin 0, length 2; no completion claim |
| slideup / slidedown mask requests | origin 0, length 2; no SLDU data claim |

These measurements establish the current lane request defects and their
focused repairs. They do not close every historical compare/alias, FP flag,
gather, arithmetic, or slide record. Original Linux ELF execution and the
integrated requester/queue/dependency paths remain for parent regression.

Setup artifacts are not RTL evidence: root
`out/board-current-lane-before-20261010/` is an aborted compile missing
`fixed_p_rounding.sv`; it was never simulated and must not be staged. The
initial `verification/out/board-current-lane-before02-20261010/` diagnostic run
detected the slidedown request failure. The canonical baseline replaces its
unqualified ancillary ready signals and adds the expected slidedown-error
assertion; the small-case LMUL is also corrected to the archived m1 shape.
Production lane RTL is byte-identical. No false fixture failure is
counted as an architectural board reproduction.
