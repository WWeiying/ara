# HDV 相关性处理、EP 契约与 Kernel 编写指南

## 0. 文档目的与结论先行

本文专门回答以下问题：

1. 一段 HDV task 从软件提交到标量后端、向量后端执行，依次经过哪些模块？
2. 每个模块负责处理哪一类相关性、顺序和完成条件？
3. 软件负责保证什么，硬件负责保证什么？
4. EP、logical packet、scalar slice、vector slice、Ara vector instruction 分别是什么？
5. `pbits`、`packet256`、`cross`、loop marker 和 prefetch 字段分别控制什么？
6. 普通 RVV kernel 应该怎样改写成 HDV kernel？
7. 哪些指令可以放在同一 EP，哪些必须切开？
8. 为什么当前 RTL 已移除 same-EP hazard suppression？

本文以当前 RTL 和当前 `apps/*_hdv` kernel 为准。依赖与 `pbits` 主题若与旧文档冲突，以本文的分析为准。

### 0.1 最重要的结论

当前实现中，EP 更准确的含义是：

> 一组由 VLIWPU 一次交给 HEU、随后被拆成 scalar slice 和 vector slice 的指令。

它不是天然满足以下任意一种含义：

- EP 内所有指令在同一个周期执行。
- EP 内所有指令同时完成。
- EP 内所有指令没有数据相关。
- EP 内所有访存可以任意重排。
- EP 被 HEU acknowledge 时，Ara 中的向量指令已经执行完成。

当前 RTL 的真实行为是：

- VLIWPU 主要按照软件 `pbits`、包边界、最大 issue width 和控制指令切 EP。
- VLIWPU 不解析完整寄存器读写集合，也不动态验证 EP 内依赖。
- HEU 按指令类别把同一 EP 拆成 scalar slice 和 vector slice。
- 标量 slice 内的部分标量依赖由 `hdv_scalar_backend` 动态保序。
- 向量 slice 被 VDU 逐条发送给 Ara。
- 向量寄存器依赖始终由 Ara 原有 read/write list 和 hazard table 保序，不因 EP 归属而豁免。
- 标量和向量后端之间只实现了有限的显式协同，软件仍必须避开未覆盖的跨后端依赖。

因此，当前最稳妥的编程模型是：

> `pbit=1` 表示“允许这些指令进入同一个前端分组”，不等于“软件证明这些指令完全独立”。向量寄存器依赖必须保留 Ara 常规 hazard 检查；跨标量/向量后端的依赖必须按照本文规则显式切 EP。

### 0.2 same-EP suppression 已移除

当前 `hardware/src/ara_sequencer.sv` 不再根据 `ep_id` 屏蔽 RAW、WAR 或 WAW hazard。每条向量请求都经过 Ara 常规 read/write-list 检查，同一 EP 与跨 EP 请求遵循相同的向量寄存器相关规则。

原实验逻辑被移除有两个原因：

1. 当前多个 HDV kernel 在同一 EP 中包含真实向量 RAW/WAW 依赖。
2. HEU 的 `ep_id` 只有 1 bit。它足以区分 HEU/VDU 当前和缓冲的两个 vector slice，但不能保证 Ara 中仍在执行的旧 `vid` 生命周期内不重用。

例如，当前 AXPY 中以下两条指令位于同一 EP：

```asm
vle32.v   v3, (a2)
vfmacc.vf v3, fa0, v0
```

第二条读取并写回第一条产生的 `v3`，存在真实 RAW 和 WAW。若因为 `ep_id` 相同而屏蔽相关位，后端可能在 `v3` 尚未就绪时推进第二条指令。

因此：

- 当前 kernel 的现有依赖结构由 Ara 常规向量 hazard 处理保护。
- `ep_id` 仍用于 VDU 的响应归属和 `vset` 完成匹配，但不再参与 sequencer 的相关性豁免。
- `task PASSED` 只说明 task 协议完成，不能替代逐元素数值比对。

---

## 1. 基本概念

### 1.1 Task

Task 是 host 提交给 HDV 的一段独立程序。软件通过 task CSR 提供：

- task 入口地址；
- task descriptor/物理地址信息；
- start；
- status 查询。

当前公共定义位于：

```text
hardware/src/hdv/hdv_pkg.sv
```

CSR 地址为：

| CSR | 地址 | 作用 |
|---|---:|---|
| `HDV_CSR_VTASK_ADDR` | `0x7c0` | task 入口地址 |
| `HDV_CSR_VTASK_PADDR` | `0x7c1` | task descriptor/物理地址 |
| `HDV_CSR_VTASK_START` | `0x7c2` | 启动 task |
| `HDV_CSR_VTASK_STATUS` | `0x7c3` | busy/done/error |

软件侧通常把 task 函数放入 `.hdv_task` section，并使用裸函数和内联汇编精确控制布局：

```c
__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void my_hdv_task(...) {
  __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ...
    ".option pop\n"
  );
}
```

### 1.2 Fetch beat

IPU 与 VLIWPU 之间的基本取指宽度是 128 bit，也就是 16 bytes。本文称它为 fetch beat。

一个 fetch beat 不是一个 EP。它只是指令供给的物理传输单位。

### 1.3 Logical packet

Logical packet 是一个 HINT header 管理的指令布局单位。

- 128-bit logical packet：1 个 128-bit fetch beat。
- 256-bit logical packet：连续 2 个 128-bit fetch beat。

每个 logical packet 的第一个 32-bit word 是：

```asm
lui x0, imm20
```

因为写入 `x0` 没有普通架构副作用，所以 RTL 把它解释为 HDV HINT header。

logical packet 也不是 EP。一个 logical packet 可以被切成多个 EP。

### 1.4 Slot

VLIWPU 以 16-bit slot 观察 logical packet。

- RVC 指令占 1 个 slot。
- 普通 32-bit 指令占连续 2 个 slot。
- 当前 HDV kernel 基本使用 `.option norvc`，因此业务指令通常都是 32 bit。

`NumSlots=8`、`SlotWidth=16` 时，一个 EP 最多携带 8 个 16-bit slot，即最多 4 条 32-bit 指令。

### 1.5 EP

EP 是 VLIWPU 一次发给 HEU 的 execute packet。

EP 具有以下性质：

- 包含最多 `MaxIssueSlots` 个 16-bit slot；
- 保留每条指令的 slot 顺序和 PC；
- 可同时包含标量和向量指令；
- 遇到 branch/system 指令时被硬件强制截断；
- 可由 `pbits` 主动截断；
- 可因 issue width 被截断；
- 理论上可由外部 `dep_break` 截断。

当前 `ara_tb.sv` 把 `hdv_dep_break` 接为全零。因此在当前常用仿真环境中，没有动态依赖检测帮助软件切 EP。

另外，`ctrl_vliwpu_dep_break_i` 的当前宽度是 `NumSlots-1`，与单个 8-slot EP 窗口对应，而不是与 256-bit logical packet 的全部 14 个 payload slot 对应。即使未来接入非零 `dep_break`，也必须重新核对它在 256-bit packet 后半段的边界覆盖，不能把它直接视为完整的 logical-packet dependency bitmap。

### 1.6 Scalar slice 和 vector slice

HEU 收到一个 EP 后，按指令类别生成两个保持原 slot 顺序的子集：

- scalar slice：标量、分支、system 类指令；
- vector slice：RVV 算术、配置和向量访存指令。

这两个 slice 可以向两个后端独立握手和推进。

