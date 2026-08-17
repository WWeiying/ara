# Ara Verification Environment

This directory contains the staged functional verification environment for the
CVA6 plus Ara system. Functional correctness and performance regression are
kept separate: a functional test passes only when its self-checking software and
simulation checks pass.

## Stage 1: Reproducible regression

The current stage provides:

- automatic discovery of Ara applications and the existing `rv64uv` tests;
- manifest-defined suites in `suites.json`;
- one VCS compile per hardware configuration;
- isolated output directories for every test;
- deterministic run metadata and exact commands for replay;
- lock-file validation for RTL dependencies, the RVV 1.0 riscv-dv generator,
  and deterministic VCS seeds;
- timeout handling and JSON, CSV, and JUnit reports;
- environment and configuration checks, including every locked dependency and
  the required Bender version.

Run the environment check and inspect the suites:

```bash
python3 verification/verify.py deps
python3 verification/verify.py doctor
python3 verification/verify.py list --suites
python3 verification/verify.py list --suite smoke
```

Run the verification framework's own unit tests from the repository root with
the package directory on `PYTHONPATH`:

```bash
PYTHONPATH=verification python3 -m unittest discover -s verification/tests
```

Running `unittest discover` without this `PYTHONPATH` only produces import
errors for `ara_verify`; it does not exercise the framework.

`deps` reads exact Git revisions from `Bender.lock` and
`toolchain.lock.json`. The riscv-dv checkout is fixed to the RVV 1.0 update at
`a9e723ba921aee0cd2aea7999d92859f2a2f088e` and is stored below the ignored
`verification/tools/` directory. The command refuses to modify dirty checkouts
and can be previewed with `--dry-run`.

Run a smoke regression:

```bash
python3 verification/verify.py run smoke
```

Record scalar retirement plus CVXIF request/response events for later tandem
comparison:

```bash
python3 verification/verify.py run --test app:vsaxpy --commit-trace
```

Run selected points or all directed RVV tests:

```bash
python3 verification/verify.py run --test app:vsaxpy --test rvv:vadd
python3 verification/verify.py run rvv-directed --jobs 4
```

Tests use the manifest timeout by default. For an intentionally large directed
binary, override it for only the current invocation, for example
`python3 verification/verify.py run --test rvv:vlsseg --timeout 900`.

Generate a deterministic RVV 1.0 random assembly smoke program with the
locked riscv-dv implementation:

```bash
python3 verification/verify.py generate-rvv --test ara_dsa_rvv1_smoke --seed 1
```

The local test list also defines a ten-seed strict-checkpoint profile and
ten-seed arithmetic, load/store, integer, FP32, FP64, vector-configuration
churn, slide-index memory, and mixed-control profiles, plus a 50-seed nightly
profile. Omitting `--iterations` uses the profile's YAML iteration count and
`--seed` becomes the first seed; passing `--iterations` explicitly overrides
that count. Every generation writes
`stimulus_coverage.json`, which reports the instruction families, exact
mnemonics, SEW/LMUL/policies, masks, and memory modes actually present in the
generated assembly. Generation is only a stimulus-construction step; it
does not count as an Ara correctness pass until the resulting program has been
compiled, executed on Spike, executed on RTL, and compared architecturally.

Run that complete pipeline with an existing VCS executable:

```bash
python3 verification/verify.py run-rvv \
  --test ara_dsa_rvv1_smoke --seed 1 \
  --simv verification/out/stage2-repro-build/_build/vcs/simv
```

Use the short strict-state diagnostic before longer random regressions:

```bash
python3 verification/verify.py run-rvv \
  --test ara_dsa_rvv1_signature_smoke --seed 1 --vector-signature \
  --simv verification/out/stage2-repro-build/_build/vcs/simv
```

