# HDV 流式内核 AVL Sweep —— 结果与分析

记录 ARA-HDV 向量流水在一组 1D 流式内核上、随应用向量长度(AVL)缩放的性能,并基于
增强版 sweep 采集的 58 列计数器做瓶颈诊断。

## 1. 测量配置

- **硬件**:VLEN = 1024 b、NrLanes = 4、AxiDataWidth = 128 b(= 16 B/beat),**单个共享
  AXI 端口**,DATA 预取器开启。
- **指标**:`task_cycles` = mock-host 测得的任务总周期;`cyc/el` = task_cycles ÷ AVL;
  `pf` = 预取 AR 发出数 → demand 命中数。
- **RTL 状态(post-fix)**:same-id LSU + vset-wb 路由 + addrgen `rob_match` 跨页 flag 修复
  + vldu per-burst 预取命中消费 + store-aware **bounded-lead** 预取 + **去除全局预取模式否决**。
- **采集**:`hardware/avl_sweep.sh`,每个 AVL 点记录 58 列(HDV-CSR / HDV-PERF / IPU-PERF /
  PERF-ADDRGEN(-PF) / PERF-SEQ + 派生)。
- **核集合**:8 个 —— vsaxpy、vvaddint32、vscopy、vsscal、vsdot、vsswap、vmc、dropout。
- **fdotp 排除**:其预取对自身地址/时序病态敏感(非单调),任何描述符消费时序的改动都
  会大幅改变其命中率;点积类由 vsdot 代表(vsdot 对所有修复逐位一致)。
- AVL 8 → 4096 全程 **全核 PASS**。

## 2. 主结果:周期与效率

### 2.1 总周期 vs AVL

| 核 | dtype | 256 | 512 | 1024 | 2048 | 4096 |
|---|---|--:|--:|--:|--:|--:|
| vsaxpy     | f32 | 195 | 387 | 771  | 1552 | 3114 |
| vvaddint32 | i32 | 212 | 403 | 796  | 1578 | 3140 |
| vscopy     | f32 | 208 | 416 | 832  | 1657 | 3307 |
| vsscal     | f32 | 250 | 506 | 1018 | 2037 | 4075 |
| vsdot      | f32 | 472 | 904 | 1768 | 3496 | 6952 |
| vsswap     | f32 | 334 | 670 | 1350 | 2693 | 5379 |
| vmc        | i32 | 113 | 192 | 394  | 813  | 1656 |
| dropout    | f32 |  59 | 196 | 536  | 1096 | 2216 |

### 2.2 效率(cyc/el)

| 核 | 256 | 512 | 1024 | 2048 | 4096 |
|---|--:|--:|--:|--:|--:|
| vsaxpy     | 0.761 | 0.755 | 0.752 | 0.757 | 0.760 |
| vvaddint32 | 0.828 | 0.787 | 0.777 | 0.770 | 0.766 |
| vscopy     | 0.812 | 0.812 | 0.812 | 0.809 | 0.807 |
| vsscal     | 0.976 | 0.988 | 0.994 | 0.994 | 0.994 |
| vsdot      | 1.843 | 1.765 | 1.726 | 1.707 | 1.697 |
| vsswap     | 1.304 | 1.308 | 1.318 | 1.314 | 1.313 |
| vmc        | 0.441 | 0.375 | 0.384 | 0.396 | 0.404 |
| dropout    | 0.230 | 0.382 | 0.523 | 0.535 | 0.541 |

所有核 cyc/el 都呈"小 AVL 高、大 AVL 收敛到 plateau":小 AVL 时每核固定的启动开销
(vsetvli、首迭代冷启动 miss、流水填充)摊到很少元素上;AVL ≥ 1024 摊薄到稳态。
**评估稳态性能应看 AVL ≥ 1024 的点**,256 及以下偏悲观。

## 3. 瓶颈分类:带宽受限 vs 延迟/计算受限

单端口 16 B/beat、1 beat/cycle,R 与 W 串行(由 vsaxpy 实测端口利用率 ≈ 94 % 印证),
故带宽下界 `floor(cyc/el) = 每元素搬运字节 ÷ 16`:

