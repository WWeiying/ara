# 普通屏蔽访存：修复约束与验收

## 已证明的问题与边界

`measurement04` 证明：当前 AddrGen 对 VL8/e16、全屏蔽的普通 load 仍发出
翻译，并传播返回的页故障。三项对照使用真实 AddrGen 与延迟 MMU 模型。
这不是完整 Sv39/页表/异常返回验收，也不代表429条历史访存记录同因。

当前 indexed 路径会检查 `owner`、`first_element`、valid 和当前元素位，
对屏蔽元素发送 `is_skip` 描述符；普通 unit-stride/strided 路径绕过了它。
VLDU 的写使能和 VSTU 的 WSTRB 在此之后生效，无法撤销已经发生的异常。

## 修复候选的责任划分

以下约束已用于当前 AddrGen 候选实现；候选尚未完成测试验收，不能视为
问题已关闭。独立审查见 `REPAIR_REVIEW_20261010.md`。此前 final04
冻结镜像不包含此候选，不能用其通过结果证明本修改正确。

1. AddrGen 对所有 masked 请求按当前绝对元素编号查询所属掩码窗口，必须
   同时匹配 vid、窗口范围和对应 lane valid；缺少掩码不能当作全开或全关。
2. 屏蔽元素不请求 MMU、AR 或 AW，但必须有内部进度。复用 skip 描述符
   推进消费者字节数、掩码和源数据，禁止直接把整个指令 done 拉高。
3. 普通 unit-stride 若采用逐元素路径，地址增量必须是 `1 << SEW`；
   strided 保留原始有符号位模式的 stride 加法，包括零和负步长。
   indexed 保留原索引元素及 spill-register 握手，不能误消费索引。
4. 跳过最后一个元素也必须完成 AddrGen。不能依赖不存在的最后 MMU
   响应；无翻译时也要确保前后两个状态机恰好完成一次。
5. 非活动元素不能因初始 base 的对齐检查报异常。对齐检查需要针对实际
   将访问的活动地址；保留精确 cause/tval/vstart 与 FOF 的非首元素处理。
6. 中途异常必须排在此前数据/skip 描述符之后，不能用提前的非法指令
   通知使 VSTU/VLDU 抢先丢弃仍待消费的前缀。若新增有序异常标记，就不能
   再把同一故障当作“没有描述符的早期异常”重复发送。
7. 地址生成 ack 与指令退休不同。VLDU 仍需等待有效结果真正写回；VSTU
   仍需等待已发出写事务的 B response，纯 skip 不得增加 pending_b。
8. 保留原 `vm=1` burst 数据通路、队列容量和事务推进。不涉及 masked
   translation 的 indexed、QBS/AKV 独占路径也必须独立回归。

## 不应掩盖的性能代价

将 masked 普通访存分解为逐元素访问是易于验证的正确性方案，但全一掩码
会增加 AR/AW 和翻译请求，不能称作性能不变。若采用它，必须报告这种代价，
不能只选择 vm=1 的对照证明没有退化。

安全的后续合并只能覆盖已经知道 predicate 的窗口：在有效掩码、地址对齐、
剩余 VL、页边界和消费者粒度均允许时，合并连续 active 或 inactive 区间。
不能为了保留大 burst，在尚未确认后续掩码时访问另一保护页；也不能用
“最后写使能为零”代替访问前的异常资格判断。

## 最小测试矩阵

| 维度 | 必需场景 | 检查 |
| --- | --- | --- |
| 原始语义 | e16/VL8 全关 + 保护页 | 无目标异常、无访问、旧目标/尾部/guard 全保留 |
| 正对照 | 同地址 bit0 激活 | 精确页故障；修 PTE 后从 vstart 正确重启 |
| 有效页 | 全关、全开、稀疏 | skip/真实请求数量、完整数据和正常完成 |
| 窗口 | 多个掩码字、延迟 valid、错误 owner | 不错用前后指令掩码；窗口外等待 |
| 重启 | 字内/字边界 vstart | 前缀保持、正确元素地址、最后 skip 能结束 |
| 对齐 | 全关未对齐、活动未对齐 | 仅活动访问报错，精确 cause/tval/vstart |
| 寻址 | unit、正/负/零 stride | 活动地址与标量参考一致，跳过也推进逻辑元素 |
| Stores | 全关、稀疏、延迟 B | 无伪 AW/W/B，已有写事务排空后才退休 |
| FOF | 首元素/非首元素故障、全关 | 正确 trap 或 VL 缩短，内部消费者不遗留 |
| 队列 | 描述符反压、结果反压、连续 load/store | 不重复请求、不丢 token、不提前结束 |
| 控制 | unmasked burst、indexed skip | 数据、事务和周期对照保持既有行为 |

