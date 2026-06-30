# HDV 内核 AVL Sweep 报告

**日期**：2026-06-22 　**分支**：`hdv`
**平台**：ARA + HDV 前端，VLEN=1024，NrLanes=4，AxiDataWidth=128bit，IPU buffer=32 包，预取 buffer=64 项，MaxOutstandingVecEPs=2

> AVL = application vector length（内核 strip-mine 的元素总数）。本实验扫描 AVL，观察周期数 / 吞吐 / 预取命中随问题规模的变化。

---

## 1. 实验方法

- **统一旋钮**：`hardware/Makefile` 加 `avl ?= 1024`，接到各 1D 内核的 AVL 参数（a0 / a2 / vsaxpy 的 elements）。`make sim app=<k> avl=<N>` 即把该内核的应用向量长度设为 N。
- **sweep 脚本**：`hardware/kernel_sweep.sh`
  ```bash
  ./kernel_sweep.sh 1d "32 64 256 1024 4096"          # 所有 9 个 1D 内核 × 自定义 AVL
  ./kernel_sweep.sh kernel vsdot_hdv "32 64 256"      # 单内核 × 自定义 AVL
  ./kernel_sweep.sh all                               # 1D + BLAS/GEMM + fixed 全量 sweep
  ```
  输出统一写入 `kernel_sweep_out/`: `avl_all.csv`、`<kernel>.csv`、log 和实时控制台表。
- **本次数据**：AVL = `16 64 256 1024 4096`（5 点几何序列）。
- **AVL 运行期注入（已实现，关键）**：scalar backend 复位时读 `$value$plusargs("HDV_A<n>=%d")` 覆盖 `xrf[10+n]`。sweep 脚本用 `make sim app=<k> hdv_plusargs="+HDV_A<reg>=<N>"` 设 AVL，**运行期生效、无需重 elaborate**。
  - *为什么必须运行期*：VCS 对命令行 `+define+` 改动不重编（`../simv up to date`），所以 **define-based AVL 是 stale 的**（实测 vsdot 改 a2 define 不生效，卡在首次编译值）。plusarg 每次跑都生效，可靠。
  - *速度*：同一内核换 AVL ~55s（不重编）；仅换内核（地址 define 变）重编一次。比 define-per-point（~3 min/点）快 ~3–5×。
- **任务截断解除（已实现，关键）**：mock host 在 `acknowledged_eps >= expected_ep` 时自动完成任务；`expected_ep` 由编译期 ELEMENTS（默认 1024）算出，会把 AVL>1024 **截在 1024**。sweep 再传 `+HDV_EXPECTED_EP=8000000`（很大）→ host 改为等内核自然 `ret` → 跑完整 AVL。实测 vsaxpy 2048→1546cyc(256EP, 2×)、4096→3076(512EP, 4×)，正常翻倍。
- **数据上限**：data.S 静态，AVL 必须 ≤ 各内核数组元素数（见下表 max；如 vsdot 数组仅 1024）。提高上限需用 gen 脚本（`apps/<orig>/script/gen_data.py`）重新生成更大数据。

## 2. AVL 范围推荐

各 config 的 VLMAX = VLEN×LMUL/SEW：e32/m1=32、e64/m1=16、e64/m2=32、e64/m4=64、e64/m8=128、e16/m4=256、e32/m8=256。

| 区间 | AVL | 覆盖 regime |
|---|---|---|
| 亚向量 | 8, 16 | 最小 VLMAX(16) 单/亚向量 |
| 单/数向量 | 32, 64 | 启动开销 |
| 预取热身 | 128, 256 | 命中率爬升；最大 VLMAX(256) 单向量 |
| 稳态 | 512, 1024 | 预取饱和 |
| 深稳态 | 2048, 4096 | 渐近 cyc/元素 |

- 核心序列：`8 16 32 64 128 256 512 1024 2048 4096`
- 可选尾数（测 strip-mine 余数）：`100 1000 3000`

## 3. Sweep 数据（9 个 1D 内核）

> 列：cycles=total_task_cycles；cyc/el=cycles/AVL（吞吐）；EPs=执行包；avg/pk=IPU avg_cycles_per_pkt；pf=预取 AR→命中。

采集自 `kernel_sweep_out/`（运行期注入，可靠）。`—`=数据上限或未取。

### 表 3a — Cycles（total_task_cycles）

数据数组已把 vmc/vvaddint32/fdotp 从 1024 平铺到 4096（脚本 `/tmp/tile_data.py`），vsswap/vsdot 本就 4096。

