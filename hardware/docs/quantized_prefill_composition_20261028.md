# Complete Prefill call composition prototype

The experimental `execute.h` composes whole-operation admission, bounded
causal grouping, QBS descriptor submission, activation alignment and strided
K panel reuse. It remains verification code, not enabled runtime dispatch.

For each KV head, flatten `(query token, local GQA head)` into a row sequence
and process up to eight rows at a time. Quantize each Query/head row once.
Each row retains its own visible prefix. The existing online arithmetic
produces a bounded output tile which is then copied to the tensor's actual
token/head strides. This supports groups crossing query boundaries and a
partial final group; it does not allocate a full score matrix.

Before any callback, the complete input is admitted and workspace ranges are
checked against Query/K/V/output/mask extents. Invalid input returns fallback
with no quantization, command issue or output write. Once execution starts,
command failure is terminal. Earlier groups may already be committed and
must not be silently recomputed through the ordinary backend.

The implementation initializes panel metadata rather than clearing its full
payload for each group. Gather and alignment-copy paths overwrite bytes before
use. Output staging and workspace are software buffers, not new RTL storage.
They still incur traffic and copying costs that must be included when the
complete engine is measured; the smaller running VCS scheduler experiment
alone cannot establish this entry point's performance.

## Checked behavior

```sh
python3 verification/akv/quantized_kv/prefill/test_execute.py
```

The composed test uses two KV heads, five query tokens, GQA=3 and D=96.
Prefixes are 1/33/65/32/20, so execution covers different tile counts,
nonmonotonic prefixes, unaligned activation subgroups and a seven-row tail.
It compares every output and padding word with the existing per-query Decode
implementation using the QBS numerical reference. Thirty Query/head rows are
quantized once, four output groups complete, and V decoding occurs 260 times.

Negative cases cover invalid data in the last Query/head row, output/workspace
aliasing, insufficient workspace, failure on the first command and failure
after one group has committed. The latter checks exactly which output rows
were written and which remain untouched. GCC and Clang UBSan pass.

This complements, but does not replace, real-model-data numerical checking,
native VCS execution, full runtime shape admission and performance testing.