局部测试必须实例化真实消费者才能宣称消费者已验收；模拟 sink 的结果只能
证明 AddrGen 局部协议。Sv39 测试使用真实 S-mode、页表和精确 trap ledger，
不拿 Linux ELF 直接当裸机加载，也不以 MPRV-only 替代 S-mode 路径。
原始 Linux 信号与重启验收仍保留为独立层级。

## 当前候选与验证顺序

候选仅修改 `hardware/src/vlsu/addrgen.sv`。masked 普通请求使用元素级
访问与 skip 描述符；skip 的总线地址固定为零，以保证消费者按完整元素
宽度推进，而不是按可能未对齐的被屏蔽虚拟地址截短。只有活动地址才能
触发对齐异常或 MMU 请求。中途对齐错误使用有序异常描述符，禁止再发送
early-illegal 通知。无翻译及最后元素被屏蔽的情况也等待地址生成完成。

真实 S-mode Sv39 的三项独立参考已在 `sv39_reference02` 通过：全屏蔽
保护页、活动元素页故障修 PTE 后原 PC 重试、有效页对照。最初参考检查器
错误地要求全屏蔽 load 必须产生目的寄存器写记录，已在保留旧失败记录的
前提下修正；不能将该检查器问题归为 RTL 错误。完整旧目标、尾部与 guard
检查仍保留，并有故意破坏结果的负对照。

下一步先做候选局部协议测试和消费者审查，再用新冻结镜像执行同一 Sv39
程序及实际 load/store 控制测试。测得性能之前，不宣称 masked 访问性能
无损。后续连续元素合并不得越过未知掩码窗口或引入被屏蔽地址的异常。

候选已独立冻结到
`/home/wangwy/fpga_runs/current_board_masked_candidate01/frozen`，共539个
输入文件。两版 snapshot 的完整源文件哈希对比显示，相对 final04 只有
`hardware/src/vlsu/addrgen.sv` 改变。构建服务为
`ara-board-masked-candidate-build02.service`；首次服务因误用 `build`
而非 `build-image` 子命令立即退出，保留 `build.log`，未执行编译或仿真，
不能计作 RTL 失败。第二次构建日志为 `build02.log`，已成功构建，耗时
113.85秒；`image/image.json` 绑定全部镜像文件与快照。构建通过不等同于
候选程序验收通过。

未含候选的 final04 镜像上，真实 Sv39 三项基线已结束：全屏蔽保护页
FAIL（313.98秒），活动故障修页表重试 PASS（309.49秒），全屏蔽有效页
PASS（305.67秒）。证据位于 `sv39_final04_baseline01`。有效页 PASS 只
表明架构结果符合检查，不能据此认定没有物理读事务；全屏蔽保护页的精确
异常位置需结合 commit trace 复核。将用相同 ELF 验收候选。

独立消费者审查在 `CONSUMER_REVIEW.md` 另记 VLDU 异常路径的风险：
部分结果未按正常队列计数入队、异常完成缺少最终写回握手约束、剩余字节
未清理。它们尚待延迟 final-grant 定向复现，不能仅凭静态推断宣称原始
Linux 必然卡死；sequencer 的 `ara_idle_o` 与 VLDU 的 `idle_o` 不同。

## VLDU 异常收尾候选

消费者 `consumers/measurement01` 的 partial-exception 场景已捕获：
真实 VLDU 经与 operand requester 相同的 `stream_register` 接受结果，
cycle12 首次接收，cycle15 报 done，此时仍有4字节未写入；最终 bank
grant 在cycle35。无异常对照在cycle35写回后cycle36才 done。这证明
异常路径没有维护正常路径的最终写回约束，不是仅以空闲计数推测故障。

已据此修改 `vldu.sv` 候选：部分前缀按正常 FIFO 计数和指针入队，空前缀
不制造虚假结果；异常等待整个结果队列及最终写回握手排空；正常完成逻辑
不在异常状态重复退休；异常完成后清零剩余字节与局部指针，并释放本指令
的当前掩码。最终 grant 状态复位为全一，表示尚无在途写回，后续接收清位、
最终写回置位。异常期间的请求接收门控另需公共接口时序检查。

