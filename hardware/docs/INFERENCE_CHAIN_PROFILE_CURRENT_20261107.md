# 面积优化基线上的 QBS/AKV 完整调用性能归因

验收状态：两条完整调用、普通 RVV 冒烟、独立协议检查、原始输入完整性和
周期对账均已通过；原始失败记录未改写。

## 1. 结论

现有机制仍有性能损失，但两个路径的限制不同，不能通过统一扩大计算资源解决。

1. **M1 Q6_K 投影受权重供给节拍限制。** 当前配置每周期最多接收 16 B，
   一个四输出行 tile 有 840 B 权重；搬运至少需要 53 个握手周期，而点积
   发射只需 32 周期。实测严格等权重期间，89.27% 的周期仍在接收数据。
   增加 dot 吞吐或只加深 outstanding，不能消除这部分必要的数据量。
2. **本次 F16/GQA2 Attention 的主要工作在 QK/PV，而非外部 KV 填充。**
   QK/PV 两段合计占插桩完整调用的 61.64%；generic 路径对两个 head 分别
   重放相同 K/V，已有配对 head 与 PANEL4 能力没有在这个测试中启用。
   下一步应先验证现有资源能否减少重复重放和逐命令控制，而不是新增阵列。
3. **完整调用不等于专用引擎 busy。** 孤立 Q6_K SDK 调用中，新量化占
   41.14%，设备发现/计划等区间占 22.21%。但是实际 GGML 已缓存设备能力，
   并能在符合条件的连续算子间复用 activation；不能把这些百分比作为
   每次真实模型投影都要付出的剩余开销。

本轮完成 profiling，没有实现上述后续优化，没有修改生产 RTL、SDK、
llama.cpp、FPGA 副本，也没有启动综合。下文是两个真实数据算子切片的
当前 SoC 测量，不是完整层或整模型周期占比，也不是新旧硬件加速比。

## 2. 固定的硬件、软件和证据

测量计划为 [INFERENCE_CHAIN_PROFILE_EXECUTION_20261107.md](INFERENCE_CHAIN_PROFILE_EXECUTION_20261107.md)。
此前历史证据复析仍保留在 [INFERENCE_CHAIN_PROFILE_20261107.md](INFERENCE_CHAIN_PROFILE_20261107.md)，
不能将其中旧 SoC 的周期混入本次结果。

| 项目 | 本轮身份或配置 |
|---|---|
| 生产 RTL 基线 | 面积阶段末尾 `71468b1c3`，经 `8d9ef7cee` 恢复；本轮提交只增加测量与分析 |
| 新 VCS 源快照 | 从 `640862d2d` 的提交树导出，依赖取自已验收的冻结清单 |
| Lane / VLEN | 4 / 1024 bit |
| 前端 | 普通主核，非 IDEAL_DISPATCHER |
| QBS / AKV-v2 | 开启 |
| 共享整数乘法器 / 共享 FMA | 开启 / 默认关闭 |
| QBS AXI 数据宽度 | 128 bit |
| 仿真 RAM | 16 MiB，仅扩容量，不改变接口宽度或时延模型 |
| Q6_K SDK 提交 | `a704cec051aacd567c71b7542f602f1c9e99fb3b` |
| F16 SDK 提交 | `640862d2d0fdb209e4a0a2412c317e1d9bd68928` |
| llama.cpp 提交 | `b5da29fde5a986dfc005a5de1c8b06a3479b51c4` |
| VCS 镜像 SHA256 | `3ed8bc6b761d49664162b9f3b45e525e5c051923618950cbdb2b38ea403486a6` |

两次 SDK 提交之间生产 SDK 内容未变。SDK 和汇编均来自 Git archive，未使用
工作区未提交的 AKV 汇编。没有用本地未登记的依赖修改重新生成测试环境。

