# HDV 程序改写指南

本文说明如何把普通 Ara/RVV kernel 改写成 `vsaxpy_hdv` 这种 HDV task 程序。目标是让程序员能手动插入 HDV hint header、控制 EP 并行关系、固定 task entry 地址，并让 testbench/mock host 能按预期启动和结束任务。

当前规则以现有 RTL 为准：

- IPU 从 `task entry` 开始取 128-bit fetch packet。
- 每个 128-bit fetch packet 的第一个 32-bit word 是 HDV hint header。
- 当前 header 使用 RISC-V hint 形式 `lui x0, imm20`。
- header 后面通常放 3 条 32-bit 指令。
- VLIWPU 根据 header 中的 p-bit 把指令打成 EP。
- HEU 把 EP 内标量指令发给 scalar backend，把向量指令发给 Ara vector backend。
- `ret` 被 scalar backend 识别为 HDV task 结束。

## 1. 文件结构

建议新建 app 文件夹时尽量沿用普通 app 结构：

```text
apps/<name>_hdv/
  main.c
  data.S
```

`main.c` 保留普通 C 入口、数据准备和校验逻辑。真正交给 HDV 执行的 kernel 建议写成一个单独函数，并把函数体写成裸 inline assembly。

参考结构：

```c
void kernel_hdv(int n, const float a, const float *src1, float *src2);

int main() {
    kernel_hdv(n, a, src1, src2);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void kernel_hdv(int n, const float a, const float *src1, float *src2) {
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ...
    ".option pop\n"
    );
}
```

关键点：

- `section(".hdv_task")`：把 HDV task 放到 linker script 的专用段。
- `aligned(16)` 和函数内 `.balign 16`：保证 task entry 是 16B 对齐。
- `naked`：避免编译器自动生成 prologue/epilogue，防止 header/packet 布局被破坏。
- `.option norvc`：当前手写 HDV packet 默认按 32-bit 指令规划，先禁用压缩指令。
- `.option norelax`：避免 linker relaxation 改写指令长度或布局。

## 2. 固定 Task Entry 地址

HDV mock host/TB 会从 `HdvTaskEntry` 指定的地址启动任务。程序必须让第一条 HDV header 正好位于这个地址。

当前 linker script 支持：

```ld
__hdv_task_entry = DEFINED(HDV_TASK_ENTRY) ? HDV_TASK_ENTRY : .;
.text.hdv_task __hdv_task_entry : ALIGN(16) {
  KEEP(*(.hdv_task))
} > L2
```

因此 app 需要在 `apps/Makefile` 中加入类似规则：

```make
HDV_TASK_ENTRY ?= 0x80001000
bin/<name>_hdv: RISCV_LDFLAGS += -Wl,--defsym=HDV_TASK_ENTRY=$(HDV_TASK_ENTRY)
bin/<name>_hdv: DEFINES += -D<NAME>_HDV_TASK_ENTRY=$(HDV_TASK_ENTRY)UL
```

地址选择要求：

- 必须 16B 对齐。
- 必须落在 L2 memory 范围内。
- 不要和 `.text`、`.data`、`.bss` 等段重叠。
- 建议使用类似 `0x80001000`、`0x80002000` 这种清晰地址，不要使用 `0x80000008` 这类容易和启动代码/对齐边界混淆的位置。

构建时可以手动覆盖：

```sh
make -C apps bin/<name>_hdv HDV_TASK_ENTRY=0x80002000
```

同时要同步 TB：

```systemverilog
localparam HdvTaskEntry = 64'h8000_2000;
```

如果 `HDV_TASK_ENTRY` 和 TB 的 `HdvTaskEntry` 不一致，HDV 会从错误地址取指。

## 3. Header 格式

当前 header 使用一条显式 RISC-V 指令：

```asm
lui x0, imm20
```

`x0` 写回被丢弃，所以这条指令对普通 RISC-V architectural state 没有副作用。HDV RTL 不把它作为业务指令执行，而是解析 `imm20`：

```text
imm20[12:0]  pbits
imm20[13]    packet256
imm20[14]    cross
imm20[15]    loop_start
imm20[16]    loop_end
imm20[18:17] prefetch_mode (00=off, 01=1×VLEN, 10=2×VLEN, 11=4×VLEN)
imm20[19]    reserved, keep 0
```

含义：

