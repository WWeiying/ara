# Gap71/72/73 超时修复与验收

## 已确认的原因

正式基线是 `closure90-current-20261005-01` 的 654 项 PASS。
两批 closure91 的超时结果不能加入通过集合。

| 场景 | 原始证据 | 结论及处理 |
| --- | --- | --- |
| gap71 四项 Sv39 custom 测试 | 空 `rvtest_init`；CRT MRET 后为 U-mode；首条 mstatus 读取异常，mtvec 无效 | 修 DUT 启动 hook，设置 MPP=M 和真实 handler；不改共享 CRT/RTL |
| 修正后的 gap71 QBS read | 两次命令 success=1，busy 为 240/139 周期；300 秒时末尾 retire 序号为 38,015、到 93,019 周期，仍在内存比较 | 启动错误已消除，但完整测试仍未验收；旧预算不够完成软件检查 |
| gap72 QBS | 300 秒时退休 82,306 条；前三项命令完成，正在比较 seed | 未见未完成后端请求；保留全字节检查重跑 |
| gap72 AKV | 300 秒时退休 84,457 条；前三项命令完成，正在准备第四项 | 不是硬件死锁证据；保留完整生命周期测试 |
| gap73 AKV v1 | 300 秒时退休 90,004 条；第五阶段打印未结束；printf 占留存退休指令的 38.3% | 保留六类独立拒绝与完整合法恢复，不因时间限制删减场景 |

gap71 的启动 hook 通过链接后机器码审计，检查 MPP 设置、真实 handler
地址和 CRT 在 MRET 前的 hook 调用。软件 Spike 的 CRT 不同，因此其
通过不能证明 DUT 的启动环境正确，也不能证明 custom 指令执行正确。

## 检查器的独立修复

gap71 和 gap72 原先将 VRF 写限制在 CVX request/response 握手之间。
实际 gap71 QBS 的第一条命令在 70,332 周期分配，70,565--70,571 周期
写回，70,573 周期才完成 request 握手；该规则会误报合法执行。
gap72 AKV LOAD 也存在 early response 后继续写回的合法行为。

`custom_backend_lifetime.py` 现在按 `arch_seq` 和 `VID` 绑定：

- 每个预期 custom 必须有且只有一个 backend allocation/completion。
- opcode 必须与 architectural start 对应；拒绝未绑定的 custom 事件。
- 拒绝额外 group、重复完成和 custom VID 在完成前复用。
- 完成记录的 use_vd/vd/EEW/VL/vstart 必须与 allocation 一致。
- 写回必须在 backend lifetime 内；允许 monitor 同周期先打印 done 再打印最后写。
- 不再用接口握手周期作为执行起止周期。

这一修正没有删除数值检查：完整目的字节、源寄存器、尾部、异常零写、
PTE/data/guard、trap EPC/TVAL 与 CSR 恢复仍由原独立 oracle 检查。
旧部分 trace 的生命周期检查通过不等于完整测试 PASS。

## 新批次策略

新运行器 `run_closure92_batch.py` 保留旧运行器及原始失败凭据，仍从
同一正式 654 集合准入。新项选择明确封存 1,800 秒墙钟上限；默认
预检预算仍为 300 秒，只有显式 `--vcs-timeout 1800` 才选择新预算。
选择、producer plan、实际运行和 runtime proof 的预算必须一致。
历史 654 的预算约束没有放宽。

预算调整依据是实际 trace 已推进到有界软件循环以及余量估计，不是
用更大的超时掩盖未定位的硬件卡死。保持 RTL、VCS 镜像、完整软件
检查和测试规模不变。修正启动后的 QBS read ELF 与先前单点截断
实验逐字节一致：

`6ede44b997f3e2d5498a3a9fd6087529fdc25613b787851c4154dbf4272d23f0`

七项独立任务最多八路，实际只有七路；使用独立目录，不覆盖旧 VDB。
结束后独立验收通过项，再自动做 DVE 汇总。失败或超时项保留首错
证据但不加入正式覆盖率。仿真预计超过十分钟，不持续轮询。

## 状态入口

```bash
./vstatus jobs closure92
tail -n 30 verification/out/closure92-service-20261005-01.log
```

本文件的静态分析和预检不是 DUT 通过结论。实际通过数、运行错误、
完整覆盖率及新条件位增量以新批次 checkpoint/collection 为准。

## 完整运行后的首错定位与修复

closure92 七项完成，DUT 结果为六项 PASS、一项 FAIL。独立 collector
随后在 gap73 的 descriptor 检查处停止，因此不能把六项直接计入
正式覆盖率。正式基线仍是 654 项 PASS。

### QBS 故障后的 VRF 布局标签

`gap71_qbs_fault` 的第 60 项检查对应第一次异常快照的 v8。
初始整寄存器 load 使用 EW8 物理布局。故障 QBS 没有任何 VRF write，
但 dispatcher 在发出目的请求时提前将 v8 的 EEW 标签改为 EW32。
异常处理程序随后执行整寄存器 store，按错误标签重新解释旧数据。
16 个 64 位快照字均发生字节重排；重试 QBS 的数值结果则正确。
这不是 QBS 算术错误，也不是超时。

修复保留普通 RVV 的提前布局标记，仅排除 VQBEXEC。QBS 本来阻塞到
terminal response；只有无异常响应时才将实际写入的 M 个寄存器
标为 EW32。M=3 等情形不改 reservation 中未写入的 padding 寄存器。
故障时既没有数据提交，也没有标签提交。未增加状态寄存器、流水级
或等待周期；是否保持实测性能仍需新镜像回归确认。FOR_VERIFY 断言
检查故障响应周期的全部 EEW/valid 元数据不变。

### AKV 的独立检查器错误

实际 phase 1 中，位于 descriptor+12 的 `sw` 记录为 effective address
末三位 4、mask=f0、wdata=0x81。CVA6 的 STORE writeback 数据未移位；
旧检查器却将 mask 的 bit 4 映射到 address+4，并取 wdata 的高半字，
错误地重建了 K/V stride。依据 `cva6_rvfi.sv` 和 `store_unit.result_o`
修正为有效地址加字节索引，数据从最低字节开始，且严格验证连续 mask。

完整内存检查还必须观察 scalar load 的架构读回结果：vector store 不会
出现在 scalar RVFI 的 store retire 流中。读回检查与独立 vector write
检查并存，不将“软件打印 PASS”作为替代证据。

修正后重放原始完整日志：194 次请求/响应、6 次预期异常、11,944
字节内存检查、独立 vector 检查和 stdout 检查全部 PASS。未重跑 DUT，
未修改原始日志。检查器单元测试 31 项，28 PASS、3 项需显式 preflight
参数而跳过；新增上半字 store、不同宽度/偏移以及损坏读回负例。

### 独立新镜像回归

`run_qbs_fault_layout_repair.py` 构建带相同参数和覆盖率配置的新 VCS
镜像，再五路并行执行 QBS read/fault、AKV read/fault 和 gap73。
每项墙钟上限 1,800 秒，全部使用原 ELF 和完整独立检查；新输出目录：

`verification/out/qbs-fault-layout-repair-20261005-01`

该目录中的新 VDB 不混入旧 654 项设计。此阶段是修复验收，不是新 RTL
全套覆盖率重采集。进度查看：

```bash
cat verification/out/qbs-fault-layout-repair-20261005-01/status.json
tail -n 20 verification/out/qbs-fault-layout-repair-20261005-01/image/compile.log
```
