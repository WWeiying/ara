# HDV 文档索引

## 当前硬件设计入口

| 文档 | 内容 |
|---|---|
| `hdv_design.md` | **当前 HDV RTL 权威设计说明**。合并原 full mechanism、module walkthrough、prefetch config、scalar backend comparison、EP demand analysis、bug roadmap 六份文档，并按当前 RTL 重新整理。推荐先读这个。 |
| `hdv_program_porting_guide.md` | **HDV 程序移植指南**。普通 RVV kernel 改造成 HDV task 的规则：`.hdv_task`、task entry、`lui x0, imm20` HINT、p-bit、`packet256`/`cross`、loop flags、`prefetch_mode`/`prefetch_disable`、task-end 和 sweep 验证。 |
| `paper_ch3_seamv_hardware_architecture.md` | 论文第三章硬件架构草稿，偏论文正文风格，不替代 RTL 设计说明。 |

## 论文

| 文件 | 内容 |
|---|---|
| `Boosting_Vector_Instruction_Throughput...pdf` | HDV 机制参考论文。**RTL 已演进，不能把论文描述直接等同于当前代码。** |
| `paper.md` | 论文总稿/实验规划。 |
| `paper_data.md` | 论文数据表。 |

## 历史文档（archive/）

| 文档 | 内容 |
|---|---|
| `archive/hdv_minimal_scalar_core_plan.md` | 早期"最小标量核"草案，当前已演进为 `hdv_scalar_backend`。 |
| `archive/cva6_hdv_minimal_integration_plan.md` | 早期 CVA6→HDV 标量后端接入计划，当前已落地在 `scala_backend/`。 |
| `archive/hdv_avl_sweep.md` | 2026-06-22 左右的 AVL sweep 历史快照；其中 kernel 集合、失败状态和 CSV 文件名已过时。 |
| `archive/hdv_kernel_status.md` | 2026-06-22 左右的 kernel 状态历史快照；当前通过/性能状态不要以此为准。 |

## 当前数据与脚本

| 项目 | 说明 |
|---|---|
| `hardware/kernel_sweep.sh` | 当前统一 sweep/单点脚本，支持 `point`、`all`、`--skip-long`、`--append` 和 `KERNEL_SWEEP_OUT=<dir>`。 |
| `hardware/kernel_sweep_sum.sh` | 从 log 直接重建 `kernel_all.csv` 和各单项 CSV；不读取旧 per-kernel CSV，避免 stale 数据混入。 |
| `kernel_sweep_out*/kernel_all.csv` | 当前 sweep 汇总 CSV。需要保留多组实验时，用不同 `KERNEL_SWEEP_OUT` 目录。 |
| `paper_data.md` | 当前论文数据收集文件；其中 representative metrics 已按 HDV/main real/main ideal 原始字段展开。 |

## 阅读顺序

1. `hdv_design.md` - 建立当前 RTL 全局理解，并按模块查具体逻辑
2. `hdv_program_porting_guide.md` - 改写新 app
3. `kernel_sweep.sh` / `kernel_sweep_sum.sh` - 跑单点、sweep 和汇总
4. `paper_ch3_seamv_hardware_architecture.md` - 写论文架构章节时参考
5. `paper_data.md` - 查当前实验数据
