# HDV Kernel Sweep 数据

本文档已同步到当前 `hardware/kernel_sweep_out/kernel_all.csv`。

## 1. CSV 一致性检查

- 数据源: `hardware/kernel_sweep_out/kernel_all.csv`
- 形状: 65 列,132 条数据行。
- 行宽检查: 所有数据行都是 65 列。
- 单项 CSV 检查: 每个 `kernel_sweep_out/*.csv` 都和 `kernel_all.csv` 中对应 kernel 的子集一致,
  没有发现单项 CSV 的旧数据混入总表。
- 派生字段检查:
  - 对所有带 AVL 的行,`cyc_per_elem == task_cycles / avl`。
  - 对所有 `pf_ar > 0` 的行,`pf_hit_rate == pf_hit / pf_ar`。
- 当前通过/失败汇总: 131 PASS,1 FAIL。
  - `blas,vssyrk_hdv,size=128,n=128`: FAILED, `task_cycles = 799998`.
- PASS 行结构性检查:
  - 所有 PASS 行均满足 `vq_push == vq_pop`。
  - 所有 PASS 行均满足 `real_wait_stall == 0` 且 `resp_meta_stall == 0`。
  - 所有 PASS 行在采样 DONE 点均满足 `vec_busy == 0`。
  - `imem_outstanding` 不是全 0;PASS 行最大观测值为 4,因此当前不能再写
    "imem_outstanding 全 0" 作为健康性断言。
  - `seq_full` 只有 `jacobi2d_fix` 非零(`seq_full = 4718`)。

当前总表不包含 `fdotp` 和 `vspf`。

## 2. 指标说明

- `task_cycles`: mock-host 报告的任务周期。
- `cyc_per_elem`: `task_cycles / AVL`,仅 AVL sweep 行填写。
- `cyc_per_macc`: BLAS/GEMM 行由脚本按操作量计算的归一化指标。
- `pf_ar->pf_hit`: 发出的预取 AR 数量以及 demand load 命中的已完成预取数量。
- 空单元格表示该指标不适用或对应 log 未输出。
- FAILED 行仅用于调试可见性,不应作为论文性能点。

## 3. AVL Sweep

当前 active AVL sweep 包含 9 个 kernel:
`vsaxpy_hdv`, `vvaddint32_hdv`, `vscopy_hdv`, `vsscal_hdv`, `vsdot_hdv`,
`vsswap_hdv`, `vmc_hdv`, `dropout_hdv`, `vsdwt_hdv`。

### 3.1 任务周期

| Kernel | 256 | 512 | 1024 | 2048 | 4096 |
|---|--:|--:|--:|--:|--:|
| vsaxpy | 195 | 387 | 771 | 1552 | 3114 |
| vvaddint32 | 212 | 403 | 796 | 1578 | 3140 |
| vscopy | 208 | 416 | 832 | 1657 | 3307 |
| vsscal | 250 | 506 | 1018 | 2037 | 4075 |
| vsdot | 472 | 904 | 1768 | 3496 | 6952 |
| vsswap | 335 | 671 | 1351 | 2694 | 5380 |
| vmc | 113 | 192 | 394 | 813 | 1656 |
| dropout | 59 | 196 | 536 | 1096 | 2216 |
| vsdwt | 451 | 875 | 1723 | 3419 | 6811 |

### 3.2 每元素周期

| Kernel | 256 | 512 | 1024 | 2048 | 4096 |
|---|--:|--:|--:|--:|--:|
| vsaxpy | .761 | .755 | .752 | .757 | .760 |
| vvaddint32 | .828 | .787 | .777 | .770 | .766 |
| vscopy | .812 | .812 | .812 | .809 | .807 |
| vsscal | .976 | .988 | .994 | .994 | .994 |
| vsdot | 1.843 | 1.765 | 1.726 | 1.707 | 1.697 |
| vsswap | 1.308 | 1.310 | 1.319 | 1.315 | 1.313 |
| vmc | .441 | .375 | .384 | .396 | .404 |
| dropout | .230 | .382 | .523 | .535 | .541 |
| vsdwt | 1.761 | 1.708 | 1.682 | 1.669 | 1.662 |

