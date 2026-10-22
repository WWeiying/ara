# 指令及类型覆盖审计

## 结论与范围

当前尚不能宣称全部指令及其合法类型、边界和交互均已覆盖。普通 RVV 计算指令的静态形式比较齐全，主要缺口是访存变体、配置交叉、专用机制形状与错误恢复，以及标量系统能力。

本次只读审计当前冻结的 445 项覆盖回归，不修改 RTL、不重启或改变现有八路任务。代码覆盖率、指令出现在 ELF、指令实际执行、结果被独立检查是不同层次的证据。

数据文件：`verification/out/instruction-audit-20260927-01/inventory.json`。
生成工具：`verification/tools/audit_campaign_instructions.py`。
回归：`verification/out/vcs-current-coverage-20260927-01/`。

审计快照有 143 项 PASS，其他 302 项尚未完成。445 个 ELF 共出现 465 种向量助记符形式；快照 PASS 的可映射退休记录中出现 380 种。这不是最终回归结果，也不是指令功能覆盖率。部分原始编码未映射，AXPY 的该条目没有唯一退休 trace，因此执行清单是下界。退休活动本身不证明每条指令的全部架构结果均被检查。

## 普通 RVV 指令形式

以锁定的 RVV 1.0 riscv-dv `src/isa/rv32v_instr.sv` 为清单，展开 vv/vx/vi/vf 等形式；访存另行核对宽度和字段数。该清单不等同于整个 RISC-V ISA。

| 类别 | 清单形式数 | 本轮 ELF 中出现 |
|---|---:|---:|
| 配置 | 3 | 3 |
| 整数 | 139 | 139 |
| 定点 | 32 | 32 |
| 浮点 | 91 | 91 |
| 归约 | 16 | 16 |
| 掩码 | 15 | 15 |
| 排列 | 21 | 21 |
| 合计，不含访存 | 317 | 317 |

317/317 仅证明已安排 ELF 包含这些形式，不能替代当前 RTL 全部执行通过，也不能证明 SEW、LMUL、mask、VL、vstart 和舍入方式的交叉齐全。

## 访存缺口

以下分母按字段数 NF=2..8 与数据/索引宽度 8/16/32/64 展开，每类 28 种形式。执行测试时仍须按 EMUL、NF、寄存器对齐等条件选择合法配置，不能任意组合。

| 分段访存类别 | ELF 形式数 / 28 |
|---|---:|
| 连续加载 vlseg | 17 / 28 |
| 连续存储 vsseg | 16 / 28 |
| 跨步加载 vlsseg | 18 / 28 |
| 跨步存储 vssseg | 12 / 28 |
| 无序索引加载 vluxseg | 9 / 28 |
| 有序索引加载 vloxseg | 6 / 28 |
| 无序索引存储 vsuxseg | 7 / 28 |
| 有序索引存储 vsoxseg | 5 / 28 |

- 上述八类均未发现 NF=7；NF=5/6 也较稀疏。`hardware/src/segment_sequencer.sv` 的字段计数逻辑没有排除 NF=7。
- 普通有序索引加载缺 `vloxei64.v`。
- 分段 fault-only-first 只发现 `vlseg8e64ff.v`，来自 `load_store-coverage300-seed905-db158b495b83`。补充核查确认该处 e32/mf2、数据 EEW64 对应 EMUL=1、NF=8、v17 起始组配置合法，且 PC=0x80000548、编码 0xe10bf887 有 trap=0 的退休记录；不是单纯非法编码测试。但正常退休不能证明首元素、后续元素异常及字段部分完成路径。
- 普通连续 fault-only-first 四种宽度均静态出现；整寄存器加载的四种组长乘四种宽度，以及四种整寄存器存储组长也静态齐全。

## 类型与边界交叉

- 随机生成器默认最低浮点 SEW 为 32，不能替代 FP16 定向测试；需要单独核验合法 FP16 运算、转换及异常值覆盖。
- 严格随机签名流采用 tu/mu，并将部分无序归约和索引存储改为有序版本。原始 profile 覆盖不能直接当作最终执行覆盖。
- 随机访存 vstart 主要为 `[0, VL-1]`，不能覆盖 `vstart==VL` 和 `vstart>VL` 的无操作边界。
- policy/type 矩阵主要针对 `vadd.vv`，不能外推到所有指令；平均类有四种 vxrm 定向组合，但 LMUL 主要为 m1，部分饱和/窄化定向测试固定 vxrm=2。
- 应建立按指令合法域裁剪的交叉表，区分未覆盖、不可达、未实现扩展和有证据的豁免，而非简单枚举全笛卡尔积。

来源：`verification/ara_verify/{random_rvv,vector_signature,stimulus_coverage,dynamic_coverage}.py`、`verification/riscv_dv/testlist.yaml`、`apps/riscv-tests/isa/rv64uv/`。现有粗粒度 family 统计会合并多种 segment 模式，不能替代上述细分。

## QBS、AKV 与系统能力

| 范围 | 已有证据 | 主要缺口 |
|---|---|---|
| QBS | 九种权重格式均有对应测试选项 | 宽 M5..8、M8 交织及 N<=16 边界没有对应专门选入用例 |
| AKV | D64、D128 与软件分组 D256 | 合法 D96；逻辑 D256 不能代替原生 D96 |
| 专用命令恢复 | 部分非法版本、selector、寄存器、释放后访问 | 跨页/AXI 错误、非零 vstart、上下文 generation 失配、失败后状态完整性 |
| 标量 ISA | 启动与定向程序间接执行 | 尚无 I/M/A/C/F/D 的完整专项闭环，尤其 LR/SC、AMO aq/rl、FENCE.I、FP 异常与舍入 |
| 系统 | MMU、trap、状态/context 前置测试 | 中断及调度/隔离的完整证据，不能声称已验证完整 Linux |

QBS 支持边界见 `hardware/include/qbs_pkg.sv`；AKV 校验见 `hardware/src/vlsu/akv/akv_engine.sv`，D256 分组见 `software/akv/src/akv_runtime.c`。

当前配置未启用的 B/H、PMP entries=0，以及 AKV 非法的 BF16/FP32 输入，不应列成当前合法功能必须执行的空洞；需要区分非法指令拒绝测试与合法功能测试。

另发现检查器风险：`apps/llama_qwen25_real/common/qbs_benchmark_impl.h` 的 `benchmark_validate()` 仅以绝对误差超阈值累计 mismatch，没有显式拒绝 NaN。NaN 比较为 false，可能漏报异常结果。此处是检查器漏洞，不是已证实的 RTL 数值错误；本轮未修改冻结程序。

## 后续优先级

1. 保留现有八路任务；完成后导出执行与检查证据，不能用本次静态数量宣称验收。
2. 补强 NaN 检查，新增合法分段访存、索引宽度、fault-only-first 和恢复测试。
3. 补 QBS 宽 M、AKV D96，以及对应的状态切换和失败恢复。
4. 分批补 FP16、舍入、policy、VL/vstart 边界；每项记录独立 oracle 和目标覆盖 bin。
5. 单独开展标量原子/系统定向测试，不要求先运行耗时的完整 Linux。

本报告没有新增 RTL 修复、仿真或豁免。以上可达空洞不能为了提高百分比而豁免。
