# 旧镜像覆盖率增量与未修复问题

## 当前状态摘要

以下表格是当前口径；后面的过程记录按发生阶段保留，旧的待准入
数字不代表当前集合。正式准入不等于重验全部历史案例。

| 项目 | 当前状态 | 是否纳入最新集合 |
| --- | --- | --- |
| 正式旧镜像PASS集合 | 741项，`targeted-toggle-offline-admitted-741-parent-20261007-01`；保留740项精确前缀，追加独立核验通过的GAP113，6162实例OR及限定Toggle增量核验通过 | 是；仍为冻结旧镜像，不代表当前RTL signoff |
| 741项原始DVE报告 | `raw741-dve-parent-20261007-01`及独立post-export audit通过；行85.21%、条件82.03%、分支82.95%、FSM60.54%、Toggle63.55%、Score74.86% | 已验收；Toggle较740项增加0.22个百分点，未应用豁免 |
| 最新原始DVE百分比报告 | 740项无豁免报告`final-raw740-dve-agent-20261007-01`；i_system行85.21%、条件82.03%、分支82.95%、FSM60.54%、toggle63.33%、Score74.81% | 正式740项，不包含未批准候选豁免 |
| 最新已核验豁免报告 | 同一740项应用六策略5808点及snapshot24；i_system条件82.04%、分支87.70%、Score75.76%，行/FSM/toggle不变；实际save/reload/reset及11个rooted scope核验通过 | 已应用5832个精确点；不代表新RTL signoff，不声称全2989层级fresh |
| 已核验限定候选豁免报告 | 历史723项六组策略报告原始分支82.89%、应用候选策略后87.63% | 仅代表723项，不套用到737项 |
| 735项候选豁免DVE汇总工具 | v8实际audit/prepare/check通过；组合原生runtime已启动一次，但最终资格尚未完成，按用户暂停要求保留现场并停止，不应用到740项报告 | 未批准，未纳入本次百分比 |
| AKV descriptor同ELF预算补跑 | 原6751检查PASS；相对738实际line/cond/branch/FSM均零增量，保留功能记录，不重复VCS | 否，无新增覆盖增益 |
| AKV skew_context同ELF预算补跑 | 原3237检查PASS；相对738实际line/cond/branch/FSM均零增量，保留功能记录，不重复VCS | 否，无新增覆盖增益 |
| R1窄化拒绝矩阵 | 严格差分PASS，44/45目标命中；相对722新增line15/cond14/branch15，已正式准入 | 是 |
| GAP104 whole-register保留NF | 父侧严格重放PASS，新增line2/branch2，已正式准入 | 是 |
| 新LZC候选豁免 | 60个条件点原生选择/保护核验通过，补充padding四态源证明；60个分支HOLD，合并应用仍待验收 | 否 |
| 历史RTL失败/未闭环差分 | 记录保留，本轮不修RTL、不纳失败VDB | 否 |
| GAP109 QBS K2累加sticky | 完整software/native PASS，v2精确FMA/LZC参数绑定通过；父侧独立6162实例OR确认新增cond2，正式732已准入 | 是 |
| GAP110 Q3 R4尾块 | 软件/native完整核验PASS，独立raw及compiled核查新增35个条件点、26目标全命中；v2完整准入及独立重验通过 | 是，正式734；不是新的DVE百分比 |
| R2 vector-memory EMUL边界 | VILL/VL0下两条普通load/store未产生非法指令异常；保留FAIL，不修RTL | 否 |
| AKV生命周期v2 | 完整独立检查通过；相对723新增line3/cond4/branch3、四目标全命中；已正式准入 | 是 |
| GAP105 QBS M8跨字边界 | 独立检查器v5完整核验通过；相对724新增191条件点、12个目标全命中，已正式准入 | 是 |
| Indexed restart同组index/destination | 457项自检及独立架构对比PASS，但相对724的line/cond/branch/FSM增量全部为0；原目标误把MaskM6当作索引端口，正确端口为SlideAddrGenA8 | 否，无新增覆盖增益 |
| MaskM6/StA7 snapshot豁免 | 24cond源证明、原生导出/重载及两次独立核验通过；已随5832点应用到740项报告，8branch保持HOLD | 已应用限定24cond，不排除其他邻点 |
| VNCLIPU宽度/源组对齐拒绝 | 源保持后继真实核验PASS；新增line2/cond1/branch2，五目标全命中；精确725前缀及6162个metric instance OR父侧独立核验通过 | 是，正式726；原检查FAIL保留 |
| GAP106 QBS正无穷scale | 独立受限software/native核验PASS；相对726实测新增line8/cond33/branch9，7192个pin无漂移及6162个metric instance精确OR父侧核查通过 | 已正式准入727；不宣称完整标量ISA/Spike custom验证 |
| RVH关闭配置分支豁免 | 完整247条原生记录及1533个保护点的五阶段核验、父侧独立verify通过，最终空EL完成 | 仅限定原生资格通过，未应用总汇总 |
| LZC七组汇总环境恢复 | 已失败退出；原生绑定数组误加载为初始化函数局部变量，父侧纯Tcl复现通过；封存输入724项，最终空EL保留 | 否，本次汇总不得采用；准备仅修工具作用域的后继 |

用户在完成740项汇总和限定豁免后，重新授权提升FSM与Toggle。
本阶段保持旧镜像及740项集合不变，先对照编译shape、封存RTL和
已通过集合定位未命中的可达状态转换及信号位，再补短定向激励。
新增测试须独立通过功能核验后才可追加覆盖率；失败不准入，不修RTL。

## 阶段过程记录

### FSM与Toggle定向增量阶段启动

本阶段的比较基准为740项，FSM60.54%、Toggle63.33%；已新增
一项PASS，正式集合为741项；DVE及独立审计确认Toggle63.55%。分工分析系统PTW/cache、Dispatcher/segment及
QBS/RVV数据位，避开已有同类激励及已记录功能FAIL。

现有`coverage_bitmap_delta.py`默认只解析line/cond/branch/fsm，
不能据此宣称Toggle没有增益。新增Toggle诊断工具需要绑定真实
VDB位编码及shape，保留原工具不变；原始位增量不是DVE百分比。
每项激励应记录具体目标、可达条件、独立功能检查和实际目标命中。
不通过增加豁免或修改分母来冒充新激励的覆盖效果。

本阶段已完成两个真实VCS判别实验：

- GAP111同PTE缓存行交互：26项检查、11537条标量指令、3645次
  GPR写回及3561次完整访存检查通过，包含压缩指令和精确1次trap。
  全设计FSM原始增量为0，14个主目标未命中，碰撞假说未获证实。
  只保留`gap111-pte-line-qualified-agent-20261007-01`功能证据，
  不调布局重试、不增加正式集合，尚未测其Toggle增量。
- GAP112末RAM字FOF：Host/Spike194检查通过，但真实VCS在
  0x80200000读取处触发冻结TB的L2越界fatal（`ara_tb.sv:1454`），
  没有成功终点。退出码0不能解释为PASS，VDB不准入；不把这次
  testbench拒绝越界刺激当作已确认RTL功能错误。保留现场，先静态
  检查合法内存内的页故障是否适用，不直接放大RAM或取消检查。

740项Toggle的scoped并集已实际提取，绑定design层级、info及shape
checksum，输入未改；`targeted-toggle740-gap113-20261007-01.json`
涵盖profile engine和两个payload bank，744个input pins。它只证明
原始序列位置，不声称逻辑bit或0->1/1->0方向已经校准。

GAP113使用两组合法Q3_K/Q8_K数据模式，复用既有完整VRF、CSR及
源/guard检查；Host44检查和42个损坏负例通过。单次VCS实际CPU
374.650秒，DUT41项检查通过。父侧独立执行后验核验通过：8192字节
完整VRF、7328字节source/guard、24个CSR值及正常事务完成均核验。
资格结果位于`gap113-payload-toggle-qualified-agent-20261007-01`，
seal为`925fffaa27020ca24b697ad5f36cd5f74e813544ce3315a539df3c185cfdbd0b`。
相对精确740项，payload bank1实际新增2402个原始Toggle序列位置，
83个预定目标命中74个；bank0和integer profile scope无新增位置。
这里不是DVE评分分母，不把2402位置直接换算成百分比，也不声称
完整标量ISA或Spike custom QBS验证。已正式追加为741项，准入清单
位于`targeted-toggle-offline-admitted-741-parent-20261007-01`，seal为
`ad53b488eb12de7c8fe1a470d72c5a36dbea5cb349383dcf9c3c8068cebfb0f1`。
全设计line/cond/branch/FSM原始增量均为0；限定Toggle增量为2402。
DVE新报告已在独立目录导出，实际742个输入、741个测试身份及GUI
证据、2989行完整层级顺序、无豁免状态、空diagnostics和前后pins
独立核查通过。审计文件为`raw741-post-export-audit-20261007-01.json`，
seal为`95d08567d754ef6eb499e8a2aa2633def655b0e86e4384f6e24b0e6656ee6953`。
原始Toggle为63.55%（增加0.22个百分点），Score为74.86%
（增加0.05个百分点）；其他四项不变。旧报告和豁免不覆盖。

### 740项精确豁免已应用

用户随后授权继续应用豁免。独立复核六策略及snapshot24的冻结
源码/参数、编译shape和740位图适用性，共5832点，无整模块排除。
最终`point-only-5832-raw740-v4-agent-20261007-01`实际DVE终态及
save/reload/reset通过，result seal
`3e7e581606ae8a50fe0e5d8febb26ddeb0bb6114176ed62d02390c70d4bfbbda`。
system分支82.95%→87.70%、条件82.03%→82.04%，其他原始指标
不变；Score74.81%→75.76%。这是豁免分母调整，不是新增激励。
正式报告只采用11个实际rooted scope，原2989行全层级raw保留。
旧v2的环境警告及未刷新子层级报告保持HOLD，不使用其百分比；
v3未启动。原生EL保存到`waivers/old_image_reviewed_5832.el`，
适用性说明见`DVE_REVIEWED_WAIVERS_740.md`。没有新VCS仿真，
没有修改RTL，没有纳入失败案例或未批准的LZC/RVH等候选。

### 本波最终覆盖率与暂停

740项无豁免DVE报告：
`verification/out/final-raw740-dve-agent-20261007-01/summary.csv`。
以下均为`ara_tb.dut.i_ara_soc.i_system`同一层级；增量单位是百分点。

| 指标 | 上次737项 | 本次740项 | 增量 |
| --- | ---: | ---: | ---: |
| 行 | 85.19% | 85.21% | +0.02 |
| 条件 | 82.02% | 82.03% | +0.01 |
| 分支 | 82.93% | 82.95% | +0.02 |
| FSM | 60.54% | 60.54% | 0.00 |
| Toggle | 63.25% | 63.33% | +0.08 |
| DVE Score | 74.79% | 74.81% | +0.02 |

本波不修改RTL，不纳入失败/未闭环测试，不将历史723项豁免
百分比套用到740项。正式覆盖率统计结束后暂停，下一批激励和
未完成的历史735项候选豁免核验等待用户继续指示。

本波最终正式集合为740项，准入manifest seal
`752d493c5fa8179ddd414d7810da479b1a56341a1600dff56c5b5afa0a3304b5`。
737之后的三项累计新增原始覆盖点line23/cond20/branch22/FSM0；
这些是位图增量，不是DVE百分比的分母或百分比增量。
CSR单次仿真28.30秒，54项检查、416观察字节及完整标量差分通过；
queue-mask单次仿真386.70秒，6936项检查、6912定义内存字节、
24个CSR值、32条原生向量写入核验通过。720个mask活动位严格
比对，7472个mask尾部位按ISA允许集合核验，不强求Spike尾部
选择一致，也不跳过整个目标寄存器。队列测试新增四lane VRF
仲裁条件点，原source-lifetime等待cond665四点未命中，不能称
该等待场景已覆盖。两项零增益AKV补跑继续保留功能记录但不准入。

组合候选豁免runtime_v8父侧全文审实现和tests，实际11项
接口测试PASS（0.060秒、零skip）。保持固定历史735人口、
7684精确native target、19566已审保护点、41214 QBS条件
complement及六阶段27250-point检查；原有Tcl未改，采用成功
final v8 reader和owner-bound backend。测试只是接口资格，
不是actual prepare/verify/native GUI/application批准。
成功host reader后将一次bounded原生核验安排后台，不再
创建重复reader版本；同时仅静态筛选可达FSM零转换，不盲跑。

CSR完整terminal collector父全文审查，实际27 tests PASS
（0.766秒）；父实际collect --with-raw成功，qualification seal
`a103410e06f2f737f3335fbfc66c484500d6db19207026a969a529077049813c`，
输出`csr-frozen-counter-qualified-parent-20261007-01`。
54checks/416观察字节、完整782/434/203差分、独立counter CSR
状态、ELF guards、零backend及日志/OS终态/全部pins均通过；
vector明确`UNOBSERVABLE_ZERO_DESTINATIONS`。实际raw新增
6line/4cond/5branch/0FSM、7目标全命中，6162instance shapes核验。
尚未正式准入，准备直接封存738精确前缀OR的739集合，
不再重跑VCS、不额外建立重复candidateplan。

queue唯一DUT终态exit0、wall386.697858秒、timeoutfalse。
父独立核对6162实例和compile/source/raw前后SHA：相对738
实际新增cond4，line/branch/FSM均0。原四lane requester cond665
均未命中，明确不称source-lifetime stall已覆盖，不调参重跑。
四个真实增益均位于每lane的
`i_operand_requester.gen_vrf_arbiters[0].i_lp_vrf_arbiter`：
cond raw135、width166、checksum845025520、native condregid54、
vector110，源码`rr_arb_tree.sv:264`（level2/l1右端grant门控）。
父确认源码SHA `f72bc188ea8253230a722bfb6436ab31b6e41c26020fa4ba4eebd93025984f7e`
与冻结build一致。这是实际VRF仲裁条件增益，不是原665目标；
完整功能核验后可按真实增益评估准入，当前不提前计入738。

CSR终态父独立运行generic严格scalar差分，实际结果
`TERMINAL_TOHOST_MATCH`：782条完整指令、434 scalar writes、203
memory accesses、零trap、零skipped values、mismatch=null，
终态tohost=1。matched scalar state SHA
`c4ffb0ca80a0fe96afc6b47f83db8f54691f679ee69b9c303987dcc31f57755d`。
仍须collector封存独立CSR/gold/guards、zero-vector lifecycle与
输入输出完整性，不将generic scalar match误称全ISA/signoff。

CSR单次DUT真实结束：exit0、wall28.301076秒、timeoutfalse，
console仅SUCCESS，CVX requests/responses/exceptions/protocol_errors/
outstanding均0。父侧独立核对compile design SHA、6162个metric
instance的width/checksum及四raw数据文件读取前后SHA。
相对738的i_system实际新增line6/cond4/branch5/FSM0，七个
primary（line275/578/585/589、cond90/92、branch202）全部命中。
这是实际覆盖增益诊断，不是完整功能资格，仍待782条完整
scalar/CSR/memory差分与54项独立gold及guards验收后正式准入。
初次临时诊断命令使用宿主Python不具备的int.bit_count失败，
仅改诊断为bin.count后成功；没有修改输入/镜像或重跑仿真。

v8最终reader实际audit/prepare/check均exit0，父侧读真实
`.v8-check.log`并核对reader/plan/log SHA：reader
`6726724968e288afd3602d757900ac197a06395351e2e8c62d8e3eb2d25fe970`，
plan seal `e6cf29a9cb6fb147f8e46afce582920bfa9bee007d565bf040070e6801aaf7f1`，
check log `e4b0f3b207278f3ee3e99617bda8a7e608a5d3e2dcf1c2054100e040dff19fc0`。
实际状态`PREPARED_HISTORICAL735_EPOCH_CHECK_PASS_NO_DVE`：8768
literal pins、8757 endpoints、59 parses及2509220703字节fresh尾部
hash；不是新的覆盖率百分比、不是豁免应用批准。组合runtime
接入固定reader再验收，不重跑此前已完成的1792原生资格。

CSR runner父侧全文审核并实际13 tests PASS（9.807秒），
prepare162pins成功，prepared seal
`dfff44ebf7f75e79dba389f4a034daca60bb650e3c810e9e92f258f5e555a95e`。
唯一parent输出`csr-frozen-counter-old-image-738-parent-20261007-01`，
systemd unit `ara-csr-frozen-counter-738-parent-20261007-01`。
父确认launcher3487123 active/running；120秒VCS/180秒unit，
参考完整782条指令、434个scalar writes、203个memory accesses。
启动前需原封存核验，不预先称DUT通过/7目标命中，禁止重跑。

queue mask尾部逐位oracle父侧已全文审实现及集成计划，实际
13项测试PASS（0.463秒）。覆盖全部有效位翻转拒绝、tail old1
不能清零、old0可置1/保留、v9破坏、未证实prestate、未知
native写以及保留实际DUT tail的identity transport。该helper
尚非完整逐请求终态collector，不能替代32个primary writer及
额外transport、scalar/memory/CSR/lifecycle/raw增益的集成核验；
已安排继续集成，不修改generic comparator、不用整vd跳过。

CSR counter-freeze新刺激父侧全文审核C和preflight，实际12项
测试PASS（6.786秒）；随后独立核验manifest seal
`ea8b192a08e8bb131a5e3d4f094626b3393f7caad47a1f35ea672b84916220ab`、
所有input/output pins、完整Spike轨迹重放及冻结738目标绑定。
结果54 checks、416观察字节、16 CSR单元、零trap、7个fresh
目标（4line/2cond/1branch）。CY/IR全程冻结后比较显式种子值，
不把不同平台的运行中计数器当严格gold；最终清零再解除抑制。
软件预检不是DUT通过，runner尚待封存及父审，不提前准入。

queue单次DUT已确认真实启动：started.json绑定sim PID3483063、
launcher3481992及已批准ELF/image SHA；父侧`ps`确认sim进程存活，
commit_trace.csv已产生249856字节。启动前封存核验完成；现在等待
终态独立差分及覆盖增量，不再频繁轮询。

v8真实完整role audit已结束并生成诊断seal
`10d93e7a4a469acd6a6390fce7a020230e5ba656622e9203ff5cb901cbd79d38`。
原声明消费1260524065字节，实际消费624402360字节；状态为
`MEASURED_ROLES_DIAGNOSTIC_NOT_REPORT_APPROVAL`。最终v8 plan已生成，
还须真实check及父侧验收，不提前作为豁免应用成功。

queue mask tail修正后父侧全文审核软件、preflight及runner，
实际27项tests全部PASS（22.662秒），独立封存verify输出
`VERIFY_PASS_NO_EDA`。批准唯一prepared seal
`b45a190d4441fe9c4573aadad51dcd3a670679ff1281fd2bea76a930e4b31d7c`，
以systemd独立unit `ara-queue-mask-source-lifetime-738-parent-20261007-01`
启动。父侧确认launcher PID3481992持续CPU执行，启动前仍核验
全部封存输入；尚未看到started.json时明确不称VCS已经执行。
预算600秒、unit660秒，目标四lane cond665/vector010；有效mask
720 bits严格检查，7472 agnostic VRF tail位按ISA允许集合处理，
非目的v9/source/div/guards继续严格。等待一次DUT和实际raw增益，
不自动重跑、不因软件预检通过而准入。

v8限定工具角色与尾部fresh hash修正后的真实audit已启动。
父侧通过`ps`确认PID3477724为目标audit进程，STAT R，elapsed
4分34秒、CPU累计4分23秒；通过`/proc/3477724/fd/1,2`确认输出
独立保存至`eight-policy-semantic-735-agent-20261006-02.v8-tail-tool-audit.log`，
没有覆盖此前失败的`.v8-audit.log`。这是运行中证据，不是终态
审计成功或应用豁免批准；不重复启动、不以文件存在推断完成。

v8限定工具读取及fresh尾部核验父侧实际补验通过：
`TailHash`与`WorkerBoundary.test_real_nested_tool_revalidate_has_only_fixed_roles`
两项测试PASS（10.810秒、零skip）。只允许四个已封存工具路径，
保留ELF头与streaming identity检查；阶段末每个端点仅fresh hash一次，
检查重复执行拒绝和缓存SHA不能绕过尾部核验。未将工具测试当作
完整role audit成功，仍须真实audit/prepare/check后才能运行候选豁免。

父侧实际统计v8历史source_plan：8754个pin路径，总文件大小
2995746794字节（按路径计数，包含工具软链接别名）；六个
worker若无缓存，每次全量pre/post重哈希的上界为
35948961528字节，不是实测I/O。较大项
包括192MB Spike、144MB clang别名及多份114MB历史config。
代理实际测得首轮25.93秒，8743端点各hash一次；同phase
再次复核8.06秒、新增hash/read为0，现有实现已缓存端点SHA。
后续开销主要为路径/identity复核。现有finish只做identity
复核，不称为fresh尾部hash；准备阶段尾一次去重streaming
hash，保留worker及固定源约束，不反复重哈希无关工具。
该统计用于工具效率，不代表覆盖率增益。

PTW完整终态父侧实际collect通过，qualification seal
`f74ca68558d757af7f9f549eeae3a3c588eb8faf709ffe71d31ab181ded0a9f4`，
目录`ptw-sfence-boundary-qualified-parent-20261006-01`。逐条
scalar/RVC memory/CSR/两次精确trap及35项数学输出检查通过；
vector保持零目的请求UNOBSERVABLE，不伪造向量PASS。collector
24项测试父独立PASS（7.295秒）。因全部raw零增益仅保留
功能记录，不增正式738集合。

下一普通RVV候选为四lane operand requester cond665纯
source-lifetime stall。初版软件已通过Spike，但父审指出
mask目的tail即便tu也可agnostic，不能将Spike留旧字节
选择当作架构必须行为；要求首个DUT run前分清active mask
严格检查与agnostic tail、保留非目的reg/source/div/guards
严格检查，再封存软件预检。不因合法tail差异误报RTL bug。

PTW单次run真实终态exit0、wall90.666秒、未超时。父独立读取
新FSM VDB并与738比较，35位/checksum3345966803一致：
raw21和raw25均未命中，PTW全部FSM新增0；data SHA
`9cbbc5f5bc228d753aa7b28ce262e88ab0609000479003a3537b3b3f31d7ed30`。
父进一步核对全部6162实例的width/checksum及四文件读取
前后hash：相对738，全设计及i_system的line/cond/branch/FSM
增量均为0。这是诊断，不是完整功能资格；继续差分收尾，
不准入、不开发额外准入工具、不调布局重试。

v8固定worker边界父侧全文审源码/tests，并实际3项测试PASS
（192.029秒）：真实六组exact bindings/dependencies、封存
输入不可写、临时派生文件清理、未知dependency/worker拒绝。
仍需真实完整role audit及prepare/check，不提前应用豁免。

PTW单次判别run已由父侧启动systemd独立任务
`ara-ptw-sfence-old-image-parent-20261006-01`，VCS硬预算300秒、
unit外层360秒、整进程组超时清理、无自动重试。最终runner
17项测试PASS（3.184秒），实际prepare177pins通过，seal
`dab42b9f65171af71a64127d711b9f33bd3304d3ef5d25aed77ea3fdec53c943`。
运行目录`ptw-sfence-boundary-old-image-parent-20261006-01`。
首次prepare期间runner并发编辑触发pin拒绝，未启动VCS/产物；
待代理明确冻结后重新审查/prepare成功，未放宽完整性门控。
run尚未终态验收，不计入738、不宣称目标命中。

组合候选豁免runtime_v7父侧全文审代码及测试，实际10项
接口测试全部PASS（0.052秒、零skip）。helper SHA
`fb765a9d2b2368acb56cb8221833c41f9331217da01bf988738c269abe566dc4`，
test SHA
`82a649e28209ee1c262e6a249c5cd2e833a8cb46d8ef8c433dfb5d6ab787b23f`。
终态使用owner-bound backend并拒绝合并pin冲突，人口固定
历史735、原Tcl未改。此次只有接口级验收，没有真实reader
闭环、prepare或DVE运行，不据此应用豁免/宣称覆盖率提高。

PTW页边界SFENCE软件预检已由父侧独立审核源码、执行9项
测试PASS（0.006秒），并按固定seal重新检查全部输入/输出
pin及原Spike trace：35检查、160字节输出、64字节trap记录、
两次精确S-ECALL通过。预检目录
`ptw-sfence-boundary-preflight-737-agent-20261006-02`，seal
`0d1c7cb868f77d68fb5c5350a15c94c6171fa8e5c81891cc740c4e93441b3b9e`。
已核实SFENCE经controller.flush_ex到PTW.flush_i，年轻Iwalk
可并行但raw21/25控制窗口未实测。安排同ELF一次最小判别
仿真的runner准备；无增益不调布局重跑，预检PASS不冒称
RTL覆盖增益或正式准入。

v7真实role audit已执行到历史six-policy bindings，随后因
invoke的临时config写入被只读Path拒绝而退出；这是工具的
临时派生文件权限边界，不是RTL或测试失败。invoke还启动
固定worker子进程，需分别验证其返回binding/dependency及
封存输入，不能只放开写权限便宣称全链读取受控。保持历史
输入不可写，先静态盘清临时读写/子进程边界再修。父侧另
独立复跑v6历史闭包10项测试全部PASS（3.786秒）。

738实际raw复核：load完成碰撞cond1052/1061/1058/1067
已经命中；普通store候选缺少可达依据，两条都不启动试跑。
转向普通RVV队列与冷PTW刷新仍零覆盖点的合法场景。

735 reader v7根因修复后，父侧实际重跑16项测试全部PASS
（16.114秒）：嵌套PROOF/config/compiled XML受控读取、
未知文件拒绝、解析后捕获内容释放、原始模块未修改及三阶段
读取均通过。仍需完整历史输入role audit及实际prepare/check；
单元测试通过不等于豁免DVE报告验收，不提前应用豁免。

735 reader后继v7父侧独立执行16项测试（16.188秒）：3项FAIL、
1项测试API ERROR。静态定位同一工具根因：namespace先安装
受控Path/json，随后全量复制原globals又将其覆盖；因此嵌套
context.Path绕过pin检查、Design读取未记录、json解析未释放
捕获内容。要求在复制完成后绑定受控接口，并保留原有拒绝/
完整性断言；另修当前unittest无assertIsNotInstance的API。
候选豁免DVE仍不启动，737原始报告不受影响。

下一批完成碰撞候选的静态检查：当前segment_sequencer和
ara_sequencer的SHA均与旧镜像build-source-pins一致；封存
compile.command.json配置store_b_ab_baseline=0，因此使用
WaitForStoreB=1。sequencer要求store完成后才返回响应，
dispatcher在WAIT_STORE_RESPONSE收到响应后才恢复解码。
简单store、vset VL=0、零长度访存序列不能保证与短暂的
store_complete_q重合，不据此启动试跑或宣称该覆盖点不可达。
下一步分别检查load异步完成窗口及冷PTW walk/SFENCE的
精确刷新窗口，只对有可达性依据的方案做独立预检与短仿真。

QBS1792+原8组组合runtime父侧全文审Python/Tcl/tests，实际
8 tests PASS（109.846秒），含六阶段及重排multiset、邻居/
reset/annotation/额外条目失败注入。主机边界stub不代表
实际DVE组合验收；仍等修复后的735受控reader，不应用豁免。

两项历史AKV预算补跑相对正式738的离线增量均为line0/cond0/
branch0/FSM0，同旧镜像/ELF/原oracle记录保留，不重复仿真
也不新增覆盖候选。诊断文件
`historical-akv-gap35-gap46-rawdelta-738-agent-20261006-01.json`。

clip17已正式准入738，prepared seal
`6987742befedafdc2017ebce405633435ac6e4d3f73baa0cce7bc13a62c45cd8`，
admission manifest seal
`972d4dec87035fb12343d25305666a8d9c5a88ea8215ef330638e468386249f7`。
正式目录`clip17-offline-admitted-738-parent-20261006-01`；全部
旧737前缀、6162实例OR、完整功能资格及42目标检查保留。
不修改RTL，不纳300秒超时VDB，不声称738新DVE百分比。

父侧全文审raw737持久回执复核代码，并实际执行复核PASS：
737测试/2957 pins/2989层级行。回执seal
`d99b1a3e1146d736f42c428ec7a92ef15fcf6fd9e2b6e314f10aa613af795a35`。
原始报告737百分比可用；仍不代表完整signoff或豁免批准。

clip17实际raw gain完成：相对正式737新增line17/cond12/
branch17/FSM0，42预定目标全部命中。候选seal
`a63daa0120ddf15547ab929a6fd7ec438d6bc000a68fc12178fdd335285c685f`。
父侧使用独立JSON/整数运算复算全部6162实例的宽度/checksum/
OR、精确737前缀和738唯一测试，实测增量一致。初次复核
命令因本机Python缺int.bit_count失败，改用bin.count后
独立复核通过；未改任何输入文件。正在prepare-admission，
正式集合仍737，不能提前称738或更改737报告百分比。

clip17准入工具父侧全文审核及13 tests PASS（1.201秒）；
实际prepare-gain完成，plan seal
`aaa3ce21799ab73c129cf30e3cff96d0eb4b223a4bbe3cf900d0fb51d0609689`，
目录`clip17-gain-plan-737-parent-20261006-01`。正在实际
collect-gain；保持正式737，不提前称738或新百分比。

737最新层级报告显示较大可检验缺口：四lane operand queues
分支53.92%至54.91%、slide/addrgen queue33.33%、store/mask
queue34.81%、CSR分支45.05%、PTW45.98%。dispatcher已
95.41%行/88.78%分支，QBS98.60%行/95.35%分支，AKV95.55%行/
96.95%分支。下一批优先查上述普通RVV/系统侧可达缺口，
不再仅依赖非法编码小增量；低覆盖本身不构成豁免理由。

clip17完整实际collect PASS，qualification seal
`990f68434c1a2caa0c9d4902ad5bc972abb072c843226187662d033f295f1007`。
2094检查、17精确trap、33正常向量写者/4100字节、完整scalar/
memory/CSR/三组VRF快照及每非法owner零backend/native通过。
原300秒TIMEOUT保留；450秒补跑321秒结束。仍需计算相对737
的raw增量并正式准入，不提前称738。

737原始DVE任务实际退出0/inactive，summary.csv完成，
diagnostics.txt为空。i_system导出行85.19%、条件82.02%、
分支82.93%、FSM60.54%、Toggle63.25%、Score74.79%。
这是无豁免报告；selected计数737，仍待逐身份及输入前后
漂移独立核验，暂不替代顶部最新独立核验的723报告。

clip17同ELF450秒补跑真实结束，returncode0、wall321.112826秒、
timeout=false，尚未准入。修正工具API后父侧38 tests PASS
（11.420秒）；新独立qualification plan02 seal
`c4e45acf7793251ea058481ec94aba322e56747ec0db379ecdf98bfe3c0ce906`。
完整collect已启动，输出计划
`narrow-clip-reject-450-qualified-parent-20261006-01`；只有
完整架构核验及相对737的真实raw增量通过后才能纳入。
737原始DVE汇总已生成selected_tests.txt，计数精确737；
仍待全部导出及身份/诊断/源文件核验，暂无新百分比。

737项独立原始DVE报告已启动，unit
`ara-737-raw-dve-parent-20261006-01`，输出
`raw-dve-737-parent-20261006-01`；限时600秒/service660，
明确DVE_WAIVERS=off。现有导出脚本父侧已审；正式输入seal
`8299c0f8c4ebadef0359a4f23988f76d0540d2b7fe7a6bcbd14b6fa6a827a787`
与737 admission output_pins一致。尚待完整输出、精确737
selected tests及零诊断/输入前后无漂移核验；不能称最新
百分比已完成或最终审计批准。

clip17实际verify暴露工具API错误：verify_plan使用三参数
life.merge_pins，但该函数仅接受两参数。prepare计划保留，
不得称verify通过；应嵌套二参数合并并补真实路径测试，再
生成独立后继计划。不影响450秒VCS或更改结果容忍。

450秒collector已父侧全文审查，实际35 tests PASS（10.944秒），
exact450 profile绑定后继runner/test，不接受任意预算。实际
prepare完成，plan seal
`846b969babc78f7db835992782548dcec982194e30bd8e33b4be1c3c17975f44`，
目录`narrow-clip-reject-450-qualification-plan-parent-20261006-01`。
正在verify配置；真实VCS PID3420541确认运行，尚未终态。

准备737项无豁免的独立原始DVE汇总，避免最新原始百分比
被候选豁免工具阻塞。正式combined-inputs共738行（1编译+
737测试），admission manifest SHA保持
`bd0ee8b3f52627578b120eb97109d7efc40a6e44466867f3d816ca2ec35a12ad`。
必须核验selected tests精确匹配、无拒绝/诊断及输入前后无
漂移；尚未启动报告或宣称新百分比。

450秒补跑已由父侧启动，prepared seal
`2e7cac11b8c42b8cf1c514f8cb41fd695753927ec154e11c61cfa82d03ffeafe`，
unit `ara-clip17-450-old-image-parent-20261006-01`，launcher
PID3420160，服务确认active/running。仍须完成终态架构核验
和相对737的raw覆盖增量，不计入正式集合。

同ELF450秒补跑程序父侧全文审核，8 tests PASS（41.189秒）。
后继绑定原300秒超时/启动/原始trace及日志，保留全部原pins；
私有预算450、service上限510，不改原runner/ELF/旧镜像。
正在prepare独立目录`narrow-clip-reject-450-old-image-parent-20261006-01`。
尚未运行完，不计入737项或宣称覆盖增益。

父侧继续定位735读取失败：source735v3的pins中，CAPTURE目录
仅登记groups.tcl/inputs.txt/readonly-evidence.json，未登记
mask.read_config实际读取的config.json与first.el。
历史config实际SHA为代码固定的
`79d3fab018b585106a88ff50cfa6bf4ba1a143051422a19598602a03fa99c7b5`，
first.el实际SHA为
`c11b89f8ae115a50c83bd409d57d003c768991ae589656c021c5209cdb9f44a8`。
后继应补齐独立历史权威文件的传递闭包，保留原plan，不能
把未知读取放行或改历史pin。

clip17统一collector增加OS回执/PID/预算绑定、逐退休ELF
opcode核对、33正常写者及精确4100写回字节门控。父侧全文
审核新增逻辑及gold/error-injection测试，实际33 tests PASS
（11.073秒）；尚未验收真实成功终态，不计入覆盖率。

clip17首轮300秒达到wall timeout，OS returncode -9、进程组
清理完成、post_failure_pin_error为null；未纳入覆盖率。
commit尾部为cycle120662/retire order73116，参考73304条，
说明已接近软件终态但不能以此宣称功能PASS。准备同ELF、
同旧镜像的450秒后继，不改RTL或激励，不改历史运行证据。

735 audit持久日志已获得真实失败栈：snapshot_binding调用
mask.read_config(CAPTURE)时触发Unknown/conflicting pin。
应静态查明历史配置链的路径/声明绑定缺口；不能绕过校验、
替换历史文件或使用失败报告百分比。未启动DVE。

clip17未封存collector已修正Counter(starts.keys())，并补全
事件守恒、非法owner零backend/零native、完整VRF读回、trap
ledger、CSR与UVM/contract失败注入。父侧实测26 tests PASS
（1.076秒）；仍须补齐执行回执/ELF绑定并核验真实DUT终态，
工具测试通过不计作新RTL PASS或覆盖增量。

735 reader日志通道缺陷已用小型非audit探针确认：旧等待循环
丢弃中间输出块，仅保存终态块；原exit1的真实诊断无法恢复。
证据`eight-policy-semantic-735-agent-20261006-02.v5-channel-findings.json`。
父侧核验v5及test SHA未变，启动原程序一次有界观测，unit
`ara-735-v5-role-audit-observed-20261006-01`，限时600秒，
stdout/stderr直接持久化到
`eight-policy-semantic-735-agent-20261006-02.v5-observed.log`。
这是已确认日志采集问题后的观测，不放宽校验、未启动DVE，
实际审计退出根因仍待终态日志。

clip17终态检查器静态审核发现工具问题：lifecycle将starts字典
直接用于Counter，字典值会被视作计数，而非每个owner计数1。
应改为Counter(starts.keys())并增加完整事件守恒正负例。
另外v2测试因尚未定稿的前继源码SHA不一致失败；尚未封存
collector，不放宽检查、不修改执行runner。两者均为工具问题，
不是实测RTL失败；正在运行的VCS无需重跑。

clip17运行器父侧全文审查及12项实际测试通过（17.336秒）。
已启动一次有界旧镜像VCS，独立目录
`narrow-clip-reject-old-image-parent-20261006-01`，
prepared seal `7e5095088a6e15fd7108d3ee11a658dc709f2cf121b7084435ca18000205acdb`。
systemd unit `ara-clip17-old-image-parent-20261006-01`，
launcher PID3408345、VCS PID3408824；预算300秒、整个服务360秒。
确认started记录及VCS coverage初始化；尚未完成独立终态核验，
不计入737项、不宣称覆盖率增益，不改RTL。

