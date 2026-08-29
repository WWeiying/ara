# Qwen2.5 Real-Operator Benchmarks

该目录保存 Qwen2.5-1.5B-Instruct Q4_K_M 第 0 层的六个真实量化线性算子
benchmark。输入、权重和 golden 均来自完整 `llama.cpp` 推理 capture，不使用随机
或合成数据。

六个 case 分别覆盖 Decode/Prefill 的 Attention-Q、FFN-Gate 和 FFN-Down：

- `llama_qwen25_decode_attn_q`: Q4_K, `1536 x 1536`, `M=1`。
- `llama_qwen25_decode_ffn_gate`: Q4_K, `1536 x 8960`, `M=1`。
- `llama_qwen25_decode_ffn_down`: Q6_K, `8960 x 1536`, `M=1`。
- `llama_qwen25_prefill_attn_q`: Q4_K, `1536 x 1536`, `M=15`。
- `llama_qwen25_prefill_ffn_gate`: Q4_K, `1536 x 8960`, `M=15`。
- `llama_qwen25_prefill_ffn_down`: Q6_K, `8960 x 1536`, `M=15`。

RTL 日常相对评估另提供六个 `_eval` case。它们保留完整 K、真实量化 block 和
真实数值，只裁剪独立的输入 token 或输出行：

- `decode_attn_q_eval`: Q4_K, `N=1536, K=1536, M=1`。
- `decode_ffn_gate_eval`: Q4_K, `N=4096, K=1536, M=1`。
- `decode_ffn_down_eval`: Q6_K, `N=256, K=8960, M=1`。
- `prefill_attn_q_eval`: Q4_K, `N=1536, K=1536, M=4`。
- `prefill_ffn_gate_eval`: Q4_K, `N=4096, K=1536, M=4`。
- `prefill_ffn_down_eval`: Q6_K, `N=64, K=8960, M=4`。

eval case 的 `capture_rows/capture_inputs` 表示完整 capture 尺寸。生成器逐 token
裁剪 golden，并在 provenance 中记录 slice 和哈希；不能通过直接截短完整 golden
文件构造评估数据。

每个 app 的 `generated/provenance.json` 记录原始 tensor 和嵌入布局的大小、SHA-256、
shape、量化类型和 capture commit。标准 RVV app 在构建时转换为 x32 field-major
布局，QBS app 转换为 R4 block-major 布局；原始 GGUF row-major 字节仍以硬链接或
副本保存在同一 `generated` 目录。离线 repack 不计入运行时间。

默认 QBS 计时遵循 GGML 生产调用路径：动态 `F32 -> Q8_K/Q8_0` 量化，M=4 K-quant
所需的 `A_M4_INTERLEAVED` activation 重排，每条命令的 16-byte stack descriptor
构造，`fence/vsetvli`，阻塞 QBS 执行，以及各输出行的普通 RVV store。输入加载、模型
加载期的持久权重 repack、输出缓冲清零、结果校验和打印不在计时区间内。每个命令都
现场构造 descriptor，避免把只在 benchmark 中存在的预建 descriptor 误当成生产
路径。

仅用于摊销消融的 app 可定义 `QBS_BENCH_PREBUILT_DESCRIPTOR=1`，把 immutable
descriptor 预建到计时区间外；它不是主性能口径。输出中的 `timing_scope` 和
`setup_included` 区分两种模式。`timed_cycles` 是从动态 activation 量化开始到最后
一条结果 store 返回的连续区间；当前 `compute_cycles` 为兼容旧汇总字段而记录同一
区间。descriptor 构造嵌在逐 tile 命令循环中，因此不伪造一个无法独立观测的
`descriptor_setup_cycles`；其净开销由 production/prebuilt 配对实验测量。

`logical_read_bytes` 是内核接口层的公式化 footprint，包括计时区间内的 F32 量化
输入、prefill activation pack、descriptor、权重和量化 activation；RTL testbench
输出的 AXI read counters 才是总线事务实测值，二者不能混用。

常用命令：

```bash
make -C hardware llama_real_list
make -C hardware llama_real_build case=decode_attn_q
make -C hardware llama_real_spike case=decode_attn_q
make -C hardware llama_real_sim case=decode_attn_q no_fsdb=1
```

## 多量化格式闭环

同一套生成器还从真实 Qwen2.5 推理 capture 中提取了四个等价的 layer-0
`blk.0.attn_q.weight` decode 点，用于比较标准 RVV 和 QBS。每个点均保留完整 K、一个
真实 activation、前 256 个真实输出行及对应 llama.cpp golden：

| 格式 | 模型 capture | K | N | M | activation |
| --- | --- | ---: | ---: | ---: | --- |
| Q3_K | Qwen2.5-1.5B Q3_K_M | 1536 | 256 | 1 | Q8_K |
| Q5_K | Qwen2.5-1.5B Q5_K_M | 1536 | 256 | 1 | Q8_K |
| Q6_K | Qwen2.5-1.5B Q6_K | 1536 | 256 | 1 | Q8_K |
| Q8_0 | Qwen2.5-0.5B Q8_0 | 896 | 256 | 1 | Q8_0 |

离线生成、编译、并行运行和严格配对汇总命令如下：

```bash
make -C hardware llama_format_build
make -C hardware llama_format_rvv_compile
make -C hardware llama_format_qbs_compile
make -C hardware llama_format_rvv_parallel
make -C hardware llama_format_qbs_parallel
make -C hardware llama_format_status mode=rvv
make -C hardware llama_format_status mode=qbs
make -C hardware llama_format_sum
```

RVV 和 QBS 分别写入时间戳目录，原有运行不会被覆盖。运行根目录还记录 Git HEAD、
dirty 状态、L2 配置、仿真器和各 ELF 的 SHA-256。汇总器要求四组 workload 的
K/N/M 完全一致、两边均 `PASS`、mismatch 均为 0，并且源权重、activation 和 golden
的字节数与 SHA-256 完全一致，才生成
`hardware/format_closure.csv`。CSV 同时包含量化、activation pack、matmul、总计算周期、
数值误差、逻辑读取量、总线计数，以及 `qbs_perf.csv` 导出的全部原始计数和派生比例。
汇总时还会再次检查 QBS command/success/fault 终止账目。`input_phase_ratio` 是 activation/weight
阶段占总 busy 时间的比例，不应解释为严格 stall；等待和受限行为分别参考
`weight_prefetch_wait_ratio`、`read_response_idle_ratio` 和 `fp_input_blocked_ratio`。
QEMU emulation 只验证真实 GGML
派发与数值语义，不用于替代 RTL 性能数据。
