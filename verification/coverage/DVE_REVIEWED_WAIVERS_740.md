# 740项旧镜像的已核验DVE豁免

## 范围与依据

本文件只说明冻结旧镜像的报告豁免，不修改RTL、不修复功能错误，
也不表示当前主线RTL已经完成signoff。740项输入全部来自正式
PASS集合，失败、超时及未闭环测试不计入。

| 豁免类别 | 指标 | 点数 | 依据 |
| --- | --- | ---: | --- |
| QBS pending metadata | 分支 | 448 | 已证明的结构不变量 |
| 操作数观察代码 | 分支 | 1832 | 非功能诊断代码；其中408点已命中，并非不可达 |
| 操作数参数边界 | 分支 | 1144 | 冻结参数与具体编译覆盖点 |
| FF1宽度边界 | 分支 | 904 | 参数宽度和已证明的范围边界 |
| 窄化指数边界 | 分支 | 1272 | 源码case范围证明 |
| FP16 packing边界 | 分支 | 208 | 已证明的下界 |
| MaskM/StA snapshot | 条件 | 24 | reset后生产、排队及元数据传播保持恒零 |

合计5832个精确点，不排除整个模块。MaskM/StA的8个待审分支、
port8、其他条件邻点保持未排除。LZC、额外QBS条件、RVH候选及
已发现功能错误不包含在此文件中。

## 实际统计

层级为`ara_tb.dut.i_ara_soc.i_system`，同一740项集合：

| 指标 | 无豁免 | 应用豁免 | 变化，百分点 |
| --- | ---: | ---: | ---: |
| 行 | 85.21% | 85.21% | 0.00 |
| 条件 | 82.03% | 82.04% | +0.01 |
| 分支 | 82.95% | 87.70% | +4.75 |
| FSM | 60.54% | 60.54% | 0.00 |
| Toggle | 63.33% | 63.33% | 0.00 |
| DVE Score | 74.81% | 75.76% | +0.95 |

这是排除已审核点后调整统计分母的效果，不是新增激励执行效果。
两类报告同时保留，不将其解释为解决了失败案例。

## 文件与复用

- 原生DVE文件：`waivers/old_image_reviewed_5832.el`。
- 适用性及审批记录：`waivers/old_image_reviewed_5832.json`。
- 原始全层级报告：`verification/out/final-raw740-dve-agent-20261007-01/summary.csv`。
- 正式豁免报告：`verification/out/point-only-5832-raw740-v4-agent-20261007-01/summary_waived.csv`。
- 工具：`apply_points740_v4.py`、`apply_points740_v4.tcl`。

在兼容设计的DVE会话中可加载原生文件：

```tcl
gui_exclusion_file -load -file {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/waivers/old_image_reviewed_5832.el}
```

加载前必须匹配design、shape及源码/参数证明。不要将该EL默认
加载到新RTL或其他配置；当前通用`run_dve_coverage.sh`不会因
目录中多了一份EL就自动应用它。新的集合需要重新核验适用性，
使用独立输出目录，并同时保留原始和豁免后的报告。

## 结果核验与显示缓存

实际同会话完成raw、applied、reloaded、reset四阶段。每次保存的
EL都与5832个已批准记录作精确语义比较，检查scope、checksum、
表达式和vector；不允许额外排除。四份empty EL均为空，740项
测试身份一致，源文件及VDB输入未变化。

DVE全树展开后部分子层级可能仍显示缓存值。正式豁免报告只使用
11个明确选择、重新设为根并处理GUI事件后读取的scope：system、
向量后端、VLSU、QBS engine、compute engine、两个payload buffer
及四个lane。六种指标均从实际rooted行读取；raw与原报告对应行
一致，reset恢复raw，applied与reloaded一致，行/FSM/toggle保持
不变。原2989行报告完整保留，包括外部UVM根；不声称豁免后
2989行都已重新刷新。

旧v2因环境变量警告和缓存显示保持HOLD，不作为正式豁免报告。
v4启动前移除不应传入DVE入口的`DVE`变量，仅允许已确认的精确
Qt退出提示，其他warning/error继续拒绝。没有重跑VCS仿真。
