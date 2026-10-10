# 规约优化深度核查报告

> 后续更新（2026-10-10）：下文保留 2026-10-07 核查结束时的源码、结果和限制。NaN min/max 的后续修复已完成验收，包含额外发现的多上下文合并输入错误；138 例 IEEE 边界及两类各 192 条的流水测试在两种配置下通过，相关回归为 19/19。详细范围见 [NaN min/max 修复移植记录](reduction_nan_minmax_import.md)。本文件中的“仍存在”是原核查快照的结论，不代替后续记录。

核查基线为 `30c6971b`，优化快照为 `e4d261110ea7b8ad37305059d2dc5256b7898247`，开始日期为 2026-10-07。本报告以当前源码和本次新运行的测试为证据；历史日志仅作线索，不视为重新验证。默认重点配置为 `NrLanes=4`、`VLEN=1024`、`reduction_complete_4lane=1`，同时核查关闭优化的行为和单独开关的边界。本次核查已完成：优化方向有实际周期收益，核查起点存在十类已定位问题，当前工作树已完成相应修复与回归；继承的 NaN min/max 错误仍存在，因此整个规约单元不能被宣称为完全符合 ISA。上述 Git HEAD 是核查起点，本报告所列修复仍在未提交工作树中；每轮实际编译版本以对应目录的 `source_manifest.json` 为准。

## 核查范围与完成标准

| 范围 | 必需证据 | 当前状态 |
|---|---|---|
| 基线与改动归属 | 固定提交差异、非规约修改清单、公平对照边界 | 已区分核心、接口元数据与 VLDU/vcompress 外围修改；同源码开关性能对照通过 |
| 有序规约 | 顺序、mask、异常标志、重复指令源数据不变、流水握手 | 已复现并修复源别名复用错误；有序普通求和同步测试通过；宽化失败已定位到测试宏的未声明寄存器修改，修正后开关对照通过 |
| 无序/整数/极值规约 | 树确定性、上下文归属、宽化、尾部及空 lane | 空 lane、FP16 尾部和上下文返回丢失已修复并复测；继承的 NaN min/max 错误仍在 |
| 精确数值后端 | 独立数值参考、多 beat、特殊值、舍入及背压 | seed 问题已修复；980 单 beat、1500 多 beat 测试通过 |
| 跨 lane 协议 | 分块符号扩展、进位、包标签、握手和提前释放 | 真实 SLDU 的 1200 例独立数值/协议测试通过；提前释放另由整机依赖矩阵和源码约束覆盖 |
| 跨指令依赖 | seed 格式/版本、RAW/WAR/WAW、缓存失效和字节覆盖 | seed ID 生命周期、组成员版本、读取身份和有效零版本均有已通过的定向反例；依赖矩阵与链式探针通过 |
| 回归与合理性 | 新编译整机回归、性能对照、硬件成本限制 | 同源码开关对照已编译；最新完整配置的 18 个探针与 16 个 ISA 程序共 34 项全部通过，已知 NaN 反例另列 |
| 教学与性能说明 | 与代码和消融配置一致、无过度结论 | 已同步十类修复原理、性能限制及最终证据表，撤回历史全面正确的概括 |

## 对优化合理性的判断

这些改动有明确的体系结构依据，但不同机制解决的问题和代价不同，不能合并成“所有规约都加速”。固定等待旁路减少有效数据已经可传输时的额外寄存等待；多上下文执行利用 FPU 反馈或跨 lane 交换期间的空闲时隙；精确累加改变无序求和的数据表示和归并方式；late seed 则把“向量主体可以先算”与“最终结果必须使用正确 seed”分开。前述三项同 ELF 周期对照说明其中部分工作负载确实受益，收益不是仅由外围加载修复造成。

| 机制 | 合理使用的前提 | 本次暴露的主要成本或风险 |
|---|---|---|
| 输出、输入和路由旁路 | 全链路握手只消费一次，保留必要的缓冲边界 | 控制状态更依赖同拍事件；有序末项曾提前退休；组合 ready 路径的时序收益还需综合验证 |
| 上下文重叠 | 每个返回值和计数都有明确归属，退休顺序保持正确 | 新旧状态覆盖导致丢失 FPU 返回；增加上下文状态、tag 和调度逻辑 |
| 无序精确累加与压缩分块 | 只进入允许的 unordered 格式，位宽覆盖最坏情况，树语义确定 | 分段寄存器、根加法与舍入器有面积和时序代价；空 lane、FP16 布局和特殊 seed 均曾出错 |
| late seed 与结果缓存 | 地址、版本、有效性、字节覆盖和所有权同时成立 | 组寄存器版本、epoch 零、ID 复用及缓存寿命缺陷；缓存不是仅加一个数据选择器 |
| 有序重复结果复用 | 所有输入语义相同，前驱本身也不改变后继输入 | 命中率取决于程序；源编号相同并不等于源值相同；非重复有序探针需独立报告 |

因此，可以认定这些优化方向具有工程上的合理性，且在已测四 lane 配置上存在周期收益；不能据此认定其硬件成本更低、任意应用更快，或适合直接推广到其他 lane 数。精确求和允许的数值变化也只适用于无序规约，不能借此放宽有序逐项舍入。可维护性方面，多种开关共享状态机使边界组合容易出错，本次十类问题说明持续保留定向反例、源码指纹和接口断言比只保留性能 PASS 日志更重要。

正确性的判断必须与“值得优化”分开。核查起点的实现存在已复现错误，不能判定为正确；修复后的结论以本报告的测试范围为限。已知继承的 NaN min/max 错误意味着整个规约单元仍不能被描述为完全符合 ISA，缺少 PPA 结果则意味着净硬件收益尚未建立。这是本次审计的明确限制，不是把未证明的范围默认为通过。

## 与基线的源码归属

`git diff 30c6971b -- hardware/src hardware/include` 显示，本分支的主要改动集中在 `ara_sequencer`、`operand_requester`、`valu`、`vmfpu`、`sldu` 及两个新增精确数值模块。`ara_typedef.svh`、`ara_pkg.sv`、`lane.sv`、`lane_sequencer.sv`、`vector_fus_stage.sv` 主要传递别名、版本、late seed 和旁路数据等接口信息。本次另加 `global_vl`，使 lane 保留架构总长度；它和局部 `vl` 分别服务于协议选择与本 lane 的元素计数。

两个外围修改必须与规约性能分开：`vldu.sv` 修正写回地址和 instruction ID 掩码宽度互换，避免加载写错 VRF 地址；`masku.sv` 增加 vcompress 最后一个 mask bit 为零时的结束处理。两者没有被规约优化开关包围，也不应被计入规约数据通路的创新或加速收益。关闭规约开关的当前源码保留它们，适合作为同环境对照；原样 `30c6971b` 则用于判断问题是否已经存在。

## 已定位的优化缺陷汇总

