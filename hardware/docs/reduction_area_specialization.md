# 规约面积精简：保持计算吞吐的资源共享

本轮目标是减少规约微架构的硬件开销，同时保持性能基本不变。功能、精确状态位宽、seed 版本及真实依赖检查不放宽；优先选择不增加周期的结构共享。后续若有改变周期的方案，暂按整体约 2%、关键场景不超过约 5% 的退化筛选，并分别报告各个场景。周期、集成时序和面积必须独立测量，不能把周期不变当成执行时间已经不变。

本轮对照源码为 `13dfca21955dfd4e05905e92e4afaff7b7b579b6`，是已有规约机制的优化版本，不是官方 Ara。此前历史 `ara_main` 面积报告没有完成历史源码快照与当前配置的严格匹配，因此不用它计算本轮可归因的面积收益。原有序短反馈精简另见 [有序短反馈专用化](ordered_feedback_specialization.md)。

可随源码保存的指标及哈希摘要见 [验证证据](reduction_area_specialization_evidence.json)。完整工具日志保存在各实验目录，摘要中的运行中项目不计为通过。

逐模块的历史面积差额、源码对应关系及允许改变架构后的精简方向，见 [面积增量与架构审查](reduction_area_architecture_audit.md)。其中候选尚未实现，历史差额不等于严格匹配基线的功能成本。

## 实现与开关

| 修改 | RTL | Makefile 开关 | 保持的行为 |
| --- | --- | --- | --- |
| 首拍、后续拍共用更新通路 | `fp32_exact_reduction_accum.sv`，`SharedBeatUpdate` | `reduction_shared_exact_update=1` | 每拍接收能力、逐元素特殊值合并顺序、首拍 seed 插入规则 |
| 两个归一化阶段共用两套 chunk 运算 | 同模块，`SharedNormalize` | `reduction_shared_exact_normalize=1` | 原两周期归一化、带符号进位、精确状态输出时间 |
| FP16/FP32 共用尾数提取 | `fp32_exact_reduction_finalize.sv`，`SharedExtract` | `reduction_shared_finalize_extract=1` | 舍入模式、guard/sticky、异常标志和组合接口 |

三个开关分别对应 `ARA_RED_SHARED_EXACT_UPDATE`、`ARA_RED_SHARED_EXACT_NORMALIZE`、`ARA_RED_SHARED_FINALIZE_EXTRACT`。通用 Makefile 的默认值均为关闭，可单独消融；`full_compact` 综合配置显式启用共享归一化。宏按是否定义生效，关闭时必须不定义，不能传 `=0`。

共享更新把首拍与后续拍的相同逐元素操作放到一个组合数据通路中。首拍先初始化上下文并按原语义插入非延迟 seed，再进入公共更新；后续拍从寄存状态继续累加。首拍使用新格式和 bank 0，后续拍使用锁存格式和当前 bank；start 后的外部元数据变化不影响正在执行的上下文。没有改变元素的合并顺序，也没有把精确累加替换成普通浮点加法。

共享归一化在运算器之前选择低八段或高八段，每拍仍处理原来的两个 chunk。高段阶段的初始进位从前一阶段保存的有符号进位取得，必须先进行符号扩展。最终精确结果仍使用原有段寄存器保存，没有增加根结果寄存器或额外流水周期。输入选择器可能影响路径，因此需看综合结果，不能根据运算函数调用次数直接声称面积降低。

共享提取根据 FP16/FP32 选择移位量，生成同一份 24-bit 窗口和 guard/sticky；FP16 使用其中所需的 11-bit 尾数。非正规数和特殊值仍遵循各自既有路径。种子绑定、特殊值处理以及异常标志逻辑保持原语义。本次没有缩短分段状态位宽，也没有缩减结果队列或删除版本检查。

## 验证证据

| 范围 | 结果 | 证据目录（相对 `hardware/build`） |
| --- | --- | --- |
| 最终舍入差分：修改前、当前关闭、当前开启 | Icarus 和 VCS 均通过 56,736 组 | `finalize_area_v1` |
| 累加器差分：原版与更新/归一化四种组合 | 12 种合法参数配置、300 条序列、14,168 周期通过 | `exact_update_v4` |
| 独立整数参考模型：三个开关同时开启 | 900 项 FP32/FP16/宽化、普通/延迟 seed 通过 | `exact_area_oracle_v2` |
| 匹配整机对照：三个开关同时开启 | 两组各 22/22 通过，15 个周期窗口及全部结束时间一致 | `exact_area_soc_v3` |
| 最终选择：只开启共享归一化，保留此前短反馈配置 | 22/22 通过，15 个周期窗口及全部结束时间一致 | `exact_area_soc_normalize_v1` |

最终舍入测试包含每个最高有效位位置、两种格式、正负值、舍入进位、sticky、随机内部状态以及 seed/NaN/Inf/零组合。累加器测试逐周期比较输入 ready、输出 valid、busy、精确状态、结果、异常标志和元数据，包含同拍 start/data、独立 start、输入空泡、输出背压以及 start 后外部元数据变化。差分测试证明所测范围内与修改前行为一致，独立参考模型提供额外数值检查；这些都不是完整 RVV 形式证明。

`exact_update_v1` 使用了非法的 deferred-seed/local-rounding 参数组合；v2 又给只支持 FP32 的本地舍入模式输入 FP16。这两次断言失败保留，未通过关闭断言处理。v3 修正测试刺激后通过，v4 扩展为更新/归一化全部组合后通过。验收检查完整日志中的 Error/Fatal/断言，不能只看最终 PASS 字样。