所有以下相对证据目录均位于：

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/
```

| 证据 | 目录与状态 |
|---|---|
| 新 SoC 镜像及原始编译日志 | `chain_soc_20261107_01/`；原 worker 收尾异常保留 |
| 独立镜像身份/编译审计 | `chain_soc_admitted_20261107_01/` |
| 同镜像普通 RVV 数值及协议冒烟 | `chain_profile_runs_20261107_01/smoke/`，PASS |
| Q6_K 最终 ELF | `chain_q6_build_20261107_integrity02/` |
| Q6_K 正式数值与协议结果 | `chain_q6_integrity_vcs_20261107_01/`，PASS |
| F16 ELF | `chain_f16_build_20261107_profile03/` |
| F16 正式数值与协议结果 | `chain_profile_runs_20261107_01/f16/`，PASS |
| 最终重审、周期对账和原始证据哈希 | `chain_profile_reconciled_20261107_03/` |

最终 `result.json` 状态是 `CURRENT_RUNS_RECONCILED`。分析器重新运行原始数值
检查，复核 source/image/ELF/raw-log/vector-trace 哈希和独立 UVM 证据，
并逐条核对 `terminal_cycle - fire_cycle == native_busy_cycles`。

## 3. 输入和正确性检查

### 3.1 Q6_K 投影

使用真实 Qwen3 position40 的单 token Decode activation，算子为
`blk.0.attn_v.weight` 的 M1/K2048/N64 输出切片。保留完整 K；N 从原先
128 行切片按 R4 block-major 规则取前 64 行，而不是截取错误的连续字节。
每次调用由两个 N32 命令组成，使用 FILL/RELEASE activation context。

每次检查完整 2336 B Q8_K 数据，包括 scale、量化值和 bsums；64 个 FP32
输出与独立参考逐位相同；检查 8 组各 64 B guard、CSR、planner 及命令工作量。
两次调用均通过，且独立 UVM 无协议问题。第一次与重复调用之间有校验工作，
不将其命名为严格的 cold/warm cache 实验。

两次计时调用返回后，另外逐字节读取原始 F32 activation 的 8192 B 和
R4 权重的 107520 B，计算目标机 FNV-1a64，并与冻结 host 文件的独立常量
核对，分别为 `5ef242baed35757d`、`7eceba2d0d76e82d`，全部匹配。
这些读取在两个 ROI 之外，不插入两次调用之间；证明最终目标可见 payload
签名一致，不等同于证明执行中途从未出现瞬态改写。

### 3.2 F16 Attention

使用真实 Qwen3 的 KV head0、query heads0/1，D128/GQA2、137 个有效 token、
容量 256，三个 tile 为 64+64+9。保留原始 softmax 范围，没有裁掉 token 后
继续沿用旧输出参考。

完整调用包括 Q 的 F32→F16 转换、设备查询、Decode 验证与建 plan、native
执行及最终 drain。采用未插桩/插桩/插桩/未插桩的 ABBA 顺序。

四次调用的 256 个输出彼此逐位相同，也与独立 tile64 native 参考逐位相同；
相对原捕获参考最大绝对误差为 `0.0009320676326751709`，满足事先固定的
`atol=0.003, rtol=0.02`。FCSR 一致，VCSR/VSTART、输入指纹和 guard 检查通过。
共检查 1024 个输出，独立 UVM 通过。

本测试主动关闭可选实验选择器，测量提交版 generic 路径。它不证明本地未提交
汇编、打开实验开关的路径或当前板上软件具有相同周期。

## 4. Q6_K：完整调用与引擎内部是两种画像

### 4.1 完整调用的互斥分解

计时点之间不添加中间 fence。保留 native executor 原有的 fence、vset、
descriptor 处理和结果 store，最后执行一次完整调用 drain。

| 区间 | 第一次 | 重复调用 | 平均周期 | 占平均完整调用 |
|---|---:|---:|---:|---:|
| 实际 RVV activation 量化 | 11533 | 11451 | 11492.0 | 41.14% |
| 设备发现、绑定、计划/准入等 | 6478 | 5929 | 6203.5 | 22.21% |
| QBS engine busy | 8247 | 8242 | 8244.5 | 29.52% |
| execute 区间内、busy 以外 | 2066 | 1856 | 1961.0 | 7.02% |
| 最终 drain | 30 | 30 | 30.0 | 0.11% |
| 完整调用 | 28354 | 27508 | 27931.0 | 100% |

`execute - busy` 仍包括 SDK、迭代器、descriptor、命令前后同步、vset 和
结果存储等，不能将这 1961 周期全部称为无效等待。新增的量化后 CSR 读数
位于准备计时点之后，计入第二行，而非宣称探针没有成本。

### 4.2 真正的等权重证据

| 每完整调用的平均指标 | 数值 | 解释 |
|---|---:|---|
| 内部 tile 数 | 128 | 两个命令，每个 64 个 tile |
| dot issue | 4096 cycles | 占 busy 的 49.68%，不是物理 FU 利用率 |
| 有效乘积 / 发射容量 | 131072 / 131072 | 发射槽有效率为 100%，不是时间利用率为 100% |
| COMPUTE_TILE 中不发射 dot | 640 cycles | 5 cycles/tile，包含退休与交接尾部 |
| weight phase | 2801.5 cycles | 包括初始加载等候和后续严格等权重 |
| 严格 WAIT_WEIGHT | 2087.5 cycles | 占 busy 的 25.32%，已包含在 phase 中 |
| FP-input / profile-result / context-start / commit 阻塞 | 均为 0 | 本形状未证明这些接口是瓶颈 |

严格 WAIT_WEIGHT 的互斥四分项：

| 条件 | 平均周期 | 占严格等待 |
|---|---:|---:|
| reader burst FIFO 无 outstanding | 32.0 | 1.53% |
| 有 outstanding，但无 RVALID | 5.0 | 0.24% |
| RVALID 且 RREADY，正在传输 | 1863.5 | 89.27% |
| RVALID 但非 RREADY | 187.0 | 8.96% |
| 合计 | 2087.5 | 100% |

计数定义见 `hardware/src/vlsu/qbs/qbs_engine.sv:488`，仅在 compute engine
的严格 WAIT_WEIGHT 状态分类。它观察共享 reader，不按当前所需 tile/tag
过滤；“无 outstanding”不等于已经证明“软件没有发请求”。

但是，权重工作量本身给出了独立限制：每 R4 tile 的四行 Q6_K 数据为
`4 × 210 = 840 B`，128-bit 接口即使连续传输也至少需要 53 个 beat，
而 M1 dot 为 32 cycles，COMPUTE_TILE 实测为 37 cycles。持续供给无法
完全隐藏在这段计算之后；不能以此前 M4 的零 WAIT_WEIGHT 推断 M1 也不缺供给。

每次调用的权重 payload 为 107520 B，全部 reader 数据有 6938 个 beat。
这是 QBS reader 的接口活动，不是板上 DDR 吞吐测量。单独权重的理想
传输下界为 6720 cycles，也不是可以实现的完整调用时间。

当前源码已有 M1 R4 lookahead（`qbs_engine.sv:413`），不能将本次现象描述为
“没有预取”。短窗口中相邻 tile 启动间隔为 56/57 cycles，与供给限制相符；
要进一步区分接收气泡，仍需关联目标 bank、ingress 和余字排空，而不是
将所有 AR-slot/full 计数直接解释成新增 stall。

### 4.3 哪些硬件扩大暂时不值得做

- 本点 FP-input、结果及 context-start 阻塞为零，不支持扩这些队列。
- Activation context 已生效：第二个命令重放 2336 B，避免对应的 activation
  AXI payload；不能因为 replay 仍耗时就认为 context 没有工作。
- 即使假设 640 个 compute-no-issue 周期全部可删且其他工作不变，完整调用
  也只有 `27931 / (27931 - 640) = 1.02345x`。这是条件预算，不是收益预测。
- 若将全部 282 个 reader 接收反压周期都假设为关键路径且可删、其他周期不变，完整调用
  上界也约为 1.01020x；这些周期事实上可能部分重叠，因此不能承诺该收益。

优先调查 ready 气泡或 bank 交接是否有小改进空间，不先扩 dot、SRAM bank
或 reader 深度。必要的权重传输量仍然存在。

## 5. F16 AKV：主要成本是消费上下文，而不是把 KV 搬进来

### 5.1 完整调用与插桩扰动

| 顺序 | 未插桩 A0 | 插桩 B1 | 插桩 B2 | 未插桩 A3 |
|---|---:|---:|---:|---:|
| 完整周期 | 53130 | 53260 | 53064 | 52878 |

未插桩平均 53004 cycles；插桩平均 53162 cycles。观测到的差值为
`+158 cycles / +0.2981%`。空探针区间中位数为 6 cycles，但该数不能
机械地从各阶段减去；ABBA 差值还包含调度、代码布局与缓存变化。

| CPU 到达阶段边界的互斥区间 | 插桩平均周期 | 占插桩完整调用 |
|---|---:|---:|
| FULL | 2199.5 | 4.14% |
| QK，三个 tile 合计 | 22275.0 | 41.90% |
| scale / mask / online softmax | 5361.5 | 10.09% |
| PV，三个 tile 合计 | 10493.5 | 19.74% |
| 两次 REFILL 合计 | 2423.5 | 4.56% |
| RELEASE 和归一化输出 | 349.5 | 0.66% |
| 以上 span 之外 | 10059.5 | 18.92% |
| 合计 | 53162.0 | 100% |

最终 drain 平均 38 cycles，已经包含在最后一项中，不可再次相加。
这些是 issue-side 区间，阶段间没有人为排空。QK 尾部可能延续到 softmax，
PV 尾部 store 可能延续到 REFILL；不能把每一行当成独占硬件时间或纯 stall。

### 5.2 原始命令、工作量与实际服务周期

下面周期取两个未插桩调用的平均值；每条命令的 native busy 均已与
被动 fire/terminal 信号逐条一致核对。

| 命令类别 | 每调用条数 | busy 周期合计 |
|---|---:|---:|
| FULL | 1 | 2149 |
| REFILL | 2 | 2410 |
| K-column | 768 | 13311 |
| V-row | 274 | 6850 |
| RELEASE | 1 | 1 |
| 合计 | 1046 | 24721 |

第一次 FULL fire 到最后 RELEASE terminal 的区间平均为 42556.5 cycles：
24721 为 engine busy，17835.5 是命令之间的间隔。两者严格相加等于该
区间，但间隔中有必要的 RVV 算术、scalar 送数、softmax 和依赖等待，
不能全部称为可删除的派发开销。

三次填充共读取 70720 B：64 B descriptor、512 B Q、70144 B K/V，
对应 4420 个 128-bit beat。FULL/REFILL 的 engine busy 合计 4559 cycles，
仅比 payload 连续传输下界多 139 cycles。这个点不支持“外部 KV 填充
吞噬主要时间”的解释，也不代表实际板上 DDR 永远没有瓶颈。

K-column/V-row 均没有外部 AR 或读 payload，它们消费的是本地 context。
一次调用的 replay payload 为 140288 B，说明 SRAM→VRF 数据递送也有实际成本。
首个未插桩调用中：64-token K-column 每条 22 cycles；9-token 尾块
为 7/8 cycles；D128 V-row 每条 25 cycles。K-column 的 bank-read 周期
合计 4608，V-row 重放反压合计 2192；这些计数已在命令 busy 中，不能再次相加。

`akv_engine.sv:660` 起的 replay 协议等待各 lane 接收和 final grant，
并在 REPLAY_READ/WRITE 间推进。因此 SRAM 命中不等于一周期免费装入 VRF。
AKV busy 平均约占未插桩完整调用的 46.64%，剩余时间不能解释成“处理器空闲”：
普通 RVV 算术和 scalar 控制也会在这些时间内执行。

### 5.3 重复工作如何产生

提交版 generic QK 对每个 head 依次执行：

```text
逐 head：128 次 K-column -> 取 Q 标量 -> widening FMA
逐 head：逐 token 取 V-row -> 转换权重 -> F16 FMA 更新该 head 的输出
```

见本次 F16 构建冻结的 `inputs/software/akv/src/akv_v2_attention_rvv.S:545`
和 `:679`；不是工作区未提交汇编。两个 head 使用相同 KV，却分别重放，
因此实际产生 `3 × 2 × 128 = 768` 条 K-column 和 `2 × 137 = 274` 条 V-row。
尾块只有 9 token，但每个 head 仍有 128 个 K 维度的 column 命令。

硬件已有 PANEL4：`akv_v2_context.sv:205` 一次 bank-read 可以抽取四个
相邻维度；`akv_engine.sv:620` 按列将其送入后续向量寄存器。冻结 SDK
的 `experimental/paired_heads/` 也已存在 head 配对实现，但当前默认选择
需要 `AKV_PAIR_HEADS=1` 和 capability/shape 等准入，本次未打开。

若后续合法地共享两个 head 的 K/V，再使用 PANEL4，静态工作量可变为
96 条 K panel 命令、137 条 V-row，逻辑 K 列数减为 384。外部 KV 字节和
每个 head 必须完成的数学运算不会因此减少。以上是已有路径的候选工作量，
不是本轮已测的加速比；也不能把命令减少比例直接换算为周期加速比例。

## 6. 与实际 GGML 推理链路的对应关系

本轮测试使用真实模型数据和生产 native executor，但完整计时对象仍是
独立 SDK 调用，不是编译并执行完整 GGML graph。

| 本轮测量工作 | 实际 GGML 中的处理 | 应如何解释 |
|---|---|---|
| QBS 每次显式 device query | 冻结 `qbs.cpp:540` 的 static device 已缓存 | 不应建议再“新增设备缓存”或把全部 query 成本乘以算子数 |
| QBS 每次 fresh RVV 量化 | `qbs.cpp:1139` 起支持符合条件的跨算子 activation 复用 | 单独 V 投影的量化比例不是整模型每个 V 投影都需付出的成本 |
| N64 的一次 planner | 实际矩阵通常有更多输出 tile | 小切片会放大每调用固定成本，不能线性外推其百分比 |
| F16 SDK 测试的 scalar Q 转换和 device query | 冻结 `akv.cpp:194` 缓存 device，`:766` 使用 F16 type-trait 转换 | span 之外的 18.92% 不全是可移除的实际后端开销 |
| generic F16 QK/PV | native executor 同一 replay/算术路径 | 可用来定位逐 head 重放成本；可选 paired/PANEL4 路径仍需独立 A/B |
| 本次 F16 KV | 量化 KV、Prefill、其他 D/GQA/上下文有不同路径 | 不能将本点占比用作所有 Attention 的统一画像 |

这些源码引用均为 Q6 构建内冻结的 llama.cpp，而不是未经固定的最新 master。
本轮没有恢复已归档的大资源试验，也没有关闭数值/准入/fallback 规则。

## 7. 周期信号能证明什么

新增 monitor 是被动 bind，不驱动 DUT。两个运行分别保留第一次执行命令
呈现后 1000 个连续周期；QBS 另有首次 integer launch 后 200 周期 root 窗口。

- Q6 的 1000 周期窗口中有 864 次 reader R 握手、246 个严格 WAIT_WEIGHT
  周期；200 周期 root 窗口有 185 次 R/data 接收。这支持供给路径的解释，
  不能用此前缀代替全调用百分比；全调用以上述终态计数为准。
- 每条命令的 fire/terminal 在全运行中记录，不仅限于 1000 周期窗口。
  Q6 四条、F16 4184 条均完成生命周期与 busy 的一致性核对。
- monitor 的 AR/R **只连接 QBS reader 接口**，不是全 SoC 或 AKV 的 AXI。
  F16 窗口中这两列为零，不能据此断言 AKV 没有访存；它的传输证据来自
  自身 AKV_PERF 及独立 AXI checker。
- front valid 且非 ready 可以持续跨越异步命令执行，不能将其全部记为
  接纳前的前端停顿。命令进入引擎和向 CPU 完成握手是不同边界。

## 8. 下一步按收益与面积代价排序

| 优先级 | 动作 | 根据 | 验证方式 |
|---|---|---|---|
| 1 | 在现有硬件上评估已存在的 paired-head/PANEL4 F16 路径 | 本次 QK/PV 合计 61.64%，且逐 head 重放相同 KV | 同一真实输入、完整调用 A/B；数值/CSR/guards/工作量/独立协议全部通过后才谈默认选择 |
| 2 | 将准入、缓存状态与实际 GGML dispatch 对上 | SDK 固定成本被小 N 放大，实际已有多种缓存/复用 | 用固定 graph epoch、activation identity、实际命令生命周期区分 hit/miss；不再凭孤立 slice 比例新增机制 |
| 3 | 用目标 tag/bank 精确拆 QBS 接收气泡 | reader 接收反压有记录，但不是主要必要传输量 | 一个原形状、连续三 tile 短窗口；区分 active-bank 保护、ingress 满与 pending multiword，再决定是否值得改 ready |
| 暂缓 | 扩 dot、FP/result FIFO、SRAM 或读窗口 | 当前没有相应主要阻塞证据，且权重传输下界不变 | 只有后续形成不同证据才重新评估 |

第 1 项首先复用已经存在的代码和硬件，不先做新功能。保持每个 head 内
K/token 的累加顺序、F16/F32 边界、异常语义、单 worker 和运行时 fallback；
不能以转换到不同精度/数学顺序的实现作为无条件等价替换。本轮不执行这些
后续性能优化，也未声称已达到新收益。

GQA2 后续应评估 `AKV_PAIR_HEADS=1` 的组合路径，不能单开只针对六头选择的
`AKV_QK_PANEL4` 并认为已经测到相同机制。组合收益也不能单独归功于 PANEL4。
当前 generic checker 固定了命令顺序并要求 `v2_column_panel=0`，未来候选
需要独立、按候选签名严格检查的后继 checker，不能修改这次已封存的检查器。

## 9. 本轮测量缺陷与处置

原始编译和第一次冒烟 worker 在最后 JSON 输出时误将 `flush=True` 传给
`json.dumps`。编译文件和原始失败状态均保留；镜像另经精确驱动版本与
全部产物哈希审计，修正后的普通 RVV 冒烟实际重跑通过。

原 Q6 测试错误要求完整调用 `vcsr=0`，但量化器明确使用 RNE vnclip，
反汇编中 `csrwi vxrm,1` 位于 `0x80000a24`；原退休轨迹每次都执行此写入。
`vcsr=2` 正好表示 `vxrm=1, vxsat=0`。原两次输出、Q8 和 guards 无错误，
但测试仍报 `errors=2`，原记录和原 campaign 总状态继续为 FAIL。

新增 CSR 后继程序直接观测量化后的 VCSR/VSTART，并要求 QBS 后原样保留，
不在量化后重置 CSR。新 ELF 在相同镜像上重跑 PASS；原失败日志不会被新
checker 接受。该后继的 SDK、llama 和四份数据与原构建逐文件一致。

独立复核随后要求补原始输入 payload 完整性。最终 ELF 在不修改原 profiling
函数或 CSR checker 的前提下，用外层入口在两次调用后检查 payload，再次
同镜像运行通过；本文 Q6 周期全部取最终 ELF，而非将旧周期追认为新测量。

F16 checker 的显式后继仅允许严格整行 `UVM_ERROR : 0`/`UVM_FATAL : 0`
汇总，不接受非零计数或真实事件，也不改写原日志。独立 UVM 始终另行检查。

这些是本轮测量设施问题，不是通过修改 RTL 消掉的处理器功能错误。

## 10. 复现、验收与版本管理

```sh
python3 -B verification/performance/chain_profile/current_results.py \
  --q6-run /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/chain_q6_integrity_vcs_20261107_01 \
  --f16-run /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/chain_profile_runs_20261107_01/f16 \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/chain_profile_reconciled_NEW
