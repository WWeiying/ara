# Resident PV：阻塞式 SoC 接入前设计审核

日期：2026-11-08。**本文是设计审核和后续验收条件，不是实现、通过证据或性能结论。**
本次审核只新增本文；不修改 production RTL/SDK、旧 sealed 文档或既有报告。
边界：四 lanes、VLEN1024；复用现有 VMFPU、StA 队列、context 读口和最终写回口，
不改总线/DDR、lane 数量、MAC 数量。仍需 lane wrapper 的所有权与握手控制接线。

## 1. 写入前检查与证据边界

- 创建前确认目标不存在。检查本树及 signoff 的 `verification/out`，并检查所见相关
  worker 构建目录和 FPGA finalize 目录，共解析 811 份 `source-pins.json`，无本文文件名引用。
  旧文档存在继承 pin；不改它们，也不修改任何 worker 的输入清单。
- 源码定位基于本树 HEAD `e47681fb359411003763720bd67fb3202eb933b8` 及当时工作区；
  行号仅供定位。未提交的 `software/akv/src/akv_v2_attention_rvv.S` 不是已交付 SDK 依据。
- [VMFPU gate](RESULTS.md)、[context/FPU gate](../pv_context_fp/RESULTS.md)、
  [import gate](../pv_import/RESULTS.md) 的通过范围各自独立，不能合并宣称 SoC 已通过。
  import gate 明确尚缺“源流排空后才允许 commit”的父级条件。
- [旧 SOC 文档](SOC_INTEGRATION.md) 第 72 行仍是 coefficients-first；本次提议采用
  [后续 import 审核](../pv_reader/VRF_IMPORT_REVIEW.md) 的 seeds-first/interleaved 布局。

## 2. 最小命令和几何

候选编码为 `opcode=0x5b, funct3=7, funct7=2`，保留 column/panel 的 `funct7=0/1`。
`rs1` 是标量控制：`[5:0]=T-1, [6]=H-1, [8:7]=Dcode`，更高位全零。
建议沿用现有 Dcode：0/1/2 对应 D64/D128/D96，3 非法；T 解码先扩为 7 位再加一。

| 对象 | 预留/检查 | 实际传输 |
| --- | --- | --- |
| vector rs2 源组 | 8 寄存器对齐，预留 8，不与整个目的组重叠 | EW16，384 元素，只读前 6 寄存器 |
| vector rd 目的组 | 4 寄存器对齐，预留全部 4 | 内部 VL256；仅 H 个 head 的前 D 元素有定义 |
| 每 lane 源流 | 96 halfwords，共 24 个 64-bit word | 0..7 为 seed0，8..15 为 seed1，16..23 为 interleaved coefficients |

seed 和目的每 head 固定跨 128 个 F16 元素。每 lane 的 active word 数为 D/16，
即 4/6/8；目的 word 地址为 `vaddr(vd)+8*head+word`，D96 不可紧凑拼接两个 head。
T 短、H1、取消时仍排空每 lane 的全部 24 words；inactive 数据不能进入 FP 运算或贡献 flags。

## 3. 提议：whole4-reg clobberable

**新 custom ABI 将 rd 起始的全部四寄存器定义为可破坏，只有 active 元素有定义。**
这不是普通 RVV 的 tail-undisturbed 或 tail-agnostic 规则，也不由调用者 `vta` 决定。
inactive 不保证保留、清零、全一或任何确定值；helper 不得读取、归约、参与下一轮运算或
作为有效结果存出这些元素。H1 时第二个 head 同样不定义。

- 最小实现可以只写 active words，不必清零或写满四寄存器，也不必先维护旧目的布局。
  成功 terminal、所有最终写回确认后，将整个目的组统一 retag 为 EW16。
  未写 inactive 字节换布局后的含义不保证，正是 clobberable 约定允许的范围。
- 失败/预提交取消必须没有 PV architectural destination write，也没有 PV 结果 retag，
  保持旧目的内容和 metadata。不是“写了以后报错”，也不能在 issue 时提前 retag。
- maintenance 的保值物理布局转换允许发生，并在转换真正完成时更新对应布局 tag；
  它不是 PV 结果写入。此方案无需目的 maintenance，源组转换又因禁止 alias 不涉及目的组。
  因而失败时目的原 metadata 仍须逐项不变，不能拿 maintenance 作为提前改目的 tag 的借口。
- 首次不可撤销的结果写接受后，禁止取消/可恢复失败；应继续到全部 final acknowledgment。
  全局 reset 不等同于一次承诺回滚的指令异常。

