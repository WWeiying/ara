# SEAM-V 实验规划（execution doc）

> 论文：**SEAM-V: A Hybrid Decoupled RISC-V Vector Processor with Back-End-Visible Execute Packets for High-Throughput Vector Execution**
> 投稿：*Integration, the VLSI Journal*（Elsevier, CCF-C）
> 前作：ISCAS 2026（已发表）→ 本期刊版必须严格差异化，核心是 **H0→H+ 的后端增量**。
> 本文档是论文工作文档（小节结构 + 实验执行清单 + 思考）。所有性能数字以真实仿真/综合/PR 结果为准，未跑的标 `TODO`。

---

## 论文定位（重要）

**对比基线 = 主流紧耦合 RISC-V 向量架构（标准 CVA6+Ara，标量核紧耦合驱动向量单元）。** 不以"混合解耦"作为对比类别或定位锚点（它只是作者前作 ISCAS 一篇，非公认方向）。SEAM-V 作为针对紧耦合架构短板（短向量/控制密集下标量发射瓶颈 → 向量 lane 饿死 → 利用率低）的新向量架构来立论；其"解耦+VLIW"是 SEAM-V 自身设计选择（使能后端可见的执行包），不作为对比类别。"语义鸿沟"收到 SEAM-V 内部（解耦后后端对前端 EP 无感知 → 本文用 back-end-visible EP 补上）。ISCAS 仅作前作引用（前端基底 + 防重复发表声明）。

## 全文小节结构（投 Integration, VLSI Journal）

- **Abstract / Keywords**
- **1. Introduction**：1.1 主流紧耦合（CVA6 驱动 Ara）→ 1.2 短向量瓶颈(lane 饿死/利用率低，引 Ara 实测) → 1.3 SEAM-V(VLIW 打包+后端可见 EP) → 1.4 贡献(4) → 1.5 组织
- **2. Background & Related Work**：2.1 紧耦合 RISC-V 向量单元(Ara/Vitruvius…)=基线类；2.2 解耦与 ILP 暴露(DAE/乱序向量/VLIW-EPIC，**ISCAS 前作在此引用**)；2.3 向量 hazard 处理与访存预取；（差异化表）
- **3. SEAM-V Architecture Overview**：3.1 顶层(前端+集成标量后端+Ara) vs 紧耦合基线；3.2 执行包+VLIW HINT header(基底)；3.3 解耦内部的语义鸿沟(铺垫 §4)；3.4 **后端可见的执行包：trans_id 标签通道**(统一机制，核心图)
- **4. Back-End-Visible Execute Packets（核心贡献）**：4.1 EP-aware sequencer hazard bypass；4.2 解耦 VLSU Next-VL 预取(buffer+信用流控+LMUL 泛化)；4.3 访存定序安全的跨 EP 向量提前发射
- **5. Scalar Back-End & Programming Model**：5.1 cva6_hdv_scalar_backend；5.2 task 流+hint 编码+编程模型
- **6. Experimental Methodology**：6.1 RTL 配置(4 lanes,VLEN=1024)；6.2 基线=紧耦合 Ara + ablation 阶梯(T/H_base/H1-H4/IDEAL)；6.3 Benchmark(BLAS L1/L2/L3+真实应用)；6.4 综合/PR/功耗(TSMC 28nm)
- **7. Evaluation**：7.1 主表/ablation(vs 紧耦合 Ara,E1)；7.2 AVL sweep/短向量利用率(E2)；7.3 Lane sweep(E3)；7.4 内存延迟敏感性(E4)；7.5 微架构计数器(E5)；7.6 真实应用(E6)；7.7 PPA+版图(E7)；7.8 敏感性(E8,可选)
- **8. Discussion**：局限、>2 EP 扩展、future work
- **9. Conclusion** / **References**

**图表**：Fig.1 架构总览(重画,不复用 ISCAS) · Fig.2 EP+HINT header · Fig.3 trans_id 标签通道(核心) · Fig.4 hazard bypass · Fig.5 解耦预取 · Fig.6 跨EP early issue · Fig.7 ablation 瀑布 · Fig.8 AVL 曲线 · Fig.9 lane · Fig.10 内存延迟 · Fig.11 版图; Tables: 计数器/真实应用/面积/功耗.

**可写性**：§1-§5(机制基于已有 RTL) **现在就能写**(占 60%+)；§6.x+§7 等实验回填(先占位)。

---

## 0. 要证明的命题（实验都为这些服务）

| # | 命题 | 主要支撑实验 |
|---|---|---|
| C1 | ep_id 跨边界 → 消除 sequencer 假相关 → 提吞吐 | E1, E3, E5 |
| C2 | EP-driven 解耦预取 → 隐藏访存延迟 | E4, E5 |
| C3 | 跨 EP early issue → 重叠 → 提吞吐 | E1, E5 |
| C4 | 短向量收益大、可泛化、低 PPA 代价 | E2, E3, E6, E7 |

---

## 0.5 进展快照与前置 TODO（截至 2026-06）

### A. 已完成
- **真实应用 HDV 内核移植 + 正确性验证：6/6 通过**
  - softmax(DNN)、lavamd(HPC/分子动力学)、dropout(DNN正则)：spike 逐元素 check 通过。
  - fmatmul(矩阵乘fp64)、fconv2d(CNN fp64)、jacobi2d(stencil fp64)：python 交叉验证通过（dump kernel hex 输出 vs python 解析 data.S 全精度计算，逐元素 ≤1 ULP）。
  - 每个真实应用都有 `<name>_asm`（纯 Ara 基线）+ `<name>_hdv`（packet 化）双版本。
- **HDV 指令硬件兼容性：静态确认全支持**——用到的 vfslide1up/down、vfredusum、vmerge、vfcvt、vfsgnjn、vmflt、vlm.v 都被 Ara 解码/执行；fdiv.d/fcvt.d.w 被标量后端 fpu_wrap 支持。
- **RTL 端到端通路打通**——8 参注入链（InitialA0-A7=xrf[10-17]，5 文件+Makefile）；softmax/lavamd/fconv2d 在真 HDV RTL 上跑通 128/128 EP。

