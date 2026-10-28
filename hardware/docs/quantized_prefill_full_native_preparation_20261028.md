# Prefill 完整调用路径的 RTL 测量准备

## 目的和当前状态

跨 query 共享 V 解码能减少重复工作，但仅测内部调度不能证明运行时调用更快。
本次准备完整入口的 ABBA 测试，将准入检查、query 量化、QK、online softmax、
V 解码、PV、输出写回和完成等待全部计入周期。尚未运行这个完整入口 ELF，
因此本记录不提供它的加速比，也不宣称已完成 GGML 集成。

当前后台运行的是较早的内部调度测试，不能用它代替本次完整调用测试。
截至本次检查，该测试第一轮 baseline 输出为 203366 cycles、4 次命令、
74 次 V 解码、FCSR=1、VCSR=5、errors=0；第二轮已经开始。
这只是程序的单轮输出，完整 ABBA、独立输出检查和协议检查尚未完成。

## 固定输入与公平比较

- 输入来自已封存的真实 Qwen3 Prefill capture，不使用随机替代数据。
- 取一个 KV head，query 16--19，每个 query 两个 GQA head，D=128。
- K 为 Q4_0，V 为 Q8_0，共输出 8×128 个 FP32 数值。
- Baseline 逐 query 调用现有 `akv_quant_native_execute`，每次均执行准入检查。
- Candidate 一次调用 `quant_prefill_execute`，全量准入后跨 query 分组执行。
- 两者都使用同一 QBS 硬件、输入、数学回调及编译选项，不以 RVV baseline 命名。
- 四轮顺序为 baseline/candidate/candidate/baseline；每轮均初始化向量状态、
  FCSR、VCSR，并在开始与结束读取周期之前排空向量工作。
- 预计每轮均为 4 次 QBS 命令；V 解码次数分别为 74/20/20/74。
  这是待检查的活动条件，不是已经测得的完整调用性能。

输出布局含行尾 padding 和首尾 guard。每轮检查真实 capture golden，容差为
`2e-5 + 2e-5 * abs(golden)`，同时要求 ABBA 输出逐位一致、FCSR 一致、
VCSR 保持 5。输入验证与散写成本位于计时范围内；打印和结果核对位于范围外。

## 构建证据

目录：`verification/out/prefill-full-q4-build-20261028-01/`。

- `build.json` 状态为 `BUILT_NOT_EXECUTED`，`whole_call=true`。
- 全部 15 个目标文件重新编译，复用目标文件数为 0。
- ELF：`prefill-full.elf`。
- ELF SHA256：`e72984a55cb019cdd19e5af867022cf495547b522eafa379f361afd8d09ced55`。
- 构建清单及继承输入合计核对 259 个文件哈希，无不一致。
- 反汇编包含真实 native QBS 执行及 baseline 入口，不包含 `qbs_ref_execute`。

新增文件位于 `verification/akv/quantized_kv/prefill/`：

| 文件 | 用途 |
|---|---|
| `native_full_main.c` | 完整入口和逐 query baseline 的同 ELF 测试 |
| `build_full_native.py` | 核对已有 recipe 后重新编译全部对象，封存输入 |
| `check_full_native.py` | 强制完整调用范围标记，再执行独立数值和活动检查 |
| `test_check_full_native.py` | 拒绝缺失、重复、错序标记和错误结果 |

完整入口检查器及原数值检查器共 5 个 unittest 方法通过，包含多个反例。
这些是检查器测试，不是 RTL 测试。完整入口检查器尚未接入正式执行 worker；
启动完整入口仿真前应使用继任 worker 调用它，并保留现有协议与身份检查。
不能修改当前运行中 worker 的已封存脚本。

## 下一步验收

先完成正在运行的内部调度实验，核对正确性和实际收益，再决定是否启动完整
入口实验。后者通过数值、活动、协议和性能检查后，才推进 GGML 的受控接入。
标准 RVV fallback 不变；当前没有修改 RTL 或启用新的生产默认路径。
