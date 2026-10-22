# Next Reachable Control Gaps: Frozen Old Image / Raw714

## Measured Follow-Up: Raw715

The proposal below is retained as the pre-experiment analysis, not a statement
that all proposed guards work. The latest admitted base is now Raw715,
`gap100-offline-admitted-715-20261006-01`, with independently verified raw DVE
report `raw715-dve-20261006-01`.

GAP101 measured proposal 2 once. Case A correctly trapped; case B did not trap
and wrote the initialized v31/v0 bytes into the guarded target. The frozen store
decoder places the source register in `ara_req.vs1`, while the proposed overflow
guard reads `ara_req.vd`, whose store default is zero. Thus the assumption below
that v31 selects that guard was disproved. This is an old-image correctness
failure, not a reason to waive the guard or admit the failing test. The complete
failed test/VDB remains excluded and the evidence is sealed in
`gap101-register-overflow-failure-sealed-20261006-01.json`.

The independent GAP101A test checks case A only, with full trap, VRF, guarded
memory and legal recovery checks. Its host/Spike preflight passes 539 checks;
it has not yet earned RTL coverage admission. It does not close case B.
System proposals 1 and 3 remain timing hypotheses requiring raw-bit or
cycle-level witnesses, not guaranteed coverage increments.

### Cache Stimulus Review Before RTL Execution

The first cache preflight uses leaf slots 1/2 and 33/34. The RVV CVA6
configuration declares a 256-bit (32-byte) D-cache line, and the SoC configuration
function does not override that width. Two adjacent 8-byte PTEs in either pair
therefore share a cacheline: translation of the first instruction page can warm
the PTE needed for the second page. Software/Spike success does not establish
the intended refill collision. Before the bounded RTL experiment, qualify the
configuration against the frozen build pins and move each PTE pair across a
cacheline boundary. Preserve the previous preflight, build a new ELF, and run
its independent Spike reference. Even with this correction, require a measured
replay witness; do not assume page crossing necessarily causes replay.

The successor `cache-port1-sv39-preflight-715-20261006-04` now uses slots
3/4 and 35/36. Parent-side replay of all evidence pins, the independent Spike
oracle and linked geometry passed; all 11 preflight unit tests passed. The
reference contains 35 checks, 160 exact output bytes and two S-mode ECALL
records. Both PTE pairs cross 32-byte lines. This proves the corrected layout
and architectural reference, not that the second PTE is cold at runtime or that
RTL replay occurred. The bounded old-image test and target-bit admission remain
pending.

The bounded RTL execution has now completed with software SUCCESS. Independent
comparison matched 12335 non-trap instructions, 4015 GPR writes and 2062 scalar
memory accesses, with no unobservable values skipped. Both expected S-mode
ECALL trap rows are present. All five proposed replay targets remain zero;
the measured union gain is four condition points (three in the cache-memory
arbiter and one in port1 control), with no new FSM point. This disproves the
claim that this stimulus necessarily observes replay, but not its reachability.
The result is a functional coverage candidate, not a replay witness.

Do not infer that page-table initialization stores warm both PTE cachelines:
`wt_dcache_mem` gives its single-word write port no tag access and enables
valid/tag writes through `wr_cl_vld_i`. A store's presence alone does not prove
line allocation. The timing relationship between PTW refill and scalar READ
still needs direct evidence before another replay experiment is selected.

Static implementation proposals, not coverage claims or exclusion approval.
No simulation, DVE, URG, RTL edit, or admission was performed for this note.
The deterministic dispatcher test is ready for implementation. The two system
tests have legal source-level routes but require measured timing witnesses;
their exact hit sets are not guaranteed by static analysis.

## Evidence and Coordinate Contract

Base: `verification/out/closure92-offline-admitted-714-20261006-01`.
Its status is `PASS_RAW_UNION_HISTORICAL_ONLY`, with 714 distinct VDB paths.
This is not an official714 DVE denominator or aggregate signoff. The six707
application report is not used as this baseline.

SHA256 of inputs read for this analysis:

| Input | SHA256 |
| --- | --- |
| Base `status.json` | `81446c068c86b089d890875c497e890a70309187f950ccd19dc6d64660866f32` |
| Base `combined-bits.json` | `8e8fce1608bd494461df24d28f9c12f18179cd16dca2e38efc58a386623d0b58` |
| Old `build-source-pins.json` | `6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b` |
| Old `shape/fsm.verilog.shape.xml` | `39eec846a15994d7e7e196025d5b215a11474af4e9b4de19afb2d25223c485fc` |
| Old `shape/branch.verilog.shape.xml` | `d4b0187fe173ee56dc958538c16639ac1f41c42e4cf46daea07a4e759f13c74e` |
| Old `shape/line.verilog.shape.xml` | `70d031cd99b85e25904d30aab3cc71d4876b5d311d94deee8df07d9b331a9e15` |