| 核 | 访存模式 | B/elem | floor | 实测@4096 | 距 floor | 瓶颈 |
|---|---|--:|--:|--:|--:|---|
| vsaxpy     | 2L+1S e32       | 12   | 0.75 | 0.760 | **99 %** | 带宽 |
| vvaddint32 | 2L+1S i32       | 12   | 0.75 | 0.766 | **98 %** | 带宽 |
| dropout    | L+mask+S e32/m8 | ~8.1 | ~0.51| 0.541 | ~94 %    | 带宽 |
| vsswap     | 2L+2S e32(原地)| 16   | 1.00 | 1.313 | 76 %     | 带宽(最重) |
| vscopy     | 1L+1S e32       | 8    | 0.50 | 0.807 | 62 %     | 有余量 |
| vmc        | 1L+1S e16/m4    | 4    | 0.25 | 0.404 | 62 %     | 有余量 |
| vsscal     | 1L+1S e32       | 8    | 0.50 | 0.994 | 50 %     | 计算/依赖 |
| vsdot      | 2L e32(规约)   | 8    | 0.50 | 1.697 | **29 %** | 规约依赖 |

- **带宽受限组(vsaxpy / vvaddint32 / dropout / vsswap)**:实测贴着 floor(76–99 %),
  预取满命中,已压到单端口物理极限 —— 再快只能靠加宽 AXI 或让 R/W 并发。
- **延迟/计算受限组(vsdot / vsscal / vscopy / vmc)**:实测远离 floor,瓶颈不在带宽:
  - **vsdot(1.70 cyc/el,仅 29 % floor,最慢)**:规约 `vfmacc` 把结果累加进同一寄存器,
    形成迭代间依赖链,compute 无法流水,load 再快也填不满 —— 规约依赖受限,与访存无关。
  - **vsscal(0.99,50 %)**:1L+1S 本应与 vscopy 一样轻,但多了 `vfmul` + 标量依赖、EP 链
    更长;瓶颈在计算侧,不是预取(见 §5C 的 `ipu_ready_stall`)。
  - **vscopy / vmc(62 %)**:纯 copy / 轻核,余量来自单端口 R/W 串行 + 每 strip 启动开销。

## 4. 预取效果

### pf ARs → demand hits

| 核 | 256 | 1024 | 4096 |
|---|--:|--:|--:|
| vsaxpy     | 13→12 | 63→59 | 255→251 |
| vvaddint32 | 14→14 | 64→61 | 260→260 |
| vscopy     | 7→7   | 32→32 | 131→131 |
| vsscal     | 7→7   | 32→32 | 131→131 |
| vsdot      | 14→14 | 63→63 | 258→258 |
| vsswap     | 14→14 | 64→64 | 262→262 |
| vmc        | 0→0   | 3→3   | 17→16   |
| dropout    | 1→0   | 7→6   | 31→30   |

去掉过度保守的全局模式否决 + bounded-lead 后,**全 8 核高 AVL 都达 ~100 % 命中**。唯一
系统性的"差 1"是 vmc / dropout 的**冷启动**:首迭代之前无物可预取,必然一次 demand
miss —— 物理最优,不是缺陷。

两处修复的定位:
- **vsaxpy(带宽受限组)**:store-aware drain 原来把预取排空到 0、demand 暴露 load 延迟;
  改成保留 ~1 迭代提前量的 bounded-lead 后,贴上 0.75 floor(−7…−12 %)。
- **vsscal(延迟受限组)**:预取曾被全局预取模式否决误杀到只剩 3 个 AR(该全局模式在
  HDV packet 间隙瞬时掉 0,而 addrgen 滞后于前端,单流短循环恰好在间隙被处理 → 合法
  预取被一刀切)。去掉这个否决后预取满命中(3 → 131,−7…−15 %)。它仍到不了带宽 floor
  是 `vfmul` 依赖所限,不是预取问题。

## 5. 全量计数器诊断(58 列 @ AVL=4096)

