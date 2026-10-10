# 无序浮点归约合并阶段的 fflags 独立风险审查

## 1. 状态与边界

- 日期：2026-10-08；工作树：`/home/wangwy/openproject/ara_dsa_signoff_integration`。
- 状态：**静态风险已定位，三个最小候选仅准备源码，未编译、未运行 Spike、未运行 VCS，未取得新镜像实测结论。**
- 本文不是修复记录，也不是通过报告。已有历史 PASS 不代表本风险已经闭环。
- 不修改冻结 RTL、mask 验收 helper 或封存 helper；不改变正在准备/执行的原 6 项失败验收 build02。
- 新候选不加入 `suites.json`、Makefrag、campaign、验收清单或覆盖率集合；后续必须人工授权才可独立运行。
- 本风险与 `source_element_cnt` 的真实源 beat 计数修复分开处理。该补丁没有为本文涉及的跨 lane/SIMD 合并状态补充异常有效位；对源计数补丁的静态认可不能扩展成对整个归约异常路径的认可。

## 2. 核心问题

归约不是只对原始向量元素执行一次加法。它还要将 lane 内的部分和、不同 lane 的部分和，以及同一 64-bit 数据字内的 SIMD 分量继续合并。这些合并也是真实浮点运算，可能第一次产生舍入、溢出或无效运算异常。

当前静态路径中，跨 lane 与最后的 SIMD 合并能发出有效 FPU 运算，但没有设置 `issue_be`。该信号默认是零，而且同时用于生成浮点异常 mask。因此，结果数值可能正确，而合并新产生的异常被屏蔽。

这不是“已经实测发现三个失败”，而是有具体源码链路支持、等待最小激励确认的独立风险。

## 3. 精确源码链路

以下行号对应本次阅读快照；后续以状态/信号名及 hash 定位，不能仅依赖行号。

| 阶段 | 源文件与定位 | 观察 |
| --- | --- | --- |
| 默认控制 | `hardware/src/lane/vmfpu.sv:1656` | `issue_be = '0` |
| 跨 lane 合并 | `hardware/src/lane/vmfpu.sv:2256`，`INTER_LANES_REDUCTION_RX` | 输入和局部结果有效时置 `vfpu_in_valid`，没有对 `issue_be` 赋值 |
| SIMD 合并 | `hardware/src/lane/vmfpu.sv:2335`，`SIMD_REDUCTION` | lane0 将高半部分和送入低半继续计算，发出有效 FPU 运算，没有对 `issue_be` 赋值 |
| 输入异常资格 | `hardware/src/lane/vmfpu.sv:1208` 至 `1228` | 从 `issue_be` 提取 `vfpu_simd_mask`，同时写入请求 tag 的 `flag_mask` |
| fpnew 输入 | `hardware/src/lane/vmfpu.sv:1248` 至 `1249` | tag 和 SIMD mask 随该请求进入 fpnew |
| FMA mask | `hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv:134` | 各算术子 lane 接收自己的 `simd_mask_i[lane]` |
| 第一次过滤 | `hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv:303` 至 `310` | `temp_status |= lane_status[i] & {5{lane_masks[i]}}` |
| 第二次过滤 | `hardware/src/lane/vmfpu.sv:1502`、`1507` | `vfpu_ex_flag_fn & {5{|vfpu_tag_out.flag_mask}}` |
| 返回异常 | `hardware/src/lane/vmfpu.sv:1545` 至 `1559` | 输出握手触发 fflags 有效，输出值来自已经过滤后的异常 |
| 标量侧接口 | `hardware/src/ara_dispatcher.sv:1105`、`1115`、`1133` | 合并各 lane 的异常及有效信号；这里不能恢复上游丢失的异常 |

必须区分两类 mask：原始元素的有效范围，和内部合并运算的异常有效范围。源已经消费完不代表部分和合并不再有架构意义。但也不能简单把整个 FPU 的 mask 常置一，否则可能引入 inactive/tail 分量的虚假异常。

**只放开 VMFPU 最后的异常门控不足以修复整个路径**：fpnew 格式切片已经先过滤过异常。本文仅记录这一约束，不实施任何修复。

### 阅读快照

```text
hardware/src/lane/vmfpu.sv
4996dd3cbaf5cb82eac741856950ca13063ef3835a27e8441551b9c8ad7a4b37

hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv
c6819beb6a21ae10e12a3529d4e315dba4447b40f088c9c0a70775cf089d08b8
```

这些 hash 仅标识阅读快照，不声明 build02 的最终 manifest 与其相同。

## 4. 历史测试实际证明了什么

离线读取既有 `audit.json` 和 `commit_trace.csv`，筛选真实 retire 的 `csrr rd,fflags`：opcode 为 `0x73`，CSR 为 `0x001`，funct3 为 `010`，rs1 为零，rd 非零。统计的是 RTL 提交记录中的返回值，而不是从测试源码猜测执行次数。

