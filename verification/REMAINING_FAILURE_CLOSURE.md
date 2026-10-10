# 历史失败闭环记录

## 范围

工作树为 `ara_dsa_signoff_integration`。本轮处理
`out/batch-exploration-20260926-04/checkpoint.json` 中的 15 项未通过记录，
不改写原记录，不把最近覆盖率任务的 18 项历史超时混入本表。
产品工作树 `ara_dsa` 本轮未修改。

| 类别 | 原始记录 | 当前处理 |
| --- | --- | --- |
| control-cross 停顿 | 701、704、707、709、712、716 | 非法 EW128 处理修复后，原 ELF 全部 PASS |
| load/store/slide 停顿 | 1417 | SLDU 无源 slide 误消费修复后，原 ELF PASS |
| 首错 | 1402 | 部分异常写回严格比较补齐，原 ELF PASS |
| 向量比较不完整 | 1401、1406、1420 | 异常维护写回证明补齐，原 ELF 全部 PASS |
| 基础设施错误 | 1409、1410、1412 | 修复破坏索引的插桩，三个派生 ELF PASS；原失败记录保留 |
| 定向测试超时 | vlsseg | 原 ELF 已完成并 PASS |

当前所选 15 项已完成分类闭环：12 项原 ELF 通过，3 项激励修复后的派生 ELF
通过。不等于原 15 个 ELF 全部通过，也不等于整个设计完成 signoff。
新功能 RTL 的代码覆盖率尚未收集，不能将这些非覆盖率镜像结果并入旧 VDB。
以下保留根因调查和验证推进记录，最终结果见文末表格。

## Seed1417：无源 slide 错误消费后续归约输入

### 指令及静态逻辑

原始程序在 SEW=32、LMUL=mf2、VL=1、vstart=0 下执行：

```asm
vslide1up.vx v13, v23, s6, v0.t
vredand.vs   v20, v10, v25
```

第一条只向元素 0 写入标量。`lane_sequencer.sv` 的
`slide_up_source_empty` 正确禁止了其向量源操作数请求，允许后续归约先把
数据送入 SLDU 输入缓冲。`sldu.sv` 的 FIRST_WORD 状态也允许无源推进，
但旧的结束处理仍无条件拉高输入 ready。这两个行为不一致。

### 原镜像证据

冻结的原 ELF 位于：
`out/batch-exploration-20260926-03/cases/load_store_slide-coverage300-seed1417-0166db9e7196/tests/ara_dsa_rvv1_load_store_slide_coverage300_0/input.elf`。

复用原 VCS 镜像和已有探针，仅把无提交看门狗缩短到 3000 周期。
详细日志位于 `out/remaining15-seed1417-slide-probe-20260927-01/run.vcs.log`。
下表为日志的仿真时间戳，不是程序周期计数器：

| 时间戳 | 观察 |
| --- | --- |
| 50910000 | slide vid0 接收，VL=1、masked、scalar=1 |
| 50930000 | 四 lane 接收归约 vid1 |
| 50970000 | 四 lane 的归约发送 valid/ready 均为 1，数据进入 SLDU 缓冲 |
| 50980000 | 当前仍是 slide vid0；输入 valid=1111、ready=1111，误消费归约数据 |
| 50990000 | 当前切换到归约 vid1，输入已为空；lane 均等待归约返回 |

因此这是数据握手丢失造成的死锁，不是内存响应慢或看门狗过短。

### 修改及验证边界

将现有 scalar-only 判断抽成一个信号，同时用于无源推进和输入消费门控。
只禁止 scalar-only FIRST_WORD 消费输入，不增加队列、流水级或全局串行化。
加入验证断言，确保该状态下不能消费输入。

必须先通过原 seed1417 的完整 Spike 标量/向量比较，再通过 VL=1/2、
不同 SEW 和 mask 的定向测试及既有 slide/reduction 回归。
AXPY 使用冻结的同一 ELF，对照原 2810 cycles 检查性能。
修复候选已经写入并不等于上述测试已经通过；最终状态以新目录的独立报告为准。

## Control6：e64 扩宽漏报 illegal，EW128 进入后端

