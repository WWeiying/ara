# Exact completion performance probes

These maintained sources restore the ignored `apps/` working copies. They do not
modify production RTL or invoke synthesis. Use existing frozen SoC simulators.
The normal-overlap app is a separate directed protocol workload; its original
source is archived unchanged.

From the repository root, use the repository's installed LLVM toolchain and
four-lane, VLEN=1024 default configuration:

```bash
export LLVM_INSTALL_DIR="$PWD/install/riscv-llvm"
export GCC_INSTALL_DIR="$PWD/install/riscv-gcc"
python3 hardware/tb/reduction_probes/run_probes.py build --app perf_exact_seed_fallback_latency
python3 hardware/tb/reduction_probes/run_probes.py run --app perf_exact_seed_fallback_latency \
  --baseline hardware/build/exact_direct_read_soc_v2/baseline/simv \
  --candidate hardware/build/production_tail_integrated_soc_20261017_v1/production/simv \
  --out hardware/build/exact_seed_fallback_compare_NEW
```

Build installs the archived `main.c` into `apps/<app>/`, generates `oracle.h` for
the fallback probe with the archived integer-only Python oracle, then executes
`make -C apps bin/<app>`. Direct oracle reproduction is:

```bash
python3 hardware/tb/reduction_probes/gen_exact_seed_fallback_oracle.py \
  --out apps/perf_exact_seed_fallback_latency/oracle.h
```

Run freezes one ELF, sources, exact commands, and simulator/ELF hashes in a new
directory. It invokes `run_reduction_audit.py` separately for baseline and
integrated, each with `--jobs 1 --timeout 1800` and only the selected app. Pass
`--profile` only when both simulators support the desired observer. Never replace
an old evidence directory. The helper also supports the archived
`perf_exact_dense_seed_latency` and `perf_packet_normal_overlap` apps.

The fallback probe has eight windows: four source/seed combinations, each with
ordinary and chained seeds. Each window sums eight isolated reduction latencies;
`vadd.vi` source refresh, flags reset, and the `vstart` setup barrier precede the
first `rdcycle`. Each measured interval is `rdcycle`, reduction, scalar readback,
`rdcycle`. The oracle decodes binary32 into integer multiples of 2^-149 and
implements ties-to-even rounding using integer quotient/remainder. Every result
and per-instruction fflags is checked, including later chain iterations.

Scenarios are all-zero sources with seed 3; per-lane +1/-1 cancellation with
seed 3; 32 minimum subnormals with seed 1; and 32 ones with a minimum-subnormal
seed. Source EW32 lane placement follows `ara_pkg::shuffle_index`: lane=index%4.
All cases use VL32. Summed cycles include identical scalar-readback overhead and
must be compared only between matching windows and identical ELFs.

Original measured build command: `make -C apps bin/perf_exact_seed_fallback_latency`.
Original frozen ELF SHA256:
`66551679d4c455422ee1d7b0953752bdf14da0a05a5a99b4c8822539855b0b8e`.
Original paired runs used the two simulator paths above, ELF directory
`hardware/build/exact_seed_fallback_compare_20261017_v1/elfs`, output suffixes
`baseline` and `integrated`, and the same audit arguments emitted by the helper.

Strict collection for an already completed fallback pair (does not rerun):

```bash
python3 hardware/tb/reduction_probes/collect_fallback_results.py \
  hardware/build/exact_seed_fallback_compare_20261017_v1 \
  --out hardware/build/exact_seed_fallback_compare_20261017_v1/comparison_NEW.json
```

The run helper invokes this collector after successful fallback runs. It requires
all eight windows, independent integer-oracle final results/flags, identical ELF
hashes, successful tohost, and completed simulator manifests; it preserves log
and simulator hashes and reports cycle deltas without changing expectations.
