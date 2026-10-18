# 面积与收益证据补充

本轮目标为“降低面积，保住收益，有些收益证据补齐”。已有五项精简配置及旧综合输入保持冻结，本轮新增候选默认关闭。面积结论需以匹配综合为准，仿真周期不等于执行时间或 Fmax。

## 精确后端的可归因测量

新增 `apps/perf_exact_backend_tradeoff/main.c`：FP16/FP32，VL=1/4/8/32/128/256，稠密/交替/全无效 Mask，独立源版本与原地 Seed 链，共 72 个窗口，每窗口 16 条规约。使用 LMUL=8 以覆盖最大 VL，源 v8-v15、Mask 构造暂存 v24-v31 不重叠；Seed/规约目的只使用对应寄存器的首元素。所有输入为 1、2 或零，所测结果在两种格式上都能精确表示，独立整数位编码模型检查结果和 fflags=0。独立源流交替重写源寄存器，防止重复结果复用冒充累加吞吐；它包含源写入开销。计时结束前标量读出最后结果，确保最后一项规约确实完成。

三种同源同 ELF 配置由 `run_exact_backend_tradeoff.py` 冻结：full；banked（只关闭指数分段）；exact_off（关闭整条 exact 家族及其依赖控制）。full/exact_off 测到的是精确表示、通信、收尾及重叠的整体效果，不能单独算作累加器收益。full/banked 则用于确认分段表示是否保持周期并减少资源。原有 cancellation 数值探针规定了精确结果，不能直接用来要求另一条合法无序树得到同一结果，因此本测试采用两条路径均精确的输入。

v1 前两项首次 vmset.m 时 v0 未初始化，full 和 banked 均出现零结果；保留 `exact_backend_tradeoff_v1/benchmark_v1.c`、ELF、日志和终止记录。v2 先初始化 Mask 输入，再设置 Seed，未修改期望结果。驱动同时修正为编译前冻结共享 ELF，并通过 `run_reduction_audit.py --elf-dir` 提供同一份输入，避免后启动配置读到新 ELF。`collect_exact_backend_tradeoff.py` 要求三侧完整结束、72 个唯一窗口、指定坐标全集、源码/头文件/模拟器/ELF 哈希匹配及实际日志通过，再生成收益报告。

当前 `exact_backend_tradeoff_v2` driver PID 2767621，运行中；已观察窗口不能代替全部 72 项。尚无最终 exact-family 收益结论。

## 标量规约缓存的根 Lane 特化

新增参数 `RootOnlyReductionCache`、宏 `ARA_RED_ROOT_ONLY_RESULT_CACHE`、Makefile `reduction_root_only_result_cache=1`，默认关闭，要求 chain bypass。operand_requester 新增 Lane ID 输入，lane 将实际 ID 接入。候选仅使非根 Lane 的两项标量规约 victim cache 状态保持零；正常 VRF、近期 MFPU/SLDU 结果和实时转发保持原有功能。这是减少缓存部署范围的候选，不删依赖或版本检查，也不假设普通向量结果只存在 Lane 0。非根 Lane 若原本有可命中 victim 的请求，应通过正常路径获得数据，其性能代价必须测量。

潜在裁剪包括缓存数据/版本/地址/字节有效/年龄、替换逻辑、九个消费者对两项缓存的匹配，以及共享转发存储中相应未使用来源；最终是否裁剪和实际面积变化尚未综合证明。仿真断言要求非根 cache 始终无有效项。

`root_only_cache_soc_v1` driver PID 2770342，与现有五项精简全开配置对照，仅新增根缓存开关不同；两侧采用当前相同 requester/lane 源码。10 项定向程序覆盖短流、Mask、Load/Slide Seed、别名、Seed、浮点组、整数 Seed hazard、epoch zero 和寄存器组矩阵。保留参考宏选项由 `run_exact_area_soc.py --preserve-reference-flags` 支持，指定套件由 `--app` 支持。配置仍在验证，未宣称面积降低或全面回归完成。

下一步：收齐两类测试，检查 full/exact_off 的合法数值路径；根缓存候选通过后再补完整规约与混合回归及局部面积对照。若出现周期退化或面积不降，则调整/淘汰该候选，不以理论寄存器位数作收益证明。

## 后续验证进展

分段/非分段表示的两侧已经各自完整通过 72 个窗口，坐标集合、ELF、实际日志均核对，所有周期逐项相同。记录为 `exact_backend_tradeoff_v2/representation_cycle_check.json`，明确只完成两组表示对照，第三组 exact_off 尚未结束。新增局部表示消融 `run_exact_area_ppa.py --block accumulator --accumulator-mechanism representation`：同一当前模块、相同 normalize/collision/seed/输出策略，只改变 ExponentSegmented=0/1，`exact_representation_ppa_v1` 已启动（driver PID 2779959）。它与 72 窗口共同回答“分段是否在保持周期的同时降低硬件成本”，不把整条 exact 家族加速归给分段状态数组。

时序环诊断：主整机仍在 REPORT，寄存器间报告只有表头。独立 Verilator 检查 v1 遇到未使用 nonblocking cache 的 BYTE_WIDTH 参数问题，v2 删除该未使用备选模块后遇到原有 enum 零值聚合初始化的严格诊断；v3 仅为获取 SCC 路径允许该初始化，保留各版失败，均不是完整 lint 验收或 ISA 证明。117 个 UNOPTFLAT 告警中实际 example path 涉及共享 ADD 的有三项，压缩摘要存入 `reduction_loop_lint_v3/shared_loop_summary.json`。

私有 v4 把 shared_ordered_adder 的仲裁、请求 payload 和 return ready 分开为独立组合关系，原 RTL 未改、旧综合未改。部分路径改变，但共享路径仍有三项告警；不能把拆块当作已经消除真实环路，也不能将向量/always-block 粒度的 SCC 全认定为位级物理环。仍需核查条件、字段和映射后网表。

新审查方向（尚未实现）：`red_stream_compatible()` 已要求前后均不走 RCE。当前完整配置的 FP16/FP32无序求和走 exact，浮点 min/max 走 RCE，宽化输入在 VMFPU 中已转换 SEW；旧 background tree 的兼容性因此可能只剩非合法格式或 global_vl/local_vl 不一致的抽象组合。需要先证明合法格式、VL=0 与所有回退路由，再考虑静态裁剪 VMFPU 旧后台 root FIFO、后台结果与进度寄存器。前台 Lane-local 的 RedContext 数据仍可能承担实际计算，不能一并删除。

根缓存定向对照已结束，两侧各 10/10 PASS，四个性能程序的 10 个窗口完全相同。原 driver 的最终比较默认要求至少五个性能程序，因此报告步骤失败；显式 `--min-performance-apps 4` 对冻结完整套件重新核对通过。没有跳过功能失败，也没有修改窗口或期望。后续 driver 已提供显式最低性能程序数选项并记录配置，默认仍为五项。

扩大回归 `root_only_cache_full_v1` 已启动，两侧 driver PID 2775864/2775865，共 34 项，包括原 29 项、72 窗口新探针和队列打包/随机依赖/所有权/LMUL 矩阵。复用已通过定向测试的同一对冻结 simulator，逐源码与 executable 哈希检查后启动，无重新编译或修改旧快照。

局部面积入口 `run_requester_cache_ppa.py` 采用实际 Lane 的 request/queue typedef、10-bit 字节地址及所有 requester 顶层功能接口，只有 Lane ID 和 RootCache 常量化。三组为 Lane0/原缓存、Lane1/原缓存、Lane1/关闭 victim cache；相同标准单元库、1ns/.15ns uncertainty、相同驱动/负载，禁止寄存器复制/合并，串行运行。所有接口保留，不能把未连接测试平台造成的裁剪当真实收益；也不能将局部差额直接等同于整机面积下降。

准备封装的第一次 VCS 检查缺省 timescale，保留失败日志；补入与 SoC 相同的 `-timescale=1ns/100fs` 后编译成功，未改 RTL 算法。实际局部综合 `requester_root_cache_ppa_v1` 已启动，driver PID 2776211，面积和时序仍待结果。现有整机综合/串行队列保持原冻结输入。

## 最新证据与尚未通过的部分（2026-10-14）

本节更新前述运行中记录。根缓存完整对照 `root_only_cache_full_v1` 两侧均 COMPLETE，34/34 功能通过，共93个性能窗口逐项周期相同，仿真结束时间也相同。比较器检查共同输入集、ELF与模拟器哈希、终态及实际日志，不仅查看 manifest 的 PASS 字段。`comparison.json` 和 `verified_comparison.log` 保留检查结果。这些证据支持已覆盖场景中关闭非根 victim cache 不损失吞吐，不能推导所有工作负载均无退化。

`requester_root_cache_ppa_v1` 三组局部综合完成：根 Lane 原缓存与非根原缓存均18865.055789 μm²，非根精简16053.575806 μm²，下降14.9031%。三个非根的局部差额合计8434.439949 μm²，仍不是整机面积证明。报告最差 setup slack 分别+0.000078 ns和+0.000206 ns；但 QoR 的 hold 违例分别为−0.10 ns／1577条和−0.11 ns／1227条，不能宣称时序闭合或精简使所有时序改善。

