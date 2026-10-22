# FSM与Toggle覆盖率80%闭环计划

## 用户新增可信执行IP整模块范围授权

用户允许有修改但功能独立、架构边界清晰的执行部件整体waive。
因此可信集成口径不再以“源码完全未改”为必要条件；但不能把
已知未解决功能错误隐藏成覆盖豁免，原始报告和功能检查继续保留。
授权范围也包含其它具有类似独立边界和已有功能验证证据的执行/辅助
模块，不限于下面七类。逐实例记录理由和证据；局部修改本身不阻止
整体豁免。已知功能失败仍须保留，不能把范围调整当成修复或新增覆盖。
本次扩大评审至SIMD ALU/乘法、serial divider算术核心及FPnew FMA，
不是将VALU/VMFPU及其队列、依赖、异常和完成控制一起排除。

父端实际解析冻结编译design.xml，`i_system`内候选模块库存如下。
这是实例数量，不是已批准数量或可预计的覆盖率增益：

| 模块类型 | 编译实例数 | 本轮处理 |
| --- | ---: | --- |
| simd_alu | 4 | 评审算术结果和flags回归，再准备独立集成范围 |
| simd_mul | 16 | 评审SEW/饱和/舍入及流水回归 |
| serdiv | 5 | 仅算术核心，不扩展到simd_div调度wrapper |
| fpnew_fma | 32 | 独立IP边界，包括其流水验证责任，需明确证据 |
| fpnew_classifier | 127 | 独立分类逻辑，参数/源码身份绑定 |
| fpnew_rounding | 50 | 按EnableRSR等实际参数区分，不自动批准全部 |
| lzc | 453 | 按实际width/mode证据区分，不排父仲裁控制 |

通过后的整模块EL在单独TRUSTED_IP_INTEGRATION报告中使用；保留
797项原始及已验收73.18%精确豁免口径。不使用新分母掩盖缺失激励，
也不将范围调整写成新增Toggle活动。577个去重根实例的整模块豁免
现已完成原生应用及独立验收，最终结果见下一节。

用户进一步确认，同类功能独立、已有可靠验证证据的模块也可以整体
豁免，包括局部修改过的模块。实施时采用相同准入规则，不限于七类
库存；不把“没有发现问题”当成穷尽验证，也不排除功能检查。
已知失败、调度/队列/依赖/异常/完成控制继续保留。C910 SRT算术
核心正在按此规则独立评审，尚未加入已验收的577个根实例。

### 当前正式口径

| 797项已通过测试的报告口径 | Line | Condition | Branch | FSM | Toggle |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原始、无豁免 | 85.45% | 82.30% | 83.25% | 70.68% | 65.49% |
| 原有精确点豁免 | 85.43% | 82.31% | 84.03% | 81.09% | 73.18% |
| 可信独立IP整模块豁免 | 84.62% | 80.46% | 82.45% | 80.74% | 72.81% |

可信IP报告为`verification/out/trusted-ip797-global-parent-20261008-01/`，
原生DVE排除文件为其中的`applied.el`。它绑定本次冻结设计及确切
实例校验码，不可直接套到新RTL镜像。整模块豁免不增加PASS测试数，
也不意味着当前Toggle已达到80%。

## 最新已验收整体报告（797项，含MaskU精确豁免）

### 可信IP整模块原生汇总已启动

父端实现`report_trusted_ip797.py/.tcl`，6项host测试实际通过，准备目录
为`trusted-ip797-global-parent-20261008-01`，config SHA为
`4ca6047e0c9e96218f8c4c07aed35a4a29d38cd18042d015fa3f5ae1b5f4e358`。
独立后台服务`ara-trusted-ip797-global-parent-20261008-01.service`
已启动，父端确认worker PID1445236实际存活，运行目录/命令正确；
`execution.json`及`live-identity.json`已生成，未出现service stderr。
原生DVE执行577根精确scope豁免，保留同797项输入和原有EL。
保存/重载时允许native保留或省略已被整IP包含的冗余子项，其它范围
的原EL必须精确保留；raw/reset/final恢复原797六指标及2989行原始
层级数据，applied/reloaded一致，非目标模块指标不得改变。
最终qualification通过前仍不能宣布已应用，暂不更新73.18%结果。
任务只汇总现有VDB，无RTL修改、无仿真重跑，也不覆盖旧报告。

父端已独立检查原生`applied.el`：577根及其数字校验码、可信IP注释、
重复拒绝和原EL补集保护全部通过。`modules_applied.csv`有完整73行；
临时`i_system`为Line84.62%、Toggle72.81%、FSM80.74%、
Condition80.46%、Branch82.45%。尚待reload/reset/final和终态验收，
不能作为正式最终值。整体排除可靠IP后比例略低，是因这些IP已有较高
覆盖，剩余控制/交互更难覆盖；不筛选模块以人为抬高百分比。
独立只读补验工具`verify_trusted_ip797_readonly.py`的12项测试实际
通过，补验manifest SHA为
`fe0f2fb17ad705db9016ba0de74b12ed30d44393789eb1535240231163aeb7f5`，
目录`trusted-ip797-readonly-parent-20261008-01`。最终补验检查whole块
注释/重复、完整marker计数以及递归GUI日志，不重跑EDA。

本轮临时模块报告暴露的剩余低Toggle包括D-cache read-port controller、
PTW、QBS read engine/FP accumulator、segment sequencer、mask operand
queue、scalar store unit和store/load lookahead。它们未被独立算术IP
范围掩盖；须区分可达控制缺口、配置常量和数据字段，不凭低比例
直接整模块排除。Gather→indexed-load定向测试优先覆盖LDU完成等待。

整模块原生服务现已终止：inactive、MainPID0、ExecMainStatus0，
原生qualification状态`TRUSTED_IP_INTEGRATION797_NATIVE_VERIFIED`。
结果确认Line84.62%、Toggle72.81%、FSM80.74%、Condition80.46%、
Branch82.45%。GUI中TRUSTED、COMPACT及EXPORT三项完成marker各一次。
独立补验发现一个报告封存脚本问题：qualification记录了service stdout
的hash，随后正常打印最终JSON，导致stdout文件追加一行而hash变化。
父端实际检查全部24个其它输出pin均精确匹配，stdout的原前缀hash
精确匹配、唯一追加内容也精确等于qualification的最终status/metrics
JSON。未发现原生EL或覆盖数据漂移。补验后继将显式检查这一次已知
尾追加，并封存完整最终日志；不重跑EDA、不放宽其它文件hash要求。

已生成`remaining-toggle797-raw-priority-parent-20261008-02.json`，
绑定797 Toggle OR、可信scope清单及旧qualified EL，排除可信IP和
已有整模块观察器。它是原始serialized-zero调查排序，仍包含旧精确
点豁免，不是DVE最终未覆盖分母，也不据此估算覆盖百分比。
主要原始缺口集中于SoC接口别名、QBS payload banks、CVA6/CSR和
C910 SRT算术核心。已安排分别区分配置/接口常量、可达控制和可靠
独立算术核心，避免把所有零槽都误认为能用随机激励补齐。

最终独立补验已完成：`verify_trusted_ip797_readonly_v2`父端实际8项
测试通过，manifest SHA
`f1562c63d29de47ec6f70c9ada54f9b40de55a5df261e9a8f91a1ec608ba6f65`。
父端验收receipt为
`trusted-ip797-readonly-v2-prepared-agent-20261008-01/parent-qualification.json`，
SHA `bde0baabf0a605e74583d54c47218b341f7d363c4a76ab3ba700ae0ebeddb09a`，
状态`TRUSTED797_SEALED01_READONLY_SUPPLEMENT_V2_PASS`。它严格核验
原stdout前缀及唯一186-byte最终JSON追加，全部其它原输出pin、577根
注释/重复、五阶段EL/marker及递归GUI日志。完整报告现已独立验收，
无需重跑EDA。Toggle72.81%、FSM80.74%是可信IP集成口径最终值。

Gather→indexed-load新激励已开始VCS：10项父端host tests实际通过，
预检Spike独立gold PASS，39052条entry→tohost指令，16个完整向量
writer/16384 bytes、24个CSR值与两组各12672-byte源/快照guard检查。
预检SHA `cd05bebfca68cba72358c6b5185bbb75897ba0dd6bafb2fcab69d6283ccd4371`，
prepared SHA `e344e4f083ab58c3f6a30ae6ad7f34cd3991678abffee914403d700bd149cd5f`。
服务`ara-gather-war797-parent-20261008-01.service`已启动，VCS PID1456679，
绑定冻结simv66及独立ELF；commit trace已有3359行，不是只创建了任务。
单次仿真300s预算，不修RTL，不由simulator退出认定PASS。
严格collect及相对797完整OR的新增目标命中通过前，不增加PASS计数。

该VCS任务现已退出，service为inactive、MainPID0、ExecMainStatus0。
父端随后执行严格collect，在`Exact Gather/LD producer and context`
检查处拒绝，失败保存在`gather-war797-qualified-parent-20261008-01/`。
正在只读区分检查器生产者编号假设与实际轨迹；目前不能判定RTL
故障，也不能计入覆盖率。上述正式报告仍为797项，没有新增PASS。

只读定位确认，原检查器将Gather生产者写成3（SLDU），但冻结RTL
`ara_sequencer.sv`将Gather派往ALU和MASKU，`operand_requester.sv`
的writeback监控将MASKU映射为2。实际四轮Gather均为source2，
每轮128次写回，vd16、EEW8、VL1024。原始轨迹保留，用独立后继
检查器按真实路由检查；不能仅更换标签就宣布功能通过，仍须完整
比较16个目标组、全部有效字节和标量/存储/CSR/guard结果。

C910 SRT整核心候选已由父端执行6项边界测试并生成源证据清单
`srt-whole-trusted797-reviewed-parent-20261008-01.json`，SHA为
`8ab861afddc0070b26ef071d30af8a3fcdce083f2960bd8748e9872308df662c`。
候选包含16个向量核心和1个标量核心；仅包含其bound-table和内部
gated-clock子模块，保留外部prepare/round/pack/control和wrapper。
该提案尚未原生应用，不改变已验收的72.81%结果。

Gather后继检查器已完成父端10项实际测试及完整collect。父端结果
`gather-war797-successor-qualified-parent-20261008-01/qualification.json`
SHA为`f7fbbcb4da9b7dab57cbb963ffdbc38fd48cc8fef1b1e03179cc82cf089e9677`，
状态`GATHER_WAR797_FULL_STRICT_AND_NEW_TARGET_GAIN_PASS_NOT_ADMITTED`。
四轮16个向量writer、16384个有效字节及标量、存储、CSR、guard全部
比较通过，无unknown skip。相对原797项，新增118个serialized Toggle
槽、24个Condition槽；其中LDU的完成等待目标新增18个槽，四个队列
entry均命中。这里的槽是数据库覆盖位置，不猜测映射成多少信号位
或翻转方向；尚需离线正式纳入798项清单，再做原生百分比汇总。

17个SRT核心的独立原生汇总已启动，父端实际14项边界测试通过。
目录为`trusted-srt797-global-parent-20261008-01`，config SHA为
`aa19231bcfce807f548b18d69efc2a51a904a923e7b546d52a3da0951ceb32d5`。
服务`ara-trusted-srt797-global-parent-20261008-01.service`拥有worker
PID1467255及DVE PID1467726，已实际确认DVE可执行文件、运行目录和
cgroup。原797项/73个报告scope不变；GUI仅增加17个根，完整继承
577个旧根，候选总数594。该后台任务尚未结束，不能先报其百分比。

用户要求完成当前批次后暂停，不扩展新激励。Gather已正式准入798项，
目录`gather-war-offline-admitted798-v2-parent-20261008-01`，admission
SHA为`f5efacbc0c28c2766d6899f28b002a308f35bdadf33c7e4934a7d241d6b44da3`。
父端实际18项准入测试、4项历史清单测试及35个输出hash/799行唯一
compile-first ledger核验通过。旧797的ELF附件缺第797成员，后继
按封存的VSMUL manifest和ELF补齐，没有改旧文件或取消去重。
本次新激励PASS并产生118个Toggle/24个Condition原始新增位置；
798项尚未进行原生全局百分比汇总。失败及工具问题整理见
`verification/coverage/BATCH_WRAPUP_20261008.md`。

SRT原生后继现已完成，service inactive/MainPID0/ExecMainStatus0。
qualification SHA为
`8333bde0a8c1f5032362882eda934f2d5c670ac34896390678d5d00c8166b776`，
状态`TRUSTED_SRT797_594_NATIVE_VERIFIED`。父端复核26个输出hash、
594根/17新增根及五阶段恢复一致性通过；仍是797项数据。
最终Line84.38%、Condition80.27%、Branch81.90%、FSM80.74%、
Toggle72.97%。原577根和精确点口径保留，不把豁免增益当激励增益。
当前批次已收尾，按用户要求暂停目标，不继续扩展。

### 整模块候选与只读接口实测进展

`trusted-execution797-leaves-review-agent-20261008-01.json`已形成
731个RECOMMEND候选，嵌套106个，最小根实例625个；尚未应用DVE。
该清单包含501个LZC，其中48个位于`i_system`之外，故与顶部仅统计
`i_system`的453个库存不同。后继清单
`trusted-execution797-isystem-review-agent-20261008-02.json`已移除
这48个外部实例，保留683个推荐实例及577个去重根实例；SHA为
`7089a39a78818e9abf5e420aef5b5b4e61a196e8743983654ed19be6cf104769`。
父端实际运行`test_review_trusted_execution797_system_v2`的8项测试
通过：源码/参数证据绑定、严格scope边界、重复拒绝、known-bug HOLD、
父子根去重及越界注入拒绝。该后继仍是只读准备包，尚未原生应用。
本轮覆盖设计范围不扩大到SoC外设，不覆盖原始或73.18%报告。
SIMD ALU四实例因carry/borrow失败尚未定位而HOLD；不是因为有修改。

父端实际运行`test_c910_vector_discovery`的12项测试全部通过，绝对
PYTHONPATH配置检查通过，单次300秒只读DVE任务已启动并终止。
任务`c910-vector-discovery-5ffe92a5fa3da8a2d4f3.service`最终failed、
MainPID0、ExecMainStatus1；原生DVE returncode0且未超时，但
`discovery-error.txt`为`Column enumeration hit bound64; not complete`。
实际`initial.frames`显示列0返回Variable、4返回Type、5返回Coverage，
列63仍返回成功与空字符串；因此不能用“查询抛异常”判断列结束。
其余点击快照未生成，本次不构成逐位或豁免资格通过。保留失败证据，
先根据安装API与实际返回修正读取方案，不盲目重跑、不降低完整性门槛。
整模块豁免使用独立的scope接口，不应被此partial-bit诊断阻塞。

只读诊断v2已实际完成，service
`c910-vector-discovery-25bed7643b89e813e18a.service` inactive、MainPID0、
ExecMainStatus0；父端实际16项host测试和check通过，并独立verify通过。
四阶段每阶段210行，均为7列`tglListView`，没有进入逐位detail。
父端解码`click*.frames`的action发现：`selected_before`为嵌套分组；
原unselect把带额外list层的`{bound_sel[6:0]}`作为名字，实际返回
`List item(s) ... were not found`，选择因而逐次累积。
double-click虽rc0，不能据此称为有效逐位展开。现已定位selection
读取/取消的脚本问题，须正确解码token并严格检查单选readback，同时
静态核对double-click的item语义，才可安排有明确假设的后继诊断。
这不是RTL bug，v2只读完成不等于1424方向豁免通过；仍不汇入覆盖率。

为真实增加激励命中，已安排新增Gather非顺序/重复源读取后紧跟
indexed-load覆盖同源组的定向场景。797项LDU的
`vinsn_issue_d/q.hazard_wait_complete[0:7]`及队列相关字段尚未命中；
新场景要求严格架构/VRF/source/guards/CSR比较和相对797 OR的实际
bitmap差集证据。只有功能PASS而无新增命中不能称为覆盖闭环。
当前正在构造准备，尚未仿真、尚未新增入797项。

`current-population797-masku-zero3-prepared-agent-20261008-01`已完成：
service inactive、MainPID0、ExecMainStatus0；原生终端rc0且无超时。
qualification SHA为
`9db76c7b52ba428dba02057575bd68cf1ae4c2d25340bd1e00e5025a1ec5b771`。
父端独立核对17个输出哈希、config/source-map绑定、精确有序唯一的
797项测试和73scope六指标五阶段。raw/reset/final一致且等于原797
raw，applied/reloaded一致；Line/FSM/Condition/Branch全scope不变。

| 指标 | 原始 | 精确豁免后 |
| --- | ---: | ---: |
| Line | 85.45% | 85.43% |
| Condition | 82.30% | 82.31% |
| Branch | 83.25% | 84.03% |
| FSM | 70.68% | 81.09% |
| Toggle | 65.49% | 73.18% |

范围为`ara_tb.dut.i_ara_soc.i_system`。沿用全部原EL，仅追加已严格
局部验收的MaskU三个恒零字段，768 physical bits/1536 directions，
984个其他局部对象保护。Toggle提高0.04个百分点，距80%差6.82。
这是精确豁免带来的分母变化，不是新增激励命中；C910/QBS/cause60
候选均未计入。仍是冻结旧RTL镜像的历史PASS集合，官方Covered/Total
未单独核实，不代表最新RTL signoff，不由序列化位数反推分母。

## 局部候选与本轮验收记录

MaskU整体报告已经生成73个scope的六指标五阶段CSV。父端独立解析
全部阶段：raw/reset/final与原797项raw完全一致；applied/reloaded
完全一致；所有scope的Line/FSM/Condition/Branch均不变。
仅`ara_tb`、`i_system`、`i_ara`的Score/Toggle有变化。
`i_system`应用后Toggle显示73.18%，原为73.14%；随后worker最终
qualification、原生终端和完整输出哈希均已验收，见顶部正式报告。
此增量来自1536方向的精确豁免，不是新增激励命中。

C910 fresh03真实DVE已结束，native returncode0、timeout=false，但
`error.txt`明确记录before阶段`Full117 bit complement`失败；父端
读取`bits_before_0.tsv`仅有表头，没有任何逐位数据。因此DVE进程
退出0不构成资格通过，1424方向仍HOLD，不汇入覆盖率。
已安排仅依据实际导出与安装API帮助分析展开/视图行为，不猜方向或
放宽完整性检查。QBS及cause60涉及同类partial API，暂不启动，
先完成接口证据闭合；冻结失败包和日志完整保留，不盲目重试。
随后service正式终止：`MainPID=0`、`ActiveState=failed`、
`ExecMainStatus=1`，与局部资格拒绝一致。禁止依据native进程rc0
覆盖该验收失败。父端确认`csr_rows`三元组索引本身无明显错位；
当前数据不足以判定double-click后的实际bit视图。
下一步只读诊断须在同一scope/同一PASS sample保存初始和每次点击
之后的全部path/meta/name及列，不先用正则过滤，区分全局压缩切换
与不同逐位标签/视图。先审阅方案再单次运行，不导入EL、不改RTL。

父端已完整阅读QBS7612与cause60的局部native核心及启动脚本。
QBS现有准备02的启动器仍含`--collect`，且precheck在错误留存范围外；
因此未批准启动，要求独立后继补持久service日志、双解释器检查和
precheck终端留存，保留冻结02。cause60亦需核查完整import环境和
双解释器检查后再授权；不因准备包主机测试通过就宣称native成功。

AXI错误slave候选的父端13项离线测试实际通过（10.021秒）。父端
核对upsizer错误slave实例、demux输入别名、err_slave全部R写者和
ATOP过滤器注入路径：直接错误数据为固定值，过滤器输出则可能在
`64'hCA11AB1EBADCAB1E`与零之间变化。后者低64位的34个pattern-one
位全部保护；仅高64位和30个pattern-zero位进入候选。七处别名共
1452个候选方向槽，仍非官方分母、未作native资格或整体增益声明。

797项加MaskU三个恒零字段的整体报告已提交至
`ara-current-population797-masku-zero3-parent-20261008-01.service`。
父端完整只读check返回0，准备包11项主机测试通过；配置SHA为
`170c663a862aa530540f186eb1d04101d4b14046647cf14e5a894a5ab8343e1b`。
本次保留全部797项成员及原EL，只追加已局部验收的三个字段。
提交时尚未完成整体验收；现已通过，顶部报告为正式结果。

C910输入填充位使用独立最终fresh03准备包，配置SHA为
`54333111b2206676dbeadea33de7e2840b2db6d01a1f2c0ece0e7b36c13e1265`。
父端核对handoff04的32个文件哈希及26项测试、prepare和双解释器
check的通过记录，随后执行唯一launch-reviewed启动检查。
原失败包及开发中准备包均保留且不重启；启动提交不等于native验收，
只有逐位保护、五阶段保存/重载全部通过后才可考虑整体汇入。

两项任务均已实际进入DVE：MaskU整体报告native PID1414726，
C910局部native PID1414609，后者所属服务为
`c9101424-local-6b69c59e61073c545845.service`。
父端核对两个进程的`/proc`可执行文件、工作目录及精确service cgroup，
不是仅依据提交记录或状态文件宣称运行。两任务独立后台进行，
不重新仿真，不更改RTL，不频繁轮询；后续终端状态分别见上述
MaskU正式验收和C910局部拒绝记录，不能继续声称两路仍在运行。

## 上一轮已验收整体报告（797项，未含MaskU新增豁免）

`current-population797-inherited796-agent-20261008-01`整体任务已完成，
systemd服务inactive、ExecMainStatus0，实际DVE returncode0且未超时。
qualification SHA为
`1ebc05103bc71ee6ec26d97e51ed4867fed3d35a21ee38490956c3ccadf2c5c6`。
父端独立核对精确797个有序且唯一的原生测试、source-map及17个输出
哈希，并解析73个scope六指标五阶段：raw/reset/final完全一致，
applied/reloaded完全一致。本轮严格沿用796项EL，没有增加豁免。

| 指标 | 原始 | 精确豁免后 |
| --- | ---: | ---: |
| Line | 85.45% | 85.43% |
| Condition | 82.30% | 82.31% |
| Branch | 83.25% | 84.03% |
| FSM | 70.68% | 81.09% |
| Toggle | 65.49% | 73.14% |

统计范围为`ara_tb.dut.i_ara_soc.i_system`。相对796项，沿用原EL后的
Toggle提高0.13个百分点；FSM已达到80%，Toggle仍差6.86个百分点。
MaskU局部资格虽已通过，尚未应用至本报告；其它候选亦未计入。
仍是冻结旧RTL镜像的历史功能PASS集合，official denominator未核实，
不是最新RTL的signoff，不从序列化方向数反推官方Covered/Total。

## 上一轮已验收整体报告（796项）

`current-population796-alua137-ptw156-agent-20261008-01`的DVE已退出0且无超时。
qualification SHA为
`f439bae9092c0a787ee8fb8177ee33277e6ec25f61ef0c198f5a8dce50807270`。
父端独立核对17个输出文件哈希、796个原生测试的精确有序成员，以及
73个scope的六指标五阶段等式：raw/reset/final一致，applied/reloaded一致。
统计范围为`ara_tb.dut.i_ara_soc.i_system`，不是整个testbench。
随后父端通过独立systemd任务完整重放verify，服务退出0；资格文件SHA
仍为上述值，未重跑DVE。任务为
`ara-coverage796-offline-verify-parent-20261008-01.service`。

| 指标 | 原始 | 精确豁免后 |
| --- | ---: | ---: |
| Line | 85.44% | 85.42% |
| Condition | 82.27% | 82.28% |
| Branch | 83.25% | 84.03% |
| FSM | 70.68% | 81.09% |
| Toggle | 65.39% | 73.01% |

本轮增加已严格准入的AKV别名测试，以及ALUA137分支和PTW156 Toggle
精确豁免。相对795项，豁免后Branch提高0.12个百分点，Toggle提高
0.02个百分点；FSM已达到80%，Toggle仍差6.99个百分点。未完成验收的
FP64和VSMUL候选未计入。仍是冻结RTL镜像的历史功能PASS集合，
`official_denominator_verified=false`，不代替最新RTL的signoff。

## 上一轮已验收整体报告（795项）

### Scoreboard异常原因高位源码闭合

旧镜像原始dispatcher已从独立封存源码恢复证据，父端实际SHA核对为
`9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43`，
不是用当前不同版本的dispatcher替代编译证据。源码审查将此前ACC
整字段透传的HOLD推进为源码已闭合：normal/MMU/store-B/QBS/AKV的
cause生产者及scoreboard reset/hold/copy链均纳入范围。
仅固定配置的`cause[62:6]`，每副本57位；共60处不同物理副本，候选
6840个双方向槽。低6位、bit63、FPU flags及软件全64位可写的
`mcause/scause`均保护，不豁免整个exception结构。
父端另检查scoreboard不仅在ex.valid时复制异常，还在FPU路径复制
无valid的fflags，故不能用valid-only逻辑论证高位未用。
14-copy准备包仍保持冻结；已安排独立60-copy后继准备与负向测试。
完整native身份、逐位豁免与保存/重载尚未验收，不计作覆盖率增益。

### C910 FP16输入填充位1424方向资格检查

独立v3保留完整normal/denormal/remainder写者检查，修复准备文件的
tuple/list序列化比较，不放宽源码证明。父端实际执行v3与launcher共
24项测试全部通过（168.917秒），真实launcher check通过；随后唯一
launch-reviewed正常退出0，提交
`c9101424-local-680d1d33f01dc9c6c1b5.service`。
配置seal为
`c07b18d0bf51279413c0e56930788a03ae65b314c50f94128b57602931187675`。
仅候选8个FP16子lane的initial_divisor/remainder输入填充位，合计1424
Toggle方向；不豁免迭代运算位、输出、控制或整个功能单元。
native逐位查询及保存/重载仍待实际验收，不能依据24项主机测试宣称
豁免已生效；不纳入已启动的797项整体报告。

后续父端核查发现worker1390232已不存在，`--collect`服务亦已卸载；
目录未生成execution/terminal/worker-error/launcher.log，宿主journal
当前用户不可读。因此仅能确认提交成功，不能确认native实际开始，
更不能确认成功或推断失败根因。已安排只读排查启动前检查和记录缺口，
不重新启动、不计入豁免；后继需要在prepare/check之前也留存错误，
并将服务stdout/stderr保存至独立文件，避免无终端证据的退出。

只读复现已定位具体precheck差异：prepare时selection使用
`/usr/bin/python3`，systemd worker使用解析后的`/usr/bin/python3.9`；
check依赖当前sys.executable重建selection，因此字节比较报
`Exact native driver`。worker同解释器实际只读check返回1，旧包24个
pins均无漂移。不能从此推断native向量位API不支持，它尚未执行。
已安排独立后继固定解释器路径、补父子解释器一致性测试和precheck
错误留存，不改原冻结失败包，不盲目重启。

### MaskU三个字段局部native验收通过

实际服务已正常退出0，terminal returncode0/timeoutfalse；父端重放
strict inspect正常返回0。capture-result SHA为
`8135f4886498ec0fdb2f0d83573058fc74f8f8c86d49f460ca65481c2441fc27`。
三个字段768物理位、984保护对象、987完整对象的五阶段身份/豁免
保存重载及清理检查通过；清理EL为空，初始X不豁免。仍为局部资格，
未应用至整体797报告，不能将1536方向直接换算成全局百分比。

精确797集合并集准备包已完成父端检查：
`masku-zero3-union797-prepared-agent-20261008-01`，seal为
`fb995f4d46fa436b89407fa80ef9447db371d82e07b8ceee2bdc0e952d73053e`。
父端实际11项负向/并集测试通过（34.700秒），完整check返回0。
旧796完整EL字节前缀保留，三个新对象无既有EL重叠，797新增样本
及全集合目标raw位均为0；保留984其它对象。准备包本身不启动EDA，
最终整体报告后继需绑定已完成797 qualification后再运行验收。

### 最新正式增量：VSMUL准入797项

父端完整阅读runner/collector及负向测试后实际执行16项测试全部通过
（41.867秒），冻结prepare verify通过。单次宿主VCS实际运行110.981秒，
退出0、未超时；随后父端完整collect正常退出0，不是仅凭退出码判断PASS。
资格文件为`vsmul-saturation796-qualified-parent-20261008-01/qualification.json`，
SHA为`a1894829082271554496c996d487152156b56e06c17e352d22265137da7fc7c2`。
完整匹配18927条指令、10802次GPR写和884次标量访存；48个向量writer的
4992个主写字节，以及reshuffle的128个身份保持字节均独立检查。另核对
36次全寄存器快照、1272项检查、72项CSR及输入/尾部/保护区。
相对正式796项，全2989实例Toggle OR实测新增122方向，其中饱和目标
新增114方向；全6162指标实例OR另新增Line14、Condition61，Branch/FSM
无新增。父端随后实际执行准入工具12项测试全部通过（97.121秒），
显式授权独立发布任务，正常退出0。正式目录为
`vsmul-saturation-offline-admitted797-parent-20261008-01`；admission manifest
SHA为`775485fa0a5cfbb8bb1715374e60d3228d341522b2df3c666754407b30ef55f4`。
父端独立复核34个输出哈希、唯一797项集合与精确796前缀；另逐实例
重算6162个指标及2989个Toggle并集，新增122方向严格一致。797项
整体DVE百分比仍待独立汇总，不将原始方向增量直接换算为官方百分比。
运行目录为`vsmul-saturation796-vcs-prepared-agent-20261008-01`。

797项独立整体报告已完成prepare；父端实际执行13项工具测试全部通过
（220.295秒），完整check通过。随后启动唯一后台服务
`ara-current-population797-inherited796-parent-20261008-01.service`，
worker PID1386145已从实际进程核对。报告目录为
`current-population797-inherited796-agent-20261008-01`，config SHA为
`4145a211520006ec00b04c6ba18ffdf1acdd700bf761774c0fad69bc523a1fc0`。
本次严格沿用已验收796项EL，不包含尚未验收的MaskU/C910/QBS候选。
完整797有序集合、72模块根和五阶段的最终结果仍待运行验收。

DVE随后实际terminal returncode0/timeoutfalse；父端独立解析五份
modules CSV，73个唯一scope、六指标的raw/reset/final和
applied/reloaded分别完全一致。i_system新表原始Line85.45%、
Condition82.30%、Branch83.25%、FSM70.68%、Toggle65.49%；沿用原EL
后Line85.43%、Condition82.31%、Branch84.03%、FSM81.09%、
Toggle73.14%。这是实际DVE表值，不根据122原始方向推算；完整
qualification仍在收尾，暂不替换首部已验收796项结果。

### 历史795项验收

### 下一轮源码驱动缺口审查

父端检查正式796残余位图与冻结源码：`masku_operands`的
`VlBitMaskEnable`为局部参数0（源码第26行），`deshuffled_vl_bit_mask`、
`shuffled_vl_bit_mask`和`bit_enable_mask_o`在组合逻辑中初始化为0，
禁用分支继续置0。三者各有512个未命中方向，共1536方向。
当前源码SHA与旧镜像build-source-pins一致；实际rank SHA为
`b82696123a3510191bbc106d3a6b8fbb4d2dadeedf6b5d8e5e8f8b1d39274346`。
这不是增加随机case可解决的路径。仅作为精确恒零候选，编译实例、
typed物理位和nativeEL保存/重载资格仍待完成，不计作覆盖增益。
其他MaskU字段保持保护。另并行审查QBS双缓冲数据位和FP16除法/
开方填充位，先确定实际可达性再构造激励，不依据残余总数预测收益。

父端在native运行前发现MaskU v1的EL解析假设过严：要求三个对象各自
重复checksum/instance头，实际已有PTW的DVE导出却会合并同scope头，
并移动ANNOTATION。原v1未运行EDA，保留冻结版本；独立后继应接受
精确同scope/checksum的合法分组和注释重排，同时拒绝额外/缺失/重复
对象、部分位、错误注释和其它metric。没有因此放宽功能覆盖准入。

独立v2已通过父端实际24项测试（8.174秒）和verify-config；单次900秒
宿主launcher另通过12项测试（0.230秒），启动清单完整校验通过。
父端启动`ara-masku-zero3-native796-v2-parent-20261008-01.service`，
worker PID为1380130；实际DVE PID1380441的exe、cwd和cgroup已独立
核对一致。启动清单SHA为
`214e3834edbc0b01756b894c8873d61cef78f30fa537a1e87a4a638c7fd3a873`。
仅验证三个恒零字段的1536方向及受保护补集，不修改RTL、不重新仿真、
不自动重试、不应用至整体集合。最终native保存/重载结果仍待验收；
不能将启动成功或模型测试通过当成实际豁免资格或覆盖率提升。

QBS payload双缓冲残余审查发现，有效输入和selection的低8位数据，
每bank共8192个逻辑位，在796原始位图中均无缺失；SRAM wrapper数据
亦无缺口。不能将buffer整体残余归因于随机数据不足。剩余selection
主要是第8位命中有效位；候选映射不可达4112位置和side立即consumed
路径3500位置仍须完整源码/typed/EL资格，未豁免、未计增益。原审查
以sealed766并集加30个sample重算，与796两bank位图一致；不冒充
重新审计全部796个样本。小型跨word pending新刺激仅有8个候选位置，
暂不安排低收益重复仿真。

QBS精确control-zero packet后继02已由父端完整阅读检查器后实际执行
38项测试全部通过（64.502秒），并完整重算验证返回0、7612候选方向
一致。packet SHA为
`eaba18abb4b3cd12500b6a6ff49021e3ae2573fc93e26ba0694b1355f986fd84`。
4112映射不可达及3500 side立即消费候选互不重叠，已扣796现有EL；
weight高half/NativeView0缺精确compiled binary身份仍HOLD。
安排独立native后继及797新增样本反例核对，不将796准备包改名冒充797，
不因主机测试通过宣称已应用豁免或全局覆盖率提高。

`current-population795-pmp816-agent-20261008-01`已正常结束，服务退出0，
DVE退出0且无超时。父端完整verify重放正常退出0，qualification SHA为
`43b1c922c2561daa5d5e8cb51e30e471bb8d0eaa137d90ad10c63b55cf5257a5`。
另独立核对17个输出pins、795个实际原生测试的精确有序成员，以及
73个scope的六指标五阶段报告：raw/reset/final一致，applied/reloaded一致。
该报告集合包含正式DIV795及PMP816精确并集，不包含随后准入的AKV别名测试、
PTW156或ALU-A137候选。仍是冻结RTL镜像的历史功能PASS证据；
`official_denominator_verified=false`，不冒充其它RTL的signoff。

| 指标 | 原始 | 精确豁免后 |
| --- | ---: | ---: |
| Line | 85.44% | 85.42% |
| Condition | 82.27% | 82.28% |
| Branch | 83.25% | 83.91% |
| FSM | 70.68% | 81.09% |
| Toggle | 65.38% | 72.99% |

相对794项，原始Toggle提高0.02个百分点，豁免后提高0.07个百分点；
原始Line提高0.16个百分点、Branch提高0.18个百分点。
FSM达到80%，Toggle距80%仍差7.01个百分点，目标未完成。

### 后续增量状态

AKV别名测试相对实际795项独立重算仍新增274个Toggle方向，分布于
14个实例。准入JSON后继工具的19项测试由父端实际执行全部通过
（1.382秒）；完整prepare和显式授权admit均正常退出0，正式集合增至
796项。目录为`akv-canonical-alias-offline-admitted796-parent-20261008-01`，
prepared seal为
`44c970e1b529c0d596b522f29c4ce3eb7d49b69aee9bc1f84211c9cb0d411159`，
admission seal为
`1aa18b04d4b1f3a4a2d8182c0457e240f43e0538bbeabe1b0385724e5a56400d`。
父端独立复核33个输出pins、精确795前缀和796项唯一集合，完整2989
实例原始OR及274个增量方向一致。准入保留完整6162个非Toggle指标
实例。随后796项整体DVE独立执行并完成验收，见本文首部新报告；
以下记录保留各候选当时的状态，不代替最新验收结果。

正常FP64 DIV/SQRT激励224组的软件预检已冻结，通过Spike11810条
指令、4286次标量访存和675项检查。父端实际执行13项测试全部通过
（4.698秒）；整数独立gold覆盖结果/flags/FCSR、平方根邻值及有效
舍入模式，不用宿主浮点结果充当gold。VCS已正常结束，耗时92.121秒、
退出0且无超时；尚未通过完整收集验收，不计入覆盖率。

PTW RVH=0输出156方向的局部资格工具，父端完整阅读后实际执行
14项测试全部通过（10.234秒），完整check通过。独立原生DVE服务
`ara-ptw-rvh0-outputs156-parent-20261008-01.service`已启动，父端直接
确认worker1133747和DVE1133983运行。其配置seal为
`e9441de43157a0afd9074205e9f9b88925a0c2cc9fd4b4ed5dff42a050471830`。
仅核验12个组合恒零输出，保护137个其他typed对象；尚未应用全局。
该次原生任务随后退出1：DVE保存`first.el`时把唯一ANNOTATION移至
11个Toggle条目之后、最后一个目标之前；12个精确字段/checksum/scope
正确，Python门禁却要求ANNOTATION先于所有Toggle，故拒绝并清理EL。
不是RTL失败或完整五阶段PASS。原失败、native before/applied及first.el
全部保留。正准备仅接受同scope中唯一精确注释重排的独立后继，仍拒绝
缺失/错误/重复注释或其他字段；完整五阶段须重新资格，不能离线伪补。

FP64运行工具、896个请求owner及只读selector探针由父端完整阅读，
16项运行/收集器测试实际全部通过（2.647秒），包括SQRT未使用B的
未知值处理、使用中输入未知值拒绝、flush取消重发、持有稳定性、错误
结果/flags/TID拒绝及真实Tcl路径。原生运行prepare seal为
`360726d7b8698e04a151e24ee266642b111b079362b98ec602698dcfb818c3fe`；
父端完整verify通过后授权单次600秒VCS运行，实际92.121秒结束。
完整collect已执行但退出1：重用收集函数访问`runner.reused`，正常数
runner未导出该接口。失败目录`scalar-c910-pattern795-qualified-parent-20261008-01`
及架构检查产物保留；这是收集工具接口缺失，不是已确认的RTL故障。
正在审计完整依赖并准备独立后继收集器，复用原VPD/VDB，不重跑VCS，
不跳过完整架构/owner/flags检查，不提前准入。
独立API后继由父端完整阅读后实际7项测试通过（0.304秒），完整collect
已执行至VPD转换后的owner波形门禁，再次拒绝于
`Flush cannot lose accepted or held output owner`。新失败与原VCD保留在
`scalar-c910-pattern795-qualified-v2-parent-20261008-01`。架构对比完整
通过11810条retire、6104次标量写、672次浮点写、4286次标量访存及
224组结果/flags/FCSR、675项检查；这不能代替owner波形门禁。
正在基于同一VCD诊断首拒绝edge的live/pending、flush及握手/输出次序，
未判定RTL故障，未放宽门禁，未重跑VCS，也未计入覆盖率。
首拒绝证据已定位到time=51095000：live仅有第二条FMV_X2F，
PC=0x800021dc、TID=0，accepted=true；pending/scheduled为空。
同沿flush=1、out_valid=1、out_tid=0、result=0x3ff0155555555555，
与owner独立gold严格一致；下一沿out_valid清零，完整退休记录亦匹配。
冻结fpu_wrap固定out_ready=1，因此该同沿输出应先被严格消费，再检查
flush后是否仍有未完成owner。原checker先进入flush分支，误把尚未从
live移除的已完成请求视为丢失。正在准备独立事件顺序后继；仅允许原
complete_output通过后消费，不取消真实live/held owner，不放过错误
TID/result/flags，不改变RTL，不重新仿真。
首拒绝诊断为`scalar-c910-pattern795-first-flush-agent-20261008-01.json`，
SHA为`0754a4ac4af9614e9426e5d51762b7091a3eedca1b2ffc2e26fc6bcb92ccc711`。
父端另独立核验796正式manifest所绑定的完整2989实例Toggle并集，
以本次原生`tgl.verilog.data.xml`比较，相容的原始OR仅新增10方向：
SRT 4、迭代SRT 4、ROUND 2。sample SHA为
`819fd223358580b25ad5c1068e15e4e2a8a455fdb9b5cab443da72f0b455575a`。
这是原始位图诊断，不是功能准入或官方百分比；静态90个可变候选
不得当作实测新增90方向。完成本case后不再盲目扩展类似正常selector
测试，优先转向正式796剩余可达缺口。
同沿输出独立后继`collect_scalar_c910_pattern795_v3.py`由父端完整
阅读，46项测试实际通过（7.506秒），含错误TID/result/flags、未知字段、
无输出但有live、额外accepted owner、held owner及缺少重发拒绝。
实际完整collect继续拒绝于`Independent compiled PC/issue TID`；
失败和转换波形保留于`scalar-c910-pattern795-qualified-v3-parent-20261008-01`。
本项继续HOLD。后续先对同一VCD完整梳理剩余issue/flush事件及源时序，
不逐门禁盲目放宽，不重复VCS，不因架构PASS单独越过已承诺的波形门禁。
独立源码与原VCD复核进一步修正首拒绝解释：writeback完成不等于
架构退休，scoreboard清除优先于同沿writeback。time=51165000实际
重发第一条FMV（PC=0x800021d8、issue/FU TID均0），原checker却因
先前物理输出推进了退休参考游标而期待DIV（PC=0x800021e0）。
因此不是同沿PC/TID不匹配。此前“退休记录确认完成”只说明相同PC/
结果后来确实退休，不能证明flush前那次物理输出已经退休。
branch mispredict还可仅通过scoreboard cancelled处理，不伴随FPU
flush_i；现有探针缺branch-resolution/cancel/commit-ack，不能宣称
所有额外请求均已安全取消。六份相关源码与冻结build一致。
继续HOLD，不增加仿真。后续通用checker需要分离物理请求生命周期
与架构退休gold；当前仅10方向增益不足以为此追加新探针长仿真。

ALU-A137精确Branch豁免工具由父端实际执行8项测试全部通过
（23.583秒）。目标137点、保护267点，仍需原生五阶段资格和全局
应用验收；工具测试通过不是整体覆盖率增益。
父端完整check通过后启动独立服务
`ara-alua-group5-native137-parent-20261008-01.service`；实际DVE进程
1145945的exe、cwd、参数及cgroup均直接核对一致，未只依据状态文件。

PTW注释顺序独立后继`ptw_rvh0_outputs156_local_v2.py`由父端完整
阅读，实际8项测试通过（0.111秒），完整check通过。仅将同一checksum/
instance中的唯一精确ANNOTATION移回规范位置，缺失、重复、错误注释、
异scope/字段/位宽/单方向仍拒绝。原失败产物和旧helper保持不变。
新配置seal为
`250fb9ba8ce5159cb2c25b4f8846009f1b87cbddcc1837bd95b1435160d2926c`；
已启动`ara-ptw-rvh0-outputs156-v2-parent-20261008-01.service`，等待完整
五阶段结果，不把重排通过误称为全局应用或覆盖率提高。
实际DVE1147050的进程参数、cwd、service cgroup均由父端直接核对。
两项原生服务随后均正常结束、退出0。父端分别重新运行完整verify：
ALU返回`ALUA_GROUP5_BRANCH137_NATIVE_QUALIFIED_NOT_APPLIED`，
PTW返回`verify_PASS`。ALU完整404个Branch点五阶段验证，目标137、
保护267，before/reset/final一致且selected/reloaded一致；不是整个ALU
或功能单元豁免。PTW12字段156方向的EL保存/加载及源恒零资格完成，
但五阶段TSV文本完全相同，不能称作观察到了GUI排除标志变化。
两项尚未应用正式796集合；下一整体报告必须独立验证精确EL并集、
新AKV测试的零命中/补集保护、完整membership与apply/reset/reload效果，
不得将局部资格退出0当作全局百分比证明。
正式796并集后继`report_population796_alua_ptw.py`由父端完整阅读，
实际12项回归通过（73.501秒），独立完整check正常退出0。
配置位于`current-population796-alua137-ptw156-agent-20261008-01`，
seal为`062daf585d00ef170942b36f5a631dee7f4676af32fcbb4e5d8af86a8159badf`。
完整保留795政策，只增加137个ALU Branch向量及156个PTW Toggle方向；
对实际796全部数据及新增AKV单项重放目标零命中与补集保护。
父端已授权并启动同名`ara-current-population796-alua137-ptw156-agent-20261008-01.service`。
实际worker1165001的参数、cwd及cgroup直接核对，处于启动复核阶段。
工具DVE预算3600秒，服务上限4500秒覆盖前后核验；不自动重试。
仍待完整原生五阶段终态，不宣称DVE已启动或提前更新顶部百分比。
随后实际DVE1166774已启动；父端直接核对exe、cwd、命令及cgroup
与sealed服务一致，进程在运行。仅确认启动，不频繁轮询，不提前报分数。

### 新的真实激励：四EEW VSMUL饱和/恢复

基于正式796剩余零坐标选择`vsmul_saturation796`：EEW8/16/32/64，
各执行min*min饱和、非饱和RNU舍入、零恢复，共12条VSMUL；每条
覆盖四Lane各一个完整64-bit packet。完整定义两源128-byte寄存器，
结果仅改活动32 bytes并严格保留96-byte tail，逐条保存源/目的/guards
及VL/vtype/vstart/vcsr/fcsr。独立整数gold与Spike1272项检查通过，
18927条retire、4608 snapshot bytes、72 CSR，ELF去重通过。
父端完整阅读源码/preflight/tests，实际11项测试全部通过（17.138秒）。
preflight目录为`vsmul-saturation796-preflight-agent-20261008-03`，
seal为`f8661178864094e49c6d5d83a45f11e1361fb524d0ec01d7ef628cdff115b3da`。
simd_mul/ara_sequencer/ara_pkg实际读取源码SHA均由父端独立确认
匹配冻结build，暂无版本混用；运行配置需绑定这些源防后续漂移。
目标为15个实例`input_sat`的114个未排除serialized零坐标；不猜原生
方向ID，不把预测容量当实际新增。剩余8个AluA default-EEW保护点
继续HOLD。尚未启动VCS或准入，等待运行/收集工具完整验收。

QBS FMA对齐候选的软件预检已封存为
`qbs-fma-align796-preflight-closure-agent-20261008-01.json`，
seal为`d24639ee5efbe742fe444b3329721690fc33a80acbe72037448825a37df6d032`。
该封存是软件参考路径，不是custom-native PASS：155000条退休、
6705项检查、32个FP站点、16384字节VRF快照和12条CSR记录。
原checker把结构数组元素stride误写为4224，实际ELF四元素共16512
bytes、stride4128；独立后继仅据ELF修正读取步长，原03产物不变。
正式796仅剩10个host见证位置，不是已测RTL增量。因此暂不启动
该高指令数低预测增益native仿真，保留全部预检证据，资源优先投入
VSMUL及全局可达缺口排序。不得把host位、padding源证明或软件
预检当作原生Toggle命中/资格；未计入整体报告。

后续整体汇总按批次执行：先完成定向测试的功能资格和精确豁免资格，
再将正式准入的新测试与新EL合入一轮整体DVE报告。每个单项通过后
只更新其原始OR及资格证据，不立即重复生成全部层级报告；失败/HOLD
不入集合，也不借批次汇总将其掩盖。

## 前一份已验收报告（794项历史证据）

`current-population794-soc61-parent-20261008-01`已正常结束，服务退出0，
DVE退出0且无超时。qualification SHA为
`fce23ff83487b83e51c069863710f4fad0c11716070ed3d4327aa57470972007`。
父端独立核对17个输出哈希、794项实际membership、配置与资格pins一致、
完整EL掩码及保护门禁；实际CSV各阶段为72个配置scope加ara_tb共73行，
六指标raw/reset/final一致、applied/reloaded一致且scope集合精确匹配。
该报告包含ITLB增量和61个SoC常量字段的精确EL，不包含新PMP816 EL
或随后DIV测试。仍为冻结镜像的历史验证证据，不冒充其它RTL的signoff。

| 指标 | 原始 | 精确豁免后 |
| --- | ---: | ---: |
| Line | 85.28% | 85.25% |
| Condition | 82.27% | 82.28% |
| Branch | 83.07% | 83.72% |
| FSM | 70.68% | 81.09% |
| Toggle | 65.36% | 72.92% |

相对793项报告，原始Toggle提高0.02个百分点，豁免后提高0.21个百分点。
FSM已达到80%，Toggle距80%还差7.08个百分点，目标未完成。
PMP816的局部原生资格已成立，未应用全局，不预估其全局百分点。

### DIV完整资格与795项正式准入已通过

已基于原VCD定位首个拒绝点：time=35825000，前条FCSR写触发flush，
当时live为空、pending为空，只有下一条尚未成为存活owner的FMV请求被取消。
该edge实际in_valid=in_ready=1，但FFLARNC的flush清除优先于load，
不能将有效/就绪同时为1误称为“没有握手”。该请求随后重发并正常完成；
不是已确认的RTL故障。独立后继检查器
`scalar_div_subnormal794_flush_v2.py`仅允许这种flush优先取消，并要求
精确PC/操作数/TID匹配、注册valid清除以及后续重发；已接受或保持中的
owner被flush仍拒绝，不能通过跳过输出来放行。

父端实际执行`test_scalar_div_subnormal794_flush_v2.py`共35项测试，
全部通过（3.435秒，含导入的原Native测试）。实际波形完整确认576个
owner输出、144次DIV的流水/数值/flags，以及143次取消后重发。
原失败目录和冻结collector均保留，RTL未改、VCS未重跑。
随后父端阅读独立完整collector后继，实际执行8项测试全部通过（0.383秒），
并使用原仿真产物执行完整collect，正常退出0。资格目录为
`scalar-div-subnormal794-qualified-v2-parent-20261008-01`，qualification SHA为
`6dc6a89afce6346a52b52647ca43b8eb6a3a4d2d012655bcce3739e72f0bf2ef`。
父端独立复核334个输入pins和10个输出pins全部通过。
完整10013条指令、6450次GPR写、432次FPR写和1181次标量访存与Spike一致，
skipped=0、mismatch=null；144次DIV逐项结果/fflags/FCSR、436项签名检查、
FCSR恢复和guards均通过。

相对正式794项集合，全模块原始OR实测新增654个Toggle方向、177个行点、
15个条件点、184个分支点、0个FSM点。654是系统整体增量，不是先前7个
目标字段的580方向候选容量，二者不能混同。集合准入和新全局DVE汇总
不能将此原始增量外推上表百分比。随后795项正式准入已完成，但795项
全局DVE报告尚未生成，文首794项仍是最新整体百分比。

### 当前增量准备与后台任务

父端实际执行795项DIV准入工具的10项测试全部通过（2.411秒），并独立
重算2989实例的原始序列化Toggle增量，精确匹配654个新增方向。
正式prepare通过，prepared seal为
`fdd8d3edc128e8520d91b96aa7e15909461adc18658ecd97e8fb82d505626e34`。
父端执行带显式授权的admit并完整重放验收，正常退出0。正式795项目录为
`scalar-div-subnormal-offline-admitted795-parent-20261008-01`，manifest SHA为
`4d13a15758c65791a43798467bb63c516d0747d631f6fede476eb63202001660`。
794项全局报告不因此自动成为795项报告。

PMP816精确并集工具由父端完整阅读，实际10项测试全部通过（144.718秒）。
其并集保留794项报告的全部既有EL，新增2176个方向无物理位重叠，
13个MDA继续不豁免。父端独立handoff已准备成功，目录
`pmp816-global794-handoff-parent-20261008-01`，seal为
`401c57fd7e6fc3bd85c2d53bec197522dc39297823093f9c5901d1f8b1103da9`。
完整既有EL逐字保留，30855个输入pins，未启动整体EDA或产生新百分比。
父端实际执行整体794/PMP报告工具的10项测试全部通过（69.660秒），
独立静态审查未发现阻塞问题。为避免重复DVE汇总，794/PMP候选报告
不启动EDA；独立795项后继已由父端实际执行11项测试通过（22.368秒），
完整check通过。将已正式准入DIV与PMP精确并集放入同一轮完整报告。
目录为`current-population795-pmp816-agent-20261008-01`，配置SHA为
`e5914b638b926b7e983ab60187d94bfbc7623db88bbdca40d82faf0b340029c9`。
服务`ara-current-population795-pmp816-parent-20261008-01.service`已启动，
父端直接确认真实DVE进程1120762的可执行文件、工作目录、cgroup及
运行状态，CPU正在消耗；尚未生成完成资格，不提前报告新的百分比。
该决定不改变已封存794报告或其冻结工具。

AKV Sv39规范虚拟地址别名激励的父端19项runtime工具测试全部通过
（30.833秒），独立prepare和verify通过。准备seal为
`f777d171de39027b9d0b7fdd4b7fd88f2c3ad5438a27e9f79eb9cbcde0c62de1`，
273个pins；独立native模型116614步，不把自定义指令软件模型称为Spike。
真实DUT检查包括10个命令、4次全VRF快照、两个S态ecall及接受的MMU
VA/PA到AXI AR捕获。只读探针，不force、不改RTL。

后台服务`ara-akv-canonical-alias794-parent-20261008-01.service`使用独立目录
`akv-canonical-alias794-old-image-parent-20261008-01`，worker1099456及实际
simv1099619的exe/cwd/cgroup/命令已由父端直接核验；提交日志已开始增长。
单次900秒预算，无自动重试，不频繁轮询。此处是启动证据，不是功能PASS；
只有完整终态、架构/VRF/协议/周期级检查通过后才可重基最新集合准入。
该服务随后正常结束：ExecMainStatus=0，仿真returncode=0、timeout=false，
VCS CPU452.030秒。完整collector已实际执行，原失败记录保留在
`akv-canonical-alias794-qualified-parent-20261008-01/failure.json`，未准入。
首差为Retirement32191，PC=2147493212，insn=805315955，读取mstatus：
模型0x0000000a00006600，RTL0x8000000a00006600，仅SD bit63不同。
冻结`csr_regfile.sv`在1996行按XS/FS/VS Dirty派生SD；新case的模型
写mstatus时仅保存写值，未重新派生SD。这是参考模型错误的明确假设，
独立SD后继的14项测试已由父端实际执行全部通过（11.564秒），包括
完整116614步回放及故意破坏SD、访存、flags、两个ecall记录的拒绝测试。
完整资格收集已正常退出0，目录为
`akv-canonical-alias794-qualified-sd-v2-parent-20261008-01`。
核心资格SHA为
`bb545552788a04cdabc841f7b6b8550679e7084f49d89e5bfb59f426afec5d9b`，
后继receipt SHA为
`8404d026f11a631e83e836a3295f28974749da41ef9f1d37dbffd0d73a064134`。
父端独立检查核心291个输入pins、16个输出pins、后继310个输入pins
全部通过。完整116614条指令、70418次GPR写逐条匹配，无跳过；
10个命令、4次全VRF快照、两个精确S态ecall及8个接受的地址转换/AR
通过。相对794项原始集合新增274个Toggle方向，其中目标AKV字段240个，
Line/Condition/Branch/FSM无新增。该增量仍需针对795项去重重算。
已开始准备796项正式准入；目前尚未准入、不预估全局百分比。
不屏蔽SD或跳过首错，不重跑VCS、不修改冻结collector或RTL。

### 下一轮精确补充（尚未计入）

795项实际残差分析定位标量C910 bound-table的90个可变表值位置；
准备正常FP64 DIV/SQRT共224个输入组合，覆盖除数尾数高位selector，
并以独立整数数值模型、Spike完整差分及flags/guards核验。
90是静态可变化候选容量，不是已实现的命中增量或全局百分点预测。

PTW的`shared_tlb_update_o.g_content`11个叶字段及`vmid`共有156个
未命中方向；冻结RVH=0源码直接组合赋零。正在准备精确原生资格，
不得顺带豁免未复位内部`gpte/gpaddr/ptw_stage`状态或MDA。
ALU-A扩展生产者证明得到137个精确不可达Branch vector候选，
含原24项；父端完整阅读生产者、VFU路由及队列转换源码，并实际执行
7项证明/保护测试全部通过（22.411秒）。47个同组vector、其他220个
Branch vector及所有非Branch指标保持保护。正在准备原生点资格；
尚无原生豁免资格，不计入整体覆盖率。

父端另外核对795项Segment sequencer的typed原始缺口：响应暂存
`ara_resp_d/q.resp`各128个方向、`exception.cause`各127个方向等
位于排序前列。这只是未扣全部精确EL的原始诊断，不能作为净增益估算。
对应segment源码SHA与冻结build一致。不能仅以segment是访存指令
推导响应字段恒零，必须证明所有并发返回及采样门控；暂维持HOLD。
不通过超长运行翻转`verify_arch_seq`高位来制造覆盖收益。

### 基于最新完整层级报告的缺口排序

以下读自794项实际`modules_applied.csv`，不是对795项的预测；这些模块
各有自己的分母，不能相加或仅凭百分比认定哪个贡献了最多缺口。

| 已统计模块 | Toggle | FSM | Branch |
| --- | ---: | ---: | ---: |
| CVA6整体 | 61.71% | 65.43% | 69.44% |
| CVA6 PTW | 43.84% | 68.75% | 45.98% |
| QBS读引擎 | 46.37% | 85.71% | 89.92% |
| QBS浮点累加器 | 48.40% | 100.00% | 79.86% |
| Segment sequencer | 59.01% | 66.67% | 93.44% |
| Store/load lookahead | 61.46% | 59.09% | 86.67% |
| Vector dispatcher | 67.00% | 76.19% | 90.18% |
| Lane0 ALU-A操作数队列 | 94.70% | NA | 51.85% |
| Lane0 ALU-B操作数队列 | 95.06% | NA | 57.04% |

普通向量队列已补充静态复核，两个原候选被撤回：合法vf4/vf8扩展实际
走已命中的ALU-B路径，FP sum reduction源实际走MFPU-C，而不是目标B。
不能靠执行这些合法指令宣称覆盖另一个队列；相关未命中点仍保留，
先查全部生产者及可达性，不盲跑或按“可靠模块”整块豁免。
静态结论为`vector-flow794-source-decision-agent-20261008-01.md`，SHA
`cf247f665da7ad93a2ef4dd7d2bfdc66355cc42eba5f14ed470b7592084e472e`。

## 上一份报告（793项历史证据）

`current-population793-qbs3232-parent-20261008-01`已完成五阶段原生
汇总及后台终态验收，DVE退出0且未超时。qualification SHA为
`290d18b35691338479d73b13ce1c2220b6a88830a10bd60b8038cf5cb7607a9b`。
父端独立核对17个输出哈希通过；资格记录确认实际793项membership、
完整EL物理掩码、所有非目标保护、raw/reset/final一致、applied/reloaded
一致，以及72根报告与原始层级六指标匹配。报告使用冻结旧RTL镜像，
不代表另一RTL版本的signoff。

| 指标 | 原始 | 精确豁免后 |
| --- | ---: | ---: |
| Line | 85.28% | 85.25% |
| Condition | 82.27% | 82.28% |
| Branch | 83.07% | 83.72% |
| FSM | 70.68% | 81.09% |
| Toggle | 65.34% | 72.71% |

相对791项，原始Toggle增加0.09个百分点，豁免后增加0.20个百分点。
该历史报告包含两项新增标量异常测试和已验收的QBS3232方向精确EL；
61个常量字段虽已局部原生验收，但未包含在本表。ITLB新测试已正式
纳入794项集合；本表仅记录当时793项报告，不包含794项的后续结果。
FSM已达到80%，Toggle距80%仍差7.29个百分点，
目标未完成；不可用候选位数外推覆盖率。

## 上一份报告（791项历史证据）

`current-population791-inherited785-parent-20261008-01`已正常结束，
qualification SHA为
`ad675368b58524794a04cc7518374eaf025382e7687f57dd60f2bb9986cba1e3`。
父端独立核对原生791测试membership、五阶段EL掩码、72根六指标报告
一致性和qualification全部output pins，均通过；后台服务终态0、无超时。
原始Line/Condition/Branch/FSM/Toggle为85.27%/82.27%/83.06%/70.68%/65.25%；
精确豁免后为85.24%/82.27%/83.72%/81.09%/72.51%。
相对785项报告，原始Toggle增加0.23个百分点，豁免后增加0.16个百分点；
本次完整继承相同EL，没有新增豁免，两种增量的分母不同。
FSM已超过80%，Toggle距80%尚差7.49个百分点；目标仍未完成。
集合已正式增至793项，本报告未包含随后准入的两项标量异常测试。
下方785项及更早过程记录仅作历史证据，最新百分比以文首794项报告为准。

## 794项汇总过程（历史记录，已完成）

本节保留准备和执行过程。794项全局汇总及PMP局部原生验收均已完成，
当前状态以文首和各项终态验收记录为准；下文的“正在运行”不是当前进程状态。

794项整体汇总工具已由父端完整阅读并实际执行12项测试，全部通过
（255.143秒）。包括旧QBS及其它掩码完整保留、61字段精确不重叠、
原生保护行/角色/范围/校验和篡改拒绝，以及完整792项常量源证明
和793/794增量的逐字段零命中检查。冻结工具SHA为
`a7e5b02cfdb3565234bba721ce62febedc108e6f2d3c6a2cf42f419ee670086c`。
仅准备服务`ara-global794-soc61-prepare-parent-20261008-01.service`
已正常完成（服务退出0）；准备期间父端直接核对PID1068666的exe、
cwd、cgroup及命令。
输出目标为`current-population794-soc61-parent-20261008-01`。
prepared config SHA为
`81526ba2020842417df95403931ca06441716ecf7b98ebf88ba0a67daca9434f`，
含30770个证据pins。父端检查794项唯一membership、72根报告、6162个
非Toggle实例、2989个Toggle实例及61字段/QBS继承信息通过。
已启动独立`ara-global794-soc61-parent-20261008-01.service`进行正式汇总。
父端实际核对worker PID1073346的exe/cwd/cgroup/命令，进程运行；
前置check随后通过，运行器记录实际DVE PID1076020、launcher1075978。
父端直接读取/proc，核对DVE executable/cwd/cgroup/starttime/command
全部一致；实际执行export_dve_coverage.tcl，正在原生汇总。
新百分比须等待完整五阶段验收。不会因为观察等待超时而重启服务。

下一类PMP静态候选由父端实际15项工具测试通过（0.703秒）：
`pmp-unused-entries794-static-agent-20261008-02.json`，SHA为
`88d09c5fd376db8a3c8426fe320245b1e3f9dd17ebde3ff1c4e8ba89f59862b4`。
冻结镜像实际NrPMPEntries=0，编译中的[0:0]只是占位端口。
完整枚举q/reset/next/反射与连接后，扣除已有EL，剩816个完整字段、
1088位、2176个未覆盖方向；13个MDA保持HOLD，动态_d和其reserved、
未赋值RVFI字段及其它PMP对象均不排除。此为静态候选容量，尚无新原生
EL资格，不纳入最新覆盖率。另一批FP64次正规数DIV激励正在准备，
计划以独立结果位/fflags金值及Spike逐条检查验收，未启动VCS。
PMP原生工具已由父端完整阅读Python、Tcl及tests，并实际执行12项
测试通过（41.486秒），包括fresh prepare/check、五阶段generated Tcl、
scalar/vector完整双方向、类型/范围/归属和非目标保护负测。
正式prepare/check均通过，输出`pmp-constants816-native-parent-20261008-01`，
config SHA为
`5aa5a2cc88e4b10e3ddae357c768d2c6744a84440119f5cd83fa6e186a7e8d26`。
独立服务`ara-pmp-constants816-native-parent-20261008-01.service`已启动。
父端实际核对worker1079933和DVE1080139的exe/cwd/cgroup/command；
DVE已开始导出native_before_0.tsv，仍待完整原生五阶段验收。
完整保护4509个非目标typed objects，13个MDA不豁免。本服务与794项
全局汇总独立目录/独立DVE实例，未覆盖原报告，未计入新百分比。
该服务随后正常退出0且无超时，父端独立核对481个证据哈希全部通过，
并实际运行完整verify得到PASS。capture-result SHA为
`1b7bc2ef450a3280094b3f701e80c812a238a2e2d2534ac2dfbdfcc6bd7f7c48`。
状态为`PMP_CONSTANTS816_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED`：
816个字段、2176个方向的原生局部资格已经成立，但仍未应用全局EL。
该软件预检为10013条指令、144次FDIV.D、436项检查；父端静态发现
每单元另有两次FMV_X2F和一次FMV_F2X也经过FPU，检查器必须纳入
这些实际请求，不能将它们误判为多余DIV。补齐前不启动RTL仿真。
独立只读审阅进一步发现工具的terminal_gate复用链读取runner.IMAGE_SHA，
而新runner未导出该属性；必须修正并测试真实终态调用链，不能等仿真
结束后才发现AttributeError。完整owner检查应包含实际握手、STALL
保持和TID完成；不能仅忽略FMV请求或假定输入永远ready。gold及EX2/EX3/
ROUND拼接计算的静态审阅未发现问题。以上为运行前检查器问题，未发现
新的RTL故障，也未将该测试计入正式覆盖率集合。
进一步复审指出FMV passthrough只使用A，DIV使用A/B；未使用操作数
可能合法含X。used字段仍须逐位已知并符合金值，未使用字段不得当零，
若检验holding稳定性应比较原始含X位串。补齐used-X拒绝与unused-X允许
负/正测后才可运行。不能通过忽略全部操作数来放宽请求语义。
以上检查器问题已修正并通过独立静态复审；父端实际39项工具测试
全部通过（2.544秒），正式prepare/verify通过。prepared SHA为
`dc033335b17cee63364d49f0a636de5535c496dee496d4f3b2af656d84556965`。
已启动`ara-scalar-div-subnormal794-parent-20261008-01.service`，输出
`scalar-div-subnormal794-old-image-parent-20261008-01`。父端直接读取
worker1086086的子进程，确认实际simv PID1086261的exe/cwd及完整命令
匹配冻结镜像、预检ELF、独立code.vdb和聚焦probe；CPU时间实际增长。
仿真预算600秒、不自动重试，RTL未变。正确性与全部owner/EX2/ROUND
探针验收尚未结束，不计入正式PASS或覆盖率增量。
VCS随后正常结束，CPU时间50.150秒，未超时。首次离线collector完整
架构对比通过：10013条指令、6450次GPR写入、432次FPR写入、1181次
标量访存，skipped_unobservable=0，mismatch=None；144个结果/fflags/FCSR
金值及436项检查、完整guards、FCSR恢复均通过。但wave audit在
`No flush during FPU owner`门禁处拒绝，保留
`scalar-div-subnormal794-qualified-parent-20261008-01/failure.json`。
目前不能认定RTL错误或自定义放宽flush：使用现有probe.vcd重建首拒
周期的flush/live/scheduled/valid及真实接受/返回关系。未重跑VCS、
未改RTL、未准入该case。检查器资格失败的VDB不计入正式报告。

AKV成功地址别名激励已完成独立软件预检，输出
`akv-canonical-alias794-preflight-agent-20261008-02`，SHA为
`0a1608bb9176452aad21efd75256bb3315742e4d3c3b44e5adf2be7aa7b56e98`。
参考为120799条指令、4247项检查、两次精确S-ecall、完整VRF/CSR和页
guards。正/负canonical Sv39别名映射相同Q/K/V物理页，13个真实地址
字段有724个剩余方向，其中别名相交上界520；不是实测覆盖增量。
软件适配Spike通过不代表自定义AKV执行通过，native runner/collector
仍需绑定两阶段共10条custom命令、实际S-mode翻译及完整结果oracle。
未启动该激励VCS，未准入，未预测全局百分点。

VL高位静态审查输出`vl-highbits793-static-agent-20261008-02.json`，SHA为
`29233c63ebb030293065442ea70141bec14cb08f92d27fe44ef4103b1abd8550`。
csr_vstart[10:9]允许直接CSR写入，csr_vl[10:9]可由合法VL512/1024
置位；本轮可批准新豁免为0方向。queue计数高位仍需闭合命令域、
减法下溢及完成清零不变量，不能用benchmark最大长度代替证明。

ITLB增量已正式发布为
`itlb-ppn-aba-offline-admitted794-parent-20261008-01`，manifest SHA为
`02ee7424a6b21d8073097d8a6389be4393d76fc7a3ab31ce410f1c24f70de8cf`。
父端发布后独立验证30个输出哈希、795行唯一输入清单（编译VDB加794项
测试）、793项完整前缀、6162个非Toggle实例逐位OR及2989个Toggle实例
无旧命中丢失，全部通过。新增测试实际16个ITLB槽位、48次accepted更新、
3846项软件检查均验收通过；496个新增方向是ITLB scope的实际增量，
不是系统总增量，也不据此推算全局百分比。

SoC常量字段的第三次独立原生验证已经通过：
`soc-constants61-native-parent-20261008-03/capture-result.json`的SHA为
`40bd30fd8fafcdb2fb32751d742e01e7f7bc236fa8a8a11634a53a3ffbdee8a3`。
父端独立核对537个证据哈希、五阶段每阶段9012个完整对象、非目标保护、
两次加载相同的61字段EL及初始/复位/最终空EL，全部通过。DVE退出0，
未超时。此处仅代表局部精确豁免资格；下一份794项报告才会应用该EL。
前两次失败记录保留，未通过的工具验收不计入成功证据。

`scalar-slot-rotation-offline-admitted793-parent-20261008-01`已正式准入，
manifest SHA为
`757513188f805841491c898584b22722df80facd8f8c9fb424564a82502f17c3`。
父端发布后独立检查28个输出哈希、794行唯一输入清单、792项原集合
的完整前缀、6162个非Toggle实例逐位OR及2989个Toggle实例无命中丢失，
均通过。新增测试与Spike逐条对比1626条标量指令、372次访存、89项
软件检查和12次精确异常；波形核实slot2/3/6/7各自的LD/SD/LD实际
分配及异常取消路径。新增系统Toggle方向1880个，其中12个目标字段
合计768个；Line/Condition/Branch/FSM增量均为0。不按序列化位数
推算DVE百分比，也不将没有向量指令的测试称为向量执行验证通过。

QBS bank1局部v2原生验收已通过，输出为
`qbs-bank1-group-hit-native791-v2-parent-20261008-01`，qualification SHA为
`323b84514531645f65bb8c952cc739e9dc64bb82a026bb6a2ff74050cbaf852f`。
before/selected/reset/reloaded/final五阶段均完整绑定6707个原生对象，
排除方向依次为0/3232/0/3232/0；704个仍可能命中的方向保持保护。
这份EL已应用上方793项全局报告；本段保留局部验收证据，不另行累加增益。

61个SoC常量字段的精确原生验证已启动独立宿主机DVE服务
`ara-soc-constants61-native-parent-20261008-01.service`。父端实际10项
工具测试通过；18个scope、61个完整字段、7686个候选方向、8951个
非目标对象严格保护。prepared config SHA为
`70f9a405e6d930590295e7bdf3718f24e039c047ecfade0c26bf78620ba15abb`。
启动后父端直接核实实际DVE PID1038729的exe/cwd/cgroup/command一致。
原生首次运行已终止：DVE退出0且未超时，但服务验收失败。
before阶段的`orig_instr.rvftype.repl`原生行无法匹配现有typed resolver；
发生于加载candidate EL之前，未应用任何豁免。完整失败记录保留，
下一工具版本须以真实原生表和编译shape说明别名关系并补负测，
不能跳过未知行或豁免整个联合体。DVE退出0不代表资格通过。
源码/编译形状与真实表随后确认：不是联合体重复，字段是单比特
`[14:14]`而原生表显示裸名，旧resolver只支持`[0:0]`裸名。
独立v2仅允许唯一exact-name、内部signal、left==right且非目标字段
使用该显示别名，全部原有完整性/MDA/角色/目标标签门禁保留。
父端实际10项v2测试通过（28.875秒），包含18张真实表9012行完整
绑定及fresh prepare/check五阶段host测试；这仍不是原生豁免资格。

ITLB的A/B/A映射激励已由父端审阅runner、collector、探针和链接布局，
实际31项工具测试及prepared check通过；Spike参考为37340条指令、
3846项检查和48次精确ECALL。独立600秒VCS服务
`ara-itlb-ppn-aba792-parent-20261008-01.service`已启动，prepared SHA为
`ee90d67c0e880ee590d822e6b1131ee8154962ca5f4c926149e75b8ac199bd12`。
必须通过完整标量对比及实际16槽位各自A/B/A的accepted update/PTE
波形检查后才能准入。该诊断以792项为基线；后续准入必须合并到
最新正式集合，不覆盖793项。未经校准的序列化坐标不称为原生bit号。
该VCS已正常结束，无超时，CPU时间162.470秒。首轮collector误继承
旧测试的零后端请求条件而拒绝：实际6个后端请求分别是三组
vstart/vcsr只读CSR（实际指令字00802773/00f024f3），requests=responses=6
且protocol_errors=outstanding=0。早先称vlenb有误，以实际CSR地址为准。
新验收必须将全部6次握手与逐条CSR架构结果绑定，保留48次异常和
实际16槽位PTE检查；只重做离线验收，不重跑已有仿真，不直接跳过门禁。
独立v2 collector已由父端完整审阅；实际12项工具测试通过（38.743秒），
随后完整离线验收成功。输出`itlb-ppn-aba-qualified-v2-parent-20261008-01`，
qualification SHA为
`0e39eeac0b6a6335877c8232a7b54fe44f91a0e162cdc81b562d56547f7495f8`。
37340条标量指令、48次异常全部匹配，skipped_unobservable=0；3846项
软件检查通过，6次只读CSR start/request/response/retire及两个独立
console monitor身份一致；波形实际48个accepted更新证实16槽位各自
A/B/A。父端独立检查14个输出哈希通过。相对792基线，ITLB scope新增
496个序列化Toggle方向，其中诊断目标坐标新增480个；未经原生位号
校准，不称为具体原生PPN低位覆盖。尚未正式准入，必须对最新793项
完整并集和历史ELF去重后才能进入下一集合，不将该局部数换算百分比。

标量FPU仲裁测试已完成一次固定120秒预算VCS，实际27.856秒且未超时。
父端实际34项工具测试通过后运行，离线资格输出为
`scalar-fpu-fma-arbiter792-qualified-parent-20261008-01`，SHA为
`0b30ba04bd032c2311b67d9babfcadd43752e911623c0a31db23a96dc3f176a6`。
613条指令、185次标量访存、56项检查、50次FPU请求及结果通过。
真实FMA hold=0、stall=0，因此状态为
`FULL_ARCHITECTURE_FMA_HOLD_NOT_TRIGGERED_NO_RETRY_NOT_ADMITTED`。
实际Toggle新增4个方向，Line/Condition/Branch各新增1个位点，FSM为0；
尚未准入。不能用功能PASS冒充hold路径覆盖，也不通过重复调整激励
凑触发。fpu_exception只读取源码实际驱动的cause/valid/tval，
tval2/tinst/gva保持UNOBSERVED，不将未驱动成员当成零。

793项全局报告工具已由父端补齐受封存配置约束的后台run-reviewed
入口，实际最终11项工具测试通过（60.712秒）。fresh prepare/check
均通过，输出`current-population793-qbs3232-parent-20261008-01`，
config SHA为
`b38418835ab071fdd5918f51bc4b7e85e22e4851b4e6478c2c4a75b11d934549`。
独立服务`ara-global793-qbs3232-parent-20261008-01.service`已启动；
完整793项唯一membership、72根、6162个非Toggle实例及2989个Toggle
实例的门禁保持不变。metadata准确记录新增3232方向EL，而不是沿用
no-new-exclusions标志。未包含61常量候选，须原生五阶段终态通过后
才可更新顶部正式覆盖率。
后台实际DVE PID1048758的exe/cwd/cgroup/command已由父端直接核对，
不是仅有服务状态或准备文件。后台运行不等于报告已经验收。

61常量v2的父端fresh prepare/check均通过；独立服务
`ara-soc-constants61-native-v2-parent-20261008-01.service`已启动，
config SHA为
`b5629d8a96e850e86f6dcab9f3f21fab9155d41746424ce6975362ee0be637f1`。
实际DVE PID1046710的exe/cwd/cgroup/command由父端直接核对一致。
旧01失败输出不覆盖；v2尚待五阶段原生资格，不提前应用EL。
v2随后在保存first.el后终止：before/applied各18张完整表已导出，
但EL gate只接受logic签名，而实际`i_system.hart_id_i[2:0]`端口保存
为net签名。未完成reset/reloaded/final，也未获得资格；不应用到
全局报告。新工具必须以实际compiled对象类型绑定该精确net条目，
禁止直接跳过陌生EL语法或放宽目标范围。原生失败证据保持不变。

## 最新集合准入与汇总边界

QBS bank1 group_hit精确局部原生验证已由父端完整审阅Python/Tcl工具，
实际9项工具测试和封存config check通过后启动宿主机服务
`ara-qbs-bank1-native791-parent-20261008-01.service`，worker预算900秒。
输出`qbs-bank1-group-hit-native791-agent-prepared-20261008-01`，config SHA为
`3d27f35f3f03fac4eef79580941e2df3ad245fba3face4c8a9d7e1e239acac0b`。
实际DVE PID1006589的exe、cwd及服务cgroup已由父端直接核对一致。
测试只验证3232候选方向的部分位EL和26个scope非目标保护，不将EL
应用到正式集合；须五阶段原生验收通过后再决定准入。未重复启动仿真。

父端已独立解析本次实际`first.el`，确认精确3232个目标方向；26个
`native_selected_*.tsv`逐作用域完整绑定与非目标保护检查均通过，
`reset-empty.el`为零字节。这只是已完成selected阶段及reset排除表的
中间证据，尚不代表五阶段资格完成，也不更新整体覆盖率。

本次原生局部服务最终因900秒预算超时结束，terminal为returncode=-15、
timeout=true，qualification-reject为Strict actual terminal；未生成合格
资格，不应用正式EL。before/selected/reset/reloaded均导出了26个scope，
final只完成首scope的检查（后续文件可能部分写入，不按存在即通过）。
日志未见目标范围不匹配，开销集中在每阶段逐对象GUI选择及排除标志
查询。下一实现保留各阶段完整原生对象绑定、全局EL精确方向和保护
补集验证，消除重复逐对象选择查询；对象identity和排除语义分开取证，
不以推测标志代替实际GUI结果，也不直接延长预算重试。

下一批动态激励已进入实现准备：利用完整flush后issue_pointer归零、
accepted allocation推进的源码路径，将非对齐异常导入slot2/3/6/7。
目标残差容量768个方向，不保证实际命中；必须用分配握手/flush/VID
波形和完整标量gold核实，而不能按退休指令数推断。AMO入队建议已
要求先与冻结SoC的ATOP拒绝路径核对，未批准直接运行成功AMOSWAP测试。

槽位方案的补充源码核查：`decoder.sv`的`OpcodeOpImm`将固定32位
`0x00000013`解码为ALU/ADD，而非FU_NONE。NOP推进分配指针的依据是
`scoreboard.sv`中decoded valid、ack且非flush_unissued的实际分配条件，
不是FU_NONE自动完成路径。同周期完整flush会将下一拍指针覆盖为零；
新探针必须区分该情况，不能仅统计NOP退休数。封存的初始提案不改写，
后续激励与验收以这一补充约束为准。

槽位激励`scalar_misalign_slot792.c`及软件预检查工具已由父端审阅。
独立输出`scalar-slot-rotation792-preflight-agent-20261008-02`的Spike
参考通过12次精确异常、89项检查、1626条退休指令和372次内存访问；
父端实际核对90个输入/输出文件哈希一致，manifest SHA为
`0f51226da7eff4c7bd79ad579002a9b252a0eaf3b1cd3c7e1dd46aa72dc5e2c5`。
这不是DUT通过或覆盖率准入。真实参考负例测试随后暴露工具缺陷：
直接赋值冻结的SpikeCommit.memory_accesses产生FrozenInstanceError，
未执行预期的损坏检测。需用dataclasses.replace构造损坏记录、重新
完成负例测试并在新目录封存后，才批准VCS；原02证据保持不变。

父端已用dataclasses.replace修复上述负例工具，实际02参考的4项测试
全部通过，随后独立重建并封存
`scalar-slot-rotation792-preflight-parent-20261008-03`，SHA为
`b10eb7a59693d32d997ff96ce4a0a78f95ce6496d6b1ea3e866fda4d589dd3f9`。
新参考仍为12次异常、89项检查、1626条退休指令及372次内存访问，
其真实参考负例4项再次全部通过。02目录保留为历史工具缺陷记录；
后续runner必须绑定03，不用02的旧工具pin作为当前资格依据。

槽位runner/probe/collector的源码审阅与实际14项runtime测试通过，
复测前后四文件哈希保持一致。父端实际prepare/verify通过，prepared
SHA为`96b19cdaa35ca43964cc0bb5aa0b57e6a6287e62d9eafcbc19dc6511aad7fc3e`。
短VCS在独立`scalar-slot-rotation792-old-image-parent-20261008-01`中
正常结束，耗时36.20秒、returncode0、无超时。父端完整collector通过，
资格目录`scalar-slot-rotation792-qualified-parent-20261008-01`，SHA为
`a68e58d37fa0813dff50717e2f2778b8eb3faf335691479b1e68d130504f3fd1`。
实际1626条标量退休、372次内存访问、89项检查及12次异常全部精确匹配；
每个slot2/3/6/7均实际收到LD(A)/SD(~A)/LD(A)，各landing分配链长度
为3/4/7/8，真实握手及mret flush证明目标槽位，而非按退休数推断。
此测试已具备DUT资格，尚未测量相对792的全量增益或正式准入，不改
已验收791项报告的百分比。

791项整体汇总已完成实际prepare，输出目录为
`current-population791-inherited785-parent-20261008-01`，配置SHA为
`480f8e9ef4f81caa6ab01c8cc04abb955ef46ad65c6ef3a150eac4a2e3d9b6f4`。
本次仅增加已准入测试，完整继承785项已验收EL，不新增observer豁免；
须通过输入校验、实际DVE运行及五阶段验收后才能更新整体百分比。
父端实际check已通过，宿主机后台服务
`ara-coverage-population791-parent-20261008-01.service`已启动；实际wrapper
PID991964已核对为运行中，启动阶段重新校验来源，尚不据此声称DVE已完成。
随后实际DVE PID993728已启动，父端直接读取`/proc`核对安装可执行文件、
本次独立输出cwd及同一systemd cgroup，三者一致；原生所选测试清单已导出。
这是运行身份确认，不是终态或五阶段验收，百分比仍不更新。
789至791项的RR190、CLASS_PADDING及FPNEW90常量方向零活动补充审计
已生成，父端实际6项工具测试通过；这不是新的覆盖率报告。

标量非对齐异常测试的原始退休差分已通过866条指令及226次内存事件。
后续探针验收发现检查器使用基础配置的AXI user宽度64，而实际TB、harness、
SoC及CVA6生成配置链传入宽度1，使load请求结构实际136位而非199位。
离线适配仅修正该配置推导，父端实际6项工具测试通过；复用原波形，
不重跑VCS、不修改RTL。完整波形资格及相对791项增益尚未验收，
因此该测试暂不纳入正式PASS集合或百分比。
适配随后增加未驱动write-user单个位的独立读取规则，源代码确认load
write-enable恒为0且无user字段生产者；地址、取消、tag及其他活动字段
仍要求确定的二进制值。父端再次完整审阅适配代码并实际运行12项工具
测试通过。此处是检查器验证，不是新RTL修复或测试准入证据。

QBS bank1 activation `group_hit`的全周期源码归纳审阅工具已由父端完整
阅读，实际6项测试通过；父端另查阅ingress队列复位/推进、pending保留
字节索引、per-slot consumed门控及group_hit生成逻辑。候选3232方向仅
具有复位后可达状态的静态不可达依据，不声称形式证明或已应用EL。
704个映射允许的剩余方向保持保护。下一步须完成原生精确对象、位方向、
checksum和非目标补集验证，不能直接将候选数折算成覆盖率提升。

标量非对齐异常离线资格随后完成，目录
`scalar-misalign789-soc-qualified-agent-20261008-03`；core SHA为
`21d1221c9d2760cacbfe51172771e8842eebc7b59b1bedf9bffa7cc9a0024052`，
独立SoC配置/字段读取closure SHA为
`eae0cef384adaf5d3a5ec8a225616ffc7c5bfb379cdcf38be9f1d763ac158c86`。
父端实际重验全部input/output pins、18项工具测试及六次故障owner波形
重放均通过，确认3次load取消及故障store不入队。只读取CSR异常有效时
port0的PC/TID，不要求未使用port1或无关scoreboard成员为二进制；实际
PC/TID未知值仍拒绝。此样本无向量目的，不能宣称向量执行验证。
相对正式791项的2989实例Toggle OR，父端独立核对无丢失/无宽度或
checksum漂移，实际新增1742个序列化方向、14个实例；其中五个指定LSU
tval字段共306个新增方向。四类诊断增量为Line10/Condition4/Branch5/FSM0。
这些是新增命中证据，正式准入及DVE整体百分比尚待完成，不修改正在
运行的791项报告输入。
父端另独立重放全部6162个四类实例的`baseline OR single == combined`，
同时检查实例集合、width/checksum和位宽上界，均通过。被动observer的
原生边界负例工具也由父端完整阅读并实际7项测试通过，覆盖错配module/
metric checksum、零容量对象、外来branch vector及未观察签名；此工具
不新增EL、不修改791汇总依赖，也不作为DUT覆盖率增益。

父端实际12项792准入工具测试、prepared verify及显式admit均正常结束。
正式输出`scalar-misalign-offline-admitted792-agent-20261008-01`，manifest SHA为
`0aadd9e4fa71a5a582830a043fedc67669b0f53cea866a1b8147a5526c8f81f4`。
发布后父端重验全部output pins、793行唯一ledger、完整791前缀，均通过；
正式集合792项PASS。1742个Toggle方向及10/4/5个Line/Condition/Branch
新增命中已纳入集合，但运行中的791项DVE输入保持原封不动。
该DVE已实际终态0且无超时，父端另独立核对实际791测试membership、
五阶段EL掩码及72根六指标报告一致性均通过；完整资格文件未生成前
不更新本文件顶部的正式百分比。

本轮新增CSR高位翻转任务已由父端审阅app、软件参考、运行器及收集器，
21项工具测试实际通过；prepare与verify均通过后启动宿主机服务
`ara-csr-cause-wlrl788-parent-20261008-01.service`。
独立输出为`csr-cause-wlrl788-parent-run-20261008-01`，prepared SHA为
`126bc695249d2c1162b80a9902d696ece50fd1c774d1932748769b60bbd77a25`。
父端已实际核验simv937871的exe、cwd和运行命令；预算180秒，服务上限240秒。
该测试检查匹配实现的mcause/scause全64位存储，不将WLRL高位值视为
可移植异常编码；不触发真实异常，保持MIE/MPRV关闭并恢复CSR。
需完整664条退休指令、168次内存访问、30笔原生CSR归属及44项软件检查
全部通过才可准入。当前仅已启动，不计入788项PASS或整体覆盖百分比。

CSR随后正常终态0，用时25.0317秒、无超时。独立收集器在
`csr-cause-wlrl788-qualified-agent-20261008-01`完成上述664/168/30/44检查，
标量差分及原生CSR owner均通过。四类位图相对788项增量均为0；Toggle
已核验实际新增928方向（真实q/d464、观测别名464，八字段各116）。该样本没有向量目标，明确记录为
`UNOBSERVABLE_ZERO_DESTINATIONS`，不声称向量差分通过。

父端完整阅读789准入源码和测试，实际13项工具测试及prepared verify通过后
显式admit。正式目录`csr-cause-wlrl-offline-admitted789-agent-20261008-02`，
admission SHA为
`810a9531e1e7a7edaece3fcec19e90e47fee3530e641f824aaed49e8deb3522d`。
父端另外独立检查全部output pins、790行唯一ledger、完整788前缀以及
全部6162实例有界OR，均通过。928是新增方向数，不是百分比；整体仍需
新DVE报告验收，不能沿用785项分母推算。

788项observer汇总03的父端25项工具测试与实际check均通过，但独立负例
发现Line标签可一致替换、Branch999999可在正确metric checksum下被接受。
因此03禁止启动DVE，须精确绑定compiled point IDs后建立新后继；不将
host check通过视为原生覆盖报告验收。

AKV规范地址K流故障已拆成两项完整独立测试，不删减每项5680字读回。
父端阅读运行/收集器及测试，实际22项工具测试和两个prepared verify通过。
已并行启动`ara-akv-canonical-kfault-phase0-parent-20261008-01.service`与
`ara-akv-canonical-kfault-phase1-parent-20261008-01.service`，实际simv
943616/943617的exe、cwd、cgroup均核验；每项480秒、服务上限540秒。
输出分别为`akv-canonical-kfault-phase0-old-image-agent-20261008-01`与
`akv-canonical-kfault-phase1-old-image-agent-20261008-01`。冻结RTL不变，
需完整故障归属、PC/tval、VRF/CSR/guard、映射重试及release核验后才能
纳入覆盖率；运行中不提前增加PASS或百分比。

两项AKV随后正常终态0、无超时，用时332.3167/333.4077秒。原冻结
collector在最后`Complete two faults/retries/terminal waveform`合取检查
被拒绝，原failure保留、不计入PASS。父端从源码确认vlsu将akv_clk门控后
连接engine；现有VCD实际各只有333个门控上升沿，却被与global commit
cycle175232/175033比较。最终状态均为plan0/fault_pending0/ar_valid0/
burst_count0/clk0。还发现原VCD迭代器忽略文件末尾空timestamp，解析
最后变更帧不能替代捕获结束时间。正在建立仅离线检查器后继，必须绑定
真实结束时间、时钟/reset epoch及完整fault/retry/drain/idle证据；不直接
删除终态检查，不改RTL，不重跑VCS，尚未资格通过。

父端随后完整审阅离线epoch后继并实际运行14项组合工具测试，全部通过。
源码与实测确认全局ClockPeriod为1ns、VCD单位100fs，退休周期对应
`timestamp=155000+cycle*10000`，不能与333个AKV门控沿数比较。
第一项在`akv-canonical-kfault-phase0-epoch-qualified-parent-20261008-01`
完成完整离线资格核验，qualification SHA为
`60a85808b4287d60d1e968fee7a7e7a8a893531b4918cf10631601b54f3324e2`。
冻结collector中的fault/retry/owner/drain检查仍完整执行，另外检查单次reset、
实际VCS finish、VCD末尾空timestamp及保持至EOF的空闲状态；未修改RTL，
未重跑VCS。第二项随后也完成父端离线资格核验，输出
`akv-canonical-kfault-phase1-epoch-qualified-parent-20261008-01`，SHA为
`d0be73155da4cd491fef3425c354bb4c920684c294779e9cbca99a3d1800cc75`。
独立审阅员实际9项epoch及22项原门禁测试通过，并重核独立结果pins；
两项均为fault/ack各1、AR/RLAST各6，原始拒绝结果仍保留。
两项尚未population准入，正式集合仍为789，整体百分比仍以785报告为准。
两项针对789的完整原生Toggle位图OR已测得581及2297个新增序列化方向位置
（第二项相对第一项合并后集合，共2878），主要位于AKV engine/read-engine
及VLSU异常传播路径；四类非Toggle位图增量均为0。原始测量文件为
`akv-canonical-kfault-two-phase-gain789-agent-20261008-01.json`，不直接
把该位置数换算成GUI百分比。父端完整审阅准入工具并实际15项测试通过，
正在准备第一项正式准入；尚不提前增加正式集合数量。
父端随后actual prepare/verify/admit790均通过，正式目录为
`akv-canonical-kfault-offline-admitted790-parent-20261008-01`，manifest SHA
`c626fcfddb166639a5b3120411171c9ffdb06897b9ad1b3fcf44d4cb7f890655`。
首项新增581个Toggle序列化方向位置已计入正式集合；第二项2297仍待准入。
正式集合790项，整体GUI百分比仍以785项报告为准。
第二项随后也完成父端显式admit，正式目录为
`akv-canonical-kfault-offline-admitted791-agent-20261008-01`，manifest SHA
`8b732015035c1f716940598f05d8a8063e4b4829eb5cd67cfebcbb2728ee2b30`。
父端独立复核全部output pins、792行唯一ledger的完整790前缀，以及
6162实例形状/校验和/有界完整OR，均通过。两项合计2878个Toggle
序列化方向位置均已纳入791正式集合，GUI百分比仍须新整体报告核验。
新增scalar misalignment软件参考及工具的16项测试也已实际通过；
其目标是精确LD/SD异常tval高位，不以重复寄存器entropy替代缺口分析。

Line/Branch native身份仍缺可信GUI样本；不能将compiled的8个Line BB
与native行数直接等同。安排一个同shape历史PASS样本的短时只读DVE观察
方案（最多300秒），只导出确切scope的原生labels/columns/path/子项；
不应用或保存EL，不发布覆盖百分比。需父端审阅prepared后才启动，
拿到native样本再完成point绑定及四项负例闭环。

父端已完整审阅只读导出v2，实际12项工具测试及prepare/check通过。
新目录为`cvxif-point789-readonly-parent-20261008-02`，config SHA为
`fc98702c3f64f914bb3d76435ca725afa9b5380f13438d07831c1c850fae1161`。
启动器直接使用已封存xvfb/DVE路径，并把配置SHA及工具身份绑定到
execution/live/terminal记录；旧prepared保留。已启动宿主机独立服务
`ara-observe-cvxif-point789-parent-20261008-01.service`，只读预算300秒、
服务上限360秒，首次服务检查实际MainPID971207存活。
此任务仅获取Line/Branch原生标识，不修改VDB、不应用豁免、不发布百分比。
实际DVE PID971407的exe/cwd/cgroup/command均匹配封存配置，但原生
detail选择返回`Native detail selection identity`；Line TSV仅有header，
不能将其称为有效Line导出，也不能判断失败发生在Branch。
错误路径中的`exit 1`又被DVE包装为不支持参数的`gui_exit`，导致未正常退出。
父端已显式停止该独立服务并保留error/live/log；不对失败导出作覆盖资格。
后继需依据实际GUI返回标识修正选择器和错误退出，不放松目标身份门禁。
父端随后完整审阅只读v3及递归walk测试，15项工具测试与实际check通过。
独立目录`cvxif-point789-readonly-v3-prepared-agent-20261008-01`，config SHA
`2c3f1e081df93c49def1cda0170a522adda04c3f152e88e77330162266ad3556`。
v3不选择detail、不查询exclusion，每行明确`UNOBSERVED`，错误退出采用
`gui_exit -noprompt`。真实DVE运行终态0，无超时，取得Line的Block/Statement
两个aggregate项，以及Branch两个Item父项及四个分支子项，共六项。
这说明Line native行数不能等同8个compiled BB；新Point绑定须依据实际
aggregate/child结构。此次仅identity observation，不是豁免或整体百分比资格。
已生成的observation重复verify尝试独占写入而报FileExistsError；原结果保留，
父端使用只读receipt及hash重放，不因该工具幂等问题重跑EDA。
父端只读重放随后通过：execution/live/terminal配置与工具身份、全部
output pins及原生两项/six项数量一致，observation SHA为
`b8131b282e9346709bb16721ab07ab5b4985d42d57d86cd57025079a3740dd27`。
新scalar misalignment检查器最初24项测试中有一项源码匹配失败：
store buffer实际valid_i接store_buffer_valid，而非直接st_valid。
已按源码`store_buffer_valid=st_valid & (!RVA || amo_op_q==AMO_NONE)`
修正证明锚点，并保留故障store的st_valid必须为0门禁；不改RTL，先重测
工具后再批准原生VCS任务。
修正后父端24项运行/收集器测试实际全部通过，已启动宿主机服务
`ara-scalar-misalign789-parent-20261008-01.service`，输出为
`scalar-misalign789-old-image-agent-20261008-01`，prepared SHA
`2439896c582f48ce5b078c01989e2a8ce90c56c531a98997c284c22aaa28b27e`。
预算120秒、服务上限170秒；冻结RTL/镜像不变，尚未计入PASS或覆盖率。
实际任务随后在33.8166秒正常退出0、无超时，已形成五类覆盖VDB及focused VPD。
父端读取原生终态及日志；尝试现场PID复核时simv980930已经结束，故只将
原runner保存的live-identity视为运行时证据，不宣称父端独立捕获到存活进程。
仍需完整866条标量差分、226次内存访问、六笔原生LSU/CSR异常归属和
56项软件检查完成资格验收，再针对791集合计算新增命中后准入。
同时继续分析QBS activation bitmap的writer/context映射；先区分结构不可达
位与合法输入可翻转位，再决定新增激励，避免无针对性的shape扫描。
初步分析显示bank1只接M8 contexts4..7，M2/M3无法驱动它；量化writer
受context residue限制，不能用改变K或重复低M扫描填充这部分缺口。
合法byte映射不可达尚不等于reset/abort/stale全周期恒零证明，未直接豁免。

2026-10-08本轮父端检查：known-old非零vstart激励的7项软件测试和21项
运行/收集器测试实际通过，冻结准备seal为
`de05bbfff9d5fee5b3c582e734d0a80801b351e8f30e02e24346110d00e2eca5`。
父端actual verify通过后启动宿主机独立服务
`ara-mask-compare-known786-parent-20261008-01.service`，输出
`mask-compare-restart-known-old-image786-agent-20261008-01`。
预算为360秒，服务上限420秒；不编译、不重试、不修改冻结RTL。
运行结果未验收，不能提前增加PASS数量或覆盖百分比。
父端随后直接核验存活simv877125的实际exe、cwd及服务cgroup，与启动记录一致；
这次是真实VCS正在运行，不仅是Python准备进程。

CSR packed父信号的源码布局推导已由父端实际重放通过；首次真实owner
重放仍被严格拒绝：首两笔PC/TID/操作/数据一致，但波形提交周期484/486
对应退休记录485/487。仅能证明采样关系待核实，不能直接加一放行，
也不能将该检查失败认定为RTL故障。独立后继检查器必须从冻结监视器源码
及实际波形证明周期关系，并保留全部30笔owner检查；不重跑VCS。

以下条目保留过程时间线，其中早期“尚未准入/正在运行”不覆盖文首最新状态。

本轮后续：CSR周期根因由冻结源码和独立审阅共同确认，是CVA6 RVFI
posedge寄存级；monitor读取该寄存结果的时间比原生CSR commit晚一拍。
后继使用实测post-counter与下一沿pre-counter相等关系绑定观察时刻，
不引入任意周期容差，不修改CSR事务字段。父端36项测试通过，真实30笔
原owner门禁完整通过；独立证据
`csr-satp-sepc-rvfi-epoch-parent-review-01.json`，SHA为
`4c933576f241a6795bc7f7113404e02f0edf21c834e5eaefdb1f399df795362f`。
这是owner组件通过，完整资格与准入尚未完成，不能增加PASS数。

known-old非零vstart VCS正常退出0、无超时，用时240.218秒。
父端随后启动一次完整离线资格检查至
`mask-compare-restart-known-qualified786-parent-20261008-01`；
终端退出0不是功能PASS，待全标量/有效向量/CSR/保护区域/原生VDB校验。
完整collect实际拒绝`Simulator/UVM failure diagnostic`；console包含
`test wrote failure value 0000000000000003 to tohost`，不能因为OS退出0而准入。
保留FAIL目录和原VDB，基于同一次聚焦VPD及原生向量轨迹定位首错；
尚未给出完整根因，不修冻结RTL，不将失败测试加入覆盖集合。
后继只读取证已确认根因：VMSLTU的MaskB请求把lane级vstart1/2/4用于
EW64旧mask word寻址，实际VRF地址5/6/8，而应读取v1的packed-mask首word4。
四Lane共12次返回均与预测错word相符，随后MASKU合并这些错误旧位。
vstart4/8/16分别损坏prestart位{2}/{3,6}/{1,2,5,7,9,10,13,15}，
active位全部正确，10条非mask writer精确匹配。这不是合法tail差异。
标量首错order31589、PC0x800024f8，期望mask字节f3，实得f7。
证据`mask-compare-known786-measured-bug-agent-20261008-01.json`，SHA为
`1448736d8c403b94cf2e4ec578ce26e84894f84a4cb6bc858c4dd00a84e13225`，
父端重核13个顶层证据pins通过；原失败、镜像和VDB保持不变。
未修RTL、未重复VCS、未加入覆盖集合。VPD只转换一次。

标量entropy64后继的父端24项测试与9973个冻结pins实际prepare重放通过。
正式参考范围为3326条指令、1646次GPR写及903次访存；5000为含boot/终止后
idle的Spike日志计数，不能作为业务指令数。准备seal为
`1f999e25e41f7501129fdcabf9e5f2f1c1c30aeb3913884aed2e5d0db597f5e8`。
已启动独立宿主机服务`ara-scalar-entropy64-786-parent-20261008-01.service`，
输出`scalar-entropy64-reviewed786-agent-20261008-01`；先重核pins再启动VCS，
启动服务本身不证明simv已执行。最终需检查固定cgroup/实际exe/cwd/命令/
终态receipt与原生五指标VDB，PASS前不准入；Toggle按741缓存+45后缀测增益，
未知MDA interval编码不能冒充已证明的方向增益。
父端已直接核验实际存活simv884326的exe/cwd/cgroup与receipt一致，
确认真正进入VCS执行，不再仅是Python准备阶段。

CSR完整后继资格的父端12项测试和实际plan verify通过；实际collect复用
原VCD、全部原检查保留，完整资格通过。core SHA为
`08292dd5ee50f8e7b274349b464c2f8f1fedc8ecbb8e6dd0cc1a8cec06195bc1`，
closure SHA为
`6f7324797716c70f54c6aad3c1a63c5fc9b9aad1b03e836cbb3d394078e0cc99`。
相对786项实际新增436个目标Toggle方向，Line/Condition/Branch/FSM新增均0。
随后父端完成17项准入工具测试、实际prepare/verify及显式admit，正式准入787项。
准入目录为`csr-satp-sepc-offline-admitted787-parent-20261008-01`，manifest SHA为
`aaef43fef3b8da3a1e854e4907b0823a3488270ddb8b7ae5af0c21be5cb8d5fc`。
父端再次独立核对全部6162个指标实例的按位OR、原786项前缀、唯一VDB列表和
输出哈希通过；不以局部方向数量换算全局百分比。
父端另行重核完整资格/closure的10073个输入与输出pins通过，全部30笔
native CSR owner及core/closure哈希关系一致。

entropy64完整离线资格通过，qualification SHA为
`797b412536fc0235cb511b631a9c01db48af0793060d68366bef9879739fc0e9`。
父端重核10005个资格输入/输出pins通过。严格3326条指令、1646次GPR写、
903次访存、390checks均通过；新增7个Condition点位于scalar divider LZC。
两个目标scope的serialized Toggle新增为0，未知MDA方向仍不计增益。
因此停止相似regfile数据模式追加；该结果仍未正式准入，后续需相对787顺序去重。

entropy64的788项准入后继已由父端完整阅读，14项工具测试通过，实际verify通过。
准备seal为`2626e47a6034149b558d8f42cc257a60cc6f724b8594033c3e46d2fa02c8eeb3`；
显式admit正常完成，正式集合增至788项；目录为
`scalar-entropy64-offline-admitted788-agent-20261008-01`，manifest SHA为
`cf59a7fd898c33493f662b247448d52642b694a6cce68785e938f20112d12641`。
父端另行独立核对输出哈希、789行唯一输入清单（含编译VDB）、原787项精确前缀及
全部6162个指标实例的有界按位OR通过。重算实际新增Condition7，其余三指标新增0。
新的整体百分比仍待统一DVE报告，不能从PASS数量或局部增量推算。

被动CVXIF UVM监视器边界的源码和编译身份检查由父端14项测试实际通过。
下一次整体DVE仅考虑精确两个验证scope：`i_ara_cvxif_dut_bind`及其私有`cvxif`。
它们只读取DUT，不驱动功能信号；运行中的断言、scoreboard和全部硬件功能模块保留。
这是DUT评分范围修正，不是新激励命中；尚未创建或应用新EL，不提前报覆盖率收益。
静态残差排序已移除无法精确扣除旧掩码的partial-EL对象，避免将已豁免的高位再次
当作动态缺口。未知MDA编码不用于推算方向或全局百分比。

本轮AMO候选的端到端核查撤回了直接运行方案：虽然CVA6配置RVA=1且九个
AMO数据对象有1152个未命中的serialized坐标，但冻结SoC的L2前置
`axi_atop_filter`明确将ATOP原子写响应为SLVERR。已封存的
`gap60-cache-atomic-analysis-20261004-01/frozen-system-chain.json`还证明RMW
返回零且不写L2，cache的ack/result接口没有相应异常通道。
因此在L2运行AMOSWAP成功测试不能与Spike架构结果一致，不能为覆盖率先运行后
放宽检查，更不能仅因当前SoC不支持就豁免宣称支持的RVA功能点。
本轮未启动该测试、未改RTL；转为核查可独立比较的MMU/AKV异常地址和固定配置字段。
LR-only历史资格不能代替RMW或SC的正确性证据。

788项整体报告后继处于冻结前审查，不能用早期host-plan seal批准DVE。
父端发现并要求补齐三项入口约束：输入清单必须逐项等于raw bitmap的tests；
原生snapshot选择必须复用已验证的`capture_cvxif_passive_two_scope770_v2.tcl`
（旧版`gui_list_get_selected -meta`不受当前DVE支持）；最终资格必须封存全部
observer的阶段TSV、columns和metric availability，而不只记录整体百分比文件。
还需核对786/787/788后缀对所有继承恒定字段的零命中证据，及精确两个observer之外
的所有物理豁免掩码不变。报告工具审查不是新的DUT覆盖率，EDA尚未启动。

下一动态候选是AKV的两次Sv39叶页故障：K payload地址分别为
`0x0000001555555550`和`0xffffffeaaaaaaaa8`，都canonical且8字节对齐，
XOR为`0xfffffffffffffff8`。预期验证bit3..63的虚拟地址/异常tval传播，
不把bit0..2作为目标；descriptor/Q/V合法，仅K叶PTE无效。
新软件和预检尚在准备，实际异常owner、精确custom PC、cause13及tval、
映射恢复重试、context释放、源数据和guards均必须核对。Spike只可验证其标准
标量/特权部分，自定义AKV操作必须另用独立原生结果与事务检查；尚未运行或准入。

父端已完整阅读`audit_constant_suffix788.py`及测试，并实际重放生成
`constant-families-suffix788-parent-20261008-01.json`，SHA为
`fa9687f8f1389cadc7656f167d3e6d996b3264b3afaa4b11b8c1acc5ae509029`。
新增786/787/788样本对RR190的22528方向、CLASS_PADDING的5316方向及
FPNEW90的8520方向均零激活；这证明继承的精确恒定豁免未被新样本推翻，
不代表新增覆盖率。父端本轮suffix/report工具合计23项测试通过。

AKV双地址软件预检已完成：12288个主机参考word精确匹配，Spike的软件参考
退休174413条指令，每个地址检查5680个word与两次标准trap。
产物`akv-canonical-kfault-preflight-agent-20261008-01/preflight.json`明确标为
`AKV_CANONICAL_KFAULT_HOST_SPIKE_PASS_NOT_DUT_QUALIFIED`，没有声称Spike执行AKV。
父端完整阅读预检实现；RTL运行/原生自定义事务检查仍待冻结与审阅。
时间预算须在运行前依据软件规模决定：历史单阶段GAP71 QBS的终态耗时322.372秒，
不能盲目把双阶段上限定为540秒后等待超时；也不由未完成的失败样本推算精确完成时长。
保留全部检查，采用事先说明的预算或独立并行阶段，不修改已封存预检。

独立候选评估：GPR/FPR历史原生比例已为97.28%/99.96%，不能用单测试MDA
比例推断整个集合的大块缺口。因此不再准备全寄存器新激励；QBS K1 ROW
静态候选仅12方向，也不优先消耗仿真预算。后续改按最大绝对缺失Toggle方向
选动态场景，不以模块低百分比或静态候选上界承诺全局收益。

FCLASS/DIV/SQRT已由父端独立verify后正式准入，集合增至784项PASS。
目录为`fclass-divsqrt-offline-admitted784-agent-20261008-01`，
admission-manifest SHA为
`721845f0b7423db3346fbf62f77970351a1640eefc8e2a87a307f3e0ec95bb4e`。
完整继承783项前缀，6162个指标实例按位OR，未重复ELF/VDB；
新增Line25、Condition166、Branch65、FSM0个原始覆盖点。
VALU完整架构检查通过，785项准入工具的父端5项测试及实际verify通过，
父端授权后正式准入`valu-restart-offline-admitted785-agent-20261008-01`；
admission-manifest SHA为
`10273c45e4a4eb21929e0599a2bfc27bfb76afb2b36fe547de0198b5ee918cf5`。
相对于实际784项重算仍新增422个目标Toggle坐标，四Lane分别90/110/110/112，
新增Line1、Branch1、Condition0、FSM0；完整保留784项前缀，未重跑仿真。
QBS两阶段M4仿真正常退出0，但尚待完整离线资格检查，不能计为PASS。
首次离线资格结果为`TWO_M4_QUALIFICATION_HOLD_NOT_ADMITTED`：
检查器错误调用`targeted_toggle_evidence.xml`，该模块无此接口。
这属于检查工具接口错误，不证明RTL故障；保留原失败和冻结输入，
仅准备新的离线检查器并补充真实XML/原生身份测试，不重跑VCS。
XML后继检查器的父端9项真实样本与负例测试通过，复用原仿真完成离线资格。
结果`qbs-pending-two-phase-m4-qualified-xml-successor-agent-20261008-01`，
qualification SHA为
`f8198c6920c9afed0f787c2e439978164cf423fb22ef12d820da28a66d3a5736`。
完整8192字节VRF、24个CSR值、24832字节源/保护区域、18个后端活动、
46个架构请求/响应均核对，独立整数结果准确，观察到hit13下降沿；
相对783项实际新增96个局部payload Toggle坐标。
这是自定义计算的原生功能资格，不是完整标量ISA或custom Spike PASS；
仍未正式准入，需相对最新785项去重及重算增益后才能加入786项集合。
全局正式百分比仍以下方783项报告为准；新增准入数不能直接换算新百分比。

新的785项单次全局汇总已通过父端完整源码审阅、17项工具测试和实际check。
配置目录为`current-population785-rr190-prepared-agent-20261008-01`，SHA为
`796fbe9f3c009b8b6aed24b840d3699a965a9e257341757e5615d6b08b997a49`。
宿主机服务`ara-current-population785-rr190-parent-20261008-01.service`
已启动，主进程839594为真实Python校验进程，cwd与服务cgroup已独立核验。
先再次检查封存输入，再进入DVE；此时不能把Python进程宣称为实际DVE。
汇总同时继承全部旧豁免并加入已原生验证的RR190恒定22528方向，
非目标对象、原FSM、所有旧物理掩码和784/785后缀零命中检查均保留。
待五阶段原生报告完成并独立verify后更新正式百分比；不轮询长任务。
实际DVE进程841386的exe、cwd与cgroup已由父端直接核验，
已进入真正的DVE汇总，不再仅是Python封存输入校验阶段。

下一批动态缺口由独立工作项准备：SATP/SEPC合法M态元数据读写矩阵，
以及非零vstart的整数mask比较。都先进行独立软件gold与Spike预检，
从实际785项原始位图扣除已命中位，再决定DUT投放；候选位数不作为收益。
不执行高地址、不访问虚构页表，不修改RTL，不豁免真实动态字段。

QBS两阶段正式786项准入已完成：父端完整源码审阅、13项测试和actual verify
通过后授权发布`qbs-two-phase-m4-offline-admitted786-agent-20261008-01`，
admission-manifest SHA为
`384c2b5b364f41a49968aac913b8e0904b5fe2f83c5af818af3afe535d864904`。
真实status明确`aggregate_passed=786`、`baseline=785`，完整保留785前缀；
重算新增96个payload Toggle方向和8个Condition覆盖点。
继承的发布函数终端文字仍打印`ADMITTED785`，此文字不是集合数量权威；
应读取封存manifest与status。自定义原生资格边界保留，不冒充custom Spike。
正在运行的785项全局DVE报告不取消、不改输入；786项将在后续新集合汇总中吸收。

mask比较的独立软件预检已通过1905checks，三个vstart为4/8/16，
完整初始化源及prestart位，精确校验VL/vtype/vstart/vcsr/fcsr和源/目标guard；
未消费的mask-tail不强制与Spike字节相等。预检封存SHA为
`f2bf92408da3ce248ca5ceee57e9628e5e7375b9f7addbb9a2cb79699f01fdc5`。
尚无DUT启动；必须准备严格标量/向量/CSR/原生上下文收集器再授权。

SATP/SEPC短矩阵的父端源码审阅和17项软件测试通过，真实Spike预检封存为
`csr-satp-sepc785-preflight-agent-20261008-04/preflight-manifest.json`，SHA
`530f6b46bca0b9007642628beab66f2a663a8e8072eb7f2024e26b8406cd7ed2`。
673条退休、168次标量访存、44checks、42个64位观察值，矩阵CSR访问30次；
整个测试保持M态、MPRV/MIE为0，不执行SRET/MRET，不访问被写入的高PPN或SEPC。
SATP恢复Bare、SEPC恢复原值，guard只读；仅软件资格，尚无DUT PASS。
初次软件失败保留：参考C扩展配置不一致及数组初始化意外产生RVV，
最终使用匹配参考ISA、明确无隐式向量化编译；未放宽架构gold。
运行/收集器正在准备，授权前必须完成全标量ISA/内存、原生CSR上下文与VDB检查。
父端已对最终真实Spike文件独立核验全部输入/输出pins并重放独立CSR期望，
673条退休、44checks、30次CSR访问、168次访存完全一致；未增加DUT PASS数量。
父端在DUT启动前发现原生CSR检查器的假失败风险：`csr_buffer`收到`csr_valid_i`
时即记录请求，同周期`csr_ready_o`可能因本次valid而变0，不能把ready当作
当前请求的接受门控。要求按实际单项缓冲占用、同周期old-commit/new-issue交接
建立owner，并单独验证ready逻辑；补首个issue-ready0合法、占用未释放重发非法、
同周期提交及接收合法的测试。此为收集器语义订正，不是RTL故障或运行重试。
旧CSR准备01早于ready语义修补，父端verify明确拒绝pins/source_contract漂移；
保留未运行01，不覆盖旧准备、不把它视为DUT失败。
最终冻结准备02的父端35项运行/收集器测试及actual verify通过，seal为
`642d106324512b604d588a8a8bc003f0f3225b8fc126c36ccf70ec11d7d6d146`。
已授权宿主机服务`ara-csr-satp-sepc786-parent-20261008-01.service`，
输出`csr-satp-sepc786-old-image-agent-20261008-02`；180秒仿真、240秒服务上限，
绝对Python依赖及明确VCS环境，不编译、不重试、不修改RTL。
启动器记录实际simv862574的exe/cwd/cgroup校验；父端读取记录时仿真已结束，
不能声称父端又核验了存活进程。console显示完整VCS覆盖结束，CPU为17.470秒；
尚待完整终态检查，不能提前计为PASS或推算覆盖百分比。
CSR仿真实际墙钟31.734秒、退出0且无超时。父端独立对真实trace重放通过：
673退休、168访存、44checks、30个期望CSR事务，零标量差异。
首次完整collect保留为`csr-satp-sepc786-qualified-agent-20261008-01`，
首失`Exact CSR probe declarations`：VCD实际仅保留packed父对象
commit_instr_i438位、mstatus_q64位、fu_data_i207位、csr_reg_q13位，
未展开七个所需子字段。这是波形绑定问题，未证明DUT错误。
要求独立后继离线解码器按冻结源码精确布局及实际VCD宽度提取字段，
保留全部30-owner、ready、提交/发射交接检查；不重跑仿真、不删除检查。
在原生owner闭环前不发布gain、不准入PASS集合。

非零vstart比较的第二位源审阅指出old-vd潜在地址问题：冻结lane_sequencer的
MaskB只有mask-logical和carry范围将vstart清零，VMSLTU不在这些枚举范围内。
MaskB为EW64，generic per-lane vstart1/2/4直接成为word偏移；
保留prestart mask应从首个packed-mask word获取，当前全零v1会掩盖前两项，
偏移4还可能读取未初始化的v2。因此原始预检不能用于声称此DUT路径正确。
不启动该版本；准备独立后继刺激，完整初始化v1/v2为不同word模式，
严格检查prestart与active位并采集真实MaskB地址/读取/merge信号，先辨明根因。
此刻仅是源码风险，不是已实测RTLbug，不修改冻结RTL。

QBS候选2368方向仅为静态上界；真实新增96中84落在候选内、12在外。
剩余2284候选不能据此证明不可达。phase1实际partial42次，
残留mask仅ff00/fff0/f000各14次；slot1还受slot0选中word约束。
已确认hit13下降来自不同ctx的新pending替换旧pending，不是清valid清空metadata。
以后改变profile/合法基址余数前应先给出新残留mask及word-match见证，
不能同一Q6/M4/K2仅换随机数据便声称将覆盖剩余候选。

## 当前已验收整体报告（783项）

最新整体报告为`current-population783-classpadding-parent-20261008-01`，
状态`CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED`，实际选中783项PASS。
原始Line/Condition/Branch/FSM/Toggle为85.25%/82.18%/83.00%/70.68%/64.96%；
精确豁免后为85.22%/82.19%/83.65%/81.09%/71.75%。Toggle距80%仍差8.25个百分点。
上述数字来自DVE原生全局报告，不用局部覆盖位数推算全局分母；仍对应冻结旧镜像。

`fpnew-class-padding5316-local-prepared783-agent-20261008-01`已正常退出，
父端独立verify通过。状态为`CLASS_PADDING5316_LOCAL_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED`。
这些是编译配置和源逻辑证明的恒定分类填充位；最新整体已完成五阶段验收，
父端独立verify也通过，qualification SHA为
`827565bba59ccf990845367f102cb1ecc6a0ebb68b5eb2b044c3e411c67e6100`。
相对于前一783项报告的71.62%增加0.13个百分点，原始Toggle64.96%不变：
该变化是精确豁免收益，不是新激励运行收益。
下文保留过程记录；其中“尚待执行”等历史状态以本节最新验收结果为准。

本轮父端工具测试26项通过（VALU预检12项与FCLASS/DIV/SQRT运行及收集器14项），
FCLASS/DIV/SQRT的实际封存配置verify通过，准备SHA为
`dfc6b43127ef5053bc0164280690451232687a2a6b66dea3af296ac2fcbce153`。
已在宿主机后台启动服务`ara-fclass-divsqrt783-parent-20261008-01.service`，
输出`fclass-divsqrt783-old-image-agent-20261008-01`，仿真上限900秒。
实际simv进程795112的exe、cwd及cgroup均已核对。使用原冻结镜像，
不重新编译、不重试、不修改RTL；75个有限定向单元尚待DUT严格校验，
未计入783项集合或任何覆盖百分比。

合法QBS两阶段M4场景的父端8项独立测试通过，零skip；非法M8/ROW拒绝且目标不变，
19项篡改/非法输入负例通过。Q2_K和Q6_K的gold来自独立打包解码及整数计算，
并交叉核对参考模型。合法映射候选上界2368方向，不代表DUT覆盖增益。
该场景尚无DUT PASS、尚无custom Spike支持，不纳入统计；继续准备原生请求、
完整VRF/CSR/源及目标保护检查后才启动一次有界测试。

分类填充位全局继承工具的父端14项测试通过，原FSM记录和所有旧物理位排除完整保留，
新增精确5316方向；低10个有效分类位、整模块排除、重复位和校验码漂移负例均检查。
父端独立prepare及actual check通过，目录
`current-population783-classpadding-parent-20261008-01`，配置SHA
`1250b130e7b16a0f883b098dc6559752506858971be73324810573b58d55202e`，28814个输入指纹。
服务`ara-current-population783-classpadding-parent-20261008-01.service`已后台启动，
原生DVE预算3600秒，服务硬上限4800秒。此时服务正在再次校验封存输入，
不能提前声称DVE实际进程已出现或整体新百分比已验收。Agent独立prepare仅保留，
不启动第二路重复报告。终态通过五阶段原生检查后才更新整体百分比。

全局分类填充位报告实际DVE进程803715的exe/cwd/cgroup已由父端核对，
服务内再次封存检查后已进入原生汇总阶段，尚无新合格百分比。
VALU高vstart运行/收集工具父端17项测试通过，准备seal为
`e12aea6614770fce27f26a27be83c9e185a79cdd765f65c16c88635dd62fa568`，
actual check通过。已授权服务`ara-valu-restart783-agent-20261008-01.service`，
输出`valu-restart783-old-image-agent-20261008-01`，900秒仿真、960秒服务上限。
四项VCS环境与准备配置一致，Python依赖均用绝对路径；不改冻结RTL。
12条高/零vstart VADD及完整前后快照尚待DUT验收，422方向仅是候选上界。
VALU实际simv进程804413的exe/cwd/cgroup已由父端核对。

最新783集合剩余字段重排已完成，依据已合格EL而非历史百分比。
`rr-disabled-formats783-residual-agent-20261008-01.json`绑定30个实际编译caller：
190个禁用格式输入字段、22528个恒定方向是源证明候选；父端5项源证明测试通过，
尚待DVE原生局部资格，不纳入全局数字。启用格式、top仲裁及5160个非目标对象保留。
另有2000个partial/struct及5647个MDA对象继续HOLD，不猜测位映射。
该重排还显示CVA6、CSR、scoreboard仍有明显动态/配置缺口，下一步按实际字段值域
选取合法定向场景，不通过整模块豁免消除这些缺口。

FCLASS/DIV/SQRT后台仿真已正常退出0，未超时，wall为636.7145秒；
原生VCS覆盖采集完整结束。状态仍为`SIMULATION_EXITED_NOT_ADMITTED`，
严格完整架构收集未通过前不能标记PASS、追加VDB或更新覆盖百分比。
新合法M4场景运行准备工具的父端7项测试通过；该封存版本明确
`collector_ready=false`，不会据此直接启动或准入。
父端另外复核190个禁用格式输入：22528方向全部在783原生OR中未命中，
30个编译caller及5160个非目标对象保持绑定。此检查支持局部资格准备，
不能替代DVE原生排除验证。

FCLASS新收集器首次离线验收拒绝，原因是调用旧C910 store上下文恢复器，
其硬编码48次store，而本次矩阵为75组。父端独立读原始native trace：
75个alloc、75个done、75个唯一owner，EEW/VL=(1,16)/(2,8)/(3,4)各25，
alloc/done的owner、VID、opcode、use_vd、vd、EEW、VL、vstart完全匹配。
这是当前可确认的检查器绑定不匹配，不能据此声称RTL错误或DUT完整PASS。
保留原failure，另行恢复本场景store上下文，不重跑VCS，不跳过架构检查。

190字段局部原生工具父端14测试及实际check通过。目录
`rr-disabled190-local-prepared783-agent-20261008-01`，配置SHA
`1bb663d10d36b8040b5000b1ff301d93095bc5f983f143054a9001ffd40033b4`。
服务`ara-rr-disabled190-parent-20261008-01.service`已后台启动，DVE预算5400秒，
服务5520秒；此刻仍需等待实际DVE身份及完整五阶段终态资格。
22528方向仅为静态候选，不能提前加入整体覆盖数字。
父端已核实此局部任务的真实DVE进程812108：exe为当前VCS DVE，
cwd为该独立输出目录，cgroup归属`ara-rr-disabled190-parent-20261008-01.service`。
新store75检查器审查还识别出独立发布风险：`life.save`使用独占创建模式，
不能再次写入已经生成的core qualification。后继必须用独立sidecar绑定原core
结果SHA、恢复证明和检查器指纹，而非覆盖原合格结果或重复仿真。

store75后继父端7项测试通过；复用原636.7秒仿真日志，一次离线完整收集合格。
目录`fclass-divsqrt783-qualified-agent-20261008-02`，core资格SHA
`847a1483c8f02b27e32e07abec9b10684218b36d8ac1dffac4a4e61927a9985b`，
独立closure SHA`217b3858b56b19744990b0398756f51ae0e2b76f29e3271e1608d1b5ddbc77ee`。
165928条指令、30460次完整访存（含19648次compressed）、228向量请求、
11136比对字节、75单元2251 checks和452 CSR均通过，unknown/非bitexact为0。
相对783集合实测Line+25、Condition+166、Branch+65、FSM+0；预先绑定236个
Toggle目标命中220。该220是目标子集，不是全芯片总增量或全局百分比。
此资格尚未正式准入，集合仍为783项；准备一次准入及联合后续报告，避免重复全量汇总。

RR190局部任务正常退出0、未超时，父端独立verify通过，资格SHA为
`303c6e64596d0cfb7dd6bcc201dadecb2673471633a178fadc19bc28c4957152`。
完整五阶段、190字段22528方向、5160非目标对象保护与原生EL保存/重载/复位均通过。
状态`RR_DISABLED190_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED`；这批未加入71.75%全局数字。

VALU场景正常退出0，耗时850.9158秒。严格架构资格
`valu-restart783-qualified-agent-20261008-01/qualification.json`，SHA
`97f0d2d0b5e2846d83f9e4bc7eb6d042bdc8b3b2d73f91b6f1be7a377c7770fa`。
170167指令、13144 checks、98304字节前后快照、3072目标保护字节、3200源保护
字节和60 CSR通过，unknown skip为0。相对783的422预定Toggle缺口全部命中；
仍是局部原生子集增量，正式准入和相对于下一集合的去重增量待验收。

父端独立运行fclass准入9项及QBS新运行/收集12项工具测试，共21项PASS。
QBS实际collector-ready封存配置verify通过，seal
`8db9ab6f8f66508675302457dd1ddd3b12ac93e860fd4f3dd4efb8831b8b41e4`。
已授权唯一服务`ara-qbs-two-phase-m4-783-parent-20261008-01.service`，
600秒worker/660秒service，输出`qbs-pending-two-phase-m4-vcs783-agent-20261008-01`。
使用只读双bank聚焦VPD，64MiB上限，无force、不改RTL。两阶段gold/native/CSR/guards
和完整波形FIFO守恒需全部通过才可准入；无custom Spike/full scalar ISA声明。

### 本轮补充进展（各项准入状态见说明）

- FPnew常量字段的局部原生核验已经启动，服务为
  `ara-fpnew-tied90-parent-20261008-01.service`，目录为
  `fpnew-tied90-local-prepared781-agent-20261008-01`。父端9项工具测试
  和封存配置检查通过，配置SHA为
  `60aa913eeb09637030ed08204c57b133a324c7cd4ffc5d3433d2afe839331f57`。
  实际DVE进程757382的exe/cwd/cgroup已核对，非仅检查启动脚本。
  70个scope的90个字段共8520个方向，只涉及32个FMA/18个Cast
  的常量零舍入ID及禁用格式占位字段。原生应用、保存、复位、
  重载、最终复位及非目标对象保护尚待终态验收；当前未计入
  整体百分比，不是激励收益，也不豁免动态功能路径。
  此局部任务现已终态：DVE正常退出0，但启动环境中的Python
  依赖路径为相对路径，切换到输出目录后`before`阶段导入
  `elftools`失败，封装验收退出1。环境过滤代码保留PYTHONPATH，
  不能将此归因于DVE删除变量。同一输出目录下独立导入测试
  已实证：相对依赖路径失败，绝对依赖路径成功。
  全部70个scope原生before表已取得，父端在明确依赖路径环境中
  离线运行同一封存检查器，`before_PASS`。失败发生在应用豁免
  之前，cleanup-empty.el为空；8520个方向仍未资格或全局应用。
  下一步在新输出目录启动同一封存工具，明确使用绝对依赖路径，
  不修改RTL、原失败记录或封存工具，不增加无必要的适配层。
  此启动修正现已完成：同一实际输出cwd下原封存检查器返回
  `before_PASS`；父端新目录`fpnew-tied90-local-prepared781-parent-20261008-02`
  的prepare/check通过，配置SHA为
  `dc049f1066dc8c6451b981ed9323edc3e3a6e422ad69d055a805733cad9cc71d`。
  服务`ara-fpnew-tied90-parent-20261008-02.service`已启动，实际DVE
  766436的exe/cwd/cgroup及进程环境中的绝对Python依赖路径
  已核验。尚待五阶段终态，不计入整体覆盖率。
  Agent另行完成的`fpnew-tied90-local-prepared781-agent-20261008-02`
  仅保留为未启动准备记录，不重复执行。
  父端02现已完成：原生DVE和服务均正常退出0、未超时，
  日志包含完整`FPNEW_TIED90_FIVE_PHASE_DONE`；父端独立执行
  同一封存工具的verify，返回`verify_PASS`。局部资格receipt为
  `fpnew-tied90-local-prepared781-parent-20261008-02/capture-result.json`，
  SHA为`274aed0cee5a274fd65ffbada559b32a1c0b9227010ee1464eb3d806052ee669`。
  350份原生对象表、450条精确目标排除标志、保存/重载语义一致、
  非目标对象保护及三个空EL复位均通过，773个文件指纹封存。
  状态为`FPNEW_TIED90_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED`：8520方向
  已具备局部资格，但仍未全局应用，不能替换781项整体百分比。
- 783项加FPnew90整体消费者的真实EL测试识别出跨指标误判：
  祖先VMFPU的60条FSM记录（52条Transition、4条State、4条header）
  被旧检查器当作整模块Toggle排除。修正仅允许严格语法、机器归属
  及校验码匹配的FSM记录与Toggle新增项共存，保留完整旧EL；未知
  记录、整模块排除、重复物理位、字段父子冲突和校验码漂移仍拒绝。
  父端13项工具测试通过，包括实际781+9700与原生FPnew90的并集。
  新整体汇总目前在离线prepare阶段，尚未启动EDA或产生新百分比。
  后继02已由父端完成实际check并启动，目录
  `current-population783-fpnew90-prepared-agent-20261008-02`，config SHA
  `cd90ea43f021b88ae42eab1ab60c8112c7e92bc1201b5a11f1a8bd3d1cf9edae`。
  服务`ara-current-population783-fpnew90-parent-20261008-02.service`的
  实际DVE785134已核对exe/cwd/cgroup；保留完整783项和既有EL，
  本轮新增8520个局部资格方向。仍待整体五阶段终态验收。
- FPnew分类padding后继候选：31个scope、62个对象、2658位，
  共5316个方向。逐编译格式求向量/标量两条mux路径的动态位并集，
  仅排除其补集，不按当前vtype或一个格式泛化；所有低10位分类槽、
  其他字段及数组受保护。父端9项源代码测试和62个文件指纹通过，
  10项局部工具测试及实际check通过，配置SHA
  `0f5f5d968572f5402ffe8baa653d7bee54bf60df252cb6b335fd8575ea91cc3b`。
  目录`fpnew-class-padding5316-local-prepared783-agent-20261008-01`，
  服务`ara-fpnew-class-padding5316-parent-20261008-01.service`，实际
  DVE784591的exe/cwd/cgroup已核验。尚未取得局部资格或全局应用，
  不声称原始位图序列化映射已校准，也不计入百分比。
- FCLASS/DIV/SQRT有限矩阵已完成独立gold和Spike预检：FP16/32/64
  的75个单元、2251项检查通过，165928条退休指令；父端15项工具
  测试通过。只绑定236个真正分类位的未命中方向，不将padding或
  未证明的DIV/SQRT增益计入预测。DUT运行和准入尚未完成。
- QBS两phase后继的主机预检发现原静态候选遗漏准入约束：M>=5
  必须使用M8-interleaved activation，M8+ROW被reference以code7
  拒绝。尚未生成成功ELF/manifest或启动VCS；原4120方向映射交集
  不能视为合法执行收益上界。保留HOLD记录，按合法M4/ROW重新
  核查所有descriptor条件及实际映射，再准备后继激励，不修改RTL。
- 新增普通RVV动态候选为VALU高vstart重启：e8/m8/VL1024，
  1020→0→1020，每条vadd前重新写vstart；检查1020字节前缀保持、
  活动字节结果和CSR。4个VALU scope的45个对象在合法低8位内
  尚缺422个方向槽，这是候选上界，不是实测增益。当前在准备
  独立gold/Spike预检，尚未运行VCS或准入。
- 正向QBS K2/ROW测试已正式准入783项，目录为
  `qbs-k2-pending-offline-admitted783-agent-20261008-01`，manifest SHA为
  `8d0d58bf873e0b0f4c601d1e9fb88fca74babb572f822a0580967eef9e5d23f0`。
  父端11项准入测试、实际verify及admit通过，保留完整782项前缀、
  6162个实例的精确OR与所有既有增量记录，VDB/ELF去重通过。
  新增214个载荷映射Toggle方向、37个条件覆盖位；行/分支/FSM
  新增0。FIFO归属由实测信号重建、write_req由源码推导，不能
  冒称全部直接波形或完整标量ISA Spike比较。整体百分比待汇总。
- 781项加9700个精确方向的整体DVE汇总已启动：
  `ara-population781-plus9700-parent-20261008-01.service`，输出
  `current-population781-plus9700-prepared-agent-20261008-01`。
  父端8项测试及封存配置检查通过，配置SHA为
  `8a501ebe03d577ff93a84096baa63ca1d88eb0e30fb248499e5bcd60fb63fd73`。
  9700包含先前已应用的BTB132/QBS128和新增QBS9440；不能称为
  9700个新增激励命中。正式新百分比须等待完整汇总验收。
  此任务现已正常退出0且未超时，全部五阶段终态校验通过。
  781项实际选中，精确EL并集、所有其他位保护、raw/reset/final
  一致和applied/reloaded一致均成立；权威结果见下表。
- DTLB权限测试的离线后继检查器已通过，父端8项检查通过。
  `dtlb-permissions-qualified780-scalar-agent-20261008-01/qualification.json`
  SHA为`603ee851e1f9e505805a7f113263ebe9827bb8cf1c74ebcb4e0e879e687ee38d`。
  193080条指令、19857次完整访存、5次MMU权限故障与handler的
  cause/PC/tval/权限状态及周期归属均核验通过；零向量请求按
  UNOBSERVABLE_ZERO_REQUESTS记录，不能冒称向量功能覆盖。
  父端9项准入检查通过后已正式准入782项，目录为
  `dtlb-permissions-offline-admitted782-agent-20261008-01`，manifest SHA
  `a52004d8882b5101d823d6dd647b7fb20c7c25a544abc96d15cb6f85d36d50b8`。
  保留全部781项前缀及6162条实例精确OR，VDB/ELF去重通过。
  相对781新增238个DTLB属性Toggle坐标，行/条件/分支各新增2，
  FSM新增0；不是整体百分比。无需重跑VCS，RTL不变。
- 正式781集合的QBS残余分析发现主/侧载荷映射分别仍有9585和
  8816个方向属于映射可行但仲裁可触发性待证。共18401个方向
  保留为HOLD，优先补正向激励，不能因未命中直接豁免。
  分析产物为`qbs-residual781-typed-ranking-agent-20261008-01.json`。
- 新正向激励候选：Q2_K/Q8_K、M4/N8/Kblocks=2，两侧ROW_MAJOR，
  权重基址为16字节对齐缓冲区加10，activation基址16字节对齐。
  权重1344字节、activation2336字节、32个FP32输出。
  静态预计111个hit位的222个缺失方向；此为预测，不是实测增益。
  判据为context2/block1的activation范围A+1460：首拍first_lane=4、
  take=12；若offset28的后续拍先获准写word0，保留b8..15，
  pending.strb=0xff00。须同时抓更旧pending的有效位、地址和strb，
  以及slot0 write_req/slot1 selected_word，验证这一仲裁前提。
  旧槽选择word1时，b13对应quant字节37、byte_lane5，应置hit[13]。
  同时观察range/tag、offset、take、remaining、selected_word及
  word_match，检查保留byte编号而不是仅检查最后结果。
  普通vle32预载避免已记录的异常EEW路径；整数解包/dot/min为
  独立gold，保留VRF/CSR/源/guard/tail检查。先静态复核与预检查，
  后进行单次代表仿真；尚未启动，不计入合格集合。
  独立复核已确认上述具体hit的两个原生方向21532/21533在781项
  OR中均未覆盖，ABI和字节映射符合冻结源码。其余预计方向仍需
  单独去重及实测；plane2在此是activation主数据，不是side字段。
  此激励现已通过父端6项fixture检查、6项运行环境检查及封存
  配置verify，已启动`ara-qbs-k2-row-pending782-parent-20261008-01.service`。
  输出为`qbs-k2-row-pending-old-image782-agent-20261008-01`，prepared SHA
  `9ec4782319fbac9cb42e82464cef2a7c410ea3017cf8f73f471470005b047932`。
  父端直接核验/proc中的simv PID738836，冻结镜像、独立cwd和
  服务cgroup均一致；probe READY，QBS seq1显示success=1/fault=0、
  busy_cycles=961。此为运行进展，不是完整软件PASS或覆盖准入。
  保持600秒仿真预算、660秒外层预算及64MiB波形限制，无自动重试。
  仿真随后正常退出0，软件打印checks=6/errors=0和PASSED。
  离线检查通过完整native VRF/CSR/源/guard后，在探针诊断门拒绝：
  未锚定的PROBE_REJECT正则匹配了控制台回显的Tcl源码第80行，
  并非实际错误输出。实际probe READY在第126行，软件检查位于
  第145/146行。保持原collector与仿真封存，后继检查器仅修正
  实际诊断行识别；不重跑VCS，不把此次拒绝判为RTL故障。
  正式准入仍须后继资格、周期仲裁证据和相对782的原生OR增量。
  父端4项诊断门检查通过后，核心资格文件已生成，SHA为
  `376472de5f4ad629a48c64d5d4f88f5fa3cbf36af2a231db2713d027741e0b2e`。
  当前目标sample为21532命中、21533未命中，不能声称全部222方向
  已达成。后继包装最后一步尝试通过open(x)重写核心资格文件而
  拒绝；保留完整核心证据，另建诊断修正receipt，不覆盖该文件。
  仍需周期判据及实际OR增量验收，尚未正式准入。
  后续诊断sidecar的父端4项测试及实际record重算均通过，SHA为
  `14b6139515b2def5482bb89cc009cdbbba9a8d61a3202bcbf29b2a39005ed0c8`。
  原核心资格SHA保持不变，修正了出版流程，不改变功能检查范围。
  父端随后重算VCD周期链和相对正式782的双bank原生OR，均通过：
  实际新增214个payload方向（bank0=186、bank1=28），重点目标
  新增21532，21533未新增。此为真实激励增益，不是豁免变化。
  VCD单位100fs；20325000处新槽选word0、剩余0xff00，20335000
  处旧槽仍保留原b13、选word1、hit=0x2000，源byte13=6。
  write_req的部分直接对象及unpacked source未进入VCD，不能称为
  直接抓取；请求条件依冻结源码推导，source1 owner依完整FIFO
  push/pop/count重建并核验。产物目录为
  `qbs-k2-row-pending-cycle782-agent-20261008-01`。尚待正式准入783。

- BTB固定地址bit0的132个方向已完成独立原生五阶段核验。
  `btb-bit0-132-native-v4-prepared779-agent-20261008-01/capture-result.json`
  状态为`BTB_BIT0_132_LOCAL_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED`。
  8860个其他方向保持不变，应用与重载一致，清理后恢复原统计；
  后台任务正常退出0。此为结构不可达豁免资格，不是激励收益。
  后续780项整体报告已应用该132方向，见下表与权威报告。
- QBS已有128个方向的局部原生资格，同样尚未应用到整体统计。
  两组不得手工折算新的整体Toggle百分比。
  后续780项整体报告已同时应用这128方向和BTB132；此前未应用
  的描述属于局部资格阶段，不代表当前整体报告。
- DTLB权限矩阵的第三次软件预检查通过：
  `dtlb-permissions-preflight779-agent-20261008-03/preflight.json`
  状态为`SPIKE_SOURCE_PTE_CSR_TRAP_GOLD_PASS_NOT_DUT`。
  8378项检查仍需RTL仿真、原生更新探针及严格比较后才能准入。
- AKV tile-range测试软件预检查通过；实际RTL结果尚未取得。
  父端检查新运行比较环境发现旧独立模型不支持实际ELF中的合法
  `MUL x7,x6,x7`（PC `0x80002034`，编码`0x027303b3`）。
  只在本测试的模型中补齐低64位乘法及完整退休记录，不改旧模型、
  ELF或RTL；18项运行环境检查通过，含符号/溢出/寄存器别名检查。
  实际软件检查数为3872，早期3864描述不作为准入依据。
  后台VCS已启动`ara-akv-tile-range780-parent-20261008-01.service`，
  输出`akv-tile-range-old-image780-agent-20261008-01`，prepared SHA为
  `569ea772b7e53268aa5276ff1b4f1aa1e4ce7e546bd9d138cccc8149e5f46623`。
  启动时核验实际simv PID689132、冻结可执行文件及独立cwd，日志
  已显示正确ELF装载；600秒仿真上限、660秒外层上限，无自动重试。
  启动证据不等价于终态PASS，尚未准入780集合。
  此任务现已正常退出0、未超时；父端离线核验通过，产物为
  `akv-tile-range-qualified780-parent-20261008-01/qualification.json`，
  状态`AKV_TILE_RANGE_NATIVE_INDEPENDENT_QUALIFIED_NOT_ADMITTED`。
  独立本地ISA模型核对67119条退休指令、48703次GPR写回、三次
  精确异常，skipped_retirements=0；自定义指令采用独立模型而非
  冒称Spike原生支持。相对780集合新增120个Toggle方向，全部
  落在requested_tile_start_q，符合静态预测。
  父端13项准入检查通过后已正式准入781项，目录
  `akv-tile-range-admitted781-parent-20261008-01`，manifest SHA为
  `720511a144576a95fee244a675635c96104b249c0f99ab3d6b8e0249de77f900`。
  保留完整780项前缀、6162条实例记录精确OR和所有历史gain记录，
  新ELF/新VDB去重通过；未重跑仿真，没有修改RTL。
  DTLB纯标量预检查最终产物为`dtlb-permissions-preflight779-agent-20261008-04`，
  其11项父端检查通过；193080条Spike退休指令、8378项软件检查，
  只修改本测试软件ISA为`rv64gc_zfh`，冻结RVV镜像配置不变。
  权限矩阵VCS后台任务`ara-dtlb-permissions780-agent-20261008-01.service`
  已核验实际PID694507、冻结simv及独立cwd，commit trace正在
  推进；预算1200秒、外层1260秒，不重复启动。prepared SHA为
  `13484ec02db18086914486561dc69693de57f8ef42216870ebe605f220a8fe12`。
  功能终态和实际覆盖增量尚未验收。
  任务现已正常退出0、未超时，elapsed622.811秒。旧collector
  在要求五条trap退休行处拒绝。源码`cva6_rvfi.sv:315`仅为ECALL
  异常输出valid行，其余同步异常虽有trap信号但valid=0；monitor
  依valid打印，故页故障不出现trap退休行。没有据此判为RTL失败。
  父端独立Spike与实际trace比较通过193080条指令、112155次GPR
  写回及2716次非压缩标量访存，寄存器跳过数0、mismatch=None。
  压缩访存和五次异常仍须在后继collector中分别依完整访存检查、
  handler gold及MMU原生探针核验；不能只凭tohost成功准入。
  父端随后独立调用全访存检查器，19857次访存全部通过，包含
  17141次压缩、2716次非压缩，loads9245、stores10612、skipped=0。
  地址及写数据由reference先前GPR状态计算，不取DUT反馈作为gold。
  新collector还需复用已核验的无向量请求schema：
  non_bit_exact_instructions/unobservable_instructions为整数0，
  不是空列表；只标记UNOBSERVABLE_ZERO_REQUESTS，不冒称向量PASS。
  五次页故障须由handler CSR/gold及MMU探针独立闭环。
- MaskB的EW16/SExt4候选被可达性审核拒绝：lane0对应分支已在
  780项中命中；VL=1的标量消费不能覆盖其他lane。邻近缺失点对应
  EW8，不能用EW16测试冒充覆盖。拒绝记录为
  `mask-b-sext4-target780-rejected-agent-20261008-01.json`。
  未启动此无新增目标的RTL测试，没有修改RTL或豁免这些可达位。
- BTB132与QBS128的独立只读复核通过；两组与780原EL及彼此
  无物理方向重叠，共260个精确新增方向。整体报告仅准备一次
  批量应用，不更新百分比，直至全人口五阶段验证通过。
  批量脚本首次父端10项预检查有一项失败：旧QBS解析器成功时
  返回排序列表，新调用直接与目标集合比较。修正为精确集合比较，
  保留旧解析器的严格内部方向检查，不改旧封存解析器或放松保护。
  父端曾因未读到函数末尾误判为None；完整检查第82行的
  `return sorted(found)`后已纠正该判断。修正后父端11项检查通过。
  仅绑定780项的独立整体任务已启动：
  `ara-population780-plus260-parent-20261008-01.service`，输出
  `current-population780-plus260-prepared-agent-20261008-02`，seal为
  `79b9a4286b0f6446d5ff4e345dd8df1352abf4ecf2bf889415cff60cc73fb8f8`。
  此任务不声称包含最新781项，仍待终态五阶段验收。
- QBS主/side字节选择的完整源映射分类已扩展到两个bank，形成
  `qbs-main-side-exact-batch780-agent-20261008-01.json`，SHA为
  `b3a125456ca92ebef722b83272f33b29333e4f1da488790b55eb2b85108bb600`。
  相对780和原EL，9440个方向（4720位、688个对象）为新的
  源映射零候选；已资格128方向单列，不重复计算。18401个方向
  保持HOLD，不因未命中而豁免。候选考虑九种weight profile、
  ROW/R4及activation ROW/M4/M8，pending沿用原writer索引。
  父端4项分区/负向测试通过；需原生精确局部核验后才能批量
  应用，不作为实测覆盖收益或新的整体百分比。
  精确native核验脚本父端6项检查通过，已启动独立任务
  `ara-qbs-hit9440-native780-parent-20261008-01.service`，输出
  `qbs-hit9440-native780-agent-20261008-01`，seal为
  `7a8d223671bf09439ee4b80ba83fb0ca0ec713958e55ca72bdbd83883d276797`。
  保护123240个其他方向及目标vector的13456位补集，不包含已资格
  128方向；原生终态尚未取得，不提前计入。
  原生任务现已正常退出0、未超时，实际DVE PID702100、exe/cwd
  身份一致。`capture-result.json`状态为
  `QBS_NEW688_OBJECTS9440_DIRECTIONS_NATIVE_NOT_APPLIED`，
  semantic_reload=True、global_final_empty=True。全五阶段精确
  方向和补集保护核验已通过，尚未应用到整体统计。
  父端完整只读重放verify亦通过，receipt SHA为
  `2995f02feb9f81bdbda9fa5974c10aea86114da61052d389c18b55fb8840ca6e`；
  另一个agent独立检查103个pins、两bank每阶段3193对象及精确
  first/second方向集合均通过。准备后继一次性781项+9700方向
  整体报告，但必须保持与目前780项+260任务的输入/产物区分。

| 指标 | 原始 | 精确豁免后 |
| --- | ---: | ---: |
| Line | 85.24% | 85.21% |
| Condition | 82.16% | 82.17% |
| Branch | 82.99% | 83.65% |
| FSM | 70.68% | 81.09% |
| Toggle | 64.89% | 71.33% |

权威产物：
`current-population781-plus9700-prepared-agent-20261008-01/qualification.json`，
SHA：`19d0773506c88e4f40a9d51d99b66b3b134382a536252910bd1fcbf5fef11394`。
统计范围为`ara_tb.dut.i_ara_soc.i_system`，不是包含额外测试台的
`ara_tb`根节点。原生DVE已正常退出0、未超时；父端再次完整执行
五阶段验收，原始/复位/最终统计相等，豁免应用/重载统计相等，
完整层级与72个模块及根节点六指标一致，精确EL集合及清理通过。
上一777项同范围Toggle为64.39%/70.49%，当前分别提高0.50/0.84
个百分点；FSM为70.29%/80.64%，本轮提高0.39/0.45个百分点。
此前780项报告在原已验收豁免集合上仅加入已资格BTB132/QBS128，
Toggle由71.10%到71.11%，原始覆盖率不变，FSM和其他四类不变。
这0.01个百分点是精确豁免变化，不是激励收益。当前781项报告
包含后继QBS9440精确豁免，根节点原始Toggle仍为64.89%，豁免后
由71.11%升至71.33%。此0.22个百分点不能称为新激励收益。
较早771项Toggle为64.11%/68.89%；跨豁免集合的增幅不全是激励收益；
CVXIF被动观察器高位padding排除不等价于DUT功能覆盖提升。
原始位图增量不用于手工推算DVE百分比分母。原失败记录保留。

最新正式合格测试集合为783项，最新已验收整体报告为781项。
不能使用781项百分比冒充783项总报告，也不能再使用777项百分比
代表当前报告。ITLB、VMACC和长mask的vfirst已完成正确性资格及
正式准入。vfirst新增20个目标统计位；逐指令、寄存器、内存、
CSR和8次原生请求上下文均已核验，其他四类代码覆盖未增加。
776项前缀产物为`vfirst-offline-admitted776-parent-20261007-01`；
777项产物为`akv-entropy-offline-admitted777-parent-20261007-01`。
新增AKV测试已按776项重新去重，实测新增1235个Toggle统计位，
其他四类覆盖增量为0。这是原始位图增量，尚非整体百分比。
绑定775项冻结集合的原整体DVE任务已退出：Tcl中的
`op1144_keys`变量未绑定，只有部分产物，不构成有效整体报告。
失败记录保留。独立修正后的整体DVE任务已主动停止，不能使用
partial文件报新百分比；任务为
`ara-native-full775-quoted-parent-20261007-01.service`。停止原因是
实测GUI逐对象查询成本过高，而非RTL失败；新整体报告将复用
已通过的局部原生资格，保留全人口五阶段统计和精确EL集合检查。
MFPU和RVH0现已完成原生局部资格及父端完整重放，尚未加入
后续整体报告；局部资格不等价于整体统计应用。
Toggle距离80%目标仍有8.67个百分点；不得以未验收候选或扩大
豁免范围宣称目标已达成。以下按时间保留历次核验记录，较早的
数字不代表当前正式基线。

正式778项产物：
`c910-float-edge-initialized-admitted778-parent-20261008-01`。
准入manifest SHA：
`b47e290304b57b5a012c82552b6c6676f70aaf8912cf989f532156f6b8b20c2f`。
浮点边界测试已经父端实际准入、独立审查通过：完整777项前缀、
6162条实例记录精确OR、唯一VDB、ELF去重、完整标量/向量/CSR/内存
比较。相对777项新增Toggle统计位置1224、Line38、Condition119、
Branch38、FSM0；没有新整体百分比，没有新RTL签核声明。

正式779项产物：`btb-ring-admitted779-parent-20261008-01`。
准入manifest SHA：
`299cc1cf1bd65f2f64f495c9f791c3a190ba5329e86344f035224678ccfbb9ca`。
BTB已相对正式778项重新去重，新增Toggle统计位置6156，其他四类
指标增量0；精确前缀、6162条记录OR、唯一VDB和ELF去重通过。
两项相对777项合计新增7380个Toggle位置，但不得据此手工推算
整体百分比。本次准入没有重跑仿真，没有修改RTL。

最新正式780项产物：
`dtlb-ppn-swap-offline-admitted780-agent-20261008-01`。
父端实际准入manifest SHA：
`4b679eed5892200a4d166748d9ae504a31d5dddcb3cdbca0e1f3ec61cab2bb7b`。
准入检查器9项测试通过，完整779项前缀、6162条实例记录OR、
唯一VDB及历史ELF去重通过。191475条标量指令、19071条完整访存、
48次实际DTLB更新、96次接受load及8297项gold检查均已核验。
相对779项实测DTLB新增496个Toggle统计位置；`i_system`范围内
Line/Condition/Branch/FSM分别新增6/5/4/7个原始位置，不是百分比
增幅。完整实例记录范围对应增量为17/21/13/7，两种范围不能混用。
该纯标量测试没有向量请求，不宣称向量比较PASS。
新780项整体报告已由父端启动独立后台任务：
`ara-current-population780-compact-agent-20261008-01.service`，
输出`current-population780-compact-prepared-agent-20261008-01`。
config SHA为`1d0c7ddf9b7752f79192ca90f8915e1be3da8d1180f8057ec2b3ad18c481ed00`。
启动后先重新核验封存输入，再执行原生DVE五阶段统计；只有最终
qualification现已通过：原始/复位/最终一致、应用/重载一致、
完整层级与各根节点六指标一致、所有其他位保护通过。当前正式
百分比已更新为780项，本次未应用新增BTB候选豁免。
BTB目标地址固定bit0的132个方向原生局部核验未通过：DVE在
before阶段报`Nonunique/foreign BTB root`，属于表格根节点身份检查
失败。已保留error.txt和原日志，核验实际PID/cwd/cgroup后终止该
失败局部任务的进程组，避免等待600秒上限；未加入整体豁免，不
计为激励覆盖收益。780项整体报告沿用原有已验收豁免，不受该
候选失败影响。QBS异常场景的FAIL继续排除。

BTB报告脚本的静态差异已定位：已验收`apply_points740_v4.tcl`
先恢复完整ara_tb根、展开层级、选择完整scope并读取选择结果，
之后才setroot；失败的局部脚本直接setroot，并只接受`i_btb`
显示名。后续修正必须沿用完整scope选择约束，显示名仅接受
编译数据库绑定的实例名/模块名，禁止接受任意节点或忽略兄弟
节点。此差异是可检验的脚本根因假设，不是已完成原生验证。

下一项短定向激励已完成冻结源/779位图可达性核对：AKV的
`requested_tile_start_q`在command_fire先捕获完整64-bit rs2，
之后才检查它是否小于16-bit kv_length。因此高位不是结构常量，
应补负向测试，不能按成功tile范围豁免。保持合法descriptor
`D64/q_rows=1/kv_length=1/stride=128`，三个独立FULL输入
`UINT64_MAX -> 2 -> 1`，期望每次TILE_RANGE拒绝、cause2、tval0、
精确fault PC；随后tile0 FULL/LOAD/RELEASE检查正常恢复。
必须使用64-bit寄存器绑定，不能被uint32_t便利接口截断。
descriptor AR是合法必要读取，要求payload AR为0，而不是全部
AR为0。每次失败按设计清除context_ready，不冒充状态无变化。
独立gold检查完整VRF、CSR、源数据/guard、异常次数及恢复结果。
原生目标shape为12374、checksum为4015856550、对象offset4238，
779并集缺120个方向；120仅为静态潜力，仿真后重新去重才可报告
实测收益。该case不声称覆盖成功context base/read-address缺口。

QBS字节选择的第一组小范围证明已封存，父端最终10项检查通过：
`qbs-main-hit-congruence780-bank0-p2-slot1-row0-agent-20261008-02.json`，
SHA `23e6d07d94580fb63025509708a37104f78b5cfb5f191214cb27aae1128375fe`。
范围仅bank0/plane2/slot1/row0：64个source bit、128个方向在
780并集全为0，旧EL交集为0；合法输入映射的有限超集不包含
这些组合，源码链哈希与冻结编译一致。它们仅为原生局部核验
候选，尚未加入正式统计。另48个缺失方向有映射见证但尚未
证明word选择和pending仲裁，保留HOLD，不豁免也不声称已命中。
直接读取/FILL与context REUSE/RELEASE的输入offset来源不同，
不得用直接读取的映射见证冒充replay路径证据。
128方向原生局部核验已由父端启动，工具
`qbs_hit128_native780.py`的10项检查通过，独立任务
`ara-qbs-hit128-native780-parent-20261008-01.service`；输出
`qbs-hit128-native780-bank0-p2-slot1-row0-agent-20261008-01`，
config SHA `7864c19fd3f06b06a148ae39f5c8ed97f7b15aef3c61cfeaa51db0b41d420ed5`。
仅检查64bit/128方向，3177个其他对象和192个目标vector补集bit
保持保护；不是整体应用，验收前不更新正式覆盖率。
该原生任务现已正常退出0、未超时，`capture-result.json`通过，
SHA `f2de6691f6e94a08061ae97b82aeee23c4779ebbe41aa8c06fb16e75182f21a3`。
实际五阶段native inventory每阶段3193对象，3177非目标对象及
192个目标vector补集bit保持保护；全局EL精确128方向、语义
重载一致、最终全局清理为空。未排除initial-X或usage_d。
状态仍为`QBS_BANK0_P2_SLOT1_ROW0_EXACT128_NATIVE_NOT_APPLIED`：
已取得局部原生资格，等待与后续已合格候选一起批量加入整体
报告，不能据此改写780项的正式百分比。

BTB第二次原生观察确认了显示名根因：完整scope的选择/readback
正确，但GUI path/name均为`btb_gen.i_btb`，不是`i_btb`。第三版
只增加这个精确生成层级别名；编译srcinst id=-1968、父frontend
id=-466及冻结frontend源码均核验，禁止任意后缀匹配。
父端5项检查通过后启动独立
`ara-btb-bit0-native-v3-parent-20261008-01.service`；config SHA
`bb6edb16befafd68567280865181e28ff09f094bfe3c5506539e3092cd836718`。
候选仍仅66个bit/132方向，8860个补集方向保持保护；尚未批准
整体应用。前两次失败产物完整保留，没有重跑RTL仿真。
第三次已通过根节点身份检查并保存原生`first.el`，但应用阶段
校验器拒绝其格式：DVE把唯一ANNOTATION放在Toggle记录之间，
而校验器错误地要求全部header位于记录之前。已保留实际EL、
error.txt和before统计；DVE正常退出0不等于核验PASS，本候选
仍未应用到整体统计。后续只根据该实际格式修正独立解析器，
必须仍检查唯一checksum/scope/annotation、精确132方向和完整
补集，不能跳过未知header、重复header或额外Toggle记录。
DTLB权限/global属性的软件oracle另有7项父端检查通过，目前
仍是激励准备，不计为DUT PASS或已实现覆盖提升。

新增激励在EDA之前继续执行严格预检。MaskB SExt4的父端组合
检查出现2项失败：所写raw71/branch-vector期望不对应EW16，
已交由producer绑定修正，不能放宽断言后声称覆盖目标达成。
原生branch_spec使用1-based源条件，诊断位映射必须逐项核对。
DTLB权限预检02被`Unexpected vector/FP/fatal trap`拒绝；静态
反汇编证实vsetivli/vse32/vse64初始化指令存在，而软件检查要求
纯标量。compile已经包含禁loop/SLP向量化选项，不能重复追加
这些选项当作解决。后续仅此标量MMUfixture使用不含V的编译
目标，冻结RVV RTL镜像和Spike能力保持不变；重新证明没有
隐式RVV指令及完整CSR/gold通过后，才能启动VCS。该预检失败
不是DUT bug证据，当前未计入任何覆盖统计。

### 779项之后的定向补充：源码先行，不盲目堆seed

1. QBS/AKV翻译异常地址：两套read engine的异常地址及tval字段
   残余1395个统计方向是容量上界，不是收益预测。源码确认开启
   翻译后PMA检查必须等待mmu_valid且无mmu_exception，因此真实
   页表fault可到达该路径。descriptor只检查对齐、shape和范围
   溢出，不提前按物理地址拒绝canonical VA。复用gap71的真实
   缺页、修复、重试参考，独立重定位root/middle PTE与gold地址，
   先完成一个正canonical窗口fixture预检，再扩展互补窗口。
   必须核验实际MMU fault，而不能用cause5的PMA fault代替。
   父端独立核验目标地址`0x0000001555402080`和
   `0xffffffeaaaa02080`均为合法Sv39 canonical、16字节对齐，
   VPN2/VPN1/VPN0分别为85/170/2与426/341/2，页内偏移均128。
   参考页表必须同步更新这些索引，不能只替换descriptor地址。
2. DTLB缓存物理页号：content_q/n的32个PPN字段残余2684个方向，
   其中低8位缺412个方向。历史VPN/ASID矩阵主要映射到相同PPN，
   ASID已无缺失。新激励用16个稀疏Sv39 VA映射到冻结2MiB RAM
   内不同的合法物理页，再交换映射、SFENCE并检查真实数据。
   PPN高位缺失不得当作合法RAM范围内可保证的收益。
3. DTLB权限/global属性残余142个方向，页表地址链可能只补几十
   个方向，暂排在上述两组后面。reduction第二暂存槽的可达条件
   尚未证明，不启动试探仿真，也不据此新增豁免。

两个新fixture先构建独立gold和软件预检，不修改RTL或已有封存
测试。每点实际预算根据退休指令数及历史wall确定，目标600秒
以内；不把四fixture合计约34万指令误称为数万指令或承诺同一
600秒预算。777报告中PTW原始FSM为44.00%，豁免后为68.75%，
两者不能混用。后续增量统一相对正式779项重新去重。

### 2026-10-08新增场景的检查边界

QBS正canonical窗口的软件预检已通过：79002条入口至tohost指令、
160项软件检查、两次预期trap；软件fallback参考不等同于原生custom
逐指令参考。正式RTL资格必须独立核验MMU异常优先于PMA、故障地址
及CSR、无错误目标AR、在途响应排空，以及修复页表后的同PC重试与
普通RVV恢复。探针还需观测`ar_stalled_q`：源码中的`fault_valid_o`
同时要求burst FIFO为空和没有滞留AR，不能只凭FIFO为空判定排空。

DTLB物理页号切换的软件预检已通过191475条指令、8297项gold检查，
包括16个完整物理页的8192个数据检查。该规模使用独立1200秒仿真
预算，外层1260秒，无自动重试；旧预检的300秒值不是测量预测。
全部访存共有19071条，其中压缩16823、非压缩2248；原比较器只
报告非压缩访存，不能用2248代表完整访存检查。新局部检查器必须
按参考前序GPR计算地址，并核对PC/opcode、读写mask、store数据
和load返回值。48次TLB写入、每阶段16槽和96次接受load的声明
还需本次逐周期探针证实，软件VA数本身不是硬件槽覆盖证据。
以上仅是预检及准备状态，尚未准入，不改变777项整体百分比。

两路已分别提交宿主机systemd后台，不启动容器、不重新编译RTL：

- QBS：`ara-gap71-canonical-qbs779-parent-20261008-01.service`，
  输出`gap71-canonical-qbs-positive779-run-agent-20261008-03`，
  prepared SHA `c5e0d48f00061aeee897f5cfcd026c3661417e133fe4dc37ed1bcf4e31bf9991`。
  父端运行脚本测试通过；实际simv PID621092的exe/cwd/cgroup已核对，
  全部41个探针对象启用，已有23461条提交记录。预算600秒，
  外层660秒，无自动重试；后续须独立验收，不把启动当作PASS。
- DTLB：`ara-dtlb-ppn-swap779-20261008-01.service`，
  输出`dtlb-ppn-swap1200-parent-20261008-01`，
  prepared SHA `ea604a7eafc87133d3231f8f5f1c265ff60003cc50829759c632202401abf201`。
  父端最新runner/collector的24项测试通过，prepared检查通过；
  实际simv PID623542的exe/cwd/cgroup已核对，探针READY，提交轨迹
  已生成335872字节，确认不是只有服务壳进程在运行。
  预算1200秒，外层1260秒，无自动重试。原有779项集合保持封存。

离线检查的新增审查：DTLB完整访存检查通过独立5项测试，参考
fixture全部19071次访存零跳过；审查记录SHA为
`60be89c5563e487850dff99e9412c79193989f68d6d109b8a6b3843ad54594f4`。
它是检查器审查，不是正在运行DUT的资格结果。QBS离线检查器
当前7项测试通过，覆盖MMU/PMA优先级、故障排空、重试、缺失/未知
信号及截断拒绝；恢复writer与生命周期仍补负向测试。未采集AR.len，
因此只检查AR/RLAST事务守恒，不宣称逐beat长度协议闭环。

BTB剩余132个统计位置对应目标字段bit0双方向；冻结源码中reset
为0、JALR目标bit0清零、BTB保存和读取该目标，属于结构固定候选。
仅整理逐位豁免，尚未原生DVE验收或加入整体报告。另6个valid清除
方向可由活动期间复位触发，不能因目前缺失而豁免。最新779项
QBS/AKV大字段缺口另做离线去重排序，不复用741项的旧残余数量。

QBS本次终端验收发现实际FAIL，不能准入：VCS在322.372秒内退出0、
未超时，但日志报告`GAP71_CHECK_FAILED index=60`、`errors=1`及
`UVM_ERROR`。`Core Test *** FAILED ***`必须优先于进程退出码判断。
离线检查输出`gap71-canonical-qbs-positive779-qualified-parent-20261008-01`
已保留`rejection.json`，不是通过目录；没有计入779项集合。

源码检查索引60对应首次故障快照的v8：前置51项检查之后，首个
VRF快照r0为52、r8为60。实际完整16个64位字与seed均不符，
例如地址`0x80011480`应为`0x719ac3de2688b45f`，实际为
`0xb4b4b4b45c5e5d5f`。原生向量轨迹中故障custom arch_seq39
为一次分配、一次完成、零VRF写入；重试arch_seq76写128字节。
因此“故障命令直接写坏VRF”假设已被否定。EEW布局元数据更新或
故障回滚是待核查假设，尚未逐周期证明；不能把相似字节排列当作
已确证根因。使用已有提交/VPD和冻结源码继续诊断，暂不改RTL，
不重复仿真，其他独立DTLB任务不受影响。

进一步离线判别排除了简单“seed按EW64存储”的假设：原生轨迹
显示seed v8的arch_seq12实际EEW编码0（EW8）、VL128，16次
write；fault custom arch_seq39为EEW编码2（EW32）、VL32、零write。
对四种源/目标EEW的16种独立字节置换逐一计算，实际快照仅与
EW8物理布局按EW32解读的结果完全相等（128/128字节）。
因此问题集中在故障前后布局描述与物理内容不一致，而不是数值
计算误差。冻结dispatcher在请求接受时更新目标EEW，静态与
字节证据一致；本次探针没有直接记录eew_q，仍不宣称其具体
更新周期已被波形观察。该失败保持未准入，RTL暂不修改。

BTB bit0候选准备产物为
`btb-bit0-132-prepared779-agent-20261008-01`，manifest SHA
`6f9edc8b0d3cd18a0137f16a5f1b3ddf486158963f946a7e67d1b28d64e181eb`。
父端实际10项测试通过（5.492秒），含冻结779与compiled绑定及
扩大范围、漏方向、重复等拒绝测试。候选只包含66个目标字段的
bit0双方向132位置，与既有EL无重叠；其余8860位置保持保护。
状态仍为`STATIC_PREPARED_NOT_NATIVE_APPROVED`，后续原生DVE
保存/重载与补集保护核验通过之前，不应用、不报豁免后新百分比。

DTLB本次已在681.937秒内正常终止、未超时，程序SUCCESS。父端
离线检查越过完整191475条scalar/GPR及19071次访存门禁，随后在
零向量数据结果的schema检查处拒绝：`vector_zero()`把
`non_bit_exact_instructions`预期为列表，而冻结比较器实际返回
整数计数。这是离线检查器接口类型错误，不是已发现的DUT错误；
TLB槽波形尚未完成验收，仍不能准入。保持原runner/collector及
seal不变，用独立兼容检查入口按实际返回schema严格核验零值，
不将UNOBSERVABLE称为vector PASS，不重跑VCS。首个拒绝命令
尚未创建qualification输出目录，因此没有伪造的通过产物。

DTLB兼容检查已由父端完整实际执行通过，不重跑VCS：
`dtlb-ppn-swap779-qualified-parent-20261008-02/qualification.json`
SHA `66e01ec60094614032e0303c7296a8b73b0fe323320a52200c581bdee25d5a75`；
`postrun-schema-qualification.json` SHA
`d84641d1898dffb4624ebbe54cecb974620a92fd470d3667ef74392e1183066c`。
完整原门禁重放：191475条scalar、16823次压缩与2248次非压缩
访存（8553 load、10518 store）、零skip；波形48次更新、各阶段
16个真实槽、96次接受load与精确VA/PPN对应全部通过。新schema
检查的6项测试实际通过，仅纠正零向量计数字段类型，并完整限制
其他字段的类型/零值/空列表；保持UNOBSERVABLE而非vector PASS。
当前为资格通过但未准入，须相对779项去重并核验实际增量后合入。

### 已完成批次的后台任务与汇总记录（历史状态）

- 初始化后的浮点边界测试已启动：
  `ara-c910-float-edge-initialized777-parent-20261007-01.service`。
  父端10项测试通过；真实Spike预检通过36997条入口至tohost指令。
  仅补充三个LMUL8寄存器组的完整初始化，原48个浮点边界场景不变。
  必须通过全请求、零未知字节、零跳过的向量比较后才能准入。
- BTB地址训练测试已启动：
  `ara-btb-target-ring777-parent-20261007-01.service`。
  父端12项测试通过；软件预检确认32个槽、96次A/B/A目标跳转。
  实际BTB更新仍须由本次探针核验，不将软件执行次数当作硬件更新次数。
- 两路实际simv的可执行文件、工作目录及systemd cgroup已核验，
  提交轨迹已推进；各自600秒预算，均无自动重试，不修改RTL。
- 新版777项整体报告的31项测试通过，但实际02配置检查发现
  自引用哈希问题：配置读取与输入审计共用Reader，导致输入集合
  误包含配置自身。已拦截EDA启动；02产物保留且不作为有效报告。
  修复检查逻辑后重新封存，不重跑777项已有仿真。
- 修复后32项测试通过，包含无mock的真实777项prepare/check。
  父端03封存及实际check通过，配置SHA：
  `d118e7f4559664ead1cac0bde48e04e6ad68291bbd3a35fb8a9cc49fad648092`。
  已启动`ara-global777-compact-parent-20261007-03.service`；此报告
  固定统计777项，不将后续尚未正式准入的候选暗中混入。
- 浮点初始化测试已正常退出，184.127秒、未超时。父端唯一collector
  完整通过：36997条标量指令、147条向量目标请求、8544字节、
  零unknown/skip/非逐位比较，48个场景的CSR/内存签名一致。
  资格SHA：`18168c5b7a05081362e4682a7d4fe9ca8bb5662bda4b3a15af2eefc667eef9ae`。
  相对777项实测新增Toggle方向1224、Line38、Condition119、Branch38，
  FSM增量0；仍需正式准入，不能据此推算全局新百分比。
- BTB仿真已正常退出0，探针文件已封存；独立架构比较、实际表项
  更新及去重增量正在验收，退出成功不代替完整PASS。
- BTB离线资格已完成，父端16项测试通过；实际32个槽、96次A/B/A
  preedge mispredict/update完全匹配，37753条指令、完整4096字节
  VRF和CSR/PTE/code guards通过。资格SHA：
  `cd6e476360ff6c0c5b3753e6b0b305a09ba7617c65c897f0ac02a8f610c06dab`。
  相对777项新增BTB Toggle序列位置6156，其中目标地址字段5960；
  四类其他指标增量0。正式准入须相对最新778项再次去重，不能直接
  相加两组相对777项的增量。未直接探测stored_q，更新路径由固定
  RTL写使能关系与preedge信号共同核验；不虚称直接读取表项存储。

## 当前推进顺序：优先实际可达的翻转

当前Toggle提升按以下证据顺序执行，而非简单增加随机seed：

1. 固定RTL镜像及参数，定位缺失的具体信号和统计坐标。
   对可达信号从实际驱动逻辑选择激励，要求发生往返变化；
   高位计数器需要长VL和边界值，不是增加随机数据即可覆盖。
2. 将定向测试先通过独立架构检查，再与最新正式集合的原始
   Toggle位图求差；没有新增目标的测试不作为提升证据。
3. AKV描述符与步长候选须验证合法/非法描述符、精确异常、
   数据结果及真实读请求；高步长不能引入越界访问。
4. 操作数读请求的固定零wdata、配置禁用的mask字段只在源码、
   编译对象和实际统计坐标三者一致时按字段豁免。不能整块
   排除功能单元，也不能用豁免掩盖仍然可达的未测功能。
5. 原始覆盖率与豁免后覆盖率分别展示。已有合格VDB复用，
   局部增量确认后阶段性整体汇总，不反复仿真全部测试。

### 本轮执行记录

- `vfirst-offline-admitted776-parent-20261007-01`已正式准入；
  admission SHA为`85abeb09ddfc3c4ddbfc43eefa7c71d860932dd66af572edac0bd7030ce3c33c`。
  独立复核全部输入/输出绑定、776唯一测试、775前缀和6162条
  metric记录的OR一致性通过，20个目标统计位均有实际新增覆盖。
- mask父级常量字段资格任务为
  `ara-masku-parent-only775-parent-20261007-01.service`；已核对
  实际DVE可执行文件、工作目录和进程归属。任务现已退出0，
  strict receipt为`MASKU_PARENT_ONLY_STRICT_NATIVE_QUALIFIED_NOT_APPLIED`；
  原生结果SHA为`4b0066d021c80c7b08c3f1a2ecc3ed55a9dd44f926c1772847128ee88a7ee61a`。
  仅父级一个256位对象获得局部资格，986个其余对象保持保护；
  尚未纳入整体统计，不据512个方向推算官方百分比。
- AKV运行器与检查器34项测试通过，父端实际耗时38.362秒。
  唯一VCS任务为`ara-akv-entropy775-parent-20261007-01.service`，
  产物目录`akv-entropy-old-image775-parent-20261007-01`，
  prepared SHA为`96c4dc17891d08ed191d1426aee04b61508570079bd0622d44b140a0842db487`。
  包含6条专用命令及逐指令参考检查，波形仅采集6个真实读范围信号。
  尚无实际覆盖增量结论；准备记录绑定775项，正式准入须与776项重算。
  该VCS任务现已退出0、无timeout，CPU时间241.140秒；270次请求/
  响应、一条预期异常、protocol_errors=0、outstanding=0，selfcheck成功。
  首次collector在创建输出前拒绝manifest哈希：prepared SHA为上述
  `96c4dc...db487`，executed SHA为
  `94dd5c6f0d4d748cb3e5204b6f646989eba3abced9f9fae16a70c6c45da929d2`。
  父端结构化对比已确认两份JSON及247项pins完全相同，差异仅为
  集合遍历造成的pins字典排列顺序。须用独立双哈希入口保留两份
  原文件并继续完整原检查器；不能忽略哈希，也无需重跑VCS。
  独立入口又定位到重新prepare时新增wrapper自身依赖；静态比对
  证明无原pin缺失或变化。私有runner只移除这个精确依赖，其SHA
  和测试SHA仍封存在独立closure中；真实wrapper命名空间prepare
  正例及其它负例共16项父端通过，耗时36.223秒。
  实际完整collector已通过：67572条退休指令零跳过、6次VRF完整
  快照24576字节、9条真实读范围、一条精确异常均一致。
  qualification SHA：`a32928e4a26ab3456d9a59ea8d29ce7ff4a282b9fe8419f121ba12f9fb5e50d0`；
  closure SHA：`feda50282f581f106598ed50e32ff519837c786682c0c247e581b9e652982f57`。
  相对775项集合，AKV局部实测新增1235个序列化统计位；Line、
  Condition、Branch和FSM增量均为0。尚未正式准入；须扣除776项
  已有覆盖并完成VDB siminfo身份检查后加入唯一正式谱系。
  父端独立读取实际VDB的siminfo/vcmArguments：原始命令与清单
  完全相同，workdir、seed=1、编译VDB及五类覆盖选项匹配；
  siminfo记录时长252.486687秒。XML的teststatus=unknown保留，
  不作为功能PASS依据；正式777准入还须将这项身份检查固化。
  该准入现已完成：父端13项测试和独立审查通过，实际prepare及
  正式admit均通过。最新admission SHA为
  `39ad0375146e5a6d98f1ef0141030f95309e2a8409dc71f6d510b59631bc3d52`。
  777项保持精确776项前缀、唯一新增VDB、无重复ELF、6162条
  metric记录完整OR；相对776项仍新增1235个Toggle统计位。
  功能PASS依据保持独立参考模型资格，不冒充原生Spike专用指令
  对比；原XML的unknown状态未改写。整体百分比等待阶段性DVE报告。
- FULL775生成器错误已静态复现：未引用完整Tcl数组变量名，
  `gen_lanes[0]`中的方括号被当作命令替换。24处同类语句必须修正，
  并用真实完整selection验证；已有partial缺少应用/重载/复位证据，
  不得补写成通过。原失败产物保留，修正只涉及报告工具，不涉及RTL。
- 独立selection修复已通过宿主机真实执行及原始配置检查；
  父端9项引用测试与6项wdata证明测试共15项通过，耗时25.067秒。
  仅24条声明引用方式改变，720个目标和492个保护坐标完全不变，
  EL与775项输入清单逐字节保留。新汇总任务为
  `ara-native-full775-quoted-parent-20261007-01.service`，
  config SHA为`f5ec8d04f9f7f0985a6cd8efa7ea87442e2692c5dbbb14886c3f8bf27f79917a`。
  实测before阶段MFPU导出788 scopes/53468行耗时20.3分钟，
  observer127 scopes/18789行耗时5.1分钟，combo153 scopes/19113行
  耗时2.3分钟；72个关键模块summary约41秒。后续四阶段继续逐行
  GUI查询预计另需110至125分钟，超过5400秒总预算。父端据此主动
  停止此唯一旧全局服务，直接确认service inactive/dead且实际DVE
  PID 501050已退出；全部原配置/局部导出/partial保留，不作为成功
  报告。systemd停止命令成功不等价于五阶段资格完成。
  后继报告不削减777项合格测试集合，也不扩大豁免；复用已通过的
  局部五阶段资格，全局仍独立检查raw/reset/final为空EL且统计恢复、
  applied/reloaded完整EL精确等于批准集合且统计一致，以及实际777项
  测试选择。省略的是重复逐对象GUI查询，不是有效统计或保护条件。
- requester的36个读请求wdata字段共4608方向，源码和编译对象核对
  表明已归属既有read108豁免。此复核没有增加豁免，不得重复计收益。
- CVXIF被动观察字段的零扩展高位已完成静态差集和父端18项测试：
  两层各5个对象，AR/AW/W/R/B的真实宽度为98/104/146/136/7位，
  只将高于真实宽度的1024位扩展部分作为候选。合计18516方向，
  与封存775 EL交集为0；低位payload和其余76个对象仍受保护。
  这是验证设施统计范围的规范化，不是DUT功能覆盖提升。
  静态审计产物`cvxif-padding776-static-prepared-agent-20261007-01.json`
  尚未获得原生范围资格，也尚未加入整体统计。
  父端完整阅读独立native入口及v2范围检查，40项测试通过。
  实际prepare seal为
  `b8a9d69555ba6e5e49629ad86a9de0bb07ef65b13f3541d99121c464b0e6b065`。
  独立任务`ara-cvxif-padding776-parent-20261007-01.service`已启动，
  父端直接核对实际DVE PID 529571的/proc executable、cwd和cgroup。
  验收要求原生五阶段、精确EL往返、全部低位payload及其余对象
  保持保护；只允许整数退出码0且无timeout。终端日志使用不可变
  快照，不以仍可能追加的launcher日志作为封存依据。
  此局部DVE现已正常退出0，并生成五阶段资格receipt；两个scope
  分别包含41/45个原生对象，36/40个其余对象受保护。父端第二次
  verify发现幂等性工具缺陷：重建计数为tuple，JSON读取计数为list，
  数值相同但Python直接比较失败。逐项复核全部receipt pins无漂移；
  独立审查确认该根因。原文件保持冻结，采用离线规范化复核，
  不重跑EDA，也不把未完成复核的局部receipt提前应用到整体。
  离线复核现已完成：父端9项测试通过，含实际原verifier连续两次
  重放；独立closure只将每对对象计数转为JSON列表，原最终比较
  直接通过，所有其他类型和字段仍要求精确一致。父端实际closure
  为`cvxif-padding776-offline-closure-parent-20261007-01.json`，SHA
  `232dbc6deabf69fc849cfd4d33a032daca271f7c8a35688db146475158877190`。
  10个对象的18516个扩展方向现已获得局部资格，低位payload、
  76个其余对象及原生额外对象仍受保护。此项属于验证观察器
  不可达补零位的统计规范化，不是新功能覆盖；整体应用仍待汇总。
- 浮点边界激励`apps/riscv-tests/isa/rv64uv/c910_float_edge.c`已通过
  真实Spike预检：FP16/32/64、RNE/RTZ，共48个场景、1440项检查，
  涵盖正常恢复、正负溢出、精确子正常结果及下溢/NX/UF标志。
  独立检查源与目标保护区、288项CSR结果、4608字节定义向量写、
  1536字节store结果；父端9项预检工具测试通过。实际预检产物为
  `c910-float-edge-preflight776-agent-20261007-02`，尚未作为RTL PASS
  或新增覆盖证据。后续增量必须相对最新777项集合计算。
  父端运行器8项测试通过，实际prepare绑定124项输入；seal为
  `42c273792164634b44e1d69a03f5a550f9ca3b2a54795f11824a26602cff1430`。
  唯一VCS任务`ara-c910-float-edge777-parent-20261007-01.service`已启动，
  父端核对实际simv PID 536729的可执行文件、独立cwd与所属cgroup。
  运行目录为`c910-float-edge-vcs777-parent-20261007-01`；sim预算600秒，
  systemd预算660秒，无自动重试。采集逐条退休、向量写回及五类代码
  覆盖；尚未完成独立RTL结果验收，不能提前计作PASS或覆盖增量。
  实际VCS现已正常退出0，wall时间174.526秒、无timeout，软件自检
  SUCCESS；481次后端请求/响应守恒、exceptions/protocol_errors/
  outstanding均为0。此记录只证明仿真终端和自检，逐指令、定义
  向量字节、CSR/内存及相对777项的覆盖差集仍待collector验收。
  父端collector工具12项测试通过，但实际collector在store上下文
  检查处拒绝。诊断确认48条store的activity上下文均为None，而
  96条load和48条div匹配；原始CSV首store为eew=1/vl=16/vstart=0。
  通用解析器仅在alloc_vd等于指令目的字段时设置上下文，store
  的该字段实际为vs3，alloc_vd为0，故不满足条件。此为专用验收器
  使用通用解析器的契约错误，不证明RTL计算失败；已有标量、
  内存与48项fcsr检查通过。失败目录封存，后继入口须严格绑定
  原始store alloc元数据及生命周期，不简单跳过上下文检查。
  父端独立store上下文适配的6项测试通过，48条store原始alloc/done
  上下文、VID、geometry及非VRF写回均通过。实际完整重放随后在
  通用向量对比的严格门禁处停止：结果无mismatch，144条目的指令、
  4608个有效结果字节匹配，non-bit-exact/unobservable和未完成请求
  均为0；但EEW16->32及32->64时三个寄存器的SLDU重排各搬运
  128字节，其中未初始化的96字节尾部仍为未知，总计576字节。
  六次重排的实际地址范围及source=3已确认。此为激励初始状态
  不完整，不能改写成“零未知跳过”或伪装成RTL数值错误。
  原失败产物保留。后继定向case计划先完整初始化三个LMUL8组，
  再执行相同48项边界，维持零未知跳过标准；普通向量请求全流
  结束已由标量tohost及生命周期确定，通用对比的PREFIX标签也需
  按其实际API处理，不能简单用标签猜测未完成RTL请求。
- 下一项可达Toggle候选是CVA6 BTB目标地址：按正式777项重算，
  `btb_d/q[0..15][0..1].target_address`共64个对象仍缺6088个原始
  序列化坐标，现有EL没有排除此族。更新端已覆盖较多地址变化，
  因而假设是没有把变化送到每个槽，而不是缺少随机地址本身。
  计划使用两个代码bank遍历32槽，每槽A/B/A目标跳转，覆盖低位
  与高位规范Sv39地址的交替；固定清零的JALR bit0不作为可达目标。
  该6088数字只是静态缺口容量，不是新增覆盖。软件预检应核对
  源PC槽索引、合法PTE/代码保护区、精确返回值及CSR恢复，RTL侧
  要用实际BTB valid/mispredict/update/target探针证明每槽更新。
  测试预算600秒；尚未启动EDA或作为正式PASS。

1. 对实际773项集合的未覆盖位，沿RTL驱动路径区分数据输入不足、
   控制场景不足和配置不可达。分别记录0到1、1到0，不以case数量
   或源码预测代替原生覆盖收益。
2. 普通RVV优先补VMACC的MulFPU-C操作数队列：e8/m8的VL=1024、
   1020、1024交替，使每Lane长度256、255、256经过四个FIFO槽。
   当前静态目标仅144个缺失序列化坐标，尚非官方新增方向。
   独立预检24项通过，包括19次向量写的整数参考结果、四次完整
   VRF快照、尾部保持、源保护区、CSR及错误注入检查。
3. ITLB bulk实际VCS退出0，CPU546.590秒，103572条非陷入指令
   对比匹配。原失败是验收器将下一条独立CSR请求当作上一条结果
   的使用者；修正后必须保留6次请求/响应守恒、精确标签、退休
   值、真实使用者、48次陷入、PTE和代码保护区检查。正在只读
   重放完整验收，不重跑VCS，不修改RTL。
4. RVH0原生五阶段完成且任务退出0，60个目标、2794个保护对象。
   父端原生检查通过，封存记录只在service.log上发生哈希变化：
   包装器在生成结果后追加结果路径/哈希。必须证明精确追加内容，
   保留原记录并生成完成后闭环，不能直接忽略哈希错误。
   后续父端已确认：日志恰为两行，第一行哈希等于原封存哈希，
   第二行JSON恰为原结果绝对路径及原结果SHA；所有其它封存
   文件哈希匹配，无新增证据文件。完整原生五阶段检查已通过。
5. MFPU原生验收继续后台执行。候选资格和新PASS集合齐备后，
   在一个新目录统一汇总；不反复重跑完整报告，不先报估算百分比。

地址范围纠正：冻结镜像编译配置实际为`sim_l2_mb=2`，即2MiB；
此前把256KiB测试包范围当作镜像L2容量的判断不正确。VMACC新
启动文件仅将栈顶从0x80200000移到0x80040000，主动限制测试
地址包络；实际参考运行栈深48字节。该变化不是RTL修复，也不
意味着原2MiB栈地址超出了真实镜像范围。

本轮实际闭环：RVH0完成后封存工具父端7项测试及真实receipt
重放通过。ITLB新增AXI端口解析按源码证明的281/84位打包顺序
解码，不要求不存在的VCD子字段；父端9项解析测试通过。
父端完整重放结果与独立审查的六份诊断JSON一致：标量/CSR、
代码保护、原生参考、AXI观测、原始增量及Toggle目标统计。
相对773项实测新增948个序列化坐标，其中目标862个；其余
四种代码指标增量为0。父端qualification SHA：
`d69da479938dba3aa798a67d40162a41d77ef8fbf5a6ec70eefedde67c61a73f`。
这是正确性和局部增量闭环，尚未正式准入或改变整体百分比。
诊断中继承的`after.hit`和`dve_toggle_percent`为原生历史摘要，
不是OR后的新统计；增量取实际位图，禁止从该摘要推算收益。

VMACC运行/采集工具首次父端29项测试有一项负向检查失败。
必须检查错误注入是否落在真实受检数据，以及采集器能否拒绝
源保护区损坏；负向闭环之前不得启动VCS或计入覆盖率。

后继负向测试改为破坏真正受检的最后一次源保护区读值，并由
独立签名检查拒绝；父端最新22项运行/采集检查全部通过
（11.559秒）。旧29项包含7项导入测试，不能把两批数相加。
启动包prepare/verify通过，封存SHA：
`f77870aa6f52c5bac88305b7e6a5e6c39e42c16c459d1dc1713ef8713e1c9305`。
唯一后台任务`ara-vmacc-C-fifo773-parent-20261007-01.service`已启动，
真实simv PID436945；父端核对exe、cwd、cgroup均匹配。独立目录
`vmacc-C-fifo-vcs-parent-20261007-01`，上限600秒；未准入覆盖率，
不重编RTL，不重复运行。

MFPU原生任务现已正常终止，父端重新执行完整verify通过，
4930个证据pins与3940份五阶段库存检查闭环。272个目标、
34816个方向候选及744个保护子scope完成局部资格，未应用
到总体百分比。真实结果SHA：
`5b6ec22297d34ce9e7a944c0c9c677bca25d0856c1e39f4c82854e6cfa3e8dc8`。
不得把34816个候选方向当作新增命中，或直接相加推算覆盖率。

ITLB正式774准入父端16项检查通过（55.136秒），实际prepare
在历史ELF去重处停止，尚未创建正式774目录。现773清单不含
本次bulk VDB，但旧工具的sidecar fallback按历史父目录在整个
JSON中的字符串出现与否匹配，可能把包含历史pins的本次资格
记录当作历史运行命令，再将本次ELF误判成历史重复。必须根据
运行记录自身身份和原生命令封存证明实际归属；不可忽略真正
重复ELF，不可直接删掉失败门控。正在准备独立后继去重器及
负向检查，不改原失败入口、不重跑VCS、不宣称774已准入。

后继`admit_itlb_bulk774_v2.py`仅使用已封存773历史证据解析
历史ELF，不使用带有旧pins引用的候选资格记录充当历史归属。
仍调用完整历史去重，并要求每个解析出的ELF/命令已被773
证据封存。父端7项真实/负向检查通过（113.121秒），包括
完整6162项OR、所有773个历史成员及真正重复ELF拒绝。
独立prepare正在进行，正式准入仍须另行授权并封存结果。

VMACC真实VCS正常退出0、无timeout，耗时199.400秒。终态资格
与父端重新运行完整collector均通过，除各自输出pins外所有
语义字段一致：36339条指令、19次向量写、18420个必需活跃
字节、2344项软件检查、完整VRF/尾部/源保护区/CSR及请求归属。
相对773项的144个预定缺失坐标全部命中，Line/Condition/
Branch/FSM增量为0。父端独立资格SHA：
`3b2b157a5ff7ca50e0809ec8a8771d96e282b864185717adc6abc60828249524`。
后续准入必须重算最新集合增量，保留ITLB新增坐标，不可用
773版OR结果覆盖后续774集合，也不可提前换算整体百分比。

ITLB正式准入774已完成，父端授权入口正常退出且完整证据和
输出pins封存：`itlb-bulk-offline-admitted774-parent-20261007-01`。
manifest SHA：
`5a5f9cdb4fcd5a26ba48628344a1c1028426709453bd8cb1adbc2c94d3344a28`。
旧失败去重入口保留；没有绕过去重、没有重复仿真。
VMACC775后继工具父端19项测试通过（14.469秒），实际prepare
已启动；要求全部6162项OR、774完整前缀、独立原生singleton、
最新144个目标差集及历史774范围ELF去重，不能用旧773诊断
替代这次计算。

下一批真实缺口优先AKV描述符高熵读入后精确拒绝/恢复、合法
单行上下文的大stride。静态候选570+314+168仅为不同编译对象
的缺失槽上限，不是官方收益。`0xfffffffe`仅满足V1偶数对齐；
V2_FULL需满足更严格的payload对齐，不能混用模式。全FF描述符
应先触发VERSION错误、无payload访问；单行合法stride的地址
乘数均为0仍须独立oracle、真实地址/VRF/CSR/guard检查。
后续case与775整体报告并行准备，不为了等待未来case无限
推迟新的正式百分比，也不改正在运行的冻结报告集合。

## 最新独立复核与待闭环事项

vfirst完整collector已通过，父端再次执行同一严格路径的独立
重放通过；两份qualification除各自input pins外的全部语义
字段一致。父端资格SHA：
`f648835ecb81792a89baccde689aad80dcb1e0f55a41def67483149dee3cc5c2`，
目录`vfirst-long-mask-qualified-parent-review-20261007-01`。
9918条退休精确标量对比、1024字节原生mask写、8次vfirst无
VRF写、384项签名检查及完整请求归属通过。相对775集合20个
目标槽全部新增命中，其他四类指标增量0。当前正在准备正式
776准入，不改正在汇总的775冻结集合或提前更换整体百分比。
进一步只读复核真实trace：8条vfirst（arch_seq 5/15/25/35/
45/55/65/75）均为VL1024、vstart0、eew0、use_vd=False，
无VRF写，allocations/completions均为1。冻结collector没有
逐条要求非load指令的上述上下文字段，776准入须补此独立
上下文门禁及错误注入检查；本次实际数据正确，不重跑VCS。

整体775任务已确认进入真正DVE：PID475742，exe为当前安装
的dve.exe，cwd为新独立汇总目录，并属于授权user unit。
不频繁轮询，原生五阶段终态验收之后才发布新统计。

实际缓存prepare及未修改的原check已通过，配置目录
`native-full775-cached-parent-20261007-01`，config SHA：
`9ebd932ebdc0dfba10f12b4d6d5ddd988be7d2af067650eab91fb4f653b8286f`。
缓存receipt SHA：
`d8db6ac5aa50b9d06f990dee5fb84980b3af64a61b8a218168c3e9f7fefb654d`。
实测332次调用仅一次解析、331次完整文本缓存命中，失败数0。
原慢prepare因成功后继已产生而停止，不是因观察超时重启。
唯一整体后台任务为`ara-native-full775-cached-parent-20261007-01`；
原报告入口运行，DVE内部预算5400秒，尚待原生终态资格。

vfirst真实prepare已通过，237个pins，prepared SHA：
`07c589307c81c855b86e7fda468c6ddfdbd5c82e599a8ec6c0f39ab8ebed23b5`。
独立后台任务`ara-vfirst-long-mask775-parent-20261007-01`已启动。
父端核对真实simv PID473252的exe、cwd和所属cgroup一致。
预算600秒，复用镜像、不生成FSDB；未准入正式覆盖集合。
该仿真随后实际正常退出0、无timeout，用时63.166秒；软件
自检SUCCESS，81次请求/响应、0异常/协议错误/在途遗留。
独立资格任务`ara-vfirst-long-mask775-qualification-parent-20261007-01`
已在后台启动，尚待完整差分和原生增量验收，不能仅据自检
计入覆盖率。

本轮新增工具的真实入口核查拦截了三类问题：vfirst collector
将6162条metric-instance记录误作unique scope数（实际2624）；
测试fixture的`0x`格式不符合真实CSV字段规范；两个依赖合并
调用误传三个参数给仅接收两个参数的接口。修复仅涉及未封存
的新验证工具，不修改RTL或降低未知值/正确性检查要求。父端
重新运行38项检查全部通过（25.172秒），包含真实prepare、
原生mask/标量参考、完整6162条OR及负向错误拒绝。

整体汇总prepare的性能问题已静态定位：对332个对象重复解析
同一份8.7MB历史EL。独立后继`prepare_full775_cached.py`在同一
验证epoch使用完整文本相等性缓存解析结果，返回集合副本，
失败不缓存；原源码、精确EL parser及最终原check保持不变。
helper和tests额外封存进config。父端8项检查通过（8.117秒），
独立审查未发现保护范围变化；真实prepare仍须终态验收。

本轮父端独立检查通过：`test_report_native_full775.py`的10项
测试（15.143秒），`test_full775_protocol_independent.py`的17项
测试（0.173秒），以及`test_preflight_vfirst_long_mask.py`的11项
测试（0.918秒）。这些分别验证整体汇总入口、775集合/豁免
保护契约和软件激励预检，不等价于新的RTL仿真通过或新的
整体覆盖率。当前保留较早启动的准备任务，目标目录为
`native-full775-branch720-mfpu272-rvh60-prepared-agent-20261007-01`。
父端停止了自身重复prepare（退出143，未形成配置目录），
没有停止较早任务或删除原始证据。须在封存、独立审查及原生
报告终态验收后才能发布新百分比。

长mask激励软件预检封存SHA为
`11498ad03cb3378280ea6c92f9cfa525ec955707516fe8ef86a874a9cee99cec`。
RTL的`vfirst_count_d`由全零扫描块的步进量或块内首位位置
增加，因此跨越计数位边界的首位位置是具体可检验的覆盖假设。
仍需真实RTL的scalar结果、mask回读、CSR/保护区、无额外VRF
写入和原生增量闭环；20个静态目标不能提前视为命中。

775正式准入已完成：`vmacc-offline-admitted775-parent-20261007-01`。
manifest SHA：
`59d67f7d5088baefaa498eda1d8e0f607e0eaf87945cc79a5f83607f8d679a13`。
ITLB948增量证据保留，VMACC按774重基后144个预定坐标全命中。
新原生整体报告将一次性纳入已验收的Branch720、MFPU272和
RVH0精确规则；正式报告结果出来前不计算或承诺新百分点。

后续真实激励还包括MASKU的`vfirst.m`长mask首位扫描：
VL1024、e8/m8、vstart0，首位2/4/128/256/512/1023及全零/首位0。
静态目标仅20个未覆盖槽，不能夸大收益；应检查精确scalar
返回、源mask和guards、CSR及无trap。普通软件不能翻转冻结
配置`VlBitMaskEnable=0`的512个候选槽，不安排无效随机测试。

最新父端检查：queue FP312资格工具、768 V2汇总工具及TLB
ASID/VPN/RSW激励构建和运行入口合计34项测试通过（31.535秒）。
这些是采集/验收工具的检查，不等价于新增处理器测试通过，
也不改变下表的正式百分比。冻结的失败或超时局部记录保持不变；
源码已证明但局部原生资格未完成的候选，必须在新完整汇总
会话中通过五阶段、精确EL、保护补集、系统范围及实际工具
正常退出检查，才能首次计入。

LZC可靠库候选父端重放独立测试及二叉优先级树归纳检查通过，
匹配实际WIDTH=25/51/109。候选收窄为23132个已赋值内部位；
212个未驱动备用位和96个端口对象保留，不整体豁免数组。
父端证据：`fma-lzc-binary-proof-parent-20261007-01.json`，
SHA为`fbb02ebcebe289081ba51d32e359f680fc9ea188f7f789acf7a1d9668b2afa53`。
这是二值计算逻辑的证明，不声称任意四态或启动瞬态等价；
精确原生范围及正式统计尚未闭环，因此未计入覆盖率。

新增Sv39 ASID/VPN/RSW矩阵已由父端完整重算预检：110项输入
pin匹配，Spike 11032条指令、3811次GPR写及2394次内存访问；
107项软件检查、96次目标读、1536项PTE最终映像、RSW分阶段
写入、保护区域和CSR恢复均通过。相对768集合预测984个缺失
序列化方向，尚非实测。父端已启动独立600秒限时任务
`ara-cov-tlb-asid-768-20261007-02.service`，运行入口MainPID
165189且active/running；正确性比对和实际覆盖收益通过后才
准入，不自动重试。预检SHA：
`f9c45fbe5209b312d897e8c8573a1b22628175600e26679aea1b76df0da7fd19`。
随后VCS正常returncode=0，CPU用时61.270秒，软件报告成功。
当前状态为`SIMULATION_EXITED_NOT_ADMITTED`；RTL提交轨迹、
参考结果及实际新增方向仍待严格核验，不能仅凭成功打印准入。
后续严格资格已通过，目录：
`tlb-asid-vpn-rsw-qualified-768-agent-20261007-01`。
父端12项采集负向/正向检查通过，并重放全部证据pin、完整
6162项模块/指标位图的769集合OR与逐指令标量比对，均通过。
资格SHA为`5936877444b0d5edfe9a694b30e2e50f55bfe3e2db7ab7f7eb846533eca1b31a`。
实测新增1058个序列化方向，其中984个为预定ASID/RSW目标；
不据此推算官方百分比。107项软件检查、PTE/CSR/保护区完整
独立结果核验通过，未修改向量状态，不声称独立AXI波形验证。
下一步正式准入769，再纳入后续原生完整报告。
769现已正式准入，父端封存manifest及全部output pins复核通过：
`tlb-asid-vpn-rsw-offline-admitted-769-agent-20261007-01/admission-manifest.json`，
SHA为`b6bd6cca9a31b67b38ae834bfb5736ed04c31f14302efeac2440657147317ecf`。
上表正式百分比仍对应766；在准备的768汇总保持其冻结集合，
不为了追赶新项反复重建入口或宣称769百分比。

新完整汇总入口`report_native_batch768_v3.py`区分已有局部资格
和源码已证明、需在完整会话首次完成资格的候选。父端V3及
LZC独立归纳/负向工具共15项测试通过（17.839秒）。原局部
超时/失败记录不改写成PASS；最终仍须通过真实完整采集验收。
审查要求连同间接加载的Tcl一起封存，不能仅绑定Python入口。
首次实际完整host预检拒绝的根因已定位：新observer注入按
字符串排序的同scope清单，覆盖旧child的原生遍历顺序，使
`gen_schedule_mask[10]`排到`[2]`前面。全部对象相同，仅顺序
错误。新V3的host模型保留已有清单顺序并要求排序后的完整
身份集合相等，未削弱真实原生五阶段检查。父端修后9项测试
通过（35.717秒）；两份首次失败准备目录保留，未启动DVE。
修后独立准备目录为`native-batch-full768-v3-prepared-agent-20261007-02`。
修后准备、生成Tcl完整五阶段host及独立check均通过，16520项
输入pins封存，config SHA：
`5b6a373a2937cf15809143c813ce250d4af49af011e2564a5f68fda8542071fc`。
父端已启动唯一完整汇总任务：
`ara-native-batch-full768-v3-parent-20261007-02.service`。
stdout直接写该目录`service.log`，不使用外部sidecar冒充；
首次source候选资格与已获局部资格的组分别标记，实际完整
原生五阶段和终态验收通过后才应用。任务限时5400秒，不
反复轮询，不预估或提前宣称新的覆盖率百分比。
父端已核实真实DVE PID178935的exe和cwd，stdout含
`EXACT742_LIVE pid=178935 launch=178874`；不是仅启动入口。

LZC窄范围原生资格完成，父端完整只读重放实际终态、213项
证据pins、精确二维EL及五阶段/接口保护检查，结果相同，未
修改原产物。目录：`fma-lzc-assigned23132-native-agent-20261007-01`。
资格SHA为`650c8ae7b592720ef66b1fe13252193a789bbdfcc9ce0c6d47267cd739b5ec2f`。
已审查23132内部位、46264双向坐标成员；212备用位及96接口
对象保留。6项EL范围负向测试与5项独立备用节点无fanout
证明测试通过。备用无fanout证明不是零值/X状态假设，尚未
加入原EL。局部资格不等价于总体统计，本项未应用至正在
运行的768报告；下一次需核对与既有EL的重叠及完整保护范围。
LZC与768完整现有EL的精确交集审查已由父端重放通过：32个
新实例/128字段/46264方向的共享实例、共享字段与重复方向
均为0；3项归属测试通过。证据：
`fma-lzc-assigned23132-existing768-intersection-agent-20261007-01.json`，
SHA为`928d878ed8f8513a64657f645515f3a379589a9a391e9a60e4dd7a169536162d`。
无须改写旧owner；仍未应用至总体。下一完整汇总计划绑定
769正式测试集合、此LZC局部资格和queue FP312的首次完整
资格，当前768采集保持冻结且独立运行。

下一新增激励为MFPU重启末字边界：e16/m8、VL512，三个
互不重叠且8对齐的寄存器组；start508、511、0各4条FMA，
每条前重写vstart，各阶段重置目的初值8，活动区最终40，
prestart区保持8。父端完整重放Spike预检通过，10项实际与
负向测试无跳过，检查逐条完整VRF、三份快照和60项CSR结果。
预检验收目录：`mfpu-restart-word-boundary-preflight768-agent-20261007-01`，
SHA：`2729b8024b22d811bc156445475f5d4dda65c15d98eac555fd1643004060e85d`。
已授权独立600秒单次VCS；726个源码/位图缺口仅为候选，
不得宣称已覆盖，实际新增收益须相对正式769集合核算。
尚未通过DUT，不计入覆盖率，不改RTL。
运行入口5项检查通过，父端核查其复用既有600秒冻结运行器。
已实际启动`ara-mfpu-restart-word-boundary-769-20261007-01.service`，
VCS PID196897、exe及独立cwd核实；prepared SHA为
`1aa28e46f7c7b253c099fcd4e35ef422691aae795265f8ad90317f797d54788c`。
完成后自动严格资格检查，但不自动准入。新增点相对769统计。

MFPU任务现已正常完成，VCS CPU用时257.880秒。父端在独立
目录完整重放资格采集，不重新仿真：53077条标量退休、29235次
GPR写、6856次标量提交内存访问，以及50条向量目的写指令的
14376字节逐指令结果比对通过，无跳过、不完整或非位精确结果。
12条FMA另与独立结果模型逐字节核对，12288字节完整VRF快照、
3200字节源/保护区及60项CSR结果通过。相对正式769实测新增
726个目标Toggle序列化方向；Line/Condition/Branch/FSM无增量。
原资格SHA：
`17283ab5ea53fd91e6077d3aa08e58e4fd96b3b53034e1ddf25378860fa454af`。
父端重放目录：`mfpu-restart-word-boundary-parent-replay-20261007-01`，
SHA：`3ea2f60559ea985dd8c95749231944a8ea73574e26641e5bc9b33455c527b511`。
全部结果及raw_gain与原资格相同；正式770准入正在离线准备。
此处新增方向数不是官方百分比，不更新下面766项正式指标。

770现已正式准入。父端23项准入工具正向/负向检查通过，并独立
重算全部产物：精确769前缀、770唯一VDB、6162项完整位图OR、
ELF去重、所有输入/输出pins及结果与封存产物一致。manifest：
`mfpu-restart-word-boundary-offline-admitted-770-agent-20261007-01/admission-manifest.json`，
SHA：`7f8cbc5061a61c776d008590617c8727a07ead3c87dfb762139626166d2ba80a`。
本次不重跑VCS、不修改RTL；正式百分比仍需原生报告。

薄后继`report_native_increment770.py`已由父端7项测试通过
（23.338秒），包含真实6162项形状/OR负向检查和完整五阶段
host检查。它一次汇总正式770、已合格LZC及queue312首次完整
资格，避免额外769会话；冻结768和769入口不改写。原768的
资格或真实正常终态缺失时拒绝prepare/run，不用合成报告替代。

父端进一步以真实770 manifest执行薄后继population检查，8427项
pins、精确769/768前缀、6162项完整OR及770唯一成员全部通过。
尚未启动后继EDA，当前768原生完整采集继续独立执行。后续
缺口分析须扣除已准备的固定字段与LZC范围，不能把旧766排名
直接当成770剩余缺口；读端operand_payload固定零的wdata不得
重复豁免，写回数据、动态地址和控制路径不能据低覆盖整体排除。

完整768采集已终止：systemd wrapper为failed/ExecMainStatus=1，
service.log首个验收错误为旧observer整字段规则拒绝
`accumulator_updates_o[31:0]`。采集产物已包含五阶段库存，但
尚不视为合格报告，不使用summary.csv.partial作为正式数据。
原运行器仅在DVE wait返回0之后调用verify；因此该错误发生于
采集后的离线检查，不宣称wrapper成功或补造终态。保留原始
失败目录，下一步按精确EL、原生对象/位范围及完整未排除补集
定位规则冲突，离线闭环优先，禁止盲目重跑DVE。

父端逐scope复核进一步定位为四个QBS层级旧统计/探针整字段
owner遗漏，而非单个新accum66部分位。离线适配必须从封存的
child/diagnostic source全范围恢复这些owner，不允许把部分位
提升为整字段豁免。首次父端6项工具测试为5 PASS、1 ERROR：
真实DVE导出的cause块混入已批准的diagnostic注释，旧按相邻
行归属的partition拒绝Unknown annotation。后继按封存模板
逐scope核对完整批准注释集合，再按字段及checksum路由规则；
未知注释、未知scope/checksum、缺失/额外位仍必须拒绝。当前
没有把此次失败采集提升为正式资格或百分比。

修后的离线工具父端9项测试全部通过（78.759秒），包含真实
五阶段库存和精确EL、84个旧whole-owner的168项导出冲突、
未知/缺失注释、额外同scope foreign-checksum空block、方向
改变、部分位不能授权整字段、保护字段/清除阶段误排除及真实
wrapper失败边界。完整离线采集复核已实际启动，PID231694，
使用原封存768数据，不启动DVE/VCS。完成后仍需独立父端重放
和全部pins复核，不能凭工具单元测试宣布正式覆盖率提升。

新增窄范围候选：masku_operands两个内部VL mask向量，各256位。
冻结源码VlBitMaskEnable为不可覆盖的literal localparam0；完整
写入检查证明所有非零驱动都位于关闭分支。输出接口保留。
父端6项正向/负向测试通过，并完整重算107项pins的源码/形状
证明；候选共1024个未命中序列化方向，尚无原生资格、不用于
官方百分比。证据：
`masku-vl-disabled-internal2-source-review770-agent-20261007-01.json`，
SHA：`8b2496d8a38f297658cbc91187d0961c3bbfc048f29518af2c35c50de02c66a5`。

770剩余缺口静态审查排除了低收益的QBS scale扫值：当前有限
数据字段二进制缺口很少，不能由旧741总容量推断。下一激励
候选是Sv39互补合法虚址上的RVV load/store，以覆盖地址副本和
B-response元数据；预检应证明canonical映射、PTE及源/目的
数据正确，再以独立Spike/内存检查准入。约3232个低64位方向
仅为潜在收益，未实测。动态仲裁库和SRAM工作端口仍保留，
没有为凑80%整体豁免可靠模块。

Sv39候选采用S-mode后继，不使用不能驱动冻结Ara翻译路径的
MPRV-only版本。父端19项测试通过（52.414秒），另完整重算
72项pins、ELF符号、58788条Spike退休、3113项软件检查及
48次精确S-ecall cause9/返回。三阶段每阶段16对向量store/load，
固定e64/m1、VL8、64字节范围；上下canonical互补虚址映射
同一物理页，三份完整VRF快照与整页读回均核对。预检SHA：
`2c5a419eddde4de7b8750ffed7b48b34918216af283ef8c8cee018094f2305f8`。
预检不等价于DUT通过；实际B-metadata槽位推进和方向增量
须单次600秒冻结镜像仿真确认，不允许忽略预期之外的异常。

后继离线768绑定的770入口父端7项测试通过（79.111秒），保留
原wrapper失败证据并要求精确合格closure，而非冒充原服务
退出0。当前唯一prepare进程为PID239957，目录
`native-increment770-offline768-prepared-agent-20261007-01`，
避免父端重复准备；生成Tcl及配置封存检查通过后再启动原生
完整汇总。本次不扩大到尚缺完整原生对象绑定的mask候选。

770 prepared01生成host五阶段通过，153组、18240项pins；父端
独立check正常退出，config SHA为
`c19a38668c8e8bdacbafb07f15ed066fcc2407745ccf2034a720c0385f2624a5`。
启动前额外审查发现freeze769.py/.tcl的显式传递pins缺失，故
该准备记录保持HOLD，未启动EDA；check成功不等价于依赖完整。
下一准备须补齐实际递归加载脚本的绑定，并保存为独立02配置，
不能改写01或仅声称source已封存。此项不影响已独立复核的
正式768百分比。

修后的770 prepare02父端10项测试通过（70.744秒），实际独立
check通过；18242项pins包含冻结769 Python和21份递归Tcl。
config SHA：`6135d75162beef44ceb14fcd49e60d52026c57016d344c5aedc053d9577a0bd3`。
已实际启动唯一完整汇总服务
`ara-native-increment770-offline-parent-20261007-02.service`，
MainPID252774，真实DVE PID253951的exe/cwd核对通过，stdout
直接写02目录service.log。不修改冻结01、768原失败或正式结果。
该报告完成之前不推算LZC/queue312的官方百分比增益。

Sv39运行入口父端11项检查及固定正式770基线的3项后继检查
通过，完整prepared verify通过；prepared SHA：
`09197a827b1f674d1e3f220bc2083715a57d8fbf250cb097e771b9b89ee8f037`。
唯一服务`ara-cov-sv39-alias770-parent-20261007-02.service`已启动，
真实VCS PID253729的冻结exe及独立cwd核对通过；提交轨迹与
只读11信号VPD均已生成。仍为未准入候选，单次预算600秒，
systemd RuntimeMaxSec630、停止宽限10秒，不自动重试。完整
逐指令/预期异常/VRF/CSR/同PA整页与实际metadata槽位检查通过
之后才准入；VPD的64MiB是后续资格HOLD阈值，不声称运行期
文件大小监控。新测试不改变正在运行770报告的冻结输入集合。

下一正式汇总入口`report_native_increment769.py`已完成父端
8项测试（37.057秒），生成Tcl完整五阶段host通过，正式769
的精确768前缀及6162项完整OR通过；仍是预演，不是原生结果。
实际prepare须当前完整768资格通过，且真实systemd unit/PID/
配置绑定匹配、inactive/dead、ExecMainCode=1及ExecMainStatus=0。
原完整运行器不输出terminal.json，不要求补造不存在的终态
文件；未知或active状态继续HOLD。所有间接Tcl和unit receipt
作为输入证据绑定，新增组不能继承虚构的局部资格。

历史766项正式报告为离线闭环：父端完整独立重放通过，资格和
closure的SHA与首次审查完全一致；未改原报告或重跑DVE。
目录：`native-batch-full766-offline-closure-parent-review-01`。
资格SHA：`0ed4bbb08ea2dda3ad7b8472698d7ee7964c54db3c3dc0d150284ee40e20d5e8`。
closure SHA：`3dbabf3983881b2fd3f02052e696ffd5f40c08db2ecea1f24d2b49ee651e228f`。
外部真实stdout、启动配置及全部阶段均绑定，四项离线工具
测试通过。正式范围保持`ara_tb.dut.i_ara_soc.i_system`。

最新正式报告现为768项，完整离线复核已由父端独立重放至正常
退出，资格和closure与首次审查逐字节相同。目录：
`native-batch-full768-offline-closure-parent-review-01`。
资格SHA：`29f835bb59e38bc770793849b5fc468a0d92de2578567bce0ce6ad2079569dee`。
closure SHA：`a31cf87be8ffc0dea70cccef37ceb006c0aa64d9013442f8f7e4426e9832d78b`。
原采集失败目录保留，完整原生五阶段/EL及保护补集已核实，
无重复EDA；原wrapper退出1与原生采集零返回的证据分别记录。

| 最新768项系统指标 | 原始/清除/最终 | 合理排除/重载后 |
| --- | ---: | ---: |
| Line | 85.21% | 85.18% |
| Condition | 82.10% | 82.11% |
| Branch | 82.95% | 82.99% |
| FSM | 70.29% | 80.64% |
| Toggle | 63.80% | 66.94% |

Toggle相对766增加0.62个百分点，尚未达到80%；FSM已达到。
官方Toggle hit/total仍未取得，不按序列化方向数推算分母。
770项集合已准入，上述正式百分比尚未纳入769和770的新增项，
以及下一阶段的LZC和queue312窄范围排除。

CSR02已独立实际启动，配置SHA为
`564012de8606df39dc91981ab857092cd6e49ff5f2463b8cebd40c5629c3786d`，
目录`csr-reserved1193-native-agent-20261007-02`，12项工具测试
通过。改用原生保存EL精确成员证明1193位双方向及111保留位
补集，并核查2031个其他对象/数组/端口与五阶段实际指标。
不声称逐bit GUI flags已取得。五阶段表格与EL已完整导出，但
工具退出超时，实际terminal为returncode=-15、timeout=true；
`qualification-hold.json`原因是`Actual tool/terminal`。
本项保持HOLD，未完成资格或正式应用，不计入正式覆盖率。
保留完整证据用于后续合并审查，不重复运行本次局部采集。

普通RVV stride测试已完成实际Spike预检及VCS运行。父端绑定
`stride-metadata-full64-preflight767-agent-20261007-02`后，20项
源/实际参考/负向检查测试全部通过，无跳过；另9项准入工具
测试通过。正确性证据包括9086条标量指令、21条向量写寄存器
指令的对比，4096字节全VRF、605项软件检查及94对请求/响应。
14个队列字段实测新增1500个序列化Toggle方向；VL1访问合法
基址，不宣称访问高地址。正式集合目录：
`stride-metadata-full64-offline-admitted-768-agent-20261007-01`。
父端全量重算、输入/输出哈希和独立参考/合并结果复核通过。
准入manifest SHA：
`1add5889916fd9cfe2bb6e95368a2a86d43f1d0ac27ac4cf89786639cb6f4198`。
读请求常零字段的精确候选审查继续推进。尚未完成的豁免
不计入上表，不以新增方向数量推算正式覆盖率百分比。

QBS cause9/constant13原生采集已实际exit0，无超时。原验收器
不接受DVE百分号字符串，因此保留原拒绝记录，以严格两位小数
单百分号解析适配独立重放；其余源码、配置、哈希、实际工具、
五阶段对象、EL及补集检查全部保留。父端独立资格通过：
`qbs-cause9-constant13-native-offline-qualified-parent-20261007-01/capture-result.json`，
SHA为`46df5c8c2ec8b08df3c3ca2f7101cbb5acacfdd78e4917be312bf3d72d112006`。
622对象中只排除22个精确范围、743个源位，保留600个其他对象、
216个目标补集位及数组；未应用至正式人口，未宣称百分比收益。
父端原生/离线验收工具共14项测试通过。

读请求108字段原生任务已启动，独立目录
`requester-read108-native767-agent-20261007-01`，配置SHA为
`ebce4b0ab67e634d168f1f055272e11b4507607999e50d55eadf2149322de5d6`。
实际DVE PID130810、exe及cwd已核实，随后exit0，无超时。
父端全部24项源码/负向原生工具测试通过，并完整只读重放原
inspect：仅把不可重复写入的结果保存替换为与已存结果相等核验，
所有实际终态、源码、哈希、五阶段标记、对象及EL检查均保留。
资格SHA为`a31abca542924c82f51f53e4e2c5ed17b22c3476eae035ecdccd5f355dbe749b`。
本项只检查读端常零
wdata/be/wen，不排除读地址/队列选择、VRF读回、握手或写路径，
其余2876对象保持保护；已具备下一全人口报告的资格，尚未
应用至正式百分比。

原生MDA展开探针已exit0，但对象列表层无法展开，未取得可靠
物理位映射；保存失败证据，不猜flatten、不新增EL。完整766
报告中CVA6 Toggle为51.69%、Ara为70.23%、QBS为73.04%，
regfile为97.28%。后续优先按完整集合的协议/地址/配置字段
可达性定位大缺口，不用单例比例或低熵算术数据猜测系统分母。

下一高收益源候选为冻结RVH=0下两个TLB的guest内部PTE字段。
父端43项输入/源码/配置/覆盖证据哈希核对通过，并实读TLB
整体复位、保持和受RVH保护的唯一写入逻辑；仅726内部字段、
4224源位为候选。普通PTE、标签、valid、ASID、命中、flush、
PLRU及端口/数组保留，PTW无复位保证的guest字段不能套用。
原始缺失8448个序列化方向仅作诊断；待精确原生资格和完整
人口五阶段统计，不宣称已提高覆盖率。

下一768汇总入口已完成父端静态审查。首次独立测试发现新
partition重复/错误移动旧annotation，导致完整retained union
不能通过原FSM observer验收；仅修正新入口，旧封存解析器
与证据保持不变。修复后的汇总/TLB/CVA6固定字段共26项测试
全部通过，不以宽松旧验收器绕过问题，也未启动失败的EDA。

另两组高收益源候选已获准在证明与负向测试完成后单次原生
审查：QBS accumulator固定FP32配置下66个禁用格式/运算组
内部result字段（2112源位）；CVA6关闭FPGA/ZCMT及accelerator
first-pass默认字段（诊断4396个原始方向）。父端实读源码：
first-pass初始化零、use_imm明确零、instruction result高32位
零扩展；FpgaAlteraEn=0下previous-entry副本为零，RVZCMT=0
时jump_address为零。未驱动FPGA FIFO helper继续HOLD。
QBS证明覆盖全部合法请求和优先级，活动计算数据不受测试输入
范围限制，父端6项源证明测试通过；flags、舍入、特殊值、握手、
活动计算及2251个其他对象/108个数组保持保护。
这两组与TLB均尚未取得新的正式覆盖率百分比；下一全报告将
等待已获资格项集中纳入，避免逐项重复全量采集。

CVA6固定120字段随后原生exit0，但最初验收因119个GUI/typed
显示别名被拒绝：88个单比特vector显示为scalar名称，31个数组
用`[0]`显示`[0:0]`。通过typed shape、path/meta/type的严格
逐项双射作只读离线适配，不删除数组维度、不宽松匹配宽vector，
保留原失败日志和冻结helper。父端8项负向测试及完整独立重放
通过，SHA与首次资格一致：
`cva6-fixed120-native768-offline-qualified-parent-20261007-01/qualification.json`，
`3944a6e765d78ee007833e526c5f203be236dfc7818cb0cfcfa5d6bb7beb206d`。
保护1403个其他对象、50数组、两处低32位；未纳入HOLD1656。
此项为原生条目资格，不是正式人口百分比。

TLB02单次采集已实际运行，配置SHA为
`22b16fecce042cf781301b59323821ad0e4532fc46206694a13d7f1a8ef5424d`。
父端launch工具测试通过；五阶段996对象/每scope与8448精确
EL成员、DONE及EXIT_DISPATCH已输出，但随后退出超时：实际
returncode=-15、timeout=true，资格为HOLD_NOT_APPLIED，
原因`Tool terminal0 required`。不能用完成标记替代正常工具
终态，也不能计入正式豁免。QBS accum66也已实际运行，
配置SHA为`c08cab66d3ecd385d397b09433ea0daacc49fb9350a720eef396185a527f04c5`。
实际exit0，但first-stage rooted表因同名子scope无法唯一绑定
而报`Nonunique root not bound to exact fullscope/displayed node`，
未完成五阶段，保持REJECTED_NOT_QUALIFIED，不作为豁免依据。
后继须修正准确视图绑定或在全人口会话首次完成精确资格，
不伪造local PASS、不修改旧封存输出或重复有效采集。

父端本轮另通过20项CVA6原生/operand queue源证明工具测试、
9项QBS accum66原生工具测试。operand queue新差集为312字段、
1152源位：ALU实例显式FPUSupportNone保护下的默认零字段，以及
MFPU全局fp8默认零字段；EW8转换中的局部同名变量不能混用。
已扣现有336排除字段，活动FP16/32、舍入/flags/control仍保护。
该差集目前只完成源审查，ALU合并参数形状必须经实际原生身份
进一步绑定，尚无批准EL、EDA启动或正式百分比收益。

## 历史过程（以最新独立复核为准）

766项DVE采集已结束，全部五阶段原生表及DONE标记已产生，
但正式验收失败：`Foreground lifecycle stdout missing`。
真实systemd服务将stdout追加到独立
`native-batch-full766-service-agent-20261007-01.log`，继承的
验收器硬要求报告目录内`service.log`。原报告、failure.json
与外部日志保持不变；后继只读离线闭环须绑定真实启动配置和
实际日志，完整复核全部阶段，不能伪造路径或重跑DVE。
原失败记录随后已由上方独立离线闭环验收，不再作为当前阻塞；
原目录failure.json仍保留，以追溯采集器的日志路径错误。

QBS全102实例残余审计与数据语义共15项父端测试通过，SRAM
数据与相关binary尺度字段已覆盖，不启动没有明确新增目标的
正power-of-two尺度VCS试验。13个精确常量范围仅静态候选，
还未原生验收；fault cause等保留功能路径继续做完整驱动锥
审查，不根据现有输入低熵排除可达功能。

普通RVV残余按formal766实际typed清单重新分类，不再盲目追加
mask/FP数值随机。36个operand queue的8190个缺失序列化槽中，
5376属于禁用FP格式字段；有效MFPU FP16/32数值字段缺口为0。
这些计数仅用于诊断，不等同DVE分母，不据此自动豁免。
已准备`vgap_stride_metadata_full64`：VL1真实strided load/store
使用四个64位stride模式并轮转四个队列槽，再做VL2恢复；全部
实际VL1地址仍为基址，不宣称访问高地址。14个队列字段有条件
预计新增1500方向，需先严格Spike/ELF/源码检查及独立605项
结果检查，后续实测才准入。父端源预检与CSR失败模型合计
15测试通过。未以预测替换实测，也未更改RTL。

CSR01导出问题的安装接口证据已核查：
`preferencesCovMainMenu.tcl`的取消压缩菜单明确调用
`gui_cov_tgl_compress -id $window -opt uncompress`。后继仅对
两个代表对象做只读视图探针，不加载候选豁免；先确认实际
行结构及双方向属性，再修正导出，不缩减1304位补集要求。

767项已正式准入，父端完整verify及六项准入测试通过：
`qbs-payload-residual4-offline-admitted-767-agent-20261007-01/admission-manifest.json`
SHA为`a4dac6fb073fc665cb8f274557d04c8d2bf3ad9291a70bda03bcfdce3542b405`。
继承全部766前缀、767唯一成员及6162实例原始OR；该项新增
Condition15、Toggle504方向（bank0 226、bank1 278），其他
原始指标增量为0。仍不以方向数量代替官方百分比。

CSR46对象1193位独立原生审查01未通过，目录为
`csr-reserved1193-native-agent-20261007-01`，配置SHA为
`bb4624d77946b3edee17fed9dfaf2b2411c69c8169a72843f31ef84345c05f36`。
父端16测试通过，逐驱动语义证据及完整写入语料已封存到
`writer-proof.json`。审查会检查全部2077个CSR对象及目标对象
所有保留位的双方向状态。实际before导出只有8个node位，
目标对象应有1304个完整位清单，vector位未导出，检查器拒绝
验收；未应用candidate EL，没有新增人口豁免。后继先定位
原生展开/压缩行格式，保留01失败证据，不放松精确补集要求。

766项统一报告的原启动记录（已终止，见上方日志绑定问题），目录为
`native-batch-full766-agent-20261007-01`，配置SHA为
`ce709dbf1da6a16f16c8c10e7c2006c59429a3ff08c09237a3355a7267f53650`。
父端复核12949项输入pins一致，八项入口测试通过；已确认实际
DVE进程64877运行过。报告加入已独立资格核验的RVFI788、CVA6
RVFI457及PMP0内部770对象，并在五阶段读取全部目标和保护
补集的排除状态。终态独立验收前，正式百分比仍采用下表765项。

后续激励按formal766实测并集去重：四条QBS命令已实际完成，
仿真CPU耗时149.550秒，资格SHA为
`b9f739e6bc557736c3bf2fc4996acd58cf49c522fdc85ec47685079113d92cad`。
新增504个原始Toggle方向，其中预测504个命中500个。父端
537项输入pins及输出pins核对一致，独立重算完整runtime audit
与封存结果相同；residual runtime与算术审查合计15测试通过。
该项已完成上方正式767准入，不把方向数换算为官方百分比。已有14个预测
未命中点涉及pending slot0的仲裁，仍保留未覆盖，不据预测
豁免。CSR另有46对象1193位完成静态候选审查，尚待精确位级
原生资格检查；不排除有效权限、中断、SATP、计数器或可写状态。

冻结镜像的FMA实际为32个fpnew_fma实例，不存在C910 FMA算术
子模块；不沿错误层级继续排除。其余大缺口涉及rounding、LZC
及classifier，仍保持保护。已审核的额外纯算术十对象只有28个
历史缺失位置，优先安排其他高收益真实激励，不启动低收益EDA。

PMP0内部770个对象完成原生资格，父端独立重验与封存结果
完全一致，SHA为`b3e8898b50035449d861c4f41e283485df5f5e2bd6bf95cc481d3f1559191954`。
另外严格核对五阶段实际TSV均为2077个唯一对象，无额外对象；
两份EL理由文本均为精确的复位后常零理由。7个输出别名及
全部动态d保持保护。原生helper14项测试通过；新统一766报告
须进一步在五阶段读取全部2077对象的excluded状态，证明目标
与补集的实际应用，不只比较身份清单。父端766入口八项测试
通过(22.486秒)。新人口正式百分比仍待完整报告。

正式人口已增加至766项，父端完整封存verify通过，并独立执行
六项准入测试通过。`qbs-payload-matrix4-offline-admitted-766-agent-20261007-01/admission-manifest.json`
SHA为`bbad20298653af04606493c1e6c6433cf22bb9f532b4cc16f52922fe9b7bfb3b`。
完整765项前缀、766个唯一成员及全部6162实例OR保持；新增
line 0、condition 12、branch 0、FSM 0，QBS payload实测新增
Toggle方向2561。新统一报告未验收前，正式百分比仍取下方
已验收765项报告，不因人口增加而直接替换其标注。

最新765项统一报告已完成，父端完整verify再次通过：
`native-batch-full765-agent-20261007-02/qualification.json`
SHA为`6f375f9e5fd6ee04a1a0dcf5a70a12ce88e774e7d7ffe9500cc8cbb65aaa751a`。
应用与重载相同，清除与final恢复raw；FSM已超过80%，Toggle
尚未达到。报告没有纳入随后资格完成的RVFI788、CVA6 RVFI457
及新matrix4激励，不能将这些后继候选计入本表。

| 最新765项系统指标 | 原始值 | 合理排除及重载后 |
| --- | ---: | ---: |
| Line | 85.21% | 85.18% |
| Condition | 82.08% | 82.09% |
| Branch | 82.95% | 82.99% |
| FSM | 70.29% | 80.64% |
| Toggle | 63.66% | 65.20% |

相对763项，FSM增加0.95个百分点，Toggle增加0.12个百分点。
新matrix4资格SHA为
`f619daa019a4488d71b27b722fd509352b6bf12ca8b9ff903675ef724e11e12f`。
父端550项输入/输出pins一致、七项资格测试通过；独立重算
完整四命令runtime audit与封存结果一致，未发现hart异常。
新增2561个原始Toggle方向（bank0 1155、bank1 1406），预测
2320个中命中2306，14个未命中保留。后继766须保留完整765
前缀及6162实例OR，不把方向数直接换算成官方百分比。

CVA6父层RVFI457资格SHA为
`e5ae15157446f1848413fda855cea69b6910c08e590b1f5e44a8027ecfd2e5cf`。
父端重新执行完整原生五阶段并只读比较，资格完全一致；保护
1315个对象及31个数组。尚未应用后继全量人口报告。

实际ratio诊断01因300秒超时未验收；所捕获的raw/applied
109行仍显示百分比而非numerator/denominator，故不能宣称
官方分母已导出，也不能盲目加时重跑。后继先核查无id的
`gui_cov_show_value`当前view及实际列读取语义，不改评分规则。

RVFI788原生04已完成；资格SHA为
`ff9ceb495a70de8d602788128c030a1b5e3698378dccc0cbdce7884fb6f3108d`。
父端重新执行全部五阶段检查并只读比较，结果与封存资格一致。
重验时唯一额外项为结果文件自身的哈希：独立核实该seal后，
仅从重算输入pins去掉这一自引用项，其他字段必须完全一致；
原始文件不重写。788对象精确保存/重载，418对象保护，四份
empty EL为空。正式人口应用及其百分比仍须后继统一报告验收。

## 历史过程记录（以下状态已由上方最新资格与准入结果取代）

QBS UART matrix4已正常退出，DUT报告四条命令errors=0，仿真
CPU耗时148.680秒。它仍未完成独立结果资格和准入，不提前
计入人口或宣称Toggle增量。CVA6父层RVFI457原生任务已确认
进程38943运行，配置SHA为
`4a5c74a617c1e54bbc50674f51d1818f77d1e872f9f87053fa9024332373f28c`，
父端718项pins无漂移；资格尚待终态。

当前765项统一DVE报告已实际启动，输出目录为
`native-batch-full765-agent-20261007-02`，配置SHA为
`7788edc2ea227e403c9fecc03abbc3085712e2a35a967028a317f6ee33b78c72`。
本次检查确认DVE进程16595仍在运行；完成并独立验收前，不使用
临时输出更新正式百分比。正式集合765项与已完成的763项报告
是不同阶段，不能混称。

两项新任务已经终止且未准入：QBS matrix4在600秒预算内超时，
日志出现非法取指地址及未知指令数据，需定位首个控制流偏离，
不能仅增加超时后重复试验。RVFI788原生03任务在保存`first.el`
后解析失败：DVE对单比特输出分别保存`0to1`及`1to0`记录，
而现有检查器仅识别整对象记录。后继检查必须严格核验两个
方向、精确bit范围及全部非目标补集，失败记录保留；此项不是
已经完成的豁免，也不是RTL计算错误的证据。

RVFI方向记录后继离线解析已独立复核：
`system_rvfi_native_el.py`对实际03的`first.el`严格识别500个
整对象及288个完整双方向对象，共788个目标；父端12项测试
通过，拒绝缺方向、重复方向、错误范围及额外非目标对象。
仍由原封存检查器核对scope/checksum/annotation和精确声明。
这只闭合导出格式问题，实际保存/重载/清除资格仍待后继验收。

QBS matrix4超时已定位到软件打印路径：完整hart trace在18591ns
记录`_fstat@0x800069f6`的ECALL，a7=80；18603.5ns随后出现
未映射trap-vector取指。之前的`__smakebuf_r`函数序言及SP更新
合法，不是栈指针异常的证据。后继仅恢复已有DUT UART的
`printf_`绑定，静态核验ELF调用路径后运行同预算独立测试。
旧失败ELF、日志、超时结果保留，不修改RTL或降低资格要求。

UART软件后继已确认实际simv进程33816运行，输出独立目录为
`qbs-payload-matrix4-uart-old-image-agent-20261007-01`。准备/运行
manifest SHA为`2e1a229bfd0ca211fba6ea45ac77613300a87774f018bb543da874c01297c469`，
父端410项pins一致，四项UART入口测试通过；两个实际ELF打印
调用均绑定`printf_`。600秒预算、独立结果oracle及资格要求
保持不变。尚未终态，不能将预检通过或trace增长记为功能PASS。

CVA6父层输出RVFI观测候选完成独立源级复核：
`cva6-parent-rvfi-output-source-review763-agent-20261007-01.json`
SHA为`f5e448c55889ad9d783a6c718a3d3000a2d39e53d5af9a23d1ef562a74754bbb`。
父端488项pins一致、13项测试通过。457个精确标量/向量候选
仅扇出至观测路径，源审查未发现硬件执行反馈；1315个本层
非目标对象及全部31个数组保持保护，子模块不在本候选范围。
此项尚未取得原生保存/重载资格，不作为已批准排除或已测得
百分比。DVE实际ratio诊断另行隔离执行，不修改正在运行的
765项汇总，且不根据序列化bit数量反推官方计分分母。

RVFI788原生04后继已确认实际DVE进程32360运行。配置SHA为
`3d8c5607cd8e3365aa036613a3889836c2cf5b9ca5d47c8d694f1b468f1a2d01`，
父端685项pins无漂移，11项04入口测试通过(26.626秒)。03实际
导出文件及完整1206对象绑定均纳入后继来源检查，仍未宣称
原生五阶段资格完成或正式覆盖率增量。

另发现配置受限的CSR Toggle候选方向：冻结SoC配置覆写
`NrPMPEntries=0`，并非默认配置包中的8项。`csr_regfile` reset
及next生成循环对全部64项强制零，因此PMP `q/next`有常值
源码依据；CSR写入临时`d`仍可变化，必须保持保护。编译
Toggle定义checksum为1176918775，`pmpcfg_q`有384个typed
leaf，`pmpaddr_q`等为明确packed数组。既有CSR branch豁免
不能自动视为这些Toggle已排除。父端三项PMP0配置传播测试
通过；后继须独立核对所有驱动、精确数组/范围及原生身份，
不得根据本候选声明覆盖率收益、豁免全部CSR或宣称PMP能力
已获验证。启用PMP的其他配置不能沿用本豁免理由。

正式集合增至765项，父端独立执行封存verify及九项准入测试通过。
`vmfpu-ured-reset-offline-admitted-765-agent-20261007-01/admission-manifest.json`
SHA为`834b457b607b9b73b21e4e2c8decaf5140d8e23cd8cc04c04bc7267d592d757c`。
完整764项前缀保持，6162个实例完整OR，新增唯一reset激励实测
FSM点4个，其他三类点增量为0。5543项输入及六项输出证据绑定
保持一致。本项未重新仿真、未应用豁免。新的全量报告须继续
从这一正式集合推进，不创建分叉人口，也不提前宣称百分比。

VMFPU可达INTRA reset激励完成后继独立功能资格，实测新增四条
FSM转换，随后已准入上述765项正式集合。`vmfpu-ured-intra-reset-qualified763-agent-20261007-02/qualification.json`
SHA为`a58b07f93515bc3809cdda94b8201ab2e4a439af3a1c0246327d82f9bc618b8a`。
父端146项pins无漂移，六项后处理测试通过。原01检查只允许
reduction取消，遗漏同周期仍在飞的seed：后继精确绑定seed的
seq37/vid0/PC及reduction的seq38/vid1/PC，不泛化允许其他取消。
无需重新仿真。epoch0核验4224字节初始写入；epoch1核验完整
4096字节VRF、680项检查、CSR flags及guard，所有128个操作数
为1、seed为2，树归约所有中间整数不超过130，结果精确。
四条reset转换属于实际覆盖而不是豁免；前缀不完整仅允许精确
绑定的reset取消请求，恢复epoch必须完整。不得宣称本项已入
763项报告，也不将有限reset测试称为完整复位形式证明。

此前完成的763项统一报告，父端完整verify通过。
`native-batch-full763-agent-20261007-01/qualification.json`的SHA为
`150ac4a03e2692367900551e054246fb0a7591d6c22d44e85bb3d72645668ce7`。
配置SHA为`54a49eefe913cadfe588cdf4f5f2e7cd1927af802e8b49f4fc646e3d74ebd084`。
保存/重载指标相同，reset/final恢复原始指标；非目标点完整审计
通过。下方旧762项数字仅作历史对照，不是最新统一结果。

| 最新763项系统指标 | 全设计原始值 | 合理排除及重载后 |
| --- | ---: | ---: |
| Line | 85.21% | 85.18% |
| Condition | 82.05% | 82.06% |
| Branch | 82.95% | 82.99% |
| FSM | 69.97% | 79.69% |
| Toggle | 63.61% | 65.08% |

相较762项应用结果，FSM增加0.14个百分点、Toggle增加0.12个
百分点，两个80%目标均未达到。764项新激励及VMFPU10、SLDU2、
C910 prepare/pack240资格尚未包含本报告。下一步优先核实DVE
实际计分对象/分母与残余大缺口；不能将大量序列化bit排除数
误解为等比例覆盖率收益。报告不宣称官方分母已独立导出。

764项QBS后继缺口矩阵已重新计算，父端六项分类测试通过。
`qbs-payload-current764-hit-matrix-agent-20261007-01.json`基于
实际544个方向增量过滤后，剩余映射可行HOLD方向16439个。
Q3_K/R4_BLOCK_MAJOR/phase10为当前高增量候选：224个side
metadata方向、608个条件性main方向。main预测依赖pending排空
及实际仲裁，不构成测得增量或不可达证明。后继激励优先按目标
并集减少格式/相位组合重叠，逐项独立结果检查后再准入。

C910 prepare/pack纯算术内部后继02原生资格已完成。
`c910-prepare192-pack48-native-agent-20261007-02/capture-result.json`
SHA为`c9611bb7e6ea4bbe197f4198d639ed2b3148c88ea62afd4d4608da812362fada`。
父端复核746项pins无漂移，三项02入口回归通过。240个目标对象、
10896个逻辑bit；3740个非目标保护对象在五阶段保持不变，包含
舍入、flags、控制、标量实例及子层。已有16个向量核的功能证据
绑定保留，不宣称完整IEEE穷举。01脚本入口失败记录保留，02
通过后才有资格进入后继统一报告，当前未应用正式百分比。

系统父层RVFI重复观测网络完成源审查，尚未原生批准。候选788
个内部node/vector共22126个bit，既有四个observer scope排除
不覆盖这些父层网络；450份冻结HDL的扇出审查未发现执行反馈。
418个其他对象（包含全部数组、硬件端口、clock/reset）保护。
父端六项源审查测试通过，仅名字/FOR_VERIFY宏不构成豁免依据。
762项中的36953个未命中序列化位置不是官方计分分母，不能据此
预报Toggle百分比。后继须完成精确原生保存、重载、清除审计。

QBS payload phase已完成后继准入，正式集合764项。
目录`qbs-payload-phase-offline-admitted-764-agent-20261007-01`，
准入SHA为`167f82e2a614e34e7dd8606bdb9211370cb573ebc0ad414baa99f7da355398f1`。
父端复核5483项pins无漂移，12项准入测试通过；原763项完整
前缀保持，6162个实例执行完整OR。新增72个条件点；payload
范围新增544个原始Toggle方向，其中288个是事前预测目标。
后继统一DVE报告尚未完成，不将这些数量换算为官方百分比。

SLDU两条精确转换资格已完成，原01因JSON/Tcl序列化入口问题
保留拒绝记录；使用独立02后继，未改动冻结源或失败记录。
`sldu-two-native763-agent-20261007-02/capture-result.json`的SHA为
`9bfdf3fd1b7ce9810071499e017f731d0053dddbb6b2f98c76e053b2359b0ab0`。
父端复核82项输入/输出pins无漂移，六项后继测试通过。
仅NP2_COMMIT->RUN及FIRST_WORD->DOWNSCALAR两条转换为目标；
后者依据FIRST_WORD期间的合法队列所有权与首结果边界。其余
34点保护。该源抽象不是全RTL形式证明，资格尚未应用全量报告。

VMFPU新增十点原生资格已完成，尚未应用全量报告。
`vmfpu-ten-native762-agent-20261007-01/capture-result.json`的SHA为
`d26981360b37062bd0c0c84d81709f1c3eeb9eba8c5c627821ab49c800db3ce1`。
父端核对69项pins和配置SHA一致，无漂移；12项原生资格测试及
六项源审查测试通过。四个固定Lane不可达状态及六条queue-owner
约束下不可能的直接handoff是目标，138个其他FSM点保持保护，
包含20条确实可达的reset转换。原生资格只证明排除身份、保存/
重载/清除及补集保持，不把源抽象模型称为RTL形式验证。

QBS payload phase新增激励已完成独立功能资格，尚未准入正式集合。
`qbs-payload-phase-qualified763-agent-20261007-01/qualification.json`
SHA为`7929b72d7ecb452d89cf59591acf5434db1945541a81e85f2ef0eff9619463b7`。
父端复核1209项输入/输出pins无漂移，四项资格测试通过。
测得此前预测的288个缺失Toggle方向全部命中；这不是官方百分比。
资格检查完整512字节目的结果、8192字节VRF、7328字节源/guard
区域及24项CSR，并核对退休完整性与command/uop/write生命周期。
该独立custom结果检查不等于完整标量ISA差分，也不宣称Spike
执行了custom指令。后继准入须保持763项前缀及全部原检查规则。

统一763项报告helper的父端十项测试通过(17.871秒)。实际worker
已观察到PID4163712执行`report_native_batch763.py run`，输出目录
`native-batch-full763-agent-20261007-01`；配置SHA为
`54a49eefe913cadfe588cdf4f5f2e7cd1927af802e8b49f4fc646e3d74ebd084`。
这是启动时的进程证据，不代替最终DVE结果和完整verify。

QBS偶数起点候选已完成精确原生资格，不再只是静态候选。
最终静态报告`qbs-even-start-hit-static762-agent-20261007-02.json`
SHA为`e00a593df5e8fc302484209d22965d9cfc9a133a472966beb2a63a481120164d`，
父端核对45项pins无漂移；读engine、context replay、ingress、
pending及hit mask的源链保持冻结，2547456次读回递推检查通过。
原生资格`qbs-even-hit19328-native762-agent-20261007-01/capture-result.json`
SHA为`bf06c26430b00c7201916f564531c6860ee431bee1c0cf5dc151384a323760c7`，
父端核对99项pins无漂移，七项原生正负向测试通过。仅涉及1215
个hit向量中的9664个bit/19328个方向，与旧1792及scale120去重；
16928个同向量非目标bit及全部其他字段继续保护，保存、重载、
清除通过。M8 activation quant存在与目的byte奇偶不同的合法
writer，因此没有统一豁免activation奇偶性，没有排除初始X。
剩余16983个缺失方向仍待证明或激励。新资格待集中应用到763项
统一报告，不得直接把这些方向数换算为官方覆盖率百分比。

mask/gather后继已完成独立defined-policy资格并准入，正式集合
增至763项，但下方最新DVE统一百分比仍来自762项。新目录为
`operand-mask-data-defined-policy-admitted763-agent-20261007-01`；
资格SHA为`c4b7c7663272556595b484753b72270a4aff1fc7edd19299b1e2952841c50a86`，
准入SHA为`962d7292ff80e5fffe4fd8e8e8de00938c32dca3a92d21e179b8cf59f915200c`。
父端核对5234项资格pins无漂移，八项实际轨迹/负向测试通过。
763项无重复且保持原762项完整前缀。191288条退休指令、全部
GPR及内存访问对齐；27200个向量结果字节和8256个独立oracle
结果字节通过，含192个guard字节及5256项软件检查。四条mask
比较的64个未定义tail字节保留原计数，仅核验精确范围；全零
mask加法用已知前态、无有效写入和完整独立内存读回证明1024
字节目标保持，没有降低通用比较器准入标准。原HOLD目录不改。
本项新增raw条件点4个、Toggle序列化方向位置14个；不是官方
DVE百分比，也不代表大量缺口已被覆盖。

FP16算术内部及lookahead两条转换已完成实际原生检查，父端
分别核对263及77项pins无漂移。FP16资格
`half-fma816-native-agent-20261007-01/capture-result.json`的SHA为
`0cecf445115b92e5fc17eb126100a585f5d14d12f2bc2201e04d605f72259d45`，
精确16个scope/816个纯算术对象，保留3520个本地保护对象及
全部子层。lookahead资格
`lookahead-send-ready2-native-762-agent-20261007-01/capture-result.json`
的SHA为`86147b97220922bc91968f0c3f4857b12549b3124b92d32627616eb761994e13`；
仅排除冻结Beats=8配置中两条Send->Ready转换，保留其余46点。
reset可达状态归纳、单beat及非法初态反例测试通过，父端另验
九项证明测试及六项原生捕获测试。两项保存/重载/清除均通过，
尚未应用到下方762项统一百分比，等待批量报告。

标量DIV/SQRT已完成独立功能检查及精确算术内部原生资格。
功能资格`scalar-divsqrt-finite-qualified-agent-20261007-01/qualification.json`
的SHA为`a5b6ebf7704f62f9190b53582e94a87f28f8831060e183d0d23432ac9f596cfd`；
父端核对172项pins无漂移，十项测试通过。实际20条DIV/SQRT、
40项结果/flags及35项guard检查通过；963条退休指令、451次GPR、
60次FPR写入和172次内存访问对齐，没有跳过、trap或结果不一致。
该有限集合不等于完整浮点功能穷举。

原生资格`scalar-radix158-native-agent-20261007-01/capture-result.json`
的SHA为`d13b7b413162601a68099fb4f24041c07fd00db6829d60e7b29e2fcec51e819e`。
父端核对209项pins无漂移，11项测试通过；实际DVE保存、重载、
清除验证158个纯算术对象/9684个逻辑bit，保留52个本地控制与
接口对象及全部子模块。该资格尚未应用到下方762项统一报告，
不得从逻辑bit数量推算官方百分比。

关闭FPU队列后继原生资格已完成：
`queue-disabled-fp-temporaries-native-alias-agent-20261007-02/capture-result.json`，
SHA为`7ae0597fde3ba244ddd3dcbd3ae4a9768d6fb7246661ff931afeca8c58946609`。
父端核对136项pins无漂移，12项后继身份绑定及负向测试通过。
精确16个scope/336个固定字段、1536个逻辑bit；752项本地保护
对象（688项编译node/vector及64项额外数组保护）保持完整，
8个参数合并ALU scope仍HOLD。五阶段原生资格不是全量报告
应用，3072个名义方向槽不直接换算为DVE百分比。

新增QBS输入奇偶性研究在初步阶段仅作为候选：父端有限枚举九种
权重profile的816个块字节，location映射全部保持offset奇偶性，
九种块大小也均为偶数。只有进一步证明read engine所有合法
基址、首/末beat、页切分和缓存复用均产生偶数source start，
且pending保存writer身份不变，才可能排除相反奇偶的hit位。
activation的row-major/M4/M8布局须分别求并集，不可套用权重
结论。上述完整链路现已由本节开头的后继证据及原生资格闭环；
保持全部可达hit/BE/valid保护，尚未产生新的统一百分比。

FP16 FMA已通过后继离线功能资格：
`half-fma-source-tail-qualified-agent-20261007-01/qualification.json`，
SHA为`c80479bddc7569c3e6d36afc958121a52e50476b8f2bfdb5c79bbfc78821c568`。
父端核对127项pins无漂移，tail-source八项及fixed-routing六项
测试通过。实际40429条标量退休、18814个向量结果字节、16384
字节完整VRF快照和20项CSR检查通过；16个FP16物理核共224次
接收/完成，结果、flags及mask逐项核对，包括mask=0的计算。
VL31最后一个物理元素的B/C输入按冻结队列规则补零，A不补零；
该项通过来自精确源映射及独立参考，不是忽略inactive结果。
原始失败目录保持不变，没有重跑VCS。该资格尚未准入测试集合
或应用新的算术内部排除；下一步仅允许精确816个纯算术对象
进入原生资格，控制、舍入、flags、接口及修改逻辑继续保护。

最新完成并经父端独立执行完整verify的统一报告为762项，目录
`native-population-dispatcher-four-full762-agent-20261007-01`。
资格SHA为`24f8c0b83627fe9cbc772481bbd49c2dcdc6b834ef8136028b0aa885df3ef7ae`。
保存/重载一致，清除后的原始指标恢复；本次新增四条Dispatcher
转换已包含。相较761项报告FSM从79.08%提高到79.55%，Toggle
仍64.96%。两个80%目标尚未完成。

| 最新762项系统指标 | 全设计原始值 | 合理排除及重载后 |
| --- | ---: | ---: |
| Line | 85.21% | 85.18% |
| Condition | 82.05% | 82.06% |
| Branch | 82.95% | 82.99% |
| FSM | 69.97% | 79.55% |
| Toggle | 63.61% | 64.96% |

标量FMA扩展资格已实际完成22个精确对象/1566个逻辑bit，资格
`scalar-fma22-native-agent-20261007-01/capture-result.json`的SHA为
`976fded90d31b5f71552c9027fda44fb4af68cf89bea060eceba42f98dce0d5f`。
父端核对256项输入/输出pins无漂移，11项正反向测试通过。每个
实例40个控制/边界对象及完整补集继续保护；尚未应用到上述762
报告，不能把1566bit直接换算为官方百分比收益。

mask/gather运行01终态为1800秒TIMEOUT，不准入。根因不是从
超时猜测得出：提交轨迹明确显示cycle247776、order191287向
`tohost=0x80001000`写入1，之后反复退休`finish`自环；原启动
命令遗漏`+COMMIT_TOHOST`，无法触发提交监控器结束。原VDB仅
包含`.mode64`，没有完整测试数据，因此不能从该目录收集覆盖。
保留原始目录，离线架构核验也不能将不完整VDB变成已准入数据。

后继`run_operand_mask_data_v2.py`只添加该结束监控参数，复用
相同ELF及冻结RTL，不扩大1800秒预算。三项命令、私有命名空间
及错误终止地址测试通过；新prepared SHA为
`0744b28320a35105a5f22a250b97692534c999a74560b5c531ab0c2f5a5572d5`。
后台unit为`ara-operand-mask-data-20261007-02.service`，启动时实际
simv PID4113279，父端核对/proc/exe及提交文件增长。该运行现已
正常结束，但原自动严格比较门控保持HOLD，尚未合入正式集合。
父端另行检查36个向量请求、27200个已定义结果字节，没有首个
结果不一致；四条mask比较指令共有64个未定义tail字节，另有
一条全零mask的加法没有活动VRF写入。后继资格必须精确证明
这四个tail范围及全零mask目标保持，通过独立内存oracle检查，
不能降低通用比较门控或把无写入等同于通过。

C910 radix16 child复核确认已有两组原生范围共覆盖16个向量
实例，每实例158个纯算术字段；761项配置中的c910八组及fp16
八组已包含这些范围。本次新候选为零，不重复排除或计算收益。
全部接口、reset/clock、算法选择、符号、轮次、边界比较及选商
控制继续保护。证据为
`srt-radix16-child-residual-source-review762-agent-20261007-01.json`，
SHA为`c2f4064a1566fc8cb8889038a3feb1d95c32a37501379605ceb5afd574c35095`。

762项正式集合已完成新的FSM缺口排序，证据为
`admitted762-fsm-priority-parent-20261007-01.json`，SHA为
`67c936292c506e29d3e13b244b39dd9bab284ac2988f4c1f918b8d4335548d90`。
输入/输出pins已核验，四项身份、重复成员及shape反向测试通过。
该诊断保留既有761项报告的155个精确排除身份；新Dispatcher四条
转换在统一报告核验前仍显示，不提前宣称已经应用。主要剩余
转换数量为Dispatcher17、缓存port1十二条、store/load lookahead
十一条、AXI upsizer十条及load unit十条。数量是序列化坐标诊断，
不是新的DVE百分比或不可达证明。

队列临时字段原生检查01已终止且未应用，原因是保护补集中的
一位`operand_queue_cmd_i.target_fu[0:0]`与GUI标量显示名无法精确
绑定；DVE进程退出码0不能代替五阶段资格通过。保留失败目录，
后继须修正完整typed身份绑定并保留该保护字段，而不是删除
保护检查或对整个队列作排除。

762项加Dispatcher四条转换的统一DVE报告已完成独立核验；
mask/gather运行02已正常结束，仍在上述离线资格检查阶段。
新增标量、FP16、队列及QBS精确范围将集中汇总，避免每增加
一项就重复生成全设计报告。各项原生资格不代表统一报告已经
应用；最终以正确性准入、保存/重载/清除审计及统一报告为准。

标量FMA精确8对象已完成原生资格，目录为
`scalar-fma8-native-agent-20261007-01`，资格SHA为
`ef5db2372ad86e6b3d5a3887fda51f7df51895e1b7941d50e187dcc5de74043b`。
父端独立核对224项pins均无漂移；871个逻辑bit不是官方覆盖率
分母，该资格尚未应用到人口集合。后续扩展仅考虑mantissa及sum
纯数值字段，不包含sum_raw中的carry、控制、舍入或flags。

QBS payload新增bank0 scale-hit120位的源证明，证据为
`qbs-bank0-scale-hit120-proof762-agent-20261007-01.json`，SHA为
`2e9c4d179835967bfdf4e2de78aad879add5d3917906de6047799d5bb1bf73ac`。
所有合法activation profile/layout的scale源索引满足
`index <= 4*row+byte`，writer要求`start+writer=index`且`start>=0`，
因此超出该界的writer不能命中。bank1的M8 context4存在反例，
不能延伸排除。父端五项边界测试通过；120位/240方向仍须严格
逐bit原生资格，不能整体排除hit向量、BE、valid或真实命中控制。

关闭FPU的队列浮点转换临时字段已完成静态候选审查：冻结源
默认将fp8/fp16/fp32清零，唯一非零全局写入受FPUSupport门控。
目录证据`queue-disabled-fp-temporaries-static-parent-20261007-01.json`，
SHA为`684da514eab370b59d98764c86ac6a6fb4466808f9c6aff47aa199eee19cf2ee`。
24个源实例各21个完整本地字段；其中16个编译定义全部为FPU0，
可进入336个字段的原生资格流程。其余8个ALU实例的coverage
shape合并了FPU0/56参数变体，在实例参数绑定进一步确认前HOLD。
这不是关闭浮点功能，也不是排除队列实例；所有接口、控制、实际
数据和非目标字段继续保护。五项源码正负向测试通过，未应用EL，
不能把4608个名义方向槽当作DVE实际分母或百分比收益。

标量FP32/FP64有限算术资格已完成一次实际VCS及独立参考闭环：
20条ADD/MUL/FMA，40项结果/flags检查和35项guard检查，包含
FP32 NaN boxing及CSR恢复。父端核对179项输入/输出pins无漂移，
10项参考正负向测试通过；998条标量指令、466次GPR写入、80次
FPR写入及180次标量内存访问精确对齐。资格目录为
`scalar-fpu-finite-qualified-agent-20261007-01`，SHA为
`df01c882f68fe9035a4563421c76d19cfe17cd7e07f7037967c6f101472f5569`。
仅支持保守的标量FMA纯算术内部范围进入原生资格检查，不宣称
完整IEEE穷举或UVM最终报告闭环，不自动豁免接口/舍入/flags/
pipeline或修改逻辑。该测试尚未准入人口集合。

761项报告03的封存差异现已定位并完成父端独立核对：473个实质
输出文件全部无漂移，唯一差异为service.log在资格文件写入后追加
802字节结果JSON。原41字节前缀哈希与封存值一致，追加JSON的
status、qualification SHA和system五阶段值与封存文件精确相同；
不允许任意日志变化。之前完整实质核验已执行到最后封存结果比较，
后继只读复核也保留全部输入、原生目标/保护、模块及五阶段检查。
资格文件SHA为
`4cd4ea9aee8d032fd496f93f2662a66c882a818a9af5ccdc5c9ab8f1fd384346`。

| 历史761项系统指标 | 全设计原始值 | 合理排除及重载后 |
| --- | ---: | ---: |
| Line | 85.21% | 85.18% |
| Condition | 82.05% | 82.06% |
| Branch | 82.95% | 82.99% |
| FSM | 69.81% | 79.08% |
| Toggle | 63.61% | 64.96% |

这份报告不包含第762项及新Dispatcher四条转换。尚未达到两个
80%目标，不能用旧745更高的Toggle数替代同一配置的最新结果。

新增`vgap_operand_mask_data.c`针对MaskM谓词数据及MaskB比较/
gather路径：四种互补mask，e8/m8满VL1024，以及e64/m8满VL128
的全位变化数据、正常和全位为1的越界索引。软件检查5256项，
独立整数参考逐条验证12条目标指令的8256字节完整结果，Spike
195000条指令通过，未启动VCS、未准入覆盖率。原生覆盖增益仍需
实测；为节省仿真时间，不把Spike通过当作RTL通过或直接计入。
该激励随后已启动一次独立后台VCS：unit为
`ara-operand-mask-data-20261007-01.service`，launcher4080172、
实际simv4080237，父端从/proc核实可执行文件为冻结镜像。
目录`operand-mask-data-old-image-parent-20261007-01`，上限1800秒；
完成后自动执行严格标量/向量差分，失败或核验未完成均HOLD。
参考检查器六项正负向测试通过；不持续轮询，不改RTL，不在
仿真尚未完成时宣称获得Toggle增益或已准入。

Dispatcher精确四条转换已完成原生资格核验，目录为
`dispatcher-four-native762-agent-20261007-01`，资格文件SHA为
`a069195b8977e94f63d775083ef605b5424322185663f7f6963bd43ff8507c85`。
父端独立核对81项输入/输出pins无漂移，12项正反向测试通过；
另行只读解析first/second EL，核对四条记录一致、四个清除EL为空，
并运行92个坐标的五阶段目标/保护审计通过。仅四条直接转换可
加入后继统一报告，88个非目标点保持保护；此资格不代表已应用
到762项全量报告，也不产生新的系统百分比。

761项统一报告03已生成五阶段数据及资格文件，但父端重新执行完整
实质核验器时，在最后的封存结果一致性检查处报出
`Sealed result differs`。此前的目标、保护补集、清除/重载及模块
报告检查未报错；仍须逐字段查明重新计算记录与封存记录的差异，
不能仅凭代理端资格文件将该报告提升为父端核验完成。已交由报告
负责人进行只读差异定位，不改封存文件，也不重跑DVE。

FP16 finite FMA实际VCS测试退出码0，软件报告SUCCESS，但波形
检查器仍处于`HOLD_NOT_ADMITTED`。冻结VMFPU对vfmacc的物理
输入顺序为(vs2,vs1,vd)，并非软件书写顺序；EW16的物理元素
排列也不是线性SIMD序号。后继检查器必须从冻结shuffle映射
推导准确坐标，逐项验证输入、舍入、mask、结果及flags，复用已有
波形，不把检查器失败提前解释为RTL错误或功能通过。

缓存port1审查证明剩余多个replay/kill状态在正常配置下可达，不能
以“可靠模块”整体排除。下一激励针对其他端口refill恰好与标量
load tag检查重叠的合法场景；只有确认实际重叠、正确读数及事务
完成后才准入。单元级测试若不来自同一SoC覆盖镜像，不合入系统VDB。

## 历史统一报告与可靠功能单元排除边界

最新正式集合和父端核验完成的统一DVE报告均为762项；
最新统一百分比见本文首部762表。下文保留准备及历史报告的
证据链，历史运行中状态不表示任务目前仍在运行。
761统一报告的首次准备尚未启动EDA：真实Tcl宿主预检发现含lane
方括号的数组名没有按list引用，失败记录保存在
`native-population-union-full761-agent-20261007-01/prepare-failure.json`。
父端独立执行`test_report_native_population_union`共15项测试，14项
通过，实际selection/entry五阶段测试在严格模块Scope/Name对齐处
失败；后继需要修正真实GUI模型与参考模块名称绑定，不能删除
模块一致性校验。此失败不改变已准入测试或原始覆盖数据，也不
产生新的覆盖率百分比。
后继02的宿主五阶段和父端全部15项测试已通过，父端独立核对
7958项封存pins通过；但启动前实际层级审查发现新增八个cast
根节点仍使用推断leaf名称，未绑定DVE真实flattened generate
标签。因此02继续不启动EDA，保留`runtime-rejection.json`。
这说明宿主GUI模型通过不等于真实DVE层级合格；后继必须从
已封存745原生层级报告读取名称并保留严格Scope/Name比较。
后继03已完成上述标签绑定，父端四项v2测试通过，并确认实际
DVE进程4037718（可执行文件`dve.exe`，启动进程4037622）正在运行。
目录为`native-population-union-full761-agent-20261007-03`，配置SHA为
`cd752e949804ba5cdb82e96ddca8e4b21dc1b5004fc90774938784841086e9aa`。
采用761项已准入VDB、FMA612替换108子集、cast168及child15；
保留原有合格范围和非目标保护，不重新运行761项仿真。启动和
宿主测试不代表DVE报告已合格，系统百分比仍待实际五阶段结果。
03任务已生成raw/applied阶段：raw FSM69.81%、Toggle63.61%，
applied FSM79.08%、Toggle64.96%。这些是尚未完成重载/清除/最终
核验的阶段数据，不替代下面的正式745表。新增FMA/cast范围没有
使系统Toggle接近80%，且不得为美化数字选择性撤回已核实范围。
后续重点转向CVA6、QBS累加及operand mask/MFPU等真实Toggle
缺口的激励和配置可达性审计；QBS新建算术逻辑不能仅因“功能
单元较可靠”整体豁免。FSM剩余重点为Dispatcher/cache replay控制。
Dispatcher17剩余转换已完成冻结源码审查，文件为
`dispatcher17-static-reachability-762-agent-20261007-01.json`，SHA为
`f2ea39ba3f4563f02d65844b1cf3afa74400d7e581c1ea593589494db1be5166`。
父端核对12项pins及17个编译身份，并复核准备阶段、寄存请求
握手、held FIFO所有者及EEW/snapshot写入路径。仅raw31/32/34/37
四条转换获准进入原生精确资格验证：ISSUE必有prepared，入口
注册请求无valid，前置阶段保持源布局/所有者。其余13条转换
继续保护；不排除任何整个状态或Dispatcher实例。静态证明不
等于EL已经应用，需原生保存/重载/清除和完整保护补集核验。
提议的FOF后继矩阵尚未启动，已知GAP112功能缺口未闭环，不
为了FSM百分比重复发起预计可能失败的长测。
标量load的非幂等commit门控/Sv39冷TLB定向测试已完成一次实际VCS运行：
`load-ni-tlb-old-image-760-agent-20261007-01`退出码0，CPU时间77.610秒，
软件报告SUCCESS。当前终态仍是
`TERMINAL_CAPTURE_PENDING_ARCHITECTURE_AXI_AND_FSM_QUALIFICATION`，
未计入761项；需独立核对Spike架构结果、CTRL只读复位契约、访存
协议及目标状态转换。退出码、SUCCESS和零向量请求的ARA_CONTRACT
均不能单独代替该标量访存测试的正确性核验。日志中的未触发断言
和仿真结束时未完成的断言也不宣称为断言覆盖闭环。
该测试随后已完成独立核验：11940条标量指令、3710次标量写入及
3595次标量内存访问与Spike精确对齐，未跳过不可观测值；CTRL
仅一次只读访问，复位值由冻结RTL单独核实，不声称Spike模拟该设备。
实际前沿AXI核验68个AR、155个R、3602个AW/W/B，稳定性、ID、
响应、LAST和最终排空通过。14项软件检查及CSR/内存参考通过。
VDB和逐周期波形共同确认raw22/29两个非幂等load转换命中；
raw21/28两个TLB转换仍未命中，保留为缺口。新增原始line4、
branch2、FSM2，不把它们当作百分比。资格为
`load-ni-tlb-qualified-760-agent-20261007-01/qualification.json`，SHA为
`1d20a55f1c49816ba775180175f69ff4659385bada7d68a2c6cdf01bd0f13314`。
父端独立10项正负向测试通过，284项输入及8项输出pins无漂移；
现已接续761项准入762：
`load-ni-tlb-offline-admitted-762-agent-20261007-01/admission-manifest.json`，
SHA为`6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5`。
父端独立核对5202项输入和5项输出pins无漂移，762项唯一，完整
保留761前缀及同一compiled design。当前DVE任务仍固定761项；
不在运行中替换输入，不将新准入数量冒充已完成的统计百分比。
此前745项统一报告为`qualified-native-combo-diagnostic-full745-agent-20261007-01`，
资格SHA256为`69cdeba221f23874be91c266b5236b5b48c49c4836e8064fc29b4298e5b6231f`。
父级6206项输入和417项输出pins无漂移，原始/清除/最终一致，
应用/重载一致；224个完整诊断字段增加Toggle 0.13个百分点，
未改变FSM百分比。没有关闭运行时检查，非目标节点持续保护。
下面关于初始745报告离线核验器修复的说明作为其前置资格保留。
745项五阶段数据已完成；原失败来自离线核验器误继承742入口
绑定包装，而非DVE采集失败。`verify_native_combo745_offline.py`
在私有命名空间中使用原实质核验器，保留745入口/schema/
population及全部原生目标、保护补集和清除/重载检查。3项适配
测试通过，未改冻结配置、原脚本或失败记录，未重跑DVE。资格
文件为`qualified-native-combo-full745-agent-20261007-01/qualification.json`，
SHA256为`9f7260352368b2ba522a0a81943f133af3b9bdd1ee015ea9a5c2530b083f11a5`。

| 历史745项系统指标 | 全设计原始值 | 合理排除及重载后 |
| --- | ---: | ---: |
| Line | 85.21% | 85.18% |
| Condition | 82.03% | 82.04% |
| Branch | 82.95% | 82.99% |
| FSM | 60.94% | 69.03% |
| Toggle | 63.55% | 65.20% |

相对742项正式报告，排除后FSM增加0.45个百分点，Toggle增加
1.00个百分点。仍未达到80%；该表已包含224个诊断字段范围，
不包含第746项以后新增测试。原始值/清除后/最终值一致，应用
及重载值一致。

FP16计算中复位代表例已完成独立架构及五通道AXI闭环，正式
加入第746项：679软件检查、完整4096字节VRF快照、五CSR、
两执行epoch，恢复后的13363条标量指令与Spike一致，37条
向量指令及9216字节回写核验。16个C910实例实际新增16个FSM
位置及3个条件点，事务最终排空。父级15项资格pins与4062项
准入pins均无漂移，4项准入测试通过。准入文件为
`external-reset-fpu-half-offline-admitted-746-agent-20261007-01/admission-manifest.json`，
SHA256为`edcc5b1614dd65c51c8e9c69f1ce60bb9196101eea89330c59fde05238a96ddb`。
其UVM最终check/report缺失边界仍明确；依据独立架构、AXI及
事件核验准入，不声称UVM最终报告通过。

QBS affine AUX阶段复位/恢复已接续746项准入第747项。资格核对
两epoch、目标阶段复位及slot0重新分配，恢复后8192字节完整VRF、
7840字节源/guard、24个CSR值与独立原生参考一致；41项软件检查
及独立事件/事务检查通过。新增1个FSM转换、5个条件点，不声称
完整标量ISA差分、Spike自定义ISA通过或UVM最终check/report通过。
父级4361项输入及6项输出pins无漂移，747项唯一且保留精确746前缀。
准入文件为`qbs-affine-aux-offline-admitted-747-agent-20261007-01/admission-manifest.json`，
SHA256为`1c2de4bb109f450cb3365b7fe5b935d018af0340070c81743beb6c2dfafe3046`。
SCALE/MIN_SCALE随后已完成资格核验，并接续FPU批次后的758项，
依次形成759、760项。最新760准入为
`qbs-affine-min-scale-offline-admitted-760-agent-20261007-01/admission-manifest.json`，
SHA256为`0b4ae9ddf332355cdbb02ff42f237487dd0857fa5872b86916bc5ac40b3b207e`。
父级5031项输入和5项输出pins无漂移，760项唯一并保留758项前缀。
SCALE和MIN_SCALE各测试相对746新增16个原始FSM位置，但在合并
后按去重并集计数，不能把阶段名当成16个entry都在该阶段复位。

其余11个FP16/FP32/FP64计算阶段复位测试均已退出0。父级用官方
转换器复用原有VPD，四路离线转换后逐项核验真实目标状态、有效位、
下降沿断言/释放和四完整周期复位，全部通过。窗口结果为
`fpu-matrix-window-audit-parent-20261007-01/result.json`。该结果不
代替完整架构/事务核验。其后完整架构和事务核验均通过，11项已
接续747形成758：`fpu-reset-matrix-offline-admitted-758-agent-20261007-01/admission-manifest.json`，
SHA256为`4ae911058627d23527a2b3cbe553de7e14674e95df74ca05c0c64faaf1491507`。
父级4852项输入和4项输出pins无漂移，758项唯一并保留精确747前缀。
该批合并后新增48个FSM和17个条件位置，未重跑VCS。正式760
相比745总共新增97个FSM和25个条件原始位置；百分比仍待DVE。

另补充QBS子层纯统计字段的连接链审查：FP accumulator五完整
统计输出、compute五直通端口和engine五别名，共15对象、399位、
798方向。逐条核对所有源码引用并检查冻结编译形状，连接链终止于
已审查的VLSU打印字段；新增功能读取、错误生产者等负例被拒绝，
4项测试通过。候选为`qbs-child-statistics-source-candidate-parent-20261007-01.json`，
原生DVE资格已完成：
`qbs-child-statistics-native-agent-20261007-01/capture-result.json`，
SHA256为`3fa51ba861639a7fb18f0d8a742257200b08d2e1897969a2a4f4186c7697cde4`。
父级再次执行封存核验器，结果及SHA一致；15对象的798方向均显式
绑定，全部非目标对象保持保护，保存/重载语义一致，最终全局排除
清空。该资格采集使用代表性744集合，不等于最新760统一报告；
尚未应用到统一百分比，798不是官方分母或百分比增益。

746项原始FSM缺口及745项已核验排除身份的诊断排序已生成于
`admitted746-fsm-priority-parent-20261007-02.json`，只指导激励优先级。
排序器3项测试通过，保留状态与转换的区别，不输出覆盖百分比。
首次诊断文件01错误地把DWC另一种原生记录schema按旧schema解释，
文件02通过规范化修正并确认31个DWC排除点全部匹配；01未用于
任何排除、准入或百分比统计，保留供审计。当前优先对象仍为QBS
累加器取消/复用、Dispatcher、标量load及cache replay/kill交互，
不得为追求目标排除这些可达控制路径。

最新760项诊断排序已更新于`formal760-fsm-priority-parent-20261007-01.json`。
760项准入输入和输出pins通过核对，原生155项FSM排除身份经规范化
保留不变，未应用新排除或输出百分比。剩余未排除转换按实际bitmap
排序为Dispatcher17、QBS累加器15、dcache读端口1为12、scalar load为12、
store/load lookahead11、AXI upsizer10、dcache读端口0为9。
这些是诊断转换数，不是系统覆盖率分母；后继激励应依据此排序，
避免继续针对746项报告中已被新增测试覆盖的转换重复仿真。
最新排序器追加3项回归：760精确人口及不生成分数、新增重复测试
拒绝、冻结shape漂移拒绝，均通过；复用的6项位图/身份测试亦通过。

Dispatcher17项不应直接等同于17种可达软件场景。冻结源码的
`arch_decode`只允许NORMAL、OVERLAP_ISSUE_ORIGINAL及满足退出条件
的WAIT_IDLE/WAIT_IDLE_FLUSH进入解码；OVERLAP_ISSUE_ORIGINAL重放
的仍是被CVXIF保持的同一请求。后续须检查保持请求、
`overlap_prepared_q`、snapshot和EEW更新的跨周期不变量，再区分
实际可达重放/异常转换和编译器保守提取的组合候选。仅阅读局部
case或观察未命中不能证明不可达，本轮不新增该类豁免。

标量Load后继代表方案已核对760位图和冻结源码：一个ELF两phase，
先用较老长延迟DIV阻塞commit，再连续warm DRAM/CTRL load触发
NI提交约束；另用Sv39下warm页到DTLB-cold页触发translation miss。
目标为SEND_TAG/WAIT_GNT到ABORT_TRANSACTION_NI，以及对应
ABORT_TRANSACTION转换，预计2至4个新转换但不保证。实际须只读
观察state、grant、DTLB hit、stall_ni和commit ID，并以Spike核验
DIV、DRAM、CSR及恢复结果；CTRL值单独依据冻结reset/no-write
契约，不能冒充Spike MMIO差分。一次600秒有界独立测试，不改RTL，
不混入历史cache碰撞或ECALL时序。只有结果和事务检查通过后准入，
正式增量对760或其合法后继计算，零命中不得描述为覆盖率提升。

Cast168第三次原生采集退出0但未取得资格：真实first.el含
`logic [0:1][63:0]mid_pipe_input_mant_q`类型声明，离线EL解析器
拒绝此多维语法，中止后已清除排除。证据目录为
`fpnew-cast-fp-shared168-native745-agent-20261007-03`。
后继先用全部真实EL及八scope原生对象做离线语法、位宽、身份和
保护补集回归，再在新目录执行完整保存/重载；不得将退出0视为
五阶段资格通过，亦不得因解析失败放宽目标范围。

Cast168第四次已完成五阶段原生资格：
`fpnew-cast-fp-shared168-native745-agent-20261007-04/capture-result.json`，
SHA256为`acf46cc867704929ba718e0cf7efd9ffe936de463081f84667f0b4cfa87fe41a`。
168完整对象、9576位，2064个本地非目标对象及全部子模块保持保护；
完整对象双方向、原生保存/重载一致，最终全局EL为空。父级执行
9项typed数组及保护负例回归通过，并用
`verify_cast168_native_offline.py`重放原实质核验器：全部pins核对、
唯一输出与封存result逐项相等、原文件SHA不变。直接再次inspect
会因原脚本排他写入已有文件失败，不能据此覆盖资格文件；只读
适配不删除检查、不重跑DVE。精确范围可用于后继统一报告，但
本次资格不是最新人口百分比，也不声称完整IEEE认证。
只读复核器另有2项回归通过：实质重放不改变资格文件内容及mtime，
错误seal在写入前被拒绝。该工具不生成新的native资格或覆盖率分数。

后续FP16 FMA数值范围候选仍HOLD。父级核对冻结vmfpu SHA
`1f8288ed2a50f8fa59a7ea3d6f3a7e3138f5219bbb1af52e864d9dfe359d8307`：
ADDMUL使用fpnew PARALLEL slices，THMULTI/C910只选择DIVSQRT，
FpFmtMask启用FP16。此前C910半精度FDIV/FSQRT复位检查不能作为
FP16 FMA内部数值字段的功能资格。须另外绑定实际FP16 FMA请求、
对应slice及独立结果/fflags证据，不能仅依据SEW16名称或源码与
上游一致就排除其内部数值对象。

为减少后续实验次数，父级复用三份已核验QBS VCD观察全部16个
entry的阶段/有效位，未新跑仿真。3项单元测试覆盖全slot统计、
未知有效状态拒绝及无效entry不计为覆盖。恢复路径的AUX、SCALE、
MIN_SCALE各存在16个entry同时有效且同阶段的窗口，证据为
`qbs-slot-phase-opportunities-parent-20261007-01.json`。在下降沿首次
观察slot15进入MIN_SCALE时，16个entry均已有效且在MIN_SCALE，
可用一项合法外部复位代表例补充批量取消/重分配转换。

必须按最新760编译形状确定真实缺口：只有entry1至15的
`FP_MIN_SCALE_MULTIPLY->FP_DOT_CONVERT`未命中，AUX与SCALE
对应转换已经全命中；源码、shape与已准入bitmap证据为
`qbs-remaining15-fsm-native-shape-parent-20261007-01.json`，
SHA256为`7f557026a3cff8c4989c3de677f4a0a13de1c133ebaeadbe34c8514241c0b61c`。
此前口头AUX-slot15预测已撤销，后继限定MIN_SCALE-slot15，
仍须实测全entry复位前状态、有效位、恢复结果和新的FSM命中，
不能把现有窗口分析当成已执行的新测试或新覆盖增量。

MIN_SCALE-slot15代表例已仿真退出0，CPU253.380秒，完整资格为
`qbs-affine-min-slot15-qualified-760-agent-20261007-01/qualification.json`，
SHA256为`46ac9d3363d12681196f4375440442fcabea79626315a86da3be854ea61b679b`。
父级479项输入及21项输出pins无漂移；实际复位前16entry全部有效且
处于MIN_SCALE，四周期复位后清valid、保留阶段，随后16slot均重新
分配为DOT。两epoch恢复8192字节VRF、初始seed、7840字节源/guard、
24CSR及41软件检查通过，正式760原始位图实测增加15个FSM转换。
原资格状态明确为NOT_ADMITTED，其后已单线准入761，文件为
`qbs-affine-min-slot15-offline-admitted-761-agent-20261007-01/admission-manifest.json`，
SHA256为`fb32312b28f37c0a674fbefa521f75dd041e78bf6cfe6f83f0d7dc8f8b61f9f7`。
父级5098项输入和6项输出pins无漂移，761项唯一并保留精确760
前缀，15项转换与冻结原生shape逐项一致。不把761准入当成新的
DVE百分比，不声称Spike自定义ISA、完整标量ISA或UVM最终
check/report通过。

已有FMA数值内部扩展范围的源码证据亦重新核对：165项pins匹配，
5项字段分类/保护边界测试通过。612个完整数值对象包含原108个
已核验对象；相关文件与上游逐字节一致，rounding、flags、接口、
控制、子模块及修改区均保护。扩展原生保存/重载资格正在独立
准备，未提前用于统一报告，也不声称完整IEEE认证。

612对象首次DVE资格采集在应用之前因Tcl过程作用域缺失全局变量
绑定而终止；不是RTL计算错误。已捕获全部612目标及2832非目标，
初始和清理EL为空，但应用/重载/清除闭环未完成，不能用于正式排除。
失败记录为`fma_expanded_native_612-agent-20261007-01/qualification-reject.json`，
SHA256为`29f659cf59bc5b0a2ccd8ca9d492a0705105011075165a0905edf0a8ec5899ad`。
后继须在独立脚本和目录中先完成普通Tcl作用域回归，再执行同一
精确范围的原生五阶段资格；保留首次失败证据，不放宽保护补集。

FMA612第二次采集同样未取得资格，但与首次不同：实际生成的
`selection.tcl`被JSON保存函数序列化，外层带双引号，换行成为
字面`\n`，配置命令没有被正常执行。第二次脚本已包含
`fma_design`等global绑定，不能把这次失败再归因于缺失同一绑定。
父级核对真实生成文件及两代prepare源码，首次生成使用文本保存，
第二代使用JSON保存，后继须使用真实Tcl文本输出；启动DVE前
必须实际source生成文件并核对全部配置变量，不能只测试模板。
第二次目录`fma_expanded_native_612-agent-20261007-02`保留不动，
范围和保护规则均不放宽，两次失败均未计入覆盖率。

FMA612第三次已正确执行Tcl并保存first.el，但应用阶段的离线
解析器拒绝原生标量成对方向语法，例如tentative_sign被保存为
0to1和1to0两条。父级直接重放stage apply复现拒绝原因。后继
必须基于全部真实612对象EL校验：一个完整whole条目，或同对象、
同checksum及完整类型签名下恰好两个方向；缺一、重复、whole与
单方向混合均拒绝。不能把成对方向语法改为只排除未命中方向。
第三次目录`fma_expanded_native_612-agent-20261007-03`保留，未资格、
未进入统一报告；完成实际EL全部语法回归后才运行独立后继。

FMA第四次已取得完整资格：
`fma_expanded_native_612-agent-20261007-04/capture-result.json`，
SHA256为`b07201c920d2a952f08d263758cd54c4d5093e5eeac81a419d4512f2e8f7b492`。
612完整数值字段、26064逻辑位，2832非目标对象及全部子模块
保持保护；原生五阶段稳定、保存/重载语义一致、清除EL为空。
父级独立8项真实EL方向/完整数组/结构字段/源码签名回归通过，
`verify_fma612_native_offline.py`只读重放原实质verify也通过：全部
pins核对，唯一输出与原封存result完整相等。只读重放保留已封存
的stdout快照，不复制持续变化的未封存worker stdout；2项回归
确认资格及快照内容/mtime不变，错误seal拒绝。
该范围可在后继761项统一报告中取代原108字段的子集，不能将
108再重复相加；并入已资格的Cast168及QBS子层15统计对象。
本节资格不等于新系统百分比，不声称完整IEEE功能认证。

上一正式集合已准入745项。GAP115复位取消/恢复完成679项
软件检查、完整VRF核验及独立AXI事务守恒；复用实际focused波形，
未因自动标记误判重新仿真。相对744项新增4个FSM位置。准入文件：
`verification/out/gap115-offline-admitted-745-agent-20261007-01/admission-manifest.json`，
SHA256为`965ec298fcd169b9a184367893ddfad7b080c75ac71e85fad72fe4977cf7b5b6`。
独立审计中164项证据pins与6项输出pins均匹配，5项审计与5项
准入单元测试通过。UVM最终check/report未执行这一边界保持明确，
依据是独立事务与架构核验，不伪造UVM汇总。

操作数队列精确常量位的DVE资格已完成：108个对象、156位的
312个方向，保存/重载/reset还原通过，298项pins无差异。
`verification/out/queue-constant-native-744-agent-20261007-03/capture-result.json`
SHA256为`15dcd0fc0a923f0ea8d49ef0a6edd3c89d711cee7ff546edf1ede125347daa87`。
没有排除initial-X、usage_d组合瞬态或其他非目标点。此范围已
应用并核验于上面的745项统一报告。

为缩短总耗时，后续并行执行745项统一DVE报告与代表性RTL
定向取消测试；报告一次汇入已核验的队列与FP16范围，并导出
关键模块层级。不为每两个新增方向单独生成全量报告。取消测试
可通过官方UCLI条件断点观察合法目标阶段，仅驱动测试平台
`ara_tb.rst_n`外部复位引脚，不强制内部DUT状态或数据；保持四个
完整时钟后恢复，并独立核验实际目标阶段、事务取消和恢复结果。
这类测试不得被描述为正常计算性能样本。

共享定向复位入口已实现：`external_reset_driver.tcl`，配套
`run_external_reset_fixture.py`。脚本及runner共12项host测试通过。
配置绑定只读计算状态、有效位及聚焦波形对象；UCLI在实际下降沿
状态条件满足时停止，再读回状态和有效位。唯一可写对象为
`ara_tb.rst_n`，用deposit拉低，经过四个完整下降沿后释放。
配置缺失、路径注入、无效阶段值、dump失败或目标未到达均拒绝
执行/准入。Host测试只证明脚本约束，不证明RTL恢复正确或覆盖增加；
实际波形、恢复后的完整架构状态与事务检查通过后才可准入。

FP16代表测试已退出0，实际VCS CPU时间100.710秒。父级独立
VCD核查绑定真实层级，确认stage=6、guard=1；在100fs时间单位下
86240000时断言复位，86280000时释放，中间四个完整时钟。
通用只读核查工具为`audit_external_reset_window.py`，7项正反测试
通过，包含错误阶段、无效guard、少/多时钟、未知复位及重复复位
拒绝。有效证据为`external-reset-fpu-half-ex2-window-parent-20261007-02.json`。
父级CSV复核确认679检查、零失败、零trap及VL/vtype/vstart/vcsr/fcsr
为512/11/0/0/33。窗口证据不单独替代完整VRF、事务及恢复审计；
后续已完成这些独立检查，以顶端列出的746项准入结果为准。

224个完整纯诊断字段已完成独立DVE资格重放：六个scope、11038个
方向，359项文件哈希无漂移，2170个非目标节点保持保护。完整
保存/重载语义一致，清除后EL为空。资格结果为
`verification/out/diagnostic-scope-native-744-agent-20261007-01/capture-result.json`，
SHA256为`53ec4fc3f71fd67864cc4b2ffb9457664216abfc9b7ad637b3fa47a0794aaad9`。
父级已批准其精确诊断范围用于后继统一报告；此操作不禁用任何
断言、错误检查或PASS门控，不排除功能数据、描述符、控制及架构
CSR，也不选择性删除未命中高位。已应用到顶端最新745项诊断
统一报告，11038仅为编译对象方向数，不据此推算官方百分比。

745项统一组合报告已完成，原执行服务为
`ara-qualified-native-combo745-20261007-01.service`；目录为
`verification/out/qualified-native-combo-full745-agent-20261007-01`。
它一次组合既有排除、FP16附加内部对象和队列常量位，并导出
关键模块层级。保存、重载和清除核验已完成，以本节顶端745项
表格作为最新正式百分比，不使用运行中或partial结果。

上一准入集合为744项，保留742项完整前缀。新增
GAP114经逐条标量、完整向量回写与8次预期S-ecall核验后准入，
实际新增1个FSM位置；LMUL=8 payload-walk经24条向量目的写、
15505字节与125541条标量退休匹配后准入，仅新增scoreboard的
2个二进制Toggle方向，操作数队列目标零增量。准入清单为
`verification/out/rvv-lmul8-payload-walk-offline-admitted-744-agent-20261007-01/admission-manifest.json`，
SHA256为`06bc169ca882a44b382bea694b2dfc4ffcdb23a353b73fb117d6b29cbc70168a`。
以下系统百分比仍属于已完成的742项DVE报告，不冒充744项结果。

742项同一冻结镜像集合的新组合报告已完成原生DVE保存、重载及
清除恢复验证：
`verification/out/qualified-native-combo-full742-agent-20261007-03/qualification.json`。
资格文件SHA256为
`1b8664a6b467b09fec2142b10f6077dfca26dbb03752265b970f820ff9dfe66a`。

| 系统级指标 | 全设计原始值 | 应用及重载排除后 |
| --- | ---: | ---: |
| Line | 85.21% | 85.18% |
| Condition | 82.03% | 82.04% |
| Branch | 82.95% | 82.99% |
| FSM | 60.54% | 68.58% |
| Toggle | 63.55% | 64.20% |

该组合包含124条既有精确FSM转换、四个纯观察实例、108个FMA
算术数据对象、1264个C910 FP32/FP64 SRT内部数据对象，以及
配置不可达的upsizer内部错误路径31个FSM点和168个Toggle方向。
实际DVE系统百分比已核验；尚未建立完整的官方覆盖点数量分母，
不得将原始序列位数当作官方分母。80%目标尚未达到。

可靠功能单元的排除是集成验证范围调整，不等于证明全部操作、
舍入模式和特殊值均已验证。仅允许源代码未修改、具有独立测试
证据且精确限定的算术内部数据路径。接口、valid/ready、复位、
舍入与异常状态、mask/tail、已修改逻辑和已知缺陷保持统计。
QBS/AKV自研机制不能仅凭“已有测试通过”整体排除。

新增C910与DWC排除后，FSM由上一统一报告的67.14%升至68.58%，
Toggle则由64.52%降至64.20%。这是完整一致范围排除的真实结果，
不能只删除未命中位来反转这一变化。后继激励应针对可达的状态
转换与队列交互；新测试通过后另行准入，不能混入本742项数字。

FP16 SIMD子槽2/3的8个C910 SRT实例也已完成1264个内部数据对象
原生资格核验，保留416个局部保护对象；父级核验320项有效文件
哈希无差异。该结果尚未应用至全集合报告，不声称百分比提高。
功能依据仅为有限RTZ除法，不表示所有开方、特殊值、舍入模式
和fflags均验证完成。结果及末行日志追加的独立证明分别为
`verification/out/c910-fp16-additional8-native742-agent-20261007-01/capture-result.json`
和同目录`postterminal-receipt.json`，receipt SHA256为
`dcc0141bb263628ed024380e53bca144ef85169a031b348fdc765dee9bc04832`。

GAP115复位恢复的AXI补充捕获已退出0，只记录clk、reset与Ara
AXI请求/响应四对象，VPD为457477字节。原capture-failure不是
DUT失败：`text.count`将UCLI脚本回显中的标记文字也计数，误判
实际setup失败。独立完整行核查为1个ready标记、4个对象标记、
0个capture-error。后继直接转换现有波形，未重跑；事务配对、
RLAST、复位取消及排空已核验，作为745项中的新增成员准入。

连续FP归约候选的译码静态审查必须使用冻结副本
`verification/out/old-image-source-evidence-20261006-01/ara_dispatcher.sv`，
SHA256为`9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43`，
与build-source-pins一致，而非已修改的workspace或不匹配的HEAD。
连续归约的早期候选现已撤销：父级直接读取744项
`combined-bits.json`，四lane的`i_vfus.i_vmfpu`均为checksum
3873291691、width37，raw25和raw27均为1。因此MFPU_WAIT到
普通/有序归约状态不能再作为新缺口，不启动重复定向序列。
先前“8条未命中”的判断不成立，不能据此预测覆盖率收益。

QBS累加器重新分配弧必须考虑取消后的槽位复用，不能只按正常
完成路径判不可达。冻结`qbs_fp_accumulator.sv`的SHA256为
`f191445db9ba3bf23c3650db2710ec5df251202e39fba14dad87adacda45f205`。
`request_ready_o`要求目标entry无效；新请求将该槽位置为
FP_DOT_CONVERT。正常AUX/SCALE/MIN_SCALE阶段会继续推进，不能
同时被新请求覆盖。但reset及clear仅清除valid/inflight等标志，
不初始化`entry_state_q`，所以取消中间阶段后重新分配，可产生
这些阶段到DOT的转换。这属于需要保留的恢复/复用验证范围。
已有FINAL_DRAIN时复位零FSM增益不能证明计算中复位也无增益。
定向方案必须先绑定实际阶段与合法复位触发条件，不能反复试延迟
或用正常完成测试替代取消路径；尚未证明命中或提高百分比。

## 目标及基准

用户授权通过补充激励和合理豁免提升FSM与Toggle到80%以上。
本轮使用同一冻结VCS镜像、正式741项PASS集合和兼容覆盖配置。
最新独立核验报告为`verification/out/raw741-dve-parent-20261007-01/summary.csv`。
系统层级为`ara_tb.dut.i_ara_soc.i_system`。

| 指标 | 原始基准 | 目标 | 相差百分点 |
| --- | ---: | ---: | ---: |
| FSM | 60.54% | >80% | >19.46 |
| Toggle | 63.55% | >80% | >16.45 |

已完成并独立核验的66条不可达转换豁免，将同一741项集合的
FSM提高到63.88%（增加3.34个百分点）。正式资格文件：
`verification/out/fsm741-exact66-full-report-20261007-02/qualification.json`，
SHA为`dd6dbf0c3a1d670fd0296aa392139d3ab3733be0682ba23a1bfbf381a23462ce`。
实际raw/applied/reset/reloaded/final五份根层级表均已核对。
此批只改变FSM分母；Toggle仍为63.55%。80%目标尚未达到。

四个纯观察实例的排除也已独立完成资格核验：同741项集合
Toggle从63.55%变为64.65%，FSM不变。资格文件为
`verification/out/observer-only-rooted-741-agent-20261007-04/qualification.json`，
SHA为`89f34505d6650340851c46c983e95b0672803b6fd4949d2ac7c6b2ac05207c9c`。
这是范围调整，不是新增激励命中。两批目前为独立报告，不能
将两份百分比当成已生成的组合报告。

新增cached完整QBS检查已正式纳入742项历史冻结镜像PASS集合：
`verification/out/gap113-full8-cached-offline-admitted-742-agent-20261007-01/`。
其743行清单为同一编译VDB加742项测试，继承完整741项前缀。
后续组合报告将使用742项；上表的独立正式数字仍属于741项。

742项组合报告现已完成：
`verification/out/fsm72-four-observer-full742-20261007-01/qualification.json`，
SHA256为`5189117b74763e0c56d0a09b5decef5ac3bf491b6cd23eaa1949676d511e58f2`。
父级独立核验4728个输入/输出文件哈希，全部匹配。
该报告含72条精确FSM转换与四个非递归观察实例排除；不含下述
61条归约互斥候选或可靠算术数据通路的后续排除。

| 同一742项集合 | FSM | Toggle | Line | Condition | Branch |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原始/清除豁免后 | 60.54% | 63.55% | 85.21% | 82.03% | 82.95% |
| 应用/重新加载后 | 64.20% | 64.65% | 85.18% | 82.04% | 82.99% |

观察模块的范围调整可同时改变各指标的分母，因此Line略降并非
测试丢失。80%目标仍未达到。这是冻结镜像的集成报告，不是当前
主线RTL的signoff证据。

124条FSM集合也已正式完成原生验证：
`verification/out/fsm124-native-742-20261007-01/qualification.json`，
SHA256为`c57eec2fc9ba17ad57860c1139cdd3fcd959e66b80aa2efb745fa3c2d24f47fe`。
父级独立核验4745个输入/输出pins无差异；applied/reloaded的
124条完整原生记录相同，且等于批准集合，reset恢复raw。
FSM从60.54%提高到67.14%。该报告不含四observer或FMA排除，
Toggle保持63.55%，不能拼接其他报告的64.65%作为组合结果。

本次集合组成是72条既有记录加VMFPU26、VALU8、双缓冲12、
PTW cache-port0六条。独立审查后保护了VMFPU/VALU所有新增
回到NO的复位弧、port0的REPLAY_REQ到IDLE及SIMD20条。
前文较大的候选计数仅是审查过程，不是实际批准/应用数量。

最新统一报告为
`verification/out/fsm124-fma108-observers-full742-20261007-02/qualification.json`，
SHA256为`e5b785f12178705aed23eddc1ade56c9deac5efb3efc2ad237ef38e60782cf3e`。
同742项集合，包含FSM124、四observer和FMA108；父级独立核验
4918个pins无差异。原始FSM60.54%/Toggle63.55%，应用与重载
均为FSM67.14%/Toggle64.52%，清除后完全恢复原值。
相对observer-only的64.65%，加入完整FMA数据通路范围后Toggle
下降0.13个百分点，说明该数据通路原本覆盖高于系统平均。
不能只排除其中未命中位来追逐目标；该报告按一致的数据通路范围
保留覆盖点和缺口的完整排除，并如实展示分母变化。80%仍未达到。

目标不是承诺所有未覆盖点都可豁免。原始与豁免后报告分别展示，
不得将冻结旧镜像的结果称为当前主线RTL signoff。

## 四路工作

| 工作 | 优先范围 | 输出及准入条件 |
| --- | --- | --- |
| FSM激励 | cache/PTW、scalar load、Dispatcher合法异常与恢复转换 | 目标转换及可达条件、独立参考结果、实际VCS命中 |
| FSM豁免 | 参数禁用状态、结构不可达转换 | 冻结源码/参数与compiled shape证明、精确DVE记录 |
| Toggle激励 | payload、VRF/operand数据、lane/寄存器组、SEW边界 | 信号映射、合法数据模式、独立功能核验及并集增量 |
| Toggle豁免 | 固定端口、padding、参数固定bit | 精确bit/方向、恒定性证明及原生DVE排除记录 |

先按实际覆盖对象分母排序，优先少量高增益测试；不按测试数量
判断进展。仿真最多8路同时执行，禁止同目录覆盖，优先短测试。
运行较久的任务后台独立服务执行，确认进程和日志后不反复轮询。

## 豁免边界

### 当前执行证据（2026-10-07）

C910的`c910-srt-native1264-load-agent-20261007-03/first.el`已经
由DVE实际导出。父级独立核对1264个批准对象：1208项源码wire
导出为native net，56项导出为reg；实例、双校验码、信号名和位宽
均匹配，缺失0、额外0。旧检查器仅接受reg/wire/logic，因此报
Unknown exclusion syntax，不能将这个工具错误解释为RTL问题。
后继只允许有源码依据的wire/net对应关系，不放宽对象清单或位宽。
`c910-srt-native1264-load-agent-20261007-04`的DVE原生验证已启动；
完成save/reload/reset之前仍是候选，不纳入上述正式百分比。

04后实际因顶层DVE脚本的`info script`路径语义而失败：前代Tcl
被错误定位到输出目录，任务随后退出，失败证据保留。恢复任务
`c910-srt-native1264-recovery-agent-20261007-01`改用绝对源路径，
从`/tmp`执行的静态测试及阶段顺序检查共3项通过。现已实际完成
原生保存、重载和还原，资格状态为
`EXACT_C910_1264_NATIVE_ROUNDTRIP_NOT_POPULATION_APPLICATION`。
`capture-result.json` SHA256为
`5fa9180cf70f658fbf355e7510a8d9c99af0240f6be22084139791f47fddbf38`。
父级独立核验167个pins全部一致；1264个批准对象、416个本地
保护对象、零额外排除均经核验。该结果尚非742项应用后的系统
计分报告，不能从77472个逻辑位推算或宣称Toggle已经达到目标。

DWC错误支路的源码契约与反例检查7项通过，命令为
`python3 -B -m unittest discover -s verification/coverage -p test_review_dwc_internal_error742.py`。
该证据支持INCR生产者不会进入仅接受特定WRAP请求的错误支路，
但不能代替31项FSM/168项Toggle的精确DVE排除、重载及保护点核验。
新增原生工具的16项测试也已通过，但首次实际导出包含
`Toggle 0to1 ...`方向性记录，检查器未识别而失败。因此该批
仍未计入正式报告。后继必须按实际导出逐bit、双方向核对，不得
将单方向排除当成整个信号排除，亦不得跳过保护对象检查。

DWC后继`dwc31-fsm168-toggle-native742-agent-20261007-03`已实际
完成原生资格验证，状态为
`EXACT_DWC31_FSM_168_INTERNAL_TOGGLE_NATIVE_QUALIFIED_NOT_APPLIED`。
`capture-result.json` SHA256为
`9b6bba6bdb55dec71a34be08a39391bcced706432916bef747d6c4dcb90560c3`。
父级独立核验836个pins全部一致。实际范围是7个不可达状态及
24条关联转换，32个内部Toggle对象共168个逐bit方向；其余8个
FSM点和4188个Toggle位置受保护。资格检查含五阶段审计、重载
一致性及四份空排除文件，不等于已生成系统层级应用后百分比。

统一应用报告任务已启动：
`qualified-native-combo-full742-agent-20261007-02`，config seal为
`4931ffe35e81785b2897fd1b83d10209599c275a4f6e6ac2a127d64c9f07c3a3`。
该任务一次加载124条既有FSM、四observer、FMA108、C9101264及
DWC31/168，避免重复对742项集合做多份应用报告。01曾因启动器
适配遗漏subprocess.STDOUT在DVE启动前失败，已保留失败证据；
02修复该适配，命令构造检查通过并确认实际DVE进程。终态仍须
独立核对精确集合、保护补集与raw/reset/reloaded实际计分。

GAP114受控异常/flush实验已完成。原离线检查拒绝结果的原因是
复用检查契约固定`ara_trap_events=0`，而该程序预期8次S-mode
ecall。实际完整匹配65298条有效指令、35428项标量写、10735项
标量内存访问，mismatch为空，无跳过状态；父级独立核对8个
trap标记均为`00000073`，PC顺序精确对应trapA、trapB及recovery。
需按该case预先定义的8次异常严格复验，不更改通用零异常门禁，
不将此项解释成RTL故障，也不重跑已完成的VCS。

GAP115活动DIV复位实验完成且程序报告成功，但原UVM准入门禁
拒绝：`+COMMIT_TOHOST`使`ara_commit_monitor.sv:270`直接调用
`$finish`，未置UVM绑定的`ara_tb.exit[0]`，因此最终UVM check/report
summary及TEST_DONE缺失。已有完整事件可供独立两epoch守恒与
架构恢复审查；在完成该审查前不准入，不能伪造最终UVM报告或
把原门禁失败修改成PASS。

用户后续授权功能单元和可靠复用模块的豁免。将其与不可达点豁免
分开管理：可信复用IP移出本轮集成覆盖率门禁，必须明确独立验证
证据、复用源码身份及范围，不能声称被排除IP已经靠本轮达到80%。
全设计raw保留；集成报告单独列出排除模块和理由，不用相同标题
混淆两种分母。不能仅凭模块名称、历史使用时间或上游来源判可靠。
QBS、AKV、改动的接口/控制、已知故障及其相关信号继续保护。

当前FPnew依赖存在修改的`fpnew_cast_multi.sv`、
`fpnew_divsqrt_multi.sv`、`fpnew_opgroup_multifmt_slice.sv`、
`fpnew_pkg.sv`及C910的`ct_vfdsu_round.v`，这些不能仅按复用IP
整体排除。未修改的算术子模块须逐项核对冻结源码和独立测试证据。

- 不允许因为Linux/llama.cpp暂时未使用，就排除仍可达的功能。
- 不允许排除已发现bug、超时、未检查通过的路径。
- 不将整个功能模块伪装成不可达点豁免，不通过force/deposit翻转
  信号制造功能覆盖。经过独立验证且冻结源码未修改的复用子IP，
  可明确移出本轮集成覆盖范围，但仍保留其原始覆盖率及验证责任。
  纯验证观察模块可在独立产品RTL统计口径中排除，但必须证明不
  参与功能控制；原始含观察逻辑报告保留，不解释为新增激励收益。
- FSM状态和转换分开审查；Toggle必须确认DVE编码及bit/方向含义，
  不能将原始序列位置直接当作逻辑bit。
- 既有5832点只覆盖分支/条件，不会直接提高FSM或Toggle。
- 新排除文件必须校验scope/checksum/源码参数，保存、重载并恢复
  raw，确认没有额外邻点被排除。

### 可靠模块的排除准入

FMA108首次批量原生验证在首实例取消选择时失败，原因是DVE
返回的嵌套列表未经规范化；失败清理随后被重算提示弹窗阻塞。
2026-10-07已终止精确任务
`ara-fma-datapath-108-native-agent-20261007-01.service`，保留失败
目录和诊断证据，不将其归档为PASS。后继必须修复选择列表及
reset/recalculate/save顺序，再使用独立输出目录验证。
一次product格式验证成功不能替代108对象集合验证。

后继`fma-datapath-108-native-agent-20261007-02`现已完成108对象
原生load/save/reload/reset验证。资格状态为
`EXACT_108_FMA_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS`，
`capture-result.json` SHA256为
`8d3c1c3e285b03de9b94244506b3a22436a8c59803680c981f4206b85b7dd9ee`。
父级独立核验161个pins无差异，两份EL精确108对象语义集合相等，
无其他排除，最终清空。文本排序不一致不作为语义差异。
该批含12实例乘9个内部算术信号，8368逻辑位双方向；它是
集成覆盖范围调整，不是穷尽功能验证，不是不可达豁免。
已应用到上文`fsm124-fma108-observers-full742-20261007-02`统一报告。
不能由对象数量估算系统Toggle百分比，必须使用实际DVE根层级结果。

用户再次明确允许可靠功能单元豁免。执行时优先选择未修改且已有
独立验证证据的FMA、除法/开方内部算术数据通路，而不整体排除
VMFPU、VALU、Lane或整个FPnew包装层。接口和控制仍参与集成
覆盖：valid/ready、in-flight状态、仲裁、复位、flush、mask/tail、
舍入和异常状态及本地修复逻辑均保留。可靠性证据只支持对应
运算、精度和配置；不能将部分通过记录解释成整个功能单元穷尽验证。
此类排除单列为复用数据通路范围调整，并完整保留raw结果与排除
清单；不把它与结构不可达豁免混为一谈。

进一步的FP16复用数据通路候选证据来自历史PASS的
`c0279-extra-rvv-vfdiv-46c98dbd428e`。其oracle是严格常量自检加
trace审计，不是逐条Spike完整架构对比。`vfdiv.c`包含e16的
vv/vf、masked/unmasked四组；main明确设置`CHANGE_RM(RM_RTZ)`。
父级用精确Fraction解码binary16、计算有理数商，再按向零舍入
独立重算TEST_CASE1的首组16个参考值，16/16一致。
VCMP_U16执行严格相等比较，不是容差检查。仍须确认历史ELF
实际执行、compiled子槽映射和冻结源码身份后，才可扩大对应
内部算术集成范围；不能推广为RNE或全部特殊值已验证。

| 类型 | 所需证据 | 可采用的处理 |
| --- | --- | --- |
| 未修改算术子IP | 冻结源码身份；独立参考模型下的通过记录；参数及运算范围匹配 | 仅在集成报告中排除经验证的实例/范围 |
| 参数禁用功能 | 实际编译参数、实例连接及不可达逻辑证明 | 精确状态、转换或信号bit豁免 |
| 纯验证观察模块 | 输出连接审查，证明不驱动产品状态或功能控制 | 产品统计范围排除，保留含观察逻辑的raw报告 |
| 本地修改的IP或集成控制 | 无论上游来源，仍需验证本地修改及交互 | 保持纳入门禁；不可因历史成熟而整体排除 |
| 已知失败或尚未证明的功能 | 首错记录、待补验证证据 | 不豁免，不进入verified PASS集合 |

每个排除项记录实例路径、源码/配置身份、理由、证据路径、批准
范围及原生DVE排除对象。只验证过部分SEW/运算/参数时，不能
推广成整个功能单元的验证完成。集成接口、握手、复位、异常、
mask/tail及共享资源交互仍由本项目承担覆盖责任。

## 增量收集

### VMFPU归约互斥转换候选（尚未正式豁免）

2026-10-07对742项并集与冻结源码补充核查得到41条额外候选。
`hardware/src/lane/vmfpu.sv`的SHA256为
`1f8288ed2a50f8fa59a7ea3d6f3a7e3138f5219bbb1af52e864d9dfe359d8307`，
与冻结构建记录一致。INTRA、INTER_TX、INTER_RX、LN0_COMMIT
四种归约状态分别在2056、2223、2246、2314行无条件设置
`prevent_commit=1`。候选目标为INTRA/NO/OSUM；产生这些目标的
提交或新接收路径要求`!prevent_commit`（2596、2657行）。
MFPU_WAIT的2523行推进属于独立case，不能从上述四个状态执行。
复位只进入NO，不属于普通FSM转换刺激；保留复位验证责任。

- 四个lane各有INTER_RX/TX到INTRA/NO/OSUM的六条，合计24条。
- 四个lane各有INTRA到NO/OSUM的两条，合计8条。
- lane1至3各有LN0_COMMIT到INTRA/NO/OSUM的三条，合计9条。
- 与既有lane职责豁免无重复；742项兼容PASS并集中41条均未命中。

这是控制条件互斥证据，不是把归约模块认定为可靠后整体排除。
当前仍需独立复核全部后续赋值与原生DVE保存/重载核验，不将
41条提前计入正式覆盖率。已修改的归约控制及合法转换保持覆盖。

同一分析方法在VALU得到另外20条候选（742项均未命中）：
四个lane各有INTER_RX/TX到INTRA/NO的四条及INTRA到NO的一条。
889行的case入口在`alu_state_q!=NO_REDUCTION`时必定成立；
1014、1066、1076行在上述三个状态中无条件设置prevent_commit。
1250行的提交及1306行的新接收路径要求其为0，因此目标状态
不能由这些路径覆盖。冻结VALU源码SHA256为
`f8a8cd12e9d4732eca87e1c9a1aa48b52a8e684f2d7e64d0e8ec1faa9411c778`。
LN0/SIMD的转换不据此扩大排除，全部复位及合法归约路径保持覆盖。
这20条仍为待独立审核及DVE验证候选，未计入正式数字。

### 双缓冲lookahead索引互斥候选（尚未正式豁免）

实际compiled实例`i_vlsu.i_store_load_lookahead`使用
`store_load_lookahead_pair.sv`，不是同名的单缓冲模块。
冻结源码SHA256为
`ba8ec0605fd37db5b9574c3f04bc6c962fa23a0582e6029999fcbb5a8d57ea20`。
两台机器`state_q_0/1`各有六条额外候选：Empty到Ready、Fill到Send、
Pending到Ready、Ready到Send、Replay到Ready及Replay到Send。
742项中这12条均未命中。

183行的Pending推进只写`pending_idx`，该索引只在Pending状态
选择，且存在Fill时private_busy为1，禁止该推进。202行的fill
覆盖只写`fill_target`；fill_fire要求已有Fill或实际prepare_fire，
因此目标只可能处于Fill或Send，不能覆盖其他四个状态。
这些是数组索引和状态谓词的互斥条件，不是整个缓冲模块的可靠性
豁免。Send到Ready的同周期AR/R路径仍保留；第二缓冲的Pending
状态也保留，不能因为当前未命中而认定不可达。
本批待独立复核和原生DVE验证，尚未计入正式覆盖率。

### SIMD除法直接IDLE转换候选（复核后保留覆盖）

四个lane的`i_vmfpu.i_simd_div`各有五条候选，合计20条：
ISSUE_SKIP/ISSUE_VALID/LOAD到ISSUE_IDLE，以及
COMMIT_READY/COMMIT_SKIP到COMMIT_IDLE。742项均未命中。
有效case分支只允许这些状态推进到VALID/SKIP/WAIT_DONE或
READY/SKIP/DONE；直接IDLE赋值属于default或完成/空闲状态。
但独立复核发现compiled转换实际绑定到365/366行的异步复位
赋值，而非156/205行的default。同步状态路径互斥不证明复位
转换不可达；首次审核时尚无工具语义证据证明这些转换不统计reset。
因此撤回本批“default提取伪转换”的解释，20条全部保持覆盖，
不能计入豁免。其余包含回到NO/IDLE的候选同样须检查compiled
源位置，不能以同步控制互斥掩盖真实复位路径。

工具判别现已完成：
`verification/out/fsm-async-reset-sampling-probe-agent-20261007-01/result.json`，
seal为`623089878c0f5d6bd6ee3aa07257ff15e180912c7feb504a9dd14305fd2ef434`。
冻结选项未启用reset过滤；同VCS与覆盖/时序选项的独立最小探针
在A/B/C三个状态分别非时钟边沿复位，三条reset弧全部计数。
因此上述20条SIMD及27条归约复位候选必须保持覆盖，不可按
“工具默认不采样”处理。该探针不并入产品VDB，不能替代产品复位
测试，也不能将模型探针的命中当作系统覆盖增量。

### FINAL_DRAIN复位实验的实际结果

`gap113-cached-final-drain-reset-old-image-742-agent-20261007-01`已正常
结束，VCS CPU249.480秒；日志确认目标QBS_FINAL_DRAIN触发一次
复位并释放，重启后41项自检通过，接口监视器protocol_errors为0。
这不足以替代独立epoch/VRF资格检查，尚未正式准入。
父级直接比较其累加器FSM数据与742并集：checksum匹配、宽度288，
新增序列位置为空。因此本次不声称命中了预计的16条
SCALE_MULTIPLY到DOT_CONVERT转换，不重复相同实验。后续须核查
触发时累加器实际状态及entry分配生命周期，建立新假设后才测试。
父级随后直接读取该测试全部FSM instance_data，与742项的相同
checksum及宽度逐项比较：系统所有实例新增FSM位置总数也是0。
因此不把其他模块的潜在复位增量当作本次收益。零增量本身不能
证明工具不采样异步复位；需相同VCS及覆盖选项下的工具说明或
独立、明确从目标状态触发复位的最小判别实验，再处理复位弧。

SRAM审查同时确认当前编译配置不采集存储数组的Toggle；85个
`tc_sram`实例仅有680个clk/reset/req/we序列位置。排除数组无收益，
禁止为提高覆盖率而排除这些实际存储接口。

1. 提取各scope实际分母、已覆盖点、未覆盖点及源映射；将缺口
   分为可达、已证明不可达、待证明、已知故障四类。
2. 测试先完成Host/Spike或独立QBS/AKV参考预检，再运行一次
   有具体目标的VCS；失败保留证据，不纳入verified集合。
3. 通过后与741项并集比较，仅在有实际覆盖增量时追加正式清单。
4. 阶段性批量导出DVE，不为每个微小增量重复全量仿真或导出。
5. 同一PASS清单输出raw和reviewed-waived两份报告，核对测试身份、
   层级顺序、配置、输入完整性与排除文件，记录各自百分比。

尚不能仅依据当前汇总百分比证明80%可达。若无新命中，仅靠删除
未命中分母，FSM需要排除约24.33%的原始全部对象，Toggle约20.56%；
如此大量的豁免必须有逐点依据，不能为了目标数字强行排除。
若合理豁免与可实现激励仍不能达到目标，应明确报告剩余缺口。

## 本轮已确认结果

### 741项缺口权重定位

直接读取正式741项`combined-bits.json`，系统下FSM共有1838个
原始序列位置，命中1283个。这不是DVE计分分母：其比例与系统
正式FSM60.54%不同，不能用原始位数量自行计算豁免后百分比。
原始未命中位置只用于安排工作优先级：

| 实例 | 原始未命中位置 | 下一步 |
| --- | ---: | --- |
| QBS FP accumulator | 48 | 拆分机器与状态/转换，判断合法输入及流水控制是否可达 |
| CVA6 AXI error slave ATOP filter | 31 | 审查上游过滤及固定ATOP配置，不能按名称直接排除 |
| Dispatcher | 28 | 对照已审查结构转换及FOF首错，故障相关点不豁免 |
| WT Dcache读port2 | 27 | 已核对冻结连接恒零，待原生DVE资格 |
| Store/load lookahead | 24 | 审查进入/退出、等待和恢复组合 |
| VMFPU | 每lane19 | 区分lane参数不可达与缺失归约/队列交互 |
| WT Dcache读port0/1 | 19/15 | 补合法replay/kill/miss并发，不重复已否定的缓存行碰撞刺激 |
| PTW | 18 | 参数禁用分支与合法页表fault/flush路径分别审查 |
| VALU | 每lane9 | 区分lane0归约职责和其他lane可达状态 |

WT Dcache读port2不可达候选已核对冻结四份源码及编译配置。
当前实际存在`gen_accelerator.i_acc_dispatcher`，不能用未启用
accelerator分支解释；有效证明为`acc_dispatcher.sv:556`请求恒零，
经`cva6.sv:1400`接入port2，读controller从IDLE离开要求data_req。
只审查7个状态和20个转换，保护IDLE及port3共享写路径；未完成
原生排除资格之前，不称为已应用豁免或新的百分比。

系统级Toggle较低部分包括标量核49.76%、向量后端68.52%；
每lane VRF为95.48%，因此不以重复VRF数据激励作为首要任务。
QBS engine为66.13%、PTW为37.54%，还须结合实际对象分母排序。

后续全设计Toggle并集已生成：
`verification/out/toggle741-capacity-ranking-agent-20261007-01.json`。
全体系统后代原始序列位置2649938、未命中987319；它仍不是
官方Toggle分母。QBS子树102实例、原始位置258550、未命中94566；
payload bank0/1分别未命中26222/29358。纯观察实例的较大缺口
包括`i_cva6_rvfi`41688和`i_cva6_rvfi_probes`11581，须独立审核
产品统计范围，不把删除观察逻辑分母称为产品执行覆盖提升。

FSM shape已拆解为576个状态（命中519）和1262个转换（命中764）。
转换比例60.5388%与DVE60.54%一致，但原生资格和实际评分仍以
DVE为准。已证明的三组初始候选只含34个未命中转换，单靠这些
不足达到80%，需要继续补激励和审核其他真正不可达的转换。

QBS FP accumulator的48个未命中转换为16个entry各自的
`FP_AUX_CONVERT`、`FP_MIN_SCALE_MULTIPLY`、`FP_SCALE_MULTIPLY`
到`FP_DOT_CONVERT`。正常entry生命周期禁止中途复用，但异步
复位清除`entry_valid_q`而不复位`entry_state_q`，复位后新请求
可产生这些转换。因此不能仅依据正常计算路径将它们豁免；需
核对冻结源码和复位契约，以合法复位恢复激励补充覆盖。

### 固定lane职责的VMFPU候选

已独立核查`ara.sv`、`lane.sv`、`vector_fus_stage.sv`和`vmfpu.sv`
当前内容均匹配冻结构建源码。`ara.sv:488`将genvar lane编号作为
常量传入；`vmfpu.sv:2281`唯一的相关状态入口依据该常量分流。
`next_mfpu_state`只返回NO/INTRA/OSUM，复位只进入NO。因此有：

| 实例lane | 不可进入状态 | 未命中状态数 | 未命中关联转换数 |
| --- | --- | ---: | ---: |
| 0 | `LN0_REDUCTION_COMMIT` | 1 | 5 |
| 1、2、3各自 | `SIMD_REDUCTION` | 1 | 5 |

注意`LN0_REDUCTION_COMMIT`名称不能解释成lane0专用，其实际
入口在非零lane分支。四实例共24个候选对象全部在741项并集中
未命中；其他124个对象及相反的合法lane职责仍保护。compiled
module checksum为`3873291691`，FSM为`mfpu_state_q`，每实例
raw宽度37。这些是源码及compiled shape候选，原生DVE排除
尚待验证；不能将24对象全部计为计分转换（其中仅20个转换）。

VALU采用相同的固定lane职责：`valu.sv:1097`是相关状态的唯一
入口。lane0不能进入`LN0_REDUCTION_COMMIT`，lane1至3不能进入
`SIMD_REDUCTION`。四实例共4个状态、12个关联转换全部未命中。
`alu_state_q`的module checksum为`1674936110`，每实例raw宽度
21，VALU源码SHA为
`f8a8cd12e9d4732eca87e1c9a1aa48b52a8e684f2d7e64d0e8ec1faa9411c778`，
匹配冻结构建。其余合法计算、排队、提交及复位对象继续保护。

AXI error-slave的ATOP filter暂不豁免，但此前可达理由需纠正：
缺口实例是`i_ariane_axi_dwc.gen_dw_upsize.i_axi_dw_upsizer`内部
不支持burst的错误从设备，不是SoC地址解码错误从设备。
CPU开启A扩展、产生非零ATOP，并不能单独证明该内部路径可达。
冻结`axi_shim.sv`90/253行将AW/AR burst固定为INCR，而
`axi_dw_upsizer.sv`412/474/726行只有不支持的多beat WRAP设置
错误选择信号。上述源码与冻结构建一致；错误从设备位于demux
select=1，正常请求选择另一端口。当前重新独立审查全部选择
信号赋值、compiled实例和slave内部状态后再定排除范围。
普通SoC解码错误、AMO及背压仍保留验证责任，不能由内部DWC
错误路径的证明推广为全部错误恢复不可达。

PTW另已完成参数禁用证明：`ptw_stage_q`的两处时序写入
（reset和update）均受`CVA6Cfg.RVH`保护，冻结配置RVH=0时
都不存在。首个请求虽然给`ptw_stage_d`赋S_STAGE，却不会
更新q。因此该机器属于禁用的guest-stage bookkeeping，不是
“q已复位为S_STAGE”。三个状态和六个转换全部零命中，可作为
精确配置豁免候选；不能排除同实例的常规`state_q`页表遍历。
证据文件为
`verification/out/ptw-rvh0-disabled-fsm-review-741-agent-20261007-01.json`，
SHA为`f21c4f28689fc4e68176463551343e9e4e9c86e053d223df8620ee020bea001c`。
下一组合批次优先纳入六个转换，待实际原生记录和计分核验。

### 原生排除工具的实测边界

四个纯观察实例的排除文件已在
`verification/out/observer-only-scoped-741-agent-20261007-02/`
完成保存、重载和还原验证。但`summary_scoped.csv`的系统及观察
实例数值仍与raw一致，故尚未证明排除改变计分分母；不能将
`APPLIED_OBSERVER_ONLY_741_INTEGRATION_SCOPE`状态理解成目标
覆盖率已经提高。需继续验证计分/刷新语义，raw741保持有效。

FSM三组批量尝试未通过保护审核，已还原所有排除。原生DVE
保存时可将关联转换吸收到状态排除中，GUI逐项查询也不等价于
原生排除记录：port2的`IDLE`出现意外的excluded查询结果。
这些失败报告不用于waived统计；后继优先验证仅转换排除，
同时审查原生记录、实际计分、重载和保护对象，不能放宽门禁
来掩盖额外排除。

### 实测增量与未闭环测试

- 已生成M8/N8两组Q3_K/Q8_K的payload-full8后继，使用独立整数
  点积参考（结果绝对值小于2^23、FP32可精确表示），继承完整VRF、
  source/guard和CSR检查；5项构建单元测试通过。软件预检和交叉
  核查不等于DUT通过或覆盖增量。第一次VCS在600秒预算超时，
  `simulation-status.json`为`SIMULATION_NOT_ADMITTED`，未计入
  741项。后继先分析退休PC及验证循环耗时，不盲目增加预算。
  已准备并实际启动cached后继：同两组原生输入改用静态常量，
  删除DUT上的运行期bit packing，而不删结果或体系状态检查。
  后继软件预检44项检查和42项负向检查通过，父侧独立3项
  静态输入等价单元测试通过。后台服务为
  `ara-gap113-full8-cached-agent-20261007-01`，VCS预算仍为600秒，
  只执行一次；终态后自动离线核验，尚不表示DUT通过或准入。
  独立目录为
  `verification/out/gap113-payload-full8-cached-old-image-741-agent-20261007-01/`。
  后继现已退出0，VCS CPU时间217.650秒。独立离线核验为
  `FULL8_COMPLETE_NATIVE_VRF_CSR_LIFECYCLE_PASS_NOT_FULL_SCALAR_ISA`，
  DUT执行41项检查；不声称Spike支持custom ISA。相对741项，
  当前解析确认2个condition位置、12个二进制Toggle位置新增，
  FSM无新增。packed-array部分尚未给出全量诊断，需由兼容
  VDB的正式DVE报告统计；功能通过与预测增量是不同准入问题。
  资格文件位于
  `verification/out/gap113-payload-full8-cached-qualified-agent-20261007-01/qualification.json`。

- GAP113已独立核验并准入741：新增2402个Toggle原始序列位置，
  正式DVE Toggle由63.33%升至63.55%；FSM没有增量。
- 内存范围内的Sv39 FOF后继180秒预算超时，未准入。末段仍有
  软件退休进展，但更早的trace发现非预期异常：周期54167的
  `0103e407`响应置异常，随后handler记录mcause=13、
  mepc=0x8000213c、mtval=0x40001000；参考应抑制后续元素页故障，
  最后仅有S-ecall cause9。这项属于待确认功能不一致，不能豁免；
  不延长预算重复运行，保留首错证据，其他独立覆盖任务继续。
- 本轮只增加验证激励及覆盖率工具，不修改RTL。

## 2026-10-07 Sv39 S-mode alias terminal and address-padding review

- A separate verification-only scope review identified exactly
  `ara_tb.dut.i_ara_soc.i_system.i_ara_cvxif_dut_bind` and its private
  `.cvxif` interface. Parent inspected adapter/interface/UVM consumers and
  checked all 11 source/compiled-inventory pins. The adapter has 41 input
  ports and no DUT output, inout or ref connection; its 43 assignments
  only feed the private interface. The agent instantiates a monitor only.
  These two scopes are testbench code, not the actual functional CVXIF.
  Their exclusion is a candidate for the next report only, preserving the
  fixed system scope, DUT interface coverage and all running correctness
  checks. No wildcard CVXIF exclusion is permitted. The 19096 missing
  serialized positions are diagnostic, not an official percentage gain.
  Evidence SHA:
  `a274a9ae809ab2bcc8823cf45e1b3a259ef263ed7a9cb0a903d021796cfa5b08`.

- Address-padding fresh02 was independently reviewed after the original
  historical EL rescan incorrectly included its own unexecuted candidate.
  The successor recognizes that candidate only through exact prepared
  schema, source-derived target set, sealed producer and absence of any
  execution/application evidence; arbitrary overlapping files still fail.
  Explicit width/configuration derivation and negative tests were added.
  Parent reran 43 tests and replayed the complete proof02 plus prepared
  dependency/tool-identity checks successfully. Proof SHA is
  `0195478a81a85e9a84d488c0f6bcad0f38d403958ea5d22a46b591fd8f7424a9`;
  native config seal is
  `bb0fad46532f16abe55da63f4522bbeb92f6d83dda5e6e0767a01ee89b7509c7`.
  Local native qualification now runs in independent service
  `ara-vlsu-padding51-native770-parent-20261007-02.service`, with real
  DVE PID 270330 and matching executable/work directory verified.
  This is not population application and changes no official percentage.

- `sv39-rvv-alias-smode-old-image770-agent-20261007-02` completed in
  227.064 wall seconds (211.150 VCS CPU seconds), return code 0, without
  timeout. The DUT printed success; the contract monitor recorded 217
  requests/responses, no protocol errors and no outstanding requests.
  This is a simulation terminal result, not correctness qualification or
  coverage admission. Full scalar/vector, expected trap, memory and
  pre-edge metadata checks remain required before admitting the VDB.
- Parent independently ran `test_prove_vlsu_address_padding770.py` and
  `test_vlsu_address_padding_native770.py`: 22 tests passed. The candidate
  covers 51 internal address fields, only bits `[127:64]`; the low 64 bits
  and all interfaces remain protected. The 3264 bits / 6528 direction
  coordinates are diagnostic capacity, not an official denominator or
  measured coverage increase. Source hashes close the reviewed writer
  inventory; mutation rejection alone is not a semantic equivalence proof.
- Native full770 report service
  `ara-native-increment770-offline-parent-20261007-02.service` remains
  active. Its sealed inputs are unchanged. The qualified official baseline
  remains full768: FSM 80.64%, Toggle 66.94% after approved exclusions.

## 2026-10-07 continuation: targeted Toggle and other code coverage

This section supersedes the preceding live-job snapshot; it does not erase
the original failure or replace an unqualified report with a passing label.

- The full770 native export finished. Its original wrapper failed on
  `Observer target/protected membership differs: cmd_pop_o`. The offline
  successor identifies exactly 20 queue scopes and 40 complete scalar
  fields (`cmd_pop_o`, `flush_i`) already selected by the sealed prior EL.
  Reconciliation changes no exclusion coordinates and retains all partial
  bits, other objects, and five-stage reset/reload checks. The independent
  parent replay completed successfully, with exactly matching qualification
  SHA `762f949e8bbb8cb55de20970c1f771b399cb4a6c6f0d09ab478da7d102f1259b`.
  All eight negative/positive tests passed in 40.665 seconds. The parent
  output is `native-increment770-offline-closure-parent-review-01`.
- Independently verified full770 reports raw Line 85.21%, Condition 82.10%,
  Branch 82.95%, FSM 70.29%, Toggle 63.93%; applied/reloaded Line 85.18%,
  Condition 82.11%, Branch 82.99%, FSM 80.64%, Toggle 67.75%.
  These percentages are not the still-pending full771 report.
- The Sv39 alias test is formally admitted in
  `sv39-alias-offline-admitted-771-agent-20261007-01/admission-manifest.json`,
  seal `ad9e01dcd0ea3ef442d7f28934bf1695dca61c7b6d1c7580bd2a49f0c2569860`.
  It preserves the 770 prefix and binds the independent parent correctness
  replay. Its 7052 new binary Toggle coordinates and one Condition
  coordinate are diagnostic increments, not percentage-point estimates.

### Next bounded batch

1. ITLB ASID/replacement: execute mapped instruction thunks, rather than
   merely access data. Check exact execution, ASID phases, page/code guards,
   SATP restoration and actual translation updates against independent
   architectural evidence.
2. Sv39 fault-address propagation: alternate low/high canonical fault
   addresses for scalar loads/stores. Check cause, tval, fault PC, counts,
   store non-effects, guard bytes and successful recovery. Do not reuse the
   unclosed fault-only-first scenario as a known-good reference.
3. QBS routing: first derive a legal descriptor/address mapping that reaches
   specific missing hit/group_hit bits. Changing payload values alone is
   insufficient. If the missing combinations are structurally unreachable,
   prove exact constant bits rather than run ineffective simulations.
4. Prepare one fresh full771 DVE report using source-qualified constant-bit
   candidates only. Skip a testbench-monitor candidate whose native API
   readback is not closed; it must not delay the useful batch.

Use the existing frozen VCS image, independent run directories and a
600-second budget for each new short test. Background runs must have their
actual process and progress checked once; no frequent long-job polling.
Only independently qualified PASS VDBs enter the cumulative population.
Keep failures and timeouts outside the scoring union and retain first-error
evidence. No RTL changes are required for this coverage batch.

Measure each batch against the preceding compatible union: newly covered
coordinates per module plus native Line/Condition/Branch/FSM/Toggle before
and after exclusions. Never infer a score from raw capacity, or waive a
functional datapath merely because it is considered reliable. Reuse all
compatible prior PASS VDBs; do not rebuild or rerun the full population for
software-only stimulus additions.

### Verified module-level priorities

The following are actual full770 native hierarchy percentages, not an
average across modules. Queue entries show lane 0; all four lanes were
inspected and these three queue types have matching scores.

| Module | Raw Toggle | Applied Toggle | Raw Branch | Next evidence needed |
| --- | ---: | ---: | ---: | --- |
| CVA6 PTW | 40.27% | 40.27% | 45.98% | Instruction translation and expected page-fault paths |
| QBS read engine | 39.90% | 44.60% | 89.92% | Address/layout selection, not repeated arithmetic payload |
| MaskM operand queue | 54.22% | 60.37% | 32.59% | Legal command/count bounds and actual mask producer paths |
| Slide/index operand queue | 63.89% | 69.08% | 33.33% | Indexed/slide metadata and per-queue conversion reachability |
| Store operand queue | 62.50% | 67.43% | 34.81% | Command/count and real flush/backpressure paths |
| QBS engine | 67.90% | 75.05% | 95.35% | Residual routing and constant-bit proof |
| AKV engine | 77.28% | 78.83% | 96.95% | Specific residual replay/fault bits, not a new broad payload sweep |

The low queue Branch scores do not establish a missing functional test on
their own. `FPUSupportNone` and disabled conversion parameters prune
several source paths; an older source audit already classified 720 branch
coordinates as parameter-false existing candidates. Their actual full770
application and native leaf scoring must be reconciled before claiming a
new exclusion or test gain. Existing candidate status alone does not prove
that the scoring denominator changed.

For pending MFPU constants272, parent independently reran eight tests in
7.135 seconds and the complete source/config verifier successfully. This
only approves preparation for fresh native binding and five-stage checks;
it is not population application. Dynamic results/tags, flags, arbitration,
interfaces and protected descendants remain in the coverage inventory.
Parent also ran all 43 Sv39 admission tests successfully in 1.848 seconds.

### Fresh771 launch and preflight evidence

- Parent independently passed all eight `test_report_native_full771.py`
  tests in 90.491 seconds and the complete sealed `check` command. The
  prepared configuration seal is
  `3269a95bf92f99d3c4e31066b6807176e65e7f36c74a374752f9ac52bafcdbb0`.
  Output: `native-full771-padding-pack-prepared-agent-20261007-01`.
  The single background unit is
  `ara-native-full771-parent-20261007-01.service`, verified active/running
  with worker PID 334704 at launch. It performs launch-time input checks
  before starting DVE; active worker status alone is not proof of a live
  DVE process or a successful report. Read the actual `live-identity.json`,
  `launcher.log`, and terminal qualification after completion. Do not
  restart solely because no report has appeared yet.
- This report includes only locally qualified padding51 and pack323, in
  addition to the prior canonical union. MFPU272 and monitor02 remain
  explicitly outside this report. Existing raw/applied770 percentages
  remain authoritative until the full771 qualification passes.
- Inspection of the actual full770 `combined.el` found only Toggle and
  FSM state/transition directives, not Line/Condition/Branch directives.
  Consequently the old 720-coordinate parameter-false Branch candidate
  cannot be described as applied by this union. A separate native-approved
  addition is needed if those points are to be removed from scoring.
- Parent ran all eight ITLB preflight unit tests successfully in 0.069
  seconds. Its original reference preflight failure remains preserved;
  independent parsing of the saved Spike trace against the current address
  oracle found exactly 48 matching S-mode ECALL types/PCs. This is a
  reference-checker reconciliation, not DUT qualification, and no failed
  preflight may enter the coverage union.
- The scalar FPU experiment completed VCS successfully with 22 selfchecks
  and 14.740 seconds CPU time. Its wrapper failed before qualification:
  an unanchored `BP_PROBE_ERROR` search also matches the echoed Tcl source.
  The actual `BP_PROBE_READY` event occurs exactly once. The contract line
  includes `mmu_request_cycles=0`, which must be parsed explicitly instead
  of using the older field layout. Preserve the failed wrapper and inputs;
  validate an offline successor against real error/duplicate-event/nonzero
  counter negative tests, then replay full architecture and waveform
  checks. A selfcheck success is not enough to admit this VDB.

### Continued Toggle closure: measured evidence, not population size

The full771 worker has now launched the actual native DVE executable
(`/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/gui/dve/linux64/bin/dve.exe`,
PID 336508). Its exact-audit and before-exclusion exports are progressing.
Partial CSVs remain non-authoritative; retain the full770 published scores
until terminal qualification succeeds.

The scalar FPU offline successor is
`scalar-fpu-backpressure-offline-diagnostic-771-agent-20261007-04`.
Parent independently passed 15 checker tests, checked 233 frozen input
identities, and replayed the actual VCD against the saved waveform audit.
The evidence contains 12 capture/hold/release transactions, 64 STALL
samples, and three ownerless idle flushes. A legal idle flush requires
READY, no valid request, no pending transaction, and both hold/use-hold
controls clear; active-owner flushes remain rejected by negative tests.
The architecture evidence covers 285 retired instructions, 114 GPR writes,
96 scalar memory accesses, exact floating results/NaN boxing, flags and
FCSR restoration, guards, and 22 selfchecks. No VCS rerun or RTL change
was needed. This is qualified diagnostic evidence, not yet population
admission or a claimed Toggle gain.

For each prospective new test, first map missing Toggle coordinates to
legal producers. Exercise both transition directions with data patterns,
addresses, metadata boundaries, or real ownership/backpressure sequences.
Measure newly covered coordinates against the compatible cumulative PASS
union before spending another simulation or report run. A repeated pattern
or larger seed population is not useful if it reaches no missing points.

The operand-count review provides a concrete counterexample to excluding
bit 8: e8/m8, VL=1024, vslidedown stride=31 legally produces command count
264 and retained count 256. Those bits are already covered in all four
slide queues, so do not rerun that test or waive them. Proposed bits [10:9]
remain HOLD until all ordinary, indexed, slide and maintenance producers
are bounded. Similarly, a missing QBS routing coordinate without a legal
byte-mapping witness is not by itself proof of a constant signal.

Next useful candidates are instruction-side ASID/replacement, vector Sv39
fault-address propagation, and exact scalar-FPU hold-path coordinates.
Describe the fault test as vector VL=1, not scalar LSU coverage. Admit only
independently checked PASS results; retain full771 as a prefix when adding
the next compatible batch. Native-proven disabled-format MFPU constants
and parameter-false Branch points may reduce the denominator separately,
but must not be described as new functional coverage.

### Independent checks and next denominator audit

Parent independently passed 30 ITLB preflight/runner/collector and Sv39
fault-preflight tests in 6.102 seconds using `verification/tools/soc-venv`.
The system Python lacks pyelftools and produced three import errors; this
was a host dependency mismatch, not a DUT failure or grounds to change
the checkers. The ITLB and Sv39 workers were verified with actual simv
PIDs 338545 and 341575, respectively, matching their independent run
directories and active CPU execution. Both use the existing frozen image
and terminal-only collectors; neither result is admitted while running.

Parent also passed all ten QBS routing host tests and independently
replayed the exact source-domain report with seal
`f4e3a58721eb928ed1401f570fa31484734c4a9b2a221c52d1fbda47226f9742`.
The selected legal trace witnesses only 106 missing serialized positions;
the 7472 positions without a legal byte-mapping witness are not proven
all-cycle constants. Do not launch a dedicated low-yield VCS experiment
or turn that classification into exclusions.

The Sv39 diagnostic target list includes exception fields from multiple
producers. Split it before treating the list as a coverage forecast:

- The current VL=1 vector page-fault test can exercise its actual tval,
  valid, and cause-low-bit propagation.
- FOF, nonzero fault vstart, store-response, QBS, and AKV exceptions need
  their own legal producer conditions; inclusion in a target inventory is
  not evidence that this test reaches them.
- gva, tinst, tval2, and cause high bits require a source/configuration
  domain review, including RVH=0 and every assignment/forwarding path.
  A field that stayed zero in the current tests is not automatically
  constant. Only a closed source proof and exact native-node binding may
  authorize a later exclusion.

Keep this classification in a fresh read-only successor artifact, rather
than changing inputs sealed by an active simulation or DVE session.

### Measured FPU gain and Sv39 terminal-boundary diagnosis

The scalar-FPU collection reports 148 new serialized Toggle positions
against the exact771 union, all in the scalar FPU wrapper: held operand
registers, operation, format, and tag fields. Line/Condition/Branch/FSM
increments are zero. Parent passed four gain-checker tests independently.
This is real stimulus gain, not an official native percentage; population
append remains pending its sealed collection and admission checks.

The Sv39 run completed VCS with return code zero in 161.882 wall seconds
(146.930 CPU seconds), SUCCESS, 79 requests/responses, eight exceptions,
and no protocol error or outstanding request. Its original qualification
failed `Complete entry-tohost reference` and stays excluded from scoring.
Parent independently parsed the saved reference: 20781 commit records,
one successful tohost store at index19771 / PC0x8000007a, followed by 1009
records of the terminal `c.j +0` at PC0x8000007e and no GPR/memory/vector
effects. The original collector incorrectly requires the last reference
record itself to be the tohost store. A fresh offline successor must bind
the complete entry-to-success prefix and validate the harmless tail, with
negative tests for absent/incorrect terminal writes and illegal tail
effects. Do not rerun VCS or promote SUCCESS alone into qualification.

Parent completed an independent full FPU gain collection in
`scalar-fpu-backpressure-gain771-parent-review-01`, seal
`80b2e365223b2f4455506d52145079f1ad6180befdf678132f6f0c2691cc9aed`.
The gain, single-test bits, cumulative bits, four-metric delta and input
ledger are byte-identical to the agent's sealed collection. The proposed
772-test union preserves the entire771 prefix and 6162 four-metric
instances. The 148 new serialized pair slots map to operand_a_q80,
operand_b_q62, operation2, source format1, destination format1 and tag2.
These are serialized transition coordinates, not 148 physical signal
bits or a native percentage. Formal admission remains a separate gate.

For the exception-domain proof, trace whole-structure forwarding as well
as local assignments: the MMU data path defaults to misaligned_ex_q,
whose producer can select scalar or accelerator requests. RVH=0 alone
inside one consumer does not prove forwarded fields constant. The
current addrgen misaligned output is explicitly zero and its VLSU/SoC
connection is scalar, which is useful upstream evidence; source hashes,
all other producers, reset and invalid cycles still require closure
before native exclusions are authorized.

### Formal772 admission and bounded-test efficiency

Parent explicitly admitted the scalar-FPU member after the independent
gain replay and 16 admission/terminal-prefix tests passed. The formal
manifest is
`scalar-fpu-backpressure-offline-admitted-772-agent-20261007-01/admission-manifest.json`,
seal `28cc362f64c2c48e8a3b8a1dbf568903434464cc4dcea7e2dfad2aae282ca332`.
Its status confirms 772 unique PASS members, the exact771 prefix, 6162
four-metric OR instances, nonduplicate ELF, independent architecture and
holding checks, and 148 new serialized Toggle positions. This becomes
the base for the next compatible batch, not a reason to mutate the live
full771 DVE input ledger or claim a new official percentage.

The ITLB trial timed out at its original600-second budget and remains
excluded. Its Spike oracle contains 546932 matched instructions; the
partial DUT trace reached 156642 retired instructions. Source analysis
identified a 3*512*16 inner scan recomputing expected leaf PTEs, unrelated
to the intended48 translated instruction executions. A separate stimulus
successor should preconstruct the expected512-entry leaf table once per
phase and compare every entry directly. Retain all16 ITLB slots, all three
ASID phases, all48 calls, all10966 checks and all64KiB code guards. Require
a new independent reference and real slot-visit evidence before any
rerun or admission; do not simply increase the timeout.

The Sv39 terminal-prefix successor passed complete scalar comparison but
rejected `invalidated_fault_csrs=['0x341']`. The actual source deliberately
advances mepc by4 before MRET. Parent reconstructed source-register values
from the DUT trace: the eight fault-handler mepc writes at PC0x80002070
write load-PC+4 or store-PC+4; the four ECALL returns at PC0x800020aa write
the precise resume PC0x800025f0. These normal return writes must be bound
to exact encoding, PC, source value and ordering in a fresh checker,
with negative tests for wrong return addresses and altered cause/tval.
Do not remove CSR integrity checks wholesale or rerun this successful
VCS experiment merely to repair its consumer.

Parent also independently passed all ten MFPU native-binding tests in
9.264 seconds. This approves the binding helper's tested matching rules,
not actual native exclusion or application; the fresh native receipt and
five-stage exclusion/complement checks are still required.

### Fresh MFPU read-only native binding

Parent independently completed the sealed MFPU272 `check` CLI with
return code zero and explicitly authorized a separate read-only DVE
session. Configuration seal:
`01b938fe098477b772226aa4e376f8253d0cccf9fa87533425733e36c45553b1`.
Output: `mfpu-constants272-readonly-native-binding-prepared-agent-20261007-02`.
Background unit: `ara-mfpu272-readonly-parent-20261007-01.service`.

This session inventories 44 target scopes and all744 protected child
scopes, checks exact typed labels/array dimensions and port/internal
roles, and requires both initial and final global exclusion lists to be
empty. It neither applies exclusions nor updates the live full771 report.
The 272 target fields / 34816 proposed direction coordinates are still
source-proven candidates, not an applied score or a native-qualified
exclusion. Actual live executable identity, terminal capture, and then a
separate five-stage apply/save/reload/reset/complement qualification are
required. Freeze dependencies while this capture is running; do not
duplicate launch or infer completion from an active wrapper alone.

The ITLB timeout diagnostic additionally confirms all16 phase0 ECALL PCs
and 156626 nontrap scalar instructions match the reference prefix with
no mismatch or skipped register values. The later two phases and complete
terminal/slot-visit gates remain unproven, so its partial VDB stays outside
the official union despite that useful diagnostic evidence.

Parent verified the actual MFPU read-only DVE process PID354816 with
matching executable and independent output cwd. This is launch/progress
evidence only; stop polling until terminal capture is available.

The next exception-member source review is sealed in
`rvh0-exception-members-source-review771-agent-20261007-01.json`, SHA
`1afeb33d33fd5ddcbd403e97ba42f30fe6269a3a7690d0cbc833ce5b1461df48`.
Parent read its complete producer/forward/reset closure, independently
passed nine tests in 1.390 seconds, and replayed the full source verifier.
It identifies 60 gva/tinst/tval2 fields in five scopes and 3058 currently
missing serialized coordinates under the frozen RVH=0 configuration.
Negative tests reject unguarded writes, RVH else/negated/disjunctive
writers, unknown whole-structure producers and invalid-cycle overrides.
All tval/valid/cause fields, 2756 other typed objects and 38 arrays remain
protected. This is permission to prepare precise native binding, not to
apply exclusions: no new cause aliases, EL application or percentage
claim is justified until the native-node and five-stage gates close.

### Parent continuation: exact CSR returns and cheaper ITLB stimulus

Parent independently passed all17 CSR-return and terminal-prefix tests
in8.196 seconds. The successor binds the deliberate mepc rewrite to
the exact handler PC, opcode, source-register value, observation order
and actual return evidence; cause/tval writes remain rejected. Actual
offline replay in `sv39-fault-alternating-csr-return-parent-review-20261007-01`
passed the architecture gates but stopped at coverage collection. The
historical raw_gain helper incorrectly uses `before['tests'][0]` as the
design VDB. That directory is a test-only VDB and has no design XML.
This is not evidence of deleted historical results or an RTL failure.
A fresh successor must use the hash-bound compile VDB, verify its full
design/shape identity against the sealed baseline, and retain the failed
receipt. No design files may be fabricated, and no successful VCS test
needs rerunning for this consumer error. This member is not yet admitted.

Parent read the full linear ITLB source transformation and independently
passed all6 exact-diff/source-contract tests. The measured Spike workload
falls from546932 to253120 instructions, removing293812 instructions
without changing10966 software checks,48 traps,16 target instruction
pages, three ASID phases or64KiB code guards. This is reference evidence,
not an RTL PASS. Prepare a fresh source-bound runner/collector and require
full architectural and real-slot evidence before the single600-second
VCS attempt can enter the formal772 successor union.

Both existing parent DVE units were independently confirmed active/running
during this continuation. Do not mutate their frozen inputs, infer final
scores from partial reports, or start duplicate sessions. Formal percentages
still refer to the qualified770 population until native reporting closes.

### Native capture terminal audit and independent qualification tests

The MFPU272 read-only DVE capture has now reached a real terminal:
`terminal.json` records returncode0, timeoutfalse and the same actual
executable/cwd/PID354816. Its wrapper failed later during offline binding,
not during native collection. Parent identified the exact mismatch at
`native_before_0.tsv` row98: DVE labels the internal singleton
`gen_parallel_slices[1].active_format.mask_slice` without a range; the
compiled object is vectornode left0/right0, portnode0. The original matcher
accepts a bare singleton only for ports. A fresh offline successor may
accept this exact internal singleton spelling while rejecting bare
multi-bit vectors, type/port swaps, duplicate owners and incomplete arrays.
Preserve the frozen failed verifier and capture; no new DVE run is needed
to diagnose this alias. No exclusion has been applied by this read-only run.

Parent independently read the RVH0 five-stage helper and Tcl entry, then
passed all10 tests in52.881 seconds. Tests execute the real Tcl entry with
controlled GUI stubs, including apply/save/reset/reload/reset, exact native
EL parsing, protected arrays/cause, incomplete reload rejection, and global
configuration failure before exclusion. This is tool evidence, not actual
native qualification. The partition is60 target fields and2794 protected
objects, including38 arrays;2756 is the non-array protected subset.

The full771 actual DVE process PID336508 was independently observed live
at32m54s elapsed and98.3 percent CPU. Its partial report remains ineligible
for final percentages. Existing source/config pins remain frozen.

### Branch720 parent replay and preparation pin rejection

Parent independently passed18 parameter720 tests in14.288 seconds, read
the whole source/native binding implementation, and completed the real CLI
in a separate directory without running EDA:
`operand-parameter720-native-reuse-772-parent-review-20261007-01`.
Audit SHA: `af18df7c4c144bf9b601d82da999c72fd3a0bd4292416c17cee1c89ded6ead0a`.
Candidate EL SHA: `388bd97b786950ee98bfa268f5cb78b3514f1bdf0bc5f0c495d23f273d60228d`,
identical to the independently prepared agent candidate. All720 coordinates
are parameter-false TRUE bodies, currently unhit in the formal772 union.
Only12 queue scopes are retained, with492 protected Branch coordinates;
the other historical707 targets are not inherited. Existing770/771 canonical
ELs contain no Branch directives. This proves reuse eligibility, not current
application or a new official score. Actual denominator accounting and
protected-complement checks remain gates for the next population report.

Parent's fresh RVH0 preparation produced config seal
`8315a67a4fdde2dd4c9dd04078f3c43bc1391aaf3f7aad2131626a5138c7dcfb`
in `rvh0-exception60-native772-parent-prepared-20261007-01`, but its immediate
verify-config rejected a concurrently changed helper source. No DVE session
was launched from that stale seal. Preserve it as rejected preparation;
freeze/review the final helper before preparing a distinct successor.

### Formal773 independent closure and fresh native execution

Parent independently read the completed Sv39 collector, gain and admission
tools; all11 gain/admission tests passed. A separate complete architecture
replay qualified19759 nontrap instructions,1091 checks,8 precise vector
page faults,4 supervisor ECALLs,4096-byte full VRF and4096-byte page-store
protection, with79 matched requests/responses and no scalar mismatch.
Replay: `sv39-fault-alternating-completed-parent-review-20261007-01`,
qualification SHA `5a5cf3f3ba0c678de96c7eb000b4ffd13db11da3f43d72abf1a839f584e066cd`.
Parent actual gain replay in `sv39-fault-alternating-raw772-parent-review-20261007-01`
confirms1258 additional scoped binary Toggle coordinates. Its proposed
four-metric union and scoped gain are byte-identical to the agent products.
Line/Condition/Branch/FSM gains are zero;1258 is not a native percentage.

Parent also executed the complete admission evaluator and checked every
formal773 product, ledger, input/output pin and all6162 OR instances against
`sv39-fault-alternating-offline-admitted-773-agent-20261007-01`.
Manifest SHA: `65710f130e698571f9e17800e57361b0baa2a9d407a02287409797de64f64060`.
Formal773 preserves the exact772 prefix, a unique new VDB and nonduplicate
ELF. No new simulation or RTL edit was used. This is now the independently
reviewed population base; live771 native-report inputs remain unchanged.

The fresh RVH0 V2 helper and new parent-owned background runner passed13
combined tests in57.130 seconds. The runner reuses the mature execution
body in a private namespace, changing only its seal environment key and
binding the reviewed entry/contract/verifier. It rejects unreviewed seals
and restarts; the original runner remains untouched.
Fresh prepare and verify-config both passed with seal
`9fbcd99d5519a4a89178615fdaf9915de4e34f825ceb11393bccb44d9857fae7`.
Parent launched unit `ara-rvh0-exception60-native772-v2-parent-20261007-01.service`
in `rvh0-exception60-native772-v2-parent-prepared-20261007-01`.
Actual DVE PID371695, executable, independent cwd and service cgroup were
checked live. Native execution has a900-second budget and no automatic
retry. The five-stage qualification and population application remain
unproven until actual terminal capture passes. Do not infer new scores.

### Linear ITLB execution and rejected RVH0 native inventory

Parent independently passed21 linear ITLB build/run/collector tests in
2.800 seconds, read the complete collector, and rechecked8595 input pins
against prepared seal
`b5813cbc646a30c1834408684db0bb87af4fa90bd8af7c449bfe7dac7cf1fe71`.
The exact packed189 MMU update projection and six readonly vector-CSR
transactions have separate strict accounting; neither synthetic arch_start
PCs nor normalized summary strings replace architectural PC/value checks.
One fixed600-second simulation was launched as
`ara-itlb-linear772-parent-20261007-01.service`.
Actual simv PID374121, executable, independent cwd, command and ELF loading
were verified. The run directory is
`itlb-asid-exec-linear-old-image-772-agent-20261007-01`.
Automatic terminal qualification is not automatic admission. Its prepared
diagnostic base remains772; any eventual formal successor must rebase the
increment onto the current773 population without changing this frozen run.

The RVH0 V2 native attempt stopped at the first before-inventory with
`Foreign/duplicate full typed object`, before applying any target exclusion.
Preserve the original error/terminal/qualification-reject evidence in the
parent V2 directory. Static/mock tests were insufficient to prove actual
native presentation; inspect the real TSV and compiled inventory before
designing a successor. No repeated DVE attempt or weakened complement
check is authorized merely to obtain a score.

Parent independently passed6 MFPU offline alias tests in2.096 seconds
and reviewed the completed narrow singleton/MDA display adapter. It
continues rejecting unknown display types, bare multi-bit vectors, port
role swaps, reordered dimensions, foreign objects and duplicate ownership.
Actual full788-scope offline replay is in progress in a distinct parent
review directory; no exclusion or new percentage follows from these tests.

### Complete MFPU offline binding and exact RVH0 alias diagnosis

Parent actual full788-scope offline replay completed successfully in
`mfpu272-binding-offline-parent-review-20261007-01`.
Binding SHA: `d9ff0be6713e0f85e3e27bf243ae1232ffc4859a26c32189cf7a4293653d9f48`.
Closure SHA: `20b8c3e3af1da640088a6c7a09d9115e2942252233b1e638939bf9e734b95ae1`.
All272 targets and744 protected child scopes were retained;1652 protected
singleton/ordered-array display aliases were audited. Original directory
pins were rechecked unchanged; the genuine DVE terminal0 and wrapper1
remain distinct. No EDA was replayed and no exclusion was applied. The
next actual five-stage exclusion qualification must bind this completed
receipt, with exact target directions and the entire protected complement.

Parent independently passed6 RVH0 alias tests in4.008 seconds and replayed
the sealed offline evidence JSON exactly. Its first-scope mismatch is only
protected `instr.rvftype.repl`: actual source/compiled type is[14:14] and
DVE displays the bare singleton name. All692 first-scope objects then
match; duplicate count is zero and both arrays match without flattening.
The other four scopes and all later stages were not captured, so the
failed native attempt remains unqualified. Before another native capture,
prepare a source-bound singleton display policy for the full inventory;
reject multi-bit names, alias collisions and any expanded target scope.

The current offline matcher repeatedly scans native names against every
compiled object. A separate indexed successor can reduce this overhead,
but must reproduce the complete788-scope result and retain all negative
identity/complement checks. Do not edit the frozen successful adapter or
replace correctness checks with a sampling shortcut.

### Indexed replay verified; ITLB timeout remains outside the union

Parent read the complete indexed MFPU resolver and independently passed
its5 tests in1.253 seconds. It indexes exact normalized declarations and
candidate name boundaries, then uses the unchanged typed matcher; complete
arrays, duplicates, role mismatches and missing inventory remain rejected.
Parent also ran the full788-scope CLI, reproducing every sealed binding
and all1652 protected alias records exactly, not merely a first-scope sample.
Receipt: `mfpu272-indexed-all788-parent-review-20261007-01.json`, SHA
`65302338ddd9d62e382bb5641f0deba63894febda7bea5900458b3f3e0be608c`.
This permits reuse of the faster resolver for the next native qualification;
it is not an applied exclusion or score improvement.

The linear ITLB run has reached its actual600-second timeout. The unit
terminated with exit1; no candidate VDB entered the formal773 population.
The last complete retirement is atPC0x8000231e, following the leaf-gold
zeroing loop atPC0x80002318, with149946 complete retirement rows followed
by one incomplete final row. Exact reference-prefix alignment and phase
identification are required before calling this a software-cost problem
or an RTL issue. Do not simply increase the timeout or admit partial data.
Inspect the remaining initialization/guard work and preserve every target
access and full-memory check before preparing any cheaper successor.

Parent independently read the Branch720 next-report contract and passed
all22 tests in4.343 seconds. The contract checks exact native directives,
six-stage protection and actual-count gates; simulated fixtures are not
actual DVE counts. Next full-report preparation must explicitly rebind
the current773 population and use real native observations, never infer
integer denominator changes by inverting rounded percentages.

### MFPU five-phase launched; actual Toggle stimulation remains separate

Parent independently passed the sealed MFPU five-phase `check` using
config SHA `810e5ee5f3937adc78be192817c3c79b594e033a9ce2896426298ce6a138dd2e`.
The previously reviewed ten tests also passed. Started the one-shot host
unit `ara-mfpu272-five-phase-parent-20261007-01.service`, with its own
prepared output directory, 5400-second native budget and control-group
lifecycle. Actual DVE PID392416, executable, cwd and active process were
verified. Do not edit its frozen dependencies, restart the output, or
claim a percentage improvement before all five stages qualify.

RVH0 V3 has now terminated unsuccessfully. Native failure is at the
selected saved-EL grammar gate (`Only exact typed Toggle; no other
metrics`), not proof of an RTL failure or successful exclusion. Cleanup
cleared exclusions and saved `cleanup-empty.el`. Preserve this failed
attempt; diagnose actual saved directives against the exact source-bound
target set offline before proposing a successor.

The full771 report also remains unqualified due to the observed
`ex4_expnt_rst[12:0]` target/protected membership conflict. Existing
pack323 owner evidence must resolve the classification without expanding
the exclusion. Formal773 PASS population is available, but no newer
qualified full-population percentage replaces the last770 result yet.

Separate actual-stimulus work targets a reachable ordinary-RVV operand
queue or Dispatcher bit gap. Require source-derived production and
cleanup paths, comparison against current773 hit maps, and independent
Spike checks before authorizing a short VCS test. ITLB successors must
preserve all accesses and full guard checks while reducing software
initialization overhead; neither timeout extension nor a partial VDB is
a substitute for completion. Report real newly hit directions separately
from source-proved denominator exclusions.

### Bulk ITLB reference independently replayed before another simulation

Parent read the complete bulk application, scalar helper and builder,
then independently passed all five builder tests (0.701 seconds).
Actual preflight SHA is
`ea0f3507627a7759ab41e1044d41c0186fd796c7e217fc542db9189d2b280499`.
All bound input hashes and actual ELF PROGBITS/PT_LOAD/BSS constraints
were rechecked. Complete Spike interval contains103572 nontrapping
instructions instead of253120, a149548-instruction reduction, with the
same10966 software checks,16slots,three ASID phases and full64KiB guards.

The first parent replay omitted the mature producer's explicit trapped
ecall expansion and correctly failed the144-thunk-instruction gate:
the nontrapping parser contains only96 arithmetic thunk instructions.
This is a parent invocation issue, not a processor mismatch. Parent then
independently compared all48 raw Spike exception cause/PC records with
the exact expected sequence, expanded those48 ecalls using the reviewed
producer, and passed the complete PTE/CSR/code/guards oracle (103620
expanded instructions,66600 scalar writes,26384 scalar memory accesses).
Do not manufacture trap evidence from handler entries alone. The future
collector must also require the exact fixed-entry/successful-tohost
reference interval, with no arbitrary skipped commit records.

RVH0 V4 is a fresh successor matching the actual saved EL grammar:
41 annotated whole vectors and19 unannotated complete scalar pairs.
The five-scope2854-object complement is retained. Parent read helper,
actual Tcl and negative tests, passed three private-launcher tests,
and passed the actual sealed `verify-config`. Config SHA is
`64d3fa0c75889a848b73b64d4b62968c66ba941510c357a5b48dcfe814b60039`.
Full independent16-test qualification-helper regression is pending;
no new native qualification or official coverage improvement follows
from preparation or launcher tests.

### Full771 independently qualified; bulk ITLB and RVH0 successors started

Parent independently passed all eight full771 owner-adapter tests and
replayed the complete actual offline verifier in
`native-full771-pack-owner-offline-closure-parent-review-20261007-01`.
Qualification SHA is
`5cb90569a4cde0cfaa8dc064269f90cb2eb9c20a88c732fbaf7b615e1b1b29fd`;
closure SHA is
`b26e3f1a721ad71323ac7e4ae699205ea4a4d74578c5fa657e0324307c7ed752`.
Both are exactly equal to the agent's independent output. Existing
c910240 source-qualified48 objects account for all96 selected/reloaded
observer conflicts; no EL coordinates were added, scalar pack and ports
remain protected, and original failed-directory files are unchanged.
Actual raw/applied/reset/reloaded/final checks all passed. Latest qualified
system771 results now supersede770: raw Toggle64.11%, applied/reloaded
Toggle68.89%; FSM70.29% raw and80.64% applied; Line85.21/85.18,
Condition82.10/82.11 and Branch82.95/82.99. Do not attribute this771
percentage to773, or combine raw hit gains with exclusion effects.

Parent passed the complete16 V4 native-helper tests in87.418 seconds,
three launcher tests and actual sealed config verification. Started
`ara-rvh0-exception60-native772-v4-parent-20261007-01.service`;
actual DVE399197 executable/cwd/cgroup verified. The new run must finish
allfive actual stages before RVH0 exclusions can enter a full report.

Parent also read the complete bulk ITLB runner/collector and passed all17
tests in12.566 seconds, including full real-reference replay, raw exception
ledger, initialization dominance and exact773 baseline union checks.
Prepared run seal is
`4518dde9720e387d3d3ce9811b3079d6e230dcf9665e3c1fdf5a63c2b4e690f3`.
Started `ara-itlb-bulk773-parent-20261007-01.service` with unchanged600s
simulation budget, no retry and terminal-only automatic qualification.
Console confirms actual ELF section loading and tracer start. This is
not admission or measured coverage gain; terminal scalar/CSR/PTE/guard,
lifecycle and waveform checks still must pass.

### V4 reload exposed ordering-only rejection; no new native qualification

Actual V4 selected/reset checks completed, but reloaded saved `second.el`
reorders scalar directives to1to0 then0to1 and reorders target objects.
The parser incorrectly required adjacent0to1-first pairs. Native output
therefore rejected at `re_call el --stage reloaded`; later inventories
were not collected. Preserve failure and do not treat this as an RTL
fault, successful qualification, or missing direction evidence.

The next parser must compare exact semantic scope/name/type/checksum and
direction membership, independent of serialization order. Each scalar
still requires exactly one0to1 and one1to0; duplicates, missing directions,
partial vectors, foreign metrics and protected targets remain rejected.
Vector annotations stay bound to the exact following whole-vector item.
Exercise both actual first/second files and valid reordered variants
before any new native attempt, not just the first observed presentation.

One bulk ITLB runtime snapshot confirmed actual simv401599 progressing:
about5min18sec elapsed,35995 complete retirements and110666cycles.
This is not terminal success. The59.1% reference-instruction reduction
does not imply the same wall-time reduction because memory accesses can
dominate runtime. Keep the frozen600s run unchanged; if it times out,
use exact native/reference prefix and measured cycle cost to decide the
next action rather than blindly retrying or extending its deadline.

### V5 semantic ordering checked; bulk ITLB finished within its original budget

Parent reviewed V5 records, actual first/second evidence and Tcl inheritance.
Three semantic tests passed in1.470s, including200 legal scope/object/direction
permutations and strict duplicate/missing/foreign/partial-member negatives.
Two additional tests passed in27.663s: actual reloaded second.el through the
complete host five-stage session, and the real V4 three-stage inventories
with explicitly missing later stages. Reused authorization tests passed
against the new private launcher (3tests,0.013s), and actual sealed config
verification passed. Config SHA:
`8321726a1f6a2d279b64e8fdfcdeb526067bcb005db45a2fca51a793b667d164`.
Started one-shot `ara-rvh0-exception60-native772-v5-parent-20261007-01.service`;
actual DVE409792 executable/cwd/cgroup verified. No population application
or new percentage follows until full real qualification passes.

Bulk ITLB actually completed normally: `simulation-status.json` returncode0,
VCS CPU546.590s, simulation time248625500000fs. Full scalar comparison is
`TERMINAL_TOHOST_MATCH`,103572 matched instructions, mismatchnull and zero
skipped unobservable values. The unit failed only during later automatic
qualification at the inherited CSR lifecycle gate, not at simulation or
the full architectural comparison. This result contradicts any inference
that failed unit status alone means timeout. Preserve the original failure.

Native evidence for the first independent CSR pair:
vstart response118018; vcsr request/response118019; vstart retire118020;
vcsr retire118021. The same ordering occurs in allthree pairs. Opcodes are
0x00802773 and0x00f027f3: read-onlyCSRRS with rs1=x0, distinct rd14/rd15.
They are not consumers of each other's GPR result. A new source-reviewed
offline collector must preserve request/response/TID conservation, exact
word/value alignment and response-before-own-retire, while allowing this
legal issue/retire overlap. Full PTE/CSR/guards/lifecycle/waveform/coverage
checks remain required. No new VCS run, timeout change or RTL edit is needed.

Parent also independently passed all10 full773 Branch720 consumer tests
in0.499s, covering actual native720 bytes, current773 unhit points, nested
Tcl hooks and retained protection. The prepared report stays unlaunched;
avoid an extra full aggregation while new qualifications are still pending.
