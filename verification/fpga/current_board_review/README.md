# 板测旧问题与当前 RTL 复核

## 范围与验收规则

本轮从验证分支 `7d5d1829` 开始，核查较早 FPGA 版本报告的问题在当前
RTL 中是否仍存在。旧板测失败并不自动构成当前 RTL 失败，模块测试通过
也不自动构成原始 Linux 程序回归通过。

当前修改、原始触发条件与对应验收见[修复索引](CURRENT_REPAIRS.md)；
历史失败族的剩余范围见[完整范围清单](CURRENT_SCOPE.md)。

### 最新修复与验收入口

最新冻结镜像为 **candidate06（M6）**。索引源与目的组重叠、物理EEW混合
且缺页重启时的源转换去重错误已经由原始首错波形定位并修改。三个完整
Sv39来源程序均完成独立验收，共48405项检查、4832结果、302 guards，
实际worker正常退出0，见
[M6三项独立终审](indexed_overlap_original/repair06_whole3_audit01/REPORT.md)。
48项代表性回归现已完成[独立终审](gather_repair05/m6_regression48_terminal_audit01/REPORT.md)：
全部实际ELF通过，16项正常控制的完整含周期提交CSV逐字节一致，未观察到
这组控制的周期退化。不推广为所有工作负载或所有访存故障路径的周期结论。

Gather M5源起点修复已通过两项原98调用前缀及48项回归；M6的e16/m8/op1
原98调用也已通过[完整原始CSV独立验收](gather_original_review/e16_m8_ops1_prefix98_terminal_audit01/REVIEW.md)。
e8/m8/op1原66调用现已通过[独立验收](gather_original_review/e8_m8_ops1_prefix66_terminal_audit01/REPORT.md)，
保留65个前序调用及全部1024容量结果/guards。后继e16/m8/ei16原98调用
也已通过[完整动态索引验收](gather_original_review/e16_m8_ops20_prefix98_terminal_audit01/REPORT.md)，
保留原97前序及50176结果/196guards，含OOR与有数据的末尾。
e16立即数31原98调用也已通过[独立验收](gather_original_review/e16_m8_ops3_prefix98_terminal_audit01/REPORT.md)，
包括VL1从源31取值、完整前缀/尾部保护。e8/m8立即数31原66调用在同镜像
执行。这些前缀不是完整2688调用或未知旧停滞验收。

下面保留较早镜像的发现与验收过程。标题中的candidate04/03/02及进行中
语句按各段原时间理解，不替代上述最新入口，不把旧镜像结果归于M6。

故障原始资料：

- `/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/repro/ALL_FAILURE_REVIEW.md`
- 同目录 `STALL_TRIAGE.md`、`README.md`，父目录 `ISSUES.md`。
- `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/` 下的归档 RTL、ELF、
  板测日志和身份核对清单。

2026-10-10 读取交付包的 `hashes.json`，逐文件重新计算 SHA256：

| 交付包 | 文件数 | 不匹配 |
| --- | ---: | ---: |
| `rvv_verification_handoff02` | 62 | 0 |
| `rvv_verified_handoff03` | 795 | 0 |
| `rvv_compare_uncovered_handoff01` | 326 | 0 |

总报告的 871 条失败、198 条卡死是 ELF 记录数，不是独立 RTL bug 数。
本轮优先处理五类线索，不声称已经重新执行全部历史程序。

## 较早镜像的发现与验收记录

**当前candidate04：19个归档比较单例和16项代表性控制已独立验收通过。**
candidate03的原始e8/m2比较single已实际失败：活动结果位84应为0却为1。
周期探针确认源从全局元素64读取，但结果仍从位0压缩，因而位84使用
源元素148。见[源起点错误的原始数据与周期证据](comparison_alias_original/SOURCE_ORIGIN.md)。
candidate04相对candidate03仅修改lane sequencer的整数/浮点比较源请求
起点，保留架构vstart及MASKU的活动位门控。原e8/m2的同ELF已完整PASS，
周期后验确认源84与压缩/最终写回位84正确。三项浮点A/B控制全部PASS，
其中两个非零vstart旧失败各10错变0错，零起点控制完整周期CSV不变。
19个原单例的整批及16项代表性控制均完整PASS/exit0，独立审计核对
原始成员、输入ELF、成功退出、失败标记否决与完整提交CSV；1859项计划pin、
1144项原测量pin和107项原来源pin均无漂移。16个控制中15份CSV逐字节
一致；重启比较控制仅有周期字段变化，结束周期30318变30319，增加1周期，
非周期事件字段完全一致。见[独立35项验收](comparison_alias_original/candidate04_audit02/README.md)。
此前candidate03的FAIL/CANCELLED记录保持不变，不据此关闭全部4032配置
父矩阵或原Linux ELF验收。

随后在同一candidate04镜像完成八项非周期性NaN定向控制：prestart、
屏蔽元素和tail不多提交NV；活动sNaN及有序比较的qNaN正确提交NV；
EQ/NE的活动qNaN保持静默。全部数据/输入/CSR检查通过，701项pin无漂移。
这是新的定向范围，不冒充板测原程序，见
[NaN资格化验收](comparison_source_controls/nv_successor/DUT_REPORT.md)。

另外19个归档标量比较single全部通过candidate04，独立核查1321项计划pin、
166项来源pin、539份冻结源码，以及每条目标指令的分配、退休、完成和原始
全容量oracle，见[标量比较19项验收](comparison_scalar_original/terminal_audit01/README.md)。

Gather新八项的首轮仍保留1 TIMEOUT、7 CANCELLED。退休轨迹确认两项
已完成目标和全容量检查，之后耗时来自56448组合的标量筛选循环。
后继保留原输入/汇编/完整oracle，只缩窄空枚举循环，八个来源tuple现已
全部通过candidate04：一项已验收control加七项独立续跑。另一次worker
启动观察门禁失败的NOT_ACCEPTED记录也保留，见[续跑说明](gather_original_review/CONTINUATION.md)
及[精确八项终态](gather_original_review/successor01/vcs_candidate04_remaining7_01/complete.json)。

