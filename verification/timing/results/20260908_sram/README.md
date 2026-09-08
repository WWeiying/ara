# SRAM Buffer Candidate Results

参考版本为 `be1487b5`，候选为 `ara_dsa_sram` 中的工作区实现。
`summary.json` 保存实际源文件、binary、日志和输入向量的 SHA256。
这些是功能和周期结果，不是面积、时序、功耗或 FPGA 结果。

- `engine_cycles.csv`：新编译的参考/候选版本，33 个相同 engine 用例。
- `real_cycles.csv`：七个真实模型切片，输入 K 完整，输出切片缩小。
- `sram_adapter_0.csv` / `sram_adapter_4.csv`：真实 Q4 Decode 的前 128 个周期，
  分别对应两个 adapter；取样在下降沿，不能把 valid 列直接累加当作握手次数。
- `adapter.log`：81 组配置、65536 种 strobe、独立唯一字节计分板及解码对照。
- `macro_functional.log`：相同测试使用真实 TSMC 8x256 模型，显式关闭 timing check。
- `engine.log`：33 个 engine 用例、四类 fault、激活缓存生命周期及 SRAM/旧寄存器解码对照。
- `profile.log`：448 个 profile 定向用例，逐步核对算术和 fflags。
- `synthesis_define_vcs.log`：VCS 在 `SYNTHESIS` 宏下的功能测试，不是综合。
- `handoff.log`：普通 RVV、4 个 QBS 和 10 个 AKV 命令的顶层交接。

性能代价必须保留：三个真实 Q4 Prefill 点不变；Q4 Decode 增加 1.58%；
三个 Q6 Prefill 点增加约 1.10%--1.16%。短功能用例的最大相对退化约 10.40%。
详细机制、拆分写的根因、适用边界及复现命令见
`hardware/docs/qbs_block_buffer_sram.md`。

重新汇总本机的已完成结果：

```sh
python3 verification/timing/summarize_sram_results.py \
  --run-root /tmp/ara_dsa_sram_20260908 \
  --handoff hardware/sram_handoff_20260908 \
  --output verification/timing/results/20260908_sram
```

汇总器拒绝缺失用例、异常日志、不同输入、变化的 traffic 或顶层验证后变动的源文件。
最初没有连接 SRAM 读/ready 的旧 profile TB，以及未关闭 hold notifier 的宏试跑，
属于环境迁移诊断，未混入本目录的 PASS 结果；原始诊断日志仍留在 `/tmp` 根目录下。
