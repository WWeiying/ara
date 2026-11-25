# 本轮执行索引

范围见 `PLAN.md`。七组算子实验仍在推进，下面不是全套完成声明。
源码和结果与旧论文、旧仿真目录分开保存，不覆盖历史数据。

输出根：`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`。

| 输出目录 | 内容 | 当前已确认的状态 |
|---|---|---|
| `operator_soc_20261115_all_01` | 当前全开计算 RTL + Direct-U 四文件门控 | VCS编译通过；旧监视器不包含私有Resident FPU握手 |
| `operator_soc_20261115_activity_02` | 同一生产RTL，加只读计算活动监视器 | 正式主镜像；编译通过 |
| `operator_campaign_20261115_qualification_02` | 主镜像普通RVV、QBS/AKV/RVV交接 | 2/2通过，含独立协议及源/镜像身份检查 |
| `operator_campaign_20261115_calibration_01` | Q4_K投影、Q6_K投影、T137三路径Attention | 已启动3路实际VCS，结果以终态记录为准 |
| `operator_summary_20261115_qualification_03` | 主镜像资格测试汇总 | 已生成；不是性能数据 |
| `operator_summary_20261115_calibration_04` | 首批完成后的自动汇总 | finalizer等待本批服务完成后生成report/ |

## 已完成校准与独立复核

校准三项原始worker结果为Attention PASS、Q4_K/Q6_K检查失败；x32原始worker
为Q4_K检查失败、Q6_K未派发。原始记录均保留，不改写。其数值检查器把量化器
设置`vxrm=1`之后的`VCSR=2`错误要求为0；独立后继检查只订正此项。CSR谱系
检查随后识别出原解码将`vmv1r.v`误认成`vsmul`，V3使用Spike精确match/mask，
保留对真实饱和运算的拒绝和全部数值/guard/事务条件。

以下三项已通过独立数值、CSR、协议和身份审计，原worker仍显示原始FAIL：

- `operator_audit_20261115_q4_native_vcsr_01`
- `operator_audit_20261115_q6_native_vcsr_01`
- `operator_audit_20261115_q4_x32_vcsr_v3_01`

`operator_audit_20261115_q4_x32_vcsr_01`保留误解码导致的审计FAIL，不参与通过
统计。没有为修正检查器重跑上述仿真。T137额外的活动审计为
`operator_attention_activity_audit_20261115_t137_01`，确认四lane Resident QK/PV
各35,072个语义FMA；没有以busy代替计算活动。

汇总在`operator_summary_20261115_corrected_calibration_05/`，有完整调用分段、
原始指标长表和按激活/行权重哈希形成的配对。Q4_K M1/N64/K2048首次/重复
完整调用分别为RVV 74,437/73,850、QBS 29,702/28,610周期。本表属于校准，
不代表全部形状、模型或正式平衡顺序性能已经完成。

## 已启动主批与顺序后继

`operator_campaign_20261115_main_03`为8项、最多4路，内容为Q6_K x32补跑、
四个真实捕获Attention点、一个小Prefill和两个量化KV调度点。真实Attention
包括Qwen3 KV137/513/1025及Llama-3.2 D64/KV129，带更强RVV调度对照，不能
与前一轮诊断RVV混淆。裸机Resident强制臂仍不是Linux准入证明。

`operator_chain_20261115_formats_04`直接持有后继worker，先等待主批通过，再
执行`operator_campaign_20261115_formats_04`的36项(九格式*M1/M4*两路径)。
任一批新失败停止后续派发，不自动重试。后继与主批不同时占用两组四路。
汇总由后继控制器自动生成，分别在`prerequisite-report/`、`successor-report/`。

九格式输入是同一真实Qwen3 Q4_K源的受控再量化，并非九个原生模型。
五格式RVV为已有x32，另外四格式为新候选并单独标识，不冒称已验证强基线。
每项输出在ROI外逐元素/字节检查，避免大批printf拖慢仿真。