新增 `ARA_RED_PRUNE_LEGACY_FP_STREAM` 候选，默认关闭。仅在4 Lane、HalfSingleDouble、exact sum/global/FP16和RCE min/max/direct完整配置中裁剪旧树形规约后台状态，保留前台累加上下文、普通 FPU、ordered 和 RCE 移交。静态使旧后台 root FIFO、部分结果和进度等寄存器保持零。断言独立使用原始、未裁剪的兼容条件检查不存在应进入该后台路径的前后指令对，避免以禁用后的条件进行自证。`prune_fp_stream_soc_v1` 两侧12/12通过，六个周期窗口相同；局部面积证据尚缺。`prune_fp_stream_full_v1` 扩大为35项，复用前一轮同一对冻结模拟器，检查所有源码和模拟器哈希，启动前冻结共同ELF，仍在运行。

`exact_backend_tradeoff_v2` 三侧已经结束，full和banked各72窗口通过且周期相同，exact_off失败。保留完整失败日志和 `failure_audit.json`，不生成三侧收益结论。FP16、VL256、dense、16条原地Seed链的最终4096虽然可表示，但中间值超过2048时传统无序树可合法舍入，因此原用例不能要求两条树均结果精确且flags为零。FP32非空Seed链返回单次规约值而非16倍，不能用合法舍入解释；同时查明关闭组保留了要求exact_global的CHAIN_BYPASS，构建配置违反现有Make依赖。必须先对合法关闭配置复测，再判断是否存在实际RTL错误。

v3关闭组同时关闭exact家族及依赖的chain bypass、shared capture、root cache和legacy FP pruning，保留其他仍适用的RCE能力与寄存器版本检查。FP16最大dense链改为明确标注的两个8条Seed链，计时仍执行16条规约，最终期望值由该新指令序列独立计算为2048；其余Seed链期望仍为16倍，不以失败输出修改期望。日志新增chain_span字段，收集器核对每个坐标的预定链长度。共同新ELF和源码已冻结到 `exact_backend_tradeoff_v3`，三组重新启动；旧v2失败记录不改。banked是直接RTL表示诊断，关闭segmented时不满足生产Make的global依赖限制，不能作为已支持的生产构建配置推荐；其周期对照只用于表示研究，还需局部面积和时序证据。

## VMFPU 裁剪面积对照入口

新增 `run_vmfpu_stream_ppa.py`，从实际 Lane 提取完整 `vfu_operation_t`，采用10-bit字节地址、4 Lane、VLEN1024及HalfSingleDouble配置。Lane ID和全部功能接口保持动态，包括RCE及共享有序ADD的请求和响应，不以端口悬空或绑零裁掉功能。共享ADD本体位于本次测量边界之外，两侧相同。参考输入为冻结五项精简版，替换为同一当前VMFPU源码；两侧仅相差 `ARA_RED_PRUNE_LEGACY_FP_STREAM=1`，综合约束、库、寄存器复制与合并选项相同。输出同时保留setup、hold与check_timing，不以面积下降宣称Fmax不降。

初次封装 `vmfpu_stream_ppa_prepare_v1` 编译失败：VMFPU缺省将cva6_user_cfg直接赋给完整cva6_cfg，导致serdiv的TRANS_ID_BITS无效。失败保留。v2封装从冻结ara_soc提取实际gen_usr_cva6_config函数，采用整机同值配置常量，经build_config构造完整配置并显式传入VMFPU；没有修改RTL除法器或缩窄其位宽。`vmfpu_stream_ppa_prepare_v2` VCS顶层编译成功。实际串行局部综合 `vmfpu_stream_ppa_v1` 已启动，driver PID2809182。新增收集器 `collect_vmfpu_stream_ppa.py` 核查冻结源/库/日志哈希、相同约束和唯一开关差异，只有两侧工具完整成功且setup/hold均有实际路径时才出具面积差额。

进一步复用候选尚未实现：最新整机映射报告中的RCE独立FP64加法器面积6536.712 μm²，共享有序ADD内部FP64 slice面积11851.224 μm²。二者确有功能交集，但流水级、返还协议、并发需求不同。直接共享的潜在毛节省上限仅约6537 μm²（还须减新增仲裁/标签成本），不能把RCE全部35956 μm²都算作可移除加法器。应先补RCE FP64与ordered同时活跃的profiling和混合用例；目前不修改其独立实例，也不宣称共享不损失周期。

## 八段精确表示候选：实现与初步验证

新增累加器参数 `CompactSegments`、宏 `ARA_RED_COMPACT_EXACT_SEGMENTS`、构建选项 `reduction_compact_exact_segments=1`，默认关闭，要求指数分段开启。原16个16-bit窗口、每项49-bit有符号bin，改为8个32-bit窗口、每项65-bit bin。有限输入仍转换成以2^-149为单位的精确整数，再依指数选择窗口；FP32最多257项的位宽依据为24-bit有效数、最多31-bit窗口内位移、9-bit人口进位余量和符号，共65位。FP16在同一固定点域上使用对应绝对位移，较小有效数也满足该余量。

每次归一化仍完成两个64-bit chunk，第一次产生低128位及有符号carry，第二次产生高128位与最终carry。每个chunk从四个16-bit bin变为两个32-bit bin；最大中间计算宽度仍为98位。数字在原bin中就地覆盖，bin0高33位暂存半程carry，最后一个bin高位保存顶端32位及符号。最终exact_value仍为288位，状态传输、seed/special元数据、最终舍入和valid/ready接口均未改变，没有新增归一化周期。有限状态数组784→520位（下降33.7%）只是结构位数，反馈加法器49→65位，实际面积和关键路径必须测量，不能按位数宣布芯片节省。

`exact_compact_segments_unit_v1` 首次编译失败，原因是函数参数名bins为SV保留字，记录保留；修正为chunk_bins。v2随后通过300条随机/定向指令、12种合法接口配置、每配置8种更新/归一化组合的逐周期对照，以及900组独立整数模型的FP16/FP32/宽化及普通/late seed检查。与旧模块比较时，仅在双方out_valid都为0时忽略exact_value内容：接口原本只在out_valid时定义规范化精确payload；累加中的就地编码不同不必相同。ready、valid、busy、结果、flags与其余元数据仍每周期比较，所有有效精确payload及其背压保持期间逐位比较，未删除握手或提前输出检查。

v3增加长流负值和正负抵消；v4对所有长流额外使用独立288-bit公式：0x107fffff的固定点整数为0xffffff×2^31，256源元素及是否插入seed分别计算，负数取相反数、交替流源和为0。v3、v4累加对照均通过。未开启compact的 `exact_compact_fallback_unit_v1` 对旧模块完整逐周期比较也通过，证明这次通用化没有在已覆盖路径中改变回退接口行为。以上均为单元证据，尚非整机吞吐和完整ISA证明。

`exact_compact_segments_soc_v1` 在五项精简、根缓存及FP旧后台裁剪同时开启的配置上做35项整机对照，两侧仅相差compact宏。启动前冻结共同ELF，构建文件列表核对无其他宏差异；正在运行。`exact_compact_segments_ppa_v1` 在相同源码/库/约束下仅改变CompactSegments=0/1，正在串行局部综合。新增收集器对segments和representation分别只容许目标参数变化，不能将其他开关差异混入消融。旧整机和各已启动消融输入保持冻结，不受后续源码及注释更改影响。

## 分段表示的面积证据已完成

`exact_representation_ppa_v1` 两组局部综合均完整成功，collector核对同源码、相同约束和库、仅ExponentSegmented参数变化。四个宽bank模式面积41098.511838 μm²，16段模式11565.455878 μm²，下降71.8592%，顺序单元1214→846。最差报告setup slack −0.139097→+0.000094 ns，setup违例601→0；hold仍有违例，分别−0.11 ns／1321条与−0.10 ns／729条。因此只能说局部setup检查改善，不能说所有时序闭合或SoC Fmax提高。

`joint_evidence.json` 核对该PPA累加器源码哈希与 `exact_backend_tradeoff_v2` 的冻结源码一致，连接已有72窗口full/banked周期完全相同的证据。该结论为“16段表示相对四个宽bank，在已测窗口中保留周期且降低局部面积”。这是已有分段机制的成本收益证明，不是本轮新增8段候选的收益，也不是相对原版Ara的整机节省。直接将局部29533 μm²差额乘4加到SoC报告中不成立，嵌入时的边界、约束、扇出和映射优化可能不同。

## FP64收尾与有序计算的容量探针

新增 `perf_rce_ordered_capacity`，SEW64、VL1/4/8/16，每窗口32对无序规约与有序规约。无序结果交替写v8/v12/v14/v18，有序结果v10又作下一条有序规约的seed，避免重复结果缓存替代实际加法。源均为精确的1，seed为3和5，检查四个无序结果等于VL+3、有序最终结果等于32×VL+5、实际VL及fflags=0；计时结束前读出全部最终结果。它是资源容量探针，不代表应用平均收益。

新增只读 `completion_capacity_profile.sv`，bind Ara，同时记录现有共享ordered请求/接受、RCE FP64请求/接受、同周期请求及ordered在RCE FP_WAIT期间的需求；不驱动设计端口，不更改硬件。`completion_capacity_profile_v1` 复用已冻结五项精简＋根缓存＋FP后台裁剪源码，冻结新ELF及observer，VCS编译已通过，仿真运行中。收集器检查完整功能日志、四个窗口、源/模拟器/ELF哈希，并将每周期事件累加结果与最终counter摘要互相核对；request占用周期不等同于接受次数。只有看到这些证据，才能评估是否值得建立共享RCE/ordered加法器候选；本探针没有实现共享，更不能给出共享后的性能结论。

