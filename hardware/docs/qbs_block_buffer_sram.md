# QBS Block Buffer 的 SRAM 接入与验证

## 1. 范围与结论

本工作在 `ara_dsa_sram` 分支完成，起点为 `be1487b5`。原来的
`ara_dsa` 工作目录和 `ara_dsa_timing` 工作目录均不修改。

目的不是增加算术单元，而是把 QBS 本地块缓冲中适合存储器实现的压缩
payload 从寄存器移到单端口同步 SRAM。保留当前九种权重 profile、
M1--M8、尾块、权重双缓冲、激活复用及故障处理，不改 ISA、数值计算
顺序、dot array、FP accumulator 或 AKV 数据通路。

这是一个已完成代表性功能验证的存储实现候选，**还没有合入 `ara_dsa`**。
Q4 的三个真实 Prefill 点周期不变；Q4 Decode 增加约 1.58%；Q6 的三个
真实 Prefill 点增加约 1.10%--1.16%。不能把它描述为无性能代价的替换。
尚未运行 DC、PNR、面积、时序或功耗评估，也尚未完成 FPGA 存储映射。

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

因此本次同时处理了读窗口、写入拆分、完成资格以及上游 backpressure。

## 3. 数据划分

每个 adapter 内部有四个行/上下文，每行分三个独立 payload plane。
两个 adapter 保持原来的权重 ping-pong 和八个激活上下文。

| 数据 | 每行/上下文逻辑组织 | 总银行数 | 总逻辑容量 |
|---|---:|---:|---:|
| 权重低位 payload | 4 x 256 bit | 8 | 1024 B |
| 权重高位 payload | 2 x 256 bit | 8 | 512 B |
| 激活 INT8 payload | 8 x 256 bit | 8 | 2048 B |
| 合计 SRAM payload | 单端口、byte write enable、同步读 | 24 | 3584 B |

仍用寄存器保存：

- 每行最多 20 B 权重元数据，包括 scale、min、Q5_0 的高位辅助位等。
- 每上下文最多 36 B 激活元数据，包括 scale 和 Q8_K 的 16 个 bsum。
- 原有逐字节 valid、去重计数、银行归属和完成状态。
- 权重和激活各自的一个未完成写 beat。两个 adapter 总共新增 634 bit
  暂存数据/控制状态，包括 valid，不是一个可无限积压的队列。

这里的 3584 B 是逻辑 SRAM 容量，**不是节省的面积**。TSMC 映射使用
`TS1N28HPCPUHDSVTB8X256M1SWBSO`，深度 2/4 的银行只使用部分物理地址。
24 个宏的物理 bit 容量合计 6144 B；端口、外围电路和字节有效状态都有代价。
不能直接用寄存器 bit 数推导最终面积或功耗。

## 4. 各模块如何配合

### 4.1 `qbs_payload_sram.sv`

定义一个 256-bit、单端口、按字节使能写入、读延迟一周期的存储器。
普通 RTL 仿真使用 `tc_sram`；`TARGET_SRAM_MC` 使用上述 TSMC 宏。
payload 不复位，读数据只能在当前块的 valid/complete 条件满足后被消费。

物理地址仍检查逻辑深度，不允许因为物理宏有 8 个字就访问逻辑银行未分配的地址。
FPGA 后续可使用工程已有的 `tc_sram` FPGA 实现，但本次没有验证 VCU118 映射。

### 4.2 `qbs_payload_buffer.sv`

把原生块 offset 转换为 `(plane, word, byte lane)`。所有格式仍保持压缩
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

模块每周期为每个物理银行选一个写地址。如果一个输入 beat 还触及该银行的
另一个字，返回未写入字节的 mask，由 adapter 保存并在下一周期完成。
不同银行可以同时写，权重与激活之间不共用写端口或暂存状态。