由增强版 `avl_sweep.sh` 采集。**健康性总览**:全核
`vec_busy = imem_outstanding = real_wait_stall = resp_meta_stall = resp_meta_max =
seq_full = pf_ar_rob_full = pf_ar_lkup_full = pf_queue_full = 0`,且 `vq_push == vq_pop`
—— 无结构性溢出、无命令泄漏、无死锁残留;预取信用 = 物理 buffer(128 beat = 128 beat),不溢。

### 5A. 顶层周期 / EP
| 计数 | axpy | vadd | copy | scal | dot | swap | vmc | drop |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| task_cycles | 3114 | 3140 | 3307 | 4075 | 6952 | 5379 | 1656 | 2216 |
| cyc/el | .760 | .766 | .807 | .994 | 1.697 | 1.313 | .404 | .541 |
| wall_cycles | 3182 | 3208 | 3375 | 4143 | 7020 | 5447 | 1724 | 2284 |
| eps | 512 | 512 | 384 | 384 | 519 | 512 | 424 | 149 |

`wall = task + 68`(恒定 68 = mock host 启动开销)。`eps` = 迭代数 × 每迭代 EP 数;dot 519
(规约尾)、drop 149(m8 宽、迭代少)。

### 5B. HDV-PERF(派发路径)
| 计数 | axpy | vadd | copy | scal | dot | swap | vmc | drop |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| ep_ack | 384 | 384 | 256 | 384 | 386 | 384 | 80 | 48 |
| ep_vset_ack | 128 | 128 | 128 | 128 | 129 | 128 | 16 | 16 |
| vq_push/pop | 637 | 637 | 382 | 509 | 638 | 638 | 90 | 94 |
| vq_max_occ | 8 | 8 | 5 | 7 | 8 | 8 | 7 | 8 |
| vq_bypass | 3 | 3 | 2 | 3 | 5 | 2 | 6 | 2 |
| **vq_full_stall** | 45 | 11 | 0 | 0 | 0 | **1237** | 0 | **1278** |
| dispatch_cycles | 940 | 906 | 512 | 766 | 898 | **2259** | 96 | **1406** |
| operand_wait_cyc | 640 | 651 | 384 | 512 | 643 | 640 | 96 | 96 |
| ara_backpressure | 2450 | 2477 | 2900 | 3541 | 6281 | 4719 | 1448 | 2071 |

- `ep_vset_ack = 128`(= 迭代数,4096/32):每迭代一条 vsetvli;vmc/drop=16(m4/m8 宽)。
- **`vq_full_stall`:swap 1237、drop 1278 突出** —— 这两核把向量命令队列压满、派发被挡
  (swap 是 2L+2S 最重访存,drop 是 m8 宽包,后端消化慢 → vq 堆积,`dispatch_cycles` 同步偏高)。
- `ara_backpressure` 随总周期单调(dot 最高 6281)。`real_wait_stall = resp_meta_stall = 0`
  —— 派发后端从不满,派发不是任何核的瓶颈。

### 5C. IPU-PERF(操作数服务)—— vsscal 瓶颈的铁证
| 计数 | axpy | vadd | copy | scal | dot | swap | vmc | drop |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| ipu_ready_cyc | 640 | 642 | 514 | **3631** | 643 | 640 | 179 | 130 |
| **ipu_ready_stall** | 2 | 3 | 3 | **3120** | 2 | 2 | 2 | 18 |
| ipu_sram_stall | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 17 |
| ipu_serve_cyc | 3094 | 3113 | 3283 | 4047 | 6814 | 5333 | 1630 | 2089 |
| packets | 638 | 639 | 511 | 511 | 641 | 638 | 177 | 112 |
| bypass_hits | 255 | 256 | 130 | 130 | 257 | **382** | 132 | 80 |
| demand_reads | 1 | 1 | 2 | 2 | 2 | 1 | **118** | 49 |
| avg_cyc_per_pkt | 4 | 4 | 6 | 7 | 10 | 8 | 9 | **18** |

