# 2026-10-08 原始失败激励修复验收

## 最终结论（2026-10-09）

本轮已确认失败的修复及有限验收完成，停在全量回归之前，等待用户手动
指令。下文保留调试过程中的失败和待验状态；最终状态以本节及所列完整
证据为准。没有宣称所有旧覆盖率用例已在新RTL重跑，也没有合并覆盖率。

| 验收项 | 最终结果 | 证据目录（相对verification/） |
| --- | --- | --- |
| 六项原失败及17项邻接 | 23/23 PASS，全新build04运行；六项检查数1820/2705/160/1075/4229/2294 | `out/failed-repair-acceptance-20261008-06/` |
| mask完整矩阵 | 68场景、65860检查、8224字节独立读回及原生VRF检查PASS；1594239条退休 | `out/masklogical-same-source-native-agent-20261008-01/` |
| 八逻辑跨块边界 | 8场景、8337检查、完整1024字节VRF及1152字节读回/护栏PASS | `out/masklogical-restart8-nativefix-20261008-01/` |
| 原cache完整测试 | 功能PASS：3轮、12288次写、1758次独立读回、9个fence、正常退出0 | `out/cache04-scalar-functional-reaudit-agent-20261008-01/`，原运行`out/system-cache-repair-20261008-04/` |
| 性能防回归 | AXPY2810周期，等于验收基准；23项末退休周期均与build03相同 | acceptance06与acceptance05逐项比较 |

68场景仿真正常退出0，用时4688.94秒，含离线检查总计4753.97秒；597请求/
597响应、零异常、零协议错误、UVM_ERROR/FATAL均为0。四种同源恒等运算
均在实际两路X输入握手下得到正确已知常量，不能把该结果扩大成所有未知值
传播场景均已验证。

cache为固定纯标量ELF，原UVM报告仍有两条要求向量流量的错误
`CVXIF/NO_TRAFFIC`、`VID/NO_TRAFFIC`，不称其为UVM clean。独立后继检查器
仅对该ELF精确认定这两条门槛不适用，验证零向量活动、全部标量读写与正常
终态，并拒绝其他错误；父端10项正负单测通过。原STOPPED日志未修改、
未将其VDB准入覆盖率。

父端完成最终来源核对：四组结果的source/image pins分别1043、596、821、
1284项均与当前文件一致；23项逐例结果与汇总一致，正常退出证据齐全。
build04相对build03只改变lane_sequencer的mask-logical门控，原68/8项程序
仅修复native打印适配，计算场景和独立oracle不缩减。所有本轮后台服务已
结束，没有自动全量测试、综合、提交、推送或主线合并。

## 范围与停止条件

工作区为 `ara_dsa_signoff_integration`。先修复明确失败的原始激励，
再运行有限邻接回归和性能门槛；不自动重启全量回归，不混合旧 RTL
覆盖率。只有原始激励的完整自检和独立检查通过后才能关闭对应问题。
过程记录本身不替代PASS证据，最终验收见首节与相应输出文件。

## 六项功能失败

| 原始激励 | 实测错误和根因 | 本次修复 | 验收范围 |
| --- | --- | --- | --- |
| `vgap76_red16` | VL=63 的宽化规约将一个无效尾元素计入；源消耗进度与归约工作计数混用 | 用源接收计数计算真实输入尾部，不改变中间结果合并的工作计数 | 原始 ELF、完整标量/内存比较和向量检查，不能以 unordered reduction 容差放过精确标量结果错误 |
| `mask_restart` | 非零 vstart 的比较读取错误的旧 mask word，破坏 prestart 位 | packed MaskB 请求从 mask word 起点读取，不使用 lane 数据元素偏移 | 原始 ELF、全部有效位及 prestart/tail、独立原生写回归属 |
| `qbs_canonical` | 故障 QBS 零 VRF 写回却提前更新 EEW，破坏原数据解释 | 保留已有修复：仅成功完成时更新实际目的组的布局元数据 | 原始 160 项版本，不以早期 144 项版本代替；故障零写回、完整快照、重试及普通 RVV 恢复 |
| `vgap101_illegal_segment_store` | 分段 store 用默认 vd=0 检查越界，实际 vs1=v31 回绕并写内存 | 用实际 store 源寄存器 vs1 检查组边界 | 原始 1075 项、两次非法异常、完整寄存器与内存保护检查 |
| `vmemory_emul_r2_boundary_reject` | VILL 与 VL=0 组合漏掉普通访存非法异常 | 普通 load/store 保留 VILL 检查，whole-register 分支仍按架构例外处理 | 原始 4229 项、异常账本及合法恢复，不仅运行通过的子集 |
| `vgap112_sv39_fof` | FOF 标志未传到 PE；第二元素缺页错误产生普通 load trap | 传递标志；抑制架构 trap 时仍向 VLDU 发送内部异常终止描述符以排空前缀 | RAM 内 Sv39 fixture、VL=1/vstart=0、无 FOF trap、完整数据/CSR/独立在飞指令检查 |

