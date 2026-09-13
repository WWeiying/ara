# 从 timing worktree 移植的无新增流水级优化

## 1. 范围和基准

第一批以 `ara_dsa` 的 `b07e194deb4bc8cc88cc26cb1266893b9e92612d` 为比较基准，
借鉴 `ara_dsa_timing` 中的 QBS 状态压缩和 ALU 算术改写。
来源包含 `3349cf83` 之前的已提交工作，以及该 worktree 的 ALU 未提交改动。
不是将旧 worktree 的文件整体覆盖到当前设计。

第一批只修改三个 RTL 模块，已提交为 `7b7c3de0`；第 8 节记录在此基础上的接收路径优化。

| 模块 | 本次内容 | 保持不变的部分 |
| --- | --- | --- |
| `qbs_fp_accumulator` | 中间数据复用、缩短 FP tag | FP 微操作顺序、RNE 舍入、仲裁、128 项最终结果存储 |
| `qbs_profile_engine_int` | 元数据按行/context 保存、复用最终 subtotal、收窄有界算术 | 两个 tile context、M8 两波处理、短尾块修正排空、点积流水级 |
| `simd_alu` | 平均加减、窄化舍入和饱和的组合改写 | 指令语义、SEW、vxrm、结果位置、输入输出接口 |

没有移植 SRAM 读延迟、额外点积流水级、Dispatcher/lane 新队列、乘法重定时、
VFPU 操作数旁路 FIFO，或删除 ready/范围检查的修改。
当前 AKV、激活 context replay、共享读通道 fault drain 和所有指令编码保持不变。

## 2. 为什么可以复用 QBS 浮点中间寄存器

一个 FP entry 同时最多发出一个微操作。`entry_inflight_q` 置位以后，调度器不会
再次选择该 entry；结果返回后才推进其状态。利用这个不变量，可以让结果覆盖已经
结束使用的输入，而不增加等待周期：

| 同一存储位置 | 最初保存 | 后续保存 | 覆盖条件 |
| --- | --- | --- | --- |
| dot | 整数 dot | 转换后的 FP32 dot | I2F 已完成 |
| aux | 整数 correction sum | 转换后的 FP32 correction sum | I2F 已完成 |
| scale | 权重 scale | 权重 scale × 激活 scale | MUL 已完成 |
| min scale | 权重 min scale | min scale × 激活 scale | MUL 已完成 |
| accumulator | 前一 block 的累加值 | dot FMA 的中间结果 | FMA 已完成，且还需 affine correction |

激活 scale 仍独立保存，因为两个 scale MUL 都可能使用它。不同 entry 的存储不共享。
最终 accumulator 仍然是 8 bank × 16 row 的 FP32 结果数组。

FP tag 从 `{state, slot}` 的 7 bit 改为 4-bit slot。返回时读取对应 entry 的状态。
这不是用 FIFO 猜返回次序：每个结果仍带 slot，可以对应不同延迟的 FP 单元。
安全前提是 entry 在微操作完成前不能改变状态或被重新分配。
仿真仍保存 issued-state 影子值，并检查返回时状态一致、entry 有效且在飞。
影子值位于 `ifndef SYNTHESIS` 中，不计入硬件。

本模块声明的数据寄存器减少 `5 × 32 × 16 = 2560 bit`，不含 tag 缩短带来的变化。
这只是 RTL 状态位数，不是 DC 实测寄存器数量或面积结果。

## 3. QBS 整数路径的状态为什么不必重复保存

一个局部 stream 的编号是 `row × 4 + local_context`。
权重 scale/min 只依赖 row，激活 bsum 只依赖 local context；
不需要在 16 个 stream 的流水元数据中各保存一份。
本轮保持 decoder 的接口不变，在寄存器入口按 row/context 提取，并断言有效 stream
的数据确实满足这种重复关系。以后增加 profile 时，这个断言会检查共享条件是否仍成立。

block 的浮点 scale 在第一拍 decode 时保存到其 tile context，直到该 context 的结果
排空前保持不变。两个 tile context 分别保存，不能用一份全局寄存器替代。
M8 的 `start_context_base_i` 仍随结果传播，用于区分前四个和后四个激活上下文。

最后一个 subgroup 完成后，`subtotal_dot_q` 和 `subtotal_aux_q` 已是最终整数结果。
原来的 result 数组只是再复制一次，因此改为用 `result_pending_q` 标记 subtotal 可输出。
只有所有结果都握手完成，context 才能重新分配。新增断言禁止修正逻辑覆盖待消费结果，
也禁止在结果尚未排空时装入下一份 block 元数据。

## 4. 位宽的依据和刻意保留的余量

| 数据 | 原位宽 | 当前位宽 | 依据 |
| --- | ---: | ---: | --- |
| 未缩放 subgroup 部分和、slot dot | 32 | 21 | 最长 subgroup 为 32 个 INT8 乘积；正极值可达 524288 |
| block dot subtotal | 32 | 28 | 九种 profile 中 Q6_K 给出最宽界限，最低可到 -134217728 |
| min 字段 | 8 | 6 | 当前解码范围为 0–63 |
| dot correction 乘积 | 隐式 48-bit 表达式 | 29 | 21-bit 有符号 dot × 8-bit 有符号 scale |
| dot correction 加法 | 48 | 30 | 保留 guard bits 后检查，才写回 28-bit subtotal |
| bsum/aux | 16 | 16 | 保留全部编码位，不额外假定输入一定是规范量化器生成 |
| aux subtotal | 32 | 32 | 保持已有行为，不照搬 timing 分支的更激进收窄 |
| aux correction 乘积、加法 | 隐式 48-bit 表达式 | 23、33 | signed 16 × unsigned 6，再与 signed 32 subtotal 相加 |

例如 Q6_K 单元素最大量级来自 `q∈[-32,31]`、`a∈[-128,127]`、`s∈[-128,127]`。
一个 block 有 256 个元素，负极值为 `256 × (-32) × (-128) × (-128) = -2^27`；
正极值小于 `2^27`。其余当前 profile 的界限更小。
累加发生在每个 block 内；跨 block 的累加仍走 FP32，不能把全模型的 K 直接乘到此界限上。

`verification/timing/test_qbs_bounds.py` 检查九种 profile 的整数边界及 correction guard bits。
RTL 检查每次写回前是否越界。以后增加更大 block 或不同 scale 编码时，必须一起复核这些界限。

## 5. 普通 RVV ALU 的组合改写

平均加减原来先对两个操作数取半，再串行处理低位进位/借位和舍入。
现在在 SEW+1 位上计算原始和/差，加上 `round << 1`，再取 `[SEW:1]`。
舍入位由低两位计算，保持四种 vxrm 模式以及有符号/无符号运算的行为。

`vnclip` 原来将整个 2×SEW 数据移位后做宽舍入加法，再检查高位是否溢出。
现在只对低 SEW 位加舍入增量，用一个额外 carry 位和原高位判断饱和。
特别处理负数加一跨零、正数跨最大值、负数低位产生 carry 等边界。
移位和舍入增量的来源不变；没有修改 `fixed_p_rounding`。

ALU 是组合模块，本次没有引入额外周期。物理上的时序收益仍需综合/布局报告确认，
不能由 RTL 行数或者算术表达式数量推断具体 MHz。

## 6. 验证方式和复现

基准版本先独立运行 QBS engine，保存 33 个功能点及四类 fault 的结果和周期。
修改后还在同一次 VCS 仿真中绑定基准模块，对比每个周期的 ready/valid、busy、
分组结果、FP32 结果、fflags、bank 读取及原有活动计数器。
仅 valid 有效时比较 payload，不能把无效状态的数据当成接口承诺。

```sh
cd verification/timing
make check BUILD=/tmp/ara_timing_check RUN_TIMEOUT=600
```

`REFERENCE` 默认固定为本轮改动前的提交，不读取正在变化的 timing worktree。
生成的 reference RTL 只改模块名，保存在 BUILD 下，不加入硬件源文件列表。
`RTL_EXTRA_SOURCES` 是 QBS 验证的可选参数，默认空，不影响原有验证命令。

ALU 测试同时对比旧 RTL 和独立的加宽算术模型：穷举 8-bit 平均操作数、
16→8-bit 窄化源数据/移位/vxrm，补充大 SEW 边界、随机数据、无效周期和两个窄化落点。

```sh
# 只跑各 SEW 的定向极值，完整 check 已包含这些点。
make alu-check BUILD=/tmp/ara_timing_edges SIM_ARGS=+EDGES_ONLY

# 普通 RVV、QBS、AKV 在同一顶层中的切换回归，使用独立目录。
cd ../..
python3 verification/akv/run_current_handoff.py \
  --output "$PWD/hardware/timing_port_handoff_new"
```

本轮不运行 DC、Innovus 或 Vivado，不修改 uncertainty，不宣称已经达到 1 GHz。

## 7. 本轮实测结论

| 检查 | 结果 |
| --- | --- |
| 整数位宽边界 | 3 项检查通过，覆盖全部九种 profile |
| QBS profile，含逐周期基准对照 | 448 点通过 |
| QBS engine，含 M5–M8 尾块 | 33 点及四类 fault 通过，所有点的周期变化为 0 |
| 激活 context FILL/REUSE/RELEASE | 通过 |
| ALU 穷举及随机对照 | 9,877,184 组通过 |
| 大 SEW 定向边界 | 22,528 组通过 |
| 完整顶层 RVV/QBS/AKV 切换 | 普通 RVV、4 次 QBS、10 次 AKV 通过，traps=0 |
| 定义 SYNTHESIS 后的 QBS 编译与运行 | 33 点及四类 fault 通过；这不是 DC 综合 |

QBS 两个模块合计减少 9736 bit 的声明数据状态，其中 FP entry 为 2560 bit，
整数路径为 7176 bit；另有 FP tag 从 7 bit 缩至 4 bit，未计入上述合计。
综合工具可能已经合并部分旧的重复寄存器，因此不能把该数字当作实测面积减少量。

实测记录、源文件哈希和 33 点的前后周期表保存在
`verification/timing/results/20260908/`。这些结果支持“本轮覆盖范围内没有增加执行周期”，
不代表已经完成全部模型回归或物理时序收敛。没有修改原来的性能结果目录。

## 8. QBS 回数接收控制的组合优化

### 8.1 依据和边界

本批基准为 `7b7c3de0`，只修改 `qbs_block_adapter.sv` 的组合组织和写入表达式。
不修改 `qbs_read_engine` 的 AXI、completion、fault 协议，也不修改 compute engine
的 ready 条件、双 bank 调度、M8 两波执行或激活 context replay。

timing worktree 的 `clk_i_max.tim` 首条路径从 read engine 的
`completion_tag_q.role` 出发，经 `completion_ready`、`data_valid`、
`compute_weight_write_valid` 到 block adapter 的 `weight_accepted_q`，slack 为
`-0.214 ns`。**该报告对应 SRAM 版 adapter，不是当前寄存器版，也不是本批修改后的报告。**
它用于定位值得检查的控制链，不能用来计算本批修改的时序收益。

当前代码有两个可以保持周期行为的改写点：

- 每个 beat 最多 16 字节，原来的 `new_*_bytes++` 是循环展开的条件累加。
  把新增字节判断独立出来，再明确写成平衡加法树，可以避免在 RTL 中描述长串行计数链。
- 原来的完成判断从 `row < row_count` 开始逐字节 `&=`，把行使能混入整个归约表达式。
  compute engine 的 live row count 又经过 valid 控制的选择器。先独立归约 byte-valid，
  再判断当前行是否启用，可以使行选择位只在归约末端参与计算。

这是组合结构优化，不是减少 kernel 周期的调度优化。综合工具可能已经优化过部分旧表达式；
最终门级深度、扇出、面积和功耗变化必须另行测量。

### 8.2 字节计数如何改写

每个输入 byte 仍使用原来的地址映射和范围判断，生成目标 row/context、局部 offset、有效位。
只有范围检查通过，压缩后的局部地址才会用于写入；不会先截断 offset 再检查范围。
weight offset 用 8 bit 覆盖 210 字节，activation offset 用 9 bit 覆盖 292 字节。
这些 target 只是组合信号，不是新的 FIFO、寄存器或流水级。

对第 `i` 个输入字节，新增标志为：

```text
new_mask[i] = strb[i] && mapping_valid[i] && !byte_valid[target[i]]

16 个 1-bit 标志
  -> 8 个 2-bit 两两和
  -> 4 个 3-bit 和
  -> 2 个 4-bit 和
  -> 1 个 5-bit 新增字节数，范围 0..16
```

局部 `write_valid` 不再作为计数树内部的条件，而是在寄存器更新处决定本拍是否写入。
总计数器仍为原来的 32 bit，没有收窄，也没有改变溢出行为。
这里的“移到末端”限于 adapter 内部；上游的 row count 仍可能由 valid 限定，
因此不能声称整条 completion-to-counter 物理路径已经消失。

必须保留的规则如下：

- `clear` 和 write 同拍时，清理优先，计数归零、byte-valid 清零。
- 重复 byte 可以覆盖存储数据，但不重复增加 accepted-byte 计数。
- `strb=0` 或范围检查失败的 byte 不能写入，也不能增加计数。
- `valid=0` 时，无论组合地址、strobe 或预计算 count 是什么，都不改变状态。
- 清理只清 byte-valid 和计数，不清 payload；这一点与基准完全一致。
- 权重和激活分别计算 mask、count，允许同拍写入，不能因共享读总线就假设两者互斥。
  尤其是权重 AXI 回数可以与本地 activation replay 并行。
- M8 的两个 adapter 仍分别接收 context 0..3 和 4..7，M5..M7 的填充布局也不改变。

### 8.3 完成判断为什么仍然准确

每行先根据当前 profile 的 block 字节数计算 `payload_complete`：
该 block 范围内的 byte-valid 必须全部为 1，范围以外的数组容量不参与判断。
然后单独计算 `row_active`，最终得到：

```text
weight_complete[row] = row_active[row] && payload_complete[row]
all_weight_complete = row_count 合法 && 没有已启用但未完成的行
```

activation 使用同样的组织方式。没有启用的 context 不阻挡完成，M8 时两个局部
bank 都检查各自四个 context。仍使用 byte-valid，而不是用收到的总字节数猜测完成，
因此重复写、部分 strobe 和跨 native block 的 beat 不会造成提前完成。

### 8.4 实测和结论