| 历史用例 | 历史验收 | 实际读取 | 输入/预期 | 对本风险的证明能力 |
| --- | --- | --- | --- | --- |
| `vgap75_red16` | Oct5 audit PASS | 36 次，全部返回 0 | 有限数 min/max，初值为相应无穷中性值；源码要求 flags=0 | 能检查不应出现的异常，不能证明合并新产生的异常正确上报 |
| `vgap76_red32` | Oct6 audit PASS，924 checks，19796 vector bytes | 14 次，全部返回 0 | 扩宽无序求和；输入小整数、初值2，可精确求和；源码要求 flags=0 | 经过归约路径不等于触发该异常路径 |

原始目录，相对于工作树根：

```text
verification/out/gap35-restart-repair-20261005-01/results/vgap75_red16/
verification/out/gap76-old-image-20261006-01/results/vgap76_red32/
```

每个目录的 `audit.json` 是历史验收状态，`commit_trace.csv` 是本次统计的 RTL 证据。历史文件未修改。

| 文件 | SHA-256 |
| --- | --- |
| Oct5 `vgap75_red16/audit.json` | `2d525e3d27861e4da29c71441f7066f4444c73d5cfc8bdffb10bc391f2317430` |
| Oct5 `vgap75_red16/commit_trace.csv` | `c7885576d4eec10aee3e833053604e60fcac589edbf365111a5afcaa8b27024f` |
| Oct6 `vgap76_red32/audit.json` | `fc7ddac8d5c82453bede08f89f976d6937da449d44782911e29adcaa19a6e1f3` |
| Oct6 `vgap76_red32/commit_trace.csv` | `b1797d7115ec25800eb96e4d23a52265e2c9991193b0eed7682a127c020da133` |

其他相关源码审查：

- `apps/riscv-tests/isa/rv64uv/vgap75_red_body.h:45`、`:52`：清除、读取并要求 fflags=0。
- `apps/riscv-tests/isa/rv64uv/vgap76_wide_body.h:37`、`:58`、`:66`、`:68`：扩宽无序归约，随后要求 fflags=0；默认输入为 `(i%5)-2`，初值2。
- `apps/riscv-tests/isa/rv64uv/vfredusum.c` 和 `vfwredusum.c`：有数值测试，但未找到显式 fflags/fcsr 读取检查，不能用数值 PASS 推导异常已验证。
- `apps/riscv-tests/isa/rv64uv/vgap_vmfpu_ured_intra_reset.c`：会检查 fcsr，但用128个1加初值2，仍为精确运算；不能鉴别合并异常丢失。
- `verification/ara_verify/random_rvv.py:110` 的 `_rewrite_ordered_fp_reductions()` 将无序普通/扩宽求和改为对应有序指令。调用位于 `deterministic_stream` 分支（约917行）。使用该改写的严格随机 PASS 不能作为无序合并异常已覆盖的证据；不能泛化成所有随机流程都执行这种改写。

结论是“**本次检索未找到针对合并阶段非零异常的合格实测证据**”，而不是声称仓库任何历史测试都绝不可能触及它。

## 5. 三个最小可判别候选（均未实测）

固定四 lane、VLEN=1024、SEW=32、LMUL=1、vstart=0、无 mask、RNE、`vs1[0]=+0`。指令为 `vfredusum.vs v2,v8,v1`。

| ID | VL | 活动源元素 | 预期结果位型 | 预期 fflags | 目的 |
| --- | --- | --- | --- | --- | --- |
| 0 | 2 | `[1, 2^-23]` | `0x3f800001` | `0x00` | 精确对照，检查不会无故报异常 |
| 1 | 2 | `[1, 2^-24]` | `0x3f800000` | `0x01`，仅 NX | 两个源位于不同 lane，合并产生不精确舍入 |
| 2 | 5 | `[1,0,0,0,2^-24]` | `0x3f800000` | `0x01`，仅 NX | 两个非零源位于 lane0 同一64-bit字的低/高32位，最终 SIMD 合并产生不精确舍入 |

1 附近 FP32 的间距为 `2^-23`。`1+2^-24` 正好是相邻可表示数的中点，RNE 取偶得到1，但必须报告不精确；`1+2^-23` 则完全可表示。只检查结果1会遗漏本风险。

位型常量：`1=0x3f800000`、`2^-23=0x34000000`、`2^-24=0x33800000`。源码用整数位型加载，不通过标量浮点运算生成数据，避免提前污染 fflags。

位置依据为 `hardware/include/ara_pkg.sv` 的 `shuffle_index()`，四 lane/EW32 分支（约545行）：源元素0/1分别进入 lane0/1 的低32位，元素4进入 lane0 的高32位。因此候选1与2在当前结构中针对不同合并阶段。改变 lane 数量后不得原样沿用阶段归因。

