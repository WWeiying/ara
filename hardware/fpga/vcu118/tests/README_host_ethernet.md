# VCU118 J10 Ethernet Downloader: Preflight and Bring-Up Plan

Status: **IP/environment preflight only. Ethernet download RTL is not integrated,
and no link, throughput, or Ethernet-to-DDR test has passed on hardware.**
The existing UART and JTAG single-beat loader remain unchanged.

## One Windows Command

From PowerShell, after updating the `ara_dsa` checkout:

```powershell
py -3 D:\project\ara\hardware\fpga\vcu118\tests\host_ethernet_preflight.py --upload
```

No board connection, `.ltx`, reset, or programming is needed. Vivado GUI can stay
closed. The runner prefers `D:/Xilinx/Vivado/2020.1/bin/vivado.bat`, then PATH.
Use `--vivado PATH` for another installation of **2020.1**. Other versions are
reported and rejected, not silently treated as equivalent.

The script creates a unique short directory under `D:/fpga_runs` (system temp on
Linux), prints its path, and writes Vivado output to `vivado.log`. It never opens
the Ara project or an existing checkpoint. It does not launch synthesis,
implementation, simulation, or bitstream generation. It creates one disposable
AXI Ethernet IP and its example project using `-in_process`, without opening a
second GUI. Generated vendor products remain local.

`--upload` explicitly authorizes uploading diagnostics to a new
`fpga-evidence/ethernet-...` branch at `origin`, even when IP preflight fails.
The checkout's branch/index are not changed. Only these files are packaged:
`preflight.json`, `requested_config.tsv`, `stages.tsv`, `preflight.rpt`,
`ip_status_before.rpt`, `ip_status_after.rpt`, and `vivado.log`, when present.
Logs may contain local paths and license-server diagnostics. License files,
environment dumps, generated vendor RTL, projects, and bitstreams are not selected.
Omit `--upload` to keep all results local. Report the printed `UPLOADED_BRANCH`.
If Git upload fails, local results and the prepared bundle are retained.

`--out PATH` requires a **new** directory; old evidence is never overwritten.
`--static-only` checks the repository's board XML without invoking Vivado. It is
useful for development but cannot establish installed IP availability.

### Windows Board Repository Path Fix

The first uploaded run (`81eaefcc43aa2481aed56ea931483c4d1e679831`) stopped in
`project`, before catalog or license checks. Python could read the board XML, but
Vivado 2020.1 reported the repository as `'{D:\project\ara\...\board_files}'`
and rejected it as nonexistent (`Board 49-91`). The runner now passes forward
slashes for Tcl-facing paths; Tcl also normalizes and checks the repository and
all three board XML files before creating the disposable project. It records the
effective repository parameter and available VCU118 boards on discovery failure.
No board files, license settings, Ara project, or RTL changes are required.
Update the checkout and rerun the same command; each run gets a fresh directory.
Regression tests cover Windows-shaped argv on Linux and Tcl path/discovery
failures, but a Windows Vivado rerun is still required to confirm the correction.

### Installed IP Version Correction

The next uploaded run (`6f546884471657d46d4b6ba10b646f743174f264`) confirmed
`project: PASS` and the board-path correction. Its Vivado 2020.1 catalog contains:

| IP | Installed Version | Catalog REQUIRES_LICENSE |
| --- | --- | --- |
| AXI Ethernet | 7.2 | 1 |
| Gigabit Ethernet PCS/PMA | 16.2 | 0 |
| Tri-Mode Ethernet MAC | 9.0 | 1 |

The earlier script incorrectly pinned AXI Ethernet to 7.1, using an older guide
as its version reference. It now requires the observed 7.2 definition and uses
that same catalog object's VLNV for creation. It neither upgrades installed IP
nor selects an arbitrary newer version. A missing or ambiguous definition is
still rejected. Tests now filter the observed three-entry catalog rather than
returning a fictional object for every exact query; they also cover absent,
older-only, newer-only, multiple-version, and duplicate definitions.

`REQUIRES_LICENSE=1` describes an IP requirement, not whether this installation
has or lacks that license. No configuration, generation, or actual license-status
stage ran in this evidence. Those remain unverified until the next preflight.

## What Is Checked

- Bundled VCU118 2.4 board, XC VU9P `xcvu9p-flga2104-2L-e`, TI DP83867ISRGZ PHY.
- FPGA-perspective TX at AU21/AV21, RX at AU24/AV24; PHY reference clock at
  AT22/AU22, MDIO AR23, MDC AV23, PHY reset BA21.