NF8四个原来源tuple的真实Sv39程序现已全部通过candidate04，覆盖两个
load异常重启、一个store异常重启和一个全屏蔽场景，共12394项检查。
见[四项终态](masked_translation/nf8_strided_review/sv39/vcs_candidate04_01/complete.json)。
这不等于完整192组合或原Linux信号流程已验收；NF7仍属于candidate02独立批次。

为取得当前组合RTL的直接回归证据，已完成
`integration/candidate04_regression38_03`：保持旧candidate02已验收38项
ELF、完整oracle、每项预算及四路调度，切换到candidate04冻结镜像。
最终执行器通过17项host检查与38项dry-run，四个真实simv已出现提交记录；
服务为`ara-candidate04-arithmetic38-03`。前两个准备目录没有运行DUT，保留作
审查记录。2026-10-11 04:02:49 -07:00完成，38/38 PASS，服务正常退出。
独立复核1368项文件哈希、38个实际ELF/镜像身份及76份原始日志均通过；
见[当前38项终态验收](integration/CANDIDATE04_38_TERMINAL.md)。这不代表
完整原始22种算术矩阵或Linux程序已完成回放。

**已验收组合镜像 candidate03：标量插入focused11及代表性回归16/16实测通过。**
candidate03仅在candidate02基础上修正VMVSX/VFMVSF内部请求vstart，
保留架构CSR的空操作判断。原e16/m1/op6、整数同因及stored-EEW控制共11项
通过，见[周期证据与冻结身份](fp_moves/CANDIDATE03_REVIEW.md)。随后复用同一
candidate03镜像，以jobs=2重放candidate02的原十项RVV/QBS/AKV smoke及
六项single，完整oracle全部通过，16份含周期字段的完整提交CSV逐字节一致。
总墙钟470.72秒，1305项pin无变化，无新构建或生产修改；见
[16项报告](fp_moves/CONTROLS16.md)及[终态记录](fp_moves/candidate03_controls16_01/complete.json)。
candidate03未重跑全部38项，也未据此承接candidate02的完整访存验收。

NF7 indexed与mask-alias测试使用**candidate02**。NF7分组已有局部DUT通过，
整批验收仍待完成；alias三项单例与三项原序列前缀已全部通过，独立终态
检查确认输入身份、完整检查、成功退出与失败标记否决。前缀覆盖262个不同
原始配置。详情见[掩码逻辑验收](mask_alias_original/BOUNDED.md)。
分别以 `masked_translation/indexed_review/sv39/vcs_plan06/` 和
`mask_alias_original/vcs_candidate02_01/` 的独立终态为准，不将启动或局部结果
记作整族通过，也不将其结果归于candidate03。

**此前组合镜像 candidate02：算术回归38/38实测通过。**
`integration/memory_regression_plan02/complete.json` 已终止为
`PASS_38_CANDIDATE02`，四路运行沿用final04的原38个ELF及oracle，
不包含此前已在candidate02通过的十项smoke。独立复核全部returncode0、
原oracle及tohost=0；752项计划pin、162项门槛pin和539文件快照均无不匹配。
六组extension完成144子例及144次整寄存器读回退休；比较主矩阵完成
102/100/100子例。证据见
[独立审计](integration/memory_regression_audit01/finding.json)及
[组合验收](masked_translation/COMBINED02_ACCEPTANCE.md)。
这是candidate02的新实测，不是移用final04 PASS，也不代表完整Linux访存族验收。

较早的冻结整机批次 `current_board_integration_final04` 已结束：48个ELF中
45 PASS、1 TIMEOUT、2 CANCELLED。超时项为 `extension_e32_m4_vf4`，
记录到子例22。随后同镜像的原子例完整复现通过，约59.76秒；与矩阵
截断前144周期的事件序列一致，三个内部布局转换有界完成，未进入怀疑
的blocked/pending分支。不能将这些内部操作误判为已证实的死循环；
原始超时及取消记录保持不变。随后独立 `extension_overlap/final04_successor01`
在同一镜像、同一ELF、未改oracle的条件下，将这三项完整矩阵全部跑通，
用时分别651.01、630.22、1000.71秒，输入哈希保持一致。
因此final04的48个ELF已有跨两次保留记录的全部通过证据，而非首轮48/48。
该批次不包含后加的 AddrGen/VLDU/异常响应
等待候选。比较矩阵的四项已全部通过，包括之前超时的 e16。

