# 完整 llama.cpp 的 Direct-U / Resident 接入

本文说明 2026-11-14 的完整模型候选，不替代旧交付标签的验收记录。
旧 [BOARD_HANDOFF.md](BOARD_HANDOFF.md) 与 [LOW_OVERHEAD.md](LOW_OVERHEAD.md)
中的程序是 SDK 配对测试；本次增加的是实际 `llama-simple` 和 GGML 后端接入。

## 软件调用关系

```text
llama-simple -> GGML FLASH_ATTN_EXT
  -> RISC-V akv.cpp
     -> 准备用户缓冲区、预触碰、锁页、获取一次 Direct-U 租约
     -> 原生 AKV 或满足条件的 Resident QK/PV
     -> 完成并释放租约
```

实际租约覆盖一个完整 Attention 节点，不是每个 head、KV tile 或硬件命令。
逻辑上的分组检查不再触发重复 ioctl，也不把 K/V 复制到内核。
工作区在租约外分配并复用；日志实际输出、页表检查和可能分配内存的初始化
在租约外进行。SDK 使用本轮 compact FP16 probability 实现。

这不等于零开销。每个 Attention 的租约获取/释放、地址资格检查、Q 转换、
数值准入以及正常调度仍有成本。是否比原生 AKV 快，需要同一位流板测。

## 保留的路径

| 输入或环境 | 行为 |
|---|---|
| 符合现有条件的量化线性投影 | 原 QBS 后端，未替换算法 |
| F16 Decode，Resident 形状及真实 INFO4 能力均合格 | Resident QK/PV |
| F16 Decode 不适用 Resident，但符合原生 AKV | 同一次租约内执行原生 AKV |
| 符合已有条件的 F16 Prefill | 同一次租约内执行原生 AKV Prefill |
| Q4_0/Q8_0 KV | 原量化 KV 路径，在 AKV 租约外运行，仍检查内存条件 |
| 无设备、准入不足或不支持的算子形状 | 普通 RVV 回退 |
| 已开始计算后执行失败、状态破坏或释放失败 | 停止并保存失败，不静默重算 |

Resident 的硬件能力需同时满足有效 INFO4、版本 1、QK/PV 均支持、4 Lane、
VLEN1024；不能只因编译开关打开就认定硬件支持。形状、特征和数值条件仍由
原有 SDK 与后端检查，不把 Resident 扩展为任意上下文长度的路径。

## 源码与身份

- llama.cpp 仓库：`/home/wangwy/llama/llama.cpp`，分支 `qbs-activation-context`。
  基础提交 `a2b7f30da9aadf88b0a068c447383ed2e26ee867` 加本次审核过的覆盖文件。
- Ara/SDK 仓库：`/home/wangwy/openproject/ara_dsa`，分支 `ara_dsa`。
  基础提交 `4a7361f51ba5447a616217dad1c8e72e3ee2b45b` 加白名单 SDK/client 覆盖文件。
- 核心接入文件：`akv.cpp`、`resident.inc`、`linux-direct.cpp/.h`、CPU CMake
  及 `examples/simple/simple.cpp`。simple 新增显式 FlashAttention/KV 类型参数。
- 打包入口：`verification/performance/resident_deployment/direct_model/build.py`。
  冻结完整源码、工具链、编译参数、运行脚本及每个覆盖文件的哈希。
- 不纳入未交付的 `software/akv/src/akv_v2_attention_rvv.S` 修改。

候选不是一个旧标签即可重建的版本；以包内 `source-pins.json`、
`pins/candidate-contract.json`、ELF 哈希及构建日志共同确定身份。
禁止从两个当前脏工作区直接任意混合构建后沿用本候选的验收结果。

已构建的候选包：

```text
/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/
  resident_direct_model_20261114_03/board.tar
```

同目录 `board/` 可直接查看内容；`result.json` 记录交叉编译成功及输入哈希未变。
ELF SHA256 为 `1c9b8709e3736cb815361b23af85d1114c029b20d3663bea8da95a0613a0d5c6`，
契约 SHA256 为 `24ca1175ee15322a16157e05b13adbd3f495447e7f248b78dbf595b925858dba`。
十项包文件 SHA256 校验通过。ELF 是实际完整模型程序，不是 Attention fixture。

