# 原始 indexed overlap 缺页恢复调查

## 输入与合法性

原始证据目录：
`/home/wangwy/fpga_runs/ara_va_rvv_retest_20261018_01/`。
本次优先处理 `original_reproducer/vector_probe.c` 和 `vector_probe.S`。
用户消息中的 `tvector_probe.S` 在该目录不存在，实际文件名为 `vector_probe.S`。
四个原始 ELF 的 SHA256 已逐项核对，与 `original_reproducer/manifest.json`
一致；不修改原始证据文件。

| 原始程序 | FPGA 已记录结果 | QEMU/Linux 已记录结果 |
|---|---|---|
| vector_resident_control | PASS，50 轮及 mask/tail/vstart 检查 | PASS |
| vector_resident_overlap | PASS，50 轮及 mask/tail/vstart 检查 | PASS |
| vector_fault_control | PASS | PASS，50 轮、150 minor faults |
| vector_fault_overlap | 连续 3 次 SIGSEGV，退出码 139 | PASS，50 轮、150 minor faults |

以上是核验的已有结果，不表示本轮重新执行了这些 Linux ELF。

目标指令 `vluxei64.v v2,(a1),v2`，机器码 `0x0625f107`，板上 PC `0x1042c`。
数据 SEW32/LMUL1，索引 EEW64/EMUL2，索引组 v2-v3，目的组 v2，VL32。
目的 EEW 小于源 EEW，且重叠在源组最低编号部分，因此符合 RVV 1.0
一般寄存器重叠规则。这是普通 indexed load，不是禁止重叠的 indexed
segment load。依据：
https://github.com/riscvarchive/riscv-v-spec/blob/v1.0/v-spec.adoc
的 Vector Operands、Vector Load/Store Width Encoding 和 Exception Handling。

## 板测症状与版本对应

三次错误地址减去基址，均为 `0x0001400000007000`。
正确前两个索引分别为 `0x7000`、`0x14000`；错误值恰好为
`(index[1] << 32) | index[0]`。该关系指向布局解释，但本身不能证明内部根因。

板测摘要记录源码提交 `adbc41505d4659e779b20f39de700fedec5f4384`。
调查开始时的验证工作树与该提交的 dispatcher、lane、lane_sequencer、VLDU、AddrGen
五个源码文件比较无差异；下述 dispatcher 修复是在此后加入。
此比较对应摘要中的源提交，不替代位流构建输入审计。

## 根因分析

本例 e32/m1、VL32 恰好写满 1024 位目的寄存器。旧 e32/m2、VL32
测试只写目的组的一半，因此两者不覆盖同一条布局优化路径。

dispatcher 对 full overwrite 省略旧目的布局转换，并在接受目的写请求时
将目的寄存器 EEW 标签更新为目标 EEW。如果 indexed load 在首元素缺页、
尚未写回任何数据，原始索引仍可能保留 EW64 物理布局，但标签已变为 EW32。
重试或异常处理中的向量保存再按错误标签解释数据，可能形成板测所见偏移。
首次请求的 source snapshot 只能保护该次地址生成，不自动保证异常后的
架构 VRF 内容和布局标签一致。

用于区分的信号：

- 接受的源快照、目的 reshuffle 和原始 VLXE 请求的顺序。
- v2/v3 的 EEW 标签、原始物理 VRF 字节、快照 capture/replay 字节。
- 第一次异常前的目的 VRF 实际写回握手和 byte enable。
- 异常的 PC、tval、vstart，以及重试的 old_eew_vs2 和索引输出。
- 真实 MMU 请求地址是否等于原始基址加当前活动索引。

dispatcher 单元测试只能证明控制与标签行为；需要完整向量数据通路及
缺页重试测试确认数值故障。系统适配测试采用实际 Sv39 页表、异常和重试，
其结果仍不能替代原始 Linux 四程序的板上回归。

## 当前处理边界

先冻结未修复输入和建立复现；本调查开始时未改变 RTL。
优先使用短的首元素故障判别测试，再运行保留原汇编和数据检查的四个对照。
不将需要 Linux 系统调用的 ELF 直接当作裸机程序运行。

## 已完成的短 SoC 复现

`system/run01/fault_overlap/result.json` 记录约 67 秒的真实 VCS SoC 结果。
程序使用原始 `vector_probe.S`，保留 32 个索引和结果检查，只执行一轮，
使用实际 Sv39 页表和标量异常处理器：仅第一页访问所需 PTE 故意无效，
第一次异常修复该 PTE 并执行 SFENCE，保持原 PC 和 vstart 重试。

