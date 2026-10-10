# 历史失败与额外验收欠账清单（2026-10-08）

## 最终状态补记（2026-10-09）

下文保留历史审计时的PENDING和旧镜像分类，不将旧记录回写为新镜像PASS。
最新修复验收见[本轮最终结论](coverage/FAILED_REPAIR_20261008.md)：build04
的六项原失败和17项邻接全部通过；新增mask跨块重启修复已通过68场景完整
矩阵及八逻辑边界测试。cache原始ELF也已完整运行，独立功能审核通过3轮、
12288次写、1758次读回、9个fence及正常退出；原UVM两条向量流量要求对该
纯标量ELF不适用，专项审核保留原STOPPED，不声称UVM clean或准入覆盖率。

旧20+7组对应ELF的历史闭环、两项AKV旧镜像证据及wrong-stimulus分类不变。
scalar物理owner关联和归约fflags的未实测静态风险仍不冒充已确认RTL失败，
也未在本轮新增通过声明。本轮已确认失败清单无剩余未验收项；全量新RTL
回归等待用户人工指令，不由这些有限验收推定已完成。

## 1. 范围与判定规则

工作区：`/home/wangwy/openproject/ara_dsa_signoff_integration`。
本次只读既有 ELF、trace、日志和准入记录，并增加离线 checker/tests；不修改 RTL，不启动 EDA。
父任务的 build02 及原六项失败修复由父任务统一调度，本清单不另起构建。
本次最终整理仅修改此文档；所有 sealed helpers 保持冻结。父端已将cache独立后继service排队，等待23项验收全部PASS及前置服务退出后执行，预算上限1800秒。本任务未检查或改变服务运行状态，不将“已排队”写成“已通过”。

以下路径中的 `out/` 均指 `verification/out/`。状态必须分开理解：

- **CLOSED/旧镜像**：指定 ELF 在指定旧镜像已有足够的后续通过证据。不是当前 RTL 签核，也不删除旧失败记录。
- **CLOSED/观察契约**：原软件 oracle 加上完整已观测架构数据的独立检查通过；不声称观测不到的 CSR 或全 32 个向量寄存器。依据父任务本轮明确的验收范围，不额外要求构造全标量解释器。
- **WRONG_STIMULUS**：原软件/启动环境或期望值不符合原契约。修正后 ELF 或 oracle 的 PASS 单列，不能改写成原 ELF PASS。
- **PENDING/当前 RTL**：仍需在父任务新镜像执行原 ELF；构建启动不等于验收通过。
- **HOLD/非必要诊断**：保留尚未证明的内部关联，不冒充已经证明；该诊断不阻塞本轮实际功能验收。checker/tool/零覆盖增益拒收不计作RTL功能bug。

本轮未新增覆盖率准入、未合并任何 VDB。旧镜像的 798 项不能冒充 build02 的覆盖率。

## 2. 四项额外欠账：已取得的证据

| 项目 | 此刻证据 | 判定和最小下一行动 |
|---|---|---|
| `system_gap30_cache` | 原 ELF SHA `37c66165e549...`；300.111 秒 TIMEOUT；63,828 条退休，最后周期 98,715；三轮写入数 `4096/4096/2441`；读回 `586/586/0` 全正确；失败分支未执行 | **PENDING/父端已排队补跑原ELF**，1800秒上限。冻结checker要求原3轮、12,288次写入、1,758次独立读回及成功终态；前缀正确不等于完整PASS |
| `akv_gap35_descriptor` | 原 ELF SHA `f08781d48f8a...`；旧镜像重试 1199.322 秒正常退出，6,751 checks；26个完整512-byte目的组共13,312字节独立检查；23次非法命令、69次实际trap CSR读回 | **历史验收完成，仅旧镜像已观察架构scope**。原自检及独立gold均PASS。父端本轮以AKV fault/read/onehot邻接回归检查新RTL，不额外要求重跑本原例；不将邻接PASS或旧证据称为本原例的新RTL全内部验收 |
| `akv_gap46_skew_context` | 原 ELF SHA `bb333b09bee3...`；旧镜像重试 2035.076 秒正常退出，3,237 checks；12阶段36,864字节独立检查，另有768次poison读和768次poison写；24次fflags/vstart读回和3次trap | **历史验收完成，仅旧镜像已观察架构scope**。完整phases、tail、seed/source/guard/descriptor均核对，不缩小刺激；新RTL邻接回归与本历史闭环分别记录 |
| `scalar_c910_pattern795` | 原 ELF/Spike 对比11,810条退休、6,104次GPR写、672次FPR写、4,286次标量访存；224组结果/flags/FCSR、675checks；已有VCD核对1,359次物理请求=1,176次正确输出+183次同步flush取消 | **架构功能历史验收完成；物理mapping尚未证明，是非必要诊断**。未发现算术结果错误；不为补此内部关联扩大本轮scope或重复仿真，也不声称已证明全部内部行为 |