这些仍为待 A/B 测试的候选，尚未合入或宣称验收通过。
`current_board_masked_candidate01` 仅含 AddrGen 修改，**不含此 VLDU
修改**。消费者首元素故障测试的 BE=0 空结果地址检查也在独立复核，不能
把该检查器拒绝自动视为非零字节的架构写错误。

`consumers/candidate03` 中六个收尾场景已完成：partial/FOF 的最终写回
仍为cycle35，done延后到cycle37；无异常对照仍为write35/done36；各项
flush后的空闲与后继load检查通过。但独立到达顺序测试
`arrival_candidate04` 发现本候选的 ready 门控引入了回归：异常描述符
或早期异常先到/同拍到达时，故障指令本身不能入队，四项均accept=0。
相同测试的原版可以accept=1，因此不能将candidate03的通过扩大为整体
候选通过。

已据此将异常输入的接收门控限制在 `vinsn_issue_valid` 时生效，允许
故障owner首次入队，再阻止后续请求。待用相同六项收尾与四项到达顺序
测试验收新候选；旧失败日志、冻结代码和检查器均保留，不覆盖原结果。

上述新候选已用相同测试台完成：`consumers/successor06` 六项异常收尾、
`consumers/arrival_successor07` 四项到达顺序全部通过；归档对比为
`consumers/ab_summary07.json`。无异常对照仍为 write35/done36，部分
前缀异常为 write35/done37；四项到达顺序均仅接收一次、完成一次并恢复
空闲。这是公共端口的真实 VLDU 测试，不是整机或 Sv39 验收。

独立审查另发现跨指令协议风险：AddrGen 的异常 ack 可以早于 VLDU 的
前缀排空，后续请求可能被 AddrGen 接受但被正在异常收尾的 VLDU 拒绝；
或者后续请求过早入队，使异常入口的 commit_cnt==1 永远不成立。
详见 `VLDU_CANDIDATE_REVIEW.md`。正在用真实 sequencer 公共端口
复现响应时序，并审查仅对异常 load/FOF 等待对应 load-done 的方案；
不将局部十项通过视为该跨模块风险已经关闭。

### 异常响应等待的实测与组合回归

真实 sequencer 的公共端口复现 `consumers/sequencer_before10` 证明：
异常/FOF 在ack9即返回，但匹配VID的load-done直到21才出现。
按指令ID锁存load-done，且仅对内部exception.valid为真的load等待后，
`consumers/sequencer_final12` 同一7项测试通过：异常响应延至21；另一个
VID在16完成不会放行目标VID，目标在25完成时才返回。提前done、同拍
done、普通load、无故障FOF的响应周期均不变，异常元数据保持正确。
最终sequencer SHA为 `bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655`。
局部A/B见 `consumers/sequencer_ab12.json`。

VSTU未做新的RTL修改。真实VSTU公共端口6项场景及6个后继store通过，
验证skip无W/B、异常前写事务等待B返回、首次B错误归属和无flush后继状态。
详见 `store_consumers/REPORT.md`。该测试的AddrGen和AXI对端为模型。

AddrGen、VLDU和sequencer组合候选已封存在
`/home/wangwy/fpga_runs/current_board_memory_candidate02/frozen`；
后台服务为 `ara-board-memory-candidate02.service`。计划为构建后执行
同一3项Sv39 ELF，再执行10项普通RVV/QBS/AKV代表性回归；失败即停止。
状态文件为该目录上一级的 `campaign/status.json`。尚未完成的阶段不计通过。
预检曾因引用前一版sequencer局部测试而拒绝执行，保留 `preflight`；
使用最终SHA对应的final12后 `preflight02` 通过，未放宽输入身份检查。

该组合流水线现已结束：build-image、sv39、smokes均PASS，3项Sv39及10项
smoke的全部summary条目均PASS/returncode0，服务已退出。Sv39控制台三项
均出现 `MT_SV39_PASS`，未改变程序和原来的完整检查。该结果证明组合候选
通过这些整机场景，不代表已验证全部历史Linux程序或8项新增扩展。

另有8项更广的Sv39源场景已在host/Spike参考通过，见
`sv39_extended/REFERENCE_REPORT.md`；它们尚未计入本组合候选的RTL验收。