因此，同一 EP 内的“同时性”只表示两个 slice 可以并行交给不同后端，不表示所有指令同周期执行。

### 1.7 Ara vector instruction 和 `vid`

VDU 把一个 vector slice 序列化成逐条 Ara 请求。Ara sequencer 为每条被接受的向量指令分配一个 `vid`。

Ara 使用 `vid` 跟踪：

- 指令是否仍在执行；
- 各向量寄存器最近的读者和写者；
- 新请求相对于在飞指令的 RAW/WAR/WAW hazard；
- lane operand requester 是否可以继续推进。

一个 EP 可以产生多条 Ara vector instruction，也就会对应多个 `vid`。

---

## 2. 端到端执行路径

当前主路径可以概括为：

```text
Host
  |
  v
TIU -> TSU -> IPU -> VLIWPU -> HEU
                                  | \
                                  |  \-> VDU -> Ara sequencer -> lanes/VLSU
                                  |
                                  \----> HDV scalar backend
```

### 2.1 TIU：Task Interface Unit

文件：

```text
hardware/src/hdv/hdv_task_interface_unit.sv
```

TIU 负责：

- 实现 task CSR 接口；
- 保存 task entry 和 task descriptor；
- 接收 start；
- 向 TSU 发送 task；
- 汇总 busy/done/error 状态。

TIU 不负责：

- 指令取指；
- EP 形成；
- 寄存器相关检测；
- 访存顺序；
- task 内控制流。

### 2.2 TSU：Task Schedule Unit

文件：

```text
hardware/src/hdv/hdv_task_schedule_unit.sv
```

TSU 内部有 task FIFO，负责：

- 按 host 提交顺序排队；
- 一次只激活一个 task；
- 将 task entry/descriptor 发给 IPU；
- 保存 task 级 done/error。

TSU 的顺序是 task 级顺序，与 EP 内指令相关无关。

### 2.3 IPU：Instruction Prefetch Unit

文件：

```text
hardware/src/hdv/hdv_instruction_prefetch_unit.sv
```

IPU 使用两个 64-byte ping-pong buffer，并以 128-bit packet 向 VLIWPU 供给指令。

主要职责：

- 从 task entry 开始取指；
- 第一包返回后即可 early serve；
- 后台填充当前/另一个 buffer；
- 处理标量后端产生的 redirect；
- 识别循环区域并缓存 backward loop；
- 保护 loop buffer，减少重复指令存储访问。

IPU 处理的是指令供给和控制流重定向，不判断数据依赖。

### 2.4 VLIWPU：Logical packet 解析和 EP 形成

文件：

```text
hardware/src/hdv/hdv_vliw_pack_unit.sv
```

VLIWPU 负责：

1. 识别 `lui x0, imm20` HINT。
2. 拼接 128-bit 或 256-bit logical packet。
3. 标记 16-bit/32-bit 指令边界。
4. 粗粒度分类 scalar/vector/system/branch。
5. 根据 `pbits`、issue width、控制边界和 `dep_break` 形成 EP。
6. 可将 packet 尾部 EP 跨到下一 logical packet。
7. 将 prefetch metadata 与形成的 EP 对齐。

当前分类规则的关键点：

- opcode `0x57` 识别为向量算术/配置；
- 向量 load/store 编码识别为 vector；
- FENCE、FENCE.I、SYSTEM 识别为 system；
- branch、JAL、JALR 识别为 branch；
- 其他指令进入 scalar 类。

VLIWPU 的停止条件可以简化为：

```text
到达 logical packet 末尾
或达到 MaxIssueSlots
或当前完整指令后的 pbit=0
或对应 dep_break=1
或当前指令是 branch/system
```

VLIWPU 不负责：

- 解码完整 RVV 寄存器组占用；
- 判断向量 RAW/WAR/WAW；
- 判断 scalar slice 与 vector slice 之间的完整依赖；
- 判断两个访存是否别名；
- 保证 `pbit=1` 的指令一定并行。

### 2.5 HEU：混合分流和有限的跨后端协同

文件：

```text
hardware/src/hdv/hdv_hybrid_execution_unit.sv
```

HEU 是理解 HDV 依赖行为的核心。

#### 2.5.1 EP 分流

HEU 重组完整 32-bit 指令，然后：

- vector 类进入 vector slice；
- 其他类进入 scalar slice；
- 两边保留原 slot 位置；
- 记录 EP PC、prefetch metadata 和 `ep_id`。

#### 2.5.2 当前 EP 与一个 buffered EP

HEU 维护：

- 一个 current EP；
- 一个 buffered EP。

该缓冲允许 VLIWPU 在 current EP 尚未完全交付后端时提前交付下一 EP，吸收前后端速率差。

#### 2.5.3 HEU 的“完成”不是向量执行完成

HEU 对一个 EP 的正常推进条件是：

```text
scalar slice 已由标量后端执行完成
并且
vector slice 已被 VDU acknowledge
```

VDU acknowledge 表示：

- 该 EP 的所有向量指令所需标量操作数已经捕获；
- 该 EP 中产生 scalar-visible result 的向量指令已完成对应写回。

它不表示普通向量算术、向量 load/store 已在 Ara 中完成。

这个区别解释了为什么：

- 后续 EP 可以在前一 EP 的普通向量指令仍在 Ara 中时推进；
- 向量寄存器正确性仍需要 Ara scoreboard；
- 仅靠 EP 边界不能表示“等待所有向量访存完成”。

#### 2.5.4 HEU 跟踪的依赖范围

HEU 为 scalar slice 和 vector slice生成以下标量可见 mask：

- scalar GPR read/write；
- scalar FPR read/write；
- vector 指令读取的 GPR/FPR；
- vector 指令写回的 GPR/FPR。

vector 指令的标量读取包括：

- vector load/store 的基址 `rs1`；
- strided vector memory 的标量 stride `rs2`；
- `.vx` 的整数标量源；
- `.vf` 的浮点标量源；
- `vsetvli/vsetvl` 的 AVL/vtype 标量源。

vector 指令的标量写回包括：

- `vset*`；
- `vmv.x.s`；
- `vcpop.m`；
- `vfirst.m`；
- `vfmv.f.s`。

这些 mask 只描述标量架构状态。HEU 不解析 vector register RAW/WAR/WAW。

#### 2.5.5 Buffered vector early issue

当 current EP 的 scalar side 尚未结束时，HEU 可以尝试提前发射 buffered EP 的 vector slice。

允许 early issue 前会检查：

- current EP 是否有未解析 branch；
- current EP 是否含 scalar memory/order operation；
- buffered vector 对 current scalar/vector scalar-visible 状态是否有 GPR RAW/WAR/WAW；
- 是否有 FPR RAW/WAR/WAW；
- VDU 是否可接收。

因此这是一种有条件的跨 EP overlap，不是无约束乱序。

它没有检查：

- vector register 之间的 RAW/WAR/WAW；
- 任意地址别名；
- Ara 中旧 `vid` 是否已完成。

这些仍由 Ara 或软件负责。

### 2.6 HDV scalar backend：标量 slice 的执行和局部保序

文件：

```text
hardware/src/scala_backend/hdv_scalar_backend.sv
```

标量后端维护独立的：

- XRF；
- FRF；
- CSR/`vl` 可见状态；
- 标量 LSU；
- 分支和 redirect 状态。

#### 2.6.1 Scalar-scalar 依赖

对 simple scalar 指令，`p_simple_batch` 从低 slot 向高 slot 扫描。

它维护 `prior_write_mask`，并在以下情况下停止同批发射：

