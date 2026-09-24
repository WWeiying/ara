# VCU118 J10 Ethernet Downloader: Preflight and Bring-Up Plan

Status: **IP/environment preflight only. Ethernet download RTL is not integrated,
and no link, throughput, or Ethernet-to-DDR test has passed on hardware.**
The existing UART and JTAG single-beat loader remain unchanged.

Latest Windows evidence (`227b2a84c8e9d3fe35c1558b47a3f0f5aa0514df`): **all 11
preflight stages passed** using collector `6c94d2ff`. TEMAC reports **Bought** for
both generated and available Synthesis license levels. Example generation now
completes with inherited console handles and a Vivado-native log. This validates
the launch workaround in one Windows run, not Ethernet hardware operation.
Preserve `D:/fpga_runs/ara_eth_zr9jsk58`; there is no need to repeat this preflight
unchanged. Next is the example clock/reset/pin review, before an isolated network
build or Ara integration.

## One Windows Command

This command creates a new preflight. For the already successful
`ara_eth_zr9jsk58` run, use **Collect the Existing Example** below instead;
do not regenerate IP just to collect the review inputs.

From PowerShell, after updating the `ara_dsa` checkout:

```powershell
py -3 D:\project\ara\hardware\fpga\vcu118\tests\host_ethernet_preflight.py --upload
```

No board connection, `.ltx`, reset, or programming is needed. Vivado GUI can stay
closed. The runner prefers `D:/Xilinx/Vivado/2020.1/bin/vivado.bat`, then PATH.
Use `--vivado PATH` for another installation of **2020.1**. Other versions are
reported and rejected, not silently treated as equivalent.

The script creates a unique short directory under `D:/fpga_runs` (system temp on
Linux), prints its path, and uses Vivado's native `-log` to write `vivado.log`.
Vivado inherits the PowerShell console, so output is also visible while it runs.
Run directly in PowerShell, without piping or redirecting the command's output,
and wait for the final stage summary and upload branch. It never opens
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

## Collect the Existing Example

The next gate needs actual top-level connections, reset/control logic and XDC
content, not only the preflight's list of file names. The offline collector reads
the successful directory without running Vivado, regenerating IP, modifying
the example/Ara project, or connecting to hardware. Use ordinary PowerShell;
no GUI, board power, terminal indentation, or Vivado environment setup is needed.

```powershell
git -C D:\project\ara pull --ff-only origin ara_dsa
if ($LASTEXITCODE -eq 0) { py -3 D:\project\ara\hardware\fpga\vcu118\tests\host_ethernet_review.py D:\fpga_runs\ara_eth_zr9jsk58 --upload-example }
```

**Upload scope is different from preflight:** `--upload-example` explicitly
uploads the selected generated example integration HDL and XDC, plus XCI/XPR
configuration and existing diagnostic reports, to an isolated branch at `origin`.
Omit it to create a local bundle only. Upload only to a remote where these example
files may be shared; the script neither strips notices nor changes their license.
It does not select TEMAC/PCS-PMA implementation HDL, encrypted cores, license
files, bitstreams, checkpoints, simulator products or the entire project tree.
The current successful inventory selects:

- 17 allowlisted Verilog files under `imports`, covering the example top, support,
  clock/reset, AXI-Lite initialization and example packet/FIFO logic.
- 15 XDC files recorded by Vivado, including scoped/OOC constraints. These are
  review inputs, **not** 15 files to apply unconditionally to a new top level.
- 11 XCI configuration XML files, the example's XPR metadata, and 7 preflight
  reports. `review.json` adds hashes, parsed IP parameters and explicit open
  hardware/build acceptance flags. A recognized XML schema is not an IP check.

The collector requires the supported configuration, completed preflight/stages,
the matching bundled board XML, and required integration files. It validates
inventory counts, rejects path traversal/links, protected content and oversized
inputs, and checks the archived bytes against the collected hashes before any
push. Source files are hashed now; the earlier preflight did not hash generated
HDL, so this does not prove they remained unchanged since generation. An intact
preflight directory can be moved; inventory paths are mapped only within it.

