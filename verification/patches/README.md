# 可复现的依赖 RTL 基线

## 为什么不能只锁定 Git HEAD

`Bender.lock` 固定的是依赖仓库提交，不包含依赖工作区中的未提交修改。
原 `ara_dsa` 的 CVA6、FPnew 和 PULP DivSqrt 均存在这类修改。验证环境只克隆
干净提交，会重新引入部分已修问题；直接共享目录，则可能在仿真期间混入新改动。

本目录采用“锁定提交 + 审核补丁”的方式。`dependencies.json` 固定提交号及补丁
SHA-256。`setup_worktree.sh` 和 `verify.py deps` 只接受干净的对应提交，或已完整
应用相同补丁的工作树；未知修改、部分补丁、错误版本和软链接依赖均报错，不覆盖。
`verify.py doctor` 将缺失必要补丁视为错误，不能把干净旧版本报告为就绪。

比较相对于 HEAD 进行，包含暂存和未暂存修改。所需 CVA6 子模块
`core/cache_subsystem/hpdcache`、`core/cvfpu` 还必须匹配 HEAD 中的 gitlink 且干净。
其他未参与当前 Bender 仿真目标的 CVA6 子模块不复制、不修改、不算作已审核；
若后续目标使用它们，需要将其纳入输入清单，不能沿用当前目标的通过结论。

## 本轮纳入的改动

### 2026-10-09：逐项吸收上游正确性修复

本次不升级依赖仓库的锁定版本，不覆盖先前的本地修复。修改前的工作区
已归档为 `/tmp/ara-signoff-upstream-before-20261009.tgz`；各项测试另有
冻结源码、镜像、输入和结果指纹。依赖采用更新后的 CVA6、FPnew 补丁和新增的
`axi-local-fixes.patch`，三者均通过 `patch_state` 的精确差异核验。
`dependencies.json` 中的 `upstream_fixes` 记录借鉴的提交，不表示直接合并了
整个提交或依赖仓库。

| 部分 | 本次处理 | 定向验证结果 |
|---|---|---|
| CVA6 load | flush 优先于同拍 load-buffer 分配，取消位不被分配清除 | 32 场景、384 检查通过；旧版 16 场景失败 |
| CVA6 CSR | MRET 返回非 M、SRET 清 MPRV，不依赖 RVH 开关 | 24 场景、312 检查通过；旧版 8 场景失败 |
| CVA6 MMU | canonical 地址检查与寄存响应使用同一请求 | 192 场景、2880 检查通过；旧版 48 场景失败 |
| CVA6 PTW | RVH=0 同样拒绝非叶 PTE 的 A/D/U 非零组合 | 192 场景、2304 检查通过；旧版 84 场景失败 |
| FPnew | I2F 溢出标志、cast/FMA/DIV 的下溢边界、THMULTI flush 清理 | 5537 次结果/标签/全部 flags 比较通过；旧版 235 次不匹配及 2 处取消状态错误 |
| AXI | splitter 支持性判断、demux 容量/同拍计数、bank 响应范围 | 同一激励旧版 26/43 通过，修复版 43/43 通过 |
| Ara VLDU | 最后一个 beat 真正消费后才结束 burst，保留无 R 的 skip | 长 burst 18 场景通过；小 burst 新旧各 97 场景通过，计数和周期一致 |
| Ara SIMD MUL | 四个 SEW 分支补齐组合默认值 | 新旧各 24 配置通过，数值及逐周期等价；不是新发现的计算结果错误 |
| Ara 配置约束 | 拒绝 `VLEN < ELEN*NrLanes` 的零寄存器步长配置 | 提取实际断言块验证合法/非法边界；不是完整参数化整机验证 |

不能将表中场景、比较次数和配置数简单相加为测试程序数，也不能把多个输入
触发同一缺陷的次数称为多个独立 bug。修改未增加执行流水级；FPnew 定向
实验的全部 5537 次等待周期和总模拟时间与旧版一致，但不据此宣称整机性能
已经完整验收。

两处需要本地适配，不能逐字套用上游：

