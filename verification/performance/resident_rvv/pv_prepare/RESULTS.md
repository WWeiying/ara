# 实际 Qwen3 调用中的 PV 准备成本

`resident_pv_prepare_vcs_20261109_01`：**PASS**。宿主机 VCS 复用未修改的冻结 SoC
镜像，仿真耗时 1,476.70 秒；独立协议检查和执行后的 source pins 检查通过。
这次没有新硬件，不能把测得的完整调用差值作为 resident 执行的性能收益或退化。

## 准备 helper 的两个实测区间

真实 Qwen3 D128/H2/T137 调用拆为 T64、T64、T9，连续两个 candidate 调用：

| 捕获 | T | helper issue 区间 | 加诊断存出/排空区间 | 准备产生的 flags | 前/后 FCSR |
| --- | ---: | ---: | ---: | ---: | --- |
| 0 | 64 | 257 | 391 | NX | 3 / 3 |
| 1 | 64 | 196 | 282 | NX | 3 / 3 |
| 2 | 9 | 146 | 280 | UF、NX | 3 / 3 |
| 3 | 64 | 225 | 311 | NX | 3 / 3 |
| 4 | 64 | 184 | 318 | NX | 3 / 3 |
| 5 | 9 | 146 | 232 | UF、NX | 3 / 3 |
| 第一次调用合计 | 137 | 599 | 953 | | |
| 第二次调用合计 | 137 | 555 | 861 | | |

issue 区间包含时间戳保存和 helper call/return、完整 seed 初始化、有效 FP 运算和
最后的 EW16 normalization 请求；CPU 返回不等于所有向量执行已完成。
第二个区间还包含计时记账、VL 配置、额外 768 B 结果捕获存出和 fence。
输入快照会预热输入。两者都不是未来 custom 指令的精确开销或严格上下界。

## 数值与执行身份

- 第一组三份原始捕获，使用独立 Spike SoftFloat 检查 FP32→FP16 概率/scale 转换、
  seed 乘法、源组中 active 数据及 coefficient interleave。第二组三份在 target 中
  对概率、scale、seed 和 active prepared source 逐位比较，不是另外三份独立 oracle 输入。
- 三块准备结果分别有 384、384、274 个定义明确的 F16 元素；其余 source padding 不作为数值输入。
  最后一次 short tile 的 v13 即使保留不同历史布局，也必须在最终 EW16 读入前完成正常维护。
- 原完整调用的 output、CSR、输入和 guard 检查未移除；四次均 errors=0，FCSR=3、VCSR=0、vstart=0。
- 所有 948 个既有 AKV 命令通过原硬件工作检查。独立 vector trace 核对 932 个 replay/column
  指令的顺序及签名，其中 272 个是 v10 轮换行；两个 arm 均真正执行较强的轮换软件控制。
- source pins 1,644 项和运行报告中的 9 项 artifacts 已由父级重新计算哈希，无差异。
- 11 项 helper host checks、5 项 driver/checker host checks通过；GNU numeric/no-aliases
  反汇编确认 leaf 的全部 38 条静态指令。384 个 host 几何枚举不等于这些形状已在 RTL 运行。

实际数值范围仍是 D128/H2、RNE、上述三块真实有限数输入。FCSR 之前已有 UF/NX，
因此 sticky union 相等不能独立证明每个既有异常位都正确再次产生，也不覆盖所有 NaN/舍入模式。
后续新指令验收必须补独立的 CSR/异常/形状定向点。

## 不把冗余诊断 arm 当作优化结果

| 完整调用 arm | trial 0 | trial 1 | trial 2 | trial 3 |
| --- | ---: | ---: | ---: | ---: |
| 较强轮换 RVV / 轮换 RVV 加准备及捕获 | 35,134 | 42,464 | 42,671 | 34,777 |

两个均值为 34,955.5 与 42,567.5。后者**先准备和捕获，再重复执行原 PV helper**，
并未用新指令代替原计算；多出的 7,612 周期不能解释为“新方案慢 21.8%”。
它也不能直接从新方案总时间里扣掉。完整硬件对照必须移除诊断捕获，并在同一程序布局下
比较真实新指令与较强轮换控制；旧实验的 34,213.5 周期也不能替代这个配对对照。

准备成本尚未否定收益假设，因此继续最小 SoC 接入；目前仍不宣称完整调用获益。
真实软件准备后的寄存器布局已验证，不需要凭已知理想 FMA 吞吐猜测布局或绕过维护。

## 证据

验证工作树 `verification/out/`：
- 构建：`resident_pv_prepare_build_20261109_02/`。
- 运行：`resident_pv_prepare_vcs_20261109_01/`，含 result/status、命令、日志、独立协议报告和 pins。
- ELF SHA256：`620c74f6dfcde173888a0e9bd99794a8fe128733e5ceddf0f20527e205ac882e`。
- SoC 镜像 SHA256：`3ed8bc6b761d49664162b9f3b45e525e5c051923618950cbdb2b38ea403486a6`。
- result.json SHA256：`31be648df0fc3eb080cb26849900936923514f47764af214120eb367bdadd0e9`。

早期 `resident_pv_prepare_build_20261109_01/` 未执行，build receipt 的旧 arm 标签/对象清单
已在后继脚本修正；不得把它当作本次通过版本。
