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
- **5. Scalar Back-End & Programming Model**：5.1 hdv_scalar_backend；5.2 task 流+hint 编码+编程模型
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
| 标量后端 | `hdv_scalar_backend` |
| Ara 向量核 | `ara` = dispatcher + sequencer + lanes + VLSU + MASKU/SLDU |
| 访存/互连 | `axi_mux` + AXI bridge + `axi_inval_filter` |

**L2 — 子模块（核心拆分表）**：
| 区域 | 子模块 (RTL 文件) |
|---|---|
| HDV 前端 | `hdv_task_interface_unit` (TIU)、`hdv_task_schedule_unit` (TSU)、`hdv_instruction_prefetch_unit` (IPU，含双 64B buffer)、`hdv_vliw_pack_unit` (VLIWPU)、`hdv_hybrid_execution_unit` (HEU)、`hdv_vec_dispatch_unit`（含 command window + operand service） |
| 标量后端 | decoder、2× simple ALU、complex lane(branch/mult/FPU/LSU)、XRF/FRF/CSR stub（`hdv_scalar_backend` 内部） |
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



## 1. Introduction（引言）

深度神经网络、科学计算、图像处理和自动驾驶等数据并行负载持续推动通用处理器向向量化架构演进。RISC-V 向量扩展（RVV）以开放、可伸缩和向量长度无关的编程模型，为不同物理向量长度下的软件可移植性与性能扩展提供了统一接口 [1]。现有 RVV 处理器通常采用紧耦合执行组织：应用级标量核负责取指、译码、控制流、地址计算和向量指令发射，向量单元作为后端执行数据并行命令。该组织接口清晰、兼容性好，但其执行效率受限于标量驱动的逐条命令流模型：向量后端虽具备较强的数据并行能力，前端供给、控制推进、后端调度和访存访问之间却缺乏能够跨前后端保留的包级执行语义。

这一限制会在不同粒度和不同阶段的实际负载中显现。短向量、循环尾部、小 batch 算子和小矩阵计算会削弱向量指令对标量控制开销的摊销能力；控制密集、不规则或访存敏感 kernel 则会因标量/向量交织、保守相关性处理和内存等待打断向量执行连续性。即使应用整体具有较大数据并行度，其内部也常包含向量粒度、控制强度和访存行为不断变化的执行阶段。因此，问题并不局限于短 AVL 场景，而是源于传统逐条供给模型难以向后端持续传递可用于调度和访存协同的包级执行单元。

已有方法主要从增强前端、解耦执行和显式并行表达等方向提升向量执行效率。一类方案通过更强的标量主核、乱序发射或复杂内存系统提高指令投放速率和延迟容忍能力，但通常伴随更高的面积、功耗和验证成本 [2]–[4]。另一类方案采用解耦执行、显式并行表达或 VLIW 风格组织，使向量侧减少对标量核逐条同步发射的依赖，并在前端形成更连续的指令供给 [5]–[8]。然而，前端供给连续性并不等价于端到端执行效率：若前端形成的包级并行性、控制边界和访存意图无法跨越后端接口保留下来，向量后端仍只能消费无包级语义的命令流，并以保守方式处理相关性、调度和访存请求。包级执行语义在前后端之间的退化，成为限制向量处理器持续吞吐提升的关键缺口。

本文提出 **SEAM-V**，一种面向 RVV 的混合解耦向量执行架构。SEAM-V 的核心思想是以 execute packet（EP）作为贯穿前后端的基本执行语义：前端通过任务级解耦、本地指令获取、标量控制与 VLIW 风格指令组织，将细粒度交织的标量/向量指令流重构为连续可供给的执行包；软件通过轻量级 HINT header 与 p-bit 显式标记包边界、局部并行性、循环属性和访存意图，使 EP 不仅是前端供给单元，也是后端可利用的语义载体。通过这一设计，SEAM-V 将传统 scalar-driven RVV instruction stream 转化为 EP-driven packet stream，从而为前端供给、后端调度和访存系统提供共同的语义基础。

进一步地，SEAM-V 将 EP 身份、请求级访存提示和循环执行状态对后端可见，使后端能够围绕 EP 进行协同执行。基于后端可见的 EP 语义，SEAM-V 在统一抽象下支持包级相关性处理、访存提前化与受限跨包执行重叠，从而在保持 RVV 软件模型和后端正确性边界不变的前提下，提高标量控制、向量计算和访存访问之间的流水并行度。本文围绕这一 EP-centric 执行模型展开设计、实现与评估，目标是在不同向量粒度和执行阶段中提升 RVV 向量处理器的持续执行效率。

本文主要贡献如下：

1. **面向 RVV 的混合解耦执行架构与 Execute Packet 生成机制。** 本文提出一种前端解耦的向量执行框架，将向量任务从标量核逐条同步发射中解耦，并通过本地指令获取、标量控制与 VLIW 风格指令组织，将细粒度交织的标量/向量指令流重构为以 execute packet（EP）为基本单位的连续供给结构，从而缓解多粒度和控制/访存敏感场景下的前端供给瓶颈。
2. **后端可见的执行包语义贯通机制。** 本文将 EP 从前端打包结果提升为贯穿前后端的统一执行语义，使 EP 身份、请求级访存提示和循环执行状态能够跨越解耦边界对向量后端可见，在不修改 RVV ISA 的前提下保持包级执行语义的连续性，避免其在后端退化为普通命令流。
3. **基于 EP 语义驱动的后端协同执行机制。** 本文利用后端可见的 EP 语义，使后端围绕执行包进行相关性裁剪、访存延迟隐藏与受限跨包执行重叠，在保证依赖关系和内存定序正确性的前提下，提高向量计算、标量控制与访存访问之间的流水并行度。
4. **完整系统实现与物理级评估。** 本文完成 SEAM-V 的端到端 RTL 实现，并通过综合与物理设计流程评估其面积、功耗和能效开销；同时结合微基准与真实向量工作负载，系统量化前端解耦、执行包语义贯通和后端协同优化带来的性能与能效收益。

全文组织如下：§2 回顾 RVV、向量后端执行模型以及相关工作；§3 介绍 SEAM-V 硬件架构，包括前端解耦、EP 形成、后端可见语义通路和 EP-driven 后端协同；§4 介绍编程模型与软件接口，说明 task、HINT header、p-bit 契约和访存意图如何表达硬件可消费的 EP 语义；§5 给出实验方法、性能评估、消融分析、敏感性分析和物理级代价评估；§6 讨论 SEAM-V 的适用边界、软件标注和扩展方向；§7 总结全文。