735 reader v5 actual audit已失败退出1，未生成审计JSON，执行通道
没有返回诊断文本。终态回执为
`eight-policy-semantic-735-agent-20261006-02.v5-role-audit-terminal.json`。
退出根因尚未建立，不推断OOM，不自动重试；尚未启动DVE。

clip17矩阵软件预检已父侧实际验收：全文审APP/header/host/
preflight及两组tests，22 tests PASS（7.797秒），实际verify
PASS NO_VCS。目录`narrow-clip-reject-preflight-737-agent-20261006-01`，
seal `f0fc1ee53df6af7c7a1b78df9ff2aa5bb4655dc2c805268dcce32606a3b7576e`，
ELF SHA `a0cb0f491a8cee459b93855138db8cc961a5eda74a35caea9bde5854a57a6f04`。
Host/Spike2094 checks、17精确trap、73304参考instructions及tohost1；
全VRF快照12288字节、guards1536字节。737静态目标为17line/
12cond/13branch，尚不是实际DUT增量。一次300秒旧镜像runner
及逐owner zero-backend/native资格检查器正在并行准备；尚未
启动VCS、未计入正式737、不改RTL。

735 reader v5已父侧全文审helper/tests，实际8 tests PASS（0.095秒），
包含真实snapshot.BUILD读取、普通Path绕过拒绝、未声明JSON
拒绝、原模块不变及私有命名空间常量绑定。冻结helper SHA
`ba63bdef94a7e778e6d6bdb8fe39779c071247e302e116c47e70dfc455b89431`，
test SHA
`03cbed6c446d80e8b0c09a29b13e7214073c65d51201f1859cf7ee06d18e4f73`。
actual audit PID3400615确认Rs、97.2%CPU运行，不重复启动；
这是读角色审计，尚非DVE百分比报告启动或完成。

窄化矩阵的环境风险已在源码修正：不再转换verify_elf函数，
signatures/validate仅允许冻结精确AST位置和计数的尺寸常量
改变；父侧实际header_audit+oracle_functions检查PASS。
17单元、2094软件检查，每单元恰一种独立拒绝原因（宽源对齐、
EMUL16或EEW128），不执行合法窄化计算；仍待完整host/Spike
预检和旧镜像VCS，未计入737。

父侧重新实测既有私有常量Path桥接的2项测试PASS（0.002秒），
确认snapshot.BUILD受控读取且原模块/检查方法不变。735后继
仍开发中，尚未实际audit/check通过，不能宣称报告后台运行。

矩阵预检初审发现环境检查器风险：oracle_functions中的宽泛
AST常量替换还包含verify_elf，PCs的literal2->18会误改ELF类别
常量2。该备用转换入口不应保留，须使用独立verify_elf仅精确
变更fault/recovery PC总数25->18，signatures/validate只变矩阵
维度。已要求先修改并增加回归再Spike预检；这是工具风险，
不是实测DUT失败，不修RTL、不计入覆盖率。

既有八组EL与新QBS1792的静态合并审查完成：父侧全文审helper/
tests，6 tests PASS（21.621秒）；actual prepare输出
`qbs1792-eight-merge-review-parent-20261006-01`，seal
`4ef6743caa8787085081e9019a60aaf024b51880d04a2da5ec3ba65231a22b87`。
5892+1792原生identity互斥，期望合计7684；共享payload scope中
旧组是Branch、新组是Condition，不能仅按数字ID判断冲突。
旧729八组失败报告仍HOLD，仅作为EL参考，尚无新组合原生
阶段验收，不应用豁免或更新百分比。

735 reader下一处工具根因已静态明确：冻结base Context内
snapshot.BUILD为普通Path，绕过capture后被严格JSON parser
拒绝。已有`eight_policy_epoch_732_report_v4.py`的
bind_constant_paths私有桥接可供适配；需在735 CatalogContext
调用链全面检查普通Path常量，保持方法体和原模块不变，不放宽
捕获/哈希/JSON约束。原v4 actual audit失败保持，不能当作汇总
已启动。本阶段v4工具18 tests PASS仍不足替代actual audit。

QBS1792原生资格已由父侧封存独立manifest：全文审seal helper/test，
4 tests PASS（11.561秒），actual prepare输出
`qbs-full1792-qualified-parent-20261006-01`，manifest seal
`8d495aa66f024d82ce27fcf50ecd646e91388e3c4b1474b9454301fdc0e10565`。
171 pins包含实际执行回执、五阶段、原生identity+annotation
multiset及空EL证据；final_application仍false，不改百分比。

后续普通RVV定向矩阵已开始源分析：合并VNCLIPU/VNCLIP的
wv/wx/wi源组对齐及宽度超界拒绝点。736静态候选上限13cond/
18line/14branch，必须先扣除737新覆盖点，不能当作实测增量。
每单元独立opcode/合法性、cause2/tval/EPC、全VRF/CSR/guards
保值及零backend/VRF非法活动，末尾合法vadd恢复；先Spike
预检、审核ELF，再有界旧镜像VCS。不触碰合法窄化已知风险
或改RTL。

窄化源组非法对齐拒绝已正式纳入737项。actual prepared seal
`7c22b0a7144fc65d5fa93ce6bf792fbc21694bab00f2cb87a900da9799b56c19`，
actual admit输出`narrow-source-group-offline-admitted-737-parent-20261006-01`，
manifest seal
`bd0ee8b3f52627578b120eb97109d7efc40a6e44466867f3d816ca2ec35a12ad`。
2130检查、2112内存字节、1032已知native写回字节、精确cause2/
opcode/tval/mepc及非法请求零backend/VRF活动检查通过。
独立6162实例OR和精确736前缀核查通过；新增line1/cond1/branch1，
不含FSM增量、不声称最新DVE百分比、无RTL改变或重仿真。

窄化增量父侧进一步核查compiled source mapping：line raw407
对应冻结dispatcher1966的illegal_insn赋值；cond raw224是同一行
源组8寄存器对齐拒绝true。branch raw1036对应编译branch group25/
native vector93，是完整arch_decode分支向量，不能称1966局部if
的独立分支覆盖。映射所用冻结dispatcher SHA
`9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43`。
父侧已全文审正式admission helper并14 tests PASS（0.012秒），
实际prepare开始；正式集合仍736，准备不等于准入。

QBS full1792 multiset后继真实DVE已终态：service inactive/dead，
ExecMainStatus0；父侧直接执行封存plan verify及完整inspect PASS。
1792条原生identity/属性/annotation准确对应，before/selected/
reset/reloaded/final五阶段3584项逐项核验通过，41214保护点和
initial/before/reset/final/cleanup五个空EL要求通过。
输出`qbs-full1792-native-multiset-v2-agent-20261006-01`，plan seal
`15511391e5bc9295eee799e20e680be7e24c1498c930d05ed4a63b0e04e1b111`。
资格状态`FULL1792_NATIVE_MULTISET_SIGNATURE_PROTECTION_PASS_NOT_APPLICATION`。
仍仅是复位后settled legal-known控制条件下的源证明和原生资格，
不声称任意X/delta不可达，尚未应用总汇总、不改变百分比。
原byte-order失败目录继续封存HOLD。

窄化源组非法对齐actual raw collect通过：父侧全文审gain helper
并18 tests PASS（2.430秒），实际plan seal
`6693e705bbce1fa15e3679d83408c4b5fb22455bdcacc14c8c274d9dc0273f38`。
候选`narrow-source-group-raw-gain-736-parent-20261006-01`，seal
`04869a7a3dc48b53748b9043b00a27fd63df6670b1cb1155b073801af4761541`。
相对正式736实测line1/cond1/branch1/FSM0，独立逐实例整数OR
6162项及精确736前缀检查通过；待正式准入，不先称737 PASS。

735百分比reader v3工具6 tests PASS，但actual check失败，
原因`Byte capture budget exceeded`，不是RTL测试失败。
父侧读取封存plan实测1581条byte_paths总计1190018776字节，
超过768MiB；仅root/six/eight各114036353字节的config即有
三份。准备收窄仅需内容读取的角色，所有pin/hash继续保留，
原失败不得作为有效百分比，不为此重仿真。

Sv39已正式纳入736项。父侧全文审核admission helper及10 tests
PASS，并用独立整数位图OR检查6162个metric instance、735精确
前缀及唯一singleton，新增条件点数与compiled/raw一致。
prepared seal
`6274a7556c76b322252dba81e00f3b8ebc2e7918b5db46f31b3d34a7a8265a9f`；
实际admit输出`sv39-masked-offline-admitted-736-parent-20261006-01`，
manifest seal
`a46222989c3c88436c5e2f431eaafa3b8790ffa9fa05bd65920dc695b6088784`。
新增cond1，line/branch/FSM为0，无RTL修改或重仿真，尚无新DVE
百分比。本阶段735百分比报告仍保持封存人口，避免每新增一项
即重建汇总；不得把其将来结果称为736百分比。

父侧完成Sv39实际raw增量核验：12项工具测试PASS，独立候选目录
`sv39-masked-raw-gain-735-parent-20261006-01`，seal
`c1ce44cb339df971da2c500ee75233192c0a904b170b0a69aa791bc6c89771e2`。
相对正式735实测仅新增cond1，dispatcher raw493/truth10命中，
line/branch/FSM增量为0。完整软件/native资格保持，待正式准入；
不把候选736当作已经准入，不把raw位数当作DVE百分比。

窄化源组非法对齐父侧完整terminal核验PASS：22项工具测试PASS
（11.804秒），实际collect目录
`narrow-source-group-qualified-parent-20261006-01`，seal
`1af00755d4aa0999255fd016de9ccc716b44e257646398805cf611a67e626189`。
2130软件检查、2112内存字节、1032已知native写回字节及精确
illegal trap/CSR/恢复检查通过；cond224与line407目标均实际命中。
尚未收集相对最新集合的合并增量，不计入正式735；无RTL修改，
无重仿真。QBS1792后继service当前MainPID3378885真实运行，
仍待完整资格核验，不批准最终豁免应用。

Sv39 v3完整terminal核验父侧实际PASS，未准入覆盖率。v2+v3
合计28 tests PASS（4.655秒），v3只修tuple owner判断，
完整gold/identity/CSR及原比较器检查保持；successor plan seal
`467b76fc3b8084a71e15ecf6ff7c50497d55995f253756992912860ac13e55b3`。
只读collect输出`sv39-masked-terminal-v3-qualified-parent-20261006-01`，
qualification seal
`78d388eec92293fe90c3aed832f5e8f9b8bc4812456b0bf5bcf00c332abffc0c`。
完整scalar/RVC/memory/native vector均PASS，105正常writers/
13321字节及128字节trap保值维护、异常与恢复全闭合；待735
实际raw gain及正式admit，不重仿真、不修改RTL。

窄化runner首次prepare发现工具误把image_inputs的66 runtime加
3 provenance共69pins视作66。父侧仅修runtime/provenance区分，
保留所有pins，加入缺少runtime/改hash/额外runtime拒绝测试，
9 tests PASS（0.014秒），真实prepare通过，seal
`fb12208a002dc3fb614ac539903edf64f5c8ef8b38d3ebd2953932b09f0c2a0b`。
service`ara-narrow-source-group-20261006-01`已启动，180秒sim预算，
独立目录`narrow-source-group-old-image-parent-20261006-01`，
当前真实simv PID3378049在运行；未准入。

QBS full1792排序后继父侧全文审读并实际10 tests PASS（60.847秒），
精确annotation/identity/属性multiset、重复拒绝及完整final-stage
要求保持，actual157pins及diagnosis核验通过。冻结新plan seal
`15511391e5bc9295eee799e20e680be7e24c1498c930d05ed4a63b0e04e1b111`，
父侧授权一次限定资格service
`ara-qbs-full1792-multiset-v2-20261006-01`，3600秒，无最终应用。
原失败HOLD保留；新目录`qbs-full1792-native-multiset-v2-agent-20261006-01`。
仍待完整真实五阶段及独立inspect，不宣称1792豁免已批准。

Sv39 v2实际collect继续HOLD，原因已父侧源码/实测定位为工具类型
错误：vector_commit._parse_architecture_mapping返回
starts List[Tuple[arch_seq,instruction]]，不是整数集合；v2的
`ARCH in starts`因此必为false。actual rejected集合恰为{243}，
不是出现额外拒绝或RTL数据失配。封存v2/helper/test/plan/result，
准备仅修tuple owner核对并增加真实parser契约测试的v3后继，
其余完整gold、identity、CSR和比较器条件保持，不重新仿真。

窄化源EMUL8不对齐拒绝候选已完成父侧静态与独立预检复核：
`vnclipu.wv v24,v9,v20`，cond224/line407在正式735均0。
9 tests PASS（0.004秒），冻结v2预检seal
`d811770781aa9e838782ae6cf0a043d8d7c3ac0625d761ffc3ba24e8b078a58f`
及全部pins/Spike轨迹重放通过，2130 checks、2112内存字节及
1024 VRF字节oracle匹配。仅软件资格，不声称DUT命中，准备
一次有界VCS及完整拒绝/恢复核验；不改RTL。

Sv39 case-only cause13 identity后继父侧全文审读并运行20 tests
PASS（0.089秒），覆盖accepted load byte/未知或错误seed字节/
重复/额外source/owner/interval/geometry/配置/CSR异常拒绝。
actual prepare已完成，successor plan seal
`050f8a3403a8c437991d5162d5ac915bd65dcf52f8310df4d4412780640b6483`，
父侧开始`sv39-masked-terminal-v2-qualified-parent-20261006-01`
只读collect；原HOLD及通用vector_commit代码保持冻结，无重仿真。
case-only predicate须通过完整gold及独立128字节identity证据后
再调用原比较器，原比较器仍检查prestate/unknown及全部正常写回。

QBS full1792本次DVE正常OS退出，但资格HOLD：actual Tcl在
`Reload native signature drift`报terminal1，最后cleanup空EL通过，
缺失final-stage，不能批准整批豁免。父侧实际离线解析first/second
均1792条，完整原生record multiset相同、顺序不同；这仅定位
导出顺序差异，不替代完整五阶段或annotation逐identity验收。
冻结原失败目录，后继应采用精确native identity/全部属性/annotation
multiset及重复拒绝，保留source、邻居和global empty检查；
不修改RTL、不重跑仿真、不将原失败session挽救为成功。

735百分比工具父侧全文审读helper/tests/native multiset Tcl，
实际9 tests PASS（4.883秒）；actual prepare PID3368443已运行。
尚未生成新的DVE百分比，不把准备阶段当作覆盖报告完成。

Sv39故障arch_seq243的父侧独立轨迹诊断通过：解析native VRF写回并
按EEW还原后，accepted集合恰为v8的128字节，每字节严格匹配
独立seed公式；SLDU port3 accepted128字节，load port4所有BE为0，
两次alloc/done闭合，source集合恰为3/4。此解释检查器HOLD，
不是新仿真、不是通用checker放宽，也不是正式准入；正在准备
case-only后继，须另校验sealed Spike prestate、CSR及负向测试。

Sv39实际VCS正常退出，wall156.166618秒，无超时，tohost=1。
父侧terminal工具12 tests PASS（2.582秒）及plan prepare通过，seal
`7139b5dbb3c97ddf017c37e4494f6c7b45dd4c4c0a232d29152d964064d039eb`。
实际collect保留HOLD输出`sv39-masked-terminal-qualified-parent-20261006-01`：
完整scalar对比31239条、17946写回、5724标量访存PASS，RVC及独立
19460字节gold检查已通过；normal vector105条/13321字节无失配、
unknown0/incomplete0。但故障arch_seq243仍unretired，尚不准入。
父侧源码与轨迹核查：同请求先执行SLDU port3的E32→E8布局维护，
16个beff写回；随后实际load port4四lane均be00。通用identity-load
fault门控仅接受cause4，不接受本次cause13，故未证明trapped请求。
需case-only严格保值/生命周期/CSR证明后继，不忽略写回、不修改
历史通用checker或RTL、不重跑VCS；不能把当前HOLD称为RTL数据bug。

Sv39 masked fault/retry旧镜像运行已由父侧启动，未准入。
runner及其测试全文审查，6 tests PASS（0.004秒），实际prepare
128 pins PASS，prepared seal
`1cef43f38496b540d1ed2391c25765a2535bdabb6564fd7e9a8701a6428b4a4a`。
service`ara-sv39-masked-unit-fault-20261006-01`，目录
`sv39-masked-unit-fault-old-image-parent-20261006-01`，sim预算180秒、
service上限240秒、完整raw commit/vector trace、不启用FSDB。
后续仍需真实simv身份确认及完整scalar/vector/trap/memory终端检查，
最后相对735核对实际覆盖增益；不将进程退出当成功，不修改RTL。

QBS side-old整批限定原生资格已启动，不是最终豁免应用。
父侧完整审读full1792 helper/Tcl/tests，实际6 tests PASS（42.231秒），
actual verify149 pins PASS。冻结plan seal
`224eb4be2d8202858cc2ed89b0f3246a83f688c162284d6b12e7e6233f043f01`。
父侧记录独立授权后启动service
`ara-qbs-full1792-qualification-20261006-01`，MainPID3361099，
实际systemctl状态active/running。限定一次3600秒后台核验，
1792个精确truth-vector临时排除、五阶段3584目标/邻居审计、
41214 raw补集保护绑定、EL保存/复位/重载及最终空EL；
不允许整模块排除、不修改原始VDB或RTL、不自动重启。
仍待真实DVE身份确认、完整终端结果与父侧独立inspect；不新增PASS，
不宣称整批豁免已批准或百分比已提高。

Sv39 masked unit-stride页故障/原PC重试候选已绑定正式735集合。
父侧实际运行14项host测试PASS（1.851秒），随后独立执行新预检，
目录`sv39-masked-unit-fault-preflight-735-parent-20261006-01`，seal
`a8e1d8e8bb524a361de18e63a7ab613b6a1695240ef8f99f11fa7957e1229b55`。
目标dispatcher cond raw493在735中仍为0；Spike预检35996条退休记录、
85项检查、2个预期trap、19460字节独立内存/CSR/guard核验通过。
masked active 9字节、恢复load 17字节，目的组mask/tail及原PC重试已核验。
此阶段未启动VCS、未准入覆盖率、未修改RTL；旧734预检原样保留。
最新已验收DVE百分比仍为723项；734后继host prepare正在进行，
735百分比未生成，不将预检或候选豁免算成实测覆盖提升。

只读CSR实际gain为line12/cond12/branch12/FSM0，全部发生于
dispatcher，24预定line/cond目标均fresh命中。candidate seal
`68ff2c2cfb03ba5a237cadd355b3b079524fa28bc69b580bb62aa0ee02b18cb1`。
父侧准入工具8 tests PASS（0.005秒），正式prepare seal
`2c266b7c81cd9c8a3e1a3f7cf667b93895bfed158b1d0dcf096fde5aa2b42327`，
actual admit已生成735正式集合，admission seal
`4fb3c0219a791c9a669ad9403d97634042f57b423e0e94d7c65bdf57cfa59397`。
父侧独立读取正式输出，确认734精确前缀/735唯一测试/全部
6162指标实例逐位OR；正式完整verify已通过，输出
`OFFLINE_HISTORICAL_ADMISSION_REVERIFIED`。目录
`readonly-csr-offline-admitted-735-parent-20261006-01`。
不代表已重跑734个历史案例或已有735项DVE百分比。

QBS nested单点真实DVE闭环通过。父侧完整审读helper/Tcl/tests，
7 tests PASS（2.225秒）、prepare133 pins及verify通过，plan seal
`58978dee4b7603d5acafcdb2b9349cf983bf63c098293740d4077065c41043c1`。
实际DVE PID3351697 exe/祖先身份核验通过；service正常退出0。
实际EL是Condition8260/vector3，而非XML编号；点checksum
4245564008、truth11，scope/module/metric/expression全部匹配。
before/selected/reset/reloaded/final邻居状态通过；first/second
字节相同，5个global empty EL均为空，最后清理复位确认。
父侧独立inspect PASS并封存capture-status seal
`7bbdd8227dae4eb6dcd8f9df547086eb775137819e688ee4ba5c1844b6f6f682`，
目录`qbs-nested-singleton11-parent-20261006-01`。仅证明单点
签名/43005保护，不是1792整批资格或最终应用。

CSR增量工具父侧全文审读并运行14 tests PASS（1.863秒）。
真实prepare相对734已通过，plan seal
`1a5e9688182fcedee1b51e99ce219d5c767745fe5515ef405da6a7122c4ed52c`。
开始只读采集已完成VDB，不重跑VCS；正式计数尚未改变。

下一条普通RVV候选已定位到实际734零点：dispatcher cond
raw493、width1140/checksum1370170966，expression
`(!ara_req.vm) || ara_req.use_vs2`的truth vector10。
冻结源码4346行对应masked非indexed普通load发生页故障后
WAIT_IDLE_FLUSH控制分支。相邻vector01/00已命中；不预报
额外line/branch/FSM收益。准备Sv39 masked unit-stride load
首元素页故障、原PC修PTE+sfence后重试及普通load恢复，先做
Spike独立完整目的/mask/tail/CSR/trap/guards预检，暂不运行VCS。

734报告后继Tcl原生multiset helper父侧实际执行冻结729的
applied/reloaded流，精确5892条匹配；annotation directive
变异被拒绝。此仅核验重载比较工具，不批准原729失败报告，
仍需新的完整session阶段、protected检查及百分比验收。

CSR v3完整terminal资格正式产物已生成。父侧全文审查工具/
测试并运行22 tests PASS（6.525秒）；真实prepare168 pins，
plan seal `9630d7bc5e8763f7571c62478c6c8ca578080469f3a21625bc640bd69bc51d5e`。
父侧actual collect通过，qualification seal
`dd87ac132013bd97db883a65d2ca680631bc8b57f056e05bfb97f454d5e073d4`，
目录`readonly-csr-terminal-qualified-parent-20261006-01`。
191 requests/responses、12拒绝、拒绝backend/VRF活动0、5个
正常backend uops全部身份/生命周期匹配，2864字节显式读回、
9543退休、黄金scalar/vector及CSR/trap检查通过。尚需相对
734的覆盖增量及准入，正式集合734不变；未重跑VCS或改RTL。

CSR v3父侧实际执行独立黄金比较：scalar为
TERMINAL_TOHOST_MATCH，9543指令、5299标量写回、1929标量
访存全部匹配，unknown skip0、mismatch无；vector为PASS，
3条写回指令/264 accepted bytes匹配，12个预期拒绝请求，无
incomplete/unretired/unknown skip。此前432字节完整缓冲区
检查补充inactive/guard证据；完整资格尚待封存与增量准入。

DVE后继离线10项测试父侧实际PASS（39.363秒）。完整5892条
EL记录的身份/属性multiset相等且无重复；仅顺序改变。旧729
GUI错误仍被硬拒绝，不将离线等价诊断冒充新报告或豁免批准。

父侧独立读取CSR v3 actual commit_trace.csv，按标量load/store
宽度重构可观察内存并检查：9543条retirement连续、733项自检
失败0、12个完整trap ledger（cause/tval/mepc/opcode）、240个
前后CSR值、12个目的寄存器哨兵及432字节source/dump/result
全部匹配独立期望。此为只读诊断，不替代完整逐指令黄金比较、
vector生命周期/VRF及postpins资格；尚不准入或发布新增百分比。

父侧复核完整native capture所有封存artifact哈希，并重放实际
1344组/448嵌套/3584向量解析，通过。但抽查实际ID-display
字段仍仅返回表达式/meta和truth vectors，没有数值ID，故
不能以该字段非空证明compiled numeric signature绑定。要求
下一步先静态确认接口，再以限定探针核验；不重复全量查询，
不猜XML顺序，1792候选及41214保护仍HOLD。

只读CSR v3 VCS已终止，return0、wall67.536秒、CPU52.790秒；
191 requests/191 responses，12 exceptions，protocol_errors0、
outstanding0。status明确为SIMULATION_EXITED_NOT_ADMITTED。
这些契约计数只证明事务闭合，不能替代独立逐指令/CSR/trap/
向量和完整内存检查；正在准备完整terminal资格，正式集合734不变。

两bank完整1344组原生只读查询实际完成，111.617秒、return0；
448个嵌套组、3584个真值向量均被采集，status为
FULL1344_TREE_VECTORS_DISPLAY_CAPTURED_SIGNATURE_PROTECTION_HOLD。
后续仍需原生ID-display到compiled数值身份绑定与41214保护
核验；1792候选尚未批准或应用，不预报覆盖率提升。

729失败离线定位进一步区分两问题：CSV plan seal被误用于
runtime-plan校验，实际runtime文件哈希与已有pin一致，不是
文件字节漂移；此外GUI已报Combined EL actual reload bytes differ。
故仅修seal传参不能批准报告。后继须完整核对EL身份/属性及
重复项，保留原生/protected/roundtrip拒绝条件；不重跑仿真。

只读CSR v3真实Spike预检通过，父侧12项host测试全部PASS
（31.295秒，无跳过）；preflight seal
`cfc86e25e0784f6d41b4a6e8d93b66e19c5e97587a2cd02cd8a35b61e0e9a676`。
父侧正式prepare seal
`919cc59c2b2a6c3fce82ac069caa9311474eae6415ef2ec2334b9dce127dfb93`，
独立systemd单次600秒VCS已启动，simv PID3334222的实际exe
确认是冻结旧镜像。输出`readonly-csr-v3-old-image-parent-20261006-01`。
需完成独立terminal检查及相对734的增量核验；尚未准入。

1792原生映射后继父侧完整审阅，11项host测试PASS（16.645秒），
封存98 pins的实际verify通过；已授权一次300秒只读DVE采集，
service为`ara-qbs-full-nested-native-20261006-01`，plan seal
`c11ddc09123d063682e6ec738743cc37fdddefa5c921c3f64c4473c01ffd2f30`。
范围为两bank共1344组/448个嵌套组，仅查询实际身份及真值；
不应用豁免。数值signature和41214个保护条件仍需另行核验。

只读向量CSR激励的v2 Spike预检失败已定位为激励编译问题，
不是RTL失败：局部期望数组初始化引入额外`vsetivli e64,m4`
（PC 0x80002c1a，opcode 0xcda47057），将恢复用`vadd.vi v10,v8,3`
置于不合法的LMUL4目的组。12条非法CSR写本身均产生预期异常。
原失败输出保留，尚未运行VCS。v3仅将三张期望表改为静态
只读存储，保留原检查期望；ELF检查要求恰好8条显式向量指令。
父侧实际运行v3 preflight/runner单元测试：12项中10 PASS、2项
因尚无真实v3 preflight而跳过（0.046秒），不能替代真实Spike
或RTL验证，也不计入734正式集合。

729项八组DVE汇总现已终止，status为FAILED，原因是
`External source seal differs`指向runtime-plan.json。原报告保留
用于调查，未批准应用/准入，不能用于发布覆盖率百分比。
目前有效百分比仍为723项，正式PASS集合734项。

GAP110已正式准入734。v2增量candidate seal
`348597c327918640538c75be7034b1ae16b7c6e61f12d90433bb45cd0a66abc3`，
正式prepare seal
`13389249f9b42e6d363a73d0d09ce64006848067922ef11674acdfaa832e962e`，
admission seal
`388c041fc323289521358ee2ef08bad6367cbb3b93fe3adabf6527d0a4847261`。
目录`gap110-offline-admitted-734-parent-20261006-01`。
完整software/native重放、41检查、VRF/CSR/source guards、35cond
编译坐标和26目标通过；父侧另外独立核查输出哈希、733精确
前缀、734唯一测试及6162实例逐位OR，并执行正式verify通过。
line/branch/FSM增量为0；没有重收singleton或重跑VCS，没有
修改RTL。旧733只继承资格并重查pins，不宣称本轮重验733项。
新DVE百分比仍待汇总，不能将723项百分比冒称为734项。

1792 nested两父树的限定只读采集实际成功，57.516秒、return0；
4个原生节点，其中weight/activation各自独立child的真实path/meta
均匹配历史嵌套结构。DVE实际报告Tcl 8.4.5.1 / 8.4。
目录`qbs-nested224-tree-profile-parent-20261006-01`，plan seal
`ba5d7c05673dd581b0e1d027b72e7e2dd65823fa47018237fe909203679e0d0e`；
父侧9 tests PASS（1.058秒）、prepare80 pins及verify通过后授权
启动，actual DVE PID3318893已核验。该结果仅证实2父树查询
假设，不等同于1792资格或41214保护核验，未应用排除。

GAP110 v2父侧完整21 tests运行65.509秒，20项通过，完整
prepare路径发现profile_engine_int.sv的3个附带增量点缺source
白名单绑定。此前只在mkdir前检查的测试无法发现此遗漏；
现在完整compiled路径已覆盖。该源文件已在冻结build及历史
732库存中有精确hash，3点已定位到源码265行tail-wave correction
drain/start_ready条件，待明确绑定后重验；未运行新的仿真。

父侧进一步审计GAP110 compiled全部设计输入：design/sourceinfo
及常规shape已有库存，实际cond增量还需要tgl shape/info的
历史pin；对应正式732/727记录可精确回溯。后继v2先检查完整
读取清单再解析XML，复用封存singleton；清单写出需真实换行，
实际写入/不可覆盖及完整prepare路径均要测试，不用空fixture
替代实际compiled增量核验。

GAP110父侧复用正式732及新资格的封存pins，独立只读完成
compiled坐标/源码匹配：35个新增条件点分布为payload bank0
4点、bank1 28点、profile_engine_int 3点，26目标全命中。
源码仅涉及qbs_payload_buffer.sv/qbs_profile_engine_int.sv。
此核查没有写入正式集合；后继v2需产生可独立重放的完整证据
库存及准入记录，旧失败记录保持不变。

普通RVV下一条候选已完成冻结源码和733未命中审计：
VTYPE/VL/VLENB的CSRRS/CSRRC/CSRRSI/CSRRCI非法写，共12条；
对应12个condition false及12个line位置仍未命中。准备精确
illegal instruction cause/tval/mepc、目的寄存器/CSR保持及合法
向量恢复的独立期望与Spike预检；尚未启动，不预报实际增益。

1792缺失的224组表达式均有唯一已枚举父表达式，但父子在
compiled raw层是不同记录/不同truth vectors，不能用父组替代。
已有原生capture证明tree firstChild/nextSibling/path/meta API
可用；准备仅查询bank0两个父树的限定只读探针，先证实真实
child handle，仍不猜XML ID、不丢候选、不应用豁免。

GAP110递归helper绑定后实际collect取得singleton，随后因
`tgl.verilog.info.xml`未传入证据库存而拒绝compiled核验。
原工具及输出封存，failure SHA
`070985b6a6b635ba78c01ac19793c77ea94228ae13b2bde832d7329ac2a41c00`，
singleton SHA
`9081836e52bda2f0a7c5e7508caeb0b1532a779f233676b94fb717fa758dd766`。
父侧独立只读检查6162实例、design/width/checksum、733唯一
旧测试加1新测试：实测product raw增量line0/cond35/branch0/FSM0；
26目标全部before0/single1。该结果是独立raw诊断，尚非准入，
不能用它宣称734集合或新DVE百分比。后继复用同一singleton，
补齐所有compiled设计输入的历史绑定，不重收raw、不重跑VCS。

1792后继v3父侧全文审阅，实际26 tests PASS（3.346秒），
在禁用现代Tcl命令的宿主机模拟器中执行完整1344组capture
流程并复现原lassign错误。实际v2原生inventory另揭示每scope
预期672组中只有448组名称直接存在，224组身份仍缺失。
v3明确禁止EDA启动，不丢弃缺失组、不猜测XML到GUI对应；
实际prepare75 pins及verify通过，seal
`74e4a713ebd96e4fafee24d90d9c511384303fb128a34284ac21105b9da1bdb3`，
目录`qbs-side1792-native-discovery-v3-parent-20261006-01`。
尚无原生资格/EL应用，需先确定嵌套表达式的原生访问方式。

GAP110准入工具父侧全文审阅，25 tests PASS（0.060秒）；
部分写入生命周期测试是fixture，不代表真实734已准入。
增量工具复用链进一步发现GAP106 v4库存缺失，已定位正式
727的封存book中精确SHA，并要求沿732->730->727证据pin
补全递归工具绑定，不用当前文件动态hash冒充历史核验。
正式集合仍733，尚未取得新的有效DVE百分比。

GAP110增量工具父侧实际12 tests PASS（31.473秒），实际
collect在创建输出前拒绝：复用的`prepare_gap107_raw_gain_v2.py`
不在已有证据pin库存中。尚无gain输出及覆盖准入；需补完整
复用工具的精确绑定及实际准备路径测试，不降低核验条件。

1792 v2采集终态51.626秒HOLD：DVE成功加载设计并导出
首个payload scope的完整expression inventory，随后其内置Tcl
报`invalid command name lassign`。原生signature尚未取得，
没有应用豁免；保留冻结v2输出。后继先审计旧DVE Tcl语法
兼容性及完整capture脚本，再考虑一次限定只读采集。

GAP110 v2正式离线资格核验已PASS，qualification seal
`de367a7367c8d5b01956da47588c8e3e8d5d493a1038eea2d5edd35feabe1404`。
结果只证明限定software/native合同，不宣称完整scalar ISA或
Spike custom核验；尚待相对正式733集合的真实bitmap增量及准入。
同一仿真日志复用，RTL和旧镜像均未修改。

1792只读discovery的v2已通过父侧准备及verify，plan seal
`1257af80d1e5aea46be45ad5a1ac3ad8882d21f6440a0291837d852ea727e034`。
完整生成selection已在宿主机Tcl解释器执行核验，保留原失败
记录；父侧授权一次300秒只读采集，独立systemd任务启动，实际
DVE PID3299030及/proc executable身份已核验、运行中。
未创建/应用排除，未将1792候选计入覆盖率或已批准豁免。

1792 native只读discovery父侧全文审阅helper/Tcl/tests，实际
16 tests PASS（1.774秒）；fresh prepare58 pins，plan seal
`f84487e23126c677e1d40d986ea1f2a8e0ce4c8a739d8b47163bfd8519c8ad86`，
目录`qbs-side1792-native-discovery-parent-20261006-01`。
父侧记录授权并启动300秒独立只读任务，实际DVE executable
身份核验PID3290192通过。终态19.776秒HOLD，return0但
native rows为空，未选择豁免、未创建EL、未应用排除。
实际GUI日志根因是生成selection.tcl的多行`[list ...]`
缺少续接，使返回的首组list被当成Tcl命令，qsd_scopes未赋值。
不是已证实DVE API/许可证/RTL问题。保留原工具/记录，
后继需宿主机实际解析完整生成脚本再启动，不重复盲试。

GAP110 ABI对齐后继父侧diff复核并实际50 tests PASS
（18.462秒）。既有预检的ABI pin使用compiler依赖字面路径
`apps/qbs_gap110_q3_r4_tail/../common/qbs_abi.h`，后继同时
保留原路径及同SHA的canonical路径并检查普通目录/枚举/
字段位移；不修改冻结preflight。实际prepare391 pins，
seal `ef748a418b36d1e8532d833b7888950dcf18451680fc71689fec60df941d70e8`，
输出`gap110-native-v2-qualified-parent-20261006-01`离线collect
进行中。首次collect命令手工seal少写导致准备输出核验拒绝，
未创建资格输出；仅更正为prepare返回的完整seal后再collect。
仿真及旧镜像均未重跑/更改，正式集合仍733。

父侧只读诊断仅在内存中将GAP110描述符布局期望改成冻结
ABI规定的R4=2/M8=3，不写文件、不修改封存检查器；复用
同一终态trace完成全部runtime检查。结果：41项检查、240
字节custom有效写回、8192字节完整VRF、两相各initial4224/
actual4224/weights1024/activation2496/descriptor144/CSR160
字节readback通过。该诊断用于确认错误局限于描述符期望，
不是正式资格输出或覆盖准入，仍需ABI绑定后继正式核验。

GAP110实际VCS终态正常，CPU205.550秒，51 requests/51
responses、0 exception/protocol/outstanding，UVM ERROR/FATAL
均0，两命令共41项自检PASS；仍不等于覆盖准入。检查器证据
book修正后父侧实际45 tests PASS（17.669秒），实际prepare
388 pins，seal
`5f59009cbd5034e9bfa0d45dcea2f01dbaee56ab319f278b256a5de99922ff12`。
实际collect在`gap110-native-qualified-parent-20261006-01`
保留拒绝：`Readback differs: descriptor_packet offset64`。
父侧静态与退休日志归因：冻结ABI的R4/M8布局枚举分别2/3，
软件正确生成header `0x632152`/`0x432152`，且后续完整readback
一致；检查器错误硬编码布局1/2，期望`0x621152`/`0x421152`。
此为工具预期错误，不是已证实RTL bug。原资格输出/检查器
保持封存，准备明确ABI绑定的后继；只重新离线核验已有日志，
不重跑仿真、不修改RTL、不提前纳入PASS/覆盖率集合。

1792侧字段条件的独立只读复核未发现限定合同内反例；证明
限定冻结配置、有效复位后收敛及已知合法控制/metadata。
768组合是Boolean投影，不能宣称任意X/初始delta下的四态
形式证明。扩大合同允许输入X可使old-side为X，但未证明
指定known-1向量可达，也不构成当前已证实DUT bug。
保护范围及未应用EL状态保持不变。

