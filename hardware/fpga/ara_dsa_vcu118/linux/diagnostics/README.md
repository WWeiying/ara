# Vector discard investigation, 2026-09-28

This directory contains diagnostics and an ALU fix with mapped and partial
board validation. Full Linux board acceptance remains pending.

## Main-RTL integrated board investigation (2026-10-02)

The finalized main-RTL bitstream has SHA256
`b97f0aaab964d4f6a0a5b89f06d522dcbe6bfed364eb448e3bf1bd9d2ed2c7b5`.
Evidence: `D:/fpga_runs/ara_mainrtl_board_20261002`. The original reviewed
Image and full rootfs were loaded with readback verification: 30,029,982
payload bytes in 3.0700672 s (9.781539 MB/s). Linux again reached `Run /init`
but did not reach the init marker within 180 s. This is not Linux acceptance.

Two nonfreezing snapshots have retired=1460184595, last/head PCs
`ffffffff80015e92`/`ffffffff80015e94`, trap_count=171435, and last trap
cause=8. Cycles advanced from 10543271226 to 11062032290 while DDR counters
were unchanged; DDR response errors and outstanding transactions were zero.
The actual Image instruction at the head PC is `02070807`, `vle8.v v16,(a4)`.
This matches a previous stopping location, not an established root cause.
`fpga_head_pc_o` observes `commit_instr_pc[0]`; it does not establish whether
Ara accepted that instruction or whether its memory requests were issued.

### Configuration capture is not a validated observation path

Vivado 2020.1 `readback_hw_device -capture` returned success on xcvu9p and
produced `readback_probe/capture.bin`. However, the subsequent debug snapshot
reported status=4 instead of 7: clock locked remained asserted, while fabric
ready and SoC reset release were deasserted. Retired/PC/trap values remained
the same, but the snapshot sequence advanced from 6 to 8 and the old counter
values cannot establish preservation of the running core. The debug block
also snapshots/freezes its counters when SoC reset asserts.

Consequently, do NOT treat this capture (or the second capture already
launched before that comparison) as a trustworthy dump of the original
stalled backend. The capture operation is associated with a board-state
change; its exact low-level mechanism has not been established. No explicit
reset/program command was part of the capture script. The clocks were not
stopped, so the documented capture conditions were not satisfied either.
Successful tool return is not sufficient validation. The independent
location-table export was cancelled, and the original bitstream/Linux flow
was relaunched under `D:/fpga_runs/ara_mainrtl_board_recovered_20261002`.
No functional RTL was changed for this investigation.

Recovery completed with the same bitstream and input hashes: DDR calibration
and Ethernet initialization passed again. Linux still did not reach its init
marker. The recovered run's commit head is now `ffffffff80b8857c`, last retired
PC `ffffffff80b8857a`, retired=1459281173. This is another copy of the same
four-load restore sequence; its third load is again `02070807`.
`resident_text_verified/report.json` records two single-beat reads of the
256-byte window at physical `0x80d88530`. Both reads match the reviewed Image
byte-for-byte. Core retirement and trap counts remained unchanged; status was
7 before and after. DDR AR increased by exactly 64 and R bytes by 512,
accounting for the diagnostic reads, with zero response errors/outstanding
transactions. This rules out a mismatch in that resident code window, not
data corruption elsewhere or stale instruction-cache contents in general.

