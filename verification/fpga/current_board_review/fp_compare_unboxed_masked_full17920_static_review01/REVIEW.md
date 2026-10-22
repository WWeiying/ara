# Masked Unboxed E16/MF4 Full17920: Static Reuse Review

结论：来源和几何足以支持一个独立完整移植，现有unmasked框架可高度复用；**不能只改名称或vm位后沿用旧gold**。本轮只有源码、ELF小文件和封存元数据静态核查，没有运行模型/Host/编译/Spike/VCS、大trace或活动任务查询。不是新的执行授权，也不改变arithmetic18/22或e8/e16m8预算。

## 1. 实际身份与旧错

`fp_comparison_original/provenance01/parents.json`中精确条目为
`rvv_fp_compare_unboxed_e16_mf4`，HASH_EXACT_PRESENT，SEW16/mf4，
UNMASKED0/UNBOXED1/RESTART0/DESTINATION_KIND0。

- 原ELF：`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions46/binaries/rvv_fp_compare_unboxed_e16_mf4`，本轮实hash `82d90319cdef6cad35167ab9e5e2cccc86b90103c172b88f20b5537c23609a79`。
- 已通过unmasked父ELF实hash `404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152`，两者不是同一父程序。
- 完整C：`fp_compare_unboxed_prefix265_prepare01/software/original/parent.c`，实hash `03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad`，与masked条目一致；同一C通过宏选择masked分支。
- 原masked汇编：`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_fp_comparisons_unboxed_v24_01/rvv_fp_compare_unboxed_e16_mf4.S`，实hash `baf8aa75c2902f2b2f1b0491a64ad0dba738a48c397c059dd9c88383e8767f6c`。
- 该归档`e16/fixtures.h`实hash `5664c1a4546bb402fe64ef190ca8e4910efa21fc35daea5229a187377eba7cb1`，与已接受移植使用的原fixture一致。16个u16输入的32B在masked ELF的0x108f8唯一匹配；6x16x16个(bit,flags)结构的12288B在0x10968唯一匹配。这里是静态原始字节匹配，不是数值模型运行。

通过ELF PT_LOAD字节匹配，capacity与十个helper的完整185条编码均唯一定位。每个helper相对已证明的unmasked原编码**仅目标指令bit25由1变0**，其余所有指令字节相同；capacity仍`52fd/00e2f557/8082`，vtype14。masked原始位置如下（不可复制成新SoC PC）：

| Helper | 原地址 | 条数 | masked目标编码 |
| --- | --- | ---: | --- |
| capacity | 0x10542 | 3 | 不适用 |
| op_0..3 | 0x1054a/1058a/105ca/1060a | 各17 | 60881c57/70881c57/6c881c57/64881c57 |
| op_4..9 | 0x1064a/10692/106da/10722/1076a/107b2 | 各19 | 60805c57/70805c57/6c805c57/64805c57/74805c57/7c805c57 |

原C、helper与fixture证据可用。本轮没有重新编译masked Linux父ELF，因此不冒称已获得新的masked全Linux binary重建等同证明；后续source admission应保留本父的原始来源链，不能借用unmasked的404b重建证明来声称82d9同一。

旧板证据为`rvv_recovery08_11/terminal_scene/report.json`的results[45]：完整17920、exit1、errors5816，4.705601s。`rvv_recovery08_12/previous_report.json`保存的是相同结果/输出，不算两次独立失败。首条DETAIL是seed0/op0/VL8/mode3/sticky0，expected_flags0/actual16/errors1；下一条sticky1为expected1/actual17。按原loop这是call39/40，后有VL15/16及op1/2等all-off多出NV。前20条所保留详情均是此类NV不符，不能把未保留详情的全部5816错误都归为flags，也不能据旧板错宣称当前M9仍有同一缺陷。

## 2. 保留不变的完整范围

32seed x10op x7VL x4mode x2sticky=17920，原顺序不分区、不重置前史。CAP16，VL序0/1/2/3/8/15/16；输入各32B有效、各2048B backing；VLEN1024、physical1、vtype14、vd24与v8/v16不重叠。mask128B每call全写，output130B每call全写，逻辑结果2B，guard位于output[0]/[3]。沿用8个输入SD+16maskSD+16outputSD+尾SH=41stores/call，734720总fresh stores；单个对齐LWU覆盖结果和两guard，不从output+1构造宽指针，不扩充bytes4..129的原结果约束。

286720结果位、35840guards、17920 flags/vstart、326144动态helper+capacity3保持。10752 vf调用仍LHU原b[0]后FMV.D.X到f0，不能修复其非法NaN boxing，也不能全置零；所有32seed实际payload/10752 committed FPR writeback检查可复用。调用者fflags保存/设sticky/读取/恢复和vstart返回0保持，不能增加未测的恢复后CSR读回声明。完整错误逐bit计数、两guard合计一次错误、原前20 DETAIL及总数/exit语义不变。

## 3. 必须改的最小清单

