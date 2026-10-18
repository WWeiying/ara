# 下一轮面积精简实施记录

目标：逐项实现面积精简，兼顾时序与基本不变的性能；完成候选功能与吞吐验证后，再集中进行综合比较。2026-10-13 开始。本轮不新启动中间综合，之前运行的冻结快照任务不修改。

审查依据见 [架构审查](reduction_area_architecture_audit.md)。需要完成的工作包括转发与状态组织、精确累加更新、共享有序后端的容量评估与可行实现、中央 seed/旧路径特化、统一回归和最终综合。某项若无收益或损害性能，应保留排除依据，不把单个安全改动当作整体任务完成。

## 1. 转发 payload 共享捕获：已实现，整机验证通过

`operand_requester.sv` 新增独立开关 `ARA_RED_SHARED_FORWARD_CAPTURE`，Makefile 参数 `reduction_shared_forward_capture=1`，默认关闭并依赖 chain bypass。原来 9 个消费者分别保存 64-bit 数据，现在保存五个来源的数据和每消费者 3-bit 来源编号。五个来源是两项规约缓存、近期 SLDU、近期 MFPU、当前 SLDU。所有来源可同拍捕获，所有消费者可同拍读取；没有改动匹配、优先级、版本、字节覆盖、grant 或 credit。

理论 payload/selector 存储由每 Lane 576 bit 变为 347 bit，四 Lane 共减少 916 bit；这是 RTL 位数预算，不是综合面积结论。来源编号和来源数据在同一边沿取得，因此同拍 cache 替换不会读到新生产者的数据。无效输出可以变化，`lane.sv` 仅在 forwarded valid 时使用它。数据 mux 从寄存器前移到寄存器后，新增 fanout 和输出选择路径必须在最终综合检查，不能因周期不变便声称时序无损。

仿真专用参考寄存器保留旧的每消费者 payload，`a_shared_forward_payload` 对每次有效响应逐周期比较；综合通过 `SYNTHESIS` 排除参考硬件。独立压力测试从实际 requester 文件提取原封不动的捕获代码，记录完整源码与提取块哈希，不用手写替代 DUT。

单元验证 `hardware/build/shared_forward_unit_v1` 已通过 6000 周期，五种来源分别命中 5372/5430/5416/5374/5326 次，5841 个多读者周期，24 次复位，涵盖全消费者广播、同拍五来源、每拍来源数据替换及 cache/MFPU 分类优先级。该测试验证存储/选择，不替代真实 requester 匹配与架构验证。

匹配整机验证 `hardware/build/shared_forward_soc_v1` 已完成，两组均启用已通过的共享归一化、短反馈 scalar/AFTER，候选只多共享转发捕获开关。两侧 22/22 项通过，15 个周期窗口全部相同；重新核对完整冻结 ELF 集合、模拟器哈希、日志失败标记及结束时刻后生成 `comparison.json`。后续组合扩展仍补充真实缓存命中与依赖覆盖，不能单靠现有 22 项证明全部转发场景。

复现：

```sh
python3 hardware/scripts/run_shared_forward_unit.py --out hardware/build/shared_forward_unit_new
python3 hardware/scripts/run_exact_area_soc.py --out hardware/build/shared_forward_soc_new --mechanism none --normalize-both --forward-capture --jobs 2 --timeout 3600
```

## 2. 发射描述直接读取：已实现，独立整机验证中

新增 `ARA_RED_SHARED_ISSUE_DESCRIPTOR` / `reduction_shared_issue_descriptor=1`，作用于 VALU 和 VMFPU。原来的 `vinsn_issue_q` 在时钟边沿取得 `vinsn_queue_d.vinsn[issue_pnt_d]`，同时队列及指针取得同一份 d 状态；因此复位后它与 `vinsn_queue_q.vinsn[issue_pnt_q]` 始终相同。候选直接读取队列槽位，不改变描述的 owner、队列深度、issue/processing/commit 指针或指令寿命。仿真中保留原寄存器副本，逐周期比较整个结构。

