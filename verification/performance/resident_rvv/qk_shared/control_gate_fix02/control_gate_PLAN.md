# Stage3 Central Ownership Gate

Status: parent-authorized successor to preserved failed runs _01 and _02.
Retains the _01 poison-literal correction and its host regression. Corrects the
_02 test-only barrier assumption to exactly one waiting cycle for QK T1, since
the only active lane satisfies the complete barrier on its first result edge.
Multi-lane barrier >=2, final-debt hold >=12 and nonzero stalls are unchanged.
Diagnostics now print the case and counters. No scenarios, production files,
functional invariants or unexplained thresholds changed. This successor has
the same 43 cases and is not yet frozen, compiled, or executed.

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
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage3_control_gate_20261110_03`.
Pin original and copied inputs, the two contract documents, accepted dependency
provenance, compiler, source list and runner. Snapshot the engine for static
audit only. Check pre/post source and image identities. Fail closed on missing,
duplicated, reordered or inconsistent work receipts and simulator diagnostics.
Preserve first failure and stop; later fixes require fresh output directories.
Bound compilation at 240 seconds, simulation at 60 seconds, each case at 12000
cycles and the entire bench at 500000 cycles. Long-running launch, if needed,
must put the worker itself directly under a transient systemd service.

## Counter Re-Audit Before Run 03

| Case | Expectation and source-level justification |
| --- | --- |
| Successful QK T1, H1 or H2 | Exactly one barrier-hold sample. The sole lane waits 12 cycles after the last accepted payload, so reader completion is already latched. Group Barrier transitions to Commit on the first result-valid edge, independent of ready. H2 increases results, not active lanes. |
| Successful multi-lane QK/PV | Barrier hold >=2: the last active lane delays first result by 12 cycles while others delay by 2. Grant skew is at most one cycle; T17 lane 0's extra final packet cannot remove that gap. |
| Every successful case | Each lane's final ack is scheduled 28+lane cycles after its last result acceptance; done follows acceptance. The debt monitor samples before consuming a due ack, retaining >=12 cycles after all active done handshakes. No final-grant-as-result conflation. |
| Backpressure | Per-lane grant is low every fifth cycle. D64 or longer QK and the PV baseline each deliver many ordered payloads; nonzero stalled-payload sampling remains mandatory. Result stability is checked separately through the barrier and grant stalls. |
| Prelaunch QK abort/invalid base/context/RM | No launch, seed, Q/K/V request, result or ack. Cancel aliases import-done, so nonzero seed limits cannot deadlock Drain. Poison source valid remains asserted and every source-ready bit must stay zero. |
| Early-invalid PV / PV seed abort | Import starts at command acceptance even when context validation fails. Discard consumes 24 words from each lane, exactly 96. Early invalid has zero seeds/reads/results. Seed abort must interrupt a positive but incomplete seed count. |
| QK seed abort | First accepted seeds trigger abort before either head's complete Q-read sequence and K launch. No K-busy count is expected. Results and acks stay zero. |
| QK K-busy abort | T64 starts a nine-cycle collector (eight groups + capture). Stub abort-done appears only after observing abort, with no artificial FPU delay. All four done handshakes precede collector drain, requiring busy_hold >0 and abort_busy >=3. Lease remains held throughout. |
| QK precommit abort | Wait for all accepted payloads and some but not all first results. Abort preempts the last active lane's 12-cycle result delay. Full successful private-work counts, zero architectural results/acks, positive barrier wait. |
| Recovery | Each negative case is followed by T1/H1 QK and T3/H1 PV. The same source, payload, result, flags, lease and ack oracles apply; no counters are waived for recovery. |

The per-case 12000-cycle and global 500000-cycle bounds, simulator diagnostic
rejection, exact case ledger and pre/post identity checks remain unchanged.
