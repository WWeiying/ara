# D256 Attention 的片上数据复用

本次工作从 `1ddd5de0` 出发，位于独立分支 `akv-d256-efficient`。
原 `ara_dsa` 分支保留不动。不修改 RTL、指令编码、SRAM 容量、综合约束或论文。
目标是先改善已有 D256 软件调度，再根据实测决定是否扩大 GGML selector。

## 1. 先区分外存装载和片上递送

D256 用现有两个 D128 物理区分两阶段执行：

1. QK 阶段：两个物理区分别保存 K 的前 128 维和后 128 维。
2. Softmax 阶段：合并后的完整 QK 分数沿原 RVV 路径处理。
3. PV 阶段：两个物理区改为保存 V 的前后两个 128 维片段。

因此每个 tile 有两次 FULL，但**并没有从外存读取两份相同的 K/V**。
两次 FULL 带来的是描述符、Query 和阶段切换开销；K 和 V 的有效数据各读一次。

真正发现的重复来自 Query-head 外循环：四个 Query head 共享同一份 K/V，
原软件却逐 head 请求相同的片上列和行。外存流量低，不代表片上指令和递送成本低。

同一真实 Gemma D256/GQA4/KV17 输入，在当前同一个 simulator 上的复测：

| 路径 | 总周期 | 列命令数 | 行命令数 | 片上 replay 字节 | K/V 外部 payload 字节 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原单-head AKV | 47,393 | 1,024 | 136 | 69,632 | 17,408 |
| 四-head 共享递送 | 32,713 | 256 | 34 | 17,408 | 17,408 |
| 四-head 共享递送 + panel4 | 30,255 | 64 | 34 | 17,408 | 17,408 |
| 强 tiled-RVV | 35,408 | 不适用 | 不适用 | 不适用 | 不适用 |

原 AKV 的列命令忙周期合计 12,284，行命令 3,808，两次 FULL 合计 1,309。
这些计数不是可以与所有执行周期简单相加的互斥分解，但命令数和字节数与循环结构
严格对应。四-head 修改后，列/行请求和 replay 都按预测减少到四分之一，外部 K/V
payload 不变。这支持片上递送重复是重要根因，而不是内存系统没有及时返回 K/V。

四-head 修改相对原 AKV 提速约 1.45 倍，相对强 RVV 约 1.08 倍；再使用已有
panel4 后分别达到 **1.57 倍和 1.17 倍**。后者相对强 RVV 减少约 14.6% 周期，
仍未达到既有 1.2 倍准入要求。不能因此删除 Gemma 的 fallback。

## 2. 共享内核如何修改

修改在 `software/akv/src/akv_v2_attention_rvv.S`，benchmark 和 GGML native
executor 使用同一源文件。

- QK：同时保留四个 F32 向量累加器，一条 K 列命令的结果用于四个 Query。
  每个累加器仍严格按维度 0 到 255 执行原有 `vfwmacc`，没有改成并行部分和。
- PV：一次 V 行递送服务四个 Query。前后两个 D128 输出片段互相独立，可分别
  遍历 token；每个输出元素的 token 顺序不变。
- PV 数值：保留 F32 乘法/FMA 后逐 token 舍入回 F16 的原顺序，不能直接替换
  成 F16 FMA，也不能一直累加在 F32 中最后才舍入。
- q_rows=1..8：每四个 head 为一组，剩余 1..3 个 head 走原单-head 循环。
  不越界读取 Query，不要求硬件新增 Query 槽。
- 列 panel：设备确实报告已有 panel4 能力时，四个相邻列通过一条命令递送；
  仍逐列按原顺序更新四个累加器。检查放在 D256 入口，不影响 D64/D96/D128。
  没有 panel4 能力时继续使用合法的单列命令。

