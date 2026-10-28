# Expanded stride repair acceptance

The accepted result is
`verification/out/m4-stride-expanded-20261027-01/acceptance-result.json`, SHA-256
`9e4c24cc666ee24c72dcdfa1791c6c19cca8f8888a07a46e66d1a3326c86e06f`.
This is a functional graph test of the private repaired integration object,
not an installed-runtime, RTL performance, or whole-model result.

| Weight format | Paired graphs | Compared outputs | Native commands |
| --- | ---: | ---: | ---: |
| Q4_K | 16 | 976 | 84 |
| Q6_K | 17 | 1096 | 92 |
| Q4_0 | 16 | 976 | 84 |
| Q8_0 | 16 | 976 | 84 |
| Total | 65 | 4024 | 344 |

All output pairs are finite and bit-exact. Each pair runs the same logical
activation values once in a dense control and once in a legal strided view.
The actual scheduler callbacks preserve the input tensor, data address, backing
allocation and strides; a hidden contiguous replacement is not accepted.

## Covered paths

- K512, N8, M1/3/4/7/8/15 across the four formats; additionally Q6_K K1536,
  M15, wide-M enabled, two threads, 8-byte element stride and 16-float padding.
- 32 single-thread and 33 two-thread cases; 17 wide-M cases actually select
  the wide workspace and issue M8/M7 commands. A flag alone is insufficient.
- Actual element strides are 4 or 8 bytes. Row strides are
  2052/2112/4100/4108/12352 bytes. Padding and interleaved unused elements,
  input guards, weights and repacked weights retain their original bytes.
- M1 GEMV, M3 tails, M4 groups, M7 groups plus tails, and M8/M15 wide paths
  reconcile to 244 runtime calls and 344 native commands. Command counts are
  M1=24, M3=72, M4=168, M7=28 and M8=52.
- The activation source is a captured Qwen2.5-1.5B tensor [1536,15]. K512
  selects each row's prefix; K1536 uses the complete rows. Test weights are
  deterministic and reference-quantized, not claimed to be captured weights.
- Q8_K producer traces distinguish dense full-K preparation from gathered
  block preparation. The existing Q8_0 Zvfh path has no equivalent producer
  trace; its evidence is symbol ownership, actual view strides, native call
  accounting and output comparison, not an inferred counter.

## Independent audit

The parent review replayed the four raw logs through `check.py`, compared each
result with the recorded per-format and combined JSON, and verified all 1952
accepted input hashes. It separately checked the 1880 inputs of the still-live
complete Q/V/K VCS experiment. None changed.

`test_check.py` covers actual-log replay and eleven corrupt-evidence rejection
tests, including one-bit mismatches, missing calls, nonfinite output, changed
strides, hidden input replacement, wrong wide selection and incomplete exits.

## Preserved preparation failure

`run.py` originally stopped before QEMU because its link gate rejected any
archive member named `repack.cpp.o`. Both the general and architecture-specific
source files use that basename. This does not establish duplicate integration
code: the RISC-V archive member supplies quantization helpers.

`accept.py` is the explicit successor. It checks that the four QBS
`forward_mul_mat` specializations and the buffer entry point are supplied by
the accepted private object, then runs the already linked test. It neither
rebuilds the image nor changes the numerical checker. The original
`result.json` stays FAIL; only `acceptance-result.json` is the accepted result.
The original README and scripts remain unchanged as sealed evidence inputs.

## Remaining integration gate

Promote the blockwise input helper and dispatch changes to normal runtime
sources, rebuild normal libraries without object overrides, and repeat graph
and model checks together with the selected packed producer. This evidence
does not cover `MUL_MAT_ID` or justify a performance claim for strided views.
