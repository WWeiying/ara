# QBS M4 交错激活跨 word 定向覆盖

## 目标和依据

基于 gap80 的687项旧镜像 PASS 原始位图，以下条件仍未命中：

- 实例：`i_qbs_engine.i_compute_engine.i_block_adapter_bank0`。
- metric：Condition，checksum：`2250470448`。
- native expression ID：150，raw index：400，目标 vector：1。
- 表达式：`activation_target[0].offset[3:0] == 1`。

父会话用`targeted_point_delta.py`独立核验现存位图，并保存
`verification/out/gap81-m4-phase12-target-before-20261006-01.json`。
该实例的`activation_target[0].offset`相关18个历史未命中条件仍为零。
这些是诊断 raw points，不是18个已批准豁免，也不是DVE百分比。

## 可证伪的静态假设

实际激励使用Q5_K权重及Q8_K激活，M=4、N=1、K_blocks=1，即K=256。
最初静态例子使用Q4_K；实际采用数值可精确推导的Q5_K原生定向数据，
并复用独立的解码和M4打包参考。该输入不是模型捕获数据。
目标由激活布局和源拍phase决定，不依赖这两种
权重profile的差异。新的源码显式检查Q5_K，不混称Q4_K测试。
权重为ROW_MAJOR，激活为M4_INTERLEAVED；激活基址为64字节对齐
缓冲区加12，保持接口要求的4字节对齐。

reader首拍只返回该range前4字节，后续16字节拍的range offset依次
为4、20等。offset132的拍经M4映射，每个context得到native offsets
33至36。扣除4字节scale后，quant payload offsets为29至32，
跨越SRAM word边界。没有旧pending干扰时，首轮可写前三个字节位置，
保留末尾四字节；adapter保存整拍targets，pending byte0的native
offset为33，因此低四位等于1。即使该byte已消费且strb为零，offset
译码仍能触发上述条件。未消费的数据必须随后正确提交，不能以覆盖
命中代替数据正确性。

已有测试包含ROW_MAJOR的M4/A4、M3/A8、M2/A12，以及M8/A4的packed
布局；缺的是M4_INTERLEAVED和phase12同时出现，不应靠堆随机seed
寻找这个确定的映射组合。相关reader、compute、adapter、payload及
package源码已与旧build pins核对一致。

## 激励和验收要求

- 新建独立激励，不改历史gap51源码、已保存oracle或旧结果。
- 复用成熟的完整VRF、CSR、输入缓冲、descriptor和guard检查。
- 使用独立软件参考计算四个输出；检查目的寄存器尾部及其他寄存器。
- 检查激活基址模16确为12；保留全部1168字节Q8_K输入及metadata。
- 仿真只使用冻结旧镜像，独立trace和VDB；RTL bug仅记录，不修复。
- 通过计算和契约验收后，确认raw index400从0变1，才声称目标覆盖提升。
- 若同拍有旧pending，实际remaining mask可能不同，应按真实轨迹分析，
  不强行要求静态举例的`0xf000`。

## 已完成预检与当前运行

独立目录`gap81-m4-phase12-preflight-20261006-02`已完成编译及host
预检：独立MAC、bsums、M4打包一致，四个输出为256、512、768、1024；
1024-word VRF、12个CSR值及3440字节源数据保护契约保留，52项host
负例被拒绝。ELF中的custom word、VL1及激活地址模16等于12已核验。
父会话再次执行独立preflight验收通过。

已通过`ara-coverage-gap81-old-image-20261006-01.service`启动旧镜像
VCS，输出在`verification/out/gap81-old-image-20261006-01/`，实际
commit日志增长，尚未通过最终RTL验收或计入覆盖率。

独立审查发现初版运行验收脚本错误地要求单命令检查数18；18是host
额外reference检查后的计数，DUT对应17，DUT最终总计24。原始driver
源码已保存为输出目录的`driver-source-original.py`。不修改正在运行
程序的封存输入，也不修改原始日志；待本次VCS结束后以修正后的
独立验收读取原始结果，避免因检查脚本错误重跑仿真。

