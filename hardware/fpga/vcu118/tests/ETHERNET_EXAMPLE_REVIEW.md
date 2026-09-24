# VCU118 J10 Generated Example Review

Reviewed on 2026-09-24. **Do not build/program the generated example unchanged
as a PC downloader.** Source review completed with the integration blockers
below; physical implementation, license-at-bitgen, link and packet checks remain
open. No Ara RTL, Windows project, vendor installation or board was modified.

## Evidence and Scope

- Evidence commit: `2dfc00c4cbac63fd9a724b435771d091bb981a92`.
- Branch: `fpga-evidence/ethernet-review-20260924_110539-5c4674fd`.
- ZIP SHA256: `1b6fadd61adfe4e31a1562bd02acd0d59f86643884dd053629b3658c253095c3`.
- All 52 archive members match manifest sizes and SHA256s. The 51 original
  inputs also match `review.json`: 17 HDL, 15 XDC, 11 XCI, 1 XPR, 7 reports.
- This proves collection integrity, not that generated files were unchanged
  between generation and collection. No protected IP implementation was supplied.
- Source references below are relative to `example/` inside that archive.

## Physical Constraints: Blocker

`imports/eth_j10_ex_des_loc.xdc:73` through line 75 explicitly assigns:

| Signal | Example PACKAGE_PIN | J10 board contract |
| --- | --- | --- |
| `sgmii_txp` (wildcard `*txp`) | AV20 | AU21 |
| `sgmii_rxp` (wildcard `*rxp`) | AR20 | AU24 |
| `mgt_clk_p` | AW18 | AT22 |

The bundled board XML and UG1224 Table 3-25 agree on J10 locations. Negative
partners are AV21, AV24 and AU22 respectively; MDIO/MDC/PHY reset are
AR23/AV23/BA21. Data electrical properties must follow the active board preset:
DIFF_HSTL_I_DCI_18, TX OUTPUT_IMPEDANCE RDRV_48_48, RX ODT RTT_48. The reference
pair is LVDS. A high-level board guide's PHY-side voltage table is not a reason
to replace the FPGA differential I/O standard with LVCMOS18.

The generated PCS board XDC also associates the reference pair with the correct
`SGMIICLK_P/N` BOARD_PINs. This **conflicts at source level** with the explicit
example placement; final effective LOCs and ordering have not been evaluated by
Vivado. Do not assume board automation overrides everything correctly. Replace
the example location XDC in an isolated project, explicitly constrain both sides
of each pair and management signals, and assert post-link `report_io` values.
The 15 XDCs include OOC/scoped constraints; do not add them all as top-level XDC.

## Configuration: Matches the Selected Interface

The top XCI is AXI Ethernet 7.2, non-processor mode, 1G, SGMII/LVDS, 625 MHz,
shared logic in core. The child PCS/PMA is 16.2 and actually reports `Standard`
SGMII, `Physical_Interface` LVDS, `LvdsRefClk` 625, TX pair 2/RX pair 0.
The early console message saying 1000BASEX during IP creation is not the final
configuration. The unused GTY/125 MHz configuration fields do not make this a GT
lane design. The MAC child is TEMAC 9.0; the prior Bought license report still
does not prove bitstream authorization or hardware operation.

PCS MDIO address **1** is distinct from external DP83867 address **3**. The latter
matches the board guide's straps. Do not "fix" top-level `PHYADDR=1` to 3.

## Clocks and Reset: Dependency Not Yet Closed

`imports/eth_j10_clocks_resets.v:87` takes the independent 300 MHz board clock;
lines 92-127 divide/multiply it to produce the 100 MHz AXI-Lite control clock.
The main system reset depends on MMCM lock and soft reset (line 72), with
AXI-Lite reset release synchronized to that clock (line 161).

`imports/eth_j10_support.v:144` maps `mgt_clk_p/n` to the IP's LVDS clock input.
The 625 MHz reference is supplied by the external PHY, not by that control MMCM.
The wrapper forwards the IP's `phy_rst_n` to the board; the reset counter's actual
internal clock connection is not present in the collected files. Its XCI count
value alone cannot prove freedom from a PHY-reference/reset dependency cycle.

Use an independent, timed PHY-reset path in the isolated wrapper, and keep its
control/MDIO clock available while the PHY reference is absent. Check the TI
reset/stabilization requirements. PG138 documents this dependency for KCU105;
that warning is a design consideration, **not evidence of a measured VCU118
deadlock**. No reset lockup has been observed in this preflight.

## Initialization: Demo Defaults, Not PC Networking

`imports/eth_j10_axi_lite_ctrl.v:260` resets external-loopback enable to 1 and
auto-negotiation enable to 0. Lines 892-899 issue these settings to the PHYs.
A bounded simulation of the unmodified generated controller measured:

- PHY 3, extended register 0x00D3, write 0x4000 via 0x0D/0x0E addressing.
  This enables the six-wire differential reference-clock mode.
- PHY 3, BMCR register 0: writes **0xC140**, then **0x4140**. The final commanded
  value enables local loopback and disables copper auto-negotiation.
- PHY 1, control register 0: writes **0x0140**, also clearing PCS auto-negotiation.
- Eight MDIO command writes and 22 AXI-Lite writes total; terminal state is 61.

