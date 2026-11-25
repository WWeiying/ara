# Resident 概率数据通路候选

## 为什么继续改，以及不改什么

目标是让 Resident 的 QK/PV 计算收益保留下来，而不是让调用框架把收益耗尽。
按完整链路区分，当前有三层成本：

| 层次 | 处理方法 | 当前状态 |
|---|---|---|
| Linux 的逐次 ioctl、复制和内核状态借用 | 用户态直达，权限建立移到循环外 | 门控 RTL、测试内核和程序已准备；尚待新位流验收 |
| SDK 的重复校验、控制字构造、函数栈操作 | 同一调用只做一次公共计划校验，预计算控制字，使用无栈叶函数 | 继承单次准入候选；不重新扩大缓存 |
| 每个 tile 的 Softmax 到 PV 数据搬运 | 本轮将概率中间数据改为 FP16 单位步长存取 | 软件数值对照通过，板上收益待测 |

本轮只改第三层，不改 RTL、指令编码、硬件容量、总线或 Linux 内核。
它不能单独解释或消除旧 Linux 路径数毫秒的差距。前两层与第三层要区分验收，
不能把几次不同环境的耗时下降直接相加。

## 数据怎样走

原准备路径：

```text
QK -> FP32 score -> Softmax / 原 F64 归约
   -> FP32 probability 写回 -> PV 再读 FP32 -> 转 FP16 -> 配对打包 -> Resident PV
```

候选路径：

```text
QK -> FP32 score -> 同一 Softmax / 同一 F64 归约
   -> 转 FP16 并写回 -> PV 直接读 FP16 -> 同一配对打包 -> Resident PV
```

转换只是提前，不是删除；求和仍使用未舍入的 FP32 概率，不能改成对 FP16 概率求和。
已有 accumulator 的 F16 缩放、配对格式、最终 EW16 布局维护、PV 的 FMA 顺序和
输出归一化均保留。全掩码分支明确写入 FP16 零。输入异常标志保持 sticky，不清零。
转换产生的异常标志出现时间提前，因此要求中间没有观察或清除 `fflags` 的操作；
当前 SDK 在这段区间没有这种操作。等价性针对完整准备阶段，不声称逐指令时间相同。

工作区用 union 叠加两种 scratch 格式，仍是原内存：

- `score[head][64]`：QK 输出及 Softmax 输入，FP32。
- `resident_probability[head][128]`：仅前 `T` 项有效，FP16；每行仍占 256 字节。
- 每个 head 的 FP32 行被完整消费后才写回其 FP16 前缀；下一 tile 的 QK 覆盖它。
- 工作区大小、对齐、成员偏移和行距均与原 ABI 相同，没有新增分配。

采用单位步长 load/store，未使用表面指令更少但可能由硬件拆成逐元素请求的跨步或
段访问，也未删除看起来像空操作、实际上用于 VRF 布局维护的自 OR。

## 可以确定节省什么

对于 `H` 个有效 head、`T` 个 token，概率写回加读回的有效字节数：

| 项目 | 原路径 | 候选 |
|---|---:|---:|
| 概率写回和读回 | `8*H*T` | `4*H*T` |
| H2、T64 | 1,024 B | 512 B |
| H2、总 T137，分成 64/64/9 | 2,192 B | 1,096 B |

这不是总访存流量减半，更不是执行时间减半。QK score、K/V、accumulator、Softmax
和其它调用成本不包含在此。FP16 narrowing 总次数不减少，只从 PV 移到生产端。

历史准备诊断中，T137 的三个 tile 合计约 555--599 个 issue 周期，整个历史对照
约 35,000 周期，且二者计时边界不同。因此这是一项小规模数据通路改善，不应预计
它独自解决 Linux 路径的数倍退化。更大的改善仍依赖直达路径消除逐次内核往返。

## 开关与适用范围

`AKV_RESIDENT_COMPACT_COEFFICIENTS=1` 显式开启，默认是 0。
同时需要 `AKV_EXPERIMENTAL_RESIDENT_ATTENTION=1`，并链接 `pv_compact.S`。

