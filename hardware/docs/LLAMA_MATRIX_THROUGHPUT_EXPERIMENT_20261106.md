# 格式限定的矩阵吞吐扩展：组件级结果

## 1. 为什么选择这一项

已归档的真实 QKV 投影中，dot issue 占 QBS busy 约 87.89%，而输入反压及结果等待计数为零。新端口测量进一步区分了整数修正、FP arithmetic、I2F cast 和 half-scale，排除了仅由 FP 总 uop 数推断单端口拥塞的做法。两项证据支持研究矩阵计算吞吐扩展；它们尚不足以确定完整模型收益。

本候选接受适量新增算术资源，不以全部复用现有 lane 乘法器为前提。目标是减少 Prefill 多输入行计算的实际周期，同时避免更宽格式通路、全局仲裁和 FP 重结合带来的复杂性。本阶段没有综合，也不声称面积已经满足某个百分比。

## 2. 硬件变化

| 模块 | 修改 | 不变项 |
| --- | --- | --- |
| `qbs_profile_decoder.sv` | 新增默认关闭的 `WideMatrixDot`；256 元素块且局部 M=3/4 时，每上下文每周期解码 4 个元素，而非 2 个 | M1/M2 和 32 元素块的步长；所有原生格式与 scale 解码 |
| `qbs_dot_array.sv` | 启用时每输出行最多 16 个 INT8 乘积槽，四行共 64 个；宽矩阵路径按每上下文四乘积归约 | 三阶段数据/metadata 对齐；普通窄模式的两乘积、四乘积、八乘积归约；接口结果位宽 |
| `qbs_profile_engine_int.sv` | 四条按物理输出行固定归属的修正通路，每条在两个 tile context 的本行条目间仲裁 | 每输出子组与块的运算顺序、结果持有、context 生命周期、尾 wave 安全排空 |
| `qbs_compute_engine.sv` | 参数向整数引擎传递，默认关闭 | FP 累积器、激活/权重双缓冲及命令调度 |

每条修正通路只服务一个输出行，避免先从全局 32 个条目依次选出四个，再将四个任意条目连接到四个 subtotal 写口。每行只需在 8 个候选之间进行局部 round-robin。现有两通路选择器保留在默认分支中。

新增的乘积与修正均为整数精确运算。每个输出仍先完成相同子组修正，再按原块顺序转换、缩放及 FP 累积；没有修改舍入、融合乘加、FP 初始值或 ISA。四个乘积的单周期和仍在现有 19 位结果范围内，完整子组继续由 21 位部分和保存，原溢出断言保留。

宽路径读取的四个连续字节位于原 128-bit 权重窗口及 256-bit 激活窗口内，不增加本次 buffer 读端口。它不能因此被称为外部供给能力翻倍；AXI、完整命令及 CPU 准备成本仍需下一阶段测量。

`pair_capacity` 统计参与输出行上的配置乘积槽容量。因此启用 64 槽设计但走原 M1/M2 或短块路径时，空闲槽也计入容量，不能仍将其利用率写成 100%。有效 pairs、FP uop、输出数及工作量保持不变。

## 3. 验证方法与结果

两套独立 VCS 镜像来自同一份 RTL 和 bench，仅顶层 `Wide` 参数分别为 0/1。每侧运行：

- 36 项原有格式/形状用例，覆盖九种 profile、M1--M8 的代表点、N 尾部、跨块，以及 256-block 长 K。
- 真实 Qwen2.5 Prefill Q 投影的 M1/N8/K1536 和 M4/N8/K1536 两项切片，权重与激活来自同一已归档捕获。
- 每次执行保留原有输出、fflags、资源计数和故障排空检查，包括等待输入时取消及四个流水位置注入故障。

候选向量文件只修改硬件结构必然改变的 dot-cycle 和容量期望；所有 payload、期望输出、fflags 及其余计数逐字保持一致。独立检查器重新计算几何与计数，拒绝任何其他输入变化。38 项每侧全部通过，未观察到测试区间周期增加。相关工具共 30 项单元测试通过。

