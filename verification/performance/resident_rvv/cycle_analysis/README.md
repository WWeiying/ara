# Resident execution: evidence and design gates

This is a successor analysis, not an edit to the sealed probe worker. It does
not drive RTL, change arithmetic, or claim a new speedup. The active goal is
still resident-data execution on shared RVV arithmetic, conditional on measured
benefit. Bus widths, memory interfaces, lane count and arithmetic resources are
fixed; synthesis is out of scope.

## Reproducible observations

`pv_schedule.py` checks the accepted trace hashes and complete instruction
lifetimes before analyzing both auto calls. Its frozen reference is the same
Qwen3 D128/H2/T137 ABBA experiment documented in the parent directory. The two
calls each contain three PV helpers, with 64, 64 and 9 rows.

Evidence: `verification/out/resident_pv_schedule_20261108_01.json` in the
signoff-integration worktree.

| Observation | First auto call | Second auto call |
| --- | ---: | ---: |
| Row replay commands | 137 | 137 |
| Intra-tile row-to-row intervals | 134 | 134 |
| Every observed row allocation interval | 45 cycles | 45 cycles |
| Every row replay allocation-to-completion interval | 26 cycles | 26 cycles |
| Next row allocation minus previous row's last FMA completion | 1 cycle | 1 cycle |
| First FMA allocated before its row replay completes | 137/137 | 137/137 |

These are allocation/completion events, not FPU input handshakes. One example
from the first full tile is:

| Instruction | Allocated | Completed |
| --- | ---: | ---: |
| V row 0 into v8:v9 | 141948 | 141974 |
| Head 0 FMA reading v8:v9 | 141953 | 141984 |
| Head 1 FMA reading v8:v9 | 141964 | 141992 |
| V row 1 into v8:v9 | 141993 | 142019 |

The main and frozen versions of `ara_sequencer.sv`, `operand_requester.sv`,
`vmfpu.sv`, `vlsu.sv` and `akv_engine.sv` were hash-equal during this audit.
The frozen source hashes remain in the probe worker's `source-pins.json`.

## What the RTL already does

1. `akv_engine.sv` asserts `command_early_ack_o` for an admitted resident row or
   column load. `vlsu.sv` propagates that through `addrgen_ack_o`. The CPU need
   not wait for the entire replay before submitting the following FMA.
2. Replay writes use the existing load-unit result path. Each word tracks lane
   acceptance separately from final VRF grants; the next word follows those
   confirmations. The replay counter is not a pure bank-conflict counter.
3. Each PV row has two FMA readers of v8:v9. The next row overwrites that group.
   `ara_sequencer.sv` retains all readers in its WAR mask. It blocks multiple
   readers at entry, and blocks operand-free writers while hazards remain.
   Lane-local source-lifetime release does not make this entry check disappear.
4. `vmfpu.sv` requires the selected operand queues before accepting a SIMD beat.
   Accumulator dependencies remain real dependencies, even if the V operand is
   served directly from resident storage. Group/latency guards also preserve
   result order and must not be removed as a performance shortcut.

The 45-cycle recurrence is consistent with the reused-destination dependency
gate. It does not establish that all 45 cycles are unnecessary, or that FMA
arithmetic is idle throughout. There is already producer/consumer overlap.

## Questions the cycle probe must answer

`analyze.py` requires the passive replay to match the accepted ELF's timings,
outputs, instruction work, source pins and independent protocol checks. It
then joins FPU input acceptance to the live vector instruction ID. It reports:

- FPU input/output handshakes, separately from queued instructions;
- unavailable source and accumulator operands, latency gates and backpressure;
- replay requests denied versus final-write confirmation waits;
- context-bank conflicts, AXI handshakes, and complete-call phase windows.

Input acceptance per lane-cycle is not pipeline occupancy. Missing-operand,
latency and backpressure observations can overlap and must not be added into
a stall pie chart. FMA element counts must agree with the original dimensions
and masks before being used as useful-operation throughput.

## Selecting a bounded implementation

Do not add a new command merely because replay uses VRF. First distinguish:

| Candidate | Question it answers | Main limit |
| --- | --- | --- |
| Rotate two existing V destination groups in a diagnostic helper | How much is caused by reusing v8:v9? | Does not eliminate replay or accumulator traffic |
| Pipeline existing resident replay | Is the per-word completion protocol the main limiter? | Must preserve ordered final-grant ownership and fault/drain behavior |
| Bounded resident-PV execution using the existing FPU | Do command supply and VRF round trips justify a shared-arithmetic controller? | Needs explicit coefficient delivery, ownership and completion rules |

The first is a discriminating control, not a hardware innovation. If it removes
most of the loss, compare any hardware proposal against it rather than an
artificially weaker baseline. The second is useful only if the cycle evidence
identifies replay pacing as significant. Neither observation alone establishes
that the third is worthwhile.

Before implementing resident-PV, settle these contracts:

- Keep FP16 probability conversion and token-ordered FP16 FMA identical to the
  accepted helper. QK subsequently retains dimension-ordered FP32 widened FMA.
- Deliver coefficients explicitly. The persistent Q store is not free scratch:
  replacing it with probabilities would damage the next QK tile unless restored.
- Reserve the entire accumulator register footprint through the ordinary
  scoreboard. A local accumulator must have defined initialization, writeback,
  flag propagation and drain behavior; no hidden state may survive an ownership
  change unintentionally.
- Use existing arithmetic with explicit arbitration and result tags. A data mux
  alone does not establish instruction ownership, exception precision or safe
  coexistence with ordinary RVV/QBS operations.
- Validate the resident view and shape before side effects. Preserve release,
  refill, fallback, invalid-command and fault behavior.
- Count preparation, command submission, conversion and final drain in the
  comparison. Report a local phase speedup separately from full-call speedup.

PV is the first implementation gate; QK and runtime integration follow only
after bit-exact correctness and repeatable full-call benefit. Check D64/D96/D128,
single/paired heads, full/tail tiles and relevant CSR/ownership boundaries.
If the evidence rejects the benefit hypothesis, retain the measurements rather
than force an area-increasing mechanism into the design.

## Commands

Run the local checker tests without a simulator:

```sh
python3 -B -m unittest discover \
  -s verification/performance/resident_rvv/cycle_analysis -p 'test_*.py' -v
```

`pv_schedule.py` takes `--evidence`, `--build` and a new `--output` path.
`analyze.py` additionally takes `--profile`; it refuses an unfinished or
unaccepted passive replay. Neither tool overwrites an existing output file.
