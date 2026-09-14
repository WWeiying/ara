# QBS 入口译码流水验证

基线 `4cb07780`。本次修改将逻辑/物理位置译码放到两项入口 FIFO 之前，
保持 SRAM 仲裁与写合并，并修正激活 context 回放对块尾立即写完的依赖。
没有修改 ISA、算术顺序、SRAM 容量/端口或 AKV 数据通路。

- `commands.csv`：33 个功能命令的修改前后周期；四类故障及 context 复用也通过。
- `real.csv`：七个真实 Qwen2.5 切片，完整 K；周期增加 0.078%--0.263%，
  输入文件、访存字节、range 数和 dot 工作量保持一致。
- 33 个命令中最大周期增幅为 Q4_0、M1/N1/Kb65 的 4.27%，不是所有形状都小于 0.3%。
- `macro_functional.log`：真实 TSMC SRAM 功能模型，81 组配置、81 组零停顿连续流、
  256 种 strobe、非连续/重复写及满队列独立 clear 通过；关闭物理 timing checks。
- `payload_equivalence.log`：110592 次 payload 对照通过，不是形式等价证明。
- `handoff.log`：普通 RVV 和 4 个 QBS、10 个 AKV 命令交接通过，traps=0。
- `summary.json`：PASS 状态、源文件/输入/日志 SHA-256 及两组局部 DC 状态。
- `rtl.patch`：相对基线的生产 RTL/生成器差异，不包含用户原有面积报告改动。

本目录只归档完成的功能结果。通用 SRAM 的首次 65536-mask 运行在 600 秒后
超时，不计为完整通过；失败初版回放和宏时序 notifier 诊断保留在原始运行目录，
不作为通过结果。局部/整机 DC 尚在后台运行，功能通过不等于 1 GHz 已闭合。

说明、逐周期根因和复现命令：
[`hardware/docs/timing_optimization_port.md` 第 22 节](../../../../hardware/docs/timing_optimization_port.md)。

原始仿真：`hardware/timing_qbs_ingress_20260914_jEgtgo/`。
新的冻结整机综合：`hardware/dc_runs/20260914_0521_qbs_ingress/`。
