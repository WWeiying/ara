# 投影驻留容量：下一项硬件工作的可行性约束

## 1. 这项核查回答什么

完整推理目标允许适度增加面积，因此需要比较增加少量片上存储与增加计算资源的
价值。本轮先检查当前 activation context 为什么不能覆盖一些常用 Prefill 形状。
没有修改 RTL、SDK 能力声明或生产调度，也没有执行新的模型、VCS 或综合。

工具 `verification/performance/end_to_end_baseline/context_capacity_study.c` 调用
正式 SDK 的 planner 和 context 准入函数。假设容量分别为 4672、9344、18688、
37376 B，检查相同的调度，而不是手写一套乐观调度器。另有假设 max blocks=255
的分组，用于分离存储容量与 block 数限制；它不是当前硬件可配置的模式。

输入矩阵使用 Qwen3-1.7B 投影维度 N/K=2048/2048、1024/2048、6144/2048、
2048/6144；M=1/4/8 是调度扫描。九种 profile 是替代量化选择，不能理解为一次
真实模型同时执行了这些 profile。共 864 项，包括边界、MAC 总数守恒、逻辑流量
和四个手算锚点检查。没有传入真实张量或执行矩阵计算。

运行：

```sh
python3 -B verification/performance/end_to_end_baseline/run_context_capacity.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/context_capacity_next
```

结果及构建、依赖哈希保存在唯一验证工作树的
`verification/out/e2e_context_capacity_20261106_02/`。

## 2. 当前资源与明确限制

| 位置 | 已确认的机制 | 对扩展的约束 |
| --- | --- | --- |
| `qbs_activation_context.sv` | 当前 payload 容量 16*292=4672 B，分成两个相邻行交错 bank | 扩容要重新检查 bank 深度、SRAM 实例映射，不是凭空增加可用容量 |
| `qbs_pkg.sv` | context max M=8、max K blocks=32，查询中 block 数减一用 5 bit 表示 | 仅改 SDK 的最大 block 数会与硬件契约不一致 |
| `qbs_activation_context.sv` | ExtendedShapes 的完成标签是 32 位；block byte offset 是 13 位 | 大容量必须同步检查标签与地址范围，9344 B 已超过 13 位字节地址范围 |
| `qbs_compute_engine.sv` | 普通 lookahead 按 K 奇偶选择两个 activation bank；wide-M 则按上下 wave 使用它们 | 增大 M 不会自动保留原先的下一 K-block 预取重叠 |
| `qbs_dot_array.sv` | 各模式都使用 32 个 INT8 乘积槽 | 调度、容量或 M 的变化不会自动增加算术吞吐 |

当前 context 只有一个，填充/复用/释放仍受 ID、generation、布局和 profile 匹配
约束。这些条件不能因增加容量而删除。生产路径不会使用本工具修改后的假设能力。

## 3. 具体例子

M4/N2048/K2048，Q4_K 权重搭配 Q8_K 激活：

```text
每个输入行：2048/256 * 292 = 2336 B
四行激活：4 * 2336 = 9344 B
N32 输出块：2048/32 = 64 个
```

| 假设 | context 是否符合正式 planner 准入 | 激活逻辑外部递送 |
| --- | --- | ---: |
| 当前 4672 B / 32 blocks | 否 | 598016 B |
| 假设 9344 B / 32 blocks | 是 | 9344 B，计入首次填充 |

权重流量和数学工作不变；这里只消除多个 N tile 对同一份激活的外部重读，内部
context replay 仍存在。上述差值既不是 DDR 实测流量，也不是周期或加速比。
如果直接读取已经被计算隐藏，扩容仍可能没有明显收益。

同样的 M4/K2048，Q8_0 激活则是 64 个 block，每块 34 B，四行共 8704 B。
9344 B 存得下，但当前 max blocks=32 仍拒绝。假设同时扩展 block 能力才准入。
因此不能把 K-quant 的容量结论不加区别地推广到 Q4_0/Q5_0/Q8_0/IQ4_NL。

M4/K6144 的 Q8_K 激活需要 28032 B。两倍容量仍不够；若希望同时覆盖此类 FFN
输入，要比较更大容量、K 条带加部分和状态，或保留 DIRECT，而不是默认统一扩容。

## 4. 扫描结果的正确解释

保留当前 32-block 上限时，各容量在 108 个 profile/shape/M 组合中的准入数为：

| 假设 payload 容量 | 准入组合数 / 108 |
| ---: | ---: |
| 4672 B | 15 |
| 9344 B | 35 |
| 18688 B | 50 |
| 37376 B | 55 |

这不是模型覆盖率、调用命中率或执行时间占比。每种 profile 在扫描中等权，真实
模型的张量类型、实际 M、切片和开关不同。更大容量的边际准入收益下降，也说明
block 数、结果容量、布局和 M 尾块等约束会继续存在。

## 5. 进入硬件实现前的决策门槛

1. 先核对当前最佳 Prefill 后端实际产生多少个可复用 M4/K2048 调用，激活读取
   是否有未被隐藏的周期成本，不能只按省下的字节决定扩容。
2. 比较 9344 B 的小幅扩容与有界 K 条带。后者需要保存/恢复部分和、累积异常
   标志和 K 游标，不能仅复用上一条命令的 accumulator。
3. 若扩容，统一参数化容量、地址、完成标签、SRAM 映射和能力查询，并保持旧
   capability 编码的兼容性。不能把本工具的 255-block 假设直接写进旧 5-bit 字段。
4. 保留普通 RVV 与现有 DIRECT/M4 路径；新机制只在成本有依据的形状选择。
5. 对比完整投影的准备、FILL、所有 REUSE、RELEASE 和结果提交，而非单独测
   稳态 REUSE 命令。只有完整调用有收益，才考虑集成到实际模型。

结论是“小容量扩展有明确的适用形状，但不是无条件有效的改进”。下一项 RTL
方案仍需结合正在运行的 Attention 实验及端到端投影占比选择，不在本轮预先承诺
面积或性能收益。