## 2. Background and Related Work（背景与相关工作）

### 2.1 RVV and Spatio-Temporal Vector Execution

SIMD 与向量体系结构都利用数据级并行性，但二者暴露和组织并行性的方式不同。固定宽度 SIMD 通常以架构可见的数据宽度约束单次操作的元素规模；相比之下，向量处理器将一条向量指令组织为由运行时状态决定长度的元素流，并在空间 lane 与时间 beat 上共同展开。对于 RVV，这一展开过程由 `vl`、SEW、LMUL、mask、访存模式和物理 lane 数共同决定，可能持续多个周期，并涉及多次寄存器访问、lane 流水推进和访存请求。因此，RVV 后端并不是简单的固定宽度 SIMD datapath，而是负责执行进度、结构冲突、访存返回和内存定序的有状态向量执行后端。

这一时间-空间展开特性构成了 SEAM-V 的基本设计前提。执行包可以在前端表达局部并行性、控制边界和访存意图，但不能完全静态决定向量指令在后端的真实执行过程。真实的依赖关系、寄存器一致性、访存返回顺序和内存定序仍必须由向量后端动态维护。因此，面向 RVV 的执行包机制不应将后端静态化为 VLIW/SIMD 式执行阵列，而应在保留后端正确性边界的前提下，将前端可知的包级语义传递给后端利用。

### 2.2 Scalar-Driven Execution and Semantic Gap

现有许多 RVV 处理器采用紧耦合组织：应用级标量核负责取指、译码、控制流、地址计算和向量指令发射，向量单元逐条接收并执行向量命令。该组织接口清晰、兼容性好，但前端按标量指令流推进，后端按运行时状态展开执行，二者之间通常只传递普通向量命令，而缺少包级边界、局部并行性、循环上下文和访存意图等可供后端消费的 EP 语义。

这种语义缺失在向量粒度、控制强度和访存行为频繁变化的 workload 中尤为明显。其根本问题并非某一类场景的局部低效，而是标量驱动的逐条命令流难以持续向后端提供可用于调度和访存协同的包级执行信息。换言之，即使前端能够更快地投放指令，若后端仍只能看到无 EP 语义的命令流，端到端执行效率仍会受到保守相关性处理、访存等待和调度不连续性的限制。这一前端结构化信息在后端接口处退化的问题，本文称为前后端执行语义鸿沟。

### 2.3 Decoupling, Packetization, and Backend Management

已有研究主要从增强前端、解耦执行、显式并行表达和后端动态管理等方向提升向量执行效率。一类方案采用更宽发射、乱序执行、寄存器重命名和复杂内存系统，以提高指令投放速率和延迟容忍能力 [2]–[4]。这类方案通用性强，但通常伴随更高的面积、功耗和验证复杂度。另一类方案采用解耦执行，将控制、访存或向量计算从主核逐条同步发射中分离，通过队列化接口和局部执行上下文提高供给连续性 [5], [6]。

与解耦执行互补，VLIW/EPIC 及部分 DSP 架构通过软件或编译期标记显式暴露指令级并行性，将可并行操作组织为执行包，以降低硬件动态依赖发现压力 [7], [8]。这类 packetized execution 在执行资源、延迟和依赖关系能够被充分建模时较为有效。然而，对于 RVV，执行包不能直接替代后端动态管理：向量指令会在后端展开为多拍元素流，真实执行进度、寄存器冲突、访存返回和内存顺序仍需由 sequencer、scoreboard 和访存定序逻辑维护。

因此，现有方向分别改善了前端供给、显式并行表达或运行时重叠能力，但通常没有将前端形成的包级信息作为后端可消费的统一语义保留下来。若 EP 身份、包边界、包内并行性、循环状态和访存意图不能跨越后端接口，后端仍需按无包级语义的逐条命令流进行保守处理。SEAM-V 关注的正是这一缺口：不是用静态打包取代后端动态管理，而是让后端在自身正确性框架内利用 EP 语义。

### 2.4 Positioning of SEAM-V

SEAM-V 位于解耦向量执行、显式执行包和向量后端动态调度三类工作的交汇处。它通过前端解耦与 VLIW 风格组织形成 EP，但不将 EP 静态化为 VLIW/SIMD 调度结果；它保留向量后端作为 RVV 时间-空间展开执行的正确性维护者，同时使 EP 身份、循环状态和请求级访存提示对后端可见，使其能够在现有动态调度框架内消费包级语义。

相对于前期工作 [16]，本文保留其前端解耦与执行包形成思想，并将其作为 SEAM-V 的前端基础；在此基础上，本文进一步提出后端可见的 EP 语义贯通机制、EP-driven 后端协同执行机制，以及完整系统实现与物理级评估。由此，SEAM-V 区别于仅提升供给的解耦设计、仅在前端暴露并行性的 packetized execution，以及仅依赖运行时推断的后端优化机制。其核心定位是在保持 RVV 软件模型和后端正确性边界的前提下，建立从 EP 生成、语义贯通到后端消费的端到端执行路径。

## 3. SEAM-V Hardware Architecture（SEAM-V 硬件架构）

前两节指出，RVV 向量指令会在后端进行时间-空间展开，因此向量后端必须保留依赖管理、寄存器状态维护、访存定序和多拍执行控制能力；与此同时，传统标量驱动的逐条命令流又难以向后端传递包级执行语义。SEAM-V 的硬件架构围绕这一矛盾展开：前端将标量/向量交织指令流组织为 execute packet（EP），并将 EP 语义跨越解耦边界传递至向量后端；后端仍作为 RVV 执行正确性的维护者，但能够利用 EP 语义减少不必要的保守性并增强调度协同。

图 3 展示 SEAM-V 的整体微架构。系统在 host 与向量后端之间引入一条混合解耦执行路径，包括任务接口、本地指令供给、VLIW 风格 EP 形成、混合标量/向量分流、向量派发，以及后端可见 EP 语义通路。该路径将传统 scalar-driven RVV instruction stream 重构为 EP-driven packet stream：前端负责显式化包边界、局部并行性、循环上下文和访存意图；后端负责管理真实向量执行进度、寄存器相关性和内存顺序，并在此基础上消费 EP 语义。

【图 3：SEAM-V Overall Architecture】

### 3.1 Architecture Overview

