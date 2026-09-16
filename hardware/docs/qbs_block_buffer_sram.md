# QBS Block Buffer 的 SRAM 接入与验证

## 1. 范围与结论

本工作在 `ara_dsa_sram` 分支完成，起点为 `be1487b5`，现已将
`348cbd50` 快进合入 `ara_dsa`。`ara_dsa_timing` 工作目录未修改；
此前已验证的两批时序优化随基线保留。

目的不是增加算术单元，而是把 QBS 本地块缓冲中适合存储器实现的压缩
payload 从寄存器移到单端口同步 SRAM。保留当前九种权重 profile、
M1--M8、尾块、权重双缓冲、激活复用及故障处理，不改 ISA、数值计算
顺序、dot array、FP accumulator 或 AKV 数据通路。

当前实现使用单端口 SRAM，并合并相邻返回 beat 对同一个 SRAM 字的写入。
2026-09-14 在已合入的 SRAM 实现上增加了写入译码流水：每个 adapter 的权重、
激活入口各有两项 FIFO，保存数据及已译码的目的位置，再进行 SRAM 写仲裁。
这会增加少量 beat 级寄存器，不增加 SRAM 容量、端口或算术单元。
连续规则写入仍可每拍接收一个 beat；非连续地址、块尾排空仍可能产生等待。

第 5 节保留最初寄存器/SRAM 转换的历史对照，不代表当前流水版的周期。
入口译码流水这一步使七个真实切片相对此前版本增加 0.078%--0.263% 的 engine 周期，
详细证据见 [`timing_optimization_port.md` 第 22 节](timing_optimization_port.md)。
随后加入的共享输入对齐压缩写入选数网络，不再增加周期；33 个完整命令和七个真实
切片相对已有流水版的周期均不变，宏模型、故障处理和普通 RVV/QBS/AKV 交接通过。
共享输入对齐的验证及独立综合目录见第 9 节。随后启用了唯一提交计数和
共享读窗口解码，见第 10 节；这两项不改变入口 FIFO、SRAM 或算术流水。
当前权重 SRAM 字宽进一步收窄至 128 bit，激活仍为 256 bit；逻辑容量不变，
只减少物理宏的闲置容量和权重选数网络。新旧周期对照、宏面积及验证见第 11 节。
PNR、功耗闭环和 FPGA 存储映射尚未完成。

## 2. 为什么不能直接把数组换成 RAM

原 `qbs_block_adapter` 向 decoder 暴露全部原生块字节，组合读不需要地址
握手。同步 SRAM 必须先给地址，下一周期才能使用数据；同时一个物理
单端口 bank 每周期只能执行一次读或一次带 byte mask 的写。

当前软件布局还允许这些情况：

- R4 权重连续排列，16-byte AXI beat 可以跨原生块边界。
- payload 不一定从块的第 0 字节开始。例如 Q8_K 激活前面有 4-byte scale。
- Q6_K 的低位、高位和 scale 分处不同区域，不能作为单一线性量化数组读取。
- 激活上下文重放可以和另一银行的权重 AXI 回数同周期发生。
- M5--M8 使用两个四上下文银行，不能按旧 M<=4 实现删除第二组激活存储。

因此本次同时处理了读窗口、写入合并、完成资格以及上游 backpressure。

## 3. 数据划分

每个 adapter 内部有四个行/上下文，每行分三个独立 payload plane。
两个 adapter 保持原来的权重 ping-pong 和八个激活上下文。

| 数据 | 每行/上下文逻辑组织 | 总银行数 | 总逻辑容量 |
|---|---:|---:|---:|
| 权重低位 payload | 8 x 128 bit | 8 | 1024 B |
| 权重高位 payload | 4 x 128 bit | 8 | 512 B |
| 激活 INT8 payload | 8 x 256 bit | 8 | 2048 B |
| 合计 SRAM payload | 单端口、byte write enable、同步读 | 24 | 3584 B |

仍用寄存器保存：

- 每行最多 20 B 权重元数据，包括 scale、min、Q5_0 的高位辅助位等。
- 每上下文最多 36 B 激活元数据，包括 scale 和 Q8_K 的 16 个 bsum。
- 银行归属、完成状态及已提交字节计数。生产路径启用 `UniqueInputBytes=1`，
  用每行计数代替逐字节 valid；通用 adapter 默认仍使用 bitmap，支持重复覆盖。
  生产路径的仿真影子 bitmap 只用于断言，不参与综合。
- 权重和激活各自的一个未完成写 beat。原有两个 adapter 合计 634 bit
  数据/控制状态继续保留；当前另加每域两项入口 FIFO，以及 FIFO 和残留 beat
  的逻辑/物理位置元数据。FIFO 保存的是 16 B beat，不是完整解压块。
  新增状态的综合后面积需查报告，不能直接用声明位数代替。

这里的 3584 B 是逻辑 SRAM 容量，**不是节省的面积**。当前两个权重 plane 均映射为
`TS1N28HPCPUHDSVTB8X128M1SWBSO`，高位银行只使用其中四个地址；激活保持
`TS1N28HPCPUHDSVTB8X256M1SWBSO`。24 个宏的物理 bit 容量合计 4096 B，
其中 512 B 是高位银行未使用的地址。端口、外围电路和字节有效状态都有代价。
不能直接用寄存器 bit 数推导最终面积或功耗。

## 4. 各模块如何配合

### 4.1 `qbs_payload_sram.sv`

定义一个单端口、按字节使能写入、读延迟一周期的存储器；`DataWidth` 支持 128/256。
权重取 128-bit，激活取 256-bit。普通 RTL 仿真使用 `tc_sram`；
`TARGET_SRAM_MC` 根据宽度选择对应 TSMC 宏。
payload 不复位，读数据只能在当前块的 valid/complete 条件满足后被消费。

物理地址仍检查逻辑深度，不允许因为物理宏有 8 个字就访问逻辑银行未分配的地址。
FPGA 后续可使用工程已有的 `tc_sram` FPGA 实现，但本次没有验证 VCU118 映射。

### 4.2 `qbs_payload_buffer.sv`

当前实现把写入逻辑按固定物理 bank 展开，而不是用运行时 bank 下标反复更新整组
宽数据数组。生产 adapter 启用 `StreamWriteData=1`：每个输入 beat 先共享字节对齐，
再依据压缩格式及 M4/M8 布局连接到目标字节，不再为每个 SRAM/metadata 字节重复
生成一套 16 路优先选数器。写地址、byte enable 和两个槽位之间的覆盖优先级保持不变。
独立 payload 模块默认 `StreamWriteData=0`，保留任意逐字节目标及重复目标的通用选择逻辑。
这不是新增软件模式，也不增加 payload 容量、SRAM 端口或流水级。

实际 compute 路径将两个 adapter 配置为 `NativeView=0`，直接输出 SRAM 的
读窗口和辅助信息。权重为 `4 row * 2 plane * 128 bit` 加 `4 * 20 B`
metadata，激活为 `4 context * 256 bit` 加 `4 * 36 B` metadata。计算入口
只需选择这 3840 bit 的有效存储视图，不再先展开成 16064 bit 的原生索引视图
再选择 bank。数字描述的是组合接口宽度，不是新增寄存器数或最终门数。

兼容测试仍可启用 `NativeView=1`：各格式的 `weight_view` 和 `activation_view`
只是组合连线，不是额外保存九份 block。未启用的兼容输出逐元素接零，由综合
常量折叠消除。综合友好改写的依据、功能对照和证据边界见
[`timing_optimization_port.md` 第 14 节](timing_optimization_port.md)。

