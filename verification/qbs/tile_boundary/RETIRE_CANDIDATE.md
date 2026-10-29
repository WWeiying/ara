# Last-dot retirement candidate

## Exact change

`retire_candidate.sv` is a test-only copy of the current integer engine.
It adds a completion alternative: issue and s0 are empty, only the final dot
metadata stage is valid, dot data is valid, and that result belongs to the
current compute context. On that edge the existing dot accumulation still
executes; compute-active clears and done registers concurrently. No new start
is allowed on that same edge. On the next edge dot data and metadata are empty.
An added assertion checks this property when done is observed.

No context-valid clearing, correction handling, result-ready rule, narrow-tail
guard, dot latency or arithmetic is changed. This is not two simultaneous
integer-tile issues or a replacement of final context release by input release.
Bank changes remain under the original parent's done-driven FSM.

## Local VCS evidence

The baseline and candidate were compiled independently using the same engine
Makefile, standalone composition generator and testbench. `candidate.mk`
substitutes only the integer-engine source in the compile inventory. Production
RTL files are unchanged. The generator's `generation.json` describes the
canonical composition, not a claim that its production integer module was used;
the VCS compile log records the actual candidate replacement.

| Run | Functional cases | Response gap | Additional checks |
| --- | ---: | ---: | --- |
| Baseline `baseline-full.log` | 36 | 0 | Four atomic fault classes, context lifecycle, next-block fault/reset replay |
| Candidate `candidate.log` | 36 | 0 | Same checks, plus bounded boundary probe |
| Candidate `candidate-gap3.log` | 36 | 3 | Same checks with spaced read responses |

All three logs pass the independent existing
`run_tile_context_engine.check_log(text,36,1,gap)` parser. Its context count is
one for this vector set; this does not claim capacity-wide context coverage.
Four fault classes are validation, MMU, AXI and PMA. The numerical suite also
includes M>4 tail waves and all nine supported profiles, but the bounded probe
does not itself cover every tail or profile.

For gap=0, per-case configuration tuples match exactly. Of 36 cases, 34 are
faster and two unchanged; none slower. Summed case cycles are 30667 baseline
and 30179 candidate (1.59% reduction). This sum is a diagnostic collection of
different shapes, not a workload-weighted benchmark or model performance.
No matched gap=3 baseline performance comparison is claimed.

The first observed boundary changes from last-read/done/start/new-read offsets
0/6/7/8 to 0/5/6/7. The old context remains live, and correction is still in
flight. Thus the measured one-cycle saving matches the intended completion
change without premature context release in the observed windows.

Evidence under `verification/out/`:

- Baseline build: `qbs-tile-boundary-build-20261029-01`.
- Candidate build: `qbs-retire-boundary-build-20261029-01`.
- Baseline log SHA256: `fb77599edc64eb12c94f576aaadbf2c7431f2b0824d1042f8c5e3ed2d349501e`.
- Candidate log SHA256: `431de651dc1b77a466e7aa683f653ec1bbd79915d278e149ccf9a1f3c6bf59a8`.
- Candidate gap3 log SHA256: `5258d60b3ec2b290dee63ee09b96eae5287236d679aff7b6a6e3ff28f251aeba`.

## Remaining gate

Do not promote solely on these cases. Run capacity-bound context combinations
and directed small-M subgroup-16 tails with result pressure, reset and faults.
Then compile a fresh canonical SoC image, revalidate ordinary RVV/coexistence
and compare the same real projection binary against the baseline image. Any
hardware performance claim must come from that matched pair. No synthesis,
timing or area improvement is established here.