下表是 **compute bench busy 区间**，含测试任务控制的数据递送，不是完整 SDK 调用或模型推理：

| 输入 | 原配置 cycles | 候选 cycles | 区间时间比 |
| --- | ---: | ---: | ---: |
| 真实 Q4_K，M4/N8/K1536 | 3464 | 2696 | 1.28487x |
| 真实 Q4_K，M1/N8/K1536 | 1602 | 1602 | 1.00000x |
| Q6_K，M4/N8/3 blocks | 1970 | 1586 | 1.24212x |
| Q3_K，M4/N7/3 blocks | 1584 | 1200 | 1.32000x |
| Q2_K，M4/N7/3 blocks | 1578 | 1194 | 1.32161x |
| Q8_0，M4/N7/4 blocks | 459 | 459 | 1.00000x |

真实 M4 点的 dot issue 为 1536 -> 768，FP arithmetic 仍为 768 次、cast 为 384 次，整数结果到 FP 的等待为零。扩展在该输入下减少了 768 个测试区间周期，并没有证明整模型也减半。M5/M6 的部分用例仍存在结果等待，说明尾 wave 与累积仲裁是后续需要观察的边界，不能将它隐藏为无等待。

原始结果：唯一验证工作树 `verification/out/e2e_matrix_dot_pair_20261106_01/`。独立重新核对输入 pin、镜像及日志后，回执保存在 `verification/performance/evidence/matrix_dot_pair_20261106_01/result.json`。

## 4. 接入与保留门槛

参数仍默认关闭；现已在第 9 节的配对 SoC 测量中显式开启，但尚未成为生产默认，
也未完成全尺寸 GGML 投影或 FPGA 验收。不改变原交付 SDK、指令编码、普通 RVV
路径或封存中的模型任务。

下一步在完整 QBS engine 中测量真实读响应、激活 context FILL/REUSE/RELEASE、结果提交及异常恢复；随后用完整 SDK 调用配对检查准备、命令和输出总成本。若收益主要被供给等待隐藏，应优先改善驻留/供给，而不是继续堆乘法器。只有完整调用证据和代表性回归通过，才讨论运行时集成与生产默认值。

## 5. 完整命令测试与故障场景核查

本节保留首次失败和定位过程；最终命令验收见第 6 节，整机结果见第 9 节，
不要把本节当时的“仍在执行”理解为当前状态。

`qbs_engine.sv` 现已向 compute engine 转发默认关闭的 `WideMatrixDot` 参数。完整命令测试使用实际共享读模块及 VRF 提交路径，原冻结 bench 的输出、fflags、计数、unknown 检查、context 生命周期及故障恢复断言均保留；独立派生 wrapper 仅增加参数传递。

初次运行目录：`verification/out/e2e_matrix_engine_pair_20261106_01/`。安排的四组向量为普通 36 项、真实 M1/M4 切片，以及 12 项容量边界 context 测试，每组采用 response_gap=0/3。前七组配对日志通过，但最后的 context/gap3 在两侧均失败，原运行保持 FAIL。

失败位于 `wide context fault did not interrupt active replay` 检查：Q4_K、M4/N5、4 blocks 的 REUSE 权重 AXI 错误没有观察到所要求的故障/replay 重叠。两侧在该检查前均通过了故障返回、replay 已停止以及原 context 仍有效的检查。不能将它直接判定为新候选引入的功能错误，也不能因两侧同失败就忽略。

静态假设是：共享读模块要排空故障 AXI 事务才报告 `read_fault_valid`；response_gap=3 延长排空，replay 可能先完成，因此刺激未满足“故障打断 active replay”的前提。后继工具 `run_matrix_fault_schedule.py` 保留原失败，首先以相同前两项向量和被动探针记录 replay start/last/idle、AXI error/last、read fault 的周期顺序。只有顺序证据支持假设，才继续检查可选的故障从设备快速排空调度。