原生块 offset 转换为 `(plane, plane 内字节偏移)` 的函数集中在生成的 `qbs_pkg`，
由 `scripts/gen_qbs_abi.py` 维护。生产 adapter 配置
`PredecodedWriteLocations=1`，在 FIFO 前完成转换，payload 模块直接消费保存的
位置；payload buffer 再按 plane 宽度拆成 word/byte lane，权重使用 `[6:4]/[3:0]`，
激活使用 `[7:5]/[4:0]`。独立测试保留默认的原生 offset 译码路径。所有格式仍保持压缩
存储，直到 profile decoder 才拆位、查 IQ4_NL 表或恢复有符号量化值。

| Profile | 低位 SRAM | 高位 SRAM | 寄存器中的辅助信息 |
|---|---|---|---|
| Q4_K | 128 B 量化低位 | 不使用 | d、dmin、12 B subgroup 元数据 |
| Q5_K | 128 B 量化低位 | 32 B 高位 | d、dmin、12 B subgroup 元数据 |
| Q6_K | 128 B 低位 | 64 B 高位 | 16 B scale、2 B d |
| Q3_K | 64 B 低位 | 32 B hmask | 12 B scale、2 B d |
| Q2_K | 64 B 量化位 | 不使用 | 16 B scale/min、d、dmin |
| Q8_0 | 32 B INT8 | 不使用 | d |
| Q4_0 / IQ4_NL | 16 B 压缩值 | 不使用 | d |
| Q5_0 | 16 B 低位 | 不使用 | d、4 B 高位辅助位 |

模块有两个组合输入槽位：slot 0 是旧 pending，slot 1 是入口 FIFO 本周期取出的
beat，而不是尚未寄存的 AXI 输入。这两个仲裁槽位不是两个物理写端口；
两项入口 FIFO 则是实际的寄存器存储，位于本模块之前。

每个物理银行先选择旧 pending 需要的一个字，再把新 beat 中落在同一字的
字节合入。没有旧写入的银行可以直接服务新 beat。一个 SRAM 字最后只产生
一个地址和一次带 byte enable 的写入：权重为 128-bit data / 16-bit enable，
激活为 256-bit data / 32-bit enable。
如果同一字节同时被两个槽位覆盖，以 slot 1 的新数据为准。
不同银行可以同时写，权重与激活之间不共用写端口或暂存状态。

#### 输入对齐为何可以共享

adapter 的每个输入 beat 最多包含 16 个连续源位置；strobe 可以有空洞，
不同 beat 的偏移可以不连续，甚至重复。优化只利用 **同一个 beat 内的布局关系**，
不要求整个命令的 beat 严格按顺序到达。SRAM 字、原生块、scale/payload 区域的
边界仍由原来的完整目标地址和 mask 判断，不能只凭低四位决定是否写入。

权重使用统一的 R4 源坐标。设每行压缩块大小为 `B`，源位置为 `S`：

- R4 的 `S` 就是该 beat 的源偏移；row-major 的 `S = row * B + offset`。
- 对目标行 `r`，共享对齐后的第 `j` 字节取 `beat[(j + r*B - S) mod 16]`。
- K 格式各存储区域起点均为 16 的倍数，因此 payload/side 的低四位可以直接使用。
- Q4_0、Q8_0、IQ4_NL 的低位 payload 从原生字节 2 开始；Q5_0 从字节 6 开始。
  这两种偏移用固定连线选择，side metadata 不做这一偏移。

例如 Q6_K 每行 210 B，R4 中源偏移 208 的 beat 含 row 0 的最后两个字节，
以及 row 1 的前 14 个字节。对 row 1，`r*B-S=2`，其第 0 字节自然选择
输入 byte 2；row 0 的元数据仍取输入 byte 0/1。没有填充、丢弃或额外重发。

激活首先按该 beat 原始 offset 对齐，再用静态布局连线选择：

- row-major：payload 的原生偏移为 `scale_bytes + payload_offset`。
- M4/M8：`C` 为存储的 context 数，payload 源偏移为
  `C*scale_bytes + C*payload_offset + global_context`。
- scale 按 context 连续排列；Q8_K 的 bsum 则按 2 B 元素交错，不能按量化值的
  单字节交错方式处理。代码分别计算两个区域的常量连线。
- 第二个 adapter 的 `global_context = local_context + 4`，因此 M5--M8
  后四路也有独立且正确的字节来源。

`rotate_beat()` 采用四级固定字节旋转网络。`activation_phase()` 中的除法和取模
只处理生成期的常量布局参数；没有增加运行时除法器。共享的是对齐后的组合数据，
不是 SRAM 端口或计算单元。共享输入对齐本身不改去重状态；第 10 节的后续优化
才在唯一提交契约下用计数替换 bitmap。两种模式都不能用“接收字节数”判定完成。

验证时可启用 `QBS_STREAM_EQUIV`，在每一个实际写入周期检查：同一 beat 对该
物理字节至多有一个写者，并且共享对齐选出的数据严格等于原 16 路选择树的结果。
`verification/timing/qbs_stream_contract_checker.sv` 另外检查真实 adapter 目标与
源坐标的对应关系。新增 profile 时必须同时检查区域偏移和这些断言，不能只增加
枚举值或修改块大小。

地址映射函数把 profile 和 offset 都作为显式参数。不能只传 offset，
却在函数内部隐式读取可能变化的 profile：格式切换而 offset 不变时，
连续赋值的仿真敏感性可能遗漏格式变化。首次格式切换和各 profile 的
读窗口对照已纳入测试，防止首拍被错误分类为元数据。

`qbs_profile_engine_int` 和其中的 decoder 在实际 compute 路径使用
`CompactRead=1`。decoder 按行共享当前窗口的字节对齐，再逐元素拆 low/high 位，
不再为每个格式和输出元素分别动态查询完整窗口。metadata 仍由原生 offset
映射读取；scale、min、bsum 和浮点累加顺序不变。两个 bank 的选择和 M8 的 context wave 仍在
compute 模块中完成，没有改变 SRAM 地址发起及返回的时刻。

这仍然是**同步读窗口**，不是可任意寻址的完整块。只有当前 K 索引需要的
payload 有效。独立 profile 测试可用 `CompactRead=0` 接原生索引视图；必须
保证生产端和消费端的配置配对。新增格式时，写入 offset 映射、紧凑读映射及
量化解码需要一起维护，并跑各 K 窗口的独立内容对照。

### 4.3 `qbs_block_adapter.sv`

沿用原来的 R4/M4/M8 字节映射及完整范围检查。先检查原生 offset 和
行/上下文是否合法，再截取局部地址位宽，不能先截断再判界。

数据进入某个 SRAM 字或元数据寄存器时才更新完成状态，并增加
`accepted_*_bytes_o`。这些字段在本模块指**已写入本地存储的唯一字节数**，
不保证和输入 beat 握手同周期更新。两种实例化方式为：

- 生产 compute engine 的两个 adapter：`UniqueInputBytes=1`，每个原生字节在
  一次 clear 到下一次 clear 之间至多写入一次。按行累计实际提交数，完成还要求
  入口 FIFO 和 pending 排空；输入顺序可不连续，strobe 可以有空洞。
- 通用 adapter 默认：`UniqueInputBytes=0`，保留逐字节 bitmap 和去重查询。
  重复字节可以覆盖数据，但不重复计数。下面的 bitmap 更新/查询描述仅适用于此模式。

valid 状态按固定 `(row/context, byte)` 位置生成写使能：将所有已提交且目标相同的
字节请求作 OR，再把该 valid 位置 1。因为这些请求都写入常量 1，不需要数据缓冲中
“最后一个写者获胜”的优先选择链。清除、复位以及置位所在的周期不变，去重查询
仍读取更新前的 valid 状态。它只是更新网络的改写，不减少原有逐字节覆盖精度。

译码按输入字节共享，而不是每个目标 valid 位都重新比较完整地址。每个输入目标拆为
行/上下文号、16-byte 分组号和组内 4-bit 偏移；先生成这三组选择信号，再在每个
固定目标处合并。16-byte 分组只是组合译码的组织方式，不要求输入 beat 对齐，也
不把 valid 精度扩大到 16 B。210-byte 权重和 292-byte 激活的最后一组仅生成实际
存在的 2/4 个 valid 位，不新增存储、流水级或 SRAM 端口。

