# HDV 文档索引

## 核心文档（3 个）

| 文档 | 内容 |
|---|---|
| `hdv_full_mechanism_tutorial.md` | **HDV 完整教程**。任务启动→取指→HINT/p-bit→EP 打包→HEU 分发→标量/向量后端→task complete 全流程，包含 §16 指令发射与依赖处理、性能计数器和当前 vsaxpy_hdv 运行口径。**推荐先读这个。** |
| `hdv_modules_code_walkthrough.md` | **RTL 模块逐讲解**。TIU/TSU/IPU/VLIWPU/HEU/vector dispatch/`hdv_top`/Ara 侧（sequencer hazard bypass、VLSU prefetch）的关键信号、状态机、波形观察点，以及 `run.vcs.log` / EP trace 的性能观测点。适合逐模块读代码和查信号。 |
| `hdv_program_porting_guide.md` | **HDV 程序移植指南**。普通 RVV kernel 改造成 HDV task 的规则：`.hdv_task`、task entry、`lui x0, imm20` HINT、p-bit、cross、loop flags、ebreak task-end、expected EP 计算。 |

## 参考文档（3 个）

| 文档 | 内容 |
|---|---|
| `cva6_hdv_scalar_backend_comparison.md` | `cva6_hdv_scalar_backend.sv` 与完整 CVA6 的详细对比。复用/删减清单、指令集覆盖、CSR stub、FENCE NOP、ebreak task-end。 |
| `hdv_scalar_ep_demand_analysis.md` | 基于 apps dump/kernel 的 EP 内标量需求分析，评估 2 simple ALU + 1 complex lane 是否合适。 |
| `hdv_scalar_backend_bug_review_and_roadmap.md` | 标量后端早期问题复盘和 roadmap，不代表当前 RTL 状态。 |

## 论文

| 文件 | 内容 |
|---|---|
| `Boosting_Vector_Instruction_Throughput...pdf` | HDV 机制参考论文。**RTL 已演进，不能把论文描述直接等同于当前代码。** |

## 历史文档（archive/）

| 文档 | 内容 |
|---|---|
| `archive/hdv_minimal_scalar_core_plan.md` | 早期"最小标量核"草案，当前已演进为 `cva6_hdv_scalar_backend`。 |
| `archive/cva6_hdv_minimal_integration_plan.md` | 早期 CVA6→HDV 标量后端接入计划，当前已落地在 `scala_backend/`。 |

## 阅读顺序

1. `hdv_full_mechanism_tutorial.md` — 建立全局理解
2. `hdv_modules_code_walkthrough.md` — 对应 RTL 模块和信号
3. `hdv_program_porting_guide.md` — 改写新 app
4. `cva6_hdv_scalar_backend_comparison.md` — 调标量后端时参考