### B. 前置 TODO（跑实验扫描前需备好的基础设施；状态为本轮 RTL 实查）
1. **三优化独立开关（E1 ablation + E7 面积增量）**
   - 跨 EP early issue：✅ `EnableBufferedVectorEarlyIssue` param（hdv_hybrid_execution_unit.sv，置 0 即关）。
   - 解耦预取：🟠 `hdv_prefetch_mode_i`(header imm20[17:18])有 1X/2X/4X/8X（addrgen.sv），**缺 OFF 档**——需加 off 编码/param gate。
   - EP-aware hazard bypass：🔴 `vid_ep_id_q`(ara_sequencer.sv)**焊死常开**，需加 `EnableEpHazardBypass` param，关时走原始全 hazard 检查。
2. **内存延迟可参数化（E4 预取证明）**：✅ 已有 `ara_testharness.sv: AxiRespDelay` + `axi_sim_mem` 延迟；需确认 RTL/cycle 级生效并换算 cycle，扫 10/30/50/100。
3. **kernel 规模参数化（E2 AVL sweep）**：🟠 规模在 data.S（gen_data.py 带 size 参数，已具备）+ init 寄存器（kernel 循环吃 a3/a7/a0）。方案：gen_data 生成规模 S 数据 + InitialReg=S + `HDV_EXPECTED_EP` 设大让 `ret` 结束任务（免逐点重算 EP）+ driver 脚本扫 S=32..2048 + 从 run.vcs.log 抓 cycle。HDV 模式 TB 不校数据（正确性已 spike 验过），纯测 cycle。流式核(softmax/dropout/lavamd/vsaxpy)是 AVL sweep 主力；矩阵核(fmatmul/fconv2d/jacobi2d)按矩阵维度扫、进主表。
4. **lane 数参数化（E3 泛化）**：✅ `config/{2,4,8,16}_lanes.mk` + NrLanes param。⚠️ 确认 `config/4_lanes.mk` 的 `nr_lanes ?= 8`（疑似笔误）+ HDV 前端 ep_id 位宽对 lane 数无写死。

### C. 移植硬约束（gotchas，对后续任意复杂内核通用）
- **大内核(>32 fetch包，如 lavamd 40/fconv2d 38)不能用 `loop_start/end` 标记**——会让 IPU 循环头早锁、挡后台预取 → buffer 末包 bg_stall 第一次迭代死锁。去掉标记，靠 IPU 后向分支 auto-lock。
- **内层循环退出**依赖 `branch_backward` 正确判定（已修为 B-type 立即数符号位 `cva6_decoder_instr[31]`）；否则 loop-exit 不触发、IPU 锁死。
- **fp64 归约类参考**勿写 in-program（app 的 -O3 -ffast-math 误编译）；用 python 交叉验证。spike printf 不支持 %f（用 hex via memcpy）。

### D. 实验工作量定性（用户自行执行）
- 轻：① 加 hazard-bypass/预取 OFF 开关；② expected-EP 设大；③ AVL sweep driver 脚本。
- 中：E1/E2/E4/E5 跑数 + 抓 run.vcs.log 计数器；E3 多 lane 重综合。
- 重：E7 PPA（综合 + PR 版图 + 门级功耗 SAIF）。

---

## 1. 对照阶梯（baseline ladder）

**Headline 对照 = `T`（原生 Ara） vs `H4`（完整 SEAM-V）。** 主表/主图都以原生 Ara 为基线报 speedup 与利用率，不引入"ISCAS 版"作为对比曲线。

下面的 `H_base`→`H4` 是 **ablation 内部拆解**，用来说明每个后端优化各贡献多少，属于正常工程拆解，不是"和某篇论文对比"。

| 标记 | 含义 | 开关 |
|---|---|---|
| `T`    | **原生 Ara（传统标量核驱动，无 HDV）——主基线** | 关 HDV |
| `H_base` | HDV base：前端打包在、后端三优化全关 | 三优化全关 |
| `H1`   | H_base + EP-aware sequencer hazard bypass | 开 hazard bypass |
| `H2`   | H1 + 解耦 VLSU 预取（静态使能） | 开 prefetch |
| `H3`   | H2 + 动态预取控制（VLIW header） | 开 dynamic pf ctrl |
| `H4`=`H+` | H3 + 跨 EP buffered vector early issue | 开 early issue（完整 SEAM-V） |
| `IDEAL` | `apps/ideal_dispatcher` 理想分发上界 | — |

> 注：面积/功耗的"新增逻辑增量"用 `H_base` vs `H4` 做差得到——这是隔离后端优化硬件成本的工程手段，与对比基线无关。
>
> **前置 TODO**：确认每个开关都有独立的 `define`/`param`，能逐档退回。已知存在：`EnableBufferedVectorEarlyIssue`、prefetch 的 `PF_EN`/header `imm20[18:17]`。需确认 hazard bypass 是否有独立开关（否则要临时加一个仿真用 `ifdef`）。
>
> **学术合规（与对比基线分开处理）**：ISCAS 2026 是同作者同架构的已发表前作，期刊版**必须在 Related Work 引用并说明 delta**（后端协同设计为新增），cover letter 声明差异。这是防"重复发表"的硬要求，但**不需要**作为实验对比曲线——主对比仍是原生 Ara。

---

## 2. Benchmark 套件

### 2.0 各 kernel 计算公式

> 约定：标量 $a,\alpha,\beta,s$；向量 $\vec{x}$（分量 $x_i$）；矩阵 $A$（元素 $A_{ij}$）；向量长度 $n$。

**进主表的 7 个（Tier-1）**

