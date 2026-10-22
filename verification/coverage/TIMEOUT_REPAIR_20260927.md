# 2026-09-27 超时归因与修复验证

## 范围与结论

本次针对 `vcs-dve-gap-20260927-02` 累计383项中的18个TIMEOUT。
这些不是已确认的18个RTL错误。只读检查保留的日志、提交轨迹、ELF及源代码后，
目前证据一致指向：测试仍在推进，却被统一的300秒墙钟限制终止。
这不保证未执行的部分正确，因此旧TIMEOUT不改写为PASS。

没有修改RTL、已有比较器、原始测试、既有VDB或已有结果。
没有启动新的RTL编译，也不改变处理器周期级看门狗。
总表：`verification/out/timeout-repair-20260927-01/triage.json`。
其中PC多样性是观察量，不能单独证明无死锁；下面还检查了具体循环和进度。

## 实测归因

| 用例 | 超时时的证据 | 处理 |
| --- | --- | --- |
| vl1r | 67587次退休，cycle103780；正在printf；已输出至检查9通过 | 新quiet入口仅去掉成功/进度文本，全部原TEST_CASE及比较保留 |
| vlseg | 74995次退休，cycle116502；已输出检查56通过 | 同上，保留原全部SEW及masked检查 |
| trap_state_prereq | cycle102327，已进入main打印trap_case记录 | 只省略逐case快照输出；所有trap执行、比较、失败记录和终态检查不变 |
| linux_vector_context | cycle105647已完成4/6轮；cycle107912正在下一轮有限初始化循环 | 原ELF重放，预算600秒，保留连续6轮上下文切换 |
| operand e64 | 44/56项完成；cycle119596在第45项prepare/memset | 原ELF重放，预算600秒；按最近归约开销估算全程400–450秒 |
| FP16 s0..s7 | 已分别完成34/39/41/40/33/39/40/39项，均为58项中的一部分 | 464项按ordinal模32划分为32片，每片14或15项；每项输入/期望/CSR检查不变 |
| Q6_K | cycle67848，已选中result=PASS输出分支，停在printf | 原ELF重放，600秒，必须等完整退出才通过 |
| Q8_0 | cycle63893，已选中result=PASS输出分支，停在printf | 同上 |
| QBS chain3_operation | cycle88632，已完成3次operation的结果检查，正在printf | 同上；不拆operation，保留FILL/RELEASE连续性 |
| AKV portability | case0..4已输出status=0/errors=0，正在后续输出 | 按独立功能case及mixed检查分片，保留数值和状态检查 |
| AKV D256 | case0通过，17-token子例在256维循环的第166维，索引递增 | 按原子例拆分；大子例再按score/PV/online组拆分，保留完整维度与参考比较 |

FP16的完成数取`csr_checks / 3`，不是进入函数即递增的`cases`。
结合轨迹中`num_failed`仅初始化为零，可确认已完成部分未报告错误。
某些CSV末尾为`arch_start,PC=0`，不是PC=0的退休，不能误判为异常跳转。

## 修改边界

- `coverage_quiet_success.h`仅允许省略三种固定格式：逐项Checking文本、
  `PASSED.`文本和trap快照。错误、总检查数、最终PASS/FAIL及返回值全部保留。
- quiet用例直接包含原C测试，避免复制后遗漏检查。原测试仍可按原方式运行。
- FP16保留原整数参考算法、NaN/Inf/边界输入、frm/fflags/vstart检查。
  32片保持464个ordinal完整互斥并集；最大geometry没有缩小。
- 分片不等于原进程顺序的证明。FP16各case自行初始化；AKV分片声明只保留
  每个独立子例的检查全集，不冒充跨子例上下文连续性测试。
- Linux和QBS连续operation使用原ELF，避免切分破坏所测顺序关系。

## 验证和停止规则

第一波40次执行：3个quiet入口、5个原ELF重放、32个FP16分片。
使用同一VCS coverage镜像，最多8路；只有按证据批准的用例使用600秒预算。
任何新增非PASS停止派发并保留证据，不自动重试或进一步扩大限时。

