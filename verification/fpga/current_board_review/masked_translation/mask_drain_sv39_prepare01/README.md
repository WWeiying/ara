# Real Sv39 Mask-Drain Boundary Preparation

LOAD and STORE Host/Spike references are accepted; both M7 services have
been launched (not yet DUT acceptance). No RTL change or SoC build. This is a new
boundary test derived from the established ../sv39_fixture.c/.S scaffolding,
not a source-faithful port of any archived original16 Linux scenario.

One e64m4 VL9/start0/all-active masked zero-stride load to v24..v27 accesses
unmapped VA0x40001000. This requires three expanded mask words on four lanes.
The real M-mode trap handler records/validates cause13, exact original PC,
tval, S-mode status, Sv39 satp, VL9, vtype26, vstart0, fcsr117 and vcsr5.
The labeled vstart read precedes handler vector operations/PTE repair.
Snapshot the whole old destination group plus v23/v28 neighbors and v8;
repair the leaf PTE, addressed SFENCE, then MRET without changing MEPC.

After same-PC retry, read actual vector CSRs, issue a distinct masked load
to v8 from mapped VA0x40000000 with alternate predicate, read CSRs, then a
masked add with the complementary predicate and masked store to a different
address. Check the complete512-byte
target group,256-byte neighbor guards,128-byte successor register, all
snapshot guards,8KiB data, complete12KiB page tables and their guards,
all48 source-mask bytes, exact two-trap ledger, completion and CSR restore.
Distinct architectural owner/history is required; hardware VID reuse is
legal and a different numeric VID is not asserted without DUT evidence.

The LOAD exercises real lane MaskM and exception/CSR/flush/retry paths.
The separate STORE member changes the target to ordinary masked unit-stride
vse64.v and cause15, with the full store-side memory oracle; it exercises
real StA queues but is not the early-indexed SlideAddrGenA case owned by Zeno.
Software progress and complete checks demonstrate recovery, not direct
internal queue/flush signal measurement. No full-run FSDB is requested.

Fixed unique Spike reference bound500000 instructions,120s,128MiB trace;
compile only the software SoC/Spike ELF pair against the sealed integration
runtime. Host C oracle must agree with independent Python before reference.
No automatic retry/budget extension. Terminal Spike result is NOT DUT PASS.

## Actual M7 Entry

- `reference_load01/READY.json`: 120321 retired, 914 checks, reference rc0.
- `reference_store01/READY.json`: 125321 retired, 914 checks, reference rc0.
- `vcs.py` reuses frozen runner and accepted M7 image/admission helpers.
  `dut_check.py` consumes one complete CSV, checks all914 oracle operands
  against independent expectations (including14 actual CSR restore reads),
  exact trap CSR records, repair/SFENCE/same-PC retry and successor ordering.
- `host_dut_check01.json`: 11 focused adapter tests PASS, not DUT evidence.
- LOAD: `ara-mask-drain-load-m7-01.service`, `vcs_m7_load01/`.
- STORE: `ara-mask-drain-store-m7-01.service`, `vcs_m7_store01/`.
- Each output contains `plan.json`, local `service.log`, `launch.json`,
  once-only `startup_observation.json`, then terminal `complete.json`.
  Numeric child exit is persisted before artifact checks in
  `run/tests/<runtime_name>/child_exit.json`.
- Fixed3600s simulator/4200s service bounds, one worker each, no retry/build.
  Running or reference PASS does not constitute M7 architectural acceptance.
