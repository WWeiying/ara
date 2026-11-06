# 输出驻留候选的 llama.cpp 接入准备

## 当前状态

本轮只建立默认关闭的接入草案，并进行真实 RISC-V 目标对象编译。
没有覆盖 `/home/wangwy/llama/llama.cpp` 的已跟踪或未提交文件，没有改变生产 ELF、
板卡、RTL 或默认后端。正在运行的成对 VCS 试验仍使用先前封存的输入。

新增 SDK 入口：
`software/akv/experimental/quantized_kv/output_tile/ggml_entry.h`。
它复用原有 tensor mapper、host allocation 范围检查和 strided runtime 协议，
只转入独立的 `quant_output_tile_execute`。NORMAL_MEMORY 仍由调用方根据平台
确认，不能仅因 GGML buffer 为 host-accessible 就宣称满足硬件内存契约。

## 接入方式

`prepare_output_backend.py` 从 llama.cpp 固定交付提交
`da56aa750559c180d631b466de983ff2bb5d54d9` 提取两个文件，按唯一匹配的源码锚点
生成修改后的文件和可检查补丁。原 checkout 的脏文件不会混入：

- `ggml/src/ggml-cpu/CMakeLists.txt` 增加默认 OFF 的
  `GGML_RISCV_AKV_OUTPUT_TILE`，位于已有 QBS、AKV 和量化 KV 支持的条件下。
- `arch/riscv/quant-kv.cpp` 在 Decode 的已有 DIRECT task/mutex 中调用新入口。
- 编译时启用不等于运行时启用；还需显式设置 `GGML_RISCV_AKV_OUTPUT_TILE=1`。
- 与 grouped-PV、Register-PV 的运行时选择互斥，冲突时在执行前 fallback。
- Prefill、F16 Attention 和未启用时的原有路径不重定向。
- 拒绝和执行失败沿原有 complete/fallback/failed 分别处理，不能执行一半后再
  默默调用普通路径重算。

新入口在异常 context 状态下先返回拒绝，report 清零使用 volatile 字节循环，
避免这一步被编译器换成向量清零。实际机器 CSR 仍由 runtime 的入口再次检查。
最终检查还必须包括实际 GGML 图中的拒绝、指令执行及输入不变性，不能只看代码。

## 已完成验证及范围

准备目录位于唯一验证工作树的
`verification/out/e2e_output_backend_20261106_02/`，状态为
`ADAPTER_PREPARED_NOT_COMPILED_OR_EXECUTED`，这是准备步骤的固定回执。

后继 `check_output_backend.py` 在新的目录中重新提取完整交付 GGML 源码、校验
补丁前后哈希，再编译真实 RISC-V 对象，不依赖修改中的 llama checkout：

| 组合 | 目标对象编译 | 新 runtime 的未解析引用 |
| --- | --- | --- |
| 两项均关闭 | 通过 | 无 |
| 仅 Register-PV | 通过 | 仅 `quant_register_execute` |
| 仅 Output-tile | 通过 | 仅 `quant_output_tile_execute` |
| 两项均编译 | 通过 | 两者都有，运行时仍互斥选择 |

完整回执：`verification/out/e2e_output_backend_compile_20261106_02/result.json`，
状态 `TARGET_ADAPTER_COMPILE_PASS_NOT_GRAPH_ACCEPTANCE`。
编译目标为 rv64gcv_zfh_zvfh、lp64d，保留严格 FP 与 fused-MAD 的既有策略。

编译保留了上游 `vec.h` 的两处 FP16 type-punning strict-aliasing 警告，原样保存
stderr；该类警告不设为 fatal。unused-function 按既有 GGML 配方关闭，其余
警告仍设为 error。本轮没有修复或执行这些 FP16 函数，不把该检查宣传为零警告。

这四项是对象编译及符号检查，不是 CMake 全目标构建、链接、GGML dispatch、
完整模型或性能验收。特别是不能因为调用符号存在就认为所有模型都启用了候选。

## 复现

```sh
python3 -B verification/performance/end_to_end_baseline/prepare_output_backend.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/backend_prepare_next
python3 -B verification/performance/end_to_end_baseline/check_output_backend.py \
  --prepared /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/backend_prepare_next \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/backend_compile_next
```

## 接下来必须完成

1. 完成正在运行的完整调用 ABBA 与协议验收，不能以首对结果替代最终验收。
2. 用隔离交付树和固定 SDK 构建实际后端，覆盖新选项开/关、与旧路径共存，检查
   CMake 的真实源文件、编译选项和最终链接输入。
3. 实际执行 GGML 图，证明命中新入口并比较输出/fflags/native 活动，覆盖真实
   多 KV head、跨 tile、mask、线程和 NORMAL_MEMORY 拒绝；图测试不以直接调用
   SDK 入口冒充。
4. 扩展代表性真实形状后再决定运行时选择条件，并完成模型级检查。

当前原生试验的第一对完整调用结果有改善，但 ABBA 尚待完成；不在本文件中
把暂时数值写成最终收益，也不宣称整体软硬件优化 goal 已完成。
