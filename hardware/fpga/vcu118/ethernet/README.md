# Isolated VCU118 J10 Diagnostic Build

Status: implementation and local RTL regression available. **Not yet synthesized
in real Vivado, programmed or tested on a physical Ethernet link.** This is the
next build gate, not the Ara Ethernet-to-DDR downloader or a throughput result.
The existing Ara RTL, golden host bitstream and UART/JTAG loaders are unchanged.

## Windows: One Build Invocation

Keep the successful `D:/fpga_runs/ara_eth_zr9jsk58` preflight directory intact.
Run in ordinary PowerShell, not the Vivado Tcl console:

```powershell
git -C D:\project\ara pull --ff-only origin ara_dsa
if ($LASTEXITCODE -eq 0) { py -3 D:\project\ara\hardware\fpga\vcu118\tests\host_ethernet_build.py --upload }
```

No board power, cable, GUI target connection, `.ltx` argument or hardware reset
is required for this build. Leave the console open until the final state/upload
branch. Do not pipe/redirect the command's console handles. This is a real
synthesis/implementation build, longer than the earlier IP preflight; no runtime
estimate has been measured yet. Default parallel jobs: 4, selectable with `--jobs`.

The runner creates a fresh short `D:/fpga_runs/ara_eth_build_*` directory. It
validates the successful preflight and hashes eight reviewed vendor integration
files, copies them without modification, and snapshots the authored RTL/Tcl/XDC
and board repository. It creates a new Vivado 2020.1 project/IP, never opens the
Ara project, never programs hardware and never overwrites a previous run.
An alternative intact preflight path may be supplied as a positional argument.
`--prepare-only` performs input verification/copying without Vivado.

`--upload` publishes reports, the native Vivado log and synthesis/OOC `runme.log`
files to a new `fpga-evidence/ethernet-build-*` branch at origin. It does not
upload bitstreams, checkpoints, generated IP HDL or license files. Logs can
contain local paths/license diagnostics. The current checkout/index is unchanged.
Reports are also uploaded after a failed build; send the final branch name.

Success is `built_needs_manual_review_and_board_test`. **Do not program the new
image yet.** First review the uploaded IO/clock/CDC/timing/methodology reports.
Any `FAIL` stops the flow; no DRC severity is downgraded. TEMAC must report a
full Synthesis license before synthesis, and actual bitgen must succeed. This
does not constitute a complete timing-coverage review or hardware acceptance.

## Circuit and Boundaries

- The independent 300 MHz board clock supplies 100 MHz JTAG AXI-Lite, VIO and
  debug hub. JTAG is management-only, not the packet payload path.
- External PHY reset is low for 20 ms, followed by 200 ms settling. It depends
  only on the management clock, not PHY-provided 625 MHz. The original IP reset
  output is disconnected and its board-reset association is `Custom`. TI lists
  reset timing in the [DP83867 datasheet](https://www.ti.com/lit/ds/symlink/dp83867is.pdf)
  and recommends no MDC activity during the 200 ms power-up settling interval
  in [this TI clarification](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/1359515/dp83867is-power-up-timing-minimum-t1).
- The reviewed support, clocks and good-frame-aware RX/TX FIFOs are reused.
  Neither the vendor demo controller, pattern generator nor its wrong LOC XDC
  is added. Board pins/electrical properties are asserted again after routing.
- Packet path: MAC -> good-frame RX FIFO -> bounded echo -> TX FIFO -> MAC.
  RX MAC cannot be backpressured; the vendor FIFO must discard overflow/bad
  frames. No bytes are ever written to Ara or DDR.
- Echo starts disabled. It accepts only destination `02:00:00:00:01:18`, test
  EtherType `0x88b5`, nonzero unicast source distinct from itself, lengths
  60..1514 bytes excluding FCS. It swaps destination/source and preserves the
  remaining bytes. FCS handling remains in the MAC. No ARP, IP, UDP, DHCP,
  VLAN or jumbo-frame support is claimed. It is deliberately single-buffered
  and not a wire-rate downloader. Use a directly connected test NIC later.
- Disable rejects a frame before transmission; once transmission has started,
  disable does not truncate it. Reset discards queued/in-progress traffic.

Management contract for the forthcoming board-control script: core `i_jtag`,
AXI4-Lite 32-bit full-word aligned accesses to `0x000..0xffc` only. Read B/R
completion/error responses. Do not use the Ara `host_load.py` memory/debug
layout on this image. Out-of-range/partial raw GUI transactions can alias the
MAC register window and set the diagnostic sticky error; there is no AXI address
firewall in this isolated image. No DDR interface is connected.

VIO `i_vio` output 0 requests PHY+MAC/packet reset; output 1 enables echo, both
initially zero. Input 0 is a 32-bit diagnostic vector:

| Bits | Meaning |
| --- | --- |
| 0 | Independent control MMCM locked |
| 1 | External PHY reset released |
| 2 | Reset timer settling complete, **not link ready** |
| 3 | Sticky AXI response/address/strobe error |
| 4 | Echo enable requested |
| 5, 6, 7 | Sticky frame seen, echo submitted to TX FIFO, frame rejected |
| 23:8 | Independently synchronized PCS status bits, **not atomic** |
| 31:24 | Zero |

Sticky packet bits clear on packet reset. The error bit clears on control/PHY
reset. They are observations, not packet counts, PHY link qualification or proof
that an echo reached the PC. PHY ID/readback/negotiation remain board-test gates.

## Timing and Verification Scope

Vendor scoped IP timing is retained, without importing OOC XDC at top level.
New constraints bound first-stage bit synchronizers and the RX FIFO's
toggle-qualified six-bit read-pointer transfer to 8 ns. Only explicit reset
synchronizer assertion pins and the asynchronous board reset are excepted.
MDIO/reset pad routes receive 20 ns budgets. These do **not** establish complete
source-synchronous MDIO timing signoff; inspect existing IP exceptions and board
timing. No broad asynchronous clock-group exceptions hide MAC/control crossings.

Automated gates: exact pins/standards/electrical properties, no unresolved black
boxes, no erroneous/incomplete routes or Error-severity DRCs, nonnegative worst
setup/hold path slack, common 100 MHz management/debug clock and 625 MHz PHY
reference. Pulse-width checks, unconstrained paths, CDC, bus-skew, Critical
Warnings and IO timing still require the emitted reports to be reviewed before
programming. A nonnegative worst timed path alone is not timing closure.

Local tests (Icarus on PATH, evidence commit already fetched):

```sh
python3 -m unittest discover -s hardware/fpga/vcu118/tests -p 'test_host_ethernet_*.py'
python3 hardware/fpga/vcu118/tests/check_ethernet_diag.py
```

The bounded stream simulation uses the actual hash-verified RX/TX FIFO source,
two independent clocks, a behavioral MAC stream and FDRE. It checks PHY reset
timing, valid 60/64/1514-byte frames, stalls, disabled echo, address/EtherType
rejection, oversized/short/MAC-marked-bad frames, 4K RX FIFO overflow, disable
during transmit, mid-frame reset and recovery. It does not model
protected MAC/PCS, JTAG IP, physical FCS checking, MDIO, top MMCM or analog PHY.
Python/Tcl tests exercise source integrity, immutable input copies, license and
failure gates; mocked APIs cannot prove real Vivado command/IP compatibility.

After this build/report gate: provide the checked JTAG/MDIO initialization and
readback sequence, program the matching `.bit`/`.ltx`, verify 1G/full-duplex link,
then run PC packet tests. Only after that integrate a reliable UDP data protocol
and DDR writes with CRC, range checks, acknowledgements and readback.
