# Quantized Prefill 的 GGML 接入准备

## 当前运行时缺口

已安装的 `ggml-cpu/arch/riscv/quant-kv.cpp` 调用
`akv_quant_ggml_strided_execute`。其元数据桥 `ggml_decode.h` 明确要求
query 的 `ne[1] == 1`、输出 `ne[2] == 1`，因此当前量化 Attention 的该路径
只接受 Decode，多 token Prefill 仍回到标准实现。独立 Prefill benchmark
通过不等于 GGML 已经调用它。

本次只增加独立原型 `verification/akv/quantized_kv/prefill/ggml_map.h`，
没有修改已安装的 llama.cpp 文件、生产开关或 RTL。

## 张量映射

| GGML 张量 | 原始维度 | Prefill 入口解释 |
|---|---|---|
| Q | `[D, queries, query_heads, 1]` | token stride=`nb[1]`，head stride=`nb[2]` |
| K | `[D, capacity, kv_heads, 1]` | 保留真实 token/head stride |
| V | `[D, capacity, kv_heads, 1]` | 保留真实 token/head stride |
| mask | `[capacity或更大, mask_rows, 1, 1]` | 每个 query 使用一行，行 stride=`nb[1]` |
| 输出 | `[D, query_heads, queries, 1]` | token stride=`nb[2]`，head stride=`nb[1]` |

mask_rows 可以大于 queries，以容纳 GGML 的 padding，但不能小于 queries。
不同 query 的真实可见前缀仍由完整准入阶段逐行检查，不能由 query 编号推断。

映射器先核对原张量的 query、输出和 mask 维度，再创建局部单 query 元数据
视图，复用现有 Decode 映射器的操作、格式及附加输入检查，最后恢复实际
query 数和 mask 行间距。不修改输入张量，不访问数据，不发硬件命令。
保留现有 Q4_0/Q8_0 K、Q8_0 V、F32 Q/输出、F16 mask、单线程约束。

## 安全边界

`MAP_OK` 仅表示元数据已映射，不代表可以执行。正式桥接必须依次完成：

1. 使用现有 backend buffer API 验证各张量 data pointer 起始的可访问范围，
   不能以逻辑 shape 或底层分配大小直接替代 view 的真实范围。
2. 调用全量 Prefill admission，检查所有 query、mask 行、可见 KV 区域、
   能力参数及地址别名；未通过时尚未写结果，允许 fallback。
3. 分配符合 `sizeof(quant_prefill_workspace_t)` 和 64 字节对齐要求的私有
   workspace。不可照搬 Decode 包装器的固定 16384 字节栈缓冲区。
4. 在既有 `ggml_riscv_qbs_direct_run` 的执行所有权内发命令，保持普通 RVV
   与 QBS 使用规则；不能绕过该包装器直接发射。
5. 一旦开始执行，运行错误必须返回 failed，不能把可能部分写回的输出当成
   未执行请求而再次走 fallback。多线程共同准入尚未实现，继续单线程限制。

## 已做测试与尚未完成项

测试使用实际 GGML 头文件，而非自建 tensor 仿真结构：

- 20 个正常映射组合：query 数为 1/2/4/20/256，K 为 Q4_0/Q8_0，
  mask 行数恰好匹配或带 padding；核对 Q 与输出不同的 token/head 轴顺序。
- 16 个拒绝场景：线程、use_ref、算子、空源、query 上界、维度不符、
  多 batch/mask head、不支持格式、元素步幅、附加输入、精度模式。
- 拒绝时结果结构不变；正常映射不修改 tensor 元数据或输出数据。
- GCC 和 Clang UBSan 执行检查；另检查 C++17 头文件兼容性。

这些是元数据单元测试，不是模型执行证据。当前仍需完整调用 VCS 验收，再
完成 buffer-aware 桥接、实际 GGML graph 测试和受控模型运行；此时不启用
默认快速路径，也不据此宣称端到端性能提升。
