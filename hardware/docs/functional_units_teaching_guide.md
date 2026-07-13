# Ara 功能部件、归约与 Mask 单元 RTL 教学指南

本文面向希望从 SystemVerilog RTL 入手理解 Ara 微架构的读者。目标不是逐行翻译代码，而是覆盖每个模块中具有独立硬件含义的逻辑段：接口、数据组织、队列、数据通路、状态机、握手、写回以及特殊指令路径。对重复展开的组合网络，本文解释其生成规律和每类分支，而不机械重复数千条等价赋值。

## 1. 文档范围与源码入口

本文覆盖以下模块：

| 功能 | 核心模块 | 子模块或外部模块 |
|---|---|---|
| 整数、逻辑、移位、定点、比较 | `valu` | `simd_alu`、`fixed_p_rounding` |
| 整数乘法/MAC | `vmfpu` | `simd_mul` |
| 整数除法/余数 | `vmfpu` | `simd_div`、CVA6 `serdiv` |
| 浮点运算、浮点比较 | `vmfpu` | `fpnew_top` |
| Slide、重排、跨 lane 归约交换 | `sldu` | `sldu_op_dp`、`p2_stride_gen` |
| Mask、bit-level 操作 | `masku` | `masku_operands`、`popcount`、`lzc` |

主要源码：

- [`valu.sv`](../src/lane/valu.sv)
- [`simd_alu.sv`](../src/lane/simd_alu.sv)
- [`fixed_p_rounding.sv`](../src/lane/fixed_p_rounding.sv)
- [`vmfpu.sv`](../src/lane/vmfpu.sv)
- [`simd_mul.sv`](../src/lane/simd_mul.sv)
- [`simd_div.sv`](../src/lane/simd_div.sv)
- [`sldu.sv`](../src/sldu/sldu.sv)
- [`sldu_op_dp.sv`](../src/sldu/sldu_op_dp.sv)
- [`masku.sv`](../src/masku/masku.sv)
- [`masku_operands.sv`](../src/masku/masku_operands.sv)
- [`fpnew_top.sv`](../deps/fpnew/src/fpnew_top.sv)，来自外部 `fpnew` 依赖

这些模块并不直接解码 32-bit RISC-V 指令。前端 [`ara_dispatcher.sv`](../src/ara_dispatcher.sv) 将指令解码成 `ara_op_e` 和控制字段，主 [`ara_sequencer.sv`](../src/ara_sequencer.sv) 决定目标 VFU，随后每个 [`lane_sequencer.sv`](../src/lane/lane_sequencer.sv) 产生 VRF operand request 和 `vfu_operation_t`。

整体路径如下：

```text
CVA6 指令
  -> ara_dispatcher：解码、SEW/LMUL/寄存器和转换信息
  -> ara_sequencer：scoreboard、目标 VFU、全局完成条件
  -> lane_sequencer：每 lane 的 operand request 和 VFU command
  -> operand_requester -> vector_regfile -> operand_queue
  -> valu / vmfpu / sldu / masku
  -> operand_requester 仲裁写回 -> vector_regfile
```

## 2. 阅读这些 RTL 前需要掌握的 SystemVerilog 语法

### 2.1 `parameter`、`localparam` 与类型参数

```systemverilog
module valu #(
  parameter int unsigned NrLanes = 0,
  parameter type vaddr_t = logic,
  localparam int unsigned DataWidth = $bits(elen_t)
) (...);
```

- `parameter` 可在实例化时覆盖，用来生成不同 lane 数、VLEN 或功能配置的硬件。
- `parameter type` 传递一个类型而不是数值，使模块不必写死地址宽度或 command struct。
- `localparam` 是模块内部推导常量，调用者不能覆盖。
- `$bits(T)` 返回类型或信号的位宽；`$clog2(N)` 返回容纳 `N` 个状态所需的向上取整对数。

这些都是 elaboration-time 机制：综合前就确定结构，不会变成运行时寄存器。

### 2.2 packed array、struct 和 union

```systemverilog
typedef union packed {
  logic [0:0][63:0] w64;
  logic [1:0][31:0] w32;
  logic [3:0][15:0] w16;
  logic [7:0][ 7:0] w8;
} alu_operand_t;
```

这是同一条 64-bit 总线的四种视图：1 个 64-bit、2 个 32-bit、4 个 16-bit 或 8 个 8-bit 元素。`packed union` 中所有成员共享同一组比特，不产生四份存储。

```systemverilog
typedef struct packed {
  vid_t id;
  vaddr_t addr;
  elen_t wdata;
  strb_t be;
  logic mask;
} payload_t;
```

`packed struct` 将多个字段拼成一条定宽总线，适合放进 FIFO 或寄存器数组。

注意声明：

```systemverilog
elen_t [NrLanes-1:0] operand;
```

`elen_t` 本身是 packed 类型，右侧 `[NrLanes-1:0]` 也是 packed 维度，因此整体可直接拼接、按 lane 索引，也能整体赋值为 `'0`。

### 2.3 `always_comb`、`always_ff` 与 d/q 命名

Ara 大量使用 next-state 写法：

```systemverilog
always_comb begin
  state_d = state_q;
  if (event) state_d = NEXT;
end

always_ff @(posedge clk_i or negedge rst_ni) begin
  if (!rst_ni) state_q <= IDLE;
  else         state_q <= state_d;
end
```

- `_q` 表示寄存器当前值。
- `_d` 表示组合逻辑算出的下一拍值。
- `always_comb` 内通常使用阻塞赋值 `=`，从上到下描述组合优先级。
- `always_ff` 内使用非阻塞赋值 `<=`，表示所有寄存器在时钟沿同时更新。
- 组合块开头先给所有 `_d` 默认值，可以避免推导 latch。

### 2.4 continuous assignment、generate-if 和 `genvar`

```systemverilog
assign ready_o = stage_ready[0];

if (NumPipeRegs > 0) begin : gen_pipeline
  for (genvar i = 0; i < NumPipeRegs; i++) begin : gen_stage
    ...
  end
end
```

`assign` 持续驱动组合网络。模块作用域的 `if` 和 `for (genvar ...)` 是 generate 结构，只在 elaboration 时决定实例数量。例如 `NumPipeRegs=0` 时，乘法器流水寄存器根本不会生成。

### 2.5 `inside`、范围匹配和 `unique case`

```systemverilog
if (op inside {[VREDSUM:VWREDSUM]}) ...
```

`inside` 是集合成员测试；`[A:B]` 表示枚举编码从 A 到 B 的闭区间。Ara 的 `ara_op_e` 特意按功能连续排列，因此常用范围快速分类。

```systemverilog
unique case (op)
  VADD: ...
  VSUB: ...
  default: ...
endcase
```

`unique` 声明最多一个分支应匹配，并允许工具对互斥条件优化；仿真器还可能对无匹配或多匹配发出告警。它不是普通软件 `switch`，每个分支最终仍综合成译码和多路器。

### 2.6 位选、变宽和 reduction operator

```systemverilog
x[base +: width]
x[base -: width]
```

分别表示从 `base` 向高位或低位选择固定宽度。宽度必须是 elaboration-time 常量，`base` 可以动态变化。

```systemverilog
{{56{sign}}, value[7:0]}
```

`{N{expr}}` 是 replication，常用于符号扩展。

```systemverilog
&valid_vec   // 所有位 AND
|data        // 是否存在任意 1
^data        // 所有位 XOR
```

一元 `& | ^` 是 reduction operator，与二元按位运算不同。

### 2.7 类型转换和 assignment pattern

```systemverilog
rvv_pkg::vew_e'(value)
logic'(condition)
'{id: id, addr: addr, default: '0}
```

- `type'(expr)` 是显式类型转换，避免枚举/位宽告警。
- `'{field: value, default: '0}` 按字段构造 packed struct，未列出的字段用默认值填充。
- `'0`、`'1` 会自动扩展到左值宽度，分别表示全 0、全 1。

### 2.8 valid/ready 握手

Ara 遵循 decoupled handshake：

```text
transfer = valid && ready
```

生产者在 `valid=1` 且尚未握手时必须保持 payload 稳定；消费者用 `ready` 表示本拍可接收。反压会沿 result queue、operand queue 和 VFU 流水向前传播。

`spill_register` 是一个单级弹性缓冲，既切断长组合路径，也保持 valid/ready 语义。

### 2.9 Ara 的寄存器宏

```systemverilog
`FF(q, d, reset_value, clk, rst_n)
`FFL(q, d, enable, reset_value)
```

这些宏来自 `common_cells/registers.svh`：`FF` 生成普通带复位寄存器，`FFL` 生成带 load-enable 的寄存器。阅读时可将其理解为相应的 `always_ff`。

## 3. `valu`：lane 内整数执行控制器

### 3.1 模块职责

`valu` 不是单纯的加法器。它是整数 VFU 的小型执行流水控制器，负责：

1. 保存最多 `ValuInsnQueueDepth` 条在途指令。
2. 从 `AluA/AluB` operand queue 接收 64-bit 数据拍。
3. 复制 scalar operand，处理 narrowing 两拍写入。
4. 调用 `fixed_p_rounding` 与 `simd_alu`。
5. 对普通结果排队，送 VRF 或 MASKU。
6. 控制整数归约的 lane 内、跨 lane 和 lane 0 最终折叠。
7. 产生 `vxsat` 和完成标志。

### 3.2 接口分组

- `vfu_operation_i/valid_i`：来自 `lane_sequencer` 的指令级 command。
- `alu_operand_i[1:0]`：两个 operand queue 输出，通常对应 `vs1` 和 `vs2`。
- `alu_result_*`：写回 VRF 的 request/payload/grant。
- `mask_operand_*`：结果目标是 mask layout 时，送到全局 MASKU，而非直接写 VRF。
- `mask_i/mask_valid_i/mask_ready_o`：MASKU 广播来的每字节 predicate strobe。
- `alu_red_valid_o` 与 `sldu_*`：归约 partial result 和 SLDU 的握手。

### 3.3 lane ID 处理

源码将 `lane_id_i` 复制到固定宽度 `lane_id`。lane 0 在归约中有特殊职责：只有 lane 0 使用真实的 `vs1[0]` 初值，并接收跨 lane 最终结果；其他 lane 使用中性值。设计没有用 generate 为 lane 0 生成不同模块，是为了保持层次化综合/P&R 时各 lane 结构一致。

### 3.4 指令队列

`vinsn_queue` 为每条指令保存 `vfu_operation_t`，并维护：

- `accept_pnt`：新指令写入位置。
- `issue_pnt`：当前产生 micro-op 的指令。
- `commit_pnt`：当前等待结果写回完成的指令。
- `issue_cnt/commit_cnt`：相应阶段的在途指令数。

三组指针允许不同指令分别处于接收、执行和写回阶段。`vinsn_queue_full` 用 commit 数判断，因为只有结果全部提交后槽位才真正可复用。

队列寄存器在独立 `always_ff` 中更新。复位时指针和计数清零；正常时整体执行 `vinsn_queue_q <= vinsn_queue_d`。

### 3.5 result queue

result queue 的 payload 包含：

- `id`：指令 ID，用于 scoreboard/completion。
- `addr`：lane 本地 VRF 地址。
- `wdata`：64-bit 数据。
- `be`：8-bit byte enable。
- `mask`：结果应送 MASKU 还是直接送 VRF。

读写指针和 `result_queue_cnt` 构成环形 FIFO。`full` 阻止继续执行，形成反压。普通算术每处理一个 64-bit beat 就产生一个 entry；narrowing 可能两拍才拼满一个 entry；归约则把当前 write entry 临时当 accumulator。

### 3.6 MASKU 输出 spill register

当 result entry 的 `mask=1` 时，`mask_operand_valid` 有效。数据经过 `spill_register` 送 MASKU。这样做有两点：

1. MASKU 的反压不会直接形成从全局单元到 lane ALU 的超长组合路径。
2. 同一个 result queue 可以统一管理“写 VRF”和“送 MASKU”两种目的地。

`mask_operand_gnt = valid && ready`，与 `alu_result_gnt_i` 一起决定 result entry 何时出队。

### 3.7 scalar operand replication

`scalar_op` 根据 `vsew` 将标量低位复制到整个 64-bit SIMD word：

- EW8：8 份低 8 bit。
- EW16：4 份低 16 bit。
- EW32：2 份低 32 bit。
- EW64：原值。

因此后端 `simd_alu` 不需要区分 `vv` 和 `vx/vi`，只看到两个同宽 SIMD operand。

### 3.8 narrowing 控制

`VNSRL/VNSRA/VNCLIP/VNCLIPU` 的输入元素宽于输出元素。一个 64-bit 输入拍只能生成目标 word 的一半位置，因此 `narrowing_select_q` 在两次 micro-op 间翻转：

- 第一拍写目标 word 的偶数槽或低半布局。
- 第二拍写另一个半布局。
- 两半齐全后 result queue entry 才置 valid，并确认 mask operand。

`narrowing(op)` 是 `automatic function`，仅由 opcode 组合判断，不保存状态。

### 3.9 归约输入和状态

整数归约 opcode 范围为 `VREDSUM` 到 `VWREDSUM`。归约 FSM：

```text
NO_REDUCTION
  -> INTRA_LANE_REDUCTION
  -> INTER_LANES_REDUCTION_TX
  -> INTER_LANES_REDUCTION_RX
  -> ... TX/RX 多轮 ...
  -> SIMD_REDUCTION（lane 0）
  -> 正常写回

非 lane 0：最后进入 LN0_REDUCTION_COMMIT 后完成。
```

SLDU 返回数据先经过 `i_alu_reduction_spill_register`，切断全局 SLDU 到 ALU accumulator 的时序路径。

`reduction_rx_cnt_init()` 决定每个 lane 在树形归约中需要真正合并多少次。某些 lane 在部分轮次只是握手同步，不执行 ALU 运算。当前硬编码覆盖最多 16 lane。

### 3.10 归约 operand MUX

`alu_operand_a` 在不同阶段来自：

- 第一拍：`vs1[0]` 的 replicated scalar，其他 lane 对应中性值。
- 后续 lane 内归约：result queue 中 accumulator。
- 跨 lane 或 SIMD 归约：仍以 accumulator 为一端。

`alu_operand_b` 来自：

- lane 内阶段：`vs2` 数据拍。
- 跨 lane阶段：`sldu_operand_q`。
- lane 0 最后 SIMD 折叠：从 accumulator 的高子元素抽出的 `simd_red_operand`。

同一套 `simd_alu` 因而被普通整数、lane 内归约、跨 lane 合并和最终 word 内折叠复用。

### 3.11 fixed-point rounding 实例

仅当 `FixPtSupport == FixedPointEnable` 时生成 `fixed_p_rounding`。它输出每个 SIMD 元素一个 rounding increment bit `r`。关闭定点支持时直接 `assign r='0`，相关逻辑在综合时被裁掉。

### 3.12 `simd_alu` 实例

`valu_valid` 表示本拍确实执行一个 micro-op。送入的 mask 为：

```systemverilog
(mask_valid_i && !vm) ? mask_i : '1
```

即 unmasked 指令全部 byte active；masked 指令等待 MASKU 提供 strobe。`simd_alu` 输出 `valu_result` 和 per-element saturation bits。

### 3.13 `p_valu` 组合控制块的默认段

组合块开头完成四件事：

1. 所有队列、指针、计数器默认保持。
2. 所有 output valid/ready 默认拉低。
3. 计算本拍按 SEW 可处理的元素数。
4. 根据 `alu_state_q` 覆盖默认行为。

这是典型“默认保持 + 条件覆盖”的 FSM 写法。后写赋值具有更高组合优先级。

### 3.14 普通执行 `NO_REDUCTION`

只有 result queue 不满、当前指令不是归约、所需 operand 均 valid，并且 masked 指令已有 mask 时才能发射。

发射后：

- `valu_valid=1`。
- 对使用到的 operand 拉高 ready。
- 生成 `wdata/id/addr/be/mask`。
- 扣减 `issue_cnt`。
- 非 narrowing 立即 push result entry。
- 指令所有元素发射完后推进 `issue_pnt`。

`be(element_cnt, vsew)` 只打开本拍真实有效元素的字节，处理最后不足一整拍的情况。

### 3.15 `INTRA_LANE_REDUCTION`

每个 lane 先独立累积自己负责的元素：

- 第一拍需要 `vs1` 和 `vs2`；以后只需新的 `vs2`，另一端是 accumulator。
- `red_mask` 合并 `vl` 边界和 predicate mask。
- inactive byte 保持原 accumulator，而不是写入 ALU 输出。
- 当前 lane 的所有元素处理完后转入 TX。

`prevent_commit=1` 防止元素数较少的 lane 提前报告完成，因为它仍需参加全局同步。

### 3.16 `INTER_LANES_REDUCTION_TX/RX`

TX 将本 lane partial result 送入共享 SLDU。收到 grant 后进入 RX。RX 收到 SLDU 返回的数据时：

- 若 `reduction_rx_cnt_q != 0`，用 `simd_alu` 合并远端 partial 与本地 accumulator。
- 若该 lane 此轮不活动，只完成握手。
- `sldu_transactions_cnt` 控制全局树的轮数。

最后一轮结果被送到 lane 0。其他 lane 转到 `LN0_REDUCTION_COMMIT`，只等待整体完成。

### 3.17 `SIMD_REDUCTION`

跨 lane 后，lane 0 的 64-bit word 里仍可能有多个 SEW 元素。例如 EW8 有 8 个 partial。状态机依次从高半提取 32/16/8-bit 子块，与低部 accumulator 再运算，形成 log2(64/SEW) 次 word 内折叠。

完成后只以 `be(1, vsew)` 写回 `vd[0]` 所在元素。

### 3.18 写回和完成

普通 entry 在 `NO_REDUCTION` 下可请求 VRF。归约中间结果不能写 VRF，只有最终 `SIMD_REDUCTION` entry 可写。

收到 VRF grant 或 MASKU grant 后：

- 清 valid。
- 推进 result read pointer。
- 对非归约扣减 commit element count。

当 `commit_cnt==0 && !prevent_commit`：

- 产生 `alu_vinsn_done_o[id]`。
- 释放指令 queue entry。
- 若是归约，产生 `alu_red_complete_o`，让 lane 内 SLDU/ADDRGEN arbiter 释放共享通道。

### 3.19 接受新指令

`valu` 接受两类 command：

1. `vfu == VFU_Alu` 的普通 ALU 指令。
2. `VMSEQ...VCOMPRESS` 范围的 mask 相关指令，因为它们虽以 MASKU 为主 VFU，仍需 VALU 预处理。

比较类在 ALU 内被强制视为 unmasked，真正的 mask-undisturbed/tail 处理交由 MASKU；`VMADC/VMSBC` 是例外，它们把 `v0` 当 carry/borrow 输入，因此 ALU 仍需 mask bits。

## 4. `simd_alu`：64-bit 组合 SIMD 算术数据通路

### 4.1 模块定位

`simd_alu` 基本是无流水组合模块。控制、排队、反压都在 `valu`；它只根据 `op_i/vew_i` 将两个 64-bit operand 映射成结果。

### 4.2 union 视图

`opa/opb/res` 用 packed union 同时提供 EW8/16/32/64 视图。`assign result_o=res` 不增加硬件，只是类型重解释。

### 4.3 比较预计算

`p_comparison` 为每个元素计算 `less` 和 `equal`。有效位放在每个元素最低 byte 对应的位置：EW8 使用 bit 0..7，EW16 使用 0/2/4/6，EW32 使用 0/4，EW64 使用 0。

符号比较通过在 operand 前拼接符号位实现：

```systemverilog
$signed({is_signed & sign_bit, operand})
```

无符号操作时前缀为 0；有符号操作时进行一位符号扩展。这样可复用同一个 `$signed` 比较表达式。

### 4.4 逻辑与 mask logical

- `VAND/VOR/VXOR` 与相应归约 opcode 直接按位运算。
- `VMAND/VMANDNOT/VMNAND/VMOR/VMNOR/VMORNOT/VMXOR/VMXNOR` 也是 64-bit 按位逻辑。

这些 mask logical 的实际逻辑在 ALU 完成，但结果仍是 VRF 的特殊 mask layout，所以 `valu` 将结果送 MASKU 做重排和 bit-level 写回。

### 4.5 MASKU 辅助 pass-through

- `VCPOP/VFIRST/VMSBF/VMSOF/VMSIF/VIOTA` 将 `operand_b` 原样送 MASKU。
- `VRGATHER/VRGATHEREI16/VCOMPRESS` 将 `operand_a` 原样送 MASKU。

这不是“ALU 实现了这些指令”，而是复用现有 ALU result channel 将 operand 搬到集中式 MASKU。

### 4.6 加减、carry/borrow

`VADD/VREDSUM/VWREDSUM*` 按 SEW 分成 8/4/2/1 个加法。`VADC/VMADC` 额外加上 `mask_i` 中的 carry-in。

`VMADC` 不返回普通和，而把 carry-out 编码到每个元素结果的低两位附近，使后续 `masku_operands` 可以抽取为 1-bit mask。

`VSBC/VMSBC` 同理处理 borrow-in 与 borrow-out。注意源码 operand 命名对应实际表达式 `opb - opa`，阅读指令语义时应以 dispatcher/lane_sequencer 的 operand 路由为准。

### 4.7 saturating add/sub 与 average add/sub

`VSADDU/VSADD/VSSUBU/VSSUB` 先做多一位运算，再根据 carry 或符号溢出选择饱和值，同时产生 `vxsat`。

`VAADD/VAADDU/VASUB/VASUBU` 先算扩展和/差，再右移一位并按 `vxrm` 加 rounding bit。

### 4.8 shift 与 narrowing shift

- `VSLL/VSRL/VSRA` 分别进行逻辑左移、逻辑右移、算术右移。
- shift amount 只取 `log2(SEW)` 个低位，符合 RVV 规则。
- `VNSRL/VNSRA` 从 2×SEW 输入产生 SEW 输出，目标槽由 `narrowing_select_i` 决定。

算术右移对 operand 使用 `$signed`，逻辑右移保持无符号。

### 4.9 rounding shift 与 clip

`VSSRL/VSSRA` 使用外部 `fixed_p_rounding` 产生的 `rm`，把它加到移位结果。

`VNCLIP/VNCLIPU` 做宽输入右移、舍入和窄化，并检查被裁掉的高位以产生 saturation。最终槽位同样由 `narrowing_select_i` 控制。

### 4.10 merge 和 scalar move

`VMERGE` 逐元素根据 mask bit 在 `opa/opb` 间选择。虽然 mask 接口是 byte strobe，但每个元素只查看对应首 byte 的 mask bit。

`VMVSX/VFMVSF` 直接传递已经由上层排好格式的 `opa`。

### 4.11 min/max 和归约 min/max

普通 `VMIN/VMAX` 与 `VREDMIN/VREDMAX` 复用 `less` 结果。opcode 决定选择较小或较大 operand，有符号/无符号则由 `is_signed` 控制。

### 4.12 integer comparison mask

`VMSEQ/VMSNE/VMSLT*/VMSLE*/VMSGT*` 把比较结果编码进每个元素低位，同时保留一位 mask 信息。MASKU 后续只抽取每个元素的比较 bit、压缩成连续 mask bits，并处理旧 `vd` 与 tail/mask policy。

### 4.13 默认赋值与组合完整性

`p_alu` 开头令 `res='0`、`vxsat='0`，末尾有 `default`。这样每种输入都有确定输出，不会推导 latch。`valid_i=0` 时输出保持默认组合值，而不是保持上一拍。

## 5. `fixed_p_rounding`：定点舍入增量生成

### 5.1 模块输出的含义

该模块不直接完成移位，只计算每个 SIMD 元素应不应该在截断结果上加 1，输出 `r_o`。它只服务：

- `VSSRA/VSSRL`
- `VNCLIP/VNCLIPU`

### 5.2 operand 解释

- `operand_a_i`：shift amount。
- `operand_b_i`：被移位数据。
- `j`：当前元素的动态 shift amount。
- `bit_select[j]`：低 `j` 位为 1 的掩码，用来判断被丢弃位中是否存在 1。

`bit_select` 声明为 64 个 64-bit 项的 packed array，常量表第 `j` 项等价于 `(1<<j)-1`。

### 5.3 四种 `vxrm`

RVV 定点舍入模式在代码中对应：

| `vxrm` | 名称 | rounding increment 思路 |
|---|---|---|
| `00` | RNU | 取被丢弃部分最高位 `v[j-1]` |
| `01` | RNE | tie-to-even，结合 `v[j-1]` 与保留最低位 `v[j]`/sticky |
| `10` | RDN | 永不加 1 |
| `11` | ROD | 若结果最低位为 0 且丢弃部分非零，则加 1 使结果变奇数 |

源码对 EW8/16/32/64 重复相同公式，只是循环元素数不同。

### 5.4 动态位选语法

```systemverilog
r_o[i] = opb.w8[i][j-1];
```

内层索引 `j-1` 是运行时动态 mux。阅读时要注意 shift amount 为 0 的边界；RISC-V 舍入公式在 shift=0 时应不增加，验证时应专门观察该输入是否由上游或综合/仿真语义正确处理。

### 5.5 查找表的硬件含义

常量 `bit_select` 通常综合成比较/移位或 mux 化常量网络，而不是存储 RAM。它用于构造 sticky-bit：

```systemverilog
|(operand & bit_select[j])
```

表示被截断的低 `j` 位中至少有一位为 1。

## 6. `vmfpu`：乘法、除法与浮点执行控制器

### 6.1 模块职责

`vmfpu` 把三类不同延迟的执行资源统一成一个 VFU：

1. `simd_mul`：整数乘法、MAC、定点 `vsmul`。
2. `simd_div`：整数除法与余数。
3. `fpnew_top`：浮点算术、转换、比较、浮点归约。

它还负责多条在途指令、不同单元延迟的顺序化、result queue、FP exception flags、mask 结果转发以及复杂的浮点归约状态机。

### 6.2 三 operand 接口

`mfpu_operand_i[2:0]` 对应 A/B/C 三个输入。不同 opcode 会交换 `vs2` 和旧 `vd`：

- 普通乘加需要 `vs1`、`vs2`、`vd`。
- 某些浮点 add/sub 为适配 FMA 数据通路，会把源操作数路由到 C。
- `swap_vs2_vd_op` 控制 operand 与 ready 的同步交换。

因此不要仅凭数组下标判断架构源寄存器，应同时查看 `lane_sequencer` 的 request 和 `vmfpu` 的 operand mux。

