# 块内统一非有限值判定：独立 RTL 对照

## 唯一改动与假设

此前当前后端回调配置的退休定位中，query 扫描区域有 4067 个 gap cycles、
3146 条退休指令。原实现每个元素检查一次 NaN/Inf，再更新本来就需要的
最大绝对值；候选复用该最大值，每个 32 元素 block 检查一次非有限值。
其他准入顺序与计算路径不变。

该 bit-pattern 等价性及 2819 项 GCC/UBSan 差分已通过，见
`quantized_native_production_binding_results_20261028.md`。本实验检验它在
完整调用中是否有实际收益，而不根据减少的源码行数或主机时间作结论。

## 实验隔离

- A：当前共享 selector，已包含对齐信息。
- B：独立 `selector_block_max.h` 候选，同样保留对齐信息。
- 两路 canonical `runtime_strided.c` 相同，仅在独立 translation unit
  中替换 selector 和导出名称，不覆盖生产库对象。
- 两路均使用真实后端的共享 RVV Q8_0 V 解码、GGML query 量化及 scale/MAD。
- 不改 RTL、hint、descriptor、数据布局、QBS 命令或 softmax/PV 顺序。
- 同 ELF，ABBA 四轮；每次完整 256 输出、FP flags、guard、活动及独立
  协议检查均需通过，不能只检查程序返回值。

输入继续使用真实 Qwen3 query19、GQA2、D128、20 可见 token、token-major
KQ4_0/VQ8_0，物理 8 KV heads 中选 head0。ROI 包括准入、量化、panel、
QK、softmax/PV、输出和 drain，不含 UART 或检查代码。

新日志字段为 `candidate=0/1`，不是 `aligned=0/1`，避免把本候选误记为
又一次对齐优化；构建声明 `selector_block_max=true`、`aligned_selector=false`，
检查器还要求唯一的当前/候选回调接线标记。检查器的正例、次序/数值/活动
反例以及两种日志字段的互斥测试均通过。

## 封存输入和输出

- 构建：`verification/out/selector-block-max-q4-build-20261028-01/`。
- ELF：`c07bce4f992c2ca85655e9f1fcc49a35d7a917c1c0eebe873036b4bc7c9d5572`。
- 全部 17 个对象从当前依赖重编译，无旧对象复用。
- 预检查：`verification/out/selector-block-max-q4-preflight-20261028-01/`，
  PREFLIGHT_NOT_RUN、指纹一致，不是仿真通过记录。
- 正式任务：`selector-block-max-q4-20261028-01.service`。
- 结果：`verification/out/selector-block-max-q4-vcs-20261028-01/result.json`。

候选尚未接入共享实现。等待正式结果后，只有输出/协议检查通过且完整调用
周期确有收益，才推进正常运行时回归；回归前不外推到模型整体性能。