| 阶段 | PC | vstart | tval |
|---|---|---:|---|
| 首次正常缺页 | `0x800007f4` | 0 | `0x0000000040007000` |
| 页表修复后的错误重试 | 同一 PC | 0 | `0x0001400040007000` |

重试错误偏移与三次板测完全相同。异常处理器未执行向量保存/恢复，
因此该故障不依赖 Linux 调度或上下文保存。Spike 对同一短程序通过。
这仍是原程序的判别性适配，不等价于原 Linux 50 轮端到端验收。

复现复用已冻结 candidate09 SoC 镜像，其 dispatcher、lane、VLDU、MMU
与调查前当前源码一致。该镜像的 AddrGen 和 wt_axi_adapter 比当前源码旧，
详情记录于 `system/run01/image-audit.json`。测试采用 AXI64 和低虚拟地址，
不能将该镜像当作当前完整 RTL 的验收结果。

## 修复候选及验证安排

真实 dispatcher 控制路径测试已完成 56 项检查，证据为
`dispatcher/out03/run.log`。未修复版本的 m1 全覆盖场景在第 56 周期接受
索引捕获，第 61 周期接受原始 VLXE；其间没有目的 reshuffle，而 v2 标签
已变成 EW32。首元素异常后，重试先发出根据该 EW32 标签转换到 EW64 的
reshuffle，再重新捕获索引。m2 部分覆盖对照在首次 load 之前已有目的
reshuffle。这与完整 SoC 的错误索引模式相吻合。
该单元平台只检查控制和标签，不模拟实际 VRF 数值；不能单独作为数值证明。

将 `indexed_load_groups_overlap` 判断移到目的 reshuffle 决策之前，
禁止重叠 indexed load 使用 full-overwrite 的目的布局转换省略条件。
因此，索引先进入现有快照，旧目的字节转换到目标布局，再发出原始 load。
即使首元素发生异常，架构 VRF 字节与布局标签也保持一致，重试仍能恢复索引。
不增加快照存储或新流水级；非重叠访问的省略条件保持原样。

第一处修复的冻结目录：
`/home/wangwy/fpga_runs/indexed_fault_overlap_fix_20261018_01/frozen`。
`system/fixed01` 的四个原始场景短版全部 PASS；运行约 48--53 秒/项。
`system/run02/fault_overlap` 使用相同 ELF，在旧镜像再次复现相同错误，
其 SHA256 与 `fixed01/fault_overlap` 一致：
`23c6ba3f87b4f7da607b2cf1d851d46cfae229dfb5976570354796f2526be267`。
两个镜像并非只差 dispatcher：新的镜像也包含之前已验证的 VA 和缓存修复，
因此定位同时依靠下述单模块控制测试和数值错误模式，不将其当作单变量性能实验。

### 上下文恢复暴露的第二处遗漏

额外的 `fault_overlap_context` 在缺页处理中调用现有 Linux 风格保存/恢复序列：
以 e8/m8 的四组 store/load 保存和恢复全部向量寄存器，再恢复向量 CSR。
该补充项在旧镜像和第一处修复镜像上均失败；不得以四项通过掩盖此结果。

`system/context_probe01` 在保存后逐项检查内存中的 v2/v3 共 32 个索引，
全部与原输入一致。因此，保存出的数据正确；仅恢复并重试后出现异常。
这次错误发生于 vstart=1，tval=`0x0000000120401070`。

静态路径：恢复后索引组均为 EW8，组内布局不混合；原源转换条件仅覆盖
in-lane、compress 或 mixed indexed layout，因此跳过 EW8 到 EEW64 的转换。
source snapshot 实际保留 raw VRF words，却以请求的 EEW64 标记；后续 replay
又将 AddrGen 的 old_eew_vs2 设为该标记，导致字节被错误解释。
`dispatcher/out_uniform_eew8_fix1_01` 的真实控制路径测试确认：
source_normalizations=0，但已捕获并发出 VLXE，快照标签为 EW64。

第二处修复仅将 overlapping indexed load 加入源布局转换门控。
当实际布局不同于请求索引 EEW 时，先转换索引，再捕获快照，再转换目的。
同 EEW 或非重叠 indexed load 不增加此转换。
最终候选冻结于 `/home/wangwy/fpga_runs/indexed_fault_overlap_fix_20261018_02/frozen`，
对应 `image/image.json` 的新 SoC 镜像构建成功。

### 单元控制测试的限制