后继并不删除重叠断言，也不修改功能 RTL。快速排空只影响人为注入错误的 REUSE/RELEASE 响应，正常调用仍使用原 response_gap；所有输出、fflags、saved-context、VRF 无部分提交及重试检查保持不变。完整门槛在后继测试与独立审计完成前仍未关闭，不使用初次运行的局部通过来声称整个命令测试已通过。

初次探针编译因 include 放在 bench 声明之前而失败，未执行仿真，该记录仍在 `verification/out/e2e_matrix_fault_schedule_20261106_01/`。声明顺序修正后的入口为 `run_matrix_fault_schedule_v2.py`，运行目录 `e2e_matrix_fault_schedule_20261106_02/`；冻结的首个 worker、探针和失败报告未被改写。实验工具的 36 项单元测试通过，这些是工具检查，不替代 RTL 测试或面积/时序证据。

该后继的被动测量已复现原失败，并证实前述时序假设：

| 事件 | 周期 |
| --- | ---: |
| replay start | 89829 |
| 首个 AXI 错误响应握手 | 89834 |
| replay 最后一个数据握手 | 89903 |
| replay 已空闲 | 89904 |
| 故障 AXI burst 的最后一个响应握手 | 89974 |
| 读引擎报告 fault | 89975 |

故障 burst 共 36 beats；相邻握手间隔 4 周期，35 个间隔正好为 140 周期，与 89974-89834 一致。错误响应发生时 replay 尚在运行，但读引擎在排空后才上报，届时 replay 已结束；这里没有观察到数值或取消错误。`rootcause.json` 保存有序事件。开启仅针对注入错误的快速排空后，相同前两项 context 向量已通过原有重叠及完整故障恢复检查，完整 12 项两侧回归仍在执行，最终审计尚待完成。

初次完整命令运行中已经独立检查的真实切片结果如下。这里包含共享读模块、实际响应交互及 VRF 提交，但不含 CPU/SDK 准备；整组验收仍受上述故障场景门槛约束。

| 真实 Q4_K，N8/K1536 | 原配置 cycles | 候选 cycles | 命令区间时间比 |
| --- | ---: | ---: | ---: |
| M4，response_gap=0 | 2054 | 1486 | 1.38223x |
| M4，response_gap=3 | 4434 | 4050 | 1.09481x |
| M1，response_gap=0 | 775 | 775 | 1.00000x |
| M1，response_gap=3 | 2269 | 2269 | 1.00000x |

gap 是测试从设备相邻响应的受控间隔，不是板上 DDR 延迟模型。慢供给下矩阵吞吐增量缩小，支持后续同时检查驻留和供给，不能据快速响应点继续承诺翻倍计算就会带来接近翻倍的完整调用收益。

## 6. 完整命令验收与整机入口

后继完整 context 测试及独立审计已完成，状态为 `MATRIX_FULL_ENGINE_COMPOSITE_REAUDITED`。重新检查 175 项输入身份和全部相关原始日志，每配置共 100 项直接命令检查、26 项 context 生命周期检查通过。该数量包括 50 项向量场景在两种响应调度下运行，不是 100 个独立模型。原失败记录和被动复现保持 FAIL，没有改写。

审计组合明确区分：初次 worker 已通过的七组配对，以及修正故障刺激后的 context/gap3 配对。正常调用的响应间隔、向量输入及数值标准不变；只在人为注入的故障流量中加快排空以覆盖所要求的 active replay 取消。两种调度下都保留恢复后按原输入重新计算的检查。

已检查的直接命令没有周期退化。Q4_K M4/N5、4 blocks 的 context 点在 gap0 时，FILL 为 1591 -> 1085 cycles，REUSE 为 1435 -> 929；gap3 时分别为 2887 -> 2381、1719 -> 1213。32 元素块的 M4 context 点保持原周期。完整 SDK 的准备开销仍未包含，因此不能把这些比值当作完整模型增量。

审计回执：`verification/performance/evidence/matrix_engine_pair_20261106_01/result.json`；重新检查工具为 `collect_matrix_fault_schedule.py`。