去重读取按输入 beat 查询一个 16-bit 窗口，不再对 32 个候选字节分别做完整的
`valid[row][offset]` 动态查询。具体过程为：

1. 根据当前 profile，把已有的 native byte-valid 按源字节顺序连线。权重按
   R4 block-major 顺序连接，row-major 访问通过 `row * block_bytes + offset`
   定位；激活分别连接 row-major、M4 或 M8 的 scale、quant 和辅助数组顺序。
2. 源偏移的高位选择从 16-byte 边界开始的 32-bit valid 窗口，低四位右移，
   取出本 beat 对应的 16 位。多取的 16 位处理未对齐 beat，尾部补零。
3. 将查询结果与原来的 mapping-valid、strobe 和同拍旧/新 beat 去重条件结合。
   只有 SRAM/metadata 实际消费的字节参与计数，未提交字节继续留在 pending。

例如 Q6_K 每行 210 byte，R4 源偏移 208 的 16-byte beat 同时覆盖 row 0 的
208/209 byte 和 row 1 的 0..13 byte。窗口读取保留这种跨 native-block 行为，
不要求 block 大小为 16 的倍数。M8 的两份 adapter 只连接各自四个 context 的
valid，其余 context 在该视图中为零，最终仍用原来的 context 范围检查筛选。

这些视图只是组合连线，不是第二份 valid 存储；每个 adapter 的 2008 个 byte-valid
位及更新周期不变。格式映射的除法和取模仅出现在编译期常量函数中，用于生成固定
索引，不用于运行时地址计算。新 profile 若改变源布局，必须同步增加此视图映射，
并用原 native 索引规则验证，不能只修改 block 大小。

一次写入的流程如下：

1. 入口 `ready` 由两项 FIFO 的占用和本域 read/clear 决定，不经过 SRAM 仲裁反馈。
   握手时保存原始 beat，以及每个字节的合法位、行/上下文、原生 offset、物理 plane/offset。
2. 下一拍，若旧 pending 能在本拍写完，取出 FIFO 队首。旧字节先选择 SRAM 字，
   队首中落在同一字的字节合并写入；两者可以同拍提交。
3. 只把该队首 beat 未写完的字节及其目的位置转入 pending。输入 FIFO 可在同拍
   入队下一 beat；不能覆盖仍未提交的旧 pending。
4. 非连续地址可能使 pending 跨两个 SRAM 字，此时先暂停出队、排空一个字。
   FIFO 暂存后续输入，满时再向上游施加反压；满状态不通过组合 pop 放行输入。
5. bitmap 或逐行唯一字节计数只在实际写入后更新。complete 还要求 FIFO 与 pending
   均已排空，不能将“最后一拍已接收”误当作“块可供计算”。无新输入且允许写入时，
   两项 FIFO 加 pending 的保守排空上界为六拍。

例如 Q8_K 激活的量化值前面有 4-byte scale：

| FIFO 出队的原生 offset | 对应量化字节 | 本周期 SRAM 写入 | 留到下一拍 |
|---|---|---|---|
| 32--47 | 28--43 | 字 0 的 byte 28--31 | 字 1 的 byte 0--11 |
| 48--63 | 44--59 | 字 1 的旧 byte 0--11 + 新 byte 12--27 | 无 |
| 64--79 | 60--75 | 字 1 的 byte 28--31 | 字 2 的 byte 0--11 |
| 80--95 | 76--91 | 字 2 的旧 byte 0--11 + 新 byte 12--27 | 无 |

原来单独补写尾部会插入空拍；现在利用 SRAM 一次可写 32 B、输入每拍只有
16 B 的差额合并写入，连续回数不必暂停。数据仍在 SRAM 中，没有退回整块寄存器。

通用模式下，同拍旧、新 beat 可能覆盖同一个源字节。计数逻辑先把二者 offset 归一到
同一行组/上下文组的字节位置，再移位对齐旧 committed mask，剔除新槽位中的
重复项。两组 16-bit mask 分别计数后相加；中间计数支持最多 32 个提交字节。
重复写仍更新数据，但 `accepted_*_bytes_o` 只累计唯一字节。

即使剩余字节只是重复覆盖，也不能让 complete 提前使能计算。
clear 优先于写入，清除本域有效位、FIFO 占用/指针和 pending，不扫描清零 SRAM。
权重 clear 不清除激活 FIFO，激活 clear 也不清除权重 FIFO。没有 reset 的数据寄存器
只能在有效位和占用允许时被消费。断言检查 FIFO 上下溢出、残留写不被覆盖、
clear 后无遗留事务、待写期间格式稳定，以及 read 不与 clear/FIFO/pending 冲突。

激活 context 的 REUSE/RELEASE 同样必须区分接收与落盘：回放启动握手后，
`qbs_engine` 复用 `activation_range_index_q` 记录本块已经发起；即使块尾还在 FIFO
中，也不再启动同一 K 块。推进到下一块时才重新取得启动资格。否则重复回放可能
被反压保存到下一 K 块，造成错误数据。仿真另用按 K 块记录的位图检查唯一启动，
该位图不参与综合。

### 4.4 `qbs_profile_engine_int.sv`

SRAM 读入口使用现有 issue 阶段的 `buffer_read_valid_o` 和 `buffer_read_k_base_o`。
本轮写入流水不改变已有 dot/correction 的级数或 FP 的算术顺序。

| 时刻 | 原寄存器版本 | SRAM 版本 |
|---|---|---|
| 边沿前 | K cursor 等待进入 s0 | 同一 K cursor 驱动 SRAM 读地址 |
| 边沿 | K 进入 s0 寄存器 | K 进入 s0，同时 SRAM 采样地址 |
| 下一周期组合逻辑 | decoder 按 s0 K 读完整数组 | decoder 按 s0 K 使用 SRAM 返回窗口 |
| 下一边沿 | dot array 接收解码值 | dot array 接收相同解码值 |

每周期消费 K 数量仍为 M1:8、M2:4、M3/M4:2。请求的 K 索引自然对齐，
一个 decoder 周期不会跨越其 payload 窗口。M8 两个四上下文 wave 的规则保持不变。

### 4.5 `qbs_compute_engine.sv`

把 SRAM 写入 ready 接回原有 `weight_write_ready_o` / `activation_write_ready_o`。
M8 的激活输入广播只有在两个 adapter 都 ready 时才算一次握手，避免一侧
接收、另一侧丢失。读取仅送到当前权重银行和当前 activation wave 银行。

原来的银行切换、下一 tile 预取、tail-wave correction drain 以及
`QBS_FAULT_CLEAR` 条件保留。SRAM 的到来不允许在读数据尚未消费完时清理
银行，也不能在 fault 后把 pending 数据误当作下一命令的数据。

## 5. 最初 SRAM 转换的历史实测

以下是 2026-09-08 的冻结对照，不包含之后的算术和入口时序流水优化。
当前版本数据见第 1 节链接。以下均为 QBS engine 的 command cycles，不是整个 SoC 的 kernel 周期，
也不是模型 tokens/s。输入来自真实 Qwen2.5-1.5B 捕获数据；保留完整 K，
只缩小输出行数和 token 数。

| 数据切片 | M x N x K | 寄存器版 | 独立补写 SRAM | 当时合并写 SRAM |
|---|---:|---:|---:|---:|
| Q4 Decode attn_q | 1 x 32 x 1536 | 2219 | 2254 | 2219 |
| Q4 Prefill attn_q | 4 x 32 x 1536 | 7200 | 7200 | 7200 |
| Q4 Prefill attn_q | 8 x 16 x 1536 | 7638 | 7638 | 7638 |
| Q4 Prefill attn_q 尾块 | 7 x 16 x 1536 | 7612 | 7612 | 7612 |
| Q6 Prefill ffn_down | 4 x 32 x 8960 | 41939 | 42427 | 41939 |
| Q6 Prefill ffn_down | 8 x 16 x 8960 | 44493 | 44981 | 44493 |
| Q6 Prefill ffn_down 尾块 | 7 x 16 x 8960 | 44479 | 44967 | 44479 |