| 项目 | 核查对象 | 当前证据 |
| --- | --- | --- |
| 掩码流长度与消费位置 | MASKU、SLDU、lane MaskM 请求 | 三条 slide 卡死已复现；修复后 3,648 项联合测试通过，选定原始源码移植单例及组合整机通过 |
| 比较旧目标读取起点 | lane MaskB、operand requester、MASKU 合并 | 当前已修正，缩减测试通过；未重复修改 MaskB。长掩码流另有已复现的问题 |
| Mask-logic source alias 原三条停滞来源 | 原序前缀至零基trial97/65/97及对应精确tuple | **candidate02六项终态PASS**，独立严格checker核对两阶段COMPLETE、六项markers/counts/exit0、失败标记否决及pins零漂移；覆盖262个独立原trial（含重复tuple共265调用），不是三条完整5376-case父矩阵、原Linux闭环或candidate03验收；[后续终态与范围](mask_alias_original/BOUNDED.md)取代此前alias进行中状态 |
| 有序规约异常掩码位置 | VMFPU 元素选择、issue BE、FP 标志 | 当前与归档均复现丢 NV；修复后 166 项 VMFPU/FPnew 回归通过 |
| m8 浮点扩宽规约合法性 | dispatcher、下游 EEW/EMUL | 原 VL=0 程序及十个非零 VL 扩展配置整机通过；无序规约另需覆盖跨指令状态 |
| 整寄存器搬移重启 | dispatcher 源 EEW 与架构 vstart | 原始源码移植单例及混合 EEW/后继读取扩展整机通过 |
| slideup 源读取起点 | lane sequencer、operand requester、SLDU | 独立审查发现并实测复现；修复后 41 项源请求及数值检查通过 |
| FP/整数标量插入及 RVV-10 原来源回归 | dispatcher VMVSX/VFMVSF内部vstart与目标布局；原FP move/slide单例 | candidate02真实BE0及原oracle失败；candidate03 focused11通过，七项正常控制周期一致，另16项代表性回归完整trace保持一致；现[原来源47 single ports](fp_moves_original47/README.md)全部PASS（32 slide+15 scalar insertion），独立核验全部markers/exit及1309 pins零漂移；不代表完整父矩阵或原Linux闭环 |
| gather 重启前缀保护 | MASKU gather 写回字节使能 | 修复后 12 项端口级检查通过；原始源码移植及前缀扩展整机通过 |
| 无序规约异常归属 | VMFPU 部分和、跨 lane/SIMD 合并与异常提交 | 80 项模块及整机异常边界通过；166 项有序规约保持通过；后续发现跨指令活动状态覆盖，不能视为整类闭环 |
| 浮点比较异常 predication | VMFPU、MASKU 精确有效元素范围 | 整机实测 all-off、tail、prestart 多置 NV；产生端 606 项、接收端 24 项及归档汇编来源的五项局部移植（含重建oracle与派生控制）通过；final04 四项比较矩阵全部通过 |
| 连续规约活动状态 | 远端 lane 活动位、NV 提交、seed 选择 | 不同 VL 的连续独立规约整机复现数值及 NV 错误；按规约保存活动状态后，1/2/4 lane 共432项通过，final03 successor 原连续规约整机通过 |
| 大偏移 slide | 原始 e8/m4、e8/m8、e16/m8 源码场景 | final03 上 e8/m8 末元素185变91，证实 MaskM 读字3比生产者写字3提前三周期；精确 RAW 完成约束后，final04 六个原始来源完整程序全部通过 |
| 整数扩展高端重叠 | 原始 e16/m2、VL127、vzext.vf2 v24,v25 | final03 反复 EEW8/16 转换且未接受原指令；限定扩展域的快照修复后，final04 原始来源完整 oracle 及三项 vf2 矩阵通过；successor01中两项vf4、一项vf8完整矩阵也全部通过 |
| 全屏蔽普通 load 的翻译异常 | 原始 scenario3 的 VL8/e16/all-off 条件 | 局部32项通过；相同ELF真实Sv39对照由全关保护页FAIL变PASS，活动页故障重试与有效页对照保持PASS；原始Linux信号/完整访存族仍待验收 |
| VLDU 异常退休与清理 | 部分前缀结果、最终 VRF grant、剩余字节 | 实测 done15早于write35；最新候选同一测试台6项收尾和4项到达顺序通过，正常对照周期不变；组合镜像3项Sv39及10项smoke通过，更多异常场景待验收 |
| 异常 load 的跨指令收尾 | sequencer 响应、FOF、对应 vid 的 load done | 公共端口实测异常响应9早于done21；最终候选同一7项通过，普通load/无故障FOF响应周期不变；同一组合镜像13项整机通过 |
| Sv39 扩展访存 | masked load/store、正负零stride、FOF及非零故障重启 | candidate02_extended8_02完整通过八个场景、6227次检查，之前被外层期限中断的记录保留 |
| NF2 段访存字段故障 | 稀疏mask、后字段跨页、元素5重试、已完成前缀保护 | 相同candidate02镜像四项通过、4133次检查；b3为旧失败来源，b5为历史正向控制；不替代Linux信号ABI验收 |

### 新候选与冻结回归的区别

工作区另有第九个生产文件 `hardware/src/vlsu/addrgen.sv` 的 masked
访存候选；final04 冻结镜像不包含它。当前候选状态、性能代价和验收约束
见 `masked_translation/REPAIR_CONTRACT.md`，不能将后台 final04 的结果
算作这一新增候选的结果。

随后工作区又加入第十个生产文件 `hardware/src/vlsu/vldu.sv` 的异常
收尾候选。`current_board_masked_candidate01` 冻结镜像仅含 AddrGen
修改，不含此 VLDU 候选。不得将前者的 Sv39 结果误记为两项修复合并
后的验收；合并候选需要独立冻结、构建和整机回归。

AddrGen 单独候选的三项真实 Sv39 测试已通过，每项709检查、0错误。
修复前全屏蔽保护页首错明确为目标PC `0x80000b68` 的cause13，tval为
`0x40001000`；修复后保持目标PTE无效且不产生该异常。活动故障对照仍
发生精确异常、修PTE、SFENCE并从原PC重试。详见
`masked_translation/CANDIDATE01_SV39_20261010.md`。这三项不包含新
VLDU最终握手修复，也不代替store/stride/FOF/segment验收。

三项访存修改的组合镜像已另行封存至
`/home/wangwy/fpga_runs/current_board_memory_candidate02/frozen`，后台
`ara-board-memory-candidate02.service` 已正常结束，构建、三项原Sv39程序和
十项普通RVV/QBS/AKV回归全部通过。三项Sv39分别用331.95、331.84、
294.37秒完成；这些是宿主机墙钟时间，不是RTL性能周期。详情及状态路径见
`masked_translation/REPAIR_CONTRACT.md`；这13项不代表完整历史访存族已经验收。

