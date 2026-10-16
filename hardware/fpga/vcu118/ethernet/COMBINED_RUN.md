# Frozen combined flow

`freeze_ara_build.py` snapshots the exported package and integration tools,
validated loader BD, final XSA, matching firmware ELF and its build metadata.
It computes hashes of actual input bytes, including uncommitted changes, and
rejects concurrent modification during copying. It does not launch Vivado.

Run `run_combined.ps1` from that independent bundle root. It verifies the
inventory, prepares only required IP, then runs `host_ethernet` synthesis only
by default (`-Stage synth`). It does not advance to implementation even if
synthesis passes. `-Stage all` is a separate explicitly selected mode. The
2026-09-27 review resumes synthesis first; implementation requires path-level
review of that new result (see `TIMING_REAUDIT_20260927.md`).
It refuses an existing flow state instead of resetting
or automatically retrying a run. `state.json`, `flow.log`, `runs/` and package
reports remain available after the SSH connection closes. A routed completion
is not permission to program: review timing, bus skew, DRC, CDC, pad constraints
and unconstrained paths from that checkpoint first. No automatic bitgen or
board operation is included.

The automated synthesis timing gate remains conservative: setup, hold and pulse-width checks must all
pass before implementation. Missing timing paths or an unreadable summary fail
closed. A standalone implementation request rechecks its synthesis parent, so
an old completion marker cannot bypass this policy. Routed timing is checked
again. Failed runs keep their reports and checkpoints but are not accepted.
The user has authorized deferring only the identified vendor PHY hold and MIG
MaxSkew checks until physical implementation. This is not a global hold/skew
waiver: an automated stop requires review of actual failing paths before any
implementation release. No report values or vendor constraints are changed.

The `ara_combined_20260927_0320` run used the earlier policy and was stopped
on request during implementation on 2026-09-27 (+08:00), after synthesis timing
failed. Its state is `stopped_synthesis_timing_failed`; the board was not modified.
The frozen bundle remains unchanged and must not be used to restart the flow.

## Firmware and cold launch

After a reviewed combined bitstream has been freshly programmed, use the
bundled `ethernet/ara_init.py` with `--elf ethernet/artifacts/fast_probe.elf`,
the `firmware_sha256` from the bundle's `snapshot.json`, matching `--probes`,
a new `--out`, and `--fresh-bitstream-confirmed`. Supply absolute Vivado/XSCT
paths if they are not in PATH. This is a deliberate board-changing operation:
the script validates ELF32 MicroBlaze load segments and hashes, checks the
integrated hardware/ROM and zero loader traffic, closes Vivado transport, then
selects exactly one MicroBlaze and resets/downloads/starts only that processor.
Its success additionally requires the integrated network INFO response.
It never launches an Ara application. Inspect its `report.json` and `xsct.log`.

For the reviewed VCU118 six-wire SGMII subsystem (100 MHz MAC management
clock), add `--prepare-phy-clock` when initializing after cold programming.
This opt-in operation enables external PHY3 D3[14] before the firmware's
DMA/PCS reset sequence, after the same cold-board and zero-DDR guards.
PHY IDs, D3 mode and write readback are checked; failure prevents firmware
download/launch. MDIO addressing and divider state are restored. Do not run
the Tcl helper directly against a running system or use this flag for other
PHY/clock configurations.

On 2026-09-30 the same VALU-fixed bitstream and original firmware recovered
UDP INFO twice after cold programming using this ordering (first diagnostic,
then integrated tool). Evidence:
`D:/fpga_runs/ara_restore_probe_20260930/integrated_preclock_init`.
The preceding diagnostic Linux image transferred 30029982 bytes including
readback in 3.065351 seconds with no retransmissions. These results validate
the tested initialization/transport path, not full Linux/BusyBox boot.

Then use `ethernet/ara_load.py --elf software/host_smoke.elf --probes ...
--full-reset-confirmed --out ...`. It performs network verification, sticky
hardware isolation/drain, fresh run controls and the existing JTAG doorbell
launch. Keep a single loading client and do not run a UART debugger concurrently.

The first integrated recovery procedure is **fresh bitstream programming**,
not just a SoC reset: VIO's lock output may remain high across SoC reset, and
firmware state must be re-established. A locked or previously active loader is
rejected by initialization. No unchecked unlock or warm-reload path is exposed.
Board initialization, power-cycle recovery and network-loaded Ara execution
remain unvalidated until this combined image is tested physically.

## Constraints

One Ara-owned C1 MIG and E12/D12 input buffer remain. The loader XSA has no
private MIG or input buffer; its clock wizard uses that buffered 250-MHz input.
Management is 100 MHz, shared UI is 300 MHz, Ara is 50 MHz. SmartConnect and DMA
retain their generated CDC constraints. No broad asynchronous clock group is
introduced between these related clocks. UI loss resets the loader subsystem
as well as the shared arbiter.

`ethernet_timing.tcl` is implementation-only, late-loaded Tcl. It requires the
actual management/UI periods and MDIO endpoints, and adds the reviewed 20-ns
management pad routing budgets without changing TEMAC's own MDIO multicycle
rules. These are not a complete PHY source-synchronous timing model. Generated
PCS/LVDS constraints retain ownership of serial I/O clocks. Report and review
exception coverage/overrides and physical CDC in the combined netlist.
