# 共享对齐优化合入后的验收结果

本记录对应共享 `admission.h` 的已证明对齐读取，以及 `execute.h` 的借用
局部指针清理。没有合入此前周期退化的边界规划，也没有修改 RTL。
Prefill 的构建和运行时开关继续默认关闭。

## 本次新代码证据

| 层级 | 结果目录，均位于 verification/out/ | 状态 |
|---|---|---|
| 11 项共享入口/差分/内存测试 | 本轮 unittest 日志与提交中的测试源码 | 通过 |
| 两格式/两布局真实回放 | prefill-promoted-real-20261028-01 | PASS |
| 正常 CMake OFF/ON 库 | prefill-aligned-ggml-build-20261028-01 | PASS |
| 实际 OFF/ON graph 调度 | prefill-promoted-graph-20261028-01 | PASS |
| Qwen2.5 模型对照 | prefill-promoted-qwen25-model-20261028-01 | PASS |
| Qwen3 模型对照 | prefill-promoted-qwen3-model-20261028-01 | PASS |

graph 两套程序共 16 次调用，两种格式成功进入 Prefill，带孔 mask 的拒绝
请求均为零命令，fallback 输出与标准路径逐位一致。OFF 测试 ELF 与合入前
相同，表明该测试中未启用的新特性没有改变 OFF 二进制。

Qwen2.5-1.5B 使用 4-token prompt，Qwen3-1.7B 使用 40-token prompt，
后者跨 32-token tile。每项均覆盖 K=Q4_0/Q8_0、V=Q8_0，一次 Prefill 与
两步 Decode。每个模型六组比较，911616 个 logits、token、CSR 逐位一致；
两个模型合计 1823232 个 logits。开启侧每模型各完成 56 次 Prefill，关闭侧
没有新路径执行；每模型 ON/OFF 各 112 次 Decode 的逐项活动完全一致。

模型输入、库、ELF 和镜像前后哈希一致。Qwen2.5 source-pins SHA256：
`8edb5b5a407139a8d09afd6e8bb0feb90e5b42a2aa1be20eb5efd5762aa9c2ac`。
Qwen3 source-pins SHA256：
`3967e4bdbe2f05e9e80a40994c6e2a981d76271f64a9727c971b7d4f70842dd9`。
两项服务均正常结束；本次最终核查没有运行中的 prefill 服务。

## 性能与结论边界

独立候选此前同 ELF 完整入口 VCS 加速为 1.485x，是推进共享修改的实测
依据；此处标准库和模型测试证明合入后的功能与路径没有回归，不测周期。
不能将候选加速与原跨 query 共享的约 1.46x 简单相乘，也不将它作为两个
模型的端到端加速。后续若需总体性能，应以最终共享代码重建相同配对程序。

当前可保留这项不增加硬件资源的软件优化。下一项优化应从真实剩余热点
取证，尤其检查共用 Decode selector 的读取、重复准入与前处理，而不是
恢复已被否决的规划或盲目扩大 SRAM/新增指令。全部软硬件优化目标仍未
因此自动完成。