十项普通RVV/QBS/AKV控制程序的ELF及包含周期字段的完整提交记录，
与final04逐字节一致；可复核清单见
`masked_translation/COMBINED02_ACCEPTANCE.md`。该结论仅覆盖这些正常控制。
随后使用同一组合镜像执行八项真实Sv39扩展，覆盖普通load/store、
正/负/零步长、非零故障重启和FOF；参考模型通过不等于RTL通过，
首次扩展在 `masked_translation/sv39_extended/candidate02_extended8_01/`
因外层期限中断；保持ELF/RTL/oracle的02补跑现已完整通过。
NF2字段故障测试也已单独通过，见
`masked_translation/segment_review/sv39/vcs_preflight01/complete.json`。
具体范围和限制见 `masked_translation/COMBINED02_ACCEPTANCE.md`。
NF7 indexed正在candidate02独立分组实测，已有局部DUT通过但尚未完成整批验收；
不能用NF1或NF2通过替代它，也不能归入candidate03验收。

`current_board_integration_final03/frozen` 不随工作区后续修改变化。
其回归使用七文件的已冻结组合，不包含后来新增的整数扩展
域识别。新修复候选需要另建快照和镜像；不得把 final03 的 PASS 当作
这个新候选已经通过。

扩展候选保留此前普通 widening 域，只在 VXUNARY0 的六种合法
VZEXT/VSEXT 解码中设置内部分类标志，同时用于源快照识别、合法高端
重叠和旧目标保存。需要转换旧目标布局时，扩展指令的未屏蔽形式也先
保留窄源，再转换目标并重放源，以保留 prestart/tail，不假定 vf4/vf8
具有与普通两倍扩宽相同的读写节拍。未增加快照容量或放宽重叠合法性。
独立审查见 `extension_overlap/INDEPENDENT_DESIGN_REVIEW.md`；原始程序、
逐周期记录和参考模型结果位于该目录的 `measurement01/`。

### final03 整机检查点

当前该流水线已结束，不能写成全部通过。35 个计划 ELF 中，31 个完成并
通过：原始来源单例 6、组合 1、扩展 5、gather 2、smoke 10、比较异常
5，以及比较矩阵的 prefix 与 e64 两项。e64 矩阵用时 285.07 秒；e32
在 300 秒墙钟上限停止，e16 同批取消。最后的 flags-sequence 和
reduction-epoch 未运行。TIMEOUT/CANCELLED 不是新的数值反例，也不计 PASS；
将检查提交进度，用同一冻结镜像及 ELF 在新目录补完，不覆盖旧批次。

整数扩展候选另跑的 dispatcher 回归通过 459 个配置、12,738 个检查，
证据在 `/home/wangwy/fpga_runs/board-extension-dispatcher-regress01/`。
这覆盖既有规约/整寄存器搬移译码，不代表新的 extension 数值与快照路径
已经通过。

随后同一 final03 镜像的 successor 补跑中，flags-sequence 和
reduction-epoch 已分别用39.18秒、22.16秒通过，原连续规约首错消失。
e32 比较矩阵在337.65秒通过；e16 在600秒仍未完成，记录 TIMEOUT，
不计入整程序 PASS，不重写原流水线结果。只读复核证明 e16 的102/102
子例已全部返回0，日志已有 `MATRIX_PASS sew=16 cases=102 errors=0`；
最后子例在cycle524645完成，最后退休PC为`0x80000760`、cycle525503，
仍在输出收尾标记。没有未完成的数值子例，也没有固定子例卡死的证据。
完整依据见 `extension_overlap/FINAL03_E16_TIMEOUT_REVIEW_20261010.md`。

### final04 历史启动与阶段记录

final04 当时冻结539个输入文件，包含上述八个改动文件（新增 sequencer
RAW 修复）。预检命令和输入哈希在
`/home/wangwy/fpga_runs/current_board_integration_final04/preflight/`。
计划先验收原始 VL127 extension，再验收大偏移 slide 六程序，之后运行
既有整机检查和144子例的 extension 矩阵，合计48个 ELF；该数量含组合及
对照，不能解释为48个独立 bug。所有矩阵在 Spike 上先通过，但新 RTL
程序结果仍须单独验收。详见 `extension_overlap/MATRIX_READY_20261010.md`
及 `large_offset_slide/MASK_RAW_HYPOTHESIS.md`。

历史启动检查中，服务 `ara-board-integration-final04.service` 曾处于
active/running，PID3785239，阶段为 `build-image`；这不是当前运行状态，
该流水线现已结束。运行输出与预检目录分离：

```sh
jq '{status,current_stage,stages:[.stages[]|{name,status}]}' \
  /home/wangwy/fpga_runs/current_board_integration_final04/campaign/status.json
```

当时每阶段最多四路，单 ELF 600秒。e16/e32 比较矩阵此前仍在逐项推进且
接近300秒上限，因此使用600秒验收预算。该轮extension矩阵的原始
TIMEOUT/CANCELLED记录保留；后续逐周期复核表明trial22的三个维护uop
有界完成，blocked/pending假设被排除，不能称为已证实的维护循环。
同镜像、同ELF完整补跑结果见上文及
`extension_overlap/FINAL04_TRIAL22_REVIEW_20261010.md`。

final04 构建已通过；`extension-original` 在48.15秒完成，记录
`RVV_EXTENSION_PASS sew=16 cases=1 errors=0`、`BOARD_REPLAY_PASS`，
tohost=0。它检查原 VL127 完整结果、prestart/tail 和 guard，不是仅观察
不再卡住。独立 trace 复核确认原目标接受、退休各一次，三个维护 uop
全部完成，未再进入永久 EEW 转换循环。

`large-offset/summary.json` 记录六项全部 PASS：e8/m8 单例289.59秒、
e8/m4 单例197.55秒、e8/m4 序列261.98秒、e8/m8 序列428.26秒、
e16/m8 单例203.88秒、e16/m8 序列294.11秒。这些是仿真墙钟时间，
不是硬件性能周期。这些是历史阶段记录；最终批次及独立补跑状态见上文。

大偏移掩码 RAW 的独立联合模块对照见 `large_offset_slide/mask_raw/README.md`：
真实 sequencer、四个 lane sequencer 和 requester 下，修复前22项完成、
8项失败，修复后22/22通过；其余14个对照的记录和周期相同。纯 WAR 对照
仍走 source-lifetime 而非 wait-complete。生产者和 VRF 在该测试中由模型
提供，不用这个结果替代原程序的 SLDU/完整访存验收。