Build directory: `verification/out/repaired-aligned-build-20260930-01`;
design database: `sim/simv.vdb/snps/coverage/db`. All five base design pins
were compared with actual database bytes and matched. For width W, raw index i
is hit iff `int(bits,16) & (1 << (W-1-i))` is nonzero. Branch coordinates use
`closure_point_inventory.points`: vectors reverse within each branch_spec.
FSM coordinates enumerate states then transitions for each fsmfsm in shape
order. FSM names/IDs below are compiled-shape diagnostics, not DVE-native EL
bindings. No XML raw offset is to be promoted to a native exclusion ID.

Scope abbreviations:

* D = `ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher`.
* C = `ara_tb.dut.i_ara_soc.i_system.i_ariane.gen_cache_wt.i_cache_subsystem.i_wt_dcache`.
* P = `ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_ptw`.

## 1. Cache: Scalar Read Replay Against Instruction PTW Refill

Priority: first system experiment; one short Sv39 test, not a value scan.

Exact primary targets at `C.gen_rd_ports[1].genblk1.i_wt_dcache_ctrl`:

| Metric / definition checksum | Raw | Exact identity | Raw714 |
| --- | --- | --- | --- |
| FSM / `3476102610` | 6 | state REPLAY_READ, ID6 | zero |
| FSM / `3476102610` | 7 | state REPLAY_REQ, ID7 | zero |
| FSM / `3476102610` | 21 | READ(ID5) -> REPLAY_REQ(ID7) | zero |
| FSM / `3476102610` | 27 | REPLAY_REQ(ID7) -> REPLAY_READ(ID6) | zero |
| branch / `3466602542` | 36 | spec7, vector4, spec checksum `2091678112` | zero |

The branch is the true `wr_cl_vld_i || !rd_ack_q` path at wt_dcache_ctrl.sv:167,
under READ/REPLAY_READ and valid tag. FSM width28 bits=`0xdcc5780`.
Secondary targets at port0 have the same zero raw6/7/21/27, but are not promised.

Source route: cva6.sv:1397-1401 connects port0 to LSU/PTW and port1 to scalar
loads. wt_dcache.sv:204-244 instantiates both controllers and shares refill
`wr_cl_vld`. wt_dcache_missunit.sv:406/429 asserts that signal on load response
and cacheline installation. wt_dcache_mem.sv:181 suppresses read grants during
refill. READ therefore legally enters REPLAY_REQ on a refill/read collision,
then enters REPLAY_READ on a later read grant.

Stimulus recipe:

1. Reuse the proven Sv39 setup/restore harness, with cacheable DRAM mappings.
   Keep the current instruction page and a small data set warm. Map the next
   instruction page but leave its I-TLB entry cold; use a separate lower-level
   page-table cacheline not warmed by the data setup.
2. Link a straight-line block across the 4KiB instruction-page boundary. Put
   eight independent scalar `ld` instructions at the end of the first page,
   reading different already-warm data cachelines. Frontend lookahead into the
   second page supplies an instruction PTW while those loads execute.
3. Follow with a small ordinary `sd`/`ld` readback block and one SFENCE/re-entry
   phase using a second cold instruction page. Do not fence between each load:
   that would serialize away the intended conflict. Do not assume FENCE.I
   flushes D-cache; its behavior depends on frozen DcacheFlushOnFence.

Discriminating witness: same-cycle valid scalar READ tag and
`wr_cl_vld_i || !rd_ack_q`, followed by REPLAY_REQ -> REPLAY_READ and one correct
load completion. If ordinary loads complete but no witness occurs, record a
functional PASS with target-not-observed, not a coverage success. No blind
seed/timeout or RTL-delay changes. A focused existing trace/FSDB window may be
used by the implementing parent if supported by the frozen image.

Independent oracle: exact scalar loaded values and post-store bytes against a
separate host reference; guard bytes and non-target memory unchanged; no
unexpected traps; exact CSR restore; Spike architectural comparison. Hardware
request/completion conservation must additionally exclude duplicate replay
responses. Spike alone cannot prove cache replay occurred.

