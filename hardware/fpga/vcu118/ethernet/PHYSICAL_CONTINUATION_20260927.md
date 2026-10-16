# Reviewed synthesis to physical implementation

The user authorized continuing through implementation and bitstream generation
if checks pass. This updates the earlier synthesis-only policy: the reviewed
remaining synthesis hold and MIG skew findings may be repaired physically.
It does not waive routed setup/hold/pulse/skew, CDC, DRC or timing coverage.

## Accepted input and remaining checks

Full synthesis `synth_3aac2309e5ae` completed. WNS is +0.501 ns with zero setup
failing endpoints (previously -0.260 ns / 636). The complete hold and skew
summary remains -0.413 ns / 137284 endpoints and -0.029 ns / 16 endpoints.
The failing clock categories match the preceding inventory, including the
separate -0.154 ns MIG UI-to-calibration hold path. Boundary and constraint
checks report zero failures. The old synthesis-only state remains `failed`:
it records the strict hold gate honestly and is not rewritten as all-pass.

Bundle: `D:/fpga_runs/ara_singleid_synth_20260927_2011`.
Inventory SHA256:
`2afcd0d742ea8a290c1b65131c01ace4ac8dbd4d6d2ca530b2c628aa287dd25a`.
Reviewed full synthesis timing report SHA256:
`3c680416e4bd25d0e34ff222fc395969454f3fecea89da4d293d1b086e3bbfef`.
RTL, XDC, firmware and the frozen package scripts are unchanged.

## Separate continuation

`scripts/continue_physical.ps1` requires an explicit physical-deferral switch,
the exact inventory/report hashes, the completed synthesis parent and a new
output directory. It locks the existing managed package and checks tool/input
integrity. It never fabricates `latest_synth.json`, resets IP or launches
synthesis. The normal managed-run timing gate is unchanged.

The Tcl continuation checks IP/parent freshness and live setup, loops and
multiple drivers, then creates a new implementation child of the completed
synthesis. It enables the documented `ExploreWithAggressiveHoldFix` post-place
physical optimization directive before routing, targeting the observed short
hold paths without changing RTL, clock frequency or timing exceptions.

After routing it checks route completeness, multiple drivers, loops, boundary
and constraint checks, and strict setup/hold/pulse-width summary. Full reports
and URAM/ready-fanout evidence are retained. Nonzero CDC Critical/Warning counts,
DRC/methodology findings or missing-clock/unconstrained endpoints cause
`review_required`; they are not automatically waived by vendor hierarchy or
severity. This is deliberately conservative: a warning need not be a design
error, but a human path/structure review may be needed before bitgen. Missing
or unrecognized report formats fail closed.

Only clean automated report review proceeds directly to `write_debug_probes`
and `write_bitstream`, with native bitgen DRC enabled. If report review stops,
the saved routed checkpoint can subsequently use the existing audited bitgen
flow after the outstanding findings have actually been reviewed. No board
programming or reset is part of either continuation path.

Offline validation: `tests/test_continue_physical.tcl`, 13 scenarios, including
negative setup/hold/skew, incomplete routing, multiple drivers, loops, CDC
findings, missing CDC report, coverage gaps and DRC/methodology findings.
Only the clean scenario reaches bitgen. Windows PowerShell parser and uploaded
continuation-script SHA256 checks passed. These are control-flow tests, not
physical timing acceptance.

## Active job

- Output: `D:/fpga_runs/ara_physical_20260927_2253`.
- Frozen continuation scripts: `D:/fpga_runs/ara_physical_tools_20260927_2253`.
- Started 2026-09-27 22:53 (+08:00), independent PowerShell PID10228.
- Vivado PID6620; implementation child name `impl_ae103fab57a4`.
- A separate SSH check confirmed the `preflight` stage and IP/parent reuse.
- `state.json` records wrapper outcome; `stage.txt` records the live Tcl stage.
- `inputs.json` records script hashes and explicit deferral authorization.

This is a launch record, not a routing or bitstream completion claim. Let the
detached flow finish without continuously polling or editing its inputs.

## Routed outcome and targeted repair