七个点的 dot cycles、输入 payload 字节数、range 数量均未变化。
Q4 Decode 的 activation-load 阶段由 214 恢复到 179 cycles，消掉 35 个额外周期。
探针仍观察到 35 个 activation pending 周期，但这 35 拍现在都同时提交了
旧、新字节，输入没有因此暂停。**pending 占用不能再当作等待周期。**

Q6 M4 的 weight-load 阶段由 2343 恢复到 1855 cycles，消掉 488 个额外周期。
原先最差的短点 Q6 M3/N3/Kblocks2 也由 584 恢复到 529 cycles。
全部 33 个 engine 点与寄存器基线逐项周期相等，而不是只看平均值。

81 组连续写入配置覆盖九种 profile、M1--M8 和现有布局，输入停顿均为 0。
刻意构造的非连续/重复序列仍观察到 4 个域阻塞周期；这些停顿用于防止
一个单端口银行同拍写两个地址，结果和唯一字节计数均通过比对。
因此不能把当前方案称为任意地址流都无停顿的多端口存储器。

计数器口径：

- `weight_pending` / `activation_pending`：正沿前 pending 有效的周期数，是占用，不是 stall。
- `wold_new_commit` / `aold_new_commit`：同拍有旧、新字节提交的次数；可能涉及同字或不同 bank，
  不能直接解释成所有情况下的“同一个字合并次数”。
- `QBS SRAM writes`：adapter 端口采样；集成后的 valid 已被 compute-engine 握手门控，
  不能用其中的 blocked 字段推断上游反压。
- `QBS SRAM ingress`：在 compute-engine 握手门控之前统计真实 `valid && !ready`。
  `buffer_blocked` 是其中 adapter 未 ready 的子集，包含 clear、读取占用等限制，
  不等于写拆分额外增加的周期。

例如 Q4 Decode 仍有 72 个权重入口 blocked 周期，其中 36 拍 adapter 未 ready；
两组权重 pending 均为 0，总周期及各阶段已恢复到原基线。这些计数不能被当成
尚未消除的 72 个 SRAM 写合并开销，也不能把所有阻塞计数相加作总 stall breakdown。
本次性能结论以同输入、同算术工作量下的 command cycles 对照为准。

## 6. 验证范围

- 448 个 profile 用例：逐步比较解码量化值、subgroup、整数结果、FP 结果和 fflags。
- 81 组 adapter 配置：九种 profile，M1--M8，R4/row-major，M4/M8 激活布局。
- 同样 81 组配置的连续回数测试：每拍尝试输入，检查无停顿和所有读窗口的数据。
- 不连续地址使 pending 跨两个字、同拍新旧覆盖、R4/row-major 地址归一去重。
- 全部 65536 种 strobe，重复覆盖、不同 beat 长度、并发写和 clear/pending 取消。
- 与 `be1487b5` 寄存器版并行对照：pending 排空后比较 byte-valid、计数和 complete；
  每个实际读取窗口比较量化值、scale、min、bsum 等解码输出。
- 33 个完整 engine 用例、四类 fault，以及激活缓存 FILL/REUSE/RELEASE。
- 七个真实模型数据切片，明确比较 command cycles 和 traffic。
- 顶层普通 RVV/QBS/AKV 交接：4 个 QBS、10 个 AKV 命令，程序检查通过且无 trap。
- `SYNTHESIS` 宏下的 VCS 编译和功能测试。这仅验证相应代码分支，不是 DC 综合。
- 真实 TSMC 8x256 模型的功能读写验证。零延迟 RTL 会触发宏的 hold notifier，
  因此该测试显式使用 `+notimingcheck`，不构成物理时序验证。
- SRAM 每个使能写字节的已知值检查；可用 `+QBS_SRAM_BUS_TRACE` 打印有界物理端口访问。

测试未覆盖全模型长时间运行、全量随机 RVV 回归、FPGA XPM 实现和带 SDF
的门级时序仿真。不可将代表性通过扩大为所有工作负载和所有物理实现均已验证。

## 7. 复现

在本 worktree 的 `verification/timing` 中：

```sh
make sram-check sram-engine-check BUILD=/tmp/qbs_sram_check RUN_TIMEOUT=300
make adapter-baseline-engine-check BUILD=/tmp/qbs_sram_check \
  BASELINE_ROOT=/path/to/clean_be1487b5_worktree RUN_TIMEOUT=300
```

第二条需将示例路径替换为参考 worktree，其 HEAD 必须是 `be1487b5`，
相关 RTL 没有未提交修改。合并后的 `ara_dsa` 不能再充当该寄存器基线。
`adapter-check` / `adapter-engine-check` 已转到新的握手及窗口感知测试。
旧完整数组的 cycle miter 仅供历史实现参考，不能直接用于 SRAM 窗口接口。

```sh
make -C ../qbs rtl-profile-check \
  RTL_BUILD=/tmp/qbs_sram_profile RTL_RUN_TIMEOUT=300

make sram-check BUILD=/tmp/qbs_sram_macro RUN_TIMEOUT=300 \
  SRAM_DEFINES='+define+TARGET_SRAM_MC +notimingcheck' \
  SRAM_EXTRA_SOURCES='/home/wangwy/ara/backend/library/mem/ts1n28hpcpuhdsvtb8x128m1swbso_170a/VERILOG/ts1n28hpcpuhdsvtb8x128m1swbso_170a_tt0p9v25c.v /home/wangwy/ara/backend/library/mem/ts1n28hpcpuhdsvtb8x256m1swbso_170a/VERILOG/ts1n28hpcpuhdsvtb8x256m1swbso_170a_tt0p9v25c.v'
```

真实数据入口为 `verification/qbs/run_adaptive_real_rtl.sh`，通过
`QBS_ADAPTIVE_RTL_SIMV` 和 `QBS_ADAPTIVE_RTL_RESULT_DIR` 指定独立 binary/结果目录。
顶层入口为 `verification/akv/run_current_handoff.py --output <hardware下新目录>`。
后台运行时保留 source hash、binary hash、返回码和日志，不能覆盖其他工作的结果。

最初写合并版本的结果根目录：`/tmp/ara_dsa_sram_merge_20260908/`；
顶层结果：`/home/wangwy/openproject/ara_dsa_sram/hardware/sram_merge_handoff_20260908/`；
可版本管理的紧凑结果在 `verification/timing/results/20260908_sram_merge/`。
寄存器基线和独立补写 SRAM 记录保留在 `/tmp/ara_dsa_sram_20260908/`，未覆盖。
逐周期 CSV 从首个有效写入开始采样 128 拍，采样点在正沿更新寄存器之前。

```sh
python3 verification/timing/summarize_sram_results.py \
  --run-root /tmp/ara_dsa_sram_merge_20260908 \
  --baseline-run-root /tmp/ara_dsa_sram_20260908 \
  --previous-sram-root /tmp/ara_dsa_sram_20260908 \
  --engine-dir checked_ingress/engine --require-cycle-parity \
  --handoff /home/wangwy/openproject/ara_dsa_sram/hardware/sram_merge_handoff_20260908 \
  --output verification/timing/results/20260908_sram_merge
```

该汇总检查日志 PASS、用例身份、输入 hash、traffic/dot、逐点周期一致性以及
顶层仿真时的 RTL hash，不会把缺失或诊断失败的日志算成通过。
综合 blackbox/Bender 和 DB 列表已补齐，clock uncertainty 未修改。

## 8. 合入后的 DC 启动检查