Nonduplication: raw714 contains warm-permission, superpage/SFENCE and ordinary
RVV memory tests; relevant port1 replay states remain zero. The source of
`system_gap30_cache.c` performs bulk store, fence, bulk read, fence, rather than
this instruction-translation/data-read overlap. That current software source
is contextual evidence, not a claim of a newly verified historical source seal.

Budget estimate: 3-8 minutes old-image VCS, timeout600; Spike normally seconds.
Estimate only, not a measurement of this proposed test.

## 2. Dispatcher: Two Isolated Illegal Segment-Store Boundaries

Priority: highest confidence increment; legal architectural trap tests with
deliberately illegal store operands. This is not an assertion that the rejected
instructions themselves are legal. No backend memory fault injection.

| Metric / definition checksum at D | Raw | Exact identity | Raw714 |
| --- | --- | --- | --- |
| branch / `1558979345` | 345 | spec25 vector784; spec checksum `3771491581`; line4541 NF*EMUL>8 true | zero |
| line / `1316526434` | 1334 | native BB1326, file547, line4542, checksum `4136722710` | zero |
| branch / `1558979345` | 343 | spec25 vector786; same spec checksum; line4543 vd+register_count>32 true | zero |
| line / `1316526434` | 1337 | native BB1329, file547, line4545, checksum `2466644338` | zero |

Use the sealed OLD dispatcher, not current hardware/src/ara_dispatcher.sv.
Its `segment_register_count=(nf+1)*lmul_register_count(emul)` and store decoder
at lines4525-4545 give two independently selectable guards:

* A: e8,m2,VL1, vstart0, unmasked `vsseg8e8.v v16,(a0)`.
  NF8*EMUL2=16>8, while v16+16=32 does not exceed32. With base in a0,
  the 32-bit encoding is `0xe2050827`.
* B: e8,m1,VL1, vstart0, unmasked `vsseg2e8.v v31,(a0)`.
  NF2*EMUL1=2<=8, but v31+2=33>32. Encoding `0x22050fa7`.

Use raw words if the assembler rejects invalid register groupings. Verify ELF
instruction bytes and decoded nf/vm/width/rs1/vs3 independently. Allocate a
valid writable guarded DRAM target so mcause cannot be confused with an address
fault. Keep VL nonzero, so zero-length suppression cannot mask the guard.

Oracle: exactly two illegal-instruction traps (mcause2), exact mepc for each
word, Spike-matched architectural trap metadata, zero target/guard changes,
all VRF bits unchanged by rejected operations, vstart/VL/vtype unchanged as
architecturally applicable. The trap handler's first explicit memory operation
must be a scalar store to a ledger; this detects phantom pending-store state.
After each trap, issue a legal small segment store and scalar readback to prove
recovery. Separate host packing checks those bytes. Track legal-store writes
separately from the rejected words; rejected words must launch no VLSU store.

Existing raw714 membership includes `villegal_segment_recovery` (illegal load)
and `vsegment_emul_edges` (valid field spacing). Neither substitutes for these
two zero store-specific guards. Do not claim new segment FSM transitions:
the sequencer's only remaining raw5/raw8 arcs go from MICRO_OPS/WAIT_END to
IDLE; its source has no normal direct edges for them. Its sole missing branch
raw44 is the ARA_DEBUG_SEGMENT logging path, not useful functional coverage.

Budget estimate: 2-4 minutes old-image VCS, timeout600; one ELF/two trap phases.

## 3. PTW: SFENCE Commit While a Younger Instruction Walk Is Pending

Priority: exploratory short control test after 1/2; native FSM remains HOLD.

Exact diagnostic targets at P, width35, definition checksum `3345966803`,
raw714 bits=`0x6fe2b9c00`:

* raw21: state_q WAIT_GRANT(ID5) -> LATENCY(ID1), zero.
* raw25: state_q WAIT_RVALID(ID6) -> LATENCY(ID1), zero.
* state_q-specific checksum is `3090985924`; do not confuse it with the module
  definition checksum or ptw_stage_q checksum.

Actual cva6_ptw.sv:608-610 guard, not an abbreviated state-only rule:

```systemverilog
if (flush_i)
  if (((state_q inside {PTE_LOOKUP, WAIT_RVALID}) && !data_rvalid_q) ||
      ((state_q == WAIT_GRANT) && req_port_i.data_gnt))
    state_d = WAIT_RVALID;
  else state_d = LATENCY;
```

