# Gather remainder12 准备结果

**PREPARED ONLY，未运行 DUT。** `ready.json` 为
`PREPARED_12_HOST_SPIKE_PASS_NOT_DUT`，`vcs_started=false`。
本轮准备设置300秒总限，实际18.93秒完成；只有既有 GCC 构建和 Spike 参考检查，
没有 VCS service/launcher、镜像构建或 RTL 修改。父38和 NF7 的运行/资源状态未操作。

## 最小批次选择

已有8项覆盖7个 shape；下列12项各补一个不同的未覆盖 shape，来自真实 first-failing
single，而非合成扫描点。全部通过后才可称19个 archived shape 均至少有一个 single
通过；仍只有20/83来源单点，不能声称其它 opcode/数值 tuple 或父矩阵通过。

case ID 为 `gather_` 加下表后缀；共同条件 seed0、scalar0、VL2、mask0（全开）、
trial0/vstart1、tu/mu、destination91。目标 seed 的完整 capacity RNG/input/indices/
predicate/setup 保留；原 asm、full-cap oracle、双 guard、返回 vstart、cases/errors 保留。
仅六层空枚举循环缩到准确 tuple，原 filter 未删除。

| 后缀 | op | cap | Spike 固件退休数 | 选择依据 |
| --- | ---: | ---: | ---: | --- |
| e8_mf4 | 0 | 32 | 11416 | 最后一个未验收的未拆分 fractional parent single |
| e8_mf2_ops20 | 20 | 64 | 12295 | EI16 索引加宽，index EMUL1 |
| e8_m1_ops1 | 1 | 128 | 15171 | SEW8 LMUL1，scalar index0 |
| e8_m2_ops3 | 3 | 256 | 21015 | 最大 archived SEW8 LMUL，index31 在范围内 |
| e16_mf2_ops20 | 20 | 32 | 12454 | fractional EI16，index EMUL1/2 |
| e16_m2_ops0 | 0 | 128 | 17603 | SEW16 LMUL2 |
| e16_m4_ops20 | 20 | 256 | 22884 | 最大 archived SEW16 LMUL，index EMUL4 |
| e32_mf2_ops3 | 3 | 16 | 14716 | index31 超出 VLMAX，结果应为0 |
| e32_m2_ops0 | 0 | 64 | 17559 | SEW32 LMUL2 |
| e32_m4_ops1 | 1 | 128 | 19700 | SEW32 LMUL4，scalar index0 |
| e64_m2_ops3 | 3 | 32 | 21561 | index31 恰为 VLMAX-1，结果必须取 input31 |
| e64_m4_ops20 | 20 | 64 | 23015 | EI16 索引缩窄，index EMUL1 |

未虚构不在83来源中的 e8/m4、e8/m8、e16/m8 或其它 fractional opcode。
不选择新 seed/mask/VL/vstart，不将一个来源改造成另一个数值 tuple。

## 精确来源、哈希与差分

