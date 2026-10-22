# 第一批增量覆盖：访存形式与短控制组合

## 基线与边界

- 基线为当前 RTL 下已完成的 445 项 PASS，含独立补跑通过的 Q5_K。原始超时记录保留。
- 不修改 RTL、不重新编译 VCS，不重跑 445 个已有用例。
- 宿主机 VCS 执行；DVE 汇总。不使用 Verilator 或 URG。
- 首批针对缺失的合法分段访存形式，使用独立标量结果检查，而非只确认没有异常。
- 所有新增测试使用冻结 ELF、相同 VCS 镜像和独立输出目录。普通 FAIL/TIMEOUT 保留证据并继续其他用例；检查器、镜像或环境不可靠时停止。

## 测试设计

优先覆盖 NF5/6/7 的连续、跨步、索引分段访存和有序 64 位索引加载。选择合法 SEW/LMUL/EMUL、寄存器组和不重叠的索引寄存器。每个用例规模有界，不通过扩大矩阵来制造覆盖。

数据模式应区分字段与元素；加载结果逐字段检查，存储检查目标内存和应保留区域。masked 操作必须检查非活动元素没有被误改。正常路径覆盖不能替代 fault-only-first 的故障与部分完成语义，后者单独安排。

先完成软件/Spike 预检，再选代表点做 VCS 预检，随后八路并发。首批不使用带已知 NaN 检查风险的 QBS 数值比较器，因此不需要为访存补测修改冻结检查环境。

## 执行与汇总

已实现 40 项：NF5/6/7 × EEW8/16/32/64 × 连续/跨步/索引，共 36 项；另有 `vloxei64` × SEW8/16/32/64 四项。索引用例同时检查有序与无序操作。每项检查完整长度、短尾、masked 短尾和 VL=0。

软件预检：同一测试源码构建的 40 个 Spike HTIF 版本全部通过。RTL 使用独立的 SoC 启动/结束协议 ELF；不能把 HTIF 运行称为同一 ELF 的 RTL/Spike 逐指令差分。RTL 自检和独立退休/结束审计仍须通过。

实际目录：`verification/out/vcs-memory-gap-20260928-01/`。选择清单：`verification/tests/rvv_memory_gap_selection.json`。

状态命令：

```sh
./vstatus status memory-gap
./vstatus jobs memory-gap
```

先串行验证 NF7/e64 跨步及 e8/ei64 索引两项，然后八路并行剩余 38 项。代表点不通过时不展开；已经通过的原 445 项只复用证据。

入口：`verification/coverage/extend_memory_coverage.py`。

准备：

```sh
python3 -B verification/coverage/extend_memory_coverage.py \
  --output verification/out/NEW_DIRECTORY \
  --previous verification/out/vcs-current-coverage-20260927-01 \
  --selection PATH_TO_SELECTION_JSON
```

执行必须由独立 systemd 用户服务启动，设置 `ARA_CHECKPOINT_UNIT` 为自身服务名，`KillMode=control-group`，使用 `--execute --jobs 8`。现有调度器负责状态、时间限制和独立审计。

完成后只汇总 PASS 且 VDB 完整、身份匹配的测试。报告在新目录 `dve/summary.csv` 与 `dve/summary_waived.csv`；`collection.json` 记录总数、通过数和排除项。不把失败用例的活动算作验证通过覆盖率。

## 后续阶段

1. 根据新报告确认访存分支、操作数队列、dispatcher 的实际增量，新增刺激不预先等同于覆盖提升。
2. 针对仍未命中的可达状态补 EEW 切换、寄存器重叠、快照、store-response 等待等短序列。
3. 在独立、可追踪的软件检查器修订中补 QBS NaN 拒绝，再安排宽 M、AKV D96 与上下文恢复。
4. 系统类另补 CSR/MMU/PTW/原子操作定向程序，不启动耗时完整 Linux。

每阶段以实际退休、数值/状态检查和覆盖点增量为依据；指令静态存在不算完成验收。

操作数队列的低百分比需要按实例审查：`operand_queues_stage.sv` 对 store、slide/addrgen、mask_m 实例关闭若干转换能力，不能试图用更多激励命中参数禁用的功能。先定位未覆盖点及其可达性，只有可达空洞才生成测试；任何新增豁免均须另行提供 RTL 与配置证据。本批没有扩大豁免。
