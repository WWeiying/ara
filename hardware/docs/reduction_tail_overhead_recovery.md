# 规约收尾开销回收

## 当前验收结果（2026-10-17）

最终整合快照 `production_tail_integrated_soc_20261017_v1` 已 COMPLETE，50/50 整机功能测试通过。相同 ELF、相同外围、严格相同且顺序一致的 105 个性能窗口，相对时序分级前的规约参考为 18 个周期不变、87 个减少、0 个增加；与首 header 旁路快照的 105 个窗口全部一致。主侧独立重新读取原始 manifest、ELF、simulator 和日志再次得到相同结论，证据为 `hardware/build/reduction_tail_final_independent_cycle_audit_20261017_v1.json`。这不是相对官方未优化 Ara 的性能数据。

| 验收项 | 当前结果 |
|---|---|
| 整机功能 | 50/50 通过 |
| 原有完整性能窗口 | 105/105 匹配；18 不变、87 减少、0 增加 |
| 稠密状态、串行延迟与持续吞吐 | 同 ELF 8/8 通过，无周期增加 |
| 零源、局部相消、seed 高/低不适配 | 同 ELF 8/8 通过，无周期增加，逐条检查结果与 flags |
| 正式 SeedReceive=0 数值/协议 | 500 帧通过；header 等待 169 帧，正文后等待 0 |
| 原 workload 中旧 RCE 写回/年轻 packet 并发 | 4 次真实双握手，owner 与数据均不同 |
| 普通结果写回/年轻 packet 并发 | 独立消费者反压测试 2 次真实双握手，程序自检通过 |
| 当前源码一致性 | 41 个生产文件与最终仿真冻结快照一致 |
| 静态入口 | 391 HDL、455 份冻结文件记录、11 个库哈希通过；未运行 DC |
| 当前整机面积、setup/hold、Fmax | 未重新测量，不能宣称物理收益已保住 |

完整 suite 的 400 条 Lane profile 摘要有效：bypass_fire=5688、RCE 双握手=4、normal_drain_fire=3336。suite 内普通写回/packet 双握手计数为 0，它的正覆盖来自独立 v4 反压测试，不能混入原 workload 的性能收益。普通写回与 packet 的并发修正没有使原 105 窗口变快或变慢；它消除的是定向测试实际覆盖的无谓互斥。

本轮保留共享加法后端、root/finalizer 和 completed 寄存边界，没有增加 FP 运算单元或宽数据缓冲。功能和测试范围内的周期开销回收已验证；整体目标仍缺少新的物理面积与时序证据。功能/周期验收完成后，用户明确授权启动整机综合。当前冻结目录为 `hardware/build/synthesis/reduction_tail_integrated_entry_v1`，容器为 `synopsys_workspace`，1 ns 时钟、0.15 ns setup uncertainty；已启动后台 DC 并进入 ANALYZE。机器验收状态为 `FUNCTIONAL_AND_CYCLE_VERIFIED_PHYSICAL_SYNTHESIS_RUNNING`，尚无新的最终物理结果，没有将目标标为全部完成。下文各阶段的“开发中”“待验证”和周期数字保留为当时的历史记录，以本节的最终快照结论为准。


目标是在保留共享标量加法器、seed与舍入分级、非透明结果输出的前提下，消除上一轮增加的执行周期开销。开发与仿真阶段未启动综合；完成后经用户明确授权启动冻结版本的整机综合，最终面积/Fmax 尚待报告。

## 第一项：省略精确状态的低零块

原Sparse Window只省略高位符号扩展，仍从最低64-bit块开始发送。FP16、FP32中很多正常范围的局部精确和，其最低一个或多个块严格为零。原路径仍发送这些零块并逐周期合并，消耗通信周期。

候选在每Lane的header中编码低零块数，接收端将它们直接重建为零。只省略逐位确认等于零的完整64-bit块，不丢弃小数精度或sticky信息。负数同样按288-bit补码检查低块是否为零。高位符号扩展和guard块仍沿用原协议。