| kernel | 公式 | BLAS/类型 | 访存 |
|---|---|---|---|
| vsaxpy | $y_i \leftarrow a\,x_i + y_i$ | L1 | unit-stride |
| vscopy | $y_i \leftarrow x_i$ | L1（纯访存） | unit-stride |
| vsdot | $d = \sum_i a_i b_i$（归约→fa0） | L1 归约 | unit-stride |
| vsgemv | $y_i = \sum_j A_{ij} x_j$（$A$:32×128） | L2 | unit-stride |
| vsspmv | $y_i = \sum_{k} \text{val}_k\, x_{\text{col}_k}$（CSR，间接寻址） | L2 稀疏 | **indexed/gather** |
| vssyrk | $C_{ij} \leftarrow \alpha\sum_k A_{ik}A_{jk} + \beta C_{ij}$（更新三角） | L3 | **strided** |
| vsgemm | $C_{ij} = \sum_k A_{ik} B_{kj}$（$32^3$） | L3 | unit-stride |

**Tier-1 其余（已移植，未必进主表）**

| kernel | 公式 | 说明 |
|---|---|---|
| vsscal | $y_i \leftarrow a\,x_i$ | 标量缩放（L1） |
| vsswap | $\vec{x} \leftrightarrow \vec{y}$ | 交换两向量 |
| vvaddint32 | $z_i = x_i + y_i$ | int32 整数加 |
| vssymv | $\vec{y} \leftarrow \alpha A\vec{x} + \beta\vec{y}$（$A=A^{\mathsf T}$） | 对称矩阵·向量（L2） |
| vsger | $A_{ij} \mathrel{+}= \alpha\, x_i y_j$ | rank-1 更新（L2，嵌套） |
| vstrsm | 解 $L X = B$ 求 $X$ | 三角方程组求解（L3，前向代入+skip 分支） |
| vmc | $y_i = (x_i \cdot s) \gg 3$ | 定点 widening（e16→e32） |
| vsdwt | $s_i=(x_{2i}+x_{2i+1})/\sqrt2,\; d_i=(x_{2i}-x_{2i+1})/\sqrt2$ | Haar 小波一步（就地） |

**Tier-2 真实应用（待移植）**

| app | 公式 | 领域 |
|---|---|---|
| softmax | $\text{softmax}(\vec{x})_i = \dfrac{e^{x_i-\max_k x_k}}{\sum_j e^{x_j-\max_k x_k}}$ | DNN（max 归约+exp+和归约+除） |
| fconv2d | $Y_{i,j} = \sum_{m}\sum_{n} X_{i+m,\,j+n}\,K_{m,n}$ | CNN（滑窗，计算 bound） |
| jacobi2d | $A^{\text{new}}_{i,j} = c\,(A_{i,j}+A_{i\pm1,j}+A_{i,j\pm1})$ | 科学/5 点 stencil |
| blackscholes | $C = S\,\Phi(d_1) - Ke^{-rT}\Phi(d_2)$，$d_{1,2}=\frac{\ln(S/K)+(r\pm\sigma^2/2)T}{\sigma\sqrt T}$ | 金融（超越函数密集，标量-向量混合最强） |

### 2.1 Tier-1：BLAS 微核（已移植，做主表 + ablation），7 个

| kernel | BLAS | 结构 | 访存模式 | 主压测贡献 | 角色 |
|---|---|---|---|---|---|
| `vsaxpy`  | L1 | 单层 | unit-stride | 全部 | 主例（已 gold 验证） |
| `vscopy`  | L1 | 单层 | unit-stride | 预取（访存 bound） | 预取正例 |
| `vsdot`   | L1 | 归约 | unit-stride | hazard bypass + vec→scalar 写回 | 归约 |
| `vsgemv`  | L2 | 多 chunk + 行归约 | unit-stride | hazard bypass（计算密） | L2 |
| `vsspmv`  | L2 | gather | indexed (vluxei) | 预取**优雅 no-op** | 预取负例 |
| `vssyrk`  | L3 | 嵌套 | strided | 预取（strided 部分有效）+ loop-lock | 访存中间态 |
| `vsgemm`  | L3 | 嵌套 | unit-stride | 长向量收敛 + hazard bypass | 计算 bound |

> 可选 `vsger`（L2 嵌套）专测跨 EP early issue。

### 2.2 Tier-2：真实应用（证明外推性）

> **现状核查（2026-06）**：fconv2d / jacobi2d / dropout / fmatmul **已有真改造的 HDV 版本**（hand-asm + 最新 HDV_HINT 含 prefetch_mode，已编进 `apps/bin/`），git 提交 "port … to hand-asm baseline + HDV" 印证。**但均未 gold 验证、不在 README_hdv 已测 15 核清单内**。只剩 softmax / blackscholes 需新移植。

| 应用 | 状态 | 领域 | 压测点 | 优先级 |
|---|---|---|---|---|
| `fconv2d_hdv`  | ✅已验证(见 §0.5) | CNN 3×3(fp64) | 滑窗 unit-stride、计算 bound → 预取 + hazard bypass | **P1（先验证）** |
| `jacobi2d_hdv` | ✅已验证(见 §0.5) | 科学/5点 stencil | 邻域 strided + 嵌套 → 预取 + loop-lock | **P1（先验证）** |
| `dropout_hdv`  | ✅已验证(见 §0.5) | DNN 正则 | elementwise + mask，访存 bound | P2 |
| `fmatmul_hdv`  | ✅已验证(见 §0.5) | 矩阵乘(fp64) | 计算 bound、长向量收敛 | P2 |
| `softmax_hdv`  | ✅已验证(见 §0.5) | DNN | exp+归约+除法，标量/向量强交织 → hazard bypass + 跨EP | **P1（新移植首选）** |
| `blackscholes` | ❌需新移植 | 金融/RiVEC | 超越函数 + 标量数学穿插向量 → HEU/跨EP 拉满 | P3（冲刺） |

覆盖 CNN / 科学计算 / DNN / 金融 多域，堵死 "microkernel-only" 质疑。**实际移植负担 = 仅 softmax（+ 可选 blackscholes）；其余 4 个只需补 gold 验证。**

