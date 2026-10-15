# Masked Load/Store 异常收尾与写前缀保留

## 状态

2026-10-12：冻结 M6 的局部联合 VCS 反例已复现；当前工作树已加入
VLDU 修复候选，七项首元素缺页长度边界已通过联合 VCS。后台 M6 SoC 仿真仍使用原冻结镜像，
不能作为本候选的通过证据。VSTU 最新候选已通过七项首元素故障长度边界、
索引提前错误与写反压组合，以及正常掩码 store 的 M6 周期对照。
M7 的 VL9 load/store 整机缺页恢复和16项正常控制均已通过；索引异常的
有效写前缀仍只有模块验收，完整原始 Linux 失败程序按各自范围保留。

## 实测根因

测试连接真实 AddrGen、VLDU、MASKU 和 sequencer，模拟合法的 MMU
缺页响应及 lane 谓词源，不强制内部寄存器。四 lane、e64、masked
零步长 load，在首个活动元素缺页。VL8 与 VL9 仅长度不同。

原始数据在 `multiword_fault_liveness01/startup_diagnostic01/`：

| 观察 | VL8 控制 | VL9 反例 |
| --- | --- | --- |
| 需要的展开谓词字 | 2 | 3 |
| VLDU 接收的谓词字 | 2 | 2 |
| load 异常响应与 done | 已产生 | 已产生 |
| 最终 MASKU 剩余元素 | 0 | 1 |
| 第100周期 global idle | 1 | 0 |

VL9 在第14周期进入 HANDLE_EXCEPTION，只弹出本地一个谓词字；第15周期
清除 load issue 状态并报告异常。第三字的 first_element=8 仍等待接收，
但 VLDU 的输入 valid 受 issue_valid 限制。MASKU 未完成导致全局 running
不能清零，而 dispatcher 又必须等 idle 才发出异常 flush，形成循环等待。

本地 spill 有两个槽，ready 不随同周期 pop 组合拉高，因此异常末周期弹出
一字无法补收第三字。这与 VRF 前缀未写完、MMU 未返回或存储器无响应不同。

最初10秒宿主限时在 VCS 进入测试前到期，保存在 `measurement01`，不是
RTL 卡死证据。同一二进制随后用独立启动诊断执行，约11秒启动后两项均运行
100周期并退出0；VL9的退出0表示成功观察到预定反例，不表示架构测试通过。

## 修复行为

在部分结果完成实际 VRF 写回后，masked load 进入 DRAIN_EXCEPTION_MASK：

1. 保留故障指令的 issue 上下文，使后续谓词能够继续进入缓冲。
2. 仅丢弃 owner 与故障指令一致的有效谓词字，不产生新的访存或结果写回。
3. 通过 first_element 加每字覆盖元素数判断末字，不能用临时无数据判断结束。
4. 消费末字后进入原 HANDLE_EXCEPTION，再释放指令队列并报告 load 完成。

MASKU 因真实握手自然完成，sequencer 随后可进入 idle，原 flush 通路得以运行。
不提前清除 MASKU 的在飞位，也不通过全局 flush 丢弃其他指令的数据。
无异常路径的条件和握手未修改；周期是否保持仍需正常控制实测。

独立静态复核确认：masked 请求向 AddrGen/MASKU 原子广播；early-illegal
本身不撤销谓词源，真正的 abort 在最终 HANDLE_EXCEPTION 之后。正常末谓词
字消费伴随对应数据 issue 完成，真实 fault index 小于 VL 的路径仍保有待排空
末字。不能在 early-illegal、MASKU done 或暂时 mask_invalid 时直接跳过排空。

## 验收边界

VSTU 的同类原始测量见 `vstu_multiword_fault_liveness01/measurement01/result.json`：
首元素 store page fault 无 AW/W，VL8 全局空闲，VL9 在 store done 后残留
MASKU commit=1。当前 VSTU 候选保留原先的前序完成、故障槽归属及 pending-B=0
门槛；达到门槛后接收并丢弃同 owner 的谓词，只在无掩码或本地末谓词字被
消费时执行原异常完成块。不增加正常路径状态，不提前确认写响应。
`vstu_multiword_fault_drain_successor01/measurement01/result.json` 中
VL1/4/5/8/9/12/16 均退出0，实际消费全部1/1/2/2/3/3/4字，完成时缓冲为空，
MASKU commit及全局running归零。这些首元素故障没有AW/W，不证明带前缀
写事务或B响应反压的行为正确。

