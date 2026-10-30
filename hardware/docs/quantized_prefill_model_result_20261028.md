# 量化 Prefill 接入后的真实模型功能闭环

## 本次结果

`verification/out/prefill-model-qemu-20261028-01/result.json` 为 PASS。
使用标准 ON 构建的完整 llama 库，在两个独立子进程中仅切换运行时 Prefill
开关。QBS M4 preparation、packed layout、cache 和其他执行选项保持固定。
没有覆盖库对象，也没有把回放内核替换到模型测试中。

模型为现有只读镜像中的 Qwen2.5-1.5B-Instruct Q4_K_M，28 层；prompt 为
`The quick brown fox`，分词后 4 token。每种 KV 配置执行一次 Prefill、
两步自回归 Decode，比较每一步最后位置的全部 151936 个 logits。

| KV 配置 | 比较次数 | logits 数 | token/CSR | logits |
|---|---:|---:|---|---|
| K=Q8_0，V=Q8_0 | 3 | 455808 | 完全一致 | 逐位一致 |
| K=Q4_0，V=Q8_0 | 3 | 455808 | 完全一致 | 逐位一致 |
| 合计 | 6 | 911616 | 完全一致 | 逐位一致 |

两侧生成的 token ID 均为 34208、916、279。测试没有放宽已有逐位 logits、
CSR 或 token 检查；预置 CSR 条件与原始模型测试一致。全模型涉及其他算子，
因此不能把独立 Attention graph 的 VCSR=5 直接作为全模型最终值要求。

## 实际路径证据

- 关闭侧没有新 Prefill 执行 trace。
- 开启侧完成 56 次 Prefill：28 层乘两种 KV 配置；逐项 status、mapping、
  selection 为 0，命令数与完成分组数非零。
- 两侧各有 112 次成功的量化 Decode 调用：28 层乘两步乘两种 KV 配置。
  每项成功 Decode 的完整活动字段列表在两侧相等，而不仅是总调用数相同。
- guest 正常结束，主机独立日志检查通过；模型镜像、源码、库、ELF、QEMU
  和输入前后哈希核验通过。
- 主机验收器另有反例测试，拒绝缺失 Prefill、命令数为零、selection 错误、
  logits 对照缺失、guest 非零退出及 Decode 活动变化。

## 与性能证据的关系

本次 QEMU 只证明真实模型功能与路径覆盖，**不测硬件性能**。已有 VCS
小批真实 Qwen3 输入的完整 C 入口测量为 1.455x；它不包含新 frontend 的
heap 分配与模型调度开销，也不能替代 Qwen2.5 或其他模型的端到端加速比。
实际 graph 的两种 K 格式与 mask fallback 另有独立通过记录。

当前默认开关仍关闭。下一阶段需扩大 query/上下文及模型形状，检查小批
收益边界、真实 token-major KV 的 panel 成本和其他 fallback。尚未证明整个
软硬件优化目标完成；本次没有新增 RTL 修改。
