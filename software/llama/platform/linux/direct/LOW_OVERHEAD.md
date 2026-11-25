# Resident 低开销 SDK 候选

## 目标与实际修改

保持原生 AKV 的 Query 转换、KV 装载、在线 Softmax、累加及输出归一化，只替换 QK/PV 执行。不能靠关闭检查、改变累加顺序或把准备成本移出计时来证明收益。

本轮没有新增 RTL、CSR、驱动或内核修改，沿用上一轮直通环境的权限门控和 v4 测试内核。

| 修改 | 实现位置 | 消除的工作 |
|---|---|---|
| Resident 固定路由后跳过原生策略 | `software/akv/src/akv_v2_native_riscv.c` | 不再查询原生环境变量、计算不会执行的 paired/panel4 选择 |
| 无栈 PV 入口 | `software/akv/experimental/resident_attention/pv_fast.inc` | 每次 PV 去掉 4 次栈写、4 次栈读、2 次 SP 调整及内部调用/返回；增加 1 条寄存器搬运 |
| 每租约缓存设备能力 | `direct_cost/low_overhead/bench.cpp` | 每个计时调用从 5 条 INFO 降到 0；两侧相同，与真实 llama.cpp 已有的设备缓存一致 |

SDK 的 Resident 调度默认调用新 PV 入口；旧入口保留供对照。新准备段与旧准备段的 148 字节机器码完全相同，控制字仅提前在整数临时寄存器中构造，没有修改浮点运算或异常标志处理。准备段保持来自原版的内容；测试会拒绝任何未同步的字节差异，避免两个入口以后悄悄分叉。

原生 AKV 的 Resident 关闭编译对象与本轮修改前 `4a7361f5` 的对象逐字节相同。没有将工作区未提交的 `akv_v2_attention_rvv.S` 混入交付。

## 测试和证据

证据位于 `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`：

| 目录 | 结果范围 |
|---|---|
| `resident_low_overhead_20261113_03` | 384 种形状的控制/写回范围检查；真实汇编准备段字节一致；不模拟自定义算术 |
| `resident_pv_legacy_regression_20261113_02` | 原 PV 入口 18 项测试通过，384 种形状；原准备源文件及机器码未变 |
| `resident_executor_low_overhead_20261113_04` | 196 个映射、976 次桩叶调用、UBSan、GNU 开关/回退编译及关闭对象一致性检查 |
| `resident_direct_build_low_overhead_20261113_02` | 新 ELF 静态编译、32 项结果分析器测试及客户端指令审计；未执行板测 |

旧回归脚本中“Resident 能力字必须为零”的断言已按当前 ABI 更新：真正支持时检查精确能力字，关闭时仍要求零。旧时代基线对象也已更新为本轮输入提交；没有将历史失败记录改成通过。

## 板测交付

使用新的独立包，而不是上一轮未修改 SDK 的包：

```text
verification/out/resident_direct_delivery_low_overhead_20261113_01.tar.gz
```

新性能 ELF SHA256：

```text
06a98c969270ecaef7de355383ad176f8511cbd502ca5ac9c3e6f39c17e0fad1
```

包内 `sdk-overlay/` 固定四项 SDK 增量，基线仍为 `4a7361f51ba5447a616217dad1c8e72e3ee2b45b`。这不是“基线提交原封不动”的程序，不能只报基线标签而不附增量清单。内核 Image、权限门控 RTL 和安全测试 ELF 与上一轮一致，不需要为本轮软件改动再改变硬件；但如果板卡仍是没有门控的旧位流，仍必须先完成 [BOARD_HANDOFF.md](BOARD_HANDOFF.md) 中的新硬件/内核部署。

沿用包内 `board/run_environment.sh`：先 11 项安全测试，再测三组完整 SDK 调用。使用包内新版分析器；它要求热路径 `info_calls=0`，不会接受旧版要求 5 次查询的日志。

## 仍需区分的范围

- 数值算术和实际耗时尚待新 ELF 的板测。机器码/桩测试不等同于板测验收，不能据此报加速比。
- 完整 llama.cpp 尚未接入本轮直通租约与工作线程缓存。本轮交付的是 SDK 配对测试，不是新的完整模型程序。
- PV 系数转换、交织打包和 Resident 准入仍有成本；没有为了“零开销”删除尾部维护、越界检查、动态 `frm/vstart` 检查或同步。
- 设备能力在一次独占租约内稳定，因而可以缓存；KV 长度、指针、mask 或数值发生变化时的检查不能据此跳过。
- 已封存的 `resident_direct_delivery_20261113_01` 保持原样，供追溯和对照；新候选不覆盖原报告或原 ELF。