### 6.3 指令队列与 processing 阶段

相比 `valu`，VMFPU 队列多一个 `processing_pnt/processing_cnt`：

```text
accept -> issue -> processing -> commit
```

原因是乘法/FPU 有流水延迟：指令的输入可能已经全部发射，但结果仍在执行单元中。processing pointer 用于解释返回结果属于哪条指令、使用哪种 SEW 和 mask。

### 6.4 scalar replication 与 narrowing

scalar operand 同样按 SEW 复制。FP narrowing/widening 还需要：

- `cvt_resize` 指示 wide/same/narrow。
- `narrowing_select_in/out` 跟踪输入、输出的半字位置。
- 对 FP8/FP16/FP32 做重排和 subnormal normalization 辅助。

### 6.5 clock-gating 数据寄存器

VMFPU 为不同 SEW multiplier 的 operand、mask、opcode 使用 power-gating wrapper。`clkgate_en` 只在乘法请求到来时更新相关寄存器，以减少大乘法阵列无效翻转。`GF22` 宏选择工艺专用 gating cell，否则使用 generic 实现。

这是 conditional compilation：`` `ifdef GF22`` 在预处理阶段选择源码分支。

### 6.6 四套 `simd_mul`

VMFPU 分别实例化 EW64/32/16/8 multiplier。每套在 64-bit datapath 内拥有不同数量的并行乘法 lane，并可配置不同 pipeline latency。

只有与当前 `vsew` 对应的实例收到 `valid`。输出 mux 用 processing 指令的 `vsew` 选择结果，确保与流水返回时刻对齐。

### 6.7 `simd_div`

整数除法只实例化一套 serial divider。一个 64-bit SIMD word 内的多个小元素依次送入 divider，因此吞吐低于乘法，但显著节省面积。`issue_be` 让 masked/tail 元素直接 skip，避免无意义的长除法。

### 6.8 浮点归约辅助状态

浮点归约比整数复杂，因为 FPU 有多拍延迟且结果可能乱序返回。相关状态包括：

- `INTRA_LANE_REDUCTION`
- `INTER_LANES_REDUCTION_TX/RX`
- `SIMD_REDUCTION`
- `OSUM_REDUCTION`
- `MFPU_WAIT`

`ntr_filling` 在首个真实 FPU 结果尚未返回时注入中性值，保持流水持续推进。`first_result_op_valid` 区分 result queue 的旧值和本拍新返回值。

### 6.9 unordered reduction

`VFREDUSUM/VFREDMIN/VFREDMAX/VFWREDUSUM` 采用：

1. lane 内 FPU 归约。
2. SLDU 对数树交换 partial。
3. lane 0 最终 SIMD word 内归约。

min/max 的中性值分别为正无穷和负无穷；sum 为正零。masked 或最后不完整 packet 的元素替换成中性值。

### 6.10 ordered sum reduction

`VFREDOSUM/VFWREDOSUM` 必须维持元素顺序，不能使用任意重关联的树。`next_mfpu_state()` 将其送到 `OSUM_REDUCTION`：

- 只有当前持有顺序中下一个元素的 lane 真正发射 FPU operation。
- accumulator 由 SLDU 依次送到下一 lane。
- 最终结果回到 lane 0。

这条路径延迟更高，但符合 ordered reduction 语义。

### 6.11 FPU opcode preprocessing

VMFPU 将 Ara opcode 翻译成 `fpnew_pkg::operation_e`：

- add/sub/reduction sum -> `ADD`
- mul -> `MUL`
- FMA family -> `FMADD/FNMSUB` 加 `op_mod`
- div/sqrt -> `DIV/SQRT`
- min/max -> `MINMAX`
- comparisons -> `CMP`
- classify -> `CLASSIFY`
- float/int/float-width conversions -> `F2I/I2F/F2F`

同时设置：

- `fp_rm` rounding mode。
- `fp_src_fmt/fp_dst_fmt/fp_int_fmt`。
- operand sign inversion。
- reduction neutral value。

### 6.12 `fpnew_top` 接口

VMFPU 使用 64-bit vector mode：

- `vectorial_op_i=1`
- `simd_mask_i` 屏蔽 inactive element，使其不产生异常。
- `tag_i` 携带 byte mask/归约标记穿过可变延迟流水。
- `status_o` 返回 NV/DZ/OF/UF/NX flags。

`vfpu_in_valid/ready` 和 `vfpu_out_valid/ready` 构成两端独立握手。

### 6.13 `vfrec7/vfrsqrt7` 后处理

如果 `FPExtSupport` 打开，VMFPU 在 fpnew 返回的分类/中间信息基础上使用查找与 leading-zero 信息构造 `vfrec7/vfrsqrt7` 近似结果，并选择相应 exception flags。这部分是 fpnew 外的 Ara 扩展后处理通路。

### 6.14 浮点比较结果编码

`VMFEQ...VMFGE` 的 fpnew comparison bit 被放到每元素固定低位。`VMFNE` 因 fpnew 没有原生 not-equal，在返回后取反。结果不直接写 VRF，而由 MASKU 抽取、压缩和重排成 mask layout。

### 6.15 latency stall

fpnew 内不同 operation latency 不同，甚至 div/sqrt 是可变延迟。Ara 的上层 result queue 假设按指令顺序处理，因此 VMFPU 比较 issue 指令和 processing 指令延迟：

- 新指令比旧指令更快时 stall，避免后发先至。
- 任一指令为 div/sqrt 且 ID 不同时保守 stall。

这是在支持多条在途指令的同时维持 in-order commit 的关键逻辑。

### 6.16 普通 `NO_REDUCTION` 状态

当 operand、mask 和目标单元 ready 时：

- opcode 范围 `VMUL...VSMUL` 发给 multiplier。
- `VDIVU...VREM` 发给 divider。
- `VFADD...VMFGE` 发给 fpnew。
- 扣减 issue count，并将 byte enable/tag 随流水传递。

processing 侧根据 opcode 范围选择 `unit_out_*`，将结果 push 到统一 result queue。

### 6.17 reduction 状态机

unordered reduction 的 TX/RX 与 `valu` 类似，但每次 merge 必须等待 fpnew 输出重新 valid。`SIMD_REDUCTION` 也通过 fpnew 多次合并 word 内元素。

`OSUM_REDUCTION` 单独维护 `osum_issue_cnt`，逐元素从 64-bit word 中取值，并与 SLDU accumulator 结合。

`MFPU_WAIT` 保证 lane 0 的最终 VRF write grant 完成后才能复用 accumulator/commit 状态。

### 6.18 result queue、mask 转发和写回

result payload 的 `mask` 表示结果目标：

- 普通数值 -> `mfpu_result_req_o` 写 VRF。
- FP comparison -> `mask_operand_o` 送 MASKU。

收到任一目标的 grant 后 entry 出队。非归约按每拍元素数扣 commit count；归约最终只提交一个元素。

### 6.19 接受新指令

VMFPU 接受 `vfu==VFU_MFpu`，也接受 `VMFEQ...VMFGE`，因为浮点比较的主目标虽标为 MASKU，实际比较仍在 fpnew 计算。

比较指令进入 VMFPU 后会：

- 强制 `vm=1`，避免 VMFPU 本地直接应用 predicate；bit-level policy 交给 MASKU。
- 清 `use_vd_op`，旧 `vd` 由 MaskB queue 单独送 MASKU。

## 7. `simd_mul`：按 SEW 生成的并行整数乘法器

### 7.1 参数化结构

每个实例固定一个 `ElementWidth`。generate-if 在 EW64/32/16/8 四种结构中只生成一种：

- EW64：1 个 64×64 -> 128 multiplier。
- EW32：2 个 32×32 -> 64 multiplier。
- EW16：4 个 16×16 -> 32 multiplier。
- EW8：8 个 8×8 -> 16 multiplier。

因此 VMFPU 外层实例化四份，而每份内部没有动态 SEW 大 mux。

### 7.2 弹性流水

`NumPipeRegs` 决定插入多少寄存器。operand、opcode、mask、valid 全部同拍前进。

```systemverilog
stage_ready[i] = stage_ready[i+1] | ~valid_q[i];
```

含义是：下一阶段能接收，或者当前阶段只是 bubble，本阶段就可更新。ready 从输出反向传播，valid/data 从输入正向传播，这是标准 elastic pipeline。

### 7.3 有符号选择

`signed_a/signed_b` 根据 opcode 决定是否扩展符号位：

- `VMULH`：双方有符号。
- `VMULHU`：双方无符号。
- `VMULHSU`：一方有符号、一方无符号。
- `VSMUL`：双方有符号。

将额外符号位拼到 operand 前再 `$signed` 相乘，可用一套表达式覆盖所有组合。

### 7.4 product 选择

- `VMUL` 取 product 低 SEW。
- `VMULH*` 取 product 高 SEW。
- `VMACC/VMADD` 将低半 product 与 `operand_c` 相加。
- `VNMSAC/VNMSUB` 将 product 取负后与 C 相加。

operand A/B/C 的架构含义由上层为不同 opcode 调整。

### 7.5 `VSMUL` 舍入与饱和

`VSMUL` 取定点乘积的中间高位，并根据 `vxrm` 产生 rounding bit。若最高正数乘法发生特殊溢出，`vxsat_o` 标记 saturation。各 SEW 分支公式相同，只是切片宽度和并行元素数不同。

### 7.6 mask 传递

乘法器不在内部丢弃结果，而把 `mask_i` 与 data 同步穿过流水成为 `mask_o`。VMFPU 在 result queue/writeback 处使用它，保证多拍延迟后仍与正确元素对齐。

## 8. `simd_div`：共享串行除法器的 SIMD 包装

### 8.1 为什么需要双 FSM

一套 `serdiv` 每次只能处理一个标量元素。一个 64-bit word 包含多个 EW8/16/32 元素，因此模块分为：

- issue FSM：逐元素送入 divider 或跳过 inactive 元素。
- commit FSM：按顺序接收结果并拼回 64-bit word。

两个 FSM 可在 divider 支持的范围内重叠输入准备和输出收集。

### 8.2 输入寄存器与计数器

握手接收一个完整 64-bit packet 后锁存 A/B、SEW、opcode、byte enable 和 mask。计数器初值由 SEW 决定：EW8 处理 8 项，EW16 处理 4 项，EW32 处理 2 项，EW64 处理 1 项。

### 8.3 issue FSM

典型状态含义：

- `ISSUE_IDLE`：等待新 packet。
- `ISSUE_DIV`：当前元素 active，等待 `serdiv_in_ready` 后发射。
- `ISSUE_SKIP`：当前元素被 mask/tail 禁用，不占用 divider。

每发射或 skip 一个元素，issue counter 递减并选择下一个切片。

### 8.4 commit FSM

- active 元素等待 `serdiv_out_valid`。
- skipped 元素直接向结果 buffer 插入 0 占位并移动位置。
- 收齐一个 packet 后拉高 `valid_o`，等待下游 `ready_i`。

mask 和 byte enable 保证最终无效位置不会真正写 VRF，因此 skip 插入值本身不影响架构状态。

### 8.5 opcode 映射

Ara opcode 映射到 `serdiv_opcode`：

| Ara | serdiv code |
|---|---|
| `VDIVU` | `00` |
| `VDIV` | `01` |
| `VREMU` | `10` |
| `VREM` | `11` |

### 8.6 operand 提取与扩展

动态计数器从 packed union 选出当前 byte/halfword/word。signed `VDIV/VREM` 做符号扩展，unsigned 操作补零，再统一送入 64-bit `serdiv`。

### 8.7 输出重组

每收到一个 scalar result，旧 `result_q` 左移 SEW 位并 OR 新低位结果。经过固定次数后恢复为一个 64-bit SIMD packet。`commit_cnt_en` 只在真实接收或 skip 时更新 buffer。

### 8.8 sequential block

最后一个 `always_ff` 集中保存双 FSM、operand、mask、result 和计数器。复位给 opcode/SEW 合法默认值，避免 X 扩散。

## 9. `fpnew_top`：外部浮点库的顶层路由器

### 9.1 与 Ara 的边界

`fpnew_top` 位于 `hardware/deps/fpnew`，不属于 Ara 自有实现。Ara 的 `vmfpu` 负责 RVV opcode/operand/layout，fpnew 负责 IEEE 浮点运算。

### 9.2 参数

- `Features`：总宽度、支持的 FP/INT format、vector/Nan-box 能力。
- `Implementation`：各 operation group 的 pipeline register 和 unit 类型。
- `DivSqrtSel`：选择除法平方根实现。
- `TagType`：随 transaction 透明传递的 metadata 类型。
- `EnableSIMDMask`：是否让 inactive SIMD lane 不执行、不报异常。

### 9.3 output struct

`output_t` 将 `result/status/tag` 打包。每个 operation group 输出一份 `output_t`，最后统一仲裁。这避免三组平行数组在 arbiter 端口中散开。

### 9.4 input ready

`get_opgroup(op_i)` 把 operation 分类到：

- `ADDMUL`
- `DIVSQRT`
- `NONCOMP`
- `CONV`
- `DOTP`

输入 ready 只查看目标 group。源码将 `in_valid_i` 也并入 `in_ready_o`，所以这里的 ready 更接近“本拍发生可接受请求”的 qualification；接入时应严格遵循该模块既有 valid/ready约定。

### 9.5 NaN-box 检查

对窄于总 WIDTH 的 scalar FP operand，高位应全 1。generate loop 为每个 format、每个 operand 生成检查。vector mode 不使用 scalar NaN-box，直接视为 boxed。

只有 `Features.EnableNanBox && FP_WIDTH < WIDTH` 时才生成比较器，否则常量置 1。

### 9.6 SIMD mask

```systemverilog
simd_mask = simd_mask_i | ~{NumLanes{EnableSIMDMask}};
```

当 mask 功能关闭时，右项全 1，使所有 lane active；开启时保留输入 mask。这是一种用常量参数在综合时裁掉功能的写法。

### 9.7 operation group generate

`for (genvar opgrp...)` 为每个 operation group 实例化 `fpnew_opgroup_block`。每组根据配置选择：

- 支持哪些 format。
- format unit 是 parallel、merged 还是 disabled。
- pipeline register 数和位置。
- 需要 2 个还是 3 个 operand。

`in_valid` 只对 opcode 所属 group 拉高，因此只有一个 group 接收当前 transaction。

### 9.8 `fpnew_opgroup_block` 下层

继续向下追时：

- `fpnew_opgroup_block.sv`：按 format 分片或共享单元。
- `fpnew_opgroup_fmt_slice.sv`：实例化具体 arithmetic slice。
- `fpnew_fma*.sv`：add/mul/FMA。
- `fpnew_divsqrt*.sv`：div/sqrt。
- `fpnew_noncomp.sv`：sign inject、min/max、compare、classify。
- `fpnew_cast_multi.sv`：浮点/整数和宽度转换。

### 9.9 输出 round-robin arbiter

不同 group latency 不同，可能同时产生结果。`rr_arb_tree` 在 `opgrp_out_valid` 间仲裁，并把下游 `out_ready_i` 只反馈给获胜 group。

`AxiVldRdy=1` 表示 arbiter 遵循 decoupled valid/ready，payload 在阻塞时保持。最终 unpack 到 `result_o/status_o/tag_o`。

### 9.10 busy

`busy_o = |opgrp_busy`，只要任一 group 内仍有 transaction 就为 1。Ara 当前主要依赖显式 valid/ready 和自己的计数器，而非用 busy 判断单条指令完成。

## 10. `sldu`：全 lane slide、重排与归约交换控制器

### 10.1 模块职责

SLDU 是全局单元，一次看到所有 lane 的 64-bit 数据。它负责：

- `vslideup/vslidedown/vslide1up/vslide1down`。
- source/destination EEW 不同导致的 byte reshuffle。
- 非 2 次幂 stride 的多轮分解。
- unordered reduction 的跨 lane 对数树。
- ordered FP sum 的顺序 accumulator 搬运。

### 10.2 instruction queue 与 result queue

SLDU 有自己的 instruction queue，因为它与 lane VFU 并行接收主 sequencer broadcast。result queue 每个 entry 包含 `NrLanes` 份 payload/valid，使一拍可向多个 lane 发起写回。

对于普通 slide，result queue 最终写 VRF；对于 reduction，result queue 作为返回各 lane ALU/MFPU 的传输 buffer，不写 VRF。

### 10.3 mask spill/queue

普通 masked slide 也从 MASKU 接收 per-lane byte strobe。mask 信号经过 spill/queue 后，与被 slide 的数据 beat 对齐。

归约不使用 predicate strobe 在 SLDU 内过滤，因为 inactive 元素已经在 lane 内 VFU/operand queue 变成中性值。

### 10.4 `p2_stride_gen`

硬件 datapath 擅长 2 次幂 stride。`p2_stride_gen` 将一般 stride 分解成多个 2 次幂步骤，并用 popcount/valid 指示是否到最后一步。

例如 stride 6 可视为 4+2，通过内部临时 buffer 做两轮置换。

### 10.5 reduction mux selection

`sldu_mux_sel_o` 告诉每个 lane 的共享 SLDU/ADDRGEN stream mux 当前应选择：

- `NO_RED`
- `ALU_RED`
- `MFPU_RED`

lane 内 [`lane.sv`](../src/lane/lane.sv) 用 FIFO 保持 SLDU、ADDRGEN、ALU reduction 和 FPU reduction 对共享总线的指令顺序。

### 10.6 `sldu_op_dp` 实例

组合 datapath 输入：所有 lane 的 word、slide amount、source EEW、destination EEW 和方向；输出仍是所有 lane 的 word。

控制器负责决定“本拍该做哪一种置换”，`sldu_op_dp` 只完成固定映射。

### 10.7 主状态机

主要状态：

- `SLIDE_IDLE`：等待/初始化新指令。
- `SLIDE_RUN`：普通 2 次幂 slide 或归约树步骤。
- `SLIDE_RUN_VSLIDE1UP_FIRST_WORD`：插入 scalar 的首拍特例。
- `SLIDE_RUN_OSUM`：ordered sum accumulator 搬运。
- `SLIDE_WAIT_OSUM`：等待最后处理完成。
- `SLIDE_NP2_SETUP/RUN/COMMIT/WAIT`：非 2 次幂 stride 多轮流程。

### 10.8 IDLE 初始化

收到新 issue 指令后，根据 opcode 初始化：

- `in_pnt/out_pnt`：当前 packet 内读写 byte offset。
- `vrf_pnt`：目标 VRF word 地址偏移。
- `issue_cnt/commit_cnt`：剩余 byte/element。
- `output_limit`：允许写回的最后位置。
- slide direction 和 stride。

`vslideup` 从 source 起点读、从目标 offset 写；`vslidedown` 从 source offset 读、从目标起点写。

### 10.9 普通 `SLIDE_RUN`

当所有 lane input valid、result queue 有空间、需要的 mask 已到达时：

1. 计算本拍 input/output 剩余 byte 数。
2. 构造 sequential `out_en_seq`。
3. 用 `shuffle_index` 转成 VRF physical layout 的 `out_en_flat`。
4. 与 predicate mask 合并得到每 lane `be`。
5. 将 `sldu_op_dp` 输出中 enabled byte 写 result entry。
6. 更新 input/output pointer、issue count 和 VRF 地址。

这里体现了“数据置换”和“架构有效元素控制”分离：datapath 可产生整拍数据，byte enable 决定哪些 byte 真正提交。

### 10.10 scalar slide 特例

`vslide1up` 的第一个元素来自 scalar，不来自 lane operand。专门状态在正确 lane/byte offset 插入 scalar 并设置 byte enable。

`vslide1down` 的最后元素类似，由状态机在最后 packet 修补。

### 10.11 unordered reduction tree

SLDU 将各 lane partial result 当作 EW64 传输单元。每轮设置不同的 `red_stride_cnt`，通过 `sldu_op_dp` 将需要合并的 partial 移到目标 lane。

每轮约一半 lane 真正合并，其他 lane 只握手。经过 `log2(NrLanes)` 轮，最终 partial 送 lane 0，再由 VALU/VMFPU 做 word 内 SIMD reduction。

### 10.12 ordered reduction

`SLIDE_RUN_OSUM` 每拍查找唯一 valid lane，将 accumulator 发给下一 lane；最后一次强制发回 lane 0。这里不使用树，因为树会改变浮点加法顺序。

### 10.13 非 2 次幂 slide

NP2 流程使用 result queue 中的专用 buffer entry：

1. `SETUP` 等待完整 input packet。
2. `RUN` 执行当前 2 次幂子 stride。
3. 若仍有子 stride，将结果循环回输入。
4. 最后一轮进入 `COMMIT`，应用最终 byte enable 并写 VRF。

### 10.14 写回和 reduction 返回

每 lane 输出分为：

- `sldu_result_req_o`：普通 slide，目标是 VRF。
- `sldu_red_valid_o`：归约，目标是 lane 内 VALU/VMFPU。

两者复用相同 payload。所有 lane 接收后才能推进 result queue pointer，避免不同 lane 的 packet 失配。

### 10.15 接受与完成

SLDU 只接受自己目标的 slide 指令，以及 target VFU 包含 SLDU 的 reduction。完成条件同时考虑：

- issue 全部结束。
- result queue 被接受。
- 普通写回已收到 final grant。
- reduction 的 lane VFU 已完成同步。

## 11. `sldu_op_dp`：展开后的 byte permutation 网络

### 11.1 为什么文件有约 1.7 万行

该文件为 1/2/4/8/16 lane、source/destination EEW、允许的 2 次幂 slide amount、方向预先展开所有 byte 映射。它本质是自动生成的组合 mux truth table，不是 1.7 万行顺序执行的软件。

### 11.2 flatten/unflatten

```systemverilog
assign op_i_flat = op_i;
assign op_o      = op_o_flat;
```

packed array 可直接赋给同总位宽的 flat vector。之后所有映射统一按 bit offset 表达，避免同时计算 lane index 和 byte offset。

### 11.3 lane 数 generate 分支

```systemverilog
if (NrLanes == 1) ...
else if (NrLanes == 2) ...
...
else $error(...);
```

只有配置对应的一大段 case 会被 elaboration；其他数万行不会进入综合网表。当前支持 lane 数必须为 1/2/4/8/16。

### 11.4 case key

```systemverilog
unique case ({eew_src_i, eew_dst_i, slamt_i, dir_i})
```

把四个控制字段拼成一个译码 key：

- `eew_src_i`：输入 physical layout。
- `eew_dst_i`：输出 layout。
- `slamt_i`：本轮 slide amount。
- `dir_i`：up/down。

`slamt=0` 且 EEW 不同主要做 reshuffle；EEW 相同且 `slamt!=0` 主要做 slide。模块注释明确：不能在同一拍同时做任意 reshuffle 和 slide，因此控制器需要拆分复杂操作。

### 11.5 indexed part-select

```systemverilog
op_o_flat[dst +: 8] = op_i_flat[src +: 8];
```

每条语句描述一个 byte mux 连接。组合 case 的所有语句共同定义该配置下的完整 permutation。

### 11.6 映射如何理解

VRF 数据在 lane 间按 `shuffle_index(element byte, NrLanes, EEW)` 分布。生成器对每个逻辑 byte：

1. 根据 source EEW 求 physical source byte。
2. 根据 slide direction/amount 求逻辑目标 element。
3. 根据 destination EEW 求 physical destination byte。
4. 输出一条固定 8-bit 连接。

因此看具体 case 时不要从连续 bit 位猜元素顺序，应先画逻辑 element index，再套 shuffle 映射。

### 11.7 default 分支

每个 lane 数分支最后 `default: op_o_flat = op_i_flat`。未列出的组合保持原数据，用于安全默认和某些无需置换的情况；合法控制组合应由 `sldu` 保证落入预期 case。

### 11.8 综合结果

尽管源码巨大，综合结果主要是每个输出 byte 前的多路器网络。展开写法让综合器直接看到常量连接，避免复杂动态除法/模运算和跨 lane 索引逻辑。

## 12. `masku_operands`：MASKU 输入整理、重排和压缩

### 12.1 输入通道布局

每个 lane 向 MASKU 提供：

```text
index 0: MaskM，即 v0 mask operand
index 1: MaskB，即旧 vd 或 gather 数据
index 2: VALU result
index 3: VMFPU result
```

`masku_fu_i` 在 ALU/FPU result 中选择当前需要的来源。

### 12.2 shuffled 与 sequential 视图

VRF 中元素按 lane 和 SEW shuffle。模块同时输出：

- `*_o`：保持 lane-local shuffled 形式。
- `*_seq_o`：按逻辑元素顺序 deshuffle 后的大向量。

MASK bit 操作、popcount、iota 等需要 sequential 视图；最终写 VRF 时还要重新 shuffle。

### 12.3 deshuffle 组合块

对每个 sequential byte 调用 `deshuffle_index`，求它在拼接 lane payload 中的 physical byte，然后复制到对应输出位置。ALU、旧 vd 和 mask 可能具有不同 EEW，因此分别计算索引。

### 12.4 vd/mask spill registers

每 lane 的旧 `vd` 和 `MaskM` 经过独立 spill register。原因是 MASKU 内部可能分多拍消费同一个大 packet，若直接反压 operand queue 会形成长路径。

ready 由 shuffled consumer 和 sequential consumer 的 ready OR 得到；设计假设同一时刻只有选定路径真正消费。

### 12.5 valid 分发

spill output valid 同时送到 shuffled 与 sequential 接口。ALU/FPU result 不另加 spill，因为上游 VALU/VMFPU 自带 result queue；其 valid 直接从选定 FU 通道取。

### 12.6 bit-enable 生成

`bit_enable_shuffle_eew` 决定目标 byte layout。模块先构造 `vl` 范围 mask，再根据 `shuffle_index` 映射成 physical byte enable。

若 `vm=0`，再与 `v0` bit 合并。`VMADC/VMSBC` 是例外：它们把 v0 当 carry/borrow source，而不是 predicate，因此不能在这里先过滤结果。

### 12.7 比较结果压缩

VALU/VMFPU 为每个 SEW 元素返回一个包含 comparison bit 的完整元素。模块遍历 physical byte，只在每个元素起始位置抽取该 bit，写入连续的 `alu_result_compressed_seq_o`。

这一步完成：

```text
64-bit SIMD comparison result
  -> 每元素 1 bit
  -> sequential mask bit vector