## 已复现的当前 MASKU/SLDU 卡死

使用交付的 `mask_slide_restart_tb.sv` 联合驱动真实 MASKU/SLDU，保留原始
三条触发配置及三个对照。runner 将 RTL、头文件和测试复制到独立输出目录，
记录 `pins.json` 后编译；不会使用另一轮已修改的工作区文件。

输出：`verification/out/board-current-slide-before-20261010/`。

| 指令 | SEW | VL | vstart | 掩码握手数 | 完成 | 剩余 issue/commit 字节 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| slide1up | 32 | 16 | 0 | 2 | 是 | 0/0 |
| slide1up | 32 | 16 | 8 | 1 | 否 | 32/32 |
| slide1up | 64 | 8 | 0 | 2 | 是 | 0/0 |
| slide1up | 64 | 8 | 4 | 1 | 否 | 32/32 |
| slidedown offset=0 | 16 | 32 | 0 | 2 | 是 | 0/0 |
| slidedown offset=0 | 16 | 32 | 16 | 1 | 否 | 32/32 |

失败时 MASKU read count 和掩码队列均为零，SLDU 掩码无效；源操作数
四路有效，结果队列未满。因此该实验能够区分掩码耗尽与源数据/写回反压。
测试中的 `EXPECTED_BUG_REPRODUCED` 表示成功复现预期故障，绝不是功能 PASS。
这仍是联合模块测试，不包含完整 lane 请求、VRF 和 Linux 执行环境。

### Slide 修复与写回验证

`board-current-slide-before-footprint-20261010` 在原六条测试上增加写回端口
检查，没有改变 RTL：两个 slide1up 卡死例都已经写坏 32 个前缀字节。
SLDU 从前缀开始遍历并没有错，但必须禁止这些元素产生写回字节使能。

修复只改两处责任边界：

- MASKU 对 SlideUnit 保留完整遍历所需的 read/commit 掩码流，不按
  `vstart` 提前裁短；原有 slideup 的 stride 裁剪仍保留。访存的重启裁剪不变。
- SLDU 的重启前缀保护同时覆盖 slideup/slidedown；slide1up 只有
  `vstart=0` 才允许将标量写到元素零。不增加流水级或改变握手协议。

`verification/out/board-current-slide-after-20261010/status.json` 为 PASS：
六条均消费两拍掩码、正常完成、issue/commit 计数归零；三个重启点只写
32 个有效字节，三个零起点对照写 64 字节，前缀错误写回均为零。
这里验证的是全一掩码和零源数据的写回范围与完成性，不能替代任意数据、
稀疏掩码、真实 VRF 读取以及原始完整程序的回归。

随后 `verification/out/board-slide-matrix-current-20261010-a/` 的独立字节
oracle 联合回归通过 3,584 项。包含 SEW8/16/32/64，整拍与非整拍 VL，
零起点/元素一/跨 lane 字边界/最后元素重启，普通与标量插入 slide，
零/单元素/非二幂/跨字/源范围外偏移，全开/全关/交替/稀疏掩码，以及
各 lane 不同写回反压。每项检查写入字节及数值、无重复写回、前缀/尾部/
屏蔽字节不写、握手暂停时结果稳定、恰好一次完成和队列排空。
数据使用不同字节值，oracle 按架构元素运算，不调用 DUT 的 shuffle 函数。
源和掩码递送仍由测试台建模，完整 lane/VRF 及程序测试另行验收。

性能对照使用同一矩阵中的 896 个 `vstart=0` 子项，不计作新增独立配置。
`board-slide-matrix-before-controls-20261010-a` 使用修复前冻结的 RTL，
`board-slide-matrix-current-controls-20261010-a` 使用修复后 RTL，两边均
PASS；逐项比较完成周期，`changed=0`。该结论限于这些联合模块对照，
不等同于全部应用无性能回退或时序已收敛。

最终矩阵 `board-slide-matrix-current-20261010-b` 另加 64 个不带掩码的
重启/对照组合，总计 **3,648/3,648 PASS**，耗时 51 秒，且继续通过上述
896 项逐周期数对照。这三个矩阵版本有重叠，不能相加后宣称更多独立测试。

加入 gather 修复并完成 lane 源读取修复后，再以最终工作区组合运行
`board-slide-matrix-final-20261010-c`：**3,648/3,648 PASS**，耗时 50.732 秒，
896 个零起点对照的完成周期仍全部相同。该目录冻结最终 MASKU/SLDU
输入，避免误将较早补丁组合的通过结果当作最终组合结果。

## 复现命令

在验证工作树根目录，修复前的已封存快照保留上述输出目录中。
对当前工作区运行功能检查：

```sh
python3 verification/fpga/current_board_review/slide/run.py \
  --out verification/out/board-slide-current-NEW
```

`--expect-starvation` 仅用于故障基线的诊断验收，不应加入修复后的通过回归。
每次必须使用新输出目录。VCS 在宿主机运行，不使用 Verilator 或 URG。

## Dispatcher 两项修复

完整来源、哈希和运行目录见 `dispatcher/results.json`。

- 原板测 `0xcc881c57` 在 e32/m8、VL=0 时被错误报为 illegal；当前也复现。
  修复复用整数扩宽规约已有的单结果寄存器例外，普通 m8 扩宽向量指令仍拒绝。
- 原板测源按 EEW8 装载、当前 SEW16、vstart=1，当前请求从字节 1 开始，
  而不是字节 2；反向 EEW 情形也不正确，另有 vstart=EVL 仍发射的问题。
  修复按架构字节位置精确换算内部元素起点，需要时复用已有布局转换，
  超出 EVL 则不发射。vstart=0 保留原存储布局快路径。