对 decoder 的输出仍保留原生字节索引，减少格式解码的变化，但这只是一个
**同步读窗口视图**：payload 字节由 SRAM 输出的当前 32-byte 字重复布线，
并不是把整个块又复制回寄存器。只有当前 K 索引需要的 payload 有效；
不允许其他使用者把这个接口当作可任意寻址的完整块。

### 4.3 `qbs_block_adapter.sv`

沿用原来的 R4/M4/M8 字节映射及完整范围检查。先检查原生 offset 和
行/上下文是否合法，再截取局部地址位宽，不能先截断再判界。

数据进入某个 SRAM 字或元数据寄存器时才设置对应 byte-valid，并增加
`accepted_*_bytes_o`。这些字段在本模块指**已写入本地存储的唯一字节数**，
不再保证和输入 beat 握手同周期更新。重复字节仍允许覆盖数据，但不重复计数。

一次拆分写的流程如下：

1. 输入 valid/ready 握手，先写该周期能接收的字节。
2. 其余字节连同原 offset、row/context、group 标志保存到该域的 pending beat。
3. 下一周期停止接收该域的新 beat，完成剩余字节写入；另一域仍可继续工作。
4. pending 清除后才能重新接收新 beat。

即使剩余字节只是重复覆盖，也不能让 complete 提前使能计算。
clear 优先于写入，清除有效位和 pending，不扫描清零整个 SRAM。
断言检查第二周期能全部写完、无同银行读写碰撞，以及 read 不与 clear/pending 冲突。

### 4.4 `qbs_profile_engine_int.sv`

只新增现有 issue 阶段的 `buffer_read_valid_o` 和 `buffer_read_k_base_o`。
不增加 dot pipeline 级数，不改变 correction 或 FP 的算术顺序。

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

## 5. 实测结果和性能代价

以下均为 QBS engine 的 command cycles，不是整个 SoC 的 kernel 周期，
也不是模型 tokens/s。输入来自真实 Qwen2.5-1.5B 捕获数据；保留完整 K，
只缩小输出行数和 token 数。

| 数据切片 | M x N x K | 寄存器版 | SRAM 版 | 周期增加 |
|---|---:|---:|---:|---:|
| Q4 Decode attn_q | 1 x 32 x 1536 | 2219 | 2254 | 1.58% |
| Q4 Prefill attn_q | 4 x 32 x 1536 | 7200 | 7200 | 0 |
| Q4 Prefill attn_q | 8 x 16 x 1536 | 7638 | 7638 | 0 |
| Q4 Prefill attn_q 尾块 | 7 x 16 x 1536 | 7612 | 7612 | 0 |
| Q6 Prefill ffn_down | 4 x 32 x 8960 | 41939 | 42427 | 1.16% |
| Q6 Prefill ffn_down | 8 x 16 x 8960 | 44493 | 44981 | 1.10% |
| Q6 Prefill ffn_down 尾块 | 7 x 16 x 8960 | 44479 | 44967 | 1.10% |

七个点的 dot cycles、输入 payload 字节数、range 数量均未变化。
Q4 Decode 的 activation-load 阶段从 179 增到 214 cycles，增加 35；
逐周期探针恰好观察到 35 个 activation pending 周期。权重 pending 为 0。
原因是原生 Q8_K 的 4-byte scale 使连续 AXI 回数在分离后的量化数组中
跨 SRAM 字，并非 dot 吞吐或计算结果发生变化。

Q6 M4 的 weight-load 阶段从 1855 增到 2343 cycles，增加 488；
activation、dot 和总访存量不变。compute/overlap 的分类比例也随权重投放
时机改变，不能把 overlap 数值增大单独解释为性能提升。

另有 33 个较短、功能导向的 engine 点。其中个别 row-major 点的相对
退化更明显，例如 Q6 M3/N3/Kblocks2 从 529 增到 584 cycles，约 10.40%。
不能只列出大点中约 1% 的代价，便声称所有形状都几乎不受影响。

