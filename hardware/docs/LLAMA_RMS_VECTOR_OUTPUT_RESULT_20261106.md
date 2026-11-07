# 融合 RMSNorm 输出向量化的完整调用结果

## 结论与范围

在 4-lane、VLEN1024、128-bit 物理内存平台的实际 VCS 中，保留原始 FP32
平方、按序 FP64 求和及 mean/scale 计算，仅将符合条件的输出循环改为两次
独立舍入的 RVV 乘法和向量写回，完整融合调用得到以下结果：

| 实际输入 | 原始两个试次 cycles | 候选两个试次 cycles | 完整调用提速 |
| --- | --- | --- | ---: |
| Qwen3 第一层 Decode，1x2048 | 55591、55405 | 23544、23258 | 2.371608x |
| 第一层 Prefill，4x2048 | 222325、222231 | 87762、87646 | 2.534411x |

采用同一 ELF 的原始/候选/候选/原始顺序，两侧包含相同的 CSR 完成与 fence
边界。数值输入按真实模型 embedding 重建，保留原捕获输出的逐位核对链路。
这是完整局部融合调用的时间，不是单个向量指令吞吐，也不是整个模型提速。
本次没有修改 RTL，没有新增硬件资源，也没有执行综合或面积估算。

## 为什么不是单纯增加算力

前一项仅优化求和的候选，完整调用收益约 1.10x。求和加速后，输出阶段仍有
逐元素标量推进成本。本次在保持计算顺序的前提下，利用已有向量乘法和
load/store 通路完成输出；没有改用近似平方根或改变求和树，也没有把两次
乘法合并成另一种舍入语义。

这说明向量硬件已经存在，并不代表软件在整个调用中都充分使用了它。选择
新增硬件之前，应先确认剩余成本是当前硬件能力不足，还是现有通路没有
被调用。该结论只针对已测区域，不能据此排除矩阵或 Attention 新硬件投入。

## 验证证据

- exact-ELF Spike 与 VCS 的功能/CSR 摘要一致；Spike 周期不用于性能数据。
- 40960 个结果检查，53 个原 Norm 边界、10 个顺序敏感求和场景通过。
- 155 个输出边界场景通过，包括 110 个向量调用、40 个标量 fallback 和
  5 个空调用；涵盖别名、舍入模式及特殊值等保护条件。
- 实际轨迹包含 288 次按序 widening reduction 分配和 458 次向量输出 store。
- 独立协议检查通过。后继 collector 重新执行原始日志、ISA 摘要、轨迹活动、
  原始/candidate 变换、compile/link 配方和完整协议重放，而非只读取 PASS。

原始 worker：
`ara_dsa_signoff_integration/verification/out/e2e_rms_vector_output_vcs_20261106_01/`。

独立 collector：
`ara_dsa_signoff_integration/verification/out/e2e_rms_vector_output_collect_20261106_01/`。

版本内入口：
`verification/performance/evidence/rms_vector_output_20261106_01/result.json`。

## 接入前还需完成的工作

当前仍是经过验收的实验实现，没有自动替换 llama.cpp 的生产库。应以同一
输出 helper 接入 GGML 的适用分支，保留 FRM、vstart、布局及别名保护和原始
fallback，再完成完整模型功能配对。普通有效 RAM、不可观察中间 fflags 的
软件契约不应扩展为异常/缺页等价性声明。

必须在模型执行账目中测出 RMSNorm 的实际占比，才可估计这项局部提升的
端到端贡献；不能把 2.37x/2.53x 与 QBS 或 Attention 的局部加速相乘。