修复后定向检查 **99/99**，扩展检查 **12,738/12,738** 通过。
后者包含 **459 条目标指令配置**，不是 12,738 条独立程序；覆盖 70 个
浮点扩宽规约、384 个整寄存器搬移及其非法对照。
真实 `ara_sequencer` 的额外检查确认 m8 规约跟踪 8 个源寄存器、1 个种子
和 1 个结果寄存器；保留内部 EMUL 编码不等于申请 16 个结果寄存器。
64 个零起点搬移配置未增加布局转换请求。这还不是 FPU/VRF 数值验收。

## 有序规约异常标志

详见 `ordered_reduction/MEASURED_20261010.md`。原始场景的 seed=+Inf，
输入交替为 +Inf/-Inf，mask=0x24；参与相加的非首子元素被移到运算器
低位槽，但异常掩码仍取原字的低位，导致 FMA 已产生的 NV 被过滤。
修复让异常掩码跟随实际被选中的元素，不改变算术顺序或增加周期。

冻结的当前修复前 RTL 在 166 项中有 132 项丢失异常标志；修复后
166/166 通过，132 项标志得到纠正，结果位与周期数均未变化。
真实 VMFPU/FPnew 的逐周期 CSV 记录操作数、接受事件、原始 FMA 状态、
掩码后状态、tag 和已寄存的异常输出；不能仅根据最终打印的 fflags 猜测根因。
该测试的 CSR sticky OR 和 slide 链接由测试台建模，完整指令/CSR 验收仍待完成。

## 独立审查后的补充门槛

首轮模块通过后，独立审查发现 slideup 的 `SlideAddrGenA.vstart` 仍继承
lane-local vstart，而 SLDU 从源起点遍历。这是独立于掩码耗尽的错误：
直接从正确起点喂数的联合测试无法覆盖它。

`lane/SLIDE_SOURCE_V2.md` 记录真实 lane sequencer、operand requester 和
SLDU 联合复现。e32、VL=16、vstart=8 的 slide1up 修复前请求 VRF 字 33，
而不是字 32，使目标元素 8 得到源元素 15，而不是源元素 7。
将 slideup 的源请求起点置零，保持 SLDU 的前缀写保护；slidedown 路径不变。
41 项中修复前 13 项 UP 失败、28 项对照通过，修复后全部通过；
所有完成周期相同，20 项 DOWN 的请求及结果记录完全相同。
测试包含真实请求仲裁，但 VRF 数据存储和读后队列由测试台建模。

整机程序还需补非零 VL 的 m8 扩宽规约数值测试，以及混合存储 EEW 的
整寄存器搬移和后继读取。原板测 m8 的 VL=0 场景仍保留，但单独通过它
只能证明不再误报非法，不能证明后端算术正确。

## Gather 重启前缀保护

详见 `gather/README.md`。原始板测有独立的 `vrgather.vv` 前缀损坏记录；
本轮先用交付包通用短例中的 `vrgather.vx` 输入缩小问题，不把这个短例
冒充已在板上执行的同一 ELF。SEW16、VL=2、vstart=1、标量索引 0，
源为 `1000+i`、旧目标为 91。修复前真实 MASKU 写回端口在第 7 周期以
`BE=03` 改写元素零，得到 `[1000,1000]`，应为 `[91,1000]`。

MASKU 从零开始遍历 gather，但原 BE 仅检查 vm/predicate，没有检查
架构前缀。补充绝对目标索引 `vl - issue_cnt_q >= vstart` 的写使能条件，
覆盖四种 SEW，不改变索引请求、队列或完成路径。修复后该写使能为零，
12/12 项检查通过，短例仍为 9 个周期。另含跨结果字、稀疏掩码、
向量索引及 EI16 索引检查。原始随机输入的 vv 程序在整机阶段单独回归。

## 关闭问题的条件

1. 冻结旧板测资料并核对实际触发指令、配置、输入及 oracle。
2. 在当前 RTL 确认是否仍有故障，记录首错或卡死的关键周期信号。
3. 修复前后同一测试对照，另加邻近边界、控制组、连续请求和普通 RVV 回归。
4. 原始失败程序回归通过才关闭其原始记录。缩减例通过只关闭相应局部假设。
5. 页表、保护页、FOF、异常处理及重启类保留真实系统环境，不能直接替换成
   不产生异常的裸机访存用例。

## 最终组合整机验收

`integration/` 保留原始汇编和选定场景的输入、完整检查代码及来源哈希。
只替换 Linux 入口、输出和退出机制，不将 Linux ELF 直接作为裸机 ELF。
14 个原始来源移植/补充程序的 Spike 参考运行全部通过；这检查软件 oracle，
并不证明 RTL 已通过。另编译 7 个普通 RVV 测试及 3 个 QBS/AKV 测试。

最终冻结输入位于：
`/home/wangwy/fpga_runs/current_board_integration_final01/frozen/`。
2026-10-10 启动服务 `ara-board-integration-final01`，顺序为整机编译、
六条单例、组合程序、扩展数值检查、两条 gather、十条普通/自定义指令回归。
同一阶段最多四路；任何阶段未通过就停止后续阶段，保留首错。
本节仅记录启动，不把待运行项写成 PASS。

进度及逐阶段结果：

```sh
cat /home/wangwy/fpga_runs/current_board_integration_final01/campaign/status.json
systemctl --user status ara-board-integration-final01 --no-pager
```

`campaign/plan.json` 固定命令、源码、配置和软件哈希；阶段目录保存独立
日志和检查结果。代码、配置或 ELF 身份不匹配即失败；断言、超时、跳过、
缺少终止标记以及架构检查错误均不能计为通过。不收集或合并旧覆盖率。

首次整机编译成功，六条单例中 `restart_compare`、`m8widen`、`wholemove`、
`slide1up_prestart` 已 PASS。`reduction_fflags` 在 300 秒达到时限，
`maskslide` 被同批 fail-fast 取消，不计 PASS。其原因尚不能写为 RTL 卡死：
两条提交轨迹都在推进标量筛选循环，maskslide 日志还显示目标指令已正常
返回；规约轨迹中尚没有选定目标 PC 的提交记录。后续阶段未运行。

