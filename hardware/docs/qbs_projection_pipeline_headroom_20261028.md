# 当前 QBS 投影路径的剩余优化空间

## 范围与证据

本分析使用已经通过数值与协议检查的
`verification/out/m4-packed-qkv-vcs-20261027-01/`。这是完整 Q/V/K 投影切片，
M=4、K=1536，总计 8192 个输出，每轮 64 条 QBS 命令；不是完整 Transformer
层或端到端模型运行。四轮采用不复用、复用、复用、不复用的 ABBA 顺序。

已有软件改进减少了重复 Query/activation 准备，配对总周期从
1,659,464 降至 1,166,072，测得 1.4231 倍。这里进一步分析复用后的剩余硬件
活动，不把软件收益再次算作硬件收益，也不与其他切片的加速比相乘。

新分析工具 `verification/qbs/m4_prepared_reuse/analyze_pipeline.py` 执行了：

1. 核对原始 PASS 回执、source-pins 清单哈希、UVM 状态及完整日志哈希。
2. 核对五个当前 QBS RTL 模块与测量时封存的哈希一致。
3. 将 256 条命令严格归属到四轮，每轮 64 条，核对顺序、配置和故障状态。
4. 对每条命令检查互斥 phase 的和等于 busy，并核对候选阻塞的分类和。
5. 将日志中的四轮计时逐字段对照原始数值验收结果，而不是重新接受一段
   只有性能计数、没有正确性证据的日志。

输出：`verification/out/m4-qkv-pipeline-audit-20261028-01/result.json`。
SHA256：`a1d8a0e65a54fa701aacd2f5a94157dccf12d23ca5afc0335269c31cc055fd30`。
这是新分析，未进行新仿真；原始数值/协议 PASS 不是由分析工具重新产生。
两项工具测试包含完整有效序列，以及错序、错误 phase 和、错误容量、错误
阻塞分类、失败命令、被修改的计时、重复日志和未完成日志等拒绝场景。

## 实测活动

下面为复用后的第一轮（trial 1）；trial 2 的 QBS 活动计数相同，总调用为
582,537 周期。

| 项目 | trial 1 |
|---|---:|
| 完整切片总周期 | 583535 |
| admission | 6331 |
| activation 准备 | 97731 |
| execute 区间 | 478448 |
| QBS busy 周期总和 | 447414 |
| dot 发射周期 | 393216 |
| dot 发射 / QBS busy | 87.8864% |
| 有效整数乘积对 / 发射容量 | 12582912 / 12582912 |
| tile 数 | 3072 |
| compute 状态下未发射 dot 的周期 | 18432，即每 tile 6 周期 |
| 严格 WAIT_WEIGHT 周期 | 0 |
| tile context 启动被阻止周期 | 0 |
| integer result 等待 FP 接收周期 | 0 |
| FP 输入或 cast 输入被反压周期 | 0 |
| 有 FP entry、但没有可调度 uop 的周期 | 6144 |
| correction pending 周期 | 221184 |
| result pending 周期 | 49152 |

`execute` 占总调用约 82.0%，但不能把它全当作等待。每个 dot 发射周期已经
处理 32 对乘数，该测试填满了这部分发射容量。

## 计数器实际表示什么

### dot 发射不是物理功能单元利用率

`qbs_profile_engine_int.sv` 在 `compute_active_q && issue_active_q` 时增加
`dot_active_cycles_o`。`pair_capacity_o` 每次增加 `row_count_q * 8`；本测试
row_count=4，故每次容量为 32。M=1/2/4 分别每 context 推进 8/4/2 个 K 元素，
总乘法吞吐保持不变。

因此 100% 的 `useful_pairs/pair_capacity` 表示发射出来的乘积槽被填满；
87.9% 表示 dot 发射占命令 busy 的比例。二者都不是整条 lane、FP 单元或整颗
处理器的真实计算利用率，不能用前者宣称“硬件利用率 100%”。

### phase_overlap 不是等待

`qbs_engine.sv` 在 compute 状态且 reader 仍 busy 或存在 weight range 请求
时将周期归为 overlap。这与是否被访存阻塞不是一回事。该分类与其他 phase
互斥，可以作为活动分布；不能将 overlap、read outstanding 或 pending 计数
再相加成一份 stall breakdown。

权重前取并不是完全没有开销：本轮 weight phase 为 18,486 周期。但严格
`QBS_WAIT_WEIGHT` 为 0，表示没有在该等待状态中滞留。不能据此声称内存不
消耗周期，也不能据此判断增加预取深度必然有效。

### pending 不是反压

`qbs_compute_engine.sv` 的 `probe_profile_result_pending_cycles` 仅检查任一
result pending 位为 1；`probe_profile_correction_pending_cycles` 仅检查任一
correction slot 有效。这些是工作在途的占用观察。

真正的 result 阻塞条件是 `integer_result_valid && !fp_request_ready`，本轮
为 0。因此，不能因为 result pending 有 49,152 周期，就将它们解释为可通过
扩大队列消除的等待。FP entry table 的高占用同样需要配合实际 ready/valid
阻塞判断，不能单独作为扩容依据。

## 六周期间隙来自哪里

当前整数 tile 完成条件包含：最后一组输入已发出、s0 无效、dot metadata
流水线已空、dot 输出无效。`compute_active_q` 在这之后撤销并产生 `done_o`，
上层才能推进 tile/权重 bank。`qbs_dot_array.sv` 内有 quant、product 和
reduction 输出寄存级，格式和 context 元数据与之对齐。

这解释了每 tile 固定的无 dot 发射尾段，但它并不证明六周期可以全部删掉。
如果要允许相邻 tile 的 dot 在途重叠，必须同时处理：

- decoder 当前 profile/M/row_count 与 s0 输入的对应关系；
- 在途 dot 与 context/profile、subgroup 和 scale 元数据的对齐；
- 上层完成脉冲、tile 计数及权重 bank 清理/复用的时刻；
- correction slot 的吞吐和小 M 尾波的 drain 限制；
- 旧 context 仍有结果待消费时不得被重用。

不能仅把 `start_ready_o` 中的 busy 条件删掉，或提前产生原有 `done_o`。
当前两个 context 的作用包括整数结果/correction 排空与后续工作的重叠，
并不等于上层已经支持任意两个 dot tile 同时发射。

## 优先级结论

复用后两轮总周期为 1,166,072：

| 假设，其他工作不变 | 乐观估计的切片加速比 |
|---|---:|
| 完全移除 compute 状态下所有无 dot 发射周期，共 36864 周期 | 1.03265 倍 |
| 完全移除 QBS busy 中所有非 dot 发射周期，共 108396 周期 | 1.10249 倍 |

这些是假设所对应的同工作量估计，不是优化后实测，不是全模型收益，也不是
对所有微结构变化的普遍上界。第二项还把必要的 activation/weight 装载、结果
提交和排空都理想化移除了，实际无法按该假设直接实现。

这组证据不支持“先扩大 FP/result 队列”或“简单翻倍 dot 阵列”。相同吞吐
预算下，单纯消除 tile 切换尾段的完整切片空间约为几个百分点，必须先证明
可以保持数值顺序、bank 生命周期和时序结构，再值得进入 RTL 修改。

当前优先收齐共享 RVV 回调下的 Prefill 完整调用配对，判断分组后软件检查、
K 面板、V 解码和在线 PV 各自还占多少。QBS 的上述 RTL 保持不变；没有因
计数器名称而盲目扩容，也没有将这次分析计作新的性能提升。