### 3.3 预取 AR 与命中

| Kernel | 256 | 1024 | 4096 |
|---|--:|--:|--:|
| vsaxpy | 13->13 | 63->63 | 255->255 |
| vvaddint32 | 14->14 | 64->64 | 260->260 |
| vscopy | 7->7 | 32->32 | 131->131 |
| vsscal | 7->7 | 32->32 | 131->131 |
| vsdot | 14->14 | 63->63 | 258->258 |
| vsswap | 14->14 | 64->64 | 262->262 |
| vmc | 0->0 | 3->3 | 17->17 |
| dropout | 1->0 | 7->6 | 31->30 |
| vsdwt | 7->0 | 31->0 | 127->0 |

当前 CSV 显示:简单单位步长流式 kernel 基本都是满命中;`dropout_hdv` 保持预期的冷启动差
1 次命中;`vsdwt_hdv` 发出预取 AR 但 demand 命中为 0。

## 4. AVL=4096 详细计数器

### 4.1 顶层与派发

| Kernel | task_cycles | cyc/el | eps | ep_ack | ep_vset_ack | vq_push/pop | vq_max | vq_full_stall | dispatch_cycles | operand_wait | ara_backpressure | ipu_ready_stall |
|---|--:|--:|--:|--:|--:|---:|--:|--:|--:|--:|--:|--:|
| vsaxpy | 3114 | .760 | 512 | 384 | 128 | 637/637 | 8 | 45 | 940 | 640 | 2450 | 2 |
| vvaddint32 | 3140 | .766 | 512 | 384 | 128 | 637/637 | 8 | 11 | 906 | 651 | 2477 | 3 |
| vscopy | 3307 | .807 | 384 | 256 | 128 | 382/382 | 5 | 0 | 512 | 384 | 2900 | 3 |
| vsscal | 4075 | .994 | 384 | 384 | 128 | 509/509 | 7 | 0 | 766 | 512 | 3541 | 3120 |
| vsdot | 6952 | 1.697 | 519 | 386 | 129 | 638/638 | 8 | 0 | 898 | 643 | 6281 | 2 |
| vsswap | 5380 | 1.313 | 512 | 384 | 128 | 638/638 | 8 | 1237 | 2259 | 640 | 4720 | 2 |
| vmc | 1656 | .404 | 424 | 80 | 16 | 90/90 | 7 | 0 | 96 | 96 | 1448 | 2 |
| dropout | 2216 | .541 | 149 | 48 | 16 | 94/94 | 8 | 1278 | 1406 | 96 | 2071 | 18 |
| vsdwt | 6811 | 1.662 | 2180 | 768 | 128 | 384/384 | 1 | 0 | 1024 | 896 | 384 | 773 |

### 4.2 访存与预取

| Kernel | demand_ar | pf_ar | pf_hit | loads | hit_rate | demand_aw | demand_B | pf_B |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| vsaxpy | 139 | 255 | 255 | 256 | 1.000 | 132 | 1296 | 30832 |
| vvaddint32 | 213 | 260 | 260 | 256 | 1.000 | 132 | 480 | 31648 |
| vscopy | 132 | 131 | 131 | 128 | 1.000 | 132 | 128 | 15872 |
| vsscal | 132 | 131 | 131 | 128 | 1.000 | 132 | 128 | 15872 |
| vsdot | 260 | 258 | 258 | 256 | 1.000 | 0 | 256 | 32080 |
| vsswap | 256 | 262 | 262 | 256 | 1.000 | 264 | 256 | 31728 |
| vmc | 17 | 17 | 17 | 16 | 1.000 | 20 | 512 | 6992 |
| dropout | 32 | 31 | 30 | 32 | .967 | 16 | 1056 | 15872 |
| vsdwt | 255 | 127 | 0 | 128 | 0 | 260 | 32768 | 16256 |

