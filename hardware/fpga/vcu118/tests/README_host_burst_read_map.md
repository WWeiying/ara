# Read-Only Host Burst Mapping

Run from `hardware/fpga/ara_dsa_vcu118/software` in a Vivado-enabled shell.
Close the GUI hardware target connection first. Leave the board powered and
programmed with the host design; do not run concurrent board tests.

In PowerShell, with `$P` set to the matching `.ltx` file:

```powershell
py -3 ..\..\vcu118\tests\host_burst_read_map.py $P
```

Add `--fixed-probe` to compare two FIXED reads per region with the normal INCR
reads in the same session. A correct FIXED read returns the starting word on
every beat. If only INCR is wrong, address progression is suspect; if FIXED is
also wrong, inspect R-channel ordering/capture before attributing an address
fault. This option is read-only and does not reset the JTAG AXI core.

Results go to a unique `burst_maps/<timestamp_and_suffix>/run` directory under
the current directory. The script prints its location before connecting, then
prints the mapping for each region. Optional positional argument two selects
an explicit, new output directory. `--vivado` accepts an executable or `.bat`
path when Vivado is not on PATH. No here-string or pasted Python is needed.

The diagnostic uses existing host transport and identity checks. It reads
32 independent 64-bit words before and after varied two/three-beat reads at
DDR scratch `0xffff0000` and uncached LLC SPM `0x1401ff00`. It neither writes
memory/debug registers nor resets or launches the CPU. It does not reprogram
the board or change RTL/constraints.

`map.json` retains raw data, all matching single-read addresses, window
stability and partial failures. Transport logs are under `transport/`.
Repeated values, unmatched words and unstable windows remain ambiguous.
Completing this diagnostic is not a burst correctness pass; exit code zero
means evidence was collected. Stable before/after reads do not exclude
intervening memory changes.

Local mock validation from this tests directory:

```sh
python3 -m unittest -v test_host_burst_read_map.py
```

These tests validate the diagnostic and CLI, not FPGA behavior.

## Observed Board Mapping

The user-reported run `20260924_114552_iliphukc` found stable windows in both
regions. Relative to a 64-byte-aligned base, two/three-beat reads matched:

| Start | Single-read addresses matching successive burst words |
| --- | --- |
| `+0x00` | `+0x00`, `+0x48`, `+0x90` |
| `+0x08` | `+0x08`, `+0x50` |
| `+0x38` | `+0x38`, `+0x40`, `+0x88` |
| `+0x40` | `+0x40`, `+0x88` |

These observations fit `line_base(start) + 64*n + ((start + 8*n) & 63)`.
This describes matching data, not a captured internal bus address. It rejects
the hypothesis of a constant 72-byte stride at all starting offsets, but
does not identify the faulty component. Keep burst writes/load disabled;
the independently verified single-beat mode remains separate.

## Inspect the Archived Netlist

From the same exported software directory and Vivado-enabled shell:

```powershell
py -3 ..\..\vcu118\tests\host_axi_netlist.py $P
```

This reads the adjacent `bitstream.json`, checks checkpoint/probes hashes,
opens that exact routed DCP, reports JTAG AXI port widths and the leaf
drivers of SIZE/LEN/BURST pins, and exports small LLC address-handling
submodules if their hierarchy survives optimization. It does not connect
to hardware, reload current RTL/XDC, synthesize, implement or write a bitstream.
Allow several minutes to open the DCP; progress goes to `vivado.log`.

Outputs are placed in a unique `axi_netlists` subdirectory. A static SIZE
value of `011` corresponds to an 8-byte beat. `???` is unresolved/dynamic,
not a bus value or proof of an error. Dynamic LEN/BURST drivers are not
cycle-level observations. This diagnostic alone cannot sign off the design.
Missing hierarchy is reported rather than replaced by current RTL.
The generated netlists/logs stay local unless explicitly uploaded below.

The next falsifiable checks are: does the archived JTAG interface really
drive SIZE=3, and does the synthesized LLC address recurrence match its RTL?
A static report cannot establish a dynamic SIZE/LEN. For a cycle-level
distinction, observe ARADDR/ARLEN/ARSIZE/ARBURST on accepted JTAG requests,
the LLC descriptor/SRAM request addresses on their handshakes, and RDATA/
RLAST on RVALID&&RREADY at the JTAG input. Incorrect requests implicate the
upstream command/core path; correct requests with wrong internal addresses
implicate the fabric; correct input R beats with wrong reported words
implicate the JTAG return/capture path. Do not alter RTL on a data-match
formula alone.

The runner and Tcl query logic have mock tests, not a local Vivado run:

```sh
python3 -m unittest -v test_host_axi_netlist.py
```

## Upload Existing Evidence Through Git

No board access or Vivado rerun is needed after netlist extraction. From the
exported software directory, run:

```powershell
py -3 ..\..\vcu118\tests\host_axi_upload.py --push
```

This selects the newest `axi_netlists/*/inspection.json` and, when present,
the newest `burst_maps/*/run/map.json`. It prints both paths before packaging.
Use `--netlist PATH` and `--map PATH` to select specific existing directories;
an incomplete newest inspection is rejected, not silently replaced by an old
successful one. Missing any of the four exported LLC netlists is an error.

Only the inspection metadata, AXI report, four LLC netlists, Vivado logs,
mapping JSON and mapping transport audit are included. There is no recursive
directory upload. DCP, bitstream, ELF, unrelated logs and source changes are
excluded. The manifest records per-file SHA256/length and the ZIP SHA256.
Selected input is limited to 512 MiB and the ZIP to 48 MiB.

