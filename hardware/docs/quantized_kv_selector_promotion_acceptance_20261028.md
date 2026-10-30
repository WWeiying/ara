# 共享 selector 对齐优化：运行时验收

> 评测接线复核（2026-10-28）：本文既有 native 周期数据使用通用标量
> `dequantize_row_q8_0` 作为 V 回调；当前 llama.cpp 后端使用共享 RVV
> `akv_quant_q8_0_value`。这些历史配对数据在其配置下仍有效，但不能当成
> 当前后端回调配置下的周期或瓶颈占比。真实 GGML/模型功能回归不受此
> benchmark 差异影响。更正及补测见 `quantized_native_binding_audit_20261028.md`。


## 结论

共享 `selection_strided.h` 的两处对齐信息接入后，正常 llama.cpp 库构建、
真实 GGML 图以及 Qwen2.5/Qwen3 模型功能回归均 PASS。没有修改 RTL、
数值运算顺序、指令编码、量化格式或设备能力要求。

整批结果入口：
`verification/out/selector-promotion-runtime-20261028-01/result.json`。
入口状态为 PASS，5 个阶段的结果摘要哈希均已记录，流水线输入指纹一致。
任务结束后，另对各阶段结果摘要及合并去重的 1030 个当前源码/数据/工具
指纹重新核验，全部一致。

## 检查层级

| 层级 | 范围 | 结果 |
|---|---|---|
| 正常库 | CMake Prefill OFF/ON，正常静态库，不替换对象 | PASS |
| 真实图 | 2 种 K 格式，正常 mask/带孔 mask，运行时 OFF/ON | 16 次调用 PASS |
| Qwen2.5-1.5B | 4-token prompt，2 种 K 格式，各 3 个生成步骤 | 6 组、911616 logits 逐位一致 |
| Qwen3-1.7B | 40-token prompt，跨 32-token tile，2 种 K 格式，各 3 个生成步骤 | 6 组、911616 logits 逐位一致 |

两模型均为 Q4_K_M 权重。KV 分别为 K=Q8_0/V=Q8_0 和 K=Q4_0/V=Q8_0。
模型每次比较的全部 151936 个 logits，而非只检查选中 token。
每种 KV 配置比较 prompt 最后一项 logits 以及后续两个单 token 步骤。
两模型累计 1823232 个 logits 逐位一致；对应 greedy token 和 FCSR/VCSR
也完全一致。

每个模型在 Prefill 开启模式完成 56 次 Prefill，关闭模式不进入该路径；
两种模式各完成 112 次 Decode，完整活动字段一致。图测试中启用构建的
两次正常输入走快路径，两次带孔 mask 被拒绝并进入原回退，禁用构建无
Prefill 快路径活动。

## 比较的含义

这是接入后当前共享源码上的 Prefill OFF/ON 模型功能回归，不是两套
不同 selector 二进制的模型级 A/B，也不是不同 KV 格式之间的逐位一致性
声明。两种模式保持 QBS 准备、缓存和量化 KV Decode 配置相同，仅切换
Prefill 路径。它证明本次接入未破坏这些已支持的完整模型执行路径。

旧 selector 与新 selector 的直接一致性另由冻结旧函数的 972 项差分、
真实输入回放以及同 ELF 原/候选 RTL 实验支持。VCS 的局部完整调用结果为：
82691→71651 cycles，1.1540801943×，周期减少 13.3509088%。该测量包括
准入、量化、K panel、QK、softmax/PV、输出和 drain；不包括 UART 和
模型图调度，不外推为模型端到端提速。

## 可追溯证据

目录前缀均为 `verification/out/selector-promotion-runtime-20261028-01/`。

| 子目录 | result.json SHA256 |
|---|---|
| libraries | b416d580ad40f9a9b1aaf32e618ab82ff386f9f051017ce837b905984296c3fe |
| graph-build | 7a50051ac3bf0b389061d24f2de66e71d9f211d9ac613c70632da845dd96ab8c |
| graph | ecc0bbffd7f8c79b2d78c09074646a2971fda58db93371c6968301656926aaeb |
| qwen25 | 2fcd6fb698f27d362b6386d65d53d01ff2ee926afc6acfc67bb98aa6f59c6f8c |
| qwen3 | 8a3d56ce4c6fd58506de19370c36bea746527c8508dfb4846bc1012b76c88130 |

`graph-build` 的状态是 BUILT_NOT_EXECUTED；图的实际 PASS 在 `graph`，
不能把程序构建成功代替图执行通过。模型实际日志包含逐项 bitwise、
csr_equal、token_equal 标记和 `GUEST_TEST_EXIT=0`。QEMU 只作功能验证，
不提供真实硬件性能。

## 下一步边界

当前优化改善的是通用准入的标量装载开销，不是新增专用计算硬件。继续
软硬件优化前，应以已接受完整调用的周期边界拆分剩余开销，区分安全
扫描、query 准备、命令执行和 PV，优先处理实测占比大的环节。不能仅凭
代码长度或 QEMU 时间决定修改 RTL，也不能通过删掉安全扫描换取表面提速。
