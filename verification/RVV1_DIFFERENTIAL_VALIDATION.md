# RVV 1.0 差分验证缺陷报告

## 1. 验证范围与方法

本文记录 Ara 与 Spike 进行 RVV 1.0 差分验证时发现的架构状态差异、根因和
RTL 修复。RTL 基线提交为 `77eb36a7`，RVV 1.0 随机指令生成器固定在
`a9e723ba921aee0cd2aea7999d92859f2a2f088e`。

早期复现用例为 `ara_dsa_rvv1_signature_smoke`、seed 1、`VLEN=1024`。
随机指令主体使用 `SEW=16`、`LMUL=4`、`VL=79`、`tu,mu` 和
`vxrm=RNU`。严格检查模式在初始状态以及每条生成的 RVV 指令之后保存全部
`v0-v31`。每个检查点包含 4096 字节向量寄存器状态，并通过 512 条标量
`ld` 读回；Spike 与 RTL 的对应退休结果逐条精确比较。检查点还读取
`vl`、`vtype`、`vstart`、`vcsr` 和 `fcsr`。

随机向量指令序列如下：

```asm
vwaddu.wx   v0,  v16, a1
vmin.vx     v8,  v16, a4
vmslt.vx    v25, v20, s5, v0.t
vredminu.vs v5,  v28, v5, v0.t
vnclipu.wx  v12, v16, zero, v0.t
vssrl.vv    v8,  v20, v28, v0.t
vcpop.m     s11, v26
vasubu.vv   v28, v16, v4
vmulh.vx    v12, v16, s8
vmxor.mm    v2,  v15, v28
```

早期三轮有效证据保存在：

```text
verification/out/rvv1-vector-checkpoints-short-seed1-v14-reshuffle-fix/
verification/out/rvv1-vector-checkpoints-short-seed1-v15-average-fix/
verification/out/rvv1-vector-checkpoints-short-seed1-v16-mask-lmul-fix/
```

三轮仿真复用同一个检查点 ELF 和 Spike 提交日志，因而可以直接比较修复前后的
第一处差异。该阶段曾停在 `vmxor.mm`，但这已经不是当前首错：后续 mask
directed matrix 与短随机严格检查已经越过该指令。报告保留第 4 至第 11 节作为
早期定位过程，并在第 15 节以后统一记录后续缺陷、源码修改和证据。

在早期固定 ELF 的严格重放阶段，验证曾越过 widening MAC 高半区重叠缺陷，
匹配前缀由 2810 条增加到 5086 条。当时第一个确定可见的架构差异是
`vcpop.m t2, v20` 返回 37，而 Spike 返回 41。进一步插入选择性检查点后，最早
观察到的差异落在 source 600 的 `vslidedown.vi v16, v16, 7` 检查点，但错误读回
地址对应 `v4`，不是该指令的目的组 `v16-v19`。检查点本身会执行整组
`vs1r.v` 并改变内部 EEW 布局，因此现有证据还不足以把该问题归因于 SLDU、EEW
元数据或检查点采集逻辑。它在本报告中保留为该阶段的待确认问题，不算已发现的 RTL
根因。后续验证已改用非侵入式 accepted-VRF 写回轨迹；第 24 节以后记录该环境和
更晚的随机回归。

## 2. 当前结论

| 编号 | 缺陷或异常 | 状态 | 主要源码 |
|---|---|---|---|
| V-01 | 检查点整寄存器 store 后立即标量读回出现 `X` | 验证环境已修 | `verification/ara_verify/vector_signature.py` |
| V-02 | widening `.vx` 未先按源 SEW 截断标量 | 已修并定向通过 | `hardware/src/ara_dispatcher.sv` |
| V-03 | mask 目的寄存器错误继承数据 LMUL 合法性约束 | 已修并定向通过 | `hardware/src/ara_dispatcher.sv` |
| V-04 | mask 结果把非活动位错误合并进 old-vd | 已修并定向通过 | `hardware/src/masku/masku.sv` |
| V-05 | reduction seed/result 错误继承数据 LMUL | 已修并定向通过 | `hardware/src/ara_dispatcher.sv` |
| V-06 | fixed-point shift/round/narrow 饱和语义错误 | 已修并矩阵通过 | `fixed_p_rounding.sv`、`simd_alu.sv` |
| V-07 | LMUL 组只检查基址寄存器的 EEW | 已修并回归通过 | `hardware/src/ara_dispatcher.sv` |
| V-08 | averaging add/sub 丢失 `SEW+1` 中间位 | 已修并矩阵通过 | `hardware/src/lane/simd_alu.sv` |
| V-09 | mask logical 源/目的错误使用数据 LMUL | 已修并矩阵通过 | `ara_dispatcher.sv`、`masku.sv` |
| V-10 | `VMADC/VMSBC` restart prefix/tail 的 old-vd 合并错误 | 已修并定向通过 | `ara_dispatcher.sv`、`masku.sv` |
| V-11 | `vcpop/vfirst` 最后一片把 `index >= vl` 的尾位计入 | 已修并定向通过 | `hardware/src/masku/masku.sv` |
| V-12 | mask load/store 的 EVL、`vstart` no-op 判定错误 | 已修并定向通过 | `hardware/src/ara_dispatcher.sv` |
| V-13 | `VID/VIOTA/VCOMPRESS` 混淆数据组 EMUL 与 mask 源 LMUL | 已修并定向通过 | `ara_dispatcher.sv`、`masku.sv`、`lane_sequencer.sv` |
| V-14 | `vsetvl*` 的 VLMAX 使用 ELEN 而非 VLEN | 已修并定向通过 | `hardware/src/ara_dispatcher.sv` |
| V-15 | segment micro-op 的首个 `vl` 和字段寄存器步长错误 | 已修并定向通过 | `hardware/src/segment_sequencer.sv` |
| V-16 | indexed load/store 对非零 `vstart` 的边界字请求不一致 | 已修并定向通过 | `lane_sequencer.sv`、`vlsu/addrgen.sv` |
| V-17 | out-of-range `vslidedown` 仍等待不存在的源流 | 已修并定向通过 | `lane_sequencer.sv`、`sldu.sv`、`lane.sv` |
| V-18 | gather/compress 的 no-data 终止 token 处理不完整 | 已修并定向通过 | `lane_sequencer.sv`、`masku.sv` |
| V-19 | `VMVXS/VFMVFS` 标量返回与 MASKU 同时消费 MaskB | 已修并回归通过 | `hardware/src/ara.sv` |
| V-20 | 不同 SEW 的相邻 multiply 流可能发生流水线越序 | 已修并定向通过 | `hardware/src/lane/vmfpu.sv` |
| V-21 | widening/narrowing 与源目的重叠时 EEW 转换破坏源或 old-vd | 已修并边界回归通过 | `ara_dispatcher.sv`、`sldu.sv` |
| V-22 | widening MAC 高半区重叠时 accumulator 前缀未转换 | 已修并固定 ELF 越过 | `ara_dispatcher.sv`、`sldu.sv` |
| V-23 | widening reduction 的窄源/宽结果重叠及 tail 布局损坏 | 已修并 seed 5 越过 | `ara_dispatcher.sv`、`sldu.sv` |
| V-24 | unordered FP reduction 的空活动集合及跨 lane 活动生命周期错误 | 已修并由 seed 3/5 的非空、全空场景严格验证 | `vmfpu.sv`、`vector_fus_stage.sv`、`lane.sv`、`ara.sv` |
| V-25 | 全长 read-modify-write 错误跳过 mixed-EEW 目的组重排 | 已修并由 seed 7 及 seed 1/3/5 回归严格验证 | `hardware/src/ara_dispatcher.sv` |
| V-26 | PULP DivSqrt 在 directed overflow 上把无穷编码再次加一 | 已切换 THMULTI，并由 arithmetic seed 10 严格越过 | `hardware/src/lane/vmfpu.sv` |
| V-27 | SLDU 部分输出 entry 的逻辑进度计算错误，可能提前完成或永久残留 | 已修并由 seed 10、seed 1/7 回归验证 | `hardware/src/sldu/sldu.sv` |
| V-28 | `WAIT` 用请求是否写 `vd` 推断标量返回，可能把残留 MaskB valid 误认作 store 响应 | 已修并由 store corner 与严格随机回归通过 | `hardware/src/ara_sequencer.sv` |
| V-29 | AddrGen 与 lane/MASKU 分周期接收内存请求时，未保存各接收端的握手历史 | 已修，RVV corner 24/24 与 integer-stress seeds 7--10 严格通过 | `hardware/src/ara_sequencer.sv` |
| V-30 | masked store 用数据源旧 EEW 布局索引 predicate byte | 已修，load/store 10 seeds 通过 | `hardware/src/vlsu/vstu.sv` |
| V-31 | unit-stride segment restart 的首 micro-op 沿用普通 unit-stride 地址公式 | 已修并由 load/store/slide seed 9 严格通过 | `hardware/src/segment_sequencer.sv` |
| V-32 | restarted/segmented store 从非活动组头取得源布局标签 | 已修并由 load/store/slide seed 1 严格通过 | `ara_dispatcher.sv`、`segment_sequencer.sv` |
| V-33 | 非法向量访存异常未平衡 CVA6 pending-memory 记账 | 已修并由异常恢复定向测试与 checkpoint seed 9 严格通过 | `hardware/src/ara_dispatcher.sv` |
| V-34 | CVA6 标量 `fdiv/fsqrt` 的 PULP DivSqrt 结果与 Spike 相差 1 ULP | 已切换 THMULTI，原首错由 mixed-control 与 nightly 回放越过 | `hardware/deps/cva6/core/fpu_wrap.sv` |
| V-35 | 非零 `vstart` 的 unit-stride 尾部跨 VRF word 时过量消费 AXI byte | 已修，定向 load/store 与 nightly seeds 21/22 严格通过 | `hardware/src/vlsu/vldu.sv`、`hardware/src/vlsu/vstu.sv` |
| V-36 | indexed store 的算术位域去重误删 mixed-layout 数据源重排 | 已修，定向内存签名与 nightly seed 1 严格通过 | `hardware/src/ara_dispatcher.sv`、`apps/riscv-tests/isa/rv64uv/vstore_signature.c` |
| E-01 | non-bit-exact reduction 的不确定性未传播到后续结果 | 验证环境已修 | `verification/ara_verify/vector_commit.py` |
| E-02 | 严格 signature 的成功 `ecall` 在 RTL 中进入 trap handler 后重复执行 `test_done` | 验证环境已修 | `ara_commit_monitor.sv`、`random_rvv.py`、`rvv_replay.py` |
| E-03 | 逐向量比较器只检查已观察写回，漏掉部分目的字节完全未写 | 验证环境已修并新增单元测试 | `vector_commit.py`、`test_vector_commit.py` |
| E-04 | 已 trap 的 CVX 请求错误消耗下一条正常向量退休记录 | 验证环境已修并离线/在线严格验证 | `vector_commit.py`、`test_vector_commit.py` |
| E-05 | mask destination tail 在 `tu` 下被比较器误认为确定值 | 已修 knownness 传播，nightly seed 15 离线严格重算通过 | `vector_commit.py`、`test_vector_commit.py` |
| E-06 | 随机流生成 indexed store 的双 EEW 物理源重叠保留编码 | 验证环境已修；原 seed 16 合法化后严格通过 | `random_rvv.py`、`test_random_rvv.py` |
| E-07 | 不可观测 vector-to-scalar 返回仅跳过本条值比较，后续仍比较已分叉 GPR 状态 | 验证环境已修；nightly seed 5 离线重算通过 | `vector_commit.py`、`spike_trace.py` 及对应测试 |
| P-01 | `vcpop.m t2,v20` 为 37，Spike 为 41 | 待定位，可能是更早 mask 生产者 | 尚未修改 |
| P-02 | source 600 检查点出现跨目的组布局式差异 | 待区分 RTL 与检查器扰动 | 尚未修改 |

表中的“已修”只表示对应定向测试和已列出的相关回归通过，不等价于全部随机 profile、
全部 seed 或完整 RVV 1.0 指令空间已经通过。`vmin.vx`、早期 `vmulh.vx` 检查点
本身未发现功能错误；`vmfpu.sv` 的 V-20 是由后续不同 SEW multiply 回归暴露的
独立调度问题。

## 3. 检查器稳定性修正

### 3.1 现象

最初的检查点用向量 load 初始化寄存器，并连续执行整寄存器 store。紧随其后的
标量读回在 Ara 上出现未知值，差分只能运行 401 至 433 条退休指令。错误发生在
初始状态保存阶段，不能归因于任何随机算术指令。

### 3.2 原检查点序列

```asm
vs1r.v v0, (t0)
addi    t0, t0, 128
vs1r.v v1, (t0)
addi    t0, t0, 128
```

### 3.3 修改后的序列

```asm
vs1r.v v0, (t0)
csrr    t2, vl
addi    t0, t0, 128
vs1r.v v1, (t0)
csrr    t2, vl
addi    t0, t0, 128
```

Ara 对向量 CSR 读取使用现有的 wait-for-idle 路径。每个整寄存器 store 后读取
`vl`，可以在开始标量读回前建立完成边界。短诊断用例还把基于向量 load 的 VRF
初始化改成确定性的标量立即数和 `vslide1down.vx` 序列，使初始向量状态在两种
模型中均为已知值。

这些改动只用于验证环境，不是处理器功能修复。检查点会串行化向量执行，不能用来
测量性能、重叠、队列反压或真实并发行为。

## 4. Widening `.vx` 标量操作数位宽

### 4.1 现象与根因

第一处真实架构差异出现在：

```asm
vwaddu.wx v0, v16, a1
```

对于 widening `.wx` 指令，标量操作数应先截断到源 `SEW`，再按有符号或无符号
规则扩展到 `2*SEW`。原 dispatcher 直接传递完整 XLEN 值。在 `SEW=16` 时，
`a1` 的高位进入宽加法，污染结果的高半部分。

### 4.2 原逻辑

```systemverilog
ara_req.scalar_op      = acc_req_i.rs1;
ara_req.use_scalar_op  = 1'b1;
ara_req.conversion_vs1 = OpQueueConversionZExt2;
```

转换信息到达 VALU 时，VALU 已按 `2*SEW` 运算，无法恢复源 `SEW` 所需的截断。

### 4.3 修复逻辑

```systemverilog
function automatic elen_t widening_scalar_op(
    xlen_t scalar, vew_e source_eew, logic sign_extend
);
  elen_t scalar_elen;
  scalar_elen = elen_t'(scalar);
  unique case (source_eew)
    EW8:  widening_scalar_op = sign_extend
                              ? {{ELEN-8{scalar_elen[7]}}, scalar_elen[7:0]}
                              : {{ELEN-8{1'b0}}, scalar_elen[7:0]};
    EW16: widening_scalar_op = sign_extend
                              ? {{ELEN-16{scalar_elen[15]}}, scalar_elen[15:0]}
                              : {{ELEN-16{1'b0}}, scalar_elen[15:0]};
    EW32: widening_scalar_op = sign_extend
                              ? {{ELEN-32{scalar_elen[31]}}, scalar_elen[31:0]}
                              : {{ELEN-32{1'b0}}, scalar_elen[31:0]};
    default: widening_scalar_op = scalar_elen;
  endcase
endfunction
```

当 `conversion_vs1` 为 `ZExt2` 或 `SExt2` 时，dispatcher 先调用该函数，再把
结果送入后端。修复后的 `vwaddu.wx` 完整检查点与 Spike 一致。

## 5. Mask 目的寄存器的 LMUL 合法性

### 5.1 现象与根因

`vmslt.vx v25, v20, s5, v0.t` 在 `LMUL=4` 下被送入陷阱路径，因为 `v25`
没有按四寄存器组对齐。整数比较的目的结果是一个 mask 寄存器，与数据 LMUL
无关，因此不能对目的寄存器应用四寄存器组对齐约束。

### 5.2 原检查

```systemverilog
LMUL_4: if ((rs1 & 5'b00011) != 0 ||
            (rs2 & 5'b00011) != 0 ||
            (rd  & 5'b00011) != 0)
  illegal_insn = 1'b1;
```

### 5.3 修复逻辑

```systemverilog
function automatic logic integer_mask_result(ara_op_e op);
  integer_mask_result = op inside {
    VMSEQ, VMSNE, VMSLTU, VMSLT, VMSLEU, VMSLE, VMSGTU, VMSGT,
    VMADC, VMSBC, [VMANDNOT:VMXNOR]
  };
endfunction

LMUL_4: if ((rs1 & 5'b00011) != 0 ||
            (rs2 & 5'b00011) != 0 ||
            (!integer_mask_result(ara_req.op) &&
             (rd & 5'b00011) != 0))
  illegal_insn = 1'b1;
```

数据源仍按各自有效 LMUL 检查，mask 目的寄存器按单个架构寄存器处理。

## 6. Mask 结果的活动元素门控

### 6.1 现象与根因

合法性修复后，`vmslt.vx` 不再陷阱，但检查点仍有数值差异。Spike 读得
`0x000000000efdebf2`，Ara 读得 `0x0000fcc56efdebf2`。mask/background
合并路径把当前结果字中不属于活动结果范围的位也 OR 进了未扰动目的值。

### 6.2 原逻辑

```systemverilog
result_queue_mask_seq = masku_operand_m_seq |
                        {NrLanes*DataWidth{vinsn_issue.vm}} |
                        {NrLanes*DataWidth{
                          vinsn_issue.op inside {[VMADC:VMSBC]}
                        }};
background_data_init_seq = masku_operand_vd_seq | result_queue_mask_seq;
```

### 6.3 修复逻辑

```systemverilog
result_queue_active_mask_seq = '0;
for (int unsigned i = 0; i < NrLanes*DataWidth; i++) begin
  if (i < processing_cnt_q) result_queue_active_mask_seq[i] = 1'b1;
end

result_queue_mask_seq = masku_operand_m_seq |
                        {NrLanes*DataWidth{vinsn_issue.vm}} |
                        {NrLanes*DataWidth{
                          vinsn_issue.op inside {[VMADC:VMSBC]}
                        }};
if (vinsn_issue.use_vd_op)
  result_queue_mask_seq &= result_queue_active_mask_seq;
background_data_init_seq = masku_operand_vd_seq | result_queue_mask_seq;
```

合并掩码现在只覆盖当前结果字真正表示的活动元素。修复后 `vmslt.vx` 检查点通过。

## 7. Reduction seed 的有效 LMUL

### 7.1 现象与根因

`vredminu.vs v5, v28, v5, v0.t` 曾因 dispatcher 对 `vs1=v5` 应用
`LMUL=4` 对齐而陷阱。Reduction 的 `vs2` 是数据向量组，但 `vs1` seed 和
`vd` 结果各只占一个架构寄存器。

### 7.2 修复逻辑

```systemverilog
lmul_vs2 = csr_vtype_q.vlmul;
lmul_vs1 = csr_vtype_q.vlmul;

if (ara_req.op inside {[VREDSUM:VREDMAX]})
  lmul_vs1 = LMUL_1;
```

修复仅改变 seed 操作数的有效 LMUL；数据源 `vs2` 仍使用当前数据 LMUL。
`vredminu.vs` 检查点现已通过。

## 8. 定点移位、舍入和窄化语义

### 8.1 现象与根因

`vnclipu.wx` 最初产生未知位，随后得到 `0x0000b94c00000b6c`，而 Spike
期望 `0x0000ffff00000b6c`。原实现存在四个耦合问题：

- shift 为零时访问 `j-1`，产生非法位选择；
- RNE 没有正确考虑 sticky bit；
- `vnclip*` 按目的 `SEW` 划分操作数，而不是按源 `2*SEW`；
- 饱和判断发生在舍入增量之前，且溢出结果没有钳位到目的类型上限。

### 8.2 修复后的通用舍入判断

```systemverilog
function automatic logic rounding_increment(
  logic [63:0] value, logic [5:0] shift, vxrm_t mode
);
  logic retained_lsb, rounding_bit, sticky;
  logic [63:0] lower_mask;
  rounding_increment = 1'b0;
  if (shift != 0) begin
    retained_lsb = value[shift];
    rounding_bit = value[shift-1'b1];
    lower_mask   = (64'h1 << (shift-1'b1)) - 1'b1;
    sticky       = |(value & lower_mask);
    unique case (mode)
      2'b00: rounding_increment = rounding_bit;
      2'b01: rounding_increment = rounding_bit & (sticky | retained_lsb);
      2'b10: rounding_increment = 1'b0;
      2'b11: rounding_increment = !retained_lsb & (rounding_bit | sticky);
    endcase
  end
endfunction
```

以 `vnclipu` 为例，ALU 先对 `2*SEW` 源操作数舍入，再根据舍入后的值检测溢出，
最后在饱和时写入无符号最大值：

```systemverilog
automatic logic [31:0] rounded =
    (opb.w32[b] >> opa.w32[b][4:0]) + rm[b];
automatic logic sat = |rounded[31:16];
vxsat.w16[2*b + narrowing_select_i] = {2{sat}};
res.w16[2*b + narrowing_select_i] = sat ? 16'hffff : rounded[15:0];
```

修复后的 `vnclipu.wx` 检查点通过。

## 9. LMUL 寄存器组的 EEW reshuffle 检测

### 9.1 现象与根因

定点修复后，`vssrl.vv` 仍与 Spike 不一致。该指令使用 `LMUL=4` 的源寄存器
组，而组内各寄存器保存的内部 EEW 布局元数据并不完全相同。原 dispatcher
只检查组基址寄存器，因此可能漏掉其他组成员所需的 reshuffle。

原逻辑还用目的 EMUL 统一决定 reshuffle 次数，但 `vs1`、`vs2` 和 `vd` 的
有效 LMUL 可能不同。

### 9.2 修复逻辑

```systemverilog
function automatic logic group_needs_reshuffle(
  logic [4:0] base, vlmul_e lmul, vew_e target_eew
);
  group_needs_reshuffle = 1'b0;
  for (int unsigned i = 0; i < 8; i++) begin
    if (i < lmul_register_count(lmul) && (unsigned'(base) + i) < 32)
      group_needs_reshuffle |= eew_valid_q[base + i] &&
                               eew_q[base + i] != target_eew;
  end
endfunction
```