先在未修改 adapter 上验证定向激励和独立 source-byte 计分板，再以相同输入驱动
新 adapter 和从 Git 固定提取的 reference。比较每周期的完整 payload、byte-valid、
逐行完成位、整体完成位和 accepted-byte 计数，不仅比较最后结果。

| 检查 | 结果 |
| --- | --- |
| 九种权重 profile，M1..M8，row-major/R4 和 activation row-major/M4/M8 | 81 组通过 |
| 16-bit strobe 全组合，经真实写入和独立计分板检查 | 65536 组通过 |
| 上述测试逐周期 reference 对照 | 157217 个测试周期通过 |
| 同拍权重/激活写入、重复写、clear 与 valid 冲突、空闲周期 | 均实际覆盖 |
| QBS engine | 33 功能点和四类 fault 通过，周期与独立基准一致 |
| activation FILL/REUSE/RELEASE | 通过 |
| VCS 定义 SYNTHESIS 后执行同一 engine 回归 | 33 点及四类 fault 通过，不代表完成 DC 综合 |
| 完整顶层切换 | 普通 RVV、4 条 QBS、10 条 AKV 通过，traps=0 |

真实模型数据来自 `llama/captures/qwen2.5-1.5b-q4_k_m`。
Decode 使用捕获的 `attn_q`；Prefill 使用捕获的 `attn_q` 和 `ffn_down`。
保留完整 K=1536/8960，只截取输出行和 token 数，使功能仿真保持短小。
下表是 QBS engine 测试环境中的 command 周期，不是完整 SoC kernel 周期或 token/s。

| 来源/格式 | M | N | K | 基准周期 | 修改后周期 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Decode attn_q / Q4_K | 1 | 32 | 1536 | 2219 | 2219 |
| Prefill attn_q / Q4_K | 4 | 32 | 1536 | 7200 | 7200 |
| Prefill attn_q / Q4_K | 8 | 16 | 1536 | 7638 | 7638 |
| Prefill attn_q / Q4_K | 7 | 16 | 1536 | 7612 | 7612 |
| Prefill ffn_down / Q6_K | 4 | 32 | 8960 | 41939 | 41939 |
| Prefill ffn_down / Q6_K | 8 | 16 | 8960 | 44493 | 44493 |
| Prefill ffn_down / Q6_K | 7 | 16 | 8960 | 44479 | 44479 |

七点的 phase 周期、权重/激活/总 payload 字节数、range 数、dot 活跃周期和
weight-prefetch 等待周期也与基准一致。浮点计算顺序、量化格式和数据内容没有修改。

本批不增加状态位或流水级，不更改普通 RVV、AKV 或软件 ABI。不运行综合、布局或功耗工具。
结果支持“已测功能和执行周期不变”，不支持“已经消除违例”或“已获得某个 MHz/面积收益”。
详细记录位于 `verification/timing/results/20260908_adapter/`。

### 8.5 复现命令

从仓库根目录执行，BUILD 使用新的独立目录：

```sh
make -C verification/timing adapter-check adapter-engine-check \
  adapter-baseline-engine-check BUILD=/tmp/qbs_adapter_check RUN_TIMEOUT=300

QBS_ADAPTIVE_RTL_SIMV=/tmp/qbs_adapter_check/engine/simv \
QBS_ADAPTIVE_RTL_RESULT_DIR=/tmp/qbs_adapter_check/real \
  bash verification/qbs/run_adaptive_real_rtl.sh

QBS_ADAPTIVE_RTL_SIMV=/tmp/qbs_adapter_check/baseline_engine/simv \
QBS_ADAPTIVE_RTL_RESULT_DIR=/tmp/qbs_adapter_check/baseline_real \
  bash verification/qbs/run_adaptive_real_rtl.sh

diff -u /tmp/qbs_adapter_check/baseline_real/summary.csv \
  /tmp/qbs_adapter_check/real/summary.csv
```

`ADAPTER_REFERENCE` 默认固定为 `7b7c3de0`。`RTL_BLOCK_ADAPTER_SOURCE` 只用于验证中
装入基准 adapter，普通 QBS 验证默认仍编译当前 RTL。
`QBS_ADAPTIVE_RTL_SIMV` 允许真实数据测试使用独立编译目录；不设置时保持原行为。
Decode 单点和顶层切换的命令见结果目录的 README。

## 9. SRAM 写入仲裁并行候选的验证记录（已撤回，2026-09-10）

### 9.1 当前证据边界

9 月 8 日启动的整机 DC 在优化中途退出，最后日志行的 `WORST NEG SLACK`
幅值为 2.34 ns；没有输出本轮的 mapped DDC 或 `clk_i_max.tim`。现有最终报告仍是
8 月旧版本，不能据此宣布当前最坏路径属于 QBS。检查时 EDA 容器为 exited，Docker
记录 `OOMKilled=true`。这不是一次正常完成的综合结果。

本节工作是针对当前 RTL 中明确存在的长组合结构做局部 A/B 实验，不是已证实消除了
上述 2.34 ns。仍使用 1 ns 时钟、0.15 ns setup uncertainty，不放宽约束。

### 9.2 可检验的假设与改写

旧 `qbs_payload_buffer` 逐字节动态索引 bank，更新 `write_req/write_addr/write_data`；
后续字节读取前面字节刚写入的组合状态。两个 slot 各 16 bytes，旧 pending 先处理。
这把 bank 解码、首地址选择、字节覆盖和 consumed 判断描述成串行优先关系。

候选版按物理 bank 分开产生候选位图，并区分两种不同优先级：

1. 每个 bank 的第一个有效字节选择本拍 SRAM word；先看 pending，pending 无该 bank
   请求时再看新输入。
2. 指向被选中 word 的字节都可以写入。多个字节指向同一 byte lane 时，序号最大的
   字节覆盖前面的数据；新输入优先于 pending 中的同地址字节。

地址选择使用前缀归约构造 first-one，数据选择使用后缀归约构造 last-one，再进行
独热数据选择。bank 和 byte lane 均为 elaboration 常量，不再通过动态数组下标逐次更新。
新 slot 仍只能继承旧 slot 的地址，旧 slot 的 consumed 不依赖新输入，因此不会引入
`ready -> input valid -> pending consumed -> ready` 的组合环。

只修改写仲裁，SRAM 数量、容量、读延迟、metadata、profile、pending 寄存器、计算与
完成协议不变。该改写是否减少门级延迟和面积，要以配对 DC 报告为准。

### 9.3 验证与复现

新增的 payload miter 固定使用 `1b0aec5f` 的原模块，先在未改动设计上运行，验证测试
环境本身。每拍比较两个 slot 的 consumed、各 bank 的 request/address/byte-enable、
有效写字节和 SRAM/metadata 输出窗口。覆盖九种 profile、连续与离散地址、重复 byte、
各 slot valid 组合，以及改变新输入不得影响 pending consumed 的检查。

```sh
make -C verification/timing payload-check \
  BUILD="$PWD/hardware/timing_payload_new/equivalence" RUN_TIMEOUT=300
make -C verification/timing sram-check sram-engine-check \
  BUILD="$PWD/hardware/timing_payload_new/regression" RUN_TIMEOUT=300
python3 verification/timing/run_payload_dc.py \
  --output "$PWD/hardware/timing_payload_new/dc"
```

局部 DC 只综合 payload buffer 和其真实 8x256 SRAM macro，使用两核，单次上限一小时。
脚本复制 RTL、library 配置和 Tcl 到独立目录，保存 Git 基准、RTL diff、源码哈希和
运行状态；mapped DDC 优先于最终报告保存。两个版本须分别在各自源码状态下启动，
不能让正在运行的 DC 读取后来被覆盖的源文件。

局部输入/输出预算为 0.5/0.4 ns，未包含整机的上游/下游路径，也没有插入整机的 clock
gating。应比较相同边界的时序、面积和关键路径，不能把局部 slack 当作整机 `clk_i` slack。

本轮目录为 `hardware/timing_payload_20260910/`。已经完成的 VCS 结果如下：

| 检查 | 结果 |
| --- | --- |
| 原版与候选的 payload 逐周期对照 | 110592 次检查通过；测试环境在原版上也先完成同样检查 |
| SRAM adapter | 81 组配置、65536 种 strobe、重复覆盖、非连续地址、clear 和读窗口通过 |
| 连续流式写入 | 81 组全部通过，stalls=0；非连续定向序列仍为 4 个必要停顿 |
| QBS engine | 33 个计算用例、四类 fault 通过；activation FILL/REUSE/RELEASE 通过 |
| 33 点周期对比 | 与 `20260908_sram_merge/engine.log` 的身份及周期逐项一致 |
| Qwen2.5 真实 Q4_K attn_q，M4/N32/K1536 | PASS，7200 cycles，与归档基准一致 |
| Qwen2.5 真实 Q6_K ffn_down，M4/N32/K8960 | PASS，41939 cycles，与归档基准一致 |

两个真实模型切片的 phase cycles、payload 字节、range 数和 dot cycles 也与归档基准相同。
这些结果是模块/engine 范围的功能和周期证据，不是整机普通 RVV 或完整模型的新一轮回归。

两份局部 DC 都达到 3600 秒的运行上限，退出码 124，没有 mapped 报告。这是工具运行
超时，不是 RTL 功能失败。进入 compile 的中间统计如下，不能将其当作最终门数或面积：

| 指标 | 原版 | 并行候选 |
| --- | ---: | ---: |
| Leaf Cell Count | 598912 | 825606 |
| Sequential Cell Count | 1804 | 1804 |

并行候选的中间单元数增加约 37.9%，没有证据表明它更易综合，因此已从当前 RTL 撤回。
测试记录保留。当前改写见下一节，不采用该候选的全 bank/byte 独热数据选择矩阵。

## 10. 面积与综合友好的缓冲接口及流程（2026-09-10）

### 10.1 检查范围与结论边界

本轮检查了 SoC 的编译配置、SRAM 选择、QBS/AKV 的主要存储及计算接口，以及普通
RVV lane 数据通路和既有时序修改。实际修改集中在 payload buffer 和 DC 流程，没有
借此改变 ISA、九种权重 profile、M/N/K 范围、浮点累加顺序或 RVV 的相关性规则。

| 部分 | 当前结构与本轮处理 |
| --- | --- |
| QBS payload | 两个 adapter，每个 12 个单端口 SRAM bank；改进外围选择逻辑，不增加端口或容量 |
| QBS activation context | 有效 payload 上限 16×292 B，已有双 bank 同步 SRAM 和重放协议；不改变其延迟 |
| QBS FP accumulator | 8×16 个 FP32 累加槽位，存在并行访问、旁路和提交约束；不为节约寄存器而直接换成单端口 RAM |
| AKV context | 已映射 SRAM；原 context 与 v2 context 的存储、请求/返回配对不变 |
| AKV v2 column buffer | 4×1024 bit 输出暂存用于列递送；不是可无代价替换成同步单端口 RAM 的闲置数组 |
| 普通 RVV ALU/MUL/VMFPU | 保留已完成的时序/正确性修改，本轮不增加流水级或改变 issue/commit 时刻 |
| 观测计数器 | compute-engine 的 probe 受 `ifndef SYNTHESIS` 保护；具有接口输出的计数器另行跟踪，不一概当作可删状态 |

上述是结构检查，不等于全设计形式等价或最终 PPA 签核。整机最新一次 compile 未完成，
8 月的 `clk_i_max.tim` 不能作为当前 RTL 的精确最坏路径。日志中的 2.34 ns 是负 slack
的幅值，也不能直接当成路径延迟或工作周期。

### 10.2 先看到什么证据，再改什么

对保留原写入结构、仅展开读窗口的诊断版本执行 DC elaboration，资源报告
`hardware/timing_payload_20260910/fixed_view_elab/elaborated_references.rpt` 中出现：

| 中间选择操作 | 数量 | 对应问题 |
| --- | ---: | --- |
| `SELECT_OP_2.3072_2.1_3072` | 96 | 动态 bank 写入反复选择整组写数据 |
| `SELECT_OP_2.640_2.1_640` | 63 | weight metadata 的整数组条件更新 |
| `SELECT_OP_2.1152_2.1_1152` | 63 | activation metadata 的整数组条件更新 |

这些是 GTECH/综合中间操作，不是 96 个最终 3072-bit 标准单元，更不能直接换算为
面积。但它们证明 RTL 的数组写法让工具先构造了很宽的选择网络。该诊断运行还暴露了
局部脚本误把 `elaborate` 返回状态当作 collection 的 `SEL-001`，已修正；因此该目录
保留 FAIL 状态，仅将其资源表用于定位，不能列为正式综合通过。

当前 `qbs_payload_buffer.sv` 做三项等周期改写：

1. **固定 bank 的写入仲裁。** 每个物理 bank 单独处理自己的 16-byte slot，不再通过
   动态 bank 下标更新整个三维数组。仍由第一个可接受字节选择本拍 word，后续匹配
   word 的字节合入；slot 1 继承 slot 0 已选 word，不反过来影响 pending consumed。
2. **固定 metadata 字节的写使能。** 每个字节独立比较目标 row 和 offset，用五层
   二选一树选出 32 个输入中最后一个有效写者。保留“较新字节覆盖旧字节”的精确规则，
   未命中时原寄存器保持，不再让整个 metadata 数组参与每次条件赋值。
3. **固定格式连线的读窗口。** 各格式的 plane 和 byte offset 在 elaboration 时确定，
   运行时只选择对应格式的数据。不先选择一个动态下标，再对所有 bank/byte 做第二次
   选择。逐字节生成输出选择逻辑，避免 VCS 因单字节变化重算整个输出数组。

没有增加寄存器级数、pending 深度、SRAM 数量或存储容量。同步读采样时刻、byte-enable、
重复地址覆盖、clear 后的所有权控制保持原样。接口仍提供原生块下标的窗口，因此无需
修改 decoder 或软件。metadata 仍不复位，由 adapter 的 byte-valid 限定读取合法性。

当前 bank-local 候选已完成局部 elaboration/link 并进入映射。与原版相同范围的
compile 前统计如下：

| 指标 | 原版 | 当前 bank-local 候选 |
| --- | ---: | ---: |
| Leaf Cell Count | 598912 | 241781 |
| Sequential Cell Count | 1804 | 1804 |
| 每个 payload buffer 的 8×256 SRAM 实例 | 12 | 12 |