目标是移除每 Lane 两份重复的发射描述寄存器。实际综合会裁剪部分未使用字段，因此不能按完整结构位数直接计算面积。代价是发射控制前经过队列选择器；该候选仍默认关闭，最终必须检查译码和 operand 选择关键路径，不以功能等价代替时序结论。

独立匹配整机回归 `shared_issue_soc_v1` 已完成两组构建并开始执行，driver PID 2015253；两组保留相同短反馈/归一化，候选只开启描述共享。不能用已有转发回归代替此项验证。

## 3. 精确累加的同段碰撞转发：已实现，单元验证通过

新增参数 `CollisionForwardUpdate`、宏 `ARA_RED_EXACT_COLLISION_FORWARD`、Makefile `reduction_exact_collision_forward=1`，默认关闭。替换有限值的分段更新：每个元素读取本拍开始的 bin，通过段号比较从前面最后一个同段有效元素接收更新值，最后按段号统一写回。这样不必每处理一个元素就形成一份完整的新 bin 数组供下一次动态读取。保留四个元素更新位置，不新增流水拍、不降低 FP16 四项/FP32 两项的拍吞吐。

首拍先完成原来的初始化和非延迟 seed 插入，再执行该有限值更新；特殊值、零与标志累积仍由原逻辑处理，非分段模式保持原路径。面积是否改善仍需综合；该结构意图减少选择网络串联，不把运算函数数量当作门面积证据。

`exact_collision_unit_v2` 已通过：12 种合法参数配置×8 种共享更新/归一化/碰撞转发组合与原始 RTL 逐周期比较，300 条多拍指令、14,168 周期；扩充同段正负抵消、多个段、最大有限值、子正常值、全 Mask 和稀疏激活刺激。独立 900 项数值 oracle 在碰撞转发开启时通过，最终舍入差分 56,736 项通过。v1 是早期刺激版本，oracle 未开启新碰撞转发，不能用 v1 oracle 声称验证了新路径。

## 4. 三项组合与有序资源画像：验证中

`area_combined_soc_v2` 对三个候选同时开启与全关闭做匹配比较，两侧均保留上一轮短反馈/归一化，29 个程序包含原 22 项及 7 项有序/FP64/混合序列。driver PID 2025541。新增只读 `ordered_area_profile.sv` 记录每 Lane 的 ordered 请求、接收和返回，用于判断共享一套/两套短反馈资源所需的并发容量；记录全程序而非仅性能窗口，不能直接据此预测新架构的加速比。

组合 v1 在构建阶段失败，原因是 VCS bind 中不能用该位置的类型名 `$bits(vfu_operation_t)`。改为实际信号 `$bits(vinsn_issue_q)` 后建立独立 v2，保留失败目录；没有修改 RTL 算法或跳过断言。画像收集入口 `collect_ordered_area_profile.py` 要求测试通过及四 Lane 完整摘要，核对逐请求记录与汇总计数一致。

## 5. 有序短反馈共享：已实现，一套/两套压力测试通过

已完成资源画像 `ordered_share_demand_v1/profile.json`：7 个程序通过，其中 6 个确有 ordered 请求，分别记录 256、192、32、16、128、3 次请求；这组 trace 的每拍请求峰值均为 1，没有观察到同拍多个 owner。`perf_rce_fp64_mixed` 没有 ordered 请求，不能用于支撑此结论。画像只是实施共享候选的依据，不证明任意程序没有争用。

