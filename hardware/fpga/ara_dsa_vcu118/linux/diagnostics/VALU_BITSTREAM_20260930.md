# VALU Incremental Bitstream

Completed on Windows at 2026-09-30 04:20:27 +08:00. Scheduled task
`AraValuBitstream20260930` returned 0. No board programming was performed.

## Artifacts

Directory:
`D:\fpga_runs\ara_valu_release_20260930\bitstream_host_ethernet`

| File | Bytes | SHA256 |
| --- | ---: | --- |
| ara_dsa_vcu118.bit | 80159227 | 4166A5BEC610638F81A120CA1EBA198DFFA1F68328F39B28C7AD635F61D01344 |
| ara_dsa_vcu118.ltx | 112122 | 397E46DDB318A29854CD24BF6BD955AF9DE20EB08CE3FCD0400131E0FA5511F6 |

The output directory contains `bitstream.json` with checkpoint, audit and
artifact hashes, plus the native `session.log`. Use the probes from this
directory with this bitstream, even though their hash matches the older probes.

The input is a byte-identical copy of
`D:\fpga_runs\ara_valu_incremental_20260929\routed.dcp`, renamed to
`D:\fpga_runs\ara_valu_release_20260930\ara_dsa_vcu118_routed.dcp` for the
existing bitstream wrapper. Its SHA256 is
`E0C84074B6EBE8E3F510EE2E1556B5CD1F2DF90C87974430F31AE2CDCB397F76`.
The profile is `host_ethernet`. No RTL, timing exceptions, clocks, placement,
routing or DRC severities were changed during audit/bitstream generation.

## Checks

The frozen `ara_valu_fix_20260928\package` audit flow reopened the saved DCP.
The completed audit manifest is:
`D:\fpga_runs\ara_valu_release_20260930\ara_audit_20260930_033309_284c61408b15\completed_audit.json`

Its SHA256 is
`FF2824A40DF84318C5EDF1B6672C7DB3E3EEEBFBEC6926079881BB3E065D7B27`.
All 32 report hashes were also independently checked after copying the
reports to Linux. Bitstream generation used the existing `audited` mode,
which verifies those hashes instead of repeating the full report suite.

| Routed check | Result |
| --- | --- |
| Setup WNS / TNS / failing endpoints | +0.001 ns / 0 / 0 |
| Hold WHS / THS / failing endpoints | +0.001 ns / 0 / 0 |
| Pulse WPWS / TPWS / failing endpoints | +0.005 ns / 0 / 0 |
| Fully routed nets / routing errors | 972276 / 0 |
| Constraint and boundary checks | FAILURES=0 in both reports |
| Missing clocks / unconstrained internal endpoints | 0 / 0 |
| Multiple clocks / combinational loops / latch loops | 0 / 0 / 0 |
| Native bitgen log | 0 Errors, 0 Critical Warnings, 501 Warnings |

`finish_incremental_valu.ps1` waits for this audit, rejects missing/mismatched
evidence and negative setup/hold/pulse margins, then calls the frozen existing
bitstream wrapper. Its report-gate tests passed 14 cases in Windows PowerShell,
including negative slack, failing/missing endpoints, malformed/NaN summaries,
and Error/Critical Warning DRC findings. It never programs the board.

## Remaining Acceptance Work

This is a generated test artifact, not completed CDC or Linux acceptance.
The positive timing margins are very small. Do not call the design robust
across subsequent builds based on this result alone.

- The full CDC report still contains 739 Critical findings: CDC-1 711,
  CDC-4 3, CDC-10 11, CDC-11 8, CDC-12 3, CDC-13 3. Most destinations are
  inside Ethernet IP; two CDC-11 findings concern board-ready fanout.
  Vendor hierarchy membership is not a waiver.
- Relative to the previous bitstream's audit, the earlier incremental CDC
  comparison found eight changed representative startpoints on Ethernet
  reset CDC-10 paths, with unchanged destinations and finding counts. That
  comparison does not establish reset-cone equivalence or CDC signoff.
- The current URAM/ready-fanout detail report is exactly identical to the
  previous audit: eight URAMs, CASCADE_ORDER NONE on both ports, 2848
  unconnected cascade inputs and 48 GND inputs. Existing REQP-1869 warnings
  are retained, not claimed fixed. The VIO-only fanout indicator remains 0.
- The full routed DRC report has 1606 findings, all Warning or Advisory;
  methodology findings and partially constrained pad interfaces still need
  their documented interface/protocol review. Native bitgen success does
  not replace that review.
- Board reset/calibration, Ethernet/JTAG loading, the VALU reproducer and
  complete Linux boot/runtime regression have not been run on this bitstream.

The prior board image and all previous build artifacts remain untouched.
