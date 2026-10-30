# Qwen3 跨 tile Prefill 模型验收

结果：`verification/out/prefill-qwen3-model-20261028-01/result.json` 为 PASS。
模型为 Qwen3-1.7B Q4_K_M，guest 路径与只读磁盘清单一致；模型源 SHA256
为 `d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5`。
没有为了该模型修改 RTL、计算内核、标准库或既有 fallback。

## 覆盖范围

- 实际 prompt 为 40 token，跨过 32-token KV tile 边界；n_ctx=128，
  n_batch=n_ubatch=64。不是长上下文全覆盖测试。
- 模型有 28 层，Qwen3 的 query/KV head 配置与此前 Qwen2.5 不同。
- K=Q8_0/Q4_0，两者 V 均为 Q8_0。
- 每种配置测试一次 Prefill 和两步自回归 Decode。
- 同一个标准 ON 库构建，两个独立子进程只切换 Prefill 开关；其他 QBS
  优化保持相同，未覆盖 runtime 对象。

## 严格数值对照

| K 格式 | 比较步数 | 全量 logits | ON/OFF logits、CSR、token |
|---|---:|---:|---|
| Q8_0 | 3 | 455808 | 完全一致，logits 逐位一致 |
| Q4_0 | 3 | 455808 | 完全一致，logits 逐位一致 |
| 合计 | 6 | 911616 | 通过 |

Q8_0 配置 token ID 为 22406、11、4263；Q4_0 为 22406、11、10339。
两种 KV 格式之间生成结果可以不同；验收比较的是**同一 KV 格式的 ON/OFF**，
不能将格式差异误判为新调度错误。没有为本次测试放宽逐位匹配要求。

优化侧 56 次 Prefill 均成功且有真实命令和分组完成活动；关闭侧没有新路径
执行记录。两侧各 112 次成功 Decode，逐项活动记录完全一致。
guest exit=0，主机验收与前后输入身份检查通过。
source-pins SHA256：`6a0041614a8e477bd31ed3fc03e18099e9a32bd8ccd8e177466e2e847324c706`。

## 结论与剩余工作

结合 Qwen2.5 4-token prompt 的独立通过结果，现有标准库已在两个模型、
两种 KV 格式和两个 prompt 长度上验证新 Prefill 的真实调用及 Decode 不退化。
这是 QEMU 功能证据，不是 FPGA 或 RTL 的整模型性能结论，也不证明所有
模型/上下文均支持。K=Q8_0 的完整 C 入口 VCS ABBA 正在独立运行；Q4_0
已有 1.455x 的通过记录，尚不能将它推广为 Q8_0 或端到端加速比。