新增 `shared_ordered_adder.sv`，`ARA_RED_SHARED_ORDERED_ADD` 开启，`ARA_RED_SHARED_ORDERED_UNITS=1/2` 选择一套或两套；Makefile 对应 `reduction_shared_ordered_add` 和 `reduction_shared_ordered_units`，要求已有 scalar/AFTER/ordered_fast 开关。Lane 仍负责有序元素顺序、seed、Mask、token 和最终提交；中央只提供共享标量 ADD 服务，不改变运算顺序。使用与现有短反馈相同的多格式 fpnew、固定 ADD、单个 AFTER 寄存器、关闭 SIMD/NaN boxing；在原 9-bit tag 外附加 Lane owner，结果返回原 Lane。新接口经过 VMFPU、vector_fus_stage、lane 和 Ara，默认关闭时不实例化共享硬件。

每组使用轮转仲裁和请求锁定；不同组互不争用。新资源减少的是物理加法器数量，不增加 FP64 收尾与 ordered 的争用：暂未把 RCE 已有 FP64 加法器也并入该单元。增加输入选择和跨 Lane 连线，可能影响 Fmax，因此只能在最终 PPA 后决定一套/两套或不共享的选择。

发现并修复了一个真实协议问题：初版允许 fpnew 的多个格式切片同时在途，随机并发/背压测试触发输出不稳定与同 Lane 返回次序错误。修正版给每组增加 busy 所有权，只允许一个尚未接收的结果；上一结果被接收时可同拍接收下一请求，不增加固定流水拍。保留请求/输出在背压下稳定、owner 属于对应组的断言。

独立测试 `shared_ordered_unit_v3` 已通过：一套、两套配置分别运行 6000 周期，复位后独立参考逐项比较 1423/2739 个结果，多请求源周期分别为 5480/5247，包含 FP16/32/64、五种标准舍入模式、NaN/Inf/正负零/子正常值、随机数、长背压与在途复位。每个 Lane 使用独立的原 scalar fpnew 作算术参考，参考 FIFO 检查数据、状态、tag 和次序；不是用新共享模块自己验证自己。测试 v1 是不适用于独立 top 的 SoC testbench XMR 构建失败；v2 保留上述真实协议失败；v3 为修复后版本。

`shared_ordered_soc_v1` 及 `shared_ordered_quick_v1` 使用修复前的冻结模块，即使某些程序通过也不能作为最终修正版验收。新的修正版已纳入下面的全组合回归，不能混用两种快照的结论。

## 6. 旧整数后台上下文特化：已实现，验证中

新增 `ARA_RED_PRUNE_LEGACY_INT_STREAM` / `reduction_prune_legacy_int_stream`。`uses_rce()` 覆盖所有 global VL 非零的整数规约，而 dispatcher 将普通 VL=0 指令作为 NOP 处理。候选在 `RceIntEnable` 时关闭仅供旧 SLDU 树空闲周期使用的后台规约调度，令其后台 accumulator、结果、三项 local-root 数据与进度寄存器为常量。仍保留原有控制门禁与 legacy 回退状态机，不通过删除整个 context-stream 宏意外改变 RCE 混合执行。

`a_pruned_integer_stream_is_unused` 检查关闭后的组合 next-state 没有实际需要后台上下文；正常功能回归继续检查整数、全 Mask、空 Lane、VL=0、宽化及混合运算。该候选未证明面积变化，需最终检查综合是否确实删去状态与选择逻辑。

## 7. 中央 seed 表合并：本轮不优先实施

SLDU 精确 seed/result 表为 8 项，每项约 32-bit 数据、5-bit vd、8-bit 版本、4-bit 字节有效和 valid，共约 400 bit；消费者的独立快照不能随表合并删除。RCE 通用表支持 64-bit 数据和不同发布/生命周期控制。共享可以消除部分重复数据/匹配，但同时需要保留两侧查询并发、多个写源以及消费者快照，可能引入更大的多端口 mux 和关键路径。与四套有序加法器共享相比，这是较小且收益不确定的方向，当前保留两套表；不能把约 400 bit 预算说成已经节省的面积。

## 8. 五项组合与下一步

`area_shared_all_soc_v1` 于本轮启动，driver PID 2038273。启用共享转发、共享发射描述、碰撞转发、修复后的单套共享有序 ADD 和旧整数后台特化，保留已验证的短反馈/归一化，29 项匹配整机回归。其输入全部冻结，不能修改正在运行快照。

