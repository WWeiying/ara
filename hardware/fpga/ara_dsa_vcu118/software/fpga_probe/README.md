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