- `pbits`：描述相邻 16-bit slot 之间是否请求继续打入同一个 EP。
- `packet256`：当前 logical packet 是否由两个连续 128-bit fetch beat 组成。
- `cross`：当前 packet 尾部 EP 是否允许跨到下一个 logical packet 开头。
- `loop_start`：软件标记 loop 开始。
- `loop_end`：软件标记 loop 结束。
- `prefetch_mode`：控制 VLSU next-VL prefetch 窗口（loop 内 unit-stride load 自动预取下一轮数据）。

推荐在 inline asm 中定义宏：

```asm
.macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=1
  lui x0, (((\pbits) & 0x1fff) | (((\packet256) & 1) << 13) | (((\cross) & 1) << 14) | (((\loop_start) & 1) << 15) | (((\loop_end) & 1) << 16) | (((\prefetch_mode) & 3) << 17))
.endm
```

注意：

- 不要用 `.word` 隐藏 header。写成 `lui x0, ...` 能在 dump 中一眼看出这是 header。
- `imm20` 最大只能承载 20 bit，所以不要再塞超出 bit 19 的字段。
- reserved bit 必须保持 0，便于后续扩展。

## 4. Fetch Packet 布局

普通 128-bit packet 推荐写法：

```asm
HDV_HINT <pbits>, <packet256>, <cross>, <loop_start>, <loop_end>
inst0
inst1
inst2
```

这正好是：

```text
32-bit header + 3 * 32-bit instruction = 128 bit
```

当前手写规则建议：

- 每个 header 后面先放 3 条 32-bit 指令。
- 需要少于 3 条时用 `nop` 补齐。
- 需要更多指令时进入下一个 packet，再放新的 header。
- 不要让 assembler 自动插入压缩指令，所以必须使用 `.option norvc`。

## 5. p-bit 如何控制 EP

VLIWPU 以 16-bit slot 为粒度扫描 packet。由于当前推荐全 32-bit 指令，一条业务指令占 2 个 16-bit slot。

对于 header 后的 3 条 32-bit 指令：

```text
slot0/slot1 = inst0
slot2/slot3 = inst1
slot4/slot5 = inst2
```

有用的 p-bit 主要是：

```text
pbits[1] : inst0 后是否继续连 inst1
pbits[3] : inst1 后是否继续连 inst2
```

示例：

```asm
HDV_HINT 0x00
inst0
inst1
inst2
```

效果：`inst0`、`inst1`、`inst2` 分成 3 个 EP。

```asm
HDV_HINT 0x02
inst0
inst1
inst2
```

效果：`inst0 || inst1` 是一个 EP，`inst2` 进入下一个 EP。

```asm
HDV_HINT 0x0a
inst0
inst1
inst2
```

效果：`inst0 || inst1 || inst2` 是一个 EP。

`vsaxpy_hdv` 里常用 `HDV_HINT` 默认值 `0x1f`，对 3 条 32-bit 指令来说等价于尽量把三条业务指令打在一起。

重要限制：

- p-bit 是“允许并行”的软件承诺，不是强制并行。
- VLIWPU 仍会因为 branch/system、issue width、32-bit 指令边界、硬件依赖断点等条件提前切 EP。
- 同一 EP 内的指令应由软件保证没有非法 RAW/WAW/资源冲突。
- 向量指令之间的数据相关由 Ara 后端处理，但标量操作数 snapshot、`vset rd` 写回、branch/ret 等仍需要按当前 HDV 规则保守安排。

## 6. 跨 Packet 打包

如果一个 packet 尾部只有少量非控制流指令，而下一个 packet 开头有可并行指令，可以用 `cross=1` 允许跨 packet 组成一个 EP。

示例来自 `vsaxpy_hdv`：

```asm
HDV_HINT 0x02, 0, 1, 1, 0
vsetvli t0, a0, e32, m1, ta, ma
vle32.v v0, (a1)
sub a0, a0, t0

HDV_HINT
vle32.v v3, (a2)
slli t1, t0, 2
vfmacc.vf v3, fa0, v0
```

这里第一个 packet 的 p-bit 让：

```text
EP0 = vsetvli || vle32.v v0
```

`sub` 是 packet 尾部剩余指令，`cross=1` 允许它和下一个 packet 开头继续组合：

```text
EP1 = sub || vle32.v v3 || slli || vfmacc
```

使用跨包打包时必须满足：

