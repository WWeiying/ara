# 当前板测问题修复索引

工作目录：`/home/wangwy/openproject/ara_dsa_signoff_integration`。
本轮修改相对验证分支起点 `7d5d1829`，尚未合入 `ara_dsa`。
原始板测资料、源码、ELF与失败日志均保留。完整范围见
[CURRENT_SCOPE.md](CURRENT_SCOPE.md)。

## 已测量并修改的逻辑

下表的通过范围以对应报告中的程序、参数和镜像为准。一个模块测试数
或一组源码移植程序的通过，不能推导出所有历史 Linux 程序都已通过。

| 问题及触发条件 | 原错误及修复行为 | 修改位置 | 主要实测证据 |
| --- | --- | --- | --- |
| 重启后的谓词流与计算消费范围不一致 | ALU/MFPU/MASKU从头消费时，谓词也从字零提供完整范围；SlideUnit的mask read/commit计数不扣除vstart前缀；访存仍按其起点提供谓词 | `lane/lane_sequencer.sv`、`masku/masku.sv` | [lane测试](lane/)、[整机回归](integration/README.md)，原slide及比较场景与补充控制 |
| slideup源流错误地随vstart偏移 | 源请求从所需的原始流起点读取；写回单独保护prestart，非零vstart不插入元素0标量 | `lane/lane_sequencer.sv`、`sldu/sldu.sv` | 41项源请求检查及原slide整机程序；[47项原浮点move/slide单例](fp_moves_original47/README.md) |
| 大偏移slideup过早读取尚未写完的mask字 | 对跨mask字的slideup保留生产者完成依赖，避免把较早的写回脉冲当作后续字可用 | `ara_sequencer.sv` | [原始大偏移场景及逐周期原因](large_offset_slide/)，六个完整源码程序在candidate02通过 |
| 整寄存器搬移将架构vstart当成存储EEW的元素数 | 根据架构SEW换算字节位置，再换成内部EEW的起点；非零vstart且存储EEW大于CSR SEW时归一化源布局，越界起点为空操作 | `ara_dispatcher.sv` | 原wholemove、混合EEW补测；含扩宽规约的联合译码回归覆盖459配置/12738检查；candidate03代表性回归保持通过 |
| m8浮点扩宽规约被误判非法 | 区分单寄存器规约结果与普通扩宽向量目的组，允许合法m8源组规约 | `ara_dispatcher.sv` | 原VL0非法反例、十个非零VL控制及整机回归 |
| 整数扩展的高端源/目的重叠在布局转换中破坏源或反复转换 | 精确识别六种VZEXT/VSEXT；必要时保存窄源，转换旧目的布局，再重放源 | `ara_dispatcher.sv` | [VL127原场景、vf2/vf4/vf8矩阵](extension_overlap/)，candidate02的38项回归包含全部六个矩阵 |
| gather写回覆盖重启前缀 | gather结果的字节使能保护vstart之前的目的元素 | `masku/masku.sv` | 12项端口检查、原vv场景和补充vx前缀场景；[gather整机](integration/README.md) |
| 有序浮点规约异常掩码与被选中元素错位 | 对压缩到低位的规约操作数使用对应元素的有效性，避免丢弃应提交的NV | `lane/vmfpu.sv` | [有序规约测量](ordered_reduction/MEASURED_20261010.md)，166项局部回归与原稀疏mask异常场景 |
| 无序规约的异常/活动状态归属错误 | 区分真实有效贡献与填充值，按指令保存跨lane活动状态，避免后继规约覆盖当前状态 | `lane/vmfpu.sv` | [无序规约](ordered_reduction/unordered_widening/)、[连续规约](ordered_reduction/unordered_widening/epoch/)，1/2/4lane共432项epoch检查 |
| 浮点比较对all-off、tail或prestart元素多提交NV | 逐元素NV随比较结果送入MASKU，在实际消费的有效元素范围内提交 | `lane/vmfpu.sv`、`masku/masku_operands.sv`、`masku/masku.sv`、`ara.sv` | 产生端606项、消费端24项、归档汇编来源的五项局部移植（含重建oracle和派生控制），及e16/e32/e64比较矩阵；[比较检查](ordered_reduction/comparison_producer/) |
| MASKU结果队列满时覆盖描述符 | 队列满时禁止默认描述符赋值，保留已有条目 | `masku/masku.sv` | 原地址96变98的局部反例、队列满与分批grant控制；[比较消费检查](comparison/) |
| 屏蔽的普通load/store仍进行地址翻译并引发异常 | 先确认请求归属与当前元素谓词；屏蔽元素产生skip描述符，活动元素才进行翻译/地址检查 | `vlsu/addrgen.sv` | [组合访存验收](masked_translation/COMBINED02_ACCEPTANCE.md)：原3个Sv39场景、扩展8场景、NF2四场景 |
| 异常load完成早于前缀实际VRF写回，且残留字节状态污染后继指令 | 部分结果按真实FIFO项入队，等待最终VRF grant，再清理issue/commit和mask状态 | `vlsu/vldu.sv` | done15早于write35的原测量，6个异常收尾及4个到达顺序局部控制；上述Sv39整机验收 |
| sequencer异常响应早于对应load完成 | 保存对应VID的load done，仅在异常路径等待它；普通无异常路径保持原响应条件 | `ara_sequencer.sv` | 响应9早于done21的端口反例、正常/FOF/其他VID控制，以及candidate02整机验收 |
| 标量插入在VL2/vstart1时没有写入元素0 | VMVSX/VFMVSF内部请求起点改为0，架构CSR的vstart>=vl空操作判断保留 | `ara_dispatcher.sv` | [candidate03逐周期验证](fp_moves/CANDIDATE03_REVIEW.md)：BE0变BE0x03，11项通过；[原47单例](fp_moves_original47/README.md)全部通过 |
| 比较源随vstart偏移，但结果仍从位零压缩 | 整数及浮点比较源从零提供完整流，MASKU继续保护架构prestart和谓词 | `lane/lane_sequencer.sv` | [原e8/m2首错及逐周期证据](comparison_alias_original/SOURCE_ORIGIN.md)：源148错误映射到位84；candidate04相同ELF与周期后验PASS；[19原单例+16控制独立验收](comparison_alias_original/candidate04_audit02/README.md)全部PASS；[浮点三项同ELF对照](comparison_source_controls/AB_REPORT.md)全部PASS，零起点控制周期不变 |
| Gather重启时索引源偏移与MASKU从零扫描不一致 | VRGATHER/VRGATHEREI16的AluA索引流从零开始；保留架构vstart、目的字节保护及MaskB实际数据索引 | `lane/lane_sequencer.sv` | [M5聚焦波形验收](gather_original_review/gather_repair05/m5_successor01/focused01/acceptance.json)、[两项原98调用前缀独立终审](gather_original_review/gather_repair05/m5_successor01/prefix_terminal_audit01/TERMINAL.md)、[48项回归终审](gather_repair05/m5_regression01/TERMINAL_AUDIT01.json)；原第66调用元素128由0修为79，16项完整控制CSV保持一致 |
| 索引load与目的组重叠且物理EEW混合时，源布局转换被去重取消 | 对重叠indexed load保留必需的vs2源转换，复用原快照、目的转换和源重放；不更改架构vstart | `ara_dispatcher.sv` | [M5首错与M6修复根因](indexed_overlap_original/REPAIR06_ROOT_CAUSE.md)、[三项完整Sv39独立验收](indexed_overlap_original/repair06_whole3_audit01/REPORT.md)、[M6回归48及16项完整周期对照](gather_repair05/m6_regression48_terminal_audit01/REPORT.md)；原错误地址修为0x40017000，代表性控制无观测周期退化 |

