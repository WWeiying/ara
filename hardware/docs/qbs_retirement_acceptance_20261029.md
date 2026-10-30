# QBS final-dot retirement: SoC acceptance

## Decision

Retain the integer-engine final-dot retirement change in the verification
branch. Local numerical/fault gates and the two fresh SoC runs pass. The
measured improvement is small and reproducible, not a large new acceleration.
No main-worktree merge, synthesis, PPA or full-model speedup is implied.

The change registers completion while consuming the final valid dot result,
rather than waiting an additional empty-pipeline cycle. Arithmetic, context
release, correction draining and result backpressure remain unchanged. See
`verification/qbs/tile_boundary/RETIRE_CANDIDATE.md` for the local gates and
the explicit gap-3 fault-overlap test precondition.

## Matched projection result

Identical ELF SHA256:
`ef66be1e29bae12c63dd780b296bec441a348e6c608bdb2202daa8ca64556a60`.
The full-output Q/V/K slice has K=1536, N=1536/256/256 and four input rows.
Its four ABBA trials issue 256 QBS commands and return 131072 result bytes.
These timings include the slice SDK path but exclude intervening GGML graph
operations and complete model execution.

| Software path | Old RTL mean cycles | New RTL mean cycles | Speedup | Cycle reduction |
| --- | ---: | ---: | ---: | ---: |
| Original group sums | 582799.5 | 579791.5 | 1.005188x | 0.516129% |
| Parallel group sums | 550864 | 547856 | 1.005490x | 0.546051% |

Every trial saves exactly 3008 cycles in the execution phase. Preparation and
admission cycles are identical per corresponding trial, as are cache counts
(two hits, one miss, one store), FCSR=17 and VCSR=5. All trials report zero
numerical errors. Execution-phase means change from 478183.5 to 475175.5 for
original sums and 477909 to 474901 for parallel sums.

Across both changes, old RTL/original sums to new RTL/parallel sums is
582799.5 / 547856 = 1.063782x, or 5.995801% fewer cycles. This is the combined
benefit of these two recent changes on this slice, not the original QBS versus
ordinary-RVV acceleration and not model throughput.

The independent SoC checker matches 42354 requests/responses, 34062 backend
allocations/completions, 28997 completed AXI reads and 2112 matched write
bursts/responses. Final outstanding counts and protocol errors are zero.
Source and image identity checks pass before/after execution.

## Ordinary RVV and Attention non-regression

The unchanged three-way Attention ELF also passes. Its six corresponding
trials have exactly identical cycles before and after the RTL change:

| Path | Trial cycles, old and new |
| --- | --- |
| Ordinary RVV | 245497, 245088 |
| Generic native Attention | 81047, 80523 |
| Paired native Attention | 58341, 58310 |

All 3864 hardware records match. Checks cover the original 512 finite/tolerance
outputs, exact repeat/native-pair checks and cross-image checksums/FCSR/VCSR;
this is not a cross-image full output dump or universal RVV correctness proof.

## Evidence and reproduction

Paths below are relative to `verification/out/`:

- Baseline projection: `m4-sums-qkv-vcs-20261029-01/result.json`.
- Candidate projection: `qbs-retire-projection-vcs-20261029-01/result.json`.
- Ordinary regression: `qbs-retire-ordinary-vcs-20261029-01/result.json`.
- Baseline image: `canonical-shared-resources-build-20261025-02/result.json`.
- Candidate admission: `qbs-retire-soc-build-20261029-01/reviewed-admission.json`.

The original candidate build worker remains FAIL because of canonical filelist
ordering, not compilation failure. Its separate admission proves equivalent
effective source/configuration and absence of conflicting included headers;
the original result is not overwritten. See `tile_boundary/SOC_ADMISSION.md`.

```sh
python3 verification/qbs/tile_boundary/compare_projection.py \
  --baseline-run verification/out/m4-sums-qkv-vcs-20261029-01/result.json \
  --candidate-run verification/out/qbs-retire-projection-vcs-20261029-01/result.json \
  --baseline-build verification/out/canonical-shared-resources-build-20261025-02/result.json \
  --candidate-build verification/out/qbs-retire-soc-build-20261029-01/reviewed-admission.json
```

Baseline/candidate run-record SHA256 respectively:
`7e91adb371f8e126b7d978ae240534c4ac838c3ee634b1ae700e7623007d902f`,
`45d88a5028f810ddd4c416950399f3adc57cc04c1a37ed94d08890586f100674`.

Next, measure runtime call-layer overhead on the fixed accepted image before
further optimization. The audit in `software_call_overhead_audit_20261029.md`
identifies possible costs, not measured bottlenecks. Do not enlarge compute
resources or remove cache-validity checks on the strength of this result.