因此当前决定是：保留独立分支，不覆盖已验证的高性能寄存器版。
若继续优化，应首先分析连续回数的写合并，避免同一 SRAM 字被相邻 beat
反复分两拍写入，而不是增加算术单元或放大 timeout。写合并仍必须支持
不连续 offset、重复 strobe、clear、M8 和权重/激活同时写入。

## 6. 验证范围

- 448 个 profile 用例：逐步比较解码量化值、subgroup、整数结果、FP 结果和 fflags。
- 81 组 adapter 配置：九种 profile，M1--M8，R4/row-major，M4/M8 激活布局。
- 全部 65536 种 strobe，重复覆盖、不同 beat 长度、并发写和 clear/pending 取消。
- 与 `be1487b5` 寄存器版并行对照：pending 排空后比较 byte-valid、计数和 complete；
  每个实际读取窗口比较量化值、scale、min、bsum 等解码输出。
- 33 个完整 engine 用例、四类 fault，以及激活缓存 FILL/REUSE/RELEASE。
- 七个真实模型数据切片，明确比较 command cycles 和 traffic。
- 顶层普通 RVV/QBS/AKV 交接：4 个 QBS、10 个 AKV 命令，程序检查通过且无 trap。
- `SYNTHESIS` 宏下的 VCS 编译和功能测试。这仅验证相应代码分支，不是 DC 综合。
- 真实 TSMC 8x256 模型的功能读写验证。零延迟 RTL 会触发宏的 hold notifier，
  因此该测试显式使用 `+notimingcheck`，不构成物理时序验证。

测试未覆盖全模型长时间运行、全量随机 RVV 回归、FPGA XPM 实现和带 SDF
的门级时序仿真。不可将代表性通过扩大为所有工作负载和所有物理实现均已验证。

## 7. 复现

在本 worktree 的 `verification/timing` 中：

```sh
make sram-check sram-engine-check BUILD=/tmp/qbs_sram_check RUN_TIMEOUT=300
make adapter-baseline-engine-check BUILD=/tmp/qbs_sram_check \
  BASELINE_ROOT=/home/wangwy/openproject/ara_dsa RUN_TIMEOUT=300
```

第二条要求参考 worktree 的 HEAD 是 `be1487b5`，相关 RTL 没有未提交修改。
`adapter-check` / `adapter-engine-check` 已转到新的握手及窗口感知测试。
旧完整数组的 cycle miter 仅供历史实现参考，不能直接用于 SRAM 窗口接口。

```sh
make -C ../qbs rtl-profile-check \
  RTL_BUILD=/tmp/qbs_sram_profile RTL_RUN_TIMEOUT=300

make sram-check BUILD=/tmp/qbs_sram_macro RUN_TIMEOUT=300 \
  SRAM_DEFINES='+define+TARGET_SRAM_MC +notimingcheck' \
  SRAM_EXTRA_SOURCES=/home/wangwy/ara/backend/library/mem/ts1n28hpcpuhdsvtb8x256m1swbso_170a/VERILOG/ts1n28hpcpuhdsvtb8x256m1swbso_170a_tt0p9v25c.v
```

真实数据入口为 `verification/qbs/run_adaptive_real_rtl.sh`，通过
`QBS_ADAPTIVE_RTL_SIMV` 和 `QBS_ADAPTIVE_RTL_RESULT_DIR` 指定独立 binary/结果目录。
顶层入口为 `verification/akv/run_current_handoff.py --output <hardware下新目录>`。
后台运行时保留 source hash、binary hash、返回码和日志，不能覆盖其他工作的结果。

本机结果根目录：`/tmp/ara_dsa_sram_20260908/`；
顶层结果：`hardware/sram_handoff_20260908/`；
可版本管理的紧凑结果在 `verification/timing/results/20260908_sram/`。
综合 blackbox/Bender 和 DB 列表已补齐，但没有启动综合或修改 clock uncertainty。
