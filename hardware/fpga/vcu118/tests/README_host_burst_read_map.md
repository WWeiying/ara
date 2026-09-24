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