该探针随后完整结束并通过collector，四窗口周期分别470、845、1293、2029；ordered请求及接受均928次，RCE请求及接受均288次。同周期双侧请求为0，ordered请求出现在RCE FP_WAIT期间的周期也为0。现有两套加法器在这些序列中未观察到计算需求重叠，说明共享值得进一步验证，但不证明全部合法混合流互斥。尤其还需覆盖跨格式有序规约、FP64 late seed、MASK与背压、前后类别顺序，核查当前资源释放条件是否结构性排斥ordered，及共享返回延迟变化是否影响其他路径。暂不改变两套硬件实例。

## 八段表示面积结果与FP后台完整回归

`exact_compact_segments_ppa_v1` 两侧完整成功。相同当前源码、约束与库，CompactSegments=0面积11622.911888 μm²，=1面积10442.375925 μm²，减少1180.535963 μm²（10.1570%）。最差报告setup slack分别+0.000076 ns、+0.000261 ns，均无setup违例；hold仍分别−0.08 ns、−0.10 ns，不能称时序闭合。16段参考与上一组11565 μm²的差别来自这轮同源通用化和重新映射，八段收益必须使用本轮11623→10442配对，不能跨轮取更有利数字。整机嵌入差额尚未证明。

`prune_fp_stream_full_v1` 两侧35/35全部COMPLETE/PASS，比较器检查93个性能窗口及全部仿真结束时间，均逐项相同。测试输入包含修正后的72窗口新探针，ELF固定且每侧相同。最长的tail程序持续执行标量检查与向量指令，检查到其进程和指令trace实际推进，未因等待时间较长重启或替换程序。FP旧后台裁剪的功能/周期证据已完成该套件，局部VMFPU面积综合仍在运行，候选默认关闭。

## RCE与有序规约共享加法器候选

新增 `reduction_shared_rce_add`／`ARA_RED_SHARED_RCE_ADD`，默认关闭，要求现有shared ordered ADD和RCE FP64 sum。shared_ordered_adder增加NrClients参数，默认仍为4个Lane；候选增加第五个RCE客户端，标签带客户端归属及原始9-bit标签。四Lane、一或两单元、每单元最多一条未返回请求的规则保持；五客户端采用有界轮转，输出背压时锁住归属。RCE通过UseSharedFp64Add选择中央后端，其私有FP64 FMA在候选中不实例化，普通Lane bulk VMFPU维持原有路径。

RCE请求将现有两个合并操作数、rounding mode及指令ID送入共享FP64 ADD，返回原数值与fflags，仍由RCE原MERGE／FP_WAIT／SEED状态机推进。共享后端有一层AFTER输出寄存器，原私有后端为两层；反馈请求若未获仲裁，沿已有回退路径保存结果后在MERGE或SEED重试，不允许丢失旧响应或改变合并顺序。新增完整返回标签检查，既有RCE owner断言及共享单元输入/输出背压稳定性断言保持启用。局部计算完成、算术返回与架构指令完成仍分别管理。

`shared_completion_unit_v1` 四种6000-cycle压力组合全部通过：4或5客户端，各配1或2单元；复位后检查结果分别1423、2739、1372、2780条。测试包含跨格式随机数据、NaN/Inf/零、舍入模式、标签、输出停顿和复位。它证明仲裁/返回协议，不单独证明RCE状态机适配。

随后 `shared_completion_oracle_v2` 用独立Python FP64整数模型检查1200条RCE指令，两个上下文、随机Lane到达、错误seed ID/寄存器/版本、32周期结果背压，同时四个外部客户端持续竞争。全部通过，RCE请求被阻塞9395周期、存在竞争11857周期，错误seed三种各390次。v3改为竞争/安静交替，开启已有可选seed feedback，换随机种子并施加64周期结果背压，另外1200条通过；覆盖5903个阻塞周期、6689个竞争周期、443次被接受的普通反馈、277次seed反馈。保留v1 runner因冻结包文件路径识别失败的记录；修正为按ara_pkg.sv唯一文件名定位后才运行v2/v3，没有修改数值期望或忽略断言。

`shared_completion_soc_v1` 两侧20/20全部通过，所有测量窗口及结束时间无退化。FP64规约＋普通浮点混合974→940周期；容量探针470/845/1293/2029→470/749/1197/1933；FP late seed四窗口529/528/529/667→529/528/529/663；ordered FP32、宽化ordered、masked ordered、e64短流等已测窗口不变。相同ELF、相同外设和计时区间，仅共享开关不同，属于周期证据，不等同于执行时间或Fmax。

`shared_completion_full_v1` 再扩大到44项，合并8段表示、根缓存、FP后台裁剪及此前五项精简，两侧只改变共享宏，文件列表已核对，正在运行。`shared_completion_ppa_v1` 对RCE＋中央ordered后端整体做相同接口、约束、库的局部对照，所有功能输入保持动态；只改变Shared=0/1，正在串行综合。封装先编译私有/共享两种实例成功；初次编译检查有工作目录路径错误，日志保留，修正测试文件路径后完成检查。实际毛节省上限为原私有FP64加法器6537 μm²，须减第五客户端与路由开销，以配对报告为准。

## 精确机制的三组完整收益消融

`exact_backend_tradeoff_v3` 的full、banked、exact_off均COMPLETE，各72窗口全部通过。collector再次检查源、模拟器、ELF及实际日志，结果保存在comparison.json。full/banked的72窗口周期逐项相同。full相对合法exact_off，FP16独立源流周期减少30.08%–45.78%，FP16 Seed链53.40%–72.49%；FP32独立流23.53%–48.12%，FP32 Seed链44.54%–73.15%。各组18窗口，均有改善，没有以剔除慢例得出范围。范围不代表应用平均收益；独立流包含源寄存器重写，链流包含真实Seed依赖，且FP16最大dense用例明确是两个8条链。

例如VL256、dense：FP16独立1064→744、两个8条Seed链940→438；FP32独立1496→1144、16条Seed链1223→676。全组采用同一ELF和测量区间，读出最终结果后才结束计时，并检查结果和fflags。exact_off还关闭依赖的chain bypass与shared capture，故full/off是精确累加、通信、收尾及依赖后移的整体收益，不应归给分段算术单项。v2的FP32链失败在合法关闭配置复测中没有重现，旧错误构建与失败日志仍保留。

## 有序请求Mask与Ready解耦候选

旧五项精简整机的实际timing_max路径从共享后端FP32输出valid寄存器走到FP64输出status寄存器，报告arrival约3.013ns，并有TIM/OPT自动切环记录。源码进一步核实：ordered请求mask取vfpu_simd_mask[0]，该值来自issue_be，而ordered分支仅在vfpu_in_ready时设置issue_be，形成ready→mask→共享请求/后端控制的反馈关系。该发现是具体源码/映射路径证据，尚不能据此宣称其为所有时序问题的唯一原因；大向量always块也可能产生保守SCC。

新增 `reduction_ordered_ready_independent_mask`／`ARA_RED_ORDERED_READY_INDEPENDENT_MASK`，默认关闭，要求共享有序后端。候选仅将标量ordered请求mask按vinsn_issue_q.vm或mask_i[0]生成：源元素已经抽取到低元素，原接受操作的be(1,SEW)低位恒为1，消费计数与队列推进仍由原valid/ready控制。新增断言在每次真实接受时逐位检查与原vfpu_simd_mask[0]一致，未删除Mask或异常语义检查，也未增加流水级或时序例外。`ordered_mask_decouple_soc_v1` 在已有组合上做12项同ELF对照，正在编译/运行。尚未有周期或时序改善结论。

新增 `collect_shared_completion_ppa.py` 对共同filelist、唯一Shared参数差异、库/源哈希、setup/hold、check_design前后报告及工具终态进行核查，等待两侧综合完成。run_exact_area_soc进一步在准备前验证参考source_manifest中每个源文件哈希，确保复用的是封存输入。

## 本轮收齐的回归及诊断

`exact_compact_segments_soc_v1` 两侧已完整结束，35/35全部通过。严格比较器再次核对93个性能窗口，周期逐项相同。结合本轮局部11623→10442 μm²对照，八段表示已有配对功能、周期、局部面积证据；集成面积、频率及hold闭合仍未证明。

`ordered_mask_decouple_soc_v1` 两侧12/12全部通过，10个性能窗口周期相同，新增接受mask等价断言未失败。该改动在已覆盖有序FP16/32/64、宽化、Mask、边界及组合场景中未改变被接受操作或周期。`ordered_mask_loop_diagnostic_v1` 为同一组合的两侧结构诊断，使用冻结综合依赖、相同当前模块、仅mask宏变化；兼容处理与先前诊断一致，双方均无Verilator错误，但UNOPTFLAT数量仍各116。因此不能宣称该改动已消除整机组合环或修复时序，必须继续用映射后的实际路径判断；向量/always块粒度的SCC统计也不能直接当物理环数量。

## Requester算术队列转发候选（尚未验证完成）

新增参数ArithmeticOnlyForwarding、宏ARA_RED_ARITHMETIC_ONLY_FORWARD、构建选项reduction_arithmetic_only_forward，默认关闭，要求chain bypass。候选保留AluA/AluB/MulFPUA/MulFPUB/MulFPUC五个队列的实时、近期及victim数据转发；MaskB、MaskM、StA、SlideAddrGenA通过原有hazard检查和VRF读口取数。只在四个队列静态关闭转发候选、匹配与响应选择，普通指令和全部队列仍可执行，RAW/WAR/WAW处理不变。共享捕获模式中这些队列的无效转发payload明确置零，valid始终不产生；有效payload和算术消费者路径保持原协议。

