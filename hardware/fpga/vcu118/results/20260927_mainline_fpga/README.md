# Main RTL FPGA integration run

Superseded: the user requested one combined Ara+Ethernet build. The wrapper
PID 22996 was stopped during IP preparation before host-only full synthesis;
IP workers were left to finish. Do not resume this baseline-only wrapper.
Its last `state.json` stage may remain `prepare_ip` after wrapper termination.
Current preflight and remaining launch gates: `../../ethernet/INTEGRATION_BATCH.md`.

This run absorbs the current dirty main RTL into the existing **host** FPGA
profile (Ara, CVA6, QBS, AKV, DDR and JTAG). It is NOT the shared-DDR Ethernet
profile. The standalone Ethernet baseline remains unchanged on the board.
Ethernet integration remains governed by `../../ethernet/ARA_INTEGRATION.md`.

## Inputs and export fixes

- Main repository HEAD at capture: `68f8910b`, plus working-tree changes.
  HEAD alone does not identify these inputs.
- 623 compilation files; 788 files verified against the fresh export's
  `SHA256SUMS` on both Linux and Windows.
- New `vsetvl_preview`, `store_load_lookahead` and
  `store_load_lookahead_pair` sources are included in compilation order.
- The exporter now accepts the reviewed dispatcher/segment revision without
  reapplying layout/control changes already present upstream.
- Upstream CVA6 SRAM reset/user wiring is recognized without duplicating ports.
- The MIG R-channel cut from `456fd1e9` is preserved reproducibly on export;
  previously it existed only in the packaged wrapper and would be lost on sync.
- Historical timing evidence remains historical, not relabeled as a result for
  the new dispatcher or updated full design.

## Checks completed

- `export_tests.log`: 33 tests passed.
- `ddr_patch_tests.log`: 6 tests passed, including byte-for-byte comparison of
  the regenerated DDR wrapper with the accepted R-cut revision.
- `sync_tests.log`: 26 tests passed.
- `static_host.log`: pyslang 11.0.0, full host hierarchy, no non-vendor
  elaboration errors. New preview/lookahead instances and existing QBS/AKV
  SRAMs/DDR CDC widths are explicitly checked. Vendor IP remains unelaborated.
- `ddr_cut_run.log`, `ddr_cut_result.json`: VCS test passed, 128 ordered
  512-bit R beats with stalls and independent RREADY. Not MIG validation or
  physical timing signoff.

## Independent Windows build

Linux snapshot: `/home/wangwy/fpga_runs/ara_mainline_20260927_0205/package`

Windows root: `D:\fpga_runs\ara_mainline_20260927_0205`

Archive SHA256:
`53901a42c9a75e23e4e15858386cd51c1373ca06695af50366d46a49d1a07b1e`

Manifest SHA256:
`bbd0b44a4fd7e2fe0a5034edadc5f38bd1401cccdfd5f63a32ce5f2c89809a45`

The copied `run_host.ps1` was launched independently via Win32_Process.Create
(initial wrapper PID 22996), using Vivado 2020.1. It verifies the package,
prepares host IPs, then invokes the existing guarded `run.ps1 -Stage all`.
The last observed stage was `prepare_ip`, with a live Vivado worker. This
document is not a completion marker; consult the live files below.

```powershell
Get-Content D:\fpga_runs\ara_mainline_20260927_0205\state.json
Get-Content D:\fpga_runs\ara_mainline_20260927_0205\flow.log -Tail 30
```

Detailed IP preparation logs are in `package\build\managed\prepare_host_*`.
Top-level worker logs are under `package\build\ara_dsa_vcu118_host\*.runs`;
isolated run records are under `runs`. Success requires `completed_flow.json`
and report review, not merely an exited process or a DCP on disk. Errors are
recorded in `state.json`; no automatic retry/reset is performed.

No bitstream has been accepted or programmed by this work. After routing,
review timing, CDC, DRC and unconstrained paths before bitgen/board testing.
