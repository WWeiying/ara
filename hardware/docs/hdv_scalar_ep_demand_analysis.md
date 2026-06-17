# HDV Kernel EP 标量计算需求与标量后端实现选择分析

本文基于当前仓库中的 `apps/**/*.dump`、`hardware/src/hdv/*`、以及
`hardware/deps/cva6_hdv/hdv/cva6_hdv_scalar_backend.sv`，分析同一个 HDV
execute packet（EP）内可能暴露给标量后端的计算需求，并据此讨论当前标量后端的实现选择。

## 1. 统计口径

当前只有 `apps/vsaxpy_hdv/vsaxpy_hdv.dump` 真正带有 HDV hint header，因此只有它的 EP
边界可以认为是确定的。其它 dump 是普通 RISC-V/RVV 指令序列，只能用于估计“如果后续改造成
HDV hint/p-bit 程序，局部代码中可能出现什么类型的标量压力”。

因此本文同时使用两个指标：

| 指标 | 含义 | 用途 |
|---|---|---|
| `raw_scalar_run` | 在普通 dump 中，两个 vector 指令之间或 vector/branch 周围连续出现的标量指令数量 | 估计 kernel 局部标量压力和编译器生成代码的标量密度 |
| `win3_all32_scalar` | 假设当前 fetch packet 中业务指令大多为 32-bit，任意 3 条连续业务指令窗口内的标量指令数量 | 贴近当前 `NumSlots=6` 个 16-bit slot，即最多 3 条 32-bit 指令的 EP 容量 |

当前 VLIWPU 的 packet/EP 结构是：

- fetch packet 为 128 bit；
- 高 32 bit 是 RISC-V hint header；
- 低 96 bit 是 6 个 16-bit slot；
- 32-bit 指令占 2 个 slot；
- `MaxIssueSlots=NumSlots=6`，所以一个 EP 最多容纳 6 个 halfword slot；
- 如果 EP 中全是 32-bit 指令，一个 EP 最多容纳 3 条业务指令；
- 如果存在 compressed scalar 指令，同一个 EP 可以容纳超过 3 条标量指令，但这依赖具体编码和 p-bit。

所以，`raw_scalar_run=20/40/60` 这类数字不能直接解释成“一个 EP 要 20/40/60 发射”。这些大段通常来自编译器生成的地址计算、循环控制、scalar load/store、函数序言/尾声或展开代码。它们说明标量后端吞吐很重要，但在当前 EP 容量下不会被一次性送入同一个 scalar slice。

## 2. 当前真实 HDV 程序：`vsaxpy_hdv`

`vsaxpy_hdv` 当前的 HDV task 代码为：

```asm
80001000: vsetvli t0,a0,e32,m1
80001004: vle32.v v0,(a1)
80001008: sub a0,a0,t0
8000100c: li zero,0x2        # HDV_HINT
80001010: vle32.v v3,(a2)
80001014: slli t1,t0,0x2
80001018: vfmacc.vf v3,fa0,v0
8000101c: li zero,0x1f       # HDV_HINT
80001020: add a1,a1,t1
80001024: vse32.v v3,(a2)
80001028: add a2,a2,t1
8000102c: li zero,0x1f       # HDV_HINT
80001030: bnez a0,0x80001000
80001034: ret
80001038: nop
8000103c: li zero,0x1f       # HDV_HINT
```

按当前 hint/p-bit 和 VLIWPU 打包行为，循环主体中可以近似看成：

| EP | 指令 | 标量后端需求 | 说明 |
|---|---|---|---|
| EP1 | `vsetvli` + `vle32.v` | 0 | `vsetvli` 走 vector dispatch/Ara，VL 写回再回到 scalar backend |
| EP2 | `sub a0,a0,t0` + `vle32.v` + `slli t1,t0,2` | 2 integer ALU | 当前标量后端会串行执行 `sub` 和 `slli` |
| EP3 | `vfmacc.vf` + `add a1,a1,t1` + `vse32.v` | 1 integer ALU | vector 和 scalar 可并行启动，EP accepted 受较慢一侧限制 |
| EP4 | `add a2,a2,t1` + `bnez a0,loop` | 1 integer ALU + 1 branch | branch 产生 redirect，当前标量后端顺序执行 |

这个真实程序说明：即使是最简单的 vector loop，单发射标量后端也会在 EP2 和 EP4 上产生额外串行周期。`vsaxpy_hdv` 的同 EP 最大标量需求不是 6 发，而是 2 条简单标量操作；如果 branch 不能和 ALU 并行，则 EP4 也会被拆成两个标量执行步。