dispatcher 现在检查有效寄存器组的全部成员，并分别保存 `vs1`、`vs2` 和 `vd`
的有效 LMUL。reshuffle 计数上限跟随正在处理的操作数，而不是无条件跟随目的
EMUL。v14 日志中，`vssrl.vv` 及其后的 `vcpop.m` 检查点均通过。

## 10. Averaging add/sub 的中间结果位宽

### 10.1 现象与根因

v14 的第一处差异位于：

```asm
vasubu.vv v28, v16, v4
```

某个错误的 32 位检查点字中，Spike 为 `0xc1cfeb97`，Ara 为
`0x41cf6b97`。在 16 位元素下，每个错误元素相差 `0x8000`，且均发生在无符号
减法产生借位时。

RVV averaging subtraction 要求使用 `SEW+1` 位中间结果，再进行一位带舍入的
右移。原无符号路径在右移前丢弃第 `SEW` 位，导致发生借位时丢失结果最高位。
有符号 averaging 路径也必须显式构造符号扩展的 `SEW+1` 位中间结果。

### 10.2 修复逻辑

```systemverilog
automatic logic [16:0] sub_u =
    {1'b0, opb.w16[b]} - {1'b0, opa.w16[b]};
automatic logic signed [16:0] sub_s =
    $signed({opb.w16[b][15], opb.w16[b]}) -
    $signed({opa.w16[b][15], opa.w16[b]});
automatic logic round_u =
    average_rounding_increment(sub_u[1], sub_u[0], vxrm);
automatic logic round_s =
    average_rounding_increment(sub_s[1], sub_s[0], vxrm);

res.w16[b] = (op_i == VASUBU)
             ? (sub_u >> 1) + round_u
             : (sub_s >>> 1) + round_s;
```

同一 `SEW+1` 原则已用于 `vaadd`、`vaaddu`、`vasub` 和 `vasubu`，覆盖
SEW 8、16、32 和 64。v15 日志与 Spike 一致到第 23727 条退休指令，证明
`vasubu.vv` 检查点和后续 `vmulh.vx` 检查点均已通过。

## 11. Mask logical 指令的有效 LMUL

### 11.1 现象与根因

平均运算修复后，下一条 `vmxor.mm v2, v15, v28` 被 Ara 判为非法。Mask
logical 指令的两个源和目的都是单个 mask 寄存器，不应继承数据 `vtype` 中的
`LMUL=4`。原逻辑错误地对 `v15`、`v28` 和 `v2` 应用了四寄存器组约束。

### 11.2 修复逻辑

```systemverilog
if (ara_req.op inside {[VMANDNOT:VMXNOR]}) begin
  lmul_vs1 = LMUL_1;
  lmul_vs2 = LMUL_1;
end
```

同时，`integer_mask_result()` 把 `[VMANDNOT:VMXNOR]` 归入单 mask 目的结果，
reshuffle 检测和目的布局元数据也按 `LMUL_1` 处理。v16 仿真中该指令不再陷阱，
整个软件用例可以执行到 `tohost` 并显示 `SUCCESS`。

在 v16 阶段，严格检查点仍在 `vmxor.mm` 的结果中发现数据差异，因此当时只能确认
合法性和有效 LMUL 已修。后续又修正了 mask 活动窗口、old-vd 合并及 MaskB 消费
关系；`vmask_logical_matrix` 的八种 mask logical directed matrix 已全部通过，
短随机严格检查也越过了该位置。因此 `vmxor.mm` 不再列为当前未解决问题，但这一
结论仍限于已有 directed matrix 和已运行 seed，不扩展为全部 mask 状态空间证明。

## 12. 当前未解决问题

### 12.1 固定旧 ELF 的 `vcpop.m` 差异

widening MAC 高半区重叠修复后，同一 ELF 的严格比较在 5086 条指令后出现：

```text
PC:      0x0000000080001d7a
指令:    vcpop.m t2, v20
Spike:   t2 = 41
Ara:     t2 = 37
```

这一结果只证明 `vcpop.m` 看到的 `v20` 中有四个有效位不同，不能证明 popcount
电路本身错误。已有独立 `vcpop` 尾部边界测试通过；更可能的两类原因是更早的
mask 生产者写错 `v20`，或内部布局在后续消费前失配。恢复验证时应先定位最后一个
写 `v20` 且其后状态仍与 Spike 一致的动态指令，再判断是否需要修改 MASKU。

### 12.2 source 600 检查点差异

选择 source 600 至 610 的检查点运行，在下列指令之后首先失败：

```asm
vslidedown.vi v16, v16, 7
```

但差异来自签名地址 `0x80008208`，即 `v4` 的第 8 字节，而该指令只写
`v16-v19`。Spike 期望 `0x0000000200000001`，Ara 读得
`0x0002000000010000`，表现为字节/元素布局置换。source 599 的另一独立检查点
运行可以通过，但该检查点自身执行全部 `vs1r.v`，可能改变内部 EEW 布局，因而
不能直接证明无检查点程序在 source 599 时状态也相同。

当前必须保留三种可能：

1. 早于 source 600 的指令已经使 `v4` 数据与 EEW 元数据失配；
2. source 600 引发了与目的组无关的元数据或共享资源错误；
3. 整寄存器检查点在混合 EEW 状态下保存 `v4` 时发生验证环境扰动。

本轮没有修改 `vslidedown` RTL，也没有新增针对它的结论。下一次恢复时，需要用
不写 VRF 的定点探针观察 source 600 前后的 `eew_q[4]`、SLDU 请求和 `vs1r.v v4`
实际 EEW，随后再决定修 RTL 或检查器。

### 12.3 暂停点

本报告整理完成后按用户要求暂停验证。当前没有后台 VCS 回归由本轮启动；P-01、
P-02 均未宣称解决。软件自检 `SUCCESS`、directed test `PASS` 与严格差分
`MATCH` 是三种不同证据，后续仍应分别报告。

## 13. 当前比较能力与边界

当前环境能够严格比较：

- 每条标量退休指令的 PC 和指令编码；
- 每条指令的 GPR/FPR 写回寄存器集合和值；
- 非压缩标量 load/store/AMO 的地址、字节掩码和 store 数据；
- 检查点模式下，每条生成的 RVV 指令后的完整 `v0-v31`；
- 检查点模式读取到的 `vl`、`vtype`、`vstart`、`vcsr` 和 `fcsr`；
- CVXIF 请求/响应以及 Ara 后端 uop 分配和完成的生命周期一致性。
- 非侵入模式下，按 `arch_seq` 聚合并反 shuffle 后的全部已接受、值确定 VRF
  写回字节，以及整条目的写回完全缺失。

当前尚未严格覆盖：

- 任意 vector store 目标内存在每条指令后的即时状态；
- 压缩标量访存的独立地址/掩码解码检查；
- 除检查点显式读取项以外的全部 CSR 状态；
- 非侵入轨迹中部分 byte-enable 应写而未写的完整活动字节证明。

当前 `vid/arch_seq` 已保留到最终 VRF 写回观察点，因此可在不改动 ELF 的情况下
直接定位错误写回值。检查点方法仍用于完整寄存器/CSR 快照，但会改变原程序执行
时序；非侵入路径不会产生这种扰动。两者尚未完全等价：现有写回轨迹严格检查
“实际接受的字节”，要证明某条指令所有应写活动字节均出现，还需加入基于
`vl/vstart/vtype/mask` 的期望写掩码。

## 14. Widening MAC 高半区重叠时的 accumulator 布局

### 14.1 现象与首错定位

`ara_dsa_rvv1_mixed_control`、seed 1 在 `SEW=16`、`LMUL=4`、`VL=79`、
`tu,mu` 下最初表现为 masked slide 和后续 XOR 的结果错误。逐级检查 mask 输入、
slide 写回和动态执行路径后，确认这些均为下游症状。使用单检查点独立运行后，首个
直接产生错误架构状态的指令为静态向量指令 2046：

```asm
vwmaccu.vx v0, a7, v4
```

该指令的宽目的/累加器组为 `v0-v7`，窄源组为 `v4-v7`。RVV 允许窄源与宽目的
的高编号部分重叠。`VL=79` 时，实际活动的 32 位目的元素只占 `v0-v2`，活动的
16 位源元素位于 `v4-v5`，两者在本次操作的活动寄存器范围内并不相交。

紧邻指令之前的 source 2045 完整状态检查通过；执行 `vwmaccu.vx` 后，Spike 在
`v0` 低 64 位保存两个 32 位元素：

```text
Spike: 0x0000027b0000027b
Ara:   0x00000000027b027b
```

Ara 的结果仍呈现窄元素布局。修复前单检查点运行在第 2810 条严格比较处失败，失败
位置就是该指令后的 `v0-v31` 状态读回。

### 14.2 RTL 根因

dispatcher 检测到合法 widening 高半区重叠后，会禁止对整个 `vd` 组执行普通
reshuffle，以免在窄源被消费前把 `v4-v7` 改成宽布局。该规则对不读取旧目的值的
widening add/sub 是必要的，但 `vwmacc*` 还通过 `use_vd_op` 把 `vd` 作为宽
accumulator 读取。原 overlap 路径跳过了整个目的组转换，也没有单独转换位于窄源
之前的安全目的前缀，因此 VALU 以 32 位 accumulator 语义读取了仍按旧 EEW 排列
的 `v0-v2`。

不能简单让该请求回到普通多操作数 reshuffle。这样会先转换整个 `v0-v7`，再恢复
窄源，既增加无效转换，也会破坏现有 overlap 状态机的请求推进；实际回归中该方案
使原 `vwiden_overlap_edges` 无法在 300 秒限制内完成，因此已撤销。

### 14.3 修复行为

overlap 上下文新增 `overlap_prefix_vl`，表示原指令发射前可以安全转换为目的 EEW
的目标元素前缀。原 narrowing overlap 的行为保持不变，其前缀仍为 `vstart` 以下
需要保留的元素。对于读取 `vd` 的 widening MAC，dispatcher 计算高半区窄源在
宽目的组中的起始元素；只有当全部活动目的元素均位于该边界之前时，才把前缀设为
当前 `vl`。

本例中高半区源从宽目的元素 128 开始，而 `vl=79`，因此状态机先通过
`OVERLAP_PREFIX_FIXUP` 把 `v0-v2` 的 79 个 accumulator 元素转换为 32 位布局，
不触碰 `v4-v7`。随后继续使用原有流程：必要时捕获活动/尾部边界字，发射原
`vwmaccu.vx`，等待其完成，再由 `OVERLAP_FIXUP` 恢复未更新尾部并统一目的 EEW
元数据。若活动目的已经进入重叠源区域，则不启用这一有限前缀转换，仍保留原有
特殊 overlap 行为。

### 14.4 定向测试与回归结果

`vwiden_overlap_edges.c` 新增 `vwmaccu.vx` 高半区重叠测试。测试先用 `e32,m8`
初始化 `v8-v15` accumulator，再用 `e16,m4` 把窄源装入 `v12-v15`，最后以非零
标量 7 和 `vl=79` 执行 widening MAC。它同时检查 79 个活动结果以及被窄源装载
覆盖后的未扰动尾部。

```text
rvv:vwiden_overlap_edges      PASS  49.28 s
rvv:vwiden_lmul4_edges        PASS  57.26 s
rvv:vnclip_edges              PASS  46.43 s
rvv:vreduction_overlap_edges  PASS  16.08 s
Python verification tests     PASS  65/65
```

为避免随机程序重新生成后因代码布局变化走不同控制路径，最终 A/B 验证复用了修复前
失败运行的同一个 ELF 和 Spike commit log，只替换 RTL `simv`。修复后的仿真成功
到达 `tohost`，并越过原 `vwmaccu.vx` 检查点；严格匹配长度由 2810 条增加到
5086 条。新的第一处可见差异位于更晚的：

```asm
vcpop.m t2, v20
```

该处 Spike 返回 41，Ara 返回 37。当前证据尚不能判断是 `vcpop.m` 本身还是更早
的 `v20` mask 生产者错误，因此本轮未对其修改 RTL。后续若恢复随机回归，应从该
指令前的最后一个 `v20` 写入者开始做单检查点动态前驱定位。

### 14.5 检查点使用约束

完整向量检查点使用 `vs1r.v` 保存所有寄存器，会保持架构位值，但可能改变 Ara
内部 EEW 布局；插入代码还会改变随机程序的地址布局和动态调用路径。因此，多检查点
同次运行只适合观察，不应作为无扰动二分证据。本缺陷的确认使用了“目标前一指令与
目标指令相邻检查”“目标单检查点独立运行”和“相同 ELF 固定重放”三类证据。

## 15. 已修改源码总览

当前 worktree 不只包含功能修复，也包含验证 trace 和新激励。下表区分各文件的
主要职责；`FOR_VERIFY` 下的 `$display` 探针不参与综合，也不应被当成功能修复。

| 文件 | 已完成的功能修改 | 验证相关修改 |
|---|---|---|
| `hardware/src/ara_dispatcher.sv` | 指令合法性、每操作数 LMUL/EMUL、VLMAX、mask memory EVL、EEW group reshuffle、widen/narrow overlap 协议 | 架构请求序号与可选 decode/reshuffle/overlap trace |
| `hardware/src/ara.sv` | `VMVXS/VFMVFS` 的 MaskB 单一消费者仲裁 | 无 |
| `hardware/src/segment_sequencer.sv` | segment 字段寄存器步长及非零 `vstart` 首 micro-op | 无 |
| `hardware/src/lane/fixed_p_rounding.sv` | RVV 四种 `vxrm` 舍入增量 | 无 |
| `hardware/src/lane/simd_alu.sv` | narrowing saturation 与 averaging `SEW+1` 中间结果 | 定点运算 trace |
| `hardware/src/lane/lane_sequencer.sv` | mask/索引边界字请求、slide OOR no-source、gather/compress no-data token | slide、mask、indexed 请求 trace |
| `hardware/src/lane/lane.sv` | no-source slide 不向共享 SLDU/AddrGen 仲裁器压入空操作数 | lane 状态 trace |
| `hardware/src/lane/vmfpu.sv` | 不同 SEW multiply 的可变有效延迟互锁 | multiply/widening MAC trace |
| `hardware/src/masku/masku.sv` | mask 活动范围、carry old-vd、`vcpop/vfirst` tail、VID/VIOTA/compress/gather 数据路径 | 多组可选 MASKU trace |
| `hardware/src/sldu/sldu.sv` | OOR slide 零源生成、部分 EEW 修复和 overlap snapshot | slide/overlap trace |
| `hardware/src/vlsu/addrgen.sv` | indexed 操作按 lane sequencer 提供的聚合边界字消费 | indexed 地址 trace |
| `hardware/src/vlsu/vstu.sv` | mixed-EEW masked store 的数据/predicate 独立物理索引 | 可选 store data/stall trace |
| `verification/ara_verify/vector_signature.py` | 插入完整 VRF/CSR/memory signature 与选择性检查点 | 检查点元数据 |
| `verification/ara_verify/vector_commit.py` | 非侵入式逐写回严格比较、未知传播及 trapped request 映射 | 首错、未完成与异常请求报告 |
| `verification/ara_verify/random_rvv.py` | 生成、Spike/RTL 运行、严格比较及首错归属 | JSON 报告与重放信息 |
| `apps/riscv-tests/isa/rv64uv/*.c` | 新增和补强 directed edge tests | 软件自检 oracle |

功能代码中仍存在若干 `FOR_VERIFY` 调试块，尤其是 dispatcher、MASKU、SLDU、
operand requester 和 VMFPU 中的可选 plusarg trace。它们用于继续定位 P-01/P-02，
不改变非 `FOR_VERIFY` 综合逻辑；最终合入前应单独审查并删除不再需要的临时探针。

## 16. Mask 语义相关修复

### 16.1 活动位窗口与 `VMADC/VMSBC` old-vd

mask 结果不是普通数据向量：一个架构 mask 寄存器包含逐元素 bit，当前处理字中只有
`[vstart, vl)` 对应的位允许被更新。修复后 MASKU 先构造活动位窗口，再决定哪些位
使用新 ALU 结果、哪些位保留 old-vd。核心原则如下：

```systemverilog
result_queue_active_mask_seq = '0;
for (int unsigned i = 0; i < NrLanes*DataWidth; i++) begin
  if (i < processing_cnt_q)
    result_queue_active_mask_seq[i] = 1'b1;
end

if (vinsn_issue.use_vd_op)
  result_queue_mask_seq &= result_queue_active_mask_seq;
```

`VMADC/VMSBC` 即使 `vm=1` 也可能因 `vstart != 0` 或 tail-undisturbed 需要读取 old-vd。
dispatcher 因此不再把“非 predicated”误解为“不需要目的旧值”。对应 directed
`vmask_carry_tail_edges` 已通过，包含 tail-undisturbed 与 carry-in 边界。

### 16.2 `vcpop/vfirst` 最后一片 tail 门控

原 popcount/first datapath 直接消费固定并行宽度的一片 mask。最后一片不足完整宽度
时，VRF 中 `vl` 以上的尾位仍可能为 1，并被错误计数或提前终止搜索。修复直接以
当前剩余元素数门控每一位：

```systemverilog
for (genvar i = 0; i < VcpopParallelism; i++) begin
  assign vcpop_slice[i] = vcpop_slice_raw[i] &&
                          (issue_cnt_q > vlen_t'(i));
end
for (genvar i = 0; i < VfirstParallelism; i++) begin
  assign vfirst_slice[i] = vfirst_slice_raw[i] &&
                           (issue_cnt_q > vlen_t'(i));
end
```

这项修改由 `vcpop` 和 `vfirst` 的尾部边界 directed test 验证。它不能直接解释
当前 P-01，因为 P-01 的差值也可能来自 `v20` 更早的生产者。

### 16.3 MaskB 的单一消费者

`VMVXS/VFMVFS` 从 lane 0 的 MaskB 队列把元素 0 返回标量核。原连接同时允许
MASKU old-vd spill register 接收同一 valid/ready 事件，导致一个 payload 被两个
逻辑消费者竞争。修复在这两类操作期间屏蔽 MASKU 侧 valid：

```systemverilog
masku_operand_valid_masku = masku_operand_valid;
masku_operand_ready_lane  = masku_operand_ready_masku;
masku_operand_ready_lane[0][1] =
    masku_operand_ready_masku[0][1] | pe_scalar_resp_ready;

if (pe_req.op inside {[VMVXS:VFMVFS]})
  masku_operand_valid_masku[0][1] = 1'b0;
```

标量返回仍参与原 ready 合并，但 MASKU 不再错误截获该字。相关 scalar handoff 与
mask corner regression 已通过。

## 17. LMUL、EMUL 与配置状态修复

### 17.1 数据组和 mask 单寄存器分离

修复后的 dispatcher 不再对一条指令使用单一 LMUL 假设。典型规则是：

```systemverilog
// VIOTA/VID 写普通数据向量组。
ara_req.emul = csr_vtype_q.vlmul;

// mask 源始终只占一个架构寄存器。
if (ara_req.op inside {[VMSBF:VMSIF], VIOTA})
  lmul_vs2 = LMUL_1;
if (ara_req.op == VCOMPRESS)
  lmul_vs1 = LMUL_1;

// reduction seed 为单寄存器，数据源仍跟随数据 LMUL。
if (reduction_result(ara_req.op))
  lmul_vs1 = LMUL_1;
```

因此合法性、操作数请求长度、目的元数据更新分别使用 `lmul_vs1`、`lmul_vs2` 和
`ara_req.emul`。`vid_queue_edges`、`vcompress_edges`、
`vreduction_lmul_edges` 和 `vreduction_overlap_edges` 已覆盖这些差异。

### 17.2 `vsetvl*` 的 VLMAX

VLMAX 的架构定义是 `LMUL * VLEN / SEW`。原实现局部使用了与 ELEN 相关的宽度，
在 `VLEN != ELEN` 的配置下返回错误 `vl`。当前代码由 `VLENB` 计算：

```systemverilog
automatic int unsigned vlmax = VLENB >> csr_vtype_d.vsew;
unique case (csr_vtype_d.vlmul)
  LMUL_2:   vlmax <<= 1;
  LMUL_4:   vlmax <<= 2;
  LMUL_8:   vlmax <<= 3;
  LMUL_1_2: vlmax >>= 1;
  LMUL_1_4: vlmax >>= 2;
  LMUL_1_8: vlmax >>= 3;
  default:;
endcase
```

此前 `vsetivli` 路径虽然使用同一 `vlmax`，却把五位立即数 AVL 直接写入 `vl`，
没有执行 VLMAX 约束。原 28 项测试的前 26 个合法配置均未使立即数超过 VLMAX，
因此没有暴露该缺陷；第 27 项 `e32,mf2,AVL=20` 的 VLMAX 为 16，修复前错误返回
`vl=20`。当前实现对立即数采用 `min(AVL,VLMAX)`；这既满足 `AVL>=2*VLMAX`
时必须返回 VLMAX 的规则，也是在中间 strip-mining 区间内允许的选择。

测试本身也已补强：第 27 项不再把指令写回值误当作原始 AVL，而是以常量 20
检查合法 VL 区间，并独立比较 `rd` 返回值与 `vl` CSR。包含该严格检查的完整
`vsetivli` 28 项定向测试在 61.02 秒通过；`vsetvli` 与 `vsetvl` 的既有 directed
tests 继续覆盖寄存器 AVL 路径。

### 17.3 Mask memory 的有效长度和 no-op

`vlm.v/vsm.v` 访问 `ceil(vl/8)` 个字节，不是 `vl` 个数据元素。`vstart` 对这类
指令按 mask byte progress 使用。dispatcher 现在先转换 EVL，再判断是否为空：

```systemverilog
ara_req.vl         = (csr_vl_q >> 3) + |csr_vl_q[2:0];
ara_req.vtype.vsew = EW8;
mask_mem_noop      = csr_vstart_q >= ara_req.vl;
```

