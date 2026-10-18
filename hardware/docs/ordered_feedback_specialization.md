# 有序浮点规约短反馈路径的面积精简

## 目标与验证状态

目标是在保留有序浮点规约计算顺序、舍入和反馈延迟的前提下，裁剪短反馈单元中没有实际用途的运算能力。此次修改不改变主 FPU、RCE、SLDU 的有序 token 协议、指令生命周期或相关性管理。

RTL 已实现固定 ADD、关闭 SIMD 和移动流水寄存器三个独立开关，当前均默认关闭，原实现仍可用于消融。四组局部综合、四路差分仿真及两个单元素候选的整机功能回归均已完成。输出寄存器候选的局部面积减少 66.626%，所测整机周期不变；整机综合正在运行，尚不能保证集成后 Fmax 不降低，最终默认配置未确定。

## 短反馈通路与面积精简原理

`hardware/src/lane/vmfpu.sv` 中的 `i_fpnew_ordered_fast` 是各 Lane 内额外实例化的 FPnew 单元。原实现只启用 ADDMUL 运算组，关闭除法、开方、转换等其他运算组，使用一个 BEFORE 流水寄存器。请求选择条件是四 Lane、`OSUM_REDUCTION` 状态和 `VFREDOSUM/VFWREDOSUM` 指令。该单元每步完成浮点加法与舍入，下一步仍使用前一步的结果，不会把有序求和改成树形求和。

原实现启用 SIMD，并将动态操作码接到 ADDMUL 组。有效请求只执行加法，但这个运行时事实不一定足以让综合工具裁剪通用运算逻辑。另一方面，`processed_osum_operand()` 已将当前源元素放到数据包低位，有序结果写回也只使能一个元素，因此没有必要为每一步有序加法保留多个并行 SIMD 子通道。

| 配置 | 额外构建变量 | 运算接口 | SIMD | 一级寄存器位置 |
| --- | --- | --- | --- | --- |
| 原短反馈 | 无 | 动态操作码 | 开启 | 输入 |
| 固定加法 | `reduction_ordered_add_only=1` | ADD、op_mod=0 | 开启 | 输入 |
| 单元素加法 | `reduction_ordered_scalar_add=1` | ADD、op_mod=0 | 关闭 | 输入 |
| 单元素加法、输出寄存器 | `reduction_ordered_scalar_add=1 reduction_ordered_output_reg=1` | ADD、op_mod=0 | 关闭 | 输出 |

四组都需要 `reduction_ordered_fast=1`；该功能要求四 Lane 和 `reduction_output_bypass=1`。单元素配置优先于固定加法配置，无需同时启用两个开关。输出寄存器配置要求启用单元素配置。关闭三个精简开关即可恢复原短反馈实现。

FPnew 的 BEFORE 操作码寄存器复位为 FMADD，即使其输入固定为 ADD，仍可能保留操作码选择及部分通用运算逻辑。把唯一一级寄存器放到结果侧，可以让组合运算入口直接看到常量 ADD，同时减少需要寄存的输入数据。移动寄存器仍保留一级协议延迟，但改变了 VMFPU 内的组合路径边界，因此周期等价不等于实际执行时间等价，必须检查集成时序。

## 接口与正确性约束

单元素配置保留原有浮点格式支持、舍入模式、结果标签、异常标志及 valid/ready 握手。主 FPU 结果仍优先使用共享出口，短反馈结果遇到背压时等待。短反馈不会在收到请求的同一周期返回结果，保留 SLDU token 协议要求的寄存器边界。

RVV 输入不采用标量 NaN boxing 约定。原向量模式绕过 boxing 检查，因此关闭 SIMD 时同时设置 `EnableNanBox=0`，避免将合法窄格式数据错误解释成 NaN。单元素结果高位不要求与原 SIMD 结果一致；架构可见结果元素、异常标志、标签及有效握手时序必须一致。

运行时断言检查有效请求确实是 ADD、op_mod=0，且 `issue_be` 不使能当前 SEW 的第一个元素以外的字节。`vfpu_simd_mask` 按最窄格式编码，较宽元素对应多个重复位，不能用“掩码只允许 bit 0”代替这个字节使能约束。

## 功能与周期验证

局部测试 `hardware/tb/ordered_add_equivalence_tb.sv` 同时比较四种实现。覆盖 FP16/FP32/FP64、五种舍入模式、零、无穷、安静与信号 NaN、非正规数、规格化边界、随机位模式、输入空泡和输出背压；检查有效请求握手、输出有效周期、结果元素、异常标志及标签。`hardware/build/ordered_area_v5/run.log` 记录 14,183 个请求全部通过，冻结源码哈希见同目录 `evidence.json`。这是与原实现的差分验证，不是独立的 IEEE 浮点形式证明。

整机对照采用同一组 ELF、相同外围和测量区间。输入寄存器候选的带断言回归见 `hardware/build/ordered_soc_v3`；输出寄存器候选见 `hardware/build/ordered_soc_v4`。两者各 14 项用例通过，覆盖有序规约、宽化、FP16、多种舍入、Mask、别名、空向量以及混合规约/普通浮点运算。七个有周期输出的窗口均与原版一致：549、124、123、137、292、28、974；其余用例验证功能并比较仿真结束时间，没有将其称为独立性能测量。14 项用例的仿真结束时间均未退化。

`ordered_soc_v4` 已实际运行两套构建和回归，文件列表只差单元素与输出寄存器两个宏，共用同一份冻结 RTL。比较结果、ELF 哈希与源码核查分别见 `comparison.json` 和 `provenance_audit.json`。具体用例名称及每项周期见比较文件。

## 四组局部面积和时序结果