本四项功能账本的剩余待办只有cache的完整原例终态；两项AKV及scalar的历史功能验收已有明确证据。新RTL的23项主验收和邻接回归由父端另记，不能由本表推定完成。

### 2.1 Cache：为什么不能直接判死锁

原程序在 M-mode `rvtest_init()` 中做 3 轮：4096 个 64-bit volatile 元素写入，`fence w,r`，每隔 7 个元素读回比较，再执行 `fence rw,rw; fence.i`。
数据公式为 `(round << 32) ^ index ^ 0xfeed1234`，每轮 586 次检查，总计 1758 次。

ELF 虽已 stripped，但可以按执行地址反汇编并逐条绑定退休编码。第三轮关键位置：

- `0x80000242` 计算写入值；`0x80000248` 执行 `sd`；`0x8000024c` 为有限循环回边。
- 已观察最后一次 `sd`：cycle 98713，地址 `0x800062c0`，数据 `0x00000002feed1bbc`，对应 round=2、index=2440。
- 最后退休 cycle 98715、PC `0x80000246`，正在递增下一元素索引。
- 第三轮 index=0 和 2048 分别位于 cycle 81694、95969；最后一段仍有实际进展。
- 前两轮检查计数最终写成 1172，没有执行 `failures++`。两个已完成轮次的三类 fence 均已退休。

因此当前证据支持“300秒预算截断了正常前缀”，不是已测得cache特定状态死锁；trace结束后是否又有等待无法由这个前缀证明。估计剩余本体约2.3万周期，但这不是保证完成时间。父端最终采用1800秒有限上限，以其排队runner为准，不再保留早先600秒建议作为当前执行命令。

原例：`out/system-gap30-20260929-01/results/extra-rvv-system_gap30_cache/tests/rvv_system_gap30_cache/`。
实际旧镜像见该目录 `work/coverage.command.json`：`fp16-repaired-coverage-20260928-02/sim/simv`，不是 Sept30 的固定覆盖镜像。
离线前缀报告：`out/extra-debt-cache-prefix-20261008-01.json`；加强 ELF 编码绑定后的报告使用 `...-02.json`，原报告保留。

### 2.2 AKV：不减少原 oracle，也不添加不存在的观测要求

两项原 ELF 全 SHA：

```text
descriptor f08781d48f8a29a5413850b54af4de7d4c31117bc588934acfd6d46b585df7c2
skew       bb333b09bee3df3280dff94abb0aedb257c8c7ae434396c7c5b604d470ab0051
```

原完成记录分别在：

- `out/akv-gap35-descriptor-budget1800-old-image-717-20261006-02/`
- `out/akv-gap46-skew-context-budget3000-old-image-717-20261006-02/`

两者保留 `FULL_ORIGINAL_ORACLE_PASS_NOT_ADMITTED` 原记录，不能回写历史 TIMEOUT 为 PASS。
旧完成镜像为 `out/repaired-aligned-build-20260930-01/sim/simv`，SHA `2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3`。
两目录各自的`terminal.json`均记录`returncode=0`，耗时分别1199.322263678秒、2035.076214316秒；`manifest.json`绑定上述同一旧image与各自原ELF。每项的`console.log`和`run.vcs.log`均由原oracle检查完整PASS，`commit_trace.csv`及`trace_hart_0.log`用于独立读回、命令/异常和实际CSR检查。验收报告`input_pins`对这五个输入文件逐一给出完整SHA，本次再次核验均一致。

