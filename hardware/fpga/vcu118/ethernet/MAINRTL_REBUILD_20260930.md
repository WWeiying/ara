# Main RTL integrated rebuild, 2026-09-30

## Frozen inputs

- Linux bundle: `/home/wangwy/fpga_runs/ara_mainrtl_20260930`.
- Windows bundle: `D:/fpga_runs/ara_mainrtl_20260930`.
- Profile: `host_ethernet`, unchanged 50 MHz Ara target.
- Archive SHA256: `1935b28fd03b959736b88c724c7cbdbaaeff1194737f8ea8b77169479fb0173a`.
- Inventory SHA256: `9dfee610630bfc5f1087ba687a05e946623abd4d569ff7417c6565f9e1cb61dd`.
- 875 frozen package files verified on Linux and Windows.
- Firmware SHA256 remains `26253345510d09f96ef2c5ebe1b6b3e9bae408936162689fad1105210cc47fa2`.
  BD, XSA, ELF and firmware metadata were copied together from the preceding
  Windows build; unrelated temporary artifacts were rejected by hash checks.

Compared with `ara_valu_fix_20260928/package`, exactly six RTL files changed:

1. `ara_dispatcher.sv`: effective destination ELEN legality, blocked segment
   store completion, empty-segment reservation cleanup, verification assertions.
2. `lane/vmfpu.sv`: previously tested queue write workaround and no-FPU
   single-driver repair.
3. `sldu/sldu.sv`: scalar-only slide operation must not consume a younger operand.
4. `fpnew_opgroup_multifmt_slice.sv`: current main dependency's conversion-token
   participation and mask handling.
5. `control_mvp.sv`: current main dependency's exact division remainder handling.
6. `norm_div_sqrt_mvp.sv`: current main dependency's rounding/overflow flags.

Constraints are byte-identical to the preceding build. Board DDR arbitration,
single-ID protection, AKV/QBS FPGA adaptations, VALU repair and prior timing
changes are preserved. This is a new dirty-source snapshot, not a Git release.
Conflict-checked export synchronization retained local documentation and saved
a backup under the exported package's `.fpga_sync_backups` directory.

## Checks and automation

- Export tests: 33 passed. Synchronization tests: 26 passed.
- Full `host_ethernet` static hierarchy: no non-vendor elaboration errors.
  Xilinx primitives/IP remain for Vivado to elaborate.
- New report-gate unit tests: 10 passed; Tcl control-flow tests: 5 passed.
- Report parser also checked against real preceding synthesis and CDC reports.
- Windows PowerShell syntax check passed before launch.

`rebuild_mainrtl.ps1` runs IP preparation, fresh synthesis, physical-gate review,
incremental implementation, one full routed checkpoint audit, report comparison
and audited bitgen. It does not call the ordinary all-stage wrapper or fabricate
an all-timing-passed synthesis record. Setup must pass. Only already-reviewed
hold/skew clock categories at no worse slack are deferred; cross-clock and
pulse/skew failing endpoint counts may not increase. New categories stop the job.

The physical reference is the last VALU-fixed routed checkpoint:
`D:/fpga_runs/ara_valu_release_20260930/ara_dsa_vcu118_routed.dcp`, SHA256
`e0c84074b6ebe8e3f510ee2e1556b5cd1f2df90c87974430f31ae2cdcb397f76`.
Fresh synthesis and optimization produce the authoritative netlist; only then
is `read_checkpoint -incremental` used before placement and routing. There is
no retry loop, RTL retuning, clock relaxation or timing exception addition.

Routed setup/hold/pulse and route integrity must pass. The checkpoint audit
retains driver, loop, boundary, Gray-bus skew and constraint checks. Release
requires timing coverage and DRC/methodology gates, plus a detail-row comparison
of Critical/Warning CDC findings including clock context and full pin paths.
New/changed rows stop for review even if total counts match. Existing CDC
findings remain unresolved; passing this comparison permits only an experimental
bitstream, not production CDC signoff. Audited bitgen verifies report/checkpoint
hashes and keeps native bitgen DRC, without repeating the complete audit.

## Launch and status

Detached Windows supervisor was created through WMI, PID 22188. This is a
launch record, not synthesis, timing, bitstream or Linux acceptance.

```powershell
Get-Content D:\fpga_runs\ara_mainrtl_20260930\state.json
Get-Content D:\fpga_runs\ara_mainrtl_20260930\runs\stage.txt
Get-Content D:\fpga_runs\ara_mainrtl_20260930\flow.log -Tail 25
```

Do not edit frozen inputs or restart the same directory. Failure preserves
evidence and sets `stopped_for_review`. Successful output is under
`bitstream_host_ethernet`, with hash manifest. No programming, reset, UART,
network board traffic or automatic Linux launch is performed.

Earlier focused VMFPU tests and representative regression passes are useful
evidence, but the long `vfncvt_int8` regression timed out and full Linux remains
unaccepted. A new bitstream must still be tested on the board with the original
Linux image and root filesystem before claiming that the boot stall is fixed.

## Checkpoint-only continuation, 2026-10-01 Windows time