1. **独立身份/源码配置/helper与PC。** 从原C以UNMASKED0派生新目录；保留masked原.S，不修改已封存unmasked文件。更新历史ID、原ELF/hash、所有新SoC/Spike PC、ABI/初始化/失败分支区间和source/helper pins。现有prepare_source.py中的UNMASKED1断言、source_row无mask分支、helper_proof的固定原PC、scope.py的historical name均不能原样复用。
2. **oracle必须mode敏感。** 当前unmasked的2240个`(seed,op,VL)`记录不足。最简单改为8960个`(seed,op,VL,mode)`八字节record，Z16/O16/BaseFlags8/VL8/Arow8/Brow8格式不变；sticky仍运行时OR，完整17920 rows保留。表从17920B增至71680B，仅多53760B，输入period可沿用，远非1MiB几何障碍。原生成器的独立FP16分类和fixture1536对照可复用，但allowed集合和flags union必须按mode重建；旧gold/READY不能复用作新参考PASS。
3. **逐bit集合按原C分支。** `active=(i<VL)&&maskbit(mode,i)`，模式字节依次ff/aa/24/00，start恒0。active仅允许wanted并累加该元素fixture.flags；VL0所有16位必须old；VL>0且i<VL但mask=0必须old（DK0无alias-agnostic例外）；i>=VL仍逐位允许{old,1,wanted}，不把tail收紧成一个Spike值或误作mask-undisturbed。old仍固定0x5b5b，不读a/b替代。特别是all-off、VL>0的tail仍走原tail允许集，并非所有16位都强制old。
4. **flags只对真正active元素归并。** mode3任意VL均只能返回原sticky0/1；mode1/2在VL1同样无active。无效boxing的vf仍按原fixture rhs14的qNaN语义：EQ/NE只有active lhs sNaN贡献NV，ordered比较有active元素才贡献NV。禁止`VL>0 => NV16`或沿用unmasked BaseFlags。首错call39应明确expected0/1，而不是旧unmasked表值；末call17920（seed31/op9/VL16/mode3/sticky1）期望flags1，不是unmasked的17。
5. **owner不能跟mask活跃数一起删。** frozen M9 dispatcher的no-op gate是VL/start等前端条件，并不读取v0内容来提前省掉all-off比较。可沿用五个helper-memory owner/call必需（包括VL0），以及target在VL>0时必需：89600 memory +15360 target，2560 VL0 target单列。all-off VL>0以及mode1/2 VL1的target仍须有真实backend owner；不能因flags0/结果old就豁免。每个实际alloc都要求匹配done，optional VL0若实际alloc也配对。104960是必要owner合同，不在未测时硬断言masked实际总token一定等于unmasked；额外真实token仍须generic严格验证。
6. **新增定向负例而非重造框架。** 模式索引错/交换aa与24、all-off spuriousNV、inactive sNaN不应置NV、active sNaN应置NV、inactive位被改/全关mask缺targetowner、VL0 old/flags、合法不同tail选择及非法tail位、raw scalar归零/boxing、丢fresh/guard/vstart/调用drop-dup-reorder。复用成熟numeric-first worker、lossless六event generic、完整每call owner账本、actual stop hook与collector，不沿用旧硬编码ELF/PC或成功receipt。

## 4. 成本与可执行性判断

可信同形基准是已接受unmasked完整移植：
`fp_compare_unboxed_full17920_worker_review01/TERMINAL_REVIEW01.md`，
M9实际sim0/6687.051487s，retired2665794、finalcycle6152665；
已编译成功路径SoC upper2682862（linked_audit02/RESULT.json）。
不是用旧板4.7秒换算VCS，也不是旧265-prefix未知walltime外推。

masked的调用数、185 helper编码长度、full fresh字节、五个memory helper及原结果LWU均不变，因此**可作为接近6687秒量级的准备候选**，没有m8那种体量倍增。mode敏感record若每mode加载一次并跨两sticky复用，会由2240次LD增为8960次，多6720条LD；但这只是可选源码布局的静态计数，尚未编译证明真实hoist/地址/ABI成本。最直接的mode维record无需运行时逐元素掩码循环，预计主要代价是record访问/索引；不能声称已通过3M gate。

masked目标还可能增加MASKU供数、等待及执行周期；all-off并非前端NOP，不能把少active数换算成固定加速。墙时受宿主负载影响，现有6687s只提供同形实测基准，不保证相同耗时或某个deadline。需要后续单一source实现、原C/独立oracle等价与负例、实际linked完整CFG/stack/新ELF helper检查、一次有界完整参考成本后才具备worker预算准入条件。本任务没有执行或授权这些阶段；当前没有新的准备/参考/DUT PASS。

最小下一动作：获准后以unmasked prepare/worker作为不可变参考，在新masked目录仅实现以上mode-record/oracle/helper身份差异，先做source/Host与actual artifact gate。原17920历史失败不能由unmasked17920、任意短控制或mask-all-on子集替代。