SEAM-V 的硬件流水可概括为五个阶段。首先，host 以 task 粒度提交向量 kernel，任务接口和调度逻辑将其转化为本地执行上下文。其次，本地指令供给单元从任务入口取指，并在循环阶段复用已获取的指令流，为前端打包提供稳定的局部窗口。第三，VLIW 打包单元根据 HINT header 与 p-bit 将标量/向量交织指令组织为 EP。第四，混合执行单元将 EP 分解为 scalar slice 和 vector slice，分别送入集成标量后端和向量派发路径。最后，向量派发单元将 vector slice 中的向量指令转化为后端请求，并将 EP 语义绑定到请求元数据中。

这一组织形成了明确的前后端分工。前端不再只是加速取指或缓存指令，而是将程序中的局部结构显式化为 EP；后端不被静态打包取代，而是在保留 RVV 时间-空间展开执行所需正确性机制的同时，利用 EP 语义进行更积极的相关性处理、访存提前化和执行重叠。换言之，SEAM-V 的核心不是增加若干孤立优化模块，而是建立一条从 EP 生成到 EP 消费的端到端语义路径。

### 3.2 Front-End Decoupling and Instruction Supply

SEAM-V 以 task 为粒度启动向量 kernel。Host 只提交任务入口和控制信息，任务启动后，本地前端独立推进取指、标量控制和 EP 形成，从而将 host 的职责从细粒度指令驱动转化为粗粒度任务提交。该设计直接缓解了紧耦合 RVV 中标量核长期处于向量指令供给关键路径的问题。

本地指令供给单元以 fetch packet 形式向 VLIW 打包单元提供输入。对于循环 kernel，前端根据标量后端解析出的分支重定向推进取指，并利用 header 中的 loop marker 保留软件可见的循环边界信息。该机制减少循环体重复取指，并为 EP 形成提供稳定、连续的局部指令窗口，使程序中的局部并行性、控制边界和访存意图能够持续暴露给硬件。

### 3.3 Execute Packet Formation

EP 形成是 SEAM-V 前端的核心。软件通过 HINT header 提供 packet 级上下文，通过 p-bit 描述相邻指令是否允许进入同一 EP；硬件则在 logical packet 内扫描 instruction slots，并根据 p-bit、控制/系统边界、依赖断点和最大发射宽度生成 EP。HINT/p-bit 并不是强制并行执行命令，而是向硬件提供可利用的包级语义；硬件仍可因控制边界、issue width、后端压力或安全条件切分 EP。

图 4 展示 HINT header、p-bit、slot scanning 与 EP output 的关系。HINT header 定义 packet 级上下文，包括 logical packet 宽度、跨 packet 打包许可、循环标记和访存提示；p-bit 定义 packet 内部的连接关系；VLIW 打包单元根据这些信息从线性指令流中形成一个或多个 EP。完整 HINT header 编码和软件契约将在 §4 中给出。

【图 4：HINT Header and EP Formation】

每个 EP 同时承担三种角色。第一，EP 是前端供给单元，定义一组可共同进入后续流水的标量/向量指令。第二，EP 是局部并行性的显式载体，为后端相关性裁剪提供依据。第三，EP 携带循环上下文和访存意图，为后端访存提前化提供语义来源。因此，SEAM-V 将 EP 同时作为前端组织单元和后端协同执行的共同语义对象。

### 3.4 Hybrid Execution and Back-End-Visible Propagation

混合执行单元接收 EP 后，将其划分为 scalar slice 和 vector slice。Scalar slice 由集成标量后端执行，用于循环控制、分支解析、地址计算、标量寄存器更新和任务推进；vector slice 进入向量派发路径，由派发逻辑读取所需标量操作数并转换为后端请求。由于 RVV 后端会继续管理向量指令的多拍展开，前端推进不以整条向量指令完成为条件，而以 vector slice 的标量操作数已被派发逻辑捕获、必要的 `vset` 标量可见写回已完成为条件。该事件只表示向量 slice 已进入后端管理域，并不表示向量指令已经执行完成。

为支持 EP 粒度的流水重叠，HEU 维护 current EP 与 buffered EP 两级状态，并为包含 vector slice 的 EP 分配轻量级 `ep_id`。`ep_id` 与请求级访存提示随向量请求进入后端，使后端能够区分不同 EP 的请求归属和访存提前化意图。受限的 buffered vector early issue 允许后续 EP 的 vector slice 在满足依赖和内存顺序约束时提前进入派发路径，从而将标量控制、向量计算和访存等待在 EP 粒度上重叠。

图 5 展示 current EP、buffered EP、scalar/vector slice 和 early-issue 安全条件。该机制只允许 memory-order-safe 的跨 EP 重叠：若 current EP 含未解析分支、标量访存或其他可能影响内存顺序的操作，或者 buffered vector slice 依赖 current EP 的写结果，则提前发射被阻止。因此，SEAM-V 的 cross-EP overlap 是受限执行重叠，而不是任意跨包乱序。

【图 5：Hybrid Execution and Safe Cross-EP Overlap】

向量派发单元将 vector slice 序列化为后端可接受的逐条向量请求。由于后端接口仍以单条向量命令为粒度，VDU 使用 command window 保持每条请求与其所属 EP 的对应关系，并复用既有 accelerator request metadata path 传递 EP 语义。当前实现中，向量请求元数据携带 `ep_id`、`prefetch_disable` 与 `prefetch_mode`；后端 dispatcher 将其转化为内部 HDV hint，供 sequencer 和 VLSU 消费。命令类别和 EP 内最后一条向量指令等信息主要用于 VDU 内部响应匹配、写回路由和 EP acknowledge，并不作为后端访存幅度选择的语义来源。

除 per-request metadata 外，SEAM-V 还向后端提供 loop-active 等全局上下文。Loop-active 指示前端当前处于循环体执行阶段；它与每条请求携带的 EP 身份和访存提示共同构成后端可见 EP 语义，使后端能够识别命令所属 EP、循环状态和访存提前化意图。由此，后端不再只看到无结构的向量命令流，而是获得可用于相关性、访存和调度协同的包级信息。

### 3.5 EP-Driven Backend Cooperation

后端可见 EP 语义被三个路径消费：相关性处理、访存提前化和跨 EP 执行重叠。三者并不是孤立优化，而是同一 EP 语义在不同后端子系统中的使用方式。图 6 展示 EP 语义在 sequencer、VLSU 和 HEU/VDU/后端执行路径中的消费过程。

【图 6：Back-End-Visible EP Consumption】

首先，sequencer 利用 `ep_id` 进行 EP-aware dependency handling。传统 sequencer 需要根据在飞命令维护 RAW、WAR 和 WAW 检查；SEAM-V 在在飞向量指令状态中记录 EP 身份，并在新请求到来时识别同包候选冲突。对于 p-bit 契约下被标记为同 EP、且软件保证不会破坏 RVV 正确性的候选冲突，sequencer 可将对应在飞指令从保守 hazard 检查集合中排除。该机制不移除 scoreboard，也不绕过跨 EP 或真实数据依赖，而是在后端动态管理框架内利用前端提供的包级独立性信息减少假相关阻塞。

