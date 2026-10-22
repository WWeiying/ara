# 单次启动记录

父明确授权、Averroes独立无阻断、fresh admission通过后，单次启动成功：
`ara-gather75-candidate04-01.service`。4 jobs、300秒/单项、6300秒外层；不重跑accepted8，
不重试、不改RTL/镜像。这里只确认启动，不宣称75项DUT PASS。

仓库根执行的命令：
```sh
python3 -B verification/fpga/current_board_review/gather_original_review/replay_remainder75.py --launch --parent-review-sha256 caed9f4ad7bcf98b1506dea72deac3cb11dd59c4edaefe5ee8500deb1eec49b5
```

输出 `Running as unit: ara-gather75-candidate04-01.service`，launcher exit0。
执行plan与审核plan字节相同，SHA256：
`116e89a3b9466ae910926653f1a84abb9c480c7dc12a9aca77ba81f5e76b2f83`。

fresh admission：future reserved24/24、MemAvailable182.85GiB；prefix/FP仍hold。
`vcs_candidate04_01/resource_gate.json` 保存完整roster与资源计数。
first12 startup原始证据在 `first12/actual_simv_confirmation.json`，状态
`ADVANCING_4_SIMV`；checker独立重算实际身份与增长，不只信observer状态。

| actual simv PID | cycle 前->后 | CPU ticks 前->后 | trace bytes 前->后 |
| --- | --- | --- | --- |
| 100441 | 599->942 | 203->253 | 32768->57344 |
| 100445 | 425->771 | 191->240 | 20480->45056 |
| 100446 | 369->713 | 177->228 | 16384->40960 |
| 100453 | 195->540 | 152->202 | 4096->28672 |

四路PID/start_ticks、actual exe、service cgroup、private work/ELF/trace/case绑定均通过。
完成这一次短窗口确认后停止外部轮询；worker在后台自动执行first12严格gate，全部PASS
才进入remaining63，并独立检查该阶段的启动。任何首错/超时/身份或启动确认失败取消
本runner，保留raw记录，不自动重试。

输出根：`vcs_candidate04_01/`。重点文件为 `first12/independent_gate.json`、
`remaining63/independent_gate.json`、`worker_exit.json`、`complete.json`；均由worker在对应
阶段/终态生成。单点记录在各阶段 `replay/tests/<case>/`，含原日志、private ELF 和trace。
`review_ready.json` 的vcs_started=false是保留的**启动前**输入快照，不是当前运行状态。
