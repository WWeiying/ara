# clk_i：缩短浮点转换返回路径

基准为 `verification/out/resident-repair-20261123-01/dc`。在其 1 GHz、
setup uncertainty 0.150 ns 的 `clk_i_max.tim` 中，第一条路径从标量
CONV 的 `mid_pipe_dst_fmt_q` 到 issue 的 `fu_data_q.operand_a[37]`，
slack 为 −0.071 ns。网表里舍入器的 `abs_rounded_o[32]` 在 0.486 ns
到达；其后 U1083、U2628、U2632 等门再次归并舍入结果各位。数据从
FPU 出口到达 issue 数据端还有约 86 ps。修改只针对前一段，不屏蔽
合法的浮点转整数结果旁路。

设 m 为截断幅值、r 为原舍入器产生的 0/1 进位。原负整数输出先算
m+r 再取负；新电路一次计算 ~m+(1−r)。正整数和浮点结果仍是 m+r。
三个边界条件也不必等最终加法：模加为零只可能来自 0+0 或全一+1；
负整数最小值只可能由其幅值或前一个幅值舍入而得；正边界溢出只需
检查进到边界位的进位和该位的原值。加法宽度、舍入决策、异常优先级、
寄存器使能、valid/ready、flush 和流水级数不变。标量和 Lane 使用同一个
cast 实现，QBS 专用的 INT32→FP32 端口也实例化它。

| 已执行验证 | 结果 |
|---|---|
| Spike SoftFloat 对照 | 540 个转换向量，结果和异常标志零差异 |
| 原 DC 源码与新 RTL 的 VCS 对照 | 每配置 24,000 个刺激周期；四种配置共 67,947 个未取消的输出握手 |
| 周期级检查 | 每周期 ready/valid/busy；对所有有效输出（含停顿）检查数值、flags、符号扩展、mask、tag 和 aux；覆盖背压、flush 和复位 |

原始证据为 `verification/out/cast-fused-softfloat-20261123-01/audit.json`
和 `verification/out/cast-fused-equiv-20261123-01/pass.json`。这是部件证据，
不是 SoC 时序或完整模型性能结果。

后续任务 `verification/out/cast-fused-soc-dc-20261123-01` 复用上轮
已验收的 9 个 ELF、参考签名及周期；全部匹配后才在容器内启动全局 DC。
正式预算为 setup 0.200 ns、hold 0.075 ns；另在相同映射下按 0.150 ns
导出 `qor_compare_setup015.rpt`，然后恢复 0.200 ns 再导出网表约束。
验收应分别看 `clk_i_scalar_conv_max.tim` 和全局 WNS/TNS/面积。
Dispatcher 的分支撤销路径、Lane 共享整数乘法返回路径及 hold 并不因
这次代数变换而消失。
