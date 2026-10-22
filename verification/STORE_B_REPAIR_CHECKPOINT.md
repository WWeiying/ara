# Store B-response repair checkpoint

The tested candidate has been integrated into the signoff worktree on
2026-09-26; this is not a main-branch merge or a final signoff claim.
The acceptance gate is both precise exceptions and no measured performance
regression on configuration-matched representative programs. Do not change
AXI delays, the benchmark ELF, or completion semantics to pass the gate.

## Frozen performance evidence

AXPY ELF SHA-256:
`95d17384bb80addb04586b1884dbd0c8084b1cf26134d80c7c5ff6b0247fea3d`.
All measurements use QBS + AKV-v2, 2 MiB simulated L2, real CVA6 and the same
AXI-delay configuration. `total_cycles`, not the separate hardware ROI count,
is the comparison metric. AXPY itself is not a numerical self-check.

| Candidate | total_cycles | Functional evidence | Performance gate |
| --- | ---: | --- | --- |
| Original early response | 2786 | Performance baseline; B faults are not precise | Reference only |
| Precise B completion | 3193 | Multi-burst fault test passes | FAIL |
| One read buffer | 3223 | Four directed DUT cases pass, including numerical/fault checks | FAIL |
| One read buffer + VL preview | 3195 | AXPY protocol PASS; enhanced directed test exposed FIFO-full bug | FAIL |
| Two read buffers + VL preview + full-flag correction | 3185 | Four enhanced directed DUT cases PASS | FAIL |
| Two read buffers + two-hint FIFO + VL preview + full-flag correction | 2933 | Four enhanced directed DUT cases PASS | FAIL (+5.28%) |
| Image04: above + two-slot empty request bypass | 2810 | AXPY completion/protocol PASS; separate numeric, fault and FP checks required | FAIL (+0.86%) |

The one-entry VL-preview measurement is in
`out/store-vl-preview-20260926-03/`. Its source manifest and pre-run source
check are retained. Subsequent working-source edits do not retroactively
change this image or its results.

## Measured dependency chain

In the preview run's bounded cycle trace:

| Event | Cycle |
| --- | ---: |
| Next vsetvli preview, VL=32 | 471 |
| First next-iteration load at CVA6 issue | 472 |
| Second next-iteration load at CVA6 issue | 474 |
| First speculative read AR | 480 |
| Older store WLAST | 526 |
| Older store architectural response | 533 |
| Second ordinary load AR | 557 |

The second address becomes available before store completion, but the single
buffer holds the first address and cannot prepare the second. This is the
specific hypothesis for a two-entry data buffer, not evidence that such a
buffer has already recovered performance.

## Correctness constraints

- Store completion still waits for all owned B responses; errors preserve
  the faulting instruction, address and restart element.
- VL preview changes only operand forwarding. It must not update retirement
  validity, vector configuration, or architectural registers early.
- Flush, transaction-ID reuse and real writeback invalidate a preview.
- Read preparation is restricted to permitted cacheable/idempotent physical
  ranges, without translation or active PMP rules, and disjoint from the
  known store range. Unsupported cases use the ordinary path.
- Only an exact subsequent architectural AR can consume buffered data.
  Speculative errors are discarded and retried through the normal request.
- Held AXI requests/responses must remain stable; cancellation must drain
  already-issued transactions. QBS/AKV handoff must wait for private traffic.

## Focused tests

The original one-entry buffer passed 19 protocol scenarios, 686 cycles, in
`out/store-b-lookahead-unit-20260926-01/`. These are module-level tests, not
19 full processor programs. The forwarding arithmetic/decode test passed
172,032 combinations across four parameter configurations; this does not
test scoreboard retirement or flushing.

`vstore_lookahead.c` now checks both vector and scalar state in a store-error
handler. The younger vset destination and dependent scalar destination must
retain their old architectural values at the trap; after return, they must
compute the correct new values. A separate trace records actual forwarding
consumption, not just preview-slot occupancy.

The first enhanced DUT run stopped at `cva6_fifo_v3.full_write` before the
fault portion. With candidate queue depth 4, the two-bit `usage_o` wraps to
zero at full capacity. The previous `usage < depth-1` test reopened issue.
The candidate now uses `!full && usage < depth-1`, preserving the reserved
slot for the pending issue-stage instruction. The enhanced DUT regression
subsequently passed; the failed run is retained at
`out/store-preview-fault-numeric-20260926-01/`.