其次，VLSU 利用请求级访存提示与 loop-active 上下文进行 EP-driven memory anticipation。`prefetch_disable` 显式决定是否关闭预取；在未关闭时，`prefetch_mode` 选择 1X、2X、4X 或 8X 的预取幅度。将访存提示绑定到向量请求，而非仅依赖瞬时 header 信号，可以避免前端推进、packet 间隙或请求排队导致的语义错位。地址生成逻辑结合预取幅度、队列占用和在途请求信用进行流控，避免预取请求压制 demand load/store。这样，软件和前端已知的循环访存意图被转化为后端可执行的访存提前化行为。

最后，HEU 的 buffered vector early issue 与 VDU command window 共同支持跨 EP 执行重叠。后续 EP 的 vector slice 可在满足依赖和内存顺序约束后提前进入后端；后端则根据 `ep_id` 区分请求归属，并在 sequencer、VLSU 和响应路径中维护正确状态。该机制使标量控制、向量计算和访存访问能够在 EP 粒度上形成时空重叠，而不是严格等待前一 EP 的所有事件完成后再启动下一 EP。

综上，SEAM-V 的硬件架构围绕 EP 构建了一条端到端语义路径：前端通过任务级解耦和 VLIW 打包生成 EP，混合执行单元以 EP 为粒度组织标量/向量分流和受限跨包重叠，向量派发单元将 EP 语义绑定到后端请求，向量后端则在保留 RVV 动态正确性管理的前提下消费这些语义。下一节将从软件侧介绍 task、HINT header、p-bit 契约和访存意图如何表达这些硬件可消费的 EP 语义。

## 4. Programming Model and Software Interface（编程模型与软件接口）

前一节说明了 SEAM-V 如何在硬件中生成、传递并消费 EP 语义。本节从软件侧定义这些语义如何表达。SEAM-V 的软件接口遵循两个原则：第一，不改变 RVV 指令语义和既有向量 kernel 的计算模型；第二，将软件可知的局部并行性、控制边界和访存意图以轻量级标注形式暴露给硬件。由此，SEAM-V 在普通 RVV 编程模型之上建立显式的软件-硬件契约，使硬件能够利用程序结构，而不依赖完全动态的后端推断。

### 4.1 Task-Level Execution Model

SEAM-V 以 task 为基本执行单元。主程序负责数据准备、参数传递和结果校验，热点 RVV kernel 被封装为 SEAM-V task 并提交给硬件执行。Task 内部仍使用标准 RVV 指令描述向量计算，但其取指、标量控制、向量派发和 EP 形成由 SEAM-V 本地前端推进。相比 host 逐条投放向量指令的紧耦合模式，task-level execution 将软件接口提升到 kernel 粒度，降低 host 参与度，并为前端包级组织提供稳定执行上下文。

这一模型将软件侧职责划分为两层：算法层仍以普通 RVV kernel 表达数据并行计算；执行结构层则通过 HINT header、p-bit 和访存提示表达可供硬件利用的包级语义。换言之，SEAM-V 并不要求软件显式管理向量后端状态，而是要求软件在可确定的局部范围内描述哪些指令可被组织为 EP、哪些位置构成控制或访存边界，以及哪些访存流具有可提前化的规律。Task 的结束由标量后端识别的 task-end 指令触发；本文示例采用 `ret` 表示任务返回。

### 4.2 HINT Header Format and EP Annotation

SEAM-V 使用 RISC-V HINT 形式的 `lui x0, imm20` 描述 EP 形成规则。该指令不改变普通 RISC-V architectural state；在 SEAM-V 中，其立即数字段被解释为 packet 级元信息。表 1 给出当前 HINT header 格式。

【表 1：HINT Header Encoding】

| 字段               | 位范围         | 含义                                                         |
| ------------------ | -------------- | ------------------------------------------------------------ |
| `pbits`            | `imm20[12:0]`  | 相邻 16-bit slot 是否允许继续并入同一 EP                     |
| `packet256`        | `imm20[13]`    | 当前 logical packet 是否扩展为 256-bit                       |
| `cross`            | `imm20[14]`    | 当前 logical packet 尾部 EP 是否允许跨入下一 logical packet  |
| `loop_start`       | `imm20[15]`    | 循环体起始标记                                               |
| `loop_end`         | `imm20[16]`    | 循环体结束标记                                               |
| `prefetch_mode`    | `imm20[18:17]` | 预取幅度；在 `prefetch_disable=0` 时，`00`=1X，`01`=2X，`10`=4X，`11`=8X |
| `prefetch_disable` | `imm20[19]`    | 显式关闭 prefetch                                            |

HINT header 定义 packet 级上下文，p-bit 定义 packet 内部的连接关系。其中，`packet256` 扩大 VLIW 打包单元的 logical packet 扫描窗口；`cross` 则允许当前 logical packet 的尾部 EP 跨越取指包边界，与下一 logical packet 开头继续形成同一个 EP。二者均不改变单个 EP 的硬件最大发射宽度；实际 EP 宽度仍受 issue width、p-bit、dependency break、控制/系统边界和后端安全条件约束。

访存提示由 `prefetch_disable` 和 `prefetch_mode` 共同定义。当 `prefetch_disable=1` 时，该 packet 显式关闭预取；当 `prefetch_disable=0` 时，`prefetch_mode` 编码预取幅度，分别表示 1X、2X、4X 和 8X。该设计将“是否启用预取”和“预取距离选择”解耦，避免将 `00` 同时用作关闭语义和最小预取幅度语义。

p-bit 不是强制并行执行命令，而是一种安全性契约：当软件将多条指令连接到同一 EP 中时，表示这些指令在该 packet 语义下不存在会因后端 EP-aware 相关性裁剪而破坏正确性的依赖、控制或访存边界。硬件仍可根据 issue width、控制边界、后端压力和安全条件切分 EP。因此，EP annotation 是可被硬件利用的结构化信息，而不是替代后端正确性管理的静态调度结果。

该契约同时支持保守退化。若软件无法确认相邻指令是否可以安全合并，应切断对应 p-bit，使其进入不同 EP；若存在分支、系统指令、内存顺序约束或未解析依赖，也应形成 EP 边界。保守标注不会改变功能正确性，只会减少硬件可利用的包级语义。