另以同一组冻结 executable 完成 7 项有序/FP64 快速对照 `shared_ordered_quick_v2`，两侧均通过，6 个窗口分别为 549/124/123/137/292/974，两侧完全相同。它不能替代完整 29 项，也不能称为只开启共享有序单项的消融。

比较脚本已加完整性检查：两侧 test 集合必须等于各自预先冻结的全部 ELF，若有 configuration 则也必须匹配；核对模拟器/ELF 哈希、实际日志成功/失败标记。此前 quick_v2 的一次 6 项部分比较已归档为 `comparison.partial_untrusted.json`，不作验收；最终 7 项报告重新通过完整检查。用尚未完成的 full 29 项目录测试新检查，正确拒绝了部分结果。

两套共享单元的整机组合 `area_shared_two_soc_v1` 已启动，driver PID 2049379，通过源码哈希、编译选项与 filelist 校验后复用同一 baseline，只构建/执行两套单元的候选，防止重复消耗完整基线仿真资源。

24 项额外依赖、队列、普通算术和异常测试位于 `area_shared_extended_v1`，baseline/scalar driver 为 2046488/2046489。已复现历史 VNCLIPU 错误：`reduction_rce_queue_recycle` 两侧均输出 got=8、expected=ffffffff。核对其 ELF SHA256 与历史 `throughput_control_known_failure_v4` 完全相同，失败签名也相同；见 `inherited_failure_audit.json`。它是已知非规约饱和窄化数据错误，本轮不修改该指令或测试期望，不把失败计为通过。其余扩展项继续验证，不能声称该 24 项全部通过。

新增综合候选 `full_area_local`、`full_area_shared1`、`full_area_shared2`，均保持原队列深度和外围配置。`area_shared1_stage_v1` 与 `area_compact_control_stage_v1` 仅 PREPARED，未调用 DC。单套候选的所有规约宏与实际仿真完全相同；初步源码核对 362 个同名 SV 文件一致，三项差异为 SLDU 注释、已验证的 FPU boxing 固定循环边界改写、find_first_one 的注释与断言综合排除写法。详细记录在 prepared 目录 `simulation_source_audit.json`；后续更改源码则必须重新冻结，不得用旧快照冒充最终实现。

仍需完成单项与组合测试收集、修正版有序回归及周期比较、长背压/真实相关和非规约覆盖、参数开关检查、严格匹配基线与最终综合。根据结果淘汰无收益或时序退化候选，再确认最终配置。本轮尚未启动新的综合。

## 9. 后续检查清单

最终候选于 2026-10-13 10:22 UTC 进入 COMPILE。DC 实际 elaboration 实例报告 `ordered_backend_inventory.rpt` 为 shared_units=1、lane_local_units=0，均与预期一致，确认没有同时保留四套 Lane 内短反馈副本。源码沿 OSUM 路径检查：有效源/seed/token/Mask 和指令计数决定 `vfpu_in_valid`，自身 `vfpu_in_ready` 用于接受后的计数与操作数确认；这一局部检查不足以证明跨 SLDU、结果队列与多格式 FPU 的完整环路不可达，仍保留映射后环路审查要求。

最终候选映射前 `check_timing_pre.rpt` 报 TIM-209 环路，第一条所列路径涉及 shared_ordered_adder 与 VMFPU；旧 `full_compact_prepare_v1` 也有 VMFPU/本地 ordered fast 环路。完整环路段和报告哈希存入 `area_final_shared1_v1/pre_mapping_loop_audit.json`，状态 UNRESOLVED。不能因旧版也存在就认定新路径安全，不能使用自动断环后的 slack 宣称闭合；待映射后检查是否被常量/状态优化消除，仍在则需追踪握手依赖。未添加 false path、未屏蔽告警、未中止或重启当前综合。

