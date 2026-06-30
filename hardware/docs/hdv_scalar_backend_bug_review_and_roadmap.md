# HDV 标量后端：Bug 核查 + 下一步效率/性能路线

针对 `hdv_scalar_backend.sv` 及其在 `hdv_top` / HEU / `hdv_vec_dispatch_unit` 中的集成，
做了一轮静态核查。结论分两部分：**(A) Bug / 正确性问题**（按严重度排序），**(B) 效率与性能路线**。

> 复核基准：`UseCva6HdvScalar=1`（默认，真实后端启用，未被 `ara_soc`/TB 覆盖）。
> 此时 IPU 的 redirect、HEU 的 scalar done/ready 全部取自真实标量后端，循环由真实 `bnez` 驱动。

---

## A. Bug / 正确性核查

### A0（验证缺口）当前集成需要新的编译/仿真结果闭环

- `sim/run.vcs.log` 时间戳 **2026-06-15 22:40**；而 `hdv_scalar_backend.sv`（06-16 11:51）、
  `hdv_top.sv`（12:51）、HEU（12:41）、`hdv_vec_dispatch_unit.sv`（12:57）都更新于其后。
- 也就是说，那份“PASSED, got 130 EPs”是**旧代码**（很可能 mock 驱动循环、或更早后端）的结果，
  **不能代表当前真实后端 + 最新集成的行为**。
- **行动**：当前环境先以 `make -C hardware compile` 和静态检查为准；功能正确性需要后续在有仿真许可时重跑，或用你提供的新 VCD/log 做后验分析。

### A1（已解决）任务 ABI/上下文初始化 —— kernel 参数注入机制已实现

- ~~标量后端 `xrf_q/frf_q` 复位为全 0，且没有任何外部装载端口 / `$readmemh` / initial（已核实：0 个 init 块）~~
- **已解决**：`hdv_scalar_backend.sv` 第 20-35 行定义了 `Initial*` 参数，第 1549-1566 行通过 `+HDV_A0..A7` plusarg 在 initial 块中将寄存器上下文写入寄存器堆。复位后寄存器初始值由仿真注入，`a0=AVL`、`a1=x 指针`、`a2=y 指针`、`fa0=alpha` 均可在启动前正确建立。
- vsaxpy 的入口参数在 HDV 模型里由 host core 在派发任务前写入寄存器；当前机制通过 plusarg 完成上下文初始化，mock host 不再需要额外写寄存器。
- **这是真实后端能跑”真程序”的第一前置条件，当前已满足。** 后续若需动态上下文切换，仍可扩展
  host/TIU 通过任务描述符把 `a0..a7 / fa0.. / sp` 等写入标量后端的端口机制。
- 参考：comparison 文档 §11.1#1 已把它列为最高优先，当前 RTL 已实现该机制。

### A2（已处理，仍需优化）vset→标量 / 向量操作数快照冒险

当前 `hdv_vec_dispatch_unit` 已经做了 acknowledged 延迟来保证正确性：

- vtrace 模式：普通 vector EP 入队即可 acknowledged；含 `vset rd!=x0` 的 EP 等对应 Ara response 写回后 acknowledged。
- 真实标量模式：普通 vector EP 等本 EP 的所有 vector slot 都被 dispatch FSM 消费后 acknowledged，保证 rs1/rs2/frs1 已经从真实 XRF/FRF 中读出并保存到 Ara request 或 resolved command window；含 `vset rd!=x0` 的 EP 还要等 granted VL 写回。

这同时解决两类问题：

- `sub a0,a0,t0` / `slli t1,t0,2` 不会在 `vsetvli` 的 `t0` 写回前读旧值。
- 后续 scalar EP 不会先更新 a1/a2/a0，导致尚未发出的旧 vector 指令从真实寄存器堆读到新地址/新标量值。

当前已加入参数化 resolved command window，顶层默认深度为 8，用来保存已经抓好 operand 的 vector request。后续性能优化方向不是盲目加深这个 window，而是让 operand snapshot 更早、更批量完成，并把真正有后端收益的 metadata 交给 Ara。

### A3（高）`unsupported` 判定过宽 + AMO/LR/SC 会被当普通 store 静默执行

- `p_execute_decode` 只用 CVA6 decoder 的异常位和 `fu` 大类判 `unsupported`，**不做 ISA 白名单**。
- CVA6 decoder 会把 AMO/LR/SC 归到 `fu==STORE`/`LOAD`；当前轻量 LSU `aw.atop='0`，
  会把它们当**普通 load/store** 发出去——语义错误且**不报错**（静默错误最危险）。
- 同理，decoder 把某些非目标扩展译成 ALU op 时，后端也会照跑。
- **修复建议**：在 `p_execute_decode` 增加显式判定——
  对 `op` 属于 AMO/LR/SC（或 `fu==STORE/LOAD` 且 decoder 标了 amo 标志）→ 置 `unsupported`；
  并对真正支持的 op 列白名单，其余一律 `unsupported`（→ `scalar_error_o`，不静默）。

### A4（中）测试 oracle 只数 EP 个数，掩盖“算错/循环次数错”