### 4.3 HDV Kernel Example

Listing 1 给出一个简化的 HDV 标注向量 kernel 片段，用于说明 HINT header、p-bit、`packet256`、cross-packet packing 以及 loop/prefetch annotation 的关系。示例使用伪宏 `HDV_HINT` 表达软件可见标注语义，而非完整可编译 kernel；其中 `P_SPLIT` 表示 logical packet 内部仍按照真实依赖、控制边界和后端安全条件切分为多个 EP，不表示将 header 覆盖范围内的所有业务指令强制合并为同一 EP。示例中的 `prefetch_mode=1X` 隐含 `prefetch_disable=0`。

【Listing 1：Simplified HDV-Annotated Vector Kernel】

```asm
loop:
    HDV_HINT pbits=P_SPLIT, packet256=1, cross=1, loop_start=1, prefetch_mode=1X
    vsetvli   t0, a0, e32, m1, ta, ma
    vle32.v   v0, (a1)
    vle32.v   v1, (a2)
    sub       a0, a0, t0
    slli      t1, t0, 2
    add       a1, a1, t1
    add       a2, a2, t1

    HDV_HINT pbits=P_SPLIT, loop_end=1, prefetch_mode=1X
    vfadd.vv  v2, v0, v1
    vse32.v   v2, (a3)
    add       a3, a3, t1

    HDV_HINT pbits=P_NONE, prefetch_disable=1
    bnez      a0, loop
    ret
```

该示例展示了三类软件意图。第一，`packet256` 允许一个 HINT header 覆盖更大的 logical packet，从而摊销 header 的静态代码空间和取指开销；logical packet 内部仍可通过 p-bit 切分为多个 EP，以保留真实依赖、控制边界和硬件安全条件。第二，`cross` 允许 logical packet 尾部 EP 在满足 p-bit 和安全条件时跨入下一 logical packet 开头继续打包，从而减少因取指包边界造成的 EP 人为截断。第三，loop 标记和 `prefetch_mode=1X` 将循环上下文与流式 unit-stride 访存意图暴露给后端。实际 kernel 可根据依赖关系、控制边界和访存模式选择更保守或更积极的 EP 标注。

### 4.4 Memory Intent and Correctness Boundary

Prefetch annotation 描述循环体内规则 unit-stride load 的访存提前化意图。软件首先通过 `prefetch_disable` 显式决定是否关闭预取；在启用预取时，再通过 `prefetch_mode` 选择 1X、2X、4X 或 8X 的预取幅度，使后端能够根据循环访存步长提前发起后续访问。对于不规则访存、gather/scatter、短促执行阶段或难以由固定幅度建模的访问模式，软件可关闭该提示，使后端退化为普通 demand-driven 访存执行。

Prefetch annotation 是性能提示而非正确性条件。程序 RVV 语义不依赖预取是否命中或是否实际发出；硬件仍负责维护队列资源、访存定序、预取流控和循环退出时的状态清理。由此，SEAM-V 能够在规则流式访问中利用软件暴露的访存意图隐藏延迟，同时在访问模式不匹配时保持保守、正确的执行行为。

SEAM-V 保持 RVV 软件模型不变。EP、p-bit、loop 标记、`prefetch_disable` 和 `prefetch_mode` 均为 SEAM-V 微架构解释的信息，而不是新的 RVV 指令语义。软件负责遵守 EP annotation contract，不将存在未解决依赖、控制不确定性或内存顺序风险的指令错误合并；硬件负责维护 RVV 后端的动态依赖管理、寄存器一致性和内存定序。保守标注不会影响功能正确性，只会减少可利用的包级语义。由此，SEAM-V 在不改变算法语义的前提下，为 RVV kernel 提供了可被硬件消费的显式执行结构。



## 5. Experimental Methodology and Evaluation（实验方法与评估）

本节从性能、机制贡献、微结构行为和物理代价四个层面评估 SEAM-V。实验围绕 EP-centric execution 的完整路径展开：前端是否能够稳定生成 EP，EP 语义是否能够跨越前后端边界保留，后端是否能够利用这些语义降低保守阻塞、提前访存并增加执行重叠。除特别说明外，所有性能结果均归一化到紧耦合 RVV baseline。

### 5.1 Experimental Setup and Workloads

本文基于 RTL 仿真、kernel sweep 和物理级实现流程进行评估。比较对象包括紧耦合 RVV baseline（`T`）和完整 SEAM-V（`H4`）。`H4` 启用 task-level decoupling、local instruction supply、EP formation、backend-visible EP、EP-aware hazard bypass、EP-driven prefetch 和 memory-order-safe cross-EP overlap。为分离各机制贡献，本文进一步构造逐级消融配置：`H_base` 仅启用前端解耦与 EP 生成，`H1` 加入同 EP 相关性裁剪，`H2/H3` 加入预取控制，`H4` 为完整设计。表 X 总结实验配置、向量后端参数、存储系统设置和消融开关。

【表 X：Experimental Setup and Evaluated Configurations】

Workload 覆盖三类执行模式。AVL sweep kernels 用于观察不同向量粒度下的执行效率；BLAS/GEMM kernels 用于评估计算密集和不同 LMUL 配置下的行为；fixed-size kernels 覆盖卷积、stencil、softmax、分子动力学以及稀疏/不规则访存片段，用于验证 SEAM-V 在更复杂执行阶段中的适用性。所有统计仅包含功能检查通过的数据点；失败或调试配置不进入几何平均值。本文报告 task cycles、speedup、cycles per element、cycles per MAC、sequencer stalls、EP bypass 次数、prefetch hit rate、backpressure、area、power、energy 和 EDP。

当前 hdv sweep 数据已完成基础一致性检查。有效数据点满足向量请求 push/pop 平衡，任务结束采样点无遗留向量 busy 状态，可用于性能趋势和微结构计数器分析。对于尚未完成的 main/hdv 对齐实验，正文仅保留统计占位，最终数值以后续相同 workload、相同后端配置和相同 memory model 下的成对实验为准。

### 5.2 Overall Performance

图 X 给出完整 SEAM-V 相对于紧耦合 RVV baseline 的归一化性能。Across all evaluated workloads，`H4` 实现 `[待填]` 的几何平均加速比；在 AVL sweep、BLAS/GEMM 和 fixed-size kernels 中分别达到 `[待填]`、`[待填]` 和 `[待填]`。该结果用于验证 SEAM-V 的收益是否跨越不同向量粒度、访存模式和计算强度，而不是集中于单一短向量 microbenchmark。

【图 X：Normalized Performance over Tight-Coupled RVV Baseline】

