# Independent Remaining9 M6 Terminal Acceptance

**ACCEPTED: nine canonical reduced singles, not full parents.** No discrepancy found by the authorized complete reconstruction. This summary reads only the generated audit JSON and the original command's final exit response; no CSV was reopened and no audit/reference/Host/DUT run was repeated.

## Command and Identity

- Actual auditing PID1006545, original execution session35772, final command **exit_code=0** observed directly in tool chunk46e50e. Full command and invocation method: [TERMINAL01_INVOCATION.md](TERMINAL01_INVOCATION.md); persisted exit evidence: [command_exit_observation.json](terminal01/command_exit_observation.json).
- Audit runtime1765.190 s. Sealed prepared SHA `0eae1de4381ab00d1f76203b1c39cfbfd8e3c59747ee4dc7763323bcd7341154`; audited complete SHA `d2b57da8b703fb5e301e3c584856be1d802bb5b0c688c72accef715e531330bc`.
- Exact M6 image SHA `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`; batch plan SHA `10807a26d22d6beb48acdd075e3e1ccea37e5ca69f38c783ce2ed9027375891a`.
- Terminal gates verified nine unique expected child results, numeric rc0 and elapsed within5400 s each, COMPLETE metadata, aborted=false, retries0, private ELF/command/image identity, exact raw oracle/finish markers and failure vetoes. No worker label alone was sufficient.
- Before/after verification passed for **1438 unique pins**, incorporating1352 batch-plan pins and75 terminal-evidence pins plus preparation/admission bindings (sets overlap). Frozen539 sources and66 image files, configuration and source-manifest digests were included. No pin drift.
- Auditor command rc0 is not an outer DUT service exit observation. The latter remains unknown/null; no service query or GC-derived rc0 was used.

## Full Reconstruction

| Shape | Retired Rows | CSV Rows |
| --- | ---: | ---: |
| e16_mf2 | 1855423 | 1855480 |
| e16_m1 | 1859650 | 1859707 |
| e16_m2 | 1868132 | 1868189 |
| e16_m4 | 1885091 | 1885148 |
| e16_m8 | 1919013 | 1919070 |
| e32_mf2 | 1853904 | 1853961 |
| e32_m2 | 1860181 | 1860238 |
| e32_m4 | 1868565 | 1868622 |
| e32_m8 | 1885334 | 1885391 |
| **Total** | **16855293** | **16855806** |

- Exactly **9 CSV parses, once per shape**. All16855806 original row objects passed unfiltered and unchanged to the sealed checker; each observer's before/after ordered row digests match. Actual retired PCs/encodings, transport/uop ownership and complete reconstructed producer dictionaries match. Per-shape JSON hashes also match the aggregate binding.
- **1296 original oracle bytes = 9 x144**, covering result, full original destination tail and both guards. Every case reads NV16/vstart0; five e16 results are7e00 and four e32 results are7fc00000. All architectural exits are0.
- All189 helper instructions (21 consecutive once per shape),27 capacity instructions and63 legal bootstrap/C CSR instructions checked. Both entire unused helper ranges have zero retirement in every shape, not merely zero entry hits.
- All original input/seed/mask initialization loops remain checked, including e16m8 CAP512 and seed64 words. **60480 ordered fixture-field reads = 9 x6720**, covering all3360 fixture rows per single; these are not3360 target executions. No oracle or skipped-loop history was shortened.
- Restores: the DUT evidence establishes only original frm/fflags restore instructions retiring with saved zero-valued source operands. There is **no post-restore CSR readback or internal state observation**, so final restored frm/fflags state was **not directly measured**. Spike CSR logs do not extend DUT scope. This limitation is not a bug finding.

## Boundaries and Artifacts

Accepted scope is these nine handoff03 redspecial02 source-derived reduced singles on the frozen M6 image. It is not full6720 parents, all11 records, Linux replay, newer workspace RTL, or direct vector payload/waveform observation. Per-shape intermediate labels retain `PENDING_BATCH_PIN_RECHECK`; the final aggregate establishes that this last check completed successfully.

- [result.json](terminal01/result.json): status `INDEPENDENT_M6_REMAINING9_SINGLES1296_ACCEPTED_NOT_FULL_PARENTS`, SHA `1c42f3ab98f80a6f90e53cafb121dea65ddfdc28afcda8ca96aa07b7817b1367`.
- [verified_pins.json](terminal01/verified_pins.json): SHA `d35762c96e40f284937d3e2764f85f9a0d3606d0932d9603851df49ec4e28756`.

No sealed code, reference, source or DUT output was changed. This acceptance does not authorize additional runs.