The actual FIFO credit test passed depth 3 (241 cycles) and depth 4 (258
cycles), including continuous issue, pop stalls, simultaneous push/pop, and
flush recovery. The two-entry data buffer passed 43 cases in 1,944 cycles.
These test counts are separate from full-processor program counts.

`out/store-pair-regress-20260926-01/` contains four passing processor tests:
numeric, multi-burst fault, QBS/AKV handoff, and masked-store edges. In numeric,
the dependent SUB at PC `0x80000ff8` consumed preview data at wall cycle
80289, before the first store exception response (contract monitor cycle
80352). The second iteration repeats this distinction. The handler verified
old t2/t3 and v8 values, while resumed execution verified the new VL/result.
Do not subtract cycles across the wall and contract monitor domains as a
precise latency; their ordering here is separated by dozens of cycles.

Performance remains unclosed. In the two-entry run the upstream one-address
hint register overwrote the first hint while the new store's VLSU window was
still inactive. The working candidate now retains two input hints in a FIFO.
Per-bank invalidation/fill/replay probes were added to distinguish further
loss from AW invalidation, normal-demand fallback, or late fill. The new run
is `out/store-pair-queued-20260926-01/`; only a completed, source-checked run
may be used as evidence. A compile interrupted by a source-manifest mismatch
was not simulated; its logs and manifest are archived inside that directory.

The resumed, source-checked image completed AXPY with 2933 total cycles and
zero protocol errors. `out/store-queued-regress-20260926-02/` reran all four
directed processor cases on this image: numeric, fault, handoff and masked
all PASS, with zero protocol errors. Numeric exercised two exceptions and
the multi-burst fault case exercised one. This closes the previously missing
directed regression for the two-hint FIFO, not the performance acceptance gate.
The first observed lost ready entry was cancelled by external invalidation
at trace time 5610000 with AWVALID=0; it must not be attributed to an AW
overlap. Correct cancellation must not be relaxed solely to recover cycles.

## FP16/INT8 investigation and candidate

The B-only images above do not include FP16/INT8 changes. Combined images
starting with `out/store-fp16-image-20260926-01/` also repair conversions.
The independent analysis identified three frozen control-cross failures:

| Seed | First differing PC | Instruction | Configuration |
| --- | --- | --- | --- |
| 202 | 0x80000890 | vfncvt.rtz.xu.f.w v0,v16 | e8,m1,VL82 |
| 305 | 0x80000bf0 | vfncvt.x.f.w v26,v0,v0.t | e8,m2,VL42 |
| 401 | 0x8000054e | vfncvt.x.f.w v1,v11 | e8,mf8,VL16 |

These are measured illegal-instruction divergences, not measured wrong
numeric results: the dispatcher rejects SEW8 despite FP16 source support.
Static inspection also found INT8 enable/packing incorrectly coupled to FP8
in VMFPU and both fpnew integer-format helper functions. Relaxing decode alone
would expose that unsupported downstream path. The later fix must preserve
the no-FP8 configuration and route FP16-to-INT8 with FP16 input/output-format
selection for fpnew readiness and INT8 integer-result selection, then verify
rounding, saturation, flags, masks, vstart and both packing halves.

## Next gates

1. Unit-test queue credit and the two-entry buffer before integration.
2. Run the frozen AXPY and inspect actual VL forwarding, both read addresses,
   exact hits, store response, and total cycles.
3. Pass numerical overlap/mask/tail, precise multi-burst faults, and QBS/AKV
   handoff on that same image; then run representative independent RVV checks.
4. Only after correctness and performance gates pass, address FP16-to-INT8
narrowing in a separate patch. Its measured failures are illegal-instruction
   divergence; downstream integer-format and packing support also needs repair.

Do not merge this candidate on the strength of the arithmetic unit test or
AXPY's successful exit alone.

## 2026-09-26 correctness-first update

The latest user request prioritizes passing the known correctness cases.
Performance remains a separate, unmet integration gate, not waived by this
change in work order. No candidate has been merged into the main worktree.

### Conversion input/output widths

The first combined image enables only FP16-to-INT8 narrowing in the decoder,
the VMFPU format routing/byte assembly and fpnew integer-format helpers.
FP8 stays disabled. The helpers retain their original equal-width rules and
add only the FP16/INT8 pair, rather than all smaller integer formats.
Frozen seeds 401 and 202 PASS scalar and vector comparison against Spike
(3901 and 6534 matched instructions respectively). Matched AXPY remains
2933 cycles, identical to the preceding B-only candidate.

