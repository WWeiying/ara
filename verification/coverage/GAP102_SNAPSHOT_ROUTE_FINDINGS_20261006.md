# GAP102: correct execution, wrong coverage-path hypothesis

## Outcome and sealed evidence

The parent collector02 verified the full architecture/data oracle, but raw127
did not hit. Actual single VDB union with frozen717 adds zero line, condition,
branch and FSM bits. There is no718 admission and no waiver justification.
Collector01 and02 failures, their original artifacts, run02 and RTL are retained.

Independent read-only evidence:

`verification/out/gap102-snapshot-route-offline-evidence-20261006-01.json`

SHA256: `afcb91cfc64dd25edad2e00b9a6ae782b4a4c9a15d1127e093bd95c5812fc5ec`.

This diagnostic re-read the actual single VDB using the sealed diagnostic input
list and required exact equality with collector02's saved raw bitmap. It binds
the old design, source owner, native branch paths, original CSVs and observed
write byte counts. It does not rerun the collector, simulator, Spike or DVE.

Three focused tests passed. Reproduction in a fresh evidence filename:

```bash
python3 -m unittest discover -s verification/coverage -p test_explain_gap102_snapshot_path.py
python3 verification/coverage/explain_gap102_snapshot_path.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/gap102-snapshot-route-parent-check-20261006-01.json
```

## Old-source identity and monitor semantics

Read dispatcher from the historical source snapshot, not current RTL:

`verification/out/old-image-source-evidence-20261006-01/ara_dispatcher.sv`

SHA256: `9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43`.
It matches the old66-file image's build-source manifest. The same manifest
matches `ara_system.sv` and `ara_commit_monitor.sv` bytes used for interpretation.

The monitor's allocation `insn` is `ara_req.verify_arch_insn`, not internal
`ara_req.op`. Its EEW field is `ara_req.vtype.vsew`; source0 on alloc/done is
a formatted placeholder. Maintenance-uop instruction text therefore remains
`0xf2c56457`; it must not be called four architectural MAC instructions.
Architectural retirement order and accelerator sequence are separate namespaces.
The monitor explicitly writes zero PC for arch_start and maintenance events.

## Actual sequence43

One arch_start: cycle14006, PC0, opcode `0xf2c56457`. One matching architectural
retire: cycle14066, PC `0x8000222c`, order8609, no trap. Backend completion may
follow scalar retirement; it is not required to precede retirement.

| Alloc/done cycles | use_vd / vd | EEW / VL | Granted bytes | Source-derived interpretation |
| --- | --- | --- | --- | --- |
| 14008 /14027 | 0 /0 | EW16 /129 | 0 | Source snapshot capture |
| 14031 /14046 | 1 /8 | EW32 /32 | 128 | Whole-register normalization at v8 |
| 14048 /14063 | 1 /12 | EW32 /32 | 128 | Whole-register normalization at v12 |
| 14065 /14090 | 1 /8 | EW32 /129 | 516 | Original widening MAC |

Snapshot capture at source1481-1506 uses `VSLIDEDOWN`, no architectural vd,
source EEW and saved source VL. OVERLAP_CAPTURE at1335-1365 instead uses
destination EEW and one-register element count: EW32/VL32 for this shape.
The first uop's EW16/VL129 discriminates the two source-defined capture paths.
RESHUFFLE at1519-1559 uses a destination-writing VSLIDEDOWN and full-register
VL, matching the two128-byte writes. Their exact old EEW notebook contents
are not directly logged; do not infer those values solely from source code.

## Native branch bitmap cross-check

Dispatcher scope: `ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher`.
Compiled branch checksum1558979345; raw width1215. Native spec25 checksum
3771491581 and spec24 checksum1445690029 are retained in each evidence point.

| Raw / spec / vector | Bound compiled leaf or arm | Single-test hit |
| --- | --- | --- |
| 142 /25 /987 |5720 snapshot entry;5728 vs2 choice;5746 not gather | yes |
| 141 /25 /988 |5751 nonzero reshuffle request | yes |
| 158 /25 /971 |5642 widen-overlap snapshot gate false | yes |
| 159 /25 /970 |5642 same gate true | yes |
| 76 /24 /41 |1505 source-capture ready handshake | yes |
| 74 /24 /43 |1512 source-wait drain complete | yes |
| 96 /24 /21 |1364 OVERLAP_CAPTURE not-ready arm | no |
| 97 /24 /20 |1364 OVERLAP_CAPTURE ready arm | no |
| 127 /25 /1002 |5843 `VL <= overlap_start_element` false path | no |

Native vector IDs are not expression indexes. For example, entry5720 has path
index1236, while target5843 has true index1259/false index1260. The1270-character
path uses one-based LSB indexing: character offset `1270-index`. The raw hit
integer instead uses bit `1215-1-raw`. The diagnostic retains entire paths,
expressions, parent indexes and native spec checksums, including don't-care `-`.

These hit bits accumulate the whole software test. They do NOT establish
cycle ordering or uniquely assign every hit to sequence43. Both true and false
arms at5642 hit, which is compatible with the pre-/post-capture re-decodes but
does not prove that ordering from the bitmap alone.

## Why the VL129 idea did not reach5843

The original arithmetic `129 > (12-8)*(128/4) =128` is correct, but it is
downstream of a different routing decision:

1. Source5435 computes `widen_accumulator_layout_conflict` before destination request
  suppression. MAC reads old vd; its narrow vs2 aliases the destination high
  group, so preserving the readable narrow view takes priority at5720.
2. Snapshot capture retains vs2. At5463, a valid matching narrow source snapshot
  makes `source_snapshot_resolves_widen` true on later decode.
3. Source5479's `source_snapshot_replays_wide_vd` exception does not apply to this
  `.vx` shape: no vector vs1 and vs2=v12 differs from vd=v8.
4. Therefore `!source_snapshot_resolves_widen || source_snapshot_replays_wide_vd`
  is false.5642 no longer suppresses destination normalization;5751 can normalize
  the old accumulator, then5753 skips overlap repair and directly issues MAC.
5. Source5843 is nested below5753 and5829. Merely crossing128 does not force its false
  arm to execute. This test validates the snapshot-resolution route, not the
  assumed overlap-prefix boundary route.

This is source-plus-observed-uop inference, NOT sampled internal state.

## Limits and reachability disposition

No direct probe exists here for `state_q`, `ara_req.op`, EEW valid/tag notebook,
`source_snapshot_valid_q`, either resolve/replay predicate or branch cycle.
We cannot report exact state residency or measured predicate values per cycle.

Raw127 remains **NOT PROVEN UNREACHABLE**. No parameter constant disables this
branch, and initialized-vstart0 snapshot routing is not a global proof.
The source's active masks explicitly depend on vstart: with VL129/vstart128,
the same group geometry makes only destination v12 active and only narrow
source v14 active. A legal metadata prestate with v12 wide/v14 narrow can remove
the snapshot conflict while retaining the full-group high-overlap classification.
This is a source-level countermodel to an unconditional unreachability claim,
not a prepared stimulus or measured hit; actual prestate production and all
other gates would need separate verification. Invalid EEW tags and other
read-modify-write instruction families also cannot be dismissed by this run.

No new stimulus, simulation, exclusion EL, native waiver capture, configuration
unreachability claim or admission is authorized by this document.