## 当前通过证据对应的镜像

### M7/M8 访存修复及验收范围

以下两类问题已有周期级反例，修改在当前工作区中；M6 镜像不包含这些
修改，不能将 M6 的通过记录算作修复后回归。

| 问题 | 已取得的证据 | 当前验收状态 |
| --- | --- | --- |
| masked load/store 异常后只丢弃一个谓词字，提前清除上下文，阻止 MASKU 排空 | 四模块联合测试中 VL8 可完成，VL9 第三个谓词字不能被接收，MASKU/global running 不清零；load/store 均有独立反例 | VLDU/VSTU 七种 VL 及局部控制通过。M7 真实 Sv39 的 VL9 load/store 各914检查通过，包含陷阱CSR、页修复、同PC重试和后继访存；16项正常控制310350行周期记录与M6一致。原VL8 Linux停滞仍单列 |
| indexed store 的后续地址错误使已接受 AW 的合法前缀丢失 | M6 与首版掩码修复在 WREADY 暂停时均出现 AW=1、W=0、B=0 就完成异常；放开 WREADY 后仍无写数据 | VSTU 等待正常/skip 描述符排空及 B 收尾，局部控制及M8整机966检查通过，验证写前缀、poison及vstart2同PC重试；M8全部20项回归通过 |
| 本地 indexed 不对齐异常仍误发MMU请求，仲裁无法释放 | M7周期79692对0x40000011发出MMU请求，同周期检测不对齐；下一拍AddrGen撤销请求，CVA6却锁在ACC且没有实际翻译回应，handler标量load滞留。Ara AW/W/B及flush均已完成 | AddrGen仅允许有效且对齐的indexed地址请求翻译。M8同ELF退出0/262.724秒，966检查及14项CSR恢复读取通过；全20项回归通过，16正常控制及完整resident indexed load合计1146852行周期与非周期字段无差异。见 `masked_translation/indexed_early_illegal_failure_review01.md` |