这是可能增加等待的面积折中，不宣称周期必然不变。还可能因victim消费/替换时机变化影响后续命中，必须以混合序列测量。arithmetic_forward_soc_v1的18项配对对照覆盖Load/Store、Mask、Slide、Seed及普通/规约混合，输入ELF在编译前冻结，正在运行。requester_arithmetic_ppa_v1对根Lane和非根Lane分别成对比较，双方都保持root-cache精简开启，只改变ArithmeticOnly=0/1，所有其他接口保持动态，串行局部综合正在运行。旧三组root-cache PPA的封存脚本未修改；新runner追加显式参数及独立模式，不用跨Lane或跨轮报告推导收益。

Requester候选定向序列中已观察到性能折中：容量探针VL1窗口470→473周期（+0.638%），其余三个窗口相同；已完成的Load/Slide Seed、规约后Slide窗口也相同。该记录是当前部分窗口，不是完整18项结论。严格比较器若报告周期退化将保留原结果，不修改测试期望或将退化标记为零；最终需结合完整性能分布和局部面积决定是否保留。新增collect_requester_arithmetic_ppa分别核查根/非根两对，要求只改变ArithmeticOnly参数，保留setup与QoR hold信息。

## 转发等价检查的四态误报定位与修正

arithmetic_forward_soc_v1 两侧18项均完成，候选侧18项通过，基线侧perf_rvv_memory_coverage触发a_shared_forward_payload，其余17项通过。虽然该程序最后tohost=0，审计器正确保留断言失败，不能当作功能通过；也不能因候选不转发MaskB而将此现象算作修复了数据通路。原日志及失败manifest均保留。

forward_payload_diagnostic_v1只扩充错误文本、未改断言条件或数据逻辑；v2进一步用$sampled读取断言真正的采样值，排除NBA更新后valid已清零造成的观察混淆。实测采样valid=1、source=4，shared与原始响应均为xxxxxxxxxxxxxx01，case_equal=1、logical_equal=x。部分写入/未知尾字节使逻辑==得到X，SVA将其视为失败。另在实际抽取的捕获模块中注入未知尾字节，旧断言复现失败，而独立!==逐位检查完整6000周期通过，说明该例为等价检查误报，并非观测到载荷差异。

因此仅将仿真等价断言的==改为===：仍比较全部64位，未知位置也须与原响应逐位一致，没有屏蔽字节、去掉断言或改变ISA期望。shared_forward_x_fixed_v1在6000周期、五种来源、多消费者广播、替换和复位下通过。负向测试shared_forward_x_negative_v2故意翻转已知位，允许下一采样沿同时验证嵌入断言，确实触发a_shared_forward_payload错误，NEGATIVE_CONTROL_COMPLETED标记及negative_control_detected=true保留。v1负向测试因直接检查器提前$fatal、未留到嵌入断言采样而未满足覆盖门槛，该失败也保留，v2才补全两层检查。

forward_payload_assertion_audit_v2使用冻结PPA相同宏进行SYNTHESIS预处理，去掉文件/行指令、空行及行尾空白后，两份源文本哈希完全一致，证明修正没有改变可综合硬件。v1原始文本比较仅因三行注释空白不同失败，文件保留。arithmetic_forward_soc_v2以相同冻结ELF重跑两侧18项，双方采用修正后的同一断言，仍仅改变转发范围宏；测试期望、Mask/Store/Slide场景与严格性能比较均不变。该组仍在运行，旧v1失败不会被重新分类为PASS。

新增collect_area_candidate_status.py及reduction_area_candidate_status.json，索引功能、周期、局部面积、未完成证据，保留functional_failure与cycle regression的区别。索引不替代单项严格收集器，也不宣称待完成任务仍活跃；进程活跃性另以实际进程检查为准。

## Requester重跑完整结果与根Lane局部面积

arithmetic_forward_soc_v2两侧18/18均COMPLETE且功能通过，包括先前误报的perf_rvv_memory_coverage。严格零退化比较仍失败，已保留比较JSON和driver异常：容量探针VL1为470→473周期（+0.6383%），memory coverage为390→392（+0.5128%），其余有计时的窗口相同。功能通过不等同于零性能代价；未修改比较器阈值、期望或原v1失败记录。

requester_arithmetic_ppa_v1根Lane两组已完整成功，仅ArithmeticOnly=0/1不同；root_pair_evidence.json明确标记partial。面积19132.007749→17122.055812 μm²，减少2009.951937 μm²（10.5057%），最差报告setup slack +0.000189→+0.000010 ns，均为正但余量很小；QoR hold两侧均约−0.11 ns，违例1602→1498。非根两组尚未完成，不能据此乘4或推导整机节省。

当前统一索引以修正断言后的v2为Requester主对照，同时retained_failures中继续保存v1基线功能失败；strict_no_regression=false及最坏窗口代价被单列，不将基本不变的工程判断写成零退化。

只读mapped_feedback_inspection_v1首次检索部分单元失败，查明mapped_checkpoint写出在change_names之前；旧报告使用规范化后的层级名。对照实际脚本和Missing mapped inspection cells错误后，仅停止该诊断实例并保留superseded_audit，原综合及其队列不受改动。v2读同一checkpoint后执行原报告阶段同样的名称规范化，已通过五单元检索，report_cell触发了全图更新和原有OPT-150/314反馈诊断；连接导出仍在运行。该动作仅作诊断，既不编译新RTL，也不添加时序例外，不能被当作时序修复证据。

shared_completion_full_v1随后两侧44/44全部COMPLETE/PASS，严格比较101个性能窗口无退化，包含五项精简、根缓存、FP后台裁剪及八段表示的组合。两侧只改变RCE共享开关，原冻结输入未变；这一组合功能/周期证据已收齐，面积及集成时序仍待测量。

## 归并发射的 ready 反馈控制精简

映射连接导出 mapped_feedback_inspection_v2 已完整完成，completion_audit.json 核对原五项精简整机 checkpoint 哈希、工具完整结束标记及输出哈希。仅规范实例名称后导出连接和 Verilog，没有重新优化、修改原综合或加入时序例外。旧 checkpoint 的 Lane 2 路径从 bulk FPU in_ready 经 U16001、U4761、U7213、U3068、U7042、U4570、U6920、U6890、U10858、U6800、U6757、U4388 返回 vfpu_in_valid；这给出了实际门级 ready→valid 反馈的定位依据。该网表尚未包含随后候选，不能据此声称新组合仍有同一环，也不能认为先前 Mask 解耦已修复时序。

新增默认关闭的 reduction_context_issue_cut／ARA_RED_CONTEXT_ISSUE_CUT。前台和旧后台 RED_CTX_MERGE_PAIRS 均将第二对与根节点选择显式写为互斥分支，根节点依据 red_context_pair_issue_q 判定，不再读取本拍 ready 更新的 pair_issue_d。如果第二对在本拍被接受，pending[1] 同时置位，根节点必然不可发射；如果第二对未被接受，pair_issue_d 仍为1，根节点同样不可发射。因此该改写没有有意新增等待拍，返回数据的同拍旁路也保留。context_issue_guard_audit_v1 穷举2-bit阶段进度、4个valid、2个pending和ready的512种二态组合，原/新根选择相同且不能与第二对同时选择。这只证明选择谓词，不等于完整RTL形式验证。

context_issue_cut_soc_v1 对当前共享收尾、八段累加、根缓存、旧FP后台裁剪及独立Mask组合启动18项相同ELF配对验证，两侧仅改变新开关；context_issue_loop_diagnostic_v1 另外启动同源结构SCC对照。功能、周期和物理时序尚待收集，不能提前称候选通过或环路消失。旧综合队列、冻结输入和已停止的两项任务均未改变。

## 最新整机面积归因与控制诊断收集

重新使用实际 area.rpt 生成 reduction_area_increment_shared1_audit.json，记录历史基线和五项精简整机报告哈希；审计器新增对共享有序加法器的独立分类，并核查不相交类别之和等于 Ara 增量，避免将它混入残差或与 Lane 子模块重复计算。Ara 915540.9599→1194041.4462 μm²，整机2928017.2042→3220930.4104 μm²。仍是历史报告观察，不是严格匹配的因果成本，且原五项整机流程尚未完整结束。这些数值不能替代最新候选的集成面积或时序结果。

context_issue_loop_diagnostic_v1 两侧已完整结束，collector检查显式源文件哈希、唯一宏差异、工具返回码和实际日志。双方0错误，各116项UNOPTFLAT，信号集合也完全相同，没有仅因数量相同而漏掉集合变化。该诊断未提供候选消除物理反馈环的证据；整机功能与周期对照仍在运行，候选默认关闭。统一候选索引增加 context_issue_cut 条目，其状态仍按实际配对manifest收集。

## 算术消费者转发的完整局部面积结果

requester_arithmetic_ppa_v1 四种模式均已完整结束，collect_requester_arithmetic_ppa.py 核对冻结源码/参考/库哈希、两对Tcl仅ArithmeticOnly参数不同、工具终态及实际setup/hold报告后生成comparison.json。根Lane为19132.007749→17122.055812 μm²，减少2009.951937 μm²（10.5057%）；非根Lane为16004.855819→14744.183819 μm²，减少1260.672000 μm²（7.8768%）。双方均已启用root-only cache，所以这是在根缓存精简之上的转发范围增量对照，不能拿它与另一轮未精简Requester报告直接相减。不同Lane和整机嵌入的约束/扇出会改变映射，因此不将局部结果乘Lane数当整机节省。

