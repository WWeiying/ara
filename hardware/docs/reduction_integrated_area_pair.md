# 规约面积精简的整机配对

本轮配对使用当前同一份 RTL 和完整 `ara_soc`：真实 CVA6、4 Lane、VLEN=1024、AXI/外围及相同 SRAM。参考侧是已有五项精简的规约优化实现，不是官方原始 Ara。v2参考侧与算术转发候选均已 COMPLETE，整机面积为3,217,815.8582→3,172,506.4267 μm²，Ara为1,192,619.6620→1,145,621.9986 μm²；面积分别下降1.4081%和3.9407%。1ns约束下报告的最坏reg2reg slack为−1.83705→−2.56573ns，两侧均未时序闭合，且有自动切环。最新v3在算术转发候选上继续静态裁剪旧后台状态并精简共享ADD，v3因拓扑统计把格式切片误计为执行单元而停止；修正检查后已重新启动 `area_pair_timing_v4`，硬件及约束不变，尚无新面积或时序结果。

| 配置 | 相对参考侧的开关变化 | 用途 |
|---|---|---|
| `area_pair_reference` | 无 | 当前五项精简实现的匹配参考 |
| `area_pair_compact` | 根 Lane 缓存、旧 FP 后台裁剪、八段精确累加、RCE/有序加法共享 | 测量四项组合的整机成本 |
| `area_pair_arithmetic` | 上述四项，再加算术消费者转发 | 测量允许轻微周期损失的额外面积折中 |
| `area_pair_timing` | 在arithmetic上增加静态后台状态、固定索引仲裁、共享格式结果寄存器 | v3面积与时序联合候选 |

独立有序 Mask 和归并互斥发射控制在三侧同时开启，不计入上述面积候选的增量。归并控制的18项同ELF配对回归和15个周期窗口已通过，但116项结构环路警告及其信号集合没有变化，尚无物理时序改善证明。三侧仍保持相同普通结果队列深度、共享有序单元数量、周期、时钟不确定度、库、输入驱动及输出负载，寄存器复制与合并均关闭。

新入口 [area_pair.py](../scripts/synthesis/area_pair.py) 复用原流程，不修改正在运行的 `flow.py`、`profiles.json`、模板或串行队列。新增配置及入口副本进入每套输入的 provenance 和冻结哈希集合。运行这组配置需使用新入口，原入口不认识新增配置名。

已准备的目录为 `hardware/build/synthesis/area_pair_reference_v2`、`area_pair_compact_v2` 和 `area_pair_arithmetic_v2`。[输入审计](../build/synthesis/area_pair_input_audit_v2.json) 验证436份源文件/头文件内容、390个HDL文件的顺序和包含路径、11个库、后端脚本及约束一致；只允许表中规定的宏差异。输入审计记录的是启动前的 `PREPARED`、`dc_started=false` 状态；随后参考侧和算术转发候选均完成；历史输入审计中的启动前状态不代表当前运行状态。v2的physical_summary中total_cell_area为空，上述面积读取实际area.rpt；v3已修正summary提取并检查数值有效性。

检查已冻结输入：

```bash
python3 hardware/scripts/synthesis/audit_area_pair.py \
  hardware/build/synthesis/area_pair_reference_v2 \
  hardware/build/synthesis/area_pair_compact_v2 \
  hardware/build/synthesis/area_pair_arithmetic_v2 \
  --out hardware/build/synthesis/area_pair_input_audit_v2.json
```

四项中间配置的执行入口示例；此命令会真正启动 DC，当前该中间配置尚未启动：

```bash
python3 hardware/scripts/synthesis/area_pair.py run \
  --out hardware/build/synthesis/area_pair_compact_v2
```

后续须检查工具完整终态、映射覆盖、实际 setup/hold 路径、自动切环警告，以及相同 ELF 和测量区间下的功能及周期。局部面积不能乘 Lane 数作为整机结论。既有算术转发18项功能测试通过、20个窗口中最坏周期增加0.6383%；50项扩展回归已完整通过功能检查，105个窗口中两项周期退化，严格零退化比较仍为false。最终配置取舍需使用完成后的整机配对和性能证据。

旧v1准备目录保留，不改写其冻结文件。v2在私有模板中将全寄存器集合的 `-from/-to` 查询改为 `clk_i` 路径组最坏单路径查询，验证起点和终点所属单元都在 edge-triggered 寄存器集合中；若验证不成立则报错，不把它冒充寄存器间最坏路径。SDC、时钟、综合优化选项及其他报告保持相同，新增 `reg2reg_query_scope.rpt` 标明范围。只读旧检查点探针约357秒完成，但仍有自动切环警告，回放slack约−2.712ns，与旧报告约−2.157ns不同；它证明查询方式可执行，不证明时序闭合或稳定Fmax。

最新候选于2026-10-15 05:50 UTC通过Make入口启动：`area_pair_timing_v3`，driver PID3929393，已确认容器DC进入ANALYZE。启动前，组合22项两侧功能全部通过，18个计时窗口相同；共享后端四种配置逐拍对照通过。两组各50项的扩大消融与局部PPA仍在运行，不冒充已经完成。v3匹配参考 `area_pair_arithmetic_v3` 仅PREPARED，没有同时启动第二套整机。

[输入审计](../build/synthesis/area_timing_input_audit_v3.json) 核对两侧436份源/头文件、390个HDL顺序、11库及约束，仅三个独立宏不同。原五项报告任务的停止记录仍保留，未重启用户要求停止的旧任务。查询最新候选：

```bash
make -C hardware dc_status dc_profile=area_pair_timing \
  dc_out=/home/wangwy/openproject/ara_reduction_optimization/hardware/build/synthesis/area_pair_timing_v3
```

修改细节及证据见[面积与收益跟进记录](reduction_area_benefit_followup.md)的“第三轮面积与时序联合精简”。

最新状态更正：v3的RUNNING记录已被随后FAILED终态替代。两组50项扩大回归现已全部通过，各105窗口相同。修正拓扑检查后重启目录为`hardware/build/synthesis/area_pair_timing_v4`，查询状态时将上述dc_out末尾的v3换为v4；v3保留失败证据。