- 跨包 EP 内不能包含 branch/jal/jalr/ret/system。
- 前一包尾部和后一包头部之间必须没有软件层面的非法依赖。
- 如果跨包 EP 中有标量指令更新寄存器，而同 EP 的向量指令读取该寄存器作为 scalar operand，要确认当前 operand snapshot 语义是否符合预期。
- branch target 不要跳进跨包 EP 中间。

## 7. 分支、Loop 和 Ret

当前短期规则：

- branch target 必须是合法 EP 起点。
- 最好让 branch target 指向某个 16B 对齐 fetch packet 的 header 后 loop 起点。
- 不支持 C66x 风格“跳进 EP 中间并忽略低地址同 EP 指令”的完整语义。
- branch/jal/jalr/ret 会强制结束 EP。
- `ret` 表示 HDV task 完成。

loop 推荐写法：

```asm
.balign 16
task_start:
loop:
HDV_HINT ..., 0, 0/1, 1, 0
...

HDV_HINT ..., 0, 0, 0, 1
bnez a0, loop
ret
nop
```

注意：

- `loop_start` 和 `loop_end` 当前主要是 header metadata，便于 RTL/调试识别 loop 范围。
- 真正跳转由标量后端执行 branch，并通过 redirect 通知 IPU/VLIWPU。
- `ret` 后面的 `nop` 只是为了补齐 packet，不应该作为有效业务 EP 执行。

## 8. 标量和向量寄存器约定

普通 C 调用 HDV task 时仍使用 RISC-V ABI：

```text
a0, a1, a2, ... 传整数/指针参数
fa0, fa1, ...    传浮点参数
ra               普通 C call 的返回地址
```

当前 HDV scalar backend 会维护自己的 XRF/FRF 上下文，并给 vector dispatch 提供向量指令需要的 scalar operand。

改写时要注意：

- 向量 load/store 的 base pointer 来自标量寄存器，例如 `a1/a2`。
- `vfmacc.vf` 这类指令的 scalar FP operand 来自 FRF，例如 `fa0`。
- `vsetvli rd, rs1, ...` 若 `rd != x0`，后续标量指令读取这个 rd 时要等 Ara 的 vset response 写回；当前 RTL 对此有保护，但软件排布仍应尽量清晰。
- 同一个 EP 内如果标量指令更新某个寄存器，另一个向量指令又读取这个寄存器作为 operand，必须明确想要旧值还是新值。当前 vector dispatch 会在消费该 vector slot 时抓取标量 operand，不等于“同 EP 内自动读写旁路”。

## 9. 从普通 RVV Kernel 改写的步骤

### 9.1 找出热循环

先从普通程序中找出主要 RVV loop，例如：

```asm
loop:
  vsetvli ...
  vle...
  ...
  vse...
  add/sub pointer/counter
  bnez loop
```

只把热循环改成 HDV task。普通初始化、校验、打印仍留在 C 中。

### 9.2 固定函数和地址

给 kernel 函数加：

```c
__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
```

在 `apps/Makefile` 为这个 app 添加 `HDV_TASK_ENTRY` 规则。

### 9.3 禁用压缩和 relaxation

在 asm 开头写：

```asm
.option push
.option norvc
.option norelax
.macro HDV_HINT ...
.endm
.balign 16
```

结尾写：

```asm
.purgem HDV_HINT
.option pop
```

### 9.4 按 packet 重排指令

把指令按每包 3 条业务指令排布。每个 packet 前插入 `HDV_HINT`。

原则：

- 同一 EP 内允许并行的指令用 p-bit 连起来。
- 有 RAW/WAW 或必须先后执行的地方切 EP。
- branch/jal/jalr/ret 单独成 EP（VLIWPU 自动切为 BRANCH 硬边界）。
- **FENCE 单独成 EP（VLIWPU 自动切为 SYSTEM 硬边界），在 scalar backend 中作为 NOP 执行。**
- **ebreak 可作为显式 task-end marker（与 ret 解耦），置于 task 末尾的独立 EP 中。**
- 需要跨 packet 提高利用率时显式设置 `cross=1`。

### 9.5 计算 expected EP 数

TB 中 `AutoExpectedEpAcknowledges`（原名 `AutoExpectedEpAccepts`）用来判断测试是否通过。若 task 自然执行到 `ret` 或 `ebreak`，expected 应包含直到 task-end 指令为止的 EP 数，不应包含其后的 padding/data。

以当前 `vsaxpy_hdv` 为例：