panel4 的实测与预测一致：GQA4 每 tile 的列命令从 256 减到 64，逻辑列数仍为
256；K/V 外部流量和片上 replay 字节均不变。上述三种 AKV 的 AXI AR 字节数
均为 32,240，其中不仅有 K/V，还有 Query、描述符及普通 RVV load。
因此不能把 `akv_replay_bytes` 当成外存读取量，也不能把节省的片上字节全部
归为总线带宽收益。

## 3. 验证范围与当前边界

### 真实模型数据

原短点来自固定的 Gemma-3-1B Q4_K_M 实际 Decode 输入，D256/GQA4/KV17。
本次另从完整 Gemma 推理截取 layer 0 的 Decode Attention，得到 KV140。
后者保留全部真实四个 Query head 和 K/V，并跨越三个 64-token tile，末尾有 12
个有效 token；不是重复短输入拼成的长测试。模型 SHA、capture 命令、二进制 SHA
和张量元数据保存在独立 capture 目录。

性能验证比较同一 capture、同一 VCS simv、相同数值容差下的原/新 AKV 和强 RVV。
每次保存 ELF、源码快照和哈希。旧 47,191/36,043 的历史报告使用不同 simulator，
只作为历史线索，不能与本次新周期混在一起计算加速比。

### 直接检查运算顺序

`apps/akv_d256_reuse_smoke` 只在测试构建中导出原单-head 循环入口，与当前
分组和 panel 内核对照。检查完整 score/accumulator 数组以及 `fflags`：

- Query rows 1、3、4、5、7、8；
- token 数 1、3、17、64，以及从 tile_start=64 开始的一-token 尾块；
- 有 padding 的 288-element Query/K/V stride；
- 非零、带符号、包含小数及 F16 小数值的输入和初始累加器；
- RNE 和 RDN 舍入方式，未使用的 head/score 尾部必须保持不变。

该测试是原生内核一致性验证；真实模型性能仍由上面的 capture 测试提供。
普通 RVV、D64/D96/D128 和 QBS/AKV 交接需另做代表性回归。

短点的 panel4 原生仿真已 PASS。扩展一致性测试及交接回归使用独立后台任务，
以完整结束标记为准，不把已通过的部分 case 当成整项完成。

### 长点暴露的是另一项已有数值边界

KV140 不是成功的性能结果，不能放入有效加速比的汇总：

| 路径 | 实测周期，仅供诊断 | 对原始 GGML 输出的超差元素数 | 状态 |
| --- | ---: | ---: | --- |
| 强 tiled-RVV | 193,172 | 18 / 1,024 | FAIL |
| 四-head 共享递送 | 149,455 | 18 / 1,024 | FAIL |
| 四-head 共享递送 + panel4 | 141,683 | 18 / 1,024 | FAIL |

没有扩大容差：仍为 `abs_error <= 0.004 + 0.002 * abs(golden)`。
这三个运行都正常计算结束，并不是 watchdog/许可证/仿真超时。AKV 和强 RVV
打印出的首批失败元素相同，数值彼此仅相差约 0--1 ULP。

根因不能简单写成“FP16 精度不足”，而是 **FP16 中间舍入与最大值更新顺序相互
作用**。GGML 的逐 Query Decode 路径按 token 执行：遇到新的最大 QK 分数，
先缩放已有 F16 累加器并舍入，再加入当前 V。当前两条 tiled 路径先得到整个
tile 的最大值，只缩放一次，再依次累加。这在实数算术中等价，但 F16 中间结果
会在不同位置舍入，长输入便可能超过原容差。

为区分这个原因与 QK/地址/递送问题，`analyze_d256_numerics.py` 固定同一份
真实输入、相同逐维 F32 QK 分数，单独改变最大值更新间隔和累加精度：

| Host 诊断顺序 | 超差元素数 | 最大误差/容差 |
| --- | ---: | ---: |
| 逐 token 更新，F16 累加器 | 0 | 0.375 |
| 64-token tile 更新，F16 累加器 | 18 | 1.600 |
| 逐 token 更新，F32 累加器 | 29 | 2.398 |
| 64-token tile 更新，F32 累加器 | 29 | 2.398 |

