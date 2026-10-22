# Original e16/mf4 M6 Single Plan

Prepare only. No launch, build, reference run, live simulation query, waveform
or retry. Reuse the exact prepared SoC ELF on the existing frozen M6 image.
This new directory does not alter any reference READY/CONFIG/pin/helper/log.

## Independent Admission

Actual acceptance is `../original_e16_mf4_reference_audit01/REVIEW.md`
(d9ad719158b37c9a1c1788b1e44fab5f84f06bc0d50a601128d8322cee91dc4c)
and **result.json**, not audit.json
(a0cfeb4214f5569092f6acf9cfd4c9539e275b5699e319aa2e36e0d567ba8678).
READY is f858249f61dc7b9c4e3507f78bb483543d0439ef74942e838fc1251931a661de;
canonical sourceproof is f6efe2b2b360e96d4caa69fef05764bf205040f6c7347033e01cbd19562185af.
Host/prepare are gated on those actual accepted files and their source pins.

Authorization provenance clarification: preparation and resource/profile
coordination arrived through the **parent coordinating messages**. Earlier
assistant or parent descriptions must not be recast as direct original-user
ISA commands or as a program-correctness proof. The actual command includes
Zfh+Zvfh; the later minimum-profile file lacks explicit Zfh. The sealed
CONFIG_DELTA remains unchanged. The independent review accepts only this
concrete actual-profile reference with zero scalar-FP consumers, not exact
minimum-profile equivalence or DUT correctness. Correctness evidence is the
original source/ELF/raw/oracle and independent audit, not message attribution.

## Exact Scope And Gates

One authentic archived scenario3/l4/mode3/frm0/op0/sticky0, e16/mf4/cap16/VL8.
Original SoC ELF: eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162.
All scalar skip loops retained:3360 fixture rows,6720 field reads,215040
mask-byte stores,128 source-element stores,512 seed-word stores,144 initial
output-byte stores. Exactly one original21-instruction reduction helper.

The strict CSV checker compares **every retired instruction PC/encoding**
against the actual pinned SoC ELF. It requires fixture bank1/row1545, ordered
full fixture traversal, source16/seed64/mask64/full-output setup, exact helper
argument pointers and values, contiguous21 retirements, vset return capacities,
saved frm/fflags, requested zero CSR operands, NV16, returned vstart0, packed
flags, and original CSR-restore instructions using the saved zero operands.
All144 original scalar LBU checks must occur after the whole helper:0x7e00,
126 destination tail bytes0x5b, and16 guard bytes0x5b. CTRL exit0 and only the
original no-effect park afterward are required. CSV does not expose vector
payloads directly: full data/store correctness is proved by the original
scalar oracle, not fabricated vector-port or waveform observations.

The generic frozen-runner trace validator is also mandatory. Raw console AND
run.vcs.log must have exact original/wrapper/simulator completion and no
failure/DETAIL, including the real `RVV_FP_REDSPECIAL_DETAIL` partial line.
Private ELF/inputs/command/image, COMPLETE membership, hashes, and budgets
are checked. A sticky abort survives strict checking; publication uses the
existing blocked-signal atomic final decision. Terminal validation fresh-reads
and hashes the disk plan, then rechecks all image/source/helper/reference pins.

## Resource And Budget

jobs1, case5400s, direct service6600s, no FSDB/retry/build. A new pinned parent
run authorization is required; prepare permission cannot launch a process.
Service identity requires this worker as MainPID in its exact cgroup, trusted
explicit user-bus environment, KillMode=control-group, Restart=no and6600s.
The inherited resource gate counts live simulators once, enforces cap24 and
32GiB available RAM, and adds only unused parent reservations. No live/resource
queries occur during Host or prepare.

Reference firmware1858335 instructions contains1612800 scalar mask-loop
instructions. Parent planning estimate is about47min (2820s), implying659
retired/s; this is an estimate, not a new measurement or runtime guarantee.
The much slower273retired/s proxy would take6807s and exceed5400s. The bound
remains5400s regardless: timeout stays incomplete, with no automatic extension
or oracle/traversal reduction. Service6600s leaves1200s checking/cleanup headroom.

## Preparation Interface

```sh
python3 -B test_host.py
python3 -B replay.py prepare \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --reserved-slots 0 --authorize-prepare
```

`prepared01/ready.json` contains the exact no-build service command with new
parent-review placeholders. It must not be executed before independent entrance
review and parent launch approval. No service is started by this preparation.
Host fixtures are synthetic checker protocol tests, not alternate ELF/reference
stimuli or claimed architectural results. Expected acceptance, if later run,
is only this original single, not all11 or the full6720-call Linux parent.

Draft Host history: host01 stopped in class setup, before any test/DUT, because
it incorrectly assumed fixed Spike-to-SoC offsets inside original C. The SoC
linker relaxes some global accesses to GP-relative instructions. The corrected
checker identifies each relevant actual SoC instruction uniquely inside the
original main function and verifies all retired encodings against that ELF.
host01.json/log are retained. host02 reached31 tests but its synthetic register
fixture omitted C.LI (used for a6), and its mock COMPLETE record omitted the
required status_counts. The fixture now includes those existing contracts;
neither correction weakens the production checker. host02.json/log are retained;
host03 is the final Host result, not a DUT retry.