通过条件仍为原自检、完整退出、独立trace审计和完整VDB。
日志中单独的`result=PASS`前缀不算通过。旧18个TIMEOUT继续保留在历史结果中，
新结果用`repair_of`或分片对应关系说明是否完成了原检查。

FP16全部完成后，`audit_fp16_repair_shards.py`从实际PASS日志提取ID位图，
核验464项无遗漏、无重复、VLEN=1024以及每项3个CSR检查。
该检查通过后第二波AKV队列才启动；前序失败时不启动后序。

```sh
./vstatus status timeout-repair
```

输出：`verification/out/vcs-dve-timeout-repair-20260927-01/`。
本文件记录归因和已实施的验证安排，不预先宣称后台测试全部通过。

## 首批实测与重新安排

首批已通过`coverage_vlseg_quiet`和`coverage_trap_state_quiet`，
`coverage_vl1r_quiet`仍被300秒限时截断，队列按规则停止；AKV后续队列未启动。
不能将这次停止描述成全部测试已经完成。

quiet vl1r的提交轨迹在cycle388/13967/38121/82240依次进入TEST_CASE1/2/3/4，
cycle124862仍在第4组有限memset循环中，连续清零地址递增。
前三组增量约1.4万、2.4万、4.4万周期，与1/2/4个寄存器的检查工作量增长一致。
结合第4组8个寄存器与末尾小型第5组，估计完整约18–21万周期，
按实测速率约450–510秒；重新安排中只将本项设为900秒以容纳并发负载波动。
这是估算，不是完成结果；不改输入、比较、程序顺序或RTL看门狗。

新入口`resume_timeout_repair.py`校验旧PASS的ELF、仿真镜像、oracle、
源文件及VDB散列，复用上述两个PASS，避免重复仿真。旧失败证据保持原样。
新首批目录为`vcs-dve-timeout-repair-20260927-03`，38次执行待验证；
完成且FP16实际ID并集核验通过后，才启动22项AKV的`-04`批次。
沿用8路并行，新增非PASS停止派发。这里只完成测试组织修复，未修改RTL。

## AKV mixed 的后续超时分析

首批40项已全部通过，其中32个FP16分片的实际日志证明464个ordinal完整互斥。
AKV第二批14项通过，mixed超时后取消7项；原始记录保留在`-04`目录。

mixed不是普通的常数期望检查：它先在目标处理器上执行独立标量参考，
再执行native路径并逐元素比较。原600秒预算没有充分计入这个区别。
该项ELF SHA256保持与`-04/inputs/extra-app-coverage_akv_portability_mixed.elf`一致。
结合其反汇编和commit_trace.csv，确定如下进度：

| 事件 | PC | 实测 |
| --- | --- | --- |
| reference入口 | 0x800012a8 | cycle67351 |
| 第一遍max-score token递增 | 0x8000140c | 65次，最后cycle238117，寄存器s6=65 |
| 第一遍点积维度递增 | 0x8000145e | 4160次，即65×64 |
| 第二遍token递增 | 0x800016ae | 完成token0，cycle241755 |
| 第二遍点积维度递增 | 0x800016fa | 共110次，最后token1的d=46，cycle243414 |
| native入口 | 0x800019f6 | 尚未到达 |

超时时最后退休cycle243428。PC0x80001758是参考点积中的K地址计算，
并非硬件队列等待。此证据支持“参考计算未完成”，不证明后续native一定正确。
输入有65个token、64维、10个masked token，参考执行两遍score，
再对55个有效token做PV累加；softcap、mask scale、position bias和sink同时开启。
保留这些功能、65-token跨块尾部、原参考算法及全部容差检查。

按照第一遍约17万周期及标量PV循环工作量，估计全程序约55–65万周期；
按已测约406cycle/s，约23–27分钟。mixed单项预算改为1800秒，
不是统一增加其它测试限时，也不改变RTL周期看门狗。
`resume_akv_repair.py`复用14个经散列核验的PASS和VDB，重跑8个未完成项，
输出到`vcs-dve-timeout-repair-20260927-05`，8路并行。
完成后自动汇总DVE；任何新的非PASS仍停止派发，禁止自动反复加时。
本轮不修改RTL、测试ELF、软件参考或原始失败记录。
