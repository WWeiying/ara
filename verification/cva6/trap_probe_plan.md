# 实际 SoC 异常、委托与 SSIP 诊断计划

## 目的与范围

本测试接在 Sv39 缺页重启验证之后，检查操作系统所依赖的异常载荷、权限委托和
`mret/sret` 返回。它不是完整 Linux 启动，也不是 CLINT、PLIC、定时器或外部中断
的验证。当前 SoC 外部中断输入接零，因此软件写入 `mip.SSIP` 产生真实可屏蔽
中断，而不是在 testbench 中 force 内部信号。

激励是 `apps/riscv-tests/isa/rv64uv/trap_state_prereq.c`。
`trap-prereq` suite 注册该测试，使用非 ZCC 的 scalar-C 构建。

| 操作 | M→M | S→M | U→M | S→S | U→S | tval 预期 |
|---|---|---|---|---|---|---|
| ECALL | 是 | 是 | 是 | 不支持委托 cause 9，不测试该组合 | 是 | 0 |
| EBREAK | 是 | 是 | 是 | 是 | 是 | 0 或故障指令 PC |
| C.EBREAK | 是 | 是 | 是 | 是 | 是 | 0 或故障指令 PC |
| 读取未实现 CSR `0xfff` | 是 | 是 | 是 | 是 | 是 | 当前配置返回指令字 `0xfff022f3` |
| SSIP | 是 | 是 | 是 | 是 | 是 | 0 |

共 24 个子用例，每个 18 项检查，加上 16 项 CSR 恢复检查，共 448 项。
illegal-instruction 返回具体指令字是当前 `TvalEn=1`、`ZERO_TVAL=0` 的平台约定，
不应写成所有 RISC-V 实现都必须返回指令字。
规范依据：[Machine trap value](https://docs.riscv.org/reference/isa/priv/machine.html)、
[Supervisor trap value](https://docs.riscv.org/reference/isa/priv/supervisor.html)。

## 运行前的静态假设

当前 decoder 在没有上游异常时先把原始指令位写入 `ex.tval`，为之后的非法指令
异常保存编码。ECALL 路径已在 R-90 修复；EBREAK 和中断选择路径仍需实测。

| 候选原因 | 必须同时捕获的信号 | 区分条件 |
|---|---|---|
| 译码默认指令编码泄漏到 breakpoint | 原始 16/32 位指令、展开指令、PC、上游 ex、译码后 cause/tval、issue 当前/下一态 | `ex_i.valid=0`，译码时 cause=3 且 tval=0x100073/0x9002；不是软件保存时才改变 |
| 中断接管普通指令时没有清 tval | pending/enable/delegation/global-enable、当前 privilege、译码 ex、发射握手 | 必须是最终选中的 interrupt cause，而非仅有 pending 电平；预测错误值等于被接管的原始指令 |
| issue/提交途中的异常混配 | fetch/issue PC 与指令、队列 q/d、valid/ack/flush、提交 PC/ex、CSR 更新 | 若译码正确但提交错误，沿指令身份和握手定位首次分歧；不能只凭相同 PC 配对 |
| trap 写错 M/S bank 或错误委托 | medeleg/mideleg、priv q/d、trap_to_priv、cause/epc/tval 两个 bank 的 q/d | cause、PC、payload 正确但目的 bank 错误，或 bank 正确而 xRET 恢复 privilege 错误 |
| 测试没有真正清除 SSIP，形成重复 trap | mip/sip 写入、mip q/d、软件读回、trap 次数、handler PC | 必须看 SSIP 清零后再返回；保留第一次快照，重复 trap 应报错，不能覆盖首错 |
| 测试退出 ECALL 被误认为待测 trap | 软件 phase、独立 primary/exit 计数、预期 PC、所有 trap 提交轨迹 | 正常 primary 每例一次；退出 trap 分开；仅 ECALL U→S 有额外 S→M 桥接 |
| 修复错误地清除所有 tval | illegal-CSR 原始编码、前序 Sv39 缺页 VA、提交 cause/tval | illegal-CSR 与 page fault 必须保留载荷，不能为了 ECALL/interrupt 清零而全局清零 |

这些是仿真前假设，不代表已复现。默认 `ZERO_TVAL=0`，只修改 CSR 中受
`ZERO_TVAL` 保护的条件，不能修复默认配置的泄漏。M-mode 条件中使用 `GPLEN-1`
而非 `XLEN-1` 的问题应另列配置覆盖，不能混成当前实验已证明的根因。

## 激励自检与探针采样契约

- M/S handler 使用独立保存栈、64 字节对齐；不用 printf、浮点或隐式向量计算。
- 每例只委托待测的同步 cause 或 SSIP，不把所有异常统一委托。
- 同步异常跳到已知恢复标签；中断保持 xEPC，继续被中断的指令。等待循环有界，
  指令固定为 32 位，检查中断 PC 落在该窗口且对齐。
- 清 SSIP 后先读回。清除失败则标记 fatal 并走退出路径，不重复 xRET 等待。
- 每例保存 primary cause/PC/tval/status/pending/次数；退出 M/S trap 单独检查。
  无错误时共 49 次 trap，39 次进入 M、10 次进入 S；这不是退休指令总数。
- 保存并恢复 16 项 CSR，检查恢复值；最后进入普通测试框架输出快照与检查结果。
- `trap_prereq_probe.sv` 绑定 `id_stage` 与 `csr_regfile`；decoder 是组合模块，
  不虚构其独立时钟。仅通过 `verify_extra_sources` 加入诊断镜像，不改变 DUT。
- 与已有 CSR/FPU 探针共用 pre-edge `#1step` sink，使用统一 cycle、epoch 与
  edge_time。`q/d` 是同一采样相位的当前状态和下一状态意图。
- 捕获异常相关的 fetch/decode/issue 状态、权限/中断控制改变、trap/eret 和尾拍；
  不把所有正常打印循环写入诊断日志。全程序 commit trace 用于补充指令身份。
- 每路有界 8192 行、唯一 END、无 dropped/truncated。完整性检查通过不等于功能
  正确，还须核对目标事件覆盖；组合 ex.valid 不等于实际 trap，valid 不等于 fire。
- 冻结 ELF、反汇编、RTL/依赖补丁、探针和日志哈希。同一轮捕获离线比较上述假设；
  只有缺失判别证据或准备验证明确修复时才增加诊断仿真。

## 预定验证顺序

1. 独立审查激励、CSR 恢复与探针覆盖；完成构建和反汇编核对。
2. 一次原 RTL 诊断运行，保留失败日志；无论 PASS/FAIL 都核查捕获完整性。
3. 找到沿数据通路的首次错误位置后，才修改对应 RTL，保持原 ELF 不变复测。
4. 运行 Sv39 页故障恢复、CSR/浮点 prerequisite 和普通 RVV 代表点，避免误清其他
   异常信息或破坏向量功能。诊断次数可以减少，必要的回归不能省略。

以上保留运行前假设和判定条件，不按结果倒改预期。执行结果单独归档在
验证报告第 106 节：一次原 RTL 运行定位两类 tval 错误，最小修复后相同 ELF
的 448 项检查通过，并完成四点相邻回归。原始失败记录仍保留，不改写成 PASS。