双套共享备选完整验证也已结束：`area_shared_two_soc_v1` 两侧 29/29 PASS，严格比较器再次通过，21 个窗口及全部 finish 时间完全一致，与单套在这组 workload 上没有周期差异。暂保留单套作为面积优先候选，双套作整机时序/并发能力备选，不据此断言任意 workload 均无争用。

`area_final_shared1_v1` 已进入 ELABORATE，DC PID 2087399 仍活跃，检查时未发现 Error/Fatal。串行队列 `continue_serial.py` 已启动（PID 2090832，`area_final_serial_v1`）：核对前驱 driver PID 2087326 的进程启动标识，等待实际 COMPLETE，再用 flow report 校验完成产物，最后启动 `area_final_control_v1`。前驱失败/driver 消失、flow 驱动变化或后继不再 PREPARED 则停止，不自动重试，不把等待超时当任务结束。当前队列为 WAITING_FOR_PREDECESSOR，控制组尚未启动。

最终综合阶段已开始：2026-10-13 09:57 UTC，`area_final_shared1_v1` 通过冻结检查后启动，driver PID 2087326、容器 DC PID 2087399，status=RUNNING。该配置已完成 29/29 匹配回归和 21 个不退化窗口。compact 控制组仍 PREPARED，计划串行，未同时启动多项最终整机映射；双套备选长尾仍在运行。

为释放内存，明确取消已过时的 `full_retry2`：其映射早已完成且 checkpoint 存在，生成 reg2reg 报告持续占用约 68 GiB；核对 PID 1008846 的 cwd/命令后 SIGTERM，保留全部报告、映射 checkpoint 及其哈希到 `cancellation_audit.json`。进程退出后可用内存由约 39 GiB 恢复约 105 GiB，再启动最终候选。这是主动取消旧方案的报告阶段，不是证明 DC 自行失败/成功，不作自动重跑理由；另外两项历史映射任务未停止。

完整组合验证已结束：`area_combined_soc_v2`（前三项）和 `area_shared_all_soc_v1`（全部五项、共享一套）均为两侧 29/29 PASS，重新执行严格比较器通过，21 个性能窗口逐项相同，完成时间无退化。全 29 项原配置画像 `ordered_demand_full.json` 中 11 项实际使用 ordered ADD，总计 915 请求，没有同拍多 Lane 请求；其余 18 项不能用于声称 ordered 覆盖。双套 `area_shared_two_soc_v1` 的候选长尾仍在运行，保留作为时序/争用备选。

最终 compact 控制与单套候选已重新冻结为 `area_final_control_v1` / `area_final_shared1_v1`，包含最新实例数量检查及模块路径报告。`area_final_input_audit_v1.json` 验证两侧有序排列的 390 HDL 文件内容一致、库和约束一致，仅六个宏字段不同（五项机制加共享单元数）；候选 HDL 与此前完成仿真源码核对的 stage 完全相同，并链接 29 项完整比较及旧源码审查哈希。当前均 PREPARED，未启动新 DC。机器约 42 GiB 可用，已有旧 DC 进程仍在运行，其中一项 RSS 约 68 GiB；最终启动需控制并发内存，避免多套整机映射同时增长耗尽内存。

原始基线六项运行验证最终为 2 PASS、4 FAIL：short/e64 stream 通过；empty 的 canonical NaN/NV 不配对；seed 与 ordered FP16 出现未知操作数/未知缓存读数据断言；ordered rounding 报 FP16 case0 flags=0/1。两项已明确断言失败的仿真主动 SIGTERM，driver 将其记录失败（returncode=255），并继续剩余测试，停止原因与日志哈希记录在 `regression/assertion_failure_termination.json`。未关闭断言或重写预期。未知值的具体原始根因尚未定位，不将其归因于本轮共享优化。该原始源码对照目前不是与当前修复版本功能等价的公平性能基线；可作为明确标注缺陷的历史面积参照，本轮精简应优先比较当前 compact 对照。

