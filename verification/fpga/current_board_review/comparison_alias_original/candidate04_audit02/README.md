# Candidate04 Independent Terminal Audit

35/35 full-oracle PASS and zero exit, independently checked.
Exact membership:19 archived comparison-alias singles +10 original smokes +6 original controls.
All staged ELFs match original inputs; no source/oracle replacement.

Pin sets unchanged: candidate04 plan1859; original19 measurement1144; original source107.
No119-entry pin list was found in these manifests; the actual full lists were rehashed.

| Control | CSV Rows | Changed Cycle Rows | Last Cycle M3 / M4 | Noncycle Differences |
| --- | ---: | ---: | --- | ---: |
| smokes__rvv_vadd | 40797 | 0 | 65438 / 65438 | 0 |
| smokes__rvv_vslideup | 33635 | 0 | 56008 / 56008 | 0 |
| smokes__rvv_vslidedown | 26447 | 0 | 41490 / 41490 | 0 |
| smokes__rvv_vrgather | 17283 | 0 | 28256 / 28256 | 0 |
| smokes__rvv_vmseq | 43836 | 0 | 65658 / 65658 | 0 |
| smokes__rvv_vfredosum | 32611 | 0 | 51740 / 51740 | 0 |
| smokes__rvv_vfwredosum | 21708 | 0 | 34438 / 34438 | 0 |
| smokes__qbs_control_smoke | 1259 | 0 | 4383 / 4383 | 0 |
| smokes__akv_context_smoke | 14990 | 0 | 25397 / 25397 | 0 |
| smokes__qbs_akv_handoff_smoke | 4685 | 0 | 11318 / 11318 | 0 |
| singles__maskslide | 11578 | 0 | 19497 / 19497 | 0 |
| singles__restart_compare | 18975 | 1374 | 30318 / 30319 | 0 |
| singles__reduction_fflags | 5381 | 0 | 9435 / 9435 | 0 |
| singles__m8widen | 12408 | 0 | 21158 / 21158 | 0 |
| singles__wholemove | 23161 | 0 | 33222 / 33222 | 0 |
| singles__slide1up_prestart | 1596 | 0 | 3046 / 3046 | 0 |

15 CSVs are byte-identical. restart_compare has1374 changed rows, each exactly+1 cycle,
starting at VMSEQ.vx opcode608e4c57 uop_done27644->27645 (CSV line17603).
All18975 rows and all noncycle fields match; final cycle30318->30319.
Every CSV was fully parsed, with valid schema, monotonic cycles, continuous retirement order,
complete final row and a console-confirmed successful simulation finish.
QBS has2 and AKV has3 cvx_resp exception indications; their entire traces match candidate03.
These are not new architectural traps. The initial over-strict auditor is recorded in candidate04_audit01/error.json.
Original first-error baseline and cancelled records remain unchanged. No whole-parent closure claimed.