> **TB 配置 caveat**：README_hdv §0 描述的 `+define+HDV_APP_<NAME>` per-app 配置机制在当前 `ara_tb.sv` 中 grep 不到（只见统一 `HdvTaskEntry`，默认 0x8000_1000）。每个 kernel 在 TB 跑起来所需的 init 寄存器(a0-a3/fa0) + expected-EP 怎么配，**需先重新确认**——直接决定所有 kernel 的 bring-up 成本。

### 2.3 正例 + 负例对照（诚实性加分，明确写进论文）

| 贡献 | 正例（强受益） | 负例（优雅退化） |
|---|---|---|
| hazard bypass | vsgemv / vsdot（EP 内多向量指令） | vsgemm 计算 bound 收益递减 |
| 解耦预取 | vscopy / vsaxpy（unit-stride） | **vsspmv gather → no-op 不拖累** |
| 跨 EP early issue | vsger / softmax（标量穿插） | 纯向量长循环收益小 |

---

## 3. 扫描范围（sweep ranges）

### 3.1 AVL sweep（核心，复刻并扩展 ISCAS 的短向量叙事）
```
AVL = 32, 64, 128, 256, 512, 1024, 2048   (元素数, fp32)
```
- 32–128：SEAM-V 主战场（短向量、标量发射瓶颈最重），重点采样。
- 256：对标 ISCAS 主配置点。
- 1024–2048：证明"长向量收敛到访存 bound"（ISCAS 只到 512，延伸即新内容）。

### 3.2 矩阵/应用规模
| kernel/app | 规模点 |
|---|---|
| vsgemm / vssyrk | M=N=K ∈ {16, 32, 64, 128} |
| vsgemv | 行×列 ∈ {32×128, 128×512} |
| fconv2d | 3×3 kernel，输入 {16×16, 64×64, 128×128} |
| softmax | 行长 ∈ {64, 256, 1024} |
| jacobi2d | 网格 {32×32, 128×128} |

### 3.3 微架构 sweep
| 参数 | 范围 | 用途 |
|---|---|---|
| lane 数 | 2, 4, 8, 16 | E3 泛化；预期 hazard bypass 收益随 lane↑ |
| VLEN | 512, 1024, 2048 | E8 敏感性（可选） |
| 内存 AR 延迟 | 10, 30, 50, 100 cycles | E4 预取鲁棒性（**致命洞，必做**） |
| 预取窗口 | 1×VLEN, 2×VLEN | E8 预取放大比 vs 命中率（可选） |

> **前置 TODO**：(a) kernel 问题规模目前是硬编码宏，需参数化（编译宏或 plusarg）才能扫 AVL；(b) 确认 TB/AXI 内存模型的读延迟可参数化（决定 E4）。

---

## 4. 实验矩阵（E1–E8）

| 实验 | 变量 | 固定配置 | 测什么 | 证 | 优先 |
|---|---|---|---|---|---|
| **E1 主表/Ablation** | T→H_base→H1→H2→H3→H4 + IDEAL | 4 lane, VLEN=1024, AVL=256 | 各阶 cycle + 向量利用率，**逐项 Δ**（主对比 T vs H4） | C1/C3 | 🔴 |
| **E2 AVL sweep** | AVL 32→2048 | 4 lane, VLEN=1024；跑 T/H4 | cycle + util vs AVL；geomean speedup | C4 短向量 | 🔴 |
| **E3 Lane sweep** | lanes 2/4/8/16 | VLEN=1024；T/H4 | speedup vs lane 数 | C1 泛化 | 🟠 |
| **E4 内存延迟 sweep** | AR latency 10/30/50/100 | 4 lane；H2/H4 | 预取收益 vs 延迟；pf 命中率 | **C2（洞2）** | 🔴 |
| **E5 微观计数器** | — | E1 同配置 | seq `blocked/ep_bypass`；addrgen `pf_hit/pf_ar`；HDV `ep_acknowledged`；跨EP 重叠 | C1/C2/C3 机理 | 🔴 |
| **E6 真实应用** | T/H4 | 4 lane | 3–4 真实 app 的 cycle + util | C4 外推 | 🟠 |
| **E7 PPA** | T/H_base/H4（综合 + PR） | — | 面积/功耗/能量，新增逻辑增量 | C4 代价 | 🟠 |
| **E8 VLEN/预取窗口** | VLEN 512/1024/2048；pf 窗 1×/2× | — | 敏感性 | 加分 | 🟡 |

**数据来源**：性能计数器代码里已内建，从 `hardware/sim/run.vcs.log` 抓 `[PERF-SEQ]` / `[PERF-ADDRGEN]` / `[IPU-PERF]` / `[HDV-PERF]`，逐 EP 明细在 `hdv_ep_trace_<TESTCASE>.log`。

---

## 5. PPA：面积测量（重点细化，含 PR 版图阶段）

### 5.1 两个阶段都要报
| 阶段 | 工具 | 产物 | 论文用途 |
|---|---|---|---|
| **综合后 (pre-PR)** | Synopsys Design Compiler，TSMC 28nm（与 ISCAS 同工艺，保持可比） | `report_area` 层次报告、cell area、门数 | 模块层级面积拆分主表 |
| **PR 后 (post-PR)** | Innovus / ICC2 | die/core area、利用率、布线后各 block 面积、**版图图(die shot/floorplan)** | 物理实现可信度 + 版图图（VLSI 期刊强卖点） |

> 报告两套面积：综合面积（逻辑层级清晰、易拆模块）+ PR 后实际 die area（含布线/利用率，体现真实物理代价）。版图图建议同时给整体 floorplan 和高亮"新增 SEAM-V 逻辑"的着色图。

### 5.2 面积分层（按 RTL 真实模块名）

**L0 — 芯片整体**：SEAM-V SoC 总 die area / core area / 利用率（PR 后）。

**L1 — 顶层 block（占比饼图/堆叠条）**：
| L1 block | 对应 RTL |
|---|---|
| HDV 前端 | `hdv_top` 下的 TIU/TSU/IPU/VLIWPU/HEU/vec_dispatch（去掉 mock host） |
| 标量后端 | `cva6_hdv_scalar_backend` |
| Ara 向量核 | `ara` = dispatcher + sequencer + lanes + VLSU + MASKU/SLDU |
| 访存/互连 | `axi_mux` + AXI bridge + `axi_inval_filter` |

