# 共用 selector 对齐候选的真实 Decode 执行验证

结果：`verification/out/selector-real-execution-20261028-02/result.json`，PASS。
候选仍未安装到共享 runtime，没有修改 RTL。

`selector_runtime.c` 在独立 translation unit 中包含同一 canonical
`runtime_strided.c`，仅改 selector 和导出符号名称。原 runtime 单独编译并
同时链接，没有覆盖生产库对象，也未复制或改写计算内核。

输入为封存的真实 Qwen3 capture：20 个 query 分别按 Decode 调用，
16 query heads、8 KV heads、D=128，可见前缀来自各自真实 mask。
每种格式先计算原连续入口，再在连续/行间 padding K 上分别运行原 strided
与候选 strided 入口。三路输出逐位一致，浮点异常标志一致。

| K 格式 | 布局 | 输出 | 命令 | 完成组 | V 解码 | 候选 K 拷贝字节 |
|---|---|---:|---:|---:|---:|---:|
| Q4_0 | 连续 | 40960 | 160 | 160 | 1680 | 0 |
| Q4_0 | 行间 padding | 40960 | 160 | 160 | 1680 | 120960 |
| Q8_0 | 连续 | 40960 | 160 | 160 | 1680 | 0 |
| Q8_0 | 行间 padding | 40960 | 160 | 160 | 1680 | 228480 |

相对 capture golden 最大绝对误差分别为 1.40815973e-6、2.95042992e-6，
保持原固定容差。采用实际 GGML primitives 和 QBS 数值参考，无 RTL 周期。
旧/新 selector 的拒绝、对齐和浮点标志差分另有 972 项场景通过记录。

二进制 SHA256：`b9780426b5b9b377573e43194d8543dc87207b31a2b83852ceee175908ea744a`。
source-pins SHA256：`1e788307af5563699248f83f21bab2ba186c49dae0cf6521a11301319750370f`。
下一步在同一 ELF 中用真实 Decode 输入比较原/新完整调用周期，保留协议、
数值和活动检查；不得把前一项 Prefill 准入的加速当成本候选的实测结果。