```

### 12.8 ready 回传

最终组合块清零全部 `masku_operand_ready_o`，再只对当前选中的 FU、MaskB、MaskM 通道回传 ready，防止同时错误消费另一 FU 的结果。

## 13. `masku`：集中式 mask 与 bit-level 执行单元

### 13.1 为什么 MASKU 是全局单元

mask vector 在 VRF 中仍按 byte/SEW layout 分布，并非简单 EW1 连续存储。许多操作需要跨 lane 观察连续 bit，因此 Ara 使用一个连接所有 lane 的集中式 MASKU：

- 产生普通 masked 指令的 per-lane byte strobe。
- 执行 bit-level mask 指令。
- 压缩 ALU/FPU comparison result。
- 处理 old-vd/tail/mask undisturbed。
- 返回 mask vector、普通 vector 或 scalar。

### 13.2 顶层计数器和 pointer

- `mask_pnt`：当前从输入 mask packet 读取到哪个 bit。
- `vrf_pnt`：当前写到目标 vector 的哪个位置。
- `read_cnt`：尚未读取的 mask/predicate 元素。
- `issue_cnt`：尚未执行的元素。
- `processing_cnt`：尚未形成 result queue 的元素。
- `commit_cnt`：尚未最终写回的元素。

这些计数分离是因为 VIOTA、mask logical、gather 的输入 bit 数、输出元素宽度和写回 packet 边界不同，无法用一个 counter 表示所有阶段。

### 13.3 `masku_operands` 实例

该实例完成 FU 选择、spill、shuffle/deshuffle、bit enable 和 comparison compression。`masku` 主体因此主要按 sequential bit vector 编写算法，而不用在每种指令中重复 lane 位置计算。

### 13.4 并行度参数

- `VmLogicalParallelism = NrLanes*64`：mask logical 一次处理完整输入 packet。
- `VmsxfParallelism`：`vmsbf/vmsif/vmsof` 每拍扫描部分 bit。
- `ViotaParallelism`：每拍并行计算若干 prefix count。
- `VcpopParallelism/VfirstParallelism = 16`：popcount/first 分片处理。
- `VrgatherParallelism = 1`：当前 gather 实现一次处理一个 index，简单但吞吐有限。

### 13.5 instruction queue 限制

`MaskuInsnQueueDepth=1`，MASKU 同时只处理一条 mask 相关指令。原因是 mask strobe 广播没有携带 instruction tag；若 ALU 和 MFPU 同时执行不同 masked 指令，接收方无法区分 strobe 属于谁。

### 13.6 mask queue

每个 mask queue entry 保存所有 lane 的 8-bit byte strobe，并有 per-lane valid。不同 lane 可在不同拍接受，但 entry 只有在所有目标都确认后才整体释放。

它服务普通 `vm=0` 指令，不是 mask 指令结果 FIFO。

### 13.7 result queue

result queue 每 entry 保存每 lane 的 `id/addr/wdata/be`，用于 mask 指令写回。`result_final_gnt` 区分：

- operand requester 已接受 write request。
- VRF bank 实际完成最终写入。

只有需要的 final grant 全部回来，指令才能标记 done，避免 scoreboard 过早释放目标寄存器。

### 13.8 gather 两级 FIFO

MASKU 为 `vrgather/vcompress` 维护：

- index FIFO：保存输出顺序、越界信息、compress 结束标记。
- request FIFO：保存要发给每个 lane `MaskB` requester 的 `{idx,eew,vs,last}`。

越界 gather index 不必真的读 VRF，只在 index FIFO 记录并最终写 0。

### 13.9 `vcpop` 与 `vfirst` 子模块

- `popcount` 每拍统计当前 16-bit slice 的 1 数，累加到 `popcount_q`。
- `lzc` 以 trailing/leading 配置查找当前 slice 第一个 1；`vfirst_count_q` 累加此前空 slice 长度。

`vfirst` 一旦找到 1 可提前终止，不必扫描剩余 vector。若始终为空，scalar result 返回 -1。

### 13.10 Mask ALU 默认值

Mask ALU 多数中间结果默认 `'1`，因为 mask tail-agnostic 允许 tail 写 1，而且后续常用 AND 将需要更新的位置清成计算结果。默认赋全 1也避免未覆盖 bit 被意外清零。

### 13.11 mask logical

`VMAND...VMXNOR` 已由 `simd_alu` 完成 64-bit 按位逻辑。MASKU 直接接收 `masku_operand_alu_seq`，负责 sequential/layout 转换和写回。

### 13.12 integer/FP comparison

`VMFEQ...VMSGT` 使用 `alu_result_compressed_seq`。MASKU 再结合：

- predicate mask `v0`
- 旧 `vd`
- tail policy

形成最终 mask vector。masked-out bit 可从旧 `vd` 保留或按 agnostic policy 设置。

### 13.13 `VMADC/VMSBC`

carry/borrow bit 已由 `simd_alu` 计算并压缩。由于 v0 是真正 source，而不是 predicate：

- `masku_operands` 不用 v0 过滤结果。
- mask queue 将 v0 strobe 送 ALU 作为 carry/borrow-in。
- MASKU 写回完整输出 mask。

### 13.14 `VMSBF/VMSIF/VMSOF`

模块用 `found_one_q` 跨 slice 记录此前是否见过 1。当前 slice 内 `vmsbf_buffer` 形成前缀状态：

- `vmsbf`：第一个 1 之前为 1。
- `vmsif`：第一个 1 及之前为 1。
- `vmsof`：只有第一个 1 位置为 1。

`VmsxfParallelism` 控制每拍组合前缀链长度，在面积/频率与吞吐间折中。

### 13.15 `VIOTA` 与 `VID`

两者复用 prefix-sum 数据通路：

- `VIOTA` 输入为 source mask bit，输出当前元素之前的 1 数。
- `VID` 将隐式输入视为全 1，因此输出 element index。

`viota_acc_q` 保存之前 slice 的累计值，`viota_res[]` 是本拍并行前缀结果。输出按当前 SEW 扩展成普通 vector 元素，并单独生成 byte enable。

注意 predicate 对二者影响不同：VIOTA masked-off source 不参与计数；VID 的 index 计数不被 predicate 改变，只影响是否写目标元素。

### 13.16 `VRGATHER/VRGATHEREI16`

预处理阶段从 ALU channel 得到 index：

- `VRGATHER` 按 SEW 解释 index，但硬件最多保存 16 bit，并检查高位 overflow。
- `VRGATHEREI16` 固定取 16-bit index。
- scalar gather 使用 `scalar_op`。

MASKU 计算 VLMAX 判断越界。合法 index 通过 request FIFO 向所有 lane 发 ad-hoc MaskB request；返回的 balanced payload 中只抽取目标元素。越界直接产生 0。

### 13.17 `VCOMPRESS`

source mask bit 为 1 时：

1. 当前 source element index push 到两个 FIFO。
2. `vcompress_cnt` 记录实际输出元素数。
3. MaskB 读取 source vector 元素。
4. 结果按紧凑连续 index 写入目标。

因为输出元素数小于等于 `vl`，结束条件和 commit count 有专门的 `vcompress_issue_end` 处理。

### 13.18 结果重新 shuffle

Mask ALU 主要产生 sequential `alu_result_vm_m`。随后循环调用 `shuffle_index`，把每个 byte 放回目标 SEW 对应的 physical lane layout。

VIOTA/VID/gather/compress 还要对 byte enable 做同样 shuffle。

### 13.19 old-vd 与 undisturbed policy

MaskB queue 可读取旧 `vd`。`background_data_init_seq` 将旧 vd、predicate 和 tail 默认值组合为 result queue 背景，Mask ALU 只覆盖 active bit。

这是实现 mask-undisturbed/tail-undisturbed 的核心：不能只依赖 byte enable，因为 mask vector 的单个 bit 与 VRF byte 并非一一对应。

### 13.20 普通 predicated execution

对于在 VALU/VMFPU/VLSU/SLDU 执行的普通 `vm=0` 指令，MASKU：

1. 从各 lane `MaskM` 取得 v0 packet。
2. 根据 instruction SEW 和 `mask_pnt` 找出每个逻辑元素的 mask bit。
3. 将一个 mask bit复制为该元素所有 byte 的 strobe。
4. 写入 mask queue。
5. 广播到目标 VFU。

`mask_valid_lane_o` 和各单元 ready 确保只有真正执行该指令的单元消费 strobe。

### 13.21 native MASKU execution 条件

MASKU ALU 只有在以下资源都满足时处理一个 slice：

- result queue 有空间。
- 所需 ALU/FPU result valid。
- 需要旧 vd 时 MaskB valid。
- 需要 predicate/source mask 时 MaskM valid。
- gather 时 index FIFO 非空。

一次 slice 完成后分别推进 input、mask input、output counter；只有对应 packet 的所有 slice 用完才对 operand 拉 ready。

### 13.22 scalar result

`VCPOP/VFIRST` 不写 VRF，而通过 `result_scalar_o/valid_o` 返回主 sequencer。结果有效时 issue/processing/commit count 一次清零，下一拍清 accumulator。

### 13.23 VRF commit

对每 lane 发 `masku_result_req_o`。普通 grant 后清当前 per-lane valid；当所有 lane request 被接受且 final grant 条件满足时推进 result queue。

不同操作按不同粒度扣 `commit_cnt`：mask-to-mask 按 bit 数，VIOTA/gather 按 SEW element 数，compress 按实际输出数。

### 13.24 接受新指令与阈值初始化

新指令只在 queue 不满、ID 未重复，且它本身需要 MASKU 时接受。按 opcode 初始化：

- `delta_elm`：每拍逻辑处理元素数。
- `in_ready_threshold`：一个 ALU packet 需要被分几拍消费。
- `in_m_ready_threshold`：一个 mask packet 的消费拍数。
- `out_valid_threshold`：何时凑满一个输出 word。

这组三个阈值是理解 MASKU time-multiplex 的关键。

## 14. 四条指令的端到端追踪

### 14.1 `vadd.vv`

```text
dispatcher: op=VADD, vfu=ALU
lane_sequencer: 请求 AluA(vs1)、AluB(vs2)，若 vm=0 再请求 MaskM(v0)
operand queues: 输出两个 64-bit SIMD packet
masku: vm=0 时产生 per-byte strobe
valu: NO_REDUCTION 发射
simd_alu: 按 SEW 并行加法
valu result queue
operand_requester: 仲裁写 VRF
```

### 14.2 `vredsum.vs`

```text
dispatcher: 设置归约中性值/转换信息
sequencer: target = ALU + SLDU
lane 0 AluA: vs1[0]；其他 lane AluA: 中性值
AluB: 各 lane 的 vs2 元素
valu: lane 内累加
lane stream mux: ALU partial -> SLDU
sldu: 对数树交换
valu lane 0: 最终 word 内 SIMD fold
只写 vd[0]
```

### 14.3 `vmseq.vv`

```text
dispatcher/sequencer: target = ALU + MASKU
lane_sequencer: AluA/AluB 请求普通向量；MaskB 请求旧 vd；必要时 MaskM 请求 v0
simd_alu: 每元素比较并编码 comparison bit
valu result queue: mask=1，送 MASKU
masku_operands: 抽取每元素 1 bit、deshuffle
masku: 合并 predicate/old-vd/tail，重新 shuffle
masku result queue -> VRF
```

### 14.4 `vfredosum.vs`

```text
dispatcher: op=VFREDOSUM
sequencer: target = MFPU + SLDU
vmfpu: OSUM_REDUCTION，使用 fpnew ADD
sldu: accumulator 按元素架构顺序在 lane 间移动
vmfpu: 每次只将下一个元素加入 accumulator
最终 accumulator 回 lane 0
vmfpu result queue -> vd[0]
```

### 14.5 `vnclip.wv`：为什么一个目标 word 要等两个源 beat

```text
第 1 个宽源 beat 到达
  -> 按 vxrm 舍入、右移、饱和到半宽
  -> 只写 result queue 当前槽的一半
  -> 保存 narrowing phase，不发布 valid

第 2 个宽源 beat 到达
  -> 生成另一半窄结果
  -> 与同一 queue 槽的半成品合并
  -> 此时才增加 result queue count
  -> MASK 与 byte enable 也在目标 word 完整时才共同前进
```

这里最容易犯的错误是把“源 beat 被消费”误当成“目标 beat 已产生”。观察波形时应看到源侧两次握手、结果队列一次入队。若第一拍就增加 queue count，写回端可能读到半个新结果和半个旧数据。

### 14.6 `vdiv.vv`（EW16）：一个 SIMD beat 如何串行执行

```text
LOAD: 锁存 4 个 16-bit dividend/divisor、BE、opcode 和 SEW
ISSUE_VALID/SKIP: 从 element 3 向 element 0 逐个检查并发送
WAIT_DONE: 已发送的元素等待 serial divider 返回
COMMIT_READY/SKIP: 返回值逐个左移拼入 64-bit result
COMMIT_DONE: 四个位置处理完后，才向 VMFPU 发布一个 beat
```

若 `be = 8'b1111_0011`，元素 3、2、0 进入 divider，元素 1 走 SKIP；issue 与 commit 两侧都要为 element 1 前进一步，才能保持四个元素的位置不漂移。外部输入从 LOAD 到整个 64-bit 结果被接收之前必须保持在内部寄存器中，因为输出拼接仍依赖被锁存的 `vew` 和 BE。

### 14.7 非 2 次幂 slide：同一数据为什么会回环

以距离可分解为两个 2 次幂分量的 slide 为例：

```text
外部 operands
  -> NP2_SETUP：确认内部 buffer 可用
  -> NP2_RUN：执行第一个 power-of-two 置换
  -> 内部 buffer 经 loop mux 回送
  -> NP2_RUN：执行第二个 power-of-two 置换
  -> NP2_COMMIT：把内部格式转换成可写回 payload
  -> NP2_WAIT：等待该 chunk 排空，再处理下一 chunk
```

因此 NP2 路径不是“普通 slide 多等一拍”，而是把 result queue 的固定槽临时当作中间 buffer。调试时要同时看剩余 stride、loop mux、内部两个固定指针和外部 queue valid；只看 VRF request 会误以为模块停住。

### 14.8 `vcompress.vm`：读取进度与目标写指针分离

```text
每个 source element 都被读取并检查 mask
mask=0：只推进 source index
mask=1：复制元素，同时推进 source index 和 destination index
目标 word 未填满：以 old-vd 作为 background 保留未写位置
最后一个输入处理完：排空 result queue 和 final grant 后完成
```

例如 8 个输入的 mask 为 `1010_0101`，source 进度最终增加 8，而 destination 只增加 4。任何用同一 counter 同时表示这两个事实的实现都会在稀疏 mask 下提前结束或写错地址。

## 15. 推荐学习顺序与波形观察点

### 15.1 阅读顺序

1. [`ara_pkg.sv`](../include/ara_pkg.sv)：`ara_op_e`、`vfu_e`、queue 编号和 shuffle helper。
2. [`vector_fus_stage.sv`](../src/lane/vector_fus_stage.sv)：VALU/VMFPU 如何接入 lane。
3. `simd_alu` -> `valu`：先理解组合计算，再理解控制。
4. `simd_mul/simd_div/fpnew_top` -> `vmfpu`。
5. `sldu_op_dp` 的生成规律 -> `sldu` 状态机。
6. `masku_operands` -> `masku`。
7. 回看 `lane_sequencer/operand_queue/operand_requester`，串起 operand 和写回。

### 15.2 建议首先跑的单元测试

测试位于 `apps/riscv-tests/isa/rv64uv`：

- `vadd` 类：确认普通 VALU 数据路。
- `vredsum.c`：确认整数归约状态。
- `vfredosum.c`：确认 ordered reduction。
- `vmseq.c`：确认 ALU + MASKU 分工。
- `vmsbf.c`：确认 MASKU prefix 状态。
- `viota.c`：确认 mask-to-vector layout。
- `vcompress.c`：确认 ad-hoc MaskB request。

### 15.3 关键波形信号

VALU：

```text
vinsn_issue_q.op, alu_state_q
alu_operand_valid_i, alu_operand_ready_o
valu_valid, valu_result
result_queue_valid_q, alu_result_req_o/gnt_i
alu_red_valid_o, sldu_alu_valid_q
```

VMFPU：

```text
mfpu_state_q
vmul/vdiv/vfpu_{in,out}_{valid,ready}
vinsn_issue_q, vinsn_processing_q
result_queue_valid_q
reduction_rx_cnt_q, osum_issue_cnt_q
```

SLDU：

```text
state_q, sld_slamt, sld_dir
sldu_operand_valid, sld_op_src, sld_op_dst
in_pnt_q, out_pnt_q, issue_cnt_q
red_stride_cnt_q, sldu_red_valid_o
```

MASKU：

```text
vinsn_issue.op
masku_operand_{alu,vd,m}_valid
mask_pnt_q, vrf_pnt_q
read_cnt_q, issue_cnt_q, processing_cnt_q, commit_cnt_q
mask_queue_valid_q, result_queue_valid_q
in_ready_cnt_q, in_m_ready_cnt_q, out_valid_cnt_q
found_one_q, viota_acc_q, popcount_q, vfirst_count_q
```

## 16. 阅读时容易混淆的几个概念

1. `vm=1` 表示不使用 predicate mask；不是“mask 全零”。
2. `MaskM` 是 v0 source/predicate 通道；`MaskB` 通常是旧 vd 或 gather 数据通道。
3. `vfu=VFU_MaskUnit` 不代表所有计算都在 MASKU。integer/FP comparison 和 mask logical 会先借用 VALU/VMFPU。
4. `be` 是每 byte 写使能；mask vector 的架构元素是 1 bit，二者不能直接等同。
5. `valid` 表示 payload 存在，只有 `valid && ready` 才算消费。
6. result queue grant 与 final grant 不同：前者是请求被仲裁器接收，后者是 VRF 实际完成。
7. unordered FP reduction 可以使用树；ordered sum 必须保持元素顺序。
8. `sldu_op_dp` 的巨大 case 是空间展开的组合网络，不是逐条执行的微码。

掌握这些边界后，再从一条具体指令沿 `dispatcher -> sequencer -> lane_sequencer -> operand queue -> VFU -> writeback` 追踪，会比孤立阅读单个大文件更有效。

## 17. 用代码理解 RTL 的统一方法

下面不再按源码行号索引，而是抽取每个模块中决定硬件行为的代码。代码中的 `...` 表示省略了同构的端口连接、其他 SEW 分支或重复赋值，不表示真实源码中存在省略号。

阅读每个代码块时始终回答五个问题：

1. 哪些信号是寄存器状态，哪些只是组合结果？
2. 默认赋值表达的是“保持”“无请求”还是“输出零”？
3. 哪个 `valid && ready` 才是真正发生的数据传输？
4. queue、pointer、counter 在一次传输后怎样守恒？
5. 这块逻辑最终综合成 MUX、加法器、比较器、寄存器还是仲裁器？

典型的 Ara 控制块可以抽象成：

```systemverilog
always_comb begin
  state_d = state_q;       // 默认保持寄存器
  req_o   = 1'b0;          // 默认不产生外部副作用
  ready_o = 1'b0;

  if (can_execute) begin
    req_o = 1'b1;
    if (req_o && gnt_i) begin
      state_d = NEXT_STATE;
      count_d = count_q - 1;
    end
  end
end

always_ff @(posedge clk_i or negedge rst_ni) begin
  if (!rst_ni) begin
    state_q <= IDLE;
    count_q <= '0;
  end else begin
    state_q <= state_d;
    count_q <= count_d;
  end
end
```

第一个过程生成 next-state 组合网络，第二个过程生成寄存器。`state_d = state_q` 不是“执行了一次复制”，而是 MUX 的默认反馈输入；只有后续条件覆盖它时，下一时钟沿才改变状态。

## 18. `valu`：整数执行控制的完整骨架

### 18.1 指令不是直接执行，而是先进入生命周期队列

核心结构可简化为：

```systemverilog
typedef struct packed {
  vfu_operation_t [VInsnQueueDepth-1:0] vinsn;
  queue_pnt_t accept_pnt, issue_pnt, commit_pnt;
  queue_cnt_t issue_cnt, commit_cnt;
} vinsn_queue_t;

assign vinsn_queue_full  = vinsn_queue_q.commit_cnt == VInsnQueueDepth;
assign vinsn_issue_valid = vinsn_queue_q.issue_cnt != '0;
assign vinsn_commit_valid = vinsn_queue_q.commit_cnt != '0;
```

一条指令会经历三个位置：

- `accept_pnt`：新指令写入的位置。
- `issue_pnt`：当前正在消费 operand beat 的指令。
- `commit_pnt`：当前正在把结果写回 VRF 的指令。

`issue_cnt` 和 `commit_cnt` 不重复。指令可以已经 issue 完，但结果仍在 result queue 中，因此它应从 issue 数量中消失，却仍在 commit 数量中存在。这个分离允许流水重叠，又保持指令顺序。

接收新指令时的本质操作是：

```systemverilog
if (vfu_operation_valid_i && vfu_operation_ready_o) begin
  vinsn_queue_d.vinsn[accept_pnt] = vfu_operation_i;
  vinsn_queue_d.accept_pnt++;
  vinsn_queue_d.issue_cnt++;
  vinsn_queue_d.commit_cnt++;
end
```

完整 RTL 还会在队列原为空时初始化 `issue_cnt`、`commit_cnt`、归约状态和 narrowing selector。教学上应记住：指令级 handshake 只登记工作，不代表 operand 或结果已经移动。

### 18.2 scalar replication 把所有指令统一成 SIMD-SIMD 运算

```systemverilog
always_comb begin
  scalar_operand = '0;
  case (vinsn_issue_q.vtype.vsew)
    EW8 : scalar_operand = {8{scalar_i[7:0]}};
    EW16: scalar_operand = {4{scalar_i[15:0]}};
    EW32: scalar_operand = {2{scalar_i[31:0]}};
    EW64: scalar_operand = scalar_i[63:0];
  endcase
end
```

这综合成一个由 SEW 控制的复制与选择网络。下游 ALU 不需要知道 operand 来自 `.vv`、`.vx` 还是 `.vi`；它总能按当前 SEW 把两个 64-bit word 看成相同数量的元素。

### 18.3 普通运算必须同时满足“输入齐”和“输出有空间”

普通执行分支可概括为：

```systemverilog
if (!result_queue_full && operands_valid) begin
  alu_valid = 1'b1;

  operand_ready_o[OpA] = 1'b1;
  operand_ready_o[OpB] = 1'b1;

  result_queue_d[write_pnt].data = alu_result;
  result_queue_d[write_pnt].be   = issue_be;
  result_queue_d[write_pnt].addr = result_addr;

  result_queue_write_pnt_d++;
  result_queue_cnt_d++;
end
```

这里有两个不能拆开的条件：

- operand 未全部 valid 时不能只消费其中一个，否则不同 beat 会错配。
- result queue 满时不能消费输入，否则组合结果无处保存。

因此 `operand_ready` 实际由“计算能否原子完成”反向控制。综合后，ready 信号会穿过 valid 检查、queue full 检查和 opcode 需要的 operand 集合。

### 18.4 narrowing 为什么需要两拍拼接

窄化指令每个源元素产生一半宽度的目标元素。一个 64-bit 源 beat 只能形成半个目标布局，因此控制逻辑类似：

```systemverilog
if (is_narrowing(op)) begin
  if (!narrowing_select_q) begin
    narrowing_result_d = alu_result;
    narrowing_select_d = 1'b1;
    // 不增加 result queue：结果还不完整
  end else begin
    result_queue_d[write_pnt].data =
      combine_narrow_halves(narrowing_result_q, alu_result);
    narrowing_select_d = 1'b0;
    result_queue_cnt_d++;
  end
end
```

关键点是第一拍可以消费源 operand，但不能声明一个完整输出；保存寄存器和 selector 共同描述“半成品”。mask operand 也必须与这两拍的目标元素正确对齐，不能每拍都无条件弹出。

### 18.5 reduction 把 ALU 变成带反馈的 accumulator

核心 operand MUX 可以抽象为：

```systemverilog
assign alu_operand_a = reduction_feedback
                     ? reduction_result_q
                     : operand_a;

assign alu_operand_b = reduction_from_sldu
                     ? sldu_operand
                     : first_op_q ? scalar_seed : operand_b;
```

第一次操作把 `vs1[0]` 的 scalar seed 与首组向量元素结合；后续操作把上一拍结果反馈成一个 operand。除 lane 0 外，其他 lane 使用操作单位元作为 seed，例如 sum 的 0、and 的全 1、min/max 对应的极值。否则 scalar 会被每个 lane 重复累计。

整数归约状态流为：

```text
INTRA_LANE_REDUCTION
  -> INTER_LANES_REDUCTION_TX
  -> INTER_LANES_REDUCTION_RX  （按树层重复）
  -> lane 0: SIMD_REDUCTION
  -> result queue -> VRF
```

`INTRA` 在每个 lane 内沿 beat 累计；`TX/RX` 借 SLDU 把 lane partial result 按二叉树合并；最后 lane 0 还要把一个 64-bit word 内的多个 SIMD 元素归并成 element 0。非零 lane 即使本地 `commit_cnt` 已经为零，也要等跨 lane 阶段同步结束，不能提前报告整条指令完成。

### 18.6 result queue 把执行和写回解耦

```systemverilog
alu_result_req_o.req   = result_queue_valid;
alu_result_req_o.wdata = result_queue_head.data;
alu_result_req_o.be    = result_queue_head.be;

if (alu_result_req_o.req && alu_result_gnt_i) begin
  result_queue_read_pnt_d++;
  result_queue_cnt_d--;
end
```

实际代码还区分送 VRF 和送 MASKU。比较结果、mask logical 等先由 VALU 计算，但最终架构目标是 mask vector，所以 payload 的 `mask` 标志会把它路由到 MASKU。这个结构解释了为什么“指令属于 MASKU”不等于“所有计算都在 MASKU 完成”。

### 18.7 三种进度不能混为一个 counter

VALU 同时存在指令级和元素级进度：

| 状态量 | 单位 | 回答的问题 |
|---|---:|---|
| queue `issue_cnt` | 指令 | 还有几条指令尚未发完 operand |
| queue `commit_cnt` | 指令 | 还有几条指令尚未完成写回 |
| `issue_cnt_q` | 元素 | 当前 issue 指令还剩几个元素未消费 |
| `commit_cnt_q` | 元素 | 当前 commit 指令还剩几个元素未写回 |

result payload 不只有数据，而是把写回所需语义一起冻结：

