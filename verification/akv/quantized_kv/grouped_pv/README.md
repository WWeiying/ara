# Grouped PV leaf candidate

Standalone, opt-in-by-caller prototype only. No SDK, GGML, online scheduler,
ISA or production defaults are changed. See parent-owned `INTEGRATION.md` for
the subsequent integration gates. The independent leaf has now executed under
QEMU at VLEN256 and VLEN1024; no VCS performance or full-Attention acceptance is
claimed. See `verification/akv/results/grouped-pv-reference-20261026.json`.

## API and numerical contract

`akv_grouped_pv_update(heads, dim, stride, output, value, ms, vs, rescale_mask)`
returns `AKV_GROUPED_PV_OK` (0) or `AKV_GROUPED_PV_BAD_ARGUMENT` (1).

- Heads: 1..8; dimension: every integer 32..256, including vector tails.
- `stride` is in **float elements**, at least `dim`. Caller supplies accessible
  output span `(heads-1)*stride+dim`, V span `dim`, and coefficient spans `heads`.
- Four-byte alignment, span overflow, mask bits and output/input nonoverlap
  are checked before any FP operation or write. Output padding is included in
  the conservative overlap check. Read-only inputs may overlap each other.
  These checks cannot establish actual allocation capacity or mapping validity.
- Set mask bit h means `Y[h,d] = round32(Y[h,d] * ms[h])`, followed by
  `Y[h,d] = fma(V[d], vs[h], Y[h,d])`. Without that bit there is **no scale**,
  even by one. A zero MAD coefficient never suppresses the FMA.
- Do not derive the mask from `ms != 1`. It represents the original maximum
  update branch. The caller computes all coefficients before entering this leaf.
- Compile with strict FP semantics, `-ffp-contract=off`, no fast-math. The scalar
  fallback uses a volatile binary32 temporary for separate scale rounding and
  explicit `fmaf`; the RVV version uses separate `vfmul.vf` then `vfmacc.vf`.
  V remains read-only; Y is the FMA accumulator. e32m4 uses one V and one Y group,
  not eight simultaneously live head vectors. VLA advances by returned VL.
- Caller establishes RNE, gradual underflow and masked FP traps. No FRM or
  VCSR writes occur in the leaf; sticky FP exceptions accumulate normally.
  RVV VL/vtype and caller-saved vector registers are clobbered. No claims about
  NaN payload selection across different machines; inactive ms is not evaluated.
- Within each head the operation order is unchanged; independent heads and
  dimensions are interleaved. Intermediate exception observations, arbitrary
  scale/MAD callback side effects, aliasing, signal/trap recovery and concurrent
  buffer mutation are not supported. This leaf is not a drop-in callback ABI.

The scheduler's score/maximum/expf/sum/final-normalization arithmetic is absent,
not replaced. Future integration must preserve it and the original fallback.

## Tests and compile-only inspection

From the repository root:

```sh
python3 -B verification/akv/quantized_kv/grouped_pv/test_kernel.py -v
```

Host GCC O0/O3 each run 13,824 valid cases and 17 invalid no-write/no-FP-change
cases. The independent oracle traverses each complete head's scale pass then
its MAD pass. Tests compare every output byte, padding/guards/inactive rows,
all input bytes, RNE and flags; cover heads 1..8, twelve dimensions including
33/63/127/255, three strides, four branch masks, six numeric patterns and
clean/sticky flags. Patterns include signed zero, subnormals, explicit inexact
underflow/overflow assertions, separate-rounding boundaries and inactive
signaling-NaN scale coefficients. A deliberately unconditional-scale mutant
must fail. Host evidence is scalar semantics, not RVV execution.

The Python suite optionally uses `GROUPED_PV_CC` (default the installed
`riscv64-unknown-elf-gcc`) for `-O3 -march=rv64gcv -mabi=lp64d` object generation
and objdump only. It checks FP32 m4 multiply/FMA/load/store instructions and
absence of vector arithmetic in the scalar oracle. No Zfh is required. A missing
compiler is an explicit skipped compile test, never native PASS. Temporary
build objects are removed after tests.

The **same** C file is directly runnable on RVV Linux, for the parent to execute:

```sh
$RISCV_LINUX_GCC -std=c11 -O3 -Wall -Wextra -Werror \
  -fno-fast-math -ffp-contract=off -frounding-math -fno-tree-vectorize \
  -march=rv64gcv -mabi=lp64d \
  verification/akv/quantized_kv/grouped_pv/test_kernel.c -lm -o test_grouped_pv
```

Do not omit `-fno-tree-vectorize`: the reference must remain scalar; explicit
RVV intrinsics remain enabled. On RVV, each arm snapshots FCSR/VCSR immediately
after arithmetic, checks full equality plus VCSR=5, and restores the caller's
FP environment/VCSR after the suite. PASS says `backend=RVV csr=fcsr_vcsr`;
host says `backend=scalar csr=host_fenv`. RISC-V compile success alone is not
that PASS. The parent `run_reference.py` ran both VLEN256 and VLEN1024 with
the same ELF; each passed all 13824 numerical and 17 rejection cases.
VLEN128 and actual RTL execution have not been tested for this leaf.

## Work and traffic convention

For one token and H heads, D floats, R set rescale bits:

| Logical operand work | Old per-head scale/MAD | Grouped leaf |
| --- | ---: | ---: |
| V read bytes | 4HD | 4D |
| Y read bytes | 4D(H+R) | 4HD |
| Y write bytes | 4D(H+R) | 4HD |
| Binary32 multiply elements | RD | RD |
| Binary32 fused-MAD elements | HD | HD |

These are source-level vector operand bytes, not measured AXI/cache/VRF traffic,
instructions, spills, or cycles. Coefficient loads and admission checks are
excluded. RVV has one V load per VLA chunk, H Y loads/stores/FMAs and R multiplies
per chunk. Actual VL and compiler output determine instruction counts.

H6/D128/T128: V reads 384 -> 64 KiB, saving 320 KiB; each actual head-token
rescale saves another 1 KiB of Y read+write. Base Y traffic remains 768 KiB.
Logical scheduling calls become 128 grouped updates versus 768 MAD callbacks
plus R scale callbacks; six final normalization callbacks remain outside this
leaf. These are API counts, not a claim of retired indirect calls (inlining may
remove them). No counters/global arrays are added to the hot leaf, and no
performance or complete-Attention acceptance is claimed.
