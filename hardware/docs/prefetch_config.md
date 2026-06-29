# HDV 数据预取配置约束

适用：`addrgen.sv` 的向量单位步长(unit-stride)load 预取。基于 RTL 常量推导，
建议对关心的具体点用 `avl_sweep` 实测复核（计数器 `pf_ar / pf_hit / pf_avl_low`）。

## 硬件常量（来自 RTL）

| 量 | 值 | 出处 |
|---|---|---|
| 预取缓冲预算 `PrefetchBufBeats` | **128 AXI beat** | `addrgen.sv` |
| AXI 数据宽 `AxiDataWidth` | 128 bit = **16 B/beat** | config |
| store 饿死时的 bounded lead `PrefetchLeadBeats` | 24 beat | `addrgen.sv` |
| lead 倍率 `prefetch_mul`（来自 HDV_HINT `prefetch_mode`） | 1X/2X/4X → L=1/2/4（`prefetch_mode` 为 2-bit，`PF_EN_8X` 在 enum 中定义但编码不可达） | `addrgen.sv` |

credit 门：`(resident×2 + in_flight + 本次burst) ≤ 128` → **缓冲永不溢出**；
超预算的预取 AR 只是**等待 / 退化为 demand-only**，不会 wedge / overflow。

## 两个约束

**① enable 门（不满足则 `pf_ar=0`，完全不预取）**

    AVL ≥ 2 × VL          (VL = min(AVL, VLMAX))
    ⟹ 实际需 AVL ≥ 2 × VLMAX

**② fit 门（不满足则 lead 受预算限，部分降级为 demand，仍不溢出）**

    K × L × (VL × SEW/8) / 16  ≤  128   beat
    ⟺  K × L × VL × SEW ≤ 16384
    e32 (SEW=32):  K × L × VL ≤ 512

K = 并发单位步长 load 流数；L = 2^prefetch_mul（lead 深度，单位=描述符）。

每条 vle 描述符占用 beat = VL × (SEW/8) / 16；e32 → **VL/4**（VL=32 → 8 beat）。

## 配置表（e32；✓=满预取，⚠=超预算降级为 demand，非溢出）

| LMUL | VLMAX→VL | beat/描述符 | enable 门 AVL≥ | K=1 | K=2 | K=4 | K=8 |
|---|---|---|---|---|---|---|---|
| **m1** | 32 | 8  | 64  | 1X/2X/4X ✓ | 1X/2X/4X ✓ | 1X/2X/4X ✓ | 1X/2X ✓·4X⚠ |
| **m2** | 64 | 16 | 128 | 1X/2X/4X ✓ | 1X/2X/4X ✓ | 1X/2X ✓·4X⚠ | 1X ✓·2X⚠ |
| **m4** | 128| 32 | 256 | 1X/2X/4X ✓ | 1X/2X ✓·4X⚠ | 1X ✓·2X⚠ | ⚠ |
| **m8** | 256| 64 | 512 | 1X/2X ✓·4X⚠ | 1X ✓·2X⚠ | ⚠ | ⚠ |

（表按 VL=VLMAX 计；若 VL<VLMAX，beat/描述符按实际 VL 缩小，fit 更宽松，但 enable
门要求 AVL≥2VL，而 VL<VLMAX 时 AVL=VL → enable 反而**不满足**，见下。）

## 实务要点

- **enable 门是真正的卡点**。`VL=min(AVL,VLMAX)`，若 AVL≤VLMAX 则 VL=AVL → `avl=vl`
  → 永远 `< 2vl` → 否决。要满足 `avl≥2vl` 必须 **AVL>VLMAX**，此时 VL 被钳到 VLMAX。
  - **m1 主路径**：`li aX,1024; vsetvli` → AVL=1024、VL=32，轻松满足 → 预取生效（实测
    vsgemm m1 248 命中、vsaxpy/vsdot/vscopy 高命中）。
  - **m4 局限**：要 VL=N 就得 AVL=N≤128 → `avl=vl` 否决（实测 vsgemm m4 N=128 →
    `pf_avl_low`、pf_ar=0）。只有当你**就是要 VL=128** 时设 AVL≥256 才可用。
- **流数 K**：credit 流控对**任意 K 死锁安全**；fit 门决定满 lead 的上限。
  `PrefetchLeadBeats=24`≈“2 流 e32/m1 的 1.5 迭代”，即默认调优在 **m1、1–2 流**。
- **跨步 `vlse` / gather**：不走此有效预取路径（每元素 1 AR，实测极慢，如 vssyrk）。
- **重刷流**（一条流复位重读，如 vsgemm 每 row-block 重读 B）：由 stream-break
  flush 修复支持（addrgen 检测地址回跳 → 排空在途后原子 flush lookup FIFO + vldu buffer）。

## 一句话
预取是为 **m1 + 高AVL/低VL 把戏**设计的：VL=真实数据量(≤32)、AVL 抬到 1024。
此档下 1–8 流、1X–4X lead 基本都不溢出（见表）。m2 勉强、m4 仅满 VL=128 可用。