Expected output includes `COUNTS`, `REVIEW_REQUIRED`, `UPLOADED_BRANCH` and
`UPLOADED_COMMIT`. Send the branch/commit, not individual source excerpts. No
network bitstream or synthesis is produced, and `build_ready` remains false.
After reviewing this one bundle, the next deliverable is the isolated network
build/test flow, with explicit pin, clock, PHY-reset, MDIO and control settings.

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
failures. The next uploaded run below confirmed the correction in Windows.

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
stage ran in that evidence; the subsequent runs below reached those stages.

### Generated IP and the Original License Blocker

Run `D:/fpga_runs/ara_eth_9k5nelr8`, uploaded as
`f8d60ab166fbca0c1f02e3413bfa9b6cb95c8159`, passed all stages through
`license_after`. Two separate findings must be preserved:

- The example flow added HDL and XDC, exported simulator scripts, then printed
  `can not find channel named "stdout"`. `open_example_project` returned an
  error; the example inventory was skipped. The log localizes the failure to
  that flow, but does not identify which command closed or lost the channel.
  This does not establish a vendor RTL bug or a completed example.
- `ip_status_after.rpt` lists `tri_mode_eth_mac@2015.04` with generated **and**
  available license level `Design_Linking` for Synthesis. This is not a hardware
  license. Successful IP generation and the two license-report commands do not
  approve a board bitstream. AVB is disabled; its additional table rows are not
  used to infer the required TEMAC feature's license level.

The runner now records `diagnostics.temac_license` and any observed stdout
channel error even when the example stage fails, and prints both independently.
A detected TEMAC Design_Linking level rejects overall success even if every
command stage passes. Unknown tables remain unverified. Full/Bought/Purchased
levels are recognized while preserving the raw report values; neither these nor
Hardware_Evaluation set `bitstream_license_verified` or `hardware_verified`.

### Purchased License and the Remaining Example Failure

After license activation, run `D:/fpga_runs/ara_eth_ymyhv6sh`, uploaded as
`9523a342e8947de5c7834d0eab97c1da71cb2d48`, reports available level `Purchased`
before generation and generated/available TEMAC Synthesis levels `Bought` after
generation. The earlier Design_Linking blocker is no longer observed. The same
`stdout` error persists after simulator script export, independently of licensing.

The runner previously used Python to redirect Vivado stdout/stderr to a regular
file and passed `-nolog`. The hypothesis under test is that this Windows batch
launch arrangement contributes to the missing Tcl stdout channel. It now leaves
the console handles inherited and lets Vivado manage its own `-log` file. This
was a candidate workaround at that point, not a proven root cause or a vendor
patch. The subsequent run below confirms example generation succeeds with it.

To distinguish channel failures, `preflight.rpt` records:

- A separate `console` stage, Tcl version, channel names and an actual stdout
  write/flush at startup and immediately before/after example generation.
- Example return code and original error stack, including when stdout fails.
- Temporary, observation-only Tcl execution traces of `close stdout` and
  `chan close stdout`, with calling frames. Traces are removed after the call.
  They observe only this interpreter, not child interpreters or native code;
  absence of a close trace does not prove the channel was never closed.

If stdout fails before the example, the example is not attempted. If stdout
disappears during it, the run fails even if the example command returned success.
If the parent channel remains healthy but the example fails, the remaining fault
must be investigated inside the example flow; it cannot be called fixed. Errors
are never ignored to accept a partially exported example. No license, IP
configuration, board constraint, vendor installation, or Ara RTL is changed.

Linux tests cover command construction and inherited stream options, report
classification, 18 mocked vendor-flow scenarios, and four isolated Tcl processes
that really close stdout. They cannot reproduce Windows Vivado internals.

### Windows Preflight Passed

Run `D:/fpga_runs/ara_eth_zr9jsk58`, uploaded on branch
`fpga-evidence/ethernet-20260924_104025-8f42693a` as
`227b2a84c8e9d3fe35c1558b47a3f0f5aa0514df`, establishes:

