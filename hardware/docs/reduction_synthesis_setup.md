# 规约整机综合环境与执行入口

本环境用于 `reduction-optimization` 的完整 `ara_soc` 综合，包括真实 CVA6、Ara、Lane、VALU/VMFPU、SLDU、RCE、VRF、缓存、AXI/外设和 L2。默认是 4 Lane、VLEN=1024、1 MiB L2。准备和检查命令不启动 Design Compiler；只有明确执行 `run` 或 `make dc` 才会启动。

## 依据与修改原因

主要参考 `/home/wangwy/openproject/dc_ara_main_real/backend/syn/ara_soc/v1-dc`。该目录有 `ara_soc_dc.ddc`、`ara_soc_dc.v`、`ara_soc_dc.sdc` 和完整面积/QoR 报告；面积报告记录了 DC T-2022.03-SP2、TSMC 28nm 标准单元和 SRAM 宏。这里引用它作为已产出整机综合结果的环境依据，不把它的旧面积、时序数值作为当前规约分支的结果。`ara_dsa_signoff_integration` 的 `dc_lock.sh`、`dc_flow_state.tcl`、`run_snapshot_dc.py` 和启动脚本提供了目录锁、明确失败状态、输入冻结及批处理退出的参考。部分 ara_dsa 历史任务停在 REPORT 阶段，不能仅凭存在 area.rpt 就宣称综合成功。

原分支的 `hardware/Makefile` 虽有 `dc` 目标，但缺少 `backend/flist`、`run/run.cmd` 和 SRAM 接口文件，普通执行时规约开关默认关闭；原 SDC 是 1.25 ns、0.4375 ns setup uncertainty，与上述工作目录的 1 ns/0.15 ns 不同。旧 DC 脚本还存在 `verilogout_no_tri ture` 拼写、link 失败退出码、工具报错但 shell 返回零等问题。新入口修复这些问题，并在私有副本应用仿真中使用的 divider/FP CSR 依赖修复，不修改共享 `hardware/deps`。

## 常用命令

以下命令从仓库根目录运行。`./s` 是仓库内入口，不依赖用户全局 alias；无参数只显示帮助。它在宿主机准备文件，并在真正执行时通过既有 `synopsys_workspace` 容器、当前 UID/GID、DC T-2022.03-SP2 的绝对路径调用 `dc_shell-t -64bit -f .../dc.tcl`。

```bash
# 只查看帮助、准备状态或做静态检查，均不启动 DC。
./s
./s status --profile full
./s check --profile full

# 新配置首次准备；已存在的目录不会覆盖。
./s prepare --profile full --out hardware/build/synthesis/full_new

# 之后明确决定启动综合时才执行：本次准备工作没有执行它。
./s run --profile full

# 仅在明确决定进行 DC analyze/elaborate/link 时使用；它也会启动 EDA。
./s run --profile full --out hardware/build/synthesis/full_elab --elaborate-only

# 综合完成后重新检查并汇总面积、时序和输出文件哈希。
./s report --profile full
```

`--out` 指向的目录必须先用 `prepare --out 同一路径` 准备。上面的 `full_elab` 是示例新目录，使用前也要准备。完整综合和 elaboration-only 不共用已经尝试过的 run 目录。默认命令前台运行，便于观察退出状态；如之后需要长期后台运行，应让作业管理器直接拥有 `./s run` 进程。

保留与已有工作目录相近的 Make 入口：

```bash
make -C hardware dc_preflight dc_profile=full   # 已准备则检查，否则准备
make -C hardware dc_flist dc_profile=mixed     # 新建完整准备目录，而不只是生成裸 flist
make -C hardware dc_status dc_profile=full
make -C hardware dc dc_profile=full           # 真正启动，只消费已准备的快照
```

不要在这套入口上附加 `reduction_*=...` 临时开关。入口会拒绝这类覆盖，避免“命令看似打开、实际快照未打开”。用 `dc_profile`/`--profile` 选择固定方案。`config=default`、4 Lane、VLEN=1024 固定；该 SRAM 映射不可直接用于其他 Lane 数或 VLEN。`mc` 不再控制新入口，它固定使用与成功综合目录一致的 SRAM 宏模式。

## 四个配对配置

