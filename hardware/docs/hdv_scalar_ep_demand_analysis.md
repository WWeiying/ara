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

## 5. 当前标量后端实现选择

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

## 6. 单发射是否太窄

结论：**对于功能验证，单发射足够；对于完整 Ara benchmark 的性能目标，单发射偏窄。**

原因如下：

1. `vsaxpy_hdv` 已经有 2 条标量操作落在同一个 EP 的情况。
2. 大多数 hand-written vector kernel 的局部窗口中，3 条业务指令内经常有 2 到 3 条标量指令。
3. 当前 p-bit 的语义本来就是表达并行关系；如果标量后端永远单发射，HDV 只能在 vector/scalar 跨后端并行上获益，无法利用 EP 内多条 scalar 的并行性。
4. 但当前 EP 容量只有 6 个 halfword slot，因此直接做 4/6 条完整标量通路收益有限，尤其在全 32-bit 指令场景下，一个 EP 最多只有 3 条业务指令。

所以更科学的判断是：

- 1-wide：实现简单，适合 bring-up，但会成为明显瓶颈；
- 2-wide integer ALU + branch：性价比最高，能覆盖 `vsaxpy_hdv`、copy/swap/dot/dwt/gemm loop 中最常见的组合；
- 3-wide full scalar：只有在大量 compressed scalar 或更宽 EP 设计下才更有必要；
- 4-wide 或更宽：当前 EP 容量下容易面积/时序投入大于收益。

## 7. 推荐的后端结构

建议把标量后端分成“可并行的简单通路”和“保守串行的复杂通路”。

### 7.1 第一优先级：2 ALU + branch

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

### 7.2 第二优先级：1 scalar LSU

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

### 7.3 第三优先级：保留 scalar FP，但不急于多发

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

### 7.4 MUL/DIV：单个多周期单元即可

推荐配置：

| 资源 | 建议 |
|---|---|
| Integer MUL/DIV | 1 个多周期单元 |
| 发射 | 与复杂通路串行 |

理由：

- hand-written RVV kernel 中 MUL/DIV 同 EP 热点不明显；
- compiler-generated benchmark 中会出现 MUL/DIV，但通常不是同 EP 高并发；
- 多个 MUL/DIV lane 面积大，收益不如 2 ALU + LSU。

## 8. 对当前实现的辩证评价

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
- 最合理的路线是先把同 EP 最常见的简单标量并行利用起来，再逐步处理复杂通路的非阻塞化。

## 9. 建议演进路线

### 阶段 A：保持当前单发射，作为功能基线

目标：

- 确认完整 RV64IMC + F/D + Zicsr 用户态标量语义覆盖；
- 确认 branch redirect、vset 写回、vector operand snapshot 正确；
- 用真实 benchmark 找出 unsupported 指令。

这个阶段不追求性能，只保证 correctness。

### 阶段 B：增加 2-wide simple scalar issue

目标：

- 同一 scalar slice 中选择最多 2 条 simple ALU 指令并行执行；
- 支持 `ALU + branch` 同周期执行；
- 对同 EP 内写同一寄存器、读写冲突做静态/动态保护。

关键前提：

- VLIWPU/p-bit 已经保证同 EP 内无数据依赖；
- 后端仍要防御非法情况，例如两个 lane 同时写同一 rd；
- branch redirect 要保持唯一，含多个 control-flow 的 EP 应该禁止或只允许第一个。

### 阶段 C：simple lane 与复杂 lane 解耦

目标：

- ALU/branch 可以和 LSU/FPU/MUL 的请求发起重叠；
- scalar slice accepted 仍等待所有 lane 完成；
- 复杂 lane 用 busy bit 或 per-slot done bit 管理。

这样可以改善 `vsgemv/vsspmv/vssymv/fmatmul/fconv` 等 kernel 中 scalar LSU/FP 拖住简单地址更新的问题。

### 阶段 D：增加 scalar slice skid buffer

目标：

- 标量后端忙时 HEU 可提前交付下一组 scalar slice；
- 后端内部按 EP 顺序提交 accepted；
- 不破坏 vector operand snapshot 和 branch redirect 顺序。

这一步对持续供指有帮助，但复杂度高于简单 2 ALU；应在 operand snapshot 和 EP 顺序语义稳定后再做。

## 10. 结论

从当前 dump 和 RTL 来看，标量后端不应该停留在永久单发射，也不应该一开始做很宽的完整多发射 core。

更合理的实现选择是：

1. 保留当前 CVA6-style 后端作为 correctness 基线；
2. 下一步优先做 **2-wide simple integer ALU + branch 并行**；
3. 保留 **1 条 scalar LSU**，先不做多 LSU；
4. 保留 **1 条 scalar FPU** 和 **1 个 MUL/DIV 单元**，初期多周期串行即可；
5. 后续再考虑 complex lane 解耦和 scalar slice buffer。

这个选择和当前 kernel 统计匹配：`vsaxpy_hdv` 与大多数手写 RVV loop 的同 EP 标量需求主要是 2 到 3 条简单标量操作；完整 benchmark 又要求 LSU/FP/MUL/DIV 功能存在，但不支持把这些复杂单元都做成宽发射。
