# 共享量化 KV selector 的对齐信息接入

> 评测接线复核（2026-10-28）：本文既有 native 周期数据使用通用标量
> `dequantize_row_q8_0` 作为 V 回调；当前 llama.cpp 后端使用共享 RVV
> `akv_quant_q8_0_value`。这些历史配对数据在其配置下仍有效，但不能当成
> 当前后端回调配置下的周期或瓶颈占比。真实 GGML/模型功能回归不受此
> benchmark 差异影响。更正及补测见 `quantized_native_binding_audit_20261028.md`。


## 修改范围

`software/akv/experimental/quantized_kv/selection_strided.h` 在原 view 检查
之后，仅给 query 位模式拷贝添加 4 字节对齐信息，给 K/V scale 位模式
拷贝添加 2 字节对齐信息。继续使用固定长度 memcpy，不采用违反别名规则的
指针转换，不删除任何有限值扫描、越界、别名或设备能力检查。

query base 和 head stride 均已证明能被 4 整除，元素偏移也是 4 的倍数。
KV base、head/token stride 均已证明是偶数，18/34 字节 block 同样为
偶数。因此增强的对齐断言不增加准入假设。非 GNU/Clang 编译器保留原指针。
宏在头文件末尾取消定义。

这项修改由共享 strided runtime 和 Prefill admission 共同使用，未改
计算顺序、命令描述符、硬件资源、ISA 或 fallback 选择范围。llama.cpp
已经通过同一共享源码接入该路径，不需要再复制一套模型专用实现。

## 已有收益与回归边界

接入前的独立旧/新双入口 RTL 对照已 PASS：真实 Qwen3 query19、GQA2、
D128、20 可见 token、token-major KQ4_0/VQ8_0，完整调用均值
82691→71651 cycles，1.15408×。详见
`quantized_kv_selector_native_pair_20261028.md`。此后共享头文件改变，
该封存实验仍对应其原先记录的源码，不应再次使用旧配对程序声称当前
共享源码仍是旧基线。

`selector_baseline.h` 冻结接入前的原 selector，972 项差分测试现在比较
冻结基线与实际共享实现，而非比较两个都已优化的函数。另保留源函数
精确变换检查，证明只有 K stride 放宽及上述两处对齐信息的差异。

下一验收层级为：主机完整 Decode/Prefill 执行、正常 CMake OFF/ON 构建、
真实 GGML 图及 Qwen2.5/Qwen3 模型 logits/CSR 回归。模型级检查完成前，
不将这次局部 RTL 加速外推为模型整体收益。

## 接入后的已完成检查

- `test_selector_aligned`：GCC、Clang UBSan 均 PASS，各比较 972 项。
- `strided_selection/test_selection.py`：6 项 PASS，包括源变换、C++ 头文件、
  原拒绝集合、布局/拒绝边界和真实数据重排；包含 ASan/UBSan 检查。
- `test_native_strided`：3 项 PASS；每种正常构建含 288 个执行场景，
  且故意删除 panel 失效处理的反例会被测试拒绝。
- `test_admission test_admission_aligned test_execute test_ggml_map
  test_ggml_prefill_memory`：11 项 PASS。此前一次调用误写不存在的
  `test_ggml_entry` 名称导致 unittest 导入失败，已用这里的正确名称重跑；
  该工具调用错误不是 RTL 或软件数值失败。
- `verification/out/selector-promoted-decode-real-20261028-01/result.json`：
  Q4_0/Q8_0、连续/带间隔 K 的四组完整 Decode 回放均 PASS。
- `verification/out/selector-promoted-prefill-real-20261028-01/result.json`：
  相同四组 Prefill 完整回放均 PASS。

上述真实数据每组各 40960 输出；主机回放使用 GGML 原始 primitive 和
QBS 数值参考，不提供 RTL 时间或模型速度。

完整运行时回归入口：`run_selector_promotion.py`。它先构建正常 OFF/ON
静态库和图测试程序，再并行执行互不写入的图、Qwen2.5 和 Qwen3 检查，
各自使用独立输出目录。结果入口预定为
`verification/out/selector-promotion-runtime-20261028-01/result.json`。
该批次已全部完成并 PASS，详细模型比较边界和证据摘要见
`quantized_kv_selector_promotion_acceptance_20261028.md`。
