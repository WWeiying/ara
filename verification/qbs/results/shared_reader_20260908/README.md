# Shared Reader Fault Regression

VCS on the host, September 8, 2026. No synthesis, physical implementation,
model tolerance changes, or reuse of an old top-level simv as current RTL.

Original artifacts: `hardware/qbs_read_axi_20260908/`.
Detailed explanation: `hardware/docs/qbs_shared_reader_fault_review.md`.

| Test | Result |
| --- | --- |
| Existing reader tests, original RTL | PASS |
| New stalled-AR probe, original RTL | Expected FAIL at 8035000 ps: AR withdrawn on older R error |
| Reader with the fix | Existing cases plus 6 fault/stall combinations PASS |
| QBS engine | 33 functional cases, context lifetime, 4 fault classes PASS |
| QBS normal cycles | All 33 identical to the post-INT8-fix baseline |
| AKV engine, behavioral SRAM | PASS, including fault recovery and D64/D96/D128/segmented D256 |
| AKV engine, macro-interface SRAM model | Same suite PASS |
| Newly compiled full RTL | RVV/QBS/AKV handoff PASS; QBS=4, AKV=10, traps=0 |

`integration_status.json` contains source/config/simv hashes and timestamps;
`handoff.conf` identifies the ELF and run; `handoff_summary.txt` holds the final
command counts. The original run retains `source.patch` and complete logs.

The integration run names baseline `ac3a7523` plus the saved source changes.
The tested reader SHA-256 is
`ca80f45429b3e9c033b2e4cae07a5fad2d9c2484700f1d5320b65eaf85f63503`.
The QBS command vector file SHA-256 is
`24d9d661893dbdbd13b37ea003cb364dc5fe038f7ab042445dedd25b47ecb885`;
it is byte-identical to the original baseline vector file.

This proves a standalone reader AXI defect and its bounded repair, not a
demonstrated model failure in the current two-slot VLSU AXI-cut integration.
This suite does not certify OS task switching, interrupts, or arbitrary
mid-command resets. Performance equality refers to the 33 engine cases,
not a newly measured complete-model speedup.

Reproduce in new directories:

```bash
make -C verification/qbs rtl-read-check RTL_READ_BUILD=/tmp/qbs-read-check
make -C verification/qbs rtl-engine-check RTL_ENGINE_BUILD=/tmp/qbs-engine-check
make -C verification/akv rtl-check BUILD=/tmp/akv-engine-check
make -C verification/akv rtl-macro-check MACRO_BUILD=/tmp/akv-macro-check
python3 verification/akv/run_current_handoff.py --output hardware/qbs_handoff_new
```
