# 推理全链路性能画像：面积优化基线

## 1. 本轮做了什么

本轮回答的是：现有加速机制在完整调用链中，是否被准备、调度、搬运、
同步或实现中的额外工作抵消。先复查当前代码和已保存的真实执行记录，
不恢复已归档的扩阵列、扩接口、Output-Tile 等实验，不修改生产 RTL、
SDK、llama.cpp 或 FPGA 副本，也不启动综合或长仿真。

这是一次新的原始证据复析，不是新的硬件性能实验。主要结果：

- 投影中已测的主要工作仍是有效点积，不是 FP 队列堵塞；目前没有证据支持
  通过扩 FP/result queue 获得显著收益。
- 完整投影调用仍有准备及命令边界成本；软件准备缓存与硬件 activation
  驻留不是同一件事，不能因前者 hit 就认为后者也复用了输入。
- 量化 Attention 的主要缺口应继续从在线更新、输出向量往返、准入检查和
  Prefill 分组复用范围调查，而不是仅优化 QBS 的 QK 点积。
- 实际板测还存在 F16 AKV 路径，不能把量化 KV 的热点当作 F16 的热点。
- 整模型各算子的真实硬件周期占比仍缺少与当前全树一致的测量，不能把切片
  占比、QEMU 时间或函数前的退休间隔拼成一份整模型 stall breakdown。

## 2. 版本和证据可信范围

| 项目 | 本次固定位置 |
|---|---|
| Ara 分支 | `ara_dsa` |
| Ara HEAD | `8d9ef7cee26860d64f1a6d6506056584f79a3a7b` |
| Ara 提交树 | 与面积阶段末尾 `71468b1c3` 相同 |
| llama.cpp 分支 | `qbs-activation-context` |
| llama.cpp HEAD | `b5da29fde5a986dfc005a5de1c8b06a3479b51c4` |
| llama.cpp 提交树 | 与 `8ed9403e3` 相同；原有未提交工作保留 |
| 本轮分析工具 | `verification/performance/chain_profile/profile.py` |
| 最终分析输出 | `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/chain_profile_20261107_02/` |

工具重新核对两组 VCS 记录的原始 PASS 回执、source-pins 清单哈希、实际
ELF、原始日志和 vector trace 哈希，以及独立 UVM 的 PASS/无 issues。
随后重跑原来的完整数值/活动检查器，而不是只读取结果中的一个 cycles。
工具自身的七项单元测试覆盖正常求和及重复记录、缺失工作、错误顺序、
错误周期、失败命令和错误时间嵌套的拒绝行为。

当前 Dispatcher、VLSU 与全部已钉住的 QBS RTL 文件和 10/29 测量版本一致。
但整 SoC 不同：`ara_pkg.sv`、`operand_queue.sv`、`simd_alu.sv`、
`simd_mul.sv`、`vector_regfile.sv`、`vmfpu.sv` 存在面积阶段的变化；
Attention 记录中的 `qbs_runtime.c` 也早于当前的接纳扫描/iterator 代码优化。
具体逐文件结果写入 `source_comparison.csv`。

因此，下文周期是**保留机制的有效历史实测**，不是将面积优化后的整个
当前 RTL 重新跑过的结果。与当前匹配的模块可以支撑对应的静态归因，
不能据此宣布整个新 SoC 周期相同。未提交的 AKV 汇编也不自动属于固定
SDK 交付；后续构建必须记录究竟使用提交版还是工作区版。

## 3. 先区分实际执行路径

```text
llama_decode / GGML graph
  |
  +-- 量化线性投影
  |     F32 activation -> Q8 准备/准备缓存 -> QBS planner
  |     -> descriptor / fence / vset -> QBEXEC
  |     -> VLSU 接纳 -> 读取/解包/点积/缩放 -> VRF commit -> 输出 store
  |
  +-- F16 KV Attention
  |     AKV FULL/REFILL -> context SRAM -> QK 的普通 RVV 算术
  |     -> mask/online softmax -> PV 的普通 RVV 算术 -> release/output
  |
  +-- Q4_0/Q8_0 K、Q8_0 V Attention
  |     准入扫描 -> query 量化 -> 必要的 K panel
  |     -> QBS QK -> 在线 softmax -> RVV value decode/PV -> output
  |
  +-- 其余算子或不满足准入条件
        正常 GGML/RVV/scalar fallback
```