中间 leaf 数减少约 59.6%，原先 3072/640/1152 bit 的整数组条件选择已不再出现在
当前 reference 表中。这说明展开结构有所简化，但不是最终面积减少 59.6%，也不能
证明最坏时序已经收敛。当前仍存在 bank 内的字节写入选择和格式选择，必须继续看
mapped 结果。`check_pre.rpt` 的 424 项提示为 416 个未驱动输出的中间单元、8 个未使用
输入端口；后者是读地址低五位及 SRAM wrapper 的 reset，不是未解析的 SRAM 宏。
宏引用已链接到 `ts1n28hpcpuhdsvtb8x256m1swbso_tt0p9v25c`。

### 10.3 综合流程改进

- 预检补查 `qbs_payload_buffer.sv`、`qbs_payload_sram.sv`、8×256 blackbox 和 DB。
- `analyze/elaborate/link` 失败不继续正常流程，缺 SDC 时非零退出。
- 每次运行有独立编号。带约束的 pre-compile DDC/SDC、compile 后的 mapped DDC/SDC
  保存到 `outputs/checkpoints/<run_id>/`；mapped 检查点早于大量时序、面积、功耗报告。
- `run/dc.status` 记录阶段和 runner 退出码。批处理完成后退出，不因 GUI 调试选项留下
  等待输入的 DC 会话；直接在 GUI 中 source 的使用方式仍保留。
- `dc`、`dc_flist`、`dc_preflight` 在生成共享 filelist 前取得目录锁，直到结果收集结束
  才释放；直接调用 `run.cmd` 使用同一把锁。旧 `dc.log/dc.status` 自动复制到
  `run/log_archive/`。工具返回 0 但日志含 Error/Fatal，或缺少完成标记，也视为失败。
- 增加 `DC_ELAB_ONLY=1`，用于先检查展开结果及宏引用；这种模式不采集 mapped PPA。
- 局部实验复制 RTL、Tcl、库配置和 runner，记录内容哈希；超时记录为 TIMEOUT，不冒充
  RTL FAIL。可指定 Git reference 和仅 elaboration 模式，以相同边界进行比较。

不改变 1 ns 时钟、0.15 ns setup uncertainty、clock-gating setup/minimum width、
功耗优化开关或原来的 dont-use。检查点无法恢复一次尚未结束、因 OOM 中断的
`compile_ultra` 内部状态；它防止的是成功 compile 后在报告阶段丢失唯一映射结果。

进入 EDA 容器后，整机仅展开的命令为：

```sh
cd /home/wangwy/openproject/ara_dsa/hardware
DC_ELAB_ONLY=1 make dc mc=1 qbs=1 akv_v2=1 config=default ideal_dispatcher=0 sim_l2_mb=1
```

正式整机综合仍用相同命令去掉 `DC_ELAB_ONLY=1`。本轮没有自动启动新的整机长综合，
当前局部综合结果目录为 `hardware/timing_payload_20260910/bank_local_dc/`，须等
`status.json` 和 mapped 报告完成后才能量化面积/时序收益。

### 10.4 当前验证

本轮最终候选的测试目录为 `hardware/timing_payload_20260910/bank_local_test/`。
最终验证目录为 `hardware/timing_payload_20260910/bank_local_verify/`。payload 复用
`bank_local_test/payload/simv`，该二进制与局部 DC 使用同一份 RTL。其首次 300 秒运行
到第八种格式时触及墙钟上限，没有功能首错；随后保持 4096 trials/profile 和同一二进制，
以 600 秒上限完成。没有修改 RTL 看门狗或缩小检查数量。

| 检查 | 当前结果 |
| --- | --- |
| Payload 对照 `1b0aec5f` | 九种格式，110592 次逐周期检查通过 |
| QBS engine | 33 个计算用例、四类 fault、activation FILL/REUSE/RELEASE 通过 |
| 33 点周期 | 与 `20260908_sram_merge/engine.log` 的 case 身份、周期逐项相同 |
| Q4_K 真实 attn_q，M4/N32/K1536 | PASS，7200 cycles |
| Q6_K 真实 ffn_down，M4/N32/K8960 | PASS，41939 cycles |
| SRAM adapter 配置及连续写入 | 81 组配置通过，81 组连续流 stalls=0，非连续/重复地址用例通过 |
| SRAM adapter 完整 strobe 矩阵 | 65536 种 strobe 全部通过，174486 个测试周期，VCS CPU 约 661 秒 |

SRAM 穷举保留原有完整输入集合，在独立的 `bank_local_fullstrobe/` 目录后台运行，
仿真墙钟上限为 1800 秒，编译与仿真总上限为 2100 秒。测试台每完成 4096 种 mask
打印一次进度，没有改变 RTL 看门狗、激励或期望结果。完整 PASS 位于该目录的
`launcher.log` 和 `sram/run.log`，此前 `bank_local_verify/sram/` 是 600 秒超时的
部分结果，二者不混用。上述记录对应 payload 改写，下一节的 valid 改写单独回归。

两个真实切片复用 `regression/real/*.vectors`，其结果、phase cycles 和 traffic 行均与
之前日志逐项一致。这里的“周期相同”指 RTL 模型的执行周期，不是 VCS 在主机上的耗时。
本轮更细粒度的组合连线会增加事件仿真开销：payload miter 使用约 337 CPU 秒，Q4/Q6
切片分别约 12/127 CPU 秒。尚不能据此承诺整机 VCS 的墙钟性能不变。

纯软件流程检查已通过 11 个 synthesis-preflight 测试、8 个 DC runner/helper 测试，以及
当前 406-source/18-define 配置的预检。未进行 PNR、功耗提取或新的整机 RVV 回归。

## 11. Adapter 的 valid 置位网络（2026-09-11）

### 11.1 修改依据与不变量

`qbs_block_adapter.sv` 每个实例保存 840 个 weight valid 位和 1168 个 activation
valid 位。它们表明哪些字节已经实际写入 SRAM 或 metadata，不是哪些字节刚到达
AXI 接口。此前每拍最多 32 个目标通过动态 row/offset 下标依次将这些位写成 1，
DC 需要展开动态数组更新。该写法与 payload 已定位的宽数组选择问题同类；本轮
进一步检查它的综合负担，但在得到 A/B 报告前不声明节省比例。

本轮保留全部 2008 个 valid 位，只改更新网络。对每个固定目标位 `(row, byte)`：

```text
set_hit = OR(所有已提交字节中，目标等于这个位置的项)
next_valid = reset ? 0 : set_hit ? 1 : clear ? 0 : old_valid
```

原逻辑的每个写者都写入常量 1，故相同目标的多次写入可以交换顺序，也可以合并为
OR；这与 payload 数据需要保留“最后一个写者”的规则不同。实现仍保留原代码的
reset 最高优先级、置位高于 clear 的赋值语义。正常协议中 clear 已把两路 source
valid 清零，因此不会出现 clear 同拍又置位。

没有改变动态 valid 查询、字节地址映射、去重 mask、accepted-byte 计数、完成归约、
pending 暂存或 ready 条件。计数仍读取更新前的 valid 状态，跨 slot 的重复提交仍由
原来的 `overlapping_bytes()` 去重。没有增加请求延迟、寄存器数量或 SRAM 端口。

### 11.2 对照与结果位置

新增 `verification/timing/qbs_valid_equivalence.sv`，以 `1b0aec5f` 中按顺序动态写入
valid 的规则建立独立参考状态。每拍比较每个 adapter 的全部 valid 位，不只比较最终
计算结果；同时继续使用已有的 SRAM 内容、计数、完成状态及 ingress 检查器。

测试及局部 DC 位于 `hardware/timing_valid_20260911/`：

| 目录 | 用途 |
| --- | --- |
| `regression/engine/` | 33 个 engine 用例、fault 与 activation lifetime 检查，加逐拍 valid 对照 |
| `real/q4_m4n32/`、`real/q6_m4n32/` | 复用上一轮的真实 attn_q/ffn_down 输入，比较周期和逐项 phase/traffic |
| `fullstrobe/` | 九格式/81 配置、连续流、重复地址、clear 和完整 65536 strobe 矩阵 |
| `baseline_dc/` | 保留本轮修改前的 adapter，使用已经改好的 payload buffer |
| `candidate_dc/` | 使用本轮固定目标 valid 更新的 adapter |

两份 DC 是同一套 Tcl、库、1 ns 时钟和 0.15 ns setup uncertainty，当前先执行
elaboration-only。快照哈希已确认只有 `qbs_block_adapter.sv` 不同，避免把上一轮
payload 改进计入本轮收益。结果必须分别检查各目录的状态及报告，不能用 GTECH
单元数代替 mapped 面积，也不能把上一节的 PASS 自动算成本节通过。

本轮已完成的 engine 检查：33 个计算用例及四类 fault 全部通过，33 点的身份和
执行周期与上一节一致；两个 adapter 各完成 22929 个周期、每周期 2008 个 valid
位的对照。真实 Q4_K attn_q（M4/N32/K1536）通过，保持 7200 cycles，phase 和
traffic 字段也逐项一致；两个 valid 参考各检查 7209 个周期。汇总文件为
`engine_summary.json`。

真实 Q6_K ffn_down（M4/N32/K8960）也已通过，保持 41939 cycles，phase 和 traffic
逐项一致；两个 valid 参考各检查 41948 个周期。真实切片结果及输入/日志哈希存入
`real_summary.json`，周期表为 `real_cycles.csv`。完整 strobe 矩阵与局部 DC A/B
继续在后台执行，结果另行检查完成状态；没有启动整机综合或修改约束。

新增逐位参考模型及细粒度 valid 网络会增加 VCS 工作量。本轮 engine 测试 CPU
约 147 秒、Q4/Q6 切片约 44/373 秒；这不能解释为硬件执行周期变长，也不能把增加的
主机耗时全部归因于 RTL 或全部归因于探针，二者未单独做耗时消融。

流程单元测试为 9 个 runner/helper/snapshot 测试，加 17 个 synthesis preflight/
collection 测试，均通过；当前综合源列表预检仍为 406 sources、18 defines。

### 11.3 后续展开检查发现的代价

上述 A/B 已生成 `elaborated_references.rpt`，但其后的 `report_runtime` 不受本机
DC T-2022.03-SP2 支持，两份任务均被 runner 正确标为 FAIL。因此这里只比较报错前
生成的展开资源，不能把它们称为完整综合通过，也不能据此报告最终面积或 slack。

| Adapter 本层展开项 | 原动态更新 | 固定目标完整比较 |
| --- | ---: | ---: |
| 840/1168-bit 二选一操作 | 各 66 | 0 |
| GTECH AND2 | 129730 | 256442 |
| GTECH OR2 | 5101 | 668973 |
| GTECH NOT | 68655 | 399767 |
| GTECH BUF | 65662 | 3350 |
| 报告中的高扇出网数 | 8 | 396 |
| DC 会话内存，MB | 3690 | 4986 |
| 展开及报告墙钟，秒 | 1033 | 1287 |

两次运行并发，墙钟不是隔离的速度基准；以上 GTECH 计数也没有把未展开的 synthetic
operator 等价成门数。结论是：宽选择器消失并不意味着综合工作量下降。逐目标重复
完整 row/offset 比较形成了另一种大网络，需要共享译码，不能仅以 MUX 数作为优化依据。

## 12. Valid 更新的共享分组译码（2026-09-11）

### 12.1 根因假设与实现

上一版每个 adapter 有 2008 个固定目标，每个目标比较 32 个输入，合计描述 64256
个完整目标匹配项，每项均含 row 和 offset 判断。DC 展开报告中的 AND/OR 数量和
高扇出代价支持“重复完整地址比较放大展开网络”这一假设。

当前将每个输入的地址拆为三段，先独立共享译码：

```text
row_select[writer][row] = committed[writer] && target_row == row
group_select[writer][group] = target_offset[high:4] == group
byte_select[writer][byte] = target_offset[3:0] == byte

group_hit[row][group] = row_select[row] & group_select[group]
set_hit[row][group][byte] = OR(group_hit[row][group] & byte_select[byte])
```

每条位向量包含 32 个 writer。权重有 14 个组，激活有 19 个组；每组最多 16 byte。
按 RTL 表达的比较次数为 `32*((4+14+16)+(4+19+16))=2336` 个小比较，再加分组
AND/OR 网络。这不是最终门数，不能用比较次数降幅充当面积或综合时间降幅。

拆分满足 `offset == 16*g+b` 等价于“高位等于 g 且低四位等于 b”，不假定 beat
对齐、strobe 连续或同拍只有一个 writer。所有 writer 都写 1，故 OR 合并仍然等价；
reset > set > clear 的优先级保持不变。尾部不完整组仅生成真实存在的 valid 位。

动态 valid 读取、完整地址范围检查、pending、去重计数、SRAM 仲裁、profile 支持和
接口均未改动。没有增加模块、存储、流水级，也没有修改 1 ns/0.15 ns 约束。

### 12.2 验证与证据边界

独立结果目录为 `hardware/timing_valid_shared_20260911/`。`regression/engine/`
用当前源码重新编译，复用原 engine 激励、SRAM 内容/计数/ingress 检查，并绑定
第 11 节的逐拍 valid 参考；随后使用同一 binary 跑原 Q4/Q6 真实输入。
`adapter_dc/` 冻结源码、Tcl、库环境和哈希，在容器中做局部展开，不覆盖整机报告。
这些任务的完成状态应以各自日志为准，上一版的 PASS 不自动计入本版。

本轮也将主 DC 和局部 DC 的 runtime 报告改成命令存在性检查。不支持时打印 Tcl
墙钟秒数，不吞掉其他综合错误；支持时仍调用工具自身命令。10 个流程测试覆盖
两种分支，另有 17 个综合预检/结果收集测试通过。源码列表仍为 406 sources、18 defines。

当前共享译码候选已完成以下实测，汇总及源码/输入/binary/log 哈希保存在
`hardware/timing_valid_shared_20260911/verified_summary.json`：

| 用例 | 结果 | 与上一版比较 |
| --- | --- | --- |
| Engine 33 个点及四类 fault | PASS | 33 点身份与周期逐项一致，activation lifetime 通过 |
| Q4_K 真实切片 M4/N32/K1536 | PASS，7200 cycles | phase、traffic、SRAM/ingress 统计一致 |
| Q6_K 真实切片 M4/N32/K8960 | PASS，41939 cycles | phase、traffic、SRAM/ingress 统计一致 |
| 逐位 valid 等价检查 | PASS | 每个 adapter 分别检查 22929、7209、41948 拍，每拍 2008 位 |