整机采用显式开关：

```text
qbs=1 qbs_matrix_dot=0   原点积与修正组织，默认
qbs=1 qbs_matrix_dot=1   启用候选，由格式和局部 M 自动选择宽点积
```

`hardware/Makefile` 检查开关为 0/1，拒绝在 qbs=0 时启用；Bender 将 `ARA_QBS_WIDE_MATRIX_DOT` 传给实际 VLSU 实例。`simulator.conf` 同时记录 `qbs_matrix_dot`，避免只凭目录名判断所用硬件。没有修改生成的 `qbs_pkg.sv` 或 ISA/描述符定义，ABI 生成检查通过。两侧工作树的 38 项工具测试通过，包括开关和非法配置的真实 make 展开。

已验证的五个 QBS 模块及两处配置入口同步到唯一验证工作树，其他主线 RTL 不随此次同步。下一门槛是实际 CVA6+RVV SoC、普通 RVV 回归和相同 ELF 的完整 SDK 调用测量；在这些门槛前，默认值不变，不部署 FPGA，也不启动综合。

## 7. 整机配对构建

主线配置入口提交为 `39f745675`，唯一验证分支七文件同步提交为 `45e28f45c`。`build_matrix_soc.py` 检查五个引擎文件与完整命令验收身份一致，两处 glue 与固定提交一致，其他已编译设计输入与前一套已检查的 SoC 保持原哈希。不会将主线未提交的 testbench、AKV 汇编或依赖差异带入验证构建。

两侧均已完成预检查：`e2e_matrix_soc_preflight_20261106_02/` 为候选，`_03/` 为基线，状态均为 `MATRIX_SOC_PREFLIGHT_NOT_COMPILED`。初次预检查因 PATH 中的 ccache/g++ 与既有基线不一致而失败，保留在 `_01/`，没有启动 VCS。正式 worker 固定 `/usr/bin/g++`、`/usr/bin/python3` 和相同 VCS，清除影响编译的环境覆盖。

预检查使用实际 make 展开和 Bender 生成源清单；只允许在相同位置增加宽点积宏，不放松其他源码、顺序或宏上下文。官方 Makefile 中的 `bender script verilator` 仅生成 VCS 使用的源清单格式，不调用 Verilator 仿真器。ABI 生成检查及 41 项工具测试通过。

正式构建入口如下，必须使用新目录：

```sh
python3 -B verification/performance/end_to_end_baseline/build_matrix_soc.py \
  --wide 0 --execute \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/matrix_soc_base_next
python3 -B verification/performance/end_to_end_baseline/build_matrix_soc.py \
  --wide 1 --execute \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/matrix_soc_wide_next
```

两套构建的输出和 VCS 增量目录独立，可以并行。每个 worker 直接由 systemd 管理，完整编译上限 7200 秒；只构建、不自动执行程序。构建结束后仍需核对实际 VCS 命令、原有严格 lint 检查、生成配置、源清单和镜像哈希。通过构建不等于通过普通 RVV 或 SDK 性能验收。

## 8. 整机镜像复核及真实 Qwen3 输入

两套 VCS 均已完成编译和链接。原构建 worker 在后置清单检查处保持 FAIL：
Make 在 Bender 输出末尾追加了一行空白，而 worker 使用逐行完全相等比较。
`collect_matrix_soc.py` 不修改原记录，仅允许 `actual == planned + '\n'` 这一确切差异；
同时重新检查源文件顺序、全部宏、七文件批准范围、编译命令、完整头文件清单、
既有严格 lint 规则及镜像组成。没有追加源码/宏豁免，也没有重新编译。

独立回执状态为 `MATRIX_SOC_PAIR_REAUDITED_NOT_EXECUTED`，保存在
`verification/performance/evidence/matrix_soc_20261106_01/result.json`。两套均为实际
CVA6、4 lanes、VLEN1024、16 MiB 仿真 L2，配置只在 `qbs_matrix_dot=0/1` 有别。
此回执只接受编译产物，不接受程序执行、普通 RVV 回归或性能。