`integration_fast/` 是保留原副本后的独立测试效率改进，只收紧三处已被
单场景过滤条件排除的循环边界，保留输入生成、汇编、寄存器初始化、
全部结果/异常/guard 检查。规约表游标补偿跳过的 285 次递增，仍读取
第 4905 项参考结果。原始场景源码逐字保留；主机对照和 14 项 Spike
检查通过。这不改变 RTL，也不把超时重新标记为 PASS；须用新副本重新
验收，复用同一个冻结的 VCS 镜像。新程序位于
`/tmp/current-board-integration-fast01/soc/`，来源证明见
`integration_fast/PROOF.md`。

新的四路服务为 `ara-board-fast01-replay`，状态文件是
`/home/wangwy/fpga_runs/current_board_integration_final01/fast01-replay/status.json`。
截至首批结果：`reduction_fflags` 20.91 秒 PASS，实测
`cases=1 flags_seen=16 errors=0`；`maskslide` 31.21 秒 PASS，
`cases=1 errors=0`；m8 原始场景也 PASS。后续程序依次验收，不将
这两个单例的通过扩大解释为全部旧板测问题关闭。

### 扩展验收发现的未解决项

最终镜像下六条单例和组合程序均已通过。扩展单例中的
`slide_source_e32`、`slide_source_e64`、`wholemove_layout` 通过。
但 `m8widen_nonzero` 第 10 个配置失败，后续 gather/smoke 阶段按规则
未启动，不能写成全套通过。

具体为 e32/m8、VL=65 的 `vfwredusum.vs`，FP64 seed=2.0，
仅源元素 1 的 +Inf 和元素 33 的 -Inf 被掩码选中；应返回规范 NaN
并置 NV=16，实际 NV=0。原 10 项中此前九项检查通过，这包括有序路径
的同类异常输入。该缺陷不是原 VL=0 illegal 修复的充分验收。

`integration_fast/prepare_unordered_single.py` 保留原汇编与输入，
单独执行第 10 个配置；先检查数值，再检查标志，全部检查仍保留。
Spike 通过；同一冻结 VCS 镜像在 25.68 秒内复现 NV=0，且 NaN 数值
检查通过，证明不依赖前九次调用。证据：
`/home/wangwy/fpga_runs/current_board_integration_final01/unordered-single-before01/`。
当前正在检查无序规约部分和合并时的异常掩码，尚未将此项关闭。

### 无序规约修复的局部证据与新一轮整机验收

`ordered_reduction/unordered_widening/MEASURED_20261010.md` 记录逐周期原因：
部分和合并继续使用已经耗尽的源掩码，跨 lane 和 SIMD 合并则继承了零 BE，
使算术部件已产生的 NV 被过滤。另一个边界是 seed sNaN 先于远端有效源
参与计算，不能仅按本 lane 当时的活动状态提交或丢弃异常。

修复分离真实源活动与内部算术掩码，每 lane 暂存 5 位无序规约标志，
在活动信息完整且本地完成之前提交；无有效元素时保持本实现的 seed 直通。
匹配的 before03/after03 共 80 项：修复前 49 项标志错误，修复后 80/80
通过，数值与完成周期均未变化；有序规约原 166 项继续通过。检查含连续
普通浮点指令、队列反压，以及与 dispatcher 一致的多 lane 标志汇聚规则。
这些是模块结果，不代替完整 sequencer/SLDU/CVA6 的验收。

另补连续 8 条规约与 8 条普通 VFADD 的裸机测试，检查异常清除、保存/恢复、
即时 CSR 读取及下一条指令的标志归属。准备目录为
`/tmp/current-board-flags-sequence02`，Spike 已通过。首次准备版本的失败
属于 oracle 过严：规范允许全屏蔽无序求和将 sNaN 规范化并置 NV，也允许
原样复制且不置标志。现将严格 NaN seed 保留检查用于有序规约，无序全屏蔽
对照使用有限数，不把实现允许的差异计为 RTL bug。

新冻结组合位于 `/home/wangwy/fpga_runs/current_board_integration_final02/frozen`，
服务 `ara-board-integration-final02` 正在独立构建并按原验收顺序运行。
状态文件为同目录 `campaign/status.json`；初轮证据不覆盖、不改写结果。

该新镜像的六条单例全部 PASS，组合程序 `all` 在 142.6 秒通过。
独立的 `flags-sequence02` 在 38.43 秒通过全部 8 条规约和 8 条普通加法，
包含数值、guard、即时异常读取以及先前标志恢复检查。随后五个扩展 ELF
全部通过，包含 `m8widen_nonzero` 的十个配置和扩展组合程序；
`gather_original` 与 `gather_prestart` 分别在 29.1 和 119.0 秒通过。

普通 smoke 阶段未通过，因此整轮仍标为 FAIL。首两项 vadd/vslideup 的
e16 第二检查均在元素 8 起出错。反汇编表明 smoke 的独立编译器配置
未完全禁止隐式向量代码：手写 VL=16 后，LLVM 为 C 数组初始化插入
`vsetivli zero,8,e16,m1,ta,ma`，后续目标指令实际只处理八个元素。
这不是将普通 RVV 数据路径误判为新 RTL bug 的依据。
`integration/smoke_scalar.py` 保留原构建器，并采用 `apps/common/runtime.mk`
已使用的 `-scalable-vectorization=off`、`-riscv-v-vector-bits-min=0` 和
`-mno-implicit-float`；测试源码、期望值不变，新 ELF 单独重新验收。

独立静态审查还指出跨指令的 `reduction_global_any_active` 未带指令身份：
较快 lane 若进入下一条规约，可能在 lane0 完成旧规约前覆盖活动位。
这是需要实测的重叠边界，当前单指令及 CSR 串行化连续测试不覆盖它。
正在构造无中间 CSR 排空的两条独立规约；未复现前不写成已确认新故障。