```text
当前指令读取了更早 slot 写入的寄存器
或
当前指令与更早 slot 写同一个 rd
```

也就是阻止同批的 scalar RAW 和 WAW。

这不等于整条 EP 失败。后面的标量指令会在前面的写回可见后继续执行。因此，标量 backend 能把一个含有标量依赖的 scalar slice 分多拍完成。

例如：

```asm
slli t1, t0, 2
add  a1, a1, t1
```

即使两条指令位于同一 EP，第二条也不会错误地读取旧 `t1`。代价是它们不能作为真正独立指令在同批推进。

#### 2.6.2 Complex scalar 指令

复杂指令按更保守的顺序执行。`complex_simple_raw_stall` 防止 complex 指令读取尚未由 simple batch 写回的标量寄存器。

#### 2.6.3 VDU 标量操作数服务

标量后端通过组合读口向 VDU提供：

- `rs1`；
- `rs2`；
- `frs1`。

该接口当前始终 ready，返回当前 `xrf_q/frf_q` 中的值。

这不是一个通用的跨后端 forwarding network。它不能自动把同一 EP 中刚由标量指令计算、尚未写回的新值转发给向量指令。

#### 2.6.4 `vset` 特殊 interlock

`vset*` 是向量指令，但会向标量 GPR 写回实际 `vl`。

VDU 从 `vset` EP 被呈现开始，一直到对应写回到达，向标量后端提供：

```text
vec_vset_inflight_i
vec_vset_inflight_rd_i
```

标量后端发现当前 scalar 指令读取这个 `rd` 时会 stall。

这是当前跨向量到标量 RAW 中最明确的一条专用保护。

它不应被误解为对所有 vector-to-scalar result 都有通用 scoreboard。

#### 2.6.5 标量访存

标量后端拥有标量 LSU。当前显式的跨后端保护之一是：

- VDU 发现 vector store 已进入 command window 或已经发送给 Ara 时，拉高 `vec_store_inflight_o`；
- 标量后端在该信号有效时阻止标量 memory operation。

这提供保守的 vector-store 到后续 scalar-memory 顺序。

### 2.7 VDU：向量 slice 序列化、标量操作数快照和命令窗口

文件：

```text
hardware/src/hdv/hdv_vec_dispatch_unit.sv
```

VDU 的主要职责是：

1. 接收 HEU 的多 slot vector slice。
2. 按 slot 顺序选择向量指令。
3. 判断每条指令是否需要 GPR/FPR 标量操作数。
4. 从标量后端读取并快照标量操作数。
5. 把指令、操作数和 HDV metadata 放入 command window。
6. 逐条与 Ara `valid/ready` 握手。
7. 保存 response metadata，将 scalar-visible response 写回标量后端。
8. 在满足 EP acknowledge 条件时通知 HEU。

#### 2.7.1 四个不同的“进度点”

理解 VDU 时必须区分：

| 层级 | 事件 | 含义 |
|---|---|---|
| Level 1 | Ara request handshake | Ara 接收了一条向量指令 |
| Level 2 | operand captured | 该指令的标量操作数已被快照 |
| Level 3 | EP acknowledged | 本 EP 全部向量指令完成标量操作数捕获，且 scalar-visible writeback 已完成 |
| Level 4 | Ara response | 一条向量指令实际执行完成并返回 |

Level 3 不是 Level 4。

#### 2.7.2 标量操作数快照

向量指令进入 command window 后，所需基址、stride、`.vx` 或 `.vf` 标量值已经固定。后续标量 EP 修改同一 GPR/FPR，不会改变已排队的向量请求。

这使标量地址更新可以与 Ara 中旧向量请求重叠。

#### 2.7.3 同 EP 的 read-old pattern

当前 VDU 特意不在一个新 EP 第一次呈现的同周期直接 bypass 操作数，而是经过一个寄存阶段再快照。这保留了当前 kernel 中常见的 read-old 模式：

```asm
vse32.v v3, (a2)
add     a2, a2, t1
```

两条指令在同一 EP 中时，store 使用旧 `a2`，标量 add 生成下一迭代使用的新 `a2`。

这属于有意的 WAR/read-before-write 模式，不是通用 forwarding。只有在明确需要“向量读旧值、标量写新值”时才应采用。

### 2.8 Ara sequencer：向量寄存器动态相关处理

文件：

```text
hardware/src/ara_sequencer.sv
```

Ara sequencer 为每个向量寄存器维护访问记录：

- `read_list`：最近读该寄存器的在飞 `vid`；
- `write_list`：最近写该寄存器的在飞 `vid`。

新向量请求到达后，根据 `vs1`、`vs2`、`vm`、`vd` 形成：

- RAW hazard；
- WAR hazard；
- WAW hazard。

hazard vectors 随请求进入后续 PE/lane 路径。operand requester 在旧 `vid` 的相应操作数或结果就绪前阻止新指令错误推进。

这套机制是当前有依赖 vector instruction 正确执行的基础。

### 2.9 Ara lanes 和 VLSU

Ara lanes 负责向量算术、操作数读取、结果写回和 lane 同步。

VLSU 负责：

- 向量 load/store 地址生成；
- 请求拆分和内存事务；
- demand/prefetch 仲裁；
- prefetch lookup/buffer；
- load data 返回；
- 向量访存完成。

向量访存之间的正常执行顺序和向量寄存器目标相关由 Ara 原路径处理。HDV HINT 提供的 prefetch metadata 只能提前数据访问，不能成为正确性条件。

### 2.10 `hdv_top`：连接、flush、内存仲裁和 task drain

文件：

```text
hardware/src/hdv/hdv_top.sv
```

`hdv_top` 不实现新的寄存器 dependency checker，但负责把前述机制连接成完整系统：

- 实例化 TIU、TSU、IPU、VLIWPU、HEU、scalar backend、VDU 和 Ara；
- 将 scalar branch resolved event 转换成 IPU redirect；
- 对 task error、task completion 和 redirect 生成相应 flush；
- 将 IPU instruction memory、scalar LSU 和 Ara memory path 接入共享 AXI 仲裁；
- 将 VDU 的 prefetch metadata 送入 Ara/VLSU；
- 汇总 task busy/done/error；
- 在 scalar backend 遇到 `ret` 请求 task completion 后，等待 `vec_dispatch_busy` 清零再向 TSU 报告 task done。

最后一项非常重要。scalar `ret` 只说明标量程序到达 task 末尾；如果 VDU 仍保存 command 或 response metadata，`hdv_top` 会记录 completion request 并等待向量 dispatch 路径排空。

这仍不改变前述 EP acknowledge 语义：

- 单个 EP 可以在普通向量指令完成前 acknowledge；
- 整个 task 的 done 路径会额外等待 VDU/Ara response 管理状态排空。

### 2.11 `hdv_mock_host_core`：独立 bring-up 模型

文件：

```text
hardware/src/hdv/hdv_mock_host_core.sv
```

该模块用于 standalone prototype/bring-up，模拟：

- host 写 task CSR；
- 固定延迟的 scalar/vector handshake；
- EP acknowledge 计数；
- watchdog；
- task completion/error。

它不是当前真实 scalar backend 和 Ara dependency 行为的替代品。使用 mock latency 跑通只能验证接口状态机，不能证明真实 scalar/vector dependency、memory ordering 或数值结果正确。

---

## 3. 软件与硬件责任边界

### 3.1 总表