详细源码逻辑、输入身份及结果路径见
[异常掩码排空修复](masked_translation/EXCEPTION_MASK_DRAIN_FIX.md)。
M7 首元素缺页程序已验证真实 lane 队列下的恢复推进和后继访存结果，
但没有采集内部 flush 周期信号。有效 indexed 写前缀的整机恢复已经在
M8 相同失败 ELF 上通过966检查，并纳入20项回归；另一个 indexed load
不对齐异常/重试程序也已通过，终态为 `M8_INDEXED_LOAD_MISALIGNED_PASS`，
输入未变化且无中止，见 `masked_translation/indexed_load_misaligned_sv39_prepare01/vcs_m8_load01`。
M7 首元素缺页证据在 `masked_translation/mask_drain_sv39_prepare01`；
正常周期对照在 `memory_candidate07_controls16/prepared01/complete.json`。

### M9 非掩码步长访问的对齐异常

M9改动限AddrGen。非掩码VLSE/VSSE可能以对齐元素开始，但不对齐的
stride使后续元素发生异常。该路径需要等待有序异常结果，而不能在
首元素地址处理后提前ack整个指令；否则后续异常与已推进的owner不一致。
初始对齐检查改用包含vstart的实际起始地址，初始异常的vstart同周期
可见。后续元素对齐异常进入有序descriptor路径，保留已接受的合法
load/store前缀，避免重复作为early illegal完成。

`unsafe_stride_defer`只选择剩余多元素且stride不满足EEW对齐的非掩码
VLSE/VSSE；正常对齐unit、零步长和负步长控制不扩展这一等待条件。
局部LOAD7/STORE4检查已通过，包含真实W/B反压和前缀完成约束。
整机M-mode/Sv39各load/store共四项现已完成独立验收：2790检查、
36必要memory owners、精确cause4/6、vstart1、同PC重试、已完成前缀
poison保留、后续不同owner和CSR恢复。证据入口：
`unmasked_strided_alignment_soc_m9_sv39_worker03/terminal_report01/REVIEW.md`。
独立controls16的310350完整事件行与M8包括周期在内逐字节一致。
这些结果不代表所有访存模式都零性能代价或原Linux记录全部关闭。

原整机检查器的Spike-only tohost引用错误已在独立后继修正，复用两份
已结束M-mode CSV，不改RTL或oracle；旧NOT_ACCEPTED批次原样保留。
原外层service退出码未能追溯，实际simulator/checker的数值退出成立。

### 完整序列验证的当前进度

以下是当前检查时点的状态，不把参考模型或检查器通过计作RTL通过。
软件检查的指令数减少是验证提速，不是处理器性能提升；测试仍保留
原始输入、顺序、计算段及完整结果检查。Linux进程、信号和上下文行为
尚不能由这些源码移植程序替代。

