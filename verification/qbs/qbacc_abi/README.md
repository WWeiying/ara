# Optional QBACC ABI gate

This tests definitions, not execution. No decoder, engine, runtime, or QEMU
execution path is enabled. Architecture, numerical-contract and descriptor
versions are unchanged. QBACC uses QBEXEC fields plus funct7 bit 3 (instruction
bit 28); bits 2:0 still encode M-1. The encoder is available in all builds, but
callers must query support before execution.

QBINFO index 4 bit 0 announces VRF continuation; all other bits are reserved
zero. `ARA_QBS_VRF_CONTINUATION` is a presence-based define, like
`ARA_QBS_ENABLE`: omit it to disable (defining it to zero still enables it).
C advertisement additionally requires VLEN exactly 1024. SV additionally
requires QbsEnable. Existing capability indices are not newly gated.
The unchanged C reference forwards to the generated header and inherits this
build gate. Previously built/default QEMU does not acquire the new capability.

Run from the signoff worktree, using an archived pre-change source tree:

```sh
python3 verification/qbs/qbacc_abi/run.py \
  --baseline-dir verification/out/qbacc-abi-sidecar-20261023-01/before \
  --output verification/out/qbacc-abi-sidecar-20261023-01/check
```

The runner refuses to reuse output. It runs generator `--check`, spec mutation
and checker tests, five host GCC variants (baseline and both generated headers
default/enabled), and four package-only VCS variants (each combination of the
two defines). Compilation is bounded at 300 seconds per command; each binary
at 30 seconds. C checks remain enabled with NDEBUG. No SoC or compute test runs.

Each variant covers 262144 M/register encodings and 2304 capability queries
(256 indices across nine VLEN values, including 1023/1024/1025). C also checks
all QBINFO register encodings and the unchanged reference capability entry.
Every existing capability word is compared with the archived header/package;
new index 4 is checked against an independent literal 0/1 expectation. SV has
no production encoder: its encoding checks exercise generated field constants,
not decoder acceptance. SV comparisons use case inequality to reject X/Z.
The archived SV package is mechanically namespace-renamed only.

Logs, commands, pre/post source SHA256, ELF/image hashes, and a final result
are retained under output. Any failed command, malformed PASS, changed legacy
word, or source drift prevents PASS. This does not certify QBACC execution,
fault atomicity, accumulator continuation, or production performance.