同源结构控制`operator_variants_20261115_01/{loan_off,queue_zero,shared_fma_off}`
均已编译，尚待资格测试与代表点执行。复用/协作、更大Prefill、真实FFN down
及普通RVV共存准备继续进行；七组范围没有缩小为上述主批和格式批。

复用/协作固件已封存为`operator_qbs_reuse_prepare_20261115_release_01`，包含
6个native配置及3个已有x32对照。`operator_chain_20261115_reuse_06`等待格式批
通过后执行9项，仍与前批串接、批内最多4路；不在主批运行时额外启动VCS。
覆盖M4、M8、两次M4和M1/N128的direct/operation/cross-call复用。目标端对
全输出和输入/权重/Q8/packed/guard逐元素或字节检查，打印在ROI外。

三个结构控制的资格批均已准备为
`operator_campaign_20261115_control_{loan_off,queue_zero,shared_fma_off}_qual_05`。
每个含普通RVV smoke与QBS/AKV/RVV交接，目前尚未启动，不能当作已验证的
结构性能消融。原较大Q64 Prefill已编译，但逐值printf太多，未派发；正在
准备保留完整数值检查的紧凑输出后继，避免无意义仿真墙钟开销。

结构控制的顺序准入及性能清单已固定于
`operator_control_sequence_20261115_08/plan.json`：每个开关先通过资格测试，再
执行其性能批；借用/队列各配M4、M8、2xM4，共享FMA配真实T137完整Attention。
这些批次尚未执行，不能与已通过的全开数据混为结构消融结果。

主批首个T137强对照已PASS，独立协议/私有FPU工作均通过。五臂完整调用周期
为普通内存panel4/轮换60,038、原生AKV 41,456、已建立的AKV replay/轮换
38,848、强制Resident 34,811、默认native路由42,196。固定顺序校准单列，
不把replay基线称作普通RVV，也不据此宣称Linux或整模型Resident收益。
已开始准备对称顺序后继，核查顺序偏置后再决定正式性能图准入。

`operator_chain_20261115_balanced_07`已接续复用批，执行已编译的T137对称顺序。
其后`operator_chain_20261115_real_projection_prefill_09`已接入9项：真实Decode
position40 FFN down Q6_K M1/N128/K6144、attn_q与FFN gate Q4_K M1/N64/K2048，
真实四行Prefill FFN down Q6_K M4/N64/K6144，各配已有x32；另有紧凑Q16因果
Prefill。所有投影保持原生GGUF权重字节和完整K，无受控再量化。

Q64后半段Prefill紧凑产物仍因保守时间估计超过三小时而held，不派发空manifest。
正在单独核查真实queries0..63的完整前缀方案：batch仍为64，但各查询可见K
为1..64，可降低工作量，不截短任何查询原本应看到的Key。准备成功之前不称为
生产64-query范围已测。裸机直接SDK调用本身也不证明GGML选择器已被验收。

已完成的主批三项另外形成只读快照
`operator_summary_20261115_main_snapshot_06/`，包括`attention_calls.csv`及
`metrics_long.csv`，逐项重新核验source/image、数值、协议和原artifact哈希。
状态为`CHECKED_CASE_SNAPSHOT_NOT_FINAL_BATCH`，不是整批结束声明；运行中、
未派发或失败项不进入快照。后台链在整批终态后仍会生成正式完整汇总。

普通RVV/专用机制共存已发布为`operator_coexist_prepare_20261115_published_01`，
3个ELF包含52个整数运算场景、12个FP16/32/64 FMA场景和14个交替阶段。
独立SoftFloat/已审核ISA gold、输入/guard/CSR、精确退休与计算工作检查均已
准备；11项host tests通过，不是RTL验收结果。