| 测试范围 | 已取得证据 | 尚待完成 |
| --- | --- | --- |
| FP16/m8 别名比较原始前682次连续调用 | M8实际退出0，完整682调用、349184结果位、1364 guards及flags/vstart检查通过；封存证据复核通过 | 原17920次父程序与Linux范围仍未关闭 |
| VSMUL e8/m4 原始前777次连续调用 | M8实际退出0，完整777调用、397824结果字节、1554 guards及vstart/vxsat检查通过；封存证据复核通过 | 原10752次父程序与Linux范围仍未关闭 |
| VMACC e8/m4 原始前482次连续调用 | M8实际退出0，完整482调用、246784结果字节、964 guards、6266 helper指令检查通过；封存证据复核通过 | 原22400次父矩阵与Linux范围仍未关闭 |
| 段访问e16/m2完整144配置 | M8模拟器退出0；后继完整CSV核验及独立审查通过，120项数值/24项原规则允许的不对齐异常，983040 oracle字节/288检查点；旧NOT_PASS保留 | 是能力分支验收，不是144数值PASS；Linux历史范围仍未关闭 |
| 剩余负步长38项源码场景 | M6十组、38项独立终审记录已归档，650641检查，1362个唯一输入/证据pin匹配；实际child与offline wait全0 | 外层worker退出未知；M6证据不是M8/M9回归，也不是Linux或完整父程序验收 |

VMACC准备阶段的Python兼容性、源码偏移误报、字符串转义及输入路径错误
已经单独记录，未被当成RTL错误，见
[准备问题核查](arithmetic_restart_original/macc_disjoint482/full482_preparation_main_findings01.md)。
段访问检查器额外检查每个必要访存指令的后端完成记录，包括VL>0的
all-off目标；不能只凭总体分配/完成数相等验收，见
[完整144项主线核查](masked_translation/segment_full144_main_review01.md)。

### M6 功能及代表性回归已验收

indexed load 在索引组与目的组重叠、且重启后的活动索引寄存器具有不同
物理 EEW 时，通用同寄存器去重会取消必需的源布局转换。M5 波形确认
索引16/17被按32位布局拼接，导致错误地址 `0x0000400040017000`。
当前 dispatcher 仅为 `indexed_load_groups_overlap` 保留已有源转换请求，
继而复用原源快照/目的转换/重放路径。

证据见[根因及修复](indexed_overlap_original/REPAIR06_ROOT_CAUSE.md)和
[独立静态审查](indexed_overlap_original/STATIC_REPAIR06_REVIEW.md)。M6独立
构建通过；完整50轮 fault_ov1 程序已由严格checker验收PASS，退出0，耗时
3059.083465秒，21595项检查、1600次fault/repair/retry。完整CSV独立复算
已通过，见[首个完整程序独立验收](indexed_overlap_original/repair06_pilot_audit01/REVIEW.md)；
驻留页重叠对照也已完成独立验收，原50轮及第51次masked restart、1632个结果、
102个guard、5215项检查通过，见
[驻留页原始CSV验收](indexed_overlap_original/repair06_controls_audit01/RESIDENT_REVIEW.md)。
非重叠缺页对照随后完成，三项完整source-faithful Sv39程序及真实worker退出0
已经独立验收，合计48405检查、4832结果、302 guards，见
[三项独立终审](indexed_overlap_original/repair06_whole3_audit01/REPORT.md)。
独立波形审查已确认转换/快照/重放顺序，
原错误MMU地址及mtval均纠正为 `0x40017000`，见
[波形独立审查](indexed_overlap_original/repair06_wave_audit01/REVIEW.md)。
三项完整任务状态入口为
`indexed_overlap_original/repair06_worker/prepared01/complete.json`。
48项代表性回归已完成独立终审：755项输入pins及372项原始证据不变，
48个实际ELF/退出0/日志及oracle均核对。16项正常控制、310350行完整
含周期CSV与封存M4基线逐字节一致，未观察到这些控制中的周期退化。
见[回归及周期独立终审](gather_repair05/m6_regression48_terminal_audit01/REPORT.md)。
此结论不覆盖全部工作负载，尤其不能用于断言所有混合EEW或访存故障路径
周期不变；也不代表历史Linux故障全部关闭。
回归先前通过严格后台门槛实际启动，
[启动独立核查](indexed_overlap_original/repair06_followup/fresh02_launch_audit01/REPORT.md)
确认真实前序退出后才启动子任务，不用marker或GC默认状态代替。

