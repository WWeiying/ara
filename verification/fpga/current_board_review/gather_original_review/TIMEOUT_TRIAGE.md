# Gather 300秒终态只读归因

## 原状态与结论

`vcs_candidate03_01` 保持原样：TIMEOUT 1、CANCELLED 7；其中首两路均实际运行约300秒，另六项未启动。`complete.json` 不是 PASS。没有将中途检查完成改判为程序验收通过。

两项结束前持续退休，目标 gather 与该 tuple 的完整检查早已结束，主要时间消耗在原始单点筛选的空枚举循环。当前证据支持预算低估，不支持 DUT 卡死、gather 未完成或移植语义错误。candidate03 镜像未修改。

## 封存轨迹

| 项目 | gather_e16_m1_ops0 | gather_e8_mf8 |
| --- | ---: | ---: |
| 最后退休 cycle | 327037 | 322499 |
| 最后退休 PC | 0x800003be，bnez t1 | 0x800003b8，li a4,2 |
| 退休指令数 | 191078 | 227437 |
| gather PC / cycle | 0x800006d2 / 14144 | 0x800006ce / 8489 |
| 完整 tuple 检查结束 cycle | 15720 | 8995 |
| 输出元素检查数 | 64 | 16 |
| 输出前两项 | 91,538 | 91,26 |
| 剩余输出元素 | 全部91 | 全部91 |
| 检查后 cases / errors / vstart | 1 / 0 / 0 | 1 / 0 / 0 |
| 最后1000条指令覆盖周期 | 325287..327037 | 321087..322499 |
| 最后枚举 seed/op/s/l/mode/trial | 1/12/2/0/2/1 | 0/18/7/4/0/3 |

证据目录：`vcs_candidate03_01/replay/tests/gather_e16_m1_ops0/` 与 `gather_e8_mf8/`，保留 console.log、commit_trace.csv、input.elf、inputs.json。两项 trace 未见 trap，errors 寄存器始终为0。实际 SoC ELF SHA256：

- e16：`da1bf208f6eafd6248784fbf480e40474a892e1c4c43d313d307b4caa24757c3`
- e8：`373cb5e1f5e10eb390bc9b7d4547403ab66cfd5734a112a7099fb86d8c61ae40`

## 空迭代与 Spike 计数

归档单点仅加入精确 tuple 的 continue 过滤，仍枚举 `3*21*8*7*4*4=56448` 个组合。只执行一次目标，其他组合仍产生计数、条件计算和分支。截止300秒分别推进约29801、16979个组合，不是无限循环。

使用既有 `spike01` 封存 HTIF ELF，命令为 `spike --isa=rv64gcv_zvl1024b -m2 --log-commits --log=/dev/stdout ELF`，提交日志仅在内存处理，未覆盖 reference01。两项 exit0，目标 vrgather.vv 各退休一次。计数扣除5条启动 ROM 与 HTIF 退出后自旋：

| 项目 | e16/m1 | e8/mf8 |
| --- | ---: | ---: |
| 固件至 tohost 退出写的退休数 | 352177 | 751714 |
| C main 退休数 | 341197 | 742408 |
| tuple 检查后 C main 退休数 | 336883 | 740576 |
| 当前 VCS 检查后 C main 退休数 | 181858 | 222260 |
| 同速度外推总周期 | 约592419 | 约1053598 |
| 同速度外推总耗时 | 约543秒 | 约980秒 |

周期外推公式：检查结束 cycle + 当前检查后周期跨度 * Spike 完整检查后 C 退休数 / 当前 VCS 检查后 C 退休数。Spike 不是 DUT 时序模型，HTIF ELF 也不是 SoC ELF，外推不是测得的最终周期或验收。原30..120秒预算依据不适用于原循环端口，不据此盲目加 timeout。

## 旧30秒 control 差别

旧 SoC ELF `bc01908559122bca514fd150feffb467ea27a587057d7e1e378aafbd38a0157f` 在 candidate02 的 `../integration/memory_regression_plan02/replay/summary.json` 为 PASS/exit0，30.8107569秒，9469条退休、最终 cycle16329。目标 PC 为0x80000498，cycle12935。

它绑定的真实 prepared 在 `/tmp/current-board-integration-fast01/prepared/gather_original/case.c`，不是仓库中未缩界的副本：seed<1、op<1、s<1、l=2..2、mode<1、trial<1。该 prepared 的 source pins 校验通过。与本次 e16 来源的 scenario.c、operations.S、operations.h 一致；GCC 哈希与选项一致，runtime/startup/linker 一致。原 op0 的12条汇编指令编码一致，仅链接地址变化。

## 后继边界

用户授权独立 successor 仅缩六层循环到相同精确 tuple；完整 RNG/setup、原 asm、full-cap oracle、guard、返回 vstart 与统计均保留。新 prepared/soc/spike/reference 与独立 candidate04 输出，不覆盖旧输入或300秒记录。只代表八个来源 single，不是原 Linux ELF、父矩阵、83项全集或板级验收。不改 RTL、不构建镜像、不提高300秒预算、不自动重试。
