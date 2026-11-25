# 算子级 VCS 实验汇总（2026-11-16）

本轮使用归档 RTL `dbe2b78817ef45b912444afcb85ad6e01a2be135` 对应的 4-lane、VLEN=1024 SoC 仿真镜像。以下为算子或完整 SDK 调用周期，不是 Linux、FPGA 或完整模型性能。结果和输入均保留在 `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`。

## 覆盖与结果

- 九种权重 profile：36/36 通过，包含 M1/M4 和 QBS/RVV 对照。完整逐次数据见 `operator_tables_20261116_formats_final_29/`。权重是以真实 Qwen3 Q4_K 数据解量化后重建的对照数据，并非九个原生模型；四种 RVV 实现为候选基线，不应与五种成熟基线混为同等强度。
- 激活复用与 M4/M8：`operator_campaign_20261115_reuse_06` 9/9 通过；整数、FMA 和交替执行共存回归 `operator_campaign_20261116_coexist_fixed_39` 3/3 通过。
- Decode Attention：真实 Qwen3 和 Llama 切片在 `operator_campaign_20261115_main_03` 中通过；T137 平衡顺序复测 `operator_campaign_20261115_balanced_07` 通过。原始批次另有两项验证开销过高而停止，替代批次 `operator_campaign_20261116_quantkv_compact_17` 2/2 通过；不能把原批次改标为通过。
- Prefill：真实 Qwen3 Q16 切片经独立修正检查与协议复核通过，见 `operator_prefill_audit_20261116_v2_36`；原始批次失败记录保留。Q64 批次 `operator_campaign_20261116_prefill64_fixed_52` 1/1 通过。
- 尾块及软件 K 分段：`operator_campaign_20261116_boundaries_independent_49` 2/2 通过。Gemma D256 定向切片 `operator_campaign_20261116_d256_independent_50` 1/1 通过。
- 单开关消融：`loan_off` 与 `queue_zero` 各自资格 2/2、修正后的共存 3/3、性能 3/3 通过；`shared_fma_off` 资格 2/2、共存 3/3、Attention 性能 1/1 通过。控制变量只覆盖所列切片，不代表面积、时序或所有模型。

## 周期示例

真实 Qwen3 投影切片，第二次完整调用：

| 切片 | M/N/K | RVV cycles | QBS cycles | RVV/QBS |
|---|---:|---:|---:|---:|
| Decode attention Q, Q4_K | 1/64/2048 | 71897 | 26377 | 2.73x |
| Decode FFN gate, Q4_K | 1/64/2048 | 71923 | 26363 | 2.73x |
| Decode FFN down, Q6_K | 1/128/6144 | 2644686 | 92979 | 28.44x |
| Prefill FFN down, Q6_K | 4/64/6144 | 1618573 | 250890 | 6.45x |

数据来自 `operator_campaign_20261115_real_projection_prefill_09` 中8项分别通过的投影测试；同批 Prefill 的原始失败和独立复核单独记录。该对照包含软件准备和 SDK 调用，不是纯计算阵列周期。

真实捕获的 Decode Attention 完整调用（包含 QK、Softmax、PV 和排空）：

| 切片 | KV token | 普通 RVV | 原生 AKV | 强制 Resident |
|---|---:|---:|---:|---:|
| Qwen3 D128、2 heads | 137 | 60038 | 41456 | 34811 |
| Qwen3 D128、2 heads | 513 | 179315 | 107359 | 79661 |
| Qwen3 D128、2 heads | 1025 | 341723 | 199024 | 141945 |
| Llama 3.2 D64、2 heads | 129 | 40071 | 29015 | 26538 |

单位均为 cycles。以上是定向裸机调用；强制 Resident 不代表 Linux 自动准入，也不能替代板级端到端性能。T137 另有平衡顺序复测，其他点为固定顺序。

T137 共享 FMA 对照：开启共享时平衡顺序两次原生 AKV 为 41089/41160 cycles、Resident 为 34492/34490；关闭共享时各一次分别为 40739 和 34729 cycles。两组重复次数和运行顺序不同，只能说明该代表点差异较小，不能证明所有普通 RVV 浮点操作性能等价。

Q4，N=64、K=2048，第二次完整调用：

| M | RVV | QBS | RVV/QBS |
|---:|---:|---:|---:|
| 4 | 188755 | 91257 | 2.07x |
| 8 | 378467 | 164877 | 2.30x |

同一 M8 数据，完整调用第二次为：全部开启 164877 cycles、关闭借用 178366 cycles、队列深度为零 170057 cycles。M4 分别为 91257、91179、91257 cycles；该点关闭借用没有测出收益。各项是独立编译配置，结果不应相加。

Qwen3 F16 Prefill：Q16 切片 RVV 353788.5、AKV 385784 cycles，AKV 慢约 9.0%；Q64 切片 RVV 793988、AKV 784094 cycles，约 1.013x。两点调用 SDK，不是 GGML 实际调度验证；浮点异常标志仅验证重复一致，未有独立标志金标准。

量化 KV 的 Q4/Q8 切片中，跨 query 共享 V 相对逐 query 的完整调用分别约 1.253x、1.255x；两侧均使用 QBS QK，不是相对纯 RVV 的加速比。

## 证据边界

原始 Q16 Prefill 测试检查器误将每个 query 的可见长度当作硬件 panel 实际重放长度。复核按驻留 tile 长度检查，数值和独立协议检查通过；独立复核不覆盖原始批次失败。共存生成器零长度 `.incbin` 问题已在独立测试副本修正，重构建后的回归通过。

本批次不是完整模型验收；未覆盖所有模型、所有长度、所有格式的原生模型数据，也未测板级调用成本、PPA、功耗或 Linux 上的 Resident。F16 Prefill 长上下文、更多模型与 GGML 自动选路仍需另行验证。
