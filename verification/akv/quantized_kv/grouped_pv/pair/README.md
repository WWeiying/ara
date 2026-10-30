# Complete Attention grouped-PV pair

One ELF, OFF/ON/ON/OFF, using the SAME current field-copy SDK on both arms.
No SDK instrumentation, ABI additions, per-head counted callbacks, or inferred
grouped-update count. `sdk_adapter.h` directly selects API0
`akv_quant_strided_execute` or API1 `akv_quant_strided_execute_grouped_pv`.
The grouped API does not retry the original scheduler after rejection/failure.
Selection evidence is the pinned adapter/SDK, actual timed linked calls and
successful full execution, not an invented grouped counter. The common query
quantization counter is identical in both arms.

## Workload and scope

Real Q4_0 K/Q8_0 V capture, one original H6 group, D128, 128 visible tokens,
physical two-KV-head cache, output stride136. Four complete native Attention
calls; no reduced heads/tokens/dimensions or fake repetition checks. H/S control
evidence remains separate: this pair measures the grouped update within the
complete B operator, not pure hardware, a model, or Q8 K-format coverage.

Timer includes mapping, admission, query quantization, panel gather, QK,
online softmax/PV, final normalization and existing RVV drain/fence. Caller
tensor construction/output poison, post-call numerical/guard checks and UART
are excluded. One common normal linker, no forced function addresses.

Each call checks all768 finite outputs against original captured gold using
unchanged 0.004+0.002*abs(gold) tolerance. Every later call must match first OFF
bit-for-bit. Output padding and two64-byte guards remain checked. FCSR is read
before validation, must match across all calls and contain only fflags; VCSR5.
Only a 16-hex FNV digest and max-error bits are printed, no huge raw arrays.
Host compact checking DOES NOT independently recompute all768 values: numerical
evidence is the pinned full on-target checks plus separate SDK numerical gates.

Each call:8 QBS commands,6 quantizations,128 V decodes,4 K panels,9216 copied
bytes. Four calls total32 commands. `check.py` enforces exact ordered complete
lines, API0/1/1/0, no fallback, digest/CSR equality, error/work/geometry and busy
bounds. Unknown/extra/malformed protocol and work records fail. Normal boot
noise is ignored. A simulator `Command:` line is admitted only as the first
line and only with the actual exact reviewed argv.

## Immutable inputs and building

Starting historical receipt: field_copy_pair/prepare/out/build-gnu-06/build.json,
SHA ddbe521cdcd0157cbed04096a8825d4a9569233905777e6de6e58ec186c95cfc.
Its immutable artifacts and dependency identities are checked, not relabeled
as a current SDK PASS. Old live SDK pins move ONLY to exact archived candidate
blobs. All other old inputs remain exact. This historical translation does not
substitute archived SDK for new compilation.

Snapshot all current SDK C/headers and compile three fresh objects: main
(including Q8 V decoder/mapper), runtime.c, runtime_strided.c. Grouped leaf is
header-only; unknown new C units fail. Reuse14 unchanged objects only with
accepted dependency/object SHA proofs; never reuse affected SDK dependents.
GNU -M dependencies must be pinned and cannot leak live SDK headers. Preserve
the original FP policies, tool/lib identities and all original tensor/gold
bytes. Inspect actual rdcycle/drain CFG and linked API bodies before execution.
`linked-review.json` is static evidence, not proof of dynamic selection.

Recipe only (fresh directory required):
```
python3 -B verification/akv/quantized_kv/grouped_pv/pair/prepare.py --output verification/akv/quantized_kv/grouped_pv/pair/out/recipe-review
```
GNU build, never VCS:
```
python3 -B verification/akv/quantized_kv/grouped_pv/pair/prepare.py --build --output verification/akv/quantized_kv/grouped_pv/pair/out/build-gnu-01
```
Failures remain in their fresh directories. `checked_build(build.json)` rechecks
pins, actual GNU command ledger, tensor payloads, archived dependency proof,
and linked timer/API evidence. Both source branches use current frozen SDK;
there is no before-field-copy arm or reused historical timing.

## Worker review and execution

`run.py --build <build.json> --build-sha256 <reviewed-sha> --output <fresh-out>`
defaults to offline preflight; no simulator/EDA subprocess. Canonical image
must pass the unchanged actual canonical checked_soc contract:
canonical-shared-resources-build-20261025-02, result SHA
e554e706c54298aaf98ff6cfafc23e2c1fd23c6eba4da44c8b80be0da5103724.

Only after parent source/linked-body/preflight review may a direct-owned
systemd service use `--execute-reviewed`, timeout at most10800 seconds. The
existing bounded process cleanup runs children in a private cwd. Actual UVM
requires events/backend/AXI/AXI-write using unfiltered raw log/trace. Source,
ELF/image/config/graph/helper pins are checked before/after; active service
stdout is not sealed as evidence. No service is launched by preparation.
Measured regression is reported honestly; a functional PASS does not promise
a speedup or deployment. No whole-model, PPA or independent per-command FP
oracle claim follows from this pair.