| 问题 | 主要负责方 | 当前保证 |
|---|---|---|
| task 提交和状态 | TIU/TSU | task FIFO 和单 task 激活 |
| 指令连续供给 | IPU | ping-pong buffer、redirect、loop replay |
| logical packet 解码 | VLIWPU | HINT、128/256、slot 和粗分类 |
| EP 边界 | 软件 `pbits` + VLIWPU | pbit/控制/宽度/外部 dep break |
| scalar/vector 分流 | HEU | 保留 slot 顺序，形成两个 slice |
| scalar-scalar RAW/WAW | scalar backend | simple batch/complex 路径动态保序 |
| vector-vector RAW/WAR/WAW | Ara sequencer | 所有请求均使用常规 read/write-list 和 hazard vector |
| scalar-to-vector operand | VDU + scalar read port | 捕获当前 XRF/FRF 值，无通用同 EP forwarding |
| `vset` 到 scalar consumer | VDU + scalar backend | 专用 inflight interlock |
| 其他 vector-to-scalar result | VDU writeback | 写回支持，但同 EP scalar consumer 没有通用 interlock |
| buffered vector early issue | HEU | 检查 branch、scalar memory、GPR/FPR 依赖和资源 |
| vector-store 到 scalar-memory | VDU + scalar backend | `vec_store_inflight` 保守阻塞 |
| scalar-memory 到 later buffered vector | HEU | scalar memory 阻止 early issue |
| vector register group/LMUL hazard | Ara | 软件不能只看一个寄存器号 |
| prefetch | VDU/VLSU + software hint | 可选性能优化，不改变架构结果 |
| 数值正确性 | 软件测试 | 必须与 golden result 比较 |

### 3.2 软件必须保证的事项

软件至少必须保证：

1. HINT header 与业务指令布局一致。
2. 32-bit/16-bit 指令宽度与 p-bit 计算一致。
3. branch、JAL、JALR 的目标落在合法 packet/header 布局上。
4. 同一 EP 中不存在未被当前硬件覆盖的 scalar-to-vector RAW。
5. 同一 EP 中不存在未被当前硬件覆盖的 generic vector-to-scalar RAW。
6. 需要严格先后顺序的 scalar/vector memory operation 不依赖“同一 EP 自然有序”。
7. 使用 read-old pattern 时，必须明确向量读取旧标量值、标量产生下一次使用的新值。
8. prefetch 关闭或 miss 时，程序仍必须正确。
9. task 退出前，所有架构可见结果满足程序要求。
10. 对输出数据做数值验证，而不仅检查 task completion。

### 3.3 硬件不能替软件保证的事项

当前硬件不会自动：

- 从 p-bit 推导寄存器独立性；
- 在 VLIWPU 中构建完整 dependence graph；
- 检查 RVV LMUL register group overlap；
- 检查两个地址是否 alias；
- 把同 EP scalar producer 的结果旁路给 vector consumer；
- 对所有 vector-to-scalar result 建立通用 scoreboard；
- 让 EP acknowledge 等价于 Ara 全部执行完成；
- 保证 1-bit `ep_id` 在 Ara 全生命周期内唯一。

---

## 4. 相关性分类与当前处理方式

### 4.1 RAW、WAR、WAW

若较早指令为 `I0`，较晚指令为 `I1`：

- RAW：`I0` 写，`I1` 读。`I1` 必须看到 `I0` 的新值。
- WAR：`I0` 读，`I1` 写。`I0` 必须先读取旧值。
- WAW：`I0` 写，`I1` 写。最终必须保留 `I1` 的结果。

不能因为两条指令进入同一 EP，就认为这些关系消失。

### 4.2 Scalar-scalar

| 类型 | 当前处理 | 编程建议 |
|---|---|---|
| RAW | scalar backend 检测并分拍 | 可以同 EP，但没有真正并行收益时可主动切开 |
| WAW | scalar backend 阻止同批写同一 rd | 可以同 EP，但建议减少无意义打包 |
| WAR | 通常允许前面的读使用旧值 | 仅在明确 read-old 语义时使用 |
| branch 依赖 | scalar backend 按 slot 顺序推进 | branch 由 VLIWPU 强制形成边界 |

### 4.3 Vector-vector

| 类型 | 当前处理 |
|---|---|
| RAW | Ara `write_list` 和 source hazard vector 保序 |
| WAR | Ara `read_list` 和 source hazard vector 保序 |
| WAW | Ara `write_list` 和 destination hazard vector 保序 |

同一 EP 内可以存在真实 vector dependency。VDU 将 vector slice 序列化为逐条请求后，Ara 对这些请求执行与普通 RVV 请求相同的动态相关检查。

### 4.4 Scalar-to-vector

#### 情形 A：vector 需要 scalar 指令刚产生的新值

```asm
addi    a1, a0, 16
vle32.v v0, (a1)
```

如果放在同一 EP，HEU 会把 `addi` 发给 scalar backend，把 `vle32.v` 发给 VDU。VDU 没有通用旁路保证捕获 `addi` 的新结果。

正确做法：切 EP。

```asm
HDV_HINT 0x00
addi    a1, a0, 16
vle32.v v0, (a1)
nop
```

对 128-bit、三条 32-bit 指令的 packet，`pbits=0x00` 会在每条完整指令后切开。

#### 情形 B：vector 需要旧值，scalar 产生下一迭代的新值

```asm
vse32.v v3, (a2)
add     a2, a2, t1
```

这是当前 AXPY 使用的 read-old pattern。VDU 对 store base 做快照，标量 add 更新下一轮指针。

该模式可以使用，但必须同时满足：

- vector 指令读取的是 EP 进入时的旧值；
- scalar 指令写的新值只供后续 EP 使用；
- 不依赖 vector 指令先完成；
- 仿真探针验证 operand capture 值符合预期。

### 4.5 Vector-to-scalar

#### `vset*`

```asm
vsetvli t0, a0, e32, m1, ta, ma
sub     a0, a0, t0
```

`sub` 需要 `vsetvli` 返回的实际 `vl`。当前 VDU/scalar backend 有 `vset` 专用 interlock，但为了使软件意图清晰并降低时序耦合，当前 kernel 通常仍把 dependent scalar 放到下一 EP。

#### 其他 scalar-visible vector result

例如：

```asm
vfmv.f.s ft1, v0
fsw      ft1, 0(a0)
```

VDU 支持把 `vfmv.f.s` 结果写回 FRF，但标量 backend 没有对所有此类结果建立与 `vset` 同等的通用 same-EP interlock。

正确做法：切 EP，让 vector scalar-visible writeback 完成后再执行 consumer。

### 4.6 Memory dependency

需要分别考虑：

1. vector memory 与 vector memory；
2. scalar memory 与 scalar memory；
3. scalar memory 与 vector memory。

#### Vector-vector memory

由 Ara/VLSU 常规路径管理。相关的目标向量寄存器仍通过 Ara hazard table 保序。

#### Scalar-scalar memory

由 scalar backend LSU 和标量程序顺序管理。

#### Scalar-vector memory

当前有两个主要防护：

- current EP 含 scalar memory 时，HEU 不允许 buffered vector early issue 越过它；
- vector store 在 flight 时，标量 backend 阻止 scalar memory。

但这不是完整的跨域 memory dependence engine。例如，普通 vector load 的 EP acknowledge 不表示 load 已经完成。因此，仅切 EP 不一定等价于等待 prior vector load 完成。

编程原则：

