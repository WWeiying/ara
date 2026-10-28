# Prefill 完整入口 VCS 验收

## 结果与范围

`verification/out/prefill-full-q4-vcs-20261028-01/result.json` 为 PASS。
完整入口已计入准入检查、query 量化、QK、online softmax、V 解码、PV、
输出暂存/散写和 drain；打印及结果核对不在计时区间。

两侧均使用同一 QBS 硬件。Baseline 对每个 query 调用现有 Decode 入口，
candidate 对整个小批调用 Prefill 入口。输入来自真实 Qwen3 capture：
KV head 0、query 16--19、每 query 两个 GQA head、D=128，K=Q4_0，
V=Q8_0。它是完整函数调用的测量，不是整模型或普通 RVV 的对比。

| 轮次 | 路径 | 周期 | QBS 命令 | V 解码 |
|---|---|---:|---:|---:|
| A1 | 逐 query | 300611 | 4 | 74 |
| B1 | 跨 query | 206762 | 4 | 20 |
| B2 | 跨 query | 206860 | 4 | 20 |
| A2 | 逐 query | 301146 | 4 | 74 |

ABBA 平均：**300878.5 → 206811 cycles，1.4548476628×**，
周期减少 **31.2643%**。完整调用成本使加速比低于内部调度实验的 1.775×，
但没有抵消跨 query 复用收益。不能把两次不同 ELF 的周期差直接解释为
精确的单函数开销分解，后者需要同一入口内的阶段计数。

## 正确性与协议证据

- 四轮各 1024 个输出，独立检查确认逐位一致；最大 golden 绝对误差为
  `3.5762786865234375e-7`，使用原固定容差，不放宽验收。
- 四轮 FCSR 均为 1，VCSR 均为 5，程序 errors 均为 0。
- 输出 padding/guard 检查通过；完整调用范围标记由专用 checker 验证。
- 独立协议检查 PASS、issues 为空：5473 个请求/响应，4662 个向量分配/完成，
  3020 个 AXI 读事务、1128 个匹配 B 响应的写事务，最终均无 pending。
- 运行前后源码、输入、镜像身份核验通过。

ELF SHA256：`e72984a55cb019cdd19e5af867022cf495547b522eafa379f361afd8d09ced55`。
执行服务：`prefill-full-q4-vcs-20261028-02.service`，已正常退出。
该服务由前一实验通过后自动衔接，不是同时启动的未验收试跑。

## 接下来的落地边界

下一步将原型计算入口整理为可供 C++ GGML 调用的 C 接口，复用已经测试的
metadata map、backend extent 检查和完整准入逻辑。生产默认不直接开启，
先完成真实 graph 的受控调用及模型功能验证。至少还需覆盖另一种 K 格式、
不同 query/head/前缀形状，并验证拒绝输入不写输出、执行失败不重走 fallback。
普通 RVV、已有 Decode 和未支持的 mask/线程路径必须保留。

本轮没有修改 RTL，也不据此宣称完成了整个软硬件优化目标。
