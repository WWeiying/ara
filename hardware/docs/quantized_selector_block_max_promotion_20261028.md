# 块内统一判定接入共享 selector

## 软件改变和不变项

共享 `selection_strided.h` 只把 query 的逐元素 NaN/Inf 检查改为块最大
绝对值的统一检查。每块先排除非有限值，再执行原 Q8_0 输入范围检查。
保留按 block 的错误优先级、对齐证明、布局/别名/设备能力与 finite-scale
检查，不改变 query 量化、QBS 命令、V 解码、softmax/PV 或 fallback 范围。

输入完整可读是既有 view/normal-memory 契约的一部分。现在块内遇到 NaN
仍会继续读到块末尾，但不读出已验证的 view，也不写输出或产生浮点异常。
没有修改 RTL 或增加计算资源。

合入前使用真实 Qwen3 数据和后端一致的 RVV 回调，在同 ELF ABBA 中得到
47972→47182 cycles，1.0167436734×。这是完整 Decode 调用的小幅局部收益，
不能乘以前一轮的对齐收益来宣称新的组合加速。

## 差分与集成检查

`selector_before_block_max.h` 封存接入前的真实共享函数；
`test_selector_block_max` 比较它与实际当前共享函数。2819 项涵盖正常
D/GQA/K 格式组合、块内 32 个位置、F32 边界位模式和跨 block 的拒绝
优先级；GCC 和 Clang UBSan 均需通过。函数级精确差分限制改动范围。

原 selector 差分、strided 拒绝集合、布局边界、Prefill admission、完整
执行、GGML 映射、私有 workspace/分配检查继续保留。真实 Decode 与
Prefill 主机回放需覆盖两种 K 格式和连续/带间隔 K；这些是功能检查，
不以主机时间作为硬件性能。

接入后的新输出目录：

- `verification/out/block-max-promoted-decode-real-20261028-01/`。
- `verification/out/block-max-promoted-prefill-real-20261028-01/`。
- 正常库、真实图、模型流水线：
  `verification/out/block-max-promotion-runtime-20261028-01/`。

运行时流水线使用 `run_selector_promotion.py`，正常 CMake 构建 OFF/ON
库，再运行真实图、Qwen2.5 和 Qwen3 对照；只有对应结果为 PASS 才纳入
验收。开始运行后封存代码，不在消费者尚未结束时继续修改共享文件。

当前已完成：上述三组主机 unittest 共 27 项 PASS；包括 GCC/UBSan 的
2819 项块最大值差分、972 项原 selector 差分及已有布局、执行、映射检查。
接入后 Decode/Prefill 两个真实数据回放目录均 PASS，各覆盖 Q4_0/Q8_0、
连续/带间隔四组，每组 40960 个输出，输出和浮点标志保持一致。
正常 CMake/模型回归尚未在此记录中宣称完成。

该批后续已全部 PASS。两个模型累计 1823232 logits 逐位一致，token/CSR
与 Decode 活动一致；完整验收范围及结果哈希见
`quantized_selector_block_max_acceptance_20261028.md`。
