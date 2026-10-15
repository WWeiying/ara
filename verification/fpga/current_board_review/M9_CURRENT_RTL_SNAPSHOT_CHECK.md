# Current Main RTL Matches Frozen M9 Sources

Worktree: `/home/wangwy/openproject/ara_dsa_signoff_integration`.
Frozen source root:
`/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources`.

The11 modified tracked files under hardware/src were individually compared
with their frozen counterparts using cmp; all match. A subsequent complete
directory comparison also exited0 with no differences:

```sh
diff -qr hardware/src /home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources/hardware/src
```

The actual campaign/image/image.json SHA256 remains
`48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`.

This confirms byte equality of the entire hardware/src tree, not just equal
Git branch names. No RTL was edited, compiled or simulated for this check.
The runner classification repair changes verification software only and does
not alter those RTL sources or frozen campaign assets.

The133 Verilog/SystemVerilog source/header files retained under the frozen
`hardware/deps/cva6/core` were also individually compared with the current
worktree paths:133 checked, zero mismatches, actual command exit0. A full core
directory diff additionally lists current-only files, including unselected
configurations, documentation and local build directories; it reports no
differing common file. Therefore this check establishes equality of the
retained core source subset, not equality of both complete directory trees or
proof that current-only files participate in the frozen build.

This is not a new complete audit of all dependencies, testbench, installed tools or
compiled simulator libraries; those retain their separate frozen manifests and
prior admission evidence. Nor does source equality extend a passing test's
scope: arithmetic remains18/22, and the e16/m8 diagnostic3868-call prefix is
not a complete4095-call PASS.
