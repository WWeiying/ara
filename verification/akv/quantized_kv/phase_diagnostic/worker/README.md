# Three-Call Diagnostic Worker

Parent review pending. No EDA launch is authorized by this implementation.
Only this directory belongs to the worker owner; accepted workers, six-call
checkers, preparation/analysis helpers, RTL and external llama are unchanged.

The worker consumes `prepare/out/<build>/build.json`, not a six-call ELF.
It requires a separately parent-reviewed JSON and its SHA256 via `--review`
and `--review-sha256`. Review schema:

```json
{
  "schema": "quant_hsb_phase_worker_review_v1",
  "program_receipt": "/absolute/path/to/prepare/out/build/build.json",
  "program_receipt_sha256": "64 hex digits",
  "helper_pins": {"/absolute/path/to/helper": "64 hex digits"},
  "phase_map": "/absolute/path/to/phase-map.json",
  "phase_map_sha256": "64 hex digits",
  "runtime_environment": {"LD_LIBRARY_PATH": "exact inherited value, or null if unset"}
}
```

`helper_pins` must include every `.py`, `README.md`, and `.gitignore` in
`prepare/` and `analysis/` (excluding their output directories). The review
also pins `analysis/analyze.py`. Do not generate review hashes while a producer
is still editing. The phase map uses the analyzer's `quantkv_phase_map_v1`:
reviewed function/range labels only, never inferred inlined phase claims.
An empty functions map and ranges list is valid but leaves everything explicitly
unclassified. The worker's `retirement.py` uses the analyzer's ELF validation,
disassembly map and streaming `analyze()` engine API directly. It does not use
the analyzer's older standalone transcript parser. Its timing inputs come from
the worker's independently checked three-call transcript, without synthesized
rows or a six-call transformation. A full pinned input manifest and post-check
bind the adapter's result to the raw log, ELF, scalar/vector trace and helpers.

The accepted Execution preserves LD_LIBRARY_PATH. This worker preserves it too,
requires an exact match to the reviewed value (unset and empty are distinct),
and pins runtime-environment.json plus the execution environment before/after.
Static ldd inspection resolved the accepted simv dependencies both with and
without LD_LIBRARY_PATH: its RPATH contains $ORIGIN/simv.daidir, ./simv.daidir
and the VCS V-2023.12-SP1 linux64/lib directory. That does not prove runtime
dlopen dependencies, including PLI libraries, are independent of the inherited
environment; no such assumption is made. No simulator was invoked for this audit.

Execution uses canonical_q4_hsb/run.py's accepted canonical checked_soc and
original Execution, before/after manifest checks, L2 admission, four required
UVM checks, unfiltered COMMIT_TRACE and VECTOR_TRACE. Scalar trace generation
has no row cap. No sampling, prefix/suffix extraction, or truncation is allowed.
One attempt only, timeout 1..10800 seconds, fresh independent output. Run the
worker itself as the direct process of any future transient service.

The default invocation is offline preflight. Actual execution additionally
requires `--execute-reviewed-diagnostic`, which is not approval to launch now.
PASS is diagnostic only: all 2304 outputs, eight commands, CSR/work checks,
UVM, retirement analysis and input/image post-pins must pass. It is never
six-call repeatability or performance acceptance.

Host tests: `python3 -B -m unittest discover -s verification/akv/quantized_kv/phase_diagnostic/worker -p 'test_*.py'`.

The real-artifact tests require final prepare/out/build-gnu-02 explicitly; they
do not select an arbitrary passing build. Its ELF/disassembly, both timer PCs,
original golden data and native command sites pass through the retirement
adapter API with synthetic host rows. This tests integration, not actual program
execution, numerical execution evidence, or real phase attribution.

The native implementation is software/qbs/src/qbs_native_riscv.c inline assembly,
not a separate native_riscv.S in this tree. Source cases 4 and 2 emit 06b5045b
and 02b5045b respectively. Final linked PCs are 0x800025d0 (M4, preceding
vsetvli encoding 0d22f057) and 0x80002630 (M2, preceding 0d12f057), both within
qbs_native_execute_command. Tests verify ELF bytes, source identity against the
original object-build source pins, vector configurations and the analyzer's
exact [M4,M2]*4 expectation. Other native variants exist in the ELF but must
not retire inside the measured H/S/B windows.