GAP110独立runtime qualifier父侧全文审阅，实际39 tests
PASS（9.282秒），包含完整CSV写回/CSR/readback和缺失/
错误mask、tail、SID、完成顺序负例。真实prepare在创建任何
输出前拒绝：`Missing sealed ancestor helper book`。
父侧核对确认：preflight仅直接绑定732 evidence book，
该已认证book才绑定730 ancestor book；检查器错误要求祖先
直接出现在preflight.input_pins。只修工具证据路径，冻结
preflight/runner/RTL/镜像不变，当前仿真不重跑。不得将39项
工具测试称为DUT PASS；准备修正后重新实际prepare。

QBS payload side旧槽1792条件候选父侧全文审阅proof/测试/
canonical verifier，实际38 tests PASS（23.762秒）及9 tests
PASS（0.002秒）。实际父侧prepare输出
`qbs-payload-side1792-proof-native-plan-732-parent-20261006-01`，
seal `bf1651bbae82cfc82db2695595b5d88f71ee26525bf482afca30b4626b9072e3`，
42个输入pin，1792个候选及41214个保护条件；与agent独立输出
seal一致。实际canonical verify通过。工件包含768种布尔状态
转换投影的归纳检查，此数不是DUT测试数。证明仅绑定冻结配置
和正式732集合；未创建/应用EL，DVE实际原生选择资格仍HOLD，
不得据此宣布覆盖率上升。正式总集合仍733项。

GAP110 Q3_K R4短尾父侧完成native参考、ELF审计和runner审阅，
实际build测试10项PASS（7.988秒），此前runner测试12项PASS。
独立检查最新733项bitmap，26个预测目标仍全部未命中。
实际prepare验证369个输入pin，prepared seal
`6803bc87380efafecb2d53b3e0688c14dfec175cf573a5d04b0a3d11b8b46387`。
已启动独立600秒预算任务`ara-gap110-q3-r4-20261006-01.service`，
目录`gap110-q3-r4-old-image-parent-20261006-01`；父侧从
`/proc/3280044/exe`和cmdline确认实际冻结simv及输入ELF、trace、
五类coverage参数。保持RTL和镜像不变，尚未功能准入或新增百分比。
后续raw gain必须相对正式733项计算，不能误用preflight的732项。

store fault/flush父侧实际prepare/admit完成，正式集合733项，
目录`store-fault-flush-offline-admitted-733-parent-20261006-01`。
prepared seal
`90afdfa25d5726705cc850871bdda9dbe959fd576bda7e87df09e87738f69fbd`，
admission seal
`ff12f5b191546e814fde60a4e71e1112e07c769ece72bdb9a0706d512ce83a81`。
父侧全文审阅admit工具与测试，实际8 tests PASS（0.005秒）；
实际admit重放完整封存输入与raw gain，另独立检查8个正式
输出hash、733唯一成员、input文本及完整bitmap与此前独立
6162实例OR候选一致。新增line1/cond1/branch1/FSM0，不是
百分比。未重验历史732项或生成733项DVE百分比。
下一GAP110 Q3_K短尾runner父侧全文审阅，实际12 tests
PASS（3.172秒，包含真实prepare但不启动VCS）。激励源码/
独立native参考仍待审阅，尚未启动仿真或准入。

store fault/flush实际raw collect已完成，candidate seal
`4be1c9ae6db77bb743fb656063eb5e57c0523849c45cfaba4f05f385b0ccac6a`，
目录`store-fault-flush-gain-732-parent-20261006-01`。
父侧以独立整数OR逐一核验全部6162 metric实例、精确732
前缀及733唯一候选成员、全部输出hash，确认新增line1/
cond1/branch1/FSM0。primary VSTU line raw54和conditional
branch raw43均由未命中转命中。正式admission待完成，不能
把733候选数或原始位置增量写成最新正式集合/百分比。

store fault/flush原始增益工具实际13 tests PASS（1.593秒）。
真实prepare首次在XML Element属性访问处拒绝，尚未创建输出；
修正为`.get('chksum')`后实际prepare成功，plan seal
`60d26fba5aac11624ccf9c9223a08c87c9839277a057fb27b3a676356a08d450`，
目录`store-fault-flush-gain-plan-732-parent-20261006-01`。
完整6162 metric实例bitmap collect已启动至独立
`store-fault-flush-gain-732-parent-20261006-01`，不重跑仿真。
gain尚未终态，不宣称733准入或新DVE百分比。

store fault/flush完整严格collect实际成功，qualification
`store-fault-flush-qualified-parent-20261006-01/qualification.json`
seal `eccf64c9a7cce97c45a4e871aba6d555750a65c81b8908299d6b730598fb9201`。
包括完整标量退休/异常CSR对齐、272字节向量差分、native
写回所有已知字节、请求/uop/SID守恒、134项源/目标/guard
及终态日志核验；仍不宣称完整ISA资格或B-error内部逐周期
竞态证明。raw gain尚未收集，未准入，正式集合仍732。

终态目录验收工具已修正：重新验证封存preflight、66个旧镜像
文件义务及精确command/预算/元数据，不调用要求目录不存在的
fresh-run prepare。新增真实已完成目录和命令/缺失镜像pin
负例，父侧实际11 tests PASS（2.068秒）。实际prepare成功，
`store-fault-flush-qualification-plan-parent-20261006-01/plan.json`
seal `ef3d87ebc28982affc69c115839935b4fda6572f929900c81eab4949b495f599`。
完整collect已启动至独立`store-fault-flush-qualified-parent-20261006-01`，
尚未宣称qualification终态或新增覆盖准入；原simv数据不重跑。

store fault/flush仿真终态return0，wall35.511秒，无超时。
父侧对封存trace实际独立调用lifecycle及observed：26请求/
响应、1异常、7后端uop守恒，134检查0失败，100字源/目标/
dump及1024字节明确readback通过；cause7、tval、vstart0和
后续8字恢复正确。实际scalar_exact通过2714条退休、1325
GPR写入和403次标量内存访问；向量差分3指令272字节PASS，
无未知字节跳过或未完成请求，异常请求为arch_seq10。
完整qualification尚未封存：验收工具fresh-run假设会错误
拒绝已存在的终态目录，正在修工具验证路径，不重跑仿真。
未collect新覆盖增益、未准入，正式集合仍732。

store fault/flush实际simv PID3267659已确认存活（20秒、
CPU49.4%），命令、旧镜像路径与started.json一致，非仅
Python校验进程；尚无终态或功能PASS，独立结果检查待完成。

store fault/flush旧镜像runner父侧全文审阅，实际10 tests
PASS（0.220秒），prepare seal
`6101312ac73b8bdc3d75f7924681829f12ca9696930233564de1bb24e47a3a6c`。
单次有界运行已托管到
`ara-store-fault-flush-732-20261006-01.service`，独立输出
`store-fault-flush-old-image-732-parent-20261006-01`。600秒
仿真预算、66个旧镜像输入校验及完整提交/向量trace；无RTL
修改、无自动重试、不自动准入。后续严格功能检查及最新732
覆盖差值待完成，服务启动不等于simv已启动或DUT通过。

QBS payload侧信息旧pending槽静态分析父侧实际完成，目录
`payload-cond731-static-parent-20261006-01/review.json`，SHA
`21bc8ee97c3f1e10465e2526e8b41a96531b1647c52e8a452be4ae00d95172b3`。
父侧全文审阅分析工具并核对payload consumed、adapter pending
全部更新分支及mask绑定，独立检查报告所有pins和最新732
bitmap：两bank各896个精确候选条件点仍未命中，总1792。
侧信息plane2即时consumed，因此pending.strb不保留该类字节；
旧槽有效side hit为0，受enable门控的旧数据选择也不可执行。
其余41214个条件点保持保护。仅静态候选，原生DVE资格及EL
尚未完成，不改变百分比。尝试的Q6_K/M8 phase有限传输模型
得到新增comparison witness为0，不能外推全部场景不可达，
也不为此启动无明确增益的重复仿真。

store fault/flush内存匹配v3正式软件预检父侧完成：工具实际
7 tests PASS（0.021秒）；完整独立host、ELF编译及Spike
严格134检查PASS，目录
`store-fault-flush-preflight-v3-parent-20261006-01`，manifest seal
`9ca0579d7f3fb7cd9acd37d6e2c711e8996357714e524c36d39a7a3b2aad2fab`。
仅显式匹配Spike RAM，原oracle、异常cause7、vstart0、100字
buffer/source guard及后续8字恢复保持；未启动VCS、未准入。

父侧同ELF最小内存诊断完成，目录
`store-fault-flush-memory-diagnostic-parent-20261006-01`。
只给Spike增加`-m0x80000000:0x200000`，实际return0（0.461秒）。
复用原严格validate，134检查通过：唯一store access fault，
cause7、tval `0xe0000000`、fault vstart0，后续8字恢复写入
正确，trap及源/目标guard保持。由同ELF结果确认前次失败的
内存映射环境根因；仅软件诊断，不是DUT/B-channel验证、
不准入覆盖率。后继正式预检及旧镜像runner仍需核验。

lane0 ALU-B原生14点资格工具父侧全文审阅并实际32 tests PASS
（1.592秒）。实际prepare完成，目录
`alub-lane0-native14-731-parent-20261006-01`，config seal
`2161578520b87e61258a81688bd8062d223822296dce24ccd7d62a5f3bd31ca0`。
仅封存准备，未启动DVE；原生选择、保护点和导出重载资格仍
保持HOLD，不应用14点豁免，不改变覆盖百分比。

store fault/flush软件失败已得到环境根因证据：Spike trace2461
在`0xe0000000`实际写入，vstart变1，2462才因下一元素+6
未对齐报错；命令没有`-m`，本机Spike源码帮助明确默认2048 MiB。
该默认与冻结RTL 2 MiB RAM不匹配。后继应显式约束内存布局，
不放宽cause7/vstart0期望；本次失败保留，尚未跑后继或DUT。

store fault/flush v2软件预检已终止失败：独立host及ELF编译
步骤完成，Spike返回1，trace末尾为`*** FAILED *** (tohost = 1)`，
停留PC `0x800020f8`。完整失败保留在上述独立目录；未启动
DUT，不能据此报告RTL bug或纳入覆盖率。后续先解析首次
失败的trap/自检及Spike环境，再确定是否需要激励后继。

父侧已完整审阅store fault/flush软件预检v2，实际执行原工具及
v2共23 tests PASS（7.967秒）。后继以封存历史中的simv及
compile.command SHA和66个runtime文件约束输入，不以新读取
的digest认可任意替换镜像。独立软件预检已启动于
`store-fault-flush-preflight-v2-parent-20261006-01`；尚未宣称
Spike、DUT或覆盖率准入通过。单epoch读取辅助工具实际21 tests
PASS（0.045秒），未接入正在运行的729项DVE。该DVE实际进程
PID3230267在本次核查存活，累计运行25分48秒、CPU97.4%；
没有新有效百分比，不重启、不替换其输入。

GAP109正式732父侧实际prepare/admit完成。admission seal
`badbcc7aad21ce6dab6c8c0eeabc7f85b2c13226bbe893a56c88995eab149794`，
prepared seal
`29aae71622737e40ed9ee3a6a27ce38933854d06b9998f6498a7d6e33a1d7313`。
目录`gap109-offline-admitted-732-parent-20261006-01`。父侧审阅
原始admit全文、v2完整diff和测试，实际28 tests PASS（0.059秒）。
实际admit重放software/native及compiled gain之后，另独立核验
9个正式输出hash、732 status/input顺序、完整bitmap与此前独立
6162实例OR核验的candidate相同。正式line0/cond2/branch0/FSM0
增量成立；不宣称重验731项历史测试或732项新DVE百分比。

GAP109 v2增益映射后继实际完成，candidate seal
`7ab75aa0f72ee0366fd130564ae8fda578d06f39013ee66775ad60446377f3fb`，
目录`gap109-raw-gain-v2-731-parent-20261006-01`。
父侧全文审阅工具及负例，实际9 tests PASS（27.112秒）。
保留原失败，复用原singleton，不重跑或重采集。NULL metric
checksum以精确scope/module、完整merged WIDTH32 MODE0+1参数
和compiled tgl/cond checksum绑定，仅用于对应LZC，不全局放宽。
父侧另用独立整数运算逐一核验6162个metric instance：精确731
前缀及732项唯一集合，完整OR一致，line0/cond2/branch0/FSM0。
目标FMA raw77由未命中变为命中。尚为候选，不正式准入或报告
新DVE百分比。

731原始bitmap的缺口排序定位到QBS payload buffer：bank1
cond5159/21503未命中，bank0cond4142/21503未命中（非DVE百分比）。
冻结source与build pin均为
`664916dbe39405b316c1bff5e750d33b3fecffdfaf5a3c6385287d362ca0056e`。
bank1 source571未命中条件最多的行：349(552)、97(488)、
401(432)、282(406)、346(396)、342(379)。先区分固定参数
不可达与真实合法writer/profile/layout组合缺口，不因数量大
直接豁免，数据相关byte-valid及邻点仍保护。

父侧独立读取优化实测完成，目录
`verification-epoch-benchmark-parent-20261006-01`，report seal
`0b49029a38f17081dce62a3433c69c5a8b01cfa6bb2fdc65f1744848a8a422e4`。
12项负例/同结果测试PASS。封存输入样本的重复读取9.748秒，
单epoch捕获3.417秒；独立worker峰值RSS167772→35144 KiB，
少哈希779592214 bytes，pins与JSON结果一致。仅为样本工具
实验（重复方案先跑，有page-cache/order影响），不能外推整个
DVE速度；未接入当前DVE，也不能以快照代替后续新epoch校验。

GAP109实际仿真return0，CPU221.510秒，51 requests/responses，
exceptions/protocol_errors/outstanding均0。父侧实际native collect
完成，qualification seal
`490d91c941f74692de9e4af73587b2ea00985237af7429feeeb0b7b138ea56eb`。
完整8192-byte VRF、8192-byte初始VRF、24CSR、6880源guard
及41自检通过；不宣称完整标量ISA或Spike custom执行。
raw增益工具39 tests PASS，但实际收集在额外LZC的NULL metric
checksum绑定处严格拒绝。保留失败目录
`gap109-raw-gain-731-parent-20261006-01`及singleton，不重跑。
父侧独立按整数OR比较确认新2个cond位置：目标FP32 FMA
width117和cast-multi LZC width217各1个。尚需后继完整参数绑定
及全量准入，正式集合仍731，不冒称已准入732或新百分比。

GAP109独立软件/native qualifier及负例父侧全文审阅，实际51项
测试PASS（7.483秒）。实际prepare核验423个pins，目录
`gap109-native-qualified-731-parent-20261006-01.prepared.json`，seal
`1b72e5f49a179b39084125078d8f85995b9b86900ae108965bfbcdf1c2b060b9`。
仅准备检查，不是RTL资格PASS；必须在真实终态后collect。
读取/哈希/JSON共享的独立VerificationEpoch工具及测试已审阅，
实际23 tests PASS（0.035秒）；同epoch只证明捕获字节快照，
新完整性边界必须重新验哈希，不接入当前封存DVE任务。

lane0 ALU-B静态候选父侧实际prepare完成，目录
`alub-lane0-static14-731-parent-20261006-01`，candidate seal
`81eb26c1cb540374af0324377f5a1bc36e298a6f265f4db4078198c2c051c71c`。
仅限定9个line/5个branch点；native qualification保持HOLD，
未生成或应用豁免。原生后继工具可离线准备，不干扰当前DVE。

Store FIFO全路径静态可行性报告父侧已全文审阅：地址fault可在
StA命令未排空时报告done，因此不得使用done必为空的假设批准
八点豁免。正常访存计数lemma的11,156,480组算术检查不等于
DUT测试；异常flush的全状态屏障证明仍未闭合，八点继续HOLD。
新激励准备转向合法store fault/flush/recovery，先检查731集合
避免重复，独立核对trap/source/destination及新覆盖位置。

当前729项DVE真实进程PID3230267已核对，执行八策略脚本，
进程存活且CPU活跃；仅为运行证据，尚无新有效百分比。
lane0 ALU-B候选proof强化为全部VS2字面量赋值计数、完整PE
赋值和FIFO存储写入归纳；父侧重新审阅并执行12 tests PASS
（13.764秒），原生资格仍HOLD，不应用豁免。

GAP109父侧全文审阅runner、独立Fraction/native oracle与ELF
audit；实际25项runner测试PASS。实际prepare核验406个pins，
prepared seal为
`825f37dfd9d8ba6316405f6539626a896b4169d30e4404e244be0954e36777af`。
已托管到`ara-gap109-k2-sticky-731-20261006-01.service`，实际
simv PID3235232已确认存活并运行；输出目录
`gap109-k2-sticky-old-image-731-parent-20261006-01`，预算600秒。
未修改RTL、未重建镜像，不宣称RTL PASS或覆盖准入。
lane0 ALU-B限定14候选工具父侧全文审阅，实际12项测试PASS；
源级枚举及FIFO存储归纳仅是静态资格，原生DVE选择/导出重载
仍未执行，不声称已经豁免或改变覆盖率。

GAP109预检父侧审阅build及static contract全文，实际22项
Python测试PASS（6.019秒）；独立合并input/output/artifact
清单核验333个唯一pins无漂移。manifest seal为
`37f8e166e013483c1b3c99b90968d402cf88d89299dfe0e4043df4a2b17e6a06`，
ELF SHA为
`7882d8878241e7770d966bd78d0e3f1dee49c131696f479df8ecc399f330cd92`。
目录`gap109-k2-sticky-preflight-731-20261006-01`。host44检查及
46个保护区损坏负例、标准FP32 Spike24操作/52项ledger预检
均保留，不能宣称custom-app Spike或RTL PASS。runner仅准备，
VCS尚未启动、覆盖增量未测、正式集合仍731项。

lane0限定候选的父侧静态复核补充：requester的IDLE及最后
fetch接新请求两条路径均取消VL=0 command valid；FIFO reset
将存储置0，但flush仅清指针/计数，不能声称flush清存储。
保留旧命令必须通过所有producer不产生ReductionZExt的归纳
证明。算术枚举1..65535确认lane0正VL非零，仅为算术检查，
不冒充全RTL形式证明；custom producer边界仍纳入候选核验。

Store FIFO零增益诊断REPORT父侧全文审阅并独立核sha256：
`f9466aa5bf859042d068f348b3b33d1ed43639134442f943852489af4f8e7df3`。
固定镜像WaitForStoreB=1，49对burst相邻store的next allocation
均晚于old done 3cycles；本合同不能以更多store触发同周期
command push/pop。证据不是直接FIFO/AXI探针，异常/flush/
拆分边界全域尚未证明，因此八点仍HOLD，不自动豁免或重跑。

新限定豁免候选开始准备：lane0 ALU-B ReductionZExt的9个
line及5个branch点。源级依据为正全局VL时lane0 localVL必
非零，零长请求被dispatcher/requester门控，其他Lane真实
neutral路径必须保护。尚须封存源码/compiled映射、边界及
native资格核验，不声称已应用豁免或覆盖率提升。

GAP109有限值K2激励父侧已全文审阅整数IEEE/native oracle及
execute.S。用宿主gcc -O2 -Wall -Wextra -Werror独立编译并运行
oracle_tests，22项PASS；另编译host_reference实际执行，两phase
均result_bits=1132462080（0x43800000、256），control flags0/
CSR8，target flags1/CSR9且仅stage10产生NX。逐块12阶段
reference结果符合静态假设；这是host参考模型证据，不是RTL
PASS或覆盖增益。编译ELF/冻结目标绑定仍待完成，尚未VCS。

下一条QBS有限值K2累加sticky激励开始准备；父侧已审阅main
相对GAP108的变更，保留完整VRF/CSR/源guard检查，仅把合法
M1/N1 descriptor及权重/激活跨度改为K2。目标为FP32 FMA
cond raw77：control scales[0,1]与target[2^-60,1]最终值均256，
但target应仅NX=1，必须检查flags差别而非只检查结果。独立
oracle及冻结源码/compiled目标核验待完成，尚未启动VCS。

DVE后台服务本轮实际检查仍active、MainPID3222537；进程
列表只有准备核验runner，尚无DVE child，status仍PREPARED_NO_DVE。
因此仅声称启动前校验正在运行，不声称实际DVE已开始。journal
读取因权限拒绝，未修改权限；后续使用输出目录及真实进程核验。

DVE729八策略CSV修复汇总已托管启动：父侧已审阅实际私有
consumer及run_reviewed/claim_once路径，两个封存plan的sha256
独立匹配，配置seal为
`f965477b2bfeace138c85563245b7f4e70e0701a0b3ad4499e85ef29a58301bb`，
launch seal为
`744ffa4ce23553b52afc1d213c489e012ec9266b174314c663bafbec803dcd83`。
systemd服务`ara-eight-policy-csv-fixed-729-20261006-01.service`
实际active/running，MainPID3222537；先进行全部输入pin核验，
通过后才启动DVE。固定729项、5892个目标及17774个保护位置，
不重跑仿真，不冒称731项或已产生百分比，不重复启动/频繁轮询。

纯WAR实际admit完成，正式集合731项；manifest seal为
`79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641`。
目录`pure-war-offline-admitted-731-parent-20261006-01`，精确
730前缀保留、新增四个已绑定Lane条件位置。此为历史旧镜像
raw覆盖准入，不等同731项DVE百分比或重验全体历史测试。

纯WAR准入工具负例已按真实职责补全：ELF/pins递归去重校验
真实evidence-pins.json损坏，同时明确非ledger证据由调用方
life.check全量校验，另有负例验证。父侧重新审阅并实际执行
9项测试PASS（30.881秒）；真实prepare完成，seal为
`156b6dca697a3b49d501563cf1958ae81aede92be988d9ba931d035b202da0e0`。
正在实际admit重放，结束前仍为730项，未改RTL或重跑仿真。

父侧全文审阅纯WAR731准入工具，实际8项单元测试中7项通过、
1项`test_pin_ledger_drift`失败：ELF历史去重遍历对测试传入的
非pins/非ELF条目未作hash拒绝，而负例预期拒绝。尚未执行
实际prepare/admit，不声称731项。需明确遍历校验契约并补
真实pins ledger损坏负例，不能删除断言或带失败准入；此为
工具测试问题，没有新RTL失败证据。

DVE729 CSV修复准备进程PID3216312已实际ps确认，elapsed
约3分20秒、CPU93.7%、状态Rs，仍在运行源码身份/封存准备；
不是已启动DVE，也不是新百分比。保留唯一准备任务不重复启动。

Store FIFO增益工具已全文审阅，13项测试PASS（6.563秒），
父侧实际以正式730为基线collect完成。candidate seal为
`6c40f2634d7879c2c29855e699539a14ec6c8a13a1871fb5c5383cd270816304`，
目录`store-fifo-burst-gain-730-parent-20261006-01`。line/cond/
branch/FSM增量全部0，八FIFO目标fresh gain为0，终态
`STORE_FIFO_NO_FRESH_TARGET_GAIN_HOLD_NOT_ADMITTED`。保留
功能PASS及原VDB，不准入、不以incidental增量替代队列目标，
不重复跑；先静态分析请求推进与FIFO生产/消费时序再决定激励。

父侧独立逐项整数OR复核正式730全部6162个metric instance，
确认与729加GAP108 singleton精确一致、形状/checksum及历史
前缀保持，新增cond8。DVE729消费路径v2源码已审阅，3项
端点绑定/拒绝缺失授权/私有消费者测试PASS（5.299秒）。

纯WAR raw工具全文审阅，12项测试PASS（23.333秒）。父侧
实际prepare/collect对照正式730完成，plan seal为
`ddadc8ca9c14027db207d4299f5c255a9967e9891fde783c2655f9eb6fe6e64b`，
诊断seal为
`5ed322cd80a3e5a134a4c3876a9e7cb51ff956481a4725cf48fa44394e165378`。
目录`pure-war-raw-diagnostic-730-parent-20261006-01`实测新增
cond4，line/branch/FSM0；四Lane requester_index=8的raw1059
四目标全部新命中。仍为未准入诊断，不声称731项或DVE百分比，
也不声称直接观察source-lifetime stall；后续准备正式准入重放。

GAP108已实际正式准入730项，manifest seal为
`8da19c3fba8b438851231dfc79c8006caeea2364f578c29f9afa3c6fbf91d3f5`，
prepare seal为
`a0b792e41001d8677f4983c26251ac4450366903d2f245ba42b4815d56c269d2`。
父侧审阅admission v2差异、25项工具测试PASS，并实际执行
prepare/admit完成完整software/native及compiled gain重放。
随后独立确认730个唯一成员、729历史精确前缀和6162个metric
instance。相对729新增cond8，line/branch/FSM不变；累计相对
723新增22line/270cond/24branch，共316个覆盖位置，非百分比。
未生成最新DVE百分比、未重验全体历史案例，不声明custom Spike
或完整scalar ISA。后续两项测试增益必须对照正式730基线。

GAP108限定源码绑定v2由父侧审阅差异，44项测试PASS（16.294秒），
随后实际复用封存singleton执行raw/compiled核验成功。candidate
位于`gap108-raw-candidate-v2-729-parent-20261006-01`，seal为
`05d3b1db9c3163d93c9ecef797173242c34212addb9af03ad9fbba585c958415`。
实际新增cond8，其余line/branch/FSM为0，精确729前缀保持；
这是未准入候选，仍需正式admission工具重放审查后才可称730项。
原缺失绑定失败目录及原工具保留，没有重复采VDB或重仿真。

纯WAR900实际独立功能资格通过，qualification seal为
`b6859948cfaf0949f5bd8ebc476fba46840ae67515b56876cd3cc17ce450d161`。
父侧复核206 pins无漂移；标量241635条退休、191701次寄存器
写、5300次访存匹配，34条向量写及6144已知字节无unknown或
duplicate。125次请求/响应守恒；未观察source-lifetime周期
探针，不声称直接证明目标stall发生，未测覆盖增益、未准入。

store FIFO实际资格seal为
`a47662c6244db0f0d51b3f895ba694c190a5f58aca5e881c0afb5a963e84628a`，
父侧独立177 pins复核无漂移。2360项检查、56次store顺序及
9664字节读回、60995条标量退休/42027次寄存器写/5600次访存
通过；136次请求/响应守恒。未测八个目标或实际增益，不计入
正式729项；只准备raw核验，不重复仿真或修改RTL。

父侧独立使用已保留GAP108 singleton与正式729 bitmap执行精确
OR，诊断增量为line0/cond8/branch0/FSM0、6162个metric instance。
singleton SHA256为
`2a65e582c69908c619010121a130daa5e4a381514d67960f0d4015f31a835b45`，
四个原始输入hash独立重验无漂移。尚未compiled绑定准入，
不声称730项或DVE百分比。缺失的lzc.sv当前SHA与冻结build
source pins一致，均为
`f31989be4369ea7c4809c0c3d61df28581e9ac7666005fde6e476a975d1acd07`，
且非symlink；准备仅增加该精确历史源码绑定的工具后继，
不得放宽到任意源码、修改RTL或重跑仿真。

父侧实际执行GAP108 raw/admission工具的57项单元测试PASS。
真实raw提取保留singleton bitmap，但在compiled source绑定阶段
拒绝`hardware/deps/common_cells/src/lzc.sv`未绑定，诊断目录为
`gap108-raw-candidate-729-20261006-01`。未生成可准入candidate，
不增加正式729项、不声明新百分比；需核对旧编译源码身份后
使用限定后继工具，原工具及失败产物不改，不重复仿真。

父侧检查两个真实systemd服务均已inactive/dead、MainPID=0，
pure WAR900及store FIFO的simulation-status均为returncode0、
`SIMULATION_EXITED_NOT_ADMITTED`。只是正常退出，不等同功能
资格或覆盖准入；分别交独立检查器继续完整核验。

GAP108真实仿真终态returncode0，VCS CPU186.720秒，契约
requests51/responses51、exceptions/protocol/stall/outstanding全0。
父侧实际collect完整software/native资格PASS，seal为
`f91e8305cc3cb242f3b19036856744590a8b82c3887c62d67ac95627beea53cd`。
41项自检、完整VRF8192字节、初始源VRF8192字节、24个CSR
及6880字节源/保护区、256字节custom写回独立核验通过；
两phase实际结果0x100/0x200及生成flags0/3符合分阶段舍入。
父侧另用jq+sha256sum独立检查全部evidence pins，返回0且
没有不匹配。仍仅限software/native资格，不声称完整scalar
ISA或custom Spike通过；未计算实际增量，正式集合保持729。

729底座及CSV修复八组消费路径已由父侧全文审阅：独立
`eight_policy_csv_fix_729_wiring.py`把同一精确身份Context
绑定到read_config、verify及前台runner，原模块全局不变。
实际6项测试PASS（0.015秒），包含读取/验证/执行同family、
消费者源码pin及原有一次启动门槛。真实DVE仍未启动；后续
须使用此后继入口，不能误用仍绑定旧Context的原runner。

store FIFO VCS已由父侧实际启动。runner及测试全文审阅，
实际8项PASS（0.004秒）；封存prepared独立verify PASS，seal
`fa74f8704a11cf0928804146f6c0c8a2f881356d8875532f7d47aa5ee48035c2`。
服务`ara-store-fifo-burst-20261006-01.service`，真实ps/proc/exe
确认simv PID3201243与冻结镜像一致，使用独立输出目录。
仿真wait预算仍600秒；服务外层660秒含启动前预检重放开销，
不表示仿真预算加大。没有DUT PASS或八目标命中结论。
GAP108 software/native资格工具和46项测试全文审阅，实际
46PASS（7.583秒）；actual prepare418pins，seal
`a1c0418c818397f4156ef9fcd275f583912116f3e1ac08711e62eead9393b502`。
保留完整VRF/flags/guards、SID、请求响应和退休绑定检查，
不冒称完整scalar ISA；尚未读取实际终态或collect。

正式729工具身份适配已由父侧全文审阅，实际12项测试PASS
（13.539秒）；原正式封存链729..723的manifest/ledger/PASS
及精确前缀、R1 host命令和cc来源均受校验，错误来源与链接
负例被拒绝。底座及DVE实际导出仍在准备，未产生新百分比。
store FIFO原预检失败的真实compile.trace为循环展开重复三个
全局汇编标签，不是RTL错误。限定v2只增加-fno-unroll-loops
并绑定独立测试文件，父侧实际14项测试PASS（5.843秒）。
v2预检由父侧实际verify PASS，2360检查、60995条Spike指令，
seal`713f47a0032fb597cdddb12d809f68ee5f67a0bdacd3ab538d25ecb6084021b9`，
ELF`6c42b42c861db73c92e80bebcc70efe2f998a7e35560a9e483f9e4cc2bd44fa2`。
旧失败目录未改；尚未VCS或计入覆盖率。

GAP108旧镜像VCS已实际启动，未准入：父侧全文审阅runner
及测试，实际21PASS（0.043秒）；actual prepare401pins，seal
`ad154bde3b72c06ba41b243e0beac70462ac2e467c1275fa8ba12cff92414666`。
服务`ara-gap108-subnormal-20261006-01.service`，真实ps及/proc/exe
确认child3198029使用冻结simv、独立ELF和code.vdb，预算600秒。
只采集原始commit/vector及覆盖率，DUT数值、七目标增益均
未验证，不频繁轮询；后续须完整software/native资格检查。
纯WAR900秒资格后继已全文审阅、实际10项测试PASS（0.021秒），
prepare190pins，seal
`8fcc2698193da3047ddeda2dc1c6ed9b62c8387749e14417e8713c7c97b8c242`。
继承全部原有oracle算法，仅明确900秒与新run绑定；尚未collect。

同ELF纯WAR900秒后继已实际启动：父侧全文审阅runner和9项
测试，实际9PASS（0.018秒）；prepare158pins，seal为
`288d0497b0778f9abb1cdb38157dc9167bae855b4acfecad55fe94f1d7e74acb`。
后台服务`ara-pure-war-budget900-20261006-01.service`，真实ps
确认child3195998执行原冻结simv、原ELF和独立code.vdb。
不复用旧超时VDB，不删减原1765检查、不修改RTL；实际结果
及最新基线增益尚待终态资格核验，不准入或频繁轮询。
GAP108次正规数激励父侧审阅main相对已审GAP107的变化、
独立整数IEEE oracle、build及测试，实际16项测试PASS
（5.699秒）；标准Spike只验证12次分阶段FP32运算，不能
冒称custom QBS app的Spike或DUT PASS。VCS入口仍待审阅。

普通RVV store command FIFO新激励及host/Spike预检工具已经
由父侧全文审阅；实际12项测试PASS（5.342秒）。测试直接
绑定正式729及冻结compiled definition，确认四lane共8个
line/branch目标仍零命中，并拒绝错误VL/vstart、错误store
数据、缺store、缺scalar读回及保护区损坏。刺激为e32/m1，
VL=4/8/12/16/20/28/32，各连续8次独立store，burst内只有
地址加法、无barrier；全部2360检查保留。尚未DUT仿真，
同周期FIFO push/pop重合是待验证假设，不保证8点增益。

父侧进一步读取正式729 ledger及原六组Context：729实际封存
`/usr/bin/gcc`哈希`472ed0bac12ba95f15d484b506ff1b32cc089cc47f5253a7ff0697667501f322`，
并封存工作区LLVM五个工具路径。实际readlink确认其中三个
链接为clang->clang-22、ld.lld->lld、llvm-readelf->llvm-readobj；
其余两个不是同类链接。原v2的强制cc来源属于R1专用条件，
不应不加区分地施加给所有后来的人口集合。后继从原Context
做精确链接适配，保留所有ledger项的字节检查；若引用历史
cc身份仍须有封存祖先证明，不凭当前工具状态补写历史。

729汇总底座准备发现工具身份门槛不匹配：原v2仅接受固定
工具链接白名单，且强制最新ledger包含历史`/usr/bin/cc` pin。
新集合的LLVM链接需依据实际ledger及resolved字节独立绑定；
缺失历史cc项不得补造。父侧已读v2，确认cc仅用于历史producer
来源核验、并非DVE执行工具；后继优先沿正式封存祖先追溯
原始cc出处，再做限定身份适配。当前没有新DVE运行或最新
百分比，不以工具门槛失败当作RTL失败。

纯WAR超时后父侧核查完整目标事件：DIV（arch79）在cycle79649
完成，indexed load（arch80）在cycle85402完成；之后退休持续
推进到224882。不能由此宣称最终数值通过，但没有把这次超时
误记为目标指令停死。准备同一ELF、全部检查不变的独立900秒
后继及对应资格绑定，不修改原600秒证据或冻结工具。
原八组DVE日志已经保存final-empty.el，并记录EIGHT_FAILED
及csv_row清理异常；该次输出继续禁止用于覆盖率百分比。

纯WAR仿真实际终态为TIMEOUT，不准入：600秒预算到期，
returncode=-9，wall_seconds=604.3241790318862；输入pin无漂移，
进程组已清理。commit日志末尾完整记录为cycle285620、退休
order224882，末行被终止截断；Spike参考241635条退休指令。
仍有执行进度不等于通过，也不足以排除末尾故障；后续先
核查目标指令及剩余执行区间，不自动放大预算或使用该VDB。
终态资格工具已全文审阅，父侧实际52项测试PASS（9.132秒）；
176pin资格计划已准备，seal为
`d8200b3beed333ffc75b163572899dac35ef51646414994c9c1a144aeee22205`，
因真实超时不执行collect。原激励/日志/失败状态均保持。

QBS FP32次正规数候选已由父侧静态核对：profile decoder的
Q8_K activation scale读取完整32位；accumulator固定使用契约
舍入模式，先FP_SCALE_MULTIPLY再FP_ACCUMULATE_DOT，不能
把两次舍入合并成一条数学表达式。FPnew仅在舍入后仍tiny且
inexact时置UF。三个相关源码的实际SHA256与旧镜像build pins
逐项一致（qbs_fp_accumulator、qbs_profile_decoder、fpnew_fma）。
正在准备exact和tie-to-even两阶段的独立数值参考、全VRF/
CSR及保护区预检；尚未启动VCS，不计入729集合或实际增益。

CSV-only八组汇总后继四个文件已由父侧全文审阅，实际运行
`test_eight_policy_csv_fix.py`，5项测试全部PASS（0.108秒）。
修复仅在原八组Tcl初始化前装入独立CSV过程，保留原选择、
原生绑定及验证器逻辑；测试包含真实snapshot调用链、引号/
逗号字段、729人口绑定及依赖篡改拒绝。不代表真实DVE汇总
已成功。正在准备正式729绑定的独立目录，不修改失败727
目录或原始VDB。父侧真实ps确认原DVE仍在清理，纯WAR的
simv PID3177879也仍在执行（8分25秒），不是仅凭服务状态
推断存活；尚无纯WAR通过或覆盖率增益结论。

父侧实际读取正式723与729的完整raw bitmap，调用原工具
核查同design、同instance universe、width/checksum一致及没有
旧命中位丢失。六条新增激励共增加308个raw编译位置：