| 镜像 | 实际验收范围 | 结果位置 |
| --- | --- | --- |
| candidate02 | 38项算术/重启整机回归、10项正常RVV/QBS/AKV控制、3项原Sv39、8项Sv39扩展、4项NF2；掩码逻辑3单例+3前缀 | [组合验收](masked_translation/COMBINED02_ACCEPTANCE.md)、[掩码逻辑](mask_alias_original/BOUNDED.md) |
| candidate03 | candidate02基础上增加标量插入修复；11项定向、16项代表性回归、47个原来源浮点move/slide单例通过 | [定向测量](fp_moves/CANDIDATE03_REVIEW.md)、[16项对照](fp_moves/CONTROLS16.md)、[47项原单例](fp_moves_original47/README.md) |
| candidate04 | candidate03基础上增加比较源起点修复；19别名比较原单例+16项控制独立验收通过；另19标量比较原单例、3浮点A/B、8NaN控制、8Gather来源tuple及4NF8来源tuple通过。代表性控制15份CSV一致，重启比较结束周期增加1、非周期事件不变。38项组合回归已全部通过并正常退出，独立复核1368项pin和76份原始日志 | [源起点测量](comparison_alias_original/SOURCE_ORIGIN.md)、[35项独立审计](comparison_alias_original/candidate04_audit02/README.md)、[标量19验收](comparison_scalar_original/terminal_audit01/README.md)、[NaN验收](comparison_source_controls/nv_successor/DUT_REPORT.md)、[Gather续跑](gather_original_review/CONTINUATION.md)、[NF8四项终态](masked_translation/nf8_strided_review/sv39/vcs_candidate04_01/complete.json)、[M4回归38项](integration/CANDIDATE04_38_TERMINAL.md) |

candidate03的16项对照完整提交CSV（包括周期字段）与candidate02逐字节
一致。标量插入的七个正常/空操作控制同样一致。原本错误的混合EEW插入
增加了必要的目的寄存器布局转换，其额外周期见定向报告。

masked普通访存修复会将该路径按元素处理。`vm=1`的原burst路径保持，
但不能将这些正常控制的周期一致推广为所有masked访存都没有性能代价。

## 待完成的原始问题验收

### 2026-10-14 Unboxed e16/mf4 完整17920终态

M9原unboxed/unmasked e16/mf4连续17920 source-port已独立接受：
286720结果位、35840 guards、17920 flags/vstart、326144 helper，
10752次FPR committed writeback；89600 memory+15360非空target共
104960对owner完成。sim实际0/6687.051487秒，systemd success/exited0，
collector wait0/9.037511秒、observer wait0；750输入pins不变。
证据：[独立终态报告](fp_compare_unboxed_full17920_worker_review01/TERMINAL_REVIEW01.md)。
这是已有修复的完整来源验收，不是新增RTL修复或arithmetic22成员。
FPR证据不等于物理读回，原Linux未关闭；独立alias-v8 e16/m8仍仅
first700/17920接受。旧unboxed265 ERROR/退出未知及startup记录保留。

### 2026-10-14 e32/m4 完整矩阵终态

M9 e32/m4 原5985连续调用已独立终态验收：sim实际0/9010.677922秒，
systemd success/exited0，collector实际wait0/16.913秒；766080结果、
11970 guards、77805 helper及389025实际输出读取完整。独立核对全部
5985 call和65837 owner元数据，29925 memory+3762 target共33687对完成，
含117个op24目标；1203 nonraw pins不变，未重读CSV/raw。
证据：[终态报告](arithmetic_restart_original/full_e32_m4_terminal_review01/REVIEW.md)。
算术完整来源验收并集增至18/22、86940 calls，剩4/20160；详见
[当前范围](CURRENT_SCOPE.md)。这是跨冻结镜像并集，不是原Linux闭环，
也不增加原程序未定义的fflags专用oracle。

### 2026-10-12 最新验收与仍未定位的问题

以下是已有修复的新增验收证据，不是新增 RTL 修改或额外 bug 数：