Seed 305 advances past `vfncvt.x.f.w` but its next `vfwcvt.f.x.v` at
`0x80000bf4` still traps. This is the symmetric INT8-to-FP16 conversion gap.
The next candidate enables precisely that conversion and corrects the
operand queue's byte gathering: EW8 physical order is `0,4,2,6,1,5,3,7`,
while EW16 physical order is `0,2,1,3`. Each selected half therefore takes
source bit offsets `0,16,32,48`, plus `8*select`, not a duplicated source byte.

The reported masked `vor.vx` mismatch at lower PC `0x800008c8` is dynamically
AFTER the trapped producer. Its 17 changed bytes exactly match mask-enabled
elements and old v8 data; all 25 inactive plus 86 tail bytes in the examined
destination register remain unchanged. Do not label this as a separate mask
bug or confuse numerical PC order with dynamic instruction order.

### Integer conversion boundary flags

`out/fp16-int8-cast-root-20260926-01/` measured 12 failures among 32 short
cast-core cases: valid negative minima reported NV, and negative-to-unsigned
rounding could wrap its temporary result to zero and omit NV.

The fix in `fpnew_cast_multi.sv`:

1. Allows signed-negative exponent N-1 through the rounding path.
2. At that boundary, accepts only a rounded magnitude equal to 2^(N-1).
3. Allows a negative unsigned rounded zero only for input magnitudes below 1.
4. Reuses the existing sign-extended minimum data encoding with normal
   exact/inexact status when valid; other saturation cases retain NV.

No pipeline stage, valid/ready handshake or division/arithmetic operation was
changed. The fixed unit at `out/fp16-int8-cast-fixed-20260926-02/` PASSes all
36 cases, including INT16/INT32/INT64 full-width sign extension, negative zero
and RMM boundaries. The earlier fixed-01 attempt stopped at time zero because
an unguarded combinational `int_width(X)` call preceded reset; it is retained,
not counted as a numerical run. The guard now matches the existing cast path.

### Final-image test plan

`run_store_fp16_regression.sh IMAGE_DIR NEW_OUTPUT_DIR SHARD_DIR` freezes ELF
inputs, verifies shard provenance, runs the conversion smoke before the full
matrix, then schedules at most five VCS workers. A failed/incomplete task never
counts as PASS. It includes the original three strict random replays, four
store tests, adjacent conversion/reduction/store-error tests, and eight
conversion shards. Shards partition all 464 cases without removing checks;
see `VFNCVT_INT8_DIRECTED.md` and the shard manifest. Golden PASS and cast-unit
PASS are not substitutes for the pending processor-level results.

## 2026-09-26 processor CSR ordering investigation

The extended cast-core matrix passed 86/86 checks in
`out/fp16-int8-cast-extra-boundaries-20260926-01/`. This includes 64-bit
signed/unsigned boundaries; it does not establish processor CSR ordering.

Combined image `store-fp16-image-20260926-02` compiled, passed its AXPY/UVM
gate and retained 2933 cycles. Its narrowing smoke then found a distinct
processor-level failure: result bytes match, but an immediately following
`csrr fflags` reads zero instead of NV|NX (0x11). The batch
`out/store-fp16-regress-20260926-02/` was stopped at this failed smoke gate;
none of its downstream full-matrix tasks is a PASS or a completed regression.

The first case gives a cycle-level discriminator:

| Event | Cycle | Evidence |
| --- | ---: | --- |
| Conversion allocated | 3637 | vector_trace.csv, instruction 4a889c57 |
| Conversion scalar acknowledgement retired | 3638 | trace_hart_0.log, PC 80000e20 |
| FFLAGS read retires with zero | 3639 | trace_hart_0.log, PC 80000e24 |
| Conversion destination writes | 3646, 3648, 3649 | vector_trace.csv |
| Conversion backend completion | 3650 | vector_trace.csv |

Therefore scalar acknowledgement is not vector execution completion. The
candidate adds an accelerator busy sideband and gates only FFLAGS/FRM/FCSR
CSR accesses until older queue entries, the request spill, dispatcher work,
backend execution, and the final asynchronous flag update have drained.
The issue-stage CSR address comes from `issue_instr_i.result[11:0]`, not the
EX-stage `csr_addr_i`. Ordinary RVV request issue is not serialized by this
new CSR-only gate. Already-excepting instructions bypass this gate.

`FP_CSR_TRACE` provides a bounded cycle trace of queue/spill/backend state,
CSR issue handshake, and flag updates; an assertion rejects an actual floating
CSR issue while the synchronization condition remains active. The software
test retains its immediate CSR reads: adding a fence/vset to hide the race is
not an acceptable fix.

