# 关键模块 90% 覆盖率推进计划

## 目标与边界

本计划只针对当前冻结的 RTL 和配置，在唯一验证工作树
`ara_dsa_signoff_integration` 中推进。主要目标是关键模块**可达的行、
条件和分支覆盖率达到 90%**，同时逐项关闭重要状态转换缺口。
全芯片原始覆盖率不承诺都达到 90%；无法证明不可达的点保留为未关闭项。

代码覆盖不能替代指令结果、异常恢复、访存副作用和协议正确性检查。
测试通过、独立检查通过、完整 VDB 和相同编译配置缺一不可。
已知的 carry/vstart 和大偏移 slide 首错继续保留，不因为覆盖率上升而关闭。
本阶段不运行完整 Linux 启动，不更换 RTL，不使用 Verilator 或 URG。

## 验收口径

| 对象 | 目标 | 验收依据 |
| --- | --- | --- |
| Dispatcher、Sequencer、各 lane 操作数队列 | 可达行/条件/分支均至少 90% | 完成的 DVE 原始报告；另列经过审查并实际应用的豁免报告 |
| VLSU、QBS、AKV 主要执行和控制路径 | 可达行/条件/分支均至少 90% | 逐项异常、恢复和形状/类型边界测试，加原始点增量 |
| CSR、Controller、MMU、ITLB、DTLB、PTW | 可达行/条件/分支均至少 90% | 当前 M/S/U、Sv39、PMP0、RVH0 配置对应的测试和源代码证明 |
| 关键 FSM | 可达状态至少 95%，可达转换至少 90% | 分开列状态和转换；DVE FSM 百分比是原生转换统计，不能当成状态比例 |
| 活跃控制与握手信号 | 85% toggle 工作目标 | 需精确限定信号集合；目前全模块 Toggle 只作诊断，不冒充控制信号覆盖 |
| 宽数据/地址通路 | 单列 Toggle 和功能边界 | 不通过无意义翻转追求统一 90%，也不能豁免实际需要的数据位 |

“可达”分母只能来自当前配置下证据充分、经独立审查、原生点身份核准、
并且实际应用成功的 DVE exclusions。静态分析的候选点数不能直接从分母扣掉。
原始结果和豁免后结果必须同时保留。

## 当前起点

最新正式完成集合为 `closure90-current-20261005-01`，654 项 PASS，
checkpoint 为 `coverage_status=COMPLETE`、`aggregate_passed=654`。
原始 ara_tb 行/条件/分支/FSM/Toggle 为
77.21/80.32/77.55/53.98/60.22%。

本批之前的起点为 `gap65-late-fault-runtime-20261004-02` 的 651 项 PASS，
独立完成证据在 `gap65-report-only-recovery-20261005-01/reports`，
原始指标为 77.19/80.31/77.53/53.98/60.21%。

QBS late-fault 新测试已经通过 VCS 和独立检查，实际 DVE 导出已完成；
旧 collector 的最终核验超时，不能直接把集合改成 651 项。
独立、只读恢复流程已完整核验 651 项结果及 19,769 个证据文件，
并完成末尾重新哈希，共 306.1 秒；没有重跑模拟器或 DVE。
旧 collector 失败状态、第一次测试 fixture 错误及其日志原样保留。

模块起点由 `closure_scorecard.py` 读取已完成集合生成，包含精确层级路径。
它是查看工具，不重新授权、修正或接纳任何测试。

```bash
python3 -B verification/coverage/closure_scorecard.py \
  --baseline verification/out/gap65-late-fault-runtime-20261004-02 \
  --completion verification/out/gap65-report-only-recovery-20261005-01/reports \
  --output verification/out/NEW_SCORECARD
```

## 实施顺序

1. **关闭归档问题。** 独立核验真实的 651 项结果，减少同一阶段重复读取
   巨大镜像和历史证据，不跳过内容哈希、集合身份和独立 PASS 检查。
   任何漂移立即拒绝；只有完成 checkpoint 才更新正式数量。