补充实测：上述 `smoke_scalar.py` 的十项程序已在同一 final02 镜像下
全部通过，含七项普通 RVV 和三项 QBS/AKV 控制及交接检查。完整结果位于
`/home/wangwy/fpga_runs/current_board_integration_final02/smoke-scalar02-replay/summary.json`。
旧 smoke 批次保留 FAIL，不改写历史记录；该结果也不包含之后新增的比较
异常修复。

连续规约测试 `reduction_epoch/measurement01/soc_replay/` 已出现实测反例：
第一条 FP16 无序规约使用 sNaN seed，远端 lane 有有效源；紧接另一条
相同 vtype、不同 VL 的独立规约。第一条应产生规范 NaN `0x7e00` 和
NV=16，实际为原始 seed `0x7c01`、NV=0。单独执行以及不改变 VL 的
对照均通过。周期归因和修复尚在进行，不能将前面的串行化检查当作这一
重叠边界已通过的证据。

### 比较指令另一个实测缺陷

`comparison/README.md`、`results.json` 保存来源、程序哈希、独立整数 oracle
及整机提交记录。相同旧冻结镜像下，active-sNaN 和无 sNaN 对照通过；
all-off、tail、prestart 三项预期 NV=0，实测 NV=16，而数据检查均通过。
5 项均通过启用 Zvfh 的 Spike 检查。这里使用归档汇编及重建 oracle 的
单场景移植，不冒充原始 Linux 全程序逐项通过。

当前比较由 VMFPU 产生元素结果，MASKU 才拥有精确 predication、tail 和
prestart 窗口。不能只撤销 VMFPU 的强制 vm=1，否则会改变 mask 消费协议。
下一步需要测量并修正逐元素异常与 MASKU 接受事件的对应关系；此缺陷
与无序规约少置 NV 是不同原因，不能用后者通过替代前者验收。

未处理的板测分类及准确来源见 `remaining_scope.md`。其中比较指令的
异常 predication、非 indexed 访存的 masked translation、扩展重叠等
需要分别取证，不能用本轮 slide/有序规约修复替它们结案。

### 连续规约修复与队列反压的新证据

`reduction_epoch/MEASURED_20261010.md` 给出原始三程序、Spike 对照和
50 信号的有限波形窗口：7107 周期首次返回归约 token 时 global activity=1，
7124 周期被下一条指令清零，7130 周期错误过滤旧 NV，7131 周期错误选择 seed。
修复每 lane 仅增加一个 epoch activity bit，在第一次内部 RX 握手时锁存，
同时用于标志提交和最终 seed 选择；seed 旁路只在架构写回请求有效时使用，
不再干扰 SLDU 部分和传输。独立审查确认快照保持到 lane0 grant。

`ordered_reduction/unordered_widening/epoch/README.md` 记录修复后 1/2/4 lane
各 144 项通过；同配置修复前分别有 0/59/57 项失败。432 项前后完成周期
完全一致，80/166/606 项既有回归仍通过。真实 SoC 的连续规约反例必须另行
用新冻结镜像验收，模块结果不替代这一门槛。

比较接收端的多字反压测试另发现结果队列元数据被覆盖。
`comparison/consumer_after04/multiword_active.log` 第 47 周期显示
`cnt=2 full=1 wp=0 rp=0 iter=2 accept=0 grant=0`，但第 0 项地址从 96
变成 98；最终写回 98/97，而应为 96/97。原因是默认描述符赋值没有检查
队列 full，写指针回绕后覆盖了仍在等待消费的表项。修复保护 full 时
的描述符，不改变队列容量或握手。修复后两字反压、跨字 NV/prefix 检查
已通过；`consumer_after06` 的整数四字测试也通过，包含错峰 lane grant
与 full→pop→refill，25 个输入 slice、218 次按 lane 统计的输入等待和
276 次按 lane 统计的输出等待，不产生浮点异常脉冲。

测试端曾把结果固定按 EW8 解码，实际 MASKU 输出采用当前 vtype.vsew。
该错误导致有效元素的数据误报，已依硬件端口布局纠正；它不能解释或
豁免前述地址 96→98 的真实覆盖。旧日志及修复前镜像全部保留。

组合验收冻结在 `/home/wangwy/fpga_runs/current_board_integration_final03/frozen`，
共 539 个输入文件。服务 `ara-board-integration-final03` 使用
`integration/run_pipeline_comparison.py`，先构建一个镜像，再按四路运行
原先板测移植、smoke、比较五项、比较矩阵、异常 CSR 序列和连续规约反例。
`campaign/status.json`、各阶段 `summary.json` 和 `worker.log` 分别记录
总状态、逐 ELF 结果和工作日志；失败停止，不复用旧 PASS 冒充新版本结果。
本段记录启动，不表示该组合已经完成验收。

接收端最终结果为 `consumer_after05` 23/23 加 `consumer_after06` 1/1，
合计 24/24；详见 `comparison/test_matrix.md`。final03 当前已经完成构建，
六个原先单例通过，后续阶段按独立总状态记录推进。

RVV-08 大偏移 slide 的额外真实场景见 `large_offset_slide/README.md`：
三种形状的单例和原有连续四次调用，各保留完整源码 oracle，共六个 ELF、
15 次目标调用。Spike 六项通过，现复用 final03 镜像独立三路重放，不为
这些测试重新修改 RTL 或重新构建。

## 架构判据

采用 [RVV 1.0 规范](https://raw.githubusercontent.com/riscvarchive/riscv-v-spec/v1.0/v-spec.adoc)
中的 prestart、Vector Reduction Operations、Whole Vector Register Move 规则：
前缀元素必须保持；规约的标量种子和结果仅占单个寄存器的元素零，不应按
普通扩宽向量结果的整个寄存器组判断；整寄存器搬移按当前架构 SEW 定义
重启位置和有效长度，不能直接把内部存储 EEW 下的元素编号当作架构编号。
