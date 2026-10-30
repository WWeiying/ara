# 共用 Decode selector 的对齐读取实验

> 评测接线复核（2026-10-28）：本文既有 native 周期数据使用通用标量
> `dequantize_row_q8_0` 作为 V 回调；当前 llama.cpp 后端使用共享 RVV
> `akv_quant_q8_0_value`。这些历史配对数据在其配置下仍有效，但不能当成
> 当前后端回调配置下的周期或瓶颈占比。真实 GGML/模型功能回归不受此
> benchmark 差异影响。更正及补测见 `quantized_native_binding_audit_20261028.md`。


`selector_aligned.h` 独立复制现有 strided selector，保持所有条件及拒绝顺序，
只在 view 校验后显式标明 query 位模式四字节对齐、K/V scale 二字节对齐。
原软件 `selection_strided.h`、Decode runtime 和 RTL 尚未改变。

## 安全依据

现有 view 检查同时证明 data、token stride、head stride 的对齐和有效范围。
query element 偏移是四的倍数；KV block 大小 18/34 均为偶数，因此 scale
地址满足二字节对齐。候选仍通过 builtin memcpy 复制对象表示，不做 typed
pointer 双关。非法 base/stride 在到达 alignment assumption 前已拒绝。
mask 和能力等其他读取未全局替换。

## 差分与代码生成

`python3 -B -m unittest test_selector_aligned` 的 GCC/Clang UBSan 均通过。
共 972 场景：960 个有效组合，覆盖 D=32/96/128、GQA=1..8、KV heads=1/2、
两种 K 格式、五个 VL 前缀和连续/行间 padding 布局；另有 12 项未对齐、
非有限数、alias、越界和能力拒绝。旧/新返回值、有效 selection 字段、浮点
异常标志一致，拒绝时不写 selection。未将 padding 字节误作有效字段比较。

代码生成保存在 `verification/out/selector-aligned-codegen-20261028-01/selector.s`。
GNU RISC-V GCC 14.1.1、O3、fno-builtin、fno-tree-vectorize 下，探针函数
静态 lbu 数由 18→12、sb 由 6→0、sh 由 1→0；这些是源码相关静态出现数，
不是动态执行次数、覆盖率或周期比例。候选暴露的对齐允许编译器避免查询/
scale 检查中的临时字节复制。

## 下一步

当前只是独立 selector，尚未在真实数据完整执行路径或 RTL 上测量。
应先以真实 capture 比较候选/原 Decode 和 Prefill 的输出、异常标志、活动及
拒绝行为，再在相同 ELF 中计入完整准入成本测周期。不能复用上次 Prefill
额外 query 行对齐的 1.485x 作为这里的收益，也不修改现有 selector 的复制
校验契约来跳过测试。