`operator_chain_20261115_coexist_10`等待真实投影/Prefill批后执行全开共存组。
三个结构控制也分别准备同ELF的`control_{variant}_coexist_10`，仅在该控制的
资格测试通过后才允许运行，再执行性能消融。结构控制worker以全开共存批为
前置，避免它与全开后继队列同时占用两组VCS。顺序交替不等于并发复位、异常
或Linux上下文切换的全部验证；源SEW64 widening至128超出ELEN64，未准备。

64-query经济窗口已准备为
`operator_prefill_prefix64_prepare_20261115_q0_63_01/manifest.json`，使用真实
queries0..63及原gold，逐query完整因果可见K为1..64。ABBA保守估计约87.5分钟，
不是实测；每次native有4130条命令，QK/PV各532,480个有效标量FMA。7项host
tests与交叉编译通过。`operator_chain_20261115_prefill64_12`服务已启动等待，
串接结构控制的最终性能批，尚未实际启动该项VCS，避免并发叉路。

边界组在准备真实M2/M3、N35及完整K2048的软件分段；软件segment=3是存储/
规划契约，不假装硬件K能力只有3块。D256尚不能由现有D128骨架代表，正单独
审核真实Gemma T17、H4、D256的旧分段调度与当前SDK，未作为完成项。

结构控制的单一顺序worker已prepare于
`operator_control_worker_20261115_parent_11`，封存脚本为
`inputs/run_controls_parent.py`。等待全开coexist_10通过，然后逐镜像执行
qual_05 -> coexist_10 -> perf_08，共9个批次，任何失败停止后续；每批直接持有
frozen campaign执行，结束后只收检查通过的数据。目前只做完prepare和语法
检查；三项隔离host故障注入已验证前置失败、阶段失败、owner退出时不继续派发
也不重试。`operator-controls-20261115-11.service`现已直接持有此worker等待
前置批；只读复核继续，尚未声称结构控制的VCS已执行。

尾部边界批`operator_chain_20261115_boundaries_13`也已prepare，等待prefill64_12；
含M2/N35直接尾块、M3/N35按3+3+2保留完整K2048的两项固件。它与prefill64_12
均已按前置owner顺序启动等待服务，尚未派发VCS，不能看到服务active就声称
对应仿真在跑。三个尾部owner的MainPID已核实；全链仍最多一个批次派发四路。

调度只读复核发现P1：旧chain仅检查前置campaign PASS，可能早于其owner汇总
成功放行。prefill64_12/boundaries_13仍在WAITING时已停止服务，未终止对应VCS
(它们尚未启动)。原目录和attempt保留，不重写成PASS；正在准备显式owner成功
且退出门槛的后继helper，完成故障测试后用新目录接回。当前主批VCS不受影响。

主批Q6_K优化x32对照已PASS：实际Decode position40、M1/N64/K2048，首次/
重复完整调用RVV 448,970/448,516、QBS 31,920/30,873周期，配对约14.065/14.528倍。
激活SHA为`f718530b673014fe9720eaa5ccff5e9d29d37882fb17e6a7828cf3b9edfe7ed7`，
行权重SHA为`10d62d15cbed627f546f05a4cdc390355c73caf7576077ad6590f16a00e64cb7`，
两侧均已逐文件核对一致。原生结果引用独立修正审计，不改原失败worker状态。

P1后继已接回：`chain_owner_v2.py`及21项隔离host tests完成，放行要求campaign
PASS、owner最终PASS、原attempt PID退出；systemd可查询时还要求服务成功。
missing unit本身不算通过。控制序列的新gate先等待全开coexist owner完整结束，
再直接持有一份新封存的原顺序worker。旧WAITING owner保留，不重复执行。

新的三个实际等待服务为`operator-controls-20261115-gate-v2-14`、
`operator-chain-20261115-prefill64-owner-v2-14`、
`operator-chain-20261115-boundaries-owner-v2-15`；MainPID已逐项核实。
其输出分别为`operator_control_worker_20261115_gate_v2_14`、
`operator_chain_20261115_prefill64_owner_v2_14`、
`operator_chain_20261115_boundaries_owner_v2_15`。旧prefill64_12/boundaries_13
控制器仍保持受控停止状态，不把旧attempt改为成功；待执行campaign仍使用
未尝试的原prefill64_12/boundaries_13输出，数值输入与ELF未改。