已有 hdv 数据显示，SEAM-V 在流式 AVL kernels 上能够维持稳定的单位元素执行成本。以典型 unit-stride workloads 为例，`vsaxpy`、`vscopy` 和 `vvaddint32` 的 cycles per element 在 AVL 增大后基本收敛，说明本地指令供给和 EP 形成可以支撑连续执行。相比之下，`vsdot`、`vsdwt` 等规约或访存模式更复杂的 kernel 具有更高单位成本，表明其瓶颈更多来自真实依赖、访存结构或后端资源压力，而非单纯前端供给不足。

【图 X：AVL Sweep and Per-Element Efficiency】

BLAS/GEMM 结果采用 cycles per MAC 归一化，以避免矩阵规模差异掩盖结构趋势。GEMV/SYMV 类 kernel 主要反映向量配置和短任务粒度下的执行效率；GEMM、SYRK 和 TRSM 类 kernel 则体现计算密集、访存复杂或依赖更强场景下的收益边界。Fixed-size kernels 直接报告 task cycles 和 normalized speedup，用于说明 SEAM-V 在真实应用片段中的端到端效果。

总体来看，SEAM-V 的收益来源随 workload 改变。规则 unit-stride kernel 主要受益于连续供给和 EP-driven prefetch；标量/向量交织明显的 kernel 更依赖前端解耦和跨 EP 执行重叠；规约、强依赖或后端饱和的 kernel 收益较小。该趋势说明，SEAM-V 提升的是多阶段执行中的持续吞吐，而不是单个 datapath 的峰值计算能力。

### 5.3 Ablation Study

图 X 展示 `T → H_base → H1 → H2/H3 → H4` 的逐级消融。`H_base` 衡量前端解耦和 EP 生成的供给收益；`H1` 衡量同 EP 相关性裁剪对 sequencer 保守阻塞的影响；`H2/H3` 衡量 EP-driven prefetch 对访存等待的隐藏能力；`H4` 衡量 cross-EP overlap 对标量控制、向量计算和访存访问重叠的额外贡献。相对于 `H_base`，完整后端协同进一步带来 `[待填]` 的平均性能提升，其中 hazard bypass、prefetch 和 overlap 分别贡献 `[待填]`、`[待填]` 和 `[待填]`。

【图 X：Ablation Study of SEAM-V Mechanisms】

消融样例选择覆盖不同瓶颈类型，包括流式访存、规约依赖、访存/写回压力、计算密集和真实应用片段。若 `H_base` 已显著优于 `T`，说明任务级解耦、本地供给和 EP 形成有效缓解了标量驱动供给瓶颈；若 `H1–H4` 继续带来增益，则说明 EP 语义不仅在前端形成，而且能够在 sequencer、VLSU 和执行控制路径中被后端实际消费。

该实验也是区分 SEAM-V 与普通前端优化的关键。仅提高前端供给并不能解决后端保守相关性、访存等待和跨包重叠不足等问题；只有当 EP identity、loop context 和 memory intent 被保留下来，后端才能围绕同一包级语义进行协同。因此，Full SEAM-V 的收益应理解为前端组织和后端消费共同作用的结果。

### 5.4 Microarchitectural Analysis

图 X 汇总代表性 kernel 的后端计数器，包括 sequencer stalls、EP bypass、prefetch request/hit、operand wait 和 backpressure。Sequencer 统计用于验证 EP-aware dependency handling：当 p-bit contract 暴露同 EP 内可安全处理的候选冲突时，`seq_ep_bypass` 增加，保守 RAW/WAR/WAW 阻塞应相应降低。该结果说明 SEAM-V 并未移除 scoreboard，而是在后端正确性边界内减少不必要的假相关阻塞。

【图 X：Sequencer Stall and EP Bypass Breakdown】

Prefetch 统计用于验证 EP-driven memory anticipation。当前数据表明，规则 unit-stride kernels 能获得完整或近完整的 prefetch 命中；`dropout` 类 kernel 保留冷启动带来的少量缺口；而 `vsdwt` 这类访存模式不匹配样例虽然产生 prefetch 请求，却无法转化为 demand 命中。这一结果说明 prefetch mode 是性能提示而非正确性条件：访问模式稳定时，它提高访存提前化能力；访问模式不匹配时，系统仍可退化为 demand-driven 执行。

【图 X：Prefetch Usefulness and Memory Behavior】

后端 backpressure 和 operand wait 用于解释瓶颈迁移。当 SEAM-V 缓解前端供给空洞后，部分 workload 的主要限制会转向向量后端队列、访存端口、写回路径或真实数据依赖。例如，规约类 kernel 的单位成本更高，主要受依赖链约束；访存/写回压力较强的 kernel 则可能在 Ara backpressure 上表现更突出。因此，本文同时报告 speedup 和微结构计数器，避免将所有性能变化简单归因于单一机制。

### 5.5 Sensitivity and Boundary Cases

图 X 给出不同 AVL、LMUL/GEMM 配置和 memory-latency 条件下的敏感性结果。AVL sweep 用于观察向量粒度变化时的供给与后端利用率；LMUL/GEMM sweep 用于分析 RVV 时间-空间展开粒度变化下的计算效率；memory-latency sweep 用于评估 EP-driven prefetch 和 cross-EP overlap 在不同访存压力下的鲁棒性。尚未完成的 sensitivity 数据在图中保留占位，正文不据此作最终结论。

【图 X：Sensitivity to Vector Granularity and Memory Behavior】

该组实验强调两点。第一，SEAM-V 不是短 AVL 专用优化；短向量更容易暴露前端供给和控制开销，但 EP 语义贯通的作用贯穿不同向量粒度。第二，SEAM-V 的收益依赖可利用的局部并行性和可预测访存意图。对于强串行依赖、不规则 gather/scatter、访存提示与真实访问模式不匹配或后端已充分饱和的 workload，EP 语义仍保持正确性，但可转化为性能收益的空间有限。

### 5.6 Physical Cost and Energy Efficiency

本文采用 TSMC 28nm HPC+ 工艺进行物理级评估，典型条件为 TT/0.9V/25°C，目标频率为 1GHz。综合和功耗评估基于 Synopsys Design Compiler 与 SAIF switching activity；后端物理实现报告布局布线后的面积、时序和功耗。若 post-PnR 频率与 baseline 不同，性能和能量结果按实际频率归一化。

【表 X：Physical Implementation Setup】

