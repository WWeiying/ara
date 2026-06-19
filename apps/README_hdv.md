# HDV Kernels 现状与限制

本文记录 `apps/` 下 **HDV 版本 kernel**(`*_hdv`)的改写**现状与限制**。

改写的**详细规则**(header 格式、p-bit、EP 打包、expected EP 计算、loop/ret 约定等)以
`hardware/docs/hdv_program_porting_guide.md` 为准。本文不重复这些规则,只记录"改了哪些、能不能跑、为什么"。

---

## 0. TB 已参数化:按 app 选择 task config

`hardware/tb/ara_tb.sv` 现在**按 `+define+HDV_APP_<NAME>` 选择每个 app 的 task config**(不再写死
vsaxpy)。`make sim app=<name>_hdv` 会由 Makefile 自动注入这个 define
(`vscopy_hdv → +define+HDV_APP_VSCOPY`)。

config 块给每个 app 设:`HdvTaskEntry`(统一 0x8000_1000)、初始寄存器
`HdvInitA0/A1/A2/A3/Fa0`、`HdvExpectedEp`。已配 6 个 app(vsaxpy/vsscal/vscopy/vsswap/
vvaddint32/vsdwt),缺省回落到 vsaxpy。`EnableMockBranch=0`、`MockLoopIterations=0`——
**循环由真实标量后端驱动**。

配套的 RTL 改动:**a3 通路已补全**(`scalar backend` 的 `InitialA3`→`xrf[13]`、`hdv_top`、
`ara_soc` 各加 `HdvInitialA3` 参数并逐层传递),所以需要第 4 个参数的 kernel(如 vvaddint32 的
`dest`)现在能拿到 a3。

> **注意:寄存器初值是 parameter(编译时常量)**,所以切换 app 会**重新编译**(define 变了),
> 不是只换 plusarg。这是 param-based init 的必然。

---

## 1. "可编译" 与 "可运行 / 数据已验证" 是两回事

| HDV app | 可编译 | TB 可运行(config 已配) | 数据正确性已实测 | dump 静态自检 |
|---|:--:|:--:|:--:|:--:|
| `vsaxpy_hdv` | ✓ | ✓ | ✓(gold-diff) | ✓ |
| `vsscal_hdv` | ✓ | ✓ | 待跑 | ✓ |
| `vvaddint32_hdv` | ✓ | ✓(用 a3) | 待跑 | ✓ |
| `vscopy_hdv` | ✓ | ✓ | 待跑 | ✓ |
| `vsswap_hdv` | ✓ | ✓ | 待跑 | ✓ |
| `vsdwt_hdv` | ✓ | ✓ | 待跑 | ✓ |

> 6 个 app 的 TB config 都配好了、`make sim app=<name>_hdv` 能跑;但**只有 vsaxpy 做过 gold-diff
> 数据验证**,其余"待跑"——结构上能跑,数据正确性需要各自跑一遍确认(向量 store 类可用
> gold-dump 比对,归约类结果在 fa0)。
>
> 另:各 app 的 `HdvExpectedEp` 是**按公式的最佳估计**(iters×EP/迭代+1)。多发射标量后端会让实际
> EP 数和公式差一点(vsaxpy 就是实际 128 vs 公式 129,这是既有现象),跑时可能要微调
> `HdvExpectedEp`,但不影响功能。

---

## 2. 已改写的 15 个 kernel

**第一批(单层 strip-mine,纯向量 load/compute/store):**

| HDV app | 计算 | 类型 |
|---|---|---|
| `vsaxpy_hdv` | `y = a*x + y` | float |
| `vsscal_hdv` | `y = a*x` | float |
| `vvaddint32_hdv` | `z = x + y` | int32 |
| `vscopy_hdv` | `y = x` | float |
| `vsswap_hdv` | `x ↔ y` | float |
| `vsdwt_hdv` | Haar 小波步(就地) | float |

**第二批(归约 / 嵌套 / 特殊):**