整机 v1 的关闭候选基线有 21/22 项通过，`reduction_audit_tail` 超过 300 秒墙钟时限；该项不计为通过，也不据此判定为新 RTL 错误。v2 将单项墙钟时限提高至 1200 秒，硬件周期 watchdog 和预期结果不变，并把归一化共享也纳入候选。原失败目录保留。检查该程序发现共有 54 种操作/位宽组合、324 个用例，v2 同一用例再次达到 1200 秒墙钟时限，其余 21 项通过；日志末尾仍在执行整数规约测试，没有用超时充当结果通过。v3 将预算进一步设为 3600 秒，并在独立目录中并行执行两种配置；没有删去任何用例。v3 已全部通过：尾元素测试覆盖 324 用例，约 1863 秒完成。两种构建的 396 个源文件一致，文件列表只差三个候选开关；22 项 ELF 哈希一致，15 个有周期输出的窗口和所有测试结束时间完全相同，证据见 `comparison.json` 与 `provenance_audit.json`。这组结果对应三个开关一起开启，最终选择的仅共享归一化配置另行验证。

## 面积与时序

三项局部综合分别位于 `finalize_ppa_v1`、`exact_update_ppa_v1`、`exact_normalize_ppa_v1`。每项独立比较关闭/开启，采用相同冻结源码、工艺库和时序约束；共享更新的两组结果已完成，其余仍待收集。共享更新使面积从 17,256.455826 增至 18,343.247925，即增加 6.298%；两组 setup 无违例，但 hold 最差值由约 −0.08 ns 变为 −0.11 ns，违例数由 566 增至 979。故共享更新不纳入推荐配置，保持关闭，不能作为面积优化成果；原始报告及哈希见 `exact_update_ppa_v1/results_verified.json`。共享归一化的面积从 17,256.455826 降至 16,253.999840，减少 1,002.455986（5.809%）；两组 setup 无违例，最差 setup slack 分别为 0.000083 ns 与 0.000024 ns。最差 hold slack 均约 −0.08 ns，hold 违例数由 566 增至 614，仍需物理实现修复，不能声称时序已经完全收敛。证据见 `exact_normalize_ppa_v1/results_verified.json`。共享提取仍待结果。累加器测试使用分段、无本地舍入、延迟 seed、跳过无效舍入拍配置。局部面积不能直接乘到 Ara 总面积，局部时序不能代替整机关键路径。

现有 `full_scalar_after_prepare_v1` 整机综合只包含前一轮的单元素短反馈与输出寄存器精简，未包含本轮三个新增候选。其冻结输入不修改。`full_compact_prepare_v1` 已于 2026-10-13 06:51:40 UTC 启动独立整机综合，包含本轮选中的共享归一化及上一轮短反馈精简；运行在 `synopsys_workspace` 容器中，driver PID 1977440、DC PID 1977501。启动前核对 433 个输入文件与上一轮一致，源码差异仅为精确累加器和最终舍入器；新启用的宏只有共享归一化，工艺、时钟、核数、DC 脚本和 SDC 一致，详见 `baseline_input_audit.json`。整机报告尚未完成。最终是否默认启用候选，需要根据局部收益、整机回归和集成时序分别判断。没有通过布局布线证明 Fmax，也没有测量真实活动率功耗。

## 候选配置

`full_compact` 继承 `full_scalar_after`，仅增加 `ARA_RED_SHARED_EXACT_NORMALIZE=1`。不包含面积变差的共享更新，也不包含面积尚未完成验证的共享提取。保持队列深度、版本检查、精确位宽和各项原有吞吐机制。该配置的独立整机回归位于 `exact_area_soc_normalize_v1`，22/22 项全部通过，其中尾元素检查包含 324 个用例。15 个有周期输出的窗口和全部仿真结束时间均与基线完全相同。基线复用 `exact_area_soc_v3/baseline`，核对了 396 个源文件、文件列表、编译选项和 22 项 ELF 哈希，且基线自身也已完整通过。最终证据见 `comparison.json`、`provenance_audit.json` 及 `baseline_reuse_audit.json`。

5.809% 是单个精确累加器的局部降幅，不是 Ara 或 SoC 的降幅，也不意味着总面积开销已降到原版的 5% 以内。四 Lane 集成实际能省多少，需要整机报告；不将该局部面积与短反馈局部面积直接相加作为整机结果。

## 复现

输出目录必须不存在。测试入口固定基线提交并冻结当前源码、测试和输入数据，记录命令和哈希。整机两种模式并行运行，`--jobs` 是每种模式的并发数，总并发上限为它的两倍。`--prepare-only` 仅准备输入；省略该选项会实际调用工具。

```sh
python3 hardware/scripts/run_exact_area_unit.py --out hardware/build/exact_unit_recheck
python3 hardware/scripts/run_exact_area_soc.py --out hardware/build/exact_soc_recheck --mechanism none --normalize --jobs 2 --timeout 3600
python3 hardware/scripts/run_exact_area_ppa.py --block finalizer --out hardware/build/extract_ppa_recheck
python3 hardware/scripts/run_exact_area_ppa.py --block accumulator --accumulator-mechanism update --out hardware/build/update_ppa_recheck
python3 hardware/scripts/run_exact_area_ppa.py --block accumulator --accumulator-mechanism normalize --out hardware/build/normalize_ppa_recheck
```

面积收集入口 `collect_exact_area_results.py 目录… --out 新JSON` 只接受两个模式均成功完成、有完成标记且无 DC Error 的实验；同时输出面积、setup/hold 及报告哈希。它不会把未完成的中间面积写作最终数据。