AKV 不是一块替代所有 Attention 算术的独立矩阵阵列。F16 路径通过专用
context/read/replay 组织数据，再使用 RVV；量化路径则由 QBS 计算 QK，
其余在线更新主要由 CPU/RVV 完成。两者的瓶颈及可用计数器不同。

## 4. 投影：算术主导，但调用边界仍需拆清

证据：`qbs-retire-projection-vcs-20261029-01`。真实 M4、K1536 的完整
Q/V/K 输出切片，每试次 64 个 QBS 命令；选取已经启用 parallel sums
及软件准备复用的 ABBA 中间两次。不是完整模型，也不含图中的中间算子。

### 4.1 完整切片的互斥记账

| 区间 | 平均周期 | 占完整切片 |
|---|---:|---:|
| planner/admission 区间 | 6114.5 | 1.12% |
| activation 准备区间，包含已启用的准备复用 | 65924.5 | 12.03% |
| QBS engine busy | 444404.5 | 81.12% |
| execute 区间内、engine busy 之外 | 30496.5 | 5.57% |
| 其他计时边界余量 | 916.0 | 0.17% |
| 合计 | 547856.0 | 100% |

`execute - busy` 不是纯软件开销，也不是已证明可以删除的排空时间。
其中可能有 descriptor 构造、调用、fence、vset、接纳前等待、结果存储和
其他同步。当前 SDK 还包含本次历史 ELF 没有的 iterator 优化，因此不能
把这 5.57% 原封不动地当成当前全部冗余。

### 4.2 命令内部的有效工作

| 计数 | 每试次平均值 | 正确解释 |
|---|---:|---|
| dot issue | 393216 cycles | 占 engine busy 88.48%；不是整处理器利用率 |
| useful pairs / issued capacity | 12582912 / 12582912 | 本形状发射出的乘积槽全有效 |
| tiles | 3072 | 内部计算 tile 数 |
| compute without dot issue | 15360 cycles | 每 tile 5 周期 |
| strict WAIT_WEIGHT | 0 | 此 M4 点未在严格等待状态中滞留 |
| context-start / result / FP-input blocked | 均为 0 | 本点未证实这些接口反压是瓶颈 |
| FP table full | 147456 cycles | 在途表占用，不是可直接删除的 stall |
| correction pending / result pending | 221184 / 49152 cycles | 重叠的在途状态，不能相加成损失 |

当前 `qbs_profile_engine_int.sv:265` 保留 `!compute_active` 和 context
生命周期约束；`:272` 已经包含最后一个 dot 的 retiring 条件。旧文档中
每 tile 六周期不是当前保留实现的值。本次原始日志复算为五周期。

在工作量、发射能力及其他时间都不变的假设下，即使把全部 15360 个
compute-without-issue 周期理想地删掉，完整切片也只会变为：

```text
547856 / (547856 - 15360) = 1.028845x
```

这是约 2.9% 加速的条件预算，不是已实现收益；其中包含必要的管线尾部，
不能简单提前 done 或撤掉 bank/context 保护。它也不限制其他形状、减少
实际工作量或改变访存/准备路径的优化。

### 4.3 两种复用不能混淆

当前硬件 activation context 为 4672 B；这组 M4/K1536 的 Q8_K payload
为 `4 × 6 × 292 = 7008 B`。当前 SDK 在
`software/qbs/src/qbs_runtime.c:699` 正确检查容量和 layout，因而该形状
不满足整个输入 tile 的硬件驻留条件。

日志中每试次软件 cache 有两次 hit，但命令均是 DIRECT，activation
读取 payload 为 `64 × 7008 = 448512 B`。软件 cache 避免再次量化，
没有自动消除硬件读取。相对本试次 weight payload 1870848 B，这部分
activation payload 确实存在；它不是板上 DDR 字节数，也不能直接换算
成相同比例的周期损失。