这样 `vstart >= ceil(vl/8)` 时直接走合法完成路径，不向 VLSU 发出空请求。
`vmask_mem_emul_edges` 与严格 load/store 前缀回归已越过原首错。

## 18. `vstart`、segment 与 indexed memory

### 18.1 Segment micro-op 的首元素和字段寄存器

segment sequencer 把一条 `vlseg/vsseg` 拆成多个字段 micro-op。原首 micro-op 固定
`vl=1`，在 `vstart>0` 时会形成 `vl<=vstart` 的空请求；字段寄存器地址又只加
`segment_cnt`，没有乘字段的 EMUL。修复为：

```systemverilog
ara_req_o.vl = ara_req_i.vstart + 1'b1;

unique case (ara_req_i.emul)
  LMUL_2: segment_reg_offset = segment_cnt_q << 1;
  LMUL_4: segment_reg_offset = segment_cnt_q << 2;
  LMUL_8: segment_reg_offset = segment_cnt_q << 3;
  default: segment_reg_offset = segment_cnt_q;
endcase
ara_req_o.vs1 = ara_req_i.vs1 + segment_reg_offset;
ara_req_o.vd  = ara_req_i.vd  + segment_reg_offset;
```

`vsegment_emul_edges` 已覆盖非零 `vstart` 与多字段 EMUL。

### 18.2 Indexed 操作的聚合边界字

indexed offset 在 lane 间以聚合 VRF word 被消费。原 lane 与 AddrGen 分别伪造
低 lane valid，遇到 `vstart` 落在字中时可能少取或重复取 offset。修复把边界对齐
统一放在 lane sequencer：从包含 `vstart` 的首聚合字开始，请求覆盖到 `vl` 的完整
聚合字；AddrGen 只在所有 lane word 到齐时接收。

```systemverilog
idx_first_aggregate_word = pe_req.vstart / idx_elems_per_aggregate_word;
idx_aggregate_word_count =
    ((pe_req.vl + idx_elems_per_aggregate_word - 1) /
     idx_elems_per_aggregate_word) - idx_first_aggregate_word;

operand_request[SlideAddrGenA].vstart =
    idx_first_aggregate_word * idx_elems_per_lane_word;
operand_request[SlideAddrGenA].vl =
    (idx_first_aggregate_word + idx_aggregate_word_count) *
    idx_elems_per_lane_word;
```

`vindexed_vstart_edges`、`vluxei`、`vsuxei` 与 segment 相关回归均通过。该修改还
消除了原 AddrGen 中“把未提供数据的 lane valid 强制置 1”的不对称处理。

## 19. Slide、gather 与 compress 的无源请求

### 19.1 Out-of-range `vslidedown`

当 `offset >= VLMAX` 时，所有活动结果按规范为 0，不应再从 VRF 请求源组。原路径
虽然能在部分情况下产生零值，却仍等待共享 SLDU 操作数流，可能死锁。修复在 lane
sequencer 与 SLDU 同时识别该条件：

```systemverilog
slide_down_source_oor = pe_req.op == VSLIDEDOWN &&
                        !pe_req.use_scalar_op &&
                        pe_req.stride >= slide_vlmax;

vfu_operation_d.skip_sldu_operand = slide_down_source_oor;
operand_request_push[SlideAddrGenA] = pe_req.use_vs2 &&
                                      !slide_down_source_oor;
```

SLDU 在此模式下把源字置零，并在结果队列可接收时推进，不等待
`sldu_operand_valid`。`vslide_mask_edges` 已通过 offset、mask、tail 与边界组合。
P-02 的原地 `vslidedown.vi v16,v16,7` 并非 OOR，不能由本项已修事实推出结论。

### 19.2 Gather/compress 的 no-data token

out-of-range gather 元素以及 compress 的结束标志可能没有对应 VRF 数据请求，但
下游仍需要一个顺序 token 来推进 FIFO 和结束检测。当前请求结构保留 `no_data`
属性：索引 FIFO 始终推进，只有真实数据项增加源请求计数；末尾 OOR 项显式发送
no-data 终止 token。`vrgather_edges` 与 `vcompress_edges` 已通过。

## 20. EEW 布局与重叠修复协议

### 20.1 只检查活动源寄存器

每个物理向量寄存器都有内部 EEW 布局元数据。对 LMUL 组进行操作时，必须检查本次
`[vstart,vl)` 实际覆盖的全部成员，而不是只看组基址，也不应转换纯 tail 成员并
破坏合法重叠源。当前辅助逻辑先求活动首寄存器和数量：

```systemverilog
active_group_needs_reshuffle |=
    eew_valid_q[base + first_register + i] &&
    (eew_q[base + first_register + i] != target_eew);
```

reshuffle 次数分别跟随 `vs1/vs2/vd` 的有效 LMUL。该规则解决了 `vssrl.vv`、
部分 VID/VIOTA、whole-register move 和非零 `vstart` 下漏转或过转的问题。

### 20.2 Widening/narrowing 合法重叠

普通“先转换整个目的组再执行”会破坏仍需读取的重叠源。dispatcher 因此识别：

```systemverilog
legal_widen_overlap = ara_req.cvt_resize == CVT_WIDE &&
                      widening_high_overlap(...);
legal_narrow_overlap = narrow_low_overlap_alias &&
                       reshuffle_req_d[0];
```

特殊状态机保存旧 EEW 元数据，必要时捕获跨 active/tail 边界的一个聚合 VRF word，
发射原架构指令后仅修复未写区域。对于 narrowing，安全前缀为 `vstart`；对于读取
old-vd 的 widening MAC，只有活动目的全部位于高半区窄源之前时才设置：

```systemverilog
if (legal_widen_overlap && ara_req.use_vd_op &&
    unsigned'(ara_req.vl) <= overlap_start_element)
  overlap_prefix_vl_d = ara_req.vl;
```

这保证 accumulator 前缀按宽 EEW 读取，同时不转换重叠窄源。详细首错和固定 ELF
证据见第 14 节。`vnclip_edges`、`vreduction_overlap_edges`、
`vwiden_lmul4_edges` 和 `vwiden_overlap_edges` 均已通过相关边界回归。

## 21. 运算流水线修复

### 21.1 不同 SEW multiply 的互锁

同一个 VMFPU 中不同 SEW multiplier 的有效延迟不同。仅比较静态 op latency 不足以
覆盖相邻 multiply 属于不同 SEW、不同 `id` 的情况，后发请求可能先到结果仲裁点。
当前把这一组合纳入 `latency_problem_d`：

```systemverilog
latency_problem_d =
    (vinsn_issue_lat_d < vinsn_processing_lat_d) ||
    ((vinsn_issue_d.op inside {[VMUL:VSMUL]}) &&
     (vinsn_processing_d.op inside {[VMUL:VSMUL]}) &&
     (vinsn_issue_d.vtype.vsew != vinsn_processing_d.vtype.vsew) &&
     (vinsn_issue_d.id != vinsn_processing_d.id)) ||
    (((vinsn_issue_d.op inside {VFDIV, VFRDIV, VFSQRT}) ||
      (vinsn_processing_d.op inside {VFDIV, VFRDIV, VFSQRT})) &&
     (vinsn_issue_d.id != vinsn_processing_d.id));
```

该互锁只约束可能越序的不同指令，不把同一指令的 lane 内分片错误串行化。

### 21.2 Fixed-point 舍入与 averaging

第 8、10 节给出了核心实现。新增 `vaverage_matrix` 覆盖四种 averaging 指令、
四种 `vxrm` 和多个 SEW；`vnclip_edges` 覆盖 shift=0、sticky/tie、饱和、mask、
tail、`vstart` 与源目的低半区重叠。两组测试均已通过当前定向回归。

## 22. 已补充的验证激励

本轮工作期间新增或显著补强的 directed tests 包括：

- `vaverage_matrix`：`vaadd/vaaddu/vasub/vasubu`、四种 `vxrm`、多 SEW；
- `vmask_logical_matrix`：八种 mask logical、不同 VL/LMUL/vstart/policy；
- `vmask_carry_tail_edges`、`vmask_compare_edges`：carry/compare 的 old-vd 与活动位；
- `vnclip_edges`：窄化、舍入、饱和、重叠和 restart；
- `vreduction_lmul_edges`、`vreduction_overlap_edges`：seed/result LMUL 与重叠；
- `vrepair_edges`、`vwiden_lmul4_edges`、`vwiden_overlap_edges`：EEW 修复和宽窄重叠；
- `vid_queue_edges`、`viota`：数据组 EMUL、无源 VID 和队列边界；
- `vslide_mask_edges`：mask/tail/OOR/非整字边界；
- `vrgather_edges`、`vcompress_edges`：OOR/no-data/结束 token；
- `vsegment_emul_edges`、`vindexed_vstart_edges`：segment/indexed 的 EMUL 与 restart；
- `vmask_mem_emul_edges`、`vstore_signature`：mask memory 和 store 后内存签名；
- `fp_nanbox_div`：FP NaN-box 与除法/舍入路径。

另外，原 `vasub/vasubu/vcompress/vcpop/vfirst/viota/vlsseg/vssseg/vmvxs/vrgather/
vslidedown` 等测试已增加 VLEN 条件、边界 case 或回归触发序列。随机环境支持
arithmetic、load/store、mixed-control 等 profile、固定 seed 重放、完整退出签名、
选择性逐 RVV 检查点和 vector store 后内存签名。

## 23. 已有验证证据与结论边界

下表记录 2026-08-08 初始 campaign 阶段引用的代表性结果；它们是后续根因定位的
起点，不代表完成第 24--39 节修复后的当前 RTL 状态。

| 结果目录 | 关键结果 | 能证明的范围 |
|---|---|---|
| `rvv-mask-architectural-matrix-v2` | `vmask_logical_matrix PASS` | mask logical directed matrix 通过 |
| `rvv-corners-after-maskb-fix` | 19 个 corner tests 全 PASS | mask、average、repair、slide、gather、compress、segment 等组合回归 |
| `vsetvl-vlen-fix` | `vsetvli`、`vsetvl` PASS | 当前 VLEN 配置下 VLMAX directed 通过 |
| `indexed-vstart-fix-run2_20260808` | `vindexed_vstart_edges PASS` | indexed 非零 `vstart` directed 通过 |
| `vwiden-overlap-acc-prefix-final_20260808` | `vwiden_overlap_edges PASS` | widening overlap/accumulator 边界通过 |
| `widen-acc-prefix-focused-regression_20260808` | 三项 focused regression PASS | widening 修复未破坏列出的窄化/reduction 测试 |
| `mixed-control-seed1-vwmaccu-prefix-fix_20260808` | 5086 条匹配后停在 `vcpop.m` | 固定 ELF 已越过 widening MAC 原首错 |
| `mixed-control-seed1-checkpoints-600-610_20260808` | source 600 检查点 FAIL | 暴露 P-02，但不足以证明 slide RTL 根因 |

该阶段只能声明“已定位并修复多类定向 RVV 语义缺陷，且固定随机 ELF 的严格匹配
前缀显著推进”，不能声明“全部激励通过”或“RVV 1.0 全指令已验证”。P-01/P-02
及其后续暴露问题的修复和严格比较证据见第 24--39 节；完整 profile × seed 回归仍
应以严格状态比较而非软件 `SUCCESS` 作为最终通过条件。

## 24. 非侵入式逐向量指令写回对比

原检查点方式会在测试程序中插入 `vs1r.v`、`vcpop.m`、CSR 读取和标量签名检查，
因此可以观察状态，但会改变原始指令流、VRF EEW、完成边界和后端并发。本轮新增的
路径不修改 ELF：`operand_requester` 只在 ALU、MFPU、MASKU、SLDU 或 VLDU 的结果
真正赢得 VRF 仲裁时导出 `vid/address/byte-enable/data`；提交监视器再使用已有的
`vid -> arch_seq` 生命周期，把普通 uop、reshuffle uop 和 segment uop 重新归并到
产生它们的架构向量指令。

离线比较器先通过 RVFI retirement 为 `arch_seq` 补上动态 PC，再定位相同 PC 和编码
的 Spike commit。对于每次已接受写回，它根据 lane、VRF word address 和目的 EEW
逆转 Ara 的字节 shuffle，得到 `(vreg, byte)`，并与该架构指令执行后的 Spike 向量
状态逐字节比较。若失配，JSON 会给出架构序号、PC、指令编码、向量寄存器字节、
expected/actual、cycle、`vid`、lane、写回单元、VRF 地址和 EEW。含 `X/Z` 的仿真
字节保留为 unknown，不会被伪造为 0；结果同时报告确定比较字节和 unknown 数量。

Ara 的 VRF shuffle 不只是跨 lane 转置：`EW16` 和 `EW8` 还会对每个 64-bit lane
内部的元素槽位索引做 bit reversal。比较器最初遗漏了这一步，因而在完整刺激尾部
把 `vmin.vx` 的 element 4 与 element 8 对调，并连续误报七条指令失配。当前
`_deshuffle_byte` 已按 `ara_pkg::shuffle_index` 的实际规则同时逆转 lane 分布和
lane 内槽位顺序；专门覆盖 `EW16/EW8` 交换位置的单元测试可防止该类误报回归。

端到端验证随后使用未插入检查点、未选择单条指令的完整
`ara_dsa_rvv1_signature_smoke` seed 1：

```text
scalar retirement prefix = 2251 instructions
vector destination requests = 521
compared vector requests = 521
compared known VRF bytes = 39620
skipped X/Z bytes = 30720
first mismatch = none
vector result = PASS
```

结果保存在 `verification/out/vector-commit-full-signature-smoke_20260808/tests/ara_dsa_rvv1_signature_smoke_0/vector_commit_comparison.json`。
这证明该完整刺激中“架构请求归属、后端 uop 聚合、最终 VRF 写回观察、EEW 反
shuffle、RVFI/Spike 动态对齐”链路已经闭合。当前严格结论是：该次运行所有被 VRF
接受且值确定的写回字节均与 Spike 一致，并能发现整条目的写回缺失；尚未声称仅凭
该轨迹可证明部分 byte-enable 缺失，也未把 vector store 的目标内存效果并入同一
事件，后者继续由 store signature 路径检查。

## 25. Widening reduction overlap 与空活动集合

### 25.1 窄源和宽结果重叠

seed 5 的 `vwredsumu.vs v1,v0,v31` 以 EW8 读取 `v0-v3`，同时以 EW16
写 `v1[0]`。原 dispatcher 允许该重叠，但禁止目的 reshuffle，并假定 reduction
除 element 0 外均为 agnostic。实际指令采用 tail-undisturbed，`v1` 未写区域仍保留
EW8 物理布局；指令结束后却把整个 `v1` 的 EEW 元数据改成 EW16。后续 EW8 请求
按错误元数据转换 tail，最终在 `vmv.v.v` 暴露字节差异。

当前 widening reduction 复用 overlap-repair 状态机：执行前保存跨 active/tail
边界的聚合字，按旧窄布局完成 reduction，再从 element 1 开始修复未写 tail，并以
LMUL1 约束单寄存器 reduction 结果。修复后 seed 5 的原动态首错 789 消失。

### 25.2 全掩码 FP reduction 的 seed

`vfredmin.vs v22,v22,v3,v0.t` 的十个源元素全部被屏蔽。原 MFPU 仍把中性 qNaN
送入 lane 内和跨 lane 归约树，与 `vs1[0]=0xfffeedec` 运算后得到 canonical qNaN
`0x7fc00000`。RVV 对空活动源集合的要求是原样返回 `vs1[0]`，不能改变 NaN payload。

当前每个 MFPU lane 在 unordered reduction 期间累计实际 `issue_be`，Ara 顶层对各
lane 的活动标志求 OR；lane 0 同时保存首次接收的 seed。仅当操作属于
`VFREDUSUM/VFREDMIN/VFREDMAX/VFWREDUSUM` 且全局没有活动源元素时，最终 VRF
写回数据切换为保存的 seed。ordered reduction 不使用该计数，因而不进入覆盖路径。
正确 ELF 的结束仿真时刻与修复前一致，并打印 `Core Test SUCCESS`；原全掩码首错消失。

activity 标志必须覆盖完整的跨 lane 归约生命周期，而不能在各 lane 局部完成时清零。
seed 3 的 `vfredmin.vs v10,v30,v13,v0.t` 中，lane 2/3 已分别看到有效 mask 字节，
但它们早于 lane 0 完成；旧实现使顶层 OR 在最终写回前退回 0，并把 result queue 中
正确的 `0xa5687810` 错误覆盖为 lane 0 的局部 seed `0xfffffffe`。当前每个 lane 在
下一条归约的首次 operand 握手时开启新的 activity epoch，并以当前 `issue_be` 直接
覆盖旧值；同一归约的后续握手只做 sticky OR。这样，较早完成的 lane 会把活动证据
保持到 lane 0 最终写回，同时下一条归约不会继承上一条的活动状态。

修复后的 seed 3 正常执行到软件成功出口：4611 条标量提交与 Spike 对齐，931 个
动态向量目的请求共比较 46,503 个确定 VRF 字节，`first_mismatch` 为空。seed 5 的
全活动集合为空场景仍返回原始 `0xfffeedec`，1020 个动态向量目的请求共比较 99,367
个确定字节且无首错。这两个方向的用例分别验证“不能错误覆盖正常结果”和“必须原样
返回空集合 seed”。

## 26. 非 bit-exact 结果的验证器污染传播

unordered FP sum 的归约树和 NaN payload 不要求与 Spike bit-exact。旧比较器会跳过
该条指令，却立即把其目的寄存器视为确定值。seed 5 中 Spike 的
`vfwredusum.vs` 产生 `0x7ff8000000000000`，Ara 产生另一个合法 qNaN；后续把同一
寄存器按 EW32/EW8 使用时，payload 差异分别在 `vfrsqrt7` 和 `vwaddu` 中形成假首错。

当前 unknown-state 模型只把 unordered FP reduction 实际写回的 element 0 标为
non-bit-exact，不污染 undisturbed tail；对普通向量算术则按元素索引、源 SEW 和目的
EEW，把 `vs2` 及向量 `vs1` 的未知源字节传播到对应目的元素。比较器还修正了
`funct6=0x13` 的解码，避免把 FP unary `vfrsqrt7` 误判为 mask-destination。

修正后，该 seed 的 1020 个动态向量目的请求没有确定字节 mismatch：共严格比较
99,367 个确定 VRF 字节，6 条 unordered FP reduction 及其依赖结果按规范标记为
non-bit-exact/unknown。最终 4 KiB signature 仍可因合法 NaN payload 不同而逐字节
不同，因此这类随机 FP 用例以逐指令 accepted-VRF 比较为判定依据，不以最终签名
完全相同作为必要条件。

同一版 RTL 和比较器还重放了 arithmetic seed 1、seed 2、seed 3 与 seed 9。seed 1 的 4590 条
标量退休前缀、985 个动态向量目的请求和 75,091 个确定 VRF 字节无 mismatch；
seed 2 的对应数字为 4621、988 和 22,951，seed 3 为 4611、931 和 46,503，
seed 9 为 4636、957 和 161,149。四例均正常执行到软件成功出口，严格
结果同样只因 non-bit-exact/unknown 字节记为 `UNOBSERVABLE`，`first_mismatch`
为空。

## 27. 全长 read-modify-write 的目的布局重排

arithmetic seed 7 的首个确定差异出现在 `vwmaccu.vx v30,s7,v7`。其前一条
`vmor.mm v31,v13,v10` 正确生成了 64 个架构 mask 位，并按 `v31` 当时的 EW16
物理布局写回；这对 mask 结果本身是合法的。随后 widening MAC 把 `v30:v31` 作为
EW32 累加器读取。原 dispatcher 发现该操作无 mask、`vstart=0` 且覆盖完整 VLMAX
后，按“完整目标会被覆盖”规则取消目的组重排。该规则没有区分纯覆盖和
`use_vd_op=1` 的读改写操作，导致 MAC 直接把 EW16 布局的 `v31` 当成 EW32 old-vd。
乘法器的源操作数、标量截断和乘加运算均正确，但错误的累加器输入使 element 0 的
低 32 位得到 `0xd3c64c77`，而 Spike 期望 `0xe0004c77`。

当前只有 `use_vd_op=0` 的全长纯覆盖操作可以跳过目的 preservation reshuffle。
accumulate 及其他读改写操作若发现目标组任一寄存器的 EEW 与目标 EEW 不同，必须先
逐寄存器规范化完整 old-vd 组。修复后的 trace 在同一架构序号下先为 `v30`、`v31`
各发一个 EW32 reshuffle uop，再发原始全长 MAC。seed 7 正常到达成功出口，4565 条
可比较退休指令全部与 Spike 对齐；1037 个动态向量目的请求比较 64,677 个确定 VRF
字节，`first_mismatch` 为空。seed 1、seed 3 和 seed 5 的 985、931 和 1020 个向量
目的请求回归同样无确定字节差异；seed 5 的标量差异仍仅来自已知合法的 unordered
FP NaN payload。

## 28. 严格 signature 的精确结束条件

严格检查点程序在读完最终 4 KiB vector signature 后以专用 `ecall` 通知 Spike
结束。RTL 原先只识别 `tohost` store；该 `ecall` 会进入通用 trap handler，返回后
再次执行 `test_done`，因此程序持续退休指令，commit-progress watchdog 也不会触发。
这会把已经完成的测试误判为超时，并在 trace 中重复追加 signature 读取过程。

当前重写器在最终 `ecall` 处生成 `__ara_vector_signature_exit_ecall`，runner 将该精确
地址作为 `COMMIT_EXIT_PC` 传给提交监视器。监视器仅在配置地址退休的指令确实为
`ecall` 且 `trap=1` 时报告成功，否则立即报错；普通测试仍沿用原有 `tohost` 路径。
对没有新符号的既有 ELF，replay 使用仓库内 LLVM objdump，在旧
`__ara_vector_signature_read_done` 附近定位 `ecall`，不依赖 ZCC。seed 7 使用该
机制在第一次软件成功出口结束，避免了此前约 9.7 万条重复退休记录。

## 29. Directed overflow 的浮点除法舍入

arithmetic seed 10 的第一个确定差异位于：