| 缺陷 | 直接后果 | 修复与证据 |
|---|---|---|
| 有序重复指令未排除前驱改写源 | 复用过期结果，64 得到 32 | 禁止源别名复用；两种定向反例通过 |
| late seed 改变特殊值树位置 | 相同输入的 NV 标志随依赖状态改变 | 全局模式统一在根节点插入 seed；数值和整机反例通过 |
| 精确门禁使用 lane 局部 VL | 短向量混用两种协议，无法完成 | 增加 global_vl，空 lane 发空子树；短向量与长度矩阵通过 |
| FP16 活动位未按物理槽布局生成 | VL=5 漏算源元素 | 统一使用 be() 和 mask 生成 active；99 例矩阵通过 |
| 新指令复用 ID 时清空旧 seed 缓存 | 消费者等待已经存在但被失效的 seed | 完成时才替换缓存；完整 profile 的依赖矩阵通过 |
| 前后台切换覆盖同拍 FPU 反馈 | pending 位永久保留，min/max 流停滞 | 保留已更新的下一拍上下文；有限数反例通过 |
| 寄存器组版本维护和读取归属不完整 | 标量 seed 得到 64 而非 39；组向量源得到 256 而非 231 | 更新所有目的成员版本，并限制缓存匹配在版本所属的源寄存器；两种反例和五项矩阵通过 |
| 未填写的 source_version 被当作有效零版本 | epoch 回绕时整数规约复用旧 seed，39 得到 64 | 补齐 ALU 请求版本并增加显式有效位；零版本反例与最新 11 项定向回归通过 |
| 缓存寿命未预留 issue 到 grant 之间的版本领先量 | 请求端边界条件下，回绕版本可命中旧缓存并绕过新生产者 | 寿命改为 246；单元接口反例、失效边沿及 11 项整机定向回归通过 |
| lane 0 将最后一个 masked 跳过的输入 token 误作全局最终结果 | FP16 有序交替 mask，9 提前写成 8 | 整机隔离反例及波形已确认；最终接收条件改为已完成的寄存计数，独立反例及三项有序探针已通过 |

表中“通过”均指对应反例回归，不表示整个分支已无错误。下文保留失败与修复证据，最终回归和仍存在的继承缺陷分别列出。

## 已确认的反例：late seed 改变特殊值计算树

现有 `fp_exact_reduction_oracle_tb.sv` 比较普通 seed 和 late seed，但其 900 组输入由 `finite_value()` 生成，只覆盖有限数，每组一个 64-bit beat，且输出始终 ready。不能用它证明 NaN/Inf、多 beat 或背压等价性。

本次将相同测试骨架的输入改为 FP32、RNE、seed=`0x7fc00000`（qNaN）、两个有效元素 `[+Inf,-Inf]`，重新用 VCS 编译当前 RTL。普通路径返回 `{fflags,result}=00/7fc00000`，late-seed 路径返回 `10/7fc00000`，即后者额外设置 NV。原始失败日志在 `hardware/build/reduction_audit/seed_special/run.log`，仿真时间为 66 ns。

原因是普通路径先把 seed 放进局部特殊值树，qNaN 抑制该节点后续的无穷冲突；late-seed 路径先对两个无穷求和，产生 NV，再插入 seed。两者有限数加法等价，但 IEEE 特殊值/异常行为不等价。SLDU 全局路径同样根据 `late_seed` 改变 seed 的树位置，需要整机反例和修复回归。