### 4.3 Sequencer 计数器

| Kernel | seq_blocked | seq_raw | seq_war | seq_waw | seq_ep_bypass | seq_full |
|---|--:|--:|--:|--:|--:|--:|
| vsaxpy | 2071 | 252 | 1 | 1687 | 320 | 0 |
| vvaddint32 | 2097 | 128 | 1793 | 33 | 512 | 0 |
| vscopy | 2647 | 128 | 2391 | 0 | 128 | 0 |
| vsscal | 3288 | 256 | 3033 | 128 | 192 | 0 |
| vsdot | 6027 | 131 | 5785 | 528 | 449 | 0 |
| vsswap | 4210 | 128 | 3698 | 1 | 261 | 0 |
| vmc | 32 | 32 | 2 | 0 | 32 | 0 |
| dropout | 2029 | 17 | 1982 | 64 | 56 | 0 |
| vsdwt | 384 | 384 | 1 | 128 | 384 | 0 |

当前计数器支持的主要结论:

- `vsaxpy_hdv`,`vvaddint32_hdv`,`vsswap_hdv` 主要受访存带宽/写端口压力限制。
- `vsscal_hdv` 主要受计算/依赖限制;预取满命中,但 `ipu_ready_stall = 3120`。
- `vsdot_hdv` 主要受规约依赖限制;`seq_war = 5785` 且 `demand_aw = 0`。
- `vsdwt_hdv` 当前会发出预取 AR,但没有 demand 命中。

## 5. BLAS / GEMM 行

下表直接来自当前 `group=blas` 行。`size`、`rows`、`n` 是 `kernel_sweep_sum.sh` 写入 CSV
的原始字段;对于 `*_m2/m4/m8` 行,`size` 表示 LMUL selector。