FOF 的内部终止描述符和软件可见异常不是同一个概念：前者让 VLDU
停止等待永远不会返回的剩余元素，后者由 dispatcher 的 FOF 语义
决定是否上报。仅传递标志而删除内部终止描述符不能视为完整修复。

## 验收脚本

`run_failed_repair_20261008.py` 先运行上述六项，任一失败停止继续派发；
已经运行的独立用例保留完整结果。全部通过后才运行有限邻接回归。
所有仿真独立目录，原始 ELF 不重编译，源码/镜像/检查器固定哈希。

AXPY 复用 `repaired-aligned-600-20260930-01` 的同一 ELF 和配置，
检查 CVXIF、后端请求完成及 AXI 事务，`total_cycles` 不得超过原
实测 2810。该门槛仅证明这个代表点，不宣称所有程序性能不下降。

独立检查器的负向测试必须拒绝历史失败轨迹；进程退出 0 或单独
出现 SUCCESS 都不能代替完整功能验收。修复镜像 VDB 不加入旧镜像
的 798 项集合。

## 另外四项验收欠项

- `system_gap30_cache`：原始超时，需确认同一 ELF 完整通过。
- `akv_gap35_descriptor`：软件自检通过，独立架构验收仍需闭合。
- `akv_gap46_skew_context`：软件自检通过，独立架构验收仍需闭合。
- `scalar-c910-pattern795`：架构比较已通过，附加内部事件归属尚未闭合。

这四项不是已经确认的四个 RTL bug，但也不能因为程序自检通过就
把缺失的独立证据写成已完成。整体目标结束前仍须处理其验收状态。

## 构建记录

`failed-repair-image-20261008-01` 在补齐失败清单时主动取消，未运行
仿真，保留 `cancelled.json` 和编译日志。后继使用新目录，不覆盖或
复用这个不完整构建。

后继 `failed-repair-image-20261008-02` 已启动宿主机 VCS 编译，服务为
`ara-failed-repair-build-20261008-02.service`，实际 `vcs1` 进程已确认。
`ara-failed-repair-acceptance-20261008-02.service` 在后台等待这个构建
成功和源码哈希校验，随后最多五路运行原始失败点；失败则停止后续
派发，通过后进入有限邻接回归。输出为
`verification/out/failed-repair-acceptance-20261008-02/`。

截至启动时，父端运行的 mask/QBS/memory/调度脚本测试共 32 项通过；
FOF 检查器负责人另行执行新检查器与原 oracle 的 37 项测试通过。
这两项是软件验收工具测试，不是新 RTL 的 PASS 结果。

## 首批实测与脚本修正

build02 编译通过，458 个输入文件一致性校验通过。首批已取得：

| 原始激励 | 完整检查 | 结果 | 总提交轨迹末周期 |
| --- | ---: | --- | ---: |
| `vgap76_red16` | 1820 | PASS，严格标量/向量比较 | 51605，原失败轨迹 51612 |
| `mask_restart` | 2705 | PASS，58822 条标量指令及原生 mask 保留检查 | 见该点 audit.json |
| `vgap101_illegal_segment_store` | 1075 | PASS，完整两阶段非法指令检查 | 33066 |
| `vmemory_emul_r2_boundary_reject` | 4229 | PASS，完整原始边界/异常用例 | 322550 |