| Kernel | EEW/LMUL | AVL 16 | 64 | 256 | 1024 | 2048 | 4096 |
|---|---|---:|---:|---:|---:|---:|---:|
| vsaxpy | e32/m1 | 28 | 47 | 200 | 792 | — | 3076 |
| vscopy | e32/m1 | 25 | 52 | 208 | 832 | — | 3307 |
| vsscal | e32/m1 | 27 | 58 | 250 | 1018 | — | 4075 |
| vsdot | e32/m1 | 89 | 148 | 472 | 1768 | 3496 | **6952** |
| vmc | e16/m4 | 113 | 113 | 113 | 394 | 813 | **1649** |
| vsswap | e32/m1 | 29 | 82 | 334 | 1350 | 2692 | ✗死锁 |
| vvaddint32 | e32/m1 | 28 | 62 | 194 | 746 | ✗死锁 | ✗死锁 |
| fdotp | e64/m8 | 98 | 133 | 396 | ✗死锁 | 1842 | — |
| dropout | e32/m8 | 113 | 113 | 113 | 113 | — | — |

> 加粗 = 本轮数据扩展后新跑通的高点。`✗死锁`= 该 AVL 触发前端死锁（task_error，与数据无关，见 §4.4）。

### 表 3b — cyc/元素（吞吐，越低越好）

| Kernel | 16 | 64 | 256 | 1024 | 2048 | 4096 |
|---|---:|---:|---:|---:|---:|---:|
| vsaxpy | 1.75 | 0.73 | 0.78 | 0.77 | — | 0.75 |
| vscopy | 1.56 | 0.81 | 0.81 | 0.81 | — | 0.81 |
| vsscal | 1.69 | 0.91 | 0.98 | 0.99 | — | 0.99 |
| vsdot | 5.56 | 2.31 | 1.84 | 1.73 | 1.71 | 1.70 |
| vmc | 7.06 | 1.77 | 0.44 | 0.38 | 0.40 | 0.40 |
| vsswap | 1.81 | 1.28 | 1.30 | 1.32 | 1.31 | — |
| vvaddint32 | 1.75 | 0.97 | 0.76 | 0.73 | — | — |
| fdotp | 6.13 | 2.08 | 1.55 | — | 0.90 | — |
| dropout | 7.06 | 1.77 | 0.44 | 0.11 | — | — |

> vsdot/vmc 的 cyc/元素在大 AVL 收敛（vsdot~1.70 归约稳态、vmc~0.40），证明数据扩展后稳态可达。

### 表 3c — 预取 AR→命中（单位步长内核的预取热身）

| Kernel | 16 | 64 | 256 | 1024 | 4096 |
|---|---|---|---|---|---|
| vsaxpy | 0→0 | 2→1 | 13→12 | 61→61 | 235→232 |
| vscopy | 0→0 | 1→1 | 7→7 | 32→32 | 131→131 |
| vsswap | 0→0 | 2→2 | 14→14 | 64→64 | 195→194 |
| vsscal | 0→0 | 1→1 | 7→7 | 32→32 | 131→131 |
| vsdot | 0→0 | 2→2 | 14→14 | 63→63 | — |
| vmc | 0→0 | 0→0 | 0→0 | 3→3 | — |

> EPs / packets / avg_cyc_per_pkt 全量见 `kernel_sweep_out/<kernel>.csv`。

## 4. 分析

### 4.1 吞吐（cyc/元素）随 AVL
- **纯流式**（vsaxpy / vscopy / vsscal / vvaddint32）：小 AVL 启动开销高（16→1.6–1.8），AVL≥64 即压到 **~0.75–1.0 平**（吞吐受限，启动很快摊薄）。vscopy 全程 0.81（最规整）。
- **双流读写**（vsswap）：~1.3（同时读 src1/src2 + 写回，比单流高）。
- **归约**（vsdot / fdotp）：启动最高（16→5.6 / 6.1），随 AVL 单调下降（→1.7 / 1.5）——`vfred*` 归约树的固定尾开销被摊薄；归约类对小 AVL 最不友好。
- **大 VLMAX**（vmc e16/m4、dropout e32/m8，VLMAX=256）：AVL≤256 时只 1 个向量，cyc/元素 由"1 向量固定开销 / 元素数"主导，从 7.06(16) 暴跌到 0.44(256)；过 256 进入多向量后才稳。

### 4.2 预取热身（表 3c）
单位步长流式内核：AVL=16 **0% 命中**（冷启动，无预取）→ 64 ~50% → 256 ~90% → **≥1024 ~100%**。即**预取要 ~256–1024 元素才热满**；小 AVL 下预取无收益。非单位步长 / 大 LMUL（vmc）预取很少（3→3@1024）。