## 配套硬件与系统

需要 Direct-U v4 内核和包含 `SAKVCTL` 门控的新位流，不可直接用旧位流运行。
本次只改运行时接入和测试/打包，没有新增生产 RTL 或内核修改，也未运行 Vivado。

内核 Image SHA256：

```text
d52d67d62a6d97c61684ede19f406dd72e805c8b606538c916190cab2aea50d1
```

限制为 root、单 hart/单 worker、受控静态 RV64 Linux 程序、普通 RAM、不可变模型
文件映射。新门控覆盖原生 AKV 和 Resident；旧的未接入租约的 AKV 程序不能照用。
先完成原交接中的权限/生命周期测试，再运行整模型。

helper 在映射清单未变时复用 smaps 资格检查，并管理进程锁页。它不能通过
相同 maps 清单证明锁页策略未变。不得绕过 helper 执行 munlock、madvise、
userfault 或其它策略变化；必要的租约外变化先调用 `invalidate()`。
租约内禁止分配/映射变化/打印；缺页、信号等按 v4 的撤销/终止规则处理，
不承诺透明恢复任意多线程或动态加载应用。

运行目录与 ELF 目录使用干净的候选包目录，不放额外 `libggml-*.so`，也不注入
`GGML_BACKEND_PATH`。虽然本候选不构建动态后端，upstream 的
`ggml_backend_load_all()` 仍可搜索外部插件；静态链接本身不等于禁止插件搜索。
交付脚本使用干净环境，但不应将任意外部插件混入已核验的程序身份。

## 测试与运行入口

- helper：主机定向测试、ASan/UBSan、缺少契约时拒绝准入。
- 后端：22 项软件路由测试、163 次 Attention 调用，涵盖 D64/96/128、GQA、
  尾块、Prefill、能力拒绝、无设备、释放失败及量化 KV 路由。检查租约内无
  new/delete，工作区复用，以及不适用 Resident 时不会误发 Resident。
- 主机路由测试使用可核查的替身执行接口，不代表真实硬件算术/板测通过。
- 完整模型回退检查入口：
  `verification/performance/resident_deployment/direct_model_checks/run_fallback.py`。
  同一实际 ELF 在系统 QEMU 中运行小模型，比较 RVV 与设备缺失回退的完整 logits。
  该项不模拟 Direct-U 硬件，不测 Resident 性能。

本轮实测记录位于验证工作树 `verification/out/`：

| 记录目录 | 结果 |
|---|---|
| `resident_direct_model_helper_20261114_01` | helper 主机、ASan/UBSan、契约拒绝测试通过 |
| `resident_direct_routing_host_20261114_02` | 22 项 / 163 次 Attention 软件路由检查通过 |
| `resident_direct_model_20261114_03` | 完整 GNU RV64 静态构建、关键符号及输入身份检查通过 |
| `resident_direct_model_fallback_20261114_02` | 系统 QEMU，SmolLM2-135M-Instruct-Q4_K_M，两侧各生成 4 token，正常退出 |

最后一项两侧 786,528 字节 logits 记录逐字节一致；请求 AKV 的一侧 120 次
因设备不可用拒绝准入，Resident/native 实际调用均为零。完整烟测约 160 秒。
这个时间仅为主机测试运行耗时，不是硬件性能；其意义是实际模型回退路径正确。
早期构建/启动包装器失败的目录保留，未覆盖或重新标记为通过。

交叉编译包提供同一个 ELF 的 `rvv`、`native`、`resident` 模式：

```sh
sh run_board.sh resident /models/model.gguf /results/new-diagnostic 'A fixed prompt' 4
```

运行前按打包目录的 README 设置并核验位流、内核、契约哈希和内存前提；
脚本不会替操作者确认位流身份。先用 `ARA_DIRECT_DIAGNOSTIC=1` 比较短点完整
logits、退出状态及实际 `resident_groups`；通过后用 `=0` 单独测完整耗时。
成功退出不等于 Resident 已使用，`EXECUTED_UNVERIFIED` 也不是自动验收 PASS。

本轮仍待 FPGA 会话完成新门控位流、v4 内核启动、安全测试，以及真实模型的
原生 AKV/Resident 配对测试。不得把主机路由或 QEMU 回退结果表述为板上加速。