```text
每轮 loop:
  EP0 = vsetvli + vle
  EP1 = sub + vle + slli + vfmacc
  EP2 = add + vse + add
  EP3 = bnez

32 轮 loop = 32 * 4 EP
fall-through ret = 1 EP
expected = 32 * 4 + 1 = 129
```

如果改了 p-bit、packet 布局、`TOTAL_ELEMENTS`、VLEN 或 SEW，就必须重新计算 expected。

## 10. 检查 Dump

构建后检查 dump：

```sh
make -C apps bin/<name>_hdv
less apps/<name>_hdv/<name>_hdv.dump
```

必须确认：

- `.hdv_task` 起始地址等于 TB 的 `HdvTaskEntry`。
- task entry 第一条就是 `lui zero, <imm>` header。
- 每 16B packet 第一个 word 都是 header。
- 没有压缩指令混入 HDV task。
- branch target 对齐且指向期望的 loop 起点。
- `ret` 位于任务结尾，后续只有 padding，不再有有效业务指令。

`vsaxpy_hdv` 的关键 dump 形态类似：

```text
80001000: 0c002037      lui zero, 0xc002
80001004: 0d0572d7      vsetvli t0, a0, e32, m1, ta, ma
80001008: 0205e007      vle32.v v0, (a1)
8000100c: 40550533      sub a0, a0, t0
80001010: 0001f037      lui zero, 0x1f
...
80001030: 1001f037      lui zero, 0x1001f
80001034: fc0516e3      bnez a0, 0x80001000
80001038: 00008067      ret
8000103c: 00000013      nop
```

## 11. 常见错误

### task entry 不一致

现象：

- HDV 从错误地址取指。
- 第一包不是 header。
- VLIWPU 解析出错误 p-bit。

处理：

- 检查 `HDV_TASK_ENTRY`。
- 检查 TB `HdvTaskEntry`。
- 检查 dump 中 `.hdv_task` 地址。

### 忘记 `.option norvc`

现象：

- packet 内混入 16-bit compressed 指令。
- 手算的 p-bit 与实际 slot 不匹配。

处理：

- 在 HDV asm 块内强制 `.option norvc`。
- 重新检查 dump。

### p-bit 把有依赖的指令放进同一 EP

现象：

- 标量寄存器值不符合预期。
- vector 指令抓到旧/新 operand 与预期不一致。

处理：

- 在依赖边界把 p-bit 置 0。
- 或重排指令，把 producer 放到前一个 EP，consumer 放到后一个 EP。

### branch target 不合法

现象：

- IPU redirect alignment assertion。
- 跳转后 VLIWPU 从 EP 中间错误组包。

处理：

- branch target 指向 16B 对齐 packet/loop 起点。
- 不要跳到 header word。
- 不要跳到 32-bit 指令的后半个 16-bit slot。

### ret 后继续执行

现象：

- EP 计数比 expected 多。
- HDV 继续吃到 `nop` 后的数据区。

处理：

- 确认 scalar backend 版本支持 `ret` 产生 task complete。
- 确认 expected 只统计到 `ret`。
- 确认 `ret` 后没有有效业务指令。

## 12. 最小模板

下面是一个可复制的 skeleton：

```c
__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void kernel_hdv(long n, float a, const float *in, float *out) {
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16))\n"
    ".endm\n"
    ".balign 16\n"
    "loop:\n"

    "HDV_HINT 0x0a, 0, 0, 1, 0\n"
    "vsetvli t0, a0, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "sub a0, a0, t0\n"

    "HDV_HINT 0x1f, 0, 0, 0, 1\n"
    "vse32.v v0, (a2)\n"
    "bnez a0, loop\n"
    "ret\n"

    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
```

这个模板只是展示格式，不代表 p-bit 一定正确。实际 kernel 必须根据指令依赖、资源使用、branch 位置和 expected EP 数重新规划。

## 13. 提交流程建议

改写一个新 HDV app 时，建议按下面顺序提交/检查：

1. 新建 `<name>_hdv`，先保证普通编译通过。
2. 加 `.hdv_task`、`HDV_TASK_ENTRY` 和 header，检查 dump 地址。
3. 先用保守 p-bit，每条关键指令拆成较小 EP，确认功能。
4. 再逐步增大 p-bit 并合并 EP。
5. 最后尝试 `cross=1` 跨 packet 合并尾部 EP。
6. 每次改 packet 布局后同步 expected EP 数和注释。