- 不要在 task 中构造需要精确 alias 顺序、但未被上述机制覆盖的 scalar/vector memory 依赖。
- scalar producer 写内存、later vector consumer 读同地址时，要确保 scalar store 完成后 vector 才能发射。
- vector store、later scalar consumer 读同地址时，依赖 `vec_store_inflight` 保护并做数值验证。
- vector load 后马上由 scalar 访问同一数据时，不能把 EP acknowledge 当成 load completion。
- FENCE/SYSTEM 应作为硬边界，但仍需确认它是否等待了所需的向量完成条件。

### 4.7 Control dependency

VLIWPU 遇到以下指令会强制停止当前 EP：

- conditional branch；
- JAL；
- JALR；
- FENCE/FENCE.I；
- SYSTEM。

HEU 不允许 buffered vector early issue 越过 current unresolved branch。

branch 被标量 backend 解析后产生 redirect，redirect 会 flush IPU/VLIWPU/HEU/VDU 中不应继续执行的前端状态。

软件仍需保证：

- branch target 指向正确的 HINT/header 边界；
- taken branch 后不依赖同 packet 尾部指令执行；
- `ret` 不与 taken loop branch 形成错误的同一控制组。

当前 DWT 已采用：

```asm
HDV_HINT 0x1f, 0, 0, 0, 1
bnez t0, dwt_loop
nop
nop

HDV_HINT
ret
nop
nop
```

这样 `ret` 只在 loop fall-through 后执行。

---

## 5. HINT header 和 p-bit 规则

### 5.1 HINT 格式

当前所有 HDV kernel 使用的宏等价于：

```asm
.macro HDV_HINT pbits=0x1f, packet256=0, cross=0, \
                loop_start=0, loop_end=0, \
                prefetch_mode=0, prefetch_disable=0
  lui x0, (((\pbits) & 0x1fff) |
           (((\packet256) & 1) << 13) |
           (((\cross) & 1) << 14) |
           (((\loop_start) & 1) << 15) |
           (((\loop_end) & 1) << 16) |
           (((\prefetch_mode) & 3) << 17) |
           (((\prefetch_disable) & 1) << 19))
.endm
```

字段定义：

| `imm20` 位 | 字段 | 含义 |
|---|---|---|
| `[12:0]` | `pbits` | 16-bit slot 边界后的 EP continuation |
| `[13]` | `packet256` | logical packet 使用两个 128-bit beat |
| `[14]` | `cross` | packet 尾部 EP 可继续拼接下一 logical packet |
| `[15]` | `loop_start` | loop-start marker |
| `[16]` | `loop_end` | loop-end marker |
| `[18:17]` | `prefetch_mode` | `00/01/10/11 = 1X/2X/4X/8X` |
| `[19]` | `prefetch_disable` | 显式关闭 prefetch |

### 5.2 p-bit 的准确含义

假设一条完整指令结束在 slot boundary `b`：

- `pbits[b]=1`：允许继续扫描下一条指令并尝试放入同一 EP；
- `pbits[b]=0`：在当前完整指令后结束 EP。

“允许继续”不等于“保证继续”，因为硬件还可能因以下原因停止：

- issue width；
- packet end；
- branch/system；
- `dep_break`；
- 32-bit 指令完整性。

### 5.3 128-bit packet 的 p-bit

128-bit packet 中：

```text
32-bit header + 96-bit payload
```

若使用 `.option norvc`，payload 是三条 32-bit 指令：

```text
inst0: slot 0,1
inst1: slot 2,3
inst2: slot 4,5
```

有效的内部连接位是：

```text
pbits[1]: inst0 后是否连接 inst1
pbits[3]: inst1 后是否连接 inst2
```

常用编码：

| pbits | EP 结果 |
|---:|---|
| `0x00` | `inst0`、`inst1`、`inst2` 分别成 EP |
| `0x02` | `inst0 + inst1`，然后 `inst2` |
| `0x08` | `inst0`，然后 `inst1 + inst2` |
| `0x0a` | `inst0 + inst1 + inst2` |
| `0x1f` | 对纯 32-bit 三指令布局，相关有效位与 `0x0a` 一样都被置位 |

注意：`0x1f` 还设置了一些位于 32-bit 指令内部或无效位置的 p-bit。VLIWPU 只在完整指令结束边界检查 p-bit，所以当前 `.option norvc` 布局下通常不产生额外效果，但 `0x0a` 更能直接表达意图。

### 5.4 256-bit packet 的 p-bit

256-bit packet 中：

```text
32-bit header + 224-bit payload
```

纯 32-bit 指令时可放七条：

```text
inst0: slot 0,1
inst1: slot 2,3
...
inst6: slot 12,13
```

有效内部连接位：

```text
pbits[1], pbits[3], pbits[5], pbits[7], pbits[9], pbits[11]
```

`0xaaa` 设置这些奇数位，表示尽量连续打包。

但是当前 `MaxIssueSlots=8`，所以一个 EP 最多只有四条 32-bit 指令。即使 `pbits=0xaaa`，七条业务指令也至少会被 issue width 切成两组。

因此：

> `packet256=1` 扩大的是 logical packet 的软件布局窗口，不会把单个 EP 扩到七条 32-bit 指令。

### 5.5 `cross`

当：

- 当前 packet 尾部 EP 已经扫描到 packet 末尾；
- `cross=1`；
- EP 尚未达到 `MaxIssueSlots`；
- 当前和此前没有控制边界；

VLIWPU 可以保存该尾部 EP，并从下一 logical packet 的开头继续填充。

`cross` 适合：

- packet 尾部只有一两条独立指令；
- 下一 packet 开头有可安全合并的指令；
- 希望形成更接近四条 32-bit 指令的 EP。

`cross` 不适合：

- 前后 packet 之间有 scalar-to-vector RAW；
- 前一个 packet 尾部包含 branch/system；
- 后一个 packet 的 vector 指令需要前一 packet scalar 新结果；
- 仅为提高 `avg_EP_width` 而跨越真实依赖。

### 5.6 Loop marker

`loop_start` 和 `loop_end` 用于向 IPU 提供 loop 区域信息，支持 loop buffer 锁定和 replay。

它们不替代真实 branch：

- loop 是否继续仍由 branch 结果决定；
- taken backward branch 仍通过 redirect；
- marker 不自动构造计数器或控制依赖；
- marker 不允许 branch 后的指令继续执行。

### 5.7 Prefetch 字段

`prefetch_mode=0` 表示 1X，不表示关闭。

| `prefetch_disable` | `prefetch_mode` | 行为 |
|---:|---:|---|
| 1 | 任意 | 显式关闭 |
| 0 | 0 | 1X |
| 0 | 1 | 2X |
| 0 | 2 | 4X |
| 0 | 3 | 8X |

prefetch metadata 与 EP/vector command 对齐，并由符合条件的 unit-stride vector load 使用。

prefetch 与 p-bit 是两个独立维度：

- p-bit 决定前端分组；
- prefetch mode 决定候选未来地址；
- p-bit 更宽不保证 prefetch 更容易命中；
- prefetch miss 不应改变程序结果。

---

## 6. p-bit 选择原则

### 6.1 先判断依赖，再追求宽度

不要从“一个 packet 能装几条指令”开始设计。正确顺序是：

1. 写出程序顺序。
2. 标注每条指令读写的 GPR/FPR/vector register。
3. 标注 memory/control side effect。
4. 建立 RAW/WAR/WAW。
5. 判断依赖由哪个硬件模块覆盖。
6. 对未覆盖的边界设置 p-bit 为 0。
7. 对可安全重叠的边界设置 p-bit 为 1。
8. 最后再考虑 256-bit packet 和 cross。

