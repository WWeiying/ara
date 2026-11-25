# Stage3 Central Ownership Gate

Status: plan acknowledged; files pending parent review. Not frozen, compiled,
or executed. The test has 43 cases, including ten negative cases followed by
both QK and PV recovery.

## Static Findings

- The production controller instantiates the real group, import, reader and
  fanout. QK skips source import and seeds each active lane with zero; PV must
  drain 24 source words per lane, including cancelled commands.
- QK lane activity is `lane < T`, not `T <= lane_count`. Each active lane gets
  `ceil(ceil((T-lane)/4)/2) * H` seeds and results. The last K packet has its own
  lane mask; T17 must not deliver that packet to lanes 1 through 3.
- Commit requires successful import and reader completion plus every active
  lane's first held result. Normal done before results is a protocol error.
  Architectural result acceptance and final VRF acknowledgement are distinct.
- The reader's CancelDrain waits for the non-cancellable K collector. Central
  Drain independently checks `!column_busy_i`. The engine also gates command
  admission with `!v2_column_busy`, but is not instantiated here.
- The active stage3 reader worker's source-pins include production control,
  reader, fanout, engine and reader_gate helper/test inputs. None are edited.
  Its pins contain no inherited Markdown inputs. The separate active DC
  worker is outside this task; it is neither invoked nor changed.

## Composition And Oracles

Instantiate only production control/group/import/reader/fanout, using selected
accepted package SHA identities via read-only reader_gate.py source_selection.
Use independent frozen copies, including a uniquely named infrastructure copy.
Retain all RTL assertions; no force/release of DUT internals, fake completion,
SYNTHESIS define, arithmetic model, full SoC, URG, DC, ZCC or Verilator.

The test drives only public interfaces. Stub lanes check every accepted zero
seed / tagged PV seed / tagged coefficient / shuffled K or V word. They hold
tagged result data, slot and byte enables until architectural handshakes after
the complete active-lane barrier. Normal done follows all results; error done
follows an observed lane_abort. Inactive lanes never provide result or done.
The memory model has synchronous one-cycle Q/V responses and an eight-token
group K gather followed by final capture; a gather ignores abort until drained.
This is control/transport evidence, NOT arithmetic, real SRAM, engine, native
FPU coexistence, full architectural integration, performance or board evidence.

## Cases And Assertions

- QK T1/2/3/17/64 x H1/2 at D64, plus D96/T17/H2 and D128/T64/H2.
  Valid bases include 3 and the last fitting row; invalid nonzero bases test
  resident-row overflow and physical-row overflow. Invalid context and rounding
  admission are separate recoverable failures. Early-invalid PV context still
  requires all 96 source words; prelaunch QK cancel must terminate with no seeds.
- PV baseline before QK; QK and PV recovery after every negative case.
- Abort before launch, during seeds, during K busy, before commit, and during
  PV source import. No post-commit abort is a recoverable test.
- Independent source/payload/result/ack counters; stable stalled beats; inactive
  masking; no QK source acceptance even with poison source valids asserted;
  ordered read addresses; held barrier; delayed final acknowledgement;
  no release/terminal/admission while debt or column busy remains.
- The K-busy case requires all active lanes to finish abort before K drain,
  then observes positive lease-held cycles. A terminal-only test is insufficient.

## Review And Freeze

Parent review precedes freeze and execution. Freeze copies selected inputs to
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage3_control_gate_20261110_01`.
Pin original and copied inputs, the two contract documents, accepted dependency
provenance, compiler, source list and runner. Snapshot the engine for static
audit only. Check pre/post source and image identities. Fail closed on missing,
duplicated, reordered or inconsistent work receipts and simulator diagnostics.
Preserve first failure and stop; later fixes require fresh output directories.
Bound compilation at 240 seconds, simulation at 60 seconds, each case at 12000
cycles and the entire bench at 500000 cycles. Long-running launch, if needed,
must put the worker itself directly under a transient systemd service.
