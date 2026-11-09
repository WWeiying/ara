# Resident PV Source Import Transport Gate

This host-VCS gate connects the prototype importer directly to **four real,
unmodified production operand_queue instances**, selected from frozen
`chain_soc_20261107_01/source` using accepted `resident_pv_vmfpu_20261108_04`
source pins. It is separate from the context-FP gate and makes no numerical,
SoC, performance, synthesis, or FPGA acceptance claim.

## Queue And Layout Contract

- StA configuration: DataBufDepth=2, FPUSupportNone, NrLanes=4, VLEN=1024,
  CmdBufDepth=VstuInsnQueueDepth+MaskuInsnQueueDepth=5, NrSlaves=1.
  AccessCmdPop=1 exposes completion for observation.
- The command type is checked against the exact packed declaration in frozen
  lane.sv, including ntr_red, is_reduct, and target_fu. Source command: EW16,
  elem_count=96 per lane, OpQueueConversionNone, non-reduction, target_fu=ALU_SLDU
  (the target field is unused on the production StA interface).
- Six registers provide exactly 24 64-bit source words per lane. Sixteen seed
  words precede eight coefficient groups. Each head reserves eight seed words;
  D64/96/128 uses 4/6/8 of these, for H1/H2. Inactive seeds are consumed but must
  not appear at the seed interface. Each coefficient group contains eight
  interleaved 32-bit token pairs, including both head halfwords even for H1.
- Queue heads retain a coefficient group until its last active pair is accepted.
  The importer has no payload storage. The bench checks stable queue heads and
  coefficient output under backpressure and no early group pop.
- The independent raw-bit oracle starts with natural halfwords. A physical
  lane word contains natural offsets lane+{0,8,4,12}, low to high. Expected
  coefficient pairs are consecutive natural halfwords after the seed region;
  no DUT helper or internal DUT state is used in the oracle.

## Admission And Ownership

**FP completion is not source completion.** For short T, unused coefficient
groups can remain in StA after the last active pair and even after fast FP
completion. The parent must include error-free import source_done in permission
for irreversible commit. It must retain exclusive ownership until import/drain,
FP completion, and final acknowledgements have all completed. Cancellation must
drain all 24 owned words per lane without flushing the following command.

Invalid configurations are rejected before queue mutation: the harness issues
no queue command and no operand request for them, and asserts that the importer
does not request queue data or deliver seeds/coefficients.

## Checks

The 170-case run includes the full D64/96/128 x H1/H2 x T1/8/9/63/64 matrix
in unstalled, deterministic-stall, and reproducibly randomized-stall modes.
Lane request times are unequal. Returns occur exactly one cycle after credited
issue. Seed order, inactive suppression, coefficient pair raw bits, credit
bounds, and source/sentinel counts are checked independently at each edge.

Cancellation during seeds, coefficients, and remaining drain is tested for all
D/H configurations. Every cancellation is immediately followed by a successful
reuse without reset/flush. All cases hold completion for six cycles while
attempting a new start. Valid and cancelled cases each consume exactly 24 source
words and pop one source command per lane. An ordinary EW16, four-element
sentinel command follows in each real command FIFO and must return exactly one
unchanged word and one command pop per lane. It is consumed independently while
import completion remains held, before acknowledging completion and reusing.

Expected totals: 108 good, 18 cancelled, 44 invalid; 12,096 source words,
504 source command pops, 504 intact sentinel words, and 12,600 one-cycle returns.
The parser rejects missing/duplicate receipts, malformed fields, incorrect
counts, missing protocol coverage, and simulator assertion/error diagnostics.

## Execution And Provenance

Run unit tests and static review before launching a fresh gate:

```sh
cd verification/performance/resident_rvv/pv_import
python3 -B -m unittest -v test_run.py
python3 -B run.py /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_import_AGENT_UNIQUE
```

Use a transient systemd service that directly owns `run.py` for an independent
worker; capture its stdout/stderr separately and confirm the actual VCS process.
The runner bounds tests, compilation, and execution to a shared 540-second
budget. `--prepare-only` snapshots/checks sources without claiming execution.
Output directories must be new children of signoff `verification/out`.

The minimal selected closure includes pinned fifo_v3, lzc, and the common_cells
assertion header. Only the snapshot include directory reaches the compiler.
The inherited COMMON_CELLS_ASSERTS_OFF define is preserved; explicit bench and
importer assertions remain enabled, with independent queue/credit checks.
The conditional UVM include is inactive and UVM/assertion-disabling configuration
changes are rejected. TARGET_VERILATOR is omitted; no Verilator or URG is run.

Local sources, documentation, runner/tests, selected frozen sources, header,
lane/stage contracts, admitted file list, and accepted manifest/report are pinned.
Compiler inputs are copied snapshots. Source and image identity are rechecked
after execution. Closed logs and snapshots enter report artifacts; live service
logs never do. Preserve every failed run unchanged. Do not edit pinned local
files while a consumer runs. The parent owns akv_resident_pv_import.sv; source
issues require a concrete hypothesis and review before any RTL edit.