| Header位 | 含义 |
|---|---|
| 7:5 | 省略的低零块数，0到5 |
| 4:0 | 指令ID，保留当前3-bit vid_t的全部位 |
| 13:11 | 原最高发送块编号，2到5 |
| 8 | 原补码符号 |
| 其余 | seed、特殊值、活动信息、格式和舍入模式保持原编码 |

新字段使用原ID字段的零填充位，线路仍为64-bit；当前Ara固定NrVInsn=8，新增仿真断言检查ID宽度不得超过5-bit，未来扩展ID时需同步调整编码。旧包的7:5为零，仍可按原逐块协议接收。非RCE和fixed-window模式不启用低块省略。

每Lane从skip+1发送到原最高块；整个精确值为零时只发送header。RCE在四个匹配header到齐后，从最小起始块进行合并，早于某Lane起始块的部分补零，晚于其最高块的部分补符号。所有低块被省略时，root和carry从零开始正确初始化。全零帧在header汇合后进入原seed处理或seed等待阶段。seed仍插入一次，最终仍只舍入一次。

提前完成的Lane可以交出本地上下文，但旧规约的结果、指令ID与寄存器版本仍由RCE持有。下一context的header保留在原SLDU spill中，由原lane_consumed协议屏蔽；不能被旧frame误消费。header-only且late seed未就绪时，local_complete仍必须等待正确seed。

## 资源与时序边界

新增状态为四个Lane各3-bit起始块编号，共12-bit RTL元数据，以及低零检测和小位宽选择控制。没有新增宽数据缓冲、FP运算器、指令上下文队列或通信位宽；沿用原packet beat寄存器。共享加法器、EXACT_SEED_ADD、root/metadata寄存器、finalizer的seed_in_exact=1以及completed结果寄存器都保留，未恢复原有长组合串接。新增元数据/选择逻辑的实际面积与时序影响尚无新综合测量。

## 当前验证

`hardware/build/rce_exact_window_v5` 独立数值/协议测试通过：80帧、40次同拍结果pop/push、两个延迟seed的header-only帧、80次stale-ID隔离、499个payload token、7周期未来header阻挡。覆盖不同窗口、负数补符号、dense兼容、FP32与FP16、反压和复位。Python整数oracle生成期望结果及异常标志；FP16状态对齐bit125，FP32随机状态保证四Lane和seed不溢出288-bit范围。旧RTL断言保留。早期失败属于向量格式、TB调度及缺少真实SLDU valid屏蔽的建模错误，保留在早期目录中；没有修改数值期望掩盖错误。

第一步完整生产组合冻结在 `hardware/build/production_low_limb_skip_soc_20261017_v1`，使用同一组 50 个 ELF、8 路仿真，现已 COMPLETE，50/50 功能通过。严格匹配原 105 个性能窗口标签后，相对时序分级前 baseline 为 100 个相同、0 个增加、5 个减少；相对 seed 分级版为 18 个相同、0 个增加、87 个减少。最差回退窗口 Slide seed vl=4 由 299→331 恢复为 299。完整证据为 `hardware/build/production_low_limb_skip_full_comparison_20261017_v1`；其冻结后源码变化记录在 `post_run_source_scope.json`，不能覆盖后续步骤。

## 尚未完成的范围

本机制回收的是可省略的通信周期，没有删除两个收尾寄存边界。对于没有低零块的稠密精确状态，skip=0，第一项本身不能消除其新增收尾周期。完整回归与稠密状态的剩余开销仍需继续分析，不能把优先10窗口恢复等同于全场景开销已消除，也不能据此宣称最终PPA已验证。

## 第二步：省略高位 guard 块（已通过定向测试，整机待验证）

原包在最高非符号数据块之外再发送一个符号扩展块。RCE 已保存各 Lane 的原始符号，因而可以直接重建末块以上的和：设末块无符号加法的进位为 C，四个源中负数的数量为 N，则末块以上的有符号整数为 C−N，范围为 −4 到 3。将这个 4-bit 值符号扩展到 root 剩余高位即可。这里不能沿用“按末块 bit63 扩展”的规则，因为去掉 guard 后，末数据块的 MSB 不一定等于原始源符号。