- **SGMII over LVDS**, not RGMII or an Ethernet transceiver lane. The provided
  reference clock is **625 MHz**. Differential data I/O standards come from the
  board preset/pin file; do not replace them all with `LVDS` by assumption.
- Installed AXI Ethernet, PCS/PMA, and TEMAC catalog entries, configuration
  properties and allowed values, selected AXI Ethernet **7.2** configuration.
- Exact effective configuration readback: 1G, SGMII/LVDS, board interfaces,
  625 MHz, and the board's bitslice placement preset. Unknown or ignored
  properties stop generation. There is no trial-and-error alternative mode.
- IP status/license reports before and after product generation; creation and
  file/constraint inventory of the vendor example.

The candidate uses `processor_mode=false` to expose the unbuffered MAC-side
stream interface for a future hardware downloader, not a MicroBlaze software
stack. This is not a finalized Ara integration or a pin-checked bitstream.
The external PHY's MDIO address and the PCS/PMA's own `PHYADDR` are distinct;
the script does not overwrite the latter with the external PHY address.

`PASS` in the two `license_*` stages means **the report command completed**, not
that a full hardware license exists. A missing/evaluation license may still allow
product/example generation. Review the reports for the TEMAC dependency and
restrictions before proceeding. `bitstream_license_verified` and
`hardware_verified` are always false in this preflight.

## Implementation Gates

1. **IP preflight (this script):** inspect installed support, licensing and
   generated example clock/reset/constraint inventory. If the TEMAC license is
   unsuitable, assess an open MAC plus compatible PCS/PMA separately; do not
   bypass licensing or assume an open RGMII MAC solves the LVDS interface.
2. **Isolated network image:** derive clocks, independent PHY reset, MDIO
   initialization, and IO/CDC constraints from the VCU118 example. Check the
   PHY-clock/reset dependency explicitly. Prove stable 1G link and packet
   loopback/CRC handling before connecting to Ara memory. Preserve the golden
   Ara `.bit` and matching `.ltx` for recovery.
3. **Bounded download protocol:** reuse a proven ARP/IPv4/UDP implementation;
   fixed addresses and standard MTU first. Add session/sequence/address/length,
   integrity checks, ACK/retry and duplicate suppression. Validate a complete
   packet before DMA and acknowledge only after write responses. First prove
   behavior with BRAM, including loss, duplication, malformed length, range and
   reset cases. No arbitrary register writes or remote program launch.
4. **DDR integration:** separate validated streaming DMA path and arbiter at the
   DDR interface, avoiding the unresolved LLC/JTAG burst path. It is not assumed
   correct merely because it avoids that path. Check AXI IDs, responses, 4 KiB
   splits, byte strobes, backpressure, arbitration, outstanding draining, reset,
   and CDC. Keep CPU passive during download and enforce destination ranges.
   Establish cache coherency/boot policy; a fence alone is not a cache flush.
5. **End-to-end:** PC ELF parsing/BSS handling, DDR readback/hash, then reuse
   JTAG launch/run-ID/result checks and snapshots. UART remains for logs. Test
   smoke/trap and large transfers, packet faults and recovery, plus unchanged
   CPU/Ara traffic. Measure verified payload bytes/time separately from tool
   startup and software execution; do not claim a speedup from line rate.

The next hardware image should test the network in isolation, not simultaneously
introduce a new network stack, DMA, and Ara memory path. The user's next action
for now is only the preflight command above.

## References and Local Tests

- [VCU118 board guide UG1224](https://docs.amd.com/v/u/en-US/ug1224-vcu118-eval-bd).
- [AXI Ethernet PG138 v7.1, May 2019](https://docs.amd.com/api/khub/documents/ZfG2eaY4zZT4hU~HF5MaaA/content):
  historical configuration and VCU118/KCU116 example (printed page 141), not
  evidence of which IP version is installed in Vivado 2020.1.
- [PG138 revision history](https://docs.amd.com/r/en-US/pg138-axi-ethernet/Revision-History):
  records version 7.2 on June 24, 2020; installed versions above are from the
  actual uploaded catalog, not inferred from this document date.
- [Vivado IP flow UG896 v2019.1](https://docs.amd.com/api/khub/documents/v9xbbDpXI1pI8~L4nCyifA/content):
  product and in-process example generation.
- Repository board contract: `hardware/fpga/ara_dsa_vcu118/board_files/vcu118/2.4`.

```bash
python3 -m unittest discover -s hardware/fpga/vcu118/tests -p 'test_host_ethernet_preflight.py'
python3 hardware/fpga/vcu118/tests/host_ethernet_preflight.py --static-only
```

Mock tests check control flow, evidence and rejection behavior, not the vendor
IP's actual supported properties, licensing, electrical behavior or timing.
