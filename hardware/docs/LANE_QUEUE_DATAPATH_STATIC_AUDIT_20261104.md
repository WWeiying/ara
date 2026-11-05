# Lane 队列与数据通路静态冗余审计

## 1. 范围与结论

本次只完成两个方向的静态审计：

1. Lane 操作数、指令和结果队列的数据生命周期、容量、位宽、复位与清零。
2. 操作数选择、格式转换、VRF 返回和写回网络的重复逻辑。

审计对象为 `ara_dsa` 工作区，HEAD 为 `47adfc126`。工作区已有尚未提交的
共享移位 ALU；不能只用 HEAD 复现整个工作区。本文末尾记录关键文件哈希。
本次不修改 RTL、依赖库、FPGA 副本或测试检查器，不运行仿真、综合。
结论是候选设计审查，不是新增优化的正确性、性能或面积验收。

**最值得实施的三个候选：VRF 返回网络去掉不需要的仲裁、整数扩展统一字节
选择、操作数输入 FIFO 的 payload/控制复位分离。**

**不应直接做：删除结果队列清零、合并信用/占用计数、共用不同操作数队列、
删除源快照、削减容量、把浅队列统一换为 SRAM。**

原先提出的“结果队列无效数据清零可能冗余”需要收窄：VALU 普通结果也依赖
旧表项为零，不仅仅是归约特殊路径依赖它。下面给出源码依据。

## 2. 当前数据通路与审计依据

```text
lane_sequencer
  -> 每个 operand requester 保存独立地址/长度/依赖状态
  -> 每 bank 的高/低优先级仲裁 -> VRF SRAM
  -> 一周期后，按目标 queue 路由返回值
  -> 与 source snapshot replay 选择
  -> input FIFO + command FIFO -> 扩展/重排/归约填充
  -> VALU / VMFPU 的独立操作数选择
  -> 结果组装、窄化半包、归约中间结果
  -> result queue -> 写回仲裁 -> VRF
```

MASKU/SLDU/VLDU 的写回在 operand requester 中各有一个 stream register；
它们的入口接受和真正 SRAM 写入不是同一个事件。

| 源码 | 本次核查内容 |
|---|---|
| `hardware/src/lane/operand_queues_stage.sv` | 九个实例的真实参数、并发消费者、异常 flush |
| `hardware/src/lane/operand_queue.sv` | 信用、数据 FIFO、命令 FIFO、扩展、计数和 pop |
| `hardware/src/lane/operand_requester.sv` | 请求/返回生命周期、依赖、长度缩放、bank 仲裁及写回 |
| `hardware/src/lane/vector_regfile.sv` | 一周期 SRAM 返回、目标标签、通用返回 crossbar |
| `hardware/src/lane/lane.sv` | 类型定义、跨模块连接、源快照和 replay mux |
| `hardware/src/lane/lane_sequencer.sv` | snapshot/replay 请求和各操作数来源 |
| `hardware/src/lane/valu.sv` | 指令队列、部分结果组装、归约与结果队列清零 |
| `hardware/src/lane/vmfpu.sv` | issue/processing/commit、窄化、结果返回、归约 |
| `hardware/src/lane/vector_fus_stage.sv` | 独立 VALU/VMFPU 接口组织 |
| `hardware/include/ara_pkg.sv`、`rvv_pkg.sv` | 深度、指令 ID、转换和元素宽度类型 |
| `hardware/deps/common_cells/src/{fifo_v3,stream_register,stream_xbar,rr_arb_tree}.sv` | 实际依赖实现，不以通用 FIFO 的假设代替源码 |

关键定位均是审计时行号，后续修改可能使其变化。

## 3. 容量和状态盘点

以四 Lane、VLEN=1024、64-bit Lane 数据通路为例，九个队列不是统一的两级 FIFO：

| 操作数队列 | 命令深度 | 数据深度 | 转换/用途 |
|---|---:|---:|---|
| AluA | 4 | 5 | 整数扩展 x2/x4/x8，归约 seed |
| AluB | 4 | 5 | 整数扩展 x2/x4/x8，归约尾部填充 |
| MulFPUA | 4 | 5 | x2、浮点重编码、归约 seed |
| MulFPUB | 4 | 5 | x2、浮点重编码、归约填充 |
| MulFPUC | 4 | 5 | x2、浮点重编码、旧 vd/累加操作数 |
| StA | 5 | 2 | store 数据，异常 flush |
| SlideAddrGenA | 4 | 2 | slide/index 地址共用，目标标签、cmd pop、异常 flush |
| MaskB | 3 | 3 | mask/gather 相关操作数，整数扩展，cmd pop |
| MaskM | 1 | 1 | mask 数据，异常 flush |

