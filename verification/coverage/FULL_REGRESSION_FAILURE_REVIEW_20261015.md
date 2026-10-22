# 全回归失败复核与补跑

## 执行真实性

本轮登记的 798 项均有匹配当前镜像和输入 ELF 的实际执行证据，没有发现漏跑。
审计不以父进度文件中的 `executed` 汇总字段代替实际记录。原记录中 748 项直接
保存数值退出码，49 项只能由上层 shell/结果链推导为零；原 c0375 超时记录没有
正常退出码。第 727 项的历史清单存在身份恢复例外，已根据封存的原始命令及 ELF
哈希单列，不能描述为无条件匹配旧清单。

执行审计：
`verification/out/full-regression-failure-review-20261015-01/execution/README.md`。
这是执行及身份审计，不等于所有 798 项功能检查已经通过。

## 原 28 项失败

### 17 项控制类测试

这些程序测试标量计算、CSR、页表、异常或 FENCE，不要求分配向量执行 VID。
统一的向量 UVM 测试却要求至少有一组 CVXIF 请求和向量 VID，因此原日志中出现
`CVXIF/NO_TRAFFIC`、`VID/NO_TRAFFIC`。软件自检成功不能直接覆盖这些报错；本轮
建立了单独、绑定精确 ELF 的控制类验收范围。

重新检查包括完整终止、精确软件检查数、RVFI 顺序、请求/响应配对、零协议错误、
无遗留事务，以及所有经 CVXIF 的指令只能是已审核的向量 CSR 操作。若出现向量
数据指令、自定义指令、其他 UVM 错误或矛盾计数，检查必须失败。没有全局屏蔽
UVM_ERROR，原日志和原失败结果均保留。

17 项按此范围通过。e0638/e0727 另补核恢复 PC、捕获 store、异常与当前 controller
路径；e0639/e0641 保留其额外 UART/HPM 检查。没有宣称重新证明旧基线的精确 FSM
增量、安全属性或旧 relative727 protection delta。

- 实现：`control_scope_audit_20261015.py`、`audit_control_fence_20261015.py`。
- 证据：`verification/out/full-regression-failure-review-20261015-01/control-scope-final/`、`fence/`。

### 11 项 Tcl 探针测试

旧扫描器把多行 Tcl 命令回显内的 `puts "...PROBE_ERROR $failure"` 当作运行时错误。
新分类器仅识别与已校验哈希的冻结 Tcl 源码完全相同的完整命令；使用 Tcl
`info complete` 识别语法边界，不执行源码。实际运行时错误、未知格式和截断回显
不能被过滤。

清除误报本身不构成通过。11 项进一步复用原独立数值、CSR、异常、VRF、内存保护、
事务生命周期等适用的检查器，对本轮已生成输出重新核对，功能结果均通过，无需
重复仿真。其中 QBS/AKV 的自定义操作使用其独立架构及生命周期 oracle，不宣称
Spike 能执行自定义指令。

6 项内部波形 witness 也通过。e0786/e0788/e0791/e0792/e0794 的旧内部 owner/TID
检查仍需适配当前源码约定；它们与已经通过的架构结果分开报告，不将缺少内部证明
称为硬件错误，也不伪称这些内部证明已完成。详细剩余方案见下列 README。

- 实现：`ucli_runtime_log_20261015.py`、`audit_probe_semantics_20261015.py`。
- 最终证据：`verification/out/full-regression-failure-review-20261015-01/probe-semantics/audit.json`、`README.txt`。
- 初始及中间审计报告保留，最终摘要明确引用最终阶段结果。

## 两项超时

| 项目 | 原预算 | 观察 | 一次性补跑预算 |
|---|---:|---|---:|
| c0375 Q3_K decode projection | 300 s | 向量计算和数值自检已完成，输出尾段被截断；旧通过耗时接近 300 s | 600 s |
| e0784 VALU restart | 900 s | 向量响应/完成已配平，继续核对源数组；旧正常结束约 851 s | 1200 s |

仅这两项补跑，保留相同 ELF、镜像、seed、周期看门狗和覆盖配置，使用独立目录
两路并行，不自动重试。本轮不重新编译、不改 RTL、不改变软件规模。

c0375 已正常结束并通过完整 benchmark 记录、数值自检、trace、协议及 VDB 检查。
e0784 的最终状态以补跑进度文件为准；正常仿真后还自动检查完整 scalar/vector
参考、12 个目标指令、VRF/CSR/source guards、生命周期和当前 VDB 身份，不能仅凭
退出码算通过。

```bash
cd /home/wangwy/openproject/ara_dsa_signoff_integration
jq '{status,counts,cases:(.cases|map_values({status,reason}))}' \
  verification/out/full-regression-repair-replays-20261015-01/progress.json
```

## 后续汇总

`collect_failure_review_20261015.py` 已作为独立后台任务安排，等待两项补跑完成后，
生成不覆盖旧结果的新 798 项账本，并对核验通过的当前镜像 VDB 使用 DVE 汇总。
模块级 cache 专项不与 SoC VDB 混合。失败、超时、94 项尚缺专用审计的扩展仍被
排除；旧内部 witness 未完成的状态也在新账本保留。功能回归通过不是全芯片 signoff。

```bash
jq . verification/out/full-regression-reviewed-20261015-01/status.json
```

覆盖率正式报告仅在新目录 `dve/summary.csv` 完整导出后有效，不使用 `.partial`
文件，也不强行套用不匹配新设计的旧豁免。原回归输出保持不变，不能将其历史
`COMPLETE_WITH_FAILURES` 文本改写成新的验收结果。