| 模块路径类别 | 新增行 | 新增条件 | 新增分支 | 新增FSM |
| --- | ---: | ---: | ---: | ---: |
| QBS及内部FP/adapter | 10 | 246 | 11 | 0 |
| AKV | 3 | 4 | 3 | 0 |
| CVA6 controller/CSR/padding counter | 7 | 11 | 8 | 0 |
| 普通RVV dispatcher | 2 | 1 | 2 | 0 |
| 合计 | 22 | 262 | 24 | 0 |

这不是DVE百分比增幅，也不含toggle增量。结果表明本轮新增
点主要在QBS，不足以宣称普通RVV operand queues或FSM覆盖
已显著提升；下一批继续针对这些剩余可达缺口。

父侧全文审查九组thin prepare/runner/entry及测试，实际13项
测试PASS（0.134秒）。其中真实冻结eight_snapshot_audit、
真实batch audit及CSV过程参与Tcl测试，仅mock原生GUI查询：
先精确复现csv_row未定义，再装入单独提取的CSV函数，使六个
审计阶段全部通过，含逗号/引号字段及目标/保护状态核验。
不加载整个exporter主程序，避免附带GUI操作。九组准备入口
要求已完成且独立verify通过的八组报告；当前八组失败，不得
假造参考或绕过该门槛，需先运行限定CSV修复八组后继。

GAP107正式准入729已完成，admission seal为
`e5bd9eeb19acc452d25db12f342c3c12532614a0c773c43355a33e34d8dd1912`。
父侧另行检查最终输出哈希、精确728前缀及6162个实例逐项OR，
全部通过；新增line2/cond22/branch2/FSM0。冻结旧镜像不变，
不把该raw合并冒称最终DVE百分比或新RTL验收。

GAP107限定准入工具由父侧全文审查，实际20项测试PASS。
实际prepare成功，seal为
`4f34b8a93aa160837a0bd11c4dbe86de41c28b1a42295df27fb81ee3092fb266`；
父侧另行独立核查3447个输入pin，无漂移。准入操作基于
固定728正式集合、限定native资格及26点增量，实际重放数值/
写回/退休证据，不提升完整ISA或custom Spike声明。最终输出
仍须验收后再更新当前状态表。

纯WAR后台VCS入口由父侧全文审查，17项runner测试PASS；
实际prepare核查146pins，seal为
`451934511f1c7014169a180f53868e530f227849193c19d8c7252592c60d5493`。
服务`ara-pure-war-20261006-01.service`已启动，父侧真实ps及
/proc/exe核对simv PID3177879与冻结旧镜像一致，命令实际
使用指定ELF和独立输出`pure-war-old-image-parent-20261006-01`。
预算600秒、保留完整commit/vector及五类VDB、不生成FSDB，
无自动重试；还没有DUT通过、目标命中或准入结论。
旧fixture负例曾错误修改冻结dataclass而报环境异常，原记录
保留；独立successor用dataclasses.replace构造单PC变异，
不修改原源码/ELF/检查器，补充结果38项全PASS由runner固定
seal核验。父侧实际Spike预检verify已通过。

父侧全文审阅九组RVH后继Python、私有Tcl及测试，实际15项
测试PASS（80.226秒）。范围为6139目标、19307保护位置、
六阶段状态审计；RVH按精确native签名等价，不误要求完整EL
文件字节顺序相同，原八组片段仍保持字节/顺序检查。测试
mock了继承八组split_bind，不代表完整DVE应用已通过；新发现
的csv_row缺失需要额外真实调用路径测试和限定后继修复。

父侧检查真实八组DVE日志，发现before阶段已完成七组23570
位置审计，但`eight_snapshot_audit`调用未定义的`csv_row`
而报EIGHT_ERROR。日志保留完整Tcl调用栈，随后进入排除清理
和final保护审计。该次百分比不得使用，不能把仍在运行的
清理进程说成成功统计。正在静态定位工具依赖，冻结运行文件
保持不变，准备后继修复；无RTL更改或仿真重跑。

GAP107相对正式728的raw候选封存在
`gap107-raw-candidate-728-20261006-02`，seal为
`d954f5248876dcfc919a97281ac733816c4447daa334da2a6f96afc0c1c0aee7`。
父侧审查v2后继相对原工具的改动：仅对新增命中所引用的
fpnew_cast_multi源码增加冻结build哈希核验，并先保存singleton
以保留失败现场；不修改RTL或原检查器。实际32项测试PASS。
另行独立核查3443个输入及输出pin，无漂移；精确728前缀、
729个唯一候选VDB及6162实例逐项OR通过。实测新增line2、
cond22、branch2、FSM0，共26点，预定20个目标全部新增命中。
首轮缺少源码pin的拒绝现场保留；尚未正式准入，不把正式
集合提前改为729，准备限定准入后继。

普通RVV纯WAR新激励`vpure_war_div_indexed_load`完成一次
host/Spike预检，父侧全文审核源码、独立字节期望、ELF与检查器。
预检封存在`pure-war-div-indexed-preflight-727-20261006-01`，
seal为`e2c29d00524aeee602f219b7d464f62e3fc39906736fecad523eaee03253201a`。
父侧实际verify PASS，141个pin独立核查无漂移；35个非fixture
单元测试PASS，3个需要环境变量的实际fixture测试未运行，不能
把它们称为PASS。实际Spike轨迹包含241635条退休指令、1765
项自检，两次完整VRF快照及源/保护区、CSR恢复独立核验通过。
相邻指令为e8/m8/VL1024的VDIVU读v8组、索引load写v8组，
目标是四lane requester的纯source-lifetime等待条件；没有
人工延迟或提示调参。尚未VCS执行，不能宣称DUT通过或实际
新增覆盖点；准备一次600秒旧镜像仿真入口。

FENCE.T已由父侧正式准入728，输出
`fence-t-u-padding-offline-admitted-728-parent-20261006-01`，
admission seal为
`db371b3e126a4739117de8501daab2c149306acf0e4446b3eb64d69c65ec6add`。
父侧全文审查准入工具及测试，实际7项测试PASS；prepare的
3104个pin独立复核无漂移。准入后另行复核全部输出哈希、
精确727前缀及6162个metric instance逐项OR，通过；实际新增
line7/cond11/branch8/FSM0。限定资格不宣称UVM clean、完整
ISA、精确周期或未知OS退出码。运行中的DVE报告仍封存727
输入，不能将其未来百分比标成728；GAP107增量须对准最新728。

GAP107父侧全文审阅独立software/native检查器及测试，实际40项
测试PASS；prepare核查388pins，单次collect通过，封存在
`gap107-native-qualified-parent-20261006-01`，qualification seal为
`23f4ab908ca0ac63f8ed6e40af1b73e716d735b373c5f601fcc397fbca8326db`。
父侧另行逐文件复核404个证据pin，无漂移。实际41项软件自检、
两次custom各128字节写回、完整VRF前后读回、24个CSR值及
6880字节源数据/保护区均通过；两结果为canonical NaN
0x7fc00000，生成NV=16，与原fflags=8合并后为24。UVM_ERROR
和UVM_FATAL均为0，实际子进程退出码为0。该结论是受限
software/native验证，不冒称完整标量ISA或Spike custom验证；
尚待相对正式集合的覆盖增量及准入，不将集合提前增加。

父侧已全文审阅FENCE.T覆盖增量工具及测试，实际7项测试PASS；
随后对`fence-t-u-padding-gain-candidate-agent-727-20261006-01`
执行独立verify成功，候选seal为
`0007ddb0edc692199285582601982b516161e30ba90f5d38777df51460663508`。
相对正式727集合，实测新增line7、cond11、branch8、FSM0，
共26个编译覆盖点；6162个metric instance完整OR及精确727项
前缀保留。该候选尚未正式准入，不把集合写成728；两个UVM
无向量流量诊断、未知OS退出码及无完整ISA/逐周期证明继续保留。

FENCE.T后验结果已实际封存于
`fence-t-u-padding-post-parent-727-20261006-01`，seal为
`ae86f14616195603c505c98671bc8d8e5c0a234faad2ab060245beade3dabb11`。
父侧独立核查169个输入/输出/检查器pin全部一致。限定scalar
功能与退休资格通过，保留两个UVM policy错误、OSreturncode
未知和无逐周期计数证明；不使用通用错误忽略规则。相对正式
727的实际覆盖增量及精确前缀准入仍待完成，尚未算为728。

GAP107 runner及测试由父侧全文审查，实际18项测试PASS，
真实prepare校验371pins完成；prepared seal为
`b8c600b2b874f2321d3e6ae7e79552b8dcd381326de42e7bddca4f0514439e80`。
服务`ara-gap107-invalid-nan-727-20261006-01.service`已启动，
父侧确认真实simv PID3159074及`/proc/exe`与旧镜像一致，实际
加载指定ELF。输出`gap107-invalid-nan-old-image-parent-727-20261006-01`，
预算600秒，完整commit/vector/VDB；尚无RTL PASS或准入结论。

GAP107单次实际RISC-V/host build已完成，父侧298个input/output/
artifact pin独立核对无漂移。preflight seal为
`793e037f1ec024412c3a92faa8d123fece6242983a2aa5572d4eeae9ad7c7b25`，
ELF SHA256为
`3b11180a06f57e72e45f6c0b11bce4a28077d83f90392457fa6c7db91a30dabc`。
两custom site位于0x8000017a/0x80000252；host44检查及46破坏
负例，实际ELF完整VRF种子/快照和前后CSR序列通过预检。
这是静态ELF/host资格，不是Spike custom执行或RTL PASS；
旧镜像单次600s runner仍待父审后启动。

FENCE.T纯标量UVM限定后继由父侧全文审查并实际7项测试PASS。
它只接受精确源码行/组件/消息匹配的两个NO_TRAFFIC诊断，
核对实际severity总数、五类全零协议记录、全零ARA_CONTRACT
及无向量/custom backend退休；保留原错误，不成为通用UVM
override。正常终态日志后继仍待审核，不采用未知OS退出码。

FENCE.T父侧实际离线退休审核通过：18853条retire与ELF操作码
一致，三轮195个capture stores、五个trap ledger stores和
CEIL1011匹配；151个封存输入pin后验均无漂移。该执行没有
持续native counter采样，仍不能宣称逐周期控制器证明。
transient systemd服务已被回收，无法补取精确OS退出码/墙钟
时间；旧show中的默认0不作为退出证据。后验工具须明确使用
完整封存VCS终态日志和已结束进程/VDB证据，不虚构receipt，
不只为补元数据重跑，也不把两个NO_TRAFFIC错误改写为UVM0。

GAP107独立build/ELF审核工具及测试由父侧全文审查，实际
11项测试PASS。检查真实custom字、立即前后CSR捕获、四组
完整VRF种子/快照、掩码及fflags初始化；还核对固定RNE的
QBS数值契约与architectural frm保留为2不混淆。RISC-V实际
build产物仍待封存，没有RTL执行或覆盖增益结论。

FENCE.T单次实际VCS于2026-10-06 18:17:31正常结束，CPU118.700
秒；原458项及新增241项自检均PASS，Core SUCCESS，实际
CEIL=1011、padding_witness=1。但UVM日志保留两条错误：
CVXIF/NO_TRAFFIC、VID/NO_TRAFFIC。冻结UVM在无向量请求及
无VID分配时无条件要求流量，此纯标量系统用例没有向量运算。
因此需要明确的限定适用范围核验，不能称UVM零错误，不能
静默忽略日志，也不能仅依据exit0或自检PASS准入。完整退休、
异常现场、协议计数和输入完整性核验仍待后验collector完成。

727项八组服务已越过预检，父侧通过进程树及`/proc/exe`
确认真实DVE PID3145219，路径与live-identity封存工具一致。
实际GUI日志出现SIX/SEVEN/EIGHT runtime installed及canonical
inputs加载标记。此时没有终态百分比，不从脚本已加载推断
全量保护点或候选豁免应用已经成功；保持后台运行不频繁轮询。

FENCE.T linked审核工具及测试由父侧全文检查，实际3项测试
0.196秒PASS。151个封存pin实际核对后，单次有界旧镜像VCS
已启动：服务`ara-fence-t-u-padding-727-20261006-01.service`，
真实simv PID3145914，输出
`fence-t-u-padding-run-parent-727-20261006-01`；预算600秒，
保留完整COMMIT_TRACE及line/cond/fsm/tgl/branch VDB。仅启动
并确认实际可执行程序，不代表自检、退休审核或覆盖率已PASS。
后验仍需完整151pin、699项功能检查、195 capture stores、唯一
ECALL异常和CEIL核对；不修改RTL，不根据超时盲调PAD。

GAP107特殊值激励的独立整数位级IEEE oracle、static contract及
测试由父侧全文审查；实际12项测试6.906秒全部PASS，包含46项
双phase破坏性负例。两phase分别得到dot0/256、correction0、
canonical NaN 0x7fc00000和NV=16；fflags seed8按OR保留为24。
宿主NaN payload未用作期望。正式727仍有20个准确compiled
条件零点；目前仅主机/静态证明，不是实际RTL PASS或新覆盖。
旧GAP106文件保持不变，新的独立RISC-V ELF及旧镜像运行待做。

FENCE.T独立单次build已实际完成，输出
`fence-t-u-padding-build-parent-727-20261006-01`，ELF SHA256为
`cfd003ebd8ee84d1e0cca8365e407e74ee4a12e4053d5cebf176f7b0406dd418`。
父侧检查linked符号：三个resume均为对应fence+4，capture为
fence+8；U ECALL位于0x80001eb0，M handler及两个MRET符号
存在，LOAD段位于0x80000000起始的合法范围。完整ELF退休/
独立结果审计及旧镜像VCS仍待完成，不宣称软件已PASS或新增
覆盖率。v2静态pin作用域测试由父侧实际执行通过。

FENCE.T静态后继已由父侧全文检查727 adapter、三项测试、独立
build脚本及当前C/汇编激励。实际三项测试PASS；主目标11cond、
2branch、1line及两个旁证分支在正式727仍为零。旁证分支不
冒充新增主目标。后继绑定727及封存工具，只在新目录编译，
不修改共享Makefile、旧ELF或RTL；仍需实际ELF审计与VCS。

QBS下一条特殊值激励已完成源码/727零位静态分析：两phase
分别使用Inf乘零和quiet NaN/Inf激活，独立期望canonical
NaN=0x7fc00000、fflags=24（NV加原seed8）。20个条件零点
只是预测目标，尚非实测增量；实现后先审查检查器再运行。

727项八组汇总启动入口由父侧实际check通过，返回
`LAUNCH_CONTRACT_VERIFIED_NO_DVE`。launch seal为
`d2bb42fcfd85c246bc5bb0874417bfa58c5da35077ad3fb0a18222eaae35a467`。
独立服务`ara-eight-policy-727-20261006-01.service`使用
`run-reviewed`前台等待实际DVE，避免短launcher退出后连带
终止子进程。结果目录为
`lzc-snapshot-eight-policy-runtime-727-agent-20261006-01`；
5892目标、17774保护点、23666审计位置不变，不包含RVH247。
服务启动不等于实际GUI加载完成，也不构成覆盖百分比结论。

RVH完整247点空选择项后继已结束，父侧重新执行独立verify通过：
247条原生记录、1533个保护分支、1780个位置的五阶段共8900项
状态检查均符合预期，最终EL为空。导出与重载记录的语义及
signature一致，不宣称两次EL字节相同。结论仍仅为限定原生
豁免资格，尚未应用到727项总汇总，也没有新的百分比结论。

FENCE.T U-padding检查器由父侧实际运行6项测试，9.240秒全部
通过；精确保留指定ECALL的trap=1退休记录，拒绝错误或重复
trap。测试中的逐周期计数模型只是检查器测试，不是DUT原生
波形证据；新激励尚待静态preflight及旧镜像实际运行。

最新六组汇总配置`branch-combo-six-policy-population-727-agent-20261006-01`
已生成，seal为
`fdff47142add3d05d4272e29af917fdf4e5401bddcbd65757d000c550bc523d2`。
父侧独立检查该seal、正式727 manifest链接、全部728行输入
（一个编译VDB加727个测试VDB）顺序和唯一性通过；5808目标
与13562保护点保持原审阅范围，未授权实际DVE启动。八组后继
准备进程PID3130987已确认活跃；此为文件/源码检查阶段，不
等同百分比测量，也不添加尚未完成核验的RVH247豁免。

RVH空选择项后继的实际DVE日志已验证故障假设：DTLB和ITLB
第一次选择均记录`raw={{}}`，对应一个精确空token；过滤日志
为`old={} removed=1`，随后`Branch0.1`单项回读正确，两模块的
第二个分支也正常。完整`DBG_AUDIT before 1780`及
`DBG_AUDIT selected 1780`已出现；任务继续完成reset/reload/final。
这支持仅修GUI选择工具，不构成RTL问题，也不替代完整终态
核验。不得从部分阶段通过推断247点已最终准入豁免。

新FENCE.T padding激励的初稿已由父侧审查，发现退休检查器
禁止ECALL日志与既有RVFI同步异常记录方式不一致。应精确接受
指定ECALL的trap记录，并核查完整CSR/内存结果，不能删掉异常
行来复用旧无异常检查器。旧镜像编译命令含`no_fsdb=1`，原生
逐周期counter采样路由仍需明确；未得到实际采样前不宣称counter
因果闭环。测试仅在静态与参考检查正确后启动，不修改RTL。

RVH空选择项工具后继已通过父侧10项测试（7.880秒），并在
独立目录`rvh-branch-native-full247-empty-v2-agent-726-20261006-01`
完成实际配置check。配置seal为
`64b99b7c97dac7df5014798b78123324354ec4cf60b4b7369cbe4d25015a5873`。
后台服务`ara-rvh-full247-empty-v2-parent-20261006-01.service`
已启动，真实DVE PID3128098的可执行文件与封存工具一致。
后继只过滤精确空选择token，其他未知/重复token及错误单项
回读仍拒绝；增加选择前/后原始值日志。247目标、1533保护点、
14scope和五阶段1780位置核验均保持不变；此时尚未完成真实
原生结果核验，不采用该任务的任何百分比或豁免结论。

GAP106已正式准入727项，manifest seal为
`918a5cb4b471e1106a10b4e1c76eb996e9803a44c8d4566c0a038d3b697e29d2`，
prepare seal为
`6ddbf327758d3690a9cce655c076711319cab3404d6af6cdb792214e9e45ca16`。
父侧全文审阅准入工具与测试，实际19项测试PASS；实际prepare
及admit均重新核查封存输入、受限software/native结果及原始增量。
准入后父侧另行检查9个正式输出校验值、精确726前缀、727项
唯一输入和6162个metric instance位图精确OR，均通过。该步骤
未重跑历史仿真、未改RTL，不等同新RTL signoff；727项的DVE
百分比及八组策略应用结果仍待实际汇总。

GAP106候选04已测得相对726的新增line8/cond33/branch9/FSM0，
父侧独立检查7192个输入/输出pin均无漂移，6162个metric
instance的合并位图均为基底与singleton精确OR，测试列表保留
完整726前缀，追加后727项唯一；50个新增编译点及两个预设
目标命中一致。candidate seal为
`12359de9fccd9172beb0faceaf982a3dfe3ee3d1f262bc58bdfbaf08d9c1e50a`。
父侧已审阅v4工具相对v3的差异，实际21项测试PASS。缺少
cond/branch instance checksum的FP32 FMA位置仅依据已封存
tgl完整参数变体、精确scope/module/宽度绑定，不任意放宽校验。
三次失败的离线准备目录均保留；没有因此重跑仿真或修改RTL。
候选尚待正式准入步骤，不将727宣称为当前正式集合。

RVH完整247点后台核验已FAILED退出。真实DVE完成了前五个
scope的before检查，并发现DTLB的两个native分支；随后第一次
选择时报`gui_list_select`空列表项不存在，DTLB尚无审计数据行。
全部1780点的before门控没有完成，未导出first.el，最终空EL
已保存。初步假设为切换视图后旧选择列表含空项，仍待工具层
测试验证；不得跳过DTLB/保护点或采用本次结果。仅修工具的
后继正在准备，RTL及原失败目录不修改。

RVH完整247点原生测量已启动为独立后台服务
`ara-rvh-full247-parent-20261006-01.service`，输出目录为
`rvh-branch-native-full247-agent-726-20261006-01`，配置seal为
`ce46b9f226a390712d2643e8b314e3d884e480cad73dce389d1974a2a6863b80`。
父侧实际check PASS后启动；真实DVE PID 3122153的`/proc/exe`
与封存工具路径一致，编译VDB已加载，初始空EL已保存，日志
正在逐scope导出分支位置。此为限定原生测量，不是726项的
全量百分比报告，也未将247点豁免应用到正式集合。后续只在
终态后检查完整导出/重载/保护点与最终空EL，不持续轮询。

八组策略汇总的Tcl、启动入口与测试已由父侧阅读，实际15项
测试PASS；验证同scope条件/分支分别路由、保护清单完整性、
全量before门控及禁止重复启动。仍待最新正式集合绑定和真实
DVE报告，测试通过不等于新增豁免已应用或百分比已提高。

RVH完整247点原生测量后继的Python、Tcl及测试已由父侧全文
审阅，独立执行7项测试PASS（72.473秒）。测试检查14个scope
的1780个分支位置、247目标及1533保护点，验证五阶段选择/
重载/清空、不同generate绑定、错误表达式/校验值/身份拒绝及
单次启动门控。Python/Tcl哈希分别为
`84c773a5aaf11f2ff277dfce33bc9e65e953dc6d0307cfe23ac89d22309bff52`、
`f2359a288d98e7502b001d162396a8feb67abe5d3209e86b13a0ce70b92b0f45`。
这只是工具审阅和主机测试，完整247点的真实DVE导出、重载及
独立核验尚未完成；不得把三点pilot结论扩大为247点已批准。

GAP106相对正式726集合的离线增量准备工具及测试已由父侧全文
审阅，实际14项单元测试PASS。检查覆盖精确725/726前缀、
唯一新输入、零增益拒绝、设计/输入/shape校验值漂移、位图
方向及native资格门控。此结果仅证明准备工具的这些检查，
不代表已经测得新增覆盖点，更不代表正式准入727项。

GAP106真实离线software/native资格核验通过，seal为
`1917e146ea25069df212db9b92863bf9d96ae31fc4a66e18f198a4041ce9b0f7`。
父侧完整阅读390行检查器及314行测试并实际31项测试PASS，
随后collect及465个pin独立复核通过。两命令的VRF后态8192
字节、初态8192字节、24个CSR值、6880字节输入/保护区均核验；
128字节目的寄存器中每命令4字节为有效结果，其余124字节按
当前custom契约清零。此为完整受限native检查，不宣称完整标量
ISA或Spike custom差分。增益及准入仍待相对正式726集合核验。

GAP106实际仿真于2026-10-06 17:34:04结束，CPU172.940秒。
两个命令各17项检查通过，加上前置及总量检查共41项，完整
VRF/source/CSR自检统计符合预期；Core SUCCESS，51请求与
51响应，0协议错误、0 UVM_ERROR/FATAL。真实离线资格检查
尚未完成，因此没有准入。下次原始增益需相对正式726集合测量，
不能继续将预检时的725集合视为最新总集合。

RVH三点pilot真实终态完成，父侧实际独立verify返回
`RVH_PILOT3_NATIVE_ROUNDTRIP_QUALIFIED_NOT_APPLICATION`。
3条原生记录的字段/注解重载一致，97个保护点在before、selected、
reset、reloaded、final五阶段均保持预期状态；三个empty EL确实
为空。first/second原生文件字节不同，检查的是完整记录语义及
signature，不冒称文件逐字相同。完整247点仍待后继原生核验，
没有应用到726项总汇总、没有新覆盖百分比。

VNCLIPU已正式准入726项集合，admission seal为
`3ce8d24ffa5bfee7f4b363878b348af4e4b4de67995bc71db7b2bb6931121517`。
父侧完整阅读准入工具及23项测试PASS，并实际verify封存输入、
缓存OR和compiled身份后准入；随后独立核对产物哈希、唯一726
成员、精确725顺序前缀及6162个metric instance的逐位OR。
新增line2/cond1/branch2/FSM0，五目标全部命中。尚无726项
完整DVE百分比报告；历史723项百分比仍只能标为历史。

RVH三点原生pilot父侧完整审核及7项测试、136pin config检查
通过后启动。unit为`ara-rvh-pilot3-parent-20261006-01.service`，
实际DVE身份记录PID3111577；只使用一个已准入sample进行原生
选择/保护资格采集，不是725或726项总百分比汇总。完整247
候选仍锁定，待本次精确3/97保护及reset/reload验收。

LZC作用域后继完成父审：v3 Tcl相对冻结旧版只增加
`global lpa_binding lpa_expected`，Tcl SHA256为
`5ff065327cde3a972442379e0a6b7f8ae687e69b68b7bd0fe9db95169d07e7b9`。
父侧实际4项作用域测试及2项runner测试PASS：正常proc加载后
1200绑定、36 scope完整；旧局部加载复现缺失；缺失/错误tuple
在GUI调用前拒绝。允许将这一修正绑定到新的725项八策略准备
入口，不重跑724项，不放宽原生保护检查，尚未启动新DVE。

GAP106使用M1/N1/K1、Q5_K×Q8_K、DIRECT，对比scale=1与
FP16正无穷。独立解包/MAC得到dot=256、correction=0，FP32
结果应为0x43800000及0x7f800000，新增fflags=0。完整VRF、
六CSR及输入保护区均检查；Spike不支持custom，未宣称Spike
功能PASS。父侧完整阅读测试包并实际运行9+14项工具测试PASS，
启动独立unit `ara-gap106-positive-inf-parent-20261006-01.service`。
实际simv PID3109693、exe及工作目录已核验；600秒硬上限，
不自动重试。原生raw4/raw7目标预计可达，增益必须实测。

VNCLIPU维护核验完成后，父侧对qualification seal及其中199个
输入/产物pin再次逐项SHA256核对，0差异。确认原仿真trace、
原FAIL现场、后继检查器及独立标量/向量证明绑定一致。原始覆盖
collector正在准备，正式准入必须保留725项精确顺序前缀并证明
正覆盖增益；禁止用资格PASS直接替代覆盖准入。

VNCLIPU真实离线维护核验已通过，qualification seal为
`b8f42476e14ac0ffeaa5519c92a9ceb344ab2a6b2e63fdaf2906e6a4657cc5ce`。
源v8维护128字节与独立参考前态一致，v16完整128字节与后态
一致，真正未知字节为0；312826条退休指令、255101次标量写、
9432次标量访存均匹配，33条向量写指令检查通过。原通用skip
输出与FAIL现场仍保留。此为资格核验完成，不能代替覆盖增益
及精确725前缀准入审查，因此正式集合仍为725项。

VNCLIPU维护写回后继检查器经父侧完整阅读及31项测试PASS。
检查指定架构owner的3个uop allocation/completion、源v8全部
128字节保持、目的v16维护写回及最终128字节状态；错误owner、
VID、EEW、数据、尾部、未知字节及缺失/重复写回等负例均拒绝。
原通用skip计数及FAIL保留，不将其改写为原检查通过。真实离线
collect在`vnclipu-maintenance-qualified-parent-20261006-01`
执行中，尚未准入、尚未测覆盖增益，也未启动新的VCS。

组合豁免的最小metric-aware拆分工具经父侧完整阅读及14项测试
PASS。实际24个Condition记录与既有Branch策略共用4个scope，
现按scope、module/metric checksum及directive类型分流，并要求
每个已审原生块逐字保持、不得遗漏或重复。未知scope、混合类型、
checksum变更及whole-instance指令均拒绝。此工具只拆已封存的
proposal，不替代DVE真实重导出、保护点及reset/reload验收。

LZC失败根因经父侧纯Tcl独立复现：初始化局部作用域中有
1200个`lpa_binding`及36个`lpa_expected` scope，初始化退出后
全局数组不存在。显式声明两个global后，原封存selection生成
全局1200/36绑定，无需改native ID。包装服务已失败退出；本次
combined EL未加载，LZC before/final均未完成。后继只修作用域
并增加实际proc加载回归，保留全部23570点检查及原失败现场。

RVH原生小范围计划经父侧完整阅读及5项测试PASS、120个封存pin
实际verify PASS。pilot仅包含一个scope的3个候选和97个保护点，
尚未启动DVE；完整247候选不能直接批准。725组合静态计划的
15个pin经父侧再次核验通过，5892目标及17774去重保护点仍仅
为准备结果，不是新的总覆盖率报告。

VNCLIPU进一步只读定位：PC=0x80002754、opcode=0xba804857、
arch_seq=124的恢复指令，cycle101187至101193出现16条
source=3、VID=1、vd=v8、EEW32写回，共128字节。通用比较器
`vector_commit.py`的`_architectural_compare_mask`对非架构目的
寄存器返回0，因此内部source reshuffle被归入skip计数。后继
必须独立核验全部源字节保持、写回归属及v16完整结果，禁止仅
将允许跳过字节数设为128。原FAIL证据及冻结检查器保持不变。

LZC七组原生采集的`DVEfiles/dve_gui.log`末尾明确报告
`SEVEN_FAILED No discovery-backed native token for protected branch position`。
已有六组final audit不代表全部七组保护检查成功；LZC的4200点
原生保护核验尚未闭合，不引用本次任何应用后百分比。最终空EL
已保存，源封存及失败现场保留；后续只定位映射问题，不跳过
保护点、不自动重启、不修改RTL。

VNCLIPU仿真于2026-10-06 17:19结束，CPU时间817.130秒。
终态退出码0且自检成功，但离线完整核验目录
`vnclipu-terminal-qualified-parent-20261006-01`记录了
`Full vector gate differs: skipped_unknown_bytes`。此证据尚不能
区分参考模型字节未知与真实RTL错误，先定位逐指令/逐字节来源；
不放宽零跳过检查、不重新仿真、不增加正式725项集合。

MaskM6/StA7的24个条件点已形成限定范围的审阅豁免，文件为
`verification/coverage/waivers/mask_store_snapshot.el`，SHA256为
`c11b89f8ae115a50c83bd409d57d003c768991ae589656c021c5209cdb9f44a8`。
审阅约束保存在同目录`mask_store_snapshot_review.json`；EL逐字
复制原生导出，不改native ID。批准只适用于封存旧镜像、正常复位
后的常量snapshot路径，不包括强制赋值、复位前X态或新RTL。
72个条件邻点、8个分支HOLD及实际索引端口8均保持保护；本步骤
没有更改全局默认EL，也没有产生新的总覆盖率百分比。

24cond原生资格采集终态完成；capture-result seal为
`c8da58c274ea6578902c0f8c3c2b698310edaa8884b6e41c52675029dd0083de`。
父侧实际独立verify返回PASS：24条EL精确compiled/native绑定、
导出重载一致、三个empty阶段、邻点保护、输入成员与哈希均
通过。19份产物绑定；`per_branch_GUI_audit=False`明确保留，
不把仅cond EL白名单推断成逐branch GUI查询。8branch仍HOLD，
此终态不批准组合应用，不冒称最新总百分比已经提高。

RVH静态证据父侧7项测试PASS并实际verify通过：绑定725、
101项pins、38组/10个scope、247目标/1126同组保护；27个
无精确compiled匹配的源位置HOLD。证据seal为
`d585c52ecc3611b86a3044dfd1164f8dcafcc8c37ad0ae0e73a8a2a17f268f9c`。
尚无原生资格，不生成EL、不批准应用。

24cond原生运行适配器复用封存`capture_operand_1144.py`的进程
身份与超时管理，父侧全文阅读适配器、8项新增测试及其底层
capture流程。与prepare工具共22项测试PASS，实际runtime
check通过；runtime seal为
`fd83977fbc45dc91ed4fc26012864dbb450a457ff3a9fd1a1a03f15f742fe1be`。
已显式授权资格采集，在systemd前台长寿命unit
`ara-mask-store-cond24-native-parent-20261006-01.service`运行，
预算1800秒。原配置和VDB不改；此步骤不批准应用、不会直接
合入总EL或最新汇总，仍要求实际24条精确EL、相邻点保持、
三个empty阶段和导出重载一致等验收。失败保留，不自动重试。

新`qualify_vnclipu_parent_terminal.py`及其测试已由父侧全文审阅，
实际33项软件门控测试PASS。覆盖精确异常PC/cause/tval、全
VRF/source/guards读回、合法恢复、请求响应和VID分配完成守恒、
拒绝项无后端/VRF活动、错误ELF/身份/元数据/协议/终态拒绝。
这些是检查器测试，不是DUT通过结果。helper SHA为
`2b87191d1eee57bdf1302260c729a814df2a6cf2555ac670318b183aa94e9543`，
tests SHA为`1bbada7452d849d03bed9b68da19a0b101d7dd5b9c582bd4c4cf4921f3c9f7a1`。
AXI无副作用依据算术opcode、Dispatcher拒绝和无后端分配的
因果路径，不声称捕捉了按owner归属的AXI探针或全局总线空闲。

系统静态筛选得到131个源码直接RVH决策，编译branch结构中
表达式为`1'b0`。按已用helper的表达式位序对应，得到247个
唯一true-pattern位置，724中全部未命中，同组1126个位置须
保留。六组既有策略没有CVA6 core owner，未因而覆盖这批点。
这些是待复核候选而非已批准EL；要求重绑725、精确源位置和
编译signature，并执行原生资格与保护检查。未匹配到精确
compiled决策的源码位置不补猜，不豁免复合权限判断。

历史descriptor/skew同原ELF预算补跑的42项封存pins再次核验
一致，但缺少完整标量独立执行比较以及缺失向量端口证据的
明确准入合同，仍HOLD。现有目的组数据读回不能冒充全32VRF
或完整scalar Spike差分，不把预算补跑PASS自动计入正式集合。

AKV V2四列对齐拒绝的后端候选暂不创建刺激、不启动VCS。
候选engine condition raw48/55分别对应vd和selector四列对齐
错误；父侧完整检查冻结Dispatcher的`is_akv2column`路径，
在发出请求前已拒绝`rd[8:7]!=0`、`rd>28`和`rs1[1:0]!=0`。
因此预想的`selector2/vd8`或`selector0/vd10`会在前端失败，
不能据此命中engine同类检查。零覆盖不等于可达缺口；先检查
所有producer及中间字段保持关系，再决定是否属于结构候选。
不以故意绕过Dispatcher的强制信号作为普通软件覆盖证据。

MaskM6/StA7的24cond native准备工具父侧14项测试PASS，
已完整阅读prepare/bind/artifact校验及薄Tcl hook、36个选择
与保护组。已对agent-owned配置执行实际check通过，seal为
`79d3fab018b585106a88ff50cfa6bf4ba1a143051422a19598602a03fa99c7b5`，
97项pins。配置仍为qualification-only、不支持直接launch，
需审核固定运行接口后才能执行，不据prepare结果批准豁免。

系统不可达候选仅继续静态筛选：冻结编译输入绑定
`cv64a6_imafdcv_sv39_config_pkg.sv`，其中
`CVA6ConfigHExtEn=0`，`RVH=bit'(CVA6ConfigHExtEn)`；
`build_config_pkg.sv`直接传递RVH，`ara_soc.sv`配置函数不覆盖
RVH，并设置`NrPMPEntries=0`。父侧已阅读这些源码及PTW
权限路径。该配置证据不能证明复合表达式的每个零点不可达：
只允许另行核对受常量支配的精确编译点，A/D、MXR、SUM、
普通页错误、superpage等可达路径继续保护。不生成或应用新EL。

LZC七组724项报告已实际进入DVE：`live-identity.json`记录实际
PID3088984和核实后的安装路径；父侧检查实际进程存在。不是
仅依据systemd活跃状态推断。终态百分比及保护/reset/reload
验收仍待完成，不频繁轮询。MaskM6/StA7源证明54个输入pins
父侧SHA复核全部一致，候选24条件/8分支、328个保护点；
此复核不替代原生资格及豁免批准。

父侧补充`test_vnclipu_wrong_pc_parent.py`两项测试PASS：原正确PC
仍通过；仅修改异常记录PC且确认恰好一次突变时，错误PC被拒绝。
补充文件SHA为
`af44f15550eced74e0dafec8dddcfa15435c02de54c8c4965c24da0296d46913`；
原46项测试的失败记录和原预检保持不变。额外审查记录在
`vnclipu-reject-parent-review-20261006-01.json`。已授权systemd
unit `ara-vnclipu-reject-parent-20261006-01.service`使用原封存
runner启动，预算1200秒、NO_FSDB、收集commit/vector/VDB；
结果须经完整对比、事务核验和正增量检查，当前尚未准入。

MaskM6/StA7结构候选独立复核54pins零差异，与six-policy全部
5808目标重复0点；32个候选在725中仍为零。8个分支点与原
debug策略保护清单冲突，保持HOLD，不直接追加EL；只准备
另外24个条件点的原生资格核验。SlideAddrGenA8保护不变。

725项正式集合另经独立只读verify成功，seal及724项精确前缀、
191个条件增量和12个目标绑定均通过；不替代全量DVE报告。