```asm
vfrdiv.vf v10, v28, ft0
```

该指令使用 `e64,m2,vl=15` 和 `RDN`。Spike 期望负无穷
`0xfff0000000000000`，原 RTL 在 `v10` 的一个元素上得到
`0xfff0000000000001`。对 PULP DivSqrt 内部舍入信号的选择性探针证明，除法器已先
形成正确的负无穷，但随后通用 directed-rounding 增量仍对无穷编码加一。该行为与
fpnew 自带文档中对 PULP DivSqrt IEEE 舍入限制的说明一致，不是 vector lane 的
shuffle、mask 或 scalar broadcast 错误。

默认 Ara 配置所需的 FP16/FP32/FP64 格式均被集成的 THMULTI 单元支持，因此 VMFPU
把 `DivSqrtSel` 从 `PULP` 改为 `THMULTI`。修复后 seed 10 越过原 PC，最终 4527 条
可比较退休指令全部与 Spike 对齐，未再出现该一 ULP 编码差异。

## 30. SLDU result-entry 逻辑进度

### 30.1 现象与直接根因

seed 10 后续首先在 `vmv8r.v v16,v8` 暴露 `v19` 两个字节缺失。向前追踪最后一个
生产者后，真实首错是：

```asm
vslideup.vi v11, v5, 15    # e16, mf2, vl=18
```

该指令应搬运 6 个架构字节。修复前 trace 只在第一个跨界聚合字写回 2 字节，SLDU
随后把指令标记完成，剩余 4 字节被丢弃。首拍的 `out_pnt=30`、
`remaining_byte_count=2`、`current_output_end=32`；原 result queue 把 32 记为该
entry 的逻辑进度，使 `commit_cnt=6` 一次归零。

result entry 并不总与一个输入拍一一对应：输入边界和输出边界不同时，一个 entry
可能由多个周期逐步填满。因此正确计数不是简单选择“本拍字节数”或“输出结束位置”，
而要按生产者语义解释该 entry 覆盖的完整逻辑区间：

- reduction 的每个 entry 表示一个固定 `NrLanes*8` 聚合步骤，即使 lane offset
  使 byte-enable 稀疏；
- 普通 slide entry 记录该 entry 累积覆盖到的 `current_output_end`；
- 普通 `vslideup` 的第一个目标字还含有 `[0,stride)` 未修改前缀，必须从逻辑进度
  中扣除；
- `vslide1up` 的首前缀由 scalar operand 实际写入，不能扣除；
- mask 关闭的元素虽然没有 byte-enable，仍属于已经处理的架构进度。

此外，排队的 `vslide1up` 成为 commit head 时，旧逻辑无条件减去 `stride`；而它
直接成为 head 时已有 `!use_scalar_op` 条件。两条初始化路径现已统一，避免最后残留
一个 scalar element、result queue 已空但 `commit_cnt` 永不归零。

### 30.2 修复证据

修复后的原动态 `vslideup` 在两个 result entry 中完成：第一个 entry 写回跨界的
2 字节，第二个 entry 写回剩余 4 字节；非侵入式比较器在原指令处比较 6 个确定字节
并报告 `PASS`。后续 `vmv8r.v` 比较 1024 个确定字节也为 `PASS`。

完整 seed 10 在 47.25 秒内正常到达软件成功出口：4527 条退休指令与 Spike 精确
对齐；913 条有目的向量请求中，788 条至少包含一个确定可比较字节，共比较 72,245
字节且 `first_mismatch` 为空。seed 7 和 seed 1 回归分别匹配 4565、4590 条退休
指令，并比较 63,888、74,831 个确定向量字节，无 mismatch；两例的后端 uop
`alloc/done` 分别为 `2011/2011` 和 `2160/2160`。

## 31. 部分写回缺失的验证器检测

原非侵入式比较器会精确检查 Ara 已接受的每个 VRF 写回字节，也能在整条指令完全
没有写回时检查目的状态是否变化；但当一条指令只写了部分目标字节时，它只遍历
`actual` 集合。上述 `vslideup` 的两个已写字节与 Spike 相同，因此比较器曾把该
指令误报为 `PASS`，直到后续整组搬运读取缺失字节才间接暴露。

当前比较器在建立 Spike 指令前后状态后，还遍历每个目的寄存器字节。若该字节在
架构 mask、`vl/vstart`、tail/mask policy 和 unknown-state 门控后仍为确定可观察，
Spike 前后值发生变化，但 Ara 的 accepted-VRF 轨迹中不存在对应 byte-enable，则
立即报告 `missing_changed_vrf_write`，并给出寄存器、字节、前值、期望值和比较
mask。该规则不要求值未变化的元素必须产生物理写回，也不会把 agnostic 或未知字节
误判为缺失。

新增单元测试构造一个 8 字节目的结果，其中 Ara 只写低 4 字节而高 4 字节在 Spike
中明确变化；比较器现在在首个缺失高字节直接报错。验证环境共 81 个 Python 单元
测试通过。随机结果中的顶层 `UNOBSERVABLE` 表示至少有指令只涉及架构不确定或无
活动字节，不表示数值 mismatch；判读时必须同时检查 `first_mismatch`、确定比较
字节数和逐指令状态，不能把合法 agnostic 状态伪装成 bit-exact 通过。

## 32. 零 VL MASKU 指令泄漏预处理队列配额

integer-stress seed 4 原先在 PC `0x80004732` 的
`vmv8r.v v24,v16` 之后永久停顿。探针显示停顿时所有 `vid` running bitmap 均为空，
所有 PE 也均为 ready，但主 sequencer 的 ALU instruction-queue 计数为 5，而队列深度
仅为 4，因此后续请求始终被 `vinsn_queue_issue` 拒绝。这不是 `vmv8r` 的数据搬运或
内部 reshuffle 死锁，而是更早的队列信用泄漏最终在该指令处耗尽容量。

逐事件记录 ALU 的 reserve、PE issue 和 completion 后，泄漏对应下面的零长度序列：

```asm
vsetivli t4, 0, e32, m8, tu, mu
vcpop.m  a1, v30, v0.t
...
vcpop.m  t1, v0, v0.t
```

主 sequencer 根据 `target_vfus()` 为 MASKU 指令可能需要的 lane ALU/VMFPU 预处理路径
预留队列配额。lane sequencer 在 `vl=0` 时则采用快速完成路径：不向 VALU/VMFPU
建立 uop，直接置位通用 `vinsn_done`。原实现没有在该路径返回对应的
`alu_vinsn_done` 或 `mfpu_vinsn_done`，因此每条零 VL `vcpop.m` 都永久占用一个 ALU
配额。连续随机程序最终可把计数推到 `depth+1`，且因为没有真实 uop，之后也不可能
再收到 completion。

修复位于 `lane_sequencer.sv` 的零 VL 快速完成分支。该分支现在按照原请求的执行单元
和预处理目标同步产生队列完成事件：普通 ALU/MFPU 请求分别归还对应信用；MASKU
整数/掩码预处理归还 ALU 信用，浮点比较归还 MFPU 信用；完全不经过 lane ALU 的
`VID` 不产生伪完成。非零 VL 的 issue、operand、result 和 completion 路径不变。

修复后的 seed 4 完整运行到 `Core Test SUCCESS`。提交轨迹包含 4992 次向量请求和
4992 次响应，后端 8317 个 uop 的 alloc/done 完全配对；原 `vmv8r` 停顿不再出现，
结束时各功能单元队列计数均回到零。严格比较在后续新首错之前通过 4183 个动态向量
检查点。新的首错位于 arch_seq 4565、PC `0x80004b50` 的 `vmv.v.v`，属于本修复之后
暴露的独立数据问题，本节不把它计作零 VL 配额修复的回归失败。

## 33. `vmv.v.v` 唯一源被错误判为重复操作数

### 33.1 现象与探针证据

修复零 VL 配额泄漏后，integer-stress seed 4 的严格首错位于 arch_seq 4565、PC
`0x80004b50`：

```asm
vsetivli ra, 17, e16, mf2, tu, mu
...
vmv.v.v v20, v0
```

此前的 `vmv8r.v v0,v8` 使 `v0` 保持 EW64 物理布局，而当前 `vmv.v.v` 需要按 EW16
读取 17 个元素。Spike 中 `v0` 的架构值以及此前所有严格检查点均正确，但 Ara 把
源字节按错误布局读出。例如 Spike 期望位于架构字节 24--28 的非零数据，在实际
`v20` 中被分散到字节 6--7、14 和 22--23。这种规律证明问题是源寄存器缺少必要的
deshuffle，而不是 ALU 数值计算或目的 byte-enable 错误。

定向 dispatcher 探针进一步证明：初始解码时 `v0` 的 EEW notebook 为 EW64，目标
EEW 为 EW16，`use_vs1=1`、`active_group_needs_reshuffle(v0)=1`，因此源重排候选位
最初被正确置位；但进入 RESHUFFLE 时只剩目的位 `3'b001`，硬件仅重排了旧目的
`v20`，随后直接发射原始 `vmv.v.v`。

### 33.2 根因与修复

dispatcher 会清除指向同一架构操作数的重复重排请求。原去重条件直接比较指令编码
中的 `rs1` 和 `rs2` 字段：两者相等时清除 vs1 重排位。该判断遗漏了操作数有效性。
`vmv.v.v` 实际只使用 vs1，`use_vs2=0`；但该编码中未使用的 `rs2` 字段也为 0，恰好
与合法源 `vs1=v0` 相等。于是唯一真实源被误认为是 vs2 的重复项并被清除。

修复位于 `ara_dispatcher.sv` 的 reshuffle 去重掩码。只有 `use_vs2=1` 时，
`rs1==rs2` 才表示两个实际源操作数别名；当 vs2 未使用时，vs1 重排请求不再受未使用
编码字段影响。目的寄存器别名、source-snapshot replay、窄化/规约重叠等原有例外条件
保持不变。

### 33.3 验证结果

修复后 seed 4 再次完整运行到 `Core Test SUCCESS`。轨迹包含 4992 次架构向量请求和
响应，8318 个后端 uop 的 alloc/done 完全配对，最大同时在飞 uop 数为 6；新增的一
个 uop 正是此前缺失的 `v0` 源布局转换。严格标量提交前缀匹配 7417 条指令且无差异；
全部 4525 条有向量目的的动态请求均通过非侵入式 VRF 写回比较，共比较 420724 个
确定字节，`first_mismatch`、未完成请求和未退休请求均为空。

## 34. `vrgatherei16` 重叠只读源的快照回放链路不完整

### 34.1 现象与根因

integer-stress seed 3 的首个严格差异位于 arch_seq 1072、PC `0x800013ee`：

```asm
vrgatherei16.vv v16, v0, v4
```

该指令在 SEW=64、LMUL=8、VL=128 下读取数据组 `v0-v7`，同时从 `v4` 开始读取
16-bit index 组。两个源都是只读操作数，但物理寄存器范围部分重叠且采用不同元素
布局。dispatcher 已正确识别这种布局重叠，先保存完整数据源快照，再重排 index
源，并给原始请求设置 `source_snapshot_replay_vs2`。问题发生在后续的动态 gather
读取路径：`vrgatherei16` 的数据元素不是由固定的 lane operand stream 顺序取得，
而是由 MASKU 根据 index 逐项产生 MaskB 请求。lane sequencer 保存了该动态流的
hazard 信息，却没有同时保存并转发 `source_snapshot_replay_vs2`，因此 MaskB 又从
已经被 index 重排覆盖的 VRF 区域读取数据。

即使补上传递位，原 operand requester 也把所有快照回放固定从 word 0 开始。顺序
源可以这样读取，但 gather 的每次请求携带任意 `vstart=idx`，必须从该元素所在的
lane-local VRF word 开始，否则非零 index 仍会读错快照位置。

### 34.2 修复

`lane_sequencer.sv` 现在与动态 gather 请求一起保存
`source_snapshot_replay_vs2`，并在生成每个 MaskB 请求时原样传播。该状态与已有的
source hazard、wait-complete 状态采用相同的请求生命周期，在新 gather 被接受时
建立，在动态请求流结束后清除。

`operand_requester.sv` 则根据请求的 `vstart` 和源 EEW 初始化
`source_snapshot_index`。顺序回放仍从 0 开始；只有显式 snapshot replay 使用
`vstart >> (EW64-eew)` 选择包含目标元素的 lane-local word。该修改不改变普通 VRF
请求地址、bank 仲裁或非 gather 的顺序回放。

### 34.3 验证结果

修复后，原差异位置写回了 Spike 期望的 `0xf7` 字节。运行继续到后续独立的 masked
`vslide1up` 停顿前，2151 条有目的向量请求、332115 个确定字节全部严格一致，原
arch_seq 1072 不再产生 mismatch。完成下一节的 slide 修复后，同一 seed 的全部
4517 条有目的向量请求均通过，说明动态 gather 快照修复没有在后续随机指令中引入
新的可观察差异。

## 35. masked `vslide1up` 提前释放 MASKU 上下文

### 35.1 现象与逐级探针证据

seed 3 随后停在 arch_seq 2344：

```asm
vsetvl       zero, zero, t6    # SEW=8, LMUL=mf8, VL=1
vslide1up.vx v13, v2, a4, v0.t
vmsif.m      v15, v12
```

SLDU 停留在 `SLIDE_RUN_VSLIDE1UP_FIRST_WORD`，其 source operand、result queue 和
VRF result grant 均不构成阻塞，唯一缺失的是 predicate。逐级探针得到以下事实：

- 四个 lane 都生成并接受 `MaskM(v0)` 请求，`vl_words=1`、`vstart=0`；
- operand requester 的 hazard 和 wait-complete 均为零，首周期得到 VRF bank grant；
- MaskM 数据随后同时到达四个 lane 的 MASKU 输入；
- 数据到达时 MASKU 的唯一指令槽已经被下一条 `vmsif.m` 覆盖，因而没有形成目标为
  SLDU 的 mask queue entry。

MASKU 原来对所有 `VSLIDEUP` 都以 `vl-stride` 初始化 `commit_cnt`。这对普通
`vslideup` 合理，因为 offset 以下的目的元素保持不变；但 `vslide1up` 会把标量写入
元素 0，再把源元素上移。该例中 `vl=1`、`stride=1`，仍有一个需要 predicate 的
标量目标元素，原计算却得到 `commit_cnt=0`。MASKU 因此在 MaskM 数据经过 operand
queue 和输入 spill register 的若干周期延迟期间提前释放提交上下文，允许后续 MASKU
指令覆盖它，SLDU 则永久等待不会再产生的 predicate。

### 35.2 修复与适用范围

`masku.sv` 现在仅对 `!use_scalar_op` 的普通 `vslideup` 从提交范围中减去 stride；
`use_scalar_op` 表示的 `vslide1up` 保留完整 `vl`。这样 MASKU 会持有该指令上下文，
直到对应 mask word 被 SLDU 接收后再允许下一条 MASKU 指令进入。源元素计数、普通
slideup 的低位跳过、未掩码快速路径、SLDU 数据移动和 VRF 写回逻辑均未改变。

### 35.3 验证结果

修复后的完整 integer-stress seed 3 在 234.01 秒内输出 `Core Test SUCCESS`，原
arch_seq 2344/2345 均正常完成。非侵入式比较覆盖全部 4517 条有目的向量请求，比较
606452 个确定字节，`first_mismatch`、未完成请求和未退休请求均为空；标量退休前缀
匹配 7442 条指令且没有状态或访存差异。专门覆盖 mask、tail、offset 和越界组合的
`rvv:vslide_mask_edges` 也在同一 RTL 上通过（41.25 秒）。

## 36. `vrgatherei16` 同寄存器数据/索引视图的回放范围与布局元数据

### 36.1 现象与两层根因

integer-stress seed 5 的首个严格差异位于 arch_seq 1626、PC
`0x80001c60`：

```asm
vrgatherei16.vv v11, v9, v9, v0.t   # e32, m1, vl=7
```

同一个 `v9` 在该指令中同时表示 SEW=32 的 gather 数据源和 EEW=16、
EMUL=mf2 的索引源。dispatcher 必须先保留数据视图，再把物理寄存器重排成索引
视图。原快照只保存当前 `vl=7` 个数据元素，但每个合法 gather index 可以选择
`[0,VLMAX)` 中的任意数据元素；该例首个 index 为 13，因此回放访问了未捕获的
快照内容。数据源快照范围现改为数据视图的完整 VLMAX，普通顺序源和非 gather
快照仍按当前 VL 保存。

扩大快照范围后，源快照探针确认目标 lane-local word 已正确回放为
`0x0154fec50154fec5`，但 MASKU 仍将其重组为 `0x01540154`。进一步沿元数据追踪发现，
快照保存的是重排前的 EW32 物理字节布局；随后 `v9` 被重排为 EW16 index 布局，
原始指令重新译码时又从 EEW notebook 读取了当前 EW16，并写入 `eew_vd_op`。
`vrgather`/`vrgatherei16` 的动态数据读取经 MaskB 进入 MASKU，而该入口约定使用
`eew_vd_op` 对数据字节 deshuffle。于是数据本身来自正确的 EW32 快照，伴随它的
布局说明却错误地变成 EW16，最终在 MASKU 内发生二次错误重排。

### 36.2 修复边界

`ara_dispatcher.sv` 在建立 vs2 source-snapshot replay 时，若当前操作属于
`VRGATHER`、`VRGATHEREI16` 或 `VCOMPRESS`，同时把 `eew_vd_op` 恢复为
`source_snapshot_eew_q`。这三个操作通过 ad-hoc MaskB 请求读取数据源；只有明确
启用快照回放时才覆盖该字段。普通 old-vd operand、非快照 gather/compress、索引
流的 `eew_vs2`、MaskB 地址 EEW、VRF 普通读取和 MASKU 的通用 deshuffle 规则均不变。

该修改与前一节动态回放链路修复分工明确：lane sequencer 负责把 replay identity
传播到每个动态 MaskB 请求，operand requester 用 index 选择正确快照 word，
dispatcher 则保证返回字节附带其真实物理布局。三者缺少任意一项都不能正确支持
同一寄存器的异构数据/索引视图。

### 36.3 验证结果

修复后的目标 arch_seq 1626 比较 24 个确定目的字节，`mismatch_count=0`。完整
seed 5 在 271.30 秒内通过：4993 次架构向量请求和响应全部配对，8589 个后端 uop
全部完成；4515 条有目的向量请求共比较 510576 个确定字节，`first_mismatch`、
未完成请求和未退休请求均为空，7420 条标量提交与 Spike 对齐。

共享路径定向回归 `rvv:vrgather_edges` 和 `rvv:vcompress_edges` 分别通过。此前覆盖
重叠 gather 与 masked slide 修复的 integer-stress seed 3 也再次完整通过：4517 条
有目的向量请求、606452 个确定字节均无差异，7442 条标量提交与 Spike 对齐。

## 37. masked narrowing 的 old-vd 快照同时也是窄 `vs1`

### 37.1 现象与根因

integer-stress seed 2 的首个向量差异位于 arch_seq 1818、PC
`0x80001f92`：

```asm
vnclip.wv v4, v4, v4, v0.t    # e8, m2, vl=21
```

该合法重叠同时赋予 `v4` 三种角色：窄布局的目的组、窄布局的 shift-amount 源
`vs1`，以及从同一基址开始的双宽数据源 `vs2`。由于指令带掩码且采用 undisturbed
策略，dispatcher 已在把物理寄存器组转换为宽 `vs2` 布局前保存窄 old-vd；该快照
随后也用于保留未激活目的元素。原逻辑却只把它视为目的保留数据，不允许
`source_snapshot_replay_vs1` 使用 preserve 类型快照。因此 `vs1` 仍从已经转换为宽
布局的物理 VRF 读取，shift amount 与 Spike 不同，首个确定差异为 `v4` 的 byte 2：
期望 `0xff`，实际 `0x80`，该请求共出现 7 个错误字节。

这个问题不能通过让 `vs2` 也读取同一快照解决：快照保存的是窄 old-vd/`vs1`
视图，不包含双宽 `vs2` 的完整数据组。修复必须区分两个源的真实布局角色。

### 37.2 修复

`ara_dispatcher.sv` 现在允许 preserve 快照在寄存器基址、EEW 和 LMUL 均与 `vs1`
匹配时回放 `vs1`，同时仍禁止把该窄快照误用作宽 `vs2`：

```systemverilog
if (ara_req.use_vs1 && ara_req.vs1 == source_snapshot_vs_q &&
    ara_req.eew_vs1 == source_snapshot_eew_q &&
    lmul_vs1 == source_snapshot_lmul_q) begin
  ara_req.source_snapshot_replay_vs1 = 1'b1;
  reshuffle_req_d[2] = 1'b0;
end
```

lane 侧原有 `masked_narrow_overlap_preserve` 仍负责把同一快照用于 masked/tail
目的合并。由于每个窄源字在对应结果写回前读取，顺序回放不会被当前指令的写回
覆盖。普通 narrowing、非重叠源、未掩码结果和宽 `vs2` 路径不改变。

### 37.3 验证结果

修复后 arch_seq 1818 不再产生差异，随机程序继续推进到后续独立的 slide 问题。
定向 `rvv:vnclip_edges` 通过；完成第 38、39 节修复后，同一 seed 2 的全部 4574 条
有目的向量请求、514517 个确定字节均与 Spike 一致。

## 38. `vslide1down` 的零长度向量源污染后继 SLDU 请求

### 38.1 逐周期证据

seed 2 的下一处差异位于 arch_seq 3130、PC `0x800034a4`：

```asm
vslide1down.vx v15, v26, a6, v0.t   # 前一条，VL=1
vslidedown.vi  v31, v6, 13          # 出错请求，e32, mf2, VL=1
```

前一条 `vslide1down` 在 `VL=1` 时只把 scalar operand 写入最后也是唯一的活动元素，
不消费任何 `vs2` 元素。lane sequencer 原来仍为它产生 `SlideAddrGenA` 的 `vs2`
请求，而 SLDU 又按 scalar-only 路径完成。该 operand 随后到达 lane-to-SLDU 的
spill/聚合路径，却没有与后继请求匹配所需的独立 instruction tag，因而被下一条
非整字跨度的 `vslidedown` 当作自己的首个 source aggregate。

