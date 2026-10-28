# 准入读取的编译结果归因

候选 `admission_aligned.h` 是独立函数，未安装到生产。它完整保留原准入
逻辑，仅在两处已证明对齐的读取中使用编译器 alignment assumption。
仍用固定长度 builtin memcpy 复制对象表示，不转为违反别名规则的 typed load。

## 对齐证明

- query 的 `akv_quant_view_valid(...,4)` 已验证 data、token stride、head
  stride 均为四字节对齐；block 和 element 偏移也是四的倍数。
- mask 已验证 data 和 row stride 为二字节对齐；token 偏移为二的倍数。
- 新假设只用于上述检查成功后的数据读取。未提前用于非法/未对齐输入。
- 现有 Decode selector 仍保持原实现，未在未证明的其他字段读取中全局替换。

## 代码生成证据

用现有 bare-metal GNU GCC 14.1.1、O3、rv64gcv_zfh_zvfh、fno-builtin、
fno-tree-vectorize、fno-fast-math 编译 `admission_codegen.c`，生成带源注释的
`verification/out/prefill-admission-codegen-20261028-01/admission.s`。

原额外 query 行检查的元素读取：4 次 lbu、4 次 sb 写临时栈对象、再 lw 读回。
编译器在这里不知道地址已由自定义校验函数证明对齐。
候选读取为一次 lw，不经上述临时字节复制；mask 使用 lhu。
这是静态指令序列证据，不是动态指令数或测得的周期节省。

## 差分测试

`python3 -B -m unittest test_admission_aligned` 在 GCC 和 Clang UBSan 下通过。
复用原 20 项正常/拒绝场景，并增加未对齐 query base、query token stride、
mask base 三项。每次同时运行旧/新函数，要求返回原因、完整计划对象表示、
浮点异常标志一致；拒绝时不写调用者计划，输出保持原状。
NaN、tiny query、隐藏 KV scale、mask 洞、别名与能力拒绝仍检查。

## 下一步

先用真实 capture 经过完整计算入口检查数值与拒绝行为，再将原/新准入的
阶段成本和完整调用周期在同一 ELF 中配对测量。不得依据 lw 数减少就
假定净收益，更不删除 source-domain guard。RTL 和生产入口当前未变。
