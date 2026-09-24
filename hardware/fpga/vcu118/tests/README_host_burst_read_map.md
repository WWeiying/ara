# Read-Only Host Burst Mapping

Run from `hardware/fpga/ara_dsa_vcu118/software` in a Vivado-enabled shell.
Close the GUI hardware target connection first. Leave the board powered and
programmed with the host design; do not run concurrent board tests.

In PowerShell, with `$P` set to the matching `.ltx` file:

```powershell
py -3 ..\..\vcu118\tests\host_burst_read_map.py $P
```

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
The generated netlists/logs stay local; they are not added to Git.

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
