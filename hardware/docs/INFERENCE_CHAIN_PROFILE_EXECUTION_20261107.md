# 当前面积基线的性能测量计划

## 目标和边界

在面积优化保留版本上，取得 QBS/AKV 完整调用的可信周期画像，识别供给、
准备、命令前后边界和 Attention 各阶段的主要限制。不扩计算阵列、队列
或 SRAM，不改架构语义、准入规则、数值检查，不做综合或 FPGA 重建。

先前的只读分析见 `INFERENCE_CHAIN_PROFILE_20261107.md`。其中的历史
周期不自动成为本次测量值；只有新镜像和相应测试通过后才填写当前周期。

## 固定环境

- 唯一验证输出位于 `ara_dsa_signoff_integration/verification/out/`，不创建
  开发 worktree。本轮代码放在 `verification/performance/chain_profile/`。
- RTL、提交版 SDK 与汇编从主线确定提交导出，不使用工作区未提交的 AKV
  汇编；其他未提交内容保持原样。
- 依赖来自已验收面积测试的冻结 source inventory，复制前逐文件核对哈希，
  不读取原依赖目录的未登记修改。
- 固定 4 Lane、VLEN1024、128-bit AXI、QBS/AKV-v2 开启、共享整数乘法器
  开启、共享 FMA 按当前默认关闭。仿真 RAM 为 16 MiB，仅扩大容量，不改
  存储延迟或接口宽度；这不是 SRAM 面积测量。
- 使用宿主机 VCS V-2023.12-SP1、普通 CVA6 前端和被动 UVM 检查器。
  不使用 Verilator、URG、ZCC，不通过 QEMU 时间解释硬件性能。

## 两个必测点

| 点 | 数据与规模 | 需要回答的问题 |
|---|---|---|
| QBS Decode V 投影 | 真实 Qwen3 单 token position40；Q6_K，M1/K2048/N64，两条 N32 命令 | 权重供给是否限速；activation 驻留及命令边界的成本 |
| F16 AKV Decode | 真实 Qwen3，D128/GQA2，137 有效 tokens | FULL、两次 REFILL、QK、Softmax、PV、release/output 的调用周期分布 |

QBS 使用完整 K 和原始 Decode activation，不从 M4 Prefill 抽一行后声称
是 Decode。N 裁剪必须遵循 R4 block-major 布局，并检查完整参考结果。
量化准备、planner/admission 与 execute 分别计时，保留完整调用总计时。

AKV tile 是 64 tokens，137 覆盖 64+64+9。保留原始有效长度，避免沿用
原输出参考却改变 softmax 范围。未插桩与阶段插桩两路使用同样输入，检查
完整输出及 CSR，记录插桩对完整调用的影响，不假设观察免费。

## 观测方法

1. 保留现有完整调用的最终 drain；不在阶段间新增 fence/drain，不插入
   打印或改变计算顺序。
2. 现有 QBS/AKV PERF 记录提供命令活动；strict WAIT_WEIGHT 的四分项
   用于区分无 outstanding、等待响应、传输数据和接收反压。
3. 被动 boundary monitor 记录命令 fire/terminal，并保存第一次执行命令
   呈现后 1000 周期的窗口，观测 Ara/VLSU idle、tile start/done 和读通道。
   窗口不是全调用轨迹，不能据此前缀推算全部占比。
4. COMMIT_TRACE/VECTOR_TRACE 和被动 UVM 用于命令/完成/写回与协议一致性。
   PC 前退休间隔只作定位，不作为独占执行时间。
5. 阶段 rdcycle 值表示 CPU 到达阶段边界的时间；异步工作由原调度语义和
   最终完成边界约束，不额外声称每个中间边界都已排空。

## 检查与执行

- 每个构建输出包含源清单、数据及工具哈希、实际命令、ELF 与完整配置。
- 执行前后核对 source/image pins；先检查普通 RVV 冒烟，再运行两条
  诊断测试。失败保留首个证据，不修改 checker 使失败变通过。
- 数值、CSR、guards、原始输入完整性和独立 UVM 都通过后，性能才被接受。
- 长任务由 systemd 用户服务直接持有 worker；worker 等待实际 VCS 子进程。
  记录状态、日志和子 PID，不使用短 launcher 遗留孤立进程。
- 两个测试独立运行，资源允许时并行；每项 VCS 上限三小时。确认执行后
  不持续轮询，阶段完成后读取结果。

## 完成条件

| 要求 | 验收证据 |
|---|---|
| 基线身份明确 | 冻结源码、配置、依赖清单以及 actual build command |
| 激励真实且范围清晰 | capture receipt、数据哈希、layout/shape、完整参考检查 |
| 当前硬件通过 | 新镜像下数值/CSR/guard/work 与独立 UVM PASS |
| 性能可解释 | 完整调用和各阶段周期、命令活动、必要的周期窗口相互对账 |
| 观察开销被识别 | AKV 未插桩/插桩完整调用对照与数值等价 |
| 不误报端到端收益 | 明确只是算子切片；不把不同切片加速比相乘或冒充整模型 |
| 工作可复现 | 版本化脚本和测试，原始日志、输入/image 身份及最终报告 |

本轮最终产物应给出瓶颈排序、明确的源码根因证据及低面积候选的下一步
区分测试。未取得测量的项保持未完成，不以已有历史分析替代。
