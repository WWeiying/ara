# 当前 RTL 全量覆盖率重收集

## 本轮范围

在 `ara_dsa_signoff_integration` 验证工作树运行，不修改 RTL，不重新编译，
不调用 Verilator 或 URG。复用已通过修复回归的 VCS coverage 镜像：

`verification/out/repair-closure-coverage-20260927-01/sim/simv`

启动前核对了 458 项编译源码记录与当前源文件一致，镜像组件与既有运行记录一致。
配置为 4 lanes、VLEN=1024、2 MiB 仿真内存，启用 QBS/AKV/AKV-v2、AXI delay
及故障观察探针。本轮结果仅对该冻结配置有效。

| 输入集合 | 处理 |
| --- | --- |
| 历史 427 PASS | 只作为程序选择依据，旧 RTL 的 VDB 不进入汇总 |
| 最新 21 PASS | 验证证据、镜像及 VDB 哈希后复用 |
| 两者交集 3 项 | ELF、测试身份、自检与 trace-audit 契约相同，仅计一次 |
| 最终集合 | 445 项，其中新执行 424 项，复用 21 项 |

三个交集为 `vslide_mask_edges`、`vreduction_lmul_edges` 和
`vreduction_overlap_edges`。不将仅 ELF 相同、检查契约不同的测试自动合并。
最新 21 项保留原随机/定向检查、AXPY 周期门槛、1401/1402 异常探针证明及
1409/1410/1412 的派生激励标识；`vlsseg` 使用成功的 1800 秒补跑结果。

## 调度与统计

- 最大 8 个 VCS worker，在宿主机独立目录运行。
- 保留各点已有的 300/600/900/1800 秒预算，不统一缩短或放宽。
- 随机测试仍与 Spike 做标量、向量严格比较；定向测试保留原自检与独立审计。
- 普通功能失败或超时记入结果，不计入 PASS 覆盖率，不自动改 RTL 或反复重试。
- 基础设施错误、输入/镜像漂移等停止调度；systemd 控制组负责清理子进程。
- 收尾时仅汇总检查通过且兼容的 VDB，导出完整层级的原始及 DVE 原生豁免后报告。
- 本轮不跑完整 Linux 内核启动；包含既有 Linux 关键能力定向测试。

输出目录：`verification/out/vcs-current-coverage-20260927-01/`。
服务：`ara-vcs-current-coverage-20260927-01.service`。
计划或启动不代表已经完成，以 `checkpoint.json` 和 DVE 完整报告为准。

## 查看进度

```bash
cd /home/wangwy/openproject/ara_dsa_signoff_integration
./vstatus status current-coverage
./vstatus jobs current-coverage
./vstatus log current-coverage -n 40
```

`checkpoint.json` 给出总数、已完成数、PASS/失败分类与复用数。
最终 `dve/summary.csv` 为原始覆盖率，`dve/summary_waived.csv` 为豁免后覆盖率；
`.partial` 不作为结果，豁免成功需 `waiver_status.json` 为 `APPLIED`。

已完成启动前的脚本回归（102 项通过）及冻结计划核验；后台服务已启动。
启动检查显示 21 项复用 PASS、8 项 RUNNING、416 项 PENDING；这不是最终结果。
本机当前用户无法读取 journal，因此优先使用上述状态命令及输出目录中的
`logs/`、`scheduler/logs/` 查看日志。