每 Lane 合计 33 个 64-bit 数据槽，即 2112 bit；命令槽同样合计 33 个。
本配置命令类型名义宽度为 22 bit：EEW 3、elem_count 11、conv 4、
ntr_red 2、is_reduct 1、target_fu 1，共 726 bit。实例未使用的字段可能已被
综合消除，不能把这些名义位数全部算成可压缩触发器。

VALU 和 VMFPU 各有四项指令队列、两项结果队列；每个结果 payload 名义
94 bit（ID 3、地址 10、数据 64、BE 8、vxsat 8、mask 1）。两者结果数据
合计只有 376 bit/Lane。不能把整个 VFU 面积都当成结果 FIFO 的面积。

源快照容量为 `8*VLEN/(NrLanes*64)` 个 64-bit word，即 32 word/Lane、
2048 bit/Lane，四 Lane 总共 1 KiB。它服务合法重叠访问，不是重复的性能缓存。

### 3.1 历史面积只能用于筛选

参考：`hardware/dc_runs/20260916_control_closure/backend/syn/ara_soc/v1-dc/reports/area.rpt`，
报告日期 2026-09-16；它不是当前工作区的重新综合结果。

| 单 Lane 层级 | 历史面积，um2 | 使用方式 |
|---|---:|---|
| operand queues 合计 | 17434.0317 | 包含 FIFO、转换与控制，不能全计为存储 |
| operand requester | 12856.5358 | 包含依赖、地址、stream register 和 bank 仲裁 |
| VRF 返回 mux | 3699.3599 | 位于 VRF 层级，不包含在前两项中 |
| VALU | 17118.5278 | 包含旧整数 ALU，不代表当前共享版 |
| VMFPU | 157310.9979 | 包含算术单元，不是可由本次队列审计消除的面积 |

返回 mux 四 Lane 历史总面积约 14797 um2，即使全部去掉也只有该报告 SoC
面积的约 0.41%；实际仍要保留路由数据选择。因此本次不能预告整芯片大幅缩小。

## 4. 可实施候选

### A1. VRF 返回网络专用化，优先级最高

位置：`operand_requester.sv:508` 附近的单 bank 请求，
`vector_regfile.sv:48` 的返回标签，`:130` 的 `i_vrf_mux`，以及
`stream_xbar.sv:138` 的逐输出仲裁。

当前每个 requester 每周期只由其地址低位选择一个 bank；对应固定的 queue
编号。一个 bank 最多接受一个请求。每个 bank 的返回延迟相同，目标标签与
read-valid 同步寄存。因此对于任意队列 q，同周期的有效返回来源满足：

```text
hit[q][b] = rdata_valid_q[b] && (tgt_opqueue_q[b] == q)
onehot0(hit[q])
```

现有实现却为九个输出分别实例化八输入 RR arbiter；其外部接收恒为 ready，
没有输出 spill register。若上述结构性不变量成立，合法流量下不存在需要
轮询裁决的冲突。可以用 `OR(hit & rdata)` 的专用 one-hot 路由替代通用仲裁，
保留原来的一周期 SRAM 返回和本周期组合路由。

这不是删掉读数据 mux；仍需八选一的数据选择，只去掉不需要的竞争管理。
空输出的数据不必与原 RR 选中的无效数据一致，但必须证明所有消费者均由
valid 门控。源码中 input FIFO 只在 operand_valid 时 push；snapshot capture
同样由 VRF valid 门控。非法多来源不能默默 OR 掩盖，应加入 onehot0 断言。

适用边界：当前等延迟 SRAM、每 queue 单 requester。未来若加入变延迟返回、
多端口向同一 queue 送数据，必须重新审查，不能继续沿用这个结论。

验证要求：全部单来源 bank/queue 组合、多 queue 同时返回、连续跨 bank、
flush 前后返回、snapshot replay 交界；检查有效数据、valid、入队和周期逐拍一致。
固定一组输入比较旧 xbar 与新路由，并对冲突注入确认断言报错。

### A2. 整数符号/零扩展共用选择网络，优先级高

位置：`operand_queue.sv:227`、`:339` 至 `OpQueueAdjustFPCvt` 分支。

SExt/ZExt 的 x2/x4/x8 各自重复了同一源元素选择，差别在扩展高位。
例如 x2/EW8，两者均选择 `ibuf_operand[16*e+8*select +: 8]`。
建议先形成每个目标元素的源片段，再由 signed-extension 使能生成高位填充值。
转换倍数和源 EEW 只控制源片段映射，不分别复制完整符号/零扩展路径。

