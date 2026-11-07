# llama.cpp RMS 模型功能验收（2026-11-06）

本记录仅归档已有 QEMU 模型运行及独立 host raw 审计，没有新增模型执行或 EDA。
compact receipt 见 [rms_ggml_model_20261106_01](../../verification/performance/evidence/rms_ggml_model_20261106_01/result.json)。

## 证据身份

- Collector：`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_rms_ggml_model_collect_20261106_01/result.json`
- Collector SHA256：`bc009e9f9419551eea9ddf0203c08691fbdc3a7ea30379b64c12d8eec1a34bc9`
- 审计状态：`RMS_GGML_MODEL_SCOPED_RAW_AUDIT_PASS`。
- Worker：`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_rms_ggml_model_qemu_20261106_01/result.json`
- Worker SHA256：`3a4e79242c74f24d1e994722ac9bf88b567b1ff24473eec96451e7655be8a72e`
- 原运行状态：`RMS_GGML_PREBUILT_MODEL_PAIR_FUNCTIONAL_PASS`。

## 已验证事实

限定于该 Qwen3 模型、40-token prompt、一次 Decode，以及 `q8_0/q8_0`、
`q4_0/q8_0` 两种量化 KV 配置。重放旧 native checker 与新增 Norm work checker 后，
四组比较共 607744 个 logits 的 bitexact verdict、token/CSR 和 native 工作量守恒一致。
这里独立重放的是 guest driver 的完整比较记录，并非重新读取导出的 logits 数组。

每个配置各有 Prefill、Decode 两步，每步 113 个 Norm 节点；合计 452 节点、
59622 行，所有节点均为 `fused=1`，sum/output 行数相等。每步形状分布如下，
两种 KV 配置均满足同一分布：

| 阶段 | `(width, rows)` 与节点数 |
| --- | --- |
| Prefill | `(128,640)` × 28；`(128,320)` × 28；`(2048,40)` × 55；`(2048,1)` × 2 |
| Decode | `(128,16)` × 28；`(128,8)` × 28；`(2048,1)` × 57 |

实际 newc 的 `/init`、`/base`、`/candidate`、`/test` 四个 ELF 字节匹配绑定输入，
baseline/candidate 非 A/A。实际 archive 仅 `ops.cpp.o` 改变，其他 31 个成员不变。
独立 collector 的 15 项 host 测试通过。

## 范围限制

本次独立审计重 hash 并复核路径身份的范围仅为 57 个选定输入，包括关键收据、
实际 ELF/cpio/raw/checker/archive。原 worker inventory 有 35622 项；其全量输入和
路径验收通过上面的终态 worker SHA 引用，本次没有重新扫描整个 QEMU 源码树、
native 源码闭包、模型磁盘或完整工具链。不能把本次审计称为全 pins 二次复核。

生产 baseline 已自动向量化 ordered RMS；先前 isolated baremetal 的局部比例不是
生产收益，本验收不提供生产或完整模型性能承诺，也不是默认 F16 主路径的验收。
运行时选择保持 opt-in，未提升为默认生产库，未新增 RTL、PPA 或硬件性能验收。