## 3. 手写 RVV kernel 的统计结果

下面表格只列具有代表性的 hand-written/vector kernel。`raw_scalar_run` 是普通 dump 中局部连续标量段，不等同于真实 EP 宽度；`win3_all32_scalar` 更接近当前 3 条 32-bit 业务指令 EP 的局部压力。

| Kernel/function | Vector 指令数 | `raw_scalar_run` | 类型构成 | `win3_all32_scalar` | 对标量后端的含义 |
|---|---:|---:|---|---:|---|
| `vsaxpy_hdv_task_start` | 5 | 3 | 2 ALU + 1 branch | 3 | 当前真实 HDV loop，2 ALU 或 ALU+branch 并行有价值 |
| `vsaxpy.loop` | 5 | 2 | 1 ALU + 1 branch | 3 | 改造成 HDV 后需求接近 `vsaxpy_hdv` |
| `vscopy.loop` | 3 | 3 | 3 ALU | 3 | 指针更新/计数更新集中，2 ALU 会明显优于单发射 |
| `vsswap.loop` | 5 | 3 | 2 ALU + 1 branch | 3 | ALU+branch 并行更合适 |
| `vsdot.dotp_loop` | 6 | 2 | 1 ALU + 1 branch | 2 | 单发射可跑，branch 并行能减少尾部开销 |
| `vsdwt.dwt_loop` | 9 | 5 | 4 ALU + 1 branch | 3 | 原始标量段较长，但当前 EP 一次最多暴露约 3 条 32-bit |
| `vsgemv.row_loop` | 13 | 5 | 1 LSU + 3 ALU + 1 branch | 3 | 需要 scalar LSU，且 ALU/LSU 可并行会有收益 |
| `vsspmv.row_loop` | 8 | 6 | 1 LSU + 4 ALU + 1 branch | 3 | 稀疏索引导致 scalar load 和地址计算压力更明显 |
| `vsgemm.k_loop_128` | 37 | 7 | 6 ALU + 1 branch | 3 | 主要是指针/循环控制；2 ALU 是合理起点 |
| `vsgemm.row_block_loop_128` | 16 | 6 | 6 ALU | 3 | 多个地址更新，单发射会拉长 EP accepted |
| `vgemm.c_col_loop` | 18 | 9 | 5 ALU + 4 LSU | 3 | scalar LSU 密度较高，LSU 成为关键资源 |
| `vssymv.row_loop` | 6 | 8 | 2 LSU + 2 scalar FP + 3 ALU + 1 branch | 3 | 少量 scalar FP 是真实需求，不能只做 integer backend |
| `vstrsm.update_loop` | 3 | 4 | 3 ALU + 1 branch | 3 | ALU+branch 并行可减少循环控制开销 |

这组 hand-written kernel 的聚合统计：

| 统计对象 | 数量 |
|---|---:|
| 参与统计的 hand/vector 函数 | 37 |
| `raw_scalar_run <= 3` | 12 |
| `raw_scalar_run = 4..6` | 18 |
| `raw_scalar_run >= 7` | 7 |
| `win3_all32_scalar = 3` | 34 |

解释：

- 大多数 hand-written kernel 在局部都能找到 3 条连续业务指令中全是标量或含 2 条以上标量的窗口。
- 标量操作类型以 integer ALU 和 branch 为主。
- BLAS/稀疏类 kernel 会出现 scalar LSU。
- `vssymv` 等少数 kernel 会出现 scalar FP。
- integer MUL/DIV 在这些手写 kernel 的同 EP 热路径中不明显，更多出现在 compiler-generated benchmark 中的索引计算。

## 4. Compiler-generated benchmark kernel 的压力

编译器生成的 benchmark dump 中有大量 vector 函数，原始标量段可以很长：

| Kernel/function | Vector 指令数 | `raw_scalar_run` | 类型构成 | `win3_all32_scalar` |
|---|---:|---:|---|---:|
| `dtype-conv3d.dp_fconv3d_CHx7x7_block` | 359 | 64 | 33 ALU + 27 LSU + 3 MUL/DIV + 1 branch | 3 |
| `fconv3d.fconv3d_CHx7x7_block` | 359 | 64 | 33 ALU + 27 LSU + 3 MUL/DIV + 1 branch | 3 |
| `lavamd.kernel_vec` | 224 | 50 | 35 ALU + 13 LSU + 1 MUL/DIV + 1 branch | 3 |
| `fmatmul_vec_16x16` | 67 | 41 | 17 ALU + 24 LSU | 3 |
| `iconv2d_7x7_block` | 381 | 38 | 15 ALU + 23 LSU | 3 |
| `softmax_vec` | 59 | 26 | 17 ALU + 9 LSU | 3 |
| `conjugate_gradient.CG_iteration_spmv` | 30 | 24 | 12 ALU + 11 LSU + 1 branch | 3 |

