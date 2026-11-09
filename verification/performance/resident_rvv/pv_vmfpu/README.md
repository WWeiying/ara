# Resident PV: actual VMFPU integration gate

This step connects the resident controller to the existing lane `vmfpu` and
its actual `i_fpnew_bulk`. It adds neither a multiplier nor another FPU to the
production design. `EnableResidentPv` defaults to zero, and `vector_fus_stage`
ties the new inputs inactive. No instruction advertises or enables this path
yet. The testbench's second, original VMFPU is a verification reference only.

## Ownership contract

Acquisition is an explicit handshake. Native instruction queue capacity is not
an acquisition condition: issue, processing and commit must all be empty, as
must native result, mask and reduction paths. Native arithmetic and pending
flags must have drained. A simultaneous native instruction offer wins. The
parent must also drain upstream operand requests; this local endpoint cannot
prove the sequencer or resident-context state is idle.

While acquired, the existing FPU accepts only private FP16 SIMD FMA requests.
An accumulator-slot tag travels in retained `control` bits, not a discarded
operand field or a simulation-only tag. Native result queues, flags and
instruction completion cannot consume private returns. Release requires no new
private offer and a drained FPU, including output backpressure. It never flushes
an accepted operation or assumes a fixed return latency.

Private flags and results are **not architectural completion**. Before a future
SoC command releases ownership, its parent must authorize all-lane commit,
complete destination writes and publish flags. Decoder legality, register
dependencies, context locking and that commit barrier remain separate gates.

## Verification

`run.py` uses the admitted SoC's frozen packages and dependencies. It copies the
current candidate VMFPU and adapter, then replays the previously accepted 899
PV cases, including 12 real-model operand cases. It retains the same independent
SoftFloat results, every-input/return/commit checks and reset/error cases.

Four exact substitutions are made to the old testbench: the arithmetic
endpoint type, a test-only controller-busy connection, and a final ownership
drain check before simulation exits; a reset-driver correction removes an extra
unchecked clock edge before reset assertion. Runtime reset calls already occur
at negedge, so waiting for another negedge admitted an uncounted FMA. All
original comparisons and transaction balances remain required. The original file
is retained alongside the derived file. Unit tests check that reversing those
substitutions reconstructs the original byte for byte. Its checker and corpus
must match the original acceptance receipt.

Both existing arithmetic configurations are tested: `SharedFma=0` and `1`.
The old testbench's `pipe=3` receipt field is retained for checker identity; it
is not an override or measurement of the actual VMFPU FPU latency. The latter
comes from frozen implementation parameters. The private protocol uses tags and
handshakes in both configurations.

The adapter additionally injects native instructions around ownership changes,
checks their arithmetic/flags, and compares the native path against the frozen
original VMFPU. The receipt requires actual native completions and observed
ownership/backpressure scenarios. These checks are not full ISA coverage.

```sh
python3 -B verification/performance/resident_rvv/pv_vmfpu/run.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/NEW_OUTPUT
```

Output directories must be new. Inputs are pinned before compilation and checked
after execution. Failed runs and their original evidence are retained. Use host
VCS only. This gate does not run synthesis and does not measure whole-attention
or model speedup; randomized stalls and test-only return reordering deliberately
distort cycle counts.