SEAM-V 的新增硬件主要包括 task interface、local instruction supply、VLIW pack unit、HEU control、VDU command window、EP metadata path、sequencer EP-aware logic 和 VLSU prefetch support。表 X 给出模块面积和功耗拆分。Full SEAM-V 的总面积开销为 `[待填]`，功耗变化为 `[待填]`，关键路径变化为 `[待填]`。该表重点说明新增代价集中在 EP 语义生成、传递和消费路径，而不是扩大向量 datapath。

【表 X：Post-PnR Area and Power Breakdown】

能量评估综合考虑执行周期和功耗。本文使用 task cycles、实际时钟周期和 post-PnR power 计算单任务能量，并报告 EDP 以刻画性能/功耗权衡。Full SEAM-V 的平均 energy reduction 为 `[待填]`，EDP reduction 为 `[待填]`。若物理结果显示新增控制和缓冲逻辑开销可控，同时执行周期显著减少，则说明 backend-visible EP 能够以较低硬件代价提升 RVV 向量处理器的性能与能效。

【图 X：Energy and EDP Comparison】



## 5. Experimental Methodology and Evaluation（实验方法与评估）前版本

本节从性能、机制贡献、适用范围和硬件代价四个方面评估 SEAM-V。实验旨在回答三个问题：第一，EP-centric execution 是否能够提升 RVV 向量处理器在多粒度 workload 下的持续执行效率；第二，前端解耦与 EP 生成、后端可见 EP 语义贯通以及 EP-driven 后端协同分别贡献多少收益；第三，这些性能与能效收益是否能够以可控的面积和功耗开销获得。

### 5.1 Experimental Setup and Workloads

本文基于 RTL 仿真和物理级评估流程对 SEAM-V 进行实验。所有性能实验均在相同向量后端配置、相同存储系统模型和相同 workload 输入下进行，比较对象包括紧耦合 RVV baseline、仅启用前端解耦与 EP 形成的 SEAM-V-FE，以及启用后端可见 EP 和全部 EP-driven 后端协同机制的 Full SEAM-V。对于机制分析，本文进一步构造逐项打开 hazard bypass、EP-driven prefetch 和 cross-EP overlap 的消融配置。

【表 X：Experimental Setup and Evaluated Configurations】

Workload 覆盖三类执行特征。第一类是向量粒度可调的 microbenchmarks，用于分析不同 AVL、循环粒度和标量/向量交织程度下的执行效率。第二类是 BLAS/GEMM 类计算 kernel，用于评估 SEAM-V 在计算密集与不同向量配置下的表现。第三类是真实应用片段，包括卷积、迭代 stencil、分子动力学、softmax 和稀疏/不规则访存相关 kernel，用于验证 SEAM-V 是否能够覆盖更复杂的执行阶段。所有统计均只包含功能检查通过的测试点；失败或调试中的配置不进入性能几何平均值。

本文报告任务周期数、相对 speedup、每元素周期、每 MAC 周期、向量后端利用率、sequencer stall、EP bypass 次数、prefetch 请求与命中率、后端 backpressure，以及面积、功耗、能量和能效指标。除特别说明外，所有性能结果均归一化到紧耦合 RVV baseline。

### 5.2 Overall Performance

图 X 给出 Full SEAM-V 相对于紧耦合 RVV baseline 的总体性能。SEAM-V 通过任务级解耦降低 host 逐条驱动压力，通过 EP 形成提高前端供给连续性，并通过后端可见 EP 使向量后端能够消费包级语义。Across all evaluated workloads，Full SEAM-V 实现平均 `[TODO: geomean speedup]` 的性能提升，并在 `[TODO: best-performing kernel]` 上达到最高 `[TODO: max speedup]`。

【图 X：Overall Performance of Full SEAM-V】

不同 workload 类别体现出不同收益来源。流式 unit-stride kernel 主要受益于 EP-driven memory anticipation；标量/向量交织明显的 kernel 更依赖前端解耦和跨 EP 执行重叠；计算密集 kernel 的收益则取决于向量后端是否已接近饱和，以及 EP 是否能减少供给间隙和保守调度。真实应用片段的结果表明，SEAM-V 的收益并不局限于短 AVL 场景，而来自不同向量粒度、控制强度和访存行为阶段中的持续执行效率提升。

为了更清楚地区分 workload 行为，图 X 按 workload 类别汇总归一化性能。对于 AVL sweep kernel，本文报告不同向量长度下的 speedup 趋势；对于 BLAS/GEMM kernel，本文使用每 MAC 周期作为归一化指标；对于固定规模真实 kernel，本文直接报告任务周期和相对 speedup。该分类有助于避免单一平均值掩盖 SEAM-V 在不同执行模式下的效果差异。

### 5.3 Ablation Study

图 X 展示 SEAM-V 的消融结果。消融配置按照本文贡献逐步展开：Baseline 表示传统紧耦合 RVV 执行；SEAM-V-FE 仅包含任务级解耦、本地指令供给和 EP 形成；SEAM-V-BEV 在此基础上加入后端可见 EP 语义通路；后续配置分别打开 EP-aware hazard bypass、EP-driven prefetch 和 cross-EP overlap；Full SEAM-V 启用全部机制。

【图 X：Ablation of SEAM-V Mechanisms】

SEAM-V-FE 用于量化前端解耦与 EP 生成的基础收益。该配置减少 host 逐条发射和重复取指带来的供给间隙，并将标量/向量交织指令流组织为可连续推进的执行包。SEAM-V-BEV 进一步验证 EP 语义贯通的必要性：当 EP 身份、循环上下文和访存意图能够跨越前后端边界保留下来时，后端获得消费包级信息的基础。

后端协同配置用于区分三类 EP 消费方式的贡献。EP-aware hazard bypass 通过同 EP 相关性裁剪降低保守 scoreboard 阻塞；EP-driven prefetch 将循环体内规则访存意图转化为后端访存提前化；cross-EP overlap 则允许安全条件下的后续 EP 向量 slice 提前进入后端。消融结果显示，三类机制分别作用于相关性处理、访存延迟和执行重叠，并在 Full SEAM-V 中共同提升端到端吞吐率。具体而言，Full SEAM-V 相对于 SEAM-V-FE 进一步带来 `[TODO: backend cooperation speedup]` 的平均提升，其中 hazard bypass、prefetch 和 overlap 分别贡献 `[TODO]`、`[TODO]` 和 `[TODO]`。

### 5.4 Microarchitectural and Sensitivity Analysis