`select_q` 是输入 word 内的消费位置，必须保留 `deshuffle_index` 产生的物理
字节顺序，以及 x2/x4/x8 的 4/2/1 步进。不能把它改成简单连续字节索引。
FP conversion 的 `OpQueueAdjustFPCvt` 还具有专门的元素重排，不能仅凭外形
相似并入整数扩展。浮点 subnormal/NaN 重编码本轮保留。

共享范围是单个 queue 的互斥转换，不能把 AluA/AluB/MFPU A/B/C 合为一个
转换器：它们可能同周期消费不同指令状态的操作数。

综合工具可能已合并部分表达式；静态代码重复不等于净表重复。后续只做一版
有明确结构的候选，若部件面积没有实质下降，不继续反复试写法。

验证要求：每个合法 EEW/倍数、全部 select 位置、正负边界及随机数据；同时
比较输出、元素计数、select、ibuf_pop/cmd_pop，包含背压、最后不满 word、
连续命令、masked/restart/widen/narrow 消费场景。FP/neutral 路径做不变对照。

### A3. input FIFO payload 与复位控制分离，优先级高但收益待测

位置：`operand_queue.sv:96` 和实际 `fifo_v3.sv:143` 附近。

当前通用 FIFO 对所有 payload 位做异步复位。input FIFO 的有效数据必须先
经过 push 写入；pop 只来自有效输出的消费，flush 清指针和计数而不擦 payload。
这使得 2112 bit/Lane 数据存储具备采用无复位 DFF 的条件。

建议仅在局部专用 FIFO 或兼容的局部包装中拆分 payload 和控制；不修改所有
模块共同使用的 `fifo_v3`。保持深度、非 fall-through 行为、full 时不接受新
push 的语义、同时 push/pop 行为以及 flush 优先级。指针、计数和 valid 必须复位。
payload 只能在有效写使能下写入，不能让未知数据影响控制或架构输出。

该改动减少的是复位单元/复位网络开销，不是删除 2112 个存储位。
库中有无更小无复位单元、综合是否已做等效处理，决定实际收益。
命令 FIFO 先不一起改：空命令的 EEW/conv 会直接进入转换和 pop 组合逻辑，
需要另证数据先于命令返回的关系及复位后 X 传播。三个外部写回 stream
register 的数据复位可作后继候选，但 tag/valid 和 grant 不随意改变。

验证要求：复位后 payload 置 X、首次读写、环绕、满/空边界、push/pop 同拍、
flush+push、在途 VRF 返回与 flush、snapshot 注入；有效数据与完整握手逐拍
对照，独立检查无未初始化读取。不能用忽略所有 X 的检查器验收。

### A4. 写回仲裁的控制与宽数据分离，优先级中

位置：`operand_requester.sv:267` 的 payload，`:1019` 起的每 bank 仲裁。

当前将地址、wen、wdata、BE、queue ID 一起经过高优先级、低优先级和最终
选择。读请求的 wdata/BE 为常量零；写数据来自五个 FU 源。
可保留原有 RR 控制与高低优先级，仅让仲裁传递源索引/必要元数据，再根据
最终获胜源选择写数据和 BE。另一种等价表示是使用最终 one-hot grant 选择数据。

不能合并成“所有 bank 共用一个获胜写回源”：不同 bank 可以同时接受不同 FU
的写回。不能改变 RR 更新、优先级、同拍 grant、final_gnt 或 chaining 的
`vinsn_result_written_d/q`。后两者是依赖推进的依据。

该方向可能减小重复宽 mux，也可能把选择推到 grant 之后拉长关键路径。
常量零分支又可能已被综合消除，因此排在 A1/A2 后面，不承诺时序必然改善。

验证要求：同 bank 冲突与不同 bank 并行；五个写源、读写混合、持续背压、
stream register pop/refill 同拍；精确比较每个 grant、SRAM 写数据/BE、依赖推进。

### A5. 位宽和命令元数据，优先级低至中

`lane.sv:33` 的 VRF 地址类型按字节容量计算，本配置为 10 bit；
`ara_pkg.sv:1013` 的 `vaddr()` 和 requester 实际按 64-bit word 编址。
本配置只需 128 个 lane word、7-bit 有效 word 地址；每 bank 16 word 只需 4 bit。
这是值得核查的类型过宽，但不能直接裁公共接口：需覆盖最后地址加一、
LMUL 组边界、slide/gather、异常重启、跨模块写回和验证地址字段。
高位也可能已被综合消除。它与 Linux 虚拟地址保留 64 bit 完全不是同一问题。