Descriptor独立结果不取DUT输出作为gold：零起算phase24（第25个命令）的前64 halfwords是`0x7700+7*i`，其余目的数据是原seed `0x9000+13*i`。全部26组完整读回；原23次非法命令及3次成功fill/load/release顺序不变。336,803条退休编码与原ELF绑定；23次trap的mepc/mcause/mtval共69次实际读回与原ELF、异常记录逐个绑定。AKV参数校验在引擎中进行，拒绝命令可以先发生后端分配；不套用普通RVV的“非法指令不得分配”门槛。原descriptor程序没有单独分配目的guard区，因此仅声称其完整v8..v11目的组保护，不添称不存在的guard检查。

Skew 新补的独立逐字节检查每个阶段包括：

| 对象 | 每阶段字节 | 检查内容 |
|---|---:|---|
| got | 640 | 512-byte 目的组及前后各64-byte保护区 |
| initial | 640 | 完整 seed 及前后保护区，不与 got 互为 gold |
| source | 1536 | 两代、每代三路，各256-byte；含有效块外的保护字节 |
| descriptor | 128 | 两份64-byte ABI描述符，用独立字段编码和 ELF 地址计算 |
| descriptor_copy | 128 | 同样与独立编码比较，不仅与另一份 DUT 内存互比 |

合计每阶段3072字节，12阶段36,864字节；实际标量 compare loads 为29,184条。phase0/7各三路128-byte poison操作另外核对，后续行载入必须返回 fill 时缓存的数据，不能错误采用已被 poison 的外部值。seed/tail 不是零，不允许宽松忽略。

新增证据：`out/extra-debt-descriptor-readback-20261008-01.json`、`out/extra-debt-skew-readback-20261008-01.json`。
完整已观察契约的本轮验收报告（均PASS、未准入覆盖率）：

- `out/extra-debt-descriptor-observed-acceptance-20261008-01.json`
- `out/extra-debt-skew-observed-acceptance-20261008-01.json`

两份报告由 `verification/coverage/audit_akv_observed_repair.py` 独立重读原完成记录产生，不是仅修改旧状态字符串；`source(name)` / `audit(directory, name)` 可供父runner在新镜像上重用。
原 descriptor trap CSR 证据：`out/akv-budget-pass-native-evidence-review-20261006-02.json`。
原 qualification 审计：`out/akv-budget-pass-qualification-gap-review-20261006-01.json`。

**范围明确**：descriptor 没有命令边界 vl/vtype/vstart/fflags 读回；skew 只有明确的 fflags/vstart 读回，没有 vl/vtype 边界读回。旧运行没有 vector-port CSV，不声称其他向量寄存器未改变。这些缺失如实列出，但按父任务最新要求，不再强加“全标量解释器+全32VRF”作为这两项原已观察架构契约的前置条件。原完整 checks、命令守恒、异常、每字节读回和保护区门槛不变。

### 2.3 Scalar795：HOLD 到底是什么

`out/scalar-c910-pattern795-qualified-v3-parent-20261008-01/failure.json` 的原因是 `Independent compiled PC/issue TID`，不是数值差分失败。

旧 owner checker 将物理完成流与退休参考逐个推进，忽略 CSR flush 周围的取消、重复发射和不退休的物理完成；另一版先处理 flush 再处理同沿 output，也会误报丢失 owner。
新双层离线检查保留完整架构差分，并按实际 operand/op/RM 独立计算物理输出，用 TID 与 flush 优先级追踪物理生命周期。已有波形核对：

- 1359 issues = 1359 requests = 1176 outputs + 183 cancellations；没有遗留 live owner。
- 输出中160 DIV、64 SQRT，全部结果及 flags 通过独立 Fraction/integer-isqrt 数学参考。
- 16次被取消的 SQRT 不能计作已退休 SQRT；同PC重发也不能当作重复退休。
- 物理输出到每个架构退休的完整关联**尚未证明**，不能因为两层各自通过就声称已完成该关联。

