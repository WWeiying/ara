# Prefill 实际 GGML graph 调度验收

## 标准构建

`verification/out/prefill-ggml-build-20261028-01/result.json` 为 PASS。
两套库均由标准 CMake 构建完整 llama target；OFF 不编译 Prefill C 入口，
ON 恰好编译一份，并在 quant-kv.cpp 中启用对应宏。没有对象覆盖。
源码和运行时输入前后哈希一致。

## QEMU 功能结果

最终结果：`verification/out/prefill-graph-qemu-20261028-02/result.json`，PASS。
使用 QBS-capable QEMU、VLEN=1024，分别启动 OFF/ON 构建链接的真实
`ggml_graph_compute` 测试。QEMU 仅验证功能和调度，不提供 RTL 周期。
输入是同一真实 Qwen3 capture，20 query、16 Q heads、8 KV heads、D=128。

| 构建 | graph 调用数 | 新路径完成 | 非前缀 mask 拒绝 |
|---|---:|---:|---:|
| OFF | 8 | 0 | 不进入新路径 |
| ON | 8 | 2 | 2 |

两种 K 格式分别为 Q4_0、Q8_0，V 均为 Q8_0。每种格式包含运行时开关
关闭/开启、原始 causal mask/最后 query 带孔 mask 四项对照。

ON 构建的两次成功调用各为 40960 个输出、160 条 QBS 命令、40 个分组、
480 次 V 解码、320 个 query/head 量化，workspace 为 22464 字节。
相对 capture golden 最大绝对误差：Q4_0 为 1.40815973e-6，Q8_0 为
2.95042992e-6。开关两侧均使用原固定数值容差，未为接入放宽阈值。

带孔 mask 的调用 trace 为 status=1、selection=6、commands/groups/
queries_quantized 均为 0，输出与关闭开关的标准路径逐位一致。
全部 graph 调用保留预置 DZ 标志，FCSR=9、VCSR=5。
主机解析器检查 begin/end 顺序、16 次调用、成功命令活动、fallback 零活动、
guest exit=0 及完成标记，前后 source pins 一致。

## 首次汇总失败

目录 `prefill-graph-qemu-20261028-01` 保留 FAIL：OFF guest 实际完成，但
新主机解析器错误引用不存在的正则分组。待 worker 退出后修正字段索引，
补充正常/错误命令数、CSR、exit、缺失 native 活动等解析测试，然后在新目录
重跑两套程序。未改 guest ELF、内核、数据、计算逻辑或数值容差；首次结果
没有重标为 PASS。

## 当前边界

这证明标准库中的实际 graph dispatch 已接上新路径，并保持该 mask 拒绝
路径正确。它不代表完整模型已经验收，不代表所有 fallback 已覆盖，也不
把此前 C 入口的 1.455x 直接作为模型收益。下一步进行真实模型受控 ON/OFF
运行，核对实际 Prefill 命中、Decode 保持原路径以及模型输出/数值指标。