### 首因与原始证据

六项来自 batch04 checkpoint 的复用记录，不是本轮重新仿真。
其原镜像均为 `out/seed509-fix-20260926-01/sim/simv`。
701/704/707/709/712 的 artifact 在 batch02，716 在 batch03：

```text
out/batch-exploration-20260926-02/cases/short_control_cross-coverage300-seed701-e1da62ce6e6a/tests/ara_dsa_rvv1_short_control_cross_coverage300_0/
out/batch-exploration-20260926-02/cases/short_control_cross-coverage300-seed704-e1da62ce6e6a/tests/ara_dsa_rvv1_short_control_cross_coverage300_0/
out/batch-exploration-20260926-02/cases/short_control_cross-coverage300-seed707-e1da62ce6e6a/tests/ara_dsa_rvv1_short_control_cross_coverage300_0/
out/batch-exploration-20260926-02/cases/short_control_cross-coverage300-seed709-e1da62ce6e6a/tests/ara_dsa_rvv1_short_control_cross_coverage300_0/
out/batch-exploration-20260926-02/cases/short_control_cross-coverage300-seed712-e1da62ce6e6a/tests/ara_dsa_rvv1_short_control_cross_coverage300_0/
out/batch-exploration-20260926-03/cases/short_control_cross-coverage300-seed716-e1da62ce6e6a/tests/ara_dsa_rvv1_short_control_cross_coverage300_0/
```

以下文件名均相对于各自 artifact，行号为从 1 开始的文本行号。
Spike 所列行为 handler 读取 mepc，紧接下一行读取 mcause=2。
RTL 所列行为非法 EW128 的首次分配，不一定是原算术 uop，可能已是维护 uop。

| Seed | 首因 PC / encoding | 指令及配置，vstart 均为 0 | Spike mepc/cause | RTL EW128 首次分配 |
| --- | --- | --- | --- | --- |
| 701 | 8000060c / c2440e57 | vwredsumu.vs v28,v4,v8; e64,m2,VL24 | spike_commit.log:5203/5204 | ara_vector_trace.csv:4176, cycle16652, arch209 |
| 704 | 80000520 / 4b441857 | vfwcvt.xu.f.v v16,v20; e64,m4,VL2 | spike_commit.log:428/429 | ara_vector_trace.csv:579, cycle1474, arch36 |
| 707 | 800004e0 / 49f79e57 | vfwcvt.rtz.x.f.v v28,v31,v0.t; e64,m1,VL16 | spike_commit.log:410/411 | ara_vector_trace.csv:579, cycle1419, arch36 |
| 709 | 80000598 / cfc91457 | vfwredosum.vs v8,v28,v18; e64,m4,VL57 | spike_commit.log:550/551 | ara_vector_trace.csv:783, cycle2254, arch45 |
| 712 | 800004d2 / 4b051c57 | vfwcvt.f.xu.v v24,v16; e64,m4,VL34 | spike_commit.log:508/509 | ara_vector_trace.csv:579, cycle1927, arch37 |
| 716 | 8000062c / 48879857 | vfwcvt.rtz.x.f.v v16,v8,v0.t; e64,m4,VL12 | spike_commit.log:965/966 | ara_vector_trace.csv:4511, cycle6144, arch245 |

原始 `run.vcs.log` 中 701 的第115行、其余五项的第43行均报告
100000 cycles 无 architectural/backend progress。并非墙钟不足。
`commit_comparison.json` 给出了上述首个分歧，704 为 Spike trap handler 前的 PREFIX。
不能用最终结果分类 RTL_STALL 掩盖更早的非法指令分歧。

### 传播机制与修复范围

合法的 CSR SEW64 经 `vsew.next()` 得到内部 EW128。
OPIVV 的 widening reduction 路径没有目的宽度上限检查；FP 路径原检查
`csr_vtype_q.vsew` 和 `ara_req.eew_vs2`，遗漏扩宽后的目的 `ara_req.vtype.vsew`。
因此这些是合法 opcode 在不支持的有效宽度下缺少 trap，不是 vill 配置问题。

