# Combined build batch

## Scope and scheduling

User direction: integrate updated main RTL, Ara/CVA6/QBS/AKV, existing JTAG
debug/loading, and the tested J10 MicroBlaze/SGDMA/CDMA loader into one C1-DDR
profile before launching full synthesis/implementation. No OS, PCIe, dual-DDR
or new performance architecture is added to this batch.

The old host-only wrapper was stopped during IP preparation. It must not
resume automatically. Existing IP results are retained, not reset. The board
has not been reset or programmed during this integration preparation.

Short static checks, BD validation and focused simulations are preflight,
not additional full FPGA builds. One combined full build is the target, not
a guarantee of first-pass physical timing or board acceptance.

## Completed preflight

- [x] Export current main RTL and preserve the accepted MIG R-channel cut.
- [x] Add conditional loader/shared-DDR RTL and `host_ethernet` profile.
- [x] Validate a loader BD with its private MIG removed and external UI AXI.
  Actual generated boundary: address 32, data 512, no external ID pins.
  Final Tcl validated in `D:/fpga_runs/ara_loader_shared_20260927_03`;
  fresh import/OOC registration and XSA export passed in
  `D:/fpga_runs/ara_loader_import_20260927_03`. No synthesis was launched.
- [x] Add shared-clock AXI arbitration and 9-to-8 ID remapping using existing
  libraries, checked addressing before MIG truncation, sticky admission lock,
  drain acknowledgement, and loader transaction/error counters.
- [x] VCS focused protocol test: 72 response checks, simultaneous masters with
  identical IDs, burst/strobe correctness, out-of-range/4-KiB-crossing rejection,
  B/R backpressure during lock, permanent isolation and Ara traffic after lock.
  Includes stopped-clock asynchronous reset, lock clearing and reset with an
  accepted write still pending. Archived latest evidence:
  `../results/20260927_ethernet_integrated_preflight/`.
  This is not a physical DDR or full SoC test.
- [x] Static full `host_ethernet` hierarchy passes with vendor-IP exceptions.
- [x] Add Ethernet checkpoint identity gate and test 52 bitgen gate scenarios
  with mocks. Gate tests do not constitute an actual bitstream build.
- [x] Actual generated wrapper port contract plus reset/calibration-loss tests
  pass with VCS; PHY/vendor logic is stubbed, not simulated internally.
  UI reset also resets the loader subsystem, avoiding stale upstream DMA state.
- [x] Generate a new standalone BSP from the final shared-DDR XSA and link the
  integrated CDMA firmware with warnings-as-errors for application sources.
  Workspace: `D:/fpga_runs/ara_loader_shared_bsp_04`. Program headers, linker
  map and input hashes are archived with the latest preflight evidence.
  Code/control objects remain in BRAM; BSS is `0xFF000000..0xFF045F7C`.
- [x] Application limits enforced by integrated firmware and host sender;
  legacy raw DDR probe entrypoints disabled in the integrated firmware.
  Both standalone and integrated native protocol tests pass.
- [x] Ethernet verified-load, sticky lock/drain and shared JTAG launch path
  implemented. Ten host tests include real launch-helper failure-before-doorbell
  checks and Python/Tcl transport mocks. These are not board execution tests.
- [x] Packaged 8-KiB ROM binary reviewed and SHA256 pinned in `ara_load.py`.
  Require passive-loop PC, LLC scratchpad configuration, default platform ROM,
  zero prior Ara DDR activity/traps and exact live ROM matching before launch.
- [x] Actual XSA passes 28 generated-configuration/reset/clock checks;
  three checker tests include per-field corruption and private-MIG rejection.
  This metadata audit does not replace routed timing or physical CDC analysis.

## Combined build preflight closure

- [x] Place the validated/import-tested loader BD into the frozen combined package.
  Keep vendor files and generated outputs out of the mutable source tree.
- [x] Source/XSA review confirms one C1 MIG, one E12/D12 input buffer and shared reset.
  Review generated clocks, PHY/MDIO constraints, CDC/reset-domain crossings,
  generated-clock ancestry and interaction with the existing timing scripts.
  Added implementation-only late Tcl management/UI period checks and bounded
  MDIO/PHY-reset pad routing budgets; retained vendor serial/CDC constraints.
  Physical clock/CDC/IO signoff still requires the combined routed netlist.
- [x] Select matching ELF download through XSCT after fresh programming. The new
  `ara_init.py` rejects wrong ELF/hash/ranges, non-cold ROM and prior loader DDR
  traffic before download. Target-selection/failure tests pass in actual XSCT
  2020.1 with mocked board operations; no board access occurred in these tests.
  Fresh programming, then initialization, is the first-version recovery policy.
  Actual power-cycle recovery remains a board acceptance test, not preflight.
- [x] Freeze the complete source/IP/firmware/constraint inventory with hashes.
  Record concurrent main-RTL changes for the next batch, never mutate a live
  run's snapshot. Do not identify a dirty snapshot solely by Git HEAD.

Final bundle: `D:/fpga_runs/ara_combined_20260927_0320` (matching Linux archive
under `/home/wangwy/fpga_runs`). 864 files; inventory SHA256
`f9c3d85e0ce3b012230a90f648c823d24565864e5296021839b42a6dcc9e3c36`.
Earlier `0315` was a packaging-only preflight and was never sent to Vivado.
Windows bundle checksum/import/PowerShell-parser checks passed. Background
wrapper launch returned PID 8992. Inspect this bundle's `state.json` for the
current stage; do not restart the wrapper or edit its frozen inputs.

On-board cold-ROM checks, exact VIO discovery and network-load execution remain
acceptance tests after the combined bitstream exists. Use a dedicated link and
one loading client: the protocol identity exchange is not authentication.
After lock or a failed launch attempt, require a full reset before another load.

## Full flow and grouped fixes

1. Run the frozen combined synthesis and implementation once in a new directory.
2. Collect all available timing, bus-skew, DRC, CDC, unconstrained-path, resource
   and clock reports from the same checkpoint. A hard tool failure may prevent
   later reports; preserve the earliest real error and available diagnostics.
3. Review all reported problems together. Do not auto-retry, downgrade checks,
   increase timeouts blindly, or re-run synthesis just to regenerate reports.
4. Reuse a hash-matched audit for bitgen where the existing audited mode permits;
   retain native bitgen DRC. Any changed checkpoint/constraints invalidate reuse.
5. Software-only fixes require software rebuilding/testing, not FPGA synthesis.
   Constraint-only fixes may reuse synthesis after dependency checks, but must
   rerun affected implementation/audits. RTL/IP changes require a new build batch.
6. Board acceptance: identity/calibration; protected shared memory; network-loaded
   smoke execution; intentional trap; vector smoke; sustained 256-MiB readback
   and independent checks. Record integrated speed instead of inheriting the
   standalone ~10 MB/s measurement. Linux is a later acceptance point.

The combined flow is now launched (IP preparation precedes top-level synthesis
and implementation). This is not a completed synthesis, timing or board pass.
No bitstream generation or programming is automatic; grouped report review
follows routed completion. See `COMBINED_RUN.md` for the delivery/recovery scope.