The first implementation completed routing with no route errors, but strict
routed timing failed: WNS -0.299 ns / 2002 setup endpoints. Hold and pulse/skew
passed at +0.004 ns and +0.005 ns. Of the setup failures, 1963 are in the
MIG mmcm_clkout0 domain, 26 are in Ethernet IntRx_ClkOut0, and 13 are in
other cross-clock groups. The worst Ethernet path loops across an SLR boundary
and spends 2.743 of its 3.045 data-path ns in routing. The worst sampled
mmcm_clkout0 path spends 3.057 of 3.974 ns in routing. The post-route optimizer
already reduced TNS but left these failures; this is not a script-parser issue.

The next isolated implementation keeps the same synthesized parent, IP and
hold-repair directive, but applies Vivado's `ExtraNetDelay_high` placement
directive. This specifically adds cost to long-distance/high-fanout nets before
routing, addressing both observed path classes. No RTL or timing exception is
changed. The existing routed setup/hold/pulse/skew and report-review gates
remain mandatory; the first failed run and all evidence remain untouched.

The net-delay continuation is running at
`D:/fpga_runs/ara_physical_netdelay_20260928_0832`, started 2026-09-28
08:30 (+08:00). It was detached through Windows process creation; PowerShell
PID15180 and Vivado PID5336 were confirmed during preflight. The first SSH
`Start-Process` attempt exited without running the wrapper and left only two
empty log files (`ara_physical_netdelay_20260928_082954.*.log`); it did not
touch the project. This is a launch record, not a timing or bitstream pass.

## Net-delay routed result and post-route closure

The net-delay placement completed routing and its child Vivado timing summary
reported WNS -0.014 ns, TNS -0.094 ns, 16 failing setup endpoints, WHS
+0.010 ns with no hold failures, and WPWS +0.005 ns with no pulse/skew
failures. All sampled worst paths are in the MIG 300 MHz domain, with
approximately 85-92% route delay, including the Ethernet DDR write spill to
the MIG upsizer and the existing AXI CDC FIFO spill registers. The earlier
Ethernet IntRx SLR-crossing issue is no longer a failing path.

The parent full-report run remains at `routed_reports` while writing its
diagnostics. A separate Windows PowerShell process PID12484 uses `Wait-Process`
on the parent wrapper PID15180; it does not poll or launch concurrent Vivado.
On parent exit it requires the exact reviewed 16-endpoint summary and the
expected failed timing gate before invoking `scripts/close_routed_setup.ps1`
on the immutable routed DCP. That script runs one post-route `phys_opt_design
-directive Explore` on actual routed delays, rechecks route integrity and
strict setup/hold/pulse timing, and writes a new DCP only on pass. It then
calls the existing checkpoint-only full audit. The audit still requires manual
CDC/DRC/methodology/coverage review before bitgen; there is no automatic board
operation or timing waiver. Output is isolated under
`D:/fpga_runs/ara_postroute_close_20260928`; launcher transcript is
`D:/fpga_runs/ara_postroute_after_20260928.log`.

Offline post-route closure control tests cover a clean pass, continued setup
failure, and a mismatched large failure set. They are not physical evidence.

## Post-route closure result (2026-09-28)

The parent net-delay run stopped at its strict gate, as expected for its 16
remaining setup endpoints. A separate Vivado 2020.1 session then opened that
fully routed checkpoint and ran one post-route `phys_opt_design -directive
Explore`. It optimized 12 cells/nets without adding or removing cells, for
reported WNS/TNS gains of +0.014/+0.094 ns. The independent timing gate on
the resulting fully routed design reports WNS 0.000 ns / 0 failing setup
endpoints, WHS +0.010 ns / 0 failing hold endpoints, and WPWS +0.005 ns / 0
failing pulse-width endpoints. No timing exception or RTL change was made.

The new checkpoint is
`D:/fpga_runs/ara_postroute_close_20260928/ara_dsa_vcu118_routed.dcp`
(501144758 bytes, SHA256
`523e80416d02bc84ac4b6d8afd469c4d381da0b7b5147fdc0b2d47eea0bd1277`).
The zero setup margin is narrow; the saved checkpoint, not the earlier routed
run, is the candidate for further checks.

The checkpoint-only full audit started at
`D:/fpga_runs/ara_audit_20260928_170251_e9fa7ae578b6`. Its output and
manual CDC/DRC/methodology/coverage review are still pending. The earlier
net-delay routed report has no DRC Errors or Criticals, but it contains
Warning/Advisory findings; its CDC report contains Critical classifications,
mostly inside generated Ethernet MAC/PCS and control IP, plus the pre-existing
`fabric_ready` fanout. Those are not automatically waived by timing closure.
At this stage, no bitstream or board programming had been performed by the
post-route continuation.

