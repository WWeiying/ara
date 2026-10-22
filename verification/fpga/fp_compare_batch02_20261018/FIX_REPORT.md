# 浮点比较别名源布局转换遗漏：根因与修复验证

## 当前结论

在验证分支 `ara_dsa_signoff_integration` 上确认并修复一处 dispatcher 功能错误：
**比较的源与掩码目的寄存器同号时，源所需的布局转换被错误地当成重复转换取消。**

本次没有修改 `ara_dsa` 主线、FPGA 导出副本或已烧写位流；未运行综合。

六个 FPGA 失败 ELF 中有七条详细失败记录。同一确定性的“源加载后执行 Linux 式
e8/m8 向量保存/恢复，再执行原比较”操作，在旧冻结 RTL 中复现了全部七条记录的
错误计数及 fflags；只修改去重条件后，同样的七个 ELF 衍生场景全部通过。
另七个不插上下文保存/恢复的原参数对照也通过，合计 **14/14 SoC VCS PASS**。

这是已测量的 RTL 根因闭环，但不冒充原始 Linux 完整程序或修复后 FPGA 板测闭环。
板测原运行在何条指令处被 Linux 打断，没有该现场的精确记录，不能倒推成已直接观测。

## 原失败与 A/B 结果

来源为 `/home/wangwy/fpga_runs/ara_va_rvv_explore_20261018_02`、`_04`、`_06`、
`_07` 的 `summary.json`。这六个原始 Linux ELF 均已从原 C、汇编、fixtures
重新编译，SHA256 与归档 ELF 完全一致。衍生测试保留原 tuple、源数据生成和完整
oracle；上下文变体仅在源加载后、比较前增加保存/恢复。

| 原失败配置 | 原 tuple（seed/op/VL/mode/sticky） | 旧 RTL 加上下文后的 errors | 旧 RTL expected/actual fflags | 修复后同 ELF 衍生场景 |
| --- | --- | ---: | --- | --- |
| unboxed unmasked alias v16，e32/m1 | 27/2/32/2/1 | 2 | 17/17 | PASS，errors0 |
| unmasked alias v8，e32/m4 | 0/5/64/3/0 | 9 | 16/0 | PASS，errors0 |
| unmasked alias v16，e32/m8 | 5/3/2/1/0 | 1 | 0/0 | PASS，errors0 |
| unmasked alias v8，e32/mf2 | 16/5/15/0/0 | 5 | 16/0 | PASS，errors0 |
| unboxed unmasked alias v16，e16/m4 | 19/3/256/2/0 | 48 | 16/16 | PASS，errors0 |
| 同上 | 21/3/256/3/1 | 96 | 17/17 | PASS，errors0 |
| unboxed unmasked alias v8，e16/m4 | 1/2/2/1/0 | 2 | 0/16 | PASS，errors0 |

`errors` 不是错误元素数，还可能包含 flags、vstart 和哨兵检查。衍生测试新增了
只在错误时输出的 `FP_BIT index/expected/actual`，不更改原错误计数或允许值。
例如 e32/m4 的9项是8个活动结果位错误加1项 flags 错误；e16/m4 短 VL 的2项是
1个活动位错误加1项 flags 错误。

## 为什么原单点会通过，Linux 下却可能失败

1. 正常源加载采用 e16/e32，寄存器按该 EEW 在四个 lane 间组织。
2. Linux 式向量上下文路径用四组 e8/m8 store 保存全部寄存器，再用四组 e8/m8
   load 恢复。逻辑位值不变，但硬件当前物理布局和记录的 EEW 变成 e8。
3. 恢复 vtype 只恢复架构配置，不会自动把所有物理寄存器转换成原来的布局。
4. 比较需要以当前 SEW 读取源；掩码结果又需要保留目的寄存器原有布局，用来正确
   合并 prestart、未激活及允许保留的 tail 位。这是两个不同的视图。
5. 原去重只比较寄存器号。若源和 vd 同号，就取消源转换，未检查 vd 的视图是否
   真能代替源的视图。因此 MFPU 把 e8 分散的字节按 e16/e32 解读。
6. 错排后的输入既可能改变比较结果，也可能让 sNaN 消失或在错误元素位置出现，
   所以会同时表现为 flags 不变、缺少 NV 或额外 NV；不需要假定多个 FPU 算法错误。

名字带 unboxed 的几个失败 tuple 都是 vv 比较，并不读取 scalar FP 操作数。
当前证据不支持把它们统称为 NaN boxing 错误。

测试的上下文函数只实现这段保存/恢复带来的架构等价变换，不声称模拟了完整 Linux
调度器。它保留 GPR、VL、VTYPE、VSTART、VCSR 和 FCSR，不重新加载原源数组来
掩盖布局错误。十四项测试先在 Spike 上均通过，再执行 DUT。

