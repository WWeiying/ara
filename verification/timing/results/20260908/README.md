# Timing port validation, 2026-09-08

Baseline: `b07e194deb4bc8cc88cc26cb1266893b9e92612d`.
The candidate changes only `simd_alu`, `qbs_fp_accumulator`, and
`qbs_profile_engine_int`. No additional pipeline stages or queue changes.

| Check | Result |
| --- | --- |
| Integer range proofs | 3 tests PASS, covering all 9 profiles |
| QBS profile engine with bound reference RTL | 448 cases PASS |
| QBS end-to-end engine with bound reference RTL | 33 functional cases and 4 fault classes PASS |
| Activation context FILL/REUSE/RELEASE | PASS |
| Engine before/after cycle comparison | All 33 deltas are zero |
| ALU exhaustive/random comparison | 9,877,184 checks PASS |
| ALU wider-SEW directed boundaries | 22,528 checks PASS |
| Full-top RVV/QBS/AKV handoff | RVV plus 4 QBS and 10 AKV commands PASS; traps=0 |
| VCS engine test with SYNTHESIS defined | 33 functional cases and 4 fault classes PASS |

`engine_cycles.csv` contains measured cycles, not an area or frequency estimate.
`summary.json` records RTL hashes, original log locations, and test scope.
The full-top run preceded only the addition of an `ifndef SYNTHESIS` guard
around an existing assertion. Its default VCS behavior is unchanged; the final
guarded source was also checked with `SYNTHESIS` defined.

Reproduce the unit tests from the project root:

```sh
make -C verification/timing check BUILD=/tmp/ara_timing_recheck RUN_TIMEOUT=600
```

The equivalence check compares observable cycle-level behavior, not only final
numerical output. It is simulation coverage, not a formal equivalence proof.
The independent ALU model also checks arithmetic and saturation.

No DC, place-and-route, FPGA implementation or power analysis was run.
The 9,736 removed declared payload bits do not imply 9,736 fewer mapped flops:
synthesis may already share some of the original redundant state.