### 6.2 边界决策表

相邻两条指令 `I0 -> I1` 之间可以考虑 `pbit=1` 的条件：

| 关系 | 建议 |
|---|---|
| 完全独立 scalar-scalar | 可以连接 |
| scalar-scalar RAW/WAW | 硬件可保序，但可能无并行收益 |
| vector-vector 有依赖 | 可由 Ara 保序，但 EP 不代表无依赖；主动切开可能改变性能 |
| scalar 写新值，vector 同 EP 读取 | 必须切开 |
| vector 写 scalar result，scalar 同 EP 读取 | 除专用 `vset` interlock 外必须切开 |
| vector 读旧 scalar，scalar 写下一轮新值 | 可使用 read-old pattern，但必须验证 |
| 任意 branch/system | 让硬件强制切，软件布局也应明确切开 |
| scalar/vector memory 有必须维持的 alias 顺序 | 保守切开，并确认完成条件足够 |
| 仅为增加 EP width、但依赖不清楚 | 切开 |

### 6.3 两种不可混用的 EP 契约

#### 当前兼容契约

- p-bit 是前端分组许可。
- scalar slice 内依赖由 scalar backend 处理。
- vector slice 内依赖由 Ara 常规 hazard 处理。
- 软件重点避免未覆盖的跨 scalar/vector 依赖。

当前 RTL 和现有 kernel 均按这套兼容契约工作。

#### 未来严格 VLIW 契约

- `pbit=1` 表示软件证明同 EP 指令满足规定的独立性。
- vector 同 EP RAW/WAR/WAW 必须不存在。
- scalar/vector same-EP 依赖也必须满足明确定义的快照/旁路规则。
- 编译器或静态 checker 必须验证寄存器组和 memory side effect。
- 若未来重新研究基于软件独立性证明的后端优化，还必须提供覆盖 Ara 全生命周期的唯一 identity 和静态验证工具。

严格契约不是当前 RTL 的正确性前提。

---

## 7. 普通 RVV Kernel 改写流程

### 7.1 第一步：固定功能和 ABI

先保留一个已经通过数值验证的普通 RVV 版本，并明确：

- 输入指针；
- 输出指针；
- AVL/N/rows；
- scalar coefficients；
- SEW/LMUL；
- tail/mask policy；
- 输出允许误差。

HDV task 入口寄存器必须和 testbench/Makefile 配置一致。例如：

```text
a0/a1/a2/a3...
fa0/fa1...
```

不要在还没有稳定 ABI 时开始调 p-bit。

### 7.2 第二步：转成可控汇编布局

推荐：

```asm
.option push
.option norvc
.option norelax
.balign 16
```

原因：

- `.option norvc` 使每条业务指令固定占两个 16-bit slot；
- `.option norelax` 避免链接器把指令改写成意外布局；
- `.balign 16` 使 task/关键 loop 与 128-bit fetch beat 对齐；
- 固定布局后才可以可靠计算 p-bit。

### 7.3 第三步：逐条建立读写表

对 loop 中每条指令填写：

| 序号 | 指令 | 类别 | GPR 读 | GPR 写 | FPR 读 | FPR 写 | VR 读 | VR 写 | memory/control |
|---:|---|---|---|---|---|---|---|---|---|
| 0 | `vsetvli t0,a0,...` | V | `a0` | `t0` | - | - | - | config | scalar-visible WB |
| 1 | `vle32.v v0,(a1)` | V | `a1` | - | - | - | - | `v0` | load |
| 2 | `sub a0,a0,t0` | S | `a0,t0` | `a0` | - | - | - | - | - |

对 LMUL 大于 1 的指令，必须展开 register group。例如 `m4` 下 `v4` 可能占用 `v4-v7`。只比较编码中的一个 `vd` 编号会漏掉 group overlap。

### 7.4 第四步：建立 dependence graph

至少标出：

- GPR RAW/WAR/WAW；
- FPR RAW/WAR/WAW；
- vector register RAW/WAR/WAW；
- scalar-visible vector result；
- memory alias/order；
- control dependence；
- loop-carried dependence。

loop-carried dependence同样重要。例如 reduction accumulator：

```asm
vfredsum.vs v0, v24, v0
```

每轮都读取并写回 `v0`，后端必须维护跨迭代依赖。

### 7.5 第五步：先采用保守 EP

bring-up 阶段建议：

- scalar producer 和 vector consumer 分 EP；
- vector scalar-result producer 和 scalar consumer 分 EP；
- branch 单独成 EP；
- 不清楚的 scalar/vector memory 边界分 EP；
- prefetch 先关闭；
- cross 先关闭；
- 先保留 Ara 常规 vector hazard。

保守版本通过数值验证后，再逐步合并独立指令。

### 7.6 第六步：把 EP 映射到 logical packet

假设希望三条指令形成：

```text
EP0 = inst0
EP1 = inst1 + inst2
```

则使用：

```asm
HDV_HINT 0x08
inst0
inst1
inst2
```

假设希望：

```text
EP0 = inst0 + inst1
EP1 = inst2
```

则使用：

```asm
HDV_HINT 0x02
inst0
inst1
inst2
```

### 7.7 第七步：再启用 packet256 和 cross

只有满足以下条件后才启用：

- 128-bit 版本功能正确；
- disassembly 与预期一致；
- 依赖表已完成；
- EP width 受 header 密度或 packet 尾部碎片限制；
- 合并不会跨越未覆盖的依赖。

### 7.8 第八步：选择 prefetch

对每条 unit-stride load，计算：

```text
B = 当前一次 vector load 的逻辑字节跨度
S = 相邻两次执行同一条 load 指令时的地址步长
```

理想模式满足：

```text
B * 2^prefetch_mode = S
```

例如：

- `S=B`：1X；
- `S=2B`：2X；
- `S=4B`：4X；
- `S=8B`：8X。

多路相邻 stream 还要考虑 lookup FIFO、prefetch buffer 和地址重叠，不能只按单流公式机械开启。

### 7.9 第九步：检查反汇编

必须确认：

- HINT 真的是 `lui x0, imm20`；
- 每个 packet 的 header 地址正确；
- 业务指令没有被压缩；
- 256-bit packet 的第二 beat 紧随第一 beat；
- branch target 指向 header，而不是 packet 中部；
- p-bit 对应的是完整指令结束 slot；
- `ret` 不会被 taken branch 路径错误执行。

### 7.10 第十步：分层验证

验证顺序：

1. task 是否完成；
2. 是否有 assertion/error；
3. 输出逐元素是否与 golden result 一致；
4. 浮点误差是否在预期范围；
5. 所有 AVL/N/LMUL 点是否正确；
6. prefetch 关闭时是否仍正确；
7. Ara 常规 hazard 保留时是否正确；
8. 最后才比较 cycles、EP width、prefetch hit 和 overlap。

---

## 8. 代表性实例

### 8.1 AXPY：同一 kernel 中同时存在多类依赖

当前 `apps/vsaxpy_hdv/main.c` 的核心结构：

```asm
HDV_HINT 0x02, 0, 1, 1, 0
vsetvli t0, a0, e32, m1, ta, ma
vle32.v v0, (a1)
sub     a0, a0, t0

HDV_HINT
vle32.v   v3, (a2)
slli      t1, t0, 2
vfmacc.vf v3, fa0, v0

HDV_HINT
add     a1, a1, t1
vse32.v v3, (a2)
add     a2, a2, t1
```

逐项解释：

