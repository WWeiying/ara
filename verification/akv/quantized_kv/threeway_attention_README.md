# Same-Executable Attention Attribution

This inquiry separates shared software scheduling from the incremental native
QBS path. It is not a new arithmetic implementation and does not change RTL,
the runtime selector, or existing performance/tail workers.

## Modes and Measurement

One ELF runs `H,S,B,B,S,H` on the same captured Query and token-major K/V:

| Mode | QK | Schedule | V Row Decoder | Admission / K Gather |
| --- | --- | --- | --- | --- |
| H | Production scalar-output RVV dot, `nrc=1` | Head-major | Production RVV helper | None |
| S | The same dot and checked callback | Shared across Query heads | The same helper | None |
| B | Native QBS M4/M2 commands | Shared across Query heads | The same helper | Actual public-entry mapping, admission and gather |

The real capture supplies six Query heads in one GQA group, D128 and 128
visible tokens. Its physical cache holds two KV heads and capacity256. K token
strides are 144 bytes for Q4_0 and 272 bytes for Q8_0; V token stride is272
bytes. Query quantization runs six times inside every measurement. Initial
capability discovery and tensor setup remain outside all windows; the B
public-entry mapping and bounded K gathering remain inside its window.

H and S both call the same checked callback. Callback-local validation and
software counter maintenance are timed. H/S therefore measures the complete
shared scheduling change, including fewer callback invocations; it is not an
isolated V-memory-access experiment. The generic helper's validation cost must
not be silently attributed to production llama.cpp itself.

| Expected Per Trial | H | S | B |
| --- | ---: | ---: | ---: |
| Query quantizations | 6 | 6 | 6 |
| QK callbacks | 768 | 8 | 8 |
| Actual RVV dots | 768 | 768 | 0 |
| Native QBS commands | 0 | 0 | 8 |
| V decodes | 768 | 128 | 128 |
| K panels / copied bytes | 0 / 0 | 0 / 0 | 4 / 9216 or17408 |

The helper uses actual K head/token strides and already-quantized Query rows;
it does not create a packed K mirror for S. Host spies validate coordinates,
output layout, tails, rejection before callback-local writes, guards, counts
and unchanged per-head online arithmetic. Host tests do not validate native
RVV arithmetic or provide cycle measurements.

## Independent Acceptance

`check_threeway_attention.py` independently checks all768 outputs against the
original model golden, H/S exact bits, each mode's exact repeat, final FCSR and
VCSR, strict six-trial order and software work counts. Only B may emit QBS
performance records: all16 commands must match their M4/M2, N32, Kblocks4,
profile, useful work and success contracts. DUT guard failures are rejected.
Mutation tests check missing/duplicated work, wrong order, unsupported layout,
flags, numerical mismatch, false status and incomplete termination.

The transcript checker alone is not sufficient acceptance.
`run_threeway_attention.py` verifies source/build/image identity before and
after execution and runs the independent UVM/AXI/trace checker. It first
replays the terminal strided-cache and 5/33-token tail prerequisites, including
the tail QK oracle and their protocol-input hashes. A PASS label alone is not
accepted. No execution or performance result is claimed by a successful build.

Derived ratios use only cycle sums from this ELF:

- H/S: shared scheduling overall benefit.
- S/B: incremental QBS public-entry path, including its actual gather and
  admission costs, not a pure arithmetic-unit speedup.
- H/B: combined change for this reconstructed complete Attention slice.

These are not whole-model ratios and must not be multiplied with prior
projection or isolated V-decoder results. Existing default-off experimental
selection stays unchanged.

## Build and Test

Run from the verification worktree:

```bash
python3 -B -m unittest discover -s verification/akv/quantized_kv \
  -p 'test_threeway_attention_*.py' -v
python3 -B -m unittest discover -s verification/akv/quantized_kv \
  -p test_shared_rvv_qk.py -v
python3 -B verification/akv/quantized_kv/build_threeway_attention.py \
  --base verification/out/akv-quantkv-strided-attention-q8-build-20261024-01 \
  --output verification/out/akv-quantkv-threeway-attention-q8-build-20261024-03
```

Use the corresponding `q4` predecessor for Q4_0. The output directory must be
new. The builder keeps predecessor objects, actual cache payloads and compiler
policy, compiles a new main, checks GNU disassembly and the16MiB image bounds,
and records source/artifact hashes. `threeway_strided_primitives.h` is an exact
prefix copy of the frozen predecessor, checked before building; this avoids
editing a file owned by running consumers or changing its decoder accidentally.

The initial Q8 build `...-01` records a nested-main preprocessing failure and
is not a valid executable. Its evidence is retained. Q8 `...-02` and Q4
`...-01` were compile checks before all loaded repository Python helpers were
added to the pin inventory. Use Q8 `...-03` and Q4 `...-02` for subsequent
execution gates; do not substitute the earlier receipts.
No VCS campaign is launched by these build commands. The successor must not
execute before the existing strided/tail gates finish and pass raw rechecking.

For completed prerequisites, the worker interface is:

```bash
python3 -B verification/akv/quantized_kv/run_threeway_attention.py \
  --build verification/out/akv-quantkv-threeway-attention-q8-build-20261024-03 \
  --prerequisite verification/out/akv-quantkv-strided-attention-q8-20261024-01 \
  --tail verification/out/akv-quantkv-tail-attention-q8-20261024-01 \
  --output verification/out/akv-quantkv-threeway-attention-q8-20261024-01 \
  --timeout 10800
```

An independent user service may own this worker directly. When prerequisites
are still executing, `--strided-owner-pid` and `--tail-owner-pid` enable kernel
pidfd event waits on the exact original worker identity. These are not periodic
polls and do not start another simulator during the wait. All loaded repository
helpers and build inputs are frozen before waiting, then rechecked afterward.
A failed, timed-out, incomplete or mismatched prerequisite stops the successor.
Its `WAITING_GATE` status is not an executing simulator or a measured result.
The VCS execution itself remains bounded to three hours per format.