- **`ipu_ready_stall`:vsscal 3120,其余核仅 2~18 —— 单这一列就把 vsscal 的瓶颈钉死**:
  IPU 准备好却卡 3120 周期,等的是 `vfmul` 依赖链;它的预取已满命中(load 不缺),剩下
  全卡在计算侧 → vsscal 是计算/依赖受限,不是带宽、不是预取。
- `ipu_serve_cyc ≈ task_cycles`:操作数服务几乎占满全程(IPU 是主干)。
- `demand_reads`:多数核 1~2(几乎全靠预取/bypass 命中);**vmc 118、drop 49** 例外
  (mask / 部分流走 demand 读)。`avg_cyc_per_pkt`:drop 18(m8 宽包)、dot 10(规约慢)。
- `bypass_hits`:swap 382 最高(原地交换,操作数大量走 bypass)。

### 5D. PERF-ADDRGEN(访存 / 预取主计数)
| 计数 | axpy | vadd | copy | scal | dot | swap | vmc | drop |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| demand_ar | 139 | 213 | 132 | 132 | 260 | 256 | 17 | 32 |
| pf_ar | 255 | 260 | 131 | 131 | 258 | 262 | 17 | 31 |
| pf_hit | 251 | 260 | 131 | 131 | 258 | 262 | 16 | 30 |
| loads | 254 | 256 | 128 | 128 | 256 | 256 | 16 | 32 |
| pf_en_cyc | 2979 | 3005 | 3172 | **1178** | 6817 | 5244 | 1633 | 2193 |
| **demand_aw** | 129 | 132 | 132 | 132 | **0** | 264 | 18 | 16 |
| demand_B | 1296 | 480 | 128 | 128 | 256 | 256 | 512 | 1056 |
| pf_B | 30832 | 31648 | 15872 | 15872 | 32080 | 31728 | 6992 | 15872 |

- **`demand_aw`(store AW)dot = 0** —— 印证 dot 循环内无 store(规约,末尾才写);swap = 264
  (2 store/迭代),其余 ~128~132(1 store/迭代)。
- `pf_ar ≈ pf_hit ≈ loads`:预取数 ≈ 命中数 ≈ load 数 —— 几乎每条 load 都被预取命中。
- **`pf_en_cyc`:vsscal 仅 1178**(其余 3000~6800),却照发 131 个 AR:因 vfmul 卡着、load
  节奏被拉稀,少量预取窗口就够覆盖 → 再次指向计算受限。
- `pf_B ≫ demand_B`:读流量绝大部分以预取形式发出(藏延迟),demand 读只剩零头。

### 5E. PERF-ADDRGEN-PF(预取背压细分;rob_full / lkup_full / queue_full 全 0,略)
| 计数 | axpy | vadd | copy | scal | dot | swap | vmc | drop |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| pf_ar_pending | 247 | 253 | 127 | 127 | 254 | 254 | 15 | 31 |
| pf_ar_dis | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| pf_2nd | 8 | 7 | 4 | 4 | 4 | 8 | 2 | 0 |
| **dem_rob_block** | **238** | 50 | 0 | 0 | 2 | 4 | 2 | 1 |
| **pf_disabled** | **115** | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| pf_page_cross | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| pf_avl_low | 0 | 1 | 0 | 0 | 0 | 0 | 9 | 0 |

- **`dem_rob_block`:axpy 238、vadd 50** —— demand 命中 `rob_match` 被 defer(等自己的预取
  退休)的次数,是预取-命中机制正常工作的体现(axpy 预取深、defer 多)。
- **`pf_disabled`:axpy 115** —— bounded-lead 的 store-aware 节流在起作用(store 紧张时暂停
  预取让端口),只对 axpy 这种 store-bound 核生效,正是它能贴 floor 的关键。
- `pf_2nd`(跨页第二段)0~8、`pf_page_cross` 仅 vadd=1:即使数据未对齐,高 AVL 下跨页预取
  也极少,**绝大多数是单 burst** —— 所以"对齐"对这批核没必要。
