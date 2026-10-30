# 对齐准入候选的完整入口实验

## 主机真实数据结果

`verification/out/prefill-aligned-real-20261028-01/result.json` 为 PASS。
真实 Qwen3 capture 的完整 20 query、16 query heads、8 KV heads、D=128，
测试 Q4_0/Q8_0 K 及连续/带行间 padding 的 K，共四项。
每项实际运行旧逐 query、固定分组和对齐准入候选，40960 个输出逐位一致，
浮点异常标志一致。命令数 160、组数 40、V 解码 480、query 量化 320 均不变。
strided panel 计数及搬运字节也保持不变。

使用真实 GGML helper 和 QBS 数值参考，非 RTL 周期证据。最大 golden
绝对误差：Q4_0 为 1.40815973e-6、Q8_0 为 2.95042992e-6。
二进制 SHA256：`832657eb9cb3ea8edb1aa0a54bdc3f89f75748fb8986ef678af540a65db9a9bf`。
source-pins SHA256：`dbfc656953f0ceaac03d68d3d8368cddedc3984d37ed1913f7c0c0ad9c7b6c06`。

## RTL 配对条件

独立裸机 ELF 已在 `verification/out/prefill-aligned-native-build-20261028-01`
构建，15 对象重新编译。实验仅比较固定分组的旧准入和已证明对齐的候选
准入，不包含此前否决的边界规划。真实输入前五 query、KV head 0、两个
GQA head、D=128，ABBA 两侧均五命令、九次 V 解码、两个完成分组。
完整准入与计算在 ROI 内，数值、guard、CSR 和协议检查保留。

候选额外清除同步执行后 workspace 借用的局部指针；该清理也在计时区间内。
不使用已被否决的规划函数，不能把后续结果归因于分组变化。

执行服务 `prefill-aligned-native-vcs-20261028-01.service`，输出同名目录。
当前待 RTL 完整周期结果，不据静态 lw 数量减少直接推广候选。
生产入口、默认开关和 RTL 均未修改。