只有 RCE 路径采用紧凑高窗口，最高发送编号允许为 1 到 5；原非 RCE 路径及 fixed-window 模式保持原窗口。解码器同时接受旧 guarded 包和新 compact 包。没有增加宽数据寄存器，只增加负数计数和 4-bit 修正逻辑。第 5 块含真正数据时不能省略它。

一个必须处理的例子是源为 −2^64：低 64 位全零，以上全为符号 1。它的紧凑窗口可以只有 header，但不能当成数值零。若所有 Lane 的起始块都超过全局结束块，则按 header 符号数在该结束边界重建 −N；否则沿现有逐块逻辑合并隐含零/符号。`hardware/build/rce_exact_window_v7` 保留了此问题的原始失败证据，修复后的 `v8` 通过。

`hardware/build/rce_exact_window_v8`：140 帧均通过舍入前 288-bit root 和最终数据/flags 检查，70 次结果同拍 pop/push，7 个 header-only 帧，140 次 stale-ID 隔离。覆盖旧包、新包、末块 MSB 与源符号不同、正进位 3、负修正 −4、异构负数 header-only、第 5 块、FP16 与迟到 seed。独立 Python 小位宽穷举通过 279552 组；旧 legacy 模式 80 帧与 v6 字节一致。

协议改变后，原“最后 guard 的 bit63 等于 header 符号”断言已替换为第 5 块的真正符号检查；在 VMFPU 发送端增加了省略上部必须全部等于原符号的断言，直接用完整源状态检查这一承诺，没有忽略协议错误。

## 第三步：缩窄 seed 符号转换（已通过数值等价测试）

seed 转为精确整数时，先在 25-bit 有符号尾数上取负，再扩展到 288 位并移位，代替原先扩展、移位后再进行 288-bit 取负。FP16 也走同一实现。原有累加加法、seed 捕获拍、最终舍入和异常逻辑不变。`hardware/build/exact_seed_narrow_conversion_v1/finalize` 的 56736 例差分、`oracle` 的 900 组独立检查，以及窗口 `v6` 的 80 帧全部通过。这里说明的是算术等价和结构缩窄，不是新的面积或时序测量结论。

## 第四步：连续上下文消除空闲拍（已通过定向测试）

当旧 root 的最终结果被可靠捕获到 completed 寄存器时，旧结果的 ID、目的寄存器版本、数据和 flags 已整体转移。此边沿可同时接受下一条 command，重新初始化 root 接收状态，无须中间停留一拍 IDLE。completed 被反压占用时仍不允许覆盖；新指令的架构完成仍取决于它自己的最终写回。该控制修改不增加上下文或结果槽，也不连通 finalizer 到架构写回的组合路径，`hardware/build/rce_exact_window_v9/handoff` 已通过旧结果捕获与新 command 同拍、旧 pop/新 push/再新 command 三事件同拍、满缓冲隔离及复位恢复测试；原 140 帧窗口测试也通过。

以上第二到四步不是第一步整机冻结回归的组成部分，必须用新的冻结版本补做整机测试。特别是第 5 块有效且低块非零的稠密状态，既不能靠低零省略，也不能靠高 guard 省略获益；新增 `perf_exact_dense_seed` 用于单独量化此边界，不能用普通范围数据的恢复结果代替它。

## 第五步：将就绪 seed 合并到接收过程（已通过定向测试，整机待验证）

若 header 汇合时 seed 已就绪，而且它转换后的精确整数在当前全局窗口以外仅包含低零和高符号扩展，则可以在接收开始前把它放进已有 root 寄存器。每个尚未处理的 root 块仍保存 seed 的对应块，逐块与四个 Lane 输入合并；处理后的块替换为最终和，不再读取。末块的上部重建相应计入 seed 的符号，最后直接进入 RESULT，省去独立 SEED_ADD 拍。窗口长度不增加；seed 未就绪或不满足窗口条件时仍按原路径先接收源，再绑定 seed。

实现复用原 seed 转换模块，新增 `seed_fixed_o` 暴露转换本身，header 的窗口判断和预载不经过 288-bit root 加法器。四 Lane 数据、seed 块和旧进位用 carry-save 压缩后只经过一个末级进位传播加法器，避免在原多操作数加法链上再串接一个完整加法器。root 仍只有一份，最终舍入之前仍有 root 寄存边界，结果输出仍有 completed 寄存边界。除第一步的 12-bit 起始块元数据外，本步再增加一个 seed_folded 状态位和一个 carry 位，没有增加 FP 单元、宽缓冲或队列深度。

