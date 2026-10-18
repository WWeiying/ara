# 共享算术接入后的时序修正

本轮不运行综合。分析依据是 `hardware/build/synthesis/area_pair_direct_reference_v1/backend/syn/ara_soc/v1-dc/reports` 中的历史报告；其中共享后端仍采用三个固定 ADD 切片。因此以下时间值不是当前共享算术 RTL 的测量结果。

## 报告揭示的两类长路径

`reg2reg_max.rpt` 的最差路径从 Lane 0 bulk FPU 的转换流水寄存器出发，经通用结果/反馈选择、ordered request、共享 FP64 加法，到共享响应的 NX 寄存器。到达时间1.932168 ns、要求时间0.858325 ns，裕量−1.073843 ns。bulk结果约在0.618370 ns到达，加法器输入约在0.860515 ns到达。前100条路径中67条终止于共享加法器。即使算术后端缩短，保留前级通用反馈选择仍可能拖慢整个通路。

另外33条路径从精确规约 seed 寄存器经 finalizer、RCE结果、Lane写回总线进入VLSU地址生成逻辑，最差裕量−1.054539 ns。finalizer结果在约1.489393 ns才到达；透明完成缓冲又把后级组合延迟接在其后。这不证明该操作能在架构上作为地址使用，而是说明共用数据总线在结构上允许STA追踪此通路。

## 实施变化及代价

共享加法器已经接入Bender与统一构建，FP16/32/64共用对齐、加减、规格化，仍保留原有结果寄存器及握手协议。可选的其它格式保留旧后端。这项本身不改变请求到响应的周期数。局部历史综合面积减少58.776%，不等于整机面积减少相同比例。

`vmfpu.sv` 为共享有序规约请求直接构造两个加法操作数：首个元素使用seed，其余元素使用已寄存的SLDU token；源元素经过原有的有序元素提取函数。它不再从包含普通FPU反馈的通用operand mux取数。现有的指令选择、mask、预取和握手保持原语义；增加请求接受时与原operand值逐位相等的断言。该变化移除数据路径中的无关反馈选择，不声称消除了bulk输出valid经仲裁影响共享单元的所有控制路径。

`reduction_completion_engine.sv` 将已有的exact completed槽改为非透明输出。finalizer结果只有存入该槽后才能发布。占满且下游停顿时保留数据和owner；旧结果pop与新结果push同拍时以新结果替换；没有把local_done当作instruction_done。缓冲数量不变。无阻塞时结果可见时间增加一拍，seed依赖链可能累积额外周期，需要回归量化。仅这一修改仍不足以切开finalizer内部算术；最终版本进一步实施下述seed分级，仍不宣称时序闭合。

## 验证边界

正式共享后端协议测试目录为 `hardware/build/production_shared_ordered_unit_20261017_v1`，覆盖1/2单元、4/5客户端，四组通过，包含与旧后端逐周期比较。

`hardware/build/production_shared_scalar_soc_20261017_v1` 冻结共享算术单项变化，使用direct-off参考的同一组50 ELF；`hardware/build/production_shared_timing_soc_20261017_v1` 进一步冻结当前生产RTL中的VMFPU与RCE时序修改。两轮均以功能通过为硬条件，时序修正一轮单独列出性能窗口周期变化。完成状态以各目录的execution.json为准；未完成之前不能宣称50项通过。

统一综合入口静态准备与检查通过：`hardware/build/synthesis/reduction_shared_timing_entry_v1`，391份HDL、11个库。只做文件准备和环境检查，没有启动Design Compiler。实际setup/hold改善、整机面积和Fmax仍待用户后续授权综合确认。

## 第三项：seed绑定与舍入分级

继续检查finalizer内部后，将seed的精确插入移到独立组合模块 `fp32_exact_reduction_seed`。RCE新增 `EXACT_SEED_ADD` 状态，在所有Lane部分结果和正确seed到齐后，只执行一次精确加法并更新特殊值、非零和正负零元数据。结果写回已有的root/metadata寄存器，然后进入原有结果生成状态。没有增加另一组288-bit寄存器。

RCE中的finalizer将 `seed_in_exact_i` 固定为1，令seed插入算术从其有效组合路径中静态消失，而不是用运行时state选择信号掩盖串接路径。最终舍入仍只做一次；原seed寄存器保留，供全mask场景原样复制seed。局部完成仍不释放指令的结果所有权。该分级在前两项基础上再增加一拍收尾时间；与历史透明缓冲相比，普通无阻塞精确规约总计增加两拍收尾。最终性能应以全生产配置回归为准，不能把前两项快照的周期直接当最终结果。

统一综合入口仅补充 `reduction_exact_seed_max.rpt` 定向查询，以便未来区分seed宽加法和后续规格化的路径；不修改时钟、时序例外或目标约束，不启动综合。

第三项单元验收：`hardware/build/exact_seed_stage_unit_v1/finalize` 的56736组差分全部通过，包括普通/已插入seed、两种提取实现和完整异常标志比较；`oracle` 的900组独立数值oracle也通过，但该oracle原TB直接调用组合finalizer，不能单独作为新增seed分级的证明。新增组合分级等价性由前一差分测试覆盖。`hardware/build/rce_exact_seed_output_buffer_v2` 通过逐拍状态、输出反压、同拍替换和复位测试；其RCE/finalizer源哈希与工作树一致。首次协议编译因VCS不支持层次enum标签引用失败的目录保留；修正TB表达方式后重跑通过，未修改期望数值。

