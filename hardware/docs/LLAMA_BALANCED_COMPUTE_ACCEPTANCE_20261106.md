# 量化矩阵计算的平衡吞吐候选

## 1. 解决的问题与当前决定

单独增加 scale MUL 只能使原 66 项组件服务时间改善约 0.6%，没有解决完整
计算链的主要约束。以满 M4、四 weight rows 的一个 256-element block 为例，
16 个输出流的原 dot 至少需要 64 个发射周期；Q4_K 的 scale MUL 与 FMA 也
合计需要原算术端口的 64 次发射。因此，单独增加整数乘法或单独分离 scale，
都不能形成平衡的持续吞吐。

本候选同时调整三段服务能力，并保留其余数据组织：

| 环节 | 原 256 位供给计算基线 | 平衡候选 |
| --- | --- | --- |
| M3/M4、256-element profile 的 dot | 每输出流每拍 4 个元素，最多 64 products/cycle | 每流 8 个元素，最多 128 products/cycle |
| subgroup correction | 每物理 row 一个通道，合计 4 个 | 每 row 两个通道，合计 8 个；第二 grant 仅用于合格上下文 |
| FP32 scale MUL | 与 FMA 共用原算术端口 | 合格请求走独立 FP16×FP32 通路，其他仍走原 FPU |
| I2F / FMA | 各一个发射口 | 不变，不重排同一输出的 K-block 运算 |
| 输入窗口、SRAM、输出端口、FP entries | 原窗口、原容量、单结果端口、16 entries | 不变 |

候选已通过隔离 compute 的三镜像 VCS 验收，值得进入完整控制器和真实 SDK
调用评估。它仍未接入生产 SoC，不能把以下组件比例当作完整模型加速。

## 2. 为何修正通路也要扩展

Q4_K/Q5_K 的 subgroup 为 32 个元素，每块共需 128 次 correction；128-product
路径的 dot 下限为 32 周期，原四通道的修正服务率恰好够用。Q6_K/Q3_K/Q2_K
的 subgroup 为 16 个元素，每块需 256 次 correction，若仍只有四通道，下限
仍为 64 周期，新增点积资源不能兑现吞吐。因此使用每物理行两个局部通道，
而不是将所有修正请求放到一个更宽的全局选择器中。

每行只管理两个 context、各四个 activation stream，共八个候选。第一个 grant
保留原 round-robin 次序，第二个只能选择紧随其后的合格候选；不能跳过等待的
legacy owner 去服务更后的快速候选，以免连续补充的快请求使旧请求饥饿。
是否合格在上下文开始时保存，不依据已推进到下一波的实时 M 或 profile 判断。

原 correction 的 operand/product 两级流水、提交时读取 subtotal、唯一写入检查、
共享 subgroup metadata 覆盖检查和尾波排空约束均保留。dot 仍是三拍流水，
decoder 与 K cursor 同步按 8 前进，且沿用已存在的八路 quant 输入窗口。

## 3. 保持旧路径和数值契约

快速 dot 只适用于局部 M3/M4 波次和 256-element profile。M1/M2、32-element
格式，以及 M5/M6 的第二个 M1/M2 尾波不增加元素步长。第二 correction grant
同样受保存的上下文资格约束。

FP mixed 资格从实际返回的整数 context base 和完整 M 推导，在 request fire 时
存入对应 entry。随后即使调度器已经推进到下一波，也不会错用新的波次信息。
M7/M8 的第二波为 M3/M4，允许快速路径；M5/M6 的尾波不允许。

新缩放通路只接收已证明可精确执行相同 FP32 RNE MUL 的输入，保留 NX。零、
非有限输入、次正规 FP32 激活和危险指数范围回落原 FPU，原 HalfScale 优先级
也不变。I2F、两次 scale 与两次 FMA 的逐 accumulator 顺序没有改变；返回 tag
管理、并发 flags 合并和故障排空沿用上一轮已验证的实现。

`BalancedMatrixDot` 默认关闭。所有新模块通过精确 SHA 的可逆变换生成到独立
构建目录，未覆盖生产 RTL 或其他 worker 的输入。SDK、ISA 和量化 payload 不变。

## 4. 验证与实际结果

original、候选关闭、候选开启三镜像均使用物理 256 位输入和相同存储容量。
输入为此前封存的 76 项：原 66 项及 10 项边界测试。原 C oracle 的 payload、
输出和 flags 不变；候选仅修改 `C` 行中由硬件结构确定的 capacity/dot 两字段。
非快速 M1/M2 或短格式的 capacity 会计入更大阵列中未使用的位置，可能增加；
它不表示有效工作量或执行时间增加。