这些数据说明两件事：

1. 如果未来要让 HDV 覆盖完整 Ara benchmark，而不是只跑手写 micro-kernel，标量后端不能只支持 ALU/branch。Scalar LSU、CSR、FP、MUL/DIV 都需要保留。
2. 这些很大的 `raw_scalar_run` 不意味着要做 16/32/64 发射标量后端。当前 EP 容量仍限制一次进入 scalar backend 的真实指令数。更有效的优化方向是减少每个 scalar slice 内的串行周期、提高 scalar LSU 接口效率、以及让 vector operand snapshot/dispatch 不被 scalar 后端过度反压。

## 5. 当前 HDV 和真实 C66x VLIW 的差距

HDV 的目标是借鉴 VLIW-style 的显式并行表达，而不是完整复刻 C66x。这个区别很重要，因为它直接决定标量后端应该做多宽、依赖由谁保证、以及跨 fetch packet 打包是否合理。

### 5.1 C66x 的关键 VLIW 语义

根据 `docs/2010_C66x CPU and Instruction Set Reference Guide_文档.pdf` 中 3.5 节和相关章节，C66x 的核心语义可以概括为：

| 项目 | C66x 行为 |
|---|---|
| Fetch packet | 每次取 8 个 word，即 256 bit，fetch packet 256-bit 对齐 |
| Execute packet | 由 p-bit 串接形成，同一 EP 内指令同周期并行执行 |
| EP 最大宽度 | 最多 8 条指令 |
| p-bit 语义 | p-bit=1 表示下一条指令与当前指令并行；p-bit=0 表示当前 EP 结束 |
| 跨 fetch packet | EP 可以跨 fetch packet 边界，但仍受最多 8 条指令限制 |
| 功能单元约束 | 同一 EP 内每条指令必须使用不同 functional unit |
| 分支到 EP 中间 | 架构允许分支到 EP 中间，但低地址处同 EP 指令会被忽略；文档也指出这容易导致错误 |
| 异常约束 | 同一 EP 两个 taken branch、跳到 header、跳到 header-based 32-bit 指令中间等会成为异常/非法情况 |
| Loop buffer | C66x 有显式 SPLOOP loop buffer，可存最多 14 个 execute packets，服务软件流水循环 |

C66x 是一种“ISA/汇编级显式调度”的 VLIW：编译器/汇编器不仅标出哪些指令并行，还要保证 functional unit、寄存器时序、branch delay、条件执行、loop buffer 等规则。硬件按照这些显式编码执行，而不是在运行时自由重排。

### 5.2 当前 HDV 的实现语义

当前 HDV 的对应机制是：

| 项目 | 当前 HDV 行为 |
|---|---|
| Fetch packet | 128 bit，其中高 32 bit 为 RISC-V hint header，低 96 bit 为 6 个 16-bit slot |
| p-bit 来源 | hint immediate 中的 `p_bits`，当前为 `NumSlots-1=5` 个相邻 slot 关系 |
| EP 最大容量 | `MaxIssueSlots=6` 个 halfword slot；全 32-bit 指令时最多 3 条业务指令 |
| 指令类型 | RISC-V scalar + RVV vector 混合，不是 C66x fixed functional-unit ISA |
| Functional unit 约束 | VLIWPU 只做基本 class 和 dep-break；没有 C66x 那种每条指令显式指定 `.L/.S/.M/.D` functional unit 的完整资源模型 |
| 同 EP 执行 | HEU 把 EP 分成 scalar slice/vector slice；vector 发 Ara，scalar 发 `cva6_hdv_scalar_backend` |
| Scalar slice | 当前后端按 slot 顺序串行执行，不是真正同周期多发 |
| Vector slice | 发送给 Ara，Ara 内部有自己的队列/依赖处理 |
| 分支 | 当前要求 branch target 最好是 fetch packet/HDV_HINT 后的 EP 起点，16B 对齐；不支持 C66x 风格“跳进 EP 中间后低地址指令忽略”的完整语义 |
| Loop lock | 当前偏向自动检测/缓存 fetch packet，尚未等价于 C66x SPLOOP 的软件流水 loop buffer 语义 |

所以，当前 HDV 更准确的定位是：