2. **审查可达缺口。** 原始零点必须与当前源码、编译参数和原生 coverage
   shape 对应。每项归类为可达未测、配置不可达、空边界/观察器或暂未证明。
   对观察器和已关闭功能只复用经过审查的精确候选，不新增整模块豁免。
3. **补短的定向测试。** 优先选择能够区分未覆盖决策、具备独立 oracle 的
   场景。准备 warm-DTLB W/D 单独拒绝和 R-only/MXR 组合；普通 RVV 选真正
   缺失的队列转换/掩码边界，不重复已经命中的矩阵。预先核验合法指令、
   数据布局、CSR 和 trap 恢复路径；标准指令先通过冻结 Spike。
4. **并行运行。** 一个兼容的 VCS coverage 镜像，最多八个独立测试并发。
   实际有几个有价值的新 case 就跑几个，不为凑八路复制测试。
   每项按源码规模设置有限时间，不反复扩大 timeout。长任务后台执行，
   启动后确认正常进展，不频繁轮询。
5. **一次汇总。** 新测试只有自检和独立审计都通过才进入 verified 集合。
   复用旧的完整 PASS VDB，仅新增测试执行一次；完成一个批次后导出一次
   DVE，列出原生百分比和每项 diagnostic raw-bit 增量。
6. **按测量调整。** 零增益测试仍可保留为功能证据，但不沿同一路径盲目
   扩 seed。下一批依据剩余精确零点构造。若发现新 bug，保留首错并报告，
   不在覆盖探索中悄悄修改 RTL；修复阶段单独获得指示并建立新镜像证据。

## 第一阶段检查点

| 工作 | 当前状态 | 完成条件 |
| --- | --- | --- |
| 模块级目标清单 | 已实现，正式 651 集合已导出 | 工具测试通过，拒绝未完成集合/报告漂移/失败 ledger |
| QBS late-fault 651 归档 | 已完成 | 651 完整 ledger、原始报告、位图和独立测试证据一致 |
| 已审查的 operand/CSR exclusions | 离线 prepare 超时，未启动 DVE，未应用 | capture 和 report 两个独立 gate 通过，输入 VDB 完全不变 |
| Sv39 warm 权限短测试 | Spike PASS：71 checks，25,295 retired；VCS/汇总 PASS | MMU 两个条件目标、PTW 一个条件目标实测新增 |
| LMUL2 奇数 vd 的 `.vf` 拒绝 | Spike PASS：1815 checks，66,261 retired；VCS/汇总 PASS | Dispatcher 一个行点、一个分支目标实测新增，VRF/trap 独立审计通过 |
| Indexed load 首元素页故障恢复 | Spike PASS：85 checks，24,102 retired；VCS/汇总 PASS | Addrgen 实测新增两个行点、三个条件点、两个分支点 |
| Sequencer/队列下一批 | 依据当前零点选择中 | 具体可达证明、独立 oracle、短测试和实际增量；不猜测异常的到达时序 |

第一阶段结束只是一个可复核的增量检查点，不是全部达到 90% 或 Linux signoff。
若目标尚未达到，报告剩余点及限制，不以豁免或 case 数量替代关闭证据。

## 核验开销与失败保留

651 项集合的原生豁免准备使用新适配器 `run_operand_native_651.py`，
普通 650 项的既有检查不变，另外核验独立完成凭据和特殊 late-fault 行。
20 项适配器测试通过，但实际 prepare 达到 300 秒离线上限，未生成 snapshot，
因此不能签发 capture 许可，也不能扣减分母。失败记录保留在
`verification/out/operand-native-651-prepare-failure-20261005-01/failure.json`。
不自动重试，不扩大时限；这项报告准备不再阻塞新的功能测试。

新的定向批次使用 `run_closure90_batch.py`，只接受上述三项经过封存的草稿，
并且从正式完成的 651 集合出发。每项仿真预算最多 300 秒；历史测试不重跑。
`coverage_hash_session.py` 只在一个进程中复用不可变输入的内容哈希，
不缓存 oracle 结论，不拦截工具执行，输出文件始终重新读取。
阶段结束仍对所有缓存输入重新读取内容、计算 SHA256 并检查文件身份。
只有末尾核验通过后才发布该阶段的完成记录。

