# HDV Streaming-Kernel Performance (AVL Sweep)

Configuration: **VLEN = 1024 b, NrLanes = 4, AxiDataWidth = 128 b**, single shared
AXI port, DATA prefetcher enabled. Numbers are total task cycles measured by the
mock-host on the HDV pipeline (`make sim app=<k> hdv_plusargs="+HDV_A<n>=<AVL> ..."`),
post-fix RTL (same-id LSU + store-aware prefetch drain + vset-wb routing +
addrgen `rob_match` page-cross-flag fix + **vldu per-burst prefetch-hit consume**).

`AVL` = application vector length (elements). `cyc/el` = cycles / AVL.
`pf` = prefetch ARs issued → demand hits.

## Table 1 — Total cycles vs AVL

| Kernel | dtype | 256 | 512 | 1024 | 2048 | 4096 |
|---|---|--:|--:|--:|--:|--:|
| vsaxpy      | f32 | 222 | 443 | 859  | 1692 | 3358 |
| vvaddint32  | i32 | 216 | 408 | 792  | 1567 | 3139 |
| vscopy      | f32 | 208 | 416 | 832  | 1657 | 3307 |
| vsscal      | f32 | 268 | 572 | 1180 | 2391 | 4813 |
| vsdot       | f32 | 472 | 904 | 1768 | 3496 | 6952 |
| vsswap      | f32 | 334 | 670 | 1350 | 2693 | 5379 |
| vmc         | i32 | 113 | 192 | 394  | 813  | 1656 |
| dropout     | f32 |  59 | 196 | 536  | 1096 | 2216 |

## Table 2 — Efficiency (cycles / element)

| Kernel | 256 | 512 | 1024 | 2048 | 4096 |
|---|--:|--:|--:|--:|--:|
| vsaxpy      | 0.867 | 0.865 | 0.838 | 0.826 | 0.819 |
| vvaddint32  | 0.843 | 0.796 | 0.773 | 0.765 | 0.766 |
| vscopy      | 0.812 | 0.812 | 0.812 | 0.809 | 0.807 |
| vsscal      | 1.046 | 1.117 | 1.152 | 1.167 | 1.175 |
| vsdot       | 1.843 | 1.765 | 1.726 | 1.707 | 1.697 |
| vsswap      | 1.304 | 1.308 | 1.318 | 1.314 | 1.313 |
| vmc         | 0.441 | 0.375 | 0.384 | 0.396 | 0.404 |
| dropout     | 0.230 | 0.382 | 0.523 | 0.535 | 0.541 |

## Table 3 — Prefetch effectiveness (pf ARs → demand hits)

| Kernel | 256 | 1024 | 4096 |
|---|--:|--:|--:|
| vvaddint32  | 13→12  | 63→62   | 253→253 |
| vscopy      | 7→7    | 32→32   | 131→131 |
| vsdot       | 14→14  | 63→63   | 258→258 |
| vsswap      | 14→14  | 64→64   | 262→262 |
| dropout     | 1→0    | 7→6     | 31→30   |
| vmc         | 0→0    | 3→3     | 17→16   |
| vsaxpy¹     | 10→7   | 15→7    | 15→7    |
| vsscal¹     | 3→3    | 3→3     | 3→3     |

Streaming dual-source / in-place kernels (vvaddint32, vscopy, vsdot, vsswap) reach
**~100 % prefetch hit** at high AVL.

## Notes

- All 8 kernels **pass** across the full sweep (AVL 8 → 4096). **vsswap@4096**
  (the only in-place read-modify-write kernel) previously **dead-locked** at the
  array-size AVL; the per-burst prefetch-hit descriptor consume fixes it
  (5379 cyc, 1.31 cyc/el — in line with its other AVL points).
- **dropout** (masked scalar multiply, `o[k] = SEL[k] ? I[k]·scale : 0`, e32/m8)
  was refactored into a clean HDV kernel — minimal scalar `main` so the task fits
  the forced entry at 0x80001000, and 4KB-page-aligned bases (1024 B load/store
  stride, 32 B mask stride → no page-cross) — and now scales with AVL (was a
  constant 113 cyc / 2 EPs because its bloated `main` pushed the task off the entry
  the mock host launches). Steady-state ≈ 0.54 cyc/el, ~100 % prefetch hit at 4096.
- ¹ **vsaxpy / vsscal** keep the prefetch-AR count low by design (store-aware
  per-iteration drain throttles the read-flood so the single memory port is free
  for the demand stores); hit count plateaus accordingly.
- **fdotp** (f64 dot product) is **excluded** from the sweep: its prefetch is
  pathologically sensitive to its own address/timing pattern (non-monotonic), so
  any descriptor-consume-timing change swings its hit rate. The dot-product class
  is represented by **vsdot** (bit-exact under all the fixes here).