新普通RVV激励`vnclipu_wx_width_alignment_reject`已完成Spike预检：
2346项自检、312826条退休指令、全32寄存器三次快照、精确非法
异常及合法饱和恢复。五个预定编译覆盖点在725中仍未命中。
预检seal为`050ae5ca2acd8883847eb9fff51195df17b801ac2f341f27aa79b3fab2856927`，
父侧runner准备seal为
`ef5c7e20913f9009894db4ae6ca24e4709bfc20ad61412d328e347621c2f16a3`；
尚未启动VCS、尚未计入覆盖率。父侧46项测试中45项PASS，
`test_wrong_fault_pc`负例失败：实际异常行PC为
`0x0000000080002608`，测试用未补零字符串替换，未产生任何突变。
须用后继测试验证恰好修改一次异常PC并被拒绝，原封存文件不改。

LZC恢复v2在准备前加入了仅对已核实Z状态进程的处理；准备pins
与实际源码一致。父侧最终8项进程检查测试PASS，不忽略状态
不明的空命令进程或潜在EDA进程。当前仍在核验输入，不能
将systemd主进程存活解释成DVE已开始。

LZC前台恢复v2只修正进程身份检查：准确识别无关的`(sd-pam)`，
潜在EDA进程的身份或cwd不可读取时仍拒绝启动。与MaskM6/StA7
源证明共20项父侧单元测试通过。恢复计划seal为
`6d018959be4f4587f7a81179f38fce80d4a1a1013bfcd2eb3eefc77416b045be`，
unit为`ara-lzc-seven-foreground-v2-724-parent-20261006-01.service`。
原短启动器与后台claim保留；恢复进程直接调用封存的汇总流程，
不重新仿真、不改RTL，不将这份724项运行解释成725项报告。

QBS检查环境v3的源码绑定及load完成窗口修正经39项测试PASS，
实际prepare核验443项pins。实际collect又发现有限CVX事务ID
跨阶段复用被全程序唯一性误判：两个QBS命令均使用trans_id=0，
分别在cycle18125和61547完成请求/响应，没有在途重叠。父侧
直接核对原始commit CSV确认该事实。每个请求的匹配已经按
arch_start/退休窗口限定且要求唯一，不能再要求同opcode/ID在
整个程序只能出现一次。v3失败sidecar保持封存，后继修正须
增加合法ID复用正例及同窗口重复响应负例，不放宽在途守恒、
实际写字节或全寄存器/CSR/source检查；无需重跑VCS。

724项LZC runtime准备进程实际退出1，未生成runtime目录，
也未启动DVE。已有七组应用计划及六组配置仍完整保留；正在
只读定位具体环境拒绝，不能将准备失败算作RTL失败或批准
新的豁免。原723项DVE进程未被更改。

下一条普通RVV激励已完成软件预检：同组indexed load，e32/m2，
v8同时用作index/destination，VL37/vstart13。冻结operand queue
路径的snapshot replay起始word offset为1，724中四lane共
12cond/4branch目标仍为0。已有重叠激励vstart0，不覆盖此边界。
Spike实际457检查PASS、0异常；尚未在DUT运行，不计入覆盖。

GAP105实际单次raw读取及相对正式724的OR诊断已经完成，目录
`gap105-raw-diagnostic-parent-724-20261006-01`。新增条件191点：
bank0 payload 9点、bank1 adapter 44点、bank1 payload 138点，
line/branch/FSM新增均0。预定12个跨字边界目标全部命中；
shape21503/checksum2947893042匹配冻结编译布局。
single bitmap SHA
`a5f2cf4ab435a719693042898073c9139d40ab5086d3d97c355f75e202a65f56`。
该结果只保留为实际诊断，不在独立资格完成前计入正式集合，
也不换算成DVE百分比。后续复用封存单次raw结果，不重复仿真。

GAP105已实际终态，VCS CPU187.480秒；两阶段各17项检查、
总41项自检PASS，51请求/响应、0异常/协议错误/剩余请求。
这些是运行及自检证据，不等于独立准入。父侧实际调用native
检查器发现其要求普通向量load完成早于标量退休，和当前接口
不符：phase0四个seed load退休17233/17240/17248/17309，
完成17309/17375/17440/17504；QBS命令完成18125、退休18127，
phase1命令完成61547、退休61549。两轮数据均有同样边界。
原始拒绝记录保存在`native-checker-v1-rejection.json`；后继
检查需按真实allocation/done限制seed写窗口，并保证consumer
安全、全字节比对及两组生命周期一致，不能简单去掉检查。
不修改RTL、不重跑VCS、不将该检查器拒绝当成已定位RTL bug。

父侧已实际完成724项独立六组汇总配置，10335项pins，seal
`32d8deca7e562af7e5e0f8f28768d386772ecfc1c9f3908c193f9d2e5ce0d7cd`。
该配置未启动额外六组DVE。724项七组应用计划也已实际完成，
seal `325daa9245b1cef74cd8eb602d1e21f69c5abf4da78503af6fad69d44764ad46`，
绑定11157项pins、5868目标和17702保护点。父侧完整阅读新的
Tcl/运行核验/启动工具及测试，13项测试PASS，包括合并加载
次序、完整4200个LZC位置的保护和依赖遗漏拒绝。已启动后台
runtime配置准备；还没有启动七组DVE或批准新增豁免，不改变
723项正在运行的报告任务。

QBS完整software/native检查器实际26项测试PASS，明确不声称
full scalar ISA等价。它核验独立native解包/整数MAC、全部
seed和两次全VRF快照、24项CSR/source/guard，以及请求响应、
精确退休PC和两组生命周期探针的一致性。实际prepare发现
原runner的66-file image清单不含build-source-pins.json的绑定，
因此在收集前拒绝。正在补精确冻结源码manifest绑定的后继
工具；不放宽检查，不改旧配置，不重跑仍在运行的VCS。

GAP105 runner父侧完整源码审查及15项测试PASS，实际prepare
核验425项pins，seal
`85aff7d4b148a4eba850d48728fccda2c5c97d67df81e285c473bcfc19fa29d2`。
单次后台任务`ara-gap105-m8-phase8-parent-20261006-01.service`
已启动，父侧确认实际VCS PID3055282、冻结simv exe、独立cwd
和初始化日志，确认时elapsed30秒/CPU66.2%。目录
`gap105-m8-phase8-old-image-parent-20261006-01`，预算1200秒，
NO_FSDB，不自动重试。`parent-live-identity.json`只是进程观察
记录，不是功能PASS；现有正式724集合保持不变。完成后还需
完整独立检查及相对724重算实际覆盖，不根据退出0直接准入。

父侧已实际完成AKV生命周期正式准入，最新旧镜像集合为724项。
目录`akv-lifecycle-offline-admitted-724-parent-20261006-01`，seal
`c7070c02860d4a6f5e12f405f926cd19fc6e6498d1905298e5e32826ee3a8ae0`。
原723项有序前缀完整保留，只追加已独立检查的生命周期VDB；
未混入历史FAIL、R2 FAIL或未完成准入的预算补跑。原始增量为
line3/cond4/branch3/FSM0。正在运行的DVE仍固定723项，不修改
其配置，不将该报告或717项百分比冒称724项统计。

GAP105软件预检353项输入/输出及产物hash由父侧实际核验，
零不匹配，preflight seal
`c8992acc83cd3bb51d75518ba6e7383e2c6b453375c929807bf30d5bf63fd28d`。
ELF SHA `d18a70425176dc76f001fcca80a4f6ab88571164f57aca8469428528cd106565`。
软件检查不是RTL PASS；VCS启动及严格资格检查另行完成。

LZC七组独立应用计划父侧已完整审查，4项测试PASS；精确追加
60个cond，原六组EL字节不变，5868目标、17702保护点。
计划要求同一DVE会话的合并加载/复位/重载和非目标保护审计，
尚未完成这些门控，不纳入正式豁免，也不更改正在运行的六组。

GAP105的实际软件预检已生成在
`gap105-m8-phase8-preflight-723-20261006-03`，两次QBS命令分别
使用activation phase4和phase8。父侧已阅读独立native-byte点积、
M8打包参考、ELF检查和Spike能力探针。host检查44项及34个
错误注入反例通过，实际ELF已生成；Spike只验证自定义指令不被
该Spike实现支持，不宣称QBS数值执行通过。尚未取得RTL运行
及覆盖命中证据，不计入PASS集合。

LZC补充证明限定完全由padding常量零叶子驱动的selector子树：
初始化过程只能为X或0，不能产生已知1；真实输入的X/Z不在
这些子树的fanin中。父侧完整审查证明工具并运行5项测试PASS，
对补充审查目录3668项输入/输出pins核验零差异。该证明没有
测量DVE仪器的X处理语义，也没有批准新的合并豁免；原生false
及未知状态仍需保护，60个分支点继续HOLD。

AKV正式724准入工具已完成父侧全文件审查和12项测试PASS，
候选工具36项测试亦通过。工具复用封存的完整独立检查和raw
bitmap，核对723前缀、ELF唯一性、实际正增量及输入一致性；
独立审查未发现阻断性漏洞。实际prepare正在执行，完成正式
admit前，最新集合仍为723，不把准备完成当作准入完成。

父侧实际单次读取AKV VDB并相对正式723重算覆盖，目录
`akv-lifecycle-raw-parent-723-20261006-01`。原始增量为
line3/cond4/branch3/FSM0，限定AKV engine；四个cond目标
raw8/194/199/201在723均为0、本测试均为1，shape392和checksum
2836473276完全相同。bitmap combine验证精确723前缀且候选
VDB不重复；724只是待批准的原始联合，不是正式集合。
single-raw seal
`f6a5501fb3d819f7da22f48b31ff9d34d3eda6d32b4b825d9c2d49acd8c90289`。
不重复VCS、完整ISA资格回放或rawcollect；正式准入工具绑定
现有封存资格和single结果，723正在运行的DVE配置保持不变。

723 DVE实际启动已由父侧核实：PID3042302，exe为宿主机
V-2023.12-SP1的dve.exe，cwd为
`branch-combo-six-policy-population-723-parent-20261006-02`，
runner记录`SIX_POLICY_DVE_STARTED`。不再只依据worker状态
声称EDA运行；等待完整结果，不持续轮询或重启。

LZC全批次实际完成，return0，8200.681秒。父侧重新执行
v5launch.verify，120候选/4200保护点的全部原生审计通过，
51240状态检查，global final empty、全部保存/重载/复位一致。
60个cond singleton取得准确原生身份；60个branch因找不到
精确native父表达式继续HOLD。该结果明确
four_state_initialization_qualified=false、实际新增豁免0；不能
跳过此门控。父侧核对源码padding leaf为常量0、上层selector
为子树OR，安排补充任意真实输入X下的padding选择器稳定值和
初始delta行为证明，不把未收敛瞬态或未知原生ID一起屏蔽。

AKV生命周期v3资格实际完成，父侧完整源码审查并执行12项编译
绑定测试PASS。目录`akv-lifecycle-parent-native-scalar-qualification-20261006-03`，
seal `e27229c47359b655eda66c246d652c7b941798c384263736d0e4b60c395bef50`。
父侧再次独立核验253项输入/输出SHA，零不匹配。完整154769条
标量退休、104854次GPR写回匹配，无跳过/未知状态/差分错误；
4096字节seed、128字节custom写回、320次全VRF快照store和4次
异常/恢复均与独立有界ISA/custom模型匹配。该参考不是原生
custom Spike执行。compiled source/392条件shape/四目标精确
绑定已验证，尚未重算相对723原始增量，不能据此宣称已准入。

下一条QBS payload激励已完成父侧静态预检代码及723重绑定
审查，11项测试PASS。M8/Q5_K、activation phase8可在跨32-byte
字边界时触发bank1的pending byte12..15，12个精确编译条件点
目前仍为零；phase4作为对照。输出256*(context+1)可精确表示，
软件native-byte期望不依赖DUT。这里只是源码路由预测，尚无
实际ELF/Spike/VCS命中，不将预测计入覆盖；正在准备带全VRF、
CSR和guard核验的单条应用，禁止为预测结果豁免可达条件。

723单次后台worker已实际启动，PID3037448；父侧ps确认进程
存在且CPU98.7%，/proc/cwd与独立输出目录一致。launcher已结束，
worker正在启动前输入核验，actual_dve_pid_confirmed仍为false；
不能据此宣称DVE已运行或报告已生成。不持续轮询，等待实际
DVE启动与终态完整校验，不重复launch。

父侧723六policy v2实际prepare完成，10231项pins、5808目标、
13562保护点，config seal
`391d4ae3ff427ba27f33fa6b7c47f7ccd7f193c92969b6daeccd4ad5ed9f3bc5`。
独立launch-entry完成，seal
`df868a628fbd1154999c118fbe339c004adc3fa2d5f0b1e16509d533eaea1632`，
明确绑定formal723与冻结dispatcher快照，不读当前dispatcher。
父侧复核计划后执行单次background launcher，目录
`branch-combo-six-policy-population-723-parent-20261006-02`。
启动仍需确认实际DVE进程；新百分比必须等完整原生保护和
save/reload/reset核验后公布，不继承717百分比，不自动retry。

R2离线首错归因已得到独立Spike及架构trace支持，报告
`memory-emul-r2-parent-failure-diagnosis-20261006-01.json`。
完整4229检查中22项失败；两个VILL普通访存PC
0x80002cd0/0x80002e80实际正常退休，期望进入非法指令handler。
首次标量差分在102100条匹配退休之后出现，第三条EMUL上界
store则确实异常。全部VRF快照比较没有字节差异，不代表异常
语义正确。父侧核对冻结dispatcher：VSET非法配置归一化为
VILL/VL0；普通memory译码没有同等VILL拒绝，5898之后的
zero-length逻辑在未报异常时清ara_req_valid并响应空操作。
这是源码和架构证据支持的根因，尚非内部逐周期波形证明；
保留区分信号和原VDB，不修RTL、不将其上界命中单独纳入。

723汇总工具v2仅新增封存/usr/bin/cc->gcc身份检查，不允许任意
链接；父侧完整源码/测试审查并执行15项测试PASS，独立新输出
`branch-combo-six-policy-population-723-parent-20261006-02`实际
prepare已启动。AKV checker v2完整差分审查与30项测试PASS，
修正完整terminal字段及VSET response=64比较，没有改变DUT。

父侧实际尝试723六policy汇总prepare，因R1新输入中的
`/usr/bin/cc -> gcc`不在冻结工具软链接白名单而拒绝。
未生成输出目录/config，未启动DVE；不是测试失败或覆盖数据
问题。只允许在独立successor中新增此精确工具链接，必须核验
link target、resolved常规文件及准入封存的完整SHA，不能放宽
至任意软链接，也不能修改既有冻结汇总工具或删掉输入证据。

AKV生命周期v2实际VCS于15:45:34结束，CPU512.620秒，日志
Core SUCCESS、426请求/响应、4异常、协议错误0。完整独立
scalar/native资格仍待验收。父侧全读新oracle/checker并执行
44项单元测试PASS，同时发现stdout contract正则没有接受实际
日志的req_stalled/resp_stalled字段，安排独立successor修正及
负向测试；不会为日志解析错误重跑VCS，也不提前准入VDB。

父侧复核R2实际终态日志：`memory-emul-r2-old-image-parent-20261006-01`
的simulation-status记录returncode=0，但run.vcs.log在
322206500000fs报告`test wrote failure value 0000000000000003 to tohost`。
contract为319请求/319响应、1异常、0协议错误；不能用操作系统
返回码代替测试判定，也不能在期望3异常未满足时准入。VDB保留
但排除有效集合；按实际trace进行只读首错诊断，尚未确定RTL
根因，不修RTL、不自动重新仿真。

父侧完成R1正式723准入：prepared seal
`96f69e5264a5baa29070372a931aa7ecaf96c0c73852d33796a5953c1bbad32d`，
独立verify通过后执行admit；admission seal
`2f68f64b880b95164f8db6aa2b569d305bd831ad4a05056563b2ab42eade45a4`。
父侧另行核对全部14个输出产品哈希、精确722前缀和723个唯一
测试成员，无不匹配。严格证据包含488341条标量退休、320487次
GPR写回、37362次标量访存、33条向量写回4100bytes、26个完整
VRF快照、15489项检查及24次精确异常。唯一未命中raw539仍受
保护、不豁免；历史失败不纳入，未声明新RTL signoff或历史全量
重验。通用DVE单次后台runner父侧测试现为11项PASS（此前8项
记录是旧阶段），下一批配置须明确绑定本次723准入seal。

父侧对正式722原始bitmap追加按缺口数量排序的只读复核，发现
QBS payload buffer的条件点缺口远大于decoder：bank1为
16206/21503命中（5297未命中），bank0为17352/21503（4151
未命中）；block adapter bank1条件4800/5914、bank0为5146/5914。
这些只是原始编译条件bit计数，不等于控制场景数，也不是DVE
豁免后百分比。下一步先区分有效量化数据、bank切换/尾块等
可达组合与参数特化的结构性不可达点，再决定数据pattern刺激
或精确豁免，不能因零覆盖大而整体屏蔽payload模块。

R1唯一未命中line2224属于VNSRL的`ara_req.emul.next()`为
LMUL_RSVD时的非法源组拒绝。保留零点并要求源码/译码路径
分析；不能因其他24异常均通过便宣布所有拒绝路径已覆盖。

AKV生命周期runner完成父侧全源码及20项测试PASS，实际prepare
179项输入；prepared seal：
`e3acf310ba9d2a1b0d260c3052ccc2fcd67be27bd5efbde4125a930f3ae6c951`。
已单次启动unit `ara-akv-lifecycle-parent-20261006-01.service`，
实际VCS PID3016527确认运行并装载原生custom ELF（不是软件
参考ELF），目录`akv-lifecycle-old-image-parent-20261006-01`。
预算600秒，不持续轮询，不自动重启；尚无完整scalar/native
资格及覆盖准入声明，保持严格终态验收要求。

通用六policy单次后台runner已完成父侧全源码与8项测试复审。
封存配置、原始生命周期、完整native保护验证保持不变；使用
排他claim防止重复启动，worker握手绑定父侧记录，不自动retry。
尚未启动新DVE汇总，等待R1正式723人口封存之后按批次执行。

R1实际严格collector完成，结果为
`R1_CACHED_STRICT_CANDIDATE_VERIFIED_NOT_ADMITTED`，目录
`narrow-reject-r1-cached-strict-candidate-719-20261006-01`。
488341条标量退休、320487次GPR写回、37362次标量访存匹配，
无跳过或首错；33条向量写回比较4100bytes通过且未知跳过为0。
原45目标中44命中，唯一未命中为dispatcher line2224/raw539，
继续保留该缺口，不能将软件PASS冒充全部目标命中。
父侧已独立重算相对正式722集合：line15/cond14/branch15/FSM0
仍为新覆盖，不是沿用旧719增量。尚未正式准入723，要求重新
绑定最新722完整前缀并重放严格结果，失败VDB仍排除。

R2严格终态collector完成父侧全源码及40项测试复审，全部PASS。
门控区分同opcode合法和非法实例，按实际arch_seq/响应异常
分类；检查完整7快照、3异常、恢复、35向量写回及保护区。
仍以正式722为诊断基线，最终准入须相对届时最新集合重算。

AKV生命周期v2独立预检完成父侧全源码审查（应用、基础builder
及successor）与24项测试PASS，随后父侧实际重放108项输入
哈希、原生ELF十个精确custom站点及完整软件Spike参考均通过。
seal `acbc1d702e22a2c33bafe40c689051175f3bd09acf3187eea3aef05cddf70aad`，
目录`akv-lifecycle-preflight-721-20261006-02`。7735软件检查与
40960-byte快照、480-byte CSR、四次语义拒绝只是预检证据，
尚非DUT结果；DUT预计7740检查和128-byte恢复写回。
源码已确认REFILL失败清context_ready，命令返回CSR在任何
snapshot VSET前采集。下一步准备runner及严格native/完整scalar
资格检查，正式增量按最新722或之后的封存集合重算，不沿用721。

722六组既有豁免的DVE准备配置已完成：
`branch-combo-six-policy-population-722-20261006-01/config.json`，
SHA `3df4ba085eafcccc3c6b40080a77abbdb314fb638492758c5ff7088950083fbc`。
保持5808目标和13562保护点，未启动DVE、不继承旧百分比。
四低界compiled映射测试4项PASS，不将XML编号当GUI对象资格。

R1单次旧镜像VCS于2026-10-06 15:30:09 PDT正常结束，return0，
CPU耗时1657.380秒；1164请求/响应、24预期异常，protocol_errors
与outstanding均0。只说明仿真正常完成，严格逐指令和全快照
验收未完成，不直接准入VDB，原重型案例与历史记录不覆盖。

R2 runner完成父侧全源码复审、12项测试PASS及prepare/verify。
prepared seal：
`04367aceccce9e5d60f5a72319164acee39b3ebe628d7590032b230c994e8761`。
已启动独立后台unit `ara-memory-emul-r2-parent-20261006-01.service`，
主进程3010054，单次1200秒预算，目录
`memory-emul-r2-old-image-parent-20261006-01`；仅普通合法EMUL
上界两点为测量目标，低界四点HOLD。实际VCS子进程3010458
已确认运行，console确认装载精确预检ELF并启动trace。运行中
不准入、不重复启动，完成后再检查终态及严格独立差分。

四点memory EMUL低界source/config候选已封存并由父侧实际
重算验证，seal：
`586049b47fb28bcc95dbe3a40e006df21351eeb13210a7b8776973a27652425b`。
文件`memory-emul-r2-lower-source-config-candidate-721-20261006-01.json`。
精确候选为dispatcher line1228/1311、branch360/414；完整输入
哈希、冻结vtype写入/规范化路径及92状态编码证明均验证通过。
原生身份核验状态仍为HOLD_NOT_EXECUTED，exclusions_generated
与waiver_applied均false，不改变实际覆盖百分比或分母。

722准入后另外核验12份正式输出哈希、722唯一VDB及完整721
有序前缀通过。新一轮普通RVV缺口只读审计分配给独立代理，
避免重复R1/R2及AKV生命周期组合；仍不改RTL、不自动重跑旧失败。

GAP104已由父侧实际执行v2 admit完成正式准入，最新集合722项。
目录`gap104-offline-admitted-722-20261006-02`，admission seal：
`b9ad9d11e0eeb709ebcf3e4bd6d5ccbdd94d4a229e9c80b144ef10cf8213415a`。
admit重新核验独立完整scalar/vector、异常、软件及单例VDB证据，
原721前缀完整保留，仅追加唯一GAP104成功VDB，实际新增line2、
branch2，cond/FSM无新增。历史失败仍排除。此为旧镜像历史集合
准入，不是新RTL signoff；完整DVE百分比尚未导出，不继承717数字。

四个memory EMUL低界候选的源码/配置证据helper及12项测试已
完成父侧复审。92种合法或规范化VILL编码状态均不触发低界真
分支；保留reset/default/上界及所有非目标保护点。只批准准备
候选封存，原生DVE对象身份、EL保存/重载及保护点验证仍HOLD，
尚未添加或应用任何新豁免。

GAP104正式入库v1准备未通过的原因已定位为完整tracer结果中
tuple与JSON数组的表示差异，不是DUT差分错误。拒绝记录保留于
`gap104-admission-prepare-rejection-20261006-01.json`；v2只将
完整tracer结构经JSON规范化再逐字段比较，保留PC、cause、tval、
时间及尾部指令检查，未删除检查项。父侧已审查原版与v2完整
diff及18项测试PASS，含实际trace和字段变异拒绝测试。
等待v2正式准备封存，未宣称覆盖集合已经增加。

R2实际封存预检经父侧独立verify通过，seal：
`1f3ae5b8faf7195a6eca0f29688ed8d8b4e03c90ee09fc6f7fc806fd76514245`。
独立Spike退休218111条、4229检查、7份完整VRF快照及3次精确
预期异常；仅上界两个目标有合法vtype触发，低界四目标仍HOLD。
该结果不是RTL测试通过，也未计入覆盖率。完整fixture负向
测试已指定R2_PREFLIGHT执行完毕，35项全PASS、0 skip，耗时
32.425秒；避免把此前25项skip当作验收。下一步准备独立runner
与严格终态collector，复审后只启动一次有界旧镜像VCS。

父侧完整审查R2 memory EMUL preflight，确认应区分VILL诊断和
真正访存EMUL低界触发。当前ELEN64、最小EEW8，合法vtype要求
LMUL>=SEW/ELEN，因此EMUL=LMUL*EEW/SEW>=1/8。
e64/mf8先成为VILL、VL=0，不能证明命中了访存低界条件。
原六个目标中只保留上界store的line1308/branch362为实际刺激
候选，另四个低界目标保持HOLD，准备冻结源码/配置及原生覆盖
点的不可达资格证据，尚未应用豁免。父侧测试运行35项中10项
执行、25项skip，不能表述为35项全部PASS；实际封存fixture的
完整回放验收尚待完成，未启动R2 VCS。

GAP104正式入库helper已完成父侧全源码复审与15项测试PASS，
实际重新计算标量/向量、异常、软件契约及单例VDB，不只信任
candidate状态。原721封存前缀必须完整保留、候选唯一且有真实
新增覆盖，拒绝零增益和历史FAIL混入。已反馈正式status需显式
声明coverage_admitted，等待封存准备产物后再执行正式准入。

父侧对GAP104 v2执行独立完整collector重放，输出目录
`gap104-strict-parent-candidate-721-20261006-01`；1309软件检查、
22479条标量退休、12107次GPR写回、2629次标量访存匹配，
完整8192-byte向量写回及VRF保留、两次异常精确PC/cause/tval、
guard和合法恢复均通过。相对正式721集合实际新增line2/branch2，
四个预定目标全部由该单例命中。代理candidate的6448项证据
哈希经父侧重核验零差异。正式准入尚未完成，不提前宣称722。

最新集合DVE准备工具已完成父侧全源码及测试复审，8项测试
PASS；明确绑定封存PASS人口，不扫描或追加候选/FAIL/TIMEOUT。
保留717百分比及既有5808豁免目标、13562保护点。721准备
产物未启动DVE，待下一批正式准入后用新的封存集合成批导出。

GAP104单次旧镜像VCS已于2026-10-06 15:16 PDT正常结束，
160次请求/响应、2次预期异常，协议错误和未完成请求均为0。
这仍不足以直接准入：父侧复审发现原collector误将异常时间字段
当作PC比较。保留原collector及失败诊断，新增v2解析实际PC、
精确tval和异常顺序，不修改RTL、不重跑已经完成的VCS。
父侧已检查v2异常解析源码；严格差分和覆盖增量仍待完整验收。
同期R1 VCS PID2978168和LZC原生资格DVE PID2888850经进程表
确认仍在运行，不因等待重启，也不使用其运行中VDB作正式统计。

GAP104已通过父侧完整runner复审与12项测试，prepare重建并核验
166项输入；prepared seal：
`294f161ac541db2b366717e6349e640526266eef7ff32d0c68488b95cc824ea0`。
2026-10-06 15:14 PDT启动一次600秒预算独立后台service：
`ara-gap104-whole-nf-parent-20261006-01.service`，实际VCS PID2992263
确认加载对应ELF，目录`gap104-whole-nf-reserved-old-image-parent-20261006-01`。
不重复启动，未宣称目标命中；后续实际增量相对正式721重算。

R1窄化拒绝矩阵终态collector已完成父侧全源码复审、46项测试
PASS（0 skip）及封存plan verify通过，未读取运行中结果作准入。
plan seal：`2459ff3afbd45c4ef10fd817a87b28809aa2c8d91e190678c9384de60effe1dc`。
collector要求24异常、26完整快照、15489检查、完整scalar/vector
差分、CSR/guard恢复及非法请求零backend/VRF活动；相对719只作
诊断，正式准入必须按最新集合重新计算，不假定45目标全部命中。

AKV列边界已正式准入，最新集合721项历史PASS，目录：
`akv-column-boundary-offline-admitted-721-20261006-01`。
admission seal：
`eda7720583e3232e97cd4486d7790a678abc108018f6acbd56d0b1c287e20c8b`。
父侧完整复审successor，13项测试全PASS，并实际执行admit内部
check重新重放独立scalar/native模型、封存输入及精确720前缀
并集，追加唯一成功AKV VDB。增量line2/cond3/branch2/FSM0，
原raw24未命中、不替换目标；旧FAIL/TIMEOUT不混入。
这是受限独立ISA/native契约通过，不冒称Spike支持custom。
最新DVE百分比未重新导出，不把717百分比标为721。

GAP104 whole-register NF保留编码激励已完成父侧源码/独立
预检helper复审，8项实际fixture测试全PASS；两编码
`0x42850407`/`0x42850427`分别验证3-register whole load/store
保留编码拒绝。1309检查保留两次精确异常、每phase全4096-byte
VRF、目标/guard不变、合法store恢复和CSR/handler恢复。
预检seal `eb59bfec48f20d1a9176241277cc2f6b01b6e496fa479d7a73b3f0e8c3ff53ac`。
正在准备独立600秒预算旧镜像runner，尚未启动DUT或准入。

历史AKV skew_context同ELF预算补跑已正常结束，终态为
`FULL_ORIGINAL_ORACLE_PASS_NOT_ADMITTED`，实际耗时2035.076秒。
原3237项检查及12阶段完成；bare-mode翻译计数规则仍由冻结
源契约约束，非依据测量值放宽。原TIMEOUT记录保留，不自动准入。
尚在父侧/代理独立复核结果封存；不冒称全ISA差分已完成。

AKV相对720的准入successor已加零覆盖增量拒绝gate，父侧13项
测试全部PASS，包括重复成员、错误前缀、错误bitmap、缺少scalar
资格及零增益案例拒绝测试。待准备产物封存后再独立执行准入，
当前正式集合仍720项，不提前计入721。

NO_TRAFFIC冻结源码successor已完成父侧完整review、5项测试PASS，
1918项输入/输出哈希重核验零差异；seal：
`ae1fa8e89d512df80ac434e63cce399cace9ab25d3e254f1118c648ee82fbf84`。
目录`uvm-no-traffic-snapshot-diagnostic-719-20261006-02`。
快照SHA精确绑定旧编译源路径；配置及CSR前端响应、非法指令
撤销后端请求的源码链已核实。只解除successor的dispatcher身份
缺口，不改原HOLD/seal、26例oracle policy或正式覆盖准入。

父侧已完整阅读相对720的AKV准入successor，12项既有测试PASS。
实际population测试相对720新增line2/cond3/branch2/FSM0。
复审要求新增零增量拒绝gate及负向测试，冻结前完成或保留原版
后创建successor；待新封存及独立重放完成，不提前正式准入。

父侧完整复审NO_TRAFFIC只读诊断器，5项测试PASS，并重新核验
1913项输入/输出文件SHA256，零差异；diagnostic seal为
`3f284421baa0db043c52a5f53ed918525de192b0732b55c72a65f27abc36e3a3`。
26例分为17例scalar（req/resp/VID为0）及9例frontend-only
（配置/CSR/预期非法拒绝，无backend VID）。不是26个RTL bug，
但原require_contract=false不因此提升为true，也不删除UVM错误。
该版本dispatcher读取当前源码造成身份HOLD；已安排用旧镜像
绑定的冻结dispatcher快照做新只读successor，原诊断保持不变。

AKV列边界准入v2的父侧19项负向/完整性测试全部PASS，包含
缺少scalar证据、错异常、未知/跳过结果、错误原生写回绑定拒绝。
v2基于719，当前已有GAP103正式720，因此禁止用v2生成平行720
谱系，正在准备相对正式720重新核算OR/delta及源点映射的successor。
不修改旧准备器、历史提案或封存证据，不提前宣布721。

GAP103已完成正式离线准入，最新集合为720项历史PASS：
`gap103-offline-admitted-720-20261006-01`，admission seal：
`2a39f961402fd2ec536f58672466583942b6407e2028638736145713ba13955e`。
父侧完整阅读准入helper，15项测试PASS；prepare及admit均重新
重放实际标量/向量/维护字节和单测试VDB，保持719原顺序再追加
一项。新增line1/cond6/branch3/FSM1，不含历史FAIL/TIMEOUT。
这不是重验全部历史案例，也不是最新DVE百分比或新RTL signoff。

AKV列边界独立标量解释器补证已完成父侧复审：42项测试PASS，
并在新目录`akv-column-scalar-parent-qualification-20261006-01`
独立重放全部103458条退休指令、76176次GPR写入、18698次load、
7819次store；skip/unknown/mismatch均零，一次精确异常由参考状态
独立推导。父侧qualification seal：
`d9af0f90b34bc18184475cc6fca067faa67f11ec91a704416443ca4c0b358495`。
实际ASIC FF GPR选择和CSR复位/dirty/MRET源码契约也已绑定。
此为受限独立ISA/native参考模型，不是Spike原生custom差分。
正在准备独立准入successor，旧hard-gate准备器不改写，正式仍719。

R1拒绝矩阵效率successor仅缓存独立期望值表，保留全部24次
非法异常、26次全VRF快照和15489项检查。实际Spike参考指令数
1049731降至488341（减少53.479%），这不是VCS耗时测量或预测。
原激励/预检保留。父侧真实fixture预检34项、runner11项测试全
PASS（0 skip），prepared契约verify通过；2026-10-06 15:01 PDT
启动独立1800秒预算后台service：
`ara-r1-cached-reject-719-20261006-01.service`。
实际VCS PID2978168已确认加载cached ELF及封存旧镜像，禁止重复
启动或频繁轮询，尚未准入。prepared seal：
`98b82c45f2bbde8c00c9b27f2de0f2bad9f079896ddc28e79ab218f99d969377`。

GAP103严格收集器父侧21项测试全部PASS（67.218秒），包括主动
破坏业务结果、源维护、前缀、尾部及缺字节/未知字节时的拒绝测试。
代理实际候选目录`gap103-strict-candidate-719-20261006-01`报告
branch138/105/100和line202命中，相对719增量为line1/cond6/
branch3/FSM1。父侧独立离线重放至
`gap103-strict-parent-check-719-20261006-01`已正常结束，严格架构
检查、目标命中及上述原始增量全部复核通过；候选不是正式准入。

历史AKV descriptor同镜像、同ELF预算补跑已结束，终态为
`FULL_ORIGINAL_ORACLE_PASS_NOT_ADMITTED`，实际耗时1199.322秒。
原6751项软件检查通过，130个请求/响应、23次预期异常、78个
backend微操作分配/完成均闭合；原TIMEOUT记录保留。此结果正在
独立核验封存与准入证据，尚未加入正式719项集合，不将其描述为
新增逐指令完整ISA差分通过。未修改RTL、镜像或原ELF。

GAP103窄化前缀仿真已结束，returncode=0、Core SUCCESS，
116个请求/响应、零异常/协议错误/未完成事务。仿真CPU350.540秒。
正在离线检查完整标量轨迹、向量结果及维护写回字节，并从实际
VDB核算增量；自检成功不直接作为正式准入或目标覆盖命中的证据。

AKV受限独立解释器已实现，父侧读完全部源码并运行29项测试PASS，
包含封存ELF与真实完整退休轨迹重放，以及错误GPR、控制流PC、
store数据、未知opcode/CSR、未知内存读取、不完整轨迹拒绝测试。
解释器step不接收DUT值，参考内存从ELF PT_LOAD/BSS及独立执行
更新，vector快照来自独立VRF模型，非法列自行产生精确异常。
尚在补充复位CSR/GPR、ASIC寄存器堆实际选择的源码契约绑定，
因此不提前宣布新的正式PASS准入，也不称为Spike原生custom差分。

R1窄化拒绝矩阵已完成父侧实fixture27项测试（0 skip），完整
Spike验证24个非法请求、15489项检查及26次32-register快照，
preflight seal为
`28e6b5130b62e9ec720e08247475ac33496c30e184726112c72a375ec9b2b09b`。
实测参考执行1049731条标量指令，原1--3分钟预估撤回，未盲目
启动长矩阵VCS。正在准备仅预计算独立期望表的successor，保留
所有trap、快照、guard、CSR及检查数，不使用实际snapshot生成gold。
新ELF将重新通过Spike并比较指令数后再启动，原产物保持不变。

AKV标量oracle方案已完成实际退休指令集合分析，正在实现受限、
未知操作立即拒绝的独立解释器。期望GPR、控制流、内存、CSR
从封存ELF和独立vector/custom语义生成，禁止从DUT轨迹回填。
使用已完成仿真的轨迹离线重放，不重新运行VCS；完成前不准入。

GAP103窄化前缀场景已完成父侧独立Spike重放，1245项检查、75项
输入pin一致，preflight seal：
`033ca91cb0e62dcf04655af186e8cf1a441c236d0d95bcf9d801f7a25cf5ddf4`。
参考公式从加载后canonical preimage取宽源及shift低5位，覆盖
prestart/tail及所有其他寄存器。源码证明32个独立vs1r.v快照
不触发源reshuffle也不写EEW布局记录，保留低半EW32/高半EW16。
父侧preflight8项、快照证明4项、runner9项测试全部PASS。
2026-10-06 14:46 PDT已启动单次600秒后台任务，service为
`ara-gap103-narrow-prefix-719-20261006-01.service`；prepared seal：
`47fa18201707989ec965570eec546cc7db18454e2ec182228f110b0f7c125edb`。
程序首先重建并核对全部封存契约，再启动VCS；不自动重试、未准入。

