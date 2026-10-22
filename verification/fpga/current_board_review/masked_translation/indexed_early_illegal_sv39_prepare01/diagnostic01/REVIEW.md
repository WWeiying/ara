# M7 Indexed Misalignment: Measured Orphan MMU Request

## Finding

The proposed MMU arbitration root cause is confirmed for this fixture. This is
not an SLDU/global-idle/CSR-read stall: the first handler scalar load cannot
leave the LSU bypass queue after an abandoned accelerator translation request.
No RTL, image, original fixture, or original TIMEOUT evidence was changed.

## One Bounded Capture

- Same M7 image, private ELF, seed=1 and runtime testcase as the original run.
- simv PID 1963062; actual child exit 0 after explicit UCLI quit at 85000ns;
  127.219361s elapsed, no host timeout. This exit is NOT architectural PASS.
- Dump created at 79000ns, disabled/flushed at 83000ns. No force/deposit/build.
- 28 explicit signal selections plus LSU parent scope depth 2; 647 exported
  fields including actual `lsu_i.genblk3.mmu_state_q/d`. FSDB 1.7MiB.
- 4000 pre-rising-edge samples; measured `time_ns = cycle_q + 15.5` throughout.
- Input pins verified before and after. Original and diagnostic commit CSVs
  are byte-identical, SHA256
  `6b221db8c53c60ab35fa9096fdade9fa701353ccd87d70a59bdcbfb3d0a852bd`.

## Cycle Evidence

All cycle numbers below use the real commit-monitor counter sampled before the
clock edge; `cycles.csv` retains the corresponding absolute nanoseconds.

| Cycle | Observation |
|---|---|
| 79691 | Aligned prefix address 0x40000008 receives translation_valid=1; ACC q=1/d=0. |
| 79692 | Address 0x40000011: idx_op_error_d=1, mmu_req_o=1, mmu_valid_i=0. MMU q=CVA6/d=ACC, scalar lsu_valid_i=0/ready=1; actual translation_req=0. |
| 79693 | AddrGen AXI FSM IDLE, mmu_req_o=0; arbiter q=ACC/d=ACC, translation_req=0/translation_valid=0. Exception valid, cause=6, tval=0x40000011. |
| 79697/79698/79703 | Sole Ara prefix AW/WLAST/B handshakes, physical address 0x80003008, B response OKAY. |
| 79704/79705 | VSTU store_complete pulse, then issue_cnt/commit_cnt/pending_B all zero and store_pending=0. |
| 79706/79707/79713 | ara_idle=1; lane exception flush pulse; flush_done=1. |
| 79726 | Last retired instruction PC 0x80000bfc computes mt_trap_count address. Next PC 0x80000c00 is `ld t1,0(t0)`, before any handler CSR read. |
| 79735/79736 | Scalar LSU accepts address 0x80008078, then bypass count=1/nonempty. Load-unit valid=0, load-unit state IDLE, translation request=0. |
| Through 82984 | ACC remains locked for 3292 sampled cycles. The scalar load remains buffered for 3249 cycles; Ara stays idle with no pending stores or invalidation. |

The prefix completes normally and there is no second Ara AW/W/B for the bad
element, on either side of the fixed AXI delayer. The CPU AXI window contains
earlier traffic and begins with transactions already in flight; its aggregate
AW/B counts must not be interpreted as an outstanding-count invariant.

## Static Causal Connection

Paths below are relative to the immutable M7 `frozen/sources/` tree:

- `hardware/src/vlsu/addrgen.sv:1117`: indexed misalignment raises the local
  error and leaves the AXI request state. The subsequent translation block at
  1172 still sets mmu_req_d; line 761 exposes it combinationally when valid=0.
- `hardware/deps/cva6/core/load_store_unit.sv:439`: CVA6 locks to ACC on that
  request. Lines 455 and 469 only forward requests after entering ACC and only
  release on translation_valid. Here the request has already disappeared.
- Same file line 479 masks lsu_ctrl.valid in ACC; line 634 feeds that valid to
  the load unit. `lsu_bypass.sv:60,74,113` explains the measured nonempty queue.

The shallow scope dump exported MMU state, bypass count/empty, LD address and
LD valid, but not the packed lsu_ctrl/lsu_ctrl_byp or accelerator request/response
structs. Their exact valid-field gating is source-derived, NOT claimed as an
independent direct waveform observation. Ara mmu_req_o/mmu_valid_i and the actual
LSU translation request/response were measured directly.

## Scope And Repair Boundary

Suppress the translation request for the locally rejected indexed address;
retain the cause6/vstart and prefix-drain/flush behavior. Production repair and
its subsequent controls remain the main thread's responsibility. This capture
does not validate a repair, complete the fixture, or identify the original16
Linux failure root. Original 900s TIMEOUT and killed-child rc255 remain intact.

Evidence: `invocation.json`, `complete.json`, `diagnostic.fsdb`, `analysis.json`,
`cycles.csv`, and `checked_evidence.json`. Offline decode/check exits are actual
zero; neither script reruns simulation or reference execution.