准备或仿真失败不修改已有集合，不自动将失败的 VDB 纳入结果。
新测试的覆盖增量以实际 DVE 导出和原始位图为准；预测的目标点不是已命中证据。

## 后台批次与查看方式

第一批已组合为 `verification/out/closure90-selection-20261005-02.json`，
后台 service 为 `ara-coverage-closure90-current-20261005-01.service`，
输出为 `verification/out/closure90-current-20261005-01`。
流程是完整 checked prepare、最多八路的 scheduler（本批只有三项）、
逐项独立审计、PASS-only DVE 汇总及无缓存末尾核验。
本批开启独立 vector trace，非法 `.vf` 的运行后审计还检查实际 VRF 字节、
禁止非法请求进入向量后端、合法恢复及 trap/CSR 快照，不能只依赖 PASS 文本。

在验证工作树中查看：

```bash
./vstatus jobs closure90
./vstatus log closure90
```

准备中不代表仿真已开始；`coverage: COMPLETE` 和实际 `aggregate_passed`
才表示本批汇总完成。该完成状态仍不是关键模块全部达到 90%。
39 项 batch/cache-stage 小夹具测试通过，另有 34 项哈希会话和 11 项状态查询测试。

本批正式完成后，汇总末尾无缓存核验 18,448 个不可变输入文件，耗时
507.3 秒，所有文件重新哈希通过。实际新增的原始位合计为行 19、条件 22、
分支 19、FSM 0；这些原始位不能换算成等数量的 DVE 百分点。
精确批次增量见 `per-case-gains.json` 和 `raw-bitmap-delta.json`，模块原生
百分比见 `closure90-scorecard-654-20261005-01/scorecard.md`。

## 源码缺口清单

`closure_point_inventory.py` 从已经完成的集合和冻结 design shape 中提取关键
模块及其子模块的原始零点，输出 `inventory.json` 和 `zeros.csv`。每条保留
层级、指标 checksum、原生 ID、raw index、条件 truth vector、源码和片段，
并重新核验读取的报告、shape 和源码。它不重新跑历史 VDB，也不重新接纳测试。

清单仅用于诊断：branch/condition 的组内倒序位置不是原生 DVE 豁免资格；
所有点初始为 UNREVIEWED。空边界、已关闭参数和未命中的实际逻辑不能混为一类，
工具不会从分母扣点。17 项布局、身份、checksum 继承和拒绝夹具已通过。

```bash
python3 -B verification/coverage/closure_point_inventory.py \
  --baseline verification/out/COMPLETED_BATCH \
  --source-manifest verification/out/repaired-aligned-build-20260930-01/build-source-pins.json \
  --output verification/out/NEW_ZERO_INVENTORY
```

独立恢复的 651 集合还需要 `--completion` 指向其完成凭据目录。
新的正式集合完成后再生成对应清单，不能使用未完成汇总预测后的零点。
654 项源码清单在 `closure90-zero-inventory-654-20261005-01`；对缺少
per-instance checksum 的继承布局和未映射空边界另列 `unmapped_zeros`，
不猜测点身份，不丢弃未映射零点，不据此申请豁免。

## 后续精确条件目标

独立静态审查重新检查了正式 651 位图，确认以下 31 个原始条件位仍为零，
相关 16 份源码与冻结镜像一致。这些是下一批候选，不是已经获得的 DVE 增量。
等第一批实测完成后，要再次核对零点是否仍存在。