不应据此立刻增加 context SRAM。M1 已有默认启用的跨算子驻留，而长 K、
split-K、M4 layout 和容量分别有边界；历史条带化方案还因命令/commit
成本退化。应先测实际选路和完整调用，再决定是否值得改变组织。

### 4.4 M1 Decode 需要独立检查供给

当前四 lane 默认宽接口为 128 bit，即最高 16 B/cycle。
满四个权重行、K256 时，Q4_K payload 为 576 B，Q6_K 为 840 B；单独搬运
至少需要 36/53 个 beat，而满行 M1 的 dot 发射只需 32 周期。连续 tile
的摊销下界还要考虑 beat 对齐、突发、bank 切换和已有双范围前取。

这说明**M4 的零 WAIT_WEIGHT 不能证明 M1 Q6_K 不受供给限制**，不是证明
板上 DDR 已饱和。最有区分力的下一条投影测试应为真实 M1 Q6_K，而不是
再重复测同一 M4 满算术点，也不是简单扩大 dot 阵列。

## 5. Attention：先辨路径，再检查数据往返和准入

### 5.1 已接受的完整量化 Decode 调用

证据：`register-retirement-final-20261029-01`。真实 Qwen3 query19，
GQA2、D128、20 个可见 token、Q4_0 K/Q8_0 V。256 个输出与配对路径逐位
一致，FCSR/VCSR、guard、活动及独立协议检查通过。

| 路径 | 两次周期 | 平均周期 |
|---|---|---:|
| shared RVV value/PV | 48038 / 47727 | 47882.5 |
| Register-PV | 43431 / 42714 | 43072.5 |

这一增量为 1.111672x；不是最初的普通 RVV 对 QBS/AKV 加速比。
本记录没有开启 `QBS_PERF`，所以这里**没有**将旧程序的 702/703 busy
周期补到新程序上，也没有宣称剩余时间都在 scalar。

同一 UART BEGIN/RESULT 窗口的实际 offload 计数还显示：vector load
178→130、store 140→52、vset 159→71、arithmetic 343→363。
它支持“减少部分向量访存和配置工作”的结论，但窗口还包括设置和检查，
不能用这些数除以 43072.5，宣称得到精确 ROI IPC 或 DDR 带宽。

### 5.2 Register-PV 仍按 token 读写输出

`software/akv/experimental/quantized_kv/register_pv/online.h:65` 遍历 token，
每次进入 `kernel.h:41` 的 PV update；其中 `:55` 载入输出，`:58` 再写回。
现有寄存器复用是把 V 解码结果直接送入多个 head 的 PV 更新，并不是把
输出 accumulator 跨全部 token 常驻寄存器。

按源码循环，仅输出更新的逻辑读写量为：

```text
2 × heads × dim × sizeof(float) × visible_tokens
```

| GQA2、D128 | 逻辑输出更新读写量 | 最终输出大小 |
|---|---:|---:|
| T20 | 40960 B | 1024 B |
| T128 | 262144 B | 1024 B |
| T1024 | 2097152 B | 1024 B |

这是算法实现对应的逻辑工作，不是 AXI 或 DDR 实测，也不是这些流量全部
可以消除。QBS 命令占用 VRF、函数 ABI、在线最大值/归一化顺序、scalar
系数和跨 token 依赖都限制了 accumulator 保留方式。应先定位真正的
数据依赖及有效工作，再考虑用现有寄存器改善组织；本轮没有修改实现。

### 5.3 准入及 panel 整理随上下文增长

`selection_strided.h:70` 扫完整 mask；`:103` 扫 query；`:122` 检查
可见 K/V block 的 scale。KV8、D128、T137 时，单次 scale 检查对应
`2 × 8 × 137 × 4 = 8768` 次字段读取，尚未包括 mask/query。
这些检查保证非有限数、布局和数值前提，不能直接删除。

`runtime_strided.c:38` 为跨步 K-cache 整理连续 panel，一个 KV head/tile
内可复用，但后续 tile/调用仍有复制工作。实际成本应分离为准入扫描、
panel 整理及命令，而不能全部算进“QK 太慢”。