`operand_requester.sv:383` 的四个长度换算中间量使用 64-bit `elen_t`；
输入则为参数化 `vlen_t`。可推导有界字节长度并使用局部宽度，但必须保留
左移、减法、向上取整、slide 特例及无效周期行为。不能仅按常见 VL=1024 裁宽。

信用和 FIFO 计数部分非二次幂深度存在名义额外位，例如深度 5 的计数用 4 bit，
而范围 0..5 只需 3 bit。应保留容量端点，采用 `clog2(depth+1)` 的参数化
推导；收益只是少量位，不应为此全局修改依赖库或启动长回归。

命令字段在 queue 实例中有些不使用，但参数常量传播和未使用位裁剪通常能
直接处理。需要看实际综合网表再决定是否引入多个专用命令类型。

## 5. 明确不能直接删除的逻辑

| 对象 | 看似重复的原因 | 实际责任和决定 |
|---|---|---|
| `ibuf_usage_q` 与 FIFO occupancy | 都像占用计数 | 前者在 operand_issued 加一，后者在 operand_valid 返回时加一；信用包含在途读取，保留 |
| requester 的剩余长度与 queue elem_count | 都记录向量长度 | 前者管理 VRF word 请求，后者管理扩展后的消费；扩展会多拍消费一个 word，保留 |
| VFU 指令队列与 `vinsn_issue_q` | 指令似乎存了两份 | issue 预取寄存器隔离动态选择路径；issue/processing/commit 可指向不同指令，不能随意合并 |
| VMFPU `vinsn_processing_q` | 名字含 q 像额外寄存器 | 实际为对 vinsn_queue_q 的连续选择，不是独立 always_ff 存储，不能虚报删除收益 |
| 每字节 vxsat 与 BE | 最后只需要一个 CSR bit | 窄化、mask、tail 要先按有效字节筛选再归并；不可提前无条件压成一位 |
| MASKU/SLDU/VLDU stream register | FU 似乎已有结果队列 | 隔离外部时序并提供弹性；入口 grant 和最终 SRAM grant 不同，保留 |
| 普通与 reduction 结果数据 | 都在 result queue | result queue 还是累加器/半包暂存，valid=0 不意味着 payload 没有用途 |
| 源快照 | 与 VRF 保存相同数据 | 目的寄存器写回后仍需旧源，服务合法重叠/restart；不可删、不可仅凭 LLM 少用裁掉 |
| ALU/MFPU 标量广播 | 都是复制标量到 SIMD 元素 | 两个 FU 可独立并行、SEW 和标量值不同；跨 FU 共用会产生新资源冲突 |
| 常量 shuffle 与 slice 连线 | 代码行数多 | 常量重排可能只是布线，不能按 RTL 行数估算门数 |

### 5.1 结果队列清零的具体反例

VALU `valu.sv:917` 对非归约普通路径也执行：

```systemverilog
result_write.wdata = result_queue_q[result_queue_write_pnt_q].wdata | valu_result;
```

旧表项若残留 1，即使新结果为 0，也会写回 1。只删 `valu.sv:1215` 的出队
清零会改变结果。`:931` 的 vxsat 也采用累积 OR。窄化第一半处理完后可能
尚未设置 result_queue_valid，但第二半必须读取第一半；直接以 valid 选择
零值会丢失第一半。因此优化必须先把“空槽、部分组装、完整可提交、归约
累加”生命周期显式区分，或使用已有等价状态证明，不能只删 reset/clear。

MFPU 普通结果通常全覆盖写，窄化却只写半包，并以 BE 记录有效位置；归约
还使用 `first_result_op_valid_q` 跟踪部分结果（`vmfpu.sv:754`、`:2265`）。
不能套用同一个“无效槽内容无用”的论断。全 mask 浮点归约 seed 的原样旁路
以及结果标志必须保持。

两模块已经采用常量索引的整表项写入，保留后续 read-side clear 的优先级；
源码注明此前 Vivado 对动态字段写/整项清零重叠处理出现过问题。不能为了
缩短代码恢复那种写法。结果队列优化本轮判为需要另行设计，不列首批实施。

### 5.2 为什么不统一换成 SRAM

