# Carry / Slide restart repair

## Measured root causes

The current pre-repair image reproduced both historical failures in
`verification/out/gap35-root-probes-20261005-01` without a rebuild.
These diagnostic simulations are not verified coverage inputs.

* `vgap35_carry_ta`: 459 checks, three failures. With SEW=8, VL=67,
  vstart=61 and four lanes, AluA/AluB start at register word offset 1,
  whereas MASKU packs three operand beats starting at result bit 0 and
  takes carry-in from mask bit 0. The active destination mask correctly
  selects bits [61,67), but the arithmetic operands are displaced by
  32 elements. VMADC fails at element 61; VMSBC fails at 63 and 66.
* `vgap35_slide_bound`: 535 checks, six failures. The first masked
  VSLIDEDOWN has VL=7, vstart=3, stride=2041. Its allocation is arch_seq=8
  at cycle 2571. At cycle 2581, lane 0 and lane 2 write zero with BE=01,
  overwriting prestart elements 0 and 2. The out-of-range source correctly
  produces zero, but the write enable violates prefix preservation.
  The same failure occurs at strides 4089 and 2048.

## Repair scope

* For VMADC/VMSBC only, request AluA/AluB from element zero. This matches
  the existing full-VL MASKU packing and carry-input indexing. Prefix
  computations have no architectural side effects; MASKU still merges the
  unchanged old destination outside the active interval. Do not reset
  vstart globally for integer comparisons or other ALU requests.
* Extend the existing SLDU prefix byte-enable guard from internal
  zero-stride reshuffles to every nonzero-vstart VSLIDEDOWN. Reductions
  retain their existing enable path. Mask predicates remain an additional
  gate; they do not replace vstart preservation.

Neither repair adds registers, pipeline stages, or beats for the normal
vstart=0 path. This is a structural expectation, not a measured performance
claim or timing signoff.

## Independent acceptance run

`run_gap35_restart_repair.py` builds one source-pinned VCS image and runs
15 tests with five workers, at most 30 minutes per test:

* Two original carry/slide reproducers: full scalar reference self-check,
  exact check count, clean RTL contract and commit-trace validation.
  These are not claimed as full instruction-differential checks.
* Five previously passing QBS/AKV fault/read/lifetime tests with their
  independent runtime audits and performance-counter evidence.
* Eight extension/reduction tests with complete scalar and vector
  differential comparison against the previously frozen Spike traces.

Output: `verification/out/gap35-restart-repair-20261005-01/status.json`.
Each case retains its independent ELF, traces, log, audit and VDB.
Failed tests must not enter coverage. Previous 654-case VDBs are from
older RTL and are not merged with this new image. Passing this bounded
regression does not constitute full signoff.

## QBS result-checker hardening

`apps/llama_qwen25_real/common/qbs_benchmark_impl.h` previously checked only
`absolute > ATOL + RTOL * magnitude`. An actual NaN makes this comparison
false and could be accepted as a correct output. Nonfinite references were
also not rejected explicitly.

The validator now checks the FP32 exponent bits of both actual and reference
before tolerance arithmetic. NaN and either infinity count as mismatches;
maximum absolute and relative errors become positive infinity. The checksum
still includes every actual output, including invalid values. Finite-output
tolerance arithmetic is unchanged. This changes the checker, not the QBS
compute kernel or RTL.

`verification/tests/test_qbs_benchmark_validation.py` compiles the actual
production validator body with a host C compiler rather than duplicating
its logic. Six host tests pass: finite equality, tolerance acceptance and
rejection, nonfinite actual, nonfinite reference, equal infinities, and
checksum inclusion. These tests do not establish accelerator correctness;
previously compiled benchmark ELFs do not contain the new checker and must
be rebuilt before claiming coverage of this check on the processor.