`llama.cpp/.../arch/riscv/quant-kv.cpp:83` 的 Prefill 每次有 malloc/free；
Decode 则在 `:155` 使用栈 workspace。分配成本目前没有可靠周期占比，
不能将其写成已经证实的主要瓶颈。

### 5.4 Prefill 的复用止于当前 query 组

`prefill/execute.h:53` 每次最多把八个 query-head 行组成一组；GQA2 时
对应四个 query。`:60` 进入下一组清 panel 有效性，再遍历该组的可见前缀。
因此组间仍可能重复 K-panel/V 处理，不能把“组内复用”描述成整个 prompt
只读一次 KV。

已收齐的 135-query 板测中，每 KV head 的组前缀为
`4+8+...+132+135 = 2379` 行；乘 28 层和 8 KV heads，恰为 532896，
与原始计数一致。这是 V 行处理次数，不是不同 V 行数量，更不是读事务数。
相关记录位于
`/home/wangwy/fpga_runs/optimization_board_proof_20261105_01/native_answer_observer_06/result.json`。
本轮未为这条辅助记录重新执行整个板测；历史对照仅用于解释组边界。

不能因为存在重复就恢复被拒绝的 V-cache 候选：原来的 pointer-cache
完整调用反而慢约 3.84%/4.27%。重复工作、保存/索引开销和寄存器压力
要一起计量。

### 5.5 F16 AKV 的缺口不是上述量化 PV 的同一条路径

当前 F16 native 调度在 `software/akv/src/akv_v2_native_riscv.c:625`
依次完成 FULL/REFILL、QK、Softmax 和 PV；上下文/共享 reader 提供数据，
算术仍使用标准 RVV。`hardware/src/vlsu/vlsu.sv:700` 要求本地普通访存
排空，Dispatcher 对 QBEXEC 等操作另有 Ara idle 屏障。

这里可能限制吞吐的是：接受命令前的排空、reader 等待、context SRAM
读取/重放、VRF 最终写回以及 RVV 算术依赖。它们尚没有在当前整树上被
分别量化。旧量化路径使用 Newlib `expf` 的热点也不能套在已有向量指数
实现的 F16 路径上，Linux libm 与裸机 Newlib 又不相同。

准入边界也要和性能故障区分：F16 Prefill 保留与上游 tiled 数值契约一致
的最小 query 阈值；量化 Prefill 有自己的最大 query/特性限制。返回
fallback 可以是有意保持正确性的行为，不等于硬件卡住。必须用真实运行
计数确认落在哪条路径，不能只看环境变量声称已开启。

## 6. 整个应用：内核快，不等于用户等待按同比例缩短

本轮另外复核了一组已有真实板测观察，重新校验原观察者封存的 55 份
输入，并按四个原始 case 重新求和。不是本轮新板测，也不是关闭全部
硬件机制的 no-QBS 基线：两侧是相同位流、F16 KV 上的软件组合比较。

| 合计范围 | 原软件，秒 | 候选软件，秒 | 加速比 |
|---|---:|---:|---:|
| prompt eval | 4558.76303 | 3310.94867 | 1.3769x |
| decode eval | 2647.16506 | 2141.96137 | 1.2359x |
| inference | 7246.14 | 5522.84 | 1.3120x |
| host 完整等待 | 9813.05892 | 8140.82743 | 1.2054x |

四个 prompt 为 135/212/676/174 tokens，输出为 41/70/33/94 tokens。
原记录四个回答和 native 工作计数一致；只有第一项保留了与原基线逐位
比较的完整 logits，不能将其扩大成四项全部 logits 相同。

候选中 host-minus-inference 为 2617.98743 秒，占完整等待 32.16%。
这段包含未拆分的装载、进程/通信及其他应用工作，不能全称为模型加载。
这组测试是每 case 单独进程/加载，不能据此断言一个已经常驻模型的连续
对话服务也有同样损失。它说明 profiling 需要同时报告冷启动和常驻模型
执行，不能用一个切片加速比代表用户体验。

原始观察入口：
`/home/wangwy/fpga_runs/optimization_board_proof_20261105_01/final_e2e_observer_01/`。
本轮没有把板上软件/位流身份等同于当前面积优化源码。