These are observed commands to a behavioral management-register model, **not
PHY readback**. Reset-bit self-clearing, strap reloads and the persistence of
0x00D3 across the following BMCR reset were not modeled. The next controller
must order resets before final configuration, poll completion and read back
critical settings rather than assume the sequence established a real link.

For PC traffic, remove demo loopback, configure both copper and SGMII negotiation
consistently, verify speed/duplex/link, and set the intended destination MAC.
Do not label the demo's LASTSTATE or activity LED as link/packet validation.

## AXI-Lite Controller: Reproduced Handshake Limitation

Hypothesis from lines 730-756 and 805-808: AWVALID and WVALID remain coupled;
WREADY alone ends a write and clears its pending flag. AW acceptance and B/R
error responses do not qualify successful initialization. The discriminating
signals are AWVALID/AWREADY, WVALID/WREADY, BVALID/BREADY/BRESP and `axi_config_cs`.

One 100 MHz testbench run, four reset-isolated cases, maximum 100 us:

| Case | AW handshakes | W handshakes | B responses | Observation |
| --- | ---: | ---: | ---: | --- |
| Both channels ready | 22 | 22 | 22 | Reaches state 61; demo settings above |
| AW delayed through cycle 39 | 18 | 22 | 18 | Four stalled AW withdrawals; still state 61 |
| W delayed through cycle 39 | 53 | 22 | 22 | Repeated AW acceptance; still state 61 |
| All responses SLVERR | 22 | 22 | 22 | All 22 write errors ignored; still state 61 |

The subordinate has independent bounded AW/W queues, always-readable MDIO-ready
status, and ordered B responses. It is deliberately not a model of the installed
TEMAC slave. These results prove the example master is not general-purpose
AXI-Lite-safe; they do **not** prove its attached vendor slave produces those
READY patterns, nor identify a TEMAC bug. They are unrelated to the old Ara/LLC
JTAG multi-beat mapping issue. Do not modify that path on this evidence.

The production control path must retire AW/W independently, wait for B, check
BRESP/RRESP, and stop with a recorded failure on error/timeout. The selected
bring-up approach is an independent-clock JTAG AXI-Lite management port with
host-driven register/MDIO checks, instead of deploying this demo FSM. JTAG is
only the low-volume control plane; future payload transfer still uses Ethernet.

## Packet Path and Remaining Gates

The example's RX path is MAC -> RX client FIFO -> pattern/address-swap logic ->
TX client FIFO -> MAC. Non-processor mode exposes byte-wide unbuffered MAC
streams, **not a ready-made DDR/DMA interface**. The RX MAC has no TREADY. The
RX FIFO source rolls back bad or overflowed frames before forwarding complete
frames (`rx_client_fifo.v:595`, `:696`); removing this store-and-forward boundary
and writing DDR before EOF/error validation would be incorrect.

Neither these FIFOs nor PCS/MAC/MDIO signaling were simulated in the controller
test. Before a network image is accepted, the remaining checks are:

1. Isolated wrapper: independent PHY reset/control clock, corrected final pins,
   synchronized resets in MAC domains, visible reset/lock/error status.
2. Build: real synthesis/route, no black boxes or conflicting/unconstrained IO,
   review CDC and setup/hold, successful licensed bitgen. Never downgrade DRC.
3. Board: read PHY ID/address, configure and read back six-wire mode and both
   negotiation domains, verify 1G/full-duplex link through reset and reconnect.
4. Packets: bounded FIFO/CRC/error handling and PC loopback before any DDR or
   Ara integration. No program/data downloader or throughput claim yet.

The uploaded bundle is sufficient for the source-review conclusions. No further
Windows collection or unchanged preflight run is needed for this review. It is
not yet a build-ready or programming-ready deliverable.

## Reproduce Locally

No vendor source is copied into the normal source branch. The runner verifies
the uploaded archive and exact two HDL hashes, then copies only those two files
to a fresh result directory with notices intact. Needs Icarus Verilog, not Vivado.

```bash
git fetch origin fpga-evidence/ethernet-review-20260924_110539-5c4674fd
python3 hardware/fpga/vcu118/tests/check_ethernet_example_ctrl.py
python3 -m unittest discover -s hardware/fpga/vcu118/tests -p 'test_ethernet_example_ctrl.py'
```

Exit 0 means **the documented limitations were reproduced**, not that the
controller passed protocol or hardware qualification. A changed source hash
requires a new review rather than applying these assertions silently.

## Primary References

- [VCU118 UG1224, Ethernet PHY and Table 3-25](https://docs.amd.com/api/khub/documents/Uoc4S9pQd1uve6kiGiG2kA/content),
  printed pages 78-79: pin/address checks against the bundled board XML.
- [PG138 v7.2 VCU118/KCU116](https://docs.amd.com/r/7.2-English/pg138-axi-ethernet/VCU118/KCU116-Board)
  and [KCU105 reset dependency](https://docs.amd.com/r/7.2-English/pg138-axi-ethernet/KCU105-Board):
  architecture references; collected Vivado 2020.1 sources define this example.
- [TI DP83867 datasheet](https://www.ti.com/lit/ds/symlink/dp83867is.pdf),
  sections 6.6-6.7, 8.1 and 8.53: reset timing, BMCR and six-wire clock mode.