**L2 — 子模块（核心拆分表）**：
| 区域 | 子模块 (RTL 文件) |
|---|---|
| HDV 前端 | `hdv_task_interface_unit` (TIU)、`hdv_task_schedule_unit` (TSU)、`hdv_instruction_prefetch_unit` (IPU，含双 64B buffer)、`hdv_vliw_pack_unit` (VLIWPU)、`hdv_hybrid_execution_unit` (HEU)、`hdv_vec_dispatch_unit`（含 command window + operand service） |
| 标量后端 | decoder、2× simple ALU、complex lane(branch/mult/FPU/LSU)、XRF/FRF/CSR stub（`cva6_hdv_scalar_backend` 内部） |
| Ara 向量核 | `ara_dispatcher`、`ara_sequencer`、`lane`×N（内含 `vector_regfile`/`operand_queue`/`vmfpu`/`valu`/`simd_mul`/`simd_div`）、`vlsu`(`addrgen`/`vldu`/`vstu`)、MASKU、SLDU |

**L3 — SEAM-V 新增逻辑的增量面积（贡献成本的关键证据）**：
通过 **H0 vs H4 同条件综合做差**，隔离出每个贡献新增的硬件：
| 新增逻辑 | 落在哪个模块 | 预期量级 |
|---|---|---|
| ep_id / trans_id 通道加宽 | dispatcher→sequencer 通路 | 极小（几 bit 寄存器/线） |
| hazard bypass 比较逻辑 | `ara_sequencer`（per-vid `vid_ep_id_q` 比较器） | 小 |
| **VLSU 预取 buffer + FSM** | `addrgen` + `vldu` ping-pong buffer | **最大新增**（buffer 存储） |
| 跨 EP early issue 逻辑 | `hdv_hybrid_execution_unit` skid + 依赖 mask、`hdv_vec_dispatch_unit` command window | 中等 |

> 论文里给一张"**SEAM-V 各优化的增量面积 / 总面积占比**"表，直接回答审稿人"加这些值不值"。预期总增量很小（前端+协同逻辑相对 4-lane Ara 是小头），配合性能 −40% 形成强论证。

### 5.3 面积报告 TODO
- [ ] H4 完整综合，导出 L0/L1/L2 层次 `report_area`。
- [ ] H0 同条件综合，与 H4 做差得 L3 增量。
- [ ] （可选）H1/H2/H3 各综合一次，得到逐优化增量。
- [ ] PR 跑通 H4，导出 die area / 利用率 / floorplan 图。

---

## 6. PPA：功耗测量（跑哪些 kernel、怎么跑）

### 6.1 方法学（gate-level + SAIF/VCD → 功耗）
```
RTL → 综合(DC) → 门级网表
门级网表 + SDF(PR后反标) → gate-level 仿真(跑某 kernel) → VCD/SAIF(翻转活动)
网表 + SAIF → PrimeTime PX / Power Compiler → 动态+静态功耗
```
- 用 **PR 后反标 SDF** 的门级仿真活动文件最准（与 ISCAS 的 SAIF 流程一致，保持可比）。
- 报告拆 **dynamic / leakage**，并给 **per-block 功耗**（用 L1/L2 层级）。

### 6.2 跑哪些 kernel（功耗仿真贵，选代表，不全跑）

选 **4 个 kernel**，覆盖访存 bound / 计算 bound / 混合 / 负例，每个跑 **T / H0 / H4** 三档：

| kernel | 代表性 | 为什么选 |
|---|---|---|
| `vscopy` | 访存 bound | 预取活跃时功耗（预取放大访存→看 pf 是否多耗能） |
| `vsgemm` | 计算 bound | 向量单元高占用下的功耗主体 |
| `softmax` | 真实混合 | 标量/向量交织的真实功耗画像 |
| `vsspmv` | 负例 | 预取 no-op 时不额外耗能的证据 |

> 共 4 kernel × 3 档 = 12 次门级功耗跑。若机器紧张，最少保 vscopy + vsgemm × (H0,H4) = 4 次。

### 6.3 关键指标：报"能量"而非只报"功率"
H4 跑得快（cycle 少），即使瞬时功率略升，**能量(energy-to-solution)仍可能更低**——这是公平且有利的指标：
```
Energy_per_kernel = avg_power × cycles
能效 = GFLOP/s / W   (对标 ISCAS Table II 的口径)
```
报告表建议列：`config | avg power(mW) | cycles | energy(nJ/μJ) | GFLOP/s/W`。
预期故事：**H4 vs H0，功率略增（多了预取/比较逻辑），但 cycle 大降 → 单位任务能量下降、能效上升。**

### 6.4 功耗报告 TODO
- [ ] 选定 4 kernel 的门级网表 + 反标。
- [ ] 各 kernel × {T,H0,H4} 跑门级仿真出 SAIF。
- [ ] PrimeTime PX 出动态/静态/per-block 功耗。
- [ ] 算 energy-to-solution 与能效，列对照表。

---

## 7. 论文图表清单（实验 → 图表映射）

| 图/表 | 内容 | 来自 |
|---|---|---|
| Fig. Ablation | T→H_base→H1→H2→H3→H4 堆叠/瀑布图（逐优化 Δcycle） | E1 |
| Fig. AVL | speedup & 向量利用率 vs AVL 曲线（T vs H4） | E2 |
| Fig. Lane | speedup vs lane 数（T vs H4） | E3 |
| Fig. MemLat | 预取收益 & 命中率 vs 内存延迟 | E4 |
| Tab. Counters | seq stall / ep_bypass / pf_hit 等微观指标 | E5 |
| Tab. RealApp | 真实应用 cycle/util（T vs H4） | E6 |
| Tab. Area | L1/L2 面积 + L3 增量（H_base vs H4） | E7 |
| Fig. Floorplan | PR 版图（高亮 SEAM-V 新增逻辑） | E7-PR |
| Tab. Power | 功率/能量/能效（4 kernel × 3 档） | E6.x |