`hardware/build/rce_exact_window_v10` 的 500 帧通过：288 次 fold、212 次 fallback，检查 root、特殊值/零元数据、最终结果及 flags。覆盖 ready-at-header 的普通与 late seed、正负 seed、±0、NaN/sNaN、±Inf、各舍入模式、低位不 fit、高位不 fit、第 5 块有效的稠密值和迟到 seed。`handoff_v3` 覆盖 fold/fallback 两条路径的新旧指令交接、三事件同拍、反压与复位。独立小位宽代数穷举累计通过 448512 组。新增断言检查 header root 已清空、folded seed 有对应有效版本、folded seed 不得再次进入 seed 加法阶段。这些定向验证以 SLDU 提供正确版本 seed 的接口契约为前提，不能代替整机版本相关性回归。

新稠密测试的第一版曾误按 64-bit 条带放置 FP32 输入；实际 EW32 shuffle 按元素逐 Lane 分布，导致该版本局部大项相消，不能证明稠密状态覆盖。第一版结果只保留作原始证据，新版必须依据 `ara_pkg::shuffle_index` 修正映射并独立核对每 Lane 精确和。持续吞吐窗口与每条指令阻塞读取的 serialized latency 窗口分开记录，避免源版本更新的时间或重复结果复用掩盖尾部开销。

静态构建入口 `./s prepare --out hardware/build/synthesis/reduction_tail_recovery_entry_v2` 通过：391 个 HDL 文件、11 个库，未调用 DC。当前完整整机仿真将冻结到 `hardware/build/production_seed_fold_soc_20261017_v1`，保持同 50 个 ELF、同硬件外围、同测量标签；稠密 latency 测试单独记录，不混入既有 105 个窗口计数。

最新版 `production_seed_fold_soc_20261017_v1` 已通过整机编译，50 项仿真继续运行。优先 4 项/10 个窗口全部功能通过并严格匹配标签，相对 baseline 全部减少、没有增加；相对第一步低零版为 1 个相同、9 个减少。Slide seed vl=4 为 299（baseline）→331（seed 分级历史）→299（低零版）→267（当前），Exact Slide 为 501→437→405。证据为 `hardware/build/production_seed_fold_priority_comparison_20261017_v1`。这 10 个窗口不能替代新版完整 105 窗口验收。

当前 seed 转换模块（含 `seed_fixed_o`）另通过 `hardware/build/exact_seed_fold_converter_unit_v2` 的 56736 例差分和 900 例整数 oracle；v1 的编译失败来自测试 `.*` 缺少新增输出连接，保留证据，显式空连接后重跑通过。v10 的数值、元数据、协议、穷举及 hash 证据汇总在 `hardware/build/rce_exact_window_v10/evidence.json`。

真实稠密测试的旧四侧初步结果说明为何需要后续步骤：end4 serialized 16 次为 baseline 432、seed 分级/低零版 464、仅 guard 省略版 448；end5 serialized 为 432、464、464。仅省略零块或 guard 无法消除全部场景的收尾代价。新增 seed-fold 侧正在运行，结果未完成前不能宣称该边界已经恢复。所有这些 baseline 指时序分级前的规约参考快照，不是官方未优化 Ara。

## 第六步：分开 packet 数据与架构写回数据（开发中）

最新同一 ELF 的完整稠密测试位于 `hardware/build/exact_dense_seed_compare_20261017_v2/results_five_sides.json`：seed-fold 的 end4 串行普通/链式均为 432 周期，与 baseline 一致；end5 均为 448，相对 baseline 432 每次仍多 1 周期。持续吞吐四窗口分别为 469/210/478/234，相对 baseline 469/225/462/233 为 0/−15/+16/+1，全部 8 个窗口及 tohost 正确。这证明第五步尚未消除 full288 的全部开销。