1. `vsetvli -> sub` 是 vector-to-scalar RAW，依赖 `t0`。
2. `vle32.v v3 -> vfmacc.vf v3` 是 vector RAW+WAW。
3. `vse32.v (a2) -> add a2` 是 scalar/vector WAR，store 要读旧 `a2`。
4. `slli t1 -> later add` 是 scalar RAW。
5. 两个 load 和 FMA 的 vector dependency 需要 Ara 常规 hazard。

这说明当前 AXPY 的 EP 不是“完全无依赖 VLIW bundle”，而是“前端混合分组 + 后端动态保序”。

### 8.2 VADD：vector producer 到 vector store

当前 VADD：

```asm
HDV_HINT 0x0a
add      a2, a2, t1
vadd.vv  v16, v0, v8
vse32.v  v16, (a3)
```

`vadd.vv` 写 `v16`，`vse32.v` 读 `v16`，存在真实 RAW。

正确性依赖 Ara 识别 store 的 vector source，并等待 `v16` 数据就绪。不能用 same `ep_id` 把这条 RAW 清掉。

### 8.3 DOTP：loop-carried reduction

```asm
vfmul.vv    v24, v8, v16
vfredsum.vs v0, v24, v0
```

依赖包括：

- `vfmul -> vfredsum` 的 RAW；
- `v0` 在不同 loop iteration 之间的 reduction chain。

DOTP 的性能边界天然包含真实依赖。把 EP 做宽不会消除 reduction latency。

### 8.4 DWT：同一向量寄存器的计算链

```asm
vfadd.vv  v2, v0, v1
vfsub.vv  v3, v0, v1
vfmul.vf  v2, v2, ft0
vfmul.vf  v3, v3, ft0
```

两个 multiply 分别依赖前面的 add/sub。即使这些指令来自一个 256-bit logical packet，也不能因为同 EP 而消除 RAW/WAW。

### 8.5 STENCIL3：多 stream 和 accumulator chain

```asm
vle32.v    v1, (t4)
vle32.v    v2, (t5)
vfmacc.vf  v8, fa1, v1
vfmacc.vf  v8, fa2, v2
vse32.v    v8, (t6)
```

这里有：

- load 到 FMA 的 RAW；
- 两条 FMA 对 `v8` 的 accumulator RAW/WAW；
- FMA 到 store 的 RAW；
- 三路相邻 load stream 的 prefetch 竞争。

因此 STENCIL3 的优化不能只做“全 p-bit 置 1”。需要同时考虑 Ara dependency、VLSU stream 匹配和 command window 压力。

### 8.6 FIR5：四条连续 accumulator dependency

```asm
vfmacc.vf v8, fa1, v1
vfmacc.vf v8, fa2, v2
vfmacc.vf v8, fa3, v3
vfmacc.vf v8, fa4, v4
```

四条指令都读写 `v8`。

在当前兼容契约下，它们可以由 VDU 顺序发送，Ara 通过 hazard 维护 accumulator chain。它们处于同 EP 并不意味着四条 FMA 可以同时修改 `v8`。

在未来严格 VLIW 契约下，这四条必须切成不同 EP，或者改写算法使用多个独立 accumulator 后再归并。

后者是更有意义的软件优化。例如：

```text
v8  累加 tap0/tap2
v9  累加 tap1/tap3
最后 vadd v8,v8,v9
```

但这种变换会改变舍入顺序，需要重新验证浮点误差。

### 8.7 SYRK：load 后原地缩放

```asm
vle32.v  v4, (t2)
vfmul.vf v4, v4, fa1
```

这是最直接的 vector RAW+WAW 例子。`HDV_HINT 0x02` 把它们放入同 EP 并不证明独立。

### 8.8 GEMM：不同 rows 结构的区别

GEMM 1-row 中：

```asm
vle32.v   v0, (a3)
vfmacc.vf v8, fa0, v0
```

load 到 FMA 有 RAW。

4-row block 若使用四个不同 accumulator：

```text
v8, v9, v10, v11
```

不同 accumulator 的 FMA 之间可以提供更多独立性，但：

- 每条 FMA 仍依赖 B load；
- 同一 accumulator 跨 k iteration 仍有 loop-carried WAW/RAW；
- scalar `flw` 到 `.vf` FMA 是 FPR producer-consumer，通常必须分 EP。

### 8.9 SWAP：适合宽 EP 的独立 load

SWAP 中两个不同地址、不同目标寄存器的 vector load 通常更适合放在同一 EP：

```asm
vle32.v v0, (a0)
vle32.v v8, (a1)
```

如果两个 register group 不重叠、地址关系不要求额外顺序，这是真正能增加后端 memory-level parallelism 的分组。

---

## 9. 已移除的 Same-EP Hazard Suppression

### 9.1 原实验机制

原实验机制假设软件只把无向量寄存器依赖的指令放入同一 EP。VDU 序列化 vector slice 后继续携带 1-bit `ep_id`；Ara sequencer 为每个在飞 `vid` 保存该 ID，并在新旧 ID 相同时直接阻止对应 RAW、WAR、WAW hazard 位进入 hazard vector。

它不是“先检测并证明候选是假相关”，而是在常规相关位形成时直接豁免候选。

### 9.2 为什么删除

当前 kernel 中存在大量真实同 EP vector dependency，例如 AXPY 的 load-to-FMA、DOTP 的 multiply-to-reduction、DWT 的 add/sub-to-multiply，以及 GEMM 的 load-to-FMA。这些相关必须由 Ara 维护。

此外，1-bit `ep_id` 只覆盖 HEU/VDU 的 current/buffer 窗口。EP 被前端 acknowledge 后，旧请求仍可能在 Ara 中执行，而后续 EP 已经复用同一个 ID。因此该 ID 不能安全表示 Ara 全生命周期内的唯一 EP identity。

屏蔽相关位虽然可能减少 sequencer stall 和 task cycles，但被屏蔽项可能是真依赖，不能解释为合法性能收益。

### 9.3 当前 RTL

当前 sequencer：

1. 不保存每个 `vid` 的 HDV EP tag。
2. 不生成 `same_ep_vid_mask`。
3. 对所有请求统一生成 RAW、WAR、WAW hazard vectors。
4. 保留 `ep_id` 在 VDU 内部的响应归属、`vset` 写回匹配和 EP acknowledge 用途。

`HDV_ABLATION_NO_SAME_EP_BYPASS`、`haz`、`pf_haz` 模式以及 `seq_ep_bypass`、`same_ep_hazard_candidate`、`hazard_pruned_by_ep` 指标均已删除。

### 9.4 当前性能解释

删除后，`seq_raw_cycles`、`seq_war_cycles`、`seq_waw_cycles` 和各类 sequencer stall 反映常规 Ara 动态相关处理。它们可用于定位后端压力，但不能简单相加为互斥的总 stall breakdown。

EP 仍是前端分组和 scalar/vector hand-off 单位，不再携带“同 EP 向量相关可豁免”的软件承诺。

---

## 10. 推荐的 Kernel 编写检查表

### 10.1 功能

- [ ] 普通 RVV reference 已通过。
- [ ] HDV ABI 与 testbench/Makefile 初始寄存器一致。
- [ ] 输出逐元素与 golden result 一致。
- [ ] 所有 AVL/N/LMUL 组合都验证。
- [ ] 浮点 tolerance 明确。

### 10.2 布局

- [ ] task 在 `.hdv_task` section。
- [ ] task/loop 按 16 bytes 对齐。
- [ ] `.option norvc` 生效。
- [ ] `.option norelax` 生效。
- [ ] 反汇编中 header 和业务指令地址符合预期。
- [ ] branch target 指向 header 边界。