- 前端编码借鉴 VLIW p-bit；
- 后端是“scalar/vector 异构双后端”；
- vector 后端依赖 Ara 自身处理；
- scalar 后端当前是顺序执行的 CVA6-style backend；
- 整体是 VLIW-driven hybrid decoupled architecture，而不是完整 C66x-style VLIW core。

### 5.3 主要差距

#### 5.3.1 EP 宽度差距

C66x 一个 EP 最多 8 条指令；当前 HDV 一个 EP 最多 6 个 halfword slot。若全是 32-bit RISC-V 指令，只能容纳 3 条业务指令。

这意味着当前 HDV 的标量后端即使做到 4-wide 或 8-wide，也很难在现有 EP 编码下吃满。除非未来：

- 扩大 fetch packet；
- 增加业务 slot 数；
- 大量使用 RVC compressed scalar；
- 或引入更强的跨 fetch packet EP 串接语义。

#### 5.3.2 功能单元模型差距

C66x 每条指令天然绑定 functional unit，VLIW packet 的合法性包含 functional unit 不冲突。当前 HDV 的 RISC-V 指令没有这种 ISA-level functional unit 字段，VLIWPU 只能通过 opcode/class 粗分 scalar/vector/system/branch，再靠后端处理具体资源。

因此，如果要向真实 VLIW 靠近，HDV 需要增加一个更明确的 resource model，例如：

| 资源类 | 可能映射 |
|---|---|
| `S_ALU0/S_ALU1` | integer add/sub/logic/shift/address update |
| `S_BR` | branch/jal/jalr/ret |
| `S_LSU` | scalar load/store |
| `S_MUL` | integer mul/div |
| `S_FPU` | scalar F/D |
| `V_DISP` | vector dispatch/Ara issue port |

VLIWPU 或离线打包工具需要保证同一 EP 内资源不超配；标量后端则按照资源类真正并行执行。

#### 5.3.3 依赖语义差距

C66x 的并行性主要由编译器/汇编器静态保证。当前 HDV 同时有：

- hint p-bit 给出的静态并行关系；
- `ctrl_vliwpu_dep_break_i`/内部依赖检测对 p-bit 进行保守打断；
- vector backend/Ara 自身的动态队列和依赖处理；
- scalar backend 当前顺序执行，实际没有充分兑现 EP 内并行。

这比纯 VLIW 更“动态”，也更保守。它降低了编译器难度，但硬件复杂度和语义边界会变模糊。

#### 5.3.4 Branch/redirect 差距

C66x 文档讨论了 branch into middle of execute packet 的语义：跳到 EP 中间时，低地址处同 EP 指令被忽略。但这不是推荐写法，且可能导致结果错误。

当前 HDV 选择更简单的约束：

- branch target 必须是 fetch packet/HDV_HINT 后的 EP 起点；
- 最好 16B 对齐；
- redirect 后 IPU 从目标 fetch packet 开始取；
- VLIWPU 从 slot0 重新打包。

这个约束牺牲了一部分 C66x 灵活性，但显著简化了：

- IPU redirect；
- VLIWPU slot head 管理；
- carry/cross-packet 状态恢复；
- exception/interrupt restart；
- loop lock 命中判断。

对当前 HDV 原型来说，这个取舍是合理的。

#### 5.3.5 Loop buffer 差距

C66x SPLOOP loop buffer 是显式 ISA 机制：软件标出 loop body，硬件以 execute packet 为粒度缓存和调度，还支持 prolog/kernel/epilog 的软件流水语义。

当前 HDV 的 loop lock 更接近 instruction prefetch/cache 优化：

- 自动检测跳回已缓存区域；
- 尽量减少重复取指；
- 没有 SPLOOP/SPKERNEL/SPMASK 这类显式 loop ISA；
- 不表达软件流水 stage、kernel overlap、epilog drain 等语义。

所以当前 loop lock 可以降低取指开销，但还不能称为 C66x-style loop buffer。

## 6. 跨 fetch packet 打包 EP 是否偏离 VLIW

结论需要分两种情况。

### 6.1 若有显式跨边界 p-bit，则不偏离 VLIW

C66x 明确允许 execute packet 跨 fetch packet 边界。关键条件是：跨边界仍然由 p-bit 链显式定义，并且 EP 总宽度不超过架构限制。

因此，跨 fetch packet 本身不是问题。真实 VLIW 不要求 EP 必须完全落在一个 fetch packet 内；它要求：

- EP 边界由 ISA-visible 或 assembler-visible 的并行位明确表达；
- 编译器/汇编器负责保证同 EP 内无非法依赖和资源冲突；
- 硬件只按显式边界组包和发射；
- branch/exception/restart 能恢复到合法 EP 位置。