兼容性是**新增指令的有条件兼容**，不能改变旧 AKV 指令或 helper 的约定。
现有 custom 指令已有固定内部几何，但旧 `akv_destination_registers()` 对 D64 只返回 1，
对 D96/D128 返回 2，不能用于本指令的四寄存器 clobber 声明。
[rotation helper](../rotation/pv_rotation.S) 第 44、60 行使用 `VL=D` 运算/存出，说明
仅消费 active 元素符合该类用法；不代表它已经支持新指令。新 wrapper 必须声明整组 clobber，
保留 head 间距，重新准备源组，且不能依赖 H1 的第二组或 D96 的尾部仍保存旧值。
128 元素是寄存器布局 stride，不应直接当成应用内存 stride；存出仍按各 head 的实际布局。

验收只比较 active 输出的精确数值和目的组外的架构内容不变，不比较成功后的 inactive 值；
但要检查所有写地址都在目的组内、失败时整个目的组不变。源 maintenance 可改变物理字节与 tag，
不能改变源的架构内容。若将来要求保留 tail，必须另加目的旧布局维护、inactive 写屏蔽，
以及混合旧 EEW/部分寄存器写回的保值测试；不能只把 `vta` 改为零。

## 4. 实际路径上的必要修改

下列均为待实现项，不代表已接入。路径相对仓库根，行号为本次审核定位。

| 位置 | 最小动作及容易遗漏的原因 |
| --- | --- |
| `hardware/src/cva6_accel_first_pass_decoder.sv:192,215` | 先识别 PV 再落入 column；置 `is_rs1/is_load/is_vfp`，不读标量 rs2、不写标量 rd。复用 VS/FS-off 拒绝和 FP dirty 分类。 |
| `hardware/src/ara_dispatcher.sv:4928,5184` | 独立 PV 分支；检查 feature/FP16/四 lanes/VLEN1024、upper bits、Dcode、对齐/越界/整组 alias、架构 vstart=0、acc_cons_en；frm 仅允许 0..4，锁存到 fp_rm。context 还须 ready/V2、D 匹配、T 不超有效 token 数。 |
| `hardware/src/ara_dispatcher.sv:5348,5400,1147` | 复用 `vs2_reshuffle_vl/vstart`，PV 单独设 384/0、`lmul_vs2=LMUL8`，允许 PV 触发 source reshuffle。已有独立 base/limit/EEW 保存路径可维护前六寄存器，不能用目的 VL256 或完整八寄存器消费长度代替。 |
| `hardware/src/ara_dispatcher.sv:5409,5980,5030` | 明确 PV 不需要目的 preservation；排除 issue-time 目的 retag。按 QBS 模式在成功 terminal 后 retag 全四组。保留源 maintenance 自己的 tag 更新。 |
| `hardware/src/lane/lane_sequencer.sv:347,430,660` | 加 StA readiness 和 PV 源请求；用 vs2、EW16、无转换、scale_vl=0、VL=96/lane、vstart=0、hazard_vs2\|hazard_vd。QBACC 直接复用目的 lane VL，只会读 16 words，不是需要的 24。 |
| `hardware/src/ara_sequencer.sv:418,626,922` | source_register_count 对 PV 返回 8 作保守 reservation，目的为 4；实际请求仍只读 6。源和目的标记 wait_complete，最小版本一直保留到 terminal，不按私有 FMA 返回释放 hazard。 |
| `hardware/include/ara_pkg.sv:228`；`hardware/src/ara_sequencer.sv:321,381,891` | 新 op 追加在 VSXE 后保留旧枚举值；纳入 is_load/LoadUnit/target_vfus，但不能纳入 no_src_vrf。这样 WAIT 会记录各 lane 的真实源请求接受，不跳过它们。 |

保留 `vl=256/emul=LMUL4/vsew=EW16/vm=1` 作为目的内部几何，设置 ignore_zero_vl_check，
不改变架构 VL/VTYPE；明确沿用 custom 指令独立于调用者 VL/VTYPE 的规则。
现有 `scalar_op/vs2/old_eew_vs2/fp_rm` 足够承载控制与源描述；没有独立 `old_source_vl` 字段。
固定原型可按 op 推导 384/96，复用 dispatcher 已有的 source bound，不新增传播字段。
若以后支持变长源，才增加明确的 source-VL 字段并贯通 Ara/PE；old EEW 不是长度字段，
更不能用一个 base 的旧 EEW 代表混合布局的六个寄存器。