| Kernel | size | rows | n | result | task_cycles | cyc/MACC | demand_ar | pf_ar->hit |
|---|--:|--:|--:|---|--:|--:|--:|--:|
| vsgemv_hdv_m2 | 2 | 32 | 32 | PASSED | 111 | .0541 | 2 | 0->0 |
| vsgemv_hdv_m2 | 2 | 64 | 64 | PASSED | 121 | .0295 | 2 | 0->0 |
| vsgemv_hdv_m4 | 4 | 32 | 32 | PASSED | 126 | .0307 | 2 | 0->0 |
| vsgemv_hdv_m4 | 4 | 64 | 64 | PASSED | 136 | .0166 | 2 | 0->0 |
| vsgemv_hdv_m8 | 8 | 32 | 32 | PASSED | 160 | .0195 | 2 | 0->0 |
| vsgemv_hdv_m8 | 8 | 64 | 64 | PASSED | 170 | .0103 | 2 | 0->0 |
| vssymv_hdv_m2 | 2 | 32 | 32 | PASSED | 112 | .0546 | 2 | 0->0 |
| vssymv_hdv_m2 | 2 | 64 | 64 | PASSED | 122 | .0297 | 2 | 0->0 |
| vssymv_hdv_m4 | 4 | 32 | 32 | PASSED | 128 | .0312 | 2 | 0->0 |
| vssymv_hdv_m4 | 4 | 64 | 64 | PASSED | 138 | .0168 | 2 | 0->0 |
| vssymv_hdv_m8 | 8 | 32 | 32 | PASSED | 160 | .0195 | 2 | 0->0 |
| vssymv_hdv_m8 | 8 | 64 | 64 | PASSED | 170 | .0103 | 2 | 0->0 |
| vstrsm_hdv_m2 | 2 | 32 | 32 | PASSED | 30985 | 15.1293 | 572 | 0->0 |
| vstrsm_hdv_m2 | 2 | 64 | 64 | PASSED | 120249 | 29.3576 | 2232 | 0->0 |
| vstrsm_hdv_m4 | 4 | 32 | 32 | PASSED | 40898 | 9.9848 | 604 | 0->0 |
| vstrsm_hdv_m4 | 4 | 64 | 64 | PASSED | 160466 | 19.5881 | 2360 | 0->0 |
| vstrsm_hdv_m8 | 8 | 32 | 32 | PASSED | 74462 | 9.0895 | 672 | 0->0 |
| vstrsm_hdv_m8 | 8 | 64 | 64 | PASSED | 292310 | 17.8411 | 2624 | 0->0 |
| vsgemm_m1_1r | 32 | 1 | 32 | PASSED | 31910 | .9738 | 1056 | 1024->992 |
| vsgemm_m1_2r | 32 | 2 | 32 | PASSED | 19248 | .5874 | 528 | 512->496 |
| vsgemm_m1_4r | 32 | 4 | 32 | PASSED | 9183 | .2802 | 264 | 256->248 |
| vsgemm_m4_1r | 16 | 1 | 16 | PASSED | 8255 | 2.0153 | 256 | 0->0 |
| vsgemm_m4_1r | 32 | 1 | 32 | PASSED | 31837 | .9715 | 1024 | 0->0 |
| vsgemm_m4_1r | 64 | 1 | 64 | PASSED | 133676 | .5099 | 4352 | 0->0 |
| vsgemm_m4_1r | 128 | 1 | 128 | PASSED | 794787 | .3789 | 18432 | 0->0 |
| vsgemm_m4_2r | 16 | 2 | 16 | PASSED | 5435 | 1.3269 | 128 | 0->0 |
| vsgemm_m4_2r | 32 | 2 | 32 | PASSED | 20819 | .6353 | 512 | 0->0 |
| vsgemm_m4_2r | 64 | 2 | 64 | PASSED | 81541 | .3110 | 2048 | 0->0 |
| vsgemm_m4_2r | 128 | 2 | 128 | PASSED | 478798 | .2283 | 8192 | 0->0 |
| vsgemm_m4_4r | 16 | 4 | 16 | PASSED | 3485 | .8508 | 64 | 0->0 |
| vsgemm_m4_4r | 32 | 4 | 32 | PASSED | 13211 | .4031 | 256 | 0->0 |
| vsgemm_m4_4r | 64 | 4 | 64 | PASSED | 55253 | .2107 | 1024 | 0->0 |
| vsgemm_m4_4r | 128 | 4 | 128 | PASSED | 351503 | .1676 | 4096 | 0->0 |
| vsgemv_hdv | 16 |  | 16 | PASSED | 121 | .4726 | 2 | 0->0 |
| vsgemv_hdv | 32 |  | 32 | PASSED | 126 | .1230 | 2 | 0->0 |
| vsgemv_hdv | 64 |  | 64 | PASSED | 136 | .0332 | 2 | 0->0 |
| vsgemv_hdv | 128 |  | 128 | PASSED | 160 | .0097 | 2 | 0->0 |
| vsger_hdv | 16 |  | 16 | PASSED | 3004 | 11.7343 | 64 | 0->0 |
| vsger_hdv | 32 |  | 32 | PASSED | 3004 | 2.9335 | 65 | 0->0 |
| vsger_hdv | 64 |  | 64 | PASSED | 4604 | 1.1240 | 130 | 64->64 |
| vsger_hdv | 128 |  | 128 | PASSED | 7804 | .4763 | 260 | 196->196 |
| vssymv_hdv | 16 |  | 16 | PASSED | 122 | .4765 | 2 | 0->0 |
| vssymv_hdv | 32 |  | 32 | PASSED | 128 | .1250 | 2 | 0->0 |
| vssymv_hdv | 64 |  | 64 | PASSED | 138 | .0336 | 2 | 0->0 |
| vssymv_hdv | 128 |  | 128 | PASSED | 162 | .0098 | 2 | 0->0 |
| vssyrk_hdv | 16 |  | 16 | PASSED | 13840 | 54.0625 | 4112 | 0->0 |
| vssyrk_hdv | 32 |  | 32 | PASSED | 84582 | 82.5996 | 32801 | 0->0 |
| vssyrk_hdv | 64 |  | 64 | PASSED | 600231 | 146.5407 | 262212 | 0->0 |
| vssyrk_hdv | 128 |  | 128 | FAILED | 799998 | 48.8280 | 373010 | 0->0 |
| vstrsm_hdv | 16 |  | 16 | PASSED | 10682 | 41.7265 | 158 | 0->0 |
| vstrsm_hdv | 32 |  | 32 | PASSED | 40898 | 39.9394 | 604 | 0->0 |
| vstrsm_hdv | 64 |  | 64 | PASSED | 160466 | 39.1762 | 2360 | 0->0 |
| vstrsm_hdv | 128 |  | 128 | PASSED | 636146 | 38.8272 | 9328 | 0->0 |

