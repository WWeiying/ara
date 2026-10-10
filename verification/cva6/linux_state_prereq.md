# Linux State Prerequisites

## Scope And Oracle

`apps/riscv-tests/isa/rv64uv/linux_state_prereq.c` is one deterministic,
self-checking actual-SoC baremetal ELF, not a Linux boot test. It uses the Ara
`crt0.S` M-mode `rvtest_init` hook; ordinary `main` runs in U-mode and reports
the accumulated checks through `vector_macros.h` (`INIT_CHECK`, `EXIT_CHECK`).
The scalar assembly `test_macros.h` was reviewed but is not a C header.
Checks deliberately do not use `XCMP`'s early return, which would skip cleanup.

Read before designing the oracle:

- `verification/patches/README.md` and `cva6-local-fixes.patch`.
- `hardware/deps/cva6/core/csr_regfile.sv`: MSTATUS/SSTATUS read/write masks,
  dirty-state updates, and next-state SD summary (around lines 1545, 1975).
- `hardware/deps/cva6/core/acc_dispatcher.sv`: `dirty_v_state_o` is driven by
  accelerator **retirement acknowledgements**, not request acceptance.
- `hardware/src/cva6_accel_first_pass_decoder.sv`: VS Off rejects vector
  instructions before accelerator execution (around line 215).
- `hardware/deps/cva6/core/fpu_wrap.sv`: operand selection/hold, DIV/SQRT decode,
  scalar-only malformed-box canonicalization, THMULTI selection, result/status.
- `hardware/deps/fpnew/src/fpnew_top.sv` and
  `fpnew_divsqrt_th_64_multi.sv`: box checking and downstream operand reboxing.
- `apps/common/crt0.S` and `rv64uv/villegal_vstart_ops.c`: privilege and trap
  conventions. This test preserves the handler's GPRs and uses a fixed recovery
  PC instead of incrementing an arbitrary fault PC.

