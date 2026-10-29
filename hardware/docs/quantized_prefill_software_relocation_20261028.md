# Prefill 运行库收敛到软件目录

## 当前结构

已接受的 Prefill 实现位于
`software/akv/experimental/quantized_kv/prefill/`。验证目录中原来的同名文件
仅转发到这里，避免 benchmark 与真实后端维护两套执行代码。

| 文件 | 职责 |
|---|---|
| ggml_entry.h / ggml_entry.c | C/C++ API、host allocation 核对、报告与执行入口 |
| ggml_map.h | GGML tensor 元数据到请求视图的映射 |
| admission.h | 完整请求的形状、范围、mask、数值和设备能力检查 |
| execute.h | 分组、query 准备、同步执行及临时指针清理 |
| prefix_panel.h | 连续 K 直通或有界 strided K panel |
| native_prefix.h | 既有 QBS 描述符/执行器与逐行可见前缀的衔接 |
| prefix_schedule.h | M4/M2/M1 QK 与按原 token 顺序的共享 V / online PV |

未接入的 boundary planner 和其他独立实验继续留在验证目录，不进入运行库。
函数名、workspace 大小/对齐、数据类型、算法、ISA 与 fallback 策略均未改变。

## 正常构建接入

在既有 RVV/QBS/AKV/quantized-KV 构建设置上打开
`GGML_RISCV_AKV_QUANT_PREFILL=ON` 即可。CMake 的默认源目录现在从
`GGML_RISCV_AKV_RUNTIME_DIR` 推导到软件目录，不再要求显式填写验证路径。
显式 `GGML_RISCV_AKV_PREFILL_DIR` 仍可用于原有配置兼容。

运行时开关和原 normal-memory/capability gate 保持不变；功能仍默认 OFF。
这是整理已验证机制的部署接入，不是新指令、RTL 优化或额外性能收益。
llama.cpp 其他本地修改未回退；项目中的 scoped CMake patch 已同步，
不包含与本次接入无关的修改。

## 验证证据

1. 相对提交 `661e47d64` 的八个原文件逐一核对：五个文件 byte-identical，
   另外三个只修正不再准确的注释；去除注释后八个执行代码完全一致。
2. 17 项迁移/准入/执行/映射/内存/调度主机测试 PASS。旧路径编译的是转发
   入口，因此这些测试实际覆盖新的 canonical 实现，而不是旧副本。
3. 正常 CMake OFF/ON 构建 PASS，且没有显式传入 Prefill 目录。两个实际
   依赖探针各记录 25 个项目头/源输入：Prefill C entry 和 RISC-V 前端均
   不引用验证源码。生成构建文件所在的输出目录不等于源码依赖。
4. 两种构建模式共八个静态库、447 个归档条目（包括索引等条目）的内容、
   顺序、名字与非时间戳头字段完全一致。只忽略 GNU ar 创建时间戳，
   不忽略对象字节、符号表或数据；有重复文件名的成员也逐项保留比较。
5. 用新库重新编译/链接图 OFF/ON、Qwen2.5 和 Qwen3 四个最终 ELF，
   四者都与此前实测通过的对应 ELF 逐字节一致。重新运行原日志检查器，
   并核对旧报告、启动镜像、QEMU、内核及模型数据指纹，均 PASS。

因此没有重复长时间模型仿真。本批明确标注
`validation=IDENTICAL_ELF_EVIDENCE_REUSE`、`fresh_model_execution=false`、
`performance_measured=false`。复用的是此前相同程序/运行输入的 16 次图
调用及两模型累计 1823232 logits 比较证据，不是新执行的测试数量。
这一判断只覆盖软件迁移，不替代任何新 RTL 的验证。

静态库的原始整体 SHA 不同，源于归档时间戳；不能直接把这些库文件说成
逐字节相同。最终可执行 ELF 没有这种豁免，必须严格逐字节相同。
归档解析器的时间戳、重复名、内容改变、截断和坏格式反例测试均 PASS。
若成员或 ELF 不相同，等价门会失败，必须在独立目录走正常执行回归，
不能放宽条件把失败改成通过。

## 文件与命令

- 构建结果：`verification/out/prefill-software-layout-build-20261028-01/result.json`。
- 等价结果：`verification/out/prefill-software-layout-proof-20261028-01/result.json`。
- 版本控制摘要：`verification/akv/results/prefill-software-relocation-20261028.json`。
- 正常构建器：`verification/akv/quantized_kv/prefill/build_ggml_integration.py`。
- 等价核验器：`verification/akv/quantized_kv/prefill/verify_software_relocation.py`。
- 实际应用的 CMake 改动导出：`verification/akv/quantized_kv/prefill/integration/cmake.patch`。

等价核验需要已通过的旧批次以及本次正常库构建，两者不能混用不同硬件
或数值契约的性能结论。旧模型结果未修改，也未伪装成当前新执行结果。
