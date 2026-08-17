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

每个 app 的 `generated/provenance.json` 记录原始 tensor 和嵌入布局的大小、SHA-256、
shape、量化类型和 capture commit。Q4_K 权重在构建时离线转换为 Ara 的 32-row
布局；原始 GGUF row-major 字节仍以硬链接或副本保存在同一 `generated` 目录。
离线 repack 不计入运行时间。

计时区间只包含动态 `F32 -> Q8_K` 量化以及量化矩阵计算。输入加载、离线权重
repack、结果校验和打印均不在计时区间内。`logical_read_bytes` 是内核接口层的逻辑
读取量，包括计时区间内的 F32 量化输入、prefill activation 打包输入以及矩阵内核
读取；RTL testbench 输出的 `rvv_axi_ar_count/rvv_axi_r_count` 是总线事务实测值，
二者不能混用。

常用命令：

```bash
make -C hardware llama_real_list
make -C hardware llama_real_build case=decode_attn_q
make -C hardware llama_real_spike case=decode_attn_q
make -C hardware llama_real_sim case=decode_attn_q no_fsdb=1
```
