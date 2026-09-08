# 线性投影与 Attention 的下一阶段

## 范围与版本

本阶段只处理 QBS 线性投影与 AKV Attention。llama.cpp/GGML 是主要运行时，
普通 RVV 和未命中快速路径的节点继续正确执行。不扩展到 Norm/RoPE 等新硬件，
不简单增加算术阵列或双倍缓存，不运行综合、时序、面积和功耗流程。

- 固定基线：`4410dce9368751aa474b2223bcde90144cf2bad9`。
- 基线分支：`llm-linear-attention-baseline-20260908`。
- 开发分支：`llm-linear-attention-next`，每个通过的技术节点单独提交。
- 外部 adapter：`/home/wangwy/llama/llama.cpp-d256-admission` 独立工作树。
- 原 llama.cpp 工作树及其未提交修改保留；adapter patch 纳入本仓库，不在
  未经另行确认的情况下提交或推送外部仓库。

## 节点与状态

| 节点 | 工作 | 当前状态 | 进入下一步的条件 |
| --- | --- | --- | --- |
| 基线 | 保存 D256 逐 token 版本及同 simv 数据 | 已保存，7/7 VCS 通过 | 原始日志、ELF 哈希、状态可追溯 |
| D256 接入 | 受控接入 GGML Decode，保持默认回退 | 已实现，定向 GGML 检查通过，模型对照待完成 | 真模型数值、实际选择与旧维度回归通过 |
| QBS | 当前版本下选择一项收益最大的线性投影优化 | 尚未修改 | 真实输入、当前计数语义、逐周期证据一致 |
| AKV 递送 | 评估跨 Query 分组的 K/V 复用和连续行列递送 | 尚未修改 | 先量化可消除的等待，不把重叠计数简单相加 |
| 收尾 | 共用源码接入、代表回归、数据与设计文档更新 | 待后续节点 | 不降低既有格式/形状支持和 RVV 正确性 |

## D256 如何验证

D256 普通 Decode 的最新真实输入 VCS 结果已归档：Gemma KV140 为 164,622 周期，
普通 RVV 为 419,549 周期，同一 simv、同一输入、零 mismatch。2.549 倍仅是
这个算子的比较，不是完整模型速度；不使用已超差的旧 tiled-RVV 作为分母。

接入增加 `GGML_RISCV_AKV_D256=1`，默认仍关闭。限制和软件暂存容量详见
`akv_d256_efficiency.md` 第 6 节。本次没有改变 RTL 或原生计算内核。

定向 GGML 检查覆盖 16 个 D256 组合和回退/边界检查，并保留 18 个 portable
组合、并发图和 D96/D128 检查。模型队列按顺序执行：

1. Gemma-3-1B Q4_K_M，短 prompt，D256 开启。
2. 同一模型和 prompt，D256 关闭，核查原始 fallback。
3. Qwen2.5-1.5B Q4_K_M，D128，开启新开关但保持原路径。
4. Gemma 较长 prompt，开启 D256；实际 KV 长度从日志读取。

每个模型点生成 3 个 token，并执行 RVV、QBS-only、QBS+AKV 三种配置，核查
输出 token、logit 决策稳定性和覆盖守恒，不调整原容差。AKV 在这些 QEMU 模型
运行中是 GGML 功能参考，不能把模型端命中数称为原生硬件周期证据。
较长输入会自然生成新的 K/V，未把短输入数组拼接成假长上下文。

```bash
python3 verification/akv/run_d256_admission.py \
  --llama-src /home/wangwy/llama/llama.cpp-d256-admission \
  --llama-binary /tmp/akv-d256-ggml-20260908/bin/llama-simple \
  --output hardware/akv_d256_efficiency_runs/model_admission_20260908
```

长任务在独立 tmux 会话中运行，单点上限 3 小时；失败则停止后续队列并保留
失败记录。只确认启动后的进展，不连续轮询。每次必须使用新的输出目录，
实验不修改原有 `*_latest` 链接。

## 后续 RTL 修改的筛选原则

QBS 先在当前版本的真实线性投影输入上区分权重供给、激活量化及 context
交接、输出块之间的重启、短块 FP 收尾。优先解决可重复测到的最大损失，不将
早期报告中的瓶颈直接认定为当前瓶颈。每次只选择一项结构变化，保留既有九种
profile、尾块和软件 K 分段协议；优化成功后同步到共用 GGML 内核。

AKV 先区分外部 FULL/REFILL 与片上 row/column replay。检查每个 word 的读出、
结果接收与最终提交握手，不能为了连续递送跳过真实完成条件。已有四 Query
共享与 panel4 要保留，再依据周期信号判断去掉递送空拍是否值得增加控制。

任何 RTL 修改之前都先提出可以被测量否定的根因假设，确定所需计数和信号。
先跑一个有区分力的中等规模点，再跑格式/形状/RVV 代表回归，不用大量盲试
替代根因分析，也不在模型准入尚未完成时同时修改两套执行机制。