相同检查器下，engine/Q4/Q6 的 VCS CPU 时间从约 147/44/373 秒变为
44.50/15.41/131.78 秒。它说明这组测试的事件仿真工作量降低，不能代替 DC 映射
耗时、硬件主频或面积结论。局部 DC 展开和完整 strobe 穷举仍是独立后台任务，
未将上一版的完整 strobe 结果或任何旧 mapped 报告算作当前候选通过。

## 13. 综合入口的完整互斥范围（2026-09-11）

仅在 `run.cmd` 内加锁不够：`make dc` 的前置目标会先重写共享的
`backend/flist/ara_soc_dc.f`，而收集报告又在 `run.cmd` 退出之后。因此第二次启动
即使最终被拒绝，也可能已经改写第一次运行的输入；报告收集时也有混入新结果的窗口。

当前三个公开目标 `dc`、`dc_flist`、`dc_preflight` 均先通过
`global_scripts/dc_lock.sh` 取得 `run/.dc.lock`，再递归执行对应的 `*_locked` 目标。
递归 make 保留命令行配置、jobserver 和 dry-run 选项。完整 `dc` 流程的顺序为：

```text
取得目录锁 -> filelist -> preflight -> run.cmd/DC -> collect -> 释放锁
```

锁通过继承的 FD 9 保持到子 make 结束。`run.cmd` 复用同一 open-file description，
不会再次打开文件把自己锁住；独立调用时则自行取得同一把锁。内部目标会同时验证锁
文件身份及继承的 FD，只有环境变量而没有文件描述符不能绕过检查。竞争者立即失败，
不会在后台等待后自动启动另一轮综合；不要删除仍被使用的 `.dc.lock` 文件。

此锁保护上述脚本入口，不阻止用户手工编辑 RTL、直接改 filelist，或在 GUI 中绕过
`run.cmd` source Tcl。若需要边改代码边综合，仍应使用独立 worktree 或冻结源码的
实验目录。现有命令、时钟约束、RTL 和网表输出名称均没有改变。

验证全部在临时目录中使用真实 Makefile 的 DC recipe 和假 Bender/DC/collector 完成，
没有调用 EDA 工具。17 个流程测试覆盖：四个阶段分别阻塞时的并发拒绝、共享 filelist
不被竞争者覆盖、直接 `run.cmd` 互斥、递归配置传递、`-j2`、`make -n` 不执行工具、
elaboration-only 不收集 mapped 报告、各阶段失败后停止并释放锁、无锁内部入口拒绝，
以及已有日志/返回码/runtime 兼容检查。另有 17 个预检/收集测试通过；当前配置的
只读综合预检仍为 406 sources、18 defines、1 ns 时钟及 0.15 ns setup uncertainty。

## 14. 消除动态宽选择与运行时表构造（2026-09-11）

### 14.1 本轮处理的具体网络

本轮继续针对展开报告中的宽 SELECT、重复字节更新和变量除法表达式做改写，
不是为了让测试通过而增加延迟或降低约束。QBS 九种 profile、数值计算顺序、
SRAM 容量/端口、普通 RVV 的依赖处理均不改变。

| 位置 | 原先增加展开负担的描述 | 当前实现 | 保留的语义 |
| --- | --- | --- | --- |
| `ara_pkg`、dispatcher、lane sequencer | 以 EEW 决定的容量为变量分母求商/余数 | 常量字节容量的 log2 与 EEW 相减，使用移位/掩码 | 原 unsigned 位宽；非法零分母返回 X，不把非法 EEW 变成合法访问 |
| `ara_pkg::deshuffle_index` | 根据运行时 EEW 反复构造逆索引表 | 分 EEW 调用常量版本的逆表，再选择结果 | 原支持的 1/2/4/8/16 lane 映射及 EEW 默认分支 |
| mask、QBS destination 对齐 | 对 `1 << eew` 或目的寄存器组大小取模 | 对 `size - 1` 做 AND | 分母本来就是非零的 2 的幂；未替换通用除法器 |
| QBS FP / integer result 仲裁 | 16/32 次旋转索引扫描中选择宽 payload | 先在 RR 指针两侧建立有效位集合，用已有 `lzc` 选索引，再读取一次 payload | 先查指针及以后，再回绕；RR 仍只在握手时前进 |
| QBS accumulator、lane snapshot | 运行时索引写整个数组的局部 | 固定 bank/word 的 FF 使能，广播同一份写数据 | reset、clear、写入优先级、读端口数和读延迟 |
| AKV-v2 column buffer | 在 1024-bit 列中动态写一个 token 的 16 bit | 每个 bank/column 选一次 16 bit，按 token group 使能固定槽位 | capture 高于 clear；尾 token/column 不写；完成周期不变 |
| QBS SRAM write byte merge | 每个 byte 依次更新一个 256-bit bank word | bank 地址仲裁不变，低五位 byte 译码共享；每字节用平衡树选择最后写者 | slot 0 的消费不依赖 slot 1；新字节覆盖旧字节；每 bank 每拍仍只写一个字 |
| QBS metadata | 每个目标重新比较 writer 的 row/offset | 分别共享 row 和 offset 译码，再做原来的最后写者树 | 同地址多写时仍取最大的 writer 下标；不改变 metadata 存储 |
| QBS compute 读接口 | 展开原生 block 视图、选择双 bank、decoder 再索引 | 直接传递 SRAM 窗口与 metadata，decoder 只映射所需字节 | 当前 K 的数据窗口、同步读时刻、bank 切换和 context wave |

lane 的 source snapshot 没有改成单端口 SRAM：现有多个消费者需要并行读取，
直接换成单读口会改变行为或吞吐。本轮只去掉动态写描述，不能据此宣称快照容量减少。
同样，没有修改 FP 的转换、乘法、累加顺序，也没有增加流水级来掩盖关键路径。

### 14.2 紧凑读接口的范围与约束

实际 compute 中，两份 adapter 使用 `NativeView=0`，integer engine 和 decoder
使用 `CompactRead=1`。在 bank 选择处，旧组合接口有
`4*210*8 + 4*292*8 = 16064 bit`；新接口为：

```text
weight:     4 rows * 2 planes * 256 bit + 4 * 20 * 8 bit = 2688 bit
activation: 4 contexts * 256 bit       + 4 * 36 * 8 bit = 2176 bit
total:                                                     4864 bit
```

这不是额外的 4864 bit 存储。数据仍来自同样的 12 个 SRAM bank 和 metadata FF。
新接口省去重复展开和跨 bank 选择的描述，但最终面积、延时及 DC 时间仍须实测。
decoder 中的两个 byte helper 根据 profile 将原生 offset 映射到 low/high plane
或 metadata，只在当前 K 所在窗口取数。不能借此任意读取尚未发起 SRAM read 的字。

兼容模式保留给原生 block 测试，默认参数仍可使用旧接口。compute 显式选紧凑模式，
其未使用的原生视图接零。DC T-2022.03-SP2 不接受新接口最初使用的嵌套数组 default
赋值，已改成固定元素常量连线；这个兼容性问题由局部 DC 检查发现，不能用 VCS
编译通过替代 DC 语言兼容检查。

### 14.3 完成的验证及可复现证据

结果目录：`hardware/timing_synth_cleanup_20260911/`。本轮没有覆盖整机 DC 输出、
已有 sweep 日志或其他后台运行目录。VCS 在宿主机执行，局部 DC 在
`synopsys_workspace` 容器中执行。

| 检查 | 结果 | 日志位置（相对上述目录） |
| --- | --- | --- |
| shift/mask、逆表与原算式对照 | PASS，900944 次 | `helpers_checked/helpers/run.log` |
| payload 仲裁及数据逐拍对照 | PASS，27648 次，九种 profile | `payload_checked/payload/run.log` |
| profile 计算与 native-input integer/FP miter | PASS，448 个用例 | `final_qbs_checked/profile/run.log` |
| 完整 QBS engine，含 descriptor/MMU/AXI/PMA fault | PASS，33 个计算用例、四类 fault | `compact_checked/engine/run.log`、`final_qbs_checked/qbs/run.log` |
| SRAM 内容、valid、计数和尾块 | PASS，81 配置、65536 种 strobe | `compact_adapter_checked/sram/run.log` |
| 81 配置连续流 | PASS，全部无 ingress stall | 同上，`QBS SRAM streaming PASS` |
| AKV 行/列、尾块、故障检查 | PASS，D64/D96/D128、分段 D256 | `akv_checked/run.log` |
| AKV macro 分支功能模型 | PASS，相同维度和检查 | `akv_macro_checked/run.log` |
| QBS descriptor 边界检查 | PASS | `descriptor_checked/run.log` |
| Q4_K 真实切片 M4/N32/K1536 | PASS，7200 cycles | `real_q4_checked/run.log` |
| Q6_K 真实切片 M4/N32/K8960 | PASS，41939 cycles | `real_q6_checked/run.log` |

两个真实切片继续使用 `timing_payload_20260910/regression/real/` 中的原 vectors。
它们的身份、cycles、phase 和 traffic 行与 `timing_valid_shared_20260911/real/`
的记录逐项相同；33 个 engine 点的身份和 cycles 也全部相同。因此上述测试没有
发现硬件执行周期回退，不能将这一结论外推为尚未重跑的全部 RVV/模型通过。

紧凑接口不把全零的兼容输入拿去冒充完整数据做 integer miter：native 模式由
`qbs_int_equivalence` 对照原 integer engine；紧凑模式由 SRAM checker 将实际
窗口解码结果与独立寄存器版 adapter 保存的完整 block 比较，并继续检查 FP
逐拍输出和独立 engine 期望值。这样分别检查接口变换与计算行为，避免自我对照。

初次 payload miter 采用每 profile 4096 次随机组合，在 300 秒墙钟预算内未完成，
没有记为 PASS；定量检查改为每 profile 1024 次，共 27648 个对照时刻。完整
65536 strobe 矩阵另行全部通过，没有删减该矩阵或提高 RTL watchdog。

### 14.4 尚不能声称的结论

本轮最终局部 DC 使用冻结源码的 `compact_payload_dc_final/`，保持 1 ns 时钟和
0.15 ns setup uncertainty，展开后继续局部映射，墙钟上限 3600 秒。这不是整机
PPA 运行，长任务留在后台，不持续轮询。需检查 `status.json` 和报告确认完成。

`compact_payload_dc/` 是前述语法错误留下的失败记录；后续的
`compact_payload_dc_checked/` 已成功展开 `qbs_payload_buffer_NativeView0`，但
runner 随后用未带参数的模块名执行 `current_design`，产生 UID-109，因此整个
运行也标为 FAIL。脚本已改为保留 `elaborate` 实际选中的参数化 design，并打印
其名称；不忽略报错，也不把这份失败记录标为综合成功。该轮已生成的正确 design
资源表可用于诊断，不能冒充最终 mapped 面积或时序结果。

17 个 runner/互斥/快照测试与 11 个 synthesis-preflight 单元测试已通过；快照
测试也检查 `NativeView=0` 配置及参数化顶层名称处理。没有放宽工具错误判定。

仍保留 adapter 的动态 valid 查询及必要范围检查，没有将其简化成假定连续或
对齐的特殊路径。AKV 地址计算也未盲目截位，避免改变地址溢出检查。这些剩余
网络是否值得继续修改，应由新的展开和 mapped 关键路径决定。

本轮不启动整机长随机回归、PNR 或功耗流程，也不据局部测试宣称修掉所有
setup 违例。此次实测支持的是功能对照、代表点周期不回退以及更明确的硬件
结构表达；整机综合耗时和 1 GHz 收敛仍是下一次完整 DC 的独立检查项。

## 15. 入口 valid 查询与 descriptor 写入（2026-09-11）

### 15.1 根因与改写边界

第 14 节保留的 adapter 查询在局部展开中仍有 32 个 4-row/210-bit MUX、32 个
4-context/292-bit MUX，以及各 32 个 210-to-1、292-to-1 位选择器。根因是把
两个连续源 beat 当成 32 个互不相关的随机索引。这些是展开算子，不是最终 mapped
门数；写 valid 的共享译码和 SRAM 仲裁在本节不再改动。

当前先把 native valid 连线成源字节顺序，再由每个 beat 选择一个 32-bit 对齐窗口，
按低四位偏移得到 16-bit 查询结果。权重支持现有九种 profile；激活支持 Q8_K/Q8_0
以及 row-major/M4/M8。两份 context-wave adapter 各自保留范围过滤。
排列视图没有新增 FF，原来的 2008 个 valid 位、完整性归约、重复覆盖、accepted-byte
计数和 pending 提交条件不变。低地址未对齐、跨行、尾部和任意 strobe 都不能简化掉。

QBS/AKV descriptor 接收原先在 beat-byte 循环内动态更新 128/512-bit 向量。
现在把 read data 和 strobe 各左移一次，得到 descriptor 宽度的对齐数据和写掩码，
每个固定目标字节只在自己的掩码置位时写入。等价条件为：

```text
旧实现：destination = read_offset + source_lane
新实现：aligned_data = zero_extend(read_data) << (8 * read_offset)
        aligned_mask = zero_extend(read_strb) << read_offset
        fixed destination byte writes iff aligned_mask[destination] == 1
```

高 offset 不截位，因此越界 beat 不会回绕污染 descriptor 的低字节。原来的 reset、
command 接受时清零、descriptor-request 清零以及回包写入优先级保持不变。没有增加
流水级、改变吞吐/接口或修改 1 ns/0.15 ns 约束；普通 RVV 运算及依赖处理未修改。

### 15.2 本轮证据

独立目录为 `hardware/timing_ingress_cleanup_20260911/`。`before/` 保存修改前的
三个 RTL 文件；`baseline_dc/` 与 `window_dc/` 冻结各自的源码、Tcl 和哈希，采用
相同库、NativeView=0、时钟和约束，先做局部 elaboration-only，不覆盖整机报告。

| 检查 | 当前结果 | 位置 |
| --- | --- | --- |
| Descriptor 对齐网络与原 scatter 算式 | PASS，两种宽度各 786432 组 | `alignment/descriptor/run.log` |
| AKV engine | PASS，D64/D96/D128、分段 D256、尾块及 fault | `akv_checked/run.log` |
| AKV 绑定实际 descriptor 对齐网络 | PASS，957923 拍 | 同上 |
| QBS engine | PASS，33 计算点、四类 fault；周期逐项未变 | `engine_checked/engine/run.log` |
| 每拍 native valid 和新旧查询 mask 对照 | PASS，engine 两份 adapter 各 22929 拍 | 同上 |
| Adapter 九格式/81 配置、连续流 | 81 个配置 PASS，连续流全部零 ingress stall | `adapter/sram/run.log` |
| 完整 65536 strobe 矩阵 | 后台待完成，不把部分穷举记为 PASS | `adapter_full/run.log` |
| 真实 Q4_K M4/N32/K1536 | PASS，7200 cycles | `real_q4/run.log` |
| 真实 Q6_K M4/N32/K8960 | PASS，41939 cycles | `real_q6/run.log` |