归档根为
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_verified_handoff03/rvv_small_gather02`。
每个 case 的原来源目录为该根下 `rvv_small_gather_restart_` 加上述后缀。
每目录的 `scenario.c`、`operations.S`、`operations.h`、`case.json`、`scenario.elf` 与
`original.elf` 均核验；不是直接运行这些 Linux ELF。

- `prepared01/provenance.json`：逐项原目录、完整 original_case、三个原 source SHA256、
  reduced Linux ELF SHA256、original Linux ELF SHA256、编译 defines 与完整 PASS markers。
- `soc01/programs.json`、`spike01/programs.json`：逐项新 port ELF 的独立 SHA256、原编译器
  路径与 SHA256；`commands.json` 保留全部编译命令。runtime/startup/linker 与 integration 相同。
- `source_diffs/*.adapter.diff`：原 source 到既有 integration Linux entry/I/O/exit adapter。
  `*.loops.diff`：仅六层循环边界变化，可逆恢复到未缩界 port；无 oracle/asm 变动。
- `source_pins.json`：原输入、已验收8的 sealed pins、parent mapping、既有 adapter/runtime
  与生成器的绝对路径/精确 SHA256。准备前后均匹配，没有覆盖旧300秒 records/pins。
- `reference01/reference.json`：12项 full oracle+exit0、每项原汇编13指令窗口逐编码一致、
  SoC target PC、Spike 提交日志哈希、target 各退休一次、固件退休计数及命令。

ready 绑定 source_pins SHA256：
`fc21d73e0f38f387b23f597fc0ab783750ae54cf962ca2c02f51b4d35ae7e88b`。
coverage83 SHA256：
`22f73f954cb2bc87424ed71dd28c7b9669dfc9f3f37a58db231c8b05febb52c7`。
reference SHA256：
`6c19105561d4f7cb38d56cfbc6c1024766820b69843515c90af8a6dde6dcfd75`。

## 原83、parents 与重复身份

`coverage83.json` 是83条逐记录 ledger，不是将12项准备扩写成83项通过。
状态为 accepted source8、prepared-not-DUT12、not-prepared63，**75项尚未验收**。
余75项按 op0/1/2/3/20 分布恰为各15项。所有83条的 source/ELF、原始首错 detail、
selected_trial、shape/op、parent SHA256 与已知重复 ELF 路径保留。

83 = 80 个 opcode partition 来源 single + 3 个未拆分 fractional parent 的 op0 single。
full parent 是19个独立身份，各56448配置；opcode partition 各2688配置。
83个 reduced ELF 哈希和83个 original ELF 哈希各自均不同，但不能因此忽略它们与父矩阵
的覆盖包含关系。filter 字段除 op/actual 外共同相同，historical actual 在83记录中只有9种
数值；**这既不是83种数值 tuple，也不是9个可以合并的来源**。

核验了284个不同的已知 alias 路径，来自 reduced overlay、original_rebuilt、partition
overlay、parent overlay 和 additions36/binaries；哈希相同的文件是重复归档，不是独立
测试。ledger 保留每条来源的 parent/partition 身份且一律 `parent_closed=false`。
这里只索引已知 canonical aliases，不声称遍历了所有历史 recovery 文件副本。

## 语义检查与工作界限

`host_semantics.json`：原56448枚举仅一个 tuple 实际执行；缩界后仍恰为同一 tuple。
完整 cap scalar 预期、两个 guard91、返回 vstart0、cases1/errors0 和 archived 首错实际值
均核验。`test_remainder12.py` 的5项独立只读回归全 PASS，包括原始 pins、可逆 source
diff、完整 oracle 后半段不变、独立 RNG/fullcap 模型、ELF/日志身份、退出0与 failure marker
veto、重复 PASS marker 拒绝、83账本不重复计数/不声称 parent closure。

运行检查：在仓库根执行
`python3 -B verification/fpga/current_board_review/gather_original_review/test_remainder12.py -v`。
生成器只接受新的不存在目录；不会重试、覆盖或补跑。

Spike 每项耗时0.116–0.210秒；表中退休计数从固件入口到 HTIF 退出 store，包含固件
启动/setup/oracle，排除5条 boot ROM 和退出后自旋。**它不是 SoC 周期或 VCS速度保证。**
空循环从56448组合降为1，最大 fullcap256不超过已通过8项的最大 cap，未引入新枚举轴。

父最新协调指令为 Gather 预留 **4 workers，最多4路**，记录于
`resource_reservation.json`；不是新的启动授权。未来 whole1134 6 + NF8 8 + NF7 2 +
DUT38 4 + Gather 4 = cap24。待父 ready review，随后启动前重新核验实际资源；
若资源满足，不必等待 DUT38 完成，它使用独立镜像/输出。不沿用本轮任何资源假设。

若后续审核批准 candidate04 jobs4，已有同类8项实测23.58–62.55秒可作为参考，先给每项
30–120秒的宽松估计，整批约1.5–6分钟加启动开销；未经 DUT 测量，不能当作硬保证。
保留300秒/case、jobs4时12项最多3波约15分钟加启动开销，首错停、不自动重试。
**未授权/未启动新 VCS**；尚无本批次 VCS launcher。