如果 HDV 未来给 header 增加明确的“跨包 continuation p-bit”，例如：

- 当前 packet 最后一条业务指令可以通过 header bit 表示“与下一 fetch packet 第一条业务指令并行”；
- 或把 p-bit 定义为连续 instruction stream 的边，而不是只定义 packet 内相邻 slot；
- 或由离线 packer 在跨包处插入明确 continuation metadata；

那么跨 fetch packet EP 与真实 VLIW 是一致的。

### 6.2 若没有显式跨边界 p-bit，而由硬件自行合并，则偏离静态 VLIW

当前 `hdv_vliw_pack_unit.sv` 已有 `tail_cross_candidate/carry_valid` 机制：当一个 packet 尾部 EP 没有控制指令、还有空余 issue slot，并且下一个 packet 已经到达时，可以把尾部 carry 到下一包开头进行 cross-packet compaction。

这个机制对性能有利，但从“严格静态 VLIW”角度看有一个问题：当前 header 只有 packet 内 `p_bits[NumSlots-2:0]`，没有一个独立、显式的“上一包最后一条业务指令与下一包第一条业务指令并行”的 ISA 级 p-bit。

因此，如果跨包合并只由硬件根据“还有空位、无控制、无 dep_break”来决定，它更接近：

- 运行时动态打包；
- 小型 issue queue compaction；
- trace/packet fusion；
- VLIW-inspired dynamic scheduling。

这不是错误设计，但语义上已经从 C66x-style static VLIW 向 dynamic packing 偏移。

### 6.3 当前 HDV 应如何定义跨包打包

为了避免语义混乱，建议把 HDV 跨包打包分成两个层级：

| 层级 | 语义 | 建议 |
|---|---|---|
| Strict VLIW mode | 只有显式 p-bit/metadata 允许跨包时才跨包 | 用于后续对齐 C66x/VLIW 语义 |
| Opportunistic fusion mode | 硬件可在无控制、无依赖、资源允许时跨包融合 | 可作为性能优化，但文档和 RTL 参数必须明确这是动态优化 |

当前代码更接近第二种。若希望向真实 VLIW 过渡，应逐步把跨包条件从“硬件猜测可合并”改成“header 明确授权可合并 + 硬件做安全校验”。

建议增加如下约束：

1. 跨包 EP 必须有显式 continuation bit。
2. continuation bit 必须由离线打包器/汇编宏生成。
3. branch/system 指令不得跨包参与 fusion。
4. branch target 仍只允许指向 EP 起点，不支持跳入跨包 EP 中间。
5. 若发生 redirect/flush，VLIWPU 必须清空 carry 状态。
6. loop lock 缓存命中时，跨包 EP 的两个 fetch packet 必须同时有效，或者禁止跨 buffer 边界 fusion。

这样既保留跨包打包的性能潜力，又不会让 HDV 的程序语义变成隐式动态调度。

## 7. 当前标量后端实现选择

当前 `cva6_hdv_scalar_backend` 的关键行为：

- 一次从 HEU 接收一个 EP 的 scalar slice；
- `scalar_ready_o = (state_q == IDLE)`，后端忙时不能接收新的 scalar slice；
- `scalar_accepted_o = (state_q == DONE)`，表示当前 scalar slice 中所有 scalar slot 都已处理完；
- 通过 `curr_slot_idx` 找最低编号有效 slot；
- 一个周期或一个多周期状态机只处理一条 scalar 指令；
- ALU/branch/CSR 类通常在 `EXECUTE` 状态清 slot；
- MUL 进入 `WAIT_MULT`；
- FPU 进入 `WAIT_FPU`；
- load/store 进入 `LSU_AR/LSU_R/LSU_AW/LSU_W/LSU_B`；
- 完成一个 slot 后再处理下一个 slot；
- 直到 scalar slice 清空后才 accepted。

这是一种功能优先、面积较小、控制简单的设计。它和当前 HEU 的保序模型匹配：HEU 只有在 scalar/vector slice 都 accepted 后，才认为 EP accepted，之后再推进后续 EP 或处理 redirect。

但性能代价也很明确：

- 同一个 EP 内本来被 p-bit 标记为可并行的多个 scalar 指令，在后端内部被串行化；
- EP 中含 `ALU + branch` 时，branch redirect 至少要等前面的 ALU slot 处理完；
- EP 中含 `ALU + scalar load` 或 `scalar load + scalar FP` 时，LSU/FPU 的多周期状态会拖住整个 scalar slice；
- 因为 `scalar_ready_o` 只在 IDLE 拉高，HEU 不能连续灌入多个 scalar slice。