- `fpnew_fma_multi` 的 FP16/FP32 舍入位位于 super-format mantissa 内。
  直接套用统一尾部位位置会误报 UF，实测有 48 个反例；最终按目标格式选择
  正确位，并使用随请求流水的舍入模式。独立 oracle 使用 Spike SoftFloat，
  检查结果与五个 flags，而非仅比较浮点数值。
- AXI 在 `MaxTrans=1` 时，合法的不同完整 ID 可以映射到同一个计数索引；
  AR 与需要读响应的 ATOP 同拍进入，增量为 2。一位增量会截断为 0，因此
  demux 计数宽度最小为两位。测试没有用非法的完整 ID 重用充当反例。

模块详细证据与范围：
[CVA6](../cva6/upstream_20261009_report.md)、
[FPnew](../fpnew_upstream_20261009/RESULTS.md)、
[AXI](../axi_upstream_20261009/README.md)、
[Ara](../ara_upstream_20261009/REPORT.md)。
另用最终 CVA6 源码复验原 early-PPN 矩阵，278 场景、3060 检查全部通过，
证据在 `verification/out/mmu-early-ppn-upstream-parent-20261009-01/`。
该矩阵包含不同页大小/页号切换，补充 canonical 矩阵中同页相邻请求的边界。

统一整机冒烟独立于上述模块验收，使用当前源码重新编译，不使用旧镜像或
旧 VDB 背书：

```sh
python3 -B verification/uvm/run_upstream_smoke_20261009.py \
  --output verification/out/NEW_UPSTREAM_SMOKE --jobs 5
```

本次运行目录为 `verification/out/upstream-integrated-smoke-20261009-01/`，
以其中 `status.json` 的实际终态为准。十个代表程序包括 VSMUL、VFNCVT、
VFCVT、VFMACC、VFDIV、MMU relocation、AXPY、QBS control、AKV context 和
QBS/AKV handoff；检查程序自校验和实际接口协议，不声称整机逐条 Spike 对比。
每项限时 300 秒，单独目录，源码清单及镜像指纹检查不通过即拒绝验收。
本轮未收集新代码覆盖率，历史覆盖率不能转标为本次 RTL 的覆盖率。

最终闭环：原目录实际为 **9 PASS / 1 FAIL**，失败的 MMU relocation 被错误地
套用了“必须有向量流量”的 UVM 验收。原目录不改写；修正脚本按测试类型
选择检查器，MMU 使用独立的提交轨迹、CSR/trap 和物理页重映射 oracle。
复验使用 `upstream-relocate-closure-20261009-02/run`，VCS 81.87 秒通过。
该轮最初后处理从 stripped ELF 生成 dump，缺少符号，因此后处理失败；随后
冻结构建时保留的符号 dump，并逐项核对 ELF 编码，无需再次运行仿真。
最终独立验收在 `upstream-relocate-audit-20261009-03/host_audit.json` 为 PASS。

