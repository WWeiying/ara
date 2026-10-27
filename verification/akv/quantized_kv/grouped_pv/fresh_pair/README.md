# Current-source grouped-PV complete-call experiment

The accepted earlier grouped-PV comparison was numerically correct but 2.3609%
slower for the real H6/D128/T128, Q4_0 K / Q8_0 V Decode group. Its compiled
`akv_quant_strided_execute_impl` contains a per-token integer division at
`0x80003e1c` for the public leaf's stride overflow check. This is a concrete
extra instruction on that path, not a measured exclusive stall attribution.
It must not be presented as explaining the entire regression.

The current SDK already uses multiplication-overflow detection for the same
predicate. The production tests pass: GCC and Clang each check 1010575 boundary
and deterministic full-width inputs, and RVV leaf code generation contains no
division/remainder. No guard, alias rule, numerical order, callback or fallback
contract is removed. No further SDK/RTL change is introduced in this directory.

## Why another build is necessary

The older builder correctly rejects a changed external `quants.c` dependency.
This successor does not bypass its historical identity check. Instead, it
rebuilds all seventeen objects from their current sources, using the original
GNU recipes and the exact same captured data, main program and ABBA schedule.
Both arms therefore use the same current quantizer and SDK. Every actual
compiler dependency is recorded, with source and generated-capture payload
hashes. Historical binaries and failure evidence are left untouched.

The full-linked current-source disassembly has twelve integer divide/remainder
sites rather than thirteen. The hot grouped leaf's division is gone; admission,
view validation and printf divisions remain. This is static evidence, not a
cycle saving or proof of complete-call improvement.

## Execution

```sh
python3 verification/akv/quantized_kv/grouped_pv/fresh_pair/build.py \
  --output verification/out/NEW_BUILD
python3 verification/akv/quantized_kv/grouped_pv/fresh_pair/run.py \
  --build verification/out/NEW_BUILD --output verification/out/NEW_PREFLIGHT
```

Only after build/preflight review, use `--execute-reviewed` with a fresh output
directory. A direct-owned systemd service should run the worker. It uses one
ELF, the canonical checked VCS image, unchanged original full-output/golden,
guard, CSR and work checks, and independent UVM protocol checking. Execution
is bounded to three hours. Do not modify pinned files while running.

The fresh accepted static build is
`verification/out/grouped-pv-fresh-build-20261027-01`.
It is not yet an executed numerical or performance PASS. QEMU is not used to
infer hardware cycles. Complete Attention-call timing, rather than removal of
one assembly instruction, determines whether grouped-PV remains off by default.

Hypothesis: removing the repeated division can reduce the grouped path's
software overhead enough to change its complete-call comparison. Rejection:
if fresh ABBA remains slower, retain default OFF and investigate measured
scalar/vector work rather than assuming fewer loads guarantee lower latency.