| 验收 | 实际结果 |
| --- | --- |
| 每镜像普通测试 | 76 项通过，覆盖九种 profile、布局、M/N/K 和尾波 |
| 每镜像原故障/恢复 | 各 5 次通过 |
| 原版与关闭候选 | 81 次执行的周期、压力、工作量、flags、浮点事件相同 |
| 开启候选的 M1/M2 或短格式 | 34 项周期完全相同 |
| 全部 76 项周期变化 | 42 项改善、34 项不变、无回退 |
| mixed 发射/返回 | 各 4245 次，NX 636 次 |
| mixed 与其他 FP 端口并发返回 | 3579 次，其中双侧 NX 184 次 |
| 最后一个新增 correction 通道 | 3824 次有效发射，资格与工作量检查通过 |
| NX-only 两项 | 各 64 次 mixed 发射/返回/NX，输出全零且 flags=NX |
| 额外故障 | mixed issue、mixed return、correction lane7 product 边界各一次 |
| 额外故障排空 | 分别 55、52、103 周期，随后恢复的 84 个输出及完整 FP 序列通过 |

这是实际断言和故障场景通过，不是断言覆盖率或系统级 signoff 声明。

### 组件服务周期

| 范围 | 原版＝关闭候选 | 开启候选 | 原版/候选 |
| --- | ---: | ---: | ---: |
| 原 66 项合计 | 32170 | 26601 | 1.20935× |
| 其中适用多行、长 block 的 32 项 | 21249 | 15680 | 1.35517× |
| 真实 M1/N8/K1536 切片 | 625 | 625 | 1.00000× |
| 真实 M4/N8/K1536 切片 | 1378 | 1002 | 1.37525× |
| 全部 76 项合计 | 37332 | 30521 | 1.22316× |

两项真实输入来自已接受的 Qwen2.5 Prefill 捕获，M1 是其中一行；不是新的
Qwen3 或 Decode 性能结果。计时包含确定性 stimulus transport，不含完整 reader、
MMU、SDK 准备、GGML 调用或模型执行。不按这组测试出现频率估算模型性能。

M4 真实切片的 dot issues 从 768 降为 384，correction 总量仍为 1536。
同时出现了 120 个 FP 输入等待周期，全部因请求对应的 entry 尚未释放，而非
同 accumulator 冲突。该等待可能与其他工作重叠，不能直接作为可消除周期相加，
也不据此立即扩大 entry 表。下一阶段先看完整调用是否被准备、读取或提交限制。

### 资源账目

相对同样 256 位供给的原计算配置，新增声明的算术位置包括 64 个 8×8 product
位置、四个 correction 通道及一个此前验证的 24×11 scale 乘法器。product
寄存数据增加 1024 bit，四个 correction 通道的两级 packed 数据合计增加
472 bit，另有资格、仲裁、缩放流水与组合逻辑。没有扩大 SRAM、输入窗口、
FP entry 数或结果端口。

这些是 RTL 结构账目，不是综合 cell area，也不包括此前 128→256 位供给扩宽
的成本。最终性能面积判断必须统计整个候选相对完整基线的成本；本阶段未综合。

## 5. 下一验收节点

1. 固定物理256位，验证完整 QBS controller 的默认关闭/开启、context replay、
   AXI 背压、读故障、atomic commit 和恢复；不能由 compute PASS 替代。
2. 验证非零 M4 seed、K continuation 和 seed abort/drain。保留现有 continuation
   能力，不通过关闭它绕过验收。
3. 构建独立 SoC 候选，补 M4 QBS→AKV→普通 RVV→QBS 的交接。旧只发 M1 的
   handoff 不足以覆盖新增快速流水。
4. 使用同一真实 Qwen3 Full-QKV ELF、随后 FFN triplet ELF，与原镜像配对。
   保留输出、guard、CSR、完整 K、准备与提交时间。只新增按结构精确检查
   微架构计数的 successor checker，不放宽原 numerical/protocol 检查。

真实 Full-QKV/FFN 的 ELF 没有硬编码 dot/capacity；旧 host checker 才有此假设。
满 M4/N32 时，K2048 命令 dot issues 应从 4096 变为 2048，K6144 从 12288
变为 6144。此时 capacity 不变，因为每拍产品位置翻倍、发射次数减半。
FP uops、updates、useful pairs、payload 和全部输出也应不变。

## 6. 证据身份

输出：`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_balanced_compute_20261106_01/`。

- `result.json`：`a7ccf4376c736101c76659330999b633eed9985c943bc5cd5516bbc465a88b0d`。
- `source-pins.json`：`a087d50464cd15406e070b01e63672755bd7804949b68d02eedef3fd9a72d8e2`。
- 独立审查核对 131 个 pins、17 个 artifacts、三镜像；普通与故障 raw checker
  重放与发布结果精确一致。35 项 host tests 通过。

未启动综合、功耗、FPGA，未将候选提升为生产默认路径，也未宣称完整模型收益。
