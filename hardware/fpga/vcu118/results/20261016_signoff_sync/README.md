# Signoff Mainline to FPGA Source Refresh

## Version Boundaries

- Reference RTL: `ara_dsa_signoff_integration`,
  `5ee02215edd65967040c837e786b7e1f668fcc36`.
- Main RTL and reproducible dependency patch import: `f1160620`.
- Previous FPGA source checkpoint: `50ace3fa`, annotated tag
  `fpga-pre-signoff-20261016`. This tag preserves the old package, templates,
  constraints, build scripts and diagnostic source, not generated Linux/Vivado
  outputs. It is a source checkpoint, not a new hardware acceptance result.

The source update uses `prepare.py`, `export.py` and conflict-checked `sync.py`.
There is no direct blanket copy of the main RTL over FPGA-specific adaptations.
The new package has 625 compilation files and 799 verified checksum entries.
Replaying sync with the same reviewed candidate produces zero changes, zero
local-only entries and zero conflicts.

## Reviewed Differences

1. The dispatcher already retains the reviewed interval arithmetic and request
   isolation in main RTL. Its signoff revision adds architectural fixes without
   changing those implementations. Added its exact input SHA to the strict
   export allowlist; arbitrary source changes are still rejected.
2. The sole overlapping RTL conflict was the MMU canonical-address check.
   Candidate and old package differed only in the two input-versus-registered
   request/address lines. Selected the mainline registered transaction fix;
   the existing early superpage PPN repair is retained.
3. Promoted old package-only changes back to templates: C2's independent
   differential reference clock and constraints, project constraint inclusion,
   routed-checkpoint board-repository setup, and host workflow documentation.
   This makes future exports retain the previously implemented board changes.
4. Retained the UI reset distribution, MIG read-response cut, JTAG sampling,
   Ethernet integration and FPGA AXI ID remap optimization. The latter remains
   an explicit transform rather than an unexplained dependency difference.
5. Extended static hierarchy checks to the combined dual-DDR/Ethernet profile.
   Updated the protection-counter width expectation from five to six bits:
   the imported AXI fix represents MaxTrans=32 itself, not just values 0..31.
6. One Ethernet test still omitted the already-present UI reset transform from
   its expected wrapper. Updated that expectation to the full reviewed chain;
   no RTL was changed to silence the test.

`provenance/ara_local.patch` is now empty because main source changes are
committed, not because the fixes were removed. The manifest records the source
commit and per-file hashes before FPGA integration; integration and CVA6 patch
records are refreshed as well.

## New Checks

- Main RTL/dependency identity and checker tests: 35 passed.
- FPGA export/sync/retained-transform tests: 75 passed.
- Clean candidate package/protocol tests: 12 passed. The UART exercise in this
  suite is mocked and is not a board measurement.
- Package checksums: all 799 declared entries match actual package bytes.
- Pyslang 11.0.0: all five profiles elaborate without non-vendor errors:
  baseline, host, dual_ddr, host_ethernet, dual_ddr_ethernet.
- Actual-module VCS AXI remap cycle equivalence: five parameter combinations
  passed, including simultaneous push/pop. This is not physical timing signoff.
- Tcl syntax/project/CDC-script mock checks passed; these are not Vivado DRC/CDC
  reports and do not prove timing closure.

Full logs and reviewed candidate:
`/home/wangwy/fpga_runs/fpga_signoff_5ee02215_20261016/`.
Transactional sync backup:
`hardware/fpga/ara_dsa_vcu118/.fpga_sync_backups/20261016T111228Z_612162df/`.
The previous checkpoint also preserves the pre-resolution MMU source.

## Remaining Work

No Vivado synthesis, placement, routing, bit generation or programming was
started. Static checks intentionally do not elaborate proprietary Xilinx IP.
Refresh/re-create the project configuration before the next build, because
managed scripts and the reviewed constraint inputs changed. Old DCPs and
bitstreams are not acceptance evidence for this source revision. Full SoC/Linux
regression and physical timing/CDC/DRC acceptance remain separate requirements.
