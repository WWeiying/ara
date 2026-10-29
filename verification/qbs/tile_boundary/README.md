# Bounded integer-tile boundary observation

`probe.sv` binds observation-only logic to `qbs_compute_engine`. It prints at
most eight 16-cycle windows, starting near an integer tile's final input reads.
All samples are pre-NBA posedge observations. No production RTL is edited.
The fixed limit means narrow M1/M2 subgroup-16 tail coverage is not guaranteed.

Completed local run:
`verification/out/qbs-tile-boundary-build-20261029-01/boundary.log`.
The unchanged numerical suite reports 36/36 functional cases. It was launched
with `QBS_FUNCTIONAL_ONLY`, so this is not the suite's atomic-fault campaign or
an end-to-end CPU/UVM acceptance result. It took 11.42 simulator CPU seconds;
VCS compile CPU was approximately 48 seconds. No whole-model simulation was
needed to obtain these boundary observations.

Four complete observed boundaries cover M=1 and M=4. Relative to the old
tile's final SRAM read:

| Offset | Observed event |
| ---: | --- |
| 0 | Final input read |
| 1 | s0 still valid; no new input read |
| 2..4 | Remaining dot metadata/data in flight |
| 5 | Integer pipeline empty, compute still active |
| 6 | Integer done; old context still live |
| 7 | New tile starts on other bank; correction still pending |
| 8 | New tile first input read; both contexts can be live |

This proves the current boundary gap and pre-existing correction overlap. It
does not prove safety of issuing new input earlier. In particular, freeing
the old context at input completion is contradicted by its observed lifetime.
The live decoder's profile, M, row count and per-context metadata must remain
aligned until the old s0 decode finishes; bank switching before that edge is
not justified by the last-read timestamp alone.

Log SHA256: `46f86d8bc4f598c7389bd655168aa15eae0b926cfab07ed256d445c740db66cc`.
Image SHA256: `7145af9026a790ca716f8d9c678133e9b88adcf81423371f9e4c96cff280874d`.
`analyze.py <log>` verifies completion, all 36 case IDs, bounded-window cycle
continuity and observed old/new events. It explicitly reports that narrow-tail
coverage and early-overlap safety remain unproven.

Rebuild in a fresh directory from the repository root:

```sh
make -C verification/qbs rtl-engine-compile \
  RTL_ENGINE_BUILD=/absolute/fresh/build \
  RTL_EXTRA_SOURCES="$PWD/verification/qbs/tile_boundary/probe.sv"
```

Run the resulting image from its own build directory with
`-no_save -l boundary.log +QBS_TILE_BOUNDARY_TRACE +QBS_FUNCTIONAL_ONLY`
and `+QBS_COMMAND_VECTOR_FILE=<absolute qbs_command_vectors.txt>`.
Preserve generation.json, compile log and input identities with any new run.
Do not treat an existing local executable as matching modified RTL without
rebuilding and checking its source inventory.
