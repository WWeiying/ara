# Production Repack TU CSR Gate

This successor does not include `q8_0-m4.h` in its test translation unit.
It declares and calls the existing production
`ggml_quantize_mat_t<1, GGML_TYPE_Q8_0>` specialization. The comparison oracle
is the unchanged generic quantizer in the same production `repack.cpp` TU.
No algorithm is copied into the test.

The private GGML build retains production optimization/FP flags. Only the
test TU uses scalar, strict-FP test flags. `build.py` checks undefined test
symbols, strong production definitions, direct-call relocations, archive
ownership, dependencies, and the link map. It pins sources, flags, tools,
libraries, objects, executables, and initramfs before execution. It never
launches a simulator or changes external GGML sources.

Each guest executes four fresh processes: prepare OFF/ON, each with trace
OFF/ON. Each process checks 76 datasets with five rounding modes and three
sticky-flag seeds: 1,140 calls. Each call checks all output bytes, prefix and
suffix canaries, unchanged input, FCSR, and VCSR against the production oracle.
The first production call is not warmed up, so lazy opt-in initialization is
inside the first CSR comparison. Trace-disabled calls cover normal dispatch;
traced companions prove exact RVV/fallback selection and also check trace
side effects. No forced-AVL template instance exists here: VLEN128/1024 runs
exercise the actual production instance.

`check.py` requires exact labels and field sets, complete case order, exact
trace cardinality, the independent dataset eligibility list, and identical
per-call bytes/CSR digests across the four processes. Malformed suffixes such
as `M4_TU_CSR_PASS_BOGUS` are errors. At each VLEN the expected total is 4,560
checks, with 198 RVV and 2,082 generic trace records. A pair of VLEN128/1024
boots supplies 9,120 production-call comparisons, not a performance result.

From the signoff worktree:

```sh
python3 -m unittest discover -s verification/qbs/ggml_m4_prepare_production_csr -p test_check.py -v
python3 verification/qbs/ggml_m4_prepare_production_csr/build.py --output verification/out/qbs-m4-production-csr-build-20261023-01 --jobs 8
```

After review, a bounded worker can boot the generated `initramfs.cpio` with
the existing QEMU image, `-smp 1`, and separately `vlen=128` and `vlen=1024`.
Verify the manifest before and after each boot, then run:

```sh
python3 verification/qbs/ggml_m4_prepare_production_csr/check.py SERIAL_LOG
```

The current non-Zvfh production build is the target; this does not certify a
different compiler/libm, fast-math production, or the unchanged Zvfh route.
Default opt-in stays OFF. Canonical-helper RTL ABBA is parent-owned; Q8_K
fused preparation is separate remaining work.