### 8.1 抓取方式与数据身份

`capture_projection.cpp` 复用已完成模型配对验证的 llama/GGML 静态库，加载
Qwen3-1.7B Q4_K_M，执行固定自然语言 prompt 的真实图。GGML callback 在第一层
`attn_norm-0` 完成并同步后，读取前四个 token 的完整 FP32 向量。这个张量正是
`build_qkv` 的共同输入，不是 RoPE 后的 Q/K，也不是以随机数替代的激活。
抓取完成即主动退出，不执行后续 28 层，不把这次退出称为完整模型生成通过。

输入为 40 个真实 prompt token 中的前四行；四行数据逐字节不同，所有元素有限。
每行 K=2048，未缩短 K。宿主机 GGUF 与 QEMU 只读 ext4 中的模型文件通过
`debugfs` 只读流式 SHA256 核对相同，再由归档的官方 GGUFReader 提取原生权重，
没有把运行时 repack 后的内存误认为原始 GGUF 数据。

| 第一层权重 | 原始 K×N | 原生格式 | 测量用 K×N |
| --- | ---: | --- | ---: |
| Q | 2048×2048 | Q4_K | 2048×128 |
| K | 2048×1024 | Q4_K | 2048×128 |
| V | 2048×1024 | Q6_K | 2048×128 |

原始抓取在唯一验证树的 `verification/out/e2e_qwen3_projection_capture_20261106_03/`，
激活 SHA256 为 `98ed03f837793c9b55dbd67b088e3fdce0a3f34dcada3a3c22e3c918d9386f83`。
`run_projection_capture.py` 的首个尝试在新增工具链头文件登记前停止；v2 在
gen_init_cpio 软链接的身份查询处停止。两者均未进入 QEMU。v3 明确登记新编译
依赖并使用解析后的工具路径，保留两次原失败；它是当前可复现的抓取入口。

### 8.2 同一份 SDK 工作量

`projection_golden.c` 使用既有独立 QBS C reference 量化、打包及计算，逐 tile
比较 ROW_MAJOR 与 R4 布局的全部输出位。三个投影均通过；每个投影的计算
FFLAGS 为 NX。该 host 程序不链接到性能 ELF。

`projection_native.cpp` 直接使用已验收运行时中的并行 group-sum 量化 helper，
以及 SDK planner/native executor；不是新写一个有利于候选的量化循环。四行
激活准备一次，供 Q/K/V 三个调用消费；两套硬件使用同一 ELF、同一准备方式，
不把已有的软件复用收益算作新增硬件收益。

每个试次含三次 M4/N128/K2048 投影、12 条 native 命令、1536 个输出，两试次
共 24 条命令、3072 个输出、6,291,456 个有效乘积。计时分别记录激活准备、
SDK admission、执行及总区域；校验、checksum 和串口打印均在计时区间外。
输出逐位对照独立 reference，检查最终 FCSR/VCSR、量化 payload、命令数及
前后 guard。只读 RTL monitor 还核对实际命令形状、有效乘积和 dot issue 数。

该测试是**真实数据的 QKV SDK 调用组**，不是全尺寸 QKV、完整 GGML dispatch
或整个模型。权重已在运行前重排，冷启动权重准备不计入；N 前缀只是限制 VCS
运行时间。M4/K2048 的 9344 B 激活超过当前 4672 B context 容量，走正常 DIRECT
路径，不为候选人为开启原硬件无法容纳的常驻配置。这也为后续供给优化留下
真实瓶颈证据，不能把该点用作“整个激活已经常驻”的例子。

## 9. 真实 Qwen3 SDK 配对实测与归因

两套独立 VCS 均已通过，实际执行同一 ELF，并完成独立 UVM 协议/AXI/向量轨迹
检查。`collect_projection_native.py` 又重新检查输入、镜像、原始日志和全部
输出 checksum，重放 worker 的数值/CSR 判定；不是只读取末尾 PASS。
配对回执状态为 `REAL_QWEN3_SDK_RTL_PAIR_REAUDITED`。