### 10.3 依赖

- [ ] 每条指令的 GPR/FPR/VR 读写已列出。
- [ ] LMUL register group overlap 已展开。
- [ ] loop-carried dependency 已标注。
- [ ] scalar-to-vector RAW 已切 EP。
- [ ] generic vector-to-scalar RAW 已切 EP。
- [ ] read-old pattern 是有意设计而不是偶然。
- [ ] scalar/vector memory alias 顺序有明确硬件依据。
- [ ] vector dependency 能由 Ara 常规 read/write-list 规则覆盖。

### 10.4 p-bit

- [ ] p-bit 只在完整指令结束边界有意义。
- [ ] 128-bit packet 的 `0x02/0x08/0x0a` 与目标 EP 一致。
- [ ] 256-bit packet 没有误认为一个 EP 可容纳七条 32-bit 指令。
- [ ] `cross=1` 没有跨越依赖或控制边界。
- [ ] 修改指令布局后重新计算 p-bit。

### 10.5 Prefetch

- [ ] `prefetch_disable=1` 才表示显式关闭。
- [ ] `prefetch_mode=0` 被理解为 1X。
- [ ] load 是适用的 unit-stride stream。
- [ ] 同一 load 的迭代步长与 mode 匹配。
- [ ] 多 stream 不会造成明显 lookup/prefetch buffer 冲突。
- [ ] prefetch 关闭时程序仍正确。

### 10.6 控制和退出

- [ ] branch 独立成清晰边界。
- [ ] taken branch 不会执行 packet 尾部 `ret`。
- [ ] loop_start/loop_end 覆盖真实 loop 区域。
- [ ] task completion 不早于必要的 scalar-visible result。
- [ ] watchdog 只用于发现卡死，不替代正确性检查。

---

## 11. 调试时应该观察什么

### 11.1 VLIWPU

观察：

- logical packet PC；
- header/pbits；
- 128/256；
- `issue_mask`；
- `issue_count`；
- `issue_next_head_slot`；
- `tail_cross_candidate`；
- 输出 slot/class/PC。

目标：确认软件期望的 EP 边界与 RTL 实际形成结果一致。

### 11.2 HEU

观察：

- current/buffer valid；
- scalar/vector slice valid；
- scalar/vector read/write mask；
- early issue candidate/grant/block reason；
- current/buffer vector ID；
- scalar/vector outstanding；
- EP acknowledge。

目标：确认两个后端何时接收 slice，buffered vector 是否越过了不安全边界。

### 11.3 Scalar backend 与 VDU

观察：

- scalar simple batch mask；
- scalar lane order hazard；
- XRF/FRF 写回；
- VDU operand request address/data；
- operand capture；
- command window push/pop；
- vector scalar-visible response；
- `vset_inflight`；
- `vec_store_inflight`。

目标：确认向量请求捕获的是旧标量值还是新标量值，consumer 是否在 producer 完成前推进。

### 11.4 Ara sequencer

观察：

- new request `vs1/vs2/vd/vm`；
- `read_list/write_list`；
- RAW/WAR/WAW hazard vectors；
- request ready；
- operand requester stall；
- `vinsn_running`。

目标：确认真实依赖进入对应 hazard vector，并在旧 `vid` 满足完成条件前阻止不安全推进。

### 11.5 VLSU/prefetch

观察：

- demand/prefetch candidate；
- AR handshake；
- lookup/ROB/prefetch queue entry；
- return data；
- demand hit；
- late/unused；
- stream break；
- page/burst split。

目标：区分“没生成预取”“资源阻止”“预取太晚”“地址不匹配”和“数据已返回但 lookup 顺序不允许命中”。

---

## 12. 设计改进方向

### 12.1 短期正确性优先

1. 保留 Ara 常规 RAW/WAR/WAW。
2. 为所有代表 kernel 增加逐元素 golden check。
3. 在文档和 kernel comment 中使用“前端分组”而不是“无依赖并行承诺”。

### 12.2 中期硬件增强

1. 建立 scalar-to-vector forwarding 或显式 interlock。
2. 将 vector-to-scalar scoreboard 从 `vset` 扩展到全部 scalar-visible result。
3. 对跨 scalar/vector memory order 定义完整、可验证的协议。
4. 让 `dep_break` 来自真实静态 metadata 或硬件 dependency checker，而不是常量零。

### 12.3 严格 VLIW 软件工具

若未来要让 p-bit 真正表示独立性承诺，建议提供静态 checker：

输入：

- ELF/disassembly；
- HINT/pbits；
- RVV SEW/LMUL 状态；
- scalar/vector register read/write；
- control/memory annotation。

检查：

- 同 EP GPR/FPR/VR group overlap；
- unsupported scalar-vector RAW；
- generic vector-scalar RAW；
- branch/system 边界；
- packet256/cross 边界；
- LMUL alignment；
- header/target alignment。

checker 用于验证 p-bit 分组、跨后端依赖和 memory-order contract，不改变 Ara 对向量寄存器相关的动态检查。

---

## 13. 阅读 RTL 的推荐顺序

1. `hardware/src/hdv/hdv_pkg.sv`
2. `hardware/src/hdv/hdv_task_interface_unit.sv`
3. `hardware/src/hdv/hdv_task_schedule_unit.sv`
4. `hardware/src/hdv/hdv_instruction_prefetch_unit.sv`
5. `hardware/src/hdv/hdv_vliw_pack_unit.sv`
6. `hardware/src/hdv/hdv_hybrid_execution_unit.sv`
7. `hardware/src/scala_backend/hdv_scalar_backend.sv`
8. `hardware/src/hdv/hdv_vec_dispatch_unit.sv`
9. `hardware/src/ara_sequencer.sv`
10. Ara lane operand requester 和 VLSU
11. `hardware/src/hdv/hdv_top.sv`
12. `hardware/tb/ara_tb.sv`

阅读 kernel 时建议依次看：

1. `apps/vsaxpy_hdv/main.c`
2. `apps/vvaddint32_hdv/main.c`
3. `apps/vsswap_hdv/main.c`
4. `apps/vsdot_hdv/main.c`
5. `apps/vsdwt_hdv/main.c`
6. `apps/vstencil3_hdv/main.c`
7. `apps/vfir5_hdv/main.c`
8. `apps/vsger_hdv/main.c`
9. `apps/vsgemv_hdv/main.c`
10. `apps/vsgemm_hdv/main.c`
11. `apps/vssyrk_hdv/main.c`
12. `apps/vstrsm_hdv/main.c`

这组顺序从简单流式、read-old pointer update，逐步过渡到 reduction、多 stream、矩阵 blocking 和强后端依赖。

---

## 14. 最终心智模型

可以用以下五句话记住当前 HDV：

1. HINT 和 p-bit 负责描述前端怎样分组，不自动证明依赖安全。
2. HEU 把一个 EP 拆给两个后端，EP acknowledge 只表示前端可以继续，不表示 Ara 已完成。
3. scalar slice 的局部依赖由 scalar backend 处理，vector slice 的寄存器依赖应由 Ara 常规 hazard 处理。
4. scalar/vector 跨后端只支持有限的 operand snapshot、`vset` interlock、early-issue gating 和 store-order guard，其他依赖由软件切 EP。
5. 性能优化顺序必须是：数值正确、依赖契约正确、EP 布局正确，然后才是 packet256、cross、prefetch 和 overlap。
