# QBS SRAM 写合并验证

- 寄存器对照：`be1487b5`。独立补写 SRAM 起点：`621c4bda`。
- 当前代码仍在 `ara_dsa_sram` 工作区，未合并到 `ara_dsa`，未运行 DC/PNR。
- `engine_cycles.csv`：33 个完整 engine 用例全部通过，逐项周期与寄存器版相同。
- `real_cycles.csv`：七个真实模型切片全部通过，逐项周期、traffic、dot 与寄存器版相同。
- `write_merge_cycles.csv`：寄存器、独立补写 SRAM、合并写 SRAM 三者对照。
  Q4 Decode 减少 35 cycles，三个 Q6 Prefill 切片各减少 488 cycles；其余三点不变。
- 448 个 profile 用例通过；两种存储模型均通过 81 组配置、81 组无停顿连续写、
  全部 65536 种 strobe、重复覆盖、非连续地址、clear 及读窗口比对。
- 非连续/重复定向序列出现 4 个必要的域阻塞周期，正确排空，没有丢数据或重复计数。
- 顶层普通 RVV、4 个 QBS、10 个 AKV 命令交接通过，traps=0。
- SRAM 仍为 24 个单端口 bank，逻辑 payload 3584 B，宏物理容量 6144 B；
  pending 寄存器仍为 634 bit，没有增加数据缓冲容量或 dot pipeline 级数。

## 如何阅读证据

- `*.log` 是原始通过日志的复制，不从 CSV 推测结果。
- `sram_adapter_0.csv` / `sram_adapter_4.csv` 来自真实 Q4 Decode，
  从首个写入开始抓 128 拍，在正沿寄存器更新之前采样。
- `wcommit_old/new` 和 `acommit_old/new` 是两个槽位实际提交的字节 mask。
  mask 为十六进制；无效槽位的 remaining 值不参与调度，不能单看该值判断有待写数据。
- pending 是占用而非等待；old/new 同拍提交也不总等于同一个 bank 的合并。
- 真实上游反压看 `QBS SRAM ingress`，不能看已被握手门控的 adapter valid。
  Q4 Decode 的权重入口仍有 72 个 blocked 周期，其中 36 个 adapter 未 ready，
  但权重 pending=0，且总周期、阶段周期均与寄存器版相同。这不是额外写拆分开销。
- TSMC 宏测试使用 `+notimingcheck` 做功能验证；`synthesis_define_vcs.log`
  是定义 `SYNTHESIS` 后的 VCS 测试，二者都不构成物理时序或综合结果。
- `summary.json` 包含输入、binary、原始日志及顶层 RTL 的 SHA-256，
  汇总时检查用例身份、周期、工作量和 source hash，避免不同版本混用。

主设计说明：`hardware/docs/qbs_block_buffer_sram.md`。
本次原始目录：`/tmp/ara_dsa_sram_merge_20260908/`。
此前的失败诊断保留在其中的 `check/`、`diagnostic/`、`bus_check/`，
不计入此目录的通过结果。诊断定位并修正了写合并实现中格式映射函数的
隐式 profile 输入问题；最终回归均采用显式 profile 参数的实现。

此结果不能外推为任意非连续访问无停顿、全模型性能或已达到目标主频。