定义保存在 `hardware/scripts/synthesis/profiles.json`，逐项对齐当前论文 `paper_iscas_v2` 的实际 filelist，关闭功能时移除宏，不传 `MACRO=0`，因为 RTL 中有 `ifdef` 开关。

| profile | 含义 |
|---|---|
| `baseline` | 既有规约优化基础，关闭新 RCE 执行机制；不是官方未经修改的 Ara |
| `rce_only` | 通用收尾，关闭新混合发射和新整数/外部 late seed |
| `mixed` | 收尾与混合执行，关闭新整数/外部 late seed |
| `full` | 当前论文完整配置；保留该实验明确关闭的 exact seed receive 选项 |

所有配置固定普通 VALU/VMFPU 结果深度 4/4、SLDU 描述符 4，工艺、频率目标、输入输出约束、时钟门控和外围相同。继承的 exact reduction chaining 不属于这轮 late-seed 消融。不能把该四配置的差值解释成从零实现全部历史规约优化的成本。

## 短反馈面积实验配置

另提供两个以 `full` 为基础的独立配置，原有四个论文配置及默认配置不变：`full_scalar` 只增加 `ARA_RED_ORDERED_SCALAR_ADD`，固定 ADD 并关闭短反馈的 SIMD；`full_scalar_after` 在此基础上增加 `ARA_RED_ORDERED_OUTPUT_REG`，将同样的一级寄存器移到结果端。二者均为面积实验配置，准备成功不表示综合完成或整机时序通过，验证状态见 `ordered_feedback_specialization.md`。

```bash
./s prepare --profile full_scalar --out hardware/build/synthesis/full_scalar_new
./s prepare --profile full_scalar_after --out hardware/build/synthesis/full_scalar_after_new
# 只有 run 才真正启动对应快照的整机综合：
./s run --profile full_scalar_after --out hardware/build/synthesis/full_scalar_after_new
```

上述 `prepare` 和 `run` 使用同一个输出目录；示例输出目录必须尚未存在。Make 入口也可指定 `dc_profile=full_scalar` 或 `dc_profile=full_scalar_after`。

新增面积候选 `full_compact` 在 `full_scalar_after` 上只增加共享精确归一化 `ARA_RED_SHARED_EXACT_NORMALIZE`，不启用面积变差的共享更新，也不启用面积尚未确认的共享尾数提取。局部累加器面积减少 5.809%，这是局部结果，不是整机降幅。验证状态见 [规约面积精简记录](reduction_area_specialization.md)。`hardware/build/synthesis/full_compact_prepare_v1` 已通过静态检查，并于 2026-10-13 06:51:40 UTC 启动 DC。用 `./s status --out hardware/build/synthesis/full_compact_prepare_v1` 查看记录状态；同一目录不能重复启动，重试必须准备新目录。其他目录使用 `./s prepare --profile full_compact --out 新目录` 准备，Make 对应 `dc_profile=full_compact`。

## 工艺、SDC 与工具环境

默认沿用参考目录的 TSMC 28nm TT 0.9 V/25°C 库配置：四个标准单元库、六个 SRAM 库及 DesignWare，共 11 个可读库文件；其中当前文件清单声明五类实际 SRAM 接口，第六个 SRAM 库是参考环境继承的链接候选，不表示新增一块 SRAM。SRAM 的接口 Verilog 从已有参考目录复制到忽略的准备目录，工艺 DB 保留外部绝对路径并记录哈希，不把工艺文件提交到源码仓库。不运行 memory compiler 或 Library Compiler。

SDC 默认周期 1.0 ns、setup uncertainty 0.15 ns、hold uncertainty 0.075 ns、输入最大延迟 0.5 ns、输出最大延迟 0.4 ns、输入输出最小延迟 0、输出负载 0.02、最大 transition 0.3、最大 fanout 32。保留参考设计的 reset 例外；RVFI pin 不存在时不执行空对象约束。不为规约新增 false path 或 multicycle 例外。保留层次与已有 compile_ultra/clock-gating 组织；8 核为默认，不做物理布局布线。

可在新目录准备时用 `--period`、`--cores`、`--container`、`--dc-home` 覆盖相关运行设置；Make 准备时使用 `dc_period`、`dc_cores`、`dc_out`。真正 run 使用快照中封存的设置，不接受悄悄修改已经准备的约束。换工艺或主机需审查 `templates/synopsys_dc.setup.env` 和 `.main` 的库路径后重新准备。默认许可证设置来自既有环境；静态检查不申请许可证，因此许可证可用性要在后续启动时才能确认。

