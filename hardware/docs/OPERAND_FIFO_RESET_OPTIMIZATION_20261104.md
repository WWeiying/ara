# 操作数输入 FIFO 数据复位精简

## 决策与范围

此前整数 SExt/ZExt 共享试验已结束：完整 ALU-B 操作数队列的同条件 DC
面积从 2405.591957 增至 2442.887957 平方微米，增加 1.55%。该候选未进入
SoC 回归，当前已恢复原来的整数扩展代码。历史记录和失败试验不删除；
`OPERAND_EXTENSION_SHARING_20261104.md` 中的待测安排属于此前阶段。

本轮仅替换 `hardware/src/lane/operand_queue.sv` 的输入数据 FIFO 为本地
`operand_queue_data_fifo`。命令 FIFO 和公共 `fifo_v3` 不改，FPGA 副本不改。
保持原有非直通结构、容量、指针回绕、信用、握手与读写时序，取消的只有
payload 寄存器的复位。没有增加流水级，也没有缩减存储容量。

## 正确性依据

复位和 flush 仍清零读指针、写指针和占用计数。因此所有旧数据立即失效。
每个重新变为有效的槽位，都必须先由一次完整 word 写入覆盖。有效读出不依赖
复位前的 payload。空队列的数据端允许未知或旧值，但 valid、empty、信用等
控制信号必须与原实现完全一致，消费者不得使用无效数据。

flush 与 push 同拍时，payload 可以写入，但控制状态清空，这次数据不成为
有效项；随后从槽位零重新写入。满队列不能接受 push，空队列不能接受 pop，
不增加原实现没有的满队列交换或空队列直通行为。

本地模块保留原 FIFO 的数据选择与写使能结构，避免同时引入按槽时钟门控等
第二种变量。收益假设是普通触发器替代带复位的数据触发器及降低复位负载；
最终是否节省面积由库映射决定，不预先宣称比例。

## 已完成的 VCS 验证