配对setup最差报告slack根Lane +0.000189→+0.000010 ns，非根 +0.000126→+0.000181 ns；根Lane余量降低，不能概括为时序普遍改善。四组QoR hold均约−0.11 ns，违例根1602→1498、非根1225→1166；尚未时序闭合。结合arithmetic_forward_soc_v2双方18项功能全部通过，以及VL1容量+0.6383%、memory coverage+0.5128%的实际周期代价，这一候选有明确局部成本收益，适合作为允许轻微周期损失的面积折中；默认仍关闭，是否进入最终配置须看集成配对及更广混合覆盖，不能改写严格零退化比较失败。

在收齐转发面积后，arithmetic_forward_full_v1 将44项共享收尾组合回归与18项转发/内存定向程序合并去重为50项，重新冻结共同ELF，以同一组合仅切换ArithmeticOnly宏。此轮扩大精确流、Seed、特殊值、背压和混合覆盖，保留严格零退化比较及此前18项已有退化记录；当前仍在运行，不能提前宣称全部机制的收益已保住。

## 整机组合输入已完成匹配准备

context_issue_cut_soc_v1 两侧18/18均COMPLETE/PASS，严格比较15个周期窗口相同；这一结果补全了先前运行中记录，仍不代表物理反馈环已消失。新增area_pair.py复用原流程并封存扩展配置及自身代码，未改变旧flow.py/profiles.json/templates或旧队列。三套area_pair_reference/compact/arithmetic_v1均PREPARED、dc_started=false；audit_area_pair.py核对436个源/头文件内容、390个HDL文件顺序、11个库、同约束/后端脚本及精确宏差异。参考为当前五项精简实现，四项候选为根缓存、FP旧后台裁剪、八段表示和RCE共享；第三套再增加算术转发。有序Mask和归并控制共同开启，不计入面积候选差异。详情见reduction_integrated_area_pair.md。尚未启动这组三套整机综合，不能当作完成面积或时序结果。

## 整机报告查询修正与匹配参考启动

mapped_reg2reg_group_probe_v1 读取同一旧五项映射检查点，无重新综合、约束变更或人为时序例外。以clk_i组查询最坏一条路径，实际起点CP和终点D的所属单元都通过all_registers -edge_triggered集合归属检查；工具约357秒结束，completion_audit核查标记、源检查点/库/输出哈希和实际日志。回放最差slack −2.712196ns，与旧报告−2.157326ns不一致，且仍有原有自动切环；不能据此生成稳定Fmax或宣称性能提高。它仅验证无需原全寄存器 -from/-to 查询即可获得并核实最坏触发器间路径的报告方式。

area_pair.py仅在临时私有模板中替换上述报告查询并用已核实路径填写summary，原flow.py、profiles.json、templates、旧冻结目录和旧串行队列未改动。新v2三套重新冻结，输入审计再次通过436份源/头文件、390 HDL顺序、11库、运行配置及同约束/脚本；v1准备结果保留。仅area_pair_reference_v2已启动后台整机DC（driver PID2951080），启动前MemAvailable约超过80GiB门槛，另外两侧暂保持PREPARED以避免三套整机同时占内存。当前参考阶段ANALYZE，尚无综合结果。

## 最新精简候选启动交接

本轮继续收敛已实现的规约面积精简，选择area_pair_arithmetic_v2启用根缓存特化、旧FP后台裁剪、八段精确表示、共享RCE/ordered ADD和算术消费者转发，保留各独立开关。没有新增未经验证的RTL重构，也未修改全局默认配置。50项扩展两侧均功能通过，105个周期窗口只保留470→473与390→392两项退化，最坏+0.6383%；严格零退化比较仍为false。控制精简另有18项/15窗口无退化及512种选择谓词等价证据，物理时序仍待整机结果，不能声明全部时序收敛。

更新Makefile使dc_profile=area_pair_*选择area_pair.py，原full等配置仍选择原flow.py；make -n检查两条入口正确。三套冻结输入的启动前匹配审计再次通过，同源/同库/同约束，所有局部面积候选的报告已收集。旧area_final_shared1_v1的全寄存器报告查询仍占用超过100GiB，保留并核验映射检查点、area/timing报告哈希后，仅停止该旧DC实例及等待队列；retirement_audit.json保留原因和进程身份，旧流程保留FAILED终态，不冒充完成。新匹配参考侧不受影响。

通过make dc启动area_pair_arithmetic_v2，driver PID3165809，容器DC PID3165925，已确认RUNNING且进入ELABORATE；匹配参考area_pair_reference_v2继续COMPILE，四项中间配置仍PREPARED。这轮目标在确认最新精简候选整机综合实际启动后结束，后台两套整机保留运行，最终面积/时序尚未出。

## 第三轮面积与时序联合精简（2026-10-15 UTC）

### 已完成整机结果与实际问题

area_pair_reference_v2与area_pair_arithmetic_v2均为COMPLETE、returncode=0。前者整机面积3,217,815.8582 μm²、Ara核心1,192,619.6620 μm²；后者分别3,172,506.4267和1,145,621.9986 μm²。匹配组合节省整机45,309.4315 μm²（1.4081%）、Ara 46,997.6634 μm²（3.9407%）。相对历史ara_main的Ara 915,540.9599与整机2,928,017.2042，最新候选分别高25.1306%和8.3500%；历史差异不能全部当作严格配对的规约因果成本。

两侧1ns目标均不满足，reg2reg WNS为−1.83705→−2.56573ns。最新最坏路径从Lane 1普通FPU NONCOMP valid寄存器，经结果仲裁、VMFPU发射控制、共享ADD仲裁、FP64算术到UF结果寄存器；数据到达3.423734ns、要求0.857999ns。自动切环警告仍存在，因此这些slack不能换算为可信的最终Fmax，也不能用仿真周期不变证明实际执行时间不变。

旧网表存在明确的零输入状态寄存器：四个VALU映射模块定义中各331个所选后台FF的D直接接n_Logic0_，共1324个定义级实例；这是扫描的直接接零子集，不是全芯片所有常量FF的精确计数。相关脚本设置compile_seqmap_propagate_constants=false。先前只把这些FF的D置零，不能保证其Q及后续逻辑被综合清除。证据保存在build/reduction_area_timing_v3_audit/zero_fed_registers.json，原始映射网表不变。VMFPU也采用同一种RTL置零写法，本轮一并从生成结构上消除对顺序常量传播的依赖，不声称上述1324包含FP侧。

### 三项实现，全部保留独立开关

1. ARA_RED_STATIC_LEGACY_STATE：在VALU/VMFPU中将旧后台状态移到generate分支。旧通路仍启用时，保持原有复位值与逐拍更新；已由RCE覆盖、RedLegacyStreamEnable或RedLegacyFpStreamEnable为false时，相关q直接为常量，不再生成接零D的触发器。只裁剪先前已经禁用的后台上下文，不裁剪前台局部规约、有序token或架构提交状态。性能计数器及slack评分不在本轮替换范围。
2. ARA_RED_STATIC_ORDERED_ARBITER：用两个固定索引优先选择实现相同的环形优先级，先找低位请求，再优先选round_robin_q及其后方的请求。保留阻塞时锁定来源、客户端分组和接受后推进规则，避免动态索引加取模形成不必要的仲裁网络。
3. ARA_RED_COMPACT_ORDERED_BACKEND：复用fpnew_fma的原始ADD数值逻辑，为各已支持格式生成无寄存器算术，统一选择后进入一份共享结果/异常/owner寄存器。共享单元原本只允许一个未完成操作，多个格式的独立输出流水和通用格式仲裁不提供额外可用容量。候选仍是一拍返回，可在消费旧结果的同一拍接受新请求；busy和owner管理保留。输入继续不检查NaN boxing，窄格式结果仍补全高位1；Mask=0屏蔽异常标志，舍入和特殊值运算仍来自原fpnew代码。普通Lane FPU没有被替换。

上述修改分别对应Make选项reduction_static_legacy_state、reduction_static_ordered_arbiter、reduction_compact_ordered_backend，默认均关闭。没有增加流水拍数，没有缩减VLEN、Lane、普通FPU功能或队列深度，没有放宽1ns时钟、0.15ns不确定度，也未增加时序例外。

### 启动前验证与边界

compact_ordered_unit_v1四种组合（4/5客户端、1/2共享单元）各6000周期通过。v2在此基础上增加随机Mask=0，并实例化冻结的修改前模块，逐拍对照ready、response valid及所有有效结果/异常/标签，包括输出背压期间；四种组合全部通过，复位后分别核对1423、2739、1372、2780个结果。该检查验证已覆盖时序与算术一致，不等于全状态形式证明。

area_timing_smoke_v1复用已冻结并核验源码哈希的整机模拟器，直接比较v2机制组合与三个新宏同时启用的组合。两侧22/22功能通过，18个计时窗口逐项相同，包含ordered FP16、舍入、宽化、Mask、FP64收尾、FP/整数Late Seed、所有权、VL=0、epoch、普通运算、Slide及内存序列。例如ordered非重复549→549、FP64混合940→940、容量473/749/1197/1933均不变。参考本来已含算术转发的轻微代价，不以此覆盖旧470→473和390→392记录。

compact_ordered_soc_v1与static_legacy_soc_v1分别进行共享后端组合、静态状态的50项扩大消融，启动整机综合时仍在运行。compact_ordered_ppa_v1在五个动态客户端、一共享单元、同库同约束下做局部面积/时序配对，也仍在运行。未提前给出局部或整机节省百分比。

compact_static_loop_diagnostic_v1两侧工具返回0且无Error，但UNOPTFLAT仍各116项，移除一个共享ADD内部信号警告并新增一个普通FPU内部信号警告。此类向量/always块级SCC不等于物理环的计数；不能说环路已清除。最终须检查新整机网表的实际路径、自动切环和setup/hold违例。单拍FP64算术仍可能成为限制，本轮未声称1GHz闭合。