| 候选场景 | 当前零位 | 必须满足的条件与独立检查 |
| --- | ---: | --- |
| QBS/AKV 自定义读取的 Sv39 冷翻译与成功返回 | 两个 reader 各 8 位 | 实际进入 S/Sv39，非恒等映射；检查 MMU 请求、等待和译后 AR，以及独立数值/复制结果、PTE/data guard；仅设 MPRV 不足 |
| AKV FULL descriptor 的单项 stride/base 拒绝 | 6 位 | 使用 v1 FULL，逐项只违反一个 Q/K/V 奇数 stride 或 base 条件；精确非法 trap、无 payload/VRF 副作用、合法恢复；V2 前置 alignment 拒绝不能替代 |
| QBS/AKV payload 真实 Sv39 页故障与重试 | 两个 reader 各 3 位 | descriptor 合法，只有 payload PTE 无效；检查 cause=13、EPC/TVAL、禁止故障范围 AR/提交，修 PTE 与 sfence 后恢复 |
| QBS FILL 故障排空与 context 清理 | 2 位 | FILL 后续 payload access fault；检查 fault-done、abort、context 失效、禁止旧 REUSE、重填后数值正确 |
| AKV ready context 的 refill 越界 | 1 位 | context/version 均匹配，只有 tile_start 超出 kv_length；必须命中 TILE_RANGE 而非 CONTEXT 拒绝，无 payload 请求并可恢复 |

原生定位：两个 `i_read_engine` 的 C13/C44/C57/C60/C63，页故障的
C63/C93/C95；AKV engine C47 one-hot、C59(001)；QBS engine C150(101/111)。
原生 condreg truth vector 和 diagnostic raw index 必须连同 definition checksum
一起核对，不用源代码行号直接猜原始位号。

不能作为激励目标或随意豁免的例子：前置 validation 已禁止的 QBS context/profile/
layout/M 组合；`vd>30 && !vd[0]` 这种 Boolean 不可能组合；被 Dispatcher 更早
拦截的 engine alignment 场景。尚未证明 profile 一致可达的其他仲裁零位继续保留。

## 第二阶段后台批次

`closure91-current-20261005-01` 从正式 654 项集合出发，选用 gap71/72/73
各自 `20261005-05` 封存的预检。七项新测试分别为 QBS/AKV 的 S/Sv39
成功读取和 payload 页故障恢复、QBS FILL 故障清理、AKV refill 越界清理，
以及 AKV v1 FULL 六种独立 stride/base 错误。软件参考通过不代表 custom
指令已由 Spike 执行；custom 的功能证据必须来自实际 VCS 请求、响应、
异常、VRF 字节和性能记录。

新运行器 `run_closure91_batch.py` 的 compose 只封存身份和新预检，明确
`full_admission_deferred=true`、`admission_claimed=false`。正式 prepare 和
汇总仍完整检查历史 PASS 和输入，并在阶段末尾无缓存重哈希。每项仿真
上限 300 秒，最多八路并行，本批只有七项，不复制测试凑并发数。

独立审查发现新 AKV 检查器曾接受完成之后下一周期的 VRF 写。现已记录
完成周期，拒绝后续周期写入，保留 monitor 在同周期先打印完成、再打印
最后写入的合法顺序。两项回归夹具覆盖拒绝与接受；这是检查器修正，
不是 RTL 修改。封存版本的预检和独立回放均已通过。

首批 service 已结束，七项均在 300 秒上限超时；正式 PASS 总数仍为 654，
汇总位图没有增长。超时 VDB 不作为通过证据。
只有批次 checkpoint 的 `coverage_status=COMPLETE` 才可更新正式总数。
新的百分比、实际目标命中和未通过项目以该批次完成报告为准。

```bash
./vstatus jobs closure91
tail -n 40 verification/out/closure91-service-20261005-01.log
```

本批复用历史 PASS VDB，结束后自动进行独立检查和一次 DVE 汇总。
源码候选豁免仍未完成原生资格核准和实际应用，不能从分母扣减。

### 超时根因检查与单点恢复

四项 gap71 的 DUT trace 与链接后 ELF 共同确认启动错误：空的
`rvtest_init` 未设置 MPP，CRT 的 MRET 进入 U-mode。`main` 读取
`mstatus` 立即触发非法指令；CRT 留下的无效 `mtvec` 随后造成重复
取指访问异常。这四项尚未执行 custom 指令，不能归为 QBS/AKV 错误。

