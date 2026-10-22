# RVV-03 Original Whole-Register Matrix

The historical detailed whole-register program contains1134 executed cases
and366 explicit skips at VLEN1024. Its reported failures were the four
`vmv1r/2r/4r/8r` forms with nonzero vstart after changing architectural SEW
while source data remained in EEW8 layout. The previously accepted single and
four layout controls do not cover this full matrix.

## Original Identity And Preserved Behavior

The current archived C and generator hashes match the original detailed
manifest exactly. `whole.py` regenerates the archived `whole.S` byte for byte.
Both copies of the original Linux ELF, in the original package and additions07,
match SHA256 `f6ca381157fa767ab774017136af26d139e5c4776a1e7771f062251bbb7a2ecc`.
Prepared inputs and exact provenance are under[prepared01](prepared01/).

The source port replaces Linux startup/write/exit with the existing verified
SoC or Spike runtime. Only the outer operation loop gains compile-time bounds;
the original target assembly, input initialization, per-call setup, five
vstart choices, modes, return-value checks and1088-byte output oracle remain.
The full1134 source port is also built and reference-tested without partitioning.
The[wrapper diff](prepared01/wrapper.diff) makes these changes reviewable.

Each target invocation starts by loading all eight source and destination
registers as EEW8, selects its vtype/VL, sets vstart, executes the original
target, captures returned vstart and reads back the destination. Input and
output are reset before every call. Partitioning covers all source tuples but
does not claim execution of the unmodified Linux binary or preserve its
inter-operation timing.

## Exact Matrix

Every partition includes all three seeds, every original mode and all valid
start choices. Modes select SEW8/16/32/64 or VILL. The original suite excludes
whole moves under VILL, start greater than effective length, and starts at or
above the largest representable VLMAX. These exclusions are retained and
listed as skipped entries in[tuples.json](prepared01/tuples.json).

| Partitions | Target | Cases |
| --- | --- | ---: |
| op00..03 | vl1re8/16/32/64 + whole-store readback |240 |
| op04..07 | vl2re8/16/32/64 + whole-store readback |240 |
| op08..11 | vl4re8/16/32/64 + whole-store readback |240 |
| op12..15 | vl8re8/16/32/64 + whole-store readback |225 |
| op16 | vmv1r |48 |
| op17 | vmv2r |48 |
| op18 | vmv4r |48 |
| op19 | vmv8r |45 |
| Total |20 disjoint operation partitions |1134 |

Host checks run the original oracle with independent byte-copy emulation at
VLEN256/512/1024, and all20 VLEN1024 partitions. Six additional checks corrupt
prestart bytes, active bytes, tail bytes, a prefix guard, returned vstart, or
the captured original vstart. Every corruption is rejected. These29 checks
validate the oracle and partition accounting, not the hardware implementation.

Real Spike executed the complete1134-case program and all20 partitions with
the original vector assembly; each reaches successful architectural exit and
the exact original case/skip/error marker. Reference results are in
[complete.json](prepared01/complete.json). The full and partition reference
runs overlap and must not be counted as2268 distinct configurations.

## Candidate04 DUT Plan

[replay.py](replay.py) reuses the frozen candidate04 simulator and strict
original-oracle result checks. Prepared output is[vcs_candidate04_01](vcs_candidate04_01/),
with20 partitions, six workers,5400s per program and30000s service limit.
The four historically failing move forms are dispatched first. Any failure,
incomplete exit, wrong marker, checker exception or input drift stops the batch.
The plan reserves capacity for NF7, the current38 regression, full192 NF8 and
the pending Gather batch; total actual/reserved simulators must remain at most24
with at least32GiB available memory.

Budget evidence: the accepted single wholemove took46.15s and23113 retired
events. The complete source program retires about33.50million instructions in
Spike, including its scalar initialization/checking. Linear extrapolation gives
roughly three hours at six workers, with substantial uncertainty from the
different generated scalar code, vector configuration and concurrent load.
This is a planning estimate, not a DUT cycle or performance measurement.
The per-program90-minute limit avoids one unbounded monolithic simulation.

Current stage: **DUT running; not yet accepted**. The isolated user service
`ara-whole1134-candidate04-01.service` started on2026-10-11 at03:37 PDT.
Six actual candidate04 `simv` processes were confirmed for op16..19 and op00..01;
their presence is startup evidence, not test acceptance. The sealed plan hash is
`4026384e0a1bb8f3163c8f4604bfa08a95350b3d12e49f2bbafdbe5696a84269`.
The service enforces30000s and control-group teardown independently of the
per-program limits. See[independent_review01.md](independent_review01.md).

The future terminal result must include all20 program names, original1134 case
membership, exact raw markers, zero exits and unchanged image/ELF/source pins.
It will establish the source-derived configuration matrix, not Linux execution
or blanket acceptance of the separate historical memory-fault families.

Partitioning also changes the vtype inherited by the preparatory whole-register
loads between operations. Thus all1134 tuples passing in20 partitions would
not prove that the full original execution history passes. The continuous
full-program Spike run passed; its DUT counterpart remains outstanding.