Fresh synthesis completed with WNS +0.501 ns, zero setup failures, WHS
-0.413 ns and WPWS/MIG skew -0.029 ns. The synthesis physical inventory
gate passed. `opt_design` then completed at 03:51:06 (+08:00), including
its final DRC report, with zero Errors/Critical Warnings. Its checkpoint is
`runs/impl_3d28a8eb257a/ara_dsa_vcu118_opt.dcp`, 216861484 bytes, SHA256
`76d4a5e292602f09e3b6bdbfb5277c47e8a7b67302c8e96216df78eedec8e2c9`.

The supervisor incorrectly expected `opt_design Complete`; Vivado 2020.1
reported `Not started place_design` for this intentionally partial run. Thus
the optimization worker had exited but the controller kept waiting. No placement
or routing occurred during that wait. The fix waits for worker completion and
requires both end markers, no error markers, an appropriate STATUS and a
nonempty optimized checkpoint. It explicitly opens that optimized checkpoint.

After verifying the exact PID/command, clean completion markers, checkpoint
hash and absence of other Vivado workers, only the waiting controller PID12676
was stopped. Its old supervisor PID22188 exited and retained the failed state;
neither old inputs nor old logs were overwritten.

New tools were uploaded to `D:/fpga_runs/ara_mainrtl_resume_20261001` and checked
by SHA256 and the Windows PowerShell parser. Detached supervisor PID6208 was
started with `-ResumeOptimized`, the exact optimized checkpoint hash and a new
continuation directory. Eight Tcl control tests (including the real partial-run
status, missing/error markers and no rebuild on resume) and ten report-gate
tests passed. The original package/inventory and reference hashes are rechecked,
and the synthesis report gate is rerun before physical continuation.

The old successful routed DCP remains the **physical reference**, not the
authoritative logic. The new optimized DCP supplies the actual netlist and
archived constraints. Incremental placement/routing, strict routed gates, full
audit and experimental bitgen remain scheduled, with no automatic board access.

Current status command:

```powershell
Get-Content D:\fpga_runs\ara_mainrtl_resume_20261001\state.json
Get-Content D:\fpga_runs\ara_mainrtl_resume_20261001\runs\stage.txt
```

This continuation launch is not a claim of placement, timing or bitgen success.

## Routed checkpoint finalize recovery (2026-10-01)

The continuation completed placement/routing. Its audited setup/hold/pulse
minimum margins were +0.011/+0.004/+0.005 ns. Bitgen subsequently stopped on
21 PSLT-1 violations in the MIG AXI CDC destination AW/W spill registers:
missing ADV_USEFUL_SKEW on pulsed latch loads. Vivado explicitly requested
`route_design -finalize`. This is not evidence of an RTL functionality failure.

The authoritative input is
`D:/fpga_runs/ara_mainrtl_resume_20261001/runs/ara_dsa_vcu118_routed.dcp`,
SHA256 `e01976b076dce0bee24be98e3145296ce9b8e27530669212dad19cef7025f88c`.
Neither that checkpoint nor the original frozen package is overwritten.

`finalize_routed.ps1` and `finalize_routed.tcl` implement a separate recovery:

1. Verify and read-lock the specified checkpoint; refuse concurrent Vivado.
2. Copy frozen tooling into a new tool-only package, overlay the reviewed PSLT
   gates, and record input hashes. No RTL or working-tree XDC is loaded.
3. Record PSLT before repair, finalize once, and save a new routed checkpoint.
   Finalize may adjust routing; it is not assumed to be metadata-only.
4. Require zero PSLT and fully/error-free routing. A fresh audit process reopens
   the new checkpoint and checks PSLT again along with the full report gates.
5. Compare timing/coverage and detailed CDC rows against this continuation's
   already audited CDC report, whose hash was checked against its manifest.
6. Use audited bitgen, retaining live PSLT/driver/timing and native bitgen DRC.
   Any failure stops the supervisor; there is no automatic retry or programming.

The deployment directory must contain the two finalize scripts,
`check_rebuild_reports.py`, and an `overlay` directory containing the updated
`common.tcl`, `audit_support.tcl`, `audit_routed.ps1`,
`write_profile_bit.ps1`, and `write_profile_bit.tcl` from `../scripts`.
Pass `-SourcePackage`, `-Checkpoint`, `-SHA256`, `-BaselineCDC`, and a new `-Out`.
The tool-only package is for checkpoint operations, not a source-build package.

Detached supervisor PID26556 and Vivado PID15096 were confirmed started on
Windows at 17:53 (+08:00), with output in
`D:/fpga_runs/ara_mainrtl_finalize_20261001`. This is a launch record, not a
finalize or bitstream success claim. Known CDC findings still require manual
review; Linux and board acceptance remain open.

Validation: four finalize control scenarios, four rejecting/accepting PSLT
gate scenarios plus diagnostic collection, 34 checkpoint audit scenarios,
eight rebuild scenarios, 56 profile bitgen scenarios, ten report-gate unit
tests, Windows audit/bitgen wrapper tests, PowerShell parsing and wrong-input
SHA rejection passed. Tool mocks do not establish hardware timing correctness.

```powershell
Get-Content D:\fpga_runs\ara_mainrtl_finalize_20261001\state.json
Get-Content D:\fpga_runs\ara_mainrtl_finalize_20261001\finalize.log -Tail 20
```
