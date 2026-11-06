# 输出驻留：真实完整调用 VCS 结果

## 1. 已完成验收

两组独立 VCS 任务均为 PASS，原始日志与回执重新对账通过。
每组采用同一 ELF、同一 RTL 镜像中的 ABBA 顺序，baseline 是当前 Register-PV，
candidate 是 output-tile，不是早期标量 V 解码实现。

| K 类型；V 均 Q8_0 | baseline 平均 cycles | candidate 平均 cycles | 加速比 | 周期降低 |
| --- | ---: | ---: | ---: | ---: |
| Q4_0 | 45308.0 | 35679.0 | 1.269879x | 21.252% |
| Q8_0 | 46917.5 | 37490.0 | 1.251467x | 20.094% |

每组是一次四调用 ABBA，不是多次独立批次的统计置信区间。
输入来自真实 Qwen3：query19、GQA2、D128、可见历史 20，物理 KV cache 容量
256、8 个物理 KV head，测量选中的第一个 KV head 及两个 query head。
这是完整的选中 head-group 调用，**不是整个模型，也不是全部 Attention heads**。

时间包含准入、量化、key panel、native QBS QK、Softmax、PV、归一化与完成等待。
输出打印位于计时区间之外，但会增加整个仿真的墙钟耗时。

## 2. 正确性与身份

- 两组各四次调用的全部 256 个输出逐位一致。
- FCSR 均为 1、VCSR 均为 5，输出与真实捕获 golden 的最大绝对误差分别约
  2.999e-7、2.477e-7；准确值应以 JSON 为准，不替代逐元素容差检查。
- 命令、结果和 key panel 工作量一致，目标存储外围保护检查通过。
- 独立 UVM/协议检查通过，测试前后源码、镜像及动态库 pin 一致。
- 新镜像来自唯一验证分支；不把它称为当前主分支所有未提交 RTL 的验收。
- 没有修改或综合新 RTL，没有重新生成 FPGA bitstream。

原始结果目录位于 `ara_dsa_signoff_integration/verification/out/`：

- `e2e_output_q4_vcs_20261106_01/`
- `e2e_output_q8_vcs_20261106_01/`

重新校验后的摘要：
`verification/performance/evidence/output_native_20261106_01/result.json`。

## 3. 收益来自哪里

本轮没有改变 QBS 算术、描述符、QK 工作量或输出数值顺序。QBS busy 计数约为
699..701 cycles（Q4_0）与 744..746 cycles（Q8_0），两侧几乎不变。
它在整次调用的计数比例仅约 1.5%..2.0%。

因此，这一结果支持“减少 QBS 外的输出更新组织开销”，不能将收益归因于新的
点积硬件。具体变化是：先保存在线 Softmax 系数，再让一组输出跨 token 保留
在 RVV 寄存器中，避免逐 token 载入和写回。每个输出元素的条件缩放及 FMA 顺序
保持不变，不使用重新结合规约来换取速度。

QBS busy 比例只是诊断，不是可以与 RVV busy 相加的互斥时间分解；本轮尚未
测出完整模型的 Softmax、PV、投影各自时间占比。

## 4. 下一阶段门槛

1. 实际 GGML 图中检查新入口与旧入口的选择、完整输出、最终 fflags 和 fallback，
   覆盖 Qwen3 GQA2/20-token 与 Qwen2.5 GQA6/128-token 的真实输入。
2. 更大 GQA 会重读/解码 V，不能仅凭 GQA2 的结果决定默认启用所有形状。
3. 若图级通过，再做完整模型的配对数值与阶段计时；QEMU 仅用于功能，不用于
   外推 RTL 或板上 token/s。
4. 根据更新后的完整推理账目，与矩阵供给/驻留的适度硬件扩展比较。

本轮取得明确的完整调用收益，但尚不能宣称完整 LLM 推理提升 25% 或目标完成。