检查 Lane 连线发现，原 `lane.sv` 的 SLDU/addrgen stream mux 使用 `alu_result_wdata` 和 `mfpu_result_wdata` 作为规约 token 输入。这两个数据输出同时受到 RCE 架构写回选择器覆盖。即使控制协议不允许错误 token 真正进入地址生成，STA 仍可沿共享数据线追踪 finalizer 到 addrgen；而 exact TX 用 `!rce_writeback` 主动停顿一拍来避免新包被旧结果覆盖。结果输出寄存器解决了长路径问题，但数据所有权本来就不应混在这条线上。

本步新增 `alu_red_data_o` 和 `mfpu_red_data_o` 两个 Lane 内组合连接，经 `vector_fus_stage` 接到原 stream mux。VALU 的 packet 数据直接来自规约写侧累加结果；VMFPU 的 packet 数据在架构 RCE 写回选择器之前产生，exact TX 时就是 `exact_packet_word`。VRF 数据仍可由旧 RCE 结果选择器独立覆盖。删除 exact TX 的 `!rce_writeback` 条件，使旧结果写回与新 packet 传输可以同拍发生；其余目的版本、pending、commit、egress selector 所有权保持原协议。

这里没有增加跨 Lane 网络、FIFO、FP 运算器或数据寄存器，原 interconnect 的三个输入只改接专门的数据源，RCE completed 仍为非透明寄存输出。可以从 RTL 连接确认 RCE 返回数据不再直接进入 Lane 的 packet 数据选择器，但没有新的 STA，不能据此报告 WNS/Fmax。单条串行 full288 的额外输出寄存周期并未因此自动消失，本步首先针对持续执行时不必要的写回/发包竞争。

新的 `hardware/tb/reduction_packet_writeback_profile.sv` 为只读 observer，检查真实同拍 packet/VRF 写回的数据、ID/version、不同 owner 及 packet 反压稳定，并统计双握手与数据不同的重叠。冻结准备位于 `hardware/build/production_packet_egress_soc_20261017_v1`，在保留第五步整机回归的同时另做全 50 项和同 ELF 稠密测试。覆盖计数为零时必须明确未命中，不能把功能通过当成已证明并发收益。当前未启动综合。

第六步优先 4 项/10 窗口现已通过，与第五步周期完全相同；`production_packet_egress_priority_comparison_20261017_v1/profile_summary.json` 记录 1212 次 exact packet 握手、424 次 packet 停顿、164 次 RCE VRF 写回，但双握手计数为 0。因此现阶段没有证据表明本步缩短了这些 workload 的周期。正在补独立消费者反压注入，要求实际命中新包与旧结果同拍，且不改变数值预期或伪造 VRF/RCE 握手。`./s prepare --out hardware/build/synthesis/reduction_packet_egress_entry_v1` 的 391 HDL/11 库静态检查通过，未调用 DC。

消费者反压的独立验证现已通过：`hardware/build/packet_writeback_stall_soc_v1/evidence.json` 固定原 dense_v2 ELF，8/8 case 和 tohost=0；只在首次同寄存器 seed chain 的结果首次出现之前门控 SLDU completion_valid，并检查相应 RCE result_ready=0。共阻断 22 周期，结果有效反压 5 周期；随后同一采样沿发生年轻 packet owner=1/data=0x1 与旧 VRF 写回 owner=0/data=0x40e00000 的双握手，dual_fire=1、distinct_data=1。原断言开启、数值预期未改。注入反压的周期不能用于生产性能比较；该证据属于 packet-egress 冻结版本，不自动覆盖后续新 RTL。

## 第七步：已就绪局部状态直接发送 header（开发中）

VMFPU 的 `INTRA_LANE_REDUCTION` 看到 `exact_sum_out_valid` 时，原来仅设置下一状态 `EXACT_GLOBAL_TX`；header 要到下一周期才有效。此时归一化后的 root 和元数据早已位于 accumulator 的 `HOLD_RESULT` 寄存器中，额外状态切换周期不承担计算或可靠接收工作。