探针先确认目标 `v6` 的 VRF 物理字为正确值，再确认目标 SLDU 首次消费的是前一条
请求留下的数据；正确的 `v6` aggregate 在下一周期才到达。最终 `v31` 的 4 个活动
字节全部写成零，而 Spike 期望 `0xffffffff`。这排除了 VRF 内容、shuffle 地址和
目标结果写回本身的问题。

### 38.2 修复

`lane_sequencer.sv` 显式识别 scalar-only、无向量源区间的 `vslide1down`。该情形既
不发出 `vs2` operand request，也通知 SLDU 跳过 source operand：

```systemverilog
slide_down_source_empty = pe_req.op == VSLIDEDOWN &&
                          pe_req.use_scalar_op && pe_req.vl <= 1;

vfu_operation_d.skip_sldu_operand = slide_down_source_oor ||
                                     slide_down_source_empty ||
                                     slide_up_source_empty;

operand_request_push[SlideAddrGenA] = pe_req.use_vs2 &&
                                      !slide_down_source_oor &&
                                      !slide_down_source_empty &&
                                      !slide_up_source_empty;
```

该判定只覆盖 `use_scalar_op && VL<=1`，不会抑制普通 `vslidedown`、`VL>1` 的
`vslide1down` 或实际需要读取 `vs2` 的 source 区间。

### 38.3 验证结果

修复后 arch_seq 3130 的 4 个确定目的字节全部匹配，运行到第 39 节所述的独立
`vfirst` 握手停顿前未再出现向量差异。定向 `rvv:vslide1down`、
`rvv:vslidedown` 和 `rvv:vslide_mask_edges` 均通过。

## 39. MASKU scalar-return 请求的原子接收记账不一致

### 39.1 现象与根因

seed 2 最后停在以下相邻请求：

```asm
vslideup.vi v26, v8, 18, v0.t   # PC 0x80004e74
vfirst.m    s2, v24             # PC 0x80004e78
```

前一条 masked slide 已完成 SLDU 计算，但其 predicate words 仍在 MASKU mask queue
中排空。顶层 `ara.sv` 的原子广播门控工作正确：MASKU 未 ready 时，新的 MASKU
请求不会只被 lane 提前接收。问题位于 sequencer 的 `WAIT` 状态。`vfirst` 已获得
vid0 并被记为 MASKU 在飞；下一周期四个 lane 的原始 `pe_req_ready` 均为 1，旧代码
便撤销 `pe_req_valid`，却没有同时检查 MASKU readiness。由于顶层原子门控在这一
周期阻止了实际广播，lane 和 MASKU 都没有接收 `vfirst`。旧 mask context 排空后
所有 PE 虽恢复 ready，请求已经消失，sequencer 只能永久等待不会产生的 scalar
result。

逐周期探针确认旧 slide 的 MASKU `read/commit` 计数和 mask queue 最终都归零，
MASKU 随后持续 `ready=1`；停滞状态下 sequencer 为 `WAIT`、vid0 仅登记在 MASKU
在飞位、`pe_req_valid=0`，且所有 PE ready 位均为 1。这证明问题是请求撤销与原子
接收条件不一致，而不是 MASKU 内部执行或结果返回死锁。

### 39.2 修复

sequencer 现在仅在 lane operand suppliers 和当前请求所需的 MASKU 都 ready 时撤销
scalar-return 请求：

```systemverilog
if (!ara_req_i.use_vd && !is_store(ara_req_i.op) &&
    &operand_requester_ready && mask_requester_ready)
  pe_req_valid_d = 1'b0;
```

对 unmasked、非 MASKU 的 scalar move，`mask_requester_ready` 按定义恒为 1，行为
不变；对 `vfirst/vcpop` 或其他真正占用 MASKU 的 scalar-return 请求，该条件与
顶层广播门控一致，保证“撤销请求”只发生在 lane 和 MASKU 可以同周期实际接收时。

### 39.3 完整验证结果

修复后的 integer-stress seed 2 在 275.47 秒内通过，4983 次架构向量请求和响应
全部配对，8221 个后端 uop 全部完成，最大同时在飞数为 6。非侵入式写回比较覆盖
4574 条有目的向量请求、514517 个确定字节，`first_mismatch`、未完成请求和未退休
请求均为空；7423 条 RTL/Spike 标量提交前缀无差异。

共享路径定向回归 `rvv:vfirst`、`rvv:vcpop`、`rvv:vslide_mask_edges`、
`rvv:vslidedown`、`rvv:vslide1down`、`rvv:vnclip_edges` 和
`rvv:vreduction_overlap_edges` 全部通过。长随机防回归 seed 3 与 seed 5 也再次完整
通过：seed 3 比较 4517 条向量目的请求、606452 个确定字节；seed 5 比较 4515 条
向量目的请求、510576 个确定字节，两者均无向量差异且后端 alloc/done 完全配对。

## 40. VCOMPRESS 不规则目的流破坏传递 WAW 顺序

### 40.1 现象与根因

integer-stress seed 6 的首个确定差异位于 arch_seq 1028、PC `0x80001274`：

```asm
vremu.vx     v24, v0, a7
vmv2r.v      v8, v16
vcompress.vm v24, v0, v8
vor.vx       v24, v8, s6
vmul.vx      v16, v24, t3
```

逐周期写回记录表明，最后一条 `vmul` 读取的 `v24` 被第一条长延迟 `vremu`
迟到的结果覆盖。问题不是 `vmul` 的乘法数据通路，而是三个连续写者之间的传递
WAW 顺序丢失。sequencer 的普通 WAW chaining 以目的结果脉冲作为前后指令按字推进
的依据；这种方法要求前后目的流具有可对应的规则进度。`vcompress` 的目的元素数和
目的字位置由运行时 mask 决定，目的流不能与旧写者或新写者建立逐字对应关系。旧
实现仍让 `vcompress` 对旧 `vremu` 采用普通 chaining，并在 write list 中用
`vcompress` 覆盖最新写者；更年轻的 `vor` 随后只对 `vcompress` 建立 WAW。于是
`vcompress` 的局部结果可使 `vor` 提前推进，而尚未完成的 `vremu` 已不再由最新
write-list 项表示，最终出现旧结果在 `vor` 之后写回的次序反转。

### 40.2 修复

sequencer 将 `VCOMPRESS` 的目的访问定义为 completion-paced：新到达的
`VCOMPRESS` 若与旧写者构成 WAW，必须等待旧写者完整退休；写入 write list 的
`VCOMPRESS` 表项也设置 `wait_complete`，使后续写者等待该压缩操作完整退休。
RAW、无关寄存器请求和普通规则目的流仍保留原有 chaining。

这一处理保留了传递顺序：旧写者完成后才能开始不规则压缩写，压缩写完成后年轻
写者才能覆盖同一组寄存器。它没有尝试用数据相关的压缩输出脉冲推断源或目的元素
进度。

### 40.3 验证

修复后，seed 6 的首错从 arch_seq 1028 前移至第 41 节所述的 arch_seq 1447，原
`vmul.vx` 的全部确定目的字节匹配。独立 `rvv:vcompress_edges` 回归也通过。

## 41. VRGATHEREI16 重叠双源的不同 EEW 布局冲突

### 41.1 现象与根因

下一处差异位于 arch_seq 1447、PC `0x8000192c`：

```asm
vrgatherei16.vv v26, v28, v29   # e64, m2, VL=9
```

该指令的数据源为 `v28-v29` 的 e64,m2 视图，索引源为重叠 `v29` 的 e16,mf2
视图，目的 `v26-v27` 与两个源均不重叠。Ara 的 VRF 为支持不同 EEW 使用内部
shuffle 布局，因此同一组架构字节在这里必须同时保留 e64 数据视图和 e16 索引
视图。原 dispatcher 在一次 decode 中锁存全部 `reshuffle_req` 位，并依次对两个
源做原地换布局。它先把数据源转换为 e64，随后又把重叠索引源转换为 e16，最后才
请求 source snapshot。此时 e64 视图已经被第二次原地转换破坏，snapshot 保存的
不是完整数据源。MASKU 提取出的索引本身正确，但索引 13 对应的数据元素已经错误。

### 41.2 修复

当两个源寄存器组重叠、目标 EEW 不同、两个源当前都需要 reshuffle，且目的组与
两源均不重叠时，dispatcher 不再在同一批次转换两个源：

1. 第一批只规范化 `vs2` 数据视图；
2. 经 `WAIT_IDLE` 返回后重新 decode，使布局状态重新参与判断；
3. 保存已经完整的 `vs2` 数据视图；
4. 再把重叠 `vs1` 转换为索引 EEW，并从 snapshot 重放数据源。

目的与源同时重叠的情况没有套用这条简化路径，仍交由既有的保守 overlap 修复逻辑
处理。对不重叠源、两个源 EEW 相同或只有一个源需要转换的普通指令，decode 行为不
变。

### 41.3 定向激励与验证

`rvv:vrgather_edges` 新增了精确敏感场景：先用 `vl2re8.v` 建立 `v28-v29` 的
e8 原始布局，再以 e64,m2、VL=9 执行 `vrgatherei16.vv v26,v28,v29`；`v29`
中的索引序列包含 `0、1、13`，测试按原始架构字节计算并逐元素核对 e64 结果。实际
ELF 反汇编确认 whole-register load、`vsetvli`、gather 和结果 store 保持相邻。
该测试在修复后的 RTL 上通过。

随机严格比较在该修复后越过原首错，比较 1628 条有目的向量指令和 173252 个确定
字节均无差异，随后停在第 42 节所述的独立零 VL 状态机问题。

## 42. 零 VL widening overlap 进入无消费者等待状态

### 42.1 现象与根因

seed 6 越过前两个数据错误后，最后匹配到 PC `0x80001eac`：

```asm
vwmaccu.vx v8, s7, v12, v0.t   # VL=0
vsrl.vi    v8, v28, 3           # 同样为 VL=0，无法被接受
```

状态探针显示 dispatcher 永久停在 `OVERLAP_WAIT_ORIGINAL`；此时 Ara、SLDU 均
idle，输入和各流水位置也没有对应后端 uop。原因是前一条 widening accumulator
满足合法高位源/目的重叠条件，原 dispatcher 因而先进入 overlap snapshot/repair
流程；但其活动区间为空，公共零 VL 路径按架构语义正确地不发出 original uop。
overlap 状态机却继续等待该 original uop 完成，形成一个永远不存在的消费者。

### 42.2 修复

进入 widening、narrowing 或 reduction overlap 准备流程现在额外要求
`vstart < vl`。活动区间为空时不建立 snapshot、fixup 或 original-uop 状态，指令
直接走既有零 VL 快速响应路径。该条件只排除没有活动元素的请求，不改变任何
`vstart < vl` 的合法重叠修复。

### 42.3 定向激励与阶段验证

`rvv:vwiden_overlap_edges` 新增零 VL 高位重叠测试：先建立 e32,m8 的 `v8-v15`
目的组和 e16,m4 的 `v12-v15` 源视图，用 `vs8r.v` 保存原始 1 KiB 寄存器组，令
VL=0 后执行 `vwmaccu.vx v8,...,v12`，随后立即再次 whole-register store。测试
既检查后继请求能前进，也逐字节确认零 VL 指令没有修改重叠组；该测试通过。

使用同一修复 RTL 的 seed 6 严格比较已经越过旧 64000 周期停点，并在完成第 44 节
的双 EEW 重叠修复后完整通过。最终结果统一记录于第 44.4 节；本节的零 VL 首错未
再次出现。

## 43. 跨 profile 激励覆盖审计

### 43.1 审计范围

对 arithmetic、load/store、FP32、FP64、integer-stress、load/store-slide、
vtype-churn 和 mixed-control 八类正式 profile 的各 10 个生成程序合并统计。该统计
来自生成后的实际汇编，而不是 testlist 中的预期配置；共覆盖 80 个源码、196713 条
向量指令，其中 60022 条为 masked 指令，并包含 3085 次可解析的向量配置切换。

| 维度 | 实际覆盖 |
|---|---|
| 指令族 | configuration 4278、fixed-point 14991、floating-point 10033、integer arithmetic 30746、load/store 3143、mask logical 13038、mask other 59966、narrowing 8419、permutation 22258、reduction 16349、widening 13492 |
| SEW | e8 780、e16 757、e32 719、e64 829 次显式配置 |
| LMUL | mf8 136、mf4 307、mf2 682、m1 520、m2 513、m4 519、m8 408 次显式配置 |
| tail policy | ta 1482、tu 1603 |
| mask policy | ma 1620、mu 1465 |
| 访存模式 | unit-stride 2683、strided 214、indexed 91、segment 75、mask 37、whole-register 33、fault-first 10 |

由此可以确认生成器没有把验证退化为单一 SEW、LMUL、policy 或普通算术流；整数、
浮点、定点、缩窄、加宽、规约、排列、mask 和配置类均有实际动态激励。全部七类
访存模式也出现在生成汇编中。

### 43.2 覆盖边界

这些数字只证明激励被生成，不证明对应 RTL 已通过。特别是 indexed、segment、
fault-first 和 whole-register 的随机出现次数远低于 unit-stride，不能用 196713 条
总量掩盖这些模式的稀疏性。因此验证闭环同时保留 `vsegment_emul_edges`、
`vindexed_vstart_edges`、
`vstore_signature`、`vmask_mem_emul_edges`、`vrgather_edges`、
`vwiden_overlap_edges` 等定向用例，用边界值、重叠寄存器组、不同 EEW、零 VL、
非零 vstart 和逐字节内存签名补足随机分布的弱项。

验证目录还增加了套件完整性检查：Makefrag 中的每个 RVV 条目必须存在对应 `.c`
源码，否则 catalog 加载立即失败。该检查避免 suites.json 能解析、但测试源仅存在于
某台机器或被 `.gitignore` 隐藏的假覆盖状态。当前 `rvv-corners` 的 25 个显式条目
均可解析到实际源码，验证环境 84 项 Python 单元测试全部通过。

## 44. `.wv` 双重合法重叠导致双 EEW 布局循环

### 44.1 现象与精确复现

第 42 节修复后的 seed 6 不再停在零 VL 指令，但在 arch_seq 2773、PC
`0x80002ec4` 长时间无法退休：

```asm
vsetvli    zero, s6, e32, m4, tu, mu   # VL=103
vrgatherei16.vv v12, v20, v18, v0.t
vwaddu.wv  v0, v0, v4
```

`vwaddu.wv` 的目的 `v0-v7` 同时是 e64,m8 宽源，e32,m4 窄源 `v4-v7` 又合法
重叠该宽组的高半部。原运行持续生成并完成内部 reshuffle uop，却始终不接受原架构
指令；一小时墙钟超时前，标量提交前缀 3036 条、向量写回 2495 条和 255448 个确定
字节均与 Spike 一致，末尾仍有该指令的两个内部 uop 在飞。

`rvv:vwiden_overlap_edges` 增加了独立精确激励。测试先建立 `v0-v7` 的已知原始字节，
再以 e32,m4、VL=103 写入 `v4-v7`，执行反汇编编码同为 `0xd2022057` 的
`vwaddu.wv v0,v0,v4`，最后逐个核对 103 个活动 e64 结果和 tail-undisturbed
元素。修复前的 clean RTL 在该测试上 180 秒仍不能退出，证明它不依赖 seed 6 的
其他随机前序状态。互补子测试先建立 e64,m8 宽布局，使宽源当前可读而窄源需要
转换，用同一条指令覆盖另一种 snapshot/repair 次序。

### 44.2 逐周期根因

状态探针显示，进入目标指令时 `v0-v7` 的有效布局均为 e32。窄源 `v4-v7` 因而
已经可读，而宽源 `v0-v7` 需要转换为 e64。dispatcher 在形成
`dual_source_layout_conflict` 时正确得到“保存窄源、转换宽源”的关系，但后续目的
与源去重会把 `vs2==vd` 的 reshuffle 位并入目的位，合法 widening-overlap 处理又会
修改目的位。旧代码直到这些修改之后才再次读取 `reshuffle_req_d` 选择 snapshot
源，因此误选了尚不可按 e64 读取的宽源。source snapshot 的安全约束是保存当前
已经有效的源视图，而不是代替一次尚未执行的布局转换；违反该约束会产生错误宽源。

同一逻辑还存在另一种初始状态：若宽源视图已经正确而窄源需要转换，保存宽源本身
是正确的。但宽源恰好等于目的组时，旧判定把该 snapshot 视为一般的
`source_snapshot_resolves_widen`，于是先把活动目的 `v0-v6` 转成 e64；下一次 decode
又为窄源把 `v4-v7` 转回 e32。之后目的转换和窄源转换交替发生，形成 seed 6 trace
中持续重复的 e64/e32 reshuffle 循环。

### 44.3 修复

冲突首次形成时，dispatcher 现在立即锁定哪个源视图当前可读，后续目的去重和合法
重叠处理不再改变 snapshot 选择：

```systemverilog
dual_source_snapshot_vs1 = dual_source_layout_conflict &&
    !reshuffle_req_d[2] && reshuffle_req_d[1];
```

对 snapshot 保存的是“与目的完全同组、同 EEW、同 LMUL 的宽源”这一独立情形，
dispatcher 不再执行目的预重排。原指令从 snapshot 读取宽源、从 VRF 当前布局读取
窄源，待其完成后再进入既有 overlap repair，一次性把活动结果、边界寄存器和未扰动
tail 统一到目的 e64 布局。保存窄源的普通 widening 情形仍先规范化目的，再从
snapshot 重放窄源；不重叠或同 EEW 请求不进入新增分支。

### 44.4 阶段验证

精确定向 `rvv:vwiden_overlap_edges` 的“窄源先就绪”和“宽源先就绪”两个子场景均
在最终逻辑上通过，各自 103 个活动结果和全部 tail 元素均正确。共享 snapshot、
reshuffle、MASKU 和 overlap 路径的
`rvv:vrgather_edges`、`rvv:vcompress_edges`、`rvv:vnclip_edges`、
`rvv:vreduction_overlap_edges`、`rvv:vslide_mask_edges`、`rvv:vfirst` 也全部通过。
无临时探针的最终 RTL 还完整通过 integer-stress seed 6：RTL 用时 227.54 秒，
4973 个架构向量请求全部获得响应，8268 个后端 uop 分配与完成一一配对，最大同时
在飞数为 7。非侵入式向量写回比较覆盖 4473 条有目的向量指令和 474394 个确定
字节，`first_mismatch`、未完成请求和未退休请求均为空；7444 条 RTL/Spike 标量
提交也无首差异。该结果同时越过本 seed 先后暴露的 VCOMPRESS WAW、重叠
VRGATHEREI16、零 VL overlap 和 `.wv` 双 EEW 重叠四处独立问题。

## 45. 内存广播请求的分离握手与错误完成

### 45.1 两种停顿现象

最终 RVV corner 回归最初剩余两个超时。`vmask_compare_edges` 停在最后一条
`vs1r.v v18`，`vid_queue_edges` 停在最后一条 `vse16.v v20`。两者都不是数据
比较失败，而是 store 已进入 sequencer 后不再产生可退休响应。第一轮逐周期探针
显示，VSTU 已观察到四条 store 请求，AddrGen 却只接收了前三条；最后一条请求在
lane operand requester 尚未 ready 时先被 AddrGen 接收，随后从广播接口消失，
对应 store data 请求从未进入 lane。

该问题包含两层独立根因。首先，旧 `WAIT` 状态以“当前 dispatcher 请求不写
`vd`”作为标量返回类操作的近似判定。store 同样不写 `vd`，因此残留的 MaskB
valid 可能被误认作当前 store 的标量响应，使 sequencer 提前退出 `WAIT`。修复后
只有持有请求 `pe_req_o` 的 `VMVXS`、`VFMVFS`、`VCPOP` 和 `VFIRST` 能进入标量
返回完成路径，当前 dispatcher 输入不再参与这一判断。

修正上述误判后，普通 store 可以继续推进，但完整 corner 回归又在
`vsegment_emul_edges` 的 masked `vsuxseg2ei32.v` 上暴露相反顺序。探针记录到 lane
和 MASKU 先在周期 2398 接收当前 segment field，接收后 `ready` 按协议拉低；
AddrGen 在周期 2399 才给出 ack。若 sequencer 在 ack 周期重新要求所有接收端的
当前 `ready` 为 1，就会否认前一周期已经发生的握手。segment store 的后续 field
又要等待当前 field 的响应，形成稳定死锁。

### 45.2 分离握手协议

AddrGen、各 lane operand requester 和 MASKU 共享同一条 PE 请求，但它们具有独立
背压，因而“请求完成”不能由任一接收端的单周期 ready 电平表示。sequencer 现在
为处于 `WAIT` 的内存请求保存三类历史状态：

1. `addrgen_acked_q` 保存 AddrGen 是否已经完成地址侧接收，并同时保存 exception、
   exception vstart 和 fault-only-first 元数据；
2. `memory_lane_accepted_q` 按 lane 保存广播 valid 与该 lane ready 同时成立的
   接收事件；
3. `memory_mask_accepted_q` 保存 MASKU 的接收事件；对不使用 predicate 的请求，
   该条件在请求建立时即标为满足。

unmasked unit-stride load 不需要 VRF operand，因此 lane 接收位在请求建立时直接标为
满足。其他 load/store 只有在 AddrGen ack、全部所需 lane 接收位和 MASKU 接收位
均已成立后才向标量核返回响应并撤销广播 valid。各事件可以按任意顺序发生；已经
成立的事件不会因接收端开始执行后把 ready 拉低而丢失。若当前 LSU burst 已产生
异常，既有协议保证有效源已经取得，operand 接收条件按异常完成路径置为满足，异常
元数据仍由实际 AddrGen ack 返回。

lane sequencer 原有的 vid 同步屏蔽、MASKU/VLSU 的运行位继续防止同一请求被重复
采样。本修复没有把各接收端强制成一个组合式全局 ready，也没有改变内存指令退休、
异常或 store 完成的架构顺序；它只把原本隐含的多接收端事务改为显式记账。