---

## 8. 优先级与执行顺序

**P0（先做，堵致命洞，性价比最高）**
1. kernel 规模参数化（所有 sweep 的前提）。
2. 确认/补齐三优化独立开关 → 能跑出 H0/H1/H2/H3/H4。
3. E4 内存延迟 sweep（堵预取悬空洞，TB 加延迟参数即可）。
4. E1 ablation（含 H0）先在已验证的 vsaxpy 上跑通全阶梯。

**P1（主体实验）**
5. Tier-1 其余 6 核：补 TB config + gold 验证 → 扩 E1/E2/E5。
6. 真实应用：**fconv2d_hdv + jacobi2d_hdv 已存在，只需补 gold 验证**；新移植 softmax → E6。
7. E7 面积：H_base/H4 综合做差。

**P2（补全 + 加分）**
8. E3 lane sweep；验证 dropout_hdv/fmatmul_hdv（已改造）；移植 blackscholes；E6 功耗 4 kernel；PR 版图；E8。

**最小可发表集**：E1(7核, T vs H4 + ablation) + E2(AVL) + E4(内存延迟) + E6(≥softmax+1) + E7(面积+功耗)。E3/E8 锦上添花。

---

## 9. 数据状态与风险

- 现状：**6 个真实应用(softmax/lavamd/dropout/fconv2d/fmatmul/jacobi2d)已验证**（见 §0.5）；Tier-1 其余 BLAS 微核多数仍"能编译、数据未验"，进性能表前需各自验证。
- 现状更正（利好）：fconv2d/jacobi2d/dropout/fmatmul 真实应用 HDV 版**已存在**，新移植负担仅剩 softmax(+可选 blackscholes)。
- 风险1：bring-up 主要成本从"移植"转为"**逐 kernel 补 TB init 配置 + gold 验证**"；先确认当前 TB 的 per-app 配置机制（见 §2.2 caveat）。
- 风险2：E4 依赖 TB 内存延迟可参数化；E3 依赖 lane 数只换 param 不动 RTL——两者需先确认。
- 风险3：ISCAS 已发表，Fig/表/文字不得复用；主对比用原生 Ara，但**仍须在 Related Work 引用 ISCAS 并说明 delta**（后端协同为新增），cover letter 声明差异，防重复发表。
- 原则：**只填真实跑出的数字，未跑标 TODO，不臆造。**

---
---

# 论文正文初稿（中文）

> 投 *Integration, the VLSI Journal*。以下为 §1、§2 中文初稿，引用编号见文末"参考文献（本节）"。英文定稿时整体翻译润色；正文以紧耦合 Ara 为对比基线，不以"混合解耦"作对比类别。

## 1. Introduction（引言）

深度神经网络、科学计算与自动驾驶等数据并行负载的算力需求在过去十年持续高速增长 [1]，推动通用处理器走向 SIMD 与向量化。RISC-V 向量扩展（RVV）[2] 以开源、可伸缩、变长向量的特性，成为兼顾峰值性能与能效的主流路线。当前主流实现普遍采用异构组织：一个应用级标量核负责控制流、地址计算与标量运算，**紧耦合**驱动一个由多条同构 lane 构成的向量协处理器来承担数据并行计算，以 CVA6 + Ara [3,4,5] 为代表。

这一紧耦合组织的根本约束在于：标量核处在**向量指令供给的关键路径**上——每条向量指令都必须先由标量核取指、译码、发射，才能进入向量流水。向量体系结构本应"用一条指令摊销到整条向量上"以隐藏取指与发射开销 [3,4]；CVA6 执行一个点积内核时每次操作耗能约 317 pJ，其中仅约 28 pJ 用于真正的计算，其余几乎全部花在标量控制路径上 [4,5]。因此一旦**向量较短或控制流较密集**，标量核的发射速率便不足以喂饱向量 lane，向量单元利用率随向量长度（AVL）缩短而急剧下降——短向量（AVL≈32）下利用率可降至约 40%（不足峰值的一半）[16]，意味着占据芯片绝大多数面积与功耗预算的向量硬件被大量闲置。而短向量恰恰是 DNN 推理、稀疏与不规则核、以及 strip-mine 循环尾部等真实负载中的常态 [10]，使该瓶颈在实际应用中难以回避。

为缓解这一瓶颈，已有工作或以更宽发射、乱序的标量核更快地投放向量指令 [7,8,9]，或把向量侧从标量核解耦、借助软件在打包阶段暴露的并行性（VLIW/显式 ILP）半自治执行 [6,11,12,16]（详见 §2）。前者以标量侧显著增加的面积、功耗与设计复杂度为代价；后者虽提升了指令供给，却只解决了问题的一半——**解耦之后的向量后端，对前端在打包阶段本已掌握的语义（哪些指令同属一个互不依赖的发射组、是否处于循环体内、接下来将连续访问哪段地址）依然"无感知"**，只能按最坏情况保守地重查数据相关、并以 demand-only 方式访存，把本可省去的假相关阻塞与访存延迟重新计入关键路径。换言之，解耦在提高"指令供给"的同时，反而在前后端之间制造了一道**语义鸿沟**。

本文提出 **SEAM-V**，一个解耦、VLIW 打包的 RISC-V 向量处理器，其核心思想是**让前端的执行包（execute packet, EP）对后端保持"可见"**。SEAM-V 在前端以一条 RISC-V HINT 指令（`lui x0, imm20`，因 `rd=x0` 对架构状态无副作用）[15] 作为取指包头部，一次性编码软件暴露的并行性（p-bit）、循环边界与预取意图；并由此派生出一组轻量标签——执行包身份、循环活跃标志与预取幅度——通过复用既有的加速器请求通路、以近乎零开销贯通进向量后端。后端据此得以：(i) 对同一执行包内本无数据依赖的向量指令免除假相关检查、(ii) 对循环体内的单位步长访存按软件指定幅度提前预取、(iii) 在保证内存定序正确的前提下跨执行包提前发射向量指令。相对于紧耦合 Ara 基线，这些后端协同优化在保持 RVV ISA 与编程模型不变、且新增逻辑相对四 lane Ara 面积/功耗代价近乎可忽略的前提下，将典型核的执行周期显著降低，并大幅回升短向量场景的向量单元利用率。