证据根目录：
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`。

`operand_fifo_20261104_01/test.status.json` 为 PASS。

| 测试 | 范围与检查 |
|---|---|
| FIFO 独立测试 | 深度 1、2、3、5；各超过 50,000 周期 |
| 对照 | 真实 fifo_v3、独立队列模型、新实现三方核对 |
| 复位/清空 | 每种深度 83 次复位，超过 500 次 flush，含 flush+push |
| 数据有效性 | 每槽写入标记，检查当前复位/flush 周期内先写后读 |
| 并发与边界 | 空/满、回绕、并发读写、异步复位、局部 X |
| 完整 operand_queue | 8 种整数扩展配置，327,680 项组合检查 |
| 队列事务 | 2,800 次，含 80 次 flush 取消，29,108 次有效握手 |
| 逐周期核对 | valid、credit、pop、select、元素计数及有效数据 |

组合转换检查不代表合法指令覆盖；完整队列测试也不能替代 SoC/FPGA 验收。
只读复核未发现控制逻辑阻断问题。独立 FIFO 测试在复位前撤销 push/pop，
未实测复位保持期间仍有 push 的组合；静态依据仍是控制清空及有效项先写后读。
空队列 payload 的变化是否影响下游消费者，需要后续 SoC 回归检查，不能仅凭
局部 FIFO 对照判定整个 lane 等价。

## 后台验收

入口为 `verification/timing/run_operand_fifo_acceptance.py`，systemd 服务
`operand-fifo-acceptance-20261104-01` 直接托管长任务。

先在 `synopsys_workspace` 中综合新旧完整 ALU-B 操作数队列，使用相同库、
1 ns 时钟和 0.15 ns setup uncertainty。源码、脚本及实际库文件固定并核对。
若面积未降低、clk_i setup 为负或该组最差到达时间变长，停止等待人工分析。
clk_i 路径可能包含时钟门控检查；该门槛不代表全部 I/O、hold 和物理时序收敛。

门槛通过后，六路并行执行既有 62 项 SoC 回归。基线复用已验收的
`vrf_return_soc_20261104_01`，核验相同 ELF 和源码身份。候选中全部 36 个真实
操作数队列与旧实现逐拍对照，并要求应用结果、周期及活动计数不变。
遇到失败停止后续批次。本记录建立时局部测试通过，DC 已启动，尚无新面积数字。

```bash
BASE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out
cat "$BASE/operand_fifo_soc_20261104_01/status.json"
cat "$BASE/operand_fifo_20261104_01/ppa.status.json"
journalctl --user -u operand-fifo-acceptance-20261104-01 -n 15 --no-pager
```

不自动提交，不迁移 FPGA，不启动全 SoC 综合。长期任务无需持续轮询。

## 同日实测与后续功能验收

局部 DC 已完成，不再重跑。以下为相同完整 ALU-B 参数队列的结果：

| 指标 | 原版 | 去 payload 复位版 |
|---|---:|---:|
| 完整部件面积，平方微米 | 2405.591957 | 2238.263973 |
| 输入 FIFO 层级面积，平方微米 | 1274.2800 | 1112.3280 |
| clk_i 最差到达时间，ns | 0.522822 | 0.533525 |
| clk_i setup slack，ns | +0.127178 | +0.116475 |
| COMBO setup 违例数 | 65 | 65 |
| COMBO WNS，ns，QOR 两位精度 | -0.26 | -0.27 |
| clk_i hold 违例数 | 4 | 5 |
| clk_i hold WNS，ns，QOR 两位精度 | -0.02 | -0.03 |

完整部件面积下降 6.9558%，输入 FIFO 层级下降约 12.71%。最差 clk_i 路径
都从命令 FIFO 出发，终止于输入 FIFO 占用计数的时钟门控 latch；不是数据
触发器输出到消费者的数据路径。新映射使到达时间增加 10.703 ps，但仍有
116.475 ps setup 余量。两版均非全部时序通过，不能忽略 COMBO 和 hold。

原 `operand_fifo_soc_20261104_01` 保持 `STOPPED_PPA_REVIEW`，不修改旧报告。
在用户要求收尾验证后，经上述复核，仅准入后续功能与周期回归，不批准物理
时序交付。新入口 `run_operand_fifo_soc.py` 固定候选 RTL、PPA 和 QOR 哈希，
复用已有综合，不放宽任何应用、逐拍数据、周期、活动计数或输入身份检查。
新目录为 `operand_fifo_soc_20261104_02`，服务为
`operand-fifo-soc-20261104-02.service`。SoC 镜像已构建完成并开始首批真实 VCS
仿真，最多六路并行；62 项结果待完成。

补充测试 `operand_fifo_reset_20261104_01/status.json` 已 PASS，原测试不覆盖的
reset-held push 已补齐：复位期间连续写全一、X、flush+push，随后退出复位确认
队列为空，再写零并读回。四种深度均通过，候选 RTL 与原局部综合完全相同。
对应脚本为 `run_operand_fifo_reset.py`，激励为 `operand_fifo_reset_tb.sv`。

### 最终功能验收

`operand_fifo_soc_20261104_02/report.json` 已报告 PASS，62/62 项完成。
全部应用结果、执行周期与活动计数与冻结基线一致；36 个真实操作数队列的
逐拍对照也通过。候选 `operand_queue.sv` SHA-256 为
`e2e44f41cf41615fae0d7e276b20c206c66062103c8faf22ea68548b4372a00c`。
这关闭了上述功能回归等待项，但不改变 COMBO/hold 尚未收敛的结论，也不代表
FPGA 验收或全 SoC 面积验收。旧 STOPPED_PPA_REVIEW 报告保留不变。

```bash
BASE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out
cat "$BASE/operand_fifo_soc_20261104_02/status.json"
cat "$BASE/operand_fifo_soc_20261104_02/ppa-review.json"
tail -n 15 "$BASE/operand_fifo_soc_20261104_02/candidate/build.log"
```
