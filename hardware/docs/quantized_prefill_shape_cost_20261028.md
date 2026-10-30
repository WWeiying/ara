# Prefill 分组的形状成本核查

`verification/out/prefill-workload-scan-20261028-01/result.json` 为 PASS。
直接执行当前 C prefix scheduler 和原 C online scheduler，用回调统计命令、
V 解码、panel 及 QK row-token 数，GCC 与 Clang UBSan 的 160 行结果完全一致。
算术输入是合成常量，未测周期；不替代真实模型或 RTL 性能证据。

扫描 query=2/4/8/16/40、GQA=1..8、past=0/16/31/64，均为规则 causal
前缀。两侧 QK row-token 数符合独立公式 `GQA * sum(past+query_index+1)`，
说明未以减少有效计算来制造工作量节省。

## 发现的边界

query=4、past=16，每个 KV head 的计数如下：

| GQA | baseline/new QK 命令 | baseline/new V 解码 | baseline/new panel |
|---:|---|---|---|
| 1 | 4 / 4 | 74 / 20 | 4 / 1 |
| 2 | 4 / 4 | 74 / 20 | 4 / 1 |
| 3 | 8 / 8 | 74 / 39 | 4 / 2 |
| 5 | 8 / 9 | 74 / 58 | 4 / 3 |
| 6 | 8 / 8 | 74 / 57 | 4 / 3 |
| 7 | 12 / 12 | 74 / 77 | 4 / 4 |
| 8 | 8 / 8 | 74 / 74 | 4 / 4 |

160 点中 9 点出现命令数增加，21 点没有减少 V 解码；后一个数不含解码
反而增加的点。GQA=8 占满行缓冲，天然没有跨 query 共享空间。
GQA=7 的固定八行切分跨越 query 边界，使同一个 query 的不同 head 分散到
不同组，引起多次 union-prefix 解码。GQA=5 还可能把一组 M4/M1 分解成
更多小命令。问题是分组成本，而非功能错误，也不是已经实测的周期退化。

## 下一步方案约束

研究在不超过 8 行的前提下选择可变组边界，保留每行的可见前缀和计算顺序。
先以实际 callback 工作量验证选择策略，再决定有限的真实输入 RTL 测量。
不能简单强制整 query 分组：GQA=6 时那样会丢掉当前已有的复用。
候选策略需要同时考虑 union V/K 行数、QK 命令分解和组数，不能只优化一项。
在 host 和真实输入验证前，不修改已通过的生产入口、RTL 或默认开关。