Host tile/F16 结果在 AKV 日志打印的 12 个失败元素上，最大偏差仅为
`4.77e-7`；因此源代码中的顺序差异和已测输出能够相互印证。这个 Host 工具
使用 libm `expf`，不模拟 RVV vector-exp 的每条指令，也不模拟主机 SIMD dot
的全部细节；它是根因实验，不能代替 RTL 仿真或覆盖原 golden。

F32 行更偏离原 golden **不代表数学结果质量更差**：golden 本身来自 GGML
原有 F16 中间累加顺序。若要改变数值契约，需要另外做模型质量验证，不能在
本次性能修改中静默切换。本阶段保持原数学顺序、容差和 GGML fallback。
下一步应优先解决这项顺序兼容问题，再讨论提高 D256 的默认覆盖率，而不是
先扩大 context 容量或降低准入要求。

### 不同维度及构建检查

| 已完成的真实模型回归 | 配置 | 周期 | 状态 |
| --- | --- | ---: | --- |
| Qwen2.5 | D128 / GQA6 / KV16 | 35,290 | PASS |
| SmolLM2 | D64 / GQA3 / KV5 | 31,860 | PASS |
| Phi-3.5 | D96 / 单 Query head / KV18 | 10,854 | PASS |

Qwen 的前一阶段同 capture、同 simv 结果为 35,473 周期，本次没有退化。
D64/D96 表示本次功能回归通过，不据此宣称它们获得了新的加速。
Host `make -C software/akv check` 的原合约测试、192 组布局/分组/尾块和特性
检查均通过。测试同时发现旧 smoke wrapper 没有声明被 include 的汇编依赖，
导致新 C 入口与旧 `.o` 链接失败；已补齐依赖与构建锁。该构建失败保留在
`d256_reuse_regress_20260907`，修复后的回归目录使用 `_r2`，不覆盖原记录。

## 4. 复现

入口为 `verification/akv/run_d256_efficiency.py`，每次 `--output` 必须是新目录。

```bash
python3 verification/akv/run_d256_efficiency.py --mode capture \
  --output hardware/akv_d256_efficiency_runs/new_capture

python3 verification/akv/run_d256_efficiency.py --mode akv_v2 \
  --capture hardware/akv_d256_efficiency_runs/gemma_long_capture --kv 140 \
  --sim-dir hardware/qbs_akv_portability_stage2_20260907_r2/sim \
  --output hardware/akv_d256_efficiency_runs/new_native

python3 verification/akv/run_d256_efficiency.py --mode smoke \
  --sim-dir hardware/qbs_akv_portability_stage2_20260907_r2/sim \
  --output hardware/akv_d256_efficiency_runs/new_exact

python3 verification/akv/analyze_d256_numerics.py \
  hardware/akv_d256_efficiency_runs/gemma_long_capture \
  --output hardware/akv_d256_efficiency_runs/numerics_check.json
```

VCS 每点上限为三小时，长任务使用 tmux 独立后台执行，不连续轮询。
`stage.json`、`complete`、正常结束标记、零 mismatch、非 fallback 的 native 标记
和性能日志共同决定 PASS；仅进程退出或仅出现一个 PASS 字样不够。

`summarize_d256_efficiency.py` 只汇总明确命名的 cohort，同时保留 FAIL/RUNNING，
不寻找“最近一次 PASS”代替本次失败。`complete` 表示全部任务结束，`all_pass`
才表示全部通过。其 `--wait` 使用进程退出事件等待，可在 tmux 后台自动收尾，
不会周期性轮询长仿真日志。原始目录包含源码快照、ELF、日志和哈希；Git 只收录
共享实现、测试、文档以及 `verification/akv/results/d256_efficiency_20260907/`
中的小型结果快照。

## 5. llama.cpp 优先的逐 token 数值兼容

