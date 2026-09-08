# QBS/AKV 共享读路径的异常握手核查

## 1. 范围与结论

本次检查针对 `hardware/src/vlsu/qbs/qbs_read_engine.sv`，它同时服务 QBS 和 AKV。
先静态重建 AR 规划、两项 outstanding、R 返回、fault drain 的关系，再加测试台探针。
没有调整模型、软件 hint、超时或数值容差来尝试通过，也没有运行综合或 FPGA 流程。

结论：独立模块的 AXI 接口确实存在“旧 R 返回错误时撤销年轻待握手 AR”的问题。
一次 RTL 修改后新增的六组故障组合通过，正常读路径周期未改变。
这不等于已经发现完整 SoC 在真实模型上出现相同故障：当前 VLSU 的 AXI cut 和
两项 outstanding 限制使该组合受到额外约束，见第 5 节。

## 2. 原逻辑为何有风险

原来的 AR 有效条件是：

```systemverilog
axi_ar_valid_o = plan_state_q == QBS_PLAN_AR &&
    burst_fifo_count_q < ReadOutstanding && !fault_pending_q &&
    !response_fault_event;
```

一旦旧响应触发 `response_fault_event`，ARVALID 当周期就被压低，下一拍 planner
也返回 IDLE。若年轻 AR 从未展示，这样取消没有问题；若前一拍已经 VALID=1、
READY=0，就违反了“保持 VALID 和完整地址通道内容直到握手”的接口约定。

原来的测试从 `response_count < 2` 直接生成 ARREADY。它不能独立表达地址背压
与响应返回，所以即便所有旧测试通过，也没有覆盖这种合法的从设备行为。

本次只给测试台增加独立的 `hold_axi_addresses`，并在上升沿采样完整 AR bundle、
VALID/READY、RRESP/RLAST、burst 数、pending fault 和对外 fault。使用断言核对
上一拍阻塞的 AR 在下一拍（包括最终握手拍）仍稳定。

## 3. 实测的区别

原始 VCS 日志位于 `hardware/qbs_read_axi_20260908/`。以下时间单位为 ps，
相邻采样点相隔一个 10 ns 时钟；年轻地址一直为 `0xf200`：

| 时间 | 旧 RTL ARVALID | 修复后 ARVALID | ARREADY | RVALID | RRESP | 含义 |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 8,015,000 | 1 | 1 | 0 | 0 | 0 | 年轻请求已展示但未接收 |
| 8,025,000 | 1 | 1 | 0 | 0 | 0 | 继续阻塞 |
| 8,035,000 | 0 | 1 | 1 | 1 | 2 | 旧响应 SLVERR；原 RTL 丢掉年轻握手 |

原版在第三行触发 `AR changed or was withdrawn before handshake`，不是计算误差
或看门狗超时。修复后年轻 AR 正常进入 burst FIFO，旧错误响应及年轻响应排空后
才上报原来的故障。

另一个关键点是把 ARREADY 延迟六拍：旧响应已排完、burst FIFO 已空时，年轻
AR 仍然 VALID=1。此时修复后的 `fault_valid_o` 保持 0，直到年轻 AR 握手且其
响应也排完，才允许 owner 结束。未展示的第三个 range 被清理，不会补发。

## 4. 修改与不变量

新增一个控制位 `ar_stalled_q`，记录 `ARVALID && !ARREADY`：

1. 已展示且阻塞的 AR 不再受后续 response fault 撤销；完整 AR 元数据保持。
2. fault 发生时不再规划新 burst；若存在上述 AR，planner 暂不离开 AR 状态。
3. 它最终握手时仍写入原 burst-tag FIFO，不建立另一套响应队列。
4. fault 上报除了要求 burst FIFO 为空，还要求不存在待握手的 AR。
5. fault 期间仍禁止 payload/completion 发布；错误顺序仲裁仍选最早 subrequest。

AR 初次展示时 outstanding 数必须小于 2。唯一的 planner 在 AR 阻塞期间不能
接受另一条 AR，故预留的 tag slot 不会被其他请求消耗。新增断言同时检查该
资源不变量和 AR 稳定性。不存在新增算术单元、数据 SRAM、描述符或 ISA 字段，
正常路径没有额外时钟阶段。若外部总线永久拒绝这个已展示的 AR，故障也必须等待；
不能靠违反 AXI 协议解决外部总线不前进的问题。

## 5. 当前 SoC 集成的边界