VSTU 候选另有已实测的前缀事务错误：indexed 地址发生 early-illegal 时，
前序 AW 对应的正常描述符可能仍在队首等待 WREADY。pending_b 只计已接受的
WLAST，因而值为零不能证明写前缀已完成。谓词丢弃及异常完成都应等待正常
或 skip 描述符处理完，再确认 B 响应；不能仅延迟 done 而提前丢弃其谓词。
实测见 `vstu_indexed_prefix_early_illegal01/measurement_m601` 和
`measurement_candidate01`：旧M6及首版排空候选均接受AW=1，第9周期提前
丢弃正常描述符，第10周期done；第40周期释放WREADY后，至第100周期仍为
W=0/B=0。这是继承的前缀写入丢失，不是只有当前候选才出现的错误。
两次VCS退出0表示成功观察到反例，不是正确性PASS。

当前第二版候选在谓词丢弃和异常完成两处同时要求队首无描述符或为异常
描述符。正常及skip前缀仍由原通路完成，再等待B响应。AddrGen在一次AW
接受时同步入队其描述符，因此不能在AW已接受但描述符尚未入队的空隙误判。
修后仍须实测AW/W/B完整配对、正确前缀数据，以及B返回前不得done。
首版七项测试不能直接作为第二版候选的回归结果。

### 最新 VSTU 候选实测

`vstu_prefix_guard_acceptance02/measurement_candidate01/result.json` 的
九项测试均有退出0及唯一的期望通过标记，输入冻结校验不变。
候选 VSTU SHA256 为
`37880822b8066fa13e66619dd335cb42db84cdc5730c6f4dff9a3f2fd0af46a0`。

- 索引前缀反例：第9周期报告后续索引地址错误，合法描述符继续保留。
  第41周期接受正确数据和字节使能的 W，第52周期接受 B，最后谓词也在
  第52周期消费，第53周期 done；AW/W/B 均为1，未提前弹出描述符或完成。
- 首元素故障：VL1/4/5/8/9/12/16 全部通过，每项实际消费全部谓词字，
  spill 为空、MASKU 及全局在飞状态清零，没有 AW/W。
- 正常掩码 store：VL4/e64 产生4个逐元素 AW/W/B，而不是一个32字节
  burst；四个 W 的有效字节位置依次为 `ff/ff00/ff0000/ff000000`。
  最后 B 在第55周期、done 在第56周期。M6 与候选的完整 `cycles.csv`
  经 `cmp` 确认逐字节一致。

首轮 normal 测试错误地套用了无掩码 burst 的 AW/STRB 期望，在 M6
触发 Fatal；虽然 VCS 退出码为0，缺少通过标记，runner 正确拒绝验收。
旧错误日志在 `vstu_prefix_guard_acceptance01` 保留，修正的是测试台，
没有为通过测试改变 RTL 的正常访存模式。

该证据仍来自四模块联合测试。真实 lane 队列、页表、CSR、异常 flush
及同 PC 重启必须由后续整机测试覆盖，不能从此处推导完整 Linux 已通过。

### Skip 前缀与索引错误的组合

`vstu_skip_prefix_acceptance01/measurement_candidate01/result.json` 追加了
VL3 的独立组合：idx0 被屏蔽且地址不对齐，idx1 为合法活动写，idx2 为
活动的不对齐地址。AddrGen 对 idx0 只产生 skip；第8周期消费 skip 后
数据指针从0推进到8，不产生 B 等待，也不提前消费整字谓词。

idx1 的 AW 地址为 `0x40001008`，第41周期接受 W，STRB 为 `0x0000ff00`，
对应数据为 lane1 的 `0x2222222222222222`。idx2 报告 cause6、vstart2、
tval=`0x40001011`。第52周期 B 返回后才消费末谓词，第53周期 done；
无提前 pop/done，spill 为空、global idle 为1。

真实仿真退出0，用时10.643秒；外层 `systemd-run --wait` 的保留凭据记录
`code=exited/status=0`，用时39.444秒。输入及生产 VSTU 哈希均与上述
最新候选一致。该测试没有使用真实页表或 lane 队列，整机范围仍待验收。

