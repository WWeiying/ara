# Token-major KV 的完整入口 RTL 结果

> 评测接线复核（2026-10-28）：本文既有 native 周期数据使用通用标量
> `dequantize_row_q8_0` 作为 V 回调；当前 llama.cpp 后端使用共享 RVV
> `akv_quant_q8_0_value`。这些历史配对数据在其配置下仍有效，但不能当成
> 当前后端回调配置下的周期或瓶颈占比。真实 GGML/模型功能回归不受此
> benchmark 差异影响。更正及补测见 `quantized_native_binding_audit_20261028.md`。


结果目录：`verification/out/prefill-strided-q4-vcs-20261028-01/`，PASS。
构建：`verification/out/prefill-strided-q4-build-20261028-02/`，16 个对象重编译。
此前 build-01 的符号检查失败已保留；修正的是旧连续入口符号检查，不是内核。

## 数据与基线

输入来自原封存 Qwen3 capture。仅将完整 K/V 的物理字节排列从 head-major
置换到 token-major：8 KV heads、256 token，量化 block 字节不变。
本点选择 KV head 0、query 16--19，每个 query 两个 GQA head，D=128，
K=Q4_0、V=Q8_0。可见前缀为 17/18/19/20。

Baseline 是现有逐 query `akv_quant_strided_execute`；candidate 是完整
Prefill 入口。两者使用同一 QBS 镜像，均将准入、panel 搬运、计算和输出
路径纳入周期。不含 GGML frontend 分配和全模型调度开销。

| 轮次 | 路径 | 周期 | K panel | K 拷贝字节 | V 解码 |
|---|---|---:|---:|---:|---:|
| A1 | 逐 query | 312842 | 4 | 5328 | 74 |
| B1 | 跨 query | 214943 | 1 | 1440 | 20 |
| B2 | 跨 query | 214553 | 1 | 1440 | 20 |
| A2 | 逐 query | 312975 | 4 | 5328 | 74 |

平均周期 **312908.5 → 214748**，加速 **1.4570962244x**。
每轮 QBS 命令均为 4。K 拷贝字节由每 query 单独可见范围的和，变成分组
可见范围并集。这是软件 panel 拷贝量，不是 AXI 事务字节统计。

四轮各 1024 个输出逐位一致；最大 golden 绝对误差
`3.5762786865234375e-7`；FCSR=1、VCSR=5，程序 errors=0。
布局标记、逐轮 panel/byte、完整数值、独立协议及前后输入身份核验均通过。
ELF SHA256：`1fe0730f60a4f5466d151e3245ef8ac6d644927f48b78a9b09e4a042899f313a`。
服务已正常退出。

## 对下一步优化的含义

连续 K 的 Q4_0 完整入口此前为 1.455x，此处 token-major 为 1.457x。
两项独立 ELF 只支持“该代表点的布局成本未抵消复用收益”的结论，不足以
作逐函数精确周期归因或推断所有 stride/context 的性能。

本阶段已经有两个模型的真实调用功能证据、两种 K 格式的连续布局 RTL
证据及一个 token-major RTL 点。没有新增硬件、没有默认启用新路径。
下一步应围绕小 query 数/GQA 分组的收益边界与残余准入成本选择有限代表点，
用阶段计数决定是否优化软件前处理或硬件，而不是立即增加新指令或缓冲区。