33 点的身份与 cycles，以及两个真实切片的 cycles、phase、traffic 行，均与第 14 节
成功日志逐行相同。真实切片两个 adapter 分别完成 7209/41948 拍 valid 位及查询 mask
对照。这里没有把 VCS CPU 时间用于判断硬件性能，也没有重新宣称完整普通 RVV 随机
回归已经通过。

Descriptor 小测试从当前 RTL 原样提取对齐赋值，而不是另外手写同一份 DUT 算式；
参考侧使用原来的逐源字节 scatter。遍历全部 65536 个 16-bit offset，并在十个
边界 offset 下遍历全部 65536 个 strobe。QBS/AKV engine 中另绑定同一参考，检查
真正被实例化的对齐信号。小测试不等价于对整个 engine 状态空间的形式证明。

首次 engine 编译发现新 assign 放在其输入信号声明之前，已移到声明之后。失败日志
保留在 `engine/`、`akv/`，后续成功记录使用 `*_checked/`，不覆盖失败痕迹。
Adapter 的 300 秒完整检查在通过 81 配置后、strobe 穷举中途超时，没有发现 mismatch，
但不能标为完整 PASS。同一二进制在独立 `adapter_full/` 后台目录继续做完整矩阵，
墙钟上限 1500 秒；没有修改 RTL watchdog 或删掉未完成的 strobe。

### 15.3 仍需独立评估

两份局部 DC 展开均 PASS，无 Error；除 adapter 外三个源文件及 Tcl/库配置哈希一致。
下面只比较顶层 adapter，不重复累计其 payload 子模块，后者的展开结果未改变。

| 展开指标 | 改前 | 当前窗口查询 |
| --- | ---: | ---: |
| `**SEQGEN**` 实例 | 2389 | 2389 |
| 4-row/210-bit MUX | 32 | 0 |
| 4-context/292-bit MUX | 32 | 0 |
| 210-to-1 / 292-to-1 位选择 | 32 / 32 | 0 / 0 |
| 53-to-1 / 146-to-1 位选择 | 0 / 0 | 62 / 62 |
| GTECH 实例总数，不含 synthetic operators | 211444 | 173806 |
| 本次局部展开墙钟 | 约 406 秒 | 约 647 秒 |

新实现每个 beat 的窗口经常量裁剪后用到 31 位，因此每类窗口有 `2*31=62` 个
较短选择器，不是完全没有 MUX。GTECH 实例计数减少约 17.8%，不同扇入/类型的实例
并不具有相同面积；SEQGEN 实例也不能直接当最终 FF 面积。报告没有新增运行时 DIV/REM。
顶层仍有 8 条高扇出网络提示，不能据此称时序问题已全部清除。

必须明确：这次展开墙钟反而增加，尚未证明综合提速。新窗口网络仍有 profile/layout
选择及更多编译期布局连线，单次墙钟又受到同机运行负载影响；这些因素的贡献没有
进一步隔离，不能编造耗时归因。保留窗口改写的当前依据是展开网络缩小、状态不增及
功能/周期对照通过，最终映射耗时、面积和关键路径仍需同条件 A/B 确认。
VCS 事件仿真耗时也可能与门级网络规模呈现不同变化，不能拿仿真墙钟当硬件周期。

本轮没有对 AKV 宽地址乘加截位，也没有改 correction 双候选调度。这两处仍需要
对应的资源/关键路径证据，特别是地址溢出与每拍两组 correction 的吞吐不能牺牲。

## 16. 整机 DC 报告驱动的首轮修复（2026-09-12）

### 16.1 本轮依据与范围

9 月 11 日启动的整机 DC 于 9 月 12 日 01:04 完成网表输出，墙钟为 23:25:18。
`clk_i` 最差 setup slack 为 -0.676 ns，约束仍是 1 ns 周期和 0.15 ns setup
uncertainty。最差路径从 `activation_profile_q` 出发，经 bank0 的 pending-byte
提交判断及 `activation_write_ready`，再到 bank1 的 side-metadata 写使能。
终点是自动插入的 ICG 检查点，要求时间 0.650 ns，数据到达时间 1.326 ns；
不能把这条路径当作普通 FF D 端路径，也不能直接用 1/1.326 ns 宣称最高频率。

该报告最差 1000 条路径中，958 条以 payload buffer 为终点，另有 18 条以其他
QBS 逻辑为终点，24 条在其他模块。这个分布只对应报告的前 1000 条，不代表全部
81309 条违例。报告还给出两个经过 QBS/AKV 共享 reader、CVA6 LSU/MMU/PMP 的
组合 timing loop。

本轮硬件只改 `qbs_read_engine.sv` 与 `qbs_payload_buffer.sv`，不修改 profile、
指令编码、buffer 容量、SRAM 端口、计算流水级、主频目标或 clock-gating 约束。
其他已有工作区修改保留，不覆盖 FPGA 导出目录，也不覆盖本轮整机报告和网表。

### 16.2 MMU 返回不能组合地撤销其请求

原 reader 的关系为：

```text
mmu_req = translating && translation_enabled &&
          !mmu_valid && !mmu_exception_valid && !fault_pending
```

CVA6 在 ACC 状态把请求送入 MMU，并将翻译结果和 exception 返回。
其中 PMP/exception 路径可以组合依赖请求，因此上述写法把返回再反相送回请求，
形成组合环。可区分根因的信号是 `plan_state_q`、`mmu_req`、`mmu_valid`、
`mmu_exception_valid` 和 `fault_pending_q`，而不是只观察任务超时。

定向检查先在旧 RTL 上复现：在 285 ns 的返回采样沿，planner 仍等待翻译完成，
但 `mmu_req` 已撤掉，触发 `MMU request withdrawn before response was sampled`。
新实现只用 planner 的寄存状态控制请求：

```text
mmu_req = translating && translation_enabled && !fault_pending
```

成功、异常、PMA 检查仍按原来的顺序处理。返回沿推进 planner，下一周期自然撤销
请求；不插入额外翻译流水级，也不删除 fault drain 或 store-order 检查。
QBS 和 AKV 共用该 reader，因此两条路径同时修复；普通 RVV AddrGen 不在本轮修改范围。

测试覆盖延迟返回，以及请求直接产生组合 TLB/PMP 返回两种 MMU 模型。组合异常用
exception 有效而 success-valid 无效的形式，避免只测试成功返回。测试环境还修正了
响应沿重复受理请求的问题：level request 在响应沿仍为 1 是正常协议行为，不能再
当成下一笔翻译。QBS/AKV engine 的 MMU stub 同步遵守这一规则。

### 16.3 Payload 仲裁保持协议，改为树形选址

旧仲裁按 16 个源字节依次更新 `write_req` 和 `write_addr`。最终语义其实是：
每个 bank 选中第一个候选字节所属的 SRAM word，并提交所有属于该 word 的字节；
旧 pending slot 优先于新 slot。串行地重复判断和更新 word，不是协议所必需。

本轮先通过四级树选择 slot 内编号最小的候选字节，再让 16 个字节并行比较该
word 地址。新 slot 优先继承旧 slot 已选定的 word；只有旧 slot 不请求该 bank 时，
才用自己的首个 word。来自上游 ready 的 live-valid 放在选择结果的门控处，
不再进入每个候选的树形地址选择。数据仍沿用“编号更大、新 slot 优先”的覆盖规则。

必须区分两种优先级：word 的归属由最早候选决定，同一 word 中重叠字节的值由
最新候选决定。本轮不把两者混为同一个优先编码器，也不改变 pending 消耗或下一拍
ready。side metadata 不占用 payload SRAM 的写端口，直接根据 valid、mask、plane、
row 和 offset 生成写使能，避免不必要地经过 SRAM consumed 的归约逻辑。

这些新增数组只是组合连线，不新增 FF 或流水级。该改写针对报告中的长控制路径，
但四级 RTL 树不等于最终只有四级标准单元，更不等于已经消掉全部 setup 违例。

### 16.4 报告脚本和退出状态

| 原问题 | 本轮处理 |
| --- | --- |
| `all_registers` 默认返回 cell，不能直接作为当前 DC 的 `get_timing_paths -from/-to` 对象 | 显式使用 edge-triggered FF 的 output/data pins |
| `-max_paths 1` 会按 path group 返回多条路径，原 summary 写入了三个 slack | 对返回的 slack 求最小值，确保字段是单个数值 |
| `current_design` 对象没有 `area` 属性，导致面积字段为空 | 从同次 `report_area` 的 `Total cell area` 提取，包含 macro 且不重复累计层次 |
| `clk_i` 同时包含 ICG 检查，不便区分 FF-to-FF | 额外生成 `clk_i_reg2reg_max.tim`，保留原 `clk_i_max.tim` |
| Tcl 命令出错但工具仍可走到 COMPLETE | 结束前检查 DC 的 error counter，新增错误使 stage=ERRORS，并以非零状态退出 |

原日志的三条 error 中，两条 `CMD-036` 来自错误的寄存器查询；第三条 `CMD-025`
是本机 DC 启动时的 missing-manual 错误。独立空启动、只执行 `print_message_info`
也能复现这一条，尚未读取库或 RTL。流程现在记录 `DC_STARTUP_MANUAL_ERRORS`，只从
计数中扣除进入流程前已经存在的该类手册错误；流程内新增的 CMD-025 仍会算作错误。
没有全局 suppress 错误，也没有忽略 analyze/link/compile 或报告参数错误。

容器内小设计实际执行了与整机同一段报告 Tcl，面积和两个 slack 均返回单个有效
数值。该测试的数值属于 32-FF 小设计，不是修复后的 QBS 或整机 PPA。

### 16.5 验证记录与限制

独立目录：`hardware/timing_dc_repair_20260912_t9X6PJ/`。`before/` 保存本轮改动前
的两个 RTL 文件和关键脚本。payload 对照的旧模块为 `1b0aec5f`，逐拍检查 SRAM
请求、word 地址、byte enable、最新字节覆盖、consumed mask 和 native 读出视图。

| 检查 | 已完成结果 |
| --- | --- |
| MMU 根因定向检查，旧 RTL | 在 285 ns 按预期失败，确认请求过早撤销 |
| 共享 reader，延迟/组合 MMU 返回 | 两组均 PASS，含跨页、反压、MMU/PMA/AXI fault 和 stalled-AR 排空 |
| 九格式 payload 新旧逐拍对照 | 110592 次检查全部通过 |
| QBS engine，更新后的 MMU stub | 33 个计算点及四类 fault PASS；33 点 cycles 与 9 月 11 日日志逐项相同 |
| AKV engine | D64/D96/D128、分段 D256、尾块、计数器及 fault PASS |
| 真实 Q4_K，M4/N32/K1536 | PASS，7200 cycles，与修前相同；phase 和 traffic 逐项相同 |
| 真实 Q6_K，M4/N32/K8960 | PASS，41939 cycles，与修前相同；phase 和 traffic 逐项相同 |
| DC orchestration 单元测试 | 19 项 PASS |
| synthesis-preflight 单元测试 | 11 项 PASS |
| synthesis collection 单元测试 | 6 项 PASS |
| 实际 DC 报告命令检查 | PASS；使用小设计和相同 TSMC28 库，不重跑整机 compile |

可纳入版本管理的源码哈希、检查清单和前后周期表位于
`verification/timing/results/20260912_dc_repair/`。该记录明确标注了工作区包含未提交
修改，不能只凭 HEAD commit 重建被测 RTL；应同时核对记录中的源码哈希。

上述结果不等价于全部普通 RVV 随机回归，也不能替代整机综合后对 timing loop、
ICG setup、FF-to-FF、面积和违例分布的复查。本轮没有重启整机 DC；现有 -0.676 ns
仍是修复前的报告值，不能当作新 RTL 的结果。

## 17. Pending 容量判断与 SIMD 乘法流水重排（2026-09-12）

### 17.1 两类需要分别处理的路径

继续分析同一份 `clk_i_max.tim`，不能只处理占前 1000 条多数的 QBS 路径：

| 路径 | 原报告 | 本轮针对的结构 |
| --- | --- | --- |
| QBS pending 提交判断，经双 bank ready 到 side metadata ICG | 最差 -0.676 ns | 避免先完成优先仲裁再生成 ready；将 late valid 移到数据选择之后 |
| EW32 SIMD 乘法输入流水寄存器，经乘法及后处理到 VMFPU result queue | -0.675 ns，到达 1.532 ns、要求 0.856 ns | 重新利用已有流水寄存器，分开乘法和累加/舍入 |
| Operand queue 经 VALU 到 result queue | 约 -0.674 ns | 本轮未修改，后续按新整机报告单独核查 |
| C910 div/sqrt 内部 SRT 更新 | 约 -0.674 ns | 本轮未修改，不能用 QBS 优化推断其已经满足约束 |

这里的 ns 均是修改前整机报告值。只消除大量 QBS 路径不一定同步改善 WNS：其他
模块也有接近原 WNS 的路径。新版本必须重新统计整机 WNS、TNS、违例终点数以及
ICG/普通寄存器两类路径，不能只比较报告前几条。

### 17.2 不经过 consumed 的 pending 容量判断

每个物理 bank 每拍只能写一个 SRAM word。旧 pending 一定优先于新输入，因此
本拍能否排空旧 pending，只取决于它是否在同一个 bank 内访问了两个不同 word。
side metadata 不使用该 SRAM 端口，不参加冲突判断。

旧 ready 的组合路径是：

```text
pending 源地址 -> profile/layout 映射 -> 第一个候选 word 的优先选择
              -> 逐字节比较 -> consumed -> remaining 归约 -> ready
```

新实现对每个 bank 的候选集合，并行检查 word 地址的三个位。对于地址位 j：

```text
seen_1[j] = OR(candidate[b] AND word[b][j])
seen_0[j] = OR(candidate[b] AND NOT word[b][j])
conflict  = OR_j(seen_1[j] AND seen_0[j])
```

集合里有两个不同地址，当且仅当至少一位同时出现 0 和 1；因此它与“本拍仲裁后
仍有旧字节未提交”严格等价，而不需要先选中某个 word。空集合、一个字节、重复
写同一地址以及多个 bank 各写自己的一个 word，都不构成冲突。