综合模板增加 elaboration 后 ordered backend 实例数量检查：根据 profile 验证共享 ADD 为 0/1/2 套、Lane-local 快速 ADD 为 0/4 套，输出 `ordered_backend_inventory.rpt`，数量不符即失败。与路径报告一样仅影响以后新 prepare 的冻结输入；已有运行目录不修改。脚本单测 14 项仍通过，实际 DC 执行验证留到最后综合阶段。

原始基线运行验证已出现真实差异：`original_area_soc_v4` 的 short/e64 stream 通过，`reduction_audit_empty` 失败（全 Mask、sNaN seed，result=7fc00000、flags=0）。测试允许保留 sNaN 且 flags=0，或 canonical NaN 且 NV=16，原版输出不满足这两种预期；同一用例在当前精简前后均通过。不改原版测试期望、不把失败计为通过，也不将该场景纳入正确性等价的性能比较。其它原始基线用例仍在运行，不能声称原版已通过全部验证。

最终综合模板新增模块边界路径报告：shared_ordered、completion、requester、VALU、VMFPU、finalizer 六类，各记录实际实例数并提取穿过边界的最多 10 条 max path，缺失模块只记 absent（实例数 0）。用来补充整机最差路径，检查共享连线和描述直读 mux 的代价；不是新的时序约束。14 项流程测试（含 Tcl 语法完整性）通过，但未在 DC 中执行新报告命令。现有冻结任务不改，最终 prepare 时才采用新模板。

共享发射描述单项 `shared_issue_soc_v1` 已完整结束：baseline/scalar 各 22/22 PASS，完整性/冻结输入检查通过，15 个性能窗口逐项相同，全部完成时间不退化。该结果包含之前等待的长尾规约边界用例；仍不能单凭仿真确定队列直读 mux 的实际时序代价。

`original_area_soc_v4` VCS 编译成功（returncode=0，simv 生成），其六项原始基线运行验证已启动，driver PID 2077220，覆盖 short/e64 stream、empty、seed、ordered FP16 和 ordered rounding。`original_30c6971b_stage_v3/baseline_source_audit.json` 重新核对全部 38 个源码及头文件，只有 dispatcher 和接口 typedef 两项共同 CSR overlay；库/时钟等约束与候选一致。功能验证仍在进行，不把编译成功当测试通过，也不声称原版没有已知语义缺陷。

原始对照编译进一步发现 CSR 接口配套缺失：v3 报 `accelerator_resp_t` 没有 `fp_csr_busy`。补入 `hardware/include/ara/intf_typedef.svh` 的同名 1-bit 字段，与当前接口一致；prepare 同时记录其原始/修改后哈希。新的 `original_30c6971b_stage_v3` 已静态检查通过，仿真 `original_area_soc_v4` 正在编译（driver PID 2074880）。因此原始对照的共同 CSR overlay 涉及 dispatcher 和接口头文件两处；此前只统计 `.sv` 的 35 文件核对不能代表所有头文件也未改。stage_v1/v2 和 sim_v1/v2/v3 均保留但不用于最终验收。

既有 `finalize_ppa_v1` 已完成两侧局部综合，非本轮新启动：SharedExtract=0/1 面积为 20197.799959/18081.839979（−10.476%），最差已报告 setup slack 为 −0.216446/−0.254051 ns（恶化 37.605 ps）。RTL 哈希与当前 finalizer 一致，报告哈希和取舍记录为 `area_timing_decision.json`。两侧均未时序收敛，这只是局部组合块结果，不能当作整机降幅或频率；暂不加入默认组合，保留开关，待整机路径确认收益是否值得时序代价。