`--push` authorizes sending these generated design files and logs (including
local paths) to the checkout's **origin** remote with its existing access
permissions. Without `--push`, the script only packages them in a new system
temporary directory for inspection. A fresh temporary Git repository pushes
only `evidence.zip` and `manifest.json` to a unique
`fpga-evidence/axi-<UTC timestamp>-<suffix>` branch. The working checkout's
branch, index and files are untouched; no force push, pull or checkout occurs.
Git credentials use the existing system setup; the script never reads or
packages credential files. A rejected push leaves the local package intact
and reports failure. Do not merge the evidence branch into the source branch.

Send the printed `UPLOADED_BRANCH` line to the investigator. The two selected
diagnostics are independent runs, not proof they share a board configuration.
`collection_checkout_commit` describes the upload checkout only, not the
hardware build; `inspection.json` retains the archived bitstream provenance.

Local validation includes a real push to a temporary local bare repository
and verifies that existing staged/unstaged data and branch state are untouched:

```sh
python3 -m unittest -v test_host_axi_upload.py
```

## Full Connectivity Export in One Command

The four cell exports do not include the interconnect, vendor JTAG command
logic, or the storage interfaces. Some optimized duplicate output aliases
also have no driver when a cell is exported in isolation. To retain all
connectivity without another hardware experiment, run:

```powershell
py -3 ..\..\vcu118\tests\host_axi_netlist.py --full --upload
```

The default probes path is recovered from the latest inspection's recorded
bitstream outputs. The original checkpoint and probes hashes are rechecked.
Explicitly supplying a probes path remains supported. The command opens the
same old checkpoint and adds `full_design.v` using `write_verilog -mode funcsim
-include_xilinx_libs`, then calls the isolated-branch uploader automatically.
No synthesis, implementation, programming, hardware connection, or current
RTL/XDC load is performed. The full netlist contains the entire generated
design, including memory initialization and vendor simulation primitives;
`--upload` authorizes sending it to origin, not just the four small LLC cells.
If export or hash checking fails, nothing is uploaded. This is functional
connectivity evidence, not a timing simulation or board correctness pass.

## Reproduce Local Archived-Netlist Checks

On Linux, with Icarus Verilog in PATH and the evidence branch's two files in
an external directory, run:

```sh
python3 hardware/fpga/vcu118/tests/check_host_llc_netlist.py /path/to/evidence /tmp/new_llc_check
```

This checks archive/file hashes before using the unchanged exported netlists
and their included Xilinx primitive models. The combinational AR cutter is
checked for aligned 1/2/4/8-byte transfers and all 1..256-beat lengths (FIXED
and INCR), in two address regions. Both sequential splitters are checked
with 8-byte INCR beats at 16 starting offsets, lengths 1..17 and descriptor
backpressure. The read unit checks 8-byte FIXED/INCR descriptors wholly within
one line, SRAM request addresses, request/response counts, RLAST, ID and the
retained RRESP bit, with request and response backpressure. SRAM returns dummy
data; this does not check stored contents. The exported read-unit line-address
registers survive on `r_unlock_o[index]`; the undriven duplicate line-address
port and optimized-away RRESP[0] are not interpreted as hardware faults.
Each simulation has a 120-second wall limit. No board access is required.

### Evidence 62abf705: Local Findings

Source: `fpga-evidence/axi-20260924_045820-8ac2da54`, commit
`62abf7054a0876f9924e5cebd2246ddd182e5788`.
Archive SHA256: `cb8d0d2b4c0221ce7017724f375ac649b36269e4f35c39de1a09311940eaf63c`.
All ten archived file lengths and SHA256 values were checked locally.
The recorded routed checkpoint SHA256 is
`cba09318d878dea5325d08b1ba53c55559e49def20bb282b764807cb264272ac`.
That DCP itself was not transferred or independently reopened on Linux.

The report identifies ARSIZE/AWSIZE[2:0] as Q outputs of JTAG command FIFO
register bits [23:21], all FDREs, not tied-off constants. It does not record
their values during an actual request. `CMD.SIZE=64` in the host software
and the three-bit physical pin width do not establish sampled AxSIZE=3.

Results from the unchanged exported gate netlists and included primitives:

| Check | Result |
| --- | --- |
| AR cutter arithmetic | 122,880 cases passed |
| AR splitter with/without descriptor backpressure | 544 cases, 1,088 descriptors passed |
| AW splitter with/without descriptor backpressure | 544 cases, 1,088 descriptors passed |
| Read unit, 8-byte beats with backpressure | 72 cases, 240 SRAM request addresses passed |

The cutter sweep includes long FIXED lengths as arithmetic inputs; it is not
AXI protocol compliance certification. An initial broader read-unit sweep
including narrow transfers was stopped without a completion result; it is
not counted as passing. The bounded read-unit run above matches the intended
64-bit full-width host accesses and is the reproducible check in the runner.

These tests did not reproduce the board's +0x48/+0x90 matching pattern when
correct requests/descriptors were injected into these isolated blocks.
They do not exonerate the full LLC or JTAG path. Remaining distinctions need
the actual inter-module connections, vendor command/return logic and storage
interfaces, hence the full-connectivity export above. No production RTL,
constraints, host burst mapping or acceptance checks were changed based on
this negative result. Keep using the verified single-beat loader.