| 范围 | 当前 M6 验收 | 证据入口 |
| --- | --- | --- |
| 完整 e8/mf8 算术重启矩阵 | 原顺序4095次调用、65520结果元素、8190保护元素通过；原检查器的复位寄存器误报经严格镜像绑定后离线复核，旧ERROR保留 | `arithmetic_restart_original/full_small2_e8_offline_recovery_audit01/run01` |
| 完整 e16/mf4 算术重启矩阵 | M6原顺序4095次调用、65520结果、8190保护元素及4095次返回vstart检查通过；VCS退出0/6406.346秒，独立完整CSV核对退出0/179.785秒；不推断未保留的外层历史service退出 | `arithmetic_restart_original/full_e16_mf4_terminal_audit01/run01/TERMINAL.json` |
| 完整 e32/mf2 算术重启矩阵 | 原顺序5985次调用、95760结果元素、11970保护元素通过；实际仿真退出0，10026.131秒；完整CSV独立验收通过 | `arithmetic_restart_original/full_e32_mf2_terminal_audit01/run01/TERMINAL.json` |
| 完整 e64/m1 算术重启矩阵 | M7完整5985调用、95760结果、11970保护元素及5985次返回vstart检查通过；仅优化标量验证编译，源/helper/输入/顺序不减。实际仿真退出0/7544.534秒，完整4794396行CSV验收通过 | `arithmetic_restart_original/full_e64_m1_o2_vcs_m7_plan01/prepared01/complete.json` |
| NF7 indexed完整96个来源场景 | 当前M6的24份CSV独立验收通过，284816次检查；不再仅有旧M2验收 | `masked_translation/indexed_review/sv39/nf7_m6_terminal_audit02/terminal01/result.json` |
| NF2所有40个来源失败单例 | 当前M6来源程序验收40项，另2项正常控制单列；不等同原Linux完整父程序 | `masked_translation/segment_review/nf2_remaining34_terminal_audit01/terminal01` |
| MIN/MAX全NaN与全屏蔽 | 两项MIN及两项MAX来源单例均通过SoC完整144字节结果、标志、vstart和协议检查；全NaN为规范NaN，全屏蔽保留原seed位型 | `nan_min_soc_terminal_audit01/run01/TERMINAL.json`、`nan_minmax_soc_terminal_audit01/run01/TERMINAL.json` |
| 负步长异常load/store及FOF | 原负步长load、store各一项及两项原FOF场景通过当前M6独立验收；store含17275项检查、故障前缀可见性、页修复和同PC重启；FOF缩短VL后的未定义尾元素不强制检查 | `masked_translation/negative_stride_load_vcs_m6_plan01`、`masked_translation/negative_stride_store_vcs_m6_plan01/terminal_waiter01/terminal01/result.json`、`masked_translation/fof_two_singles_vcs_m6_plan01` |
| 零步长 e64/m2 完整16来源场景 | M7实际仿真退出0/2831.976秒。旧checker缺少启动mstatus及opaque ABI保存建模，旧NOT_PASS保留；绑定冻结源和镜像的修正后，离线完整验收16场景、12fault、16ecall、18188检查、512结果、32guards及16384内存字通过，无新DUT运行 | `masked_translation/zero_stride_e64_m2_original16_offline_recovery03/terminal.json` |
| 零步长 e64/m8 完整16来源场景 | M7实际仿真退出0/3624.929秒；旧producer误报保留，经绑定镜像的独立离线审计，16场景、12fault、16ecall、21260检查、2048结果、32guards及16384内存字通过，没有重新跑RTL | `masked_translation/zero_stride_e64_m8_original16_offline_recovery01/terminal.json` |
| Gather VI0 e8/m4、e16/m8 原112调用前缀 | M7两项实际退出0/3963.540及3748.594秒；各57344结果、224guards、112返回vstart、1456helper指令及完整输入检查通过。仅关闭此数值前缀缺口，不关闭未知11stall或完整2688调用child | `gather_original_review/vi0_missing2_vcs_m7_plan02/prepared01/complete.json` |

**浮点比较新增验收**：原e16/m8浮点比较前50次调用现已在M6通过，
保留第50次之前的49次调用；25600个结果位、100个保护元素及标志/vstart
检查通过。实际VCS退出0，用时1977.807秒，独立完整CSV复核退出0，
见 `fp_comparison_original/fp_alias50_terminal_eventcheck01/run01/TERMINAL.json`。
历史第50次至少62个活动结果位错误未在此M6程序复现，但尚未证明
其确切根因；不能用源起点修复解释它，因为该调用vstart=0。
后续短VL的多余NV与已修的活动资格过滤
机制相符，但完整682调用程序尚未运行。详见
[原始症状与当前逻辑核对](fp_comparison_original/fp_original_current_logic_review01.md)。

原11条Gather停滞均有用户态停止退休证据，但没有恢复出确切未返回
tuple或VID握手历史；已有来源前缀通过不能关闭它们。当前不据此猜测
RTL修复，详见[停滞触发证据复核](gather_original_review/gather_stall_exact_trigger_review01/REPORT.md)。
后续[请求至完成链静态核查](gather_liveness_review_current01.md)排除了当前
队列配置下同周期计数加减覆盖这一候选原因，未据此修改RTL或关闭历史停滞。
这些是症状/程序记录，不是可以直接相加的独立bug数。其余完整父程序、
内核向量CSR等待、Linux信号与重启ABI仍按CURRENT_SCOPE的边界保留。
下方记录为历史阶段的通过范围；遇到旧镜像或运行中描述，以本节和
CURRENT_SCOPE的最新明确终态为准。