### 最新综合启动与后续判断

新增area_pair_timing配置，在上一版area_pair_arithmetic上只开启上述三个宏。area_pair_arithmetic_v3与area_pair_timing_v3输入审计通过：436份源/头文件、390个HDL顺序、11库以及运行约束匹配。启动脚本又核对valu.sv、vmfpu.sv、shared_ordered_adder.sv与已通过组合回归的冻结模拟器源码哈希一致。修复physical_summary的空面积字段：从同一次实际area.rpt读取Total cell area，缺失或非正数时报错；没有改变综合约束或优化设置。

2026-10-15 05:50:05 UTC通过Make启动area_pair_timing_v3，driver PID3929393，确认容器DC进入ANALYZE。v3参考侧只准备，未运行；v2两侧完成报告仍保留。新轮的面积、setup/hold及环路改善尚待报告，50项回归和局部PPA继续独立运行。启动记录在该目录driver_pid.json；未提交或推送工作区修改。

从资源分布看，上一版四Lane精确累加器合计52,133.0876 μm²，RCE整体29,118.0956 μm²（其中Finalizer 12,556.3199），共享ordered ADD 18,859.6800 μm²。Finalizer属于RCE，不能重复相加；VMFPU整体也含普通运算和精确累加，不能把630,112.217 μm²全部视为新增规约面积。本轮优先删除无有效工作容量的控制/存储，后续若要继续大幅下降，应基于新报告重新分解算术与状态成本。直接削减精确位宽或增加有序反馈流水级需要额外数值和性能论证，不应仅为面积数字随意采用。

## 第三轮回归完成与拓扑检查修正

compact_ordered_soc_v1和static_legacy_soc_v1均已完成；每组两侧50/50功能通过，各105个计时窗口逐项相同，严格比较all_pass=true。该结果补全前述运行中记录，仍不证明物理时序闭合。

area_pair_timing_v3于2026-10-15 06:16 UTC以FAILED退出，尚未进入映射优化。ordered_backend_inventory显示shared_units=3 expected=1：原脚本以gen_unit下i_add的数量统计共享执行单元，新紧凑实现的一套执行单元有三个格式算术子实例，因此被误判。此处是本轮遗漏更新的脚本检查，不是已发现的RTL功能失败。旧失败目录和报告完整保留。

area_pair.py私有模板现按gen_unit所有者去重计数，并另行检查每个所有者的算术切片数：紧凑配置3，旧配置1；原本的共享单元总数及Lane本地单元检查仍保留，未移除保护或修改硬件。Tcl定向检查覆盖新结构、旧单元及双单元，原14项流程测试通过。新冻结area_pair_timing_v4与失败v3的RTL、宏、库、周期、不确定度、核数和范围逐项相同。v4通过Make在后台重新启动，具体PID和时间见driver_pid.json；尚无新整机面积和时序结论。

## v4完成后的面积/时序收敛审查（2026-10-16）

本节只进行报告与源码审查，未改变RTL、综合约束或启动新EDA任务。area_pair_timing_v4已COMPLETE且returncode=0。相对area_pair_arithmetic_v2，整机3,172,506.4267→3,181,876.9629 μm²（+0.295%），Ara核心1,145,621.9986→1,153,179.8147 μm²（+0.660%）。WNS从−2.565734改善至−1.079149ns；时序仍未闭合。clk_i组TNS从−34,328.957031改善至−20,796.187500ns，但setup违例端点从53,165增至55,964；hold最差仍−0.150243ns，clk_i组hold违例39,107→42,298。不能只凭WNS改善称整体时序已收敛。

### 面积增量的非重叠拆分

area_timing_v4_delta_audit.json保存两份报告哈希与不重叠层级分类。Lane sequencer增加7,309.85，SLDU增加2,237.26，MASKU增加2,043.55，Requester增加1,086.79，VLSU增加770.78，VMFPU整体增加765.07，主sequencer增加624.29，RCE增加456.12 μm²；VALU减少5,290.32，共享ordered ADD减少1,107.62，Dispatcher减少825.72，operand queues减少498.29，其余连接减少13.94 μm²。合计与Ara增量7,557.8161吻合。该脚本scope保守标注历史报告观察，未将每项变化冒充独立机制因果消融。

VMFPU整体内部另有普通bulk FPU增加5,285.95、EW32乘法器增加5,139.96，而精确累加器减少499.30 μm²。这些子项已经包含在VMFPU总项里，不能重复加到Ara增量。它们说明新增面积并不等于新增加了对应运算功能：本轮只修改VALU/VMFPU旧后台状态生成和共享ordered后端，需要检查映射选择与跨模块负载。

两版映射网表逐模块统计表明，四个Lane sequencer的触发器数都是2,818（706+704+704+704），但名称含D8的DF类触发器从1,016增至2,164。其local_seq面积增长与模块总增量基本对应。确定的结论是数量未增加、单元类型明显改变；驱动负载、setup优化等各自的因果贡献尚未通过独立实验分离。不能说多了数千位指令队列，也不能保证把D8全部换回小单元而不损失时序。证据见area_timing_cell_mapping_audit.json。

### 两条必须分别处理的长路径

最坏路径是operand queue命令读指针→operand mux→Lane有序操作数选择→共享ADD→结果寄存器。到Lane operand_o时约0.674768ns，到ordered_add_request_o时0.868770ns，进入FP64算术时0.895713ns，最终结果寄存器D为1.936312ns；要求0.857163ns。约一半延迟在算术之前，单改加法器尾端不足以解决全部问题。新增输入/内部寄存器可能有效，但会改变有序反馈的周期，必须测量，不能预先宣称无代价。

另一类路径从exact_seed_q，经Finalizer的seed对齐/插入、绝对值、前导位搜索、提取和舍入，再通过结果转发到地址生成spill寄存器，报告slack约−1.048018ns。源码reduction_completion_engine.sv中的completed_q目前是空闲时透明的保持槽：exact_result_o在completed_valid_q为0时直接选择raw_result。因此已有“结果缓冲”不等于存在完整时序边界。这解释了为什么仅修共享ADD仍不足以闭合。

### 推荐下一轮候选与取舍

第一优先是以v4为保留参考，针对非关键路径做面积恢复，审查Lane sequencer及SLDU的大驱动寄存器和高扇出控制。保持相同1ns约束，比较寄存器类型分布、WNS/TNS和setup/hold；不要全局禁止D8或放宽周期后把面积变化算成RTL收益。当前Lane sequencer多出的7,310 μm²是需要调查的规模，不是保证可回收的额度。

第二优先是给精确收尾到消费者的路径建立真正寄存器边界，优先复用已有completed_q而非新增大FIFO。应改为完成结果先进入槽，再从槽写回/转发，并同步修改push/pop、同拍替换、local_complete与seed版本管理。它可能让独立源流的吞吐保持不变，却使串行Seed链增加结果可见延迟；需分别测量两类负载。这条控制边界建立后，已有SharedExtract候选可以在当前约束下重评：此前局部面积虽下降约10.48%，但时序变差约37.6ps，不能直接将旧结论推广到当前整机或直接默认开启。

第三项是将共享ordered后端中的通用FMA ADD特化为真正的标量加法数据通路。当前fpnew_fma仍使用p=53、3p+4=163位的FMA对齐/求和表示和2p+3=109位前导零结构；常量ADD会被综合折叠一部分，因此源码宽度不能等同于映射后保留的完整硬件。专用ADD可围绕两个53位有效数、指数比较、对齐、符号相消、GRS和舍入重新组织，保留FP16/32/64与全部异常/舍入语义。该候选可能同时改善面积和延迟，但数值验证成本高；不能简单把163位截窄或共享成单一FP64舍入再转小格式，以免发生双重舍入错误。

第四项是精确累加的段数折中：当前8×65=520位分段状态，可以研究4个64-bit指数窗口，每段97位，合计388位，状态位理论减少25.38%。这是4个指数段，不是恢复此前4×288位完整累加器。代价是单段反馈加法从65变97位，索引/选择网络缩小；可能省面积也可能被更宽加法器抵消。应保持288位对外精确表示和人口上界，先做独立数学oracle、碰撞/抵消/最大VL验证及局部PPA。25.38%仅为段寄存器位数，不是累加模块或整机面积降幅。此前共享beat-update反增面积的方案不重复作为已确认收益。

若目标仍是相对历史ara_main整机增幅不超过5%，按当前报告还需省约107,458.90 μm²；若目标是Ara核心增幅不超过5%，还需省约191,861.81 μm²。历史基线并非严格同配置的机制消融，数字仅作目标尺度参考。共享ADD目前总共17,752.06 μm²，单靠继续精简它不可能填平上述差距。应先收回映射膨胀，再联合收尾时序边界与精确数据通路压缩，采用面积和关键负载周期都可归因的独立候选，而非再次盲目启动整机综合。

## 精确累加寄存器直接读取候选（2026-10-16）

本轮目标是继续降低面积，同时保留原有规约节拍和重叠能力。新增默认关闭的DirectBinRead参数、ARA_RED_EXACT_DIRECT_BIN_READ宏和Make选项reduction_exact_direct_bin_read。仅在ExponentSegmented、CollisionForwardUpdate和DeferSeed同时成立时改变有限数更新的输入组织：原实现将segment_bin_d传入目标段读取与同段冲突转发，候选直接读取segment_bin_q，再对首拍读值清零；未写入的段在首拍同样清零。非延后Seed模式保留原路径，避免遗漏本地Seed先插入再累加的语义。特殊值折叠、同拍前序元素优先级、归一化状态、输入接受节拍、结果背压和上下文容量均未主动改变。