第一版调度器在运行 QBS 前错误要求 ELF 必须有 `tohost` 符号。
该应用使用 MMIO EOC，因而未启动这一项。已创建后继
`run_failed_repair_20261008_v2.py`，原脚本和正在运行的其他用例不改。
23 项 ELF 的启动契约已预检：9 项 MMIO、14 项 tohost；stripped AXPY
用固定 ELF SHA 绑定已验证的原启动方式。五项后继脚本测试通过。

后继服务 `ara-failed-repair-acceptance-20261008-03.service` 等待原服务
终止后接续。只复用同一 build/source、已有 PASS 且重新独立验收通过
的结果，不复用失败/不完整结果，不重新仿真已经通过的用例。原输出
不覆盖，后继输出为 `verification/out/failed-repair-acceptance-20261008-03/`。
构建结果复用但不混合不同 RTL 的 VDB。

## Cache 超时补跑

原始 `system_gap30_cache` ELF SHA 为
`37c66165e5499258bb505c6f38431f74e7b19d5bb5e6232973441543b044c8c8`。
旧日志已完成前两轮、第三轮仍有提交进展，不是已确认死锁。
后继 `audit_system_cache_repair.py` 验收全部三轮的 12288 次写入、
1758 次独立公式读回、9 个 fence、完成标志和正常 MMIO 终止；
不把自检 PASS 冒充逐条 Spike 对比。七项检查器测试通过。

`ara-system-cache-repair-20261008-01.service` 已后台排队，只有
`failed-repair-acceptance-20261008-03` 全部 PASS 且服务终止后才补跑。
它使用同一 build02，最多运行 1800 秒，不停止其他任务、不重建 RTL，
结果在 `verification/out/system-cache-repair-20261008-01/`。

## 历史验收欠项核对

完整身份和证据链见 `verification/HISTORICAL_ACCEPTANCE_DEBT_20261008.md`。
两项 AKV 的原 ELF 已有旧镜像完整成功终态，本次独立重验全部已观察
目的组/源数据/保护区/异常记录通过，属于历史功能验收完成，不声称
当前 RTL 对这两个原 ELF 又运行了一次。当前镜像仍执行 AKV 邻接回归。
scalar795 的完整架构比较通过；尚未证明的物理输出到退休关联是附加
诊断，不是已观察到的功能错误。Cache 的完整原 ELF 新镜像补跑仍待
上述队列结束后执行。缺失的 CSR 或全寄存器观测不伪称已经证明。

## 后继验收发现的问题

`failed-repair-acceptance-20261008-03` 已复验前述四项 PASS，另两项不能
依据局部结果宣布通过：

- QBS canonical 原160项自检全部通过，仿真正常结束。原独立检查器却
  硬编码要求 `tohost` 结束，而此 ELF 使用 `0xd0000000` MMIO EOC。
  后继检查器需独立核实结束契约，并继续验证原有故障、排空、重试和
  完整数据证据；不得将160项自检单独作为全部验收。原 FAIL 记录保留。
- FOF 在 `112864500000fs` 触发 CVA6 `issue_read_operands.sv:1078`
  分支操作数未知值断言。原 ELF 的 `0x800027a8` 读取 `sf_prefix[1]`，
  `0x800027be` 与 `0x12345678` 比较，位于断言附近的检查阶段。
  该首元素是必须正确返回的有效数据，不能套用 FOF 缩 VL 后尾元素可
  不确定的规则予以忽略。尚需通过周期级证据确认未知值来源，不能仅
  凭此附近 PC 推定具体队列或写回逻辑为根因。

当前不进入全量回归或覆盖率合并。FOF 探针应聚焦首次加载/异常阶段，
复用原 ELF 与 build02，并记录 AXI 返回、地址描述符、mask、部分结果
队列及 VRF 请求/最终授权，避免重复等待完整自检阶段才观察结果。