2026-10-11恢复后的新增终态与首错见
[恢复记录](RESUME_20261011.md)。浮点merge的195次来源前缀已完成
[独立复核](fp_merge_original/terminal_resume20261011.md)；整寄存器1134项
分组已完成[严格验收](whole_register_original/strict_acceptance01.json)。NF8的
192个来源场景也完成[完整CSV独立复核](masked_translation/nf8_strided_review/sv39_full192/terminal_resume20261011.md)。
Gather ops20连续前缀在VL256/vstart128处出现新的已实测数值错误，周期探针
已确认索引源起点错位；最小RTL修复在candidate05聚焦反例、完整514检查和
波形均已通过，零起点控制完整CSV不变，见
[聚焦验收](gather_original_review/gather_repair05/m5_successor01/focused01/acceptance.json)。
原两项98调用前缀现已完成独立完整CSV复核，共196调用、100352数值和392保护元素检查；原第66调用及后续调用通过。48项回归全部通过，16项完整控制共310350行CSV与M4一致。此前83个单例、新聚焦与本次原始前缀分别保留证据，不互相替代。未知11项历史停滞、完整parent和Linux原ELF仍未关闭。下文保留原有范围记录，
新的未闭环项不能视为已修复。

以下原始来源程序已补充完成candidate04验收，和仍在运行的任务分开记录：

| 测试 | 已通过的范围 | 尚不能据此关闭的范围 |
| --- | --- | --- |
| 算术重启连续前缀 | 五个配置共262次原始调用；完整检查124928个结果元素和524个保护元素，见[独立复核](arithmetic_restart_original/TERMINAL_AUDIT01.md) | 这些前缀执行的是vadd，不代表完整22组矩阵、其他算术指令或全部历史停滞记录 |
| 浮点比较连续前缀 | e16/m2带掩码及不带掩码各130次调用，数据和异常标志通过，见[独立复核](fp_comparison_original/TERMINAL08.md) | 682次调用的别名前缀尚未在DUT执行；不是全部浮点比较父矩阵验收 |
| 定点乘法重启边界 | vsmul原调用776单独执行，以及775后接776，共两个程序、三次目标调用通过，见[终态验收](fixed_restart_original/TERMINAL_PARENT01.md) | 未保留此前全部777次调用历史，不能由相邻两次通过推断整个长程序通过 |

整寄存器1134个配置的20个分组已有仿真PASS，独立终审已完成。
分组会丢失部分跨组的前后操作关系，因此另外准备59组相邻操作补测；
这些补测现已全部通过[原始CSV独立终审](whole_register_history_edges/terminal_resume20261011.md)，
精确59对、118次调用，不等同于保留全部1134次调用历史的连续程序。

- NF7 indexed：candidate02的完整96个来源场景已通过，24份完整CSV独立
  复算一致，284816次检查、168个检查点；见
  [独立验收](masked_translation/indexed_review/sv39/terminal_audit01/REPORT.md)。
  这是冻结candidate02的结果，不代表candidate04或原Linux ELF已验收。
- 源/目的重叠比较：19个原始失败单例均已移植并通过Spike；candidate03
  的e8/m2用例已复现活动位84错误，candidate04修复后相同ELF已PASS。
  全19个来源单例和16项代表性控制已经完成candidate04独立验收；
  完整4032-case父矩阵与原Linux ELF不在本次范围，见
  [来源选择](comparison_alias_original/SELECTION.md)。
- 其余gather、算术/merge停滞以及部分比较数据症状：须恢复原始触发序列，
  现有相邻操作通过不能关闭这些记录。
- Linux信号帧、sigreturn、原权限变化和内核向量CSR等待：真实Sv39测试
  提供访存/异常/重启的RTL证据；原Linux ELF仍须在对应系统环境复测。

已存在于起点RTL中的修正（例如比较旧vd的MaskB字零起点）必须通过原
来源程序核查，但不计为本轮新修改。历史TIMEOUT/CANCELLED与复现未得到
错误的记录均保留，不以新的通过结果覆盖旧日志。
