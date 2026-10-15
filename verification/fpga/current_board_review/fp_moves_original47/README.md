# Archived RVV-10 Forty-Seven Singles

## Terminal Candidate03 Acceptance

**47/47 archived single-source ports PASS on candidate03**, independently
postchecked after completion:32 genuine slide cases and15 scalar-insertion
cases, with all15 original SEW/LMUL shapes and unchanged original oracles.
This is not execution/closure of the21504-case parent matrices, the two
overlapping parent/detail records, or the original Linux binaries.

Evidence: [terminal result](vcs_candidate03_02/complete.json),
[independent postcheck](terminal_audit01.json),
[runner summary](vcs_candidate03_02/replay/summary.json).
The independent check did not trust PASS labels alone: it verified exact47
membership across the archived provenance, ELF manifest, plan, run and summaries;
all runner exits0, exact one-case/zero-error and wrapper markers, firmware
`tohost=0`, and absence of failure/trap/fatal markers in all47 consoles. Every
private input and actual image/command identity matched. Rehashing1309 distinct
pins, including all539 frozen source files, found zero drift.

jobs2 runner wall time was853.10796 seconds; per-case elapsed sum1654.21626
seconds and maximum56.79654 seconds, within the180-second/case budget. These
are host simulation timings, not RTL performance comparisons. No rebuild or
production edit was performed. The initial capacity refusal remains intact in
`vcs_candidate03_01/`; the authorized fresh admission used `vcs_candidate03_02/`.
This postcheck did not query service/process state or launch any simulation.

- Candidate03 image ledger SHA256:
  `e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6`.
- Snapshot SHA256:
  `382af2912634002ceecbaa44b8e8f0fb8262ab6aeb30e52d66a9bb0268508a2f`.
- Accepted terminal report SHA256:
  `e798a69ae75ff5768fa2ee63670ea5e9da103ca6afa3c543c853cd34f8ec4b21`.

## Retained Preparation History

Initial preparation status was **HOST + SPIKE 47/47 PASS, READY NOT DUT PASS**.
All47 original singles had SoC and Spike ELFs; no VCS run had been launched
at that stage. Preparation rechecked309 original/helper/tool/runtime pins and
all prepared files unchanged. The later DUT acceptance above supersedes only
the pending-DUT status, not these original artifacts or their provenance.

This directory owns only the original47 single-source ports, software reference
and authorized replay. No production edit, image build, or full21504-configuration
parent-matrix execution. Candidate03's focused11 acceptance remains separate
evidence; original47 acceptance now comes from its own completed replay above.

## Membership And Historical Identity

