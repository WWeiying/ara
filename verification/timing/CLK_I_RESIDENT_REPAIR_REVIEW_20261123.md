# 全设计 clk_i 时序复核：Resident 修复版

## 约束与比较

父版为 `~/dc_runs/ara_payload_credit_20261122_01`，本版为
`verification/out/resident-repair-20261123-01/dc`。两版都用 1.000 ns
周期、0.150 ns setup uncertainty、0.075 ns hold uncertainty、TT
0.9 V/25 °C。两版不只差时序 RTL：本版恢复了 CVA6 浮点退休置脏的
正确性补丁。因此以下数字用于整版对照，不是单因素实验。

| clk_i | 父版 | 本版 |
|---|---:|---:|
| Setup WNS (ns) | −0.133 | −0.071 |
| Setup TNS (ns) | −1235.585 | −225.040 |
| Setup 违例数（DC QoR） | 18,870 | 8,074 |
| Hold WNS (ns) | −0.150 | −0.150 |
| 单元面积（含宏，mm²） | 3.586595 | 3.573401 |

现行 DC 源 SDC 改为 **0.200 ns setup**，hold 保留 0.075 ns，时钟仍为
1 GHz。旧构建目录保持不变。新预算比旧值收紧 50 ps：如果拿同一旧网表
仅改约束重报，`clk_i` setup WNS 约为 −0.121 ns。这个值不是预测的新综合
结果。未来应在同一份新网表上分别报告 0.200 ns 和 0.150 ns；跨版本只比
同约束的数据，不能将新增裕量当作 RTL 退化。

## 当前剩余违例

下列分组来自 `violation.rpt` 的 `clk_i` setup 逐行数据，按终点分组，
使用报告显示的舍入值；其行数与 `qor.rpt` 全组计数不完全一致。终点
所属模块不是违例起因，必须再读实际路径。

| 终点组 | 可见违例行数 | 累计负裕量 (ns) | 最差 slack (ns) |
|---|---:|---:|---:|
| Lane | 2,980 | −82.095 | −0.065 |
| CVA6 issue（含 scoreboard） | 1,926 | −57.731 | −0.071 |
| CVA6 EX | 903 | −35.003 | −0.070 |
| 其他 VLSU | 476 | −18.075 | −0.065 |
| Ara dispatcher | 458 | −15.712 | −0.068 |
| QBS engine | 234 | −2.517 | −0.043 |
| AKV engine | 18 | −0.466 | −0.048 |

已处理的 Resident PV 累加位在此口径下从 4,096 条、−305.372 ns 降到
未列出违例；尚不能说明它在 0.200 ns 下也全部通过。QBS dot/aux
转换表项由 1,024 条、−72.941 ns 降为 32 条、−0.034 ns，其中最差
−0.002 ns。Lane 结果队列仍有大量路径，VMFPU 为 462 条、−22.304 ns，
VALU 为 544 条、−21.753 ns。不能把两组队列违例都归为共享乘法器。

## 下一步优先级

1. **标量 FP 转换级内重新分配逻辑，覆盖最差 WNS。** 最差路径
   `mid_pipe_dst_fmt_q → cast/format selection → FP writeback → scoreboard
   forwarding → fu_data_q.operand_a` 在 FPU 出口达到 0.823 ns，至发射
   操作数为 0.909 ns，约 86 ps 在 FPU 外。另一个终点是 fence 地址
   寄存器：它取同一组实时转发值，不表示实际 fence 会依赖任意浮点结果。
   优先检查能否在现有两个标量 CONV 流水寄存器间前移格式、打包和扩展选择，
   或对标量 CONV 单独调整寄存器位置。不能把所有 FPU 组整体改级数；也不能
   把跨寄存器文件的结果一律屏蔽，`FCVT/FMV` 合法写 GPR。候选应以
   FP→FP、FP→整数、整数→FP、flags、依赖转发和 fence 对照验收。

2. **缩短授权请求到立即应答的组合回路，兼顾 WNS 和 TNS。** 新版
   最差同类约 −0.069 ns，但前 1,000 条中仍有 343 条经过 Dispatcher
   的 `acc_resp_o[345]`。代表路径分支解析 0.290 ns，Ara 请求 valid
   0.335 ns，Ara 响应 0.729 ns，CVA6 目标端 0.907 ns。仅继续缩短
   比较器无法消除 Dispatcher 段约 394 ps。优先在已有 FIFO 的
   等待/授权阶段提前形成不依赖 AVL/VL 或后端资源的静态请求类别；
   最终准入仍用实时配置、异常、flush 和 ready。必须覆盖 vtype/VL 配置变化、
   零 VL、backpressure、异常返回及同周期撤销；不能取消
   `flush_unissued_instr_i`，也不要把所有命令统一多打一拍。

3. **按实际返回路径拆 Lane 问题，不同时盲改 FMA 和乘法。** `clk_i_max.tim`
   的共享乘法代表路径既有 QBS 借用 activation → VMFPU 队列（−0.065 ns），
   也有原生乘法源 → 同一队列（−0.064 ns）。先检查能否按独占 owner
   拆开 EW8 旁路和原生写回，不改 8 位延迟；但原生路径和共享乘积树仍是
   实在的，不能用假路径消除。必要的额外流水应只在局部指标先证实
   不损害 QBS 吞吐后再评估。另有 cast → Lane FP 输入/标签路径和 VALU
   自己的队列路径，应分别提取起点/终点再改，不能用乘法器的结果外推。

4. **Hold 独立处理。** 本轮 hold WNS 未变，下一轮继续保留 0.075 ns。
   用布钟后的传播时钟、最小延时视图观察寄存器和 SRAM 保持路径，不用
   setup 的改进推断 hold 收敛。
