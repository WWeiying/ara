# E8/M8 Timeout: Static Finding and Proposed Single Scan

Status: TIMEOUT; COST_VS_STALL_UNDETERMINED. No recovery eligibility, no DUT
acceptance, no new simulation, no full trace scan performed. E16/M8 observer untouched.

Paths below are relative to `arithmetic_restart_original/` unless absolute.

## Actual Terminal Evidence

- `full_e8_m8_block_vcs_m9_plan01/prepared01/replay/tests/arithmetic_original_e8_m8_full4095_block/child_outcome.unvalidated.json`:
  actual returncode255, elapsed10800.112584460061s, timed_out=true,
  failure_seen=false, cancelled=false. Absence of a failure marker is not success.
- `prepared01/complete.json` is NOT_PASS, Sticky abort; row CANCELLED.
  `service_exit.json` records exit-code/exited/1; collector NOT_ACCEPTED.
  The generic cancellation wording does not replace the numeric timeout cause.
  `pins_unchanged=false` on this aborted path is not itself a measured pin-drift diagnosis.
- `m8_terminal_observers01/e8_m8/terminal_notice.json` independently retained those
  receipts and observed original worker pidfd exit. This is not an owner-checker recovery.
- Numeric receipt SHA256:
  `65184b8a60434d46587caa99536e9cd4a9ffbd2750a83d83895f61d5d0111659`.

## Actual ELF and Tail Loop

Private `input.elf` and `full_e8_m8_block_unrolled01/soc/program.elf` both freshly
hash to `847bdfe2e4d261225c06df8de0de2535af60500f272e725d91f42f1900da0c67`.
The private ELF PT_LOAD bytes at 0x80000b2a match the frozen disassembly:
`1063210790e39386818ca107e39ad7fe`.

`case.c` calls `initialize_mask(mask,mode)` outside the per-start trial loop.
`packed.h:140-141` copies sixteen 8-byte words from `physical_masks[mode]`.
The actual inlined loop is:

| PC | Instruction | Meaning |
| --- | --- | --- |
| 80000b2a | 6310, ld a2,0(a4) | Next mask ROM word |
| 80000b2c | 0721, addi a4,a4,8 | Advance source |
| 80000b2e | e390, sd a2,0(a5) | Mask buffer word |
| 80000b30 | 8c818693, addi a3,gp,-1848 | End pointer = out |
| 80000b34 | 07a1, addi a5,a5,8 | Advance destination |
| 80000b36 | fed79ae3, bne a5,a3,b2a | Stop after 128 bytes |

Actual symbols: physical_masks=80002080, mask=8005f058, out=8005f0d8,
gp=8005f810. The destination interval is [mask,out); source800020f0 is
physical_masks+112, mode0 word index14, and its actual ELF value is all ones.
Mode0's first word is supplied by `li a2,-1`; then 15 LD iterations follow.
This is a finite scalar initialization loop, not a vector wait instruction.
That static property alone does not prove correct dynamic traversal or total progress.

Parent's bounded CSV observation: last visible order1793563/cycle21859382,
including the load of word14 after a preceding store at mask+104.
This review did not reread the CSV. It read only the final five lines of each
existing hart log. `work/trace_hart_0.log` additionally records:

```
21859397ns 21859382 ... PC80000b2a ld a2,[800020f0] -> ffffffffffffffff
21859397ns 21859382 ... PC80000b2c a4 -> 800020f8
21859399ns 21859384 ... PC80000b2e sd ffffffffffffffff,[8005f0c8]
21859399ns 21859384 ... PC80000b30 a3 -> 8005f0d8
```

Thus another tracer has word14's store, with word15 still unobserved. These are
two log frontiers, not contradictory whole-run outcomes. Do not promote either
frontier to the final simulator cycle, or invent the next source tuple from it.

## Timing and Flush Limits

Frozen M9 `hardware/tb/ara_commit_monitor.sv:72-77` enables watchdog only for a
nonzero COMMIT_WATCHDOG plusarg. Actual command has COMMIT_TRACE and NO_FSDB,
but no COMMIT_WATCHDOG. At lines303-308, fflush is guarded by
`progress && watchdog_en`: this explicit progress-flush path was disabled.
The final block closes the file but records no final cycle. Automatic buffering
and shutdown writes remain possible; mtime near timeout cannot establish liveness.

`run.vcs.log` (1579 bytes) and `console.log` (1269 bytes) contain startup only:
no final simulation time/cycle or successful finish. Existing startup_observation
records only the initial ~5.1s CPU/file-size increase; it is not a three-hour
wall-time series. The event attachment records worker identity, not simulator
progress. No final-cycle or late wall-time/cycle checkpoint was found in these
small existing receipts/logs. Hart tracer source records only commit/exception
events; its last timestamp is also only the last visible event.

