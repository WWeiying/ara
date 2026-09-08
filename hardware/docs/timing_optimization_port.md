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
