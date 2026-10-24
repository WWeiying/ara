# AKV 通用 Decode：两头共享 K/V 的原理与结果

## 解决什么问题

同一 KV head 对应多个 Query heads 时，这些 heads 使用相同的 K/V，但各自
计算不同的 score 和输出。已有 D128/GQA6 特化会共享一次读取；原 generic
Decode 则按 head 外循环，多次回放相同的 K 列和 V 行。

本次没有增加 RTL、算术单元、SRAM 或指令编码。实验内核使用已有四列命令
和普通 RVV 算术，让一次递送同时供两个真实 heads 使用。不是把两个 Query
位置合并，也没有改变每个输出内部的累加顺序。

## 数据如何流动

QK 的两个 FP32/m2 累加组分别占 v0:v1、v2:v3，K 的四列占 v8--v11，互不
覆盖。每个 dimension 依次更新 head0 和 head1，再前进到下一 dimension。
PANEL4 一次提供四个相邻 dimension，但不会将它们合并为新的求和树。

PV 保留原有 F16 累加：先分别将两个 old scale 转成 F16 并缩放各自的部分和，
再按原 token 顺序转换 score、读取一次 V 行并更新两个累加组。不改成 F32 PV，
不融合初始缩放，也不生成不存在的第二个 head。

score 行距仍为 256 B，accumulator 行距为 512 B；D64/D96 的未使用部分不能
被当成下一行。当前实验叶函数只接受两个实际 heads；未来奇数尾头须在原
generic 中独立执行。D128/GQA6 特化不被该实验替换。

## 定向数值与协议验收

真实 KV128 捕获数据派生的三个组合为 D64/VL1、D96/VL63、D128/VL64，包含
两个 KV heads 和 256/320 B Query 行距。共六次实际 VCS 执行全部通过：

- QK 对照独立的 host scalar FMA，按 dimension 顺序核对原始 FP32 结果。
- PV 与原 generic 汇编逐位、逐状态比较；它是回归参考，不是独立 FP16 模型。
- 检查 inactive tail、行间空隙、输入不变、guards、RNE、sticky fflags 和 VCSR。
- 1044 条实际命令与流量逐项核对；原有独立 UVM backend/AXI-write 检查通过。

本次有限实数、RNE 检查不代表所有 NaN、舍入模式或操作系统抢占已经验收。
收据为 `verification/akv/results/paired-heads-rtl-20261024.json`。

## 完整 Attention 的同 ELF 对照

数据取自真实 Qwen2.5 KV128 Decode 捕获，仅选择 Query heads 0、1、6、7，
形成两个 KV heads、每组两个 Query heads 的派生区域。D128、有效 KV128，
每次输出 512 个 FP32 值。它不是新的 Qwen3 模型捕获。

计时包含 Query F32→F16 转换、计划创建、实际能力检查、QK、softmax、PV、
归一化和输出完成；输出比较、校验和与打印在计时区间之外。开启路径额外的
能力查询成本没有从周期中扣除。两路径使用相同的 ELF、输入和缓冲区地址。

| 次序 | 路径 | 完整 Attention 周期 |
| --- | --- | ---: |
| 0 | 原 generic AKV | 81266 |
| 1 | 两头共享 | 58357 |
| 2 | 两头共享 | 58411 |
| 3 | 原 generic AKV | 80512 |

两次原路径合计 161778 周期，两头共享为 116768 周期：加速 1.385465 倍，
周期减少 27.822077%。四次输出逐位一致，checksum 为 `d96c7d6498f9bf20`，
FCSR=3、VCSR=5，原 golden 容差和 guards 检查均通过。独立协议检查及执行
前后 source/image/artifact 哈希检查也已完成。

| 每次完整调用 | 原 generic | 两头共享 |
| --- | ---: | ---: |
| QK 列命令 | 1024 | 128 |
| 其中 PANEL4 | 0 | 128 |
| PV 行命令 | 512 | 256 |
| FULL / REFILL / RELEASE | 2 / 2 / 2 | 2 / 2 / 2 |
| 全部 AKV 命令 | 1542 | 390 |
| 片上 replay 字节 | 262144 | 131072 |
| 外部 read payload 字节 | 132224 | 132224 |

减少的是重复递送与命令组织，不是减少有效乘加，也不是增加计算阵列。
外部 K/V 数据量不变，不能把片上 replay 的下降称为 DDR 流量下降。
完整收据为 `verification/akv/results/paired-heads-attention-20261024.json`。

## 为什么周期下降：实际 trace 的核对

离线分析先重验完整测试结果、UVM 和所有输入哈希，再用实际 ELF 的两个
`rdcycle` 地址定位八条 CSR 退休记录。四个窗口中，结束值减开始值都与应用
打印的周期完全相同。统计只计架构退休，不把 reshuffle 等内部微操作算成
额外指令，也不把第一次展示请求当作握手成功。

| 两次完整调用的合计周期 | 原 generic | 两头共享 |
| --- | ---: | ---: |
| 完整计时区间 | 161778 | 116768 |
| KCOL 命令 busy | 45056 | 15108 |
| PV 命令 busy | 25601 | 12800 |
| 全部 AKV 命令 busy | 87578 | 44825 |
| 完整周期减全部命令 busy | 74200 | 71943 |

最后一行不是 CPU-only 周期或独占 stall：标量/向量工作可以与命令重叠，
该余项也包含同步和发令间隙。不能把它再与猜测的 FPU 时间相加。

| 每次完整调用的实际退休指令数 | 原 generic | 两头共享 |
| --- | ---: | ---: |
| 全部架构指令，不含两个计时 CSR | 21275 | 15977 |
| 标量指令，含标量浮点 | 17712 | 13574 |
| 标准 RVV，含配置指令 | 2017 | 2001 |
| AKV custom，含 INFO | 1546 | 402 |
| QK 内核中的 `vfwmacc.vf` | 1024 | 1024 |
| PV 内核中的 `vfmacc.vf` | 512 | 512 |

两个重复调用各自给出相同的指令数。custom 类别不能直接称作工作命令数：
原路径为 1542 条工作命令加 4 次 INFO；两头共享为 390 条工作命令加 12 次
INFO。额外的能力查询已计入实际指令与周期，没有从开启路径扣除。

这些证据支持“少做重复回放、少发命令、减少地址/循环控制”，而不是“少算
乘加”或“新增算术吞吐”。指令数也不能直接解释成 FPU 实际计算利用率。
复现入口为 `verification/akv/paired_heads/analyze_attention.py`，父进程独立复核
结果在 `verification/out/akv-paired-heads-attention-analysis-parent-20261024-01/`。

## 当前部署边界

本结果证明相对原 generic AKV 的机制收益，不证明相对普通 RVV 的收益，也不
代表整模型加速。正式 runtime 和 GGML selector 尚未接入；当前实现仍位于
`software/akv/experimental/paired_heads/`，其测试入口不是线程安全的生产 API。

下一项准入是相同输入下的普通 RVV / generic AKV / 两头共享三方比较：每个
实现均须满足原 golden 容差，generic 与两头共享还须逐位一致。通过后再用
无共享全局可变状态的正式选择逻辑接入，保留不支持形状的 fallback。奇数头、
更多实际模型及 Prefill/F32 路径不能由当前两头 F16 Decode 结果直接推断。