## 周期级证据

完整原始数据及判据：`cycle_before02`、`cycle_fixed01`、`cycle_cause.json`。
使用同一 SoC ELF，SHA256：
`23178038a32b9082d1d1cd78cfc7119e356a924f367541a6acf7f8b25a4beef4`。
目标为 `vmfne.vf v8,v8,ft0`，编码 `0x72805457`。

仅捕获15700–17000 ns的77个指定信号，不抓整个设计。VPD 转 VCD 后按上升沿前
状态采样，得到1300行逐周期CSV。逻辑字段中的 X 保留为未知值，不按零处理。
VCD 中不参与测量的 real 参数更新被过滤，原始及过滤文件哈希留在 normalization.json。

| 时刻/边界 | 旧 RTL | 修复后 |
| --- | --- | --- |
| 比较发往 backend | 15766.5 ns，vs2=v8、EEW32，但 v8 记录仍是 EW8，转换请求为0 | 转换完成后15792.5 ns才发出，v8已是EW32 |
| 中间转换 | 缺失 | 15767.5 ns、15768.5 ns向 v8、v9投放布局转换 |
| MFPU 源输入 | 8拍×4lane，32个64位字全部不等于逻辑源 | 32个字逐一与原fixture字序匹配，scalar均为+0 |
| MASKU NV | 没有发布预期NV | 正确发布NV=16 |
| 架构 oracle | errors9，flags0 | errors0，flags16 |

自动检查器 `audit_cycles.py` 同时验证转换前后的 EEW、握手、全部32个源字、
标量值和 NV。它不靠最终 PASS 标记反推内部路径。

## 修改内容与安全性

文件：`hardware/src/ara_dispatcher.sv`，`reshuffle_req_d` 去重处。

旧逻辑：

```systemverilog
// vs1 与 vd 同号时取消源转换；vs2 同理（另有少数特殊操作例外）。
(!ara_req.use_vd || (ara_req.vs1 != ara_req.vd))
```

现逻辑：

```systemverilog
(!ara_req.use_vd || (ara_req.vs1 != ara_req.vd) ||
 (ara_req.op inside {[VMFEQ:VMSBC]}))
```

vs2 对应条件也增加同样的比较/进借位掩码例外。仅保留原本已经判定需要的源转换，
不强制所有比较都转换。vs1 与 vs2 相同的正常去重仍保留，避免重复转换同一源。
转换完成后重新译码会读取新的寄存器布局元数据，old-vd 视图随之更新；没有在
比较执行中改变寄存器编号或放宽数据依赖。

没有增加缓冲区、寄存器组、FIFO 或流水级，没有改变 FPU 比较或异常分类规则。
硬件实际只多了去重条件的组合判定。综合面积/时序本轮未测量，不作数值承诺。

## 性能与回归

三项已完成的同 ELF 普通路径 A/B 对照：e32/m1 alias-v16、e32/m4 alias-v8、
e32/m8 alias-v16，其 `trace_hart_0.log` 逐字节一致，包括周期及指令记录。
因此这些不需额外转换的路径没有测得性能退化。

在上述 e32/m4 上下文故障场景中，修复后比错误的旧执行多26周期，用于必需的
源布局恢复。这不能当成正确基线上的性能退化：旧执行少做工作但结果错误。

核心验收：`scenarios_fixed01/results.json`，planned14、passed14。
旧 RTL 前三个反例在 `scenarios_vcs02`；后四个在 `remaining_baseline01`。
旧 RTL 反例故意 FAIL，不计入通过覆盖率。

两项补充回归均已在新镜像上完成并通过独立终验：

| 项目 | 已完成的参考与检查 | VCS 结果目录 | 实际结果 |
| --- | --- | --- | --- |
| 原319调用前缀，优化标量构造/检查 | Spike实际332948条指令；319次原helper顺序、输入、flags/vstart核对；原oracle与packed检查器10对正负对照一致 | `packed319_fixed01` | PASS，581.02秒 |
| 新定向整数邻近矩阵，40个case | Spike PASS；vmseq/vmsne/vmslt/vmsltu，合法非别名vmadc/vmsbc，三重源/目的别名、vstart、掩码、tail、mixed-EEW、context；120项oracle负面自检 | `neighbors_fixed01` | PASS，1353.30秒 |

第一项没有移除前序vector调用或减少原oracle允许值检查，但改变标量指令时序，
不代表原Linux执行调度等价。第二项是新增定向测试，不归为原板卡ELF。
两者都使用本次新冻结RTL镜像 `/home/wangwy/fpga_runs/fp_compare_alias_fix_20261018_01/image`。
后台执行由独立systemd服务直接拥有；长项不持续轮询。