`qbs_payload_buffer` 新增两个组合输出，将各 bank 冲突归约为 weight/activation
pending 的 multiword 标志。`qbs_block_adapter` 仍按原来的 pending-valid、clear
和 read 条件生成 ready，只将 remaining 判断替换成该标志。标志不依赖新输入的
valid，避免形成 ready/valid 组合反馈。原来的 word 优先级、consumed、剩余 strobe
保存方式和下一拍 pending 数据均未改变。

Adapter 内保留仿真断言，每拍直接比较新 ready 与旧 remaining 公式；payload miter
还将新冲突标志与旧参考模块的 consumed 比较。这样能在 ready 首次产生不同结果的
周期报错，而不是等最终计算结果出错才发现问题。

### 17.3 将 late valid 放到最后一级

旧路径把 `source_valid` 放进每个字节的 hit，再让 hit 驱动四级/五级数据选择树。
当 source-valid 本身来自跨 bank ready 时，写入控制到得很晚，后面仍有完整的数据
选择网络。

新实现先根据地址、mask 和 bank 归属选好每个 slot 的字节；最后才用该 slot 的
valid 产生 byte-enable，并在两个 slot 之间选择新数据还是旧数据。side metadata
也分别完成两个 16-byte slot 的选择，再应用 valid，仍然是有效新 slot 覆盖旧 slot。
旧 slot 不命中时不写，新 slot 无效时不能覆盖旧数据。

这两项 QBS 改写只增加组合逻辑，不新增寄存器、存储端口或执行周期。

### 17.4 乘法与后处理之间使用已有寄存器

`LatMultiplierEW16/EW32/EW64` 当前都是 1，EW8 是 0。原 `simd_mul` 的内部一拍
仅延迟 A/B/C 和控制，之后才执行完整乘法、乘加/乘减、VSMUL 舍入和输出选择：

```text
原：VMFPU 输入寄存器 -> A/B/C 内部寄存器 -> 乘法 + 后处理 -> result queue
新：VMFPU 输入寄存器 -> 乘法 -> product/C 内部寄存器 -> 后处理 -> result queue
```

本轮没有增加 `NumPipeRegs`，也不修改 VMFPU、sequencer 的延迟参数、发射规则或
结果队列。原 A/B 共 128 bit 改为 128-bit 乘积；C、op、mask、valid 仍按同一个
stage-ready 推进。反压时所有相关状态共同保持；有 bubble 时仍遵循原弹性流水行为。
`NumPipeRegs=0` 保持组合实现。

VSMUL 的特殊饱和值来自两个最小负数相乘，需要将这一判断与乘积一同保存。每个
元素只保存一位，而不是保存全部原操作数或每个 byte 重复保存：当前 EW16/EW32/EW64
合计每 lane 增加 4+2+1=7 个状态位，四 lane 为 28 位；这是 RTL 状态位数，不是
综合面积结论。输出时按元素的 byte 数展开 vxsat。

符号扩展、VMULHSU 的操作数方向、乘积截断、累加/减法、四种 VXRM、饱和结果和
mask 的语义保持原样。VXRM 仍按原实现从输出侧读取；本轮没有顺便改变其 CSR 契约。

### 17.5 验证与独立综合

本轮目录：`hardware/timing_ready_20260912_kF6fVT/`。其中 `before/` 保存进入本轮时
的源码，包含第 16 节修复，不是第 16 节之前的旧 RTL。

| 验证项 | 已确认结果 |
| --- | --- |
| 九种 profile 的 payload 新旧逐拍对照 | PASS，110592 次检查，含新 multiword 输出对旧 consumed 的检查 |
| Adapter 连续写入 | 81 组全部 PASS，stalls=0，涵盖 M1/M3/M4/M5..8 及布局变化 |
| Adapter 非连续/重复写 | PASS，仍为 4 次必要停顿 |
| Adapter 全 65536 种 strobe | 五分钟运行预算到期时未出现功能错误；同一 binary 在 `adapter_full/` 后台继续，不能提前记为全量 PASS |
| QBS engine | 33 个计算点及四类 fault PASS，33 点身份和 cycles 与第 16 节逐项一致 |
| Q4_K 真实 M4/N32/K1536 | PASS，7200 cycles；phase/traffic 相同 |
| Q6_K 真实 M4/N32/K8960 | PASS，41939 cycles；phase/traffic 相同 |
| SIMD MUL | 24 组配置全部 PASS；196296 次逐拍对照，84464 个独立算术模型结果检查 |

SIMD MUL 的 24 组配置为四种 SEW、0/1/2 拍和定点开关的笛卡尔积。激励包含全部
受支持乘法操作、符号边界、VSMUL 极值、四种 VXRM、不同 mask、随机数据、长反压、
bubble、在途 reset 和最后排空。对比 valid/ready、数据、mask 和 vxsat，不仅检查
最终若干输出。定点关闭的配置不投放不受支持的 VSMUL。

局部 DC 在容器内使用真实 RTL、TSMC28 库、1 ns/0.15 ns 约束及与整机一致的
CKLNQD4 clock gate 和 0.2 ns gating setup。运行前分别复制源码和脚本，避免工作区
后续修改改变正在进行的 A/B 实验：

| 目录 | 范围 |
| --- | --- |
| `dc_before/`、`dc_after/` | 真实双 adapter ready 广播到 metadata 的局部路径；只观察旧最差终点对应字节，非完整 engine PPA |
| `mul_dc_before/`、`mul_dc_after/` | EW32 乘法及输入/输出寄存边界，包含内部一拍，非完整 lane PPA |

每个 DC worker 自带一小时上限，状态记录在各目录 `status.json`。这两组局部结果
不能直接替换 `backend/syn/.../reports/clk_i_max.tim` 或宣称整机满足 1 GHz。
整机原报告和网表保留；局部映射完成后还需用整机综合确认剩余 VALU、div/sqrt 以及
新关键路径。本轮没有为得到好看的 slack 放宽 uncertainty、clock-gating setup，
也没有把真实同步路径设为 false path。

版本记录保存在 `verification/timing/results/20260912_ready_mul/summary.json`，包含
三个修改模块和测试文件的哈希、33 点周期、已完成检查及局部 DC 启动状态。后台状态
是归档时刻的快照，后续应读取运行目录中的最新 `status.json` 和结束标记。

## 18. 基于新整机报告的组合路径优化（2026-09-13）

### 18.1 报告与修改前源码对应关系

本轮使用 `backend/syn/ara_soc/v1-dc/reports/clk_i_max.tim` 和 `qor.rpt`，
报告日期为 2026-09-13。开始修改前，已将 `hardware/src` 和 `hardware/include`
的文件哈希与 `hardware/dc_runs/20260912_120931_ready_mul/source_manifest.json`
逐项核对，一致；因此这些路径对应本轮修改前的源码，而不是更早的综合网表。

| clk_i 指标 | 修改前报告值 |
| --- | ---: |
| 时钟周期 | 1.000 ns |
| Setup uncertainty | 0.150 ns |
| Hold uncertainty | 0.075 ns |
| Clock-gating setup | 0.200 ns |
| 最差 setup slack | -0.658 ns |
| 最差路径到达时间 | 1.513 ns |
| Setup TNS | -27295.217 ns |
| 报告中的 setup 违例路径数 | 81244 |
| 最差 hold slack | -0.154 ns |

81244 是 `clk_i` 分组的报告统计，包含 SRAM 和 clock-gating 路径，不能全部称为
普通 FF-to-FF 违例。这里的报告已经生成，但原整机 DC 当时仍停留在后续 REPORT
阶段，不能据此认定 `outputs` 中的旧网表已被更新。

### 18.2 为什么同时处理多类路径

新报告中多个执行单元的 slack 相近。只处理 QBS 或只处理最差的一条乘法路径，
其他模块仍可能决定 WNS。本轮按实际 cell arc 检查了以下代表路径：

| 路径 | 修改前 slack | 实际发现及本轮处理 |
| --- | ---: | --- |
| EW64 SIMD MUL 已寄存的 product/op 到 VMFPU result queue | -0.658 ns | 乘法后仍有长串进位；重构乘加、乘减和定点舍入的加法网络 |
| C910 VFDSU EX3 格式控制到 EX4 fraction | -0.657 ns | 格式/denormal 选择后再经过 55-bit 加减；保持选择逻辑，缩短加减进位 |
| Operand queue 到 VALU result queue | -0.656 ns | ALU 输入约 0.326 ns 到达，结果约 1.470 ns 到达，中间有数十级进位 cell；改写 ALU 加减及舍入 |
| QBS payload SRAM 到整数 dot 输出寄存器 | -0.652 ns | SRAM 读出约 0.292 ns，decode 输出约 0.662 ns，dot 终点约 1.498 ns；去掉求和树中重复的全宽进位 |
| AddrGen 长度寄存器到下一 burst 地址 | -0.646 ns | 长度加减、对齐和地址推进串联；保留 AXI 边界算法，替换宽加减实现 |
| Sequencer opcode 到 AKV fill tile count | -0.635 ns | mode 选择进入宽减法/比较；先并行比较两个常数上限，最后选择模式 |

这些 ns 是修改前整机的实测值，不是新 RTL 的预计值。最差路径附近仍有一条
`CVA6 LSU/MMU -> AddrGen ack -> sequencer ready -> dispatcher response ->
CVA6 issue ack -> scoreboard ICG` 的组合反馈路径，约 -0.657 ns，本轮没有改变其
握手契约。算术路径缩短后，该控制链仍可能限制 WNS。

### 18.3 保持延迟不变的算术重构

`ara_pkg` 增加组合函数 `prefix_add65`、`prefix_sub65` 和 `prefix_add3_65`。
每四位计算局部和以及 group generate/propagate；组间用五层前缀网络求进位，最后
选择该组有进位或无进位的局部结果。这样避免 64-bit 数据逐位经过一条长进位链。
第 65 位用于保留 SEW64 的进位、借位和带符号 averaging 中间结果。窄 SEW 的调用
按原来的位宽截断，不修改饱和、符号扩展或舍入定义。

三操作数场景先做 carry-save 压缩，再完成一次 carry-propagating addition：

```text
sum_bits   = a XOR b XOR c
carry_bits = ((a AND b) OR (a AND c) OR (b AND c)) << 1
result     = prefix_add(sum_bits, carry_bits, carry_in)
```

`simd_mul` 保留第 17 节已经调整好的 product 寄存位置，仅改写后面的乘加、乘减、
VSMUL 舍入。`simd_alu` 保留所有 opcode、mask、VXRM 和饱和选择，只替换对应算术。
两者都不新增流水级，不更改 valid/ready，也不修改 sequencer 的延迟参数。

QBS dot array 仍使用原来的 32 个 INT8 乘法位置和一个输出寄存器。M1 的八项求和
与 M2 的四项求和先逐级压缩为两个数，最后才传播一次进位；M3/M4 的两项求和保持
原实现。八个 `(-128)*(-128)` 的和为 +131072，仍保留 19-bit 有符号结果，避免
再次丢失极值。输入选择、stream mask、无效输出清零和延迟均未改变。

VFDSU 不能直接导入后编译的 `ara_pkg`，因此在原 Verilog 模块中使用独立的
`round_add55`，以 14 个四位组、四层前缀网络替代 `frac_add1_rst/frac_sub1_rst`
的加法。IEEE 舍入方向、格式选择、denormal 判定、exception flags 和所有寄存器
均保持原样。这不是更换浮点数值算法，也没有调整累加顺序。

### 18.4 地址与 AKV 的等价边界

AddrGen 保留原来的 burst 长度上限、AXI beat 对齐和 4 KiB 分割算法，仅将
`addr + num_bytes - 1` 等表达式映射为 carry-save/prefix 运算。地址宽度不超过
64 时使用新实现；更宽参数保留旧分支。零长度、地址回绕、跨页以及不同 AXI 数据
宽度均包含在对照测试中。本轮不修改 MMU 请求/应答和 AXI 握手。

AKV descriptor 的 `kv_length` 为 16 位。原有的全地址宽度检查仍首先要求
`tile_start < kv_length`，所以只有通过检查的命令才能提交新的 fill count。
在该前提下，两者的差也可用 16 位无损表达，不需要让完整虚拟地址宽度参与减法。
新逻辑分别计算 `min(remaining, 8)` 和 `min(remaining, 64)`，最后根据模式选择；
高位非零的非法 tile 地址仍由原检查拒绝。FULL 与 REFILL 都使用相同的计数函数，
但 context 检查、fault 和响应仍沿原路径完成。

### 18.5 已完成的验证及性能边界

独立目录为 `hardware/timing_closure_20260913_CnSzZc/`，修改前源码保存在 `before/`。
VCS 在宿主机运行，DC 在 `synopsys_workspace` 容器内运行，没有覆盖原整机目录。

| 检查 | 结果 |
| --- | --- |
| 新加减函数与 ALU 对照 | PASS，143970 次算术检查，覆盖四种 SEW、VXRM、mask、饱和和截断 |
| QBS dot 新旧逐拍对照 | PASS，192000 个输出比较，含 INT8 极值、模式变化和 reset |
| SIMD MUL 新旧逐拍及独立算术模型 | PASS，24 配置、196296 次逐拍检查、84464 个退休结果检查 |
| AddrGen 原函数/新函数对照 | PASS，12 配置、144000 次检查 |
| AKV 剩余长度 | PASS，151168 次检查；穷举 16-bit 剩余值，另含高位非法地址及随机起点 |
| AKV 完整 engine | PASS，D64/D96/D128/分段 D256、row/column、尾块、计数器和 fault |
| VFDSU 完整 round 模块 | PASS，30000 拍，比较全部 25 个输出，包括异常标志 |
| 九种 QBS profile | PASS，448 组 |
| QBS 完整 engine | PASS，33 个计算点及四类 fault；33 点身份和 cycles 与上一轮完全一致 |

真实输入来自 Qwen2.5-1.5B 的 llama.cpp capture，保留完整 K，仅截取有限的输出行
和 token 数。下面是 QBS engine 的 RTL 周期，不是整模型 token generation 周期：

