# 量化 Prefill 优化：当前验收汇总

## 优化及集成状态

在已有 QBS 量化 QK 和 RVV online softmax/PV 的基础上，将共享一个 KV
head 的多个 query/head 行分组。同一 V token 解码后供多行使用；QK 仍按
各行真实可见前缀发命令，不能计算被 mask 掩蔽的元素。对 strided K，使用
有界 tile panel 汇集多个请求共同可见的范围，不改变原始量化格式。

本阶段没有新增 RTL。优化已接到本地 llama.cpp 的受控 graph dispatch，
构建和运行时开关默认关闭；现有 Decode、标准 RVV 和拒绝路径保留。
本仓库保存本次增量补丁，外部 llama.cpp 的无关未提交修改没有被回退。

## 完整入口 RTL 性能

同一真实 Qwen3 capture 的 KV head 0、query 16--19，每 query 两个 GQA
head，D=128，V=Q8_0。ABBA 两侧均使用 QBS，不是普通 RVV 对比。
计时包含完整准入、量化、计算、输出 staging/scatter 和 drain；不包含
新增 GGML frontend 的 heap 分配和模型 graph 调度。

| K 格式 | baseline 平均周期 | 优化平均周期 | 加速比 | 状态 |
|---|---:|---:|---:|---|
| Q4_0 | 300878.5 | 206811 | 1.454848x | PASS |
| Q8_0 | 302402.5 | 206870.5 | 1.461796x | PASS |

Q8_0 四轮周期为 302183、206951、206790、302622。每轮均为 4 条 QBS
命令，V 解码为 74/20/20/74。四轮各 1024 个输出逐位一致，最大 golden
绝对误差 2.477318048477173e-7；FCSR=1、VCSR=5，程序 errors=0。
独立协议检查及输入/镜像前后核验通过。

Q8_0 结果：`verification/out/prefill-full-q8-vcs-20261028-01/result.json`。
ELF SHA256：`6ddb529dc4f9ca7440e2bf59cfc39934e05766f3b16fe6dde5c1cff29e2e795a`。
Q4_0 对应记录见 `quantized_prefill_full_call_vcs_result_20261028.md`。
两项服务均正常结束，不需要继续等待。

## 软件功能证据

| 层级 | 场景 | 已证明的内容 |
|---|---|---|
| Host | 真实 capture、Q4_0/Q8_0、完整 C 入口 | 与旧逐 query 入口逐位一致 |
| 标准构建 | 正常 CMake OFF/ON | 两套完整 llama 库构建成功，无对象覆盖 |
| QEMU graph | 两种 K 格式，开关与带孔 mask | 16 次实际 graph 调用通过；命中/拒绝活动核对 |
| QEMU 模型 | Qwen2.5-1.5B，4-token prompt | 911616 logits、token、CSR 逐位一致 |
| QEMU 模型 | Qwen3-1.7B，40-token prompt | 911616 logits、token、CSR 逐位一致，跨 tile |

每项模型对照覆盖两种 KV 配置，一次 Prefill 与两步 Decode；开启侧各完成
56 次 Prefill，ON/OFF 各 112 次 Decode 的逐项活动一致。QEMU 数据均为
功能证据，不用于换算加速比。两个模型通过也不意味着所有模型/上下文支持。

## 仍需推进

最有价值的下一项 RTL 测量是实际 token-major KV 布局的完整调用配对，
因为上述小批 RTL 点的 K 连续，尚不能量化 panel gather 对收益的影响。
应保持真实逻辑数据、可见范围和数值契约不变，分别记录 panel 次数/字节、
命令、V 解码和完整调用周期，先核对现有 Decode strided baseline。
随后才根据实测归因决定是否需要硬件改动，不能从连续布局的结果直接
断言 strided 布局收益或端到端模型速度，也不直接默认启用新路径。