预期收益来自将首拍初始化及其他状态的next-state选择移出索引读数据路径，而不是减少计算精度或增加等待；综合器能否从原代码推导出同样结构尚未知，因此这是候选，不是已确认节省。修改前源码冻结于build/exact_direct_read_audit_v1/fp32_exact_reduction_accum.before.sv。

exact_direct_read_unit_v1已通过300组、12种合法参数配置、每配置8种更新/归一化组合的逐拍等价检查，以及900组FP32/FP16/宽化规约独立整数oracle。测试包括同段冲突、抵消、Mask、输入气泡、并发start/data、256元素人口边界和结果背压。由于原测试允许不同内部表示在out_valid前不同，另启动exact_direct_read_unit_v2：使用本轮冻结的相同表示参考，并强制比较无效周期的exact_value，以进一步检查内部状态对应关系；该轮结果需另行收集。

exact_direct_read_ppa_v1正在进行单Lane精确累加器的局部配对综合，仅DirectBinRead=0/1不同，双方均采用八段、共享归一化、同段冲突转发、中央舍入和延后Seed。保持1ns时钟、0.15ns不确定度，双方禁用寄存器复制/合并及顺序常量传播，冻结源码、runner和库哈希。这是新的局部匹配对照，不能直接与历史采用不同顺序常量设置的局部数值比较。尚未得到面积/时序收益，未启动新整机综合。

exact_direct_read_soc_v1以已验证的static_legacy_soc_v1/scalar为参考保留全部宏，冻结相同ELF，在共同当前源码上只切换直接读取宏，进行两侧各50项功能与周期回归。input_pair_audit.json检查两侧源码哈希相同、唯一宏差异及50份共同ELF；结果仍待收集。原综合v4、旧失败和用户停止的任务均未覆盖或重启。本候选不修改全局默认配置，必须通过功能、周期和局部PPA之后才能考虑进入整机候选。

exact_direct_read_unit_v2随后完成，300组、12种配置的逐拍对照通过，包含无效周期的exact_value比较；未通过忽略内部表示差异来取得该轮PASS。整机两侧398份源码哈希相同、唯一宏差异的输入审计通过。局部PPA及50项整机回归仍在运行，收益结论保持未验证。

## 四个宽指数窗口的独立面积候选（2026-10-16）

新增默认关闭的WideSegments参数、ARA_RED_WIDE_EXACT_SEGMENTS宏及reduction_wide_exact_segments构建选项。采用四个64-bit指数窗口，每段97位，代替八个32-bit窗口、每段65位；有限状态从520位降至388位。每个64-bit归一化块直接由一个段及下位进位组成，继续复用原MERGE_PAIRS/MERGE_ROOT两个状态和98位chunk表示，输出仍为288位。没有修改每拍数据包容量、Seed插入规则、特殊值顺序或结果握手。宽反馈加法器可能抵消选择和寄存器的减少，132位的状态节省不能当作模块或整机面积节省。

exact_wide_segments_unit_v1完成300组、多配置逐拍对照及900组独立整数oracle。v2进一步将人口边界操作数的局部位移设为各窗口最大值63/63/63/61，覆盖最大有限FP32值、256元素加Seed以及抵消，300组对照通过。不同分段表示在结果无效时允许不同，所有握手、元数据、有效结果及特殊状态仍要求一致。population_bound_audit.json另外核查16/32/64-bit窗口下257个有限FP32项的分段上界、98位归一化和33位进位容量及288位最终结果；它是整数边界检查，不替代RTL验证或扩大VL支持范围。

exact_wide_segments_ppa_v1进行独立局部配对，DirectBinRead两侧明确为0，只有WideSegments=0/1不同。两侧均禁用顺序常量传播、寄存器复制及合并，保持相同库、时钟和输入/输出约束。新runner、源码和库哈希已冻结；收集器支持两项新候选，并额外检查切换方向、脚本与日志哈希。历史八段局部报告的解析仍得到原10.15697%节省，未覆盖历史证据。当前未有新面积结果，也未将四段候选加入整机默认配置。

本轮另以v4最终映射网表扫描直接接常量零D的DF类单元，保存网表路径、哈希和模块定义级计数于build/exact_direct_read_audit_v1/v4_remaining_zero_d_ff.json。命中主要为标量寄存器文件、除法准备与控制模块，未命中名称含VALU/VMFPU/exact/reduction/ordered的模块。该扫描不覆盖间接常量网络，也不是展开后的全芯片实例计数；它仅说明此前依靠规约后台大量接零触发器获益的同一机会不能再次计入。后续面积探索继续聚焦数据通路与选择网络，不为凑面积数字改动普通除法或标量功能。

exact_direct_read_16bin_unit_v1补充旧16段配置下的300组逐拍等价检查，已通过。该结果验证DirectBinRead未仅对当前八段生效；四段与直接读取组合尚未作为通过的配置。

四段边界覆盖复查发现v2中指数窗口和符号由同一个取模值决定，未让每个窗口的大人口定向案例都覆盖正负号。因此仅增强测试，不改RTL：exact_wide_segments_unit_v3将窗口、符号和抵消模式解耦，执行600组、12种配置及8种更新/归一化组合，已PASS。窗口0/1/2/3分别覆盖最大局部位移63/63/63/61的正、负累加和抵消，原随机输入、气泡、Mask与背压检查保留。旧v1/v2结果未覆盖或重新标记。

exact_direct_read_ppa_v1参考侧已正常完成，实际Total cell area为10,404.407918 μm²，最差报告setup slack +0.000050ns。候选侧尚在映射，因此此数值仅为本轮局部参考，不能据此声明面积下降或整机时序闭合。

## 两项候选的局部综合结论

exact_direct_read_ppa_v1两侧已正常完成，收集器核验库、源码、脚本、日志哈希和完成标记后生成comparison.json。面积10,404.407918→9,857.231881 μm²，减少547.176037 μm²（5.2591%）；顺序单元数两侧均619，说明本次收益没有依靠削减状态容量。最差报告setup slack +0.000050→+0.000028ns，TNS及setup违例数均为0；局部setup满足本组约束但余量稍降，不能宣称时序提升。QoR hold最差−0.08→−0.07ns，违例403→337，仍未hold闭合。该局部收益不能乘Lane数量当作整机确认收益。

对局部QoR面积项补充拆分：组合单元数11,523→11,001，组合面积8,390.591925→7,982.351924 μm²；顺序单元数均619，但顺序映射面积2,013.815992→1,874.879957 μm²，说明相同状态位数仍可能因驱动/时序映射改变单元尺寸。Buf/Inv面积734.999990→648.311992已包含在组合面积内，不另加到547.176037 μm²总节省。因此“直接读取只省组合逻辑”并不准确，确认结果是状态数量未减、整体单元映射面积下降。

exact_wide_segments_ppa_v1两侧同样正常完成。面积10,404.407918→11,183.423902 μm²，增加779.015984 μm²（7.4874%）；顺序单元619→487，存储减少被组合逻辑和映射成本抵消。setup slack +0.000050→+0.000037ns；hold最差−0.08→−0.09ns，违例403→307。尽管功能测试通过，面积目标未达成，因此四段方案不进入下一版整机候选，默认关闭，保留源码开关和失败的成本收益证据。未尝试把它与直接读取混合后冒充独立收益。

新增area_pair_direct_read整机实验配置，基于area_pair_timing只增加直接读取宏。收尾后端拓扑检查同步将两种紧凑配置均识别为每共享单元三个格式切片，保留所有者及切片数检查。原14项流程测试通过。准备area_pair_direct_reference_v1和area_pair_direct_read_v1，尚未启动DC；整机50项功能与周期回归仍在执行，必须收齐后决定是否启动集成综合。

## 集成验证源码对应关系补齐

两份新整机综合输入配对审计通过，436份源码/头文件、390 HDL顺序、11库和约束相同，唯一宏差异为ARA_RED_EXACT_DIRECT_BIN_READ。但进一步核对模拟器与综合发现，v1整机回归沿用旧冻结Lane sequencer和addrgen，未包含当前HEAD bf1d6e1b的索引操作长度/地址消费修复；SLDU冻结版本也与当前源码哈希不同。原v1仍是合法的旧组合独立消融，不能作为当前综合组合已完成验证的证据。

为此新增--current-integration-rtl选项，仅冻结当前lane_sequencer、sldu和addrgen到双方，不改变旧冻结测试。启动exact_direct_read_soc_v2两侧50项完整回归；直接读取为唯一候选宏。integration_source_audit.json逐项检查当前Ara hardware/src文件与准备综合的哈希对应，并核查模拟双方源码相同。综合与仿真的依赖overlay仍按各自环境保留，未宣称整份filelist完全相同。整机综合继续保持PREPARED，等待当前组合回归完成；没有修改其他会话的索引修复或重写HEAD。

新增run_direct_read_validated_pair.py及area_direct_read_validated_queue_v1后台串行任务，当前WAITING_REGRESSION。它绑定v2回归PID及Linux进程起始标识，定期检查真实进程；完整报告前进程消失则停止。两侧报告COMPLETE后重新运行严格功能/ELF/周期比较，要求50项并核验模拟器及源码哈希、36项集成源码证据，再重新核对综合配对输入。任何检查失败均STOPPED，不自动重试或覆盖旧综合。通过后按reference→candidate顺序运行已冻结整机配置，每次启动前要求PREPARED、检查脚本/输入未变及MemAvailable至少80GiB。STOP文件阻止后续启动，不终止已运行DC。队列已启动不代表整机DC已启动；各run/status.json仍是实际状态依据。当前未宣称全局面积节省或目标完成。