本文主要贡献如下：
1. **后端可见的执行包（back-end-visible execute packets）**：提出一种跨解耦边界的前后端协同设计抽象，并给出零开销的标签通道——`trans_id = {cmd_class, is_last_in_ep, ep_id}` 连同 `loop_active` 与 `prefetch_mode`，复用 `acc_req → ara_req` 通路贯通至向量后端，不修改 RVV ISA、不新增握手。
2. **EP-aware sequencer hazard bypass**：在向量 sequencer 内按执行包身份跳过同包内的 RAW/WAW/WAR 检查（p-bit 保证同包无依赖），消除由指令快速连续投放引发的假相关阻塞。
3. **EP-driven 解耦 VLSU 预取**：地址生成单元在循环体内自动识别单位步长 load，并按头部指定幅度提前发射预取请求；配以 ping-pong 预取缓冲、基于占用的信用流控，并泛化支持 LMUL 1/2/4/8。
4. **访存定序安全的跨 EP 向量提前发射**，并以真实的、基于 CVA6 的标量后端完成全系统实现，在 TSMC 28 nm 工艺下完成综合与版图，给出面积、功耗与能量的完整 PPA 评估。<!-- 具体加速比/利用率/PPA 数字待实验回填 -->

全文组织如下：§2 回顾 RVV 与紧耦合向量单元、并讨论相关工作；§3 概述 SEAM-V 架构与执行包/HINT 基底，并引出解耦后端的语义鸿沟；§4 详述后端可见执行包的标签通道及其使能的三项后端优化；§5 介绍标量后端微架构与编程模型；§6、§7 给出实验方法学与评估；§8 讨论局限与扩展；§9 总结。







## 2. Background and Related Work（背景与相关工作）

### 2.1 向量体系结构与 RISC-V 向量扩展（RVV）

向量体系结构的思想可追溯到 Cray-1 [17]：以一组**向量寄存器**为核心，单条向量指令在深度流水的功能单元上依次处理一整组元素，并通过 **chaining**（链接）把一条指令的逐元素结果直接前递给下一条相关指令，从而在不增加指令数的前提下重叠多条向量运算。"用一条指令把取指/译码/发射开销摊销到一整组数据上"这一向量架构的根本优势即源于此。RVV [2] 在现代开源 RISC-V 上复兴并推广了该思想，但采用了**向量长度无关（vector-length agnostic, VLA）**的编程模型：架构层面提供 32 个向量寄存器，单条二进制无需在编译期知道目标实现的物理向量位宽（VLEN），即可在不同 VLEN 的实现上正确且高效地运行。

程序以 `vsetvli` 在运行时配置 `vtype`（元素宽度 SEW、寄存器分组 LMUL、尾/掩码处理策略）并申请本轮可处理的向量长度 `vl`；SEW 与 LMUL 共同决定一条逻辑向量覆盖的元素数，LMUL 还可把数个物理寄存器拼成一条长向量，掩码运算以 `v0` 为掩码源。由此形成 RVV 标志性的 **strip-mine 循环**：每轮先申请一段 `vl` 元素、执行 load/算术/store 向量体，再据 `vl` 推进指针与剩余计数并经条件回边继续，直到处理完任意长度的应用向量（AVL）。该模型换得跨实现可移植性，代价是**每轮迭代都夹带一组标量控制指令**（vset、指针/计数更新、回边分支），且 `vl` 在循环体内取满、在尾部取部分——短向量与不规则负载下，正是这部分标量控制开销主导了执行时间。

RVV 的代表性**紧耦合实现** Ara [3,4] 由若干同构 lane 组成，每条 lane 持有向量寄存器文件与功能单元（整型/浮点）的一个切片；它作为协处理器挂接在应用级标量核 CVA6 [5] 之后，标量核顺序地把向量指令经加速器接口投放给 Ara 的派发器（dispatcher）与定序器（sequencer），再由 sequencer 跨 lane 调度、并以类 chaining 方式重叠相邻向量指令。在长向量、计算密集场景下 Ara 可达到很高的功能单元利用率（16 lane 上的双精度大矩阵乘约 97% [3]）；但由于每条向量指令都须先经标量核取指—译码—发射、且每轮 strip-mine 还附带上述标量控制开销，其利用率随 AVL 缩短而迅速下降（§1）。Spatz [10] 以紧凑向量单元集群化来改善短向量效率，但单元内仍受标量供给约束。本文即以紧耦合 Ara 作为对比基线。

### 2.2 提升指令供给与暴露指令级并行

围绕"如何更快地把向量指令送进向量单元"，已有工作可归为两类。**(a) 增强标量主核**：乱序向量体系结构 [8,9] 及 SemiDynamics 的乱序向量单元 [7] 借助乱序发射、寄存器重命名与深内存子系统提高发射率与访存容忍度；代价是标量/向量前端的面积、功耗与验证复杂度大幅上升。**(b) 解耦执行与显式并行**：DAE [11] 将访存与计算解耦为可重叠的指令流；Vitruvius+ [6] 以译码后解耦加重命名实现混合顺序/乱序、并通过开放向量接口与标量核松耦合；VLIW/EPIC [12] 与 TI C66x 等 DSP 用 p-bit 在编译期标记并行边界、把无依赖指令打成长指令包以零硬件依赖检查暴露 ILP [13]。作者在前期工作 [16] 中借鉴上述思想，用 RISC-V HINT 在向量场景实现**动态 VLIW 打包**与任务级解耦，构成本文 SEAM-V 的前端基底。需要强调的是，上述工作主要解决"指令供给"一侧：它们把指令更快、更自治地送进向量单元，但**解耦后的向量后端依然对前端的打包语义无感知**；SEAM-V 补上的正是"让后端利用执行包语义"这一被忽略的环节，这也是本文相对前作 [16] 的核心新增（前作聚焦前端打包与任务解耦，本文聚焦后端协同）。