Architectural expectations are independent literals, not a copy of the RTL
canonicalization function or results from another DUT operation. References:
[RVV context status](https://docs.riscv.org/reference/isa/unpriv/v-st-ext),
[D NaN boxing](https://riscv.github.io/riscv-unified-db/manual/html/isa/isa_20240411/chapters/d-st-ext.html),
[Zfh boxing](https://docs.riscv.org/reference/isa/unpriv/zfh.html).

## Evidence Plan

| IDs | Stimulus and pass criterion | Distinguishes |
|---|---|---|
| 1-18 | With FS=XS=Off, VS Off/Initial/Clean have SD=0; configuration changes from Initial and Clean produce VS Dirty, SD=1, correct VL. Explicit Dirty/Off writes update SD. Check both mstatus and sstatus. | VS missing from SD vs dirty notification missing; FS/XS cannot mask a failure. |
| 19-25 | One VS-Off `vsetivli` traps exactly once with cause=2 at its exact PC; VS/SD remain zero, and VL/vtype retain the previous legal configuration after reenabling VS. | Correct decode rejection vs no trap, unrelated trap, or side effects. |
| 26-27 | FS Dirty alone also sets SD with VS/XS Off. | Existing FP summary control. |
| 40-71 | 8 步 SSTATUS Write/Set/Clear；每步检查旧值、M/S 两个状态视图及 MPP/MPIE/MIE 保持。FS=XS=Off，另测 SD 只读。 | 区分读遮罩缺 VS、写遮罩缺 VS、RMW 丢位与误写 M-only 字段。 |
| 100-123, 150-173 | Twelve scalar H/S cases each, checking full 64-bit result and full fcsr (frm=RNE and all five flags). | Operand-A vs operand-B vs SQRT box handling, output boxing, NV/DZ behavior. |
| 200-205 | Full-width D exact division, exact sqrt and negative sqrt controls. | Accidental treatment of ordinary D operands as malformed narrower values. |
| 300-305 | Restore and read back fcsr, VL, vtype, vcsr, vstart, mstatus. | Cleanup damage on success or comparison failure. |
| 400-445 | 11 个非法 vtype 输入，覆盖三种配置指令；每例检查完整 VILL/VL=0 并恢复合法配置。 | rs2/立即数保留位被忽略、VILL 未规范化、非法配置后不能恢复。 |

Each H/S matrix contains exact 4/1 and sqrt(4), malformed finite dividend,
malformed zero divisor, malformed negative sqrt, and malformed signaling-NaN
DIV/SQRT inputs. All malformed inputs become quiet canonical NaNs with **zero
flags** here. Paired valid boxes give +Inf/DZ for 1/0 and canonical NaN/NV for
sNaN or sqrt(-4). A valid noncanonical qNaN control has zero flags. Single-bit
holes at bit 63 and at the first boxing bit (16 or 32) test both ends of the box.
H/S expected result bits are `ffffffffffff7e00` / `ffffffff7fc00000` for NaNs.
These uint64_t values are **bit patterns**, never unsigned-to-float numeric
conversions. `fmv.d.x` preserves malformed input boxes; `fmv.x.d` observes the
entire output box. No host FP, float equality, or NaN numeric cast is an oracle.

If a run fails, use the check ID and ELF disassembly to select a bounded FSDB
window; do not change RTL or rerun random inputs. For VS/SD correlate the exact
PC with `commit_ack_i`, accelerator FU, `dirty_v_state_o/i`, `mstatus_q/d`
VS/FS/XS/SD, CSR write data/address, and exception cause/PC. For scalar boxing
correlate the PC/transaction with selected `operand_a/b`, held/current
`fpu_op/srcfmt/vec_op`, `fpu_operands`, input valid/ready, and result/status/tag
at output valid/ready and retirement. Sample pre-update rising-edge values;
valid alone is not a handshake. Expected patched behavior is canonical input
before THMULTI reboxing, then the literal result and flags. Raw finite/sNaN
payload surviving into THMULTI supports a boxing-path failure; correct inputs
with wrong outputs instead implicate downstream execution or status handling.
CSR snapshots cannot alone prove the exact internal next-state cycle timing.

## 新增 SSTATUS 定向覆盖

本组新增 32 项；加上下节 46 项 vtype 检查，总计 **165 项**。
原 87 项 ID、FP 字面量和恢复比较不变。
每行连续四个 ID 分别检查：RMW 返回的旧状态、更新后 MSTATUS、更新后
SSTATUS、M-only 哨兵。前三项只比较 `STATE_MASK`；第四项检查
`MPP=3, MPIE=1, MIE=0`，结束后去掉哨兵。全程 FS=XS=Off，不执行 FP/vector
指令，不从 DUT 读值计算预期。状态中的 Dirty 包含 SD=1，其余 SD=0。

| ID | 指令及源值 | 预期状态变化 |
|---|---|---|
| 40-43 | CSRRW Initial\|SD | Off -> Initial，不能直接置位只读 SD |
| 44-47 | CSRRS Clean | Initial -> Dirty，保留原 VS 低位 |
| 48-51 | CSRRC Initial | Dirty -> Clean，清 VS 低位且 SD 清零 |
| 52-55 | CSRRC Clean | Clean -> Off |
| 56-59 | CSRRW Clean | Off -> Clean |
| 60-63 | CSRRS Initial | Clean -> Dirty，保留原 VS 高位 |
| 64-67 | CSRRC SD | Dirty -> Dirty，不能直接清除只读 SD |
| 68-71 | CSRRW 0 | Dirty -> Off，SD 随 VS 清零 |

RMW 的旧值返回和置/清位语义来自
[Zicsr](https://docs.riscv.org/reference/isa/v20260120/unpriv/zicsr.html)。
这覆盖 M-mode 访问 SSTATUS 的映射，不证明 S-mode 权限、RVH VSSTATUS 或全部 CSR。

失败记录固定为 256 条 `(id, actual, expected)`，足够容纳全部 165 项失败。
超限不越界：继续累加 `num_failed` 和未记录条数，最终输出明确 overflow 错误，
不能静默 PASS。记录计数在 M-mode hook 中显式初始化；所有失败在恢复完成后的
`main` 统一打印，测量区内只有标量比较和内存记录，没有 printf 或提前返回。
`PLANNED_CHECKS=165` 为编译期计划数；`main` 在允许 PASS 前独立检查
`test_case == PLANNED_CHECKS`，不相等打印数量错误并返回 1，不增加计数。
hook 未完成也返回 1；编译期另检查失败容量不小于计划数。

## 新增 VTYPE 定向覆盖

先以 `e16,mf2,ta,ma` 检查低字节 `0xcf` 合法且 VL=3（#400/401）。
每个反例只在该合法字节上加入表中单个高位；四个连续 ID 依次检查非法
vtype=`8000000000000000`（包括其余位必须归零）、非法 VL=0、恢复后的
vtype=`d1`（e32,m2,ta,ma）、恢复后 VL=3。预期均为独立字面量。

| ID | 指令 | 非法 vtype 位/立即数 |
|---|---|---|
| 402-405 | vsetvl | bit8：`1cf` |
| 406-409 | vsetvl | bit9：`2cf` |
| 410-413 | vsetvl | bit10：`4cf` |
| 414-417 | vsetvl | bit31：`800000cf` |
| 418-421 | vsetvl | bit62：`40000000000000cf` |
| 422-425 | vsetvl | bit63：`80000000000000cf` |
| 426-429 | vsetvli | bit8：`1cf` |
| 430-433 | vsetvli | bit9：`2cf` |
| 434-437 | vsetvli | bit10：`4cf` |
| 438-441 | vsetivli | bit8：`1cf`，编码 `dcf1f057` |
| 442-445 | vsetivli | bit9：`2cf`，编码 `ecf1f057` |

vsetvl/vsetvli 的 rs1 使用装入 AVL=3 的非 x0 GPR；vsetivli 的 AVL 立即数
同为 3。用 `.insn`/`.word` 绕过汇编器对非法 vtype 立即数的限制；vsetvli
有 11 位 vtype 立即数，vsetivli 只有 10 位，不把后者的指令选择位误当保留位。
每例恢复使用合法 vsetivli，最后仍执行原 #300-305 的完整保存态恢复。
本组不执行向量算术，不覆盖全部非法 SEW/LMUL、数据寄存器或任意配置组合。

## State Safety

All measurements run before printing. Interrupts are masked with an atomic
save/clear of MIE. The direct, 4-byte-aligned handler is installed only for the
single Off instruction; it saves t0/t1, records count/cause/PC, and returns to a
known label. Wrong or absent traps fail the oracle rather than passing silently.
The hook restores mtvec, mepc, mcause, mtval, fcsr, ft0-ft2 and vector CSRs before
restoring mstatus last (including MPP/MPIE/MIE). It changes no vector data
registers, delegation, PMP, or interrupt-enable CSRs. No comparison failure
returns early. Unexpected fatal faults outside the controlled trap window are
not recoverable. The standard `EXIT_CHECK` subsequently reads VL, so its normal
conservative VS dirtiness is outside the measured/restored hook boundary.

## Build And Handoff

主线程已在 `apps/riscv-tests/isa/rv64uv/Makefrag` 的
`rv64uv_sc_tests` continuation list 注册以下一行，本轮不再修改共享清单：

```make
    linux_state_prereq \
```

No Makefrag, catalog, RTL, dependency or shared runtime edits are part of this
change. Direct pattern-target builds work without registration. From the repo
root, reuse the existing linker script without regenerating shared files:

```sh
make -C apps -o linker_script zcc=0 config=default \
  bin/rv64uv-ara-linux_state_prereq
```

The shared `rv64uv/*` ignore rule has an explicit exception for this new source,
so it can be included together with the Makefrag registration when staging:

```sh
git add apps/riscv-tests/isa/rv64uv/linux_state_prereq.c
git add verification/cva6/linux_state_prereq.md
```

The recipe uses LLVM, not ZCC, and produces the ELF and `.dump` under `apps/bin`.
Requires the existing generated `apps/common/link.ld` for default 4-lane,
VLEN=1024 simulation. Inspect the dump for `rvtest_init`, the aligned handler,
Off PC/recovery PC, raw FMV.D.X/FMVs, DIV/SQRT, status snapshots and final CSR
restore order. Compiler-generated scalar/FP/vector work must not enter a
status-measurement sequence.

运行由主线程负责，使用冻结源码及边界/acc lifecycle/state prerequisite 探针
编译的同一新 SoC 镜像，以 `--contract-monitor` 校验日志和镜像哈希。
不再使用缺少 FPU probe 的 dependency-baseline 旧镜像诊断。已运行
`linux-state-prereq-fixed-20260922` 的 prereq、vfredmax_boundary、vle32、vsetvl
四点回归，一次编译。随后只用同镜像复验冻结的旧 87 项 ELF，单独记录
输出及 ELF hash，不覆盖旧 run。实测均通过，结果见下方闭环记录。

新版通过条件：源文件对应的 `PASSED`、**165 checks**、无失败/overflow、
SoC exit=0、monitor 无协议错误且日志无截断，并审查 simulator/assertion 错误。
27 个 scalar DIV/SQRT、8 个 SSTATUS RMW、11 个非法配置及逐例合法恢复、
一个预期 VS-Off trap，无随机循环。
编写测试时估计为秒级至几分钟短测；旧 run 报告 CPU 15.110 秒，不是新版测量或
timeout oracle。软件审查者未启动仿真，主线程的 VCS 实测另列于闭环记录；
本次未运行 Spike 或 ZCC。

## 初版编译记录（87 项）

- The exact LLVM build above passed. Only linker diagnostic: ignoring the
  memory-region assignment for non-allocatable `.comment`.
- Additional Clang `-fsyntax-only -Wall -Wextra -Werror` review passed with the
  same RV64GCV/Zfh/Zvfh target and the common/vector include paths.
- The dump confirms the M-mode hook, status-write/read adjacency, raw FPR moves,
  per-case fcsr clearing, and restoration before the final mstatus write.
  Handler: `0x80000104`; Off instruction: `0x80000548`; resume: `0x8000054c`.
  Handler preserves t0/t1 and SP. No implicit FP/vector instructions intervene
  in the state snapshots. Static code duplication by LLVM does not add dynamic
  test cases. ELF sizes: text 9806, data 8, bss 64 bytes.
- Source SHA-256: `a71771308f7c7e8dd347dd657ecfe79f9ad6fb4a0c4a590e13d32889d1fa2ca0`.
- ELF SHA-256: `54eabf012c1c09beb60e3aa0922e106e08a7822e8c648523cd393736f32be3bd`.
- 以上是初版静态/编译记录，不能代表当前增强版 ELF。初版后来由主线程运行，
  实际失败记录如下；本分析没有额外仿真。

## 旧 Run 的六项失败

来源：`verification/out/linux-state-prereq-vcs-20260922/`，
`tests/rvv_linux_state_prereq/console.log` 显示 87 checks、6 failed、tohost=6。
`work/state_prereq.csr.log` / `state_prereq.fpu.log` 完整记录 449/590 行，
均 `truncated=0,dropped=0`；END 只说明日志完整，不是 DUT PASS。
下述周期统一采用 probe 的 epoch=1、posedge 前 `#1step` 采样；q/d 是同一
快照的当前态/下一态意图，不与 instruction tracer 的另一周期基准混用。

| 失败 ID | CSR probe 周期 / PC | 实际值 | 预期值 |
|---|---|---|---|
| 4 | 600 / 80000218 | 0000000000000000 | 0000000000000200 |
| 6 | 664 / 8000030c | 8000000000000000 | 8000000000000600 |
| 9 | 797 / 8000026a | 0000000000000000 | 0000000000000400 |
| 11 | 872 / 800003cc | 8000000000000000 | 8000000000000600 |
| 16 | 1052 / 80000480 | 8000000000000000 | 8000000000000600 |
| 302 | 4380 / 800010a0 | 0000000000000000 | 8000000000000000 |

前五项是 SSTATUS 经 `STATE_MASK=800000000001e600` 后的值，最后一项是完整
vtype。指令日志中 `num_failed` 地址 `80002678` 的六次写入依次为 1..6，
写指令 PC 为 `80000302,80000356,800003c2,80000416,800004e8,80001122`。
这不是仅凭首错或失败总数猜测 ID。

- 前五项：相同快照的 mstatus.VS 分别为 01/11/10/11/11，FS=XS=00，
  但 `CSR_SSTATUS` 返回的 VS 恒为 00；读访问无 fault。与旧镜像的 SSTATUS
  read mask 缺 VS 一致。旧测试没有 SSTATUS 写入，不能用它证明 write mask 正确。
- 原 VS/SD 修复有正向证据：周期 661/869 的 `dirty_v=1,ack=01`，
  VS 分别 01/10 -> 11，SD 同一 d 快照 0 -> 1，FS/XS 保持 Off；
  下一周期 662/870 的 mstatus q 已正确。不是 FS Dirty 掩盖 VS 汇总失败。
- VS Off trap 在周期 1207、PC `80000548`、cause=2，未退休且无 dirty_v；
  恢复后旧 VL=2、vtype=8 保持，#19-25 通过。
- **#302**：acc lifecycle 周期 473 读出保存的 vtype=`8000000000000000`。
  周期 4335 的 `spill_out_fire=1`，指令 `8129f057` 即
  `vsetvl zero,s3,s2`，rs1 数据=0、rs2=`8000000000000000`，无响应异常。
  周期 4379 的 vtype CSR 指令 `c21025f3` 响应为 0，4380 退休读回 0。
  周期 4335 的零响应是 VL，不能误当成 vtype。旧 RTL
  `hardware/src/ara_dispatcher.sv` 的 `vsetvl` 路径只取 `rs2[7:0]`，丢失 VILL，
  与完整输入/错误读回相符；不是编译器漏传高位。
- **#305 通过**：CSR 日志周期 415 保存 `8000000a00006200`，4502 写恢复值时
  d=`8000000a00006200`，4524 读回 q 全值相同。不能把第六项归为清理比较过严。

Oracle 审查：RVV 要求复位 VL/vtype 可以读出并经一条 `vsetvl` 恢复，且
`vsetvl` 必须检查 rs2 全 XLEN 位。此处 rs1 是 s3（值为 0），不是 x0，
不涉及 `rd=rs1=x0` 的保留情形；#302 不应屏蔽 VILL 或改期望为 0。
[RVV 复位与配置规则](https://docs.riscv.org/reference/isa/v20260120/unpriv/v-st-ext.html)。
ISA 允许 Initial/Clean 保守变 Dirty；本测试的精确状态检查及 #305 是当前
CVA6 无异步干扰窗口的定向回归，不是对任意实现的可移植签核。该许可不能解释
相同快照里 mstatus.VS 非 Off 而 sstatus.VS 为 Off，也不能解释 VILL 丢失。

### FP 正向证据

27 个已退休算术事务（H/S 各 12，D 3）均核对 raw A/B、fmt/op、vec=0、
rm=RNE、完整 64-bit result、status、对应退休 PC/tag 和随后 FCSR 读回。
全部 54 项 FP 检查正确；每个退休事务之前均清 FCSR。配对按 epoch/顺序/
flush/PC/tag，不仅按复用 tag；14 个被 FCSR 写触发 flush 取消的原始输入 fire
不计作已执行测试，不能把 41 个原始算术输入 fire 当成 41 个退休用例。

下表为结果 ID 的 `out_fire 周期 / FCSR 读周期`；每行的 flag 检查 ID 为结果
ID+1，实际 FCSR 等于最后一列（十六进制，frm=0），退休均为 out+1。

| 操作/输入 | H ID：out/FCSR | S ID：out/FCSR | flags |
|---|---|---|---|
| 4/1 | 100：1690/1695 | 150：2813/2817 | 00 |
| malformed finite dividend | 102：1786/1792 | 152：2911/2915 | 00 |
| malformed zero divisor | 104：1889/1893 | 154：3010/3016 | 00 |
| 正确 box 的 1/0 | 106：1989/1995 | 156：3108/3112 | 08 |
| malformed sNaN DIV | 108：2102/2106 | 158：3206/3212 | 00 |
| 正确 box 的 sNaN DIV | 110：2202/2208 | 160：3307/3313 | 10 |
| sqrt(4) | 112：2272/2276 | 162：3409/3413 | 00 |
| malformed negative SQRT | 114：2335/2339 | 164：3513/3517 | 00 |
| 正确 box 的 sqrt(-4) | 116：2418/2423 | 166：3612/3617 | 10 |
| malformed sNaN SQRT | 118：2508/2512 | 168：3712/3716 | 00 |
| 正确 box 的 sNaN SQRT | 120：2607/2613 | 170：3824/3828 | 10 |
| 正确 box 的非规范 qNaN SQRT | 122：2708/2713 | 172：3932/3936 | 00 |

D 的 #200/#202/#204 分别为 4034/4038、4139/4143、4240/4246，结果依次
`4010000000000000`、`4000000000000000`、`7ff8000000000000`，flags=00/00/10。
例：#108 周期 2094 raw/`operands_sel` 的 A=`fffffffffffe7c01`，
`boxed` 的 A（送入 FPnew）已规范化为 `ffffffffffff7e00`；
结果周期 2102 为此 qNaN、flags=0。正确 box 的 sNaN
#110 则结果周期 2202 flags=10。H/S 的 qNaN 结果完整位型为
`ffffffffffff7e00` / `ffffffff7fc00000`，不是 uint64 数值向浮点的转换。
这与 [D NaN-box 规则](https://docs.riscv.org/reference/isa/v20260120/unpriv/d-st-ext.html)
一致，但不是任意舍入、反压或 flush 组合的完整 FPU 签核。

### 旧输入冻结

修改测试前，旧 source/dump/实际运行 ELF 已复制并校验到
[`provenance/pre-sstatus-coverage/`](../out/linux-state-prereq-vcs-20260922/provenance/pre-sstatus-coverage/README.md)。
source/ELF hash 与上方初版编译记录一致；dump SHA-256 为
`b5b07120e452f5dc93f2844705cbd8b5436f357e95b91b115ba1cdeaf9a4a19c`。
后续增强版的 PC/周期不同，不可用新 dump 解释旧日志。

## 增强版静态与编译记录（165 项）

- 上述 LLVM `make` 构建及 `-fsyntax-only -Wall -Wextra -Werror` 均通过。
  唯一 linker warning 仍为非 alloc 的 `.comment` 内存区域赋值被忽略。
- dump 确认 RMW 后紧邻 mstatus/sstatus 快照；写入哨兵为 `1880`，MIE=0。
  LLVM 在错误分支复制部分代码，不增加动态用例数。测量区没有隐式 FP/vector
  或打印；失败数组先检查索引 <=255，再按 24 字节记录写入，溢出分支继续报错。
- Off/resume PC 为 `80000888/8000088c`。恢复 `vsetvl` 在 `80003ba8`，仍为
  `8129f057`（rs1=s3，rs2=s2）；#302 读值仍与完整 s2 比较，#305 仍比较完整
  mstatus。最后状态恢复在 `80003de4`，打印位于其后的 `main`。
- dump 中高位 31/62/63 使用 64-bit shift 加 `cf`，未发生符号扩展污染；
  vsetvli 的立即数确为 `1cf/2cf/4cf`，vsetivli 原始字为
  `dcf1f057/ecf1f057`，其后都有非法态快照及合法恢复快照。
- `main` 在 `80003e94/80003e98` 与 `a5`（165）比较，数量不符分支返回 1，
  不经过 PASS 输出。hook 未完成分支也返回 1。
- ELF text/data/bss：21318/8/6192 字节。FP 宏及全部旧预期值与冻结 source
  对比未变；计数为 27 VS + 32 SSTATUS + 46 vtype + 54 FP + 6 恢复 = 165，
  容量 256。不做低字节 256 值穷举，无新随机实验。
- source SHA-256：`37a8cbd23cac30a921da921f3185e77d37a90acd0f0fbfb84aa3a1455aeaff82`。
- ELF SHA-256：`9454722624307a1c8b9df5f755b12e1b85d04627f61be188026cf9845ddd5826`。
- dump SHA-256：`cf6baf0053634ed319dd78e69f26469ca7bfc3db0f3e124b892b5342817e620a`。
- probe 未改，SHA-256 仍为 `2f3730fefe464d86d930fcfded38b9e3074fd9e2bd420f16c9a5c8ed854e1e4b`。
  此处记录的是编译阶段；修复后实际运行证据独立列于下节。

## 修复闭环记录

`verification/out/linux-state-prereq-fixed-20260922/` 使用修复后的 CVA6 SSTATUS
映射和 dispatcher 全宽 vtype 校验，一次 VCS 编译后四点并行：

| 测试 | 结果 | 墙钟秒 | 接口请求/响应 |
|---|---|---:|---:|
| 本文增强版，165 checks | PASS | 23.00 | 86/86 |
| vfredmax_boundary | PASS | 21.39 | 27/27 |
| vle32 | PASS | 65.01 | 186/186 |
| vsetvl | PASS | 63.16 | 85/85 |

增强版状态探针 CSR/FPU 分别 643/606 行；acc lifecycle 11392 行，均未截断。
SSTATUS RMW 和完整状态恢复通过；全部 11 个非法配置规范化为 VILL/VL=0，
各自后续合法配置恢复成功。正常结束，无 protocol error 或未应答请求。

同一镜像随后运行 `linux-state-prereq-frozen87-fixed-20260922`，使用失败实验
原封不动的 ELF，SHA-256 仍为 `54eabf012c1c09beb60e3aa0922e106e08a7822e8c648523cd393736f32be3bd`。
87 checks 全部通过，墙钟 21.17 秒，17/17 接口事务，周期捕获完整；没有修改
原六项的期望来获得 PASS。新旧代码差异及周期证据见主报告第 104 节。
两个结果目录的 `verify.py audit --require-trace` 均通过。这是自检、输入/日志
完整性和接口协议闭环，不是完整 Spike 逐指令比较或 Linux 启动证明。

## Not Proven

This does not prove Linux boot, scheduler/context save/restore, S/U-mode trap
delegation, lazy ownership, interrupts, signals, SMP, RVH, VS-Off vector CSR
access traps, vector arithmetic dirtying, or arbitrary vector register contents.
It does not exhaustively cover rounding, arithmetic, all boxing-bit patterns,
FP8/FP16ALT, non-DIV/SQRT scalar operations, vector FP NaN handling, or FPU
backpressure/flush. Configuration instructions exercise the actual CVA6/Ara
retirement path; the two observed VS/SD transitions do not sign off all lifecycle
or SD timing cases.
Compilation and static inspection are not DUT PASS evidence.