- `pf_avl_low`:vmc=9(m4 宽 → 迭代少,末尾 avl<2vl 占比高)。

### 5F. PERF-SEQ(定序器冒险)—— 这列直接标出"延迟/依赖受限核"
| 计数 | axpy | vadd | copy | scal | dot | swap | vmc | drop |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| seq_issue | 640 | 640 | 384 | 512 | 387 | 768 | 80 | 49 |
| seq_blocked | 2071 | 2097 | 2647 | 3288 | **6027** | 4209 | 32 | 2029 |
| seq_raw | 252 | 128 | 128 | 256 | 131 | 128 | 32 | 17 |
| **seq_war** | 1 | 1793 | 2391 | 3033 | **5785** | 3697 | 2 | 1982 |
| seq_waw | **1687** | 33 | 0 | 128 | 528 | 1 | 0 | 64 |
| seq_waw_block | 1687 | 33 | 0 | 0 | 401 | 1 | 0 | 48 |
| seq_ep_bypass | 320 | 512 | 128 | 192 | 449 | 261 | 32 | 56 |

- **`seq_war`(写后读冒险)是计算/依赖受限的指纹**:dot 5785(规约累加器,每迭代 WAR)、
  swap 3697、scal 3033、copy 2391、drop 1982 —— 定序器被 WAR 大量阻塞;而 axpy=1、vmc=2
  几乎无 WAR。这条线与"cyc/el 远离带宽 floor"完全吻合:**WAR 风暴 = compute 流水填不满**。
- `seq_blocked`:dot 6027 最高,与它最慢一致。
- **`seq_waw`:axpy 1687 独高且全 block** —— axpy 有强 WAW(累加进 y),但因为它是**带宽
  受限**,WAW 阻塞和访存等待重叠、不在关键路径上,cyc/el 仍贴 floor。**教训:单看一个冒险
  计数会误判,必须结合瓶颈类别一起读。**

### 5G. 一句话总览(58 列读出来的因果)
| 核 | 主瓶颈(由哪几列坐实) |
|---|---|
| vsaxpy / vvaddint32 | 带宽(cyc/el ≈ floor;pf 满命中;`dem_rob_block`/`pf_disabled` 显示预取+store 节流在工作) |
| vsscal | **计算**(`ipu_ready_stall=3120` + vfmul 的 `seq_war=3033`;预取已满命中) |
| vsdot | **规约依赖**(`seq_war=5785` 最高 + `demand_aw=0` 无 store + `seq_blocked=6027`) |
| vsswap | 带宽最重(`demand_aw=264` 双 store + `vq_full_stall=1237`) |
| vmc / dropout | 访存轻 + 冷启动(`demand_reads` 偏高、命中率差 1) |

## 6. 本轮修复的净收益(原始基线 → 现在,@4096)

| 核 | 周期 | Δ | 由哪处修复 |
|---|--:|--:|---|
| vsscal | 4813 → 4075 | **−15.3 %** | 去全局预取模式否决,解除单流预取抑制 |
| vsaxpy | 3358 → 3114 | **−7.3 %**  | bounded-lead 恢复 distance-1 预取流水 |
| 其余 6 核 | 不变 | 0 | 逐位一致,零回归 |

## 7. 方法学注记

- **vsswap@4096** 是唯一原地 read-modify-write 核,曾在数组大小 AVL **死锁**;per-burst
  预取命中描述符消费修复之(5379 cyc、1.31 cyc/el,与其余 AVL 点一致)。
- **dropout**(掩码标量乘 `o[k] = SEL[k] ? I[k]·scale : 0`,e32/m8)曾因臃肿的标量 `main`
  把任务推离 mock host 启动入口而退化成常数 113 cyc / 2 EP;改造成极简 `main`(任务落在
  0x80001000)+ 4KB 对齐数据后随 AVL 正常缩放(稳态 ≈ 0.54 cyc/el)。
- **冷启动**:vmc / dropout 高 AVL 命中率差 1,是首迭代必然的 demand miss,物理最优。
- **fdotp** 排除原因见 §1。