| HDV app | 计算 | 结构 |
|---|---|---|
| `vsdot_hdv` | `Σ a[i]*b[i]` | 单层 + 归约(`vfredsum`→`vfmv.f.s`) |
| `vsspmv_hdv` | 稀疏 mat-vec(gather) | 单层 + `vluxei` + 行归约 |
| `vsgemv_hdv` | `y = A·x`(32×128) | 单层 + 多 chunk + 行归约 |
| `vssymv_hdv` | `y = αAx + βy` | 单层 + 归约 + 标量 FP 链 |
| `vsger_hdv` | rank-1 `A += αx·yᵀ` | **嵌套**(row×col) |
| `vssyrk_hdv` | `C = αAAᵀ + βC` | **嵌套**(row×k,strided load) |
| `vstrsm_hdv` | 解 `L·X=B` | **嵌套** + 前向 skip 分支 |
| `vsgemm_hdv` | `C = A·B`(32³,4 行块) | **嵌套**(row-block×k) |
| `vmc_hdv` | `(src*scalar)>>3`(widening) | 单层 e16→e32 |

**dump 静态自检项**(15 个全过,详细判据见 porting guide §10):
task entry 首字是 `lui zero,<imm>` header;每 16B 包首字是 header;`.option norvc` 生效、task
区无压缩指令;**所有** branch target(含嵌套内/外层、前向 skip)16B 对齐;`ret` 在结尾。

> 第二批打包更保守:**向量-向量依赖打在一起**(Ara 后端负责),但**标量 load-use、
> vset rd→标量读、标量→向量 operand** 都拆到不同 EP(snapshot/写回安全),依赖紧的标量 FP 归约链
> 基本一条一 EP。功能正确性同样**未经 TB 实跑验证**(见 §5.3)。
>
> 注:`vsspmv_hdv` 的 main() 运行时初始化 col_idx,常规 `.text` 较大,task 入口抬到
> `0x80002000`(Makefile 单独覆盖)。

---

## 3. 构建

```bash
cd apps
make bin/vsaxpy_hdv                              # 默认 task entry 0x80001000
make bin/vscopy_hdv HDV_TASK_ENTRY=0x80002000    # 覆盖 entry 地址
```

> **task 实际地址由 linker 决定**:Makefile 通过 `-Wl,--defsym=HDV_TASK_ENTRY=...` 把
> `.hdv_task` 段定位到该地址。`main.c` 里的 `#define <NAME>_HDV_TASK_ENTRY ...` 只是给 C 看的
> 常量,**改它不会改变 task 的实际地址**——必须用 `make ... HDV_TASK_ENTRY=`,并同步 TB 的 `HdvTaskEntry`。

app 目录被 Makefile 的 `find -name main.c` 自动发现,无需手动加进 `BINARIES`。

---

## 4. 在 TB 中运行 HDV app

已配好的 6 个 app 直接通过 `app=<name>_hdv` 选择 TB 配置:

```bash
make -C hardware sim app=vsaxpy_hdv
make -C hardware sim app=vvaddint32_hdv
```

`hardware/Makefile` 会把 `app=vvaddint32_hdv` 转成 `+define+HDV_APP_VVADDINT32`，
`ara_tb.sv` 再据此选择 `HdvInitA0/A1/A2/A3/Fa0` 和 `HdvExpectedEp`。

新增一个 `<name>_hdv` app 时仍要补 TB 配置:

1. 在 `apps/Makefile` 为该 app 加 `HDV_TASK_ENTRY`/`DEFINES` 规则。
2. 在 `hardware/tb/ara_tb.sv` 增加 `HDV_APP_<NAME>` 分支，设置入口、初始 ABI 寄存器和 expected EP。
3. 确认数据地址与该 app dump 中 `.data` 布局一致。
4. 重新 compile/sim，因为 app 选择是 compile-time define，不是 runtime plusarg。

---

## 5. 当前限制(分三类,注意区分性质)

务必区分 **"RTL 绝对做不到" / "当前实现不完整" / "默认验证环境没配"**,不要都说成 RTL 硬限制。

### 5.1 通用"向量 → 标量"结果回写
**RTL 已补**(本轮):`hdv_vec_dispatch_unit` 现在除 vset 外,还检测 `vmv.x.s`/`vcpop.m`/`vfirst.m`
(→XRF)和 `vfmv.f.s`(→FRF),把 vset 的 resp_meta + EP-accept gating + 写回**泛化**成通用 scalar
写回(写回输出带 `is_vset`/`is_fpr` 标志,scalar backend 据此落到 FRF/XRF/csr_vl)。
- 状态:**RTL 实现 + 静态逻辑检查通过,vset 路径无回归**;但**新路径还没用归约 kernel 实跑验证**
  (需 vsdot + TB 配置,见 §5.3)。在那之前,归约结果的端到端正确性未经实测。