D256已由独立adapter准备为`operator_d256_prepare_20261115_gemma17_bound_02`，
当前SDK archive不改写，真实Gemma D256/H4/KV17/cap256、原mask/scale=1/容差
保持，10项host tests及1024值独立gold检查通过。普通RVV是同调度功能比较臂，
不是最强性能基线；无Resident。`operator_chain_20261115_d256_owner_v2_16`
已启动等待boundaries owner完整通过，尚未派发VCS。

主批两个量化KV已越过首个ROI(约113k周期)，仍在ROI外阶段。静态检查发现每轮
两次全fixture标量FNV及全输出printf，均有较大墙钟成本；保留轨迹出现_ntoa_long，
但轨迹有采集上限，不能据尾部PC断言当前卡死或全部由FNV造成。正在准备独立
紧凑后继并核对实际慢点，不编辑运行中的ELF、不放宽校验、不称为RTL故障。

随后同一Q4运行的commit推进到cycle19,551,101/order12,977,228，PC序列
0x80001c2c(load byte)、1c30(pointer++)、1c32(xor)、1c34(mul)、1c38(branch)，
pointer从0x80030563递增到0x80030567且hash持续变化。冻结ELF反汇编定位到
main内对fixture_begin的FNV循环。该证据证明ROI外串行校验在真实推进，不把
先前printf阶段误判为死循环。后继将保留完整输入逐字节比较，但去除反复
标量FNV依赖链和大量UART，不改算法、ROI或数值容差；暂未替换原运行。

量化后的检查规模核算：fixture总763,904字节，初始一次及4轮各两次，共9次
全量FNV。上述指针循环窗口108字节/795周期，样本约7.36周期/字节；按该样本
估算仅检查约50.6M周期(非整段实测)，远大于4次约113k的ROI。原型运行墙钟
受验证代码主导，不能把其仿真耗时称为算子性能。独立紧凑后继的两份固件正在
封存，完整fixture逐字节向量比较与完整数值检查均在ROI外，不减少测试输入。

紧凑量化KV v2已封存，复用原02 ELF并正确识别压缩入口；8项host tests、每份
3413项pins由父独立复核。`operator_campaign_20261116_quantkv_compact_17`
已实际启动两路，由`operator_slot_probe_20261116_17`直接持有。为不与将来
四路格式批叠加，仅将仍在等待的formats-04派发服务cgroup置为frozen；原两路
VCS未停止。已核实当前镜像实际4个simv，状态均为R。新两项全部通过且收集
完成后自动thaw派发服务；若失败保持暂停派发待分析，不能跳过失败继续跑。
新两项不得将原未完成的量化KV worker改判PASS，最终数据引用各自真实证据。

紧凑量化KV两项已数值/协议/完整输入/CSR/镜像PASS并生成
`operator_slot_probe_20261116_17/report/`，原派发服务已自动thaw。随后在完整
替代证据具备后，受控结束原两路低效FNV验证(PID3317611/3348347)，原main03
保持6PASS+2受控停止及真实INCOMPLETE，未改成8PASS，post pins仍完整核验。

格式批的原WAITING控制器已停止并保留，新的
`operator_chain_20261116_formats_owner_v2_18`用相同服务角色
`operator-chain-20261115-formats-04.service`接续，以紧凑两项最终通过为前置，
仍执行原未尝试的36项formats_04 campaign。后续reuse及其它批次的目标和输入
不变。主算子覆盖证据为原6项PASS加紧凑2项PASS的显式并集，不声称原8项全过。
原6项的正式收集输出为`operator_summary_20261116_original_passed_18/`。

