# UVM 接入边界

UVM 是可复用的 SystemVerilog 验证框架，不是单独的黄金模型。对本项目，UVM 适合承载以下内容：

- CVXIF request/response transaction agent；
- vector backend alloc/write/done transaction monitor；
- VLSU demand/prefetch、AXI AR/R/AW/W/B monitor；
- reset、flush、backpressure、queue-full 场景的 virtual sequence；
- transaction-level protocol scoreboard 和 functional coverage collector。

不应把以下内容硬塞进 UVM 而省略现有证据链：

- Spike 的 RVV 架构参考语义；
- 向量寄存器、`vl/vtype/vstart/vcsr` 和 store memory 的逐条签名；
- QBS/AKV 的软件契约和 GGML 数值参考模型；
- Linux 的启动、虚拟内存、上下文切换和用户态长稳态。

## 接入规则

1. 先稳定 transaction 字段和 monitor 采样点，再编写 agent；
2. agent 只观察 valid/ready 成功握手，不把 speculative valid 当作提交；
3. 每个 transaction 必须携带 cycle、序号/VID、指令、shape/EEW、地址或 descriptor 版本；
4. protocol scoreboard 检查接口时序，Spike/Python scoreboard 检查架构结果，两者职责不能混淆；
5. UVM regression 的 seed、config、compile command 和 coverage database 必须进入统一 `run.json`；
6. 若 UVM 与现有 VCS 测试结果冲突，先比较采样定义，再定位 DUT，不允许修改参考结果迁就 UVM。

当前仓库的可执行主线仍是既有 VCS testbench、`ara_commit_monitor.sv`、Spike trace/vector comparison 和 Python runner。此目录记录 UVM 的接口和迁移约束；在没有把 agent 接到真实 DUT 顶层并完成一次同等用例比对前，不宣称“UVM 验证已完成”。

## 推荐迁移次序

```text
CVXIF monitor
  -> vector backend transaction monitor
  -> VLSU/AXI monitor
  -> protocol assertions and scoreboard
  -> constrained virtual sequences
  -> reuse in RVV differential and QBS/AKV campaigns
```

迁移过程中保留现有 CSV/Spike 证据，避免一次性重写验证环境造成新的不可比结果。