| 真实 profile / 算子 | M / N / K | 修改后 cycles | 修改前直接对照 |
| --- | --- | ---: | --- |
| Q4_K / attention Q projection | 4 / 32 / 1536 | 7200 | 7200；phase 和 traffic 相同 |
| Q4_K / attention Q projection | 8 / 16 / 1536 | 7638 | 本轮功能回归，未存本次修改前的同形状直接测量 |
| Q4_K / attention Q projection | 7 / 16 / 1536 | 7612 | 同上，包含 M 尾块 |
| Q6_K / FFN down projection | 4 / 32 / 8960 | 41939 | 41939；phase 和 traffic 相同 |
| Q6_K / FFN down projection | 8 / 16 / 8960 | 44493 | 本轮功能回归，未存本次修改前的同形状直接测量 |
| Q6_K / FFN down projection | 7 / 16 / 8960 | 44479 | 同上，包含 M 尾块 |

这轮目标是缩短同一个执行周期内的组合延迟，不是减少算法执行周期。已验证的
周期不变，与这个目标一致；它既不是性能加速比，也不是整机 Fmax 的证明。

## 19. Dispatcher 的晚到 ready 路径

### 19.1 报告中的实际路径与根因

2026-09-13 的整机 `clk_i_max.tim` 中，除上一节的算术路径外，仍有约
-0.657 ns 的控制路径：

```text
CVA6 LSU valid -> MMU exception -> AddrGen ack
  -> VLSU/sequencer ready -> dispatcher response valid
  -> CVA6 issue ack -> scoreboard ICG enable
```

该条报告中，sequencer 的 ready 到达 dispatcher 输入约为 0.515 ns；经过
dispatcher 后，response valid 到达约为 1.092 ns。也就是说，dispatcher 内部
又增加了约 0.577 ns 的组合延迟。这是普通向量访存的路径，不是 QBS 点积阵列。
这些数值来自修改前整机报告，不能作为修改后局部综合或整机的结果。

旧 `p_decoder` 将 `ara_req_ready_i` 放在整个普通译码块的入口条件中。只有
`req_valid && resp_ready && ara_req_ready_i` 成立才计算 opcode、操作数布局、
合法性、reshuffle 和最终响应。因此，晚到的 ready 会经过后续译码与安全选择逻辑，
再返回标量核。根因假设是：把 ready 从入口条件移到提交结果的选择位置，能够
缩短这条反馈路径，而且不必插入新的流水级。

可区分该假设的证据有两项：新旧 RTL 在相同输入下逐拍一致；相同约束下，
`ara_req_ready_i -> response_valid_o` 的映射后路径缩短。只有前者通过，不能
证明后者；局部路径缩短也不等于整机所有 setup/hold 违例已经消除。

### 19.2 RTL 如何改写

普通请求先计算译码结果，最后根据 backend ready 决定是否提交。这里的“先”与
“最后”均指同一个周期内的组合逻辑，不是额外的周期，也不是提前退休指令。

```text
指令、标量操作数、CSR/布局状态 -> 译码与安全检查 -> 候选结果
                                                     |
backend ready -------------------------------------> 提交选择
                                                     |
                                       应答、next state、segment 请求
```

`ara_dispatcher.sv` 中的对应修改为：

- `init_decoder_outputs()` 集中原有默认赋值。普通译码因 backend 阻塞不能提交时，
  恢复这些默认值，保留 CSR、布局、snapshot、pending segment 等已注册状态。
- `decode_blocked` 只覆盖原本允许进入普通译码的状态。RESHUFFLE、snapshot wait、
  overlap respond 等特殊状态仍执行原状态机；不会被统一的阻塞处理覆盖。
- `ara_req` 仍为本地译码和布局 helper 提供候选值；`ara_req_committed` 才送到
  segment sequencer。阻塞时后者选择与旧 RTL 相同的 idle bundle，避免无效候选
  改变 segment 的回包、计数与访存行为。
- `prepare_reshuffle()` 复用原有 reshape 状态准备代码。旧 RTL 在没有接受新请求
  时，仍可能推进一个已经 pending 的 reshuffle；新实现保留该行为，而不是简单
  将全部 next state 固定为当前值。
- 请求 token、输出请求寄存器的使能、zero-VL 完成碰撞处理、成功响应后的 vstart
  清零，以及实际握手后的验证序号推进均保持原有规则。

该改动不增加请求队列、寄存器或流水级，不放宽 RAW/WAR/WAW、MMU、segment、
异常恢复和寄存器布局约束。阻塞周期中组合译码仍可能切换，因此不能仅凭结构
等价声称功耗也不变；目前没有对此做功耗测量。

### 19.3 已完成的逐拍检查

独立目录为 `hardware/timing_dispatch_20260913_RTu2k0/`，修改前的实际工作区
dispatcher 已保存为 `ara_dispatcher_before.sv`，不是用更早的 Git HEAD 代替。
测试类型直接从 `ara.sv` 的真实接口提取，并调用 SoC 使用的
`build_config_pkg::build_config()`，配置为 4 lane、VLEN=1024。

| 配置 | 比较周期 | backend 阻塞采样 | 前端接受请求 | 结果 |
| --- | ---: | ---: | ---: | --- |
| QBS / AKV / AKV-v2 开启 | 67040 | 13478 | 25379 | PASS |
| QBS / AKV / AKV-v2 关闭 | 67040 | 13689 | 26028 | PASS |

每拍比较全部 dispatcher 外部输出和 70 组已注册状态，包含 segment sequencer
状态与两个计数器。输出比较不仅限于 valid=1，握手控制还检查无未知值。
66,560 拍混合激励覆盖 SEW/LMUL、vset、普通及 segment 访存、FOF、CSR、整数/浮点
向量指令、非法编码、ready 阻塞和异步 lane flags。另有 480 拍直接设置一致的
新旧状态后放开寄存器，覆盖全部 15 个状态、8 种 pending-reshuffle 掩码及
ready/valid 组合。这一部分是状态逻辑对照，不声称这些强制状态全部能由合法
指令自然到达，也不是形式等价证明。

复现完整机制配置的检查：

```bash
cd verification/timing
make dispatcher-check \
  DISPATCHER_BEFORE=../../hardware/timing_dispatch_20260913_RTu2k0/ara_dispatcher_before.sv \
  BUILD=../../hardware/timing_dispatch_20260913_RTu2k0/recheck
```

加 `DISPATCHER_FEATURES=` 可检查关闭三项扩展的配置。

### 19.4 综合和整机回归的边界

`dc_before_r2/` 与 `dc_after_r2/` 为容器内独立的完整 dispatcher 综合，使用相同
TSMC28 库、1 ns 时钟、0.15 ns setup uncertainty 和 0.2 ns clock-gating setup。
输入/输出均保留，未通过固定 opcode、ready 或特殊状态来缩小设计。两者均已
通过分析、elaboration 和 link；新增函数未报 latch 推断错误。映射结果另行确认。

局部脚本除了常规报告，还生成 `ready_to_response.rpt` 与
`completion_to_response.rpt`，分别检查 ready 和后端完成信号到标量响应的路径。
两者都可能出现在整机反馈链中，不能只优化 ready 而忽略 completion。
局部 input delay 为 0.5 ns，阅读到达时间时须区分外部输入延迟和模块内部延迟；
不要把局部输出约束产生的 slack 直接当成整机的 scoreboard ICG slack。

整机 VCS 代表回归在同目录下的 `rvv_regression/` 后台运行，保留 QBS/AKV/AKV-v2，
选取 AXPY、vsetvli、widen overlap、segment EMUL、非法 segment 恢复及 mask memory
EMUL 六项。启动和编译不计为 PASS，以该目录的最终 `summary.json` 为准。
没有覆盖或重启正在运行的整机 DC，也没有改变 uncertainty 或添加时序例外。

### 18.6 可复现记录与仍待确认的项目

`verification/timing/results/20260913_closure/summary.json` 保存源码/测试哈希、
33 点周期、六个真实数据点的周期与访存计数，以及独立 DC 的启动状态快照。
局部 A/B 分别为 EW64 MUL、ALU、QBS compact decoder + dot、VFDSU round；都固定
1 ns 周期、0.15 ns setup uncertainty 和 0.2 ns clock-gating setup。

| 子目录 | 对比范围 |
| --- | --- |
| `mul_before` / `mul_after` | EW64 乘法及原有输入/输出寄存边界 |
| `alu_before` / `alu_after` | 完整 ALU 和 rounding，外围寄存器不含 operand queue 的转换网络 |
| `dot_before_fixed` / `dot_after` | 真实 compact decoder 到 dot，不含 SRAM 宏延迟及整机布线 |
| `round_before` / `round_after` | 真实 VFDSU round，保留 gated-clock cell |

`dot_before` 是最初 wrapper 的 DC 语法错误记录，不是有效 baseline；修正 wrapper
后另用 `dot_before_fixed`，未把失败记录覆盖成成功。各 worker 有一小时上限，并
检查退出码、Error/Fatal 和完成标记，当前状态以所在目录的 `status.json` 为准。
归档时八个有效 worker 仍在运行，尚无新整机 WNS/TNS 或面积结论。

外部依赖中的 VFDSU 修改另存为
`hardware/patches/fpnew/vfdsu_round_prefix.patch`，应用与检查方式见同目录 README。
新建依赖工作区时需应用该补丁；不能只提交父仓库中的 RTL 而遗漏外部依赖。

本轮新增流水级和 RTL 状态位均为零，但组合面积及实际映射效果仍需 DC 量化。
必须保留以下边界：跨模块 ready/ack 到 ICG 路径尚未关闭；其他 div/sqrt SRT 路径
需要查看优化后的排序；hold、真实 clock tree 和布线问题没有通过本轮组合改写完成
闭环。局部结果不能替代整机寄存器、SRAM 和 ICG 路径的重新统计。本轮没有放宽
uncertainty，也没有将真实同步路径排除出时序分析。

随后完成的 `round_after` 局部 DC（报告时间 01:43）中，`clk_i` setup TNS 为 0、
setup 违例数为 0；最差 FF-to-FF 到达时间 0.8327 ns，要求时间 0.8335 ns，
余量约 0.0008 ns。该局部结果仍有 78 条 hold 违例，最差约 -0.05 ns；不能称为
setup/hold 全部收敛，也不能据此替代整机结果。此时 `round_before` 尚未完成，
所以还没有同边界的前后时序改善比例。`mul_before` 也已完成，其局部 `clk_i`
setup 本身已满足约束，说明独立小模块与整机的优化条件不同，不能混用这两类数值。

## 20. 浮点反馈、延迟判定和 QBS 请求通路优化

### 20.1 根据整机报告确定范围

本轮目录为 `hardware/timing_feedback_20260913_x9goNT/`。`before/` 保存修改前
的真实工作区文件，而非用 HEAD 代替未提交的上一版。沿用 1 ns 时钟、0.15 ns
setup uncertainty，不修改时序例外，不增加执行流水级。

旧整机报告中的相关路径为：

| 路径 | 旧报告 slack / ns | 本轮改动 |
| --- | ---: | --- |
| FPnew 结果仲裁、tag 操作数、前导零检测及估计后处理，再反馈至 FPU 输入 | -0.652 | 归约反馈不再经过通用结果后处理 |
| VMFPU 下一条指令选择、延迟解码及比较 | -0.641 | 各队列项并行解码，提前形成冲突矩阵 |
| QBS 校正 RR 指针、两次串行选择、乘法、subtotal 累加 | -0.610 | 两个 grant 并行生成，保留两条共享校正算术通路 |
| QBS 行号、block index、字节偏移、读地址 FIFO | -0.610 | 在描述符验证阶段寄存行跨度，将两个乘法并行化 |

这些是修改前路径的数值，不是本轮测出的改善量。另有 SRT 余数迭代、UART AXI
splitter、sequencer hazard 生成以及跨 CVA6 的控制链，不能因修改了上述四处就
宣称所有违例已经处理。

### 20.2 归约反馈与普通结果写回分离

`vmfpu.sv` 的 lane 内归约会在没有已缓存部分结果时，直接把当拍 FPU 返回值
作为下一次归约的输入。旧写法从 `result_queue_d[].wdata` 取值，该值来自通用
`vfpu_processed_result`，把 `vfrec7/vfrsqrt7` 和比较结果处理也连到了反馈路径。

新写法只在这两个当拍反馈位置使用 `vfpu_result`，其他结果队列写回、异常标志、
mask、ordered reduction、SLDU 交换和退休规则均不变。它不是允许不同浮点指令
乱序混用结果。原状态机要求开始归约时前序指令已经完成，并在归约提交前保持
独占；归约的返回值不需要估计指令或比较指令后处理。

仿真断言在 lane 内归约收到有效结果时检查：processing 操作确实为归约，且原始
结果与通用处理结果完全一致。因此，若所有权条件被其他修改破坏，测试必须报错，
不能把错误的返回值静默送回算术单元。结构变化本身不增加等待周期。

### 20.3 VMFPU 延迟冲突提前计算

原写法先用下一拍 issue/processing 指针选择完整指令，再按 opcode、SEW 解码
延迟并比较。指针会受当拍执行单元 ready 和完成条件影响，因而晚到的控制信号
之后还串接了指令选择和分类比较。

新写法对四个 `vinsn_queue_d` 项分别解码延迟，组合地产生 4x4 的冲突判断；晚到
的两个指针只选择其中一位。这里使用的是 `_d` 队列，保留同拍接收、写入和指针
推进的原语义，不是错误地用旧 `_q` 元数据替代新请求。矩阵没有增加寄存器。

低延迟操作不能越过高延迟操作、不同 SEW 的乘法保护、变延迟 div/sqrt 保护、
`latency_problem_q` 和原过渡周期防护全部保留。仿真逐拍按旧表达式重新计算，
断言新选择结果与旧判断相同。

### 20.4 QBS 两路校正选择

旧逻辑先优先编码第一个 pending slot，再清除该 slot，计算第二次扫描起点，
重新掩码并优先编码第二个 slot。之后才进行 slot 数据选择和乘加校正。

新逻辑把 RR 指针以上和以下的 pending 集合分别处理。平衡前缀树记录每个前缀
是否至少有一个或两个请求，在同一轮组合逻辑中得到两个位置；最终按循环顺序
合并上下半区的结果。保留原先的 first/second 次序、RR 更新和每拍最多两个
consume，不是改成固定优先级，也没有扩展成 32 路乘法。

测试直接从新旧 RTL 提取选择逻辑，检查全部 32 个 RR 位置、所有不超过三个
置位的 pending 组合、全满情况及随机密集组合，另用独立的循环扫描核对。
225680 组检查通过。完整 profile/engine 测试进一步比较每拍结果、握手和计数器。

### 20.5 QBS 行跨度预计算

对于 row-major，旧偏移为 `(row * k_blocks + k) * block_bytes`；R4 则为
`((floor(row/4) * k_blocks + k) * 4) * block_bytes`。