### 6.1 当前运行时仍有可疑的高频观察开销

当前 `llama.cpp/.../arch/riscv/qbs.cpp:488` 在每次 `record_command` 中
查询 `GGML_RISCV_QBS_TRACE`；`:1075` 在每条成功 native command 后进入
该函数。关闭打印并不等于完全不存在环境查询；开启 trace 后还会执行
多项原子计数和其他选项检查。对于百万条命令，这是一条高频 scalar 路径。

这是当前源码事实，但本轮没有测得其独立周期或证明它是首要损失。前述
板测把 trace-hoisted 软件与 M4 组合一起比较，不能把 1.3120x 全归功于
减少 getenv，也不能把候选当成当前工作区已经包含的实现。若要调查，应
在一次操作进入时获取观察选项，保持该操作内计数策略不变，再用同任务
的 trace OFF/ON 对照测量开销；不能为提高数字而关闭所需的准入或正确性
检查，更不能用全局永久缓存破坏测试允许的运行时选项切换。

## 7. 下一轮最小测量集合

优先解决“损失在哪里”，再决定是否修改硬件。以下不是已启动的任务。

| 优先级 | 测量 | 必须区分的事件 | 对决策的作用 |
|---|---|---|---|
| 1 | 实际 GGML 调用/选路 | F16/量化 KV、fallback 原因、真实 M/N/K、可见长度；关闭逐调用打印 | 先确保优化的是实际运行的路径 |
| 2 | M1 Q6_K Decode 投影 | 最后数据到达、bank-ready、dot issue、WAIT_WEIGHT、AR/R 握手 | 区分带宽、响应延迟和调度，不从 M4 外推 |
| 3 | 一个完整 F16 AKV Decode 调用 | 准入、FULL/REFILL、QK、Softmax、PV、release/output | 补齐当前实际板测路径的阶段画像 |
| 4 | Register-PV 的完整调用 | 准入扫描、query 量化、K panel、QK、在线系数、PV、结束 | 判断输出往返还是控制/系数计算更值得优化 |
| 5 | 连续两条真实 QBS 命令 | 首次请求呈现、command_fire、terminal、最终写回/store 完成 | 将 pre-drain 与 SDK、必要依赖、后处理分开 |

VCS 优先采用真实数据、完整 K、有限输出行数的切片，不缩短到只有初始化
或单个极小 tile。固定相同 ELF/输入和单 worker；普通 RVV/fallback、输出、
CSR、canary 及独立协议检查保留。对预计超过十分钟的任务应独立后台运行，
先确认实际模拟器推进，然后退出轮询；有足够区分信息就不重复试参。

采样可复用已有 commit monitor、QBS phase/probe、AKV phase 接口和有界
波形，原则上不需要增加生产数据通路或队列。每次捕获至少记录版本、配置、
计时 ROI、命令关联号与漏失/截断标志。

整图计时应放在原 CPU 执行循环，保留 fusion group、graph epoch 和准备
缓存生命周期。不要通过逐节点 callback 拆图；原有 graph probe 的 QEMU
通过只证明数值和记账，不能产生真实硬件算子百分比。尚未测到的项留空，
不拿 pending/full 或下一条 PC 前的 gap 替代真实 stall。

## 8. 当前判断与边界

现有记录未证明存在一个通过删除某个 busy/idle 判断就能安全解决的全局
性能错误，也不支持为了性能先扩大计算单元和 buffer。可确认的是，
**投影的剩余空间与 Attention 的剩余空间不同，且应用边界会稀释局部收益**。

当前最值得调查的顺序是：实际选路与观测开销、M1 Q6_K 的供给、F16 AKV
的阶段时间、量化 Attention 的输出/系数/准入工作，最后才是上述历史 M4
切片中平均每 tile 五个 compute-state 无 dot 发射周期。这不是所有形状
或完整 tile 交接间隙的统一数值。不能将任何一项未经测量就宣布为当前整
模型的首要瓶颈。

本轮没有发现并修复新的功能 bug，没有宣称新的性能提升，也没有重新引入
已归档的大面积候选。输出是一份可复算、区分已知和待测部分的性能基线。