依据：[RISC-V V 1.0 规约规范](https://raw.githubusercontent.com/riscvarchive/riscv-v-spec/v1.0/v-spec.adoc)要求给定 `vtype` 和 `vl` 的无序求和树结构确定。不能以无序求和允许重排为由，让依赖是否仍在执行改变该树。

注意：本次 VCS 的 `$fatal` 最终仍返回 shell 状态 0，因此回归脚本必须同时检查明确的 PASS 标志、错误信息和超时，不能只检查进程退出码。

### 整机复现与修复

`apps/reduction_audit_seed` 在相同 `vtype/vl` 下分别使用已经就绪的 qNaN seed 和前一条规约刚产生的相同 qNaN seed。向量的第 0、4 项分别为正、负无穷，其他项为零。修复前整机输出 `plain=0/7fc00000 chain=10/7fc00000 FAIL`，与单元反例一致。修复后输出 `plain=10/7fc00000 chain=10/7fc00000 PASS`，并以 `tohost=0` 正常结束。

修复保留 late-seed 和提前释放功能：新增累加器参数 `DeferSeed`，在全局模式下只携带 seed 元数据，不把 seed 加入 lane 局部数值/特殊值状态。中央 finalizer 对普通和 late seed 都在同一个根节点插入一次。非全局局部累加模式默认保持 `DeferSeed=0`。这会改变少数原实现的特殊值异常组合，也可能改变 seed 占主导时的分块长度，历史性能数据不能未经复测就当作修复后的数据。

## 已确认的反例：有序重复指令复用了已经改变的源

`ordered_source_duplicate()` 原先比较操作码、源寄存器编号、VL、vtype 和舍入模式等，但没有检查第一条指令是否改写第二条的 seed、向量源或 mask。指令相邻只能排除两者之间的其他向量指令，不能排除第一条自己的写回。

`apps/reduction_audit_alias` 使用 FP32 最小次正规数的整数位型 `1`，所有加法都精确，避免舍入差异干扰判断：

| 情况 | 正确结果位型 | 修复前 | 修复后 |
|---|---:|---:|---:|
| VL=32，seed 初始为 0，连续两条 `vfredosum v2,v1,v2` | 64 | 32 | 64 |
| v1 各项初始为 1，第一条写 v1[0]=32，第二条重新规约 v1 | 63 | 32 | 63 |

修复在中央别名判定中排除 leader 写 seed、向量源寄存器组或活动 mask 的情况。向量源按 LMUL 计算寄存器范围；合法的不改源重复规约仍可复用结果。原始和修复整机日志分别位于 `hardware/build/reduction_audit/alias_before/`、`hardware/build/reduction_audit/fix_regression/reduction_audit_alias/`。

另一个尝试的 LMUL=2、标量目的寄存器 v9 的规约在 dispatcher 处触发 illegal instruction，尚需与基线及规范核对；该情况没有计入上述两个通过的回归，不能宣称已覆盖寄存器组内部重叠。

## 新增数值与握手验证

`gen_exact_reduction_oracle.py --special` 在原有 900 组有限数测试之外增加 80 组显式预期的 NaN、正负无穷、掩码和有符号零测试，覆盖五种标准舍入模式。更新后的 oracle TB 同时检查普通和 late seed，980 组通过。测试文件可以用 `+VECTOR_FILE=...` 指定，增加了缺失文件、空文件、格式错误和超时检查。

新增 `gen_reduction_multibeat.py` 和 `reduction_multibeat_tb.sv` 生成并验证 1500 组测试，每组 1～64 个输入 beat，包含随机有限值、同指数 bin 大量累加、正负抵消、极小次正规数、有符号零和全 mask。每组同时运行分段、非分段和 late-seed 三个实现，比较精确源整数和最终 result/fflags。驱动含随机输入空拍、start 与首拍同时/分离、输出连续五拍背压；每个背压周期重新核对精确状态及输出。所有 1500 组、三个实现通过。该测试验证数值模块与其接口，不代替 SLDU 包传输和整机依赖验证。

日志位于 `hardware/build/reduction_audit/oracle_after/` 和 `hardware/build/reduction_audit/multibeat/`。整机批量回归脚本 `hardware/scripts/run_reduction_audit.py` 保存模拟器与 ELF 的 SHA-256、运行命令、退出码和错误信息，并要求 `Core Test *** SUCCESS *** (tohost = 0)`。首次脚本误用了 `PASSED` 而把成功日志标为失败，已更正并用 `--recheck` 重读已结束的日志；没有把实际出现 `$error` 或超时的测试重新标为通过。

## 新确认的继承问题：全 NaN 的浮点极值规约

`apps/reduction_audit_minmax` 将 32 个 FP32 源元素和 seed 全部设为 qNaN 位型 `0x7fc12345`，分别执行未掩码的 `vfredmin` 和 `vfredmax`。基线 `30c6971b` 与修复后的优化版都返回 min=`0x7f800000`、max=`0xff800000`，而正确结果应为 canonical NaN `0x7fc00000`。两边均以明确的 `tohost=1` 结束；输出中的 max 被 `vmv.x.s` 符号扩展到 XLEN，所以打印为 `ffffffffff800000`。

这不是普通有限数测试能暴露的问题。现有实现用正/负无穷填充 min/max 的空槽，但 minimumNumber/maximumNumber 遇到一个数值和一个 NaN 时选择数值，因此无穷不是覆盖 NaN 情况的单位元。当前上下文优化继承了这个选择。该问题不能归因于本轮优化，也不能因基线相同就把优化版判定为符合 ISA。依据是 [RISC-V V 1.0 的浮点规约章节](https://github.com/riscvarchive/riscv-v-spec/blob/v1.0/v-spec.adoc#vector-single-width-floating-point-reduction-instructions)和 [F 扩展的 minimum-number/maximum-number 规则](https://docs.riscv.org/reference/isa/unpriv/f-st-ext.html)。

可复核日志：`hardware/build/reduction_audit/corrected_baseline/reduction_audit_minmax/stdout.log`、`hardware/build/reduction_audit/corrected_final/reduction_audit_minmax/stdout.log`。另一个含全 mask 情况的探针保留在 `apps/reduction_audit_minmax_masked`。最初直接对未初始化的 v0 执行 `vmclr.m`，四态 RTL 仿真把 X XOR X 继续算为 X，导致后续未知值和超时；这些旧日志不能作为“已确定的全 mask”证据。补上 v0 初始化后，当前关闭优化版明确返回 masked=`0x7f800000`，仍应为原样 seed=`0x7fc12345`。不能只换 neutral 常量就认为问题解决：所有源都 inactive 时还需原样复制 seed，保留 NaN payload 且不新增异常标志。

## 测试程序自身的问题与同步边界

现有 `vfredusum.c` 把 `0x42920000` 等 IEEE 位型传给 `VCMP_F32/F64`，宏会把它们作为整数数值转换成浮点数比较，而不是按位解释。已改用 `VCMP_U32/U64` 检查相同位型。`vfredosum.c` 和 `vfredusum.c` 的长向量测试请求 AVL=64，却固定期望 64 项总和；当前 VLEN=1024、e32/m1 的实际 VL=32，正确总和是 145 而不是 289。现在读取实际 `vl`，对已知的循环序列 1～8 做独立标量求和，再比较其 FP32 位型。这些整数足够小，不存在树顺序或舍入歧义。

原宏的 `MEMORY_BARRIER` 实际为空。关闭 UART 进度输出后，部分比较读到旧值；试用 `fence` 后整机又触发了 CVA6 transaction ID 冲突或未知值断言，因此没有把这次尝试保留为默认行为。新增可选 `RVV_AUDIT_SYNC`，利用当前 Ara dispatcher 在读取 vector CSR 前等待后端 idle 的机制隔离功能测试。它是此平台的测试同步方法，不是可移植的 FENCE 替代品，也不能用这组串行化运行衡量吞吐优化。所有这些尝试的失败日志保留，不被后续通过记录覆盖。

第一轮 quiet 回归位于 `official_final`：16 个 ISA reduction 程序中 12 个正常成功，4 个浮点求和程序失败或超时。修正比较、实际 VL 并加入 CSR 同步后的 `synchronized_final` 中，有序普通求和已正常成功；宽化有序 masked 测试仍得到 53 而不是 37，并在当前关闭全部规约开关的 `synchronized_off` 中复现。其根因还未完成定位，不能直接归为优化缺陷。基线原样 RTL 还包含加载地址截断问题，依赖内存的旧测试可能被这一外围问题干扰，不能用它们的失败作为规约数值参考。

回归脚本现在也捕获 VCS 的 `started at ... failed at` 形式的断言失败，并在启动任何测试前复制全部 ELF 输入，防止排队期间重新编译导致同一批次悄悄使用不同程序。旧批次仍按各测试实际记录的 ELF SHA-256 判断，不能仅按程序名认定二进制相同。

## 位宽与配置范围

288 位带符号精确和采用 `2^-149` 为单位。最大有限 FP32 对应整数 `(2^24-1) * 2^253`，1024 个同号最大值仍小于 `2^287`，1025 个则超过有符号范围。49 位带符号分段 bin 的最大单项为 `(2^24-1) * 2^15`，最多容纳 512 个这样的同号项。不能因为默认 VLEN=1024 测试通过就声称任意 VLEN 安全。

本次在 Makefile 和仿真初始化断言中增加保守上限：局部 flat exact 的 VLEN≤8192，局部分段 exact 的 VLEN≤4096，全局 exact 的 VLEN≤2048，且要求四个 lane。推导按 LMUL=8、FP32 最坏幅度、seed 也可能占一项计算。Makefile 边界接受及翻倍拒绝已检查；这些是数值安全门禁，不代表所有允许配置均完成整机验证。

## 已完成的补充回归

18 个已有性能探针中，15 个在第一轮修复整机上正常成功；`perf_exact_global_reduction_probe` 因原先 180 秒时限过短，延长后正常成功；`perf_reduction_chain_bypass_probe` 在最终修复整机上正常成功。`perf_exact_sparse_window_probe` 暴露的 assertion 忽略了合法的 `MFPU_WAIT && exact_stream_foreground_advanced_q` 情况：后继局部结果已完成而前驱尚在退休。补全该所有权状态后，该探针正常成功且无断言报错。此次修正扩大的是与控制状态一致的断言条件，不是取消所有权检查。

`apps/reduction_audit_seed_width` 的 e16 原生规约与宽化规约交替用 seed 的测试通过。`apps/reduction_audit_group` 在完成 v9 规约后，用 LMUL=2 的 v8/v9 寄存器组整体改写，再把 v9 当作 seed；原始基线和优化版都得到预期值 39。这两个通过样例只说明相应序列没有复现 stale seed，尚不能代替所有 EEW/LMUL/版本回绕条件的协议证明。

## 新确认的优化缺陷：短向量让不同 lane 选择不同传输协议

VMFPU 的 `vfu_operation_t.vl` 是分配给本 lane 的元素数，不是架构的总 VL。旧 `red_exact_sum_eligible()` 用局部 `vl>=1` 选择精确后端，而 SLDU 用总 VL 选择精确包协议。因此总 VL=1 时，lane 0 发送精确包，另外三个 lane 却仍走普通浮点树；SLDU 无法收齐同一种包。关闭规约优化的版本能完成相同的已初始化 mask 的 VL=1 测试，修复前优化版不能完成。相应现象也出现在修正过的 `vfredusum.c` 中：关闭优化通过，开启优化在短向量用例停住。

修复在 lane 的操作元数据中保留 `global_vl`，让精确后端的选择及精确流兼容性以架构长度判断。局部 `vl=0` 的 lane 仍参与协议：消费 operand queue 提供的单个占位 beat，以全零 active 位启动一次空子树累加；它不等待也不确认不存在的 mask token。只有真正有源元素的 lane 才使用 MASKU 的 valid/ready。架构 VL=0 仍不满足精确路径门禁，不能和“总向量非空但某 lane 分到零个元素”混淆。

新编译的 `short_fix` 整机已经使同步后的 `rv64uv-ara-vfredusum` 正常成功，源别名、特殊 seed 和稀疏窗口反例也重新通过。`initialized_masks_fix` 中初始化过 v0 的 VL=1 masked 用例返回 `2.0/fflags=0`，与关闭优化一致。进一步的 `reduction_audit_lengths` 覆盖 11 种 VL、FP32/FP16/FP16→FP32 三种格式、无 mask/全 active/全 inactive 三种模式，每例连续三条依赖规约；该 99 例组合回归随后发现了 FP16 尾部映射和 late-seed 生命周期错误，后文记录分项修复及复测结果。

## 本次重新测量的性能与硬件代价边界

`perf_off` 与 `perf_final` 使用同一 ELF、NrLanes=4、VLEN=1024，比较当前 RTL 关闭所有规约开关和开启完整 profile 的结果；每个探针都检查结果并以 `tohost=0` 完成。它们的测量区域位于输入初始化之后，可以避免把加载地址修复当作规约加速。

| 探针 | 关闭优化周期 | 开启优化周期 | 周期减少 |
|---|---:|---:|---:|
| 16 条整数求和流 `perf_integer_reduction_throughput_probe` | 309 | 160 | 48.22% |
| 有限数 min/max 流 `perf_reduction_minmax_stream_probe` | 411 | 261 | 36.50% |
| 非重复有序求和 `perf_ordered_nonduplicate_probe` | 2085 | 549 | 73.67% |

这些数据在多轮修复后均重新测量。最终 `ordered_final_token_fix` 与 `ordered_final_token_disabled` 包含全部十类修复，41 个源码文件 SHA-256 逐项一致，后一份 filelist 没有任何 `ARA_RED_*` define。三个探针使用相同 ELF，再次得到表中全部周期数并正常成功。最终记录在 `ordered_final_performance_comparison.json` 及两份编译目录的 `source_manifest.json`；此前 `full_final`、`epoch_valid_fix_v2` 和 `cache_lifetime_fix` 的测量保留作历史证据。数据不能外推为任意程序、任意 VL 的加速。减少排队和重叠计算的方向有实际作用，但普通数据的性能通过不能代替特殊值或协议边界验证。

精确后端并非无代价的控制优化。分段实现每 lane 有 16 个 49 位 bin，即仅这些 bin 就声明了 784 位状态，四 lane 合计 3136 位；此外还有特殊值状态、seed 元数据、上下文、包缓冲、SLDU 的 288 位根状态及中央舍入器。这个计数不是综合网表面积，未计入综合裁剪或映射效果。缺少同约束的标准单元综合、时序和功耗结果，因此本次只能支持周期收益，不能确认 PPA 净收益，也不能把 generic cells 数或源码行数当作面积证明。

### 历史定位过程与基线对照限制

早期 99 例长度组合测试在全 mask 依赖序列处停滞；拆分用例和波形定位后，已修复下文所述的 FP16 尾部映射和 seed 缓存生命周期问题。完整 profile 的 `lifetime_checks` 已通过全部 99 例。min/max 连续序列中独立的上下文切换问题也已由下文波形定位并修复；NaN 数值问题仍未关闭，不能用这些协议回归代替数值验证。

原样 `30c6971b` 的额外性能对照中，有限数 min/max 和非重复有序探针通过，但整数吞吐探针报告 `result=7fc (FAILED)`，因此该基线运行的周期数不能作为有效的整数性能对照。上表整数对照明确使用当前关闭优化 RTL，保持外围修复一致；不可把两种参照版本混写。源代码审阅、功能通过、周期测量和硬件成本应分别给出结论，任何一项都不能替代其他项。

### 旁路隔离结果

新编译 `chain_off` 保持完整 profile 的其他开关，只设置 `reduction_complete_4lane_chain_bypass=0`。同一 `reduction_audit_length_isolated` ELF 在完整旁路版不能完成，而在 chain-off 版中，VL=31 与 VL=32 的全 masked 三条依赖规约、随后 VL=1 的 FP16 规约全部正常通过。这把该最小反例的必要触发条件缩小到 chain-bypass 开关覆盖的机制，但还没有证明是 late-seed 表、operand forwarding 还是它们与其它接口的组合。

chain-off 下的完整 99 例回归最终在第 38 例明确失败：VL=5、FP16、无 mask 的三条依赖规约得到 13（`0x4a80`），预期应为 16（`0x4c00`）。因此关闭 chain bypass 只解决了上述隔离序列，不能宣称它解决整个长度矩阵，也不会以永久关闭功能代替根因修复。早期还尝试了 VCS loop-report 和 GDB 抽样。阈值 10000 会在初始化时误触发，调高阈值后也未得到确定的组合环证据。后续波形证明仿真时间持续前进，真正停滞原因是 seed 有效位被过早清除，见下文。

### 新定位的 FP16 尾部活动位错误

上述 13 对 16 的差异意味着每条求和漏掉一个 1。FP16 的 64 位 lane word 按逻辑元素顺序使用物理 slot 0、2、1、3，`ara_pkg::be()` 已按该布局生成尾部 byte enable。但精确路径原先直接把 `count>=1/2/3/4` 当作物理 slot 0/1/2/3 的 active 位，部分 beat 因而漏算或误算。VL=5 时 lane 0 的第二个逻辑元素在物理 slot 2，它被错误地排除。已将前台与提前推进路径统一改为先调用 `be()`，与 MASKU 的相同物理布局做 AND，再抽取各 FP slot 的 active 位；修复后在关闭 chain bypass 和开启完整 profile 两种配置中，99 组长度矩阵均正常通过。

### 波形确认的 late-seed 生命周期错误

`loop_wave/last_state.json` 与 `seed_state.json` 给出了更直接的证据：SLDU 正在处理 ID=1、seed_producer_id=0、seed_version=1 的第二条指令；第三条 ID=0、vd_version=3 已进入另一个队列槽。cache[0] 中的 payload 仍是 `0x3f800000`，vd=4、version=1 都正确，但 valid 已被新 ID=0 的接收逻辑清零。于是 SLDU 永远等不到已有数据的有效位。仿真时间仍在前进；此前 GDB 的组合求值栈不能据此证明零延迟组合环，这一方向已被更强的波形证据取代。

修复删除“接收新 ID 就失效旧 cache”的操作，只在新的 producer 完成时替换该槽。该选择依赖 SLDU 按序执行：旧结果的消费者排在新 producer 前面，会在新 producer 完成并覆盖槽之前绑定 seed。匹配仍要求 producer ID、vd 和版本一致。该修复保留链式旁路，不引入默认关闭功能的退化。

FP16 尾部映射修复的 `fp16_tail_checks` 已完成全部 99 组、每组三条依赖规约，并以 `tohost=0` 成功结束；这次编译明确关闭 chain bypass，以独立验证尾部逻辑。FP16 特殊值探针也正常成功。包含 cache 生命周期修复的完整 profile `seed_lifetime_fix` 也已编译完成，`lifetime_checks/manifest.json` 中七项全部通过：隔离长度序列、99 组长度矩阵、源别名、特殊 seed、seed 格式切换、链式旁路探针与稀疏窗口探针。每项均检查正常成功标志且没有断言或错误输出。


## 波形确认的上下文切换丢失 FPU 返回

连续的未掩码 min、未掩码 max 和全 masked min 在完整 profile 中停住，关闭优化能结束。`minmax_wave/full_history.vcd` 的 lane 3 在 444.5 ns 同时满足 `MFPU_WAIT`、后台有效、`red_stream_promote_foreground=1`、`vfpu_out_valid=1`、`vfpu_out_ready=1`，返回 tag 为 `0xa0`，对应后台 root 的槽 0。但下一拍 `red_context_pending_q` 仍为 `0001`，`valid_q` 为 `1100`，后台标志已清零，且之后没有新的 FPU 返回。这是已握手结果丢失导致的等待，不是 FPU 尚未算完。

组合逻辑先接收 tagged feedback 并更新 `red_context_*_d`，随后 `MFPU_WAIT` 把上下文重新初始化，再从 `_q` 恢复“后台状态”。恢复动作抹掉了同拍刚接收的反馈。修复让仍有活跃后台的退休路径跳过上下文初始化，也不再将反馈相关的下一拍状态重置为旧值；普通新指令仍正常初始化。后台调度器和同拍 root 直接晋升逻辑继续使用更新后的状态，没有关闭重叠执行。

新增 `reduction_audit_context` 用 source=2.0、seed=1.0 执行同类三条序列，预期依次为 1.0、2.0、1.0，且异常标志为零。同一 ELF 在 `seed_lifetime_fix` 中超时，在 `context_response_fix` 中返回全部预期结果并正常成功。后者的 99 例长度矩阵和已有 min/max 流探针也通过。原 NaN 探针现在能正常结束，返回与关闭优化一致的错误无穷值；因此协议修复通过不能写成 NaN 数值问题也已解决。记录位于 `context_response_before/manifest.json` 和 `context_response_checks_v2/manifest.json`，其中 NaN 项被如实保留为 FAIL。

此版本源码指纹保存在 `context_response_fix/source_manifest.json`，并附模拟器和 filelist 的 SHA-256。使用同一个 Git HEAD 的未提交工作树经历过多轮修复，不能仅凭 HEAD 判断旧日志测试的就是当前 RTL。此前顶层 `current_rtl_manifest.json` 对应更早版本，仍保留作为历史证据，不覆盖成新内容。


### 宽化输入诊断

`reduction_audit_widen_inputs` 先执行 FP32→FP64 有序规约，再切换到 FP16→FP32 masked 有序规约；源和 mask 放在栈上，用 vector CSR 同步，并在规约后把实际 v6 和 v0 存回独立对齐缓冲区核对。修复完整配置和关闭优化配置都返回第一项 73.0、第二项 37.0，mask 为 `aa/55`、popcount=8，16 个源值逐项正确，正常成功。记录位于 `widen_inputs_quiet_full` 和 `widen_inputs_quiet_off`。

此前逐项打印的诊断版本在 180 秒时限内没有结束；当时已输出的输入和结果正常，但这些运行仍记为 timeout。减少成功项的 UART 输出后保留全部比较，新 ELF 才正常完成。这个早期对照只支持“精心控制的同类运算可以正确完成”；当时没有解释旧 ISA 测试得到 53.0 的原因。后续已用指令追踪定位 VSET 未声明的 t0 修改，见后文，不能倒过来把早期诊断本身当成根因证据。


## 新确认的寄存器组版本遗漏

早期 `reduction_audit_group` 用整数规约读取覆盖后的 v9，不能充分检验浮点 seed requester 的 `source_version` 匹配。新增 `reduction_audit_group_fp` 改为 FP32 无序求和，使用最小次正规数的整数位型，确保 32+7 的结果没有舍入歧义：先产生 v9[0]=32，然后以 e32/m2 对 v8/v9 全组写入位型 7，再以 v9 为 seed 对 32 个位型 1 求和。`context_response_fix` 返回位型 64，而相同 RTL 关闭优化返回正确的 39；两者均正常结束，因此不是超时或输入未知导致的推测。

`ara_sequencer` 原先仅递增 `vreg_version[vd]`。写 v8/v9 时 v9 的版本仍保持不变，operand requester 的版本化缓存便把覆盖前的 v9[0]=32 当作当前 seed，得到 32+32=64。修复按目的 EMUL 更新组内每个寄存器各自的版本，分数 EMUL 仍更新一个寄存器，规约的标量目的也只更新一个寄存器。不能用源 LMUL 代替目的 EMUL，否则 widening 写入的第二个寄存器仍可能遗漏。

新编译 `group_version_fix` 已通过最小反例，结果由 64 恢复为 39。`reduction_audit_group_matrix` 的五项也全部通过，覆盖 m2/m4/m8 组内部寄存器、mf2 部分寄存器写入，以及 e16/m1 widening 产生 e32/m2 目的组；相同矩阵在关闭优化配置也通过。此版本还已重新通过上下文切换、99 组长度、源别名、特殊 seed 和链式旁路探针；三项性能探针仍为 160、261、549 周期。进一步的组向量源读取暴露了下文的读取端身份错误，不能由这些标量 seed 用例代替。

### 完整回归中的测试输入缺陷

`context_response_suite` 的 34 项中，18 个性能/数据流探针均通过；16 个 ISA 程序有 12 项无错误通过、2 项宽化数值失败、2 项整数 min/minu 触发 CVA6 未初始化读取断言。后两项虽打印 `tohost=0`，仍按 FAIL 保留。源码另外存在明确的输入缺陷：`VLOAD` 使用当前 VL，而测试用 VL=16 加载只含一个 seed 或两个 mask 字节的局部数组，存在越界读取；这项静态发现尚不能直接证明所有 cache 断言都由它导致。本次在 `vredmin.c`、`vredminu.c` 中为短数组设置实际加载长度，并在规约前恢复 VL=16，随后以同步测试配置重新编译。修正后的 min/minu 测试在开启和关闭优化配置中仍出现 CVA6 未初始化读取断言，虽然最终结果比较通过。这说明限定加载长度没有解决全部仿真环境问题，仍按 FAIL 记录，不能删除断言或直接重新标为通过。


### 同一问题的读取端：不能用组首版本匹配组内缓存

仅更新组内写入版本还不够。`reduction_audit_group_source` 先缓存 v9[0]=32，再对 e32/m2、VL=33 的 v8/v9 写入位型 7，最后规约整个 v8/v9 向量源。正确结果是 33×7=231；`group_version_fix` 返回 256，关闭优化返回 231。前 32 项正确，最后 v9[0] 被旧缓存位型 32 替代。

operand requester 的 `source_version` 来自请求的组首 v8，地址在多 beat 读取过程中却会进入 v9。缓存只比较该版本值和当前地址，会把 v8 的版本错误用于 v9；即使写入端已经更新 v9 的版本，也不能补救这个匹配错误。新增 `source_register` 保存版本所属的寄存器，只允许该寄存器首个 VRF word 命中规约标量缓存。请求跨到其他成员时按正常 VRF 读取，已有标量 seed 和以该寄存器为起点的消费者仍可使用缓存。源码没有为其他成员携带独立版本，不能假定组内所有成员的版本相同。

`group_source_fix` 已通过组向量源反例、五项组矩阵和链式旁路探针。版本回绕测试又确认了下文的独立缺陷。


## 新确认的缺省版本与 epoch 零混淆

`reduction_audit_epoch_zero` 对 v2 连续写入 255 次，使随后写 v2 的整数规约使用八位版本 0，并缓存位型 32；再把 v2 改为 7，让下一条整数规约以它为 seed。期望 32+7=39，而 `group_source_fix` 得到 64；关闭优化正常得到 39。现象与组写入无关，两条规约的源都只有一个寄存器身份。

原因是普通 ALU operand request 没有填写 `source_version`，结构的 `default:'0` 把它变成了零。缓存版本真的回绕到零时，这个缺省值恰好匹配旧 seed。缓存本身的 254 周期寿命限制不能阻止“缺失标签恰好等于有效标签”；这里的旧缓存是在回绕后刚刚填入，尚未超龄。

修复给普通 ALU 的 vs1/vs2 请求填入中央 sequencer 的实际版本，并在 operand command 和 requester 元数据中增加 `source_version_valid`。已有明确版本的 FP、store 和 MaskB 请求把有效位置 1，未提供版本的请求保持无效，不能命中依赖版本的缓存；零版本仍被视为合法值。`epoch_valid_fix_v2` 已编译完成，`epoch_valid_checks` 的 11 项全部正常成功且无断言报错：零版本反例恢复为 39，组源反例恢复为 231，五项组矩阵、99 组长度、源别名、特殊 seed、上下文切换、链式旁路和三项性能探针全部通过。最早的 `epoch_valid_fix` 因初始化编辑没有完整应用而主动取消，目录中留有 `DISCARDED.txt`，它不能作为测试证据。


## SLDU 分块合并的独立核查

新增 `gen_sldu_packet_oracle.py`、`sldu_packet_oracle_tb.sv` 和 `run_sldu_packet_oracle.py`。测试直接实例化真实 SLDU，包括请求队列、输入 spill、分块合并、最终舍入和输出队列；期望值由 Python 整数求和生成，不从 RTL 的分块加法结果倒推。`sldu_packet_repro/manifest.json` 记录 1200 例全部通过，包含 900 例 FP32、300 例 FP16，五种舍入模式各 240 例。测试覆盖正负抵消、跨 64 位边界进位、最高有效块附近的符号、2～5 块窗口、lane 独立延迟、输入气泡及输出阻塞；833 例的 lane 窗口长度不同。

每例同时比较完整 288 位根节点和、浮点结果、异常标志和返回 ID。输出先保持阻塞至少五拍，再让各 lane 独立接收，检查阻塞期间结果稳定、每个 lane 只收到一次结果、输入被完整消费以及最终退休。部分包头之前注入旧的无效 dummy token，检查包头会合的清理行为。该单元测试按顺序提交不同 ID 的上下文，不能单独证明 VMFPU 的跨指令提前释放；后者要结合整机链式测试和下述状态机约束。

源码中的进位界限可以直接核算：四个 64 位无符号块加上前一块的进位，最大为 `4*(2^64-1)+3 = 2^66-1`，所以 `chunk_sum[65:0]` 与两位 `exact_carry` 足够。某 lane 已超过自己在包头声明的窗口时，SLDU 提供全零或全一的隐式符号扩展，并将该 lane 的 ready 保持为零；其他 lane 仍需真实 valid。只有所有必需块都到齐，根节点、块号和进位才前进。各 lane 的压缩窗口额外保留一个完整符号保护块，四项相加最多需要额外两位，故这一保护块足够使提前结束时的最高块符号可用于扩展；五块模式只写第五块的低 32 位，组成 288 位根节点。数值不溢出的前提是前文列出的 VLEN 门禁。

包头匹配检查 magic、lane 身份与 instruction ID，仿真断言另检查格式、舍入模式、块数与 seed 所有者。VMFPU 仅在最后一块真正 `valid && ready` 时释放局部累加器，并转入 `EXACT_GLOBAL_RX`；它可开始累加后继，但仍需等待前驱完成和上下文晋升才会发布后继包头。因此一个已经结束的 lane 不会把后继包头混入前驱还在接收的块。该解释依赖当前状态机的发布顺序，不能仅凭 ready 信号推导任意生产者都安全。

复现命令如下，输出目录必须是新目录，以免覆盖历史证据：

```sh
python3 hardware/scripts/run_sldu_packet_oracle.py --filelist hardware/build/reduction_audit/epoch_valid_fix_v2/filelist/bender_script_default --out hardware/build/reduction_audit/sldu_packet_new
```

## 宽化失败的根因：测试宏改写了仍在使用的标量寄存器

`VSET` 原来执行 `vsetvli t0,...`，却没有向 C 编译器声明 t0 被写；`VSETMAX` 对 t1 也有同类问题。编译器合法地让指针跨该汇编语句保存在 t0 中，硬件则按指令把 t0 改为 VL。这不是规约求和的计算树差异。

`load_lifetime_full` 保存了修复前的直接证据。有序宽化用例在 PC `0x800001e4` 把 mask 数组地址 `0x80002878` 放入 t0；PC `0x800001f6` 的 `vsetvli` 把 t0 改为 2，随后两次 `lbu` 从地址 2 和 3 读得 `dc/ba`，因此 masked 求和使用了错误 mask，得到 53 而非 37。无序宽化用例则把结果缓冲区地址 `0x80003d80` 放在 t0，后续 `vsetvli` 将其改为 16；结果 store 和比较指针因而指向 `0x10`，最终读出 AXI 错误从设备的 `ca11ab1ebadcab1e`。此前只用 `%x` 打印 64 位值还把这一线索截成了低 32 位，现改用 `%lx`。

修复将不使用的 VL 返回寄存器改为 zero，并加上编译器 memory clobber。`vset_register_full` 与 `vset_register_off` 使用相同 ELF，两种配置中的有序、无序宽化程序都正常通过且没有断言失败。单独增加 VLOAD 后的同步、移除一个越界 seed load 均未解决旧失败，对应失败日志仍保留；不能把这些必要的测试卫生修正冒称为此次根因。修正前后的静态代码、指令追踪和开关对照共同支持上述定位。

## 整数 min/minu 告警：比较时连同未初始化尾部一起存回

旧测试在首次规约前未初始化 v3，规约只定义 v3[0]，随后 `VCMP_U8` 却按 VL=16 把整个向量存回。`min_tail_wave` 对同一失败 ELF 的波形显示：673.5 ns 的 `i_wt_dcache.rd_data` 为高 56 位 X、低 8 位全零；674.5 ns 的全 64 位已知性断言失败，而后续 `lbu` 提交值为零，正是正确的规约结果。因此旧日志里的 `xxxxxxxxxxxxxxxx` 不能解释为实际选取的结果字节错误，断言采样与告警打印也不在同一个组合逻辑时刻。

两个程序在第一次规约前增加 `VCLEAR(v3)`，定义之后可能被比较宏存回的所有尾部字节。`min_tail_full` 的两项均正常通过、没有读取 X 断言；没有修改 CVA6 断言，也没有在结果分类中忽略告警。该修正只使测试环境满足整字已知性的检查要求，不要求硬件在 tail-agnostic 策略下保留特定尾部值。关闭优化的相同 ELF 对照另记录在 `min_tail_off`。


## 缓存寿命必须包含在途版本余量

新增 `operand_cache_lifetime_tb.sv` 直接实例化真实 operand requester。测试先确认新鲜的有效零版本仍能转发，再保留一个版本为零、值为 32 的旧规约缓存；按接口允许的每拍一次写入速率推进普通写回，并提交同地址、版本再次为零、但新生产者仍有 RAW hazard 的请求。在 `cache_lifetime_before` 中，旧逻辑错误地转发 32。这个反例验证了请求端接口边界，不是由 CVA6 执行完整 256 次写入的整机程序；不能将两种证据混称。

原来 cache 的 age 从结果 grant 时从零开始，达到 254 才失效；版本号却在中央 issue 时增加。在旧结果刚写回时，后继可能已经占用在途槽并获得新版本。仅比较“254 小于 256”遗漏了这些提前增加的版本，也没有为插入、握手所在的边沿留余量。

修复将最大 age 改为 `2^VRegVersionWidth - NrVInsn - 2`；当前八位版本、八个在途槽得到 246。寄存器的正常 WAR/WAW 顺序保证同寄存器的后继写不会在旧生产者写回前完成，因此写回时领先的版本数受在途容量约束；按保守的 `NrVInsn` 计，再加缓存可被查询期间最多 `MaxAge+1` 次新发射，总数至多 `8+247=255`，严格小于一次 256 版本回绕。额外的两个边沿余量避免把失效边沿仍可观察到的旧 valid 误认为已失效。配置断言要求版本空间大于在途数加二。这一论证使用中央 sequencer 每拍最多发射一条指令的结构约束，没有依赖特定 CPU 程序“通常发得慢”。

`cache_lifetime_after` 已通过同一新鲜命中和回绕等待测试。补充的 `cache_lifetime_boundaries` 覆盖延迟 0、1、244、245、246、247、254 拍：界内正常转发，界外使用 VRF，等待中的新生产者不会被旧 cache 绕过，生产者完成后能继续正常读取。此修复保留缓存、late seed 和上下文重叠，仅缩短原先缺乏安全余量的八拍寿命。`cache_lifetime_fix` 的 11 项整机定向回归随后全部通过；最终 `ordered_final_token_fix` 也重新通过了同一组 11 项，不依赖旧版本日志作为最终回归结果。

```sh
python3 hardware/scripts/run_operand_cache_lifetime.py --filelist hardware/build/reduction_audit/epoch_valid_fix_v2/filelist/bender_script_default --out hardware/build/reduction_audit/cache_lifetime_new
```

## 完整寄存器检查发现的有序 masked 末项错误

`reduction_audit_tail` 的完整配置运行没有通过：前 38 个整数 opcode/宽度组合各六例均已完成，在 FP16 有序求和的第六例报告 `VL=15`、交替 mask 下得到 8（`0x4800`），而不是预期的 9（`0x4880`）。seed 为 2，十五个源元素均为 1，奇数索引 1/3/5/7/9/11/13 七项有效，故结果恰为 `2+7=9`，不存在舍入歧义。目的寄存器的尾部保持正确，失败发生在第零元素。

独立程序 `reduction_audit_ordered_fp16` 只运行这个边界，在 `cache_lifetime_fix` 中再次得到 8，在同源码关闭优化的 `cache_lifetime_disabled` 中得到 9 并正常通过。记录为 `ordered_fp16_full` 和 `ordered_fp16_off`，两者 ELF 相同。这是新增的整机优化反例，与前文 VSET 测试宏错误、未初始化尾部及继承的 NaN min/max 问题均不同。

`ordered_fp16_wave/lane0_events.json` 给出直接状态证据：1052.5 ns，lane 0 的 `osum_mask_skip_active=1`、`mfpu_red_valid_o && mfpu_red_ready_i=1`，`to_process_cnt_q=1`，组合逻辑把 `to_process_cnt_d` 减为零；此时输入 token 仍有效，数值为 `0x4800`，`mfpu_state_d` 却已经变为 `MFPU_WAIT`。1053.5 ns 发出的 VRF 写回正是 `0x4800`。lane 0 在跳过自己的最后一个元素时，把同一个尚待转发的输入 token 当成了所有 lane 已处理完的最终结果。

修复只改变 lane 0 的最终接收条件：要求 `to_process_cnt_q==0`，而不是在当前组合逻辑中刚刚变为零的 `_d`。这样，本地末项仍按原握手转发；等本地状态已确认完成后，再接收绕经剩余 lane 返回的最终 token。跳过 masked 项、输出旁路、跨 lane 路由及上下文重叠均保留。新编译 `ordered_final_token_fix` 已完成，`ordered_final_token_checks` 的四项全部通过：隔离反例恢复为 9，masked 有序别名、非重复有序和宽化有序三个探针也均正常成功。

为继续检查后续浮点用例，新增 `reduction_audit_tail_fp`，复用相同完整目的寄存器比较逻辑，覆盖剩下全部 16 个浮点 opcode/宽度组合、每组六例，共 96 例。原完整测试和隔离测试的失败均保留，不能把“部分边界已跑过”重写成 324 例全部通过。

## 有序浮点的舍入、异常和 inactive 语义

新增 `reduction_audit_ordered_rounding`，在 `ordered_final_token_fix` 中全部 30 例通过。FP16、FP32、FP64 各十例，第一组按顺序求 `0 + [2^p, 1, -2^p]`，其中 p 分别为 11、24、53。中间一步恰好落在两个可表示数的正中间：RNE/RTZ 得到正零，RDN 得到负零，RUP/RMM 得到 2，五者都设置 NX；若擅自重排为精确求和，很容易得到 1，因此这组数据能区别有序逐步舍入与无序精确和，而不只是检查普通整数式求和。

其余用例逐位检查全 inactive 时 qNaN seed payload 的复制、masked-off sNaN 不引入 NV、active sNaN 产生规范 NaN 并设置 NV、负零 seed 的原样复制，以及向下舍入的精确抵消产生负零。测试在 `vmv.x.s` 取得规约结果后再读取异常标志，避免把尚未完成时的 flags 当成最终值。依据为 [RVV 1.0 有序浮点规约规则](https://raw.githubusercontent.com/riscvarchive/riscv-v-spec/v1.0/v-spec.adoc)，运行证据在 `ordered_rounding_full/manifest.json`。它覆盖这三种格式的定向语义边界，不声称随机穷举全部 IEEE 输入。

原精确数值单元也用当前源码重新编译并保存了独立指纹：`numeric_single_final` 的 980 例、`numeric_multibeat_final` 的 1500 例均通过。`configuration_guards_final.json` 重新检查九个 Makefile 门禁组合：三种容量的边界值接受、翻倍值拒绝，以及完整 profile 在 2/8/16 lane 下拒绝；这些记录仅证明配置门禁，不代表所有允许参数都完成了 RTL 仿真。

## 复现与结果判定

下列命令假定仓库已有本次使用的 VCS、RISC-V LLVM 工具链和 Bender 依赖。先创建新的编译目录，避免同名模拟器被后续编译覆盖；使用完整 profile，不用关闭 chain bypass 或 context stream 来绕过反例。关闭优化对照使用相同源码、相同配置和独立目录，仅省略 `reduction_complete_4lane=1`。

```sh
make -C hardware compile reduction_complete_4lane=1 fail_on_assert=1 sim_dir=build/reduction_audit/reproduce_on vcs_library="$PWD/hardware/build/reduction_audit/reproduce_on/filelist" SIMULATOR_OPT='-full64 -sverilog +v2k -Mupdate -j8 -lca -kdb -debug_access+all +nospecify +notimingchecks +vpi +error+30'
make -C apps bin/reduction_audit_ordered_fp16 bin/reduction_audit_ordered_rounding bin/reduction_audit_tail_fp
python3 hardware/scripts/run_reduction_audit.py --sim hardware/build/reduction_audit/reproduce_on/simv --out hardware/build/reduction_audit/reproduce_cases --timeout 1500 --jobs 2 reduction_audit_ordered_fp16 reduction_audit_ordered_rounding reduction_audit_tail_fp
```

旧 ISA 程序使用 `ENV_DEFINES='-DRVV_TEST_QUIET -DRVV_AUDIT_SYNC'` 重新编译；这会启用 Ara 的向量 CSR 同步并减少 UART 进度输出。性能探针使用自身的测量区间，不能用这些同步 ISA 程序推导吞吐量。数值单元、SLDU 和缓存寿命各自有前文所列的生成器或 runner；它们不能代替整机上下文、寄存器和异常交互检查。

一次通过需要程序实际结束、出现明确成功标志、没有结果比较失败、没有断言失败或 watchdog。VCS 的零退出码本身不充分。本报告保留初始反例、修复前失败和继承缺陷，不通过删除失败日志、禁用断言或缩短向量使结果变绿。最终证据清单应同时记录模拟器 SHA、源码指纹、ELF SHA 和日志摘要；仅引用 Git HEAD 无法区分本次多轮未提交修复。

## 最终证据与适用范围

最终修复配置为 `ordered_final_token_fix`，同源码关闭优化配置为 `ordered_final_token_disabled`。两份编译清单的 41 个源码文件 SHA-256 一致，并已与当前工作树重新核对。源码、模拟器、ELF 与日志指纹及关键输出汇总在 [reduction_audit_evidence.json](reduction_audit_evidence.json)。完整原始日志与冻结的 ELF 保存在本地 `hardware/build/reduction_audit/`；该目录被 Git 忽略，因此证据摘要与原始日志的可获得性不同。

| 最终检查 | 结果 | 证据目录 |
|---|---|---|
| 18 个性能/数据流探针与 16 个 ISA 程序 | 34/34 程序通过 | `final_complete_suite` |
| 已修复反例、组版本、99 例依赖长度矩阵及链式探针 | 11/11 程序通过 | `final_targeted_checks` |
| 新发现的有序末项反例及三个有序探针 | 4/4 程序通过 | `ordered_final_token_checks` |
| FP16/32/64 有序舍入、NaN、异常和符号零 | 30/30 用例通过 | `ordered_rounding_full` |
| 完整目的寄存器的全部浮点组合 | 96/96 用例通过 | `tail_fp_final` |
| 同一完整寄存器矩阵的关闭优化对照 | 324/324 用例通过 | `tail_boundary_v2_off` |
| 精确数值单 beat、多 beat | 980/980、1500/1500 用例通过 | `numeric_single_final`、`numeric_multibeat_final` |
| 真实 SLDU 的分块数值与握手 | 1200/1200 用例通过 | `sldu_packet_repro` |
| 缓存新鲜命中、回绕等待及七个寿命边沿 | 全部通过 | `cache_lifetime_boundaries` |
| 同源码、同 ELF 周期对照 | 309→160、411→261、2085→549 | `ordered_final_perf_on`、`ordered_final_perf_off` |
| 九个参数接受/拒绝门禁 | 全部符合预期；仅为 Makefile 检查 | `configuration_guards_final.json` |

表中“程序”和“用例”是不同计数层级，不同批次还有重复探针，不能相加成所谓独立测试总数。数值单元、SLDU、完整寄存器检查与整机程序分别证明不同范围的行为，任何一类都不能替代其他类别。

完整目的寄存器矩阵的优化版本 `tail_boundary_v2_full` 在第 234 例失败，前 228 个整数边界已经完成；该失败促成 lane 0 最终 token 修复。修复后重测全部 96 个浮点边界并通过，覆盖原失败及所有后续浮点组合。最后一次 RTL 变化仅在 VMFPU 的有序最终 token 接收条件，不涉及 VALU 整数路径；最终 34 项整机回归也重新覆盖了整数规约。不能把这组分阶段证据改写为“最终优化 RTL 从头跑过一份 324 例 ELF”。初始 1296 例版本及一次编译失败误用旧 ELF 的运行已主动停止并标记，两者均不用于正确性结论。

`latest_nan_full` 与 `latest_nan_off` 使用相同 ELF 再次复现两个已知失败：全 NaN min 返回 `0x7f800000`，max 返回 `0xff800000`；全 inactive min 也返回正无穷，未复制 qNaN seed。两种配置都正常结束并由结果比较报告 FAIL。最后两项修复分别涉及缓存寿命与有序求和 token，并未修改 min/max 的 NaN 算法。因此常规回归通过不表示这些错误已经消失，修复这些继承缺陷是后续达到完整 ISA 正确性所需的工作。

本次已经完成源码归属、机制合理性、数值与协议边界、反例定位修复、定向和常规回归、同环境周期对照及教学说明核对。结论限定于已列出的配置和输入范围；未测试的参数组合、形式化全状态证明、应用级普遍加速以及同约束面积/时序/功耗收益均没有被本次证据建立。所有修改仍在 `reduction-optimization` 的未提交工作树中，没有推送。