## 5. 一个阻塞事务的边界

1. **先排旧工作，再接新源。** 停止后续 native issue；等待旧 VID、maintenance、
   lane 请求寄存器、`vfu_operation_valid_o`、requester 的未返回读、operand/result/reduction/flags
   排空，再取得全部 lane VMFPU owner。VMFPU 本地 empty 不足以证明上游已空
   (`lane_sequencer.sv:1308`, `vmfpu.sv:1377`)。
2. **取得 owner 后允许 StA 工作。** 扩展 `vlsu.sv:731` 的 QBS/store 独占路由；
   不可等待“新源 StA 空”才启动其消费者。整个事务排斥 refill/release，私有 context payload
   的 ready 不得冒充 VRF 写 grant 或普通 load 完成；各 lane 独立记账防止重复接受。
3. **统一 commit barrier。** 源 24 words 全部排空成功、reader 完成、四 lane 的 FP 全部返回，
   且无错误，才允许任何目的写入。此前错误取消全部私有工作并排空，不发布结果/flags。
   仅压低外部 write-ready 不能替代内部禁止 commit。
4. **只在 terminal 回 CPU。** 用 QBS 的 held-request 模式保持原 trans_id；
   不复用 AKV load 的 early-ack (`akv/akv_engine.sv:355`)。
   `ara_sequencer.sv:1058` 的成功 load 可以在 ack 时就回应，所以 PV ack 必须是终结事件。
   final writes 和 owner 释放条件满足后，单次发布 response、VID done、load_complete、active flags。
   非法 decode 也要平衡 load accounting，不能重复发 complete。

复用 `ara_resp.fflags/fflags_valid`，增加 PV terminal 的四 lane flags 汇总选择
(`ara_sequencer.sv:1083`)，不得借普通异步 flags 泄漏被取消的运算。
无需新架构 CSR；CVA6 已有 FP CSR busy/final-flags 串行机制
(`hardware/deps/cva6/core/acc_dispatcher.sv:120`)，必须保持到最终 flags 可见。
新增的是 owner/各 lane 接受、drain、commit/error 和累积 flags 状态，而不是新 MAC。

## 6. 分阶段最小接入与验收

按当前 goal 分阶段执行，前一阶段验收后再推进；本文本身不启动队列。
使用独立输出和冻结 pins 的 VCS gate，不用 Verilator/URG。

| 阶段 | 最小接入 | 必须满足的退出条件 |
| --- | --- | --- |
| A：编码与几何 | 生成 ABI 常量/encoder，接 decoder、源维护、StA 请求与 scoreboard；capability 仍关闭 | 精确区分 PV/旧 column/panel；FS/VS-off、frm5/6/7、vstart、upper bits、Dcode、对齐/越界/alias 拒绝无副作用。混合旧 EEW 的前六源寄存器都转换，第七/八不消费；旧 VL0/384 不改变目的 VL256。 |
| B：父级所有权 | 合并真实 importer/context/VMFPU，接旧流水排空和 source-drain commit 条件 | T1/8/9/63/64、D64/96/128、H1/2；lane 不齐、系数阻塞、native 注册 offer 碰撞；每阶段取消后无残留、无写/flags，后续真实 store/QBS/native 可执行。LSU-only flush 不能单边丢源。 |
| C：架构完成 | 接最终写回、terminal retag/flags/异常/CPU response | 所有 final grant 延迟/乱序下仍只 retire 一次且 ID 正确；失败目的内容/tag 全不变；成功仅 active 数值有定义、组外不变。inactive poison 不影响结果/flags；后续依赖读写、FCSR 读写、refill/release 不能越过 terminal。覆盖两种 SharedFma 和旧指令回归。 |
| D：软件与完整调用 | 新 wrapper 整组 clobber；接 capability/profile 与 RVV fallback | 真实 llama.cpp 数据跨 D/H/T 的完整调用收益，计入准备、转换/interleave、maintenance、import/drain、写回和 CPU 完成；数值语义不变。局部 FMA 周期不能作端到端加速比。 |

新 capability 建议另用 `akvinfo(4)`，不可在旧 word2 随意加位：
`software/akv/src/akv_runtime.c:101` 会拒绝未知位。旧 ABI/SDK 行为保持不变；新指令和
helper 通过前不宣告可用，未满足形状/类型/能力或平台准入时继续普通 RVV fallback。
上述任何 host gate 都不等于 FPGA acceptance；上板结论仍需重建并验证 bitstream。