Thus raw21 needs WAIT_GRANT with no grant; raw25 needs WAIT_RVALID with buffered
response valid. Waiting alone is insufficient. Ordinary branch misprediction
only asserts flush_if/unissued, not flush_ex: do NOT use it as a PTW flush oracle.
SFENCE.VMA in controller.sv:230-237 does assert flush_ex, propagated through
cva6 -> ex_stage -> load_store_unit -> cva6_mmu -> ptw.flush_i.

Stimulus: a privileged, valid Sv39 page-boundary block containing SFENCE.VMA
near the end of a warm instruction page and a cold mapped next page. A preceding
cache-missing scalar load delays retirement while frontend fetch can initiate
the younger next-page walk. SFENCE retirement flushes that walk. A second fixed
layout can shorten the delay to target buffered response/flush coincidence;
do not sweep random seeds. It is a legal overlap hypothesis, not proven timing.

Oracle: no unexpected fault, correct continuation signature and CSR restore,
no retirement from discarded speculative fetch, exact Spike result. In addition
record flush_ex reaching ptw.flush_i, state_q, data_gnt, data_rvalid_q and state_d
in the same cycle. Without the exact guard witness or raw delta, keep the
target-not-observed result. Native identity is pending: no EL/application.

Nonduplication: existing Sv39/SFENCE cases primarily validate translation and
permissions. The targets above are still zero in714; this specifically overlaps
a committing fence with speculative instruction walking. Do not stimulate or
waive PMP0 raw2/10/11/16, RVH-disabled raw26-34, or conservatively enumerated
direct-to-IDLE raw12/14/20 on this evidence.

Budget estimate: 3-8 minutes, timeout600, one ELF with at most two fixed phases.

## Old Source Pins Actually Checked

All hashes below matched the historical build-source-pins manifest above.
Paths are relative to repository root unless stated otherwise.

| Source | SHA256 |
| --- | --- |
| hardware/src/ara_dispatcher.sv, read from verification/out/old-image-source-evidence-20261006-01/ara_dispatcher.sv | `9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43` |
| hardware/src/segment_sequencer.sv | `672ddcdfafc3fb40206e9b28c9c4e5d67d40dc9fae18e577cff9c5dc586d4452` |
| hardware/deps/cva6/core/cache_subsystem/wt_dcache_ctrl.sv | `d2a8a3207ce394d9e703a8dea514759d14ce9995091c0e88c8dbf3b291861e51` |
| hardware/deps/cva6/core/cache_subsystem/wt_dcache.sv | `f48178cfb5c958f90b47a6b5e20a654e5488e18986e173aac68eb41137bb5b96` |
| hardware/deps/cva6/core/cache_subsystem/wt_dcache_mem.sv | `e0f1b81f9ce7b4f8358deb13daa501aa04219562db94ae1a8b5d20a484865097` |
| hardware/deps/cva6/core/cache_subsystem/wt_dcache_missunit.sv | `f7aed679ebd9fe990b88f064b8a9200be9b5f7c83277d10c7bc0af147cbedf64` |
| hardware/deps/cva6/core/load_unit.sv | `042db6cbcfdba16f6810a49de010eeb52105829e444a348df5fc7ec89f3ac7dd` |
| hardware/deps/cva6/core/cva6.sv | `e108b9d62b51102f83fdfcfbe0f64cf9ff8588226cb600933803827efbee8378` |
| hardware/deps/cva6/core/controller.sv | `d9c9cc1dea0c2a4aa2be29093b0466f11f7c28c0717825e8b16418d181b44b5c` |
| hardware/deps/cva6/core/ex_stage.sv | `8e909ca497423abffa449c8e3213ffa08bd5fa501bd88600985d3f3bcf25bfd3` |
| hardware/deps/cva6/core/load_store_unit.sv | `88ceed6bd3794272145bda9a19c4e6844242a690cc539e36b7dc23a08163d8a8` |
| hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv | `4859d957d56541c27928e347cee7ef800486cf3b1ad91aa53a9e3e044344c480` |
| hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv | `82dab3584098056cff37c18e3070875b0b71ba185e90fd878151fc197c0d9505` |

Port2 tie-off proof belongs to the parallel owner and is not duplicated here.
Low adapter/AXI-shim percentages alone do not establish software reachability.
Most dispatcher remaining FSM arcs are shared post-case overrides; no blanket
proposal is made for those. Only independently PASS cases with measured raw
deltas may enter a future union; failures and no-increment runs remain separate.