实测 26 项程序检查通过，36,892 条 retire 事件记录中包含 56 条高 VA 事件；
36,329 次正常取指无未知数据，唯一未知 payload 来自预期 instruction page
fault。原 I-cache warning 未屏蔽，已由同周期异常探针解释；不是功能数据错误。
两镜像的 433 个功能 RTL 源文件哈希及 `simulator.conf` 一致，区别为验证探针。
因此本轮十个代表程序最终均已验收，但分属原九项 UVM 和新的一项标量 MMU
复验，不将原 FAIL 伪写为 PASS。新增及原 MMU 检查器的 41 项宿主自测通过。
详细根因、独立检查和复验方法见
[`linux_mmu_relocate.md`](../cva6/linux_mmu_relocate.md#上游修复后复验的检查器选择2026-10-09)。

未盲目吸收的项：common_cells 的 FIFO usage 接口升级需要同步审计调用方；
tech_cells 的映射变更需要独立物理/FPGA 验证；APB 未发现当前路径缺失的
明确功能修复。Ara segment late-exception 提案与本地排空协议不同，尚无
可达丢异常反例，暂不套用。非默认 MVP 后端仍按下文的隔离边界管理。

### 之前已纳入的本地修复

2026-09-26 合入 store/FP 修复后，CVA6 补丁另外包含 VL preview、
保留两槽容量的请求空队列直通、队列 full 检查及浮点 CSR 顺序门控。
FPnew 补丁另外包含 FP16/INT8 转换边界、DIV/SQRT 有效格式筛选和
物理 mask 步长映射。注册表 SHA-256 已按实际依赖代码重新生成。
测试证据和仍存在的性能限制见 `../STORE_B_REPAIR_CHECKPOINT.md`。

2026-10-09 仅从主线吸收 `core/cva6_mmu/cva6_mmu.sv` 的大页提前 PPN
修正：使用当前查询的页大小，在 PPN 低位填入对应 VA 位。原有 CVA6
修复完整保留，补丁包及注册表同步更新。该项的旧版反例、定向验收范围
和剩余边界见 [MMU 专项记录](../cva6/MMU_EARLY_PPN_20261009.md)。
旧整机镜像不因补丁注册成功而获得新 RTL 的验收资格。

| 补丁 | 覆盖内容 | 适用边界 |
|---|---|---|
| `cva6-local-fixes.patch` | 提交 ID 匹配、flush 清理、queue-pop 记账、port1 退休资格、VS/SD 汇总、SSTATUS 的 VS 读写映射、ECALL/选中 interrupt tval 清零、breakpoint tval 取 PC、标量 NaN-box、THMULTI 选择；保留验证分支新增的 fence 和上游 stall | 当前 FP16/FP32/FP64 配置；不是 FP8 或 RVH 的完整验证 |
| `fpnew-local-fixes.patch` | infinity 转换、PULP HOLD 数据/状态保持、C910 `round_add55` 时序等价改写 | cast/C910 在当前配置活动；PULP HOLD 仍需独立强制背压测试 |

原 CVA6 的四文件补丁与验证分支两文件补丁做 hunk 合并，当时有五个修改文件；
SSTATUS 修复另外涉及两个包文件，ECALL 修复增加 `decoder.sv`，该阶段共八个修改文件。
不能整文件替换 `acc_dispatcher.sv`，否则会丢失一边的修复。FPnew 的 C910 改动
已包含原 `hardware/patches/fpnew/vfdsu_round_prefix.patch`，不要再次应用。

SSTATUS 修复只在启用 RVV 时暴露 `mstatus.VS[10:9]`；写入同样受 RVV 配置门控。
没有放宽 `CSR_VSSTATUS` 共用的旧写掩码，避免顺带改变尚未验证的 RVH 状态管理。
失败实验使用的旧补丁和新补丁分别保留指纹，不能把旧 simv 结果算作新 RTL 的验证。

Sv39 定向测试首次实测 116 项中仅 ECALL 的 `mtval` 失败，实际为指令编码 `0x73`。
修复只在 decoder 的 ECALL 分支清零 tval，不改变输入页故障或非法指令的 payload，
不通过开启全局 `ZERO_TVAL` 隐藏问题。复验证据见验证报告第 105 节。

随后一次 24-case/448-check 异常矩阵捕获确认 EBREAK/C.EBREAK 和 SSIP 也沿用
默认指令编码。修复分别在 breakpoint 分支写 PC、在最终中断选择后清 tval，
不清除被屏蔽中断下的非法 CSR 编码，也不改输入页故障。相同冻结 ELF 和四点
相邻回归均通过，详见第 106 节；未覆盖的 RVH、CLIC、ZERO_TVAL 配置独立保留。

`instr_tracer` 中 `+NO_INSTR_TRACE` 仅控制日志，默认不关闭；需要指令级比较时
不能关掉 oracle 所依赖的日志。它不是处理器功能修复。

Linux MMU relocation 抽取测试又捕获非 CLIC STVEC 读回丢失 BASE[5:2]：
写入/实际 trap vector 保留低位，但 CSR 读回仅保留 bit6 以上。修复让读回、
写入 WARL 和 trap 目标一致：Direct 四字节对齐、Vectored 按原硬件 256 字节
对齐。CLIC/VSTVEC 不变。原始 FAIL、周期证据和修复回归状态见
[`linux_mmu_relocate.md`](../cva6/linux_mmu_relocate.md)。注册表的新指纹不能
被解释为复验已经通过，须同时查看本次 VCS 和独立 host audit。

## 暂不应用的 PULP 补丁

`quarantine/fpu_div_sqrt_mvp-unreviewed.patch` 保存原项目的本地差异，**不在应用
注册表中**。静态审核发现两个待实测问题：

1. 非恢复除法的原始部分余数不等于最终非零余数。直接 OR 归约它可能把精确的
   FP64 `1/1` 判为 inexact，在 RUP 下还可能多加 1 ULP。
2. 若先构造溢出 infinity，再把这个 sticky 送入舍入递增，可能把 infinity 改成
   非零尾数的编码。候选反例为 FP64 `maxfinite/0.5`、RUP。

上述假设已由 `verification/out/mvp-patch-audit-20260922/` 中一次 VCS 编译和一次
八输入实验复现，同时确认 FP32 overflow 缺 NX 的旧残余问题。五项错误、三项
控制输入匹配，不能记为 DUT PASS。本轮默认标量和向量均使用 THMULTI，不实例化 PULP divider；因此先
隔离该补丁不削弱默认路径，而是避免将未验证实现默认为正确。干净 PULP 基线
本身也不因此获得签核。切换后端前必须完成对应模式的结果、flags、反压和取消验证。

2026-09-30 已针对上述根因修正两份文件，主线与唯一验证工作区的 MVP 源码
再次保持一致；178项 FP32/FP64 DIV/SQRT 正常输入专项回归通过。
详细证据与边界见 [`MVP_REPAIR_20260930.md`](../fpu/MVP_REPAIR_20260930.md)。
修正后的完整依赖差异封存在 `quarantine/fpu_div_sqrt_mvp-bounded-repair.patch`。
原始失败补丁保留，不改写历史证据；新的补丁也不自动注册为完整 PULP 后端
签核补丁，因为 FP16/BF16、特殊值、subnormal 和整机集成尚未闭环。

## 基线恢复命令

```sh
SOURCE_ROOT=/home/wangwy/openproject/ara_dsa ALLOW_DOWNLOAD=0 \
  bash verification/setup_worktree.sh
make -C verification doctor
make -C verification unit
```

重复执行不会叠加补丁。环境建立成功只证明输入一致，不证明芯片功能正确；实际
VCS、Linux/QEMU、FPGA/板级结果必须分开记录。不要使用旧 simv 为新基线背书。

## 定向验证计划与探针

| 问题 | 判别信号 / oracle | 本轮验证范围 |
|---|---|---|
| 原有修复与 fence 是否相互破坏 | issue PC/ID、queue pop、commit ID/ack、pending/ready、spill 双端握手、flush、L/S completion | 新基线重编译；归约与访存短程序，外部协议 monitor 加内部周期记录 |
| VFREDMAX 是否又误走 narrowing | reduction opcode、resize、结果位型；真正 narrowing 的独立测试 | `vfredmax_boundary` 与 `vfncvt` 成对运行 |
| infinity cast 是否被当成有限溢出 | ±Inf 在五种舍入模式下的期望值 | `vfwcvt` 的现有边界子例；该测试未逐项检查 flags，不能扩大结论 |
| 活动 THMULTI 数据路径 | `vfdiv`、`vfsqrt` 的 H/S/D 结果位型 | 现有 RTZ 代表回归，不替代全部模式/flags 矩阵 |
| PULP 原余数 sticky 假设 | 部分余数/除数、quotient、Done、roundUp、result/flags | 独立冻结副本的短单元实验，不进入默认处理器回归 |

周期日志采用上升沿更新前采样，fire 为同一采样点的 valid AND ready；队列出队、
向量响应、访存完成及架构退休是不同事件。用周期、reset epoch、issue 顺序和 PC
共同关联事务，不能只用循环复用的 ID。未触发的反压/异常组合记录为未覆盖。