后续分支 `akv-d256-online-order` 从 `59eb50d3` 出发，保留前面的性能基线。
主目标是扩大 llama.cpp 对模型、格式和 Attention 形状的可靠支持；其他运行时
只酌情复用接口。本阶段不接入新的外部运行时，不改 RTL 或 GGML 默认 selector。

当前实现保留 64-token QK 装载、panel4 列递送及四 Query-head 的 V 行复用，
但 D256 的 Softmax 改为记录每个 token 到来时的运行最大值：

1. 已遮蔽的 token 保留零权重，不计算 `-Inf - -Inf`。
2. 分数超过此前最大值时，记录 `exp(old_max - new_score)` 缩放因子。
3. 每个权重按它自己的运行最大值计算，exp 仍批量使用原 RVV 实现。
4. PV 在对应 token 之前执行 F32 缩放并舍入到 F16，再执行该 token 的
   F32 FMA 并舍入到 F16；没有新最大值时跳过多余缩放。
5. 分母按 token 顺序执行单独的 F32 乘法和加法，不再每 tile 归约一次。

缩放因子使用最多 `8 x 64 x 4 = 2048` 字节的软件局部数组，不增加硬件 context
或改变公共 workspace/descriptor ABI。编译器自身的栈帧和寄存器 spill 另外计入
软件开销。旧逐 tile PV 函数保留作回归对照；新函数仅用于实验性 D256 执行路径。
D64/D96/D128、Prefill 和 QBS 的算法、指令和选择条件均不改变。

这项修改修正的是已测的 D256 Decode 中间舍入顺序，不声称与所有 GGML 算法逐位
一致。QK 和 exp 实现仍存在原有的数值差异；带 sink 等组合也不能仅从本次无 sink
Gemma 输入推广。D256 仍必须同时通过原数值容差和性能准入，才能另行考虑接管 GGML。

已完成的静态与 Host 检查：

- `make -C software/akv check`：原合约检查、192 组布局/功能和新增 108 组
  token-order 检查通过。108 组覆盖 1/3/17/64/65/140 token、三种软件分块、
  前导遮蔽/遮蔽空洞/全遮蔽，以及已初始化的 sink 分母状态。
- Host 编译器不提供 `_Float16`，因此 Host 新测试明确只验证 F32 调度和分母。
  F16 舍入另由原生 PV 测试与独立 RVV-memory oracle 对比，不假称 Host 已测 F16。
- 新 PV 和实际 native C 调度均使用项目 LLVM 交叉编译通过；不使用 ZCC。
- 原有 D256 结果收集/数值诊断的 12 项 Python 测试通过。

原生测试新增逐 token 缩放、零权重、四-head 和 1..3-head 尾组，对照普通 RVV
内存加载实现的 PV，并同时检查整个输出、未使用区域及 `fflags`。复用既有八组
RNE/RDN、token 尾部和带 padding 的测试输入，不覆盖前一次运行记录。

后台入口：

```bash
python3 verification/akv/run_d256_online_order.py \
  --output hardware/akv_d256_efficiency_runs/online_order_20260908
```

入口按以下顺序串行执行，任一点失败便停止后续点：真实 Gemma KV140、八组原生
PV 对照、Gemma KV17、Qwen D128、SmolLM2 D64、Phi D96、同一 Gemma KV140 的
普通 RVV。每次启动要求全新的目录；保存源码和 ELF 哈希，软件在运行期间发生
变化便停止后续点，防止混合版本。所有点复用原基线同一个 simv，每点 VCS 上限
三小时，不持续轮询日志。

上述串行 VCS 队列已完成：2026-09-08 03:08:59 至 04:31:41 UTC，共约
82 分 43 秒，7/7 项通过，没有放宽容差。当前有效结果如下：