DC 在 `~/Makefile` 的 `enter_eda` 所使用的 `synopsys_workspace` 容器内运行。
普通 `make dc mc=1` 默认不开启 QBS/AKV，完整设计应在容器内执行：

```sh
cd /home/wangwy/openproject/ara_dsa/hardware
make dc mc=1 qbs=1 akv_v2=1 config=default ideal_dispatcher=0 sim_l2_mb=1
```

配置为 4 lane、VLEN=1024、CVA6 标量核、QBS、AKV-v2、1 MiB 宏实现 L2，
使用 TSMC 28 nm TT 0.9 V 25 C 库。时钟周期为 1 ns，setup uncertainty
为 0.15 ns；没有放宽约束来掩盖违例。预检确认 406 个源文件及所需开关，
当时包含 QBS payload 的 8x256 SRAM blackbox 和对应 DB；当前还需第 11 节的
8x128 权重宏，这两种 blackbox 和 DB 已接入工程。

首轮 DC T-2022.03-SP2 编译发现 `qbs_dot_array` 组合块中三条二维数组
嵌套 `default` 初始化报 `VER-294`。这不是输入端口缺省值或算术错误：
`product_d[4][8]`、`pair_sum_d[4][4]`、`quad_sum_d[4][2]` 均在后续
固定范围循环中逐元素无条件赋值。删除这三条冗余初始化即可避免该语法，
不改变任何元素的最终表达式、INT8 极值位宽、平衡加法树或流水级。

修正后重新运行 448 个 profile 用例、33 个 engine 用例、四类故障处理和
activation FILL/REUSE/RELEASE，全部通过。逐用例 PASS 行及周期与
`20260908_sram_merge` 记录完全一致。新增验证记录位于
`/tmp/ara_dsa_dc_compat_20260909/`，不是用旧 binary 代替当前源码回归。

完整设计继续编译时，还发现 AKV 的 `!&descriptor_byte_valid_q` 在 DC
中解析失败。改为显式的 `!(&descriptor_byte_valid_q)`，仍表示描述符的
字节有效位没有全部置一，不改变 fault 判断条件。该处修正后的 AKV engine
回归通过，覆盖 v1、v2、D64/D96/D128、分段 D256、行/列视图、尾块和故障。

启动前的旧报告、输出、运行目录及 filelist 已归档至
`/home/wangwy/openproject/ara_dsa_dc_runs/sram_348cbd50_20260909_003706/previous_reports_outputs_run_flist.tar`。
本次运行保留独立日志、源码快照、SHA256、开始/结束时间和返回码。
预检通过和进程启动均不等于时序收敛；面积与 slack 必须以综合完成后生成的
新报告为准，不能混用旧报告。

## 9. 共享输入对齐的面积优化验证

2026-09-14 的这轮改动只压缩写入数据选取网络，不增加流水周期，也不缩减
SRAM、权重双缓冲、M8 context、dot 吞吐或浮点精度。原来每个 adapter 有
1216 处单槽位 16 路字节选择树：payload 为 `2*3*4*32=768` 处，side metadata
为 `2*4*(20+36)=448` 处。生产路径现在使用共享旋转和布局连线，仍保留完整的
目标匹配、字节使能以及新槽位覆盖旧槽位的最终选择。这个数字是 RTL 结构计数，
不是综合后门数，也不能直接当作面积下降比例。

验证证据在 `verification/timing/results/20260914_qbs_stream_area/`。
修改前的对照为已经加入入口 FIFO 的版本，不是更早的寄存器缓冲版本。

| 验证项目 | 结果与范围 |
|---|---|
| 真实 adapter 布局前提 | 修改前、后均通过；每轮检查 152562 个权重字节、221679 个激活字节的源/目标关系 |
| 共享数据路由逐拍检查 | `QBS_STREAM_EQUIV` 通过；只在实际有效写入时与原选择树比较 |
| 格式、布局、尺寸矩阵 | 九类权重、row-major/R4、激活 row-major/M4/M8，共 81 组通过 |
| strobe、重复写与清空 | 256 种 strobe；非连续/重复流、FIFO 满后独立清空通过 |
| 连续流吞吐 | 81 组均无新增入口停顿；非连续测试仍为原来的 4 次停顿 |
| 周期信号文件 | 两个 adapter 各自抓取的首 128 个活动后周期与修改前逐项一致；不是全程波形等价证明 |
| TSMC SRAM 模型 | 相同矩阵通过；`+notimingcheck`，属于宏功能检查，不是 SDF 后仿 |
| 通用 payload 接口 | 任意逐字节目标的 110592 次对照通过，包含重复目标的优先级 |
| 完整 QBS 命令 | 33 个命令通过，周期逐点不变；另含四类原子故障及 activation context 生命周期检查 |
| 普通 RVV/交接 | `vfmacc`、`vwiden_overlap_edges`、AXPY 通过；4 个 QBS/10 个 AKV 命令交接通过 |

七个真实模型数据切片保留完整 K 维度，只裁剪输出行或输入列。计算结果、周期和
已有 traffic/dot 记录均与对照一致；这说明当前验证范围内没有用降低吞吐换取面积。
它不等价于声称所有模型均已重新运行，也不代表最终物理时序已经满足约束。

| Profile / 场景 | M | N | K | 修改前 engine cycles | 修改后 engine cycles |
|---|---:|---:|---:|---:|---:|
| Q4_K Decode | 1 | 32 | 1536 | 2287 | 2287 |
| Q4_K Prefill | 4 | 32 | 1536 | 7304 | 7304 |
| Q4_K Prefill | 8 | 16 | 1536 | 7742 | 7742 |
| Q4_K Prefill 尾块 | 7 | 16 | 1536 | 7716 | 7716 |
| Q6_K Prefill | 4 | 32 | 8960 | 42536 | 42536 |
| Q6_K Prefill | 8 | 16 | 8960 | 45090 | 45090 |
| Q6_K Prefill 尾块 | 7 | 16 | 8960 | 45076 | 45076 |

局部验证可以从仓库根目录运行，`BUILD` 应使用未占用的独立目录：

```sh
make -C verification/timing stream-check BUILD=/absolute/path/to/new-check
```

整机综合在验证全部通过后启动，目录为
`hardware/dc_runs/20260914_0917_qbs_stream_area/`。源文件、头文件、filelist 和
综合脚本均已复制到该目录；使用同一 EDA 容器、TSMC 库、8 核设置、1 ns 时钟
和 0.15 ns setup uncertainty。未修改或停止
`hardware/dc_runs/20260914_0521_qbs_ingress/` 中的旧综合。
本轮整机面积和时序尚待 DC 完成，暂不填入预计缩减值。

局部 adapter 对照在 `hardware/area_qbs_stream_20260914_oOlF3w/dc_local/`。
其 `--quick-reports` 只缩减局部报告数量、跳过昂贵的全寄存器 pin-pair 查询，
不改变综合约束或 compile 命令，也不作用于整机综合。局部报告只能与相同 wrapper
和约束的局部基线比较，不能直接替代整机层次面积。

## 10. 唯一提交计数与共享读窗口

### 10.1 面积减少的对象

2026-09-15 在 `630e16b3` 已有的入口流水、共享写入对齐和 SRAM 基础上继续压缩
控制及读选择网络。不合并两个权重 bank，不削减 M8 激活存储，不减少乘法器，
不改变九种 profile 的 ABI、FP32 累加顺序、命令提交或故障排空规则。

生产输入来自 `qbs_read_engine` 的带 tag 返回范围，或 activation context 的按块重放。
每个范围内 offset 随实际返回字节推进；调度器只为本轮所需的行/上下文发起一次范围。
同一个 block 的 context replay 在启动后即记录已发起，不能因 SRAM 尾部仍在排空而
再次启动。这些已有条件保证同一原生字节在一个 clear epoch 内至多提交一次。

### 10.2 为什么计数能判定完整