## 8. 单发射是否太窄

结论：**对于功能验证，单发射足够；对于完整 Ara benchmark 的性能目标，单发射偏窄。**

原因如下：

1. `vsaxpy_hdv` 已经有 2 条标量操作落在同一个 EP 的情况。
2. 大多数 hand-written vector kernel 的局部窗口中，3 条业务指令内经常有 2 到 3 条标量指令。
3. 当前 p-bit 的语义本来就是表达并行关系；如果标量后端永远单发射，HDV 只能在 vector/scalar 跨后端并行上获益，无法利用 EP 内多条 scalar 的并行性。
4. 但当前 EP 容量只有 6 个 halfword slot，因此直接做 4/6 条完整标量通路收益有限，尤其在全 32-bit 指令场景下，一个 EP 最多只有 3 条业务指令。

所以更科学的判断是：

- 1-wide：实现简单，适合 bring-up，但会成为明显瓶颈；
- 2-wide integer ALU + branch：性价比最高，能覆盖 `vsaxpy_hdv`、copy/swap/dot/dwt/gemm loop 中最常见的组合；
- 3-wide full scalar：只有在大量 compressed scalar、更宽 EP 设计、或显式跨 fetch packet VLIW continuation 稳定后才更有必要；
- 4-wide 或更宽：当前 EP 容量下容易面积/时序投入大于收益。

如果保留当前 opportunistic cross-packet fusion，3-wide scalar 的收益会略升高，因为不同 packet 的尾部/头部可能被压入同一 EP。但这仍不支持直接做 4/8-wide：当前融合后的 EP 仍受 `MaxIssueSlots=6` 限制，全 32-bit 指令最多 3 条业务指令。

## 9. 推荐的后端结构

建议把标量后端分成“可并行的简单通路”和“保守串行的复杂通路”。

### 9.1 第一优先级：2 ALU + branch

推荐配置：

| 资源 | 建议 |
|---|---|
| Integer ALU | 2 lanes |
| Branch | 1 lane，最好可与 ALU 同周期执行 |
| XRF read | 至少支持两个简单指令并行读操作，或通过 operand predecode/复制读口降低冲突 |
| XRF write | 至少支持 2 个 integer 写回，或增加同周期写回仲裁/旁路 |

理由：

- `vsaxpy_hdv` 的 EP2 是 `sub + slli`，2 ALU 可一拍完成；
- EP4 是 `add + bnez`，ALU+branch 可一拍解析 redirect；
- `vscopy/vsdwt/vsgemm/vsspmv` 等 loop 的主要标量压力是地址更新、计数更新和 branch；
- 2-wide 是当前 EP 容量下最稳健的收益点。

### 9.2 第二优先级：1 scalar LSU

推荐配置：

| 资源 | 建议 |
|---|---|
| Scalar LSU | 1 lane |
| Outstanding | 初期 1 个即可，后续可考虑 2-entry load buffer |
| Load writeback | 与 ALU 写回仲裁 |

理由：

- `gemv/spmv/vgemm/fmatmul/fconv/lavamd` 都有明显 scalar LSU 压力；
- 但同一个 EP 内做多个 scalar memory request 会显著增加 AXI/异常/对齐/写回复杂度；
- 先做单 LSU，更符合面积和控制复杂度约束；
- 性能优化重点应是减少 LSU 阻塞整个 scalar slice 的时间，而不是一开始做多 LSU。

### 9.3 第三优先级：保留 scalar FP，但不急于多发

推荐配置：

| 资源 | 建议 |
|---|---|
| Scalar FPU | 1 lane，多周期 |
| 支持范围 | F/D 基本计算、`fmv/fcvt/fclass/compare`、scalar FP load/store |
| 写回 | FRF/XRF 仲裁 |

理由：

- `vssymv` 等 kernel 里确实有 scalar FP；
- 完整 Ara benchmark 目标要求保留 F/D；
- 但 scalar FP 在同 EP 热路径中的密度低于 integer ALU/LSU；
- 多发 scalar FP 的面积和时序成本较高，初期不划算。

### 9.4 MUL/DIV：单个多周期单元即可

推荐配置：

| 资源 | 建议 |
|---|---|
| Integer MUL/DIV | 1 个多周期单元 |
| 发射 | 与复杂通路串行 |

理由：

- hand-written RVV kernel 中 MUL/DIV 同 EP 热点不明显；
- compiler-generated benchmark 中会出现 MUL/DIV，但通常不是同 EP 高并发；
- 多个 MUL/DIV lane 面积大，收益不如 2 ALU + LSU。