- 704/707/712/716：VMFPU 的 `1 << (EW64-vsew)` issue/process 元素计数为0，
  不能正常消耗指令；`ara_pkg::be()` 没有 EW128 分支。
  704/712/716 的 write trace 出现 `be=xx`，707 为 `00`。
  716 的后续 store 已在 cycle6257 完成；`csrr vl` 等待的是前面的转换，不是 B-response。
- 701：`ara_vector_trace.csv:4212`，cycle16678 把 seed v8 转为 EW128；
  后面的合法 vasubu 在 arch218 的 v8 reshuffle 后不能完成。
- 709：`ara_vector_trace.csv:784`，cycle2255 把 seed v18 转为 EW128；
  后面的合法 compare 在 cycle2820 再转换 v18 时停止。
  这两项的精确 SLDU 内部卡点没有本轮波形证明，但其更早的非法宽度和错误布局维护已实测。

`hardware/src/ara_dispatcher.sv` 在公共 illegal handler 前增加：

```systemverilog
if (ara_req_valid && ara_req.use_vd &&
    int'(ara_req.vtype.vsew) > int'(EW64))
  illegal_insn = 1'b1;
```

利用既有非法异常路径取消请求，先于 reshuffle、布局更新和零 VL 快速返回。
不按 `cvt_resize` 分类，因为该字段复用于归约 neutral 编码，且部分 FP widening
arithmetic 不使用 CVT_WIDE。合法 INT8/FP16 及 FP32/64 转换不受此上限影响。
两项 FOR_VERIFY 断言检查有效 backend 目的宽度和有效 EEW notebook 项均不超过 EW64。
RTL 已冻结，未修改 VMFPU、SLDU、checker 或 Makefrag；SLDU 修复由主线程持有。

### 新定向测试与当前验证结果

新增 `apps/riscv-tests/isa/rv64uv/vew64_widen_illegal.c`，使用六条原始 encoding。
每条先在原 e64/LMUL/VL 下检查一次 precise illegal trap，再以 e32/VL2 执行同一
encoding，检查精确数值、无额外 trap、fflags/vstart 以及首个目的物理寄存器的保持。
trap handler 保存其使用的 t0/t1；非法检查覆盖 cause、mepc、mtval 和计数。
本测试不声称逐一检查目的组内所有物理寄存器；backend/布局断言补充这部分防护。

独立构建及 Spike 证据目录：`out/control6-ew64-unit-20260927-01/`。
未调用 make，runtime 在新目录单独编译，未写共享 apps 产物。

- LLVM22 构建 `vew64_widen_illegal.elf`，使用 `link_sim_2m.ld`。
- Spike ISA：`rv64gcv_zvfh_zvl1024b`，60秒上限，实际正常退出0。
- `logs/spike.stdout`：`6 illegal + 6 legal checks, traps=6`，随后 `PASSED`。
- `commands.json` 保存完整编译/Spike命令；`source.before.json` 与 `source.after.json`
  相等；`result.json` 状态为 `PASS_SPIKE_ONLY`，不是 RTL PASS。
- Ara ELF SHA256：`cf4d1ec8296dd4f05251476cc3d9d515fdacef3785f73d58fe2d5c078a3f1305`。

Spike 使用同一冻结 C 源码、独立 benchmark runtime 的 golden ELF；Ara ELF 尚未运行。
待主线程统一 VCS build 后执行新定向 ELF 和六个原始 frozen ELF 的严格比较，
才能更新 closure 状态。此处未启动 RTL 仿真，也未宣称六个完整随机流已经闭环。

## 比较工具修复

新比较器不再把所有 load 异常写回一概视为未完成；只接收有严格证据的
首元素未对齐异常：内部请求全部完成、没有部分架构 load 效果、全部写回
字节已知且与异常前相同，同时异常处理程序中经标量比较确认 cause、mepc、
mtval。未知字节、重复写回或部分完成的 load 仍不走此放行条件。

归档日志用新比较器重比后，1406、1420 达到标量 `TERMINAL_MATCH` 和向量
`PASS`。这是旧镜像日志的重新检查，不是新 RTL 的实测结果。
1401 尚有 16 个未知字节来源未闭合；1402 必须完整检查部分完成 load 的
vstart、异常 CSR 和各字段写回，不能跳过 Spike 的部分提交行。