最终整机回归冻结在 `hardware/build/production_shared_seed_stage_soc_20261017_v1`，另两轮保留为单项消融。静态综合准备与检查目录更新为 `hardware/build/synthesis/reduction_seed_stage_entry_v1`，391份HDL、11个库通过；仍没有执行综合。

## 尚未证明消除的违例

旧 `timing_min.rpt` 最差hold为−0.150159 ns，从CVA6 icache适配器寄存器到icache SRAM，属于当前规约改动以外的短路径。此轮没有添加RTL延时或放宽hold约束掩盖它。共享加法器输入仲裁控制、seed阶段自身的宽加法、finalizer剩余的绝对值/规格化/舍入、requester到VALU路径和CVA6侧路径仍需未来新报告评估。本轮通过结构分级移除了已识别的主要长串接，不声称setup/hold全部闭合，更不能在禁止重新综合的条件下报告一个新的WNS。

## 收尾周期与资源所有权

以最后一个limb在边沿T被接收、seed已经就绪且下游始终ready为例：历史路径在T后进入EXACT_RESULT并输出组合结果，T+1写回；新路径在T后进入EXACT_SEED_ADD，T+1把带seed的root和元数据寄存并进入EXACT_RESULT，T+2把舍入结果存入completed槽并释放exact工作状态，T+3由下游接受结果。因此结果接受相对历史增加两拍，exact工作状态的释放增加一拍；completed槽允许旧结果尚未写回时接收下一上下文。源Lane的local_complete时点保持最后limb接受时（late seed未就绪时仍等待绑定），没有提前产生架构完成。

长向量可用Lane-local执行遮蔽一部分尾部开销；短向量、seed链可能直接暴露新增周期。以最终同ELF回归逐窗口计数为准，不能仅凭时序分级推断实际执行时间改善。

最终版本优先整机检查 `hardware/build/seed_stage_priority_checks_v1`：有序规约边界、宽化有序流、masked ordered alias、exact混合、FP late seed、有序舍入共6项全部通过，使用第三轮同一冻结simulator及ELF。此检查用于在完整长回归结束前尽早覆盖新状态边界和直接操作数断言，不能替代50项总验收。

## 2026-10-17 完整整机回归与逐标签周期证据

三轮冻结回归均已执行完成，各目录 `execution.json` 均为 `COMPLETE`，50项功能测试全部通过，driver均退出0。参考为 `hardware/build/exact_direct_read_soc_v2/baseline`，保留其direct-off编译参数并使用同一组50个冻结ELF。没有重新运行综合。

| 冻结版本 | 功能 | 105窗口相同 | 周期增加 | 周期减少 | 最大相对周期回退 |
|---|---:|---:|---:|---:|---:|
| 仅共享算术 `production_shared_scalar_soc_20261017_v1` | 50/50 | 105 | 0 | 0 | 0% |
| 再加VMFPU直接操作数与非透明完成槽 `production_shared_timing_soc_20261017_v1` | 50/50 | 20 | 85 | 0 | 5.351171% |
| 最终seed分级 `production_shared_seed_stage_soc_20261017_v1` | 50/50 | 20 | 85 | 0 | 10.702341% |

最大回退对应同一完整标签：`perf_rce_exact_slide_seed` 的 `RCE Slide seed PASS: pairs=16 vl=4 sew=32 lmul=1`，baseline/shared/timing/seed-stage分别为299/299/315/331 cycles。仅共享算术一轮的50项 `$finish` 时间也全部与参考相同。后两轮的周期增加已单独保留；其 `all_no_cycle_regression=false` 不影响功能通过结论。

独立collector `hardware/scripts/collect_production_shared_soc_comparison.py` 重新读取四套完整stdout，只将被提取的cycle数字替换为占位符，其它字符及数值字段（包括sew、vl、mask、chain、reductions、chain_span、pairs）均严格比较。105个窗口标签全部匹配，无缺失、增加或顺序差异。输出保留四套完整原行、cycles、相对baseline的差值与百分比：

- [逐标签105窗口表](../build/production_shared_soc_comparison_20261017_v1/windows.md)
- [完整JSON与50项结束时间](../build/production_shared_soc_comparison_20261017_v1/comparison.json)
- [collector命令与脚本哈希](../build/production_shared_soc_comparison_20261017_v1/command_evidence.json)

`perf_exact_backend_tradeoff` 中36个 `chain=0` 窗口，timing/seed-stage相对参考分别固定增加16/32 cycles；36个 `chain=1` 窗口则分别增加1或2 / 2或4 cycles。该benchmark的chain包含重复源复用，不能将这一组结果推广为所有真实seed依赖链的开销上界。逐标签原值及分组记录见 [tradeoff_chain_groups.json](../build/production_shared_soc_comparison_20261017_v1/tradeoff_chain_groups.json)。

正式shared ordered单元四组验收保持通过，包含1/2单元、4/5客户端和legacy逐周期比较。首轮reference到production映射中，除被替换的shared ordered后端外，其余40项映射RTL的哈希一致。第二轮的其它差异仅为VMFPU与RCE；最终轮再增加finalizer差异。最终快照包含40项production filelist映射和两个共享算术源；其中 `axi_inval_filter.sv` 有两项映射，合计41个唯一生产文件。收尾检查确认这41个当前生产文件均与最终冻结源哈希一致，见 [current_production_hash_check.json](../build/production_shared_seed_stage_soc_20261017_v1/current_production_hash_check.json)。各轮准备/运行命令、源路径和差异清单分别保存在各新目录的 `production_validation_evidence.json` 与 `manifest.json`；没有改写历史回归结果。