新增组合事件 `exact_header_bypass`：仅当前 issue/processing 都有效、ID 相同、当前确为 RCE 精确规约且本地输出已有效时，在 INTRA 当拍发送 header。使用虚拟 beat=0，不读取上一条指令遗留的 beat 寄存值。TX 和 bypass 共用一份逐包推进、header-only 释放及 pending 所有权代码，没有复制队列管理。header 被接收后直接进入首 payload beat；遇反压则进入原 TX/beat0，保持同一个 header，不重复发送。局部状态仍只有最后一个实际包被可靠接收后才能移交，架构完成仍等 RCE 最终写回。新增断言检查首 payload 不重发/不跳过及 header bypass 不是指令退休。

本步没有新增寄存器、加法器、seed 阶段或 finalizer 组合串接。提前发送的输入来自已经注册的 accumulator 状态；seed/root/finalizer/completed 的寄存边界均保留。它针对 full288 没有可删数据块时仍然存在的 1-cycle 状态等待，而不是恢复透明收尾。静态结构说明不代替新的面积或时序测量。

`production_header_bypass_soc_20261017_v1` 已编译通过并开始全 50 项。优先 4 项/10 窗口通过，相对 baseline 全部减少；相对 packet-egress 为 1 个相同、9 个减少。此时 observer 已实际命中 bypass_fire=472、旧 RCE 写回/年轻 packet 双握手=2、不同 owner/data=2，故绕过状态等待也使第六步的并发路径在原 workload 中真正发生。证据位于 `production_header_bypass_priority_comparison_20261017_v1`，仍只覆盖这 4 项。新增同 ELF 稠密侧正在运行，完整结束前不推断 full288 结果已恢复。

## 第八步：packet 期间保留旧普通结果写回（开发中）

检查第七步首 header 周期时又发现，原 exact TX 数据选择仍会把 packet 设为 VRF 默认数据并强制 VRF request=0。单独拆开 RCE 写回还不够：`rce_ordinary_drain` 允许更早的普通 MFPU 结果在规约本地计算时排空，但这个赋值在 packet 周期又把它关掉了。header bypass 若沿用此赋值，也会无谓抑制一拍原本合法的旧普通结果写回。

当前将公共 `mfpu_base_wdata` 明确用于旧队列/ordered-bypass/架构 seed 校正，VRF 与 packet 分别从它取默认值，exact 只覆盖 packet 输出，RCE 只覆盖 VRF 输出。删除 packet 对 VRF request 的强制清零，原普通结果的 request、ID、version、byte-enable 与真实 grant 协议继续决定其写回。新增断言检查 packet 活跃且旧普通结果可排空时，VRF 数据、ID/version 和 request 均匹配旧队列。没有增加宽数据缓冲或运算单元。新版 observer 另计 normal_drain_fire、normal_packet_both_fire，不改旧 RCE 的统计语义。

最终整合快照安排为 `hardware/build/production_tail_integrated_soc_20261017_v1`，与第七步生产源的唯一差异为 VMFPU；所有前轮仍使用原冻结输入完成，不覆盖历史结果。完整 50/105、同 ELF 稠密 8 窗口、普通写回与 packet 真并发定向测试及新静态入口都通过前，当前工作树仍不能宣称整体验收完成。

第七步稠密侧已完整通过：`hardware/build/exact_dense_seed_compare_20261017_v2/results_seven_sides.json` 记录同 ELF 的 8 个窗口与 tohost=0。full288 end5 串行普通/链式均为 432，持平 baseline，相对第五/六步的 448 回收最后每次 1 周期；end4 为 416，比 baseline 432 每次少 1 周期。持续吞吐四窗口为 453/194/462/218，相对 baseline 469/225/462/233 没有增加。bypass_fire=512，证明真正走了旁路；此 dense app 的双写回/发包握手仍为 0，并发正覆盖来自优先 workload 或独立消费者反压测试。

`./s prepare --out hardware/build/synthesis/reduction_tail_integrated_entry_v1` 通过 391 HDL/11 库静态检查，未调用 DC。最终整合快照的 `current_production_hash_check.json` 已确认 41 个唯一生产文件与当前工作树完全一致。`hardware/build/reduction_tail_recovery_acceptance_20261017_v1.json` 分开记录当前验收门槛，尚未把历史快照、优先窗口或未重新测量的物理结果当成最终完成。