## M7 整机恢复与正常回归

M7 已封存当前 VLDU/VSTU 候选，其他编译源码及配置与 M6 一致。
`mask_drain_sv39_prepare01` 的 load/store 两条新边界程序分别在真实
CVA6、Ara lane 队列及 Sv39 环境中通过，各完成914项独立期望检查。
保留结果为 `vcs_m7_load01/complete.json` 和 `vcs_m7_store01/complete.json`；
实际子进程分别退出0，用时177.290秒和182.569秒，没有超时或中止。

两程序均使用 e64/m4、VL9 的三字谓词流，在首个活动元素触发真实缺页。
陷阱读取验证 cause/tval/VL/vtype/vstart，快照旧目标及邻近寄存器，修复
页表并执行 SFENCE，随后从同一 PC 重试。再执行不同数据的 masked
load、整数 add、masked store 和较新的 scalar store，检查完整目标组、
邻居、后继结果、两页数据、页表及保护区。完整 scalar retirement CSV
还验证了914次检查的实际参数、两次陷阱和原始CSR恢复读取。

这证明真实队列和异常恢复路径在这些边界程序中可以推进，且后继访存
结果正确；没有采集内部 flush 信号，因此不单独报告 flush 的精确周期。
程序是新增边界测试，不能用于关闭原 VL8 Linux 卡死或原始信号 ABI。
带有效写前缀的 indexed misalignment 整机恢复仍须另行验证。

`memory_candidate07_controls16/prepared01/complete.json` 的16项正常
RVV/QBS/AKV控制全部通过。310350行完整CSV与M6的非周期字段及周期字段
均一致，未观察到这些控制中的功能或周期退化。

`multiword_fault_liveness01/successor01/measurement01/result.json` 记录
VL=1/4/5/8/9/12/16 七项通过。每项只有一次真实请求、缺页响应、load done、
MASKU done 和 sequencer 异常响应；分别消费1/1/2/2/3/3/4个展开谓词字，
完成后本地 spill 两槽均空、全局 running 为零。编译退出0，用时28.933秒；
各仿真退出0，用时约10.6秒，输入快照未变化。

这些是 e64/m4、vstart0、首元素缺页的局部结果，不是正常路径性能对照，
也未覆盖带有效数据前缀的故障、FOF 或完整 SoC。后续检查仍按下述边界执行。

后续 load 联合回归见 `multiword_fault_liveness01/regression02/REVIEW.md`：
两版本正常 masked/unmasked 路径的120行、43字段周期轨迹逐字节一致。
候选共7场景、14条指令通过，涵盖非零vstart、故障前缀延迟实际VRF写回、
末字故障和FOF；每条指令随后执行无复位的masked load以检查残留状态。
14336次完整字节比较检查了数据、prestart、inactive、suffix和tail。
有前缀的场景均先等最后bank写入，再进入谓词排空，未绕过final grant。
这些是局部模型中的性能与正确性证据；实际CPU CSR更新、页表和Linux仍未覆盖。

修复后需检查一字、两字、三字及更长流，非零 vstart，前缀实际写回，末字
故障、FOF、重启及后继 owner，并对照正常请求周期。局部测试不包含完整
CVA6、Linux 信号帧或页表实现；仍需 SoC 来源程序回归。

旧板测 RVV-16 的原 e64/m4 程序 VL=8，仅需要两个展开谓词字。
因此本次 VL9 反例不能直接解释或关闭该历史 Linux 卡死。

进一步核对旧 VL8 局部 CSV：第98至100周期仍有 `spill_b=1`、
`first_element=4`，同时 global idle 为1。这个模型将 flush 输入固定为0，
所以不能用其残留推导真实 SoC 重试必然污染。封存 M6 已有
`lsu_ex_flush_q` 驱动 VLDU spill 的 flush；dispatcher 的 WAIT_IDLE_FLUSH
依赖 sequencer 的 `ara_idle_i`，随后经 lane/VLSU 清理通路到达该 spill。
VLDU 局部 idle 因残留 mask 为0，用于专用命令的所有权切换屏障，不是
这里启动 flush 的前提。VL8 的等待清理与 VL9 无法启动清理是不同状态。
这个静态核查未形成新的 RTL 修改或独立 bug 结论。