### 45.3 最终验证

删除全部本轮临时探针并重新构建 VCS 后，`rvv-corners` 的 24 个用例全部通过。
其中原超时的 `vmask_compare_edges`、`vid_queue_edges` 和新增暴露相反握手顺序的
`vsegment_emul_edges` 分别用时 31.61、18.42 和 12.36 秒。`vstore_signature`、
masked memory、非零 vstart、segment EMUL、widen/narrow、reduction、gather、
compress 和 slide 边界均使用同一最终 `simv` 通过。

覆盖审计随后发现 `vindexed_vstart_edges` 虽已在历史调试中通过，但源码仍被旧的
`.gitignore` 通配规则隐藏，且没有列入固定 corner suite。现已将该源码正式纳入
仓库可追踪范围并加入 `rvv-corners`；使用同一最终 `simv` 对其独立复测，indexed
load/store、`SEW=16`、index `EEW=32`、`LMUL=4` 和 `vstart=63` 的组合在
13.27 秒内通过。当前固定 corner suite 因此包含 25 个可从干净检出重建的测试。

同一最终构建上的 `rvv-failure-regression` 首次运行有 13 项通过，只有完整
`vlsseg` 在默认 300 秒墙钟限制下超时。超时时提交轨迹仍持续增长，已经退休约
17.7 万条指令，因而不属于 commit watchdog 停顿。验证 runner 现支持显式
`--timeout` 覆盖；以 900 秒限制重跑相同二进制后，`vlsseg` 在 418.37 秒通过。
因此该组 14 个历史失败点均已有最终 RTL 的通过证据，同时保留较短的默认限制，
避免普通回归因个别超大 directed test 无条件延长。

同一构建还严格重放 integer-stress seeds 7--10。四个程序的 RTL/Spike 标量提交
匹配数分别为 7446、7437、7429 和 7422；逐条向量写回比较分别覆盖 4548、4383、
4604 和 4315 条有目的向量指令，共比较 1732669 个确定字节。四例的架构向量请求
均获得响应，后端 uop alloc/done 分别为 8414/8414、8151/8151、8497/8497 和
7836/7836，`first_mismatch` 与未完成请求均为空。验证框架 84 项 Python 单元测试
以及最终 24 项 RVV corner 回归同时通过。

## 46. source lifetime 起点漏掉待接收的 lane 边界命令

### 46.1 现象与根因

启用 source-lifetime-aware WAR release 后，integer-stress seed 2 的首个向量状态
差异表明，年轻写者可能在年长读者真正取得源操作数前覆盖其寄存器。原实现把
`source_lifetime_active[vid]` 仅建立在 operand requester 已进入 `REQUESTING` 的
状态上；lane sequencer 已经给出 `operand_request_valid_i`、但共享 requester 尚未
接受命令的边界周期没有计入 lifetime。若该命令因端口占用停在边界，年轻写者看到
的 lifetime 会短暂为零，从而错误解除 WAR 等待。

这里需要区分“命令已经送到 requester 边界”和“VRF 读取已经开始”。前者已使源
寄存器成为架构上不可覆盖的在用数据，即使 requester 内部状态尚未跳转；因此
lifetime 必须覆盖两个阶段，而不能只观察后一个状态机阶段。

### 46.2 修复和定向验证

每个 lane 现在同时扫描所有 operand queue 的边界 valid 和 requester 的
`REQUESTING` 元数据：只要任一 `operand_request_valid_i[q]` 携带该 `vid`，或任一
requester 正在为该 `vid` 发出 VRF/snapshot word，对应 source lifetime 均保持有效。
最后一个源 word 发出、且边界不再保留该命令后才允许年轻写者越过。该修改没有把
WAR 重新退化为“等待年长指令完成”；它只补齐从命令出现到最终源读取之间原本遗漏
的开区间。

新增 `rvv:vwar_pending_source_edges` 以 e16,m8、VL=333 构造稳定次序：先用 WAW
把年长 `vsub.vx` 挡在共享 ALU operand requester 前，使其 `v8` 源命令停留在 lane
边界，再发出写 `v8` 的年轻 `vmul.vv`。修复前同一二进制在 36.98 秒后报告结果
错误；修复后在 34.03 秒通过全部 333 个减法和乘法结果。seed 2 随后越过原首错，
并暴露第 47 节中相互独立的 masked narrowing 布局问题。

## 47. narrowing 三重别名的旧 `vd`、`vstart` 与 `vxsat`

### 47.1 首差异与双布局冲突

source lifetime 修复后的 seed 2 首差异移动到 arch_seq 1818、PC
`0x80001f92`：

```asm
vnclip.wv v4, v4, v4, v0.t    # e8,m2,vl=21
```

该指令中 `v4` 同时表示 double-width `vs2`、窄 `vs1` 和 masked-undisturbed
目的寄存器。宽源与窄源覆盖同一物理寄存器组，却要求不同的 lane 内字节布局，不能
通过一次就地 reshuffle 同时得到。dispatcher 因此保存其中一个完整源视图，再把
物理 VRF 组规范化为另一个视图，并从 lane-local snapshot 重放已保存的源。根据
指令到达前的 EEW 元数据，实际可能是“物理 VRF 保留窄视图、snapshot 重放宽
`vs2`”，也可能是“物理 VRF 保留宽视图、snapshot 重放窄 `vs1`”；修复不能假定
唯一方向。

seed 2 命中后一种方向。活动 mask-on 元素由 VNCLIP 正常生成，但 mask-off 元素必须
保留指令开始前的窄 `vd`。若只使用稀疏 byte-enable 屏蔽写回，这些字节留在宽物理
布局中，后续布局恢复便会把错误字节解释为旧 `vd`。最终产生 3 个确定字节差异；首
差异来自 SLDU、cycle 73798、`v4` byte 13，实际 `0x30`、期望 `0xfe`。

### 47.2 严格限定的旧目的重建

lane sequencer 只在 snapshot 重放 `vs1`、`vd==vs1==vs2`、`vs1` EEW 等于目的
SEW、`vs2` EEW 更宽，且操作属于 `VNSRL/VNSRA/VNCLIP/VNCLIPU` 时设置
`preserve_narrow_vd`。普通 narrowing、非精确三重别名和未使用该 snapshot 方向的
请求均不进入此路径。

重放的窄 `vs1` 通过既有扩展路径进入 VALU。VALU 按当前 narrowing half-cycle 从
每个扩展槽的低 SEW 位重建旧目的元素。真正执行的 active、mask-on 位置保留计算
结果；prestart 或 mask-off 位置写回重建的旧 `vd`。tail 不在当前 `vl` 的结果
byte-enable 内，继续由 overlap fixup 保持。这样写回后的整个有效目的区间均为统一
窄布局，而不是把“未写字节仍处于正确布局”作为隐含前提。

### 47.3 `vstart` 必须遵循 lane shuffle

在上述数据修复后，新增的 `vstart=5` 组合仍稳定失败：元素 4 应保留旧值 `0xc5`，
实际却被活动计算结果 `0x7f` 覆盖。周期探针先排除了 source snapshot 过晚的问题，
随后确认 dispatcher 的 prefix-fixup 与 snapshot 顺序也需要区分：当窄旧目的只能从
snapshot 恢复时，不能在捕获宽源前就地改写重叠前缀；该精确路径改为由最终 VALU
写回恢复 prestart，其他 overlap 仍保留原 prefix-fixup。

剩余首错来自 VALU 的 prestart mask。原辅助函数按线性 byte index 推导元素位置，
但 Ara 的 EW8/EW16 元素在 64-bit lane word 内按 `shuffle_index` 排列。例如 EW8
下一个 lane word 的逻辑元素顺序并不等于物理 byte 0--7，因而线性 mask 会屏蔽错误
字节。现在先由逻辑 byte 得到元素序号，再使用与 VRF byte-enable 相同的
`shuffle_index(..., NrLanes=1, vsew)` 映射到物理 byte。结果生成、旧 `vd` 合并和
写使能由同一 active mask 驱动，避免三处对 prestart 的解释不一致。

### 47.4 `vxsat` 与最终验证

preserve 路径会主动写回未执行位置的旧值，因此其结果 byte-enable 不再能表示哪些
元素真正执行。若直接将 ALU 的逐字节 saturation 标志归并到架构 `vxsat`，prestart
或 mask-off 的饱和中间值仍会错误置位。当前逻辑以经过 shuffle 的 active mask 和
predicate mask 共同门控 `alu_vxsat`，只有实际执行元素可以更新 sticky `vxsat`。

`rvv:vnclip_edges` 现在同时覆盖 e8,m2、VL=21 的三重别名在 `vstart=0` 和
`vstart=5` 下的逐字节结果，以及“唯一 mask-on 元素不饱和、mask-off 元素必然
饱和”的 `vxsat` 场景。修复前，旧目的合并和 `vxsat` 场景分别稳定失败；加入
`vstart=5` 后，上一版最终 RTL也明确报告 `got=0x7f, expected=0xc5`。包含 shuffled
active-mask 修复的同一 directed test 在 123.43 秒通过。

seed 2 的严格重放完整通过：4983 个架构向量请求全部响应，8214 个后端 uop
分配/完成一一对应，最大在飞数为 6；标量提交比较匹配 7423 条，逐条向量写回比较
覆盖 4573 条有目的请求和 514693 个确定字节，`first_mismatch`、未完成请求和未退休
请求均为空。使用最新构建的 `rvv-corners` 26 项全部通过；其中 `vnclip_edges`、
`vindexed_vstart_edges`、`vsegment_emul_edges` 和 `vwar_pending_source_edges` 分别
用时 78.89、12.05、12.55 和 43.76 秒。

同一最新构建随后严格重放 integer-stress seeds 1--10，十例全部为
`PREFIX/VALID/PASS`。合计匹配 74330 条标量提交，逐条向量写回比较覆盖 44971 条
有目的向量指令和 4722155 个确定字节；49845 个架构向量请求全部取得响应，83017
个后端 uop 的 alloc/done 一一对应，最大在飞数为 7。十例的 `first_mismatch`、
未完成请求和未退休请求均为空，因此该结论来自最新 `vstart` shuffle 修复后的 RTL，
而不是修复前已完成的旧回归。

同一构建的 `rvv-failure-regression` 14 项也全部通过。此前容易暴露布局、mask、
gather/compress、slide 和配置状态问题的 13 项均在 62 秒内结束；完整 `vlsseg`
在 900 秒上限下用时 510.28 秒通过。该长点持续退休，不属于 commit watchdog
停顿，也没有通过缩小测试内容规避。

## 48. 已完成 RTL 运行的离线严格后处理

长随机仿真可能已经输出 `Core Test *** SUCCESS ***` 和完整 trace，却因外层 runner
在比较阶段被中断而缺少 `result.json` 或总 `summary.json`。验证入口新增：

```bash
python3 verification/verify.py postprocess-rvv \
  --output verification/out/<existing-run>
```

该命令从 `rtl.command.json` 恢复 ELF、seed 和是否启用 vector trace，直接使用已有
Spike commit log、Ara architecture trace 和 accepted-VRF trace，重新执行标量提交
前缀比较、trace 完整性检查及逐条向量写回比较，不启动 Spike 或 VCS。缺失命令元数据、
ELF、完成标记或 trace 会得到明确的 `ARTIFACT_INCOMPLETE`、`RTL_INCOMPLETE`、
`TRACE_FAIL` 或 `VECTOR_MISMATCH`，不会被当成通过。

验证框架现有 104 项 Python 测试全部通过；其中最终状态门控测试直接驱动单个随机
case 的现有执行路径，覆盖 `SPIKE_FAIL`、`RTL_TIMEOUT`、`RTL_STALL`、`RTL_FAIL`、
`MISMATCH`、`TRACE_FAIL`、`VECTOR_MISMATCH` 和 `PASS` 的判定顺序及进程返回码。
因此软件成功标记、标量提交前缀或向量比较中的任一项不能单独构成通过结论。另以
seed 2 的真实产物做端到端恢复，离线
重建结果为 `PREFIX/VALID/PASS`，仍比较 4573 条向量请求和 514693 个确定字节，证明
恢复流程不依赖重新运行 RTL。

同一输出目录由 dry-run 转为真实运行时，runner 现在会先使旧的 summary/CSV/JUnit
报告失效，并在 `run.json` 中写入 `RUNNING`；真实结果写完后再更新为 `COMPLETE`
和各状态计数。case 日志不被该步骤删除。由此，长回归执行期间不会再把遗留的
`DRY_RUN` summary 误认为当前动态结果。

## 49. 全部随机 profile 的覆盖再审计

将 testlist 中 12 类 profile 的实际生成汇编合并，并排除 checkpoint/signature
重写器后加的诊断指令，共得到 142 个源程序和 512407 条原始向量指令，其中
163065 条使用 predicate mask；`missing_profiles` 和 `missing_reports` 均为空。
各指令族的计数之和严格等于总向量指令数，而不是同一指令在多个类别中重复计数：

| 维度 | 实际生成覆盖 |
|---|---|
| 指令族 | configuration 7572、fixed-point 34414、floating-point 47408、integer arithmetic 87747、load/store 10988、mask logical 30264、mask other 137782、narrowing 29613、permutation 43169、reduction 41943、widening 41507 |
| SEW | e8 1570、e16 1714、e32 1682、e64 1533 次显式配置 |
| LMUL | mf8 353、mf4 789、mf2 1590、m1 973、m2 1027、m4 971、m8 796 次显式配置 |
| policy | tail `ta/tu=3086/3413`；mask `ma/mu=3676/2823` |
| 访存模式 | unit-stride 6037、strided 2126、indexed 1020、segment 789、mask 433、whole-register 410、fault-first 173 |

覆盖分布仍有明确弱项：fault-first、whole-register 和 mask memory 比普通
unit-stride 稀疏一个数量级，mf8 也明显少于 mf2/m1--m4。因此“随机汇编中出现过”
不能替代定向边界验证。当前 catalog 同时保留 199 个 directed RVV 测试和 26 个
固定 corner 测试；后者显式覆盖非零 `vstart`、segment/index EMUL、mask/tail、
source/destination overlap、完整寄存器组、store 后内存签名及 source-lifetime WAR。
随机频次较低不等于缺少定向激励：directed catalog 中的 `vlff` 覆盖 fault-only-first，
`vl1r/vs1r/vmvnrr` 覆盖 whole-register load/store/move，
`vmask_mem_emul_edges` 覆盖 mask memory 的有效长度、EMUL 与零长度行为；
`vsetivli/vsetvli/vsetvl` 及 `vle8/vle16/vle32` 的配置组合覆盖 fractional LMUL
合法性和相关 EMUL 边界。这些测试是否在某版 RTL 上通过仍由该版动态 summary
判定，catalog 中存在测试本身只证明覆盖意图已经落实。
完整 campaign 除检查 `rvv>=199/app>=50/random=142` 的类别数量外，还把
`rvv-corners` 的 27 个测试作为强制名称清单；删除其中任一项，即使以其他普通测试
补足总数，也会在启动仿真前报告覆盖缺失。随机侧同样强制保留 12 类 profile 及各自
最低 seed 数，不能以增加 nightly seed 掩盖 arithmetic、load/store、FP、vtype
或 mixed-control profile 的缺失，并拒绝重复 profile。当前 catalog 与 12 类、
142 程序的随机配置均已通过这些门槛。
完整 campaign 结束时还会合并每个 profile 从实际生成汇编得到的
`stimulus_coverage.json`，核对每类源码数，并要求 configuration、定点、浮点、整数、
访存、mask、narrowing、permutation、reduction 和 widening 指令族，七类访存模式，
四种 SEW、七种 LMUL、两组 tail/mask policy 以及 masked 指令均有非零生成记录。
缺少任一维度会使 campaign verdict 失败。使用本轮已有 142 份真实生成源码执行该
新 gate 已通过；这说明阈值与当前生成器实际能力一致，而不是只在构造数据上成立。
coverage 在 signature/checkpoint 重写之前采集，并仅统计 `main` 与生成的 `sub_*`
代码区间；运行库以及后续诊断插桩中的向量配置和访存指令不会计入这些数字。

campaign 元数据同时记录固定 `simv` 的 SHA-256 和 RTL、app、验证脚本的源码快照。
初版快照错误包含 `apps/compiler_macros.h`；该文件由 app 编译规则根据固定编译选项
生成，回归本身会重写它，因而会造成并不存在设计修改时的假哈希变化。快照过滤现在
显式排除该生成文件，并有单元测试验证其内容变化不会改变源码摘要。已经启动且使用旧
过滤规则的 campaign 可用于暴露功能失败，但不作为“运行期间源码未变”的最终证明；
最终收敛回归必须由修正后的入口重新建立元数据。

本节数字只证明激励覆盖，不宣称 142 个随机程序已经全部在当前 RTL 上通过；动态
通过状态必须以对应 run 的严格 `summary.json` 为准。

## 50. 完整 directed catalog 的收敛

使用第 47 节最终 RTL 首次运行当前 199 项 directed RVV catalog 时，193 项通过，
`vsetivli` 发生一项功能失败，`vwmul/vwmulu/vwmulsu/vmacc/vnmsac` 五项达到 900 秒
墙钟上限。`vsetivli` 的根因和修复见第 17.2 节。五个超时日志在终止前持续输出正常
测试进度，其中 `vwmul` 已打印软件成功标记，未出现 watchdog、断言或结果错误；
运行期间机器上还存在其他项目的多个 VCS 进程，因此不能把这些墙钟超时归类为 RTL
失败。

使用包含 `vsetivli` 修复的同一新构建，在系统负载恢复后复跑五项，分别得到
`vwmul=36.11s`、`vwmulu=36.01s`、`vwmulsu=36.71s`、`vmacc=49.77s` 和
`vnmsac=50.28s`，全部 PASS。严格补强后的 `vsetivli` 也在 61.02 秒 PASS。
因此原 199 项运行中的全部六个非通过项均已获得当前 RTL 的通过证据；为排除
`vsetivli` 配置修复对其他测试中配置指令的间接影响，又使用该构建重新运行完整
directed catalog。统一 summary 包含 199 项且全部 PASS；严格补强后的 `vsetivli`
用时 50.74 秒，26 个 `rvv-corners` 均在该 summary 内通过，最长的 `vlsseg` 用时
432.54 秒。至此 directed catalog 已形成单次、同构建、无拆分补跑的完整通过证据。

## 51. FPNew 独立 operation group 跨界导致结果归属错位

### 51.1 首错与根因

FP64 seed 6 的第一个确定差异位于一条普通 FP 向量结果。逐条写回比较先证明错误
不是 Spike 末态签名、NaN payload 或比较器映射造成，再通过 FPNew 输入、输出 tag
和 VMFPU processing 指针的周期探针确认：前后两条向量 FP 指令进入了不同的
FPNew operation group。FPNew 的 ADDMUL、DIVSQRT、NONCOMP 和 CONV 是相互独立的
流水线，并由共享输出仲裁器返回结果；不同 group 之间不保证按输入顺序完成。

原 VMFPU 只依据名义延迟比较和除平方根特例限制年轻指令，但 result queue 的接收端
仍按 `processing_pnt` 所指的程序顺序解释下一个结果，且没有保存足以重排任意 group
输出的 ROB。因此，年轻 group 的结果先返回时，数据会被赋给仍在处理的年长向量
指令。已有按延迟排序的规则不能覆盖可变背压和彼此独立的 group，也不能仅靠增大
固定 latency 常数安全修复。

### 51.2 修复原则与实现

`hardware/src/lane/vmfpu.sv` 现在把 Ara 操作映射到 FPNew 的四类 operation group。
同一 group 内的连续向量指令仍可流水执行；只有 issue 指针准备跨越 group 边界、且
年长指令仍处于 processing 阶段时，才阻止年轻指令继续向 FPNew 投放。这样使现有
按序 processing/result queue 的结构与 FPNew 可观察的返回顺序一致，而不把所有 FP
指令全局串行化。另保留仿真断言：非 reduction 结果被接受时，FPNew 返回 tag 中的
`vid/op` 必须与 VMFPU 当前 processing 指令一致。断言只检查不变量，不参与综合功能。

### 51.3 最终验证

删除定位探针并重新构建后，FP64 seed 6 在 145.60 秒内通过。3055 个架构向量请求
全部响应，4990 个后端 uop 的 alloc/done 一一对应，最大在飞数为 6；标量提交前缀
匹配 5561 条指令，逐条向量写回比较覆盖 2746 条有目的请求和 236163 个确定字节，
`first_mismatch`、未完成请求和未退休请求均为空。用于暴露跨 group 边界的定向
`vfrsub_pipeline_edges` 也在最终构建上通过。

## 52. `vslidedown` 目的 WAW 漏检允许年轻写者越过长延迟 MFPU

### 52.1 现象与周期证据

有效化后的 FP64 seed 2 在以下相邻序列后得到错误的 `vfredmax` 结果：

```asm
vfsqrt.v       v0, v16
vslidedown.vx  v0, v24, a7
vfredmax.vs    v17, v0, v10
```

该 reduction 自身正确等待并读取了 106 个源元素。周期探针进一步确认，错误值恰好
来自更早的 `vfsqrt`，而不是 reduction tree：年轻 `vslidedown` 已先把目的组写成
预期值并完成，随后长延迟 `vfsqrt` 的剩余写回又覆盖了同一 `v0` 组，最后 reduction
忠实读取了被晚到旧写者破坏的 VRF 状态。这是写入顺序错误，而不是 RAW 检测或
reduction 中性值错误。

### 52.2 根因与修复

sequencer 对 slide 使用了比普通逐字链式执行更严格的整指令边界，因为 SLDU 的源、
目的访问顺序不能安全套用普通 result-paced chaining。`VSLIDEUP` 的边界门控包含
目的 `hazard_vd`，原 `VSLIDEDOWN` 分支却只检查 `hazard_vs1/hazard_vs2`。因此，同一
目的组存在年长写者时，年轻 slide 仍可进入 SLDU，形成上述 WAW 越序。

