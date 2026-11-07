# 混合精度缩放计算路径验收与取舍

## 1. 当前结论

独立 FP16×FP32 缩放乘法器已接入隔离的 QBS accumulator/compute 构建副本，
通过原版、候选关闭、候选开启三镜像的数值与协议对照。它没有接入生产
`Bender.yml` 或当前 SoC，不改变普通 RVV、ISA、SDK 或正在运行的其他镜像。

**不将单独增加缩放通路作为已选定的性能方案。**原有 66 项合计组件服务时间
只降低约 0.63%；真实四行切片只得到约 1.009×。这与静态分析一致：当前整数
点积服务率未变，分离 scale MUL 只能减少部分排队和尾部等待。功能通过不等于
新增资源具有端到端收益。

## 2. 实际修改了什么

构建脚本核验原 accumulator/compute 的 SHA，再生成命名独立、修改可逆的副本。
`MixedScaleIssue` 默认关闭。适用的 scale MUL 使用此前验证的三拍、II=1 通路，
其余操作保留原 FPU；原 FP16×FP16 helper 的准入优先级也不变。

- 新增独立 entry 选择和四位返回 tag；同一 entry 不允许多个端口同时发射。
- 最后一次 scale 返回后，用其自身 tag 选择旧累积值，保持 activation scale
  的生命周期，不使用同时返回的另一端口 tag。
- cast、原算术端口和 mixed 返回的 flags 在单一赋值中合并。FMA 舍入与每个
  accumulator 的 K-block 操作顺序不变。
- `busy` 包含新增流水。故障时先排空已接受的工作，再清理并恢复接收。

资源账目除 24×11 有效数乘法器外，还包括流水寄存器、选择逻辑和额外的旧
累积值读取选择；没有综合结果，不能只按乘法位宽宣称面积收益。

## 3. 验证输入与检查

沿用原有 66 项完整 native payload、C oracle 输出和 flags，追加 10 项有限值
边界测试。完整 76 项受精确 SHA 及追加关系双重绑定，旧 golden 没有替换。
测试覆盖九种 profile、多种 M/N/K、布局、部分 tile 和 K-block 连续累积。

新增边界覆盖正负零、FP16 次正规权重、FP32 次正规激活和结果上溢/下溢。
两个 NX-only 场景保持所有输出为 +0，要求完整 flags 恰为 NX；分别使用
Q6_K、Q4_K，以避免最终 FMA 的 NX 掩盖缩放乘法漏报。未改变 NaN 编码或屏蔽 flags。

| 已完成的验收 | 结果 |
| --- | --- |
| 每份镜像普通测试 | 76 项，结果与独立 C oracle 逐位相同 |
| 每份镜像原有故障与恢复 | 5 次故障及 5 次恢复通过 |
| 原版与关闭候选的完整比较 | 81 次执行的周期、操作数序列、工作量和 flags 相同 |
| 新通路完成数，含上述 5 次恢复 | 4721，与发射数相同 |
| 新通路 NX | 731 次 |
| 新通路与其他 FP 端口同时返回 | 3644 次，其中同时 NX 为 196 次 |
| 非准入 MUL 回落原 FPU / 原 HalfScale 发射 | 662 / 1745 次 |
| NX-only 两项 | 各 64 次 mixed 发射、返回和 NX；输出全零，flags=NX |
| 额外故障注入 | mixed issue 边界及返回边界各一次 |
| 额外故障排空 / 恢复 | 19 / 16 周期排空；恢复的 10 个输出和完整 FP 序列通过 |

额外故障第一项发生在 issue 边界，当时 pipeline busy 尚未置位；第二项在返回
边界，且同周期有新 issue。不能把这两项扩称为任意中间拍、SoC reset 或 MMU
故障覆盖。独立缩放部件另有 reset/clear 测试，范围见此前部件记录。

## 4. 实际周期与性能判断

计时区间从 compute 接受命令后，到结果 valid 的观察点，包含确定性 testbench
输入传输，不含 reader/MMU、SDK、GGML 调用或完整模型执行。

| 输入范围 | 原版＝关闭候选 | 开启候选 | 原版/候选 |
| --- | ---: | ---: | ---: |
| 原 66 项合计 | 32586 | 32382 | 1.00630× |
| 真实 M1/N8/K1536 切片 | 767 | 767 | 1.00000× |
| 真实 M4/N8/K1536 切片 | 1378 | 1366 | 1.00878× |

两项真实输入来自已接受的 Qwen2.5 Prefill 捕获；M1 是其中一行，不是新的
Decode 捕获。原 66 项中有 6 项开启后增加 1--2 周期，未宣称所有点均不退化。
不使用这组不按实际模型频率加权的合计比值推算 tokens/s。

下一项主要候选应平衡点积、subgroup correction、scale 和 FMA，而不是继续
微调这条独立 scale 流水。例如满 M4、四 weight rows、256-element block
包含 16 个输出流：当前 dot 至少 64 个发射周期；即使 scale 独立，dot 下限仍在。
若使每流每拍从 4 提高到 8 元素，dot 下限才变为 32 周期，但必须同步满足：

1. Q4_K/Q5_K 每块 128 次 correction，至少每拍 4 次；16-element subgroup 的
   Q6_K/Q3_K/Q2_K 每块 256 次，至少每拍 8 次。
2. Q4_K/Q5_K 的 I2F、scale、FMA 各 32 次，分别具备独立单发射能力；原 FPU
   fallback、entry 生命周期和实际排队会使理想下限增大。
3. 每个 tile 的纯权重流量分别为 Q4_K 576B、Q5_K 704B、Q6_K 840B。
   32 周期目标分别要求 18、22、26.25B/cycle；16B 入口不够，32B 入口也还要
   扣除仲裁、空泡与共享流量。不能把内部入口带宽当作实际 DDR 带宽。

这仍是下一方案的服务率约束，不是其性能承诺。优先核查实际 Prefill/FFN
调用收益、Decode 不退化及普通 RVV/fallback；最终仍按完整推理收益取舍，
不以部件测试替代目标，也不排除 Attention 等更主要的瓶颈。

## 5. 可复核证据

唯一验证输出：
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_mixed_compute_20261106_01/`。

- `result.json` SHA256：`0ffc162016b4c7b0fed96546d3589f78aaf7b2e5d7dcbe063ef254c478c93758`。
- `source-pins.json` SHA256：`8f0b44427c7396da9df1f3195436091ca9fe96a0f0927b624ec65d78a3f31c42`。
- 独立审查重核 118 个 pins、16 个 artifacts、三份镜像，并重放普通/故障检查，
  与发布的 `measured.json`、`fault-measured.json` 精确一致。
- 23 项 host 单元测试通过，包含对篡改计数、flags、操作数、缺失场景和诊断错误
  的负向测试。

未运行综合、功耗、FPGA 或新的模型性能实验，未提升为生产默认路径。