`vlsu.sv` 在 normal RVV、QBS、AKV 之间互斥选择 owner，再接入公共 `axi_cut`。
owner 切换要求普通访存与 cut 可见事务排空。cut 的 AR spill 有两项容量；reader
也最多记录两个已握手未完成的 burst。

按这个连接约束，如果 cut 被本 owner 的两个 AR 填满，reader 的 outstanding
也已经满，不会再展示第三个 AR。因此本次独立模块的刺激不代表原 SoC 已测到
可达的故障，当前组合是否完全不可达也没有做形式穷尽证明。修复的意义是模块
自身遵守 AXI，而不是依赖这个特定 cut 容量保证正确；未来换总线连接时也不应
丢失待握手事务。没有为验证而修改现有 SoC 的 cut 或正常 RVV 路径。

## 6. 已通过的验证

| 检查 | 结果 | 能证明的范围 |
| --- | --- | --- |
| 原有 reader 用例 | PASS，修改前后都在 7,880,000 ps 完成 | 对齐、跨页、两 outstanding、背压、PMA/MMU/RRESP/RLAST 处理未退化 |
| 新增异常组合 | 6/6 PASS | SLVERR、早 RLAST、晚 RLAST，各配合同周期接收和额外六拍 AR 背压 |
| 每个新异常后的普通 range | 全部 PASS | 没有残留 tag、FIFO 指针错位或失去接受能力 |
| QBS 引擎 | 33/33 功能点与 4 类 fault PASS | 九种 profile、M 尾块、布局、context 生命周期、VRF 原子性 |
| QBS 周期比较 | 33 个点逐项完全相同 | 同一输入向量文件，没有靠丢请求取得周期不变 |
| AKV 引擎 | PASS | v1 D64/D128，v2 D64/D96/D128、分段 D256、row/column、尾块、计数与异常 |
| AKV SRAM macro 接口模型 | PASS | 与行为 SRAM 使用同一测试台，两者均在 9,579,270,000 ps 完成 |
| 当前 RTL 整核混合回归 | PASS，`traps=0` | 普通 RVV 与 4 条 QBS、10 条 AKV 命令交替执行；不是只测独立模块 |
| Host 契约 | PASS | QBS 转换 56 组合；AKV portable 192 组合、online 调度 108 组合 |
| 生成的 QBS/AKV ABI | `--check` PASS | 本次未改变软硬件 ABI |

QBS 周期分母来自 INT8 极值修复后的
`hardware/qbs_int8_extreme_20260908_aea1aR/after_engine/run.log`，输入文件与本次
`verification/qbs/qbs_command_vectors.txt` 按字节比较相同。QBS/AKV 的模块仿真
不是完整模型速度，也没有用旧 simv 冒充当前 RTL 回归。

新整核回归入口会先重编译当前 VCS RTL，再运行普通 RVV 与 QBS/AKV 交替调用：

```bash
python3 verification/akv/run_current_handoff.py \
  --output hardware/qbs_read_axi_20260908/integration
```

该命令要求新的输出目录，使用 4 lanes、VLEN=1024、1 MiB 仿真 L2。保存代码哈希、
patch、simv/config 哈希和 `status.json`；构建前后源码不一致就拒绝继续。
后台任务不轮询长仿真。`status=PASS` 才表示整核混合回归完成，不能以编译成功
替代运行成功。它不验证 OS 任务切换、中断现场保存或调试抢占；这些仍是部署层缺口。

本次整核回归已于 2026-09-08 10:52:33 UTC 完成。运行标记的基线为 `ac3a7523`
加保存的 RTL/TB patch；其读模块 SHA-256 为
`ca80f45429b3e9c033b2e4cae07a5fad2d9c2484700f1d5320b65eaf85f63503`，与提交的
修复源码一致。小型记录归档在 `verification/qbs/results/shared_reader_20260908/`。

## 7. 结果定位与后续

- `baseline/run.log`：原 reader 测试，旧 RTL PASS。
- `reproduce/run.log`：新探针对旧 RTL 的首错记录。
- `fixed/run.log`：修复后全部 reader 测试。
- `qbs_engine/run.log`、`akv_engine/run.log`：当前共享读模块的两类消费者回归。
- `akv_macro/run.log`：相同 AKV 用例的 SRAM macro 接口模型检查，不是综合。
- `integration/status.json`、`integration/handoff/`：当前整核构建与混合回归。

本次是可靠性收尾，不增加快速路径覆盖范围，也不声称提升模型性能。下一项
性能优化仍需从当前真实输入的周期信号确定主瓶颈；D256 的强 tiled-RVV 对照
数值修复、完整模型长序列精度及 OS context ownership 不能被本轮测试替代。