仅在本次调用已经选中 Resident、实际状态准入通过、有效 scores features 为 NULL
时使用紧凑概率路径。原生 fallback 仍接收 FP32；有效 features 路径保持原版准备。
形状范围沿用原 Resident：VLEN1024、D64/96/128、tile T1--64、每个 PV 指令 H1/H2。
多 head 和长 KV 仍由已有分组/分块机制组织，不改变 Linux 端当前的部署准入范围。
不在 FULL 之后重新选择路线，也不在修改工作区后重试 fallback。

## 验证范围

`software/akv/experimental/resident_attention/test_compact.py`：

1. 使用实际 RVV 汇编在验证用 Spike 执行 1,838 组准备对照。覆盖 D64/96/128、
   H1/H2、T1--64、额外舍入模式、NaN/Inf/次正规数、sticky flags，以及三组真实
   Qwen3 捕获的概率、scale、seed。比较有效源寄存器内容、控制字、异常标志及边界。
2. 使用实际生产 C 函数及同一 GNU 工具链，在 QEMU Linux 执行 9,216 次 Softmax
   tile 比较。覆盖 H1--8、T1--64、全掩码/部分掩码、极小概率与三个连续 tile。
   比较概率位模式、maximum/sum/old_scale、fflags，以及 native 分支完整工作区。
3. 比较工作区 ABI。重新运行既有 host/UBSan/GNU 检查，关闭 Resident 的核心对象
   与固定基线逐字节一致。

准备测试把 custom issue 位置替换为源寄存器捕获，因此不执行或模拟 custom PV
计算。QEMU/Spike 结果不代表 RTL 时序、完整 Attention 输出或新位流已通过。
完整调用仍由交付配对程序检查真实硬件结果、flags、保护区、输入不变与路径次数。

证据位于 `ara_dsa_signoff_integration/verification/out/`：

| 目录 | 内容 |
|---|---|
| `resident_compact_20261113_04` | 与部署优化参数一致的 Spike/QEMU 数值对照及冻结源码 |
| `resident_executor_compact_20261113_03` | 原生默认/OFF 对象一致性及既有准入/编排检查 |
| `resident_direct_build_compact_20261113_01` | 固定 SDK 基线加 11 个登记文件的完整静态配对 ELF |

早期 `_01` 使用了额外 `-frounding-math`；`_02` 对齐部署编译参数。最终 `_03`
还统一了数值对照两侧的 C 类型，将旧工作区 ABI 单独检测，并补全执行前镜像哈希、
独立异常标志和未使用工作区边界检查。`_04` 再将重复登记哈希改为一致性断言，
避免后续登记覆盖早期身份；以 `_04` 为最终证据，不覆盖早期记录。
构建未混入工作区未提交的 `akv_v2_attention_rvv.S`。

## 如何交接

```sh
python3 -B verification/performance/resident_deployment/direct_cost/build_compact.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_direct_build_compact_MANUAL
```

本次候选程序在同一 ELF 中比较 native AKV 与 compact Resident。沿用 T65/128/137
真实输入、完整 SDK 调用计时和原分析器，只调整被计数 PV 叶函数的名称/指针类型。
当前 ELF SHA256：`d2c0c0d135eac857a95b149584f608e389939c2f167a2753221908a62955865a`。

完整测试包：`resident_direct_delivery_compact_20261113_02`，包含同一 v4 测试内核、
权限测试、性能程序及已登记 SDK 覆盖文件。先按 [BOARD_HANDOFF.md](BOARD_HANDOFF.md)
验收权限/生命周期，再运行配对程序。需要前一轮引入的权限门控位流；本轮无需额外
RTL 改动。不要把旧 broker 位流与直达程序混用。

为区分两类改进，可先运行旧 `resident_direct_delivery_preflight_20261113_01`，
再运行本候选，交错顺序并检查每个包的哈希。两包的 native 对照也必须分别保留，
不把不同 ELF 布局、缓存状态和采样波动误当作紧凑格式的收益。

## 整体判断与下一步

当前最重要的是验收已经准备好的用户态直达链路；继续削减几条指令不能替代它。
本轮到此冻结候选，不扩大 SRAM，不冒险删除完成同步或 OS 隔离。
若完整调用验证有收益，再将编译开关和源文件接入正式 llama.cpp 构建。
完整模型还需要安排长寿命权限、预触页和工作区生命周期；独立配对程序的准备不能
直接推广为任意模型无开销接入。若候选没有稳定收益，保留关闭状态及旧路径即可。