参考执行失败或超时现在先终止完整比较，保留 RTL 独立终态。
这防止解析异常重试产生的 GB 级日志耗尽外层预算，不会把超时变成 PASS。
主线程独立运行比较工具 76 项单测通过；后台调度脚本 19 项单测通过。

## 新 RTL 验证安排

独立镜像 `out/remaining15-image-20260927-01/` 已编译完成，
457 个编译输入的前后哈希一致，编译选项与 seed509 镜像一致。
相对于该参考镜像，只修改 `sldu.sv` 和 `ara_dispatcher.sv`。

服务 `ara-remaining15-validation-20260927-01.service` 已启动，
目录为 `out/remaining15-validation-20260927-01/`。执行顺序为：

1. 原 seed1417 ELF，完整标量、向量及独立审计。
2. 六个原 control ELF，最多五路并行。
3. 两个新增定向、三个既有 slide/reduction 定向、AXPY 周期门槛和原 vlsseg。
4. 原 1406、1420，用新比较器和新镜像重新验证。

全部输入和工具已冻结；任一失败或哈希漂移都会停止后续派发。
vlsseg 使用原 ELF、900 秒外层上限；不是更改程序来绕过超时。
最后即使所有已选项通过，调度器也只声明 `SELECTED_PASS`，
不把 1401、1402 和三个越界/异常重试记录伪装成全部闭环。
执行结果以目录中的 `checkpoint.json`、各阶段 `status.json` 和
`verdicts/` 为准；这里的启动记录不代表测试已经通过。

### 已返回的实测结果

`results/seed1417/` 已 PASS：同一 ELF，标量 `TERMINAL_MATCH`，
2720 条提交匹配，236 条向量写回指令比较通过，后端 398/398 微操作完成，
独立审计通过，VCS 墙钟 24.626 秒。这闭合原 seed1417 的死锁，
但不代替其余定向及性能回归。

六个 control 原 ELF（701、704、707、709、712、716）随后也在新 RTL 上全部
通过严格比较和独立审计。至此 7 项历史 RTL_STALL 的原始程序已完成闭环。

1401 的 16 个未知字节已补充独立保存性证明：实际写回历史表明它们是
`v20[0..15]`，异常维护前后均为已知零；结合其余字节，共 256/256 字节保持。
该证明不清除通用 unknown mask，详见 `SEED1401_FAULT_ANALYSIS.md`。
异常时刻 vstart 的观察和完整比较器集成仍需检查，尚未据此授予整例 PASS。

两个新增定向、三个既有 slide/reduction 定向已经通过新 RTL 回归。
AXPY 同一 ELF 的周期为 2810 -> 2810，无周期退化。

另启动独立服务 `ara-fault-vstart-20260927-01.service`，目录
`out/fault-vstart-20260927-01/`。它只在上述功能 RTL 外增加 bind 探针，
编译后顺序重放原 1401、1402 ELF，记录异常响应与下一拍实际 vstart。
脚本不修改当前回归的任何输入；`PROBES_CAPTURED` 仅代表探针证据取得，
不代表这两个用例已经完整通过。

三个越界程序不能凭延长超时授予 PASS。主线程有界读取确认 1409、1412
的 Spike `mcause=5`，不是未对齐访问的 cause=4；对应 e16 访问地址对齐。
RTL 仿真在 L2 越界保护处终止。参考执行反复进入 access-fault handler，
因此还需要把激励的有效地址约束、异常恢复目标与环境访问范围明确分开。
当前只修复参考超时后仍解析巨大日志的工具问题，原程序仍保留未通过记录。

## 剩余五条的闭环口径

上述 15 条的第一阶段已结束，`remaining15-validation-20260927-01/checkpoint.json`
为 `SELECTED_PASS`：10 条原失败用例通过，另有 5 个定向测试和 AXPY 性能检查通过。
这不是 15 条全部通过，也没有收集新 RTL 的代码覆盖率。

