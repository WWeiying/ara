# 当前 Decode 完整调用的退休 PC 定位

> 评测接线复核（2026-10-28）：本文既有 native 周期数据使用通用标量
> `dequantize_row_q8_0` 作为 V 回调；当前 llama.cpp 后端使用共享 RVV
> `akv_quant_q8_0_value`。这些历史配对数据在其配置下仍有效，但不能当成
> 当前后端回调配置下的周期或瓶颈占比。真实 GGML/模型功能回归不受此
> benchmark 差异影响。更正及补测见 `quantized_native_binding_audit_20261028.md`。


## 为什么继续定位

已接受的旧/新 selector ABBA 实验中，候选完整调用约 71651 cycles，
单条 QBS 命令的 busy 时间为 703 cycles。这个差距说明只缩短 QBS 命令
未必能显著改善该短 Decode 调用，但不能据此把全部剩余周期称为纯软件
开销，也不能外推到更大投影或更长上下文。

本实验首先区分：准入所在函数、query 量化、K panel 拷贝、QBS 提交、
V 解码、向量 scale/MAD、指数等库函数分别出现在多少退休间隔中，再对
热点 PC 回看反汇编。尚未根据这个假设修改 RTL 或计算内核。

## 方法

`native_decode_profile.c` 只调用一次当前共享
`akv_quant_strided_execute`。输入仍为真实 Qwen3 query19，GQA2、D128、
20 可见 token、token-major KQ4_0/VQ8_0，物理 8 KV heads 中选择 head0。
起止的 rdcycle 分别有唯一 ELF 标签，保留结束 drain。

不在每次回调插入计时器，不增加中间 drain，也不替换算术 callback。
启用 canonical VCS 镜像已有的 COMMIT_TRACE，采集每次实际退休的 PC、
instruction、cycle、order 和寄存器写回值。没有重编 RTL 镜像。
按 ELF 的 text symbol 地址区间给 ROI 内 PC 归属函数，并列出热点 PC。

原始 trace 包括起止之外的初始化和输出，分析器只选择两个唯一标签之间
的一次完整调用。UART、测试检查和输出打印不进入 ROI。

## 精确解释数据

- `architectural_cycles`：两个 rdcycle 返回值之差，与程序打印周期核对。
- `retirement_span_cycles`：起止指令在 monitor 中实际退休的周期差。
  两者可能存在边界流水延迟差，单独记录，不能默认为完全一样。
- `gap_cycles`：上一个退休到本条退休的间隔，归给本条 PC。
  所有函数的 gap 总和必须严格等于退休时间跨度。
- `instructions`：实际退休指令数；多端口同周期退休可以产生零 gap。
- `max_gap`：该 PC 或函数观察到的最大单次退休间隔。

这是一种热点定位法，不是互斥的真实 stall 分类。PC 前的长间隔可能来自
依赖、缓存、向量背压或更早的请求，不能仅根据所属函数断言根因；编译器
内联也会使多个逻辑阶段落在同一个 text symbol 内。需要结合热点指令、
源代码以及现有 QBS 周期计数判断下一步探针。

独立检查完整 256 个输出及 capture golden、FCSR/VCSR、guard 和活动
计数，并执行原有协议检查。解析器拒绝丢失/重复 ROI、乱序、异常、未归属
PC 和 rdcycle 返回值不一致；另有合成正例与故意破坏数据的测试。

## 证据入口

- 构建：`verification/out/decode-pc-profile-q4-build-20261028-01/`。
- ELF：`7b5be4b8a6b79c003aad5b364e0de94bb1ead9b42bcab6825df054605a8148b9`。
- 起点：`0x800003b0`；终点：`0x800003d6`。
- 预检查：`verification/out/decode-pc-profile-q4-preflight-20261028-01/`，
  仅 PREFLIGHT_NOT_RUN、输入指纹一致，不是功能或性能 PASS。
- 正式输出：`verification/out/decode-pc-profile-q4-vcs-20261028-01/`。
- 原始退休记录：该目录下 `work/commit.csv`。
- 最终汇总：该目录下 `result.json`；完成前不填写热点结论。

构建重新编译全部对象、封存当前依赖，仅从历史记录继承编译配方和原始
数据，不复用旧对象或旧软件身份。旧 selector ABBA 构建模式在共享优化
接入后显式拒绝，防止把两个都已优化的入口误标成原/新比较。
