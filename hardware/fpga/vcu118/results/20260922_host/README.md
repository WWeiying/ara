# Host/debug/dual-DDR local evidence

This directory records local checks for the optional `host` and `dual_ddr`
profiles. It is not FPGA signoff or a board-performance measurement.

- `debug/`: bounded debug-register/observer simulation and JSON result.
- `ddr/`: router, wrapper-reset, CDC and patcher tests, with JSON result.
- `jtag/`: sampled JTAG/reset simulation and JSON result. This tests the
  existing CPU TAP, not the vendor JTAG AXI IP used by the new host loader.
- `static/`: `pyslang` elaboration for baseline/host/dual-DDR non-vendor RTL.
- `integration_test.log` and `profiles_test.log`: package invariants and
  build-profile logic tests.
- `export_test.log`: one historical exporter-provenance expectation fails on
  a pre-existing exported `vmfpu.sv` change. The host integration test checks
  that this task did not modify that file.
- `worktree_package_test.log`: a pre-existing generated `linux/out` symlink in
  the dirty worktree violates the snapshot no-symlink policy. It is not part
  of the SHA256SUMS-listed exported files.

The package test passes all 12 cases when run on a staging directory copied
from SHA256SUMS-listed files only. The final local loader suite passes 47
tests, and `verify_package.py` validates 785 exported files.

The second MIG, JTAG AXI v1.2 IP port declarations, pin mapping, timing,
CDC/DRC and real DDR calibration still require Vivado 2020.1 on the Windows
machine. The host loader's burst-address preflight and verified loading also
require a programmed board. No local result establishes a speedup over UART.