最终整合优先 4 项/10 窗口已完整通过，标签严格一致，相对 baseline 全部减少、相对 header-bypass 版全部相同，没有周期回退。`production_tail_integrated_priority_comparison_20261017_v1/profile_summary.json` 记录 bypass_fire=472、RCE 旧结果/年轻 packet 双握手=2、不同 owner/data 各=2；普通写回重叠计数为 0，正覆盖仍等待独立消费者反压定向。上述优先证据与最终 50/105 和 dense 8 窗口分别记录，当前源码 41 个生产文件与冻结版一致。


## 最终整合补充验收：稠密边界与正式 seed 协议

最终整合版本同 ELF 的 8 个稠密测试窗口全部通过，结果和 flags 正确，tohost=0。`hardware/build/exact_dense_seed_compare_20261017_v2/results_eight_sides.json` 的 integrated 侧记录：16 次串行规约，end4 普通/seed 链均为 416 周期，end5 全 288-bit 普通/seed 链均为 432 周期；相对时序分级前参考的 432 周期分别减少 16、持平。持续吞吐四窗口为 453/194/462/218，相对参考 469/225/462/233 没有增加。该结果与 header-bypass 快照完全一致；8 窗口不代替最终完整 50 项/105 窗口回归。

正式配置 `RceExactSeedReceiveEnable=0`：中央接收在 header 汇合处等待正确版本 seed，然后接收源状态正文；它不等于取消 Lane-local 提前计算。此前 v10 的 500 帧单元测试显式启用了可选的 SeedReceive=1，覆盖正文接收后的 seed 等待，不能据此声称正式配置启用了该协议。本次补充 `hardware/build/rce_exact_window_production_seed0_v1`：正式 mode0 的 500 帧全部通过，169 帧在 header 处累计等待 338 周期，正文后等待为 0；425 次 fold、75 次 fallback。mode0 与 mode1 数值预期、metadata 完全相同，仅因 seed 到达时点不同，137 帧的 fold 路径预测变化。新测试平台的 mode1 兼容 500 帧也通过，默认向量与旧 v10 逐字节一致。生产配置和 RTL 没有为测试改变。

结构核查 `hardware/build/reduction_tail_structural_audit_20261017_v1.json` 以 seed 分级快照为参照：两个共享加法后端源码哈希保持一致，已有 288-bit root 存储复用，显式新增 RCE 状态 14 bit，没有新增 FP 运算单元、宽数据缓冲或队列槽。root/finalizer/completed 的寄存边界保留。这些是 RTL 结构证据，不等于映射后的面积与时序测量；新逻辑和布线可能影响物理结果，本轮没有启动综合。


普通结果与规约 packet 并发的最终定向证据为 `hardware/build/packet_normal_stall_soc_v4/evidence.json`。测试仅在 Lane 0 消费者请求输入处注入反压，生产者请求始终有效、grant 保持为 0，旧队列头数据和标签稳定；释放后生产者/消费者请求与 grant 均为 1。实际观察到 2 次普通写回与年轻 packet 同拍接收，owner 和数据不同，普通排空共 16 次；程序逐项检查 32 个 VFADD 元素均为 3、规约结果为 35、flags=0、tohost=0。39 份项目 RTL 与 observer 均和当前冻结版一致。注入反压只证明这条并发路径正确，不用于生产性能比较。

该定向测试的 v1/v2 曾错误门控生产者 procedural output；SV release 后该变量在重新求值前仍保持强制值 0，触发请求一致性断言。诊断确认数据/ID/version 正确，随后将门控移到消费者 input net，v3/v4 通过。失败目录和原断言保留，未通过修改 RTL、数值预期或关闭断言解决。v4 日志明确打印释放前后请求及 grant，避免将测试门控造成的假握手当作正覆盖。


## 面积与时序复核边界