历史 `out03` 和 `out_fixed01` 中的 `m2_partial` 是路径刺激，不是合法程序：
索引 EMUL=m4 时 v2 未按组对齐。因此不计作合法 RVV 指令回归。
新的部分覆盖对照采用 e32/m1、VL16，仍使用合法的 v2-v3 索引组。
控制测试的 PASS 数量不是完整处理器指令通过数量；数值结论以 SoC/Spike 为准。

## 最终验证结果

最终输入在 `system/nearby02`，VCS 结果在 `system/fixed02`。
七项并行执行，每项均检查所有 32 个结果、前后 guard、异常次数、cause、
tval、vstart、VL、vtype、vcsr/fcsr 和结束状态。七项 Spike 参考均 PASS。
VCS 判定同时要求 SYSTEM_PASS、零错误、Core Test SUCCESS 和进程成功退出，
不将进程退出码 0 单独当作通过。

| 测试 | 实际预期缺页位置（元素编号从 0 起） | VCS | 耗时（秒） |
|---|---:|---|---:|
| resident_nonoverlap | 无 | PASS | 48.010 |
| resident_overlap | 无 | PASS | 48.319 |
| fault_nonoverlap | 0 | PASS | 52.735 |
| fault_overlap | 0 | PASS | 53.061 |
| fault_overlap_context | 0，加入向量上下文保存/恢复 | PASS | 54.557 |
| fault_overlap_mid | 17 | PASS | 50.540 |
| fault_overlap_last | 31 | PASS | 52.846 |

所有缺页项只产生一次预期 page fault，修复页表后成功完成原始 gather；
mid/last 的实测 vstart 分别为 `0x11`/`0x1f`，tval 分别为
`0x40004000`/`0x4001a000`。不重新加载索引掩盖错误。

新输入的 ELF 文件哈希因重编译而不同，但对 `fault_overlap` 和
`fault_overlap_context` 已按 ELF64 PT_LOAD 逐段核验：入口、虚拟/物理装载地址、
权限、文件/内存长度、对齐和全部装载字节均与 `run02` 完全一致。
例如 fault_overlap 的代码装载段 SHA256 为
`ba59890545a90852c1b12615fd7bb4027de2e382f913ce049bab651ff7b84753`，
context 项为 `254afdfaf2e3ed577a1cb88efd1473c49d7cffc9c0f8488b3dbcaab13d04ec08`。
两者的数据装载段均为
`c0aff171b2202e0e5fb52674e385c0b7950619d6c824d86d83cd746bcb83982a`。

独立控制路径验收 `dispatcher/out_normalized_legal_fix2_02` PASS 117 项检查：
uniform EW8 用例在周期 288/289 转换两个源寄存器，296 捕获快照，
302 转换目的寄存器，306 发出原始 load。这些是单元测试周期，不是 SoC 周期。
合法 e32/m1 VL16 部分覆盖、VL32 完整覆盖及重复 fault-0 均检查通过。
独立审查未发现新增门控影响非重叠路径。

### 修改范围与剩余验收

- 本次 RTL 仅修改 `hardware/src/ara_dispatcher.sv` 两处布局门控，
  复用既有 reshuffle、source snapshot 和等待完成机制。
- 没有新增快照容量、接口、流水级；普通非重叠访问的条件不变。
- 原本错误省略的布局转换会增加该重叠场景的维护周期，不能宣称所有场景零性能开销。
  本次是正确性回归，没有进行任务性能基准测试。
- 本轮实际执行的是保留原始 gather 汇编与数据的短 Sv39 适配程序，
  不是重新运行原 Linux ELF 的 50 轮、mmap/getrusage/mask_restart 全流程。
  板上原始四程序仍须在更新位流后重测，当前不能关闭 FPGA/Linux 端到端验收。
- 修改位于 `ara_dsa_signoff_integration` 验证工作树，尚未同步主线/FPGA RTL，
  未综合；修复、测试源码和结果摘要一并纳入验证分支版本管理。
  此前 AddrGen 的完整虚拟地址修复保持不变。

### 复跑命令

在验证工作树根目录，以不存在的新输出目录复跑最终七项：

```bash
python3 verification/fpga/indexed_fault_overlap_20261018/system/replay.py \
  --image /home/wangwy/fpga_runs/indexed_fault_overlap_fix_20261018_02/image \
  --prepared verification/fpga/indexed_fault_overlap_20261018/system/nearby02 \
  --out verification/fpga/indexed_fault_overlap_20261018/system/replay_new \
  --jobs 7
```

汇总为输出目录的 `results.json`；各项 `result.json`、`vcs.log`、
`commit_trace.csv`、限时窗口 `focused.fsdb` 和镜像/ELF 身份记录均保留。