新实现接收有效描述符时寄存 `row_bytes = k_blocks * block_bytes`，请求阶段
并行计算 `row * row_bytes` 与 `k * block_bytes`，最后相加。R4 的分组及乘四
保持不变。weight 和 activation 各保存一份 25 位行跨度，共新增 50 位状态；
没有新增请求阶段，也没有改变读请求顺序、lookahead、tag 或 fault 规则。

位宽根据输入接口而非某一个模型确定：K block 数是 9 位，block 字节数是
16 位，两者乘积保留 25 位；逻辑行号保留 7 位，K index 保留 8 位。偏移使用
32 位，最终与原 64 位基址相加，再按原规则转换到虚拟地址宽度。测试包含字段
最大值、高地址和加法回绕；67571 个地址输出周期与旧算式一致。描述符本身的
合法性、越界和地址检查仍由原 decoder 完成。

### 20.6 复现及结果边界

```sh
make -C verification/timing feedback-check \
  BEFORE_DIR="$PWD/hardware/timing_feedback_20260913_x9goNT/before" \
  BUILD="$PWD/hardware/timing_feedback_20260913_x9goNT/check"
```

`generate_feedback_checks.py` 提取的 before/after cone 分别用于 VCS 比较和局部
DC，对照使用相同约束。地址 wrapper 包含描述符行跨度预计算寄存器，但没有包含
整个 descriptor decoder 和整机布线；校正 wrapper 只衡量选择器，不等于完整
的选择、乘法和 subtotal 通路。必须分别看局部结果和整机报告。

独立后台回归由 `verification/timing/run_feedback_regression.py` 启动，包含六种
浮点归约、两种估计、除法/平方根、乘加、widening 边界及 AXPY，共 14 个测试。
结果目录保存源码哈希，若回归期间 RTL 变化则标为 INVALIDATED。后台任务确认
启动后不做长时间轮询。当前结果以本轮各目录的日志和 `status.json` 为准；功能
通过不自动代表时序通过，局部 DC 通过也不代表整机 1 GHz 已经收敛。

### 20.7 发现并修正组合过程的触发遗漏

第一次整机回归的六种归约和两种估计测试通过，但新增 latency 对照断言在
AXPY 等点失败。未放宽断言，也没有通过改变 timeout 或软件规避。
`latency_probe/probe.log` 保留 VCS UCLI 逐时刻采样：AXPY 的 462 ns 时刻，
issue 指针由 0 推进到 1，processing 指针仍为 0；两项延迟分别为 2 和 4，
矩阵 `[1][0]` 已为 1，但 `latency_problem_d` 仍为 0。

原因是初稿把矩阵选择留在了写入 `vinsn_queue_d` 的 `always_comb` 中。
只变化指针而矩阵内容不变时，该过程不会因自己写入的指针重新触发，导致仿真
中的选择结果滞后。最终实现把指针选择放在独立连续赋值中；这样指针或矩阵
变化都会更新选择，且没有组合反馈到写指针的过程。原逐拍断言继续保留。

修正版 `rvv_r2/focus` 的 AXPY 已 PASS，然后才启动同一 simv 上的 14 点回归。
首轮失败日志留在 `rvv/`，不能与修正版结果混为一次全通过记录。
QBS 的 448 个 profile 点、33 个完整计算点及四类 fault 均已 PASS，完整计算
点的周期与前一轮记录相同。

整机 DC 使用 `verification/timing/run_snapshot_dc.py` 创建的
`soc_dc/backend/syn/ara_soc/v1-dc/`。406 个 RTL 源文件及 include headers
均复制到独立快照，原 DC 脚本和 SDC 不变；静态 preflight 已确认 1 ns、
0.15 ns setup uncertainty、QBS/AKV-v2、真实 CVA6 和 SRAM macro 配置。
后台 worker 只有在修正版回归 PASS、源码哈希相符、QBS 计算与 fault 检查通过后
才启动 DC。等待状态不是已开始综合，最终报告也不会覆盖原 `backend/syn`。

### 20.8 已得到的局部综合及真实输入结果

四个局部 DC 均已完成，无综合 Error/Fatal。寄存器路径对比如下：

| 局部 wrapper | 修改前最差 FF 到达时间 / ns | 修改后 / ns | 修改前 cell area | 修改后 cell area |
| --- | ---: | ---: | ---: | ---: |
| 两路校正选择器 | 0.8351 | 0.8321 | 517.272 | 662.088 |
| QBS 地址计算 | 0.8388 | 0.8366 | 2231.544 | 2557.296 |

这是约束驱动映射后的局部结果：最差时间只改善数 ps，面积增加，不能据此宣称
大幅时序改善，也不能把这些小 wrapper 的面积增长比例套到整个处理器上。
特别是选择器 wrapper 没有覆盖后面的乘法和 subtotal 更新。新结构是否降低整机
长路径，需要由完整 SoC 报告裁决；不能只比较 RTL 表达式的层数。

六个真实 Qwen2.5 输入切片均通过，新 `real/summary.csv` 与
`hardware/timing_closure_20260913_CnSzZc/real/summary.csv` 完全相同：
cycles 依次为 7200、7638、7612、41939、44493、44479，weight/activation/payload
字节数及 range、dot、prefetch wait 统计也全部相同。这证明这些已测点没有周期
和访存流量退化，不证明未测 workload 或整机物理实现也相同。

修正版的完整 14 点整机回归随后全部 PASS，latency 对照及归约反馈断言均保留。
结果归档为 `verification/timing/results/20260913_feedback/rvv_regression.csv`。
独立整机 DC 已在 2026-09-13 10:15:08 UTC 通过回归门槛并启动，确认正在分析
`soc_dc/sources/` 中的冻结源码。此时没有新的整机 WNS/TNS，不能提前填写改善
比例或宣布 1 GHz 时序收敛；后续查看该独立目录下的报告，不混用原目录旧结果。

## 21. QBS 点积与校正流水化

### 21.1 选择这两条路径的原因

在允许少量周期增加后，本轮不再只重写组合表达式，而是拆开两个已由旧整机
报告定位的长路径：payload SRAM 经格式解码、INT8 乘法和求和到 dot 寄存器，
以及校正 RR 选择经 slot 读取、乘法和 subtotal 累加到 subtotal 寄存器。
旧报告对应 slack 分别为 -0.652 ns 和 -0.610 ns，详见第 18、20 节。
这些数值属于旧整机，不是上一节局部 wrapper 的数据，也不是本轮改善量。

假设是：即使改进优先编码和进位结构，串在同一周期内的存储器读出、选择、
乘法及加法仍限制频率。用寄存器分开这些运算，可以缩短每级组合路径；代价是
流水填充与排空变长。保持每周期的接收能力，才有机会让长块工作负载的周期
代价较小。本轮先核对数据、标签、context 释放和 fault 排空，再实施并测试。

### 21.2 两处 RTL 修改

| 模块 | 修改前 | 修改后 | 不变的能力 |
| --- | --- | --- | --- |
| `qbs_dot_array.sv` | 解码输出直接经过乘法、求和，再寄存输出 | 寄存解码值；寄存乘积；寄存归约结果，共三级 | 32 个 INT8 乘积通路，每周期可接收一批 |
| `qbs_profile_engine_int.sv` | 选择 slot、乘法、subtotal 更新在同一周期 | 选择并寄存操作数；乘法并寄存；subtotal 更新，共三级 | 两条共享校正通路，每周期最多两项校正 |

没有增加乘法器数量，没有新增 SRAM，没有改变浮点运算和累加次序。
普通 RVV 与 AKV 的 RTL 未改，QBS 的指令编码、描述符、profile、布局、维度
契约及软件接口也未改。时钟仍为 1 ns，setup uncertainty 仍为 0.15 ns，
没有添加 multicycle/false-path 例外。

增加的声明状态位如下。它们是按 RTL 字段计算的位数，不是 DC 映射后的面积。

| 部分 | 新增状态位 |
| --- | ---: |
| dot 解码值、乘积及两级有效位/形状/stream mask | 1070 |
| dot context、group、scale、min、aux 的标签对齐 | 255 |
| 两条校正通路的操作数级与乘积级 | 236 |
| 合计 | 1561 |

### 21.3 保持正确性的关键条件

1. **数据和标签同时前进。** `DotLatency=3`，context、group index/end、scale、
   min、aux 与 dot 同步延迟。断言逐拍检查 dot valid 与末级 metadata valid
   一致。不能只推迟数值而仍使用当前 decoder 的标签。
2. **填槽和释放槽的顺序不变。** 校正 grant 在捕获 slot 操作数时释放该 slot，
   此后由流水寄存器持有数据。同一周期允许消费旧 group 并填入新 group；
   slot 的新填入操作保留原来的赋值优先级，不会被消费操作清空。
3. **累加时读取最新 subtotal。** 选择级不缓存 subtotal，最终提交级才读取并
   累加。相邻周期属于同一 stream 的校正能看到前一次更新。断言禁止两条
   校正通路同周期写同一 context/stream，避免丢失其中一次更新。
4. **最后一组真正提交后才能报告结果。** `result_pending` 在 last group 的
   校正提交时置位，不在 grant 时提前置位。context 仍要等全部有效 stream
   的结果被 FP 路径接受后才能释放，输出反压不能导致提前复用。
5. **排空条件覆盖新增级。** `compute_pipeline_empty` 包含全部 dot metadata
   valid。`correction_drain_empty` 同时检查 pending slots、操作数级和乘积级，
   M1/M2 的短 tail wave 不会把“slot 已空”误认为“校正已结束”。busy 也包含
   校正在途状态，fault 时沿原有排空路径退出，不把旧结果泄漏到下一条命令。

更长流水可能在每个 native block 或 row wave 的边界重复填充和排空，不能
笼统描述为“一条大命令只多两周期”。特别是 Q8_0 的 32 元素块，边界开销占比
可能高于 256 元素的 K-quant 块，必须分别测量。

### 21.4 功能检查和代表回归

本轮独立目录为 `hardware/timing_qbs_pipeline_20260913_SBCC1Q/`。
`before/` 保存本轮修改前的真实文件，未覆盖既有仿真或综合结果。

| 检查 | 结果 | 核查内容 |
| --- | --- | --- |
| 独立 dot 数学模型与三级流水模型 | PASS，16008 个检查周期、13700 批有效输入 | M1-M4、行数、随机值、INT8 极值、连续请求、气泡和复位 |
| datapath 新旧结果序列比较 | PASS，143970 次 arithmetic、164064 次 dot 检查 | dot 按输出顺序比较；其他算术仍按原周期比较 |
| C golden profile 矩阵 | 448/448 PASS | group 整数和最终浮点结果 |
| 加结果反压的 profile 矩阵 | 448/448 PASS | 只在握手时检查数据，随机及连续停顿 |
| 完整 QBS engine | 33/33 PASS，另有四类 fault PASS | 九种 profile、形状/布局边界、activation context、描述符及访存异常 |
| compute engine 新增在途异常 | 四处均 PASS | dot 解码级、乘积级、校正操作数级、校正乘积级；排空分别 65/64/60/59 周期 |
| 完整 SoC VCS 代表回归 | 5/5 PASS | QBS/AKV handoff、`vfredusum`、`vfdiv`、`vfmacc`、AXPY |

所有测试均使用第一版流水化 RTL 通过，没有调整软件、放宽超时或修改数值容差
来规避失败。新旧延迟不同，因此不能继续使用同周期整数引擎 miter 宣称等价；
`qbs-cycle-check` 仅保留给不改变延迟的改写，当前默认 `qbs-check` 使用独立
数学模型、C golden 和握手检查。以上是仿真覆盖，不是形式等价证明。

### 21.5 真实模型输入的周期代价

六个 Qwen2.5 捕获输入切片使用同一测试程序和同样的流量条件。基线为上一轮
`hardware/timing_feedback_20260913_x9goNT/real/summary.csv`。

| profile | M | N | K | 原周期 | 新周期 | 增加 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q4_K | 4 | 32 | 1536 | 7200 | 7298 | 1.36% |
| Q4_K | 8 | 16 | 1536 | 7638 | 7736 | 1.28% |
| Q4_K | 7 | 16 | 1536 | 7612 | 7710 | 1.29% |
| Q6_K | 4 | 32 | 8960 | 41939 | 42501 | 1.34% |
| Q6_K | 8 | 16 | 8960 | 44493 | 45055 | 1.26% |
| Q6_K | 7 | 16 | 8960 | 44479 | 45041 | 1.26% |

六点全部 PASS；weight、activation、payload 字节数、range 数、dot 活动周期
均与基线相同，prefetch wait 均为 0。Q4_K 各增加 98 周期，Q6_K 各增加
562 周期。这些是 engine 测试的周期，不是完整模型的 token/s，也不是实测主频。

33 个功能命令中，已测最大相对代价是 Q8_0、M1/N1/Kb65：1389 增至 1521，
即增加 132 周期、9.50%。因此只能说六个真实切片的代价约为 1.3%，不能说
全部形状都只有这一开销。同一工作负载只有在频率提升比例大于周期增加比例时，
执行时间才改善；当前尚未取得新整机频率证据。

### 21.6 归档及综合边界

```sh
python3 verification/timing/collect_qbs_pipeline_results.py \
  --run hardware/timing_qbs_pipeline_20260913_SBCC1Q \
  --baseline hardware/timing_feedback_20260913_x9goNT \
  --output verification/timing/results/20260913_qbs_pipeline
```

归档包含 `summary.json`、`commands.csv`、`real.csv`，保留修改前后源码哈希、
功能日志路径、33 个命令和六个真实切片的周期对照。可用如下命令单独复现 dot：

```sh
make -C verification/timing qbs-pipeline-check \
  BUILD="$PWD/hardware/timing_qbs_pipeline_recheck"
```

`dc_before/` 和 `dc_after/` 已在 EDA 容器内后台启动，使用同一约束下的完整
integer profile pipeline wrapper，涵盖 decoder、dot、校正选择、乘法及
subtotal。wrapper 的输入寄存器不是实际 SRAM 宏，不能代替 SRAM clock-to-Q、
bank mux、整机负载与布线。记录时尚无两组最终时序或面积数值。

上一轮 `timing_feedback_20260913_x9goNT/soc_dc/` 仍使用流水化之前的冻结源码，
没有被本轮覆盖、停止或偷偷换成新设计。它的后续结果不能归功于本轮流水化。
本轮未新开整机 DC，也不以局部结果提前宣布 1 GHz 达标。
