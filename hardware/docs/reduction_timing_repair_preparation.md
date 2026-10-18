# 时序修复候选与手动整机综合入口

本轮基于 `d074a7aa` 和 `reduction_tail_integrated_entry_v1` 的最终报告修改。当前是经过功能验证的时序优化候选，不是已经证明时序收敛的版本。已按后续指令于 2026-10-18 14:27:52 UTC 启动 Design Compiler；新的面积、setup 和 hold 结果待本轮整机综合完成后确认。

## 报告依据与覆盖范围

历史报告目录为 `hardware/build/synthesis/reduction_tail_integrated_entry_v1/backend/syn/ara_soc/v1-dc/reports/`。`qor.rpt` 中 clk_i 组 setup WNS 为 −0.310463 ns，报告违例路径数为 42,302；INPUTS 组为 −0.040381 ns、436 条。clk_i 组 hold WNS 为 −0.150243 ns、37,968 条；INPUTS 组为 −0.087097 ns、52 条。另有 1 条 transition 和 246 条 fanout 违例。这些是工具按组报告的计数，不代表同样数量的独立 RTL 问题。

| 路径 | 历史最差 slack/ns | 本轮措施及边界 |
|---|---:|---|
| SIMD 乘法 → VMFPU 结果队列 | −0.310463 | 把四种 SEW 的 `-product + c` 改为 `c - product`，避免表达式引入单独求负与相加的串联机会；工具可能本来就能化简，收益尚待测量。不增加流水级。 |
| SLDU 请求 → 共享浮点加法返回 | −0.309664 | 共享加法器用固定层数树形前导零检测替代优先循环；对齐与 sticky 计算合并为分级 jam 移位。保留单周期返回、仲裁与所有权规则。请求选择本身本轮未重构。 |
| 操作数队列 → VALU 结果队列 | −0.309688 | 纳入整机增量优化；本轮未改 VALU 队列/操作数协议，尚无证据宣称该路径消除。 |
| 精确 root → finalizer 结果 | −0.301089 | 最高位定位改为按二分窗口逐层选择，去掉“选分组后再动态读取位”的结构。保留 root、结果寄存器和完成周期。 |
| Seed → 精确 root | −0.175261 | 保留已经验证的 seed 时序边界，纳入增量优化；不添加新 seed 等待周期。 |
| UART 输入 → 门控相关端点 | −0.040381 | 保持原输入延迟，交给整机增量优化；不把接口路径设为 false path。 |
| CVA6 指令缓存寄存器 → SRAM 等 hold 路径 | −0.150243 | 启用 DC 的 `set_fix_hold [all_clocks]`，允许工具进行数据路径最小延迟修复。不能以 RTL 增加功能周期代替 hold 修复。 |
| transition / fanout | 1 / 246 条 | 保留原约束，增量优化并独立报告设计规则违例；未放开寄存器复制。 |

整机最差路径并不全部位于规约模块。这轮没有大范围改动 VALU、通用 FPU 或 CVA6 架构，也没有宣称只靠三处 RTL 化简就能消除所有违例。工具仍可能受面积、宏接口和组合逻辑深度限制；若新报告仍有违例，需要针对新路径继续迭代。

## 综合流程

保持 4 Lane、VLEN=1024、真实 ara_soc/CVA6/AXI/外设/1 MiB L2、原工艺库、1 ns 时钟、0.15 ns setup uncertainty、0.075 ns hold uncertainty。没有增加时序例外、放宽时钟或改变运算延迟。

`hardware/scripts/synthesis/templates/dc.tcl` 在首次映射前显式启用 hold 修复，保存首次映射 QoR/违例，再执行一次增量 `compile_ultra`。增量后的 setup、hold、设计规则和时钟属性分别输出报告。`flow.py` 的新摘要包含 `setup_met`、`hold_met`、`all_constraints_met`，综合进程正常完成不再被误读为时序全部满足。hold 修复和增量映射可能增加 buffer/单元面积，因此必须同时检查最终面积。

已冻结的输入目录：`hardware/build/synthesis/reduction_timing_repair_entry_v1`。该目录是新候选，不覆盖历史成功运行。prepare 已通过 391 个 HDL 文件、11 个库和容器工具路径静态检查；随后已通过统一 run 入口启动后台整机综合，运行于 `synopsys_workspace` 容器。

本轮已经启动的命令如下，不应重复执行：

```bash
python3 hardware/scripts/synthesis/unified.py run --out hardware/build/synthesis/reduction_timing_repair_entry_v1
```

若之后又修改 RTL，应在新的输出目录重新 prepare，不能认为旧快照自动包含新修改：

```bash
python3 hardware/scripts/synthesis/unified.py prepare --out hardware/build/synthesis/reduction_timing_repair_entry_v2 --period 1.0 --cores 8
python3 hardware/scripts/synthesis/unified.py run --out hardware/build/synthesis/reduction_timing_repair_entry_v2
```

## 验证记录

* finalizer：`hardware/build/timing_finalize_head_equivalence_20261018/finalize/manifest.json`，对修改前 HEAD 的 56,736 组测试通过，覆盖两种 extraction 设置与直接/seed-stage 组合、正负数、舍入、特殊值及随机状态。
* SIMD 乘法：`hardware/build/timing_simd_mul_head_equivalence_20261018_v2/manifest.json`，24 种配置通过（四种 SEW、0/1/2 级寄存器、定点开/关），每种配置 288 组定向输入和 20,000 个随机周期，检查数据、饱和标志、Mask、ready/valid、背压、气泡及复位；与 HEAD 比较每周期行为。
* 共享浮点加法：`hardware/build/timing_closure_shared_add_v1/manifest.json`，使用真实 fpnew FMA ADD 作参考，三种格式、六种舍入模式，每格式至少 100,000 组随机输入并含定向边界；已通过 2,324,034 次数值和异常标志比较（每格式 774,678 次），run.pass=true、依赖哈希检查通过。测试冻结后仅修正了一处关于零填充位置的注释，去除注释/空白后的 RTL 与测试快照完全一致。
* 完整 SoC：`hardware/build/timing_closure_soc_v1/execution.json`，冻结当前生产 RTL 与原有 50 个 ELF；编译与完整回归均已完成，50/50 通过。与上一版 `production_tail_integrated_soc_20261017_v1/production` 严格使用相同 ELF 比较，105 个测量窗口全部周期相同，50 项仿真结束时间也全部相同；没有更慢或更快的窗口。证据为 `hardware/build/timing_closure_soc_v1/compare_previous_tail/summary.json` 与 `comparison.json`。
* 综合流程工具测试：16/16 通过。

功能等价和周期保持不等于物理时序改善。只有新综合报告可以确认这些 RTL 表达方式在当前库下是否有效；布线后的时序还需要后端验证。
