# NaN min/max 修复的移植与验证

本次从 `ara_dsa_signoff_integration` 的固定提交 `7d5d1829ff68baa223618a54807e6a2b4e2c9373` 审阅并选择性移植浮点 min/max 规约修复，目标为 `reduction-optimization` 当前工作树。没有合并该提交包含的大量无关 RTL、依赖和验证系统修改，也没有修改来源工作树。来源说明见该提交的 `verification/RVV1_DIFFERENTIAL_VALIDATION.md` 第 25.2 节；主要实现位于 `operand_queue.sv`、`vmfpu.sv` 及顶层活动信号连接。

## 修复为什么合理

浮点 minimumNumber/maximumNumber 在一个输入为 NaN、另一个为数值时选择数值。因此，原实现的正/负无穷填充会将全 NaN 的 min/max 结果错误地变成无穷。来源分支把无效位置替换为 quiet NaN，让真实数值仍能正常参与极值比较，全 NaN 的非空规约则得到规范 NaN。

仅替换填充值并不足够。当 `VL>0` 但所有源元素均被 mask 屏蔽时，min/max 必须逐位复制 seed，保留 NaN payload、sNaN 编码和符号零，而且不新增异常。来源分支保存 seed，累计源活动信息，并在最终写回时选择原始 seed。这两个机制必须配套。[RVV 1.0 规约规则](https://github.com/riscvarchive/riscv-v-spec/blob/v1.0/v-spec.adoc#vector-single-width-floating-point-max-and-min-reductions)与 [RISC-V 浮点规则](https://raw.githubusercontent.com/riscv/riscv-isa-manual/main/src/unpriv/f-st-ext.adoc)是结果与异常期望的依据。

## 为当前优化分支所作的适配

| 部分 | 当前实现与原因 |
|---|---|
| 填充值 | 同步替换 operand queue、VMFPU 普通路径和多上下文初始值中的 min/max 无穷填充；只改其中一个位置仍可能混入无穷 |
| 活动状态 | 每个 lane 按 instruction ID 保存 sticky activity，顶层按同一 ID 跨 lane 求 OR；状态在该 ID 接受新指令时清零，不在局部完成时清零 |
| seed 保存 | lane 0 按 ID 保存首次成功接收的原始 seed；前台、后台规约不会互相覆盖 |
| 写回选择 | 仅在最终 VRF 写回请求上选择空集合的原始 seed；同一个输出数据总线传输 SLDU 中间结果时不覆盖。operand requester 的结果缓存也能看到修正后的最终数据 |
| sNaN seed | 内部计算使用 quiet 后的 seed，最终只有全局存在活动源时才补报该 seed 的 NV；全屏蔽时返回原始 sNaN 且不报 NV。不能只用 lane 0 的 mask 判断，因为活动源可能全在其他 lane |
| 源 sNaN | inactive/tail 先被 quiet NaN 替换，真实 min/max 运算允许上报异常；有效 sNaN 源仍设置 NV，被屏蔽或位于尾部的 sNaN 不设置 NV |
| 尾部长度 | min/max 的真实源有效范围由 `vl - intra_op_rx_cnt_q` 决定，不能使用被中性填充和部分结果合并改变的工作计数 |
| 交错执行 | 保留上下文重叠、旁路和缓存，没有通过关闭优化规避问题 |

instruction ID 在整条指令完成前不会重新分配，是上述 bank 生命周期的前提。非零 lane 提前完成后仍保留活动证据，直到该 ID 接受后继指令；lane 0 写回时读取的是结果队列中的 ID，不是此刻正在执行的后台指令 ID。

本次只把空集合覆盖逻辑用于 `VFREDMIN/VFREDMAX`。来源分支还覆盖了无序求和，但当前分支无序精确求和有自己的 seed、特殊值和 finalizer 协议，不能将来源分支的末端覆盖逻辑直接套上去。

本地 FP8 定义为 E5M2，因此采用 `0x7e` 作为其 quiet NaN，quiet 位为 bit 1。来源代码中的 `0x7c` 不适用于这个格式；本次没有把它照抄成“已验证的 FP8 修复”。整机测试范围仍是 FP16/FP32/FP64。

## 移植测试额外发现的合并输入错误

首次移植版本 `on_v3` 已通过原来的两个 FP32 反例和 192 条混合规约，但新增 IEEE 测试在 FP16、VL=64、全 qNaN 输入下得到零。短向量或含零的有限数测试无法充分鉴别这个问题。

`fp16_wave/events.json` 的 lane 0 记录显示：2661.5～2664.5 ns 四个源 beat 均产生 `0x7e007e007e007e00`；2666.5 ns 发出 tag=`0x91` 的部分结果合并时，B/C 都为 quiet NaN，但 A 为零；2667.5 ns 返回值变成零。fpnew 的 ADD 使用 B/C，MINMAX 使用 A/B，原多上下文合并只赋值 B/C，因此 min/max 会取到默认 A 值。

修复给前台和后台的各个合并节点同时连接 A 与 C，使 ADD 和 MINMAX 都读取计划中的两个部分结果。这项是当前优化分支的适配性修复，不冒称为来源分支原有补丁。失败日志、冻结 ELF 和波形保存在 `hardware/build/reduction_audit/nan_import_20261010/`，没有覆盖成 PASS。

## 测试范围与结果

最终优化镜像为 `on_v4`，同源码关闭优化镜像为 `off_v2`，位于 `hardware/build/reduction_audit/nan_import_20261010/`。两者已核对 408 份编译输入及头文件指纹；最终验收全部完成，结果见下表。测试要求明确的 `Core Test *** SUCCESS *** (tohost = 0)`，同时无比较失败、断言失败和 watchdog。VCS 的零退出码本身不充分。

| 检查 | 优化开启 | 优化关闭 |
|---|---|---|
| 原有全 NaN 与全 mask 反例 | 2/2 程序通过 | 2/2 程序通过 |
| FP16/32/64 IEEE 边界 | 138/138 用例通过 | 138/138 用例通过 |
| 连续混合活动状态 | 48 组、192 条规约通过 | 48 组、192 条规约通过 |
| 无掩码 NaN/有限数流水流 | 48 组、192 条规约通过 | 48 组、192 条规约通过 |
| 相关回归 | 19/19 程序通过 | 未重复整套集合 |
| 完整目的寄存器检查（包含在上述回归中） | 96/96 浮点边界用例通过，每例比较 128 字节 | 未在本轮重复 |
| min/max 流周期数 | 261 | 411 |
| 非重复有序流周期数 | 549 | 2085 |

源码、模拟器、ELF、日志指纹、失败反例和关键输出已汇总到 [reduction_nan_minmax_evidence.json](reduction_nan_minmax_evidence.json)。最终定向集合为 `final_focused_on/off`，后台流为 `stream_on/off`，19 项相关回归为 `regression_on`，周期对照为 `performance_off`。完整日志、冻结 ELF 和波形保存在本地被 Git 忽略的构建目录，证据 JSON 可随代码提交；它不是原始大文件的替代品。

19 项相关回归包含六个浮点规约 ISA 程序、上下文和 seed 反例、30 例有序浮点语义、九个流式/精确/旁路探针，以及 96 例完整目的寄存器检查。这里程序与用例是不同计数层级，不能重复相加。初版较慢的 108 例程序在早期关闭优化镜像中也完整通过，但最终结论使用重编译后、双方相同 ELF 的 138 例集合。

同一行开关对照使用相同 ELF，性能周期仅为对应探针的 ROI，不是所有程序的收益。min/max 的 261/411 与移植前有效对照一致。功能修复没有增加该探针的周期数，但新增活动和 seed 状态的硬件成本没有经过 PPA 评估。

新程序 `reduction_audit_minmax_ieee` 使用独立整数位型期望，包含 FP16/32/64、min/max 各 23 种场景，共 138 例：全 qNaN、全 mask 的 qNaN/sNaN/负零 seed、活动源仅在其他 lane、有效与无效 sNaN、短向量尾部、正负零、正负无穷、有限数、VL=0 不写目的、已有异常标志保持，以及四上下文的长向量路径。通过 `vmv.x.s` 等待结果，再读取 `fflags`。

新程序 `reduction_audit_minmax_overlap` 在读取任何结果前连续发出四条活动状态不同的规约，重复八轮，并改变 NaN payload，覆盖三种宽度及 min/max，共 48 组、192 条规约。它检查数值、seed 原始位型和异常，结合源码的按 ID 状态保存验证相邻指令与 ID 复用，不声称穷尽所有停顿时序。

`reduction_audit_minmax_stream_nan` 单独使用无掩码、VLMAX 的 NaN/有限数序列，确保满足后台重叠执行的门禁。除了两种配置的整程序 PASS，`stream_wave/background_events.json` 在 0～2000 ns 窗口记录了 lane 0 的 158 次真实后台输入握手，其中 54 次为部分结果合并，全部满足 A=C。该短波形是路径取证，不冒充另一次完整程序通过。

首次构建的两个语法错误版本没有生成可用镜像，也没有启动程序；`on_v3` 的 FP16 全 NaN 失败则是有效整机反例。最终验收只使用明确绑定源码和模拟器指纹的 `on_v4/off_v2`。早期测试和失效版本均另存，不混入最终通过数。

## 复现方法

以下命令使用当前仓库已有的 VCS、Bender 和 RISC-V LLVM 环境。输出目录必须是新目录，避免覆盖历史证据。先编译成功，再运行程序；不得在编译失败后继续使用旧 ELF 或旧模拟器。

```bash
set -e
make -C hardware compile reduction_complete_4lane=1 fail_on_assert=1 \
  sim_dir=build/reduction_audit/nan_reproduce_on \
  vcs_library="$PWD/hardware/build/reduction_audit/nan_reproduce_on/filelist" \
  SIMULATOR_OPT='-full64 -sverilog +v2k -Mupdate -j8 -lca -kdb -debug_access+all +nospecify +notimingchecks +vpi +error+30'
make -C apps bin/reduction_audit_minmax bin/reduction_audit_minmax_masked \
  bin/reduction_audit_minmax_ieee bin/reduction_audit_minmax_overlap \
  bin/reduction_audit_minmax_stream_nan
python3 hardware/scripts/run_reduction_audit.py \
  --sim hardware/build/reduction_audit/nan_reproduce_on/simv \
  --out hardware/build/reduction_audit/nan_reproduce_cases_on \
  --jobs 2 --timeout 900 \
  reduction_audit_minmax reduction_audit_minmax_masked \
  reduction_audit_minmax_ieee reduction_audit_minmax_overlap \
  reduction_audit_minmax_stream_nan
```

关闭优化对照使用相同源码，把两个输出目录分别改为新的 `nan_reproduce_off` 和 `nan_reproduce_cases_off`，编译时省略 `reduction_complete_4lane=1`。这个对照仍包含本次基础正确性修复，不能称为原样 `30c6971b`。

本次测试配置为四 lane、VLEN=1024、FP16/32/64。不据此宣称 FP8、其他 lane 数或所有停顿组合已通过，也没有以功能测试替代面积、时序和功耗评估。

修复已保留在 `reduction-optimization` 工作树，包含选择性移植、按指令身份的并发适配和额外合并输入修复；没有提交或推送。该结论关闭了本文已复现的 NaN min/max 问题，不是对整个 Ara 或所有参数组合的完整 ISA 正确性证明。
