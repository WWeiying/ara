# Remaining75 审核入口

准备、host 与 Spike75 完整 oracle+exit0、75项 dry-run 已通过；**此说明写入时未启动 DUT**。
入口为 `review_ready.json`、`plan.json`、`host_gate.json`、`dryrun_gate.json`。
计划 SHA256：`116e89a3b9466ae910926653f1a84abb9c480c7dc12a9aca77ba81f5e76b2f83`。
严格驱动/checker/负向回归位于上级 `replay_remainder75.py`、`check_remainder75.py`、
`test_remainder75.py`，3972 pins 包含代码、封存镜像/源码、原始来源和旧记录。

## 精确范围

`coverage83.json` 逐条保留来源、shape/op sourcekey、原始首错数值/detail、原/reduced Linux
ELF 哈希、parent/partition 身份及已知 duplicate aliases。**accepted8 + remaining75 = 83**
个不同来源单点，交集为空；19个 parent 和归档副本不重复计数。这不是83种标量数值
tuple，也不是大 parent 矩阵验收。当前 DUT 接受仍为8；所有75待 DUT 验收。

`prepared75/provenance.json` 收录75条完整原 case 与378个 prepared 文件的精确哈希。
12项 source/diff 原样复制，SoC/Spike ELF **沿用旧路径和哈希，未重编译**；余63项独立
准备/编译在 `fresh63/`。`soc75/programs.json` 是统一75项实际输入索引。
`reference75/` 对全部75（包括复用12）新跑 Spike：每种 op0/1/2/3/20 各15项。

每项只缩六层空枚举到同一原 trial，保留目标 seed 完整 RNG/setup、原 asm、原 full-cap
scalar oracle、双 guard、vstart 和 cases/errors。`source_diffs/` 区分既有 adapter 与六处
loop diff；`host_semantics.json` 保存逐项 fullcap 预期，`baseline_pins.json` 保留旧输入。
原 candidate03 TIMEOUT/CANCELLED 和首次 successor wrapper NOT_ACCEPTED 不变。

## 执行与负向 Gate

固定 unit `ara-gather75-candidate04-01.service`；4 jobs，300秒/单项，外层6300秒，
Restart=no、KillMode=control-group、独立 `vcs_candidate04_01/`，不重跑 accepted8。
同一 worker 先 first12；全部独立 strict gate PASS 后自动进入 remaining63，无第二次
用户权限请求。每 case 在交还线程池前核验 raw log、exit0、input/image/command 身份、
目标退休 PC/VL2/vstart1、返回 vstart0、全部 capacity 元素与 guards；首错取消本 runner。
最终 checker 再独立重验两阶段，不能只信 summary、claimed PASS 或 observer checks。

资源准入保留 whole1134 6 + NF8 8 + NF7 2 + DUT38 4 + Gather 4 = cap24，至少32GiB，
未知额外 simv/Tesla 比较冲突拒绝。ENOENT/ESRCH 退出竞态可略过；潜在 simv/Python
worker 无法读取则保守拒绝。父已承诺：**本批75全部 terminal 前不启动 prefix/FP**；
因此保留 DUT38 的固定4路 quota，不将空闲4路用于未声明 family。

worker 内部每阶段仅一次最多60秒启动观察：四路真实 PID/start_ticks、正确 exe/cgroup/
private ELF/trace/case、CPU/trace/cycle 增长。初次0.5秒无增长可在剩余窗口续采同 PID；
退出/PID换代可重新发现，身份错立即拒绝。失败保存 raw samples 并取消本 stage，不重启
模拟器；确认后不轮询长任务完成。7项 host 回归覆盖以上拒绝/竞态和12->63 fail-stop。
曾有一次假采样序列错误造成 host FAIL，保存于 `preseal_host_attempt01.json`；修正夹具后
preseal PASS，父随后独立执行7项也 PASS，其 `host_gate.json` 保留未覆盖。

## 审核后单次启动

父条件授权要求 Averroes 无阻断、全 pins/ready 不变且实际资源准入通过。
在仓库根运行（REVIEW_SHA 是 `review_ready.json` 的实际 SHA256）：
`python3 -B verification/fpga/current_board_review/gather_original_review/replay_remainder75.py --launch --parent-review-sha256 REVIEW_SHA`
不要重跑 test main 覆盖已保存 host gate；复核可用 unittest 导入方式。
输出：`vcs_candidate04_01/first12/`、`remaining63/`、`worker_exit.json`、`complete.json`。

准备耗时79.15秒；Spike 固件退休11,416–26,135条/项、target各一次，非 DUT 周期。
空枚举56448->1，最大fullcap256；已有8项23.58–62.55秒作参考，给75项每项30–120秒的
宽松估计，4路约9.5–38分钟加启动/checker开销。硬预算19波*300秒=5700秒，6300秒
外层留启动及终态检查空间；不提高单项 timeout、不改 RTL、不自动重试。