## Audited bitstream candidate (2026-09-28)

The checkpoint-only audit completed at
`D:/fpga_runs/ara_audit_20260928_170251_e9fa7ae578b6` with
`AutomatedChecksPassed=true`. It independently confirmed max/min slack
0.000/+0.010 ns, zero route errors, zero multiple drivers and combinational
loops, complete routed Gray bus-skew coverage, and zero constraint/boundary
check failures. Its timing summary also reports WPWS +0.005 ns and zero
setup/hold/pulse-width failing endpoints. This is physical timing closure with
no positive setup margin, not functional or CDC signoff.

The audited checkpoint was used to generate
`D:/fpga_runs/ara_postroute_bit_20260928/ara_dsa_vcu118.bit` and matching
`.ltx`. Vivado's native bitgen DRC completed with 0 Errors, 0 Critical
Warnings, 1597 Warnings and 9 Advisories. `bitstream.json` records the exact
audited checkpoint and output hashes; the bitstream is 80159227 bytes. No
board programming or reset occurred.

The audit CDC classifications are unchanged from the pre-optimization routed
report: 711 CDC-1, 3 CDC-4, 11 CDC-10, 8 CDC-11, 3 CDC-12, and 3 CDC-13
Critical findings. The CDC-1 findings divide into 455 in generated Ethernet
BD MAC/PCS logic and 256 in generated VIO control logic. Two CDC-11 findings
are the existing `fabric_ready` fanout. The DRC and methodology findings are
Warning/Advisory, including DSP pipelining suggestions and BSCAN timing
methodology. These classifications have not been suppressed or declared
functionally harmless. Treat this image as an **experimental board-validation
candidate**, not a production CDC signoff.

## First integrated board smoke (2026-09-28)

The candidate bitstream and matching LTX were programmed on VCU118 through
the Windows Vivado 2020.1 hardware server. The JTAG inventory found one
`xcvu9p_0`, two JTAG AXI cores, one MIG and two VIO cores. The board reached
`BOARD_READY status=e`. The initial programming helper pulsed board VIO reset
after configuration; the debug RTL froze on that SoC reset edge, so
`ara_init.py` correctly rejected its cold guard with `COMMAND=1`. No firmware
or application was downloaded on that attempt. A separate first-programming
mode (`--cold-no-reset`) now leaves the board VIO reset low. The same bitstream
was reprogrammed once, reached READY and passed the cold guard.

Vivado's LTX split the 256-bit Ethernet status VIO input into multiple probe
objects, including individual bits. Both host transport copies now reassemble
the value using each probe's port bit offset and width, rejecting gaps,
overlaps, unexpected ports and a missing `ETH1` magic. This correction is
software-only; the bitstream was not rebuilt. The fixed host tools ran from
`D:/fpga_runs/ara_postroute_overlay_20260928`, leaving the frozen build
package unchanged.

The matching MicroBlaze ELF SHA256 was
`26253345510d09f96ef2c5ebe1b6b3e9bae408936162689fad1105210cc47fa2`.
`D:/fpga_runs/ara_postroute_init_20260928_03/report.json` records
`firmware_ready`: integrated hardware identity and ROM hash matched, Ara and
loader DDR transaction counts were zero before firmware download, the CPU was
in the audited passive ROM loop, XSCT started MicroBlaze, and network INFO
reported the expected application range.

`D:/fpga_runs/ara_postroute_smoke_20260928_01/report.json` records the first
integrated `host_smoke.elf` pass: 4800 ELF/BSS bytes over J10, zero packet
retries, readback verified, fresh run ID 1217378766, `done=1`, `result=0`,
zero traps, zero Ara DDR errors and no outstanding Ara DDR transactions.
The loader's AW/B and AR/RLAST counts balanced with zero errors. Its status
was locked and isolated both before launch and afterward; reloading requires
fresh bitstream programming, not a SoC reset. The measured 0.93 MB/s over
4.8 KiB is a short-transfer figure, not sustained throughput. The large
loader AR/RLAST counts include firmware/DMA traffic and are not payload bytes.
Vector smoke, sustained 256-MiB transfer, Linux boot and full physical CDC
signoff remain open. The board currently holds the new image in the locked
post-smoke state.
