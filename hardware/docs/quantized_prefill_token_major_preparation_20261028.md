# Token-major 完整入口测量准备

新驱动 `verification/akv/quantized_kv/prefill/native_strided_main.c` 仅通过
交叉编译，尚未链接或运行。不能用连续布局数据段直接运行该驱动。

## 公平基线与预期活动

两侧使用相同完整物理 token-major KV 数组：8 KV heads、256 token、D=128，
本小点仅选择 KV head 0，实际处理 query 16--19 的两个 GQA head。
K token stride 为 row_bytes×8，head stride 为 row_bytes；V token stride
为 136×8，head stride 为 136。比较旧 `akv_quant_strided_execute` 逐 query
调用和完整 Prefill 调用，而非错误地用只支持连续 K 的旧入口。

由静态路径可预期 baseline 四个可见前缀为 17/18/19/20，分别搬运 panel；
candidate 搬运并集前缀 20 一次。因此 panel 应为 4→1，K 拷贝行数为
74→20，V 解码也为 74→20；两侧 QBS 命令均为 4。这些不是实测结果。
新驱动在计时外输出 panel/byte 活动，但把实际 panel 搬运计入 ROI。
全部活动、数值、CSR 和输出 guard 继续由程序检查。

## 数据转换检查

`token_major.py` 仅做 `[head][token][block bytes]` 到
`[token][head][block bytes]` 的字节置换，不反量化、不重建 scale 或量化值。
3 个测试方法通过，含非法形状拒绝和两种 K 格式/对应 V 的全部物理坐标
核对，每份 8×256 行；原 capture 内容保持不变。

下一步需使用封存的 capture 生成独立 token-major 数据段，重新编译全部
对象，并链接 `runtime_strided.c`。验收器须额外检查布局标记及四轮 panel/
byte 数，不能仅复用忽略这些字段的原 checker。链接完成和输入身份封存后，
再进行有界 VCS ABBA 和协议检查。本次未修改生产路径或 RTL。