QBS 后继离线检查已在
`out/qbs-canonical-repair-v2-audit-20261008-02/receipt.json` 得到 PASS。
除 MMIO 终止外，还修正了 `arch_start.pc` 为监视器零占位字段，以及
门控时钟295个有效边沿不能与主时钟147935周期直接比较的错误假设。
完整性改用绝对时间验证：波形到147950.5ns，与仿真结束一致，最终读
引擎空闲。129请求/129响应、4688字读回、原160项自检、故障排空和
重试均通过；父端复核新检查器13项测试通过。集成后继仍须绑定同一
build02和已完成进程证据，原FAIL报告不覆盖，本条不增加覆盖率准入。

## FOF 有效前缀未知值的实测根因

同一 ELF/build02 的独立有界探针位于
`out/fof-build02-prefix-probe-agent-20261008-01/`。仅捕获54000至56000
附近周期，未强制信号、未初始化寄存器来掩盖问题。原生写口记录为：

| 周期 | 操作 | 实测 |
| ---: | --- | --- |
| 54100 | `vmset.m v0`，编码 `7e002057` | MASKU 写回含有效 mask 位的字节为 X |
| 54170 | FOF 首元素写回 | lane0 数据为 `0x12345678`，低四位 byte-enable 为 X |
| 54172 | FOF 完成 | sequencer 收到完成；之后软件读首元素触发未知操作数断言 |

`vmset.m` 是同源 `vmxnor.mm`。当前 lane 将 mask logical 的 vs2
透传，MASKU 用独立解排列后的 vs1/vs2 重算逻辑函数；初始寄存器为
X时，四态表达式 `~(X ^ X)` 不会利用两路源是同一寄存器这一事实。
然而同源 XNOR 的架构结果必须为1，不依赖原寄存器值。此处证明的是
RTL 四态仿真中的同源恒等关系丢失，不能由 X 直接推断硅上必然出现
同样故障。正确的 AXI 数据已经到达，不能据此修改数据返回路径。

MASKU 修复显式处理四种同源恒等关系：ANDNOT/XOR 为0，ORNOT/XNOR
为1。不同源仍执行原逻辑，原 prestart/tail 合并与握手不变，不增加
流水级。文件冻结 SHA 为
`38427ef23970b7c20b9ae73cdc42f3fe813e6d42dbe51d36d89e120365bd78dd`。
新 `failed-repair-image-20261008-03` 已启动宿主机 VCS 构建；尚不能
把静态修复写成新镜像 PASS。

原FOF完整运行在出现首错后终止，避免等满1800秒；原目录中的
`diagnosed-stop.json` 记录PID、信号、探针和首次错误，原失败不删除。
探针的窗口结束也不算完整架构通过。新镜像仍须重跑原六项和17项
邻接回归；v3调度器35项离线测试通过，没有自动启动全量覆盖回归。

## build03 验收执行

build03 已通过编译及458文件来源检查，相对build02只有上述MASKU
文件改变。`ara-failed-repair-acceptance-20261008-04.service` 已启动，
使用冻结v3 runner和QBS/FOF后继checker，新跑原六项及17项邻接；
没有复用build02的PASS。FOF checker在有效字节仍严格拒绝X，只在有
来源依据的未初始化尾位保留场景使用逐位已知性追踪，15项单测通过。

`ara-system-cache-repair-20261008-02.service` 等待上述验收全部PASS
后，在同一build03补跑原始cache ELF。原cache01随前置失败停止，
未执行仿真，其记录保留。

另一个独立同源mask逻辑矩阵使用build03，输出为
`out/masklogical-same-source-repair-agent-20261008-01/`：68场景、65860
检查点，涵盖四种恒等运算、不同源对照、重启和tail边界；截至启动
时仅声明正在执行，不将预期检查数写为实测PASS。这些有界验收结束
后不自动启动全量测试或DVE合并。

### 原六项在build03的完成证据