必须同时满足三条条件：映射仅接受合法范围内的字节、每个目标字节至多提交一次、
计数只在数据实际写入 SRAM 或 side metadata 时更新。对于大小为 B 的块，合法集合
恰好有 B 个字节；提交 B 个互不重复的合法位置，才等价于全部位置已就绪。

因此每行只需保存 `weight_committed_q[7:0]` 和
`activation_committed_q[8:0]`，分别能表示 0..210 与 0..292。每个 adapter
为 `4*(8+9)=68 bit`，两个为 136 bit；原 bitmap 为 `2*4*(210+292)=4016 bit`。
这不是整机寄存器总数，也不是最终面积比例：新的加法/计数逻辑仍占面积，公共统计计数器、
入口 FIFO、pending 和 payload SRAM 均保留。

旧 pending 与 FIFO 队首可能同拍提交，故每行增量覆盖两个 16-byte mask，共 0..32 byte。
位计数使用平衡加法树。SRAM 冲突留下的字节不增加计数，后续真正写入时再增加；
`complete` 仍要求 FIFO 和 pending 同时为空。clear 取消尚未提交的数据、复位本域计数，
不扫描 SRAM，也不清除另一域。

仿真保留 bitmap 作为独立契约检查，检测重复写和计数越界；`SYNTHESIS` 下生产实例不生成
该 bitmap。默认通用模式保留原逻辑，因而未来需要重复覆盖的调用者不能直接启用此参数。
这不是由软件 HINT 保证的条件，也不能通过假设 AXI 输入始终没有停顿来推导。

新命令在 INIT 周期先安装 profile，下一边沿清空旧存储状态。因此清空周期的完成输出不用于
推进计算，也不要求新旧实现对“旧块按新 profile 解释”的结果相同。对照检查始终比较 ready
及提交计数；完成位在本域非 clear 周期严格比较，并断言 profile 切换必伴随 clear。

### 10.3 共享读窗口解码

本小节记录收窄权重字宽之前的 256-bit 实现；当前窗口尺寸与对齐级数见第 11 节。

一个物理 wave 每行消费连续的 2、4 或 8 个元素。紧凑 decoder 先对每行 low plane、
high plane 和 activation 的 32-byte 窗口各做一次字节对齐，取出连续的八个候选字节。
五级固定字节旋转网络共享 `k_base[4:0]`，之后每个元素只需选择 nibble、2-bit 字段、
高位或 IQ4_NL 表项。Q4_0/Q5_0/IQ4_NL 的 low plane 仅 16 B，先用固定连线重复两次，
使高低 nibble 的两轮计算仍访问正确字节。

例如 Q6_K 的整数是 6-bit unsigned code 减 32。翻转其最高位后按 6-bit signed 扩展，
与减 32 严格等价，不需要给每个输出另放减法器。Q4_0、Q5_0 和 Q3_K 使用相同的
偏置二进制转换原理；Q4_K/Q5_K 的 affine 值、Q8_0 INT8、IQ4_NL 查表含义不变。
subgroup scale/min/bsum、FP 数据及返回顺序均沿用原路径。

窗口不是任意完整 block：输入 `k_base`、SRAM 返回窗口及 profile 必须属于同一次有效 issue。
非紧凑模式保留原生索引实现。独立对照覆盖九种格式、M1..4 物理 wave、1..4 row、
全部合法 K 起点和全零/全一/随机数据，共 176768 个组合；不声称形式化证明所有任意输入。

### 10.4 验证与面积证据

本轮运行根目录为 `verification/timing/build_area_20260915/`。四个局部 DC 均在独立源码和
脚本快照中执行：`dc_adapter_before`、`dc_adapter_after`、`dc_profile_before_snapshot`、
`dc_profile_after`。同一对照使用相同 wrapper、库、1 ns 周期、0.15 ns uncertainty 和编译
设置；adapter 后版启用 `UniqueInputBytes`，前版不启用。不改之前整机综合的输入或输出。

展开报告已经确认后版每个 adapter 只有上述 32+36 位完成计数。实际面积以各自
`area.rpt` 为准，不能将局部面积直接乘系数当作已完成的整机结果。后续时序违例分析独立进行。

已归档的功能证据在
`verification/timing/results/20260915_qbs_compact_area/`；`commands.csv` 和 `real.csv`
保存逐点新旧周期，`summary.json` 保存输入、日志和源码 hash。局部 DC 未完成时，其中的
`local_area` 仅记录运行状态，不填面积结果。汇总工具拒绝缺失 PASS、不同输入、不同用例或
周期/流量不一致的日志，也检查局部 DC 库和综合选项是否一致。

| 本轮验证 | 已完成结果 |
|---|---|
| 改动前的唯一提交探针 | 33 命令及故障测试，共 52576 个权重、47360 个激活提交字节，无重复 |
| 新旧 decoder | 176768 个有效输入组合完全一致 |
| 唯一提交 adapter | 81 组布局/尺寸、256 种 strobe，跨块、非连续输入、满 FIFO 清空均通过 |
| 默认通用 adapter | 同一格式矩阵及重复覆盖测试通过，保留去重语义 |
| 连续流 | 两种 adapter 模式各 81 组，均无新增入口停顿 |
| 完整 QBS engine | 33 个命令、四类原子故障、FILL/REUSE/RELEASE 通过，33 点周期不变 |
| `SYNTHESIS` 仿真 | 去掉生产影子 bitmap 后重复 33 命令及四类故障，通过 |
| TSMC 宏功能 | 相同唯一提交矩阵通过；关闭 timing checks，不是 SDF 后仿 |
| 普通 RVV | `vfmacc`、`vwiden_overlap_edges`、AXPY 通过 |
| QBS/AKV owner 交接 | 4 个 QBS、10 个 AKV 命令及普通 RVV 交接通过，traps=0 |

| 真实数据切片 | M | N | K | 修改前 cycles | 修改后 cycles |
|---|---:|---:|---:|---:|---:|
| Q4_K Decode | 1 | 32 | 1536 | 2287 | 2287 |
| Q4_K Prefill | 4 | 32 | 1536 | 7304 | 7304 |
| Q4_K Prefill | 8 | 16 | 1536 | 7742 | 7742 |
| Q4_K Prefill 尾块 | 7 | 16 | 1536 | 7716 | 7716 |
| Q6_K Prefill | 4 | 32 | 8960 | 42536 | 42536 |
| Q6_K Prefill | 8 | 16 | 8960 | 45090 | 45090 |
| Q6_K Prefill 尾块 | 7 | 16 | 8960 | 45076 | 45076 |

表中是完整 QBS engine 仿真周期，不是整个模型的端到端周期。每个切片使用相同真实模型
数据与完整 K，输出值由测试中的参考结果检查；阶段计数及 traffic/dot 记录也逐项一致。
本轮目标是保留这些周期的同时减少状态与选数逻辑，不将它描述成软件或吞吐优化。

复验时各 `BUILD` 使用独立目录；`AREA_REFERENCE` 默认固定为本轮前版 `630e16b3`：

```sh
make -C verification/timing decoder-check BUILD=/absolute/path/to/decoder
make -C verification/timing unique-adapter-check BUILD=/absolute/path/to/unique
make -C verification/timing stream-check BUILD=/absolute/path/to/generic
make -C verification/timing area-engine-check BUILD=/absolute/path/to/engine
make -C verification/timing area-engine-check AREA_DEFINES=+define+SYNTHESIS \
  BUILD=/absolute/path/to/synthesis-check
```

局部面积报告完成后可重新收集至新的归档目录，不覆盖本次功能记录：

```sh
python3 verification/timing/collect_qbs_compact_area_results.py \
  --run verification/timing/build_area_20260915 \
  --output verification/timing/results/20260915_qbs_compact_area_mapped
```

## 11. 权重 SRAM 收窄为 128 bit

### 11.1 改什么，不改什么

