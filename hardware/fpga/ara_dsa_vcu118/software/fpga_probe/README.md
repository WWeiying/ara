# FPGA boot probe

This probe isolates VCU118 bare-metal startup from the Qwen benchmark. It
checks the UART-visible entry into `main`, CSR state, integer RVV `m1`, the
`e32,m8` vector length used by Qwen quantization, and one Qwen quantization
block. Run it with the same normal-speed bitstream and COM6/115200.

Expected output ends with:

```text
FPGA_PROBE 5 quantize_done ...
```

The last printed line identifies the failing stage if the probe stops.

## Quantization instruction diagnostic

The reported board run reached `FPGA_PROBE 4 quantize_begin`, with VLENB=128,
e32/m1 VL=32, and e32/m8 VLMAX=256. This localizes the missing completion to
the quantization region; it does NOT yet identify a particular failed instruction
or prove an RTL bug. The original `boot_probe.elf` is preserved unchanged.

Select `-Probe quant` in `run_fpga_probe.ps1`. This adds load readback and writes
`raw.log`, `elf.sha256`, and `status.json`. An incomplete run is not reported as
PASS. Keep COM6/115200 and the existing bitstream; reset the CPU before loading.

`quant_probe.elf` uses fixed-register assembly derived from the first probe's
quantization disassembly. `Qnn B` precedes an operation group; `Qnn D value`
follows a dependent scalar read AND an expected-value check. `Q00 F value` means
a numerical mismatch at the last begun stage. A missing D narrows the blocked
region to that group and its dependency/completion path, not necessarily the
first instruction named below.

For stage 01, the FPGA diagnostic also emits `Q01a` through `Q01g` markers:
they bracket `vsetvli`, `vmv.v.x`, `vmv.s.x`, and `vmv.x.s` separately. These
markers are diagnostic only and are intentionally absent from the Spike output.

| Stage | Operation group | Expected low 32 bits |
| --- | --- | --- |
| 01 | e32/m8 initialize and integer scalar read | ff800000 |
| 02 | m8 load and integer scalar read | c1700000 |
| 03 | vfmax and integer scalar read | c1700000 |
| 04 | vfmin and integer scalar read | c1700000 |
| 05 | vfredmax and floating scalar read | 41700000 |
| 06 | vfredmin and floating scalar read | c1700000 |
| 07 | scalar fdiv for scale | 41077777 |
| 08 | scalar fdiv for inverse scale | 3df1e3c8 |
| 09 | m8 multiply and floating scalar read | c2fdffff |
| 10 | rounding CSR writes and float-to-int conversion | ffffff81 |
| 11 | narrowing clip to int16 | ffffff81 |
| 12 | narrowing clip to int8, store and readback | ffffff81 |
| 13 | widening integer reduction, first 16 elements | fffffc08 |
| 14 | slide and widening integer reduction, next 16 | 00000379 |
| 15 | adjacent max/min reductions, first result | 41700000 |
| 16 | second result from adjacent reductions | c1700000 |

After those checks, the same unmodified C quantizer used by the boot probe runs.
Its 256 quantized elements, 16 block sums and scale bits are checked against an
integer reference. Only `QUANT_PROBE PASS` indicates full diagnostic completion.
The synthetic ramp is a diagnosis input, not a model benchmark or paper result.

The UART macros do not call printf, change vtype, or spill vector registers.
They do change scheduling. If all isolated checks pass but `original_begin`
does not finish, retain the original sequence for a dependency/pipeline study.
RTL investigation should then correlate dispatcher request valid/ready, instruction
IDs, lane operand queues, MFPU issue/processing counts, result writeback, and
SLDU reduction handshakes. Architectural simulation cannot validate those signals.

## Reproduction

From the repository root (Linux toolchain required):

```sh
make -C apps -B -j2 bin/ara_fpga_quant_probe.spike
install/riscv-isa-sim/bin/spike --isa=rv64gcv_zfh --varch=vlen:1024,elen:64 apps/bin/ara_fpga_quant_probe.spike
make -C apps -B -j2 fpga=1 sim_l2_mb=2 ara_fpga_quant_probe
```

The Spike variant omits UART MMIO and records the same assembly checks in memory.
It uses `printstr` instead of the simulator runtime's TLS-buffered printf.
`quant_reference.log` records a successful architectural run, not an FPGA run.
No benchmark kernel, RTL, Linux image or original boot probe is changed here.