`hardware/src/ara_sequencer.sv` 的实际接受条件和 `FOR_VERIFY` 阻塞镜像现均要求
`VSLIDEDOWN` 检查 `hazard_vd`、`hazard_vs1` 和 `hazard_vs2`。该修改只在存在真实
slide 目的 WAW 或源 hazard 时串行，不影响目的组独立的 slide。新增
`vreduction_overlap_edges` 场景以 e64,m8、VL=106 构造长延迟 `vfsqrt v0`，随后用
`vslidedown v0` 写零并以 `vfredmax` 观察最终状态；修复前可稳定读到旧平方根值，
修复后结果严格为正零。

### 52.3 最终验证

无临时探针的最终构建通过 `vreduction_overlap_edges`、`vslidedown`、`vfsqrt` 和
`vfredmax` 四组定向回归。原有效 seed 2 也在 187.80 秒内通过：2968 个架构向量
请求全部响应，4955 个后端 uop 全部完成，最大在飞数为 7；标量提交前缀匹配 3559
条指令，逐条向量写回比较覆盖 2710 条有目的请求和 365496 个确定字节，没有首错、
未完成请求或未退休请求。历史 FP64 seed 1 的长 slide 停顿点随后以同一构建重放，
也在 154.69 秒内完整通过。

## 53. 当前覆盖闭环与最终 campaign

当前 catalog 含 201 个 directed RVV 测试和 50 个应用。相对第 50 节统一通过的
199 项，新增项只有 `vfrsub_pipeline_edges` 和 `vwhole_vstart_edges`；两者已分别
使用当前无探针最终 `simv` 在 12.76 秒和 23.79 秒内通过。验证框架 111 项 Python
单元测试全部通过。

12 类随机 profile 共定义 142 个程序。静态覆盖来自重写前的真实 riscv-dv 汇编，
已覆盖四种 SEW、七种 LMUL、两类 tail/mask policy、masked 指令、主要算术与访存
指令族，以及 unit-stride、strided、indexed、segment、mask、whole-register 和
fault-only-first 七类访存模式。定向补强同时明确包含：

- `vasub/vasubu` 的 vv/vx 与 masked 形式；
- averaging 的 4 种指令、4 种 `vxrm` 和 4 种 SEW；
- 8 种 mask logical 在 8 组 VL/LMUL/非零 `vstart`/policy 下的矩阵；
- widening、narrowing、reduction、slide、gather、compress、segment/index EMUL
  与重叠边界；
- 10-seed checkpoint profile 中每条向量指令后的完整 VRF 状态，以及每条 vector
  store 后所有生成数据区间的逐字节内存签名。

最终统一 campaign 已使用当前 `simv` 启动，输出目录为
`verification/out/final-full-campaign-run2_20260811/`。它同时要求 201 个 directed、50 个
应用和 142 个随机程序产生唯一结果，并在完成时重新合并实际生成汇编的覆盖报告；
任一动态失败、缺失结果、重复结果或语义覆盖维度缺失都会使总 verdict 失败。在该
campaign 结束前，本节只确认激励和检查机制完整，不宣称 142 个随机程序已全部通过。

## 54. narrowing overlap 清洗器漏识别静态 `vsetvl`

### 54.1 现象与归类

最终 campaign 首次启动后，arithmetic profile 在生成后处理阶段返回错误，尚未进入
Spike 或 RTL：

```text
cannot validate narrowing source overlap without legal LMUL:
vnclip.wv v24, v12, v30
```

该指令之前的配置序列为 `li s6,0x81; vsetvl zero,zero,s6`。原清洗器只解析立即数
形式的 `vsetvli/vsetivli`，遇到寄存器形式 `vsetvl` 时没有更新当前 LMUL，随后拒绝
判断 `.wv` 窄源和宽源组是否重叠。这是验证环境对确定配置数据流覆盖不足，不是 RTL
执行失败；组件没有生成 `summary.json`，也没有可称为“首错”的动态指令。

### 54.2 严格修复

`verification/ara_verify/random_rvv.py` 现在复用 strict signature 路径已有的直线到达
定义分析：对 `vsetvl` 的 `rs2` 反向查找最近的 GPR 写者，只有可证明为常量 `li` 且
中间没有控制转移或覆盖写时才接受。寄存器 ABI 名与 `xN` 名统一归一化，因此
`li x22,...` 与 `vsetvl ...,s6` 也能正确关联。随后按 RVV vtype 编码严格解码
`vlmul[2:0]`；`0x81` 得到 `m2`，目标 `v12-v15` 宽源与 `v30-v31` 窄源不重叠，原
指令应保持不变。真正保留编码的双 EEW overlap 仍改写到不重叠的窄源寄存器组；
masked 指令不会选择包含 `v0` 的替代组。

若 `rs2` 来自算术计算、控制流合流、未知写者、`vill` 或保留的 VLMUL 编码，清洗器
继续明确失败，不根据上一条配置或寄存器号猜测。新增测试覆盖 `x22/s6` 别名、合法
保持、masked overlap 改写和未知定义拒绝。验证框架现有 113 项 Python 单元测试
全部通过；失败 campaign 产生的 10 份 arithmetic 汇编也已在临时副本上全部完成
清洗，其中只改写 1 条 `vnsra.wv` 和 2 条 `vnclip.wv` 保留编码。独立 arithmetic
10-seed 端到端重跑位于
`verification/out/arithmetic-vsetvl-sanitizer-fix_20260811/`，动态结论以其最终
`summary.json` 为准。

## 55. Store mixed-EEW、segment restart 与活动源布局

### 55.1 Masked store 的两套物理布局

VSTU 将逻辑 store byte 映射到 VRF lane/byte 时，需要使用数据源当前保存的
`old_eew_vs1`；但 MASKU 返回的 predicate bit 是按当前 store EEW 组织的。原实现用
数据 byte 的同一物理 lane/offset 同时索引数据和 mask。数据源布局与当前 store EEW
不同时，AXI `wstrb` 因而选中错误字节，即使数据 byte 本身来自正确位置也会形成错误
的 masked store。

`hardware/src/vlsu/vstu.sv` 现在独立计算两套索引：store data 继续按
`old_eew_vs1` shuffle，predicate byte 则按当前 `vtype.vsew` shuffle；两者只在最终
AXI byte 上合并。该修复没有改变 unmasked store，也没有假设数据与 mask 的内部 EEW
布局相同。`verification/out/vstu-mask-layout-fix-load-store-10seed_20260811/` 的
load/store seeds 1--10 全部 PASS。

### 55.2 非零 `vstart` 的首个 segment micro-op

segment sequencer 将一条多字段访存展开为逐字段、逐元素 micro-op。原首 micro-op
固定设置 `vl=1` 并让 field 0 的 unit-stride 操作原样通过。对 `vstart>0`，前者会使
内部请求满足 `vl<=vstart` 而成为空操作；后者使用 `base+vstart*EEW`，而 segment
element 的正确步长应为 `(nf+1)*EEW`。此外，sequencer 曾在仅识别出 held segment
指令、但请求尚未握手时提前进入展开状态，可能丢失 field 0。

`hardware/src/segment_sequencer.sv` 现在只在架构请求真实握手后启动；首 micro-op
设置 `vl=vstart+1`，并与后续 micro-op 一样把 unit-stride segment 表示为 stride
`(nf+1)*EEW` 的内部请求。字段寄存器偏移继续按 EMUL 计算。修复后的
load/store/slide seed 9 在
`verification/out/segment-vstart-fix-load-store-slide-seed9-strict_20260811/`
严格通过。

### 55.3 Restarted store 的活动源布局

`vstart` 可能使 store 源组头完全处于非活动区，而真正供数的后续寄存器具有不同
EEW 物理布局。原 dispatcher 固定从 `vs1` 组头读取 `old_eew_vs1`，segment store
后续字段也可能沿用 field 0 的标签。VSTU 因而会用错误 EEW 解 shuffle 活动数据。

dispatcher 现在根据当前 store EEW 和 `vstart` 计算首个活动源寄存器，并从该寄存器
取得布局标签；segment sequencer 则按字段 EMUL 偏移和当前活动元素为每个 store
micro-op重新选择 `old_eew_vs1`。修复后的 load/store/slide seed 1 在
`verification/out/store-active-layout-final-seed1-strict_20260811/` 完成严格比较：
5785 条向量目的写回、2213886 个确定字节一致，且全部 8643 个架构向量请求和
8029 个后端 uop 完成。

## 56. 非法向量访存异常恢复与严格比较映射

### 56.1 RTL 停顿根因

checkpoint seed 9 中的 `vlsseg8e8.v v18,(s6),a7` 在 e8,m2 下需要从 `v18`
开始的 16 个架构寄存器，越过 `v31`，必须产生 illegal-instruction exception。
CVA6 accelerator dispatcher 在 Ara 完成全部 RVV 合法性检查前，已按 opcode 将该
请求计为 pending vector load。Ara 的 segment register-span 检查原来只置通用
`illegal_insn`，没有产生 load completion；同时它已保留 segment 状态，而非法请求
不会产生 `seg_mem_op_end`。异常本身能够返回，但 trap handler 的第一条 scalar store
会持续等待这个实际上从未进入 VLSU 的 phantom load。

`hardware/src/ara_dispatcher.sv` 的统一非法响应现在根据原请求类别同步置位
`illegal_insn_load` 或 `illegal_insn_store`，复用已有延迟 completion 脉冲平衡 CVA6
pending-memory 记账；非法 segment 请求同时清除 `pending_seg_mem_op`。该处理只发生
在已确定拒绝的请求上，不会向 VLSU 投放访问，也不改变合法访存的完成路径。

新增 `villegal_segment_recovery` 在 crt0 的 M-mode `rvtest_init` hook 中安装 trap
handler。handler 的第一条显式访存保存 `mcause`，随后跳过非法指令并 `mret`；用户态
再执行第二条 scalar store。旧 `simv` 在 40.08 秒测试上限内无法完成，修复构建在
8.13 秒通过，删除临时探针后的最终构建在 10.35 秒通过。定位使用的异常和 pending
记账探针随后已从源码删除。

### 56.2 Trapped request 的比较器映射

RTL 修复后 checkpoint seed 9 已在 125.38 秒完成软件执行，但逐向量比较器把已 trap
的架构请求映射到下一条正常 vector retirement，形成映射错误而非数据 mismatch。
`verification/ara_verify/vector_commit.py` 现在按 CVX transaction ID 关联
`arch_start` 与 `cvx_resp`，记录 `trap=1` 的 architecture sequence，并在退休序列映射
时跳过这些请求。结果中单独保留 `trapped_requests`，因此异常不会被静默当作普通
完成，也不会错位消耗后继退休记录。

新增单元测试覆盖“一个 trapped vector request 后紧跟一条正常 vector request”的
映射。验证框架当前 114 项 Python 单元测试全部通过。对已经完成的 seed 9 artifact
离线重比得到 PASS，521 条向量目的写回和 35236 个确定字节一致，并识别 9 个 trapped
请求；随后经标准 runner 在线复跑也在 135.83 秒得到严格 PASS，证据目录为
`verification/out/checkpoint-seed9-final-pass-strict_20260811/`。

## 57. 当前完整 campaign 状态

当前 catalog 包含 204 个 directed RVV 测试、50 个应用测试和 12 类共 142 个随机
程序，总计 396 项。`villegal_segment_recovery` 与 `vunit_vstart_edges` 已加入不可缺失的
directed 覆盖门禁；
随机门禁仍要求四种 SEW、七种 LMUL、两种 tail/mask policy、主要指令族及七类访存
模式均在实际生成汇编中出现。第 53 节记录的旧 campaign 没有覆盖全部 profile，不能
作为最终闭环证据。新的统一 campaign 必须产生 396 个唯一结果、完整语义覆盖报告且
全部动态检查通过，才可将验证状态记为完成。

## 58. 标量除法/平方根 1 ULP 差异

### 58.1 首错聚类与根因

最终 395 项 campaign 中，11 个随机 case 的第一个 scalar mismatch 均落在
`fdiv.s/d` 或 `fsqrt.s/d`，实际值与 Spike 只差最低 1 bit。它们分布在
mixed-control 和 nightly 多个 seed，操作数、精度和 PC 均不同，但共同经过 CVA6
`fpu_wrap.sv` 中配置为 `fpnew_pkg::PULP` 的除法/平方根实现。向量 VMFPU 此前已经因
同类 IEEE 舍入边界问题选用 THMULTI；因此这些差异不是提交比较器、NaN payload 或
单条随机程序构造造成，而是标量 FPU 选择了不同的 DivSqrt 实现。

### 58.2 修复与验证边界

标量 bulk FPU 的 `DivSqrtSel` 已改为 `fpnew_pkg::THMULTI`，其余 FPNew operation
group、流水线和接口不变。mixed-control seeds 9/10 以及 nightly seed 33 均在新构建
上完成严格 PASS。nightly seeds 14/29/37 也在当前最终构建上分别以
293.16/125.28/209.49 秒完成完整严格 PASS。
nightly seeds 11/48 曾在中间构建越过原 `fdiv/fsqrt` 首错并暴露更晚的向量
indexed-segment load 和整数余数差异；第 65、66 节记录了后续修复集合上这两个完整
case 的最终 PASS。

## 59. Unit-stride restart 的 VRF/AXI 字节边界

### 59.1 周期证据与根因

nightly seed 22 在 `VL=38、vstart=25、e8` 的 `vle8.v` 后永久保留一个 VLDU
instruction。定向探针记录到 AddrGen 正确生成地址 `0x8001b242`、13-byte 逻辑访问，
并发出一个覆盖全部数据的 AXI beat。首个 VRF aggregate word 从 element 25 开始，
实际只剩 7 byte 容量；但 VLDU 原来的 `valid_bytes` 选择在“指令剩余量小于一个
aggregate word”时直接采用全部 13 byte，没有再与当前 VRF word 的 7-byte 空间取
最小值。结果是 AXI 侧确认消费 13 byte，只有前 7 byte 被映射到 VRF，后 6 byte
丢失，而 instruction/commit counter 仍等待这 6 byte，最终形成无请求可返回的停顿。

VSTU 使用了同样的二选一表达式，因而非零 `vstart` store 也存在等价的过量消费风险。
该问题与地址队列容量、AXI burst 生成或后端 sequencer hazard 无关。

### 59.2 修复与回归

VLDU 和 VSTU 现在都把每周期传输量定义为三个独立上限的最小值：当前指令尚未处理的
byte、当前 VRF aggregate word 剩余的 byte，以及当前 AXI beat 可用的 byte。这样
同一 AXI beat 可以在相邻周期安全拆成 7-byte 和 6-byte 两个 VRF payload，AXI beat
只在全部逻辑 byte 被消费后握手完成。定位用的逐周期探针已从源码删除。

新增 `vunit_vstart_edges` 固定覆盖 `VL=38、vstart=25、e8` 的 unit-stride load 和
store，并选择基址复现短尾部位于一个 AXI beat 内的边界；该测试在最终无 VLDU 探针
构建上 11.75 秒 PASS。原 nightly seed 21 的 `vle8.v` 非零 `vstart` 单 byte 错误也
在同一构建上完整严格 PASS：标量提交比较、向量逐请求写回比较均无差异。原始停顿点
所在的 nightly seed 22 也在 594.50 秒完成完整严格 PASS，且向量逐请求比较为 PASS；
它已越过第 243 个架构向量请求处的原卡死 load，并执行至程序正常结束。

## 60. Indexed store 的 mixed-layout 源操作数去重

### 60.1 后续 load 首错与真实写入源

nightly seed 1 在 `vloxseg2ei32.v v8,(a6),v0` 读取地址 `0x8001effe` 时，RTL 得到
`0x003c`，Spike 得到 `0x004e`。AddrGen 探针确认 indexed segment load 生成了正确
地址，VLDU 也忠实接收了内存中的 `0x003c`；因此该 load 只是观察到了更早的错误。
回溯同一地址的写者后，首个破坏来自
`vsoxei16.v v24,(t3),v28`：79 个有序 store element 均指向同一 halfword，Spike
按元素顺序最终写入 element 78 的 `0x004e`，RTL 却留下了较早元素的 `0x003c`。

该 store 使用 e16,m4 数据组。发射前的物理 EEW notebook 为
`v24-v27 = EW8/EW16/EW16/EW16`；`v24` 的架构字节未变，只是物理 lane 布局与其余
寄存器不同。VSTU 对一条 store 使用单一 `old_eew_vs1` 解 shuffle 整个活动数据流，
所以 dispatcher 必须先把 mixed-layout 源组归一化。周期探针显示 dispatcher 已正确
检测到该条件并形成 `reshuffle_req=3'b100`，但原 store 仍未经重排进入 VSTU。

### 60.2 根因与源码修改

重排请求形成后，dispatcher 会去除指向同一架构操作数的重复 reshuffle。原实现用
`insn.varith_type.rs1/rs2/rd` 比较寄存器号；这只对算术编码成立。indexed store 的
这些位域分别承载 scalar base、index vector 和 store data，不能表示解码后的
`vs1/vs2/vd` 关系。在本例中两个无关编码字段碰巧相等，数据源的 bit 2 重排请求被
误清除，状态机保持 `NORMAL_OPERATION`，随后 VSTU 以 `EW8` 解释整个 e16,m4 数据组。

`hardware/src/ara_dispatcher.sv` 现改为比较已经完成指令类型解码的
`ara_req.vs1`、`ara_req.vs2` 和 `ara_req.vd`。这些字段对算术、访存和内部维护请求
具有统一的操作数语义；真正别名仍会去重，不同操作数不会再因复用编码位域而误判。
修复没有把所有 multi-register store 强制重排，统一布局的常见路径保持不变。

### 60.3 定向与随机验证

`vstore_signature` 新增 e16,m4、VL=79 场景：先以 EW16 写入 `v24-v27`，再通过 EW8
视图重写 `v24` 的相同原始字节，构造架构值不变但物理布局混合的数据组；`v28-v31`
中的全部 index 均为零，并使用 ordered indexed store 写同一地址。最终内存必须等于
逻辑 element 78。该测试与原有 unit、strided、indexed、segment 和 restart store
签名在最终无定位探针构建上共同 PASS。

原 nightly seed 1 随后完成完整严格重放，RTL 用时 442.63 秒，约 4900 条随机程序
指令执行至正常退出，逐向量 checkpoint 结果为 PASS。它既越过此前的 unit-stride
restart 停顿，也越过本节的 ordered indexed store 和后续 segment load 首错。

## 61. Mask destination tail 的跨指令不确定性传播

### 61.1 假阳性首错

nightly seed 15 的逐向量比较首错位于 e16,m1、VL=61 的
`vmul.vv v11,v15,v9,v0.t`。RTL 在 `v11` 的 12 个 byte 写入乘积，而 Spike 对应 byte
为零。乘法之前紧邻 `vmxor.mm v9,v25,v27`；该 mask logical 指令只定义 destination
的前 61 个 mask bit，后续乘法却把 `v9` 当作普通 e16 数据组读取，需要 976 bit。
因此从 e16 element 3 的高位开始，乘法输入已经包含前一条 mask destination 的 tail。

RVV 规定 mask-producing instruction 的 destination tail 总是 agnostic，不受
`vtype.vta` 控制。Spike 和 RTL 对这些 bit 选择不同值都合法，且不确定性必须传播到
读取这些 bit 的后续普通向量结果。该现象不是 MFPU 乘法错误，也不能通过强制 RTL
匹配 Spike 的任意 tail 取值解决。

### 61.2 比较器修复与覆盖含义

`verification/ara_verify/vector_commit.py` 原先对所有 destination 共用
`vector_tail_agnostic`；严格流被统一改写为 `tu/mu` 后，mask destination 的 tail
因而被错误标成“保留且确定”。现在 mask result 分支无条件把 `element>=vl` 的 bit
标记为未知，并复用已有逐元素 source-knownness 传播，使后续读取这些 bit 的算术结果
同样退出 bit-exact 比较。新增单元测试固定构造 `vmxor.mm` 在 `tu` 下产生 61 个有效
bit，再将同一寄存器作为 e16 乘法源，检查 bit 61 之后的不确定性进入乘法 destination。

修复后 16 项 vector-commit 专项单元测试通过；nightly seed 15 使用原 RTL artifact
离线重算后由 VECTOR_MISMATCH 变为 PASS，4836 条有 destination 的向量请求均完成且
无首错。该随机流最终只有 39544 byte 保持严格可比较，另有 820316 byte 因 mask tail
及其传播被跳过。此结果证明原 mismatch 为假阳性，但也表明该 seed 的动态可观察覆盖
较低；后续 campaign 应同时报告 compared/skipped unknown byte，不能仅以 PASS 代替
覆盖质量判断。

## 62. VCOMPRESS/VRGATHER 的 ad-hoc 源请求身份丢失

### 62.1 死锁证据与根因

nightly seed 26 原先在 `vmv2r.v v16,v24` 后停止退休。周期探针显示 lane operand
requester 中同时残留 id 0 和 id 4 的请求，二者又分别等待对方所在的 global hazard
row，形成无法由结果脉冲解除的环。沿动态请求回溯后，污染起点是更早的
`vcompress.vm v0,v8,v15`：该指令实际分配 `vid=1`，但 MASKU 为
VCOMPRESS/VRGATHER 生成的逐元素 MaskB 请求只携带 `idx/eew/vs`，lane sequencer
构造 `operand_request` 时结构体默认把 `id` 置为 0。

这类请求绕过常规 lane 指令的顺序源请求生成路径。错误 id 不只影响调试标签：operand
requester 用它索引 `global_hazard_table`，source-lifetime 状态也按该 id 归属。当 vid 0
被后续指令复用后，仍在队列中的旧 VCOMPRESS 源请求会读取新指令的 hazard row，并把
自己的源生命期错误地记到新指令上。随机流最终形成 id 0/id 4 的相互等待；因此根因是
请求身份与 payload 未保持对齐，而不是 whole-register move 本身的相关性规则。

### 62.2 RTL 修复