```systemverilog
payload.id    = vinsn_issue.id;
payload.addr  = vaddr(vd, NrLanes, VLEN)
              + ((vl - issue_cnt_q) >> (EW64 - vsew));
payload.wdata = alu_result;
payload.be    = issue_be;
payload.mask  = result_targets_masku;
```

地址式中的 `vl - issue_cnt_q` 是已消费的元素数，再按一个 VRF word 能容纳的元素数换算为 word 偏移。普通指令的 byte enable 是元素范围、predicate 和 opcode 语义的交集；`VMERGE/VADC/VSBC` 的 v0 是数据选择或 carry/borrow 输入，因此不能按普通 predicate 方式把 byte 清掉。

queue head 若 `mask=0`，由 VRF grant 消费；若 `mask=1`，由 MASKU grant 消费。消费一次后，`commit_cnt_q` 按该 payload 实际包含的元素数递减，而不是机械减一。

### 18.8 reduction 的完整状态与提交屏障

完整状态集合为：

```text
NO_REDUCTION
INTRA_LANE_REDUCTION
INTER_LANES_REDUCTION_RX
INTER_LANES_REDUCTION_TX
LN0_REDUCTION_COMMIT
SIMD_REDUCTION
```

`LN0_REDUCTION_COMMIT` 不是额外计算阶段，而是非零 lane 的收尾同步阶段：这些 lane 已把 partial result 交给归约树，不再产生架构写回，但仍不能比 lane 0 更早释放该指令。`prevent_commit` 就是这道提交屏障。

```systemverilog
if (vinsn_commit_valid && commit_cnt_d == 0 && !prevent_commit)
  retire_current_instruction();
```

这条条件是理解归约死锁和提前完成 bug 的核心。`vl=0` 或某 lane 本地没有元素时，元素 counter 可以一开始就是零；如果没有 `prevent_commit`，该 lane 会提前进入下一条指令，跨 lane 的 TX/RX 协议便失去共同上下文。

lane 0 收到最终 partial word 后进入 `SIMD_REDUCTION`，继续把 word 内多个元素折叠到 element 0。非零 lane 进入 `LN0_REDUCTION_COMMIT`，把本地 commit 进度归零并等同步结束。完成一段 partial fold 后还要清理/重装 accumulator 的 phase，不能让上一段反馈值污染下一段。

### 18.9 写回、完成和饱和标志的不变量

应始终成立：

1. result queue 中每个 valid 槽拥有完整的 `id/addr/wdata/be/mask`，不能从“当前 issue 指令”重新组合元数据。
2. 只有 VRF 或 MASKU 对 queue head 的真实握手才能弹槽。
3. 指令完成要求元素 commit counter 为零、结果已排空且没有 reduction 提交屏障。
4. `vxsat` 只统计真正写回的 active byte：等价于 `|(alu_vxsat_q & result_queue_head.be)`。masked-off 或 tail 元素即使组合逻辑算出溢出，也不能污染架构 `vxsat`。

验证时可故意让写回端 backpressure：若 queue head 的数据、BE、地址、mask 路由或饱和位发生变化，就说明 payload 没有被正确冻结。

## 19. `simd_alu` 与 `fixed_p_rounding`：整数数据通路

### 19.1 packed union 不复制数据，只提供元素视图

```systemverilog
typedef union packed {
  logic [0:0][63:0] w64;
  logic [1:0][31:0] w32;
  logic [3:0][15:0] w16;
  logic [7:0][ 7:0] w8;
} alu_operand_t;

alu_operand_t opa, opb, res;
assign opa = operand_a_i;
assign opb = operand_b_i;
```

三者都只有 64 bit。`opa.w8[3]` 和 `operand_a_i[31:24]` 是同一组线。union 让每个 SEW 分支使用自然的元素索引，不会综合成四份寄存器。

### 19.2 比较器如何同时支持 signed 和 unsigned

```systemverilog
assign is_signed = op_i inside {VMAX, VREDMAX, VMIN, VREDMIN,
                                VMSLT, VMSLE, VMSGT};

less[b] = $signed({is_signed & opb.w8[b][7], opb.w8[b]}) <
          $signed({is_signed & opa.w8[b][7], opa.w8[b]});
equal[b] = opa.w8[b] == opb.w8[b];
```

两个 operand 都扩成 9 bit：signed 操作复制符号位，unsigned 操作补 0，然后统一使用 signed comparator。注意该源码定义的是 `opb < opa`，后面的 min/max MUX 都建立在这个方向上。

比较 mask 不立即排列成连续 bit，而是写到每个元素的低位：

```systemverilog
res.w16[b][1:0] = {mask_i[2*b], equal[2*b]};
```

bit 0 是比较结果，bit 1 携带 predicate 元数据。MASKU 随后把每个元素的 bit 0 压缩成连续 mask vector。

### 19.3 carry/borrow 是扩展一位的加减法

```systemverilog
logic [8:0] sum;
sum = opa.w8[b] + opb.w8[b] +
      logic'(op_i inside {VADC, VMADC} && mask_i[b] && !vm_i);

res.w8[b] = op_i == VMADC
           ? {6'b0, 1'b1, sum[8]}
           : sum[7:0];
```

普通 `VADD/VADC` 取低 8 bit；`VMADC` 取扩展位，也就是 carry-out。减法同理使用 `opb - opa - borrow_in`，扩展位成为 borrow 信息。`VMADC/VMSBC` 中 v0 是算术输入，不是 predicate，因此 MASKU 不能再用它屏蔽结果。

### 19.4 signed saturation 的判断式

```systemverilog
sum = opa.w8[b] + opb.w8[b];
overflow = (sum[7] ^ opa.w8[b][7]) &
           ~(opa.w8[b][7] ^ opb.w8[b][7]);

res.w8[b] = overflow
           ? (sum[7] ? 8'h7f : 8'h80)
           : sum[7:0];
```

“输入同号、结果异号”说明 signed overflow。正数相加溢出后结果符号变成 1，应钳位最大正数；负数相加溢出后结果符号变成 0，应钳位最小负数。`vxsat` 对元素覆盖的每个 byte 复制同一个 overflow bit，便于最后与 byte enable 相与。

### 19.5 移位必须逐元素进行

```systemverilog
EW8 : res.w8[b]  = opb.w8[b]  << opa.w8[b][2:0];
EW16: res.w16[b] = opb.w16[b] << opa.w16[b][3:0];
EW32: res.w32[b] = opb.w32[b] << opa.w32[b][4:0];
EW64: res.w64[b] = opb.w64[b] << opa.w64[b][5:0];
```

只取 `log2(SEW)` 个 shift amount bit，实现 RVV 要求的 modulo SEW。算术右移要对每个元素单独 `$signed` 后使用 `>>>`；若把整个 64-bit word cast 成 signed，相邻元素之间会错误传播符号。

### 19.6 rounding 模块只计算“是否加一”

```systemverilog
j = shift_amount;
case (vxrm)
  2'b00: r[i] = value[j-1];
  2'b01: r[i] = value[j-1] & value[j];
  2'b10: r[i] = 1'b0;
  2'b11: r[i] = !value[j] & |discarded_bits;
endcase
```

`fixed_p_rounding` 不执行移位。它扫描将被丢弃的位，按 `vxrm` 生成每元素一个 bit 的增量 `r`；`simd_alu` 再完成：

```systemverilog
rounded = shifted_value + r[element];
```

`bit_select` 查找表中的 `0,1,3,7,...` 用于构造低 j 位全 1 的 sticky mask。动态位选会综合成 MUX，reduction OR 会综合成 OR tree。

### 19.7 clip 是“舍入移位 + 范围检查 + 钳位”

`VNCLIP/VNCLIPU` 的完整语义顺序不可交换：

```text
宽源元素
  -> 按 shift amount 右移
  -> 按 vxrm 加 rounding increment
  -> 检查是否能装入半宽目标
  -> 超范围则输出 min/max，并置 vxsat
```

如果先检查范围再舍入，边界值可能在加一后溢出却未被检测。

### 19.8 opcode 家族、operand 角色与输出

阅读 `simd_alu` 时不要逐条 mnemonic 孤立记忆，可以按数据通路归类：

| 家族 | 共享硬件 | 关键输出 |
|---|---|---|
| add/sub/carry/borrow | SEW+1 位加减器 | result 与 carry/borrow bit |
| and/or/xor | 逐 bit 逻辑 | 元素本身或 mask bit |
| sll/srl/sra | 每元素 barrel shifter | 移位结果、被丢弃 bits |
| min/max | signed/unsigned compare + MUX | A 或 B |
| average | 扩展加法 + rounding | `(A+B)/2` 类结果 |
| saturating add/sub | 扩展加法 + overflow detect + clamp | 饱和值与 `vxsat` |
| compare | compare network | 每元素一个布尔值 |
| merge/carry-mask | predicate/carry 选择 | 数据元素或 mask bit |
| clip | 宽移位 + rounding + range check | 半宽值与 `vxsat` |

源码中的 A/B 命名不应凭汇编书写顺序猜。例如比较表达式和减法器可能采用 `opb < opa`、`opb - opa` 的内部约定，因为上游已经按 datapath 端口排列了 `vs1/vs2/scalar`。判断一条指令是否正确，应沿着“sequencer 选哪个 operand queue → VALU 的 operand MUX → ALU 表达式”完整追踪，不能只看最后一行运算符。

comparison 与 `VMADC/VMSBC` 虽都产生 1 bit/element，语义不同：comparison 的 v0 通常是 predicate；carry/borrow-mask 指令的 v0 可以是算术输入。MASKU 后续压缩和写 mask register 时仍须保留这个区别。

### 19.9 `vxrm`、动态位选和一个 EW8 例子

`fixed_p_rounding` 不直接产生最终数值，只决定右移后是否 `+1`。四种 `vxrm` 可理解为：

| 模式 | 增量依据 |
|---|---|
| RNU | 被丢弃部分的最高位，ties 向上 |
| RNE | round bit 且（sticky 或保留结果最低位），ties-to-even |
| RDN | 永不增加，直接截断 |
| ROD | 若丢弃部分非零，则把保留结果最低位置 1 |

动态移位量决定 round bit 和 sticky 范围；移位量为零时根本没有被丢弃的 bit，增量必须为零。RTL 常通过查找表、动态 bit-select 和 reduction OR 实现，因此要特别检查索引边界，而不是把它当普通软件数组访问。

以 EW8 signed saturating add 为例，`8'h7f + 8'h01` 的扩展和超过 `+127`：数据输出钳为 `8'h7f`，该元素对应的 `vxsat` byte 置位。若此元素的 BE 为零，写回时 `vxsat & be` 将它过滤，架构饱和标志不变。对 `VNCLIP`，则先对宽源按上述规则舍入右移，再检查舍入后的值能否装入 8 bit；次序不能交换。

## 20. `vmfpu`：多种长延迟单元的统一调度

### 20.1 为什么比 VALU 多 processing 阶段

```systemverilog
typedef struct packed {
  ...
  queue_pnt_t accept_pnt;
  queue_pnt_t issue_pnt;
  queue_pnt_t processing_pnt;
  queue_pnt_t commit_pnt;
  queue_cnt_t issue_cnt;
  queue_cnt_t processing_cnt;
  queue_cnt_t commit_cnt;
} vinsn_queue_t;
```

VALU 是组合计算，输入一旦消费就能立即形成 queue payload。乘法、除法和 fpnew 有流水延迟，输入已 issue 后结果还在飞行，所以需要 `processing` 阶段标识当前返回结果属于哪条指令，并提供其 SEW、地址、舍入模式和 exception 归属。

### 20.2 opcode 先分类，再选择子单元

```systemverilog
assign vinsn_issue_mul = op inside {[VMUL:VSMUL]};
assign vinsn_issue_div = op inside {[VDIVU:VREM]};
assign vinsn_issue_fpu = op inside {[VFADD:VMFGE]};
```

分类信号控制三件事：哪个子单元获得 `valid`，外部 `ready` 来自哪一路，以及 result MUX 选择哪一路。区间匹配依赖 `ara_op_e` 的枚举顺序；扩展 opcode 时不能只修改 decoder，还要检查这些范围。

### 20.3 四个乘法器是 elaboration 后并存的硬件

```systemverilog
simd_mul #(.ElementWidth(EW8 )) i_mul_ew8  (...);
simd_mul #(.ElementWidth(EW16)) i_mul_ew16 (...);
simd_mul #(.ElementWidth(EW32)) i_mul_ew32 (...);
simd_mul #(.ElementWidth(EW64)) i_mul_ew64 (...);
```

`ElementWidth` 是参数，不是运行时信号，所以综合后是四套针对不同元素宽度优化的阵列。当前 `vsew` 只激活其中一套；clock/power gating 避免其他阵列无意义翻转。

### 20.4 不同延迟结果必须保持架构顺序

设前一条是慢除法，后一条是短流水 FP compare。如果后一条结果先写入共享 result queue，就会破坏 commit 顺序。`vmfpu` 根据 opcode 和 SEW 得到预计 latency，比较在途 processing 指令与待 issue 指令的完成关系，必要时停止后一条 issue。

这类 stall 的本质不是“计算资源忙”，而是“即使资源空闲，完成顺序也不安全”。调试时要区分子单元 `ready=0` 和 ordering control 主动压低 valid。

### 20.5 FP operand preprocessing 是指令语义适配层

fpnew 提供统一的 FMA、compare、convert 等 primitive，而 RVV 有许多 operand 排列和取反变体。预处理块完成：

```systemverilog
vfpu_operands[0] = operand_a;
vfpu_operands[1] = operand_b;
vfpu_operands[2] = operand_c;
vfpu_op           = fpnew_pkg::ADD;
vfpu_op_mod       = 1'b0;
vfpu_src_fmt      = selected_format;
vfpu_dst_fmt      = selected_format;
vfpu_rnd_mode     = fp_rm;
```

具体 opcode 分支会交换 A/B/C、翻转符号、改变 `op_mod` 或选择 conversion format。这样真正的 FP pipeline 不需要了解所有 RVV mnemonic。

### 20.6 FP exception 只在结果握手时累计

```systemverilog
fflags_ex_d       = vfpu_ex_flag;
fflags_ex_valid_d = vfpu_out_valid & vfpu_out_ready;
```

valid 在 backpressure 期间可能保持多个周期。如果每个 valid 周期都累计 flag，同一个结果会被重复记账。必须以 output handshake 作为“这份异常属于一次已消费结果”的事件。

### 20.7 unordered 与 ordered FP reduction 不能共用一种树

- unordered reduction 可在 lane 内并行，再经 SLDU 平衡树合并，追求吞吐。
- ordered sum 必须依次抽取架构元素，执行 `acc = fp_add(acc, next_element)`，保持规定顺序。

浮点加法不满足严格结合律，因此树形改变括号可能改变末位和 exception。`vmfpu` 为 ordered sum 保存 element issue count，并按 SEW 从 beat 中逐个抽取元素。

### 20.8 四个指令位置和三套元素进度

VMFPU 的 queue pointer 表示“哪条指令”，局部 counter 表示“该指令剩多少元素”：

| 阶段 | 指令位置 | 元素 counter | 含义 |
|---|---|---|---|
| accept | `accept_pnt` | — | 保存新指令描述符 |
| issue | `issue_pnt` | `issue_cnt_q` | operand 尚未送入子单元 |
| processing | `processing_pnt` | `to_process_cnt_q` | 已发射、结果尚未返回 |
| commit | `commit_pnt` | `commit_cnt_q` | 结果尚未完成写回 |

乘法器、divider 和 fpnew 的输出只带计算结果及有限 tag，不会重新输出完整 RVV 指令。因此 processing queue head 必须提供返回结果对应的 opcode、vd、SEW、ID、mask policy 和地址语义。若错误地用 issue head 解码返回结果，在连续发射不同指令时就会把前一条结果贴上后一条元数据。

### 20.9 latency ordering 的实际判断

核心判定可抽象为：

```systemverilog
latency_problem =
    issue_latency < processing_latency
 || ((issue_is_divsqrt || processing_is_divsqrt)
     && issue_id != processing_id);

latency_stall = issue_valid && processing_valid && latency_problem_q;
```

第一项防止较短的新操作越过较慢的老操作；第二项把可变延迟的 divide/sqrt 与不同 instruction ID 串行化，因为静态 latency 不能预测其精确完成周期。这里比较的是“若现在发射，是否可能乱序返回”，而非仅检查功能单元 busy。

排查 stall 时至少分三类：operand 尚未齐、目标子单元不 ready、ordering 主动阻塞。三者优化方向完全不同。

### 20.10 operand 重排必须与 ready 一起重排

RVV mnemonic 与 fpnew 的统一 A/B/C 接口不总同序。典型规则包括：

- `VFRDIV` 的 scalar 放到 operand A，以表达 `scalar / vector`；多数 `.vf` 算术把 scalar 放 B。
- fused multiply-add 家族通过 A/B/C 交换、符号修改和 `op_mod` 复用同一个 FMA primitive。
- 某些指令令 `vd` 同时是加数输入，`swap_vs2_vd_op` 会改变 `vs2` 与旧 `vd` 的数据位置。

最后一条尤其重要：交换数据同时必须交换对应的 ready 路径。否则数据看似正确接到 FPU，握手却弹出了另一条 operand queue，下一拍开始所有 operand 错位。检查重排代码时，应把 data MUX、valid 汇合和 ready demux 当作一个原子结构。

窄化转换还分别维护 `narrowing_select_in` 与 `narrowing_select_out`。输入端的 half phase 在 operand handshake 时推进；输出端的 phase 在若干周期后的 result handshake 时推进。长流水允许两者同时处在不同相位，用一个 selector 会在 backpressure 或连续窄化时把半字拼错。

### 20.11 reduction 状态、neutral filling 与 `MFPU_WAIT`

完整状态集合为：

```text
NO_REDUCTION
INTRA_LANE_REDUCTION
INTER_LANES_REDUCTION_TX
INTER_LANES_REDUCTION_RX
LN0_REDUCTION_COMMIT
SIMD_REDUCTION
OSUM_REDUCTION
MFPU_WAIT
```

unordered reduction 的 FP pipeline 有固定启动间隔，而反馈 accumulator 尚未返回。为了持续推进控制并保持 pipeline 对齐，`ntr_filling` 会暂时送入中性值；`intra_issued_op_cnt` 记录已发射操作，`first_result_op_valid` 标记反馈何时真正可用。它们共同避免“把尚不存在的反馈当 operand”或把同一 partial result 累加两次。

`red_hs_synch` 表示 reduction 数据是否已通过 SLDU 完成一次交接。它不是普通 valid 的别名，而是跨 lane 循环协议的 phase。lane 0 与其他 lane 会依据它进入 TX/RX、继续 ordered chain 或结束。

`MFPU_WAIT` 是指令切换屏障：lane 0 等最终 VRF grant；非零 lane 清理本地 commit；随后 issue/processing pointer 一起前进并初始化下一条指令的 reduction 状态。跳过这个状态会让下一条指令继承旧 accumulator、phase 或跨 lane handshake。

### 20.12 ordered sum 的抽取顺序为何看起来“不连续”

lane 内 64-bit 数据按 Ara 的 shuffled 布局存放，物理 bit 顺序不是架构元素顺序。`processed_osum_operand` 因而按以下物理位置恢复顺序：

```text
EW8 : byte 0, 4, 2, 6, 1, 5, 3, 7
EW16: halfword 0, 2, 1, 3
EW32: low word, high word
EW64: whole word
```

每次只抽取一个元素，与 accumulator 做一次 FP add；masked-off 元素替换成 neutral value。这个顺序不是一种运算优化，而是从 shuffled storage 恢复 RVV 规定的元素顺序。修改 lane shuffle 或 ordered reduction 时，这张映射必须同步验证。

## 21. `simd_mul` 与 `simd_div`：两种完全不同的长延迟结构

### 21.1 multiplier 的 elastic pipeline

