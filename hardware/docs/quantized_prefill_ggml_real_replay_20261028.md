# GGML 张量经 Prefill C 入口的真实数据回放

结果目录：`verification/out/prefill-ggml-real-20261028-01/`，状态 PASS。
源程序为 `verification/akv/quantized_kv/prefill/replay_ggml.cpp`，
构建/执行脚本为同目录 `run_ggml_replay.py`。

本测试使用 GGML 的真实 tensor 和 backend allocator 创建 FLASH_ATTN_EXT
输出及源张量，并装入已封存的真实 Qwen3 capture：20 query、16 query heads、
8 KV heads、D=128、KV capacity=256，每行可见前缀来自真实 mask。
它直接调用新 C 入口，不经过注册后的 CPU graph dispatch，尚非模型集成。

| K 格式 | V 格式 | 输出数 | 命令数 | 分组数 | V 解码 | 最大 golden 绝对误差 |
|---|---|---:|---:|---:|---:|---:|
| Q4_0 | Q8_0 | 40960 | 160 | 40 | 480 | 1.40815973e-6 |
| Q8_0 | Q8_0 | 40960 | 160 | 40 | 480 | 2.95042992e-6 |

两种格式均与既有逐 query QBS 入口逐位一致，主机浮点异常标志一致，
并以原容差 `2e-5 + 2e-5 * abs(golden)` 核对 capture golden。
query quantization、V decode、scale、MAD 来自实际 GGML helper；QK 通过
QBS 数值参考模型执行，不以主机 GGML dot 替代。没有采集或宣称 RTL 周期。

构建前后检查 capture、GGML 已封存库和依赖哈希。每个编译单元独立记录
recipe、依赖和日志，QBS reference 使用 contraction-off，其他单元保持
此前回放约定的 contraction-fast。未通过更改数学规则或误差阈值取得 PASS。

二进制 SHA256：`a889113879ec80375c393ef69075f6e348f52c67b63eaa1ee08f8c300fbdd312`。
source-pins SHA256：`f77bf6cbcb2cb9937c7d136638c7f1158f79d50e2135c389caa17ba24fc43e57`。

本结果补齐真实张量到 metadata/memory 检查、完整准入、成功执行和输出写回
的接口链路。下一步才是将该入口接到受控 GGML dispatch，核对实际 graph
路径选择、执行所有权、fallback 和真实模型行为。生产默认保持不变。