当前总表中的注意点:

- 参数化的 `vsgemv_hdv_m*` 和 `vssymv_hdv_m*` 当前显示很小的 task cycles,且没有预取流量;
  这里按当前 log 如实记录,不再沿用旧文档中的 BLAS 预取数据。
- `vsgemm_m1_*` 仍然显示有效预取:1024->992、512->496、256->248。
- `vsgemm_m4_*` 在当前总表中为 demand-only。
- `vssyrk_hdv@128` 当前失败,不能作为有效论文性能点。

## 6. 固定规模 kernel

| Kernel | result | task_cycles | demand_ar | pf_ar->hit | seq_full |
|---|---|--:|--:|--:|--:|
| fconv2d_fix | PASSED | 19170 | 600 | 0->0 | 0 |
| jacobi2d_fix | PASSED | 20338 | 144 | 0->0 | 4718 |
| lavamd_fix | PASSED | 2757 | 5 | 36->36 | 0 |
| softmax_fix | PASSED | 6881 | 73 | 0->0 | 0 |
| vsspmv_fix | PASSED | 4908 | 1090 | 64->62 | 0 |
| vssyrk_m1_fix | PASSED | 84582 | 32801 | 0->0 | 0 |
| vstrsm_m1_fix | PASSED | 30918 | 558 | 0->0 | 0 |

当前固定规模 kernel 注意点:

- `lavamd_fix` 当前在 `kernel_all.csv` 中为 PASSED;统计修正后实际 demand AR 为 5,
  prefetch AR/hit 为 36->36。
- `jacobi2d_fix` 通过,但它是唯一一个 `seq_full != 0` 的 PASS 行。
- `vssyrk_m1_fix` 是固定规模 m1 的通过结果,对应 32-size vssyrk 点。

## 7. 当前可用于论文的数据点

性能结论只使用 PASS 行:

- AVL sweep:72 条 AVL 行全部 PASS。
- BLAS/GEMM:除 `vssyrk_hdv@128` 外,当前 BLAS 行全部 PASS。
- 固定规模 kernel:当前 fixed 行全部 PASS。

当前 CSV 支撑的主要定性结论:

- 单位步长流式 AVL kernel 仍然能达到完整或近完整预取命中。
- `dropout_hdv` 在大 AVL 下保持预期的冷启动差 1 次命中。
- `vsdwt_hdv` 当前有预取 AR 流量,但 demand 命中为 0。
- `vsscal_hdv` 和 `vsdot_hdv` 主要受计算/依赖行为支配,不是预取 miss 支配。
- demand-only 或 strided BLAS kernel(`vstrsm_hdv`,`vssyrk_hdv`)仍明显慢于简单单位步长流式 kernel。
