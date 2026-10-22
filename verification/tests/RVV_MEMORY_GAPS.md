# Bounded RVV Memory Gaps

40 new standalone rv64uv cases, with no Makefrag registration required:

- 36 = NF5/6/7 x data EEW8/16/32/64 x unit/strided/indexed.
- Four extra single-field indexed cases: data SEW8/16/32/64, index EEW64,
  including `vloxei64.v` and `vsoxei64.v`.
- Every case checks loads and stores independently. Indexed cases execute
  both ordered and unordered instructions, each masked and unmasked.

All data groups use m1. Segmented indexed cases have index EEW equal to SEW,
so each field and index group has EMUL=1. Data occupies v8..v14; mask uses v0;
indices use v24..v31 (EMUL up to 8 for the extra ei64 cases). No overlap.

The runtime requests eight elements and uses returned VL, requiring at least
two. Four scenarios are full VL unmasked, VL-1 unmasked, VL-1 masked (0xad),
and VL=0 masked. `tu,mu` preserves prefilled masked-off and tail elements.
Each load field is dumped independently at the original VL. Stores reload
independent seed data and compare the whole scalar destination, including
padding, inactive rows, and both end guards. Indexed addresses are a unique
permutation of eight rows. They are naturally aligned and fit even ei8;
the largest ei8 byte offset is 63. No fault, duplicate-address ordering,
agnostic-value, or unsupported register-overlap semantics are assumed.

Scalar arrays are volatile; asm declares all vector-register clobbers. The
build also disables loop and SLP auto-vectorization. Operations use the
existing rv64uv CSR-read/fence completion convention. Failures print at most
eight diagnostics per ELF but every mismatch contributes to failure status.

## Reproduce

From `/home/wangwy/openproject/ara_dsa_signoff_integration`:

```sh
python3 verification/tests/generate_rvv_memory_gaps.py --check
python3 -m unittest discover -s verification/tests -p test_generate_rvv_memory_gaps.py -v
python3 verification/tests/build_rvv_memory_gaps.py \
  --output verification/out/memory-gap-source-preflight-20260928-all40 --spike
```

The builder uses existing non-ZCC `install/riscv-llvm/bin/clang`. It reads
`apps/common/link.ld` without regenerating it, compiles runtime objects only
inside its output directory, and produces all 40
`apps/bin/rv64uv-ara-vmemory_gap_*` ELFs. It does not invoke make, VCS, or
Verilator. `build_commands.json` records exact compiler/linker commands.
Do not rebuild the ELFs after the parent runner pins them.

For only the first two representatives, add:

```sh
  --case vmemory_gap_nf7_e64_strided --case vmemory_gap_vloxei64_e8
```

`--spike` builds **separate HTIF-runtime ELFs from the same test source** and
runs each with a 30-second timeout. Ara MMIO-runtime ELFs are for the parent
VCS runner, not this stock Spike. Standalone representative invocation:

```sh
timeout 30s install/riscv-isa-sim/bin/spike \
  --isa=rv64gcv_zfh --varch=vlen:1024,elen:64 \
  verification/out/memory-gap-source-preflight-20260928-all40/vmemory_gap_vloxei64_e8.spike
```

`rvv_memory_gap_selection.json` contains `{"tests": ["rvv:stem", ...]}` in
parent-runner order: NF7/e64 strided first, ei64/e8 second. These discriminate
padded segment addressing and maximal legal index EMUL. Parent should run
these two serially and gate the remaining eight-worker expansion on success.
No VCS runtime bound or RTL correctness is claimed from Spike preflight.

## Local Results

All 40 Ara builds and all 40 Spike HTIF runs passed on 2026-09-28 at VLEN=1024.
Evidence is in `verification/out/memory-gap-source-preflight-20260928-all40/`:
`spike_results.json`, per-case `.spike.log`, and `build_commands.json`.
The first setup attempts are retained separately: stock Spike rejected
`zvfh`; subsequently HTIF section placement faulted because its legacy linker
script does not collect `.text.*`/`.tbss.*`. The new helper now uses the
supported integer-test ISA and omits section splitting only for HTIF builds.
No existing runtime, linker script, pinned test/tool, checker, or RTL changed.
