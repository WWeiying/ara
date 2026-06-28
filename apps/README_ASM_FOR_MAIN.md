# Tightly-coupled `*_asm` kernels — for main-branch (traditional Ara) testing

These 15 `*_asm/` kernels are the **tightly-coupled counterparts** of the HDV
`*_hdv/` kernels: identical vector instruction stream, but with the HDV
packetization stripped (no `HDV_HINT` packet headers, `.hdv_task` → `.text`
naked function). The scalar core issues vector ops directly to Ara — no
decoupled front-end, no software prefetch hints.

## Decoupling from hdv (already done)

* These dirs are **NOT in version control** — `.gitignore` has `apps/*`, and they
  were never `git add -f`'d, so they are ignored on the hdv branch.
* `apps/Makefile` is **unmodified** (no hdv coupling). Variant/AVL selection uses
  the stock `ENV_DEFINES=` mechanism — no Makefile edit required.
* `git checkout main` keeps these dirs (git never touches ignored files). To
  *commit* them on main: `git add -f apps/<k>_asm`.

## Compile-time knobs (pass via `ENV_DEFINES=`, NOT `DEFINES=`)

> Use **`ENV_DEFINES=`**. A command-line `DEFINES=` OVERRIDES the makefile var and
> silently drops `-DNR_LANES`/`-DVLEN`, corrupting any rebuilt runtime/data object.
> `ENV_DEFINES=` appends and preserves them (this is what `scripts/benchmark.sh` does).

| group | kernels | knobs |
|---|---|---|
| 1D streaming | vsaxpy vscopy vsswap vsdot vsscal vvaddint32 vmc vsdwt | `ASM_AVL=<n>` (≤4096) |
| BLAS-2/3 | vssymv vsgemv vssyrk vstrsm | m1: `BLAS_LMUL=1` (fixed 32×32) · m4: `BLAS_LMUL=4 ASM_AVL=<N≤128>` |
| rank-1 | vsger | `ASM_AVL=<n>` (default 128) |
| GEMM | vsgemm | m1: `GEMM_LMUL=1 GEMM_ROWS=<1\|2\|4>` · m4: `GEMM_LMUL=4 GEMM_ROWS=<1\|2\|4> ASM_AVL=<n>` |
| sparse | vsspmv | fixed 32×32 (`ASM_AVL` is a no-op) |

`ASM_AVL` (uniform AVL knob) and the variant defines reach the compiler in BOTH
the real and the spike build, so the ideal vtrace matches the swept size.
`make` can't see `-D` changes → delete stale objects before each new size
(the sweep script does this; manually: `rm <k>_asm/main.c.o <k>_asm/main.c.o.spike
bin/<k>_asm bin/<k>_asm.spike bin/<k>_asm.ideal ideal_dispatcher/vtrace/<k>_asm.vtrace`).

## Performance window + HW counters — already wired

Each asm `main()` now wraps the kernel with two markers each:
* `perf_time()` immediately **before and after** the kernel — the real Ara TB
  latches start counters on the 1st toggle and end counters (+ emits
  `perf_report_<app>.log`) on the 2nd. Without both, no perf report is produced.
* `HW_CNT_READY;` before / `HW_CNT_NOT_READY;` after — enables the SoC hardware
  counters so `[hw-cycles]` / `[cva6-d$-stalls]` / `[cva6-i$-stalls]` /
  `[cva6-sb-full]` actually count (they are gated by `hw_cnt_en`; no stock kernel
  sets it, so they would otherwise read 0). Verified: `[cva6-sb-full]` goes
  non-zero once enabled (e.g. vsaxpy@4096 → sb-full=1; dispatch-bound kernels far higher).

Both `perf_time()` and `HW_CNT_*` are `#ifndef SPIKE`/self-guarded, so they never
enter the ideal vtrace.

## The two performance modes

| | real / non-ideal (default) | ideal (`ideal_dispatcher=1`) |
|---|---|---|
| dispatcher | real cva6 issues to Ara | perfect dispatcher feeds Ara from a spike vtrace |
| report file | `hardware/sim/perf_report_<app>.log` | `hardware/sim/perf_report_<app>_ideal.log` |
| primary cycles | `total_cycles` (real wall time) | `total_rvv_cycles` (Ara-busy peak) |
| **non-ideal-only extras** | `IPC`, `total_vector_insns`, AXI counts, and (stdout) `[hw-cycles]`, `[cva6-d$-stalls]`, `[cva6-i$-stalls]`, **`[cva6-sb-full]`** (scalar-dispatch back-pressure) | — (no real scalar core) |

`ideal total_rvv_cycles` vs `real total_cycles` → the cost the ideal dispatcher hides.

## Batch sweep → CSV

`hardware/asm_sweep.sh` runs every (kernel, AVL, LMUL) point in both modes and
writes one merged CSV row each. It is **two-phase**:

* **REAL phase** — the non-ideal RTL is identical across all points, so it is
  **compiled ONCE** and every point just rebuilds its app binary and re-runs
  `simv` (seconds/point).
* **IDEAL phase** — each point bakes its own vtrace into the RTL, so it
  **recompiles per point** (minutes each) — unavoidable; `MODES=real` skips it.

```
cd hardware
./asm_sweep.sh 1d              # 1D ASM_AVL sweep (32..4096)
./asm_sweep.sh blas            # BLAS-2/3: m1 + m2 + m4 + m8  (matches hdv's LMUL set)
./asm_sweep.sh gemm            # GEMM m1/m4 × rows{1,2,4}
./asm_sweep.sh fixed           # vsspmv
./asm_sweep.sh all             # everything (long!)

MODES=real  ./asm_sweep.sh blas    # only the fast real phase (1 RTL compile total)
MODES=ideal ./asm_sweep.sh blas    # only ideal
AVLS_1D="64 256 1024 4096" ./asm_sweep.sh 1d   # custom AVL list
BLAS_LMULS="4" KERNELS_BLAS="vssymv" ./asm_sweep.sh blas   # restrict LMUL/kernels
GEMM_ROWS_L="4" ./asm_sweep.sh gemm
```

Output: `hardware/asm_sweep_out/asm_sweep.csv` (columns: kernel, tag, avl,
blas_lmul, gemm_rows, ideal_rvv_cycles, ideal_lane_util, real_total_cycles,
real_rvv_cycles, real_vector_insns, real_insns, real_ipc, hw_cycles,
dcache_stalls, icache_stalls, sb_full, axi_*). CSV is **appended** — runs
accumulate; per-point logs in the same dir.

Knobs (env): `MODES`, `AVLS_1D`, `AVLS_BLAS`, `BLAS_LMULS` (default `2 4 8`; m1
always added), `GEMM_ROWS_L`, `KERNELS_1D`, `KERNELS_BLAS`.

> Runtime: only the IDEAL phase recompiles per point. A pure `MODES=real` sweep
> compiles the RTL once and is dramatically faster. Note hdv's own BLAS sweep was
> uneven (vssymv/vsgemv: m1/2/4/8; vstrsm: m1/2/4; vssyrk: m1 only — higher LMUL
> didn't run there); the asm kernels build all of {1,2,4,8}, so this script
> exercises points hdv never did.

## data.S

Each dir ships a static `data.S` sized for the max AVL (1D = 4096/array,
BLAS = 16384/array), so any AVL in range reads valid backing data.