这轮回收并非零逻辑代价：header 路径增加 seed 定点转换后的窗口适配检测与 root 预载选择，正文合并增加第五操作数的 carry-save 压缩，首 header 旁路增加包有效和控制选择。新增显式状态只有 14 bit，不能据此估算总门面积，因为组合逻辑、扇出和综合缓冲同样占面积。RTL 核查确认没有把 seed 的 288-bit 加法器串入 header 预载，正文只保留一个末级 67-bit 进位传播加法器，也没有把最终舍入直接连回架构输出；但这些结构事实仍不能证明新关键路径一定满足原时序目标。

后续物理验收应分别检查 seed 转换/窗口判断到 root 输入、Lane header 状态检测到 SLDU 接收控制、carry-save/末级加法到 root、completed 反压到新 command ready，以及原共享加法反馈路径。比较必须保持库、约束、外围与综合选项一致，单独列出 RCE、四个 Lane 和整机面积增量，并报告 setup/hold；不能只以总面积或单个局部模块结果代表全部收益。当前不启动综合，因此这些指标继续标为未验证。


## 为什么 fallback 不必然产生净周期开销

是否进入 `EXACT_SEED_ADD` 不能单独判断整条指令是否变慢。时序分级比早期透明路径增加了 seed 处理和完成寄存两拍，但首 header 旁路回收一拍；其余代价由省略 payload 或 seed-fold 回收。早期发送端 `hardware/build/static_legacy_soc_v1/rtl/vmfpu.sv` 的最小窗口为两个 payload 块，且通常包含最高有效块上方的 guard；当前省略完整低零块及高符号块。

当源状态真正占满第 1 到第 5 块时，没有可以省略的块，但任何有限 FP16/FP32 seed 都在这个完整 288-bit 窗口内，因此 ready seed 可 fold，回收独立 seed 拍。当 seed 不适合源窗口而必须 fallback 时，源窗口必然缺少一些低位或高位覆盖；这些缺少的部分正是低零或高符号省略的对象，有机会通过少发 payload 弥补 seed 拍。源状态为零也不能直接认定变慢，因为旧协议仍发送至少两个 payload，而新协议可以只有 header。

这是无额外反压、相同本地计算条件下的周期预算解释，不是任意混合指令流的性能证明。接口反压、上下文就绪和资源竞争可能改变可见周期，仍必须用同 ELF 整机实测验证；新增零源、局部相消、seed 高位不适配和 seed 低位不适配的串行测试专门检查这条推理，结果完成前不作为新的性能结论。


上述 fallback 补充测试现已完成：`hardware/build/exact_seed_fallback_compare_20261017_v1/comparison.json` 的同 ELF 8 窗口全部数值、逐指令 flags 和 tohost 检查通过，没有周期增加。每窗口 8 条串行规约，普通/seed 链分别为：全零源 192→184 / 192→184；每 Lane 局部 +1/−1 相消 192→184 / 192→184；最小 subnormal 源配 seed=1（seed 高位不适配）192→192 / 192→192；源为 1 配最小 subnormal seed（seed 低位不适配）208→192 / 208→185。最后一条 seed 链只有最初的 seed 是 tiny，后续使用上一条已舍入结果，oracle 也逐条递推，不能把所有八条都称为低位不适配。高位不适配的两组每条均应置 NX，低位不适配组首条也检查 NX；不能以结果数值恰好未变为由忽略 flags。

测试源已归档至未被 git 忽略的 `hardware/tb/reduction_probes/`，包括 fallback/dense latency/ordinary overlap 的 main.c、整数 oracle 生成器、构建与同 ELF 对照入口及 README。原 `apps/` 与 `hardware/build/` 整体被忽略，不能仅依赖这些目录保存可复现方法；归档三份 main.c 已逐字节核对，未修改正在测量的源或 ELF。本项仍是独立边界证据，不替代最终 50/105 整机验收。


首 header 旁路快照 `production_header_bypass_soc_20261017_v1` 现已 COMPLETE，50/50 功能通过；`production_header_bypass_full_comparison_20261017_v1/comparison.json` 严格匹配 105 窗口，相对分级前参考为 18 个相同、87 个减少、0 个增加；相对 packet-egress 快照为 19 个相同、86 个减少、0 个增加。该证据已覆盖完整既有 suite，但最终整合版额外包含普通结果排空修正，仍须完成它自己的 50/105 验收，不能直接继承这份完整结果。