剩余 1401/1402 保持原 ELF。异常探针已经取得 RESP 和 NEXT 记录；比较器必须
同时证明实际 vstart 更新、异常 CSR、维护写回不破坏旧值、已完成元素写回正确，
并继续比较异常处理之后的完整指令流，不能以跳过异常指令替代检查。
`replay-failed-rvv --fault-vstart-probe` 只用于已单独编译该 bind 探针的镜像，
默认关闭，不改变正常重放或功能 RTL。

1409/1410/1412 的进一步检查发现，确定标量源值的验证插桩覆盖了索引构造中
`vmv.x.s` 读取的向量寄存器，破坏随后 `vslide1down.vx` 的索引轮换。
修复需同时约束生成工具和存量激励。派生 ELF、源码差异和原 ELF 哈希分别保留；
派生激励即使通过，也只能记为激励修复闭环，不能改写原越界程序的失败记录。

### 异常比较器的完整检查

1401：256 个维护写回字节必须与实际异常前内容一致，其中 16 个字节的 Spike
参考状态带有 unknown 标记。对这 16 字节仅证明实际旧值没有被破坏，不将 DUT
值反向填入算术参考模型，也不清除后续 unknown 标记。

1402：真实 `vstart` 从 1 更新到 2。已完成元素包含 8 个字段、每字段 4 字节，
因此必须观察到 32 字节 load 写回，不能只检查最终值相同。另有 896 字节维护
写回，其中 28 字节与 load 写回重合；必须验证维护在前、load 在后，拒绝同拍
碰撞、反序或重复 load。合计 928 个写回字节事件、900 个最终写入位置。

新增 `verified_probed_load_faults` 单独记录这类证据，不把部分完成 load
伪装成 identity-only 异常。标量对比确认 cause/mepc/mtval，向量对比确认写回
和 vstart，审计检查两份证明一致并重新核验四份原始日志的哈希。
负例覆盖遗漏写回、全 BE=0、错误值后恢复、重复/逆序写回、错误异常 CSR、
错误 vstart 和错误动态指令身份。未打开 probe 的原比较路径仍不能接受没有
证明的部分完成 load。

### 索引插桩修复

生成器原本用 K 次立即数插入和 N-K 次 `vmv.x.s`/`vslide1down.vx` 轮换，
将 K 个有界索引放入前 K 个有效元素。错误插桩在每次 `vmv.x.s` 之前执行
`vl1re8.v`，把整个索引寄存器改成固定测试图案。

`vector_signature.py` 现在只对静态证明成立的该构造保留原始轮换：核验 VL、
EEW/EMUL、轮换次数、寄存器不被覆盖、无内部跳转标签，以及整个分段访存范围
均落在数据区内。其他标量读操作继续使用原有确定值插桩，未知模式不豁免。
三个派生程序保留原随机指令、掩码、vstart、内存数据和异常处理程序；只撤去
破坏索引的插桩。Spike 均完成全部索引访问，无内存异常。

新一轮严格 VCS 结果目录为 `out/remaining5-closure-20260927-01/`，服务为
`ara-remaining5-closure-20260927-01.service`。最多 5 路并发，输入和工具冻结，
失败即停。原 ELF 重放为 1401/1402，派生激励为 1409/1410/1412。
最终结论需以该目录 `checkpoint.json` 和逐例 `verdicts/` 为准。

### 最终五项新仿真结果

`remaining5-closure-20260927-01/checkpoint.json` 已为 `SELECTED_PASS`，
服务正常退出 0。所有用例均达到 scalar `TERMINAL_MATCH`、vector `PASS`，
并通过严格结果审计；冻结输入和功能 RTL 无漂移。

| Seed | 输入类型 | 匹配标量提交数 | 常规向量写回指令比较数 | VCS 墙钟秒 | 结果 |
| --- | --- | ---: | ---: | ---: | --- |
| 1401 | 原 ELF | 3025 | 180 | 21.165 | PASS |
| 1402 | 原 ELF | 2629 | 64 | 18.715 | PASS |
| 1409 | 派生 ELF | 2824 | 251 | 26.528 | PASS |
| 1410 | 派生 ELF | 2839 | 278 | 26.741 | PASS |
| 1412 | 派生 ELF | 2864 | 276 | 25.931 | PASS |