Image03 compiled with the declaration-order correction, with all 457 source
manifest inputs unchanged. Its AXPY gate PASSes at 2933 cycles. The first
processor case now shows CSR wait/fire=1/0 at cycles 3636--3655; flags-valid
updates at 3650--3654 carry 01,11,11,11,01. CSR issue is released at 3656,
and the architectural read retires at 3659 with 0x11. This is a focused
ordering-fix result, not a claim that all matrix cases have completed.
See `out/fp-csr-image03-firstcase-review-20260926-01.md`.

The new batch is `out/store-fp16-regress-20260926-03/`; it uses image03,
preserves the same frozen shard inputs, and limits VCS concurrency to five.
Final correctness acceptance requires its complete result set and the
supplementary CSR-ordering/adjacent-FP checks, not this first-case trace alone.

Image03 measured progress:

| Test | Result | Scope |
| --- | --- | --- |
| Narrowing smoke | PASS | 40 cases; 1988 bytes, 1732 active elements, 120 CSR checks |
| Seed 202 | PASS | 6534 matched scalar instructions and vector comparison PASS |
| Seed 305 | PASS | 5810 matched scalar instructions and vector comparison PASS |
| Seed 401 | PASS | 3901 matched scalar instructions and vector comparison PASS |
| Store fault, masked, QBS/AKV handoff | PASS | Final image03 protocol and numerical checks |

The separate strengthened `vstore_axi_error` program reports PASSED for its
13 checks and produces three expected exceptions, seven matched AW/B bursts,
and zero protocol errors. Its original UVM report is FAIL solely because the
generic runner required an AXI read, although this program initializes data
with `vmv` and performs only vector stores. Preserve that report. Recheck the
same log with AXI-write requirements and full protocol checking, but without
an AXI-read existence requirement. The runner now has an explicit per-case
read-traffic expectation; this change does not retroactively alter an already
running batch's recorded status. A separate audit must distinguish this
checker-only rejection from a DUT failure and verify the frozen artifacts.

## 2026-09-26: 完整矩阵结果与 DIV 异常标志根因

Image03 的 21 项回归已结束。三个严格随机种子、464 个窄化矩阵用例、
40 个窄化 smoke 用例、24 个 INT8 扩宽用例，以及 store fault/masked/
QBS-AKV handoff 均通过。纯 store 用例的原始 checker FAIL 不覆盖，
独立复核保存在 `store-fp16-regress-20260926-03/accepted_completion.json`。
该复核去掉不适用的“必须存在读事务”要求，仍检查写事务、预期异常和协议。
checker 快照中的两处 runner 策略变化单独记录，不能解释为运行前已封存。

相邻浮点测试暴露了另一个问题：`vec_fp_csr_order` 的 FP32 DIV 用例得到
`fflags=0x18`，应为 `0x08`；`vfp_vstart_edges` 失败的是 FP64 DIV 第 5 项，
不是窄化第 9 项。第 9 项实际通过，不能因此修改 CONV 路径。

原因分为两部分：

1. 多格式 DIV 为保持 SIMD 完成同步，会启动不属于当前格式的子单元。
   FP32/FP64 的无效子单元计算占位的 0/0；它们的 NV 被错误汇入最终标志。
   修复按返回的格式筛选状态，不改变启动、完成同步或 ready/valid。
2. 输入 mask 按最细元素宽度排列。当前 FP16/FP32/FP64 配置中，FP32
   两个元素应读取 mask[0] 和 mask[2]，不是 mask[0] 和 mask[1]。
   修复只在 DIV/SQRT 内按格式选择常量步长，不改变 CONV 的 mask 约定。

证据来自实际 `fpnew_opgroup_multifmt_slice` 的 VCS 单元测试，而不是替代模型：
原始 8 项有 4 项失败；仅修格式筛选后 8 项通过且延迟保持 6 周期。
增加物理 mask 的区分用例后，10 项中有 3 项失败，证实仍需 mask 映射修复。
这些失败记录分别保留于 `fp-div-flags-root-20260926-02/` 和
`fp-div-flags-mask-root-20260926-01/`，不覆盖旧证据。

性能门槛尚未关闭：Image03 AXPY 为 2933 cycles，旧基线为 2786 cycles。
候选将请求寄存器改为保留两槽容量的空队列直通缓冲；单元测试已通过
32 个场景、2892 次检查、167 个有序事务。处理器级周期收益待 Image04
实测，不能把单元通过表述成无性能回退，也不能提前合入主工作树。

