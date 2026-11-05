# VRF 返回网络精简：实现与验证记录

## 1. 本轮范围

本轮落实 `LANE_QUEUE_DATAPATH_STATIC_AUDIT_20261104.md` 中的 A1，修改主工作区
`hardware/src/lane/vector_regfile.sv`。不修改 FPGA 副本、不改变 SRAM 宏、队列
深度、读延迟、吞吐、指令语义及异常处理。原有共享整数乘法器和 ALU 优化保持
原状。A2 格式转换共用、A3 FIFO payload 复位分离尚未实施，避免将多个风险
不同的修改混在同一次验收中。

审计时的 VRF SHA256：
`583f5b0e5af1a6ac7d120280923b858024f017bc475a79fb3d406449211e2314`。

当前候选 VRF SHA256：
`fde952dbb0a0ca86f9e5046b06d44aeef280110f5a62aa872465604a7587fe5d`。

## 2. 为什么可以去掉仲裁

每个操作数队列只对应一个 requester。它每拍至多请求一个 bank；各 bank 的
读写仲裁不会复制请求，写操作也不会产生有效读返回。读数据、有效位和目标
队列标签均延迟一拍，因此同一个队列在一个周期中至多收到一个有效 bank 返回。

旧返回网络为每个队列实例化轮询仲裁器，但输出始终 ready、不使用输出暂存，
集成流量又不产生同队列多源竞争。这些轮询状态和优先级选择没有实际调度作用。

新实现对每个队列计算：

```text
hit[bank] = 返回有效位[bank] AND (返回标签[bank] == 当前队列)
queue_valid = OR(hit)
queue_data[bit] = OR_bank(hit[bank] AND bank_data[bank][bit])
```

逐位归约提供并行选择，不增加流水级，也不把多队列返回串行化。SRAM 和返回
标签寄存器完全保留。用返回有效位而非只看标签，避免带 AluA 标签的写操作
污染读数据。

这是 requester 与 VRF 的集成不变量，不是任意独立端口输入都成立的条件。
因此增加生产 RTL 断言：返回 valid 必须已知、有效标签必须已知且合法、每个
队列的 hit 必须已知且满足 onehot0。非法碰撞不允许被静默合并。

## 3. 等价边界

- 每拍有效位严格一致，有效数据逐位四态比较；不比较无效数据的值。
- 无效拍旧仲裁器可能输出某个 bank 的旧值，新路由输出零。FIFO push 和
  snapshot capture 由 valid 控制，因此这些值不构成有效传输。
- 有效数据中未初始化字节产生的 X 应保留，不能统一屏蔽。有效 SRAM 数据
  为 Z 不在本次合法域中；位运算和旧 mux 对 Z 的四态传播不完全相同。
- 不新增 flush，不提前取消已经发出的返回。原有 snapshot/replay、队列信用
  和 flush 处理不变。本次不据此宣称所有既有 snapshot 边界已经验收。

## 4. 已完成的局部验证

工具为宿主机 VCS，实际实例化新旧 `vector_regfile`、通用 SRAM 和时钟门控。
除新旧 miter，还使用独立的逐字节存储参考模型，不以两份 RTL 相等作为唯一判据。

| Banks | 检查周期 | 有效读取 | 写入 | bank/queue 映射 |
|---:|---:|---:|---:|---:|
| 1 | 30,395 | 15,141 | 7,682 | 9 |
| 2 | 30,404 | 30,641 | 14,842 | 18 |
| 8 | 30,458 | 121,963 | 60,580 | 72 |
| 合计 | 91,257 | 167,745 | 83,104 | 99 |

全部通过。覆盖未初始化读取、连续读、最大并行返回、目标切换、随机读写混合、
字节写使能、局部 X 数据、空闲未知标签、门控唤醒和复位后保留的 SRAM 内容。

四项负向测试均被生产 RTL 断言拒绝：同队列重复返回、越界标签、未知有效
标签、未知返回 valid。不能把负向测试的预期拒绝计作软件程序执行 PASS。

证据根目录：
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`。

- `vrf_return_20261104_02/status.json`：正式局部结果。
- 同目录 `run.log`、`negative1.log` 至 `negative4.log`：原始证据。
- `vrf_return_20261104_01`：保留首次脚本验收失败记录。RTL 已触发预期 fatal，
  但脚本误要求 VCS 必须返回非零；后续依据明确的生产 fatal 标志验收，不改 RTL，
  不覆盖旧结果。

## 5. 已安排的后续验收

### 5.1 SoC 回归

目录：`vrf_return_soc_20261104_01`。

以已通过的 `shared_alu_shift_soc_20261103_02` 冻结源码为基础，仅替换
`vector_regfile.sv`，新增只读旧路由监视器。复用已核验的 62 项基线日志、ELF、
镜像身份；新候选编译后最多六路并行。检查应用结果、结束周期、区域周期及
已有四 lane 活动计数完全一致，并逐拍比较真实 SRAM 返回的新旧路由结果。
出现首批失败或周期变化后停止继续派发。

这不是对当前所有未提交工作区改动的验收，也不是 FPGA 或覆盖率 signoff。
62 项尚未完成前，不宣称系统性能无回退。

### 5.2 部件面积和时序

目录：`vrf_return_ppa_20261104_01`。

在 `synopsys_workspace` 容器中运行 DC。直接抽取新旧生产 RTL 的返回网络代码，
使用相同输入/输出寄存器、库和约束：1 ns 周期，setup uncertainty 0.15 ns。
不重新实现算法作为替代被测对象，不计入未改变的 SRAM。

最终 `report.json` 的面积是带相同寄存器边界的部件比较，不是整个 lane 或
SoC 面积。综合未完成前，不填写预计节省比例或宣称时序已通过。

### 5.3 状态命令

```bash
BASE=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out
cat "$BASE/vrf_return_soc_20261104_01/status.json"
cat "$BASE/vrf_return_ppa_20261104_01/status.json"
journalctl --user -u vrf-return-soc-20261104-01 -n 10 --no-pager
journalctl --user -u vrf-return-ppa-20261104-01 -n 10 --no-pager
```

长任务由 systemd 直接托管，不依赖交互会话；后续检查结果即可，不持续轮询。

## 6. 最终结果

`vrf_return_soc_20261104_01/report.json` 已 PASS，62/62 项的应用结果、执行
周期和活动计数与基线一致。候选 RTL SHA-256 为
`fde952dbb0a0ca86f9e5046b06d44aeef280110f5a62aa872465604a7587fe5d`。

`vrf_return_ppa_20261104_01/report.json` 中，相同寄存器边界的返回网络面积
由 6593.327893 降到 5477.303901 平方微米，下降 16.9266%；clk_i 到达时间
由 0.640244 降到 0.471378 ns，setup slack 由 +0.202664 改善到 +0.367344 ns。
这里不包括 SRAM，不能将这个比例当成完整 VRF、lane 或 SoC 的面积降幅。
上述结果关闭局部综合和限定 SoC 回归等待项，不代表物理或 FPGA signoff。
