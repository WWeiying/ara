# Complete setup inventory and fixed-ID protection repair

## Evidence and scope

Full synthesis: `ara_reviewed_synth_20260927_0116`, run
`synth_2f3b0486045d`, Vivado 2020.1. The tool completed synthesis; the timing
gate failed. No implementation or board operation followed.

Reports are retained in `/home/wangwy/fpga_runs/ara_reviewed_synth_20260927_0116`.
`tests/inspect_synth_paths.tcl` reopened the existing project without launching
synthesis or saving changes. Windows output is `D:/fpga_runs/ara_paths_20260927`.
`setup.tsv` enumerates 636 distinct failing endpoints (limit 2000, not reached),
matching the original summary. `setup_all.rpt` contains their full paths.
`hold_by_clock.tsv` samples up to five paths per destination clock; it does NOT
enumerate all hold endpoints. `complete.txt` records inspection completion.

## Setup: two endpoint groups, one common source cone

| Endpoint group | Failing endpoints | Worst slack | Best failing slack |
| --- | ---: | ---: | ---: |
| Loader SmartConnect `m00_exit/.../w_reg` | 580 | -0.260 ns | -0.141 ns |
| Protection `i_range/i_aw_spill_reg` | 56 | -0.024 ns | -0.024 ns |
| Total | 636 | -0.260 ns | -0.024 ns |

All 636 paths start at the protection demux's AW per-ID in-flight counters.
The SmartConnect group comprises 577 data/sideband register CE pins and three
control register CE pins. The AW spill group comprises address31, length8,
cache4, QoS4, protection3, size3, burst2 and lock1 pins. This classification
uses the entire enumeration, not an extrapolation from the first 50 paths.

All failing setup endpoints are in the 300-MHz MIG UI domain. The Ara 50-MHz
domain has WNS +1.983 ns; the loader 100-MHz domain has WNS +7.244 ns.
These are synthesis estimates, not routed acceptance.

The protection used `AxiLookBits=8`, creating 256 counters per channel.
`axi_demux_id_counters.full_o` reduces all of their full/overflow flags;
`axi_demux_simple` feeds this into AW/W acceptance. The resulting cone drives
the upstream SmartConnect W register enable and AW spill enables. The worst
full-design path has 14 logic levels and 3.926 ns estimated data delay.

The real `ara_eth_loader` adapter drives both request IDs to zero. The generated
loader master has no request ID pins. This permits a fixed-ID specialization:

- Add `LoaderSingleId`, default off; enable it only in the actual wrapper.
- Use one lookup bit (two counter groups) instead of eight (256 groups).
- Retain the library demux, capacity, overflow protection and target ordering.
  Do not enable `UniqueIds`: repeated ID0 transactions are not unique.
- Preserve `MaxTrans=32` and five-bit counter width. The existing per-ID full
  threshold is 31, not a newly claimed 32 simultaneous transactions per ID.
- Retain address checking, error slave, isolation/drain, all mux spill stages,
  response ID expansion and the static source-ID partition.
- Simulation assertions require the specialized loader request IDs to be zero;
  the static full-profile check verifies the elaborated protection parameters.

Falsifiable prediction: the 256-way counter-full reduction disappears or
shortens under unchanged timing constraints. Compare request/response/status
outputs cycle-by-cycle, including capacity, simultaneous completion and
same-ID DDR/error-target ordering, before accepting the timing result.

## Hold: not covered by the setup repair

Summary: 137284 failing endpoints, WHS -0.413 ns. Counts below come from the
complete clock tables, not the five-path sampling limit.

| Clock/path category | Failing endpoints | Worst hold |
| --- | ---: | ---: |
| Ara/host 50 MHz | 114809 | -0.072 ns |
| Loader management 100 MHz | 14464 | -0.090 ns |
| Ethernet IntTx_ClkOut1 | 4879 | -0.098 ns |
| MIG calibration mmcm_clkout6, intra-clock | 2355 | -0.098 ns |
| Ethernet IntRx_ClkOut0 | 510 | -0.084 ns |
| MicroBlaze debug DRCK | 158 | -0.062 ns |
| Ethernet RIU | 52 | -0.091 ns |
| Ethernet IntTx_ClkOut0, intra-clock | 31 | -0.057 ns |
| MIG infrastructure sys_clk | 16 | -0.062 ns |
| PHY IntTx_ClkOut0 -> tx_pll_clk_out_DIV | 8 | -0.413 ns |
| MicroBlaze debug UPDATE | 1 | -0.031 ns |
| MIG UI -> calibration `sample_gts_riu_reg/D` | 1 | -0.154 ns |

The 300-MHz UI intra-clock hold paths have +0.021 ns slack and no failures.
Representative other-domain failures are zero/one-logic-level short paths,
including a host counter's own CARRY8 feedback and vendor FIFO address pins.
Most representative intra-clock reports show 0.145 ns unplaced clock skew.
These are physical min-delay/clock-tree checks, not evidence that reducing
clock frequency or shortening the AW setup cone will fix hold. Do not add RTL
delay padding or false paths to make the synthesis summary green.

The UI-to-calibration hold path is a separate -0.154 ns check, not the
previously authorized MIG PLL/RIU MaxSkew exception. Before advancing, obtain
authorization for physical handling of the additional reviewed hold categories.
Until then keep the conservative full-design gate and do not launch implementation.
Final routed acceptance still requires all setup, hold and skew checks to pass.