常规向量比较数不包含单独证明的故障指令，不是整个程序的向量指令总数。
1401/1402 的故障写回按上述独立证明计入完整性审计。
本阶段共运行 167 项宿主工具测试通过，并经独立审查和负例变异复核。
本阶段新增修改仅在验证工具、激励生成和报告，不增加功能 RTL 修改。

## 修复后覆盖率收集

已安排独立目录 `out/repair-closure-coverage-20260927-01/`，以本次通过的
功能 RTL 和异常探针重新编译 VCS，唯一配置变化为 `code_coverage=1` 及输出目录。
收集范围为前两阶段的 21 项：12 项原失败 ELF、3 项修复后的派生 ELF、
5 项定向回归和 AXPY。保留原 ELF/种子及检查策略，不因采集覆盖率放宽判定。

采集 `line+cond+fsm+tgl+branch`，每项使用独立 `code.vdb`，最多 8 路并行。
成功完成且验证通过的 VDB 才可进入 DVE；旧 RTL VDB 不与新编译数据库混合。
这个修复回归子集的覆盖率不是全部历史用例在新 RTL 上的累计覆盖率。
覆盖率结果以新目录的 `collection.json` 和 `dve/summary.csv` 为准；
在它们生成并验证之前，不能把已安排重跑写成已经计入。

后台服务为 `ara-repair-closure-coverage-20260927-01.service`，自动执行重放、
逐项审计和 DVE 汇总。查看总体状态及逐例进度：

```bash
cd /home/wangwy/openproject/ara_dsa_signoff_integration
cat verification/out/repair-closure-coverage-20260927-01/status.json
cat verification/out/repair-closure-coverage-20260927-01/scheduler/status.json
```

该镜像含异常 bind 探针，原始层级覆盖率也包含其计数及 TB/UVM；汇总记录探针
层级，不将包含它的父级分数称为排除验证逻辑后的纯 DUT 覆盖率。

### 覆盖率重跑的 vlsseg 墙钟超时

首轮覆盖率重跑完成 20 项 PASS，仅 vlsseg 在 900 秒墙钟上限终止；
没有因此授予 vlsseg PASS，也没有合入其不完整 VDB。原覆盖率运行目录与
失败记录保留。

与无覆盖率的已通过运行逐行比较，超时日志的 215,756 行标量提交记录全部
等于通过记录的相同前缀。最后周期为 391,748，通过运行终点为 443,269，
已推进约 88.38%；此前无覆盖率运行墙钟为 486.285 秒。
按超时运行的平均进度估算全程约 1,018 秒，说明 900 秒不足，而不是已有
证据显示程序死锁。日志最后已完成子检查 144，原通过记录之后仍有后续检查。

因此只增加该例墙钟上限至 1,800 秒，不改程序、RTL、种子或周期看门狗，
也不重编译。新结果位于原目录的 `results/vlsseg_retry1800/`，控制记录位于
`out/vlsseg-cov-closure-20260927-01/`。新例必须完整通过自检、提交轨迹检查及
独立审计后，才允许其 VDB 与已验证的原 20 项合并；超时 VDB 始终排除。

补跑与自动汇总分别由 `ara-vlsseg-cov-retry-20260927-01.service` 和
`ara-vlsseg-cov-finish-20260927-01.service` 管理。汇总脚本不启动额外仿真，
等待补跑完成后审计并调用 DVE。查看状态：

```bash
cd /home/wangwy/openproject/ara_dsa_signoff_integration
cat verification/out/vlsseg-cov-closure-20260927-01/replay-status.json
cat verification/out/vlsseg-cov-closure-20260927-01/finish-status.json
```

只有 `finish-status.json` 为 `PASS` 且 `coverage_verified` 为 `true` 时，
才能使用该目录下的 `dve/summary.csv`。`RUNNING` 不代表已经完成覆盖率统计；
`FAIL` 时保留诊断和输入，不自动重试或将不完整结果计入。
