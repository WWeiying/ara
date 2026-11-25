# Resident 单次准入候选

本轮继续减少软件重复工作，不修改 RTL、内核、指令编码、数值算法或硬件容量。
它继承 [PREPARED_HANDOFF.md](PREPARED_HANDOFF.md) 的用户态直达候选，不能用于未部署权限门控的旧位流。

## 本轮改动

此前，普通单段 Decode 的完整 SDK 执行路径先做一次公共计划校验，Resident
选择器再验证同一个计划，命令编排又验证同一个描述符。同一描述符的地址范围、
步长、形状等检查实际执行三遍。现在改为：

```text
公共入口完整校验一次
  -> Resident 权限、能力、选项检查
  -> 从同一份已验证且不可变的计划生成命令
  -> 读取实际 vlenb / frm / vstart
  -> FULL / QK / Softmax / PV / RELEASE / 输出
```

- 普通单段 Resident 调用的描述符验证由三遍减到一遍。
- 删除临时完整 schedule 到最终 schedule 的整份结构赋值。
- 独立调用的 `akv_resident_attention_select()` 和
  `akv_resident_attention_dispatch_plan()` 仍执行完整校验，未变成不安全的公共入口。
- 带 features 的入口保留自己的 feature contract 和计划检查，仅复用已经验证的
  描述符进行映射；不能把普通路径的“三变一”数字套用于所有入口。
- 前一轮的预计算控制字、尾块派生、无栈 PV 准备及能力缓存继续保留。

这些修改位于共享 SDK，而非只在 benchmark 中删掉计时内容。内部辅助函数的
前提是本次调用刚验证了同一份不可变计划；没有跨调用缓存“永远有效”的结论。

## 检查范围

`software/akv/experimental/resident_attention/test_preflight_once.py`
使用上一轮冻结 SDK 和本轮 SDK 做差分：

- 2,537 组形状、输入对象逐位变异、地址溢出边界、特殊浮点 scale、拒绝条件。
- 16,896 组 feature 编排，含 32 种功能组合及 refill-overlap 拒绝对照。
- 比较准入结果、完整/尾块控制字、拒绝时输出不变、公共接口和 no-retry 语义。
- 同一编译器下比较异常标志；GCC 和 Clang/UBSan 各自比较新旧版本，不将
  不同编译器的浮点异常代码生成差异误判为本轮变化。

这些是主机软件验证，不是 19,433 次 RTL 仿真，也不是模型数值验收。
实际 RV64 编译、关闭 Resident 的对象字节一致性和原有映射/叶函数桩测试另行检查。
QK/PV 计算及 Softmax 未改动，板上输出、fflags 和计时仍需配对复测。

初始试跑记录没有删除：`resident_preflight_once_20261113_01` 的合成地址间隔不足，
被计划构造器正确拒绝；`_02` 将 GCC 与 Clang 的异常标志混作同一基准。
后续修正测试地址和配对方式，保留所有异常标志检查，没有放宽准入条件。
旧 `resident_policy_host` 脚本仍假定只有四项 INFO 且没有 index-4 Resident 能力，
与当前 ABI 不符；其失败未记为通过。当前差分使用实际 SDK 和同编译器前后对照。

## 构建与交接

构建入口：

```sh
python3 -B verification/performance/resident_deployment/direct_cost/build_preflight.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_direct_build_preflight_MANUAL
```

仍从固定 `4a7361f51ba5447a616217dad1c8e72e3ee2b45b` 导出 SDK，仅叠加清单中的
八个文件。未提交的 `akv_v2_attention_rvv.S` 不会混入。配对 benchmark、真实
Qwen3 输入、计时边界、检查器和运行脚本均沿用上一轮，未修改输出校验或计算规模。

本轮构建和交付身份见交付目录的 `manifest.json`、`sdk-overlay/manifest.json`
以及性能程序构建的 `result.json`。旧包保持不变。

本次证据目录均位于 `ara_dsa_signoff_integration/verification/out/`：

| 目录 | 内容 |
|---|---|
| `resident_preflight_once_20261113_05` | 19,433 组新旧准入/编排对照，GCC 与 Clang/UBSan 分别通过 |
| `resident_executor_once_20261113_02` | 主机桩、1,572,840 组尾块映射、关闭开关的对象一致性等检查 |
| `resident_leaf_once_20261113_01` | 原浮点准备段 148 字节一致、384 种控制/存储形状检查 |
| `resident_direct_build_preflight_20261113_02` | 最终静态 RV64 ELF、32 项结果分析器测试、冻结构建输入 |

交付目录为 `resident_direct_delivery_preflight_20261113_01`，同名 `.tar.gz`
包含测试内核、安全测试与本轮性能程序。沿用包内 `board/run_environment.sh`，
先通过权限/生命周期测试，再测 T=65/128/137；仍需要另行生成配套权限门控位流。

## 剩余成本

仍保留初次权限建立、动态状态检查、QK 结果落入 score 工作区、Softmax、
PV 系数转换/打包、累加器准备与完成同步。其中有些是原生 AKV 也需要的工作，
有些由现有 Resident 指令接口要求。不能从本轮校验次数减少推导端到端加速比，
也不能宣称“全部零开销”。

当前优先复测完整 SDK 调用，不继续在没有测量依据时修改浮点顺序或引入新的
数据缓存。完整 llama.cpp 的直达权限生命周期接入尚未完成。