Image04 已完成编译和 AXPY 整机门槛：程序完成及 UVM 协议检查 PASS，
`total_cycles=2810`。相较 Image03 减少 123 周期；相较旧基线仍多
24 周期（0.86%），性能验收仍未关闭。此结果只覆盖同一二进制、同一
AXI 延迟配置的 AXPY，不等价于所有程序性能均无变化。

DIV 的格式筛选与物理 mask 映射组合修复后，单元 10/10 PASS，
各事务仍为 6 周期；证据位于 `fp-div-flags-mask-fixed-20260926-01/`。
Image04 的 CSR、vstart 和 store fault/handoff/masked 五项复测均 PASS。
CSR 程序完成 21 个场景、762 次检查及 2 个预期异常；vstart 程序的
10 个分项均通过。AXPY 自身不是数值自检，不能用其结束状态替代定向
测试的数值和异常检查。

`store-fp16-regress-20260926-04/` 运行新的 21 项完整回归，最多五路 VCS。
`store-fp16-div-followup-20260926-04/` 在该批次全部通过后自动执行
52-case/1612-check 的 DIV 掩码程序；输入先由 Spike 独立校验，覆盖
246 个活动元素、47 个 prefix、720 个 masked 和 235 个 tail 元素。
后续任务以 `status.txt` 为准，不把 Spike PASS 当成 RTL PASS。

### Image04 的剩余性能差距

同一计时窗口和 vector completion trace 的完整分解如下：

| 区间 | 旧基线 | Image04 | 增量周期 |
| --- | ---: | ---: | ---: |
| 计时开始到 store1 done | 140 | 137 | -3 |
| store1 到 store2 done | 85 | 97 | +12 |
| store2 到 store31 done | 29 x 85 | 29 x 85 | 0 |
| store31 到 store32 done | 85 | 100 | +15 |
| 最后 done 到计时结束 | 11 | 11 | 0 |
| 合计 | 2786 | 2810 | +24 |

第二轮的 Y 地址 `0x800050c0` 曾经预取完成，但被 `inv_ext` 清除，
之后多出一次普通 AR 和 8 个 R beat；现有探针尚未单独给出该次外部
失效的上游原因，不能直接删除失效逻辑。末轮 X=`0x80001fb0` 和
Y=`0x80005fc0` 的 128B 请求跨越 4 KiB，当前机制拒绝这种预取并走
正常分段访问。稳态吞吐恢复，不代表总执行周期已经不退化。

对照证据：
`store-b-cycle-probe-ab-20260925-02/baseline/axpy/work/vector_trace.csv` 与
`store-fp16-image-20260926-04/work/vector_trace.csv`。计时起点均为 393，
终点分别为 3179 和 3203。若继续优化，必须先区分失效来源，并为跨页
预取补足分段请求、异常吞并、回放和顺序验证，不能以放松现有保护换取周期。

## 2026-09-26 合回验证集成工作树

- 目标：`/home/wangwy/openproject/ara_dsa_signoff_integration`。
- 来源：`/home/wangwy/openproject/ara_dsa_store_fault_fix_20260925`。
- 来源 Image04：21/21 回归通过，独立 `accepted_completion.json` 审核通过；
  后续 DIV 52 个场景、1612 次检查也已在 VCS 上通过。
- 保留目标分支新增的非法寄存器组/掩码重叠检查、随机 profile、
  `--spike-isa` 选择、Verilator tohost 检测及已有测试注册。
- CVA6/FPnew 使用独立副本，并重新生成依赖补丁及 SHA-256；不修改
  `ara_dsa_verification` 的共享依赖，也不删除旧依赖软链接的备份。
- 合并前文件和补丁备份：`verification/out/merge-store-fp16-20260926-01/`。
- 原始长回归和逐周期证据留在来源工作树的 `verification/out/`，没有
  冒充为合并后版本的新结果。合并后编译与短回归独立执行。
- AXPY 总周期比旧基线多 24 周期（0.86%）的性能限制仍保留；本次合回
  是用户明确要求的集成，不代表此前的无性能回退门槛已经满足。

合并后验证完成：VCS 重新编译成功，457 个源文件清单一致；58 项验证
脚本单元测试通过。`out/merged-store-fp16-smoke-20260926-01/` 的 7 项
整机测试全部 PASS：AXPY（2810 cycles）、CSR 顺序（21 场景/762 检查）、
DIV mask（52 场景/1612 检查）、增强 store fault、多 burst store fault、
掩码目的寄存器非法重叠、非法寄存器组。后两项专门验证保留的目标工作树
检查没有被本次合并覆盖。未重跑完整 21 项矩阵，不把来源结果当作合并后
全量回归结果。