To localize the first vector-state divergence, replace `--vector-signature`
with `--vector-checkpoints`. This inserts a full 32-register snapshot at the
entry to the generated `main` stream, after every generated vector instruction
(including `vset*`), and at exit. The short signature profile initializes the VRF with deterministic
scalar-immediate/slide sequences so an initialization-load failure cannot be
misattributed to the first random instruction. A vector-CSR read after each
whole-register store uses Ara's existing wait-for-idle path to establish
completion without relying on overlapping diagnostic stores. The insertion
preserves its temporary GPRs on riscv-dv's generated user stack, but the extra
whole-register stores, completion barriers, fence, and scalar reads serialize
the stream.
After each vector store, the rewriter also performs byte-exact scalar reads of
every riscv-dv `.region_N` data section. Other vector checkpoints do not add
these memory reads. This makes store targets observable immediately after the
responsible instruction, rather than only through a later load or final
signature. Checkpoint mode is therefore a functional
diagnostic only; it must not be used to assess performance, overlap,
backpressure, or concurrency.

Run the formal ten-seed strict-checkpoint regression with:

```bash
python3 verification/verify.py run-rvv \
  --test ara_dsa_rvv1_checkpoint_regression --seed 1 \
  --vector-checkpoints \
  --spike /home/wangwy/openproject/riscv-isa-sim/build/spike \
  --simv verification/out/stage2-repro-build/_build/vcs/simv
```

The command preserves the generated assembly and ELF, Spike commit log, Ara
commit trace, exact replay commands, trace validation, prefix comparison, and a
machine-readable result for every seed. `COMMIT_WATCHDOG` terminates an RTL
test that continues clocking without architectural or backend-uop progress. A
stalled result identifies the remaining `vid`, architectural request tag, and
instruction encoding. The runner also resolves the ELF's `tohost` symbol and
passes it as `COMMIT_TOHOST`, so riscv-dv programs terminate when their pass or
fail value is architecturally stored instead of spinning forever.
Strict vector-signature programs intentionally finish through a trapped `ecall`
after reading the complete signature. The rewriter labels that exact instruction
and the runner passes its address as `COMMIT_EXIT_PC`; the monitor accepts only a
trapped `ecall` at that configured PC. Existing rewritten ELF files without the
new label are supported by locating the first nearby `ecall` with the repository's
LLVM objdump. Default tests continue to use only the `tohost` contract.

The current tandem comparison is strict for instruction PC/encoding, the exact
scalar GPR write set and value of every instruction, and the reconstructed
scalar-register state of the matched prefix. This includes scalar results
produced by vector instructions. Spike's vector destination values are parsed
and retained. Add `--vector-signature` to force deterministic `tu,mu` policy,
store all 32 vector registers at test exit, and compare all 4096 vector-state
bytes through 512 exact scalar load results on both Spike and Ara. For
register-form `vsetvl`, strict mode scans the preceding straight-line block for
the reaching `li` definition of the `vtype` operand and rejects an intervening
write or control transfer. If policy bits must change, it substitutes the
deterministic value only around `vsetvl` and restores the original scalar
constant afterward. Ambiguous runtime dataflow remains an error.
Default random tests remain unmodified and report `vector_state_compared:
false`.

If RTL has already printed `Core Test *** SUCCESS ***` and produced the commit
traces, but the runner was interrupted during comparison, rebuild the strict
results without rerunning VCS:

```bash
python3 verification/verify.py postprocess-rvv \
  --output verification/out/<existing-run>
```

The command recovers the ELF and seed from `rtl.command.json`, validates the
existing architecture trace, reruns scalar prefix and accepted-VRF comparisons,
and regenerates each missing `result.json` plus the run-level `summary.json`.
It does not invoke Spike or `simv`. Use `--case <artifact-name>` to restrict the
operation and `--force` only when an existing result must be recomputed.

Focused architectural matrices can be built and run as one suite:

```bash
python3 verification/verify.py run rvv-corners --jobs 4
```

