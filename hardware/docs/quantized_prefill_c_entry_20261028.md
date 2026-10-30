# Prefill 的 GGML C 调用边界

## 实现

`verification/akv/quantized_kv/prefill/ggml_entry.h/.c` 封装已经通过完整入口
VCS 测试的计算实现。它尚未注册到生产 GGML dispatch，也未修改 llama.cpp。
计算只在 C 文件中包含 `execute.h`，C++ 调用者包含声明头和既有 `runtime.h`。
最初误包含私有 `native.h` 导致 GCC C++ 的严格警告检查失败；已改用公开的
runtime 声明，不抑制警告、不改变内核代码或编译容差。

执行顺序为：元数据映射 → 真实 backend buffer 范围核验 → 完整准入/执行。
workspace 大小通过函数查询，要求 64 字节对齐。报告分别保留 mapping、
memory_verified、runtime_called、命令/解码/分组等原始活动字段。
`runtime_called` 表示进入 runtime，不表示准入成功或已经发出命令。

调用者必须提供不重叠的 report/workspace、稳定的 tensor 元数据和输入，
并明确保证 normal-memory/coherency 条件。host buffer 检查不能代替该保证。
正式接入仍需处于现有 `ggml_riscv_qbs_direct_run` 的所有权管理范围内。

## 边界测试

`test_ggml_prefill_memory.cpp/.py` 在原有 54 组真实分配/view 场景中增加：

- 合法 metadata 和数据域通过完整准入，到达第一条命令回调。
- 故意令第一条命令返回 BAD_ARGUMENT，入口返回 EXECUTION_FAILED，
  仅尝试一条命令，不调用后续 decode/PV 回调、不改输出。
- 多线程请求在映射阶段 fallback，未进入 runtime。
- workspace 少一字节在 runtime 拒绝，无新命令、输出保持不变。

这些故障注入使用零输入及测试回调，只验证接口控制和失败归属，不用于
数值准确性或性能结论。数值与周期证据仍以已归档的真实模型 capture/VCS
实验为准。GCC 与 Clang UBSan 均通过，未改检查器或放宽已有断言。

下一步补实际 graph 的成功调用及真实 capture 数值比较，再进行受控的
llama.cpp 集成。执行中错误不得改成 fallback，因为其他场景可能已有部分
输出写回；只有尚未执行的准入拒绝才允许交还标准路径。
