# Frozen coverage build: splitting and compiler optimization evaluation

Measured on 2026-09-27 in the validation worktree. These experiments do not
change RTL, the active coverage image, or the queued coverage replay.

## Results

| Experiment | Observation | Decision |
| --- | --- | --- |
| `--output-split 10000 --output-split-cfuncs 2000` | Largest measured function: 525515 to 523498 lines; 26 candidate functions still exceed 100000 lines | Stop after generation/measurement; do not compile candidate |
| Isolated large translation unit with C++ `-O1` | External systemd 1800-second limit expired; no completed object | No demonstrated speedup; do not replace active build |
| Isolated small translation unit with C++ `-O1` | PCH and object completed in 41.44 seconds combined | Compilation smoke only, not whole-image correctness or speed evidence |

The split candidate generated successfully in 1741.411 seconds. Total
generation and size inspection took 2006.859 seconds. Its terminal status is
`SPLIT_INSUFFICIENT`; no make or simulation was started. The largest function
shrunk by only approximately 0.38 percent.

## Why smaller thresholds were insufficient

The local Verilator already defaults to output splitting. Its scheduling
splitter moves top-level statements to separate functions, which does not
guarantee decomposition inside a single large nested statement. Consequently,
changing the threshold is not proof that the expensive compilation units
became small. Generated function sizes, rather than option names, govern the
decision to proceed.

The 30-minute O1 result is a censored measurement: it proves only that this
task did not finish within its limit. It does not prove O1 is slower than O3,
and gives no simulation throughput measurement. The recorded service memory
peak is a cgroup statistic, not compiler peak RSS.

## Evidence

- `verification/out/coverage-split-o1-20260927-01/status.json`: source check,
  commands, timing, original/candidate function counts, and stop decision.
- The same directory contains generated function inventories, build log,
  frozen source manifest, and the candidate script snapshot.
- `verification/out/o1-unit-eval-20260927-01/task-233/status.json`: external
  timeout, systemd identity, and preserved log hashes.
- `verification/out/o1-unit-eval-20260927-01/task-0/status.json`: small-unit
  completion and object hash.

## Operating policy

Retain the original frozen build and its automatic PASS-case replay queue.
Once built, reuse that image for stimulus additions without regenerating RTL.
Do not merge coverage from experimental images into the frozen-image results.
Any later compiler/tool change needs an isolated build, representative
correctness replay, and measured compile-plus-simulation cost before adoption.
Do not repeat these two parameter experiments without a new hypothesis.