新增 `build_original_area_sim.py`，从 prepared 原始 RTL 快照构建同外围 VCS 仿真，并保留源码/头文件哈希。`original_area_soc_v1` 因头文件层级未保留而失败；v2 修复目录后发现 reference 中的两个只读 RCE 画像 bind 引用了原版不存在的模块。v3 去除这两个不适用于原版的观察器，保留架构 testbench 和 RTL 断言，正在编译，driver PID 2072589。以上失败目录保留；没有修改 RTL 算法或测试预期。

优化前源码对照已增加独立 profile `original_30c6971b`，其规约宏集合为空，prepare 从 Git 固定提交 `30c6971bff8400024ba8dd671c2fc02e451bd39a` 提取 RTL 和 Bender 清单。`original_30c6971b_stage_v2` 已静态检查通过：385 HDL、11 个库；与 `area_shared1_stage_v1` 的库哈希、时钟/不确定度/核数/工具路径/整机范围相同。35 个原始 Ara SV 文件仅 dispatcher 有明确记录的修改：补入与当前 RTL 相同的 `fp_csr_busy`，配合双方共用的 scalar CSR interlock 依赖修复。其余原始 Ara SV 与 Git 逐文件核对一致；共同原始路径下 386 个文件哈希相同。`baseline_source_audit.json` 与 `original_overlay.json` 保存证据。

这不是未经修改的原始仓库，而是“固定优化前 RTL + 当前共用依赖/CSR 修复”；尚未 HDL 编译或功能验证，尚未启动 DC，不能先报公平面积结果。第一次 prepare 的 `original_30c6971b_stage_v1` 缺少 dispatcher 的 CSR busy 配套信号，保留作准备过程记录，不用于验收。综合流程单测现为 14 项通过，覆盖原始 profile 宏集合及重复/未知 CSR overlay 的拒绝。当前源码 compact 对照仍用于隔离本轮五项精简收益，两种基线不可混称。

扩展回归已完成：`area_shared_extended_v1` 两侧各 24 项，22 PASS、2 FAIL（上述 VNCLIPU 与 vstart 历史错误）。新增 `audit_area_extended_results.py` 验证完整输入集合、冻结 ELF/模拟器哈希、重新分类实际日志，并将失败与显式传入的历史 manifest 对照；输出 `extended_audit.json` 的 `all_pass=false`、`no_new_failures=true`，通过项目均无周期退化。历史失败没有被改成 PASS；该报告仅表示本轮候选没有新增已测错误，不表示全架构正确性证明。主回归的长尾边界仿真进程仍在运行，不能以这组扩展结果替代尚未完成的主回归。

补充审查：扩展回归两侧均复现 `reduction_rce_vstart_trap` 的四项 `vstart=VL` 未触发异常错误；与 `architecture_vstart_full_v2` 的 ELF 哈希及完整失败签名一致，证据保存在 `area_shared_extended_v1/inherited_vstart_failure_audit.json`。仍计为失败，不作为本轮新引入错误，也不宣称全部架构测试通过。

资源画像收集入口新增冻结输入集合完整性、重复项目、预期集合和 ELF 哈希检查；既有 7 项画像重新检查通过，未完成的 29 项目录正确被拒绝。Makefile 对共享有序单元数增加入口检查，0、3 和多值输入均立即拒绝，避免错误配置进入构建。单套、双套及 compact 对照综合输入均已 PREPARED；截至本次检查仍未启动新的 DC。

- 描述信息共享：先提取字段的最后使用时刻和并发访问需求，再选择 Lane 内的存储合并，避免一个高端口中央表。
- 精确累加更新：比较显式段号解码、同拍碰撞合并与当前动态索引；保持每拍输入容量与精确数值。
- 有序后端共享：修正版模块已通过单元，继续验证整机服务率及一套/两套配置的性能/时序取舍。
- 中央 seed 表和旧路径：seed 合并暂不采用；旧整数后台特化需完成整机回归，确认网表已裁剪部分不重复计收益。
- 所有候选：独立开关、数值与所有权回归、性能消融后，再冻结统一输入并启动最终综合。严格匹配基线仍需建立，历史面积差额只作优先级依据。