`acceptance.py` 从原始DUT日志重新检查全部16个程序结果、对应ELF、镜像文件、冻结
RTL、输入pins和命令行；同时对验收判据做缺少PASS、同时有MISMATCH/DETAIL等
负面测试。终验结果为 `acceptance.json: PASS_TERMINAL_AUDIT`。单点程序、调用数量
和场景数量粒度不同，不能相加冒充同样数量的独立原始失败或完整ELF。

```sh
systemctl --user status ara-fpcompare-prefix319-fixed-20261018-01 --no-pager
systemctl --user status ara-fpcompare-neighbors-fixed-20261018-01 --no-pager
```

## 仍需单独验收

- 六个原始 Linux ELF 各17920次调用，在修复后的 FPGA 位流上完整重跑。
- 原 indexed-overlap 34项板测，不由本次 FP 比较测试替代。
- 优化后的原319调用前缀属于补充的历史序列回归，不用超时冒充硬件卡死。

旧319前缀30分钟仅执行到第125次 helper，trace仍在标量检查循环，不是已确认死锁。
原15286长前缀因成本主动停止，均保留原始记录，不算通过。

## 再次审核：转换去重与公共路径

本节是修复后的静态审核结论，不冒充形式验证或综合签核：

1. 新条件位于既有转换请求的 AND 去重门控处，不能把原本为0的请求变成1；它只
   阻止比较类源请求因与vd同号而被清除。无需转换的常规路径不增加转换。
2. vs1与vs2同号时的第一层去重没有删除。比较的两个源EEW一致，保留其中一个
   源转换就能修复共享源，不需要把同一物理寄存器转换两次。
3. 转换仍经原RESHUFFLE/WAIT_IDLE路径。等待最后一次VRF写入完成后，重新译码
   才使用新布局元数据。没有在转换尚未完成时提前发送原比较。
4. 别名源转换结束后，比较目的的old-vd布局从同一元数据重新读取，因此不会为了
   目的保留再转换回旧布局，避免两种视图反复切换。非别名目的仍保留独立原视图。
5. 源寄存器组按各自EEW、LMUL及活动区间处理，不把mask目的的一寄存器范围误当成
   全部源范围。40项邻近测试已覆盖跨寄存器的mixed-EEW和非零vstart。
6. VL0、vstart>=VL以及非法指令继续走原来的无操作/异常边界，未放宽合法性条件。
   VMADC/VMSBC与数据源重叠本来非法，邻近测试只覆盖其合法非别名形式。
7. 范围外的算术、访存、规约、QBS/AKV操作不满足新增op条件。没有修改这些路径的
   依赖、队列、完成或异常协议。

为检查公共dispatcher修改没有破坏前一轮故障重启修复，额外复用了三个已验收的
原ELF：Sv39 indexed-overlap在元素1、10、14触发真实缺页，再恢复执行。三项在
同一新冻结镜像上再次全部通过：`memory_controls01/results.json`。
每项均检查真实cause13、一次fault以及错误数0，不只是程序能退出。
输入ELF及其当时封存源重新核对哈希；不以后来修改的同名live fixture替换旧证据。

新增浮点边界组 `fp_edges` 另覆盖FP16/32/64、VV EQ/NE/LT/LE、VF GT/GE、左右及
三重别名、非别名目的、context0/1、掩码、prestart/tail、VL0/1。共24场景，分六个
短ELF。参考阶段六项Spike通过，host双oracle1800对检查及704项注错检查通过。
同一新冻结RTL的DUT结果为 **6/6 ELF、24/24场景PASS**，单ELF实际20.62–22.73秒；
以 `fp_edges_fixed01/results.json` 和每项原始VCS日志为准，而非只看准备阶段的Spike。

本次全部验收汇总：

| 测试集合 | SoC ELF程序数 | 集合内部的检查范围 | 当前结果 |
| --- | ---: | --- | --- |
| 原失败参数与上下文对照 | 14 | 7个真实失败tuple及7个对应对照 | 14/14 PASS |
| 原历史前缀 | 1 | 319次原vector helper调用，完整允许值oracle | PASS |
| 整数邻近矩阵 | 1 | 40场景及120项oracle负测 | PASS |
| 浮点边界矩阵 | 6 | 24场景，FP16/32/64与各类比较边界 | 6/6 PASS |
| Sv39缺页恢复对照 | 3 | 元素1/10/14故障与恢复 | 3/3 PASS |

总计25个SoC ELF执行均通过；这不是25个独立bug。全部由更新后的`acceptance.py`
重读终态日志、输入及镜像哈希核查，记录于`acceptance.json`。检查过程中未发现需要
进一步修改RTL的问题。没有做新的综合、面积/时序估计或板卡重烧。