acceptance04中red16、mask_restart、QBS canonical、illegal segment
store、memory EMUL r2五项均已PASS。FOF也正常执行至SUCCESS，但
旧checker要求ECALL文本含`tval: 0`，与CVA6的`ex_trace_item.svh`
实际ECALL打印格式不符，故原调度状态保留FAIL，停止后续派发。

后继`audit_fof_repair_v3`不忽略mtval，而核查真实handler的
`csrr t1, mtval`和向异常记录区的store均为0。原始数据离线复核在
`out/fof-build03-complete-reaudit-agent-20261008-01/audit.json`得到
PASS：2294项检查、83732条标量指令、684个定义向量字节、38请求/
38响应、唯一S ECALL、无FOF trap、15项CSR恢复。父端10项后继
checker单测通过。没有再改RTL或重跑FOF。

原六项的功能修复已有build03证据，仍需完成17项邻接/性能回归、
新增同源mask矩阵及cache完整补跑，之后才结束本次修复验收。

acceptance05 已由冻结v4启动，严格重审acceptance04的六项同镜像
完成结果；只对已精确定位的FOF检查器错误采用后继checker，不重跑
六项。六项重审成功才派发17项邻接。cache03等待acceptance05，
cache02在前置检查器失败后退出且没有仿真。v4的24项离线单测通过。
这些后继目录保留各次失败原因，不覆盖旧报告；实际进度以各服务的
`status.json`和对应进程为准。

### 同源矩阵暴露的跨块重启问题

新增矩阵在1800秒终止，不能算通过，也不能只增大超时处理。
原trace最后退休为cycle250566、PC`0x80006bea`，指令
`vmxor.mm v16,v8,v8`（`6e842857`），arch_seq99、VL1024、vstart257。
MASKU在250574/250577/250580分别写出addr64/65/66，没有第四块和
完成记录。它与原六项失败修复分开记录，是新增边界测试发现的欠项。

静态候选根因：lane sequencer先为mask logical的vs1通道设置
`MaskM.vstart=0, vl=4`，函数末尾的通用predication调整却再次将它
覆盖为`vstart=1, vl=3`；此时MaskM是逻辑源vs1，不是普通v0谓词流。
其他源与MASKU仍需要四块，可能造成少一块后的等待。先用同ELF/
build03有界探针确认最终请求与握手，再修改；不修改正在被邻接回归
绑定的RTL，也不把三块输出推定成全部原生请求已经核对。

acceptance05已取得AXPY2810 cycles PASS，与门槛相同；六原点及
已完成邻接均PASS。新增矩阵的未闭环问题仍阻止整个修复目标完成。

### 23项验收结束与cache调度问题

acceptance05现已结束：6项原失败的同build03重审和17项新跑邻接均为
PASS。AXPY任务区间仍为2810周期；其trace末周期3254不是任务耗时。
这23项通过不包含新增68场景mask矩阵，也不代表全量回归已执行。

cache03未启动仿真：前置成功的瞬态systemd服务被回收后，runner将
`LoadState=not-found`直接判成错误，记录`missing acceptance service`。
这是调度脚本的完成状态识别问题，不是cache的RTL失败。旧STOPPED
记录保留；后继须核对23项完整结果、同镜像来源和运行进程，再补跑
原始cache ELF，不把未启动的任务写成通过。

### 跨块重启的周期证据及最小修复

原ELF/build03有界波形位于
`out/masklogical-restart-count-probe-agent-20261008-01/decoded/`，
包含220周期的`cycles.csv`和`receipt.json`。cycle250567四个lane均
接受AluB/MaskB的start0、len4，以及MaskM的start1、len3。三次输入
握手发生在250572/250575/250578；最后cycle250749的issue/commit
计数均剩256、iteration=3、ALU/old-vd valid=1111、MaskM valid=0000，
没有done。这与通用谓词调整覆盖逻辑源请求的静态根因一致。

探针脚本原状态ERROR是将Tcl回显中的错误标记字符串误当成实际错误；
实际BEGIN/END/COMPLETE独立行齐全、窗口准确、VPD有效，已离线解码，
不重复仿真、不覆盖原记录，也不把诊断提前退出算架构PASS。

