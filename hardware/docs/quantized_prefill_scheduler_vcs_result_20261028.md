# 真实 Qwen3 Prefill 跨 query 共享的 VCS 结果

## 已通过的实验

结果目录：`verification/out/prefill-native-q4-vcs-20261028-02/`。
`result.json` 为 PASS，独立协议检查通过，运行前后输入身份一致。
本实验不修改 RTL；两侧均使用 QBS，比较逐 query GQA 执行与跨 query
共享 V 解码，不是与普通 RVV 的比较，也不是整模型加速比。

真实 Qwen3 capture 中取 KV head 0、query 16--19，每个 query 两个 GQA
head，D=128。K 为 Q4_0、V 为 Q8_0。计时包含 query 量化、QK、online
softmax、V 解码、PV 及 drain；不包含完整运行时准入与输出散写。

| 次序 | 路径 | cycles | QBS 命令 | V 解码 | 程序 errors |
|---|---|---:|---:|---:|---:|
| A1 | 逐 query | 203366 | 4 | 74 | 0 |
| B1 | 跨 query | 114553 | 4 | 20 | 0 |
| B2 | 跨 query | 114184 | 4 | 20 | 0 |
| A2 | 逐 query | 202638 | 4 | 74 | 0 |

平均周期：203002 → 114368.5，**1.7749817476×**，周期减少 **43.6614%**。
两侧 QK 命令数不变；相邻 query 具有重叠的可见 KV 前缀，调度器使一个
V token 解码后用于多行 PV，V 解码由 74 次降为 20 次。该工作量变化与
周期下降一致，但不能据此将全部节省周期归因于单独某个函数。

每轮 1024 个 FP32 输出均经独立检查，四轮逐位一致；相对真实 capture
golden 的最大绝对误差为 `3.5762786865234375e-7`。FCSR 四轮均为 1，
VCSR 保持 5；输出 padding 和 guard 的程序检查通过。

协议检查记录 `work/uvm_result.json`：无 issues；5473 个请求和响应匹配，
4668 个向量后端分配和完成匹配，2992 个 AXI 读事务完成、1084 个写事务
匹配 B 响应，最终均无 pending。以上为本次测试范围，不代表全设计覆盖。

ELF SHA256：`49d517bdaeb9c10c6e1803b9b7f7e8e24be325704c2af8a18b52abec9e8e5092`。
VCS 主镜像 SHA256：`71bb0f7a22208cf9eb02a40298f8b96404eef6724050a86ab685a92958edb565`。

## 下一道验收

完整入口实验已由条件任务自动启动：
`verification/out/prefill-full-q4-vcs-20261028-01/`。
它补计准入、输出 staging/scatter 等成本。开始执行时确认实际 simv PID
为 3603000；该 PID 仅作启动记录，后续应以 service/status 和实际进程核验。
当前实验结果未出，不把内部调度的 1.775× 当作完整入口的收益。

只有完整入口通过并确认收益后，才启用 GGML 的受控接入并进行真实模型
运行；现有 Decode、普通 RVV fallback 和生产默认开关保持不变。