直接重查证据：`out/extra-debt-scalar-owner-20261008-01.json`。
原架构证据：`out/scalar-c910-pattern795-qualified-v3-parent-20261008-01/{scalar-comparison.json,architecture-audit.json}`。
原 VCD：`out/scalar-c910-pattern795-qualified-v2-parent-20261008-01/probe.vcd`。
原ELF及独立Spike参考：`out/scalar-c910-pattern795-preflight-agent-20261008-02/{input.elf,spike.trace}`，ELF SHA为`f934c3178402cb5df0a167e36098ce41099d0766903ee61238a12609cfeb1357`。
原运行目录`out/scalar-c910-pattern795-old-image-agent-20261008-01/`的`simulation-status.json`记录正常退出`returncode=0`、`timeout=false`、92.121秒；它本身仅证明仿真退出，功能PASS来自后续原ELF/Spike差分及独立数学/读回检查，不能单凭退出码宣称验收。
本次6个原波形/负向检测单元测试通过，包括改坏结果、TID、flags、未知值、数学参考和未排空 owner 的拒绝。

按父端最终范围，**物理owner→retire mapping是非必要内部诊断，保留“尚未证明”，不阻塞实际功能验收结束**。旧报告的`HOLD`字符串保留原样；它指此关联而非架构数值失败。已有物理数学检查也不代表全部握手场景已覆盖：本例`hold_count=0`、`stall_cycles=0`，以及`tval2/tinst/gva`未观察，均不作额外通过声称。本轮不新增探针、解释器或重跑要求。

### 2.4 精确验收报告索引

以下四份报告均为离线产生的独立证据文件，旧原始日志不修改。报告SHA如下；各报告另含具体输入路径和SHA，功能闭环与VDB准入分别记录。

| Case | `out/`下报告 | 报告SHA-256 |
|---|---|---|
| cache前缀，未完成 | `extra-debt-cache-prefix-20261008-02.json` | `1371a8169b0c68bcf69eb5747a6809dedeb6b23033282d1a5e21e2269cc039f6` |
| descriptor历史观察契约PASS | `extra-debt-descriptor-observed-acceptance-20261008-01.json` | `36c921b75d7fd8b77f256aca91e0018fe5a424f54981e5d3c60e3abf4ef039ca` |
| skew历史观察契约PASS | `extra-debt-skew-observed-acceptance-20261008-01.json` | `c2f1b8cb2e62c4e5a3fc700635586f277cfb6ab5b390bc6efeeb2699173ecfa9` |
| scalar架构/物理数学PASS，mapping不声称 | `extra-debt-scalar-owner-20261008-01.json` | `ee0e2c331a245e106a4b04983d1a6aa188ed31bd4455419fde6cfc3479f65294` |

不得把上述任一旧镜像结果写成“build02完整原例已通过”，不得把`coverage_admitted=false`写成已加入798或新覆盖率。

## 3. 父任务的六项原失败：不得遗漏、不得用邻居代替

| 原例 | 历史失败证据 | 此刻状态 |
|---|---|---|
| `vgap76_red16` | `out/gap76-old-image-20261006-01/results/vgap76_red16/scalar-comparison.json`；f14应为boxed -1，实为boxed0 | PENDING/build02原例；vector checker PASS不抵消标量差分失败 |
| VMSLTU known786 / `mask_restart` | `out/mask-compare-restart-known-preflight786-agent-20261008-01/` 和原失败记录；nonzero vstart 的 prestart mask保持 | PENDING/build02原例 |
| QBS canonical160 / `qbs_canonical` | `out/gap71-canonical779-qbs-positive-preflight-agent-20261008-03/`；160检查中的index60，fault后布局/EEW保护 | PENDING/build02原例；Oct5的144checks PASS不能替代160checks |
| `vgap101_illegal_segment_store` | `out/gap101-register-overflow-failure-sealed-20261006-01.json`；1075checks、7fail，非法segment store越过v31 | PENDING/build02原例；GAP101A PASS不能代替 |
| `vmemory_emul_r2_boundary_reject` | `out/memory-emul-r2-parent-failure-diagnosis-20261006-01.json`；4229checks、22fail，VILL+VL0 load/store预期trap缺失 | PENDING/build02原例 |
| `vgap112_sv39_fof` | `out/gap112-sv39-fof-terminal-audit-741-agent-20261007-01/audit.json`；虽终态TIMEOUT，之前已有真实FOF异常/缩VL不符 | PENDING/build02原例；不能按普通预算超时消掉 |