`vaverage_matrix` covers all four averaging operations, all four `vxrm`
values, and SEW 8/16/32/64. `vmask_logical_matrix` covers all eight mask
logical operations under varied VL, LMUL, nonzero `vstart`, and policy
encodings. `vmask_compare_edges` checks integer and floating comparison masks
plus mask-scan results with an unaligned mask destination and byte-exact guard
registers. `vfp_vstart_edges` checks masked FP32/FP64 arithmetic at unaligned
nonzero `vstart` values, including preservation of prestart and masked-off
destination elements. `vdiv_vstart_edges` checks masked and unmasked integer
divide/remainder restart across SEW 8/16/32/64, including request-bound write
byte-enables. `vrepair_edges` targets widening, narrowing saturation/rounding,
EEW reshuffling, and reduction register-group boundaries.
`vwiden_overlap_edges` exercises the legal case where a narrow widening source
overlaps the high-numbered half of the wider destination register group,
including a zero-VL widening accumulator that must make forward progress
without modifying the aliased group. It also covers a `.wv` operation whose
destination is its complete wide source while the narrow source aliases the
wide group's high half, requiring both source layouts to remain readable.
`vslide_mask_edges` covers masked slide-up offsets both within and beyond one
mask transport word; `vrgather_edges` covers scalar indices beyond VLMAX and
an overlapping `vrgatherei16` data/index pair that needs simultaneous e64 and
e16 views of one raw register group.
`vnclip_edges` covers narrowing overlap, masked `vd==vs1==vs2`, nonzero
`vstart`, lane-word byte shuffling, masked/prestart old-destination
preservation, and the rule that only actually executed elements may set
`vxsat`.
`vstore_signature` scalar-checks unit-stride, strided, indexed, and segmented
store targets immediately after each vector store.

Reuse an already compiled simulator while still rebuilding test binaries:

```bash
python3 verification/verify.py run smoke --simv hardware/sim/simv
```

Use `--skip-build` only when both the simulator and selected ELF files already
exist. Each run is written below `verification/out/`; the directory contains
`run.json`, build logs, per-test artifacts, `summary.json`, `summary.csv`, and
`junit.xml`. `run.json` is `RUNNING` until all selected tests have produced
reports, then becomes `COMPLETE`; a dry run is marked `DRY_RUN`. Starting a
new invocation in the same output directory invalidates stale summary/CSV/JUnit
reports but preserves case logs, so an old dry-run summary cannot be mistaken
for live results.

Run the complete directed, application, and 12-profile random campaign with an
explicit Ara-compatible Spike executable:

```bash
python3 verification/run_full_campaign.py \
  --simv verification/out/<final-build>/_build/vcs/simv \
  --spike /path/to/ara-compatible-spike \
  --output verification/out/<full-campaign> \
  --jobs 8 --random-jobs 4 --timeout 900
```

`--spike` is mandatory for the complete campaign. Random profiles that enable
nonzero `vstart` require a Spike build configured
to execute restartable vector ALU instructions from nonzero `vstart`.  The
reference model must still trap for the RVV operations that architecturally
require `vstart=0`, including reductions, mask scans, `vcpop`, `vfirst`,
`viota`, and `vcompress`.  Pass that executable explicitly with `--spike` so a
campaign does not silently depend on a host-local default Spike configuration.

The validated reference build uses riscv-isa-sim commit `488e07d7` plus
`verification/patches/riscv-isa-sim-ara.patch`:

```bash
git -C /path/to/riscv-isa-sim checkout 488e07d7
git -C /path/to/riscv-isa-sim apply \
  "$PWD/verification/patches/riscv-isa-sim-ara.patch"
mkdir -p /path/to/riscv-isa-sim/build
cd /path/to/riscv-isa-sim/build
../configure --prefix="$PWD/install"
make -j8 spike
```