## Other gates

- 16 negative pulse-width-table endpoints are MIG PLL_CLK/RIU_CLK **MaxSkew**,
  worst -0.029 ns. Do not describe them as actual too-short clock pulses.
- User Gray bus-skew report has no violated paths; boundary and constraint
  checks each report `FAILURES=0`.
- DRC: 1717 Warning/Advisory findings, no Error/Critical Warning findings.
  This is not a blanket DRC waiver or a bitstream approval.
- CDC: 481 Critical rows: MAC/PCS 476, reset controller3, SmartConnect2.
  This matches the preceding audit's localization, not a vendor-wide waiver.
- `check_timing`: 9089 no-clock pins and 45836 unconstrained endpoints remain.
  The prior audit identifies the synthesis-blackbox debug hub domain and 13
  vendor constant-clock reset endpoints. Physical debug-clock coverage and
  exception/CDC review remain mandatory; negative setup enumeration does not
  cover unconstrained paths.

## Candidate validation

Evidence: `/home/wangwy/fpga_runs/eth_single_id_20260927`.

- Specialized/generic protection: 2541 cycle comparisons, 588 protocol checks.
  Includes concurrent Ara/loader traffic, byte strobes, bursts, invalid ranges,
  isolation/drain, reset, and same-ID DDR/error requests with stalled responses.
- Generic ID-remap protocol: 76 checks; static-partition generic protection:
  588 checks. Both retain their original supported ID coverage.
- Counter comparison: 4189 checks, 454 full-capacity observations and 520
  simultaneous push/pop cycles. Both lookup widths retain identical outputs.
- Existing reverse-ID response test: 32 outstanding reads and writes, 2-bit
  user metadata and backpressure; passes without enabling single-ID mode.
- Existing remap differential test: five configurations pass.
- Whole-profile static elaboration: no non-vendor errors; 33 exporter tests pass.

The first added ordering test incorrectly required upstream AR/AW ready to stay
low despite the existing spill buffers. Corrected the test to check that the
error target is not issued early and to consume responses in order; no DUT
ordering change was made to satisfy that test.

An isolated paired synthesis completed successfully (exit 0) at
`D:/fpga_runs/eth_single_id_20260927_ooc`, 2026-09-27 20:04 (+08:00). Both sides use the
static ID partition and actual loader adapter constants; only LoaderSingleId
differs. Same part and 3.333-ns clock, no vendor PHY/MIG or upstream SmartConnect.
Reports and checkpoints were copied into the local `timing/baseline` and
`timing/candidate` evidence directories.

| Paired OOC result | Baseline | Candidate |
| --- | ---: | ---: |
| WNS | +0.331 ns | +1.077 ns |
| Setup failing endpoints | 0 | 0 |
| WHS | +0.071 ns | +0.071 ns |
| WPWS | +1.391 ns | +1.391 ns |
| CLB LUTs | 3941 | 2176 |
| CLB registers | 4692 | 3178 |
| Worst-path logic levels | 10 | 7 |
| Worst-path data delay | 2.906 ns | 2.160 ns |

Both worst paths traverse the protection counter-to-AW-spill enable cone.
This supports the causal hypothesis, but even the original isolated design
passes: upstream SmartConnect loads and the actual clock tree are not modeled.
The OOC result cannot prove the full 636 endpoints close or fix physical hold.
The original snapshot's `inputs.json` predates a generator label correction:
its `changed_blocks` label incorrectly says remap. The actual `compare.tcl`
uses the same current remap source in both variants and varies only the
LoaderSingleId generic; the source hashes and actual script are authoritative.

A file-by-file comparison of the current exported RTL manifest against the
last full-synthesis snapshot finds exactly two changed files: shared DDR RTL
and its wrapper parameter. No Ara main RTL or earlier timing repair changed.
No new full-design synthesis, implementation, constraint waiver or bitstream
generation has been started for this candidate.

## Subsequent authorized full synthesis

The user subsequently requested another global synthesis attempt. A new
immutable snapshot was frozen at
`/home/wangwy/fpga_runs/ara_singleid_synth_20260927_2011` and uploaded to
`D:/fpga_runs/ara_singleid_synth_20260927_2011`.
Both hosts verified all 867 inventory files. Inventory SHA256:
`2afcd0d742ea8a290c1b65131c01ace4ac8dbd4d6d2ca530b2c628aa287dd25a`.
Firmware remains
`26253345510d09f96ef2c5ebe1b6b3e9bae408936162689fad1105210cc47fa2`.
Against the preceding full build, only the two reviewed RTL files and three
audit documents differ; timing constraints and executable build scripts match.
The frozen profile also passed non-vendor static elaboration.

At 2026-09-27 20:12 (+08:00), an independent Windows process (PID8136)
started `run_combined.ps1 -Stage synth`. A separate SSH connection confirmed
`state.json` at `prepare_ip`, `BoardModified=false`, and active Vivado PID9108.
IP preparation will be followed by full synthesis and its report/gate checks.
This is a launch confirmation, not synthesis completion or timing acceptance.
No implementation, bitstream generation or board access is scheduled. The
conservative gate is unchanged, including the unresolved hold-policy question.
Let the detached process finish; do not edit its frozen inputs or continuously
poll/restart it. Read `state.json` and `flow.log` in the new Windows directory
when checking the result.
