# Resident 预计算控制字板测候选

## 这次继续消除的开销

沿用原生 AKV 的 Query 转换、KV 装载、Softmax、累加和归一化。本轮不修改 RTL、内核或硬件指令格式。

1. QK 直接接收已验证计划中的控制字，取消每个 tile/head pair 重新编码和判断维度的工作。
2. PV 直接接收同一计划中的控制字，复用此前的无栈准备段，不再重新编码一次。
3. 尾块从已验证的完整块计划派生，仅更新 token 计数和块位置，取消重复构造、验证相同描述符。首次准入和全部动态状态检查仍保留。
4. 继续保留上一轮的能力缓存及跳过无用原生策略。完整 SDK 调用中仍无设备 ioctl 和 K/V 内核复制。

这些变化已进入 `software/akv/src/akv_v2_native_riscv.c` 及其 QK/PV 汇编入口，适用于使用该 SDK Resident API 的调用者，不是只在测试脚本中省掉工作。能力查询缓存属于新板测程序，真实 llama.cpp 已有同类设备缓存；完整模型的直通租约接入尚未完成。

## 已完成的检查

- 1,572,840 组尾块计划与原完整检查器对照通过，覆盖 D=64/96/128、query rows=1..8、KV length=1..65535。它证明计划/控制字一致，不代表硬件支持这么大的全部调用，也不是这么多次 RTL 仿真。
- 384 种 PV 形状控制/存储范围检查通过；实际链接后的 PV 入口跳转目标正确。
- PV 浮点/向量准备段 148 字节保持一致；QK 从自定义指令到结果写回的机器码保持一致。
- SDK 主机桩测试、UBSan、开关/回退编译检查通过。Resident 关闭时整个 GNU 对象与本轮最初基线逐字节相同。
- 新静态 RV64 ELF 编译和 32 项分析器测试通过，未进行板测或自定义指令的数值执行。

证据均在 `ara_dsa_signoff_integration/verification/out/`：

```text
resident_executor_prepared_20261113_02/
resident_prepared_low_overhead_20261113_03/
resident_direct_build_prepared_20261113_02/
```

一次前置检查因测试脚本在运行期间变动而被身份检查拒绝，保留在 `resident_executor_prepared_20261113_01/`，没有重标为通过；上面的 `_02` 是冻结输入后的完整重跑。

## 板测包与身份

优先使用新的包，不覆盖前两轮：

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/
resident_direct_delivery_prepared_20261113_01.tar.gz
```

性能 ELF SHA256：

```text
62209f2c6ade6a2db82a84258ada3d44b4a124d7b52b794a000648ad7c393660
```

SDK 身份为 `4a7361f51ba5447a616217dad1c8e72e3ee2b45b` 加 `sdk-overlay/manifest.json` 登记的六项增量，不能只报基线提交。仍使用原权限门控 RTL 和 v4 内核，内核 SHA256：

```text
d52d67d62a6d97c61684ede19f406dd72e805c8b606538c916190cab2aea50d1
```

如果板卡尚未部署该门控和测试内核，先按 [BOARD_HANDOFF.md](BOARD_HANDOFF.md) 完成部署；本次软件变化本身不需要新的硬件功能。

板上只需上传新包的 `board/`，沿用其中 `run_environment.sh`，使用新的输出目录。先通过 11 项安全测试，再测 T=65/128/137 的完整 SDK 配对；使用包内对应的分析器，不能混用旧 ELF 或旧分析器。

## 仍不能宣称什么

未测量板上净收益，不能说已经达到原生 AKV 加 Resident 理论收益，更不能说全部额外开销归零。系数转换/打包、必要的动态准入和 Linux 状态保护仍存在；当前指令接口需要这些准备，不能在不改变接口的情况下简单删掉。

新包计时包含 Query 转换、计划校验、Softmax、QK/PV、KV 装载及完成等待。固定输入预检查和租约初始化仍在循环外并有记录，没有新增把 PV 准备排除在计时外的处理。