### 2.3 向量相关性处理与访存预取

在向量后端内部，sequencer 通常以 scoreboard 对在飞向量指令做保守的 RAW/WAW/WAR 检查 [3,4]；当指令被快速连续投放时，这种最坏情况检查会把本无依赖的指令也判为相关而阻塞发射，产生**假相关**开销。访存一侧，硬件预取与跨步预取 [14] 以及解耦访存前端常被用于隐藏内存延迟，但其预测多基于运行时观测到的地址流，对短促或不规则的访问难以及时收敛。SEAM-V 与上述思路的关键区别在于其信息来源：它不依赖运行时的相关性推断或地址流预测，而是直接利用**软件在打包阶段即已确定的执行包边界与循环标记**——据此精确地判定同包指令互不依赖以免检、并触发与循环迭代步长相匹配的预取，从而以更低的硬件代价获得更精确的相关性处理与访存提前。

### 2.4 与已有工作的差异化

综上，已有工作或以加重标量/向量前端复杂度换取更高发射率 [7,8,9]，或以解耦与显式并行把指令送进向量单元 [6,11,12,16]，或以运行时启发式做相关性检查与访存预取 [3,4,14]。SEAM-V 的独特之处在于**同时**：(1) 维持解耦带来的高指令供给；(2) 让向量后端"看见"并利用前端的执行包语义，从而在 sequencer 与 VLSU 两处以软件确定性的信息消除假相关与访存延迟；(3) 全程不修改 RVV ISA、新增逻辑 PPA 代价极低。<!-- §2.4 配一张差异化对照表（行=工作类别，列=指令供给/后端语义利用/PPA 代价/是否改 ISA），末行 SEAM-V。 -->

> **与前作的重复发表声明**：参考文献 [16] 为作者团队已发表的前期工作，提出了基于 RISC-V HINT 的混合解耦前端与动态 VLIW 打包。本文不复用其图表与正文，主对比基线为原生紧耦合 Ara；本文的全部核心贡献（§4 后端可见执行包及其三项后端优化、§5 真实标量后端实现、§6–§7 的 PPA 与扩展评估）均为相对 [16] 的新增内容。

---

### 参考文献（本节 §1/§2 引用，定稿时并入全局 References）

1. J. Sevilla, L. Heim, A. Ho, T. Besiroglu, M. Hobbhahn, P. Villalobos. "Compute Trends Across Three Eras of Machine Learning," *IJCNN*, 2022.
2. A. Waterman, K. Asanović (eds.). "The RISC-V Instruction Set Manual, Vol. I: Unprivileged ISA — 'V' Standard Extension (RVV 1.0)," RISC-V International, 2021.
3. M. Cavalcante, F. Schuiki, F. Zaruba, M. Schaffner, L. Benini. "Ara: A 1-GHz+ Scalable and Energy-Efficient RISC-V Vector Processor with Multiprecision Floating-Point Support in 22-nm FD-SOI," *IEEE Trans. VLSI Systems*, 28(2):530–543, 2020.
4. M. Perotti, M. Cavalcante, N. Wistoff, R. Andri, L. Benini, et al. "A 'New Ara' for Vector Computing: An Open-Source Highly Efficient RISC-V V1.0 Vector Processor," *IEEE ASAP* / arXiv:2210.08882, 2022（及 Ara2, arXiv:2311.07493）.
5. F. Zaruba, L. Benini. "The Cost of Application-Class Processing: Energy and Performance Analysis of a Linux-Ready 1.7-GHz 64-bit RISC-V Core (CVA6/Ariane) in 22-nm FDSOI," *IEEE Trans. VLSI Systems*, 27(11):2629–2640, 2019.
6. F. Minervini, O. Palomar, O. Unsal, E. Reggiani, J. Quiroga, J. Marimon, C. Rojas, et al. "Vitruvius+: An Area-Efficient RISC-V Decoupled Vector Coprocessor for High Performance Computing Applications," *ACM TACO*, 20(2):1–25, 2023.
7. R. Espasa (Semidynamics). "Implementation of an Out-of-Order RISC-V Vector Unit," RISC-V Summit / 技术报告, 2021.
8. R. Espasa, M. Valero, J. E. Smith. "Out-of-Order Vector Architectures," *MICRO-30*, pp. 160–170, 1997.
9. Y. Gao, R. Egawa, H. Takizawa, H. Kobayashi. "An Out-of-Order Vector Processing Mechanism for Multimedia Applications," *Computing Frontiers*, pp. 233–236, 2012.
10. M. Cavalcante, M. Wüthrich, M. Perotti, S. Riedel, L. Benini. "Spatz: Clustering Compact RISC-V-Based Vector Units to Maximize Computing Efficiency," *ICCAD* / arXiv:2309.10137, 2023.
11. J. E. Smith. "Decoupled Access/Execute Computer Architectures," *ISCA* 1982 / *ACM TOCS*, 2(4):289–308, 1984.
12. J. A. Fisher. "Very Long Instruction Word Architectures and the ELI-512," *ISCA*, pp. 140–150, 1983.
13. Texas Instruments. "TMS320C66x DSP CPU and Instruction Set Reference Guide," SPRUGH7, 2010.
14. M. Payami, E. Azarkhish, I. Loi, L. Benini. "A Hybrid Instruction Prefetching Mechanism for Ultra Low-Power Multicore Clusters," *IEEE Embedded Systems Letters*, 9(4):125–128, 2017.
15. A. Waterman, K. Asanović (eds.). "The RISC-V Instruction Set Manual, Vol. I: Unprivileged ISA — HINT Instructions," RISC-V International, 2019.
16. [作者团队]. "Boosting Vector Instruction Throughput in RISC-V via a Hybrid Decoupled Architecture with VLIW-Driven Execution," *IEEE ISCAS*, 2026.（前作）
17. R. M. Russell. "The CRAY-1 Computer System," *Communications of the ACM*, 21(1):63–72, 1978.