综合采用相同工艺库、约束和依赖源码。测试顶层使用 8-bit 标签，实际 VMFPU 标签为 9-bit，因此这里的绝对面积不能直接当作集成后每 Lane 面积。正式结果汇总于 `hardware/build/ordered_ppa_v4/four_way_results.json`；原版与输出寄存器版的库、依赖哈希及归一化脚本核对见 `original_vs_after.json`。

| 配置 | 单元面积 | 相对原版减少 | 时序单元数 | ADD 模式最差 setup slack（ns） |
| --- | ---: | ---: | ---: | ---: |
| 原版 SIMD、输入寄存器 | 48,537.719709 | 0% | 702 | −0.467986 |
| 固定 ADD、SIMD、输入寄存器 | 46,785.311698 | 3.610% | 667 | −0.442393 |
| 单元素 ADD、输入寄存器 | 33,618.647808 | 30.737% | 389 | −0.439445 |
| 单元素 ADD、输出寄存器 | 16,198.895960 | 66.626% | 156 | −0.298359 |

有效综合目录依次为 `ordered_ppa_v2/0`、`ordered_ppa_v2/1`、`ordered_ppa_v4/2`、`ordered_ppa_v4/3`，均位于 `hardware/build`。四组均有无 Error 的完成日志、QoR、面积、时序报告和 `mapped.ddc`。时序检查未报告组合环或未约束端点；输出寄存器版提示 reset 无输入延迟，两组约束均已将 reset 设为 false path。

所有配置都存在 setup 和 hold 违例，不能声称达到 1 GHz 或完成时序收敛。输出寄存器版的最差 setup slack 改善，但完整 QoR 中 setup 违例路径数/TNS 从原版的 67/−30.77 ns 变为 121/−34.18 ns，并非所有时序指标都改善。输入寄存器单元素版为 67/−28.94 ns，389 条 hold 违例、最差 hold slack 约 −0.12 ns。原版有一项 transition 违例，其余三组没有 transition/capacitance 违例。

ADD 模式分析由 `hardware/scripts/ordered_add_mode_timing.tcl` 在映射网表上执行，仅生成报告，不修改或重新综合网表。脚本约束实际加法操作码，直接处理带保持反馈的输入操作码寄存器输出，并检查 Q/QN 极性。四组分别确认 42、7、3、0 个操作码寄存器；格式、mask、舍入、握手和数据保持动态。报告仍包括原 SIMD 子通道的输出路径，不能解释为每种格式的独立指令延迟。有效模式报告位于原版的 `add_mode_v2` 和其他三组的 `add_mode_v1`，各有 `evidence.json`。

## 整机综合与尚待完成的验证

为验证组合路径边界变化，已于 2026-10-13 04:03 UTC 启动 `full_scalar_after` 整机综合，目录为 `hardware/build/synthesis/full_scalar_after_prepare_v1`。启动前静态检查通过（389 个 HDL、11 个库）。`baseline_input_audit.json` 核实对照 `full_retry2` 有 434 个文件一致，源码差异只有本次 `vmfpu.sv` 修改；工艺库、时钟周期、时钟不确定度、核数和工具配置一致。该记录只证明输入可比，不代表综合完成。

整机候选尚在运行，原整机 `full_retry2` 的进程和报告也保留。局部面积降幅不能直接乘到 Ara 或 SoC 总面积上，局部 slack 不能证明整机 Fmax。最终选择需要核对集成后的面积和时序；当前不以局部结果提前修改默认配置。此流程未进行布局布线或带真实活动率的功耗验证。

## 复现入口

整机回归入口从指定 full-profile 构建读取文件列表和编译命令，冻结当前 VMFPU/dispatcher，其余源码来自参考构建；需保留参考依赖和已编译应用。输出目录必须不存在。以下命令实际编译并仿真输出寄存器候选；去掉 `--output-register` 比较输入寄存器候选，增加 `--prepare-only` 则只准备、不运行工具。

```sh
python3 hardware/scripts/run_ordered_add_soc.py \
  --reference hardware/build/rce/paper_iscas_v2/full \
  --out hardware/build/ordered_soc_recheck --output-register
python3 hardware/scripts/compare_ordered_add_runs.py hardware/build/ordered_soc_recheck
```

局部综合入口读取 `full_retry2` 的冻结依赖与工艺库，保存新顶层快照、文件哈希和每组报告。以下命令会实际启动 DC；模式 0/1/2/3 对应上表四行。

```sh
python3 hardware/scripts/run_ordered_add_ppa.py \
  --out hardware/build/ordered_ppa_recheck --modes 0 1 2 3
```

整机综合配置 `full_scalar` 和 `full_scalar_after` 分别对应两个单元素候选；原有四个论文 profile 不变。准备、检查、运行与报告入口见 `hardware/docs/reduction_synthesis_setup.md`。

## 保留的失败与修复证据

`ordered_soc_v2` 保留错误掩码断言触发记录：正常 FP32 请求的最窄格式 mask 有重复位，随后改为字节使能检查，没有关闭断言。`ordered_ppa_v2/2` 和 `ordered_ppa_v3/3` 保留测试顶层 mask 端口位宽不匹配的链接失败；实际 VMFPU 原本已连接 bit 0，修复局部测试顶层后使用新目录完成综合。`ordered_ppa_v2/0/add_mode_v1` 保留仅约束输入操作码但未穿过保持反馈的无效模式分析，不用作结果证据。旧失败目录均不覆盖、不计入通过结果。

## 后续面积精简

共享累加更新、共享归一化和共享最终尾数提取的实现、独立开关、测试及面积结果见 [规约面积精简记录](reduction_area_specialization.md)。这些候选建立在短反馈优化之上，分别验证收益，不能把局部面积降幅相加当作整机降幅。