The recovered run's last recorded trap is cause 2, tval `c0102573` (`rdtime
a0`), at `ffffffff80907a2c`. A historical trap is not proof of a terminal
illegal-vector-instruction fault. The different restore site means this is
not established as the same dynamic invocation as the initial run.
The board was left in this recovered diagnostic state, not reset afterward.

The next causal observation must distinguish: request not accepted (CVA6
dispatch/ready state), Ara issue blocked (running IDs, queue credits and
dependency table), address generation/MMU waiting (request/valid/ack and
AXI AR handshake), and load completion blocked (VLDU result occupancy,
per-lane final grants and completion ID). Capture those together with the
commit-head PC and request transaction ID. Neither DDR-idle nor an isolated
queue unit-test pass discriminates these alternatives.

### Read-only observation inventory

`D:/fpga_runs/ara_stall_inventory_20261002/state.json` reports
`complete_read_only`. The routed DCP SHA256 was checked before and after:
`7884b794a6c41de283c5e4af00202e6268704cf70136fa7a3d09a33a58a16d8e`.
`inventory_stall_observation.tcl` opened that checkpoint and enumerated seven
unique modules (CVA6 accelerator dispatcher, Ara dispatcher/sequencer,
AddrGen, VLDU, scalar LSU and LSU bypass). No design modification, hardware
connection, synthesis, placement, routing or programming was performed.
Opening the full routed checkpoint alone took about ten minutes; it was not
a new implementation run. Reports were copied to
`/tmp/ara_stall_inventory_20261002`.

`plan_stall_observation.py` resolves an ordered, bounded candidate profile
from those TSV files. The real inventory resolves 460 candidate signal bits;
four requested consumer pins have no connected net: AddrGen `mmu_dtlb_hit_i`
and VLDU `axi_r_i[last]`/`axi_r_i[resp][1:0]`. These are NOT zero-valued
observations or demonstrated hardware defects. Optimized/unused consumer
ports must be traced to their live producers when needed. In particular,
the accelerator dispatcher's commit-PC consumer pins are disconnected; the
commit head must be taken from the producer or existing debug input instead.

The candidate manifest deliberately says `insertion_ready=false` and
`hardware_capture=false`. Complete per-PE running IDs, AddrGen state Q pins,
producer PC, clock domains and synthesized-checkpoint bindings remain to be
resolved. Named mapped nets alone do not prove RTL register semantics or
FSM encoding. Six resolver tests cover missing/disconnected pins, duplicate
instances, bit ordering and scope mismatch; they validate the diagnostic
tool, not the processor.

The matching synthesized DCP is available at
`D:/fpga_runs/ara_mainrtl_20260930/runs/synth_3d28a8eb257a/ara_dsa_vcu118.dcp`.
The intended observation-only route is to insert ILA into a copy of that
synthesized design and use the verified routed checkpoint as a physical
reference. This can avoid another main-RTL synthesis, but still requires
implementation, existing release gates and reproduced board failure before
any new capture is evidence. At this initial inventory stage no insertion or
build had been launched; the subsequent preparation is recorded below.
See AMD UG908, [non-project debug insertion](https://docs.amd.com/r/2020.2-English/ug908-vivado-programming-debugging/Debug-Core-Insertion-in-Non-Project-Mode?contentId=r56H2rD~xqlWqhDX06zjUQ)
and [incremental debug changes](https://docs.amd.com/r/2024.1-English/ug908-vivado-programming-debugging/Current-Design?contentId=Mz6FBAO9L4tOJok4K0R7ww).

### Synthesized observation bindings

The subsequent inventory in `D:/fpga_runs/ara_stall_synth_inventory_20261002`
pins the raw synthesized DCP SHA256 to
`28998c0c59ee7fa6880508caef119c6eb7b5841e577baf36ea2b98b324712fdb`.
It adds the existing debug module and VLSU, and records primitive register
Q connections rather than inferring them from net names. The second profile
resolves 606 logical sources including the capture clock to 579 unique data
nets, with no missing sources. Aliases have explicit logical-to-probe-bit
mapping. Head PC comes from the connected debug input; response valid and
unused VLDU/AddrGen consumer inputs are taken from connected producer or
parent pins. These replacements are not functional fixes.

The raw DCP alone has unlinked external IP and no clocks. Observation
preparation therefore needs the completed project synthesis run and checks
every binding and its 50 MHz clock.
`prepare_stall_ila.tcl` then adds observation logic only to the in-memory
design and writes a separate checkpoint. It contains no placement, routing,
bitstream generation or board-access commands. Preparation was started in
`D:/fpga_runs/ara_stall_ila_prepare_20261002`. That first run validated all 606
logical sources (the returned TSV matches the input table structurally), but
failed because read-only project mode prohibits both the existing CDC script's
debug-clock reconnection and `create_debug_core`. Its result is not usable for
implementation. No observation checkpoint was accepted.

The corrected preparation first opens the frozen project read-only, then uses
`save_project_as` to make a separate editable project retaining run results.
It checks the project location and source/copied synthesis DCP SHA256 before
linking and inserting observations. The new run is
`D:/fpga_runs/ara_stall_ila_prepare_20261002_02`; its state and preparation
marker must establish completion. This tool-flow correction is not evidence
about the Linux stall's cause.

Nine Python resolver tests and the Tcl clock/cardinality helper tests pass.
They are tool tests, not an ILA implementation, hardware capture, root-cause
proof or Linux acceptance. Functional RTL and the current board image remain
unchanged by these inventory and preparation operations.

`implement_stall_ila.tcl` continues from the prepared checkpoint, checks the
579-bit/1024-sample/one-stage observation configuration, runs `opt_design`,
rejects unresolved blackboxes, then uses the original routed DCP only as an
incremental physical reference. It saves optimized, placed and routed
checkpoints and runs the existing full reports and timing gate. It stops at
`timing_passed_requires_full_audit`; it does not generate or program a bitstream.
Its mocked flow tests cover normal command order and rejection of wrong
width, unresolved blackboxes, incomplete routing and timing failure.

`run_stall_ila.ps1` pins the original synthesis/reference hashes and requires
a successful preparation state and exact preparation marker. The independent
Windows launcher PID 26172 was started to wait for preparation PID 13916,
then run this implementation in
`D:/fpga_runs/ara_stall_ila_implementation_20261002`. Launcher output is in
the adjacent `ara_stall_ila_implementation_20261002_launcher.log`. Waiting or
launching is not completion; inspect actual processes, state, stage and
reports before making a completion claim. No new functional RTL synthesis is
requested by this observation pipeline.

Preparation `_02` completed successfully at Windows time
`2026-10-02T09:50:46+08:00`. The marker records `probe_width=579` and
`clock=clk_50_clkwiz`; its linked-source TSV again matches all 606 logical
sources. The prepared checkpoint SHA256 is
`3220d57ad60af8fe18133297fe758d0e227d8ee9d662be4d1edc9e0356bd8152`.
The implementation wrapper accepted the pinned inputs and started Vivado
PID 22760 under wrapper PID 26172. This is an observation implementation,
not another functional RTL synthesis or a board pass. The open-checkpoint
board-catalog warning `Board 49-67` must not be mistaken for a timing result;
the actual routed reports and release audit are still pending.

The first observation implementation was deliberately stopped at optimization
on `2026-10-02T09:58:05+08:00`: `Board 49-67` was followed by
`Constraints 18-638` when DDR board-derived XDC was reapplied, demonstrating
that the missing catalog was not merely cosmetic. This run is failed and
must not supply a release checkpoint. No placement or programming was accepted.
The implementation script now loads the frozen `board_files` repository,
requires exactly one matching board definition, checks checkpoint board/part,
and promotes both missing-board diagnostics to errors before optimization.
Two added mock cases reject a missing board catalog and wrong device part.
The corrected independent run is
`D:/fpga_runs/ara_stall_ila_implementation_20261002_02` (wrapper PID 7188),
using the same prepared checkpoint and original physical reference hashes.
This is a concrete tooling correction, not a functional root-cause hypothesis.

Run `_02` then passed the board-context check and MIG regeneration, but failed
debug IP generation with `IP_Flow 19-3458`: advanced triggering requires
`ALL_PROBE_SAME_MU_CNT` in 2..16, while the prepared observation core had 1.
No placement or board access occurred. Preparation now requests two match
units; implementation explicitly upgrades the existing prepared checkpoint's
debug core from one to two before optimization, retaining the same width,
depth, input pipeline and probe mapping. Unexpected trigger configurations
are rejected. The mock flow verifies the upgrade and invalid-count rejection.
The corrected run is `D:/fpga_runs/ara_stall_ila_implementation_20261002_03`,
wrapper PID 14892. Its input hash is still the original prepared DCP; the
debug-only property adjustment is logged as `OBSERVATION_TRIGGER_CONFIG` and
will be included in the newly written optimized checkpoint. This diagnostic
configuration failure does not explain the processor's Linux stall.

Run `_03` subsequently completed both MIG generation (phase 1 checksum
`1b63fbd5d`) and debug-core generation (phase 2 checksum `13b32537c`), then
entered phase 3 Retarget. This is actual Vivado evidence that the two prior
configuration failure points were passed, not a completed optimization,
placement, route, timing audit or board capture.

Run `_03` finished routing and reports on October 2, but failed the strict
setup gate: WNS -0.009 ns, TNS -0.016 ns, two failing endpoints. Hold had
zero failing endpoints (WHS 0.000 ns); pulse width had zero failures
(WPWS +0.005 ns). Both setup failures originate at MIG read-response FIFO
`i_cdc_fifo_gray_src_r/wptr_q_reg[5]` and terminate at slice 4, word 8,
bits 35 and 62 CE pins. The worst data path is 2.889 ns, including 2.536 ns
routing. This is an observation-build timing failure, not evidence of the
Linux root cause. The routed checkpoint and all reports remain preserved.

The routed DRC summary contains only Warning/Advisory entries. CDC category
counts match the original `audit_cc1ab1094250` report, but detailed reports
include changed representative source endpoints; equal counts are not CDC
signoff. No bitstream or board programming was performed.

`close_stall_ila.ps1` reuses this routed checkpoint and the existing
`close_routed_setup.tcl` physical optimization flow, with immutable-input
hash checks and no functional RTL edits. Closure run `_01` was stopped
during checkpoint loading after Board 49-67 exposed a missing board catalog
setup in that older helper. The helper now sets the frozen board repository,
checks the exact board definition and promotes board/constraint lookup
failures to errors. Replacement run
`D:/fpga_runs/ara_stall_ila_closure_20261002_02` started under wrapper PID
8420 / Vivado PID 2432. This run completed at 15:26 +08:00 on October 2:
post-route critical-path optimization improved WNS from -0.009 to +0.011 ns,
and the final setup/hold/pulse-width gate passed. Its saved routed DCP SHA256
is `b3d9ece26da98419b3337f401b5a435e92d1494efaeec7b23aeb6caaf79d9271`.
No functional RTL was resynthesized.

`audit_stall_ila.ps1` / `.tcl` use the frozen audit helpers and explicit board
catalog, requiring the closure completion marker and recorded DCP hash.
Independent audit `D:/fpga_runs/ara_stall_ila_audit_20261002_01` completed;
reports are in the frozen package's `reports/audit_6a9a20ee1e23` directory.
Setup/hold/pulse-width slack is +0.011/0.000/+0.005 ns. All 972118 routable
nets are fully routed, with zero routing errors. Boundary and constraint
checks report zero failures; the 48 bus-skew summary rows have minimum
slack +2.337 ns. `check_timing.rpt` differs from the original image's
`audit_cc1ab1094250` report only in its header. In particular, the existing
partial-input-delay entries are eth_mdio, jtag_tck_i, jtag_tdi_i,
jtag_tms_i and uart_rx_i; sys_reset has an explicit false path.

CDC category counts are unchanged, but eight CDC-10 representative source
names differ. This is not enough to establish reset connectivity equivalence.
Read-only `inspect_stall_reset.tcl` is comparing bounded upstream reset
cones in original/observation routed checkpoints under
`D:/fpga_runs/ara_stall_reset_review_20261002_01`. `compare_stall_reset.py`
parses those Tcl-list inventories and compares references, initialization
properties and input drivers; it rejects incomplete exports. Five unit
tests pass. Even identical bounded inventories do not prove whole-design
equivalence. Manual CDC review and diagnostic bitstream generation remain
pending; timing closure is not Linux acceptance or full CDC signoff.

Reset inventory collection subsequently completed at 16:50 +08:00. Both
187-cell exports are byte-identical, SHA256
`380eb9738c487c08675b087eacf9e7a260313a3b1351bf08b746e8986b2e46e2`;
the structured comparison finds no changed references/properties/drivers.
This excludes an observed topology change in these bounded reset cones,
not all possible CDC defects. No functional RTL was changed.

Diagnostic bitgen started at 16:54 +08:00 in
`D:/fpga_runs/ara_stall_ila_bitgen_20261002_01`, wrapper PID 23928 and
Vivado PID 20308. `bitgen_stall_ila.ps1` pins the audited DCP and reset
inventories, verifies the frozen package and all reviewed report hashes,
then reuses the existing bitgen helper with explicit board catalog setup.
Live setup/hold, multiple-driver and native bitgen DRC checks remain enabled.
The wrapper does not synthesize, route or program the board. Its output is
explicitly diagnostic-only with CDCSignoff=false and LinuxPassed=false;
Generation completed at 17:21 +08:00, with 0 errors and 0 critical warnings.
BIT length is 80159227 bytes, SHA256
`85a8b32c70d527e374a2fc05033d5e9e1347a87f02884258a698c8dcf4c2ae1c`;
LTX length is 336680 bytes, SHA256
`768d5b834c8e05f2e4ddf15cbe21443c9f416d46ec30d2df137ecee9ab32b074`.

`reproduce_stall_ila.ps1` preserves the prior Linux/firmware hashes and
collects ILA data after execution, including when Linux acceptance times
out. Its initial PowerShell 5.1 JSON-array counting error was corrected
before programming. The following attempt in
`D:/fpga_runs/ara_stall_ila_board_20261002_01` stopped at `get_hw_targets`:
Labtoolstcl 44-199 reported no matching targets. `program_hw_devices` was
not reached. The wrapper's conservative BoardModified=true denotes an
attempted programming stage, not evidence of successful programming.
Windows PnP confirms USB serial 210308A3B79F is absent from present devices,
although the board's COM6/COM7 UART interfaces remain present. JTAG USB
reconnection is required before a new evidence-directory attempt; do not
repeat synthesis or treat this transport failure as the Linux root cause.

### Observation image board reproduction, October 3

JTAG USB returned with PnP status OK. Run
`D:/fpga_runs/ara_stall_ila_board_20261002_02` programmed the diagnostic
BIT/LTX pair, reached BOARD_READY, initialized Ethernet, and transferred
30029982 bytes including readback in 3.071761 seconds (9.776 MB/s).
Original image hashes were retained. Linux reached `Run /init as init
process` at 62.317906 seconds but did not produce the acceptance marker.
The wrapper completed ILA collection without resetting the stopped execution.

Evidence: `capture/capture.csv`, `.vcd`, `.ila`, `linux/report.json`,
`linux/uart.txt`, and a subsequent `snapshot/snapshot.json`. The 1024 ILA
samples have one constant 579-bit raw value. Direct CSV columns show:

* Ara request opcode 0x02070c07 (fourth vector restore load, v24), rs1
  0xffffffd602e10c00, VL=1024, with request valid but not ready.
* AddrGen requests MMU service, but MMU valid and DTLB hit remain zero.
  MMU ownership is CVA6 (mmu_state_q=0); no vector AXI AR is offered.
* LSU bypass occupancy is 2, output valid is 1, ready is 0, and both pop
  signals are 0. No new scalar LSU input request is asserted.
* VLDU has one issue/commit entry with 1024 bytes remaining, no AXI R data
  and no queued results. Sequencer load PE retains ID 3.
* Independent debug snapshot head PC is 0xffffffff80015e9a, retired count
  1466845174; DDR outstanding counts and error count are zero. This differs
  from the earlier third-load PC but lies in the same restore sequence.

Frozen `load_store_unit.sv:439` grants accelerator MMU ownership only when
acc_mmu_req is asserted, no new scalar LSU request exists, and the bypass
queue is empty (`lsu_bypass.sv:61`). Thus the captured occupancy explains
why the vector request cannot obtain ownership. It does NOT yet explain
why the scalar head cannot pop. Distinguish invalid/incorrect queue payload,
load/store-buffer pressure, page-offset conflict, D-cache grant/response
wait, and translation wait before changing arbitration or functional RTL.
The instructions following the fourth restore load include three scalar
loads of saved vector metadata, but their presence in the source does not
prove the identity of either buffered hardware request.

Do not use the preliminary bindings-only full-PC reconstruction: it disagrees
with the independent debug snapshot. Some optimized aliases/constant paths
need further validation. Decode control evidence against the named CSV
columns; no reset/polarity fault is established by this reconstruction.
The current profile lacks scalar queue FU/address, load/store FSM, scalar
translation and cache grant/return signals needed to distinguish the above
causes. Linux root cause and broader functional acceptance remain open.

Sampling semantics: `ara_fpga_debug/retire_count_i` is the per-cycle retire
increment, which the frozen debug RTL adds into its accumulated counter.
The eight sampled bits are therefore commit activity, not the low eight bits
of a cumulative instruction count. `head_pc_i` is the commit-head PC, not
proof that the Ara request has been accepted. The common one-stage ILA input
pipeline must be accounted for when comparing samples to external snapshots.

`capture_stall_ila.tcl` is prepared for a later, already-programmed diagnostic
image. It selects cable `210308A3B79F`, exactly one VCU118 and exactly one
`i_stall_ila`, maps `probe0[578:0]` to a raw bus, and requests 1024 samples
with immediate triggering and a 0.5-minute timeout. It exports ILA archive,
CSV and VCD; it has no programming, reset or AXI memory commands. Supply only
the LTX matched to the reviewed/programmed observation image. Immediate
capture shows the current stalled state, not necessarily the earlier event
that caused it. Reproduced failure and time-correlated evidence remain required.

The five mocked capture-flow cases pass (normal capture, wrong cable, absent
or ambiguous core, timeout). No board capture has yet validated this script.
The tool sequence follows AMD's
[ILA run command](https://docs.amd.com/r/2020.2-English/ug835-vivado-tcl-commands/run_hw_ila),
[explicit user probe mapping](https://docs.amd.com/r/2020.2-English/ug835-vivado-tcl-commands/create_hw_probe),
and [capture export](https://docs.amd.com/r/2020.2-English/ug908-vivado-programming-debugging/Saving-Captured-ILA-Data-to-a-File).

## Additional isolation results (2026-09-30)

### Actual operand-history controls

`make_vector_operand_trace.py` builds a bounded GDB script from the earlier
TB window. It relocates 87 user vector instruction sites against the first
user vector PC, captures scalar operands/VL/VTYPE/VSTART, and stops at the
first read-return restore (1024 event / 32 restore hard bounds). Evidence:
`/tmp/ara_vector_operands_20260930/gdb.log`, 186 events, two restores. These
are QEMU architectural operands, not observed FPGA cycle-level state.

Two previously uncovered instruction sequences were isolated without RTL changes:

- `READ_PROBE PATH_PROBE`: the actual final path-building copies use m8 VL
  7, 0, 15. The nonempty source offsets are 0xfd0 and 0xf01; destination
  offsets are 0x540 and 0x547. All source/destination pages are pre-touched
  to separate alignment/zero-length handling from demand-page exceptions.
  QEMU and `linux_path_probe_eth` on the board pass read832, a scalar check
  of all 22 copied bytes, and 128 vector iterations. Rootfs SHA256:
  `4773ff1df968094a2efc2646843c717579d3af21f370d59f2729a6e5ca9f6243`.
- `READ_PROBE MASK_PROBE`: the loader's e64/m1 VL=2 VID/VMUL by 3,
  VMSLEU/VMERGE and two-load/store forms, including overwriting v0 with its
  own comparison mask. QEMU and `linux_mask_probe_eth` pass scalar result
  checks after read832 and all 128 subsequent vector iterations. Rootfs:
  `dcad5d0a4fb5db65713a531d35c86001bed64326330cbb93fdd34cef29ccf5ae`.

Neither sequence alone reproduces the full-rootfs stall. The tests do not
duplicate all preceding loader execution, physical addresses, or interrupts.
The extended VLDU harness (`SHORT=1`) interleaves 7/15-byte loads with 1024-byte
loads and checks partial byte enables; matching RTL and actual routed-cell
models pass all four ID/backpressure cases. Evidence directories:
`/tmp/ara_vldu_short_20260930`, `/tmp/ara_vldu_short_mapped_20260930`.
The long-load RTL regression also passes. The mapped extraction limitations
described below still apply.

`patch_restore_serial.py` / `restore_serial_fragment.S` create a separate
hash-pinned diagnostic Image. Three existing standard-V NOPs are reclaimed
to insert `csrr zero,vl` between the four actual restore loads. All load,
metadata and architectural state-restoration operations remain. The moved
conditional branch retains its original return destination. On this frozen
Ara implementation CSR reads explicitly wait for backend idle. No production
kernel or RTL is replaced. QEMU boots the original rootfs to its BusyBox shell
with the diagnostic Image (SHA256
`9b27bdfa90f43fd8bfa262ad3c137f0003488ca971e8c2eef3506e1f6ca4864f`).
This is a completion/overlap diagnostic, not a supported general kernel patch.

The board run `linux_serial_restore_eth` still times out after `Run /init`.
All 30,029,982 payload bytes were verified over Ethernet in 3.068545 s
(9.786391 MB/s including readback), with zero packet retries. Two subsequent
nonfreezing snapshots (`serial_restore_snapshot1`, `serial_restore_snapshot2`)
show cycles 17,937,037,371 -> 19,440,187,049 but retired fixed at
1,456,744,638. Last retired PC is `ffffffff80015e8e`; commit-head PC is
`ffffffff80015e90`, the third load (`vle8.v v16,(a4)`) in this diagnostic.
Both inserted CSR waits preceding that PC have retired, so merely separating
the four loads does not make this full-rootfs control boot. DDR read/write
outstanding counts and response error count are all zero in both snapshots.

Important limits: commit-head PC is not a vector request-acceptance probe;
it cannot distinguish an unissued instruction from an accepted operation
awaiting response. The last recorded exception here is cause 2, tval
`cd717057`, whereas the original full-rootfs stall recorded cause 8. Thus
these are not established as the same dynamic restore invocation. A recorded
illegal-instruction exception can be part of Linux lazy vector enable; it
alone does not establish an unsupported instruction or the hang's cause.
No internal lane completion or dependency state was sampled on the board.
Local evidence: `/tmp/ara_serial_restore_board_20260930`.

`qemu_vector_fault_history.gdb` bounds the reference trace at the first
read-return restore. `/tmp/ara_vector_fault_history_20260930/gdb.log` records
eight page faults and two restores, including two vector-store page faults
but no observed vector-load page fault in that window. This is a QEMU
architectural reference, not evidence that FPGA page-fault timing matches.

The next discriminating observation must correlate accelerator request and
response handshakes/IDs, dispatcher state, sequencer running/dependency bits,
VLDU commit/result occupancy and per-lane final write grants. DDR-idle and a
commit-head PC alone do not justify a VLDU, cache, or interconnect RTL fix.

No production RTL was changed in this investigation. Evidence root is
`D:/fpga_runs/ara_restore_probe_20260930`.

- `linux_read832_jtag`: original kernel with a minimal static PID 1 passes
  actual 832-byte kernel read and 128 vector iterations (131072 bytes checked).
- `linux_readtrap_jtag` / `readtrap_context`: an intentional read-return
  breakpoint captures the full-rootfs task before restore. Its saved vector
  data is page aligned, stable across two reads, 4096 bytes of FF; metadata
  has VL=0, VTYPE=VILL and VLENB=128. This is a diagnostic capture, not a boot pass.
- Actual routed VLDU netlist and matching RTL both pass 16 consecutive
  832/1024-byte loads with instruction-ID reuse and asymmetric lane stalls.
  See `run_vldu_restore.sh` and `vldu_restore_mapped.svh`. The extracted cell
  omits the ready driver and unused high VRF address bits: the test derives
  ready from actual commit-count flops and checks the seven physical address
  bits. This does not validate the external ready cone or full-SoC timing.
- `qemu_init_vector_history.gdb` identifies SEW/LMUL transitions and a vector
  store page-fault/retry in actual dynamic-loader startup, before read.
- `linux_fault_store_eth`: minimal PID 1 exercises e64/m1 then e8/mf2,
  a store to a demand-paged mapping, read832, then 128 vector iterations.
  All three diagnostic markers pass on QEMU and the board. Therefore this
  sequence alone is not a sufficient reproducer of the full-rootfs stall.
  Ethernet payload/readback: 30029982 bytes / 3.065351 seconds = 9.796587 MB/s,
  zero data/control retries. Full BusyBox boot remains unaccepted.

### Cold Ethernet initialization ordering

`preclock_guard` and `preclock_eth_init` recover the same bitstream and
firmware without cable or route changes. External PHY3 register D3 starts
at zero; enabling its six-wire clock (0x4000) BEFORE the original firmware
initializes DMA/PCS restores UDP identity. Internal PCS1 becomes readable
and PHY SGMII status register 37 changes from 0 to 3. The inspected firmware
initializes DMA before its later PHY setup, while DMA reset drives PCS reset.
This supports a clock/reset ordering problem, not a corrupted Linux image.

`ara_init.py --prepare-phy-clock` provides this opt-in sequence after the
existing cold/zero-DDR guard and firmware hash validation. It stops MicroBlaze,
checks PHY identity/mode, enables the clock with readback, restores MDIO
addressing/divider state, then downloads the original firmware. Preparation
failure prevents firmware launch. Repeat cold-board validation is recorded
separately; this option does not authorize initializing an active system.

The integrated option passed a second cold initialization in
`integrated_preclock_init` (D3 0 -> 0x4000, UDP firmware identity received).
`linux_full_preclock_eth` then loaded the original full rootfs and original
Image: 30029982 bytes / 3.066254 seconds = 9.793705 MB/s including readback.
The full boot still times out at 180 seconds after printing `Run /init as
init process` at kernel time 62.323643 seconds; no init marker or shell.
Non-freezing `full_preclock_snapshot1` and `full_preclock_snapshot2` record
cycles 10674478890 -> 11198306613 but retired fixed at 1471885607, last/head
PCs `0xffffffff80015e98` / `0xffffffff80015e9a` (fourth restore load),
trap_count=175645 and last cause=8. DDR error and read/write outstanding
counts are zero in both. The different restore-load stopping positions do
not identify a specific backend unit; they also show that Ethernet recovery
alone is not a Linux fix. Board execution was left in this diagnostic state,
with the Ethernet master locked/isolated; no original image was restored.

## Board test of the fixed bitstream (2026-09-30)

The new host_ethernet bitstream SHA256 is
`4166a5bec610638f81a120ca1eba198dffa1f68328f39b28c7ad635f61d01344`.
Both cold programming operations reached `BOARD_READY status=e`.
Evidence: `D:/fpga_runs/ara_valu_board_20260930` (also collected under the
same basename in Linux `/tmp`). No RTL was changed during these board tests.

- **Old unmodified bare reproducer now passes its own criteria:**
  `bare_discard/snapshot.json` records done=1, result=0, trap_count=8,
  last_trap_cause=8 and DDR errors=0. The generic loader still labels the
  run failed because its normal policy rejects any trap. These eight ecalls
  are intentional; this is not a global relaxation of the loader policy.
- **Ethernet load passes:** `linux/report.json` records 30,029,982 payload
  bytes in 3.067485 s including readback (9.789773 MB/s), zero retries,
  and locked/isolated, balanced, error-free loader DDR transactions.
- **Full Linux boot fails:** the unmodified kernel Image has SHA256
  `716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285`.
  This test uses the `/lib64`-corrected BusyBox rootfs, polling-UART DTB,
  and the prior unaligned-probe skip arguments. Linux reaches `/init`, but
  the standard init marker is absent after 180 seconds. No shell acceptance.
- **The stall moved:** non-freezing `linux_snapshot1` and `linux_snapshot2`
  show cycles 12,291,501,846 -> 12,961,198,033, with retired fixed at
  1,459,709,018. Last/head PCs are `0xffffffff80015e92`/`0xffffffff80015e94`;
  trap_count=171136, last cause=8, last trap PC=`0x3fb9b1e186`. DDR error
  count and read/write outstanding counts are all zero. The actual loaded
  Image contains `0x02070807` at offset `0x15e94`: `vle8.v v16,(a4)` in
  the four-load vector restore sequence. This is a new observed blocking
  location, not proof that this instruction or VLDU is the root cause.

The frozen package's older host script rejected the split Ethernet VIO
probes before downloading firmware. The successful attempt used independent
copies of the current host scripts under the evidence directory's `tools/`;
the frozen package and bitstream were not modified. The existing split-probe
transport regression passed (1 test).

`rvv_context_check.S` and `check_rvv_console.py` test vector computation and
byte readback between syscalls. The original unexecuted test incorrectly
expected vectors to survive getpid: this kernel explicitly calls
`riscv_v_vstate_discard` on syscall entry (`arch/riscv/kernel/traps.c`).
The corrected test reinitializes vector state after each syscall. Its minimal
PID-1 variant passes 128 iterations / 131072 checked bytes on QEMU with the
same kernel. This is not a vector-preserving syscall ABI test.

### Restore-path controls (2026-09-30)

`vector_restore_bare.S` / `.ld` exercise four Linux-style e8/m8 loads,
four stores and a 4096-byte scalar comparison. All three board controls pass
with result=0, done=1, no traps and no DDR errors:

- Default: M-mode, progress MMIO stores between loads.
- `-DTIGHT`: M-mode, only pointer additions between the four loads.
- `-DTIGHT -DSV39`: S-mode, identity-mapped 1 GiB Sv39 leaves with A/D set.

Evidence is `D:/fpga_runs/ara_restore_probe_20260930/{bare,tight,sv39}`.
These controls do not cover Linux page layout, interrupts, previous vector
operations or kernel context switching. They do not establish the Linux
stall's root cause or prove all vector loads correct. No RTL changes were
made for these tests. The `-DDRAIN` variant was compiled but not run.

The corrected `rvv_context_check.S -DINIT_PROBE` was also run as a minimal
static `/init` on the board, with the original Image, OpenSBI and DTB.
The diagnostic initramfs contains `/init` and `dev/` and is zero-padded to
the original 2432000-byte extent, so the embedded DTB is unchanged.
Its SHA256 is
`911171ed38b3fb8165b02b12d26bb0e31e69d4339aa759d152cd50c2d3ab7288`.
`linux_init/uart.txt` contains both `ARA_RVV_CONTEXT_INIT_START` and
`ARA_RVV_CONTEXT_OK iterations=128 bytes_checked=131072` after kernel boot.
The generic Ethernet loader reports timeout because it waits for the normal
shell init marker, which this diagnostic deliberately does not emit. This
is a diagnostic-specific pass, not a full rootfs/shell acceptance.
The same diagnostic also passes QEMU; PID 1 then deliberately parks, so
the QEMU runner's timeout exit is expected after the checked marker.

This narrows the unresolved full-rootfs failure to a more specific execution
history than Linux vector use or basic restore alone. BusyBox/glibc are not
proven faulty: their startup can expose a hardware sequence absent from this
minimal test. Full-rootfs acceptance remains failed.

### Scalar usercopy board control: negative result

The scalar-usercopy diagnostic Image was loaded over JTAG on the SAME
VALU-fixed bitstream. The integrated loader first passed the cold ROM guard
and locked/drained the Ethernet DDR master. All 30,029,982 payload bytes
were written and read back in 146.909549 seconds (204411 bytes/s).
Linux reached `Run /init as init process` at 62.314132 seconds but did not
emit the init success marker within the 120-second post-launch window.
Evidence: `D:/fpga_runs/ara_restore_probe_20260930/linux_scalar_usercopy_jtag`.

The subsequent `scalar_usercopy_snapshot` has last/head PCs
`0xffffffff80015e98` / `0xffffffff80015e9a`, the FOURTH e8/m8 restore load,
with retired=1472013094, DDR errors=0 and no DDR transactions outstanding.
Thus disabling kernel vector usercopy alone does NOT fix boot, and it is
not a necessary trigger for the broader restore-path failure. Do not
promote the scalar threshold patch as a working workaround. Investigation
must also cover context save/restore around scheduling and other traps.
`jtag_linux_control.py` composes the existing guarded APIs without Ethernet
packet dependence. Its three mocked tests verify gate ordering, rejection
before loading, and failure reporting; these are not hardware signoff.

Ethernet follow-up: PHY D3=0x4000 (clock mode enabled), CFG4=0x1170, SGMII
AN status=0, copper BMSR=0x796d. A complete MDIO scan finds only external
PHY address 3. One explicitly requested `--restart-sgmii` diagnostic
toggles CFG2 bit 7, restoring and checking the original CFG2=0x29c7.
SGMII AN remains zero and firmware identity still times out. The loader
CPU was resumed. No repeated AN restart is warranted from this evidence.
The successful earlier firmware and the current failed-initialization
firmware have identical SHA256
`26253345510d09f96ef2c5ebe1b6b3e9bae408936162689fad1105210cc47fa2`.
The failure happens before any Linux payload is sent; it cannot be caused
by executing the diagnostic kernel. Startup clock/reset sequencing remains
a hypothesis, not an established root cause. Ethernet DDR is now deliberately
isolated for the JTAG Linux experiment, so do not attempt more firmware
network recovery on this boot without restoring a cold board state.

The sections below describe earlier controls and the original failure.

### Actual Image / read-usercopy investigation (2026-09-30)

Full Linux is still NOT accepted on the board. The following narrows the
trigger, not the faulty RTL module. The SDK's current rebuilt Image differs
from the board Image; addresses below were decoded from the hash-pinned
board Image, not inferred from the rebuilt SDK's System.map.

`run_qemu_restore.py` with `qemu_restore.gdb` captured 12 restore occurrences
on the original Image and full corrected rootfs. Evidence:
`/tmp/ara_restore_gdb_20260930/{gdb.log,uart.log}`. The first occurrence is
initial vector activation, with zero context data. Later occurrences include
the dynamic loader's read syscall (a7=63, 832 bytes), with saved VL=0,
VTYPE=VILL, VSTART=0 and all-ones context data. The actual restore executes
`vsetvli a3,zero,e8,m8,ta,ma` and four 1024-byte loads. At the third load,
runtime VL=1024, VTYPE=0xc3 and VSTART=0. Saved VILL alone is not an illegal
restore: these loads execute with the temporary valid e8/m8 configuration.
The saved configuration is reinstated only after the four loads.

The candidate chain is syscall discard -> kernel context save -> vector
usercopy -> deferred vector restore. Actual vector usercopy begins at
`0xffffffff80b87634`; the stalled restore head is `0xffffffff80015e94`.
The board's last user ecall PC suffix agrees with the dynamic loader read
wrapper, but the failing board invocation has not yet been captured with
its arguments. Do not assert that QEMU's particular read is already proven
to be the board's failing invocation. QEMU also uses a different platform
and page-table mode; it is an architectural reference, not cycle equivalence.

`patch_restore_trap.py --site third` intentionally replaces the third load
with EBREAK. Board evidence `linux_third_trap` under
`D:/fpga_runs/ara_restore_probe_20260930` captures the FIRST restore, from
the initial vector trap, not the later failing read. Its buffer is page
aligned (`0xffffffd6023f2000`), with third address +0x800. This does not
establish the failing read's buffer address. The `--site read` variant uses
three existing NOP slots to trap only read returns, retaining every vector
instruction. It has now run in QEMU and on the board (`linux_readtrap_jtag`);
the read-return buffer is also page aligned at `0xffffffd6023f2000`, and
`readtrap_context` confirms stable all-FF saved data.
`read_restore_state.py` can read the stopped task's saved metadata and
4096-byte context twice through single-beat JTAG, without memory writes.

Two discriminating controls have completed:

- `patch_usercopy_scalar.py`: validates the Image hash, both actual
  AUIPC/LD references and the 768-byte threshold, then changes only that
  8-byte threshold to UINT64_MAX. User RVV and restore code stay enabled.
  `/tmp/ara_usercopy_scalar_20260930.Image` boots the full rootfs to its
  init marker and shell in QEMU, but still stalls on the board (see above). This is a
  diagnostic control, not an accepted production fix.
- `rvv_context_check.S -DINIT_PROBE -DREAD_PROBE`: activates user V, opens
  its own ELF and reads exactly 832 bytes. Checks the byte count and ELF
  magic, then runs the existing 128 vector iterations. QEMU passes both
  `ARA_RVV_KERNEL_READ_OK` and `ARA_RVV_CONTEXT_OK`. Rootfs SHA256 is
  `cb0640de1a3f9b58f81a030bc6f1ede1fedf16a9f7cbccbe98bd130f71a6a0df`.
  Evidence: `/tmp/ara_rvv_read832_qemu_20260930.log`. A focused GDB run
  using `--gdb-script qemu_read832.gdb` confirms entry into the ACTUAL
  kernel vector usercopy with a2=832 and then the third restore load with
  the same saved VL/VTYPE/all-ones state as the full-rootfs read.
  Evidence: `/tmp/ara_read832_chain_gdb_20260930_02/gdb.log`.
  This minimal rootfs also passes on the board in `linux_read832_jtag`.

The initial attempt to use the 12-hit trace with the minimal rootfs timed
out after two hits, because that program does not generate 12 restores.
The focused three-breakpoint script supersedes that incomplete trace.
An earlier rootfs named `ara_rvv_read_init_20260930.cpio` was packaged after
a failed compile and is invalid; do not use it. Use the read832 rootfs above.

At this earlier point, further board tests were blocked by firmware identity timeouts
after cold programming. SSH/JTAG work, Windows reports a 1 Gbit/s wired
link and the dedicated host route, and MicroBlaze is running. ARP/UDP
responses are absent; this is not a failed Linux diagnostic, since no
payload or launch occurred. Evidence: `readtrap_eth_init`,
`readtrap_eth_init_retry`, `readtrap_eth_init_cold2` in the board diagnostic
directory. A subsequent read-only identity query also timed out. Cable/PHY
recovery was pending. The cold PHY clock ordering recovery and subsequent
successful Ethernet tests at the top of this document supersede that blocker.

Follow-up live network inspection: Windows SSH and JTAG are reachable; wired
interface 10 is Up at 1 Gbit/s with 192.168.1.11. An unbound Find-NetRoute
query selected Wi-Fi, but the explicit-source query correctly uses the
existing interface-10 /32 route. An attempted New-NetRoute was rejected as
already existing; no route change succeeded. Do not call this a missing-route
root cause. A Scapy ARP request explicitly sent on interface 10 received zero
replies, and the bound UDP firmware-identity query still timed out.

The matching firmware ELF identifies eth_probe_stage at 0xff0002b4: it is 8
(ready), with frame/profile/drop counters zero. MicroBlaze PCs move within
the input loop and its timer advances about 305 million ticks in 3 seconds.
DMA status is TX=0x1000a, RX=0x10008. MAC receive/transmit configuration is
0x1000ffff/0x10000000 (enabled); sampled MAC byte/frame counters are zero.
Counter implementation must be checked before interpreting zero as absolute
proof that no physical packets arrive.

`inspect_loader_mdio.tcl` pauses only the running loader MicroBlaze while
issuing MDIO read commands, then resumes it even on a read error. It does
not reset the board or write PHY configuration. Live results: external
PHY address 3 gives BMCR=0x1140, BMSR=0x796d on both reads, IDs=0x2000/a231,
AN advertisement=0x01e1, partner=0xcde1, register 17=0xbc02. The external
link and autonegotiation bits are set. Address 1 returned 0xffff for every
read, so it did not provide a valid internal PCS status; this is not a
valid all-bits-set healthy status. Internal PCS address/configuration and
clock/reset need checking next. Physical cable disconnection is not supported
by these current link observations. The script printed LOADER_RESUMED.

Even if scalar usercopy boots on the board, that only identifies a necessary
trigger. Locate the hardware fault using the request ID, translation and
AXI descriptor handshakes, VLDU issue/commit counts, per-lane result valid/
grant/final-grant, and VSTU pending completion across save/copy/restore.
Zero DDR outstanding counts do not prove that vector writeback or backend
completion has finished. No production RTL was changed in this investigation.

## Current evidence

The failing board bitstream SHA256 is
`bde214d6d00664f2d9d006ee607146719442ef2c18521d8c2b9c77904a45204e`.
Its routed checkpoint is
`D:/fpga_runs/ara_postroute_close_20260928/ara_dsa_vcu118_routed.dcp`.

* `vector_ecall_init.S`: on Linux, first user ecall returns; the second stops
  with head PC `0xffffffff80b880d8`, the discard-path m8 configuration.
* `patch_discard_drain.py`: creates a separate hash-pinned diagnostic Image,
  replacing only the NOP at `0xb880f4` with `csrr zero,vl`. On the board this
  moves the stall to that CSR during the **first** ecall. Evidence:
  `D:/fpga_runs/ara_discard_drain_{run,snapshot}_20260928_01`.
* `vector_discard_bare.S` with `USER_ECALL` and `BOARD`: without Linux, eight
  intended U-to-S ecalls repeat the same discard sequence. The board stops
  at the second ecall's vsetvli, PC `0x8000009c`, with trap_count=2.
  Evidence: `D:/fpga_runs/ara_discard_bare_{run,snapshot}_20260928_01`.
* Adding `SERIALIZE_MOVES` inserts a vector CSR read after each VMV. The board
  reaches done=1, result=0, trap_count=8. Evidence:
  `D:/fpga_runs/ara_discard_serial_{run,snapshot}_20260928_01`.
  The generic loader reports failure because it rejects all recorded traps;
  these eight ecalls are intentional. This is a diagnostic checkpoint pass,
  not a general loader or Linux pass. No vector data readback is checked by
  this assembly test; final VL/VTYPE and forward progress are checked.

The main-tree VCS SoC image at
`verification/out/main-store-fp16-image-20260926-01/sim/simv` completes both
S-mode and U-to-S unmodified discard tests: 51 requests/responses and 32
backend allocations/completions. Serialized mode completes 83 requests/
responses and 32 backend allocations/completions. No protocol errors.
Logs are under `/tmp/ara_discard_bare_20260928/`.

Before the fix, the archived board source hashes of acc_dispatcher, ara_dispatcher, valu,
ara_sequencer, lane_sequencer and operand_requester match the current source.
This does not establish equivalence of every source, SoC configuration,
technology implementation, stimulus schedule, or mapped netlist.

The initial falsifiable hypothesis concerned overlap of vector operations and
their completion tracking. Serialized success alone does not identify which
queue, handshake, or synthesized logic is incorrect. Do not use serialization
as proof that arbitrary Linux user vector programs are safe.

## Reproduction

Use the repository RISC-V GCC with `-nostdlib -static -march=rv64gcv
-mabi=lp64d -Wl,--no-relax`, and link `vector_discard_bare.S` with
`vector_discard_bare.ld`. Options:

* no define: M-mode discard;
* `-DSUPERVISOR`: S-mode discard;
* `-DUSER_ECALL`: eight U-to-S ecalls;
* `-DSERIALIZE_MOVES`: drain after every VMV;
* `-DBOARD`: use FPGA debug RESULT/DONE, not simulation MMIO.

Without BOARD, the simulation control register expects exit-code payload 0
for success; it adds the completion bit itself. The initial test harness
incorrectly wrote 1 and reported failure despite matching final CSRs; the
corrected S-mode and ecall runs above supersede that harness failure.

`run_valu_discard.sh OUTPUT` builds an isolated ALU test for four e8/m8 VMVs
(VL=256 per lane), verifies each word/address/byte-enable and completion,
and checks five request gaps with and without deterministic writeback stalls.

`export_vector_netlist.tcl CHECKPOINT NEW_OUTPUT_DIRECTORY` only reads the
checkpoint and exports function-simulation netlists of valu, ara_sequencer,
and lane_sequencer. It does not synthesize, route, or program the board.

## Routed ALU discrepancy

The isolated RTL test passes all ten gap/backpressure combinations in
`/tmp/ara_discard_bare_20260928/valu_final/`. The routed lane-0 `valu__1`
export does not pass the same test. Reproduce with `NETLIST` set to the
absolute exported `valu_0.v` path and `MAPPED_VALU=valu__1` when invoking
`run_valu_discard.sh`. The script stops at the first failed case; it does not
claim the remaining cases passed. Add `+TRACE` when invoking the resulting
`simv` to print the first forty cycles and mapped queue signals.

Evidence: `/tmp/ara_discard_bare_20260928/mapped_trace_data/trace.log` and
`trace_stalled.log`. With continuous grants, the first two writes are correct,
but the third has data=0 and byte-enable=0. With GAP=31 and BACKPRESSURE=1:

* cycle 4: request=1, grant=0, queue read pointer=0, write pointer=1,
  valid=01, output data=all ones and byte-enable=ff;
* cycle 5: request=1, grant=0, read pointer still 0, valid=11, but output
  data=0 and byte-enable=0;
* cycle 7: the first grant receives the corrupted data and the test fails.

Thus the exported model loses a pending result even without a second
instruction being accepted. This is a concrete RTL/model discrepancy, not
yet proof of a synthesis-tool bug or the complete board-hang explanation.
Compare linked-synthesis and routed versions and audit export boundaries
before choosing a functional fix. The exported upper three address bits are
undriven because the routed parent consumes only the low seven; the test
explicitly checks that boundary rather than treating it as data corruption.
No SDF is used, so these tests are not timing signoff.

## Synthesis isolation and fix

The original linked-synthesis ALU and a freshly synthesized standalone ALU
both reproduce the payload loss. Thus the discrepancy is already present
before physical optimization. `synth_valu_probe.tcl` and `valu_synth_top.sv`
reproduce it using Vivado 2020.1 and the board's four-lane, VLEN=1024 setup.
Merely changing the packed queue into an unpacked array did **not** fix it;
that rejected experiment is not in the RTL.

The successful change constructs the write payload in a temporary struct,
then updates whole queue entries through constant-index loop assignments.
Read-side clears also use constant-index entries. Original write/clear
priority, payload fields, and completion bookkeeping are retained. The
previous overlapping dynamic field assignments and whole-entry clears lost
the pending payload in the synthesized model.

Both `hardware/src/lane/valu.sv` and its FPGA package copy carry the fix.
New SHA256: `f8a8cd12e9d4732eca87e1c9a1aa48b52a8e684f2d7e64d0e8ec1faa9411c778`.

* Fixed RTL: 10/10 gap/backpressure cases passed.
* Freshly synthesized fixed netlist: 10/10 passed, including request-held
  data/address/byte-enable stability. Evidence:
  `/tmp/ara_discard_bare_20260928/static_entries_netlist_test`.
* Rebuilt VCS SoC: 8/8 representative RVV tests passed, including add,
  merge, narrowing, shifts, LMUL reductions and overlapping reductions.
  Source manifest: 457 files, unchanged across compilation.
  Evidence: `verification/out/valu_queue_fix_20260928_02/regression`.
* Original eight-ecall discard reproducer on the rebuilt SoC: 51 requests
  and responses, 32 allocations and completions, zero protocol/UVM errors.
  Evidence: `/tmp/ara_discard_bare_20260928/user_ecall_fixed.log`.

These are functional tests, not full-design timing or board signoff.

`stage_valu_fix.py` clones only SHA256-listed inputs from the reviewed board
package and replaces only the hash-pinned ALU. It rejects changed originals
and existing destinations. `build_valu_fix.ps1` prepares IP and runs gated
synthesis in an independent process; it does not program the board or bypass
synthesis failures. Full-design netlist/timing review is required before
physical continuation.

Fresh build: `D:/fpga_runs/ara_valu_fix_20260928`; original package remains
unchanged. Read `state.json` and `flow.log` there for progress.

## Historical Linux controls (2026-09-28)

The original bitstream has not yet been replaced with this fix. A scalar-only
control with an embedded no-V, polling-UART DTB reached PID1 but panicked on
an RVV instruction in the dynamic loader (`0xcd817057`). The installed glibc
loader requires V, so disabling V is not a valid workaround for this rootfs.
Evidence: `D:/fpga_runs/ara_scalar_linux_20260928_03`. An earlier `_01`
control used a firmware-embedded DTB that overwrote the downloaded DTB and
was not a valid no-V comparison; `_02` failed host cleanup before launch.

Linux on the board is still unvalidated. The acceptance target is the
unmodified kernel with V enabled, successful shell interaction, repeated
user/kernel transitions and checked vector data, not just an init banner.

## Current restore investigation (2026-09-30 evidence)

The fixed-VALU bitstream is now on the board. Full Linux is **not accepted**.
The board was most recently left in the passing static MFPU diagnostic,
not a working BusyBox shell. A VMFPU queue fix has now passed restricted
RTL/mapped tests below; it is not yet in a new board bitstream.

`build_staged_init.py` replaces only `/init` in the original 2432000-byte
rootfs, keeping BusyBox and the dynamic loader/libc unchanged. With the
diagnostic serialized-restore Image, QEMU prints all stage markers and reaches
the shell. On FPGA, `ARA_STAGE_SHELL_ENTERED` prints but `ARA_STAGE_PROC_DONE`
does not: the first mount command has not completed. This establishes real
BusyBox entry, not an invented acceptance banner. Evidence on Windows:
`D:/fpga_runs/ara_restore_probe_20260930/linux_serial_staged_eth` and
`staged_snapshot`; local copies are `/tmp/linux_serial_staged_eth` and
`/tmp/staged_snapshot`.

The stopped commit head is `ffffffff80015e90`, the serialized kernel's third
`vle8.v` (destination v16). Last trap cause is 2, tval is `cd717057`, and
trap PC is `3f8f02e7d0`. The actual rootfs libc at offset `9e7d0` contains
`vsetivli zero,2,e32,mf2,ta,ma` in the fork-child branch. A cause-2 trap there
can be normal lazy vector enable; it is not proof of unsupported instructions.
QEMU's `qemu_fork_restore.gdb` trace confirms this user instruction after
return from vector restoration. Its current nested trap can be a timer;
QEMU does not reproduce the board's cycle-level execution or Sv39 mapping.

Passing `FORK_PROBE` after the output path to `build_rvv_init.sh` constructs
a separate static PID1.
On FPGA with the **original, unpatched kernel**, 16 clone/wait4 children
complete the libc-like first-use vector sequence; subsequent 128 context
iterations check 131072 bytes. Markers are `ARA_RVV_FORK_OK children=16` and
`ARA_RVV_CONTEXT_OK iterations=128 bytes_checked=131072`. Evidence:
`D:/fpga_runs/ara_restore_probe_20260930/linux_fork_probe_eth`, copied to
`/tmp/linux_fork_probe_eth`. Simple fork/first-use alone therefore does not
reproduce the full-rootfs failure. During test bring-up, the freestanding
program needed explicit non-relaxed GP initialization; that diagnostic
linker-relaxation issue was corrected before accepting these results.

`sequencer_restore_tb.sv` exercises 32 e8/m8 loads, delayed address-generator
acknowledgements, delayed completion, overlapping and serialized issue.
RTL passes four cases. The current routed sequencer export also passes those
cases **assuming its replicated vd[0:1] boundary inputs are zero**, appropriate
to destinations 0/8/16/24 but not independently traced through the parent.
Deliberately setting these aliases to one fails the payload check. Thus this
is a conditional cell-level result, not full-netlist equivalence. Evidence:
`/tmp/ara_seq_restore_20260930_02` and
`/tmp/ara_seq_restore_mapped_20260930`.

`mfpu_queue_probe.sv` instantiates the unchanged packaged VMFPU with half,
single and double support enabled, but restricts traffic to unmasked e64 VMUL
by scalar 3. Thirty-two instructions exercise ID reuse, result-queue wrap,
VRF addresses, byte enables, exactly-once completion and blocked-result
stability. Six RTL cases (lane VL 1/4/32, immediate/stalled grants) pass in
`/tmp/ara_mfpu_queue_rtl_20260930_05`. This does not test floating-point,
narrowing or mask operations. The attempted FPUSupportNone wrapper could not
be used as an RTL oracle because that configuration has two continuous
drivers for vfpu_mask; it is not the board configuration or a Linux diagnosis.
The final mapped experiment uses Vivado 2020.1, standalone synthesis and
`-max_dsp 0` to avoid encrypted DSP simulation primitives. It tests queue
mapping, not the board's DSP implementation or routed timing.

Source hashes match the frozen board package:

* VMFPU: `61de19fb76c0a7eb39566c521f464b2ae3874c9d504cf4486dbf3b4e2bf8f7f8`.
* SIMD multiplier: `1ba7d9f1ed1aed9ec5407d0af244c4aa3a4be1f2457fdaee4653d6fa875c6c64`.

### New VMFPU discrepancy and restricted fix validation

The original complete standalone synthesized model (not an extracted cell)
fails while its matching RTL passes. With lane VL=1 and immediate grants,
at 265 ns the third result has ID/address/BE/data all zero, instead of the
expected payload `a30f63b54c12c167`. With lane VL=32 and delayed grants, at
255 ns a pending result changes even though it has not been granted. These
are not Linux timeouts or missing boundary aliases.

The change in both `hardware/src/lane/vmfpu.sv` and the FPGA package copy
initializes a temporary payload from the selected entry, performs the same
24 field/slice updates on that payload, then assigns whole entries through
constant-index loops. The later read-side clear still has priority. Queue
valid bits, pointers, counters, FP narrowing packing, reduction sequencing,
and arithmetic are not intentionally changed. Original source has no other
read of the modified next-state payload; next-state valid-bit reads remain.

Fixed VMFPU SHA256:
`a96f686b78d4def540835ce5bc36af2ed7eb867f562f2d7f7ab7b3079f5d562a`.
The fixed RTL and freshly synthesized fixed model both pass all six cases,
with exactly the original RTL's counts and cycles. Evidence:

* Original failures: `/tmp/ara_mfpu_queue_mapped_20260930_01`.
* Fixed RTL: `/tmp/ara_mfpu_queue_fixed_rtl_20260930_01`.
* Fixed mapped: `/tmp/ara_mfpu_queue_fixed_mapped_20260930_01`.
* Windows synthesis: `D:/fpga_runs/ara_restore_probe_20260930/mfpu_full_synth`
  and `mfpu_fixed_synth`, with separate preserved input trees/logs.
* Original netlist hash:
  `11a3fc714e58927479ef5b6ad2ea0ac22402f85b3dd875b3be8962cf72e943d2`.
* Fixed netlist hash:
  `fa491b062e8b8a8fc09b7cfae6b9c801f7a5866a9cb94ab467ab1a21e81ba6fb`.

Logs and board evidence are retained in
`verification/out/restore_investigation_20260930`. The independent
`run_mfpu_soc_regression.sh` broadens checks to integer multiply/MAC/divide,
fixed point, FP multiply/add, narrowing, reductions, mask comparison,
vstart and Linux vector context. Its output is
`verification/out/mfpu_queue_fix_20260930_01`. Eleven tests pass;
`vfncvt_int8` reaches the 300-second wall-time limit. Its final retirement
trace is still advancing through scalar input preparation at cycle 279663,
not evidence of a vector deadlock. The unchanged test and simulator were
rerun with a 1800-second bound in
`verification/out/mfpu_queue_fix_narrow_20260930_01`; this also timed out.
Its final retired cycle is 1596453 in scalar policy preparation: forward
progress beyond the first run, but not an acceptance result.
Missing completion/contract summaries in the timed-out run are
not a passing regression and are not independently a protocol violation.

`MFPU_PROBE` adds a separate static PID1 test: poison the destination,
generate 128 e64 elements with VID, VMUL by 3, store and scalar-check every
element. QEMU prints `ARA_MFPU_QUEUE_OK elements=128` and the existing
128-iteration context PASS. This test is for a board comparison, not a
replacement rootfs or a complete Linux boot acceptance test.

The board also passes both markers with the original kernel and the existing
VALU-fixed bitstream, which does NOT contain this new VMFPU change. Evidence:
`verification/out/restore_investigation_20260930/linux_mfpu_probe_eth`.
Loading 30029982 bytes including readback took 3.067775 seconds
(9788848 bytes/s); all reported data/control retries and Ethernet errors
were zero. The loader was locked and isolated before CPU execution. The board
is left running the diagnostic PID1, parked after its PASS marker, not the
full BusyBox rootfs. This negative reproduction is important: it neither
invalidates the standalone mapped failure nor proves that the same failure
exists in the current routed board implementation.

The captured original loader trace has only one VMUL before its first read
return (global VL=2/e64/m1). That is not the same workload as the queue
stress. Therefore the demonstrated VMFPU discrepancy must not be advertised
as the proven cause of the earlier full-rootfs restore stall without further
board evidence. A new full-design bitstream has not been generated here.

### Evidence still needed before a functional change

The DDR monitor counts handshakes before the DDR width converter; zero
outstanding transactions cannot establish an empty Ara load queue, completed
VRF writeback, or successful accelerator MMU arbitration. The snapshot's
last AR is not attributed to the stopped instruction. The snapshot freeze
stops debug counters, not the processor or fabric clocks.

At the reproduced head PC, distinguish these cases using the actual signals:

* Dispatcher has not dispatched: acc request valid/ready, dispatcher state,
  ara_idle and per-PE running IDs/hazards.
* Address generator cannot advance: state_q, axi_addrgen_state_q,
  core_st_pending_i, MMU req/valid/exception, AXI AR valid/ready and metadata
  queue occupancy; correlate CVA6 MMU ownership and scalar LSU occupancy.
* Load accepted but not completed: VLDU instruction/result counters,
  per-lane request/grant and final-write acknowledgement, completion ID.
* Backend completed but scalar retirement waits: sequencer addrgen_ack,
  response valid/trans_id, CVA6 accelerator response and scoreboard valid.

The current debug ABI exposes none of these internal states. Do not infer
which one failed from PC plus DDR-idle alone, weaken timeouts or mass-rewrite
queues. No cycle-level signal yet identifies the remaining failing module.

### Current-package static re-audit (2026-09-30)

This review describes local source, not proof that the same source is present
in the running routed bitstream. No functional RTL was changed by this review.
The syntax inventory scanned 706 files (package plus main Ara source), found
148 overlap groups, and reported parser diagnostics in six files. These are
candidates, including ordinary constant-index code and duplicate copies,
NOT 148 confirmed bugs or a complete elaboration audit. Raw inventory:
`/tmp/ara_queue_reaudit_20260930.json`. All six scanner unit tests pass using
the existing `/tmp/ara_pyslang_verify_20260922_001` Python module directory.

Main-source fixes absent from the current FPGA copy:

* `sldu/sldu.sv`: scalar-only VSLIDE1UP can complete without a vector source,
  but the FPGA copy still asserts operand ready at the finishing boundary.
  A buffered younger operand can consequently be consumed. Main source adds
  `slide1up_scalar_only` to inhibit that ready. Check a scalar-only slide
  followed by a slide with distinct source words, including backpressure.
* `ara_dispatcher.sv`: the blocked-decode store-accept path does not exclude
  `pending_seg_mem_op_q`; main source excludes it to preserve the segment
  architectural request until all fields finish.
* `ara_dispatcher.sv`: zero-work segment handling does not clear the segment
  reservation; main source clears it so the next segment cannot bypass the
  old-memory drain. The FPGA copy also lacks the final effective destination
  width check before layout maintenance for widening beyond ELEN.

These are confirmed source-integration gaps with identifiable trigger
conditions, not newly reproduced FPGA failures. The captured stalled restore
is an ordinary unmasked e8/m8 load, not a segment store or illegal widening
operation. No captured evidence links the above triggers to that stall.
Do not bulk-copy main RTL: AKV's bounded popcount replacement and QBS's
preserved LUT are intentional FPGA-specific differences.

Other synthesis candidates remain in VLDU result writes/clears, MASKU,
SLDU, sequencer dependency tables, and CVA6 `lsu_bypass.mem_n` (whole entry
enqueue plus selected valid-bit clear). The already passing restricted
VLDU/sequencer mapped tests constrain these suspicions but do not establish
whole-design equivalence. Do not infer the VALU/VMFPU symptom from syntax alone.

Load-path checks and discriminating observations:

* AddrGen issues MMU/AXI requests only with queue space and AX ready. The
  normal read path has a two-entry AR holding FIFO with ready from registered
  occupancy, plus an AXI cut. Ready dependence alone does not demonstrate a
  combinational deadlock here. Inspect AR holding FIFO, descriptor occupancy
  and actual AR handshakes together.
* CVA6 grants MMU ownership only with no incoming scalar LSU request and an
  empty LSU bypass; ACC ownership ends on translation_valid. DTLB permission
  and PTW errors assert translation completion, and PMP forwards that valid.
  Exception-only ownership loss is not demonstrated by this source review.
  A stall needs mmu_state, bypass occupancy, scalar/ACC requests, translation
  valid/exception and PTW state to distinguish arbitration from translation.
* VLDU clears final-grant history on a new beat acceptance. Operand requester
  uses a registered stream, so a simultaneous grant may belong to the older
  beat; clear priority is necessary and is not by itself a lost-final-ack bug.
  Inspect both stream valid/ready pairs, per-lane final grants and byte counts.
* Sequencer can respond to a normal load after address-generation ack and
  required request acceptance, before all data is written. Global idle depends
  on per-PE completion. PC, zero DDR outstanding and scalar response therefore
  cannot substitute for VLDU/lane completion evidence.

The unused FPUSupportNone VMFPU elaboration still has two continuous vfpu_mask
drivers (unconditional tag assignment and no-FPU zero assignment). That is a
separate configuration defect, not the board's half/single/double setting.
Full-rootfs boot acceptance and routed CDC signoff remain open.

### FPGA-only compatibility follow-up

Scope is exclusively packaged RTL; main-source differences are not evidence
for this follow-up. Production RTL and the running board were not changed.

`lsu_bypass_probe.sv` instantiates the unchanged FPGA CVA6 `lsu_bypass`,
SHA256 `c8b0eebd8c800c6fa2307c35541792a9860dc596a8119ad5b5054a2d43dde008`.
The probe uses a valid bit plus a 256-bit opaque payload, not the full board
lsu_ctrl type. An independent queue oracle checks payload/valid and empty
credit over 64 rounds of stalls, simultaneous enqueue/dequeue, empty bypass,
two-entry occupancy/drain, pointer wrap, and flushing an occupied queue.
RTL and Vivado 2020.1 standalone synthesized netlist both pass 896 cycles:

* `/tmp/ara_lsu_bypass_rtl_20260930_02`
* `/tmp/ara_lsu_bypass_mapped_20260930_03`
* Windows: `D:/fpga_runs/ara_restore_probe_20260930/lsu_bypass_synth`

The first mapped attempt ran the testbench with inherited picosecond units
before global reset release. Explicit testbench timescale fixes that harness
error; it is not a DUT counterexample. No LSU source fix was necessary for
these tests. This reduces suspicion of the mixed dynamic whole-entry/valid
writes in this restricted configuration, but is not full LSU/MMU or routed
equivalence. Reproduction scripts are `run_lsu_bypass_probe.sh` and
`synth_lsu_bypass_probe.tcl`; NETLIST selects the mapped simulation input.

Remaining FPGA-only priorities are VLDU payload/final-write/completion state,
sequencer running/dependency updates, and dispatcher RESHUFFLE waiting on
both ara_idle and sldu_idle. A stuck completion bit, stale dependency or
unconsumed operand could block restore with DDR idle. These are falsifiable
hypotheses, not established bugs: sample the request acceptance, per-PE IDs,
both idle signals, SLDU state/operand valids and drain enable, and per-lane
VLDU grants in the same failing interval. The existing short mapped tests
do not include all this upstream history.

The simd_mul rounding temporary r is assigned only on VSMUL paths and was
the subject of historical latch warnings. Used bits are assigned in each
legal rounding mode before use; VMUL does not consume r. Source review alone
does not establish stale rounding data as a cause of the observed VMUL or
restore stall. Do not turn this historical warning into a Linux diagnosis.

### Main VMFPU no-FPU driver fix

At the user's request, only `hardware/src/lane/vmfpu.sv` moves the tag-based
vfpu_mask assignment into fpu_gen; no_fpu_gen retains its constant-zero
assignment. The FPGA RTL copy is intentionally unchanged. No arithmetic,
queue timing, or FPU-enabled connectivity is changed by this fix.

The queue harness accepts `VMFPU_SOURCE=hardware/src/lane/vmfpu.sv` and
`NO_FPU=1` to reproduce the disabled-FPU configuration. The unchanged FPGA
source still fails elaboration with ICSD on vfpu_mask in
`/tmp/ara_mfpu_single_driver_baseline_20260930`. Fixed main RTL passes all six
integer VMUL queue cases with no FPU in
`/tmp/ara_mfpu_single_driver_none_20260930`. The FPU-enabled configuration
also passes all six cases in `/tmp/ara_mfpu_single_driver_full_20260930`.
These are integer-path tests,
not a floating-point ISA regression or Linux boot acceptance.

### Frozen scalar follow-up (2026-10-03 Windows time)

`inventory_scalar_stall.tcl` exported the actual whole-design synthesized
bypass/load/store cells without changing or accessing the board. Source DCP
SHA256 is `28998c0c59ee7fa6880508caef119c6eb7b5841e577baf36ea2b98b324712fdb`.
Inventory: `D:/fpga_runs/ara_scalar_inventory_20261003`, copied locally to
`/tmp/ara_scalar_inventory_20261003`. These are functional cell netlists,
not routed timing simulation or whole-system equivalence.

`scalar_bypass_mapped_tb.sv` checks the actual 188-bit interface against an
independent queue oracle. Frozen RTL and whole-design mapped cell both pass
1792 cycles, including two entries, stalls, overlapping push/pop, wrap and
flush. Constant-specialized hypervisor fields and operation bit 7 stay zero;
operation values exercise queue payload transport, not instruction execution.
RTL result: `/tmp/ara_scalar_bypass_rtl_20261003` (the shared bench prints the
MAPPED marker in either mode). Final mapped result and input hashes:
`/tmp/ara_scalar_bypass_mapped_20261003_final`.

`scalar_load_mapped_tb.sv` passes five bounded control-path cases on the
whole-design load cell using Vivado 2020.1 primitive models:

* DDR load accepts despite a different commit ID.
* Translation exception escapes cache-grant wait.
* Translation exception escapes store page-offset conflict wait.
* TLB miss/abort followed by hit permits DDR load acceptance.
* A peripheral load waits for its commit ID and then proceeds.

Final evidence: `/tmp/ara_scalar_load_mapped_20261003_cacheack`.
Two earlier harness failures are retained, not counted as DUT failures:
`..._20261003` used the exclusive peripheral-range upper boundary as a
non-idempotent address; `..._20261003_final` omitted cache acknowledgment of
killed requests. Frozen `wt_dcache_ctrl.sv` asserts data_rvalid on kill;
the corrected model returns that acknowledgment with the accepted request ID.
This test does not validate the complete cache or arithmetic result datapath.

Reproduce mapped tests with `bash run_scalar_mapped.sh bypass|load CELL.v
UNISIMS_DIR NEW_OUTPUT`. Use exported cells and matching 2020.1 primitives;
the runner records input hashes and requires the final PASS marker, since
the simulator may return zero even after a testbench fatal error.

The board capture remains an unresolved Linux stall, not an acceptance pass.
The independent snapshot PC is `0xffffffff80015e9a`, matching the fourth
vector restore load (`vle8.v v24,(a4)`). Captured controls show scalar bypass
occupancy two with neither pop asserted, scalar MMU ownership, and a pending
vector MMU request. Frozen arbitration requires an empty scalar queue before
granting vector ownership. This explains the vector wait, not its root cause.

Required discriminating observations before a functional fix: scalar queue
head FU/address/transaction ID, load/store FSM, load-buffer occupancy,
page-offset conflict, scalar DTLB hit/PPN/exception, cache request/grant,
kill/tag/return ID, and commit transaction ID. These separate wrong queue
payload, missing cache completion, translation wait, store conflict and
non-idempotent commit dependency. Do not relax MMU ownership protection on
the basis of queue occupancy alone. Candidate-map PC/reset reconstruction
has unresolved alias interpretation; use the independent snapshot for PC.

An additional non-resetting snapshot at
`D:/fpga_runs/ara_stall_scalar_snapshot_20261003` confirms persistence:
cycles advanced from 18239880557 to 105092834195, while retired remained
1466845174, head PC remained `0xffffffff80015e9a`, and DDR transaction/byte
counters were unchanged with zero outstanding requests and zero errors.
This is evidence of sustained lack of architectural progress, not proof
that cache-internal transactions or their completion handshakes are healthy.

### Scalar/cache/MMU observation implementation (2026-10-03)

Persistent baseline evidence is archived under
`/home/wangwy/fpga_runs/ara_scalar_followup_20261003`.
Expanded inventory `D:/fpga_runs/ara_scalar_expanded_20261003_02` completed
without board access. It includes the actual `cva6_ptw` hierarchy, all three
WT read controllers, missunit and store buffer. The initial inventory did
not include the cva6-prefixed PTW; the second inventory corrects the selection,
not the design.

`plan_scalar_observation.py` resolves 416 unique physical bits in `profile_02`:
scalar queue FU/address/op/ID, MMU ownership, load-buffer occupancy, store
speculative/committed counts and valid bits, cache grants/cancellations/returns,
cache/PTW state registers, PTE return data, and vector request anchors.
Unavailable optimized/unused pins are listed explicitly, never decoded as zero.
FSM register encodings must be checked against the synthesized design before
assigning RTL enum labels. Required unresolved sources reject the profile.

`run_scalar_observation.ps1` was launched as Windows PID 14424 in
`D:/fpga_runs/ara_scalar_observation_20261003`. It verifies frozen inputs,
prepares observation-only probes and incrementally implements against the
original routed reference. It stops on a timing failure, or after timing
passes with `timing_passed_requires_probe_and_full_audit`. No automatic
bitstream generation or programming is enabled. Functional RTL is unchanged.
Do not report completion from the process launch; inspect `state.json` and
the physical-stage marker after the independent job finishes.

`capture_stall_ila.tcl` now accepts an optional expected probe width, keeping
579 as the legacy default. The scalar profile requires 416. Its mock tests
cover both widths and reject invalid widths before accessing hardware.
`audit_stall_ltx.py` checks final LTX coverage, ordering and exact names against
the candidate physical bits. Name mismatches require routed alias review;
even an exact name match is not proof of routed electrical connectivity.
The older 579-bit LTX has 45 name mismatches, recorded in
`previous_ltx_audit.json`; do not guess through its renamed PC/state buses.

Local verification: 16 Python unit tests pass for profile selection, existing
resolver and LTX auditing; preparation, implementation and capture Tcl mock
tests pass. Windows PowerShell 5.1 parses the launcher and reads width=416,
missing=0. These are tooling checks, not Linux boot or hardware acceptance.

### Parallel scalar tests (2026-10-03 Windows time)

The current frozen package passes the existing real bypass/load/WT-controller
contract in `verification/out/load-contract-current-scalar-parallel-20261003-01`:
22 logical requests, 18 completions, four cancellations, and 15 cache accepts
with 15 returns. Translation and cache storage are modeled; this does not
validate the real MMU/PTW or board liveness. The independent trace checker has
23 passing unit tests.

`run_scalar_store_probe.py` and `scalar_store_probe_tb.sv` verify the actual
RTL probe semantics. `no_st_pending_o` describes the committed queue only.
A speculative store can retain a page-offset conflict while that signal is
one; committing and granting it, or flushing the speculative entry, releases
the conflict. Result: `verification/out/scalar-store-probe-20261003-02`.
The earlier runner setup failure is retained in `...-01`, not a DUT failure.

Additional functional tests use the actual whole-design exported cells and
matching Vivado 2020.1 primitive models, without re-synthesis:

* `scalar_store_mapped_tb.sv`: 640 requests and 4353 checks pass, covering
  four-entry speculative/commit queues, ordered address/data/byte-enable
  transport, pointer wrap, address conflicts, grants and speculative flush.
  Evidence: `ara_scalar_followup_20261003/store_mapped_02` under the local
  FPGA run directory. Initial `store_mapped_01` incorrectly required the
  unused store `data_size` output to survive synthesis; the exported netlist
  ties it to zero. The WT store path uses byte enables. This initial failure
  is a test assumption error, not evidence of corrupted store data.
* `scalar_load_slots_mapped_tb.sv`: 640 accepted requests and 2048 checks pass,
  covering two occupied load slots, full-buffer backpressure, response ID/data,
  simultaneous old return/new allocation, reuse and suppressed flushed returns.
  Evidence: `ara_scalar_followup_20261003/load_slots_mapped_01`. Cache/MMU
  inputs are boundary stimuli; this does not prove cache-return delivery.

Reproduce using `run_scalar_mapped.sh store ...` or `load_slots ...`.
These results narrow the tested queue-corruption hypotheses, but do not rule
out history-dependent failures or physical timing effects. Board root cause
is still unresolved. In particular, the pending vector MMU request cannot be
granted while the scalar bypass queue is nonempty; the missing observation is
why its scalar head cannot pop. The 416-bit profile samples the distinguishing
load-buffer, scalar translation, store-conflict and cache/PTW signals. Do not
declare a store conflict, bad PPN or lost cache response from old probes alone.

### Board-address PPN attribution (2026-10-03 Windows time)

The subsequent investigation supplies evidence missing above. No functional
RTL or frozen implementation inputs were changed. Initial reconnection found
DONE=0, so the old stalled state was gone. The same hash-verified diagnostic
BIT/LTX and original Linux/rootfs were reloaded, reproducing the fourth-load
stall in `D:/fpga_runs/ara_scalar_reproduce_20261003_01`.

`read_current_restore.py` derives CPU0's current task from the original
Image's actual `task_curr` instructions, checks those bytes on the board,
and reads metadata and kernel page tables twice using single-beat JTAG.
It does not reset, halt, or write memory. The recovered symbols used
vmlinux-to-elf 1.3.6 with explicit RISC-V/64-bit and Image base
`0xffffffff80000000`; its initially guessed section base was incorrect.
The SDK's different rebuilt Image/System.map was not used as an address oracle.

Measured on the stalled board:

* Head PC `0xffffffff80015e9a`; retired count remains 1463289825 while cycles
  advance. Current task is `0xffffffd602803000`, with vector data pointer
  `0xffffffd602e10000`, matching the ILA's fourth-load address plus its offset.
* The following scalar reads use `task+0xb80`, `+0xb90`, `+0xb88`.
  Kernel root entry at `0x81c32ac0` is `0x3fbfbc01`; leaf at `0xfefef0a0`
  is `0x20a000e7`: a 2 MiB mapping to DDR, first scalar PA `0x82803b80`.
* The sealed MMU composition block produces PPN `0x3800`, not `0x82803`.
  PPN bit positions incorrectly reuse full physical-address slice positions.
  The reconstructed attribute address `0x03800000` falls in the NI peripheral
  range. `check_mmu_ppn_slice.py` reproduces this with the actual board values
  and the whole-design exported load unit: wrong PPN gives pop=0; supplying
  the correct PPN gives pop=1 under otherwise identical boundary inputs.
* New ILA capture again shows scalar bypass count=2, pop_ld=0, scalar MMU
  ownership, and the pending vector translation. The scalar load waits for
  commit eligibility; the older vector waits for the MMU; MMU handoff requires
  an empty scalar bypass. This closes the circular-wait explanation.

`patch_restore_order_control.py` is a diagnostic counterfactual, not a fix.
It reuses one NOP's space to insert FENCE rw,rw after the fourth vector load,
retaining all four vector loads and all metadata reads. The patched Image
SHA256 is `90d5b91e29e6547ec2d678a7c09f7f437b4742d16d51fdc97b6ff88fa4f60f06`.
QEMU reaches its shell; the SAME board bitstream now reaches the Linux init
marker in `D:/fpga_runs/ara_scalar_order_control_20261003_01/linux`.
This supports the causal ordering chain without waiting for a new bitstream.
The old serial-restore control did not insert a barrier after the fourth load.

Limits: the old ILA still does not directly sample scalar PPN/stall_ni or the
active TLB entry. Kernel page-table reads, exact source execution, mapped-load
tests, and the board ordering intervention are distinct evidence, not a claim
of directly measuring those internal signals. The general RTL repair must
also separate current-cycle PPN page-size selection from registered full-PA
selection. Original unmodified Linux and fixed RTL still require acceptance;
the diagnostic Image is not a production solution or proof of no other bugs.

Local evidence: `ara_scalar_followup_20261003/{current_task_01,
reproduce_capture_01,reproduce_linux_01,order_control_linux_01}` in the local
FPGA run directory, and `verification/out/mmu-ppn-board-address-20261003-01`.
Tooling tests: `test_read_current_restore.py` checks bounded address mapping,
the read-only pointer/page-walk path, pinned instruction bytes and patch extent.

Follow-up acceptance did NOT pass the full shell smoke. The first long UART
command suffered a reported input overrun and was truncated. The console
checker now supports explicit `--tx-gap 0.02 --clear-line`; defaults are
unchanged. With paced transmission, uname and /proc/cpuinfo succeed, and dd
reports 256 input/output records (1 MiB). The final hash/copy/cmp marker is
absent. Subsequent snapshots confirm a second stable stall, not a reason to
extend the timeout: PC `0xffffffff80b88582`, retired count 1929143758.

This is irqentry_exit's duplicated fourth vector restore load. The first
ordering control deliberately did not patch that site. Read-only collection
with `read_current_restore.py --site irq-return` finds task
`0xffffffd602803c00`, vector buffer `0xffffffd602e10000`, scalar VA
`0xffffffd602804780`, and the same 2 MiB leaf PTE. Correct PA is `0x82804780`,
correct PPN `0x82804`; the sealed composition predicts `0x4800`, hence NI
attribute address `0x04800000`. Two repeated collections are stable.
Evidence: Windows `...ara_scalar_order_control_20261003_01/irq_task` and local
`ara_scalar_followup_20261003/order_control_irq_task_01`.
The board is left at this second site. Do not call the one-site software
control a complete Linux fix. Four Python tooling tests pass, including
paced byte transmission and recognition of a real response marker.

### MMU PPN repair candidate (2026-10-03 Windows time)

Both the main CVA6 dependency and FPGA mirror now compose the early PPN
using the current DTLB page size and VPN bits beginning at VA bit 12.
The registered full physical-address path is unchanged. The two RTL copies
are byte-identical. This is a hardware repair, not a Linux fence workaround.

VCS evidence: `verification/out/mmu-ppn-repair-20261003-02`.
The extracted real MMU composition block feeding the old mapped load unit
passes eight directed addresses (including both measured board cases),
768 additional offsets, previous/current page-size transitions, bare
addressing, and a genuine NI access that must remain blocked before commit.
The same acceptance test against sealed old RTL fails at the first board
address: `verification/out/mmu-ppn-negative-20261003-01`.
These are boundary-controlled tests, not full MMU/PTW or board signoff.

`stage_mmu_fix.py` verified and cloned the 20260930 sealed package into
`/home/wangwy/fpga_runs/ara_mmu_fix_20261003/package`; only the MMU RTL differs,
plus new provenance and checksum entries. Staging preservation/tamper tests
and four existing diagnostic tests pass.

Windows task `AraMmuFix20261003` runs `build_mmu_fix.ps1` independently in
`D:\fpga_runs\ara_mmu_fix_20261003`. Startup was confirmed at `prepare_ip`,
PID 17992. It verifies the package, prepares IP, and runs synthesis with
existing gates, then stops for repaired-netlist and timing review.
It does not automatically program the board. Subsequent implementation,
bitstream audits, and original unmodified Linux board acceptance remain
required. The previous observation-only build passed timing but contains
no functional repair and must not be mistaken for this candidate.

### Reviewed physical continuation (2026-10-03)

The repaired synthesis `synth_bd388cff3f8a` completed, but the generic
`run.ps1` strict synthesis timing gate stopped it. Its setup WNS is
+0.501 ns with zero failing endpoints. Every one of the 15 failing hold
and pulse-width clock groups has exactly the same worst slack and endpoint
count as `ara_mainrtl_20260930/runs/synthesis_timing.rpt`.
Worst hold is -0.413 ns (Ethernet TX cross-clock, eight endpoints);
the -0.029 ns values are MIG PLL pulse-width checks, not bus-skew results.
The existing `check_rebuild_reports.py synthesis` comparative gate passes.
This defers these physical checks; it does not declare them fixed.

`continue_mmu_fix.ps1` runs as Windows scheduled task
`AraMmuContinue20261003`, with state/logs under
`D:\fpga_runs\ara_mmu_fix_20261003\implementation_reviewed`.
It verifies sealed inputs and reference hashes, reruns the synthesis
comparison, exports the actual repaired MMU netlist and PPN fan-in,
then uses existing `rebuild_mainrtl.tcl` to optimize the current synthesized
parent and reuse physical data from the hash-pinned 20261001 routed design.
No RTL or XDC is changed, and no synthesis rerun is requested.
The existing strict routed timing and route-integrity gates remain enabled.
Netlist functional review and release audits remain required before bitgen
and board acceptance; this continuation does not program the board.
Ten report-checker tests and eight Tcl rebuild scenarios pass.

### Actual mapped MMU composition check

`mmu_ppn_mapped_tb.sv` and `run_mmu_ppn_mapped.sh` simulate the unmodified
MMU cell exported from repaired full-design synthesis, with matching Vivado
2020.1 primitive models. The TLB response PPN/page size and previous-page
register output are forced boundary inputs; this is not a PTW/TLB lookup
or whole-system test. PPN output is never forced.
All 2,351 checks pass: both measured board addresses, three current and
three previous page-size combinations across 256 offsets, every PTE PPN
bit in 4K mode, and bare addressing.
Artifacts and source/primitive hashes are archived locally under
`/home/wangwy/fpga_runs/ara_mmu_fix_20261003/mapped_mmu{,_test}`.
The repaired full-design implementation reached incremental routing.
Board-definition lookup warnings and standalone-synthesis export IP blackbox
warnings remain review items: final linked design must have no unresolved
blackboxes and must retain complete board/IP constraints before release.
Do not infer Linux or post-route acceptance from this bounded mapped test.

### Post-route recovery tail

The reviewed implementation finished routing but failed the strict final
timing gate: WNS -0.007 ns, TNS -0.013 ns, two endpoints. Hold and pulse
width both pass at +0.005 ns. The worst reported path is UI reset
synchronizer stage 3 to AXI CDC write-channel spill data bit 38 CLR.
It is a 3.333 ns clock recovery check, with 3.778 ns data delay
(3.698 ns routing, 97.882%) and reset fanout 2,739. This supports a
post-route physical optimization trial, not a false-path exception.

`close_mmu_recovery.ps1/.tcl` starts from the preserved routed DCP,
checks that exactly two violating endpoints belong to that reset source
and AXI CDC CLR sinks within the reviewed -0.020 ns bound, then runs one
`phys_opt_design -directive Explore` pass and reroutes if needed.
The frozen board catalog must resolve and the netlist must have no
blackboxes. All final setup/hold/pulse and route-integrity gates remain
strict. No RTL/XDC edits, synthesis rerun, automatic retry or programming.
Seven mock gate scenarios pass; they do not establish physical closure.
Windows task `AraMmuRecovery20261003` writes to
`D:\fpga_runs\ara_mmu_fix_20261003\recovery_closure`.

Recovery closure passed: setup +0.019 ns, hold +0.005 ns, pulse +0.005 ns,
all with zero failing endpoints. Candidate SHA256:
`5a6b6873916b78148b97b1d5abfe4b9cd547294667d4fbd7a41c2587efe793fe`.

`release_mmu_fix.ps1`, task `AraMmuRelease20261003`, audits that exact
checkpoint using a separately copied tool package from the previously
validated 20261001 release. It does not rerun synthesis, placement, routing
or route-finalize. Full audit, strict timing/DRC/methodology/CDC regression
checks, and bus-skew evidence precede audited bitgen. Bitgen rechecks the
checkpoint/report hashes and retains native mandatory DRC.
Output root is `D:\fpga_runs\ara_mmu_fix_20261003\release`; expected final
artifacts are under `bitstream_host_ethernet`.
The scheduled task stops on any failed gate. It never programs the board,
and a generated experimental image is not Linux acceptance or complete
manual CDC signoff.

### Original Linux board acceptance (2026-10-04 Windows time)

The MMU-repaired release was programmed on target 210308A3B79F, xcvu9p_0.
BIT SHA256 `be34ef4f435eed0dd50553aaa5ea8a20ae41b0bdc8203bd52cc7bc2644c1a1ae`;
LTX SHA256 `397e46ddb318a29854cd24bf6bd955af9de20eb08ce3fcd0400131e0fa5511f6`.
Original Image/OpenSBI/DTB/initramfs hashes match the previously failing
baseline. No ordering-control Image or modified initramfs was used.

Evidence: `D:\fpga_runs\ara_mmu_board_20261004_01`; local copies under
`/home/wangwy/fpga_runs/ara_mmu_fix_20261003/board_acceptance`.
The first initialization stopped after a successful cold precheck because
Windows taskkill returned an error for an already-exited child. No firmware
or Linux had launched. With no remaining Vivado process, an unchanged
initialization retry passed (`ethernet_init_retry`), without reprogramming.
The original wrapper's failed state is preserved; use the subsequent
per-stage reports below for acceptance.

- `linux/report.json`: `passed_linux_init_marker`, execution started;
  original Linux 6.19.6 reaches /init, emits both init messages and a shell.
- 30,029,982 payload bytes transferred and read back in 3.0607133 seconds,
  9,811,432.52 payload bytes/s (not end-to-end boot time).
- `shell/report.json`: passed with 20 ms/byte command pacing. uname,
  cpuinfo, 1 MiB zero-file write, SHA256, copy and cmp all complete;
  response marker `ARA_SHELL_MEMORY_OK` and shell prompt are present.
- File SHA256 matches the host oracle:
  `30e14955ebf1352266dc2ff8067e68104607e750abb9d3b36582b8af909fcb58`.
- `after_shell/snapshot.json`: DDR error_count=0, read/write outstanding=0.
  Trap count is not expected to be zero for Linux; snapshot alone is not
  execution acceptance.

This passes the original boot and shell/tmpfs smoke workflow that previously
stalled. It is not exhaustive RVV instruction coverage, repeated cold-boot
reliability, peripheral coverage or long-duration stress signoff.
The board is left running the repaired image and original Linux shell.

### Extended live smoke: timer-command stall (2026-10-04)

Subsequent evidence is under `ara_mmu_board_20261004_01/extended_01` and
`timer_recovery_01`, with local copies in the board_acceptance directory.
The original boot/shell passes above remain valid, but are not stability signoff.

Passed on the same boot: 4 MiB /dev/urandom write, copy, bytewise cmp and
matching SHA256; 32 MiB zero-file write and SHA256 matching the host oracle
`83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`;
20 rounds of printf-to-wc pipelines, each producing 3, completed with exit 0.

The next command `cat /proc/uptime; sleep 2; cat /proc/uptime` printed
`2113.01 1627.77` once, then produced no completion within 120 host seconds.
A subsequent Ctrl-C recovery attempt received no UART bytes/prompt in 20 s.
This establishes a console stall at the sleep test, NOT its root cause;
timer/idle/interrupt and instruction/dependency failures remain to distinguish.
No reset, reprogramming, RTL edit or Vivado access was performed in this test.
The failure state is preserved. Cleanup and post-test diagnostics did not run;
40 MiB of test files remain in `/tmp/ara_smoke_92a323781bc0`.

## Isolated dual DDR plus Ethernet build (2026-10-04 Windows)

The live board remains on the single-DDR MMU-repaired release above. No
hardware connection, reset, serial access or programming is part of this build.
`stage_dual_ethernet.py` verifies every baseline SHA256 and creates a separate
package; it does not copy the dirty working-tree RTL over the accepted image.
Evidence/build root: `D:\fpga_runs\ara_dual_ethernet_20261004` (local root has
the same basename under `/home/wangwy/fpga_runs`).

- New `dual_ddr_ethernet` profile combines HOST, DDR2 and ETHERNET defines and
  generates both vendor MIGs. Original profiles remain separate.
- Combined RTL instantiates the Ethernet loader/arbiter only in Channel 0.
  Channel 1 bypasses that arbiter. Blindly combining the old macros would
  instantiate a second loader with disconnected external Ethernet pins.
- C1 covers `[0x80000000,0x100000000)`; C2 covers
  `[0x100000000,0x180000000)`. Ethernet downloads remain C1-only. This does not
  claim direct Ethernet downloads to C2. A separate updated Linux DTB and
  board acceptance are required before claiming Linux uses 4 GiB.
- Keep the repaired MMU and all other accepted CPU/Ara RTL unchanged. The
  only changed RTL files in the sealed package are board top and DDR wrapper.
- `check_ddr2.py`: 334 router response checks plus baseline/dual reset tests
  passed. `check_dual_combined.py`: actual staged wrappers, actual shared-DDR
  arbiter, stubbed vendor PHY/loader; exactly one loader and coupled resets
  passed. This is not PHY or board validation.

`build_dual_ethernet.ps1` runs detached, with one OOC job at a time to reduce
peak memory. It then runs synthesis, baseline-bounded physical-estimate review,
incremental implementation using the last accepted MMU-repaired routed DCP,
one post-route physical optimization pass, strict timing and the routed audit.
The reference is physical reuse only, never a substitute for the new netlist.

The synthesis gate still rejects negative setup, incomplete reports and new
or worse physical clock groups. It accounts narrowly for the duplicate MIG
clock names/counts and the new Ethernet generate scope. Baseline hold/pulse
estimates may proceed to placement; routed setup/hold/pulse/skew are not waived.
The old Vivado `Not started place_design` status after completed opt_design
is handled using the existing worker markers/checkpoint checks. Do not restart
successful synthesis because implementation or a later report needs review.

Audit artifacts are reused by the bitstream writer instead of regenerating
the same full report set for an unchanged checkpoint. New C2 CDC topology is
not automatically accepted by comparison with a single-channel baseline;
new findings stop for review, preserving the checkpoint and reports. Any
produced bitstream is retained on disk and never automatically programmed.

Progress: `Get-Content D:\fpga_runs\ara_dual_ethernet_20261004\state.json`.
Within implementation, `runs\stage.txt` records the current physical stage.

## Preserved loader stall: read-only follow-up

The earlier sleep-test label identifies the shell command group, not the
blocked syscall. Further evidence identifies `cat` in the current task's comm
field at offset 1696, established from the original kernel's `proc_task_name`
instruction at `0xffffffff80305b7e`. This supports a stall while starting the
second `cat /proc/uptime`, rather than a proven timer/nanosleep failure.

Evidence: `/home/wangwy/fpga_runs/ara_sleep_debug_20261004`, with source capture
`sleep_code_02` and new target capture `sleep_target_01`. The latter also exists
under `D:\fpga_runs\ara_mmu_board_20261004_01`. No reset, CPU halt, reprogramming,
program-memory write or RTL change was performed. Debug snapshot commands were
issued. The independent dual-DDR build was not modified.

- Retirement remains 8,949,988,642 with clock advancing. Last retired PC is
  `0x3f93ee6b4a`, instruction `0xd92fb0ef`: JAL to `0x3f93ee20dc`.
- Both complete 4 KiB pages match the original dynamic linker exactly, at
  file offsets `0x11000` and `0xd000`. Its RX PT_LOAD has equal file/virtual
  offsets. Load base is `0x3f93ed5000`; target is `__tls_pre_init_tp`.
- Target VA maps to PA `0x801660dc`, leaf PTE `0x2005985b`: valid, readable,
  executable, user, accessed. Memory page tables do not measure SATP/TLB.
- Each capture's 1040 DDR AR increments equal its 1040 diagnostic reads.
  These increments are not evidence of CPU progress.
- `head_pc` has no valid bit. The scoreboard clears issued/valid on retirement
  but retains PC. The eight instructions from `0x3f93ee6b32` through the JAL
  fit the eight-entry scoreboard wrap, consistent with an empty scoreboard;
  this does not directly measure emptiness or prove a frontend bug.
- Current LTX has JTAG AXI/VIO/MIG cores, no CPU pipeline ILA. Existing VIO
  status does not expose instruction queue, ITLB/PTW or scoreboard state.

`analyze_loader_stall.py --source SOURCE --target TARGET --loader LOADER
--image IMAGE` checks these captures offline, pins the original ELF/Image
hashes, decodes the actual JAL and rejects changed execution or inconsistent
pages. `test_analyze_loader_stall.py` covers positive and negative evidence
checks. Its success is evidence consistency, NOT RTL/board acceptance.

Static RTL candidates remain fetch/translation cancellation or starvation,
instruction queue/backpressure, and backend dependency/completion. In the
sealed ICache, KILL_ATRANS waits for fetch_valid and KILL_MISS waits for an
IFILL_ACK; the non-shared-TLB path prioritizes DTLB access and routes fill
updates using request-selection registers. No sampled signal establishes
that any of these conditions is the live blocker. Scalar stores after the
four vector stores precede the retired JAL, so the vector-store proximity
alone is not proof of a vector/scalar memory-order deadlock.

Do not patch a candidate or claim a root cause without a discriminating
reproduction. The current no-reset/no-image-change constraint preserves the
scene but limits direct internal-state observability.

### Mapped instruction-translation boundary check

`loader_ifetch_mapped_tb.sv` tests the actual exported repaired MMU, SHA256
`48d25b66c73eb0195eb293405b81c9d81625990f85e04d11fe6d3b18cbd5a2e8`, using the
matching Vivado 2020.1 unisims. VCS passed six checks in
`/home/wangwy/fpga_runs/ara_sleep_debug_20261004/mapped_ifetch_02/run.log`:
source/target/TLS-store PCs, user permission failure, ITLB miss without an
active walk, and hit recovery. ITLB output PPN/page-size/user/hit and inactive
PTW are forced boundaries; lookup, walk progress, caches, timing and whole-CPU
execution are not tested. This is not a reproduction of the board stall.

The first test attempt compared all PA bits and failed: the exported MMU
ties unused output bits [11:0] to zero. The sealed ICache forms its memory
address from the translated tag and saved virtual index/offset
(`cva6_icache.sv`, cl_tag_d and mem_data_o.paddr). The corrected test checks
only PA[55:12] plus valid/exception. This was a test-boundary error, not an
RTL repair. Both attempt logs are retained. Offline evidence tests: 10 passed;
existing read-current-restore tests: 4 passed. No root-cause fix is claimed.

### Captured page walk and external-invalidation collision

Follow-up evidence uses the same frozen `ara_mmu_fix_20261003/package`, not
the changing working-tree RTL. No board image or production RTL was changed,
and no synthesis/implementation was launched for this investigation.

`loader_ptw_mapped_tb.sv` exercises the existing MMU netlist without internal
forces, supplying captured PTEs through a controlled cache response model.
`mapped_ptw_02/run.log` under the evidence directory records four passes:
source and target cold walks take three PTE reads each, then target-next and
source-again hit. ASID and response latency are controlled test inputs, not
measurements of the stalled CPU. This checks translation logic, not the real
cache or instruction frontend. The initial `mapped_ptw_01` had a testbench
handshake sampling error; that failure is not a design defect.

The adapter test uses the real frozen `wt_axi_adapter`, `axi_shim`, arbitration
and FIFO RTL. Run from the repository with VCS on PATH:

```sh
python hardware/fpga/ara_dsa_vcu118/linux/diagnostics/run_inval_read_collision.py --package /home/wangwy/fpga_runs/ara_mmu_fix_20261003/package --out /tmp/unique_inval_original
python hardware/fpga/ara_dsa_vcu118/linux/diagnostics/run_inval_read_collision.py --package /home/wangwy/fpga_runs/ara_mmu_fix_20261003/package --out /tmp/unique_inval_candidate --candidate
```

Output directories must not exist. `--candidate` modifies only a copy in that
output directory, adding `~inval_valid_i` to read-ready gating. Source hashes,
compile log, per-case logs and results are retained. Original failures are
expected: VCS exit status alone is insufficient; explicit pass markers and
fatal messages are checked.

Results in `inval_rtl_02` and `inval_candidate_01`:

| External invalidation | Original | Isolated candidate |
| --- | --- | --- |
| None | Pass | Pass |
| Read beat 0, 1 or 2 | Corrupted returned line | Pass |
| Last read beat 3 | Four AXI beats accepted, zero load completions | Pass |

Cycle traces were added in `inval_rtl_trace_01` and
`inval_candidate_trace_01`, including ready, last, invalidate, capture,
metadata-pop and pending metadata. There are no internal forces.

The concrete defect is at frozen `wt_axi_adapter.sv:532`: read-ready masks
internal atomic invalidation but not external invalidation. The external
invalidation branch at line 556 suppresses D-cache read capture and completion
even when AXI RVALID/RREADY handshake. `axi_shim.sv:270` directly propagates
ready. A lost last beat leaves read metadata pending. Downstream,
`wt_dcache_missunit.sv:226` retains MSHR validity until load ACK, and
`cva6_ptw.sv:399` waits for the cache response to advance PTE lookup.

Connection to the real scene: four vector stores precede the last retired
JAL; a frontend walk is not serialized by scalar load/store issue gating.
The last CPU AR at `0x828597e0` covers the captured root PTE at `0x828597f0`.
The collision can therefore explain no external reads outstanding while an
internal page walk remains pending. Scalar stores retiring before the JAL
do not rule out an earlier frontend response loss.

Important boundaries: this is a confirmed adapter RTL defect under concurrent
inputs, not a capture of that collision on the physical board. The test's
invalidation address `0x83299f80` is representative near the last observed
write, not a sampled vector AW. Only the PTE beat is captured data; the other
three read beats are synthetic sentinels. Initial adapter test `inval_rtl_01`
incorrectly supplied an unaligned line request; `wt_dcache_missunit` performs
that alignment upstream, so the test was corrected before drawing conclusions.
Atomic/I-cache/multi-request regression and whole-CPU overlap reproduction
remain necessary before accepting a production fix. Existing LTX has no
internal CPU ILA to prove the exact stalled cycle. An attempted local read-only
routed-netlist export failed because Linux Vivado lacks the VCU118 device;
the collision result is RTL simulation, not routed-netlist confirmation.

#### Reachability verification with the real invalidation filter

The runner now supports `--filter 1`: instead of driving invalidation directly,
it connects frozen `axi_inval_filter.sv` and `fifo_v3.sv` to the adapter.
An accepted AW generates invalidation through the actual fall-through FIFO.
Depth 4 and line size 32 match `cheshire_soc.sv:888`. `--filter 2` sends the
same AW with the filter disabled. No internal signals are forced.

| Test group | No overlap | Overlap with each of four R beats |
| --- | --- | --- |
| Original, real filter enabled | Pass | Three corrupt lines; one lost completion |
| Original, real filter disabled | Pass | All pass |
| Isolated candidate, real filter enabled | Pass | All pass |

Evidence directories: `inval_filter_original_02`, `inval_filter_disabled_01`,
`inval_filter_candidate_01`. Original last-beat log records one accepted AW,
four accepted R beats, one invalidation, no load completion and pending read
metadata. Candidate last-beat log backpressures R during invalidation, accepts
it next cycle, returns one completion and clears metadata. The first filter
compile attempt used an incorrect typedef name; no result was inferred from it.

Static reachability checks in the frozen package:

- `cheshire_soc.sv:624` packs filter outputs directly into the accelerator
  response; `acc_dispatcher.sv:403` forwards them to the cache.
- `acc_dispatcher.sv:132` stalls scalar LOAD/STORE issue for pending vectors,
  not frontend translation. Fences have additional synchronization.
- `frontend.sv:217,250,373` resolves immediate JAL targets in the frontend;
  target fetching need not wait for JAL retirement. Its request at line 312
  depends on queue readiness and frontend halt; `controller.sv:324` asserts
  frontend halt for active FENCE.I, not simply a pending vector store.
- `csr_regfile.sv:2852` enables accelerator consistency on reset when enabled
  in configuration. CSR 0x7c2 can change it: live CSR state is NOT measured.
- `cheshire_pkg.sv:499` selects generic FIFO storage (`FpgaEn=0`), consistent
  with this test; do not enable stub-only FPGA RAMs to imitate the board.

These tests validate the real AW-to-invalidation path and prove an interface
defect, but do not execute the full loader/vector pipeline. Only AW is needed
by this filter; vector W/B traffic and actual wide data bus are not modeled.
The 16-byte representative write is not a capture of the board's vector AW.
Original Linux stall attribution still requires temporal evidence or a
whole-CPU instruction-sequence reproduction; no board repair is claimed.

### Integrated page-walk/cache confirmation

`run_loader_cache_chain.py` connects the exported MMU netlist to the frozen
full WT D-cache (controllers, MSHR, write buffer and RAM), AXI adapter and real
AW invalidation filter. The cache RAM uses the frozen Xilinx implementation
and Vivado 2020.1 XPM simulation model. No internal forces or mock load ACKs
are used. PTE values and target VA come from the preserved loader scene.

The driver requires `--package`, `--netlist`, `--models` (unisims), `--xpm`
(matching `xpm_memory.sv`) and a new `--out`. `--candidate` only patches the
output-directory adapter copy. It tests no collision, each root-line beat,
and a disabled-filter control. Check per-case pass/failure signatures, not
VCS exit status alone; the original design is expected to fail selected cases.

Initial three-case results (`cache_chain_original_04`): no collision and
disabled-filter controls pass. Last-beat collision gives:

```text
CACHE_CHAIN_STALL ar=1 r=4 ack=0 ptw=0 aw=1 inval=1 external_pending=0 mshr=1 adapter_pending=1
```

Thus the real MSHR remains occupied and the mapped MMU cannot finish the target
translation after external traffic has drained. In `cache_chain_candidate_01`,
the held last beat is accepted one cycle later; three PTE replies and twelve
AXI R beats complete translation to PPN `0x80166` in 33 test cycles. All three
candidate cases pass. A 1000-cycle bound detects noncompletion; it is not a
measurement of board stall duration. The retained MSHR/metadata and RTL wait
conditions explain why merely waiting longer cannot produce the missing ACK.

The subsequent six-case matrix (`cache_chain_original_matrix_01`) distinguishes
data corruption from lost completion: collisions at beats 0 and 1 still complete
this translation (those neighbour words are unused); beat 2 loses the selected
PTE and raises a page fault; beat 3 loses completion and stalls. No-collision and
disabled-filter controls pass. `cache_chain_candidate_matrix_01` passes all six
cases after external invalidation is included in R-channel backpressure. A
passing translation in the first two original cases does not mean their cache
line contents are correct.

Configuration readback capture was considered but not performed. XAPP1230
requires stopping the clocks associated with captured state throughout readback;
this conflicts with preserving the current live scene. Its UltraScale procedure
also does not establish support for this UltraScale+ device. Existing board
observations do not expose the historical RVALID/RREADY/invalidation coincidence.
Reference: https://download.amd.com/docnav/documents/XAPP1230.pdf (page 4).

Harness qualifications: this does not execute the loader instructions or the
Ara store pipeline, nor reproduce live cache/TLB contents or AXI latency.
Neighbour PTE words are zero placeholders, ASID is controlled, and the vector
write is represented by its AW. RAM `SimInit` is normalized to `zeros` in an
isolated wrapper copy: the frozen Xilinx RAM already unconditionally uses
zero initialization, but its assertion rejects the generic wrapper's `none`.
This is a simulation parameter consistency adjustment, not a production fix.
Earlier attempts retained compile-dependency and SimInit assertion failures;
none is evidence of a board defect. Production RTL and the current board are
unchanged. Physical-scene attribution still lacks an observed collision cycle.

### Dual-DDR C2 physical review and continuation

Windows review: `D:\fpga_runs\ara_dual_physical_review_20261004_01`.
Original build: `D:\fpga_runs\ara_dual_ethernet_20261004`.
Physical trial output: `D:\fpga_runs\ara_dual_physical_trial_20261004_01`.

The original synthesis completed with setup WNS +0.501 ns/TNS 0. New C2 MIG
hold groups are -0.402 ns (581 endpoints, same clock) and -0.173 ns (one
cross-clock endpoint). The worst reported path is calibration FIFO read enable
to the PHY RXTX_BITSLICE, with a 0.402 ns inter-SLR compensation and unplaced
estimates. This is not proof that routed hold will pass. C1's clock is now
`mmcm_clkout0_1`, whereas C2 is `mmcm_clkout0`; names alone do not identify IPs.

`review_dual_physical.tcl` opens the existing completed synthesis and inventories
all 582 negative C2 endpoints and clock sources. It fails on changed counts,
unexpected clock ownership or paths leaving C2. `check_dual_synthesis.py
--physical-review DIR` permits an implementation trial only for that narrowly
reviewed inventory; all other existing checks remain. It explicitly reports
`synthesis_timing_clean: false`; this is not a claim of clean synthesis timing.
No false paths, multicycle paths, uncertainty changes or routed waivers are added.

`queue_dual_physical.ps1` waits for the identified review process without manual
polling. Only a completed inventory can invoke `continue_dual_physical.ps1`.
The continuation verifies frozen inputs, reuses the completed synthesis and
the previously accepted physical reference, then applies existing strict
routed checks. Separate logs/checkpoints preserve the original failed gate.
It stops before release: CDC/DRC and functional-defect review remain, and it
never programs or resets the board. Use trial `state.json` and `stage.txt`
after the continuation starts, rather than the original stopped state file.

### Repaired dual-DDR build (2026-10-04)

The previous physical trial stopped in `opt_design`, not routing: MIG 66-99
identified C2 banks 40/41/42 driven from the C1 reference in bank 71, across
SLRs and I/O columns. Internal-only timing endpoints were insufficient to
establish a legal clock topology. Do not reuse that trial's physical deferral.

`stage_dual_repair.py` verifies the old combined package and changes only the
AXI return backpressure, C2 top-level clock wiring, project constraint list and
new C2 clock XDC. C1/SoC remain on E12/D12. C2 uses U21 Q1 AW26/AW27, bank 41,
250 MHz (UG1224, board clock diagram); MIG's 4000 ps input setting is unchanged.
The prior MMU repair and all other frozen baseline contents are retained.

Build bundle: `D:\fpga_runs\ara_dual_inval_clock_fix_20261004`.
`run_dual_repair.ps1` checks saved regression results, runs an isolated C2 MIG
synthesis/optimization using the actual generated vendor IP, and only then
starts `build_dual_ethernet.ps1`. This is an independent background process,
not an SSH-owned child. No programming, UART traffic or board reset is done.
The full build still requires the synthesis physical gate and strict routed,
CDC/DRC and release checks. A preflight pass is not routed timing acceptance.

The frozen repaired package passes six complete cache/MMU cases, five actual
AW-filter cases, five disabled-filter controls, and eleven direct-adapter
cases including sustained invalidation, I-cache and LR atomic read responses.
These tests compile the repaired production source without `--candidate`.
LR coverage does not constitute all-AMO coverage or a Linux hardware pass.

The repaired synthesis `synth_903503b5ace4` completed with setup WNS +0.501 ns
and TNS 0. Its initial physical gate stopped on the new `c2_sys_clk` group.
The read-only `physical_review_01` in the build bundle subsequently exported
all 34 negative paths in the four reviewed C1/C2 groups and their full clock
paths. C2's 16 reference-clock paths are MIG reset/synchronizer/counter paths:
their relative endpoints and individual slacks exactly match C1, worst -0.062 ns.
The one C2 cross-clock path is `sample_gts_reg` to `sample_gts_riu_reg`, inside
MIG calibration. C1 and C2 both have 0.141 ns data delay and 0.176 ns uncertainty;
reported unplaced clock skew is 0.072 ns versus 0.092 ns. Their hold slacks are
-0.154 ns and -0.173 ns. This supports an implementation trial, not a claim that
hold has been repaired. The old C2 -0.402 ns same-clock group is now +0.001 ns.
The -0.029 ns WPWS number is a pulse-width estimate, not bus-skew slack.

`check_repaired_synthesis.py` checks actual clock ownership, reference pins,
periods, C1/C2 endpoint correspondence, exact counts/slack envelopes and the
complete remaining physical-group inventory against the accepted baseline.
Its result explicitly keeps `synthesis_timing_clean: false` and
`routed_checks_relaxed: false`. Ten focused checker tests pass, and the actual
exported review passes. It requires `check_rebuild_reports.py` from the frozen
build tools beside it (or on PYTHONPATH).

`continue_repaired_dual.ps1` was launched independently on Windows at
2026-10-04 21:15 +08:00, output `implementation_reviewed_01` inside the bundle.
It verifies package and review identity, reuses completed synthesis and the
accepted `ara_mmu_fix_20261003/recovery_closure/candidate_routed.dcp` physical
reference, and retains strict routed timing, route-integrity, CDC/DRC and
release checks before bitstream generation. It never programs the board.
New continuation tools are separate from the original hashed tools; both
bundle and continuation `state.json` track the flow. This launch is not
evidence of implementation completion or hardware acceptance.

### Original-image cold retest (2026-10-04 evening)

After the user power-cycled the board and requested testing the old system,
the original single-DDR MMU-repaired BIT/LTX and all five original software
artifacts were hash-checked and reloaded. No new dual-DDR image was programmed.
Evidence: `D:\fpga_runs\ara_old_image_retest_20261004_01`; matching Linux-side
reports are under `/home/wangwy/fpga_runs/ara_old_image_retest_20261004_01`.

Ethernet initialization passed. Loading and readback of 30,029,982 bytes took
3.091462 s (9,713,844 bytes/s, not Linux runtime throughput or boot time).
Linux 6.19.6 reached /init and shell; the 1 MiB scalar file smoke passed with
the original expected SHA256. All 12 extended command groups completed:
4 MiB random write/copy/cmp/matching hashes, 32 MiB zero-file hash matching the
host oracle, 20 successful printf/wc pipelines, timer test, cleanup and status.
The `sleep 2` test returned this time (uptime 292.79 -> 295.25 seconds).
The earlier console stall is therefore not deterministic for this command
sequence; this does not disprove the static/simulation invalidation defect
or establish its direct involvement in the historical board stall.

The post-test snapshot has DDR errors=0 and both outstanding counts=0. Six
subsequent read-only commands (uname, uptime, meminfo, df, ps, root listing)
also returned exit 0 and a shell prompt. MemTotal is 2,001,736 kB, still the
single-DDR configuration. Extended temporary files were removed; the basic
smoke's two 1 MiB files remain. The board is left at the Linux shell.
No full-memory, RVV, long-duration, or new-RTL acceptance is claimed.

`test_mmu_board.ps1` retains its default busy-Vivado guard; its optional
`ImplementationPids` accepts only explicitly inspected offline batch build
processes with recognized implementation command lines. PIDs 9288 and 23824
were checked for this run; neither was stopped or reused for board access.

Later, after interactive miniterm use, the user authorized closing that terminal
and retesting. Only the matching COM6 miniterm Python process (14340) was stopped.
`extended_02` received no UART bytes/prompt in 15 s and sent no test commands.
`console_recovery_02` (Ctrl-C) and `xon_recovery_02` (XON/Ctrl-C/newline) each
failed to recover a prompt within 20 s. No reset or programming was performed.
Snapshots `unresponsive_02a` and `unresponsive_02b` are 40.519 s apart; retired
increases from 11,049,781,597 to 11,819,807,315, with changing PCs and DDR traffic.
Both show DDR error_count=0. This is console unresponsiveness, not evidence of
complete CPU retirement deadlock. The last interactive command is unknown.
The first snapshot was saved before an owned-process cleanup race reported
failure; the second collection exited successfully. Prior bounded passes
remain valid, but this retest did not reach its command sequence.

### Bounded stability campaign: real userspace fault

The user requested broader testing on the original single-DDR image, reloaded
under `D:\fpga_runs\ara_old_image_reload_20261004_02`. `linux_stability.py`
uses paced COM6 commands, unique private tmpfs files, fail-fast subshells,
host SHA256 oracles, per-step results and a continuously flushed UART log.
It neither reboots nor reprograms, and stops on failure without cleanup.
Its four host unit tests cover stage inventory, hash rejection and kernel
fault detection. The kernel-log rejection was added AFTER the following run;
the archived Windows script is the exact executed version.

`stability_01` planned 28 groups across three rounds. Twenty-three groups
passed, then `round3_metadata` returned exit 1. The final four groups were
not run. All three rounds of 2 MiB random copy/cmp/hash, 8 MiB zero hash,
8195-byte slices from file offset 4093, thirty printf/wc pipelines, and two
background hash processes passed. These file offsets do not prove CPU
misaligned-instruction coverage. Two rounds of metadata/reclamation and ten
one-second sleeps passed. This is a failed stability campaign, not signoff.

At kernel uptime 1383.584 s, `cat[598]` crashed while reading a tiny file in
the third metadata loop. Preserved file `g` contains `5\n` (sixth iteration).
Fault: EPC `0x3fb1a7d750`, mapping base `0x3fb1a6e000`, offset `0xf750`,
cause `0xd`, badaddr 0, a5=0. In the hash-matched dynamic linker this is
`_dl_next_ld_env_entry`: `ld a5,0(a0); mv a2,a0; ld a0,0(a5)`.
The faulting halfword is `0x6388`, matching the kernel instruction dump;
RA maps to `dl_main` at offset `0x11b88`. The preceding caller stores the
environment iterator at `s0-0x260` and passes its address. We have NOT captured
the value of that stack slot at the load cycle, so neither a bad stored
pointer nor a load/translation/forwarding error is yet excluded.

The kernel then reports Bad rss-counter state for MM_ANONPAGES=4 and
MM_SHMEMPAGES=33, plus non-zero pgtables_bytes=4096 on freeing mm. Their
relationship to the user fault is not established. Subsequent dmesg,
meminfo, interrupts, ps and directory queries pass; this is not a whole-core
deadlock. Failure snapshot: DDR errors=0, read/write outstanding=0. Its
snapshot file was saved before an owned-Vivado cleanup race reported failure.
Zero AXI response errors do not exclude silent data/coherency errors.

Evidence directories: `stability_before`, `stability_01`,
`stability_failure_snapshot`, `stability_failure_inspect`, and
`stability_failure_identity`, with local copies under the same Linux run name.
Board and host binary hashes match:
- dynamic linker: `3b4c54b64962c449f277bea8904fe0d52251e7b2c2531de994c2657129f816fd`
- BusyBox: `e6184ccf088b8f98f79343d87997fea6a522cf9f3612e65f90a41a46728032c8`

Do not attribute this fault to the known invalidation collision without a
discriminating reproduction. Next isolate repeated process startup/command
substitution from filesystem mutation, compare the exact binaries on a
reference runtime, and only then select the RTL observation points. Keep the
same bounded campaign as regression for a future repaired image; do not
hide the failure by lengthening timeouts or removing its failing stage.

### Expanded independent stability batches

`linux_stability_matrix.py` expands the existing runner using `--profile`:

- `storage`: 33 groups, sizes 0/1/7/8/63/64/65/511/512/513/4095/4096/4097/
  65535/65536/65537/1048576, 8/32/64 MiB tmpfs files with host SHA256 oracles,
  8 MiB random copy/compare/hash, and seven byte-offset slice cases.
- `process`: 13 groups including exit status, environment inheritance,
  repeated dynamic exec, command substitution/pipes, metadata mutation,
  hard/symbolic links, chmod, FIFO, background wait statuses and SIGTERM.
- `compute`: 13 groups including 64-bit shell arithmetic, an integer loop,
  exact-representable floating-point accumulation in awk, host-checked
  formatted data, numeric sort, base64, gzip and tar round trips.
- `timers`: 13 groups, forty one-second sleeps interleaved with four 8 MiB
  file/hash loads, and a final sixty-second idle/wakeup check.

Capability checks precede workload commands. File-offset tests are not ISA
misaligned-load tests; awk is not comprehensive FPU coverage. Explicit gaps
are recorded in every profile report: dedicated RVV/context, pthread/futex,
LR/SC/AMO, whole physical RAM, C2, Linux networking, external peripherals and
long-duration reliability. No external media or system files are modified.

`check_stability_qemu.py` uses the hash-pinned original kernel/initramfs and
validates the same command templates with process repetition count 3.
`/home/wangwy/fpga_runs/ara_stability_reference_20261004_02` passed all 72
groups (152.84 s of measured command time). The first reference attempt
caught CR/CRLF normalization in the test oracle, not a guest data error;
normalization was corrected and the full reference rerun passed. Six host
unit tests also pass. This is test-harness validation, not FPGA acceptance
or a full repeated-fault QEMU comparison.

The user requested broader/higher-volume testing after the previous real
fault. `run_stability_campaign.ps1` was launched independently on Windows
2026-10-04 23:39 +08:00 (PID 15260):
`D:\fpga_runs\ara_stability_campaign_20261004_01`.
It orders compute, storage, timers, process and uses process repetition count
200. Each batch hash-checks/reloads the SAME original single-DDR image and
software, completes the existing boot/shell smoke, then runs its matrix.
On workload failure it stops that batch, saves its log/report and a hardware
snapshot, and only then reloads for the next independent batch. Missing
snapshot or boot failure stops the whole campaign. After the final batch
there is no further automatic reload. It does not program the new dual build.

All scripts and the reference report are frozen/hashes recorded in the
campaign tools directory. Workload exit code, snapshot collection exit code,
DDR errors and each batch's pass state remain separate, including the known
owned-Vivado cleanup race. `state.json` is authoritative for current progress;
each `PROFILE/matrix/report.json` lists both planned and completed steps.
This entry records launch, not completion. Do not occupy COM6 or power-cycle
the board during the background campaign.

### Campaign failure: preserved cp loader stall (2026-10-05)

The campaign above stopped at its first batch's **boot/shell smoke**, before
any of the 72 matrix groups began. The kernel reached init; `uname`, cpuinfo,
the 1 MiB zero-file write and its correct SHA256 completed. The shell then
stopped before the final marker. It is not a compute-matrix arithmetic
failure or a failed Ethernet download (the 30,029,982-byte verified load
completed at 9.795 MB/s including readback).

Evidence roots are `D:\fpga_runs\ara_stability_rootcause_20261005_01` and
`/home/wangwy/fpga_runs/ara_stability_rootcause_20261005_01`. The board retains
the old single-DDR MMU-repaired image, BIT SHA256
`be34ef4f435eed0dd50553aaa5ea8a20ae41b0bdc8203bd52cc7bc2644c1a1ae`.
No reset, reprogramming, CPU halt or program-memory writes were performed.
Debug snapshot commands latch counters without freezing execution.

`read_stalled_task.py` checks the exact kernel Image hash and live structure
access instructions, reads CPU0's task, walks its memory page tables, and
captures the retired/target code pages using only single-beat JTAG reads.
`--context` additionally captures complete PTE cache lines, the saved kernel
and user stacks, and the last-write page. Separate output directories prevent
overwriting previous observations. `analyze_loader_stall.py --capture DIR
--loader ELF` validates raw reads, hashes, mappings and the decoded JAL.

Measured facts from `task_capture`, `task_context` and `task_stack`:

- Current task is `cp`, task VA `0xffffffd602803c00`, page-table root PA
  `0x82e4f000`. It has not reached the file-copy body.
- Retired count remains **1,606,944,382**; last retired PC is `0x3f869dfb4a`.
  Trap count remains 215200. Clock counters advance, counter freeze is off,
  watchdog is disabled, and DDR pending/error counters remain zero.
- The two complete 4 KiB code pages match the original loader exactly.
  Loader base is `0x3f869ce000`. Offset `0x11b4a` is `jal __tls_pre_init_tp`,
  targeting `0x3f869db0dc` (offset `0xd0dc`), not a wait loop.
- The target walk is `0x82e4f7f0:0x20b94001`,
  `0x82e501a0:0x20b80001`, `0x82e00ed8:0x2005985b`, giving PA `0x801660dc`.
  The initial last DDR AR, `0x82e4f7e0`, covers that root PTE. Subsequent
  diagnostic reads overwrite last-AR, so use the earliest capture for this
  comparison, not later snapshots.
- The three captures add exactly 2069, 3240 and 3767 DDR reads respectively,
  equal to their diagnostic operations; no extra DDR writes or retirement
  occur. UART silence is therefore accompanied by a real CPU-progress stall.

The historical saved user frame contains EPC `0x3f869e2506`, RA
`0x3f869dea7a`, SP `0x3fe60559a0`, syscall 214 and cause 8: these match the
loader's return from `brk(0)` into `_dl_sysdep_start`. The actual pinned
kernel's return instructions verify the 288-byte frame layout. Walking the
saved user SP gives PA `0x810319a0`; this page exactly matches the last-write
page. Stack slots at offsets 0x990/0x998 contain the saved `dl_main` pointer
and its caller return address. An inferred `dl_main` frame pointer of
`0x3fe60559a0` makes its final `sb zero,-0x73(s0)` address **0x8103192d**, exactly
the recorded last AW. This is mutually consistent memory/instruction evidence,
not a live register-file capture or a timestamped vector-store trace.

The full current PTE cache lines, including nonzero neighbours, were replayed
through the existing mapped-MMU + frozen D-cache/XPM RAM + adapter + real
invalidation-filter test. `run_loader_cache_chain.py` now accepts `--capture`
and `--loader`; it hashes the capture and records controlled AW timing/address
as such. No CPU/vector-pipeline execution is implied by this harness.

| Root read collision | Frozen original | Isolated RREADY repair |
| --- | --- | --- |
| None | Pass | Pass |
| Beat 0 or 1 | Translation passes; unused neighbour loss possible | Pass |
| Beat 2 (selected PTE) | Wrong PTE/page fault | Pass |
| Beat 3 (last) | Lost completion; permanent internal wait | Pass |
| Beat 3, filter disabled | Pass | Pass |

Valid runs: `cache_original_04`, `cache_candidate_01`. Original last-beat
trace has `ready=1 inval=1 capture=0`, four accepted R beats, no cache ACK,
no PTW reply, MSHR/adapter metadata still pending, external pending zero.
Candidate trace has `ready=0` on the conflicting cycle, accepts the held
beat next cycle and completes all three PTE reads (12 R beats) in 33 test
cycles. The production fix already being built is
`axi_rd_rdy = ~invalidate & ~inval_valid_i`.

Earlier attempts in this root caught Python 3.9 `zip(strict=...)` incompatibility,
a time-zero testbench memory lookup, and an incorrect low-address-bit checker.
They are not evidence of additional board defects. This mapped MMU ties unused
fetch-address low bits to zero; the I-cache uses the VA index, so the valid
translation checker compares PPNs. The final 21 host diagnostic unit tests pass.
The first task capture also reported a post-collection Vivado cleanup error;
later context/stack captures exited cleanly and confirm the same stalled state.

**Attribution remains open.** The adapter defect is independently confirmed;
its predicted symptoms agree with this capture and the earlier `sleep` stall
at the same loader offset. Current probes cannot observe historical
RVALID/RREADY/external-invalidation overlap or the live PTW/MSHR state. Do not
label the physical collision proven, conflate the earlier `cat` NULL-pointer
fault with this stall, or count the 72 unstarted groups as passing. Closing
that gap needs internal temporal observation or a controlled same-workload
hardware comparison. The ongoing dual-DDR build includes the repair but also
changes memory integration, so a later dual-DDR pass alone is not an isolated
causality experiment.

#### Full scalar/vector pipeline counterfactual

`cpu_original_04` and `cpu_candidate_01` now execute the actual captured
loader prefix, starting at offset `0x11ad0`, through the complete frozen
CVA6 + Ara RTL, real invalidation filter and Vivado 2020.1 XPM RAM models.
The fixture uses the captured code, PTE lines and saved stack mapping. Caches
start cold; argument registers are zero; independent AXI RAM ports replace
the board's interconnect/LLC/DDR latency. Those initial conditions are
controlled, not a historical capture of the board pipeline.

**The original fails with no collision scheduling at all (`collision=0`).**
Its own four vector instructions generate AWs at `0x810317e0`, `0x810318f8`,
`0x81031908` and `0x81031918`. The first store shares the root-PTE D-cache
index and invalidates it. Speculative fetch of the JAL target then walks the
page table while vector stores are still in flight:

| Simulation cycle | Observation |
| --- | --- |
| 271 | First vector AW; invalidation of root-PTE cache index |
| 276 onward | Frontend requests target VA `0x3f869db0dc` |
| 282 | Root-PTE cache line `0x82e4f7e0` read accepted |
| 285 | Second vector AW; PTE R beat `0x20b94001` handshakes but capture=0 |
| 286 | Next invalidation; final R beat `0x20b93801` handshakes, capture/pop=0 |
| 329 | Last retirement `0x3f869dfb4a`, exactly the board's stalled PC |
| 500 through 2190 | MSHR=1, target fetch pending, no RVALID or PTW reply |
| 20000 | Bounded stop; no target instruction retired |

The second vector AW spans two 32-byte cache lines, so the real filter emits
two invalidations. The adapter incorrectly leaves RREADY asserted while
giving these invalidations priority over read capture/completion. The
comment assuming no other transactions during coprocessor stores is false
for the speculative instruction-fetch page-table walk. Scalar load/store
interlocks do not prevent that frontend walk.

With **only** `axi_rd_rdy = ~invalidate & ~inval_valid_i` changed, the same
input and same natural AW timing reach target instruction `0x3f869db0dc`
at cycle 330. During the collision RREADY stays zero, then both held beats
are captured, metadata pops and the PTW replies. The additional scheduled
last-beat overlap case also reaches the target (cycle 346).

`cpu_chain_audit.json`, generated by `analyze_loader_cpu_chain.py`, verifies
identical memory/bootstrap/board configuration, identical frozen source
hashes and the single compiled DUT difference. It decodes the bounded FSDB
after `fsdb2vcd` conversion using `pyvcd==0.4.1`. Low-phase waveform cycle N
describes the signals sampled at edge N+1. The focused 2000-cycle window
shows 1691 consecutive sampled stalled cycles after cycle 500. VCS can exit
zero after `$fatal`; result parsing therefore requires the success marker,
actual target retirement and absence of fatal/error text.

VCS compatibility changes exist only in isolated simulation copies: fixed
XPM initialization declaration, removal of a Vivado-only input drive in the
outputless `unread` sink, and an initialized local instead of an unsupported
function-local unpacked-array constant. Both DUT variants use the same copies.
No production RTL or programmed board image was changed by this experiment.

This closes the **instruction-level reachability and causal-counterfactual**
gap: a naturally generated conflict reproduces the exact retired PC and last
root-page-table read, and a single arbitration repair removes it. It strongly
supports this mechanism for the preserved board stall. It still does not
constitute an on-chip recording of the historical conflict, a repaired-board
pass, or a result for the unstarted 72-group stability matrix.

The full-pipeline evidence auditor and related capture, loader-analysis,
stability and JTAG-control unit tests pass: 43 tests, including rejection of
changed inputs, extra compiled changes, stale adapter hashes and VCS fatal
messages with exit code zero.

#### Artifact lineage and nonfreezing recheck

`provenance_review` in the same evidence root retains the actual campaign
`program.log`/`inputs.json` and release bitstream/audit records. The campaign's
artifact record equals the release record, its audit hash verifies, and the
sealed package `SHA256SUMS` hash matches the recorded release input. Running
the sealed package's verifier passes all 876 exported files. The matching
LTX lists only JTAG AXI, MIG and VIO cores, not a CPU pipeline ILA. This is
artifact lineage, not a physical configuration readback comparison.

`live_recheck_01` captured another nonfreezing snapshot at
`2026-10-04T23:27:14.984309+00:00`. Since `task_stack`'s final snapshot,
cycles advanced by 118,435,660,349 (about 39.48 minutes at 50 MHz) while
retired=1,606,944,382, last PC=`0x3f869dfb4a`, trap_count=215200 and both DDR
AR/AW counters remained unchanged. Status is 7, watchdog snapshot is false,
and DDR errors/outstanding remain zero. This snapshot performs no memory
transactions and does not reset/halt/reprogram the core.

Reviewing the frozen miss-unit shows why further waiting or cache flush is
not a recovery mechanism: MSHR validity clears on a load ACK or reset;
ordinary invalidations do not clear it, and flush waits for an empty MSHR.
The physical board's internal MSHR remains unobserved; this is the RTL
explanation of the measured simulation, not a new hardware signal capture.

Further board A/B execution would end the preserved live scene and has not
been launched. Toggling CSR `0x7c2` is not an isolated equivalent of the
RREADY repair: it also disables scalar/vector memory interlocks. Do not use
a successful run with that CSR disabled to claim full consistency or an
isolated arbitration-fix proof. The current dual-DDR implementation is also
not a single-change comparator for the old single-DDR image.

## Dual-DDR implementation constraint loss (2026-10-05 Windows)

`ara_dual_inval_clock_fix_20261004/implementation_reviewed_01` stopped at
08:14 after routing: setup -4.300 ns / 36,531 failing endpoints, hold
-3.214 ns / 727 endpoints. No bitstream was generated or programmed.
The preserved synthesis includes the external-invalidation RREADY repair.

The actual generated implementation worker creates an in-memory `GateLvl`
fileset, without RTL `verilog_define`. The original `cdc.xdc` incorrectly
treats every existing `sources_1` as an RTL fileset. Its profile check fails
at the start of `ara_cdc::apply`. Vivado 2020.1 records this as
`CRITICAL WARNING: [Common 17-1548]`, continues optimization, and writes a
checkpoint missing the entire board CDC constraint application. The worker
log then reports numerous conflicting setup/hold paths and disables hold
fixing. The single-DDR physical reference was also rejected: 78.07% cell
matching is below the tool's 80% threshold, so this was not incremental P&R.

`review_dual_constraint_loss.tcl/.ps1` checks the frozen routed DCP, without
physical implementation, board access, or changing the original checkpoint.
Evidence: `D:\fpga_runs\ara_dual_route_review_20261005\review_01`; local
copies are under `/home/wangwy/fpga_runs/ara_dual_route_review_20261005`.

- Actual fileset: `MODE=GateLvl DEFINES=`; second DDR hierarchy is present.
- Hub clock is `mmcm_clkout5` (75 MHz), not VIO's `clk_50_clkwiz` (50 MHz).
  This independently confirms the final debug-clock step never ran.
- Native `before.xdc` has no `cdc_fifo_gray` constraints. Reapplying only
  timing constraints restores all 30 DDR max-delay groups and 20 Gray skew
  groups, without reconnecting the routed debug hub or relaxing 3 ns bounds.
- Reanalysis of the unchanged physical route reduces hold failures to 14:
  four MDM/MicroBlaze JTAG paths and ten small C2 MIG paths. Setup is still
  failing (-6.415 ns / 36,181 endpoints); this is not timing closure.
- Worst newly restored 3 ns path has 9.440 ns data delay, 9.152 ns routing,
  even though all its reported cells occupy the same slice. The existing
  physical solution must be reoptimized with the intended constraints.

The fix checks RTL defines only in `DESIGN_MODE=RTL`, retains explicit
profile/hierarchy validation, and records successful completion only after
the entire application finishes. `rebuild_mainrtl.tcl` also rejects a worker
log with swallowed constraint errors before placement/routing.

`rebuild_dual_cdc.tcl/.ps1` prepares an isolated corrected constraint set
against the existing `synth_903503b5ace4`, preserving sealed RTL/IP and old
results. `dual_cdc_preflight.tcl` checks 30 effective 3 ns datapath-only
exception groups and the hub/VIO clock before optimization, then repeats
effective checks after checkpoint serialization. It uses fresh physical
implementation rather than claiming reuse of the rejected single-DDR
reference or reusing the incorrectly constrained dual-DDR route.
All routed setup/hold/pulse/skew gates stay strict. Large residual failures
stop for review rather than launching a blind multi-hour physical retry.
Full CDC/DRC review and bitgen remain separate requirements; no automatic
programming is part of this flow.

Regression coverage includes RTL versus GateLvl single/dual profiles,
missing channel/reset/pointer protections, stale completion markers,
swallowed worker errors, and 11 effective-preflight rejection/pass cases.
Mock tests do not establish final hardware timing or board acceptance.

The corrected implementation was launched at 09:56 Windows local time on
2026-10-05 as scheduled task `AraDualCdcFix20261005`, under
`D:\fpga_runs\ara_dual_cdc_fix_20261005`. Its implementation worker is
`impl_cdc_d482b5a035f2`; the log confirms reuse of the existing synthesis and
all seven top-level IP runs. The task is independent of the SSH session.
`state.json` records wrapper status, `implementation/stage.txt` records the
current physical-design stage, and `implementation.log` retains tool output.
Launch is not timing closure: routed gates, the full audit and bitstream
generation still need their own successful results. The board is unchanged.

## Independent old-image board batches (2026-10-05)

The user subsequently authorized archiving the live stall and restarting the
original single-DDR system to exercise other workloads. This permission does
not program the dual-DDR build or assert that the old image's defect is fixed.

`run_independent_stability.ps1` runs compute (13 groups), storage (33), timers
(13), process (13, repetition count 200), then the original shell/copy smoke
as a fifth independent batch. `test_mmu_board.ps1 -BootOnly` still verifies
the original BIT/LTX, firmware, kernel, DTB and initramfs hashes, programs the
old image and checks the Linux init marker. It does not make the prior `cp`
smoke a prerequisite for every workload. Default callers still run that
smoke. Linux init alone is not workload acceptance.

Every batch gets a fresh original-image boot. A workload failure is recorded
and a hardware snapshot is saved before the next batch's reload. Missing
snapshot/identity evidence or a boot/transport failure stops the campaign.
Snapshot cleanup errors remain visible and prevent a batch pass. Individual
matrix results now mark success only after their exit status and output
oracle checks pass, including rejection of kernel faults.

Task `AraIndependentStability20261005` started at 10:16 Windows local time,
output `D:\fpga_runs\ara_independent_stability_20261005_01`. Tools are frozen
in the adjacent `_tools` directory. Previously collected root-cause,
campaign and first stability-failure files were copied with per-file hash
verification into `preserved_scene`, without modifying their originals.
`before_reset/snapshot.json` at 02:16:19 UTC still shows retired=1,606,944,382,
PC=`0x3f869dfb4a`, traps=215200, and DDR errors/outstanding=0. The old live
scene ended only after that collection and the user's explicit approval.

Six Python oracle/inventory tests pass. Windows PowerShell mocks verify
five-batch ordering, continued execution after a workload failure, no reload
after missing evidence or boot failure, and pass rejection for incomplete
results, acquisition errors and DDR errors. These checks validate the runner,
not the old bitstream. `state.json` and per-batch `matrix/report.json` are
authoritative for actual board results; launch is not completion.
The separately running dual-DDR physical implementation is not interrupted.