父任务 runner `verification/coverage/run_failed_repair_20261008.py` 的 `FOCUSED` 已含以上六项。`NEIGHBOURS` 包含 AXPY、Oct5十五项和 `vgap76_red32`，用于防回归，不是对原失败的替代。

父任务后续通报：3项原始FAIL已修复实测PASS，memory r2约第132k退休指令仍在正常推进，QBS/FoF后继修正MMIO启动后待跑。第3节表格保留审计时的历史待验基线；具体新镜像原例PASS对应关系以父runner的逐项结果为准，本离线任务未凭口头数量代填具体case、未误判正在推进的大例为卡死。

## 4. CLOSED：有后续通过证据，不重复算 bug

### 4.1 Oct5修复十五项

证据：`out/gap35-restart-repair-20261005-01/status.json` 的15项全部PASS。更早5项重叠证据在 `out/qbs-fault-layout-repair-20261005-01/status.json`，不能再加成20项。

| 类别 | 原例/后续修复例 | 范围 |
|---|---|---|
| carry/slide | `vgap35_carry_ta`、`vgap35_slide_bound` | 原例459/535checks通过；历史修复闭环，当前build02仍复验 |
| QBS/AKV | `gap71_qbs_fault`、`gap71_qbs_read`、`gap71_akv_fault`、`gap71_akv_read`、`akv_gap73_v1_onehot` | 其中QBS fault是144checks版本；与错误启动版、canonical160分别记录 |
| operand/reduction | `vgap75_ext16_f2`、`vgap75_ext32_f4`、`vgap75_ext64_f2`、`vgap75_ext64_f4`、`vgap75_ext64_f8`、`vgap75_red16`、`vgap75_red32`、`vgap75_red64` | 原修复回归PASS；不等同于gap76_red16 |

### 4.2 717旧审计中已闭合的20组，在798中仍有原ELF

本轮按 ELF SHA 查准入798，以下每组均找到同 SHA 成员。证据链：
`out/historical-nonpass-membership-reconciliation-717-20261006-01/{audit.json,details.json,details.zh.md}` →
`out/gather-war-offline-admitted798-v2-parent-20261008-01/elf-ledger-dedup.json`。

| 项目 | SHA前12位 |
|---|---|
| `akv_gap72_tile_range` | fe94fc92b9a9 |
| `qbs_gap72_fill_abort` | f498e63c84e5 |
| `akv_gap73_v1_onehot` | 5b4c03a5c379 |
| `gap71_qbs_read`正确启动版 | 6ede44b997f3 |
| `csr_gap35_permissions` | 0d4040d4d0fb |
| `qbs_gap35_descriptor` | be97ddb2385a |
| `vpolicy_type_matrix` | 7973e1e2bb94 |
| `vlseg` | eb13e45cc4ca |
| `vl1r` | adb3a5f74318 |
| `trap_state_prereq` | 5776c9851a28 |
| `coverage_fp16_int8_s0` | daa922cd87f0 |
| `coverage_fp16_int8_s1` | 752eeaa77458 |
| `coverage_fp16_int8_s2` | 2ff881b85589 |
| `coverage_fp16_int8_s3` | eeae7306fb79 |
| `coverage_fp16_int8_s4` | faabda5702b2 |
| `coverage_fp16_int8_s5` | 23462c090706 |
| `coverage_fp16_int8_s6` | 4d3bff243879 |
| `coverage_fp16_int8_s7` | 0abd0d92a383 |
| `akv_portability_smoke` | 9f448ed68727 |
| `akv_d256_reuse_smoke` | 7112fb5e2f8a |

另外七组曾因预算或收集问题留下nonPASS，但原ELF在798已有PASS成员：`QBS chain3`（c0390）、`Q6_K`（c0388）、`Q8_0`（c0389）、`operand_e64`（c0387）、`seed509`（c0252）、`narrow-clip-reject-450`、`pure-war-budget900`。以798账本中完整SHA及VDB路径为准，不以目录名中的短散列猜测ELF身份。