`hardware/include/ara_pkg.sv` 的 `vrgat_req_t` 新增 `vid_t id`。MASKU 在
`hardware/src/masku/masku.sv` 形成请求时写入当前 `vinsn_issue.id`；各 lane 的
`hardware/src/lane/lane_sequencer.sv` 再把 `masku_vrgat_req_q.id` 原样写入 ad-hoc
MaskB `operand_request.id`。地址、EEW、源寄存器、结束 token 和 no-data token 的原有
语义不变。这样 request ID 与逐元素地址在 MASKU FIFO、广播握手和 lane spill register
中作为同一个结构体传播，不能再由默认字段伪造为 vid 0。

最终无定位探针构建上的 `rvv:vcompress_edges` 在 13.35 秒通过。原 seed 26 使用同一
最终构建在 277.30 秒完成严格重放并得到 PASS：4194 个架构向量请求和 4637 个后端
uop 全部完成，无未完成请求，scalar commit、CVXIF 生命周期和 vector writeback 均
通过。证据目录为 `verification/out/replay-nightly-seed26-vrgat-final_20260811/`。用于
定位 whole-move 停顿的高频探针随后已删除。

## 63. Agnostic 数据进入 mask 结果时的严格未知性传播

### 63.1 VMSOF 与比较指令假阳性

seed 26 越过 RTL 死锁后，首个逐写回差异位于
`vmsof.m v17,v18,v0.t`。其前一条 `viota.m v16,v13,v0.t` 在 e16,m8 下把
`v18` 作为目标组成员，但 element 128 被 predicate 屏蔽且当前为 mask-agnostic。
Spike 为该元素选择全 1，RTL 合法地保留旧值 `0xea30`。VMSOF 随后把 `v18` 当作 packed
mask 读取，两种合法前态使“第一个 1”的位置不同：Spike 得到低 byte `0x03`，RTL
得到 `0x11`。MASKU 探针证明 RTL 的前缀扫描与它实际读取的输入一致。

修正该误报后，下一处首错是 `vmsleu.vv v3,v16,v8`。它同样读取了此前 agnostic 的
数据元素；比较结果每一位由相应数据元素产生，但旧比较器只对普通数据 destination
传播 source unknown，明确跳过 mask destination，因而又把合法分叉误报为 RTL 错误。

### 63.2 比较器修复

`verification/ara_verify/vector_commit.py` 现在按 mask 指令类别传播未知性：

- 对 `vmsbf.m/vmsof.m/vmsif.m`，逐 bit 维护“此前是否已见 1”的可能状态集合；未知源
  bit 或未知 predicate 会分叉该状态，只有确实可能产生不同结果的目标 bit 被标为未知。
- 对整数/浮点比较以及 carry/borrow mask 结果，按当前 SEW 将目标 mask bit映射回对应
  的源数据元素；任一参与源 byte 未知时，仅污染该结果 bit。
- 对 mask logical，直接按 packed bit 传播两个 mask 源的未知位；普通 masked-off、
  tail 和 undisturbed 行为仍由原有 policy 规则处理。

新增单元测试分别固定 `VIOTA agnostic -> VMSOF` 前缀传播和 e16 数据比较源污染。
vector-commit、postprocess 等全部 117 项 Python 单元测试通过。使用完成后的 seed 26
artifact 离线重算时，VMSOF 和 VMSLEU 两处假阳性均消失，完整向量写回比较为 PASS。
该修复不会把整个 mask destination 粗略跳过，仍保留所有输入确定、语义确定 bit 的
逐位严格比较。

## 64. 小 VL 有序浮点归约遗留 lane selector

### 64.1 停顿链路与周期证据

nightly seed 6 原先在 e64,m8、VL=3 的 `vzext.vf4 v24,v8,v0.t` 前停止推进。该指令
首先由 dispatcher 产生一个 `VSLIDEDOWN` 内部请求，把源寄存器组转换为后续 widening
运算所需的物理 EEW 布局。主 sequencer 的逐 PE 探针显示 vid 0 的四个 lane、MASKU
和 VLSU 均已释放，只有 SLDU 仍在飞；SLDU 又固定停在第一组输入，
`sldu_operand_valid=4'b0111`，即 lane 0--2 已有数据而 lane 3 永久缺失。

lane3 的共享 SLDU/ADDRGEN/reduction selector FIFO 此时队首为 `FPU_RED_SEL`，新布局
转换的 `SLDU_SEL` 已排在其后。回溯发现该旧表项来自前面的 e64,m8、VL=3
`vfredosum`：前三个 lane 各有一个活动元素，lane3 的局部 VL 为零。有序浮点归约链只
从实际活动 lane 产生事务，因此 lane3 不会出现 `sldu_mfpu_req_valid` 或
`fpu_red_complete`；但原 lane 控制仍无条件为每个收到归约命令的 lane 压入
`FPU_RED_SEL`。该无生产者表项既不能弹出，又阻止后续 lane3 operand stream 选通，
最终使 SLDU 为保持四 lane 原子对齐而停顿。

### 64.2 最终修复及适用边界

`hardware/src/lane/lane_sequencer.sv` 现在仅对局部 VL 为零的
`VFREDOSUM/VFWREDOSUM` 设置 `skip_sldu_operand`。VMFPU 控制请求仍被保留，只有不存在
对应事务的 lane selector reservation 被取消；`hardware/src/lane/lane.sv` 的
`FPU_RED_SEL` 入队条件同步使用该标志。有活动元素的 lane、归约结果顺序和 SLDU 全局
链均不变。

该条件不能扩展到所有浮点归约。定位过程中曾用宽条件验证边界，随即在 VL=3 的
`vfredmin` 暴露停顿：无序 min/max/sum 归约需要空 lane 注入中性贡献，SLDU 会等待其
selector 和结果。最终条件因此只包含两条 ordered-sum 指令；整数归约和无序浮点归约
继续保持所有 lane 协作。这个反例同时证明修复依据的是归约协议差异，而不是按 VL
粗略跳过空 lane。

### 64.3 定向与随机回归

`rv64uv/vfredosum.c` 新增 `VL=3` 的有序归约后立即执行 `vslidedown.vi`。该序列直接
检查空 lane selector 的生命周期：旧逻辑会在后继 SLDU 指令上停顿，最终无探针 RTL
在 61.92 秒通过。最终构建还通过 `vfredosum/vfredusum/vfredmin/vfredmax`、
`vreduction_lmul_edges`、`vreduction_overlap_edges` 和 `vcompress_edges`。

原 nightly seed 6 使用同一最终无探针 simv 在 163.07 秒完成严格重放，约 1.8 万条
Spike 指令执行到正常退出，scalar commit 与逐向量 writeback 均为 PASS。它同时越过
原 `vzext.vf4` 停顿和修复边界检查中出现的 `vfredmin` 位置。最终证据目录为
`verification/out/replay-nightly-seed6-final-no-probe_20260811/`。

## 65. Nightly seed 11 的 indexed segment 复核

### 65.1 旧首错与 micro-op 展开

标量 DivSqrt 切换为 THMULTI 后，旧 seed 11 artifact 的首个向量差异位于
`vloxseg8ei32.v v15,(s4),v31`，配置为 `e32,mf2,VL=11,vstart=1`。旧 trace 在
`v17` 的 element 3 写入 `0x00002266`，而 Spike 期望 `0x3fe00002`。该指令由 segment
sequencer 展开为 10 个活动 element 与 8 个 field，共 80 个单元素 load micro-op。

使用当前最终 RTL 的 `ARA_DEBUG_SEGMENT` 周期探针确认，内部请求严格按
`(element=1,field=0)` 到 `(element=10,field=7)` 推进；每个 element 的目标依次为
`v15` 至 `v22`，`vl=vstart+1`，没有 field 遗漏、目标寄存器错位或 vstart 跳变。
AddrGen 的 index/最终地址探针也与 Spike commit log 中的访存地址序列一致。

### 65.2 当前版本闭环

当前 RTL 在同一动态位置向 `v17` element 3 写入 `0x3fe00002`，与 Spike 一致；旧首错
已被第 60 节等后续 indexed/store 布局修复顺带消除，不需要再修改 segment sequencer
或 AddrGen。使用当前无临时功能修改的最终 simv 重放完整 seed 11 后，程序正常退出：
8675 个架构向量请求和 14607 个后端 uop 均完整收发，scalar commit 比较为无差异前缀，
逐向量 writeback 比较为 PASS，`first_mismatch` 为空。复核证据位于
`verification/out/probe-nightly-seed11-idxaddr-final_20260811/`。该结果同时说明旧 campaign
的失败状态不能直接代表当前 RTL，剩余 case 必须在最终修复集合上重新重放后再分类。

## 66. Nightly seed 48 的源组重叠回归

标量 DivSqrt 首错消除后的旧 seed 48 artifact 在 e64,m2、VL=32 的 masked
`vrem.vv v4,v8,v30,v0.t` 出现向量差异，随后程序立即执行 `vmv1r.v v4,v6` 覆盖同一
目的寄存器。该序列属于目的组可能在长延迟运算完成前被后继 whole-register 操作复用的
源生命期/布局重叠场景，也是当前 source snapshot 与 wait-complete 保护的直接回归点。

使用包含全部当前修复且无临时定位探针的最终 simv 重放原 ELF，seed 48 在 523.02 秒
正常退出并得到严格 PASS；scalar commit、请求生命周期和逐向量 writeback 均无差异，
旧 `vrem.vv` 首错不再出现。证据目录为
`verification/out/replay-nightly-seed48-current-final_20260811/`。因此该项无需新增 RTL
修改，其失败状态同样来自早于 source snapshot/overlap 修复的旧 campaign artifact。

## 67. 空 lane 有序归约完成脉冲误退后继 selector

### 67.1 Seed 32 的确定性死锁

nightly seed 32 在 e32,m4、VL=2 的 `vfwredosum.vs v0,v20,v18,v0.t` 后紧接
`vfredmin.vs v23,v28,v28`，随后又接受了 masked `vfncvt.f.x.w v24,v8,v0.t`。
原 RTL 在约 95k 周期后停止后端推进，最终保留两个未完成请求：`vfredmin` 的 vid 1
和 `vfncvt` 的 vid 0。主 sequencer 已正常接收请求，中间的 `vmsbf.m` 也已完成，
因此停顿不在前端或 CVXIF，而在 lane 内部归约共享通路。

`ARA_DEBUG_REDUCTION` 的逐周期证据显示，前一条 ordered widening reduction 在 lane2/3
的本地 VL 为零。第 64 节的修复正确地令这两个 lane 不向 SLDU/ADDRGEN selector FIFO
压入 `FPU_RED_SEL`；但是 VMFPU 在本地归约提交时仍无条件产生 `fpu_red_complete`。
在本例中，该延迟完成脉冲到达前，后一条 `vfredmin` 已向 lane2/3 压入自己的
`FPU_RED_SEL`。旧完成脉冲因而错误弹出了后继 selector。之后 lane2/3 的 `vfredmin`
归约结果持续保持 `valid=1, ready=0`，而 lane0/1 已经正常发送结果；SLDU 等待四 lane
对齐，形成永久死锁。

### 67.2 修复原则

`hardware/src/lane/vmfpu.sv` 现在仅在当前归约没有设置
`skip_sldu_operand` 时产生 `fpu_red_complete`。该条件与
`hardware/src/lane/lane.sv` 的 selector 入队条件严格对称：预留过 selector 的归约
才允许产生用于弹出 selector 的完成脉冲。空 lane 的 VMFPU 请求仍正常完成并向主
sequencer 归还 vid，不改变 ordered reduction 的全局完成规则；修复只阻止一个没有
对应 FIFO 表项的局部完成事件误伤后继指令。

`vreduction_overlap_edges.c` 新增 VL=2 的 `vfwredosum` 紧跟 `vfredmin` 场景，同时检查
两条归约的 FP64/FP32 数值。该测试在修复后通过。完整 `rvv-reductions` 专项的 18 项
测试全部通过，覆盖整数、浮点、ordered/unordered、widening 及 LMUL/重叠边界。

原 nightly seed 32 使用新 RTL 在 220.99 秒正常退出：13194 条退休记录、6229 个架构
向量请求和 9598 个后端 uop 均完整闭合，逐向量状态比较为 PASS，无首错。直接受空
lane ordered reduction 逻辑影响的 nightly seed 6 也在 175.89 秒完成严格重放并得到
PASS。证据分别位于
`verification/out/replay-nightly-seed32-selector-fix_20260811/`、
`verification/out/replay-nightly-seed6-selector-fix_20260811/` 和
`verification/out/regress-reduction-selector-fix_20260811/`。

## 68. Indexed store 双 EEW 源重叠的保留编码

### 68.1 Seed 16 的旧首错

nightly seed 16 的旧逐向量首错出现在 PC `0x80003960` 的
`vluxei64.v v16,(tp),v0`。该 load 从地址 `0x8000eff8` 读取时，RTL 内存为 0，Spike
期望 `0x9a0`。向前追踪写者后，差异来自 PC `0x80003876` 的
`vsoxei32.v v16,(sp),v20`；当时配置为 e64,m8、VL=93，store data 读取
`v16-v23`，32-bit index 以 EMUL=4 读取 `v20-v23`。因此同一组物理寄存器
`v20-v23` 同时作为 64-bit 数据源和 32-bit index 源读取。

RVV 1.0 将一条指令以两个或更多不同 EEW 读取同一物理向量寄存器的情形定义为保留
编码。Spike 对该编码继续执行并产生具体内存结果，不会使该结果成为处理器必须实现的
架构行为。Ara 在该位置与 Spike 不同因而不能归类为 VSTU 功能缺陷，也不应通过修改
RTL 去拟合参考模型对保留编码的选择。

### 68.2 生成后处理原则

`verification/ara_verify/random_rvv.py` 新增 indexed-store 源组检查。后处理器跟踪可
静态确定的 `vsetvli/vsetivli/vsetvl`，根据 SEW、LMUL、index EEW 和 segment field
数分别计算 data group 与 index group；只有两组发生物理寄存器重叠且 EEW 不同时才
识别为保留编码。该条无架构语义可保持的 store 被替换为 `nop`，并在
`reserved_indexed_store_overlap_rewrites` 中独立计数。

这里不把 index 操作数任意换成另一个现有寄存器组，因为未受约束的新 index 值可能
生成测试内存范围外的地址；也不在原地插入 whole-register move，因为临时目的组可能
覆盖仍存活的随机向量状态。合法 indexed store 的 mixed-layout、ordered、segment、
restart 和非零 `vstart` 行为继续由 `vstore_signature`、`vindexed_vstart_edges` 与
`vsegment_emul_edges` 等定向测试覆盖。新增 Python 单元测试同时覆盖普通 indexed
store、masked overlap 和 indexed segment store，`test_random_rvv.py` 共 19 项通过。

### 68.3 同源程序精确重放

为避免把重新生成的同 seed 程序误作证据，验证流程复制了原
`ara_dsa_rvv1_nightly_15.S`，只将上述一条保留 store 替换为 `nop`，再由 Spike 与
当前 RTL 执行同一个新 ELF。精确重放在 650.19 秒后正常退出并得到 PASS：14168 条
RTL scalar commit 与 Spike 前缀一致，6111 个架构向量请求全部闭合，7387 个后端
uop 的分配与完成数相等，5679 个有目的向量请求无首错。逐向量比较包含 48223 个确定
byte，另有 2520853 个由 agnostic 数据传播而不可严格观测的 byte 被显式跳过；因此
该结果证明旧首错由保留激励触发，不把不可观测 byte 误宣称为逐位一致。证据目录为
`verification/out/old-seed16-reserved-store-removed-replay_20260812/`。

独立重新生成的 nightly seed 16 也在 484.47 秒通过，包含 4098 个有目的向量请求和
69164 个确定比较 byte；但该新程序没有生成同一条保留编码，只作为生成器当前路径可
运行的辅助证据，不替代上述旧程序精确重放。

## 69. Vector-to-scalar 不可观测值的比较边界

nightly seed 5 的旧 scalar 首错位于 PC `0x80002dfe` 的
`vmv.x.s ra,v22`。`v22` 来自包含 agnostic 输入的 mask 结果，Spike 与 RTL 对 element
0 形成不同但均合法的值；完整逐向量比较没有确定 byte 差异。比较器已有 element-0
knownness 判断，却把该判断错误地限制在“当前请求存在 VRF write activity”时执行。
`vmv.x.s/vfmv.f.s` 的目的在 GPR/FPR，本来没有 VRF write activity，因此真实动态
vector-to-scalar 请求从未进入该判断。

移除错误门控后，旧首错消失，但比较器随后在由未知 GPR 派生的普通标量指令上再次
报差异。继续逐值比较这种状态并不严格：一旦 vector-to-scalar 返回读取了架构不确定
bit，Spike 与 RTL 的 GPR/FPR 状态已允许合法分叉，后续算术、分支和地址均可能受其
影响。当前规则因此在不可观测返回处仍严格检查 PC、指令编码和写寄存器集合；若程序
后面还有提交，则以带停止原因的 `PREFIX` 结束 scalar bit-exact 比较，而不是使用
Spike 值伪造 RTL 状态或无限扩展不完整的标量 taint 解码。

使用现有完整 artifact 离线重算后，scalar 比较在第 814 条提交、PC `0x80000bbe` 的
`vmv.x.s s3,v15` 后形成明确 PREFIX；完整后端 trace 仍为 VALID，15327 个架构向量
请求和 36320 个后端 uop 全部闭合。逐向量比较覆盖 14375 个有目的请求、66947 个确定
byte，`first_mismatch` 为空；3787869 个 agnostic 派生 byte 被显式跳过。该 case 最终
归类为 PASS，证据位于
`verification/out/postprocess-nightly-seed5-current-knownness_20260812/`。新增测试分别
覆盖无 VRF activity 的 scalar return 检测和不可观测返回后的 PREFIX 截止语义。

## 70. Nightly seeds 18/38 的最终重放与随机分项收敛

原 nightly seed 18 在旧构建上停在 e8,m4 的
`vsoxseg2ei16.v v4,(s2),v8`。静态合法性审计发现该程序共有三条 indexed store 以
不同 EEW 读取重叠物理源组，均属于第 68 节定义的 RVV 保留编码。原 seed 38 的旧
timeout 位于合法的 masked `vluxei16.v v16,(s5),v20,v0.t`、e32,m8、非零
`vstart=4`；其程序更早位置另含一条同类保留 indexed store。验证流程复制两份原始
汇编，只把总计四条保留 store 替换为 `nop`，再由 Spike 与当前 RTL 对各自同一个新
ELF 进行严格重放。

seed 18 在 835.88 秒后正常退出：4823 个架构向量请求全部收发，23652 个后端 uop
分配与完成数相等；逐向量比较覆盖 4465 个有目的请求和 76151 个确定 byte，
`first_mismatch`、未完成请求和未退休请求均为空。seed 38 在 459.84 秒后正常退出：
4409 个架构向量请求全部收发，5339 个后端 uop 分配与完成数相等；逐向量比较覆盖
4091 个有目的请求和 54602 个确定 byte，同样无首错和生命周期残留。两者的 scalar
比较均在读取不可观测向量 element 0 的 vector-to-scalar 返回处按第 69 节规则形成
有解释的 PREFIX，不存在 scalar mismatch。证据目录为
`verification/out/replay-old-nightly-seeds18-38-legalized_20260812/`。

至此，原 142 个随机 case 的所有历史非通过项都已有当前修复集合上的通过证据；其中
保留编码 case 使用合法化后的同源程序，比较器假阳性 case 使用当前严格后处理规则。
该结论是跨多次定向重放形成的分项收敛，不等价于 142 项在同一次源码快照和同一个
`simv` 下全部通过。全局完成仍要求第 57 节定义的 204 个 directed RVV、50 个应用和
142 个随机程序在统一 campaign 中产生 396 个唯一结果，并通过动态、覆盖和源码快照
门禁。

## 71. 统一回归的 VCS 随机生成器复用

完整 campaign 包含 12 个 riscv-dv profile。旧调度方式为每个 profile 独立执行 VCS
编译，即使这些 profile 使用相同的 UVM generator 源码和编译参数，也会重复生成同一
个 `vcs_simv`。在当前机器上，第一次生成器编译约需 47 分钟；重复 12 次既不增加
激励覆盖，也使统一回归的大部分时间消耗在验证工具自身的重复构建上。因此第一次统一
campaign 在首个生成器构建完成后主动停止，没有把不完整结果计入通过数。

`verification/verify.py run-rvv` 和 `verification/run_full_campaign.py` 现支持
`--generator-simv`。每个随机 profile 仍独立执行 riscv-dv 的 simulation-only 生成、
确定性后处理、GCC 编译、Spike 和 Ara 比较；复用的只有编译结果，不复用 seed、汇编、
ELF 或比较结果。VCS 可执行文件运行时还依赖同目录的 `vcs_simv.daidir`。初版实现只
链接 `vcs_simv`，真实集成测试立即以缺少
`vcselab_master_hsim_elabout.db` 退出；当前实现将可执行文件与运行时数据库作为一套
构件共同校验和链接，并拒绝缺失或目标冲突，避免把环境失败误记为 RTL 失败。

共享构件的 SHA-256 为
`2be089da404e04384c649b4e5a0722ccfa69f8625ff006261b2d1a52ef5af420`。真实
`ara_dsa_rvv1_smoke` seed 71 运行确认命令使用 `--so`、不存在生成器编译进程，随后
完成 GCC、Spike、Ara 和逐向量比较并得到 PASS：标量提交匹配 289 条，向量比较无
差异。较大的 `ara_dsa_rvv1_arithmetic` seed 72 也在 53.50 秒内通过，1114 个架构
向量请求和 1612 个后端 uop 全部闭合；逐向量比较覆盖 967 个有目的请求和 9612 个
确定 byte，无首错、未完成请求或未退休请求。两项证据位于
`verification/out/shared-generator-integration-v2_20260812/`。验证框架全部 127 项
Python 单元测试通过，其中新增测试覆盖运行时数据库链接、缺失和冲突三种情况。统一
396 项 campaign 尚未结束，因此本节只证明生成器复用路径正确，不把它扩张为全局
回归通过结论。