```systemverilog
assign stage_ready[i] = stage_ready[i+1] | ~valid_q[i];

`FFL(valid_q[i], valid_d[i], stage_ready[i], '0)
`FFL(opa_q[i],   opa_d[i],   stage_ready[i], '0)
`FFL(opb_q[i],   opb_d[i],   stage_ready[i], '0)
```

某级能更新的条件是：下一级愿意接收，或者本级没有有效数据。payload 和 valid 使用同一个 enable，所以暂停时不会发生“valid 属于旧数据、operand 已换成新数据”的撕裂。

乘法首先多扩展一位再进行 signed multiply：

```systemverilog
product = $signed({opa.sign & signed_a, opa}) *
          $signed({opb.sign & signed_b, opb});
```

补 0 表示 unsigned，复制符号表示 signed。结果宽度是 2×SEW，`VMUL` 取低半，`VMULH*` 取高半，MAC 在低半上加 `operand_c`。

`VSMUL` 则取定点乘积右移 `SEW-1` 的结果并舍入。最小负数乘最小负数是特殊饱和边界，通过乘积顶位与输出符号不一致检测。

### 21.2 divider 为什么有 issue 和 commit 两个 FSM

一个 64-bit beat 在 EW8 时包含 8 个独立除法，但底层只有一个 serial divider。因此输入侧逐个发送元素，输出侧逐个收集元素：

```text
issue FSM : IDLE -> LOAD -> VALID/SKIP -> WAIT_DONE
commit FSM: IDLE -> READY/SKIP -> DONE
```

issue 侧关键逻辑：

```systemverilog
if (be_q[issue_cnt_q << vew_q]) begin
  serdiv_in_valid = 1'b1;
  if (serdiv_in_valid && serdiv_in_ready)
    issue_cnt_d = issue_cnt_q - 1;
end else begin
  issue_cnt_d = issue_cnt_q - 1; // inactive 元素不送 divider
end
```

`element_index << vew` 把元素编号变成元素首 byte 编号。被 mask/tail 禁用的元素走 SKIP，仍要占据最终结果布局中的位置。

输入元素按 SEW 做符号或零扩展：

```systemverilog
extended = signed_div
         ? {{(64-SEW){element[SEW-1]}}, element}
         : {{(64-SEW){1'b0}}, element};
```

输出侧每收一个结果就移位拼接：

```systemverilog
shifted_result = result_q << SEW;
result_d = shifted_result | zero_extended_serdiv_result;
```

因为 issue counter 按固定方向选择元素，连续“左移旧结果、低位插入新结果”最终恢复正确的 64-bit SIMD 排列。只有整个 beat 组装完成，模块才拉高外部 `valid_o`。

### 21.3 multiplier：吞吐、延迟与 opcode 矩阵

`NumPipeRegs` 决定寄存器级数和首结果延迟；流水填满后，只要输出每拍 ready，模块仍可每拍接收一个 64-bit packed operand。每一级必须一起保存 `opa/opb/opc/op/mask/valid`，并共用：

```systemverilog
stage_ready[i] = stage_ready[i+1] | ~valid_q[i];
```

不同 opcode 对同一个 2×SEW 乘积的使用方式如下：

| opcode 家族 | operand signedness | 结果选择 |
|---|---|---|
| `VMUL` | 低半与 signedness 无关 | product low |
| `VMULH` | signed × signed | product high |
| `VMULHU` | unsigned × unsigned | product high |
| `VMULHSU` | signed × unsigned | product high |
| `VMACC/VMADD` | 按指令排列乘数和 C | product low + C |
| `VNMSAC/VNMSUB` | 按指令排列乘数和 C | -product low + C |
| `VSMUL` | signed × signed | 定点移位、舍入、饱和 |

源码用扩展最高位控制有符号乘法：A 仅在 `VMULH/VSMUL` 等 signed-A 操作复制符号；B 在 `VMULH/VMULHSU/VSMUL` 等 signed-B 操作复制符号。混合有符号乘最常暴露端口角色理解错误，建议用 `-1 × 2` 同时测 `VMULH/VMULHU/VMULHSU`。

### 21.4 divider 两个 FSM 的逐状态不变量

| issue 状态 | 动作 | 离开条件 |
|---|---|---|
| `ISSUE_IDLE` | 等外部输入 | input handshake |
| `LOAD` | 锁存整个 beat 并装载 counter | 无条件进入检查 |
| `ISSUE_VALID` | 当前 active 元素送 serdiv | serdiv input handshake |
| `ISSUE_SKIP` | 当前 inactive 元素不计算 | 本拍递减 counter |
| `WAIT_DONE` | 所有元素均已发送/跳过 | 外部 beat 生命周期结束 |

| commit 状态 | 动作 | 离开条件 |
|---|---|---|
| `COMMIT_IDLE` | 等新 beat 被锁存 | LOAD 事件 |
| `COMMIT_READY` | 接收一个 divider 返回 | serdiv output handshake |
| `COMMIT_SKIP` | 为 inactive 元素推进拼接位置 | 本拍递减 counter |
| `COMMIT_DONE` | 保持完整 64-bit result valid | 外部 output handshake |

counter 初值是“元素数减一”：EW8/16/32/64 分别为 7/3/1/0。`be_q[cnt << vew]` 取当前元素的第一个 byte enable；一个元素的所有 byte 本应同 active，所以无需逐 byte 再判定。ISSUE_SKIP 与 COMMIT_SKIP 必须成对推进相同位置。

边界语义也要分层理解：除零、signed overflow 和商/余数规则由底层 `serdiv` 实现；`simd_div` 负责 opcode 映射、符号扩展、元素串行化和 packed result 重组。若数值规则错，先看 serdiv；若元素位置或握手错，先看 wrapper。

### 21.5 EW16 mixed-BE 的最小波形练习

输入握手后，确认 `opa_q/opb_q/be_q/vew_q/op_q` 一直稳定。对四个 EW16 元素，画出：

```text
counter       3       2       1       0
BE active?    yes     yes     no      yes
issue path    VALID   VALID   SKIP    VALID
commit path   READY   READY   SKIP    READY -> DONE
```

若输出 backpressure，`COMMIT_DONE` 应保持 `valid_o` 和整份 result 不变；不能重新接受下一个 beat。这个练习能同时验证 serialization、mask skip、位置恢复和 elastic output 四个关键性质。

## 22. `fpnew_top`：浮点 operation group 路由

### 22.1 NaN-boxing 检查

```systemverilog
assign is_boxed[fmt][op] = !vectorial_op_i
                         ? operands_i[op][WIDTH-1:FP_WIDTH] == '1
                         : 1'b1;
```

标量窄格式放在宽寄存器中时，高位必须全 1；否则按 canonical NaN 处理。vectorial 模式的高位本来装着其他元素，不能应用标量 boxing 规则。

### 22.2 每个 group 都存在，但只有一个接收当前输入

```systemverilog
for (genvar opgrp = 0; opgrp < NUM_OPGROUPS; opgrp++) begin
  assign in_valid = in_valid_i &&
      get_opgroup(op_i) == opgroup_e'(opgrp);

  fpnew_opgroup_block #(.OpGroup(opgroup_e'(opgrp))) i_block (...);
end
```

generate loop 在 elaboration 时生成 ADDMUL、DIVSQRT、NONCOMP、CONV、DOTP 等 group block。运行时 `get_opgroup` 是 one-hot 路由条件，当前 opcode 只向匹配 group 送 valid。

### 22.3 多个在途 group 的返回由 round-robin 仲裁

```systemverilog
rr_arb_tree #(.NumIn(NUM_OPGROUPS), .DataType(output_t)) i_arbiter (
  .req_i  (opgrp_out_valid),
  .gnt_o  (opgrp_out_ready),
  .data_i (opgrp_outputs),
  .gnt_i  (out_ready_i),
  .req_o  (out_valid_o),
  .data_o (arbiter_output)
);
```

不同 group 可能在同一周期完成。arbiter 选择一份 result/status/tag，并只向被选 group 返回 ready。未选中的 group 保持 valid 和 payload，等待后续周期。

### 22.4 ready 的实现约定与正确握手判断

此版本顶层的输入 ready 带 valid 门控，可概括为：

```systemverilog
in_ready_o = in_valid_i & selected_group_ready;
```

这与常见“空闲时预先拉高 ready”的风格不同，但传输事件仍严格是 `in_valid_i && in_ready_o`。上游不能用 ready 单独预测下一拍资源，也不能把 ready 低误判成 group 忙；在 valid 为零时它本来就会低。

### 22.5 tag、SIMD mask、flush 和 busy 的契约

`TagType` 与 operands/opcode 同时进入 group pipeline，并与 result/status 一起经过输出仲裁。在 VMFPU 集成中，tag 承载与结果对应的 mask 等元数据；若 tag 与 data 的 stall enable 不一致，数值可能正确，写回 BE 却属于另一拍。

```systemverilog
simd_mask = simd_mask_i | ~EnableSIMDMask;
busy_o    = |opgroup_busy;
```

关闭 SIMD mask 功能时内部 mask 被强制为全 1。`flush_i` 广播到所有 group 和相关流水控制，用于丢弃在途工作。`busy_o` 是所有 group busy 的 OR，不等于 `out_valid_o`：流水中可以有工作但尚无结果，也可以有结果被 backpressure 保持。

### 22.6 fpnew 与 VMFPU 的责任边界

fpnew 负责 IEEE 浮点 primitive、格式转换、舍入、NaN/exception 和 group pipeline；VMFPU 负责 RVV opcode 到 primitive 的映射、operand 交换、scalar replication、lane shuffle、narrow/widen 拼接、归约顺序以及写回元数据。定位 bug 时先判断错误属于“单次 FP 运算本身”还是“向量语义适配/调度”，能显著缩小范围。

## 23. `sldu` 与 `sldu_op_dp`：控制和置换网络的分工

### 23.1 `sldu` 决定“何时搬、搬多少、下一拍取什么”

`sldu` 维护指令队列、result queue、mask spill、stride 和状态机。普通 slide 的一拍行为是：

```systemverilog
if (all_required_operands_valid && !result_queue_full) begin
  sldu_operand_ready = enabled_lanes;
  result_queue_data  = permutation_result;
  result_queue_be    = slide_byte_enable;
  result_queue_cnt_d++;
  remaining_vl_d   -= elements_this_beat;
end
```

slide-up 的低地址区域可能要求 undisturbed，因此输出不能只由移动后的 source 构成，还要与旧 vd 和 byte enable 合并。slide1 的标量只插入边界元素，其余元素仍走普通置换网络。

### 23.2 任意距离分解为 power-of-two 阶段

```text
slamt = 最大 2 次幂部分 + remainder
```

对非 2 次幂距离，第一轮置换后把结果经 loopback spill 再送入下一轮。`np2_loop_mux_sel` 在外部 operand 与内部中间结果间切换。只有 remainder 清零后，结果才进入外部 result queue。

这相当于用较小的可复用置换网络完成更大集合的距离，而不是为每个任意距离复制完整 crossbar。

### 23.3 reduction 把 SLDU 当作 lane 间交换网络

第 k 层把间距为 `2^k` 的 lane partial result 配对：

```text
stride 1: lane 0<-1, 2<-3, 4<-5, ...
stride 2: lane 0<-2, 4<-6, ...
stride 4: lane 0<-4, ...
```

SLDU 只搬运和同步，真正的 add/min/max 仍回到 VALU 或 VMFPU。因而 TX/RX handshake 必须同时考虑源 lane 是否有partial result、目标 VFU 是否ready，以及当前树层哪些 lane 仅做同步。

### 23.4 `sldu_op_dp` 是组合 byte crossbar

核心代码形态为：

```systemverilog
unique case ({eew_src_i, eew_dst_i, slamt_i, dir_i})
  SOME_CONFIG: begin
    op_o_flat[DST_BYTE*8 +: 8] = op_i_flat[SRC_BYTE*8 +: 8];
    ...
  end
endcase
```

`op_i_flat = op_i` 先把 lane×64-bit packed array 展平成一条总线。每条 indexed part-select 都是一根 8-bit 连线；case 选择不同连线集合，综合后成为 byte 粒度 MUX/crossbar。

文件巨大是因为它为 lane 数、源 EEW、目标 EEW、方向和距离预展开所有静态映射。理解它只需掌握三个变换：

1. 架构元素编号按 EEW 转成 shuffled lane/byte 位置。
2. slide 方向和距离修改架构元素编号。
3. 新编号再按目标 EEW 转回输出 lane/byte 位置。

### 23.5 完整 FSM：普通、ordered sum 与 NP2 是三条路径

```text
SLIDE_IDLE
SLIDE_RUN
SLIDE_RUN_VSLIDE1UP_FIRST_WORD
SLIDE_RUN_OSUM
SLIDE_WAIT_OSUM
SLIDE_NP2_SETUP
SLIDE_NP2_RUN
SLIDE_NP2_COMMIT
SLIDE_NP2_WAIT
```

- `SLIDE_RUN` 处理普通 slide、2 次幂分量以及 reduction 搬运。
- `SLIDE_RUN_VSLIDE1UP_FIRST_WORD` 单独构造 slide1up 的首 word，因为 element 0 来自 scalar，剩余位置来自移位 source。
- `SLIDE_RUN_OSUM/WAIT_OSUM` 实现 ordered FP sum 的单 token lane 环，并留出同步周期。
- 四个 NP2 状态把中间结果回环，直到任意 stride 的所有 set bit 均处理完。

状态名相似但完成条件不同。阅读 case 分支时，应先标注“本状态的数据来源、目的地、谁消费 valid”，再看 counter 更新，否则很容易把内部 buffer 的一次握手当成 VRF 写回。

### 23.6 byte counter、窗口指针和普通 slide 初始化

SLDU 的 `issue_cnt/commit_cnt` 以 byte 为单位，而非元素；stride 在接收指令时也由元素数换算为 byte。几个指针的层次不同：

| 状态量 | 单位 | 含义 |
|---|---:|---|
| `issue_cnt` | byte | 还需从输入侧处理多少 byte |
| `commit_cnt` | byte | 还有多少结果 byte 未完成 |
| `in_pnt` | chunk 内 byte | 当前输入窗口起点 |
| `out_pnt` | chunk 内 byte | 当前输出窗口起点 |
| `vrf_pnt` | VRF word | operand/result 的寄存器地址 |

一个 aggregate chunk 宽度为 `NrLanes * 8` byte。有效输出区间由输入、输出窗口相对位置形成，概念上类似：

```systemverilog
output_limit = NrLanes * 8 + out_pnt - in_pnt;
out_en       = sequential_enable(output_limit, out_pnt);
write_be     = shuffled(out_en) & predicate_mask;
```

`VSLIDEUP` 从输入 offset 0 读取，输出从 stride 后开始，低地址位置依 policy 保留；`VSLIDEDOWN` 从输入 stride 处读取、输出从 0 开始；`VSLIDE1DOWN` 还要为最后一个 scalar 元素保留边界位置。每拍 `byte_count` 取“输入窗口剩余、输出窗口剩余、总 issue 剩余”的最小值，所以一个 chunk 可能跨多拍完成。

### 23.7 NP2 的两个固定槽不是普通 FIFO

任意距离由 `p2_stride_gen` 逐次取出 stride 中的 2 次幂分量。NP2 期间，result queue 的两个固定槽被赋予专门角色：

```text
NP2_BUFFER_PNT：保存本轮输入/上一轮中间结果
NP2_RESULT_PNT：保存本轮 crossbar 输出
```

`SLIDE_NP2_SETUP` 等普通 queue 内容排空并收齐 operand；`SLIDE_NP2_RUN` 在外部输入和内部 loopback 间选择，处理一个分量；剩余 stride 为零时进入 `SLIDE_NP2_COMMIT`，把内部数据包装成正常可写回 payload；`SLIDE_NP2_WAIT` 等该 chunk 排空，避免固定槽被下一 chunk 覆盖。

核心不变量是：内部 NP2 valid 只表示“某轮中间值可用”，外部 VRF request 只允许看见 COMMIT 后的最终值。若过早暴露内部槽，任意 stride 会写回部分置换结果。

### 23.8 逐 lane grant、final grant 与 reduction 特例

result queue 实际是“槽 × lane”的二维结构。每个 lane 的普通 grant 可以在不同周期到达，因此对应 lane valid 被逐个清除；只有该槽所有 lane 都已被接收，并满足最终写回确认，read pointer 与 queue count 才能前进。

普通 `gnt` 表示下游请求器接收了请求，`final_gnt` 表示该 lane 的 VRF 写入真正到达最终阶段。两者分离允许写回网络流水化，但 queue 生命周期必须等后者。

reduction 是例外：SLDU 输出送回 VALU/VMFPU 的 reduction port，而不是 VRF，因此完成由 `sldu_red_valid/ready` 的握手决定，不应等待 VRF final grant。ordered sum 中任一时刻只有目标 lane 拥有有效 token；它交给下一 lane，最后回 lane 0，再经 `SLIDE_WAIT_OSUM` 隔离相邻 phase。

## 24. `masku_operands`：把四类输入变成三种可用视图

输入通道固定为：

```systemverilog
masku_operands_i = {v0.m, vd, alu_result, fpu_result};

masku_operand_alu_o[lane] = masku_operands_i[lane][2 + masku_fu_i];
masku_operand_vd_d[lane]  = masku_operands_i[lane][1];
masku_operand_m_d[lane]   = masku_operands_i[lane][0];
```

`masku_fu_i` 在 ALU 和 FPU result channel 中选择。vd 与 v0 经过 spill register，因为 MASKU 的 sequential 运算可能分多拍消费，不能要求 lane operand queue 一直保持。

### 24.1 deshuffle 恢复架构顺序

```systemverilog
for (int b = 0; b < NrLanes * ELENB; b++) begin
  int seq = deshuffle_index(b, NrLanes, eew);
  int lane = b / ELENB;
  int off  = b % ELENB;
  operand_seq[8*seq +: 8] = operand_lane[lane][8*off +: 8];
end
```

lane-local VFU 喜欢 shuffled 视图，因为每 lane 每拍处理固定 64 bit；`vcpop/viota/vfirst` 喜欢架构顺序 bit 流。这个循环只是线重排，不是运行时逐 byte 循环执行。

### 24.2 comparison compression

ALU/FPU 为每个 SEW 元素产生一个比较 bit，但它们仍分散在元素低位。压缩逻辑只访问每个元素首 byte：

```systemverilog
if ((byte % bytes_per_element) == 0) begin
  compare_mask[dest_bit] = alu_result[src_lane][src_byte*8];
end
```

`dest_bit` 还加上 `vrf_pnt`，这样一个 beat 的比较结果可以接到目标 mask register 当前写指针之后。

### 24.3 predicate bit 扩展成 byte enable

一个 mask bit 控制整个元素，因此必须复制到该元素全部 byte。比较、普通 masked 运算和 `VMADC/VMSBC` 的含义不同：后两者把 v0 当 carry/borrow source，不能与 predicate enable 相与。

### 24.4 spill register 保存的是 token，不是数据副本

只有旧 `vd` 和 v0 mask 通道需要 spill；ALU/FPU result 由各自 producer 的 valid/ready 保持。一个 spill token 同时提供 shuffled view 与 sequential view，但两者只是同一份数据的两种连线解释：

```systemverilog
spill_ready = shuffled_consumer_ready | sequential_consumer_ready;
```

因此下游必须按 opcode 选择其中一种消费语义，不能把两个 view 当成可独立弹出两次的数据副本。若两个不兼容 consumer 同时声称 ready，token 只会前进一步，另一路下一拍看到的已是新数据。

### 24.5 ALU/FPU 选择必须同时路由 ready

`masku_fu_i` 从 ALU result 与 FPU result 中选择当前计算来源。选择器不仅控制 data：valid 只取被选通道，ready 也只能返回被选 producer。否则未选 producer 会误以为结果已被消费。

comparison compression 从每个元素的低有效 bit 提取布尔值；predicate expansion 则把一个 bit 复制为该 SEW 元素的全部 byte enable。前者是“多 byte 元素压成 1 bit”，后者是“1 bit 扩成多 byte”，两条路径方向相反，不应共用计数解释。

### 24.6 三种 EEW 与 tail policy 的边界

source、旧 vd 和 v0 mask 可能具有不同 EEW/shuffle 索引，所以各自需要独立的 deshuffle 映射。复用 source 的 byte index 去读 mask，在 EW8 测试中可能碰巧正确，在 EW16/32 很快错位。

当前配置可关闭本地 `VlBitMaskEnable`；tail-undisturbed 不是因此消失，而是通过读取 old vd 并在最终 background merge 中保留 tail。`VMADC/VMSBC` 再次构成特殊边界：v0 是 carry/borrow source 时不参与普通 predicate gating。

## 25. `masku`：所有重要逻辑的代码化理解

### 25.1 为什么只允许一条在途指令

MASKU 同时维护 v0、旧 vd、比较中间结果、prefix 状态和多 lane grant。当前实现把 instruction queue 深度限制为 1，避免后一条 masked 指令读取尚未生成的新 mask，也避免两条指令共享 `found_one/viota_acc` 等状态。

### 25.2 predicated execution：从一个 bit 生成元素 byte mask

```systemverilog
mask_bit = mask_operand_seq[mask_seq_bit];

for (int byte = 0; byte < bytes_per_element; byte++)
  lane_mask[target_lane][target_byte + byte] = mask_bit;
```

MASKU 把生成的每 lane `strb_t` 放入 mask queue，再广播给目标 VFU。各 lane 可在不同周期 grant，因此 request vector 逐 lane 清除；只有所有参与 lane 都接收后才能弹出 queue head。

### 25.3 mask logical 和 comparison

mask logical 已在 VALU 做完 64-bit 位逻辑：

```systemverilog
VMAND:    result = a & b;
VMANDNOT: result = ~a & b;
VMXNOR:   result = ~(a ^ b);
```

MASKU 负责将其放入 mask register 布局并实施 tail policy。comparison 则使用压缩后的连续 bit 流，再结合 v0 predicate：

```systemverilog
effective_compare = compare_bits & predicate_bits;
```

masked-off 与 tail bit 最终写旧 vd 还是允许 agnostic 1，由 `vma/vta` policy 和 background data MUX 决定。

### 25.4 `VMSBF/VMSIF/VMSOF` 是跨 slice 的 first-one FSM

```systemverilog
current_has_one = |masked_slice;

if (!found_one_q && current_has_one) begin
  first_pos   = lzc(masked_slice);
  found_one_d = 1'b1;
  result      = pattern_before_or_at(first_pos, op);
end else if (!found_one_q) begin
  result = all_before_pattern(op);
end else begin
  result = '0;
end
```

`found_one_q` 必须跨拍保存，因为首个 1 可能在后续输入 word。三条指令共享“找首 1”网络，只在首位是否包含于输出上不同。

### 25.5 `VIOTA` 与 `VID` 是 prefix-sum 数据通路

```systemverilog
running = viota_acc_q;
for (int i = 0; i < ViotaParallelism; i++) begin
  result[i] = running;
  running  += input_bit[i];
end
viota_acc_d = running;
```

`VIOTA` 的 input bit 来自被 predicate 过滤后的 mask；`VID` 把每个有效位置视为 1，复用同一串 prefix adder。实现使用多个有限宽加法器并行处理一 slice，slice 之间由 accumulator 衔接。

### 25.6 `VCPOP` 与 `VFIRST`

```systemverilog
popcount_d += popcount(masked_slice);

if (!found_one_q && |masked_slice) begin
  vfirst_d    = processed_bits + lzc(masked_slice);
  found_one_d = 1'b1;
end
```

`VCPOP` 把每 slice 的 population count 累加成 scalar；`VFIRST` 用 leading/trailing-zero counter 得到slice内位置，再加已处理bit数。若整条向量没有 1，返回架构规定的 `-1`。

### 25.7 gather 地址为什么要广播所有 lane

当前实现先从 index operand 产生一个元素地址，然后把同一个请求发给所有 lane：

```systemverilog
for (int lane = 0; lane < NrLanes; lane++) begin
  req_o[lane].addr  = gather_addr;
  req_o[lane].valid = fifo_valid & ~lane_already_granted[lane];
end
```

每个 lane 可以独立返回 grant，`lane_already_granted` 隐藏已完成 lane 的 valid。全部 lane 都确认后才弹地址 FIFO。返回 payload 中只有拥有目标元素的部分真正被选择，其余被丢弃。这不是最省带宽的方案，但控制简单且时序对称。

### 25.8 `VCOMPRESS` 的输入计数和输出计数不同

每个 source element 都要检查 mask，因此输入计数始终遍历 VL；只有 mask=1 时目标 index 才加一：

```systemverilog
if (compress_mask_bit) begin
  output[compress_write_index] = source_element;
  compress_write_index_d++;
end
input_index_d++;
```

因此不能用“剩余输入元素数”判断 result word 是否填满。MASKU 单独维护 output slice counter 和最终 `vcompress_num_ones`，最后一个未填满 word还要以旧 vd 作为 background 实施 undisturbed policy。

### 25.9 三套 delta counter 解释宽度不匹配

MASKU 常出现“一个输入 word 被消费多拍”或“多拍才凑一个输出 word”：

- `in_ready_cnt`：输入数据切片全部消费后，才向 operand queue 拉 ready。
- `in_m_ready_cnt`：mask bit 流的切片计数，与数据宽度独立。
- `out_valid_cnt`：结果切片凑满一个 VRF word后，才置 result queue valid。

例如 VIOTA 输入是 1-bit mask，输出却是 SEW-bit整数，输入和输出吞吐比天然不同。三个 counter 分离是正确握手的基础。

### 25.10 old-vd background 与最终写回

MASKU 不直接从零开始构造结果，而是：

```systemverilog
result = old_vd;
result[active_positions] = new_value;
```

对 agnostic 位置可以先填 1；对 undisturbed 位置必须保留 old vd。完成的每 lane payload进入 result queue，VRF request发出后还要等待 `final_gnt`。普通 `gnt` 只表示中间请求器接收了请求，不能证明VRF已经完成写入。

### 25.11 MASKU 不是一个大 FSM，而是 counter 驱动的微引擎

MASKU 的 instruction queue 深度为 1，但内部另有 mask queue 和每 lane result queue。它不靠一个中央状态枚举描述所有操作，而是由 opcode 配置以下参数，再用 counter/threshold 推进：

| 参数 | 作用 |
|---|---|
| `delta_elm` | 每个计算 slice 处理多少架构元素 |
| `in_ready_cnt/threshold` | 当前数据 operand word 还要分几 slice 消费 |
| `in_m_ready_cnt/threshold` | 当前 mask word 还要分几 slice 消费 |
| `out_valid_cnt/threshold` | 多少 slice 才拼成一个可发布结果 word |
| issue/processing/commit counters | 分别记录输入、计算和写回剩余工作 |

这些 counter 的单位随指令族变化，可能是元素、mask bit、slice 或目标元素。它们不能脱离 opcode 解释。看到 `counter += delta` 时，第一问应是“这个 counter 当前以什么为单位”。

### 25.12 各指令族如何配置同一套推进框架

| 指令族 | 计算粒度 | 输入/输出关系 | 主要跨 slice 状态 |
|---|---:|---|---|
| mask logical | `VmLogicalParallelism` bits | bit → bit | 通常无 accumulator |
| comparisons/carry mask | 每 ALU packet 的元素数 | SEW-bit 元素 → 1 bit | compare compression |
| `VMSBF/VMSIF/VMSOF` | `VmsxfParallelism` bits | bit → bit | `found_one` |
| `VIOTA/VID` | `ViotaParallelism` 元素 | bit/index → SEW-bit | prefix accumulator |
| `VCPOP/VFIRST` | 各自 parallelism | bit stream → scalar | popcount / first position |
| gather | 1 个目标元素 | index → VRF read → element | address/result FIFO |
| compress | 1 个 source 元素 | 条件写目标元素 | 独立 destination index |

comparison 一拍可得到的元素数随 SEW 变化，通常由 `NrLanes << (EW64-eew)` 推导；mask logical 的吞吐与 SEW 无关；VIOTA 的输入是 bit、输出是 SEW-bit，因而 output threshold 随 SEW 改变；gather/compress 为了地址和稀疏目标控制通常 `delta_elm=1`。这解释了为什么同一组 counter 需要可编程 threshold。

### 25.13 gather 的两级排队与广播握手

gather 至少分成两类队列信息：

1. index metadata FIFO：保存 index、是否越界、是否最后一个等控制。
2. lane address request FIFO：保存由 index 换算出的 VRF 地址请求。

同一地址向所有 lane 广播时，以 lane grant bitmap 记住哪些 lane 已接受；只有全部目标 lane 均完成本次接受才弹地址。返回后根据 shuffle/owner 选择真正含目标元素的数据。越界 index 不应发起有意义的读取，架构结果直接为零。

这条路径有三个不同的“完成”：index 已消费、地址已被所有 lane 接收、返回元素已进入 result queue。把它们合并成一个 valid 会在 lane backpressure 时重复请求或丢 index。

### 25.14 result background、scalar 返回与完成条件

结果槽初始 background 按 policy 选择 old vd 或 agnostic 1，后续 slice 反复修改同一个槽的 active position；只有 `out_valid_threshold` 到达才发布完整 word。VIOTA/VID/gather/compress 写整数元素，需要精确 byte enable；mask 目标常以完整 mask word 形式写回。

`VCPOP/VFIRST` 的 scalar result 经过一级寄存；接口假定前端能按约定接收，下一周期再清 accumulator。调试这类指令时不要在 VRF result queue 中寻找 scalar 写回。

普通指令完成至少要求：issue 输入耗尽、所有部分 result 已发布、result queue 排空、所有 lane final grant 返回。`VCOMPRESS` 还要确认最后一个可能未填满的目标 word 已以 background 补全。只看 source issue counter 为零会过早释放指令。

### 25.15 接收条件与 `vinsn_running` 防重入

MASKU 有两种工作来源：目标本身就是 MASKU 的指令，以及普通 VFU 的 masked 指令所需 predicate 生成。因此接收判定概念上是：

```systemverilog
accept = !vinsn_running
      && (instruction_targets_masku || instruction_is_masked);
```

`vm=1` 的普通 ALU/FPU 指令无需 MASKU 生成 predicate；`vm=0` 时即使最终计算在别的 VFU，MASKU 也要参与。`vinsn_running` 防止上游 valid 在 ready/确认边界保持时重复登记同一条指令。若出现 mask queue 数量莫名加二，应优先检查这一防重入握手。

## 26. 完成学习后应能独立回答的问题

如果已经掌握本文的重要逻辑，应能不看结论独立回答：

1. 为什么 VALU 的 instruction queue 需要 issue 与 commit 两套 pointer/count？
2. narrowing 第一拍为什么不能增加 result queue count？
3. integer reduction 为什么只有 lane 0 使用真实 scalar seed？
4. `VMADC/VMSBC` 为什么不能把 v0 当普通 predicate？
5. signed saturation 如何从输入和结果符号检测？
6. VMFPU 为什么需要 processing 阶段和 latency ordering stall？
7. elastic multiplier 在 backpressure 时如何保证 operand、mask、valid不撕裂？
8. serial divider 如何把多个窄元素重新拼回64-bit beat？
9. ordered FP sum 为什么不能用 unordered reduction tree？
10. `fpnew_top` 怎样保证未获仲裁的group结果不丢失？
11. `sldu` 与 `sldu_op_dp` 分别负责控制还是实际置换？
12. MASKU 为什么同时需要 shuffled、sequential和compressed视图？
13. `VIOTA` 为什么是prefix sum而不是普通popcount？
14. `VCOMPRESS` 为什么必须分开维护输入和输出计数？
15. 为什么VRF写回既有grant又有final grant？

此外还应能完成以下不看答案的实操检查：

1. 为一条普通 VALU 指令画出 accept、两次 operand handshake、result queue 入队、VRF grant/final grant 和 retire，并标清每个 counter 的单位。
2. 为 `VNCLIP` 证明“两次输入只发布一次目标 word”，并指出 mask 在哪一相位前进。
3. 构造“慢 divide 在前、短 FP compare 在后”，解释 VMFPU 哪个条件阻止乱序返回。
4. 为 EW16 divider 混合 active/inactive 元素画两个 FSM 的状态序列，证明 SKIP 后元素位置不变。
5. 从 shuffled 64-bit word 手工恢复 ordered FP sum 的 EW8 元素顺序。
6. 将一个非 2 次幂 slide 距离分解，标出 NP2 两个固定槽在每轮的 owner。
7. 对一个稀疏 `VCOMPRESS` 分别计算 source、destination、result-word 和 final-grant 进度。
8. 在任一输出端施加连续 backpressure，检查 valid 为 1 时所有 payload 是否保持稳定。

最后用以下四类不变量复核自己的理解：

- **所有权不变量**：每个在途 token 当前唯一属于 operand queue、功能流水、result queue 或写回网络之一。
- **原子握手不变量**：一组必须对齐的 data/op/mask/tag/metadata 只能在同一个 handshake 上共同前进。
- **计数单位不变量**：每个 counter 的单位明确，只有在对应事件发生时按对应 delta 更新。
- **完成不变量**：输入耗尽不等于完成；还必须考虑处理中结果、queue 排空、跨 lane 同步和 final grant。

能结合波形证明这些问题，并能用上述不变量解释一次故障为何发生，才算达到可以安全修改这些模块、增加相邻指令或定位控制 bug 的教学目标。

## 27. 面向性能评估与瓶颈归因的完整 RVV 指标

本节描述测试平台在 [`ara_tb.sv`](../tb/ara_tb.sv) 中实现的完整 RVV 性能监控。监控不再只覆盖六个计算功能部件，而是同时观察三层事件：

1. dispatcher 看见的**架构指令流**，回答软件实际发出了什么指令。
2. sequencer 接收的**后端请求或微操作**，回答一条架构指令被 Ara 展开成了多少工作。
3. VALU、VMFPU、SLDU、MASKU、VLSU、MMU 和 AXI 上的**微架构事件**，回答周期消耗在何处。

这三层必须分开。尤其是 zero-VL 指令可能只在 dispatcher 完成而不进入 sequencer；segment memory 指令可能从一条架构指令展开为多条后端请求；reshuffle 则是 dispatcher 自动注入的内部请求，根本不是软件中的 RVV 指令。若只看某一层，指令数“不相等”既可能是正常展开，也可能是测量窗口不完整。

通用后端字段都带 `<class>` 前缀。架构类别可替换为 `valu`、`mul`、`div`、`fp`、`slide`、`mask`、`load`、`store`、`move_to_vec` 或 `move_from_vec`；内部类别还有 `reshuffle`。例如 `fp_operand_wait_cycles` 是 FP 类在执行阶段观测到操作数未就绪的 wall-clock 周期数，`load_arch_insns` 是 dispatcher 完成的架构 load 数，`load_exec_insns` 则是 sequencer 接收的 load 后端请求数。

### 27.1 完整类别与互斥边界

| 指标前缀 | Ara 操作范围 | 归类原则 |
|---|---|---|
| `valu` | 整数算术、逻辑、定点、移位、整数归约、整数比较、carry/borrow、merge | 比较即使还使用 MASKU，也归产生数据的 VALU 类；不会重复计入 `mask` |
| `mul` | 整数乘法、MAC、`VSMUL` | 虽与 div、FP 共享 VMFPU wrapper，仍独立统计 |
| `div` | `VDIV[U]`、`VREM[U]` | 覆盖串行除法器的完整生命周期 |
| `fp` | FP 算术、FMA、sqrt、估算、分类、符号注入、转换、归约和比较 | FP compare 不重复计入 `mask` |
| `slide` | 架构 `VSLIDEUP`、`VSLIDEDOWN` | 归约内部使用 SLDU 仍归原始 VALU/FP 指令；内部 reshuffle 不计入这里 |
| `mask` | prefix、iota/id、population/first、mask logical、gather/compress | 只统计原生 mask/bit-level/permutation 类操作 |
| `load` | `VLE`、`VLSE`、`VLXE` 后端形式 | 架构层进一步区分 unit-stride、strided、indexed、segment、whole-register、mask、fault-only-first |
| `store` | `VSE`、`VSSE`、`VSXE` 后端形式 | 与 load 使用相同的地址模式和 segment 维度 |
| `move_to_vec` | `VMVSX`、`VFMVSF` | 标量写入向量寄存器 element 0，即 `vmv.s.x`/`vfmv.s.f` 路径；普通广播/merge 按其解码后的 VALU/FP 路径统计 |
| `move_from_vec` | `VMVXS`、`VFMVFS` | element 0 返回标量，即 `vmv.x.s`/`vfmv.f.s`；sequencer 使用 `VFU_None` 和 scalar response |
| `reshuffle` | dispatcher 自动生成的内部 `VSLIDEDOWN` 请求 | 仅后端存在，用于量化 EEW 布局转换；没有对应 `<class>_arch_insns` |

前十个架构类别互斥。一个已成功解码并完成响应的非配置 RVV 指令最多增加一个类别，因此可相加而不会因多目标 VFU 重复。例如整数 compare 同时需要 VALU 与 MASKU，但仍只是一条 `valu`；FP reduction 同时使用 VMFPU 与 SLDU，但仍只是一条 `fp`。

配置类不放入上表的执行类别，而由独立指标覆盖：`vsetvli`、`vsetivli`、`vsetvl` 以及对 vector CSR 的读写。原因是它们可能修改 `vl/vtype/vstart/vxrm/vxsat` 并等待后端 idle，却不创建常规 vector instruction ID。不同类别的 `active_cycles` 允许重叠，因为不同功能部件可以并行工作。

### 27.2 三个时间点与两种 latency

后端监控器为每个 Ara vector instruction ID 保存类别、是否 masked、首次派发周期和派发等待时间。核心时间点为：

- `T_arch`：dispatcher 的 response 完成握手。这一层增加 `<class>_arch_insns`；zero-VL 和配置指令也能在这里完成。
- `T_accept`：sequencer 的 `accepted_insn` 拉高，新后端 token 第一次进入。这一层增加 `<class>_exec_insns`；请求因 ready 低而保持多个周期时只计一次。
- `T_issue`：`pe_req_d` 第一次为该 ID 有效，且该 ID 尚未在 `vinsn_running_q` 中。这里表示指令真正分配 ID 并进入各目标 VFU。
- `T_done`：该 ID 从 `vinsn_running_q=1` 变为 `vinsn_running_d=0`。这表示该指令所涉及的所有目标执行路径已经完成。

由此定义：

```text
dispatch_wait = T_issue - T_accept
execution_latency = T_done - T_issue + 1
end_to_end_latency = dispatch_wait + execution_latency
```

`execution_latency` 中的 `+1` 表示把首次派发所在周期也算入该条指令的执行跨度。因此，当指令完全串行时，`execution_latency_cycles` 往往比 `active_cycles` 每条多一个周期：首次派发的组合周期尚未出现在寄存后的 `vinsn_running_q` 中。这不是计数错误，而是两个指标观察边界不同。

`move_from_vec` 是一个重要例外。它的目标是 `VFU_None`，不会像普通 VFU 指令那样长期置位 `vinsn_running_q`。监控器因此在首次 issue 时建立独立 pending 状态，并以 `pe_scalar_resp_valid_i && pe_scalar_resp_ready_o` 作为完成点；否则 WAIT 状态中的同一请求会被误算成多次 issue。`move_to_vec` 仍经过 lane VALU，所以使用普通 ID 生命周期。

`reshuffle` 也使用后端生命周期，但类别不是根据其表面上的 `VSLIDEDOWN` opcode 直接决定，而是结合 dispatcher 的 `RESHUFFLE` 状态记录为内部类。这样软件显式 slide 的 latency 与为 EEW 转换付出的 latency 不会混在一起。

### 27.3 工作负载形状指标

比较两个 kernel 的周期前，必须先判断它们做的工作量是否相同。否则“周期更少”可能只是 VL 更短或 SEW 不同。

| 指标 | 精确定义 | 用途与注意事项 |
|---|---|---|
| `<class>_arch_insns` | `T_arch` 时该架构类别的指令数 | 最接近软件动态指令数；不包括内部 reshuffle |
| `<class>_zero_vl_nop_insns` | 在 dispatcher 因 `vstart >= vl` 或空 slide 条件直接完成的指令数 | 这些指令正常没有后端 request；whole-register memory 等忽略 zero-VL 的指令不在此列 |
| `<class>_zero_vl_nop_ratio` | `zero_vl_nop_insns / arch_insns` | 高值说明前端正在处理大量无有效 element 的架构工作 |
| `<class>_exec_insns` | `T_accept` 时该类后端请求数 | 对普通指令近似架构指令数；segment 可展开，zero-VL 可不进入后端 |
| `<class>_backend_uops_per_arch_insn` | `exec_insns / arch_insns` | 同时受 zero-VL 与 segment 展开影响，不能单独解释 |
| `<class>_nonzero_backend_coverage_ratio` | `exec_insns / (arch_insns - zero_vl_nop_insns)` | 普通类别完整窗口应约为 1；memory segment 可以大于 1 |
| `<class>_requested_elements` | 每条接收指令的 `max(vl - vstart, 0)` 之和 | 是请求处理的 element slot，不是实际有效元素数；masked-off 元素仍包含在内 |
| `<class>_avg_requested_elements_per_insn` | `requested_elements / exec_insns` | 判断 VL 形状是否变化 |
| `<class>_requested_elements_per_rvv_cycle` | `requested_elements / total_rvv_cycles` | 端到端 element-slot 吞吐，包含派发、执行及与内存交叠的影响 |
| `<class>_nominal_element_ops` | 请求元素数乘该 opcode 的名义运算权重 | 普通非 memory 操作为 1，整数/FP fused MAC 为 2，memory 为 0 |
| `<class>_nominal_element_ops_per_rvv_cycle` | `nominal_element_ops / total_rvv_cycles` | 比 requested-elements 更适合比较 add 与 FMA/MAC 的名义算术吞吐 |
| `<class>_masked_insns` | 接收时 `vm=0` 的指令数 | 表示需要 predicate 的指令数，不等于 mask 类指令数 |
| `<class>_masked_insn_ratio` | `masked_insns / exec_insns` | 比较 predicate 使用强度 |
| `<class>_reduction_insns` | 整数或 FP reduction 指令数 | 用于分离普通 SIMD 与归约算法路径 |
| `<class>_special_path_insns` | gather/compress，或采用非 2 次幂 stride 的 slide 指令数 | 标识数据置换类特殊路径 |
| `<class>_sew8_insns` | 接收时 SEW=8 的指令数 | 与其余三个 SEW bin 一起描述宽度分布 |
| `<class>_sew16_insns` | 接收时 SEW=16 的指令数 | 同上 |
| `<class>_sew32_insns` | 接收时 SEW=32 的指令数 | 同上 |
| `<class>_sew64_insns` | 接收时 SEW=64 的指令数 | 同上 |

load/store 还输出后端请求形状：`<class>_unit_stride_backend_uops`、`strided_backend_uops`、`indexed_backend_uops`、`segment_backend_uops`、`fault_only_first_backend_uops`、`backend_requested_bytes` 和 `backend_requested_bytes_per_uop`。这里的 `uop` 明确指 sequencer 接收的请求，不保证与架构指令一一对应。segment 的每个 field 会形成后端工作，所以分析 memory 指令吞吐时必须同时保留架构数和 uop 数。

在当前 ELEN=64 配置下，四个 SEW bin 之和应等于该类 `exec_insns`。对 memory 类，bin 中的宽度是 Ara 后端处理的数据 EEW：indexed 指令的索引 EEW由另一操作数字段决定，不应把该 bin 误读成索引宽度。`requested_elements` 不能直接当作“真正做了多少次算术”：mask 为 0 的元素、tail 位置以及 reduction 的内部树形操作都不会从这个值中扣除。它适合做同一 ISA 工作负载的归一化，不适合估计精确门级运算次数。

`nominal_element_ops` 同样不是门级 toggle、实际乘加器调用次数或 RVV 规范意义上的精确 FLOP。它只是稳定的工作量归一化口径：`VFMACC`/整数 MAC 的每个请求 element 记 2，其它非 memory opcode 记 1，load/store 记 0。它不扣除 mask-off/tail，也不展开 reduction tree、rounding、地址生成和内部置换。因而可用它比较同一算法在不同实现上的名义 Ops/cycle，但不能据此计算功耗或宣称实际执行了同样多的物理运算。

#### 27.3.1 配置与 vector CSR 指标

配置指令的性能问题经常表现为“计算和内存都不忙，但 RVV 周期仍在增长”。因此它们有独立报告，不能从 VALU/VLSU active cycle 反推。

| 指标 | 精确定义 | 如何使用 |
|---|---|---|
| `config_insns` | 已完成 dispatcher response 的所有配置类指令 | 应等于三个 vset 子类与 vector CSR 之和 |
| `vsetvli_insns` | `vsetvli` 动态指令数 | AVL 来自整数寄存器，vtype 来自立即数字段 |
| `vsetivli_insns` | `vsetivli` 动态指令数 | AVL 与 vtype 都由指令编码给出 |
| `vsetvl_insns` | `vsetvl` 动态指令数 | AVL 与 vtype 可来自整数寄存器 |
| `vector_csr_insns` | 对 vector CSR 的 system/CSR 指令数 | 继续拆为 write 与 read-only |
| `vector_csr_write_insns` | 实际写 CSR 的指令数 | `csrrw[i]` 总是写；`csrrs/c` 在源非零时写 |
| `vector_csr_read_only_insns` | 未修改 CSR 的只读操作数 | 有助于区分状态采样与频繁重配置 |
| `config_request_cycles` | 配置请求在 dispatcher 输入保持有效的周期 | valid 保持多拍会逐拍累计 |
| `config_blocked_cycles` | 配置请求尚未完成 response 的周期 | 除以 request cycles 得 `config_blocked_ratio` |
| `config_wait_idle_cycles` | dispatcher 在 `WAIT_IDLE` 状态等待的周期 | 配置修改通常必须与旧向量工作建立清晰边界 |
| `config_wait_backend_busy_cycles` | `WAIT_IDLE` 且 `ara_idle_i=0` 的周期 | 直接说明旧的后端工作尚未 drain |
| `config_wait_ara_ready_cycles` | dispatcher 处于正常 decode 状态但 Ara request 入口不 ready | sequencer/入口反压影响配置请求 |
| `config_wait_reshuffle_cycles` | dispatcher 正在完成内部 reshuffle 的周期 | vtype/EEW 布局转换相关成本 |
| `config_other_blocked_cycles` | 已阻塞但不属于以上原因的排他 residual | 长期非零时应新增更具体探针 |
| `vset_result_vl_sum`、`vset_avg_result_vl` | 所有 vset 最终产生的 VL 总和与平均值 | 判断配置频率之外，每次配置覆盖多少工作 |
| `vset_zero_vl_insns` | vset 结果 VL 为 0 的次数 | 后续大量 zero-VL no-op 的先导信号 |
| `vset_vill_insns` | 结果 `vtype.vill=1` 的次数 | 非法/不支持的 vtype 配置 |
| `vset_vl_change_insns` | 新旧 VL 不同的 vset 次数 | 排除重复配置后，真正改变工作长度的比例 |
| `vset_vtype_change_insns` | 新旧 vtype 不同的 vset 次数 | 与 reshuffle、SEW/LMUL 变化结合分析 |
| `vset_lmul_shrink_wait_insns` | 完成 vset 时将 dispatcher 推入 idle-wait 路径的次数 | 用于识别 LMUL/寄存器布局收缩引起的序列化 |
| `vset_sew{8,16,32,64}_insns` | vset 结果 SEW 分布 | 四个 bin 之和应等于 vset 总数 |
| `vset_lmul_encoding_<0..7>_insns` | vset 结果 `vlmul` 三位编码直方图 | 保留原始编码，包含整数、分数 LMUL 及保留编码 |

这里区分“指令计数”和“等待周期”非常重要。`vsetvli_insns` 高只能说明重配置频繁；只有 `config_blocked_ratio` 或某个等待原因也高，才能说明它对 wall time 造成明显压力。`config_wait_idle_cycles` 与 `config_wait_backend_busy_cycles` 允许前者大于后者，因为 WAIT_IDLE 状态中还可能包含状态切换边界。

报告提供 `config_subtype_hist_consistent` 和 `vset_sew_hist_consistent` 两个守恒字段。它们为 1 仅说明分类完整，不说明配置策略高效。

#### 27.3.2 架构 memory 指令形状

对 `load` 和 `store` 分别输出以下 dispatcher 层指标。它们以**一条编码指令**为单位，不受 segment sequencer 展开影响。

| 指标 | 精确定义 | 性能意义 |
|---|---|---|
| `<mem>_arch_memory_insns` | 架构 load/store 数 | memory 指令总数基准 |
| `<mem>_arch_unit_stride_insns` | `mop=00` | 包括普通 unit-stride、whole-register、mask memory 和 fault-only-first |
| `<mem>_arch_strided_insns` | `mop=10` | 需要标量 stride，地址通常难以合并成理想 burst |
| `<mem>_arch_indexed_unordered_insns` | `mop=01` | 索引来自 VRF，允许无序访问语义 |
| `<mem>_arch_indexed_ordered_insns` | `mop=11` | 有顺序约束的 indexed 访问 |
| `<mem>_arch_segment_insns` | `nf != 0` 且不是 whole-register | 一条架构指令访问多个 field，后端会展开 |
| `<mem>_arch_whole_register_insns` | unit-stride whole-register 编码 | 忽略普通 zero-VL bypass，按完整寄存器字节数执行 |
| `<mem>_arch_mask_memory_insns` | mask load/store 编码 | dispatcher 把工作长度换算为 `ceil(vl/8)` 个 byte |
| `<mem>_arch_memory_fields` | 每条指令的 `nf+1` 累加 | 除以架构数得平均 field 数；普通 memory 指令每条贡献 1 |
| `<mem>_arch_requested_elements` | `max(vl-vstart,0)`，segment 再乘 field 数 | 表示架构请求的数据 element 总量 |
| `<mem>_arch_requested_bytes` | 上述 element 乘 dispatcher 已解码的数据 EEW | whole-register 和 mask 指令使用 dispatcher 已改写的 VL/EEW |
| `<mem>_avg_requested_bytes_per_arch_insn` | requested bytes / memory insns | 对比不同地址模式前先校准工作量 |
| `<mem>_arch_memory_exceptions` | dispatcher response 携带 exception 的 memory 指令数 | 非法编码与前端异常会改变后端覆盖率 |
| `load_fault_only_first_insns` | fault-only-first load 数 | 仅 load 有此语义；实际完成元素可能被首个 fault 截短 |
| `<mem>_arch_address_mode_hist_consistent` | 四种 address mode 之和等于 memory 指令数 | 检查 `mop` 分类是否闭合 |

segment、whole-register、mask、fault-only-first 是与 address mode **正交或嵌套**的属性，不能把所有这些计数相加后与 memory 总数比较。例如一个 segment unit-stride load 会同时增加 `arch_unit_stride_insns` 和 `arch_segment_insns`。只有四个 `mop` address-mode bin 是互斥且完备的。

`arch_requested_bytes` 表示指令请求量，而非总线真实传输量。masked-off byte、fault-only-first 提前终止、地址未对齐造成的额外 beat、cache/bus 粒度以及 ROI 切边，都会让它与 AXI transfer/useful bytes 不同。这种差值本身正是后续分析的信号，不能为了“对齐”而丢掉。

#### 27.3.3 opcode 级工作量、配置形状与 latency

类别指标适合总览，但 `fp` 中的 add、FMA、divide、sqrt 延迟完全不同，`valu` 中普通 SIMD 与 reduction 也不能仅靠一个平均值解释。报告因此按 `ara_op_e` 的真实枚举名输出 `op_<OPCODE>_*`；只打印架构、后端或完成计数至少一个非零的 opcode，避免为未出现的操作生成大量空列。

| opcode 指标 | 精确定义 |
|---|---|
| `op_<OP>_arch_insns` | dispatcher 完成的该 opcode 架构指令数 |
| `op_<OP>_zero_vl_nop_insns` | 其中被 zero-VL/空操作路径直接完成的数量 |
| `op_<OP>_backend_uops` | sequencer 接收的该 Ara opcode 后端请求数 |
| `op_<OP>_backend_uops_per_arch_insn` | 后端请求数 / 架构数；观察 segment 展开或内部请求 |
| `op_<OP>_nonzero_backend_coverage_ratio` | 后端请求数 / `(arch-zero_vl)` |
| `op_<OP>_completed_uops`、`completion_per_backend_uop` | 完成数量及完成覆盖率；完整 drain 窗口应为 1 |
| `op_<OP>_requested_elements`、`avg_requested_elements_per_uop` | opcode 的请求 element 总量及平均 VL 形状 |
| `op_<OP>_nominal_element_ops`、`nominal_element_ops_per_rvv_cycle` | 按上一节权重折算的名义工作量及端到端吞吐 |
| `op_<OP>_masked_uops`、`masked_uop_ratio` | 此 opcode 使用 predicate 的后端请求数及比例 |
| `op_<OP>_avg_execution_latency` | 该 opcode 完成事件的 latency 总和 / completed uops |
| `op_<OP>_execution_latency_{le8,9_32,33_128,gt128}` | 与 class 级相同边界的 opcode latency 直方图 |
| `op_<OP>_sew_encoding_<0..3>_uops` | 接收时的 SEW 原始编码分布 |
| `op_<OP>_lmul_encoding_<0..7>_uops` | 接收时的 LMUL 三位原始编码分布，保留整数/分数编码 |

监控器在首次 issue 时把 opcode 与 vector instruction ID 一起保存，完成时再通过 ID 回查，因此 latency 不会错误地归到“完成这一拍正在 issue 的另一条操作”。`VFU_None` 的 scalar move 使用独立 pending opcode，仍遵守同一计数定义。

三个直方图自检字段分别要求 latency bin 之和等于 completed uops、SEW/LMUL bin 之和等于 backend uops；`op_<OP>_window_lifecycle_complete` 要求 accepted uops 等于 completed uops。特别注意：dispatcher 内部 reshuffle 的表面 opcode 是 `VSLIDEDOWN`，所以 opcode 报告中的 `VSLIDEDOWN_backend_uops` 可能包含内部工作；class 报告仍会把它正确分到 `reshuffle`。需要区分软件 slide 与内部 reshuffle 时，应联合读取 class 与 opcode 两层，而不能只看 opcode expansion ratio。

### 27.4 指令生命周期、占用和吞吐

| 指标 | 精确定义 | 如何解读 |
|---|---|---|
| `<class>_issued_insns` | 该类首次到达 `T_issue` 的指令数 | 小于 `exec_insns` 表示窗口结束前仍有已接收但未派发指令，或窗口切边不完整 |
| `<class>_completed_insns` | 到达 `T_done` 的指令数 | 完整 drain 的测量窗口中应等于 `issued_insns` |
| `<class>_accept_to_issue_ratio` | `issued_insns / exec_insns` | 完整窗口应为 1；不是常规吞吐率 |
| `<class>_issue_to_completion_ratio` | `completed_insns / issued_insns` | 完整窗口应为 1；偏低说明尾部仍有在途工作 |
| `<class>_active_cycles` | 至少一条该类指令位于 `vinsn_running_q` 的 wall-clock 周期数 | 同类多条重叠时每周期只加 1 |
| `<class>_inflight_insn_cycles` | 每周期该类在途指令条数之和 | 两条同类指令同拍在途时加 2，可揭示 MLP/ILP |
| `<class>_masked_active_cycles` | 至少一条 masked 的该类指令在途的周期数 | masked 与 unmasked 同拍重叠时仍只加 1 |
| `<class>_active_ratio` | `active_cycles / total_rvv_cycles` | 该类路径在整个 RVV 测量窗口中的占用比例 |
| `<class>_completion_per_rvv_cycle` | `completed_insns / total_rvv_cycles` | 指令级端到端吞吐 |
| `<class>_avg_inflight_when_active` | `inflight_insn_cycles / active_cycles` | 活跃时平均并发的同类指令数 |
| `<class>_active_cycles_per_insn` | `active_cycles / exec_insns` | 保留的兼容字段；窗口切边时可能受已接收但未完成指令影响 |
| `<class>_active_cycles_per_completed_insn` | `active_cycles / completed_insns` | 考虑同类流水重叠后的摊销占用，不是单条精确 latency |
| `<class>_requested_elements_per_active_cycle` | `requested_elements / active_cycles` | 该类活跃周期的 element-slot 摊销吞吐，只在完整窗口中有意义 |
| `<class>_masked_active_ratio` | `masked_active_cycles / active_cycles` | 活跃时间中有 masked 指令参与的比例 |

`avg_inflight_when_active` 高且 `completion_per_rvv_cycle` 也高，通常说明并发被有效利用。前者高而后者不升，说明只是积压了更多指令，需要结合 queue full、operand wait 和 result backpressure 继续定位。

### 27.5 派发等待与执行 latency 分布

总和与平均值：

| 指标 | 定义 |
|---|---|
| `<class>_dispatch_wait_cycles` | 所有已派发指令的 `dispatch_wait` 之和 |
| `<class>_avg_dispatch_wait` | `dispatch_wait_cycles / issued_insns` |
| `<class>_execution_latency_cycles` | 所有已完成指令的 `execution_latency` 之和 |
| `<class>_avg_execution_latency` | `execution_latency_cycles / completed_insns` |
| `<class>_end_to_end_latency_cycles` | 所有已完成指令的 `end_to_end_latency` 之和 |
| `<class>_avg_end_to_end_latency` | `end_to_end_latency_cycles / completed_insns` |

仅看平均值会隐藏长尾，因此同时输出直方图：

| 派发等待 bin | 范围 | 执行 latency bin | 范围 |
|---|---:|---|---:|
| `<class>_dispatch_wait_0_cycles` | 0 | `<class>_execution_latency_le8` | 1–8 |
| `<class>_dispatch_wait_1_4_cycles` | 1–4 | `<class>_execution_latency_9_32` | 9–32 |
| `<class>_dispatch_wait_5_16_cycles` | 5–16 | `<class>_execution_latency_33_128` | 33–128 |
| `<class>_dispatch_wait_gt16_cycles` | >16 | `<class>_execution_latency_gt128` | >128 |

完整窗口中必须满足：

```text
四个 dispatch bin 之和 = issued_insns
四个 execution-latency bin 之和 = completed_insns
avg_end_to_end_latency = avg_execution_latency + avg_dispatch_wait
```

最后一个等式要求分子覆盖的是同一批完成指令；如果测量窗口切在指令生命周期中间，不能用它做严格校验。

### 27.6 sequencer 和派发前端归因指标

| 指标 | 观测条件 | 归因含义 |
|---|---|---|
| `<class>_dispatch_request_cycles` | 当前该类 `ara_req_valid_i=1` | 请求占用 sequencer 输入的周期数；被阻塞时每拍都会累计 |
| `<class>_dispatch_blocked_cycles` | `ara_req_valid_i && !ara_req_ready_o` | 该类请求无法前进的 wall-clock 周期 |
| `<class>_dispatch_blocked_ratio` | `dispatch_blocked_cycles / dispatch_request_cycles` | sequencer 输入端的 backpressure 比例 |
| `<class>_fu_queue_full_cycles` | 被阻塞且任一目标 VFU instruction queue 不 ready | 目标执行队列容量压力；多个目标可同时满 |
| `<class>_mask_queue_full_cycles` | 被阻塞且该指令需要 MASKU、MASKU queue 不 ready | 能区分“主计算 VFU 满”与辅助 MASKU 队列满 |
| `<class>_slide_queue_full_cycles` | 被阻塞且该指令需要 SLDU、SLDU queue 不 ready | reduction 或 slide 可能触发 |
| `<class>_id_pool_full_cycles` | 被阻塞且 `vinsn_running_full=1` | 8 个 vector instruction ID 已用尽 |
| `<class>_response_wait_cycles` | sequencer 位于 WAIT 状态且请求被阻塞 | 常见于需要 scalar/LSU 应答的指令 |
| `<class>_other_dispatch_blocked_cycles` | 被阻塞，但已观测结构原因均不存在 | 排他 residual；若很高说明还应增加新的前端原因探针 |
| `<class>_operand_request_blocked_cycles` | 已生成 `pe_req_o`，但并非所有 lane operand requester ready | 上一条已派发请求尚未被各 lane 完整接收 |
| `<class>_lane_desync_cycles` | sequencer 发现各 lane 对 instruction ID 的 running 状态不同步 | 跨 lane 完成不均衡阻止新指令安全进入 |

`other_dispatch_blocked_cycles` 的 residual 会排除：VFU queue full、ID pool full、WAIT、sequencer block、lane desync，以及一个仍被 operand requester 卡住的既有 `pe_req`。其它具体原因计数允许重叠，不能相加后与 `dispatch_blocked_cycles` 比较。

依赖观测字段如下：

| 指标 | 含义 |
|---|---|
| `<class>_raw_hazard_cycles` | 新请求的 vs1/vs2/v0 依赖尚未完成的旧写者 |
| `<class>_war_hazard_cycles` | 新请求写 vd，而旧指令仍把该寄存器作为源 |
| `<class>_waw_hazard_cycles` | 新请求写 vd，而旧写者仍在途 |
| `<class>_false_hazard_cycles` | sequencer 实现中的 WAR 或 WAW 汇总信号 |
| `<class>_sequencer_block_cycles` | 对无 VRF 源指令或 slide 等不能安全 chaining 的情况，依赖真正阻止派发 |

RAW/WAR/WAW 表示“存在依赖”，并不都表示“发生停顿”。Ara 可以利用 hazard ID 做 chaining，因此不能把 `raw_hazard_cycles` 直接当作损失周期。真正阻塞应优先看 `sequencer_block_cycles` 与 `dispatch_blocked_cycles`。这些细分 hazard 信号由 `FOR_VERIFY` 下的 sequencer 探针提供；关闭相应编译选项时字段保持 0。

#### 27.6.1 七类 VFU instruction queue 的占用分布

`fu_queue_full_cycles` 只在“当前输入请求被阻塞”的拍上说明某个目标 queue 不 ready，无法回答 queue 平时是否长期接近容量。为此，监控器每个 ROI 周期直接采样 sequencer 的七个 `insn_queue_cnt_q`。报告前缀为 `alu`、`mfpu`、`sldu`、`masku`、`load`、`store` 和 `none`；`none` 是 scalar response/move 路径，不表示没有统计。

| 指标 | 含义 |
|---|---|
| `<vfu>_vfu_queue_depth` | 该 VFU 的名义 instruction queue 深度 |
| `<vfu>_vfu_queue_sample_cycles` | ROI 内采样周期总数 |
| `<vfu>_vfu_queue_occupancy_sum` | 每周期 queue count 的累计和 |
| `<vfu>_vfu_queue_avg_occupancy` | occupancy sum / sample cycles |
| `<vfu>_vfu_queue_avg_occupancy_ratio` | occupancy sum / `(sample cycles × nominal depth)` |
| `<vfu>_vfu_queue_avg_occupancy_when_nonempty` | occupancy sum / nonempty cycles |
| `<vfu>_vfu_queue_nonempty_cycles`、`nonempty_ratio` | queue 至少含一个 token 的周期及比例 |
| `<vfu>_vfu_queue_at_capacity_cycles`、`at_capacity_ratio` | count 大于等于名义深度的周期及比例 |
| `<vfu>_vfu_queue_peak_occupancy` | ROI 中出现过的最高 histogram bin |
| `<vfu>_vfu_queue_occupancy_<N>_cycles` | 原始 count 等于 N 的周期数 |
| `<vfu>_vfu_queue_hist_consistent` | 所有 occupancy bin 之和是否等于 sample cycles |

Ara 的 sequencer 有 gold-ticket 机制，某些边界允许 count 短暂到达“名义 depth+1”。因此 `at_capacity` 使用 `count >= depth`，而不是只判断相等；所有 queue 共用覆盖 `0..MaxDepth+1` 的 bin，不会把这个合法瞬态丢掉。此时 `avg_occupancy_ratio` 也可能略大于 1，它不是算术错误。

queue 的分析要与入口阻塞联合进行：平均占用高、at-capacity 高且对应 class 的 `fu_queue_full_cycles` 高，才是容量/消费速度限制的强证据；平均占用高但从不 at-capacity，说明并发在被利用，不应直接判为瓶颈；入口已阻塞但目标 queue 占用低，则应转查 ID pool、WAIT、hazard、lane desync 或 operand requester。

### 27.7 执行阶段的进展、等待和背压

下列字段是 wall-clock cycle 计数。同一周期可能同时存在多条在途指令、多个 lane 和多个原因，但每个类别的每个字段最多增加 1。

| 指标 | 观测语义 | 典型瓶颈 |
|---|---|---|
| `<class>_issue_progress_cycles` | 至少一个相关 lane/VFU 发生输入握手、内部状态/queue 推进、结果产生或指令完成 | 数据通路有可观察进展 |
| `<class>_no_issue_progress_cycles` | 该类仍 active，但本拍没有上述进展 | 粗粒度 liveness 空洞；可能是正常 pipeline latency，也可能是等待 |
| `<class>_issue_progress_ratio` | `issue_progress_cycles / active_cycles` | active 周期中有进展的比例 |
| `<class>_no_issue_progress_ratio` | `no_issue_progress_cycles / active_cycles` | 与 progress ratio 在完整计数逻辑下互补 |
| `<class>_operand_wait_cycles` | 当前 issue 指令有效，但所需 operand/mask 尚未齐全 | VRF bank 冲突、operand queue 空、mask 到达晚、跨 lane 输入未到 |
| `<class>_operand_wait_ratio` | `operand_wait_cycles / active_cycles` | 便于不同运行长度之间比较 |
| `<class>_unit_input_backpressure_cycles` | VMFPU 已向 mul/div/fp 子单元给出 valid，但子单元 ready 低 | 子单元接收带宽或内部串行执行受限 |
| `<class>_unit_input_backpressure_ratio` | 上项除以 `active_cycles` | 输入侧结构瓶颈强度 |
| `<class>_latency_order_stall_cycles` | VMFPU 因不同 latency 结果需保持顺序而停止继续 issue | mul/div/FP 共享 wrapper 的结果顺序约束 |
| `<class>_result_queue_full_cycles` | VALU/VMFPU/SLDU/MASKU 结果 queue 已满，阻止继续产生结果 | 生产快于消费，或下游回写停顿向上传播 |
| `<class>_result_backpressure_cycles` | 结果请求已发出但未获 VRF grant，或送 MASKU 的结果未被接收 | VRF 写端口竞争、MASKU 消费不足 |
| `<class>_result_backpressure_ratio` | 上项除以 `active_cycles` | 输出侧瓶颈强度 |
| `<class>_long_latency_busy_cycles` | VMFPU processing-stage 中存在 mul/div/FP 指令 | 结构占用，不天然代表 stall；div/FP 正常延迟也会使它很高 |
| `<class>_long_latency_busy_ratio` | 上项除以 `active_cycles` | 用于区分“执行单元本身忙”与“前后端等待” |
| `<class>_reduction_cycles` | VALU 或 VMFPU 处于非普通 SIMD reduction 状态 | reduction 专用状态机占用 |
| `<class>_cross_lane_cycles` | SLDU 正在服务整数/FP reduction 的跨 lane 阶段 | reduction tree/跨 lane 传输成本 |
| `<class>_special_path_cycles` | 非 2 次幂 slide 路径，或 MASKU gather/compress 路径处于 issue 活跃状态 | 复杂置换算法本身的占用 |
| `<class>_index_fifo_full_cycles` | gather/compress 活跃且 index/request FIFO 满 | MASKU 索引生产与消费失衡造成的明确停顿 |

为了让 load/store 也能进入同一套顶层归因流程，通用字段在 memory 类中映射到 VLSU 事件：

| 通用 load/store 字段 | VLSU 中的具体来源 |
|---|---|
| `issue_progress_cycles` | addrgen 状态或计数推进、AXI 地址/数据/响应握手、lane operand/result 握手、VLSU 完成 |
| `operand_wait_cycles` | indexed addrgen 等待索引、store 等待数据 operand，或 masked memory 等待 mask |
| `unit_input_backpressure_cycles` | AXI 地址通道或数据通道 valid 而 ready 低 |
| `result_queue_full_cycles` | load result queue full；store 没有同构的 lane result queue |
| `result_backpressure_cycles` | load 写回 VRF 未获 grant；store 的 W/B 通道响应未被接收 |
| `long_latency_busy_cycles` | MMU response 等待、load data 等待、store data/response 等待 |
| `special_path_cycles` | addrgen 正在处理 strided 或 indexed 后端操作 |

这组映射用于跨类别的第一轮比较；最终 memory 归因必须继续查看 27.8.1 的专用计数，因为一个聚合字段不能区分 MMU、AR/AW、R/W/B、mask、operand 和 VRF 写回。

这些原因字段不是 one-hot。例如某拍 FP 指令 A 等 operand，同时 FP 指令 B 已在 processing stage 中，`operand_wait_cycles` 和 `long_latency_busy_cycles` 会同时增加。因而所有原因之和可以大于 `active_cycles`，绝不能用“active 减去各原因之和”计算未知时间。

`no_issue_progress_cycles` 也不等于“浪费周期”。对于多拍 divider 或 FP pipeline，内部正在计算但接口没有握手时，可能同时出现 no-progress 与 long-latency-busy。这种组合更像固有执行 latency；只有 no-progress 同时伴随 operand wait、input backpressure、result queue full 或 result backpressure，才有较强证据指向可优化 stall。

#### 27.7.1 可相加的互斥 primary attribution

原始原因允许重叠，适合保留证据，却不适合直接画一张“100% 周期构成图”。报告另外为每个 active class-cycle 选择且只选择一个 `primary_*` 标签，优先级固定为：

```text
result backpressure
  > result queue full
  > latency/order stall
  > unit input backpressure
  > operand wait
  > long-latency busy
  > special path
  > observable progress
  > unattributed
```

每个标签同时输出 `<class>_primary_<reason>_cycles` 和除以 active cycles 的 `..._ratio`。下游反压排在上游等待之前，是为了在“结果写不出去并继续反压执行入口”的链式现象中优先标记最靠后的已观测阻塞点；`progress` 排在各种状态之后，是因为同一拍可能一边推进一边仍处于特殊/忙状态。严格守恒式为：

```text
sum(all nine primary reason cycles) = active_cycles
```

`<class>_primary_attribution_partition_consistent` 应恒为 1。这个 partition 是**确定性的归类规则，不是因果证明**：优先级改变会改变各块面积，且同类多条在途指令可能分别遇到不同事件。瓶颈结论仍应回看允许重叠的 raw reason、queue occupancy、opcode、lane sample，并通过受控 A/B 实验验证。`primary_unattributed_ratio` 高表示 active 周期没有命中现有探针；它应被视为“需要继续细分”的显式覆盖缺口，而不是默认归入固有 latency。

#### 27.7.2 result queue 的连续占用量

binary 的 `result_queue_full_cycles` 只记录最严重的容量状态。监控器还逐周期扫描 VALU、VMFPU、SLDU、MASKU 和 VLDU 的每个二项 result-queue 槽位，并通过槽位 payload 中的 instruction ID 回查原始执行类别。由此输出：

```text
<class>_result_queue_occupancy_lane_samples
<class>_avg_result_queue_entries_per_active_cycle
```

前者是“所有相关 result queue 中，占用槽位数对周期的积分”：若四个 lane 各有一个该类结果停在 queue 中，一拍增加 4；SLDU/MASKU/VLDU 的中央二维 queue 也按 `slot × lane` 逐项采样。后者用 active cycles 归一化，但没有固定在 0–1，因为一个周期可以同时占用多个 lane、多个槽位，甚至多个模块。

连续占用高而 `result_queue_full`/`result_backpressure` 低，通常表示 queue 正常承担流水解耦；连续占用、full 与 backpressure 同时升高，才说明结果排出路径形成积压。store 和 `move_from_vec` 没有同构的 lane result queue，得到 0 是结构事实，不是监控遗漏。

### 27.8 各模块的实际探针来源

| 模块 | 进展探针 | 输入等待/背压 | 输出等待/背压 | 特殊状态 |
|---|---|---|---|---|
| Dispatcher | response handshake、配置结果、zero-VL bypass | request 保持、Ara ready 低、等待 idle | accelerator response 未完成 | config、RESHUFFLE、VL/SEW/LMUL 变化 |
| Sequencer | accept、首次 `pe_req`、ID 完成、scalar response | VFU queue、ID pool、operand requester、hazard/lane desync | WAIT/scalar response | 每 ID 类别与 masked 生命周期 |
| VALU | `valu_valid` | issue valid 但 `valu_valid=0`，并排除 result queue full | `result_queue_full`；`alu_result_req_o` 未获 grant；mask result 未被 MASKU 接收 | `alu_state_q != NO_REDUCTION` |
| VMFPU | `vmul/vdiv/vfpu` 的 valid-ready handshake，以及 `unit_out_valid` 成功进入 result queue | `operands_valid=0`；子单元 input valid 但 ready 低；`latency_stall` | result queue full；`mfpu_result_req_o` 未获 grant；mask result 未被 MASKU 接收 | processing valid、`mfpu_state_q` reduction 状态 |
| SLDU | issue/commit counter、输入/输出/VRF pointer、result valid/count 或主状态机发生变化 | issue valid、无内部进展且 result queue 未满 | result queue full；任一 lane result request 未获 grant | reduction 跨 lane、`is_stride_np2` |
| MASKU | 输入/输出计数推进、gather FIFO push/pop、VRF/scalar 输出有效 | issue valid、无进展，且非 result/index FIFO full | result queue full；任一 lane writeback request 未获 grant | gather/compress 活跃、index/request FIFO full |
| VLSU/Addrgen | addrgen 状态/计数、queue push/pop、ack、AXI/VLSU 完成 | index/store operand、mask、addrgen queue、MMU/AXI wait | load result queue、VRF grant、store W/B channel | unit/strided/indexed、load/store、exception |

这里使用的是 testbench 的层次化只读探针，不改变 RTL 数据路径，也不会综合进硬件。优点是无需为研究指标改动每个模块端口；代价是内部信号改名或层次调整后，testbench 也要同步更新。

#### 27.8.1 VLSU、MMU 与 AXI 专用指标

load/store 的专用报告按流水路径组织。以下 `<mem>` 可替换为 `load` 或 `store`。

地址生成阶段：

| 指标 | 观测逻辑 | 归因含义 |
|---|---|---|
| `<mem>_addrgen_active_cycles` | addrgen 主状态、AXI addrgen 状态或 addr queue 非空 | 地址生成子系统占用时间 |
| `<mem>_addrgen_progress_cycles` | 状态/索引计数变化、queue push/pop、ack 或 memory 握手 | 活跃拍中至少有一个可观察进展 |
| `<mem>_addrgen_no_progress_cycles` | active 且无上述进展 | 地址路径空洞；需结合具体 wait 判断是否可优化 |
| `<mem>_addrgen_progress_ratio` | progress / active | 地址路径活跃质量 |
| `<mem>_addrgen_operand_wait_cycles` | indexed op 在取 index 状态但 lane index 未全部 valid | 索引从 VRF/operand requester 到达过慢 |
| `<mem>_addrgen_queue_full_cycles` | AXI addrgen queue full | 地址产生快于下游消费 |
| `<mem>_core_store_pending_wait_cycles` | addrgen 等待 core store pending 边界 | 标量核 store 与向量 memory 顺序协调成本 |

地址翻译阶段：

| 指标 | 观测逻辑 | 归因含义 |
|---|---|---|
| `<mem>_mmu_request_cycles` | `mmu_req_o` 有效的周期 | 翻译请求占用；valid 多拍会累计多拍 |
| `<mem>_mmu_wait_cycles` | MMU request 有效但 `mmu_valid_i=0` | 翻译响应等待时间 |
| `<mem>_mmu_dtlb_hit_count` | request 周期采样到 DTLB hit | 与 request cycles 的比值是接口周期采样意义上的 hit ratio |
| `<mem>_mmu_response_count` | `mmu_valid_i` 且 addrgen 有在途工作 | MMU 返回次数 |
| `<mem>_mmu_exception_count` | MMU response 携带 exception | 翻译/权限类异常 |

AXI 地址、数据和响应阶段：

| 指标 | load 对应通道 | store 对应通道 | 解释 |
|---|---|---|---|
| `<mem>_axi_address_valid_cycles` | AR valid | AW valid | 地址请求存在的周期 |
| `<mem>_axi_address_fire_count` | AR valid&&ready | AW valid&&ready | 实际地址握手次数 |
| `<mem>_axi_address_backpressure_cycles` | AR valid&&!ready | AW valid&&!ready | 下游地址入口反压 |
| `<mem>_axi_data_valid_cycles` | R valid | W valid | 数据通道存在有效 beat 的周期 |
| `<mem>_axi_data_fire_count` | R valid&&ready | W valid&&ready | 实际传输 beat 数 |
| `<mem>_axi_data_backpressure_cycles` | R valid&&!ready | W valid&&!ready | 消费方未 ready |
| `<mem>_axi_data_wait_cycles` | load 已 issue/有地址请求但 R 未 valid | store 已 issue/有地址请求但 W 未 valid | memory 或本地供数尚未产生数据 |
| `<mem>_axi_response_valid_cycles` | R valid&&last | B valid | 一个 burst 的最终响应可见 |
| `<mem>_axi_response_fire_count` | R last 握手 | B 握手 | burst/写响应完成数 |
| `<mem>_axi_response_wait_cycles` | load 当前不单列额外等待 | store commit 等待 B valid | store completion 被写响应延迟 |

AXI 并发度和 request-to-response latency：

| 指标 | 精确定义 | 如何解读 |
|---|---|---|
| `<mem>_axi_outstanding_sample_cycles` | ROI 内对 outstanding gauge 的采样周期数 | 正常应等于该报告窗口的周期数 |
| `<mem>_axi_outstanding_cycle_sum` | 每周期未完成 burst 数的累计和 | 并发度的积分 |
| `<mem>_axi_avg_outstanding` | outstanding sum / sample cycles | memory-level parallelism 的直接观测 |
| `<mem>_axi_outstanding_nonzero_cycles`、`nonzero_ratio` | 至少有一个地址已握手但最终响应未完成的周期 | memory 系统被占用的时间比例 |
| `<mem>_axi_peak_outstanding_bin` | 最高出现的并发 bin；8 表示 8+ | 识别瞬时峰值，不等于精确最大值超过 8 的部分 |
| `<mem>_axi_outstanding_<0..8>_cycles` | 并发度直方图，最后一项聚合 8 及以上 | 判断平均值是否由少数尖峰造成 |
| `<mem>_axi_request_latency_samples` | 已成功配对的最终响应数量 | load 是 RLAST，store 是 B |
| `<mem>_axi_request_latency_cycles` | 所有已配对 burst 的地址到最终响应 latency 之和 | 地址握手拍和响应拍都计入，故公式带 `+1` |
| `<mem>_axi_avg_request_to_response_latency` | latency sum / samples | burst 级端到端 memory latency，不是每 beat latency |
| `<mem>_axi_request_latency_{le8,9_32,33_128,gt128}` | burst latency 分布 | 区分稳定延迟和长尾 |
| `<mem>_axi_tracking_overflows/underflows` | 16 项时间戳 FIFO 满时仍接收地址，或无可配对请求时收到响应 | 任一非零都会降低 latency 归因可信度 |

tracker 对 load 从 AR handshake 计到对应 burst 的 RLAST handshake，对 store 从 AW handshake 计到 B handshake；读、写各有独立的 16 项 FIFO。当前 Ara 接口在每个方向按请求顺序返回最终响应，所以 FIFO 配对成立；如果以后引入多 AXI ID 且允许跨 ID 乱序返回，必须改为按 ID/transaction tag 关联，不能继续假定 FIFO 顺序。地址和响应同拍时仍按旧队首计算 latency，新请求可复用刚释放的最后一个槽位。

自检字段中，`axi_outstanding_hist_consistent` 要求并发直方图覆盖所有采样拍，`axi_latency_hist_consistent` 要求 latency bin 覆盖所有配对样本，`axi_tracking_consistent` 要求 overflow/underflow 都为 0，`axi_response_latency_coverage_consistent` 要求每个窗口内 response 都被 latency tracker 或显式 underflow 覆盖。`axi_request_response_window_complete` 进一步要求本 ROI 中地址数、最终响应数和 latency 样本数相等；短 ROI 跨事务边界时它可以合理为 0，完整 drain 的性能窗口中则应为 1。

字节量指标：

| 指标 | 定义 | 注意事项 |
|---|---|---|
| `<mem>_axi_transfer_bytes` | 每个握手 beat 按 AXI `size` 累加总线占用 byte | 是总线事务量，不等于有效 payload |
| `<mem>_axi_useful_bytes` | store 用 WSTRB 的 1 数；load 用获 VRF grant 的 result byte-enable 的 1 数 | load 以实际成功写回 lane 的 byte 为有效 |
| `<mem>_axi_bus_efficiency` | useful / transfer | 低值说明窄访问、未对齐、mask、tail 或其它 over-transfer；分母为 0 时安全输出 0 |

VLDu/VSTu 与 VRF 接口：

| 指标 | 精确定义 | 典型问题 |
|---|---|---|
| `<mem>_mask_wait_cycles` | masked memory issue 有效但尚无 mask word | MASKU/mask operand 供给延迟 |
| `<mem>_vlsu_operand_wait_cycles` | load indexed 地址 operand 或 store data operand 未齐 | VRF bank conflict、operand queue、lane 不同步 |
| `<mem>_vlsu_result_queue_full_cycles` | load result queue full | memory 返回快于 VRF 写回 |
| `<mem>_vlsu_result_backpressure_cycles` | load result 未获 VRF grant；store W/B 被反压 | 下游消费瓶颈 |
| `<mem>_operand_handshake_lane_samples` | 每 lane 的 index/store operand handshake 总数 | 是 transaction sample，不是 wall cycle |
| `<mem>_result_request_lane_samples` | load 各 lane 写回 request 总数 | 判断返回数据分布和写回请求量 |
| `<mem>_result_handshake_lane_samples` | load 各 lane request&&grant 总数 | 实际成功写回次数 |
| `<mem>_result_backpressure_lane_samples` | load 各 lane request&&!grant 总数 | 定位 wall-cycle 指标隐藏的 lane 竞争 |
| `<mem>_vlsu_completion_count` | `load_complete`/`store_complete` 脉冲数 | 应与完整窗口的后端 completed 数对应 |
| `<mem>_vlsu_exception_count` | addrgen ack 携带 exception | VLSU 后端异常，与 dispatcher 编码异常是不同层次 |

读这些指标时沿数据流逐级排除。例如 addrgen no-progress 高且 addrgen operand-wait 高，先看索引/VRF；MMU wait 高而 AXI address fire 少，先看翻译；地址 fire 足够但 load data wait 高，先看 memory latency；R beat 已到而 result queue/full 或 VRF backpressure 高，则瓶颈已经移到 load 写回。

### 27.9 wall-cycle 与 lane-sample 的区别

wall-cycle 指标适合回答“整个机器这一拍有没有发生某件事”，但它会隐藏 lane 不均衡。为此，VALU 与 VMFPU 路径还输出以下通用 lane-sample：

- `<class>_issue_progress_lane_samples`
- `<class>_operand_wait_lane_samples`
- `<class>_unit_input_backpressure_lane_samples`
- `<class>_latency_order_stall_lane_samples`
- `<class>_result_queue_full_lane_samples`
- `<class>_result_backpressure_lane_samples`
- `<class>_long_latency_busy_lane_samples`
- `<class>_result_queue_occupancy_lane_samples`

如果 4 个 lane 在同一拍都等待 operand，则 wall-cycle 的 `operand_wait_cycles` 加 1，而 `operand_wait_lane_samples` 加 4。由此：

```text
avg_progress_lanes_per_active_cycle
  = issue_progress_lane_samples / active_cycles
```

该值的范围通常为 0 到 `NrLanes`。接近 `NrLanes` 表示活跃拍中多数 lane 同时推进；明显偏低而 lane-wait sample 很高，说明 lane 间负载或供数不均。`move_to_vec` 使用 VALU，所以能出现通用 event lane sample；`move_from_vec` 的 scalar response、SLDU、MASKU 和 reshuffle 是集中式控制路径，相应 progress/wait/backpressure lane-sample 可以为 0，应使用 wall-cycle/lifecycle 指标。下面单独说明的 result-queue occupancy 不受这句话限制。

load/store 不复用上述通用 lane-sample，因为其“进展”同时横跨 addrgen、MMU 和 AXI，强行压成 compute lane sample 会产生误导。VLSU 报告另有 `operand_handshake_lane_samples`、`result_request_lane_samples`、`result_handshake_lane_samples` 和 `result_backpressure_lane_samples`。这些专用字段才用于分析 memory lane 不均衡。

lane-sample 中的 progress 是布尔采样：同一 lane 同一拍即使既接受输入又产生输出也只加 1。因此它适合衡量 lane 覆盖度，不是精确 transaction 数。`result_queue_occupancy_lane_samples` 是例外：它按每个有效 slot 累加，不是布尔 OR，既覆盖 lane-local VALU/VMFPU，也覆盖中央 SLDU/MASKU/VLDU 的二维结果队列；应按 27.7.2 的 queue-residency 语义解读。

### 27.10 必做的计数守恒检查

在开始归因之前，先做以下自检。任何一项不成立，都应先检查测量窗口或监控逻辑，而不是直接解释瓶颈。

1. 对所有出现过的后端类别，在完整接收并 drain 的窗口中：

   ```text
   exec_insns = issued_insns = completed_insns
   ```

2. 两组直方图分别守恒：

   ```text
   sum(dispatch_wait_hist) = issued_insns
   sum(execution_latency_hist) = completed_insns
   ```

3. 每类活跃周期满足：

   ```text
   issue_progress_cycles + no_issue_progress_cycles = active_cycles
   inflight_insn_cycles >= active_cycles
   masked_active_cycles <= active_cycles
   ```

   互斥主因还必须满足：

   ```text
   sum(primary_result_backpressure ... primary_unattributed) = active_cycles
   ```

   对应 `<class>_primary_attribution_partition_consistent` 必须为 1。

4. 工作负载形状满足：

   ```text
   masked_insns <= exec_insns
   reduction_insns <= exec_insns
   special_path_insns <= exec_insns
   sew8 + sew16 + sew32 + sew64 = exec_insns   // 当前合法 ELEN=64 工作负载
   ```

   每个已出现 opcode 还应满足：

   ```text
   sum(opcode execution-latency bins) = opcode completed_uops
   sum(opcode SEW bins) = opcode backend_uops
   sum(opcode LMUL bins) = opcode backend_uops
   opcode backend_uops = opcode completed_uops // 仅完整 drain 窗口
   ```

5. 明确的子原因应满足：

   ```text
   mask_queue_full_cycles <= fu_queue_full_cycles
   slide_queue_full_cycles <= fu_queue_full_cycles
   index_fifo_full_cycles <= special_path_cycles
   ```

6. 某类没有指令时，其生命周期、工作量、执行和比例字段应全为 0，且不得出现 NaN/Inf。所有 ratio 使用安全除法，分母为 0 时输出 `0.000` 或 `0.000000`。

7. 架构层分类应闭合：

   ```text
   frontend_unclassified_arch_insns = 0
   config_subtype_hist_consistent = 1
   vset_sew_hist_consistent = 1
   load_arch_address_mode_hist_consistent = 1
   store_arch_address_mode_hist_consistent = 1
   ```

   `frontend_arch_exceptions` 可以非零，但此时不要期待异常指令都创建后端请求。`frontend_unclassified_arch_insns` 非零则表示 Ara 新增了未进入分类器的 opcode，或监控时序取到了错误的 request，必须先修监控覆盖。

8. 普通非 segment、非异常且非 zero-VL 的完整窗口，通常满足：

   ```text
   arch_insns - zero_vl_nop_insns = exec_insns
   ```

   segment 会使右侧大于左侧；dispatcher 内部 reshuffle 只有后端数；ROI 边界和 exception 也会破坏这个简单等式。因此报告输出 ratio 而不是把它作为所有 workload 的硬断言。

9. VLSU 内部守恒：

   ```text
   addrgen_progress_cycles + addrgen_no_progress_cycles = addrgen_active_cycles
   backend completed_insns = vlsu_completion_count      // 完整 drain、无跨窗口边界
   ```

   对应报告字段是 `<mem>_addrgen_partition_consistent` 和 `<mem>_backend_vs_vlsu_completion_consistent`。

10. 每个 VFU queue 的 occupancy histogram 之和必须等于 sample cycles。AXI tracker 则至少满足：

    ```text
    sum(outstanding bins) = outstanding sample cycles
    sum(request-latency bins) = request-latency samples
    request-latency samples + tracker underflows = response fire count
    tracker overflows = tracker underflows = 0
    ```

    完整 drain 且不跨 AXI 边界的 ROI 还应满足 address fire、response fire 和 request-latency samples 三者相等。短窗口只要跨过一个 burst，该完整性等式就可能不成立，但 histogram/tracker 的内部守恒仍应成立。

11. 字节数只在受控条件下做强等式。对全有效、无异常、完整 drain、对齐且无 over-transfer 的简单 unit-stride workload，可比较：

    ```text
    arch_requested_bytes ~= backend_requested_bytes ~= axi_useful_bytes
    ```

    这里故意使用 `~=` 而不是无条件等号。segment 展开、mask、tail、fault-only-first、总线粒度和 snapshot 边界都可能造成合理差异；`axi_transfer_bytes` 还会包含非 useful byte。先用三个层次定位差值从哪一段出现，再判断是正常语义还是效率问题。

报告还直接输出以下布尔自检字段，便于批量脚本拒绝不可信样本：

- `<class>_window_lifecycle_complete`：`exec=issued=completed` 时为 1。它为 0 不一定是硬件错误，也可能只是 ROI 未 drain。
- `<class>_dispatch_hist_consistent`：四个 dispatch bin 之和等于 `issued_insns` 时为 1。
- `<class>_execution_hist_consistent`：四个 execution-latency bin 之和等于 `completed_insns` 时为 1。
- `<class>_active_partition_consistent`：progress 与 no-progress 之和等于 active 时为 1。
- `<class>_primary_attribution_partition_consistent`：九个互斥 primary 原因完整且不重计 active 周期时为 1。
- `op_<OP>_{execution,sew,lmul}_hist_consistent`：opcode 的 latency/SEW/LMUL 直方图分别覆盖对应母数时为 1。
- `op_<OP>_window_lifecycle_complete`：该 opcode 的 backend uops 全部完成时为 1。
- `<vfu>_vfu_queue_hist_consistent`：queue occupancy bin 覆盖全部采样周期时为 1。
- `<mem>_addrgen_partition_consistent`：addrgen progress 与 no-progress 覆盖全部 active 周期时为 1。
- `<mem>_backend_vs_vlsu_completion_consistent`：后端 lifecycle 与 VLSU completion 脉冲数相等时为 1。
- `<mem>_axi_{outstanding,latency}_hist_consistent`：AXI 并发和 burst latency 直方图闭合时为 1。
- `<mem>_axi_tracking_consistent`、`axi_response_latency_coverage_consistent`：时间戳 FIFO 无错误，且 response 都有配对/显式 underflow 解释时为 1。
- `<mem>_axi_request_response_window_complete`：本 ROI 的 address、最终 response 与 latency 样本数相等时为 1；它是窗口完整性检查，不是所有短窗口都必须成立。
- `config_subtype_hist_consistent`、`vset_sew_hist_consistent`、`<mem>_arch_address_mode_hist_consistent`：前端分类直方图闭合时为 1。

histogram、partition、coverage 类 consistency 字段只验证监控内部守恒；它们全为 1 仍不能代替 lifecycle complete、ROI drain 和工作负载对齐检查。

### 27.11 瓶颈归因顺序

建议按下面顺序分析，而不是从某个最大的数字直接下结论。

| 步骤 | 首先比较 | 若异常，再查看 | 可能结论 |
|---|---|---|---|
| 1. 架构工作量对齐 | arch class/opcode mix、config 数、memory address mode/fields/requested bytes | VL、SEW、LMUL、masked、nominal element ops | 两次运行并非等价工作负载，暂不能比较性能 |
| 2. 架构到后端展开 | class/opcode zero-VL、backend uops per arch、nonzero coverage、reshuffle 数 | segment fields、异常、vtype/EEW 变化 | 指令消失、展开或内部搬运解释了部分周期差异 |
| 3. 窗口完整性 | accept-to-issue、issue-to-completion、直方图与 completion 守恒 | ROI 起止点、未 drain 指令 | 跨窗口事件使 latency/吞吐失真 |
| 4. 配置序列化 | config blocked ratio、WAIT_IDLE/backend busy、reshuffle wait | vset 频率、VL/vtype change、LMUL/SEW hist | 重配置或布局转换阻断流水 |
| 5. 后端供给 | dispatch blocked ratio、avg dispatch wait、七类 VFU queue occupancy/at-capacity | FU/mask/slide queue full、ID pool、WAIT、other residual | sequencer、队列容量或消费速度限制 |
| 6. 并发能力 | avg inflight、completion per RVV cycle | ID pool full、queue full | 并发不足，或并发只形成积压 |
| 7. 操作数供给 | operand wait ratio、lane wait samples | VRF bank conflict、operand requester blocked、masked ratio | VRF/operand queue/mask 供数瓶颈 |
| 8. 执行单元入口 | unit input backpressure、latency order stall、primary attribution | opcode/SEW/LMUL、long-latency busy | mul/div/fp 子单元吞吐或顺序约束 |
| 9. 固有执行时延 | no-progress 高、long-latency-busy 高，其它 wait/backpressure 低 | execution latency histogram | divider/FP 固有 latency，未必是可消除 stall |
| 10. 结果排出 | result queue 连续占用、full、backpressure、lane samples | VRF conflict、MASKU 消费、写回 grant | 正常 buffering 或写回带宽/下游消费不足 |
| 11. Memory 地址与翻译 | addrgen progress/operand/queue、MMU wait/hit | indexed/strided mix、DTLB、core-store wait | 地址生成或翻译限制 |
| 12. Memory 总线 | AXI address/data/response wait/backpressure、outstanding、request latency | latency 长尾、beat/response、byte/cycle、bus efficiency | 地址入口、并发度、返回延迟、写响应或带宽问题 |
| 13. 跨 lane/特殊算法 | reduction、cross-lane、special path | slide queue、index FIFO、VLSU special path | reduction、NP2 slide、gather/compress、strided/indexed 成本 |
| 14. lane 平衡 | avg progress lanes、compute 与 VLSU lane samples | 每 lane VRF conflict/handshake | lane 负载不均或局部资源冲突 |

几个常见组合的解释：

- `dispatch_blocked_ratio` 高、`fu_queue_full_cycles` 高：前端已经有指令，但目标 VFU queue 容量或消费速度不足。
- VFU queue 平均占用和 at-capacity 都高，同时 dispatch queue-full 高：容量/消费速度瓶颈证据完整；只有平均占用高而 at-capacity 为 0，更可能是健康的并发利用。
- `dispatch_blocked_ratio` 高、`id_pool_full_cycles` 高：全局最多 8 条在途指令的 ID 容量成为限制，通常还应看到较高的 `avg_inflight_when_active`。
- `operand_wait_ratio` 高、VRF bank conflict 也高：强证据指向 VRF/operand requester；可改变寄存器映射做 A/B 验证。
- `unit_input_backpressure_cycles` 高：数据已经到达 VMFPU wrapper，但 mul/div/fp 子单元不能接收，属于执行单元入口限制。
- class 级 FP latency 长尾明显，而 opcode 拆分后仅 `VFDIV/VFSQRT` 长尾：类别平均值主要由指令 mix 解释；若同 opcode、同 SEW/LMUL 仍恶化，才转向微架构原因。
- `result_queue_full_cycles` 与 `result_backpressure_cycles` 同时高：下游写回慢导致 queue 堆满，并继续反压前端。
- result-queue occupancy 高但 full/backpressure 低：queue 在正常吸收生产/消费相位差，不应仅凭“占用高”判为瓶颈。
- `long_latency_busy_ratio` 高但 input/output backpressure 低：更可能是算法或 pipeline 固有占用；优化方向是增加并发覆盖 latency，而非扩大 queue。
- `special_path_cycles` 高且 `index_fifo_full_cycles` 高：gather/compress 的索引请求通道不平衡；如果 index FIFO 不满，则主要是特殊路径固有处理成本。
- `issue_progress_ratio` 不低但 `avg_progress_lanes_per_active_cycle` 低：机器几乎每拍“有某个 lane”在动，但多数 lane 没同时工作，wall-cycle 指标掩盖了 lane 利用率问题。
- `config_wait_backend_busy_cycles` 高且配置次数多：软件在旧向量工作尚未 drain 时频繁改变配置，形成明确序列化点。
- `reshuffle_exec_insns` 或 `config_wait_reshuffle_cycles` 高：寄存器实际 EEW 与新操作期望布局频繁不一致，应检查 vtype/SEW 变换和寄存器复用策略。
- `addrgen_operand_wait_cycles` 高：indexed memory 的索引供给不足；若同时 `operand_handshake_lane_samples` 分布稀疏，更像 VRF/lane 供数问题。
- AXI address backpressure 低而 `axi_data_wait_cycles` 高：地址很快被接受，但数据返回或 store 数据准备较慢。
- AXI request latency 高、avg outstanding 长期接近 1：并发不足以覆盖 memory latency；latency 高但 outstanding 也高且 useful bytes/cycle 已接近接口上限，则更像外部带宽/延迟限制。
- `axi_bus_efficiency` 低且 transfer bytes 明显大于 useful bytes：优先检查窄/未对齐访问、mask/tail 和地址模式，而不是仅用指令数解释带宽。
- `primary_unattributed_ratio` 高：现有探针没有覆盖大量 active 周期；先回到 waveform 补充分段状态，不能把 residual 自动解释为硬件固有 latency。

### 27.12 实测示例应如何读

以 4-lane、VLEN=1024 的 `vsaxpy` 为例，real 与 ideal dispatcher 回归均观测到：32 条架构 FP 指令、64 条架构 load、32 条架构 store，以及 32 条 `vsetvli`；`frontend_unclassified_arch_insns=0`。在这个 workload 中没有 segment、zero-VL 或异常，所以三类执行指令的架构数与后端请求数一一对应。

load 的架构 requested bytes、后端 requested bytes 和 AXI useful bytes 均为 8192；store 三者均为 4096。load/store lifecycle、直方图、active partition、addrgen partition 和 backend-vs-VLSU completion consistency 均闭合。这一步只证明测量口径在简单 unit-stride workload 上对齐，尚未证明性能没有瓶颈。

opcode 层进一步看到 `VFMACC` 的 arch/backend/completed 都是 32，请求 1024 个 element，而名义 element ops 为 2048，恰好体现 fused multiply-add 权重 2；`VLE` 为 64 条、`VSE` 为 32 条，memory 的 nominal element ops 按定义为 0。三种已出现 opcode 的 execution、SEW、LMUL histogram 都闭合，说明 class 平均 latency 可以继续安全下钻到具体操作。

一次 ideal-dispatcher 回归中，load VFU queue 平均占用 1.381、峰值 bin 2、at-capacity 为 0；MFPU 平均占用 0.573、峰值 1。这说明 workload 确实利用了队列并发，但没有证据表明名义 queue 深度被顶满。load AXI 平均 outstanding 为 0.707、峰值 bin 3、平均 AR-to-RLAST latency 为 15.031 cycles；store 分别为 0.510、2 和 20.939 cycles。两个方向的 tracker overflow/underflow 都为 0，outstanding/latency histogram 均闭合。这里的具体数值用于示范阅读关系，修改 memory model、总线参数或 ROI 后应以新报告为准。

随后才比较 active/progress/no-progress 与细分等待。例如 FP 的 `long_latency_busy` 高，而 unit-input、result-queue 和 result-backpressure 低，支持“FP processing latency 与 operand 到达节奏主导”，不支持“FP 子单元入口 ready 不足”或“结果写回堵塞”。`operand_wait` 与 `long_latency_busy` 会重叠，不能把两者相加说成总损失。要把相关性升级为因果结论，仍需改变寄存器映射、独立指令并发、memory 地址模式或总线条件做 A/B 实验。

互斥 primary partition 在所有类别上闭合为 1，可直接用于第一轮面积排名；但同一次回归仍有部分 FP/load/store active 周期进入 `primary_unattributed`。这恰好说明 partition 的价值不是“强行解释一切”，而是把未覆盖区间量化出来，提醒后续结合 waveform 或增加更细 pipeline-state 探针。

### 27.13 snapshot 测量窗口的边界效应

所有原始计数器都是单调累加值。报告沿用现有机制，在 ROI start/end 各取一次 snapshot，再逐字段相减。这样 real dispatcher 与 ideal dispatcher 使用同一套指标，也不会要求 kernel 直接控制监控器。

但跨边界指令会造成以下现象：

- 指令在 ROI 前已接收、ROI 内完成：`completed_insns` 增加，但 `exec_insns` 不增加。
- 指令在 ROI 内接收、ROI 后完成：`exec_insns` 增加，但 `completed_insns` 不增加。
- 指令在 ROI 前已在途：ROI 内会累计 active/wait/busy 周期，却没有对应的 requested elements。
- latency sum 在完成时一次性记账，因此一条跨窗口指令的完整 latency 可能全部落入完成所在窗口。
- opcode latency 与 class latency 一样在完成时一次性记账，所以 opcode lifecycle complete 也会受跨边界影响。
- AXI burst 或 VLSU request 跨越 snapshot：address、data、response、useful byte 与 completion 可能落在不同窗口；`axi_request_response_window_complete` 因而可能为 0。
- AXI 时间戳 tracker 从仿真 reset 后持续运行，不会在 ROI snapshot 处清空；因此跨 ROI 的 response 仍可得到完整 request-to-response latency，但完整 latency 会全部记入 response 所在窗口，且该窗口的 address/response 数不再相等。
- segment 架构 response 与其多个后端 uop 不在同一侧：短窗口中的 expansion ratio 可能瞬时失真。

用于严格 latency、吞吐和字节效率分析的 ROI 应满足：开始前所有后端类别与 VLSU/AXI 均无在途事务，结束 snapshot 前也已 drain；配置请求也不能悬在窗口边界。若 kernel API 无法保证 drain，至少先检查 lifecycle、直方图、addrgen 和 VLSU completion 守恒，再决定哪些指标仍可使用。只做长时间稳态分析时，边界误差可以随窗口增大而摊薄，但不能假设它自动消失。

### 27.14 报告、批量采集与后续扩展

real 和 ideal dispatcher 的性能报告都会打印上述字段。字段采用统一格式：

```text
[PERF] <class>_<metric>: <value>
```

现有批量脚本会收集所有 `[PERF] key : value` 或 `[PERF] key: value`，不需要维护固定 CSV 列表。建议数据分析脚本至少自动执行本节的守恒断言，并保留以下四组列：

- 工作负载归一化列：架构 class/opcode、zero-VL、配置、memory address mode/field/byte、后端 requested elements/uops、nominal ops、SEW/LMUL。
- 结果列：RVV cycles、class/opcode completion throughput、平均/分布 latency、AXI useful/transfer bytes、bytes/cycle 与 bus efficiency。
- 原因列：config/reshuffle、dispatch、VFU queue、operand、input、ordering、result queue residency/backpressure、primary attribution、addrgen/MMU/AXI outstanding/latency、cross-lane 和 lane-sample。
- 可信度列：所有 lifecycle、histogram、active/primary partition、queue、AXI tracker、address-mode、config、addrgen 与 VLSU consistency 字段。

当前分类覆盖 Ara `ara_op_e` 的全部后端 RVV 操作，并把配置指令和内部 reshuffle 放在正确的独立层次；opcode 报告已经可以区分 `VFDIV`、`VFMACC` 等具体操作。`frontend_unclassified_arch_insns` 应长期保持 0；今后新增 opcode 时，该字段会直接暴露 class 分类遗漏，opcode 数组上界和枚举名报告也必须同步检查。mask 有效 bit 密度和按执行类别归因的 VRF 等待已经在下一节补齐。后续若要继续细化，优先增加 indexed memory 的 index EEW、AXI ID/地址区域以及 cache/DRAM 内部事件，同时保持现有 class/opcode 字段不变，以免破坏跨版本汇总可比性。

这套指标已经覆盖架构工作量、后端展开、sequencer 容量、执行入口/内部/出口、result queue、地址生成、MMU 和 AXI 边界，足以进行系统化的第一轮瓶颈定位，但仍有清晰边界：它没有直接看到外部 cache/DRAM row-buffer 或仲裁内部原因；nominal ops 不等于门级活动；primary attribution 是观测优先级而不是反事实因果；它也不替代频率、面积、功耗和时序收敛分析。遇到高 `primary_unattributed`、AXI latency 已异常但总线内部不可见，或同 opcode/SEW/LMUL 仍出现无法解释的差异时，应增加更靠近可疑边界的探针，而不是继续堆叠顶层相关性字段。

完成一次瓶颈归因时，最终结论至少应包含四句话：软件发出了什么架构工作；它展开成多少后端工作；周期或字节在哪一级首次出现异常；通过什么受控 A/B 实验验证了原因。只有“某个 counter 最大”不能构成充分结论。

### 27.15 强化指标：mask 密度、VRF 供数和深层执行状态

仅统计 `masked_insns` 无法区分“mask 几乎全 1”和“mask 极稀疏”。监控器现在在 MASKU 将 v0 展开成 per-byte mask packet 时统计实际元素：

| 指标 | 含义 |
|---|---|
| `<class>_predicate_packets` | MASKU 生成的 predicate packet 数 |
| `<class>_predicate_elements` | packet 中属于 VL 的有效元素总数，不包含最后一包的 tail |
| `<class>_predicate_active_elements` | 上述元素中 v0=1 的数量 |
| `<class>_predicate_active_ratio` | 实际有效 mask 密度 |
| `predicate_density_bin_0..5_packets` | 0%、(0,25]%、(25,50]%、(50,75]%、(75,100)%、100% 六档 packet 分布 |

`VMADC/VMSBC` 使用 v0 作为 carry/borrow 输入，不属于 predicate density，明确排除。`predicate_hist_consistent` 验证六个 bin 之和等于 packet 数，`predicate_active_le_total_consistent` 验证 active element 不超过有效 element。

VRF 读供数不再只显示整个 lane/bank 的累计冲突，而是按 instruction ID 回查执行类别，并且纳入 snapshot ROI：

| 指标 | 精确事件 | 优化含义 |
|---|---|---|
| `vrf_read_request_lane_samples` | operand requester 真正向某 bank 发请求 | 读需求量基线 |
| `vrf_read_grant_lane_samples` | 请求当拍得到 arbiter grant | 有效供数 |
| `vrf_bank_conflict_lane_samples` | 已发 bank request 但未 grant | 同 bank 仲裁冲突，可优化寄存器映射/banking |
| `vrf_hazard_stall_lane_samples` | requester 活跃、queue 可接收，但依赖 hazard 阻止请求 | 数据相关或 chaining 时机 |
| `operand_queue_backpressure_lane_samples` | requester 活跃但目标 operand queue 不 ready | queue 容量或下游消费速度 |

前三者满足：

```text
vrf read requests = vrf read grants + vrf bank conflicts
```

对应的 `vrf_request_partition_consistent` 应为 1。注意这些是 lane-requester sample，同一 wall cycle 可以增加多次；它们适合计算供数效率，不可直接当停顿 wall cycles。

VMFPU 进一步拆分三个真实子单元：

```text
mul_input_fire / input_backpressure / output_fire / processing
div_input_fire / input_backpressure / output_fire / processing
fpnew_input_fire / input_backpressure / output_fire / processing
```

全部以 lane-sample 计数。`input_fire` 高说明入口吞吐得到利用；`processing` 高但 fire 低、且 input backpressure 低，通常是固有延迟或依赖限制；input backpressure 高才表明子单元接收能力不足；output fire 低并伴随 result queue full，则瓶颈位于结果排出。

最后增加状态驻留分布：

- `valu_state_0..5_lane_samples` 对应 VALU 六个 reduction 状态。
- `mfpu_state_0..7_lane_samples` 对应 VMFPU 八个普通/reduction/wait 状态。
- `sldu_state_0..8_cycles` 对应 SLDU 九个普通、ordered-sum 和 NP2 状态。

状态编号按各 RTL enum 的声明顺序输出，避免 testbench 复制另一套易漂移的 enum 名。分析 reduction 慢时先看状态面积：lane 内状态高表示本地 fold 主导，TX/RX 高表示跨 lane 树主导，SIMD/OSUM 高表示 word 内或架构顺序串行化，WAIT 高则继续结合写回和同步握手。NP2 的 SETUP/RUN/COMMIT/WAIT 分布能区分置换计算本身与内部 buffer 排空。

这些强化指标将定位能力从“operand wait/long-latency/special path”推进到“VRF bank、依赖、queue、具体长延迟子单元、具体 reduction/slide phase”。仍然不直接观察 cache/DRAM 内部、门级活动、功耗、时序关键路径；这些必须使用相应系统或物理设计工具补充。

opcode 报告还增加了 SEW 与 LMUL 的联合切片：

```text
op_<OP>_sew<sew_code>_lmul<lmul_code>_uops
op_<OP>_sew<sew_code>_lmul<lmul_code>_completed
op_<OP>_sew<sew_code>_lmul<lmul_code>_avg_latency
```

这里的 `sew_code` 是 `vtype.vsew` 的 0～3 编码，依次代表 8、16、32、64 bit；`lmul_code` 保留 `vtype.vlmul` 的原始三位编码，既覆盖整数 LMUL，也覆盖 fractional LMUL。只输出至少有一个 uop 或 completion 的组合，避免为每个 opcode 打印 32 个空桶。

联合切片比两张独立直方图更重要。例如 SEW=64 的样本可能恰好都来自 LMUL=8；若只看边缘分布，无法判断延迟变化来自元素宽度、寄存器组大小还是两者组合。现在可以在同 opcode、同 SEW、同 LMUL 下比较修改前后平均完成 latency。`opcode_shape_uop_consistent` 验证所有联合桶的 uop 之和等于 opcode backend uop，`opcode_shape_completion_consistent` 验证 completion 之和等于 opcode completed；二者应为 1。

MASKU 的 gather/compress 路径进一步输出：

| 指标 | 计数事件 | 可回答的问题 |
|---|---|---|
| `<class>_mask_index_fifo_pushes/pops` | index FIFO 写入/取出 | index 产生与消费是否平衡 |
| `<class>_gather_request_fifo_pushes/pops` | gather VRF request FIFO 写入/取出 | 地址请求是否堆积 |
| `<class>_gather_broadcast_request_lane_samples` | gather 请求广播到各 lane 的 valid 数 | 广播需求量 |
| `<class>_gather_broadcast_grant_lane_samples` | 广播 valid 且 lane ready | 实际接受量与跨 lane 反压 |
| `<class>_gather_broadcast_grant_ratio` | grant/request | gather VRF 请求入口效率 |
| `<class>_gather_out_of_range_indices` | index 越过源向量有效范围 | 返回 0 的索引比例是否造成无效控制工作 |
| `<class>_compress_examined_elements` | compress 检查的 source 元素 | compress 输入工作量 |
| `<class>_compress_selected_elements` | mask bit 为 1、实际压入目标的元素 | 实际输出工作量 |
| `<class>_compress_selection_ratio` | selected/examined | compress 稀疏度 |

这些计数与 `index_fifo_full_cycles`、`special_path_cycles` 联合使用：FIFO push 明显快于 pop 且 full cycle 高，说明消费端是瓶颈；广播 grant ratio 低说明 lane 侧 VRF 请求接收受阻；二者都正常而 special path 仍高，则更接近当前一次一个 index 的算法吞吐上限。compress 必须用 selection ratio 归一化，因为同样的 `vl` 在 10% 和 90% mask 密度下，目标写入量完全不同。