## 5. WRONG_STIMULUS / 工具问题：保留来源，不造同名PASS

| 原记录 | 分类、依据 | 后续如何处理 |
|---|---|---|
| `seed1409` 原ELF `2ba5d2fc...` | 后处理插入标量source代码破坏有界index轮换，越界；`out/oob-index-repair-20260927-02/seed1409/{manifest.json,original.S,repair.diff}` | 派生ELF `af040bac...` 的PASS在798；原ELF不改成PASS，不要求RTL为错误软件背书 |
| gap71 QBS read/fault、AKV read/fault旧启动版 | SHA分别 `48ac9a5e78c0`、`fa50150d27e4`、`a353942477db`、`e7ce1bd79215`；closure91/历史审计所指ELF的M初始化hook缺失，MRET到U后访问M CSR | 重新建立正确hook的派生ELF单独验收；正确版本已在Oct5/798对应记录中。旧四项不当作新RTL原例重跑 |
| `vgap35_carry_illegal` `c1bae48ac518` | U-mode写mtvec导致测试环境错误，`audit_historical_timeout_contracts_717.py`及封存原trace | `vgap36`正确M-hook派生版555checks另列；不是原坏ELF通过 |
| AKV column-boundary旧adapter | 把非活动目的元素错误预期为0，实际契约应保留seed；两帧v8[1..63]的126项差异 | 保留原FAIL；修正参考后完整数据检查的派生验收已在后续721/798链中，不得简单忽略tail |
| GAP112 last-RAM刺激 | 访问到`0x80200000`触发TB越界fatal，不是原期待的页故障 | 修订后的Sv39刺激是不同ELF，且暴露真实FOF问题，仍在第3节PENDING |
| gather旧checker | producer编号把SLDU3当成MASKU2，另有非写回store的VL/EEW字段处理错误 | 后继严格checker及gather798准入是独立证据；不是靠放宽数据比较修RTL |
| gap75旧构造/栈问题 | 原程序/构建有问题，修正后operand/reduction原修复回归和gap76需分别区分 | 第4.1节八项PASS保留；gap76_red16仍单独PENDING |
| scheduler intentional-failure fixture | 测试调度器预期失败的负向激励 | 不计RTLbug，不准入PASS覆盖 |
| GAP101A/GAP102 precheck报错 | `out/gap101a-admission-precheck-failure-20261006-01.json`、`out/gap102b-preflight-preoutput-failure-20261006-01.json` | 工具/前置条件失败，不能变成DUTFAIL |
| GAP102 strict candidate | `out/gap102-strict-candidate-717-20261006-02/failure.json`；功能检查通过，因零新增覆盖点被collector拒收 | 功能通过与准入增益不同；不为零增益重复修RTL |
| scalar795早期collector/API/owner错误 | 第2.3节及v2/v3 failure.json | 旧HOLD保留；新增双层证据不伪造完整owner关联 |

本清单覆盖本次历史审计发现的失败家族及其派生身份；不是把所有1865个历史名称都当作待修bug，也不把没有终态的任意目录直接算PASS。

## 6. 离线复核命令（可以运行，不启动EDA）

```bash
cd /home/wangwy/openproject/ara_dsa_signoff_integration
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=verification:verification/coverage:verification/tools/plic-venv/lib/python3.9/site-packages:verification/tools/soc-venv/lib/python3.9/site-packages
python3 -m unittest -v test_audit_extra_acceptance_20261008
```

`audit_extra_acceptance_20261008.py --case cache|descriptor|skew|scalar-owner --run DIR --output NEW.json` 是纯离线工具，要求新输出路径，不覆盖旧证据。其中scalar直接解析已有VCD，不调用会启动EDA转换器的collect入口。测试已通过9项；另6项scalar原波形/负向测试通过。

## 7. 父任务最小验收接口与命令

### 7.1 Cache优先补跑原例

`verification/coverage/audit_system_cache_repair.py` 提供 `source()` 与 `audit(directory)`。必须复制 `source()/input.elf`，保留全SHA，不从当前apps重编同名替代。checker验证原1758checks、3轮完整独立地址/数据读回、9个原fence、完成标记和终态；不要求为了这一个普通标量测试重建镜像。