## 输入冻结与结果目录

默认每配置目录是 `hardware/build/synthesis/<profile>/`，包含：

- `manifest.json`：源提交、宏、389 个 HDL 的清单、头文件/流程快照哈希、工艺库哈希和约束参数。
- `sources/`：全部参与综合的 RTL/头文件副本，包含当前规约分支和已确认的私有依赖修复。
- `backend/flist/ara_soc_dc.f`：仅引用冻结副本的综合清单，无 testbench、ideal dispatcher 或行为 SRAM。
- `backend/syn/ara_soc/v1-dc/`：沿用熟悉的 `run`、`inputs`、`global_scripts`、`local_scripts`、`reports`、`outputs` 目录。
- `status.json`：准备时为 `PREPARED`；只有实际启动后才出现 `RUNNING`/`COMPLETE`/`FAILED` 等状态。

`workspace/` 是 Bender 解析时使用的临时桥接目录，真正 DC 清单不引用其可变源码，而只引用 `sources/`。保留 Bender 的依赖源顺序，去除重复行并拒绝同名冲突宏。私有依赖从已有 `hardware/build/rce/private_deps_v1` 校验；更换机器时先使用 `prepare_rce_dependencies.py` 重建，再传 `--deps`。不会修改或拉取共享依赖。

真正综合后保存 gtech 和 mapped checkpoint、最终层次 DDC/Verilog/SDC，以及面积层次、QoR、最大/最小时序、reg-to-reg 路径、宏实例、时钟门控、设计/时序检查和 vectorless 功耗报告。`synthesis_summary.json` 只有在 COMPLETE、日志无错误且必要输出齐全时才生成。层次面积可分解 `i_system/i_ara`、RCE、Lane 和 SLDU，不应只看被 L2/标量核面积稀释的 SoC 总面积。

DC 中还会核对 32 个 VRF SRAM 和 8 个 L2 SRAM、RCE 是否按配置存在，并拒绝未映射的叶单元。任何实际综合错误都保留日志和已有 checkpoint，不把旧网表当作新成功结果；重试请使用新目录。

## 本次验证边界

准备流程只运行了 Bender 文件清单生成、私有依赖哈希检查、文件/库存在与哈希检查、容器路径和工具可执行文件检查、Python 单元测试、Bash 语法检查与 Tcl `info complete` 语法完整性检查。没有调用 DC，没有 analyze/elaborate/link/compile，没有新面积、Fmax 或功耗结果。Tcl 语法完整性不等于工具命令兼容性，HDL/工艺库实际装载和映射仍需后续正式启动验证。

`power_vectorless.rpt` 是无工作负载活动注入的估计，不能作为 benchmark 功耗。映射后的时序也不是布线后 Fmax；性能分析需明确周期目标、约束和实际时序裕量，不把仿真周期收益直接当作执行时间收益。

### 首次 DC 启动与兼容性修正（2026-10-12）

`full` 首次运行在展开/链接阶段失败，未进入 `compile_ultra`。DC 对 `ara_dispatcher.sv` 中结构体字段 `rs2[0:0]` 的选择报 ELAB-298；低位对齐检查已改为与同文件其他检查一致的 5-bit 掩码比较，保持 LMUL=2/4/8 的非法寄存器组判定。CVA6 `fpu_wrap.sv` 的 NaN-boxing 检查使用运行时格式宽度初始化循环变量，DC 报 ELAB-800；准备脚本现在在综合私有副本中改为从 0 到 FLen 的常量边界循环，仅在 `bit_idx >= fmt_width` 时检查位。共享依赖与已锁定依赖快照不变；此变换应对所有消融配置统一应用。

新增工具无关回归覆盖全部 32 个寄存器号及三种组对齐、32/64-bit FLen 下各格式宽度的每个单独 boxing 位破坏及全零/全一输入。11 项脚本测试通过，但这些检查不等于 RTL 全功能回归或 DC 综合通过。首次失败输出保留在 `hardware/build/synthesis/full`；重启目录为 `hardware/build/synthesis/full_retry2`（`full_retry1` 在依赖完整性检查时停止，未启动 DC）。重启沿用 full 配置、1 ns 周期和 8 核上限，后续必须以该目录最终状态和日志确认是否成功。
