# HDV 文档索引

本文说明 `hardware/docs` 下各文档的定位。调试当前 RTL 时，优先看“当前实现准文档”；历史计划和复盘文档只作为背景参考。

## 当前实现准文档

| 文档 | 内容 |
|---|---|
| `hdv_modules_code_walkthrough.md` | HDV 各 RTL 模块的详细讲解。覆盖 TIU/TSU/IPU/VLIWPU/HEU/vector dispatch/`hdv_top`/testbench 连接、关键信号、状态机、波形观察点。适合逐模块读代码和查信号。 |
| `hdv_full_mechanism_tutorial.md` | HDV 整体机制教程。按任务启动、取指、HINT/p-bit、EP 打包、HEU 分发、标量/向量后端、task complete 的完整流程解释。适合先建立全局理解。 |
| `hdv_instruction_issue_dependency_logic.md` | 指令发射和依赖处理逻辑总结。重点说明 EP 边界、p-bit、跨包 carry、HEU pending/accepted、buffered vector early issue、标量/向量/跨 EP 依赖。适合分析正确性和性能瓶颈。 |
| `cva6_hdv_scalar_backend_comparison.md` | 当前 `cva6_hdv_scalar_backend.sv` 与完整 CVA6 的详细对比。说明复用了什么、删掉了什么、当前 3 发射标量后端能做什么、还缺什么。 |
| `hdv_program_porting_guide.md` | 普通 RVV 程序改造成 `vsaxpy_hdv` 风格 HDV 程序的规则。覆盖 `.hdv_task`、固定 task entry、`lui x0, imm20` HINT、p-bit、cross、loop flags、expected EP 计算。 |

## 分析与后续设计参考

| 文档 | 内容 |
|---|---|
| `hdv_scalar_ep_demand_analysis.md` | 基于 apps dump/kernel 的 EP 内标量需求分析。用于评估当前 2 simple ALU + 1 complex lane 是否合适，以及后续是否需要更宽标量后端或更细 functional unit 绑定。 |
| `hdv_scalar_backend_bug_review_and_roadmap.md` | 标量后端早期问题复盘和 roadmap。包含旧日志/旧 expected EP 的问题分析，主要用于理解曾经的 bug 和后续风险点，不代表当前 RTL 状态。 |

## 历史计划文档

| 文档 | 内容 |
|---|---|
| `hdv_minimal_scalar_core_plan.md` | 早期“最小标量核”草案。当前 RTL 已演进为 `cva6_hdv_scalar_backend.sv` 轻量 3 发射后端，因此本文只保留设计演进背景。 |
| `cva6_hdv_minimal_integration_plan.md` | 早期基于 CVA6 构建 HDV 标量后端的接入计划。当前实现已经落在 `hardware/src/scala_backend/`，本文用于查最初的接入思路和文件清单。 |

## 论文资料

| 文件 | 内容 |
|---|---|
| `Boosting_Vector_Instruction_Throughput_in_RISC_V_via_a_Hybrid_Decoupled_Architecture_with_VLIW_Driven_Execution.pdf` | HDV 机制参考论文，包含 Hybrid Decoupled Architecture、HEU、VLIW-driven execution 等背景。RTL 已按当前工程目标做了简化和扩展，不能把论文描述直接等同于当前代码。 |

## 推荐阅读顺序

1. 先读 `hdv_full_mechanism_tutorial.md`，建立整体流程。
2. 再读 `hdv_modules_code_walkthrough.md`，对应 RTL 模块和信号。
3. 调依赖/性能时读 `hdv_instruction_issue_dependency_logic.md`。
4. 调标量后端时读 `cva6_hdv_scalar_backend_comparison.md`。
5. 改写新 app 时读 `hdv_program_porting_guide.md`。