### 9.5 如果向 C66x-style VLIW 靠近，标量后端还缺什么

如果目标从“HDV 原型可运行”进一步提升为“更接近真实 VLIW”，标量后端需要从顺序 FSM 演进为一个小型 in-order multi-lane backend：

| 能力 | 当前状态 | 向 VLIW 过渡的需求 |
|---|---|---|
| EP 内并行 | 当前 scalar slots 顺序执行 | 支持多个 lane 同周期 issue/execute |
| 资源检查 | 后端隐式串行，因此资源冲突自然消失 | VLIWPU/后端需要显式检查 ALU/BR/LSU/FPU/MUL 资源 |
| 寄存器文件 | 单指令读写模型更简单 | 需要多读口/多写口或 bank/replica/仲裁 |
| 写回冲突 | 串行执行天然避免 | 同 EP 多写回必须禁止同 rd 或定义优先级，最好由 packer 禁止 |
| branch | 串行解析 | 一个 EP 内最多一个 branch，branch lane 独立解析 |
| scalar LSU | 串行 AXI FSM | 至少允许 simple ALU 与 LSU request 重叠 |
| accepted 语义 | scalar slice 全部完成后 accepted | 保持这个语义，但内部用 per-lane done 汇聚 |

这个演进方向比直接搬完整 CVA6 issue/scoreboard 更合适。因为 HDV 的 p-bit/EP 已经提供了“同 EP 可并行”的静态信息，不需要重新实现一个复杂 out-of-order 或完整 superscalar issue。

## 10. 对当前实现的辩证评价

当前实现的合理点：

- 复用 CVA6 decoder/ALU/branch/mult/FPU 思路，避免完全手写 ISA 语义；
- 用一个小 FSM 接 HDV scalar slice，接口清楚；
- `scalar_accepted_o` 表达“对后续 EP 安全完成”，语义保守正确；
- 对 bring-up、分支 redirect、vset 写回 hazard、vector scalar operand service 都比较友好；
- 面积和控制复杂度低。

当前实现的不足：

- EP 内 scalar 指令全部串行，违背 VLIW/p-bit 的并行表达能力；
- `scalar_ready_o` 只在 IDLE 拉高，不能缓存下一组 scalar slice；
- ALU/branch 没有并行，循环尾部 redirect 延迟偏大；
- scalar LSU/FPU 会阻塞整个 scalar slice，复杂指令和简单指令不能重叠；
- 如果未来把更多 Ara benchmark 转成 HDV hint 程序，单发射会成为稳定瓶颈。

需要注意的边界：

- 不应为了 `raw_scalar_run=64` 直接设计 64-wide 或 8-wide 标量后端，因为这不是当前 EP 中真实同时发射的指令数；
- 也不应只看 `vsaxpy_hdv` 得出“2 条标量已经足够所有 benchmark”的结论，因为更复杂 kernel 有 scalar LSU/FP/MUL/DIV 需求；
- 不应把当前跨包 fusion 直接描述成严格 C66x-style VLIW，除非补上显式跨包 p-bit/continuation metadata；
- 最合理的路线是先把同 EP 最常见的简单标量并行利用起来，再逐步处理复杂通路的非阻塞化。

## 11. 向真实 VLIW 过渡的实现路线

### 阶段 A：保持当前单发射，作为功能基线

目标：

- 确认完整 RV64IMC + F/D + Zicsr 用户态标量语义覆盖；
- 确认 branch redirect、vset 写回、vector operand snapshot 正确；
- 用真实 benchmark 找出 unsupported 指令。

这个阶段不追求性能，只保证 correctness。

### 阶段 B：明确 HDV VLIW 语义边界

目标：

- 文档和 RTL 参数中区分 strict VLIW mode 与 opportunistic fusion mode；
- 默认先按 strict VLIW mode 推进工具链和程序语义；
- 若开启跨包 fusion，必须明确它是动态优化，不是 ISA 必须依赖的行为。

建议：

- 新增 `EnableCrossPacketFusion` 参数；
- 新增 `RequireExplicitCrossPacketPbit` 参数；
- 在 strict mode 下，若没有显式 continuation bit，禁止跨 packet EP；
- 在性能实验中可以打开 opportunistic mode，但 benchmark 结果要标注。

### 阶段 C：增加 2-wide simple scalar issue

目标：

- 同一 scalar slice 中选择最多 2 条 simple ALU 指令并行执行；
- 支持 `ALU + branch` 同周期执行；
- 对同 EP 内写同一寄存器、读写冲突做静态/动态保护。