AKV新增2行/3条件/2分支虽然具有完整原生custom观察证据，但
剩余标量GPR/控制流/load-store尚未完成独立完整结果检查，准入
准备器维持hard gate。父侧读取准备器并执行7项测试PASS，没有
通过放宽检查或把指令身份匹配冒称标量结果对比来凑720项PASS。

父侧对719个VDB关联的历史日志进行了UVM诊断行补查：先扫描
926个邻近日志，再找到并检查53个嵌套日志，全部VDB均找到日志。
26个案例存在`VID/NO_TRAFFIC`或`CVXIF/NO_TRAFFIC`及非零summary，
已扫描日志未发现其他UVM错误标签。这个发现不等于26个RTL故障：
冻结UVM通用smoke在check_phase无条件要求向量请求及backend VID，
纯标量/CSR/vset/非法请求拒绝测试可能不应产生这些流量。
不过也不能直接忽略；已安排逐案例核对激励契约、实际流量和独立
oracle，原719准入与VDB不改动。该扫描仅是UVM诊断检查，不能
冒称重新完成719项全部架构差分或最终signoff。

AKV列边界离线收集器v5已修正UVM错误匹配，父侧42项测试
全部PASS，并独立重放原仿真产物。父核验目录为
`akv-column-boundary-v2-parent-v5-check-20261006-01`，seal：
`f449289ee1b5c547f3206fc950626ff73d54a29ea58598ceab0693af2c9dc259`。
核验覆盖完整4096-byte VRF、四次全VRF快照、388个custom有效
写回字节、24次边界CSR读回、非法列精确异常及恢复/释放路径。
此为原生custom独立参考检查，不冒称Spike支持custom或全标量差分。
父侧相对719诊断合并得到line2/condition3/branch2/FSM0；
预设raw24未命中，增量来自其他实际AKV/VLSU路径。正式准入仍待
完整证据及新增点身份核对，正式集合仍719，不改写DVE百分比。

父侧复审AKV列边界v4离线收集器：35项测试PASS，但发现UVM
错误行正则过度转义，会漏匹配`UVM_ERROR @ ...`。最小Python复现
证明旧正则返回空、正确正则可捕获错误行。此为验证收集器问题，
不是新RTL故障；已要求新建successor并增加错误/非零summary负测，
原收集器与结果保持不变。修正并重放真实日志前不准入该案例。

下一条覆盖激励正在准备：e16/m4、VL129、vstart13的
`vnsrl.wv v8,v8,v12`，先分别建立宽源与窄shift源的布局。
目标是冻结dispatcher中尚未命中的narrow prefix及snapshot返回
路径；要求独立canonical preimage、全4096-byte VRF、源内存
guards和CSR核验。当前仅静态假设，尚未运行VCS、未计覆盖增量。

2026-10-06 14:34 PDT：两个历史超时案例已由父侧核对源码证明及
v2四项测试后并行启动，实际VCS PID分别为2947764、2947780。
保持旧镜像、原ELF和完整检查数，不修改RTL：

- `akv-gap35-descriptor-budget1800-old-image-717-20261006-02`：
  预算1800秒，6751项检查；service为
  `ara-akv-gap35-budget1800-20261006-02.service`。
- `akv-gap46-skew-context-budget3000-old-image-717-20261006-02`：
  预算3000秒，3237项检查；service为
  `ara-akv-gap46-budget3000-20261006-02.service`。

裸地址检查器订正绑定旧镜像编译源码及原ELF：SATP/VSATP复位为0，
ELF无翻译CSR写入，translation计数只在使能翻译且完成翻译时递增，
所以应严格为0，而非旧检查器要求的至少4次。其他数据、CSR、trap、
协议和PERF检查保留。两路尚未准入，不增加正式PASS数量。

AKV列边界v2仿真已正常结束，日志SUCCESS，196次请求/响应配平、
协议错误0，VCS CPU时间358.240秒；完整独立数据核验仍在进行，
暂未计入覆盖率。原失败/超时记录保留，不以新fixture替代原ELF闭环。

最新正式准入集合已提升为719项PASS，目录
`gap102b-offline-admitted-719-20261006-01`。父侧读取准入helper、
12项测试全PASS，并独立完成6228项输入与实际scalar/vector/维护
写回证据重放。admission seal为
`0edf5405a8139eea50d82af6181f7d53ccb70699c2b232c8e3001add0ec242bb`。
严格保留718前缀，只新增GAP102B；相对718新增line1/branch1，
condition/FSM无增量。相对原717两项合计line2/condition1/branch2。
DVE百分比仍以717报告为准，待更多有效增量成批汇总，未把719的
raw点数换算成未经DVE导出的百分比。所有失败/超时VDB仍排除。

最新正式准入集合为718项PASS，目录
`opivx-vsbc-vd0-offline-admitted-718-20261006-01`。父侧读取准入
helper并执行15项测试全PASS，独立`verify`完成全部封存证据重建，
确认原717顺序保留、新增VSBC一项、正增量和编译XML身份一致。
admission seal为
`ce3d7568cc0a14efece87975098a94f207b2d43119cc1e7720021c14a56f6f8e`。
相对717新增line1/condition1/branch1/FSM0；未重跑DVE，因此下文
717项百分比仍只代表717项，不能标成718项的最新百分比。

AKV修正版v2已完成父侧原/新源码差异审查、运行器审查及27项测试，
全部通过。修正inactive seed预期，保留完整四帧8192元素检查并新增
24个CSR读回；专用命令仍为原8条。一次900秒预算旧镜像VCS已启动，
service为`ara-akv-column-boundary-v2-old-image-20261006-01.service`，
实际VCS PID2934809已确认。preflight seal为
`629dce5e446f002cf5ea7ec84895ee923b3a8c12fcf1df298f7d15253f89677d`，
prepared seal为
`7c8f3564b941ef167ff7c6156be5072f0eaefe74837e2f107a5f95adc735d974`。
原失败测试/ELF与timeout保留。当前只证明预检和启动，不证明DUT
PASS或覆盖准入；Spike仍是软件参考，不是native AKV指令执行。

GAP102B strict successor03完成父侧复核：21项主检查器测试和3项
逐写回补充测试全PASS，198项证据哈希零差异。qualification seal为
`8176e9ce76d98b05432313b091202ab916cde5f810c3ca447b55decbb534e2a7`。
保留shared comparer的5252字节比较和128字节skip原始记录，独立
audit核5382个uop有效写字节，逐字节去shuffle与oracle匹配，包括
维护v14全部128字节、源active2字节及MAC active4字节；无未知字节。
完整快照、CSR、保护区、723项自检、35366条标量提交和84/84事务
均通过。已授权待VSBC718封存后创建719集合并重新算相对718增量，
目前不能将717项DVE百分比当作719项报告。原失败collector不覆盖。

GAP102B父侧逐record审查进一步确认：实际比较5252字节，
`skipped_unknown_bytes=128`（总计与最后MAC record一致），并非
逐字节零跳过。最后MAC有2条uop、81次write event，活跃结果4字节
被比较；额外128字节必须按维护写回/保留元素独立补证。已要求
successor严格核实际写回去shuffle、preimage和完整VRF快照，不把
mask外写回无条件忽略，也不把现有PASS标签当作全部字节已验证。
该case仍未准入，不需要为检查器口径修正重跑RTL。

GAP102B实际VCS自检SUCCESS，CPU124.780秒，requests84/responses84，
exceptions0/protocol_errors0/outstanding0。父侧独立读取其实际VDB，
确认dispatcher raw127命中；相对717项新增line1/branch1，cond/FSM
无新增。原始诊断输入位于`gap102b-raw-parent-probe-20261006-01`。
标量和向量差分、723项自检均通过，但collector将5504个Spike
声明字节误当成RTL比较字节而拒收；实际比较5252字节。该拒收
尚在按部分写回/保留元素契约严格修正，未准入，不视作DUT失败，
也不直接把检查器预期改成实测值。

VSBC strict candidate已由父侧独立验收：31项实际日志测试全PASS，
191项封存输入哈希零差异；status seal为
`b7a991e6d1f6fdb5f850d012b201322d8dfadbf4da6cb21b19f885898cea4c53`。
11444条标量指令、7219次寄存器写和912次标量内存访问匹配；
4条向量结果388字节严格匹配。非法请求无backend分配或VRF活动，
精确异常、vstart保持、完整快照及恢复均通过。相对717项实际新增
line1/condition1/branch1/FSM0，已授权生成独立718项集合，尚待
集合产物验收，不能提前把717项报告标成718项。

AKV TIMEOUT离线诊断发现测试适配器错误：它要求inactive column
元素清零，而冻结RTL的byte enable仅覆盖active token，现有软件
reference也保持inactive元素。126次差异均为前两帧v8[1..63]保持
原seed，不能归为RTL bug。实际custom写回388字节，原预期640
字节错误。原ELF/预检/TIMEOUT保留且不准入；已授权新软件/oracle
successor预检，暂不重跑VCS。诊断seal为
`4a157591f3cc1aeeb3bd5fd84c5839a276830f51ef9c024890ffc2bf40c07011`，
父侧核验5项直接证据哈希零差异。

历史nonPASS successor审计已完成父侧1056个输入文件哈希核验，零差异。
目录`historical-nonpass-membership-reconciliation-717-20261006-01`。
原30组中20组已有同镜像同ELF PASS并在717中；加closure92与GAP101
后合计32组，剩余12组（11个case名）未完成运行/准入闭环。类别为
7组未找到匹配PASS、4组仅其他ELF或身份未证PASS、1组仅不同镜像
同ELF PASS。此核对更新此前16/14的阶段清单，不删历史记录，
不将12组解释成12个已确定RTL bug。

VSBC场景VCS已正常结束，自检SUCCESS，CPU47.630秒；contract为
requests32/responses32/exceptions1/protocol_errors0/outstanding0。仍须
完整差分与目标bitmap验收，不能仅凭tohost宣称新成员准入。
AKV列边界场景300秒预算结束，记录为TIMEOUT，未纳入覆盖率。
console显示全部8条专用命令均完成（含一次预期SELECTOR拒绝、恢复
读取和release）；最后完整retire为cycle104819/order67955，PC
`0x80002c18`。尚在离线核对末PC与检查循环，不将预算超时判成RTL bug。

717项六policy DVE报告已完成，父侧独立执行`read_config`和
`verify_artifacts`通过。5808目标、13562保护点共19370点完成核验，
raw/reset CSV逐字节相同；报告结果seal为
`72385671421520a7d33023d9de369fe3792163be31f6dc1e2091e2a37e54c8b7`。
以下均为旧镜像`i_system`层级，不能用于新RTL signoff；已有豁免
应用后的分支提升属于分母调整，而非本轮新增激励命中。

| 717项旧镜像报告 | Line | Condition | Branch | FSM | Toggle | Score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 原始 | 85.13% | 81.85% | 82.86% | 60.46% | 63.17% | 74.70% |
| 应用六组已有豁免 | 85.13% | 81.85% | 87.61% | 60.46% | 63.17% | 75.64% |

该报告仍标记`official_denominator_verified=false`，不冒充最终
signoff豁免审批。本轮LZC/FSM候选没有加入六组已有政策。

GAP102B一次600秒预算VCS已启动，独立目录
`gap102b-widen-acc-vstart-old-image-717-20261006-01`，实际VCS
PID2917037已确认，prepared seal为
`767835e44c1c2f952645f2e12045defad1ce20d77e6fa346d593acdd5cfcbd59`。
该测试尚待DUT功能和target127覆盖增量验收，不修改RTL。

VSBC OPIVX非法vd0场景已通过父侧21项实际日志检查器测试，零skip，
并独立核验旧镜像66文件及全部运行输入。一次600秒预算的VCS已启动，
目录`opivx-vsbc-vd0-old-image-717-20261006-01`，实际VCS PID2913411。
预检seal为`3b4e1c23901fe45c0b1e5434e7f244d2a8e041b103e0e0315cfd59ef685e3d09`。
非法请求的精确异常、无向量写回、vstart保持及合法恢复仍待DUT验收；
未增加717项准入数，也未改RTL。此前静态去重曾使用ZCC objdump，
已记录工具来源并用非ZCC工具重新核对；本次编译及后续执行不用ZCC。

GAP102B预检由父侧独立重放，16项测试、79项输入哈希及723项软件
自检通过。重放目录`gap102b-widen-acc-vstart-parent-check-20261006-01`，
seal为`3a52e74d09a1ce7b7ab0e556202aac34e841df3ab198682586298299578bfe06`。
完整VRF和额外声明的v10字节均严格检查，没有跳过未知字节；尚未
启动该场景VCS，静态预测的覆盖目标不作为实际命中证据。

AKV列边界激励已启动一次300秒预算的旧镜像VCS仿真，独立输出为
`akv-column-boundary-old-image-20261006-01`，service为
`ara-akv-column-boundary-old-image-20261006-01.service`。父侧读取C激励和
运行器并执行12项检查器测试，全部通过；165项输入哈希核验完成。
实际VCS PID2911443已确认，加载封存simv和本次独立ELF。预检seal为
`065ee77f907e67c7d7a2290561e22fb2a028763b88878a13f620cbd5c5d15a76`，
prepared seal为
`0d58b18e85bca42383a8d4c1363d9d01b6161afeba5ed61b02d3de979dc5e7e9`。
Spike执行的是软件参考，而非native AKV指令模型；RTL功能、精确异常、
恢复路径和raw24覆盖增量仍待独立验收，未纳入717项之外的新成员。

FSM可见单列只读检查已结束，目录为
`dcache-read-port2-fsm-visible-column-714-20261006-01`。15项工具
测试和前后输入核验通过，实际8个状态/20条转移名称一致，但仅请求
可见`Coverage`列仍返回异常字段：State/IDLE原始hex为`41a906`，
Transition/IDLE->READ原始hex不是百分比。终态为
`HOLD_NATIVE_QUERY_INCOMPLETE`；没有排除文件、没有豁免资格。
保留原始字节，停止重复列读取；不能把工具返回0当有效覆盖值。

LZC v5单点短检查已完成，耗时291.463秒，实际DVE Tcl版本8.4.5.1。
父侧独立重放`reviewed_probe`及`verify_probe`通过：同一子实例84点
五次审计，仅临时改变指定位置47；原生condition ID20/vector2签名
保存与重载一致，其他位置不变，最终排除文件为空。该结果修复了
工具兼容性阻碍，但不是完整120候选/4200保护位置资格验收；尚未
新增正式处理器豁免，仍须完整同会话核验。

717项的独立DVE汇总已后台启动，service为
`ara-branch-combo-six-policy-717-20261006-01.service`。父侧16项工具
测试及封存配置输入核验通过，并确认实际DVE PID2873580正在执行。
本次仅复用已核验的六组原生排除，输出raw/applied/reset及保护点
审计；报告完成并验收前，最新百分比仍使用715项结果。

GAP102合法扩宽累加边界激励的v2预检已完成父侧独立复核：75项
输入哈希、723项自检、完整4096字节VRF、源数组、CSR及恢复保护区
与Spike一致，10项检查器测试通过。该结果不是DUT PASS，未准入；
目标raw127仍未命中，必须通过旧镜像实际VDB验证覆盖增量。
随后运行输入封存完成，162项输入哈希检查通过，运行计划SHA为
`7c9aed3b60eb2249e8555547bc81ac7d7b3b2e647fdbb4a01b35483aab6b4280`。
独立后台service为`ara-gap102-widen-acc-cross-old-image-20261006-02`，
输出目录同名，VCS预算600秒；不自动重试、不修改RTL、未准入。
该运行随后SUCCESS，CPU时间299.020秒，82请求/82响应、零异常及
协议错误。第一次离线收集因错误使用`arch_start.pc`而拒绝：冻结
monitor该字段为0，PC仅在retire有效；原检查器源码与失败产物已
保留。修正为唯一操作码请求序号、唯一退休PC及先后周期联合校验，
新增拒绝测试后12项工具测试通过，无需重仿真。第二次离线收集
确认101339条提交、74174次GPR写回、2495次标量访存、35条向量
结果/6144字节全部匹配，723项自检和完整VRF/CSR/保护区通过。
但raw127仍未命中，原始line/condition/branch/FSM增量均为0。
`gap102-strict-candidate-717-20261006-02`因此未按覆盖增量准入；
这是功能通过但覆盖预测未成立，不计为新的RTL错误，也不以新增
PASS数量冒充覆盖提升。继续离线分析上游路径，不盲目重跑。
父侧实际读取seq43的周期记录：14008分配`use_vd=0/eew=1/VL129`
微操作，14027完成；14031和14048分别分配`vd8`、`vd12`的
`eew=2/VL32`微操作，14046和14063完成；14065分配
`vd8/eew=2/VL129`原操作，14090完成。冻结源码的
`SOURCE_SNAPSHOT_CAPTURE`明确不写目的寄存器、采用源EEW和原VL，
其后可先归一化累加器再执行原操作。上述字段及先后关系与这条
绕行路径一致，解释了不能仅靠跨过element128预测raw127命中。
CSV未直接采集状态寄存器及snapshot有效位，不将这组对应关系
扩大成所有输入的不可达证明，也不据此豁免raw127。

read-port2原生枚举03已取得实际FSM对象：8个状态、20条转移。
父侧从原始TSV字节中独立核对这两组ASCII名称，集合和端点完整。
但隐藏列读取返回非法UTF-8字节，任务终态FAILED_OR_HOLD；坏列
不得用于身份或覆盖状态判断。原始产物不改，只离线隔离异常字段，
待精确绑定与singleton核验后再决定豁免。尚未应用新增排除。

最新cache跨页激励已结束，VCS自检SUCCESS，CPU时间76.810秒。
父侧独立标量比较为TERMINAL_TOHOST_MATCH，12335条提交、4015次
GPR写回和2062次标量内存访问匹配，无未知值跳过；两次S态ECALL
有记录。五个目标replay覆盖位均未命中；实际新增condition4，已完成
严格准入。不能把本次功能PASS表述为replay覆盖成功。

LZC原生资格batch04已终止，状态FAILED_RECORDED_NOT_QUALIFICATION。
实际DVE日志指出`lpn_guard_exclude`中的`{*}$args`参数展开编译失败；
不是RTL错误，也不是候选不可达证明。完整global-before审计已执行，
但首项singleton排除尚未执行。最终排除文件为空、global-final与
global-before相同。保留原证据，先修正工具兼容性，不应用候选豁免。

最新严格准入集合为717项PASS：
`cache-port1-offline-admitted-717-20261006-01`。父侧核验正式输出
封存、6084项输入哈希、原始CSV架构判据及716项前缀完整性通过。
封存标识为
`82cd5f277d934c7b2435bfff3e2af1d4dd64cdea6435baba67b72749be183b62`。
新增条件覆盖点4个，分别为D-cache memory仲裁器3个、port1控制器
1个；line/branch/FSM无增量。纯标量激励没有向量活动，向量比较
状态为UNOBSERVABLE，不虚报向量PASS。最新DVE百分比仍对应715项。

上一严格准入集合为716项PASS：
`gap101a-offline-admitted-716-20261006-01`。父侧独立重放准入核验
通过，封存标识为
`df9e35f425734bce6d22416acf3f91fbea85f007ceb1e45f2e1eee703da4fd8a`。
完整保留715项前缀，只追加独立GAP101A的PASS VDB，716项无重复。
539项自检、13025条标量提交、6436次GPR写回及1731次标量内存
访问匹配，无未知值跳过；独立账本确认非法NF×EMUL请求被拒绝且
没有后台微操作或目标内存破坏。新增line1/condition1/branch1/FSM0。
原GAP101寄存器越界失败仍排除，不能以GAP101A通过核销该错误。
最新已验收的DVE百分比仍对应715项；尚未生成716项百分比报告。

上一严格准入集合为715项PASS：
`gap100-offline-admitted-715-20261006-01`。GAP100的完整标量比较、
23次异常账本和14个覆盖目标通过独立验收，原始增量为line3/
condition13/branch4/FSM0。正式产物5949项封存哈希核验通过，
原714项前缀完整、715项唯一，bitmap与已独立重收的候选完全一致。
没有修改RTL或重跑仿真。最新原始DVE报告已更新为715项，目录为
`raw715-dve-20261006-01`；向量比较不适用的范围未虚报为向量PASS。
父侧只读核验正式报告的6678项封存哈希、精确输入与selected成员、
完整层级和关闭豁免的状态全部通过。

| i_system原始指标 | 707项 | 715项 | 增量（百分点） |
| --- | ---: | ---: | ---: |
| Line | 85.12% | 85.13% | +0.01 |
| Condition | 81.82% | 81.85% | +0.03 |
| Branch | 82.85% | 82.86% | +0.01 |
| FSM | 60.46% | 60.46% | 0.00 |
| Toggle | 63.12% | 63.15% | +0.03 |
| Score | 74.67% | 74.69% | +0.02 |

本表不应用豁免，不包含GAP101或其他FAIL/TIMEOUT。后文707至714项
状态为当时的过程记录；不能混用707项六组豁免结果与715项原始结果。

上一严格准入集合为714项PASS：
`closure92-offline-admitted-714-20261006-01`。AKV73完成独立ELF、
stdout、commit及VRF核验，collector的12项测试通过，父侧独立
重收原VDB并确认增量为line0/condition6/branch0/FSM0。正式产物
5877项封存哈希全部核验，精确保留713项前缀、追加1项且无重复。
没有重跑仿真或修改RTL，旧QBS fault及其他非PASS仍排除。
最新独立DVE百分比仍对应707项，不能写成714项百分比。

上一严格准入集合为713项PASS：
`closure92-offline-admitted-713-20261006-01`。五项历史PASS完成父级
独立完整离线核验、16项拒绝性测试及严格集合验收后正式准入，父级
再次核验5620项封存哈希和精确708+5顺序/唯一性。新增原始覆盖位为
line12/condition33/branch11/FSM0。没有重跑仿真或修改RTL，历史FAIL
和TIMEOUT仍不纳入。最新独立百分比报告仍对应707项，不能将其
百分比或正在执行的707项豁免报告写成713项结果。

上一严格准入集合为708项PASS：
`gap99-offline-admitted-708-20261006-01`。CSR激励的两个目标条件均
实测命中，新增1个行点、2个条件点和1个分支点，FSM无增量。
完整标量比较、自检和零CVX/向量活动范围证明通过。最新独立核验的
原始百分比报告仍为707项；六组豁免后台任务也明确绑定707项。
不把707项百分比或豁免结果冒充708项结果，待阶段性合并再导出，
避免每增加少量位就重复整个DVE汇总。

上一严格准入集合为707项PASS：
`gap98-offline-admitted-707-20261006-02`。FP16激励的125个目标全部
命中，原始增量为423个行点、148个条件点及423个分支点，FSM无增量。
完整标量比较为`TERMINAL_TOHOST_MATCH`，24条向量目的指令和6144
字节精确匹配，32组微操作、48组接口请求全部核验排空。
`ara-raw707-dve-20261006-01.service`已完成并退出0，父级独立执行
`verify_historical_raw_report.py`通过：恰好707项已准入测试及设计输入，
豁免关闭、诊断为空。最新原始结果如下；分项层级表仍明确保留706
历史标签，不混用集合。

| 集合 | Line | Condition | Branch | FSM | Toggle | Score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 706 PASS | 84.76% | 81.75% | 82.42% | 60.46% | 63.09% | 74.50% |
| 707 PASS | 85.12% | 81.82% | 82.85% | 60.46% | 63.12% | 74.67% |

新报告为`raw707-dve-20261006-01`。上述百分比仅对应旧镜像，
不代表当前RTL signoff，也未包含尚待全量应用的新增豁免。

707项六组豁免任务已执行，但本次工具流程失败，未生成有效报告：
`ara-six-policy707-dve-20261006-01.service`，目录
`branch-combo-six-policy-707-20261006-01`。父级独立执行21项测试、
封存配置核验通过，范围为114个原生scope、5808目标点及13562保护点。
实际DVE退出0，但验收器因缺少必要证据返回失败；GUI日志在before
审计阶段报告`gui_list_select`选择了不存在的空列表项。最终空排除文件
已保存，原始VDB未改变。保留本次失败目录，后续仅修复工具选择流程，
不得将该结果解释成处理器case失败或有效豁免。状态/save/reload、根
报告刷新及最终reset全部验收通过前，不宣称新的豁免百分比。
配置绑定仅限已核验的六组分支策略，不包含待核准的LZC或PTW FSM。

六组流程的空列表错误已在独立后继选择适配器中复现并修正：仅规范化
DVE空选择的包装形式，仍要求有效旧选择显式清除、目标单项精确读回，
未知选择或混合空/有效选择均拒绝。父级6项测试通过。尚未重新完成
全量DVE应用验收，故不产生新的豁免百分比。

六组后继`branch-combo-six-policy-707-20261006-02`已完成封存，父级
独立10项组合测试及最终配置核验通过，配置SHA为
`9412f766aa75e7099fb3c0b354db655b78b1b6bee3abf39032b81d651128acaa`。
`ara-six-policy707-dve-20261006-02.service`已启动，实际DVE PID2728623
身份核验及进程检查通过，GUI日志确认选择适配器已加载。
仍绑定707项、5808个目标及13562个保护点；尚未完成全量验收，
不能宣称有效豁免结果或最新集合百分比。最终配置生成前的中间core
配置未用于启动任务。

LZC产品只读原生查询第三次工具后继已完成，目录
`lzc_selector_native_product_discovery-707-20261006-03`，DVE退出0。
父级独立执行inventory验证，输出`native-inventory-parent-verified.json`：
36个实例、4200个原生位置；查询程序2项和清单检查4项测试通过。
前两次工具失败保留。此步骤没有排除点，也未批准应用；条件表达式
精确绑定仍待验证，op16保持HOLD，不能把原生清单完成解释成豁免完成。

下一批CSR激励依据`csr-functional-inventory-707-20261006-02.json`。
条件571点和分支626点均完整映射；行位宽974中有5个无源码shape项
的位置268/608/641/932/959，单独保留为未解析，不能豁免或悄悄删除。
初版清单的完整映射检查因此拒绝运行；后继清单显式记录这个范围。
两个拟补条件分别是SATP不支持模式和MPRV/Bare配合非M有效权限。
SATP刺激使用保留MODE=1，而非可能被Spike支持为Sv48的MODE=9；
检查旧值、忽略写入后的读回以及实际数据访存，预检和RTL验收前
不计入707项或宣称覆盖增量。

CSR激励的实际Spike预检随后通过：14项自检、96字节观察值、两次
保留MODE=1写入及两个MPRV阶段均匹配，无陷阱、无向量目的请求。
父级阅读源码、独立核验81项预检pins；清单9项和启动器7项测试通过。
封存启动计划核验152项pins后，旧镜像任务
`ara-gap99-csr-satp-mprv-20261006-01.service`已启动，目录
`gap99-csr-satp-mprv-old-image-20261006-01`。当前只是运行，完整
标量比较、自检/contract及覆盖位增量验收前不增加707项。

gap99实际VCS任务退出0，CPU时间15.43秒，软件SUCCESS。父级随后
只读离线runtime核验通过：标量`TERMINAL_TOHOST_MATCH`，96字节
独立观察值及CSR操作/恢复顺序精确，contract各计数为0。该case不含
向量指令，commit仅退休事件、vector仅配置记录，所以原始向量比较
保留`UNOBSERVABLE`，不伪造向量PASS。共用contract检查器的非零
activity要求仅在上述完整零活动证明下不适用，其他错误仍拒绝。
runtime检查尚不是完整输入封存/集合准入，707项暂不增加。

随后gap99严格准入完成：父级独立16项测试及608项输入pins核验
通过，新集合`gap99-offline-admitted-708-20261006-01`为708项PASS。
两个目标条件均命中，原始增量为line1/cond2/branch1/FSM0；没有
重跑VCS或修改RTL。向量结果仍为UNOBSERVABLE、0请求/0字节。

上一严格准入集合为706项PASS：
`gap97-offline-admitted-706-20261006-01`。gap97六个目标条件点全部命中，
原始增量为6个条件位，行/分支/FSM增量为0。706项原始DVE汇总任务
`ara-raw706-dve-20261006-01.service`已完成并退出0，父级独立运行
`verify_historical_raw_report.py`核验通过。下表来自实际706项报告
`raw706-dve-20261006-01`，豁免关闭，诊断为空；四舍五入后与705项
相同，不代表六个新增条件命中没有发生。

| Line | Condition | Branch | FSM | Toggle |
| ---: | ---: | ---: | ---: | ---: |
| 84.76% | 81.75% | 82.42% | 60.46% | 63.09% |

706项原始层级报告的重点模块如下，均未应用豁免：

| 模块 | Line | Condition | Branch | FSM |
| --- | ---: | ---: | ---: | ---: |
| Dispatcher | 93.88% | 80.47% | 85.81% | 60.26% |
| QBS engine | 98.55% | 79.01% | 95.28% | 79.13% |
| AKV engine | 95.02% | 78.87% | 96.15% | 96.97% |
| CVA6 CSR | 58.72% | 43.08% | 43.77% | NA |
| CVA6 PTW | 60.48% | 48.68% | 45.98% | 44.00% |

操作数队列需要按实例解释：四lane的mask_m分支均为32.59%，
slide_addrgen_a均为33.33%，st_mask_a均为34.81%。这些原始值
包含参数化实现产生的组合；不能直接把全部未命中项判成可达功能
缺口或全部豁免。先区分源证明排除项与需要mask、slide、store消费
及背压交互激励的路径，再检查有效分母和实际增量。

另有已完成的701项四组豁免报告，Branch为85.24%，五组报告Branch
为86.41%；两者都不是706项结果，不能直接叠加到新集合百分比。
五组报告已通过父级独立复核：5600个目标与12626个保护点均完成
原生状态检查，刷新根节点后再次核验，最后全局reset恢复原始报告。
这仍不是新RTL或最新706集合的signoff。失败/超时VDB不纳入集合，
本目标不修RTL错误。后文按证据形成顺序记录过程，其中早期
“最新”表述仅指该历史阶段，不替代本摘要。

## 后续激励与豁免审查（尚未准入）

五项历史PASS已在708项基线上完成父级独立离线核验，输出为
`closure92-offline-five-parent-replay708-20261006-01.json`。
`gap71_qbs_read`、`gap71_akv_read`、`gap71_akv_fault`、
`akv_gap72_tile_range`及`qbs_gap72_fill_abort`全部通过完整oracle、
标量/向量/内存/CSR检查、contract、实际执行命令和66文件镜像绑定。
10项拒绝性测试通过；没有重跑仿真或改变原始VDB。该结果明确为
`OFFLINE_REPLAY_COMPLETE_NOT_ADMISSION`，正式集合仍为708项。
正在准备708+5的独立严格collector；AKV73仍需单独完整oracle审查，
旧QBS fault失败不因其他fault测试通过而被核销或纳入。

该collector准备目录为`closure92-five-strict-collector-713-20261006-01`。
父级16项拒绝性测试及完整`collector.py verify`均通过，实际重新读取
708项原始覆盖位并与基线核对，精确合并5个新成员。提案原始增量为
line12/condition33/branch11/FSM0，状态仍明确为未准入。
父级随后授权并完成独立713项正式集合，目录
`closure92-offline-admitted-713-20261006-01`。正式状态为
`PASS_RAW_UNION_HISTORICAL_ONLY`，父级再次核验5620项封存哈希，
原708项顺序及精确5项新增唯一性通过。不从覆盖位增量推测新的
DVE百分比，也不宣称当前RTL signoff。

下一组合激励为`vgap100_csr_hpm_vectored.c`，包含15个场景、225项
自检：M/S/U读取HPM3与四种mcounteren/scounteren组合、M态被委托
EBREAK仍留在M态、S态软件中断的向量入口以及U态同步ECALL对照。
静态目标为12个条件位、1个行位和1个分支位，并非实测覆盖增量。
父级已阅读源码及CSR权限/向量入口逻辑；软件中断的EPC和NOP退休
数量存在时刻差异，须由独立oracle明确核验有限窗口、trap和CSR状态，
不得通过宽泛忽略标量差异宣称通过。
Spike预检04已通过：225项自检、23次预期陷阱、1800字节观察值和
1800字节原始快照匹配。父级独立12项测试及70项输入pins通过，
预检manifest SHA为
`a7d725d519eec37dc6d1d42514a84f8121add0f9ed6bd147a9341697682e5cdc`。
预检仍明确`scalar_comparison_qualified=false`；RTL尚未验收，
不纳入713项，不宣称静态14个目标已在RTL命中。
父级独立9项运行器测试及141项运行输入pins通过，运行计划SHA为
`99628c3b968ca032a79b389fab4a47b695cec7897fec94cc3eec99f8ee940e3d`。
`ara-gap100-csr-hpm-vectored-20261006-01.service`已启动，独立目录
`gap100-csr-hpm-vectored-old-image-20261006-01`，预算600秒、无波形，
收集line/condition/branch/FSM/toggle。运行仍绑定已封存708项预检，
后续准入须与最新713项重新核对实际增量，不修改旧预检记录。
该运行已退出0，软件报SUCCESS，VCS CPU时间45.03秒，contract各
活动/错误/未完成计数为0。父级只读收集该VDB并与正式713项结合，
诊断性原始增量为line3/condition13/branch4/FSM0，全部来自CSR模块。
这不是准入：完整标量比较及软件中断差异的限定核验仍待完成，
状态保持`SIMULATION_EXITED_NOT_ADMITTED`，正式集合不增加。

gap97针对705项集合中六个未命中的Dispatcher条件点：CSR置位/清位
操作及大AVL的VL截断。激励分别检查vxsat、vxrm、vcsr、CSR返回旧值，
以及AVL为`1<<20`时e8/m1返回VL=128。父级已阅读激励和独立oracle，
12项检查器单元测试通过；这不是Spike预检或RTL验收通过的证据，
在完整RTL比较完成前不增加PASS数，也不合并其覆盖率。

随后实际Spike预检完成：75检查、10个CSR探针、600字节精确观察值
均通过，封存于`gap97-csr-large-avl-preflight-705-20261006-02`。
独立VCS任务`ara-gap97-csr-large-avl-20261006-01.service`已退出0。
父级完整标量比较得到`TERMINAL_TOHOST_MATCH`：767条退休指令、
340次标量寄存器写和181次内存访问匹配，无陷阱，软件成功标记一次，
contract错误为空。严格准入清单和原始覆盖增量仍待完成，不增加705。
该case不执行向量数据运算，vector比较实际返回`UNOBSERVABLE`，
0次目的请求、0字节、无未完成请求；不能将其改写成向量数据对比PASS。
vset配置的正确性由退休指令、返回VL及后续CSR读回验证。
`vector_trace.csv`不提供该条vset握手，但`commit_trace.csv`中的
`arch_start/cvx_req/cvx_resp`提供了接口证据。父级随后独立执行完整
runtime检查：85对CVX请求/响应匹配且排空，其中vset请求/响应各一次，
返回值128，与对应退休指令一致。不能由vector trace没有请求推断
整个旧监视器没有vset握手证据。

gap98新增FP16除法pack激励`vgap98_div16_pack.c`，专门针对可达
但未命中的指数表项，而不是用豁免删除它们。最小非正规数
`+/-0x0001`分别除以biased exponent为5至30的二次幂及31的正无穷；
每种重复16元素，以覆盖四lane及各16-bit位置。有限除数的独立有理数
RNE oracle检查精确/下溢边界；除以无穷返回带符号零且不产生UF/NX。
激励保留全部输出、源数据、VL/vstart、fflags及两端guard检查，预计
3112项自检、24次向量目的请求和6144字节对比。两项源级oracle/布局
单元测试通过，尚无Spike或RTL实测结论，不计覆盖率或PASS数。

随后实际Spike预检通过：3112项自检、24条向量目的指令、6144字节
均匹配。另建8实例证据重绑定清单，保留原ELF和Spike哈希，不重复
编译或执行软件。目标为125个未命中点（含7个指数-25边界），不将
这些可达/尚未分类点豁免。父级独立执行重绑定5项和启动器6项测试
通过，并核验529项输入pins及封存启动计划。独立旧镜像VCS任务
`ara-gap98-div16-pack-20261006-01.service`已启动，输出目录
`gap98-div16-pack-old-image-20261006-01`。完整架构比较及严格准入
尚未完成，不增加706项集合，也不声明125点已命中。

该VCS任务随后退出0，CPU时间148.2秒，软件成功且contract记录
48对请求/响应、异常/协议错误/未完成请求均为0。父级运行准入器
17项测试及546项输入pins检查通过，但实际准入被事件白名单拒绝：
真实commit trace还有32条`uop_alloc`和32条`uop_done`，不是陷阱。
39123条退休指令、48组架构请求及全部微操作记录均保留。失败目录
`gap98-offline-admitted-707-20261006-01`不得作为707项PASS集合。
另建检查器后继版本，补微操作配对、命令及时间绑定的完整核验后
离线重放；不因检查器格式问题重跑VCS，不修改RTL，也不直接丢弃
微操作事件后宣称通过。后继v2检查器随后完整离线验收通过，
707项正式旧镜像集合位于`gap98-offline-admitted-707-20261006-02`；
原失败目录保留且不作为覆盖输入。125个目标全命中，增量在本文件
首部列出。这仍不是当前RTL的signoff。

