# 下一项结构优化前的真实 Decode 输入与测量约定

## 1. 为什么不沿用 Prefill 的一行

当前宽点积候选已在全 N QKV 和真实 FFN 长 K 上取得执行收益，但 Decode 的
M1 dot 步长没有变化。完整模型工作量账目指出，Decode 量化投影中 FFN 和
词表输出层分别占约 61.44% 和 18.09% 的 MAC；需要真实 Decode 的输入和
已有快速路径作为对照，不能用 Prefill 行、全部 DIRECT 的弱基线，或不同
模型的较早切片替代。

## 2. 当前捕获怎样进行

`run_decode_capture.py` 复用已通过完整模型检查的静态库，不重建 llama.cpp。
先执行真实 Qwen3-1.7B Q4_K_M 的 40-token Prefill，检查返回码、有限 logits
和已核验的首个贪心 token 22406。随后以该 token、位置 40、同一 Q8_0 K/V
cache 进入第一个 Decode，捕获以下 F32 输入：

| 源张量 | 行数 | K | 后续消费者 |
| --- | ---: | ---: | --- |
| `attn_norm-0` | 1 | 2048 | 第一层 Q/K/V |
| `ffn_norm-0` | 1 | 2048 | 第一层 gate/up |
| `ffn_swiglu-0` | 1 | 6144 | 第一层 down |
| `result_norm` | 1 | 2048 | 最终词表输出投影 |

这是完整执行 Prefill 后真实产生的 Decode 激活，不重复或拼接输入。前三个
捕获后继续执行后续层，最终在 Decode 词表投影之前停止；它没有完成本次
Decode 的最终 logits 或生成第二个 token。因此验收状态明确区分完整 Prefill
已执行与完整 Decode 尚未执行，也不使用 QEMU 时间作为性能数据。

回调在后端同步后读取真实张量，检查形状、步长、有限值及捕获次序；第一层
Decode 输入还必须不同于旧 Prefill 首行。回调可能切分调度图，因此其中观察
的 context 统计用于确认路径和准备数据，不冒充无观测模型的覆盖率或周期。

## 3. 长运行之前的准入与结束后的验收

先核对模型盘、host GGUF、源码、编译器、静态库和所有需要的原始权重，缺少
词表 tensor 或出现未知格式时在 Prefill 开始前拒绝。原始权重保留 N128 前缀，
完整 K 和原始 N 进入清单：Q/K/V、gate/up/down，以及词表输出权重。

为减少日志开销，Prefill 关闭 QBS 逐条日志；在完整图调用返回后、Decode
开始前再开启两个原有 trace 门控。配置不在任何阻塞执行 context 内变化。
检查器要求四个捕获边界前分别完成 0/4/6/196 个投影调用和 0/192/576/17920
条 native 命令，并逐调用核对 K、N、profile、M1 和实际命令数量。

同时要求 28 次 grouped Prefill、28 次 Decode Attention 及输出驻留路径实际
成功，并出现合法 activation-context 命令。K6144 超出当前 context 容量，
必须保留 DIRECT，不强行提高能力或放宽 descriptor 检查。

运行目录：验证树 `verification/out/e2e_decode_capture_20261106_01/`。捕获状态
只有在上述检查全部完成后才为 `REAL_QWEN3_DECODE_CAPTURED_NOT_BENCHMARKED`。
未取得这个结果前，不把准备文件或运行中的 QEMU 当作已接受数据。

本批现已完成，独立复核状态为 `REAL_QWEN3_DECODE_CAPTURE_REAUDITED`，目录为
`verification/out/e2e_decode_capture_audit_20261106_01/`。收集器重新检查 231 项
直接输入，重读原日志、四个 F32 payload，并从已核验原始 GGUF 再次提取全部
七组权重前缀；native QEMU 构建身份也经过独立复核。捕获的 Decode 输入确实
不同于 Prefill 首行。

捕获范围内实际有 DIRECT=1792、FILL=84、REUSE=15960、RELEASE=84 条命令。
DIRECT 对应超出 context 容量的长 K 路径；已有的 QKV/gate-up 共享及单操作内
复用已在运行。以上只覆盖词表投影之前的工作，不作为完整模型的时间比例或
无观测运行的精确 context 覆盖率。

## 4. 下一轮硬件测量要保留的成本

用真实输入建立 M1 SDK 调用，保留 Q/K/V 与 gate/up 的已有 context 生命周期
和长 K 的安全 DIRECT fallback。比较相同输入、相同工作量和数值；N 采样必须
明确，不将其直接外推成全模型时间。按完整调用记录准备、admission、执行和
命令间开销，再用 AR/R、严格等待、FP/result 反压及排他阶段计数解释瓶颈。

现有 128-bit reader 与量化权重块的服务下界表明，增加 M1 乘法器不能自动
解决数据供给。应先确认实际传输效率和空隙，再选择更好的请求推进、缓冲、
数据驻留或软件批量提交，允许合理面积投入，但不先假定某个队列一定有收益。

## 5. 软件对照还有一个必须固化的差异

本次已核验模型库编译的 `arch/riscv/qbs.cpp` 哈希仍为 `43a86cfd...bf6e`，
尚未采用已重建、做过 host 检查的 `trace-context.patch` 后像 `9aa982ff...8f9`。
后者把 trace 环境查询从每条 native 命令移到阻塞 context 创建时读取一次。
本批 C SDK 计时不执行该 GGML 层查询，所以已测 QKV/FFN 的硬件时间比不受
此差异影响；但它仍是模型级软件基线必须处理的开销，不能遗漏。

后续在独立构建输入中只重建这一对象并核对其余库成员，验证调用之间更新
配置的行为、native 序列、结果及 CSR 后再固化新基线。不能覆盖当前脏 llama
工作区，也不能修改正在被 Decode 捕获消费的库或源码。