关键前提：

- VLIWPU/p-bit 已经保证同 EP 内无数据依赖；
- 后端仍要防御非法情况，例如两个 lane 同时写同一 rd；
- branch redirect 要保持唯一，含多个 control-flow 的 EP 应该禁止或只允许第一个。

### 阶段 D：增加 VLIW resource model

目标：

- VLIWPU 或离线 packer 为每条指令标出资源类；
- 同一 EP 内资源不超配；
- 后端按照资源类分派到 ALU/BR/LSU/FPU/MUL/vector dispatch。

最小资源表：

| Resource | 初期数量 | 说明 |
|---|---:|---|
| `S_ALU` | 2 | integer simple ops/address update |
| `S_BR` | 1 | branch/jal/jalr/ret |
| `S_LSU` | 1 | scalar load/store |
| `S_MUL` | 1 | integer mul/div，多周期 |
| `S_FPU` | 1 | scalar F/D，多周期 |
| `V_DISP` | 1 | Ara vector request dispatch |

### 阶段 E：simple lane 与复杂 lane 解耦

目标：

- ALU/branch 可以和 LSU/FPU/MUL 的请求发起重叠；
- scalar slice accepted 仍等待所有 lane 完成；
- 复杂 lane 用 busy bit 或 per-slot done bit 管理。

这样可以改善 `vsgemv/vsspmv/vssymv/fmatmul/fconv` 等 kernel 中 scalar LSU/FP 拖住简单地址更新的问题。

### 阶段 F：增加 scalar slice skid buffer

目标：

- 标量后端忙时 HEU 可提前交付下一组 scalar slice；
- 后端内部按 EP 顺序提交 accepted；
- 不破坏 vector operand snapshot 和 branch redirect 顺序。

这一步对持续供指有帮助，但复杂度高于简单 2 ALU；应在 operand snapshot 和 EP 顺序语义稳定后再做。

### 阶段 G：实现显式跨 fetch packet VLIW continuation

目标：

- 让跨 packet EP 从“硬件 opportunistic fusion”升级为“显式 VLIW 编码语义”；
- 保持 C66x 类似原则：EP 可以跨 fetch packet，但必须由 p-bit/metadata 明确连接；
- 继续禁止 branch target 跳入 EP 中间，直到有完整异常/restart 语义。

实现选项：

1. 在 hint header 中预留一个 `cross_next` bit，表示 packet 末尾 EP 可以与下一 packet 开头继续并行。
2. 把 p-bit 定义从“packet 内 slot 边”扩展为“全局 instruction stream 边”，由离线工具生成。
3. 增加跨包 EP 的 resource/dependency 校验；若下包未到或 loop buffer 缺失，不发射半个 EP。
4. redirect/flush 时清空 VLIWPU carry，并强制从 target EP 起点重新组包。

这一步完成后，HDV 的跨包行为才更接近真实 VLIW，而不是动态 fusion。

## 12. 结论

从当前 dump 和 RTL 来看，标量后端不应该停留在永久单发射，也不应该一开始做很宽的完整多发射 core。

更合理的实现选择是：

1. 保留当前 CVA6-style 后端作为 correctness 基线；
2. 明确当前跨包打包的语义：没有显式 continuation bit 时，它是 opportunistic dynamic fusion，不是严格 C66x-style VLIW；
3. 下一步优先做 **2-wide simple integer ALU + branch 并行**；
4. 保留 **1 条 scalar LSU**，先不做多 LSU；
5. 保留 **1 条 scalar FPU** 和 **1 个 MUL/DIV 单元**，初期多周期串行即可；
6. 后续再考虑 complex lane 解耦、scalar slice buffer、显式跨 packet continuation、以及更完整的 VLIW resource model。

这个选择和当前 kernel 统计匹配：`vsaxpy_hdv` 与大多数手写 RVV loop 的同 EP 标量需求主要是 2 到 3 条简单标量操作；完整 benchmark 又要求 LSU/FP/MUL/DIV 功能存在，但不支持把这些复杂单元都做成宽发射。

如果长期目标是向真实 VLIW 过渡，关键不是盲目加宽标量后端，而是把三个语义补完整：

1. EP 边界必须由 p-bit/metadata 明确表达，包括跨 fetch packet 的边界。
2. EP 内资源使用必须由 packer/VLIWPU 静态检查，后端按 lane 真并行。
3. branch/redirect/loop buffer 必须以 EP 为恢复和缓存粒度，而不是只按 fetch packet 做近似优化。