The current inventory is 207 directed RVV tests, 50 applications, and 142
generated random programs. In addition to the minimum count gates, the campaign
requires all 32 `rvv-corners` tests by name and requires all 12 random profiles
at their configured minimum seed counts. After generation it merges the 12
`stimulus_coverage.json` files and checks that every expected source exists and
that all required instruction families, memory modes, SEW/LMUL values,
tail/mask policies, and masked instructions actually occur. Coverage is
collected from generated `main/sub_*` code before diagnostic rewriting; missing
semantic coverage makes the campaign fail. Random profiles retain a complete exit
signature and also enable non-intrusive per-vector-instruction commit
comparison; checkpoint profiles additionally compare full vector state after
each generated RVV instruction. `campaign_summary.json` reports collection
completeness as `status` and functional success as `verdict`. The command exits
successfully only when every expected, uniquely identified result is present,
all component commands return zero, every result status is `PASS`, and the
managed RTL, application, and verification source snapshot is unchanged from
campaign start to completion.

The default `smoke` suite remains a deliberately small integration gate;
architectural coverage belongs to `rvv-directed` and `rvv-corners`.
`rvv:vsetivli` now explicitly checks the `e32,mf2,AVL=20,VLMAX=16` boundary,
including agreement between its destination GPR and the `vl` CSR. It therefore
detects an implementation that copies the immediate AVL without applying the
RVV VLMAX constraint.

## Stage 2: Commit event trace

Builds produced by this runner include a verification-only CVA6 RVFI adapter
and Ara monitor. `--commit-trace` writes `commit_trace.csv` beside each test
log. `retire` rows are scalar architectural retirement events; `arch_start`,
`cvx_req`, and `cvx_resp` describe the accelerator interface; `uop_alloc` and
`uop_done` describe the sequencer lifecycle. Reshuffle and segment-memory uops
retain the architectural request tag that created them. A CVXIF response is
not treated as generic vector architectural completion.

## Stage 3: Non-intrusive vector commit comparison

`--vector-commit-compare` records each ALU, MFPU, MASKU, SLDU, and VLDU result
only after it wins VRF arbitration. The monitor retains the backend `vid` to
architectural-request mapping across reshuffle and segment uops. The offline
comparator groups all writes by architectural request, reverses Ara's lane
shuffle using the destination EEW, maps the request to its RVFI PC and Spike
commit, and compares every known byte accepted by the VRF. No instruction or
memory access is inserted into the test program.

Use `--vector-commit-index` to check one one-based dynamic vector-destination
request while bringing up the path:

```bash
python3 verification/verify.py run-rvv \
  --test ara_dsa_rvv1_signature_smoke --iterations 1 --seed 1 \
  --vector-commit-compare --vector-commit-index 513 \
  --spike /home/wangwy/openproject/riscv-isa-sim/build/spike \
  --simv verification/out/vector-commit-build_20260808/_build/vcs/simv
```

The case directory contains `ara_vector_trace.csv` and
`vector_commit_comparison.json`. A mismatch identifies the dynamic request,
PC, instruction, vector register byte, lane, writeback source, `vid`, VRF
address, and EEW. Unknown simulation bytes are never converted into values;
they are counted separately and make a selected request unobservable if no
known byte remains. The current path strictly checks accepted write values and
detects a wholly missing destination write. Complete active-byte coverage and
vector-store memory effects remain separate checks.

The comparator also propagates architecturally agnostic vector bits. If
`vmv.x.s`, `vfmv.f.s`, `vcpop.m`, or `vfirst.m` has an unknown relevant source
bit that can change its scalar result, that result is not bit-exact across
implementations and may change later control flow. In that case scalar
retirement and vector writebacks remain strictly checked through the first such
result, then both comparisons end with an explicit `PREFIX` status. A case
accepts this boundary only when both sides agree on the prefix, the RTL program
exits successfully, and the complete RTL request/uop trace is valid; a scalar
`MATCH` never accepts a vector `PREFIX`.

## Planned stage

Stage 4 adds vector architectural coverage, randomized memory backpressure,
protocol assertions, and Sail cross-checking.