- Vivado 2020.1 exited with code 0; all 11 stages passed, including `example` and
  `example_inventory`, with the same requested IP configuration as before.
- Actual stdout writes and flushes succeeded at startup and before/after the
  example. The example returned 0 and opened `eth_j10_ex`. No stdout channel
  error or `STDOUT_CLOSE` event was recorded. Channel names alone are not a
  validity check: this Vivado lists file handles rather than a literal stdout
  entry even though the stdout write/flush succeeds.
- The example inventory contains 158 files, including 15 XDC files. This is an
  inventory, not proof that all constraints are applicable or complete.
- The required TEMAC Synthesis row is `Bought / Bought`. Neither bitstream
  generation nor hardware access occurred. Both hardware acceptance flags remain
  false, intentionally.
- Archive/member SHA256 values, collector source hashes, requested configuration,
  stage results and the license table were checked against the uploaded manifest.

The practical example-generation blocker is cleared in this run. The console/log
change is supported as a workaround; the evidence does not isolate whether handle
redirection, native logging, or an internal tool interaction caused the original
failure. Do not call it an Ethernet RTL repair or alter IP settings to chase it.

Before building or programming a network image, review the generated example's
`eth_j10_example.v`, `eth_j10_support.v`, `eth_j10_clocks_resets.v`,
`eth_j10_axi_lite_ctrl.v`, `eth_j10_ex_des_loc.xdc`, and
`eth_j10_example_design.xdc`, together with the IP's scoped clock/board XDC.
These files remain under `example/eth_j10_ex`; the uploaded bundle contains only
their inventory, not their contents. Establish independent PHY reset release,
the reference-clock dependencies, actual external PHY MDIO initialization,
board-pin/electrical matches, and the example's test-mode controls first. Do not
infer these connections from file names or use an unreviewed example bitstream.

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
introduce a new network stack, DMA, and Ara memory path. Current evidence is
sufficient to proceed with the licensed-MAC route. Example generation has passed;
its clock/reset/constraint review remains open before building that network image.

## References and Local Tests

- [VCU118 board guide UG1224](https://docs.amd.com/v/u/en-US/ug1224-vcu118-eval-bd).
- [AXI Ethernet PG138 v7.1, May 2019](https://docs.amd.com/api/khub/documents/ZfG2eaY4zZT4hU~HF5MaaA/content):
  historical configuration and VCU118/KCU116 example (printed page 141), not
  evidence of which IP version is installed in Vivado 2020.1.
- [PG138 revision history](https://docs.amd.com/r/en-US/pg138-axi-ethernet/Revision-History):
  records version 7.2 on June 24, 2020; installed versions above are from the
  actual uploaded catalog, not inferred from this document date.
- [PG138 v7.2 VCU118/KCU116 board description](https://docs.amd.com/r/7.2-English/pg138-axi-ethernet/VCU118/KCU116-Board)
  and [example components](https://docs.amd.com/r/7.2-English/pg138-axi-ethernet/Components-of-Example-Design):
  architectural review references, not substitutes for the generated 2020.1 files.
- [Vivado IP flow UG896 v2019.1](https://docs.amd.com/api/khub/documents/v9xbbDpXI1pI8~L4nCyifA/content):
  product and in-process example generation.
- [Tcl execution traces](https://www.tcl-lang.org/man/tcl8.6/TclCmd/trace.htm):
  observation of channel-closing calls, not a Vivado workaround guarantee.
- Repository board contract: `hardware/fpga/ara_dsa_vcu118/board_files/vcu118/2.4`.

```bash
python3 -m unittest discover -s hardware/fpga/vcu118/tests -p 'test_host_ethernet_preflight.py'
python3 -m unittest discover -s hardware/fpga/vcu118/tests -p 'test_host_ethernet_review.py'
python3 hardware/fpga/vcu118/tests/host_ethernet_preflight.py --static-only
```

Mock tests check control flow, evidence and rejection behavior, not the vendor
IP's actual supported properties, licensing, electrical behavior or timing.
