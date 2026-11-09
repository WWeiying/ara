# Resident PV: Accepted Production-SoC Smoke

## Scope

One complete attention slice from captured Qwen3 data: D128, two query heads,
one KV head, T137, processed as 64+64+9 tokens. The whole caller executes on
CVA6 plus the production RVV/AKV integration. It is not a complete model,
decoder layer, Linux application, or FPGA acceptance.

The software prepares seeds and probabilities with ordinary RVV, then directly
issues the experimental resident PV instruction. It retains the original QK,
online softmax, normalization and output path. The capability remains zero, so
production runtime selection is not enabled by this experiment.

## Immutable Identities

Evidence is in the signoff worktree's `verification/out`:

- SoC build: `resident_pv_soc_build_20261109_03`.
- Software: `resident_pv_soc_eval_smoke_20261109_01`.
- Run: `resident_pv_soc_smoke_vcs_20261109_01`.
- Image SHA256: `70fe9cae0fd260e15894f38d2bf5461948723ab445051e402a1ea2bbde183ab4`.
- ELF SHA256: `800112e29ca917d7039be7b6608ac95ae91f66bd2bdf4492fc391a7801a2e865`.
- Result SHA256: `ded2362bd087d84ca7377bea63fd27406eed279f1641707c3a4512157a0b34a4`.
- Protocol result SHA256: `c53b36f7a68ea3ff379a9249b763962ffbc988483e61d78cde4f077ac6d16c97`.

No bus-width, DDR, clock, lane-count or arithmetic-array change is present.
Four lanes, VLEN1024, 128-bit AXI, shared integer multiplier, unchanged parallel
FMA implementation and 16 MiB simulation-only memory match the reviewed image
contract. The new private arithmetic uses the existing lane FPUs.

## Acceptance

The directly owned worker exited successfully; result state is PASS. VCS
simulation took 490.224 seconds. Acceptance requires all of the following:

- All 256 FP32 output words equal the independently pinned native golden
  bit-for-bit. The target's printed expected field is not the host oracle.
- FCSR exactly 3, VCSR/VSTART zero, and initial CSR state zero.
- Query contents, guard fingerprints and the complete immutable input-data
  fingerprint match the independently derived expected values.
- Exactly 100 legacy AKV transactions complete successfully. The new path
  replaces 137 V-row commands with three PV commands, not with omitted work.
- The ordered vector trace contains 96 K-panel commands and three exact PV
  encodings, with no substituted V-row path.
- Real LDU-to-VRF writes have the correct VID, destination interval, byte
  enables and count. Every PV command drains all 96 source words and all 64
  final result acknowledgements before completion.
- Every lane's accepted and returned FMA counts agree. Command-local flags
  equal the union of the four lane flags.
- The passive CPU/backend/AXI protocol checker passes, with the full executable
  and compiled-library identities checked. Original and copied input/artifact
  pins still match after execution.

ABBA admission separately replays these numerical, work, protocol and artifact
checks from the original evidence. It does not accept a PASS string alone.

## Measured Work

| Tile T | PV command cycles | FMA beats per lane | Source words, all lanes | Actual result writes | Final acks | Local flags |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 1148 | 1024 | 96 | 64 | 64 | 3 |
| 64 | 1148 | 1024 | 96 | 64 | 64 | 3 |
| 9 | 213 | 144 | 96 | 64 | 64 | 3 |
| Total | 2509 | 2192 | 288 | 192 | 192 | union 3 |

Four lanes each execute four FP16 elements per accepted FMA beat. Total useful
work is 35072 scalar FMAs, matching the original ordered PV computation.
Accepted issue occupancy within the three exclusive PV service intervals is
`2192/2509 = 87.37%` per lane. This is an input-handshake rate for these intervals,
not whole-call FPU utilization or a count of simultaneously occupied pipeline
stages. Preparation outside the instruction is not included in that denominator.

The complete attention call took 34263 cycles: 34228 to return and 35 for the
final drain. This single smoke call has no same-layout baseline arm. It must not
be divided into an earlier software run to claim an optimization speedup.

## Remaining Gates

The separately built ABBA ELF compares strong register rotation with preparation
plus resident PV in one binary and on the same SoC image. It includes preparation,
instruction execution, stores and final drain. Only that paired result can
establish the first complete-call performance increment.

Selected D64/D96/D128, H1/H2, token tails, admitted rounding modes, special FP
values, illegal admission, failed-context recovery and QBS coexistence are still
required at SoC level. Component tests are supporting evidence, not substitutes.
QK's shared-storage/FP32 extension and production runtime capability remain
pending; no synthesis, FPGA update or whole-model claim follows from this PASS.
