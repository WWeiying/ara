# Native benchmark 与当前 llama.cpp 回调的一致性复核

## 发现与证据

`verification/out/decode-pc-profile-q4-vcs-20261028-01/result.json` 已 PASS。
本次完整调用 73073 cycles、37513 条退休指令；rdcycle 差与退休跨度相等。
数值、活动、协议以及运行前后输入指纹检查均通过。

| 退休 PC 所属函数 | gap cycles | 占退休跨度 |
|---|---:|---:|
| dequantize_row_q8_0 | 32145 | 约 44.0% |
| akv_quant_strided_execute_impl（含内联 selector/online 调度） | 16821 | 约 23.0% |
| quant_kv_ggml_mad_f32 | 5142 | 约 7.0% |
| __ieee754_expf | 5133 | 约 7.0% |
| expf wrapper | 2183 | 约 3.0% |

gap 是前一次退休到当前 PC 退休的间隔，不是函数的互斥因果 stall。
QBS busy 为 706 cycles；该计数与上述函数 gap 不能相加。

热点 `0x80002360/2368/236c/2370` 实际执行逐元素的 signed-byte load、
整数转 F32、标量乘和 F32 store，各执行 2560 次，正好对应 20×128 个
V 元素。它不是 RVV 解码 helper 内的向量循环。

静态接线复核发现：

- Prefill 目录下的 native 驱动绑定通用 `dequantize_row_q8_0`，来自
  `ggml/src/ggml-quants.c`；该 ELF 中是标量循环。
- 当前真实后端 `arch/riscv/quant-kv.cpp::decode_value` 已绑定
  `software/akv/experimental/quantized_kv/q8_0_value.h` 中的
  `akv_quant_q8_0_value`，使用标准 RVV 解码。
- 正常 CMake 图和模型测试实际使用后者；主机数值参考使用通用解码是
  合理的，但不能把这个主机参考的接线直接作为真实后端的性能接线。

因此，本次暴露的是 standalone 性能评测的回调差异，不是刚发现一个
真实后端仍未向量化的 V 解码缺陷。不能再重复实现已有的 RVV 解码来
宣称新增收益，也不能按标量版本热点决定硬件扩容。

## 已做更正

所有七个 Prefill native 驱动统一引用 `native_main.c` 中的
`prefill_native_decode`，它直接调用同一共享 RVV helper。query 量化和
scale/MAD 保持原 GGML 实现，不改算法或输入。

构建检查拒绝仍带 `dequantize_row_q8_0` 的链接结果；新增静态回调测试
同时核对真实后端和所有 native 驱动都使用共享 helper。历史 ELF、日志
和结果不覆盖、不重新标记；相关文档加入接线说明。

原 selector 的历史 1.15408×配对，以及 Prefill 历史配对，仍是其标量
V 回调下的真实结果；不是当前生产回调配置下的收益。此前图/模型功能
PASS 仍成立，也没有把 QEMU 时间用作 RTL 性能。

## 补测设计

1. 当前实际共享实现退休 PC 定位：
   `verification/out/decode-pc-production-q4-build-20261028-01/` →
   `verification/out/decode-pc-production-q4-vcs-20261028-01/`。
   与后端使用相同 RVV V helper，保留完整周期边界和原协议检查。
2. 原/新 selector 的同 ELF ABBA：
   `verification/out/selector-production-q4-build-20261028-02/` →
   `verification/out/selector-production-q4-vcs-20261028-01/`。
   基线是冻结的旧 selector，候选是当前共享 selector；两路用同一个
   canonical runtime 和相同 RVV V helper。命令、布局、量化、PV 均不变。
3. 冻结基线 runtime 的真实数据主机对照：
   `verification/out/selector-frozen-baseline-replay-20261028-01/result.json`，
   Q4_0/Q8_0、连续/带间隔四组均 PASS，各 40960 输出，逐位/浮点标志一致。
   它是功能检查，不提供硬件性能。

第一版 production pair 构建因旧实验 workspace 符号仍被预检查引用而链接
失败，未启动仿真。已将其改为冻结基线的 workspace 导出，第二版新目录
完整重建成功；失败目录保留，不能算作 RTL 失败或通过记录。

实际性能与热点以这两个新输出目录的最终 `result.json` 为准。只在它们
完成后再作下一项优化，不沿用标量 V 版本占比作为当前后端瓶颈。
