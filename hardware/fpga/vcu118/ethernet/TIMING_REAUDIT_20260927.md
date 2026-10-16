# Integration and timing-change re-audit

Scope: current exported `host_ethernet`, including earlier timing repairs.
Conclusion: focused pre-synthesis checks pass; proceed to one new frozen full
synthesis. This is not proof of all workloads, vendor IP simulation, routed
timing, or board acceptance. No RTL/clock constraints were changed by this
audit. No new placement, routing or board operation was used as evidence.

Evidence root: `/home/wangwy/fpga_runs/timing_reaudit_20260927_0110`.

## Regressions and integration

| Check | Evidence and boundary |
| --- | --- |
| CDC FIFO timing changes | 9 width/depth configurations, cycle/state comparison, reset and backpressure |
| MIG return cut | 128 ordered 512-bit beats with stalls |
| Remap per-entry counters | 5 configurations, directed fill/drain and 10000 random cycles each |
| Address protection | 17,009,984 comparisons to original range calculation |
| Static source-ID partition | 584 protocol checks, plus 32 outstanding reads and writes with reverse-ID responses and 2-bit user fields |
| Dispatcher arithmetic | VLEN 64/1024/65536: 79648/110368/2174752 comparisons against pre-optimization arithmetic |
| Current dispatcher/sequencer | 68672 cycles, all 16 states, 9211 EEW metadata checks (151 first/2871 later segment) |
| VLEN casts | All 11 VLEN configurations; original/patched and unsigned reference |
| QBS fault LUT | 1024 boundary combinations and all 32 fault inputs; no added latency |
| Actual shared wrapper | Generated port contract, reset and UI-calibration-loss tests; vendor internals stubbed |
| Static whole profile | No non-vendor elaboration errors; Ara 5-bit ID extension and static partition checked |
| Loader XSA | 28 clock/reset/width/configuration checks; no private MIG |
| Host/export/flow | 97 Ethernet Python tests, 33 exporter tests, 42 offline managed-run scenarios |

The old dispatcher checker rejected this export because its `db90e341`
reference predates store completion, FP CSR busy and legality repairs. Added
explicit `--current-main` mode: capture current main sources, require the
reviewed transformation to match exported bytes, compare current state and
outputs, exercise WAIT_STORE_RESPONSE and retain the old arithmetic oracle.
Do not call the old-version rejection a DUT failure or reuse its old pass.
Current main already contains several earlier timing transformations; current
main/export agreement alone is not independent proof of those transformations.
The retained old arithmetic oracle and EEW/segment geometry assertions provide
additional coverage, but this is differential simulation, not formal proof.

Shared-DDR review: one C1 MIG; loader ID zero; Ara ID5 is zero-extended to8;
the mux source tag maps bijectively into MIG ID8. Both response channels
restore the source tag before demux. Individual channel casts preserve all
non-ID fields. Five mux spill stages, loader range/error path, sticky lock
and drain, reset topology and MIG R cut remain. Static mode removes the
dynamic ID-table capacity throttle, not downstream ready/backpressure.
Warm cache reload remains unsupported; cold-ROM and reserved-memory checks
are still mandatory. Integrated throughput/boot must be measured on board.

## Old netlist report classification

Reports copied from stopped `ara_combined_20260927_0320`, not the new candidate:

- All 9089 `no_clock` pins trace to five `dbg_hub/sl_iport*_o[1]`
  roots (1114/6158/265/1284/268). The hub is a synthesis-stage blackbox.
  The 45823 unconstrained maximum-delay pins are within JTAG/XSDB/VIO debug
  structures, including MIG calibration debug, not the new arbitration RTL.
  Require linked physical debug-clock coverage later; do not add false paths.
- Another 13 constant-clock endpoints are vendor PCS RX recovered-clock reset
  structures. Review their physical configuration after optimization.
- No multiple clocks, disconnected generated clocks or combinational loops
  were reported. Partial input delays name MDIO, JTAG and UART asynchronous
  inputs; sys_reset has its explicit asynchronous reset exception.
- All 481 reported critical CDC rows terminate inside generated loader vendor
  blocks (MAC/PCS, reset controller or SmartConnect). This is localization,
  NOT a vendor-wide waiver. Physical CDC review before bitgen must account for
  these structures and any new/user-owned crossing.
- TIMING-47's six clock-group findings are vendor MicroBlaze debug/BSCAN
  clocks. Do not introduce a blanket asynchronous group between management
  and UI, which share a source.
- The MDIO input's user 20-ns datapath budget is overridden by TEMAC's
  first-stage MDIO false path. It is NOT an effective bounded input path.
  Preserve the vendor synchronizer exception; review output pad timing and
  synchronization separately. No claim that all four pad budgets take effect.

## Authorized physical checks

Historical standalone `ara_loader_bd_cdma_02` reports, read without launching
new implementation, show:

| Specific check | Before placement/routing | Routed |
| --- | ---: | ---: |
| PHY IntTx_ClkOut0 to tx_pll_clk_out_DIV hold | -0.413 ns | +1.824 ns |
| MIG PLL_CLK to RIU_CLK MaxSkew | -0.029 ns | +1.041 ns |

PHY hold requirement remains 0 ns and uncertainty 0.177 ns. The physical
clock/data delays change. These reports support deferral, not current combined
signoff. The user now authorizes deferring only these categories at synthesis.
Other negative hold paths in the old whole-design report are NOT implicitly
authorized. Keep the next run synthesis-only and inspect the complete new
failure set before implementation. Never loosen uncertainty or blanket-waive
all hold/pulse-width failures. After routing all checks must close, with
DRC/CDC/exception/unconstrained-path review before bitstream generation.

## Snapshot handling

The mutable export inventory has six stale entries from reviewed follow-up
changes (host workflow docs, remapper, shared DDR, DDR wrapper, common script,
run gate). Do not copy its old checksums as evidence of current bytes. The
freezer records fresh hashes, validates matching BD/XSA/firmware and rejects
changes during copying. Verify the new frozen package before tool launch;
keep both earlier stopped snapshots unchanged.

New bundle: `D:/fpga_runs/ara_reviewed_synth_20260927_0116`, with the same
local archive under `/home/wangwy/fpga_runs`. All 866 files verified on both
hosts. Inventory SHA256:
`7d563753a07bec3c08e51df851974f3aba72d284d77da983c576a9beca357487`.
Matching firmware SHA256:
`26253345510d09f96ef2c5ebe1b6b3e9bae408936162689fad1105210cc47fa2`.
The prior main-RTL VCS image's 457 manifest entries were rehashed: zero changed
or missing files. This preserves the relevance of its recorded short program
regressions; those programs were not rerun as part of this timing audit.

Started independently through Windows process creation at
2026-09-27 16:17 (+08:00), wrapper PID25708, explicit `-Stage synth`.
A separate SSH connection confirmed `prepare_ip` and active Vivado PID14084.
No implementation/bitgen/programming is scheduled by this wrapper. Read
`state.json` after completion; do not restart it or edit the frozen inputs.