- mock host 在 `AutoExpectedEpAcknowledges=130` 命中即 FINISH=PASS；不校验数据，也不校验循环真的跑了 32 次。
- 真实后端即便把 `a0` 算错（A1/A2 导致），只要凑够 130 个 EP 握手就“PASS”。
- **建议**：增加自检模式——让真实 `bnez` 自然终止循环（去掉硬上限），
  仿真结束比对输出向量（y = alpha*x + y）与黄金值；或至少断言实际迭代数 == 期望。

### A5（低 / 已知）数值/CSR 副作用不完整

- `fflags` 恒 0、`fcsr` 只管 `frm`、`time/instret` 都别名到 `cycle`、misaligned 访存直接报错不拆分、
  `FENCE/ECALL/MRET/SFENCE` 无真实语义。comparison 文档 §6 已列，功能上对裸机紧 kernel 影响小，
  但跑通用程序/检查 flags 的测试会暴露。按目标取舍即可。

### A6（提示）多 slot 向量 EP 的操作数服务是 2 拍/条

- `vec_dispatch` 对每个向量 slot：先 `capture_operand`（1 拍读 XRF/FRF 寄存）再 `accept_insn`（1 拍发 Ara）。
  正确，但吞吐受限。属性能项，见 B 部分。

---

## B. 下一步：在满足功能前提下提升效率/性能

> 顺序原则：**先把 A0/A1/A2 的正确性闭环做完（否则性能优化无意义），再做吞吐。**

### 阶段 0：先闭环正确性（必须先做）
1. 当前环境先跑 compile 和静态检查；有仿真许可或新 VCD/log 后再闭环 A0。
2. 实现任务上下文初始化（A1）：最小可行——TIU/task descriptor 带一个初始寄存器块，
   复位后由 host 写入 `a0..a2 / fa0`。先让 vsaxpy 在真实后端上跑出**正确数据 + 正确 32 次循环**。
3. vset→标量冒险当前已用 vector dispatch acknowledged 延迟规避；后续若要提吞吐，再扩展 operand snapshot / resolved-request buffer，或增加标量端向量写回 scoreboard。
4. 改造 oracle 为数据自检（A4），把“真实后端跑对 vsaxpy”作为新基线。
5. 收紧 `unsupported` + AMO 报错（A3）。

### 阶段 1：标量后端吞吐（EP 内并行）
- **现状**：一个 EP 的多条标量 slot 串行执行（`p_find_slot` 取最低 index 逐条）。
- **机会**：VLIWPU 已保证同 EP 内**无依赖**，可安全并行。
- **做法**：复制 2 个 ALU lane + 1 个 branch/CSR + 1 个 LSU，按 slot 并行发射；
  多写端口直接写 `xrf_d`（同 EP 无 WAW 冲突，仲裁简单）。
- **收益**：地址递增/计数/比较密集的标量 slice 从 N 拍降到 ~1 拍。

### 阶段 2：标量 LSU
- **AW/W 同拍发射**（现在 `LSU_AW→LSU_W→LSU_B` 串行，至少省 1 拍/store）。
- **多 outstanding load**：对标量访存密集 kernel 有用；需引入返回乱序 + 简单 load 记分。
  优先级中，先做 AW/W 合并这种低风险项。

### 阶段 3：向量派发吞吐
- **操作数 snapshot FIFO**：真实标量模式下，先把一个 EP 的所有 vector 操作数快照保存下来，再向 HEU acknowledged。
  这样后续 scalar EP 可以提前更新寄存器，而旧 vector request 仍使用快照值。
- **跨 EP 持续灌 Ara**：当前 HEU 已用“入队”推进（已经有一定解耦 + 1-EP skid buffer）。
  在 A2 用记分位保证标量正确读后，可让不同 EP 的向量指令**持续**流入 Ara，
  用 `vec_dispatch` 的 issued/resp 计数维持在途，提升 Ara 利用率（这正是论文 H 架构的核心收益点）。

### 阶段 4（视目标）通用性
- 若目标扩到全 Ara benchmark / 编译器生成胶水：按 comparison §11 补 CSR 集、FCSR/FFLAGS、
  AMO/LR/SC、misaligned 拆分、trap 策略。这些是兼容性而非紧 kernel 性能。

---

## C. 建议的最小动作清单（可逐条交给我实现）

| 序号 | 动作 | 类型 | 风险 |
|---|---|---|---|
| C1 | 重跑仿真，确认当前真实后端行为 | 验证 | 低 |
| C2 | 加任务寄存器上下文初始化端口/机制 | 功能 | 中 |
| C3 | 扩展 operand snapshot / resolved-request buffer，或增加 vset→标量 scoreboard | 性能/扩展 | 中 |
| C4 | `unsupported` 白名单 + AMO 报错（A3） | 正确性 | 低 |
| C5 | oracle 改数据自检（A4） | 验证 | 低 |
| C6 | LSU AW/W 同拍（B 阶段2 低风险项） | 性能 | 低 |
| C7 | EP 内标量多发射（B 阶段1） | 性能 | 中 |

> 说明：当前代码能通过的是 **EP 握手计数测试**，不是 **数据正确性测试**。
> A0–A2 闭环之前，不建议先做性能优化——否则是在未验证的功能上提速。