格式派发的v2进程检测在当前宿主机发现不一致：前置服务已退出且/proc/PID
不存在，但`os.kill(pid,0)`返回成功，导致只等待不派发。新封存v3先检查/proc
节点，再保持原服务终态、owner/campaign PASS、pins和不重试条件；22项host
tests通过。替代等待中的v2后，`operator_chain_20261116_formats_owner_v3_19`
已实际进入SUCCESSOR_EXECUTING，formats_04首四项Q2_K/Q3_K/Q4_K/Q5_K M1
native已核实为4个实际simv进程。没有修改RTL、数值或源输入以绕过此宿主机
调度问题。其余尾部同类liveness迁移用新helper/输出，旧封存记录保留。

尾部v3控制器已全部替换并确认active等待：
`operator_control_worker_20261116_gate_v3_20`、
`operator_chain_20261116_prefill64_owner_v3_21`、
`operator_chain_20261116_boundaries_owner_v3_22`、
`operator_chain_20261116_d256_owner_v3_23`。旧v2服务仅在WAITING状态停止，原
child/campaign均未尝试，现有ELF、SDK和case内容不变，没有影响四路格式仿真。

格式已通过项快照为`operator_summary_20261116_formats_snapshot_19`(19项)。
`formats_table.py`生成的`operator_tables_20261116_formats_partial_20`把38次
首次/重复调用分列，并按format/M/N/K/trial及激活、行权重、独立gold三个SHA
完全相同才配对；当前仅2条配对记录，其余不填加速比。新增x32候选单独标记
并保留primary_eligible=False，不借主表掩盖基线成熟度差异。整批终态后使用
同一脚本生成完整表，不将此部分表当最终全部结果。

`operator_summary_20261116_formats_snapshot_21`已核验29项PASS，
`operator_tables_20261116_formats_m1_complete_22`有58次调用和22条配对记录。
九格式M1/N64/K2048均已配齐，首次/重复仍分列；M4尚未全部完成。重复调用
完整ROI加速比：已有x32的Q3_K 13.128、Q4_K 2.586、Q5_K 13.378、Q6_K 14.511、
Q8_0 2.847倍。四个新候选x32单列：Q2_K 4.046、Q4_0 9.362、Q5_0 15.980、
IQ4_NL 12.924倍；不将后四项误作既有强基线，也不混成全九格式主文几何平均数。
这些仍是同一Qwen3源的受控格式转换数据，不是九种原生模型性能闭环。

校准投影保留K2048、N64。Q4_K来自真实Prefill行截片，不能称作Decode；
Q6_K是position40的真实Decode输入。Attention保留D128/GQA2、完整137有效KV、
tile64+64+9。一个ELF运行三模式及重复调用，完整输出、flags、guards和命令
工作均由独立参考检查。新测试侧RVV对照先标诊断，不冒充此前更强的RVV基线。
QBS的既有x32多输出基线正单独编译并做布局审计后加入。

## 查看状态

在主仓库根目录执行一次：

```sh
python3 -B verification/performance/operator_eval_20261115/status.py
```

该命令不派发任务，不循环轮询。它显示各批完成数、逐项状态及正在执行的
实际子进程。详细文件：`status.json`、`runs/<case>/status.json`、
`runs/<case>/result.json`；只有数值和独立协议都通过且身份未漂移才是PASS。

主批服务为`operator-campaign-20261115-main-03.service`；后继服务为
`operator-chain-20261115-formats-04.service`。旧校准服务已结束，其失败保留。
状态命令也展示独立修正审计及后继控制器，`--detail`可展开实际子进程命令。

## 下一批准入

先审核本批正确性、完整调用周期、观测指标及墙钟速率，再放行宽度、格式、
复用和Attention形状扩展。需要新输入/新检查器的项不能仅靠任务名宣称已排队。
派生长KV重复数据只作结构验证，主论文长上下文曲线另取真实捕获。
QBS协作必须配同源开关镜像及等工作量2xM4，不由全开结果推断贡献。
实际GGML调用、完整模型、Linux租约和板卡测时与本SDK/RTL切片分层报告。