操作数数据队列只有 1/2/3/5 项，结果队列只有 2 项；需要即时组合读、
同拍 push/pop、部分字节组装和归约回读。同步 SRAM 会增加端口、旁路或读
延迟约束，可能比保留 DFF 更贵。VRF 本身已经是 SRAM。
源快照虽然较大，但有多 queue replay 读取，不能在未盘点同时读端口前替换
为单端口宏。当前只建议 payload 无复位 DFF，不把 SRAM 化当作默认答案。

## 6. 建议实施顺序和验收边界

本次到静态审计为止，不自动开始下面的实施。

1. A1：先验证 onehot 返回不变量及新旧路由等价，再做单部件面积/时序比较。
2. A2：在每 queue 内合并 SExt/ZExt 选择，保持参数化格式支持和周期。
3. A3：限定 input FIFO 的 payload 复位分离，不同时改命令/结果队列。
4. A4/A5：前三项有实测净收益后，再决定是否做写回 payload 拆分与局部位宽。

每项保持容量、外部握手、每周期并发数、SRAM 延迟、异常 flush 和最终写回
顺序不变。不能把吞吐下降换来的面积降低归为本轮目标实现。

必要的后续验证分层：

- 局部：新旧输出/握手逐拍比较，参数边界和 X/复位/flush 专门检查。
- 组合：requester -> VRF -> queues，冲突、背压、snapshot、不同 EEW 同拍工作。
- SoC：原 62 项共享 ALU 回归可复用作起点，但不代替新增的网络/flush 定向
  检查；补 source overlap、indexed fault/restart、mask/slide、浮点窄化和归约。
- 性能：同 ELF、同配置逐区域比较 cycles、队列阻塞和读写次数；不是仅看 PASS。
- 面积：同库、同约束部件比较；当前没有新增综合结果，不填写预期节省百分比。

建议探针：cycle、queue/bank ID、issue/return/pop、credit/occupancy、
command fire、select/elem_count、snapshot replay、flush、result partial/valid、
所有写源 grant、最终 SRAM addr/data/BE。只取覆盖假设的短窗口，避免盲目长跑。

## 7. 静态审计完成核对

| 要求 | 本次证据与结论 |
|---|---|
| 队列深度和类型 | 已逐实例核查，见第 3 节；纠正默认深度与实际深度混淆 |
| 生命周期、复位、重复数据 | 已沿 issue/return/consume/writeback 核查，A3 与第 5 节明确可尝试及不可直接删项 |
| 位宽和元数据 | A5 列出局部候选、综合可能已裁剪部分及不可擅改的边界 |
| 操作数选择和转换 | A2、独立标量广播及 FP/reduction 不合并边界已说明 |
| VRF 返回和写回 | A1 给出 onehot 结构性论证；A4 保留仲裁/并发/最终 grant |
| 性能、正确性与工具风险 | 每项列明不变量、反例和后续最小验证，未宣称已实现或实测节省 |
| 不影响当前工作 | 只新增本报告；现有 RTL、冻结 helper、FPGA 与报告不修改 |

## 8. 源码身份

以下 SHA256 对应本次读取的工作区文件。当前无新的仿真/综合验收；历史面积
报告与这些源码不是同一版本，不能混用为严格 PPA 配对。

```text
eafc82bfe3bd7413aa549015a2145e977d1ce01a9bd52c369993e5dac10e453d  hardware/src/lane/operand_queue.sv
6b0150d900030585c4689e054cc7a47256e0663e9a9eb36780380549518c4676  hardware/src/lane/operand_queues_stage.sv
327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2  hardware/src/lane/operand_requester.sv
583f5b0e5af1a6ac7d120280923b858024f017bc475a79fb3d406449211e2314  hardware/src/lane/vector_regfile.sv
f8a8cd12e9d4732eca87e1c9a1aa48b52a8e684f2d7e64d0e8ec1faa9411c778  hardware/src/lane/valu.sv
a01ea5a29483ada2519ad2f9aa6ae9bcb4fc9bc364aa5d3846715947c7c22581  hardware/src/lane/vmfpu.sv
5e621bf955cad43e87881253a2d8626c5bad23e2251e2ee7276a3518d1036241  hardware/src/lane/lane.sv
33a941e7eeaf8d3818fd74f108231573214040fdc6f483cdaeb1919abc767e57  hardware/src/lane/simd_alu.sv
861ea44cbd3129731b77977da36fb0dac1a1350d7df664a1b4310423e7d272bc  hardware/deps/common_cells/src/fifo_v3.sv
092a9881343f4ad3074906b28b6cc859b5f6e2873a5f770711c05fc01dbb85d3  hardware/deps/common_cells/src/stream_xbar.sv
```
