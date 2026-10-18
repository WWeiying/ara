# 统一规约版本

当前统一版本的收尾周期回收已完成整机验证，最终快照为 `production_tail_integrated_soc_20261017_v1`：50/50 功能通过，同 ELF 的 105 个性能窗口相对时序分级前规约参考为 18 个不变、87 个减少、0 个增加，与首 header 旁路快照全部一致。稠密 8 窗口、seed 边界 8 窗口、正式 SeedReceive=0 的 500 帧及普通写回/packet 真并发测试均通过。详见 `reduction_tail_overhead_recovery.md`。共享加法器和关键寄存边界保留。用户现已授权启动冻结版本的整机综合，目录为 `hardware/build/synthesis/reduction_tail_integrated_entry_v1`，DC 已在 `synopsys_workspace` 容器后台运行。整机面积与 setup/hold、Fmax 等待最终报告，不能宣称整体物理收益已验证。

当前版本的可随提交保存的验证快照见 [reduction_validated_snapshot.json](reduction_validated_snapshot.json)，包含生产源码哈希、50 项 ELF 标识、105 个周期窗口及定向测试摘要。完整仿真日志和综合产物保留在本地 build 目录，不纳入 Git；本轮综合仍在运行，快照没有声称物理验收完成。

本分支只有一套正式构建配置：`reduction`，4 Lane、VLEN=1024。以已完成整机综合的 `area_pair_direct_reference_v1` 为基础，接入三格式共享标量加法器。配置清单位于 `config/reduction.json`，普通构建由 `config/reduction.mk` 固定对应选项，综合由 `hardware/scripts/synthesis/unified.py` 使用相同宏集合。无需选择面积候选或逐项填写优化开关。

该版本包含已有规约收尾解耦、混合执行、Late Seed、精确累加与中央收尾，以及已验证的根缓存、八段表示、旧后台状态裁剪、共享规约加法后端、算术消费者转发和调度控制精简。结果队列深度为4，共享有序加法单元数量为1。FP16/FP32/FP64 共用 `shared_scalar_fp_add` 的对齐、加减与规格化通路，保留各格式所需的舍入处理。原有返回寄存器、仲裁、标签和反压协议保留；可选非标准格式仍使用原 fpnew 实现。直接读取及四段表示关闭。

普通硬件构建沿用原命令，自动包含统一配置。综合统一使用仓库根目录的 `./s`：

```bash
./s prepare
./s check
./s run
./s status
./s report
```

`prepare` 和 `check` 不启动综合；`run` 才启动 DC。默认输出目录为 `hardware/build/synthesis/reduction`，新一轮可通过 `--out` 指定独立目录。也可使用 `make -C hardware dc_flist`、`dc_preflight`、`dc`、`dc_status`。正式入口只接受 `reduction` 配置。原研究脚本及 `build` 下冻结实验保留用于审计和复现，不是日常构建的配置菜单。RTL 内已有条件分支暂保留，正式构建宏固定，未启用分支不进入相应硬件；此轮没有清理未经验证的大片 RTL。

选择依据：参考侧整机面积3,165,155.922700 μm²，最差setup裕量−1.073843 ns；直接读取候选面积3,162,281.274633 μm²，仅节省0.091%，setup恶化约27.7 ps。因此采用参考方案。上述结果为DC综合单元面积，时序尚未闭合。50项整机对照均通过，105个性能窗口周期一致。统一入口不构成新的PPA改善，这些历史面积与时序数字不包括新共享算术及后续时序修改。

历史整机证据位于 `hardware/build/synthesis/area_pair_direct_reference_v1`；功能对照位于 `hardware/build/exact_direct_read_soc_v2`。未启动新的综合、未推送提交。

首次统一配置的历史入口验收（早于共享算术接入及本轮时序修改）：`reduction_unified_entry_v1` prepare通过，390份HDL、11个库；其宏集合、36份Ara生产RTL哈希、库哈希、1ns时钟和0.15ns不确定度均与所选参考综合一致。普通Make构建展开后的规约宏与同一清单逐项一致，旧直接读取/双共享单元命令行值不会改变正式配置。Python语法、shell语法及git diff空白检查通过。当时尚未改变有效RTL，因此该历史检查不代表后续共享算术或时序修改通过了50项动态回归。

## 共享算术接入与时序修正（2026-10-17）

正式 Bender 文件表已加入共享加法器，综合入口的结构检查改为每个共享执行单元一个 `i_format_shared_add`。`reduction_shared_integration_v1` 静态准备通过（391份HDL、11个库），未运行DC。该快照只含共享加法器接入，不含随后 VMFPU/RCE 时序修正。

局部同条件综合：旧固定ADD后端16910.039967 μm²，共享算术6970.991996 μm²，减少58.776%。这是局部算术包装模块结果，不能替代整机增量面积或整机时序结论。历史共享算术数值对照覆盖FP16/32/64、六种舍入编码，共2324034次比较；正式接入后的后端协议测试覆盖1/2单元、4/5客户端，四组通过。正式direct-off整机组合回归独立记录在 `hardware/build/production_shared_scalar_soc_20261017_v1`，完成情况以其execution.json为准。

后续时序修改独立验收：VMFPU有序规约从token/源操作数直接构造共享加法请求，避开普通FPU反馈数据选择路径，并加入实际接受请求时的操作数一致性断言。精确RCE复用原完成缓冲，结果必须寄存后才发布，切断finalizer到VRF/下游消费者的组合通路；无阻塞时最终结果可见时间增加一拍，local_done不等于架构完成。没有增设第二个结果队列，也没有改变精确计算或舍入算法。回归与周期差异需要单独记录，不能沿用加法器单项实验的“周期完全相同”结论。

第三项时序修改进一步将seed的精确插入和finalizer舍入分开：新增 `EXACT_SEED_ADD` 状态及组合seed模块，复用已有root/metadata寄存器，不增加第二组288-bit寄存器。最终无阻塞收尾相对历史透明路径增加两拍。56736组分级数值差分和输出缓冲逐拍测试通过；最终整机组合以 `production_shared_seed_stage_soc_20261017_v1` 为准，前两轮为消融。详细依据、代价和验证边界见 `reduction_timing_followup.md`。

## 历史 seed 分级验收（2026-10-17）

正式配置采用共享算术、直接有序操作数、寄存完成输出和seed分级的最终组合。三个消融快照分别完成50/50整机功能回归；各105个性能窗口的标签严格匹配。共享算术单项105窗口周期全部不变；增加完成缓冲后20窗口不变、85窗口增加、最大增幅5.35%；最终组合仍为20窗口不变、85窗口增加、最大增幅10.70%（Slide与seed混合短窗口299→331周期）。周期增加是收尾分级的代价，不能在没有新时序测量时声称实际执行时间改善。

当前40项RTL映射及两个共享后端模块与最终测试快照哈希一致。56,736组seed分级数值差分、定向协议和静态构建检查通过。最终验收记录为 `hardware/build/reduction_timing_acceptance_20261017_v1.json`，逐窗口四版本对照为 `hardware/build/production_shared_soc_comparison_20261017_v1/windows.md`。本轮没有启动综合，没有新的WNS/Fmax或整机面积结论；修改尚未提交或推送。