下表均为两次相同 QKV 调用组的周期合计，M4、每个投影 N128、K2048。两侧
准备方式完全一致，原始权重重排在运行前完成；不含完整 GGML 图派发和模型运行。

| 区域 | 原硬件 cycles | 宽点积 cycles | 时间比 |
| --- | ---: | ---: | ---: |
| 激活准备 | 115664 | 115664 | 1.00000x |
| Q 的 SDK 执行 | 79223 | 48711 | 1.62639x |
| K 的 SDK 执行 | 77657 | 47169 | 1.64636x |
| V 的 SDK 执行 | 78185 | 48625 | 1.60792x |
| 三个 SDK 执行合计 | 235065 | 144505 | 1.62669x |
| 含准备、admission 及调用控制的总区域 | 361555 | 270995 | 1.33418x |

24 条命令、3072 个输出全部逐位正确，量化 payload 与独立参考相同，最终
FCSR=9、VCSR=5；前后 guard 完整，两侧最终输出 checksum 相同。
该程序第二次准备发生在前一组 QBS/VRF 提交之后，也通过了相同 RVV 量化检查；
这提供真实软硬件交替执行证据，但不替代普通 RVV 全指令回归。

### 9.1 为什么收益不是简单的 2x

`diagnose_projection_pair.py` 重放上面的完整配对，并检查下列守恒关系：

| 指标，两次试次合计 | 原硬件 | 宽点积 |
| --- | ---: | ---: |
| 有效整数乘积 | 6291456 | 6291456 |
| dot issue | 196608 | 98304 |
| QBS busy cycles | 221006 | 130446 |
| FP uop，三条端口总发射数 | 122880 | 122880 |
| FP accumulator updates | 24576 | 24576 |
| QBS reader AR | 2056 | 2056 |
| QBS reader R beats | 78040 | 78040 |
| QBS reader payload bytes | 1244544 | 1244544 |
| 严格 QBS_WAIT_WEIGHT 周期 | 0 | 7744 |

没有少做乘积、FP 累积或访存。dot issue 恰好减半，省下 98304 个 issue 周期；
新暴露的权重等待为 7744 周期，因此 busy 实际减少 `98304-7744=90560`，
与 SDK 执行及总区域实测减少的周期完全相同。两个方向的 FP input blocked 和
profile result blocked 均为零，不能由 FP uop 总数反推一个单端口已饱和。

该等待计数器在 `qbs_compute_engine.sv` 中仅对 `state_q==QBS_WAIT_WEIGHT` 增一。
`qbs_engine.sv` 将同一严格状态再分为四个互斥桶：无在途 burst、在途但无 R、
R 握手、R 被阻塞。本点分别为 336、0、7408、0，合计 7744。它表示等待期间
共享 reader 大多正在传送数据，**不是**“DDR 响应迟了 7408 周期”；这些 R beat
也不能直接称为全部属于权重。要继续优化，仍需区分 activation/weight 的请求
归属和双缓冲可覆盖的时间，而不是仅根据桶名字修改访存优先级。

即使把新增的 7744 周期全部消掉，这个候选总区域也只能再获得约 1.02942x。
所以不把下一阶段局限为清理这项小等待，更不立即再增加一倍乘法器。

### 9.2 为什么还不能按 42.68% 选择下一项硬件

准备占该候选区域 42.68%，但这里裁掉了 N，没有裁 K。完整 Q/K/V 的 N 分别
为 2048/1024/1024，准备的同一激活可被更多输出通道消费，因此不能把 42.68%
当作完整模型或全尺寸投影的准备占比。当前几何下的 1.33418x 也不是模型加速比。

下一门槛是保留真实全 N 的 QKV SDK 调用组，以及实际 GGML 的准备复用记录。
全尺寸 VCS 优先采用一轮确定性配对、保留全部输出检查，每侧仍最多 3 小时；
超时不放宽数值标准，也不把部分命令冒充完整投影通过。