修复仅在lane sequencer通用MaskM截短条件排除八种mask-logical。
三路源恢复对齐，仍由MASKU按[vstart,vl)合并old-vd。普通谓词读取、
slide专用规则、hazard和流水级均不改。新build04需通过原68场景完整
矩阵、八逻辑精确256边界邻接、23项验收及原cache；通过前不宣称闭环。

build04已编译PASS，和build03逐文件比较仅lane_sequencer.sv变化，
SHA为`65d0e9dc482e4c340de8adcd4f9873138c824e5af8139c6424aed256b96352ce`。
首次构建命令误抄dispatcher SHA，前置检查在编译前拒绝；其FAIL保存在
`failed-repair-image-20261008-04/preflight-wrong-sha.json`，纠正参数后
由04b服务完成唯一实际编译，没有为此修改dispatcher。

当前后台验收目录为：

- `out/failed-repair-acceptance-20261008-06/`：同新镜像全新6+17项，
  不复用旧PASS；v5的24项离线单测通过。
- `out/masklogical-same-source-repair-agent-20261008-02/`：原68场景及
  65860项检查，捕获冷源和重启窗口后继续完整执行，不以探针结束代替PASS。
  预算9000秒，依据实测约390周期/秒及完整场景外推，非已测完整运行时间。
- `out/masklogical-restart8-build04-20261008-01/`：八逻辑各一条，
  VL1024/vstart256，含vs1=v0和合法目的/源别名；8337检查点。
  arch_start的PC为监视器零占位，checker以seq/编码绑定，退休侧核对
  ELF真实PC；父端已跑包含实际记录形状的正负单测。
- `out/system-cache-repair-20261008-04/`：等待fresh23项全部通过后
  执行原cache ELF，旧成功瞬态服务被回收不再导致误拒。

本段仅记录已启动的验收，不将预期场景数写成通过数。各目录status
和对应进程是终态依据；当前没有全量回归、综合或覆盖率合并。

### 修复后波形与native打印环境订正

build04同原ELF的已关闭重启窗口完成离线核对：四lane三路请求均为
start0/len4，四次输入握手在250573/576/579/582，地址64至67完整输出，
cycle250585完成。独立参考核对全部128字节及prestart保持通过。
证据：`out/masklogical-restart-build04-offline-20261008-01/receipt.json`。
这是原卡死点修复证据，不替代完整矩阵的最终验收。

新增八逻辑程序完整计算已通过：八条原生alloc/done、1024字节VRF、
1152字节读回/护栏和printf前checks8337/errors0均核对正确，但其打印
链接到newlib printf而非工程printf_。cycle262693的首个异常来自
`_fstat`中PC0x8000668e的ecall，随后进入未安装的异常向量；这不是
mask算术结果错误。该运行由父端SIGTERM停止，FAIL保留。

静态核查发现68场景ELF也有同样输出依赖，故提前停止这一路，避免
在已知不支持的打印路径上再等完整长运行。仅增加native wrapper引入
common/printf.h，原8项/68项计算源码及检查循环不变；CRT/runtime对象
不变，native链接检查拒绝newlib stdio/syscall/ECALL。后继ELF作为新的
刺激身份记录，不声称原坏打印环境已完整通过。父端7项相关单测通过。

新后台目录：

- `out/masklogical-same-source-native-agent-20261008-01/`，ELF SHA
  `43d5d7b1c9b14a0c73f1cd6ea879164eb74d83f7633e232d7a443f52e9ad259e`；
  保留68场景、65860检查和原独立oracle。
- `out/masklogical-restart8-nativefix-20261008-01/`，ELF SHA
  `a306e117bab7c28967da01ff38b7a23bc21ac1690ac222d84f2e4b674524485b`；
  保留八逻辑和8337检查，Spike预检通过。

两项继续使用build04，不再改RTL、不再编译硬件；23项验收和cache队列
不受此测试打印修正影响。最终通过以新目录完整终态为准。
