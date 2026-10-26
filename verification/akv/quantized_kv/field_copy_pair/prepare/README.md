# Field-copy pair preparation

GNU-only preparation, no simulator or EDA invocation. Baseline 839a0362 and
candidate 083d4ed8 execute the identical accepted six-call H/S/B/B/S/H source.
This is a fresh pair, not a continuation of an old ELF or old timing result.
Each side retains 768 outputs per call, all original golden/guard/CSR/repeat
checks, six full operators and sixteen QBS commands. The same accepted canonical
image is required downstream. A previous six-call run took about 162 minutes;
this is not a guarantee of completion within the unchanged 10800-second bound.

Private version trees contain the quantized Attention headers/C files and the
unchanged local main include closure. Main (including the Q8 V decoder and GGML
mapper), runtime.c and runtime_strided.c are rebuilt. Compiler dependency scans
check every remaining object before reuse; none may consume a changed header.
External llama files are read-only and must match their historical hashes.
Original compile flags, including per-TU FP contraction policy, are retained.
Only the five changed pre-existing headers are translated to baseline blobs
when checking the historical program. No imported module is monkeypatched.

Both arms use identical ordinary linker rules and original object ordering.
The predecessor's fixed-main review padding/assertions are removed on BOTH
sides. Tensor/gold payloads must equal the accepted original; addresses,
section sizes and linked function differences are explicitly recorded, not
forced equal. This measures the compiled optimization including ordinary
layout effects, not instruction-isolated causality. The main timed CFG is
checked intraprocedurally; calls are recorded, not expanded or executed.
Numerical/RTL acceptance remains the worker's responsibility.

Run from the signoff worktree:

```
python3 -B -m unittest discover -s verification/akv/quantized_kv/field_copy_pair/prepare -p 'test_*.py'
python3 -B verification/akv/quantized_kv/field_copy_pair/prepare/build.py --output verification/akv/quantized_kv/field_copy_pair/prepare/out/build-gnu-01
```

Worker interface: build.json contains programs.baseline/candidate, each with
elf, elf_sha256 and build_receipt. input_pins is a path-to-SHA256 map; artifacts
closes generated evidence except build.json itself. Pin build.json separately.
The workload, dependency proofs, layout differences and not-executed scope are
explicit. The consumer must verify every pin before and after execution and
use the original six-call numerical/protocol checker and actual canonical
checked_soc admission. No new timing/protocol marker or reduced workload.

Use build.py:checked_pair(receipt) for the worker admission interface; it returns
the normalized quantkv_field_copy_pair_prepared_v1 report and closed pin map.