direct_read_queue_negative_v1对该入口进行拒绝测试：用独立临时目录提供不合格的COMPLETE报告，真实比较器返回非零，队列记录STOPPED，reference/candidate综合阶段日志均未创建，两边仍PREPARED。此测试只验证不合格报告不能越过比较入口，不替代真实50项通过证据。正在运行的正式队列和回归未修改或重启。

对上一版整机两份映射网表进一步逐个匹配Lane sequencer触发器实例名称，审计保存在build/synthesis/lane_seq_ff_mapping_audit_v1.json并带双方网表SHA-256。四个Lane的定义级FF数维持706/704/704/704；Lane 0/1/2由非D8映射变为D8的实例分别305/435/447，Lane 3仅20，反向变化为5/12/3/39。集中在operand_request_o的vstart、hazard、vl、source_version字段以及vfu_operation_o的scalar_op字段。它定位了面积增长对应的信号家族，但不同Lane变化幅度说明布局负载和时序映射也参与选择；未通过独立消融证明RTL因果，因此不贸然删除请求载荷或全面限制D8。继续以当前完整配对综合判断直接读取方案的整机面积。

## 专用标量浮点加法器候选（尚未集成）

新增独立实验模块hardware/src/reduction/scalar_fp_add.sv，针对当前共享收尾/有序后端只执行ADD的使用方式，尝试用专用加法数据通路代替固定操作码的fpnew_fma。现有紧凑后端已经由综合常量折叠部分通用逻辑，因此不能将整个FMA面积视作可删除增量。候选采用幅值排序、带sticky的指数对齐、有效数加减、归一化以及现有fpnew_rounding，保留NaN、Inf、符号零和异常标志；没有新增流水级，也尚未接入Bender或shared_ordered_adder。是否满足频率和是否实际省面积均待局部配对综合确认。

首轮编译发现large/small为SystemVerilog保留字，改为larger_operand/smaller_operand后，scalar_fp_add_unit_20261016T132936_974379Z的smoke通过：FP16/32/64各5454次，与真实fpnew_fma的ADD逐项比较结果和五位异常标志，覆盖六种舍入配置。完整随机和定向差分正在独立目录scalar_fp_add_unit_20261016T133007_273479Z执行，不能将smoke通过视作数值正确性验收，更不能据此声称整机性能不变。后续若采用，必须保留现有请求仲裁、所有者、输出寄存器、Mask标志门控和窄格式NaN boxing，并重新验证后台握手与混合负载。

scalar_fp_add_unit_20261016T133007_273479Z现已完成，FP16/32/64各774678次比较通过（每格式100000组随机操作数，各遍历六种舍入配置，另含特殊值和定向案例）；结果及异常标志均一致，依赖哈希未改变。此证据支持进入局部面积/时序评估，不是所有浮点输入的形式证明，也不涵盖尚未集成的仲裁、NaN boxing和背压接口。

## 最新完成版的后续面积定位

以area_pair_timing_v4最终area.rpt对历史ara_main报告重新进行互斥层级拆分，保存area_timing_v4_historical_breakdown.json。Ara总差237638.8548 μm²，其中VMFPU +88416.38、RCE +29574.22、operand requester +27943.61、SLDU +18217.42、共享ADD +17752.06、Lane sequencer +15958.32、VALU +14631.96 μm²。它仍是历史报告差异，不是严格配对消融，不将其全部归因于规约。

进一步按四个VMFPU的直接子模块与本地单元互斥拆分，保存area_timing_v4_vmfpu_breakdown.json：精确累加器总面积51633.79 μm²；VMFPU本地组合与顺序逻辑相对历史增加35888.16 μm²；常规fpnew bulk增加13377.34 μm²，同时普通整数乘法器映射面积有所下降。这说明共享ADD专用化即使成功也只是总体增量的一部分。接下来的RTL审查仍需聚焦精确累加数据通路及本地上下文/选择逻辑，不通过减少并发上下文、删掉预取或取消规约结果复用来制造面积下降。

专用ADD局部配对scalar_fp_add_local_v1已实际启动，基线固定为fpnew_fma的ADD/零内部流水，候选为scalar_fp_add；三种格式各自保留动态输入、舍入配置和全部结果/异常输出，外部输入/输出寄存器及约束相同。该寄存器边界用于局部对照，不能代替整机operand mux到共享ADD的真实关键路径。工具输出前不估算节省比例。

## 三种浮点格式共享算术的第二候选（开发中）

现有共享ADD虽只有一个未完成请求，紧凑后端内部仍保留三个格式切片。新增独立shared_scalar_fp_add.sv实验：FP16/FP32的有效数左对齐至53位，保留各自原生偏置指数，统一幅值选择、对齐、加减和归一化；目标格式分别抽取尾数与guard/sticky，直接按目标精度舍入。不能先得到已舍入FP64结果再转换到窄格式，否则可能出现双重舍入错误。输出窄格式NaN boxing，异常与符号零沿用同一语义。

此模块没有内部寄存器或仲裁，不减少共享后端请求容量；未来若接入应保留当前一拍输出寄存器和所有者协议。当前仅是独立实验文件，未加入Bender、默认配置或任何正在运行的综合快照；专门格式切换差分正在准备。它也未承诺时序：动态格式解码/结果选择会增加逻辑，必须与三切片专用ADD及原固定ADD的FMA实测比较，不能直接把删除两个切片的名义面积算作收益。

## 两种ADD候选的后端协议验证

为检验一拍反馈和结果所有权，主agent在build/shared_add_backend_prototypes_v1生成测试专用的共享后端快照：保留原仲裁、busy、锁定客户端、所有者、输出寄存器和Mask异常门控，仅替换紧凑分支的算术。scalar版逐格式替换FMA；shared版将三个合法格式交给单个shared_scalar_fp_add。源码未接入Bender或生产RTL，不影响正在运行的整机冻结组合。

run_shared_ordered_unit.py增加可选--candidate-module和可重复--extra-source，默认行为不变，额外源码置于候选前并冻结哈希。shared_add_backend_scalar_protocol_v1和shared_add_backend_shared_protocol_v1均完成四配置（1/2执行单元×4/5客户端）回归，逐周期与原后端比较ready/valid及有效载荷，并通过独立fpnew数值scoreboard检查返回标签、结果和flags。覆盖背压、复位丢弃在途请求、格式交错及第五个FP64收尾客户端；测试台原样保留，其舍入模式为0..4，六模式算术由独立数值测试覆盖。两候选四配置均PASS，复位后分别核对1423/2739/1372/2780个响应。

此结果证明所测序列没有改变后端周期协议，不代表组合时序闭合，也未覆盖整机Mask/Seed/VRF交互。三格式共享候选的完整随机算术验证与面积对照仍待收齐，不能依据协议通过提前宣称采用或面积下降。

三格式共享算术full差分shared_scalar_fp_add_unit_20261016T134010_787036Z已完成：FP16/32/64各774678次，共2324034次，逐次随机轮换格式并使用随机未boxed高位；结果、NaN boxing及五位flags均与真实fpnew_fma一致，依赖哈希未改变。首次smoke的数值日志通过，但runner最初PASS标记拼写导致manifest误判，旧目录和失败元数据保留；full使用修正runner并实际PASS，没有改RTL或预期值规避失败。

shared_scalar_fp_add_local_v1现已启动三模式串行综合。主agent编写统一runtime-format wrapper：Mode0固定ADD的FMA、Mode1三个专用切片、Mode2单个共享数据通路，三侧共用64位输入、格式/舍入控制、所选64位boxed结果和flags及相同寄存器边界。此对照比独立三切片全部端口同时动态的前组更接近真实后端用途，但仍不含客户端仲裁/operand mux，不代替整机时序。启动前核对两个RTL和wrapper与prepare-only冻结一致，共享RTL与full差分一致，MemAvailable为177.48GiB。

新增collect_scalar_fp_add_results.py用于两组局部实验，拒绝未完成任务及缺字段报告，核验源码、库、冻结filelist/Tcl、日志完成标记和报告哈希；同时读取面积、实际setup/hold、TNS及违例数、FF/LATCH计数。运行中拒绝测试成功，尚无最终面积结果生成。

## 独立整机ADD候选回归已启动

新增prepare_shared_scalar_fp_add_soc.py和run_prepared_shared_scalar_fp_add_soc.py，准备目录shared_scalar_fp_add_soc_prepare_v1保持不运行；实际独立任务shared_scalar_fp_add_soc_v1已启动两个候选编译。冻结参考为exact_direct_read_soc_v2/scalar，保留其全部宏和其他RTL，只替换共享ADD模块并插入对应算术源。50个ELF逐项从v2/elfs复制并核对原配置哈希，不从当前apps/bin重新取。两算术源分别与已通过的独立full差分冻结副本一致，原后端与prototype reference哈希一致。

运行器冻结自身与审计/比较脚本，编译和回归记录真实PID、Linux进程起始信息、日志和终态；每侧两个仿真worker。候选完成后须等待参考50项COMPLETE，再调用既有严格功能/周期比较器；单独返回0不算完整通过。参考的长reduction_audit_tail仍持续执行标量初始化，CPU和trace显示进度，未到3600秒超时，因此没有重启或改测试。候选driver的基线等待循环本身未绑定进程身份，另由监控agent核对参考driver身份，若参考提前退出且非COMPLETE须报告处理。以上均为隔离实验，不改变生产RTL和已冻结整机综合队列。