### 5.2 loop-lock(基本已具备,缺多层优化)
- **分支跳转是真实的,不是模拟。** 标量后端解析分支、产生 `redirect_valid/pc`,`hdv_top` 据此驱动
  IPU redirect(`hdv_ctrl_redirect = scalar_backend_redirect`)。单层 backward branch 是真跳转、能跑。
- **loop_start/loop_end 已接进 loop-lock**:IPU 的 `served_pkt_loop_start/end` 驱动
  `loop_build/loop_locked/loop_protect`(`hdv_instruction_prefetch_unit.sv` 中),并经
  `effective_loop_fetch_lock` 启用 2-buffer loop-lock。(VLIWPU 只透传 marker,不动作。)
- **嵌套循环功能上能跑**:IPU 的 redirect 是**按目标地址**的(`redirect_in_active`/`in_fill` 命中
  buffer 就 replay,否则 FILL 重取),任意 backward branch(含内外层)都能正确取指/replay。
- **缺的是多层 loop-lock 优化**:`loop_build/loop_locked` 是单 bit、单层。深层嵌套时内层命中 buffer
  走 replay、外层 back-edge 走重取——**功能对,只是外层没省取指**。这是 perf,不是 correctness。

### 5.3 验证环境限制(按 app 配置,不是 RTL 不行)
`hardware/tb/ara_tb.sv` 已经为当前 6 个 HDV app 做了 compile-time config 分支。限制在于:

- 新增 HDV app 时仍要补一个 `HDV_APP_<NAME>` 分支。
- `HdvExpectedEp` 仍是静态期望值,改 p-bit/EP 布局/VLEN/TOTAL_ELEMENTS 后要同步更新。
- 数据正确性验证仍要逐 app 跑 gold/result 比对;目前只有 `vsaxpy_hdv` 明确做过 gold-diff。

> `vsetvli rd=t0` 后标量读 `t0`(vset→标量 RAW)**不是限制**:已有 `vec_vset_inflight` +
> `vec_scalar_vset_wb` 互锁处理(porting guide 里也按此排布)。

---

## 6. 仍未改写的 kernel(及原因)

手写 kernel 里只剩 2 个**结构上不适合**当前 HDV 模型:

| kernel | 为什么没改 |
|---|---|
| `vgemm` | 用**栈帧**(`addi sp` + `sd s0..s3`)、读**栈传参**(`ld t0, 32(sp)`)、多重 guard 分支。naked-HDV-task 模型里第 7 个参数走栈,TB 调用拿不到;prologue/epilogue 也不符合"单热循环=task"的形态。需较大重构且仍无法在当前 TB 正确取参,故不移植。 |
| `vsfft` | **没有 kernel 实现源码**:`fft_r2dif_f32_256` 只在 main.c 声明、未定义(目录里只有 twiddle 表 `data.S`)。无可移植的 asm。 |

| 非手写,不在范围 | 原因 |
|---|---|
| `saxpy` | C + `#pragma clang loop vectorize`,编译器自动向量化 |
| `vmc`(原 `vec_mul_shift`) | 原 kernel 整段注释、active 代码是 `vvaddint32`;已按注释里的 widening kernel 移植为 `vmc_hdv` |

> 其余 9 个(`vsdot`/`vsspmv`/`vsgemv`/`vssymv`/`vsger`/`vssyrk`/`vstrsm`/`vsgemm`/`vmc`)
> 已移植(见 §2),dump 结构自检全过,但**功能正确性未经 TB 实跑验证**——仍卡在 §5.3 的
> per-app TB config + gold/result 比对。

---

## 7. 解锁路线

| 针对 | 状态 / 需要的改动 |
|---|---|
| 5.1 归约回写 | **RTL 已实现 + 静态检查**(vec_dispatch 通用 scalar 写回 + scalar backend FRF/XRF 分发)。待:用 vsdot 实跑验证 |
| 5.2 loop-lock | loop_start/end **已接** loop-lock;嵌套**功能已可跑**(目标地址 redirect)。剩:多层 loop-lock **性能优化**(可选) |
| 5.3 验证环境 | 当前 6 个 app config 已配;新增 app 仍需补 `HDV_APP_<NAME>` 分支、expected EP 和数据地址 |

现在最大的实际阻塞不是结构 RTL,而是**更多 kernel 的 app config、expected EP、gold/result 验证**。
