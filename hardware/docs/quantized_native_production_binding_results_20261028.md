# 真实后端回调配置下的 Decode 结果与下一优化点

## 回调一致性

本批 native 程序的 V 解码直接调用当前 llama.cpp 后端所用的共享
`akv_quant_q8_0_value`。query 量化和 scale/MAD 也保持原 GGML 实现。
没有修改 RTL、量化格式、实际计算输入或 hardware capability gate。
它纠正了早先 native benchmark 仍使用标量 V 回调的问题，不能把新旧
不同 ELF 的总周期之差当成新硬件优化收益。

## 对齐优化的同 ELF 配对结果

结果：`verification/out/selector-production-q4-vcs-20261028-01/result.json`，
PASS。基线是冻结的接入前 selector，候选是当前共享 selector；除两处
已证明的对齐信息外，准入和执行路径相同。两者都用实际共享 RVV V 解码。

| 顺序 | Selector | 完整调用 cycles |
|---|---|---:|
| A | 冻结原版 | 58743 |
| B | 当前共享实现 | 47761 |
| B | 当前共享实现 | 47252 |
| A | 冻结原版 | 58693 |
| 均值 | 原版 | 58718 |
| 均值 | 当前 | 47506.5 |

加速 **1.2359992843×**。这是原/新 selector 的配对局部收益，不是模型
整体收益，也不能与此前不同分母的 Prefill 或投影收益相乘。

范围：真实 Qwen3 query19，GQA2、D128，20 可见 token，KQ4_0/VQ8_0，
token-major 物理 8 KV heads 中选 head0；包括准入、query 量化、K panel、
QK、online softmax/PV、输出和 drain。UART、数值检查及图调度不在 ROI。

四轮各 256 输出逐位一致，FCSR 均为 1、VCSR 均为 5，最大绝对 golden
误差 2.9988586903e-7。每轮 1 个命令、1 个完成组、20 次 V 解码、1 个
K panel、1440 字节 K 拷贝。独立协议检查和前后源码/镜像指纹均 PASS。

ELF：`693e5a6cf2b5990529fda88fec69fd116e1a4c81f44eba4c40743327779c2f3f`。
真实模型功能回归仍见
`quantized_kv_selector_promotion_acceptance_20261028.md`；其正常后端本来就
使用 RVV V helper，因此 benchmark 修正不撤销两模型既有功能 PASS。

## 当前实现的退休热点

独立单调用归因：
`verification/out/decode-pc-production-q4-vcs-20261028-01/result.json`，PASS。
该 ELF 完整调用为 48578 cycles，19773 条退休指令；退休跨度与 rdcycle
差相同。它与 ABBA 的 ELF 不同，只用来定位，不与其总周期直接相减。

| Text symbol | gap cycles | 约占退休跨度 |
|---|---:|---:|
| akv_quant_strided_execute_impl（含内联 selector/online） | 16898 | 34.8% |
| prefill_native_decode（共享 RVV helper） | 7727 | 15.9% |
| __ieee754_expf + expf wrapper | 6978 | 14.4% |
| quant_kv_ggml_mad_f32 | 5127 | 10.6% |
| strided_value（上下文和地址处理） | 2689 | 5.5% |
| quantize_row_q8_0 | 1944 | 4.0% |

QBS busy 702 cycles，不与函数 gap 相加。它只说明这个短调用中命令本体
不是主要时间跨度，不能外推到更大投影、更长上下文或不同 GQA。

在这个固定 ELF 中，按反汇编进一步定位三个内联扫描区域：

| 区域 | PC 范围（左闭右开） | gap cycles | 退休指令 |
|---|---|---:|---:|
| mask 扫描 | 80002c08–80002c38，加 80002de2–80002de8 | 3161 | 2353 |
| query 有限值/量化范围扫描 | 80002d5c–80002de2 | 4067 | 3146 |
| KV scale 有限值扫描 | 80002de8–80002e66 | 3664 | 1757 |

各区间经当前反汇编检查；地址只对本 ELF 有意义，不用于其他版本。
gap 指前一个退休到当前 PC 退休的间隔。这里不是互斥因果 stall 分解；
向量背压和更早的依赖也可能延迟某个 PC 的退休。

## 已准备但未接入的 query 判定候选

`selector_block_max.h` 在独立函数中只改变同一个 32 元素 query block
内部的非有限值判定位置。清除 sign 后，F32 位模式为非负 unsigned：
任何 NaN/Inf 的绝对值位模式都大于等于 `0x7f800000`。因此，先求块内
最大绝对值，再判断该最大值是否越过此边界，与逐元素检查等价。

原来的代码已经逐元素求最大值以检查 Q8_0 quantizer 的输入范围。
候选复用这个结果，删除每个元素额外的 exponent mask/判定，改成每块
一次非有限值检查，然后仍执行原范围检查。不使用浮点运算或近似。

拒绝优先级保持按 block：同块中出现超范围有限值和 NaN 仍先返回
NONFINITE；前一个 block 已超范围则不为后一个 block 的 NaN 改判。
与原版不同，块内遇到 NaN 后会把这个 block 剩余元素读完；输入已由
完整 view 验证且契约要求整块可读、normal memory，不引入越界读取，
不改变 hidden KV 跳过规则、输出写入或 FP flags。

`test_selector_block_max` 的 GCC 与 Clang UBSan 各 2819 项均 PASS，覆盖
F32 原始位模式边界、所有 32 个 block 内位置、零、正负 Inf、qNaN/sNaN、
量化范围边界和 block 间拒绝优先级。另有完整函数
差分检查，限制变动只在上述判定处。

这只是已测热点上的独立软件候选，尚未进行真实 RTL 周期对照，不安装到
共享路径，也不宣称性能提升。下一次对照应只切换本候选，保留当前共享
RVV V 回调；不能同时改 mask 扫描、指数函数或硬件而混淆收益归因。