FP16 pack源证明已增加机器可检查的格式/指数流水对齐、共同enable、
reset/hold和FF1归一化范围，父级重新执行13项证明/清单测试通过。
705清单为`fp16-pack-lower-bound-candidates-705-20261006-01.json`：
8个WIDTH16实例中208个候选（指数-51至-26），936个其余分支保留；
指数-25边界保留，已有1个实例实测命中。该证明限于正常二态/reset
闭包，不扩展为X初始化证明。候选尚未原生资格核准或应用，不报告
豁免后的覆盖百分比；118个可达/尚未分类的未命中表项继续保留。

208点原生核验工具及实际配置通过父级审核，8项核验器测试通过。
后台任务`ara-fp16-pack-native208-20261006-01.service`已启动，实际
DVE进程PID2637202已确认。它仅使用一个历史测试做原生身份、完整
1144点状态（208目标、936保护点）、save/reload及reset核验；不是
706项全量豁免应用。输出目录为
`verification/out/fp16-pack-native208-capture-prepare-20261006-01`。
首次任务已失败：诊断清单将case表达式与default下的子条件合并，
而DVE原生记录只保存case根表达式，签名还包含未进入子树的`,-`。
校验器原来的序列化假设不正确；最终清除后1144点状态恢复且EL为空。
失败目录及工具保持封存，另建v2核验器验证精确原生身份和完整往返，
不放松checksum或保护点检查。v2实际任务已完成，父级再次独立
执行`verify`得到`PACK208_NATIVE_REVERIFIED`。208条原生记录匹配，
1144点全程核验，936个保护点（含default和指数-25）不受影响，
save/reload一致且最终reset为空。结果位于
`fp16-pack-native208-capture-prepare-20261006-02`。这仅核准原生
身份及往返操作，不是706项全量报告的应用批准；全量输入绑定、
实际分母变化和报告仍待验收，不宣称新的豁免覆盖百分比。

父级进一步核对冻结SoC配置：`ara_soc.sv`明确覆盖
`cfg.NrPMPEntries=0`，经`build_config`原样传递，PTW的PMP输出因此
恒为允许访问。相关源码哈希与冻结构建一致。此前设想用PMP deny
激励PTW access-error在这个镜像上不可行，不安排无效仿真。
新增源证明及3项测试通过，706清单
`ptw-pmp0-fsm-candidates-706-20261006-01.json`标出
`PROPAGATE_ACCESS_ERROR`状态和3条相关迁移为4个候选，其他31个
FSM点全部保留。普通`PROPAGATE_ERROR`及页表错误不排除。
原始FSM位置目前仅为诊断映射，尚未取得原生DVE身份，不应用豁免。

PTW的H扩展stage状态机不能套用上述正常reset状态证明：源码中
`ptw_stage_q`的复位和更新均仅在`CVA6Cfg.RVH`分支内，RVH关闭时
不能声称它恒为`S_STAGE`。当前配置包将HExtEn设为0，build_config
保留RVH；后续若排除此类instrumentation，须另核验冻结源码/实际
参数及无架构影响，并绑定原生FSM身份。普通Sv39翻译和页故障不是
因此可排除的功能。本段只记录审查边界，未生成或应用新的FSM豁免。

LZC补零选择器候选的三项结构单元测试通过；可达但未命中的节点
仍保留。原生DVE坐标及真/假分支对应关系尚需独立核验，不能只根据
未命中位直接生成豁免。FP16除法pack指数下界的源证明也在独立审查，
可达边界和真实激励缺口不能排除。

LZC独立root校准随后完成8/8自检、原生导出及离线核验；父级核验
汇总封存和71项输入pins通过。汇总为
`lzc_selector_native_measurement-705-20261006-02/native-summary.json`。
实测selector假对应`Branch0.1`、真对应`Branch0.0`；XML op23 ID3
对应原生Condition2，真假vector ID分别为1/2，取决于selector而非
输出值奇偶。32次singleton保存/重载共核验14896个可见位置，
reset/final EL均为空。XML op16 ID2不能据此等同原生Condition2，
保持HOLD；隐藏XML-only位置没有因此得到原生核准。该校准不是
处理器补零节点的身份迁移批准，尚未对707集合应用任何LZC排除。

gap97严格准入检查器14项测试通过，完整旧镜像/ELF/预检/历史证据链
485项pins匹配；已完成完整架构、CVX握手、自检、contract及零向量
数据范围核验，集合从705增加到706。输出保存原始`UNOBSERVABLE`
向量比较结果，不伪造向量数据PASS。全部六个目标条件点实测命中。

以上工作不修改RTL或重新构建处理器。历史FAIL/TIMEOUT和本轮归约
失败继续独立保存，均不作为706项PASS集合的成员。

新增历史记录清单为
`verification/out/historical-nonpass-records-20261006-01.json`。
扫描18份一级`all-outcomes.json`及旧镜像扩展的逐case状态后，发现
30条非PASS记录（27条TIMEOUT、3条FAIL）。这是限定证据格式下的
历史记录数，不是当前未解决bug数；不同ELF不得合并，后续同名补跑
是否闭环还须核对镜像和准入证据。另行只读匹配发现其中16组在
其他`all-outcomes.json`中存在同名、同ELF的PASS记录：
`csr_gap35_permissions`、`qbs_gap35_descriptor`及c0234、c0528至
c0540。此结果只提供核销候选，尚不证明使用同一镜像、后来通过或
已纳入706项集合；其余14组也不能直接解释成14个RTL bug。
脚本不将报告工具顶层FAILED
误算为处理器case失败，也不改变任何覆盖率输入。两项单元测试通过。

后续只读核销清单
`historical-nonpass-sixteen-image-membership-reconciliation-706-20261006-01.json`
确认上述16组均有同ELF、封存镜像的PASS成员，已在706项中各出现
一次。父级再次核验该清单357项`input_pins`，并检查当前708项输入
列表中的16个成员均恰好出现一次。因此无需重复准入，不增加PASS
计数；原始非PASS VDB不因后续通过而纳入。该核对没有重做这16组的
完整功能oracle，也没有证明原始超时根因闭环；另外14组仍需独立分类。

另外两个gap35历史FAIL的原始日志已再次检查：`vgap35_carry_ta`
报check367的0/1、check445的0/1、check448的1/0三处差异，tohost=3；
`vgap35_slide_bound`报check2/4、135/137、268/270共六处差异，
分别为0/0xb6、0/0xb4，tohost=6。后者自检源码对应前三轮
`vstart=3`之前的目的字节0和2，应保持旧值。两者均产生
`CVXIF/DUT_FAIL`，不是仅因缺VDB而被误判失败。现有日志只证明
自检差异；未在本轮完成逐周期根因验证，不将猜测写成已确认RTL根因。
本轮不修复、不准入，待统一修复阶段处理。

进一步核对`closure92-current-20261005-01/outcomes/`，早期七项
超时在调整启动环境/预算后得到六项PASS、一项QBS fault FAIL。
这六项运行结果仍需独立collector准入，不能仅按outcome直接加到705。
另一个`qbs-fault-layout-repair-20261005-01/status.json`记录修复后
新镜像的五项PASS；该目录明确`old_vdb_reuse=false`，不能用来
覆盖旧镜像结果或并入旧设计VDB。这也说明30条历史非PASS记录
绝不能解释成30个未修复RTL错误。

## 镜像与统计范围

本轮复用 `verification/out/repaired-aligned-build-20260930-01/sim/simv`，
不回退工作区 RTL，不重新编译处理器，不修复本轮发现的 RTL bug。
最初基线是 `closure90-current-20261005-01` 的 654 项 PASS。
本轮结果仅说明该封存镜像的覆盖，不是修复后当前 RTL 的 signoff。

每项先通过独立 Spike，再要求完整标量/向量对比、自检和 RTL contract
检查全部通过。合并检查同一设计、覆盖点 checksum/width、VDB 唯一性及
输入清单一致性。失败、超时以及纯诊断 VDB 不纳入 verified coverage。
官方百分比来自 DVE，下面的点数是原始覆盖位增量，两者不能混用。

## 各批结果

| 批次 | 测试重点 | PASS | FAIL | 合计 PASS | 新增行点 | 新增条件点 | 新增分支点 | 新增 FSM 点 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gap76 | 浮点扩宽、扩宽归约、整数扩展及 min/max 回归 | 15 | 1 | 669 | 6 | 19 | 5 | 0 |
| gap77 | 单比特/稠密尾数、非正规数与有符号零 | 4 | 0 | 673 | 0 | 6 | 0 | 0 |
| gap78 | 双源低尾数、跨 lane 输入分布、扩宽加减 | 4 | 0 | 677 | 14 | 78 | 21 | 0 |
| gap79 | FP16/32/64 特殊值、异常标志及掩码抑制 | 8 | 0 | 685 | 45 | 121 | 23 | 0 |
| gap80 | 全 lane 同值低尾数、扩宽加法 | 2 | 0 | 687 | 0 | 2 | 0 | 0 |
| 本轮合计 | 34 次独立验收运行 | 33 | 1 | 687 | 65 | 226 | 49 | 0 |

上表合计限定为gap76至gap80。后续gap81新增一项验收通过的QBS M4
地址对齐场景，历史集合达到688项，新增122个原始条件位；行、分支、
FSM增量为0。它不是上表中那34次运行的一部分。

这些是与各批前序集合比较的实际增量，不按指令出现次数推算。
gap77 的六个新增条件点来自标量 FPU，不算作向量队列提升。
gap78 实际补上 16 个 MFPU 队列 LZC 条件点；其他新增点主要来自
标量 oracle 的浮点比较及仲裁。gap79 的 189 个新增点均位于向量 lane。

每批完整证据保存在 `verification/out/gapNN-old-image-20261006-01/`：
`status.json`、逐项 `audit.json`、比较结果、`combined-inputs.txt`、
`combined-bits.json`、`raw-bitmap-delta.json` 和 `combined-dve/summary.csv`。
五批的独立验收和 DVE 导出均已完成。

## 原生 DVE 百分比

以下均为同一旧镜像、无新增豁免的 `i_system` 层级数据：

| 已完成报告 | 行 | 条件 | 分支 | FSM | Toggle |
| --- | ---: | ---: | ---: | ---: | ---: |
| 669 PASS | 80.39% | 81.12% | 79.94% | 60.46% | 62.87% |
| 673 PASS | 80.39% | 81.13% | 79.94% | 60.46% | 62.87% |
| 677 PASS | 80.40% | 81.16% | 79.97% | 60.46% | 62.89% |
| 685 PASS | 80.44% | 81.22% | 79.99% | 60.46% | 62.90% |
| 687 PASS | 80.44% | 81.22% | 79.99% | 60.46% | 62.90% |
| 688 PASS（加gap81） | 80.44% | 81.28% | 79.99% | 60.46% | 62.90% |
| 690 PASS（加gap82/83，无豁免） | 80.44% | 81.40% | 79.99% | 60.46% | 62.92% |
| 691 PASS（加gap84，无豁免） | 80.45% | 81.44% | 80.02% | 60.46% | 62.93% |
| 692 PASS（加gap85，无豁免） | 80.46% | 81.45% | 80.02% | 60.46% | 62.93% |
| 693 PASS（加gap86，无豁免） | 80.46% | 81.46% | 80.03% | 60.46% | 62.93% |
| 695 PASS（加gap87/88，无豁免） | 80.62% | 81.47% | 80.20% | 60.46% | 62.95% |
| 697 PASS（加gap89/90，无豁免） | 81.41% | 81.49% | 80.93% | 60.46% | 63.00% |
| 698 PASS（加gap91，无豁免） | 81.72% | 81.54% | 81.27% | 60.46% | 63.02% |
| 699 PASS（加gap92，无豁免） | 82.10% | 81.56% | 81.63% | 60.46% | 63.04% |
| 701 PASS（加gap93/94，无豁免） | 82.24% | 81.73% | 81.92% | 60.46% | 63.08% |

gap76至gap81的历史集合报告已完成。最新正式输出为
`verification/out/gap81-dve-only-retry-20261006-01/combined-dve/summary.csv`。
历史前缀不是当前checker重新准入的全量signoff；当前checker的诊断
重放和新RTL验收属于另一个证据层次，不能据此改变历史结果。
gap82已通过独立离线验收，历史PASS集合达到689项，新增241个原始
条件位；没有重跑VCS。689项正式DVE输出位于
`verification/out/lzc-historical-689-20261006-01/`。
该目录已完成180个结构不可达LZC条件向量的精确原生排除、邻点检查
和最终清除，原始VDB不变。但层级百分比仍需复核：顶层条件覆盖率
在raw/waived报告中为80.60%/80.67%，`i_system`两份均为81.40%。
在核实层级刷新及分母行为前，不将该层级数字用作豁免收益结论。

gap83随后通过旧镜像完整验收，历史集合达到690项，针对3个明确
可达的FP16 LZC组合新增条件3点，其他原始指标增量为0。独立验收
及bitmap在`verification/out/gap83-offline-admitted-690-20261006-02/`。
官方690项无豁免DVE报告已完成，百分比直接读取正式报告，不从3个
新增条件位推算。

已启动独立的690项无豁免导出，管理单元为
`ara-raw690-dve-20261006-01.service`，输出目录为
`verification/out/raw690-dve-20261006-01/`。
输入使用gap83独立验收后的`combined-inputs.txt`，明确设置
`DVE_WAIVERS=off`，不重新仿真、不自动载入历史豁免。
启动后实际DVE进程PID2382254已确认存在，现管理单元已退出且
ExecMainStatus为0，正式`summary.csv`已生成。独立核验输入为1个
Design加690个唯一测试VDB，与gap83准入清单逐项一致；原生实际
选择的690个测试名也逐项一致，diagnostics为空，日志有成功标记。
报告中的`i_system`条件为81.40%、Toggle为62.92%，其他指标见表。
相对688项报告分别提升0.12和0.02个百分点。`.partial`不是正式报告，
本轮仍是旧镜像历史集合统计，不是当前RTL全量重新验收。

gap84 FP32除法随后通过Spike、旧镜像VCS自检及完整差分验收，
历史集合达到691项。相对690的原始增量为line15、condition83、
branch29、FSM0。691项正式无豁免报告现已完成，百分比见表；独立
核对实际选中测试与输入清单均精确691项，diagnostics为空。证据在
`verification/out/gap84-offline-admitted-691-20261006-01/`，具体说明
见`GAP84_DIV_ROUNDING.md`。没有修复RTL或纳入失败VDB。

gap85 FP32平方根已通过Spike、自检、完整scalar/vector差分及contract
验收，旧镜像集合达到692项PASS。相对691新增line2、condition13、
branch2、FSM0；692项正式DVE报告已生成并核验。证据在
`verification/out/gap85-offline-admitted-692-20261006-01/`，详见
`GAP85_SQRT_ROUNDING.md`。校准及调试VDB仍不纳入集合。

## Bug 与排除记录

gap94的普通FP16指数/舍入扫描严格验收通过，历史集合达到701项
PASS。相对700新增line30、condition162、branch138、FSM0。严格
比较30条向量指令、3840字节，详见`GAP94_DIV16_ALL_LANES.md`。
701项无豁免DVE导出已完成，服务退出码0；已独立核验实际选中
测试、输入清单、diagnostics为空及豁免关闭。正式报告在
`verification/out/raw701-dve-20261006-01/summary.csv`，核验记录在
同目录`population-verification.json`，百分比见上表。

gap93的普通FP16前导位扫描严格验收通过，历史集合达到700项PASS。
相对699新增line118、condition189、branch152、FSM0；没有使用
已知故障的扩宽归约路径。证据和边界公式见
`GAP93_DIV16_LEADING_SCAN.md`。最新正式百分比仍为699项报告，
不从原始点数推算700项百分比。

gap92的FP32前导位扫描严格验收通过，集合达到699项PASS；相对698
新增line352、condition37、branch352、FSM0。24条向量指令、6144字节
严格匹配，自检528项通过。具体证据与输入公式见
`GAP92_DIV32_LEADING_SCAN.md`。这些是原始点增量，尚不等于正式
DVE百分比提升；没有把失败或纯诊断VDB纳入。699项正式无豁免
报告已完成并独立核验实际测试选择、输入清单和空diagnostics，报告
在`verification/out/raw699-dve-20261006-01/summary.csv`，百分比见表。

gap91的FP32跨lane指数扫描已完成严格验收，历史PASS集合达到698项。
相对697项新增line308、condition99、branch335、FSM0；严格比较
60条向量指令、15360字节，无未知字节跳过或非位精确比较。
证据在`verification/out/gap91-offline-admitted-698-20261006-01/`。
698项无豁免DVE导出已完成，管理单元退出码0；独立核验输入与实际
选中测试均精确698项，diagnostics为空，豁免关闭。原生百分比见表，
报告在`verification/out/raw698-dve-20261006-01/summary.csv`，人口核验
在同目录`population-verification.json`。具体激励和预期见
`GAP91_DIV32_ALL_LANES.md`。

`vgap76_red16` 在 LMUL=1、VL=63、全开 mask 时失败。
Spike 和独立整数输入 oracle 均给出 -1.0，RTL 给出 +0.0。
周期探针确认 lane 3 已消费 14 个真实元素后，工作计数器仍为 7，
最后一拍开启两个 FP32 分量，把无效尾元素 +1.0 计入归约。
原因是归约工作计数器不等于真实输入剩余量。

状态：已记录、未修复。用户要求后续统一修复；本轮不修改 RTL。
具体根因和周期证据见 `GAP76_OLD_IMAGE.md`。
该失败 VDB 不在 687 项输入清单或 bitmap 的 tests 清单中。
归约探针和独立 LZC 校验 VDB 同样没有合入。

历史 carry/slide 和 QBS 修复的验收结果属于另一镜像。
不能因为它们已经通过，就混入本轮旧镜像覆盖率。
本轮新增测试未遇到需要放宽超时或修改环境才能通过的 case。

上述无环境问题的结论限定于gap76至gap80。gap81后续确实遇到
工具问题：host与DUT检查数混淆，以及DVE入口设置了应取消的`DVE`
变量。保留原失败记录后，以独立离线验收和DVE-only重试完成闭环，
没有重跑VCS或修改RTL。详见`GAP81_M4_PHASE12.md`。

gap82首次仿真保存了工具拒绝：脚本将架构VL=1误当作QBS内部提交
请求的VL要求。实际活动VL为128，与dispatcher中的
`qbs_m * (VLEN / 32)`一致。已用封存旧源码完成独立离线验收：
两个命令均核对完整生命周期、每命令512字节写回及精确结果。
原脚本拒绝记录保留，新增验收证据独立保存；不属于新增RTL故障。

## 诊断与后续依据

LZC 缺口调查采用实际 common_cells 模块的 WIDTH=10/23、MODE=1
独立短测试，校验位扫描结果并检查覆盖 checksum，与处理器运行分开。
gap77 的初始 381 点统计混合了行、条件、分支；条件单项实际为 321。
工具已增加 metric filter 及单元测试，避免把混合点数说成条件点数。
gap78 使这组历史条件缺口降至 305；不能直接将其全部豁免。

进一步提升应先检查原生条件表、参数关闭路径和状态可达性，再补激励。
本轮没有增加 FSM 覆盖，不能据此宣称控制状态交互已充分验证。
修复后需重新对同一 RTL 镜像进行回归与覆盖率汇总，不能相加不同
镜像的百分比，也不能使用失败测试覆盖位补高 PASS-only 覆盖率。

gap80 两项新增两个 lane1/lane3 MFPU C 的 LZC 条件点，分项见
`GAP80_OLD_IMAGE.md`。截至该报告没有应用本轮新增豁免。

查看最近批次：在本验证 worktree 执行 `./vstatus jobs gap80`。

## 692 项正式报告核验

`verify_raw692_report.py` 已核对设计 VDB 加 692 个唯一测试 VDB，
以及 DVE 实际选择的 692 个测试路径与准入清单逐项一致。
导出完成标志存在、diagnostics 为空、waiver 状态为 DISABLED。
报告位于 `verification/out/raw692-dve-20261006-01/summary.csv`，
核验及文件哈希记录在同目录 `population-verification.json`。
这是旧镜像 PASS-only 统计，不代表历史失败已修复或当前 RTL 已 signoff。

FP64 除法新增激励 gap86 已通过 Spike 与 VCS 的 1530 项自检，
225 条向量提交和 38580 字节严格对比通过，无未知字节跳过，
标量提交至 tohost 一致且无 trap。历史集合达到 693 项；相对 692
新增行 6、条件 18、分支 8、FSM 0。693 项正式 DVE 报告已导出，
`verify_raw693_report.py` 已逐项核验实际选择的 693 个测试及文件哈希。
独立准入证据及限定条件见 `GAP86_DIV64_ROUNDING.md`。

gap87 FP64 平方根也已通过严格验收，历史联合 bitmap 达到 694 项，
仅新增条件 2 点；694 项百分比尚未导出，不冒充上表的 693 项报告。
下一轮优先补除法器非正规结果指数选择路径，依据
`functional-line-ranking-693-20261006-01.json` 的源码绑定定位。
缺少 checksum 的 scope 单独记为 unresolved，不静默豁免或丢弃。

gap88 按源码缺口扫描 FP64 非正规结果指数，已通过 680 项自检、
完整标量及 60 条向量提交的严格验收。历史集合达到 695 项，相对
694 新增行 162、条件 23、分支 167、FSM 0；CPU 时间 68.230 秒。
695 项 DVE 正式报告已导出并核验实际选择的695个唯一测试，
证据在 `raw695-dve-20261006-01/population-verification.json`。
详见 `GAP88_DIV64_EXPONENT_SCAN.md`。

gap89 对四个lane逐一覆盖非正规输入首个有效位，已严格验收，
历史集合达到696项；新增行713、条件18、分支713、FSM0。
gap90 将gap88的每个指数复制到四个lane，Spike/VCS2720项自检及
240条向量提交、61440字节严格对比通过，历史集合达到697项。
相对696新增行10、条件20、分支10、FSM0；697项正式报告已完成。
`verify_historical_raw_report.py` 核验实际DVE选择的697个唯一测试、
准入清单、完成标志、空diagnostics和无豁免状态。结果及文件hash在
`raw697-dve-20261006-01/population-verification.json`。

相对695项正式报告，行提高0.79个百分点、条件0.02个百分点、
分支0.73个百分点、Toggle0.05个百分点，FSM不变。此处使用DVE
实际百分比，不按原始位数或新case数量推算。

## 701项集合的缺口复核及豁免应用进度

`raw-branch-line-ranking-701-20261006-01.json`重新读取已准入701项
的原始位图，校验输入成员和branch shape哈希后按源码行排列缺口。
这是诊断排名，不是DVE百分比或已豁免数量：

| 路径 | 源码行 | 原始未命中branch位置 |
| --- | ---: | ---: |
| C910 FF1前导位编码 | 37 | 1015 |
| C910 round双精度非正规指数表 | 414 | 636 |
| C910 SRT非正规舍入指数表 | 423 | 636 |
| operand requester调试路径 | 627 | 432 |
| C910结果打包 | 178 | 429 |
| QBS pending激活元数据 | 403 | 288 |

相对699项排名，FF1未命中位置从1027降至1015。指数表虽然与
FP64有关，其组合逻辑仍可在其他格式下求值，不能只凭格式名称
豁免整张表。需证明各实例实际指数输入范围并核对原生覆盖坐标。

QBS的单测试root-refresh应用已由父线程独立复核：448个目标、
3790个保护点、最终reset均通过，7项工具测试通过。证据目录为
`qbs-root-refresh-single-699-20261006-01`。operand调试branch单测试
应用也已独立复核，1832个目标和1176个保护点通过，3项工具测试
通过，证据为`operand-debug-1832-application-701-pilot-20261006-01`。
后者属于无功能反馈的验证打印逻辑，其中已命中点不是不可达点。

上述单测试结果只证明精确应用和恢复流程；完整集合应用报告仍需
独立验收，不能替代701项无豁免正式报告。FF1独立校准VDB不计入
处理器PASS集合。历史失败和超时记录仍保留，本轮没有修复RTL。

1832项full701应用已完成DVE导出，但原验收器返回FAILED：其原始
表少于独立raw701表一行。父线程逐项比较确认共有2988行完全一致，
没有新增行，唯一缺项为产品设计之外的顶层
`uvm_custom_install_verdi_recording`。design数据库绑定它到VCS厂商
UVM录波源码，module checksum为2787408814，无子实例。保留原失败
记录，只允许后续独立复核精确解释这一外部模块差异；不能据此忽略
产品行差异，当前仍不将该应用宣称为正式覆盖率提升。

上述差异现已通过独立产品树复核，详见
`OPERAND_DEBUG_COVERAGE_SCOPE.md`。701项集合仅排除审核过的1832个
非功能调试branch后，i_system Branch为83.05%，相对原始81.92%
提高1.13个百分点；Line/Condition/FSM/Toggle不变。这是分类统计
结果，不是新激励收益或其他豁免的合并结果。原始报告及失败状态
继续保留，独立资格sidecar记录精确例外和所有证据哈希。

QBS独立完整699项应用也已退出码0并由父线程重新verify：
`qbs-rooted-report-699-20261006-01`，状态为
`QBS_ROOTED_REPORT_EXACT448_HISTORICAL699_ONLY`。448个目标精确匹配，
3790个保护点不变，最终reset通过。原生应用结果SHA256为
`151014b4cb2e71fded0a837cb4e3f2cc4ff63d24a5671e8d1b2051682c249c87`。

| 699项QBS独立应用的分支指标 | 原始 | 应用后 |
| --- | ---: | ---: |
| i_system | 81.63% | 82.00% |
| payload bank0 | 85.07% | 95.00% |
| payload bank1 | 83.01% | 92.70% |

上述为完整699项实际导出及恢复核验，不是最新701项的合并豁免
总结果。工具保留application_approval/aggregate_admission/官方分母
资格为false，不能据此宣称新RTL signoff或已经自动纳入常规统计。

1144项操作数队列配置不可达候选已重新绑定到最新701项集合。
父线程独立重跑`rebind_operand_1144_701.py`，输出为
`operand-native1144-rebound-701-parentcheck-20261006-01.json`，状态
`NATIVE1144_REBOUND_TO_RAW701_NOT_APPLIED`。36个实例的1144个目标
全部未命中，原资格文件、源文件和编译设计哈希一致；实例缺少单独
metric checksum时，逐项通过compiled module/metric定义及原生
spec/vector坐标核验，而不是仅按位宽匹配。该结果仅确认旧证明与
最新集合兼容，尚未执行701项DVE应用，也未修改正式覆盖率分母。

父线程检查了最新后台工具流程：`test_capture_ff1_native904_v2`
与`test_apply_qbs_rooted_701`合计15项测试通过。旧FF1测试夹具
直接将脚本送入交互式Tcl标准输入，抛错后仍可继续打印成功标记，
其负向用例因此失败；v2在完整脚本外增加catch并遇错退出，保留
旧失败记录，不将其解释为RTL错误或已批准的豁免。当前运行的是
`ara-ff1-native904-capture-20261006-02.service`和
`ara-qbs-rooted-report-701-20261006-01.service`，均已核对实际
DVE子进程；这只是运行确认，最终原生坐标、保护点和reset验收
仍需等待完整产物并独立复核。

FF1原生904项捕获随后正常退出，父线程独立运行v2 verify通过：
`FF1_NATIVE904_V2_REVERIFIED`。1728个精确坐标、904个目标、824个
保护点及最终清空均核验通过；配置为
`43d28c2145a33638d9d6adbc9d22d4f30b90e102b3d6471b1c669b09492aa032`，
结果为`15c65c3f1e6a43079ea64dc73fe388004c596a32dadc59d8be33cbe6d911baf7`。
这是单处理器测试上的原生资格证据，不是701项完整应用或正式
分母批准。后续组合报告仍需实际执行；原始覆盖率保持不变。

组合前的坐标去重检查已完成：
`four-policy-coordinate-audit-701-20261006-01.json`核验1144个配置
不可达操作数点、1832个非功能调试点、904个FF1点及448个QBS点，
四组目标的scope/raw-index无重叠，共4328个唯一坐标。只有调试组
含408个已命中点，其余三组目标在701项集合中全未命中。工具的
两项负向/去重测试通过。此结果不替代原生签名和保护清单核验，
不生成EL，也不能把各组独立报告的百分比提升直接相加。

父线程审查组合脚本时发现报告节点构造问题：按scope中的点号逐级
生成祖先得到64个路径，其中4个`gen_lanes[n]`路径并不存在于
实际报告树；DVE将`gen_lanes[n].i_lane`作为一个Depth节点显示。
新增`report_scope_ancestors.py`从真实Name/Depth堆栈恢复祖先，
3项测试通过，并在raw701表上确认上述42个目标scope共有60个
真实祖先，不含4个虚构父节点。已通知组合脚本使用新版本修正，
不改封存脚本或RTL；现有9项组合测试未覆盖此实际层级差异。

## 最新701项QBS单独应用结果

`qbs-rooted-report-701-20261006-01`已正常退出，并由父线程读取
封存配置、独立verify_artifacts及逐字段比较结果通过，状态为
`QBS_ROOTED_REPORT_EXACT448_HISTORICAL701_PRODUCT_ONLY`。
448个目标、3790个保护点和最终清空均通过，实际选入701项PASS。
结果SHA256为
`849dd976dd9ee9dc0ca5279a44345dd6785a926c2c10022b82c83b74d7534758`。

| 701项QBS单独应用的Branch | 原始 | 应用后 | 清除恢复 |
| --- | ---: | ---: | ---: |
| i_system | 81.92% | 82.29% | 81.92% |
| i_ara | 83.39% | 83.81% | 83.39% |
| payload bank0 | 85.07% | 95.00% | 85.07% |
| payload bank1 | 83.01% | 92.70% | 83.01% |

这是最新701项集合的独立实际应用证据，不是四组组合报告；不能
与其他独立应用的百分点直接相加。原始无豁免报告保留，RTL未改，
失败VDB未纳入，工具仍不宣称当前RTL signoff或正式分母批准。

四组完整报告树检查也已通过：
`test_actual_report_ancestors_701.py`使用实际raw701表及74个目标
模块，验证所有目标均可选择、祖先无重复、4个虚构generate父节点
不出现，而实际`gen_lanes[n].i_lane`节点仍保留。这是组合导出前
的工具回归，不是新增处理器PASS项或覆盖位。

首次四组prepare被成员验收拒绝，尚未生成输出配置或启动DVE：
组合工具错误地将调试报告配置的`corpus_tests`整数701与QBS的
测试路径列表比较。父线程核验实际selected_tests顺序相同、
702个成员路径集合相同、membership逐文件列表完全相同，并确认
701项计数一致。这是工具字段类型错误，不是不同测试集合或RTL
失败；修正时仍须检查计数、实际路径和membership，不能删除
成员核验条件或改用仅比较数量。

## 四组组合应用已启动

上述字段比较已在尚未封存的组合工具中修正：核验整数计数701、
selected_tests顺序、全部输入路径和逐文件membership完全一致。
v2及完整报告树6项工具测试通过，prepare正常完成。

输出目录为`branch-combo-four-policy-701-20261006-01`，最终配置
SHA256为
`41b0112507a9f75e9cd33abbcc18d0dd5d6035736234706af38810e055ad4761`。
对应后台unit为`ara-branch-combo-four-policy-701-20261006-01.service`。
父线程核验了实际启动树及launch-bound DVE PID2548664，使用宿主机
VCS V-2023.12-SP1 DVE，不重新运行处理器仿真。

本次包含4328个精确目标和8282个保护点，仍使用同一套701项PASS
输入。完整应用、清除恢复和最终全局清空由工具审计；任务已启动
不代表结果通过，最终百分比和资格仍待完整产物独立复核。相关
代码和输入已经封存，不再修改运行任务依赖。

窄格式指数表原生核验亦已并行启动，独立目录为
`narrow-exponent-native1272-capture-20261006-02`，后台unit为
`ara-narrow-exponent-native1272-capture-20261006-02.service`。
父线程8项工具测试及独立read_config通过，绑定32个实例、5616个
坐标（1272目标/4344保护）及3392个哈希，pack未加入。配置seal为
`a3c889088d12c71d76dedfe499d5772e1b0340bf6054705292c7461dddeed22b`，
实际launch-bound DVE PID2550770已核验。原准备文档追加导致哈希
不符的记录保留，仅文档使用原SHA精确匹配的历史副本，不重定向
源码或checker证明。原生捕获未完成，尚非完整集合应用或分母批准。

组合脚本只读审查另记录两项限制：刷新报告后没有单独再次导出
目标签名/保护状态，因此不能宣称已完成额外after-refresh审计；
library初始化位于主catch之外，若初始化失败可能缺少Tcl清理，
验证器须拒绝缺失证据。运行任务不改依赖，结果须按实际证据验收。

## 下一条激励的缺口选择

`remaining-branch-gap-ranking-701-20261006-01.json`已生成：只在
诊断视图中移除四组目标及待核验1272范围，原始bitmap、正式报告
和分母均未改变。未绑定metric checksum的实例单列，不猜测归属。
该排名用于避免对已经证明或正在核验的范围重复构造case。

| 主要剩余位置 | 未命中branch位置数 |
| --- | ---: |
| ct_vfdsu_pack.v:178 | 429 |
| lzc.sv:95 | 376 |
| ct_vfdsu_srt_radix16_bound_table.v:105 | 369 |
| qbs_payload_buffer.sv:285 | 236 |
| operand_queue.sv:336 | 206 |
| lzc.sv:76 | 198 |
| fpnew_opgroup_multifmt_slice.sv:232 | 198 |
| ct_vfdsu_round.v:595 | 196 |

这些是位置计数而非覆盖率或已确认可达点。下一步分别从浮点
边界/舍入和QBS合法写入路径分析可达输入，再选择最小判别激励；
不能据此批量豁免这些功能逻辑，亦不能将失败诊断VDB计入PASS集合。

## 1272项原生资格独立核验完成

`narrow-exponent-native1272-capture-20261006-02`已生成终态结果，
父线程逐文件核验哈希并重新执行verify，得到
`EXP1272_NATIVE_REVERIFIED`。状态为
`NARROW_EXPONENT1272_NATIVE_ROUNDTRIP_VERIFIED_NOT_APPLICATION_APPROVAL`，
结果SHA256为
`b2f44e6b0814912965c6476d3e057c2dd34ca76a0144532f107517d6e74ec019`。
5616个完整坐标中，1272个目标原生记录精确匹配，4344个保护点
保留；default/WIDTH64受保护、pack未加入、最终清空通过。

这是单测试原生资格，不是701项正式应用、处理器PASS新增项或
分母批准。当前四组任务不修改也不重启；后续需独立版本将此范围
应用到完整集合并验收，不能直接把1272点换算为正式百分比。

## SRT边界表新激励假设

父线程核对旧镜像封存的prepare、SRT及radix16源码：普通除数
规格化尾数左对齐，`initial_bound_sel_in`取其隐含1及高6位，
经initial寄存器写入bound table的选择器。因此FP64/FP32/FP16
各扫描`1+k/64`、k=0..63，理论上可选择0x40..0x7f的64个表项。
使用`x/x=1`和`(-x)/x=-1`可用精确位模式检查结果和零fflags，
避免把新的舍入近似引入测试oracle。

`test_divisor_bound_scan_scope.py`的3项检查通过：封存源码及连线
选择链、initial寄存器捕获、三种精度的64个选择器和精确有理数
预期值。它是激励设计前置证据，不是已通过RTL或新增覆盖位。
仍需逐物理实例确认raw701未命中表项、Spike预检和旧镜像严格
验收；若失败，记录首错并排除VDB，不在本目标中修RTL。
后续需重新绑定701项集合再取得组合报告，不把两份报告的百分比
增量相加。

### 三种精度除数扫描的前置验收

`gap95-divisor-bound-preflight-20261006-01` 中的 FP64、FP32、FP16
三个独立 ELF 均完成 Spike 自检，分别执行1616、3152、6224项检查。
每项检查包括精确结果、源数组保持、fflags、vstart、VL及输出边界；
三者各有48条被测向量 load/div/store 指令。这里的48不包含vset类
配置指令，不代表完整程序的向量指令总数。

父线程复核公共C源码，并运行激励及封存源码链的6项单元检查，全部
通过。raw701逐物理实例绑定显示，16个bound-table实例中有353个
普通除法选择表项尚未命中；default和非普通除法项不是本激励的
目标。该数字是目标缺口，不是已获得的覆盖增量。

目前状态为 `GAP95_THREE_SPIKE_PREFLIGHTS_PASS_NOT_VCS`，尚未计入
701项PASS或覆盖率。后续只复用旧镜像，独立目录运行并完成严格
标量/向量比较；若暴露RTL错误，记录而不修复、不纳入其VDB。

## QBS payload写入缺口的初步可达性分析

第285行的236个未命中点均为slot0 pending写数据的`01`分支：两bank
的weight plane0/1、四row的byte14–15共32点；bank0 activation
plane2各row byte12–31共80点；bank1 plane2各row byte1–31共124点。
地址预解码、adapter pending保存及最低word优先仲裁的相关源码
与旧镜像封存哈希一致。