无序归约一般不能对任意随机输入强求与 Spike 的中间加法顺序一致。本组只使用两个非零正数与零，不依赖易发生消去的长加法序列；预期值由上面的精确二进制关系给出。最终仍须同时检查结果、fflags 和阶段握手，不能只凭 VL 判断异常发生位置。

## 6. 已准备的独立源码与手动构建说明

源码：[reduction_merge_fflags_20261008.c](reduction_merge_fflags_20261008.c)。它不位于自动 directed 测试目录，没有加入任何执行入口。

- 默认执行三个候选；`RED_MERGE_CASE=0/1/2` 可各自生成最小 ELF。
- 开头初始化源、种子、目标的8个元素，随后将真实 VL 设置为2或5。
- 紧邻归约前写 `fcsr=0`，同时确定 RNE 并清除异常。
- 用 `vmv.x.s` 等待并取回结果，立即读取 fflags/vstart，不调用 printf 或浮点参考计算。
- `merge_observed[3]` 保留实际 VL、结果位型、fflags、vstart 和失败位图。
- `merge_started_mask`、`merge_completed_mask` 区分未执行与已执行；不能把 BSS 中默认零解释为通过。
- 每项4个检查，全部运行应完成12个检查，完成 mask 为 `0x7`；单项应4个检查，完成 mask 为 `1<<ID`。`g75_result[1]` 为失败检查数。
- 沿用现有 `gap75_start.S` 的启动/trap/tohost 约定。任何 trap、错误结果、超时、缺少终止或缺少证据都不能算 PASS。

**以下仅是后续人工授权使用的构建说明，本次没有执行，包括编译也没有执行。** 路径使用项目 LLVM，不使用 ZCC。

```bash
ROOT=/home/wangwy/openproject/ara_dsa_signoff_integration
CC=/home/wangwy/openproject/ara/install/riscv-llvm/bin/clang
# 使用新的独立输出目录，不能指向 build02 或已有结果目录。
OUT=$(mktemp -d "$ROOT/verification/out/reduction-merge-fflags-prepared-XXXXXXXX")

"$CC" --target=riscv64-unknown-elf -march=rv64gcv_zfh_zvfh \
  -mabi=lp64d -mcmodel=medany -mno-relax -msmall-data-limit=0 \
  -O2 -fno-vectorize -fno-slp-vectorize -ffreestanding \
  -DVLEN=1024 -DNR_LANES=4 -DRED_MERGE_CASE=-1 \
  -fuse-ld=lld -nostdlib \
  -T"$ROOT/verification/tests/gap75.ld" \
  "$ROOT/verification/tests/gap75_start.S" \
  "$ROOT/verification/coverage/reduction_merge_fflags_20261008.c" \
  -o "$OUT/input.elf"
```

编译后先离线核对 ELF 的三处动态候选仍执行 `vfredusum.vs`、设置 RNE、读取 fflags，而没有经过随机生成器的 ordered rewrite。再由人工选择独立运行目录、确认参考模型和 VCS 镜像参数及来源。这里不提供自动运行/提交覆盖率脚本，防止误混入本轮验收。

## 7. 后续最小取证与通过条件

一个包含三个候选的短运行即可初步区分，不需要整套回归。窗口覆盖归约进入至 CSR 读取完成，关注：

| 信号组 | 要回答的问题 |
| --- | --- |
| `mfpu_state_q`、操作码、VID、lane编号 | 该运算属于哪个候选、哪个合并阶段 |
| `vfpu_in_valid && vfpu_in_ready`、`operand_a/b/c` | 真正送入 FPU 的两个部分和是否为计划值 |
| `issue_be`、`vfpu_simd_mask`、输入 `flag_mask` | 有意义的合并是否被标成全 inactive |
| fpnew `op_status`、`lane_status`、`lane_masks`、`status_o` | 原始异常是否产生，以及第一次在哪一级消失 |
| `vfpu_tag_out.flag_mask`、`vfpu_ex_flag_fn`、`vfpu_ex_flag` | 返回 tag 是否匹配，第二次过滤是否清除了异常 |
| 输出 valid/ready、`fflags_ex_valid_o`、`fflags_ex_o`、CSR提交值 | 区分异常丢失、返回未握手和 CSR 可见性问题 |

合格证据应同时满足：参考结果与固定数学预期一致；RTL三项数据/CSR检查完成；无trap/超时/UVM错误；输入和输出握手的 tag 对应；新增失败被保留而不是豁免。若数值正确、原始 NX 已产生而 mask 为零后 NX 消失，才形成该静态假设的实测闭环。若原始 NX 未产生，则先检查实际操作数、舍入模式和阶段，不能直接修改门控。

本组三项只鉴别最小 NX 路径，不等于穷尽 FP16/FP64、扩宽、masked/all-off、sNaN、NV/OF/UF 或 stall 情形。若未来授权修复，修后仍需选择相邻边界验证，尤其避免内部无效分量错误置旗。**当前保持冻结，先完成原6项 build02。**