2026-09-15 在当前工作区已有的时序流水、共享写入对齐、唯一提交计数和共享读解码
基础上，只调整权重的物理存储组织。比较基线是修改前保存的工作区源码快照，包含
当时尚未提交的优化，并非直接取 `630e16b3` 的干净检出版本。

| 每行存储 | 修改前逻辑组织 | 当前逻辑组织 | 当前物理宏 |
|---|---:|---:|---|
| 权重低位 | 4 x 256 bit | 8 x 128 bit | 8 x 128 bit |
| 权重高位 | 2 x 256 bit | 4 x 128 bit | 8 x 128 bit，使用前四字 |
| 激活 | 8 x 256 bit | 8 x 256 bit | 原 8 x 256 bit，不变 |

所选 UHD 单端口编译器的合法深度从 8 开始，因此原权重低位和高位分别只用了
8x256 宏的一半、四分之一地址。改为 128-bit 宏后，低位宏全部使用，高位宏使用一半。
激活的 256 B 已经占满原宏；本轮不改为 16x128，不增加其地址译码和分字处理。
逻辑 payload 总量仍是 3584 B，24 个物理宏合计容量从 6144 B 降至 4096 B。

ISA、profile 编号、原生块布局、软件二进制、AXI beat 宽度均不变。九种格式仍使用
同一套计算资源；权重双缓冲、M8 激活上下文和之前的时序流水全部保留。

### 11.2 为什么不必降低计算吞吐

一个物理 wave 每个上下文计算 2、4 或 8 个 K 元素，K 起点按照对应步长推进。
每行、每个权重 plane 实际读取最多八个连续字节；合法起点不会让这一组所需字节
跨越 16-byte 窗口。因而不需要把一次计算拆成两次 SRAM 读取。

实现同步调整了三个位置：

- **写入**：权重按 16 B 划分 SRAM 字，激活仍按 32 B；两个输入仲裁槽的总数据宽度
  仍为 256 bit，因为它们承载两个 16-byte beat，不是一个权重 SRAM 字。
- **读地址**：依据 profile 的原生压缩布局，把原来一个 32 B 字拆成两个 16 B 字。
  例如 Q6_K low 地址为 `{k[7], k[5:4]}`，high 地址为 `{1'b0,k[7],k[4]}`。
  Q4_0/Q5_0/IQ4_NL 的 low 始终读第零字，高低 nibble 由 K 位置选择。
- **计算入口**：weight window 从 256 bit 改为 128 bit，权重对齐旋转从五级变为四级。
  激活保留 256 bit/五级。符号恢复、整数 dot、scale/min/bsum 修正和 FP 累加顺序不变。

需要特别检查的是写入，而不是算术：一个未对齐的 16-byte beat 可能跨两个权重字。
已有 pending 和两项入口 FIFO 保留未提交字节，下拍再和新 beat 中落在同一字的部分
合并。跨原生块、跨 plane 或不连续输入仍按实际冲突施加 backpressure，不通过丢字节
或提前标记 complete 来保证吞吐。下表中的连续流和 Q6_K Decode 是对此的专项检查。

### 11.3 宏接入与面积口径

新增宏为 `TS1N28HPCPUHDSVTB8X128M1SWBSO`，目录为共享工艺库下的
`mem/ts1n28hpcpuhdsvtb8x128m1swbso_170a/`，具备 VERILOG、LEF、NLDM 和 TT DB。
DB 由 EDA 容器中的 Library Compiler 生成；新增工程 blackbox，补齐 `Bender.yml`
和 `synopsys_dc.setup.env`。本轮在容器中完成 adapter 的 DC analyze/elaborate/link，
确认链接到实际 8x128、8x256 库单元；没有启动新的整机 compile。

| TT 0.9 V / 25 C 宏面积 | 修改前 | 当前 |
|---|---:|---:|
| 单个权重宏面积，um² | 4601.1245 | 2520.1773 |
| 16 个权重宏合计，um² | 73617.9920 | 40322.8368 |
| 8 个激活宏合计，um² | 36808.9960 | 36808.9960 |

仅权重宏的库面积合计减少 **33295.1552 um²，即约 0.0333 mm² / 45.23%**。
这是已生成宏的 Liberty 单元面积差，不是整机减少 45.23%，也不是已完成映射后的
QBS 总面积。字宽变化还会改变外围译码和选择逻辑，最终净面积和时序需新一轮综合确认。
当前运行中的 `hardware/dc_runs/20260915_control_timing/` 源码快照和输出未被修改。

### 11.4 功能和性能实测

独立运行目录：`hardware/weight128_20260915_97vc3G/`。
紧凑归档：[`verification/timing/results/20260915_weight128/`](../../verification/timing/results/20260915_weight128/)。
其中 `commands.csv`、`real.csv` 保存逐点周期；`summary.json` 保存输入、源码、库和日志
SHA256，并区分宏面积、局部展开和未执行的整机物理验证。

| 检查 | 结果 |
|---|---|
| 新旧 decoder | 61952 个合法 issue 组合通过，九种 profile、1..4 row、M1..4 物理 wave |
| 通用 payload 仲裁 | 独立字节数组参考模型 110592 次检查通过，含重复目标、掩码及覆盖优先级 |
| 真实 TSMC 宏模型 | 九种格式和三类布局组合共 81 组、256 种 strobe 通过 |
| 连续/非连续写流 | 连续矩阵 81 组 stalls=0；非连续及重复测试仍为 4 次停顿；满 FIFO 清空通过 |
| 完整命令 | 33 个命令、四类原子故障、FILL/REUSE/RELEASE 通过，33 点周期不变 |
| 生产综合条件 | `SYNTHESIS` 下去掉仿真影子 bitmap，重复命令及故障检查通过 |
| 普通 RVV 与交接 | `vfmacc`、`vwiden_overlap_edges`、AXPY、QBS/AKV handoff 均通过，handoff traps=0 |
| DC 接入 | analyze/elaborate/link 通过，128/256-bit 宏均解析成功；非完整综合结果 |

61952 与第 10 节旧测试的 176768 不是同一计数口径：本次独立 decoder 对照只枚举
engine 真正发出的按 2/4/8 对齐的 K 起点。完整块到读窗口的地址映射还由 SRAM adapter
原生字节参考检查覆盖，不能只凭窄窗口 decoder 的输入对照判断地址映射正确。
宏检查使用 `+notimingcheck`，属于功能仿真，不是带 SDF 的门级时序验证。

验证中另修正了旧 bind checker 的 INIT 观察点：新 profile 已安装、clear 尚未完成时，
不比较即将被清掉的旧块 complete。逐字节状态和提交计数仍检查，非 clear 周期的 complete
仍严格检查。这只修改测试观察语义，未放宽生产 RTL 的 complete 条件。

真实数据取自 Qwen2.5-1.5B Q4_K_M 的 `attn_q` 和 `ffn_down` 捕获，分别含 Q4_K、Q6_K
权重。保留完整 K，只裁剪输出行和输入列；测试检查计算结果，并逐项比较 phase、traffic、
dot 和 prefetch-wait 计数。

| 真实数据切片 | M | N | K | 修改前 cycles | 当前 cycles |
|---|---:|---:|---:|---:|---:|
| Q4_K Decode | 1 | 32 | 1536 | 2287 | 2287 |
| Q4_K Prefill | 4 | 32 | 1536 | 7304 | 7304 |
| Q4_K Prefill | 8 | 16 | 1536 | 7742 | 7742 |
| Q4_K Prefill 尾块 | 7 | 16 | 1536 | 7716 | 7716 |
| Q6_K Decode | 1 | 32 | 8960 | 17813 | 17813 |
| Q6_K Prefill | 4 | 32 | 8960 | 42536 | 42536 |
| Q6_K Prefill | 8 | 16 | 8960 | 45090 | 45090 |
| Q6_K Prefill 尾块 | 7 | 16 | 8960 | 45076 | 45076 |