为解释性能收益来源，本文进一步分析后端计数器和敏感性实验。图 X 展示代表性 kernel 的 stall breakdown、sequencer 相关性阻塞、EP bypass 次数和访存等待。对于同 EP 内由 p-bit 契约暴露无非法依赖的向量指令，sequencer 可减少不必要的 RAW/WAR/WAW 保守检查；因此，具有较多局部并行向量操作的 kernel 应表现出更高的 EP bypass 计数和更低的相关性阻塞比例。

【图 X：Microarchitectural Counter Breakdown】

图 X 分析 EP-driven prefetch 的有效性。对于规则 unit-stride 访问，prefetch 请求能够转化为较高命中率，并降低 demand load 等待；对于冷启动阶段、短促执行阶段或非规则访存，prefetch 命中率可能较低。该结果说明，prefetch annotation 是性能提示而非正确性条件：当访问模式稳定时，它提高后端访存提前化能力；当访问模式不匹配时，硬件仍可退化为 demand-driven 访存执行。

【图 X：Prefetch Usefulness and Memory Behavior】

图 X 给出不同向量粒度和访存条件下的敏感性结果。AVL sweep 用于观察从短向量到较长向量阶段的性能变化；memory latency sweep 用于评估访存压力对 EP-driven prefetch 和 cross-EP overlap 的影响；LMUL 或向量配置 sweep 用于观察 RVV 时间-空间展开粒度变化时的收益趋势。该组实验强调，SEAM-V 并不是针对某一固定 AVL 的特化优化，而是在 workload 粒度、控制强度和访存行为变化时，通过 EP 语义贯通提升前端供给、后端调度和访存协同。

【图 X：Sensitivity to Vector Granularity and Memory Behavior】

总体而言，SEAM-V 对具有稳定局部并行性、规则访存意图和标量/向量交织的 kernel 更有利；对于强串行依赖、不规则 gather/scatter 或已经充分饱和向量后端的长向量 kernel，收益可能受限。本文将这些 limited-benefit cases 纳入分析，以界定 SEAM-V 的适用范围。

### 5.5 Physical Cost and Energy Efficiency

SEAM-V 的新增硬件主要来自任务接口、本地指令供给、VLIW 打包、混合执行控制、向量派发 command window、后端 EP hint 通路以及 VLSU prefetch 支持。表 X 给出面积和功耗拆分。相对于 baseline，Full SEAM-V 的总面积开销为 `[TODO: area overhead]`，总功耗开销为 `[TODO: power overhead]`，最高工作频率变化为 `[TODO: frequency/timing impact]`。

【表 X：Area and Power Breakdown】

能量结果综合考虑功耗开销和执行周期减少。虽然 SEAM-V 引入额外控制逻辑，但其减少了前端供给间隙、保守后端阻塞和访存等待，因此可能降低单个 workload 的总能量。图 X 报告代表性 workload 的归一化能量和 energy-delay product。Full SEAM-V 在所有通过测试的 workload 上实现平均 `[TODO: energy reduction]` 的能量改善，并将 EDP 降低 `[TODO: EDP reduction]`。

【图 X：Energy and Cost-Benefit Analysis】

从成本收益角度看，SEAM-V 的硬件代价主要集中在小规模控制和缓冲逻辑，而性能收益来自更连续的前端供给、更少的后端保守阻塞和更积极的访存提前化。该结果表明，以 EP 为核心的前后端语义贯通能够以可控硬件开销提升 RVV 向量处理器在多粒度 workload 下的性能与能效。



---

1. ## 参考文献候选

   [1] RISC-V International, “The RISC-V Vector Extension, Version 1.0,” 2021.

   [2] M. Cavalcante, F. Schuiki, F. Zaruba, M. Schaffner, and L. Benini, “Ara: A 1 GHz+ Scalable and Energy-Efficient RISC-V Vector Processor with Multi-Precision Floating Point Support in 22 nm FD-SOI,” IEEE Transactions on Very Large Scale Integration (VLSI) Systems, vol. 28, no. 2, pp. 530–543, 2020.

   [3] M. Perotti, M. Cavalcante, N. Wistoff, R. Andri, L. Cavigelli, and L. Benini, “A ‘New Ara’ for Vector Computing: An Open Source Highly Efficient RISC-V V 1.0 Vector Processor Design,” in Proc. IEEE International Conference on Application-specific Systems, Architectures and Processors (ASAP), 2022.

   [4] M. Perotti, M. Cavalcante, R. Andri, L. Cavigelli, and L. Benini, “Ara2: Exploring Single- and Multi-Core Vector Processing with an Efficient RVV 1.0 Compliant Open-Source Processor,” IEEE Transactions on Computers, 2024.

   [5] F. Minervini et al., “Vitruvius+: An Area-Efficient RISC-V Decoupled Vector Coprocessor for High Performance Computing Applications,” ACM Transactions on Architecture and Code Optimization, vol. 20, no. 2, 2023.

   [6] J. E. Smith, “Decoupled Access/Execute Computer Architectures,” in Proc. International Symposium on Computer Architecture (ISCA), pp. 112–119, 1982.

   [7] J. A. Fisher, “Very Long Instruction Word Architectures and the ELI-512,” in Proc. International Symposium on Computer Architecture (ISCA), pp. 140–150, 1983.

   [8] M. S. Schlansker and B. R. Rau, “EPIC: Explicitly Parallel Instruction Computing,” Computer, vol. 33, no. 2, pp. 37–45, 2000.

   [9] R. Espasa, M. Valero, and J. E. Smith, “Vector Architectures: Past, Present and Future,” in Proc. International Conference on Supercomputing (ICS), 1998.

   [10] R. M. Russell, “The CRAY-1 Computer System,” Communications of the ACM, vol. 21, no. 1, pp. 63–72, 1978.

   [11] J. L. Hennessy and D. A. Patterson, Computer Architecture: A Quantitative Approach, 6th ed. Morgan Kaufmann, 2017.

   [12] B. R. Rau and J. A. Fisher, “Instruction-Level Parallel Processing: History, Overview, and Perspective,” Journal of Supercomputing, vol. 7, pp. 9–50, 1993.

   [13] Texas Instruments, TMS320C6000 CPU and Instruction Set Reference Guide, Texas Instruments, latest available revision.

   [14] CDC, CDC 6600 Computer System Reference Manual, Control Data Corporation, 1964.

   [15] M. Perotti et al., “Ara2: Exploring Single- and Multi-Core Vector Processing with an Efficient RVV 1.0 Compliant Open-Source Processor,” arXiv:2311.07493, 2023. 若采用 IEEE TC 正式版，可与 [4] 合并。

   [16] <你的前期工作>, “<前端解耦与 VLIW/EP 打包相关论文题名>,” in Proc. , .