### 4.3 EPs 与封装
- EPs 随 AVL **线性**（= strip-mine 迭代数 × 每迭代 EP）。`avg_cyc/pkt` 多数 4–10。
- **dropout 反常**：恒 2 EP / 113 cyc / avg 35，**不随 AVL 变**——内核只处理 1 个 chunk，a0(n) 未驱动 strip-mine（内核结构问题，非注入失效；其 e32/m8 单向量 avg 35cyc/pkt 也最重）。

### 4.4 数据扩展与高 AVL 异常
**数据已扩展到 4096**：vsswap/vsdot 的 data.S 本就 4096（早先 1024 是 expected_ep 截断假象，已修）；vmc/vvaddint32/fdotp 用 `/tmp/tile_data.py` 把 1024 数组平铺 4× 到 4096，并更新了被平铺顶移的后续数组地址（Makefile）。

扩展后暴露两类问题：

| 内核 | 现象 | 性质 |
|---|---|---|
| **vsdot / vmc** | 干净跑到 4096，cyc/元素收敛 | ✅ 数据扩展成功 |
| **vsswap** | ≤2048 正常，**4096 死锁** | 高迭代数触发前端死锁 |
| **vvaddint32** | ≤1024 正常，**≥2048 死锁**（EP 卡在 164 不动） | 前端死锁 |
| **fdotp** | 1024 死锁、2048 通，**不稳定** | 前端死锁（与 fdotp 原始 got=49 同源）|
| **dropout** | 全程 113cyc，a0 不驱动 strip-mine | 内核结构（见 4.3）|

> **关键（已定位）**：vsswap/vvaddint32/fdotp 的高 AVL 失败**不是数据问题**（数据已够）。根因诊断（addrgen 停滞探针抓死锁瞬间）：
> - 死锁态：`occ=12 rob_empty=1 inflight=0 match=0 ar_v=0`——预取 buffer 还有 12 项驻留没人消费，addrgen 完全空闲。
> - 因为 `vec_busy=0`（向量单元空闲）：**前端在某 EP 停止派发**（vvaddint32@2048 停在 EP 164/256）。
> - **死锁在前端/dispatch,不在 addrgen**。预取是**触发器**：关预取后 vvaddint32 干净跑到 4096（2103/4217cyc）。预取让 load 走 buffer 命中、完成变快，改变 EP 完成时序，**暴露前端的一个竞态**（与 MaxOutstandingVecEPs=2 的 EP 完成跟踪疑似相关）。
>
> **工作区**：受影响内核设 `prefetch_mode=0` 即可跑到 4096（损失预取收益）。**根治需探前端/HEU 的 EP 完成握手**，是后续工作。vsaxpy/vscopy/vsscal/vsdot/vmc 无此问题（预取开也能到 4096）。

## 5. 复现

```bash
cd hardware
./kernel_sweep.sh 1d "16 64 256 1024 4096" # 重跑本报告
# 单内核加密：
./kernel_sweep.sh kernel vsdot_hdv "8 16 32 64 128 256 512 1024 2048 4096"

# 单点直接跑(运行期注入,AVL 寄存器: 多数 a0=A0; vsdot/fdotp=A2):
make sim app=vscopy_hdv hdv_plusargs="+HDV_A0=2048"
make sim app=vsdot_hdv  hdv_plusargs="+HDV_A2=512"
```

## 6. 范围与局限

- **已覆盖（9 个 1D 流式内核）**：vsaxpy, vvaddint32, vscopy, vsswap, vsdot, vsscal, vmc, dropout, fdotp —— "AVL" = 向量长度，干净可扫。
- **数据上限（静态数组）**：vsaxpy/vscopy/vsswap/vsdot/vsscal=4096；vmc=2048；vvaddint32/dropout=1024；fdotp=2048。提升需 gen 脚本重生成。
- **未覆盖**：vsdwt（AVL 经 t0，接法不同）；矩阵/2D 内核（gemm/syrk/jacobi2d/fconv2d 等，"AVL"=内层维度，需按 2D 维度单独参数化）。
- **性能**：AVL 经运行期 `+HDV_A<n>` 注入（`hdv_scalar_backend.sv`），同一内核扫各 AVL 点**无需重编**；仅换内核时重编一次。`+HDV_EXPECTED_EP` / `+HDV_TASK_WATCHDOG` 同理运行期覆盖。