还发现需要明确统计的软件限制：归档运行时 `q8_K-prepared-reuse.h` 只允许
`group<8` 且 `K<=6144` 的完整 M4 组走准备缓存；第 9 组起是正常的重新准备，
不是 LRU 循环污染，也不是算错。40 个 prompt token 对应 10 个完整 M4 组，
仅前 8 组可能复用。实际命中仍受图策略、epoch、数据内容和 producer 选择影响。
应先统计这种按 batch/形状变化的覆盖限制，再决定扩大准备缓存、调整图调度，
或合并块统计扫描；不能把已有复用再次作为新增收益。

### 9.3 实验与版本

原始目录均在唯一验证树 `verification/out/`：

- `e2e_qwen3_matrix_base_20261106_01/`、`e2e_qwen3_matrix_wide_20261106_01/`：两侧运行。
- `e2e_qwen3_matrix_pair_20261106_01/`：独立配对复核。
- `e2e_qwen3_matrix_diagnosis_20261106_01/`：原始守恒及严格等待桶的复核。

`watch_projection_pair.py` 通过 inotify 等待两侧 result 文件事件后执行汇总，
不采用固定间隔轮询，不修改原 worker 结果。

硬件开关、ISA、SRAM 容量和端口保持第 2 节的定义：新增 32 个 INT8 乘积槽及
修正并行能力，没有新增外部读端口或本次数据 buffer 容量。尚无映射面积和时序
结果，不能把资源数量直接换算成已经证实的面积比例，也不部署到 FPGA。

## 10. 全输出维度与实际准备复用的后续门槛

全输出程序已生成并通过前置核验，状态为
`FULL_QWEN3_SDK_BUILT_NOT_EXECUTED`。同一真实捕获保留 M4/K2048，Q/K/V
分别使用完整 N2048/N1024/N1024，一轮共 128 条命令、33554432 个有效乘积和
16384 个输出。独立 C 参考逐位比较 row-major/R4 两种权重布局，完整输出的
N128 前缀也必须与上一批参考相同。程序仅重建 caller/data 两个 object，复用
九个已核验公共 object；两侧 16 MiB SoC 均核对 ELF 的 L2 地址范围。

独立运行和收集目录在验证树中：

- `e2e_full_qwen3_qkv_build_20261106_02/`：冻结后的准备成功记录。
- `e2e_full_qwen3_qkv_base_20261106_01/`：原点积宽度 VCS。
- `e2e_full_qwen3_qkv_wide_20261106_01/`：宽点积 VCS。
- `e2e_full_qwen3_qkv_pair_20261106_01/`：仅在两侧完成后创建的独立汇总。

记录时两侧 VCS 已实际执行，尚无本批性能结论。即使全输出通过，也只证明
四个真实 token 的完整 QKV SDK 调用组，不能称为完整 Prefill、Decode 或模型
增量加速。单轮消除了重复试次开销，但也不提供多轮统计分布。

失败证据原样保留：第一份 build 因 helper 在运行期间发生变化被身份门控
拒绝，未启动 VCS；第一份 watcher 因先于目录创建而退出。后者仅修复等待
逻辑，未重启仿真。新 watcher 先监视父目录，再监视已创建的运行目录，并在
安装监视之后检查完成文件，兼容先启动或先完成的 worker；真实 inotify 单测
覆盖目录创建与原子 result 文件改名。

实际准备复用另由 `run_preparation_census.py` 执行。它复用当前已核验的完整
Qwen3 模型库，仅打开原有日志；检查每个 cache/direct 事件与 prepared-buffer
的组数、K、epoch、producer 及阶段对应，再比较两种 Attention 选择下的计数。
尤其区分以下三件事：前八组真实缓存命中、第九组起直接准备、完整 packed
buffer 重复。最后一项不自动证明原始 FP32 输入逐字节相同，不能直接作为新
缓存命中或已节省周期。新增硬件方案仍需结合全 N 的准备摊销和完整执行占比
作出选择，而非仅凭缓存上限就扩大资源。