合并前还须严格核对DVE输入为`[design_vdb, *baseline_bitmap.tests]`，
成员唯一，并将该清单纳入哈希绑定。只有功能验收通过的本项VDB
才可附加；raw400未命中时只能报告运行通过，不能报告目标覆盖提升。

## 首次实际结果

本次VCS已正常结束，CPU Time为105.490秒。日志记录单命令17项
检查、最终24项检查均零错误，完整VRF/CSR/source检查计数正确，
`Core Test *** SUCCESS ***`；28次请求对应28次响应，异常、协议
错误和未完成请求均为零。

初版driver仍按18判断，因此保存了`FAIL: DUT command selfcheck
incomplete`。这是已定位的验收工具问题，不是本次RTL首错；不能
删掉该失败记录或直接改成PASS。正在用新sidecar离线复核原日志，
不重跑VCS。

父会话直接读取本次`cond.verilog.data.xml`，确认目标实例checksum
仍为2250470448、条件宽度5914，raw index400为1；旧687项对应位
为0。可达性假设得到实际覆盖证据支持。完整功能验收和DVE合并
仍待完成，尚不宣称688项正式汇总或给出新的覆盖百分比。

父会话随后直接执行修正后的独立`runtime()`检查原始日志，结果PASS：
解析25776行commit记录，确认28次请求/响应、9次后端分配/完成守恒；
唯一QBS命令对应的512字节架构写回逐字节符合独立参考值。
17项单命令和24项最终软件检查及完整状态检查均满足契约。
此结果证明本项功能检查通过，不替代尚待执行的完整来源绑定、
覆盖率合并与DVE报告验收；原driver的FAIL记录仍原样保存。

## 实际原始覆盖增量

`gap81-offline-rechecked-20261006-01/raw-bitmap-delta.json`相对旧687项
显示122个新增原始条件位：bank0 adapter 20、bank0 payload buffer 60、
bank1 adapter 8、bank1 payload buffer 34。行、分支、FSM增量均为0。
这是逐位bitmap诊断，不能直接当作DVE条件百分比或功能覆盖率。
正式百分比仍应读取成功完成、输入成员核验通过的DVE报告。

曾重复启动`ara-gap81-offline-recheck-20261006-01.service`；父会话
确认两任务实际存活后停止了后启动的重复任务，保留其输出。
继续保留先启动的`gap81-offline-rechecked-20261006-01`任务，
没有因观察超时重跑仿真，也没有覆盖原VDB。

## DVE环境修正及重试

先启动的报告任务保存为FAIL：启动器产生`DVEENVDIRNFND`警告，
明确要求调用方不要设置`DVE`环境变量。封存环境工具先清理继承变量，
却又从identity记录重新加入了`DVE`，因此警告来自启动环境构造，
不是VDB不兼容或RTL计算错误。GUI完成标记不能越过该诊断失败。

独立`retry_gap81_dve.py`只在调用入口取消`DVE`，保留封存的
`VCS_HOME`及实际执行文件身份核验，让原安装启动器推导自身路径。
仍然拒绝所有原诊断项，不使用旧`summary.csv.partial`。
任务`ara-gap81-dve-only-retry-20261006-01`输出到
`gap81-dve-only-retry-20261006-01`，已观测并核验本次子进程的
`dve.exe`。最终报告验收尚待完成，未改变原失败记录或重跑VCS。

## 完成的历史集合报告

`gap81-dve-only-retry-20261006-01/status.json`已为COMPLETE，
`combined-dve/summary.csv`正式生成，无需使用partial文件。
输入是原687项历史PASS集合加本项，共688项；旧前缀没有全部按当前
checker重新准入，此报告不作为当前RTL全量signoff证明。

| i_system指标 | 旧687项 | 加GAP81后688项 |
|---|---:|---:|
| Line | 80.44% | 80.44% |
| Condition | 81.22% | 81.28% |
| Branch | 79.99% | 79.99% |
| FSM | 60.46% | 60.46% |
| Toggle | 62.90% | 62.90% |
| Score | 73.00% | 73.01% |

本次没有新增豁免，报告百分比来自DVE正式输出，而非raw bit数量估算。