八个切片均为 QBS engine 周期，不是端到端模型时间。Q6_K Decode 原有的
`prefetch_wait=4095` 同样未增加，不能将其写成无加载等待。本次结论是这些代表点
没有因收窄权重存储而退化，不宣称所有模型、格式和输入时序下都已穷举验证。

局部复验可使用第 7 节的双宏模型命令，并在各自独立的 `BUILD` 中执行：

```sh
make -C verification/timing decoder-check BUILD=/absolute/path/to/weight128_decoder
make -C verification/timing payload-check BUILD=/absolute/path/to/weight128_payload
make -C verification/timing sram-engine-check BUILD=/absolute/path/to/weight128_engine
make -C verification/timing area-engine-check AREA_DEFINES=+define+SYNTHESIS \
  BUILD=/absolute/path/to/weight128_synthesis
```

VCS 在宿主机运行，MC/Library Compiler/DC 在 `synopsys_workspace` 容器运行。
本轮没有覆盖既有仿真或综合目录，也没有更改 clock uncertainty。

## 12. 上下文 SRAM 和计算状态压缩

### 12.1 保留容量和访问带宽，减少宏外围开销

本轮继续在第 11 节的 128-bit 权重宏版本上修改，不撤回之前的流水和时序优化。
这里的 QBS activation context 是用于跨命令 FILL/REUSE 的存储，**不是**第 11 节
计算块内的 8x256 激活 payload 宏；后者仍然不变。

| 存储 | 必须保留的逻辑容量 | 修改前物理组织 | 当前物理组织 | 宏库面积减少，um² |
|---|---:|---|---|---:|
| QBS activation context | 4672 B | 4 个 64x256 | 2 个 76x256 | 13102.453 |
| AKV 行上下文 | 6144 B | 4 个 64x256 | 2 个 96x256 | 11329.633 |
| AKV K/V 上下文 | 32768 B | 16 个 64x256 | 8 个 128x256 | 33972.484 |
| 合计 | 43584 B | 24 个宏 | 12 个宏 | 58404.570 |

三类存储的逻辑 bank 数和每拍端口宽度不变。QBS 每个奇偶 bank 需要 146 个
128-bit 行，打包为 73 个 256-bit 物理字，使用编译器可生成的 76 深度宏。
地址右移一位选择物理字，最低位选择半字，写使能按 byte mask 选择对应半字。
非二次幂深度不使用取模寻址，越界地址不能激活宏。

AKV 行上下文每个 bank 恰好需要 96 个 256-bit 字，直接接一个 96x256 宏。
K/V 上下文的八个 bank 分别从两个 64x256 换成一个 128x256。最后一种并未减少
数据容量，而是减少重复的译码、外围电路和 bank 内的宏输出选择器。
已有的未对齐写入、跨字处理、行读取、列 gather 和 backpressure 均保留。

新宏使用同类 TSMC 28 nm UHD SVT 库。MC 和 Library Compiler 在 EDA 容器中生成
宏及 TT DB，工程增加对应 blackbox、filelist 和 link library。
上表是 Liberty 宏单元面积差，合计约 **0.0584 mm²**，不是整机映射后的净面积差。
加上第 11 节的权重宏，两轮宏面积合计减少约 0.0917 mm²；外围逻辑和布线效果仍需
全局综合确认。更深宏的访问时间与原宏不同，因此不能仅凭无额外周期就声称主频不变。

### 12.2 按共享关系和生命周期减少寄存器

`qbs_profile_engine_int` 原来为每个 4x4 stream 都保存一份 subgroup 元数据。
实际 bsum 只随四个激活上下文变化，scale/min 只随四行权重变化，last 标志对整个
subgroup 相同。当前每个计算 context 保存四份 bsum、四份 scale/min 和一个 last，
dot 值仍为每条 stream 独立保存，不共享计算结果。

安全条件是：同一个 context 的上一组元数据必须已被全部 correction 输入级捕获，
才允许下一组覆盖。RTL 增加断言检查尚未消费的 slot；若最后消费与新组写入同拍发生，
correction 输入级读取的是写入前的寄存器值，不会混入新组元数据。

辅助累计值从有符号 32 bit 缩为 26 bit。即使不假设 Q8_K bsum 是规范量化生成的，
保留完整 signed-16 输入，最坏绝对值仍为：

```text
16 groups * 32768 * 63 = 33030144 < 2^25
```

因此 signed-26 足够；加法保留第 27 位检查溢出，接口仍符号扩展为 32 bit。
并未降低输入精度，也没有截断 FP 运算结果。

`qbs_fp_accumulator` 将 activation scale 和 accumulator addend 合并为一个
32-bit 工作寄存器。scale 的最后一次乘法**返回后**，该寄存器才改装 addend：
首块为零，其余从 accumulator bank 读取。仿射格式需等 min-scale 乘法返回，
不能在第一次 scale 乘法后提前覆盖。一个 live entry 独占对应 accumulator，
因此推迟读取不会遇到其他 entry 修改同一累计值。正项 FMA 完成后，工作寄存器保存
中间和，再供负项 FMA 使用。FP 运算顺序、舍入、entry 数量和发射规则均不变。

| 逻辑压缩 | 声明状态位减少 |
|---|---:|
| subgroup 元数据去重 | 750 bit |
| auxiliary subtotal 收窄 | 192 bit |
| FP entry 工作值复用，计入新增 first-block 标志 | 496 bit |
| 合计 | 1438 bit |

这是 RTL 声明位数差，不等于最终减少 1438 个触发器；综合可能已优化部分冗余位。
压缩没有减少并发 context、结果 entry 或访存端口，也没有增加架构可见等待周期。

### 12.3 验证口径与全局综合

本轮运行目录为 `hardware/context_area_20260915_dJqcsu/`。
新旧比较的旧版取自修改前工作区快照，保留原有未提交的时序和权重宏修改。
五个修改模块均建立逐周期对照：检查有效输出数据、ready/valid、结果提交及计数器。
这是动态对照，不是形式等价证明。

- QBS 原生 profile 矩阵覆盖九种格式、M1..4、1..4 行、边界数据及重复累加，448 点。
  另用同一矩阵加入结果接收停顿，检查元数据释放和 FP entry 生命周期。
- 完整 engine 覆盖 33 个命令及四类原子故障，使用实际 CompactRead 计算路径；
  本轮前后命令周期相同。
- QBS context 使用真实厂商 Verilog 宏，覆盖最大深度、两轮 refill、逆序 replay、
  对齐边界、backpressure、abort/release；有效字节严格比较，X/Z 不能冒充正确数据。
- AKV 使用真实宏及旧版逐周期对照，覆盖 D64/D96/D128、分段 D256、行列视图、
  尾块、计数器、参数校验及故障。
- 普通 RVV 回归包含 `vfmacc`、`vfredusum`、`vwiden_overlap_edges` 和 AXPY。
- 第 11.4 节八个真实模型切片重新运行，输入文件 SHA256 相同，周期、phase、traffic、
  dot 和 prefetch-wait 均与该节数值一致。完整 K=1536/8960 不缩短。

宏模型使用 `+notimingcheck`，验证功能与同步访问拍序，不属于 SDF 时序仿真。
本轮**不运行局部 DC**。功能、周期和源码哈希检查全部通过后，再以独立的 RTL/脚本
快照启动一次整机综合，保留 1 ns 时钟、0.15 ns setup uncertainty 和原核数设置。
既有综合的快照、日志、报告和网表不覆盖。

紧凑结果归档位于
[`verification/timing/results/20260915_context_area/`](../../verification/timing/results/20260915_context_area/)。
`summary.json` 区分动态等价、功能测试、库面积差和待完成的整机 PPA；
`real.csv` 与 `commands.csv` 保存逐点周期，宏和源码都有 SHA256 可核查。