| 输入和实现 | kernel_cycles | mismatch |
| --- | ---: | ---: |
| Gemma D256 / GQA4 / KV140，逐 token AKV | 164,622 | 0 |
| 同一 Gemma KV140，普通 RVV | 419,549 | 0 |
| Gemma D256 / GQA4 / KV17，逐 token AKV | 33,521 | 0 |
| Qwen D128 / GQA6 / KV16 | 35,343 | 0 |
| SmolLM2 D64 / GQA3 / KV5 | 31,959 | 0 |
| Phi D96 / 单 Query head / KV18 | 10,901 | 0 |
| 原生 PV smoke，原有 8 组及 online 8 组 | 不作为性能点 | 全输出及 fflags 一致 |

Gemma KV140 相对同输入、同 simv 且通过数值检查的普通 RVV 为 **2.549 倍**，
周期减少 **60.76%**。分子分母均为 `kernel_cycles`；不要混用 `hw_cycles`。
这不是完整模型加速比，也不是相对已经修正数值顺序的最强 tiled-RVV 加速比。
前文 193,172 周期的 tiled-RVV 仍超差，不能作为有效分母。

归档在 `verification/akv/results/d256_online_20260908/`，包括完整状态和六个
性能点的小型 CSV。原 ELF、逐点源码、日志和哈希仍在独立运行目录中。

## 6. 受控接入 GGML Decode

新阶段位于 `llm-linear-attention-next`，基线引用
`llm-linear-attention-baseline-20260908` 保留 `4410dce9`。
llama.cpp 的接入使用独立工作树 `llama.cpp-d256-admission`，原
`qbs-activation-context` 的未提交修改完整保留。

新开关为 `GGML_RISCV_AKV_D256=1`，只在 AKV 本身开启时起作用，默认关闭。
接入条件是 v2、D128 物理区、D256 segmented 和 panel4 能力可用，F16 K/V、
F32 Query/输出、合法对齐与步长，以及正长度的普通 Decode mask。mask 只能是
连续有效前缀的零偏置与末尾 `-Inf` padding；暂不接管前导遮蔽、空洞、全遮蔽、
有限偏置、softcap、ALiBi 或 sink。D256 Prefill 和不符合条件的节点仍走 RVV。
GQA 超过 8 只有同时开启既有 portable 分组功能时才拆组处理。

不能只放开维度判断：GGML 的 Query 转换暂存区和功能参考累加器原来只容纳
D128，本次都扩展到 D256。前者最大 4 KiB，新增的是 2 KiB 软件栈容量，
并非片上 SRAM。只转换实际使用的 Query 行，原生 executor 不读取未初始化的
尾部。后者只在功能参考执行中使用。原生 QK/PV 仍调用同一个共享内核，本次
未改 RTL、指令、descriptor、native 算法或 QBS 选择。

`AKV_D256_ONLINE_FP16` 是软件实现契约标记，防止 adapter 在缺少逐 token
舍入实现的旧头文件上开启新选择；它不是新 ISA capability bit。使用构建脚本
将 adapter 和本仓库的 runtime 一起编译，不应混装其他版本的静态库。

定向 GGML 测试新增 D256/GQA1、3、4、8、9，KV17、65、140，共 15 点，
加 1 点末尾遮蔽；逐项检查默认回退、开启后输出、越界保护、5 类特性回退、
不对齐步长、v1 拒绝和显式关闭。原有 18 组 portable 测试与 D96/D128 检查
仍保留。D256 测试用 `AKV_TEST_D256=1` 显式开启，旧测试入口默认不要求外部
llama.cpp 安装新 adapter。

模型队列为 Gemma 短输入开启、同输入关闭、Qwen 原路径回归、Gemma 较长输入
开启，每点生成 3 个 token，分别比较 RVV、QBS-only、QBS+AKV。统计实际 Decode
命中数与 fallback 原因，不仅要求模型能结束。长输入来自同样的真实模型推理，
不把重复短 capture 当作长 K/V 数据。此处 QBS 执行 QEMU 自定义指令模型，
AKV 执行 GGML 功能参考；模型通过不等于新增原生 RTL 性能数据，也不等于大规模
困惑度验证。模型结果待队列完整结束后归档，不预填 PASS。

复现与当前阶段安排见 `llm_linear_attention_next.md`。