接口已用7项离线测试验证，包括正向完整fixture、真实旧TIMEOUT拒绝、坏数据/计数/终态、缺失或提前fence，以及纯标量contract。特别注意：本例没有向量请求，合法contract是`requests=0 responses=0`；父runner要在通用`check_contract_log()`要求非零向量请求之前分派到本checker，不能因合法零流量而误判FAIL。

```bash
python3 -m unittest -v test_audit_system_cache_repair
# 仿真正常退出后，由父任务离线执行：
python3 verification/coverage/audit_system_cache_repair.py "$CASEOUT"
```

父端已使用`verification/coverage/run_system_cache_repair_20261008.py`排队，待23项原验收全部PASS及服务终止后，在新独立目录补跑原ELF，1800秒上限。此处不再提供第二套启动命令，以免重复运行；本整理任务未启动该service。父端runner负责新build/source/image/checker绑定、正常进程退出和独立保存结果。

cache原ELF完整SHA为`37c66165e5499258bb505c6f38431f74e7b19d5bb5e6232973441543b044c8c8`。父端已确认同一helper单测7/7 PASS，冻结值：

| 文件（`verification/coverage/`下） | SHA-256 |
|---|---|
| `audit_system_cache_repair.py` | `eddf824e0e54b247a6182fa620141ec569143541956bb7a3883612ac39487d3c` |
| `audit_extra_acceptance_20261008.py` | `95c96ed728d9ac30f38772e70d0ed530e14c2b7d36f139d67879372bf2800045` |
| `test_audit_system_cache_repair.py` | `41eed349092161ac0b4db184ca32c7369bec9eeec3f46afcd0dbd8b1e0fb235b` |

文档最终整理没有更改这些文件。audit返回PASS不代替runner的进程/镜像来源检查；同样，单测PASS不代表原cache程序已在新镜像运行通过。覆盖率稍后按**相同新镜像**单独统计，不并入旧798。

### 7.2 AKV保持原例、观察契约完整

Descriptor和skew的历史原例均已按第2.2节完成闭环，不再作为本轮必须追加仿真的欠账。父端本轮已安排AKV fault/read/onehot新RTL邻接回归；该回归评价新RTL的相应功能，但不冒充两项原ELF在新镜像上的运行记录。

历史验收保留原软件自检、descriptor完整26组或skew完整12阶段的独立gold读回，以及已有的实际CSR/trap/protocol检查。没有新观测时，不增加全32VRF和新标量解释器门槛，不声称缺失CSR或全内部行为已经验证。

```bash
# 纯离线，不运行任何EDA。NAME取akv_gap35_descriptor或akv_gap46_skew_context。
python3 verification/coverage/audit_akv_observed_repair.py \
  --case "$NAME" --run "$CASEOUT" --output "$NEW_REPORT"
```

### 7.3 Scalar795不因诊断HOLD重复消耗仿真

采用本次原ELF/Spike及已有波形独立检查，历史架构功能已通过；物理mapping是非必要诊断，保留未证明，不为它添加重跑或探针要求。父端按实际功能验收结束，本项不因旧collector的HOLD文本继续阻塞。

## 8. 当前交付与后续状态更新原则

- 已新增离线数据checker、负向tests及本inventory；旧证据不改写。
- 798账本用于去重及历史身份，不用于推断当前RTL通过。
- 当前原六项、AXPY性能门槛、Oct5十五项和red32由父任务build02 runner负责。
- 四项额外debt按第2节分别处理：cache已由父端排队，终态待回；两项AKV历史原例已验收完成；scalar历史架构PASS，物理mapping未证明仅作非必要诊断。
- 本轮不扩大scope、不修改sealed helpers，不将内部未观察项包装为已验收；主线23项及新RTL邻接回归的终态由父端负责记录。
- 原例终态返回后，只追加对应新镜像的验收证据；不要用同名、缩小规模或改期望值的PASS消除历史FAIL。
- 本次离线测试合计30项通过：新增数据检查9项、cache验收7项、scalar波形/负向6项、复用AKV目的组及异常检查8项。另已完成两项AKV原完成记录的完整观察契约重验PASS；没有启动新的EDA任务。