```

输出目录必须不存在。`result.json` 保存全部调用、phase、命令服务周期、
边界与窗口；`call_partition.csv` 保存可加和调用区间；`evidence-pins.json`
保存重审输入身份。失败或不完整运行不能进入该报告。

| 计划要求 | 当前证据 |
|---|---|
| 面积基线、配置、依赖和实际镜像固定 | frozen source inventory、编译身份审计及同镜像 hash |
| 两条真实输入与完整规模 | 原捕获回执、R4 裁剪和 host golden 审计、137 token 不裁剪 |
| 普通 RVV、新 Q6、F16 正确性 | 三个实际运行 PASS；Q6 两次、F16 四次完整调用 |
| 数值、CSR、guard、工作量及独立协议 | 各运行原始数值检查和独立 UVM PASS，执行后 pins 一致 |
| 原始输入完整性 | Q6 目标机 F32/权重 115712 B 签名核验；F16 每调用原始数据和 guard 指纹核验 |
| 完整周期、阶段和引擎活动对账 | `chain_profile_reconciled_20261107_03/`，四条 QBS 与 4184 条 AKV 命令逐条核对 |
| 观察开销不被假设为零 | F16 ABBA 实测 +158 cycles；空探针不作固定扣除 |
| 源码根因与低面积下一步 | 本文第 4–8 节，区分供给、重复重放和已存在的运行时优化 |
| 不扩大研究范围或误报收益 | 无生产 RTL/SDK/llama 修改，无综合、无整模型速度结论 |

本轮脚本测试覆盖测量工具、拒绝路径和实际构建产物；它们是 host 单元测试，
含继承复用测试，不是同等数量的独立 RTL kernel 或新全回归。运行 Q6 的
产物测试时需设置 `Q6_INTEGRITY_BUILD` 为上述最终构建目录，不能把跳过计为通过。
最终执行为根目录 27 项、Q6 目录 104 项、F16 目录 22 项，全部通过且无跳过。
本轮运行结束后无未完成的 profiling VCS 子进程。原有无关工作区修改未纳入
提交，原始失败证据和旧报告未删除。