Full reference firmware2825046 and the old ~403.97 firmware/s planning proxy
explain the prior estimate, not this timeout. Last observed retire count divided
by elapsed wall time mixes boot/trace conventions, possible stalls and host
throughput; it cannot prove remaining runtime or justify a larger timeout.

## Recoverable Progress Fields

- Source completed-call counter `checks` at8005f050: only business increment
  store at PC80000da6, with s5 increased at80000da4. Distinguish startup zeroing.
  This counts source checks performed, not necessarily successful checks.
- `errors` at8005f040 and `elements` at8005f048 distinguish source failures and
  full-cap checking progress. No claim of numerical acceptance without full oracle.
- Helper call at80000d78/jalr s1; exact op-helper entry/13-PC window and arguments
  a0..a6 recover operation, VL, capacity1024, mask and vstart. Match against the
  sealed 4095-entry sequence, not retire-count proportions. A new mode0 maskcopy
  may be at a new VL/op/seed boundary; tail alone does not identify which one.
- Actual helper return and completed-check store distinguish last entered target,
  last returned helper, and last fully checked source call.
- CVX/arch/uop events expose front request/response and backend ownership. Frozen
  monitor `arch_start` means req_valid first seen, NOT accepted handshake;
  `cvx_req` requires req_valid&&req_ready, `cvx_resp` resp_valid&&resp_ready.
  Uop identity is arch order + VID + trans_id + instruction, with VID reuse tracked.

## Proposed One-Pass Closed Analysis (NOT EXECUTED)

Subject to parent authorization: one process, <=180s, <=512MiB, one forward read
of the existing 220110178-byte CSV. No semantic rerun of full oracle, no new DUT,
no automatic retries. Record actual process wait result; pre/post inode/size/mtime;
compute CSV SHA256 during that same pass. Pin source/spec/ELF/probe/receipts.
Bound output to a small progress ledger and at most32 detailed gap windows.

1. Validate header, complete rows, monotonic cycle/retire order, actual PC/code
   for selected source landmarks; preserve incomplete final line as truncation.
2. Recover checks/errors/elements writes and each helper entry/return's args,
   including exact source ordinal/tuple from the immutable sequence. Report last
   entered, returned, checked calls and current finite-loop coordinate separately.
3. Collect per-million-simulation-cycle counts and top32 gaps between retires and
   between any real handshake/completion/retire progress. A same-cycle multi-port
   retirement is legal. Track request/response and uop lifetimes, outstanding
   ownership at every large gap and EOF; do not count arch_start as acceptance.
4. Record longest completed-target latencies by op/VL, observed scalar-init/check
   intervals, maskcopy pointer bounds/16-store traversal, and EOF pending owners.
   Reuse sealed protocol semantics, with an explicit incomplete-run result rather
   than demanding normal terminal/full4095 totals or applying the known VI2 bug.

Falsifiable outcomes:

- Repeated valid source-boundary advancement, finite maskcopy traversals and no
  dominating internal cycle gap support distributed execution cost *over the
  recorded interval*. They still cannot rule out an unlogged terminal stall.
- A large gap bracketed by later events with a persistent accepted owner localizes
  a real long hardware wait in simulated cycles, not necessarily deadlock.
- Repeated maskcopy PC/pointer states without counter/call advancement falsify the
  simple finite-source-progress explanation and require data/control analysis.
- Unfinished accepted owner at EOF identifies a pending candidate, not a proven
  stall duration: without a final simulator-time endpoint, tail censoring remains.
- If no final-time evidence exists, retain COST_VS_STALL_UNDETERMINED regardless
  of file mtime or active-looking tail. A scan cannot recover missing wall-time
  checkpoints. No architectural PASS or timeout increase follows from this plan.

## Small Input Identities

- program.dis: b2dae912131172637dcbf013e18f45a2f39a2970f64df57ac14bcbe60dfd12d9
- case.c: 3df39c33da95232e86edaa6e4e184fed6bfa3618a1a1cedfd0dcfb7df274be37
- packed.h: f3323f6db3d9c4a24296722315941f89457932f1bbafbafe131fc25f0c503157
- sequence.json: 5898b8e0931be22c6fedaadd4f8bc3aadcc2ebf1b3f6f3693c1f216fde298f35
- symbols.json: 96d9fcc161cd40132973c2598f2155e62b9c4457d98c7caeafec6cd04791c257

All original files/limits and e16 observer remain unchanged. Only this new
analysis note was created; no full CSV/reference parse or large-file hash performed.