合法weight基址要求2字节对齐，activation要求4字节对齐；M≥5
必须采用M8_INTERLEAVED，不能用非法M8 ROW_MAJOR强行命中。有限
事务枚举中weight pending只出现byte0–13，M8 activation pending
只出现byte0，与缺口形状相符。但尚未完整证明backpressure、clear、
context replay及所有合法事务衔接，因此236点全部保留，不豁免。

建议的M8、N1、单K块、activation地址mod16=4定向case预计只会
验证已有命中路径，不能承诺覆盖增量；本轮不为追求case数量启动
该实验。优先执行有明确353个目标位置的除数扫描，并准备独立
五组豁免应用，保持正在运行的四组任务依赖不变。

## GAP95三路旧镜像运行启动

三路独立systemd用户任务已启动：
`ara-gap95-div64-bound-20261006-01`、
`ara-gap95-div32-bound-20261006-01`、
`ara-gap95-div16-bound-20261006-01`。
实际VCS进程PID分别为2570378、2570381、2570386，命令中的ELF、
TESTCASE、trace及VDB目录均逐项核对，日志确认三种精度各自加载了
对应ELF。每项墙钟上限600秒，复用冻结镜像，无RTL或构建修改。

新增`admit_gap95_batch.py`，按三个独立结果分别执行软件签名、
协议日志、完整Spike标量及向量精确比较，失败项保留诊断且排除。
向量检查要求48条及12288字节全部精确匹配，无未知字节跳过、
未完成、未退休或异常请求。集合成员及源码/镜像/VDB证据固定，
只能将通过项追加到701项集合。运行器8项及验收器3项单元检查
通过；这不是三项处理器PASS或已提高覆盖率的声明。

## GAP95完整验收及704项集合

三项运行均正常终止，`admit_gap95_batch.py`完成独立软件自检、
协议检查及完整Spike标量/向量精确比对，三项全部PASS。新集合为
`gap95-offline-admitted-20261006-01`，704项，原701项成员保持原序，
只追加这三个独立VDB，无RTL修改或新RTL signoff声明。

相对701项原始bitmap新增374个line位置、374个branch位置，cond及
FSM未新增。逐项复核preflight目标表：353个未命中的普通除法表项
全部被本轮命中。374是包含其他路径增量的总位置数，不是百分比。

已启动`ara-raw704-dve-20261006-01`独立报告任务，使用704项精确
输入清单和`DVE_WAIVERS=off`，输出为`raw704-dve-20261006-01`。
正式百分比必须等待实际DVE导出及人口清单核验，不从bitmap直接
估算，也不把尚在运行的701项四组豁免增量加到704项报告上。

## 701项四组联合报告完成并独立复核

`branch-combo-four-policy-701-20261006-01`正常退出。父线程重新
运行绑定、完整原生记录、保护点、输入哈希、实际DVE启动及报告
验收，结果为`FOUR_POLICY701_REVERIFY`，无差异。保存结果的文件
清单按运行器约定比重算结果多config.json及selection.tcl两个
哈希；先前直接比较整个字典的断言因此失败，按这两个明确额外
证据核验后匹配，不改写原结果或放宽实际证据检查。

4328个原生排除记录及8282个保护位置核验通过，最终全局清空。
同一701项集合的实际rooted i_system报告如下：

| 阶段 | Branch | Score |
| --- | ---: | ---: |
| 原始 | 81.92% | 73.89% |
| 四组应用 | 85.24% | 74.55% |
| 复位清除 | 81.92% | 73.89% |

这是701项历史产品范围的组合报告，不是704项报告，也不是新RTL
signoff或所有豁免的正式分母批准。四组会话仍存在此前记录的
after-refresh附加审计限制，不能用本结果宣称完成未提供的审计。
五组后继工具另增加刷新后完整原生/保护核验，父线程15项测试
通过；不修改已经封存的四组任务和依赖。

## 最新704项原始DVE百分比

`raw704-dve-20261006-01`正常导出，父线程重新运行
`verify_historical_raw_report.py`，核对704项实际选中测试、设计输入、
诊断为空和waivers禁用，状态为`VERIFIED_HISTORICAL_RAW_REPORT`。

| 指标 | raw701 | raw704 | 变化（百分点） |
| --- | ---: | ---: | ---: |
| Line | 82.24% | 84.67% | +2.43 |
| Condition | 81.73% | 81.73% | 0.00 |
| Branch | 81.92% | 82.30% | +0.38 |
| FSM | 60.46% | 60.46% | 0.00 |
| Toggle | 63.08% | 63.09% | +0.01 |
| Score | 73.89% | 74.45% | +0.56 |

以上是i_system同一旧镜像的原始实际报告，不含四组或五组豁免。
条件及FSM没有因除数扫描而提高，后续另针对控制组合和状态转换
检查合法激励，不将本次行/分支改善说成所有覆盖维度都已改善。

## GAP96及五组任务已启动

GAP96扫描FP32最小正规数除以`2^n`，n=0..52，并覆盖正负号。
指数差经round加127偏置后，pack的组合case输入为1-n；即使
数值已下溢成零，该组合表的输入仍会变化，不能仅因输出不用而
把该路径豁免。独立精确有理数oracle检查RNE舍入及UF/NX标志。
每种指数重复8个元素，使四lane的两个FP32物理位置都得到激励。

`gap96-div32-pack-preflight-704-20261006-01`沿用已通过Spike的
原ELF，重新绑定704项集合；96个目标仍未命中。源码、目标身份及
运行器的11项父级测试通过。任务`ara-gap96-div32-pack-20261006-01`
已启动，实际VCS PID2591430及对应ELF加载日志已核对。待完成严格
验收，不能先计入PASS。

五组任务`ara-branch-combo-five-policy-701-20261006-01`也已启动，
config seal为`9ee807bbb65c0f2404dac7970507a2903820ff44943b5169660295848fffaba8`。
5600目标、12626保护位置，实际launch-bound DVE PID2590885。
增加刷新后的完整原生及保护审计；当前仅运行中，仍绑定701项，
不能冒充704项应用结果。所有封存的旧任务和依赖保持不变。

## GAP96验收工具风险修正及705项集合

审查发现共享`admit_fp64_scan.py`在收集文件时会把已有expected pin
替换为文件当前哈希，存在掩盖证据漂移的风险。原GAP96薄适配器
没有用于准入；旧helper不改，新增`admit_gap96_offline_v2.py`。
后继工具先核验封存的704重绑manifest及其全部expected pins，再
绑定运行manifest和基线链；已绑定文件的每次hash读取必须与原
expected一致，冲突拒绝，保存时也不能替换已有expected。3项
测试检查原pin不可覆盖、文件漂移拒绝和共享helper未改。

GAP96运行正常退出，经该后继工具完成软件自检、协议检查及
完整标量/向量精确比对。输出为
`gap96-offline-admitted-705-20261006-01`，集合增至705项；42条
向量请求、10752字节严格匹配，无跳过未知字节或不完整请求。
相对704项新增118个line、47个condition、118个branch位置，FSM
未新增。父线程逐目标复核96个原始未命中pack表项，96个全部命中。
没有修改RTL、重建镜像或修复已记录的RTL错误。

已启动独立`ara-raw705-dve-20261006-01`原始报告任务，waivers禁用。
正式705项百分比待实际报告及选中测试清单核验，不把新增位置数
直接换算为官方百分比。下一批诊断以705项集合为基础，优先
分析普通RVV、dispatcher及系统路径的condition/FSM合法缺口。

独立审查确认v2已关闭expected-pin替换风险，未发现新增阻断。
随后新增`test_gap96_expected_pin_integration.py`：使用临时小型
证据链实际调用共享helper的完整收集循环，在console封存后改变
内容，必须在比对和输出创建前拒绝，且原manifest expected不变。
该集成负例及原3项检查共4项通过。测试使用临时文件，不修改
实际704/705证据、共享helper或任何RTL，不需要重新仿真。

## 705项实际报告与控制路径补充计划

`raw705-dve-20261006-01`正常完成，父线程实际运行人口核验工具，
确认705项独立输入和实际选中测试一致、诊断为空且waivers禁用。
最新i_system原始报告为：

| Line | Condition | Branch | FSM | Toggle | Score |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 84.76% | 81.75% | 82.42% | 60.46% | 63.09% | 74.50% |

这些百分比来自DVE，不由新增位置数估算。FSM仍未提高，因此
下一批不是继续重复浮点数据扫描，而是补两个明确合法路径：

1. CSRRS/CSRRSI置vxsat、CSRRC/CSRRCI清vxsat，以及旧值为0时
   CSRRCI zimm2；独立初始化并检查旧返回值、新值及VCSR一致性。
   配合AVL=`1<<20`、e8/m1检查VL128，目标为dispatcher六个
   未命中condition坐标。旧dispatcher必须使用封存哈希一致的
   源码，不能用integration当前不同字节解释旧镜像。
2. PMP明确拒绝独立页表页读取，sfence后冷翻译load应产生访问
   异常5而不是页错误13；handler检查PC和VA，恢复权限后再翻译
   必须成功。目标是PTW错误状态及进入/退出转换，同时先检查
   PMP readback及handler可执行性，避免异常递归。

以上仍为待实测的激励计划，不计入705项或覆盖率。

## LZC selector branch的新结构候选

`inventory_lzc_selector_branches_705.py`绑定旧LZC源码、编译WIDTH
10/23、MODE1、准确generate坐标、branch checksum及705项bitmap。
共发现60个未命中selector分支：对应左子树全部由填充位构成，
正常二态下selector恒0。另636个位置保留。3项测试检查填充证明、
真实输入左子树必须保留以及表达式错绑拒绝，实际inventory通过。

产物`lzc-selector-branch-candidates-705-20261006-01.json`仅为
结构候选。原生branch向量/真假臂身份还未独立校准，不能直接
从XML vector编号生成EL；不豁免、不改变分母、不排除四态初始化
行为，也不将历史180项condition排除当作新branch资格。

对既有690项selector条件清单重新绑定705项bitmap与编译shape，
产物为`lzc-selector-condition-candidates-705-20261006-01.json`。
结果仍为22个已命中保留点、60个布尔selector结构候选、60个
ternary原生语义待核验点。它们与新增60个branch候选属于不同
metric，不能合称已经批准180项新豁免。现安排独立原生身份
资格工具，先确认真假选择语义及完整保护范围，再决定能否应用；
不修改现有封存工具和运行中的五组任务。

## AKV73历史用例的独立复核

父侧独立检查`closure92-akv73-fulloracle-713-20261006-01`中1844个
封存输入哈希，全部一致，并直接对原始ELF、stdout、commit trace和
vector trace重新运行检查器。11条custom命令、6次预期异常、11944
字节内存检查全部通过；非法命令的VRF写入为0字节，恢复路径写入
384字节，全部后端分配均完成。此次没有重新仿真或修改RTL。

独立unittest执行31项，其中28项通过、3项因未指定实际preflight
而跳过；不能把这3项称为已执行通过。现有带实际preflight的封存
重放结果仍需与后续严格collector一起复核。该用例目前未加入正式
713项集合，以上结果不是新的DVE百分比，也不关闭旧QBS fault故障。

## LZC原生位置核验后台任务

已独立核验`lzc_selector_native_product_batch-707-20261006-02`的
2936个输入哈希和5项预算/保护测试，并启动一次DVE session。
实际`dve.exe` PID为2752663，supervisor为2752568；启动命令已由
进程表确认。该批核验120个候选位置，保护4200个原生位置，DVE
上限10500秒，不自动重试或自动批准最终豁免。输出在独立02目录，
不会覆盖01或已封存的707原始报告。

任务使用实际discovery耗时作为预算依据；预算文件中的
`user-reported context`来源标签不准确，该辅助上下文来自父侧
agent观测，不是用户提供。它不作为测得查询延迟，也不影响原生
位置资格判定。运行完成后仍需核验单项EL绑定、保护点不变和
最终reset证据，才能决定哪些位置可以正式豁免。

## AKV73收集候选的父侧验收

`closure92-akv73-strict-collector-714-20261006-01`的12项测试通过，
父侧执行`collector.py verify`以退出码0完成。随后独立从原始VDB
重新收集candidate bitmap，与封存candidate完全一致；同正式713项
执行union后，与proposed集合及delta完全一致。集合顺序保留全部
713项并仅追加AKV73，无重复VDB或ELF。

实际原始增量为行0、条件6、分支0、FSM0。已授权生成全新正式714项
目录，但本节记录时正式输出尚待完成核验；不提前替换文档顶部
正式集合，也不将707项DVE百分比标成714项。授权来源是父侧agent
在用户goal范围内独立执行与审批，不是用户提供的通过声明。

## GAP100参考平台修正的静态根因

独立参考目录`gap100-spike-platform-matched-713-20261006-01`
使用`--disable-dtb`，120秒内未完成；trace反复出现PC0的取指访问
异常。父侧核查Spike `sim_t::reset()`确认该选项不仅跳过CLINT
创建，也跳过`set_rom()`，因此没有安装正常reset ROM。增加超时
不能解决此启动配置错误，不据此报告RTL故障，也不纳入覆盖率。

后续方案保留正常DTB/reset ROM，使用独立DTB仅删除CLINT设备
节点，保留CPU ISA、PMP和MMU配置，并复用相同ELF及已有RTL
trace进行严格比较。DTB修改使用结构化工具，不忽略mip读值；
参考平台匹配资格仍需运行证据，不能从静态分析提前宣称通过。

保留reset ROM、仅去掉CLINT的新参考目录为
`gap100-spike-no-clint-dtb-713-20261006-01`。其逐指令比较结果
为`TERMINAL_TOHOST_MATCH`：6830条非trap提交、3116次标量寄存器
写入、1306次内存访问匹配，未跳过不可观察寄存器值，没有差异。
该数值来自新的参考重放，不是重新执行RTL。异常handler观察与
RVFI trap事件的完整对应仍须验收，尚未纳入714项集合。

父侧另外执行4项DTB检查测试通过，并使用系统`/usr/bin/fdtget`
逐节点逐属性独立遍历两个DTB，不依赖参考脚本自身的FDT解析器。
唯一差异为删除`/soc/clint@2000000`，保留的10个节点、46项属性
完全一致，包括CPU配置与内存属性。该证据约束平台修正范围；
不等于中断功能的覆盖证明，也不能替代异常账本和严格准入验收。

## LZC批量核验02的工具失败

`lzc_selector_native_product_batch-707-20261006-02`运行225.767秒
后结束，DVE退出0，但验收状态为`FAILED_RECORDED_NOT_QUALIFICATION`。
初始及最终保护表均仅写入2项，不是4200项完整证据；GUI报告第一
scope的`Branch1.0`不可选择。最终排除文件为空，未批准任何新豁免。

父侧对照03只读查询记录确认该scope中`Item1/Branch1.0`真实存在。
成功查询在切换Branch详情后执行`gui_list_expand ... -all`，批量
`lpb_row`则直接选择，缺少展开步骤。当前假设是GUI折叠状态阻止
选择，并非该位置不存在；须先用可见性模拟测试核验后，再生成
独立后继脚本。不能通过忽略缺失行、缩减保护范围或放宽断言通过。

## 下一批可达控制路径的筛选依据

父侧重新解析已核验`raw707-dve-20261006-01/summary.csv`的完整
Depth层级，而非只匹配短模块名。该707项历史报告中Dispatcher
FSM为60.26%、segment sequencer为66.67%、PTW为44.00%，
cache adapter与其AXI shim均为22.22%，WT D-cache为33.75%。
WT D-cache read port2的FSM为0%，其余两个read port为25%和40%。

这些数值只作为静态筛选方向，不冒充714项最新分项。低覆盖或0%
本身不构成豁免理由：须核对旧镜像封存源码与端口连接，区分未启用
接口和可达但缺激励的缓存miss/flush/顺序状态交互。已安排优先
分析可达FSM路径和短系统定向激励，不继续重复同类浮点数据扫描。

## 固定关闭的D-cache读端口2

父侧核对`cva6.sv`、`acc_dispatcher.sv`、`wt_dcache.sv`及
`wt_dcache_ctrl.sv`四文件，哈希均与旧镜像manifest708中的
`common_expected_pins`一致。CVA6缓存请求口2连接accelerator读
请求口0；acc_dispatcher将这组请求固定为0，未启用accelerator时
也固定为0。WT D-cache的read port2使用该输入。

控制器复位为IDLE，IDLE离开条件为`data_req && !stall_i`并收到
read ack。由于`data_req`固定0，正常复位后状态归纳地保持IDLE；
READ/miss/replay/kill请求状态无法由该接口进入。这是结构约束，
不是因为随机测试尚未覆盖。已安排生成逐项候选及保护清单，但
尚未批准DVE豁免。复位、IDLE/default和输出赋值不整模块排除，
其他可达缓存端口仍需激励，不豁免故障注入或四态初始化行为。

## 六组707项历史豁免报告验收完成

`branch-combo-six-policy-707-20261006-02`已结束。父侧独立执行
`read_config`和`verify_artifacts`，退出码0；结果为
`EXPLICIT_HISTORICAL_BASE_EXACT5808_PRODUCT_BRANCH_REPORT_NOT_AGGREGATE_SIGNOFF`。
核验5808个目标、13562个保护位置，共19370项；root刷新后再次
审计及原生导出通过，最终reset通过。01失败记录仍保留。

| 707项报告阶段 | Line | Condition | Branch | FSM | Toggle | Score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 原始 | 85.12% | 81.82% | 82.85% | 60.46% | 63.12% | 74.67% |
| 应用六组历史豁免后的DVE呈现 | 85.12% | 81.82% | 87.59% | 60.46% | 63.12% | 75.62% |
| reset | 85.12% | 81.82% | 82.85% | 60.46% | 63.12% | 74.67% |

Branch呈现值增加4.74个百分点，清除后恢复原始值。状态仍明确
`aggregate_admission=false`、`official_denominator_verified=false`，
不据此宣称当前714项最终覆盖或RTL signoff；这些结果只证明
707项历史基底上精确六组应用的效果。不包含LZC/PTW/读端口2
尚待资格核验的新候选，也没有把FAIL/TIMEOUT加进测试集合。

## GAP100严格收集候选独立验收

父侧审核异常账本和收集脚本后，独立执行7项ledger测试及10项
collector测试，全部通过；核验候选5939项输入哈希，全部一致。
从原始trace重新构建23次异常账本，与封存账本完全一致：15条
ECALL RVFI trap、6次illegal instruction、1次breakpoint和1次SSIP。
后8次的RVFI缺项由封存RVFI valid门控解释，实际handler入口、
cause/EPC观察、EPC改写与返回路径均单独检查，不当作丢失异常。

父侧重新读取原始VDB并与正式714项做union，candidate、combined
及delta均与封存候选完全一致。增量为line3/condition13/branch4/
FSM0，14个目标点均命中。已授权生成独立正式715项目录，但本节
记录时尚待正式产物验收；顶部正式集合仍为714项。没有改RTL或
重跑仿真，向量数据仍为零预期目的写入的UNOBSERVABLE范围，不
虚报向量比较PASS。

正式715项产物随后完成父侧独立验收，seal为
`069e9e7717e915c18ce921f583fa33bf18e7670a3f13ec12073e8bba1998a283`。
本节先前的候选状态为过程记录，顶部已更新为正式715项。

LZC批量核验03已通过父侧7项测试及2952项输入pin检查，120个
候选和4200个保护点与02一致。已启动独立后台任务，实际DVE
PID2787004，入口为`lzc_selector_native_product_batch_v3.tcl`。
完整初始4200项审计完成前不允许单项排除；上限10500秒、不自动
重试、无最终自动豁免批准。01/02失败记录不改变，尚无03豁免结果。

03随后在20.504秒结束，未生成`global-before.tsv`。原生DVE日志
报告`EK-CMD-013: command cannot be renamed`，发生在重命名
`gui_exclude_items`时，早于初始对象审计。退出码0不能视为资格核验
通过；该批次没有提供可准入豁免。后继脚本须使用独立包装过程，
不得重命名Synopsys内建命令，并补充这一限制的测试。

父侧独立执行读端口2原生资格计划的`prepare.py verify`及5项测试，
均通过，计划哈希为
`a53792a82badd5a6ed2d8503829231f95728e3e4103e1362a51f2fca5735446c`。
计划含27个FSM、35个行和31个分支候选，保护IDLE及可能的自环、
复位、默认路径和全部条件/toggle对象。这里只验证离线计划绑定，
尚未获取原生DVE选择器或应用豁免，不改变715项正式集合的覆盖率。

## GAP101非法segment store预检

父侧审阅激励和独立判据，重新解码`0xe2050827`及`0x22050fa7`：
分别为NF=8、v16、e8、m2导致NF×EMUL超限，以及NF=2、v31、
e8、m1导致寄存器组越界。预检02的70项输入pin、ELF字节、原始
Spike轨迹和715项目标位重新核验通过，10项检查器测试通过。
预检seal为
`fb201ab205a72b1790da0873237868bb7b389c9c0b9d08a589953851df652298`。

Spike预检观察到精确两次非法指令异常、1075项检查通过；检查包含
8192字节VRF快照、非法store的目标内存不变和后续合法store恢复。
四个dispatcher目标点在715项集合中仍为零。已授权一次独立目录的
旧镜像VCS运行，预算600秒、无FSDB、保存架构轨迹及VDB；此时
尚无RTL通过或新增覆盖率结论，不准入、不自动重试、不修改RTL。

## 715项原始DVE报告后台导出

父侧执行`prepare_raw715_dve.py check`及11项测试，全部通过，配置
seal为`c7607c51d0dd85f446817fbfc5a02d1e3c15d1383ee17166eae09ead17bf3667`。
随后启动独立原始报告任务，父侧通过实际进程树确认监督进程
2797907、启动器2798409及DVE进程2799618。输入为正式715项
清单，waiver关闭，输出`verification/out/raw715-dve-20261006-01`。
这是读取既有VDB的报告导出，不重新仿真。完成并验收前，最新独立
百分比仍标记为707项历史数据，不能提前将其称为715项百分比。

## LZC内建命令保持不变的后继资格核验

父侧审阅v4代码及Tcl，8项单元测试通过。后继仅将自有`lpb_session`
中的一处排除调用改为保护包装过程，再调用原生`gui_exclude_items`，
不重命名或重定义DVE内建命令。独立核验2965项输入pin全部一致，
120项候选及4200项保护点保持不变，plan seal为
`9989497998e55cf715bee8d1ecdf93c378bf814d548a918c171c336508296283`。
已启动后台监督进程2802342，目录为
`verification/out/lzc_selector_native_product_batch-707-20261006-04`。
只授权单次资格测量，尚未得到原生核验结果，未批准应用豁免。

## GAP101旧镜像segment store寄存器越界失败

一次VCS测试已结束，tohost写入3（失败），软件记录1075项检查、
7项差异。父侧独立解析原始commit trace：第一阶段NF×EMUL超限
产生mcause=2及完整异常账本；第二阶段`0x22050fa7`对应
`vsseg2e8.v v31`，未异常，第二份账本全零，总异常次数为1而非2。
该指令在周期22691和22744分配两条微操作，并在22766提交，PC为
`0x80002284`。目标快照第二阶段word2实际为
`0xa5a5a5a5a5a5405f`，预期全为`0xa5`；低字节0x5f和0x40对应
初始化的v31和v0，说明非法访问绕回后产生了内存副作用。

冻结dispatcher在1202行将请求默认字段置零，store解码4389行把
指令的源寄存器号放入`ara_req.vs1`，但4543行的segment寄存器
越界检查使用`ara_req.vd`。segment_sequencer第234行按vs1加
segment偏移形成实际store源。静态字段路径与观察到的越界未拒绝、
v31/v0写入一致；七项自检差异不能算成七个独立bug。

原始失败轨迹和VDB保存在
`verification/out/gap101-illegal-segment-store-old-image-20261006-01`。
本轮不改RTL、不重建镜像、不将该FAIL或其中的局部命中纳入覆盖率。
可将独立NF×EMUL检查拆成新测试重新取得完整PASS证据，但原始
寄存器越界失败仍单独保留，不能借拆分宣称GAP101整体通过。

父侧随后重放封存失败审计，148项输入哈希和完整差异账本一致，
3项检查器测试通过；确认该记录未准入。

## 715项队列缺口的参数化分类

父侧核验`operand_queue.sv`和`operand_queues_stage.sv`均与冻结
镜像源哈希一致。mask_m、slide_addrgen_a和st_mask_a实例采用
FPUSupportNone，整数扩展、归约及中性值填充支持参数为默认关闭；
这些参数禁用分支应按具体覆盖点证明，不以整个实例为豁免单位。
mask_b则显式开启IntExt2/4/8，不能套用前三者的禁用结论。
请求消费、队列握手、计数、pop及实际连接的flush路径仍须保留。
新的原始715项报告中前三种队列的低分支率分别为32.59%、33.33%、
34.81%，参数解释不等于这些缺口已完成豁免。

读端口2只读DVE清单01已结束，状态`HOLD_NATIVE_QUERY_INCOMPLETE`，
五种指标均存在原生查询缺项，未产生或应用豁免。行/分支/toggle的
列模式查询达到128列边界仍未得到可靠终止；FSM/条件存在字段查询
不支持。须先依据保留的HELP/QUERY返回修正工具调用并补测试，不能
把DVE退出码0或部分清单当成完整原生资格证明。

## GAP101A独立NF×EMUL激励预检

单独激励`vgap101a_nf_emul_only.c`保留非法NF×EMUL拒绝及合法
segment store恢复，不执行已证实有bug的v31寄存器越界情形。
原GAP101失败记录和VDB完全保留，不以这个独立激励替代原测试。
父侧审阅源码/检查器并重新读取原始Spike轨迹，539项检查、一次
非法指令异常、4096字节VRF不变和目标/recovery各64字节守护通过。
88项输入pin一致，5项检查器单元测试通过。预检seal为
`e558c325ed1e28876b021d2e0c2b0ff48a0f6e90dc683d424e47714668f65dc5`。
目标仅为715项中的branch raw345和line raw1334，未将已失败的
寄存器越界目标混入。已授权新目录的一次固定旧镜像VCS测试，预算
600秒、无FSDB，保存commit/vector轨迹和VDB；尚未准入覆盖率。

父侧随后确认GAP101A实际simv PID2815825，运行独立目录
`gap101a-nf-emul-only-old-image-715-20261006-01`，PRELOAD指向上述
固定预检ELF；实际命令保留五类覆盖采集、架构及vector轨迹，关闭
FSDB。这是启动确认，尚无PASS或新增位结论。

读端口2清单失败的离线复盘也通过父側只读核验。问题是查询脚本
假设越界列会报错，而原生接口实际返回成功加空值；条件名称返回
单元素列表包装，未经规范化导致选择失败。FSM名称state_q及List
视图已被原生接受，但脚本在读取行前终止，因此不能宣称FSM不可
枚举。后继须以实际日志返回补测试，保留完整保护范围和01记录。

父侧进一步从715原始bitmap按分支根行分组，lane0的mask_m、
slide_addrgen_a及st_mask_a分别都剩81个分支点：根行244有22项、
336有45项、502有14项。前两组与中性值/归约、转换类型选择有关；
502仍包含转换selector及公共消费控制，不能仅依据低覆盖率追加
mask/store/slide测试或整体豁免。MaskM生产者显式conv=None，但
StA和SlideAddrGenA分别接pe_req.conversion_vs1/vs2，必须继续
核实dispatcher和所有请求生产路径。新豁免候选还需扣除此前已经
资格核验的点，避免重复计数或把结构性组合误当作可达缺口。

GAP101A随后VCS终端SUCCESS，CPU时间65.630秒。父侧独立解析
原始CSV，539项检查零失败、异常账本完整、非法指令未提交、VRF与
目标/recovery快照无差异；contract请求78/响应78、异常1、协议
错误0、在途0。独立读取原始VDB与715项bitmap诊断合并，新增
line1/condition1/branch1/FSM0，预定branch345和line1334均命中。
这只是局部oracle及覆盖诊断，完整架构比较/严格collector仍待验收，
不将模拟退出码0或这三个新增位直接等同正式716项准入。

父侧随后独立运行完整commit及vector比较。标量结果为
`TERMINAL_TOHOST_MATCH`，13025条提交、6436次GPR写回、1731次
标量访存全部匹配，未知值跳过数0、无差异；向量比较PASS，32条
初始化指令/4096字节逐字节匹配，无未知、非bit-exact或未完成请求。
非法store为arch_seq37，其异常账本及无内存/VRF副作用另由独立
检查核验，不把仅覆盖初始化写回的vector PASS冒充非法store证明。
严格collector及正式集合准入仍待完成。

读端口2原生查询后继02已通过父侧18项测试及封存输入核验，seal为
`2d94c160dbb54f09254025b3335908866ea0ee6bc0804987f717e959567df5ed`。
采用上一轮实际空列边界和名称包装返回，字段查询不全仍保留HOLD；
未知列模式不再阻止行树读取。已授权一次300秒独立只读DVE枚举，
未授权任何排除、reset/import或正式豁免应用。
# 父侧续推进记录：indexed restart 与检查器环境问题

## 最新正式集合：725项PASS

父侧完整审查`admit_gap105_offline.py`及tests，20项测试PASS，
实际prepare后独立admit已成功。目录：
`gap105-offline-admitted-725-parent-20261006-01`。
admission seal：
`0f49638e8cea36b28b5832e7eaeea39ee9b5249a162de3f3732c0fcd13a5a397`。
父侧再次核验输出hash无漂移、725个唯一成员、原724项有序前缀
完全一致。新增GAP105一个PASS，原始位图增益line0/cond191/
branch0/fsm0，12个目标均命中。独立native及全VRF/CSR/guards
契约通过，不声称custom Spike或完整标量ISA差分。无新仿真、
无重新采集bitmap、无RTL修改；历史失败不计入。
最新DVE百分比仍对应723项，与725项正式raw集合必须分开引用。

LZC前台恢复prepare另发现环境扫描错误：全用户/proc扫描遇到
PID624598的cwd权限拒绝；ps表明这是UID1002的(sd-pam)，
不是EDA进程。prepare在创建侧目录前拒绝，未启动DVE。
需限定实际EDA候选身份，不能泛化忽略PermissionError，也不能
让不相关PAM进程阻止目标任务。保留原恢复源及拒绝事实。

LZC启动器return0并非DVE开始：systemd服务KillMode=control-group，
短launcher退出后子worker3080799消失；原status仍PREPARED_NO_DVE，
无execution、runner log为空。已重建background的Popen路径，
`start_new_session`不能逃离systemd cgroup。保留旧claim及记录，
使用显式一次恢复入口，systemd直接托管前台长寿命worker；
未修RTL，不重prepare原配置，不在DVE未执行时引用覆盖百分比。

indexed-load正确端口8的condition1050/1063/1206、branch690在
四lane均已被724项覆盖，本次也命中。原端口6目标标签错误，
总raw增量0是有效诊断。后续只对MaskM/StA恒0生产路径建立
不可达证明候选，暂不应用任何排除。

父侧额外复核历史carry_illegal超时：724项inputs已明确包含
`gap36-timeout-current-20261004-01/results/vgap36_carry_illegal/.../code.vdb`。
后继程序将原555项测试和mtvec初始化放在M-mode初始化hook，
避免原U-mode main写mtvec造成异常循环；预期未放宽。
因此历史原ELF TIMEOUT记录不能说成当前仍在超时，也不能
将不同ELF后继PASS冒充原ELF修复。该环境后继已入集合，无需
重复运行或重复计入。实际RTL FAIL仍保留，不在此修复。

indexed restart实际raw诊断相对724项的line/cond/branch/fsm增益
均为0，故不作为正增益准入项。原16目标绑定requester_index=6，
父侧静态发现枚举中6是MaskM、8才是SlideAddrGenA；不声称
该测试已覆盖原目标。保持功能PASS证据，纠正端口映射后再研究
剩余可达缺口，不重复跑该程序。raw诊断目录为
`operand-index-snapshot-raw-diagnostic-agent-20261006-01`。

724项七策略DVE启动entry已实际准备并由父核验合同，seal为
`e729bbf04bec7d85d162af00baafffe97dc6f90e41701ddc37210d8ce7665bee`。
已提交独立后台launch unit
`ara-lzc-seven-dve-launch-724-parent-20261006-01.service`，
日志`lzc-seven-dve-launch-724-parent-20261006-01.log`。
启动前11184 pins核验及后续DVE仍须区分；此处不宣称新增60项
条件豁免应用成功，也不宣称新百分比。旧723报告保留。

两项环境检查问题已完成实际资格核验，尚未正式准入：
indexed restart后继完整核验seal为
`8074b4a620ae093e5812a0de0aa00321562143d45cb260dad9e9ce8e038cd2a6`，
父侧187个输入/输出pin无漂移；7395条退休、645次压缩访存及
726次非压缩访存全部检查，无跳过，并完成向量/CSR/签名核验。
GAP105冻结最终v5配置455pins后，父实际collect已通过，
qualification seal为
`77a1291e96d477d56744100af93a0d0b4a4c97da4fbaccd523a7827d3f0000f5`。
原191个条件新增位可进入后续准入评审，不等于已正式725项。
不重新仿真、不改RTL，旧拒绝记录保留。

LZC严格后继724准备已经实际成功，runtime-plan seal为
`2e556f60fc95ace5e71b41483d481cad85e34cdf696e789d85da11d5614bdb36`。
尚待launch-entry审查，无新增DVE运行或正式豁免应用。
GAP105 v5 prepared seal为
`7cfd0c85b2e921a9d8aea7bace400dbfdd419c709df1a1d83bc12c1716536423`。
实际collect因prepared配置不一致拒绝；父侧独立核对发现唯一
pin差异为v5检查器源码从541f78a9...变成ff4d1f15...，仿真输入、
旧镜像及其结果未变。该次不准入，停止编辑并审查差异后使用
新侧目录重新prepare/collect；不覆盖旧封存、不重新仿真。

723项六策略DVE实际终态已经核验，capture seal为
`ffb5573d71d9c9618a7c86216a29f0fab140c5f3662b8f80efc2a022d5495e0f`。
独立审查确认精确723项成员、10231输入pins、48输出pins，
5808目标/13562保护点及reset/reload一致。i_system原始指标：
Line85.16%、Condition81.87%、Branch82.89%、FSM60.54%、
Toggle63.17%、Score74.72%；六策略应用后Branch87.63%、
Score75.67%，其余不变。不得冒称724项最终报告或最终豁免批准。

LZC严格序列化后继工具父侧12项测试PASS，已独立后台prepare，
unit为`ara-lzc-seven-runtime-v2-724-parent-20261006-01.service`；
日志在`lzc-seven-runtime-v2-724-parent-prepare-20261006-01.log`。
准备期间尚无新增DVE任务。QBS v5准确补C.FLD/C.FLDSP及FP
目的寄存器识别，父侧46项测试PASS；真实trace缺失的8条读回
opcode为0x3406/0x24e6，本地Spike源码宽度/编码已独立核对。
正式collect及覆盖准入仍待实际通过，不能用工具测试代替。

AKV skew的12阶段独立读回封存父侧verify PASS，12项真实
fixture及损坏负例测试PASS；36864个分阶段字节覆盖原目的组、
guards、source、seed、descriptor/copy。仍不声明full32VRF或
完整标量ISA差分，尚未正式覆盖准入。

indexed restart运行已终止，CPU 38.660秒，Core SUCCESS，
19次请求/响应、0异常、0协议错误。实际完整audit在标量签名
检查处拒绝`Unknown scalar store`，原因是所调用的通用helper
只处理非压缩标量访存；trace共有321条压缩store未识别，首条
PC=0x80002002、opcode=0xe422（C.SDSP），后续有0xc190（C.SW）。
这不是DUT失败证据，亦不允许略过这些内存副作用。保留原runner
及仿真产物，用后继检查器补准确RVC解码/真实trace负例测试，
通过完整核验后再测覆盖增益，无需重新仿真。目前未准入。

正式准入仍为724项PASS，本段不增加正式测试数。新标准RVV测试
`voperand_index_snapshot_restart` 使用e32/m2、VL=37、vstart=13，
索引和目的均为v8；独立检查前缀、尾部、邻接寄存器、输入和CSR。
父侧已阅读冻结RTL相关路径、程序及runner，24项工具测试PASS。
已核验158个输入pin并启动一次1200秒上限的旧镜像VCS，
目录为`operand-index-snapshot-old-image-parent-20261006-01`，
实际simv PID为3069917。不得把启动或退出码直接计为PASS；
完成后仍需完整标量/向量比较、签名和实际覆盖增益核验。

GAP105 qualifier v4父侧39项测试PASS，但实际离线collect在
标量读回核验中拒绝`Unknown scalar read encoding`。失败sidecar
`gap105-native-qualifier-v4-ready-20261006-01`保留，尚未准入。
需准确核对实际压缩读指令，不允许跳过RVC读回或声称full ISA。
已测191个新增条件点仍仅为诊断数据。

LZC七组runtime准备失败的离线根因是EL字符串被JSON序列化，
native读取因此拒绝header。只修独立检查/准备工具，不改RTL或
冻结产物；60项条件候选尚未应用，不把源代码不可达证明等同
已完成DVE豁免。723项DVE进程已退出，但status仍为RUNNING，
需核查工具终态及保护/reset/reload证据后才能引用新百分比。