Authority: [fp_moves/SELECTION.md](../fp_moves/SELECTION.md).
Campaign `C` is `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
The exact47 names come from `C/rvv_small_fp_moves01/manifest.json`, SHA256
`e517533db5227820bbce08f6230f32b904d1d0a02169178e99d4f98221495d52`.

| Archived operation | Shapes | Count |
| --- | --- | ---: |
| op2 masked vfslide1up.vf | e16/mf4 | 1 |
| op3 masked vfslide1down.vf | e16/mf4 | 1 |
| op4 unmasked vfslide1up.vf | all15 below | 15 |
| op5 unmasked vfslide1down.vf | all15 below | 15 |
| op6 vfmv.s.f | all15 below | 15 |

Shapes: e16/{mf4,mf2,m1,m2,m4,m8}, e32/{mf2,m1,m2,m4,m8},
e64/{m1,m2,m4,m8}. There are **32 genuine slide regressions and15 scalar
insertion originals**, not47 new synthetic controls. The two overlapping parent/
detail records in the49-record family are not added. No op0/1/7 case is added.

The original single manifest has `board_reproduction_confirmed=false`, a
pre-board preparation field. The later `C/rvv_move_symptoms02/symptoms.json`
(SHA256 `dacc94e171ac5e8baa2fd0c4674e8283ca772fda32d5d7347234dcf55f5c07a9`)
confirms matching prefix/single numerical symptoms for all47. Both histories
are preserved, including the three frozen report hashes. This is old measured
data failure evidence, not inference from a stalled trace or proof of shared
internal root cause. Historical QEMU512/1024 references are not current DUT PASS.

[original_provenance.json](prepared01/original_provenance.json) contains every
archived single name, original parent identity, C/S/header hashes, both original
ELF hashes/paths, historical first-failure fields, target opcode/PC, SEW, LMUL
and capacity. All original parent and single ELF bytes are rehashed. No original
Linux ELF is rebuilt or executed.

## Exact Setup And Oracle

All47 retain the archived tuple: seed0, scalar0, valid boxing, VL2, vstart1,
mask-mode0, sticky0. Mode0 means all-ff predicate bytes, not all-off. Only op2/3
are masked targets; op4/5/6 are unmasked. Destination remains v24, source v8,
scalar ft0, predicate v0. LMUL/SEW and `tu,mu` settings remain those of each
archived assembly.

Every case retains full-capacity source and old-destination loads, predicate
load, boxed +0 scalar load, selected VL, flags/vstart setup, target, immediate
vstart/fflags sampling, saved-fflags restore and full-capacity destination store.
At VLEN1024, capacities range16..512 depending on shape. The source values
include the original zeros, finite extrema, infinities and NaNs, unchanged.

The original oracle block is required byte-identical. It checks all cap
elements, prestart/tail preservation, returned vstart0, unchanged fflags0,
scalar-result sentinel and both guards. For op6 it retains the crucial rule
`start < vl && i == 0`; it is not rewritten as the ordinary `i >= start` rule.
For slides, element0 remains the original maximum finite value, while active
element1 comes from the proper source/scalar. Physical fractional-register
tails beyond the original cap are not claimed as extra coverage.

`prepare47.py` calls Tesla's pinned `fp_moves/focused.py:adapt` with the original
VL2/start1, without editing that helper. Original C/S/headers are copied into
each prepared case. `adaptation.diff` shows only Linux entry/write/exit wrapping
and unreachable op0 trace-drain handling; no input, tuple, loop or oracle change.
The three existing integration startup/runtime/linker files are reused unchanged.
This preserves original single math/setup, not original parent-prefix state,
Linux ELF addresses or OS timing.

Three core generator/oracle sources match their archived hashes. The current
prefix-capable reducer is a later version, explicitly distinguished from the
archived reducer hash. Its single extraction and the original assembly generator
must reproduce all47 archived C/S files byte for byte. Archived reducer bytes
were not recovered. The initial preflight rejection and this limitation are
recorded in [PREPARATION_HISTORY.md](PREPARATION_HISTORY.md), not hidden by
rewriting the archived manifest.

## Software Verification And Handoff

Host: **47 positive checks and282 negative checks PASS**. The host-only fixture
independently hashes full source/old-destination/mask/scalar inputs, verifies
the original parameters and models each actual selected operation. Mutations
cover the historical element0 symptom, tail data, NV flags, guard, returned
vstart and scalar-result sentinel. None is linked into target ELFs.

Spike: **47/47 PASS**, including all32 original slide regressions. Total
reference execution wall time was1.700 seconds (excluding compilation),
714101 retired instructions to replay_exit across the47 separate programs.
These are Spike instruction counts, not measured RTL cycles or VCS timings.
SoC ELF sizes are9680..9776 bytes.

| Op | ELFs | Reference instructions per ELF | Total instructions |
| --- | ---: | ---: | ---: |
| 2 | 1 | 10247 | 10247 |
| 3 | 1 | 10255 | 10255 |
| 4 | 15 | 10244..24606 | 231836 |
| 5 | 15 | 10242..24604 | 231806 |
| 6 | 15 | 10219..24085 | 229957 |

The target build uses the existing RISC-V GCC and runtime, with no ZCC and no
implicit vectorization of the scalar oracle. Reference ISA is explicitly
`rv64gcv_zvfh_zvl1024b`. `address_map.json` maps each archived Linux target to
its new SoC/Spike target and requires identical opcode, exact operands and an
actual call to the target function. Spike stops before the target to inspect
PC/VL/vstart, then requires original zero-error completion, wrapper success and
exit0. This reference does not weaken illegal-instruction or exception checks.

The final generated status is in [status.json](prepared01/status.json), host
evidence in [host.json](prepared01/host.json), reference evidence in
[reference.json](prepared01/reference.json), and all47 compatible SoC entries
in [soc/programs.json](prepared01/soc/programs.json). There is no synthetic
`all` ELF or full-parent matrix in this preparation. Each entry retains its
original name and exact one-case success marker; original and adapted ELF
identities remain distinct.

Handoff SHA256:

| Artifact | SHA256 |
| --- | --- |
| soc/programs.json | 9f36fdf5b60ad89ac9a3aede4975d7a3d39ba55d86a5db3af5e40730f5b78fcb |
| original_provenance.json | e140181cf6ec3687427d7858aa82710f51e0a52cde9752f32a3828b6d32f8b30 |
| address_map.json | 7d86111069a3946165ceeb528006b0770c7c88b88561fd2cc79467644a8cf0d5 |
| reference.json | 760c53bee4e126f7eb20b7e6361f59431e967fe325cef21d637da97ac385817e |

Any further DUT replay must be separately reviewed on an explicitly pinned
image using the existing integration runner. Require complete
membership, successful firmware exit, exact original markers/counts and failure
marker veto; do not inherit acceptance from focused11 or from older slide tests.
No image is selected or launched by this preparation script.