仅在 gap71 的 DUT 启动 hook 中设置 MPP=M 和实际 trap handler，
软件参考的启动路径保持不变。链接后审计新增 hook 机器码、异常入口
地址以及 CRT 在 MRET 前调用 hook 的检查。未修改 RTL、共享 CRT
或仿真超时。`gap71-custom-preflight-20261005-06` 的 QBS read
软件参考与静态审计通过，但不是 DUT 功能通过。先单项重跑确认根因，
其余三项 gap72/73 根据已有逐周期 trace 判断进度，不盲目扩大超时。

gap72/73 的末尾 trace 显示正在执行有界的内存比较、复制或 printf，
没有未完成的后端请求。300 秒截断时退休指令数分别为 QBS 82,306、
AKV 84,457 和 AKV v1 one-hot 90,004；不能将这些数当完整测试长度。
gap73 的 printf 已消耗 34,468 条指令，约占留存退休指令的 38.3%。
后续减少日志/重复遍历时必须保留每阶段全字节检查，不以抽样或可抵消
checksum 替代；未测得完成前不外推成 PASS。

gap72 检查器另有与超时无关的时间窗口错误：QBS 写回可早于接口握手，
AKV LOAD 的写回可晚于 early response。现按 `arch_seq/VID` 对齐的
backend allocation/completion 验证写回，拒绝未分配、重复完成以及
完成之后的写入，仅允许 monitor 同周期先打印 done 的合法顺序。
完整 VRF 数值、异常零写、源寄存器、尾部和 CSR 检查保持不变。
另要求无写回命令仍具备分配/完成证据，拒绝未绑定的 custom 事件、
额外 backend group、custom VID 提前复用和完成元数据漂移。
26 项单测通过；两项旧部分 trace 的生命周期回放通过不是完整 DUT
测试通过，因此尚不增加正式覆盖率。

启动修正后的单点后台任务为 `closure91-current-20261005-02`，
查询 `./vstatus jobs closure91`；旧七项超时凭据通过
`./vstatus jobs closure91-timeout` 保留。后台先完整核验历史输入，再
运行单项 `gap71_qbs_read`，仍复用冻结 RTL/VCS 镜像与 300 秒上限。

原生豁免离线适配器的 56 项单测已通过，但一次真实 654 prepare 在
建立输入清单时拒绝了历史编译依赖中的 `../` 路径。源集合确有工具链
`bin/../include` 和源码相对包含路径；失败发生在全量准入之前，不是
RTL 错误，也没有生成有效 snapshot、启动 DVE 或应用任何 exclusion。
拒绝凭据保存在
`gap74-native654-capture-20261005-01.offline/rejected.json`。
不覆盖这个失败、不复用部分产物、不重复运行同一失败适配器。
后续需为合法依赖别名建立保留路径语义、身份检查和末尾内容核验的
新适配器，经过独立测试审查后才能再准备原生点资格核准。

## 超时修复重跑（closure92）

closure91 的修正启动单点仍在 300 秒时被软件比较循环截断，已完成两次
QBS/Sv39 命令但没有最终 PASS。新增的 `run_closure92_batch.py` 保留旧
运行器，仍严格准入同一正式 654 集合；只有七项新测试显式封存 1,800
秒预算。无需重编译 VCS/RTL，不删除检查、不减少测试规模。既有 654
的预算和历史准入要求保持不变。

gap71 也通过真实 trace 确认原 CVX 握手区间不适合作为 VRF 写回区间。
gap71/72 现在复用 `custom_backend_lifetime.py` 检查，补齐无写回命令
生命周期、未绑定事件和同周期完成处理。数值/异常/完整内存/CSR 检查
不变。详见 `GAP71_73_REPAIR.md`。

新预检：gap71 `20261005-08`、gap72 `20261005-07`、gap73 `20261005-07`；
全部通过 host/软件 Spike（适用时）及静态/检查器验收，但不代表 DUT
通过。新运行器 68 项单测、原 closure91 68 项单测通过。

```bash
./vstatus jobs closure92
tail -n 30 verification/out/closure92-service-20261005-01.log
```

新批次使用独立输出 `closure92-current-20261005-01`，完成后独立验收
通过项，再自动 DVE 汇总。没有最终 checkpoint 之前，正式仍为 654。
